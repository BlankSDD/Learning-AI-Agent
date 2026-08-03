# StudyMate 评估方案

## 1. 评估集格式

评估集使用 JSONL，每行一个问题：

~~~json
{
  "id": "q001",
  "input": "RAG 和微调有什么区别？",
  "intent": "question",
  "expected_sources": ["rag.md"],
  "required_terms": ["检索", "微调"]
}
~~~

## 2. 第一版指标

| 指标 | 定义 |
|---|---|
| Retrieval Hit Rate | Top-K 是否包含期望来源 |
| Citation Accuracy | 引用是否真实存在且支持回答 |
| Answer Correctness | 人工或规则判断回答是否正确 |
| Abstention Rate | 无证据问题是否正确拒答 |
| Tool Success Rate | 工具调用是否成功 |
| Latency | 从输入到输出的耗时 |
| Token Cost | 单次回答的 Token 成本 |

## 3. 基线

先记录三个版本：

1. 直接把问题发送给模型，不检索。
2. 固定关键词检索后回答。
3. 加入 Tool Calling 和会话上下文。

比较：

- 正确率。
- 引用正确率。
- 延迟。
- Token 成本。
- 拒答表现。

## 4. 评估原则

- 不只记录成功案例。
- 失败样本必须保存。
- 每次修改 Prompt、切分、检索策略后重新评估。
- 真实模型评估和单元测试分开。

