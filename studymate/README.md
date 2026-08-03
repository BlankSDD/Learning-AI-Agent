# StudyMate

StudyMate 是一个运行在命令行中的个人学习资料对话助手。

它读取本地 Markdown / TXT 学习资料，根据用户的问题、学习目标或关键词检索相关知识，调用大模型生成带来源的回答、学习建议或下一步问题。

## 1. 知识库放在哪里

默认知识库路径是：

~~~text
D:\develop_projects\Learning-AI-Agent\studymate\knowledge\
~~~

你可以直接把 Markdown 文件放在这里，也可以继续创建子文件夹。

StudyMate 会递归扫描所有子文件夹，所以以下结构都可以：

~~~text
studymate/
  knowledge/
    claude-code/
      overview.md
      commands.md
      workflows.md
    opencode/
      overview.md
      configuration.md
    codex/
      overview.md
      prompts.md
    ai-agent/
      rag.md
      tool-calling.md
      evaluation.md
~~~

支持的文件扩展名：

- .md
- .markdown
- .txt

推荐按主题建立文件夹，例如：

- knowledge/claude-code/
- knowledge/opencode/
- knowledge/codex/
- knowledge/ai-agent/
- knowledge/python/
- knowledge/backend/

文件夹不会影响检索。目录和文件名会作为来源路径显示在回答中，例如：

~~~text
Sources:
- claude-code/commands.md:12-28
~~~

## 2. 文档建议

每个 Markdown 文件建议：

- 只讲一个主题。
- 使用清晰的一级和二级标题。
- 每个知识点尽量配一个例子。
- 不要把几十个完全无关的主题合并到一个文件。
- 保留官方文档的版本、更新时间和来源说明。

例如：

~~~markdown
# Claude Code Commands

来源版本：2026-08

## /init

功能说明……

## /plan

功能说明……
~~~

## 3. 安装和运行

在 studymate 目录执行：

~~~powershell
cd D:\develop_projects\Learning-AI-Agent\studymate
py -m pip install -e ".[dev]"
~~~

扫描知识库：

~~~powershell
py -m studymate ingest .\knowledge
~~~

启动对话：

~~~powershell
py -m studymate chat --knowledge .\knowledge
~~~

## 4. 自动更新在线开发文档

文档源配置位于：

~~~text
config/docs_sources.json
~~~

当前默认启用三个官方文档源：

- `claude-code`：Anthropic Claude Code 官方文档。
- `opencode`：OpenCode 官方文档。
- `codex`：OpenAI Codex 官方仓库中的 README 和开发文档。

更新所有已启用的文档：

~~~powershell
py -m studymate update-docs --proxy 127.0.0.1:7897 --workers 8
~~~

也可以直接运行独立脚本：

~~~powershell
py .\scripts\update_docs.py --proxy 127.0.0.1:7897
~~~

如果已经配置 `STUDYMATE_DOCS_PROXY`，可以省略 `--proxy`。`--workers` 控制并发下载数，默认是 8。只更新指定项目：

~~~powershell
py -m studymate update-docs --only claude-code opencode
~~~

在对话中输入 `/update` 会更新配置中启用的项目，并自动重载检索索引；输入 `/update codex` 只更新 Codex。配置中的 `enabled` 可以控制默认更新哪些项目。

下载文件会写入 `knowledge/<source-id>/`，并按配置中的分类规则保存为 Markdown。文档更新器只覆盖它生成的同名文件，不会删除目录中的其他学习资料。

如果当前目录已经是 studymate，也可以直接使用默认路径：

~~~powershell
py -m studymate chat
~~~

## 5. 环境变量

设置模型服务。推荐使用通用 Provider 配置：

~~~text
STUDYMATE_TYPE=openai_compatible
STUDYMATE_PROVIDER=newapi
STUDYMATE_ENDPOINT_TYPE=openai
STUDYMATE_API_KEY=
STUDYMATE_BASE_URL=https://huazi.de5.net/v1
STUDYMATE_MODEL=claude-sonnet-4-5-20250929
~~~

其中：

- `STUDYMATE_TYPE` 当前必须是 `openai_compatible`。
- `STUDYMATE_PROVIDER` 用于标识供应商，例如 `newapi`、`deepseek`。
- `STUDYMATE_ENDPOINT_TYPE` 当前必须是 `openai`。
- `STUDYMATE_API_KEY` 是模型服务密钥。
- `STUDYMATE_BASE_URL` 是 OpenAI 兼容接口根地址。
- `STUDYMATE_MODEL` 是供应商支持的模型名称。
- 对 `provider=newapi`，如果 Base URL 没有路径，程序会自动补充 `/v1`。
- `STUDYMATE_DEBUG=true` 会输出脱敏的请求诊断信息，排查完成后建议改为 `false`。
- `STUDYMATE_RESPONSE_FORMAT` 可设为 `json_object` 或 `none`。NewAPI/Claude 兼容接口默认建议使用 `none`，避免上游拦截该参数；程序仍会通过 Prompt 要求模型返回 JSON。
- `STUDYMATE_STREAM=true` 使用流式请求并在本地聚合完整回答，适合 NewAPI/Claude 兼容接口。
- `STUDYMATE_USER_AGENT` 用于覆盖 HTTP 客户端 User-Agent。默认是 `ai-sdk/openai-compatible/2.0.37`，用于兼容会拦截 `OpenAI/Python` 的网关（例如当前 Huazi Cloudflare 配置）。
- `STUDYMATE_HTTP_REFERER`、`STUDYMATE_X_TITLE` 和 `STUDYMATE_EXTRA_HEADERS_JSON` 用于传递供应商要求的额外请求头。
- STUDYMATE_DOCS_PROXY 是在线文档更新使用的 HTTP 代理，例如 `http://127.0.0.1:7897`。

原有 `OPENAI_*` 变量仍然兼容。如果 `STUDYMATE_*` 对应字段为空，程序会回退读取：

~~~text
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=
~~~

DeepSeek 配置示例：

~~~text
STUDYMATE_PROVIDER=deepseek
STUDYMATE_BASE_URL=https://api.deepseek.com
STUDYMATE_MODEL=deepseek-chat
STUDYMATE_API_KEY=填写你的 DeepSeek API Key
~~~

当前实现适配的是 OpenAI 兼容的 `/chat/completions` 接口；不符合 OpenAI 协议的供应商，需要另外实现 Provider Adapter。

如果 DeepSeek 返回 `HTTP 402 Insufficient Balance`，说明 API 请求已经到达服务端，但账户余额不足，需要在 DeepSeek 开放平台充值或更换有余额的 API Key。

不要把 API Key 或 .env 提交到 Git。

## 6. 当前功能

当前版本已经实现：

- 递归读取 Markdown / TXT 知识库。
- 文档标题识别。
- 文档切分。
- 本地关键词检索。
- CLI 对话服务。
- 问题、学习目标、关键词输入分类。
- 回答来源校验。
- /help、/sources、/reset、/quit 命令。
- OpenAI 兼容模型调用适配。
- 自动更新 Claude Code、OpenCode、Codex 官方 Markdown 文档。

当前搜索基线是本地内存关键词检索。后续根据评估结果再升级 SQLite FTS5、Embedding 或混合检索。

## 7. 当前问答实现

StudyMate 当前采用：

~~~text
本地知识库读取
  -> 文档切分
  -> 本地关键词检索 Top-K
  -> 拼接相关知识片段和短期历史
  -> 一次性调用 AI 模型
  -> 解析结构化回答
  -> 校验引用并显示答案
~~~

### 7.1 是否流式

NewAPI 配置默认使用流式请求。StudyMate 会接收完整的流式片段，在本地聚合 JSON 后一次性打印结构化答案；因此当前 CMD 还不会逐字显示生成过程。

对应代码：

- `src/studymate/llm.py`：构造 Prompt、调用模型、解析 JSON。
- `src/studymate/cli.py`：读取完整回答后打印到 CMD。

如果模型网关返回 `HTTP 403 Your request was blocked`，先检查 debug 日志中的 `user_agent`。当前 Huazi 的 Cloudflare 会拦截 `OpenAI/Python`，而 AI SDK 风格的 User-Agent 可以通过。该问题发生在模型鉴权之前，不代表 Key 或模型权限错误。

### 7.2 是否有历史记录

当前有“当前进程内的短期历史”，但没有持久化历史：

- 每次问答会保存用户问题和模型回答。
- 默认最多保留 10 条消息。
- 实际发送给模型时使用最近 6 条消息，约 3 轮对话。
- `/reset` 会清空历史。
- 退出程序或重新启动后，历史会丢失。
- 当前没有 SQLite、文件会话或用户会话 ID。

对应代码：`src/studymate/chat.py`、`src/studymate/llm.py`。

### 7.3 检索和模型的边界

每次提问都会使用“当前问题”进行本地关键词检索，默认取 Top 5 片段。历史会发送给模型帮助理解“它”“上一个问题”等指代，但当前不会使用历史改写检索问题。

如果没有检索到证据，StudyMate 会直接返回“知识库中没有足够依据”，不会调用模型。检索到证据后，模型只能基于传入片段生成回答。

模型返回的引用还会经过校验。如果引用不属于本次检索结果，回答会被拦截，避免产生无法追溯的来源。

### 7.4 当前能力边界

| 能力 | 当前状态 |
| --- | --- |
| 本地 Markdown/TXT 检索 | 已实现 |
| AI 模型生成回答 | 已实现，NewAPI 默认流式请求并在本地聚合 |
| 当前会话短期历史 | 已实现，仅内存保存 |
| 历史持久化 | 尚未实现 |
| 基于历史改写检索 | 尚未实现 |
| Embedding/向量检索 | 尚未实现 |
| 流式请求 | 已实现；当前 CMD 聚合完整 JSON 后一次性显示 |

## 8. 代码更新记录

以下记录用于追踪功能、代码位置和验证方式。后续新增功能时，继续在本节追加记录。

| 日期 | 功能 | 主要代码位置 | 更新内容和验证 |
| --- | --- | --- | --- |
| 2026-08-02 | RAG 基础问答 | `src/studymate/ingest.py`、`src/studymate/search.py`、`src/studymate/chat.py` | 递归读取知识库、切分文档、本地关键词检索、拼接证据后调用模型。 |
| 2026-08-02 | 非流式模型调用 | `src/studymate/llm.py`、`src/studymate/cli.py` | 使用 OpenAI 兼容 Chat Completions，一次性返回结构化 JSON。 |
| 2026-08-02 | 短期对话历史 | `src/studymate/chat.py`、`src/studymate/llm.py` | 保存当前进程内最近消息；支持 `/reset`，不做持久化。 |
| 2026-08-02 | 引用安全校验 | `src/studymate/citations.py`、`src/studymate/models.py` | 校验模型引用是否来自实际检索片段。 |
| 2026-08-02 | 在线文档更新 | `config/docs_sources.json`、`src/studymate/docs_updater.py`、`scripts/update_docs.py` | 支持 Claude Code、OpenCode、Codex 配置化更新，并写入 `knowledge/<source-id>/`。 |
| 2026-08-02 | CMD 更新命令 | `src/studymate/input.py`、`src/studymate/chat.py`、`src/studymate/cli.py` | 支持 `update-docs`、`/update`、`/update codex`，更新后自动重载检索索引。 |
| 2026-08-02 | 测试和开发依赖 | `tests/`、`pyproject.toml` | 已安装 pytest，当前测试结果为 `25 passed`。 |
| 2026-08-02 | 模型服务错误处理 | `.env`、`src/studymate/llm.py`、`src/studymate/chat.py`、`tests/integration/test_query_workflow.py` | 支持 DeepSeek/OpenAI 兼容接口；将 402 余额不足、鉴权失败和限流错误转换为可读提示，并显示当前接口和模型，避免会话崩溃；测试结果为 `26 passed`。 |
| 2026-08-02 | 通用 Provider 配置 | `.env`、`.env.example`、`src/studymate/llm.py`、`tests/contract/test_llm_contract.py` | 增加 `type/provider/endpointType/apiKey/baseUrl/model` 对应配置；兼容 NewAPI 的 `/v1` 地址和不同 OpenAI 兼容模型；测试结果为 `27 passed`。 |
| 2026-08-02 | API 请求诊断 | `src/studymate/llm.py`、`.env`、`.env.example` | 增加 `STUDYMATE_DEBUG`；输出最终请求 URL、Key 来源/长度、模型和脱敏服务端错误，辅助定位 401/403/402。 |
| 2026-08-02 | NewAPI 请求兼容 | `src/studymate/llm.py`、`.env`、`tests/contract/test_llm_contract.py` | NewAPI 默认不发送 `response_format`，兼容 Claude 上游；增加代码块 JSON 解析；测试结果为 `28 passed`。 |
| 2026-08-02 | Cherry Studio / Huazi 请求兼容 | `src/studymate/llm.py`、`.env`、`.env.example`、`tests/contract/test_llm_contract.py` | 对齐 Cherry Studio 的 `/v1`、额外 headers、流式请求和 `ai-sdk/openai-compatible/2.0.37` User-Agent；定位并修复 Huazi Cloudflare 拦截 `OpenAI/Python` 导致的 403；测试结果为 `29 passed`（另有 3 个受本机 pytest 临时目录权限影响的用例未执行）。 |
| 2026-08-02 | Claude 引用格式兼容 | `src/studymate/llm.py`、`tests/contract/test_llm_contract.py` | 将模型返回的已检索 `chunk_id` 字符串补全为可审计引用对象；非法响应转换为可读错误，不再导致 CLI 堆栈退出；真实 CMD 问答验证通过。 |

当前待办方向：先补充 CMD 增量显示和历史持久化，再根据检索评估结果升级 Embedding 或混合检索。

## 9. 开发流程

1. 先阅读 docs/ 中的需求和接口契约。
2. 先运行测试，确认当前失败点。
3. 只实现让当前测试通过的最小代码。
4. 补充边界测试。
5. 更新 README、评估数据和 ADR。

测试命令：

~~~powershell
py -m pytest
~~~
