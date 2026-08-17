from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Protocol, Sequence

from .llm import OpenAIAnswerer, describe_llm_error
from .models import Chunk, SearchResult
from .search import (
    _deduplicate_chunks,
    _has_unknown_opaque_identifier,
    expand_query_terms,
    tokenize,
)


class EmbeddingProvider(Protocol):
    """Provider contract for converting text into dense vectors."""

    cache_namespace: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        ...


class EmbeddingError(RuntimeError):
    """Raised when an embedding provider cannot return valid vectors."""


class OpenAICompatibleEmbeddingProvider:
    """Call an OpenAI-compatible ``/embeddings`` endpoint."""

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
            model = os.getenv("STUDYMATE_EMBEDDING_MODEL")
        if answerer is None and not model:
            raise EmbeddingError(
                "未配置 Embedding 模型，请在 .env 中设置 STUDYMATE_EMBEDDING_MODEL"
            )

        try:
            self.answerer = answerer or OpenAIAnswerer(
                model=model,
                api_key=os.getenv("STUDYMATE_EMBEDDING_API_KEY") or None,
                base_url=os.getenv("STUDYMATE_EMBEDDING_BASE_URL") or None,
            )
        except (RuntimeError, ValueError) as exc:
            raise EmbeddingError(str(exc)) from exc
        self.model = self.answerer.model
        self.cache_namespace = (
            f"openai-compatible:{self.answerer.base_url or 'default'}:{self.model}"
        )
        self._client: Any | None = None

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        values = list(texts)
        if not values:
            return []
        try:
            client = self._get_client()
            response = client.embeddings.create(model=self.model, input=values)
            data = getattr(response, "data", None)
            if data is None and isinstance(response, dict):
                data = response.get("data")
            if not isinstance(data, list) or len(data) != len(values):
                raise EmbeddingError(
                    f"Embedding API 返回数量异常：期望 {len(values)}，实际 {len(data or [])}"
                )

            indexed_vectors: list[tuple[int, list[float]]] = []
            for fallback_index, item in enumerate(data):
                if isinstance(item, dict):
                    raw_index = item.get("index", fallback_index)
                    raw_vector = item.get("embedding")
                else:
                    raw_index = getattr(item, "index", fallback_index)
                    raw_vector = getattr(item, "embedding", None)
                vector = _validate_vector(raw_vector)
                indexed_vectors.append((int(raw_index), vector))
            if {index for index, _ in indexed_vectors} != set(range(len(values))):
                raise EmbeddingError("Embedding API 返回的 index 无法与输入对应")
            indexed_vectors.sort(key=lambda item: item[0])
            vectors = [vector for _, vector in indexed_vectors]
            return vectors
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingError(
                f"Embedding API 调用失败：{describe_llm_error(exc)}"
            ) from exc

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise EmbeddingError(
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


class JsonEmbeddingCache:
    """Small local cache keyed by provider namespace and input text."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._entries: dict[str, list[float]] = {}
        if self.path.is_file():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            if isinstance(payload, dict):
                self._entries = {
                    str(key): vector
                    for key, vector in payload.items()
                    if isinstance(vector, list) and _is_numeric_vector(vector)
                }

    def get(self, namespace: str, text: str) -> list[float] | None:
        return self._entries.get(_cache_key(namespace, text))

    def put(self, namespace: str, text: str, vector: list[float]) -> None:
        self._entries[_cache_key(namespace, text)] = vector

    def flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._entries, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )


class EmbeddingSearchIndex:
    """Dense semantic search over the same Chunk -> SearchResult contract."""

    def __init__(
        self,
        chunks: list[Chunk],
        *,
        provider: EmbeddingProvider,
        cache_path: str | Path | None = None,
        min_score: float = 0.2,
        batch_size: int = 32,
        max_chunks: int | None = None,
    ):
        if min_score < 0 or min_score > 1:
            raise ValueError("min_score must be between 0 and 1")
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")
        if max_chunks is not None and max_chunks < 0:
            raise ValueError("max_chunks must be zero, positive, or None")
        unique_chunks = _deduplicate_chunks(chunks)
        self._chunks = unique_chunks[:max_chunks] if max_chunks else unique_chunks
        self.provider = provider
        self.min_score = min_score
        self.batch_size = batch_size
        self._cache = JsonEmbeddingCache(cache_path) if cache_path else None
        self._chunk_vectors: dict[str, list[float]] = {}
        self._query_vectors: dict[str, list[float]] = {}

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        if top_k <= 0 or not self._chunks:
            return []
        if _has_unknown_opaque_identifier(query, self._chunks):
            return []
        query_terms = expand_query_terms(query)
        if not query_terms:
            return []

        self._ensure_chunk_vectors()
        query_key = query.strip().casefold()
        query_vector = self._query_vectors.get(query_key)
        if query_vector is None:
            query_vector = self.provider.embed([query])[0]
            _validate_vector(query_vector)
            self._query_vectors[query_key] = query_vector

        results: list[SearchResult] = []
        for chunk in self._chunks:
            score = max(0.0, _cosine_similarity(query_vector, self._chunk_vectors[chunk.id]))
            if score < self.min_score:
                continue
            chunk_terms = set(tokenize(f"{chunk.title} {chunk.text}"))
            results.append(
                SearchResult(
                    chunk=chunk,
                    score=score,
                    matched_terms=sorted(query_terms & chunk_terms),
                )
            )
        results.sort(key=lambda item: (-item.score, item.chunk.path, item.chunk.start_line))
        return results[:top_k]

    def _ensure_chunk_vectors(self) -> None:
        missing: list[tuple[Chunk, str]] = []
        for chunk in self._chunks:
            text = _chunk_embedding_text(chunk)
            vector = self._cache.get(self.provider.cache_namespace, text) if self._cache else None
            if vector is None:
                missing.append((chunk, text))
            else:
                self._chunk_vectors[chunk.id] = vector

        cache_changed = False
        for start in range(0, len(missing), self.batch_size):
            batch = missing[start : start + self.batch_size]
            vectors = self.provider.embed([text for _, text in batch])
            if len(vectors) != len(batch):
                raise EmbeddingError("Embedding provider 返回的 Chunk 向量数量不匹配")
            for (chunk, text), vector in zip(batch, vectors):
                vector = _validate_vector(vector)
                self._chunk_vectors[chunk.id] = vector
                if self._cache:
                    self._cache.put(self.provider.cache_namespace, text, vector)
                    cache_changed = True
        if cache_changed and self._cache:
            self._cache.flush()


def _chunk_embedding_text(chunk: Chunk) -> str:
    return f"{chunk.title}\n{chunk.text}"


def _cache_key(namespace: str, text: str) -> str:
    return hashlib.sha256(f"{namespace}\0{text}".encode("utf-8")).hexdigest()


def _is_numeric_vector(vector: list[Any]) -> bool:
    return bool(vector) and all(isinstance(value, (int, float)) for value in vector)


def _validate_vector(vector: Any) -> list[float]:
    if not isinstance(vector, list) or not _is_numeric_vector(vector):
        raise EmbeddingError("Embedding API 返回了空向量或非数字向量")
    return [float(value) for value in vector]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise EmbeddingError(
            f"Embedding 向量维度不一致：query={len(left)}，chunk={len(right)}"
        )
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)
