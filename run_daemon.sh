#!/bin/bash
# 断点续传守护脚本：setsid 后台长跑完整 ecosystem。
# 所有状态（literature_db / skill_store / profile_store）持久化到磁盘，
# 进程被中断后重跑本脚本会自然从已有状态续上。
set -e
cd "$(dirname "$0")"
export PYTHONPATH=.
export OPENAI_API_KEY=""
export OPENAI_BASE_URL="https://yunwu.ai/v1"
export S2_API_KEY=""
export LITERATURE_DB_PATH="ai_system/literature_store/db.json"

RUN_DIR="ai_system_runs/daemon"
LOG="ai_system_runs/daemon_console.log"
PIDFILE="ai_system_runs/daemon.pid"
mkdir -p "$RUN_DIR"

# 已在跑则不重复起
if [ -f "$PIDFILE" ] && kill -0 "$(cat $PIDFILE)" 2>/dev/null; then
    echo "已在运行 PID=$(cat $PIDFILE)"
    exit 0
fi

NUM_FOUNDERS="${NUM_FOUNDERS:-2}"
MAX_CYCLES="${MAX_CYCLES:-2}"
MODEL="${MODEL:-qwen3.6-plus}"

setsid python -u -m ai_system.orchestrator \
  --message-driven --use-real-agent --mock-experiment --use-llm-investor \
  --num-founders "$NUM_FOUNDERS" --num-investors 1 --max-cycles "$MAX_CYCLES" \
  --model "$MODEL" --physical-gpu-count 0 \
  --max-projects-per-round 2 --approval-amount-usd 30 --extra-amount-usd 20 \
  --investor-total-budget-usd 300 --global-budget-cap-usd 300 \
  --run-root-dir "$RUN_DIR" --initial-review-delay-sec 25 \
  --log-level INFO >> "$LOG" 2>&1 < /dev/null &

echo $! > "$PIDFILE"
echo "已启动 PID=$(cat $PIDFILE), 日志 $LOG"
