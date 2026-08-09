from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from .models import SearchResult


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    arguments_model: type[BaseModel]
    handler: Callable[..., Any]

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.arguments_model.model_json_schema(),
            },
        }


@dataclass
class ToolOutput:
    payload: Any
    evidence: list[SearchResult] = field(default_factory=list)


@dataclass
class ToolExecution:
    name: str
    content: str
    payload: Any = None
    evidence: list[SearchResult] = field(default_factory=list)
    is_error: bool = False


class ToolRegistry:
    """Registers model-visible tools and safely dispatches tool calls."""

    def __init__(self, definitions: list[ToolDefinition] | None = None):
        self._definitions: dict[str, ToolDefinition] = {}
        for definition in definitions or []:
            self.register(definition)

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._definitions:
            raise ValueError(f"Tool already registered: {definition.name}")
        self._definitions[definition.name] = definition

    def schemas(self) -> list[dict[str, Any]]:
        return [definition.schema() for definition in self._definitions.values()]

    def execute(self, name: str, arguments: dict[str, Any] | str | None) -> ToolExecution:
        definition = self._definitions.get(name)
        if definition is None:
            return self._error(name, f"Unknown tool: {name}")

        parsed_arguments = self._parse_arguments(arguments)
        if isinstance(parsed_arguments, str):
            return self._error(name, parsed_arguments)

        try:
            validated = definition.arguments_model.model_validate(parsed_arguments)
        except (ValidationError, TypeError) as exc:
            return self._error(name, f"Invalid arguments for {name}: {exc}")

        try:
            output = definition.handler(**validated.model_dump())
        except Exception as exc:
            return self._error(name, f"Tool {name} failed: {exc}")

        if not isinstance(output, ToolOutput):
            output = ToolOutput(payload=output)
        return ToolExecution(
            name=name,
            content=_serialize(output.payload),
            payload=output.payload,
            evidence=output.evidence,
        )

    @staticmethod
    def _parse_arguments(arguments: dict[str, Any] | str | None) -> dict[str, Any] | str:
        if arguments is None:
            return {}
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError as exc:
                return f"Tool arguments are not valid JSON: {exc}"
            if isinstance(parsed, dict):
                return parsed
        return "Tool arguments must be a JSON object"

    @staticmethod
    def _error(name: str, message: str) -> ToolExecution:
        payload = {"error": message}
        return ToolExecution(
            name=name,
            content=_serialize(payload),
            payload=payload,
            is_error=True,
        )


def _serialize(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)
