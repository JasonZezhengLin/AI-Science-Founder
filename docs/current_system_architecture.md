# 当前系统架构说明

这份文档描述的是 **当前代码已经实现出来的系统**，不是理想化设计稿。

目标是让后续开发、调试、系统测试都能直接对照这份文档理解：

- 这个项目想解决什么问题
- 现在系统由哪些主体组成
- 主体之间如何通过消息交互
- GPU / token / funding / review 的语义是什么
- 哪些代码文件负责哪些职责
- 当前还有哪些明确边界和未完成项

相关文件：

- 总体设计稿：[founder_design.md](/home/dataset-assist-0/ai_scientist/founder_design.md:1)
- 外层系统目录：[ai_system](/home/dataset-assist-0/ai_scientist/ai_system)
- 上游 AI Scientist 内核：[ai_scientist](/home/dataset-assist-0/ai_scientist/ai_scientist)
- 运行手册：[docs/runtime_playbook.md](/home/dataset-assist-0/ai_scientist/docs/runtime_playbook.md:1)

## 1. 项目目标

这个项目不是单纯跑 `AI Scientist`，而是在它外面包一层科研生态系统。

核心目标是把单个科研 agent 放进一个包含：

- 基金评审
- 资源分配
- 论文写作
- 同行评审
- 文献回流
- skill 演化

的多主体系统里，观察和驱动它的长期行为。

一句话说：

> `ai_scientist/` 是科研执行内核，`ai_system/` 是科研生态壳。

## 2. 设计原则

当前实现坚持这几个原则。

### 2.1 Agent 与环境解耦

AI Scientist 本体不知道：

- 自己有多少钱
- 有没有破产风险
- 哪个 investor 在投它
- 自己是否被 reject
- 系统里还有多少竞争者

它只通过两个通道受到生态影响：

1. `skill` 文本注入
2. 文献检索结果

对应实现：

- Skill 注入：[ai_system/founder_shell.py](/home/dataset-assist-0/ai_scientist/ai_system/founder_shell.py:332)
- 上游读取 skill：[ai_scientist/treesearch/agent_manager.py](/home/dataset-assist-0/ai_scientist/ai_scientist/treesearch/agent_manager.py:1)
- 内部文献检索整合：[ai_scientist/tools/semantic_scholar.py](/home/dataset-assist-0/ai_scientist/ai_scientist/tools/semantic_scholar.py:1)

### 2.2 主体通过消息交互

系统中的主体包括：

- Founder
- Investor
- Peer Review Society
- LiteratureDB
- Orchestrator

当前实现里，消息类型集中定义在 [ai_system/messages.py](/home/dataset-assist-0/ai_scientist/ai_system/messages.py:1)：

- `initial_funding_request`
- `initial_funding_decision`
- `founder_advance`
- `extra_funding_request`
- `extra_funding_decision`
- `paper_submission`
- `review_result`

### 2.3 资源是硬约束，不允许“批准后降级”

当前系统语义已经收敛为：

- GPU 是 investor 持有的静态池
- 一轮 funding 批审时，Investor 必须同时决定批准谁、给多少 token、给哪些 GPU
- 没分到 GPU 的 proposal 这一轮必须直接打回
- 不允许“获批但改走 CPU”

这部分在 [ai_system/investor.py](/home/dataset-assist-0/ai_scientist/ai_system/investor.py:1) 和 [ai_system/resource_scheduler.py](/home/dataset-assist-0/ai_scientist/ai_system/resource_scheduler.py:1)。

## 3. 主体与职责

## 3.1 FounderShell

`FounderShell` 是单个 founder 的生命周期封装器。

主文件：

- [ai_system/founder_shell.py](/home/dataset-assist-0/ai_scientist/ai_system/founder_shell.py:1)

它负责：

- 发起 ideation
- 构建 proposal
- 接收 funding 决策
- 运行 experiment
- 预算耗尽时挂起 / 申请追加经费 / 恢复
- 运行 writeup
- 提交 peer review
- 根据结果更新 profile / skill / literature

它不负责：

- 决定 investor 如何批次开审
- 决定 reviewer 如何分配
- 管全局 founder 并发

Founder 的主要状态在 `FounderStatus` 中定义：

- `IDLE`
- `IDEATING`
- `PENDING_FUNDING`
- `EXPERIMENTING`
- `SUSPENDED`
- `WAITING_FUNDING`
- `WRITING`
- `UNDER_REVIEW`
- `DEAD`

这些状态的含义如下。

- `IDLE`
  当前没有在跑任何项目阶段，或者上一轮已经完全结束。可以开始新一轮 cycle。

- `IDEATING`
  正在生成本轮 research idea。此时还没有 proposal。

- `PENDING_FUNDING`
  idea 和 proposal 已准备好，正在等待初始 funding 决策。
  这是“项目开始前等首轮 funding”的状态。

- `EXPERIMENTING`
  已经拿到首轮 funding 和 GPU，正在跑实验阶段。

- `SUSPENDED`
  项目没有死，但已经因预算等原因被挂起，并且已经保存了 checkpoint，可恢复。

- `WAITING_FUNDING`
  项目已经挂起，并且已经向 investor 发起追加经费申请，正在等待批/拒。
  这是“项目中途等追加 funding”的状态。

- `WRITING`
  实验已结束，正在写论文。

- `UNDER_REVIEW`
  论文已经提交，正在等待同行评审结果。

- `DEAD`
  这一轮项目已经彻底失败，不能继续推进。

最容易混淆的几组区别：

- `PENDING_FUNDING` vs `WAITING_FUNDING`
  前者是项目开始前等首轮 funding，后者是项目中途挂起后等追加 funding。

- `SUSPENDED` vs `WAITING_FUNDING`
  前者强调“项目已暂停且可恢复”，后者强调“已经暂停并在等钱”。

- `WRITING` vs `UNDER_REVIEW`
  前者是论文还在写，后者是论文已经提交，在等审稿结果。

### 3.1.1 Founder 内部主链

一个 founder 的完整主链大致是：

1. `start_cycle_async()`
2. ideation
3. proposal
4. 发 `initial_funding_request`
5. 收 `initial_funding_decision`
6. `advance_async()` 进入 experiment
7. 若预算耗尽则挂起并发 `extra_funding_request`
8. 追加获批后恢复
9. experiment 完成后进入 writeup
10. 发 `paper_submission`
11. 收 `review_result`
12. skill / profile / literature 更新
13. 回到 `IDLE` 或 `DEAD`

## 3.2 Investor

主文件：

- [ai_system/investor.py](/home/dataset-assist-0/ai_scientist/ai_system/investor.py:1)

当前实现了几类 investor：

- `YesManInvestor`
- `RuleBasedInvestor`
- `LLMInvestor`
- `FundRoleInvestor`

当前系统测试主力是：

- 实验链路稳定性测试时常用 `YesManInvestor` / `RuleBasedInvestor`
- 真实基金式批审逻辑在 `FundRoleInvestor`

### 3.2.1 Investor 的核心状态

所有 batch investor 都维护：

- `application_queue`
- `active_projects`
- `max_projects_per_round`

语义是：

- `application_queue`：当前轮待审申请
- `active_projects`：本轮已批准且尚未结束的项目

### 3.2.2 Investor 的轮次语义

当前版本语义是：

1. Founder 并发准备本轮申请
2. Investor 先积累申请
3. 首轮默认等待 `180s`
4. 满足开审条件后，一次性审完整个 `application_queue`
5. 最多批准 `k` 个项目
6. 同时锁定 token 和 GPU
7. Investor 关闭本轮开审
8. 等 `active_projects` 清空后，才允许下一轮开审

这里“关闭本轮开审”的意思是：

- 不再对当前轮新到的 proposal 开新一轮评审
- 但其他未中标 founder 仍可继续准备下一轮 proposal，进入队列等待

## 3.3 Peer Review Society

主文件：

- [ai_system/peer_review.py](/home/dataset-assist-0/ai_scientist/ai_system/peer_review.py:1)

当前主路径用的是 `FounderReviewSociety`：

- 论文进入双盲 LLM 审稿
- reviewer 从 founder pool 中随机抽取
- 排除作者本人
- 当前是随机 reviewer matching，不是 skill-based matching

它输出：

- `accepted`
- `overall_score`
- `reviews`
- `meta_review`

## 3.4 LiteratureDB

主文件：

- [ai_system/literature_db.py](/home/dataset-assist-0/ai_scientist/ai_system/literature_db.py:1)

当前保存：

- `published`
- `under_review`
- `rejected`

并记录：

- `paper_text`
- `pdf_path`
- `text_path`
- `artifact_paths`

这些结果会回流到上游 `Semantic Scholar` 工具中。

## 3.5 Orchestrator

主文件：

- [ai_system/orchestrator.py](/home/dataset-assist-0/ai_scientist/ai_system/orchestrator.py:1)

它是系统主协调器，不应再被理解成“顺序 for 循环跑 founder”。

当前职责应当是：

- 初始化 founders / investors / shared infra
- 维护全局消息队列
- 启动 founder 的后台任务
- 启动 review 后台任务
- 汇总 funding / paper / bankruptcy 统计
- 执行 funding round gate

当前并行执行采用：

- `ThreadPoolExecutor` 调度外层重任务
- actual BFTS 由独立 Python 子进程运行

也就是说：

- orchestrator 协调消息
- FounderShell 维护单个 founder 状态机
- heavy work 在后台 worker 里执行

## 4. 资源与预算模型

## 4.1 Token 预算

主文件：

- [ai_system/token_budget.py](/home/dataset-assist-0/ai_scientist/ai_system/token_budget.py:1)

当前模型：

- 每个 founder 有自己的 `TokenBudget`
- 外层 LLM IO 和 founder 内部部分调用会记账
- 默认 founder 初始额度是 `$1`
- 默认单个 investor 总预算是 `$100`
- 默认全系统累计美元消耗上限是 `$100`
- 预算耗尽会抛 `BudgetExhaustedException`

全局预算达到上限后：

- 不再开放新的 funding round
- 不再批准新的 initial funding 或 extra funding
- 在途任务跑完或失败后，系统收尾退出

预算耗尽后的行为：

- experiment / writeup 阶段触发 checkpoint
- founder 进入 `SUSPENDED/WAITING_FUNDING`
- 发起 `extra_funding_request`
- 获批则恢复
- 拒绝则 `DEAD`

## 4.2 GPU

主文件：

- [ai_system/resource_scheduler.py](/home/dataset-assist-0/ai_scientist/ai_system/resource_scheduler.py:1)

当前语义：

- GPU 首先按 investor 归属
- investor 一轮批审时再按 founder 切分
- founder 一旦拿到 GPU，本轮项目结束前不释放
- 结束定义：
  - review 完成
  - 或 founder 死亡

## 4.3 挂起 / 恢复

主文件：

- [ai_system/suspension.py](/home/dataset-assist-0/ai_scientist/ai_system/suspension.py:1)

当前不是“炸了重跑”，而是有显式 checkpoint 资产：

- `ExperimentCheckpoint`
- `ResumeToken`

当前主要覆盖：

- experiment 阶段预算耗尽
- writeup 阶段预算耗尽

当前恢复语义是：

- 从上一个阶段边界恢复
- 不是恢复 Python 调用栈

## 5. 与 AI Scientist 的连接点

## 5.1 Ideation

有两条路径：

- 原始真实 ideation：`_make_real_idea_generator()`
- 当前 actual experiment 路径更稳定地使用：`_make_constrained_real_idea_generator()`

对应文件：

- [ai_system/orchestrator.py](/home/dataset-assist-0/ai_scientist/ai_system/orchestrator.py:1)
- [ai_scientist/perform_ideation_temp_free.py](/home/dataset-assist-0/ai_scientist/ai_scientist/perform_ideation_temp_free.py:1)

## 5.2 Experiment

当前有三条路径：

1. mock experiment
2. lightweight real experiment
3. actual BFTS experiment

真正的最小真实实验现在走：

- [ai_system/orchestrator.py](/home/dataset-assist-0/ai_scientist/ai_system/orchestrator.py:1) 里的 `_make_actual_bfts_experiment_runner()`
- 再调用 [ai_system/actual_bfts_worker.py](/home/dataset-assist-0/ai_scientist/ai_system/actual_bfts_worker.py:1)
- worker 里调用上游：
  - [ai_scientist/treesearch/bfts_utils.py](/home/dataset-assist-0/ai_scientist/ai_scientist/treesearch/bfts_utils.py:1)
  - [ai_scientist/treesearch/perform_experiments_bfts_with_agentmanager.py](/home/dataset-assist-0/ai_scientist/ai_scientist/treesearch/perform_experiments_bfts_with_agentmanager.py:1)

当前 actual BFTS 配置是“最小测试型”：

- `num_workers=1`
- `steps=1`
- 每个 stage `max_iters=1`
- `max_debug_depth=1`
- `num_drafts=1`

## 5.3 Writeup

当前 founder 的真实写作走完整 PDF 产线，而不是 txt 占位：

- [ai_system/orchestrator.py](/home/dataset-assist-0/ai_scientist/ai_system/orchestrator.py:1) 里的 `_make_full_writeup_runner()`

它会调用上游：

- `aggregate_plots`
- `gather_citations`
- `perform_icbinb_writeup`

最后保留：

- PDF
- paper text
- cycle 目录

## 5.4 Review

review 与 writeup 分开：

- writeup 只负责生成论文
- review 由 peer review society 负责

这符合系统制度边界。

## 6. 当前消息流

下面是当前系统的标准消息流。

### 6.1 申请 funding

1. founder 后台跑 `start_cycle_async()`
2. 产出 `initial_funding_request`
3. investor 收进 `application_queue`
4. 满足轮次 gate 后一次性 batch 审批
5. 产出若干 `initial_funding_decision`

### 6.2 获批 founder

1. founder 收到 `initial_funding_decision`
2. 激活 funding
3. 锁定 GPU
4. 后台跑 `advance_async()`
5. 进入 experiment / writeup
6. 发 `paper_submission`
7. 后台 review
8. 收 `review_result`
9. 结束本轮

### 6.3 预算耗尽 founder

1. experiment / writeup 抛预算耗尽
2. founder 落 checkpoint
3. 发 `extra_funding_request`
4. investor 批/拒
5. 批准则恢复
6. 拒绝则 founder 死亡

## 7. 代码结构总览

## 7.1 `ai_system/`

### 核心控制

- [orchestrator.py](/home/dataset-assist-0/ai_scientist/ai_system/orchestrator.py:1)
- [messages.py](/home/dataset-assist-0/ai_scientist/ai_system/messages.py:1)
- [founder_shell.py](/home/dataset-assist-0/ai_scientist/ai_system/founder_shell.py:1)

### 资源 / 预算 / 状态

- [token_budget.py](/home/dataset-assist-0/ai_scientist/ai_system/token_budget.py:1)
- [resource_scheduler.py](/home/dataset-assist-0/ai_scientist/ai_system/resource_scheduler.py:1)
- [suspension.py](/home/dataset-assist-0/ai_scientist/ai_system/suspension.py:1)

### 生态主体

- [investor.py](/home/dataset-assist-0/ai_scientist/ai_system/investor.py:1)
- [peer_review.py](/home/dataset-assist-0/ai_scientist/ai_system/peer_review.py:1)
- [literature_db.py](/home/dataset-assist-0/ai_scientist/ai_system/literature_db.py:1)

### Founder 长期记忆

- [skill_manager.py](/home/dataset-assist-0/ai_scientist/ai_system/skill_manager.py:1)
- [reputation.py](/home/dataset-assist-0/ai_scientist/ai_system/reputation.py:1)

### 真实适配器 / 测试

- [actual_bfts_worker.py](/home/dataset-assist-0/ai_scientist/ai_system/actual_bfts_worker.py:1)
- [run_two_founders_actual_demo.py](/home/dataset-assist-0/ai_scientist/ai_system/run_two_founders_actual_demo.py:1)
- [test_founder_integration.py](/home/dataset-assist-0/ai_scientist/ai_system/test_founder_integration.py:1)
- [test_founder_real_llm.py](/home/dataset-assist-0/ai_scientist/ai_system/test_founder_real_llm.py:1)

## 7.2 `ai_scientist/`

### 上游主能力

- [perform_ideation_temp_free.py](/home/dataset-assist-0/ai_scientist/ai_scientist/perform_ideation_temp_free.py:1)
- [perform_icbinb_writeup.py](/home/dataset-assist-0/ai_scientist/ai_scientist/perform_icbinb_writeup.py:1)
- [perform_llm_review.py](/home/dataset-assist-0/ai_scientist/ai_scientist/perform_llm_review.py:1)
- [perform_plotting.py](/home/dataset-assist-0/ai_scientist/ai_scientist/perform_plotting.py:1)
- [llm.py](/home/dataset-assist-0/ai_scientist/ai_scientist/llm.py:1)

### BFTS 实验内核

- [treesearch/agent_manager.py](/home/dataset-assist-0/ai_scientist/ai_scientist/treesearch/agent_manager.py:1)
- [treesearch/parallel_agent.py](/home/dataset-assist-0/ai_scientist/ai_scientist/treesearch/parallel_agent.py:1)
- [treesearch/perform_experiments_bfts_with_agentmanager.py](/home/dataset-assist-0/ai_scientist/ai_scientist/treesearch/perform_experiments_bfts_with_agentmanager.py:1)
- [treesearch/journal.py](/home/dataset-assist-0/ai_scientist/ai_scientist/treesearch/journal.py:1)

## 8. 当前已实现与未实现

## 8.1 已实现

- Founder / Investor / Review / Literature 分层
- 消息协议收口
- founder 生命周期状态机
- 批次 investor
- token 预算与追加经费
- checkpoint suspend / resume
- 内部文献回流
- PDF writeup
- founder society 双盲 LLM 审稿
- actual BFTS 最小实验接入
- 重任务并发调度

## 8.2 当前明确边界

- reviewer 匹配目前还是随机，不是 skill-based
- founder 死亡后自动补位还没做
- investor 首轮等待是固定 `180s`，不是更智能的“队列稳定检测”
- 当前 outer 并发用线程池；实验本体并发靠子进程
- 目前 batch investor 的一人一张卡分配策略仍然是简化版，不是更复杂的多卡优化器

## 8.3 当前最重要的系统约束

为了理解和测试现在的系统，下面几条必须当作当前事实：

1. **多主体必须并发准备，不允许 founder 串行排队做 ideation / proposal**
2. **Investor 一轮只审一次，必须看到该轮已收集的全部 proposal**
3. **Investor 一旦进入 active round，就不再开放新审批，直到 `active_projects` 清空**
4. **没分到 GPU 的 proposal 该轮直接 reject**
5. **获批 founder 的实验彼此不应共享全局环境**
6. **writeup 和 review 是两个独立制度环节**

## 9. 建议的阅读顺序

如果第一次接手这个系统，建议这样读：

1. [founder_design.md](/home/dataset-assist-0/ai_scientist/founder_design.md:1)
2. [docs/current_system_architecture.md](/home/dataset-assist-0/ai_scientist/docs/current_system_architecture.md:1)
3. [ai_system/orchestrator.py](/home/dataset-assist-0/ai_scientist/ai_system/orchestrator.py:1)
4. [ai_system/founder_shell.py](/home/dataset-assist-0/ai_scientist/ai_system/founder_shell.py:1)
5. [ai_system/investor.py](/home/dataset-assist-0/ai_scientist/ai_system/investor.py:1)
6. [ai_system/peer_review.py](/home/dataset-assist-0/ai_scientist/ai_system/peer_review.py:1)
7. [ai_system/test_founder_integration.py](/home/dataset-assist-0/ai_scientist/ai_system/test_founder_integration.py:1)

## 10. 面向后续系统测试的建议

后续大规模测试建议默认以 `MessageDrivenOrchestrator` 为唯一主入口，不要再把旧的顺序 debug 路径当成真实系统。

建议测试分三层：

1. mock 快速回归
2. 真实 LLM + 轻量 experiment 回归
3. 真实 LLM + actual BFTS + PDF + review 的长时 soak

所有新的系统性 bug，都应该优先问这几个问题：

- 它是消息协议问题，还是 founder 内部状态问题？
- 它是资源 gate 错了，还是执行并发模型错了？
- 它会不会让 investor 看不到正确的一轮 proposal 全量？
- 它会不会让获批 founder 实际没拿到承诺资源？

这四个问题基本覆盖了当前系统最关键的结构性风险。
