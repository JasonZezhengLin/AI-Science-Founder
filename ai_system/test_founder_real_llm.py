"""
Real-LLM founder smoke test.

This script uses:
- real AI Scientist ideation
- real LLM proposal generation
- real LLM skill updates
- actual AI Scientist experiment + full writeup pipeline
- rule-based investor decisions to deterministically trigger extra-funding and death

Run with the prepared conda env and proxy vars unset:
    source /opt/conda/etc/profile.d/conda.sh
    conda activate /home/dataset-assist-0/envs/ai_scientist
    unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
    python -m ai_system.test_founder_real_llm
"""

import json
import os
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from ai_system.env_setup import setup_openai_env
from ai_system.founder_shell import FounderShell, FounderStatus
from ai_system.investor import RuleBasedInvestor
from ai_system.literature_db import get_literature_db, reset_literature_db
from ai_system.orchestrator import (
    _make_actual_bfts_experiment_runner,
    _make_full_writeup_runner,
    _make_real_idea_generator,
)
from ai_system.proposal_builder import build_proposal
from ai_system.reputation import FounderProfile
from ai_system.resource_scheduler import ResourceScheduler
from ai_system.skill_manager import SkillManager
from ai_system.token_budget import TokenBudget, deduct_manual


MODEL = "qwen3.5-flash"
MAX_CYCLE_STEPS = 4


def _clean_dir(path: str):
    if os.path.exists(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)


def _pre_generate_idea(skill_text: str):
    generator = _make_real_idea_generator()
    last_idea = None
    for attempt in range(3):
        last_idea = generator(skill_text, MODEL)
        if last_idea is not None:
            return last_idea
        print(f" ideation retry {attempt + 1}/3 returned None")
    return last_idea


def _make_real_shell(
    founder_id: str,
    idea: dict,
    investor,
    scheduler,
    skill_dir: str,
    profile_dir: str,
    initial_budget: float,
    experiment_behavior: str,
    shared_records: dict,
    root_dir: str,
):
    skill_mgr = SkillManager(founder_id, store_dir=skill_dir)
    profile = FounderProfile(founder_id, store_dir=profile_dir)
    budget = TokenBudget(initial_usd=initial_budget)

    real_experiment_runner = _make_actual_bfts_experiment_runner(
        run_root_dir=root_dir,
        num_workers=1,
        steps=1,
        stage_max_iters=1,
        max_debug_depth=1,
        num_drafts=1,
    )
    real_writeup_runner = _make_full_writeup_runner()
    idea_lock = threading.Lock()

    def idea_generator(skill_text: str, model: str) -> dict:
        # Use a pre-generated real AI Scientist idea to keep the workflow reproducible
        with idea_lock:
            return json.loads(json.dumps(idea))

    def experiment_runner(idea_payload: dict, gpu_ids: list, model: str) -> dict:
        shared_records.setdefault(founder_id, {})
        shared_records[founder_id]["gpu_ids"] = list(gpu_ids)
        shared_records[founder_id]["cuda_visible_devices"] = os.environ.get(
            "CUDA_VISIBLE_DEVICES"
        )
        shared_records[founder_id]["skill_present"] = bool(
            os.environ.get("AI_SCIENTIST_SKILL")
        )

        # Hold the stage long enough for the second founder to allocate the other GPU.
        time.sleep(2)

        if experiment_behavior == "force_extra_then_succeed":
            count = shared_records[founder_id].get("attempt_count", 0)
            shared_records[founder_id]["attempt_count"] = count + 1
            if count == 0:
                deduct_manual(cost_usd=0.35, model=model)

        if experiment_behavior == "force_die":
            deduct_manual(cost_usd=0.35, model=model)

        result = real_experiment_runner(
            idea_payload,
            gpu_ids,
            model,
            founder_id=founder_id,
            cycle_count=1,
        )
        shared_records[founder_id]["experiment_status"] = result.get("status")
        return result

    shell = FounderShell(
        founder_id=founder_id,
        skill_manager=skill_mgr,
        profile=profile,
        token_budget=budget,
        investors=[investor],
        literature_db=get_literature_db(),
        peer_review=_AlwaysAcceptReview(),
        idea_generator=idea_generator,
        experiment_runner=experiment_runner,
        writeup_runner=real_writeup_runner,
        proposal_builder=build_proposal,
        model=MODEL,
        skill_store_dir=skill_dir,
        profile_store_dir=profile_dir,
        resource_scheduler=scheduler,
        gpus_per_funding=1,
    )
    return shell


class _AlwaysAcceptReview:
    def evaluate(self, paper_title: str, paper_text: str, author_id: str):
        from ai_system.peer_review import ReviewResult

        return ReviewResult(
            accepted=True,
            overall_score=8.0,
            reviews=[
                {
                    "reviewer": "accept_reviewer",
                    "score": 8.0,
                    "summary": "Accepted in deterministic smoke review.",
                }
            ],
            meta_review="accepted",
        )


def main():
    setup_openai_env()
    reset_literature_db()

    root = tempfile.mkdtemp(prefix="founder_real_llm_")
    skill_dir = os.path.join(root, "skills")
    profile_dir = os.path.join(root, "profiles")
    _clean_dir(skill_dir)
    _clean_dir(profile_dir)

    print("[1/5] Pre-generating two real AI Scientist ideas...")
    idea1 = _pre_generate_idea(
        "You are a rigorous researcher who prefers minimal, feasible experiments."
    )
    idea2 = _pre_generate_idea(
        "You are a careful empirical researcher who values simple ablations."
    )
    if idea1 is None or idea2 is None:
        raise RuntimeError("Real ideation failed after retries.")
    print(" founder_1 idea:", idea1["Title"])
    print(" founder_2 idea:", idea2["Title"])

    print("[2/5] Preparing one investor with two GPUs and deterministic funding rules...")
    investor = RuleBasedInvestor(
        investor_id="rule_inv",
        direction="General ML research",
        token_pool=10.0,
        founder_rules={
            "founder_1": {
                "initial_amount_usd": 0.20,
                "extra_decisions": [0.25],
            },
            "founder_2": {
                "initial_amount_usd": 0.20,
                "extra_decisions": [0.0],
            },
        },
    )
    investor._gpu_ids = [0, 1]
    scheduler = ResourceScheduler(physical_gpu_ids=[0, 1])
    scheduler.assign_investor_pool(investor.investor_id, 2)

    shared_records = {}
    founder1 = _make_real_shell(
        founder_id="founder_1",
        idea=idea1,
        investor=investor,
        scheduler=scheduler,
        skill_dir=skill_dir,
        profile_dir=profile_dir,
        initial_budget=0.05,
        experiment_behavior="force_extra_then_succeed",
        shared_records=shared_records,
        root_dir=root,
    )
    founder2 = _make_real_shell(
        founder_id="founder_2",
        idea=idea2,
        investor=investor,
        scheduler=scheduler,
        skill_dir=skill_dir,
        profile_dir=profile_dir,
        initial_budget=0.05,
        experiment_behavior="force_die",
        shared_records=shared_records,
        root_dir=root,
    )

    def _drive_shell(shell):
        last_result = False
        for _ in range(MAX_CYCLE_STEPS):
            last_result = shell.run_cycle()
            if shell.status in (FounderStatus.IDLE, FounderStatus.DEAD):
                return last_result
        raise RuntimeError(f"{shell.founder_id} did not settle within {MAX_CYCLE_STEPS} steps")

    print("[3/5] Running two founders concurrently...")
    with ThreadPoolExecutor(max_workers=2) as pool:
        future1 = pool.submit(_drive_shell, founder1)
        future2 = pool.submit(_drive_shell, founder2)
        result1 = future1.result()
        result2 = future2.result()

    print("[4/5] Validating outcomes...")
    assert result1 is True
    assert founder1.status == FounderStatus.IDLE
    assert shared_records["founder_1"]["gpu_ids"] == [0], shared_records
    assert shared_records["founder_2"]["gpu_ids"] == [1], shared_records
    assert shared_records["founder_1"]["cuda_visible_devices"] == "0", shared_records
    assert shared_records["founder_2"]["cuda_visible_devices"] == "1", shared_records
    assert shared_records["founder_1"]["skill_present"] is True
    assert shared_records["founder_2"]["skill_present"] is True

    assert result2 is False
    assert founder2.status == FounderStatus.DEAD

    founder1_skill = founder1.skill_manager.load()
    founder2_profile = founder2.profile.summary()

    assert founder1_skill != founder1.skill_manager.initial_skill()
    assert founder1.profile.summary()["total_papers"] == 1
    assert founder1.profile.summary()["accepted_papers"] == 1
    assert founder2_profile["history_length"] >= 2

    with open(os.path.join(profile_dir, "founder_2.json"), "r") as f:
        founder2_history = json.load(f)["history"]
    assert any(
        item["event_type"] == "extra_funding_requested"
        and item["decision"] == "rejected"
        for item in founder2_history
    )
    assert any(item["event_type"] == "bankruptcy" for item in founder2_history)

    print("[5/5] Summary")
    print(" founder_1 status:", founder1.status)
    print(" founder_1 remaining budget:", founder1.token_budget.summary())
    print(" founder_2 status:", founder2.status)
    print(" founder_2 remaining budget:", founder2.token_budget.summary())
    print(" GPU assignment snapshots:", shared_records)
    print(" Literature DB stats:", get_literature_db().stats())
    print("Real founder smoke test passed.")


if __name__ == "__main__":
    main()
