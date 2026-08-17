from studymate.models import Chunk
from studymate.search import InMemorySearchIndex, SearchIndex, expand_query_terms


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


def test_search_normalizes_compound_camel_case_and_separator_variants():
    index = InMemorySearchIndex(
        [
            Chunk(
                id="chunk-runtime",
                document_id="doc-runtime",
                path="07-agent-sdk/agent-runtime.md",
                title="Agent Runtime",
                text="The agent runtime executes tools and controls the loop.",
                start_line=1,
                end_line=1,
            ),
            Chunk(
                id="chunk-other",
                document_id="doc-other",
                path="python.md",
                title="Python",
                text="Python is a programming language.",
                start_line=1,
                end_line=1,
            ),
        ]
    )

    for query in ("agentloop", "AgentLoop", "agent-loop"):
        results = index.search(query, top_k=1)
        assert results[0].chunk.path == "07-agent-sdk/agent-runtime.md"


def test_search_ignores_english_question_stopwords():
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
                id="chunk-other",
                document_id="doc-other",
                path="other.md",
                title="Other",
                text="This document explains unrelated concepts.",
                start_line=1,
                end_line=1,
            ),
        ]
    )

    results = index.search("What is RAG?", top_k=1)

    assert results[0].chunk.path == "rag.md"
    assert results[0].matched_terms == ["rag"]


def test_search_index_protocol_is_replaceable():
    class FakeSearchIndex:
        def search(self, query: str, top_k: int = 5):
            return []

    assert isinstance(FakeSearchIndex(), SearchIndex)


def test_search_deduplicates_chunk_ids():
    chunk = Chunk(
        id="duplicate",
        document_id="doc-1",
        path="rag.md",
        title="RAG",
        text="RAG retrieves relevant documents.",
        start_line=1,
        end_line=1,
    )
    index = InMemorySearchIndex([chunk, chunk])

    results = index.search("RAG", top_k=5)

    assert len(results) == 1


def test_search_prefers_topic_document_over_generic_api_reference_chunk():
    index = InMemorySearchIndex(
        [
            Chunk(
                id="chunk-reference",
                document_id="doc-reference",
                path="07-agent-sdk/python.md",
                title="Agent SDK reference - Python",
                text="session_store mirrors session transcripts so the SDK can persist and resume them.",
                start_line=1,
                end_line=1,
            ),
            Chunk(
                id="chunk-sessions",
                document_id="doc-sessions",
                path="07-agent-sdk/sessions.md",
                title="Work with sessions",
                text="Sessions persist agent conversation history and resume a prior run.",
                start_line=1,
                end_line=1,
            ),
        ]
    )

    results = index.search(
        "How does the Claude Agent SDK persist and resume sessions?", top_k=1
    )

    assert results[0].chunk.path == "07-agent-sdk/sessions.md"


def test_search_rejects_low_coverage_noise_for_unknown_identifier():
    index = InMemorySearchIndex(
        [
            Chunk(
                id="chunk-noise",
                document_id="doc-noise",
                path="skills.md",
                title="Skills",
                text="This item has no relationship to the requested identifier.",
                start_line=1,
                end_line=1,
            )
        ]
    )

    results = index.search("NO_SUCH_KNOWLEDGE_ITEM_7719", top_k=5)

    assert results == []


def test_search_allows_known_opaque_identifier():
    index = InMemorySearchIndex(
        [
            Chunk(
                id="chunk-version",
                document_id="doc-version",
                path="versions.md",
                title="Version notes",
                text="Feature flag AGENT_LOOP_123 is enabled.",
                start_line=1,
                end_line=1,
            )
        ]
    )

    results = index.search("AGENT_LOOP_123", top_k=5)

    assert results[0].chunk.path == "versions.md"
