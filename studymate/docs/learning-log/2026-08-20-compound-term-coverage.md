# 2026-08-20：紧凑术语完整覆盖与检索误召回修复

## 问题

对比检索时发现，查询 `agentruntime` 在内存 BM25 风格后端中可能返回只包含 `agent` 的 Chunk：

```text
agentruntime -> agent runtime
查询词       -> agent, runtime
通用覆盖率   -> 只要命中 50% 即可保留
```

因此，只有 `agent` 没有 `runtime` 的文档也可能进入结果。SQLite 后端在本次知识库上表现得更严格，但不能依赖后端的偶然差异来保证语义完整性。

## 方案

新增 `_required_compound_phrases()` 和 `_has_required_compound_coverage()`：

1. 只检查原始 query 中明确出现的紧凑术语，例如 `agentruntime`、`agentloop`、`toolcalling`。
2. 将紧凑术语展开为组成词。
3. 要求组成词全部出现在同一个 Chunk 的可检索词项中。
4. 内存和 SQLite 后端使用同一过滤规则。

没有把所有查询的覆盖率改成 100%。例如 `Claude Code 中如何定义自定义工具？` 中，回答问题的 Chunk 可能只包含 `custom tools`，不一定重复 `Claude Code`；这种查询仍使用原有通用覆盖率规则。

## 验证结果

验证日志：[`logs/search-comparison-compound-coverage-20260820.jsonl`](../../logs/search-comparison-compound-coverage-20260820.jsonl)

| Query | Memory | SQLite | 结论 |
| --- | --- | --- | --- |
| `agentruntime` | 只返回同时包含 `agent,runtime` 的 Chunk | 只返回同时包含 `agent,runtime` 的 Chunk | 部分匹配已过滤 |
| `agentloop` | 命中 `agent-loop.md` | 命中 `agent-loop.md` | 紧凑术语仍可召回 |
| `agent` | 正常返回结果 | 正常返回结果 | 普通查询未被误伤 |
| `Claude Code 中如何定义自定义工具？` | 命中 Claude Code custom tools | 命中 custom tools 相关文档 | 中英文混合查询保持可用 |

## 测试

新增回归测试，覆盖：

- `agentruntime` 不返回只有 `agent` 的 Chunk。
- `agentruntime` 在内存和 SQLite 后端保持一致过滤。
- `agentloop` 归一化后命中正确的 `agent-loop.md` 文档。
- 普通 `agent` 查询和自定义工具查询不受影响。

完整结果：`94 passed`。

## 学习结论

这个问题说明“查询归一化”和“查询覆盖率”是两个不同步骤：

- 归一化负责把 `agentruntime` 转换为 `agent runtime`。
- 覆盖率负责判断一个 Chunk 是否足以支持这个概念。
- 通用覆盖率适合自然语言查询，但对已知复合术语可能过于宽松。
- 复合术语可以使用更严格的局部规则，而不必牺牲所有查询的召回率。

下一步可以把这类规则纳入评测集，观察 `Hit@K`、`Recall@K` 和 `MRR` 是否改善，并继续检查未知紧凑标识符是否正确返回空结果。
