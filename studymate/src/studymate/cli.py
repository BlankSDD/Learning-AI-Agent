from __future__ import annotations

import argparse
from pathlib import Path

from .agent import AgentRunner
from .chat import ChatService
from .comparison import run_search_comparison
from .docs_updater import DocsUpdateError, update_sources
from .evaluation import EvaluationDatasetError, EvaluationRunner, load_evaluation_dataset
from .ingest import chunk_document, load_documents
from .llm import OpenAIAnswerer
from .search import build_search_index
from .tools import KnowledgeTools, build_knowledge_tool_registry
from .trace import TraceStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="studymate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="scan and validate knowledge files")
    ingest.add_argument("knowledge_dir", type=Path)

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
    _add_search_options(chat)
    return parser


def _add_search_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--search-backend",
        choices=("memory", "sqlite"),
        default="memory",
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


def run_eval(
    *,
    knowledge_dir: Path,
    dataset_path: Path,
    output_path: Path,
    retrieval_k: int = 5,
    search_backend: str = "memory",
    search_db: Path | None = None,
) -> int:
    try:
        cases = load_evaluation_dataset(dataset_path)
    except EvaluationDatasetError as exc:
        print(f"Evaluation dataset error: {exc}")
        return 1
    if not cases:
        print("Evaluation dataset is empty.")
        return 1

    documents = load_documents(knowledge_dir)
    chunks = [chunk for document in documents for chunk in chunk_document(document)]
    if not chunks:
        print(f"No Markdown or TXT knowledge files found in {knowledge_dir}")
        return 1

    search_index = build_search_index(
        chunks,
        backend=search_backend,
        database_path=search_db,
    )
    knowledge_tools = KnowledgeTools(knowledge_dir, search_index)
    agent = AgentRunner(
        llm=OpenAIAnswerer(),
        tool_registry=build_knowledge_tool_registry(knowledge_tools),
    )
    report = EvaluationRunner(agent, retrieval_k=retrieval_k).run(
        cases, dataset=str(dataset_path)
    )
    try:
        report_path = report.write_json(output_path)
    except OSError as exc:
        print(f"Cannot write evaluation report: {exc}")
        return 1

    print(report.format_summary())
    print(f"Report: {report_path}")
    return 0 if report.failed == 0 else 1


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
    for name, backend in (("memory", "memory"), ("sqlite", "sqlite")):
        try:
            indexes[name] = build_search_index(
                chunks,
                backend=backend,
                database_path=search_db,
            )
        except Exception as exc:
            setup_errors[name] = f"{type(exc).__name__}: {exc}"

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
    search_backend: str = "memory",
    search_db: Path | None = None,
) -> int:
    documents = load_documents(knowledge_dir)
    chunks = [chunk for document in documents for chunk in chunk_document(document)]
    if not chunks:
        raise RuntimeError(f"No Markdown or TXT knowledge files found in {knowledge_dir}")

    search_index = build_search_index(
        chunks,
        backend=search_backend,
        database_path=search_db,
    )
    knowledge_tools = KnowledgeTools(knowledge_dir, search_index)
    agent = AgentRunner(
        llm=OpenAIAnswerer(),
        tool_registry=build_knowledge_tool_registry(knowledge_tools),
    )

    def refresh_index() -> None:
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
            refresh_index()
        return report.format()

    service = ChatService(
        search_index=search_index,
        llm=agent.llm,
        agent=agent,
        top_k=top_k,
        update_handler=update_handler,
        trace_store=TraceStore(trace_dir),
    )
    print(
        f"StudyMate loaded {len(documents)} documents. "
        f"Search backend: {search_backend}. "
        "Type /help for commands."
    )
    print(f"Trace records: {service.trace_store.path}")
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
    if args.command == "eval":
        return run_eval(
            knowledge_dir=args.knowledge,
            dataset_path=args.dataset,
            output_path=args.output,
            retrieval_k=args.retrieval_k,
            search_backend=args.search_backend,
            search_db=args.search_db,
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
            args.search_backend,
            args.search_db,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
