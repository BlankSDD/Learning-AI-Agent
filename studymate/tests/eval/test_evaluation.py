import json

from studymate.agent import AgentResult
from studymate.evaluation import (
    EvaluationCase,
    EvaluationRunner,
    load_evaluation_dataset,
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
    assert cases[0].should_abstain is False


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
