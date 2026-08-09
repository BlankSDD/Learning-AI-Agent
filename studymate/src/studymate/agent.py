from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from .citations import validate_citations
from .llm import LLMResponseParser
from .models import Answer, SearchResult
from .tool_registry import ToolExecution, ToolRegistry


@dataclass(frozen=True)
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any] | str | None


@dataclass
class ModelToolResponse:
    content: str | None = None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)


class AgentModel(Protocol):
    def chat_with_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelToolResponse: ...


@dataclass
class AgentResult:
    answer: Answer
    retrieved: list[SearchResult] = field(default_factory=list)
    steps: int = 0
    tool_calls: list[str] = field(default_factory=list)


class AgentRunError(RuntimeError):
    """Raised when an Agent response cannot be completed or parsed."""


class AgentRunner:
    """A small bounded Agent runtime for StudyMate's local knowledge tools."""

    def __init__(
        self,
        *,
        llm: AgentModel,
        tool_registry: ToolRegistry,
        max_steps: int = 5,
        max_history: int = 6,
    ):
        if max_steps <= 0:
            raise ValueError("max_steps must be greater than zero")
        self.llm = llm
        self.tool_registry = tool_registry
        self.max_steps = max_steps
        self.max_history = max_history

    def run(
        self,
        *,
        user_input: str,
        history: Sequence[dict[str, str]] | None = None,
    ) -> AgentResult:
        messages = self._initial_messages(user_input, history or [])
        retrieved: list[SearchResult] = []
        called_tools: list[str] = []

        for step in range(1, self.max_steps + 1):
            response = self.llm.chat_with_tools(
                messages=messages,
                tools=self.tool_registry.schemas(),
            )
            if not response.tool_calls:
                answer = self._parse_final_answer(response.content, retrieved)
                return AgentResult(
                    answer=answer,
                    retrieved=retrieved,
                    steps=step,
                    tool_calls=called_tools,
                )

            messages.append(self._assistant_message(response))
            for call in response.tool_calls:
                called_tools.append(call.name)
                execution = self.tool_registry.execute(call.name, call.arguments)
                self._merge_evidence(retrieved, execution)
                messages.append(self._tool_message(call, execution))

        return AgentResult(
            answer=Answer(
                answer="Agent 执行步骤超过限制，已停止本次任务。",
                citations=[],
                confidence=0.0,
                need_more_context=True,
                next_steps=["缩小问题范围", "将复杂任务拆分成多个问题"],
            ),
            retrieved=retrieved,
            steps=self.max_steps,
            tool_calls=called_tools,
        )

    def _initial_messages(
        self,
        user_input: str,
        history: Sequence[dict[str, str]],
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are StudyMate, a local knowledge learning assistant. "
                    "Use the provided tools to retrieve evidence when answering. "
                    "Do not invent facts that are absent from tool results. "
                    "When you have enough evidence, return only JSON with fields "
                    "answer, citations, confidence, need_more_context, and next_steps. "
                    "Citations must reference retrieved chunk_id values. "
                    "If evidence is insufficient, say so and set need_more_context to true."
                ),
            }
        ]
        messages.extend(dict(message) for message in history[-self.max_history :])
        messages.append({"role": "user", "content": user_input})
        return messages

    @staticmethod
    def _assistant_message(response: ModelToolResponse) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": response.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": _arguments_json(call.arguments),
                    },
                }
                for call in response.tool_calls
            ],
        }

    @staticmethod
    def _tool_message(call: ToolCallRequest, execution: ToolExecution) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": call.id,
            "name": call.name,
            "content": execution.content,
        }

    @staticmethod
    def _merge_evidence(retrieved: list[SearchResult], execution: ToolExecution) -> None:
        known_ids = {result.chunk.id for result in retrieved}
        for result in execution.evidence:
            if result.chunk.id not in known_ids:
                retrieved.append(result)
                known_ids.add(result.chunk.id)

    @staticmethod
    def _parse_final_answer(content: str | None, evidence: list[SearchResult]) -> Answer:
        if not content:
            raise AgentRunError("模型没有返回最终答案或工具调用")
        try:
            answer = LLMResponseParser().parse(content, evidence=evidence)
        except Exception as exc:
            raise AgentRunError(
                "模型最终回答无法解析为 StudyMate 所需的结构化格式"
            ) from exc

        validation = validate_citations(answer, evidence)
        if not validation.is_valid:
            return Answer(
                answer="模型返回了无法验证的引用，因此本次回答被拦截。",
                citations=[],
                confidence=0.0,
                need_more_context=True,
                next_steps=["检查知识库来源", "重新提问"],
            )
        return answer


def _arguments_json(arguments: dict[str, Any] | str | None) -> str:
    if isinstance(arguments, str):
        return arguments
    return json.dumps(arguments or {}, ensure_ascii=False)
