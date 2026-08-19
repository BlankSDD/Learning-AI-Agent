# 2026-08-20：预构建 SQLite FTS5 索引

## 用户问题

SQLite 索引是否应该固定预制？如果知识库不变，是否不需要每次启动都重建？Chat 和 Eval 是否都应该使用 SQLite？长短期记忆暂时延后。

## 结论

是的。SQLite FTS5 索引是知识库 Chunk 的词法索引，不是每次对话都需要重新计算的临时对象。只要知识库源文件没有变化，索引可以重复使用。

索引生命周期现在明确为：

```text
knowledge/*.md / *.txt
        |
        |  python -m studymate build-index
        v
data/studymate-search.sqlite3
        |
        |  Chat / Eval / compare-search 只读打开
        v
search_knowledge -> SearchResult -> Agent 上下文
```

知识库发生变化后，由用户主动运行 `build-index`。本轮不做自动检测和增量更新，先保持行为简单、可解释、可验证。

## 新增命令

```powershell
py -m studymate build-index `
  --knowledge .\knowledge `
  --search-db .\data\studymate-search.sqlite3
```

当前索引构建结果：

- 文档数：`221`
- Chunk 数：`40,866`
- 数据库：`data/studymate-search.sqlite3`

## Chat 为什么使用 SQLite

Chat 不是只显示模型回答。用户提问后，Agent 可能调用 `search_knowledge`。因此 Chat 的检索后端就是 Agent 真实工作路径的一部分：

```text
用户问题 -> Agent 决策 -> search_knowledge -> SQLite FTS5/BM25 -> 模型回答
```

使用预构建 SQLite 可以避免每次启动 Chat 都重新扫描和切分约 4 万个 Chunk。

## Eval 为什么使用 SQLite

Evaluation 的职责是判断 Agent 行为是否符合预期，例如：

- 期望来源是否进入 Top-K；
- 工具调用是否正确；
- 是否正常结束；
- 回答是否包含必要词；
- 未知问题是否正确拒答。

SQLite 的职责是提供实际检索结果。Eval 使用 SQLite，是为了评估默认 Chat/Agent 路径，而不是因为 Evaluation 本身等于 SQLite 检索。

## 内存检索的定位

`InMemorySearchIndex` 保留在代码中，通过 `--search-backend memory` 或 `compare-search` 使用。它的价值是：

- 便于理解 BM25 风格计算；
- 便于写单元测试；
- 便于用小知识库比较不同后端。

它不再作为 Chat 和 Eval 的默认实现。

## 今日命令速查

以下命令在项目根目录执行。使用 `.venv` 时的完整写法如下：

### 1. 更新知识库后重建 SQLite 索引

如果只是新增或修改本地知识库文件，直接重建索引：

```powershell
.\.venv\Scripts\python.exe -m studymate build-index `
  --knowledge .\knowledge `
  --search-db .\data\studymate-search.sqlite3
```

如果先更新 Claude Code、OpenCode 或 Codex 在线文档，再重建索引：

```powershell
.\.venv\Scripts\python.exe -m studymate update-docs --only claude-code opencode codex
.\.venv\Scripts\python.exe -m studymate build-index `
  --knowledge .\knowledge `
  --search-db .\data\studymate-search.sqlite3
```

### 2. 查看 Agent Trace 和导出上一轮输出

启动 Chat：

```powershell
.\.venv\Scripts\python.exe -m studymate chat --knowledge .\knowledge
```

进入交互界面后输入：

```text
/trace
/output
/output .\outputs\mcp-question.json
```

`/trace` 用来观察 Agent 是否按预期工作，重点查看步骤、工具调用、工具结果、停止原因和检索 Top-K 排名；它相当于面向开发人员的执行诊断记录，不会作为历史上下文发送给模型。`/output` 用来保存上一轮问答的结构化结果，方便后续查看问题、回答、引用、检索排名和 Trace。

### 3. 对比两种检索后端

```powershell
.\.venv\Scripts\python.exe -m studymate compare-search `
  --knowledge .\knowledge `
  --query "agent loop 和 agent runtime 有什么区别？" `
  --query "What is MCP?" `
  --output .\logs\search-comparison.jsonl
```

`compare-search` 只比较内存 BM25 风格检索和 SQLite FTS5/BM25 的检索结果，不调用模型，也不参与 Chat 的 Agent Loop。终端会显示每个后端的排名、分数、路径、行号和命中词，`--output` 指定的 JSONL 会保存同样的诊断信息。两个后端的分数只适合在各自后端内部比较，不能直接把分数绝对值互相比较。

## 运行时验证

启动 Chat 后立即输入 `/quit`：

```text
StudyMate loaded 221 documents. Search backend: sqlite.
```

启动前后数据库修改时间保持不变，证明运行时是只读打开，没有自动重建索引。

## 当前未实现

本轮没有实现：

- 长期记忆；
- 跨进程会话恢复；
- 知识库变化自动检测；
- SQLite 增量索引更新。

## 今日学习与工作总结

今天完成了两类检索可靠性工作：

- 修复紧凑术语的部分命中问题。`agentruntime`、`agentloop`、`toolcalling` 等写法会先展开为组成词，并要求组成词在同一个 Chunk 中完整命中，避免只命中 `agent` 的不完整证据。
- 将 SQLite FTS5/BM25 从“启动时临时重建”调整为“显式预构建、运行时只读”。`build-index` 负责扫描、切分和建立索引；Chat、Eval 和 `compare-search` 负责使用索引。知识库源文件和 SQLite 索引是两个不同的对象，前者变化后才需要重新执行 `build-index`。

今天也明确了几个边界：SQLite FTS5/BM25 是知识库检索索引，不是 Agent Memory；Trace 是开发诊断记录，不是模型记忆；Eval 是离线检查，不参与 Agent Loop 的停止控制；Embedding 和 Reranker 仍未接入主流程。

本轮验证：当前索引包含 `221` 份文档和 `40,866` 个 Chunk；完整 pytest 为 `99 passed`；没有生成 Embedding 请求。

## 明日学习与开发计划（2026-08-21）

主题：Agent Memory 与跨进程短期会话恢复。

学习顺序：

1. 区分上下文窗口、进程内对话历史、跨进程短期会话和用户可控长期记忆。
2. 对比 SQLite 知识库索引、Trace、Chat history 和 Memory 的数据职责与生命周期。
3. 阅读 `src/studymate/chat.py`、`src/studymate/agent.py` 和 `docs/04-data-model.md`，画出一次 `/resume` 恢复会话的消息流。
4. 先用 TDD 设计 `sessions`、`messages` 两张表和 `/new`、`/sessions`、`/resume` 命令，再实现跨进程短期会话恢复。
5. 运行已有 pytest，并验证恢复的历史消息会进入模型上下文，而 Trace 和知识库正文不会被错误混入长期记忆。

完成标准：退出 Chat 后重新启动，能够通过会话 ID 恢复最近对话；创建新会话不会继承旧会话消息；`/trace` 仍然只做诊断；暂不让模型自动把所有内容写入长期记忆。

这些内容放到下一次学习，先区分清楚“知识库索引”和“Agent 记忆”的职责。
