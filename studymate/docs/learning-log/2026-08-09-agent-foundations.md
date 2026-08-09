# 2026-08-09 Agent 基础与 StudyMate 第一阶段

## 记录范围

本记录整理 StudyMate 开发过程中关于 Workflow、RAG、Tool Calling、MCP、Agent Runtime、项目结构和 ChatService 的知识问答。记录的是学习结论和工程决策，不包含 API Key、`.env` 内容或个人隐私。

## 一、基础概念问答

### 问题：Workflow 和 Agent 的区别是什么？

回答结论：

- Workflow 的执行步骤由程序预先定义，模型通常只负责某一步的生成或分类。
- Agent 接收目标后，由模型决定下一步动作，可能调用工具、观察结果、继续决策，直到完成任务或触发停止条件。
- Workflow 更容易预测、测试和控制；Agent 更灵活，但需要处理循环、错误、权限、成本和评估问题。

对项目的影响：StudyMate 先实现可验证的固定 RAG Workflow，再把固定检索步骤升级为 Agent 可自主选择的工具。

### 问题：什么是 RAG 应用？

回答结论：RAG 是 Retrieval-Augmented Generation，即检索增强生成。系统先从外部知识库检索相关资料，再把资料作为上下文交给模型生成回答。

典型流程：

```text
加载资料 -> 文档切分 -> 检索 Top-K -> 拼接上下文 -> 调用模型 -> 返回引用
```

RAG 不是 Agent。RAG 解决的是“模型如何使用外部知识”，Agent 解决的是“模型如何决定下一步动作”。StudyMate 当前的本地关键词检索 + 模型回答就是 RAG 应用。

### 问题：Tool Calling 和 MCP 的区别是什么？

回答结论：

- Tool Calling 是模型与应用之间的一次工具调用机制。应用把工具 Schema 发送给模型，模型返回工具名称和参数，应用执行后再把结果传回模型。
- MCP 是标准化的工具、资源和提示词接入协议，解决不同 Agent 客户端如何发现和使用外部能力的问题。
- Tool Calling 关注一次模型请求如何调用工具；MCP 关注工具能力如何以统一协议被多个客户端接入。
- StudyMate 第一阶段使用本地 Python 工具注册，不接入 MCP；后续可以把知识库能力封装为 MCP Server。

## 二、StudyMate 产品定位问答

### 问题：StudyMate 应该实现什么功能？

回答结论：StudyMate 定位为一个基于本地知识库的学习辅导 Agent。用户可以在 CMD 中输入问题、学习目标或主题关键词，系统检索本地资料并返回带来源的解释、学习建议和后续问题。

第一阶段目标不是做通用聊天机器人，而是验证：

```text
用户目标 -> Agent 决策 -> 工具调用 -> 观察结果 -> 带引用的学习回答
```

### 问题：第一阶段应该选择哪些工具？

回答结论：第一阶段只实现两个只读工具：

| 工具 | 功能 |
| --- | --- |
| `search_knowledge` | 在本地知识库中检索相关片段，返回路径、行号、分数和 `chunk_id` |
| `open_document` | 打开知识库内的指定文档或行范围，获取更完整上下文 |

暂不加入 Shell、浏览器、任意代码执行和会修改数据的工具。这样可以先验证 Agent Loop，同时控制安全风险。

### 问题：工具是不是脚本？

回答结论：工具通常由代码实现，但工具不等于脚本。

- 脚本是可以独立运行的程序。
- 工具是暴露给 Agent 的受约束能力，包含名称、描述、参数 Schema、执行函数、错误处理和权限规则。
- 一个工具可以由 Python 函数、类方法、HTTP API、Shell 命令或 MCP Server 实现。

StudyMate 中的两个工具由 Python 方法实现，并通过 `ToolRegistry` 注册给 Agent。模型只看到工具 Schema，不能直接执行 Python 或文件系统操作。

## 三、Agent 实现问答

### 问题：StudyMate 是否要从零手搓一个 Agent 框架？

回答结论：StudyMate 需要手写一个最小 Agent Runtime，但不是从零实现 LangChain 或 OpenCode 的完整功能。

需要自己理解和实现的部分：

- `AgentRunner`。
- 工具注册和分发。
- 工具参数校验。
- Agent 状态和执行步数。
- 工具结果回传。
- 最大步数和错误处理。
- 最终回答和引用校验。

可以直接使用的基础能力：

- `openai` Python SDK：负责调用 OpenAI-compatible 接口。
- Pydantic：负责工具参数 Schema 和校验。
- pytest：负责 TDD 测试。

### 问题：是否直接使用 OpenCode SDK？

回答结论：第一阶段不使用 OpenCode SDK。StudyMate 先使用已有的 `openai` 客户端实现原生 Tool Calling，并手写 Agent Loop。

原因：

- OpenCode 更偏向完整的 AI Coding 应用运行时。
- 直接使用 SDK 会隐藏工具调度、状态管理和循环控制的核心细节。
- 当前学习目标是理解 Agent 的底层运行机制，而不是快速拼装一个黑盒框架。

后续开发 AI Coding Agent 时，再研究 OpenCode、LangGraph 等框架的实现方式并进行对比。

### 问题：AgentRunner 是基于 AI 模型对话实现的吗？

回答结论：是。AgentRunner 本身不是模型，而是模型调用和工具执行之间的控制器。

一次 Agent 运行的流程是：

```text
第 1 次模型请求：发送用户问题和工具 Schema
  -> 模型返回 tool_calls
StudyMate：校验参数并执行本地工具
  -> 把工具结果作为 tool message 追加到消息列表
第 2 次模型请求：模型继续判断
  -> 返回另一个工具调用或最终 Answer
```

模型负责“决定调用什么”；StudyMate 负责“真正执行什么”。

### 问题：Agent 一定要使用非流式请求吗？

回答结论：不一定。最初选择非流式，是为了先理解完整工具名称和参数的解析；当前 StudyMate 已经支持流式 Tool Calling。

流式模式会把工具名称和参数拆成多个增量，需要在 `llm.py` 中聚合后才能交给 `ToolRegistry` 校验和执行。当前 Huazi/NewAPI + Claude 网关使用流式兼容性更好，但 CLI 仍会在收到完整最终答案后一次性打印。

### 问题：为什么模型网关要支持 `tools` 和 `tool_calls`？

回答结论：

- `tools` 是应用发送给模型的工具定义。
- `tool_calls` 是模型返回的工具选择和参数。

如果网关只返回普通文本，程序无法可靠识别模型想调用哪个工具，也不能保证参数安全。因此当前 Agent 需要 OpenAI-compatible 的原生工具调用能力。

普通模型对话可以正常工作，并不代表该网关已经支持 Tool Calling；两者是不同的接口能力。

### 问题：Agent Loop 和 Agent Runtime 有什么区别？

回答结论：Agent Loop 是一次任务中的循环逻辑；Agent Runtime 是承载并约束这个循环的整个运行系统。

```text
Agent Runtime
  -> 模型适配、消息状态、工具注册、权限、预算、Trace、错误处理
  -> Agent Loop
       -> 决定下一步
       -> 调用工具
       -> 观察结果
       -> 继续或停止
```

在 StudyMate 中，`AgentRunner.run()` 的多轮“模型 -> 工具 -> 观察 -> 模型”过程是 Agent Loop；`AgentRunner`、`ToolRegistry`、`OpenAIAnswerer`、引用校验、工具预算和 Trace 共同构成最小 Agent Runtime。

## 四、项目结构问答

### 问题：为什么主要代码放在 `src/`，而不是直接在 `studymate/` 下建立 `main.py`？

回答结论：这是 Python 项目的 `src layout`。`studymate/` 是项目根目录，`src/studymate/` 是实际 Python 包；测试、知识库、文档和配置放在包外。

```text
studymate/
  pyproject.toml       # 项目和依赖配置
  src/studymate/       # 生产代码
  tests/               # 测试代码
  knowledge/           # 学习资料
  docs/                # 需求、架构和学习记录
```

这种结构可以：

- 防止测试时意外导入项目根目录的源码。
- 让包安装、命令行入口和部署行为更接近真实项目。
- 明确区分生产代码、测试、知识库和设计文档。

`src/studymate/__main__.py` 就是模块入口，执行 `python -m studymate` 时会调用 `cli.py` 中的 `main()`。简单 Demo 可以使用 `main.py`，但当前项目已经包含多个模块、测试和可安装配置，使用 `src` 结构更适合继续演进。

## 五、ChatService 与 AgentRunner 的职责

### 初始版本

最开始的 ChatService 是固定的一次性 RAG 流程：

```text
用户输入
  -> 意图分类
  -> 固定检索知识库
  -> 调用一次 AI 模型
  -> 校验引用
  -> 保存历史
```

### 当前第一阶段版本

CLI 会把 AgentRunner 注入 ChatService，普通问题走新的 Agent 流程：

```text
cli.py
  -> ChatService.handle()
  -> AgentRunner.run()
  -> OpenAIAnswerer.chat_with_tools()
  -> ToolRegistry.execute()
  -> AgentRunner 继续循环或生成最终答案
```

ChatService 仍然负责命令、会话历史和最终展示；AgentRunner 负责一次问题内部的工具决策和循环；OpenAIAnswerer 负责模型请求；工具负责实际读取和检索。

旧的一次性 RAG 路径暂时保留，用于兼容现有测试和旧接口。等 Agent 版本稳定后，可以删除这条兼容路径，统一使用 AgentRunner。

## 六、运行时保护补充

### 问题：为什么 Agent 会反复调用工具，不能只让模型自己停止吗？

回答结论：不能只依赖模型提示词。模型可能检索到泛化但无关的片段，或者忽略“不要重复调用”的规则，持续请求同一个工具。运行时必须负责步数、工具预算和停止条件。

StudyMate 当前采用以下保护：

- `max_steps=5` 是总步骤上限。
- 每个只读工具在一次任务中默认最多执行一次。
- 空的 `search_knowledge` 结果直接返回“知识库证据不足”。
- 模型再次请求已用尽预算的工具时，AgentRunner 不再继续工具循环，而是进入最终化。

### 问题：为什么最终化时需要清理 Tool Calling 消息？

回答结论：Huazi 的 NewAPI 后端会将 Claude 工具调用转为 Bedrock 的 `toolUse/toolResult` 块。若历史中仍有这些块，但下一次请求不含工具配置，Bedrock 会返回 `TOOL_CONFIG_MISSING`。

因此最终化时，StudyMate 会保留原始用户问题，把工具观察结果转为普通文本上下文，再发起一个不带工具的最终回答请求。这是 Provider 兼容层的约束，不改变 AgentRunner、ToolRegistry 与工具的职责边界。

## 七、Agent Trace 与问答记录

### 问题：`/trace` 是不是历史记录？

回答结论：不是。对话历史用于让模型理解当前会话上下文，会发送给模型；Agent Trace 是开发者观察一次运行的执行记录，不会发送给模型。

Trace 会记录每一步的可用工具、模型请求的工具和参数、执行结果摘要、停止原因与耗时。当前实现会把原始问题、最终回答和 Trace 追加到 `traces/session-<id>.jsonl`，便于复盘；不会保存 API Key、HTTP 请求头或完整知识库原文。

`/reset` 只清空内存对话历史，已经落盘的 Trace 不会被删除。程序也不会在下次启动时自动将 Trace 恢复为模型记忆。

## 八、阶段结论

StudyMate 第一阶段已经完成从固定 RAG Workflow 到最小 Agent Runtime 的迁移：

```text
固定检索流程
  -> 模型一次性回答

升级为

模型自主选择工具
  -> 本地工具执行
  -> 工具结果观察
  -> 模型继续决策
  -> 最终带引用回答
```
