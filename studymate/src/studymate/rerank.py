from __future__ import annotations

import json
import os
import re
from typing import Any, Protocol

from .llm import OpenAIAnswerer, describe_llm_error
from .models import SearchResult
from .search import SearchIndex


class Reranker(Protocol):
    """Contract for reranking an already-retrieved candidate list."""

    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int = 5,
    ) -> list[SearchResult]:
        ...


class RerankerError(RuntimeError):
    """Raised when a reranker cannot produce a valid ranking."""


class RerankingSearchIndex:
    """SearchIndex decorator that adds a second-stage reranking step."""

    def __init__(
        self,
        base_index: SearchIndex,
        reranker: Reranker,
        *,
        candidate_k: int = 20,
        strict: bool = False,
    ):
        if candidate_k <= 0:
            raise ValueError("candidate_k must be greater than zero")
        self.base_index = base_index
        self.reranker = reranker
        self.candidate_k = candidate_k
        self.strict = strict

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        if top_k <= 0:
            return []
        candidates = self.base_index.search(query, top_k=max(top_k, self.candidate_k))
        if not candidates:
            return []
        try:
            return self.reranker.rerank(query, candidates, top_k=top_k)
        except Exception:
            if self.strict:
                raise
            # Retrieval should remain usable if an optional reranker service
            # is unavailable. The base ranking is a safe fallback.
            return candidates[:top_k]

    def close(self) -> None:
        close = getattr(self.base_index, "close", None)
        if close is not None:
            close()


class LLMReranker:
    """Use an OpenAI-compatible chat model as a second-stage relevance judge."""

    def __init__(
        self,
        *,
        model: str | None = None,
        answerer: OpenAIAnswerer | None = None,
    ):
        try:
            from dotenv import load_dotenv
        except ImportError:
            load_dotenv = None
        if load_dotenv:
            load_dotenv()
        if model is None:
            model = os.getenv("STUDYMATE_RERANK_MODEL") or None
        try:
            self.answerer = answerer or OpenAIAnswerer(
                model=model,
                api_key=os.getenv("STUDYMATE_RERANK_API_KEY") or None,
                base_url=os.getenv("STUDYMATE_RERANK_BASE_URL") or None,
            )
        except (RuntimeError, ValueError) as exc:
            raise RerankerError(str(exc)) from exc
        self.model = self.answerer.model
        self._client: Any | None = None

    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int = 5,
    ) -> list[SearchResult]:
        if top_k <= 0 or not results:
            return []
        candidates = results[:20]
        prompt_candidates = "\n\n".join(
            f"<candidate index=\"{index}\" path=\"{result.chunk.path}\" "
            f"lines=\"{result.chunk.start_line}-{result.chunk.end_line}\">\n"
            f"{result.chunk.text}\n</candidate>"
            for index, result in enumerate(candidates)
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a retrieval reranker. Judge how directly each candidate "
                    "answers the user query. Return JSON only in this shape: "
                    "{\"scores\":[{\"index\":0,\"score\":0.0}]} . "
                    "Include every candidate exactly once. Score from 0 to 1. "
                    "Do not answer the question and do not invent facts."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"<query>{query}</query>\n"
                    f"<candidates>\n{prompt_candidates}\n</candidates>"
                ),
            },
        ]
        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": min(self.answerer.max_tokens, 2048),
            "stream": False,
        }
        if self.answerer.response_format == "json_object":
            request_kwargs["response_format"] = {"type": "json_object"}
        try:
            response = self._get_client().chat.completions.create(**request_kwargs)
            content = response.choices[0].message.content or ""
            scores = _parse_scores(content, len(candidates))
        except RerankerError:
            raise
        except Exception as exc:
            raise RerankerError(
                f"Reranker API 调用失败：{describe_llm_error(exc)}"
            ) from exc

        reranked: list[SearchResult] = []
        for index, result in enumerate(candidates):
            reranked.append(
                result.model_copy(update={"score": scores[index]})
            )
        reranked.sort(
            key=lambda item: (-item.score, item.chunk.path, item.chunk.start_line)
        )
        return reranked[:top_k]

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RerankerError(
                "The openai package is not installed. Install the project dependencies first."
            ) from exc

        client_kwargs: dict[str, Any] = {"api_key": self.answerer.api_key}
        if self.answerer.base_url:
            client_kwargs["base_url"] = self.answerer.base_url
        request_headers = dict(self.answerer.extra_headers)
        if self.answerer.user_agent:
            request_headers["User-Agent"] = self.answerer.user_agent
        if request_headers:
            client_kwargs["default_headers"] = request_headers
        self._client = OpenAI(**client_kwargs)
        return self._client


def build_reranker(name: str, *, model: str | None = None) -> Reranker | None:
    normalized = name.casefold()
    if normalized == "none":
        return None
    if normalized == "llm":
        return LLMReranker(model=model)
    raise ValueError(f"Unsupported reranker: {name}. Choose 'none' or 'llm'.")


def _parse_scores(content: str, candidate_count: int) -> dict[int, float]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise RerankerError("Reranker 返回内容不是有效 JSON")
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise RerankerError("Reranker 返回内容不是有效 JSON") from exc

    raw_scores = payload.get("scores") if isinstance(payload, dict) else payload
    if not isinstance(raw_scores, list):
        raise RerankerError("Reranker JSON 缺少 scores 数组")
    scores: dict[int, float] = {}
    for item in raw_scores:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item["index"])
            score = float(item["score"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= index < candidate_count:
            scores[index] = min(1.0, max(0.0, score))
    if set(scores) != set(range(candidate_count)):
        raise RerankerError("Reranker 没有为每个候选结果返回有效分数")
    return scores
