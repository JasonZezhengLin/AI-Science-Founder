"""
Founder 个人档案管理。

维护每个 Founder 的历史事件列表（客观履历）。
用于 Investor 评审参考（debug 版暂不使用，但保留接口）。
"""

import json
import os
import logging
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger(__name__)


class FounderProfile:
    """单个 Founder 的个人档案。"""

    def __init__(self, founder_id: str, store_dir: str = "ai_system/profile_store"):
        self.founder_id = founder_id
        self.store_dir = store_dir
        os.makedirs(store_dir, exist_ok=True)
        self._file = os.path.join(store_dir, f"{founder_id}.json")
        self.history: List[Dict] = self._load()

    def _load(self) -> List[Dict]:
        if os.path.exists(self._file):
            with open(self._file, "r") as f:
                return json.load(f).get("history", [])
        return []

    def _save(self):
        with open(self._file, "w") as f:
            json.dump(
                {"founder_id": self.founder_id, "history": self.history},
                f,
                indent=2,
                default=str,
            )

    def record_event(self, event_type: str, **payload):
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
        }
        event.update(payload)
        self.history.append(event)
        self._save()

    def record_funding_approved(
        self, investor_id: str, idea_title: str, token_amount: float, gpu_ids: list, cycle_count: int = None
    ):
        self.record_event(
            "funding_approved",
            investor_id=investor_id,
            idea_title=idea_title,
            allocated_token_usd=token_amount,
            allocated_gpus=gpu_ids,
            cycle_count=cycle_count,
        )

    def record_extra_funding(self, investor_id: str, amount: float, decision: str, cycle_count: int = None, checkpoint_path: str = None):
        self.record_event(
            "extra_funding_requested",
            investor_id=investor_id,
            requested_amount_usd=amount,
            decision=decision,
            cycle_count=cycle_count,
            checkpoint_path=checkpoint_path,
        )

    def record_experiment_suspended(
        self,
        reason: str,
        checkpoint_path: str,
        stage_label: str,
        extra_attempts: int,
        cycle_count: int = None,
    ):
        self.record_event(
            "experiment_suspended",
            reason=reason,
            checkpoint_path=checkpoint_path,
            stage_label=stage_label,
            extra_attempts=extra_attempts,
            cycle_count=cycle_count,
        )

    def record_cycle_resumed(self, stage_label: str, checkpoint_path: str, cycle_count: int = None):
        self.record_event(
            "cycle_resumed",
            stage_label=stage_label,
            checkpoint_path=checkpoint_path,
            cycle_count=cycle_count,
        )

    def record_paper_completed(
        self, investor_id: str, paper_title: str, accepted: bool, cycle_count: int = None, paper_id: str = None
    ):
        self.record_event(
            "paper_completed",
            investor_id=investor_id,
            paper_title=paper_title,
            accepted=accepted,
            cycle_count=cycle_count,
            paper_id=paper_id,
        )

    def record_bankruptcy(self, cycle_count: int = None, reason: str = None):
        self.record_event(
            "bankruptcy",
            cycle_count=cycle_count,
            reason=reason,
        )

    def summary(self) -> dict:
        """返回档案摘要。"""
        papers = [h for h in self.history if h["event_type"] == "paper_completed"]
        funding = [h for h in self.history if h["event_type"] == "funding_approved"]
        return {
            "founder_id": self.founder_id,
            "total_papers": len(papers),
            "accepted_papers": sum(1 for p in papers if p.get("accepted")),
            "total_funding_rounds": len(funding),
            "history_length": len(self.history),
        }
