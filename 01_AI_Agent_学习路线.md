# AI Agent 学习路线：从零 AI Coding 到可展示项目

> 面向候选人：高雨晨  
> 目标方向：AI Agent 应用工程 / AI Coding 工程化 / 大模型应用开发  
> 更新时间：2026-08-02

---

## 1. 先调整项目策略

华为隐私合规项目属于公司保密项目，不能把代码、规则、数据、截图或内部架构放到公开仓库，也不应该为了面试复刻内部内容。

因此，本路线只使用：

- 自己创建的代码仓库。
- 自己编写的测试数据。
- 公开文档或自己的学习笔记。
- 脱敏后的通用技术描述。

公司项目只作为简历中的工作经历，用来说明你有真实业务经验；公开练手和面试演示使用下面两个项目。

### 1.1 两个项目的分工

| 项目 | 难度 | 主要目的 | 覆盖能力 |
|---|---:|---|---|
| StudyMate | 入门 | 从零理解 LLM、Tool Calling、RAG、Memory、Evaluation | 基础 Agent 能力 |
| RepoPilot | 主项目 | 练习 AI Coding Agent 的完整工程闭环 | Code RAG、工具、规划、测试、反思、MCP、HITL、沙箱 |

推荐顺序：

~~~mermaid
flowchart LR
    A["从零 AI Coding<br/>Git + Issue + 测试"] --> B["StudyMate<br/>个人学习资料 Agent"]
    B --> C["理解基础 Agent<br/>Tool / RAG / Memory / Eval"]
    C --> D["RepoPilot<br/>代码仓库 Agent"]
    D --> E["AI Coding 完整闭环<br/>Plan -> Edit -> Test -> Review"]
    E --> F["公开作品集<br/>README + Demo + 指标"]
~~~

### 1.2 这条路线的原则

- 先做单体、小范围、可测试的项目，再做复杂 Agent。
- 先实现普通 Workflow，再实现 Agent，让你感受两者差异。
- 先用普通函数实现工具，再改造成 MCP Server，让你理解 MCP 的价值。
- 先做单 Agent，再考虑多 Agent；多 Agent 不是默认答案。
- 每完成一个功能都让 AI Coding 工具写测试、跑测试、检查 diff。
- 不追求一次生成完整项目，按 Issue 拆成可验证的小任务。

---

## 2. 从零开始的 AI Coding 方法

这里的“从零 AI Coding”指的是：你使用 Codex / OpenCode 等工具辅助设计、编码、测试和调试，但仍然掌握代码、架构和验证过程；不是让模型一次性生成一个自己看不懂的仓库。

### 2.1 基础工作流

~~~mermaid
flowchart LR
    I["Issue<br/>写清需求"] --> P["Plan<br/>让 AI 先读代码并出方案"]
    P --> C["Code<br/>小步实现"]
    C --> T["Test<br/>运行自动化测试"]
    T --> R["Review<br/>检查 diff、边界和安全"]
    R --> D["Document<br/>更新 README 和记录"]
    T -. "失败" .-> C
    R -. "发现设计问题" .-> P
~~~

### 2.2 每个任务的固定格式

在开始编码前，先写一个 Issue：

~~~text
目标：
用户需要完成什么事情？

范围：
这次只修改哪些模块？明确不做什么。

输入与输出：
输入格式、输出格式、错误格式是什么？

验收标准：
至少列出 3 条可执行的测试条件。

约束：
不能破坏哪些接口？有哪些安全或性能限制？
~~~

然后让 AI Coding 工具按顺序执行：

1. 先阅读相关文件，不要立即写代码。
2. 输出修改计划和可能影响的模块。
3. 等你确认后再实现。
4. 先补测试，再改功能，或至少同时提交测试。
5. 运行测试并展示完整结果。
6. 输出 git diff，解释每个修改点。
7. 你确认后再进入下一个 Issue。

### 2.3 AI Coding 的验收标准

每个功能至少留下：

- 一个 Issue。
- 一次可读的 commit。
- 一组自动化测试。
- 一段失败记录或边界说明。
- 一份简短的设计记录。

你要始终能回答：

- 这段代码为什么这样写？
- 如果模型换了，系统还能工作吗？
- 失败时系统怎么处理？
- 如何证明这次修改没有破坏原功能？

---

## 3. Agent 能力地图

### 3.1 从简单到复杂

~~~mermaid
flowchart TD
    A["普通函数调用<br/>确定性代码"] --> B["Workflow<br/>固定流程和分支"]
    B --> C["Tool Calling<br/>模型选择结构化工具"]
    C --> D["Agent<br/>模型决定下一步行动"]
    D --> E["Stateful Agent<br/>状态、记忆、恢复"]
    E --> F["生产 Agent<br/>评估、权限、沙箱、HITL"]
    F --> G["Multi-Agent<br/>只有确有必要时再拆分"]
~~~

### 3.2 需要亲手做出的对比

| 概念 | 核心问题 | 在项目中的体验方式 |
|---|---|---|
| 普通函数 | 代码直接调用固定逻辑 | StudyMate 的文档加载、计算器 |
| Workflow | 流程由开发者预先决定 | 固定的“检索 -> 回答 -> 引用” |
| Tool Calling | 模型选择一个结构化工具 | 让模型选择搜索笔记或制定计划 |
| Agent | 模型根据结果决定下一步 | 允许它搜索、补充信息、再次检索 |
| Memory | 系统如何保留上下文 | 保存会话状态和用户学习偏好 |
| RAG | 模型如何使用外部知识 | 检索笔记并返回引用片段 |
| Reflection | 执行失败后如何检查和修复 | RepoPilot 根据测试日志修改补丁 |
| MCP | 工具如何标准化接入 | 将文件、Git、测试工具暴露为 MCP |
| HITL | 哪些动作必须人确认 | 代码写入、执行命令、创建 PR 前暂停 |
| Multi-Agent | 是否需要多个角色协作 | RepoPilot 后期才拆 Planner / Reviewer |

---

## 4. 项目一：StudyMate 个人学习资料 Agent

这是入门项目，建议先完成。它不依赖公司内容，可以使用自己的学习笔记、公开 Python 文档、公开 Agent 文章和自己编写的 Markdown。

### 4.1 项目定位

> 一个面向个人学习资料的本地优先 Agent：能够检索学习笔记、回答问题、生成学习计划、保存学习偏好，并用引用和评估数据约束回答质量。

### 4.2 MVP 功能

- 导入 Markdown / TXT / PDF 学习资料。
- 将资料切分并建立本地知识库。
- 根据问题检索相关片段。
- 回答时返回引用来源。
- 使用 Tool Calling 选择：
  - 搜索资料。
  - 获取指定笔记。
  - 计算学习计划。
  - 保存学习偏好。
- 保存当前会话历史。
- 对回答进行简单评分和失败记录。

### 4.3 推荐技术栈

- Python。
- Pydantic。
- FastAPI，可选，第一版可以先做 CLI。
- SQLite 保存任务和会话。
- Chroma 或 Qdrant 保存向量，入门优先使用 Chroma。
- 任一兼容 OpenAI API 的模型。
- pytest。

### 4.4 架构图

~~~mermaid
flowchart LR
    U["用户问题"] --> O["Orchestrator"]
    O --> R["Retriever<br/>检索资料"]
    O --> T["Tools<br/>搜索 / 计算 / 保存偏好"]
    R --> C["Context Builder<br/>拼接引用上下文"]
    T --> C
    C --> L["LLM<br/>结构化回答"]
    L --> V["Validator<br/>格式和引用校验"]
    V --> A["回答 + 引用 + 评估记录"]
    V -. "格式错误" .-> L
~~~

### 4.5 分四步完成

#### Step 1：先不做 Agent

实现固定流程：

~~~text
问题 -> 检索资料 -> 拼接上下文 -> LLM 回答 -> 返回引用
~~~

学习重点：

- 文档加载。
- chunk 切分。
- Embedding。
- 向量检索。
- 引用溯源。

#### Step 2：加入结构化输出

定义回答模型：

~~~text
Answer:
  summary: str
  key_points: list[str]
  sources: list[Source]
  confidence: float
  need_more_context: bool
~~~

学习重点：

- JSON Schema。
- Pydantic 校验。
- 格式错误重试。
- 无依据时拒答。

#### Step 3：加入 Tool Calling

提供 4 个工具：

- search_notes(query)。
- get_note(note_id)。
- calculate_study_plan(hours, deadline)。
- save_preference(key, value)。

先把工具写成普通 Python 函数，再让模型选择工具。

学习重点：

- 工具 schema。
- 工具选择。
- 参数校验。
- 工具错误处理。
- Tool Calling 与固定 Workflow 的区别。

#### Step 4：加入简单 Memory 和 Evaluation

Memory：

- 短期记忆：当前会话历史。
- 用户偏好：每天学习时长、目标方向、已掌握主题。
- 不要一开始保存所有对话，避免记忆污染。

Evaluation：

- 准备 30 个问题。
- 检查回答是否引用正确资料。
- 记录 Recall@K、引用正确率、拒答率、平均 Token 成本。

### 4.6 StudyMate 的完成标准

- 可以导入自己的学习资料。
- 可以回答 30 个测试问题。
- 关键结论带来源。
- Tool Calling 至少调用 3 种工具。
- 结构化输出错误可以自动修复。
- 能对比“固定 Workflow”和“Agent 自主选择工具”的差异。
- 有 README、测试、截图和指标。

### 4.7 这个项目主要学什么

| Agent 技能 | StudyMate 中的实现 |
|---|---|
| LLM 调用 | 回答和计划生成 |
| Structured Output | 回答对象和引用对象 |
| RAG | 学习资料检索 |
| Tool Calling | 搜索、计算、保存偏好 |
| Memory | 会话和学习偏好 |
| Workflow | 固定的检索回答流程 |
| Agent | 模型根据问题选择工具 |
| Evaluation | 30 条问答测试集 |
| Guardrail | 无引用时拒答、参数校验 |

---

## 5. 项目二：RepoPilot 代码仓库 Agent

这是主项目，用来投 AI Coding、Agent 应用和开发者工具岗位。不要让它一开始修改真实大型仓库，而是先创建一个自己的小型目标仓库。

### 5.1 目标仓库

先用 AI Coding 工具创建一个独立的 sample-todo-api：

- Python + FastAPI。
- SQLite。
- 5-10 个接口。
- 20 个 pytest 测试。
- 一个 README。
- 有意保留 3-5 个简单 Issue，例如：
  - 增加分页。
  - 修复过期任务查询。
  - 增加标签过滤。
  - 补充输入校验。

RepoPilot 本身是另一个仓库，负责读取和修改 sample-todo-api。这样可以安全地从小仓库开始，所有问题和测试都由你控制。

### 5.2 项目定位

> 一个面向小型 Python 仓库的 AI Coding Agent，能够理解 Issue、检索代码、生成补丁、运行测试、分析失败原因，并在人工确认后输出修改报告。

### 5.3 核心流程

~~~mermaid
flowchart TD
    I["Issue / 自然语言需求"] --> P["Planner<br/>拆解任务"]
    P --> S["Code Search<br/>文件、函数、AST 检索"]
    S --> C["Coder<br/>生成结构化补丁"]
    C --> G["Human Gate<br/>确认是否写入"]
    G --> X["Sandbox<br/>Docker 执行测试"]
    X --> Q{"测试通过？"}
    Q -- "是" --> R["Reviewer<br/>检查 diff、风险和测试"]
    Q -- "否" --> F["Reflector<br/>分析测试日志"]
    F --> C
    R --> O["输出 diff、测试报告、PR 摘要"]
~~~

### 5.4 逐步开发顺序

#### Step 1：做普通代码工具

先不接 Agent，写确定性的 Python 函数：

- list_tree：列出文件树。
- search_code(query)：搜索代码。
- read_file(path)：读取文件。
- get_git_diff：获取 diff。
- run_tests：运行 pytest。

要求：

- 每个工具有输入模型和输出模型。
- 路径必须限制在目标仓库目录内。
- 工具失败返回结构化错误。

#### Step 2：实现固定 Workflow

先由代码固定流程：

~~~text
读取 Issue
  -> 搜索候选文件
  -> 读取代码
  -> 请求模型生成补丁
  -> 人工确认
  -> 运行测试
  -> 输出报告
~~~

学习重点：

- 固定流程的可控性。
- 什么时候不需要 Agent。
- 如何为每一步记录状态。

#### Step 3：加入 Code RAG 和 AST

索引内容：

- 文件路径。
- 函数名。
- 类名。
- import 关系。
- docstring。
- 测试函数。
- README。

检索方式：

- 文件名和路径搜索。
- 关键词搜索。
- 向量检索。
- AST 结构过滤。

先让 Agent 只读和检索，不允许写文件。

#### Step 4：加入 Tool Calling 和补丁

让模型根据任务选择：

- 搜索代码。
- 读取文件。
- 获取测试文件。
- 生成 patch。
- 查询 diff。

补丁不要让模型直接覆盖整文件，优先使用结构化 patch：

~~~text
Patch:
  file: app/routes/tasks.py
  operation: replace
  start_marker: ...
  end_marker: ...
  replacement: ...
~~~

#### Step 5：加入测试、反思和重试

测试失败后，把以下内容交给 Reflector：

- 原始 Issue。
- 当前 diff。
- 测试命令。
- stdout。
- stderr。
- 最近一次修改说明。

第一版只允许重试 1 次，防止 Agent 死循环。

#### Step 6：把工具改造成 MCP Server

先比较两种接入方式：

1. Tool Calling：工具函数直接注册在 RepoPilot 内部。
2. MCP：文件、Git、测试工具独立作为 MCP Server，RepoPilot 通过协议发现和调用。

MCP 工具可以包括：

- search_files。
- read_file。
- get_git_diff。
- run_tests。
- scan_secrets。

学习重点：

- 工具和 Agent 解耦。
- schema 标准化。
- 工具权限控制。
- 多个客户端复用同一工具服务。

#### Step 7：加入沙箱和人工确认

安全边界：

- 只允许访问目标仓库目录。
- 禁止访问 .env、SSH key 和系统目录。
- Docker 内运行测试。
- 默认禁止外网。
- 限制 CPU、内存和执行时间。
- 写文件、运行命令、创建 PR 前暂停确认。

### 5.5 RepoPilot 的完成标准

- 能读取一个自建 Python 仓库。
- 能从 Issue 定位候选文件。
- 能生成结构化 diff。
- 能在 Docker 中运行 pytest。
- 测试失败后能分析并修复一次。
- 能展示完整执行轨迹。
- 至少有 20 个 Issue benchmark。
- 能对比 Workflow 与 Agent 的成功率、耗时和成本。
- 有 README、架构图、录屏和失败案例。

### 5.6 这个项目主要学什么

| Agent 技能 | RepoPilot 中的实现 |
|---|---|
| Code RAG | 文件、函数、AST、测试检索 |
| Tool Calling | 搜索、读取、测试、diff 工具 |
| Planning | Issue 拆解和候选文件定位 |
| State | 保存任务阶段、diff、测试结果 |
| Reflection | 根据测试日志生成修复方案 |
| Retry | 限次数的失败重试 |
| HITL | 写入、执行命令、PR 前人工确认 |
| MCP | 将工具从 Agent 中独立出来 |
| Sandbox | Docker 隔离测试执行 |
| Evaluation | Issue benchmark、成功率、成本 |
| Guardrail | 路径、命令、密钥和网络限制 |

---

## 6. 两个项目中要主动比较的概念

### 6.1 Workflow 和 Agent

做法：

- StudyMate 先固定“检索 -> 回答”。
- 再让模型自主选择搜索、获取笔记或制定计划。
- 比较两者的成功率、延迟、Token 成本和可控性。

结论应该能说清：

- 流程固定、风险高、步骤清楚时优先 Workflow。
- 需要动态选择工具、路径不固定时才使用 Agent。

### 6.2 普通 Tool Calling 和 MCP

做法：

- 先把工具作为 Python 函数直接注册。
- 再把同样的工具移到独立 MCP Server。
- 使用相同测试集比较调用结果。

结论应该能说清：

- Tool Calling 解决模型如何调用工具。
- MCP 解决工具如何标准化描述、发现和跨客户端复用。
- MCP 不会自动解决权限、安全和工具质量问题。

### 6.3 Retry 和 Reflection

做法：

- Retry：同样输入再次执行。
- Reflection：把失败日志、当前结果和目标重新交给模型分析，再生成修复方案。

结论应该能说清：

- 网络超时、临时限流适合 Retry。
- 测试失败、参数错误、逻辑错误更适合 Reflection。
- Reflection 成本更高，必须限制次数。

### 6.4 Memory 和 RAG

做法：

- StudyMate 用 Memory 保存会话和学习偏好。
- 用 RAG 检索外部学习资料。

结论应该能说清：

- Memory 保存与用户或任务相关的状态。
- RAG 查询外部知识。
- 两者都放进上下文会增加 Token 和污染风险，需要分层加载。

### 6.5 Single-Agent 和 Multi-Agent

做法：

- RepoPilot 第一版只使用一个 Agent。
- 只有当 Planner、Coder、Reviewer 的权限、上下文和评估指标明显不同，再拆成多个角色。

结论应该能说清：

- 多 Agent 带来更多协调成本、Token 成本和失败点。
- 角色边界清楚、任务可以并行、需要独立审查时才值得拆分。

---

## 7. 六周执行计划

### 7.1 总体路线图

~~~mermaid
gantt
    title 从零 AI Coding 到 Agent 项目的六周计划
    dateFormat  YYYY-MM-DD
    axisFormat  %m/%d
    section AI Coding 基础
    Git、Issue、测试、项目规范       :s0, 2026-08-03, 2d
    StudyMate 固定 RAG Workflow      :s1, after s0, 5d
    section StudyMate
    Structured Output + Tool Calling :s2, after s1, 5d
    Memory + Evaluation              :s3, after s2, 4d
    section RepoPilot
    自建 Todo API 与代码工具           :s4, after s3, 5d
    Code RAG + AST + Patch            :s5, after s4, 7d
    测试、Reflection、HITL             :s6, after s5, 7d
    MCP + Sandbox + Trace              :s7, after s6, 7d
    section 求职产出
    README、Demo、指标、面试讲稿       :s8, after s7, 5d
~~~

### 7.2 每周交付看板

| 周次 | 学习主题 | 必须交付 | 通过标准 |
|---:|---|---|---|
| 第 1 周 | AI Coding 基础 + StudyMate Workflow | CLI、资料导入、固定 RAG 流程 | 能回答带引用的问题 |
| 第 2 周 | Structured Output + Tool Calling | 4 个工具、Pydantic 模型 | 工具参数和错误可校验 |
| 第 3 周 | Memory + Evaluation | 会话、偏好、30 条测试集 | 有引用率、拒答率、成本数据 |
| 第 4 周 | RepoPilot 基础 | 自建 Todo API、文件工具、固定 Workflow | 能根据 Issue 生成 diff |
| 第 5 周 | Code RAG + Reflection + HITL | AST 检索、测试、一次自动修复 | 20 个 Issue benchmark |
| 第 6 周 | MCP + Sandbox + 求职材料 | MCP Server、Docker、Demo、README | 能完整讲清 Agent 闭环 |

### 7.3 每周固定节奏

~~~mermaid
flowchart LR
    M["周一<br/>理解一个概念"] --> T["周二-周三<br/>让 AI 实现小组件"]
    T --> P["周四<br/>接入当前项目"]
    P --> V["周五<br/>测试、看日志、看 diff"]
    V --> R["周末<br/>写 README 和面试答案"]
    R -. "把失败案例变成下周 Issue" .-> M
~~~

建议时间分配：

| 工作内容 | 占比 | 说明 |
|---|---:|---|
| 阅读和理解 | 20% | 官方文档、源码、设计取舍 |
| 编码实现 | 45% | 只围绕当前阶段的 MVP |
| 测试评估 | 20% | 测试集、失败样本、成本记录 |
| 文档与面试 | 15% | README、架构图、项目讲稿 |

---

## 8. 评估指标

### StudyMate

- 检索 Recall@K。
- 引用正确率。
- 回答正确率。
- 无依据拒答率。
- Tool Calling 成功率。
- 平均 Token 成本。
- 平均响应时间。

### RepoPilot

- Issue 一次修复成功率。
- Reflection 后修复成功率。
- 测试通过率。
- 候选文件定位准确率。
- 工具调用成功率。
- 平均重试次数。
- 平均 Token 成本。
- 人工介入比例。
- 高风险操作拦截数量。

不要只记录“效果很好”。每个指标都要写清：

- 测试集怎么构造。
- 成功条件是什么。
- 基线是什么。
- 哪些失败没有被解决。

---

## 9. P0 / P1 学习优先级

### P0：必须完成

- Python 项目结构、Git、pytest。
- AI Coding 的 Issue -> Plan -> Code -> Test -> Review 流程。
- Structured Output / JSON Schema / Pydantic。
- Tool Calling。
- RAG 基础和引用溯源。
- 单 Agent 和固定 Workflow 的差异。
- Memory 与 Evaluation 基础。
- Code RAG、AST、Patch。
- Reflection、Retry、HITL。
- Docker 沙箱和工具权限。

### P1：在主项目中补齐

- MCP Server。
- FastAPI 和流式输出。
- SQLite / PostgreSQL 任务状态。
- Redis / 异步任务。
- LangGraph Persistence。
- Trace 和成本统计。
- Hybrid Search、Rerank。

### 暂时不要做

- 从零训练大模型。
- RLHF / SFT 深度训练。
- 一开始就做复杂 Multi-Agent。
- 一开始就支持多种编程语言。
- 直接让 Agent 修改大型真实仓库。
- 只做聊天 UI，不做测试和评估。

---

## 10. 最终公开作品集

六周结束时，建议有：

### StudyMate

- 一个可以本地运行的学习资料 Agent。
- 30 条评估问题。
- 引用和拒答示例。
- Tool Calling 演示。
- README、截图、指标。

### RepoPilot

- 一个自建的 sample-todo-api 目标仓库。
- 20 个 Issue benchmark。
- Code RAG 和 AST 检索。
- 自动生成 diff。
- Docker 测试与一次反思修复。
- MCP Server。
- 执行轨迹、失败案例和成本数据。

### 面试讲解顺序

~~~text
先讲 StudyMate：
我如何从固定 Workflow 逐步加入 Tool Calling、RAG、Memory 和 Evaluation。

再讲 RepoPilot：
我如何把相同的 Agent 原理迁移到代码仓库，加入 Code RAG、Patch、测试、Reflection、MCP、HITL 和 Sandbox。

最后讲取舍：
哪些地方坚持使用 Workflow，哪些地方才使用 Agent，以及为什么没有一开始就做 Multi-Agent。
~~~

---

## 11. 完成标准

这条路线完成的标志不是“学过 LangChain 或 LangGraph”，而是你可以：

- 从零创建项目并让 AI Coding 工具按 Issue 逐步实现。
- 独立解释 Workflow、Agent、Tool Calling、MCP、Memory、RAG、Reflection、HITL 的区别。
- 用测试集验证 Agent，而不是只展示一次成功运行。
- 对失败、成本、延迟和安全边界有记录。
- 公开展示两个不涉及公司机密的项目。
- 用 3 分钟讲清一个项目的背景、架构、难点、指标和复盘。

