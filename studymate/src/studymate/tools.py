from __future__ import annotations

import hashlib
import re
from pathlib import Path

from pydantic import BaseModel, Field

from .ingest import SUPPORTED_SUFFIXES
from .models import Chunk, SearchResult
from .search import InMemorySearchIndex
from .tool_registry import ToolDefinition, ToolOutput, ToolRegistry


class SearchKnowledgeArgs(BaseModel):
    query: str = Field(min_length=1, description="要检索的问题或主题")
    top_k: int = Field(default=5, ge=1, le=10, description="最多返回的结果数量")


class OpenDocumentArgs(BaseModel):
    path: str = Field(min_length=1, description="知识库内的相对文档路径")
    start_line: int = Field(default=1, ge=1, description="起始行号，从 1 开始")
    end_line: int | None = Field(default=None, ge=1, description="结束行号")


class KnowledgeToolError(RuntimeError):
    """Raised when a knowledge-base tool cannot complete safely."""


class KnowledgeTools:
    """Read-only tools exposed to the StudyMate Agent."""

    def __init__(self, knowledge_root: Path, search_index: InMemorySearchIndex):
        self.knowledge_root = Path(knowledge_root).resolve()
        self.search_index = search_index

    def search_knowledge(self, *, query: str, top_k: int = 5) -> ToolOutput:
        results = self.search_index.search(query, top_k=top_k)
        return ToolOutput(
            payload={
                "query": query,
                "results": [result.model_dump(mode="json") for result in results],
            },
            evidence=results,
        )

    def open_document(
        self,
        *,
        path: str,
        start_line: int = 1,
        end_line: int | None = None,
    ) -> ToolOutput:
        document_path = self._safe_document_path(path)
        try:
            lines = document_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise KnowledgeToolError(f"Cannot read knowledge file: {path}") from exc

        if start_line > max(len(lines), 1):
            raise KnowledgeToolError(
                f"start_line {start_line} is outside document with {len(lines)} lines"
            )
        actual_end = end_line if end_line is not None else len(lines)
        if actual_end < start_line:
            raise KnowledgeToolError("end_line must be greater than or equal to start_line")

        actual_end = min(actual_end, len(lines))
        selected = lines[start_line - 1 : actual_end]
        relative_path = document_path.relative_to(self.knowledge_root).as_posix()
        selected_text = "\n".join(selected)
        chunk_id = hashlib.sha1(
            f"open:{relative_path}:{start_line}:{actual_end}:{selected_text}".encode("utf-8")
        ).hexdigest()[:16]
        opened_chunk = Chunk(
            id=chunk_id,
            document_id=hashlib.sha1(relative_path.encode("utf-8")).hexdigest()[:16],
            path=relative_path,
            title=_title_from_lines(document_path, lines),
            text=selected_text,
            start_line=start_line,
            end_line=actual_end,
        )
        return ToolOutput(
            payload={
                "path": relative_path,
                "title": _title_from_lines(document_path, lines),
                "start_line": start_line,
                "end_line": actual_end,
                "text": selected_text,
                "chunk_id": chunk_id,
            },
            evidence=[SearchResult(chunk=opened_chunk, score=1.0)],
        )

    def _safe_document_path(self, path: str) -> Path:
        candidate = (self.knowledge_root / path).resolve()
        try:
            candidate.relative_to(self.knowledge_root)
        except ValueError as exc:
            raise KnowledgeToolError("Document path must stay inside the knowledge directory") from exc
        if not candidate.is_file():
            raise KnowledgeToolError(f"Knowledge document does not exist: {path}")
        if candidate.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise KnowledgeToolError(f"Unsupported knowledge document type: {candidate.suffix}")
        return candidate


def build_knowledge_tool_registry(knowledge_tools: KnowledgeTools) -> ToolRegistry:
    return ToolRegistry(
        [
            ToolDefinition(
                name="search_knowledge",
                description=(
                    "在 StudyMate 本地知识库中检索与用户问题相关的 Markdown 或 TXT 内容。"
                ),
                arguments_model=SearchKnowledgeArgs,
                handler=knowledge_tools.search_knowledge,
            ),
            ToolDefinition(
                name="open_document",
                description=(
                    "打开知识库中的一个文档或指定行范围，以获取比搜索片段更完整的上下文。"
                ),
                arguments_model=OpenDocumentArgs,
                handler=knowledge_tools.open_document,
            ),
        ]
    )


def _title_from_lines(path: Path, lines: list[str]) -> str:
    for line in lines:
        match = re.match(r"^\s*#\s+(.+?)\s*$", line)
        if match:
            return match.group(1).strip()
    return path.stem
