from __future__ import annotations

import math
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Protocol, runtime_checkable

from .models import Chunk, SearchResult

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")
CAMEL_CASE_PATTERN = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
OPAQUE_IDENTIFIER_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b")

# Normalize common compact forms before tokenization. This keeps queries such
# as "agentloop" compatible with documents that use "agent loop".
COMPOUND_ALIASES = {
    "agentloop": "agent loop",
    "agentruntime": "agent runtime",
    "toolcalling": "tool calling",
    "knowledgebase": "knowledge base",
    "claudecode": "claude code",
    "opencode": "open code",
}

# The downloaded documentation is mostly English while user questions can be
# Chinese. Keep the expansion small and domain-oriented so it improves recall
# without turning every query into a broad synonym search.
QUERY_ALIASES = {
    "自定义工具": ("custom", "tool", "tools"),
    "自定义": ("custom",),
    "工具调用": ("tool", "calling", "function"),
    "工具": ("tool", "tools"),
    "定义": ("define", "defined", "definition"),
    "循环": ("loop",),
    "运行时": ("runtime",),
    "追踪": ("trace", "traces"),
    "可观测性": ("observability",),
    "检索": ("retrieval", "search"),
    "知识库": ("knowledge", "base"),
    "关系": ("relationship", "related"),
}

QUERY_STOPWORDS = {
    "的",
    "是",
    "中",
    "和",
    "有",
    "什么",
    "如何",
    "怎么",
    "a",
    "an",
    "and",
    "are",
    "about",
    "between",
    "can",
    "does",
    "for",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "the",
    "to",
    "what",
    "which",
    "with",
}

MIN_QUERY_COVERAGE = 0.5


@runtime_checkable
class SearchIndex(Protocol):
    """Search contract used by ChatService and knowledge tools."""

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        ...


def normalize_text(text: str) -> str:
    """Normalize separators, CamelCase, and common compact domain terms."""
    normalized = CAMEL_CASE_PATTERN.sub(" ", text).casefold()
    for compact, expanded in COMPOUND_ALIASES.items():
        normalized = re.sub(
            rf"(?<![a-z0-9]){re.escape(compact)}(?![a-z0-9])",
            expanded,
            normalized,
        )
    return normalized


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(normalize_text(text))


class InMemorySearchIndex:
    """Dependency-free BM25-style index for local Markdown/TXT chunks."""

    _K1 = 1.2
    _B = 0.75

    def __init__(self, chunks: list[Chunk]):
        # Chunk IDs should be stable. De-duplicate defensively so a caller
        # cannot receive the same evidence more than once.
        self._chunks = _deduplicate_chunks(chunks)

        self._tokenized = {
            chunk.id: Counter(tokenize(f"{chunk.title} {chunk.text}"))
            for chunk in self._chunks
        }
        self._title_tokens = {
            chunk.id: Counter(tokenize(chunk.title)) for chunk in self._chunks
        }
        self._path_tokens = {
            chunk.id: Counter(tokenize(chunk.path)) for chunk in self._chunks
        }
        self._filename_tokens = {
            chunk.id: Counter(tokenize(chunk.path.rsplit("/", 1)[-1]))
            for chunk in self._chunks
        }
        self._document_frequency: Counter[str] = Counter()
        for term_counts in self._tokenized.values():
            self._document_frequency.update(term_counts.keys())
        total_length = sum(sum(counts.values()) for counts in self._tokenized.values())
        self._average_document_length = (
            total_length / len(self._chunks) if self._chunks else 1.0
        )

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        if top_k <= 0:
            return []

        query_terms = expand_query_terms(query)
        if not query_terms:
            return []
        if _has_unknown_opaque_identifier(query, self._chunks):
            return []

        phrase_terms = _query_phrases(query)
        results: list[SearchResult] = []
        for chunk in self._chunks:
            chunk_id = chunk.id
            term_counts = self._tokenized[chunk_id]
            matched_terms = sorted(term for term in query_terms if term in term_counts)
            if not matched_terms:
                continue

            content_score = sum(
                self._bm25_score(term, term_counts) for term in matched_terms
            )
            coverage = len(matched_terms) / len(query_terms)
            if coverage < MIN_QUERY_COVERAGE:
                continue
            title_score = sum(
                self._inverse_document_frequency(term)
                for term in matched_terms
                if self._title_tokens[chunk_id][term]
            )
            path_score = sum(
                self._inverse_document_frequency(term)
                for term in matched_terms
                if self._path_tokens[chunk_id][term]
            )
            filename_score = sum(
                self._inverse_document_frequency(term)
                for term in matched_terms
                if self._filename_tokens[chunk_id][term]
            )
            phrase_hits = sum(
                _contains_token_phrase(tokenize(f"{chunk.title} {chunk.text}"), phrase)
                for phrase in phrase_terms
            )
            phrase_hits += sum(
                _contains_token_phrase(tokenize(chunk.path), phrase)
                for phrase in phrase_terms
            )
            score = (
                content_score
                + (coverage * 0.5)
                + (title_score * 1.75)
                + (path_score * 5.0)
                + (filename_score * 4.0)
                + (phrase_hits * 1.25)
            )
            results.append(
                SearchResult(
                    chunk=chunk,
                    score=score,
                    matched_terms=matched_terms,
                )
            )

        results.sort(key=lambda item: (-item.score, item.chunk.path, item.chunk.start_line))
        return results[:top_k]

    def _bm25_score(self, term: str, term_counts: Counter[str]) -> float:
        inverse_document_frequency = self._inverse_document_frequency(term)
        term_frequency = term_counts[term]
        document_length = sum(term_counts.values())
        length_normalization = 1 - self._B + (
            self._B * document_length / self._average_document_length
        )
        normalized_frequency = (term_frequency * (self._K1 + 1)) / (
            term_frequency + self._K1 * length_normalization
        )
        return inverse_document_frequency * normalized_frequency

    def _inverse_document_frequency(self, term: str) -> float:
        document_count = len(self._chunks)
        document_frequency = self._document_frequency[term]
        return math.log(
            1 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5)
        )


class SQLiteFTS5SearchIndex:
    """SQLite FTS5 index using SQLite's built-in BM25 ranking function.

    The index is rebuilt from the supplied chunks when constructed. This keeps
    the persistent database deterministic after a knowledge-base update while
    still allowing SQLite to handle matching and ranking efficiently.
    """

    _BM25_WEIGHTS = (0.0, 5.0, 1.75, 1.0)

    def __init__(
        self,
        chunks: list[Chunk],
        database_path: str | Path | None = None,
    ):
        self.database_path = Path(database_path) if database_path is not None else None
        if self.database_path is not None:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)

        connection_target = str(self.database_path) if self.database_path else ":memory:"
        self._connection = sqlite3.connect(connection_target)
        self._connection.row_factory = sqlite3.Row
        self._chunks = _deduplicate_chunks(chunks)
        self._content_tokens = {
            chunk.id: set(tokenize(f"{chunk.title} {chunk.text}"))
            for chunk in self._chunks
        }
        self._path_tokens = {
            chunk.id: set(tokenize(chunk.path)) for chunk in self._chunks
        }
        self._tokenized_content = {
            chunk.id: tokenize(f"{chunk.title} {chunk.text}") for chunk in self._chunks
        }
        self._tokenized_paths = {
            chunk.id: tokenize(chunk.path) for chunk in self._chunks
        }
        self._rebuild()

    def _rebuild(self) -> None:
        try:
            with self._connection:
                self._connection.executescript(
                    """
                    DROP TABLE IF EXISTS chunks_fts;
                    DROP TABLE IF EXISTS chunk_metadata;

                    CREATE TABLE chunk_metadata (
                        chunk_id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL,
                        path TEXT NOT NULL,
                        title TEXT NOT NULL,
                        text TEXT NOT NULL,
                        start_line INTEGER NOT NULL,
                        end_line INTEGER NOT NULL
                    );

                    CREATE VIRTUAL TABLE chunks_fts USING fts5(
                        chunk_id UNINDEXED,
                        path,
                        title,
                        text,
                        tokenize='unicode61'
                    );
                    """
                )
                self._connection.executemany(
                    """
                    INSERT INTO chunk_metadata
                        (chunk_id, document_id, path, title, text, start_line, end_line)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            chunk.id,
                            chunk.document_id,
                            chunk.path,
                            chunk.title,
                            chunk.text,
                            chunk.start_line,
                            chunk.end_line,
                        )
                        for chunk in self._chunks
                    ],
                )
                self._connection.executemany(
                    "INSERT INTO chunks_fts (chunk_id, path, title, text) VALUES (?, ?, ?, ?)",
                    [
                        (
                            chunk.id,
                            _fts_text(chunk.path),
                            _fts_text(chunk.title),
                            _fts_text(chunk.text),
                        )
                        for chunk in self._chunks
                    ],
                )
        except sqlite3.OperationalError as exc:
            self.close()
            if "fts5" in str(exc).casefold():
                raise RuntimeError(
                    "当前 Python 的 SQLite 未启用 FTS5，无法使用 sqlite 检索后端"
                ) from exc
            raise

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        if top_k <= 0:
            return []

        query_terms = expand_query_terms(query)
        if not query_terms:
            return []
        if _has_unknown_opaque_identifier(query, self._chunks):
            return []

        # Each term is quoted because it has already been tokenized. Joining
        # with OR lets the shared coverage rule reject low-quality partial hits.
        match_query = " OR ".join(_quote_fts_term(term) for term in sorted(query_terms))
        phrase_terms = _query_phrases(query)
        rows = self._connection.execute(
            """
            SELECT
                metadata.chunk_id,
                metadata.document_id,
                metadata.path,
                metadata.title,
                metadata.text,
                metadata.start_line,
                metadata.end_line,
                bm25(chunks_fts, ?, ?, ?, ?) AS bm25_score
            FROM chunks_fts
            JOIN chunk_metadata AS metadata
              ON metadata.chunk_id = chunks_fts.chunk_id
            WHERE chunks_fts MATCH ?
            ORDER BY bm25_score ASC, metadata.path ASC, metadata.start_line ASC
            """,
            (*self._BM25_WEIGHTS, match_query),
        ).fetchall()

        results: list[SearchResult] = []
        for row in rows:
            chunk_id = row["chunk_id"]
            matched_terms = sorted(
                term for term in query_terms if term in self._content_tokens[chunk_id]
            )
            if not matched_terms:
                continue

            coverage = len(matched_terms) / len(query_terms)
            if coverage < MIN_QUERY_COVERAGE:
                continue

            phrase_hits = sum(
                _contains_token_phrase(self._tokenized_content[chunk_id], phrase)
                for phrase in phrase_terms
            )
            phrase_hits += sum(
                _contains_token_phrase(self._tokenized_paths[chunk_id], phrase)
                for phrase in phrase_terms
            )
            # SQLite's bm25() returns lower (usually negative) values for
            # better matches. SearchResult exposes a non-negative score with
            # higher-is-better semantics, shared by all backends.
            score = max(0.0, -float(row["bm25_score"]))
            score += (coverage * 0.5) + (phrase_hits * 1.25)
            results.append(
                SearchResult(
                    chunk=Chunk(
                        id=chunk_id,
                        document_id=row["document_id"],
                        path=row["path"],
                        title=row["title"],
                        text=row["text"],
                        start_line=row["start_line"],
                        end_line=row["end_line"],
                    ),
                    score=score,
                    matched_terms=matched_terms,
                )
            )

        results.sort(key=lambda item: (-item.score, item.chunk.path, item.chunk.start_line))
        return results[:top_k]

    def close(self) -> None:
        if getattr(self, "_connection", None) is not None:
            self._connection.close()
            self._connection = None


def build_search_index(
    chunks: list[Chunk],
    *,
    backend: str = "memory",
    database_path: str | Path | None = None,
    embedding_cache_path: str | Path | None = None,
    embedding_model: str | None = None,
    embedding_min_score: float = 0.2,
    embedding_max_chunks: int | None = None,
    reranker: object | None = None,
    rerank_candidates: int = 20,
) -> SearchIndex:
    """Build the configured search backend behind the stable interface."""
    normalized_backend = backend.casefold()
    if normalized_backend == "memory":
        index: SearchIndex = InMemorySearchIndex(chunks)
    elif normalized_backend in {"sqlite", "sqlite-fts5"}:
        index = SQLiteFTS5SearchIndex(chunks, database_path=database_path)
    elif normalized_backend == "embedding":
        from .embeddings import EmbeddingSearchIndex, OpenAICompatibleEmbeddingProvider

        provider = OpenAICompatibleEmbeddingProvider(model=embedding_model)
        index = EmbeddingSearchIndex(
            chunks,
            provider=provider,
            cache_path=embedding_cache_path,
            min_score=embedding_min_score,
            max_chunks=embedding_max_chunks,
        )
    else:
        raise ValueError(
            f"Unsupported search backend: {backend}. "
            "Choose 'memory', 'sqlite', or 'embedding'."
        )

    if reranker is not None:
        from .rerank import RerankingSearchIndex

        index = RerankingSearchIndex(
            index,
            reranker,
            candidate_k=rerank_candidates,
        )
    return index


def expand_query_terms(query: str) -> set[str]:
    """Normalize mixed-language queries into searchable concept terms."""
    normalized = normalize_text(query)
    without_phrase_stopwords = normalized
    for stopword in sorted(QUERY_STOPWORDS, key=len, reverse=True):
        if not stopword.isascii():
            without_phrase_stopwords = without_phrase_stopwords.replace(stopword, " ")
    terms = set(tokenize(without_phrase_stopwords)) - QUERY_STOPWORDS
    for phrase, aliases in QUERY_ALIASES.items():
        normalized_phrase = normalize_text(phrase)
        if normalized_phrase in normalized:
            terms.difference_update(tokenize(normalized_phrase))
            terms.update(aliases)
    return terms


def _query_phrases(query: str) -> list[tuple[str, ...]]:
    """Return meaningful ASCII bigrams for a small exact-phrase boost."""
    terms = [
        token
        for token in tokenize(query)
        if token not in QUERY_STOPWORDS and token.isascii() and len(token) > 1
    ]
    return [tuple(terms[index : index + 2]) for index in range(len(terms) - 1)]


def _contains_token_phrase(tokens: list[str], phrase: tuple[str, ...]) -> bool:
    if not phrase or len(phrase) > len(tokens):
        return False
    return any(
        tuple(tokens[index : index + len(phrase)]) == phrase
        for index in range(len(tokens) - len(phrase) + 1)
    )


def _has_unknown_opaque_identifier(query: str, chunks: list[Chunk]) -> bool:
    identifiers = OPAQUE_IDENTIFIER_PATTERN.findall(query)
    if not identifiers:
        return False
    searchable_text = "\n".join(
        normalize_text(f"{chunk.path} {chunk.title} {chunk.text}") for chunk in chunks
    )
    return any(identifier.casefold() not in searchable_text for identifier in identifiers)


def _deduplicate_chunks(chunks: list[Chunk]) -> list[Chunk]:
    unique_chunks: list[Chunk] = []
    seen_ids: set[str] = set()
    for chunk in chunks:
        if chunk.id not in seen_ids:
            unique_chunks.append(chunk)
            seen_ids.add(chunk.id)
    return unique_chunks


def _fts_text(text: str) -> str:
    """Store the same token boundaries used by the in-memory backend."""
    return " ".join(tokenize(text))


def _quote_fts_term(term: str) -> str:
    return f'"{term.replace(chr(34), chr(34) * 2)}"'
