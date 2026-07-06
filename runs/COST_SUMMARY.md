# Founder Ecosystem - Cost Summary (Config A + Config B)

*All costs are the REAL OpenRouter `usage.cost` captured at the transport layer; per-stage figures are ledger deltas from each run's `run_meta.json`, cross-checked against the summed per-call `usage.cost` in `transport_llm_calls.jsonl`.*


## Config A - `runs/full_pipeline_attempt2_noreview`

| Founder | Stage | Round | Status | LLM calls | Prompt tok | Completion tok | Cost (USD) |
|---|---|---|---|---:|---:|---:|---:|
| founder_1 | ideation | 1 | completed | 2 | 4,563 | 548 | 0.001948 |
| founder_1 | experiment | 1 | completed | 19 | 35,704 | 12,154 | 0.019611 |
| founder_1 | writeup | 1 | failed | 17 | 53,588 | 11,470 | 0.027356 |
| founder_1 | **round total** | 1 | failed_writeup | | | | **0.048915** |
| founder_2 | ideation | 1 | completed | 2 | 4,563 | 848 | 0.002215 |
| founder_2 | experiment | 1 | completed | 28 | 45,445 | 14,349 | 0.024075 |
| founder_2 | writeup | 1 | failed | 17 | 52,752 | 11,965 | 0.027529 |
| founder_2 | **round total** | 1 | failed_writeup | | | | **0.053820** |

- **Config A sum of stage costs:** $0.102735
- **Config A ledger delta (`config_total_usd`, incl. any aborted/retried attempts):** $0.102735

## Config B - `runs/ideation_exp`

| Founder | Stage | Round | Status | LLM calls | Prompt tok | Completion tok | Cost (USD) |
|---|---|---|---|---:|---:|---:|---:|
| founder_1 | ideation | 1 | completed | 2 | 3,970 | 589 | 0.001795 |
| founder_1 | experiment | 1 | completed | 31 | 50,868 | 14,585 | 0.025987 |
| founder_1 | **round total** | 1 | completed_ideation_experiment | | | | **0.027782** |
| founder_2 | ideation | 1 | completed | 2 | 4,475 | 709 | 0.002063 |
| founder_2 | experiment | 1 | completed | 25 | 41,838 | 12,213 | 0.021687 |
| founder_2 | **round total** | 1 | completed_ideation_experiment | | | | **0.023750** |

- **Config B sum of stage costs:** $0.051532
- **Config B ledger delta (`config_total_usd`, incl. any aborted/retried attempts):** $0.057994

## Grand total

- **Config A + Config B ledger deltas:** $0.160729
- **Cross-run cumulative ledger total (all runs ever, `runs/cost_ledger_total.json`):** $0.351966
- **Hard cap:** $20.00  |  **Status:** UNDER CAP