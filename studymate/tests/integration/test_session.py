import json

from studymate.agent import AgentResult
from studymate.chat import ChatService
from studymate.models import Answer
from studymate.trace import AgentTrace, TraceStore


def test_reset_removes_previous_session_history():
    service = ChatService(search_index=FakeSearchIndex(), llm=FakeLLM())

    service.handle("什么是 RAG？")
    result = service.handle("/reset")

    assert result.history == []


def test_update_command_calls_configured_handler():
    calls = []
    service = ChatService(
        search_index=FakeSearchIndex(),
        llm=FakeLLM(),
        update_handler=lambda args: calls.append(args) or "updated",
    )

    result = service.handle("/update codex")

    assert calls == [["codex"]]
    assert result.answer.answer == "updated"


def test_agent_turn_is_persisted_and_trace_command_shows_last_run(tmp_path):
    trace = AgentTrace()
    trace.finish("final_answer")
    store = TraceStore(tmp_path, session_id="session-test")
    service = ChatService(
        search_index=FakeSearchIndex(),
        llm=FakeLLM(),
        agent=FakeAgent(trace),
        trace_store=store,
    )

    service.handle("什么是 RAG？")
    trace_response = service.handle("/trace")

    persisted = json.loads(store.path.read_text(encoding="utf-8").strip())
    assert persisted["user_input"] == "什么是 RAG？"
    assert persisted["answer"]["answer"] == "RAG retrieves evidence."
    assert "停止原因：final_answer" in trace_response.answer.answer


def test_output_command_saves_last_answer_and_trace(tmp_path):
    trace = AgentTrace()
    trace.finish("final_answer")
    service = ChatService(
        search_index=FakeSearchIndex(),
        llm=FakeLLM(),
        agent=FakeAgent(trace),
        output_dir=tmp_path / "outputs",
    )

    service.handle("什么是 RAG？")
    response = service.handle("/output")

    output_path = tmp_path / "outputs" / "latest.json"
    record = json.loads(output_path.read_text(encoding="utf-8"))
    assert "问答输出已保存" in response.answer.answer
    assert record["user_input"] == "什么是 RAG？"
    assert record["answer"]["answer"] == "RAG retrieves evidence."
    assert record["trace"]["stop_reason"] == "final_answer"


class FakeSearchIndex:
    def search(self, query: str, top_k: int = 5):
        return []


class FakeLLM:
    def answer(self, *, user_input, evidence, history):
        raise AssertionError("reset command must not call the LLM")


class FakeAgent:
    def __init__(self, trace):
        self.trace = trace

    def run(self, *, user_input, history):
        return AgentResult(
            answer=Answer(
                answer="RAG retrieves evidence.",
                citations=[],
                confidence=0.9,
                need_more_context=False,
                next_steps=[],
            ),
            trace=self.trace,
        )
