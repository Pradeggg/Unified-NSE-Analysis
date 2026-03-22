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

    # Overview content for marked.js
    portfolio_summary_md = "## Portfolio summary\n\n"
    if summary:
        portfolio_summary_md += f"- **Holdings:** {summary.get('holdings_count', 0)} positions (source: {summary.get('holdings_source', 'N/A')})\n"
        portfolio_summary_md += f"- **Closed trades:** {summary.get('closed_trades_count', 0)}\n"
        portfolio_summary_md += f"- **Total realized PnL:** Rs {summary.get('total_realized_pnl', 0):,.2f}\n"
        portfolio_summary_md += f"- **PnL by tenure:** {summary.get('pnl_by_tenure', {})}\n"
    pnl_summary_md = _read(PNL_SUMMARY_MD) or "*Run Phase 1 for PnL summary.*"
    overview_json = json.dumps(
        {"portfolio_summary": portfolio_summary_md, "pnl_summary": pnl_summary_md},
        ensure_ascii=False,
    ).replace("</script>", "<\\/script>")

    def escape(s: str) -> str:
        if not s:
            return ""
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    # Tab: Overview
    overview_html = (
        "<div class='overview-cards'>"
        "<div class='card-section'><h3 class='card-title'>Portfolio summary</h3>"
        "<div id='overview-portfolio-summary' class='md-rendered'></div></div>"
        "<div class='card-section'><h3 class='card-title'>PnL summary</h3>"
        "<div id='overview-pnl-summary' class='md-rendered'></div></div>"
        "</div>"
        f"<script type='application/json' id='overview-md'>{overview_json}</script>"
    )

    # Tab: Risk & scenarios
    risk = _load_json(RISK_METRICS_JSON)
    scenario_md = _read(SCENARIO_NARRATIVE_MD) or ""
    risk_html_parts = []
    if risk:
        risk_html_parts.append("<div class='card-section'><h3 class='card-title'>Risk metrics</h3><ul>")
        for k in ("portfolio_volatility_annual_pct", "var_95_1d_pct", "sharpe_ratio", "beta_nifty", "max_drawdown_pct"):
            if k in risk and risk[k] is not None:
                risk_html_parts.append(f"<li><strong>{k}</strong>: {risk[k]}</li>")
        risk_html_parts.append("</ul></div>")
    risk_html_parts.append("<div class='card-section'><h3 class='card-title'>Scenario narrative</h3><div id='risk-scenario-md' class='md-rendered'></div></div>")
    scenario_json = json.dumps(scenario_md, ensure_ascii=False).replace("</script>", "<\\/script>")
    risk_html = "\n".join(risk_html_parts) + f"<script type='application/json' id='scenario-md'>{scenario_json}</script>"

    # Tab: Market sentiment (markdown in card)
    sentiment_md = _read(MARKET_SENTIMENT_MD) or ""
    sentiment_json = json.dumps(sentiment_md, ensure_ascii=False).replace("</script>", "<\\/script>")
    sentiment_html = f"<div class='card-section'><h3 class='card-title'>Market sentiment</h3><div id='sentiment-md' class='md-rendered'></div></div><script type='application/json' id='sentiment-md-json'>{sentiment_json}</script>"

    # Tab: Sector assessment
    sector_md = _read(SECTOR_ASSESSMENT_MD) or ""
    sector_json = json.dumps(sector_md, ensure_ascii=False).replace("</script>", "<\\/script>")
    sector_html = f"<div class='card-section'><h3 class='card-title'>Sector assessment</h3><div id='sector-md' class='md-rendered'></div></div><script type='application/json' id='sector-md-json'>{sector_json}</script>"

    # Tab: Technical table
    try:
        tech_df = pd.read_csv(TECHNICAL_BY_STOCK_CSV) if TECHNICAL_BY_STOCK_CSV.exists() else pd.DataFrame()
    except Exception:
        tech_df = pd.DataFrame()
    if tech_df.empty:
        technical_html = "<p>No technical data. Run Phase 3.</p>"
    else:
        hcols = [c for c in ["value_rs", "technical_score"] if c in tech_df.columns]
        technical_html = '<div class="table-scroll">' + _df_to_html_table(tech_df, "table-technical", highlight_cols=hcols or None) + '</div>'

    # Tab: Fundamental table
    try:
        fund_df = pd.read_csv(FUNDAMENTAL_BY_STOCK_CSV) if FUNDAMENTAL_BY_STOCK_CSV.exists() else pd.DataFrame()
    except Exception:
        fund_df = pd.DataFrame()
    if fund_df.empty:
        fundamental_html = "<p>No fundamental data. Run Phase 4.</p>"
    else:
        hcols = [c for c in ["ENHANCED_FUND_SCORE", "EARNINGS_QUALITY", "FINANCIAL_STRENGTH"] if c in fund_df.columns]
        fundamental_html = '<div class="table-scroll">' + _df_to_html_table(fund_df, "table-fundamental", highlight_cols=hcols or None) + '</div>'

    # Tab: Stock narratives
    narratives = _load_json(STOCK_NARRATIVES_JSON)
    if not isinstance(narratives, list):
        narratives = []
    narratives_html = _narratives_to_html(narratives, escape)

    tabs = [
        ("overview", "Overview", overview_html),
        ("guide", "How to read", _guide_tab_html()),
        ("risk", "Risk & scenarios", risk_html),
        ("sentiment", "Market sentiment", sentiment_html),
        ("sector", "Sector assessment", sector_html),
        ("technical", "Technical", technical_html),
        ("fundamental", "Fundamental", fundamental_html),
        ("narratives", "Stock narratives", narratives_html),
    ]
    tab_buttons = "".join(f'<button class="tab-btn" data-tab="{tid}">{label}</button>' for tid, label, _ in tabs)
    tab_panels = "".join(f'<div id="panel-{tid}" class="tab-panel" role="tabpanel">{content}</div>' for tid, _, content in tabs)

    script = """
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script>
(function() {
  function renderOverviewMd() {
    var el = document.getElementById('overview-md');
    if (!el) return;
    try {
      var data = JSON.parse(el.textContent);
      var ids = ['portfolio_summary', 'pnl_summary'];
      ids.forEach(function(key) {
        var div = document.getElementById('overview-' + key.replace('_', '-'));
        if (!div) return;
        var md = data[key] || '';
        if (typeof marked !== 'undefined' && marked.parse) div.innerHTML = marked.parse(md);
        else { div.textContent = md; div.classList.add('md-fallback'); }
      });
    } catch (e) {}
  }
  function renderMd(id, jsonId) {
    var j = document.getElementById(jsonId);
    var d = document.getElementById(id);
    if (!j || !d) return;
    try {
      var md = JSON.parse(j.textContent);
      if (typeof marked !== 'undefined' && marked.parse) d.innerHTML = marked.parse(md);
      else { d.textContent = md; d.classList.add('md-fallback'); }
    } catch (e) {}
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function() {
    renderOverviewMd();
    renderMd('risk-scenario-md', 'scenario-md');
    renderMd('sentiment-md', 'sentiment-md-json');
    renderMd('sector-md', 'sector-md-json');
  });
  else { renderOverviewMd(); renderMd('risk-scenario-md', 'scenario-md'); renderMd('sentiment-md', 'sentiment-md-json'); renderMd('sector-md', 'sector-md-json'); }

  var panels = document.querySelectorAll('.tab-panel');
  var buttons = document.querySelectorAll('.tab-btn');
  function show(id) {
    panels.forEach(function(p) { p.classList.remove('active'); });
    buttons.forEach(function(b) { b.classList.remove('active'); });
    var p = document.getElementById('panel-' + id);
    var b = document.querySelector('[data-tab="' + id + '"]');
    if (p) p.classList.add('active');
    if (b) b.classList.add('active');
  }
  buttons.forEach(function(b) {
    b.addEventListener('click', function() { show(b.getAttribute('data-tab')); });
  });
  if (buttons.length) show(buttons[0].getAttribute('data-tab'));

  function parseCellNum(txt) {
    if (!txt) return NaN;
    var s = String(txt).replace(/%|,/g, '').trim();
    var n = parseFloat(s);
    return isNaN(n) ? NaN : n;
  }
  function sortTable(tableId) {
    var table = document.getElementById(tableId);
    if (!table) return;
    var headers = table.querySelectorAll('thead th');
    var body = table.querySelector('tbody');
    var sortState = { colIndex: -1, asc: true };
    headers.forEach(function(th, colIndex) {
      th.addEventListener('click', function() {
        var rows = Array.from(body.querySelectorAll('tr'));
        if (!rows.length) return;
        var asc = (sortState.colIndex === colIndex) ? !sortState.asc : true;
        sortState.colIndex = colIndex;
        sortState.asc = asc;
        headers.forEach(function(h, i) {
          h.classList.remove('sort-asc', 'sort-desc');
          if (i === colIndex) h.classList.add(asc ? 'sort-asc' : 'sort-desc');
        });
        var cellVal = function(row, ci) { var c = row.cells[ci]; return c ? c.textContent.trim() : ''; };
        var isNum = false;
        for (var r = 0; r < rows.length; r++) {
          var n = parseCellNum(cellVal(rows[r], colIndex));
          if (!isNaN(n)) { isNum = true; break; }
        }
        rows.sort(function(a, b) {
          var va = cellVal(a, colIndex);
          var vb = cellVal(b, colIndex);
          if (isNum) {
            var na = parseCellNum(va);
            var nb = parseCellNum(vb);
            if (isNaN(na)) na = -Infinity;
            if (isNaN(nb)) nb = -Infinity;
            return asc ? na - nb : nb - na;
          }
          return asc ? (va < vb ? -1 : va > vb ? 1 : 0) : (vb < va ? -1 : vb > va ? 1 : 0);
        });
        rows.forEach(function(r) { body.appendChild(r); });
      });
    });
  }
  ['table-technical','table-fundamental'].forEach(sortTable);
})();
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
