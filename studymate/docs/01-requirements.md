# StudyMate 需求规格

## 1. 术语

| 术语 | 定义 |
|---|---|
| Knowledge Base | 本地学习资料经过导入和切分后形成的可检索数据 |
| Document | 一个源文件，如 Markdown 或 TXT |
| Chunk | 从 Document 中切分出的知识片段 |
| Citation | 回答引用的文件、标题和行号信息 |
| Session | 一次命令行对话及其短期历史 |
| Intent | 用户输入类型：question、goal、keyword 或 command |

## 2. 功能需求

### FR-001 文档导入

系统应扫描指定目录中的 Markdown 和 TXT 文件，创建 Document 记录。

验收标准：

- 忽略不支持的文件类型。
- 保存相对路径、标题、文本和内容哈希。
- 同一个文件重复导入不会产生重复记录。
- 文件读取失败时返回可识别错误。

### FR-002 文档切分

系统应按照标题和段落切分 Document，生成 Chunk。

验收标准：

- 每个 Chunk 关联一个 Document。
- 每个 Chunk 有稳定 ID。
- 每个 Chunk 保存来源路径和行号。
- 空内容不生成 Chunk。

### FR-003 知识检索

系统应根据用户输入返回排序后的 Top-K Chunk。

验收标准：

- 相关资料优先于无关资料。
- 结果包含 score 和来源。
- 没有结果时返回空集合，不抛出未处理异常。
- Top-K 参数可以配置。

### FR-004 输入类型识别

系统应识别以下输入：

- question：具体知识问题。
- goal：学习目标或学习方向。
- keyword：概念或关键词。
- command：以斜杠开头的命令。

### FR-005 回答生成

系统应根据用户输入、检索结果和会话上下文生成结构化回答。

回答至少包含：

- answer。
- citations。
- confidence。
- need_more_context。
- next_steps。

### FR-006 引用约束

- 每个重要结论尽量关联 Citation。
- 检索不到足够证据时，need_more_context 必须为 true。
- 系统不得把不存在的文件作为来源。

### FR-007 命令行对话

系统应支持：

~~~text
studymate ingest <knowledge-dir>
studymate chat
studymate eval
~~~

交互过程中支持：

~~~text
/help
/sources
/reset
/quit
~~~

### FR-008 会话记忆

第一版只保存当前 Session 的最近若干轮消息。

系统不应默认把全部历史对话永久写入知识库。

### FR-009 错误处理

系统应对以下情况给出可读错误：

- 知识库目录不存在。
- 没有可导入文件。
- 模型 API 配置缺失。
- 模型返回格式错误。
- 检索没有结果。
- 会话状态损坏。

## 3. 非功能需求

### NFR-001 可测试

核心领域逻辑不能依赖真实模型 API，必须支持 Fake LLM 和 Fake Search Index。

### NFR-002 可追溯

每次回答应能追踪到检索结果、模型请求和最终引用。

### NFR-003 可恢复

单次模型调用失败不能导致整个 CLI 进程崩溃。

### NFR-004 安全

- API Key 只能从环境变量读取。
- 日志不得打印完整 API Key。
- 第一版只能读取明确配置的知识库目录。

