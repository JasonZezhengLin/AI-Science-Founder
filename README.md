# Founder Ecosystem

Multi-agent research simulation built on SakanaAI AI-Scientist. Founder shells
generate ideas, compete for funding from an LLM investor, run real BFTS
experiments on GPU, write up papers in LaTeX, and review each other in a
double-blind peer-review society. Skills evolve from funding and review feedback.

## Layout
- `ai_system/` — orchestrator, founder shells, investor, peer review, literature DB, skill manager, BFTS worker
- `ai_scientist/` — SakanaAI framework (tree search, tools, LLM glue)
- `bfts_config.yaml` — BFTS experiment config
- `auto_chain.sbatch` — Slurm auto-resubmit chain for long runs

## Setup
1. `conda create -n founder python=3.10 && conda activate founder`
2. `pip install -r requirements.txt`
3. `cp .env.example .env` and fill in your API key
4. LaTeX: install TinyTeX, then `tlmgr install eso-pic everypage background`
5. Run: `python -m ai_system.orchestrator --message-driven --use-real-agent --use-llm-investor --num-founders 2 --num-investors 1 --max-cycles 30 --model qwen3.6-plus --physical-gpu-count 1`
