from studymate.ingest import chunk_document, load_documents
from studymate.models import Document


def test_load_documents_only_reads_supported_files(tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "rag.md").write_text("# RAG\nRAG uses retrieval.", encoding="utf-8")
    (knowledge_dir / "notes.txt").write_text("Tool calling uses a schema.", encoding="utf-8")
    (knowledge_dir / "ignore.png").write_bytes(b"not a text document")

    documents = load_documents(knowledge_dir)

    assert [document.path for document in documents] == ["notes.txt", "rag.md"]


def test_chunk_document_keeps_source_location():
    document = Document(
        id="doc-1",
        path="rag.md",
        title="RAG",
        content_hash="hash-1",
        text="# RAG\n\nRAG uses retrieval.\n\nRAG can cite sources.",
    )

    chunks = chunk_document(document, max_chars=40, overlap=0)

    assert chunks
    assert all(chunk.path == "rag.md" for chunk in chunks)
    assert all(chunk.start_line >= 1 for chunk in chunks)
    assert all(chunk.end_line >= chunk.start_line for chunk in chunks)

