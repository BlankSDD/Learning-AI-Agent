from __future__ import annotations

from dataclasses import dataclass

from .models import Answer, SearchResult


@dataclass(frozen=True)
class CitationValidation:
    is_valid: bool
    errors: tuple[str, ...] = ()


def validate_citations(
    answer: Answer,
    retrieved: list[SearchResult],
) -> CitationValidation:
    chunks = {result.chunk.id: result.chunk for result in retrieved}
    errors: list[str] = []

    for citation in answer.citations:
        chunk = chunks.get(citation.chunk_id)
        if chunk is None:
            errors.append(f"Citation references a non-retrieved chunk: {citation.chunk_id}")
            continue
        if citation.path != chunk.path:
            errors.append(f"Citation path mismatch: {citation.path}")
        if citation.start_line < chunk.start_line or citation.end_line > chunk.end_line:
            errors.append(f"Citation line range is outside chunk: {citation.chunk_id}")

    return CitationValidation(is_valid=not errors, errors=tuple(errors))
