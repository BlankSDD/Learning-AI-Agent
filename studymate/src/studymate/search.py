from __future__ import annotations

import math
import re
from collections import Counter

from .models import Chunk, SearchResult

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


class InMemorySearchIndex:
    def __init__(self, chunks: list[Chunk]):
        self._chunks = list(chunks)
        self._tokenized = {
            chunk.id: Counter(tokenize(f"{chunk.title} {chunk.text}"))
            for chunk in self._chunks
        }

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        if top_k <= 0:
            return []

        query_terms = set(tokenize(query))
        if not query_terms:
            return []

        results: list[SearchResult] = []
        for chunk in self._chunks:
            term_counts = self._tokenized[chunk.id]
            matched_terms = sorted(term for term in query_terms if term in term_counts)
            if not matched_terms:
                continue

            weighted_hits = sum(term_counts[term] for term in matched_terms)
            coverage = len(matched_terms) / len(query_terms)
            score = (weighted_hits * 0.7) + (coverage * 0.3)
            score = score / math.sqrt(max(len(term_counts), 1))
            results.append(
                SearchResult(
                    chunk=chunk,
                    score=score,
                    matched_terms=matched_terms,
                )
            )

        results.sort(key=lambda item: (-item.score, item.chunk.path, item.chunk.start_line))
        return results[:top_k]

