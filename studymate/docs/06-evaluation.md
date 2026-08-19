# StudyMate Agent Evaluation

## 1. Evaluation 和停止条件的边界

StudyMate 中有两个相关但不同的概念：

- `AgentRunner` 的停止条件控制“什么时候结束循环”。例如最终回答、空检索、工具预算耗尽或达到最大步数。
- `EvaluationRunner` 控制“这次结束是否符合预期”。它在 AgentRunner 返回结果之后运行，不会参与工具调用，也不会修改 Agent 状态。

因此，`final_answer` 是一次正常结束的信号，但不等于答案一定正确；`max_steps` 通常说明循环没有按预期收敛，需要被评测报告标记出来。

## 2. 运行评测

在 `studymate` 目录执行：

```powershell
py -m studymate eval `
  --knowledge .\knowledge `
  --dataset .\tests\eval\questions.jsonl `
  --output .\evals\latest.json
```

检索指标默认使用 `K=5`，可以显式调整：

```powershell
py -m studymate eval --retrieval-k 5
```

`eval` 默认打开 `data/studymate-search.sqlite3` 这个预构建的 SQLite FTS5 索引，不会在评测启动时重新扫描知识库。首次使用或知识库文档发生变化后，先执行：

```powershell
py -m studymate build-index `
  --knowledge .\knowledge `
  --search-db .\data\studymate-search.sqlite3
```

这里的 SQLite 是 Agent 实际使用的检索后端；评测集仍负责比较“期望来源”和“实际来源”，并检查工具调用、停止原因、引用和回答关键词。SQLite 负责提供检索结果，Evaluation 负责判断这次 Agent 执行是否符合预期。

命令会：

1. 加载知识库和评测集。
2. 每个用例使用空历史独立运行一次 Agent。
3. 检查 Agent 是否完成、停止原因、工具调用和工具执行状态。
4. 检查检索来源、回答引用、必需关键词和拒答状态。
5. 计算每道题的检索、引用、拒答和延迟指标。
6. 将每道题的结果和汇总统计写入 JSON 报告。

全部用例通过返回退出码 `0`，否则返回 `1`，方便后续接入 CI。

## 2.1 检索后端对比

Agent Evaluation 用于判断完整 Agent 行为是否符合预期；如果只想观察不同检索算法的排名，可以运行：

```powershell
py -m studymate compare-search `
  --knowledge .\knowledge `
  --query "agent loop 和 agent runtime 有什么区别？" `
  --query "What is MCP?" `
  --output .\logs\search-comparison.jsonl
```

该命令会比较：

- `memory`：临时构建的内存 BM25 风格检索，主要用于学习和小样本对比；
- `sqlite`：打开已经由 `build-index` 生成的 SQLite FTS5/BM25 索引。

分数只在同一后端内部比较。最终应结合目标来源是否进入 Top-K、排名、Hit@K、Recall@K、Precision@K、MRR 和人工相关性判断。Embedding 和 Reranker 暂不参与主流程，相关源码仅作为后续学习材料保留。

## 3. 评测集格式

评测集使用 JSONL，每行一个 JSON 对象：

```json
{
  "id": "mcp-001",
  "input": "MCP 是什么？",
  "intent": "question",
  "expected_sources": [],
  "acceptable_sources": [
    "claude-code/99-other/glossary.md",
    "ai-agent/tool-calling-vs-mcp.md"
  ],
  "required_terms": ["agent"],
  "expected_tools": ["search_knowledge"],
  "expected_stop_reason": "final_answer",
  "should_abstain": false
}
```

字段说明：

| 字段 | 作用 |
| --- | --- |
| `id` | 用例的稳定标识 |
| `input` | 发送给 Agent 的用户问题 |
| `intent` | 可选意图，会作为输入前缀 |
| `expected_sources` | 严格期望出现的检索和引用来源；多个来源必须全部命中。与 `acceptable_sources` 都为空时，表示不应有来源 |
| `acceptable_sources` | 可选的等价来源集合；多个候选中至少命中一个即可。适合概念定义等有多个正确资料来源的题目 |
| `required_terms` | 最终回答必须包含的词 |
| `expected_tools` | 期望按顺序出现的工具调用 |
| `expected_stop_reason` | 期望停止原因，如 `final_answer` 或 `empty_search` |
| `should_abstain` | 是否应该声明证据不足 |

来源匹配支持完整路径和文件名后缀。例如期望 `mcp.md` 可以匹配 `claude-code/07-agent-sdk/mcp.md`。

## 4. 第一版检查项

每个用例在报告中都会得到以下布尔检查：

- `answer_present`：是否返回非空回答。
- `loop_completed`：是否以 `final_answer` 或 `empty_search` 正常结束，而不是 `max_steps`。
- `stop_reason_matches`：停止原因是否符合用例预期。
- `tool_success`：所有实际执行的工具是否成功。
- `retrieval_matches`：检索结果是否包含期望来源。
- `citations_match`：最终回答的引用是否包含期望来源。
- `required_terms`：回答是否包含所有必需关键词。
- `abstention_matches`：是否按预期拒答或回答。

单个用例只有所有检查都通过才算通过。报告同时保留回答、引用、工具调用、完整 Trace、步骤数、停止原因和耗时，评测失败后可以直接从同一个 JSON 报告定位执行过程。

## 5. 检索质量指标

每个成功执行的用例会在 `result.metrics` 中保存以下字段：

| 指标 | 含义 |
| --- | --- |
| `hit_at_k` | 前 K 个来源中是否至少命中一个期望来源 |
| `recall_at_k` | 前 K 个结果召回的期望来源数 / 期望来源总数 |
| `precision_at_k` | 前 K 个结果中匹配期望来源的结果数 / 前 K 个结果数 |
| `mrr` | 第一个期望来源排名的倒数，未命中为 0 |
| `citation_accuracy` | 最终引用中匹配期望来源的引用比例 |
| `citation_coverage` | 被最终回答引用的期望来源数 / 期望来源总数 |
| `abstained` | Agent 是否声明证据不足 |
| `abstention_correct` | 存在 `should_abstain` 时，实际拒答是否符合预期 |

`expected_sources` 和 `acceptable_sources` 可以并存：前者仍必须全部命中，后者额外要求至少命中一个。对指标而言，一个候选来源集合视为一个预期槽位：Hit@K 命中任一严格或候选来源即成功；Recall@K 和 Citation Coverage 按严格来源数量加一个候选槽位计算；Precision@K 与 Citation Accuracy 则将所有候选路径都作为相关来源判断。

`summary.metrics` 会按以下口径汇总：

- `hit_at_k` 和 `precision_at_k` 包含全部用例；无来源题在没有召回时算正确。
- `recall_at_k`、`mrr` 和 `citation.coverage` 只统计 `expected_sources` 或 `acceptable_sources` 非空的正向用例。
- `citation.accuracy`、`abstention.rate` 和延迟统计包含所有成功执行的用例。
- 模型或工具异常的用例不会伪造检索指标，但仍会计入失败数量。

报告结构示例：

```json
{
  "schema_version": 2,
  "summary": {
    "total": 15,
    "passed": 15,
    "failed": 0,
    "pass_rate": 1.0,
    "metrics": {
      "retrieval": {
        "k": 5,
        "hit_at_k": 1.0,
        "recall_at_k": 1.0,
        "precision_at_k": 0.8,
        "mrr": 1.0
      }
    }
  }
}
```

## 6. 当前实现边界

第一版是可重复的规则评测，不会使用另一个模型来评价答案语义。它适合先验证 Agent Runtime 的行为契约：是否调用工具、是否安全结束、是否引用正确来源、是否在无证据时拒答。

后续可以增加：

- 人工标注的参考答案和答案正确性评分。
- LLM-as-a-Judge，但需要固定 Prompt、模型和评分标准。
- Token、费用和多轮延迟统计。
- 将评测报告和版本号绑定，比较不同 Prompt 或检索策略的回归。

## 7. 开发原则

- 成功和失败样本都要保留。
- 每次修改 Prompt、工具契约或检索策略后重新运行评测。
- 真实模型评测和单元测试分开。
- 评测失败时先查看 `stop_reason` 和失败检查项，再结合该用例的 Agent Trace 排查。
