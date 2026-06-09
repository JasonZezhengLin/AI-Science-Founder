"""
Founder Shell — the outer ecosystem adapter around the original AI Scientist agent.
"""

import json
import inspect
import logging
import os
import threading
from pathlib import Path
from typing import List, Optional

from ai_system import messages
from ai_system.suspension import (
    ExperimentCheckpoint,
    ResumeToken,
    load_checkpoint,
    save_checkpoint,
)

logger = logging.getLogger(__name__)

_ENV_LOCK = threading.Lock()


class FounderStatus:
    IDLE = "idle"
    IDEATING = "ideating"
    PENDING_FUNDING = "pending_funding"
    EXPERIMENTING = "experimenting"
    SUSPENDED = "suspended"
    WAITING_FUNDING = "waiting_funding"
    WRITING = "writing"
    UNDER_REVIEW = "under_review"
    DEAD = "dead"


class FounderShell:
    def __init__(
        self,
        founder_id: str,
        skill_manager,
        profile,
        token_budget,
        investors: List[dict],
        literature_db,
        peer_review,
        idea_generator,
        experiment_runner,
        writeup_runner,
        proposal_builder,
        recorder=None,
        model: str = "qwen3.6-plus",
        skill_store_dir: str = "ai_system/skill_store",
        profile_store_dir: str = "ai_system/profile_store",
        resource_scheduler=None,
        gpus_per_funding: int = 1,
        state_store_dir: str = "ai_system/runtime_state",
    ):
        self.founder_id = founder_id
        self.skill_manager = skill_manager
        self.profile = profile
        self.token_budget = token_budget
        self.investors = investors
        self.literature_db = literature_db
        self.peer_review = peer_review
        self._idea_generator = idea_generator
        self._experiment_runner = experiment_runner
        self._writeup_runner = writeup_runner
        self._proposal_builder = proposal_builder
        self.recorder = recorder
        self.model = model
        self.resource_scheduler = resource_scheduler
        self.gpus_per_funding = gpus_per_funding
        self.state_store_dir = state_store_dir

        self.status = FounderStatus.IDLE
        self.current_idea: Optional[dict] = None
        self.current_investor_id: Optional[str] = None
        self.cycle_count = 0
        self.gpu_ids: List[int] = []
        self.active_checkpoint: Optional[ExperimentCheckpoint] = None
        self.resume_token: Optional[ResumeToken] = None
        self.current_paper: Optional[dict] = None
        self.current_paper_id: Optional[str] = None
        self.last_experiment_result: Optional[dict] = None
        self.pending_extra_funding_request: Optional[dict] = None
        self.pending_proposal = None
        self._state_dir = Path(self.state_store_dir) / self.founder_id
        self._state_dir.mkdir(parents=True, exist_ok=True)

    def run_cycle(self) -> bool:
        """
        Compatibility wrapper that drives the same message/state-machine path
        used by the message-driven orchestrator.
        """
        pending_message = None
        if self.status == FounderStatus.IDLE and self.resume_token is None:
            pending_message = self.start_cycle_async()

        max_steps = 64
        for _ in range(max_steps):
            if pending_message is None:
                if self.status in (FounderStatus.IDLE, FounderStatus.DEAD):
                    return self.status == FounderStatus.IDLE
                pending_message = self.advance_async()
                if pending_message is None:
                    if self.status in (FounderStatus.IDLE, FounderStatus.DEAD):
                        return self.status == FounderStatus.IDLE
                    continue

            pending_message = self._dispatch_local_message(pending_message)

        raise RuntimeError(
            f"[{self.founder_id}] run_cycle exceeded {max_steps} state-machine steps"
        )

    def _dispatch_local_message(self, message: dict) -> Optional[dict]:
        msg_type = message.get("type")
        logger.info(f"[{self.founder_id}] handling message: {msg_type}")

        if msg_type == messages.INITIAL_FUNDING_REQUEST:
            investor = self._find_investor(message["investor_id"])
            if investor is None:
                self._bankrupt("Investor 不存在")
                return None
            decision = investor.evaluate_initial_proposal(
                message["proposal_text"],
                message["profile_summary"],
            )
            self.apply_initial_funding_decision(decision, investor.investor_id)
            return None

        if msg_type == messages.EXTRA_FUNDING_REQUEST:
            investor = self._find_investor(message["investor_id"])
            if investor is None:
                self._bankrupt("追加经费时 Investor 不存在")
                return None
            decision = investor.evaluate_extra_funding(
                message["progress_summary"],
                message["profile_summary"],
            )
            self.apply_extra_funding_decision(decision)
            return None

        if msg_type == messages.PAPER_SUBMISSION:
            kwargs = {}
            signature = inspect.signature(self.peer_review.evaluate)
            paper = message["paper"]
            if "paper_pdf_path" in signature.parameters:
                kwargs["paper_pdf_path"] = paper.get("pdf_path")
            review_result = self.peer_review.evaluate(
                paper.get("title", ""),
                paper.get("text", ""),
                self.founder_id,
                **kwargs,
            )
            self.finalize_review_result(review_result)
            return None

        raise ValueError(f"Unknown local message type: {msg_type}")

    def start_cycle_async(self) -> Optional[dict]:
        if self.status != FounderStatus.IDLE:
            return None
        self.cycle_count += 1
        logger.info(f"[{self.founder_id}] ===== 第 {self.cycle_count} 轮异步循环开始 =====")
        if not self.token_budget.can_afford():
            self._bankrupt("ideation 前 token 耗尽")
            return None

        self.status = FounderStatus.IDEATING
        idea = self._run_ideation()
        if idea is None:
            # ideation（含重试）失败：本轮跳过，保留 IDLE 让下一轮重试，
            # 不直接判 dead（founder 应有韧性）
            logger.warning(f"[{self.founder_id}] 本轮 ideation 失败，跳过本轮，保留存活")
            self.status = FounderStatus.IDLE
            if self.recorder is not None:
                self.recorder.log_event(
                    self.founder_id,
                    "ideation_failed_skip_cycle",
                    {"cycle_count": self.cycle_count},
                )
            return None
        self.current_idea = idea

        self.status = FounderStatus.PENDING_FUNDING
        proposal = self._build_proposal(idea)
        if proposal is None:
            self._bankrupt("proposal 构建失败")
            return None
        self.pending_proposal = proposal
        if self.recorder is not None:
            self.recorder.write_json(
                self.recorder.proposal_path(self.founder_id, self.cycle_count),
                {
                    "founder_id": self.founder_id,
                    "cycle_count": self.cycle_count,
                    "idea": idea,
                    "selected_investor_id": proposal.selected_investor_id,
                    "selection_reason": proposal.selection_reason,
                    "proposal_text": proposal.proposal_text,
                    "profile_summary": self.profile.summary(),
                },
            )
            self.recorder.log_event(
                self.founder_id,
                "proposal_created",
                {
                    "cycle_count": self.cycle_count,
                    "idea_title": idea.get("Title", "Untitled"),
                    "selected_investor_id": proposal.selected_investor_id,
                    "selection_reason": proposal.selection_reason,
                },
            )
        return {
            "type": messages.INITIAL_FUNDING_REQUEST,
            "founder_id": self.founder_id,
            "investor_id": proposal.selected_investor_id,
            "proposal_text": proposal.proposal_text,
            "selection_reason": proposal.selection_reason,
            "idea_title": idea.get("Title", "Untitled"),
            "profile_summary": self.profile.summary(),
        }

    def apply_initial_funding_decision(self, decision, investor_id: str) -> bool:
        investor = self._find_investor(investor_id)
        if investor is None:
            return self._bankrupt("Investor 不存在")
        if not decision.approved:
            if self.recorder is not None:
                self.recorder.log_event(
                    self.founder_id,
                    "initial_funding_decision",
                    {
                        "cycle_count": self.cycle_count,
                        "proposal_text": self.pending_proposal.proposal_text if self.pending_proposal else None,
                        "decision": {
                            "approved": decision.approved,
                            "token_amount_usd": decision.token_amount_usd,
                            "reason": decision.reason,
                            "gpu_ids": decision.gpu_ids or [],
                        },
                        "investor_id": investor.investor_id,
                    },
                )
            self._update_skill_from_event(
                f"Funding proposal rejected by {investor.investor_id}.",
                decision.reason,
            )
            self.status = FounderStatus.IDLE
            self.pending_proposal = None
            self.current_idea = None
            self.current_investor_id = None
            return False
        self.current_investor_id = investor.investor_id
        if self.recorder is not None:
            self.recorder.log_event(
                self.founder_id,
                "initial_funding_decision",
                {
                    "cycle_count": self.cycle_count,
                    "proposal_text": self.pending_proposal.proposal_text if self.pending_proposal else None,
                    "decision": {
                        "approved": decision.approved,
                        "token_amount_usd": decision.token_amount_usd,
                        "reason": decision.reason,
                        "gpu_ids": decision.gpu_ids or [],
                    },
                    "investor_id": investor.investor_id,
                },
            )
        self._activate_funding(decision, investor)
        self.pending_proposal = None
        self.status = FounderStatus.EXPERIMENTING
        return True

    def apply_extra_funding_decision(self, decision) -> bool:
        investor = self._find_investor(self.current_investor_id) if self.current_investor_id else None
        if investor is None:
            return self._bankrupt("追加经费时 Investor 不存在")
        self.profile.record_extra_funding(
            investor.investor_id,
            decision.token_amount_usd,
            "approved" if decision.approved else "rejected",
            cycle_count=self.cycle_count,
            checkpoint_path=self.resume_token.checkpoint_path if self.resume_token else None,
        )
        if decision.approved:
            if self.recorder is not None:
                self.recorder.log_event(
                    self.founder_id,
                    "extra_funding_decision",
                    {
                        "cycle_count": self.cycle_count,
                        "decision": {
                            "approved": decision.approved,
                            "token_amount_usd": decision.token_amount_usd,
                            "reason": decision.reason,
                        },
                        "investor_id": investor.investor_id,
                    },
                )
            self.token_budget.replenish(decision.token_amount_usd)
            if self.resume_token is not None:
                self.resume_token.requested_extra_funding_usd = decision.token_amount_usd
            self._update_skill_from_event(
                f"Extra funding approved by {investor.investor_id} (+${decision.token_amount_usd}).",
                decision.reason or "",
            )
            self.status = FounderStatus.SUSPENDED
            self.pending_extra_funding_request = None
            return True
        self._update_skill_from_event(
            f"Extra funding rejected by {investor.investor_id}.",
            decision.reason or "",
        )
        if self.recorder is not None:
            self.recorder.log_event(
                self.founder_id,
                "extra_funding_decision",
                {
                    "cycle_count": self.cycle_count,
                    "decision": {
                        "approved": decision.approved,
                        "token_amount_usd": decision.token_amount_usd,
                        "reason": decision.reason,
                    },
                    "investor_id": investor.investor_id,
                },
            )
        self.pending_extra_funding_request = None
        return self._bankrupt("追加经费被拒")

    def advance_async(self) -> Optional[dict]:
        if self.status in (
            FounderStatus.IDLE,
            FounderStatus.PENDING_FUNDING,
            FounderStatus.UNDER_REVIEW,
            FounderStatus.DEAD,
        ):
            return None

        if self.status in (
            FounderStatus.EXPERIMENTING,
            FounderStatus.SUSPENDED,
            FounderStatus.WAITING_FUNDING,
        ):
            if self.status == FounderStatus.WAITING_FUNDING:
                return self.pending_extra_funding_request
            checkpoint = self._load_resume_checkpoint() if self.resume_token is not None else None
            if checkpoint is not None and self.status == FounderStatus.SUSPENDED:
                self.profile.record_cycle_resumed(
                    checkpoint.stage_label,
                    self.resume_token.checkpoint_path if self.resume_token else "",
                    cycle_count=self.cycle_count,
                )
            if checkpoint is not None and checkpoint.stage_label == "writeup":
                self.last_experiment_result = checkpoint.metadata.get("experiment_result", {})
                self.status = FounderStatus.WRITING
                experiment_result = self.last_experiment_result
            else:
                experiment_result = self._run_experiment_with_budget(
                    self.current_idea,
                    resume=checkpoint is not None,
                    checkpoint=checkpoint,
                    defer_extra_funding=True,
                )
            if self.status == FounderStatus.WAITING_FUNDING:
                return self.pending_extra_funding_request
            if experiment_result is None:
                return None
            self.last_experiment_result = experiment_result
            self.status = FounderStatus.WRITING

        if self.status == FounderStatus.WRITING:
            paper = self._run_writeup(
                self.last_experiment_result or {},
                defer_extra_funding=True,
            )
            if self.status == FounderStatus.WAITING_FUNDING:
                return self.pending_extra_funding_request
            if paper is None:
                return None
            self.current_paper = paper
            self.status = FounderStatus.UNDER_REVIEW
            self._upsert_under_review_paper(self.current_idea or {}, paper)
            return {
                "type": messages.PAPER_SUBMISSION,
                "founder_id": self.founder_id,
                "paper": paper,
                "paper_id": self.current_paper_id,
                "idea_title": (self.current_idea or {}).get("Title", "Untitled"),
            }
        return None

    def finalize_review_result(self, review_result) -> bool:
        if self.current_paper is None or self.current_idea is None:
            return self._bankrupt("review 完成时论文状态丢失")
        self._finalize_literature_record(
            self.current_idea,
            self.current_paper,
            review_result.accepted,
        )
        if self.recorder is not None:
            review_payload = {
                "founder_id": self.founder_id,
                "cycle_count": self.cycle_count,
                "paper_id": self.current_paper_id,
                "paper_title": self.current_paper.get("title", ""),
                "accepted": review_result.accepted,
                "overall_score": review_result.overall_score,
                "meta_review": review_result.meta_review,
                "reviews": review_result.reviews,
            }
            self.recorder.write_json(
                self.recorder.review_path(
                    self.founder_id,
                    self.cycle_count,
                    self.current_paper_id,
                ),
                review_payload,
            )
            self.recorder.log_event(
                self.founder_id,
                "review_result",
                review_payload,
            )
        self.profile.record_paper_completed(
            self.current_investor_id or "unknown",
            self.current_paper.get("title", ""),
            review_result.accepted,
            cycle_count=self.cycle_count,
            paper_id=self.current_paper_id,
        )
        feedback_text = json.dumps(review_result.reviews, indent=2)
        event_desc = (
            f"Paper '{self.current_paper.get('title', '')}' was "
            f"{'accepted' if review_result.accepted else 'rejected'} after peer review."
        )
        self._update_skill_from_event(event_desc, feedback_text)
        self._clear_resume_state()
        self._release_gpus()
        self.current_paper = None
        self.current_paper_id = None
        self.last_experiment_result = None
        self.current_idea = None
        self.current_investor_id = None
        self.pending_proposal = None
        if not self.token_budget.can_afford():
            return self._bankrupt("循环结束后 token 耗尽")
        self.status = FounderStatus.IDLE
        if self.recorder is not None:
            self.recorder.log_event(
                self.founder_id,
                "cycle_finished",
                {
                    "cycle_count": self.cycle_count,
                    "success": True,
                    "summary": self.summary(),
                },
            )
        return True

    def _release_gpus(self):
        if self.resource_scheduler is not None and self.current_investor_id and self.gpu_ids:
            self.resource_scheduler.release_from_founder(
                self.current_investor_id, self.founder_id
            )
        self.gpu_ids = []

    def _run_ideation(self, max_attempts: int = 3) -> Optional[dict]:
        skill_text = self.skill_manager.load()
        logger.info(f"[{self.founder_id}] 开始 ideation（skill 长度: {len(skill_text)}）")
        last_err = None
        for attempt in range(1, max_attempts + 1):
            try:
                idea = self._idea_generator(skill_text, self.model)
                if idea is None:
                    logger.warning(
                        f"[{self.founder_id}] Ideation 返回 None"
                        f"（尝试 {attempt}/{max_attempts}）"
                    )
                    last_err = "ideation returned None"
                    continue
                if self.recorder is not None:
                    self.recorder.log_event(
                        self.founder_id,
                        "ideation_completed",
                        {
                            "cycle_count": self.cycle_count,
                            "idea": idea,
                            "attempts": attempt,
                        },
                    )
                logger.info(f"[{self.founder_id}] Ideation 完成: {idea.get('Title', 'Untitled')}")
                return idea
            except Exception as e:
                logger.warning(
                    f"[{self.founder_id}] Ideation 异常"
                    f"（尝试 {attempt}/{max_attempts}）: {e}"
                )
                last_err = str(e)
        logger.error(
            f"[{self.founder_id}] Ideation 连续 {max_attempts} 次失败，本轮放弃: {last_err}"
        )
        return None

    def _build_proposal(self, idea: dict):
        from ai_system.proposal_builder import build_proposal_debug
        from ai_system.token_budget import (
            BudgetExhaustedException,
            deduct_against_since,
            snapshot_token_counts,
        )

        investor_infos = [
            {"investor_id": inv.investor_id, "direction": inv.direction}
            for inv in self.investors
        ]
        is_llm_path = self._proposal_builder is not build_proposal_debug
        snapshot = snapshot_token_counts(self.model) if is_llm_path else None

        proposal_builder = self._proposal_builder
        kwargs = {
            "idea": idea,
            "founder_id": self.founder_id,
            "founder_profile_summary": self.profile.summary(),
            "investors": investor_infos,
            "model": self.model,
        }
        params = inspect.signature(proposal_builder).parameters
        if "recorder" in params:
            kwargs["recorder"] = self.recorder
        if "cycle_count" in params:
            kwargs["cycle_count"] = self.cycle_count
        result = proposal_builder(**kwargs)
        if result is not None and is_llm_path:
            try:
                deduct_against_since(self.token_budget, snapshot, self.model)
            except BudgetExhaustedException:
                logger.info(f"[{self.founder_id}] proposal 构建后预算耗尽")
        return result

    def _find_investor(self, investor_id: str):
        for inv in self.investors:
            if inv.investor_id == investor_id:
                return inv
        return None

    def _activate_funding(self, decision, investor):
        token_amount = decision.token_amount_usd
        if decision.gpu_ids:
            self.gpu_ids = decision.gpu_ids
        elif self.resource_scheduler is not None:
            allocated = self.resource_scheduler.allocate_to_founder(
                investor.investor_id,
                self.founder_id,
                num_gpus=self.gpus_per_funding,
            )
            self.gpu_ids = allocated if allocated else []
            if not allocated:
                logger.warning(
                    f"[{self.founder_id}] ResourceScheduler 无空闲 GPU，实验将走 CPU 路径。"
                )
        else:
            static_gpus = getattr(investor, "_gpu_ids", [0])
            self.gpu_ids = static_gpus[: self.gpus_per_funding] if static_gpus else []
        self.token_budget.replenish(token_amount)
        self.profile.record_funding_approved(
            investor.investor_id,
            (self.current_idea or {}).get("Title", "Untitled"),
            token_amount,
            self.gpu_ids,
            cycle_count=self.cycle_count,
        )
        logger.info(
            f"[{self.founder_id}] 获批 ${token_amount}，GPU {self.gpu_ids} (from {investor.investor_id})"
        )
        self._update_skill_from_event(
            f"Funding proposal approved by {investor.investor_id} (${token_amount}).",
            decision.reason or "",
        )

    def _run_experiment_with_budget(
        self,
        idea: dict,
        resume: bool = False,
        checkpoint: Optional[ExperimentCheckpoint] = None,
        defer_extra_funding: bool = False,
    ) -> Optional[dict]:
        from ai_system.token_budget import (
            BudgetExhaustedException,
            apply,
            reset_budget,
            set_budget,
        )

        max_extra_requests = 3
        budget_token = set_budget(self.token_budget)
        apply()
        skill_text = self.skill_manager.load()

        try:
            extra_attempts = checkpoint.extra_attempts if checkpoint is not None else 0
            try:
                if getattr(self._experiment_runner, "isolated_process", False):
                    result = self._call_experiment_runner(
                        idea=idea,
                        skill_text=skill_text,
                        resume=resume,
                        checkpoint=checkpoint,
                    )
                    if self.recorder is not None and result is not None:
                        self.recorder.log_event(
                            self.founder_id,
                            "experiment_completed",
                            {
                                "cycle_count": self.cycle_count,
                                "result": result,
                            },
                        )
                    return result
                with _ENV_LOCK:
                    had_cuda = "CUDA_VISIBLE_DEVICES" in os.environ
                    had_skill = "AI_SCIENTIST_SKILL" in os.environ
                    prev_cuda = os.environ.get("CUDA_VISIBLE_DEVICES")
                    prev_skill = os.environ.get("AI_SCIENTIST_SKILL")

                    if self.gpu_ids:
                        os.environ["CUDA_VISIBLE_DEVICES"] = ",".join(
                            str(gpu_id) for gpu_id in self.gpu_ids
                        )
                    else:
                        os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
                    os.environ["AI_SCIENTIST_SKILL"] = skill_text

                    try:
                        result = self._call_experiment_runner(
                            idea=idea,
                            skill_text=skill_text,
                            resume=resume,
                            checkpoint=checkpoint,
                        )
                        if self.recorder is not None and result is not None:
                            self.recorder.log_event(
                                self.founder_id,
                                "experiment_completed",
                                {
                                    "cycle_count": self.cycle_count,
                                    "result": result,
                                },
                            )
                        return result
                    finally:
                        if had_cuda:
                            os.environ["CUDA_VISIBLE_DEVICES"] = prev_cuda
                        else:
                            os.environ.pop("CUDA_VISIBLE_DEVICES", None)
                        if had_skill:
                            os.environ["AI_SCIENTIST_SKILL"] = prev_skill
                        else:
                            os.environ.pop("AI_SCIENTIST_SKILL", None)
            except BudgetExhaustedException:
                logger.warning(
                    f"[{self.founder_id}] 预算耗尽！剩余 ${self.token_budget.remaining_usd:.4f}"
                )
                if extra_attempts >= max_extra_requests:
                    self._bankrupt(f"追加经费达到上限 {max_extra_requests} 次")
                    return None
                return self._suspend_with_checkpoint(
                    idea=idea,
                    stage_label="experiment",
                    extra_attempts=extra_attempts + 1,
                    metadata={"resume_invocation": resume},
                    defer_funding_request=defer_extra_funding,
                )
            except Exception as e:
                logger.error(f"[{self.founder_id}] 实验异常: {e}")
                return None
        finally:
            reset_budget(budget_token)

    def _call_experiment_runner(
        self,
        idea: dict,
        skill_text: str,
        resume: bool,
        checkpoint: Optional[ExperimentCheckpoint],
    ) -> dict:
        runner = self._experiment_runner
        kwargs = {}
        signature = inspect.signature(runner)
        params = signature.parameters
        if "resume" in params:
            kwargs["resume"] = resume
        if "checkpoint" in params:
            kwargs["checkpoint"] = checkpoint
        if "skill_text" in params:
            kwargs["skill_text"] = skill_text
        if "founder_id" in params:
            kwargs["founder_id"] = self.founder_id
        if "cycle_count" in params:
            kwargs["cycle_count"] = self.cycle_count
        return runner(idea, self.gpu_ids, self.model, **kwargs)

    def _suspend_with_checkpoint(
        self,
        idea: dict,
        stage_label: str,
        extra_attempts: int,
        metadata: Optional[dict] = None,
        defer_funding_request: bool = False,
    ) -> Optional[dict]:
        self._create_checkpoint(
            idea=idea,
            stage_label=stage_label,
            extra_attempts=extra_attempts,
            metadata=metadata,
        )
        self.status = FounderStatus.SUSPENDED
        logger.info(
            f"[{self.founder_id}] 实验已挂起，checkpoint={self.resume_token.checkpoint_path if self.resume_token else 'n/a'}"
        )
        self.pending_extra_funding_request = {
            "type": messages.EXTRA_FUNDING_REQUEST,
            "founder_id": self.founder_id,
            "investor_id": self.current_investor_id,
            "idea_title": self.current_idea.get("Title", "Unknown") if self.current_idea else "Unknown",
            "progress_summary": {
                "founder_id": self.founder_id,
                "idea_title": self.current_idea.get("Title", "Unknown") if self.current_idea else "Unknown",
                "token_consumed": self.token_budget.total_consumed_usd,
                "remaining": self.token_budget.remaining_usd,
                "checkpoint_path": self.resume_token.checkpoint_path if self.resume_token else None,
                "stage_label": stage_label,
                "extra_attempts": extra_attempts,
            },
            "profile_summary": self.profile.summary(),
        }
        self.status = FounderStatus.WAITING_FUNDING
        if defer_funding_request:
            return None
        if self._request_extra_funding():
            self.status = FounderStatus.SUSPENDED
            return None
        self._bankrupt("追加经费被拒")
        return None

    def _next_extra_attempts(self) -> int:
        if self.active_checkpoint is not None:
            return self.active_checkpoint.extra_attempts + 1
        return 1

    def _checkpoint_path(self, cycle_count: Optional[int] = None) -> Path:
        cycle_id = cycle_count if cycle_count is not None else self.cycle_count
        return self._state_dir / f"cycle_{cycle_id}_checkpoint.json"

    def _create_checkpoint(
        self,
        idea: dict,
        stage_label: str,
        extra_attempts: int,
        metadata: Optional[dict] = None,
    ) -> ExperimentCheckpoint:
        checkpoint = ExperimentCheckpoint(
            founder_id=self.founder_id,
            cycle_count=self.cycle_count,
            idea=json.loads(json.dumps(idea)),
            investor_id=self.current_investor_id,
            gpu_ids=list(self.gpu_ids),
            stage_label=stage_label,
            budget_spent_usd=self.token_budget.total_consumed_usd,
            budget_remaining_usd=self.token_budget.remaining_usd,
            extra_attempts=extra_attempts,
            metadata=metadata or {},
        )
        checkpoint_path = self._checkpoint_path(checkpoint.cycle_count)
        save_checkpoint(str(checkpoint_path), checkpoint)
        self.active_checkpoint = checkpoint
        self.resume_token = ResumeToken(
            checkpoint_path=str(checkpoint_path),
            suspend_reason="budget_exhausted",
            requested_extra_funding_usd=None,
        )
        self.profile.record_experiment_suspended(
            reason="budget_exhausted",
            checkpoint_path=str(checkpoint_path),
            stage_label=stage_label,
            extra_attempts=extra_attempts,
            cycle_count=self.cycle_count,
        )
        return checkpoint

    def _load_resume_checkpoint(self) -> Optional[ExperimentCheckpoint]:
        if self.resume_token is None:
            return None
        try:
            checkpoint = load_checkpoint(self.resume_token.checkpoint_path)
            self.active_checkpoint = checkpoint
            return checkpoint
        except Exception as e:
            logger.error(f"[{self.founder_id}] 读取 checkpoint 失败: {e}")
            return None

    def _clear_resume_state(self):
        checkpoint_path = self.resume_token.checkpoint_path if self.resume_token else None
        self.active_checkpoint = None
        self.resume_token = None
        self.pending_extra_funding_request = None
        if checkpoint_path and os.path.exists(checkpoint_path):
            try:
                os.remove(checkpoint_path)
            except OSError as e:
                logger.warning(f"[{self.founder_id}] 删除 checkpoint 失败: {e}")

    def _request_extra_funding(self) -> bool:
        if self.current_investor_id is None:
            logger.warning(f"[{self.founder_id}] 无当前 Investor，无法申请追加。")
            return False
        investor = self._find_investor(self.current_investor_id)
        if investor is None:
            return False

        progress_summary = {
            "founder_id": self.founder_id,
            "idea_title": self.current_idea.get("Title", "Unknown") if self.current_idea else "Unknown",
            "token_consumed": self.token_budget.total_consumed_usd,
            "remaining": self.token_budget.remaining_usd,
        }
        decision = investor.evaluate_extra_funding(
            progress_summary, self.profile.summary()
        )
        self.profile.record_extra_funding(
            investor.investor_id,
            decision.token_amount_usd,
            "approved" if decision.approved else "rejected",
            cycle_count=self.cycle_count,
            checkpoint_path=self.resume_token.checkpoint_path if self.resume_token else None,
        )

        if decision.approved:
            self.token_budget.replenish(decision.token_amount_usd)
            logger.info(f"[{self.founder_id}] 追加获批: +${decision.token_amount_usd}")
            if self.resume_token is not None:
                self.resume_token.requested_extra_funding_usd = decision.token_amount_usd
            self._update_skill_from_event(
                f"Extra funding approved by {investor.investor_id} (+${decision.token_amount_usd}).",
                decision.reason or "",
            )
            return True

        logger.info(f"[{self.founder_id}] 追加被拒: {decision.reason}")
        self._update_skill_from_event(
            f"Extra funding rejected by {investor.investor_id}.",
            decision.reason or "",
        )
        return False

    def _run_writeup(self, experiment_result: dict, defer_extra_funding: bool = False) -> Optional[dict]:
        from ai_system.token_budget import (
            BudgetExhaustedException,
            deduct_against_since,
            snapshot_token_counts,
        )

        skill_text = self.skill_manager.load()
        try:
            snapshot = snapshot_token_counts(self.model)
            paper = self._writeup_runner(experiment_result, skill_text, self.model)
            deduct_against_since(self.token_budget, snapshot, self.model)
            if self.recorder is not None and paper is not None:
                self.recorder.log_event(
                    self.founder_id,
                    "writeup_completed",
                    {
                        "cycle_count": self.cycle_count,
                        "paper_title": paper.get("title", ""),
                        "pdf_path": paper.get("pdf_path"),
                        "text_path": paper.get("text_path"),
                        "writeup_mode": paper.get("writeup_mode"),
                    },
                )
            return paper
        except BudgetExhaustedException:
            logger.warning(f"[{self.founder_id}] Writeup 后预算耗尽")
            return self._suspend_with_checkpoint(
                idea=self.current_idea or {},
                stage_label="writeup",
                extra_attempts=self._next_extra_attempts(),
                metadata={"experiment_result": experiment_result},
                defer_funding_request=defer_extra_funding,
            )
        except Exception as e:
            logger.error(f"[{self.founder_id}] Writeup 异常: {e}")
            return None

    def _upsert_under_review_paper(self, idea: dict, paper: dict):
        artifact_paths = []
        for key in ("pdf_path", "text_path"):
            if paper.get(key):
                artifact_paths.append(paper[key])
        if self.current_paper_id is None:
            self.current_paper_id = self.literature_db.add_paper(
                title=paper.get("title", idea.get("Title", "Untitled")),
                abstract=idea.get("Abstract", ""),
                authors=[self.founder_id],
                status="under_review",
                founder_id=self.founder_id,
                paper_text=paper.get("text", ""),
                pdf_path=paper.get("pdf_path"),
                text_path=paper.get("text_path"),
                artifact_paths=artifact_paths,
            )
            return
        self.literature_db.update_paper(
            self.current_paper_id,
            status="under_review",
            abstract=idea.get("Abstract", ""),
            paper_text=paper.get("text", ""),
            pdf_path=paper.get("pdf_path"),
            text_path=paper.get("text_path"),
            artifact_paths=artifact_paths,
        )

    def _finalize_literature_record(self, idea: dict, paper: dict, accepted: bool):
        status = "published" if accepted else "rejected"
        artifact_paths = []
        for key in ("pdf_path", "text_path"):
            if paper.get(key):
                artifact_paths.append(paper[key])
        if self.current_paper_id is None:
            self.current_paper_id = self.literature_db.add_paper(
                title=paper.get("title", idea.get("Title", "Untitled")),
                abstract=idea.get("Abstract", ""),
                authors=[self.founder_id],
                status=status,
                founder_id=self.founder_id,
                paper_text=paper.get("text", ""),
                pdf_path=paper.get("pdf_path"),
                text_path=paper.get("text_path"),
                artifact_paths=artifact_paths,
            )
            return
        self.literature_db.update_paper(
            self.current_paper_id,
            status=status,
            abstract=idea.get("Abstract", ""),
            paper_text=paper.get("text", ""),
            pdf_path=paper.get("pdf_path"),
            text_path=paper.get("text_path"),
            artifact_paths=artifact_paths,
        )

    def _update_skill_from_event(self, event_desc: str, feedback_text: str):
        if not self.token_budget.can_afford():
            logger.info(f"[{self.founder_id}] 预算不足，跳过 skill 更新: {event_desc}")
            return

        from ai_system.token_budget import (
            BudgetExhaustedException,
            deduct_against_since,
            snapshot_token_counts,
        )

        current_skill = self.skill_manager.load()
        try:
            snapshot = snapshot_token_counts(self.model)
            _, ok = self.skill_manager.update_from_feedback(
                current_skill=current_skill,
                event_description=event_desc,
                feedback_text=feedback_text,
                model=self.model,
            )
            if ok:
                try:
                    deduct_against_since(self.token_budget, snapshot, self.model)
                except BudgetExhaustedException:
                    logger.info(f"[{self.founder_id}] Skill 更新后预算耗尽（已记账）")
        except Exception as e:
            logger.error(f"[{self.founder_id}] Skill 更新异常: {e}")

    def _bankrupt(self, reason: str) -> bool:
        self.status = FounderStatus.DEAD
        self.profile.record_bankruptcy(cycle_count=self.cycle_count, reason=reason)
        if self.recorder is not None:
            self.recorder.log_event(
                self.founder_id,
                "bankruptcy",
                {
                    "cycle_count": self.cycle_count,
                    "reason": reason,
                    "summary": self.summary(),
                },
            )
        self._clear_resume_state()
        self._release_gpus()
        logger.info(f"[{self.founder_id}] 破产: {reason}")
        return False

    def is_alive(self) -> bool:
        return self.status != FounderStatus.DEAD

    def summary(self) -> dict:
        return {
            "founder_id": self.founder_id,
            "status": self.status,
            "cycle_count": self.cycle_count,
            "profile": self.profile.summary(),
            "budget": self.token_budget.summary(),
            "current_idea": self.current_idea.get("Title") if self.current_idea else None,
            "current_investor": self.current_investor_id,
            "gpu_ids": self.gpu_ids,
            "resume_token": self.resume_token.to_dict() if self.resume_token else None,
        }
