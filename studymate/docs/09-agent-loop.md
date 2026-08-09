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
- 每个已注册工具默认在一次 Agent Run 中最多调用一次。模型重复请求已用尽预算的工具时，运行时强制进入最终化，防止循环消耗 Token。
- `search_knowledge` 没有任何结果时直接返回“知识库证据不足”，不再要求模型继续猜测或重复检索。
- 最终化阶段不发送 Tool Calling。对于 Bedrock 兼容网关，历史工具消息会转为普通上下文，以避免缺少 `toolConfig` 的 400 错误。
- 最终回答必须能解析为 StudyMate 的 `Answer` 结构。
- 引用只允许来自 `search_knowledge` 实际返回的片段。
- 工具错误不会直接导致进程退出，而是作为观察结果交给模型。
- 每轮会生成 Agent Trace，记录工具选择、参数、执行摘要、停止原因和耗时；Trace 只用于开发排查，不作为模型上下文。
