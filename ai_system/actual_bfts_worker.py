import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import yaml

from ai_scientist.treesearch.agent_manager import AgentManager
from ai_scientist.treesearch.bfts_utils import edit_bfts_config_file
from ai_scientist.treesearch.perform_experiments_bfts_with_agentmanager import (
    perform_experiments_bfts,
)


def _coerce_last_float(value):
    if isinstance(value, (list, tuple)) and value:
        return _coerce_last_float(value[-1])
    if isinstance(value, np.ndarray):
        if value.size == 0:
            return None
        return _coerce_last_float(value.reshape(-1)[-1].item())
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_metric_value(data):
    if not isinstance(data, dict):
        return None

    preferred_metric_names = ("val", "validation", "accuracy", "score", "metric")
    fallback_value = None

    for dataset_payload in data.values():
        if not isinstance(dataset_payload, dict):
            continue
        metrics = dataset_payload.get("metrics")
        if not isinstance(metrics, dict):
            continue

        for metric_name in preferred_metric_names:
            if metric_name in metrics:
                value = _coerce_last_float(metrics[metric_name])
                if value is not None:
                    return value

        for metric_series in metrics.values():
            value = _coerce_last_float(metric_series)
            if value is not None and fallback_value is None:
                fallback_value = value

    return fallback_value


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m ai_system.actual_bfts_worker <input_json>")

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        payload = json.load(f)

    cycle_dir = payload["cycle_dir"]
    model = payload["model"]
    experiment_idea = payload["experiment_idea"]
    num_workers = payload["num_workers"]
    steps = payload["steps"]
    stage_max_iters = payload["stage_max_iters"]
    max_debug_depth = payload["max_debug_depth"]
    num_drafts = payload["num_drafts"]

    os.makedirs(cycle_dir, exist_ok=True)
    idea_json = os.path.join(cycle_dir, "idea.json")
    with open(idea_json, "w", encoding="utf-8") as f:
        json.dump(experiment_idea, f, indent=2, ensure_ascii=False)

    config_path = edit_bfts_config_file("bfts_config.yaml", cycle_dir, idea_json)
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    cfg["generate_report"] = False
    cfg["agent"]["num_workers"] = num_workers
    cfg["agent"]["steps"] = steps
    cfg["agent"]["stages"]["stage1_max_iters"] = stage_max_iters
    cfg["agent"]["stages"]["stage2_max_iters"] = stage_max_iters
    cfg["agent"]["stages"]["stage3_max_iters"] = stage_max_iters
    cfg["agent"]["stages"]["stage4_max_iters"] = stage_max_iters
    cfg["agent"]["multi_seed_eval"]["num_seeds"] = 1
    cfg["agent"]["search"]["num_drafts"] = num_drafts
    cfg["agent"]["search"]["max_debug_depth"] = max_debug_depth
    cfg["agent"]["search"]["debug_prob"] = 0.0
    import os as _os
    bfts_model = _os.environ.get("BFTS_MODEL", "gpt-4.1-nano")
    cfg["agent"]["code"]["model"] = bfts_model
    cfg["agent"]["feedback"]["model"] = bfts_model
    cfg["agent"]["vlm_feedback"]["model"] = bfts_model
    cfg["report"]["model"] = bfts_model
    cfg["agent"]["summary"] = {"model": bfts_model, "temp": 0.3}
    cfg["agent"]["select_node"] = {"model": bfts_model, "temp": 0.3}

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

    stage_progress_files = sorted(
        Path(cycle_dir).glob("logs/*/stage_*/notes/stage_progress.json")
    )
    stage_progress = {}
    if stage_progress_files:
        with open(stage_progress_files[-1], "r", encoding="utf-8") as f:
            stage_progress = json.load(f)

    plot_paths = [
        str(p.resolve())
        for p in Path(cycle_dir).glob("logs/*/experiment_results/**/*.png")
    ]
    experiment_dirs = [
        str(p.resolve())
        for p in Path(cycle_dir).glob("logs/*/experiment_results/*")
    ]

    metric_value = 0.0
    experiment_data_paths = sorted(
        Path(cycle_dir).glob("logs/*/experiment_results/*/experiment_data.npy")
    )
    if experiment_data_paths:
        data = np.load(experiment_data_paths[-1], allow_pickle=True).item()
        extracted_value = _extract_metric_value(data)
        if extracted_value is not None:
            metric_value = extracted_value
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
        "cycle_dir": str(Path(cycle_dir).resolve()),
        "gpu_ids": payload.get("gpu_ids", []),
        "resume": payload.get("resume", False),
        "checkpoint_present": payload.get("checkpoint_present", False),
    }
    with open(payload["output_json"], "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
