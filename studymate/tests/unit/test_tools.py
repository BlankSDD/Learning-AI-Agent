from studymate.ingest import chunk_document, load_documents
from studymate.search import InMemorySearchIndex
from studymate.tools import KnowledgeTools, build_knowledge_tool_registry


def build_tools(tmp_path):
    knowledge_file = tmp_path / "rag.md"
    knowledge_file.write_text(
        "# RAG\n\nRAG retrieves evidence before generation.\n",
        encoding="utf-8",
    )
    documents = load_documents(tmp_path)
    chunks = [chunk for document in documents for chunk in chunk_document(document)]
    knowledge_tools = KnowledgeTools(tmp_path, InMemorySearchIndex(chunks))
    return knowledge_tools, build_knowledge_tool_registry(knowledge_tools), chunks


def test_search_knowledge_tool_returns_results_and_schemas(tmp_path):
    _, registry, chunks = build_tools(tmp_path)

    execution = registry.execute("search_knowledge", {"query": "RAG"})

    assert execution.is_error is False
    assert execution.evidence[0].chunk.id == chunks[0].id
    assert execution.payload["results"][0]["chunk"]["path"] == "rag.md"
    assert execution.payload["query"] == "RAG"
    assert execution.payload["rewritten_query"] == "rag"
    assert registry.schemas()[0]["function"]["name"] == "search_knowledge"


def test_open_document_tool_reads_requested_lines(tmp_path):
    _, registry, _ = build_tools(tmp_path)

    execution = registry.execute(
        "open_document",
        {"path": "rag.md", "start_line": 1, "end_line": 2},
    )

    assert execution.is_error is False
    assert execution.payload["path"] == "rag.md"
    assert "# RAG" in execution.payload["text"]
    assert execution.payload["chunk_id"] == execution.evidence[0].chunk.id
    assert execution.evidence[0].chunk.start_line == 1
    assert execution.evidence[0].chunk.end_line == 2


def test_open_document_tool_rejects_path_escape(tmp_path):
    _, registry, _ = build_tools(tmp_path)

    execution = registry.execute("open_document", {"path": "../outside.md"})

    assert execution.is_error is True
    assert "inside the knowledge directory" in execution.content


def test_registry_rejects_invalid_tool_arguments(tmp_path):
    _, registry, _ = build_tools(tmp_path)

    execution = registry.execute("search_knowledge", {"query": ""})

    assert execution.is_error is True
    assert "Invalid arguments" in execution.payload["error"]


def test_registry_returns_unknown_tool_as_tool_error(tmp_path):
    _, registry, _ = build_tools(tmp_path)

    execution = registry.execute("run_shell", {})

    assert execution.is_error is True
    assert "Unknown tool" in execution.payload["error"]
