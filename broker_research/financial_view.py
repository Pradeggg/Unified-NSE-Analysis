"""Financial analyst style research reports grounded in broker evidence."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .report import DISCLAIMER, render_broker_research_html


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())


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
            "Task: build a comprehensive financial point of view grounded only in the evidence below.",
            "Cover thesis, valuation, forecasts, risk/reward, what to verify independently, and missing evidence.",
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

    analyst_view = _clean(llm_view) or (
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
                title=page.get("report_title") or "",
                page=f"Page {page.get('page_number') or ''}".strip(),
                evidence=text[:260],
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
                title=fact.get("report_title") or "",
                fact_type=fact.get("fact_type") or "",
                fact_value=fact.get("fact_value") or "",
                page=fact.get("page_number") or "",
                url=fact.get("pdf_url") or "",
            )
        )
    return "\n".join(lines) + "\n"


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
