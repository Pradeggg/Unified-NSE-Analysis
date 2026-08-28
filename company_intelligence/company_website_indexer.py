"""Company website crawler and SQLite FTS indexer."""

from __future__ import annotations

import hashlib
import html
import re
import sqlite3
import urllib.robotparser
import urllib.request
import xml.etree.ElementTree as ET
from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urldefrag

from .company_intelligence_extract import classify_evidence_text


UNSUPPORTED_SCHEMES = {"mailto", "tel", "javascript", "data"}
DOCUMENT_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx")
DEFAULT_USER_AGENT = "AgentAddaResearchBot/1.0"


def normalize_url(base_url: str, href: str) -> str | None:
    href = (href or "").strip()
    if not href:
        return None
    parsed_href = urlparse(href)
    if parsed_href.scheme.lower() in UNSUPPORTED_SCHEMES:
        return None
    joined = urljoin(base_url, href)
    clean, _frag = urldefrag(joined)
    parsed = urlparse(clean)
    if parsed.scheme not in {"http", "https"}:
        return None
    return clean


def extract_links(base_url: str, html_text: str) -> list[dict[str, str]]:
    parser = _LinkParser(base_url)
    parser.feed(html_text or "")
    return parser.links


def classify_link(url: str, link_text: str = "") -> str:
    text = f"{url} {link_text}".lower()
    if any(term in text for term in ("annual-report", "annual report", "annual_report")):
        return "annual_report"
    if any(term in text for term in ("investor-presentation", "investor presentation", "investor_presentation")):
        return "investor_presentation"
    if any(term in text for term in ("financial-results", "financial results", "quarterly-results", "results")):
        return "results"
    if any(term in text for term in ("concall", "earnings-call", "transcript")):
        return "concall_transcript"
    if urlparse(url).path.lower().endswith(DOCUMENT_EXTENSIONS):
        return "document"
    return "html_page"


def fetch_url(
    url: str,
    timeout: float = 10.0,
    max_bytes: int = 5_000_000,
    user_agent: str = DEFAULT_USER_AGENT,
) -> dict[str, Any]:
    """Fetch one URL and return structured metadata without raising network errors."""
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = int(getattr(response, "status", 200) or 200)
            content_type = response.headers.get("Content-Type", "")
            content = response.read(max_bytes + 1)
            if len(content) > max_bytes:
                return {
                    "url": url,
                    "status": "error",
                    "status_code": status_code,
                    "content_type": content_type,
                    "content": b"",
                    "error": f"response exceeds max_bytes ({max_bytes})",
                }
            result: dict[str, Any] = {
                "url": url,
                "status": "ok",
                "status_code": status_code,
                "content_type": content_type,
                "content": content,
            }
            if _is_text_content(content_type):
                result["text"] = content.decode(_charset_from_content_type(content_type), errors="ignore")
            return result
    except Exception as exc:  # Network callers should receive an auditable error payload.
        return {
            "url": url,
            "status": "error",
            "status_code": 0,
            "content_type": "",
            "content": b"",
            "error": str(exc),
        }


def robots_allows(
    url: str,
    user_agent: str = DEFAULT_USER_AGENT,
    fetcher=fetch_url,
) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    response = fetcher(robots_url)
    if response.get("status") == "error" or int(response.get("status_code", 0) or 0) >= 400:
        return True
    text = _response_text(response)
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(text.splitlines())
    return parser.can_fetch(user_agent, url)


def discover_sitemap_urls(base_url: str, fetcher=fetch_url) -> list[str]:
    parsed = urlparse(base_url)
    base_root = f"{parsed.scheme}://{parsed.netloc}"
    sitemap_locations = [f"{base_root}/sitemap.xml"]

    robots_response = fetcher(f"{base_root}/robots.txt")
    if robots_response.get("status") != "error" and int(robots_response.get("status_code", 0) or 0) < 400:
        for line in _response_text(robots_response).splitlines():
            if line.lower().startswith("sitemap:"):
                sitemap_url = line.split(":", 1)[1].strip()
                if sitemap_url:
                    sitemap_locations.insert(0, sitemap_url)

    urls: list[str] = []
    seen: set[str] = set()
    base_domain = parsed.netloc.lower()
    for sitemap_url in dict.fromkeys(sitemap_locations):
        response = fetcher(sitemap_url)
        if response.get("status") == "error" or int(response.get("status_code", 0) or 0) >= 400:
            continue
        for loc in _extract_sitemap_locs(_response_text(response)):
            if urlparse(loc).netloc.lower() != base_domain:
                continue
            if loc not in seen:
                seen.add(loc)
                urls.append(loc)
    return urls


def download_company_document(
    conn: sqlite3.Connection,
    symbol: str,
    url: str,
    document_type: str,
    fetcher=fetch_url,
    root_dir: str | Path = "data/company_intelligence/documents",
) -> dict[str, Any]:
    clean_symbol = symbol.strip().upper()
    cached = conn.execute(
        """
        SELECT document_id, local_path, content_hash
        FROM source_documents
        WHERE symbol = ? AND source_url = ? AND fetch_status = 'ok'
        """,
        (clean_symbol, url),
    ).fetchone()
    if cached and Path(cached[1]).exists():
        return {
            "status": "cached",
            "document_id": cached[0],
            "local_path": cached[1],
            "content_hash": cached[2],
        }

    response = fetcher(url)
    if response.get("status") == "error" or int(response.get("status_code", 0) or 0) >= 400:
        failure = response.get("error", f"HTTP {response.get('status_code', 0)}")
        document_id = _document_id(clean_symbol, url)
        conn.execute(
            """
            INSERT OR REPLACE INTO source_documents
                (document_id, symbol, source_tier, source_name, source_url, document_type,
                 local_path, content_hash, fetch_status, parse_status, failure_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (document_id, clean_symbol, 1, "company_website", url, document_type, "", "", "error", "", failure),
        )
        conn.commit()
        return {"status": "error", "document_id": document_id, "error": failure}

    content = response.get("content", b"")
    if not isinstance(content, bytes):
        content = str(content).encode("utf-8")
    content_hash = hashlib.sha256(content).hexdigest()
    suffix = Path(urlparse(url).path).suffix or ".bin"
    target_dir = Path(root_dir) / clean_symbol
    target_dir.mkdir(parents=True, exist_ok=True)
    local_path = target_dir / f"{content_hash}{suffix}"
    if not local_path.exists():
        local_path.write_bytes(content)

    document_id = _document_id(clean_symbol, url)
    conn.execute(
        """
        INSERT OR REPLACE INTO source_documents
            (document_id, symbol, source_tier, source_name, source_url, document_type,
             local_path, content_hash, fetch_status, parse_status, failure_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            document_id,
            clean_symbol,
            1,
            "company_website",
            url,
            document_type,
            str(local_path),
            content_hash,
            "ok",
            "downloaded",
            "",
        ),
    )
    conn.commit()
    return {
        "status": "downloaded",
        "document_id": document_id,
        "local_path": str(local_path),
        "content_hash": content_hash,
    }


def crawl_company_website(
    conn: sqlite3.Connection,
    symbol: str,
    base_url: str,
    fetcher=fetch_url,
    max_pages: int = 25,
    max_depth: int = 1,
    include_documents: bool = True,
    respect_robots: bool = False,
    seed_sitemap: bool = False,
    document_root: str | Path | None = None,
) -> dict[str, Any]:
    clean_symbol = symbol.strip().upper()
    base_domain = urlparse(base_url).netloc.lower()
    run_id = _start_crawl(conn, clean_symbol, base_url)
    queue = deque([(base_url, 0)])
    if seed_sitemap:
        for sitemap_url in discover_sitemap_urls(base_url, fetcher=fetcher):
            if sitemap_url != base_url:
                queue.append((sitemap_url, 0))
    seen: set[str] = set()
    pages_indexed = 0
    documents_found = 0
    pages_seen = 0

    while queue and pages_indexed < max_pages:
        url, depth = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        if respect_robots and not robots_allows(url, fetcher=fetcher):
            continue
        pages_seen += 1
        link_type = classify_link(url)
        is_document = link_type != "html_page"
        if is_document:
            if include_documents:
                documents_found += 1
                if document_root is not None:
                    download_company_document(conn, clean_symbol, url, link_type, fetcher=fetcher, root_dir=document_root)
            continue

        response = fetcher(url)
        if response.get("status") == "error":
            continue
        if int(response.get("status_code", 200)) >= 400:
            continue
        content_type = response.get("content_type", "text/html")
        html_text = _response_text(response)

        title, text = _extract_title_and_text(html_text)
        page_id = _store_page(
            conn,
            run_id,
            clean_symbol,
            url,
            title,
            content_type,
            "indexed",
            text,
            "company_website",
        )
        _store_chunks(conn, page_id, clean_symbol, url, title, text)
        pages_indexed += 1

        links = extract_links(url, html_text)
        for link in links:
            to_url = link["url"]
            same_domain = urlparse(to_url).netloc.lower() == base_domain
            ltype = classify_link(to_url, link.get("text", ""))
            _store_link(conn, run_id, clean_symbol, url, to_url, link.get("text", ""), ltype, same_domain)
            if not same_domain:
                continue
            if ltype != "html_page":
                if include_documents:
                    documents_found += 1
                    if document_root is not None:
                        download_company_document(
                            conn,
                            clean_symbol,
                            to_url,
                            ltype,
                            fetcher=fetcher,
                            root_dir=document_root,
                        )
                continue
            if depth < max_depth and to_url not in seen:
                queue.append((to_url, depth + 1))

    _complete_crawl(conn, run_id, "completed", pages_seen, pages_indexed, documents_found, "")
    return {
        "crawl_run_id": run_id,
        "symbol": clean_symbol,
        "base_url": base_url,
        "status": "completed",
        "pages_seen": pages_seen,
        "pages_indexed": pages_indexed,
        "documents_found": documents_found,
    }


def search_company_website(
    conn: sqlite3.Connection,
    symbol: str,
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT symbol, url, title, category, chunk_text
        FROM website_search_fts
        WHERE symbol = ? AND website_search_fts MATCH ?
        LIMIT ?
        """,
        (symbol.strip().upper(), query, int(limit)),
    ).fetchall()
    keys = ["symbol", "url", "title", "category", "chunk_text"]
    return [dict(zip(keys, row)) for row in rows]


def _is_text_content(content_type: str) -> bool:
    clean = (content_type or "").lower()
    return (
        clean.startswith("text/")
        or "html" in clean
        or "xml" in clean
        or "json" in clean
        or "javascript" in clean
    )


def _charset_from_content_type(content_type: str) -> str:
    match = re.search(r"charset=([^;\s]+)", content_type or "", flags=re.I)
    return match.group(1) if match else "utf-8"


def _response_text(response: dict[str, Any]) -> str:
    text = response.get("text")
    if text is not None:
        return str(text)
    content = response.get("content", b"")
    if isinstance(content, bytes):
        return content.decode(_charset_from_content_type(response.get("content_type", "")), errors="ignore")
    return str(content)


def _extract_sitemap_locs(xml_text: str) -> list[str]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    locs: list[str] = []
    for node in root.iter():
        if node.tag.lower().endswith("loc") and node.text:
            locs.append(node.text.strip())
    return locs


def _document_id(symbol: str, url: str) -> str:
    digest = hashlib.sha256(f"{symbol}:{url}".encode("utf-8")).hexdigest()
    return f"company_website:{digest}"


class _LinkParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: list[dict[str, str]] = []
        self._current_href: str | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        href = normalize_url(self.base_url, attrs_dict.get("href", ""))
        if href:
            self._current_href = href
            self._text_parts = []

    def handle_data(self, data: str):
        if self._current_href:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str):
        if tag.lower() == "a" and self._current_href:
            text = " ".join(part.strip() for part in self._text_parts if part.strip())
            self.links.append({"url": self._current_href, "text": html.unescape(text)})
            self._current_href = None
            self._text_parts = []


def _extract_title_and_text(html_text: str) -> tuple[str, str]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html_text, flags=re.I | re.S)
    title = _clean_text(title_match.group(1)) if title_match else ""
    body = re.sub(r"<script[\s\S]*?</script>", " ", html_text, flags=re.I)
    body = re.sub(r"<style[\s\S]*?</style>", " ", body, flags=re.I)
    body = re.sub(r"<[^>]+>", " ", body)
    return title, _clean_text(html.unescape(body))


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _start_crawl(conn: sqlite3.Connection, symbol: str, base_url: str) -> int:
    cur = conn.execute(
        "INSERT INTO website_crawl_runs (symbol, base_url, status) VALUES (?, ?, 'running')",
        (symbol, base_url),
    )
    conn.commit()
    return int(cur.lastrowid)


def _complete_crawl(
    conn: sqlite3.Connection,
    run_id: int,
    status: str,
    pages_seen: int,
    pages_indexed: int,
    documents_found: int,
    failure_reason: str,
) -> None:
    conn.execute(
        """
        UPDATE website_crawl_runs
        SET completed_at = CURRENT_TIMESTAMP,
            status = ?,
            pages_seen = ?,
            pages_indexed = ?,
            documents_found = ?,
            failure_reason = ?
        WHERE crawl_run_id = ?
        """,
        (status, pages_seen, pages_indexed, documents_found, failure_reason, run_id),
    )
    conn.commit()


def _store_page(
    conn: sqlite3.Connection,
    run_id: int,
    symbol: str,
    url: str,
    title: str,
    content_type: str,
    status: str,
    text: str,
    page_type: str,
) -> int:
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    conn.execute(
        """
        INSERT OR REPLACE INTO website_pages
            (crawl_run_id, symbol, url, url_hash, title, content_hash, content_type, status, text, page_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, symbol, url, url_hash, title, content_hash, content_type, status, text, page_type),
    )
    conn.commit()
    row = conn.execute(
        "SELECT page_id FROM website_pages WHERE symbol = ? AND url_hash = ?",
        (symbol, url_hash),
    ).fetchone()
    return int(row[0])


def _store_link(
    conn: sqlite3.Connection,
    run_id: int,
    symbol: str,
    from_url: str,
    to_url: str,
    link_text: str,
    link_type: str,
    is_same_domain: bool,
) -> None:
    conn.execute(
        """
        INSERT INTO website_links
            (crawl_run_id, symbol, from_url, to_url, link_text, link_type, is_same_domain)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, symbol, from_url, to_url, link_text, link_type, 1 if is_same_domain else 0),
    )
    conn.commit()


def _store_chunks(conn: sqlite3.Connection, page_id: int, symbol: str, url: str, title: str, text: str) -> None:
    for chunk in _chunk_text(text):
        categories = classify_evidence_text(chunk)
        category = categories[0] if categories else "uncategorized"
        cur = conn.execute(
            """
            INSERT INTO website_page_chunks (page_id, symbol, url, chunk_text, category)
            VALUES (?, ?, ?, ?, ?)
            """,
            (page_id, symbol, url, chunk, category),
        )
        conn.execute(
            """
            INSERT INTO website_search_fts (symbol, url, title, category, chunk_text)
            VALUES (?, ?, ?, ?, ?)
            """,
            (symbol, url, title, category, chunk),
        )
    conn.commit()


def _chunk_text(text: str, max_chars: int = 900) -> list[str]:
    clean = _clean_text(text)
    if not clean:
        return []
    chunks = []
    start = 0
    while start < len(clean):
        chunks.append(clean[start : start + max_chars])
        start += max_chars
    return chunks
