#!/bin/bash
# 真实验启动脚本（DSI 集群用）。
# 与 mock 版的区别：去掉 --mock-experiment，--physical-gpu-count 给真实卡数。
# 前提：集群有 GPU、装好 torch/transformers/datasets、.env 填好凭证、
#       bfts_config.yaml 用最小规模版。
set -e
cd "$(dirname "$0")"
export PYTHONPATH=.
# 从 .env 读凭证（先在 .env 填好 OPENAI_API_KEY / OPENAI_BASE_URL / S2_API_KEY）
set -a; [ -f .env ] && . ./.env; set +a
export LITERATURE_DB_PATH="ai_system/literature_store/db.json"

RUN_DIR="ai_system_runs/real"
LOG="ai_system_runs/real_console.log"
PIDFILE="ai_system_runs/real.pid"
mkdir -p "$RUN_DIR"

if [ -f "$PIDFILE" ] && kill -0 "$(cat $PIDFILE)" 2>/dev/null; then
    echo "已在运行 PID=$(cat $PIDFILE)"; exit 0
fi

NUM_FOUNDERS="${NUM_FOUNDERS:-2}"
MAX_CYCLES="${MAX_CYCLES:-2}"
MODEL="${MODEL:-qwen3.6-plus}"
GPU_COUNT="${GPU_COUNT:-2}"     # ← 真实卡数，按集群实际改

setsid python -u -m ai_system.orchestrator \
  --message-driven --use-real-agent --use-llm-investor \
  --num-founders "$NUM_FOUNDERS" --num-investors 1 --max-cycles "$MAX_CYCLES" \
  --model "$MODEL" --physical-gpu-count "$GPU_COUNT" \
  --max-projects-per-round 2 --approval-amount-usd 30 --extra-amount-usd 20 \
  --investor-total-budget-usd 300 --global-budget-cap-usd 300 \
  --run-root-dir "$RUN_DIR" --initial-review-delay-sec 25 \
  --log-level INFO >> "$LOG" 2>&1 < /dev/null &

echo $! > "$PIDFILE"
echo "已启动 PID=$(cat $PIDFILE), 日志 $LOG"
echo "注意：真实验单个要几十分钟到数小时，用 tail -f $LOG 看进度"
