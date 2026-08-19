# 第一阶段 Agent Loop

## 状态

一次 Agent 运行包含：

- 初始用户消息。
- 当前对话历史。
- 模型可用工具 Schema。
- Assistant 的工具调用消息。
- Tool 的执行结果。
- 本次检索到的证据。
- 已执行步数和工具名称列表。

## 状态转换

```text
START
  -> CALL_MODEL
  -> TOOL_CALL? -- no --> PARSE_FINAL_ANSWER
       |
       yes
       v
  VALIDATE_TOOL
       |
  EXECUTE_TOOL
       |
  APPEND_OBSERVATION
       |
  EMPTY_SEARCH? -- yes --> STOP_WITH_NO_EVIDENCE
       |
       no
       v
  TOOL_BUDGET_EXHAUSTED? -- yes --> FINALIZE_WITHOUT_TOOLS
       |
       no
       v
  step < max_steps? -- no --> STOP_WITH_LIMIT
       |
       yes
       v
  CALL_MODEL
```

## 关键策略

- 第一阶段最多执行 5 步。
- Agent 使用原生 OpenAI-compatible Tool Calling。
- Agent 可使用流式或非流式模式；流式 `tool_calls` 会先在本地聚合，再校验和执行。
- 每个已注册工具默认在一次 Agent Run 中最多调用一次。模型重复请求已用尽预算的工具时，该调用会被拒绝并作为错误观察返回；其他尚未用尽预算的工具仍然可用。只有所有工具预算耗尽后才进入最终化，避免一次规划错误阻断后续的 `open_document`。
- 对明显的定义型问题，`search_knowledge` 成功后会关闭 `open_document` 并进入最终化；详细解释、流程和区别类问题仍保留文档读取能力。这是一个可测试的最小工具路径策略，用于降低不必要的调用和引用噪声。
- `search_knowledge` 没有任何结果时直接返回“知识库证据不足”，不再要求模型继续猜测或重复检索。
- `search_knowledge` 执行前会调用本地 `rewrite_query()`：移除模型规划中的搜索动作词、疑问词和停用词，同时保留 `Agent Loop`、`MCP` 等主题词。它只改写检索 query，不改写最终答案，也不会产生模型 API 请求。
- 最终化阶段不发送 Tool Calling。对于 Bedrock 兼容网关，历史工具消息会转为普通上下文，以避免缺少 `toolConfig` 的 400 错误。
- 最终回答必须能解析为 StudyMate 的 `Answer` 结构。
- 引用只允许来自 `search_knowledge` 实际返回的片段。
- 工具错误不会直接导致进程退出，而是作为观察结果交给模型。
- 每轮会生成 Agent Trace，记录工具选择、参数、执行摘要、停止原因和耗时；Trace 只用于开发排查，不作为模型上下文。
- 对 `search_knowledge`，Trace 还记录改写前后的 query 和 Top-K 排名，用于区分“改写错误”和“索引排序错误”。
- Agent Evaluation 对 Rivo `get_channel_failed` 等临时通道错误支持有限重试；鉴权、余额和参数错误仍快速失败。
