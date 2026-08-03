from studymate.chat import ChatService
from studymate.llm import LLMRequestError
from studymate.models import Answer, Citation, Chunk, SearchResult


class FakeSearchIndex:
    def search(self, query: str, top_k: int = 5):
        return [
            SearchResult(
                chunk=Chunk(
                    id="chunk-1",
                    document_id="doc-1",
                    path="rag.md",
                    title="RAG",
                    text="RAG retrieves documents before generation.",
                    start_line=1,
                    end_line=1,
                ),
                score=0.95,
                matched_terms=["RAG"],
            )
        ]


class FakeLLM:
    def answer(self, *, user_input, evidence, history):
        return Answer(
            answer="RAG retrieves documents before generation.",
            citations=[
                Citation(
                    chunk_id="chunk-1",
                    path="rag.md",
                    title="RAG",
                    start_line=1,
                    end_line=1,
                    quote="RAG retrieves documents before generation.",
                )
            ],
            confidence=0.9,
            need_more_context=False,
            next_steps=["继续学习 Embedding"],
        )


def test_question_workflow_retrieves_answers_and_saves_history():
    service = ChatService(search_index=FakeSearchIndex(), llm=FakeLLM())

    response = service.handle("什么是 RAG？")

    assert response.answer.answer.startswith("RAG")
    assert response.answer.citations[0].path == "rag.md"
    assert len(response.history) == 2


def test_no_evidence_workflow_returns_insufficient_context():
    class EmptySearch:
        def search(self, query: str, top_k: int = 5):
            return []

    service = ChatService(search_index=EmptySearch(), llm=FakeLLM())

    response = service.handle("资料中没有出现的概念")

    assert response.answer.need_more_context is True


def test_model_request_error_is_returned_without_crashing_session():
    class FailingLLM:
        def answer(self, *, user_input, evidence, history):
            raise LLMRequestError(
                "DeepSeek API 余额不足（HTTP 402）。请充值或更换 API Key。"
            )

    service = ChatService(search_index=FakeSearchIndex(), llm=FailingLLM())

    response = service.handle("什么是 MCP？")

    assert "余额不足" in response.answer.answer
    assert response.answer.confidence == 0.0
