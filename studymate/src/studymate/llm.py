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
        payload = self._normalize_citations(payload, evidence or [])
        return Answer.model_validate(payload)

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

    def _debug(self, message: str) -> None:
        if self.debug:
            print(f"[StudyMate debug] {message}", file=sys.stderr)
