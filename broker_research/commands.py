"""User-facing broker research command handlers."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

from company_intelligence_pg import connect, get_company_aliases, upsert_company

from .discovery import discover_report_links, score_report_match
from .fetch import DEFAULT_REPORT_ROOT, fetch_broker_report_pdf
from .parse import parse_and_store_broker_report
from .sources import active_public_sources
from .storage import (
    find_report_by_hash,
    list_broker_sources,
    list_reports_for_fetch,
    seed_broker_sources,
    update_report_fetch_metadata,
    upsert_discovered_report,
)


DISCLAIMER = "Not investment advice. For research and learning only."


@dataclass(frozen=True)
class BrokerIndexOptions:
    symbol: str
    broker: str = ""
    all_public: bool = False
    refresh: bool = False


@dataclass(frozen=True)
class BrokerFetchOptions:
    symbol: str
    broker: str = ""
    limit: int = 10


def parse_broker_index_command(text: str) -> BrokerIndexOptions:
    parser = argparse.ArgumentParser(prog="/broker-index", add_help=False)
    parser.add_argument("command")
    parser.add_argument("symbol")
    parser.add_argument("--broker", default="")
    parser.add_argument("--all-public", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args((text or "").split())
    return BrokerIndexOptions(
        symbol=args.symbol.strip().upper(),
        broker=args.broker.strip().lower(),
        all_public=bool(args.all_public),
        refresh=bool(args.refresh),
    )


def parse_broker_fetch_command(text: str) -> BrokerFetchOptions:
    parser = argparse.ArgumentParser(prog="/broker-fetch", add_help=False)
    parser.add_argument("command")
    parser.add_argument("symbol")
    parser.add_argument("--broker", default="")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args((text or "").split())
    return BrokerFetchOptions(
        symbol=args.symbol.strip().upper(),
        broker=args.broker.strip().lower(),
        limit=max(1, int(args.limit)),
    )


def render_broker_sources(rows: list[dict[str, Any]]) -> str:
    lines = [f"━━━ {DISCLAIMER} ━━━", "", "## Broker Research Sources", ""]
    if not rows:
        lines.append("No broker sources are registered.")
        return "\n".join(lines)
    lines.append("| Broker | Kind | Access | Active | URL |")
    lines.append("|---|---:|---:|---:|---|")
    for row in rows:
        active = "yes" if row["is_active"] else "no"
        lines.append(
            f"| {row['broker_name']} | {row['source_kind']} | {row['access_mode']} | {active} | {row['source_url']} |"
        )
    return "\n".join(lines)


def handle_broker_sources_command(*, conn: Any | None = None) -> str:
    own_conn = conn is None
    db = conn or connect()
    try:
        seed_broker_sources(db)
        return render_broker_sources(list_broker_sources(db))
    finally:
        if own_conn:
            db.close()


def handle_broker_fetch_command(
    text: str,
    *,
    conn: Any | None = None,
    root_dir=DEFAULT_REPORT_ROOT,
    fetcher=None,
    parser=None,
) -> str:
    options = parse_broker_fetch_command(text)
    own_conn = conn is None
    db = conn or connect()
    fetched = 0
    duplicates = 0
    failed = 0
    parsed = 0
    try:
        reports = list_reports_for_fetch(db, symbol=options.symbol, broker=options.broker, limit=options.limit)
        for report in reports:
            result = fetch_broker_report_pdf(
                broker_code=str(report["broker_code"]),
                symbol=str(report["symbol"]),
                pdf_url=str(report["pdf_url"]),
                root_dir=root_dir,
                fetcher=fetcher,
            )
            status = str(result["status"])
            if status != "ok":
                failed += 1
                update_report_fetch_metadata(
                    db,
                    broker_report_id=int(report["broker_report_id"]),
                    fetch_status=status,
                )
                continue
            duplicate = find_report_by_hash(db, str(result["pdf_hash"]))
            if duplicate:
                duplicates += 1
                update_report_fetch_metadata(
                    db,
                    broker_report_id=int(report["broker_report_id"]),
                    fetch_status="duplicate_pdf",
                    pdf_hash=str(result["pdf_hash"]),
                    local_path=str(duplicate["local_path"]),
                )
                continue
            fetched += 1
            update_report_fetch_metadata(
                db,
                broker_report_id=int(report["broker_report_id"]),
                fetch_status="fetched",
                pdf_hash=str(result["pdf_hash"]),
                local_path=str(result["local_path"]),
            )
            parse_result = parse_and_store_broker_report(
                db,
                broker_report_id=int(report["broker_report_id"]),
                local_path=str(result["local_path"]),
                parser=parser,
            )
            if parse_result["parse_status"] in {"parsed", "partial"}:
                parsed += 1
        return "\n".join(
            [
                f"━━━ {DISCLAIMER} ━━━",
                "",
                f"## Broker Fetch: {options.symbol}",
                "",
                f"- Reports selected: {len(reports)}",
                f"- Fetched PDFs: {fetched}",
                f"- Duplicate PDFs: {duplicates}",
                f"- Fetch failures: {failed}",
                f"- Parsed reports: {parsed}",
            ]
        )
    finally:
        if own_conn:
            db.close()


def _fetch_source_html(source_url: str, *, timeout: int = 15) -> str:
    from urllib.request import Request, urlopen

    request = Request(
        source_url,
        headers={
            "User-Agent": "AgentAddaResearchBot/1.0 (+research-only)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        if "pdf" in content_type.lower():
            return f'<a href="{source_url}">{source_url.rsplit("/", 1)[-1]}</a>'
        raw = response.read(2_000_000)
    return raw.decode("utf-8", errors="replace")


def index_symbol_from_html(
    *,
    conn: Any,
    symbol: str,
    html_by_source_url: dict[str, str],
    company_name: str = "",
    broker: str = "",
) -> dict[str, Any]:
    clean_symbol = symbol.strip().upper()
    upsert_company(conn, clean_symbol, company_name=company_name)
    aliases = get_company_aliases(conn, clean_symbol)
    if company_name and company_name not in aliases:
        aliases = [company_name, *aliases]
    discovered = 0
    matched = 0
    stored = 0
    sources = active_public_sources()
    if broker:
        sources = tuple(source for source in sources if source.broker_code == broker)
    for source in sources:
        html = html_by_source_url.get(source.source_url)
        if not html:
            continue
        links = discover_report_links(html, base_url=source.source_url, broker_code=source.broker_code)
        discovered += len(links)
        for link in links:
            score = score_report_match(link, symbol=clean_symbol, aliases=aliases)
            if score < 0.5:
                continue
            matched += 1
            upsert_discovered_report(
                conn,
                symbol=clean_symbol,
                company_name=company_name,
                link=link,
                match_score=score,
            )
            stored += 1
    return {"symbol": clean_symbol, "discovered": discovered, "matched": matched, "stored": stored}


def handle_broker_index_command(
    text: str,
    *,
    conn: Any | None = None,
    html_by_source_url: dict[str, str] | None = None,
) -> str:
    options = parse_broker_index_command(text)
    own_conn = conn is None
    db = conn or connect()
    try:
        seed_broker_sources(db)
        sources = active_public_sources()
        if options.broker:
            sources = tuple(source for source in sources if source.broker_code == options.broker)
        html_map = dict(html_by_source_url or {})
        for source in sources:
            if source.source_url not in html_map:
                html_map[source.source_url] = _fetch_source_html(source.source_url)
        result = index_symbol_from_html(
            conn=db,
            symbol=options.symbol,
            html_by_source_url=html_map,
            broker=options.broker,
        )
        return "\n".join(
            [
                f"━━━ {DISCLAIMER} ━━━",
                "",
                f"## Broker Index: {result['symbol']}",
                "",
                f"- Sources scanned: {len(sources)}",
                f"- Links discovered: {result['discovered']}",
                f"- Symbol matches: {result['matched']}",
                f"- Stored report metadata rows: {result['stored']}",
                "",
                "PDF fetch, parsing, and LLM analysis are separate follow-up phases.",
            ]
        )
    finally:
        if own_conn:
            db.close()
