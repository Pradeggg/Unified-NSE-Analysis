"""Financial analyst style research reports grounded in broker evidence."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .report import DISCLAIMER, markdown_table_cell, render_broker_research_html


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())


def _normalize_markdown(text: Any) -> str:
    lines = [line.rstrip() for line in str(text or "").replace("\r\n", "\n").split("\n")]
    compact: list[str] = []
    blank_seen = False
    for line in lines:
        if not line.strip():
            if not blank_seen:
                compact.append("")
            blank_seen = True
            continue
        compact.append(line)
        blank_seen = False
    return "\n".join(compact).strip()


def _money(value: Any) -> str:
    if value is None or value == "":
        return "not extracted"
    try:
        numeric = float(str(value).replace(",", ""))
    except Exception:
        return str(value)
    if numeric.is_integer():
        return f"₹{int(numeric):,}"
    return f"₹{numeric:,.2f}"


def _first_match(pages: list[dict[str, Any]], pattern: str) -> str:
    rx = re.compile(pattern, re.I | re.S)
    for page in pages:
        text = _clean(page.get("text"))
        match = rx.search(text)
        if match:
            return _clean(match.group(0))
    return ""


def _page_ref(page: dict[str, Any]) -> str:
    broker = page.get("broker_code") or ""
    title = page.get("report_title") or ""
    number = page.get("page_number") or ""
    return f"{broker} / {title} / Page {number}".strip(" /")


def _unique_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for fact in facts:
        fact_type = str(fact.get("fact_type") or "")
        fact_value = str(fact.get("fact_value") or "").strip()
        lowered = fact_value.lower()
        if fact_type == "risk" and (
            "read all the related documents" in lowered
            or "registration granted by sebi" in lowered
            or "no way guarantee performance" in lowered
        ):
            continue
        page_key = "" if fact_type in {"rating", "target_price"} else str(fact.get("page_number") or "")
        key = (
            str(fact.get("broker_report_id") or ""),
            fact_type,
            lowered,
            page_key,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(fact)
    return out


def _fact_values(facts: list[dict[str, Any]], fact_type: str) -> list[str]:
    values = []
    for fact in _unique_facts(facts):
        if fact.get("fact_type") == fact_type and str(fact.get("fact_value") or "").strip():
            values.append(str(fact["fact_value"]).strip())
    return values


def build_llm_financial_prompt(
    *,
    symbol: str,
    consensus: dict[str, Any],
    facts: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    agent_adda_context: dict[str, Any] | None = None,
    max_chars_per_page: int = 2200,
) -> str:
    page_blocks = []
    for page in pages[:8]:
        page_blocks.append(
            "\n".join(
                [
                    f"Broker: {page.get('broker_code') or ''}",
                    f"Report: {page.get('report_title') or ''}",
                    f"Page {page.get('page_number') or ''}: {_clean(page.get('text'))[:max_chars_per_page]}",
                ]
            )
        )
    return "\n\n".join(
        [
            "You are a financial analyst producing a research memo for Indian equities.",
            f"Symbol: {symbol.strip().upper()}",
            f"Consensus JSON: {consensus}",
            f"Extracted facts JSON: {facts[:30]}",
            f"Agent Adda PG context JSON: {agent_adda_context or {}}",
            "Task: build a comprehensive financial point of view grounded only in the evidence below.",
            "Cover thesis, valuation, forecasts, risk/reward, what to verify independently, and missing evidence.",
            "Explicitly incorporate Agent Adda PG data when available: price, trend, RSI, technical score, stage, screener conviction, fundamentals, quarterly/annual results, and sector rotation.",
            "Use clear analyst language similar to: quality business, weak current setup, valuation-sensitive, when the PG evidence supports that view.",
            "Separate broker view from Agent Adda's own PG-grounded view.",
            "Do not invent facts, prices, forecasts, ratings, or dates. Cite page numbers inline as [broker report p.X].",
            "Keep the tone analytical. This is research context, not investment advice.",
            "Evidence:",
            *page_blocks,
        ]
    )


def build_financial_analyst_markdown(
    *,
    symbol: str,
    consensus: dict[str, Any],
    facts: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    llm_view: str = "",
    agent_adda_context: dict[str, Any] | None = None,
) -> str:
    clean_symbol = symbol.strip().upper()
    target = consensus.get("target_price") or {}
    ratings = consensus.get("ratings") or {}
    unique_facts = _unique_facts(facts)
    target_average = target.get("average") or target.get("max") or target.get("min")
    cmp_line = _first_match(pages, r"CMP\s*:\s*₹?\s*[0-9,.]+")
    upside_line = _first_match(pages, r"Target\s*:\s*₹?\s*[0-9,.]+\s*\([^)]+\)")
    backlog_line = _first_match(pages, r"order backlog[^.]{0,180}")
    forecast_line = _first_match(pages, r"(revenue\s*&\s*PAT\s*CAGR[^.]{0,140}|Management guides[^.]{0,160})")
    valuation_line = _first_match(pages, r"based on\s*[0-9.]+x\s*FY[0-9]{2}E?\s*EPS")
    risk_line = _first_match(pages, r"Key risks[^A-Z]{0,20}.*?(?:Research Analyst|$)")
    thesis_line = _first_match(pages, r"Investment Rationale:.*?(?:Rating and Target Price|$)")
    if len(thesis_line) > 900:
        thesis_line = thesis_line[:900].rstrip() + "..."
    if len(risk_line) > 500:
        risk_line = risk_line[:500].rstrip() + "..."
    pg_context = agent_adda_context or {}
    pg_section = build_agent_adda_pg_view(symbol=clean_symbol, context=pg_context, consensus=consensus)

    analyst_view = _normalize_markdown(llm_view) or (
        f"The extracted broker evidence is constructive for {clean_symbol}: "
        f"ratings are {ratings or 'not extracted'} and the extracted target-price average is {_money(target_average)}. "
        "The view depends on order execution, defence order inflows, margin delivery, and working-capital control."
    )
    lines = [
        f"# Financial Analyst Research: {clean_symbol}",
        "",
        f"━━━ {DISCLAIMER} ━━━",
        "",
        "## Financial Analyst Point Of View",
        "",
        analyst_view,
        "",
        "## Broker Evidence Snapshot",
        "",
        f"- Broker reports covered: {consensus.get('broker_count', 0)}",
        f"- Brokers: {', '.join(consensus.get('brokers') or []) or 'No broker evidence available'}",
        f"- Ratings extracted: {ratings or {}}",
        f"- Target-price average: {_money(target_average)}",
        f"- CMP evidence: {cmp_line or 'not extracted'}",
        f"- Upside evidence: {upside_line or 'not extracted'}",
        "",
        "## Agent Adda PG-Grounded View",
        "",
        pg_section,
        "",
        "## Thesis And Growth Drivers",
        "",
        f"- {thesis_line or 'No thesis paragraph extracted from parsed pages.'}",
        f"- Order-book evidence: {backlog_line or 'not extracted'}",
        f"- Forecast evidence: {forecast_line or 'not extracted'}",
        "",
        "## Valuation And Return Setup",
        "",
        f"- Target price: {_money(target_average)}",
        f"- Valuation method: {valuation_line or 'not extracted'}",
        f"- Target spread across extracted broker facts: {target.get('spread', 0.0)}",
        "",
        "## Risks And Analyst Checks",
        "",
        f"- Broker risk evidence: {risk_line or '; '.join(_fact_values(unique_facts, 'risk')) or 'not extracted'}",
        "- Independent checks required: latest order inflow conversion, receivable/working-capital trend, margin bridge, and valuation against current market price.",
        "- Claims not backed by parsed broker pages or stored facts are intentionally omitted.",
        "",
        "## Evidence Register",
        "",
        "| Broker | Report | Page | Evidence | URL |",
        "|---|---|---:|---|---|",
    ]
    evidence_rows = 0
    for page in pages:
        text = _clean(page.get("text"))
        if not text:
            continue
        lines.append(
            "| {broker} | {title} | {page} | {evidence} | {url} |".format(
                broker=page.get("broker_code") or "",
                title=markdown_table_cell(page.get("report_title") or ""),
                page=f"Page {page.get('page_number') or ''}".strip(),
                evidence=markdown_table_cell(text[:260]),
                url=page.get("pdf_url") or "",
            )
        )
        evidence_rows += 1
        if evidence_rows >= 6:
            break
    if evidence_rows == 0:
        lines.append("| - | - | - | No parsed page evidence available | - |")
    lines.extend(
        [
            "",
            "## Fact Appendix",
            "",
            "| Broker | Report | Fact | Page | URL |",
            "|---|---|---|---:|---|",
        ]
    )
    if not unique_facts:
        lines.append("| - | - | - | - | - |")
    for fact in unique_facts:
        lines.append(
            "| {broker} | {title} | {fact_type}: {fact_value} | {page} | {url} |".format(
                broker=fact.get("broker_code") or "",
                title=markdown_table_cell(fact.get("report_title") or ""),
                fact_type=fact.get("fact_type") or "",
                fact_value=markdown_table_cell(fact.get("fact_value") or ""),
                page=fact.get("page_number") or "",
                url=fact.get("pdf_url") or "",
            )
        )
    return "\n".join(lines) + "\n"


def _fmt_pct(value: Any) -> str:
    if value is None or value == "":
        return "not available"
    try:
        return f"{float(value):.2f}%"
    except Exception:
        return str(value)


def _fmt_num(value: Any) -> str:
    if value is None or value == "":
        return "not available"
    try:
        numeric = float(value)
    except Exception:
        return str(value)
    if numeric.is_integer():
        return f"{int(numeric):,}"
    return f"{numeric:,.2f}"


def _latest_annual_eps(context: dict[str, Any]) -> float | None:
    for row in context.get("annual_results") or []:
        label = str(row.get("period_label") or "").upper()
        if label == "TTM":
            continue
        try:
            return float(row.get("eps"))
        except Exception:
            continue
    return None


def build_agent_adda_pg_view(*, symbol: str, context: dict[str, Any], consensus: dict[str, Any]) -> str:
    if not context or not context.get("available"):
        return "Agent Adda PG market/fundamental context was not available for this report run."
    instrument = context.get("instrument") or {}
    latest_eod = context.get("latest_eod") or {}
    daily = context.get("daily_score") or {}
    fscore = context.get("fundamental_score") or {}
    screener = context.get("screener_summary") or {}
    sector = context.get("sector_context") or {}
    annual = context.get("annual_results") or []
    quarterly = context.get("quarterly_results") or []
    target = consensus.get("target_price") or {}
    current_price = daily.get("current_price") or latest_eod.get("close")
    latest_eps = _latest_annual_eps(context)
    pe_latest = None
    if current_price and latest_eps:
        try:
            pe_latest = float(current_price) / float(latest_eps)
        except Exception:
            pe_latest = None
    target_average = target.get("average") or target.get("max") or target.get("min")
    target_forward_pe = None
    # The broker report currently stores FY28E EPS as parsed page text, not as a structured PG fact.
    # Use only structured PG EPS for the deterministic valuation check here.
    if target_average and latest_eps:
        try:
            target_forward_pe = float(target_average) / float(latest_eps)
        except Exception:
            target_forward_pe = None
    trading_signal = str(daily.get("trading_signal") or screener.get("trading_signal") or "").upper()
    trend_signal = str(daily.get("trend_signal") or screener.get("stage") or "").upper()
    technical_score = daily.get("technical_score") or screener.get("technical_score")
    enhanced_fund_score = fscore.get("enhanced_fund_score") or daily.get("enhanced_fund_score") or screener.get("enhanced_fund_score")
    if trading_signal == "SELL" or "BEAR" in trend_signal or (technical_score is not None and float(technical_score) < 35):
        setup = "weak current setup"
    else:
        setup = "constructive current setup"
    quality = "quality business" if enhanced_fund_score is not None and float(enhanced_fund_score) >= 75 else "mixed-quality business"
    valuation = "valuation-sensitive" if pe_latest is not None and pe_latest >= 35 else "valuation needs checking"
    latest_annual = annual[0] if annual else {}
    latest_quarter = quarterly[0] if quarterly else {}
    passed_screens = screener.get("passed_screens") or []
    lines = [
        f"My PG-grounded stance: **{quality}, {setup}, {valuation}.**",
        "",
        f"- Latest PG price/date: {_money(current_price)} on {latest_eod.get('trade_date') or daily.get('score_date') or 'not available'}.",
        f"- Technical setup: signal `{trading_signal or 'not available'}`, trend/stage `{trend_signal or 'not available'}`, technical score `{_fmt_num(technical_score)}`, RSI `{_fmt_num(daily.get('rsi'))}`, 1M change `{_fmt_pct(daily.get('change_1m_pct'))}`.",
        f"- Fundamental quality: enhanced fund score `{_fmt_num(enhanced_fund_score)}`, earnings quality `{_fmt_num(fscore.get('earnings_quality'))}`, sales growth `{_fmt_num(fscore.get('sales_growth'))}`, financial strength `{_fmt_num(fscore.get('financial_strength'))}`.",
        f"- Latest annual result: {latest_annual.get('period_label') or 'not available'} revenue `{_money(latest_annual.get('revenue'))} Cr`, PAT `{_money(latest_annual.get('pat'))} Cr`, EPS `{_money(latest_annual.get('eps'))}`.",
        f"- Latest quarter: {latest_quarter.get('period_label') or 'not available'} revenue `{_money(latest_quarter.get('revenue'))} Cr`, PAT `{_money(latest_quarter.get('pat'))} Cr`, EPS `{_money(latest_quarter.get('eps'))}`.",
        f"- Valuation check: current price / latest annual EPS is `{_fmt_num(pe_latest)}x`; broker target / latest annual EPS is `{_fmt_num(target_forward_pe)}x`.",
        f"- Screener context: conviction `{screener.get('conviction_tier') or 'not available'}`, screens passed `{screener.get('screens_passed_total') or 0}`, passed screens `{passed_screens}`.",
        f"- Sector context: `{sector.get('sector') or instrument.get('sector') or 'not available'}` had {sector.get('buy_signals') if sector else 'not available'} BUY signals and {sector.get('stage2_count') if sector else 'not available'} Stage 2 names on {sector.get('score_date') if sector else 'not available'}.",
        "",
        "Interpretation: the business/fundamental data supports BEL as a strong-quality watchlist name, but the PG technical, screener, and sector-rotation data do not support chasing it at this snapshot.",
    ]
    return "\n".join(lines)


def write_financial_analyst_report(
    *,
    symbol: str,
    markdown: str,
    output_dir: Path | str = Path("reports/financial_research"),
    latest_dir: Path | str = Path("reports/latest"),
) -> dict[str, str]:
    clean_symbol = symbol.strip().upper()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(output_dir)
    latest = Path(latest_dir)
    out.mkdir(parents=True, exist_ok=True)
    latest.mkdir(parents=True, exist_ok=True)
    markdown_path = out / f"{clean_symbol.lower()}_{stamp}.md"
    html_path = out / f"{clean_symbol.lower()}_{stamp}.html"
    latest_markdown_path = latest / f"financial_research_{clean_symbol.lower()}.md"
    latest_html_path = latest / f"financial_research_{clean_symbol.lower()}.html"
    html_text = render_broker_research_html(markdown)
    markdown_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(html_text, encoding="utf-8")
    latest_markdown_path.write_text(markdown, encoding="utf-8")
    latest_html_path.write_text(html_text, encoding="utf-8")
    return {
        "markdown_path": str(markdown_path),
        "html_path": str(html_path),
        "latest_markdown_path": str(latest_markdown_path),
        "latest_html_path": str(latest_html_path),
    }
