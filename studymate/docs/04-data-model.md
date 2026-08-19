# StudyMate 数据模型与接口契约

## 1. Document

~~~text
Document
  id: str
  path: str
  title: str
  content_hash: str
  text: str
~~~

约束：

- id 在同一知识库内稳定。
- path 必须是知识库根目录下的相对路径。
- content_hash 用于避免重复导入。

## 2. Chunk

~~~text
Chunk
  id: str
  document_id: str
  path: str
  title: str
  text: str
  start_line: int
  end_line: int
~~~

## 3. SearchIndex

StudyMate 的 Agent 和工具层只依赖以下检索接口，具体实现可以替换：

~~~text
SearchIndex.search(query: str, top_k: int = 5) -> list[SearchResult]
~~~

当前有两个实现：

- `InMemorySearchIndex`：在进程内保存 Chunk，使用 Python 实现的 BM25 风格评分。
- `SQLiteFTS5SearchIndex`：把 Chunk 的元数据保存到普通 SQLite 表，把可检索字段保存到 FTS5 虚拟表，使用 SQLite `bm25()` 排序。

两个实现都负责查询归一化、词项扩展、排序和结果去重；都不负责调用模型，也不负责生成回答。调用方只依赖 `SearchIndex`，所以 Agent 工具不需要知道当前使用哪一个后端。

SQLite FTS5 的基本结构：

~~~text
Chunk
  -> chunk_metadata（完整来源和行号）
  -> chunks_fts（path / title / text 的词法索引）
  -> bm25()
  -> SearchResult
~~~

索引生命周期与知识库源文件分开管理：

1. `build-index` 读取 Markdown/TXT、切分 Chunk，并写入 `data/studymate-search.sqlite3`。
2. Chat、Eval 和 `compare-search` 运行时只读打开这个数据库，不根据知识库重新构建。
3. 知识库文档更新后，用户需要主动再次运行 `build-index`。
4. SQLite 数据库是可重建的索引产物，不能替代 `knowledge/` 下的源文件。

这里的 FTS5/BM25 是词法检索：依赖词项是否出现、词频和文档频率；它和 Embedding 向量检索是两条不同的路线。

## 3.1 EmbeddingSearchIndex（实验性，当前未启用）

~~~text
EmbeddingSearchIndex.search(query, top_k)
  -> query embedding
  -> 每个 Chunk 的 embedding
  -> cosine similarity
  -> Top-K SearchResult
~~~

Embedding 分数表示向量相似度，和 BM25 分数没有相同的数值含义。当前实现通过 OpenAI-compatible `/embeddings` 接口生成向量，并使用本地 JSON 文件缓存 Chunk 向量。

## 3.2 Reranker（实验性，当前未启用）

Reranker 不负责从全部知识库中召回结果，而是处理已有候选集：

~~~text
BM25 / FTS5 / Embedding Top-N
  -> Reranker 判断 query 与 Chunk 的相关性
  -> 重新排序
  -> Top-K SearchResult
~~~

当前实现使用 OpenAI-compatible Chat Completions 输出 0 到 1 的候选相关性分数。它是可选的二阶段处理，会增加延迟和 Token 成本。

## 4. SearchResult

~~~text
SearchResult
  chunk: Chunk
  score: float
  matched_terms: list[str]
~~~

## 5. Citation

~~~text
Citation
  chunk_id: str
  path: str
  title: str
  start_line: int
  end_line: int
  quote: str
~~~

## 6. Answer

~~~text
Answer
  answer: str
  citations: list[Citation]
  confidence: float
  need_more_context: bool
  next_steps: list[str]
~~~

约束：

- confidence 范围为 0 到 1。
- citations 中的路径必须真实存在于 SearchResult。
- need_more_context 为 true 时，回答必须说明证据不足。

## 7. Intent

~~~text
Intent
  kind: question | goal | keyword | command
  text: str
  command: str | None
~~~

## 8. 推荐函数接口

~~~text
load_documents(root) -> list[Document]
chunk_document(document) -> list[Chunk]
SearchIndex.search(query, top_k) -> list[SearchResult]
classify_input(text) -> Intent
answer(input, evidence, history) -> Answer
handle_command(text) -> CommandResult
~~~
