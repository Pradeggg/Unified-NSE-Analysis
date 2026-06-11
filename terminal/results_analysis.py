"""Daily results analysis pipeline.

For every NSE company that filed quarterly results in the last N days, this
module assembles a structured evidence pack from the existing PG tables +
filing tools, runs an LLM analyst pass (JSON mode, strict schema), persists
the result into ``scores.results_analysis``, and renders a per-stock HTML
report plus an index page.

Composition of evidence (read-through, no fabrication):
  • ``scores.quarterly_results`` — last 8 quarters
  • ``scores.annual_results``    — last 5 years
  • ``scores.balance_sheet``     — last 3 years
  • ``scores.cash_flow``         — last 3 years
  • screener.in payload          — ratios, shareholding, peers, announcements
                                   (live → PG cache fallback via results_tools)
  • PDF/announcement filing      — ``terminal.results_tools.get_latest_results``
  • ``signals.insider_alerts``, ``signals.corporate_events``, ``signals.fii_dii_flows``
  • Credit-rating mentions       — best-effort scan of screener announcements

LLM is invoked through ``terminal.research_council.llm_client.call_llm_json``
so we get JSON-schema validation and the same OpenAI/Ollama cascade used by
the rest of the project.
"""

from __future__ import annotations

import datetime as _dt
import html as _html
import json
import os
import re
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

from terminal.financials_cache import DEFAULT_DSN

__all__ = [
    "build_evidence_pack",
    "analyze_with_llm",
    "analysis_has_placeholders",
    "deterministic_financial_analysis",
    "has_structured_financials",
    "insufficient_data_analysis",
    "persist_analysis",
    "render_stock_html",
    "render_index_html",
    "ANALYSIS_SCHEMA",
    "ANALYSIS_SYSTEM_PROMPT",
]


# ---------------------------------------------------------------------------
# PG read helpers (kept local so the module has no import-cycle with
# ``top_picks_report``; the queries mirror what that report uses).
# ---------------------------------------------------------------------------

def _fetchall(conn, sql: str, params: tuple = ()) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def _fetchone(conn, sql: str, params: tuple = ()) -> dict | None:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def _quarterly(conn, sym: str, n: int = 8) -> list[dict]:
    return _fetchall(conn, """
        SELECT period_label, period_end, revenue, expenses, operating_profit,
               opm_pct, other_income, interest, depreciation, pbt, tax_pct,
               pat, eps
        FROM scores.quarterly_results
        WHERE symbol=%s ORDER BY period_end DESC NULLS LAST LIMIT %s
    """, (sym, n))


def _annual(conn, sym: str, n: int = 5) -> list[dict]:
    return _fetchall(conn, """
        SELECT period_label, period_end, revenue, operating_profit, opm_pct,
               pat, eps, dividend_payout_pct
        FROM scores.annual_results
        WHERE symbol=%s ORDER BY period_end DESC NULLS LAST LIMIT %s
    """, (sym, n))


def _balance_sheet(conn, sym: str, n: int = 3) -> list[dict]:
    return _fetchall(conn, """
        SELECT period_label, period_end, equity_capital, reserves,
               borrowings, other_liabilities, total_liabilities,
               fixed_assets, cwip, investments, other_assets, total_assets,
               net_debt
        FROM scores.balance_sheet
        WHERE symbol=%s ORDER BY period_end DESC NULLS LAST LIMIT %s
    """, (sym, n))


def _cash_flow(conn, sym: str, n: int = 3) -> list[dict]:
    return _fetchall(conn, """
        SELECT period_label, period_end, operating_cf, investing_cf,
               financing_cf, net_cf
        FROM scores.cash_flow
        WHERE symbol=%s ORDER BY period_end DESC NULLS LAST LIMIT %s
    """, (sym, n))


def _insider(conn, sym: str, days: int = 90) -> list[dict]:
    try:
        return _fetchall(conn, """
            SELECT alert_date, alert_type, entity, value_cr, category,
                   insider_score
            FROM signals.insider_alerts
            WHERE symbol=%s AND alert_date >= CURRENT_DATE - %s::INT
            ORDER BY alert_date DESC LIMIT 10
        """, (sym, days))
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return []


def _corporate_events(conn, sym: str, days_past: int = 90,
                       days_future: int = 60) -> list[dict]:
    try:
        return _fetchall(conn, """
            SELECT event_date, event_type, purpose_raw, detail
            FROM signals.corporate_events
            WHERE symbol=%s
              AND event_date >= CURRENT_DATE - %s::INT
              AND event_date <= CURRENT_DATE + %s::INT
            ORDER BY event_date DESC LIMIT 15
        """, (sym, days_past, days_future))
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return []


def _fii_dii_recent(conn, days: int = 5) -> list[dict]:
    """Aggregate FII/DII flows context (market-wide, not stock-level)."""
    try:
        return _fetchall(conn, """
            SELECT trade_date, fii_net_cr, dii_net_cr
            FROM signals.fii_dii_flows
            WHERE trade_date >= CURRENT_DATE - %s::INT
            ORDER BY trade_date DESC LIMIT %s
        """, (days, days))
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return []


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------

def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct_change(curr: Any, prev: Any) -> float | None:
    c, p = _num(curr), _num(prev)
    if c is None or p is None or p == 0:
        return None
    return round((c - p) / abs(p) * 100, 2)


def _delta_pp(curr: Any, prev: Any) -> float | None:
    c, p = _num(curr), _num(prev)
    if c is None or p is None:
        return None
    return round(c - p, 2)


def _compute_growth(quarters: list[dict]) -> dict[str, float | None]:
    """YoY (vs q-4) and QoQ (vs q-1) growth on revenue, PAT, OPM, EPS."""
    if not quarters:
        return {}
    q0 = quarters[0]
    q1 = quarters[1] if len(quarters) > 1 else {}
    q4 = quarters[4] if len(quarters) > 4 else {}
    return {
        "yoy_revenue_pct": _pct_change(q0.get("revenue"), q4.get("revenue")),
        "qoq_revenue_pct": _pct_change(q0.get("revenue"), q1.get("revenue")),
        "yoy_pat_pct":     _pct_change(q0.get("pat"),     q4.get("pat")),
        "qoq_pat_pct":     _pct_change(q0.get("pat"),     q1.get("pat")),
        "yoy_eps_pct":     _pct_change(q0.get("eps"),     q4.get("eps")),
        "opm_delta_yoy_pp": _delta_pp(q0.get("opm_pct"), q4.get("opm_pct")),
        "opm_delta_qoq_pp": _delta_pp(q0.get("opm_pct"), q1.get("opm_pct")),
    }


# ---------------------------------------------------------------------------
# Credit rating extraction (best-effort, no new schema)
# ---------------------------------------------------------------------------

_RATING_AGENCIES = ("crisil", "icra", "care", "india ratings",
                    "ind-ra", "brickwork", "acuite", "smera", "fitch")


def _scan_credit_rating(announcements: Any) -> tuple[str, str] | None:
    """Look at screener announcements for any rating-related title.

    Returns ``(note, source_url)`` or ``None``.
    """
    if not isinstance(announcements, list):
        return None
    for row in announcements:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or row.get("subject") or "").strip()
        low = title.lower()
        has_keyword = ("rating" in low) or ("credit" in low)
        has_agency = any(agency in low for agency in _RATING_AGENCIES)
        if not (has_keyword or has_agency):
            continue
        url = str(row.get("url") or row.get("link") or "").strip()
        return title, url
    return None


# ---------------------------------------------------------------------------
# Evidence pack
# ---------------------------------------------------------------------------

def build_evidence_pack(
    conn,
    *,
    symbol: str,
    feed_row: dict | None = None,
    results_pack: dict | None = None,
    screener_data: dict | None = None,
) -> dict[str, Any]:
    """Assemble all inputs the LLM analyst needs for one stock.

    ``feed_row`` is one row from ``get_latest_results_feed``. ``results_pack``
    is the output of ``terminal.results_tools.get_latest_results`` (filing +
    parsed PDF + reconciled facts). Either may be ``None`` — the pack still
    builds from PG-only evidence.
    """
    sym = str(symbol or "").strip().upper()
    feed_row = feed_row or {}
    results_pack = results_pack or {}
    screener_data = screener_data or {}

    quarterly = _quarterly(conn, sym)
    annual = _annual(conn, sym)
    bs = _balance_sheet(conn, sym)
    cf = _cash_flow(conn, sym)
    insider = _insider(conn, sym)
    events = _corporate_events(conn, sym)
    fii_dii = _fii_dii_recent(conn)

    growth = _compute_growth(quarterly)
    ratios = (screener_data or {}).get("ratios") or {}
    shareholding = (screener_data or {}).get("shareholding") or {}
    about = (screener_data or {}).get("about") or (screener_data or {}).get("description") or ""
    announcements = (screener_data or {}).get("announcements")

    rating = _scan_credit_rating(announcements)

    return {
        "symbol": sym,
        "company_name": feed_row.get("company") or (screener_data or {}).get("name") or "",
        "industry": feed_row.get("industry") or (screener_data or {}).get("sector") or "",
        "period_label": feed_row.get("period") or "",
        "filing_date": feed_row.get("filing_date") or "",
        "filing_url": (results_pack.get("selected_filing") or {}).get("url") or feed_row.get("xbrl_url") or "",
        "audited": feed_row.get("audited") or "",
        "consolidated": feed_row.get("consolidated") or "",
        "about": about,
        "ratios": ratios,
        "shareholding": shareholding,
        "quarterly": quarterly,
        "annual": annual,
        "balance_sheet": bs,
        "cash_flow": cf,
        "growth": growth,
        "insider": insider,
        "corporate_events": events,
        "fii_dii_flows": fii_dii,
        "credit_rating": (
            {"note": rating[0], "source": rating[1]} if rating else None
        ),
        "parsed_filing_status": results_pack.get("status") or "",
        "parsed_filing_facts": results_pack.get("facts") or {},
        "results_warning": results_pack.get("warning") or {},
        "source_trail": results_pack.get("source_trail") or {},
    }


_PLACEHOLDER_RE = re.compile(r"\[[A-Za-z][^\]]{2,80}\]")


def has_structured_financials(pack: dict[str, Any]) -> bool:
    """Return True when at least one financial statement table has rows."""
    return any(
        bool(pack.get(key))
        for key in ("quarterly", "annual", "balance_sheet", "cash_flow")
    )


def analysis_has_placeholders(analysis: dict[str, Any]) -> bool:
    """Detect visible LLM template placeholders such as ``[revenue figure]``."""
    fields = (
        "business_summary",
        "pl_commentary",
        "bs_commentary",
        "cf_commentary",
        "ratios_note",
        "fii_dii_context",
        "insider_activity_note",
        "credit_rating_note",
    )
    values = [str(analysis.get(field)) for field in fields if analysis.get(field)]
    for field in ("key_strengths", "key_risks"):
        values.extend(str(value) for value in (analysis.get(field) or []))
    return any(_PLACEHOLDER_RE.search(value) for value in values)


def insufficient_data_analysis(pack: dict[str, Any], *, reason: str = "missing_structured_financials") -> dict[str, Any]:
    """Deterministic analysis for pages where evidence is too sparse."""
    company = pack.get("company_name") or pack.get("symbol") or "This company"
    period = pack.get("period_label") or "the reported period"
    filing_note = " The filing link is available below." if pack.get("filing_url") else ""
    message = (
        f"{company} filed results for {period}, but the local structured financial "
        f"tables do not contain enough rows to produce a numeric stock-level analysis."
        f"{filing_note}"
    )
    return {
        "business_summary": message,
        "pl_commentary": "Structured quarterly P&L rows are unavailable for this symbol in PostgreSQL, so revenue, margin, PAT and EPS trends are not shown.",
        "bs_commentary": "Structured balance-sheet rows are unavailable for this symbol in PostgreSQL.",
        "cf_commentary": "Structured cash-flow rows are unavailable for this symbol in PostgreSQL.",
        "ratios_note": "Analysis withheld until structured financial statement data is available.",
        "key_strengths": [],
        "key_risks": ["Insufficient structured financial statement data for this report run."],
        "verdict": "unknown",
        "score": None,
        "_evidence_warning": reason,
    }


def _fmt_metric(value: Any, suffix: str = "") -> str:
    num = _num(value)
    if num is None:
        return "not available"
    return f"{num:.2f}{suffix}"


def deterministic_financial_analysis(pack: dict[str, Any], *, reason: str = "llm_placeholder_output") -> dict[str, Any]:
    """Evidence-only analysis used when the LLM output is not publishable."""
    company = pack.get("company_name") or pack.get("symbol") or "This company"
    period = pack.get("period_label") or "the reported period"
    growth = pack.get("growth") or {}
    latest_q = (pack.get("quarterly") or [{}])[0] if pack.get("quarterly") else {}
    latest_bs = (pack.get("balance_sheet") or [{}])[0] if pack.get("balance_sheet") else {}
    latest_cf = (pack.get("cash_flow") or [{}])[0] if pack.get("cash_flow") else {}
    rev_yoy = _num(growth.get("yoy_revenue_pct"))
    pat_yoy = _num(growth.get("yoy_pat_pct"))
    if rev_yoy is not None and pat_yoy is not None:
        if rev_yoy > 10 and pat_yoy > 10:
            verdict = "beat"
            score = 7.0
        elif rev_yoy < -10 or pat_yoy < -10:
            verdict = "miss"
            score = 3.5
        else:
            verdict = "mixed"
            score = 5.5
    else:
        verdict = "unknown"
        score = None
    return {
        "business_summary": (
            f"{company} filed results for {period}. This page uses deterministic "
            "commentary from the structured financial tables because the LLM "
            "commentary for this run was not publishable."
        ),
        "pl_commentary": (
            f"Latest reported revenue is {_fmt_metric(latest_q.get('revenue'))} crore, "
            f"operating profit is {_fmt_metric(latest_q.get('operating_profit'))} crore, "
            f"PAT is {_fmt_metric(latest_q.get('pat'))} crore, and EPS is "
            f"{_fmt_metric(latest_q.get('eps'))}. Revenue YoY is "
            f"{_fmt_metric(growth.get('yoy_revenue_pct'), '%')} and PAT YoY is "
            f"{_fmt_metric(growth.get('yoy_pat_pct'), '%')}."
        ),
        "bs_commentary": (
            f"Latest balance-sheet rows show borrowings of "
            f"{_fmt_metric(latest_bs.get('borrowings'))} crore, net debt of "
            f"{_fmt_metric(latest_bs.get('net_debt'))} crore, and total assets of "
            f"{_fmt_metric(latest_bs.get('total_assets'))} crore."
        ),
        "cf_commentary": (
            f"Latest cash-flow rows show operating cash flow of "
            f"{_fmt_metric(latest_cf.get('operating_cf'))} crore, investing cash flow of "
            f"{_fmt_metric(latest_cf.get('investing_cf'))} crore, financing cash flow of "
            f"{_fmt_metric(latest_cf.get('financing_cf'))} crore, and net cash flow of "
            f"{_fmt_metric(latest_cf.get('net_cf'))} crore."
        ),
        "ratios_note": "Ratios are not interpreted in this deterministic fallback.",
        "key_strengths": ["Structured financial tables are available for this symbol."],
        "key_risks": ["Narrative is deterministic because the LLM output contained template placeholders."],
        "verdict": verdict,
        "score": score,
        "_evidence_warning": reason,
    }


# ---------------------------------------------------------------------------
# LLM analyst
# ---------------------------------------------------------------------------

ANALYSIS_SYSTEM_PROMPT = (
    "You are a sell-side equity analyst summarising a freshly-filed Indian "
    "quarterly result. You will be given structured P&L, Balance Sheet, "
    "Cash Flow, ratios, shareholding, insider activity and corporate events. "
    "Write factual, evidence-based commentary. NEVER invent numbers — if a "
    "field is missing in the evidence, say so. Be concise but specific. "
    "Use INR values in crores when the input is in crores. Output strict JSON "
    "matching the provided schema."
)


ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "business_summary", "pl_commentary", "bs_commentary", "cf_commentary",
        "key_strengths", "key_risks", "verdict", "score",
    ],
    "properties": {
        "business_summary": {"type": "string"},
        "pl_commentary": {"type": "string"},
        "bs_commentary": {"type": "string"},
        "cf_commentary": {"type": "string"},
        "ratios_note": {"type": "string"},
        "fii_dii_context": {"type": "string"},
        "insider_activity_note": {"type": "string"},
        "credit_rating_note": {"type": "string"},
        "key_strengths": {
            "type": "array", "items": {"type": "string"}, "maxItems": 6,
        },
        "key_risks": {
            "type": "array", "items": {"type": "string"}, "maxItems": 6,
        },
        "verdict": {
            "type": "string",
            "enum": ["beat", "inline", "miss", "mixed", "unknown"],
        },
        "score": {"type": "number", "minimum": 0, "maximum": 10},
    },
}


def _user_prompt(pack: dict) -> str:
    """Render the evidence pack as a compact, LLM-friendly text block."""
    sym = pack.get("symbol")
    period = pack.get("period_label")
    head = (
        f"Symbol: {sym}\n"
        f"Company: {pack.get('company_name')}  ·  Industry: {pack.get('industry')}\n"
        f"Period: {period}  ·  Filed: {pack.get('filing_date')}  "
        f"({pack.get('audited')}/{pack.get('consolidated')})\n"
        f"Filing URL: {pack.get('filing_url') or 'n/a'}\n"
    )
    about = (pack.get("about") or "").strip()
    if about:
        head += f"\nBusiness profile: {about[:600]}\n"

    growth = pack.get("growth") or {}
    if growth:
        head += "\nKey YoY/QoQ growth (computed from PG):\n"
        for k, v in growth.items():
            head += f"  {k}: {v}\n"

    def _table(name: str, rows: list[dict], cols: list[str]) -> str:
        if not rows:
            return f"\n{name}: (no rows)\n"
        out = [f"\n{name}:", "  " + " | ".join(cols)]
        for r in rows:
            out.append("  " + " | ".join(str(r.get(c, "")) for c in cols))
        return "\n".join(out) + "\n"

    body = ""
    body += _table("Quarterly P&L (latest first)", pack.get("quarterly") or [], [
        "period_label", "revenue", "operating_profit", "opm_pct", "pat", "eps",
    ])
    body += _table("Annual P&L", pack.get("annual") or [], [
        "period_label", "revenue", "operating_profit", "opm_pct", "pat", "eps",
        "dividend_payout_pct",
    ])
    body += _table("Balance Sheet", pack.get("balance_sheet") or [], [
        "period_label", "borrowings", "net_debt", "total_assets", "investments",
    ])
    body += _table("Cash Flow", pack.get("cash_flow") or [], [
        "period_label", "operating_cf", "investing_cf", "financing_cf", "net_cf",
    ])

    ratios = pack.get("ratios") or {}
    if ratios:
        body += "\nRatios (screener):\n"
        for k, v in list(ratios.items())[:25]:
            body += f"  {k}: {v}\n"

    sh = pack.get("shareholding") or {}
    if sh:
        body += "\nShareholding (latest column shown):\n"
        for k, v in list(sh.items())[:15]:
            if k.endswith("_trend") or k.startswith("_"):
                continue
            body += f"  {k}: {v}\n"

    insider = pack.get("insider") or []
    if insider:
        body += "\nRecent insider/promoter alerts (last 90d):\n"
        for r in insider[:5]:
            body += (
                f"  {r.get('alert_date')}  {r.get('alert_type')}  "
                f"{r.get('entity')}  ₹{r.get('value_cr')}cr  ({r.get('category')})\n"
            )

    events = pack.get("corporate_events") or []
    if events:
        body += "\nCorporate events (±90d):\n"
        for r in events[:5]:
            body += f"  {r.get('event_date')}  {r.get('event_type')}  {r.get('detail')}\n"

    fii = pack.get("fii_dii_flows") or []
    if fii:
        body += "\nMarket-wide FII/DII flows (last 5d, ₹cr):\n"
        for r in fii:
            body += (
                f"  {r.get('trade_date')}  FII={r.get('fii_net_cr')}  "
                f"DII={r.get('dii_net_cr')}\n"
            )

    rating = pack.get("credit_rating")
    if rating:
        body += f"\nCredit-rating mention found in announcements: {rating.get('note')}\n"

    parsed_facts = pack.get("parsed_filing_facts") or {}
    if parsed_facts:
        body += "\nFiling-parsed facts (deterministic):\n"
        for k, v in parsed_facts.items():
            body += f"  {k}: {v}\n"

    instructions = (
        "\nProduce JSON with: business_summary (2-3 sentences, what the "
        "company does and the headline result), pl_commentary (revenue / "
        "OPM / PAT YoY+QoQ with numbers), bs_commentary (debt, net debt, "
        "asset base trends), cf_commentary (OCF/ICF/FCF quality), "
        "ratios_note, fii_dii_context (only if shareholding shows a clear "
        "DII/FII move), insider_activity_note, credit_rating_note (only "
        "if credit-rating mention found above), key_strengths (3-5 short "
        "bullets), key_risks (3-5 short bullets), verdict in "
        "{beat, inline, miss, mixed, unknown}, score in 0..10. "
        "Cite numbers from the tables above; never invent."
    )
    return head + body + instructions


def analyze_with_llm(pack: dict, *, model: str | None = None) -> dict[str, Any]:
    """Run the analyst LLM call. Returns the validated JSON dict.

    Raises ``ResearchCouncilLLMUnavailable`` when no LLM provider is configured.
    """
    from terminal.research_council.llm_client import call_llm_json
    return call_llm_json(
        system=ANALYSIS_SYSTEM_PROMPT,
        user=_user_prompt(pack),
        schema=ANALYSIS_SCHEMA,
        model=model,
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _parse_period_end(label: str) -> _dt.date | None:
    if not label:
        return None
    s = str(label).strip()
    # Strip trailing time component like "30-Apr-2026 17:23:00"
    s = s.split()[0] if s and " " in s else s
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return _dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # "Mar 2026" / "Mar-2026"
    m = re.match(r"([A-Za-z]{3})[- ](\d{4})", str(label).strip())
    if m:
        months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                  "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
        mo = months.get(m.group(1).lower())
        if mo:
            yr = int(m.group(2))
            from calendar import monthrange
            return _dt.date(yr, mo, monthrange(yr, mo)[1])
    return None


def _resolve_period_end(pack: dict) -> _dt.date | None:
    quarterly = pack.get("quarterly") or []
    if quarterly and quarterly[0].get("period_end"):
        pe = quarterly[0]["period_end"]
        if isinstance(pe, _dt.date):
            return pe
        return _parse_period_end(str(pe))
    # fall back to feed to_date / period
    for key in ("to_date", "period_label", "filing_date"):
        pe = _parse_period_end(str(pack.get(key) or ""))
        if pe:
            return pe
    return None


def persist_analysis(
    conn,
    *,
    pack: dict,
    analysis: dict,
    report_path: str | None = None,
    llm_model: str | None = None,
) -> _dt.date | None:
    """Upsert an analysis row. Returns the resolved ``period_end`` or None."""
    period_end = _resolve_period_end(pack)
    if period_end is None:
        return None

    growth = pack.get("growth") or {}
    sym = pack.get("symbol")
    rating_block = pack.get("credit_rating") or {}
    credit_note = analysis.get("credit_rating_note") or rating_block.get("note") or None
    credit_src = rating_block.get("source") or None

    cols = [
        "symbol", "period_end", "period_label", "company_name", "industry",
        "filing_date", "filing_url", "audited", "consolidated",
        "business_summary",
        "growth_yoy_revenue_pct", "growth_qoq_revenue_pct",
        "growth_yoy_pat_pct",     "growth_qoq_pat_pct",
        "opm_delta_pp", "eps_yoy_pct",
        "pl_commentary", "bs_commentary", "cf_commentary",
        "ratios_snapshot",
        "credit_rating_note", "credit_rating_source",
        "fii_dii_context", "insider_activity_note",
        "key_strengths", "key_risks",
        "verdict", "score", "report_path",
        "llm_model", "source_trail", "analysis_json",
    ]

    filing_date = _parse_period_end(str(pack.get("filing_date") or ""))

    values = (
        sym, period_end, pack.get("period_label"), pack.get("company_name"),
        pack.get("industry"), filing_date, pack.get("filing_url"),
        pack.get("audited"), pack.get("consolidated"),
        analysis.get("business_summary"),
        growth.get("yoy_revenue_pct"), growth.get("qoq_revenue_pct"),
        growth.get("yoy_pat_pct"),     growth.get("qoq_pat_pct"),
        growth.get("opm_delta_yoy_pp"), growth.get("yoy_eps_pct"),
        analysis.get("pl_commentary"), analysis.get("bs_commentary"),
        analysis.get("cf_commentary"),
        json.dumps(pack.get("ratios") or {}),
        credit_note, credit_src,
        analysis.get("fii_dii_context"),
        analysis.get("insider_activity_note"),
        analysis.get("key_strengths") or [],
        analysis.get("key_risks") or [],
        analysis.get("verdict") or "unknown",
        _num(analysis.get("score")),
        report_path,
        llm_model,
        json.dumps(pack.get("source_trail") or {}),
        json.dumps(analysis),
    )

    placeholders = ", ".join(["%s"] * len(cols))
    update_set = ", ".join(
        f"{c}=EXCLUDED.{c}"
        for c in cols
        if c not in ("symbol", "period_end")
    )
    sql = (
        f"INSERT INTO scores.results_analysis ({', '.join(cols)}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT (symbol, period_end) DO UPDATE SET "
        f"{update_set}, updated_at = now()"
    )
    with conn.cursor() as cur:
        cur.execute(sql, values)
    return period_end


# ---------------------------------------------------------------------------
# HTML rendering (self-contained, no Jinja dependency)
# ---------------------------------------------------------------------------

_VERDICT_COLOR = {
    "beat": "#16a34a",
    "miss": "#dc2626",
    "mixed": "#d97706",
    "inline": "#2563eb",
    "unknown": "#6b7280",
}


def _h(text: Any) -> str:
    return _html.escape("" if text is None else str(text))


def _bullets(items: list | None) -> str:
    if not items:
        return "<em>(none)</em>"
    return "<ul>" + "".join(f"<li>{_h(i)}</li>" for i in items) + "</ul>"


def _table(title: str, rows: list[dict], cols: list[tuple[str, str]]) -> str:
    if not rows:
        return f"<h3>{_h(title)}</h3><p><em>No data.</em></p>"
    head = "".join(f"<th>{_h(label)}</th>" for _, label in cols)
    body = []
    for r in rows:
        cells = "".join(f"<td>{_h(r.get(k))}</td>" for k, _ in cols)
        body.append(f"<tr>{cells}</tr>")
    return (
        f"<h3>{_h(title)}</h3>"
        f"<div class='tbl-wrap'><table><thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table></div>"
    )


def _kpi(label: str, value: Any, suffix: str = "") -> str:
    val = "—" if value is None else f"{value}{suffix}"
    return f"<div class='kpi'><div class='kpi-l'>{_h(label)}</div><div class='kpi-v'>{_h(val)}</div></div>"


_CSS = """
body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
       max-width: 1100px; margin: 28px auto; padding: 0 20px;
       color: #111; line-height: 1.5; }
h1 { margin-bottom: 4px; }
h1 .verdict { font-size: 0.55em; padding: 4px 10px; border-radius: 999px;
              color: #fff; vertical-align: middle; margin-left: 10px; }
.subtle { color: #555; font-size: 0.92em; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 10px; margin: 18px 0; }
.kpi { background: #f7f8fa; border: 1px solid #e3e6eb; border-radius: 8px;
       padding: 10px 12px; }
.kpi-l { color: #555; font-size: 0.78em; text-transform: uppercase;
         letter-spacing: 0.5px; }
.kpi-v { font-size: 1.25em; font-weight: 600; margin-top: 4px; }
.tbl-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 0.92em; margin: 6px 0 18px; }
th, td { border: 1px solid #e3e6eb; padding: 6px 8px; text-align: right; }
th { background: #f1f3f6; text-align: left; }
td:first-child, th:first-child { text-align: left; }
.section { margin: 24px 0; }
.section h2 { border-bottom: 2px solid #e3e6eb; padding-bottom: 4px; }
.commentary { background: #fcfcfd; border-left: 3px solid #2563eb;
              padding: 10px 14px; border-radius: 4px; }
.flex2 { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
@media (max-width: 760px) { .flex2 { grid-template-columns: 1fr; } }
.footer { color: #888; font-size: 0.82em; margin-top: 30px;
          border-top: 1px solid #e3e6eb; padding-top: 10px; }
a { color: #1d4ed8; }
.score-pill { display: inline-block; padding: 2px 8px; border-radius: 6px;
              background: #eef2ff; color: #1e3a8a; font-weight: 600; }
"""


def render_stock_html(pack: dict, analysis: dict) -> str:
    """Render a single-stock analysis HTML page."""
    sym = pack.get("symbol", "")
    company = pack.get("company_name") or sym
    period = pack.get("period_label") or ""
    filing_date = pack.get("filing_date") or ""
    verdict = (analysis.get("verdict") or "unknown").lower()
    color = _VERDICT_COLOR.get(verdict, "#6b7280")
    score = analysis.get("score")
    growth = pack.get("growth") or {}
    rating = pack.get("credit_rating") or {}

    head = (
        f"<h1>{_h(company)} <small style='font-weight:400;color:#555'>({_h(sym)})</small>"
        f"<span class='verdict' style='background:{color}'>{_h(verdict.upper())}</span>"
        "</h1>"
        f"<div class='subtle'>Period: <b>{_h(period)}</b> · Filed: {_h(filing_date)} · "
        f"{_h(pack.get('audited'))}/{_h(pack.get('consolidated'))} · "
        f"<span class='score-pill'>Score {('—' if score is None else score)}/10</span></div>"
    )

    kpis = "<div class='kpis'>" + "".join([
        _kpi("Revenue YoY",  growth.get("yoy_revenue_pct"), "%"),
        _kpi("Revenue QoQ",  growth.get("qoq_revenue_pct"), "%"),
        _kpi("PAT YoY",      growth.get("yoy_pat_pct"), "%"),
        _kpi("PAT QoQ",      growth.get("qoq_pat_pct"), "%"),
        _kpi("EPS YoY",      growth.get("yoy_eps_pct"), "%"),
        _kpi("OPM Δ YoY",    growth.get("opm_delta_yoy_pp"), " pp"),
    ]) + "</div>"

    evidence_warning = ""
    if analysis.get("_evidence_warning"):
        warning_reason = str(analysis.get("_evidence_warning") or "")
        if "placeholder" in warning_reason:
            warning_text = (
                "The original LLM commentary contained template placeholders, "
                "so this page uses deterministic commentary from the structured "
                "financial tables."
            )
        else:
            warning_text = (
                "Structured financial statement data was insufficient for a full "
                "numeric analysis. Treat this page as a filing placeholder until "
                "the financial tables are backfilled."
            )
        evidence_warning = (
            "<div class='section commentary' style='border-left-color:#d97706'>"
            f"<b>Evidence warning:</b> {_h(warning_text)}</div>"
        )

    biz = (
        f"<div class='section'><h2>Business overview</h2>"
        f"<p>{_h(analysis.get('business_summary'))}</p></div>"
    )
    about = (pack.get("about") or "").strip()
    if about:
        biz += f"<div class='subtle' style='margin-top:-10px'>{_h(about[:1200])}</div>"

    commentary = (
        "<div class='section'><h2>Analyst commentary</h2>"
        f"<h3>P&amp;L</h3><div class='commentary'>{_h(analysis.get('pl_commentary'))}</div>"
        f"<h3>Balance sheet</h3><div class='commentary'>{_h(analysis.get('bs_commentary'))}</div>"
        f"<h3>Cash flow</h3><div class='commentary'>{_h(analysis.get('cf_commentary'))}</div>"
    )
    if analysis.get("ratios_note"):
        commentary += f"<h3>Ratios</h3><div class='commentary'>{_h(analysis.get('ratios_note'))}</div>"
    if analysis.get("fii_dii_context"):
        commentary += f"<h3>FII / DII context</h3><div class='commentary'>{_h(analysis.get('fii_dii_context'))}</div>"
    if analysis.get("insider_activity_note"):
        commentary += f"<h3>Insider activity</h3><div class='commentary'>{_h(analysis.get('insider_activity_note'))}</div>"
    if analysis.get("credit_rating_note") or rating.get("note"):
        note = analysis.get("credit_rating_note") or rating.get("note")
        src = rating.get("source")
        link = f" <a href='{_h(src)}'>source</a>" if src else ""
        commentary += f"<h3>Credit rating</h3><div class='commentary'>{_h(note)}{link}</div>"
    commentary += "</div>"

    sr = (
        "<div class='section flex2'>"
        f"<div><h2>Strengths</h2>{_bullets(analysis.get('key_strengths'))}</div>"
        f"<div><h2>Risks</h2>{_bullets(analysis.get('key_risks'))}</div>"
        "</div>"
    )

    pl_table = _table("Quarterly P&L (last 8)", pack.get("quarterly") or [], [
        ("period_label", "Quarter"), ("revenue", "Revenue"),
        ("operating_profit", "Op Profit"), ("opm_pct", "OPM %"),
        ("pat", "PAT"), ("eps", "EPS"),
    ])
    annual_table = _table("Annual P&L", pack.get("annual") or [], [
        ("period_label", "Year"), ("revenue", "Revenue"),
        ("operating_profit", "Op Profit"), ("opm_pct", "OPM %"),
        ("pat", "PAT"), ("eps", "EPS"),
    ])
    bs_table = _table("Balance Sheet", pack.get("balance_sheet") or [], [
        ("period_label", "Year"), ("borrowings", "Borrow"),
        ("net_debt", "Net Debt"), ("total_assets", "Total Assets"),
        ("investments", "Investments"),
    ])
    cf_table = _table("Cash Flow", pack.get("cash_flow") or [], [
        ("period_label", "Year"), ("operating_cf", "OCF"),
        ("investing_cf", "ICF"), ("financing_cf", "FCF"),
        ("net_cf", "Net CF"),
    ])

    filing = ""
    if pack.get("filing_url"):
        filing = (
            f"<div class='section'><h2>Filing</h2>"
            f"<p><a href='{_h(pack.get('filing_url'))}' target='_blank'>"
            "Open filing</a></p></div>"
        )

    footer = (
        "<div class='footer'>Generated by Unified-NSE-Analysis · "
        f"data sources: scores.* (PG), screener.in, NSE filings · "
        f"LLM: {_h(analysis.get('_llm_model') or os.environ.get('OPENAI_MODEL') or 'configured-default')}"
        "</div>"
    )

    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>Results Analysis — {_h(sym)}</title>"
        f"<style>{_CSS}</style></head><body>"
        + head + kpis + evidence_warning + biz + commentary + sr
        + "<div class='section'><h2>Financials</h2>"
        + pl_table + annual_table
        + "<div class='flex2'>" + bs_table + cf_table + "</div>"
        + "</div>" + filing + footer
        + "</body></html>"
    )


def render_index_html(date_label: str, items: list[dict]) -> str:
    """Render an index of all analyses for a given run date."""
    rows = []
    for it in items:
        verdict = (it.get("verdict") or "unknown").lower()
        color = _VERDICT_COLOR.get(verdict, "#6b7280")
        link = it.get("report_path") or "#"
        rows.append(
            "<tr>"
            f"<td><a href='{_h(link)}'>{_h(it.get('symbol'))}</a></td>"
            f"<td>{_h(it.get('company_name'))}</td>"
            f"<td>{_h(it.get('period_label'))}</td>"
            f"<td style='color:{color};font-weight:600'>{_h(verdict.upper())}</td>"
            f"<td>{_h(it.get('score'))}</td>"
            f"<td>{_h(it.get('yoy_revenue_pct'))}</td>"
            f"<td>{_h(it.get('yoy_pat_pct'))}</td>"
            "</tr>"
        )
    table = (
        "<table><thead><tr>"
        "<th>Symbol</th><th>Company</th><th>Period</th><th>Verdict</th>"
        "<th>Score</th><th>Rev YoY %</th><th>PAT YoY %</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>Daily Results Analysis — {_h(date_label)}</title>"
        f"<style>{_CSS}</style></head><body>"
        f"<h1>Daily Results Analysis</h1>"
        f"<div class='subtle'>{_h(date_label)} · {len(items)} stock(s)</div>"
        + table +
        "<div class='footer'>Click a symbol for the full analysis.</div>"
        "</body></html>"
    )


# ---------------------------------------------------------------------------
# DSN convenience
# ---------------------------------------------------------------------------

def connect(dsn: str | None = None):
    return psycopg2.connect(dsn or DEFAULT_DSN)
