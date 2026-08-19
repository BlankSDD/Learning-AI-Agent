import json

from studymate.trace import AgentTrace, AgentTraceStep, TraceStore


def test_trace_store_writes_a_question_answer_and_agent_trace(tmp_path):
    trace = AgentTrace()
    trace.add_step(
        AgentTraceStep(
            step=1,
            mode="tool_decision",
            available_tools=["search_knowledge", "open_document"],
            requested_tools=[{"name": "search_knowledge", "arguments": {"query": "RAG"}}],
            executions=[
                {
                    "name": "search_knowledge",
                    "status": "ok",
                    "evidence_count": 2,
                }
            ],
        )
    )
    trace.finish("final_answer")
    store = TraceStore(tmp_path, session_id="test-session")

    path = store.append_turn(
        user_input="什么是 RAG？",
        answer={"answer": "RAG retrieves evidence.", "citations": []},
        trace=trace,
    )

    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["session_id"] == "test-session"
    assert record["user_input"] == "什么是 RAG？"
    assert record["trace"]["stop_reason"] == "final_answer"
    assert record["trace"]["steps"][0]["executions"][0]["evidence_count"] == 2


def test_agent_trace_formats_a_readable_last_run_summary():
    trace = AgentTrace()
    trace.add_step(
        AgentTraceStep(
            step=1,
            mode="tool_decision",
            available_tools=["search_knowledge"],
            requested_tools=[{"name": "search_knowledge", "arguments": {"query": "RAG"}}],
            executions=[
                {
                    "name": "search_knowledge",
                    "status": "ok",
                    "evidence_count": 1,
                    "query": "Agent Loop 如何运行流程",
                    "rewritten_query": "agent loop",
                    "ranking": [
                        {
                            "rank": 1,
                            "path": "rag.md",
                            "start_line": 1,
                            "end_line": 3,
                            "score": 2.5,
                            "matched_terms": ["rag"],
                        }
                    ],
                }
            ],
        )
    )
    trace.finish("final_answer")

    summary = trace.format_summary()

    assert "停止原因：final_answer" in summary
    assert "search_knowledge" in summary
    assert "rewritten_query: agent loop" in summary
    assert "证据片段：1" in summary
    assert "检索排名" in summary
    assert "1. rag.md:1-3 score=2.500000 terms=rag" in summary
