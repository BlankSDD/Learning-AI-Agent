from pathlib import Path

from studymate.cli import build_parser


def test_chat_and_eval_default_to_sqlite_search():
    parser = build_parser()

    chat_args = parser.parse_args(["chat"])
    eval_args = parser.parse_args(["eval"])

    assert chat_args.search_backend == "sqlite"
    assert eval_args.search_backend == "sqlite"
    assert chat_args.search_db == Path("data/studymate-search.sqlite3")
    assert eval_args.search_db == Path("data/studymate-search.sqlite3")


def test_build_index_command_uses_default_knowledge_and_database_paths():
    args = build_parser().parse_args(["build-index"])

    assert args.command == "build-index"
    assert args.knowledge == Path("knowledge")
    assert args.search_db == Path("data/studymate-search.sqlite3")
