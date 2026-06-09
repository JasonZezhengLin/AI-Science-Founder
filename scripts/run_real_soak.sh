#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source /opt/conda/etc/profile.d/conda.sh
conda activate /home/dataset-assist-0/envs/ai_scientist

unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY

MODEL="${MODEL:-qwen3.6-plus}"
NUM_FOUNDERS="${NUM_FOUNDERS:-5}"
NUM_INVESTORS="${NUM_INVESTORS:-1}"
MAX_CYCLES="${MAX_CYCLES:-2}"
PHYSICAL_GPU_COUNT="${PHYSICAL_GPU_COUNT:-2}"
MAX_PROJECTS_PER_ROUND="${MAX_PROJECTS_PER_ROUND:-2}"
APPROVAL_AMOUNT_USD="${APPROVAL_AMOUNT_USD:-10}"
EXTRA_AMOUNT_USD="${EXTRA_AMOUNT_USD:-15}"
INVESTOR_TOTAL_BUDGET_USD="${INVESTOR_TOTAL_BUDGET_USD:-100}"
GLOBAL_BUDGET_CAP_USD="${GLOBAL_BUDGET_CAP_USD:-100}"
BFTS_NUM_WORKERS="${BFTS_NUM_WORKERS:-1}"
BFTS_STEPS="${BFTS_STEPS:-1}"
BFTS_STAGE_MAX_ITERS="${BFTS_STAGE_MAX_ITERS:-1}"
BFTS_MAX_DEBUG_DEPTH="${BFTS_MAX_DEBUG_DEPTH:-1}"
BFTS_NUM_DRAFTS="${BFTS_NUM_DRAFTS:-1}"
INITIAL_REVIEW_DELAY_SEC="${INITIAL_REVIEW_DELAY_SEC:-180}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
RUN_DIR="${RUN_DIR:-ai_system_runs/soak_5f_parallel_formal_$(date +%Y%m%d_%H%M%S)}"

mkdir -p "$RUN_DIR"

CMD=(
  python -u -m ai_system.orchestrator
  --message-driven
  --use-real-agent
  --actual-experiment
  --use-llm-investor-selection
  --num-founders "$NUM_FOUNDERS"
  --num-investors "$NUM_INVESTORS"
  --max-cycles "$MAX_CYCLES"
  --model "$MODEL"
  --physical-gpu-count "$PHYSICAL_GPU_COUNT"
  --max-projects-per-round "$MAX_PROJECTS_PER_ROUND"
  --approval-amount-usd "$APPROVAL_AMOUNT_USD"
  --extra-amount-usd "$EXTRA_AMOUNT_USD"
  --investor-total-budget-usd "$INVESTOR_TOTAL_BUDGET_USD"
  --global-budget-cap-usd "$GLOBAL_BUDGET_CAP_USD"
  --run-root-dir "$RUN_DIR"
  --bfts-num-workers "$BFTS_NUM_WORKERS"
  --bfts-steps "$BFTS_STEPS"
  --bfts-stage-max-iters "$BFTS_STAGE_MAX_ITERS"
  --bfts-max-debug-depth "$BFTS_MAX_DEBUG_DEPTH"
  --bfts-num-drafts "$BFTS_NUM_DRAFTS"
  --initial-review-delay-sec "$INITIAL_REVIEW_DELAY_SEC"
  --log-level "$LOG_LEVEL"
)

if [[ "${1:-}" == "--foreground" ]]; then
  printf 'Run dir: %s\n' "$RUN_DIR"
  printf 'Command:'
  printf ' %q' "${CMD[@]}"
  printf '\n'
  exec "${CMD[@]}"
fi

nohup "${CMD[@]}" > "$RUN_DIR/orchestrator.log" 2>&1 &
PID=$!

cat <<EOF
Started soak run.
PID: $PID
RUN_DIR: $RUN_DIR
LOG: $RUN_DIR/orchestrator.log

Watch log:
tail -f "$RUN_DIR/orchestrator.log"
EOF
