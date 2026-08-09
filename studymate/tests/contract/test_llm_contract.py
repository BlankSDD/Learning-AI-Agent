import pytest
from pydantic import ValidationError
from types import SimpleNamespace

from studymate.llm import LLMResponseParser, OpenAIAnswerer, describe_llm_error
from studymate.models import Chunk, SearchResult


def test_llm_response_parser_accepts_required_fields():
    parser = LLMResponseParser()

    result = parser.parse(
        {
            "answer": "RAG retrieves evidence before generation.",
            "citations": [],
            "confidence": 0.8,
            "need_more_context": False,
            "next_steps": [],
        }
    )

    assert result.answer.startswith("RAG")


def test_llm_response_parser_rejects_invalid_shape():
    parser = LLMResponseParser()

    with pytest.raises(ValidationError):
        parser.parse({"answer": 123})


def test_generic_provider_config_normalizes_newapi_base_url(monkeypatch):
    monkeypatch.setenv("STUDYMATE_TYPE", "openai_compatible")
    monkeypatch.setenv("STUDYMATE_PROVIDER", "newapi")
    monkeypatch.setenv("STUDYMATE_ENDPOINT_TYPE", "openai")
    monkeypatch.setenv("STUDYMATE_BASE_URL", "https://example.test")
    monkeypatch.setenv("STUDYMATE_MODEL", "claude-sonnet-4-5-20250929")

    answerer = OpenAIAnswerer(api_key="test-key")

    assert answerer.base_url == "https://example.test/v1"
    assert answerer.model == "claude-sonnet-4-5-20250929"


def test_newapi_config_uses_stream_and_compatible_headers(monkeypatch):
    monkeypatch.setenv("STUDYMATE_TYPE", "openai_compatible")
    monkeypatch.setenv("STUDYMATE_PROVIDER", "newapi")
    monkeypatch.setenv("STUDYMATE_ENDPOINT_TYPE", "openai")
    monkeypatch.setenv("STUDYMATE_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("STUDYMATE_MODEL", "claude-sonnet-4-5-20250929")
    monkeypatch.setenv("STUDYMATE_STREAM", "true")
    monkeypatch.setenv("STUDYMATE_HTTP_REFERER", "https://cherry-ai.com")
    monkeypatch.setenv("STUDYMATE_X_TITLE", "Cherry Studio")
    monkeypatch.setenv("STUDYMATE_USER_AGENT", "ai-sdk/openai-compatible/2.0.37")

    answerer = OpenAIAnswerer(api_key="test-key")

    assert answerer.stream is True
    assert answerer.extra_headers == {
        "HTTP-Referer": "https://cherry-ai.com",
        "X-Title": "Cherry Studio",
    }
    assert answerer.user_agent == "ai-sdk/openai-compatible/2.0.37"


def test_user_agent_has_a_safe_default_for_cloudflare_gateways(monkeypatch):
    monkeypatch.setenv("STUDYMATE_PROVIDER", "newapi")
    monkeypatch.setenv("STUDYMATE_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("STUDYMATE_MODEL", "claude-sonnet-4-5-20250929")
    monkeypatch.delenv("STUDYMATE_USER_AGENT", raising=False)

    answerer = OpenAIAnswerer(api_key="test-key")

    assert answerer.user_agent == "ai-sdk/openai-compatible/2.0.37"


def test_blocked_403_is_reported_as_gateway_blocking():
    class BlockedError(Exception):
        status_code = 403

        def __str__(self):
            return "Error code: 403 - Your request was blocked."

    message = describe_llm_error(BlockedError())

    assert "Cloudflare/WAF" in message


def test_llm_response_parser_accepts_json_code_fence():
    parser = LLMResponseParser()

    result = parser.parse(
        """```json
        {"answer":"ok","citations":[],"confidence":0.5,"need_more_context":false,"next_steps":[]}
        ```"""
    )

    assert result.answer == "ok"


def test_llm_response_parser_normalizes_provider_confidence_label():
    parser = LLMResponseParser()

    result = parser.parse(
        {
            "answer": "No evidence was found.",
            "citations": [],
            "confidence": "high",
            "need_more_context": True,
            "next_steps": [],
        }
    )

    assert result.confidence == 0.85


def test_llm_response_parser_normalizes_single_next_step():
    parser = LLMResponseParser()

    result = parser.parse(
        {
            "answer": "The term needs more context.",
            "citations": [],
            "confidence": 0.5,
            "need_more_context": True,
            "next_steps": "Add a document about this term.",
        }
    )

    assert result.next_steps == ["Add a document about this term."]


def test_llm_response_parser_expands_retrieved_chunk_id_citations():
    evidence = [
        SearchResult(
            chunk=Chunk(
                id="chunk-1",
                document_id="doc-1",
                path="rag.md",
                title="RAG",
                text="RAG retrieves evidence before generation.",
                start_line=3,
                end_line=4,
            ),
            score=1.0,
        )
    ]

    result = LLMResponseParser().parse(
        {
            "answer": "RAG retrieves evidence.",
            "citations": ["chunk-1"],
            "confidence": 0.8,
            "need_more_context": False,
            "next_steps": [],
        },
        evidence=evidence,
    )

    assert result.citations[0].path == "rag.md"
    assert result.citations[0].start_line == 3


def test_agent_model_adapter_sends_native_tool_call_request(monkeypatch):
    monkeypatch.setenv("STUDYMATE_PROVIDER", "newapi")
    monkeypatch.setenv("STUDYMATE_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("STUDYMATE_MODEL", "claude-sonnet-4-5-20250929")
    monkeypatch.setenv("STUDYMATE_STREAM", "false")
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    id="call-1",
                                    function=SimpleNamespace(
                                        name="search_knowledge",
                                        arguments='{"query":"RAG"}',
                                    ),
                                )
                            ],
                        )
                    )
                ]
            )

    class FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(
        "openai.OpenAI",
        lambda **kwargs: FakeClient(),
    )
    answerer = OpenAIAnswerer(api_key="test-key")

    response = answerer.chat_with_tools(
        messages=[{"role": "user", "content": "What is RAG?"}],
        tools=[{"type": "function", "function": {"name": "search_knowledge"}}],
    )

    assert response.tool_calls[0].name == "search_knowledge"
    assert response.tool_calls[0].arguments == {"query": "RAG"}
    assert captured["stream"] is False
    assert captured["max_tokens"] == 4096
    assert captured["tools"][0]["function"]["name"] == "search_knowledge"
    assert "response_format" not in captured


def test_agent_model_adapter_aggregates_streamed_tool_call(monkeypatch):
    monkeypatch.setenv("STUDYMATE_PROVIDER", "newapi")
    monkeypatch.setenv("STUDYMATE_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("STUDYMATE_MODEL", "claude-sonnet-4-5-20250929")
    monkeypatch.setenv("STUDYMATE_STREAM", "true")

    class FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["stream"] is True
            return iter(
                [
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                finish_reason=None,
                                delta=SimpleNamespace(
                                    content=None,
                                    tool_calls=[
                                        SimpleNamespace(
                                            index=0,
                                            id="call-1",
                                            function=SimpleNamespace(
                                                name="search_",
                                                arguments='{"query":"',
                                            ),
                                        )
                                    ],
                                ),
                            )
                        ]
                    ),
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                finish_reason="tool_calls",
                                delta=SimpleNamespace(
                                    content=None,
                                    tool_calls=[
                                        SimpleNamespace(
                                            index=0,
                                            id=None,
                                            function=SimpleNamespace(
                                                name="knowledge",
                                                arguments='RAG"}',
                                            ),
                                        )
                                    ],
                                ),
                            )
                        ]
                    ),
                ]
            )

    class FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: FakeClient())
    answerer = OpenAIAnswerer(api_key="test-key")

    response = answerer.chat_with_tools(
        messages=[{"role": "user", "content": "What is RAG?"}],
        tools=[{"type": "function", "function": {"name": "search_knowledge"}}],
    )

    assert response.content is None
    assert response.tool_calls[0].id == "call-1"
    assert response.tool_calls[0].name == "search_knowledge"
    assert response.tool_calls[0].arguments == '{"query":"RAG"}'


def test_agent_model_adapter_omits_tools_after_tool_budget_is_exhausted(monkeypatch):
    monkeypatch.setenv("STUDYMATE_PROVIDER", "newapi")
    monkeypatch.setenv("STUDYMATE_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("STUDYMATE_MODEL", "claude-sonnet-4-5-20250929")
    monkeypatch.setenv("STUDYMATE_STREAM", "false")
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="{}", tool_calls=[]))]
            )

    class FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: FakeClient())
    answerer = OpenAIAnswerer(api_key="test-key")

    answerer.chat_with_tools(
        messages=[{"role": "user", "content": "Finish the answer."}],
        tools=[],
    )

    assert "tools" not in captured
    assert "tool_choice" not in captured
