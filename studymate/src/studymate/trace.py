from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class AgentTraceStep:
    step: int
    mode: str
    available_tools: list[str] = field(default_factory=list)
    requested_tools: list[dict[str, Any]] = field(default_factory=list)
    executions: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int | None = None


@dataclass
class AgentTrace:
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_at: str = field(default_factory=_timestamp)
    completed_at: str | None = None
    stop_reason: str | None = None
    error: str | None = None
    steps: list[AgentTraceStep] = field(default_factory=list)
    _started_at_monotonic: float = field(default_factory=time.monotonic, repr=False)
    duration_ms: int | None = None

    def add_step(self, step: AgentTraceStep) -> None:
        self.steps.append(step)

    def finish(self, stop_reason: str, error: str | None = None) -> None:
        self.stop_reason = stop_reason
        self.error = error
        self.completed_at = _timestamp()
        self.duration_ms = int((time.monotonic() - self._started_at_monotonic) * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "stop_reason": self.stop_reason,
            "error": self.error,
            "steps": [asdict(step) for step in self.steps],
        }

    def format_summary(self) -> str:
        if not self.steps and not self.stop_reason:
            return "当前会话还没有可展示的 Agent Trace。"

        lines = [
            f"运行 ID：{self.run_id}",
            f"停止原因：{self.stop_reason or '未结束'}",
            f"总耗时：{self.duration_ms if self.duration_ms is not None else '?'} ms",
        ]
        if self.error:
            lines.append(f"错误：{self.error}")
        for step in self.steps:
            lines.append(
                f"步骤 {step.step}（{step.mode}，{step.duration_ms if step.duration_ms is not None else '?'} ms）"
            )
            lines.append(
                "  可用工具：" + (", ".join(step.available_tools) or "无")
            )
            for call in step.requested_tools:
                arguments = json.dumps(call.get("arguments", {}), ensure_ascii=False)
                lines.append(f"  请求工具：{call.get('name', 'unknown')} {arguments}")
            for execution in step.executions:
                details = [f"状态：{execution.get('status', 'unknown')}"]
                if "evidence_count" in execution:
                    details.append(f"证据片段：{execution['evidence_count']}")
                if execution.get("error"):
                    details.append(f"错误：{execution['error']}")
                lines.append(
                    f"  执行工具：{execution.get('name', 'unknown')}（{'，'.join(details)}）"
                )
                rewritten_query = execution.get("rewritten_query")
                original_query = execution.get("query")
                if (
                    isinstance(rewritten_query, str)
                    and rewritten_query
                    and rewritten_query != original_query
                ):
                    lines.append(f"    rewritten_query: {rewritten_query}")
                ranking = execution.get("ranking")
                if ranking:
                    lines.append("    检索排名：")
                    for result in ranking:
                        score = result.get("score", "?")
                        if isinstance(score, (int, float)):
                            score = f"{score:.6f}"
                        terms = ",".join(result.get("matched_terms", [])) or "-"
                        lines.append(
                            f"      {result.get('rank', '?')}. "
                            f"{result.get('path', 'unknown')}:"
                            f"{result.get('start_line', '?')}-"
                            f"{result.get('end_line', '?')} "
                            f"score={score} terms={terms}"
                        )
        return "\n".join(lines)


def extract_retrieval_rankings(trace: AgentTrace | None) -> list[dict[str, Any]]:
    """Return search rankings in a compact format for exported turn output."""
    if trace is None:
        return []

    rankings: list[dict[str, Any]] = []
    for step in trace.steps:
        for execution in step.executions:
            ranking = execution.get("ranking")
            if not ranking:
                continue
            rankings.append(
                {
                    "step": step.step,
                    "tool": execution.get("name", "search_knowledge"),
                    "results": ranking,
                }
            )
    return rankings


class TraceStore:
    """Appends one sanitized question/answer/trace record per JSONL line."""

    def __init__(self, root: Path, session_id: str | None = None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id or self._new_session_id()
        self.path = self.root / f"session-{self.session_id}.jsonl"

    def append_turn(
        self,
        *,
        user_input: str,
        answer: dict[str, Any],
        trace: AgentTrace,
    ) -> Path:
        record = {
            "schema_version": 1,
            "recorded_at": _timestamp(),
            "session_id": self.session_id,
            "user_input": user_input,
            "answer": answer,
            "trace": trace.to_dict(),
        }
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return self.path

    @staticmethod
    def _new_session_id() -> str:
        prefix = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"{prefix}-{uuid.uuid4().hex[:8]}"
