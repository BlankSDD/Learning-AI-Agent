from __future__ import annotations

import json
import os
import re
import sys
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .models import Answer, SearchResult


class LLMRequestError(RuntimeError):
    """Raised when the configured model service cannot answer a request."""


def describe_llm_error(error: Exception) -> str:
    status_code = getattr(error, "status_code", None)
    details = str(error)
    if status_code == 402 or "Insufficient Balance" in details:
        return (
            "DeepSeek API 余额不足（HTTP 402）。"
            "请在 DeepSeek 开放平台充值，或更换一个有余额的 API Key。"
        )
    if status_code == 403 and "blocked" in details.lower():
        return (
            "模型网关拒绝了当前请求（HTTP 403，可能是 Cloudflare/WAF 客户端指纹拦截）。"
            "请检查 STUDYMATE_USER_AGENT、代理和网关访问策略。"
        )
    if status_code in {401, 403}:
        return (
            f"模型 API 鉴权失败（HTTP {status_code}）。"
            "请检查 STUDYMATE_API_KEY 或 OPENAI_API_KEY 是否填写正确，"
            "并确认该 Key 属于当前 provider。"
        )
    if status_code == 429:
        return "模型 API 请求过于频繁（HTTP 429），请稍后重试。"
    if status_code:
        return f"模型 API 调用失败（HTTP {status_code}）：{details}"
    return f"模型 API 调用失败：{details}"


def _env_value(*names: str) -> str | None:
    value, _ = _env_value_with_source(*names)
    return value


def _env_value_with_source(*names: str) -> tuple[str | None, str | None]:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip(), name
    return None, None


def _safe_error_details(error: Exception) -> str:
    body = getattr(error, "body", None)
    if body is not None:
        try:
            details = json.dumps(body, ensure_ascii=False)
        except TypeError:
            details = str(body)
    else:
        details = str(error)
    details = re.sub(
        r"(?i)(api[_-]?key|authorization|token|secret)\s*[:=]\s*[^,}\s]+",
        r"\1=<redacted>",
        details,
    )
    return details[:600]


def _content_text(content: Any) -> str | None:
    if isinstance(content, str):
        return content or None
    if not isinstance(content, list):
        return None

    text_parts: list[str] = []
    for block in content:
        if isinstance(block, dict):
            block_type = block.get("type")
            value = block.get("text")
            if block_type in {"text", "output_text"} and isinstance(value, str):
                text_parts.append(value)
        else:
            block_type = getattr(block, "type", None)
            value = getattr(block, "text", None)
            if block_type in {"text", "output_text"} and isinstance(value, str):
                text_parts.append(value)
    return "".join(text_parts) or None


def _content_tool_calls(content: Any) -> list[dict[str, Any]]:
    if not isinstance(content, list):
        return []

    calls: list[dict[str, Any]] = []
    for index, block in enumerate(content):
        if isinstance(block, dict):
            block_type = block.get("type")
            name = block.get("name")
            arguments = block.get("input", block.get("arguments"))
            call_id = block.get("id") or f"content-tool-call-{index}"
            function = block.get("function")
            if isinstance(function, dict):
                name = name or function.get("name")
                arguments = arguments or function.get("arguments")
        else:
            block_type = getattr(block, "type", None)
            name = getattr(block, "name", None)
            arguments = getattr(block, "input", None)
            if arguments is None:
                arguments = getattr(block, "arguments", None)
            call_id = getattr(block, "id", None) or f"content-tool-call-{index}"

        if block_type in {"tool_use", "function_call", "tool-call"} and name:
            calls.append(
                {
                    "id": call_id,
                    "name": name,
                    "arguments": arguments or {},
                }
            )
    return calls


def _response_shape(message: Any, choice: Any) -> str:
    content = getattr(message, "content", None)
    tool_calls = getattr(message, "tool_calls", None) or []
    reasoning = getattr(message, "reasoning_content", None)
    refusal = getattr(message, "refusal", None)
    if isinstance(content, str):
        content_shape = f"str:{len(content)}"
    elif isinstance(content, list):
        content_shape = f"list:{len(content)}"
    elif content is None:
        content_shape = "none"
    else:
        content_shape = type(content).__name__
    reasoning_shape = (
        f"{type(reasoning).__name__}:{len(reasoning)}"
        if isinstance(reasoning, str)
        else ("none" if reasoning is None else type(reasoning).__name__)
    )
    fields: list[str] = []
    model_dump = getattr(message, "model_dump", None)
    if callable(model_dump):
        try:
            fields = sorted(model_dump().keys())
        except Exception:
            fields = []
    return (
        f"finish_reason={getattr(choice, 'finish_reason', None)} "
        f"content={content_shape} tool_calls={len(tool_calls)} "
        f"content_tool_calls={len(_content_tool_calls(content))} "
        f"reasoning={reasoning_shape} refusal={'yes' if refusal else 'no'} "
        f"message_fields={','.join(fields) or '(unknown)'}"
    )


def _debug_content_preview(content: str | None, limit: int = 1_200) -> str:
    if not content:
        return "(empty)"
    compact = " ".join(content.split())
    if len(compact) > limit:
        return f"{compact[:limit]}..."
    return compact


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env_value(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _load_extra_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    raw = _env_value("STUDYMATE_EXTRA_HEADERS_JSON")
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("STUDYMATE_EXTRA_HEADERS_JSON 不是有效 JSON") from exc
        if not isinstance(parsed, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in parsed.items()
        ):
            raise ValueError("STUDYMATE_EXTRA_HEADERS_JSON 必须是字符串键值对象")
        headers.update(parsed)

    referer = _env_value("STUDYMATE_HTTP_REFERER")
    title = _env_value("STUDYMATE_X_TITLE")
    if referer:
        headers["HTTP-Referer"] = referer
    if title:
        headers["X-Title"] = title
    return headers


def _normalize_base_url(
    base_url: str | None,
    *,
    provider: str,
    endpoint_type: str,
) -> str | None:
    if not base_url:
        return None
    normalized = base_url.rstrip("/")
    if provider.lower() == "newapi" and endpoint_type.lower() == "openai":
        parts = urlsplit(normalized)
        if parts.path in {"", "/"}:
            normalized = urlunsplit(
                (parts.scheme, parts.netloc, "/v1", parts.query, parts.fragment)
            )
    return normalized


class LLMResponseParser:
    def parse(
        self,
        payload: dict[str, Any] | str,
        *,
        evidence: list[SearchResult] | None = None,
    ) -> Answer:
        if isinstance(payload, str):
            text = payload.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
                text = re.sub(r"\s*```$", "", text)
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                start = text.find("{")
                end = text.rfind("}")
                if start < 0 or end <= start:
                    raise
                payload = json.loads(text[start : end + 1])
        payload = self._normalize_confidence(payload)
        payload = self._normalize_next_steps(payload)
        payload = self._normalize_citations(payload, evidence or [])
        return Answer.model_validate(payload)

    @staticmethod
    def _normalize_confidence(payload: dict[str, Any]) -> dict[str, Any]:
        """Accept common provider confidence labels while keeping Answer numeric."""
        confidence = payload.get("confidence")
        if not isinstance(confidence, str):
            return payload

        normalized = confidence.strip().lower()
        levels = {
            "very high": 0.95,
            "high": 0.85,
            "medium": 0.6,
            "moderate": 0.6,
            "low": 0.3,
            "very low": 0.1,
            "高": 0.85,
            "较高": 0.75,
            "中": 0.6,
            "中等": 0.6,
            "低": 0.3,
            "较低": 0.2,
        }
        if normalized in levels:
            return {**payload, "confidence": levels[normalized]}

        if normalized.endswith("%"):
            try:
                percentage = float(normalized[:-1].strip())
            except ValueError:
                return payload
            if 0 <= percentage <= 100:
                return {**payload, "confidence": percentage / 100}
        return payload

    @staticmethod
    def _normalize_next_steps(payload: dict[str, Any]) -> dict[str, Any]:
        """Accept a single suggested next step from compatible model gateways."""
        next_steps = payload.get("next_steps")
        if isinstance(next_steps, str):
            return {**payload, "next_steps": [next_steps]}
        return payload

    @staticmethod
    def _normalize_citations(
        payload: dict[str, Any],
        evidence: list[SearchResult],
    ) -> dict[str, Any]:
        raw_citations = payload.get("citations")
        if not isinstance(raw_citations, list):
            return payload

        chunks = {result.chunk.id: result.chunk for result in evidence}
        citations: list[Any] = []
        for raw_citation in raw_citations:
            if isinstance(raw_citation, str):
                chunk = chunks.get(raw_citation)
                if chunk is None:
                    citations.append(raw_citation)
                    continue
                citations.append(
                    {
                        "chunk_id": chunk.id,
                        "path": chunk.path,
                        "title": chunk.title,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "quote": chunk.text,
                    }
                )
                continue

            if isinstance(raw_citation, dict):
                citation = dict(raw_citation)
                chunk = chunks.get(citation.get("chunk_id"))
                if chunk is not None:
                    citation.setdefault("path", chunk.path)
                    citation.setdefault("title", chunk.title)
                    citation.setdefault("start_line", chunk.start_line)
                    citation.setdefault("end_line", chunk.end_line)
                    citation.setdefault("quote", chunk.text)
                citations.append(citation)
                continue

            citations.append(raw_citation)

        return {**payload, "citations": citations}


def build_prompt(
    *,
    user_input: str,
    evidence: list[SearchResult],
    history: list[dict[str, str]],
) -> list[dict[str, str]]:
    context = "\n\n".join(
        (
            f"[{result.chunk.id}] {result.chunk.path}:"
            f"{result.chunk.start_line}-{result.chunk.end_line}\n"
            f"{result.chunk.text}"
        )
        for result in evidence
    )
    history_text = "\n".join(
        f"{message['role']}: {message['content']}" for message in history[-6:]
    )
    system = (
        "You are StudyMate, a learning knowledge assistant. "
        "Answer only from the supplied evidence. "
        "If evidence is insufficient, set need_more_context to true. "
        "Return JSON with answer, citations, confidence, "
        "need_more_context, and next_steps. "
        "confidence must be a decimal number from 0 to 1, not a text label. "
        "Each citation must be an object with chunk_id, path, title, "
        "start_line, end_line, and quote. Use only supplied chunk_id values. "
        "Do not return citation IDs as bare strings."
    )
    user = (
        f"Conversation history:\n{history_text or '(none)'}\n\n"
        f"Evidence:\n{context or '(no evidence)'}\n\n"
        f"User input:\n{user_input}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


class OpenAIAnswerer:
    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        try:
            from dotenv import load_dotenv
        except ImportError:
            load_dotenv = None
        if load_dotenv:
            load_dotenv()

        self.provider_type = _env_value("STUDYMATE_TYPE") or "openai_compatible"
        self.provider = _env_value("STUDYMATE_PROVIDER") or "openai"
        self.endpoint_type = _env_value("STUDYMATE_ENDPOINT_TYPE") or "openai"
        self.model = model or _env_value("STUDYMATE_MODEL", "OPENAI_MODEL")
        if api_key:
            self.api_key = api_key
            self.api_key_source = "constructor"
        else:
            self.api_key, self.api_key_source = _env_value_with_source(
                "STUDYMATE_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"
            )
        configured_base_url = base_url or _env_value(
            "STUDYMATE_BASE_URL", "OPENAI_BASE_URL"
        )
        self.base_url = _normalize_base_url(
            configured_base_url,
            provider=self.provider,
            endpoint_type=self.endpoint_type,
        )
        self.debug = (_env_value("STUDYMATE_DEBUG") or "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.stream = _env_bool(
            "STUDYMATE_STREAM",
            default=self.provider.lower() == "newapi",
        )
        self.extra_headers = _load_extra_headers()
        # Huazi's Cloudflare layer blocks the Python SDK's default user agent.
        # Keep this configurable while using an AI SDK-style value by default.
        self.user_agent = _env_value("STUDYMATE_USER_AGENT") or "ai-sdk/openai-compatible/2.0.37"
        self.response_format = (
            _env_value("STUDYMATE_RESPONSE_FORMAT")
            or ("none" if self.provider.lower() == "newapi" else "json_object")
        ).lower()
        raw_max_tokens = _env_value("STUDYMATE_MAX_TOKENS") or "4096"
        try:
            self.max_tokens = int(raw_max_tokens)
        except ValueError as exc:
            raise ValueError("STUDYMATE_MAX_TOKENS 必须是正整数") from exc
        if self.max_tokens <= 0:
            raise ValueError("STUDYMATE_MAX_TOKENS 必须是正整数")
        if self.provider_type.lower() != "openai_compatible":
            raise ValueError(
                "当前只支持 STUDYMATE_TYPE=openai_compatible 的模型服务"
            )
        if self.endpoint_type.lower() != "openai":
            raise ValueError(
                "当前只支持 STUDYMATE_ENDPOINT_TYPE=openai 的接口"
            )
        if self.response_format not in {"json_object", "none"}:
            raise ValueError(
                "STUDYMATE_RESPONSE_FORMAT 只能是 json_object 或 none"
            )
        if not self.model:
            raise ValueError("Set STUDYMATE_MODEL or OPENAI_MODEL before starting chat")
        if not self.api_key:
            raise ValueError(
                "Set STUDYMATE_API_KEY or OPENAI_API_KEY before starting chat"
            )

    def answer(
        self,
        *,
        user_input: str,
        evidence: list[SearchResult],
        history: list[dict[str, str]],
    ) -> Answer:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The openai package is not installed. Install the project dependencies first."
            ) from exc

        client_kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        request_headers = dict(self.extra_headers)
        if self.user_agent:
            request_headers["User-Agent"] = self.user_agent
        if request_headers:
            client_kwargs["default_headers"] = request_headers
        endpoint = (
            f"{self.base_url.rstrip('/')}/chat/completions"
            if self.base_url
            else "/chat/completions"
        )
        self._debug(
            "request="
            f"{endpoint} provider={self.provider} "
            f"endpoint_type={self.endpoint_type} model={self.model} "
            f"key_source={self.api_key_source} "
            f"key_length={len(self.api_key or '')} "
            f"evidence_count={len(evidence)} history_count={len(history)} "
            f"response_format={self.response_format} stream={self.stream} "
            f"user_agent={self.user_agent or '(none)'} "
            f"extra_headers={','.join(sorted(request_headers)) or '(none)'}"
        )
        try:
            client = OpenAI(**client_kwargs)
            request_kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": build_prompt(
                    user_input=user_input,
                    evidence=evidence,
                    history=history,
                ),
                "temperature": 0.2,
                "stream": self.stream,
            }
            if self.response_format == "json_object":
                request_kwargs["response_format"] = {"type": "json_object"}
            response = client.chat.completions.create(**request_kwargs)
        except Exception as exc:
            self._debug(
                f"response_error type={type(exc).__name__} "
                f"status={getattr(exc, 'status_code', None)} "
                f"details={_safe_error_details(exc)}"
            )
            endpoint = self.base_url or "默认 OpenAI 接口"
            message = describe_llm_error(exc)
            raise LLMRequestError(
                f"{message} 当前配置：provider={self.provider}，"
                f"base_url={endpoint}，model={self.model}。"
            ) from exc
        if self.stream:
            content = "".join(
                chunk.choices[0].delta.content or ""
                for chunk in response
                if chunk.choices
            )
        else:
            content = response.choices[0].message.content or ""
        content = content or "{}"
        try:
            return LLMResponseParser().parse(content, evidence=evidence)
        except Exception as exc:
            self._debug(
                f"response_parse_error type={type(exc).__name__} "
                f"details={_safe_error_details(exc)}"
            )
            raise LLMRequestError(
                "模型返回内容无法解析为 StudyMate 所需的结构化回答，"
                "请重试或检查模型是否支持 JSON 输出。"
            ) from exc

    def chat_with_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ):
        """Make one native Tool Calling request for the StudyMate Agent."""
        from .agent import ModelToolResponse, ToolCallRequest

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The openai package is not installed. Install the project dependencies first."
            ) from exc

        client_kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        request_headers = dict(self.extra_headers)
        if self.user_agent:
            request_headers["User-Agent"] = self.user_agent
        if request_headers:
            client_kwargs["default_headers"] = request_headers
        endpoint = (
            f"{self.base_url.rstrip('/')}/chat/completions"
            if self.base_url
            else "/chat/completions"
        )
        self._debug(
            f"agent_request={endpoint} provider={self.provider} model={self.model} "
            f"message_count={len(messages)} tool_count={len(tools)} "
            f"stream={str(self.stream).lower()} max_tokens={self.max_tokens}"
        )
        try:
            client = OpenAI(**client_kwargs)
            request_kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": self.max_tokens,
                "stream": self.stream,
            }
            if tools:
                request_kwargs["tools"] = tools
                request_kwargs["tool_choice"] = "auto"
            response = client.chat.completions.create(**request_kwargs)
            if self.stream:
                return self._parse_streaming_tool_response(response)

            choice = response.choices[0]
            message = choice.message
            raw_content = getattr(message, "content", None)
            fallback_content_calls = _content_tool_calls(raw_content)
            self._debug(f"agent_response_shape {_response_shape(message, choice)}")
            tool_calls: list[ToolCallRequest] = []
            standard_tool_calls = getattr(message, "tool_calls", None) or []
            if standard_tool_calls:
                parsed_tool_calls = [
                    {
                        "id": call.id or f"tool-call-{index}",
                        "name": call.function.name,
                        "arguments": call.function.arguments or "{}",
                    }
                    for index, call in enumerate(standard_tool_calls)
                ]
            else:
                parsed_tool_calls = fallback_content_calls

            for call in parsed_tool_calls:
                raw_arguments = call["arguments"]
                if isinstance(raw_arguments, str):
                    try:
                        arguments: dict[str, Any] | str = json.loads(raw_arguments)
                    except json.JSONDecodeError:
                        arguments = raw_arguments
                else:
                    arguments = raw_arguments
                tool_calls.append(
                    ToolCallRequest(
                        id=call["id"],
                        name=call["name"],
                        arguments=arguments,
                    )
                )
            return ModelToolResponse(
                content=_content_text(raw_content),
                tool_calls=tool_calls,
            )
        except Exception as exc:
            self._debug(
                f"agent_response_error type={type(exc).__name__} "
                f"status={getattr(exc, 'status_code', None)} "
                f"details={_safe_error_details(exc)}"
            )
            endpoint = self.base_url or "默认 OpenAI 接口"
            message = describe_llm_error(exc)
            raise LLMRequestError(
                f"{message} 当前配置：provider={self.provider}，"
                f"base_url={endpoint}，model={self.model}。"
            ) from exc

    def _parse_streaming_tool_response(self, response: Any):
        from .agent import ModelToolResponse, ToolCallRequest

        content_parts: list[str] = []
        partial_calls: dict[int | str, dict[str, str]] = {}
        finish_reason: str | None = None

        for chunk in response:
            for choice in getattr(chunk, "choices", None) or []:
                if getattr(choice, "finish_reason", None):
                    finish_reason = choice.finish_reason
                delta = getattr(choice, "delta", None)
                if delta is None:
                    continue

                text = getattr(delta, "content", None)
                if isinstance(text, str):
                    content_parts.append(text)

                for raw_call in getattr(delta, "tool_calls", None) or []:
                    call_index = getattr(raw_call, "index", None)
                    if call_index is None:
                        call_index = getattr(raw_call, "id", None) or len(partial_calls)
                    state = partial_calls.setdefault(
                        call_index,
                        {"id": "", "name": "", "arguments": ""},
                    )
                    call_id = getattr(raw_call, "id", None)
                    if isinstance(call_id, str) and call_id:
                        state["id"] = call_id
                    function = getattr(raw_call, "function", None)
                    name = getattr(function, "name", None)
                    if isinstance(name, str):
                        state["name"] += name
                    arguments = getattr(function, "arguments", None)
                    if isinstance(arguments, str):
                        state["arguments"] += arguments

        tool_calls = [
            ToolCallRequest(
                id=state["id"] or f"stream-tool-call-{index}",
                name=state["name"],
                arguments=state["arguments"] or {},
            )
            for index, state in partial_calls.items()
            if state["name"]
        ]
        content = "".join(content_parts) or None
        self._debug(
            "agent_stream_response "
            f"finish_reason={finish_reason} content_length={len(content or '')} "
            f"tool_calls={len(tool_calls)} "
            f"content_preview={_debug_content_preview(content)!r}"
        )
        return ModelToolResponse(content=content, tool_calls=tool_calls)

    def _debug(self, message: str) -> None:
        if self.debug:
            print(f"[StudyMate debug] {message}", file=sys.stderr)
