# StudyMate 学习路线与每日任务

## 当前进度

已完成的第一阶段能力：

- 本地 Markdown/TXT 知识库、切分、关键词检索和来源引用。
- OpenAI-compatible 模型调用与 NewAPI/Claude 网关兼容。
- 原生 Tool Calling、`search_knowledge`、`open_document`。
- 最小 Agent Runtime、Agent Loop、工具预算、空检索和最大步数保护。
- 当前进程内的短期对话历史。
- Agent Trace、`/trace` 和问题/回答/执行轨迹的 JSONL 落盘。
- Agent Evaluation、JSONL 评测集和 JSON 评测报告。
- 中英文领域词查询扩展、停用词过滤、查询归一化、短语匹配以及标题/路径加权的 BM25 风格检索。
- `SearchIndex` 可替换检索接口，已实现 `InMemorySearchIndex` 和 `SQLiteFTS5SearchIndex` 两个词法检索后端。
- `compare-search` 检索对比日志，用于比较内存 BM25 风格检索与 SQLite FTS5/BM25。
- `/trace` 可显示 Agent 检索排名，`/output` 可导出单轮问答、引用、排名和 Trace。
- 完整 pytest 已通过：`99 passed`；当前测试和主流程不调用 Embedding API。

尚未完成的能力不应写进简历：Embedding/向量检索、Reranker、混合检索、跨进程会话恢复、MCP Server 和 AI Coding Agent。

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

### 第 2 天：学习并实现 Agent Eval（已完成）

目标：理解“单元测试验证代码分支”和“Agent Eval 验证整体行为”的区别。

学习和动手顺序：

1. 阅读 `2026-08-10-agent-observability-and-evaluation.md` 的 Eval 部分。
2. 设计 5 到 8 条固定场景：正常检索、空检索、重复工具调用、非法工具参数、引用校验、最终 JSON 变体。
3. 将场景存为独立 JSONL 数据集，不使用 API Key、个人对话或公司资料。
4. 实现一个本地 Eval Runner，输出通过数、失败原因和可读报告。
5. 将一条真实发现过的回归问题补成 Eval 用例。

完成标准：一次命令可以重跑所有 Agent 行为场景，并能指出失败发生在检索、工具、停止条件、解析还是引用校验。当前命令为 `py -m studymate eval`，评测集为 `tests/eval/questions.jsonl`。

### 第 3 天：查询规范化与查询改写（第一版已完成）

目标：解决 `agentloop` 与 `agent loop` 这类写法差异，理解“检索前处理”与“模型改写查询”的取舍。

先实现无需模型的规则：大小写归一、连字符与下划线归一、常见 CamelCase/拼写变体、动作词和停用词清理。当前 `rewrite_query()` 只处理检索 query，不改写最终回答，也不调用模型；例如将“请先搜索 Agent Loop 的资料，再打开命中的文档，结合原文解释它如何运行”压缩为 `agent loop`。

完成标准：为 `agentloop`、`agent runtime`、中文英文混合术语和带工具规划指令的 query 新增可重复的检索测试，且不会无故扩大召回范围。规则实现和小规模回归测试已完成，下一步用评测集验证。

### 第 4 天：RAG 检索质量（检索基线已完成）

目标：理解关键词检索、Embedding、向量检索、混合检索、重排序和引用校验各自解决什么问题。

已完成检索接口抽象、内存 BM25 风格基线、SQLite FTS5/BM25 后端和 `Hit@K`、Recall@K、Precision@K、MRR、Citation Accuracy/Coverage、Abstention Rate/Accuracy 指标。接下来使用 `compare-search` 观察两个词法后端的排名，再将结果纳入评测集。

### 下一步：查询改写与检索评测（2026-08-20）

目标：不使用 Embedding，先验证规则查询改写，再使用评测集比较内存 BM25 风格检索和 SQLite FTS5/BM25。

学习和动手顺序：

1. 阅读 `README.md` 的查询改写说明和 `docs/06-evaluation.md`，复习改写前后 query 与 Hit@K、Recall@K、Precision@K、MRR 的关系。
2. 运行 `compare-search`，比较同一问题在两个本地后端中的排名差异；再确认 Agent Trace 中的 `rewritten_query`。
3. 为正常问题、带搜索动作的问题、中文、英文、CamelCase、文件名和 API 术语各准备可复现的检索问题。
4. 检查目标来源是否真的能回答问题，修正评测集标注，并确认改写没有把未知主题变成错误命中。
5. 运行完整 pytest，记录查询改写对 Agent、Trace 和 Eval 的影响。

完成标准：能够从指标、原始 query、改写 query 和人工检查四方面说明检索失败原因，并且不产生 Embedding API 请求。

### 2026-08-19：对比查询检索验证（已完成）

本轮使用 220 份本地知识库，对以下四类问题运行了 `compare-search`：中文比较、英文比较、中文定义题和英文定义题。内存 BM25 风格后端与 SQLite FTS5/BM25 后端都完成返回；比较问题的两个主题均进入 Top-K，定义题也能召回 MCP 协议定义相关证据。

需要注意：比较问题会分别检索主题后交错合并，所以交错后的展示顺序不是跨主题全局分数排序；内存和 SQLite 的原始分数也不能直接互比。下一次应按主题统计 Hit@K、Recall@K、Precision@K 和 MRR，再判断哪一个后端更适合当前知识库。

本轮验证结果：完整 pytest 为 `93 passed`，新增了 `compare-search` 输出字段的回归测试；没有生成 Embedding 请求，也没有调用在线模型。

### 2026-08-20：紧凑术语完整覆盖（已完成）

上一轮对比发现，内存检索处理 `agentruntime` 时可能只命中 `agent`，把不完整的证据返回给用户；SQLite 因为 FTS5 的词项匹配恰好表现得更严格。这个问题不是 BM25 公式本身的问题，而是“允许部分词项覆盖”的过滤规则没有识别出紧凑术语已经表达了一个完整概念。

本轮增加了复合术语完整覆盖规则：当原始 query 中出现 `agentruntime`、`agentloop`、`toolcalling` 等已知紧凑写法时，先展开为多个词，再要求这些组成词全部命中同一个 Chunk。普通 `agent`、`agent runtime` 以及 `Claude Code 自定义工具` 等查询继续使用通用覆盖率规则，避免过度过滤有效证据。

当前验证结果：

- `agentruntime`：内存和 SQLite 都只返回同时包含 `agent`、`runtime` 的结果。
- `agentloop`：两个后端继续命中 `claude-code/07-agent-sdk/agent-loop.md`。
- `agent`：普通单词查询保持可用。
- `Claude Code 中如何定义自定义工具？`：中英文混合检索保持正常召回。
- 完整 pytest：`94 passed`。

本轮没有调用在线模型，也没有生成 Embedding 请求。

### 2026-08-20：预构建 SQLite FTS5 索引（已完成）

当前主流程已收敛为 SQLite FTS5/BM25：

- 新增 `build-index` 命令，负责扫描知识库、切分 Chunk 和重建数据库。
- Chat、Eval 和 `compare-search` 运行时只读打开预构建索引。
- 默认数据库为 `data/studymate-search.sqlite3`。
- 当前索引已生成：`221` 份文档、`40,866` 个 Chunk。
- 启动 Chat 后立即退出验证，SQLite 文件修改时间不变，确认启动没有触发重建。
- `--search-backend memory` 仍保留，主要用于学习和小规模对比，不作为主流程默认后端。

为什么 Chat 也使用 SQLite：Chat 中的 Agent 会在每次问题中调用 `search_knowledge`，SQLite 是这条真实问答路径的检索实现。为什么 Eval 也使用 SQLite：Eval 需要评估默认 Agent 路径拿到的实际证据是否命中预期来源；评测集负责判断，SQLite 负责提供结果，二者职责不同。

本轮暂不实现长短期记忆。当前对话历史仍只保存在进程内；跨进程会话恢复和长期记忆安排到下一次学习任务。

### 下一阶段：本地 RAG 与 Agent 工程化

按以下顺序扩展：

1. 先用预构建 SQLite 后端运行高价值 Agent Eval，记录默认主流程的基线。
2. 完善引用校验、证据不足时的拒答和 Trace 诊断。
3. 实现跨进程会话恢复与用户可控的记忆。
4. 将本地知识库工具包装成只读 MCP Server，再接入 MCP Client。
5. 在隔离工作区实现 AI Coding Agent 的文件扫描、受控编辑、测试运行和 Git Diff 审查。
6. 最后再对比 Embedding、向量数据库、混合检索、Reranker、LangGraph 和 OpenCode SDK；在没有评测证据前不启用这些额外依赖。

## 每次学习的固定闭环

```text
概念定义
  -> 在 StudyMate 中定位对应代码
  -> 编写或阅读一个测试场景
  -> 实际运行并观察 Trace/Eval
  -> 记录结论、边界和下一个问题
```

这个闭环比单独背框架 API 更适合准备 Agent 工程岗位面试。
