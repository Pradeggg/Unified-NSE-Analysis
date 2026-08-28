from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from terminal.ui.disclaimers import render_disclaimer_block_html
from terminal.ui.html_theme import agent_adda_dark_css


ROOT = Path(__file__).resolve().parent.parent


def _esc(v: Any) -> str:
    import html as _html
    return _html.escape("" if v is None else str(v))


def _num(v: Any, digits: int = 2) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{f:,.{digits}f}"


def _pct(n: Any, d: Any, digits: int = 1) -> str:
    try:
        n = float(n)
        d = float(d)
    except (TypeError, ValueError):
        return "—"
    if d == 0:
        return "—"
    return f"{(n / d) * 100:.{digits}f}%"


def _row(label: str, value: str, pct: str = "", *, klass: str = "") -> str:
    c = f" {klass}" if klass else ""
    return f"<tr><td>{_esc(label)}</td><td class='num{_esc(c)}'>{_esc(value)}</td><td class='num muted'>{_esc(pct)}</td></tr>"


def render(symbol_data: dict[str, Any], *, as_of: str) -> str:
    sym = symbol_data.get("symbol", "—")
    name = symbol_data.get("name", "—")
    period = symbol_data.get("period_label", "—")
    ixbrl_url = symbol_data.get("ixbrl_url", "")
    m = symbol_data.get("metrics") or {}

    revenue = m.get("revenue_cr")
    other_income = m.get("other_income_cr")
    total_exp = m.get("total_expenses_cr")
    finance = m.get("finance_cost_cr")
    dep = m.get("depreciation_cr")
    employee = m.get("employee_cost_cr")
    other_exp = m.get("other_expenses_cr")
    pbt_margin = m.get("pbt_margin_pct")
    pat = m.get("pat_cr")
    pat_margin = m.get("pat_margin_pct")

    headline_bits = []
    if isinstance(pat_margin, (int, float)):
        headline_bits.append(f"PAT margin ~{pat_margin:.1f}%.")
    if isinstance(finance, (int, float)) and isinstance(revenue, (int, float)) and revenue:
        headline_bits.append(f"Finance cost ~{(finance/revenue)*100:.1f}% of revenue.")
    if isinstance(dep, (int, float)) and isinstance(revenue, (int, float)) and revenue:
        headline_bits.append(f"D&A ~{(dep/revenue)*100:.1f}% of revenue.")
    headline = " ".join(headline_bits) or "Results snapshot from iXBRL filing."

    rows = []
    rows.append(_row("Revenue from operations (₹ cr)", _num(revenue), "100%"))
    rows.append(_row("Other income (₹ cr)", _num(other_income), _pct(other_income, revenue)))
    rows.append(_row("Total expenses (₹ cr)", _num(total_exp), _pct(total_exp, revenue)))
    rows.append(_row("Employee costs (₹ cr)", _num(employee), _pct(employee, revenue)))
    rows.append(_row("Other expenses (₹ cr)", _num(other_exp), _pct(other_exp, revenue)))
    rows.append(_row("Finance costs (₹ cr)", _num(finance), _pct(finance, revenue)))
    rows.append(_row("Depreciation & amort. (₹ cr)", _num(dep), _pct(dep, revenue)))
    rows.append(_row("PBT margin", _num(pbt_margin, 2) + "%", ""))
    rows.append(_row("PAT (₹ cr)", _num(pat), _pct(pat, revenue), klass="positive" if isinstance(pat, (int, float)) and pat > 0 else "negative"))
    rows.append(_row("PAT margin", _num(pat_margin, 2) + "%", ""))

    extra_css = """
.num { text-align:right; font-variant-numeric: tabular-nums; }
.muted { color: var(--muted); }
table { width:100%; border-collapse: collapse; }
th, td { border-top:1px solid rgba(255,255,255,.08); padding:8px; }
th { text-align:left; color: var(--muted); font-weight:700; }
.positive { color: var(--green); }
.negative { color: var(--red); }
"""

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{_esc(sym)} — iXBRL Results Snapshot</title>",
            "<style>",
            agent_adda_dark_css(),
            extra_css,
            "</style>",
            "</head>",
            "<body>",
            "<header>",
            f"<h1>{_esc(sym)} — Results Snapshot</h1>",
            f"<div class='sub'>{_esc(name)} · { _esc(period) } · As of { _esc(as_of) } · Filing: <a href='{_esc(ixbrl_url)}' target='_blank' rel='noreferrer'>iXBRL</a></div>",
            "</header>",
            "<main class='grid'>",
            f"<section class='panel summary-panel wide'><h2>Executive Summary</h2><p class='lede'>{_esc(headline)}</p><small>Source: iXBRL filing (primary).</small></section>",
            "<section class='panel wide'><h2>P&L Bridge (key lines)</h2>",
            "<table>",
            "<thead><tr><th>Line item</th><th class='num'>Value</th><th class='num'>% of revenue</th></tr></thead>",
            "<tbody>",
            "".join(rows),
            "</tbody></table></section>",
            "<section class='panel wide'><h2>Disclaimers</h2>",
            render_disclaimer_block_html(),
            "</section>",
            "</main>",
            "<footer>Not investment advice. For research and learning only.</footer>",
            "</body>",
            "</html>",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate an iXBRL-based results snapshot HTML from story input JSON.")
    p.add_argument("--input", default="reports/latest/weekly_results_story_input_2026-08-25.json")
    p.add_argument("--symbol", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)

    data = json.loads((ROOT / args.input).read_text(encoding="utf-8"))
    sym = str(args.symbol).strip().upper()
    companies = data.get("companies") or []
    match = None
    for c in companies:
        if str(c.get("symbol", "")).upper() == sym:
            match = c
            break
    if not match:
        raise SystemExit(f"Symbol not found in input: {sym}")

    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(match, as_of=data.get("as_of_date") or datetime.now().date().isoformat()), encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

