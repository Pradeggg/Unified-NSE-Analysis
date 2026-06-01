"""Renderer for stock_results and collective_news_results intents.

The _render_stock_results_block function is also used by entity.py.
"""

import re
import time
import os as _os
import datetime as _dt

from terminal.renderers._base import _get, _source_trail_lines, FOOTER
from terminal.tools import call_tool


# ─── URL / title helpers ─────────────────────────────────────────────────────

def _is_junk_url(url: str) -> bool:
    if not url:
        return False
    u = url.lower()
    return any(j in u for j in (
        "duckduckgo.com/y.js",
        "bing.com/aclick",
        "investilo.ai",
        "msclkid=",
        "/y.js?ad_domain=",
    ))


def _clean_title(t: str) -> str:
    t = (t or "").strip()
    for noise in (
        "| BSE", "|BSE", " - BSE", " | NSE", "LIVE Stock/Share Market",
        "Today's Stock Market News", "AI-Powered Stock Analysis",
    ):
        if noise in t:
            t = t.replace(noise, "").strip()
    # Strip screener.in relative-time badge glued to title (e.g. "Acquisition1d", "Dividend23h")
    t = re.sub(r"([A-Za-z\)])(\d+[dhm])(?=\s|-|$)", r"\1", t)
    # Insert missing space between digits and lowercase word (e.g. "2025from bse")
    t = re.sub(r"(\d)([a-z])", r"\1 \2", t)
    return re.sub(r"\s{2,}", " ", t).rstrip(" |").strip()


def _classify_filing(title: str, url: str) -> tuple[str, int]:
    t = (title or "").lower()
    u = (url or "").lower()
    if any(k in t for k in (
        "investor presentation", "investor update",
        "earnings presentation", "results presentation",
    )):
        return ("investor_pres", 1)
    if any(k in t for k in (
        "outcome of board meeting", "outcomeofbm", "outcome of bm",
        "financial results", "audited financial", "unaudited financial",
        "quarterly results", "quarterly result", "earnings release",
        "results - sebi", "results-sebi",
    )):
        return ("earnings_outcome", 2)
    if any(k in t for k in ("transcript", "concall transcript", "earnings call")):
        return ("transcript", 3)
    if "annual report" in t or "annualreport" in u or "bseplus/annualreport" in u:
        return ("annual_report", 4)
    return ("other", 9)


def _is_analyzable_pdf(url: str) -> bool:
    if not url:
        return False
    u = url.lower()
    if u.endswith(".pdf"):
        return True
    return any(k in u for k in (
        "annpdfopen", "attachlive", "attachhis",
        "bseplus/annualreport", "/corpfiling/",
    ))


# ─── _first_nonempty_row (shared with stock_brief) ───────────────────────────

def _first_nonempty_row(table: dict, labels: tuple) -> tuple | None:
    """Match each label loosely: ignores trailing '+' / '%' and is case-insensitive."""
    def _norm(s: str) -> str:
        return (s or "").replace("+", "").replace("%", "").strip().lower()
    wanted = {_norm(label) for label in labels}
    for key, values in (table or {}).items():
        if key.startswith("_"):
            continue
        if _norm(key) in wanted and isinstance(values, list) and any(str(v).strip() for v in values):
            return key, values
    return None


# ─── Main block renderer ─────────────────────────────────────────────────────

def _render_stock_results_block(symbol: str, lines: list[str], tool_results: list[dict]) -> None:
    """Append stock results sections to *lines* in place.

    Replaces the _render_stock_results nested closure from agent.py.
    All outer-scope vars are resolved locally via _get().
    """
    scr_fund = _get(tool_results, "scrape_screener_in")
    nse_ann = _get(tool_results, "search_nse_announcements")
    bse_filings = _get(tool_results, "search_bse_filings")
    concalls = _get(tool_results, "search_concall_transcripts")
    cat = _get(tool_results, "search_latest_catalysts")
    nse_intraday = _get(tool_results, "get_nse_intraday_snapshot")  # noqa: F841 (kept for parity)

    q = (scr_fund or {}).get("quarterly") or {}
    q_headers = q.get("_headers") if isinstance(q, dict) else []
    annual = (scr_fund or {}).get("annual_pl") or {}
    annual_headers = annual.get("_headers") if isinstance(annual, dict) else []
    ratios = (scr_fund or {}).get("ratios") or {}

    lines.append(f"━━━ {symbol or (scr_fund or {}).get('symbol', 'Stock')} — Latest Results Evidence ━━━")
    lines.append("")

    # LATEST PERIOD SUMMARY — reconcile period from available sources
    period_sources: list[str] = []
    period_label = ""
    if q_headers:
        last_q = str(q_headers[-1])
        period_label = f"Quarter ending {last_q}"
        period_sources.append(f"screener {last_q}")
    annual_hdrs_local = annual_headers or []
    if annual_hdrs_local:
        period_sources.append(f"annual {annual_hdrs_local[-1]}")
    for item in (nse_ann or {}).get("bse_filings") or (nse_ann or {}).get("nse_filings") or []:
        if not isinstance(item, dict):
            continue
        t_low = (item.get("title") or item.get("subject") or "").lower()
        if any(k in t_low for k in (
            "financial results", "outcome of board meeting",
            "audited results", "unaudited results", "outcomeofbm",
        )):
            d = item.get("date") or item.get("published")
            if d:
                period_sources.append(f"BSE filing {d}")
            break
    if period_label or period_sources:
        lines.append("▶ LATEST PERIOD SUMMARY")
        if period_label:
            lines.append(f"  Period: {period_label}")
        if period_sources:
            lines.append(f"  Reconciled from: {' · '.join(period_sources[:4])}")
        lines.append("")

    lines.append("▶ FINANCIAL SNAPSHOT")
    if ratios:
        snap_keys = (
            ("Market Cap", "₹ Cr"),
            ("Current Price", "₹"),
            ("Stock P/E", ""),
            ("ROE", "%"),
            ("ROCE", "%"),
            ("Book Value", "₹"),
            ("Dividend Yield", "%"),
            ("Debt to equity", ""),
            ("EPS", "₹"),
            ("Promoter holding", "%"),
        )
        snap_rows: list[tuple[str, str]] = []
        for k, unit in snap_keys:
            v = ratios.get(k)
            if v:
                snap_rows.append((k, f"{v}" + (f" {unit}" if unit and unit not in str(v) else "")))
        if snap_rows:
            lines.append("")
            lines.append("  | Metric             | Value                |")
            lines.append("  |--------------------|----------------------|")
            for k, v in snap_rows:
                lines.append(f"  | {k[:18]:<18} | {str(v)[:20]:<20} |")
            lines.append("")

    # Quarterly P&L as a real markdown table
    if q_headers:
        quarterly_metrics = []
        for labels in (
            ("Sales", "Revenue", "Operating Revenue"),
            ("Expenses",),
            ("Operating Profit",),
            ("OPM %",),
            ("Net Profit", "Profit after tax", "PAT"),
            ("EPS in Rs", "EPS"),
        ):
            row = _first_nonempty_row(q, labels)
            if row:
                quarterly_metrics.append(row)
        if quarterly_metrics:
            lines.append("▶ QUARTERLY P&L (₹ Cr — last 6 quarters)")
            lines.append("")
            hdr_cells = [str(h) for h in q_headers[:6]]
            lines.append("  | Metric              | " + " | ".join(f"{h:>10}" for h in hdr_cells) + " |")
            lines.append("  |---------------------|" + ("------------|" * len(hdr_cells)))
            for label, values in quarterly_metrics:
                padded = (values[:6] + [""] * (len(hdr_cells) - len(values[:6])))
                cells = " | ".join(f"{str(v or '—'):>10}" for v in padded)
                lines.append(f"  | {_clean_title(label)[:19]:<19} | {cells} |")
            lines.append("")
        elif scr_fund and scr_fund.get("error"):
            lines.append(f"  Screener unavailable: {scr_fund.get('error')}")
            lines.append("")

    # Annual P&L as a real markdown table
    if annual_headers and isinstance(annual, dict):
        annual_metrics = []
        for labels in (
            ("Sales", "Revenue"),
            ("Expenses",),
            ("Operating Profit",),
            ("OPM %",),
            ("Net Profit", "Profit after tax", "PAT"),
            ("EPS in Rs", "EPS"),
            ("Dividend Payout %",),
        ):
            row = _first_nonempty_row(annual, labels)
            if row:
                annual_metrics.append(row)
        if annual_metrics:
            lines.append("▶ ANNUAL P&L (₹ Cr — last 5 years)")
            lines.append("")
            hdr_cells = [str(h) for h in annual_headers[:5]]
            lines.append("  | Metric              | " + " | ".join(f"{h:>10}" for h in hdr_cells) + " |")
            lines.append("  |---------------------|" + ("------------|" * len(hdr_cells)))
            for label, values in annual_metrics:
                padded = (values[:5] + [""] * (len(hdr_cells) - len(values[:5])))
                cells = " | ".join(f"{str(v or '—'):>10}" for v in padded)
                lines.append(f"  | {_clean_title(label)[:19]:<19} | {cells} |")
            lines.append("")

    # Pros / Cons from screener
    pros = (scr_fund or {}).get("pros") or []
    cons = (scr_fund or {}).get("cons") or []
    if pros or cons:
        lines.append("▶ SCREENER ANALYSIS")
        if pros:
            lines.append("  Pros:")
            for p in pros[:4]:
                lines.append(f"    • {p}")
        if cons:
            lines.append("  Cons:")
            for c in cons[:4]:
                lines.append(f"    • {c}")
        lines.append("")

    # Consolidated filings: dedupe across NSE/screener announcements / BSE filings
    lines.append("▶ RESULT FILINGS & ANNOUNCEMENTS")
    seen_urls: set[str] = set()
    rendered_count = 0
    max_filings = 8

    def _emit_filing(title: str, url: str, date: str = "", category: str = "") -> bool:
        nonlocal rendered_count
        if rendered_count >= max_filings or _is_junk_url(url):
            return False
        key = (url or title).split("?")[0].rstrip("/")
        if key in seen_urls:
            return False
        seen_urls.add(key)
        t = _clean_title(title)[:100] or "Filing"
        cat_str = f"[{category}] " if category else ""
        dt = f"{date} — " if date else ""
        url_part = f"\n      {url}" if url else ""
        lines.append(f"  • {cat_str}{dt}{t}{url_part}")
        rendered_count += 1
        return True

    # 1. NSE/BSE corporate announcements (highest signal — actual filings)
    nse_payload = nse_ann or {}
    if not nse_payload.get("error"):
        for item in (
            nse_payload.get("results")
            or nse_payload.get("announcements")
            or nse_payload.get("bse_filings")
            or nse_payload.get("nse_filings")
            or []
        ):
            if not isinstance(item, dict):
                continue
            _emit_filing(
                item.get("title") or item.get("subject") or item.get("desc") or "",
                item.get("url") or item.get("link") or item.get("pdf_url") or item.get("att_url") or "",
                item.get("date") or item.get("published") or "",
            )
    # 2. Screener.in announcements (often duplicates the above — dedupe handles it)
    for item in (scr_fund or {}).get("announcements") or []:
        if isinstance(item, dict):
            _emit_filing(item.get("title", ""), item.get("url", ""))
    # 3. BSE filings from DDG search (lower signal — only fill remaining slots,
    # and only with deep filings/results URLs not generic company-quote pages)
    bse_payload = bse_filings or {}
    if not bse_payload.get("error"):
        bse_results = bse_payload.get("results") or {}
        if isinstance(bse_results, dict):
            for cat_key, group in bse_results.items():
                if not isinstance(group, list):
                    continue
                for entry in group:
                    if not isinstance(entry, dict):
                        continue
                    url = entry.get("url") or ""
                    # Only accept BSE filings/results/board-meeting pages
                    if not any(s in url for s in (
                        "/financials-results/", "/board-meetings/",
                        "/financials-annual-reports/", "comp_results.aspx",
                        "AttachLive", "AttachHis",
                    )):
                        continue
                    _emit_filing(entry.get("title", ""), url, category=cat_key)
    if rendered_count == 0:
        lines.append("  No recent result filing links were returned.")
    lines.append("")

    # Concall transcripts — dedupe and prefer transcript > ppt > recording
    lines.append("▶ CONCALL / MANAGEMENT COMMENTARY")
    screener_concalls = (scr_fund or {}).get("concalls") or []
    rendered_concalls = 0
    for item in screener_concalls[:5]:
        if not isinstance(item, dict):
            continue
        period = item.get("period") or "Period"
        link_parts: list[str] = []
        for key, label in (
            ("transcript_url", "Transcript"),
            ("ppt_url", "PPT"),
            ("recording_url", "Recording"),
        ):
            u = item.get(key)
            if u and not _is_junk_url(u):
                link_parts.append(f"{label}: {u}")
        if link_parts:
            lines.append(f"  • {period}")
            for lp in link_parts:
                lines.append(f"      {lp}")
            rendered_concalls += 1
    if rendered_concalls == 0:
        concall_items = (concalls or {}).get("results") or (concalls or {}).get("items") or []
        for item in concall_items[:3]:
            if isinstance(item, dict):
                url = item.get("url") or item.get("link") or ""
                if _is_junk_url(url):
                    continue
                title = _clean_title(item.get("title") or item.get("headline") or "")
                if title:
                    lines.append(f"  • {title}" + (f"\n      {url}" if url else ""))
                    rendered_concalls += 1
    if rendered_concalls == 0:
        lines.append("  No concall transcript or presentation link was returned.")
    lines.append("")

    # Latest catalysts — filter junk URLs
    lines.append("▶ LATEST CATALYSTS")
    catalyst_items = (
        (cat or {}).get("results") or (cat or {}).get("items") or []
        if isinstance(cat, dict) else []
    )
    rendered_catalysts = 0
    for item in catalyst_items[:6]:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("link") or ""
        if _is_junk_url(url):
            continue
        title = _clean_title(item.get("title") or item.get("headline") or "")
        if not title:
            continue
        lines.append(f"  • {title}" + (f"\n      {url}" if url else ""))
        rendered_catalysts += 1
        if rendered_catalysts >= 5:
            break
    if rendered_catalysts == 0:
        if isinstance(cat, dict) and cat.get("error"):
            lines.append(f"  ERROR: {cat.get('error')}")
        else:
            lines.append("  No latest catalyst items were returned.")
    lines.append("")

    # ── DEEP-DIVE INSIGHTS: recursively /analyze top 2 PDFs for the latest period ──
    deep_candidates: list[dict] = []

    # Primary: screener concalls list (clean, period-grouped, latest-first)
    for entry in ((scr_fund or {}).get("concalls") or [])[:3]:
        if not isinstance(entry, dict):
            continue
        period = entry.get("period") or ""
        # Prefer PPT (= investor presentation), then transcript
        if entry.get("ppt_url") and not _is_junk_url(entry["ppt_url"]):
            deep_candidates.append({
                "title": f"{period} Investor Presentation",
                "url": entry["ppt_url"], "rank": 1, "kind": "investor_pres",
            })
        if entry.get("transcript_url") and not _is_junk_url(entry["transcript_url"]):
            deep_candidates.append({
                "title": f"{period} Earnings Call Transcript",
                "url": entry["transcript_url"], "rank": 2, "kind": "earnings_outcome",
            })

    nse_payload = nse_ann or {}
    if not nse_payload.get("error"):
        for item in (
            nse_payload.get("results")
            or nse_payload.get("announcements")
            or nse_payload.get("bse_filings")
            or nse_payload.get("nse_filings")
            or []
        ):
            if not isinstance(item, dict):
                continue
            title = item.get("title") or item.get("subject") or ""
            url = (
                item.get("url") or item.get("link")
                or item.get("pdf_url") or item.get("att_url") or ""
            )
            if not _is_analyzable_pdf(url) or _is_junk_url(url):
                continue
            kind, rank = _classify_filing(title, url)
            if kind in ("investor_pres", "earnings_outcome"):
                deep_candidates.append({"title": title, "url": url, "rank": rank, "kind": kind})
    for item in (scr_fund or {}).get("announcements") or []:
        if not isinstance(item, dict):
            continue
        title = item.get("title", "")
        url = item.get("url", "")
        if not _is_analyzable_pdf(url) or _is_junk_url(url):
            continue
        kind, rank = _classify_filing(title, url)
        if kind in ("investor_pres", "earnings_outcome"):
            deep_candidates.append({"title": title, "url": url, "rank": rank, "kind": kind})

    # Dedupe by URL stem, sort by rank, take top 2
    _seen_urls: set[str] = set()
    _uniq: list[dict] = []
    for c in deep_candidates:
        key = c["url"].split("?")[0].rstrip("/")
        if key in _seen_urls:
            continue
        _seen_urls.add(key)
        _uniq.append(c)
    _uniq.sort(key=lambda x: x["rank"])
    picks = _uniq[:2]

    if picks:
        lines.append("▶ DEEP-DIVE INSIGHTS (recursive /analyze on top filings)")
        deadline = time.time() + 120
        for pick in picks:
            if time.time() > deadline:
                lines.append("  • Skipped remaining picks: 120s time budget exceeded")
                break
            kind_label = pick["kind"].replace("_", " ").title()
            lines.append("")
            lines.append(f"  ◆ {kind_label}: {_clean_title(pick['title'])[:110]}")
            lines.append(f"    Source: {pick['url']}")
            try:
                analysis = call_tool("analyze_document", {
                    "source": pick["url"], "max_pages": 40,
                    "vision_fallback": True,
                })
            except Exception as exc:
                lines.append(f"    Analysis error: {exc}")
                continue
            # Append to tool_results so SOURCE TRAIL reflects recursive call
            tool_results.append({
                "tool": "analyze_document",
                "args": {"source": pick["url"]},
                "result": analysis if isinstance(analysis, dict) else {"text": str(analysis)},
            })
            if not isinstance(analysis, dict):
                lines.append("    (no parsed content)")
                continue
            if analysis.get("error"):
                lines.append(f"    Analysis error: {analysis.get('error')}")
                continue
            page_list = analysis.get("pages") or analysis.get("page_texts") or []
            if not isinstance(page_list, list):
                page_list = []
            page_count = (
                analysis.get("total_pages")
                or analysis.get("page_count")
                or len(page_list)
            )
            text = (analysis.get("text") or analysis.get("content") or "").strip()
            if not text and page_list:
                text = "\n\n".join(
                    (pt.get("text") or "").strip()
                    for pt in page_list if isinstance(pt, dict)
                ).strip()
            if isinstance(page_count, int) and page_count > 0:
                lines.append(f"    Pages parsed: {page_count}")
            if text:
                preview = text[:1500].strip()
                shown_lines = 0
                for raw in preview.splitlines():
                    ln = raw.strip()
                    if not ln:
                        continue
                    lines.append(f"    {ln[:140]}")
                    shown_lines += 1
                    if shown_lines >= 25:
                        break
                if len(text) > 1500:
                    lines.append(
                        f"    … (preview truncated — full {len(text):,} chars in MD report)"
                    )
            else:
                lines.append("    (no extractable text)")
        lines.append("")


# ─── Intent renderers ─────────────────────────────────────────────────────────

def render_collective_news(tool_results: list[dict]) -> str:
    """Render the collective_news_results intent."""
    per_symbol = [
        tr.get("result") for tr in tool_results
        if tr.get("tool") == "get_latest_results"
        and isinstance(tr.get("result"), dict)
    ]
    ev_summary = None
    for tr in tool_results:
        if tr.get("tool") == "get_event_calendar_summary" and isinstance(tr.get("result"), dict):
            ev_summary = tr.get("result")
            break

    symbols_listed = [(r.get("symbol") or "—") for r in per_symbol]
    header_syms = ", ".join(symbols_listed) if symbols_listed else "—"

    lines: list[str] = []
    lines.append(f"━━━ Latest Results + Upcoming Events — {header_syms} ━━━")
    lines.append("")

    if not per_symbol:
        lines.append("  No get_latest_results data was collected.")
    for res in per_symbol:
        sym_r = res.get("symbol") or "—"
        lines.append(f"▶ {sym_r} — Latest Results")
        lines.append(f"  Status: {res.get('status', 'unknown')}")
        lines.append(f"  Period: {res.get('period', 'latest')}")
        selected = res.get("selected_filing") or {}
        if selected:
            title = selected.get("title") or selected.get("url") or "N/A"
            lines.append(f"  Filing: {title}")
            if selected.get("source"):
                lines.append(f"  Source: {selected.get('source')}")
        warning = res.get("warning") or {}
        if warning.get("message"):
            lines.append(f"  ⚠ {warning.get('message')}")
        facts = res.get("facts") or {}
        fact_bits: list[str] = []
        for label, key in (("Revenue", "revenue"), ("PAT", "pat"), ("EPS", "eps")):
            item = facts.get(key)
            if item:
                fact_bits.append(
                    f"{label} {item.get('value')} ({item.get('period', 'latest')})"
                )
        if fact_bits:
            lines.append("  " + " · ".join(fact_bits))
        missing = res.get("missing_facts") or []
        if missing:
            lines.append("  Missing: " + ", ".join(missing))
        lines.append("")

    if ev_summary and not ev_summary.get("error"):
        lines.append("▶ UPCOMING CORPORATE EVENTS")
        lines.append(
            f"  Index: {ev_summary.get('index', '—')} | "
            f"Window: {ev_summary.get('days_ahead', '—')} days | "
            f"Total: {ev_summary.get('total_events', '—')}"
        )
        counts = ev_summary.get("event_counts") or {}
        if counts:
            lines.append("  Mix: " + " | ".join(f"{k}: {v}" for k, v in counts.items()))
        requested = {(s or "").upper() for s in symbols_listed if s and s != "—"}
        all_events = ev_summary.get("events") or []
        matched = [ev for ev in all_events if (ev.get("symbol") or "").upper() in requested]
        shown = matched if matched else all_events[:10]
        if shown:
            lines.append("  Upcoming:")
            for ev in shown[:15]:
                lines.append(
                    f"    - {ev.get('symbol', '—')} | {ev.get('type', '—')} | "
                    f"{ev.get('ex_date', '—')} | {ev.get('detail', '—')}"
                )
        elif requested:
            lines.append(
                "  No upcoming events found for the requested symbols in the calendar window."
            )
        lines.append("")
    elif ev_summary and ev_summary.get("error"):
        lines.append(f"▶ UPCOMING CORPORATE EVENTS\n  ⚠ {ev_summary.get('error')}")
        lines.append("")

    lines.append("▶ SOURCE TRAIL")
    for trail_line in _source_trail_lines(tool_results):
        lines.append(trail_line)
    lines.append(f"\n{FOOTER}")
    return "\n".join(lines)


def render_stock_results(tool_results: list[dict]) -> str:
    """Render the stock_results intent."""
    latest_results = _get(tool_results, "get_latest_results")
    scr_fund = _get(tool_results, "scrape_screener_in")
    snap = _get(tool_results, "get_symbol_snapshot")
    tech = _get(tool_results, "get_technical_setup")
    forensic = _get(tool_results, "run_forensic_analysis")

    # Backfill scr_fund from comprehensive_stock_research if needed
    research = _get(tool_results, "comprehensive_stock_research") or {}
    if not scr_fund and isinstance(research, dict):
        emb = research.get("screener")
        if isinstance(emb, dict):
            scr_fund = emb

    sym = (snap or {}).get("symbol") or (tech or {}).get("symbol") or ""
    if not sym and forensic:
        sym = forensic.get("symbol") or ""

    lines: list[str] = []

    if latest_results:
        lines.append(f"━━━ {latest_results.get('symbol', 'SYMBOL')} — Latest Results Evidence ━━━")
        lines.append("")
        lines.append("▶ LATEST RESULTS PACK")
        lines.append(f"  Status: {latest_results.get('status', 'unknown')}")
        lines.append(f"  Period: {latest_results.get('period', 'latest')}")
        selected = latest_results.get("selected_filing") or {}
        if selected:
            lines.append(
                f"  Selected filing: {selected.get('title') or selected.get('url') or 'N/A'}"
            )
            if selected.get("source"):
                lines.append(f"  Filing source:   {selected.get('source')}")
        warning = latest_results.get("warning") or {}
        if warning.get("message"):
            lines.append(f"  ⚠ {warning.get('message')}")
        facts = latest_results.get("facts") or {}
        if facts:
            lines.append("")
            lines.append("▶ RECONCILED FACTS")
            for label, key in (("Revenue", "revenue"), ("PAT", "pat"), ("EPS", "eps")):
                item = facts.get(key)
                if item:
                    lines.append(
                        f"  {label}: {item.get('value')} "
                        f"({item.get('period', 'latest')} · {item.get('source', 'source unavailable')})"
                    )
        missing = latest_results.get("missing_facts") or []
        if missing:
            lines.append("")
            lines.append("▶ MISSING FACTS")
            lines.append("  " + ", ".join(missing))
        if latest_results.get("summary"):
            lines.append("")
            lines.append("▶ SUMMARY")
            for line in str(latest_results.get("summary")).splitlines():
                lines.append(f"  {line}")
    else:
        _render_stock_results_block(sym or (scr_fund or {}).get("symbol", ""), lines, tool_results)

    lines.append("▶ SOURCE TRAIL")
    if latest_results and isinstance(latest_results.get("source_trail"), dict):
        for tool, status in latest_results["source_trail"].items():
            lines.append(f"  {tool}: {status}")
    else:
        for trail_line in _source_trail_lines(tool_results):
            lines.append(trail_line)
    lines.append(f"\n{FOOTER}")
    body = "\n".join(lines)

    # Save Markdown deep-dive report alongside the terminal output
    try:
        symbol_out = (sym or (scr_fund or {}).get("symbol") or "RESULTS").upper()
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = _os.path.join(_os.getcwd(), "reports", "generated")
        _os.makedirs(out_dir, exist_ok=True)
        md_path = _os.path.join(out_dir, f"{symbol_out}_results_{ts}.md")
        md_chunks = [f"# {symbol_out} — Latest Results Deep-Dive", "", body, ""]
        doc_dumps = [tr for tr in tool_results if tr.get("tool") == "analyze_document"]
        if doc_dumps:
            md_chunks.append("\n---\n\n## Appendix: Full Document Text (recursive /analyze)\n")
            for tr in doc_dumps:
                src = (tr.get("args") or {}).get("source", "")
                res = tr.get("result") if isinstance(tr.get("result"), dict) else {}
                md_chunks.append(f"### Source: {src}\n")
                if res.get("error"):
                    md_chunks.append(f"_Error: {res.get('error')}_\n")
                else:
                    full_text = res.get("text") or res.get("content") or ""
                    if not full_text:
                        pts = res.get("pages") or res.get("page_texts") or []
                        if isinstance(pts, list) and pts:
                            full_text = "\n\n".join(
                                f"### Page {pt.get('page', i + 1)}\n\n{(pt.get('text') or '').strip()}"
                                for i, pt in enumerate(pts) if isinstance(pt, dict)
                            )
                    if full_text:
                        if len(full_text) > 50000:
                            md_chunks.append(full_text[:50000])
                            md_chunks.append(
                                f"\n_(truncated at 50000 chars — original {len(full_text):,} chars)_"
                            )
                        else:
                            md_chunks.append(full_text)
                    else:
                        md_chunks.append("_(no text extracted)_")
                md_chunks.append("")
        with open(md_path, "w", encoding="utf-8") as _f:
            _f.write("\n".join(md_chunks))
        body += f"\n\n📄 Deep-dive report saved: {md_path}"
    except Exception as _save_exc:
        body += f"\n\n⚠ MD save failed: {_save_exc}"

    return body
