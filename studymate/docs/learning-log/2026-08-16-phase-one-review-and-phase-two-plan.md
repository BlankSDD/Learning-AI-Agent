# 2026-08-16 第一阶段复盘与第二阶段计划

## 一、第一阶段目标

StudyMate 第一阶段的目标，是把一个固定的 RAG 问答流程升级为一个最小、可验证的 Agent Runtime：

```text
用户问题
  -> Agent 判断下一步
  -> 调用受限工具
  -> 观察工具结果
  -> 继续调用工具或生成最终答案
  -> 校验引用并记录 Trace
```

当前已经完成：

- 本地 Markdown / TXT 知识库递归加载和文档切分。
- 本地关键词检索和中英文领域词扩展。
- `search_knowledge` 和 `open_document` 两个只读工具。
- OpenAI-compatible Tool Calling。
- `AgentRunner`、工具预算、最大步数和空检索保护。
- 引用校验，打开的文档片段也可以作为引用证据。
- 当前进程内的短期对话历史。
- Agent Trace、`/trace` 和 JSONL 问答落盘。
- Agent Evaluation、JSONL 评测集和 JSON 评测报告。
- 当前自动化测试：`63 passed`。
- 当前评测集：`5/5 passed`。

## 二、第一阶段关键概念问答

### 1. Workflow 和 Agent 的区别是什么？

Workflow 的步骤由程序预先定义，模型通常只负责生成、分类或抽取某一步的结果。Agent 接收目标后，由模型决定下一步是否调用工具、调用哪个工具，以及是否继续循环。

```text
Workflow：程序决定步骤 -> 模型完成步骤
Agent：模型决定下一步 -> 程序执行受限动作 -> 结果回传模型
```

Workflow 更容易预测、测试和控制；Agent 更灵活，但必须处理循环、工具错误、权限、成本、停止条件和评估。

StudyMate 的演进是：先有固定 RAG Workflow，再把固定检索步骤暴露为 Agent 可以自主选择的工具。

### 2. 什么是 RAG？

RAG 是 Retrieval-Augmented Generation，即检索增强生成。系统先从外部知识库检索资料，再把资料作为上下文交给模型生成回答。

```text
加载资料 -> 文档切分 -> 检索 Top-K -> 组装上下文 -> 模型生成 -> 返回引用
```

RAG 解决“模型如何使用外部知识”，Agent 解决“模型如何决定下一步动作”。两者不是同一个概念，但可以组合：StudyMate 的 Agent 通过 `search_knowledge` 使用 RAG。

### 3. Tool Calling 和 MCP 的区别是什么？

- Tool Calling 是一次模型请求中的调用机制。应用发送工具 Schema，模型返回工具名称和参数，应用执行后把结果传回模型。
- MCP 是标准化的能力接入协议，规定客户端如何发现和使用外部工具、资源和提示词。
- Tool Calling 关注“这一次模型如何调用工具”；MCP 关注“工具能力如何被多个 Agent 客户端统一接入”。

第一阶段的 StudyMate 使用本地 Python 工具注册，没有接入 MCP。后续可以把知识库工具封装为 MCP Server。

### 4. 工具是不是脚本？

工具通常由代码实现，但工具不等于脚本。

- 脚本是可以独立运行的程序。
- 工具是暴露给 Agent 的受约束能力，必须有名称、描述、参数 Schema、执行函数、错误处理和权限边界。
- 工具可以由 Python 函数、类方法、HTTP API、Shell 命令或 MCP Server 实现。

StudyMate 中，模型只能看到 `ToolRegistry` 暴露的 Schema，不能直接执行 Python、Shell 或任意文件系统操作。

### 5. AgentRunner 是什么？它和模型是什么关系？

`AgentRunner` 不是 AI 模型，而是模型调用和工具执行之间的控制器。

```text
AgentRunner 发送问题和工具 Schema
  -> 模型返回 tool_calls
  -> ToolRegistry 校验并执行工具
  -> 工具结果作为 observation 回传模型
  -> 模型继续调用工具或返回最终 JSON
```

模型负责决定“调用什么”；StudyMate 负责决定“什么能执行、如何执行、执行几次以及什么时候停止”。

### 6. Agent Loop 和 Agent Runtime 的区别是什么？

Agent Loop 是一次任务内部的循环逻辑：

```text
判断 -> 行动 -> 观察 -> 再判断 -> 结束
```

Agent Runtime 是承载这个循环的完整运行环境，包括：

- 模型适配。
- 消息和状态管理。
- 工具注册和参数校验。
- 权限、工具预算和最大步数。
- 错误处理。
- 引用校验。
- Trace 和评测接口。

在 StudyMate 中，`AgentRunner.run()` 中的多轮模型、工具、观察过程是 Agent Loop；`AgentRunner`、`ToolRegistry`、`OpenAIAnswerer`、引用校验、预算和 Trace 共同组成最小 Agent Runtime。

### 7. ChatService 和 AgentRunner 的职责是什么？

最初的 ChatService 是固定的一次性 RAG 流程：

```text
用户输入 -> 意图分类 -> 固定检索 -> 调用一次模型 -> 校验引用 -> 保存历史
```

当前版本中：

- `ChatService` 负责 CLI 命令、短期历史、更新知识库和最终展示。
- `AgentRunner` 负责一次任务内部的工具决策和循环。
- `OpenAIAnswerer` 负责 OpenAI-compatible 模型请求和响应解析。
- `ToolRegistry` 负责工具 Schema、参数校验和分发。
- `KnowledgeTools` 负责真正的检索和文档读取。

### 8. 为什么代码放在 `src/`？

这是 Python 项目的 `src layout`：

```text
studymate/
  src/studymate/       # 生产代码
  tests/               # 测试代码
  knowledge/           # 学习资料
  docs/                # 设计文档和学习记录
  pyproject.toml       # 项目配置
```

它可以避免测试时意外导入项目根目录的源码，并明确区分可安装的生产包、测试、知识库和文档。当前项目已经有多个模块、CLI 和测试，因此比在根目录放一个 `main.py` 更适合继续演进。

### 9. 流式请求和 Agent Loop 是什么关系？

流式请求只是模型响应的传输方式，不等于 Agent Loop。流式模式下，工具名称和参数会分成多个增量返回，StudyMate 需要先在本地聚合，再交给工具注册表校验和执行。

因此：

- 流式和非流式都可以实现 Agent Loop。
- 流式影响响应如何传输。
- Agent Loop 影响模型、工具、观察结果之间如何循环。
- 当前 CMD 会聚合完整结果后一次性显示，不是逐 Token 打印。

### 10. `/trace` 是历史记录、日志还是 Memory？

它和日志有相似之处，但更准确地说是一次 Agent Run 的结构化执行记录。

| 数据 | 作用 | 是否发送给模型 |
| --- | --- | --- |
| 对话历史 | 帮助模型理解当前会话上下文 | 是 |
| Agent Trace | 记录步骤、工具、结果、停止原因和耗时 | 否 |
| 长期 Memory | 跨会话保存偏好、进度和事实 | 当前未实现 |

Trace 落盘也不等于可恢复会话。StudyMate 当前不会在重启后从 Trace 恢复历史，也不会自动把 Trace 发送给模型。

### 11. Evaluation 是什么？

Evaluation 是对 Agent 整体行为的检查，但不是控制循环停止的代码。

- `AgentRunner` 负责运行和停止：`final_answer`、`empty_search`、`max_steps` 等。
- `EvaluationRunner` 在运行结束后判断结果是否达标。

```text
AgentRunner：这次运行发生了什么？什么时候停止？
Evaluation：这次运行是否符合预期？
Trace：把这次运行的过程记录下来
```

评测集位于 `tests/eval/questions.jsonl`，每行是一条“问题 + 预期行为”：

```json
{
  "id": "q001",
  "input": "MCP 是什么？",
  "expected_sources": ["claude-code/04-agent-development/mcp-quickstart.md"],
  "required_terms": ["MCP"],
  "expected_tools": ["search_knowledge"],
  "expected_stop_reason": "final_answer",
  "should_abstain": false
}
```

评测器会检查答案、循环是否正常结束、停止原因、工具调用、工具执行状态、检索来源、引用、关键词和拒答行为。它类似“测试整个 Agent 任务”，而 pytest 单元测试通常只测试一个函数或一个确定分支。

### 12. 第一阶段如何处理 Agent 无限循环？

不能只依赖模型自己停止。模型可能重复请求同一个工具或持续检索泛化结果，因此运行时必须有硬限制：

- 总步数上限 `max_steps=5`。
- 每个工具默认每次任务最多调用一次。
- 空检索直接以 `empty_search` 结束。
- 工具预算耗尽后进入无工具最终化。
- 工具错误作为 observation 返回模型，不直接让进程崩溃。

## 三、第一阶段代码映射

| 概念 | 主要代码 |
| --- | --- |
| Agent Loop / Runtime | `src/studymate/agent.py` |
| Tool Schema 和分发 | `src/studymate/tool_registry.py` |
| 知识库工具 | `src/studymate/tools.py` |
| 模型和 Tool Calling | `src/studymate/llm.py` |
| ChatService / 命令 / 历史 | `src/studymate/chat.py`、`src/studymate/input.py` |
| 文档加载和切分 | `src/studymate/ingest.py` |
| 本地检索 | `src/studymate/search.py` |
| 引用校验 | `src/studymate/citations.py` |
| Trace | `src/studymate/trace.py` |
| Evaluation | `src/studymate/evaluation.py` |

## 四、第二阶段方向：RAG 检索质量优化

### 为什么先做检索，而不是继续增加工具？

第一阶段评测已经能判断 Agent 是否正确调用工具和结束，但 Agent 最终回答质量很大程度取决于检索结果。如果检索召回了错误文档，Agent 即使循环正常、工具成功、回答格式正确，也可能给出不准确的答案。

第二阶段的目标是：

```text
让 Agent 更稳定地找到正确文档、引用正确片段，并在没有证据时拒答
```

### 需要学习的内容

#### 1. 查询规范化和查询改写

学习以下问题：

- `agentloop` 和 `agent loop` 如何归一化？
- 大小写、连字符、下划线、CamelCase 如何处理？
- 中文术语如何映射到英文官方文档？
- 规则改写和模型改写的成本、延迟和可控性有什么区别？

当前已实现第一版规则：中文领域词扩展、停用词过滤、标题和路径加权。第二阶段要继续用评测集验证它不会扩大无关召回。

#### 2. BM25 和 SQLite FTS5

学习 BM25 的词频、逆文档频率和文档长度归一化，理解它为什么比简单关键词计数更适合全文检索。

StudyMate 下一步可以把当前 `InMemorySearchIndex` 抽象为检索接口，并增加 SQLite FTS5 后端：

```text
Markdown / TXT
  -> Chunk
  -> SQLite FTS5 / BM25
  -> Top-K SearchResult
  -> Agent Context
```

当前内存关键词检索保留为 baseline，用于对比改造前后的效果。

#### 3. RAG 检索评估指标

需要掌握：

- `Hit@K`：期望来源是否出现在前 K 个结果中。
- `Recall@K`：相关来源被召回的比例。
- `Precision@K`：前 K 个结果中相关结果的比例。
- `MRR`：第一个相关结果的排名倒数。
- Citation Accuracy：最终引用是否来自正确证据。
- Abstention Rate：无证据问题是否正确拒答。

当前 Evaluation 已经检查来源是否命中，第二阶段要把布尔结果扩展成这些可比较的数值指标。

#### 4. Chunking

需要理解：

- 固定字符长度切分的优缺点。
- 按标题、段落和语义边界切分。
- Chunk 大小、Overlap 对召回和 Token 成本的影响。
- 引用行号如何在切分后保持准确。

#### 5. Reranker 和 Embedding

先理解它们解决的问题，再决定是否实现：

- Embedding 将文本和查询映射到向量空间，用于处理同义表达和语义相似度。
- Reranker 对初步召回结果进行更精细的相关性排序。
- 混合检索将关键词检索的精确匹配和向量检索的语义召回结合起来。

不建议第二阶段一开始就引入复杂向量数据库。先完成 BM25 和评测基线，再用数据判断是否需要 Embedding。

## 五、第二阶段开发顺序

### 第 1 步：扩充评测集

增加到 15～20 条，至少覆盖：

- Agent 基础概念。
- MCP、Tool Calling、Agent Loop。
- 中英文混合术语。
- 需要打开文档的深度问题。
- 知识库不存在的问题。
- 工具错误和引用异常。

完成标准：所有问题都有明确的期望来源、关键词、工具和停止行为。

### 第 2 步：实现检索指标

在现有 `EvaluationReport` 中增加 Hit@K、MRR、引用准确率、拒答率和平均延迟，并保留每题 Trace。

完成标准：一次评测可以同时回答“Agent 是否完成任务”和“检索是否找到正确资料”。

### 第 3 步：抽象检索接口

让 Agent 只依赖统一的 `search(query, top_k)` 接口，使内存关键词检索和 SQLite FTS5 可以互换。

完成标准：不改 Agent 工具契约即可切换检索后端。

### 第 4 步：增加 SQLite FTS5 / BM25

建立本地索引、写入 Chunk 元数据，使用同一评测集对比旧版和新版。

完成标准：BM25 版本在中英文混合问题、长文档和多来源文档上的 Hit@K 不低于当前 baseline，并且引用行号仍然正确。

### 第 5 步：评估 Embedding 和 Reranker

只有当评测集显示 BM25 仍无法解决同义表达或语义问题时，再增加 Embedding、向量检索或 Reranker。

## 六、第二阶段之后的路线

RAG 检索质量稳定后，再按以下顺序扩展：

1. 跨进程会话恢复和用户可控的长期 Memory。
2. 工具超时、重试、幂等性和权限策略。
3. 将本地知识库工具封装为 MCP Server，并研究 MCP Client。
4. 单独构建 AI Coding Agent：工作区扫描、文件读取、代码搜索、受控编辑、运行测试和 Git Diff 审查。
5. 对比 LangGraph、OpenCode SDK 等框架与手写 Runtime 的边界。

当前不要把 MCP、长期 Memory 和 AI Coding Agent 同时加入 StudyMate。先用第二阶段把“检索质量 -> 评测指标 -> Agent 回答质量”的闭环做扎实。

## 七、第二阶段学习闭环

```text
学习检索概念
  -> 阅读当前搜索实现
  -> 为问题加入评测样本
  -> 修改一个检索策略
  -> 运行 pytest 和 eval
  -> 对比报告
  -> 记录结论和失败样本
```
