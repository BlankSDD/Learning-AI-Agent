from __future__ import annotations

import re

from .models import CommandResult, Intent, IntentKind

SUPPORTED_COMMANDS = {
    "help",
    "sources",
    "trace",
    "output",
    "reset",
    "update",
    "quit",
}
GOAL_MARKERS = (
    "想学习",
    "想学",
    "学习",
    "学会",
    "掌握",
    "从零",
    "入门",
    "学习路线",
    "目标",
)
QUESTION_MARKERS = (
    "什么",
    "为什么",
    "怎么",
    "如何",
    "区别",
    "是否",
    "能否",
)


def parse_command(text: str) -> CommandResult:
    stripped = text.strip()
    if not stripped.startswith("/"):
        return CommandResult(name="", is_valid=False, message="Input is not a command")

    parts = stripped[1:].split()
    name = parts[0].lower() if parts else ""
    if name not in SUPPORTED_COMMANDS:
        return CommandResult(
            name=name,
            is_valid=False,
            args=parts[1:],
            message=f"Unknown command: /{name}",
        )

    return CommandResult(name=name, is_valid=True, args=parts[1:])


def classify_input(text: str) -> Intent:
    stripped = text.strip()
    if stripped.startswith("/"):
        command = parse_command(stripped)
        return Intent(kind=IntentKind.COMMAND, text=stripped, command=command.name)

    if any(marker in stripped for marker in GOAL_MARKERS):
        return Intent(kind=IntentKind.GOAL, text=stripped)

    if (
        "?" in stripped
        or "？" in stripped
        or any(marker in stripped for marker in QUESTION_MARKERS)
    ):
        return Intent(kind=IntentKind.QUESTION, text=stripped)

    terms = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", stripped)
    if len(terms) <= 8:
        return Intent(kind=IntentKind.KEYWORD, text=stripped)

    return Intent(kind=IntentKind.QUESTION, text=stripped)
