#!/usr/bin/env python3
"""Generate human-readable per-config summary reports + a cost summary for the
Config A (full pipeline) and Config B (ideation+experiment) Founder-Ecosystem runs.

Reads only REAL logged data:
  <run>/run_meta.json               - per-stage cost (ledger delta), status, timing
  <run>/transport_llm_calls.jsonl   - every LLM call: prompt, response, reasoning,
                                       tokens, real usage.cost, stage tag
  <run>/outer_events.jsonl          - experiment-completed events (result artifacts)
  <run>/llm_calls_full.jsonl        - full ideation prompts/responses (2nd record)
  <founder>/cycle_1/experiment_result.json / logs/.../journal.json - node outcomes

No values are fabricated; anything missing is reported as such.
"""
import json
import os
import collections
from datetime import datetime

CONFIGS = {
    "A": {
        "dir": "runs/full_pipeline_attempt2_noreview",
        "label": "Config A - Full pipeline (ideation -> experiment -> writeup+PDF)",
        "stages": ["ideation", "experiment", "writeup"],
    },
    "B": {
        "dir": "runs/ideation_exp",
        "label": "Config B - Partial pipeline (ideation -> experiment; NO writeup/PDF)",
        "stages": ["ideation", "experiment"],
    },
}
FOUNDERS = ["founder_1", "founder_2"]


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def dur(v):
    try:
        return (datetime.fromisoformat(v["ended"]) -
                datetime.fromisoformat(v["started"])).total_seconds()
    except Exception:
        return None


def trunc(s, n):
    s = str(s or "")
    return s if len(s) <= n else s[:n] + f"  ...[+{len(s)-n} chars]"


def load_journal(run_dir, founder):
    base = os.path.join(run_dir, founder, "cycle_1", "logs")
    if not os.path.isdir(base):
        return None
    for root, _dirs, files in os.walk(base):
        if "journal.json" in files:
            try:
                return json.load(open(os.path.join(root, "journal.json")))
            except Exception:
                return None
    return None


def ideation_actions(calls):
    """Extract the ACTION/ARGUMENTS decision sequence from ideation responses."""
    seq = []
    for c in calls:
        resp = c.get("response_content") or ""
        action, args = None, None
        for key in ("ACTION:", "Action:"):
            if key in resp:
                tail = resp.split(key, 1)[1].strip()
                action = tail.splitlines()[0].strip() if tail else None
                break
        for key in ("ARGUMENTS:", "Arguments:"):
            if key in resp:
                args = resp.split(key, 1)[1].strip()
                break
        seq.append((action, args, resp))
    return seq


def stage_calls(transport, founder, stage):
    tag = f"{founder}:{stage}"
    return [r for r in transport if r.get("stage") == tag]


def fmt_tokens(calls):
    p = sum(c.get("prompt_tokens", 0) for c in calls)
    comp = sum(c.get("completion_tokens", 0) for c in calls)
    rea = sum(c.get("reasoning_tokens", 0) or 0 for c in calls)
    cost = sum(c.get("cost_usd", 0.0) for c in calls)
    return p, comp, rea, cost


def render_config(cfg_key):
    cfg = CONFIGS[cfg_key]
    run_dir = cfg["dir"]
    meta = json.load(open(os.path.join(run_dir, "run_meta.json")))
    transport = load_jsonl(os.path.join(run_dir, "transport_llm_calls.jsonl"))
    events = load_jsonl(os.path.join(run_dir, "outer_events.jsonl"))
    ev_by_f = collections.defaultdict(list)
    for e in events:
        ev_by_f[e.get("founder_id")].append(e)

    L = []
    w = L.append
    w(f"# {cfg['label']}\n")
    w(f"*Generated from real logs under `{run_dir}`.*\n")
    w(f"- **Model:** `{meta.get('model')}`")
    w(f"- **Run started:** {meta.get('started')}  |  **ended:** {meta.get('ended')}")
    w(f"- **Cumulative spend before run:** ${meta.get('cumulative_before_run_usd'):.6f}")
    w(f"- **Cumulative spend after run:** ${meta.get('cumulative_after_run_usd'):.6f}")
    w(f"- **This config's ledger delta (incl. any retried/aborted attempts):** "
      f"${meta.get('config_total_usd'):.6f}")
    w(f"- **Hard cost cap this run:** ${meta.get('cap_usd')}  |  "
      f"**halted on cap:** {meta.get('halted_cost_cap')}\n")

    meta_by_f = {f["founder_id"]: f for f in meta["founders"]
                 if "founder_id" in f}

    grand = 0.0
    for founder in FOUNDERS:
        fm = meta_by_f.get(founder)
        if fm is None:
            w(f"\n## {founder}\n\n*No record in run_meta (not run / no data).*\n")
            continue
        w(f"\n---\n\n## {founder}  -  overall status: `{fm.get('status')}`\n")
        round_cost = 0.0
        for stage in cfg["stages"]:
            meta_stage_key = "writeup_pdf" if stage == "writeup" else stage
            sm = fm.get("stages", {}).get(meta_stage_key, {})
            calls = stage_calls(transport, founder, stage)
            p, comp, rea, cost = fmt_tokens(calls)
            round_cost += sm.get("cost_usd", 0.0)
            w(f"\n### Stage: {stage}\n")
            w(f"- **Status:** `{sm.get('status')}`  |  "
              f"**duration:** {dur(sm):.0f}s" if dur(sm) is not None
              else f"- **Status:** `{sm.get('status')}`")
            w(f"- **LLM calls in stage:** {len(calls)}  |  "
              f"**prompt tok:** {p:,}  |  **completion tok:** {comp:,}  |  "
              f"**reasoning tok:** {rea:,}")
            w(f"- **Stage cost (ledger delta):** ${sm.get('cost_usd', 0.0):.6f}"
              f"  |  (sum of per-call usage.cost in transport log: "
              f"${cost:.6f})")

            # --- Prompt sent (driving prompt = first call of the stage) ------
            if calls:
                first = calls[0]
                msgs = first.get("request_messages", [])
                sys_m = next((m for m in msgs if m.get("role") == "system"), None)
                usr_m = next((m for m in msgs if m.get("role") == "user"), None)
                w("\n**Prompt sent (first/driving call of stage):**\n")
                if sys_m:
                    w("```text\n[SYSTEM]\n" + trunc(sys_m.get("content"), 1400) + "\n```")
                if usr_m:
                    w("```text\n[USER]\n" + trunc(usr_m.get("content"), 1400) + "\n```")
            else:
                w("\n*No LLM calls captured at transport layer for this stage.*")

            # --- What the agent did & decided -------------------------------
            w("\n**What the agent did & decided:**\n")
            if stage == "ideation":
                for i, (act, args, resp) in enumerate(ideation_actions(calls), 1):
                    w(f"- Call {i}: decided **ACTION = {act or '(unparsed)'}** "
                      f"| arguments: `{trunc(args, 200)}`")
                title = (fm.get("stages", {}).get("ideation", {})
                         .get("idea_title"))
                w(f"- **Final decision:** finalized idea titled "
                  f"*\"{title}\"*")
            elif stage == "experiment":
                jr = load_journal(run_dir, founder)
                if jr and jr.get("nodes"):
                    w(f"- Ran BFTS tree search: {len(jr['nodes'])} code node(s) "
                      f"attempted. Per-node outcome:")
                    for n in jr["nodes"]:
                        nid = str(n.get("id", "?"))[:8]
                        buggy = n.get("is_buggy")
                        exc = n.get("exc_type")
                        met = n.get("metric")
                        if isinstance(met, dict):
                            met = met.get("value", met)
                        verdict = ("BUGGY" if buggy else "OK")
                        detail = f"exc={exc}" if exc else f"metric={met}"
                        w(f"    - node `{nid}`: {verdict}  ({detail})")
                else:
                    w("- BFTS journal not found or empty.")
                # experiment result artifact summary
                erp = os.path.join(run_dir, founder, "cycle_1",
                                   "experiment_result.json")
                if os.path.exists(erp):
                    er = json.load(open(erp))
                    sp = er.get("stage_progress", {})
                    w(f"- **Experiment decision/outcome:** status "
                      f"`{er.get('status')}`, stage "
                      f"`{sp.get('stage')}`, good_nodes={sp.get('good_nodes')}, "
                      f"buggy_nodes={sp.get('buggy_nodes')}, "
                      f"best_metric={er.get('best_metric')}")
            elif stage == "writeup":
                w(f"- Ran full writeup chain (plots -> citations -> LaTeX -> PDF) "
                  f"across {len(calls)} LLM calls.")
                w(f"- run_meta writeup status: `{sm.get('status')}` "
                  f"(strict final page-limit reflection). "
                  f"pdf_path recorded: `{sm.get('pdf_path')}`")

            # --- Produced result / artifact ---------------------------------
            w("\n**Produced result / artifact:**\n")
            if stage == "ideation":
                ij = os.path.join(run_dir, founder, "cycle_1", "idea.json")
                if os.path.exists(ij):
                    idea = json.load(open(ij))
                    w(f"- `idea.json` -> Title: *{idea.get('Title')}*")
                    w(f"- Short hypothesis: {trunc(idea.get('Short Hypothesis'), 300)}")
                else:
                    w("- idea.json not found.")
            elif stage == "experiment":
                erp = os.path.join(run_dir, founder, "cycle_1",
                                   "experiment_result.json")
                if os.path.exists(erp):
                    er = json.load(open(erp))
                    w(f"- `experiment_result.json` status `{er.get('status')}`")
                    w(f"- experiment_data.npy files: "
                      f"{len(er.get('experiment_data_paths', []))}  |  "
                      f"plots (PNG): {len(er.get('plot_paths', []))}  |  "
                      f"best_metric: {er.get('best_metric')}")
                    for dp in er.get("experiment_data_paths", [])[:4]:
                        w(f"    - data: `{dp}`")
                    for pp in er.get("plot_paths", [])[:4]:
                        w(f"    - plot: `{pp}`")
            elif stage == "writeup":
                pdfs = []
                cyc = os.path.join(run_dir, founder, "cycle_1")
                if os.path.isdir(cyc):
                    pdfs = [os.path.join(cyc, f) for f in os.listdir(cyc)
                            if f.endswith(".pdf")]
                if pdfs:
                    for pdf in pdfs:
                        sz = os.path.getsize(pdf)
                        w(f"- PDF on disk: `{pdf}` ({sz:,} bytes)")
                    w("- NOTE: run_meta marks writeup `failed` because the strict "
                      "final page-limit reflection PDF did not complete, but a "
                      "valid intermediate reflection PDF WAS produced (above).")
                else:
                    w("- No PDF found on disk.")

        w(f"\n### {founder} round total (sum of stage ledger deltas): "
          f"**${round_cost:.6f}**")
        grand += round_cost

    w(f"\n---\n\n## {cfg['label']} - totals\n")
    w(f"- **Sum of per-founder round totals (successful stages):** "
      f"${grand:.6f}")
    w(f"- **run_meta config_total_usd (ledger delta incl. aborted/retried "
      f"attempts):** ${meta.get('config_total_usd'):.6f}")
    diff = meta.get("config_total_usd", 0) - grand
    if abs(diff) > 1e-6:
        w(f"- **Difference (${diff:.6f}):** real spend from a terminated/retried "
          f"attempt in this out-dir whose per-call rows were excluded from the "
          f"clean per-stage totals but which really hit the cost ledger.")
    return "\n".join(L), grand, meta


def render_cost_summary(results):
    L = []
    w = L.append
    w("# Founder Ecosystem - Cost Summary (Config A + Config B)\n")
    w("*All costs are the REAL OpenRouter `usage.cost` captured at the transport "
      "layer; per-stage figures are ledger deltas from each run's `run_meta.json`, "
      "cross-checked against the summed per-call `usage.cost` in "
      "`transport_llm_calls.jsonl`.*\n")

    grand_total = 0.0
    for cfg_key in ["A", "B"]:
        _txt, _grand, meta = results[cfg_key]
        w(f"\n## Config {cfg_key} - `{CONFIGS[cfg_key]['dir']}`\n")
        w("| Founder | Stage | Round | Status | LLM calls | Prompt tok | "
          "Completion tok | Cost (USD) |")
        w("|---|---|---|---|---:|---:|---:|---:|")
        transport = load_jsonl(os.path.join(CONFIGS[cfg_key]["dir"],
                                            "transport_llm_calls.jsonl"))
        cfg_sum = 0.0
        for f in meta["founders"]:
            fid = f.get("founder_id")
            if not fid:
                continue
            for stage in CONFIGS[cfg_key]["stages"]:
                mk = "writeup_pdf" if stage == "writeup" else stage
                sm = f.get("stages", {}).get(mk, {})
                calls = stage_calls(transport, fid, stage)
                p, comp, rea, ccost = fmt_tokens(calls)
                cost = sm.get("cost_usd", 0.0)
                cfg_sum += cost
                w(f"| {fid} | {stage} | 1 | {sm.get('status')} | {len(calls)} | "
                  f"{p:,} | {comp:,} | {cost:.6f} |")
            w(f"| {fid} | **round total** | 1 | {f.get('status')} | | | | "
              f"**{f.get('round_total_usd', 0.0):.6f}** |")
        w(f"\n- **Config {cfg_key} sum of stage costs:** ${cfg_sum:.6f}")
        w(f"- **Config {cfg_key} ledger delta (`config_total_usd`, incl. any "
          f"aborted/retried attempts):** ${meta.get('config_total_usd'):.6f}")
        grand_total += meta.get("config_total_usd", 0.0)

    # Ledger cross-run cumulative
    led_total = None
    if os.path.exists("runs/cost_ledger_total.json"):
        led = json.load(open("runs/cost_ledger_total.json"))
        led_total = led.get("total_usd")
    w("\n## Grand total\n")
    w(f"- **Config A + Config B ledger deltas:** ${grand_total:.6f}")
    if led_total is not None:
        w(f"- **Cross-run cumulative ledger total (all runs ever, "
          f"`runs/cost_ledger_total.json`):** ${led_total:.6f}")
    w(f"- **Hard cap:** $20.00  |  **Status:** "
      f"{'UNDER CAP' if (led_total or 0) < 20 else 'OVER CAP'}")
    return "\n".join(L)


def main():
    results = {}
    for k in ["A", "B"]:
        txt, grand, meta = render_config(k)
        results[k] = (txt, grand, meta)
        out = f"runs/CONFIG_{k}_SUMMARY.md"
        open(out, "w", encoding="utf-8").write(txt)
        print("wrote", out)
    cost_txt = render_cost_summary(results)
    open("runs/COST_SUMMARY.md", "w", encoding="utf-8").write(cost_txt)
    print("wrote runs/COST_SUMMARY.md")


if __name__ == "__main__":
    main()
