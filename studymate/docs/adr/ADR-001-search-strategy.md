# ADR-001：采用可替换的本地检索接口

## 状态

Accepted

## 背景

StudyMate 的目标是理解 RAG 的检索、上下文组装和引用流程。当前知识库规模适合本地运行，不需要先引入向量数据库或外部检索服务。

此前的检索实现直接由 `InMemorySearchIndex` 提供，Agent 工具虽然通过 `search()` 调用它，但没有明确的后端接口。这样会让后续切换 SQLite FTS5、向量检索或混合检索时触碰 Agent 和工具层。

## 决策

定义统一的 `SearchIndex` Protocol：

~~~python
class SearchIndex(Protocol):
    def search(self, query: str, top_k: int = 5) -> list[SearchResult]: ...
~~~

定义两个遵守该接口的词法检索后端：

1. `InMemorySearchIndex`：无额外依赖的本地 BM25 风格实现，适合学习、测试和小型知识库。
2. `SQLiteFTS5SearchIndex`：使用 Python 标准库 `sqlite3` 的 FTS5 虚拟表和 SQLite 内置 `bm25()`，适合需要持久化索引和更大 Chunk 数量的场景。

两个后端共同使用以下查询和结果约束：

- 大小写、CamelCase、连字符和下划线归一化。
- `agentloop`、`agentruntime` 等领域紧凑写法归一化。
- 中英文查询停用词过滤和领域词扩展。
- 内容、标题、路径、查询覆盖率和短语匹配综合评分。
- Chunk ID 去重，保证同一证据不重复返回。

数据流：

~~~text
Markdown / TXT
  -> Chunk
  -> SearchIndex
  -> InMemorySearchIndex 或 SQLiteFTS5SearchIndex
  -> Top-K SearchResult
  -> Agent Tool / LLM Context
~~~

## 原因

- 不增加运行时服务和第三方依赖；SQLite 来自 Python 标准库，但要求当前 Python 的 SQLite 编译启用 FTS5。
- BM25 的词频、逆文档频率和文档长度归一化比简单关键词计数更稳定。
- Agent、`KnowledgeTools` 和 `ChatService` 只依赖 `SearchIndex`，后端可替换。
- 评测可以在同一个契约下比较不同检索实现。
- 查询归一化和字段加权的行为可以用单元测试复现和解释。

## 后续升级条件

Embedding 和 Reranker 的实验性代码暂时保留，但不进入当前主流程：

1. `EmbeddingSearchIndex` 使用 OpenAI-compatible `/embeddings` 接口，将 Chunk 和查询转换为向量，并以余弦相似度召回。
2. `RerankingSearchIndex` 是一个装饰器，对内存、SQLite 或 Embedding 召回的候选结果进行二次排序。
3. 当前 `compare-search` 只比较内存和 SQLite 两个词法后端，将来重新启用 Embedding/Reranker 前，必须先确认 API 成本和批量限制。

新后端必须实现同一个 `SearchIndex.search()` 接口，并保留 `SearchResult` 的 Chunk、分数和来源字段，不能破坏引用校验。

## 后果

- 当前检索仍然不是完整语义检索，同义表达和跨语言语义可能漏召回。
- 内存索引和 SQLite 索引当前都会在启动时依据最新 Chunk 构建；SQLite 额外保留索引文件，但不会自动监听知识库文件变化。
- 两个后端的原始分数不具有跨实现可比性，应通过评测指标比较。
- Embedding 分数代表向量余弦相似度，Reranker 分数代表模型对查询和候选 Chunk 的相关性判断；它们也不应和 BM25 原始分数直接比较。
- Embedding 和 LLM Reranker 会产生额外 API 请求和成本，当前 CLI 关闭，不作为主流程能力。
- 检索行为已经可测试、可解释，且后续替换后端不会改变 Agent 工具契约。
