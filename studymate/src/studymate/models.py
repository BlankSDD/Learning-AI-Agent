from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class IntentKind(str, Enum):
    QUESTION = "question"
    GOAL = "goal"
    KEYWORD = "keyword"
    COMMAND = "command"


class Document(BaseModel):
    id: str
    path: str
    title: str
    content_hash: str
    text: str


class Chunk(BaseModel):
    id: str
    document_id: str
    path: str
    title: str
    text: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class SearchResult(BaseModel):
    chunk: Chunk
    score: float = Field(ge=0)
    matched_terms: list[str] = Field(default_factory=list)


class Citation(BaseModel):
    chunk_id: str
    path: str
    title: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    quote: str


class Answer(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    need_more_context: bool = False
    next_steps: list[str] = Field(default_factory=list)


class Intent(BaseModel):
    kind: IntentKind
    text: str
    command: str | None = None


class CommandResult(BaseModel):
    name: str
    is_valid: bool
    args: list[str] = Field(default_factory=list)
    message: str = ""


class ChatResponse(BaseModel):
    answer: Answer | None = None
    history: list[dict[str, str]] = Field(default_factory=list)
    retrieved: list[SearchResult] = Field(default_factory=list)
    command: CommandResult | None = None
