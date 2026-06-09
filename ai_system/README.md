# AI System

`ai_system/` 是这个仓库的科研生态壳层。

它把上游 `ai_scientist/` 当成科研执行内核，在外面加入：

- Founder 生命周期
- Investor 批次资助
- GPU / 预算约束
- 论文写作与同行评审
- Skill 演化
- 内部文献回流
- 消息驱动并发编排

这不是旧的 debug 占位目录了。当前主系统已经能跑：

- 原生 AI Scientist ideation
- actual BFTS experiment
- full PDF writeup
- 基于 founder pool 的 reviewer society
- suspend / resume
- batch investor rounds

相关文档：

- [docs/current_system_architecture.md](/home/dataset-assist-0/ai_scientist/docs/current_system_architecture.md:1)
- [docs/runtime_playbook.md](/home/dataset-assist-0/ai_scientist/docs/runtime_playbook.md:1)
- [founder_design.md](/home/dataset-assist-0/ai_scientist/founder_design.md:1)

## 1. 核心原则

### 1.1 Agent 与生态解耦

`ai_scientist/` 本体不知道：

- 自己有多少钱
- investor 是谁
- 是否破产
- reviewer 是谁
- 系统里还有多少竞争者

它只通过两条通道受到生态影响：

1. `skill` 注入
2. 文献检索结果

### 1.2 主体通过消息交互

主系统不是 `for founder in founders` 这种串行大循环。

当前主体是：

- Founder
- Investor
- Peer Review Society
- LiteratureDB
- MessageDrivenOrchestrator

消息类型定义在 [messages.py](/home/dataset-assist-0/ai_scientist/ai_system/messages.py:1)：

- `initial_funding_request`
- `initial_funding_decision`
- `founder_advance`
- `extra_funding_request`
- `extra_funding_decision`
- `paper_submission`
- `review_result`

### 1.3 资源是硬约束

当前系统语义是：

- GPU 归 investor 持有
- funding 批准时必须同时决定 token tranche 和 GPU 分配
- 不允许超发 GPU
- 不允许“获批但没卡，改走 CPU”
- founder 一旦拿到 GPU，会一直持有到本轮论文评审结束或 founder 死亡

## 2. 当前真实链路

当前真实主链如下：

1. Founder ideation
2. Proposal 构建
3. 提交 investor
4. Investor 批次评审
5. 获批 founder 进入 actual BFTS experiment
6. 预算耗尽则 suspend，申请 extra funding
7. experiment 完成后进入 full writeup
8. paper submission
9. founder society 随机分配 reviewer
10. 每个 reviewer 调用 AI Scientist 原生 review 函数
11. 汇总 review result
12. 更新 profile / skill / literature

当前主系统里：

- ideation：走原生 `generate_temp_free_idea(...)`
- experiment：走 actual BFTS runner
- writeup：走 full writeup runner
- review：外层负责编排 reviewer 分配，单 reviewer 审稿调用原生 `perform_review(...)`

## 3. 当前预算与资源默认值

定义在 [config.py](/home/dataset-assist-0/ai_scientist/ai_system/config.py:1)：

- founder 初始预算：`$1`
- investor 单项目初始 tranche：`$10`
- investor extra funding tranche：`$15`
- 单个 investor 总预算：`$100`
- 全系统累计美元消耗上限：`$100`

这些值是实验旋钮，不是制度定义本身。

## 4. 当前真实入口

主入口：

- [orchestrator.py](/home/dataset-assist-0/ai_scientist/ai_system/orchestrator.py:1)

典型真实运行：

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
  --bfts-num-workers 1 \
  --bfts-steps 1 \
  --bfts-stage-max-iters 1 \
  --bfts-max-debug-depth 1 \
  --bfts-num-drafts 1
```

也可以直接用脚本：

```bash
bash scripts/run_real_soak.sh
```

## 5. 主要代码结构

### 核心生命周期

- [founder_shell.py](/home/dataset-assist-0/ai_scientist/ai_system/founder_shell.py:1)
  - 单个 founder 的完整生命周期
  - funding / experiment / writeup / review / suspend / resume

- [orchestrator.py](/home/dataset-assist-0/ai_scientist/ai_system/orchestrator.py:1)
  - 消息驱动 orchestrator
  - founder 并发调度
  - investor round 打开条件
  - 全局预算 gate

### 生态角色

- [investor.py](/home/dataset-assist-0/ai_scientist/ai_system/investor.py:1)
  - `YesManInvestor`
  - `RuleBasedInvestor`
  - `LLMInvestor`
  - `FundRoleInvestor`

- [peer_review.py](/home/dataset-assist-0/ai_scientist/ai_system/peer_review.py:1)
  - `FounderReviewSociety`
  - reviewer 随机分配
  - 单 reviewer 调原生 `perform_review(...)`

### 基础设施

- [token_budget.py](/home/dataset-assist-0/ai_scientist/ai_system/token_budget.py:1)
  - 预算上下文
  - shell 层差分计费
  - `backend.query()` monkey-patch

- [resource_scheduler.py](/home/dataset-assist-0/ai_scientist/ai_system/resource_scheduler.py:1)
  - investor GPU 池
  - founder 级 GPU 分配

- [literature_db.py](/home/dataset-assist-0/ai_scientist/ai_system/literature_db.py:1)
  - 内部文献库存储
  - published / rejected / under_review 状态

- [skill_manager.py](/home/dataset-assist-0/ai_scientist/ai_system/skill_manager.py:1)
  - skill 持久化
  - feedback 驱动更新
  - history 记录

- [reputation.py](/home/dataset-assist-0/ai_scientist/ai_system/reputation.py:1)
  - founder profile
  - funding / paper / bankruptcy / suspend / resume 事件

- [trace_recorder.py](/home/dataset-assist-0/ai_scientist/ai_system/trace_recorder.py:1)
  - `outer_llm_io.jsonl`
  - `outer_events.jsonl`
  - `proposals/`
  - `reviews/`

## 6. 运行产物

真实 run 目录里，至少应该看到：

- `orchestrator.log`
- `outer_llm_io.jsonl`
- `outer_events.jsonl`
- `proposals/`
- `reviews/`
- `skill_store/`
- `profile_store/`
- `runtime_state/`

funded founder 一般还会有：

- `cycle_k/idea.json`
- `cycle_k/worker_input.json`
- `cycle_k/worker_output.json`
- `cycle_k/bfts_config.yaml`
- `cycle_k/logs/...`
- `cycle_k/latex/...`

## 7. 当前边界

下面这些是当前实现边界，不要误解：

- `ai_system` 不是上游 AI Scientist 的替代品，而是生态壳
- founder society review 是外层制度编排，不是上游原生单 reviewer 入口
- ideation 已回到原生路径，但当前默认仍是外层动态拼 `workshop_description`，不是固定外部 topic 文件
- LiteratureDB 当前仍以进程内单例为主，run 结束后若要长期分析，最好额外做 snapshot
- mock 路径仍然存在，但它只是本地无 API / 无 GPU 的测试夹具，不是主系统定义

## 8. 当前不该再做的事

下面这些口径已经过时，不要按旧 README 理解：

- “真实 experiment 还是轻量 LLM 摘要占位”
- “真实 writeup 还是纯文本占位”
- “主系统是顺序串行 founder 循环”
- “actual experiment 仍然依赖 constrained ideation wrapper”

这些都已经不是当前状态。

## 9. 推荐阅读顺序

如果第一次接手，按这个顺序看：

1. [docs/current_system_architecture.md](/home/dataset-assist-0/ai_scientist/docs/current_system_architecture.md:1)
2. [docs/runtime_playbook.md](/home/dataset-assist-0/ai_scientist/docs/runtime_playbook.md:1)
3. [founder_shell.py](/home/dataset-assist-0/ai_scientist/ai_system/founder_shell.py:1)
4. [orchestrator.py](/home/dataset-assist-0/ai_scientist/ai_system/orchestrator.py:1)
5. [investor.py](/home/dataset-assist-0/ai_scientist/ai_system/investor.py:1)
6. [peer_review.py](/home/dataset-assist-0/ai_scientist/ai_system/peer_review.py:1)

如果目标是调试 / 交接：

- [skills/founder-ecosystem-debug/SKILL.md](/home/dataset-assist-0/ai_scientist/skills/founder-ecosystem-debug/SKILL.md:1)
