# AI Agent 练手项目推荐

> 面向候选人：高雨晨  
> 目标：用项目支撑 AI Agent、AI Coding、RAG、隐私安全方向社招投递  
> 更新时间：2026-08-02

---

## 1. 项目选择原则

你不需要做很多零散 Demo。建议做：

- 2 个主项目。
- 1 个已有项目升级。
- 2 个小组件。

推荐组合：

| 优先级 | 项目 | 作用 |
|---:|---|---|
| P0 | PrivacyAgent 2.0 | 主打隐私安全 Agent，最贴合华为经历 |
| P0 | RepoFix Agent | 主打 AI Coding，支撑开发者工具岗位 |
| P1 | DocTranslate Agent 2.0 | 升级已有 AI 文档翻译器 |
| P1 | MCP 工具服务器 | 补齐 MCP / Tool Calling 关键词 |
| P1 | Agent Eval Harness | 补齐评估、观测、成本控制能力 |

最推荐先做：

~~~text
PrivacyAgent 2.0 -> RepoFix Agent -> MCP Server -> Agent Eval Harness -> DocTranslate Agent 2.0
~~~

---

## 2. 项目 A：PrivacyAgent 2.0

### 定位

面向移动应用与鸿蒙生态的隐私合规智能体，结合法规 RAG、规则引擎、日志语义检测、UI 遍历和人机审核，自动生成可追溯的隐私风险报告。

### 为什么最适合你

- 直接继承你在华为的隐私合规经历。
- 有真实业务指标，不像普通 Demo。
- 可以突出 AI Agent、规则系统、安全护栏、RAG、HITL。
- 面试时可以讲得很深。

### 核心模块

| 模块 | 功能 |
|---|---|
| Policy RAG | 检索法规、公司规范、历史案例 |
| Rule Engine | 执行确定性规则，如日志泄露、权限调用、敏感字段检测 |
| Semantic Judge | 使用 LLM 判断模糊场景，输出结构化风险 |
| UI Traverse Agent | 自动遍历页面，触发隐私数据访问路径 |
| Vision Skill | 识别截图中的授权弹窗、隐私提示、敏感文案 |
| HITL Review | 高危结论进入人工审核 |
| Report Generator | 生成风险报告、证据片段和修复建议 |
| Eval Harness | 统计准确率、误报率、召回率、Token 成本 |

### 推荐技术栈

- Python。
- FastAPI。
- LangGraph。
- Pydantic。
- Qdrant 或 pgvector。
- SQLite / PostgreSQL。
- Docker。
- React + Tauri，可选。

### MVP 范围

第一版不要做太大，只做这些：

- 支持上传一批日志。
- 支持 10-20 条隐私检测规则。
- 支持法规 / 规则 RAG 检索。
- 支持 LLM 语义判断。
- 输出结构化风险报告。
- 高危结果进入人工确认。
- 记录准确率、误报率和 Token 成本。

### 进阶功能

- 接入 UI 遍历。
- 接入图像识别。
- 支持历史案例库。
- 支持多应用对比。
- 支持规则版本管理。
- 支持报告导出。

### 简历写法示例

~~~text
基于 LangGraph 重构隐私合规智能体，设计 Planner-Retriever-RuleJudge-LLMJudge-Reviewer 多节点状态机；接入法规 RAG 与结构化规则引擎，实现日志泄露、权限调用、隐私弹窗等场景的自动化检测，并通过 HITL 审核闭环降低高危误判风险。
~~~

### 建议指标

- 规则准确率。
- 规则召回率。
- 误报率下降。
- 单应用检测耗时。
- 人工审核节省时间。
- 高危风险拦截数。
- 单任务 Token 成本。

### 面试可讲难点

- 规则判断和 LLM 判断如何结合。
- 如何减少误报。
- 如何做人工复核。
- 如何保证报告可追溯。
- 如何避免模型幻觉。
- 如何处理敏感日志。

---

## 3. 项目 B：RepoFix Agent

### 定位

面向中小型代码仓库的 AI Coding Agent，支持需求理解、代码检索、方案规划、自动修改、沙箱测试、失败反思、人工确认与 PR 报告生成。

### 为什么适合你

- 直接对齐 AI Coding 岗位。
- 能展示代码理解、Agent 编排、沙箱安全、自动测试。
- 能和 Codex/OpenCode 实战经历形成闭环。
- 比普通聊天机器人更有面试区分度。

### 核心流程

~~~text
Issue / 用户需求
  -> Planner Agent：拆解任务、定位候选文件
  -> Code Retriever：代码 RAG + AST 检索
  -> Coder Agent：生成补丁
  -> Sandbox Runner：Docker 内运行测试
  -> Reflect Agent：失败时分析日志并修复
  -> Reviewer Agent：安全、风格、影响面审查
  -> Human Approval：人工确认危险修改
  -> PR Summary：生成 PR 描述和测试报告
~~~

### 推荐技术栈

- Python。
- FastAPI。
- LangGraph。
- Pydantic。
- tree-sitter 或 Python ast。
- Docker。
- pytest。
- SQLite。
- GitPython，可选。

### MVP 范围

第一版只支持 Python 仓库即可：

- 读取仓库文件树。
- 识别测试文件。
- 根据用户需求定位候选文件。
- 生成代码 diff。
- 在 Docker 中执行 pytest。
- 失败后反思并重试一次。
- 输出测试报告和 PR 文案。

### 进阶功能

- 支持 TypeScript / Node 项目。
- 支持 GitHub API 创建 PR。
- 支持多模型路由。
- 支持代码改动风险分级。
- 支持依赖图检索。
- 支持 benchmark 回放。

### 简历写法示例

~~~text
独立开发 RepoFix Agent，基于 LangGraph 实现 Planner-Coder-Tester-Reviewer 多智能体闭环；通过 AST + 向量检索定位相关代码，在 Docker 沙箱中执行 pytest 并基于失败日志进行反思修复，最终输出代码 diff、测试报告与 PR 摘要。
~~~

### 建议指标

- 20 个自建 Issue benchmark 的一次修复成功率。
- 反思后成功率提升。
- 平均 Token 成本。
- 平均执行耗时。
- 测试通过率。
- 人工确认拦截的高风险操作数量。

### 面试可讲难点

- 代码仓库如何索引。
- 如何做 Code RAG。
- AST 信息如何辅助检索。
- 为什么必须使用沙箱。
- 如何防止误删文件。
- 测试失败后如何自动定位问题。

---

## 4. 项目 C：DocTranslate Agent 2.0

### 定位

面向专业文档翻译的多 Agent 工作流，解决术语一致性、长文档上下文、格式还原、质量审查和失败恢复问题。

### 为什么适合你

- 你已经有 AI 文档翻译器基础。
- 可以把已有项目升级为 Agentic Workflow。
- 能突出多格式文档处理、Office XML、OCR、任务流水线。
- 对 RAG、企业知识库、本地化、出海文档岗位也有帮助。

### 核心模块

| 模块 | 功能 |
|---|---|
| File Classifier | 识别 Word、PDF、PPT、Excel、图片 |
| Layout Parser | 解析 Office XML、OCR、表格结构 |
| Termbase RAG | 检索术语库，保证术语一致 |
| Translator Agent | 分块翻译 |
| Context Manager | 管理章节摘要和长文本上下文 |
| QA Agent | 检查数字、单位、专有名词、术语一致性 |
| Repair Agent | 修复错位表格、遗漏段落、格式破坏 |
| Cost Monitor | 统计 Token 成本、重试次数、失败原因 |

### MVP 范围

- 先支持 Word 和 PDF。
- 支持术语库 RAG。
- 支持翻译后 QA。
- 支持遗漏段落检查。
- 支持数字和单位一致性检查。
- 输出质量报告。

### 进阶功能

- 支持 PPT 和 Excel。
- 支持公式保护。
- 支持复杂表格修复。
- 支持多模型路由。
- 支持批量任务看板。

### 简历写法示例

~~~text
将多格式文档翻译器升级为 Agentic Workflow：引入术语库 RAG、翻译 QA Agent 与格式 Repair Agent，围绕 Office XML / OCR / 表格结构建立可重试流水线，实现复杂文档翻译、排版还原与质量审查闭环。
~~~

### 建议指标

- 翻译准确率。
- 术语一致率。
- 排版还原准确率。
- 人工二次干预率。
- 失败重试成功率。
- 单文档 Token 成本。

### 面试可讲难点

- 长文档如何分块。
- 术语一致性如何保证。
- 表格和公式如何保护。
- 翻译质量如何评估。
- 失败任务如何恢复。
- 多模型路由如何设计。

---

## 5. 小项目 D：MCP 工具服务器

### 定位

写一个本地 MCP Server，提供文件搜索、Git diff、测试执行、日志脱敏、隐私规则查询等工具。

### 为什么要做

MCP 是 Agent 工具接入的重要标准。你做一个小而完整的 MCP Server，就能在面试中讲清楚工具协议、权限、安全边界和 schema 设计。

### 推荐工具

| 工具 | 功能 |
|---|---|
| search_files | 搜索文件 |
| read_file | 读取文件 |
| get_git_diff | 获取 Git diff |
| run_tests | 执行测试 |
| scan_secret | 扫描敏感信息 |
| query_privacy_policy | 查询隐私规则 |
| redact_log | 日志脱敏 |

### MVP 要求

- 每个工具都有 schema。
- 工具调用有参数校验。
- 危险工具需要确认。
- 日志中敏感信息要脱敏。
- 工具失败要返回结构化错误。

### 简历写法示例

~~~text
自研本地 MCP 工具服务器，封装文件搜索、Git diff、测试执行、日志脱敏和隐私规则查询等能力，通过 schema 校验、工具白名单和结构化错误处理实现 Agent 工具调用的标准化与最小权限控制。
~~~

---

## 6. 小项目 E：Agent Eval Harness

### 定位

专门用于评估 Agent 的小框架，记录每次任务的成功率、工具调用成功率、成本和失败原因。

### 为什么要做

很多候选人只会做 Demo，不会评估。Agent Eval Harness 可以证明你知道如何把 Agent 做成可迭代、可观测、可优化的工程系统。

### 核心功能

- JSONL 测试集。
- 任务回放。
- Tool call trace。
- 成功 / 失败标签。
- Token 成本统计。
- 平均重试次数。
- 失败原因分类。
- Markdown 报告生成。

### 推荐指标

| 指标 | 含义 |
|---|---|
| task_success_rate | 任务成功率 |
| tool_success_rate | 工具调用成功率 |
| avg_retry_count | 平均重试次数 |
| avg_token_cost | 平均 Token 成本 |
| human_review_rate | 人工介入比例 |
| hallucination_rate | 幻觉率 |
| refusal_rate | 拒答率 |

### 简历写法示例

~~~text
构建 Agent Eval Harness，对 Agent 任务进行 JSONL 回放测试，记录工具调用轨迹、任务成功率、平均重试次数、Token 成本和失败原因分类，为后续 prompt、检索和工具策略优化提供数据依据。
~~~

---

## 7. 推荐开发顺序

### 第一步：PrivacyAgent 2.0

原因：

- 最贴合你的真实经历。
- 最容易形成差异化。
- 最适合面试深挖。

完成标准：

- 有 README。
- 有架构图。
- 有 demo。
- 有 20-30 条测试样本。
- 有准确率、误报率、成本指标。

### 第二步：RepoFix Agent

原因：

- 直接支撑 AI Coding 岗。
- 能展示 Agent 闭环和工程能力。

完成标准：

- 能读取一个 Python 仓库。
- 能定位文件。
- 能生成 diff。
- 能跑 pytest。
- 能失败反思一次。
- 能输出 PR 摘要。

### 第三步：MCP Server

原因：

- 补齐 Tool Calling / MCP 关键词。
- 可以被 PrivacyAgent 和 RepoFix Agent 复用。

完成标准：

- 至少 5 个工具。
- schema 完整。
- 权限可控。
- 错误结构化。

### 第四步：Agent Eval Harness

原因：

- 补齐 Agent 评估能力。
- 面试很加分。

完成标准：

- 支持 JSONL 测试集。
- 支持任务回放。
- 输出 Markdown 报告。
- 统计成功率和成本。

### 第五步：DocTranslate Agent 2.0

原因：

- 复用已有项目。
- 用于拓展 RAG、文档智能处理方向。

完成标准：

- 术语库 RAG。
- QA Agent。
- Repair Agent。
- 质量报告。

---

## 8. GitHub README 模板

每个项目 README 建议包含：

~~~text
项目背景
核心功能
系统架构
技术栈
快速开始
Agent 工作流
工具列表
安全设计
评估指标
Demo 截图
后续计划
~~~

不要只写“这是一个 AI Agent 项目”。一定要写清：

- 输入是什么。
- 输出是什么。
- 工具有哪些。
- 状态怎么流转。
- 失败怎么处理。
- 如何评估效果。
- 如何控制成本。
- 如何保证安全。

---

## 9. 最小可展示标准

一个项目可以放进简历，至少要满足：

- 可以本地运行。
- 有 README。
- 有架构图。
- 有 1 个 demo 截图或录屏。
- 有测试样本。
- 有 2-3 个量化指标。
- 有失败处理说明。
- 有安全边界说明。

如果只停留在“调用一次大模型返回答案”，不建议写进简历。

