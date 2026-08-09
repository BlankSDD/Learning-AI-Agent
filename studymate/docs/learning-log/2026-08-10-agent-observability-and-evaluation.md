# 2026-08-10 Agent 可观测性与评估

## 今日目标

今天先不增加新工具，也不接向量数据库。目标是理解如何观察和验证一个 Agent：它做了什么、为什么停止、改动后是否仍然正确。

## 一、Agent Trace 问答

### 问题：`/trace` 相当于普通日志吗？

回答结论：有相似之处，但 Trace 比普通 Debug 日志更接近一次 Agent Run 的结构化执行记录。

- HTTP Debug 日志关注请求地址、流式响应、HTTP 状态码和网关错误。
- Agent Trace 关注第几步、当时可用什么工具、模型请求什么工具、工具是否执行成功、找到多少证据、为何停止。
- Trace 用于开发者排查、复盘、评估和面试展示，不参与模型推理。

### 问题：Trace 是不是对话历史或 Memory？

回答结论：不是。

| 数据 | 作用 | 是否发给模型 |
| --- | --- | --- |
| 对话历史 | 帮助模型理解“上一个问题”等上下文 | 是，当前只保留最近消息 |
| Agent Trace | 说明本次 Agent 如何执行 | 否 |
| 长期记忆 | 跨会话保存用户偏好或学习进度 | 当前未实现 |

### 问题：Trace 落盘是否等同于持久化会话？

回答结论：不等同。StudyMate 现在会将问题、最终回答和 Trace 追加到 `traces/session-*.jsonl`，但程序重启后不会读取这些文件恢复对话，也不会把它们送回模型。

这是“可审计的运行记录”，不是“可恢复的模型记忆”。这样能先避免旧问题、敏感对话或错误结论在不受控情况下进入后续 Prompt。

### 当前代码映射

```text
AgentRunner
  -> 为每个模型步骤创建 AgentTraceStep
  -> 记录可用工具、模型请求和工具执行摘要
  -> 写入 final_answer / empty_search / max_steps 等停止原因

ChatService
  -> 保存当前会话中的 last_trace
  -> 追加 问题 + Answer + Trace 到 JSONL
  -> /trace 输出最近一轮摘要

TraceStore
  -> 管理 traces/session-<id>.jsonl
```

阅读顺序：`src/studymate/trace.py` -> `src/studymate/agent.py` -> `src/studymate/chat.py` -> `src/studymate/cli.py`。

## 二、今日动手任务

1. 在项目根目录运行：

```powershell
.venv\Scripts\python.exe -m studymate chat --knowledge .\knowledge
```

2. 输入一个知识库中有资料的问题，例如：`agent loop 和 agent runtime 有什么区别？`。
3. 查看回答后输入 `/trace`。
4. 打开启动时打印的 `traces/session-*.jsonl` 文件，确认其只记录问题、回答、来源和执行摘要。
5. 对照本文件，解释 Trace 中每一个步骤为何进入 `tool_decision` 或 `finalization`。

完成标准：你能指出一次问答中模型调用了哪些工具、哪些步骤没有再提供工具、最后为什么停止。

## 三、Agent Eval 预习

### 问题：Agent Eval 和 pytest 单元测试有什么区别？

回答结论：单元测试验证一个函数或一个确定分支是否正确；Agent Eval 验证一条完整任务在工具、检索、停止条件和最终回答层面是否符合预期。

例如：

- 单元测试：`search_knowledge` 的参数校验是否拒绝空查询。
- Agent Eval：用户问一个不存在的概念时，Agent 是否只检索一次、停止为 `empty_search`、并明确说明资料不足。

下一次实现 Eval 时，先从确定性 Fake Model 开始，不直接依赖真实模型 API。真实模型可作为单独的手工回归，不作为每次 CI 的硬性测试。

## 四、下一步问题

完成 Trace 与 Eval 后，优先学习查询规范化。原因是当前本地关键词检索对 `agentloop` 和 `agent loop` 这类写法敏感；这是可观察、可测试的 RAG 质量问题，适合在已有 Trace/Eval 基础上改进。
