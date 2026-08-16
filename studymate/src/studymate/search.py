from __future__ import annotations

import math
import re
from collections import Counter

from .models import Chunk, SearchResult

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")

# The downloaded documentation is mostly English while user questions can be
# Chinese. Keep the expansion small and domain-oriented so it improves recall
# without turning every query into a broad synonym search.
QUERY_ALIASES = {
    "自定义工具": ("custom", "tool", "tools"),
    "自定义": ("custom",),
    "工具": ("tool", "tools"),
    "定义": ("define", "defined", "definition"),
    "循环": ("loop",),
    "追踪": ("trace", "traces"),
    "可观测性": ("observability",),
    "关系": ("relationship", "related"),
}

QUERY_STOPWORDS = {"的", "是", "中", "和", "有", "什么", "如何", "怎么"}


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


class InMemorySearchIndex:
    def __init__(self, chunks: list[Chunk]):
        self._chunks = list(chunks)
        self._tokenized = {
            chunk.id: Counter(tokenize(f"{chunk.title} {chunk.text}"))
            for chunk in self._chunks
        }
        self._title_tokens = {
            chunk.id: set(tokenize(chunk.title)) for chunk in self._chunks
        }
        self._path_tokens = {
            chunk.id: set(tokenize(chunk.path.replace("-", " ")))
            for chunk in self._chunks
        }

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        if top_k <= 0:
            return []

        query_terms = expand_query_terms(query)
        if not query_terms:
            return []

        results: list[SearchResult] = []
        for chunk in self._chunks:
            term_counts = self._tokenized[chunk.id]
            matched_terms = sorted(term for term in query_terms if term in term_counts)
            if not matched_terms:
                continue

            coverage = len(matched_terms) / len(query_terms)
            weighted_hits = sum(min(term_counts[term], 3) for term in matched_terms)
            title_hits = len(set(matched_terms) & self._title_tokens[chunk.id])
            path_hits = len(set(matched_terms) & self._path_tokens[chunk.id])
            score = (
                (coverage * 3.0)
                + (math.log1p(weighted_hits) * 0.35)
                + (title_hits * 0.8)
                + (path_hits * 0.6)
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


def expand_query_terms(query: str) -> set[str]:
    """Normalize mixed-language queries into searchable concept terms."""
    normalized = query.lower()
    terms = set(tokenize(normalized)) - QUERY_STOPWORDS
    for phrase, aliases in QUERY_ALIASES.items():
        if phrase in normalized:
            terms.difference_update(tokenize(phrase))
            terms.update(aliases)
    return terms
