import json
from pathlib import Path

from studymate.agent import AgentResult
from studymate.evaluation import (
    EvaluationCase,
    EvaluationRunner,
    load_evaluation_dataset,
    select_evaluation_cases,
)
from studymate.models import Answer, Citation, Chunk, SearchResult
from studymate.trace import AgentTrace, AgentTraceStep


class StubAgent:
    def __init__(self, result):
        self.result = result
        self.inputs = []

    def run(self, *, user_input, history):
        self.inputs.append((user_input, history))
        return self.result


class SequenceAgent:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.inputs = []

    def run(self, *, user_input, history):
        self.inputs.append((user_input, history))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class StatusError(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class BodyCodeError(Exception):
    def __init__(self, code):
        super().__init__("temporary gateway failure")
        self.body = {"code": code}


def make_result(*, stop_reason="final_answer", need_more_context=False):
    chunk = Chunk(
        id="chunk-1",
        document_id="doc-1",
        path="claude-code/07-agent-sdk/mcp.md",
        title="MCP",
        text="MCP connects an agent to external tools.",
        start_line=1,
        end_line=1,
    )
    trace = AgentTrace()
    step = AgentTraceStep(
        step=1,
        mode="tool_decision",
        available_tools=["search_knowledge"],
        requested_tools=[{"name": "search_knowledge", "arguments": {}}],
        executions=[{"name": "search_knowledge", "status": "ok", "evidence_count": 1}],
    )
    trace.add_step(step)
    trace.finish(stop_reason)
    answer = Answer(
        answer="MCP connects an agent to external tools.",
        citations=[
            Citation(
                chunk_id=chunk.id,
                path=chunk.path,
                title=chunk.title,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                quote=chunk.text,
            )
        ]
        if not need_more_context
        else [],
        confidence=0.9 if not need_more_context else 0.0,
        need_more_context=need_more_context,
        next_steps=[],
    )
    return AgentResult(
        answer=answer,
        retrieved=[SearchResult(chunk=chunk, score=1.0, matched_terms=["mcp"])],
        steps=1,
        tool_calls=["search_knowledge"],
        trace=trace,
    )


def test_load_evaluation_dataset_supports_optional_expectations(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "case-1",
                "input": "What is MCP?",
                "expected_sources": ["mcp.md"],
                "acceptable_sources": ["glossary.md"],
                "required_terms": ["agent"],
                "expected_tools": ["search_knowledge"],
                "expected_stop_reason": "final_answer",
                "should_abstain": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    cases = load_evaluation_dataset(path)

    assert cases[0].expected_tools == ("search_knowledge",)
    assert cases[0].acceptable_sources == ("glossary.md",)
    assert cases[0].should_abstain is False


def test_q001_accepts_equivalent_mcp_definition_sources():
    cases = load_evaluation_dataset(Path(__file__).with_name("questions.jsonl"))
    q001 = next(case for case in cases if case.id == "q001")

    assert q001.expected_sources == ()
    assert q001.acceptable_sources == (
        "claude-code/99-other/glossary.md",
        "ai-agent/tool-calling-vs-mcp.md",
        "claude-code/04-agent-development/mcp-quickstart.md",
        "claude-code/04-agent-development/mcp.md",
    )
    assert q001.expected_tools == ("search_knowledge",)


def test_evaluation_accepts_one_of_alternative_sources():
    case = EvaluationCase(
        id="mcp-alternatives",
        input="What is MCP?",
        acceptable_sources=("glossary.md", "mcp.md"),
        expected_tools=("search_knowledge",),
    )

    result = EvaluationRunner(StubAgent(make_result())).run_case(case)

    assert result.passed is True
    assert result.checks["retrieval_matches"] is True
    assert result.checks["citations_match"] is True
    assert result.metrics is not None
    assert result.metrics.hit_at_k is True
    assert result.metrics.recall_at_k == 1.0
    assert result.metrics.citation_coverage == 1.0


def test_evaluation_fails_when_no_alternative_source_is_hit():
    case = EvaluationCase(
        id="mcp-alternatives-miss",
        input="What is MCP?",
        acceptable_sources=("glossary.md", "other.md"),
    )

    result = EvaluationRunner(StubAgent(make_result())).run_case(case)

    assert result.passed is False
    assert result.checks["retrieval_matches"] is False
    assert result.checks["citations_match"] is False


def test_evaluation_keeps_strict_expected_sources_semantics():
    case = EvaluationCase(
        id="mcp-strict",
        input="What is MCP?",
        expected_sources=("mcp.md", "another.md"),
    )

    result = EvaluationRunner(StubAgent(make_result())).run_case(case)

    assert result.passed is False
    assert result.metrics is not None
    assert result.metrics.recall_at_k == 0.5


def test_evaluation_passes_when_answer_and_loop_are_grounded():
    case = EvaluationCase(
        id="mcp-1",
        input="What is MCP?",
        expected_sources=("mcp.md",),
        required_terms=("agent",),
        expected_tools=("search_knowledge",),
        expected_stop_reason="final_answer",
        should_abstain=False,
    )

    result = EvaluationRunner(StubAgent(make_result())).run_case(case)

    assert result.passed is True
    assert result.checks["loop_completed"] is True
    assert result.checks["stop_reason_matches"] is True
    assert result.checks["tool_calls_match"] is True
    assert result.checks["citations_match"] is True


def test_evaluation_fails_when_agent_hits_step_limit():
    case = EvaluationCase(
        id="loop-1",
        input="Keep working",
        expected_stop_reason="final_answer",
    )

    result = EvaluationRunner(StubAgent(make_result(stop_reason="max_steps"))).run_case(case)

    assert result.passed is False
    assert result.checks["loop_completed"] is False
    assert result.checks["stop_reason_matches"] is False


def test_evaluation_can_require_abstention():
    case = EvaluationCase(
        id="unknown-1",
        input="Unknown",
        expected_sources=(),
        expected_stop_reason="empty_search",
        should_abstain=True,
    )
    empty_result = make_result(stop_reason="empty_search", need_more_context=True)
    empty_result.retrieved = []
    empty_result.answer.citations = []
    result = EvaluationRunner(StubAgent(empty_result)).run_case(case)

    assert result.passed is True
    assert result.checks["retrieval_matches"] is True
    assert result.checks["abstention_matches"] is True


def test_evaluation_reports_the_full_trace():
    case = EvaluationCase(id="trace-1", input="What is MCP?")

    result = EvaluationRunner(StubAgent(make_result())).run_case(case)

    assert result.trace is not None
    assert result.trace["stop_reason"] == "final_answer"
    assert result.trace["steps"][0]["executions"][0]["name"] == "search_knowledge"


def test_select_evaluation_cases_filters_and_limits_in_dataset_order():
    cases = [
        EvaluationCase(
            id="q001",
            input="one",
            expected_sources=("mcp.md",),
        ),
        EvaluationCase(
            id="q002",
            input="two",
            expected_sources=("mcp.md",),
        ),
        EvaluationCase(id="q003", input="three"),
    ]

    selected = select_evaluation_cases(
        cases,
        case_ids=["q003", "q001"],
        limit=1,
    )

    assert [case.id for case in selected] == ["q001"]


def test_select_evaluation_cases_rejects_unknown_id():
    cases = [EvaluationCase(id="q001", input="one")]

    try:
        select_evaluation_cases(cases, case_ids=["q404"])
    except ValueError as exc:
        assert "q404" in str(exc)
    else:
        raise AssertionError("unknown case id should fail fast")


def test_evaluation_retries_transient_error_and_delays_between_cases():
    agent = SequenceAgent(
        [
            ConnectionError("Connection error."),
            make_result(),
            make_result(),
        ]
    )
    sleeps = []
    runner = EvaluationRunner(
        agent,
        retries=1,
        retry_delay_seconds=5,
        case_delay_seconds=2,
        sleep_fn=sleeps.append,
    )
    cases = [
        EvaluationCase(
            id="q001",
            input="one",
            expected_sources=("mcp.md",),
        ),
        EvaluationCase(
            id="q002",
            input="two",
            expected_sources=("mcp.md",),
        ),
    ]

    report = runner.run(cases)

    assert report.passed == 2
    assert [result.attempts for result in report.results] == [2, 1]
    assert sleeps == [5, 2]


def test_evaluation_retries_rate_limit_but_not_forbidden_error():
    retry_agent = SequenceAgent([StatusError(429), make_result()])
    retry_sleeps = []
    retry_result = EvaluationRunner(
        retry_agent,
        retries=1,
        retry_delay_seconds=1,
        sleep_fn=retry_sleeps.append,
    ).run_case(
        EvaluationCase(
            id="rate-limit",
            input="one",
            expected_sources=("mcp.md",),
        )
    )

    forbidden_agent = SequenceAgent([StatusError(403), make_result()])
    forbidden_sleeps = []
    forbidden_result = EvaluationRunner(
        forbidden_agent,
        retries=1,
        retry_delay_seconds=1,
        sleep_fn=forbidden_sleeps.append,
    ).run_case(
        EvaluationCase(
            id="forbidden",
            input="two",
            expected_sources=("mcp.md",),
        )
    )

    assert retry_result.passed is True
    assert retry_result.attempts == 2
    assert retry_sleeps == [1]
    assert forbidden_result.passed is False
    assert forbidden_result.attempts == 1
    assert forbidden_sleeps == []


def test_evaluation_retries_temporary_model_channel_failure():
    retry_agent = SequenceAgent([
        BodyCodeError("get_channel_failed"),
        make_result(),
    ])
    sleeps = []

    result = EvaluationRunner(
        retry_agent,
        retries=1,
        retry_delay_seconds=2,
        sleep_fn=sleeps.append,
    ).run_case(
        EvaluationCase(
            id="channel-retry",
            input="one",
            expected_sources=("mcp.md",),
        )
    )

    assert result.passed is True
    assert result.attempts == 2
    assert sleeps == [2]
