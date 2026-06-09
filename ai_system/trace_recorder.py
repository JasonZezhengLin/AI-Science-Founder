import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class TraceRecorder:
    def __init__(self, run_dir: str):
        self.run_dir = Path(run_dir)
        self.trace_file = self.run_dir / "outer_llm_io.jsonl"
        self.event_file = self.run_dir / "outer_events.jsonl"
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

    def write_json(self, relative_path: str, payload: Any):
        path = self.run_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def write_text(self, relative_path: str, text: str):
        path = self.run_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def proposal_path(self, founder_id: str, cycle_count: int) -> str:
        return f"proposals/{founder_id}/cycle_{cycle_count}.json"

    def review_path(self, founder_id: str, cycle_count: int, paper_id: Optional[str] = None) -> str:
        suffix = paper_id or "paper"
        return f"reviews/{founder_id}/cycle_{cycle_count}_{suffix}.json"
