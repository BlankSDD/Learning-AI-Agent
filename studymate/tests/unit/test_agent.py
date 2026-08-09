import json

from studymate.agent import AgentRunner, ModelToolResponse, ToolCallRequest
from studymate.chat import ChatService
from studymate.ingest import chunk_document, load_documents
from studymate.search import InMemorySearchIndex
from studymate.tools import KnowledgeTools, build_knowledge_tool_registry


class FakeAgentModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat_with_tools(self, *, messages, tools):
        self.calls.append({"messages": messages, "tools": tools})
        return self.responses.pop(0)


def build_runner(tmp_path, responses):
    knowledge_file = tmp_path / "rag.md"
    knowledge_file.write_text(
        "# RAG\n\nRAG retrieves evidence before generation.\n",
        encoding="utf-8",
    )
    documents = load_documents(tmp_path)
    chunks = [chunk for document in documents for chunk in chunk_document(document)]
    knowledge_tools = KnowledgeTools(tmp_path, InMemorySearchIndex(chunks))
    model = FakeAgentModel(responses)
    runner = AgentRunner(
        llm=model,
        tool_registry=build_knowledge_tool_registry(knowledge_tools),
        max_steps=3,
    )
    return runner, model, chunks


def final_response(chunk_id: str):
    return ModelToolResponse(
        content=json.dumps(
            {
                "answer": "RAG retrieves evidence before generation.",
                "citations": [chunk_id],
                "confidence": 0.9,
                "need_more_context": False,
                "next_steps": ["Continue learning retrieval evaluation"],
            }
        )
    )


def test_agent_calls_search_then_returns_grounded_answer(tmp_path):
    search_call = ModelToolResponse(
        tool_calls=[
            ToolCallRequest(
                id="call-search",
                name="search_knowledge",
                arguments={"query": "RAG"},
            )
        ]
    )
    runner, model, chunks = build_runner(tmp_path, [search_call, final_response("")])
    model.responses[1] = final_response(chunks[0].id)

    result = runner.run(user_input="What is RAG?")

    assert result.answer.answer.startswith("RAG retrieves")
    assert result.answer.citations[0].chunk_id == chunks[0].id
    assert result.retrieved[0].chunk.id == chunks[0].id
    assert result.steps == 2
    assert model.calls[1]["messages"][-1]["role"] == "tool"


def test_agent_can_call_open_document_after_search(tmp_path):
    search_call = ModelToolResponse(
        tool_calls=[
            ToolCallRequest(
                id="call-search",
                name="search_knowledge",
                arguments={"query": "RAG"},
            )
        ]
    )
    open_call = ModelToolResponse(
        tool_calls=[
            ToolCallRequest(
                id="call-open",
                name="open_document",
                arguments={"path": "rag.md", "start_line": 1, "end_line": 3},
            )
        ]
    )
    runner, model, chunks = build_runner(
        tmp_path,
        [search_call, open_call, final_response("")],
    )
    model.responses[2] = final_response(chunks[0].id)

    result = runner.run(user_input="Explain RAG in detail")

    assert result.steps == 3
    assert result.tool_calls == ["search_knowledge", "open_document"]
    assert model.calls[2]["messages"][-1]["role"] == "tool"


def test_agent_stops_after_max_steps(tmp_path):
    repeated_call = ModelToolResponse(
        tool_calls=[
            ToolCallRequest(
                id="call-search",
                name="search_knowledge",
                arguments={"query": "RAG"},
            )
        ]
    )
    runner, _, _ = build_runner(tmp_path, [repeated_call, repeated_call, repeated_call])

    result = runner.run(user_input="Keep searching")

    assert result.steps == 3
    assert result.answer.confidence == 0.0
    assert "超过限制" in result.answer.answer


def test_agent_can_recover_from_unknown_tool(tmp_path):
    unknown_call = ModelToolResponse(
        tool_calls=[
            ToolCallRequest(
                id="call-unknown",
                name="run_shell",
                arguments={},
            )
        ]
    )
    runner, model, _ = build_runner(
        tmp_path,
        [unknown_call, ModelToolResponse(content=json.dumps({
            "answer": "The requested tool is unavailable.",
            "citations": [],
            "confidence": 0.2,
            "need_more_context": True,
            "next_steps": [],
        }))],
    )

    result = runner.run(user_input="Run a shell command")

    assert result.answer.need_more_context is True
    assert model.calls[1]["messages"][-1]["content"].find("Unknown tool") >= 0


def test_chat_service_uses_injected_agent_runner(tmp_path):
    search_call = ModelToolResponse(
        tool_calls=[
            ToolCallRequest(
                id="call-search",
                name="search_knowledge",
                arguments={"query": "RAG"},
            )
        ]
    )
    runner, _, chunks = build_runner(tmp_path, [search_call, final_response("")])
    runner.llm.responses[1] = final_response(chunks[0].id)
    service = ChatService(
        search_index=InMemorySearchIndex([]),
        llm=runner.llm,
        agent=runner,
    )

    response = service.handle("What is RAG?")

    assert response.answer.answer.startswith("RAG retrieves")
    assert response.retrieved[0].chunk.id == chunks[0].id
    assert len(response.history) == 2
