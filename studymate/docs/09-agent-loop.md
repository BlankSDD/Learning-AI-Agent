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
  step < max_steps? -- no --> STOP_WITH_LIMIT
       |
       yes
       v
  CALL_MODEL
```

## 关键策略

- 第一阶段最多执行 5 步。
- Agent 使用原生 OpenAI-compatible Tool Calling。
- Agent 请求暂时使用非流式模式，先保证工具调用消息完整。
- 最终回答必须能解析为 StudyMate 的 `Answer` 结构。
- 引用只允许来自 `search_knowledge` 实际返回的片段。
- 工具错误不会直接导致进程退出，而是作为观察结果交给模型。
