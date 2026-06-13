"""User-facing broker research command handlers."""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from typing import Any

from company_intelligence_pg import connect, get_company_aliases, upsert_company

from .discovery import discover_report_links, score_report_match
from .extract import extract_and_store_facts_from_pages
from .fetch import DEFAULT_REPORT_ROOT, fetch_broker_report_pdf
from .parse import parse_and_store_broker_report
from .consensus import build_broker_consensus
from .financial_view import (
    build_financial_analyst_markdown,
    build_llm_financial_prompt,
    write_financial_analyst_report,
)
from .pg_context import fetch_agent_adda_pg_context
from .report import render_broker_research_markdown, write_broker_research_report
from .sources import active_public_sources
from .storage import (
    find_report_by_hash,
    list_broker_report_pages,
    list_broker_research_runs,
    list_broker_sources,
    list_broker_research_facts,
    list_reports_for_fetch,
    record_broker_research_run,
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


@dataclass(frozen=True)
class FinancialResearchOptions:
    symbol: str
    broker: str = ""


@dataclass(frozen=True)
class ResearchReportCatalogOptions:
    symbol: str = ""
    objective: str = ""
    limit: int = 20
    report_date: str = ""


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


def parse_financial_research_command(text: str) -> FinancialResearchOptions:
    parser = argparse.ArgumentParser(prog="/financial-research", add_help=False)
    parser.add_argument("command")
    parser.add_argument("symbol")
    parser.add_argument("--broker", default="")
    args = parser.parse_args((text or "").split())
    return FinancialResearchOptions(symbol=args.symbol.strip().upper(), broker=args.broker.strip().lower())


def parse_research_reports_command(text: str) -> ResearchReportCatalogOptions:
    parser = argparse.ArgumentParser(prog="/research-reports", add_help=False)
    parser.add_argument("command")
    parser.add_argument("symbol", nargs="?", default="")
    parser.add_argument("--objective", default="")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args((text or "").split())
    return ResearchReportCatalogOptions(
        symbol=args.symbol.strip().upper(),
        objective=args.objective.strip(),
        limit=max(1, int(args.limit)),
    )


def parse_open_research_command(text: str) -> ResearchReportCatalogOptions:
    parser = argparse.ArgumentParser(prog="/open-research", add_help=False)
    parser.add_argument("command")
    parser.add_argument("symbol", nargs="?", default="")
    parser.add_argument("--objective", default="financial_research")
    parser.add_argument("--date", default="")
    args = parser.parse_args((text or "").split())
    return ResearchReportCatalogOptions(
        symbol=args.symbol.strip().upper(),
        objective=args.objective.strip() or "financial_research",
        limit=20,
        report_date=args.date.strip(),
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
                extract_and_store_facts_from_pages(
                    db,
                    broker_report_id=int(report["broker_report_id"]),
                    symbol=str(report["symbol"]),
                    pages=list(parse_result.get("pages") or []),
                )
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


def _symbol_from_research_command(text: str) -> str:
    parts = (text or "").split()
    if len(parts) >= 3 and parts[0].lower() == "/report" and parts[1].lower() == "broker":
        return parts[2].strip().upper()
    if len(parts) >= 3 and parts[0].lower() == "/deep-research":
        return parts[1].strip().upper()
    if len(parts) >= 2:
        return parts[1].strip().upper()
    raise ValueError("symbol is required")


def handle_broker_research_command(
    text: str,
    *,
    conn: Any | None = None,
    output_dir="reports/broker_research",
    latest_dir="reports/latest",
) -> str:
    symbol = _symbol_from_research_command(text)
    own_conn = conn is None
    db = conn or connect()
    try:
        facts = list_broker_research_facts(db, symbol=symbol)
        consensus = build_broker_consensus(symbol=symbol, facts=facts)
        markdown = render_broker_research_markdown(symbol=symbol, consensus=consensus, facts=facts)
        paths = write_broker_research_report(
            symbol=symbol,
            markdown=markdown,
            output_dir=output_dir,
            latest_dir=latest_dir,
        )
        run_id = record_broker_research_run(
            db,
            symbol=symbol,
            objective="broker_research",
            broker_filter="public",
            status="ok",
            coverage=consensus,
            report_markdown_path=paths["markdown_path"],
            report_html_path=paths["html_path"],
        )
        return "\n".join(
            [
                f"━━━ {DISCLAIMER} ━━━",
                "",
                f"## Broker Research: {symbol}",
                "",
                f"- Run ID: {run_id}",
                f"- Broker facts: {len(facts)}",
                f"- Brokers covered: {consensus['broker_count']}",
                f"- Markdown: {paths['markdown_path']}",
                f"- HTML: {paths['html_path']}",
            ]
        )
    finally:
        if own_conn:
            db.close()


def _llm_synthesis_from_backend(llm_backend: Any, prompt: str) -> str:
    if llm_backend is None:
        return ""
    try:
        response = llm_backend.chat(
            [
                {
                    "role": "system",
                    "content": "You produce concise, evidence-grounded financial analyst research. Do not give investment advice.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=4000,
        )
        return str(response.get("content") or "").strip()
    except Exception:
        return ""


def handle_financial_research_command(
    text: str,
    *,
    conn: Any | None = None,
    output_dir="reports/financial_research",
    latest_dir="reports/latest",
    llm_backend: Any | None = None,
    llm_synthesizer=None,
) -> str:
    options = parse_financial_research_command(text)
    own_conn = conn is None
    db = conn or connect()
    try:
        facts = list_broker_research_facts(db, symbol=options.symbol)
        if options.broker:
            facts = [fact for fact in facts if str(fact.get("broker_code") or "").lower() == options.broker]
        pages = list_broker_report_pages(db, symbol=options.symbol, broker=options.broker)
        consensus = build_broker_consensus(symbol=options.symbol, facts=facts)
        agent_adda_context = fetch_agent_adda_pg_context(db, symbol=options.symbol)
        prompt = build_llm_financial_prompt(
            symbol=options.symbol,
            consensus=consensus,
            facts=facts,
            pages=pages,
            agent_adda_context=agent_adda_context,
        )
        if llm_synthesizer is not None:
            llm_view = str(llm_synthesizer(prompt) or "")
        else:
            llm_view = _llm_synthesis_from_backend(llm_backend, prompt)
        markdown = build_financial_analyst_markdown(
            symbol=options.symbol,
            consensus=consensus,
            facts=facts,
            pages=pages,
            llm_view=llm_view,
            agent_adda_context=agent_adda_context,
        )
        paths = write_financial_analyst_report(
            symbol=options.symbol,
            markdown=markdown,
            output_dir=output_dir,
            latest_dir=latest_dir,
        )
        run_id = record_broker_research_run(
            db,
            symbol=options.symbol,
            objective="financial_research",
            broker_filter=options.broker or "public",
            status="ok",
            coverage={
                "broker_count": consensus.get("broker_count", 0),
                "broker_filter": options.broker or "public",
                "facts": len(facts),
                "pages": len(pages),
                "llm_synthesis": bool(llm_view),
                "agent_adda_pg_context": bool(agent_adda_context.get("available")),
            },
            report_markdown_path=paths["markdown_path"],
            report_html_path=paths["html_path"],
        )
        return "\n".join(
            [
                f"━━━ {DISCLAIMER} ━━━",
                "",
                f"## Financial Research: {options.symbol}",
                "",
                f"- Run ID: {run_id}",
                f"- Broker facts: {len(facts)}",
                f"- Parsed pages: {len(pages)}",
                f"- LLM synthesis: {'yes' if llm_view else 'not available; deterministic analyst sections used'}",
                f"- Markdown: {paths['markdown_path']}",
                f"- HTML: {paths['html_path']}",
            ]
        )
    finally:
        if own_conn:
            db.close()


def handle_research_reports_command(text: str, *, conn: Any | None = None) -> str:
    options = parse_research_reports_command(text)
    own_conn = conn is None
    db = conn or connect()
    try:
        rows = list_broker_research_runs(
            db,
            symbol=options.symbol,
            objective=options.objective,
            limit=options.limit,
        )
        title_symbol = options.symbol or "ALL"
        lines = [f"━━━ {DISCLAIMER} ━━━", "", f"## Research Reports: {title_symbol}", ""]
        if not rows:
            lines.append("No cataloged research reports found.")
            return "\n".join(lines)
        lines.extend(["| Run | As Of | Symbol | Objective | Broker | Status | HTML |", "|---:|---|---|---|---|---|---|"])
        for row in rows:
            lines.append(
                "| {run} | {as_of} | {symbol} | {objective} | {broker} | {status} | {html} |".format(
                    run=row.get("research_run_id") or "",
                    as_of=row.get("as_of") or "",
                    symbol=row.get("symbol") or "",
                    objective=row.get("objective") or "",
                    broker=row.get("broker_filter") or "",
                    status=row.get("status") or "",
                    html=row.get("report_html_path") or "",
                )
            )
        return "\n".join(lines)
    finally:
        if own_conn:
            db.close()


def handle_open_research_command(text: str, *, conn: Any | None = None, opener=None) -> str:
    options = parse_open_research_command(text)
    own_conn = conn is None
    db = conn or connect()
    try:
        rows = list_broker_research_runs(
            db,
            symbol=options.symbol,
            objective=options.objective,
            limit=options.limit,
        )
        if options.report_date:
            rows = [row for row in rows if str(row.get("as_of") or "").startswith(options.report_date)]
        if not rows:
            return "\n".join(
                [
                    f"━━━ {DISCLAIMER} ━━━",
                    "",
                    f"## Open Research: {options.symbol or 'ALL'}",
                    "",
                    "No matching cataloged research report found.",
                ]
            )
        path = str(rows[0].get("report_html_path") or rows[0].get("report_markdown_path") or "")
        if not path:
            return "Cataloged report has no file path."
        open_fn = opener or (lambda p: subprocess.run(["open", p], check=False))
        open_fn(path)
        return "\n".join(
            [
                f"━━━ {DISCLAIMER} ━━━",
                "",
                f"## Open Research: {options.symbol or rows[0].get('symbol') or 'ALL'}",
                "",
                f"Opened research report: {path}",
            ]
        )
    finally:
        if own_conn:
            db.close()


def _parse_broker_crawl_command(text: str) -> tuple[str, int | None]:
    parser = argparse.ArgumentParser(prog="/broker-crawl", add_help=False)
    parser.add_argument("command")
    parser.add_argument("symbol")
    parser.add_argument("--max-sources", type=int, default=0)
    args = parser.parse_args((text or "").split())
    return args.symbol.strip().upper(), (int(args.max_sources) or None)


def handle_broker_crawl_command(
    text: str,
    *,
    conn: Any | None = None,
    runner=None,
) -> str:
    from .scheduler import run_scheduled_broker_crawl

    symbol, max_sources = _parse_broker_crawl_command(text)
    own_conn = conn is None
    db = conn or connect()
    run = runner or run_scheduled_broker_crawl
    try:
        result = run(conn=db, symbol=symbol, max_sources=max_sources)
        lines = [
            f"━━━ {DISCLAIMER} ━━━",
            "",
            f"## Broker Crawl: {result.symbol}",
            "",
            f"- Sources scanned: {result.sources_seen}",
            f"- Sources succeeded: {result.sources_succeeded}",
            f"- Sources failed: {result.sources_failed}",
            f"- Skipped sources: {result.skipped_sources}",
            f"- Links discovered: {result.links_discovered}",
            f"- Reports stored: {result.reports_stored}",
        ]
        if result.failures:
            lines.extend(["", "## Failures"])
            for failure in result.failures:
                lines.append(f"- {failure['broker_code']}: {failure['error']}")
        return "\n".join(lines)
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
