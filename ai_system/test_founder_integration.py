"""
Focused founder integration tests for the shell-level lifecycle.

Run with:
    python -m ai_system.test_founder_integration
"""

import json
import os
import shutil
import tempfile

from ai_system.founder_shell import FounderShell, FounderStatus
from ai_system.investor import FundingDecision, RuleBasedInvestor
from ai_system.literature_db import get_literature_db, reset_literature_db
from ai_system.orchestrator import MessageDrivenOrchestrator
from ai_system.peer_review import ReviewResult
from ai_system.reputation import FounderProfile
from ai_system.resource_scheduler import ResourceScheduler
from ai_system.skill_manager import SkillManager
from ai_system.token_budget import TokenBudget, deduct_manual


class FixedPeerReview:
    def __init__(self, accepted: bool):
        self.accepted = accepted

    def evaluate(self, paper_title: str, paper_text: str, author_id: str) -> ReviewResult:
        return ReviewResult(
            accepted=self.accepted,
            overall_score=8.0 if self.accepted else 3.0,
            reviews=[
                {
                    "reviewer": "fixed_reviewer",
                    "score": 8.0 if self.accepted else 3.0,
                    "summary": "Deterministic review for integration testing.",
                }
            ],
            meta_review="deterministic",
        )


def _clean_dir(path: str):
    if os.path.exists(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)


def _make_shell(
    founder_id: str,
    investor,
    scheduler,
    skill_dir: str,
    profile_dir: str,
    initial_budget: float,
    experiment_runner,
    peer_review,
    writeup_runner=None,
):
    skill_mgr = SkillManager(founder_id, store_dir=skill_dir)
    profile = FounderProfile(founder_id, store_dir=profile_dir)
    budget = TokenBudget(initial_usd=initial_budget)

    def idea_generator(skill_text: str, model: str) -> dict:
        return {
            "Name": f"{founder_id}_idea",
            "Title": f"{founder_id} Simple Idea",
            "Short Hypothesis": "A tiny hypothesis for integration testing.",
            "Related Work": "Minimal related work.",
            "Abstract": "A tiny abstract for integration testing.",
            "Experiments": "Run a tiny mock experiment.",
            "Risk Factors and Limitations": "Low budget and short execution.",
        }

    def default_writeup_runner(experiment_result: dict, skill_text: str, model: str) -> dict:
        return {
            "title": experiment_result["idea_title"],
            "text": f"Paper for {founder_id}. GPU snapshot={experiment_result.get('gpu_snapshot')}",
            "metric": experiment_result.get("best_metric", 0.0),
        }

    return FounderShell(
        founder_id=founder_id,
        skill_manager=skill_mgr,
        profile=profile,
        token_budget=budget,
        investors=[investor],
        literature_db=get_literature_db(),
        peer_review=peer_review,
        idea_generator=idea_generator,
        experiment_runner=experiment_runner,
        writeup_runner=writeup_runner or default_writeup_runner,
        proposal_builder=lambda idea, founder_id, founder_profile_summary, investors, model: type(
            "Proposal",
            (),
            {
                "proposal_text": f"proposal for {founder_id}",
                "selected_investor_id": investor.investor_id,
                "selection_reason": "deterministic",
            },
        )(),
        model="qwen-mock",
        skill_store_dir=skill_dir,
        profile_store_dir=profile_dir,
        resource_scheduler=scheduler,
        gpus_per_funding=1,
        state_store_dir=os.path.join(os.path.dirname(skill_dir), "runtime_state"),
    )


def test_scheduler_allocates_two_distinct_gpus():
    scheduler = ResourceScheduler(physical_gpu_ids=[0, 1])
    scheduler.assign_investor_pool("inv", 2)
    gpu_a = scheduler.allocate_to_founder("inv", "founder_1", 1)
    gpu_b = scheduler.allocate_to_founder("inv", "founder_2", 1)
    assert gpu_a == [0], gpu_a
    assert gpu_b == [1], gpu_b
    scheduler.release_from_founder("inv", "founder_1")
    scheduler.release_from_founder("inv", "founder_2")


def test_founder_extra_funding_and_skill_update():
    root = tempfile.mkdtemp(prefix="founder_integration_")
    try:
        reset_literature_db()
        skill_dir = os.path.join(root, "skills")
        profile_dir = os.path.join(root, "profiles")
        _clean_dir(skill_dir)
        _clean_dir(profile_dir)

        investor = RuleBasedInvestor(
            investor_id="rule_inv",
            token_pool=1000.0,
            founder_rules={
                "founder_1": {
                    "initial_amount_usd": 20.0,
                    "extra_decisions": [15.0],
                }
            },
        )
        investor._gpu_ids = [0, 1]
        scheduler = ResourceScheduler(physical_gpu_ids=[0, 1])
        scheduler.assign_investor_pool("rule_inv", 2)

        state = {"calls": 0, "gpu_snapshots": []}

        def experiment_runner(idea: dict, gpu_ids: list, model: str) -> dict:
            state["calls"] += 1
            state["gpu_snapshots"].append(list(gpu_ids))
            assert os.environ.get("CUDA_VISIBLE_DEVICES") == "0", os.environ.get(
                "CUDA_VISIBLE_DEVICES"
            )
            assert "mock-update" in os.environ.get("AI_SCIENTIST_SKILL", "") or os.environ.get(
                "AI_SCIENTIST_SKILL", ""
            )
            if state["calls"] == 1:
                deduct_manual(cost_usd=26.0, model=model)
            deduct_manual(cost_usd=5.0, model=model)
            return {
                "idea_title": idea["Title"],
                "best_metric": 0.81,
                "status": "completed",
                "gpu_snapshot": list(gpu_ids),
            }

        shell = _make_shell(
            founder_id="founder_1",
            investor=investor,
            scheduler=scheduler,
            skill_dir=skill_dir,
            profile_dir=profile_dir,
            initial_budget=5.0,
            experiment_runner=experiment_runner,
            peer_review=FixedPeerReview(accepted=True),
        )

        ok = shell.run_cycle()
        skill_text = shell.skill_manager.load()
        profile_summary = shell.profile.summary()

        assert ok is True
        assert shell.status == FounderStatus.IDLE
        assert state["calls"] == 2, state
        assert state["gpu_snapshots"] == [[0], [0]], state["gpu_snapshots"]
        assert profile_summary["total_papers"] == 1
        assert profile_summary["accepted_papers"] == 1
        assert "Funding proposal approved" in skill_text
        assert "Extra funding approved" in skill_text
        assert "accepted after peer review" in skill_text
        assert shell.resume_token is None
        assert scheduler.status()["pools"]["rule_inv"]["allocations"] == {}

        with open(os.path.join(profile_dir, "founder_1.json"), "r") as f:
            history = json.load(f)["history"]
        assert any(item["event_type"] == "experiment_suspended" for item in history)
        assert any(item["event_type"] == "cycle_resumed" for item in history)
        assert any(item["event_type"] == "extra_funding_requested" and item["decision"] == "approved" for item in history)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_founder_rejected_extra_funding_dies():
    root = tempfile.mkdtemp(prefix="founder_integration_")
    try:
        reset_literature_db()
        skill_dir = os.path.join(root, "skills")
        profile_dir = os.path.join(root, "profiles")
        _clean_dir(skill_dir)
        _clean_dir(profile_dir)

        investor = RuleBasedInvestor(
            investor_id="rule_inv",
            token_pool=1000.0,
            founder_rules={
                "founder_2": {
                    "initial_amount_usd": 10.0,
                    "extra_decisions": [0.0],
                }
            },
        )
        investor._gpu_ids = [0, 1]
        scheduler = ResourceScheduler(physical_gpu_ids=[0, 1])
        scheduler.assign_investor_pool("rule_inv", 2)

        def experiment_runner(idea: dict, gpu_ids: list, model: str) -> dict:
            assert os.environ.get("CUDA_VISIBLE_DEVICES") == "0", os.environ.get(
                "CUDA_VISIBLE_DEVICES"
            )
            deduct_manual(cost_usd=20.0, model=model)
            return {
                "idea_title": idea["Title"],
                "best_metric": 0.2,
                "status": "completed",
            }

        shell = _make_shell(
            founder_id="founder_2",
            investor=investor,
            scheduler=scheduler,
            skill_dir=skill_dir,
            profile_dir=profile_dir,
            initial_budget=5.0,
            experiment_runner=experiment_runner,
            peer_review=FixedPeerReview(accepted=False),
        )

        ok = shell.run_cycle()
        assert ok is False
        assert shell.status == FounderStatus.DEAD
        assert scheduler.status()["pools"]["rule_inv"]["allocations"] == {}

        with open(os.path.join(profile_dir, "founder_2.json"), "r") as f:
            history = json.load(f)["history"]
        assert any(item["event_type"] == "extra_funding_requested" and item["decision"] == "rejected" for item in history)
        assert any(item["event_type"] == "experiment_suspended" for item in history)
        assert any(item["event_type"] == "bankruptcy" for item in history)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_founder_resume_from_writeup_budget_exhaustion():
    root = tempfile.mkdtemp(prefix="founder_integration_")
    try:
        reset_literature_db()
        skill_dir = os.path.join(root, "skills")
        profile_dir = os.path.join(root, "profiles")
        _clean_dir(skill_dir)
        _clean_dir(profile_dir)

        investor = RuleBasedInvestor(
            investor_id="rule_inv",
            token_pool=1000.0,
            founder_rules={
                "founder_3": {
                    "initial_amount_usd": 15.0,
                    "extra_decisions": [10.0],
                }
            },
        )
        investor._gpu_ids = [0]
        scheduler = ResourceScheduler(physical_gpu_ids=[0])
        scheduler.assign_investor_pool("rule_inv", 1)

        state = {"writeup_calls": 0}
        budget_holder = {}

        def experiment_runner(idea: dict, gpu_ids: list, model: str, resume: bool = False, checkpoint=None) -> dict:
            assert gpu_ids == [0]
            return {
                "idea_title": idea["Title"],
                "best_metric": 0.77,
                "status": "completed",
                "resumed": resume,
            }

        def writeup_runner(experiment_result: dict, skill_text: str, model: str) -> dict:
            state["writeup_calls"] += 1
            if state["writeup_calls"] == 1:
                budget_holder["budget"].deduct(21.0)
            return {
                "title": experiment_result["idea_title"],
                "text": f"Recovered writeup call={state['writeup_calls']}",
            }

        shell = _make_shell(
            founder_id="founder_3",
            investor=investor,
            scheduler=scheduler,
            skill_dir=skill_dir,
            profile_dir=profile_dir,
            initial_budget=5.0,
            experiment_runner=experiment_runner,
            writeup_runner=writeup_runner,
            peer_review=FixedPeerReview(accepted=True),
        )
        budget_holder["budget"] = shell.token_budget

        ok = shell.run_cycle()
        assert ok is True
        assert shell.status == FounderStatus.IDLE
        assert state["writeup_calls"] == 2
        assert scheduler.status()["pools"]["rule_inv"]["allocations"] == {}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_literature_db_search_includes_internal_statuses():
    reset_literature_db()
    db = get_literature_db()
    db.add_paper(
        title="Internal Paper A",
        abstract="A published internal paper.",
        authors=["founder_1"],
        status="published",
        founder_id="founder_1",
        paper_text="Published internal results.",
    )
    db.add_paper(
        title="Internal Paper B",
        abstract="A paper still under review.",
        authors=["founder_2"],
        status="under_review",
        founder_id="founder_2",
        paper_text="Under review internal results.",
    )
    db.add_paper(
        title="Internal Paper C",
        abstract="A rejected but searchable paper.",
        authors=["founder_3"],
        status="rejected",
        founder_id="founder_3",
        paper_text="Rejected internal results.",
    )
    results = db.search("internal")
    statuses = {item["status"] for item in results}
    assert {"published", "under_review", "rejected"} <= statuses


def test_message_driven_orchestrator_smoke():
    class DeterministicSociety:
        def register_founders(self, founders):
            self.founders = founders

        def evaluate(self, paper_title, paper_text, author_id, paper_pdf_path=None):
            return ReviewResult(
                accepted=True,
                overall_score=8.0,
                reviews=[
                    {"reviewer": "founder_2", "score": 8.0, "summary": "Looks good."},
                    {"reviewer": "founder_3", "score": 8.0, "summary": "Looks good."},
                    {"reviewer": "founder_2_dup", "score": 8.0, "summary": "Looks good."},
                ],
                meta_review="accepted",
            )

    reset_literature_db()
    orch = MessageDrivenOrchestrator(
        num_founders=3,
        num_investors=1,
        max_cycles_per_founder=1,
        use_mock_agent=True,
        use_debug_investor_selection=True,
        use_llm_investor=False,
        use_resource_scheduler=False,
        physical_gpu_count=0,
        model="qwen-mock",
        initial_review_delay_sec=0,
        # mock 实验消耗约 $30/cycle（6 calls × $5）。给足初始 approval，
        # 让 founder 能正常完成 cycle 而非预算耗尽破产。
        approval_amount_usd=50.0,
        extra_amount_usd=30.0,
        investor_total_budget_usd=500.0,
        global_budget_cap_usd=500.0,
    )
    orch.peer_review = DeterministicSociety()
    orch.peer_review.register_founders(orch.shells)
    for shell in orch.shells:
        shell.peer_review = orch.peer_review
    orch.run()
    assert all(shell.cycle_count == 1 for shell in orch.shells)
    assert all(shell.status == FounderStatus.IDLE for shell in orch.shells)
    assert all(shell.profile.summary()["total_papers"] >= 1 for shell in orch.shells)


def test_rule_investor_batch_cap_and_budget():
    investor = RuleBasedInvestor(
        investor_id="rule_inv",
        token_pool=100.0,
        default_initial_amount_usd=20.0,
        max_projects_per_round=2,
        founder_rules={
            "founder_1": {"batch_score": 10},
            "founder_2": {"batch_score": 9},
            "founder_3": {"batch_score": 1},
        },
    )
    investor._gpu_ids = [0, 1]
    batch = [
        {
            "founder_id": "founder_1",
            "proposal_text": "p1",
            "profile_summary": {"founder_id": "founder_1"},
        },
        {
            "founder_id": "founder_2",
            "proposal_text": "p2",
            "profile_summary": {"founder_id": "founder_2"},
        },
        {
            "founder_id": "founder_3",
            "proposal_text": "p3",
            "profile_summary": {"founder_id": "founder_3"},
        },
    ]
    decisions = investor.evaluate_initial_batch(batch)
    assert decisions["founder_1"].approved is True
    assert decisions["founder_2"].approved is True
    assert decisions["founder_3"].approved is False
    assert investor.token_pool == 60.0


def main():
    # 测试隔离：把文献库指向临时文件，避免污染真实运行的
    # ai_system/literature_store/db.json（测试会写入大量 fixture 假论文）。
    _tmp_db = tempfile.mkdtemp(prefix="test_litdb_")
    os.environ["LITERATURE_DB_PATH"] = os.path.join(_tmp_db, "db.json")
    tests = [
        test_scheduler_allocates_two_distinct_gpus,
        test_founder_extra_funding_and_skill_update,
        test_founder_rejected_extra_funding_dies,
        test_founder_resume_from_writeup_budget_exhaustion,
        test_literature_db_search_includes_internal_statuses,
        test_message_driven_orchestrator_smoke,
        test_rule_investor_batch_cap_and_budget,
    ]
    try:
        for test in tests:
            print(f"[RUN] {test.__name__}")
            test()
            print(f"[OK]  {test.__name__}")
        print("All founder integration tests passed.")
    finally:
        shutil.rmtree(_tmp_db, ignore_errors=True)


if __name__ == "__main__":
    main()
