"""
Suspension and resume state for founder experiments.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class ExperimentCheckpoint:
    founder_id: str
    cycle_count: int
    idea: Dict[str, Any]
    investor_id: Optional[str]
    gpu_ids: list[int]
    stage_label: str
    budget_spent_usd: float
    budget_remaining_usd: float
    extra_attempts: int = 0
    workspace_dir: Optional[str] = None
    journal_path: Optional[str] = None
    artifacts: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ExperimentCheckpoint":
        return cls(**payload)


@dataclass
class ResumeToken:
    checkpoint_path: str
    suspend_reason: str
    requested_extra_funding_usd: Optional[float]
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResumeToken":
        return cls(**payload)


def save_checkpoint(path: str, checkpoint: ExperimentCheckpoint):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(checkpoint.to_dict(), f, indent=2, default=str)


def load_checkpoint(path: str) -> ExperimentCheckpoint:
    with open(path, "r") as f:
        return ExperimentCheckpoint.from_dict(json.load(f))
