from studymate.comparison import format_search_comparison


def test_format_search_comparison_shows_rewrite_and_topics():
    record = {
        "query": "agentloop 和 agent runtime 有什么区别？",
        "rewritten_query": "agent loop agent runtime",
        "comparison_topics": ["agent loop", "agent runtime"],
        "backends": {},
        "score_types": {},
        "errors": {},
    }

    output = format_search_comparison(record)

    assert "Rewritten query: agent loop agent runtime" in output
    assert "Comparison topics: agent loop | agent runtime" in output
    assert "results interleaved by topic" in output
