# 第一阶段 Agent 范围

## 目标

StudyMate 第一阶段从固定 RAG Workflow 升级为一个最小、可验证的学习 Agent：

- 接收用户问题或学习目标。
- 自主决定是否检索知识库。
- 必要时打开知识库文档获取更完整上下文。
- 基于工具结果生成带引用的最终回答。
- 在工具错误、参数错误或超过步数时安全停止。

## 不在本阶段实现

- 多智能体协作。
- 浏览器、Shell 或任意代码执行。
- 长期记忆和学习进度持久化。
- MCP Server 接入。
- 向量数据库和 Embedding 检索升级。
- 自动修改知识库文件。

## 运行时边界

```text
ChatService
  -> AgentRunner
      -> OpenAI-compatible LLM
      -> ToolRegistry
          -> search_knowledge
          -> open_document
      -> Citation Validator
```

Agent 负责决策和循环；工具负责一个有限、可测试的动作；知识库和检索索引仍由现有模块负责。

## 验收标准

- 模型可以选择 `search_knowledge`。
- 工具结果可以回传给模型。
- 模型可以在搜索后选择 `open_document`。
- Agent 最多执行 5 步并且能够停止。
- 空检索和重复工具调用会在运行时安全结束，不会无限循环。
- 未知工具和非法参数不会执行危险操作。
- 最终引用必须来自实际检索结果。
