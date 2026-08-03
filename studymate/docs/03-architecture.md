# StudyMate 架构设计

## 1. 设计目标

- 先实现简单、可验证的固定 Workflow。
- 保留后续接入 Tool Calling、Memory 和 Agent Loop 的扩展点。
- 将模型、检索、存储和 CLI 隔离，方便测试和替换。

## 2. 分层结构

~~~text
Interface
  cli.py
    |
Application
  ingest_service.py
  chat_service.py
  evaluation_service.py
    |
Domain
  models.py
  ports.py
  policies.py
    |
Adapters
  filesystem_loader.py
  sqlite_index.py
  llm_client.py
  session_store.py
~~~

## 3. 运行时流程

~~~text
用户输入
  -> Command Parser
  -> Intent Router
  -> Session Store
  -> Search Index
  -> Context Builder
  -> LLM Client
  -> Answer Validator
  -> Citation Validator
  -> CLI Renderer
~~~

## 4. 第一版固定 Workflow

~~~text
handle_input
  -> parse command
  -> classify intent
  -> retrieve top-k chunks
  -> build prompt
  -> call LLM
  -> validate answer
  -> save session message
  -> render result
~~~

## 5. 后续 Agent 扩展

第一版不实现自主循环。后续可以在 Application 层增加：

~~~text
Agent Loop
  -> decide next action
  -> call search_notes / get_source / make_plan
  -> observe tool result
  -> decide whether to continue
  -> answer
~~~

Domain 层不应直接依赖具体模型 SDK、CLI 框架或向量数据库。

## 6. 边界

- Knowledge Loader 只负责读取和切分。
- Search Index 只负责检索。
- LLM Client 只负责模型请求和响应解析。
- Chat Service 负责业务流程。
- CLI 只负责输入和展示。

