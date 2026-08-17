# 2026-08-18：本地检索基线、Embedding 成本与测试验证

## 一、今天完成的学习

今天重点确认了 Embedding、BM25、SQLite FTS5 和 Reranker 在 RAG 检索链路中的位置，并根据当前项目的成本和学习目标收敛了实现范围。

用户问题：Embedding 是不是只要在本地实现算法，就可以把所有文本转换成向量？为什么全量生成会产生大量 API 请求？

结论：当前 `EmbeddingSearchIndex` 使用的是在线 Embedding 模型。每个 Chunk 需要发送给远程 `/embeddings` 接口，查询时还需要发送查询文本；知识库约有 40,866 个 Chunk，即使接口支持批量，也会因为批量大小限制产生多次请求。Embedding 不是一个仅靠 BM25 或 FTS5 就能自动得到的本地属性，除非另外部署本地 Embedding 模型。

因此本阶段决定：主流程暂时不使用 Embedding，也不使用 LLM Reranker，只保留可解释、无额外模型成本的本地词法检索。

## 二、核心理解

### 1. Embedding 与 BM25 的区别

- BM25 是词法检索：依赖词项是否出现、词频、逆文档频率和 Chunk 长度。
- Embedding 是语义检索：把查询和 Chunk 转为向量，再计算余弦相似度。
- BM25 适合精确术语、文件名、API 名称和标识符。
- Embedding 适合同义表达、口语化问题和词面不同但语义相近的内容。

Embedding 不是把每个词简单计数，而是将词、句子或 Chunk 映射到稠密向量空间。向量分数也不能和 BM25 原始分数直接比较。

### 2. Reranker 的位置

Reranker 是二阶段排序器，不负责扫描全部知识库：

~~~text
BM25 / FTS5 / Embedding 召回 Top-N
  -> Reranker 逐个判断 query 与 Chunk 的相关性
  -> 重新排序
  -> 最终 Top-K
~~~

Reranker 需要对召回的候选 Chunk 再调用模型判断相关性，会增加 API 调用、延迟和 Token 成本，因此当前主流程关闭。

## 三、本次实现

### 代码位置

| 能力 | 位置 |
| --- | --- |
| Embedding Provider、EmbeddingSearchIndex、向量缓存 | `src/studymate/embeddings.py` |
| Reranker Protocol、LLM Reranker、SearchIndex 装饰器 | `src/studymate/rerank.py` |
| 多后端排名打印和 JSONL 记录 | `src/studymate/comparison.py` |
| CLI 参数和 `compare-search` | `src/studymate/cli.py` |

### 配置

Embedding 必须使用真正支持 `/embeddings` 的模型：

~~~dotenv
STUDYMATE_EMBEDDING_MODEL=text-embedding-3-small
STUDYMATE_EMBEDDING_API_KEY=
STUDYMATE_EMBEDDING_BASE_URL=
STUDYMATE_RERANK_MODEL=
STUDYMATE_RERANK_API_KEY=
STUDYMATE_RERANK_BASE_URL=
~~~

当前聊天模型能正常调用，不代表同一个网关或模型支持 Embedding 接口。需要根据实际供应商提供的模型列表配置；如果 Embedding 或 Reranker 使用独立网关，可以单独填写对应的 Key 和 Base URL。

### 运行比较

~~~powershell
.venv\Scripts\python.exe -m studymate compare-search `
  --knowledge .\knowledge `
  --query "agent loop 和 agent runtime 有什么区别？" `
  --query "What is MCP?" `
  --output .\logs\search-comparison.jsonl
~~~

输出包含：

- 后端名称；
- rank；
- score；
- path、title、行号；
- matched_terms；
- 文本短预览。

日志用于开发者观察检索行为，不会自动传给 Agent，也不是 `/trace`。

## 四、如何判断排序是否合理

不能只比较分数大小，因为 BM25、余弦相似度和 Reranker 分数属于不同量纲。应该观察：

1. 目标来源是否进入 Top-K。
2. 目标来源排名是否靠前。
3. 中文、英文、连字符和 CamelCase 变体是否能召回同一主题。
4. 文件名、API 标识符和精确术语是否仍由词法检索排在前面。
5. 在评测集上比较 Hit@K、Recall@K、Precision@K、MRR 和引用覆盖率。

因此，`compare-search` 是人工观察工具；最终是否更好，需要再把固定问题和期望来源纳入 Evaluation。

## 五、当前范围调整

由于当前知识库约有 40,866 个 Chunk，如果使用在线 Embedding，需要把每个 Chunk 发送给远程 Embedding 模型，并按供应商批量限制产生多次 API 请求。当前 `.env` 也没有配置 Embedding 模型，因此决定：

- 关闭主 CLI 中的 Embedding 后端，不在正常 Chat、Eval 和 `compare-search` 中自动生成向量。
- 关闭主 CLI 中的 LLM Reranker，避免额外模型请求和网络依赖。
- 保留 `src/studymate/embeddings.py` 和 `src/studymate/rerank.py` 作为后续学习实验代码。
- 当前项目主线只比较内存 BM25 风格检索和 SQLite FTS5/BM25。

## 六、当前边界与下一步

- 默认 Chat 使用内存 BM25 风格检索，也可以显式选择 SQLite FTS5/BM25。
- `compare-search` 只比较两个本地词法后端，并把结果写入 JSONL。
- 已运行完整 pytest：`71 passed in 3.10s`，测试过程未调用 Embedding API。
- CLI 的 `chat`、`eval` 和 `compare-search` 仅开放 `memory` 与 `sqlite` 两个本地检索后端。
- `src/studymate/embeddings.py` 与 `src/studymate/rerank.py` 保留为后续学习实验，但当前不属于主流程能力。

## 七、明天的学习任务：统一检索评测

日期：2026-08-19

目标：不引入 Embedding，使用固定评测集比较内存 BM25 风格检索与 SQLite FTS5/BM25，理解“检索结果好不好”如何被量化。

学习顺序：

1. 阅读 `docs/06-evaluation.md` 和 `src/studymate/evaluation.py`，明确 Hit@K、Recall@K、Precision@K、MRR、Citation Coverage 的定义。
2. 阅读 `tests/eval/questions.jsonl`，检查每个问题的期望来源是否足以支持答案。
3. 运行 `compare-search`，观察同一问题在两个本地后端中的 Top-K、分数和排名差异。
4. 选择 3 到 5 个问题，人工判断“目标文档是否真的能回答问题”，把误判补回评测集。
5. 运行完整 `pytest`，确认检索改动没有破坏 Agent、Tool Calling、Trace 和 Eval。

完成标准：能够解释两个后端的指标差异，并能指出失败来自 Chunk、查询归一化、检索排序还是评测集标注；整个过程不调用 Embedding API。

## 八、下一阶段计划：本地 RAG 与 Agent 工程化

下一阶段先做低成本、可验证的工程能力，暂不启用 Embedding：

1. **检索质量基线**：调整 Chunk 大小、重叠长度、标题边界和路径加权，用评测集验证变化。
2. **引用与拒答**：当检索证据不足时让 Agent 清晰说明不确定性，检查回答引用是否真的支持结论。
3. **可观测性完善**：让 Trace 记录检索后端、候选数量、工具耗时、停止原因和错误分类。
4. **会话与记忆**：区分当前进程短期历史、可持久化会话和知识库内容，设计最小的跨进程恢复方案。
5. **MCP 实践**：将本地知识库能力包装成只读 MCP Server，比较 MCP Tool 与当前原生 Tool Calling 的接入差异。
6. **AI Coding Agent 入门**：在隔离工作区实现文件扫描、搜索、受控修改、运行测试和 Git Diff 审查。

Embedding、向量数据库、混合检索和 Reranker 放在后续实验阶段。只有当本地词法检索评测明确暴露出同义表达召回不足时，再单独评估本地模型、在线 API 的成本和收益。
