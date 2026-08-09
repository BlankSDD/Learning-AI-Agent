import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from studymate.docs_updater import (
    classify_page,
    extract_page_urls,
    resolve_proxy,
    update_sources,
)


def test_extract_page_urls_adds_markdown_suffix_and_filters_external_links():
    source = {"path_prefix": "/docs/en/", "page_url_suffix": ".md"}
    index = """
    - [Overview](https://docs.example.test/docs/en/overview)
    - [MCP](https://docs.example.test/docs/en/mcp.md)
    - [External](https://other.example.test/docs/en/nope)
    """

    assert extract_page_urls(index, "https://docs.example.test/docs/llms.txt", source) == [
        "https://docs.example.test/docs/en/overview.md",
        "https://docs.example.test/docs/en/mcp.md",
    ]


def test_classify_page_uses_configured_category_and_fallback():
    source = {"categories": [{"directory": "01-start", "patterns": ["quickstart"]}]}

    assert classify_page("quickstart", source) == "01-start"
    assert classify_page("unknown-topic", source) == "99-other"


def test_resolve_proxy_allows_an_explicitly_disabled_proxy(monkeypatch):
    monkeypatch.setenv("STUDYMATE_DOCS_PROXY", "http://127.0.0.1:7897")

    assert resolve_proxy("") is None


def test_update_sources_writes_pages_and_source_metadata(tmp_path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = b"# Example Docs\n\nThis is official Markdown.\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A002
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config_path = tmp_path / "sources.json"
        config_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "sources": {
                        "example": {
                            "enabled": True,
                            "display_name": "Example",
                            "target_dir": "example",
                            "mode": "pages",
                            "pages": [
                                {
                                    "url": f"http://127.0.0.1:{server.server_port}/docs.md",
                                    "path": "docs",
                                    "directory": "00-overview",
                                }
                            ],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        report = update_sources(
            config_path=config_path,
            knowledge_root=tmp_path / "knowledge",
            proxy="",
        )

        assert report.has_errors is False
        assert (tmp_path / "knowledge/example/00-overview/docs.md").exists()
        assert (tmp_path / "knowledge/example/SOURCE.md").exists()
        assert report.updated_files == 2
    finally:
        server.shutdown()
        thread.join()


def test_update_sources_reads_sitemap_and_downloads_mdx_as_markdown(tmp_path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/sitemap-index.xml":
                body = b"""<?xml version=\"1.0\"?><sitemapindex xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\"><sitemap><loc>http://127.0.0.1:%d/sitemap-0.xml</loc></sitemap></sitemapindex>""" % server.server_port
                content_type = "application/xml"
            elif self.path == "/sitemap-0.xml":
                body = b"""<?xml version=\"1.0\"?><urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\"><url><loc>http://127.0.0.1:%d/docs/agents/</loc></url></urlset>""" % server.server_port
                content_type = "application/xml"
            else:
                body = b"---\ntitle: Agents\n---\n\nAgent docs.\n"
                content_type = "text/markdown"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A002
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config_path = tmp_path / "sources.json"
        config_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "sources": {
                        "example": {
                            "enabled": True,
                            "display_name": "Example",
                            "target_dir": "example",
                            "mode": "sitemap",
                            "sitemap_url": f"http://127.0.0.1:{server.server_port}/sitemap-index.xml",
                            "path_prefix": "/docs/",
                            "page_url_template": f"http://127.0.0.1:{server.server_port}/raw/{{path}}.mdx",
                            "categories": [
                                {"directory": "01-agents", "patterns": ["agents"]}
                            ],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        report = update_sources(
            config_path=config_path,
            knowledge_root=tmp_path / "knowledge",
            proxy="",
        )

        assert report.has_errors is False
        assert (tmp_path / "knowledge/example/01-agents/agents.md").exists()
    finally:
        server.shutdown()
        thread.join()
