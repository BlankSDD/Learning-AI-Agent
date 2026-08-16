from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent import AgentResult, AgentRunner


class EvaluationDatasetError(ValueError):
    """Raised when an evaluation JSONL file is invalid."""


@dataclass(frozen=True)
class EvaluationCase:
    id: str
    input: str
    intent: str | None = None
    expected_sources: tuple[str, ...] = ()
    required_terms: tuple[str, ...] = ()
    expected_tools: tuple[str, ...] = ()
    expected_stop_reason: str | None = None
    should_abstain: bool | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any], *, line_number: int) -> "EvaluationCase":
        case_id = value.get("id")
        user_input = value.get("input")
        if not isinstance(case_id, str) or not case_id.strip():
            raise EvaluationDatasetError(f"line {line_number}: id must be a non-empty string")
        if not isinstance(user_input, str) or not user_input.strip():
            raise EvaluationDatasetError(
                f"line {line_number}: input must be a non-empty string"
            )

        intent = value.get("intent")
        if intent is not None and (not isinstance(intent, str) or not intent.strip()):
            raise EvaluationDatasetError(f"line {line_number}: intent must be a string")

        return cls(
            id=case_id.strip(),
            input=user_input.strip(),
            intent=intent.strip() if isinstance(intent, str) else None,
            expected_sources=_string_tuple(value.get("expected_sources", []), "expected_sources", line_number),
            required_terms=_string_tuple(value.get("required_terms", []), "required_terms", line_number),
            expected_tools=_string_tuple(value.get("expected_tools", []), "expected_tools", line_number),
            expected_stop_reason=_optional_string(
                value.get("expected_stop_reason"), "expected_stop_reason", line_number
            ),
            should_abstain=_optional_bool(value.get("should_abstain"), line_number),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "input": self.input,
            "intent": self.intent,
            "expected_sources": list(self.expected_sources),
            "required_terms": list(self.required_terms),
            "expected_tools": list(self.expected_tools),
            "expected_stop_reason": self.expected_stop_reason,
            "should_abstain": self.should_abstain,
        }


@dataclass
class EvaluationCaseResult:
    case: EvaluationCase
    passed: bool
    checks: dict[str, bool]
    stop_reason: str | None = None
    steps: int = 0
    tool_calls: list[str] = field(default_factory=list)
    duration_ms: int | None = None
    answer: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    retrieved_sources: list[str] = field(default_factory=list)
    trace: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.case.id,
            "input": self.case.input,
            "passed": self.passed,
            "checks": self.checks,
            "stop_reason": self.stop_reason,
            "steps": self.steps,
            "tool_calls": self.tool_calls,
            "duration_ms": self.duration_ms,
            "answer": self.answer,
            "citations": self.citations,
            "retrieved_sources": self.retrieved_sources,
            "trace": self.trace,
            "error": self.error,
        }


@dataclass
class EvaluationReport:
    dataset: str
    results: list[EvaluationCaseResult]
    duration_ms: int
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    )

    @property
    def passed(self) -> int:
        return sum(result.passed for result in self.results)

    @property
    def failed(self) -> int:
        return len(self.results) - self.passed

    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return self.passed / len(self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "generated_at": self.generated_at,
            "dataset": self.dataset,
            "duration_ms": self.duration_ms,
            "summary": {
                "total": len(self.results),
                "passed": self.passed,
                "failed": self.failed,
                "pass_rate": self.pass_rate,
            },
            "results": [result.to_dict() for result in self.results],
        }

    def write_json(self, path: Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return output_path

    def format_summary(self) -> str:
        lines = [
            f"Evaluation: {self.passed}/{len(self.results)} passed "
            f"({self.pass_rate:.1%}), {self.duration_ms} ms",
        ]
        for result in self.results:
            status = "PASS" if result.passed else "FAIL"
            lines.append(
                f"- {result.case.id}: {status} "
                f"stop={result.stop_reason or 'error'} "
                f"steps={result.steps} tools={len(result.tool_calls)}"
            )
            if result.error:
                lines.append(f"  error: {result.error}")
            failed_checks = [name for name, passed in result.checks.items() if not passed]
            if failed_checks:
                lines.append(f"  failed_checks: {', '.join(failed_checks)}")
        return "\n".join(lines)


class EvaluationRunner:
    """Runs isolated Agent tasks and evaluates their observable behavior."""

    def __init__(self, agent: AgentRunner):
        self.agent = agent

    def run(self, cases: list[EvaluationCase], *, dataset: str = "") -> EvaluationReport:
        started_at = time.monotonic()
        results = [self.run_case(case) for case in cases]
        return EvaluationReport(
            dataset=dataset,
            results=results,
            duration_ms=int((time.monotonic() - started_at) * 1000),
        )

    def run_case(self, case: EvaluationCase) -> EvaluationCaseResult:
        prompt = f"[{case.intent}] {case.input}" if case.intent else case.input
        started_at = time.monotonic()
        try:
            result = self.agent.run(user_input=prompt, history=[])
        except Exception as exc:
            return EvaluationCaseResult(
                case=case,
                passed=False,
                checks={
                    "answer_present": False,
                    "loop_completed": False,
                    "stop_reason_matches": False,
                    "tool_success": False,
                    "tool_calls_match": False,
                    "retrieval_matches": False,
                    "citations_match": False,
                    "required_terms": False,
                    "abstention_matches": False,
                },
                duration_ms=int((time.monotonic() - started_at) * 1000),
                error=f"{type(exc).__name__}: {exc}",
            )
        return self._evaluate_result(case, result)

    @staticmethod
    def _evaluate_result(case: EvaluationCase, result: AgentResult) -> EvaluationCaseResult:
        trace = result.trace
        answer = result.answer
        retrieved_sources = sorted({item.chunk.path for item in result.retrieved})
        citation_dicts = [citation.model_dump(mode="json") for citation in answer.citations]
        citation_sources = [citation.path for citation in answer.citations]

        checks = {
            "answer_present": bool(answer.answer.strip()),
            "loop_completed": trace.stop_reason in {"final_answer", "empty_search"},
            "stop_reason_matches": (
                case.expected_stop_reason is None
                or trace.stop_reason == case.expected_stop_reason
            ),
            "tool_success": all(
                execution.get("status") == "ok"
                for step in trace.steps
                for execution in step.executions
            ),
            "tool_calls_match": _sequence_contains(
                result.tool_calls, case.expected_tools
            ),
            "retrieval_matches": _expected_sources_match(
                case.expected_sources, retrieved_sources
            ),
            "citations_match": _expected_sources_match(
                case.expected_sources, citation_sources
            ),
            "required_terms": _contains_all(answer.answer, case.required_terms),
            "abstention_matches": (
                case.should_abstain is None
                or answer.need_more_context == case.should_abstain
            ),
        }
        passed = all(checks.values())
        return EvaluationCaseResult(
            case=case,
            passed=passed,
            checks=checks,
            stop_reason=trace.stop_reason,
            steps=result.steps,
            tool_calls=list(result.tool_calls),
            duration_ms=trace.duration_ms,
            answer=answer.answer,
            citations=citation_dicts,
            retrieved_sources=retrieved_sources,
            trace=trace.to_dict(),
        )


def load_evaluation_dataset(path: Path) -> list[EvaluationCase]:
    dataset_path = Path(path)
    if not dataset_path.is_file():
        raise EvaluationDatasetError(f"Evaluation dataset does not exist: {dataset_path}")

    cases: list[EvaluationCase] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(
        dataset_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvaluationDatasetError(
                f"line {line_number}: invalid JSON: {exc.msg}"
            ) from exc
        if not isinstance(value, dict):
            raise EvaluationDatasetError(f"line {line_number}: each case must be an object")
        case = EvaluationCase.from_mapping(value, line_number=line_number)
        if case.id in seen_ids:
            raise EvaluationDatasetError(f"line {line_number}: duplicate id: {case.id}")
        seen_ids.add(case.id)
        cases.append(case)
    return cases


def _string_tuple(value: Any, field_name: str, line_number: int) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise EvaluationDatasetError(f"line {line_number}: {field_name} must be a string list")
    return tuple(item.strip() for item in value if item.strip())


def _optional_string(value: Any, field_name: str, line_number: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise EvaluationDatasetError(f"line {line_number}: {field_name} must be a string")
    return value.strip()


def _optional_bool(value: Any, line_number: int) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise EvaluationDatasetError(f"line {line_number}: should_abstain must be boolean")
    return value


def _expected_sources_match(expected: tuple[str, ...], actual: list[str]) -> bool:
    if not expected:
        return not actual
    return all(any(_source_matches(item, candidate) for candidate in actual) for item in expected)


def _source_matches(expected: str, actual: str) -> bool:
    expected_path = expected.replace("\\", "/").strip("/").casefold()
    actual_path = actual.replace("\\", "/").strip("/").casefold()
    return actual_path == expected_path or actual_path.endswith("/" + expected_path)


def _contains_all(text: str, terms: tuple[str, ...]) -> bool:
    folded = text.casefold()
    return all(term.casefold() in folded for term in terms)


def _sequence_contains(actual: list[str], expected: tuple[str, ...]) -> bool:
    if not expected:
        return True
    expected_index = 0
    for item in actual:
        if item == expected[expected_index]:
            expected_index += 1
            if expected_index == len(expected):
                return True
    return False
