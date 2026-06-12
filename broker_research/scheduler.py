"""Scheduled public broker research index crawling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .commands import index_symbol_from_html
from .sources import BROKER_SOURCES, BrokerSource
from .storage import seed_broker_sources


@dataclass(frozen=True)
class ScheduledBrokerCrawlResult:
    symbol: str
    sources_seen: int
    sources_succeeded: int
    sources_failed: int
    links_discovered: int
    reports_stored: int
    skipped_sources: int
    failures: list[dict[str, str]]


def _eligible_sources(sources: tuple[BrokerSource, ...]) -> tuple[BrokerSource, ...]:
    return tuple(source for source in sources if source.is_active and source.access_mode in {"public", "partial"})


def _default_fetch_html(source: BrokerSource) -> str:
    from .commands import _fetch_source_html

    return _fetch_source_html(source.source_url)


def run_scheduled_broker_crawl(
    *,
    conn,
    symbol: str,
    sources: tuple[BrokerSource, ...] = BROKER_SOURCES,
    fetch_html: Callable[[BrokerSource], str] | None = None,
    max_sources: int | None = None,
) -> ScheduledBrokerCrawlResult:
    clean_symbol = symbol.strip().upper()
    seed_broker_sources(conn)
    eligible = _eligible_sources(tuple(sources))
    selected = eligible[:max_sources] if max_sources else eligible
    skipped_sources = len(tuple(sources)) - len(selected)
    fetch = fetch_html or _default_fetch_html
    sources_succeeded = 0
    sources_failed = 0
    links_discovered = 0
    reports_stored = 0
    failures: list[dict[str, str]] = []

    for source in selected:
        try:
            html = fetch(source)
            result = index_symbol_from_html(
                conn=conn,
                symbol=clean_symbol,
                html_by_source_url={source.source_url: html},
                broker=source.broker_code,
            )
            sources_succeeded += 1
            links_discovered += int(result["discovered"])
            reports_stored += int(result["stored"])
        except Exception as exc:
            sources_failed += 1
            failures.append({"broker_code": source.broker_code, "source_url": source.source_url, "error": str(exc)})

    return ScheduledBrokerCrawlResult(
        symbol=clean_symbol,
        sources_seen=len(selected),
        sources_succeeded=sources_succeeded,
        sources_failed=sources_failed,
        links_discovered=links_discovered,
        reports_stored=reports_stored,
        skipped_sources=skipped_sources,
        failures=failures,
    )
