"""Config A / Config B pipeline driver for the Founder Ecosystem run.

Config A (full)   : ideation -> actual experiment (real GPU code exec) -> writeup
                    -> PDF -> LLM peer review.  Output under runs/full_pipeline.
Config B (partial): ideation -> actual experiment only (no writeup/PDF/review).
                    Output under runs/ideation_exp.

Both configs: 2 founders, 1 round each. Real LLM via OpenRouter (deepseek-chat).

Cost is captured at the OpenAI transport layer by ai_system.openrouter_cost, which
reads OpenRouter's real usage.cost, logs full prompt/response/cost per call, keeps a
cross-run cumulative ledger, and HARD-halts at OPENROUTER_COST_CAP_USD.

Stages are driven explicitly (not via run_cycle) so every LLM call is tagged with
its stage for a precise per-stage cost breakdown.
"""

import argparse
import json
import logging
import os
import traceback
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("run_config")

# Generous *simulation* budget so the founder-ecosystem funding gate never blocks
# a run.  The only real limit is the transport-layer dollar cap.
SIM_BUDGET_USD = 1000.0

# BFTS experiment budget.  The stock demo pins everything to 1 (a single coding
# attempt with no debug pass), so a first buggy draft is never repaired and the
# run yields no experiment data / plots.  We give the coding agent a few debug
# iterations so it can converge to working code (the seed STARTER_CODE is a known
# -good tiny MLP), while still staying in stage 1 (no ablation/tuning stages) to
# bound cost.
BFTS = {"steps": 3, "stage_iters": 4, "debug_depth": 3, "debug_prob": 1.0, "num_drafts": 1}


def make_experiment_runner(founder_id, founder_dir, recorder):
    """Tunable variant of the demo's actual-experiment runner (real code exec)."""
    from ai_system.run_two_founders_actual_demo import STARTER_CODE, _to_text
    cycle_counter = {"value": 0}

    def run(idea, gpu_ids, model, **_):
        import yaml
        import numpy as np
        from ai_system.token_budget import deduct_manual
        from ai_scientist.treesearch.agent_manager import AgentManager
        from ai_scientist.treesearch.bfts_utils import edit_bfts_config_file
        from ai_scientist.treesearch.perform_experiments_bfts_with_agentmanager import (
            perform_experiments_bfts,
        )
        import re

        cycle_counter["value"] += 1
        cycle_dir = founder_dir / f"cycle_{cycle_counter['value']}"
        cycle_dir.mkdir(parents=True, exist_ok=True)
        deduct_manual(cost_usd=0.0, model=model)

        experiment_idea = {
            "Name": f"{idea.get('Name', founder_id)}_tiny_actual",
            "Title": _to_text(idea.get("Title", f"{founder_id} tiny actual run")),
            "Short Hypothesis": _to_text(idea.get(
                "Short Hypothesis",
                "A tiny MLP on synthetic Gaussian data validates the full pipeline.")),
            "Related Work": _to_text(idea.get("Related Work", "Pipeline validation.")),
            "Abstract": _to_text(idea.get(
                "Abstract",
                "Validates the founder ecosystem via a minimal AI Scientist experiment.")),
            "Experiments": (_to_text(idea.get("Experiments", "")) +
                            "\n\nImplementation note: use the provided tiny synthetic "
                            "scaffold as-is; keep the search short and make sure it runs "
                            "and saves experiment_data.npy plus a PNG plot."),
            "Risk Factors and Limitations": _to_text(idea.get(
                "Risk Factors and Limitations", "Tiny validation run, not publication-grade.")),
            "Code": STARTER_CODE,
        }
        idea_json = cycle_dir / "idea.json"
        idea_json.write_text(__import__("json").dumps(experiment_idea, indent=2, ensure_ascii=False))

        config_path = edit_bfts_config_file("bfts_config.yaml", str(cycle_dir), str(idea_json))
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        cfg["generate_report"] = False
        cfg["agent"]["num_workers"] = 1
        cfg["agent"]["steps"] = BFTS["steps"]
        cfg["agent"]["stages"]["stage1_max_iters"] = BFTS["stage_iters"]
        cfg["agent"]["stages"]["stage2_max_iters"] = 1
        cfg["agent"]["stages"]["stage3_max_iters"] = 1
        cfg["agent"]["stages"]["stage4_max_iters"] = 1
        cfg["agent"]["multi_seed_eval"]["num_seeds"] = 1
        cfg["agent"]["search"]["num_drafts"] = BFTS["num_drafts"]
        cfg["agent"]["search"]["max_debug_depth"] = BFTS["debug_depth"]
        cfg["agent"]["search"]["debug_prob"] = BFTS["debug_prob"]
        cfg["agent"]["code"]["model"] = model
        cfg["agent"]["feedback"]["model"] = model
        cfg["agent"]["vlm_feedback"]["model"] = model
        cfg["report"]["model"] = model
        with open(config_path, "w") as f:
            yaml.safe_dump(cfg, f)

        # Stay within stage 1 (no auto-advance to ablation/tuning) to bound cost.
        orig_main = AgentManager._create_next_main_stage
        orig_sub = AgentManager._create_next_substage
        AgentManager._create_next_main_stage = lambda self, cs, j: None
        AgentManager._create_next_substage = lambda self, cs, j, sf: None
        try:
            perform_experiments_bfts(config_path)
        finally:
            AgentManager._create_next_main_stage = orig_main
            AgentManager._create_next_substage = orig_sub

        sp_files = sorted(cycle_dir.glob("logs/*/stage_*/notes/stage_progress.json"))
        stage_progress = {}
        if sp_files:
            stage_progress = __import__("json").loads(sp_files[-1].read_text())
        plot_paths = [str(p.resolve()) for p in cycle_dir.glob("logs/*/experiment_results/**/*.png")]
        exp_dirs = [str(p.resolve()) for p in cycle_dir.glob("logs/*/experiment_results/*")]
        metric = 0.0
        data_paths = sorted(cycle_dir.glob("logs/*/experiment_results/*/experiment_data.npy"))
        if data_paths:
            try:
                d = np.load(data_paths[-1], allow_pickle=True).item()
                metric = float(d["synthetic_gaussian"]["metrics"]["val"][-1])
            except Exception:
                pass
        result = {
            "idea_title": experiment_idea["Title"], "best_metric": metric,
            "experiments_completed": 1,
            "status": "completed" if data_paths else "completed_no_data",
            "stage_progress": stage_progress, "plot_paths": plot_paths,
            "experiment_dirs": exp_dirs,
            "experiment_data_paths": [str(p.resolve()) for p in data_paths],
            "cycle_dir": str(cycle_dir.resolve()), "gpu_ids": gpu_ids,
        }
        recorder.log_event(founder_id, "actual_experiment_completed",
                           {"result": result, "idea_title": experiment_idea["Title"]})
        return result

    return run


def _setup_cost_guard(out_dir: Path, cap: float):
    os.environ.setdefault("OPENROUTER_COST_LEDGER", "runs/cost_ledger.jsonl")
    os.environ["OPENROUTER_COST_IOLOG"] = str(out_dir / "transport_llm_calls.jsonl")
    os.environ["OPENROUTER_COST_CAP_USD"] = str(cap)
    # Also enable the repo's full-prompt logger (TokenTracker-based) as a 2nd record.
    os.environ["LOG_LLM_FULL"] = "1"
    os.environ["LLM_FULL_LOG_PATH"] = str(out_dir / "llm_calls_full.jsonl")
    import ai_system.openrouter_cost as cg
    cg.install()
    try:
        from ai_system.llm_full_logger import install as install_full
        install_full()
    except Exception as e:
        logger.warning("llm_full_logger not installed: %s", e)
    return cg


def _stage_cost(cg, before):
    return round(cg.get_total() - before, 8)


def make_tolerant_writeup_runner(founder_id, recorder, founder_dir):
    """Full writeup (plots -> citations -> LaTeX -> PDF), but tolerant: the stock
    runner only reports success if the *final page-limit* reflection PDF exists,
    so a validly-produced intermediate reflection PDF is otherwise thrown away
    (marking the whole writeup failed and skipping review).  Here, if the base
    runner raises but a real PDF was produced, we accept that PDF as the paper."""
    import os
    import re
    from ai_system.orchestrator import _make_full_writeup_runner
    base = _make_full_writeup_runner()
    counter = {"value": 0}

    def _find_pdf(cycle_dir):
        if not cycle_dir or not os.path.isdir(cycle_dir):
            return None
        pdfs = [f for f in os.listdir(cycle_dir) if f.endswith(".pdf")]
        refl = [f for f in pdfs if "reflection" in f]
        pool = refl or pdfs
        if not pool:
            return None
        fin = [f for f in pool if "final" in f.lower()]
        if fin:
            return os.path.join(cycle_dir, fin[0])
        numbered = [(int(m.group(1)), f) for f in pool
                    if (m := re.search(r"reflection[_.]?(\d+)", f))]
        if numbered:
            return os.path.join(cycle_dir, max(numbered, key=lambda x: x[0])[1])
        return os.path.join(cycle_dir, pool[0])

    def run(experiment_result, skill_text, model):
        counter["value"] += 1
        cycle_dir = experiment_result.get("cycle_dir")
        paper, err = None, None
        try:
            paper = base(experiment_result, skill_text, model)
        except Exception as e:
            err = str(e)
            pdf = _find_pdf(cycle_dir)
            if pdf and os.path.exists(pdf):
                from ai_scientist.perform_llm_review import load_paper
                try:
                    text = load_paper(pdf)
                except Exception:
                    text = ""
                paper = {
                    "title": experiment_result.get("idea_title", "Untitled"),
                    "text": text or f"PDF generated at {pdf}",
                    "metric": experiment_result.get("best_metric", 0.0),
                    "pdf_path": pdf, "text_path": None, "cycle_dir": cycle_dir,
                    "writeup_mode": "full_pdf_intermediate_reflection",
                    "note": f"Accepted intermediate reflection PDF; strict final "
                            f"page-limit reflection did not complete: {err}",
                }
        recorder.log_llm(founder_id, "writeup",
                         {"experiment_result": experiment_result,
                          "paper": paper, "base_error": err})
        if paper:
            recorder.write_text(f"{founder_id}/cycle_{counter['value']}/paper.txt",
                                paper.get("text", ""))
            recorder.write_json(f"{founder_id}/cycle_{counter['value']}/paper_meta.json",
                                paper)
        return paper

    return run


def build_founder_shell(founder_id, gpu_id, literature_db, peer_review, recorder,
                        run_dir, model):
    from ai_system.run_two_founders_actual_demo import (
        TracedSkillManager, make_traced_proposal_builder,
    )
    from ai_system.orchestrator import _make_real_idea_generator
    from ai_system.founder_shell import FounderShell
    from ai_system.reputation import FounderProfile
    from ai_system.token_budget import TokenBudget

    founder_dir = run_dir / founder_id
    skill_mgr = TracedSkillManager(founder_id=founder_id, recorder=recorder,
                                   store_dir=str(run_dir / "skill_store"))
    profile = FounderProfile(founder_id=founder_id,
                             store_dir=str(run_dir / "profile_store"))
    budget = TokenBudget(initial_usd=SIM_BUDGET_USD)
    shell = FounderShell(
        founder_id=founder_id,
        skill_manager=skill_mgr,
        profile=profile,
        token_budget=budget,
        investors=[],
        literature_db=literature_db,
        peer_review=peer_review,
        idea_generator=_make_real_idea_generator(),
        experiment_runner=make_experiment_runner(founder_id, founder_dir, recorder),
        writeup_runner=make_tolerant_writeup_runner(founder_id, recorder, founder_dir),
        proposal_builder=make_traced_proposal_builder(recorder),
        model=model,
        skill_store_dir=str(run_dir / "skill_store"),
        profile_store_dir=str(run_dir / "profile_store"),
        resource_scheduler=None,
        gpus_per_funding=1,
    )
    shell.cycle_count = 1
    shell.gpu_ids = [gpu_id]
    return shell


def run_founder(cg, shell, config, recorder, run_dir):
    """Drive one founder through one round; return a per-stage record."""
    fid = shell.founder_id
    rec = {"founder_id": fid, "config": config, "stages": {}, "artifacts": {}}

    # ---- Stage: ideation --------------------------------------------------
    before = cg.get_total()
    cg.set_stage(f"{fid}:ideation")
    t0 = datetime.now().isoformat()
    idea = shell._run_ideation()
    rec["stages"]["ideation"] = {
        "cost_usd": _stage_cost(cg, before), "started": t0,
        "ended": datetime.now().isoformat(),
        "status": "completed" if idea else "failed",
        "idea_title": (idea or {}).get("Title", None),
    }
    if idea is None:
        rec["status"] = "failed_ideation"
        return rec
    shell.current_idea = idea
    recorder.write_json(f"{fid}/cycle_1/idea.json", idea)
    rec["artifacts"]["idea_json"] = str((run_dir / fid / "cycle_1" / "idea.json").resolve())

    # ---- Stage: experiment (real code execution on GPU) -------------------
    before = cg.get_total()
    cg.set_stage(f"{fid}:experiment")
    t0 = datetime.now().isoformat()
    try:
        exp_result = shell._run_experiment_with_budget(idea)
    except Exception as e:
        logger.error("[%s] experiment crashed: %s", fid, e)
        traceback.print_exc()
        exp_result = None
    rec["stages"]["experiment"] = {
        "cost_usd": _stage_cost(cg, before), "started": t0,
        "ended": datetime.now().isoformat(),
        "status": "completed" if exp_result else "failed",
        "best_metric": (exp_result or {}).get("best_metric"),
        "cycle_dir": (exp_result or {}).get("cycle_dir"),
    }
    recorder.write_json(f"{fid}/cycle_1/experiment_result.json", exp_result or {"status": "failed"})
    rec["artifacts"]["experiment_result_json"] = str(
        (run_dir / fid / "cycle_1" / "experiment_result.json").resolve())
    if exp_result is None:
        rec["status"] = "failed_experiment"
        return rec
    shell.last_experiment_result = exp_result

    if config == "B":
        rec["status"] = "completed_ideation_experiment"
        return rec

    # ---- Stage: writeup + PDF (Config A only) -----------------------------
    before = cg.get_total()
    cg.set_stage(f"{fid}:writeup")
    t0 = datetime.now().isoformat()
    try:
        paper = shell._run_writeup(exp_result)
    except Exception as e:
        logger.error("[%s] writeup crashed: %s", fid, e)
        traceback.print_exc()
        paper = None
    rec["stages"]["writeup_pdf"] = {
        "cost_usd": _stage_cost(cg, before), "started": t0,
        "ended": datetime.now().isoformat(),
        "status": "completed" if paper else "failed",
        "pdf_path": (paper or {}).get("pdf_path"),
        "text_path": (paper or {}).get("text_path"),
    }
    if paper is None:
        rec["status"] = "failed_writeup"
        return rec
    shell.current_paper = paper
    rec["artifacts"]["pdf_path"] = paper.get("pdf_path")
    rec["artifacts"]["paper_text_path"] = paper.get("text_path")

    # ---- Stage: peer review (Config A only) -------------------------------
    before = cg.get_total()
    cg.set_stage(f"{fid}:review")
    t0 = datetime.now().isoformat()
    review = None
    try:
        import inspect
        sig = inspect.signature(shell.peer_review.evaluate)
        kwargs = {}
        if "paper_pdf_path" in sig.parameters:
            kwargs["paper_pdf_path"] = paper.get("pdf_path")
        review = shell.peer_review.evaluate(
            paper.get("title", ""), paper.get("text", ""), fid, **kwargs)
    except Exception as e:
        logger.error("[%s] review crashed: %s", fid, e)
        traceback.print_exc()
    rec["stages"]["review"] = {
        "cost_usd": _stage_cost(cg, before), "started": t0,
        "ended": datetime.now().isoformat(),
        "status": "completed" if review else "failed",
        "accepted": getattr(review, "accepted", None),
        "overall_score": getattr(review, "overall_score", None),
    }
    if review is not None:
        recorder.write_json(f"{fid}/cycle_1/review.json", {
            "accepted": review.accepted,
            "overall_score": review.overall_score,
            "meta_review": review.meta_review,
            "reviews": review.reviews,
        })
        rec["artifacts"]["review_json"] = str(
            (run_dir / fid / "cycle_1" / "review.json").resolve())
    rec["status"] = "completed_full_pipeline"
    return rec


def main():
    from ai_system.openrouter_cost import CostCapExceeded
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", choices=["A", "B"], required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--model", default="deepseek/deepseek-chat")
    parser.add_argument("--cap", type=float, default=9.0)
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--founders", default="1,2",
                        help="Comma-separated founder indices to run this "
                             "invocation (e.g. '1' then '2'). Results merge into "
                             "an existing run_meta.json in --out-dir so the two "
                             "founders can be driven in separate processes while "
                             "sharing one accumulating output dir + cost ledger.")
    args = parser.parse_args()
    founder_indices = [int(x) for x in args.founders.split(",") if x.strip()]

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    from ai_system.env_setup import setup_openai_env
    setup_openai_env()
    cg = _setup_cost_guard(out_dir, args.cap)

    from ai_scientist.utils.token_tracker import token_tracker
    from ai_system.literature_db import get_literature_db, reset_literature_db
    from ai_system.run_two_founders_actual_demo import TraceRecorder, LlmPeerReview

    token_tracker.reset()
    reset_literature_db()
    literature_db = get_literature_db()

    recorder = TraceRecorder(out_dir)
    peer_review = LlmPeerReview(recorder=recorder, model=args.model)

    # Merge into an existing run_meta.json if a prior per-founder invocation
    # already wrote one to this out_dir (so founder_1 and founder_2 can run in
    # separate processes yet produce a single combined meta).
    meta_path = out_dir / "run_meta.json"
    existing_meta = None
    if meta_path.exists():
        try:
            existing_meta = json.loads(meta_path.read_text())
        except Exception:
            existing_meta = None

    run_start = cg.get_total()
    if existing_meta and existing_meta.get("config") == args.config:
        run_meta = existing_meta
        run_meta["cap_usd"] = args.cap
        run_start = existing_meta.get("cumulative_before_run_usd", run_start)
    else:
        run_meta = {
            "config": args.config,
            "model": args.model,
            "cap_usd": args.cap,
            "started": datetime.now().isoformat(),
            "cumulative_before_run_usd": round(run_start, 8),
            "founders": [],
        }

    halted = False
    for i, gpu in [(idx, 0) for idx in founder_indices]:
        fid = f"founder_{i}"
        # If this founder was already recorded (e.g. a prior failed attempt in
        # this out_dir), drop the stale entry so we keep exactly one per founder.
        run_meta["founders"] = [f for f in run_meta["founders"]
                                if f.get("founder_id") != fid]
        logger.info("========== %s : %s ==========", args.config, fid)
        shell = build_founder_shell(fid, gpu, literature_db, peer_review,
                                    recorder, out_dir, args.model)
        try:
            frec = run_founder(cg, shell, args.config, recorder, out_dir)
        except CostCapExceeded as e:
            logger.error("COST CAP HIT during %s: %s", fid, e)
            frec = {"founder_id": fid, "status": "halted_cost_cap", "error": str(e)}
            run_meta["founders"].append(frec)
            halted = True
            break
        frec["round_total_usd"] = round(
            sum(s.get("cost_usd", 0) for s in frec.get("stages", {}).values()), 8)
        run_meta["founders"].append(frec)
        recorder.write_json("run_meta_partial.json", run_meta)

    run_meta["ended"] = datetime.now().isoformat()
    run_meta["cumulative_after_run_usd"] = round(cg.get_total(), 8)
    run_meta["config_total_usd"] = round(cg.get_total() - run_start, 8)
    run_meta["halted_cost_cap"] = halted
    run_meta["token_tracker_summary"] = token_tracker.get_summary()
    recorder.write_json("run_meta.json", run_meta)

    print(json.dumps(run_meta, indent=2, ensure_ascii=False))
    print(f"\n[run_config] Config {args.config} done. "
          f"config_total=${run_meta['config_total_usd']:.4f} "
          f"cumulative=${run_meta['cumulative_after_run_usd']:.4f} halted={halted}")


if __name__ == "__main__":
    main()
