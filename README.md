# Learning AI Agent

用于系统学习 AI Agent、RAG、Tool Calling 和 AI Coding 的实践仓库。

## 当前项目

`studymate/` 是一个本地优先的 CMD 知识库问答工具：

- 递归读取 Markdown/TXT 知识库
- 本地检索相关片段，再调用 OpenAI-compatible 模型生成回答
- 返回可验证的文档来源
- 支持 Claude Code、OpenCode、Codex 官方文档更新
- 支持 DeepSeek、NewAPI 及其他 OpenAI-compatible 接口

## 快速运行

```powershell
cd studymate
.\.venv\Scripts\python.exe -m studymate chat --knowledge .\knowledge
```

首次使用时复制 `.env.example` 为 `.env`，填写模型服务配置和 API Key。`.env` 不会提交到 GitHub。

知识库文件放在 `studymate/knowledge/` 下，支持继续添加子目录和 Markdown 文件。在线文档可以使用：

```powershell
.\.venv\Scripts\python.exe -m studymate update-docs --knowledge .\knowledge
```

## 文档

- [AI Agent 学习路线](01_AI_Agent_学习路线.md)
- [AI Agent 简历与求职建议](02_AI_Agent_简历求职建议.md)
- [AI Agent 练手项目推荐](03_AI_Agent_练手项目推荐.md)
- [StudyMate README](studymate/README.md)
- [StudyMate 需求与架构文档](studymate/docs/)

## 测试

```powershell
cd studymate
.\.venv\Scripts\python.exe -m pytest
```

当前 StudyMate 已完成 RAG 基础问答、流式模型调用、引用校验和配置化文档更新。后续将继续实现工具调用、Agent 循环和 AI Coding 能力。
