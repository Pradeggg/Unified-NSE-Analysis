#!/usr/bin/env python3
"""Validate research inputs and render deterministic fundamental-analysis metrics."""

from __future__ import annotations

import argparse
import html
import json
import math
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def pct_change(new: Any, old: Any) -> float | None:
    new_n, old_n = number(new), number(old)
    if new_n is None or old_n in (None, 0):
        return None
    return (new_n / old_n - 1) * 100


def safe_ratio(numerator: Any, denominator: Any, scale: float = 1.0) -> float | None:
    num, den = number(numerator), number(denominator)
    if num is None or den in (None, 0):
        return None
    return num / den * scale


def validate(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    company = data.get("company")
    if not isinstance(company, dict):
        return ["company must be an object"]
    for field in ("name", "symbol", "as_of_date", "currency", "unit"):
        if not company.get(field):
            errors.append(f"company.{field} is required")
    try:
        date.fromisoformat(str(company.get("as_of_date")))
    except ValueError:
        errors.append("company.as_of_date must use YYYY-MM-DD")
    if number(company.get("price")) is None or number(company.get("price")) <= 0:
        errors.append("company.price must be a positive number")

    annuals = data.get("annuals")
    if not isinstance(annuals, list) or len(annuals) < 3:
        errors.append("annuals must contain at least three periods")
    else:
        for index, row in enumerate(annuals):
            if not isinstance(row, dict) or not row.get("period"):
                errors.append(f"annuals[{index}].period is required")
            for field in ("revenue", "operating_profit", "pat"):
                if number(row.get(field)) is None:
                    errors.append(f"annuals[{index}].{field} must be numeric")

    scenarios = data.get("valuation_scenarios")
    if not isinstance(scenarios, list) or len(scenarios) < 3:
        errors.append("valuation_scenarios must contain at least three scenarios")
    else:
        for index, row in enumerate(scenarios):
            if not row.get("name") or number(row.get("forward_eps")) is None or number(row.get("pe")) is None:
                errors.append(f"valuation_scenarios[{index}] requires name, forward_eps, and pe")

    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("sources must contain at least one direct source")
    else:
        if not any(source.get("tier") == 1 for source in sources if isinstance(source, dict)):
            errors.append("sources must include at least one tier-1 primary source")
        if not any(_supports_price(source) for source in sources if isinstance(source, dict)):
            errors.append("sources must include an as-of price source (supports includes 'price')")
        for index, source in enumerate(sources):
            parsed = urlparse(str(source.get("url", ""))) if isinstance(source, dict) else None
            if parsed is None or parsed.scheme not in {"http", "https"} or not parsed.netloc:
                errors.append(f"sources[{index}].url must be a direct HTTP(S) URL")

    qualitative = data.get("qualitative")
    if not isinstance(qualitative, dict):
        errors.append("qualitative must be an object")
    else:
        verdict = qualitative.get("verdict")
        if not isinstance(verdict, dict):
            errors.append("qualitative.verdict must be an object")
        else:
            for field in (
                "business_quality",
                "financial_quality",
                "growth_durability",
                "valuation_comfort",
                "stance",
            ):
                if not str(verdict.get(field) or "").strip():
                    errors.append(f"qualitative.verdict.{field} is required")

    institutional = data.get("institutional")
    if institutional is not None and not isinstance(institutional, dict):
        errors.append("institutional must be an object when provided")
    elif isinstance(institutional, dict):
        for field in ("peer_context", "segment_analysis", "management_commentary", "shareholding", "red_team_questions"):
            value = institutional.get(field)
            if value is not None and not isinstance(value, list):
                errors.append(f"institutional.{field} must be a list when provided")
    return errors


def _supports_price(source: dict[str, Any]) -> bool:
    """True when a source record is marked as the as-of price citation."""
    supports = source.get("supports")
    if not isinstance(supports, list):
        return False
    return any(str(item).strip().lower() in {"price", "as_of_price", "company.price"} for item in supports)


def enrich(data: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(data))
    annuals = result["annuals"]
    for row in annuals:
        row["operating_margin_pct"] = safe_ratio(row.get("operating_profit"), row.get("revenue"), 100)
        row["pat_margin_pct"] = safe_ratio(row.get("pat"), row.get("revenue"), 100)
        cfo, capex = number(row.get("cfo")), number(row.get("capex"))
        row["fcf"] = cfo - capex if cfo is not None and capex is not None else None
        row["fcf_conversion_pct"] = safe_ratio(row.get("fcf"), row.get("pat"), 100)
        borrowings, equity = number(row.get("borrowings")), number(row.get("equity"))
        row["debt_to_equity"] = safe_ratio(borrowings, equity)
        cash = number(row.get("cash"))
        row["net_debt"] = borrowings - cash if borrowings is not None and cash is not None else None

    first, last = annuals[0], annuals[-1]
    years = len(annuals) - 1
    summary: dict[str, Any] = {}
    for field in ("revenue", "operating_profit", "pat", "eps"):
        start, end = number(first.get(field)), number(last.get(field))
        summary[f"{field}_cagr_pct"] = (
            ((end / start) ** (1 / years) - 1) * 100
            if start is not None and end is not None and start > 0 and end >= 0 and years > 0
            else None
        )
    result["calculated_summary"] = summary

    quarter = result.get("latest_quarter") or {}
    if quarter:
        quarter["revenue_growth_pct"] = pct_change(quarter.get("revenue"), quarter.get("comparison_revenue"))
        quarter["operating_profit_growth_pct"] = pct_change(
            quarter.get("operating_profit"), quarter.get("comparison_operating_profit")
        )
        quarter["pat_growth_pct"] = pct_change(quarter.get("pat"), quarter.get("comparison_pat"))
        quarter["operating_margin_pct"] = safe_ratio(quarter.get("operating_profit"), quarter.get("revenue"), 100)
        exceptional = number(quarter.get("exceptional_after_tax"))
        pat = number(quarter.get("pat"))
        quarter["normalized_pat"] = pat - exceptional if pat is not None and exceptional is not None else None

    price = number(result["company"].get("price"))
    for scenario in result["valuation_scenarios"]:
        implied = number(scenario["forward_eps"]) * number(scenario["pe"])
        scenario["implied_value"] = implied
        scenario["upside_downside_pct"] = pct_change(implied, price)
    return result


def fmt(value: Any, decimals: int = 1) -> str:
    numeric = number(value)
    return "—" if numeric is None else f"{numeric:,.{decimals}f}"


def bullets(items: Any) -> list[str]:
    return [f"- {item}" for item in items] if isinstance(items, list) and items else ["- Not established from current evidence."]


def text_items(items: Any) -> list[str]:
    if not isinstance(items, list) or not items:
        return ["Not established from current evidence."]
    return [str(item) if not isinstance(item, dict) else "; ".join(f"{key}: {value}" for key, value in item.items()) for item in items]


VERDICT_FIELDS = (
    ("business_quality", "Business quality"),
    ("financial_quality", "Financial quality"),
    ("growth_durability", "Growth durability"),
    ("valuation_comfort", "Valuation comfort"),
    ("stance", "Stance"),
)


def verdict_items(qualitative: dict[str, Any]) -> list[str]:
    """Format the required five-point verdict for markdown and HTML."""
    verdict = qualitative.get("verdict") if isinstance(qualitative.get("verdict"), dict) else {}
    items = []
    for key, label in VERDICT_FIELDS:
        value = str(verdict.get(key) or "").strip() or "Not established from current evidence."
        items.append(f"{label}: {value}")
    return items


def quarter_items(quarter: dict[str, Any]) -> list[str]:
    return [
        f"Revenue: {fmt(quarter.get('revenue'))} ({fmt(quarter.get('revenue_growth_pct'))}% YoY)",
        f"Operating profit: {fmt(quarter.get('operating_profit'))} ({fmt(quarter.get('operating_profit_growth_pct'))}% YoY)",
        f"PAT: {fmt(quarter.get('pat'))} ({fmt(quarter.get('pat_growth_pct'))}% YoY)",
        f"Normalized PAT: {fmt(quarter.get('normalized_pat'))}",
    ]


def capital_structure_items(company: dict[str, Any], last_annual: dict[str, Any]) -> list[str]:
    """Latest annual leverage, cash conversion, and market-cap snapshot."""
    currency, unit = company["currency"], company["unit"]
    return [
        f"Latest annual period: {last_annual.get('period', '—')}",
        f"Equity: {currency} {fmt(last_annual.get('equity'))} {unit}",
        f"Borrowings: {currency} {fmt(last_annual.get('borrowings'))} {unit}",
        f"Cash: {currency} {fmt(last_annual.get('cash'))} {unit}",
        f"Net debt: {currency} {fmt(last_annual.get('net_debt'))} {unit}",
        f"Debt/equity: {fmt(last_annual.get('debt_to_equity'), 2)}",
        f"ROE: {fmt(last_annual.get('roe_pct'))}% | ROCE: {fmt(last_annual.get('roce_pct'))}%",
        f"FCF: {currency} {fmt(last_annual.get('fcf'))} {unit} | FCF conversion: {fmt(last_annual.get('fcf_conversion_pct'))}%",
        f"Market cap: {currency} {fmt(company.get('market_cap'))} {unit}",
        f"Shares: {fmt(company.get('shares_crore'), 2)} crore",
    ]


def render_markdown(data: dict[str, Any]) -> str:
    company, annuals = data["company"], data["annuals"]
    qualitative = data.get("qualitative") or {}
    unit, currency = company["unit"], company["currency"]
    lines = [
        f"# Fundamental analysis: {company['name']} ({company['symbol']})",
        "",
        f"**As of:** {company['as_of_date']}  ",
        f"**Price:** {currency} {fmt(company['price'], 2)}  ",
        f"**Scope:** {company.get('scope', 'consolidated')} | **Financial unit:** {currency} {unit}",
        "",
        "## Thesis and verdict",
        "",
        *[f"- {item}" for item in verdict_items(qualitative)],
        "",
        *bullets(qualitative.get("thesis")),
        "",
        "## Financial history",
        "",
        "| Period | Revenue | Op. profit | OPM | PAT | EPS | CFO | FCF | ROCE |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in annuals:
        lines.append(
            f"| {row['period']} | {fmt(row.get('revenue'))} | {fmt(row.get('operating_profit'))} | "
            f"{fmt(row.get('operating_margin_pct'))}% | {fmt(row.get('pat'))} | {fmt(row.get('eps'), 2)} | "
            f"{fmt(row.get('cfo'))} | {fmt(row.get('fcf'))} | {fmt(row.get('roce_pct'))}% |"
        )
    summary = data["calculated_summary"]
    lines.extend([
        "",
        "### Calculated growth",
        "",
        f"- Revenue CAGR: {fmt(summary.get('revenue_cagr_pct'))}%",
        f"- Operating-profit CAGR: {fmt(summary.get('operating_profit_cagr_pct'))}%",
        f"- PAT CAGR: {fmt(summary.get('pat_cagr_pct'))}%",
        f"- EPS CAGR: {fmt(summary.get('eps_cagr_pct'))}%",
    ])
    quarter = data.get("latest_quarter") or {}
    if quarter:
        lines.extend(["", f"## Latest quarter: {quarter.get('period', '')}", "", *[f"- {item}" for item in quarter_items(quarter)]])
    last_annual = annuals[-1] if annuals else {}
    lines.extend(["", "## Balance sheet and capital allocation", "", *[f"- {item}" for item in capital_structure_items(company, last_annual)]])
    for key, title in (("moat", "Business and moat"), ("growth_drivers", "Growth drivers"), ("risks", "Risks"), ("governance", "Governance")):
        lines.extend(["", f"## {title}", "", *bullets(qualitative.get(key))])
    institutional = data.get("institutional") or {}
    for key, title in (
        ("segment_analysis", "Segment and geographic analysis"),
        ("peer_context", "Peer and industry context"),
        ("management_commentary", "Management commentary and execution"),
        ("shareholding", "Shareholding and ownership signals"),
        ("red_team_questions", "Red-team questions"),
    ):
        if institutional.get(key):
            lines.extend(["", f"## {title}", "", *[f"- {item}" for item in text_items(institutional[key])]])
    lines.extend(["", "## Valuation scenarios", "", "| Scenario | Forward EPS | P/E | Implied value | Upside/(downside) |", "|---|---:|---:|---:|---:|"])
    for scenario in data["valuation_scenarios"]:
        lines.append(
            f"| {scenario['name']} | {fmt(scenario['forward_eps'], 2)} | {fmt(scenario['pe'], 1)}x | "
            f"{currency} {fmt(scenario['implied_value'], 2)} | {fmt(scenario['upside_downside_pct'])}% |"
        )
    lines.extend(["", "## Monitorables", "", *bullets(qualitative.get("monitorables")), "", "## Sources", ""])
    for source in data["sources"]:
        lines.append(f"- [{source['title']}]({source['url']}) — {source.get('date', 'date unavailable')}, tier {source.get('tier', '—')}")
    lines.extend(["", "*Research-only analysis, not personalized investment advice. Verify all figures against the cited filings.*", ""])
    return "\n".join(lines)


def render_html(data: dict[str, Any]) -> str:
    """Render a portable report with no external assets or scripts."""
    company, annuals = data["company"], data["annuals"]
    qualitative, institutional = data.get("qualitative") or {}, data.get("institutional") or {}

    def esc(value: Any) -> str:
        return html.escape(str(value))

    def list_html(items: Any) -> str:
        return "<ul>" + "".join(f"<li>{esc(item)}</li>" for item in text_items(items)) + "</ul>"

    rows = "".join(
        "<tr>"
        + f"<td>{esc(row['period'])}</td>"
        + "".join(f"<td>{esc(value)}</td>" for value in (
            fmt(row.get("revenue")), fmt(row.get("operating_profit")), fmt(row.get("operating_margin_pct")) + "%",
            fmt(row.get("pat")), fmt(row.get("eps"), 2), fmt(row.get("cfo")), fmt(row.get("fcf")), fmt(row.get("roce_pct")) + "%",
        ))
        + "</tr>" for row in annuals
    )
    scenario_rows = "".join(
        f"<tr><td>{esc(row['name'])}</td><td>{esc(fmt(row['forward_eps'], 2))}</td><td>{esc(fmt(row['pe']))}x</td>"
        f"<td>{esc(company['currency'])} {esc(fmt(row['implied_value'], 2))}</td><td>{esc(fmt(row['upside_downside_pct']))}%</td></tr>"
        for row in data["valuation_scenarios"]
    )
    source_items = "".join(
        f'<li><a href="{esc(source["url"])}">{esc(source["title"])}</a> — {esc(source.get("date", "date unavailable"))}, tier {esc(source.get("tier", "—"))}</li>'
        for source in data["sources"]
    )
    summary = data["calculated_summary"]
    cards = "".join(
        f'<div class="metric"><span>{esc(label)}</span><strong>{esc(fmt(summary.get(key)))}%</strong></div>'
        for key, label in (("revenue_cagr_pct", "Revenue CAGR"), ("operating_profit_cagr_pct", "Op. profit CAGR"), ("pat_cagr_pct", "PAT CAGR"), ("eps_cagr_pct", "EPS CAGR"))
    )
    verdict_html = "<ul>" + "".join(f"<li>{esc(item)}</li>" for item in verdict_items(qualitative)) + "</ul>"
    quarter = data.get("latest_quarter") or {}
    quarter_html = ""
    if quarter:
        quarter_html = (
            f"<section><h2>Latest quarter: {esc(quarter.get('period', ''))}</h2>"
            f"<ul>{''.join(f'<li>{esc(item)}</li>' for item in quarter_items(quarter))}</ul></section>"
        )
    capital_html = (
        "<section><h2>Balance sheet and capital allocation</h2>"
        f"<ul>{''.join(f'<li>{esc(item)}</li>' for item in capital_structure_items(company, annuals[-1]))}</ul></section>"
    )
    sections = []
    for key, title in (("moat", "Business and moat"), ("growth_drivers", "Growth drivers"), ("risks", "Risks"), ("governance", "Governance")):
        sections.append(f"<section><h2>{title}</h2>{list_html(qualitative.get(key))}</section>")
    for key, title in (("segment_analysis", "Segments and geography"), ("peer_context", "Peer and industry context"), ("management_commentary", "Management commentary and execution"), ("shareholding", "Shareholding and ownership signals"), ("red_team_questions", "Red-team questions")):
        if institutional.get(key):
            sections.append(f"<section><h2>{title}</h2>{list_html(institutional[key])}</section>")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fundamental analysis — {esc(company['name'])}</title>
<style>
:root{{--ink:#17202a;--muted:#667085;--line:#d9e2ec;--brand:#155e75;--paper:#fff;--wash:#f3f7f9;--risk:#9f1239}}*{{box-sizing:border-box}}
body{{margin:0;background:var(--wash);color:var(--ink);font:15px/1.6 Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}}main{{max-width:1120px;margin:auto;background:var(--paper);padding:48px 56px;box-shadow:0 8px 40px #1f293714}}h1{{font-size:36px;line-height:1.15;margin:.25rem 0}}h2{{margin-top:2rem;border-bottom:1px solid var(--line);padding-bottom:.4rem;color:var(--brand)}}.eyebrow,.meta{{color:var(--muted)}}.eyebrow{{text-transform:uppercase;letter-spacing:.12em;font-weight:700}}.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0}}.metric{{padding:16px;background:var(--wash);border-radius:10px}}.metric span{{display:block;color:var(--muted);font-size:12px}}.metric strong{{font-size:22px}}table{{width:100%;border-collapse:collapse;display:block;overflow-x:auto}}th,td{{padding:10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}th:first-child,td:first-child{{text-align:left}}a{{color:var(--brand)}}.disclaimer{{margin-top:32px;padding:16px;border-left:4px solid var(--risk);background:#fff1f2}}@media(max-width:700px){{main{{padding:28px 20px}}.metrics{{grid-template-columns:repeat(2,1fr)}}h1{{font-size:28px}}}}@media print{{body{{background:#fff}}main{{box-shadow:none;padding:0}}}}
</style></head><body><main>
<div class="eyebrow">Institutional fundamental research</div><h1>{esc(company['name'])} <small>({esc(company['symbol'])})</small></h1>
<p class="meta">As of {esc(company['as_of_date'])} · Price {esc(company['currency'])} {esc(fmt(company['price'], 2))} · {esc(company.get('scope', 'consolidated'))} · Financials in {esc(company['currency'])} {esc(company['unit'])}</p>
<section><h2>Thesis and verdict</h2>{verdict_html}{list_html(qualitative.get('thesis'))}</section><div class="metrics">{cards}</div>
<section><h2>Financial history</h2><table><thead><tr><th>Period</th><th>Revenue</th><th>Op. profit</th><th>OPM</th><th>PAT</th><th>EPS</th><th>CFO</th><th>FCF</th><th>ROCE</th></tr></thead><tbody>{rows}</tbody></table></section>
{quarter_html}{capital_html}{''.join(sections)}
<section><h2>Valuation scenarios</h2><table><thead><tr><th>Scenario</th><th>Forward EPS</th><th>P/E</th><th>Implied value</th><th>Upside/(downside)</th></tr></thead><tbody>{scenario_rows}</tbody></table></section>
<section><h2>Monitorables</h2>{list_html(qualitative.get('monitorables'))}</section><section><h2>Sources</h2><ol>{source_items}</ol></section>
<p class="disclaimer">Research-only analysis, not personalized investment advice. Verify all figures against the cited filings.</p>
</main></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Research dataset JSON")
    parser.add_argument("--format", choices=("markdown", "html", "json"), default="markdown")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        raw = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read input: {exc}", file=sys.stderr)
        return 2
    if not isinstance(raw, dict):
        print("error: input root must be a JSON object", file=sys.stderr)
        return 2
    errors = validate(raw)
    if errors:
        print("validation failed:\n- " + "\n- ".join(errors), file=sys.stderr)
        return 2
    enriched = enrich(raw)
    if args.format == "json":
        output = json.dumps(enriched, indent=2, ensure_ascii=False) + "\n"
    elif args.format == "html":
        output = render_html(enriched)
    else:
        output = render_markdown(enriched)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
