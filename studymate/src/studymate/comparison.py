from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import SearchResult
from .rerank import Reranker
from .search import SearchIndex, rewrite_query, split_comparison_query

SCORE_TYPES = {
    "memory": "bm25_style",
    "sqlite": "sqlite_bm25",
    "embedding": "cosine_similarity",
    "reranked": "llm_relevance",
}


def run_search_comparison(
    *,
    queries: list[str],
    indexes: dict[str, SearchIndex],
    output_path: Path,
    top_k: int = 5,
    reranker: Reranker | None = None,
    candidate_k: int = 20,
    setup_errors: dict[str, str] | None = None,
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with output_path.open("a", encoding="utf-8") as output:
        for query in queries:
            backend_results: dict[str, list[dict[str, Any]]] = {}
            errors: dict[str, str] = dict(setup_errors or {})
            raw_results: dict[str, list[SearchResult]] = {}
            for name, index in indexes.items():
                try:
                    results = index.search(
                        query,
                        top_k=max(top_k, candidate_k) if reranker else top_k,
                    )
                    raw_results[name] = results
                    backend_results[name] = _serialize_results(results[:top_k])
                except Exception as exc:
                    errors[name] = f"{type(exc).__name__}: {exc}"

            record: dict[str, Any] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "query": query,
                "rewritten_query": rewrite_query(query),
                "comparison_topics": list(split_comparison_query(query)),
                "top_k": top_k,
                "backends": backend_results,
                "score_types": {
                    name: SCORE_TYPES.get(name, "unknown")
                    for name in backend_results
                },
                "errors": errors,
            }
            if reranker:
                candidates = _merge_results(raw_results.values(), limit=candidate_k)
                try:
                    reranked = reranker.rerank(query, candidates, top_k=top_k)
                    record["reranked"] = _serialize_results(reranked)
                    record["score_types"]["reranked"] = SCORE_TYPES["reranked"]
                except Exception as exc:
                    record["reranked_error"] = f"{type(exc).__name__}: {exc}"

            output.write(json.dumps(record, ensure_ascii=False) + "\n")
            output.flush()
            print(format_search_comparison(record))
            written += 1
    return written


def format_search_comparison(record: dict[str, Any]) -> str:
    lines = [
        f"\nQuery: {record['query']}",
        f"Rewritten query: {record.get('rewritten_query') or '(empty)'}",
    ]
    topics = record.get("comparison_topics") or []
    if topics:
        lines.append(
            "Comparison topics: "
            + " | ".join(topics)
            + " (results interleaved by topic)"
        )
    for name, results in record.get("backends", {}).items():
        score_type = record.get("score_types", {}).get(name, "unknown")
        lines.append(f"[{name}; score={score_type}]")
        if not results:
            lines.append("  (empty)")
        for result in results:
            lines.append(
                f"  {result['rank']}. {result['path']}:{result['start_line']}-"
                f"{result['end_line']} score={result['score']:.6f}"
                f" terms={','.join(result['matched_terms']) or '-'}"
            )
    if "reranked" in record:
        lines.append(
            f"[reranked; score={record.get('score_types', {}).get('reranked', 'unknown')}]"
        )
        for result in record["reranked"]:
            lines.append(
                f"  {result['rank']}. {result['path']}:{result['start_line']}-"
                f"{result['end_line']} score={result['score']:.6f}"
            )
    errors = record.get("errors", {})
    for name, error in errors.items():
        lines.append(f"[{name} error] {error}")
    if record.get("reranked_error"):
        lines.append(f"[reranked error] {record['reranked_error']}")
    return "\n".join(lines)


def _serialize_results(results: list[SearchResult]) -> list[dict[str, Any]]:
    return [
        {
            "rank": rank,
            "chunk_id": result.chunk.id,
            "path": result.chunk.path,
            "title": result.chunk.title,
            "start_line": result.chunk.start_line,
            "end_line": result.chunk.end_line,
            "score": result.score,
            "matched_terms": result.matched_terms,
            "text_preview": " ".join(result.chunk.text.split())[:240],
        }
        for rank, result in enumerate(results, start=1)
    ]


def _merge_results(
    result_groups: Any,
    *,
    limit: int,
) -> list[SearchResult]:
    merged: list[SearchResult] = []
    seen: set[str] = set()
    for results in result_groups:
        for result in results:
            if result.chunk.id in seen:
                continue
            merged.append(result)
            seen.add(result.chunk.id)
            if len(merged) >= limit:
                return merged
    return merged
