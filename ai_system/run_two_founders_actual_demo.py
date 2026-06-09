import argparse
import json
import logging
import os
import re
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from ai_system.env_setup import setup_openai_env
from ai_system.founder_shell import FounderShell, FounderStatus
from ai_system.investor import FundingDecision
from ai_system.literature_db import get_literature_db, reset_literature_db
from ai_system.peer_review import ReviewResult
from ai_system.proposal_builder import build_proposal
from ai_system.reputation import FounderProfile
from ai_system.skill_manager import SkillManager
from ai_system.token_budget import TokenBudget
from ai_system.orchestrator import _make_full_writeup_runner, _make_real_idea_generator


logger = logging.getLogger(__name__)


STARTER_CODE = """
import json
import os
import random

import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim


seed = 0
random.seed(seed)
np.random.seed(seed)
torch.manual_seed(seed)
if torch.cuda.is_available():
    torch.cuda.manual_seed_all(seed)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
working_dir = os.path.join(os.getcwd(), "working")
os.makedirs(working_dir, exist_ok=True)
print(f"Using device: {device}")

n_train, n_val = 512, 128
x0 = np.random.randn(n_train // 2, 2) * 0.8 + np.array([-1.5, -1.5])
x1 = np.random.randn(n_train // 2, 2) * 0.8 + np.array([1.5, 1.5])
X_train = np.concatenate([x0, x1], axis=0).astype(np.float32)
y_train = np.concatenate([np.zeros(n_train // 2), np.ones(n_train // 2)], axis=0).astype(np.int64)
x0v = np.random.randn(n_val // 2, 2) * 0.8 + np.array([-1.5, -1.5])
x1v = np.random.randn(n_val // 2, 2) * 0.8 + np.array([1.5, 1.5])
X_val = np.concatenate([x0v, x1v], axis=0).astype(np.float32)
y_val = np.concatenate([np.zeros(n_val // 2), np.ones(n_val // 2)], axis=0).astype(np.int64)

perm = np.random.permutation(n_train)
X_train, y_train = X_train[perm], y_train[perm]
perm = np.random.permutation(n_val)
X_val, y_val = X_val[perm], y_val[perm]

X_train = torch.tensor(X_train, device=device)
y_train = torch.tensor(y_train, device=device)
X_val = torch.tensor(X_val, device=device)
y_val = torch.tensor(y_val, device=device)

model = nn.Sequential(nn.Linear(2, 32), nn.ReLU(), nn.Linear(32, 2)).to(device)
optimizer = optim.SGD(model.parameters(), lr=0.1, momentum=0.9)
criterion = nn.CrossEntropyLoss()

train_losses, val_losses = [], []
train_metrics, val_metrics = [], []

for epoch in range(4):
    model.train()
    batch_losses = []
    correct = 0
    total = 0
    for start in range(0, n_train, 128):
        xb = X_train[start:start + 128]
        yb = y_train[start:start + 128]
        optimizer.zero_grad()
        logits = model(xb)
        loss = criterion(logits, yb)
        loss.backward()
        optimizer.step()
        batch_losses.append(loss.item())
        correct += (logits.argmax(dim=1) == yb).sum().item()
        total += yb.shape[0]
    train_loss = float(np.mean(batch_losses))
    train_acc = correct / max(total, 1)

    model.eval()
    with torch.no_grad():
        val_logits = model(X_val)
        val_loss = criterion(val_logits, y_val).item()
        val_acc = (val_logits.argmax(dim=1) == y_val).float().mean().item()

    train_losses.append(train_loss)
    val_losses.append(val_loss)
    train_metrics.append(train_acc)
    val_metrics.append(val_acc)
    print(
        f"epoch={epoch} train_loss={train_loss:.6f} val_loss={val_loss:.6f} "
        f"train_acc={train_acc:.6f} val_acc={val_acc:.6f}"
    )

experiment_data = {
    "synthetic_gaussian": {
        "losses": {"train": train_losses, "val": val_losses},
        "metrics": {"train": train_metrics, "val": val_metrics},
    }
}
np.save(os.path.join(working_dir, "experiment_data.npy"), experiment_data, allow_pickle=True)

plt.figure(figsize=(10, 4))
plt.subplot(1, 2, 1)
plt.plot(train_losses, label="Train Loss")
plt.plot(val_losses, label="Val Loss")
plt.legend()
plt.title("Loss Over Epochs")
plt.subplot(1, 2, 2)
plt.plot(train_metrics, label="Train Metric")
plt.plot(val_metrics, label="Val Accuracy")
plt.legend()
plt.title("Validation Accuracy Over Epochs")
plt.tight_layout()
plt.savefig(os.path.join(working_dir, "training_dynamics.png"))
plt.close()

result = {
    "best_metric": max(val_metrics),
    "final_val_accuracy": val_metrics[-1],
    "status": "completed",
}
print(json.dumps(result))
"""


def _extract_json(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
        if match:
            stripped = match.group(1)
    return json.loads(stripped)


def _to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return "\n".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


class TraceRecorder:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.trace_file = run_dir / "outer_llm_io.jsonl"
        self.event_file = run_dir / "outer_events.jsonl"
        self._lock = threading.Lock()

    def _append(self, path: Path, payload: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def log_llm(self, founder_id: str, phase: str, payload: dict):
        self._append(
            self.trace_file,
            {
                "timestamp": datetime.now().isoformat(),
                "founder_id": founder_id,
                "phase": phase,
                **payload,
            },
        )

    def log_event(self, founder_id: str, phase: str, payload: dict):
        self._append(
            self.event_file,
            {
                "timestamp": datetime.now().isoformat(),
                "founder_id": founder_id,
                "phase": phase,
                **payload,
            },
        )

    def write_json(self, relative_path: str, payload: dict):
        path = self.run_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def write_text(self, relative_path: str, text: str):
        path = self.run_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)


class TracedSkillManager(SkillManager):
    def __init__(self, founder_id: str, recorder: TraceRecorder, store_dir: str):
        super().__init__(founder_id, store_dir=store_dir)
        self.recorder = recorder

    def update_from_feedback(
        self,
        current_skill: str,
        event_description: str,
        feedback_text: str,
        model: str = "qwen3.6-plus",
    ):
        new_skill, ok = super().update_from_feedback(
            current_skill=current_skill,
            event_description=event_description,
            feedback_text=feedback_text,
            model=model,
        )
        self.recorder.log_llm(
            self.founder_id,
            "skill_update",
            {
                "event_description": event_description,
                "feedback_text": feedback_text,
                "skill_before": current_skill,
                "skill_after": new_skill,
                "success": ok,
            },
        )
        return new_skill, ok


class RuleGpuInvestor:
    def __init__(
        self,
        investor_id: str,
        direction: str,
        token_pool: float,
        founder_rules: dict,
        recorder: TraceRecorder,
    ):
        self.investor_id = investor_id
        self.direction = direction
        self.token_pool = token_pool
        self.founder_rules = founder_rules
        self.recorder = recorder
        self._extra_request_counts = {}

    def _rule(self, founder_id: str) -> dict:
        return self.founder_rules.get(founder_id, {})

    def evaluate_initial_proposal(self, proposal_text: str, founder_profile: dict) -> FundingDecision:
        founder_id = founder_profile["founder_id"]
        rule = self._rule(founder_id)
        amount = float(rule.get("initial_amount_usd", 0.0))
        approved = amount > 0 and self.token_pool >= amount
        if approved:
            self.token_pool -= amount
        decision = FundingDecision(
            approved=approved,
            token_amount_usd=amount if approved else 0.0,
            reason=rule.get(
                "initial_reason",
                "Tiny initial tranche for smoke-testing the founder pipeline.",
            ),
            gpu_ids=rule.get("gpu_ids", []),
        )
        self.recorder.log_event(
            founder_id,
            "initial_funding_decision",
            {
                "proposal_text": proposal_text,
                "decision": asdict(decision),
                "token_pool_after": self.token_pool,
            },
        )
        return decision

    def evaluate_extra_funding(self, progress_summary: dict, founder_profile: dict) -> FundingDecision:
        founder_id = founder_profile["founder_id"]
        rule = self._rule(founder_id)
        count = self._extra_request_counts.get(founder_id, 0)
        extra_schedule = rule.get("extra_amounts_usd", [])
        amount = float(extra_schedule[count]) if count < len(extra_schedule) else 0.0
        approved = amount > 0 and self.token_pool >= amount
        if approved:
            self.token_pool -= amount
        self._extra_request_counts[founder_id] = count + 1
        decision = FundingDecision(
            approved=approved,
            token_amount_usd=amount if approved else 0.0,
            reason=rule.get(
                "extra_reason",
                "Additional funding released after the first budget gate.",
            )
            if approved
            else rule.get(
                "extra_reject_reason",
                "The rule-based investor stops after the tiny initial tranche.",
            ),
            gpu_ids=rule.get("gpu_ids", []),
        )
        self.recorder.log_event(
            founder_id,
            "extra_funding_decision",
            {
                "progress_summary": progress_summary,
                "decision": asdict(decision),
                "token_pool_after": self.token_pool,
            },
        )
        return decision


class LlmPeerReview:
    def __init__(self, recorder: TraceRecorder, model: str):
        self.recorder = recorder
        self.model = model

    def evaluate(
        self,
        paper_title: str,
        paper_text: str,
        author_id: str,
        paper_pdf_path: Optional[str] = None,
    ) -> ReviewResult:
        from ai_scientist.llm import create_client, get_response_from_llm

        prompt = f"""You are a concise conference reviewer.

Paper title:
{paper_title}

Paper text:
{paper_text}

Return ONLY JSON with:
- "accepted": true or false
- "overall_score": number from 1 to 10
- "meta_review": short paragraph
- "reviews": list of exactly 3 objects, each with "reviewer", "score", "summary"
"""
        client, client_model = create_client(self.model)
        response_text, _ = get_response_from_llm(
            prompt=prompt,
            client=client,
            model=client_model,
            system_message="You are a careful ML reviewer. Output only valid JSON.",
            msg_history=[],
        )
        parsed = _extract_json(response_text)
        self.recorder.log_llm(
            author_id,
            "peer_review",
            {
                "prompt": prompt,
                "response_text": response_text,
                "parsed": parsed,
                "paper_pdf_path": paper_pdf_path,
            },
        )
        return ReviewResult(
            accepted=bool(parsed["accepted"]),
            overall_score=float(parsed["overall_score"]),
            reviews=parsed["reviews"],
            meta_review=parsed["meta_review"],
        )


def make_traced_proposal_builder(recorder: TraceRecorder):
    def wrapped_builder(
        idea: dict,
        founder_id: str,
        founder_profile_summary: dict,
        investors: list,
        model: str = "qwen3.6-plus",
    ):
        proposal = build_proposal(
            idea=idea,
            founder_id=founder_id,
            founder_profile_summary=founder_profile_summary,
            investors=investors,
            model=model,
        )
        recorder.log_llm(
            founder_id,
            "proposal_builder",
            {
                "idea": idea,
                "founder_profile_summary": founder_profile_summary,
                "investors": investors,
                "proposal": asdict(proposal) if proposal else None,
            },
        )
        return proposal

    return wrapped_builder


def make_actual_experiment_runner(
    founder_id: str,
    founder_dir: Path,
    recorder: TraceRecorder,
):
    cycle_counter = {"value": 0}
    post_run_budget_gate_used = {"value": False}

    def run(idea: dict, gpu_ids: list, model: str) -> dict:
        from ai_system.token_budget import deduct_manual
        import numpy as np
        from ai_scientist.treesearch.agent_manager import AgentManager
        from ai_scientist.treesearch.bfts_utils import edit_bfts_config_file
        from ai_scientist.treesearch.perform_experiments_bfts_with_agentmanager import (
            perform_experiments_bfts,
        )

        cycle_counter["value"] += 1
        cycle_idx = cycle_counter["value"]
        cycle_dir = founder_dir / f"cycle_{cycle_idx}"
        cycle_dir.mkdir(parents=True, exist_ok=True)
        deduct_manual(cost_usd=0.02, model=model)
        recorder.log_event(
            founder_id,
            "experiment_setup_charge",
            {"cost_usd": 0.02, "gpu_ids": gpu_ids},
        )

        experiment_idea = {
            "Name": f"{idea.get('Name', founder_id)}_tiny_actual",
            "Title": _to_text(idea.get("Title", f"{founder_id} tiny actual run")),
            "Short Hypothesis": _to_text(idea.get(
                "Short Hypothesis",
                "A tiny MLP on synthetic Gaussian data is enough to validate the full pipeline.",
            )),
            "Related Work": _to_text(idea.get(
                "Related Work",
                "This run is for pipeline validation with a small synthetic baseline.",
            )),
            "Abstract": _to_text(idea.get(
                "Abstract",
                "This run validates the founder ecosystem by executing a minimal AI Scientist experiment.",
            )),
            "Experiments": (
                _to_text(idea.get("Experiments", ""))
                + "\n\nImplementation note: use the provided tiny synthetic scaffold and keep the search short."
            ).strip(),
            "Risk Factors and Limitations": _to_text(idea.get(
                "Risk Factors and Limitations",
                "This is a tiny validation run, not a publication-grade result.",
            )),
            "Code": STARTER_CODE,
        }

        idea_json = cycle_dir / "idea.json"
        with open(idea_json, "w", encoding="utf-8") as f:
            json.dump(experiment_idea, f, indent=2, ensure_ascii=False)

        config_path = edit_bfts_config_file("bfts_config.yaml", str(cycle_dir), str(idea_json))
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        cfg["generate_report"] = False
        cfg["agent"]["num_workers"] = 1
        cfg["agent"]["steps"] = 1
        cfg["agent"]["stages"]["stage1_max_iters"] = 1
        cfg["agent"]["stages"]["stage2_max_iters"] = 1
        cfg["agent"]["stages"]["stage3_max_iters"] = 1
        cfg["agent"]["stages"]["stage4_max_iters"] = 1
        cfg["agent"]["multi_seed_eval"]["num_seeds"] = 1
        cfg["agent"]["search"]["num_drafts"] = 1
        cfg["agent"]["search"]["max_debug_depth"] = 1
        cfg["agent"]["search"]["debug_prob"] = 0.0
        cfg["agent"]["code"]["model"] = model
        cfg["agent"]["feedback"]["model"] = model
        cfg["agent"]["vlm_feedback"]["model"] = model
        cfg["report"]["model"] = model

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f)

        orig_next_main = AgentManager._create_next_main_stage
        orig_next_sub = AgentManager._create_next_substage
        AgentManager._create_next_main_stage = lambda self, current_substage, journal: None
        AgentManager._create_next_substage = (
            lambda self, current_substage, journal, substage_feedback: None
        )
        try:
            perform_experiments_bfts(config_path)
        finally:
            AgentManager._create_next_main_stage = orig_next_main
            AgentManager._create_next_substage = orig_next_sub

        stage_progress_files = sorted(cycle_dir.glob("logs/*/stage_*/notes/stage_progress.json"))
        stage_progress = {}
        if stage_progress_files:
            with open(stage_progress_files[-1], "r", encoding="utf-8") as f:
                stage_progress = json.load(f)

        plot_paths = [str(p.resolve()) for p in cycle_dir.glob("logs/*/experiment_results/**/*.png")]
        experiment_dirs = [str(p.resolve()) for p in cycle_dir.glob("logs/*/experiment_results/*")]

        metric_value = 0.0
        experiment_data_paths = sorted(cycle_dir.glob("logs/*/experiment_results/*/experiment_data.npy"))
        if experiment_data_paths:
            data = np.load(experiment_data_paths[-1], allow_pickle=True).item()
            metric_value = float(data["synthetic_gaussian"]["metrics"]["val"][-1])
        else:
            best_metric_text = stage_progress.get("best_metric")
            if isinstance(best_metric_text, str):
                match = re.search(r"([-+]?\d*\.?\d+)", best_metric_text)
                if match:
                    metric_value = float(match.group(1))

        result = {
            "idea_title": experiment_idea["Title"],
            "best_metric": metric_value,
            "experiments_completed": 1,
            "status": "completed",
            "stage_progress": stage_progress,
            "plot_paths": plot_paths,
            "experiment_dirs": experiment_dirs,
            "experiment_data_paths": [str(p.resolve()) for p in experiment_data_paths],
            "cycle_dir": str(cycle_dir.resolve()),
            "gpu_ids": gpu_ids,
        }
        recorder.log_event(
            founder_id,
            "actual_experiment_completed",
            {
                "result": result,
                "idea_title": experiment_idea["Title"],
            },
        )
        if not post_run_budget_gate_used["value"]:
            post_run_budget_gate_used["value"] = True
            deduct_manual(cost_usd=0.01, model=model)
            recorder.log_event(
                founder_id,
                "post_experiment_budget_gate",
                {"cost_usd": 0.01, "reason": "Force one extra-funding branch after a completed actual experiment."},
            )
        return result

    return run


def make_traced_writeup_runner(founder_id: str, recorder: TraceRecorder, founder_dir: Path):
    base_runner = _make_full_writeup_runner()
    counter = {"value": 0}

    def run(experiment_result: dict, skill_text: str, model: str) -> dict:
        counter["value"] += 1
        paper = base_runner(experiment_result, skill_text, model)
        recorder.log_llm(
            founder_id,
            "writeup",
            {
                "experiment_result": experiment_result,
                "skill_text": skill_text,
                "paper": paper,
            },
        )
        recorder.write_text(
            f"{founder_id}/cycle_{counter['value']}/paper.txt",
            paper.get("text", ""),
        )
        recorder.write_json(
            f"{founder_id}/cycle_{counter['value']}/paper_meta.json",
            paper,
        )
        return paper

    return run


def build_shell(
    founder_id: str,
    investor,
    literature_db,
    peer_review,
    recorder: TraceRecorder,
    run_dir: Path,
    model: str,
    initial_budget_usd: float,
):
    founder_dir = run_dir / founder_id
    skill_mgr = TracedSkillManager(
        founder_id=founder_id,
        recorder=recorder,
        store_dir=str(run_dir / "skill_store"),
    )
    profile = FounderProfile(
        founder_id=founder_id,
        store_dir=str(run_dir / "profile_store"),
    )
    budget = TokenBudget(initial_usd=initial_budget_usd)
    idea_generator = _make_real_idea_generator()
    experiment_runner = make_actual_experiment_runner(founder_id, founder_dir, recorder)
    writeup_runner = make_traced_writeup_runner(founder_id, recorder, founder_dir)

    shell = FounderShell(
        founder_id=founder_id,
        skill_manager=skill_mgr,
        profile=profile,
        token_budget=budget,
        investors=[investor],
        literature_db=literature_db,
        peer_review=peer_review,
        idea_generator=idea_generator,
        experiment_runner=experiment_runner,
        writeup_runner=writeup_runner,
        proposal_builder=make_traced_proposal_builder(recorder),
        model=model,
        skill_store_dir=str(run_dir / "skill_store"),
        profile_store_dir=str(run_dir / "profile_store"),
        resource_scheduler=None,
        gpus_per_funding=1,
    )
    return shell


def run_demo(output_dir: Optional[str], model: str):
    from ai_scientist.utils.token_tracker import token_tracker

    setup_openai_env()
    token_tracker.reset()
    reset_literature_db()
    literature_db = get_literature_db()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    requested_dir = Path(output_dir or f"ai_system_runs/two_founders_actual_{timestamp}")
    if requested_dir.exists() and any(requested_dir.iterdir()):
        run_dir = requested_dir.parent / f"{requested_dir.name}_{timestamp}"
    else:
        run_dir = requested_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    recorder = TraceRecorder(run_dir)

    founder_rules = {
        "founder_1": {
            "gpu_ids": [0],
            "initial_amount_usd": 0.005,
            "extra_amounts_usd": [0.12],
            "initial_reason": "Initial tranche is intentionally tiny to force a budget gate during experiment execution.",
            "extra_reason": "The founder demonstrated enough progress to unlock a larger follow-on tranche.",
        },
        "founder_2": {
            "gpu_ids": [1],
            "initial_amount_usd": 0.005,
            "extra_amounts_usd": [0.0],
            "initial_reason": "Initial tranche is intentionally tiny to test the extra-funding path.",
            "extra_reject_reason": "The investor declines further spend after the first checkpoint.",
        },
    }
    investor = RuleGpuInvestor(
        investor_id="rule_investor_1",
        direction="Synthetic ML pipeline validation with strict budget gates.",
        token_pool=10.0,
        founder_rules=founder_rules,
        recorder=recorder,
    )
    peer_review = LlmPeerReview(recorder=recorder, model=model)

    shells = [
        build_shell(
            founder_id="founder_1",
            investor=investor,
            literature_db=literature_db,
            peer_review=peer_review,
            recorder=recorder,
            run_dir=run_dir,
            model=model,
            initial_budget_usd=0.03,
        ),
        build_shell(
            founder_id="founder_2",
            investor=investor,
            literature_db=literature_db,
            peer_review=peer_review,
            recorder=recorder,
            run_dir=run_dir,
            model=model,
            initial_budget_usd=0.03,
        ),
    ]

    for shell in shells:
        logger.info("[%s] starting full founder cycle", shell.founder_id)
        success = False
        for _ in range(4):
            success = shell.run_cycle()
            if shell.status in (FounderStatus.IDLE, FounderStatus.DEAD):
                break
        recorder.log_event(
            shell.founder_id,
            "cycle_finished",
            {
                "success": success,
                "summary": shell.summary(),
            },
        )

    summary = {
        "run_dir": str(run_dir.resolve()),
        "model": model,
        "literature_db": literature_db.stats(),
        "token_tracker_summary": token_tracker.get_summary(),
        "founders": {shell.founder_id: shell.summary() for shell in shells},
        "profile_files": {
            shell.founder_id: str((run_dir / "profile_store" / f"{shell.founder_id}.json").resolve())
            for shell in shells
        },
        "skill_files": {
            shell.founder_id: str((run_dir / "skill_store" / f"{shell.founder_id}.json").resolve())
            for shell in shells
        },
        "outer_llm_io_file": str((run_dir / "outer_llm_io.jsonl").resolve()),
        "outer_event_file": str((run_dir / "outer_events.jsonl").resolve()),
    }
    recorder.write_json("run_summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description="Run two founders through a real minimal AI Scientist experiment.")
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--model", type=str, default="qwen3.5-flash")
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    summary = run_demo(output_dir=args.output_dir, model=args.model)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
