from studymate.input import classify_input, parse_command
from studymate.models import IntentKind


def test_classify_question():
    intent = classify_input("RAG 和微调有什么区别？")

    assert intent.kind == IntentKind.QUESTION


def test_classify_learning_goal():
    intent = classify_input("我想从零学习 AI Agent，一个月后完成项目")

    assert intent.kind == IntentKind.GOAL


def test_classify_keyword():
    intent = classify_input("LangGraph")

    assert intent.kind == IntentKind.KEYWORD


def test_parse_supported_command():
    assert parse_command("/sources").name == "sources"
    assert parse_command("/trace").name == "trace"
    assert parse_command("/reset").name == "reset"
    assert parse_command("/update claude-code").args == ["claude-code"]
    assert parse_command("/quit").name == "quit"


def test_unknown_command_is_rejected():
    command = parse_command("/unknown")

    assert command.is_valid is False
