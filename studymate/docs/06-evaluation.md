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

命令会：

1. 加载知识库和评测集。
2. 每个用例使用空历史独立运行一次 Agent。
3. 检查 Agent 是否完成、停止原因、工具调用和工具执行状态。
4. 检查检索来源、回答引用、必需关键词和拒答状态。
5. 将每道题的结果和汇总统计写入 JSON 报告。

全部用例通过返回退出码 `0`，否则返回 `1`，方便后续接入 CI。

## 3. 评测集格式

评测集使用 JSONL，每行一个 JSON 对象：

```json
{
  "id": "mcp-001",
  "input": "MCP 是什么？",
  "intent": "question",
  "expected_sources": ["claude-code/07-agent-sdk/mcp.md"],
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
| `expected_sources` | 期望出现的检索和引用来源；空列表表示不应有来源 |
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

## 5. 当前实现边界

第一版是可重复的规则评测，不会使用另一个模型来评价答案语义。它适合先验证 Agent Runtime 的行为契约：是否调用工具、是否安全结束、是否引用正确来源、是否在无证据时拒答。

后续可以增加：

- 人工标注的参考答案和答案正确性评分。
- LLM-as-a-Judge，但需要固定 Prompt、模型和评分标准。
- 检索 Recall、MRR、引用覆盖率等更细的 RAG 指标。
- Token、费用和多轮延迟统计。
- 将评测报告和版本号绑定，比较不同 Prompt 或检索策略的回归。

## 6. 开发原则

- 成功和失败样本都要保留。
- 每次修改 Prompt、工具契约或检索策略后重新运行评测。
- 真实模型评测和单元测试分开。
- 评测失败时先查看 `stop_reason` 和失败检查项，再结合该用例的 Agent Trace 排查。
