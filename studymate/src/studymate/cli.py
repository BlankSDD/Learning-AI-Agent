from __future__ import annotations

import argparse
from pathlib import Path

from .agent import AgentRunner
from .chat import ChatService
from .comparison import run_search_comparison
from .docs_updater import DocsUpdateError, update_sources
from .evaluation import (
    EvaluationDatasetError,
    EvaluationRunner,
    load_evaluation_dataset,
    select_evaluation_cases,
)
from .ingest import chunk_document, load_documents
from .llm import OpenAIAnswerer
from .search import (
    SQLiteFTS5SearchIndex,
    SQLiteIndexError,
    build_sqlite_search_database,
    build_search_index,
    open_search_index,
)
from .tools import KnowledgeTools, build_knowledge_tool_registry
from .trace import TraceStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="studymate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="scan and validate knowledge files")
    ingest.add_argument("knowledge_dir", type=Path)

    index_builder = subparsers.add_parser(
        "build-index", help="build the persistent SQLite FTS5 knowledge index"
    )
    index_builder.add_argument(
        "--knowledge",
        type=Path,
        default=Path("knowledge"),
        help="knowledge directory used to build the index",
    )
    index_builder.add_argument(
        "--search-db",
        type=Path,
        default=Path("data/studymate-search.sqlite3"),
        help="SQLite FTS5 index file to create or replace",
    )

    evaluation = subparsers.add_parser(
        "eval", help="run the Agent against a JSONL evaluation dataset"
    )
    evaluation.add_argument(
        "--knowledge",
        type=Path,
        default=Path("knowledge"),
        help="knowledge directory used by the Agent",
    )
    evaluation.add_argument(
        "--dataset",
        type=Path,
        default=Path("tests/eval/questions.jsonl"),
        help="JSONL evaluation dataset",
    )
    evaluation.add_argument(
        "--output",
        type=Path,
        default=Path("evals/latest.json"),
        help="JSON report path",
    )
    evaluation.add_argument(
        "--retrieval-k",
        type=int,
        default=5,
        help="K used for retrieval quality metrics",
    )
    evaluation.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="run only this evaluation case; repeat for multiple ids",
    )
    evaluation.add_argument(
        "--limit",
        type=int,
        help="run at most this many cases after --case-id filtering",
    )
    evaluation.add_argument(
        "--delay-seconds",
        type=float,
        default=0.0,
        help="seconds to wait between evaluation cases",
    )
    evaluation.add_argument(
        "--retries",
        type=int,
        default=0,
        help="retries for connection, throttling, and temporary server errors",
    )
    evaluation.add_argument(
        "--retry-delay-seconds",
        type=float,
        default=3.0,
        help="seconds to wait before retrying a transient error",
    )
    _add_search_options(evaluation)

    comparison = subparsers.add_parser(
        "compare-search",
        help="compare memory BM25 and SQLite FTS5/BM25",
    )
    comparison.add_argument(
        "--knowledge",
        type=Path,
        default=Path("knowledge"),
        help="knowledge directory used by the retrieval backends",
    )
    comparison.add_argument(
        "--query",
        action="append",
        required=True,
        help="query to compare; repeat this option for multiple queries",
    )
    comparison.add_argument("--top-k", type=int, default=5)
    comparison.add_argument(
        "--output",
        type=Path,
        default=Path("logs/search-comparison.jsonl"),
        help="JSONL comparison log path",
    )
    comparison.add_argument(
        "--search-db",
        type=Path,
        default=Path("data/studymate-search.sqlite3"),
        help="SQLite FTS5 index file",
    )

    update = subparsers.add_parser("update-docs", help="download configured online documentation")
    update.add_argument(
        "--knowledge",
        type=Path,
        default=Path("knowledge"),
        help="knowledge directory receiving downloaded documents",
    )
    update.add_argument(
        "--config",
        type=Path,
        default=Path("config/docs_sources.json"),
        help="document source configuration JSON",
    )
    update.add_argument(
        "--only",
        nargs="+",
        metavar="SOURCE",
        help="update only the selected source ids",
    )
    update.add_argument("--proxy", help="HTTP proxy, for example 127.0.0.1:7897")
    update.add_argument("--timeout", type=int, default=30)
    update.add_argument("--workers", type=int, default=8)

    chat = subparsers.add_parser("chat", help="start interactive chat")
    chat.add_argument(
        "--knowledge",
        type=Path,
        default=Path("knowledge"),
        help="knowledge directory, scanned recursively",
    )
    chat.add_argument("--top-k", type=int, default=5)
    chat.add_argument(
        "--docs-config",
        type=Path,
        default=Path("config/docs_sources.json"),
        help="document source configuration used by /update",
    )
    chat.add_argument("--proxy", help="HTTP proxy used by /update")
    chat.add_argument(
        "--trace-dir",
        type=Path,
        default=Path("traces"),
        help="directory receiving per-session question/answer/trace JSONL files",
    )
    chat.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs"),
        help="directory used by /output when no file path is supplied",
    )
    _add_search_options(chat)
    return parser


def _add_search_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--search-backend",
        choices=("memory", "sqlite"),
        default="sqlite",
        help="检索后端：memory BM25 风格索引或 sqlite FTS5/BM25",
    )
    parser.add_argument(
        "--search-db",
        type=Path,
        default=Path("data/studymate-search.sqlite3"),
        help="SQLite 检索库文件；仅 search-backend=sqlite 时使用",
    )


def run_ingest(knowledge_dir: Path) -> int:
    documents = load_documents(knowledge_dir)
    chunk_count = sum(len(chunk_document(document)) for document in documents)
    print(f"Loaded {len(documents)} documents and {chunk_count} chunks.")
    for document in documents:
        print(f"- {document.path} ({document.title})")
    return 0


def run_build_index(*, knowledge_dir: Path, search_db: Path) -> int:
    documents = load_documents(knowledge_dir)
    chunks = [chunk for document in documents for chunk in chunk_document(document)]
    if not chunks:
        print(f"No Markdown or TXT knowledge files found in {knowledge_dir}")
        return 1

    try:
        metadata = build_sqlite_search_database(chunks, search_db)
    except Exception as exc:
        print(f"SQLite index build failed: {type(exc).__name__}: {exc}")
        return 1

    print(f"SQLite FTS5 index built: {search_db}")
    print(
        f"Documents: {metadata['document_count']}; "
        f"Chunks: {metadata['chunk_count']}"
    )
    return 0


def run_eval(
    *,
    knowledge_dir: Path,
    dataset_path: Path,
    output_path: Path,
    retrieval_k: int = 5,
    search_backend: str = "sqlite",
    search_db: Path | None = None,
    case_ids: list[str] | None = None,
    limit: int | None = None,
    delay_seconds: float = 0.0,
    retries: int = 0,
    retry_delay_seconds: float = 3.0,
) -> int:
    try:
        cases = load_evaluation_dataset(dataset_path)
    except EvaluationDatasetError as exc:
        print(f"Evaluation dataset error: {exc}")
        return 1
    try:
        cases = select_evaluation_cases(cases, case_ids=case_ids, limit=limit)
    except ValueError as exc:
        print(f"Evaluation selection error: {exc}")
        return 1
    if not cases:
        print("Evaluation dataset is empty.")
        return 1

    try:
        search_index = _open_runtime_search_index(
            knowledge_dir=knowledge_dir,
            search_backend=search_backend,
            search_db=search_db,
        )
    except (SQLiteIndexError, RuntimeError, ValueError) as exc:
        print(f"Search index error: {exc}")
        return 1
    knowledge_tools = KnowledgeTools(knowledge_dir, search_index)
    agent = AgentRunner(
        llm=OpenAIAnswerer(),
        tool_registry=build_knowledge_tool_registry(knowledge_tools),
    )
    try:
        runner = EvaluationRunner(
            agent,
            retrieval_k=retrieval_k,
            case_delay_seconds=delay_seconds,
            retries=retries,
            retry_delay_seconds=retry_delay_seconds,
        )
    except ValueError as exc:
        print(f"Evaluation options error: {exc}")
        return 1
    try:
        report = runner.run(cases, dataset=str(dataset_path))
        try:
            report_path = report.write_json(output_path)
        except OSError as exc:
            print(f"Cannot write evaluation report: {exc}")
            return 1
    finally:
        close = getattr(search_index, "close", None)
        if close is not None:
            close()

    print(report.format_summary())
    print(f"Report: {report_path}")
    return 0 if report.failed == 0 else 1


def _open_runtime_search_index(
    *,
    knowledge_dir: Path,
    search_backend: str,
    search_db: Path | None,
):
    if search_backend == "sqlite":
        return open_search_index(backend="sqlite", database_path=search_db)

    documents = load_documents(knowledge_dir)
    chunks = [chunk for document in documents for chunk in chunk_document(document)]
    if not chunks:
        raise RuntimeError(f"No Markdown or TXT knowledge files found in {knowledge_dir}")
    return build_search_index(chunks, backend=search_backend, database_path=search_db)


def run_update_docs(
    *,
    knowledge_dir: Path,
    config_path: Path,
    only: list[str] | None = None,
    proxy: str | None = None,
    timeout: int = 30,
    workers: int = 8,
) -> int:
    try:
        report = update_sources(
            config_path=config_path,
            knowledge_root=knowledge_dir,
            only=only,
            proxy=proxy,
            timeout=timeout,
            workers=workers,
        )
    except DocsUpdateError as exc:
        print(f"文档更新失败：{exc}")
        return 1
    print(report.format())
    return 1 if report.has_errors else 0


def run_compare_search(
    *,
    knowledge_dir: Path,
    queries: list[str],
    output_path: Path,
    top_k: int,
    search_db: Path,
) -> int:
    documents = load_documents(knowledge_dir)
    chunks = [chunk for document in documents for chunk in chunk_document(document)]
    if not chunks:
        print(f"No Markdown or TXT knowledge files found in {knowledge_dir}")
        return 1

    indexes = {}
    setup_errors: dict[str, str] = {}
    try:
        indexes["memory"] = build_search_index(chunks, backend="memory")
    except Exception as exc:
        setup_errors["memory"] = f"{type(exc).__name__}: {exc}"
    try:
        indexes["sqlite"] = open_search_index(
            backend="sqlite", database_path=search_db
        )
    except Exception as exc:
        setup_errors["sqlite"] = f"{type(exc).__name__}: {exc}"

    try:
        written = run_search_comparison(
            queries=queries,
            indexes=indexes,
            output_path=output_path,
            top_k=top_k,
            setup_errors=setup_errors,
        )
    finally:
        for index in indexes.values():
            close = getattr(index, "close", None)
            if close is not None:
                close()
    print(f"Comparison log: {output_path}")
    return 0 if written else 1


def run_chat(
    knowledge_dir: Path,
    top_k: int,
    docs_config: Path,
    proxy: str | None,
    trace_dir: Path,
    output_dir: Path,
    search_backend: str = "sqlite",
    search_db: Path | None = None,
) -> int:
    try:
        search_index = _open_runtime_search_index(
            knowledge_dir=knowledge_dir,
            search_backend=search_backend,
            search_db=search_db,
        )
    except (SQLiteIndexError, RuntimeError, ValueError) as exc:
        print(f"Search index error: {exc}")
        return 1
    loaded_document_count = (
        search_index.document_count
        if isinstance(search_index, SQLiteFTS5SearchIndex)
        else len(load_documents(knowledge_dir))
    )
    knowledge_tools = KnowledgeTools(knowledge_dir, search_index)
    agent = AgentRunner(
        llm=OpenAIAnswerer(),
        tool_registry=build_knowledge_tool_registry(knowledge_tools),
    )

    def refresh_index() -> None:
        if search_backend == "sqlite":
            raise SQLiteIndexError(
                "知识库已更新，但当前 SQLite 索引未自动重建。请退出后运行 "
                "'python -m studymate build-index'，再重新启动 chat。"
            )
        refreshed_documents = load_documents(knowledge_dir)
        refreshed_chunks = [
            chunk
            for document in refreshed_documents
            for chunk in chunk_document(document)
        ]
        old_index = service.search_index
        close = getattr(old_index, "close", None)
        if close is not None:
            close()
        service.search_index = build_search_index(
            refreshed_chunks,
            backend=search_backend,
            database_path=search_db,
        )
        knowledge_tools.search_index = service.search_index
        service.last_retrieved = []

    def update_handler(only: list[str]) -> str:
        report = update_sources(
            config_path=docs_config,
            knowledge_root=knowledge_dir,
            only=only or None,
            proxy=proxy,
        )
        if report.updated_files:
            if search_backend == "sqlite":
                return (
                    report.format()
                    + "\n知识库文件已更新；SQLite 索引保持不变。请退出后运行 "
                    "'python -m studymate build-index'，再重新启动 chat。"
                )
            refresh_index()
        return report.format()

    service = ChatService(
        search_index=search_index,
        llm=agent.llm,
        agent=agent,
        top_k=top_k,
        update_handler=update_handler,
        trace_store=TraceStore(trace_dir),
        output_dir=output_dir,
    )
    print(
        f"StudyMate loaded {loaded_document_count} documents. "
        f"Search backend: {search_backend}. "
        "Type /help for commands."
    )
    print(f"Trace records: {service.trace_store.path}")
    print(f"Output directory: {output_dir}")
    while True:
        try:
            text = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not text:
            continue
        if text == "/quit":
            return 0

        response = service.handle(text)
        if response.command and response.command.name == "quit":
            return 0
        if response.answer:
            print(f"\nStudyMate> {response.answer.answer}")
            if response.answer.citations:
                print("Sources:")
                for citation in response.answer.citations:
                    print(f"- {citation.path}:{citation.start_line}-{citation.end_line}")
            print()


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "ingest":
        return run_ingest(args.knowledge_dir)
    if args.command == "build-index":
        return run_build_index(
            knowledge_dir=args.knowledge,
            search_db=args.search_db,
        )
    if args.command == "eval":
        return run_eval(
            knowledge_dir=args.knowledge,
            dataset_path=args.dataset,
            output_path=args.output,
            retrieval_k=args.retrieval_k,
            search_backend=args.search_backend,
            search_db=args.search_db,
            case_ids=args.case_ids,
            limit=args.limit,
            delay_seconds=args.delay_seconds,
            retries=args.retries,
            retry_delay_seconds=args.retry_delay_seconds,
        )
    if args.command == "compare-search":
        return run_compare_search(
            knowledge_dir=args.knowledge,
            queries=args.query,
            output_path=args.output,
            top_k=args.top_k,
            search_db=args.search_db,
        )
    if args.command == "update-docs":
        return run_update_docs(
            knowledge_dir=args.knowledge,
            config_path=args.config,
            only=args.only,
            proxy=args.proxy,
            timeout=args.timeout,
            workers=args.workers,
        )
    if args.command == "chat":
        return run_chat(
            args.knowledge,
            args.top_k,
            args.docs_config,
            args.proxy,
            args.trace_dir,
            args.output_dir,
            args.search_backend,
            args.search_db,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
