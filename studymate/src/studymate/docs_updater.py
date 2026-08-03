from __future__ import annotations

import fnmatch
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit
from urllib.request import OpenerDirector, ProxyHandler, Request, build_opener


class DocsUpdateError(RuntimeError):
    """Raised when the document source configuration or download is invalid."""


@dataclass(frozen=True)
class SourceUpdate:
    source_id: str
    display_name: str
    page_count: int
    changed_count: int
    target_dir: str
    errors: tuple[str, ...] = ()


@dataclass
class UpdateReport:
    results: list[SourceUpdate] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def updated_files(self) -> int:
        return sum(result.changed_count for result in self.results)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors or any(result.errors for result in self.results))

    def format(self) -> str:
        lines = ["文档更新完成。" if not self.has_errors else "文档更新结束，但存在问题。"]
        for result in self.results:
            status = f"{result.page_count} 页，更新 {result.changed_count} 个文件"
            lines.append(f"- {result.display_name}: {status} -> {result.target_dir}")
            lines.extend(f"  - {error}" for error in result.errors)
        lines.extend(f"- 配置或选择错误: {error}" for error in self.errors)
        if not self.results and not self.errors:
            lines.append("- 没有启用任何文档源。")
        return "\n".join(lines)


def load_sources_config(config_path: Path) -> dict:
    path = Path(config_path)
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DocsUpdateError(f"无法读取文档源配置: {path}") from exc

    if not isinstance(config, dict) or not isinstance(config.get("sources"), dict):
        raise DocsUpdateError("文档源配置必须包含对象字段 sources")
    for source_id, source in config["sources"].items():
        if not isinstance(source, dict):
            raise DocsUpdateError(f"文档源配置无效: {source_id}")
        if not source.get("target_dir"):
            raise DocsUpdateError(f"文档源缺少 target_dir: {source_id}")
        if source.get("mode") not in {"index", "sitemap", "pages"}:
            raise DocsUpdateError(
                f"文档源 mode 必须是 index、sitemap 或 pages: {source_id}"
            )
    return config


def normalize_proxy(proxy: str | None) -> str | None:
    value = (proxy or "").strip()
    if not value:
        return None
    if "://" not in value:
        return f"http://{value}"
    return value


def resolve_proxy(proxy: str | None = None) -> str | None:
    try:
        from dotenv import load_dotenv

        load_dotenv(override=False)
    except ImportError:
        pass
    explicit = normalize_proxy(proxy)
    if explicit:
        return explicit
    for name in ("STUDYMATE_DOCS_PROXY", "HTTPS_PROXY", "HTTP_PROXY"):
        value = normalize_proxy(os.environ.get(name))
        if value:
            return value
    return None


def extract_page_urls(index_text: str, index_url: str, source: dict) -> list[str]:
    links = re.findall(r"\[[^\]]+\]\(([^)\s]+)", index_text)
    links.extend(re.findall(r"https?://[^\s<>\])]+", index_text))
    index_parts = urlsplit(index_url)
    path_prefix = source.get("path_prefix", "")
    suffix = source.get("page_url_suffix", "")
    seen: set[str] = set()
    page_urls: list[str] = []

    for raw_link in links:
        candidate = urljoin(index_url, raw_link.strip())
        candidate, _ = urldefrag(candidate)
        parts = urlsplit(candidate)
        if parts.scheme not in {"http", "https"} or parts.netloc != index_parts.netloc:
            continue
        if path_prefix and not parts.path.startswith(path_prefix):
            continue
        if parts.path.endswith("/llms.txt"):
            continue
        path = parts.path.rstrip("/")
        if suffix and not path.endswith(suffix):
            path += suffix
        candidate = urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))
        if candidate not in seen:
            seen.add(candidate)
            page_urls.append(candidate)
    return page_urls


def classify_page(page_path: str, source: dict) -> str:
    normalized = page_path.strip("/")
    for category in source.get("categories", []):
        for pattern in category.get("patterns", []):
            if fnmatch.fnmatch(normalized, pattern):
                return category["directory"]
    return "99-other"


def _build_opener(proxy: str | None) -> OpenerDirector:
    if proxy:
        return build_opener(ProxyHandler({"http": proxy, "https": proxy}))
    return build_opener()


def _fetch_text(opener: OpenerDirector, url: str, timeout: int) -> str:
    request = Request(
        url,
        headers={
            "Accept": "text/markdown, text/plain;q=0.9, */*;q=0.1",
            "User-Agent": "StudyMate-doc-updater/0.1",
        },
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = response.read()
            content_type = response.headers.get("Content-Type", "")
    except Exception as exc:
        raise DocsUpdateError(f"下载失败 {url}: {exc}") from exc

    text = payload.decode("utf-8-sig", errors="replace")
    if not text.strip():
        raise DocsUpdateError(f"下载内容为空: {url}")
    first_part = text.lstrip()[:256].lower()
    if "<!doctype html" in first_part or first_part.startswith("<html"):
        raise DocsUpdateError(f"下载到 HTML 页面而不是 Markdown: {url} ({content_type})")
    return text


def _page_path(url: str, source: dict) -> str:
    path = urlsplit(url).path.strip("/")
    prefix = source.get("path_prefix", "").strip("/")
    if prefix and path.startswith(f"{prefix}/"):
        path = path[len(prefix) + 1 :]
    if path.endswith(".md"):
        path = path[:-3]
    return path or "index"


def _safe_filename(value: str) -> str:
    name = Path(value).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return name or "document"


def _atomic_write(path: Path, text: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = path.read_text(encoding="utf-8") if path.exists() else None
    if previous == text:
        return False
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
    ) as temporary:
        temporary.write(text)
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, path)
    return True


def _source_metadata(source: dict, page_count: int) -> str:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    display_name = source.get("display_name", "文档")
    source_url = source.get("index_url") or source.get("sitemap_url") or "多个官方页面"
    return (
        f"# {display_name} 文档来源说明\n\n"
        "本目录由 StudyMate 文档更新器生成，请勿手动修改此文件。\n\n"
        f"- 官方来源：{source_url}\n"
        f"- 更新时间（UTC）：{timestamp}\n"
        f"- 本次页面数量：{page_count}\n"
    )


def _sitemap_page_urls(
    sitemap_url: str,
    opener: OpenerDirector,
    timeout: int,
    seen_sitemaps: set[str] | None = None,
) -> list[str]:
    seen_sitemaps = seen_sitemaps or set()
    if sitemap_url in seen_sitemaps:
        return []
    seen_sitemaps.add(sitemap_url)
    try:
        root = ET.fromstring(_fetch_text(opener, sitemap_url, timeout))
    except ET.ParseError as exc:
        raise DocsUpdateError(f"sitemap 不是有效 XML: {sitemap_url}") from exc
    namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    root_name = root.tag.rsplit("}", 1)[-1]
    locations = [
        element.text.strip()
        for element in root.findall(f".//{namespace}loc")
        if element.text and element.text.strip()
    ]
    if root_name == "sitemapindex":
        page_urls: list[str] = []
        for child_url in locations:
            page_urls.extend(_sitemap_page_urls(child_url, opener, timeout, seen_sitemaps))
        return page_urls
    return locations


def _discover_sitemap_pages(
    source: dict, opener: OpenerDirector, timeout: int
) -> list[dict]:
    sitemap_url = source.get("sitemap_url")
    template = source.get("page_url_template")
    if not sitemap_url or not template:
        raise DocsUpdateError("sitemap 模式需要 sitemap_url 和 page_url_template")
    path_prefix = source.get("path_prefix", "")
    excluded = tuple(source.get("exclude_path_prefixes", []))
    pages: list[dict] = []
    seen: set[str] = set()
    for page_url in _sitemap_page_urls(sitemap_url, opener, timeout):
        path = urlsplit(page_url).path
        if path_prefix and not path.startswith(path_prefix):
            continue
        if any(path.startswith(prefix) for prefix in excluded):
            continue
        page_path = path[len(path_prefix) :].strip("/") if path_prefix else path.strip("/")
        page_path = page_path or "index"
        raw_url = template.format(path=page_path)
        if raw_url in seen:
            continue
        seen.add(raw_url)
        pages.append({"url": raw_url, "path": page_path})
    return pages


def _discover_pages(source: dict, opener: OpenerDirector, timeout: int) -> list[dict]:
    if source["mode"] == "pages":
        return list(source.get("pages", []))
    if source["mode"] == "sitemap":
        return _discover_sitemap_pages(source, opener, timeout)
    index_url = source.get("index_url")
    if not index_url:
        raise DocsUpdateError("index 模式缺少 index_url")
    index_text = _fetch_text(opener, index_url, timeout)
    return [{"url": url} for url in extract_page_urls(index_text, index_url, source)]


def _update_source(
    source_id: str,
    source: dict,
    knowledge_root: Path,
    opener: OpenerDirector,
    timeout: int,
    workers: int,
) -> SourceUpdate:
    target_dir = knowledge_root / source["target_dir"]
    pages = _discover_pages(source, opener, timeout)
    errors: list[str] = []
    changed_count = 0
    successful_pages = 0

    def download(page: dict) -> tuple[dict, str | None, str | None]:
        url = page.get("url")
        if not url:
            return page, None, "页面配置缺少 url"
        try:
            return page, _fetch_text(opener, url, timeout), None
        except DocsUpdateError as exc:
            return page, None, str(exc)

    worker_count = max(1, min(workers, len(pages) or 1))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        downloads = executor.map(download, pages)
        for page, text, error in downloads:
            if error:
                errors.append(error)
                continue
            assert text is not None
            url = page["url"]
            page_path = page.get("path") or _page_path(url, source)
            directory = page.get("directory") or classify_page(page_path, source)
            filename = _safe_filename(page.get("filename") or f"{Path(page_path).name}.md")
            output = target_dir / directory / filename
            try:
                changed_count += int(_atomic_write(output, text))
                successful_pages += 1
            except OSError as exc:
                errors.append(f"写入失败 {output}: {exc}")

    if successful_pages:
        try:
            changed_count += int(
                _atomic_write(
                    target_dir / "SOURCE.md",
                    _source_metadata(source, successful_pages),
                )
            )
        except OSError as exc:
            errors.append(f"写入来源说明失败 {target_dir / 'SOURCE.md'}: {exc}")

    return SourceUpdate(
        source_id=source_id,
        display_name=source.get("display_name", source_id),
        page_count=successful_pages,
        changed_count=changed_count,
        target_dir=str(target_dir),
        errors=tuple(errors),
    )


def update_sources(
    *,
    config_path: Path,
    knowledge_root: Path,
    only: list[str] | None = None,
    proxy: str | None = None,
    timeout: int = 30,
    workers: int = 8,
) -> UpdateReport:
    if workers <= 0:
        raise DocsUpdateError("workers 必须大于 0")
    config = load_sources_config(config_path)
    sources: dict = config["sources"]
    selected = only or [
        source_id for source_id, source in sources.items() if source.get("enabled", False)
    ]
    unknown = [source_id for source_id in selected if source_id not in sources]
    if unknown:
        raise DocsUpdateError(f"未知文档源: {', '.join(unknown)}")

    report = UpdateReport()
    opener = _build_opener(resolve_proxy(proxy))
    for source_id in selected:
        source = sources[source_id]
        if not source.get("enabled", False) and not only:
            continue
        try:
            report.results.append(
                _update_source(
                    source_id,
                    source,
                    Path(knowledge_root),
                    opener,
                    timeout,
                    workers,
                )
            )
        except DocsUpdateError as exc:
            report.errors.append(f"{source_id}: {exc}")
    return report
