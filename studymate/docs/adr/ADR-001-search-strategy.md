# ADR-001：第一版采用 SQLite FTS5 作为检索基线

## 状态

Accepted

## 背景

StudyMate 的第一目标是理解 RAG 的检索、上下文组装和引用流程，而不是学习部署向量数据库。

## 决策

第一版使用 SQLite FTS5 或等价的本地全文检索实现：

~~~text
Markdown / TXT
  -> Chunk
  -> SQLite FTS5
  -> Top-K SearchResult
  -> LLM Context
~~~

## 原因

- 不需要额外服务。
- Windows 本地运行简单。
- 支持 BM25 排序。
- 便于测试和复现。
- 可以清楚观察检索错误。

## 后续升级条件

只有在以下情况出现时，再加入 Embedding 和向量检索：

- 同义表达导致关键词检索明显失败。
- 30 条评估问题中 Retrieval Hit Rate 不达标。
- 需要处理大量长文档。

## 后果

- 第一版语义检索能力有限。
- 但可以先建立可测量的基线。
- 后续可以比较关键词检索、向量检索和混合检索的差异。

