"""
Orchestrator — 系统主入口。

管理多 Founder、多 Investor 的异步批次运行循环。

Debug 版：顺序执行（每轮一个 Founder），简化 GPU 调度。
真实版应升级为并行执行 + GPU 隔离 + 真正的异步批次模型。
"""

import logging
import json
import sys
import os
import shutil
import re
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import List, Optional, Callable
from datetime import datetime
import time

from ai_system.config import (
    DEFAULT_INITIAL_TOKEN_USD,
    DEFAULT_SKILL_TEXT,
    GLOBAL_BUDGET_CAP_USD,
    INVESTOR_APPROVAL_TOKEN_USD,
    INVESTOR_EXTRA_TOKEN_USD,
    INVESTOR_DIRECTION,
    INVESTOR_TOTAL_BUDGET_USD,
    SKILL_STORE_DIR,
    PROFILE_STORE_DIR,
)
from ai_system import messages
from ai_system.token_budget import TokenBudget, deduct_manual
from ai_system.skill_manager import SkillManager
from ai_system.reputation import FounderProfile
from ai_system.investor import FundRoleInvestor, FundingDecision, LLMInvestor, YesManInvestor
from ai_system.literature_db import LiteratureDB, get_literature_db, reset_literature_db
from ai_system.peer_review import FounderReviewSociety, PlaceholderPeerReview
from ai_system.proposal_builder import build_proposal_debug, build_proposal, Proposal
from ai_system.founder_shell import FounderShell, FounderStatus
from ai_system.env_setup import setup_openai_env
from ai_system.resource_scheduler import ResourceScheduler
from ai_system.trace_recorder import TraceRecorder

logger = logging.getLogger(__name__)


_ACTUAL_STARTER_CODE = """
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

print(json.dumps({
    "best_metric": max(val_metrics),
    "final_val_accuracy": val_metrics[-1],
    "status": "completed"
}))
"""


def _make_mock_idea_generator():
    """创建 mock idea 生成器（debug 用，跳过真实 LLM ideation）。"""

    def mock_generate(skill_text: str, model: str, peer_brief: str = "") -> dict:
        import random
        idea_id = random.randint(1000, 9999)
        return {
            "Name": f"test_idea_{idea_id}",
            "Title": f"A Novel Approach to Machine Learning (ID={idea_id})",
            "Short Hypothesis": "We hypothesize that method X outperforms baseline Y on task Z.",
            "Related Work": "Prior work includes A, B, and C. Our approach differs by...",
            "Abstract": (
                "This paper proposes a novel method for improving machine learning models. "
                "We introduce a new technique that addresses key limitations in existing approaches. "
                "Our experiments demonstrate significant improvements over strong baselines."
            ),
            "Experiments": "1. Baseline comparison on standard benchmarks.\n2. Ablation studies.\n3. Analysis of results.",
            "Risk Factors and Limitations": "Limited compute resources. May not generalize to all domains.",
        }

    return mock_generate


def _make_mock_experiment_runner(calls_per_experiment: int = 6, cost_per_call_usd: float = 5.0):
    """创建 mock 实验执行器（debug 用，跳过真实实验）。"""

    def mock_run(idea: dict, gpu_ids: list, model: str) -> dict:
        import random
        import time

        title = idea.get("Title", "untitled")
        logger.info(f"  [Mock Experiment] 运行实验: {title}")
        for _ in range(calls_per_experiment):
            deduct_manual(cost_usd=cost_per_call_usd, model=model)
        time.sleep(0.1)

        return {
            "idea_title": title,
            "best_metric": round(random.uniform(0.7, 0.95), 3),
            "experiments_completed": random.randint(3, 8),
            "nodes_explored": random.randint(10, 50),
            "status": "completed",
        }

    return mock_run


def _make_mock_writeup_runner():
    """创建 mock 论文写作器（debug 用）。"""

    def mock_writeup(experiment_result: dict, skill_text: str, model: str) -> dict:
        title = experiment_result.get("idea_title", "Untitled")
        metric = experiment_result.get("best_metric", 0.0)
        logger.info(f"  [Mock Writeup] 写作论文: {title}")

        paper_text = (
            f"# {title}\n\n"
            f"## Abstract\n"
            f"We present a novel approach achieving {metric} on the benchmark.\n\n"
            f"## Experiments\n"
            f"Results demonstrate significant improvements.\n"
        )

        return {
            "title": title,
            "text": paper_text,
            "metric": metric,
        }

    return mock_writeup


class Orchestrator:
    """
    系统编排器。

    Debug 版：顺序执行每个 Founder 的循环。
    真实版：实现异步批次模型（见 founder_design.md 1.2 节）。
    """

    def __init__(
        self,
        num_founders: int = 2,
        num_investors: int = 1,
        max_cycles_per_founder: int = 3,
        use_mock_agent: bool = True,
        use_debug_investor_selection: bool = True,
        use_llm_investor: bool = False,
        use_resource_scheduler: bool = True,
        physical_gpu_count: int = 8,
        model: str = "qwen3.6-plus",
        actual_experiment: bool = False,
        max_projects_per_round: int = 3,
        approval_amount_usd: float = INVESTOR_APPROVAL_TOKEN_USD,
        extra_amount_usd: float = INVESTOR_EXTRA_TOKEN_USD,
        investor_total_budget_usd: float = INVESTOR_TOTAL_BUDGET_USD,
        global_budget_cap_usd: float = GLOBAL_BUDGET_CAP_USD,
        run_root_dir: str = "ai_system_runs/orchestrator_actual",
        bfts_num_workers: int = 1,
        bfts_steps: int = 1,
        bfts_stage_max_iters: int = 1,
        bfts_max_debug_depth: int = 1,
        bfts_num_drafts: int = 1,
        initial_review_delay_sec: int = 180,
        mock_experiment_in_real_agent: bool = False,
    ):
        self.num_founders = num_founders
        self.num_investors = num_investors
        self.max_cycles_per_founder = max_cycles_per_founder
        self.use_mock_agent = use_mock_agent
        self.mock_experiment_in_real_agent = mock_experiment_in_real_agent
        self.use_debug_investor_selection = use_debug_investor_selection
        self.use_llm_investor = use_llm_investor
        self.model = model
        self.physical_gpu_count = physical_gpu_count
        self.actual_experiment = actual_experiment
        self.max_projects_per_round = max_projects_per_round
        self.approval_amount_usd = approval_amount_usd
        self.extra_amount_usd = extra_amount_usd
        self.investor_total_budget_usd = investor_total_budget_usd
        self.global_budget_cap_usd = global_budget_cap_usd
        self.run_root_dir = run_root_dir
        self.bfts_num_workers = bfts_num_workers
        self.bfts_steps = bfts_steps
        self.bfts_stage_max_iters = bfts_stage_max_iters
        self.bfts_max_debug_depth = bfts_max_debug_depth
        self.bfts_num_drafts = bfts_num_drafts
        self.initial_review_delay_sec = initial_review_delay_sec

        if use_resource_scheduler:
            self.resource_scheduler = ResourceScheduler(
                physical_gpu_ids=list(range(physical_gpu_count))
            )
        else:
            self.resource_scheduler = None

        # 共享基础设施
        self.literature_db = get_literature_db()
        self.peer_review = PlaceholderPeerReview(seed=None)
        self.recorder = TraceRecorder(self.run_root_dir)

        # Investor 列表
        self.investors: List[YesManInvestor] = []
        self._init_investors()

        # Founder Shell 列表
        self.shells: List[FounderShell] = []
        self._init_founders()

        # 统计
        self.global_round = 0
        self.stats = {
            "total_papers_published": 0,
            "total_papers_rejected": 0,
            "total_bankruptcies": 0,
            "total_funding_approved": 0,
        }

    def _init_investors(self):
        """初始化 Investor 列表。"""
        gpu_per_investor = max(1, self.physical_gpu_count // self.num_investors)
        directions = [
            "Machine learning theory and methods",
            "Computer vision and image processing",
            "Natural language processing and language models",
            "Reinforcement learning and decision making",
            "ML for science and applications",
        ]
        for i in range(self.num_investors):
            gpu_start = i * gpu_per_investor
            gpu_end = gpu_start + gpu_per_investor
            gpu_ids = list(range(gpu_start, min(gpu_end, self.physical_gpu_count)))

            if self.use_llm_investor:
                inv = FundRoleInvestor(
                    investor_id=f"fund_{i+1}",
                    direction=directions[i % len(directions)],
                    token_pool=self.investor_total_budget_usd,
                    approval_amount_usd=self.approval_amount_usd,
                    extra_amount_usd=self.extra_amount_usd,
                    model=self.model,
                    max_projects_per_round=self.max_projects_per_round,
                    recorder=self.recorder,
                )
            else:
                inv = YesManInvestor(
                    investor_id=f"yesman_{i+1}",
                    direction=INVESTOR_DIRECTION,
                    token_pool=self.investor_total_budget_usd,
                    max_projects_per_round=self.max_projects_per_round,
                    approval_amount_usd=self.approval_amount_usd,
                    extra_amount_usd=self.extra_amount_usd,
                    recorder=self.recorder,
                )
            inv._gpu_ids = gpu_ids
            self.investors.append(inv)
            if self.resource_scheduler is not None:
                self.resource_scheduler.assign_investor_pool(inv.investor_id, len(gpu_ids))

        logger.info(
            f"初始化 {self.num_investors} 个 Investor: "
            + ", ".join(f"{inv.investor_id}(GPU{inv._gpu_ids})" for inv in self.investors)
        )

    def _global_budget_consumed_usd(self) -> float:
        return sum(shell.token_budget.total_consumed_usd for shell in self.shells)

    def _global_budget_remaining_usd(self) -> float:
        return max(0.0, self.global_budget_cap_usd - self._global_budget_consumed_usd())

    def _global_budget_exhausted(self) -> bool:
        return self._global_budget_consumed_usd() >= self.global_budget_cap_usd

    def _global_budget_reject_decision(self, reason: Optional[str] = None) -> FundingDecision:
        reject_reason = reason or (
            f"Global ecosystem budget cap reached (${self.global_budget_cap_usd:.2f}); "
            "no new funding rounds or extra funding can be approved."
        )
        return FundingDecision(
            approved=False,
            token_amount_usd=0.0,
            reason=reject_reason,
            gpu_ids=[],
        )

    def _init_founders(self):
        """初始化 Founder Shell 列表。"""
        skill_store_dir = SKILL_STORE_DIR
        profile_store_dir = PROFILE_STORE_DIR
        state_store_dir = "ai_system/runtime_state"
        if self.actual_experiment:
            skill_store_dir = os.path.join(self.run_root_dir, "skill_store")
            profile_store_dir = os.path.join(self.run_root_dir, "profile_store")
            state_store_dir = os.path.join(self.run_root_dir, "runtime_state")
            os.makedirs(skill_store_dir, exist_ok=True)
            os.makedirs(profile_store_dir, exist_ok=True)
            os.makedirs(state_store_dir, exist_ok=True)

        for i in range(self.num_founders):
            founder_id = f"founder_{i+1}"

            skill_mgr = SkillManager(founder_id, store_dir=skill_store_dir, recorder=self.recorder)
            profile = FounderProfile(founder_id, store_dir=profile_store_dir)
            budget = TokenBudget(initial_usd=DEFAULT_INITIAL_TOKEN_USD)

            # 选择 proposal builder
            if self.use_debug_investor_selection:
                proposal_builder = build_proposal_debug
            else:
                proposal_builder = build_proposal

            # 选择 agent 实现
            if self.use_mock_agent:
                idea_gen = _make_mock_idea_generator()
                exp_runner = _make_mock_experiment_runner()
                writeup_runner = _make_mock_writeup_runner()
            else:
                idea_gen = _make_real_idea_generator()
                if self.mock_experiment_in_real_agent:
                    # 真 ideation + 真 peer review，但实验和 writeup 用 mock
                    # （无 GPU/torch/LaTeX 环境下验证生态链）
                    exp_runner = _make_mock_experiment_runner()
                    writeup_runner = _make_mock_writeup_runner()
                else:
                    exp_runner = _make_actual_bfts_experiment_runner(
                        run_root_dir=self.run_root_dir,
                        num_workers=self.bfts_num_workers,
                        steps=self.bfts_steps,
                        stage_max_iters=self.bfts_stage_max_iters,
                        max_debug_depth=self.bfts_max_debug_depth,
                        num_drafts=self.bfts_num_drafts,
                    )
                    writeup_runner = _make_full_writeup_runner()

            # 构建 Investor 信息列表（供 proposal_builder 使用）
            investor_infos = [
                {
                    "investor_id": inv.investor_id,
                    "direction": inv.direction,
                }
                for inv in self.investors
            ]

            shell = FounderShell(
                founder_id=founder_id,
                skill_manager=skill_mgr,
                profile=profile,
                token_budget=budget,
                investors=self.investors,
                literature_db=self.literature_db,
                peer_review=self.peer_review,
                idea_generator=idea_gen,
                experiment_runner=exp_runner,
                writeup_runner=writeup_runner,
                proposal_builder=proposal_builder,
                recorder=self.recorder,
                model=self.model,
                skill_store_dir=skill_store_dir,
                profile_store_dir=profile_store_dir,
                resource_scheduler=self.resource_scheduler,
                gpus_per_funding=1,
                state_store_dir=state_store_dir,
            )

            self.shells.append(shell)

        logger.info(f"初始化 {self.num_founders} 个 Founder Shell")

    def run(self):
        """主运行循环。"""
        logger.info("=" * 60)
        logger.info("AI Scientist Founder Ecosystem (Debug Version)")
        logger.info("=" * 60)
        logger.info(f"Founders: {self.num_founders}")
        logger.info(f"Investors: {self.num_investors}")
        logger.info(f"Max cycles/founder: {self.max_cycles_per_founder}")
        logger.info(f"Mock agent: {self.use_mock_agent}")
        logger.info(f"Debug investor selection: {self.use_debug_investor_selection}")
        logger.info("=" * 60)

        while True:
            self.global_round += 1
            alive_count = sum(1 for s in self.shells if s.is_alive())
            active_count = sum(
                1
                for s in self.shells
                if s.is_alive() and s.cycle_count < self.max_cycles_per_founder
            )

            if alive_count == 0:
                logger.info("所有 Founder 均已破产，系统终止。")
                break
            if active_count == 0:
                logger.info(
                    f"所有存活 Founder 均已达到最大循环数 ({self.max_cycles_per_founder})，系统正常退出。"
                )
                break

            logger.info(
                f"\n{'='*60}\n"
                f"  全局轮次 {self.global_round} — 存活 Founder: {alive_count}/{len(self.shells)} (活跃: {active_count})\n"
                f"{'='*60}"
            )

            for shell in self.shells:
                if not shell.is_alive():
                    continue
                if shell.cycle_count >= self.max_cycles_per_founder:
                    continue

                logger.info(
                    f"[{shell.founder_id}] 启动循环 (budget=${shell.token_budget.remaining_usd:.2f})"
                )

                success = shell.run_cycle()

                if success:
                    logger.info(
                        f"[{shell.founder_id}] 循环成功完成。"
                    )
                elif shell.status == FounderStatus.DEAD:
                    self.stats["total_bankruptcies"] += 1
                    logger.info(f"[{shell.founder_id}] 已破产。")

                # 输出当前状态
                self._print_status()

                if shell.cycle_count >= self.max_cycles_per_founder:
                    logger.info(
                        f"[{shell.founder_id}] 达到最大循环数 ({self.max_cycles_per_founder})，本 founder 后续将跳过。"
                    )
        self._print_final_report()

    def _print_status(self):
        """输出当前系统状态。"""
        lines = ["\n--- 系统状态 ---"]
        for shell in self.shells:
            s = shell.summary()
            lines.append(
                f"  {s['founder_id']}: status={s['status']}, "
                f"cycles={s['cycle_count']}, "
                f"papers={s['profile']['total_papers']} "
                f"(accepted={s['profile']['accepted_papers']}), "
                f"budget=${s['budget']['remaining_usd']:.2f}"
            )
        lines.append(
            f"  文献库: {self.literature_db.stats()}"
        )
        logger.info("\n".join(lines))

    def _print_final_report(self):
        """输出最终报告。"""
        logger.info("\n" + "=" * 60)
        logger.info("  最终报告")
        logger.info("=" * 60)

        for shell in self.shells:
            s = shell.summary()
            logger.info(f"\n  [{s['founder_id']}]")
            logger.info(f"    状态: {s['status']}")
            logger.info(f"    完成循环数: {s['cycle_count']}")
            logger.info(f"    总论文数: {s['profile']['total_papers']}")
            logger.info(f"    接收论文数: {s['profile']['accepted_papers']}")
            logger.info(f"    经费轮次: {s['profile']['total_funding_rounds']}")
            logger.info(f"    剩余预算: ${s['budget']['remaining_usd']:.2f}")
            logger.info(f"    总消耗: ${s['budget']['total_consumed_usd']:.2f}")

            # 显示 skill 摘要
            skill_mgr = shell.skill_manager
            skill_text = skill_mgr.load()
            skill_preview = skill_text[:200] + "..." if len(skill_text) > 200 else skill_text
            logger.info(f"    Skill: {skill_preview}")

        logger.info(f"\n  文献库统计: {self.literature_db.stats()}")
        logger.info(
            "  全局预算: 已消耗 $%.2f / 上限 $%.2f (剩余 $%.2f)",
            self._global_budget_consumed_usd(),
            self.global_budget_cap_usd,
            self._global_budget_remaining_usd(),
        )
        logger.info(f"  Funding 批准数: {self.stats['total_funding_approved']}")
        logger.info(f"  论文接收数: {self.stats['total_papers_published']}")
        logger.info(f"  论文拒稿数: {self.stats['total_papers_rejected']}")
        logger.info(f"  破产次数: {self.stats['total_bankruptcies']}")
        logger.info("=" * 60)


class MessageDrivenOrchestrator(Orchestrator):
    """
    Event-driven orchestrator with explicit founder/investor/reviewer messages.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.use_mock_agent:
            self.peer_review = PlaceholderPeerReview(seed=None)
        else:
            self.peer_review = FounderReviewSociety(model=self.model, seed=None, recorder=self.recorder)
        for shell in self.shells:
            shell.peer_review = self.peer_review
        if hasattr(self.peer_review, "register_founders"):
            self.peer_review.register_founders(self.shells)
        self._process_start = time.monotonic()

    def _submit_background_task(self, executor, running_tasks, shell, kind, fn, *args):
        if shell.founder_id in running_tasks:
            return
        future = executor.submit(fn, *args)
        running_tasks[shell.founder_id] = {
            "future": future,
            "kind": kind,
        }

    def _submit_start_if_needed(self, executor, running_tasks, shell):
        if self._global_budget_exhausted():
            return
        if shell.status == FounderStatus.IDLE and shell.cycle_count < self.max_cycles_per_founder:
            self._submit_background_task(
                executor, running_tasks, shell, "start", shell.start_cycle_async
            )

    def _all_start_tasks_idle(self, running_tasks):
        return all(item["kind"] != "start" for item in running_tasks.values())

    # 开 round 前要求申请队列连续稳定的轮询拍数（主循环每拍约 0.2s，5 拍≈1s）。
    # 这是「这批 proposal 交齐没」的判断，与投资人的评审延迟语义无关，
    # 故用独立常量，不再复用 initial_review_delay_sec（那个默认 180，会把
    # 稳定窗口撑到 180s 导致默认配置下永远开不了 round）。
    _ROUND_QUEUE_STABLE_TICKS = 5

    def _can_open_round_now(self, investor, running_tasks):
        if self._global_budget_exhausted():
            return False
        if not hasattr(investor, "can_open_initial_round"):
            return False
        if not investor.can_open_initial_round():
            return False
        if not self._all_start_tasks_idle(running_tasks):
            return False
        # Bug2 修复：先到的 proposal 不要立刻单独开 round，给同批 founder
        # 一个聚合窗口把各自的 proposal 交齐，这样它们能在同一 round 竞争。
        # 实现：要求投资人的 application_queue 在连续若干次轮询中保持稳定
        # （不再有新 proposal 进来）才开 round。绝不依赖「在途」长等，避免死锁。
        queue_sig = tuple(sorted(p["founder_id"] for p in investor.application_queue))
        last_sig = getattr(self, "_round_queue_sig", None)
        if queue_sig != last_sig:
            # 队列刚变化（有新 proposal 进来）→ 重置计数，再等一会儿看还有没有
            self._round_queue_sig = queue_sig
            self._round_queue_stable = 0
            return False
        # 队列内容未变：累计稳定轮数
        self._round_queue_stable = getattr(self, "_round_queue_stable", 0) + 1
        if self._round_queue_stable >= self._ROUND_QUEUE_STABLE_TICKS:
            # 窗口内队列稳定，开 round；重置计数供后续轮次
            self._round_queue_sig = None
            self._round_queue_stable = 0
            return True
        return False

    def _process_initial_funding_rounds(self, queue, running_tasks):
        opened_any = False
        for investor in self.investors:
            if self._global_budget_exhausted():
                proposal_batch = investor.drain_application_queue()
                if proposal_batch:
                    decision = self._global_budget_reject_decision()
                    for msg in proposal_batch:
                        queue.append(
                            {
                                "type": messages.INITIAL_FUNDING_DECISION,
                                "founder_id": msg["founder_id"],
                                "investor_id": investor.investor_id,
                                "decision": decision,
                            }
                        )
                continue
            if not self._can_open_round_now(investor, running_tasks):
                continue
            proposal_batch = investor.drain_application_queue()
            if not proposal_batch:
                continue
            opened_any = True
            logger.info(
                "[%s] opening funding round with %d queued proposals",
                investor.investor_id,
                len(proposal_batch),
            )
            if hasattr(investor, "evaluate_initial_batch"):
                decisions = investor.evaluate_initial_batch(proposal_batch)
            else:
                decisions = {
                    msg["founder_id"]: investor.evaluate_initial_proposal(
                        msg["proposal_text"], msg["profile_summary"]
                    )
                    for msg in proposal_batch
                }
            if self.recorder is not None:
                self.recorder.log_event(
                    investor.investor_id,
                    "initial_funding_round",
                    {
                        "proposal_batch": proposal_batch,
                        "decisions": {
                            founder_id: {
                                "approved": decision.approved,
                                "token_amount_usd": decision.token_amount_usd,
                                "reason": decision.reason,
                                "gpu_ids": decision.gpu_ids or [],
                            }
                            for founder_id, decision in decisions.items()
                        },
                    },
                )
            for msg in proposal_batch:
                queue.append(
                    {
                        "type": messages.INITIAL_FUNDING_DECISION,
                        "founder_id": msg["founder_id"],
                        "investor_id": investor.investor_id,
                        "decision": decisions[msg["founder_id"]],
                    }
                )
        if opened_any:
            self.global_round += 1

    def _handle_completed_task(self, queue, running_tasks, founder_id):
        task = running_tasks.pop(founder_id)
        future = task["future"]
        kind = task["kind"]
        shell = next((s for s in self.shells if s.founder_id == founder_id), None)
        if shell is None:
            return
        try:
            result = future.result()
        except Exception as e:
            logger.exception("[%s] background task %s crashed: %s", founder_id, kind, e)
            if shell.status != FounderStatus.DEAD:
                shell._bankrupt(f"background task failure: {kind}")
                self.stats["total_bankruptcies"] += 1
            return

        if kind in {"start", "advance"}:
            if result is not None:
                queue.append(result)
            elif shell.status == FounderStatus.DEAD:
                self.stats["total_bankruptcies"] += 1
        elif kind == "review":
            queue.append(
                {
                    "type": messages.REVIEW_RESULT,
                    "founder_id": founder_id,
                    "review_result": result,
                }
            )

    def run(self):
        logger.info("=" * 60)
        logger.info("AI Scientist Founder Ecosystem (Message-Driven, Concurrent)")
        logger.info("=" * 60)
        queue = deque()
        running_tasks = {}
        max_workers = max(len(self.shells) * 2, 4)

        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ecosystem") as executor:
            while True:
                for shell in self.shells:
                    self._submit_start_if_needed(executor, running_tasks, shell)

                completed = []
                if running_tasks:
                    futures = [item["future"] for item in running_tasks.values()]
                    done, _ = wait(futures, timeout=0.2, return_when=FIRST_COMPLETED)
                    done_set = set(done)
                    for founder_id, item in list(running_tasks.items()):
                        if item["future"] in done_set:
                            completed.append(founder_id)
                for founder_id in completed:
                    self._handle_completed_task(queue, running_tasks, founder_id)

                self._process_initial_funding_rounds(queue, running_tasks)

                while queue:
                    msg = queue.popleft()
                    msg_type = msg.get("type")
                    founder_id = msg.get("founder_id")
                    shell = next((s for s in self.shells if s.founder_id == founder_id), None)

                    if msg_type == messages.INITIAL_FUNDING_REQUEST:
                        if self._global_budget_exhausted():
                            queue.append(
                                {
                                    "type": messages.INITIAL_FUNDING_DECISION,
                                    "founder_id": msg["founder_id"],
                                    "investor_id": msg["investor_id"],
                                    "decision": self._global_budget_reject_decision(),
                                }
                            )
                            continue
                        investor = next(
                            inv for inv in self.investors if inv.investor_id == msg["investor_id"]
                        )
                        if hasattr(investor, "submit_application"):
                            investor.submit_application(msg)
                        continue

                    if shell is None:
                        continue

                    if msg_type == messages.INITIAL_FUNDING_DECISION:
                        decision = msg["decision"]
                        shell.apply_initial_funding_decision(decision, msg["investor_id"])
                        investor = next(inv for inv in self.investors if inv.investor_id == msg["investor_id"])
                        if getattr(decision, "approved", False) and hasattr(investor, "mark_project_started"):
                            investor.mark_project_started(founder_id, decision)
                            self.stats["total_funding_approved"] += 1
                            self._submit_background_task(
                                executor, running_tasks, shell, "advance", shell.advance_async
                            )
                        continue

                    if msg_type == messages.EXTRA_FUNDING_REQUEST:
                        if self._global_budget_exhausted():
                            queue.append(
                                {
                                    "type": messages.EXTRA_FUNDING_DECISION,
                                    "founder_id": founder_id,
                                    "investor_id": msg["investor_id"],
                                    "decision": self._global_budget_reject_decision(),
                                }
                            )
                            continue
                        investor = next(
                            inv for inv in self.investors if inv.investor_id == msg["investor_id"]
                        )
                        decision = investor.evaluate_extra_funding(
                            msg["progress_summary"],
                            msg["profile_summary"],
                        )
                        queue.append(
                            {
                                "type": messages.EXTRA_FUNDING_DECISION,
                                "founder_id": founder_id,
                                "investor_id": investor.investor_id,
                                "decision": decision,
                            }
                        )
                        continue

                    if msg_type == messages.EXTRA_FUNDING_DECISION:
                        previous_investor_id = shell.current_investor_id
                        shell.apply_extra_funding_decision(msg["decision"])
                        if shell.status == FounderStatus.SUSPENDED:
                            self._submit_background_task(
                                executor, running_tasks, shell, "advance", shell.advance_async
                            )
                        elif shell.status == FounderStatus.DEAD and previous_investor_id:
                            investor = next(
                                (inv for inv in self.investors if inv.investor_id == previous_investor_id),
                                None,
                            )
                            if investor is not None and hasattr(investor, "mark_project_finished"):
                                investor.mark_project_finished(founder_id)
                            self.stats["total_bankruptcies"] += 1
                        continue

                    if msg_type == messages.PAPER_SUBMISSION:
                        paper = msg["paper"]

                        def do_review(paper_title, paper_text, author_id, paper_pdf_path):
                            return self.peer_review.evaluate(
                                paper_title,
                                paper_text,
                                author_id,
                                paper_pdf_path=paper_pdf_path,
                            )

                        self._submit_background_task(
                            executor,
                            running_tasks,
                            shell,
                            "review",
                            do_review,
                            paper.get("title", ""),
                            paper.get("text", ""),
                            founder_id,
                            paper.get("pdf_path"),
                        )
                        continue

                    if msg_type == messages.REVIEW_RESULT:
                        previous_investor_id = shell.current_investor_id
                        accepted = bool(msg["review_result"].accepted)
                        shell.finalize_review_result(msg["review_result"])
                        if accepted:
                            self.stats["total_papers_published"] += 1
                        else:
                            self.stats["total_papers_rejected"] += 1
                        if previous_investor_id:
                            investor = next(
                                (inv for inv in self.investors if inv.investor_id == previous_investor_id),
                                None,
                            )
                            if investor is not None and hasattr(investor, "mark_project_finished"):
                                investor.mark_project_finished(founder_id)
                        if shell.status == FounderStatus.DEAD:
                            self.stats["total_bankruptcies"] += 1
                        continue

                alive_count = sum(1 for s in self.shells if s.is_alive())
                active_or_schedulable = sum(
                    1
                    for s in self.shells
                    if s.is_alive() and s.cycle_count < self.max_cycles_per_founder
                )
                if alive_count == 0:
                    logger.info("所有 Founder 均已破产，系统终止。")
                    break
                if (
                    self._global_budget_exhausted()
                    and not running_tasks
                    and not queue
                    and all(
                        not getattr(inv, "application_queue", [])
                        and not getattr(inv, "active_projects", {})
                        for inv in self.investors
                    )
                ):
                    logger.info(
                        "系统已达到全局预算上限 $%.2f，且无在途任务，系统正常退出。",
                        self.global_budget_cap_usd,
                    )
                    break
                if (
                    active_or_schedulable == 0
                    and not running_tasks
                    and not queue
                    and all(
                        not getattr(inv, "application_queue", [])
                        and not getattr(inv, "active_projects", {})
                        for inv in self.investors
                    )
                ):
                    logger.info("所有存活 Founder 均已达到最大循环数或无待处理任务，系统正常退出。")
                    break

        self._print_final_report()


# ============================================================
#  真实 Agent 适配器（连接原始 AI Scientist 代码）
# ============================================================

def _make_real_idea_generator():
    """创建真实的 idea 生成器，调用原始 perform_ideation_temp_free。"""

    def real_generate(skill_text: str, model: str, peer_brief: str = "") -> Optional[dict]:
        import tempfile
        from ai_scientist.llm import create_client
        from ai_scientist.perform_ideation_temp_free import generate_temp_free_idea

        # 将 skill 注入到 workshop description 中
        peer_section = f"\n\n{peer_brief}\n" if peer_brief else ""
        workshop_desc = (
            f"# Research Context\n\n"
            f"As a researcher, you have the following methodological preferences:\n\n"
            f"{skill_text}\n"
            f"{peer_section}"
            f"\n# Task\n\n"
            f"Propose a novel machine learning research idea. "
            f"Focus on areas aligned with your methodological preferences."
        )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        ) as f:
            f.write(workshop_desc)
            workshop_file = f.name

        idea_file = workshop_file.replace(".md", ".json")

        try:
            client, client_model = create_client(model)
            ideas = generate_temp_free_idea(
                idea_fname=idea_file,
                client=client,
                model=client_model,
                workshop_description=workshop_desc,
                max_num_generations=1,
                num_reflections=2,  # 减少 reflection 数量以节省 token
                reload_ideas=False,
            )
            if ideas:
                return ideas[0]
            return None
        finally:
            for fpath in [workshop_file, idea_file]:
                if os.path.exists(fpath):
                    os.remove(fpath)

    return real_generate


def _make_actual_bfts_experiment_runner(
    run_root_dir: str,
    num_workers: int = 1,
    steps: int = 1,
    stage_max_iters: int = 1,
    max_debug_depth: int = 1,
    num_drafts: int = 1,
):
    def actual_run(
        idea: dict,
        gpu_ids: list,
        model: str,
        skill_text: str = "",
        founder_id: str = "unknown_founder",
        cycle_count: int = 0,
        resume: bool = False,
        checkpoint=None,
    ) -> dict:
        import subprocess

        cycle_dir = os.path.join(
            os.path.abspath(run_root_dir), founder_id, f"cycle_{cycle_count}"
        )
        os.makedirs(cycle_dir, exist_ok=True)

        experiment_idea = {
            "Name": f"{idea.get('Name', founder_id)}_tiny_actual",
            "Title": str(idea.get("Title", f"{founder_id} tiny actual run")),
            "Short Hypothesis": str(
                idea.get(
                    "Short Hypothesis",
                    "A tiny MLP on synthetic Gaussian data is enough to validate the full pipeline.",
                )
            ),
            "Related Work": str(
                idea.get(
                    "Related Work",
                    "This run is for pipeline validation with a small synthetic baseline.",
                )
            ),
            "Abstract": str(
                idea.get(
                    "Abstract",
                    "This run validates the founder ecosystem by executing a minimal AI Scientist experiment.",
                )
            ),
            "Experiments": (
                str(idea.get("Experiments", ""))
                + "\n\nImplementation note: use the provided tiny synthetic scaffold and keep the search short."
            ).strip(),
            "Risk Factors and Limitations": str(
                idea.get(
                    "Risk Factors and Limitations",
                    "This is a tiny validation run, not a publication-grade result.",
                )
            ),
            "Code": _ACTUAL_STARTER_CODE,
        }
        input_json = os.path.join(cycle_dir, "worker_input.json")
        output_json = os.path.join(cycle_dir, "worker_output.json")
        with open(input_json, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "cycle_dir": cycle_dir,
                    "model": model,
                    "experiment_idea": experiment_idea,
                    "num_workers": num_workers,
                    "steps": steps,
                    "stage_max_iters": stage_max_iters,
                    "max_debug_depth": max_debug_depth,
                    "num_drafts": num_drafts,
                    "gpu_ids": gpu_ids,
                    "resume": resume,
                    "checkpoint_present": checkpoint is not None,
                    "output_json": output_json,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

        child_env = os.environ.copy()
        child_env["CUDA_VISIBLE_DEVICES"] = ",".join(str(g) for g in gpu_ids) if gpu_ids else "-1"
        child_env["AI_SCIENTIST_SKILL"] = skill_text
        logger.info(
            "[%s] starting actual BFTS subprocess cycle=%s gpu=%s resume=%s dir=%s",
            founder_id,
            cycle_count,
            gpu_ids,
            resume,
            cycle_dir,
        )
        subprocess.run(
            [sys.executable, "-m", "ai_system.actual_bfts_worker", input_json],
            check=True,
            env=child_env,
            cwd=os.getcwd(),
        )
        with open(output_json, "r", encoding="utf-8") as f:
            return json.load(f)

    actual_run.isolated_process = True
    return actual_run


def _find_pdf_path_for_writeup(base_folder: str) -> Optional[str]:
    pdf_files = [f for f in os.listdir(base_folder) if f.endswith(".pdf")]
    reflection_pdfs = [f for f in pdf_files if "reflection" in f]
    if reflection_pdfs:
        final_pdfs = [f for f in reflection_pdfs if "final" in f.lower()]
        if final_pdfs:
            return os.path.join(base_folder, final_pdfs[0])
        numbered = []
        for name in reflection_pdfs:
            match = re.search(r"reflection[_.]?(\d+)", name)
            if match:
                numbered.append((int(match.group(1)), name))
        if numbered:
            return os.path.join(base_folder, max(numbered, key=lambda x: x[0])[1])
        return os.path.join(base_folder, reflection_pdfs[0])
    base_pdf = os.path.join(base_folder, f"{os.path.basename(base_folder)}.pdf")
    return base_pdf if os.path.exists(base_pdf) else None


def _make_full_writeup_runner():
    def full_writeup(experiment_result: dict, skill_text: str, model: str) -> dict:
        from ai_scientist.perform_plotting import aggregate_plots
        from ai_scientist.perform_icbinb_writeup import (
            gather_citations,
            perform_writeup as perform_icbinb_writeup,
        )
        from ai_scientist.perform_llm_review import load_paper

        cycle_dir = experiment_result.get("cycle_dir")
        if not cycle_dir or not os.path.isdir(cycle_dir):
            raise RuntimeError("Full writeup requires a valid cycle_dir from actual experiment output.")

        experiment_results_dir = os.path.join(cycle_dir, "logs", "0-run", "experiment_results")
        copied_results_dir = os.path.join(cycle_dir, "experiment_results")
        if os.path.exists(experiment_results_dir):
            shutil.copytree(experiment_results_dir, copied_results_dir, dirs_exist_ok=True)

        aggregate_plots(base_folder=cycle_dir, model=model)
        citations_text = gather_citations(
            cycle_dir,
            num_cite_rounds=5,
            small_model=model,
        )
        writeup_success = perform_icbinb_writeup(
            base_folder=cycle_dir,
            citations_text=citations_text,
            small_model=model,
            big_model=model,
            page_limit=4,
        )

        if os.path.exists(copied_results_dir):
            shutil.rmtree(copied_results_dir, ignore_errors=True)

        if not writeup_success:
            raise RuntimeError(f"Full PDF writeup failed in {cycle_dir}.")

        pdf_path = _find_pdf_path_for_writeup(cycle_dir)
        paper_text = load_paper(pdf_path) if pdf_path and os.path.exists(pdf_path) else ""
        text_path = os.path.join(cycle_dir, "paper_text.txt")
        if paper_text:
            with open(text_path, "w", encoding="utf-8") as f:
                f.write(paper_text)
        else:
            text_path = None

        return {
            "title": experiment_result.get("idea_title", "Untitled"),
            "text": paper_text or f"PDF writeup generated in {cycle_dir}",
            "metric": experiment_result.get("best_metric", 0.0),
            "pdf_path": pdf_path,
            "text_path": text_path,
            "cycle_dir": cycle_dir,
            "writeup_mode": "full_pdf",
        }

    return full_writeup


# ============================================================
#  CLI Entry Point
# ============================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="AI Scientist Founder Ecosystem (Debug)"
    )
    parser.add_argument(
        "--num-founders",
        type=int,
        default=2,
        help="Number of founders",
    )
    parser.add_argument(
        "--num-investors",
        type=int,
        default=1,
        help="Number of investors",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=3,
        help="Max cycles per founder",
    )
    parser.add_argument(
        "--use-real-agent",
        action="store_true",
        help="Use real AI Scientist agent (requires API keys and significant time/cost)",
    )
    parser.add_argument(
        "--actual-experiment",
        action="store_true",
        help="Backward-compatible flag. Real-agent mode now always runs the minimal actual AI Scientist BFTS experiment.",
    )
    parser.add_argument(
        "--use-llm-investor-selection",
        action="store_true",
        help="Use LLM for investor selection (otherwise debug auto-assignment)",
    )
    parser.add_argument(
        "--use-llm-investor",
        action="store_true",
        help="Use LLM fund-style investors for batch proposal review and extra funding decisions.",
    )
    parser.add_argument(
        "--mock-experiment",
        action="store_true",
        help="In real-agent mode, use mock experiment+writeup (real ideation/peer-review) "
             "for environments without GPU/torch/LaTeX.",
    )
    parser.add_argument(
        "--message-driven",
        action="store_true",
        help="Use message-driven asynchronous ecosystem clock.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="qwen3.6-plus",
        help="LLM model to use",
    )
    parser.add_argument(
        "--physical-gpu-count",
        type=int,
        default=8,
        help="Number of physical GPUs visible to the orchestrator.",
    )
    parser.add_argument(
        "--max-projects-per-round",
        type=int,
        default=3,
        help="Maximum number of proposals an investor may approve in one funding round.",
    )
    parser.add_argument(
        "--approval-amount-usd",
        type=float,
        default=INVESTOR_APPROVAL_TOKEN_USD,
        help="Initial grant tranche per approved project.",
    )
    parser.add_argument(
        "--extra-amount-usd",
        type=float,
        default=INVESTOR_EXTRA_TOKEN_USD,
        help="Extra grant tranche for approved mid-project funding requests.",
    )
    parser.add_argument(
        "--investor-total-budget-usd",
        type=float,
        default=INVESTOR_TOTAL_BUDGET_USD,
        help="Total dollar budget pool available to each investor.",
    )
    parser.add_argument(
        "--global-budget-cap-usd",
        type=float,
        default=GLOBAL_BUDGET_CAP_USD,
        help="Global ecosystem dollar spending cap across all founders.",
    )
    parser.add_argument(
        "--run-root-dir",
        type=str,
        default="ai_system_runs/orchestrator_actual",
        help="Root directory for actual experiment artifacts.",
    )
    parser.add_argument(
        "--bfts-num-workers",
        type=int,
        default=1,
        help="Worker count for minimal actual BFTS runs.",
    )
    parser.add_argument(
        "--bfts-steps",
        type=int,
        default=1,
        help="Overall step budget for minimal actual BFTS runs.",
    )
    parser.add_argument(
        "--bfts-stage-max-iters",
        type=int,
        default=1,
        help="Per-stage iteration cap for minimal actual BFTS runs.",
    )
    parser.add_argument(
        "--bfts-max-debug-depth",
        type=int,
        default=1,
        help="Max debug depth for minimal actual BFTS runs.",
    )
    parser.add_argument(
        "--bfts-num-drafts",
        type=int,
        default=1,
        help="Draft count for minimal actual BFTS runs.",
    )
    parser.add_argument(
        "--initial-review-delay-sec",
        type=int,
        default=180,
        help="Seconds the investor waits before opening the first batch review round.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )

    args = parser.parse_args()

    setup_openai_env()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    orch_cls = MessageDrivenOrchestrator if args.message_driven else Orchestrator
    orch = orch_cls(
        num_founders=args.num_founders,
        num_investors=args.num_investors,
        max_cycles_per_founder=args.max_cycles,
        use_mock_agent=not args.use_real_agent,
        use_debug_investor_selection=not args.use_llm_investor_selection,
        use_llm_investor=args.use_llm_investor,
        physical_gpu_count=args.physical_gpu_count,
        model=args.model,
        actual_experiment=args.actual_experiment,
        max_projects_per_round=args.max_projects_per_round,
        approval_amount_usd=args.approval_amount_usd,
        extra_amount_usd=args.extra_amount_usd,
        investor_total_budget_usd=args.investor_total_budget_usd,
        global_budget_cap_usd=args.global_budget_cap_usd,
        run_root_dir=args.run_root_dir,
        bfts_num_workers=args.bfts_num_workers,
        bfts_steps=args.bfts_steps,
        bfts_stage_max_iters=args.bfts_stage_max_iters,
        bfts_max_debug_depth=args.bfts_max_debug_depth,
        bfts_num_drafts=args.bfts_num_drafts,
        initial_review_delay_sec=args.initial_review_delay_sec,
        mock_experiment_in_real_agent=args.mock_experiment,
    )

    orch.run()


if __name__ == "__main__":
    from ai_system.llm_full_logger import install as _install_llm_log
    _install_llm_log()
    main()
