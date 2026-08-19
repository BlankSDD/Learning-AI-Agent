from __future__ import annotations

import json
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from .citations import validate_citations
from .llm import LLMResponseParser
from .models import Answer, SearchResult
from .trace import AgentTrace, AgentTraceStep
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
    trace: AgentTrace = field(default_factory=AgentTrace)


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
        max_calls_per_tool: int = 1,
    ):
        if max_steps <= 0:
            raise ValueError("max_steps must be greater than zero")
        if max_calls_per_tool <= 0:
            raise ValueError("max_calls_per_tool must be greater than zero")
        self.llm = llm
        self.tool_registry = tool_registry
        self.max_steps = max_steps
        self.max_history = max_history
        self.max_calls_per_tool = max_calls_per_tool

    def run(
        self,
        *,
        user_input: str,
        history: Sequence[dict[str, str]] | None = None,
    ) -> AgentResult:
        messages = self._initial_messages(user_input, history or [])
        retrieved: list[SearchResult] = []
        called_tools: list[str] = []
        tool_call_counts: dict[str, int] = {}
        trace = AgentTrace()
        definition_question = _is_simple_definition_question(user_input)

        for step in range(1, self.max_steps + 1):
            registered_tools = self.tool_registry.schemas()
            registered_tool_names = {
                schema["function"]["name"] for schema in registered_tools
            }
            available_tools = self._available_tool_schemas(
                tool_call_counts,
                registered_tools,
                blocked_tools={"open_document"}
                if definition_question and tool_call_counts.get("search_knowledge", 0) > 0
                else set(),
            )
            available_tool_names = {
                schema["function"]["name"] for schema in available_tools
            }
            if not available_tools:
                trace_step = AgentTraceStep(
                    step=step,
                    mode="finalization",
                    available_tools=[],
                )
                request_started_at = time.monotonic()
                response = self.llm.chat_with_tools(
                    messages=self._finalization_messages(messages),
                    tools=[],
                )
            else:
                trace_step = AgentTraceStep(
                    step=step,
                    mode="tool_decision",
                    available_tools=sorted(available_tool_names),
                )
                request_started_at = time.monotonic()
                response = self.llm.chat_with_tools(
                    messages=messages,
                    tools=available_tools,
                )
            trace_step.duration_ms = int((time.monotonic() - request_started_at) * 1000)
            trace_step.requested_tools = [
                {"name": call.name, "arguments": call.arguments or {}}
                for call in response.tool_calls
            ]
            trace.add_step(trace_step)
            if not response.tool_calls:
                answer = self._parse_final_answer(response.content, retrieved)
                trace.finish("final_answer")
                return AgentResult(
                    answer=answer,
                    retrieved=retrieved,
                    steps=step,
                    tool_calls=called_tools,
                    trace=trace,
                )

            messages.append(self._assistant_message(response))
            searched_without_evidence = False
            for call in response.tool_calls:
                called_tools.append(call.name)
                call_count = tool_call_counts.get(call.name, 0)
                if call.name in registered_tool_names and call_count >= self.max_calls_per_tool:
                    error_message = (
                        f"Tool call blocked: {call.name} has already used "
                        "its per-run call budget. Choose another available tool "
                        "or return a final answer."
                    )
                    execution = ToolExecution(
                        name=call.name,
                        content=json.dumps({"error": error_message}, ensure_ascii=False),
                        payload={"error": error_message},
                        is_error=True,
                    )
                else:
                    if call.name in registered_tool_names:
                        tool_call_counts[call.name] = call_count + 1
                    execution = self.tool_registry.execute(call.name, call.arguments)
                execution_record = {
                    "name": execution.name,
                    "status": "error" if execution.is_error else "ok",
                    "evidence_count": len(execution.evidence),
                    "error": _execution_error(execution),
                }
                if call.name == "search_knowledge" and not execution.is_error:
                    if isinstance(execution.payload, dict):
                        for field_name in ("query", "rewritten_query"):
                            value = execution.payload.get(field_name)
                            if isinstance(value, str):
                                execution_record[field_name] = value
                    execution_record["ranking"] = _serialize_search_results(
                        execution.evidence
                    )
                trace_step.executions.append(execution_record)
                self._merge_evidence(retrieved, execution)
                messages.append(self._tool_message(call, execution))
                if (
                    call.name == "search_knowledge"
                    and not execution.is_error
                    and not execution.evidence
                ):
                    searched_without_evidence = True

            if searched_without_evidence and not retrieved:
                trace.finish("empty_search")
                return AgentResult(
                    answer=self._no_evidence_answer(),
                    retrieved=retrieved,
                    steps=step,
                    tool_calls=called_tools,
                    trace=trace,
                )

        trace.finish("max_steps")
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
            trace=trace,
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
                    "Call search_knowledge at most once for a user question. "
                    "For a simple definition question, answer after one search and do not "
                    "open extra documents. Call open_document at most once per run. "
                    "Never request multiple open_document calls in one model response. "
                    "If its result list is empty, do not call another tool; return a final "
                    "JSON answer that says the knowledge base has insufficient evidence. "
                    "When search_knowledge returns evidence and more context is needed, "
                    "call open_document with a path from those results instead of searching again. "
                    "Only call open_document for a path returned by search_knowledge, and "
                    "never repeat a tool call with the same arguments. "
                    "When you have enough evidence, return only JSON with fields "
                    "answer, citations, confidence, need_more_context, and next_steps. "
                    "confidence must be a decimal number from 0 to 1, not a text label. "
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

    def _available_tool_schemas(
        self,
        tool_call_counts: dict[str, int],
        schemas: list[dict[str, Any]],
        blocked_tools: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        blocked_tools = blocked_tools or set()
        return [
            schema
            for schema in schemas
            if schema["function"]["name"] not in blocked_tools
            if tool_call_counts.get(schema["function"]["name"], 0)
            < self.max_calls_per_tool
        ]

    @staticmethod
    def _finalization_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Avoid sending Bedrock tool-result blocks after the tool budget is exhausted."""
        observations: list[str] = []
        cleaned: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            if role == "tool":
                observations.append(str(message.get("content", "")))
                continue
            if role == "assistant" and message.get("tool_calls"):
                continue
            cleaned.append(dict(message))

        cleaned.append(
            {
                "role": "user",
                "content": (
                    "Tool calling is now disabled for this run. Based only on the "
                    "following tool observations, return the final StudyMate JSON. "
                    "Do not invent facts or citations.\n\n"
                    "Tool observations:\n"
                    + "\n\n".join(observations)
                ),
            }
        )
        return cleaned

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
            details = _validation_error_fields(exc)
            raise AgentRunError(
                "模型最终回答无法解析为 StudyMate 所需的结构化格式"
                f"（字段：{details}）"
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

    @staticmethod
    def _no_evidence_answer() -> Answer:
        return Answer(
            answer="知识库中没有找到足以回答该问题的相关资料。",
            citations=[],
            confidence=0.0,
            need_more_context=True,
            next_steps=[
                "补充相关 Markdown 或 TXT 文档到知识库",
                "使用知识库中已有术语重新提问",
            ],
        )


def _arguments_json(arguments: dict[str, Any] | str | None) -> str:
    if isinstance(arguments, str):
        return arguments
    return json.dumps(arguments or {}, ensure_ascii=False)


def _validation_error_fields(error: Exception) -> str:
    errors = getattr(error, "errors", None)
    if not callable(errors):
        return type(error).__name__
    try:
        locations = [
            ".".join(str(part) for part in issue.get("loc", ()))
            for issue in errors()
            if issue.get("loc")
        ]
    except Exception:
        return type(error).__name__
    return ", ".join(locations[:5]) or type(error).__name__


def _execution_error(execution: ToolExecution) -> str | None:
    if not execution.is_error or not isinstance(execution.payload, dict):
        return None
    error = execution.payload.get("error")
    return error if isinstance(error, str) else None


def _serialize_search_results(results: list[SearchResult]) -> list[dict[str, Any]]:
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
        }
        for rank, result in enumerate(results, start=1)
    ]


def _is_simple_definition_question(user_input: str) -> bool:
    """Identify questions that should be answered from the search result alone."""
    normalized = " ".join(user_input.casefold().split())
    detail_markers = (
        "详细",
        "流程",
        "步骤",
        "原文",
        "文档",
        "detail",
        "detailed",
        "explain",
        "how",
        "why",
        "difference",
        "区别",
    )
    if any(marker in normalized for marker in detail_markers):
        return False
    markers = (
        "是什么",
        "是什麼",
        "什么意思",
        "有何作用",
        "what is",
        "what are",
        "what does",
    )
    return any(marker in normalized for marker in markers)
