# 2026-08-17：检索能力强化与 SearchIndex 接口

## 一、今天的问题

用户希望继续强化 StudyMate 的检索能力，并把检索部分抽象成接口，后续可以替换不同的检索后端，而不修改 Agent 和工具层。

## 二、核心理解

### 1. 检索不是 Agent 本身

检索负责从知识库中找到相关 `Chunk`，返回带分数和来源的 `SearchResult`。它不负责判断用户意图、不调用模型，也不生成最终回答。

当前边界是：

~~~text
用户问题
  -> Agent 决定调用 search_knowledge
  -> SearchIndex.search(query, top_k)
  -> SearchResult[]
  -> Agent 将结果作为工具观察交给模型
  -> 模型生成带引用的答案
~~~

### 2. 为什么要抽象接口

如果 `KnowledgeTools` 直接依赖 `InMemorySearchIndex`，以后切换 SQLite FTS5、向量检索或混合检索时，需要修改工具层和 Agent 接入代码。

现在统一为：

~~~python
class SearchIndex(Protocol):
    def search(self, query: str, top_k: int = 5) -> list[SearchResult]: ...
~~~

`ChatService` 和 `KnowledgeTools` 只依赖这个契约。当前 `InMemorySearchIndex` 是默认实现，未来的后端只要返回相同的 `SearchResult` 结构，就可以替换。

### 3. 当前检索做了什么

- 大小写归一化。
- CamelCase、连字符和下划线归一化。
- `agentloop`、`agentruntime`、`toolcalling` 等紧凑写法展开为多个词。
- 中英文停用词过滤，例如 `what`、`is`、`the`、`什么`、`如何`。
- 中文领域词扩展，例如“自定义工具”扩展为 `custom`、`tool`、`tools`。
- 内容、标题、路径、查询覆盖率和短语匹配综合评分。
- 使用词频、逆文档频率和文档长度归一化计算 BM25 风格分数。
- 根据稳定 Chunk ID 去重，避免同一证据重复返回。
- 使用最低查询覆盖率过滤只命中零散常见词的低质量结果，避免未知问题被误召回。
- 对 `FOO_BAR_123` 这类不透明标识符要求知识库出现完整标识符，防止下划线分词后被普通词污染结果。

## 三、BM25 风格评分的理解

简单关键词检索只计算“出现了几次”，容易让长文档或常见词取得不合理的高分。BM25 风格评分还考虑：

- 词频：一个词在当前 Chunk 中出现多次，相关性通常更高。
- 逆文档频率：出现在很多 Chunk 中的常见词区分度低；稀有词区分度高。
- 文档长度归一化：避免长文档仅因为词更多就天然占优。

StudyMate 还对标题、路径和完整短语加权，因为知识库中的文件名和标题通常比正文中的偶然词更能代表主题。

## 四、当前实现位置

| 内容 | 位置 |
| --- | --- |
| `SearchIndex` Protocol、查询归一化、BM25 风格排序 | `src/studymate/search.py` |
| 搜索工具依赖抽象接口 | `src/studymate/tools.py` |
| 普通对话服务依赖抽象接口 | `src/studymate/chat.py` |
| 检索行为测试 | `tests/unit/test_search.py` |
| 检索策略决策 | `docs/adr/ADR-001-search-strategy.md` |

## 五、验证结果

- 检索、工具和查询工作流测试通过。
- 搜索单元测试覆盖 `agentloop`、CamelCase、连字符、英文停用词、接口替换和 Chunk 去重。
- 完整 Agent 评测：`15/15（100%）`；`q013` 命中 `sessions.md`，`q005/q015` 均以 `empty_search` 正常停止。
- 评测仍使用相同的 `search_knowledge` 工具契约，后续应增加来源排名指标，而不只判断是否命中。

## 六、下一步学习和开发任务

1. 在评测报告中增加 Hit@K、Recall@K、Precision@K 和 MRR。
2. 记录每个问题的期望来源排名，而不只判断是否命中。
3. 对比内存 BM25 风格检索与 SQLite FTS5 的结果和启动成本。
4. 学习 Chunk 大小、标题边界和重叠区间对召回及引用的影响。
5. 只有当关键词/BM25 基线无法解决同义表达时，再评估 Embedding、混合检索和 Reranker。

## 七、检索评测指标实现

本次继续在 `EvaluationRunner` 中加入检索质量指标。指标不是 Agent 的停止条件，只是在 Agent 完成后分析这次执行是否找到了正确资料。

### 指标口径

- `Hit@K`：前 K 个来源是否至少命中一个期望来源。
- `Recall@K`：前 K 个来源命中的期望来源数，占期望来源总数的比例。
- `Precision@K`：前 K 个来源中相关来源的比例。
- `MRR`：第一个相关来源排名的倒数，越接近 1 越好。
- `Citation Accuracy`：最终引用中属于期望来源的比例。
- `Citation Coverage`：期望来源有多少被最终回答引用。
- `Abstention Rate`：所有成功用例中声明证据不足的比例。
- `Abstention Accuracy`：标注了 `should_abstain` 的用例中，拒答判断正确的比例。

Recall、MRR 和 Citation Coverage 只统计有 `expected_sources` 的正向问题；无来源问题主要用于检查误召回和拒答行为。K 默认是 5，可通过 `studymate eval --retrieval-k` 调整。

### 抽象入口

CLI 通过 `build_search_index()` 构造检索后端，返回 `SearchIndex` Protocol。后续替换为 SQLite FTS5 或混合检索时，只需要替换构造函数和后端实现，Agent、工具契约和评测指标保持不变。

## 八、关于“Bag”和 SQLite FTS5/BM25

这里用户提到的 “bag” 可以理解为 `Bag-of-Words`（词袋模型）的方向，但它不是 SQLite FTS5 本身，也不是 Embedding：

- `Bag-of-Words`：把文本看成词项集合或词频表，重点是“有哪些词、各出现几次”，不理解词语的深层语义。
- `SQLite FTS5`：负责建立全文词法索引并快速找出包含查询词的 Chunk。
- `BM25`：根据词频、逆文档频率和 Chunk 长度对 FTS5 找到的结果排序。
- `Embedding`：把文本编码成向量，用向量相似度解决同义表达和语义相近问题。

可以把本次实现记成：

~~~text
Document -> Chunk -> FTS5 词法召回 -> SQLite BM25 排序 -> SearchResult
~~~

它与之前内存检索的“互换”不是把 BM25 和内存互换，而是把“检索后端”互换：两者都实现 `SearchIndex.search()`，上层 Agent 只接收相同的 `SearchResult`。

## 九、本次实现

### 代码变更

- `src/studymate/search.py`
  - 新增 `SQLiteFTS5SearchIndex`。
  - 使用 `chunk_metadata` 保存完整 Chunk 和引用行号。
  - 使用 `chunks_fts` 保存路径、标题、正文的词法索引。
  - 使用 SQLite `bm25()` 排序，并把 SQLite 的负分数转换为统一的非负分数。
  - 复用查询归一化、领域词扩展、覆盖率过滤、短语加分和未知标识符保护。
- `src/studymate/cli.py`
  - `chat` 和 `eval` 新增 `--search-backend memory|sqlite`。
  - 新增 `--search-db` 指定 SQLite 文件。
  - `/update` 后按照当前知识库重新切分并重建所选后端。

### 运行方式

~~~powershell
py -m studymate chat --knowledge .\knowledge --search-backend sqlite --search-db .\data\studymate-search.sqlite3
~~~

默认仍然是内存后端。SQLite 数据库文件只是索引缓存，不能替代知识库 Markdown/TXT 源文件。

### 当前边界

- SQLite FTS5/BM25 仍然是关键词检索，不会因为使用 SQLite 就获得语义理解。
- 不同后端的 `score` 数值不可直接比较，应使用评测集比较 Hit@K、Recall@K、Precision@K 和 MRR。
- 本轮按计划没有运行测试；后续统一补充 SQLite 后端测试和内存/SQLite 对比评测。
