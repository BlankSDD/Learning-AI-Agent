from __future__ import annotations

import hashlib
import re
from bisect import bisect_left
from pathlib import Path

from .models import Chunk, Document

SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt"}


class DocumentLoadError(RuntimeError):
    """Raised when a knowledge document cannot be loaded."""


def _document_title(path: Path, text: str) -> str:
    for line in text.splitlines():
        match = re.match(r"^\s*#\s+(.+?)\s*$", line)
        if match:
            return match.group(1).strip()
    return path.stem


def _document_id(relative_path: str, content_hash: str) -> str:
    raw = f"{relative_path}\0{content_hash}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def load_documents(root: Path) -> list[Document]:
    root = Path(root)
    if not root.exists():
        raise DocumentLoadError(f"Knowledge directory does not exist: {root}")
    if not root.is_dir():
        raise DocumentLoadError(f"Knowledge path is not a directory: {root}")

    documents: list[Document] = []
    paths = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )

    for path in paths:
        relative_path = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DocumentLoadError(f"Cannot read knowledge file: {path}") from exc

        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        documents.append(
            Document(
                id=_document_id(relative_path, content_hash),
                path=relative_path,
                title=_document_title(path, text),
                content_hash=content_hash,
                text=text,
            )
        )

    return documents


def chunk_document(
    document: Document,
    *,
    max_chars: int = 1200,
    overlap: int = 120,
) -> list[Chunk]:
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero")
    if overlap < 0 or overlap >= max_chars:
        raise ValueError("overlap must be between zero and max_chars - 1")
    if not document.text.strip():
        return []

    text = document.text
    chunks: list[Chunk] = []
    # Line positions are shared by every chunk. Recounting from the beginning
    # for each chunk makes large downloaded documentation unnecessarily slow.
    newline_positions = [match.start() for match in re.finditer("\n", text)]
    start = 0

    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            newline = text.rfind("\n", start, end)
            if newline > start:
                end = newline

        chunk_text = text[start:end].strip()
        if chunk_text:
            start_line = bisect_left(newline_positions, start) + 1
            end_line = bisect_left(newline_positions, end) + 1
            chunk_id = hashlib.sha1(
                f"{document.id}:{start}:{end}:{chunk_text}".encode("utf-8")
            ).hexdigest()[:16]
            chunks.append(
                Chunk(
                    id=chunk_id,
                    document_id=document.id,
                    path=document.path,
                    title=document.title,
                    text=chunk_text,
                    start_line=start_line,
                    end_line=end_line,
                )
            )

        if end >= len(text):
            break
        start = max(end - overlap, start + 1)

    return chunks


def load_chunks(root: Path, **chunk_options: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for document in load_documents(root):
        chunks.extend(chunk_document(document, **chunk_options))
    return chunks
