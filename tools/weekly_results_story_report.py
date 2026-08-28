from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from terminal.ui.disclaimers import render_disclaimer_block_html

try:
    from terminal.research_council.reports.markdown_renderer import DISCLAIMER as AGENT_ADDA_DISCLAIMER
except Exception:
    AGENT_ADDA_DISCLAIMER = "Not investment advice. For research and learning only."


ROOT = Path(__file__).resolve().parent.parent


def _esc(v: Any) -> str:
    import html as _html
    return _html.escape("" if v is None else str(v))


def _fmt_num(v: Any, digits: int = 2) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    if digits == 0:
        return f"{int(round(f)):,}"
    return f"{f:,.{digits}f}"


def _fmt_pct(v: Any, digits: int = 1) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    sign = "+" if f >= 0 else ""
    return f"{sign}{f:.{digits}f}%"


def _fmt_x(v: Any, digits: int = 2) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{f:.{digits}f}x"


def _klass_for_risk(company: dict[str, Any]) -> str:
    m = (company.get("metrics") or {}) if isinstance(company.get("metrics"), dict) else {}
    d2e = m.get("debt_to_equity_x")
    ic = m.get("interest_cov_x")
    sales_yoy = m.get("sales_yoy_pct")

    try:
        if float(sales_yoy) <= -50:
            return "negative"
    except Exception:
        pass
    try:
        if float(ic) < 1.5:
            return "warning"
    except Exception:
        pass
    try:
        if float(d2e) >= 1.5:
            return "warning"
    except Exception:
        pass
    return ""


def _kpi(label: str, value: str, *, klass: str = "") -> str:
    klass_attr = f" {klass}" if klass else ""
    return f'<div class="kpi"><span>{_esc(label)}</span><b class="{_esc(klass_attr.strip())}">{_esc(value)}</b></div>'


def _ltfoods_template_css() -> str:
    """CSS adapted from the LTFOODS comprehensive research report template."""
    return """
@font-face{font-family:"Plus Jakarta Sans";font-style:normal;font-weight:400 700;font-display:swap;src:url("https://agentadda.in/_next/static/media/636a5ac981f94f8b-s.p.woff2") format("woff2")}
@font-face{font-family:"Playfair Display";font-style:normal;font-weight:400 700;font-display:swap;src:url("https://agentadda.in/_next/static/media/eaead17c7dbfcd5d-s.p.woff2") format("woff2")}
:root{
  --bg:#0d1117;--bg2:#111820;--panel:#161b22;--panel2:#1c2128;--panel3:#202936;
  --ink:#f8faff;--muted:#a8b3bf;--subtle:#788391;--line:#30363d;
  --sky:#0ea5e9;--sky2:#38bdf8;--stone:#d6d3d1;--green:#22c55e;--amber:#f59e0b;--red:#f43f5e;
  --display:"Playfair Display",Georgia,"Times New Roman",serif;
  --sans:"Plus Jakarta Sans",Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  --mono:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono",monospace;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:linear-gradient(180deg,var(--bg),var(--bg2) 36%,var(--bg));color:var(--ink);font:14px/1.65 var(--sans);-webkit-font-smoothing:antialiased}
a{color:var(--sky2);text-decoration:none} a:hover{text-decoration:underline}
.page{max-width:1240px;margin:0 auto;padding:26px 24px 64px}
.topbar{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:10px 0 22px;border-bottom:1px solid var(--line)}
.brand{display:flex;align-items:center;gap:12px;font-weight:700;color:var(--ink)}
.mark{width:36px;height:36px;border-radius:50%;display:grid;place-items:center;background:#f8faff;color:#0d1117;font:700 14px var(--sans)}
.nav{display:flex;gap:10px;flex-wrap:wrap;color:var(--muted);font-size:12px}
.nav a{color:var(--muted);padding:6px 10px;border:1px solid var(--line);border-radius:999px;background:#ffffff08}
.hero{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(300px,.75fr);gap:28px;padding:44px 0 30px;align-items:end}
.eyebrow{display:inline-flex;align-items:center;gap:8px;color:var(--sky2);font-weight:700;text-transform:uppercase;font-size:11px;letter-spacing:.12em;margin-bottom:16px}
.dot{width:8px;height:8px;border-radius:50%;background:var(--sky)}
h1,h2,h3{font-family:var(--display);line-height:1.12;margin:0;color:var(--ink)}
h1{font-size:clamp(40px,6vw,76px);font-weight:700;letter-spacing:0}
h1 span{color:var(--sky2)}
.subtitle{max-width:760px;margin:18px 0 0;color:var(--stone);font-size:17px;line-height:1.7}
.meta{margin-top:18px;color:var(--subtle);font-size:12px}
.hero-panel{border:1px solid var(--line);background:linear-gradient(180deg,#17212d,#111820);border-radius:8px;padding:18px;box-shadow:0 20px 70px #00000055}
.price{font:800 34px/1 var(--sans);letter-spacing:0;color:var(--ink)}
.move{font:700 14px var(--mono);color:var(--muted);margin-top:8px}
.verdict{margin-top:18px;padding-top:18px;border-top:1px solid var(--line);color:var(--stone)}
.badge-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}
.badge{font-size:11px;font-weight:700;text-transform:uppercase;color:var(--sky2);border:1px solid #0ea5e955;background:#0ea5e912;border-radius:999px;padding:5px 9px}
section{padding:28px 0;border-top:1px solid var(--line)}
.section-head{display:flex;align-items:end;justify-content:space-between;gap:18px;margin-bottom:18px}
h2{font-size:32px}
.section-note{max-width:560px;color:var(--muted);font-size:13px}
h3{font-size:20px;margin:4px 0 10px}
p{margin:0 0 14px;color:var(--stone)}
.grid{display:grid;gap:14px}
.grid.cols-4{grid-template-columns:repeat(4,minmax(0,1fr))}
.grid.cols-3{grid-template-columns:repeat(3,minmax(0,1fr))}
.grid.cols-2{grid-template-columns:repeat(2,minmax(0,1fr))}
.card{background:linear-gradient(180deg,var(--panel),#111820);border:1px solid var(--line);border-radius:8px;padding:16px}
.metric-label{color:var(--subtle);font-size:11px;text-transform:uppercase;font-weight:700;letter-spacing:.08em}
.metric-value{display:block;font-size:24px;font-weight:800;line-height:1.15;margin-top:7px;color:var(--ink)}
.metric-detail{display:block;color:var(--muted);font-size:12px;margin-top:6px}
.green{color:var(--green)} .amber{color:var(--amber)} .red{color:var(--red)} .muted{color:var(--muted)}
.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:#0d1117}
table{width:100%;border-collapse:collapse;min-width:760px}
th,td{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top;text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);background:#0d1117}
tr:last-child td{border-bottom:none}
.narrative{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.pullquote{font-family:var(--display);font-size:22px;line-height:1.25;margin:0;color:#f4fbff}
ul{margin:10px 0 0 18px;padding:0;color:var(--stone)}
li{margin:6px 0}
footer{padding-top:24px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}
@media (max-width: 980px){
  .hero{grid-template-columns:1fr}
  .grid.cols-4,.grid.cols-3,.grid.cols-2,.narrative{grid-template-columns:1fr}
}
"""


def _company_story(company: dict[str, Any]) -> str:
    sym = company.get("symbol", "")
    name = company.get("name", "")
    period = company.get("period_label", "")
    headline = company.get("headline", "")
    url = company.get("ixbrl_url", "")
    business_model = company.get("business_model") or []
    growth_drivers = company.get("growth_drivers") or []
    recent_events = company.get("recent_events") or []
    key_sources = company.get("key_sources") or []
    m = (company.get("metrics") or {}) if isinstance(company.get("metrics"), dict) else {}

    risk = _klass_for_risk(company)

    revenue = m.get("revenue_cr")
    pat = m.get("pat_cr")
    npm = m.get("pat_margin_pct")
    sales_yoy = m.get("sales_yoy_pct")
    sales_qoq = m.get("sales_qoq_pct")
    pat_yoy = m.get("pat_yoy_pct")
    pat_qoq = m.get("pat_qoq_pct")
    roce = m.get("roce_pct")
    roe = m.get("roe_pct")
    d2e = m.get("debt_to_equity_x")
    ic = m.get("interest_cov_x")
    debt_days = m.get("debtor_days")
    inv_days = m.get("inventory_days")
    dpo = m.get("dpo_days")
    ccc = m.get("ccc_days")

    # Story bullets: deterministic, finance-operator style
    bull = []
    base = []
    bear = []
    watch = []
    gaps = []

    if isinstance(sales_yoy, (int, float)) and sales_yoy >= 20:
        bull.append(f"Growth is real: Sales YoY {_fmt_pct(sales_yoy)} (scale + demand tailwinds).")
    if isinstance(npm, (int, float)) and npm >= 10:
        bull.append(f"Profitability is meaningful: NPM ~{_fmt_pct(npm)} with room for reinvestment.")
    if isinstance(roce, (int, float)) and roce >= 18:
        bull.append(f"High capital efficiency: ROCE ~{_fmt_num(roce,1)}%.")

    base.append("Assume QoQ noise; focus on YoY + margin persistence over 2–3 quarters.")
    if d2e is not None:
        base.append(f"Balance sheet lens: D/E {_fmt_x(d2e)} and interest coverage {_fmt_x(ic)} are the risk throttle.")

    if isinstance(ic, (int, float)) and ic < 1.5:
        bear.append(f"Debt servicing risk: interest coverage {_fmt_x(ic)} puts downside convexity on any shock.")
    if isinstance(d2e, (int, float)) and d2e >= 1.5:
        bear.append(f"Leverage risk: D/E {_fmt_x(d2e)} limits flexibility; refinancing terms matter.")
    if isinstance(sales_yoy, (int, float)) and sales_yoy <= -50:
        bear.append(f"Demand / operations stress: Sales YoY {_fmt_pct(sales_yoy)} suggests a structural break.")

    if debt_days is not None:
        watch.append(f"Cash conversion: Debtor days {int(debt_days)}; align OCF with PAT over time.")
        if isinstance(debt_days, (int, float)) and debt_days >= 90:
            gaps.append("Receivables story: who are the customers, what are payment terms, and is DSO structurally high?")
    if inv_days is not None:
        watch.append(f"Working capital: Inventory days {int(inv_days)}; watch for slow-moving build-up.")
        if isinstance(inv_days, (int, float)) and inv_days >= 120:
            gaps.append("Inventory story: is inventory build intentional (capacity/seasonality) or a demand-risk signal?")
    if ccc is not None:
        watch.append(f"Cycle health: CCC {int(ccc)} days; any deterioration usually precedes margin pain.")
        if isinstance(ccc, (int, float)) and ccc >= 90:
            gaps.append("Working-capital financing: how is growth funded (internal accruals vs short-term borrowings)?")

    if isinstance(ic, (int, float)) and ic < 2:
        gaps.append("Debt/refinancing: maturities, interest-rate exposure, covenants, and any pledged assets/receivables.")
    if isinstance(d2e, (int, float)) and d2e < 0:
        gaps.append("Solvency: confirm net worth status and any restructuring / NCLT / settlement milestones.")
    if isinstance(sales_yoy, (int, float)) and sales_yoy < 0:
        gaps.append("Demand break: is the revenue decline cyclical, customer-specific, or due to product/price resets?")

    # Always useful prompts (non-fabricated)
    gaps.extend(
        [
            "Moat/pricing power: what prevents margin mean-reversion (brand, switching costs, regulation, scale)?",
            "Capital allocation: how management uses cash (capex, acquisitions, dividends, buybacks, debt paydown).",
            "Disclosures: any related-party, contingent liabilities, or auditor emphasis worth tracking?",
        ]
    )

    def ul(items: list[str]) -> str:
        if not items:
            return "<p class='neutral'>n/a</p>"
        return "<ul>" + "".join(f"<li>{_esc(x)}</li>" for x in items[:6]) + "</ul>"

    def sources(items: list[str]) -> str:
        if not items:
            return "<p class='neutral'>n/a</p>"
        links = []
        for u in items[:8]:
            u = str(u)
            links.append(f"<li><a href=\"{_esc(u)}\" target=\"_blank\" rel=\"noreferrer\">{_esc(u)}</a></li>")
        return "<ul>" + "".join(links) + "</ul>"

    # Prefix anchors to avoid collisions in multi-company mode.
    aid = (str(sym or "company").strip().lower() or "company").replace(" ", "-")

    rev_str = _fmt_num(revenue, 0)
    pat_str = _fmt_num(pat, 0)
    npm_str = _fmt_pct(npm, 1)
    d2e_str = _fmt_x(d2e)
    ic_str = _fmt_x(ic)

    pat_cls = "green" if isinstance(pat, (int, float)) and pat > 0 else "red" if isinstance(pat, (int, float)) and pat < 0 else ""

    return "\n".join(
        [
            f'<section id="{aid}-verdict">',
            '<div class="section-head">',
            f"<h2>{_esc(sym)} — {_esc(name)}</h2>",
            f'<p class="section-note">{_esc(period)} · <a href="{_esc(url)}" target="_blank" rel="noreferrer">Primary filing (iXBRL)</a></p>',
            "</div>",
            '<div class="narrative">',
            f'<div class="card"><p class="pullquote">{_esc(headline)}</p>'
            "<p style=\"margin-top:18px\">The goal is to explain the operating story (drivers + risks) and the next evidence to pull — not to restate a ratios table.</p>"
            "</div>",
            '<div class="card"><h3>Decision frame</h3>'
            "<ul>"
            f"<li><strong>Revenue / PAT:</strong> ₹{_esc(rev_str)} cr / ₹{_esc(pat_str)} cr</li>"
            f"<li><strong>Margin:</strong> PAT margin { _esc(npm_str) }</li>"
            f"<li><strong>Balance sheet:</strong> D/E { _esc(d2e_str) }, interest cover { _esc(ic_str) }</li>"
            f"<li><strong>Working capital:</strong> debtors { _esc(_fmt_num(debt_days,0)) }d, inventory { _esc(_fmt_num(inv_days,0)) }d, CCC { _esc(_fmt_num(ccc,0)) }d</li>"
            "</ul></div>",
            "</div>",
            "</section>",
            f'<section id="{aid}-snapshot">',
            '<div class="section-head"><h2>Snapshot</h2><p class="section-note">Key KPIs for quick orientation.</p></div>',
            '<div class="grid cols-4">',
            f'<div class="card"><span class="metric-label">Revenue (₹ cr)</span><span class="metric-value">{_esc(rev_str)}</span><span class="metric-detail muted">Latest period</span></div>',
            f'<div class="card"><span class="metric-label">PAT (₹ cr)</span><span class="metric-value {pat_cls}">{_esc(pat_str)}</span><span class="metric-detail muted">Latest period</span></div>',
            f'<div class="card"><span class="metric-label">PAT margin</span><span class="metric-value">{_esc(npm_str)}</span><span class="metric-detail muted">Profit quality</span></div>',
            f'<div class="card"><span class="metric-label">Sales YoY</span><span class="metric-value">{_esc(_fmt_pct(sales_yoy,1))}</span><span class="metric-detail muted">Growth</span></div>',
            "</div>",
            '<div class="grid cols-3" style="margin-top:14px">',
            f"<div class=\"card\"><h3>Business model</h3>{ul(list(business_model))}</div>",
            f"<div class=\"card\"><h3>Growth drivers</h3>{ul(list(growth_drivers))}</div>",
            f"<div class=\"card\"><h3>Recent events</h3>{ul(list(recent_events))}</div>",
            "</div>",
            "</section>",
            f'<section id="{aid}-cases">',
            '<div class="section-head"><h2>Bull / Base / Bear</h2><p class="section-note">What would need to be true, and what breaks.</p></div>',
            '<div class="grid cols-3">',
            f"<div class=\"card\"><h3>Bull case</h3>{ul(bull)}</div>",
            f"<div class=\"card\"><h3>Base case</h3>{ul(base)}</div>",
            f"<div class=\"card\"><h3>Bear case</h3>{ul(bear)}</div>",
            "</div>",
            '<div class="grid cols-2" style="margin-top:14px">',
            f"<div class=\"card\"><h3>What to watch next</h3>{ul(watch)}</div>",
            f"<div class=\"card\"><h3>Story gaps to close</h3>{ul(gaps)}</div>",
            "</div>",
            "</section>",
            f'<section id="{aid}-sources">',
            '<div class="section-head"><h2>Sources</h2><p class="section-note">Primary documents and issuer resources.</p></div>',
            f'<div class="card">{sources(list(key_sources))}</div>',
            "</section>",
        ]
    )


def _global_narrative(data: dict[str, Any]) -> str:
    companies = data.get("companies") or []
    if not companies:
        return "<p class='neutral'>No companies provided.</p>"

    growth = []
    margins = []
    risk = []
    for c in companies:
        m = c.get("metrics") or {}
        sym = c.get("symbol")
        growth.append((m.get("sales_yoy_pct"), sym))
        margins.append((m.get("pat_margin_pct"), sym))
        risk.append((m.get("debt_to_equity_x"), sym))

    def best(items: list[tuple[Any, Any]], *, reverse: bool = True) -> str:
        vals = []
        for v, s in items:
            if isinstance(v, (int, float)):
                vals.append((float(v), s))
        if not vals:
            return "n/a"
        vals.sort(reverse=reverse)
        v, s = vals[0]
        return f"{_esc(s)} ({_fmt_pct(v, 1) if 'pct' in str(items[0][0]).lower() else _fmt_num(v, 1)})"

    return (
        "<p class=\"pullquote\">A company story is a causal chain: demand + execution → margins + cash → balance sheet → optionality.</p>"
        "<p style=\"margin-top:18px\">Use the per-company sections to understand: (1) what the business is, (2) what changed this period, (3) what could break, and (4) what evidence to pull next.</p>"
    )


def render_html(data: dict[str, Any]) -> str:
    as_of = data.get("as_of_date") or datetime.now().date().isoformat()
    universe = data.get("universe") or "—"
    notes = data.get("data_notes") or []
    companies = data.get("companies") or []

    notes_html = "<ul>" + "".join(f"<li>{_esc(x)}</li>" for x in notes[:10]) + "</ul>" if notes else "<p class='muted'>—</p>"
    companies_html = "".join(_company_story(c) for c in companies)

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>Agent Adda Research | Company Story Pack</title>",
            "<style>",
            _ltfoods_template_css(),
            "</style>",
            "</head>",
            "<body>",
            '<div class="page">',
            '<div class="topbar">',
            '<div class="brand"><div class="mark">AA</div><div>Agent Adda Research</div></div>',
            '<div class="nav">'
            '<a href="#summary">Summary</a>'
            '<a href="#notes">Data notes</a>'
            '<a href="#companies">Companies</a>'
            '<a href="#disclaimers">Disclaimers</a>'
            "</div>",
            "</div>",
            '<div class="hero">',
            '<div class="hero-left">',
            '<div class="eyebrow"><span class="dot"></span> Comprehensive company story pack</div>',
            f"<h1>Weekly Results <span>Story</span></h1>",
            f"<p class=\"subtitle\">As of { _esc(as_of) } — { _esc(universe) }. This report is designed to go beyond ratio screens by articulating a causal story and the next evidence to pull.</p>",
            f"<div class=\"meta\">{_esc(AGENT_ADDA_DISCLAIMER)}</div>",
            "</div>",
            '<div class="hero-panel">',
            f"<div class=\"price\">{_esc(as_of)}</div>",
            f"<div class=\"move\">Coverage: { _esc(len(companies)) } company(ies)</div>",
            '<div class="badge-row"><span class="badge">Filing-led</span><span class="badge">Story-first</span><span class="badge">Research-only</span></div>',
            '<div class="verdict">Read the story first; then use sources to validate and deepen.</div>',
            "</div>",
            "</div>",
            f'<section id="summary"><div class="section-head"><h2>Executive Summary</h2><p class="section-note">How to use this pack.</p></div><div class="card">{_global_narrative(data)}</div></section>',
            f'<section id="notes"><div class="section-head"><h2>Data notes</h2><p class="section-note">Scope and limitations.</p></div><div class="card">{notes_html}</div></section>',
            f'<section id="companies"><div class="section-head"><h2>Companies</h2><p class="section-note">One story per company.</p></div></section>',
            companies_html or "<p class='muted'>No companies.</p>",
            f'<section id="disclaimers"><div class="section-head"><h2>Disclaimers</h2><p class="section-note">Read before using this report.</p></div><div class="card">{render_disclaimer_block_html()}</div></section>',
            f"<footer>{_esc(AGENT_ADDA_DISCLAIMER)}</footer>",
            "</div>",
            "</body>",
            "</html>",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate a story-first weekly results report using Agent Adda theme.")
    p.add_argument(
        "--input",
        default="reports/latest/weekly_results_story_input_2026-08-25.json",
        help="Input JSON path (default: reports/latest/weekly_results_story_input_2026-08-25.json)",
    )
    p.add_argument(
        "--out",
        default="reports/latest/weekly_results_story_2026-08-25.html",
        help="Output HTML path (default: reports/latest/weekly_results_story_2026-08-25.html)",
    )
    p.add_argument(
        "--symbol",
        default="",
        help="Optional: render only one symbol (e.g. MANIPALHOS).",
    )
    args = p.parse_args(argv)

    in_path = ROOT / args.input
    out_path = ROOT / args.out

    data = json.loads(in_path.read_text(encoding="utf-8"))
    if args.symbol:
        sym = str(args.symbol).strip().upper()
        companies = data.get("companies") or []
        data["companies"] = [c for c in companies if str(c.get("symbol", "")).upper() == sym]
        data["universe"] = f"{data.get('universe') or ''} · symbol={sym}".strip(" ·")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_html(data), encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
