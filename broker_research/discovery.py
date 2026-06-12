"""HTML discovery helpers for public broker research links."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin


@dataclass(frozen=True)
class DiscoveredReportLink:
    broker_code: str
    title: str
    pdf_url: str
    source_url: str


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._href: str | None = None
        self._text: list[str] = []
        self.anchors: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        values = dict(attrs)
        self._href = values.get("href") or ""
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        title = " ".join(" ".join(self._text).split())
        self.anchors.append((self._href, title))
        self._href = None
        self._text = []


def _looks_like_pdf_link(href: str) -> bool:
    clean = href.lower()
    return ".pdf" in clean or "/downloadreport/file/" in clean


def discover_report_links(html: str, *, base_url: str, broker_code: str) -> list[DiscoveredReportLink]:
    parser = _AnchorParser()
    parser.feed(html or "")
    links: list[DiscoveredReportLink] = []
    seen: set[str] = set()
    for href, title in parser.anchors:
        if not _looks_like_pdf_link(href):
            continue
        pdf_url = urljoin(base_url, href)
        if pdf_url in seen:
            continue
        seen.add(pdf_url)
        links.append(
            DiscoveredReportLink(
                broker_code=broker_code,
                title=title or pdf_url.rsplit("/", 1)[-1],
                pdf_url=pdf_url,
                source_url=base_url,
            )
        )
    return links


def _norm(text: str) -> str:
    return " ".join((text or "").replace("_", " ").replace("-", " ").replace("+", " ").lower().split())


def score_report_match(link: DiscoveredReportLink, *, symbol: str, aliases: list[str] | tuple[str, ...]) -> float:
    haystack = _norm(f"{link.title} {link.pdf_url}")
    clean_symbol = _norm(symbol)
    if clean_symbol and clean_symbol in haystack.split():
        return 1.0
    for alias in aliases:
        clean_alias = _norm(alias)
        if clean_alias and clean_alias in haystack:
            return 0.9
    if clean_symbol and clean_symbol in haystack:
        return 0.65
    return 0.0
