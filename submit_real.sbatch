#!/bin/bash
#SBATCH --job-name=founder_eco
#SBATCH --partition=general
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=12:00:00
#SBATCH --output=ai_system_runs/slurm_%j.out
#SBATCH --error=ai_system_runs/slurm_%j.err

# ================== DSI 集群真实验提交脚本 ==================
# 用法（在登录节点 /home/zezhenglin/<代码目录> 下）：
#   sbatch submit_real.sbatch
# 看进度：
#   tail -f ai_system_runs/slurm_<jobid>.out
# 查作业：
#   squeue -u zezhenglin
# 取消：
#   scancel <jobid>
# ==========================================================
set -e
cd "$SLURM_SUBMIT_DIR"
mkdir -p ai_system_runs

echo "===== Job $SLURM_JOB_ID on $(hostname) ====="
nvidia-smi -L || echo "WARN: no GPU visible"

# ---- Python 环境 ----
# 集群有 /opt/conda。第一次跑前请先建好环境（见部署说明 README_CLUSTER.md）：
#   conda create -y -n founder python=3.10
#   conda activate founder && pip install -r requirements.txt torch transformers datasets
source /opt/conda/etc/profile.d/conda.sh
conda activate founder

# ---- 凭证（从 .env 读）----
set -a; [ -f .env ] && . ./.env; set +a
export PYTHONPATH=.
export LITERATURE_DB_PATH="ai_system/literature_store/db.json"

# ---- 规模参数（可在 sbatch 时用 --export 覆盖，或直接改这里）----
NUM_FOUNDERS="${NUM_FOUNDERS:-2}"
MAX_CYCLES="${MAX_CYCLES:-1}"
MODEL="${MODEL:-qwen3.6-plus}"

# ---- 真实验：去掉 --mock-experiment，用真实 GPU ----
# GPU 数量由 Slurm 的 --gres=gpu:N 决定，这里 --physical-gpu-count 跟着设
python -u -m ai_system.orchestrator \
  --message-driven --use-real-agent --use-llm-investor \
  --num-founders "$NUM_FOUNDERS" --num-investors 1 --max-cycles "$MAX_CYCLES" \
  --model "$MODEL" --physical-gpu-count 1 \
  --max-projects-per-round 2 --approval-amount-usd 30 --extra-amount-usd 20 \
  --investor-total-budget-usd 300 --global-budget-cap-usd 300 \
  --run-root-dir ai_system_runs/real \
  --initial-review-delay-sec 5 \
  --log-level INFO

echo "===== Job done ====="
