# 真实系统运行手册

这份文档面向真实系统测试和长时间 soak run。

它回答四类问题：

- 怎么启动真实系统
- 怎么看日志
- 怎么看 `run` 目录
- 出现异常时先查什么

相关入口：

- 主入口：[ai_system/orchestrator.py](/home/dataset-assist-0/ai_scientist/ai_system/orchestrator.py:1)
- 架构说明：[docs/current_system_architecture.md](/home/dataset-assist-0/ai_scientist/docs/current_system_architecture.md:1)

## 1. 启动前检查

先确认这几件事。

### 1.1 环境变量

仓库根目录应有 `.env`，至少包含：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `S2_API_KEY` 可选但建议有
- `HF_ENDPOINT` 可选

环境加载入口：

- [ai_system/env_setup.py](/home/dataset-assist-0/ai_scientist/ai_system/env_setup.py:1)

### 1.2 Python 环境

推荐：

```bash
source /opt/conda/etc/profile.d/conda.sh
conda activate /home/dataset-assist-0/envs/ai_scientist
unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
```

### 1.3 GPU

当前会话如果默认看不到 GPU，需要提权。

先检查：

```bash
nvidia-smi -L
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.device_count())"
```

### 1.4 关键依赖

真实系统至少需要这些：

- `tiktoken`
- `backoff`
- `torch`
- `scikit-learn`
- `yaml`

可快速检查：

```bash
python - <<'PY'
import importlib
mods = ['tiktoken','backoff','torch','sklearn','yaml']
for m in mods:
    try:
        importlib.import_module(m)
        print(m, 'OK')
    except Exception as e:
        print(m, 'ERR', e)
PY
```

## 2. 启动真实系统

## 2.1 推荐最小真实运行

这条命令适合验证真实主链是否能启动：

```bash
python -u -m ai_system.orchestrator \
  --message-driven \
  --use-real-agent \
  --actual-experiment \
  --num-founders 2 \
  --num-investors 1 \
  --max-cycles 1 \
  --model qwen3.6-plus \
  --physical-gpu-count 2 \
  --max-projects-per-round 2 \
  --approval-amount-usd 10 \
  --extra-amount-usd 15 \
  --investor-total-budget-usd 100 \
  --global-budget-cap-usd 100 \
  --run-root-dir ai_system_runs/smoke_real \
  --bfts-num-workers 1 \
  --bfts-steps 1 \
  --bfts-stage-max-iters 1 \
  --bfts-max-debug-depth 1 \
  --bfts-num-drafts 1 \
  --initial-review-delay-sec 0 \
  --log-level INFO
```

### 2.2 推荐长时间 soak run

```bash
python -u -m ai_system.orchestrator \
  --message-driven \
  --use-real-agent \
  --actual-experiment \
  --num-founders 5 \
  --num-investors 1 \
  --max-cycles 2 \
  --model qwen3.6-plus \
  --physical-gpu-count 2 \
  --max-projects-per-round 2 \
  --approval-amount-usd 10 \
  --extra-amount-usd 15 \
  --investor-total-budget-usd 100 \
  --global-budget-cap-usd 100 \
  --run-root-dir ai_system_runs/soak_run \
  --bfts-num-workers 1 \
  --bfts-steps 1 \
  --bfts-stage-max-iters 1 \
  --bfts-max-debug-depth 1 \
  --bfts-num-drafts 1 \
  --initial-review-delay-sec 180 \
  --log-level INFO 2>&1 | tee ai_system_runs/soak_run/orchestrator.log
```

### 2.3 这些参数最重要

- `--message-driven`
  必须开。当前真实系统主入口就是消息驱动 orchestrator。

- `--use-real-agent`
  打开真实 ideation / writeup / review / experiment adapter。

- `--actual-experiment`
  让 experiment 走真实最小 BFTS，而不是轻量模拟 experiment。

- `--physical-gpu-count`
  告诉 orchestrator 当前能用多少张物理卡。

- `--max-projects-per-round`
  investor 单轮最多批准多少个项目。

- `--approval-amount-usd`
  首轮 funding tranche。

- `--extra-amount-usd`
  追加 funding tranche。

- `--investor-total-budget-usd`
  单个 investor 的总美元预算池。当前单 investor 实验默认是 `$100`。

- `--global-budget-cap-usd`
  全系统累计美元消耗上限。默认也是 `$100`，用于和单 investor 总预算保持一致。

- `--initial-review-delay-sec`
  investor 首次开审前等待多久，让 founders 把 proposal 准备齐。

- `--bfts-*`
  控制最小真实实验规模。系统测试阶段建议全部压小。

## 3. 怎么看日志

## 3.1 Orchestrator 总日志

如果你用 `tee` 启动，主日志通常在：

- `ai_system_runs/<run_name>/orchestrator.log`

先看这几类关键信息：

- founder 何时 `Ideation 完成`
- investor 何时开 round
- 哪些 founder `获批 $...，GPU [...]`
- 是否出现 `预算耗尽`
- 是否出现 `Skill 已更新`
- 最终报告里的 funding / papers / bankruptcies

推荐：

```bash
tail -n 200 ai_system_runs/<run_name>/orchestrator.log
```

或者跟踪：

```bash
tail -f ai_system_runs/<run_name>/orchestrator.log
```

## 3.2 判断是否真的并发

看日志时，不要只看 founder 编号顺序，要看时间戳是否交错。

如果实现正确，并发阶段应该看到：

- 多个 founder 在接近时间内完成 ideation
- investor 一次 round 审完整个 batch
- 两个获批 founder 的 experiment 几乎同时开始
- 后台日志会交错出现，不应是严格 founder_1 跑完再 founder_2

## 3.3 actual BFTS 日志痕迹

真正进了 experiment，会在 founder 的 cycle 目录下出现：

- `idea.json`
- `bfts_config.yaml`
- `logs/*/manager.pkl`
- `logs/*/stage_*/notes/stage_progress.json`
- `logs/*/experiment_results/...`

如果这些都没有，说明根本没进 actual experiment。

## 4. 怎么看 run 目录

## 4.1 顶层结构

典型 `run_root_dir` 里应该有：

- `skill_store/`
- `profile_store/`
- `runtime_state/`
- `founder_1/`
- `founder_2/`
- ...
- `orchestrator.log` 如果你用了 `tee`

## 4.2 单个 founder 目录

通常长这样：

- `founder_k/cycle_1/`
- `founder_k/cycle_2/`

每个 `cycle_n/` 里关注：

- `idea.json`
- `bfts_config.yaml`
- `worker_input.json`
- `worker_output.json`
- `logs/`
- `paper_text.txt` 如果 writeup 成功

## 4.3 `profile_store`

这里看 founder 的客观事件履历。

重点字段：

- `funding_approved`
- `extra_funding_requested`
- `experiment_suspended`
- `cycle_resumed`
- `paper_completed`
- `bankruptcy`

如果觉得 founder 行为怪，先看 profile。

## 4.4 `skill_store`

这里看 founder 的长期 skill 演化。

重点字段：

- `skill`
- `history`

如果 founder 后续 proposal / review 风格变了，先看这里。

## 4.5 `runtime_state`

这里看挂起 / 恢复状态。

重点文件：

- `cycle_<n>_checkpoint.json`

如果 founder 因预算耗尽挂起，这里应该有 checkpoint。

## 5. 出现什么症状先查什么

下面按症状给最短排查路径。

## 5.1 founder 全都串行 ideation

先查：

1. orchestrator 是否真的走了 `--message-driven`
2. 当前代码是否还是同步调用 `start_cycle_async()`
3. 日志时间戳是否严格一段一段串行

核心文件：

- [ai_system/orchestrator.py](/home/dataset-assist-0/ai_scientist/ai_system/orchestrator.py:1)

## 5.2 investor 一轮只看见 1 个 proposal

先查：

1. `initial_review_delay_sec` 是否太小
2. `application_queue` 是否在 founder proposal 还没收齐时就被 drain
3. 日志里有没有 `opening funding round with N queued proposals`

核心文件：

- [ai_system/investor.py](/home/dataset-assist-0/ai_scientist/ai_system/investor.py:1)
- [ai_system/orchestrator.py](/home/dataset-assist-0/ai_scientist/ai_system/orchestrator.py:1)

## 5.3 获批 founder 没有 GPU 或走 CPU

这在当前正确语义下不应出现。

先查：

1. investor 的 `decision.gpu_ids`
2. investor `_gpu_ids` 是否初始化正确
3. `ResourceScheduler` pool 是否正确
4. 是否错误地允许“没卡也批准”

核心文件：

- [ai_system/investor.py](/home/dataset-assist-0/ai_scientist/ai_system/investor.py:1)
- [ai_system/resource_scheduler.py](/home/dataset-assist-0/ai_scientist/ai_system/resource_scheduler.py:1)

## 5.4 founder 没有进入 actual experiment

先查：

1. 是否传了 `--actual-experiment`
2. founder 的 cycle 目录里有没有 `idea.json` / `bfts_config.yaml`
3. 有没有 `worker_input.json` / `worker_output.json`
4. 有没有 `logs/*/manager.pkl`

如果全没有，说明没真正进 BFTS。

## 5.5 actual experiment 一进就挂

先查：

1. `worker_output.json` 是否存在
2. `logs/*/stage_*/notes/stage_progress.json`
3. `runfile.py` 生成内容
4. 环境依赖是否缺失

历史高频问题：

- 缺 `scikit-learn`
- CUDA tensor 直接 `.numpy()`
- LLM 生成代码缺 import

## 5.6 writeup 没有 PDF

先查：

1. 是否真的走 `_make_full_writeup_runner()`
2. cycle 目录是否存在实验结果和 plot
3. `perform_icbinb_writeup` 是否成功
4. `_find_pdf_path_for_writeup()` 是否找到最终 PDF

如果失败，会 fallback 到轻量 writeup。

## 5.7 review 没开始

先查：

1. founder 是否已经进入 `UNDER_REVIEW`
2. 是否发出了 `paper_submission`
3. 后台 review 任务是否被提交
4. reviewer pool 是否足够

## 5.8 founder 死掉但原因不明

先查：

1. `profile_store/founder_k.json`
2. `runtime_state/founder_k/`
3. orchestrator.log 里最后一条关于该 founder 的错误

通常死亡原因会落在：

- ideation 失败
- proposal 失败
- 追加 funding 被拒
- background task failure

## 6. 推荐排查顺序

如果一轮真实测试结果不对，建议按这个顺序查：

1. `orchestrator.log`
2. `profile_store/founder_k.json`
3. `runtime_state/founder_k/`
4. `founder_k/cycle_n/`
5. `logs/*/stage_*/notes/stage_progress.json`
6. `worker_output.json`

不要一上来就直接翻最深的 BFTS 日志。先确认外层制度和消息是否正确，再看内层实验。

## 7. 当前推荐策略

做系统测试时建议分三层：

### 第一层：mock 快回归

```bash
python -m ai_system.test_founder_integration
```

### 第二层：真实 LLM + 轻量链路

真实 ideation / proposal / review，但 experiment 不一定上 actual BFTS。

### 第三层：真实 LLM + actual BFTS + PDF + review

这才是完整 soak run。

系统出问题时，不要直接在第三层硬调，先退回上一层定位。
