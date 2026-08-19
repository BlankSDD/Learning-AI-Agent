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
    assert result.trace.stop_reason == "final_answer"
    assert result.trace.steps[0].requested_tools[0]["name"] == "search_knowledge"
    assert result.trace.steps[0].executions[0]["evidence_count"] == 1
    ranking = result.trace.steps[0].executions[0]["ranking"]
    assert ranking[0]["rank"] == 1
    assert ranking[0]["path"] == "rag.md"
    assert ranking[0]["score"] == result.retrieved[0].score
    assert model.calls[1]["messages"][-1]["role"] == "user"
    assert "Tool observations:" in model.calls[1]["messages"][-1]["content"]
    assert {tool["function"]["name"] for tool in model.calls[0]["tools"]} == {
        "search_knowledge",
        "open_document",
    }
    assert model.calls[1]["tools"] == []


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
    assert model.calls[2]["tools"] == []
    assert model.calls[2]["messages"][-1]["role"] == "user"


def test_agent_blocks_multiple_open_document_calls_in_one_response(tmp_path):
    search_call = ModelToolResponse(
        tool_calls=[
            ToolCallRequest(
                id="call-search",
                name="search_knowledge",
                arguments={"query": "RAG"},
            )
        ]
    )
    batch_open_call = ModelToolResponse(
        tool_calls=[
            ToolCallRequest(
                id="call-open-1",
                name="open_document",
                arguments={"path": "rag.md", "start_line": 1, "end_line": 2},
            ),
            ToolCallRequest(
                id="call-open-2",
                name="open_document",
                arguments={"path": "rag.md", "start_line": 1, "end_line": 3},
            ),
        ]
    )
    runner, model, chunks = build_runner(
        tmp_path,
        [search_call, batch_open_call, final_response("")],
    )
    model.responses[2] = final_response(chunks[0].id)

    result = runner.run(user_input="Explain RAG from the document")

    assert result.steps == 3
    assert result.tool_calls == [
        "search_knowledge",
        "open_document",
        "open_document",
    ]
    assert result.trace.steps[1].executions[0]["status"] == "ok"
    assert result.trace.steps[1].executions[1]["status"] == "error"
    assert "per-run call budget" in result.trace.steps[1].executions[1]["error"]


def test_agent_prompt_prefers_search_only_for_simple_definitions(tmp_path):
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

    runner.run(user_input="What is RAG?")

    system_prompt = runner.llm.calls[0]["messages"][0]["content"]
    assert "For a simple definition question" in system_prompt
    assert "Call open_document at most once per run" in system_prompt
    assert runner.llm.calls[1]["tools"] == []


def test_agent_finalization_removes_tool_messages(tmp_path):
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

    result = runner.run(user_input="Explain RAG")

    assert result.answer.answer.startswith("RAG retrieves")
    final_call = model.calls[2]
    assert final_call["tools"] == []
    assert all(message["role"] != "tool" for message in final_call["messages"])
    assert all("tool_calls" not in message for message in final_call["messages"])
    assert "Tool observations:" in final_call["messages"][-1]["content"]


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


def test_agent_stops_after_an_empty_knowledge_search(tmp_path):
    no_result_search = ModelToolResponse(
        tool_calls=[
            ToolCallRequest(
                id="call-search",
                name="search_knowledge",
                arguments={"query": "unmatched-agent-term"},
            )
        ]
    )
    runner, model, _ = build_runner(tmp_path, [no_result_search])

    result = runner.run(user_input="What is an unmatched agent term?")

    assert result.steps == 1
    assert result.tool_calls == ["search_knowledge"]
    assert result.retrieved == []
    assert result.answer.need_more_context is True
    assert "没有找到" in result.answer.answer
    assert len(model.calls) == 1


def test_agent_blocks_repeated_tool_request_but_keeps_other_tools_available(tmp_path):
    search_call = ModelToolResponse(
        tool_calls=[
            ToolCallRequest(
                id="call-search",
                name="search_knowledge",
                arguments={"query": "RAG"},
            )
        ]
    )
    repeated_search = ModelToolResponse(
        tool_calls=[
            ToolCallRequest(
                id="call-search-again",
                name="search_knowledge",
                arguments={"query": "RAG"},
            )
        ]
    )
    runner, model, chunks = build_runner(
        tmp_path,
        [search_call, repeated_search, final_response("")],
    )
    model.responses[2] = final_response(chunks[0].id)

    result = runner.run(user_input="Explain RAG")

    assert result.answer.answer.startswith("RAG retrieves")
    assert result.steps == 3
    assert [tool["function"]["name"] for tool in model.calls[2]["tools"]] == [
        "open_document"
    ]
    blocked = result.trace.steps[1].executions[0]
    assert blocked["status"] == "error"
    assert "per-run call budget" in blocked["error"]


def test_agent_recovers_by_opening_document_after_repeated_search(tmp_path):
    search_call = ModelToolResponse(
        tool_calls=[
            ToolCallRequest(
                id="call-search",
                name="search_knowledge",
                arguments={"query": "RAG"},
            )
        ]
    )
    repeated_search = ModelToolResponse(
        tool_calls=[
            ToolCallRequest(
                id="call-search-again",
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
        [search_call, repeated_search, open_call, final_response("")],
    )
    runner.max_steps = 4
    model.responses[3] = final_response(chunks[0].id)

    result = runner.run(user_input="Explain RAG from the document")

    assert result.answer.answer.startswith("RAG retrieves")
    assert result.tool_calls == [
        "search_knowledge",
        "search_knowledge",
        "open_document",
    ]
    assert result.steps == 4
    assert result.trace.steps[1].executions[0]["status"] == "error"
    assert result.trace.steps[2].executions[0]["name"] == "open_document"


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
