"""
Investor implementations for the founder ecosystem.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {
            "true",
            "yes",
            "1",
            "approve",
            "approved",
            "y",
            "t",
        }
    if isinstance(value, (int, float)):
        return value != 0
    return bool(value)


@dataclass
class FundingDecision:
    approved: bool
    token_amount_usd: float
    reason: str
    gpu_ids: Optional[List[int]] = None


class BatchReviewInvestorMixin:
    max_projects_per_round: int = 3
    application_queue: List[Dict[str, Any]]
    active_projects: Dict[str, Dict[str, Any]]

    def _init_batch_state(self):
        self.application_queue = []
        self.active_projects = {}

    def submit_application(self, proposal: Dict[str, Any]):
        self.application_queue.append(proposal)

    def can_open_initial_round(self) -> bool:
        return len(self.active_projects) == 0 and len(self.application_queue) > 0

    def mark_project_started(self, founder_id: str, decision: FundingDecision):
        self.active_projects[founder_id] = {
            "gpu_ids": list(decision.gpu_ids or []),
            "token_amount_usd": decision.token_amount_usd,
        }

    def mark_project_finished(self, founder_id: str):
        self.active_projects.pop(founder_id, None)

    def drain_application_queue(self) -> List[Dict[str, Any]]:
        batch = list(self.application_queue)
        self.application_queue = []
        return batch

    def evaluate_initial_batch(
        self, proposal_batch: List[Dict[str, Any]]
    ) -> Dict[str, FundingDecision]:
        decisions = {}
        gpu_slots = len(getattr(self, "_gpu_ids", []))
        batch_limit = self.max_projects_per_round
        if gpu_slots > 0:
            batch_limit = min(batch_limit, gpu_slots)
        ordered_batch = proposal_batch[: batch_limit]
        for proposal in ordered_batch:
            founder_id = proposal["founder_id"]
            decisions[founder_id] = self.evaluate_initial_proposal(
                proposal["proposal_text"],
                proposal["profile_summary"],
            )
        for proposal in proposal_batch[batch_limit:]:
            founder_id = proposal["founder_id"]
            decisions[founder_id] = FundingDecision(
                approved=False,
                token_amount_usd=0.0,
                reason=(
                    f"Investor {self.investor_id} reached the per-round cap "
                    f"of {batch_limit} proposals."
                ),
            )
        return decisions


class YesManInvestor(BatchReviewInvestorMixin):
    def __init__(
        self,
        investor_id: str = "yesman",
        direction: str = "General ML research",
        token_pool: float = 1_000_000.0,
        max_projects_per_round: int = 3,
        approval_amount_usd: Optional[float] = None,
        extra_amount_usd: Optional[float] = None,
        recorder=None,
    ):
        self.investor_id = investor_id
        self.direction = direction
        self.token_pool = token_pool
        self.max_projects_per_round = max_projects_per_round
        self.recorder = recorder
        self._init_batch_state()

        from ai_system.config import (
            INVESTOR_APPROVAL_TOKEN_USD,
            INVESTOR_EXTRA_TOKEN_USD,
        )

        self.approval_amount = (
            approval_amount_usd
            if approval_amount_usd is not None
            else INVESTOR_APPROVAL_TOKEN_USD
        )
        self.extra_amount = (
            extra_amount_usd
            if extra_amount_usd is not None
            else INVESTOR_EXTRA_TOKEN_USD
        )

    def evaluate_initial_proposal(
        self, proposal_text: str, founder_profile: dict
    ) -> FundingDecision:
        if self.token_pool < self.approval_amount:
            return FundingDecision(
                approved=False,
                token_amount_usd=0,
                reason=f"Investor {self.investor_id} 资金池不足。",
            )

        self.token_pool -= self.approval_amount
        return FundingDecision(
            approved=True,
            token_amount_usd=self.approval_amount,
            reason=f"YesMan: 永远批准。基于方向 '{self.direction}'。",
        )

    def evaluate_extra_funding(
        self, progress_summary: dict, founder_profile: dict
    ) -> FundingDecision:
        if self.token_pool < self.extra_amount:
            return FundingDecision(
                approved=False,
                token_amount_usd=0,
                reason=f"Investor {self.investor_id} 资金池不足。",
            )

        self.token_pool -= self.extra_amount
        return FundingDecision(
            approved=True,
            token_amount_usd=self.extra_amount,
            reason="YesMan: 永远批准追加。",
        )

    def evaluate_initial_batch(
        self, proposal_batch: List[Dict[str, Any]]
    ) -> Dict[str, FundingDecision]:
        affordable_slots = int(self.token_pool // max(self.approval_amount, 1e-9))
        gpu_pool = list(getattr(self, "_gpu_ids", []))
        gpu_slots = len(gpu_pool)
        # CPU fallback: 当没有 GPU 时（gpu_slots==0），不把 GPU 当作 batch 的硬上限，
        # 让 founder 走 CPU 路径。GPU 仅在存在时作为额外约束（不超额分配）。
        batch_limit = min(self.max_projects_per_round, affordable_slots, len(proposal_batch))
        if gpu_slots > 0:
            batch_limit = min(batch_limit, gpu_slots)
        decisions: Dict[str, FundingDecision] = {}
        for idx, proposal in enumerate(proposal_batch):
            founder_id = proposal["founder_id"]
            if idx < batch_limit:
                decision = self.evaluate_initial_proposal(
                    proposal["proposal_text"],
                    proposal["profile_summary"],
                )
                # 有 GPU 就分一张；无 GPU 则空列表（CPU 路径）
                decision.gpu_ids = [gpu_pool[idx]] if idx < gpu_slots else []
                decisions[founder_id] = decision
            else:
                decisions[founder_id] = FundingDecision(
                    approved=False,
                    token_amount_usd=0.0,
                    reason=(
                        f"Investor {self.investor_id} rejected this proposal for the current round "
                        f"because all {batch_limit} budget slots were already allocated."
                    ),
                )
        return decisions


class LLMInvestor(BatchReviewInvestorMixin):
    def __init__(
        self,
        investor_id: str,
        direction: str,
        token_pool: float,
        min_approval_usd: float = 100.0,
        max_approval_usd: float = 1000.0,
        min_extra_usd: float = 50.0,
        max_extra_usd: float = 500.0,
        model: str = "qwen3.6-plus",
        max_projects_per_round: int = 3,
        recorder=None,
    ):
        self.investor_id = investor_id
        self.direction = direction
        self.token_pool = token_pool
        self.min_approval_usd = min_approval_usd
        self.max_approval_usd = max_approval_usd
        self.min_extra_usd = min_extra_usd
        self.max_extra_usd = max_extra_usd
        self.model = model
        self.max_projects_per_round = max_projects_per_round
        self.recorder = recorder
        self._init_batch_state()

    def evaluate_initial_proposal(
        self, proposal_text: str, founder_profile: dict
    ) -> FundingDecision:
        from ai_scientist.llm import (
            create_client,
            extract_json_between_markers,
            get_response_from_llm,
        )
        import json
        import re

        if self.token_pool < self.min_approval_usd:
            return FundingDecision(
                approved=False,
                token_amount_usd=0,
                reason=f"Investor {self.investor_id} 资金池不足（剩余 ${self.token_pool:.0f}）。",
            )

        prompt = f"""You are a research funding investor.

Your direction:
{self.direction}

Available budget for this decision: ${self.token_pool:.0f} USD
Approval amount range: ${self.min_approval_usd:.0f} to ${self.max_approval_usd:.0f}

Applicant track record:
{json.dumps(founder_profile, indent=2, ensure_ascii=False)}

Proposal:
---
{proposal_text}
---

Output JSON with:
- "approved": true/false
- "amount_usd": float in range [{self.min_approval_usd}, {self.max_approval_usd}] if approved, else 0
- "reason": 2-3 sentences
"""
        try:
            client, client_model = create_client(self.model)
            response_text, _ = get_response_from_llm(
                prompt=prompt,
                client=client,
                model=client_model,
                system_message="You are an investor. Output only valid JSON.",
                msg_history=[],
            )
            result = extract_json_between_markers(response_text)
            if not result:
                text = response_text.strip()
                if text.startswith("```"):
                    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
                    if match:
                        result = json.loads(match.group(1))
            if not result:
                return FundingDecision(
                    approved=False,
                    token_amount_usd=0,
                    reason="LLM response could not be parsed",
                )
            if self.recorder is not None:
                self.recorder.log_llm(
                    founder_profile.get("founder_id", "unknown"),
                    "investor_initial_review",
                    {
                        "investor_id": self.investor_id,
                        "prompt": prompt,
                        "response_text": response_text,
                        "parsed_result": result,
                    },
                )

            approved = _parse_bool(result.get("approved", False))
            amount = float(result.get("amount_usd", 0))
            reason = str(result.get("reason", ""))
            amount = max(0, min(amount, self.max_approval_usd))
            if approved and amount < self.min_approval_usd:
                amount = self.min_approval_usd
            if approved and amount > self.token_pool:
                amount = self.token_pool
            if not approved:
                amount = 0.0
            if approved:
                self.token_pool -= amount
            return FundingDecision(
                approved=approved,
                token_amount_usd=amount,
                reason=reason,
            )
        except Exception as e:
            if self.recorder is not None:
                self.recorder.log_llm(
                    founder_profile.get("founder_id", "unknown"),
                    "investor_initial_review",
                    {
                        "investor_id": self.investor_id,
                        "prompt": prompt,
                        "error": str(e),
                    },
                )
            logger.error(f"[{self.investor_id}] LLM 评审异常: {e}")
            return FundingDecision(
                approved=False,
                token_amount_usd=0,
                reason=f"LLM evaluation error: {e}",
            )

    def evaluate_extra_funding(
        self, progress_summary: dict, founder_profile: dict
    ) -> FundingDecision:
        from ai_scientist.llm import (
            create_client,
            extract_json_between_markers,
            get_response_from_llm,
        )
        import json
        import re

        if self.token_pool < self.min_extra_usd:
            return FundingDecision(
                approved=False,
                token_amount_usd=0,
                reason=f"Investor {self.investor_id} 资金池不足。",
            )

        prompt = f"""You are a research funding investor reviewing a request for extra funding mid-experiment.

Your direction: {self.direction}
Available extra budget: ${self.token_pool:.0f}
Extra amount range: ${self.min_extra_usd:.0f} to ${self.max_extra_usd:.0f}

Track record:
{json.dumps(founder_profile, indent=2, ensure_ascii=False)}

Current progress:
{json.dumps(progress_summary, indent=2, ensure_ascii=False)}

Output JSON:
- "approved": true/false
- "amount_usd": float in range [{self.min_extra_usd}, {self.max_extra_usd}] if approved, else 0
- "reason": 2-3 sentences
"""
        try:
            client, client_model = create_client(self.model)
            response_text, _ = get_response_from_llm(
                prompt=prompt,
                client=client,
                model=client_model,
                system_message="You are a strict but fair investor. Output only valid JSON.",
                msg_history=[],
            )
            result = extract_json_between_markers(response_text)
            if not result:
                text = response_text.strip()
                if text.startswith("```"):
                    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
                    if match:
                        result = json.loads(match.group(1))
            if not result:
                return FundingDecision(
                    approved=False,
                    token_amount_usd=0,
                    reason="LLM response could not be parsed",
                )
            if self.recorder is not None:
                self.recorder.log_llm(
                    founder_profile.get("founder_id", "unknown"),
                    "investor_extra_review",
                    {
                        "investor_id": self.investor_id,
                        "prompt": prompt,
                        "response_text": response_text,
                        "parsed_result": result,
                    },
                )

            approved = _parse_bool(result.get("approved", False))
            amount = float(result.get("amount_usd", 0))
            reason = str(result.get("reason", ""))
            amount = max(0, min(amount, self.max_extra_usd))
            if approved and amount < self.min_extra_usd:
                amount = self.min_extra_usd
            if approved and amount > self.token_pool:
                amount = self.token_pool
            if not approved:
                amount = 0.0
            if approved:
                self.token_pool -= amount
            return FundingDecision(
                approved=approved,
                token_amount_usd=amount,
                reason=reason,
            )
        except Exception as e:
            if self.recorder is not None:
                self.recorder.log_llm(
                    founder_profile.get("founder_id", "unknown"),
                    "investor_extra_review",
                    {
                        "investor_id": self.investor_id,
                        "prompt": prompt,
                        "error": str(e),
                    },
                )
            logger.error(f"[{self.investor_id}] LLM 追加评审异常: {e}")
            return FundingDecision(
                approved=False,
                token_amount_usd=0,
                reason=f"LLM evaluation error: {e}",
            )


class RuleBasedInvestor(BatchReviewInvestorMixin):
    def __init__(
        self,
        investor_id: str = "rule_based",
        direction: str = "General ML research",
        token_pool: float = 1_000_000.0,
        founder_rules: Optional[dict] = None,
        default_initial_amount_usd: float = 20.0,
        default_extra_amount_usd: float = 0.0,
        max_projects_per_round: int = 3,
    ):
        self.investor_id = investor_id
        self.direction = direction
        self.token_pool = token_pool
        self.founder_rules = founder_rules or {}
        self.default_initial_amount_usd = default_initial_amount_usd
        self.default_extra_amount_usd = default_extra_amount_usd
        self._extra_request_counts = {}
        self.max_projects_per_round = max_projects_per_round
        self._init_batch_state()

    def _founder_rule(self, founder_profile: dict) -> dict:
        founder_id = founder_profile.get("founder_id", "")
        return self.founder_rules.get(founder_id, {})

    def evaluate_initial_proposal(
        self, proposal_text: str, founder_profile: dict
    ) -> FundingDecision:
        founder_id = founder_profile.get("founder_id", "unknown")
        rule = self._founder_rule(founder_profile)
        amount = float(
            rule.get("initial_amount_usd", self.default_initial_amount_usd)
        )
        amount = max(0.0, min(amount, self.token_pool))
        approved = amount > 0
        if approved:
            self.token_pool -= amount
        return FundingDecision(
            approved=approved,
            token_amount_usd=amount if approved else 0.0,
            reason=(
                f"RuleBasedInvestor initial decision for {founder_id}: "
                f"{'approved' if approved else 'rejected'} amount=${amount:.2f}"
            ),
        )

    def evaluate_extra_funding(
        self, progress_summary: dict, founder_profile: dict
    ) -> FundingDecision:
        founder_id = founder_profile.get("founder_id", "unknown")
        rule = self._founder_rule(founder_profile)
        decisions = list(rule.get("extra_decisions", []))
        request_idx = self._extra_request_counts.get(founder_id, 0)
        self._extra_request_counts[founder_id] = request_idx + 1

        if request_idx < len(decisions):
            amount = float(decisions[request_idx])
        else:
            amount = float(
                rule.get("default_extra_amount_usd", self.default_extra_amount_usd)
            )

        amount = max(0.0, min(amount, self.token_pool))
        approved = amount > 0
        if approved:
            self.token_pool -= amount
        return FundingDecision(
            approved=approved,
            token_amount_usd=amount if approved else 0.0,
            reason=(
                f"RuleBasedInvestor extra decision for {founder_id} request#{request_idx + 1}: "
                f"{'approved' if approved else 'rejected'} amount=${amount:.2f}"
            ),
        )

    def evaluate_initial_batch(
        self, proposal_batch: List[Dict[str, Any]]
    ) -> Dict[str, FundingDecision]:
        ranked = []
        for proposal in proposal_batch:
            founder_id = proposal["founder_id"]
            rule = self.founder_rules.get(founder_id, {})
            score = float(rule.get("batch_score", 0.0))
            ranked.append((score, founder_id, proposal))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        decisions: Dict[str, FundingDecision] = {}
        approved_slots = 0
        gpu_slots = len(getattr(self, "_gpu_ids", []))
        batch_limit = min(self.max_projects_per_round, gpu_slots, len(ranked))
        for _, founder_id, proposal in ranked:
            if approved_slots >= batch_limit:
                decisions[founder_id] = FundingDecision(
                    approved=False,
                    token_amount_usd=0.0,
                    reason=(
                        f"RuleBasedInvestor reached the per-round cap "
                        f"of {batch_limit} proposals."
                    ),
                )
                continue
            decision = self.evaluate_initial_proposal(
                proposal["proposal_text"],
                proposal["profile_summary"],
            )
            if decision.approved:
                gpu_ids = getattr(self, "_gpu_ids", [])
                if approved_slots < len(gpu_ids):
                    decision.gpu_ids = [gpu_ids[approved_slots]]
                else:
                    decision = FundingDecision(
                        approved=False,
                        token_amount_usd=0.0,
                        reason="RuleBasedInvestor ran out of GPU slots for this round.",
                    )
            decisions[founder_id] = decision
            if decision.approved:
                approved_slots += 1
        return decisions


class FundRoleInvestor(BatchReviewInvestorMixin):
    """
    Simple fund-style investor:
    - token pool is initialized once
    - every funding round selects at most k proposals
    - approved proposals receive a fixed tranche
    """

    def __init__(
        self,
        investor_id: str,
        direction: str,
        token_pool: float,
        approval_amount_usd: float = 100.0,
        extra_amount_usd: float = 50.0,
        model: str = "qwen3.6-plus",
        max_projects_per_round: int = 3,
        recorder=None,
    ):
        self.investor_id = investor_id
        self.direction = direction
        self.token_pool = token_pool
        self.approval_amount_usd = approval_amount_usd
        self.extra_amount_usd = extra_amount_usd
        self.model = model
        self.max_projects_per_round = max_projects_per_round
        self.recorder = recorder
        self._init_batch_state()

    def evaluate_initial_batch(
        self, proposal_batch: List[Dict[str, Any]]
    ) -> Dict[str, FundingDecision]:
        from ai_scientist.llm import (
            create_client,
            extract_json_between_markers,
            get_response_from_llm,
        )
        import re

        if not proposal_batch:
            return {}

        valid_gpu_pool = list(getattr(self, "_gpu_ids", []))
        affordable_slots = int(self.token_pool // self.approval_amount_usd)
        gpu_limited_slots = len(valid_gpu_pool)
        # CPU fallback: 无 GPU（gpu_limited_slots==0）时不让 GPU 成为硬上限，
        # 项目走 CPU 路径；GPU 仅在存在时作为额外约束。
        max_select = max(
            0,
            min(
                self.max_projects_per_round,
                affordable_slots,
                len(proposal_batch),
            ),
        )
        if gpu_limited_slots > 0:
            max_select = min(max_select, gpu_limited_slots)
        cpu_mode = gpu_limited_slots == 0
        if max_select <= 0:
            return {
                proposal["founder_id"]: FundingDecision(
                    approved=False,
                    token_amount_usd=0.0,
                    reason=(
                        f"Investor {self.investor_id} cannot open new grants this round "
                        f"because budget capacity is exhausted."
                    ),
                )
                for proposal in proposal_batch
            }

        prompt = f"""You are managing a research fund.

Role:
- You are not a startup investor. You are a fund manager allocating limited research grant budget.
- Your goal is to choose the strongest proposals for this round.
- You may approve at most {max_select} proposals this round.
- Your total remaining budget is ${self.token_pool:.2f}.
- Each approved proposal receives a fixed tranche of ${self.approval_amount_usd:.2f}.
- Your preferred direction is: {self.direction}
- This round is an exploratory micro-grant program for system-scale research testing.
- If a proposal is coherent, feasible, and directionally aligned, you should usually approve it while slots and GPUs remain.
- Reserve rejection for proposals that are clearly weak, incoherent, or badly misaligned.

Below are the proposals for this funding round:
{json.dumps(proposal_batch, indent=2, ensure_ascii=False)}

Available GPUs owned by your fund for approved projects this round:
{getattr(self, "_gpu_ids", [])}

Return JSON with:
- "selected_founder_ids": list of founder ids, length at most {max_select}
- "gpu_allocations": object mapping selected founder_id -> list of distinct GPU ids drawn from the owned GPU list above
- "reasoning": short paragraph about this round's selection standard
- "per_founder_reason": object mapping founder_id to a short reason

Output only JSON."""
        try:
            client, client_model = create_client(self.model)
            response_text, _ = get_response_from_llm(
                prompt=prompt,
                client=client,
                model=client_model,
                system_message="You are a disciplined research fund manager. Output only valid JSON.",
                msg_history=[],
            )
            result = extract_json_between_markers(response_text)
            if not result:
                text = response_text.strip()
                if text.startswith("```"):
                    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
                    if match:
                        result = json.loads(match.group(1))
            if not result:
                raise ValueError("LLM response could not be parsed")
            if self.recorder is not None:
                self.recorder.log_llm(
                    self.investor_id,
                    "investor_batch_review",
                    {
                        "prompt": prompt,
                        "response_text": response_text,
                        "parsed_result": result,
                        "proposal_batch": proposal_batch,
                    },
                )
        except Exception as e:
            if self.recorder is not None:
                self.recorder.log_llm(
                    self.investor_id,
                    "investor_batch_review",
                    {
                        "prompt": prompt,
                        "error": str(e),
                        "proposal_batch": proposal_batch,
                    },
                )
            logger.error(f"[{self.investor_id}] batch evaluation failed: {e}")
            ordered = proposal_batch[:max_select]
            selected_ids = [proposal["founder_id"] for proposal in ordered]
            result = {
                "selected_founder_ids": selected_ids,
                "reasoning": f"Fallback selection due to investor LLM error: {e}",
                "per_founder_reason": {
                    proposal["founder_id"]: "Fallback top-of-queue selection."
                    for proposal in proposal_batch
                },
            }

        selected_ids = []
        for founder_id in result.get("selected_founder_ids", []):
            if founder_id not in selected_ids and any(
                proposal["founder_id"] == founder_id for proposal in proposal_batch
            ):
                selected_ids.append(founder_id)
            if len(selected_ids) >= max_select:
                break

        per_reason = result.get("per_founder_reason", {}) or {}
        raw_allocations = result.get("gpu_allocations", {}) or {}
        used_gpus = set()
        cleaned_allocations: Dict[str, List[int]] = {}
        for founder_id in selected_ids:
            proposed = raw_allocations.get(founder_id, [])
            cleaned = []
            if isinstance(proposed, list):
                for gpu_id in proposed:
                    try:
                        gpu_int = int(gpu_id)
                    except Exception:
                        continue
                    if gpu_int in valid_gpu_pool and gpu_int not in used_gpus:
                        cleaned.append(gpu_int)
                        used_gpus.add(gpu_int)
            cleaned_allocations[founder_id] = cleaned
        remaining_gpus = [gpu for gpu in valid_gpu_pool if gpu not in used_gpus]
        for founder_id in selected_ids:
            if cleaned_allocations[founder_id]:
                continue
            if remaining_gpus:
                cleaned_allocations[founder_id] = [remaining_gpus.pop(0)]

        decisions: Dict[str, FundingDecision] = {}
        for proposal in proposal_batch:
            founder_id = proposal["founder_id"]
            has_gpu_allocation = bool(cleaned_allocations.get(founder_id, []))
            # CPU 模式下不要求 GPU 分配；有 GPU 模式下仍要求拿到 GPU 才批准
            gpu_ok = has_gpu_allocation or cpu_mode
            approved = (
                founder_id in selected_ids
                and gpu_ok
                and self.token_pool >= self.approval_amount_usd
            )
            reason = per_reason.get(founder_id) or result.get("reasoning", "")
            if approved:
                self.token_pool -= self.approval_amount_usd
                decisions[founder_id] = FundingDecision(
                    approved=True,
                    token_amount_usd=self.approval_amount_usd,
                    reason=f"Fund selection approved. {reason}",
                    gpu_ids=cleaned_allocations.get(founder_id, []),
                )
            else:
                if founder_id in selected_ids and not gpu_ok:
                    reason = (
                        reason + " "
                        if reason
                        else ""
                    ) + "Rejected because no unallocated GPU tranche remained this round."
                decisions[founder_id] = FundingDecision(
                    approved=False,
                    token_amount_usd=0.0,
                    reason=f"Fund selection rejected this round. {reason}",
                )
        return decisions

    def evaluate_initial_proposal(
        self, proposal_text: str, founder_profile: dict
    ) -> FundingDecision:
        batch = [
            {
                "founder_id": founder_profile.get("founder_id", "unknown"),
                "proposal_text": proposal_text,
                "profile_summary": founder_profile,
                "idea_title": founder_profile.get("current_idea", "Untitled"),
            }
        ]
        return self.evaluate_initial_batch(batch)[batch[0]["founder_id"]]

    def evaluate_extra_funding(
        self, progress_summary: dict, founder_profile: dict
    ) -> FundingDecision:
        from ai_scientist.llm import (
            create_client,
            extract_json_between_markers,
            get_response_from_llm,
        )
        import re

        if self.token_pool < self.extra_amount_usd:
            return FundingDecision(
                approved=False,
                token_amount_usd=0.0,
                reason=f"Fund {self.investor_id} has no budget left for extra funding.",
            )

        prompt = f"""You are managing a research fund.

The founder below asks for extra grant money mid-project.
- Remaining budget: ${self.token_pool:.2f}
- If approved, grant exactly ${self.extra_amount_usd:.2f}
- Direction preference: {self.direction}

Founder profile:
{json.dumps(founder_profile, indent=2, ensure_ascii=False)}

Current progress:
{json.dumps(progress_summary, indent=2, ensure_ascii=False)}

Return JSON with:
- "approved": true or false
- "reason": short justification

Output only JSON."""
        try:
            client, client_model = create_client(self.model)
            response_text, _ = get_response_from_llm(
                prompt=prompt,
                client=client,
                model=client_model,
                system_message="You are a conservative research fund manager. Output only valid JSON.",
                msg_history=[],
            )
            result = extract_json_between_markers(response_text)
            if not result:
                text = response_text.strip()
                if text.startswith("```"):
                    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
                    if match:
                        result = json.loads(match.group(1))
            if not result:
                raise ValueError("LLM response could not be parsed")
            if self.recorder is not None:
                self.recorder.log_llm(
                    founder_profile.get("founder_id", "unknown"),
                    "investor_extra_review",
                    {
                        "investor_id": self.investor_id,
                        "prompt": prompt,
                        "response_text": response_text,
                        "parsed_result": result,
                    },
                )
            approved = _parse_bool(result.get("approved", False))
            reason = str(result.get("reason", ""))
        except Exception as e:
            if self.recorder is not None:
                self.recorder.log_llm(
                    founder_profile.get("founder_id", "unknown"),
                    "investor_extra_review",
                    {
                        "investor_id": self.investor_id,
                        "prompt": prompt,
                        "error": str(e),
                    },
                )
            logger.error(f"[{self.investor_id}] extra funding evaluation failed: {e}")
            approved = False
            reason = f"Investor LLM error: {e}"

        if not approved:
            return FundingDecision(approved=False, token_amount_usd=0.0, reason=reason)
        self.token_pool -= self.extra_amount_usd
        return FundingDecision(
            approved=True,
            token_amount_usd=self.extra_amount_usd,
            reason=reason or "Extra tranche approved by the fund.",
        )
