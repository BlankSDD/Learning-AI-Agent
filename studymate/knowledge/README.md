# StudyMate 知识库

请把自己的学习资料放在这个目录下。

支持的文件类型：

- .md
- .markdown
- .txt

StudyMate 会递归扫描子目录，因此可以按主题组织：

~~~text
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

目录名和文件名会作为来源路径的一部分显示在回答中。

Claude Code、OpenCode 和 Codex 的官方文档可以通过项目根目录的文档更新器拉取：

~~~powershell
cd D:\develop_projects\Learning-AI-Agent\studymate
py -m studymate update-docs --proxy 127.0.0.1:7897
~~~

配置文件是 `config/docs_sources.json`。只更新一个来源时使用 `--only claude-code`、`--only opencode` 或 `--only codex`。

不要放入：

- API Key。
- .env 文件。
- 公司保密文档。
- 用户隐私数据。
- 未确认可以公开的内部资料。
