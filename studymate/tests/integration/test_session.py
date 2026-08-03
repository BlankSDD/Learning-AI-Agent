from studymate.chat import ChatService


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


class FakeSearchIndex:
    def search(self, query: str, top_k: int = 5):
        return []


class FakeLLM:
    def answer(self, *, user_input, evidence, history):
        raise AssertionError("reset command must not call the LLM")
