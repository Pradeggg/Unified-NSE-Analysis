#!/usr/bin/env python3
"""
Phase 6: Comprehensive report.
Assembles portfolio summary, PnL, risk & scenarios, market sentiment, sector assessment,
technical summary, fundamental table, and stock narratives into one MD and HTML report.
HTML matches working-sector auto_components_comprehensive_report: same CSS and tabbed layout.
"""
from __future__ import annotations

import html as html_module
import json
from datetime import date
from pathlib import Path

try:
    from config import (
        OUTPUT_DIR,
        PORTFOLIO_SUMMARY_JSON,
        PNL_SUMMARY_MD,
        RISK_METRICS_JSON,
        SCENARIO_NARRATIVE_MD,
        MARKET_SENTIMENT_MD,
        SECTOR_ASSESSMENT_MD,
        TECHNICAL_SUMMARY_MD,
        TECHNICAL_BY_STOCK_CSV,
        FUNDAMENTAL_BY_STOCK_CSV,
        STOCK_NARRATIVES_MD,
        STOCK_NARRATIVES_JSON,
        REPORT_MD,
        REPORT_HTML,
    )
except ImportError:
    OUTPUT_DIR = Path(__file__).resolve().parent / "output"
    PORTFOLIO_SUMMARY_JSON = OUTPUT_DIR / "portfolio_summary.json"
    PNL_SUMMARY_MD = OUTPUT_DIR / "pnl_summary.md"
    RISK_METRICS_JSON = OUTPUT_DIR / "risk_metrics.json"
    SCENARIO_NARRATIVE_MD = OUTPUT_DIR / "scenario_narrative.md"
    MARKET_SENTIMENT_MD = OUTPUT_DIR / "market_sentiment.md"
    SECTOR_ASSESSMENT_MD = OUTPUT_DIR / "sector_assessment.md"
    TECHNICAL_SUMMARY_MD = OUTPUT_DIR / "technical_summary.md"
    TECHNICAL_BY_STOCK_CSV = OUTPUT_DIR / "technical_by_stock.csv"
    FUNDAMENTAL_BY_STOCK_CSV = OUTPUT_DIR / "fundamental_by_stock.csv"
    STOCK_NARRATIVES_MD = OUTPUT_DIR / "stock_narratives.md"
    STOCK_NARRATIVES_JSON = OUTPUT_DIR / "stock_narratives.json"
    REPORT_MD = OUTPUT_DIR / "portfolio_comprehensive_report.md"
    REPORT_HTML = OUTPUT_DIR / "portfolio_comprehensive_report.html"

# These new paths are always derived from OUTPUT_DIR (not in config.py)
RISK_METRICS_CSV = OUTPUT_DIR / "risk_metrics.csv"
RISK_METRICS_PORTFOLIO_CSV = OUTPUT_DIR / "risk_metrics_portfolio.csv"
SCENARIO_PROJECTIONS_CSV = OUTPUT_DIR / "scenario_projections.csv"
HOLDINGS_CSV = OUTPUT_DIR / "holdings.csv"
PNL_AGGREGATES_CSV = OUTPUT_DIR / "pnl_aggregates.csv"
CLOSED_PNL_CSV = OUTPUT_DIR / "closed_pnl.csv"

# Same CSS as working-sector/output/auto_components_comprehensive_report.html
REPORT_CSS = """
:root {
  --md-primary: #00897B;
  --md-primary-dark: #00695C;
  --md-primary-light: #4DB6AC;
  --md-primary-bg: #B2DFDB;
  --md-surface: #FFFFFF;
  --md-bg: #E0F2F1;
  --md-text: #004D40;
  --md-text-secondary: #00796B;
  --md-divider: rgba(0, 137, 123, 0.2);
  --md-elevation-1: 0 1px 3px rgba(0, 105, 92, 0.12), 0 1px 2px rgba(0, 105, 92, 0.24);
  --md-elevation-2: 0 3px 6px rgba(0, 105, 92, 0.15), 0 2px 4px rgba(0, 105, 92, 0.12);
  --md-elevation-3: 0 10px 20px rgba(0, 105, 92, 0.15), 0 3px 6px rgba(0, 105, 92, 0.1);
  --md-radius: 8px;
  --md-radius-sm: 4px;
}
* { box-sizing: border-box; }
body {
  font-family: 'Roboto', system-ui, sans-serif;
  margin: 0;
  padding: 0;
  background: var(--md-bg);
  color: var(--md-text);
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
.app-bar {
  background: linear-gradient(135deg, var(--md-primary-dark) 0%, var(--md-primary) 100%);
  color: #fff;
  padding: 16px 24px;
  box-shadow: var(--md-elevation-2);
}
.app-bar h1 { margin: 0; font-size: 1.5rem; font-weight: 500; letter-spacing: 0.02em; }
.app-bar .meta { margin: 4px 0 0 0; font-size: 0.875rem; opacity: 0.9; font-weight: 300; }
.main-content { padding: 24px; max-width: 1400px; margin: 0 auto; }
.tabs { display: flex; gap: 0; margin-bottom: 0; background: var(--md-surface); border-radius: var(--md-radius) var(--md-radius) 0 0; box-shadow: var(--md-elevation-1); overflow: hidden; flex-wrap: wrap; }
.tab-btn { padding: 14px 20px; cursor: pointer; border: none; background: transparent; font-family: inherit; font-size: 0.875rem; font-weight: 500; color: var(--md-text-secondary); text-transform: uppercase; letter-spacing: 0.05em; position: relative; transition: color 0.2s, background 0.2s; }
.tab-btn:hover { background: var(--md-bg); color: var(--md-primary-dark); }
.tab-btn.active { color: var(--md-primary); background: rgba(0, 137, 123, 0.08); }
.tab-btn.active::after { content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 3px; background: var(--md-primary); }
.tab-panel { display: none; background: var(--md-surface); padding: 24px; border-radius: 0 0 var(--md-radius) var(--md-radius); box-shadow: var(--md-elevation-1); overflow-x: auto; border: 1px solid var(--md-divider); border-top: none; min-height: 320px; }
.tab-panel.active { display: block; }
.card-section { background: var(--md-surface); border-radius: var(--md-radius); padding: 20px; margin-bottom: 20px; box-shadow: var(--md-elevation-1); border: 1px solid var(--md-divider); }
.overview-cards { display: flex; flex-direction: column; gap: 20px; }
.card-section pre { font-family: 'Roboto', sans-serif; white-space: pre-wrap; word-wrap: break-word; margin: 0; padding: 16px; background: var(--md-bg); border-radius: var(--md-radius-sm); border-left: 4px solid var(--md-primary-light); font-size: 0.8125rem; line-height: 1.6; color: var(--md-text); }
.card-title { margin: 0 0 12px 0; font-size: 1rem; font-weight: 500; color: var(--md-primary-dark); padding-bottom: 8px; border-bottom: 1px solid var(--md-divider); }
.md-rendered { font-size: 0.9rem; line-height: 1.6; }
.md-rendered h1 { font-size: 1.1rem; margin: 0 0 0.5rem 0; color: var(--md-primary-dark); font-weight: 500; }
.md-rendered h2 { font-size: 1rem; margin: 1rem 0 0.4rem 0; color: var(--md-primary-dark); font-weight: 500; }
.md-rendered h3 { font-size: 0.95rem; margin: 0.75rem 0 0.35rem 0; color: var(--md-primary-dark); font-weight: 500; }
.md-rendered p { margin: 0 0 0.6rem 0; }
.md-rendered ul, .md-rendered ol { margin: 0.4rem 0 0.75rem 0; padding-left: 1.5rem; }
.md-rendered li { margin: 0.2rem 0; }
.md-rendered hr { border: none; border-top: 1px solid var(--md-divider); margin: 1rem 0; }
.md-rendered strong { font-weight: 500; color: var(--md-text); }
.md-rendered table { width: 100%; margin: 0.5rem 0; font-size: 0.8rem; border-collapse: collapse; }
.md-rendered th, .md-rendered td { border: 1px solid var(--md-divider); padding: 6px 8px; text-align: left; }
.md-rendered th { background: var(--md-primary-light); color: var(--md-text); font-weight: 500; }
.md-rendered a { color: var(--md-primary); text-decoration: none; }
.md-rendered a:hover { text-decoration: underline; }
.md-rendered.md-fallback { white-space: pre-wrap; font-family: inherit; }
.prose { padding: 0 4px; }
.prose h3 { margin: 24px 0 12px 0; font-size: 1.125rem; font-weight: 500; color: var(--md-primary-dark); padding-bottom: 8px; border-bottom: 1px solid var(--md-divider); }
.prose h3:first-child { margin-top: 0; }
.prose pre { font-family: 'Roboto', sans-serif; white-space: pre-wrap; word-wrap: break-word; margin: 0 0 16px 0; padding: 16px; background: var(--md-bg); border-radius: var(--md-radius-sm); border-left: 4px solid var(--md-primary-light); font-size: 0.8125rem; line-height: 1.6; color: var(--md-text); }
table { border-collapse: collapse; width: 100%; font-size: 0.8125rem; border-radius: var(--md-radius); overflow: hidden; box-shadow: var(--md-elevation-1); }
th, td { padding: 12px 16px; text-align: left; border-bottom: 1px solid var(--md-divider); }
th { background: var(--md-primary); color: #fff; cursor: pointer; user-select: none; white-space: nowrap; font-weight: 500; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.05em; transition: background 0.2s; }
th:hover { background: var(--md-primary-dark); }
.sortable th { cursor: pointer; user-select: none; position: relative; padding-right: 24px; }
.sortable th::after { content: ' ⇅'; opacity: 0.4; font-size: 0.85em; }
.sortable th.sort-asc::after { content: ' ▲'; opacity: 1; }
.sortable th.sort-desc::after { content: ' ▼'; opacity: 1; }
tbody tr { transition: background 0.15s; }
tbody tr:nth-child(even) { background: rgba(0, 137, 123, 0.04); }
tbody tr:hover { background: rgba(0, 137, 123, 0.08); }
.sortable { border-collapse: collapse; width: 100%; border-radius: var(--md-radius); overflow: hidden; box-shadow: var(--md-elevation-1); }
.sortable td, .sortable th { border-bottom: 1px solid var(--md-divider); }
.sortable tbody tr:last-child td { border-bottom: none; }
.cell-best { background: rgba(0, 150, 136, 0.18) !important; font-weight: 600; color: var(--md-primary-dark); }
.table-scroll { overflow-x: auto; margin: 0 -4px; border-radius: var(--md-radius); }
.narrative-card { background: var(--md-surface); border: 1px solid var(--md-divider); border-radius: var(--md-radius); padding: 20px; margin-bottom: 24px; box-shadow: var(--md-elevation-1); }
.narrative-title { margin: 0 0 8px 0; font-size: 1.1rem; font-weight: 500; color: var(--md-primary-dark); padding-bottom: 8px; border-bottom: 1px solid var(--md-divider); }
.narrative-recommendation { margin: 0 0 12px 0; padding: 8px 12px; background: var(--md-bg); border-left: 4px solid var(--md-primary); font-size: 0.95rem; }
.narrative-rec-rationale { color: var(--md-text-secondary); font-style: italic; }
.narrative-fund-label { margin: 12px 0 6px 0; font-size: 0.875rem; color: var(--md-text-secondary); }
.fund-table-mini { width: auto; min-width: 320px; margin-bottom: 12px; font-size: 0.8125rem; }
.fund-table-mini th { padding: 8px 12px; }
.fund-table-mini td { padding: 8px 12px; }
.narrative-para { margin: 0 0 12px 0; line-height: 1.6; color: var(--md-text); }
.narrative-para:last-of-type { margin-bottom: 0; }
.guide-content { max-width: 720px; }
.guide-section { margin-bottom: 24px; }
.guide-section h3 { font-size: 1rem; font-weight: 500; color: var(--md-primary-dark); margin: 0 0 10px 0; padding-bottom: 6px; border-bottom: 1px solid var(--md-divider); }
.guide-section p { margin: 0 0 12px 0; line-height: 1.6; }
.guide-table { width: 100%; margin-top: 8px; margin-bottom: 16px; font-size: 0.875rem; }
.guide-table th { background: var(--md-primary-light); color: var(--md-text); }
@media (max-width: 600px) { .app-bar { padding: 12px 16px; } .main-content { padding: 16px; } .tab-btn { padding: 12px 14px; font-size: 0.75rem; } .tab-panel { padding: 16px; } }
.search-bar { width: 100%; max-width: 360px; padding: 8px 12px; border: 1px solid var(--md-divider); border-radius: var(--md-radius-sm); font-family: inherit; font-size: 0.875rem; color: var(--md-text); background: #fff; margin-bottom: 12px; outline: none; transition: border-color 0.2s; }
.search-bar:focus { border-color: var(--md-primary); box-shadow: 0 0 0 2px rgba(0,137,123,0.15); }
.pnl-pos { color: #16a34a; font-weight: 600; }
.pnl-neg { color: #dc2626; font-weight: 600; }
.summary-grid { display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 20px; }
.summary-card { background: var(--md-surface); border: 1px solid var(--md-divider); border-radius: var(--md-radius); padding: 14px 20px; min-width: 160px; box-shadow: var(--md-elevation-1); }
.summary-card .s-label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--md-text-secondary); margin-bottom: 4px; }
.summary-card .s-value { font-size: 1.25rem; font-weight: 500; }
.risk-label-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; margin-bottom: 0; }
.risk-label-table td { padding: 8px 12px; border-bottom: 1px solid var(--md-divider); }
.risk-label-table tr:last-child td { border-bottom: none; }
.risk-label-table td:first-child { color: var(--md-text-secondary); width: 55%; }
.risk-label-table td:last-child { font-weight: 500; }
.rec-badge { display:inline-block; padding:2px 9px; border-radius:12px; font-size:0.75rem; font-weight:600; letter-spacing:0.03em; white-space:nowrap; }
.rec-strong-add { background:#dcfce7; color:#15803d; }
.rec-add        { background:#d1fae5; color:#059669; }
.rec-hold       { background:#fef9c3; color:#854d0e; }
.rec-reduce     { background:#ffedd5; color:#c2410c; }
.rec-sell       { background:#fee2e2; color:#b91c1c; }
.rec-unknown    { background:#f1f5f9; color:#64748b; }
.score-bar { display:inline-flex; align-items:center; gap:6px; width:100%; }
.score-bar .sb-val { min-width:34px; font-size:0.8rem; font-weight:500; }
.score-bar .sb-track { flex:1; height:6px; background:#e2e8f0; border-radius:3px; }
.score-bar .sb-fill { height:100%; border-radius:3px; }
.change-pos { color:#16a34a; }
.change-neg { color:#dc2626; }
"""


def _read(path: Path, default: str = "") -> str:
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return default


def _load_json(path: Path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _df_to_md_table(df, max_rows: int = 50):
    if df is None or df.empty:
        return "*No data.*"
    import pandas as pd
    df = df.head(max_rows)
    cols = list(df.columns)
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep = "|" + "|".join(["---"] * len(cols)) + "|"
    lines = [header, sep]
    for _, row in df.iterrows():
        cells = [str(row.get(c, ""))[:80] for c in cols]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _df_to_html_table(df, table_id: str, class_name: str = "sortable", highlight_cols: list | None = None):
    """Build sortable table HTML; optional highlight top fraction of numeric cols."""
    if df is None or df.empty:
        return "<p>No data.</p>"
    import pandas as pd
    cols = list(df.columns)
    best_cells = set()
    if highlight_cols:
        for c in highlight_cols:
            if c not in df.columns:
                continue
            s = pd.to_numeric(df[c], errors="coerce").dropna()
            if s.empty or len(s) < 2:
                continue
            thresh = s.quantile(0.75)
            for pos, idx in enumerate(df.index):
                v = df.loc[idx, c]
                try:
                    if pd.notna(v) and float(v) >= thresh:
                        best_cells.add((pos, c))
                except (TypeError, ValueError):
                    pass
    html = [f'<table id="{table_id}" class="{class_name}"><thead><tr>']
    for c in cols:
        html.append(f'<th data-col="{html_module.escape(str(c))}">{c}</th>')
    html.append("</tr></thead><tbody>")
    for row_idx, (_, row) in enumerate(df.iterrows()):
        html.append("<tr>")
        for c in cols:
            v = row.get(c, "")
            if pd.isna(v):
                v = ""
            else:
                v = str(v)[:120]
            cls = " cell-best" if (row_idx, c) in best_cells else ""
            html.append(f'<td class="{cls.strip()}">{html_module.escape(v)}</td>')
        html.append("</tr>")
    html.append("</tbody></table>")
    return "\n".join(html)


def _markdown_para_to_html(para: str) -> str:
    if not para or not para.strip():
        return ""
    parts = para.split("**")
    out = []
    for i, p in enumerate(parts):
        if i % 2 == 1:
            out.append("<strong>" + html_module.escape(p) + "</strong>")
        else:
            sub = p.split("*")
            for j, sp in enumerate(sub):
                if j % 2 == 1:
                    out.append("<em>" + html_module.escape(sp) + "</em>")
                else:
                    out.append(html_module.escape(sp))
    return "".join(out)


def _narratives_to_html(narratives: list[dict], escape_fn) -> str:
    """Render narrative cards with fundamental breakdown and P&L/quarterly/BS/ratios (same structure as working-sector)."""
    if not narratives:
        return "<p>No narratives.</p>"
    fund_labels = {
        "fund_earnings_quality": "Earnings quality",
        "fund_sales_growth": "Sales growth",
        "fund_financial_strength": "Financial strength",
        "fund_institutional_backing": "Institutional backing",
    }
    out = []
    for n in narratives:
        sym = escape_fn(str(n.get("symbol", "")))
        out.append('<div class="narrative-card">')
        out.append(f'<h3 class="narrative-title">{sym}</h3>')
        # Fundamental (0–100) breakdown
        fund_parts = []
        for key, label in fund_labels.items():
            if n.get(key) is not None:
                try:
                    fund_parts.append(f"{label}: {float(n[key]):.1f}")
                except (TypeError, ValueError):
                    pass
        if fund_parts:
            out.append('<p class="narrative-fund-label"><em>Fundamental (0–100):</em> ' + " | ".join(fund_parts) + "</p>")
        elif n.get("fund_score") is not None:
            out.append(f'<p class="narrative-fund-label"><em>Fundamental score (0–100):</em> {float(n["fund_score"]):.1f}</p>')
        # P&L, Quarterly, Balance sheet, Ratios (when available)
        for key, label in [
            ("pnl_summary", "P&L"),
            ("quarterly_summary", "Quarterly"),
            ("balance_sheet_summary", "Balance sheet"),
            ("ratios_summary", "Ratios"),
        ]:
            if n.get(key) and str(n[key]).strip():
                out.append(f'<p class="narrative-fund-label"><em>{label}:</em> {escape_fn(str(n[key]).strip())}</p>')
        narrative = (n.get("narrative") or "").strip()
        if narrative:
            for para in narrative.split("\n\n"):
                para = para.strip()
                if para:
                    out.append(f'<p class="narrative-para">{_markdown_para_to_html(para)}</p>')
        if n.get("recommendation"):
            rec = escape_fn(str(n["recommendation"]))
            out.append(f'<p class="narrative-recommendation"><strong>Recommendation:</strong> {rec}</p>')
        out.append("</div>")
    return "\n".join(out)


def _guide_tab_html() -> str:
    return """
<div class="guide-content">
  <section class="guide-section">
    <h3>How to use this report</h3>
    <p>This report has eight tabs: <strong>Overview</strong> (portfolio summary and PnL), <strong>How to read</strong> (this guide), <strong>Risk &amp; scenarios</strong>, <strong>Market sentiment</strong>, <strong>Sector assessment</strong>, <strong>Technical</strong> (per-stock table), <strong>Fundamental</strong> (per-stock scores), and <strong>Stock narratives</strong>. Use the tabs to switch views.</p>
    <p><strong>Tables:</strong> In Technical and Fundamental, click any column header to sort; click again to toggle ascending (▲) / descending (▼). Green-highlighted cells mark the top 25% of values in that column.</p>
  </section>
  <section class="guide-section">
    <h3>Risk metrics</h3>
    <table class="guide-table">
      <thead><tr><th>Metric</th><th>Description</th></tr></thead>
      <tbody>
        <tr><td><strong>VaR (95%, 1-day)</strong></td><td>Value at Risk: loss level not exceeded with 95% probability over one day.</td></tr>
        <tr><td><strong>CVaR / Expected Shortfall</strong></td><td>Average loss beyond VaR (tail risk).</td></tr>
        <tr><td><strong>Sharpe ratio</strong></td><td>(Portfolio return − risk-free rate) / volatility; higher = better risk-adjusted return.</td></tr>
        <tr><td><strong>Beta</strong></td><td>Sensitivity to Nifty; 1 = moves with market.</td></tr>
        <tr><td><strong>Max drawdown</strong></td><td>Peak-to-trough decline (%).</td></tr>
        <tr><td><strong>Concentration (Herfindahl)</strong></td><td>Higher = more concentrated; lower = more diversified.</td></tr>
      </tbody>
    </table>
  </section>
  <section class="guide-section">
    <h3>Scenarios</h3>
    <p>Scenario projections apply assumed index returns to the portfolio (e.g. Nifty +10%, −15%). Results depend on portfolio beta and composition. Use for stress testing and rebalancing context.</p>
  </section>
  <section class="guide-section">
    <h3>Fundamental scores</h3>
    <p>Scores are 0–100 (higher = better). They combine earnings quality, sales growth, financial strength, and institutional backing from the Screener/organized pipeline.</p>
  </section>
  <section class="guide-section">
    <h3>Stock narratives</h3>
    <p>Per-stock narrative combines holdings (qty, value), fundamental score, market sentiment snippets, and a recommendation (HOLD/ADD/REDUCE/SELL). For research context only, not investment advice.</p>
  </section>
</div>
"""


def _fmt_inr(v, decimals: int = 2) -> str:
    try:
        f = float(v)
        sign = "+" if f > 0 else ""
        return f"{sign}₹{f:,.{decimals}f}"
    except (TypeError, ValueError):
        return "—"


def _pnl_class(v) -> str:
    try:
        return "pnl-pos" if float(v) > 0 else "pnl-neg"
    except (TypeError, ValueError):
        return ""


def _rec_badge(rec: str) -> str:
    """Return an HTML badge for a recommendation string."""
    cls_map = {
        "STRONG ADD": "rec-strong-add",
        "ADD": "rec-add",
        "HOLD": "rec-hold",
        "REDUCE": "rec-reduce",
        "SELL": "rec-sell",
    }
    cls = cls_map.get(str(rec).upper().strip(), "rec-unknown")
    return f'<span class="rec-badge {cls}">{html_module.escape(str(rec))}</span>'


def _score_bar(score, max_val: float = 100) -> str:
    """Return a mini progress-bar cell for a 0–100 score."""
    try:
        v = float(score)
        pct = int(v / max_val * 100)
        if v >= 65:
            colour = "#16a34a"
        elif v >= 45:
            colour = "#f59e0b"
        else:
            colour = "#dc2626"
        return (
            f'<div class="score-bar">'
            f'<span class="sb-val">{v:.0f}</span>'
            f'<div class="sb-track"><div class="sb-fill" style="width:{pct}%;background:{colour}"></div></div>'
            f'</div>'
        )
    except (TypeError, ValueError):
        return "—"


def _chg_cell(v) -> str:
    try:
        f = float(v)
        cls = "change-pos" if f >= 0 else "change-neg"
        sign = "+" if f >= 0 else ""
        return f'<span class="{cls}">{sign}{f:.1f}%</span>'
    except (TypeError, ValueError):
        return "—"


def _build_holdings_tab() -> str:
    """Merged holdings: holdings + technical (real scores) + fundamental + risk + realized PnL."""
    import pandas as pd

    try:
        hold = pd.read_csv(HOLDINGS_CSV) if HOLDINGS_CSV.exists() else pd.DataFrame()
    except Exception:
        hold = pd.DataFrame()
    try:
        tech = pd.read_csv(TECHNICAL_BY_STOCK_CSV) if TECHNICAL_BY_STOCK_CSV.exists() else pd.DataFrame()
    except Exception:
        tech = pd.DataFrame()
    try:
        fund = pd.read_csv(FUNDAMENTAL_BY_STOCK_CSV) if FUNDAMENTAL_BY_STOCK_CSV.exists() else pd.DataFrame()
    except Exception:
        fund = pd.DataFrame()
    try:
        risk_s = pd.read_csv(RISK_METRICS_CSV) if RISK_METRICS_CSV.exists() else pd.DataFrame()
    except Exception:
        risk_s = pd.DataFrame()
    try:
        pnl_agg = pd.read_csv(PNL_AGGREGATES_CSV) if PNL_AGGREGATES_CSV.exists() else pd.DataFrame()
    except Exception:
        pnl_agg = pd.DataFrame()

    if hold.empty:
        return "<p>No holdings data. Ensure holdings.csv exists in output/.</p>"

    # Aggregate per-symbol PnL
    sym_pnl: dict = {}
    if not pnl_agg.empty and "symbol" in pnl_agg.columns and "pnl" in pnl_agg.columns:
        for sym, grp in pnl_agg.groupby("symbol"):
            sym_pnl[str(sym)] = float(grp["pnl"].sum())

    # Merge tech (rich columns — now includes enhanced_fund_score from comprehensive CSV)
    df = hold.copy()
    df["symbol"] = df["symbol"].astype(str)
    tech_cols = ["symbol", "current_price", "technical_score", "rsi", "recommendation",
                 "trend_signal", "change_1d_pct", "change_1w_pct", "change_1m_pct",
                 "relative_strength", "enhanced_fund_score"]
    if not tech.empty and "symbol" in tech.columns:
        tc = tech[[c for c in tech_cols if c in tech.columns]].copy()
        df = df.merge(tc, on="symbol", how="left")

    # Merge fund — only fill fund_score where not already provided by tech CSV
    if not fund.empty:
        fund2 = fund.copy()
        if "SYMBOL" in fund2.columns and "symbol" in fund2.columns:
            fund2 = fund2.drop(columns=["SYMBOL"])
        elif "SYMBOL" in fund2.columns:
            fund2 = fund2.rename(columns={"SYMBOL": "symbol"})
        keep = [c for c in ["symbol", "ENHANCED_FUND_SCORE"] if c in fund2.columns]
        if keep:
            f2 = fund2[keep].rename(columns={"ENHANCED_FUND_SCORE": "fund_score_fb"})
            df = df.merge(f2, on="symbol", how="left")
            # Prefer comprehensive CSV score; fall back to fundamental_by_stock.csv
            if "enhanced_fund_score" in df.columns:
                df["fund_score"] = df["enhanced_fund_score"].combine_first(df.get("fund_score_fb", pd.Series(dtype=float)))
            else:
                df["fund_score"] = df.get("fund_score_fb", pd.Series(dtype=float))
            df = df.drop(columns=["fund_score_fb"], errors="ignore")
    elif "enhanced_fund_score" in df.columns:
        df["fund_score"] = df["enhanced_fund_score"]

    # Merge per-stock volatility
    if not risk_s.empty and "symbol" in risk_s.columns and "volatility_annual_pct" in risk_s.columns:
        df = df.merge(risk_s[["symbol", "volatility_annual_pct"]], on="symbol", how="left")

    df["realized_pnl"] = df["symbol"].map(sym_pnl)

    # Composite decision (tech + fund)
    def _decision(row) -> str:
        ts = float(row.get("technical_score") or 50)
        fs = float(row.get("fund_score") or 50)
        combined = ts * 0.6 + fs * 0.4
        if combined >= 70:
            return "STRONG ADD"
        elif combined >= 58:
            return "ADD"
        elif combined >= 42:
            return "HOLD"
        elif combined >= 28:
            return "REDUCE"
        else:
            return "SELL"

    df["Decision"] = df.apply(_decision, axis=1)

    # Sort by value descending
    df = df.sort_values("value_rs", ascending=False)

    # Build filter tabs (decision counts)
    dec_counts = df["Decision"].value_counts()
    filter_btns = '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;align-items:center">'
    filter_btns += '<span style="font-size:0.8rem;color:var(--md-text-secondary);margin-right:4px">Filter:</span>'
    filter_btns += '<button class="rec-badge rec-unknown" onclick="filterTable(\'table-holdings\',\'\')" style="cursor:pointer;border:none">All</button>'
    for rec in ["STRONG ADD", "ADD", "HOLD", "REDUCE", "SELL"]:
        n = dec_counts.get(rec, 0)
        if n > 0:
            cls_map = {"STRONG ADD": "rec-strong-add", "ADD": "rec-add", "HOLD": "rec-hold",
                       "REDUCE": "rec-reduce", "SELL": "rec-sell"}
            cls = cls_map[rec]
            filter_btns += f'<button class="rec-badge {cls}" onclick="filterTable(\'table-holdings\',\'{rec}\')" style="cursor:pointer;border:none">{rec} ({n})</button>'
    filter_btns += '</div>'

    # Build HTML table manually for rich cells
    headers = ["Symbol", "Qty", "Value (₹)", "Price", "Tech Score", "RSI",
               "1M %", "Fund Score", "Volatility %", "Decision", "Tech Signal", "Realized PnL"]
    tbl = ['<table id="table-holdings" class="sortable"><thead><tr>']
    for h in headers:
        tbl.append(f'<th>{h}</th>')
    tbl.append("</tr></thead><tbody>")

    for _, row in df.iterrows():
        tbl.append("<tr>")
        # Symbol
        tbl.append(f'<td><strong>{html_module.escape(str(row.get("symbol", "")))}</strong></td>')
        # Qty
        qty = row.get("quantity", "")
        tbl.append(f'<td>{html_module.escape(str(qty) if pd.notna(qty) else "—")}</td>')
        # Value
        val = row.get("value_rs")
        tbl.append(f'<td>{"₹{:,.0f}".format(float(val)) if pd.notna(val) else "—"}</td>')
        # Price
        price = row.get("current_price")
        tbl.append(f'<td>{"₹{:,.2f}".format(float(price)) if pd.notna(price) else "—"}</td>')
        # Tech Score (bar)
        tbl.append(f'<td>{_score_bar(row.get("technical_score"))}</td>')
        # RSI
        rsi = row.get("rsi")
        tbl.append(f'<td>{f"{float(rsi):.1f}" if pd.notna(rsi) else "—"}</td>')
        # 1M %
        tbl.append(f'<td>{_chg_cell(row.get("change_1m_pct"))}</td>')
        # Fund Score (bar)
        tbl.append(f'<td>{_score_bar(row.get("fund_score"))}</td>')
        # Volatility
        vol = row.get("volatility_annual_pct")
        tbl.append(f'<td>{"{}%".format(float(vol)) if pd.notna(vol) else "—"}</td>')
        # Decision badge
        dec = str(row.get("Decision", "HOLD"))
        tbl.append(f'<td>{_rec_badge(dec)}</td>')
        # Trend signal
        trend = str(row.get("trend_signal", "") or "")
        tbl.append(f'<td><span style="font-size:0.75rem">{html_module.escape(trend)}</span></td>')
        # Realized PnL
        rpnl = row.get("realized_pnl")
        if pd.notna(rpnl):
            cls = _pnl_class(rpnl)
            tbl.append(f'<td class="{cls}">{_fmt_inr(rpnl)}</td>')
        else:
            tbl.append("<td>—</td>")
        tbl.append("</tr>")
    tbl.append("</tbody></table>")

    return (
        filter_btns
        + f'<input class="search-bar" type="search" placeholder="Search symbol, signal…" '
        f'oninput="filterTable(\'table-holdings\',this.value)">'
        + '<div class="table-scroll">' + "\n".join(tbl) + "</div>"
    )


def _build_pnl_tab() -> str:
    """P&L analysis: summary cards + per-symbol totals + full closed-trade table."""
    import pandas as pd

    try:
        pnl_agg = pd.read_csv(PNL_AGGREGATES_CSV) if PNL_AGGREGATES_CSV.exists() else pd.DataFrame()
    except Exception:
        pnl_agg = pd.DataFrame()
    try:
        closed = pd.read_csv(CLOSED_PNL_CSV) if CLOSED_PNL_CSV.exists() else pd.DataFrame()
    except Exception:
        closed = pd.DataFrame()

    summary = _load_json(PORTFOLIO_SUMMARY_JSON)

    # Summary cards
    total_pnl = summary.get("total_realized_pnl", 0)
    tenure = summary.get("pnl_by_tenure", {})
    ltcg = tenure.get("LTCG", 0)
    stcg = tenure.get("STCG", 0)
    intra = tenure.get("intraday", 0)

    def card(label: str, value: float) -> str:
        cls = _pnl_class(value)
        return (
            f'<div class="summary-card"><div class="s-label">{label}</div>'
            f'<div class="s-value {cls}">{_fmt_inr(value)}</div></div>'
        )

    cards_html = (
        '<div class="summary-grid">'
        + card("Total Realized PnL", total_pnl)
        + card("LTCG", ltcg)
        + card("STCG", stcg)
        + card("Intraday", intra)
        + "</div>"
    )

    # Per-symbol totals table
    sym_html = "<p>No aggregated PnL data.</p>"
    if not pnl_agg.empty and "symbol" in pnl_agg.columns:
        sym_tot = (
            pnl_agg.groupby("symbol")["pnl"]
            .sum()
            .reset_index()
            .rename(columns={"symbol": "Symbol", "pnl": "Realized PnL"})
            .sort_values("Realized PnL")
        )
        sym_tot["Realized PnL (₹)"] = sym_tot["Realized PnL"].apply(_fmt_inr)
        tbl = ['<table id="table-pnl-sym" class="sortable"><thead><tr>']
        for c in ["Symbol", "Realized PnL (₹)"]:
            tbl.append(f'<th>{c}</th>')
        tbl.append("</tr></thead><tbody>")
        for _, r in sym_tot.iterrows():
            fv = float(r["Realized PnL"])
            cls = _pnl_class(fv)
            tbl.append(f'<tr><td>{html_module.escape(str(r["Symbol"]))}</td>'
                       f'<td class="{cls}">{html_module.escape(r["Realized PnL (₹)"])}</td></tr>')
        tbl.append("</tbody></table>")
        sym_html = (
            f'<input class="search-bar" type="search" placeholder="Filter symbols…" '
            f'oninput="filterTable(\'table-pnl-sym\',this.value)">'
            + '<div class="table-scroll">' + "\n".join(tbl) + "</div>"
        )

    # Full closed trades table
    closed_html = "<p>No closed trade data.</p>"
    if not closed.empty:
        disp_cols = [c for c in ["symbol", "qty", "purchase_date", "purchase_rate",
                                  "sale_date", "sale_rate", "pnl", "tenure_bucket"]
                     if c in closed.columns]
        disp = closed[disp_cols].copy()
        disp = disp.sort_values("pnl") if "pnl" in disp.columns else disp
        tbl2 = ['<table id="table-closed-pnl" class="sortable"><thead><tr>']
        pretty = {"symbol": "Symbol", "qty": "Qty", "purchase_date": "Buy Date",
                  "purchase_rate": "Buy Rate", "sale_date": "Sell Date",
                  "sale_rate": "Sell Rate", "pnl": "PnL (₹)", "tenure_bucket": "Bucket"}
        for c in disp_cols:
            tbl2.append(f'<th>{pretty.get(c, c)}</th>')
        tbl2.append("</tr></thead><tbody>")
        for _, r in disp.iterrows():
            tbl2.append("<tr>")
            for c in disp_cols:
                v = r.get(c, "")
                v_str = "" if pd.isna(v) else str(v)
                if c == "pnl":
                    try:
                        fv = float(v_str)
                        cls = _pnl_class(fv)
                        tbl2.append(f'<td class="{cls}">{_fmt_inr(fv)}</td>')
                        continue
                    except (TypeError, ValueError):
                        pass
                tbl2.append(f'<td>{html_module.escape(v_str)}</td>')
            tbl2.append("</tr>")
        tbl2.append("</tbody></table>")
        closed_html = (
            f'<input class="search-bar" type="search" placeholder="Filter closed trades…" '
            f'oninput="filterTable(\'table-closed-pnl\',this.value)">'
            + '<div class="table-scroll">' + "\n".join(tbl2) + "</div>"
        )

    return (
        cards_html
        + '<div class="card-section"><h3 class="card-title">Realized PnL by symbol</h3>' + sym_html + "</div>"
        + '<div class="card-section" style="margin-top:16px"><h3 class="card-title">All closed trades</h3>' + closed_html + "</div>"
    )


def _build_risk_tab() -> str:
    """Risk metrics with human-readable labels + per-stock volatility + scenario projections table."""
    import pandas as pd

    risk = _load_json(RISK_METRICS_JSON)

    LABELS = {
        "portfolio_volatility_annual_pct": ("Portfolio volatility (annual)", "%"),
        "var_95_1d_pct": ("VaR 95% (1-day)", "%"),
        "cvar_95_1d_pct": ("CVaR / Expected Shortfall (1-day)", "%"),
        "sharpe_ratio": ("Sharpe ratio", ""),
        "beta_nifty": ("Beta vs Nifty", ""),
        "max_drawdown_pct": ("Max drawdown", "%"),
        "concentration_herfindahl": ("Concentration (Herfindahl)", ""),
        "risk_free_rate_annual": ("Risk-free rate (annual)", "%"),
        "n_constituents": ("Holdings count", ""),
    }

    risk_rows = ""
    for k, (label, unit) in LABELS.items():
        v = risk.get(k)
        if v is None:
            # try CSV fallback
            try:
                port_csv = pd.read_csv(RISK_METRICS_PORTFOLIO_CSV) if RISK_METRICS_PORTFOLIO_CSV.exists() else pd.DataFrame()
                if not port_csv.empty and k in port_csv.columns:
                    v = port_csv[k].iloc[0]
            except Exception:
                pass
        if v is None or (isinstance(v, float) and pd.isna(v)):
            display = "—"
        else:
            try:
                fv = float(v)
                display = f"{fv:.4f}{unit}" if abs(fv) < 0.01 and unit == "" else f"{fv:.2f}{unit}"
            except (TypeError, ValueError):
                display = str(v) + unit
        risk_rows += f'<tr><td>{html_module.escape(label)}</td><td>{html_module.escape(display)}</td></tr>'

    risk_metrics_html = (
        '<div class="card-section"><h3 class="card-title">Portfolio risk metrics</h3>'
        '<table class="risk-label-table"><tbody>' + risk_rows + '</tbody></table></div>'
    )

    # Per-stock volatility table
    vol_html = ""
    try:
        risk_s = pd.read_csv(RISK_METRICS_CSV) if RISK_METRICS_CSV.exists() else pd.DataFrame()
        if not risk_s.empty:
            risk_s = risk_s.sort_values("volatility_annual_pct", ascending=False)
            risk_s.columns = [c.replace("symbol", "Symbol").replace("weight_pct", "Weight %")
                               .replace("volatility_annual_pct", "Volatility % (ann)") for c in risk_s.columns]
            hcols = [c for c in ["Volatility % (ann)"] if c in risk_s.columns]
            vol_html = (
                '<div class="card-section" style="margin-top:16px"><h3 class="card-title">Per-stock volatility</h3>'
                f'<input class="search-bar" type="search" placeholder="Filter symbols…" '
                f'oninput="filterTable(\'table-risk-stock\',this.value)">'
                '<div class="table-scroll">'
                + _df_to_html_table(risk_s, "table-risk-stock", highlight_cols=hcols)
                + '</div></div>'
            )
    except Exception:
        pass

    # Scenario projections table
    scen_html = ""
    try:
        scen = pd.read_csv(SCENARIO_PROJECTIONS_CSV) if SCENARIO_PROJECTIONS_CSV.exists() else pd.DataFrame()
        if not scen.empty:
            disp = scen.rename(columns={
                "scenario_name": "Scenario",
                "index_return_pct": "Index Return %",
                "portfolio_projected_return_pct": "Portfolio Return %",
                "description": "Description",
            })
            keep = [c for c in ["Scenario", "Index Return %", "Portfolio Return %", "Description"] if c in disp.columns]
            disp = disp[keep]

            tbl = ['<table id="table-scenarios" class="sortable"><thead><tr>']
            for c in disp.columns:
                tbl.append(f'<th>{html_module.escape(str(c))}</th>')
            tbl.append("</tr></thead><tbody>")
            for _, r in disp.iterrows():
                tbl.append("<tr>")
                for c in disp.columns:
                    v = r.get(c, "")
                    if pd.isna(v):
                        v = ""
                    v_str = str(v)
                    if c in ("Index Return %", "Portfolio Return %"):
                        try:
                            fv = float(v_str)
                            cls = "pnl-pos" if fv > 0 else ("pnl-neg" if fv < 0 else "")
                            tbl.append(f'<td class="{cls}">{fv:+.1f}%</td>')
                            continue
                        except (TypeError, ValueError):
                            pass
                    tbl.append(f'<td>{html_module.escape(v_str)}</td>')
                tbl.append("</tr>")
            tbl.append("</tbody></table>")

            scen_html = (
                '<div class="card-section" style="margin-top:16px"><h3 class="card-title">Scenario projections</h3>'
                '<div class="table-scroll">' + "\n".join(tbl) + '</div></div>'
            )
    except Exception:
        pass

    scenario_md = _read(SCENARIO_NARRATIVE_MD) or ""
    scenario_json = json.dumps(scenario_md, ensure_ascii=False).replace("</script>", "<\\/script>")
    scen_narrative_html = (
        f'<div class="card-section" style="margin-top:16px">'
        f'<h3 class="card-title">Scenario narrative</h3>'
        f'<div id="risk-scenario-md" class="md-rendered"></div></div>'
        f'<script type="application/json" id="scenario-md">{scenario_json}</script>'
    )

    return risk_metrics_html + vol_html + scen_html + scen_narrative_html


def build_report_md() -> str:
    """Build full markdown report from all phase outputs."""
    summary = _load_json(PORTFOLIO_SUMMARY_JSON)
    account = summary.get("account_name", "Portfolio")
    data_as_of = summary.get("data_as_of", "")
    today = date.today().isoformat()

    sections = [
        "# Portfolio comprehensive report",
        "",
        f"**Report date:** {today}  |  **Account:** {account}  |  **Data as of:** {data_as_of}",
        "",
        "---",
        "",
        "## 1. Portfolio summary",
        "",
    ]
    if summary:
        sections.append(f"- **Holdings:** {summary.get('holdings_count', 0)} positions (source: {summary.get('holdings_source', 'N/A')})")
        sections.append(f"- **Closed trades:** {summary.get('closed_trades_count', 0)}")
        sections.append(f"- **Total realized PnL:** Rs {summary.get('total_realized_pnl', 0):,.2f}")
        sections.append(f"- **PnL by tenure:** {summary.get('pnl_by_tenure', {})}")
        sections.append("")
    sections.append("---")
    sections.append("")
    sections.append("## 2. PnL summary")
    sections.append("")
    sections.append(_read(PNL_SUMMARY_MD) or "*Run Phase 1 for PnL summary.*")
    sections.append("")
    sections.append("---")
    sections.append("")
    sections.append("## 3. Risk & scenarios")
    sections.append("")
    risk = _load_json(RISK_METRICS_JSON)
    if risk:
        for k, v in risk.items():
            if k in ("portfolio_volatility_annual_pct", "var_95_1d_pct", "sharpe_ratio", "beta_nifty", "max_drawdown_pct"):
                sections.append(f"- **{k}:** {v}")
        sections.append("")
    sections.append(_read(SCENARIO_NARRATIVE_MD) or "*Scenario narrative (Phase 7).*")
    sections.append("")
    sections.append("---")
    sections.append("")
    sections.append("## 4. Market sentiment")
    sections.append("")
    sections.append(_read(MARKET_SENTIMENT_MD) or "*Run market sentiment for sector/stock research.*")
    sections.append("")
    sections.append("---")
    sections.append("")
    sections.append("## 5. Sector assessment")
    sections.append("")
    sections.append(_read(SECTOR_ASSESSMENT_MD) or "*Run Phase 2 for sector view.*")
    sections.append("")
    sections.append("---")
    sections.append("")
    sections.append("## 6. Technical summary")
    sections.append("")
    sections.append(_read(TECHNICAL_SUMMARY_MD) or "*Run Phase 3 for technical view.*")
    if TECHNICAL_BY_STOCK_CSV.exists():
        import pandas as pd
        tech_df = pd.read_csv(TECHNICAL_BY_STOCK_CSV)
        sections.append("")
        sections.append(_df_to_md_table(tech_df.head(30)))
    sections.append("")
    sections.append("---")
    sections.append("")
    sections.append("## 7. Fundamental summary (by stock)")
    sections.append("")
    if FUNDAMENTAL_BY_STOCK_CSV.exists():
        import pandas as pd
        fund_df = pd.read_csv(FUNDAMENTAL_BY_STOCK_CSV)
        sections.append(_df_to_md_table(fund_df.head(50)))
    else:
        sections.append("*Run Phase 4 for fundamental scores.*")
    sections.append("")
    sections.append("---")
    sections.append("")
    sections.append("## 8. Stock narratives")
    sections.append("")
    sections.append(_read(STOCK_NARRATIVES_MD) or "*Run Phase 5 for per-stock narratives.*")
    sections.append("")
    sections.append("---")
    sections.append("")
    sections.append("## 9. Appendix")
    sections.append("")
    sections.append(f"- **Generated:** {today}. Phases 0–7 + market sentiment. Outputs in `{OUTPUT_DIR}`.")
    sections.append("- **Sources:** NSE data, CAS PDF, PnL CSV, fundamental_scores_database, web search (DDGS + SERP) for sentiment.")
    return "\n".join(sections)


def build_report_html_structured() -> str:
    """Build HTML report with same CSS and tabbed layout as working-sector comprehensive report."""
    import pandas as pd

    summary = _load_json(PORTFOLIO_SUMMARY_JSON)
    account = summary.get("account_name", "Portfolio")
    data_as_of = summary.get("data_as_of", "")
    today = date.today().isoformat()

    def escape(s: str) -> str:
        if not s:
            return ""
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    # Tab: Overview — summary cards + PnL snippet
    total_pnl = summary.get("total_realized_pnl", 0)
    tenure = summary.get("pnl_by_tenure", {})

    def ov_card(label: str, value: object, unit: str = "") -> str:
        cls = ""
        try:
            fv = float(value)
            if unit == "₹":
                display = f"{'+'if fv>0 else ''}₹{fv:,.2f}"
                cls = "pnl-pos" if fv > 0 else "pnl-neg"
            else:
                display = f"{fv}{unit}"
        except (TypeError, ValueError):
            display = str(value) + unit
        return (
            f'<div class="summary-card"><div class="s-label">{html_module.escape(label)}</div>'
            f'<div class="s-value {cls}">{html_module.escape(display)}</div></div>'
        )

    pnl_summary_md = _read(PNL_SUMMARY_MD) or "*Run Phase 1 for PnL summary.*"
    pnl_summary_json = json.dumps(pnl_summary_md, ensure_ascii=False).replace("</script>", "<\\/script>")
    overview_html = (
        '<div class="summary-grid">'
        + ov_card("Holdings", summary.get("holdings_count", "—"))
        + ov_card("Closed trades", summary.get("closed_trades_count", "—"))
        + ov_card("Total realized PnL", total_pnl, "₹")
        + ov_card("LTCG", tenure.get("LTCG", 0), "₹")
        + ov_card("STCG", tenure.get("STCG", 0), "₹")
        + ov_card("Intraday", tenure.get("intraday", 0), "₹")
        + "</div>"
        + '<div class="card-section"><h3 class="card-title">PnL summary</h3>'
        + '<div id="overview-pnl-md" class="md-rendered"></div></div>'
        + f'<script type="application/json" id="overview-pnl-json">{pnl_summary_json}</script>'
    )

    # Tab: Holdings (new comprehensive merged table)
    holdings_html = _build_holdings_tab()

    # Tab: P&L analysis (new)
    pnl_html = _build_pnl_tab()

    # Tab: Risk & scenarios (enhanced)
    risk_html = _build_risk_tab()

    # Tab: Market sentiment (markdown in card)
    sentiment_md = _read(MARKET_SENTIMENT_MD) or ""
    sentiment_json = json.dumps(sentiment_md, ensure_ascii=False).replace("</script>", "<\\/script>")
    sentiment_html = (
        f"<div class='card-section'><h3 class='card-title'>Market sentiment</h3>"
        f"<div id='sentiment-md' class='md-rendered'></div></div>"
        f"<script type='application/json' id='sentiment-md-json'>{sentiment_json}</script>"
    )

    # Tab: Sector assessment
    sector_md = _read(SECTOR_ASSESSMENT_MD) or ""
    sector_json = json.dumps(sector_md, ensure_ascii=False).replace("</script>", "<\\/script>")
    sector_html = (
        f"<div class='card-section'><h3 class='card-title'>Sector assessment</h3>"
        f"<div id='sector-md' class='md-rendered'></div></div>"
        f"<script type='application/json' id='sector-md-json'>{sector_json}</script>"
    )

    # Tab: Technical table
    try:
        tech_df = pd.read_csv(TECHNICAL_BY_STOCK_CSV) if TECHNICAL_BY_STOCK_CSV.exists() else pd.DataFrame()
    except Exception:
        tech_df = pd.DataFrame()
    if tech_df.empty:
        technical_html = "<p>No technical data. Run Phase 3.</p>"
    else:
        hcols = [c for c in ["value_rs", "technical_score"] if c in tech_df.columns]
        technical_html = (
            f'<input class="search-bar" type="search" placeholder="Filter symbols…" '
            f'oninput="filterTable(\'table-technical\',this.value)">'
            + '<div class="table-scroll">'
            + _df_to_html_table(tech_df, "table-technical", highlight_cols=hcols or None)
            + "</div>"
        )

    # Tab: Fundamental table
    try:
        fund_df = pd.read_csv(FUNDAMENTAL_BY_STOCK_CSV) if FUNDAMENTAL_BY_STOCK_CSV.exists() else pd.DataFrame()
        # Drop duplicate uppercase SYMBOL column if both exist
        if not fund_df.empty and "symbol" in fund_df.columns and "SYMBOL" in fund_df.columns:
            fund_df = fund_df.drop(columns=["SYMBOL"])
    except Exception:
        fund_df = pd.DataFrame()
    if fund_df.empty:
        fundamental_html = "<p>No fundamental data. Run Phase 4.</p>"
    else:
        hcols = [c for c in ["ENHANCED_FUND_SCORE", "EARNINGS_QUALITY", "FINANCIAL_STRENGTH"] if c in fund_df.columns]
        fundamental_html = (
            f'<input class="search-bar" type="search" placeholder="Filter symbols…" '
            f'oninput="filterTable(\'table-fundamental\',this.value)">'
            + '<div class="table-scroll">'
            + _df_to_html_table(fund_df, "table-fundamental", highlight_cols=hcols or None)
            + "</div>"
        )

    # Tab: Stock narratives
    narratives = _load_json(STOCK_NARRATIVES_JSON)
    if not isinstance(narratives, list):
        narratives = []
    narratives_html = _narratives_to_html(narratives, escape)

    # Tab: Guide (updated text to reflect new tabs)
    guide_html = _guide_tab_html()

    tabs = [
        ("overview", "Overview", overview_html),
        ("holdings", "Holdings", holdings_html),
        ("pnl", "P&amp;L", pnl_html),
        ("risk", "Risk &amp; scenarios", risk_html),
        ("guide", "How to read", guide_html),
        ("sentiment", "Market sentiment", sentiment_html),
        ("sector", "Sector assessment", sector_html),
        ("technical", "Technical", technical_html),
        ("fundamental", "Fundamental", fundamental_html),
        ("narratives", "Stock narratives", narratives_html),
    ]
    tab_buttons = "".join(f'<button class="tab-btn" data-tab="{tid}">{label}</button>' for tid, label, _ in tabs)
    tab_panels = "".join(f'<div id="panel-{tid}" class="tab-panel" role="tabpanel">{content}</div>' for tid, _, content in tabs)

    sortable_ids = [
        "table-holdings", "table-pnl-sym", "table-closed-pnl",
        "table-scenarios", "table-risk-stock",
        "table-technical", "table-fundamental",
    ]
    sortable_js = "[" + ",".join(f"'{t}'" for t in sortable_ids) + "].forEach(sortTable);"

    script = f"""
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script>
(function() {{
  function renderMd(elId, jsonId) {{
    var j = document.getElementById(jsonId);
    var d = document.getElementById(elId);
    if (!j || !d) return;
    try {{
      var md = JSON.parse(j.textContent);
      if (typeof marked !== 'undefined' && marked.parse) d.innerHTML = marked.parse(md);
      else {{ d.textContent = md; d.classList.add('md-fallback'); }}
    }} catch (e) {{}}
  }}
  function initMd() {{
    renderMd('overview-pnl-md', 'overview-pnl-json');
    renderMd('risk-scenario-md', 'scenario-md');
    renderMd('sentiment-md', 'sentiment-md-json');
    renderMd('sector-md', 'sector-md-json');
  }}
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initMd);
  else initMd();

  var panels = document.querySelectorAll('.tab-panel');
  var buttons = document.querySelectorAll('.tab-btn');
  function show(id) {{
    panels.forEach(function(p) {{ p.classList.remove('active'); }});
    buttons.forEach(function(b) {{ b.classList.remove('active'); }});
    var p = document.getElementById('panel-' + id);
    var b = document.querySelector('[data-tab="' + id + '"]');
    if (p) p.classList.add('active');
    if (b) b.classList.add('active');
  }}
  buttons.forEach(function(b) {{
    b.addEventListener('click', function() {{ show(b.getAttribute('data-tab')); }});
  }});
  if (buttons.length) show(buttons[0].getAttribute('data-tab'));

  function parseCellNum(txt) {{
    if (!txt) return NaN;
    // Strip ₹, +, %, commas
    var s = String(txt).replace(/[₹%,+]/g, '').trim();
    var n = parseFloat(s);
    return isNaN(n) ? NaN : n;
  }}
  function sortTable(tableId) {{
    var table = document.getElementById(tableId);
    if (!table) return;
    var headers = table.querySelectorAll('thead th');
    var body = table.querySelector('tbody');
    var sortState = {{ colIndex: -1, asc: true }};
    headers.forEach(function(th, colIndex) {{
      th.addEventListener('click', function() {{
        var rows = Array.from(body.querySelectorAll('tr'));
        if (!rows.length) return;
        var asc = (sortState.colIndex === colIndex) ? !sortState.asc : true;
        sortState.colIndex = colIndex;
        sortState.asc = asc;
        headers.forEach(function(h, i) {{
          h.classList.remove('sort-asc', 'sort-desc');
          if (i === colIndex) h.classList.add(asc ? 'sort-asc' : 'sort-desc');
        }});
        var cellVal = function(row, ci) {{ var c = row.cells[ci]; return c ? c.textContent.trim() : ''; }};
        var isNum = false;
        for (var r = 0; r < rows.length; r++) {{
          var n = parseCellNum(cellVal(rows[r], colIndex));
          if (!isNaN(n)) {{ isNum = true; break; }}
        }}
        rows.sort(function(a, b) {{
          var va = cellVal(a, colIndex);
          var vb = cellVal(b, colIndex);
          if (isNum) {{
            var na = parseCellNum(va);
            var nb = parseCellNum(vb);
            if (isNaN(na)) na = -Infinity;
            if (isNaN(nb)) nb = -Infinity;
            return asc ? na - nb : nb - na;
          }}
          return asc ? (va < vb ? -1 : va > vb ? 1 : 0) : (vb < va ? -1 : vb > va ? 1 : 0);
        }});
        rows.forEach(function(r) {{ body.appendChild(r); }});
      }});
    }});
  }}
  {sortable_js}

  window.filterTable = function(tableId, query) {{
    var table = document.getElementById(tableId);
    if (!table) return;
    var q = query.toLowerCase();
    var rows = table.querySelectorAll('tbody tr');
    rows.forEach(function(row) {{
      var text = row.textContent.toLowerCase();
      row.style.display = (!q || text.indexOf(q) !== -1) ? '' : 'none';
    }});
  }};
}})();
</script>
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Portfolio – Comprehensive Report</title>
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap" rel="stylesheet">
<style>
{REPORT_CSS}
</style>
</head>
<body>
<header class="app-bar">
  <h1>Portfolio – Comprehensive Report</h1>
  <p class="meta">Report date: {today} &nbsp;·&nbsp; Account: {html_module.escape(account)} &nbsp;·&nbsp; Data as of: {data_as_of}</p>
</header>
<main class="main-content">
  <div class="tabs" role="tablist">{tab_buttons}</div>
  {tab_panels}
</main>
{script}
</body>
</html>"""


def run_phase6() -> dict:
    """Run Phase 6: build comprehensive report (MD + HTML)."""
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    md_content = build_report_md()
    REPORT_MD.write_text(md_content, encoding="utf-8")
    html_content = build_report_html_structured()
    REPORT_HTML.write_text(html_content, encoding="utf-8")
    return {"report_md": str(REPORT_MD), "report_html": str(REPORT_HTML)}


if __name__ == "__main__":
    run_phase6()
    print("Phase 6 done.", REPORT_MD, REPORT_HTML)
