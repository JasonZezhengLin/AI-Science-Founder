#!/bin/bash
#SBATCH --job-name=founder_chain
#SBATCH --partition=general
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=12:00:00
#SBATCH --output=ai_system_runs/chain_%j.out
#SBATCH --error=ai_system_runs/chain_%j.err
cd "$SLURM_SUBMIT_DIR"
mkdir -p ai_system_runs
echo "===== Chain Job $SLURM_JOB_ID on $(hostname) at $(date) ====="
source /opt/conda/etc/profile.d/conda.sh
conda activate founder
export PATH="$HOME/.TinyTeX/bin/x86_64-linux:$PATH"
export TEXMFVAR="$HOME/.TinyTeX/texmf-var"
export TEXMFCONFIG="$HOME/.TinyTeX/texmf-config"
export TEXMFHOME="$HOME/.TinyTeX/texmf-home"
hash -r
echo "PDFLATEX=$(which pdflatex)"
kpsewhich pdflatex.fmt || "$HOME/.TinyTeX/bin/x86_64-linux/fmtutil-sys" --byfmt pdflatex
which pdflatex
set -a; [ -f .env ] && . ./.env; set +a
export PYTHONPATH="$HOME/.local/lib/python3.10/site-packages:."
export LITERATURE_DB_PATH="ai_system/literature_store/db.json"
CYCLES_PER_JOB="${CYCLES_PER_JOB:-30}"
NUM_FOUNDERS="${NUM_FOUNDERS:-2}"
MODEL="${MODEL:-qwen3.6-plus}"
DB="ai_system/literature_store/db.json"
papers_before=$(python3 -c "import json;print(len(json.load(open('$DB'))['papers']))" 2>/dev/null || echo 0)
resubmit_if_ok() {
  code=$?
  cd "$SLURM_SUBMIT_DIR"
  if [ -f STOP_CHAIN ]; then echo "STOP_CHAIN exists, stop"; return; fi
  papers_after=$(python3 -c "import json;print(len(json.load(open('$DB'))['papers']))" 2>/dev/null || echo 0)
  echo "papers: before=$papers_before after=$papers_after exit=$code"
  if [ "$code" -eq 143 ]; then
    echo "exit 143 (12h kill), resubmit"
    sbatch --export=ALL,CYCLES_PER_JOB=$CYCLES_PER_JOB,NUM_FOUNDERS=$NUM_FOUNDERS,MODEL=$MODEL auto_chain.sbatch
  elif [ "$code" -eq 0 ] && [ "$papers_after" -gt "$papers_before" ]; then
    echo "exit 0 with new papers, resubmit"
    sbatch --export=ALL,CYCLES_PER_JOB=$CYCLES_PER_JOB,NUM_FOUNDERS=$NUM_FOUNDERS,MODEL=$MODEL auto_chain.sbatch
  else
    echo "exit $code, no new papers or abnormal -> NOT resubmit (avoid spin)"
  fi
}
trap resubmit_if_ok EXIT
python -u -m ai_system.orchestrator \
  --message-driven --use-real-agent --use-llm-investor \
  --num-founders "$NUM_FOUNDERS" --num-investors 1 --max-cycles "$CYCLES_PER_JOB" \
  --model "$MODEL" --physical-gpu-count 1 \
  --max-projects-per-round 2 --approval-amount-usd 30 --extra-amount-usd 20 \
  --investor-total-budget-usd 2000 --global-budget-cap-usd 2000 \
  --run-root-dir ai_system_runs/real \
  --initial-review-delay-sec 5 \
  --log-level INFO
