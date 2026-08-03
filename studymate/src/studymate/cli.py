from __future__ import annotations

import argparse
from pathlib import Path

from .chat import ChatService
from .docs_updater import DocsUpdateError, update_sources
from .ingest import chunk_document, load_documents
from .llm import OpenAIAnswerer
from .search import InMemorySearchIndex


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="studymate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="scan and validate knowledge files")
    ingest.add_argument("knowledge_dir", type=Path)

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
    return parser


def run_ingest(knowledge_dir: Path) -> int:
    documents = load_documents(knowledge_dir)
    chunk_count = sum(len(chunk_document(document)) for document in documents)
    print(f"Loaded {len(documents)} documents and {chunk_count} chunks.")
    for document in documents:
        print(f"- {document.path} ({document.title})")
    return 0


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


def run_chat(
    knowledge_dir: Path,
    top_k: int,
    docs_config: Path,
    proxy: str | None,
) -> int:
    documents = load_documents(knowledge_dir)
    chunks = [chunk for document in documents for chunk in chunk_document(document)]
    if not chunks:
        raise RuntimeError(f"No Markdown or TXT knowledge files found in {knowledge_dir}")

    def refresh_index() -> None:
        refreshed_documents = load_documents(knowledge_dir)
        refreshed_chunks = [
            chunk
            for document in refreshed_documents
            for chunk in chunk_document(document)
        ]
        service.search_index = InMemorySearchIndex(refreshed_chunks)
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
        search_index=InMemorySearchIndex(chunks),
        llm=OpenAIAnswerer(),
        top_k=top_k,
        update_handler=update_handler,
    )
    print(f"StudyMate loaded {len(documents)} documents. Type /help for commands.")
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
        return run_chat(args.knowledge, args.top_k, args.docs_config, args.proxy)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
