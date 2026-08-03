from studymate.citations import validate_citations
from studymate.models import Answer, Citation, Chunk, SearchResult


def test_citations_must_reference_retrieved_chunks():
    retrieved = [
        SearchResult(
            chunk=Chunk(
                id="chunk-1",
                document_id="doc-1",
                path="rag.md",
                title="RAG",
                text="RAG retrieves documents.",
                start_line=1,
                end_line=1,
            ),
            score=0.9,
            matched_terms=["RAG"],
        )
    ]
    answer = Answer(
        answer="RAG retrieves documents.",
        citations=[
            Citation(
                chunk_id="chunk-1",
                path="rag.md",
                title="RAG",
                start_line=1,
                end_line=1,
                quote="RAG retrieves documents.",
            )
        ],
        confidence=0.8,
        need_more_context=False,
        next_steps=[],
    )

    assert validate_citations(answer, retrieved).is_valid is True


def test_fabricated_citation_is_rejected():
    answer = Answer(
        answer="没有依据的回答。",
        citations=[
            Citation(
                chunk_id="not-retrieved",
                path="missing.md",
                title="Missing",
                start_line=1,
                end_line=2,
                quote="不存在的内容。",
            )
        ],
        confidence=0.9,
        need_more_context=False,
        next_steps=[],
    )

    assert validate_citations(answer, []).is_valid is False

