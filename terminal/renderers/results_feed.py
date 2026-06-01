"""Renderers for results_feed and forthcoming_results intents."""
from __future__ import annotations

import re

from terminal.renderers._base import _source_trail_lines, FOOTER


def _qtr(period: str) -> str:
    p = period.lower()
    if "first"  in p: return "Q1"
    if "second" in p: return "Q2"
    if "third"  in p: return "Q3"
    if "fourth" in p or "annual" in p: return "Q4"
    if "half"   in p: return "H1" if "first" in p else "H2"
    return period[:4]


def _fy(raw: str) -> str:
    # "2024-25" → FY25
    m = re.search(r"\d{4}-(\d{2})\b", raw)
    if m:
        return f"FY{m.group(1)}"
    # "01-Apr-2024" — Indian FY starts April; month >= 4 → next calendar year
    _MON = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
            "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
    m = re.search(r"\d{1,2}-([A-Za-z]{3})-(\d{4})", raw)
    if m:
        mo = _MON.get(m.group(1).lower(), 0)
        yr = int(m.group(2))
        fy_yr = yr + 1 if mo >= 4 else yr
        return f"FY{str(fy_yr)[-2:]}"
    m = re.search(r"(\d{4})", raw)
    if m:
        return f"FY{str(int(m.group(1)))[-2:]}"
    return raw[:5]


def _filed(raw: str) -> str:
    return raw[:11] if raw else ""


def _aud(raw: str) -> str:
    r = (raw or "").lower()
    if "un" in r: return "UA"
    if "aud" in r: return "A"
    return raw[:2]


def _cons(raw: str) -> str:
    r = (raw or "").lower()
    if "non" in r: return "NC"
    if "consol" in r: return "C"
    return raw[:2]


def render_results_feed(tool_results: list[dict]) -> str:
    """Render the latest quarterly results filing feed as a compact table."""
    lines: list[str] = []
    feed: dict = {}
    for tr in tool_results:
        if tr.get("tool") == "get_latest_results_feed":
            feed = tr.get("result") if isinstance(tr.get("result"), dict) else {}
            break

    rows = feed.get("results") or []
    days_back = feed.get("days_back", 7)
    lines.append(f"━━━ Latest Quarterly Results Feed — last {days_back} day(s) ━━━")

    note = feed.get("window_note") or ""
    if note:
        lines.append(f"  {note}")

    src = feed.get("source") or "n/a"
    total_avail = feed.get("total_available", "?")
    total_in_win = feed.get("total_in_window", 0)
    lines.append(f"  Source: {src}  ·  in-window: {total_in_win}  ·  available: {total_avail}")

    if feed.get("nse_error"):
        lines.append(f"  ⚠ NSE error: {feed.get('nse_error')}")

    if not rows:
        lines.append("\n  No results filings found.")
    else:
        lines.append("")
        lines.append("| # | Symbol | Company | Qtr | FY | Filed | A | C |")
        lines.append("|--:|--------|---------|:---:|:--:|-------|:-:|:-:|")
        for i, r in enumerate(rows[:50], 1):
            sym_c = (r.get("symbol") or "")[:14]
            co    = (r.get("company") or "")[:38]
            qtr   = _qtr(r.get("period") or "")
            fy    = _fy(r.get("financial_year") or r.get("from_date") or "")
            filed = _filed(r.get("filing_date") or "")
            aud   = _aud(r.get("audited") or "")
            cons  = _cons(r.get("consolidated") or "")
            lines.append(f"| {i} | {sym_c} | {co} | {qtr} | {fy} | {filed} | {aud} | {cons} |")

        xbrl_links = [
            (r.get("symbol", ""), r.get("xbrl_url", ""))
            for r in rows[:8] if r.get("xbrl_url")
        ]
        if xbrl_links:
            lines.append("")
            lines.append("▶ XBRL FILINGS (top 8)")
            for s_, u_ in xbrl_links:
                lines.append(f"  • {s_}: {u_}")

        lines.append("")
        lines.append(
            "  _A = Audited · UA = Un-Audited · C = Consolidated · NC = Non-Consolidated_"
        )

    lines.append("")
    lines.append("▶ SOURCE TRAIL")
    lines.extend(_source_trail_lines(tool_results))
    lines.append(FOOTER)
    return "\n".join(lines)


def render_forthcoming(tool_results: list[dict]) -> str:
    """Render upcoming results announcement calendar as a table."""
    lines: list[str] = []
    feed: dict = {}
    for tr in tool_results:
        if tr.get("tool") == "get_forthcoming_results":
            feed = tr.get("result") if isinstance(tr.get("result"), dict) else {}
            break

    rows = feed.get("results") or []
    days_ahead = feed.get("days_ahead", 14)
    lines.append(f"━━━ Forthcoming Results — next {days_ahead} day(s) ━━━")

    note = feed.get("window_note") or ""
    if note:
        lines.append(f"  {note}")

    src = feed.get("source") or "n/a"
    total_avail = feed.get("total_available", "?")
    total_in_win = feed.get("total_in_window", 0)
    lines.append(f"  Source: {src}  ·  in-window: {total_in_win}  ·  upcoming-total: {total_avail}")

    if feed.get("error"):
        lines.append(f"  ⚠ {feed.get('error')}")

    if not rows:
        lines.append("\n  No forthcoming results events found.")
    else:
        lines.append("")
        lines.append("| # | Date | Symbol | Company | Period / Notes |")
        lines.append("|--:|------|--------|---------|----------------|")
        for i, r in enumerate(rows[:50], 1):
            dt_   = (r.get("date") or "")[:12]
            sym_c = (r.get("symbol") or "")[:14]
            co    = (r.get("company") or "")[:36]
            desc  = (r.get("description") or r.get("purpose") or "")[:44]
            lines.append(f"| {i} | {dt_} | {sym_c} | {co} | {desc} |")

    lines.append("")
    lines.append("▶ SOURCE TRAIL")
    lines.extend(_source_trail_lines(tool_results))
    lines.append(FOOTER)
    return "\n".join(lines)
