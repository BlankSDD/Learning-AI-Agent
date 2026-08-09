# StudyMate 学习路线与每日任务

## 当前进度

已完成的第一阶段能力：

- 本地 Markdown/TXT 知识库、切分、关键词检索和来源引用。
- OpenAI-compatible 模型调用与 NewAPI/Claude 网关兼容。
- 原生 Tool Calling、`search_knowledge`、`open_document`。
- 最小 Agent Runtime、Agent Loop、工具预算、空检索和最大步数保护。
- 当前进程内的短期对话历史。
- Agent Trace、`/trace` 和问题/回答/执行轨迹的 JSONL 落盘。

尚未完成的能力不应写进简历：Agent Eval、查询改写、Embedding/混合检索、跨进程会话恢复、MCP Server 和 AI Coding Agent。

## 按顺序学习

### 第 1 天：理解 Agent Trace

目标：区分对话历史、Trace 和长期记忆；能从一次 Trace 解释 Agent 为什么调用工具、为什么停止。

学习和动手顺序：

1. 阅读 `2026-08-09-agent-foundations.md` 中 Agent Loop、Runtime 和 Trace 的问答。
2. 阅读 `src/studymate/trace.py`，理解 Trace 的数据结构和 JSONL 落盘格式。
3. 阅读 `src/studymate/agent.py`，找到每一步何时创建 Trace、何时记录工具、何时写入停止原因。
4. 启动 CLI，提一个会触发检索的问题，再输入 `/trace`。
5. 打开启动时显示的 `traces/session-*.jsonl`，核对问题、回答和步骤摘要是否一致。

完成标准：能用自己的话解释 `final_answer`、`empty_search`、`max_steps` 三种停止原因，并说明 Trace 为什么不应回传给模型。

### 第 2 天：学习并实现 Agent Eval

目标：理解“单元测试验证代码分支”和“Agent Eval 验证整体行为”的区别。

学习和动手顺序：

1. 阅读 `2026-08-10-agent-observability-and-evaluation.md` 的 Eval 部分。
2. 设计 5 到 8 条固定场景：正常检索、空检索、重复工具调用、非法工具参数、引用校验、最终 JSON 变体。
3. 将场景存为独立 JSONL 数据集，不使用 API Key、个人对话或公司资料。
4. 实现一个本地 Eval Runner，输出通过数、失败原因和可读报告。
5. 将一条真实发现过的回归问题补成 Eval 用例。

完成标准：一次命令可以重跑所有 Agent 行为场景，并能指出失败发生在检索、工具、停止条件、解析还是引用校验。

### 第 3 天：查询规范化与查询改写

目标：解决 `agentloop` 与 `agent loop` 这类写法差异，理解“检索前处理”与“模型改写查询”的取舍。

先实现无需模型的规则：大小写归一、连字符与下划线归一、常见 CamelCase/拼写变体。之后再评估是否值得引入模型查询改写。

完成标准：为 `agentloop`、`agent runtime`、中文英文混合术语新增可重复的检索测试，且不会无故扩大召回范围。

### 第 4 天：RAG 检索质量

目标：理解关键词检索、Embedding、向量检索、混合检索、重排序和引用校验各自解决什么问题。

先为当前关键词检索建立小型评估集，再考虑 SQLite FTS5 或 Embedding。不要在没有评估基线时直接接向量数据库。

### 第 5 天以后：更完整的 Agent 能力

按以下顺序扩展：

1. 跨进程会话恢复与用户可控的记忆。
2. 更多只读工具和工具权限模型。
3. MCP：先做本地知识库工具的 MCP Server，再接入 MCP Client。
4. AI Coding Agent：工作区扫描、文件检索、受控编辑、运行测试、Git Diff 审查。
5. LangGraph、OpenCode SDK 等框架对比。此时再把自己写的 Runtime 与框架能力逐项对照。

## 每次学习的固定闭环

```text
概念定义
  -> 在 StudyMate 中定位对应代码
  -> 编写或阅读一个测试场景
  -> 实际运行并观察 Trace/Eval
  -> 记录结论、边界和下一个问题
```

这个闭环比单独背框架 API 更适合准备 Agent 工程岗位面试。
