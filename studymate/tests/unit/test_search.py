from studymate.models import Chunk
from studymate.search import InMemorySearchIndex


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

