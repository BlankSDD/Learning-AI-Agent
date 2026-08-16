from studymate.models import Chunk
from studymate.search import InMemorySearchIndex, expand_query_terms


def test_search_ranks_relevant_chunks_first():
    index = InMemorySearchIndex(
        [
            Chunk(
                id="chunk-rag",
                document_id="doc-rag",
                path="rag.md",
                title="RAG",
                text="RAG retrieves relevant documents before generation.",
                start_line=1,
                end_line=1,
            ),
            Chunk(
                id="chunk-python",
                document_id="doc-python",
                path="python.md",
                title="Python",
                text="Python is a general-purpose programming language.",
                start_line=1,
                end_line=1,
            ),
        ]
    )

    results = index.search("How does RAG retrieve documents?", top_k=1)

    assert len(results) == 1
    assert results[0].chunk.path == "rag.md"
    assert results[0].score > 0


def test_search_returns_empty_for_unknown_topic():
    index = InMemorySearchIndex([])

    assert index.search("unknown topic", top_k=3) == []


def test_search_expands_chinese_tool_terms_for_english_documents():
    index = InMemorySearchIndex(
        [
            Chunk(
                id="chunk-index",
                document_id="doc-index",
                path="documentation-index.md",
                title="Documentation Index",
                text="Claude Code documentation links.",
                start_line=1,
                end_line=1,
            ),
            Chunk(
                id="chunk-tools",
                document_id="doc-tools",
                path="07-agent-sdk/custom-tools.md",
                title="Give Claude custom tools",
                text="Define custom tools with a name, schema, and handler.",
                start_line=1,
                end_line=1,
            ),
        ]
    )

    results = index.search("Claude Code 中如何定义自定义工具？", top_k=1)

    assert results[0].chunk.path == "07-agent-sdk/custom-tools.md"
    assert {"custom", "tools"}.issubset(set(results[0].matched_terms))


def test_search_prioritizes_coverage_and_path_for_agent_concepts():
    index = InMemorySearchIndex(
        [
            Chunk(
                id="chunk-session",
                document_id="doc-session",
                path="session-storage.md",
                title="Agent session storage",
                text="An agent session stores messages.",
                start_line=1,
                end_line=1,
            ),
            Chunk(
                id="chunk-loop",
                document_id="doc-loop",
                path="07-agent-sdk/agent-loop.md",
                title="How the agent loop works",
                text="The agent loop evaluates tool calls and results.",
                start_line=1,
                end_line=1,
            ),
        ]
    )

    results = index.search("Agent Loop", top_k=1)

    assert results[0].chunk.path == "07-agent-sdk/agent-loop.md"


def test_expand_query_terms_removes_common_chinese_markers():
    terms = expand_query_terms("什么是自定义工具？")

    assert "是" not in terms
    assert {"custom", "tool", "tools"}.issubset(terms)
