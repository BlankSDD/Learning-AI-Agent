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

## 3. SearchResult

~~~text
SearchResult
  chunk: Chunk
  score: float
  matched_terms: list[str]
~~~

## 4. Citation

~~~text
Citation
  chunk_id: str
  path: str
  title: str
  start_line: int
  end_line: int
  quote: str
~~~

## 5. Answer

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

## 6. Intent

~~~text
Intent
  kind: question | goal | keyword | command
  text: str
  command: str | None
~~~

## 7. 推荐函数接口

~~~text
load_documents(root) -> list[Document]
chunk_document(document) -> list[Chunk]
search(query, top_k) -> list[SearchResult]
classify_input(text) -> Intent
answer(input, evidence, history) -> Answer
handle_command(text) -> CommandResult
~~~

