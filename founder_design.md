# AI Scientist → Founder 科研生态系统：完整技术设计文档

> 文档分工：
> - 当前代码已经实现到什么程度：看 [docs/current_system_architecture.md](/home/dataset-assist-0/ai_scientist/docs/current_system_architecture.md:1)
> - 怎么启动和排查真实系统功能实现：看 [docs/runtime_playbook.md](/home/dataset-assist-0/ai_scientist/docs/runtime_playbook.md:1)
> - 系统目标和如何分析调优系统：看 [skills/founder-ecosystem-debug/SKILL.md](/home/dataset-assist-0/ai_scientist/skills/founder-ecosystem-debug/SKILL.md)
> - `ai_system/` 目录和主入口速览：看 [ai_system/README.md](/home/dataset-assist-0/ai_scientist/ai_system/README.md:1)
> - 本文档保留“制度设计 / 目标机制 / 理想语义”，不负责逐项描述当前实现细节

## 目录

1. [系统图景](#1-系统图景)
2. [核心角色](#2-核心角色)
3. [资源模型](#3-资源模型)
4. [三大模块与数据契约](#4-三大模块与数据契约)
5. [系统全生命周期](#5-系统全生命周期)
6. [Skill 演化机制](#6-skill-演化机制)
7. [文献库与检索工具](#7-文献库与检索工具)
8. [同行评审](#8-同行评审)
9. [Founder 个人档案](#9-founder-个人档案)
10. [实现方案与代码改动](#10-实现方案与代码改动)
11. [运行终点与实验配置](#11-运行终点与实验配置)

---

## 1. 系统图景

本系统构建了一个**科研生态仿真环境**，模拟真实科研系统中“基金分配—科研执行—论文发表—文献积累—声誉更新—再申请基金”的闭环。系统中的 AI Scientist 不再独立运行，而是作为 **Founder** 嵌入一个有资源约束、同行竞争和反馈回路的多角色生态网络中。

### 1.1 总体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                     Research Ecosystem                           │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐       ┌──────────┐   │
│  │Investor A│  │Investor B│  │Investor C│  ...  │Investor M│   │
│  │方向: NLP │  │方向: 理论 │  │方向: CV  │       │方向: ... │   │
│  │Token:50M │  │Token:30M │  │Token:40M │       │Token:... │   │
│  │GPU: [0,1]│  │GPU: [2,3]│  │GPU:[4,5,6│       │GPU: ...  │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘       └────┬─────┘   │
│       │              │              │                   │         │
│  ┌────┴──────────────┴──────────────┴───────────────────┴────┐   │
│  │                     Founder Pool                           │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐                │   │
│  │  │Founder 1 │  │Founder 2 │  │Founder N │                │   │
│  │  │skill_1   │  │skill_2   │  │skill_N   │                │   │
│  │  │profile_1 │  │profile_2 │  │profile_N │                │   │
│  │  └──────────┘  └──────────┘  └──────────┘                │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                Shared Infrastructure                       │    │
│  │  ┌────────────────┐  ┌────────────────┐                  │    │
│  │  │ LiteratureDB   │  │ PeerReview     │                  │    │
│  │  │ (已发表+未发表) │  │ System         │                  │    │
│  │  └────────────────┘  └────────────────┘                  │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

### 1.2 批次运行模型

系统按**异步批次**推进。理解这个模型的关键是抓住两条独立的时钟：

- **Founder 时钟**：写完论文 → 审稿 → 更新 skill → **立刻重新 ideation**，不等任何人。
- **Investor 时钟**：上一轮资助的所有 Founder 全部走完全流程（论文评审结束）或项目失败后 → **才重新开放评审**。

两条时钟异步运转，各 Investor 之间也异步。下面用一个具体例子走一遍完整流程。

**设定**：4 个 Founder（F1, F2, F3, F4），2 个 Investor（I1: GPU [0,1], 偏好 NLP；I2: GPU [2,3], 偏好 CV）。所有 Founder 初始 token 相同。

---

**阶段 ①：初始 ideation 与投递**

四个 Founder 各自独立做 ideation，生成 idea 后各自分析 Investor 列表，自行决定投谁：

```
F1 ideation → idea "A"（NLP 方向）→ 比较 I1(NLP) vs I2(CV) → 投 I1
F2 ideation → idea "B"（NLP 方向）→ 比较 I1(NLP) vs I2(CV) → 投 I1
F3 ideation → idea "C"（CV 方向） → 比较 I1(NLP) vs I2(CV) → 投 I2
F4 ideation → idea "D"（CV 方向） → 比较 I1(NLP) vs I2(CV) → 投 I2
```

结果：I1 收到 F1、F2 的申请；I2 收到 F3、F4 的申请。

---

**阶段 ②：Investor 审批（每轮一次性决策，获批项目全部并行启动）**

```
I1 审阅队列 [F1, F2]：
  GPU 持有量 = 2
  F1: idea A 质量高、方向匹配 NLP
  F2: idea B 质量高、方向匹配 NLP
  → 两个都批准！
  → GPU 分配方案：F1 拿 [0]，F2 拿 [1]（每人 1 个，总和 = 2 = 持有量）
  → Token 分配：F1=$500，F2=$400（根据项目规模和评估得分）
  → F1、F2 同时开始实验（并行！）

I2 审阅队列 [F3, F4]：
  GPU 持有量 = 2
  F3: idea C 质量高、方向匹配 CV
  F4: idea D 质量一般、创新不足
  → 只批准 F3，拒绝 F4
  → GPU 分配：F3 独享 [2,3]
  → Token 分配：F3=$600
  → F3 开始实验；F4 被拒

I1、I2 本轮审批结束，各自进入"等待本轮项目全部完成"状态。
```

**GPU 分配规则**：Investor 单轮批准的 GPU 分配总和不能超过自己持有的 GPU 数。方案由 Investor（LLM）自行决定——可以是 1 人拿全部 GPU，也可以多人各拿一部分。

---

**阶段 ③：异步并行期——实验、重 ideation、再投递同时发生**

这是系统最核心的状态。不同 Founder 处于不同阶段，进度各不相同：

```
════════════════════════════════════════════════════════════════════
      F1             F2             F3             F4
════════════════════════════════════════════════════════════════════
  I1批准         I1批准         I2批准          被I2拒绝
  GPU[0]         GPU[1]         GPU[2,3]        剩余token=$15
  token=$500     token=$400     token=$600
  │              │              │               │
  │ 实验         │ 实验          │ 实验           │ 立刻重新ideation
  │ ████████     │ ████████████ │ ██████         │ → idea "E"
  │ ████████     │ ████████████ │ ██████         │ → 分析Investor
  │ ████████     │ ████████████ │ ██████         │ → 选投 I1
  │ ████████     │ ████████████ │ ██████         │ → 申请入I1队列
  │ ████████     │ ████████████ │ ██████         │
  │ 实验完成!    │ ████████████ │ ██████         │ (等待I1下次开放)
  │ → 写论文     │ ████████████ │ ██████         │
  │ → peer review│ ████████████ │ ██████         │
  │ → 审稿(接收) │ ████████████ │ ██████         │
  │ → skill更新  │ ████████████ │ ██████         │
  │ → 档案更新   │ ████████████ │ ██████         │
  │ → 立刻重     │ ████████████ │ ██████         │
  │   ideation   │ ████████████ │ ██████         │
  │ → idea "F"   │ ████████████ │ 实验完成!      │
  │ → 选投 I2    │ ████████████ │ → 写论文       │
  │              │ ████████████ │ → peer review  │
  │ (等I2开放)   │ ████████████ │ → 审稿(接收)   │
  │              │ 实验完成!    │ → skill更新    │
  │              │ → 写论文     │ → 档案更新     │
  │              │ → peer review│ → 立刻重       │
  │              │ → 审稿(被拒) │   ideation     │
  │              │ → skill更新  │ → idea "G"     │
  │              │ → 档案更新   │ → 选投 I1      │
  │              │ → 立刻重     │               │
  │              │   ideation   │ (等I1开放)     │
  │              │ → idea "H"   │               │
  │              │ → 选投 I2    │               │
  │              │              │               │
  ▼              ▼              ▼               ▼
════════════════════════════════════════════════════════════════════
```

三个获批 Founder（F1、F2、F3）的实验**同时并行运行**——F1 用 GPU 0，F2 用 GPU 1，F3 用 GPU 2,3。F1 最先跑完（实验规模小或收敛快），F2 跑得最久（实验规模大）。

被拒的 F4 没有等待，立刻用剩余 token 重新 ideation 并改投 I1。

---

**阶段 ④：Investor 重新开放评审**

I1 等待的条件：上一轮资助的 Founder（F1、F2）是否都已完成全流程或失败？

```
F1: 实验完成 → 写论文 → peer review → skill更新 ✓
F2: 实验完成 → 写论文 → peer review → skill更新 ✓
→ I1 条件满足！开放评审
```

I2 等待的条件：上一轮资助的 Founder（F3）是否已完成全流程或失败？

```
F3: 实验完成 → 写论文 → peer review → skill更新 ✓
→ I2 条件满足！开放评审
```

与此同时，已完成的 Founder 会立刻重新 ideation 并继续向各 Investor 投递，因此当 Investor 重新开放评审时，申请队列里通常已经攒好一批新 idea：

```
I1 的申请队列:                     I2 的申请队列:
  F4 的 idea "E" (被拒后重做的)       F1 的 idea "F" (第一轮完成后重做的)
  F3 的 idea "G" (第一轮完成后重做的)   F2 的 idea "H" (第一轮完成后重做的)
```

I1、I2 各自独立进行新一轮审批，分配 GPU 和 token，获批项目并行启动，进入下一轮循环。

---

**这个例子展示的关键机制**：

1. **同一 Investor 获批的项目全部并行启动**：F1 和 F2 由 I1 同时批准，各自拿到 1 个 GPU，实验同时跑。不存在"等 F1 释放 GPU 才轮到 F2"——审批时 GPU 就一次性分完了。

2. **GPU 分配由 Investor 在审批时决定**：I1 有 2 个 GPU，批准了 2 个人，每人 1 个。如果 I1 只批准 F1，F1 可以独占 2 个 GPU。分配总和不超过持有量。

3. **被拒 Founder 立刻重 ideation**：F4 不等任何事，立即用剩余 token 生成新 idea、改投其他 Investor。

4. **Founder 写完论文不等待，立刻重 ideation**：F1 完成后马上生成新 idea 投出去，此时 I2 可能还没开放——没关系，申请在 I2 的队列里攒着。

5. **Investor 异步开放**：I1 和 I2 各自独立等待自己的项目完成或失败，开放时间点可能不同。

6. **交叉投递**：F1 第一轮投 I1（NLP），第二轮投 I2（CV）——Founder 每次重新评估方向匹配后决定。

7. **破产触发**：如果 F4 重 ideation 阶段 token 耗尽且从未获得资助 → DEAD → 系统创建新 Founder F5 补位。

### 1.3 完整链路

```
Founder ideation
  → 生成 idea + 选择 Investor + 提交申请
  → Investor 评审（根据 idea 质量 + Founder 历史发表记录 + 方向匹配度）
  → 获批: 分配 token 预算 + GPU
      → Founder 进入实验 & 写作阶段
          → token 耗尽时可申请追加经费（复活机会）
          → 追加被拒 → Founder 破产（标记死亡，新 Founder 替换加入）
          → 实验完成 → 生成论文
      → 论文进入 Peer Review（双盲，3 个审稿人，随机分配，不审自己的）
      → 接收/拒稿决定
  → 被拒: Founder 用剩余 token 重新进入 ideation
  → 更新 LiteratureDB（接收→已发表，拒稿→未发表）
  → 更新 Founder 个人档案（历史记录；idea 申请失败不记录）
  → 更新 Founder Skill（吸收评审意见 + Investor 评语 + 追加经费评语）
  → Founder 立即重新进入 ideation
  → 破产 Founder 被清除，新初始状态 Founder 加入池中
```

---

## 2. 核心角色

### 2.1 Founder（科研人员）

Founder 是全流程科研 Agent。其内部执行模块即为现有的 AI Scientist 系统，**Agent 本身不知道自己处于一个科研生态中**——它不知道经费、peer review、声誉系统的存在。

**Founder 的属性**：

| 属性 | 说明 | 管理模块 |
|------|------|---------|
| `founder_id` | 唯一标识 | 系统分配 |
| `skill` | 文本块，描述科研风格和方法论偏好，初始为模板 | `skill.py` |
| `profile` | 历史记录列表，每条记录含事件类型、Investor、资源量、结果 | `reputation.py` |
| `token_budget` | 当前可用 token 额度（USD），各阶段累计消耗 | `token_budget.py` |
| `status` | `ideating` / `experimenting` / `reviewing` / `dead` | 系统状态机 |

**Founder 的 Agent 组成部分**（复用现有代码）：

```
现有模块 → 在本系统中的角色:

  perform_ideation_temp_free.py  → Module 1: ideation（产出 idea.json）
  AgentManager.run()             → Module 2: 实验执行（BFTS 四阶段流水线）
  ParallelAgent                  → 实验内的并行代码生成与执行
  perform_writeup.py             → Module 2: 论文写作
  perform_llm_review.py          → Module 3: peer review 中审稿人的评审逻辑

Agent 核心不变（零改动，除特定注入点）:
  ParallelAgent._draft/_debug/_improve → 代码生成
  backend.query()                      → 所有 LLM 调用瓶颈
  Journal / Node                       → 实验树追踪
  AgentManager.run()                   → 阶段编排（通过异常传播支持挂起/恢复）
```

### 2.2 Investor（基金/资助机构）

Investor 模拟现实中的科研基金，拥有独立的资源和资助偏好。

**Investor 的属性**：

| 属性 | 说明 |
|------|------|
| `investor_id` | 唯一标识 |
| `direction` | 自然语言描述的研究方向偏好，如“偏好深度学习和 NLP 应用研究，关注实际效果提升” |
| `token_pool` | 该 Investor 持有的 token 预算池（USD），分配给获批的 Founder |
| `gpu_ids` | **静态分配**的 GPU 列表，如 `[0, 1, 2]` |
| `active_projects` | 当前进行中的项目列表；未全部结束前不开放下一轮初审 |
| `application_queue` | 截至当前评审时刻累计收到的申请书队列 |

**Investor 的 LLM 决策**（通过 prompt 引导）：

1. **审批初始申请**：评估 idea 质量 + Founder 历史档案 + 方向匹配度 + 当前资源余量
2. **审批追加申请**：评估当前项目进度 + 已有结果的 promise + Founder 历史

**GPU 分配规则**：
- Investor 持有的 GPU 是静态固定的（系统初始化时分配）
- Investor 在单轮审批时，为本轮获批项目一次性划分 GPU
- 单轮分配出去的 GPU 总和**严禁超过** Investor 持有量
- 未在本轮获批的申请一律打回，不存在“获批但排队等 GPU”的状态
- Founder 一旦拿到 GPU，就一直持有到该项目完整结束（论文写完、评审结束）或项目死亡

### 2.3 文献库

共享的学术知识库：
- **已发表论文**：通过 Peer Review 的论文
- **未发表论文**：被拒稿的论文

**Agent 访问方式**：通过 `SearchSemanticScholar` 工具。每次调用时，工具同时检索 Semantic Scholar（外部）和 LiteratureDB（内部），在返回结果中明确区分来源标注。详见 [第 7 章](#7-文献库与检索工具)。

### 2.4 Founder 的外部封装层（Founder Shell）

Founder 并非一个单一的 Agent，而是 **外部封装层（Shell）+ 内部科研 Agent** 的组合。理解这一分层是整个系统设计的关键。

**为什么需要分层**：内部 Agent 是一个"盲"科学家——它只知道做科研，不知道经费、审稿、竞争的存在。而 Founder 作为一个生态参与者，需要在合适的时间点介入外部信息（如 Investor 列表、个人履历、评审反馈），做出生态层面的决策（如选 Investor、申请追加经费、更新 skill）。这些决策需要 LLM 调用，但它们和 Agent 内部的科研推理是**不同性质**的——前者可见外部环境，后者不可见。

#### 分层架构

```
┌──────────────────────────────────────────────────────────┐
│                 Founder Shell（外部封装层）                │
│                                                          │
│  可访问的信息:                                            │
│    - Investor 列表及方向描述                              │
│    - Founder 个人档案（客观履历）                          │
│    - 当前 token_budget 状态                              │
│    - Peer review 反馈                                    │
│    - Investor 审批意见                                   │
│                                                          │
│  Shell 自身的 LLM 调用（与 Agent 无关）:                   │
│    ① 申请书格式化 + Investor 选择                        │
│    ② Skill 文本更新（吸收各类反馈）                       │
│    ③ 追加经费申请书构建（汇总实验进度）                    │
│                                                          │
│  对 Agent 的注入（仅两条通道）:                            │
│    通道 A: Skill 文本 → 注入系统提示词                    │
│    通道 B: 文献检索工具 → Agent 主动调用                  │
│                                                          │
│  Shell 负责的纯逻辑（无 LLM 调用）:                       │
│    - Token 预算扣减监控                                   │
│    - 实验挂起/恢复编排                                    │
│    - GPU 分配申请                                        │
│    - 档案记录更新                                        │
└──────────┬───────────────────────────────────────────────┘
           │ 调用/注入
           ▼
┌──────────────────────────────────────────────────────────┐
│            内部科研 Agent（原 AI Scientist）               │
│                                                          │
│  不可见: Investor、经费、审稿、个人履历、竞争              │
│  可见:   Skill 文本（作为提示词前缀）、文献检索结果        │
│                                                          │
│  Agent 的 LLM 调用（原有逻辑，不变）:                     │
│    - ideation: 文献检索、idea 生成                        │
│    - experiment: 代码生成、结果分析、实验规划              │
│    - writing: 论文撰写                                   │
│    - review: 审稿（为他人论文提供评审意见）                │
└──────────────────────────────────────────────────────────┘
```

#### Shell 的三类 LLM 调用

**① 申请书格式化 + Investor 选择**

时机：ideation 完成后，Agent 产出了 `idea.json`。

```
输入:
  - idea.json（Agent 产出）
  - Founder 个人档案（历史发表记录、过往获批情况）
  - Investor 列表（各 Investor 的方向描述）

LLM 任务:
  1. 阅读 idea 内容
  2. 阅读各 Investor 的方向描述
  3. 结合 Founder 自身履历（哪些 Investor 更匹配自己的研究方向）
  4. 选择最合适的 Investor
  5. 将 idea 格式化为正式的基金申请书

输出: 申请书文本 + 选定的 investor_id
```

**② Skill 文本更新**

时机：收到 Investor 审批意见、追加经费审批意见、Peer Review 评审意见三类反馈时。

```
输入:
  - 当前 skill 文本
  - 事件描述（"你向 I1 申请经费被拒" / "你的论文被接收" / "审稿人指出…"）
  - 反馈原文

LLM 任务:
  基于反馈提取经验教训，调整科研风格和方法论偏好。
  保留未被新证据推翻的已有洞察。

输出: 更新后的 skill 文本（覆盖旧值）
```

**③ 追加经费申请书构建**

时机：实验中途 token 预算耗尽，需要向 Investor 申请追加。

```
输入:
  - 原始 idea
  - 当前实验进度摘要（从 AgentManager 的 journals 中提取）
  - Founder 个人档案
  - Investor 信息

LLM 任务:
  将实验进度格式化为追加经费申请书。
  突出已取得的阶段性成果，说明为什么值得继续资助。

输出: 追加申请书文本
```

#### Shell 与 Agent 的边界规则

| 关注点 | Shell | Agent |
|--------|-------|-------|
| 知道有 Investor 吗？ | 是 | **否** |
| 知道 token 预算存在吗？ | 是 | **否** |
| 知道 peer review 存在吗？ | 是 | **否**（仅作为审稿人参与，不知是生态机制） |
| 知道个人档案吗？ | 是 | **否** |
| 知道自己的 skill 吗？ | 是 | **是**（作为提示词前缀，不被告知来源） |
| 知道文献来自生态内部吗？ | 是 | **否**（只看到检索结果） |
| LLM 调用目的是什么？ | 生态决策（选 Investor、申请书、skill 更新） | 科学研究（idea、代码、论文、审稿意见） |

#### 为什么这样分

- **Agent 不可见经费和竞争** → Agent 的科研行为不受"我需要讨好 Investor"或"我得打败 F2"的干扰 → 更纯粹的科研动机，更接近真实科研人员的内在驱动。
- **Shell 可见环境信息** → Shell 做的是"科研人员的职业策略"——选哪个基金、怎么包装申请书、从拒稿中学到什么。这些在现实中也是科研人员自己做的，但不影响他们对科学问题的思考方式。唯一的例外是 skill——长期经验会潜移默化影响科研风格，所以 skill 是唯一注入 Agent 的反馈通道。
- **分离使得 Agent 和 Shell 可独立测试和替换** → Agent 还是原来的 AI Scientist，Shell 是新增的生态适配层。如果需要换一个不同的 Agent（比如用别的科研自动化系统），只需修改 Shell 的调用接口。

---

## 3. 资源模型

系统管理两种资源：**Token** 和 **GPU**。二者在模型层面等价对待——都是可分配、可消耗（Token 消耗性，GPU 占用性）、需调度的稀缺资源。

### 3.1 Token 资源

Token 是贯穿 Founder 全生命周期的消耗性资源。

**流向**：

```
系统初始预算环境
  → 新 Founder 初始化: 分配默认美元额度（DEFAULT_INITIAL_TOKEN，如 $1 USD）
  → Investor 审批: 从 Investor 的 token_pool 中划拨给 Founder
  → Founder 使用: 每次 LLM 调用通过 backend.query() 扣减
  → 耗尽时: 可申请追加（从 Investor token_pool 补充）
  → 追加被拒: Founder 破产（token_budget 归零，status = dead）
  → ideation 阶段 token 耗尽且从未获得资助: Founder 破产
```

**默认初始额度**（用于新 Founder 的 ideation）：
- 可配置参数，如 `DEFAULT_INITIAL_TOKEN = 1.0`
- ideation 阶段的 LLM 调用按美元成本消耗这些预算
- ideation 完成后如被拒，Founder 用剩余预算再次 ideation
- 如果预算耗尽 → Founder 破产

### 3.2 GPU 资源

**两级分配模型**：

```
Level 0: 物理 GPU 总数
  [0, 1, 2, 3, 4, 5, 6, 7]  (8 个物理 GPU)

Level 1: Investor 静态划分（系统初始化时确定，不可动态调整）
  Investor A → GPU [0, 1]
  Investor B → GPU [2, 3]
  Investor C → GPU [4, 5, 6, 7]

Level 2: Investor 内动态分配（审批时决定）
  Investor A 的 GPU [0, 1]:
    → Founder X (高经费) → GPU [0, 1]（独占）
    → Founder Y (低经费) → GPU [0]; Founder Z → GPU [1]
    → 排队: Founder W 获批但 GPU 全被占用 → 等待项目完成释放
```

**GPU 隔离实现**（方案 A）：

利用 CUDA 运行时的原生 `CUDA_VISIBLE_DEVICES` 环境变量：

```
1. Orchestrator 启动 Founder 实验进程前:
   os.environ["CUDA_VISIBLE_DEVICES"] = "0,1"  (分配 GPU 0,1)

2. Founder 实验主进程:
   get_gpu_count() 优先读 CUDA_VISIBLE_DEVICES → 返回 2
   GPUManager(2) 管理逻辑索引 0,1（映射到物理 GPU 0,1）

3. Worker 子进程 (ProcessPoolExecutor):
   os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)  # 如 "0"
   逻辑 0 = 父进程逻辑 0 = 物理 GPU 0

   子进程修改环境变量不影响父进程（Unix 进程语义）
   CUDA 运行时支持链式索引重映射
```

**需要的最小代码改动**：

```python
# parallel_agent.py get_gpu_count() — 4 行修复
def get_gpu_count() -> int:
    # 优先检查 CUDA_VISIBLE_DEVICES（支持外部 GPU 分配）
    cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES", "").strip()
    if cuda_visible:
        devices = [d for d in cuda_visible.split(",")
                   if d.strip() and d.strip() != "-1"]
        if devices:
            return len(devices)
    # 原有 nvidia-smi 逻辑兜底
    ...
```

---

## 4. 三大模块与数据契约

系统的三个核心阶段被设计为**三个独立模块**，通过明确的数据契约衔接。

### 4.1 模块一：Ideation（ideation 阶段）

**职责**：生成研究 idea，选择一个 Investor，提交基金申请。

**输入**：
- Founder 的 `skill` 文本（注入系统提示词）
- Semantic Scholar 检索工具（含内部 LiteratureDB 合并结果）
- Investor 列表及方向描述（注入系统提示词，供 Founder 做选择）
- Founder 的 `token_budget`（ideation LLM 调用从此扣除）

**处理流程**：

```
1. 组装系统提示词:
   - 注入 Founder skill
   - 注入 Investor 列表及方向描述
2. 执行 ideation 循环（复用 perform_ideation_temp_free.py）:
   - Agent 可调用 SearchSemanticScholar 检索文献
     返回结果区分:
       · "Previous Work (Semantic Scholar)" — 外部过往工作
       · "Latest Work from Peers (Internal Database)" — 同行最新工作
   - Agent 生成 idea.json
3. LLM 决策: 分析各 Investor 方向，选择最匹配的 Investor
4. 封装: idea.json + Founder profile → 基金申请书
5. 提交到选定 Investor 的 application_queue
6. 等待审批
```

**输出**：
- `idea.json`（格式与现有系统完全一致）
- `investor_id`（选定的 Investor）
- 格式化的基金申请书文本

### 4.2 模块二：Experiment & Writing（实验与写作阶段）

**职责**：获得资助后执行全流程科研，产出论文。

**输入**：
- `idea.json`
- `token_budget`（Investor 分配 + 自身剩余）
- `gpu_ids`（Investor 分配的 GPU 列表）
- Founder 的 `skill` 文本（注入 Agent 系统提示词）

**处理流程**：

```
1. Orchestrator:
   a. 设置 CUDA_VISIBLE_DEVICES（GPU 隔离）
   b. 设置 backend._budget_manager（Token 预算钩子）
2. 执行现有全流程（复用 launch_scientist_bfts.py 核心逻辑）:
   a. perform_experiments_bfts() → AgentManager.run()
      - 每次 LLM 调用: backend.query() → budget 检查 → 扣减
      - 预算耗尽: 抛出 BudgetExhaustedException
   b. aggregate_plots()
   c. perform_writeup()
3. 如果 BudgetExhaustedException 被抛出:
   a. AgentManager._save_checkpoint() → 保存当前进度
   b. orchestrator 汇总进度摘要
   c. Investor 评审追加申请（参考进度 + Founder 历史）
   d. 批准 → 补充 budget → 恢复执行
      (manager.run() 从 self.current_stage 继续，checkpoint 机制保证)
   e. 拒绝 → Founder 破产 (status=dead)
      → 实验终止，部分结果保留在 experiment_results/ 但不发表
```

**输出**：
- `paper.pdf`（完整论文）
- `experiment_results/`（实验数据、图表）
- 更新后的 `Founder token_budget`（剩余额度）

### 4.3 模块三：Peer Review（同行评审阶段）

**职责**：对产出的论文进行双盲同行评审。

**输入**：
- `paper.pdf`
- 论文所属的 `founder_id`（系统内部记录，审稿人不可见）
- 待选审稿人池（当前所有 `status != dead` 且非论文作者的 Founder）

**处理流程**：

```
1. 收集所有 ready_for_review 的论文
2. 对每篇论文:
   a. 当前版本：从 Founder Pool 中随机选择 K 个审稿人（默认 3，排除作者本人）
   b. 每个审稿人（LLM）进行双盲评审
   c. 汇总审稿意见，计算加权平均分
   d. 平均分 >= ACCEPTANCE_THRESHOLD → accept, else → reject
   e. TODO：后续升级为按论文标题/摘要与 reviewer skill 的相似度匹配
3. 批量处理所有结果
```

**输出**：
- `review_result`：`{paper_id, accepted: bool, reviews: List[str], scores: List[float]}`
- 更新 LiteratureDB（accepted → published / rejected → unpublished）
- 更新各 Founder 的 skill（吸收评审意见）
- 更新各 Founder 的个人档案

### 4.4 数据契约图

```
┌─────────────────────────────────────────────────────────────────┐
│                        Module 1: Ideation                        │
│  Input:  skill, investor_list, token_budget, tools               │
│  Output: idea.json, investor_id, proposal_text                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │   Investor Evaluation   │
              │   approve / reject      │
              │   allocate: token + GPU │
              └───────────┬────────────┘
                          │
              ┌───────────┴───────────┐
              │ approved  │ rejected  │
              ▼           ▼           │
┌──────────────────────┐  Founder 重新 │
│  Module 2:           │  ideation     │
│  Experiment & Writing│  (回 Module 1)│
│                      │              │
│  Input:  idea.json,  │              │
│          token_budget,│             │
│          gpu_ids,     │              │
│          skill        │              │
│                      │              │
│  Output: paper.pdf,  │              │
│          exp_results │              │
│                      │              │
│  [预算耗尽→追加经费]   │              │
│  [追加被拒→破产]      │              │
└──────────┬───────────┘              │
           │                          │
           ▼                          │
┌──────────────────────┐              │
│  Module 3:            │              │
│  Peer Review          │              │
│                      │              │
│  Input:  paper.pdf   │              │
│  Output: accept/reject│             │
│          review_feedback            │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Post-Review Updates  │
│  ├─ LiteratureDB       │
│  ├─ Founder Profile    │
│  └─ Founder Skill      │
└──────────┬───────────┘
           │
           ▼
     Founder 重新 ideation
     (回 Module 1，使用更新后的 skill + 更新后的 LiteratureDB)
```

---

## 5. 系统全生命周期

### 5.1 Founder 状态机

```
                    ┌─────────┐
                    │ 新生     │ (DEFAULT_INITIAL_TOKEN)
                    │ ideating│
                    └────┬────┘
                         │ 生成 idea + 选择 Investor
                         ▼
                    ┌─────────┐
                    │ 等待审批 │ (申请已提交给 Investor)
                    └────┬────┘
                    ┌────┴────┐
                    │         │
                    ▼         ▼
              ┌─────────┐  ┌─────────┐
              │ 获批    │  │ 被拒    │
              │experiment│ │ ideating│ (用剩余 token 重新 ideation)
              └────┬────┘  └────┬────┘
                   │            │ token 耗尽?
              ┌────┴────┐       ▼
              │         │  ┌─────────┐
              ▼         ▼  │  DEAD   │
        ┌─────────┐ ┌─────────┐ (被新 Founder 替换)
        │ 完成    │ │ 预算耗尽 │
        │ writing │ │ 申请追加 │
        └────┬────┘ └────┬────┘
             │        ┌──┴──┐
             │        │     │
             │        ▼     ▼
             │   ┌─────────┐ ┌─────────┐
             │   │ 追加获批│ │ 追加被拒│
             │   │ 恢复实验 │ │  DEAD   │
             │   └────┬────┘ └─────────┘
             │        │
             ▼        ▼
        ┌─────────┐
        │ review  │ (论文进入 peer review)
        └────┬────┘
             │
             ▼
        ┌─────────┐
        │ 更新    │ (skill + profile + literatureDB)
        │ 后重回  │
        │ ideating│
        └─────────┘
```

### 5.2 Investor 生命周期

```
初始状态:
  Investor 拥有 token_pool + gpu_ids + direction

单个周期:
  1. [等待] 上一轮所有已资助项目结束（论文评审完成或项目破产）
  2. [收集] 当前 application_queue 中截至该时刻累积的所有申请
  3. [批次决策] 一次 LLM 调用统一评审这一批申请
     - 最多选出 K 个提案
     - 获批: token（从 pool 扣除）+ GPU（从 gpu_ids 中一次性划出）
     - 被拒: 一律打回，Founder 用剩余 token 重新 ideation
  4. [登记] 将获批 Founder 记入 active_projects
  5. [等待] 所有 active_projects 完成或破产
  6. 回到步骤 2
```

### 5.3 Investor 重新开放评审的精确条件

```
条件 A: 上一轮所有获批项目已结束（completed + review done / bankrupt）

当 A 成立时: Investor 进入下一轮评审
```

### 5.4 破产与替换机制

- Founder 的 token_budget 是所有阶段**累计消耗**的。
- **任何时候** token 耗尽且（无资格申请追加 或 追加被拒）→ Founder 破产。
- 破产后：`status = dead`，不再参与任何活动。
- 已发表论文保留在 LiteratureDB，个人档案保留（供历史查询和研究分析）。
- 系统**立即**创建一个新 Founder：
  - 完全干净的初始状态
  - 默认 token 额度（`DEFAULT_INITIAL_TOKEN`）
  - 初始 skill 模板
  - 空的个人档案
  - 新 `founder_id`
- 系统中**活跃 Founder 数量保持恒定**。

---

## 6. Skill 演化机制

### 6.1 设计原则

Skill 是**环境反馈影响 Founder Agent 行为的唯一闭环**。它是以自然语言文本块的形式存在，注入到 Agent 的系统提示词中，影响其 ideation 创意方向和实验设计风格。

### 6.2 Skill 更新时机

以下三类事件均触发 Skill 更新：

1. **Investor 对初始申请的评审意见**（无论获批还是被拒——被拒的原因同样有信息量）
2. **Investor 对追加经费申请的评审意见**（无论获批还是被拒）
3. **Peer Review 的审稿意见**（无论接收还是拒稿）

### 6.3 Skill 更新方式

```
输入: 当前 skill 文本 + 事件描述 + 评审/反馈意见
  → LLM 处理（prompt 引导）:
      "Based on the feedback received, update this researcher's skill profile.
       Extract actionable lessons. Adjust methodological preferences.
       Preserve existing valuable insights unless contradicted by new evidence.
       Keep the skill concise (under 500 words)."
  → 新 skill 文本（覆盖旧值）
```

### 6.4 Skill 注入位置

两处注入：

**ideation 阶段**：`perform_ideation_temp_free.py` 的系统提示词。
**实验阶段**：`AgentManager._get_task_desc_str()` 的任务描述前缀。

两处注入方式相同——文本前置拼接：

```
"Your Research Style & Lessons Learned:\n{skill}\n\n"
+ [原有系统提示词/任务描述]
```

### 6.5 Skill 初始模板

```
"You are a rigorous researcher who values empirical validation.
 You prefer well-motivated hypotheses with clear experimental designs.
 You aim to contribute novel insights while ensuring reproducibility.
 You have not yet developed a specialized methodological preference."
```

---

## 7. 文献库与检索工具

### 7.1 设计原则

- **不为 LiteratureDB 创建独立 Tool**——Agent 只看到一个 `SearchSemanticScholar` 工具。
- 每次调用该工具时，系统在底层同时检索 Semantic Scholar（外部 API）和内部 LiteratureDB，并合并结果。
- 合并后的结果用明确的 section 标题区分来源。

### 7.2 返回格式

```
Search Results for: "gradient frustration in neural networks"

=== Previous Work (Semantic Scholar) ===
1: Title A. Authors. Venue, Year.
   Citations: 42
   Abstract: ...

2: Title B. Authors. Venue, Year.
   Citations: 15
   Abstract: ...
(No results found.  -- 如果没有结果)

=== Latest Work from Peers in the Ecosystem (Internal Database) ===
1: Title C. Authors. Ecosystem, Year.
   Status: Published (peer-reviewed)
   Abstract: ...

2: Title D. Authors. Ecosystem, Year.
   Status: Unpublished
   Abstract: ...
(No results found.  -- 如果没有结果)
```

### 7.3 实现方式

修改 `SemanticScholarSearchTool.use_tool()`：

```python
def use_tool(self, query: str) -> str:
    # 1. 检索 Semantic Scholar（原有逻辑，不变）
    s2_results = self.search_semantic_scholar(query) or []

    # 2. 检索内部 LiteratureDB（新增）
    db_results = self.literature_db.search(query, limit=self.max_results)

    # 3. 合并格式化
    parts = []
    parts.append("=== Previous Work (Semantic Scholar) ===")
    parts.append(
        self.format_papers(s2_results)
        if s2_results
        else "No results found."
    )
    parts.append(
        "\n=== Latest Work from Peers in the Ecosystem (Internal Database) ==="
    )
    parts.append(
        self.format_db_papers(db_results)
        if db_results
        else "No results found."
    )
    return "\n".join(parts)
```

### 7.4 LiteratureDB 数据结构

```python
class LiteratureDatabase:
    def __init__(self):
        self.published: List[Dict] = []    # peer review accepted
        self.unpublished: List[Dict] = []  # peer review rejected

    def add_published(self, paper: Dict):
        self.published.append(paper)

    def add_unpublished(self, paper: Dict):
        self.unpublished.append(paper)

    def search(self, query: str, limit: int = 10) -> List[Dict]:
        # 简单关键词匹配（published 优先排列）
        # 后续可升级为 embedding 向量检索
        ...
```

---

## 8. 同行评审

### 8.1 双盲机制

- 审稿人不知道论文作者身份（论文元信息中不含作者标识，prompt 中不注入）。
- 作者不知道审稿人身份（评审意见匿名返回）。
- 系统内部维护 paper_id → reviewer_ids 映射（仅用于更新 skill/profile，不暴露给任何 Founder Agent）。

### 8.2 审稿人分配

- 每篇论文 K 个审稿人（默认 K=3，可配置参数）。
- 候选池：所有 `status != dead` 且 `founder_id != paper_author_id` 的 Founder。
- **当前版本**：随机从候选池中选择 K 人。
- **后续优化方向**：按论文标题/摘要与审稿人 skill 文本的相似度排序，优先选匹配度高的。

### 8.3 评审流程

```
对每篇论文:
  1. 选择 K 个审稿人（排除作者本人，无放回抽样）
  2. 对每个审稿人:
     a. 调用 perform_llm_review.py 的评审逻辑
     b. LLM prompt 中不包含作者信息
     c. 产出: review_text (定性意见) + score (1-10 定量分)
  3. 汇总 K 份评审
  4. 计算加权平均分（当前版本: 简单算术平均）
  5. 平均分 >= ACCEPTANCE_THRESHOLD → accept
     平均分 <  ACCEPTANCE_THRESHOLD → reject
```

### 8.4 评审结果的后续处理

```
accept:
  → LiteratureDB.add_published(paper)
  → 更新 Founder profile:
      "使用 [investor_id] 资源完成作品 [paper_title]，成功发表"
  → 更新 Founder skill（吸收 3 份评审意见中的建设性反馈）

reject:
  → LiteratureDB.add_unpublished(paper)
  → 更新 Founder profile:
      "使用 [investor_id] 资源完成作品 [paper_title]，未发表"
  → 更新 Founder skill（吸收评审意见 + 被拒原因分析）
```

---

## 9. Founder 个人档案

### 9.1 档案格式

每个 Founder 维护一个**历史事件列表**，记录与系统交互的全流程关键事件：

```json
{
  "founder_id": "F001",
  "history": [
    {
      "timestamp": "2026-05-10T14:30:00",
      "event_type": "funding_approved",
      "investor_id": "INV_A",
      "idea_title": "Gradient Frustration in Deep Ensembles",
      "allocated_token_usd": 500.0,
      "allocated_gpus": [0, 1]
    },
    {
      "timestamp": "2026-05-10T15:20:00",
      "event_type": "extra_funding_requested",
      "investor_id": "INV_A",
      "requested_amount_usd": 200.0,
      "decision": "approved",
      "reason": "Promising preliminary results"
    },
    {
      "timestamp": "2026-05-10T18:00:00",
      "event_type": "paper_completed",
      "investor_id": "INV_A",
      "paper_title": "Gradient Frustration in Deep Ensembles",
      "accepted": true,
      "review_scores": [7, 8, 6]
    }
  ]
}
```

### 9.2 记录规则

| 事件类型 | 是否记录 | 说明 |
|---------|---------|------|
| Idea 申请基金被拒 | **不记录** | 无实质成果，避免 profile 膨胀 |
| Idea 申请基金获批 | 记录 | 含 allocated_token_usd、allocated_gpus |
| 追加经费申请（无论结果）| 记录 | 含 decision、reason |
| 论文产出（接收/拒稿）| 记录 | 含 accepted、review_scores |
| Founder 破产 | 记录 | 标记终止状态 |

### 9.3 档案的用途

- **Investor 审批参考**：评估 Founder 的历史发表记录、资源使用效率
- **实验分析**：统计分析各 Founder 产出、各 Investor 资助效率
- **不注入到 Founder Agent 提示词中**——Founder 不知道自己被如何评估

---

## 10. 实现方案与代码改动

### 10.1 新增文件清单

全部在 `founder/` 包中：

| 文件 | 核心职责 |
|------|---------|
| `founder/__init__.py` | 包初始化 |
| `founder/config.py` | 系统全局配置（DEFAULT_INITIAL_TOKEN、GLOBAL_BUDGET_CAP_USD、ACCEPTANCE_THRESHOLD 等） |
| `founder/orchestrator.py` | `FounderOrchestrator`：中央控制器，编排所有模块和角色 |
| `founder/investor.py` | `Investor`：LLM 驱动的基金评审决策 |
| `founder/token_budget.py` | `TokenBudgetManager`：预算管理 + 与 backend.query() 的钩子集成 |
| `founder/resource_scheduler.py` | `ResourceScheduler`：GPU 池管理，按经费比例分配 |
| `founder/literature_db.py` | `LiteratureDatabase`：文献存储与检索；修改 SemanticScholar 工具的结果合并逻辑 |
| `founder/peer_review.py` | `PeerReviewSystem`：双盲评审编排（审稿人选择、分数汇总、决定） |
| `founder/reputation.py` | `FounderProfile`：个人档案记录管理 |
| `founder/skill.py` | `SkillManager`：skill 文本创建、存储与 LLM 驱动的演化更新 |
| `founder/proposal_builder.py` | 申请书格式化 + LLM 驱动的 Investor 选择决策 |

### 10.2 修改的现有文件

| 文件 | 行数 | 改动内容 |
|------|------|---------|
| `ai_scientist/treesearch/backend/__init__.py` | ~15 | `BudgetExhaustedException`、`_budget_manager` 模块级钩子、`set_budget_manager()`、`query()` 调用前后检查/扣减 |
| `ai_scientist/treesearch/agent_manager.py` | ~3 | `_get_task_desc_str()`：条件注入 research_skill（文本前置） |
| `ai_scientist/treesearch/parallel_agent.py` | ~4 | `get_gpu_count()`：优先读取 CUDA_VISIBLE_DEVICES |
| `ai_scientist/perform_ideation_temp_free.py` | ~15 | 系统提示词注入 Investor 列表 + skill；工具结果合并 LiteratureDB |
| `ai_scientist/tools/semantic_scholar.py` | ~20 | `use_tool()` 新增内部 LiteratureDB 检索 + 结果合并格式化 |

**Agent 内部总改动：约 60 行，5 个文件。**

### 10.3 不改动的文件

以下文件无需任何修改：

- `parallel_agent.py`（除 `get_gpu_count()` 的 4 行外）—— 零改动
- `journal.py` —— 零改动
- `agent_manager.py` 的 `run()` 方法 —— 零改动（异常传播天然支持挂起/恢复）
- `bfts_utils.py` —— 零改动
- `perform_experiments_bfts_with_agentmanager.py` —— 零改动
- `perform_writeup.py` —— 零改动
- `perform_llm_review.py` —— 零改动（调用方从"自我评审"变为"系统审稿人"）
- `log_summarization.py` —— 零改动
- `interpreter.py` —— 零改动
- `utils/` 全部 —— 零改动

### 10.4 关键改动详解

#### backend/__init__.py

```
新增:
  class BudgetExhaustedException(Exception): ...
  _budget_manager: Optional[TokenBudgetManager] = None
  def set_budget_manager(mgr): ...

修改 query():
  调用前: if _budget_manager: _budget_manager.pre_call_check(model)
  调用后: if _budget_manager: _budget_manager.post_call_deduct(model, ...)
```

#### AgentManager._get_task_desc_str()

```
在原有 "You are an ambitious AI researcher..." 之前插入:
  if self.research_skill:
      "Your Research Style & Lessons Learned:\n{skill}\n\n"
```

#### parallel_agent.py get_gpu_count()

```
在 nvidia-smi 调用之前插入:
  if os.environ.get("CUDA_VISIBLE_DEVICES", "").strip():
      return len([d for d in cuda_visible.split(",") if d.strip() and d.strip() != "-1"])
```

#### perform_ideation_temp_free.py

```
系统提示词扩展:
  + Investor 列表及方向描述
  + Skill 注入

工具结果合并:
  SemanticScholarSearchTool → use_tool() 同时检索 LiteratureDB
```

---

## 11. 运行终点与实验配置

### 11.1 当前实现说明（Implementation Notes）

为避免设计目标与当前代码状态混淆，这里明确列出**当前已实现行为**与**尚未完成的 TODO**。

**当前已实现**

- **异步双时钟的当前版本**
  - Founder 完成一轮项目后会立即重新 ideation 并继续投递。
  - Investor 维护 `application_queue` 与 `active_projects`。
  - Investor 只有在上一轮 `active_projects` 全部结束后，才会开放下一轮批量初审。
  - Investor 的 reopen gate 当前定义为：
    - 上一轮获批项目全部 `review done` 或 `bankrupt`
    - 不要求这些 Founder 已完成下一轮 ideation 才开放

- **Investor 初审**
  - 按轮批量处理 `application_queue` 中截至评审时刻累积的全部申请。
  - 一轮初审对应一次 LLM 调用。
  - 每轮至多批准 `K` 个提案（默认 `K=3`）。
  - 未获批提案一律打回，Founder 用剩余 token 重新 ideation。

- **GPU 资源**
  - GPU 静态归属 Investor。
  - Investor 在单轮审批时动态划分本轮获批项目的 GPU。
  - 分配总量严禁超过 Investor 持有量。
  - Founder 一旦拿到 GPU，会一直持有到该项目完整结束（论文评审结束）或项目死亡。
  - 当前实现中不存在“获批后排队等 GPU”。

- **实验挂起 / 恢复**
  - 已实现 checkpoint + resume token 机制。
  - 当前支持在 experiment / writeup / review 阶段预算耗尽时挂起，并在追加经费获批后恢复。

- **同行评审**
  - 当前为真实双盲 LLM 审稿。
  - Reviewer 从 Founder Pool 中随机抽取，排除作者本人。
  - 当前 reviewer 匹配策略是随机；不是占位分数。

- **论文产线**
  - Founder 已接上完整 LaTeX / PDF writeup 流。
  - 当上游 writeup 依赖或中间产物不足时，允许回退到轻量文本 writeup 作为兜底。

- **文献库**
  - 内部 LiteratureDB 可保存并检索 `under_review` / `published` / `rejected` 状态论文。
  - 系统内部论文可通过 `SearchSemanticScholar` 的内部结果区块回查。

- **Founder Profile / Skill**
  - Profile 已记录 funding / extra funding / suspension / resume / paper completed / bankruptcy 等事件。
  - Skill 已记录更新历史日志（old skill / new skill / event / feedback excerpt）。

- **运行痕迹与分析产物**
  - 主链运行现已默认落盘 `outer_llm_io.jsonl` 与 `outer_events.jsonl`。
  - `outer_llm_io.jsonl` 用于保留外层 LLM I/O，当前覆盖：
    - constrained ideation
    - proposal builder
    - skill update
    - peer review individual / meta
    - LLM-based investor batch review / extra-funding review
  - `outer_events.jsonl` 用于保留关键制度事件，当前覆盖：
    - ideation completed
    - proposal created
    - initial funding round
    - initial / extra funding decision
    - experiment completed
    - writeup completed
    - review result
    - cycle finished
    - bankruptcy
  - 每轮 proposal 会写入 `proposals/<founder_id>/cycle_k.json`。
  - 每轮 review 结果会写入 `reviews/<founder_id>/cycle_k_<paper_id>.json`。

- **预算计价**
  - 当前 token 使用量从 OpenAI-compatible API 返回的 `usage` 字段读取。
  - `qwen3.6-plus` 已配置价格：
    - input: `$0.30 / 1M`
    - output: `$1.75 / 1M`
    - cached input: `$0.03 / 1M`
  - 当前实现已修复“首次 snapshot 差分计费误回落到固定 `$0.005`”的问题；只要模型价格表存在，即按真实 token 数换算美元。

- **运行依赖边界**
  - 完整 PDF writeup 依赖 `pdflatex`；缺失时，LaTeX/PDF 反思编译会失败。
  - 因此，正式实验若要比较完整论文产线，运行环境必须安装 LaTeX 工具链。

**当前未完成 / TODO**

- Reviewer 分配从随机升级为基于论文内容与 reviewer skill 的相似度匹配。
- Founder 死亡后自动补位，保持 Founder Pool 规模恒定。
- 更细粒度的 profile 分析字段与 skill diff 展示层。
- 更多真实 message-driven 全链路回归，以验证重链路下的稳定性。
- LiteratureDB 目前仍以进程内单例为主；若需长期离线分析，还需要额外增加 run 级 snapshot 持久化。

### 11.1 终止条件

系统跟踪全局累计美元消耗量（所有 Founder、所有阶段的 LLM 调用换算后的总成本）。

```
GLOBAL_BUDGET_CAP_USD = 100.0  # 可配置参数

当 sum(shell.token_budget.total_consumed_usd) >= GLOBAL_BUDGET_CAP_USD:
  → 系统不再开放新的 funding round
  → 不再批准新的 initial funding 或 extra funding
  → 正在执行的任务运行至完成或破产
  → 待处理 proposal 会收到明确拒绝
  → 生成最终统计报告
```

### 11.2 可配置参数一览

| 参数 | 建议默认值 | 说明 |
|------|-----------|------|
| `NUM_FOUNDERS` | 5 | 系统中始终保持的活跃 Founder 数量 |
| `NUM_INVESTORS` | 2 | Investor 数量 |
| `DEFAULT_INITIAL_TOKEN` | 1.0 | 新 Founder 初始美元额度（USD） |
| `INVESTOR_TOTAL_BUDGET_USD` | 100.0 | 单个 Investor 的总美元预算池 |
| `INVESTOR_APPROVAL_TOKEN_USD` | 10.0 | 每个获批项目的初始 tranche（USD） |
| `INVESTOR_EXTRA_TOKEN_USD` | 15.0 | 每次追加经费的 tranche（USD） |
| `GLOBAL_BUDGET_CAP_USD` | 100.0 | 系统总美元消耗上限 |
| `REVIEWERS_PER_PAPER` | 3 | 每篇论文审稿人数 |
| `ACCEPTANCE_THRESHOLD` | 6.0 | 接收/拒稿的加权平均分阈值（1-10 分制） |
| `INVESTOR_CONFIGS` | 见配置 | 各 Investor 的 direction、token_pool、gpu_ids |
| `SKILL_UPDATE_MODEL` | qwen3.6-plus | 用于 skill 演化的 LLM 模型 |
| `INVESTOR_MODEL` | qwen3.6-plus | 用于 Investor 决策的 LLM 模型 |
| `REVIEW_MODEL` | qwen3.6-plus | 用于 peer review 的 LLM 模型 |

### 11.3 最终统计报告

系统停止后自动生成：

- 各 Founder 产出统计：论文数、接收率、总 token 消耗、生存时间
- 各 Investor 资助效率：资助项目数、产出论文数、token 利用率、追加申请频率
- 文献库增长曲线：published / unpublished 论文数随时间变化
- Skill 演化追踪：各 Founder 的 skill 文本变化历史（diff 形式）
- 论文多样性指标：用于与 Baseline 对照组对比
- 破产统计：破产次数、破产原因分布
- 外层 LLM 行为回放：`outer_llm_io.jsonl` + `outer_events.jsonl` + `proposals/` + `reviews/`

### 11.4 Baseline 对照

按照 plan.md 的设计，设置两组对照实验：

**Baseline 1（无科研网络）**：
- 科研 Agent 各自独立运行
- 无 Investor、无 token 预算、无 peer review、无文献库反馈、无 skill 更新

**Baseline 2（仅文献可见）**：
- 科研 Agent 可以看到前人生成的论文
- 但无基金筛选、无预算约束、无 peer review 机制

**实验组（完整科研生态网络）**：
- 包含本设计文档描述的全部机制

三组在 `GLOBAL_BUDGET_CAP_USD` 相同的情况下运行，比较论文产出多样性。

---

## A. 附录：与原始 AI Scientist 系统的改动对照

```
原始系统 (单 Agent):
  idea → experiments → writeup → self-review

本系统 (多 Founder 生态系统):
  ┌─ 外部添加（founder/ 包, ~8 个新文件）──────────────────┐
  │ FounderOrchestrator                                     │
  │ ├─ Investor 评审 → 资源分配                              │
  │ ├─ TokenBudgetManager → 预算控制（backend 钩子）          │
  │ ├─ ResourceScheduler → GPU 调度                          │
  │ ├─ PeerReviewSystem → 双盲评审                           │
  │ ├─ LiteratureDatabase → 文献积累                         │
  │ ├─ SkillManager → skill 读取/注入/演化                   │
  │ ├─ FounderProfile → 个人档案                             │
  │ └─ ProposalBuilder → 申请书封装 + Investor 选择          │
  └────────────────────────────────────────────────────────┘
        │ 调用/注入（Agent 不知道自己处于生态中）
  ┌─────┴──────────────────────────────────────────┐
  │ 原始 AI Scientist (Agent 核心, ~60行/5文件改动)  │
  │ ├─ perform_ideation_temp_free.py               │
  │ │   └─ 提示词扩展 + 工具结果合并                 │
  │ ├─ AgentManager + ParallelAgent                 │
  │ │   ├─ _get_task_desc_str() +skill 注入         │
  │ │   ├─ get_gpu_count() CUDA_VISIBLE_DEVICES 修复│
  │ │   └─ (其余零改动)                             │
  │ ├─ backend.query() +budget hook                │
  │ ├─ semantic_scholar.py +LiteratureDB 合并       │
  │ └─ perform_writeup / perform_llm_review        │
  │     (复用, 仅调用模式变化)                       │
  └────────────────────────────────────────────────┘
```
