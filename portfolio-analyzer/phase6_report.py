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

_HERE = Path(__file__).resolve().parent
_REPORTS_DIR = _HERE.parent / "reports" / "generated_csv"


def _latest_comprehensive_csv() -> "Path | None":
    """Return the most-recently-modified comprehensive_nse_enhanced_*.csv."""
    try:
        candidates = list(_REPORTS_DIR.rglob("comprehensive_nse_enhanced_*.csv"))
        return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None
    except Exception:
        return None

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
/* Sticky table headers */
.sticky-hdr thead th { position: sticky; top: 0; z-index: 2; box-shadow: 0 1px 0 var(--md-divider); }
/* Row match highlight when searching */
tbody tr.row-match { outline: 2px solid #fef08a; outline-offset: -2px; }
/* Heat tiles – portfolio overview */
.heat-tiles-wrap { margin-top: 4px; padding: 4px 0 8px; }
.heat-tiles-wrap .ht-title { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--md-text-secondary); margin: 0 0 8px; }
.heat-tiles { display: flex; flex-wrap: wrap; gap: 3px; }
.heat-tile { border-radius: 3px; padding: 3px 6px; font-size: 0.65rem; font-weight: 600; cursor: default; transition: transform 0.1s; line-height: 1.3; text-align: center; white-space: nowrap; }
.heat-tile:hover { transform: scale(1.12); z-index: 5; position: relative; box-shadow: 0 2px 8px rgba(0,0,0,0.2); }
.ht-strong-add { background:#15803d; color:#fff; }
.ht-add        { background:#22c55e; color:#fff; }
.ht-hold       { background:#ca8a04; color:#fff; }
.ht-reduce     { background:#ea580c; color:#fff; }
.ht-sell       { background:#dc2626; color:#fff; }
.ht-unknown    { background:#94a3b8; color:#fff; }
/* Pagination */
.pager { display: flex; align-items: center; gap: 5px; margin-top: 10px; font-size: 0.8rem; flex-wrap: wrap; }
.pager button { padding: 3px 8px; border: 1px solid var(--md-divider); border-radius: 4px; cursor: pointer; background: #fff; font-size: 0.8rem; transition: background 0.15s; }
.pager button:hover { background: var(--md-bg); }
.pager button.pg-active { background: var(--md-primary); color: #fff; border-color: var(--md-primary); }
.pager .pg-info { color: var(--md-text-secondary); margin: 0 4px; white-space: nowrap; }
/* Table toolbar */
.table-toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.export-btn { padding: 5px 12px; border: 1px solid var(--md-primary); border-radius: var(--md-radius-sm); cursor: pointer; background: transparent; color: var(--md-primary); font-size: 0.8rem; font-weight: 500; transition: all 0.15s; }
.export-btn:hover { background: var(--md-primary); color: #fff; }
.col-toggle-wrap { position: relative; display: inline-block; }
.col-toggle-btn { padding: 5px 12px; border: 1px solid var(--md-divider); border-radius: var(--md-radius-sm); cursor: pointer; background: transparent; color: var(--md-text-secondary); font-size: 0.8rem; }
.col-toggle-btn:hover { background: var(--md-bg); }
.col-toggle-panel { display: none; position: absolute; top: calc(100% + 4px); left: 0; background: #fff; border: 1px solid var(--md-divider); border-radius: var(--md-radius); padding: 10px 14px; z-index: 20; box-shadow: var(--md-elevation-2); min-width: 160px; }
.col-toggle-panel.visible { display: block; }
.col-toggle-panel label { display: flex; align-items: center; gap: 6px; font-size: 0.82rem; margin-bottom: 6px; cursor: pointer; user-select: none; }
.col-toggle-panel label:last-child { margin-bottom: 0; }
/* Global search in app-bar */
.app-bar-row { display: flex; align-items: center; gap: 12px; margin-top: 10px; flex-wrap: wrap; }
.global-search-wrap { position: relative; display: flex; align-items: center; }
.global-search-wrap svg { position: absolute; left: 8px; pointer-events: none; opacity: 0.65; }
#global-search { padding: 6px 10px 6px 28px; border: 1px solid rgba(255,255,255,0.35); border-radius: var(--md-radius-sm); background: rgba(255,255,255,0.15); color: #fff; font-family: inherit; font-size: 0.875rem; width: 230px; outline: none; transition: background 0.2s, border-color 0.2s; }
#global-search::placeholder { color: rgba(255,255,255,0.65); }
#global-search:focus { background: rgba(255,255,255,0.25); border-color: rgba(255,255,255,0.75); }
.kbd-hint { font-size: 0.7rem; color: rgba(255,255,255,0.55); white-space: nowrap; }
/* RSI overbought / oversold tags */
.rsi-os { font-size:0.65rem; color:#15803d; font-weight:700; margin-left:3px; }
.rsi-ob { font-size:0.65rem; color:#b91c1c; font-weight:700; margin-left:3px; }
/* Overview chart grid */
.chart-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin: 18px 0; }
@media (max-width: 700px) { .chart-grid { grid-template-columns: 1fr; } }
.chart-card { background: #fff; border-radius: var(--md-radius); padding: 16px; box-shadow: var(--md-elevation-1); }
.chart-card h4 { margin: 0 0 12px 0; font-size: 0.88rem; font-weight: 500; color: var(--md-text-secondary); text-transform: uppercase; letter-spacing: 0.04em; }
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
    """Render searchable, filterable narrative cards with rich technical + fundamental data."""
    if not narratives:
        return "<p>No narratives.</p>"

    # Sort by value descending by default
    try:
        narratives = sorted(narratives, key=lambda n: float(n.get("value_rs") or 0), reverse=True)
    except Exception:
        pass

    # Decision counts for filter chips
    from collections import Counter
    dec_counts = Counter(str(n.get("recommendation", "HOLD")).upper() for n in narratives)
    css_map = {"STRONG ADD": "rec-strong-add", "ADD": "rec-add", "HOLD": "rec-hold",
               "REDUCE": "rec-reduce", "SELL": "rec-sell"}

    filter_row = (
        '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;align-items:center">'
        '<span style="font-size:0.8rem;color:var(--md-text-secondary)">Filter:</span>'
        '<button class="rec-badge rec-unknown" onclick="narrativeFilter(\'\')" '
        'style="cursor:pointer;border:none">All (' + str(len(narratives)) + ')</button>'
    )
    for rec in ["STRONG ADD", "ADD", "HOLD", "REDUCE", "SELL"]:
        n_count = dec_counts.get(rec, 0)
        if n_count > 0:
            cls = css_map.get(rec, "rec-unknown")
            filter_row += (f'<button class="rec-badge {cls}" onclick="narrativeFilter(\'{rec}\')" '
                           f'style="cursor:pointer;border:none">{rec} ({n_count})</button>')
    filter_row += '</div>'

    # Sort chips
    sort_row = (
        '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px;align-items:center">'
        '<span style="font-size:0.8rem;color:var(--md-text-secondary)">Sort:</span>'
        '<button class="col-toggle-btn" onclick="narrativeSort(\'value\')">Value ↕</button>'
        '<button class="col-toggle-btn" onclick="narrativeSort(\'tech\')">Tech Score ↕</button>'
        '<button class="col-toggle-btn" onclick="narrativeSort(\'decision\')">Decision ↕</button>'
        '<button class="col-toggle-btn" onclick="narrativeSort(\'alpha\')">A–Z ↕</button>'
        '</div>'
    )

    # Search bar + export
    toolbar = (
        '<div class="table-toolbar" style="margin-bottom:14px">'
        '<input class="search-bar" style="margin:0;flex:1;min-width:200px" type="search" '
        'id="search-narratives" placeholder="🔍 Search symbol, trend, decision, signal…" '
        'oninput="narrativeSearch(this.value)">'
        '<button class="export-btn" onclick="exportNarratives()">⬇ Export CSV</button>'
        '</div>'
    )

    # Build cards
    cards = []
    for n in narratives:
        sym     = escape_fn(str(n.get("symbol", "")))
        rec     = str(n.get("recommendation") or "HOLD").upper()
        ts      = n.get("technical_score")
        fs      = n.get("fund_score")
        rsi_v   = n.get("rsi")
        trend   = str(n.get("trend_signal") or "")
        val     = n.get("value_rs")
        qty     = n.get("quantity")
        price   = n.get("current_price")
        chg_1d  = n.get("change_1d_pct")
        chg_1w  = n.get("change_1w_pct")
        chg_1m  = n.get("change_1m_pct")
        trading_sig = str(n.get("trading_signal") or "")

        badge = _rec_badge(rec)
        rec_css = css_map.get(rec, "rec-unknown")

        # Header row: symbol + badge + key metrics inline
        price_str = f"₹{float(price):,.2f}" if price is not None else "—"
        try: price_str = f"₹{float(price):,.2f}"
        except (TypeError, ValueError): price_str = "—"
        val_str = f"₹{float(val):,.0f}" if val is not None else "—"
        try: val_str = f"₹{float(val):,.0f}"
        except (TypeError, ValueError): val_str = "—"

        header = (
            f'<div class="nc-header">'
            f'<span class="nc-sym">{sym}</span>'
            f'{badge}'
            f'<span class="nc-meta">Qty: {qty} &nbsp;·&nbsp; ₹{val_str} &nbsp;·&nbsp; {price_str}</span>'
            f'</div>'
        )

        # Score row: tech bar + RSI heatmap + fund bar
        rsi_tag = ""
        rsi_bg = ""
        try:
            rv = float(rsi_v)
            if rv < 30:   rsi_bg = "background:hsla(120,65%,90%,0.75);"; rsi_tag = '<span class="rsi-os">OS</span>'
            elif rv > 70: rsi_bg = "background:hsla(0,65%,90%,0.75);"; rsi_tag = '<span class="rsi-ob">OB</span>'
            rsi_display = f"{rv:.1f}"
        except (TypeError, ValueError):
            rsi_display = "—"

        score_row = (
            '<div class="nc-scores">'
            f'<div class="nc-score-item"><span class="nc-slabel">Tech</span>{_score_bar(ts)}</div>'
            f'<div class="nc-score-item"><span class="nc-slabel">RSI</span>'
            f'<span style="{rsi_bg}padding:1px 5px;border-radius:3px">{rsi_display}{rsi_tag}</span></div>'
            f'<div class="nc-score-item"><span class="nc-slabel">Fund</span>{_score_bar(fs)}</div>'
        )

        # Change chips
        def _chg_chip(label, v):
            try:
                f = float(v)
                sign = "+" if f >= 0 else ""
                col = "#16a34a" if f >= 0 else "#dc2626"
                return f'<span style="background:{col}22;color:{col};padding:1px 6px;border-radius:10px;font-size:0.72rem;font-weight:600">{label} {sign}{f:.1f}%</span>'
            except (TypeError, ValueError):
                return ""

        chg_row = " ".join(filter(None, [_chg_chip("1D", chg_1d), _chg_chip("1W", chg_1w), _chg_chip("1M", chg_1m)]))
        if chg_row:
            score_row += f'<div class="nc-score-item" style="align-self:center;display:flex;gap:4px;flex-wrap:wrap">{chg_row}</div>'

        if trend and trend not in ("UNKNOWN", ""):
            trend_color = ("#15803d" if "BULL" in trend.upper() else
                           "#dc2626" if "BEAR" in trend.upper() else "#64748b")
            score_row += (f'<div class="nc-score-item"><span class="nc-slabel">Trend</span>'
                          f'<span style="color:{trend_color};font-size:0.8rem;font-weight:500">{escape_fn(trend)}</span></div>')
        if trading_sig and trading_sig not in ("UNKNOWN", ""):
            score_row += (f'<div class="nc-score-item"><span class="nc-slabel">Signal</span>'
                          f'<span style="font-size:0.8rem;font-weight:500">{escape_fn(trading_sig)}</span></div>')
        score_row += '</div>'

        # Fundamental breakdown
        fund_html = ""
        fund_keys = [("fund_earnings_quality", "EQ"), ("fund_sales_growth", "SG"),
                     ("fund_financial_strength", "FS"), ("fund_institutional_backing", "IB")]
        fund_vals = [(lbl, n.get(k)) for k, lbl in fund_keys if n.get(k) is not None]
        if fund_vals:
            fund_items = "".join(
                f'<span class="nc-fund-item" title="{lbl}">'
                f'<span class="nc-fund-label">{lbl}</span>'
                f'<span class="nc-fund-bar">'
                f'<span class="nc-fund-fill" style="width:{min(100,float(v)):.0f}%;'
                f'background:{"#16a34a" if float(v)>=65 else "#f59e0b" if float(v)>=45 else "#dc2626"}"></span>'
                f'</span>'
                f'<span class="nc-fund-val">{float(v):.0f}</span>'
                f'</span>'
                for lbl, v in fund_vals
            )
            fund_html = f'<div class="nc-fund-row">{fund_items}</div>'

        # Detailed summaries
        details_html = ""
        for key, label in [("pnl_summary", "P&L"), ("quarterly_summary", "Quarterly"),
                            ("balance_sheet_summary", "Balance sheet"), ("ratios_summary", "Ratios")]:
            if n.get(key) and str(n[key]).strip():
                details_html += (f'<p class="nc-detail"><span class="nc-detail-label">{label}:</span> '
                                 f'{escape_fn(str(n[key]).strip())}</p>')

        # Narrative body (strip the redundant technical line already shown in score row)
        narrative = (n.get("narrative") or "").strip()
        body_html = ""
        if narrative:
            for para in narrative.split("\n\n"):
                para = para.strip()
                if not para:
                    continue
                # Skip the raw *Technical:* and *Momentum:* lines (already shown visually)
                if para.startswith("*Technical:*") or para.startswith("*Momentum:*"):
                    continue
                body_html += f'<p class="narrative-para">{_markdown_para_to_html(para)}</p>'

        # Assemble card — data attrs for JS filtering/sorting
        try: val_float = float(val or 0)
        except (TypeError, ValueError): val_float = 0
        try: ts_float = float(ts or 50)
        except (TypeError, ValueError): ts_float = 50
        dec_order = {"STRONG ADD": 0, "ADD": 1, "HOLD": 2, "REDUCE": 3, "SELL": 4}.get(rec, 5)

        cards.append(
            f'<div class="narrative-card" data-sym="{sym}" data-decision="{rec}" '
            f'data-val="{val_float:.0f}" data-tech="{ts_float:.1f}" data-decord="{dec_order}">'
            + header + score_row + fund_html + details_html + body_html
            + '</div>'
        )

    # Export data as JSON for JS
    export_data = [
        {"Symbol": n.get("symbol",""), "Decision": n.get("recommendation",""),
         "Tech": n.get("technical_score",""), "Fund": n.get("fund_score",""),
         "RSI": n.get("rsi",""), "Trend": n.get("trend_signal",""),
         "Value": n.get("value_rs",""), "1M%": n.get("change_1m_pct","")}
        for n in narratives
    ]
    export_json = json.dumps(export_data, ensure_ascii=False).replace("</script>", "<\\/script>")

    cards_container = (
        '<div id="narratives-container">' + "\n".join(cards) + '</div>'
        f'<div id="narratives-empty" style="display:none;padding:40px;text-align:center;color:var(--md-text-secondary)">No narratives match your filter.</div>'
        f'<script type="application/json" id="narratives-export-data">{export_json}</script>'
    )

    return filter_row + sort_row + toolbar + cards_container


def _narratives_css() -> str:
    """Additional CSS for narrative cards."""
    return """
.nc-header { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:10px; }
.nc-sym { font-size:1.1rem; font-weight:600; color:var(--md-primary-dark); min-width:80px; }
.nc-meta { font-size:0.78rem; color:var(--md-text-secondary); margin-left:auto; }
.nc-scores { display:flex; flex-wrap:wrap; gap:12px; padding:10px 12px; background:var(--md-bg); border-radius:var(--md-radius-sm); margin-bottom:10px; align-items:center; }
.nc-score-item { display:flex; align-items:center; gap:6px; }
.nc-slabel { font-size:0.7rem; text-transform:uppercase; letter-spacing:0.05em; color:var(--md-text-secondary); min-width:28px; }
.nc-fund-row { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:10px; }
.nc-fund-item { display:flex; align-items:center; gap:4px; font-size:0.78rem; }
.nc-fund-label { color:var(--md-text-secondary); min-width:22px; }
.nc-fund-bar { width:60px; height:5px; background:#e2e8f0; border-radius:3px; }
.nc-fund-fill { height:100%; border-radius:3px; display:block; }
.nc-fund-val { font-weight:600; min-width:24px; font-size:0.78rem; }
.nc-detail { font-size:0.8rem; margin:4px 0; color:var(--md-text); }
.nc-detail-label { font-weight:500; color:var(--md-text-secondary); }
.narrative-card { border-left:3px solid var(--md-primary-light); }
"""


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


def _heat_bg(val, lo: float, hi: float, good_hue: int = 120, bad_hue: int = 0, alpha: float = 0.25) -> str:
    """Inline HSL background style; green = good, red = bad."""
    try:
        v = float(val)
        frac = max(0.0, min(1.0, (v - lo) / (hi - lo))) if hi != lo else 0.5
        hue = bad_hue + frac * (good_hue - bad_hue)
        return f"background:hsla({hue:.0f},75%,92%,{alpha});"
    except (TypeError, ValueError):
        return ""


def _rsi_cell(val) -> str:
    """RSI table cell with heatmap background: green=oversold(<30), red=overbought(>70)."""
    try:
        v = float(val)
        if v < 30:
            bg = "background:hsla(120,65%,90%,0.75);"
            tag = '<span class="rsi-os">OS</span>'
        elif v > 70:
            bg = "background:hsla(0,65%,90%,0.75);"
            tag = '<span class="rsi-ob">OB</span>'
        elif v > 60:
            bg = "background:hsla(35,70%,92%,0.55);"
            tag = ""
        else:
            bg, tag = "", ""
        return f'<td style="{bg}">{v:.1f}{tag}</td>'
    except (TypeError, ValueError):
        return "<td>—</td>"


def _heat_chg_cell(val, scale: float = 8.0) -> str:
    """Change % cell with heatmap background intensity proportional to magnitude."""
    try:
        f = float(val)
        sign = "+" if f >= 0 else ""
        intensity = min(abs(f) / scale, 1.0)
        if f >= 0:
            lightness = int(95 - intensity * 18)
            bg = f"background:hsla(120,70%,{lightness}%,0.65);"
        else:
            lightness = int(95 - intensity * 18)
            bg = f"background:hsla(0,70%,{lightness}%,0.65);"
        return f'<td style="{bg};font-weight:500">{sign}{f:.1f}%</td>'
    except (TypeError, ValueError):
        return "<td>—</td>"


def _heat_vol_cell(val) -> str:
    """Volatility % cell: low=green, medium=yellow, high=red background."""
    try:
        v = float(val)
        if v < 25:
            bg = "background:hsla(120,60%,91%,0.65);"
        elif v < 45:
            bg = "background:hsla(45,80%,91%,0.65);"
        else:
            bg = "background:hsla(0,65%,91%,0.65);"
        return f'<td style="{bg}">{v:.1f}%</td>'
    except (TypeError, ValueError):
        return "<td>—</td>"


def _build_heat_tiles_from_csvs() -> str:
    """Build portfolio heat-tile grid from holdings + technical CSVs for Overview tab."""
    import math
    import pandas as pd

    try:
        hold = pd.read_csv(HOLDINGS_CSV) if HOLDINGS_CSV.exists() else pd.DataFrame()
        tech = pd.read_csv(TECHNICAL_BY_STOCK_CSV) if TECHNICAL_BY_STOCK_CSV.exists() else pd.DataFrame()
    except Exception:
        return ""
    if hold.empty:
        return ""

    df = hold.copy()
    df["symbol"] = df["symbol"].astype(str)
    if not tech.empty and "symbol" in tech.columns:
        merge_cols = [c for c in ["symbol", "technical_score", "fund_score",
                                   "enhanced_fund_score", "recommendation", "trading_signal"] if c in tech.columns]
        df = df.merge(tech[merge_cols], on="symbol", how="left")

    # Compute Decision
    def _dec(row) -> str:
        ts = float(row.get("technical_score") or 50)
        fs = float(row.get("enhanced_fund_score") or row.get("fund_score") or 50)
        combined = ts * 0.6 + fs * 0.4
        if combined >= 70: return "STRONG ADD"
        elif combined >= 58: return "ADD"
        elif combined >= 42: return "HOLD"
        elif combined >= 28: return "REDUCE"
        else: return "SELL"

    df["Decision"] = df.apply(_dec, axis=1)

    total_val = float(df["value_rs"].sum() or 1)
    dec_cls = {
        "STRONG ADD": "ht-strong-add", "ADD": "ht-add", "HOLD": "ht-hold",
        "REDUCE": "ht-reduce", "SELL": "ht-sell",
    }
    tiles = []
    for _, row in df.sort_values("value_rs", ascending=False).iterrows():
        sym = html_module.escape(str(row.get("symbol", "")))
        val = float(row.get("value_rs") or 0)
        dec = str(row.get("Decision", ""))
        ts = row.get("technical_score", "")
        cls = dec_cls.get(dec, "ht-unknown")
        # Width: log-scaled between 36–90px
        w = max(36, min(90, int(36 + 54 * math.log1p(val / total_val * 100) / math.log1p(100))))
        title = f"{sym} | ₹{val:,.0f} | {dec} | Tech: {ts}"
        tiles.append(f'<div class="heat-tile {cls}" style="min-width:{w}px" title="{html_module.escape(title)}">{sym}</div>')

    dec_counts = df["Decision"].value_counts()
    legend_parts = []
    for rec in ["STRONG ADD", "ADD", "HOLD", "REDUCE", "SELL"]:
        n = dec_counts.get(rec, 0)
        if n > 0:
            css_map = {"STRONG ADD": "rec-strong-add", "ADD": "rec-add", "HOLD": "rec-hold",
                       "REDUCE": "rec-reduce", "SELL": "rec-sell"}
            legend_parts.append(f'<span class="rec-badge {css_map[rec]}">{rec} {n}</span>')
    legend = " &nbsp; ".join(legend_parts)

    return (
        '<div class="card-section" style="margin-top:16px">'
        '<h3 class="card-title">Holdings heatmap <span style="font-size:0.75rem;font-weight:400;color:var(--md-text-secondary)">'
        '— tile size = portfolio value · colour = decision · hover for details</span></h3>'
        f'<div style="margin-bottom:10px;display:flex;flex-wrap:wrap;gap:6px">{legend}</div>'
        f'<div class="heat-tiles">{"".join(tiles)}</div>'
        '</div>'
    )


def _build_holdings_tab() -> str:
    """Merged holdings: holdings + technical (real scores) + fundamental + risk. No PnL column."""
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

    if hold.empty:
        return "<p>No holdings data. Ensure holdings.csv exists in output/.</p>"

    # Merge tech (rich columns — includes enhanced_fund_score from comprehensive CSV)
    df = hold.copy()
    df["symbol"] = df["symbol"].astype(str)
    tech_cols = ["symbol", "current_price", "technical_score", "rsi", "recommendation",
                 "trend_signal", "change_1d_pct", "change_1w_pct", "change_1m_pct",
                 "relative_strength", "enhanced_fund_score"]
    if not tech.empty and "symbol" in tech.columns:
        tc = tech[[c for c in tech_cols if c in tech.columns]].copy()
        df = df.merge(tc, on="symbol", how="left")

    # Merge fund — fill fund_score where not provided by tech CSV
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
            if "enhanced_fund_score" in df.columns:
                df["fund_score"] = df["enhanced_fund_score"].combine_first(df.get("fund_score_fb", pd.Series(dtype=float)))
            else:
                df["fund_score"] = df.get("fund_score_fb", pd.Series(dtype=float))
            df = df.drop(columns=["fund_score_fb"], errors="ignore")
    elif "enhanced_fund_score" in df.columns:
        df["fund_score"] = df["enhanced_fund_score"]

    # Merge per-stock volatility and recompute weight
    if not risk_s.empty and "symbol" in risk_s.columns and "volatility_annual_pct" in risk_s.columns:
        df = df.merge(risk_s[["symbol", "volatility_annual_pct"]], on="symbol", how="left")

    # Composite decision (tech×0.6 + fund×0.4)
    import math
    def _decision(row) -> str:
        ts = row.get("technical_score")
        fs = row.get("fund_score")
        try: ts = float(ts) if ts is not None and not (isinstance(ts, float) and math.isnan(ts)) else 50.0
        except (TypeError, ValueError): ts = 50.0
        try: fs = float(fs) if fs is not None and not (isinstance(fs, float) and math.isnan(fs)) else 50.0
        except (TypeError, ValueError): fs = 50.0
        combined = ts * 0.6 + fs * 0.4
        if combined >= 70:   return "STRONG ADD"
        elif combined >= 58: return "ADD"
        elif combined >= 42: return "HOLD"
        elif combined >= 28: return "REDUCE"
        else:                return "SELL"

    df["Decision"] = df.apply(_decision, axis=1)
    df = df.sort_values("value_rs", ascending=False)

    # Decision legend card
    decision_legend = (
        '<div class="card-section" style="margin-bottom:14px;padding:12px 16px">'
        '<div style="display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start">'
        '<div><span style="font-size:0.78rem;font-weight:500;color:var(--md-text-secondary);display:block;margin-bottom:4px">HOW DECISION IS COMPUTED</span>'
        '<code style="font-size:0.78rem;background:var(--md-bg);padding:3px 8px;border-radius:4px">'
        'Score = Tech × 0.6 + Fund × 0.4</code></div>'
        '<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center">'
        '<span class="rec-badge rec-strong-add">STRONG ADD ≥ 70</span>'
        '<span class="rec-badge rec-add">ADD ≥ 58</span>'
        '<span class="rec-badge rec-hold">HOLD ≥ 42</span>'
        '<span class="rec-badge rec-reduce">REDUCE ≥ 28</span>'
        '<span class="rec-badge rec-sell">SELL &lt; 28</span>'
        '</div></div></div>'
    )

    # Filter buttons
    dec_counts = df["Decision"].value_counts()
    filter_btns = '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;align-items:center">'
    filter_btns += '<span style="font-size:0.8rem;color:var(--md-text-secondary);margin-right:4px">Filter:</span>'
    filter_btns += '<button class="rec-badge rec-unknown" onclick="setDecFilter(\'table-holdings\',\'\')" style="cursor:pointer;border:none">All</button>'
    for rec in ["STRONG ADD", "ADD", "HOLD", "REDUCE", "SELL"]:
        n = dec_counts.get(rec, 0)
        if n > 0:
            cls_map = {"STRONG ADD": "rec-strong-add", "ADD": "rec-add", "HOLD": "rec-hold",
                       "REDUCE": "rec-reduce", "SELL": "rec-sell"}
            cls = cls_map[rec]
            filter_btns += (f'<button class="rec-badge {cls}" onclick="setDecFilter(\'table-holdings\',\'{rec}\')" '
                            f'style="cursor:pointer;border:none">{rec} ({n})</button>')
    filter_btns += '</div>'

    # Toolbar
    headers = ["Symbol", "Qty", "Value (₹)", "Price", "Tech Score", "RSI",
               "1D %", "1W %", "1M %", "Fund Score", "Vol %", "Rel. Strength", "Decision", "Trend"]
    toggle_checks = "".join(
        f'<label><input type="checkbox" checked onchange="toggleCol(\'table-holdings\',{i},this.checked)"> {h}</label>'
        for i, h in enumerate(headers)
    )
    toolbar = (
        '<div class="table-toolbar">'
        '<input class="search-bar" style="margin:0;flex:1;min-width:180px" type="search" '
        'id="search-holdings" placeholder="🔍 Search symbol, signal, decision…" '
        'oninput="filterTable(\'table-holdings\',this.value)">'
        '<button class="export-btn" onclick="exportCSV(\'table-holdings\',\'holdings\')">⬇ Export CSV</button>'
        '<div class="col-toggle-wrap">'
        '<button class="col-toggle-btn" onclick="toggleColPanel(\'col-panel-holdings\')">Columns ▾</button>'
        f'<div id="col-panel-holdings" class="col-toggle-panel">{toggle_checks}</div>'
        '</div>'
        '</div>'
    )

    # Build HTML table with heatmap cells
    tbl = ['<table id="table-holdings" class="sortable sticky-hdr"><thead><tr>']
    for h in headers:
        tbl.append(f'<th>{h}</th>')
    tbl.append("</tr></thead><tbody>")

    for _, row in df.iterrows():
        dec = str(row.get("Decision", "HOLD"))
        tbl.append("<tr>")
        tbl.append(f'<td><strong>{html_module.escape(str(row.get("symbol", "")))}</strong></td>')
        qty = row.get("quantity", "")
        tbl.append(f'<td>{html_module.escape(str(qty) if pd.notna(qty) else "—")}</td>')
        val = row.get("value_rs")
        tbl.append(f'<td>{"₹{:,.0f}".format(float(val)) if pd.notna(val) else "—"}</td>')
        price = row.get("current_price")
        tbl.append(f'<td>{"₹{:,.2f}".format(float(price)) if pd.notna(price) else "—"}</td>')
        tbl.append(f'<td>{_score_bar(row.get("technical_score"))}</td>')
        tbl.append(_rsi_cell(row.get("rsi")))
        tbl.append(_heat_chg_cell(row.get("change_1d_pct"), scale=3.0))
        tbl.append(_heat_chg_cell(row.get("change_1w_pct"), scale=6.0))
        tbl.append(_heat_chg_cell(row.get("change_1m_pct"), scale=12.0))
        tbl.append(f'<td>{_score_bar(row.get("fund_score"))}</td>')
        tbl.append(_heat_vol_cell(row.get("volatility_annual_pct")))
        # Relative Strength (heatmap: higher = better)
        rs = row.get("relative_strength")
        try:
            rsv = float(rs)
            rs_bg = _heat_bg(rsv, 0, 50, good_hue=120, bad_hue=0, alpha=0.3)
            tbl.append(f'<td style="{rs_bg};font-weight:500">{rsv:.1f}</td>')
        except (TypeError, ValueError):
            tbl.append("<td>—</td>")
        tbl.append(f'<td>{_rec_badge(dec)}</td>')
        trend = str(row.get("trend_signal", "") or "")
        tbl.append(f'<td><span style="font-size:0.75rem">{html_module.escape(trend)}</span></td>')
        tbl.append("</tr>")
    tbl.append("</tbody></table>")

    return (
        decision_legend
        + filter_btns
        + toolbar
        + '<div class="table-scroll">' + "\n".join(tbl) + "</div>"
    )


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
    df = df.sort_values("value_rs", ascending=False)

    # Decision legend card
    decision_legend = (
        '<div class="card-section" style="margin-bottom:14px;padding:12px 16px">'
        '<div style="display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start">'
        '<div><span style="font-size:0.78rem;font-weight:500;color:var(--md-text-secondary);display:block;margin-bottom:4px">HOW DECISION IS COMPUTED</span>'
        '<code style="font-size:0.78rem;background:var(--md-bg);padding:3px 8px;border-radius:4px">'
        'Score = Tech × 0.6 + Fund × 0.4</code></div>'
        '<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center">'
        '<span class="rec-badge rec-strong-add">STRONG ADD ≥ 70</span>'
        '<span class="rec-badge rec-add">ADD ≥ 58</span>'
        '<span class="rec-badge rec-hold">HOLD ≥ 42</span>'
        '<span class="rec-badge rec-reduce">REDUCE ≥ 28</span>'
        '<span class="rec-badge rec-sell">SELL &lt; 28</span>'
        '</div></div></div>'
    )

    # Filter buttons
    dec_counts = df["Decision"].value_counts()
    filter_btns = '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;align-items:center">'
    filter_btns += '<span style="font-size:0.8rem;color:var(--md-text-secondary);margin-right:4px">Filter:</span>'
    filter_btns += '<button class="rec-badge rec-unknown" onclick="setDecFilter(\'table-holdings\',\'\')" style="cursor:pointer;border:none">All</button>'
    for rec in ["STRONG ADD", "ADD", "HOLD", "REDUCE", "SELL"]:
        n = dec_counts.get(rec, 0)
        if n > 0:
            cls_map = {"STRONG ADD": "rec-strong-add", "ADD": "rec-add", "HOLD": "rec-hold",
                       "REDUCE": "rec-reduce", "SELL": "rec-sell"}
            cls = cls_map[rec]
            filter_btns += (f'<button class="rec-badge {cls}" onclick="setDecFilter(\'table-holdings\',\'{rec}\')" '
                            f'style="cursor:pointer;border:none">{rec} ({n})</button>')
    filter_btns += '</div>'

    # Toolbar
    headers = ["Symbol", "Qty", "Value (₹)", "Price", "Tech Score", "RSI",
               "1D %", "1W %", "1M %", "Fund Score", "Vol %", "Rel. Strength", "Decision", "Trend"]
    toggle_checks = "".join(
        f'<label><input type="checkbox" checked onchange="toggleCol(\'table-holdings\',{i},this.checked)"> {h}</label>'
        for i, h in enumerate(headers)
    )
    toolbar = (
        '<div class="table-toolbar">'
        '<input class="search-bar" style="margin:0;flex:1;min-width:180px" type="search" '
        'id="search-holdings" placeholder="🔍 Search symbol, signal, decision…" '
        'oninput="filterTable(\'table-holdings\',this.value)">'
        '<button class="export-btn" onclick="exportCSV(\'table-holdings\',\'holdings\')">⬇ Export CSV</button>'
        '<div class="col-toggle-wrap">'
        '<button class="col-toggle-btn" onclick="toggleColPanel(\'col-panel-holdings\')">Columns ▾</button>'
        f'<div id="col-panel-holdings" class="col-toggle-panel">{toggle_checks}</div>'
        '</div>'
        '</div>'
    )

    # Build HTML table
    tbl = ['<table id="table-holdings" class="sortable sticky-hdr"><thead><tr>']
    for h in headers:
        tbl.append(f'<th>{h}</th>')
    tbl.append("</tr></thead><tbody>")

    for _, row in df.iterrows():
        dec = str(row.get("Decision", "HOLD"))
        tbl.append("<tr>")
        tbl.append(f'<td><strong>{html_module.escape(str(row.get("symbol", "")))}</strong></td>')
        qty = row.get("quantity", "")
        tbl.append(f'<td>{html_module.escape(str(qty) if pd.notna(qty) else "—")}</td>')
        val = row.get("value_rs")
        tbl.append(f'<td>{"₹{:,.0f}".format(float(val)) if pd.notna(val) else "—"}</td>')
        price = row.get("current_price")
        tbl.append(f'<td>{"₹{:,.2f}".format(float(price)) if pd.notna(price) else "—"}</td>')
        tbl.append(f'<td>{_score_bar(row.get("technical_score"))}</td>')
        tbl.append(_rsi_cell(row.get("rsi")))
        tbl.append(_heat_chg_cell(row.get("change_1d_pct"), scale=3.0))
        tbl.append(_heat_chg_cell(row.get("change_1w_pct"), scale=6.0))
        tbl.append(_heat_chg_cell(row.get("change_1m_pct"), scale=12.0))
        tbl.append(f'<td>{_score_bar(row.get("fund_score"))}</td>')
        tbl.append(_heat_vol_cell(row.get("volatility_annual_pct")))
        rs = row.get("relative_strength")
        try:
            rsv = float(rs)
            rs_bg = _heat_bg(rsv, 0, 50, good_hue=120, bad_hue=0, alpha=0.3)
            tbl.append(f'<td style="{rs_bg};font-weight:500">{rsv:.1f}</td>')
        except (TypeError, ValueError):
            tbl.append("<td>—</td>")
        tbl.append(f'<td>{_rec_badge(dec)}</td>')
        trend = str(row.get("trend_signal", "") or "")
        tbl.append(f'<td><span style="font-size:0.75rem">{html_module.escape(trend)}</span></td>')
        tbl.append("</tr>")
    tbl.append("</tbody></table>")

    return (
        decision_legend
        + filter_btns
        + toolbar
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

    # Per-stock volatility table — recompute weight from actual holdings value
    vol_html = ""
    try:
        risk_s = pd.read_csv(RISK_METRICS_CSV) if RISK_METRICS_CSV.exists() else pd.DataFrame()
        if not risk_s.empty:
            # Recompute actual portfolio weight from holdings.csv
            if HOLDINGS_CSV.exists():
                hold_wt = pd.read_csv(HOLDINGS_CSV)[["symbol", "value_rs"]]
                hold_wt["symbol"] = hold_wt["symbol"].str.upper()
                risk_s["symbol"] = risk_s["symbol"].str.upper()
                total_val = hold_wt["value_rs"].sum()
                hold_wt["weight_pct"] = (hold_wt["value_rs"] / total_val * 100).round(2)
                risk_s = risk_s.drop(columns=["weight_pct"], errors="ignore")
                risk_s = risk_s.merge(hold_wt[["symbol", "weight_pct", "value_rs"]], on="symbol", how="left")

            risk_s = risk_s.sort_values("volatility_annual_pct", ascending=False)

            # Build custom table for precise formatting
            vol_rows = []
            for _, r in risk_s.iterrows():
                wt  = r.get("weight_pct")
                vl  = r.get("value_rs")
                vlt = r.get("volatility_annual_pct")
                sym = html_module.escape(str(r.get("symbol", "")))
                wt_s  = f"{float(wt):.2f}%" if pd.notna(wt) else "—"
                val_s = f"₹{float(vl):,.0f}" if pd.notna(vl) else "—"
                vlt_v = float(vlt) if pd.notna(vlt) else None
                if vlt_v is not None:
                    if vlt_v < 25:   vlt_bg = "background:hsla(120,65%,90%,0.6);"
                    elif vlt_v < 45: vlt_bg = "background:hsla(45,75%,90%,0.6);"
                    else:            vlt_bg = "background:hsla(0,65%,90%,0.6);"
                    vlt_s = f"{vlt_v:.1f}%"
                else:
                    vlt_bg, vlt_s = "", "—"
                vol_rows.append(
                    f'<tr><td><strong>{sym}</strong></td><td>{wt_s}</td><td>{val_s}</td>'
                    f'<td style="{vlt_bg}">{vlt_s}</td></tr>'
                )
            vol_tbl = (
                '<table id="table-risk-stock" class="sortable sticky-hdr"><thead><tr>'
                '<th>Symbol</th><th>Weight %</th><th>Value (₹)</th><th>Volatility % (ann)</th>'
                '</tr></thead><tbody>' + "".join(vol_rows) + '</tbody></table>'
            )
            vol_html = (
                '<div class="card-section" style="margin-top:16px"><h3 class="card-title">Per-stock volatility</h3>'
                f'<input class="search-bar" type="search" placeholder="Filter symbols…" '
                f'oninput="filterTable(\'table-risk-stock\',this.value)">'
                '<div class="table-scroll">' + vol_tbl + '</div></div>'
            )
    except Exception as e:
        vol_html = f'<p style="color:red">Error loading volatility: {html_module.escape(str(e))}</p>'

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


def _build_sector_tab() -> str:
    """Build rich sector assessment: market-cap breakdown, sector breadth, macro tailwinds."""
    import pandas as pd
    _HERE_RPT = Path(__file__).resolve().parent.parent

    # ── 1. Market-cap breakdown of portfolio ───────────────────────────────
    mcap_html = ""
    try:
        hold = pd.read_csv(HOLDINGS_CSV) if HOLDINGS_CSV.exists() else pd.DataFrame()
        comp_glob = sorted((_HERE_RPT / "reports" / "generated_csv").rglob("comprehensive_nse_enhanced_*.csv"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
        if not hold.empty and comp_glob:
            comp = pd.read_csv(comp_glob[0])
            comp["SYMBOL"] = comp["SYMBOL"].str.upper()
            hold["symbol"] = hold["symbol"].str.upper()
            merged = hold.merge(comp[["SYMBOL", "MARKET_CAP_CATEGORY", "COMPANY_NAME",
                                      "TECHNICAL_SCORE", "TRADING_SIGNAL"]],
                                left_on="symbol", right_on="SYMBOL", how="left")
            total_val = merged["value_rs"].sum()

            # Market cap summary table
            mcap_grp = (merged.groupby("MARKET_CAP_CATEGORY", dropna=False)
                        .agg(count=("symbol", "count"), value=("value_rs", "sum"))
                        .reset_index()
                        .sort_values("value", ascending=False))
            mcap_grp["pct"] = (mcap_grp["value"] / total_val * 100).round(1)
            mcap_grp["MARKET_CAP_CATEGORY"] = mcap_grp["MARKET_CAP_CATEGORY"].fillna("Unknown")

            mcap_rows = ""
            bar_colors = {"LARGE_CAP": "#0d9488", "MID_CAP": "#0891b2",
                          "SMALL_CAP": "#7c3aed", "MICRO_CAP": "#db2777"}
            for _, r in mcap_grp.iterrows():
                cat = str(r["MARKET_CAP_CATEGORY"])
                pct = float(r["pct"])
                color = bar_colors.get(cat, "#64748b")
                bar = f'<div style="width:{pct:.0f}%;height:8px;background:{color};border-radius:4px;display:inline-block"></div>'
                mcap_rows += (
                    f'<tr><td><strong style="color:{color}">{html_module.escape(cat)}</strong></td>'
                    f'<td>{int(r["count"])}</td>'
                    f'<td>₹{float(r["value"]):,.0f}</td>'
                    f'<td>{pct:.1f}%&nbsp;{bar}</td></tr>'
                )
            mcap_html = (
                '<div class="card-section"><h3 class="card-title">Portfolio market-cap breakdown</h3>'
                '<table class="sortable" style="margin-bottom:0"><thead><tr>'
                '<th>Category</th><th>Stocks</th><th>Value (₹)</th><th>Portfolio %</th>'
                '</tr></thead><tbody>' + mcap_rows + '</tbody></table></div>'
            )

            # Signal distribution by market cap
            sig_grp = (merged.groupby(["MARKET_CAP_CATEGORY", "TRADING_SIGNAL"])["symbol"]
                       .count().reset_index()
                       .rename(columns={"symbol": "Count"}))
            if not sig_grp.empty:
                sig_pivot = sig_grp.pivot(index="MARKET_CAP_CATEGORY", columns="TRADING_SIGNAL", values="Count").fillna(0).astype(int)
                sig_pivot = sig_pivot.reset_index()
                sig_html = (
                    '<div class="card-section" style="margin-top:16px">'
                    '<h3 class="card-title">Trading signal by market-cap tier</h3>'
                    '<div class="table-scroll">'
                    + _df_to_html_table(sig_pivot, "table-sig-mcap")
                    + '</div></div>'
                )
                mcap_html += sig_html
    except Exception as e:
        mcap_html = f'<div class="card-section"><p>Market-cap breakdown unavailable: {html_module.escape(str(e))}</p></div>'

    # ── 2. Sector breadth table ────────────────────────────────────────────
    breadth_html = ""
    breadth_path = _HERE_RPT / "data" / "sector_breadth.csv"
    try:
        if breadth_path.exists():
            sb = pd.read_csv(breadth_path)
            # Sort by pct_above_50dma desc
            if "pct_above_50dma" in sb.columns:
                sb = sb.sort_values("pct_above_50dma", ascending=False)
            # Build coloured table
            tbl = ['<table id="table-breadth" class="sortable sticky-hdr"><thead><tr>']
            for c in sb.columns:
                tbl.append(f'<th>{html_module.escape(str(c))}</th>')
            tbl.append("</tr></thead><tbody>")
            for _, r in sb.iterrows():
                tbl.append("<tr>")
                for c in sb.columns:
                    v = r.get(c, "")
                    v_str = "" if pd.isna(v) else str(v)
                    style = ""
                    if c == "pct_above_50dma":
                        try:
                            fv = float(v_str)
                            hue = 120 if fv >= 60 else 45 if fv >= 40 else 0
                            style = f'style="background:hsla({hue},65%,90%,0.6);font-weight:500"'
                        except (TypeError, ValueError):
                            pass
                    elif c == "breadth_signal":
                        color = "#15803d" if "HEALTHY" in v_str else "#dc2626" if "WEAK" in v_str else "#64748b"
                        style = f'style="color:{color};font-weight:600"'
                    elif c == "divergence_alert":
                        if v_str and v_str != "NONE":
                            style = 'style="color:#0891b2;font-weight:500"'
                    tbl.append(f'<td {style}>{html_module.escape(v_str)}</td>')
                tbl.append("</tr>")
            tbl.append("</tbody></table>")
            breadth_html = (
                '<div class="card-section" style="margin-top:16px">'
                '<h3 class="card-title">NSE sector breadth <span style="font-size:0.75rem;font-weight:400;color:var(--md-text-secondary)">— % of stocks above 50-DMA per sector</span></h3>'
                f'<input class="search-bar" type="search" placeholder="Filter sectors…" '
                f'oninput="filterTable(\'table-breadth\',this.value)">'
                '<div class="table-scroll">' + "".join(tbl) + '</div></div>'
            )
    except Exception as e:
        breadth_html = f'<div class="card-section" style="margin-top:16px"><p>Sector breadth unavailable: {html_module.escape(str(e))}</p></div>'

    # ── 3. Macro sector tailwinds ──────────────────────────────────────────
    tailwind_html = ""
    tailwind_path = _HERE_RPT / "data" / "macro_sector_tailwind.csv"
    try:
        if tailwind_path.exists():
            mt = pd.read_csv(tailwind_path)
            if "MACRO_TAILWIND" in mt.columns:
                mt = mt.sort_values("MACRO_TAILWIND", ascending=False)
            tbl = ['<table id="table-tailwind" class="sortable sticky-hdr"><thead><tr>']
            for c in mt.columns:
                tbl.append(f'<th>{html_module.escape(str(c))}</th>')
            tbl.append("</tr></thead><tbody>")
            for _, r in mt.iterrows():
                tbl.append("<tr>")
                for c in mt.columns:
                    v = r.get(c, "")
                    v_str = "" if pd.isna(v) else str(v)
                    style = ""
                    if c == "MACRO_TAILWIND":
                        try:
                            fv = float(v_str)
                            hue = 120 if fv > 1.0 else 45 if fv > 0 else 0
                            style = f'style="background:hsla({hue},65%,90%,0.6);font-weight:600"'
                        except (TypeError, ValueError):
                            pass
                    tbl.append(f'<td {style}>{html_module.escape(v_str)}</td>')
                tbl.append("</tr>")
            tbl.append("</tbody></table>")
            tailwind_html = (
                '<div class="card-section" style="margin-top:16px">'
                '<h3 class="card-title">Macro sector tailwinds <span style="font-size:0.75rem;font-weight:400;color:var(--md-text-secondary)">— higher score = stronger macro backdrop</span></h3>'
                '<div class="table-scroll">' + "".join(tbl) + '</div></div>'
            )
    except Exception as e:
        tailwind_html = f'<div class="card-section" style="margin-top:16px"><p>Macro tailwinds unavailable: {html_module.escape(str(e))}</p></div>'

    return mcap_html + breadth_html + tailwind_html


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

    # Tab: Overview — summary cards + heat tiles + 4 Chart.js charts
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
    heat_tiles_html = _build_heat_tiles_from_csvs()

    # Build chart data from technical_by_stock.csv
    import math as _math
    try:
        _tdf = pd.read_csv(TECHNICAL_BY_STOCK_CSV) if TECHNICAL_BY_STOCK_CSV.exists() else pd.DataFrame()
    except Exception:
        _tdf = pd.DataFrame()

    # 1. Decision distribution
    _dec_counts: dict = {}
    if not _tdf.empty and "recommendation" in _tdf.columns:
        for _, _r in _tdf.iterrows():
            _ts = float(_r.get("technical_score") or 50)
            _fs = _r.get("enhanced_fund_score")
            try: _fs = float(_fs) if _fs is not None and not (isinstance(_fs, float) and _math.isnan(_fs)) else 50.0
            except: _fs = 50.0
            _c = _ts * 0.6 + _fs * 0.4
            _d = ("STRONG ADD" if _c >= 70 else "ADD" if _c >= 58 else "HOLD" if _c >= 42 else "REDUCE" if _c >= 28 else "SELL")
            _dec_counts[_d] = _dec_counts.get(_d, 0) + 1
    _dec_order = ["STRONG ADD", "ADD", "HOLD", "REDUCE", "SELL"]
    _dec_vals = [_dec_counts.get(d, 0) for d in _dec_order]
    _dec_colors = ["#15803d", "#22c55e", "#ca8a04", "#ea580c", "#dc2626"]

    # 2. Market-cap breakdown by value
    _cap_map: dict = {}
    _cap_val: dict = {}
    if not _tdf.empty:
        _comp_csv = _latest_comprehensive_csv()
        if _comp_csv:
            try:
                _cdf = pd.read_csv(_comp_csv, usecols=lambda c: c.upper() in ["SYMBOL","MARKET_CAP_CATEGORY"])
                _cdf.columns = [c.upper() for c in _cdf.columns]
                if "MARKET_CAP_CATEGORY" in _cdf.columns and "SYMBOL" in _cdf.columns:
                    _cap_lookup = dict(zip(_cdf["SYMBOL"].str.upper(), _cdf["MARKET_CAP_CATEGORY"].str.upper()))
                    for _, _r in _tdf.iterrows():
                        _sym = str(_r.get("symbol","")).upper()
                        _cat = _cap_lookup.get(_sym, "UNKNOWN")
                        _val = float(_r.get("value_rs") or 0)
                        _cap_val[_cat] = _cap_val.get(_cat, 0) + _val
            except Exception:
                pass
    _cap_order = ["LARGE_CAP", "MID_CAP", "SMALL_CAP", "MICRO_CAP", "UNKNOWN"]
    _cap_labels = [c.replace("_CAP"," CAP").title() for c in _cap_order]
    _cap_vals = [_cap_val.get(c, 0) for c in _cap_order]
    _cap_colors = ["#1d4ed8","#7c3aed","#0891b2","#059669","#94a3b8"]

    # 3. Top 15 holdings by value
    if not _tdf.empty and "value_rs" in _tdf.columns:
        _top15 = _tdf.nlargest(15, "value_rs")[["symbol","value_rs"]].copy()
        _top15_labels = _top15["symbol"].tolist()
        _top15_vals = [round(float(v)/1e5, 2) for v in _top15["value_rs"].tolist()]
    else:
        _top15_labels, _top15_vals = [], []

    # 4. Tech score histogram
    _hist_buckets = [0]*5
    if not _tdf.empty and "technical_score" in _tdf.columns:
        for _s in _tdf["technical_score"].dropna():
            try:
                _idx = min(int(float(_s) / 20), 4)
                _hist_buckets[_idx] += 1
            except: pass
    _hist_labels = ["0–20","20–40","40–60","60–80","80–100"]

    _chart_data = json.dumps({
        "dec_labels": _dec_order, "dec_vals": _dec_vals, "dec_colors": _dec_colors,
        "cap_labels": _cap_labels, "cap_vals": _cap_vals, "cap_colors": _cap_colors,
        "top15_labels": _top15_labels, "top15_vals": _top15_vals,
        "hist_labels": _hist_labels, "hist_vals": _hist_buckets,
    }, ensure_ascii=False)

    overview_html = (
        '<div class="summary-grid">'
        + ov_card("Holdings", summary.get("holdings_count", "—"))
        + ov_card("Closed trades", summary.get("closed_trades_count", "—"))
        + ov_card("Total realized PnL", total_pnl, "₹")
        + ov_card("LTCG", tenure.get("LTCG", 0), "₹")
        + ov_card("STCG", tenure.get("STCG", 0), "₹")
        + ov_card("Intraday", tenure.get("intraday", 0), "₹")
        + "</div>"
        + heat_tiles_html
        + '<div class="chart-grid">'
        + '<div class="chart-card"><h4>Decision Distribution</h4><canvas id="chart-dec" height="200"></canvas></div>'
        + '<div class="chart-card"><h4>Market-Cap Breakdown (by value)</h4><canvas id="chart-cap" height="200"></canvas></div>'
        + '<div class="chart-card"><h4>Top 15 Holdings by Value (₹ Lakh)</h4><canvas id="chart-top15" height="200"></canvas></div>'
        + '<div class="chart-card"><h4>Technical Score Distribution</h4><canvas id="chart-hist" height="200"></canvas></div>'
        + '</div>'
        + f'<script type="application/json" id="chart-data-json">{_chart_data}</script>'
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

    # Tab: Sector assessment (rich data from comprehensive CSV + breadth + tailwinds)
    sector_html = _build_sector_tab()

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
    narratives_html = _narratives_to_html(narratives, escape) + _narratives_css()

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
  /* ── Markdown renderer ─────────────────────────────────────── */
  function renderMd(elId, jsonId) {{
    var j = document.getElementById(jsonId), d = document.getElementById(elId);
    if (!j || !d) return;
    try {{
      var md = JSON.parse(j.textContent);
      if (typeof marked !== 'undefined' && marked.parse) d.innerHTML = marked.parse(md);
      else {{ d.textContent = md; d.classList.add('md-fallback'); }}
    }} catch(e) {{}}
  }}
  function initMd() {{
    renderMd('overview-pnl-md','overview-pnl-json');
    renderMd('risk-scenario-md','scenario-md');
    renderMd('sentiment-md','sentiment-md-json');
    renderMd('sector-md','sector-md-json');
  }}
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded',initMd);
  else initMd();

  /* ── Chart.js Overview Charts ─────────────────────────────── */
  function initCharts() {{
    var el = document.getElementById('chart-data-json');
    if (!el || typeof Chart === 'undefined') return;
    var d;
    try {{ d = JSON.parse(el.textContent); }} catch(e) {{ return; }}
    var donutOpts = {{ responsive:true, maintainAspectRatio:true,
      plugins:{{ legend:{{ position:'right', labels:{{ boxWidth:12, font:{{ size:11 }} }} }} }} }};
    // Decision donut
    new Chart(document.getElementById('chart-dec'), {{ type:'doughnut',
      data:{{ labels:d.dec_labels, datasets:[{{ data:d.dec_vals, backgroundColor:d.dec_colors,
        borderWidth:2, borderColor:'#fff' }}] }}, options:donutOpts }});
    // Market-cap donut
    new Chart(document.getElementById('chart-cap'), {{ type:'doughnut',
      data:{{ labels:d.cap_labels, datasets:[{{ data:d.cap_vals, backgroundColor:d.cap_colors,
        borderWidth:2, borderColor:'#fff' }}] }}, options:donutOpts }});
    // Top-15 horizontal bar
    new Chart(document.getElementById('chart-top15'), {{ type:'bar',
      data:{{ labels:d.top15_labels, datasets:[{{ label:'Value (₹L)', data:d.top15_vals,
        backgroundColor:'#1976d2', borderRadius:3 }}] }},
      options:{{ indexAxis:'y', responsive:true, maintainAspectRatio:true,
        plugins:{{ legend:{{ display:false }} }},
        scales:{{ x:{{ title:{{ display:true, text:'₹ Lakh', font:{{ size:10 }} }},
          grid:{{ color:'rgba(0,0,0,0.05)' }} }}, y:{{ ticks:{{ font:{{ size:10 }} }} }} }} }} }});
    // Tech score histogram
    new Chart(document.getElementById('chart-hist'), {{ type:'bar',
      data:{{ labels:d.hist_labels, datasets:[{{ label:'# Stocks', data:d.hist_vals,
        backgroundColor:['#dc2626','#ea580c','#ca8a04','#22c55e','#15803d'],
        borderRadius:3 }}] }},
      options:{{ responsive:true, maintainAspectRatio:true,
        plugins:{{ legend:{{ display:false }} }},
        scales:{{ y:{{ title:{{ display:true, text:'Count', font:{{ size:10 }} }},
          grid:{{ color:'rgba(0,0,0,0.05)' }} }} }} }} }});
  }}
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded',initCharts);
  else initCharts();

  /* ── Tab switching + URL hash persistence ──────────────────── */
  var panels = document.querySelectorAll('.tab-panel');
  var buttons = document.querySelectorAll('.tab-btn');
  function show(id) {{
    panels.forEach(function(p){{ p.classList.remove('active'); }});
    buttons.forEach(function(b){{ b.classList.remove('active'); }});
    var p = document.getElementById('panel-'+id);
    var b = document.querySelector('[data-tab="'+id+'"]');
    if (p) p.classList.add('active');
    if (b) b.classList.add('active');
    // Clear global search when switching tabs
    var gs = document.getElementById('global-search');
    if (gs && gs.value) {{ gs.value = ''; globalSearch(''); }}
  }}
  buttons.forEach(function(b){{
    b.addEventListener('click', function(){{
      var id = b.getAttribute('data-tab');
      show(id);
      history.replaceState(null,'','#'+id);
    }});
  }});
  var hash = location.hash.replace('#','');
  if (hash && document.querySelector('[data-tab="'+hash+'"]')) show(hash);
  else if (buttons.length) show(buttons[0].getAttribute('data-tab'));

  /* ── Numeric cell parser ───────────────────────────────────── */
  function parseCellNum(txt) {{
    if (!txt) return NaN;
    var s = String(txt).replace(/[₹%,+↑↓]/g,'').trim();
    return isNaN(parseFloat(s)) ? NaN : parseFloat(s);
  }}

  /* ── Column sort ───────────────────────────────────────────── */
  function sortTable(tableId) {{
    var table = document.getElementById(tableId);
    if (!table) return;
    var headers = table.querySelectorAll('thead th');
    var body = table.querySelector('tbody');
    var sortState = {{colIndex:-1,asc:true}};
    headers.forEach(function(th, colIndex){{
      th.addEventListener('click', function(){{
        var rows = Array.from(body.querySelectorAll('tr'));
        if (!rows.length) return;
        var asc = (sortState.colIndex===colIndex) ? !sortState.asc : true;
        sortState.colIndex=colIndex; sortState.asc=asc;
        headers.forEach(function(h,i){{
          h.classList.remove('sort-asc','sort-desc');
          if(i===colIndex) h.classList.add(asc?'sort-asc':'sort-desc');
        }});
        var cellVal = function(row,ci){{ var c=row.cells[ci]; return c?c.textContent.trim():''; }};
        var isNum = rows.some(function(r){{ return !isNaN(parseCellNum(cellVal(r,colIndex))); }});
        rows.sort(function(a,b){{
          var va=cellVal(a,colIndex), vb=cellVal(b,colIndex);
          if(isNum){{
            var na=parseCellNum(va), nb=parseCellNum(vb);
            if(isNaN(na)) na=-Infinity; if(isNaN(nb)) nb=-Infinity;
            return asc?na-nb:nb-na;
          }}
          return asc?(va<vb?-1:va>vb?1:0):(vb<va?-1:vb>va?1:0);
        }});
        rows.forEach(function(r){{ body.appendChild(r); }});
        // refresh pagination after sort
        if(window._pagers&&window._pagers[tableId]) window._pagers[tableId].refresh();
      }});
    }});
  }}
  {sortable_js}

  /* ── Filter + decision filter ──────────────────────────────── */
  window._searchFilters = {{}};
  window._decFilters = {{}};

  window.filterTable = function(tableId, query) {{
    if(query!==undefined) window._searchFilters[tableId] = (query||'').toLowerCase().trim();
    var q = window._searchFilters[tableId]||'';
    var dec = (window._decFilters[tableId]||'').toLowerCase();
    var table = document.getElementById(tableId);
    if(!table) return;
    var rows = table.querySelectorAll('tbody tr');
    rows.forEach(function(row){{
      var text = row.textContent.toLowerCase();
      var matchQ = !q || text.indexOf(q)!==-1;
      var matchDec = !dec || text.indexOf(dec)!==-1;
      row.style.display = (matchQ&&matchDec)?'':'none';
      row.classList.toggle('row-match', !!(q&&matchQ&&matchDec));
    }});
    if(window._pagers&&window._pagers[tableId]) window._pagers[tableId].refresh();
  }};

  window.setDecFilter = function(tableId, dec) {{
    window._decFilters[tableId] = (dec||'').toLowerCase();
    window.filterTable(tableId, undefined);
  }};

  /* ── Narrative search / filter / sort / export ────────────── */
  var _narrDecFilter = '';
  var _narrSearchQ   = '';
  var _narrSortKey   = 'value';
  var _narrSortAsc   = false;

  function _applyNarratives() {{
    var container = document.getElementById('narratives-container');
    var empty     = document.getElementById('narratives-empty');
    if (!container) return;
    var cards = Array.from(container.querySelectorAll('.narrative-card'));
    var q   = _narrSearchQ.toLowerCase();
    var dec = _narrDecFilter.toLowerCase();
    var visible = 0;
    cards.forEach(function(c) {{
      var text = c.textContent.toLowerCase();
      var matchQ   = !q   || text.indexOf(q)   !== -1;
      var matchDec = !dec || text.indexOf(dec)  !== -1;
      c.style.display = (matchQ && matchDec) ? '' : 'none';
      if (matchQ && matchDec) visible++;
    }});
    if (empty) empty.style.display = visible ? 'none' : 'block';
    // Highlight matching cards
    cards.forEach(function(c) {{
      c.classList.toggle('row-match', !!(q && c.style.display !== 'none'));
    }});
  }}

  window.narrativeSearch = function(q) {{
    _narrSearchQ = q || '';
    // Also try routing through global search bar of other tabs
    _applyNarratives();
  }};
  window.narrativeFilter = function(dec) {{
    _narrDecFilter = dec || '';
    _applyNarratives();
  }};
  window.narrativeSort = function(key) {{
    _narrSortAsc = (_narrSortKey === key) ? !_narrSortAsc : false;
    _narrSortKey = key;
    var container = document.getElementById('narratives-container');
    if (!container) return;
    var cards = Array.from(container.querySelectorAll('.narrative-card'));
    var sortVal = function(c) {{
      if (key === 'value')    return parseFloat(c.dataset.val  || 0);
      if (key === 'tech')     return parseFloat(c.dataset.tech || 0);
      if (key === 'decision') return parseInt(c.dataset.decord || 5);
      if (key === 'alpha')    return c.dataset.sym || '';
      return 0;
    }};
    cards.sort(function(a, b) {{
      var va = sortVal(a), vb = sortVal(b);
      if (typeof va === 'string') return _narrSortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
      return _narrSortAsc ? va - vb : vb - va;
    }});
    cards.forEach(function(c) {{ container.appendChild(c); }});
  }};
  window.exportNarratives = function() {{
    var el = document.getElementById('narratives-export-data');
    if (!el) return;
    try {{
      var rows = JSON.parse(el.textContent);
      var headers = Object.keys(rows[0]);
      var csv = [headers.map(function(h){{return '"'+h+'"';}}).join(',')];
      rows.forEach(function(r) {{
        csv.push(headers.map(function(h){{return '"'+String(r[h]||'').replace(/"/g,'""')+'"';}}).join(','));
      }});
      var a = document.createElement('a');
      a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv.join('\\n'));
      a.download = 'stock_narratives.csv'; a.click();
    }} catch(e) {{}}
  }};

  /* ── Global search routes to active tab ───────────────────── */
  window.globalSearch = function(q) {{
    var activePanel = document.querySelector('.tab-panel.active');
    if(!activePanel) return;
    // Narrative tab has its own search function
    if(activePanel.id === 'panel-narratives') {{
      var ns = document.getElementById('search-narratives');
      if(ns) {{ ns.value = q; narrativeSearch(q); }}
      return;
    }}
    var bar = activePanel.querySelector('.search-bar');
    if(bar) {{
      bar.value = q;
      bar.dispatchEvent(new Event('input'));
    }}
  }};

  /* ── Keyboard shortcut ─────────────────────────────────────── */
  document.addEventListener('keydown', function(e){{
    if((e.ctrlKey||e.metaKey)&&e.key==='k'){{
      e.preventDefault();
      var gs = document.getElementById('global-search');
      if(gs) gs.focus();
    }}
  }});

  /* ── Pagination ────────────────────────────────────────────── */
  window._pagers = {{}};
  window.initPagination = function(tableId, pageSize) {{
    var table = document.getElementById(tableId);
    if(!table) return;
    var container = table.closest('.table-scroll') || table.parentNode;
    var pagerEl = document.createElement('div');
    pagerEl.className = 'pager'; pagerEl.id = 'pager-'+tableId;
    container.parentNode.insertBefore(pagerEl, container.nextSibling);
    var state = {{page:0, pageSize:pageSize}};
    function visibleRows(){{ return Array.from(table.querySelectorAll('tbody tr')).filter(function(r){{ return r.style.display!=='none'; }}); }}
    function render(){{
      var rows = visibleRows();
      var total = rows.length;
      var pages = Math.ceil(total/state.pageSize)||1;
      state.page = Math.min(state.page, pages-1);
      rows.forEach(function(r,i){{ r.style.display = (Math.floor(i/state.pageSize)===state.page)?'':'none'; }});
      pagerEl.innerHTML='';
      if(pages<=1) return;
      var info=document.createElement('span'); info.className='pg-info';
      info.textContent=(state.page*state.pageSize+1)+'–'+Math.min((state.page+1)*state.pageSize,total)+' of '+total;
      pagerEl.appendChild(info);
      function mkBtn(label, disabled, onClick){{
        var btn=document.createElement('button'); btn.textContent=label; btn.disabled=disabled;
        btn.addEventListener('click',onClick); return btn;
      }}
      pagerEl.appendChild(mkBtn('‹',state.page===0,function(){{state.page--;render();}}));
      var sp=Math.max(0,state.page-3), ep=Math.min(pages-1,sp+6);
      for(var p=sp;p<=ep;p++){{
        (function(pg){{
          var btn=mkBtn(pg+1,false,function(){{state.page=pg;render();}});
          if(pg===state.page) btn.classList.add('pg-active');
          pagerEl.appendChild(btn);
        }})(p);
      }}
      pagerEl.appendChild(mkBtn('›',state.page>=pages-1,function(){{state.page++;render();}}));
    }}
    window._pagers[tableId]={{refresh:function(){{state.page=0;render();}}}};
    render();
  }};

  /* ── Export CSV ────────────────────────────────────────────── */
  window.exportCSV = function(tableId, filename) {{
    var table = document.getElementById(tableId);
    if(!table) return;
    var rows = [];
    var headers = Array.from(table.querySelectorAll('thead th')).map(function(th){{
      return '"'+th.textContent.trim().replace(/"/g,'""')+'"';
    }});
    rows.push(headers.join(','));
    table.querySelectorAll('tbody tr').forEach(function(tr){{
      if(tr.style.display==='none') return;
      var cells = Array.from(tr.querySelectorAll('td')).map(function(td){{
        return '"'+td.textContent.trim().replace(/"/g,'""')+'"';
      }});
      rows.push(cells.join(','));
    }});
    var a=document.createElement('a');
    a.href='data:text/csv;charset=utf-8,'+encodeURIComponent(rows.join('\\n'));
    a.download=(filename||tableId)+'.csv'; a.click();
  }};

  /* ── Column toggle ─────────────────────────────────────────── */
  window.toggleColPanel = function(panelId) {{
    var p=document.getElementById(panelId);
    if(p) p.classList.toggle('visible');
    document.addEventListener('click',function handler(e){{
      if(!p||!p.contains(e.target)&&!e.target.closest('.col-toggle-btn')){{
        p&&p.classList.remove('visible');
        document.removeEventListener('click',handler);
      }}
    }});
  }};
  window.toggleCol = function(tableId, colIdx, visible) {{
    var table = document.getElementById(tableId);
    if(!table) return;
    table.querySelectorAll('tr').forEach(function(row){{
      var cell = row.cells[colIdx];
      if(cell) cell.style.display = visible?'':'none';
    }});
  }};

  /* ── Init pagination for large tables ─────────────────────── */
  document.addEventListener('DOMContentLoaded', function(){{
    initPagination('table-holdings', 50);
    initPagination('table-closed-pnl', 30);
    initPagination('table-fundamental', 50);
    initPagination('table-technical', 50);
  }});
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
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
{REPORT_CSS}
</style>
</head>
<body>
<header class="app-bar">
  <div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:8px">
    <div>
      <h1>Portfolio – Comprehensive Report</h1>
      <p class="meta">Report date: {today} &nbsp;·&nbsp; Account: {html_module.escape(account)} &nbsp;·&nbsp; Data as of: {data_as_of}</p>
    </div>
    <div class="app-bar-row">
      <div class="global-search-wrap">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
        <input id="global-search" type="search" class="global-search" placeholder="Search all… (⌘K)"
          oninput="globalSearch(this.value)" onkeydown="if(event.key==='Escape'){{this.value='';globalSearch('');}}">
      </div>
      <span class="kbd-hint">⌘K to focus</span>
    </div>
  </div>
</header>
<main class="main-content">
  <div class="tabs" role="tablist">{tab_buttons}</div>
  {tab_panels}
</main>
{script}
</body>
</html>"""


def run_phase6() -> dict:
    """Run Phase 6: build comprehensive HTML report."""
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    html_content = build_report_html_structured()
    REPORT_HTML.write_text(html_content, encoding="utf-8")
    return {"report_html": str(REPORT_HTML)}


if __name__ == "__main__":
    run_phase6()
    print("Phase 6 done.", REPORT_MD, REPORT_HTML)
