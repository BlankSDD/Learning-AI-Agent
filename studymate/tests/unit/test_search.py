from pathlib import Path

import pytest

from studymate.models import Chunk
from studymate.search import (
    InMemorySearchIndex,
    SearchIndex,
    SQLiteIndexError,
    SQLiteFTS5SearchIndex,
    build_sqlite_search_database,
    expand_query_terms,
    rewrite_query,
    split_comparison_query,
)


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


def test_compound_terms_require_all_expanded_terms_in_each_backend():
    chunks = [
        Chunk(
            id="chunk-partial",
            document_id="doc-partial",
            path="agent-overview.md",
            title="Agent overview",
            text="An agent can call tools.",
            start_line=1,
            end_line=1,
        ),
        Chunk(
            id="chunk-full",
            document_id="doc-full",
            path="07-agent-sdk/agent-runtime.md",
            title="Agent Runtime",
            text="The agent runtime executes tools and manages state.",
            start_line=1,
            end_line=1,
        ),
    ]

    memory_index = InMemorySearchIndex(chunks)
    sqlite_index = SQLiteFTS5SearchIndex(chunks)
    try:
        for index in (memory_index, sqlite_index):
            results = index.search("agentruntime", top_k=5)

            assert [result.chunk.path for result in results] == [
                "07-agent-sdk/agent-runtime.md"
            ]
            assert results[0].matched_terms == ["agent", "runtime"]
    finally:
        sqlite_index.close()


def test_expand_query_terms_removes_common_chinese_markers():
    terms = expand_query_terms("什么是自定义工具？")

    assert "是" not in terms
    assert {"custom", "tool", "tools"}.issubset(terms)


def test_search_expands_mcp_to_its_full_protocol_name():
    chunks = [
        Chunk(
            id="chunk-definition",
            document_id="doc-definition",
            path="mcp-introduction.md",
            title="MCP introduction",
            text="The Model Context Protocol (MCP) connects AI applications to tools.",
            start_line=1,
            end_line=1,
        ),
        Chunk(
            id="chunk-configuration",
            document_id="doc-configuration",
            path="mcp-configuration.md",
            title="MCP configuration",
            text="Configure an MCP server with a command and authentication settings.",
            start_line=1,
            end_line=1,
        ),
    ]

    memory_index = InMemorySearchIndex(chunks)
    sqlite_index = SQLiteFTS5SearchIndex(chunks)
    try:
        assert {"mcp", "model", "context", "protocol"}.issubset(
            expand_query_terms("MCP 是什么？")
        )
        assert memory_index.search("MCP 是什么？", top_k=1)[0].chunk.path == (
            "mcp-introduction.md"
        )
        assert sqlite_index.search("MCP 是什么？", top_k=1)[0].chunk.path == (
            "mcp-introduction.md"
        )
    finally:
        sqlite_index.close()


def test_search_prioritizes_exact_mcp_anchor_over_expanded_terms():
    chunks = [
        Chunk(
            id="chunk-gateway",
            document_id="doc-gateway",
            path="99-other/llm-gateway-protocol.md",
            title="Gateway protocol reference",
            text="Model context and protocol settings for the gateway.",
            start_line=1,
            end_line=1,
        ),
        Chunk(
            id="chunk-glossary",
            document_id="doc-glossary",
            path="99-other/glossary.md",
            title="Glossary",
            text="MCP (Model Context Protocol) connects AI tools to external services.",
            start_line=1,
            end_line=1,
        ),
    ]

    memory_index = InMemorySearchIndex(chunks)
    sqlite_index = SQLiteFTS5SearchIndex(chunks)
    try:
        assert memory_index.search("MCP 是什么？", top_k=1)[0].chunk.path == (
            "99-other/glossary.md"
        )
        assert sqlite_index.search("MCP 是什么？", top_k=1)[0].chunk.path == (
            "99-other/glossary.md"
        )
    finally:
        sqlite_index.close()


def test_split_comparison_query_returns_two_topic_queries():
    assert split_comparison_query("agentloop 和 agent runtime 有什么区别？") == (
        "agent loop",
        "agent runtime",
    )

    assert split_comparison_query(
        "What is the difference between tool calling and MCP?"
    ) == ("tool calling", "mcp")


def test_comparison_search_covers_both_topics_in_each_backend():
    chunks = [
        Chunk(
            id="chunk-loop",
            document_id="doc-loop",
            path="07-agent-sdk/agent-loop.md",
            title="Agent Loop",
            text="The agent loop evaluates tool calls and observations.",
            start_line=1,
            end_line=1,
        ),
        Chunk(
            id="chunk-runtime",
            document_id="doc-runtime",
            path="07-agent-sdk/agent-runtime.md",
            title="Agent Runtime",
            text="The agent runtime executes tools and manages state.",
            start_line=1,
            end_line=1,
        ),
        Chunk(
            id="chunk-decoy",
            document_id="doc-decoy",
            path="07-agent-sdk/typescript.md",
            title="Agent SDK TypeScript",
            text="The runtime backs the self-paced loop command.",
            start_line=1,
            end_line=1,
        ),
    ]

    memory_index = InMemorySearchIndex(chunks)
    sqlite_index = SQLiteFTS5SearchIndex(chunks)
    try:
        for index in (memory_index, sqlite_index):
            paths = {result.chunk.path for result in index.search(
                "agentloop 和 agent runtime 有什么区别？", top_k=2
            )}
            assert paths == {
                "07-agent-sdk/agent-loop.md",
                "07-agent-sdk/agent-runtime.md",
            }
    finally:
        sqlite_index.close()


def test_search_normalizes_compound_camel_case_and_separator_variants():
    index = InMemorySearchIndex(
        [
            Chunk(
                id="chunk-loop",
                document_id="doc-loop",
                path="07-agent-sdk/agent-loop.md",
                title="Agent Loop",
                text="The agent loop evaluates tools and observations.",
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
        assert results[0].chunk.path == "07-agent-sdk/agent-loop.md"


def test_rewrite_query_keeps_agent_loop_and_removes_task_instructions():
    query = (
        "Agent Loop \u5982\u4f55\u8fd0\u884c\u6d41\u7a0b\u3001\u6b65\u9aa4\u3001"
        "\u72b6\u6001\u5faa\u73af\u548c\u539f\u6587\u8bf4\u660e"
    )

    assert rewrite_query(query) == "agent loop"


def test_rewrite_query_removes_english_question_words_without_partial_matches():
    assert rewrite_query("How does RAG retrieve documents?") == "rag retrieve"


def test_rewrite_query_keeps_chinese_topic_terms():
    assert rewrite_query("Tool Calling 和 MCP 有什么区别？") == "tool calling mcp 区别"


def test_search_rewrite_prefers_topic_document_over_instruction_noise():
    index = InMemorySearchIndex(
        [
            Chunk(
                id="chunk-loop",
                document_id="doc-loop",
                path="07-agent-sdk/agent-loop.md",
                title="Agent Loop",
                text="The agent loop executes tools and processes observations.",
                start_line=1,
                end_line=1,
            ),
            Chunk(
                id="chunk-tool",
                document_id="doc-tool",
                path="tool-calling-vs-mcp.md",
                title="Tool Calling and MCP",
                text="Tools and MCP connect an agent to external capabilities.",
                start_line=1,
                end_line=1,
            ),
        ]
    )

    results = index.search(
        "Agent Loop \u5982\u4f55\u8fd0\u884c\u6d41\u7a0b\u3001\u6b65\u9aa4\u3001"
        "\u72b6\u6001\u5faa\u73af\u548c\u539f\u6587\u8bf4\u660e",
        top_k=1,
    )

    assert results[0].chunk.path == "07-agent-sdk/agent-loop.md"


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


def test_sqlite_index_can_be_built_then_reopened_without_chunks(tmp_path):
    database_path = tmp_path / "studymate-search.sqlite3"
    chunks = [
        Chunk(
            id="chunk-rag",
            document_id="doc-rag",
            path="rag.md",
            title="RAG",
            text="RAG retrieves evidence before generation.",
            start_line=1,
            end_line=1,
        )
    ]

    metadata = build_sqlite_search_database(chunks, database_path)
    modified_at = database_path.stat().st_mtime_ns
    index = SQLiteFTS5SearchIndex.open(database_path)
    try:
        results = index.search("What is RAG?", top_k=1)

        assert results[0].chunk.path == "rag.md"
        assert metadata["document_count"] == "1"
        assert metadata["chunk_count"] == "1"
        assert index.metadata["chunk_count"] == "1"
        assert database_path.stat().st_mtime_ns == modified_at
    finally:
        index.close()


def test_open_sqlite_index_requires_prebuilt_database(tmp_path):
    database_path = tmp_path / "missing.sqlite3"

    with pytest.raises(SQLiteIndexError, match="build-index"):
        SQLiteFTS5SearchIndex.open(database_path)


def test_open_sqlite_index_rejects_legacy_database(tmp_path):
    database_path = tmp_path / "legacy.sqlite3"
    database_path.touch()

    with pytest.raises(SQLiteIndexError, match="build-index"):
        SQLiteFTS5SearchIndex.open(database_path)


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
