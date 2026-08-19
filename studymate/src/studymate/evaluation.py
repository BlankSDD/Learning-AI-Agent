from __future__ import annotations

import json
import re
import time
from collections.abc import Iterable
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
    acceptable_sources: tuple[str, ...] = ()
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
            acceptable_sources=_string_tuple(
                value.get("acceptable_sources", []), "acceptable_sources", line_number
            ),
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
            "acceptable_sources": list(self.acceptable_sources),
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
    attempts: int = 1
    metrics: "EvaluationCaseMetrics | None" = None

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
            "attempts": self.attempts,
            "metrics": self.metrics.to_dict() if self.metrics is not None else None,
        }


@dataclass(frozen=True)
class EvaluationCaseMetrics:
    """Retrieval and answer quality metrics for one evaluation case."""

    retrieval_k: int
    hit_at_k: bool
    recall_at_k: float
    precision_at_k: float
    mrr: float
    citation_accuracy: float
    citation_coverage: float
    abstained: bool
    abstention_correct: bool | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "retrieval_k": self.retrieval_k,
            "hit_at_k": self.hit_at_k,
            "recall_at_k": self.recall_at_k,
            "precision_at_k": self.precision_at_k,
            "mrr": self.mrr,
            "citation_accuracy": self.citation_accuracy,
            "citation_coverage": self.citation_coverage,
            "abstained": self.abstained,
            "abstention_correct": self.abstention_correct,
        }


@dataclass
class EvaluationReport:
    dataset: str
    results: list[EvaluationCaseResult]
    duration_ms: int
    retrieval_k: int = 5
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

    @property
    def metrics(self) -> dict[str, Any]:
        evaluated = [result for result in self.results if result.metrics is not None]
        positive = [
            result
            for result in evaluated
            if result.case.expected_sources or result.case.acceptable_sources
        ]
        labeled_abstention = [
            result
            for result in evaluated
            if result.metrics is not None and result.metrics.abstention_correct is not None
        ]
        return {
            "retrieval": {
                "k": self.retrieval_k,
                "evaluated_cases": len(evaluated),
                "positive_cases": len(positive),
                "hit_at_k": _mean(
                    float(result.metrics.hit_at_k) for result in evaluated
                ),
                "recall_at_k": _mean(
                    result.metrics.recall_at_k for result in positive
                ),
                "precision_at_k": _mean(
                    result.metrics.precision_at_k for result in evaluated
                ),
                "mrr": _mean(result.metrics.mrr for result in positive),
            },
            "citation": {
                "accuracy": _mean(
                    result.metrics.citation_accuracy for result in evaluated
                ),
                "coverage": _mean(
                    result.metrics.citation_coverage for result in positive
                ),
            },
            "abstention": {
                "rate": _mean(
                    float(result.metrics.abstained) for result in evaluated
                ),
                "accuracy": _mean(
                    float(result.metrics.abstention_correct)
                    for result in labeled_abstention
                ),
                "labeled_cases": len(labeled_abstention),
            },
            "latency": {
                "average_ms": _mean(
                    float(result.duration_ms)
                    for result in self.results
                    if result.duration_ms is not None
                )
            },
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "generated_at": self.generated_at,
            "dataset": self.dataset,
            "duration_ms": self.duration_ms,
            "summary": {
                "total": len(self.results),
                "passed": self.passed,
                "failed": self.failed,
                "pass_rate": self.pass_rate,
                "metrics": self.metrics,
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
        retrieval = self.metrics["retrieval"]
        lines.append(
            f"Retrieval@{retrieval['k']}: "
            f"Hit={retrieval['hit_at_k']:.1%} "
            f"Recall={retrieval['recall_at_k']:.1%} "
            f"Precision={retrieval['precision_at_k']:.1%} "
            f"MRR={retrieval['mrr']:.3f}"
        )
        citation = self.metrics["citation"]
        abstention = self.metrics["abstention"]
        latency = self.metrics["latency"]
        lines.append(
            f"Citation: accuracy={citation['accuracy']:.1%} "
            f"coverage={citation['coverage']:.1%}; "
            f"abstention_rate={abstention['rate']:.1%} "
            f"abstention_accuracy={abstention['accuracy']:.1%}; "
            f"average_latency={latency['average_ms']:.0f} ms"
        )
        for result in self.results:
            status = "PASS" if result.passed else "FAIL"
            lines.append(
                f"- {result.case.id}: {status} "
                f"stop={result.stop_reason or 'error'} "
                f"attempts={result.attempts} "
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

    def __init__(
        self,
        agent: AgentRunner,
        retrieval_k: int = 5,
        *,
        case_delay_seconds: float = 0.0,
        retries: int = 0,
        retry_delay_seconds: float = 3.0,
        sleep_fn: Any = time.sleep,
    ):
        if retrieval_k <= 0:
            raise ValueError("retrieval_k must be greater than zero")
        if case_delay_seconds < 0:
            raise ValueError("case_delay_seconds must not be negative")
        if retries < 0:
            raise ValueError("retries must not be negative")
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must not be negative")
        self.agent = agent
        self.retrieval_k = retrieval_k
        self.case_delay_seconds = case_delay_seconds
        self.retries = retries
        self.retry_delay_seconds = retry_delay_seconds
        self.sleep_fn = sleep_fn

    def run(self, cases: list[EvaluationCase], *, dataset: str = "") -> EvaluationReport:
        started_at = time.monotonic()
        results: list[EvaluationCaseResult] = []
        for index, case in enumerate(cases):
            if index and self.case_delay_seconds:
                self.sleep_fn(self.case_delay_seconds)
            results.append(self.run_case(case))
        return EvaluationReport(
            dataset=dataset,
            results=results,
            duration_ms=int((time.monotonic() - started_at) * 1000),
            retrieval_k=self.retrieval_k,
        )

    def run_case(self, case: EvaluationCase) -> EvaluationCaseResult:
        prompt = f"[{case.intent}] {case.input}" if case.intent else case.input
        started_at = time.monotonic()
        attempts = 0
        while True:
            attempts += 1
            try:
                result = self.agent.run(user_input=prompt, history=[])
            except Exception as exc:
                should_retry = _is_retryable_exception(exc) and attempts <= self.retries
                if should_retry:
                    if self.retry_delay_seconds:
                        self.sleep_fn(self.retry_delay_seconds)
                    continue
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
                    attempts=attempts,
                )
            evaluated = self._evaluate_result(case, result, retrieval_k=self.retrieval_k)
            evaluated.attempts = attempts
            return evaluated

    @staticmethod
    def _evaluate_result(
        case: EvaluationCase,
        result: AgentResult,
        *,
        retrieval_k: int = 5,
    ) -> EvaluationCaseResult:
        trace = result.trace
        answer = result.answer
        retrieved_sources = _unique_source_paths(result.retrieved)
        citation_dicts = [citation.model_dump(mode="json") for citation in answer.citations]
        citation_sources = [citation.path for citation in answer.citations]
        metrics = _calculate_case_metrics(
            case=case,
            retrieved_sources=retrieved_sources,
            citation_sources=citation_sources,
            need_more_context=answer.need_more_context,
            retrieval_k=retrieval_k,
        )

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
                case.expected_sources, case.acceptable_sources, retrieved_sources
            ),
            "citations_match": _expected_sources_match(
                case.expected_sources, case.acceptable_sources, citation_sources
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
            metrics=metrics,
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


def select_evaluation_cases(
    cases: list[EvaluationCase],
    *,
    case_ids: list[str] | None = None,
    limit: int | None = None,
) -> list[EvaluationCase]:
    """Select a stable subset while preserving dataset order."""
    if limit is not None and limit <= 0:
        raise ValueError("limit must be greater than zero")

    selected = cases
    if case_ids:
        requested = {case_id.strip() for case_id in case_ids if case_id.strip()}
        known = {case.id for case in cases}
        missing = sorted(requested - known)
        if missing:
            raise ValueError(f"evaluation case id not found: {', '.join(missing)}")
        selected = [case for case in cases if case.id in requested]

    if limit is not None:
        selected = selected[:limit]
    return selected


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


def _expected_sources_match(
    expected: tuple[str, ...], acceptable: tuple[str, ...], actual: list[str]
) -> bool:
    if not expected and not acceptable:
        return not actual
    strict_match = all(
        any(_source_matches(item, candidate) for candidate in actual) for item in expected
    )
    alternative_match = not acceptable or any(
        _source_matches(item, candidate)
        for item in acceptable
        for candidate in actual
    )
    return strict_match and alternative_match


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


def _unique_source_paths(items: list[Any]) -> list[str]:
    """Keep first-seen source order so ranking metrics remain meaningful."""
    paths: list[str] = []
    seen: set[str] = set()
    for item in items:
        path = item.chunk.path
        if path not in seen:
            paths.append(path)
            seen.add(path)
    return paths


def _calculate_case_metrics(
    *,
    case: EvaluationCase,
    retrieved_sources: list[str],
    citation_sources: list[str],
    need_more_context: bool,
    retrieval_k: int,
) -> EvaluationCaseMetrics:
    top_sources = retrieved_sources[:retrieval_k]
    expected_sources = case.expected_sources
    acceptable_sources = case.acceptable_sources

    if expected_sources or acceptable_sources:
        matched_strict = _count_matching_expected(expected_sources, top_sources)
        matched_alternative = bool(
            acceptable_sources
            and any(
                _source_matches(item, candidate)
                for item in acceptable_sources
                for candidate in top_sources
            )
        )
        expected_slot_count = len(expected_sources) + bool(acceptable_sources)
        matched_retrieved = matched_strict + int(matched_alternative)
        hit_at_k = matched_retrieved > 0
        recall_at_k = matched_retrieved / expected_slot_count
        precision_at_k = (
            _count_relevant_sources(
                top_sources,
                expected_sources + acceptable_sources,
            )
            / len(top_sources)
            if top_sources
            else 0.0
        )
        first_match = next(
            (
                index + 1
                for index, source in enumerate(top_sources)
                if _matches_any_expected(
                    source, expected_sources + acceptable_sources
                )
            ),
            None,
        )
        mrr = 1.0 / first_match if first_match is not None else 0.0
        citation_accuracy = _citation_accuracy(
            citation_sources, expected_sources, acceptable_sources
        )
        citation_coverage = _coverage(
            citation_sources, expected_sources, acceptable_sources
        )
    else:
        no_retrieval = not top_sources
        hit_at_k = no_retrieval
        recall_at_k = 1.0 if no_retrieval else 0.0
        precision_at_k = 1.0 if no_retrieval else 0.0
        mrr = 0.0
        citation_accuracy = 1.0 if not citation_sources else 0.0
        citation_coverage = 1.0 if not citation_sources else 0.0

    abstention_correct = (
        None
        if case.should_abstain is None
        else need_more_context == case.should_abstain
    )
    return EvaluationCaseMetrics(
        retrieval_k=retrieval_k,
        hit_at_k=hit_at_k,
        recall_at_k=recall_at_k,
        precision_at_k=precision_at_k,
        mrr=mrr,
        citation_accuracy=citation_accuracy,
        citation_coverage=citation_coverage,
        abstained=need_more_context,
        abstention_correct=abstention_correct,
    )


def _count_matching_expected(expected: tuple[str, ...], actual: list[str]) -> int:
    return sum(
        1 for expected_source in expected if _matches_any_expected(expected_source, actual)
    )


def _count_relevant_sources(
    actual: list[str], expected: tuple[str, ...]
) -> int:
    return sum(1 for source in actual if _matches_any_expected(source, expected))


def _matches_any_expected(expected: str, actual: list[str] | tuple[str, ...]) -> bool:
    return any(_source_matches(expected, candidate) for candidate in actual)


def _citation_accuracy(
    citations: list[str],
    expected: tuple[str, ...],
    acceptable: tuple[str, ...] = (),
) -> float:
    if not citations:
        return 0.0
    return sum(
        1
        for citation in citations
        if _matches_any_expected(citation, expected + acceptable)
    ) / len(citations)


def _coverage(
    actual: list[str], expected: tuple[str, ...], acceptable: tuple[str, ...] = ()
) -> float:
    if not expected and not acceptable:
        return 1.0 if not actual else 0.0
    strict_matches = _count_matching_expected(expected, actual)
    alternative_match = bool(
        acceptable
        and any(
            _source_matches(item, candidate)
            for item in acceptable
            for candidate in actual
        )
    )
    return (strict_matches + int(alternative_match)) / (
        len(expected) + bool(acceptable)
    )


def _mean(values: Iterable[float]) -> float:
    collected = list(values)
    return sum(collected) / len(collected) if collected else 0.0


def _is_retryable_exception(exc: Exception) -> bool:
    """Retry transient transport, throttling, and temporary server failures only."""
    status = _exception_status_code(exc)
    if status is None:
        status = _status_code_from_text(exc)
    if status is not None:
        return status == 429 or 500 <= status <= 504

    current: BaseException | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, (TimeoutError, ConnectionError)):
            return True
        error_body = getattr(current, "body", None)
        error_code = getattr(current, "code", None)
        text = " ".join(
            str(value)
            for value in (str(current), error_code, error_body)
            if value is not None
        ).casefold()
        if any(
            marker in text
            for marker in (
                "connection error",
                "connection reset",
                "remote disconnected",
                "server disconnected",
                "timed out",
                "timeout",
                "temporarily unavailable",
                "get_channel_failed",
                "no available channel",
                "channel failed",
                "too many requests",
                "rate limit",
            )
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


def _exception_status_code(exc: BaseException) -> int | None:
    for current in _exception_chain(exc):
        for attribute in ("status_code", "status"):
            value = getattr(current, attribute, None)
            if isinstance(value, int):
                return value
    return None


def _status_code_from_text(exc: BaseException) -> int | None:
    for current in _exception_chain(exc):
        match = re.search(
            r"\bHTTP\s*(\d{3})\b|\bstatus(?:_code)?[=: ]+(\d{3})\b",
            str(current),
            re.IGNORECASE,
        )
        if match:
            return int(match.group(1) or match.group(2))
    return None


def _exception_chain(exc: BaseException) -> Iterable[BaseException]:
    current: BaseException | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        yield current
        current = current.__cause__ or current.__context__
