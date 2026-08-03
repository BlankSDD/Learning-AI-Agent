import pytest
from pydantic import ValidationError

from studymate.models import Answer, Citation, Intent, IntentKind


def test_answer_accepts_valid_structured_output():
    answer = Answer(
        answer="RAG 先检索资料，再让模型基于资料回答。",
        citations=[
            Citation(
                chunk_id="chunk-1",
                path="rag.md",
                title="RAG",
                start_line=1,
                end_line=4,
                quote="先检索相关资料。",
            )
        ],
        confidence=0.9,
        need_more_context=False,
        next_steps=["继续学习向量检索"],
    )

    assert answer.confidence == 0.9
    assert answer.citations[0].path == "rag.md"


def test_answer_rejects_confidence_outside_range():
    with pytest.raises(ValidationError):
        Answer(
            answer="回答",
            citations=[],
            confidence=1.5,
            need_more_context=False,
            next_steps=[],
        )


def test_intent_supports_question_goal_keyword_and_command():
    assert Intent(kind=IntentKind.QUESTION, text="什么是 RAG？").kind == IntentKind.QUESTION
    assert Intent(kind=IntentKind.GOAL, text="从零学习 Agent").kind == IntentKind.GOAL
    assert Intent(kind=IntentKind.KEYWORD, text="LangGraph").kind == IntentKind.KEYWORD
    assert Intent(kind=IntentKind.COMMAND, text="/reset", command="reset").command == "reset"

