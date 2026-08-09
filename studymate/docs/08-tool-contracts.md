# 第一阶段工具契约

## `search_knowledge`

用途：在本地知识库中检索与用户问题相关的 Markdown/TXT 片段。

输入：

```json
{
  "query": "MCP 和 Tool Calling 的区别",
  "top_k": 5
}
```

约束：

- `query` 不能为空。
- `top_k` 范围为 1 到 10。
- 只读，不修改文件。

输出包括查询词、结果片段、文档路径、行号、匹配分数和可用于引用的 `chunk_id`。

## `open_document`

用途：打开知识库内的指定 Markdown/TXT 文档或行范围。

输入：

```json
{
  "path": "ai-agent/mcp.md",
  "start_line": 1,
  "end_line": 80
}
```

约束：

- 路径必须位于 `knowledge/` 根目录内。
- 禁止通过 `..` 访问知识库外部文件。
- 只允许 `.md`、`.markdown` 和 `.txt`。
- 只读，不执行文件内容。

## 工具执行规则

- 模型只生成工具名称和参数，不能直接执行 Python 或文件系统操作。
- `ToolRegistry` 校验工具名称和 Pydantic 参数模型。
- 工具异常会作为结构化错误返回给 Agent，由 Agent 决定是否结束。
- 后续增加有副作用的工具时，必须单独增加确认策略和测试。
