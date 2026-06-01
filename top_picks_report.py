"""
top_picks_report.py — Top Investment Picks Analysis report generator.

Picks the highest-conviction 10 stocks by merging the latest Sector Rotation
Report candidate set with the latest Stage-2 tracker snapshot, then runs a
deep technical + fundamental deep dive per stock and produces an LLM-narrated
report styled identically to the Sector Rotation Report.

CLI:
    python top_picks_report.py                # full run (LLM if OPENAI_API_KEY set)
    python top_picks_report.py --no-llm       # rule-based narrative only
    python top_picks_report.py --dry-run      # plan only, no writes
    python top_picks_report.py --date 2026-05-29   # override snapshot date

Outputs:
    reports/top_picks/Top_Investment_Picks_Analysis_YYYYMMDD.md
    reports/top_picks/Top_Investment_Picks_Analysis_YYYYMMDD.html
    reports/latest/top_picks.{md,html}
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import psycopg2
from psycopg2.extras import RealDictCursor

def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(path, override=False)
        return
    except Exception:
        pass
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


ROOT = Path(__file__).resolve().parent
_load_dotenv(ROOT / ".env")
if ROOT.parent.name == ".worktrees":
    _load_dotenv(ROOT.parent.parent / ".env")

# Reuse theme + LLM helper from the sector rotation report so look & feel and
# JSON-parsing semantics stay in lock-step with the rest of the suite.
from sector_rotation_report import (  # noqa: E402
    _CSS,
    AGENT_BRAND,
    REPORT_DISCLAIMER,
    PRINT_FOOTER_DISCLAIMER,
    FULL_LEGAL_DISCLAIMER,
    _llm_call,
    _asset_data_uri,
    AGENT_LOGO_PATH,
)

REPORTS_DIR = ROOT / "reports"
TOP_PICKS_DIR = REPORTS_DIR / "top_picks"
LATEST_DIR = REPORTS_DIR / "latest"
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
MAX_PICKS = 10
PG_DSN = (
    os.environ.get("AGENT_ADDA_PG_DSN")
    or os.environ.get("PG_DSN")
    or "dbname=nse_market user=nse_admin host=/tmp"
)


# ─────────────────────────────────────────────────────────────────────────────
# TradingView-style crosshair / OHLC hover tooltip (one shared script for all
# `.tp-tv-chart` SVGs in the report). Reads bar + indicator data from a JSON
# <script> emitted by `_svg_candlestick` with matching `{chart_id}-data` id.
# ─────────────────────────────────────────────────────────────────────────────
TV_CROSSHAIR_JS = """
<script>
(function(){
  function wire(svg){
    const id = svg.id;
    const dataEl = document.getElementById(id + "-data");
    if (!dataEl) return;
    let payload; try { payload = JSON.parse(dataEl.textContent); } catch(e){ return; }
    const bars = payload.bars || [];
    if (!bars.length) return;
    const padL = +svg.dataset.padL, padT = +svg.dataset.padT;
    const cw = +svg.dataset.chartW, ph = +svg.dataset.priceH;
    const pmin = +svg.dataset.pMin, pmax = +svg.dataset.pMax;
    const N = +svg.dataset.n;
    const area = svg.querySelector(".cx-area");
    const grp = svg.querySelector(".cx-hover");
    if (!area || !grp) return;
    const vline = grp.querySelector(".cx-v");
    const hline = grp.querySelector(".cx-h");
    const ptag  = grp.querySelector(".cx-pricetag");
    const ptxt  = grp.querySelector(".cx-pricetxt");
    const dtag  = grp.querySelector(".cx-datetag");
    const dtxt  = grp.querySelector(".cx-datetxt");
    const tip   = grp.querySelector(".cx-tooltip");
    const tipBg = grp.querySelector(".cx-tipbg");
    const tipTxt= grp.querySelector(".cx-tiptxt");

    const xFor = i => padL + (i + 0.5) * (cw / N);
    const iForX = x => Math.max(0, Math.min(N-1, Math.round((x - padL)/(cw/N) - 0.5)));
    const yPrice = v => padT + (pmax - v)/(pmax - pmin) * ph;
    const priceForY = y => pmax - (y - padT)/ph * (pmax - pmin);
    const fmt = (v, d=2) => v==null ? '—' : Number(v).toLocaleString('en-IN',{minimumFractionDigits:d, maximumFractionDigits:d});
    const fmtV = v => v==null ? '—' : Number(v).toLocaleString('en-IN');

    function svgCoord(evt){
      const pt = svg.createSVGPoint();
      pt.x = evt.clientX; pt.y = evt.clientY;
      const ctm = svg.getScreenCTM().inverse();
      return pt.matrixTransform(ctm);
    }
    function onMove(evt){
      const p = svgCoord(evt);
      if (p.x < padL || p.x > padL + cw) { grp.setAttribute("visibility","hidden"); return; }
      const i = iForX(p.x);
      const b = bars[i]; if (!b) return;
      const cx = xFor(i);
      grp.setAttribute("visibility","visible");
      vline.setAttribute("x1", cx); vline.setAttribute("x2", cx);
      const yClamp = Math.max(padT, Math.min(padT+ph, p.y));
      hline.setAttribute("y1", yClamp); hline.setAttribute("y2", yClamp);
      ptag.setAttribute("y", yClamp - 7);
      ptxt.setAttribute("y", yClamp + 3.5);
      ptxt.textContent = fmt(priceForY(yClamp));
      // date tag
      dtag.setAttribute("x", cx - 30);
      dtxt.setAttribute("x", cx);
      dtxt.textContent = b.d;
      // tooltip box
      const chg = b.c - b.o, chgPct = b.o ? chg/b.o*100 : 0;
      const e20 = (payload.ema20  || [])[i];
      const e50 = (payload.ema50  || [])[i];
      const e200= (payload.ema200 || [])[i];
      const rsi = (payload.rsi    || [])[i];
      const upC = "#26a69a", dnC = "#ef5350";
      const cCol = chg >= 0 ? upC : dnC;
      // multi-line text using tspans
      tipTxt.innerHTML =
        `<tspan x="8" dy="0" font-weight="800" fill="#f0f3fa">${b.d}</tspan>` +
        `<tspan x="8" dy="14"><tspan fill="#787b86">O</tspan> ${fmt(b.o)}  ` +
          `<tspan fill="#787b86">H</tspan> ${fmt(b.h)}</tspan>` +
        `<tspan x="8" dy="14"><tspan fill="#787b86">L</tspan> ${fmt(b.l)}  ` +
          `<tspan fill="#787b86">C</tspan> <tspan fill="${cCol}" font-weight="700">${fmt(b.c)}</tspan></tspan>` +
        `<tspan x="8" dy="14" fill="${cCol}" font-weight="700">${chg>=0?'+':''}${fmt(chg)} (${chg>=0?'+':''}${fmt(chgPct)}%)</tspan>` +
        `<tspan x="8" dy="14"><tspan fill="#787b86">Vol</tspan> ${fmtV(b.v)}</tspan>` +
        `<tspan x="8" dy="14"><tspan fill="#ffb74d">EMA20</tspan> ${fmt(e20)}  ` +
          `<tspan fill="#42a5f5">EMA50</tspan> ${fmt(e50)}</tspan>` +
        `<tspan x="8" dy="14"><tspan fill="#ab47bc">EMA200</tspan> ${fmt(e200)}  ` +
          `<tspan fill="#e879f9">RSI</tspan> ${fmt(rsi,1)}</tspan>`;
      // position tooltip — flip to left of cursor if too close to right edge
      const tipW = 180, tipH = 122;
      let tx = cx + 10, ty = Math.max(padT+4, Math.min(p.y - 60, padT+ph - tipH - 4));
      if (tx + tipW > padL + cw + 60) tx = cx - tipW - 10;
      tipBg.setAttribute("width", tipW);
      tipBg.setAttribute("height", tipH);
      tip.setAttribute("transform", `translate(${tx},${ty})`);
    }
    function onLeave(){ grp.setAttribute("visibility","hidden"); }
    area.addEventListener("mousemove", onMove);
    area.addEventListener("mouseleave", onLeave);
    // Also capture moves over candles/EMAs (which sit above the area otherwise)
    svg.addEventListener("mousemove", function(e){
      // only handle if pointer is inside chart panel
      const p = svgCoord(e);
      if (p.x >= padL && p.x <= padL+cw && p.y >= padT && p.y <= padT+ph) onMove(e);
    });
    svg.addEventListener("mouseleave", onLeave);
  }
  function init(){ document.querySelectorAll("svg.tp-tv-chart").forEach(wire); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
</script>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Visual layer — extra CSS + inline SVG charting helpers
# ─────────────────────────────────────────────────────────────────────────────

# Plain-language definitions surfaced as hover tooltips on KPI / metric labels.
# Keys match the labels used in rows_tech / rows_fund / rows_val / rows_subscore.
# Lookup also tries the label with trailing "(...)" qualifiers stripped, so
# variants like "Piotroski F-score" and "Beneish M-score (simplified)" both hit.
_METRIC_TOOLTIPS: dict[str, str] = {
    # ── Technicals
    "Close": "Last traded close price on the snapshot date.",
    "EMA 20/50/200": "Exponential moving averages over 20, 50 and 200 trading days. Price stacked above all three (and EMAs in 20>50>200 order) signals a healthy uptrend.",
    "EMA50 slope (20d)": "Percent change in the 50-day EMA over the last 20 trading days. Positive = trend strengthening, negative = trend rolling over.",
    "RSI(14)": "Relative Strength Index, 14-day. >70 overbought, <30 oversold, 50 is neutral momentum.",
    "ATR(14)": "Average True Range, 14-day — typical daily price swing in rupees. Higher ATR = higher volatility; used to size stop-losses.",
    "52W High / Low": "Highest and lowest closing prices over the last 52 weeks.",
    "From 52W high": "How far the current price is below its 52-week high. Names within 10–15% of high tend to have stronger momentum.",
    "Returns 1M/3M/6M/1Y": "Price-only total returns over 1/3/6/12 months. Dividends not included.",
    "Vol vs 20d avg": "Latest day's traded volume divided by 20-day average. >1.5x = unusually active.",
    # ── Fundamentals
    "Piotroski F-score": "Piotroski F-score (0–9): 9 binary checks on profitability, leverage and operating efficiency. ≥7 strong, ≤3 weak. We approximate from BS/PnL/CF when not stored.",
    "Altman Z-score": "Altman Z (or Z' for non-listed) bankruptcy-risk score. >3 safe, 1.8–3 grey zone, <1.8 distress.",
    "Beneish M-score": "Beneish M-score earnings-manipulation probability. <-2.22 low risk, -2.22 to -1.78 watch, >-1.78 elevated. Simplified version uses 5 of 8 inputs computable from our data.",
    "Forensic risk": "Composite forensic-quality tier (low / moderate / high) blending Beneish flag, Piotroski strength, OCF/PAT earnings quality, leverage and aggressive-growth signals.",
    "ROE / ROCE": "Return on Equity = PAT / shareholders' equity. ROCE = EBIT / capital employed. >15% healthy, >20% excellent.",
    "Revenue growth (3Y)": "Compound annual growth rate of revenue over the last 3 fiscal years.",
    "PAT growth (3Y)": "Compound annual growth rate of net profit (PAT) over the last 3 fiscal years.",
    "Debt / Equity": "Total debt ÷ total equity. <0.5 conservative, 0.5–1 moderate, >1 leveraged, >2 high risk.",
    "Promoter holding": "Share of equity held by promoters (founders/controlling shareholders). Rising = positive signal, falling = caution flag.",
    "FII / DII holding": "Foreign Institutional Investor and Domestic Institutional Investor ownership percentages. Heavy institutional backing signals quality conviction.",
    "NPM": "Net Profit Margin = PAT ÷ Revenue. Sector-relative; software/pharma 15–25%, manufacturing 5–12%.",
    "EPS": "Earnings Per Share (latest fiscal year). Drives the P/E denominator.",
    # ── Valuation
    "Price": "Current market price (snapshot date close).",
    "EPS (TTM proxy)": "Trailing earnings per share proxy from screener.in ratios. Used as P/E denominator.",
    "P/E (price ÷ EPS)": "Price-to-Earnings ratio. Compare to sector median; lower can mean cheap or low-growth, higher can mean growth or over-extension.",
    "Market-cap bucket": "Size bucket — Large (>₹20k Cr), Mid (₹5–20k Cr), Small (<₹5k Cr). Affects liquidity and risk.",
    "Sales (latest)": "Revenue for the most recent reported quarter (or year), with YoY change.",
    "PAT (latest)": "Net profit for the most recent reported quarter (or year), with YoY change.",
    "Net debt (3Y)": "Total debt minus cash, latest balance sheet. Negative = net cash position.",
    # ── Sub-scores / composite
    "Earnings Quality": "Quality of reported earnings (0–10): OCF/PAT conversion, working-capital discipline, non-recurring items, Beneish flag.",
    "Sales Growth": "Revenue growth strength & consistency (0–10): 3Y CAGR, recent quarter YoY/QoQ, growth durability.",
    "Financial Strength": "Balance-sheet resilience (0–10): D/E, interest cover, current ratio, Piotroski, Altman Z, debt trend.",
    "Institutional": "Institutional backing (0–10): FII + DII holdings, promoter holding stability, recent block/bulk-deal activity.",
    "Composite": "Blended 0–100 enhanced fundamental score combining the four sub-scores plus growth & quality overlays.",
    "CANSLIM (O'Neil)": "William O'Neil CANSLIM score (0–25): C=current earnings, A=annual earnings, N=new highs/products, S=supply/demand, L=leader vs laggard, I=institutional sponsorship, M=market direction.",
    "Minervini Trend": "Mark Minervini stage-2 uptrend template score (0–8): 8 trend-template checks on price vs EMAs, 52w distance, RSI relative strength.",
    # CANSLIM component-level tooltips (used by the per-stock breakdown)
    "CANSLIM-C": "C — Current quarterly earnings (0–5). Tier 1: PAT YoY from scores.quarterly_results. Tier 2: pat_yoy_pct from fund_details pnl_summary. Tier 3: quarterly trend from fund_details. Tier 4 (⚠ proxy): 20-day price momentum — only fires when no financial data is available at all.",
    "CANSLIM-A": "A — Annual earnings growth (0–5). Tier 1: PAT CAGR from scores.annual_results. Tier 2: pat_yoy_pct from fund_details (1Y growth). Tier 3: TTM 4Q vs prior 4Q. Tier 4 (⚠ proxy): 3-month price momentum — only fires when no financial data is available at all.",
    "CANSLIM-N": "N — New highs / new products (0–5). Proxy using volume surge (>2x 20d avg = 5) or distance from 52-week high (within 5% = 5, within 15% = 3).",
    "CANSLIM-S": "S — Supply & demand (0–5). EMA stack — Price > EMA50 > EMA200 (full stack) = 5; partial stack = 3; price > EMA200 only = 1; below = 0.",
    "CANSLIM-L": "L — Leader vs Laggard (0–5). Relative strength vs Nifty 500: >10pp outperformance = 5, >5pp = 3, positive = 1.",
    "CANSLIM-I": "I — Institutional sponsorship (0–5, informational, not in 25-pt total). Combined FII + DII ownership: >30% = 5, >15% = 3, >5% = 1.",
    "CANSLIM-M": "M — Market direction (0–5, informational, not in 25-pt total). Broad-market regime context (bull / neutral / bear).",
}


_EXTRA_CSS = """
/* ===== Top Picks enhancements (overrides + additions on top of _CSS) ===== */
:root{
  --tp-ink:#0f172a; --tp-ink-soft:#334155; --tp-mute:#64748b; --tp-line:#e2e8f0;
  --tp-bg:#f8fafc; --tp-card:#ffffff; --tp-blue:#1e3a5f; --tp-blue2:#2563eb;
  --tp-teal:#0f766e; --tp-violet:#7c3aed; --tp-amber:#d97706; --tp-green:#16a34a;
  --tp-red:#b91c1c;
  --tp-radius:14px;
}
body{
  font-family:'Inter','Segoe UI',-apple-system,BlinkMacSystemFont,Roboto,sans-serif;
  font-feature-settings:"tnum","ss01"; color:var(--tp-ink);
}
/* Sticky TOC has top:8px + ~52px height ≈ 60px reserved so anchor jumps don't hide under it. */
html{scroll-padding-top:72px;scroll-behavior:smooth}
:target{scroll-margin-top:72px}
.tp-hero{
  margin:0; padding:32px 28px 26px;
  background: radial-gradient(1200px 320px at 10% -20%, rgba(37,99,235,.32), transparent 60%),
              radial-gradient(900px 260px at 90% 0%, rgba(124,58,237,.28), transparent 65%),
              linear-gradient(135deg,#0b1d3a 0%,#1e3a5f 55%,#0f766e 100%);
  color:#f8fafc; border-radius:0 0 var(--tp-radius) var(--tp-radius);
  box-shadow:0 18px 40px -22px rgba(15,23,42,.55);
  position:relative; overflow:hidden;
}
.tp-hero::after{
  content:""; position:absolute; inset:0; pointer-events:none;
  background-image: linear-gradient(rgba(255,255,255,.04) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(255,255,255,.04) 1px, transparent 1px);
  background-size: 24px 24px; opacity:.5;
}
.tp-hero-row{display:flex;justify-content:space-between;align-items:flex-start;gap:24px;flex-wrap:wrap;position:relative;z-index:1}
.tp-hero-kicker{font-size:.78rem;letter-spacing:.18em;text-transform:uppercase;color:#cbd5e1;font-weight:600}
.tp-hero-title{font-size:2.05rem;line-height:1.1;font-weight:800;margin:6px 0 4px;letter-spacing:-.01em}
.tp-hero-sub{font-size:.95rem;color:#dbeafe;max-width:640px}
.tp-hero-meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.tp-pill{
  display:inline-flex;align-items:center;gap:6px;
  background:rgba(255,255,255,.12);backdrop-filter:blur(6px);
  border:1px solid rgba(255,255,255,.2); color:#f1f5f9;
  font-size:.72rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
  padding:5px 11px;border-radius:999px;
}
.tp-pill.green{background:rgba(22,163,74,.25);border-color:rgba(22,163,74,.45)}
.tp-pill.blue{background:rgba(37,99,235,.25);border-color:rgba(37,99,235,.45)}
.tp-pill.violet{background:rgba(124,58,237,.28);border-color:rgba(124,58,237,.5)}
.tp-pill.amber{background:rgba(217,119,6,.28);border-color:rgba(217,119,6,.5)}
.tp-pill.red{background:rgba(185,28,28,.3);border-color:rgba(185,28,28,.5)}

.tp-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:22px 0 0;position:relative;z-index:1}
.tp-kpi{
  background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.18);
  padding:12px 14px; border-radius:12px;
}
.tp-kpi-lbl{font-size:.7rem;letter-spacing:.14em;text-transform:uppercase;color:#cbd5e1;font-weight:600}
.tp-kpi-val{font-size:1.55rem;font-weight:800;line-height:1.1;margin-top:4px;color:#fff}
.tp-kpi-sub{font-size:.72rem;color:#dbeafe;margin-top:2px}

/* TOC strip */
.tp-toc{
  display:flex;flex-wrap:wrap;gap:6px;
  padding:10px 14px;margin:18px 0 0;
  background:#fff;border:1px solid var(--tp-line);border-radius:12px;
  box-shadow:0 4px 14px -10px rgba(15,23,42,.25);
  position:sticky;top:8px;z-index:30;
}
.tp-toc-title{font-size:.7rem;letter-spacing:.14em;text-transform:uppercase;color:var(--tp-mute);font-weight:700;align-self:center;margin-right:6px}
.tp-toc a{
  display:inline-flex;align-items:center;gap:5px;
  padding:5px 10px;border-radius:8px;background:#f1f5f9;
  font-size:.78rem;font-weight:600;color:var(--tp-blue);text-decoration:none;
  border:1px solid transparent;transition:all .15s ease;
}
.tp-toc a:hover{background:var(--tp-blue);color:#fff;border-color:var(--tp-blue)}
.tp-toc a .num{font-size:.65rem;background:rgba(30,58,95,.12);padding:1px 6px;border-radius:6px;color:var(--tp-blue);font-weight:700}
.tp-toc a:hover .num{background:rgba(255,255,255,.25);color:#fff}

/* Stock cards */
.tp-card{
  background:#fff;border:1px solid var(--tp-line);border-radius:var(--tp-radius);
  padding:0;margin:14px 0 18px;overflow:hidden;
  box-shadow:0 6px 22px -16px rgba(15,23,42,.25);
}
.tp-card-hd{
  padding:16px 20px;
  background:linear-gradient(135deg,#f8fafc 0%,#eef2f7 100%);
  border-bottom:1px solid var(--tp-line);
  display:flex;align-items:center;gap:14px;flex-wrap:wrap;
}
.tp-card-num{
  width:38px;height:38px;border-radius:10px;
  background:linear-gradient(135deg,var(--tp-blue),var(--tp-blue2));
  color:#fff;font-weight:800;display:flex;align-items:center;justify-content:center;font-size:1.05rem;
  box-shadow:0 6px 14px -8px rgba(37,99,235,.55);
}
.tp-card-name{font-size:1.3rem;font-weight:800;color:var(--tp-blue);margin:0;letter-spacing:-.01em}
.tp-card-name small{color:var(--tp-mute);font-weight:500;font-size:.85rem;margin-left:6px}
.tp-card-bd{padding:18px 20px 20px}
.tp-card .stripe{height:4px;background:linear-gradient(90deg,var(--tp-blue2),var(--tp-violet),var(--tp-amber),var(--tp-green))}

/* Hero KPI row inside each card */
.tp-kpi-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin:0 0 14px}
.tp-kpi-tile{
  border:1px solid var(--tp-line);border-radius:10px;padding:10px 12px;
  background:#fff;position:relative;overflow:hidden;
}
.tp-kpi-tile::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--tp-blue2)}
.tp-kpi-tile.green::before{background:var(--tp-green)}
.tp-kpi-tile.red::before{background:var(--tp-red)}
.tp-kpi-tile.amber::before{background:var(--tp-amber)}
.tp-kpi-tile.violet::before{background:var(--tp-violet)}
.tp-kpi-tile .lbl{font-size:.66rem;letter-spacing:.12em;text-transform:uppercase;color:var(--tp-mute);font-weight:700}
.tp-kpi-tile .val{font-size:1.15rem;font-weight:800;color:var(--tp-ink);margin-top:3px}
.tp-kpi-tile .sub{font-size:.7rem;color:var(--tp-mute);margin-top:2px}

/* Sectioned sub-cards */
.tp-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin-top:12px}
.tp-sub{background:#fafbfd;border:1px solid var(--tp-line);border-radius:10px;padding:12px 14px}
.tp-sub h4{margin:0 0 8px;font-size:.78rem;letter-spacing:.1em;text-transform:uppercase;color:var(--tp-blue);font-weight:700;display:flex;align-items:center;gap:6px}
.tp-sub .ico{display:inline-block;width:18px;height:18px;border-radius:5px;background:var(--tp-blue);color:#fff;font-size:11px;line-height:18px;text-align:center;font-weight:800}
.tp-sub.ok{background:#ecfdf5;border-color:#a7f3d0}
.tp-sub.ok h4{color:#047857} .tp-sub.ok .ico{background:#047857}
.tp-sub.warn{background:#fff7ed;border-color:#fed7aa}
.tp-sub.warn h4{color:#b45309} .tp-sub.warn .ico{background:#b45309}
.tp-sub.bad{background:#fef2f2;border-color:#fecaca}
.tp-sub.bad h4{color:#991b1b} .tp-sub.bad .ico{background:#991b1b}
.tp-sub.violet{background:#f5f3ff;border-color:#ddd6fe}
.tp-sub.violet h4{color:#5b21b6} .tp-sub.violet .ico{background:#5b21b6}
.tp-sub.teal{background:#f0fdfa;border-color:#99f6e4}
.tp-sub.teal h4{color:#0f766e} .tp-sub.teal .ico{background:#0f766e}

/* Tables */
.tp-tbl{width:100%;border-collapse:separate;border-spacing:0;font-size:.83rem}
.tp-tbl th{
  text-align:left;font-size:.66rem;letter-spacing:.1em;text-transform:uppercase;
  color:var(--tp-mute);font-weight:700;padding:8px 10px;background:#f8fafc;
  border-bottom:1px solid var(--tp-line);
}
.tp-tbl td{padding:8px 10px;border-bottom:1px solid #f1f5f9;color:var(--tp-ink)}
.tp-tbl tr:last-child td{border-bottom:none}
.tp-tbl tr:hover td{background:#f8fafc}
.tp-tbl td.num{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
.tp-kv td{padding:6px 8px;font-size:.82rem}
.tp-kv td:first-child{color:var(--tp-mute);font-weight:500}
.tp-kv td:last-child{text-align:right;font-weight:700;font-variant-numeric:tabular-nums}
/* Info-tooltip icon for KPI/metric labels (TradingView-style) */
.tp-info{
  display:inline-block;width:13px;height:13px;line-height:13px;text-align:center;
  font-size:9px;font-weight:700;font-family:Georgia,serif;font-style:italic;
  color:#64748b;background:#e2e8f0;border-radius:50%;margin-left:5px;
  cursor:help;user-select:none;vertical-align:1px;
  transition:background .15s,color .15s;
}
.tp-info:hover{background:#0ea5e9;color:#fff}
/* CANSLIM component breakdown */
.cs-box{display:flex;flex-direction:column;gap:6px}
.cs-row{display:grid;grid-template-columns:30px 1fr 48px;gap:8px;align-items:center;padding:4px 0;border-bottom:1px dotted #e9d5ff}
.cs-row:last-of-type{border-bottom:none}
.cs-key{font-weight:800;color:#5b21b6;font-size:.95rem;text-align:center;background:#ede9fe;border-radius:4px;padding:3px 0}
.cs-name{font-size:.74rem;font-weight:600;color:#334155}
.cs-detail{font-size:.7rem;color:#64748b;margin-top:1px}
.cs-track{margin-top:4px;height:5px;background:#ede9fe;border-radius:99px;overflow:hidden}
.cs-fill{height:100%;background:#a78bfa;border-radius:99px;transition:width .3s ease}
.cs-fill.green{background:linear-gradient(90deg,#10b981,#16a34a)}
.cs-fill.amber{background:linear-gradient(90deg,#f59e0b,#d97706)}
.cs-fill.red{background:linear-gradient(90deg,#ef4444,#b91c1c)}
.cs-score{font-variant-numeric:tabular-nums;font-weight:700;color:#5b21b6;font-size:.82rem;text-align:right}
/* Analyst / Street Consensus pane */
.ac-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}
.ac-tile{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:10px 12px}
.ac-cap{font-size:.65rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#64748b;margin-bottom:5px}
.ac-val{font-size:1.05rem;font-weight:800;color:#0f172a;font-variant-numeric:tabular-nums}
.ac-sub{font-size:.72rem;color:#475569;margin-top:2px}
.ac-rationale{margin:10px 0 0;font-size:.78rem;color:#475569;font-style:italic;background:#fff;border-left:3px solid #94a3b8;padding:6px 10px;border-radius:0 4px 4px 0}
.ac-bullbear{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}
.ac-side{background:#fff;border-radius:8px;padding:10px 12px;border:1px solid #e2e8f0}
.ac-side.bull{border-left:3px solid #16a34a}
.ac-side.bear{border-left:3px solid #ef4444}
.ac-side ul{margin:6px 0 0 18px;padding:0;font-size:.78rem;color:#334155;line-height:1.55}
.ac-side li{margin-bottom:3px}
.ac-disc{margin:10px 0 0;font-size:.7rem;color:#94a3b8;line-height:1.4}
@media (max-width:640px){.ac-bullbear{grid-template-columns:1fr}}

/* Score / sub-score horizontal bars */
.tp-bar{display:flex;align-items:center;gap:8px;margin:4px 0}
.tp-bar .lab{flex:0 0 130px;font-size:.78rem;color:var(--tp-ink-soft)}
.tp-bar .trk{flex:1;height:8px;background:#e2e8f0;border-radius:999px;overflow:hidden;position:relative}
.tp-bar .fill{height:100%;background:linear-gradient(90deg,var(--tp-blue2),var(--tp-teal));border-radius:999px;transition:width .3s ease}
.tp-bar .fill.green{background:linear-gradient(90deg,#10b981,#16a34a)}
.tp-bar .fill.amber{background:linear-gradient(90deg,#f59e0b,#d97706)}
.tp-bar .fill.red{background:linear-gradient(90deg,#ef4444,#b91c1c)}
.tp-bar .val{flex:0 0 48px;text-align:right;font-size:.78rem;font-weight:700;font-variant-numeric:tabular-nums;color:var(--tp-ink)}

/* Gauge */
.tp-gauge{display:flex;align-items:center;gap:14px}
.tp-gauge-num{font-size:2.6rem;font-weight:800;line-height:1;font-variant-numeric:tabular-nums}
.tp-gauge-num small{font-size:.95rem;color:var(--tp-mute);font-weight:600}
.tp-gauge-tier{margin-top:4px;font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;font-weight:800}

/* Summary master table */
.tp-master{
  width:100%;border-collapse:separate;border-spacing:0;font-size:.85rem;
  background:#fff;border:1px solid var(--tp-line);border-radius:12px;overflow:hidden;
  box-shadow:0 4px 16px -10px rgba(15,23,42,.2);
}
.tp-master thead th{
  background:linear-gradient(180deg,#0b1d3a,#1e3a5f);color:#f1f5f9;
  padding:11px 10px;font-size:.7rem;letter-spacing:.1em;text-transform:uppercase;font-weight:700;
}
.tp-master tbody td{padding:10px 10px;border-bottom:1px solid #f1f5f9;font-variant-numeric:tabular-nums}
.tp-master tbody tr:nth-child(even) td{background:#fbfdff}
.tp-master tbody tr:hover td{background:#eff6ff}
.tp-master tbody tr:last-child td{border-bottom:none}
.tp-master a{color:var(--tp-blue);text-decoration:none;font-weight:700}
.tp-master a:hover{text-decoration:underline}

/* Chip badges */
.tp-chip{
  display:inline-block;padding:2px 8px;border-radius:999px;
  font-size:.7rem;font-weight:700;letter-spacing:.04em;
}
.tp-chip.green{background:#dcfce7;color:#166534}
.tp-chip.amber{background:#fef3c7;color:#92400e}
.tp-chip.red  {background:#fee2e2;color:#991b1b}
.tp-chip.blue {background:#dbeafe;color:#1e40af}
.tp-chip.violet{background:#ede9fe;color:#5b21b6}
.tp-chip.slate{background:#e2e8f0;color:#334155}

/* Narrative blocks */
.tp-narr{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;margin-top:6px}
.tp-narr .blk{background:#fff;border:1px solid var(--tp-line);border-radius:10px;padding:11px 13px;border-left:3px solid var(--tp-blue2)}
.tp-narr .blk.tech{border-left-color:#1d4ed8}
.tp-narr .blk.fund{border-left-color:#0f766e}
.tp-narr .blk.sector{border-left-color:#7c3aed}
.tp-narr .blk.val{border-left-color:#d97706}
.tp-narr .blk.cat{border-left-color:#16a34a;background:#f0fdf4}
.tp-narr .blk.risk{border-left-color:#b91c1c;background:#fef2f2}
.tp-narr .blk.act{border-left-color:#047857;background:#ecfdf5}
.tp-narr .blk h5{margin:0 0 5px;font-size:.7rem;letter-spacing:.1em;text-transform:uppercase;color:var(--tp-mute);font-weight:700;display:flex;align-items:center;gap:5px}
.tp-narr .blk p,.tp-narr .blk li{font-size:.83rem;color:var(--tp-ink-soft);line-height:1.55;margin:0}
.tp-narr .blk ul{margin:4px 0 0;padding-left:18px}

/* Back to top */
.tp-totop{
  position:fixed;right:18px;bottom:18px;z-index:50;
  background:var(--tp-blue);color:#fff;border:none;border-radius:50%;
  width:42px;height:42px;font-size:18px;cursor:pointer;
  box-shadow:0 10px 24px -10px rgba(30,58,95,.55);
}
.tp-totop:hover{background:var(--tp-blue2)}

/* Print */
@media print{
  .tp-toc,.tp-totop{display:none !important}
  .tp-card{break-inside:avoid;box-shadow:none}
  .tp-hero{background:#1e3a5f !important;-webkit-print-color-adjust:exact;print-color-adjust:exact}
}
"""


def _safe_floats(values: list) -> list[float]:
    out = []
    for v in values:
        try: out.append(float(v))
        except (TypeError, ValueError): pass
    return out


def _svg_bar_chart(labels: list[str], series: list[tuple[str, list]],
                   width: int = 360, height: int = 150,
                   colors: list[str] | None = None) -> str:
    """Grouped bar chart (1-2 series). Inline SVG, no JS."""
    if not labels or not series:
        return ""
    colors = colors or ["#2563eb", "#0f766e", "#d97706"]
    all_vals = []
    cleaned_series = []
    for name, vals in series:
        cv = []
        for v in vals:
            try: cv.append(float(v))
            except (TypeError, ValueError): cv.append(None)
        cleaned_series.append((name, cv))
        all_vals.extend([v for v in cv if v is not None])
    if not all_vals:
        return ""
    vmin, vmax = min(all_vals + [0]), max(all_vals + [0])
    if vmax == vmin: vmax = vmin + 1
    pad_l, pad_r, pad_t, pad_b = 8, 8, 12, 26
    chart_w = width - pad_l - pad_r
    chart_h = height - pad_t - pad_b
    n = len(labels); ng = len(cleaned_series)
    group_w = chart_w / max(n, 1)
    bar_w = max(4, (group_w - 6) / ng)
    def y_for(v): return pad_t + chart_h - (v - vmin) / (vmax - vmin) * chart_h
    zero_y = y_for(0)
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
             f'xmlns="http://www.w3.org/2000/svg" style="display:block">']
    # axis baseline
    parts.append(f'<line x1="{pad_l}" y1="{zero_y}" x2="{pad_l+chart_w}" y2="{zero_y}" stroke="#cbd5e1" stroke-width="1"/>')
    for gi, (name, vals) in enumerate(cleaned_series):
        c = colors[gi % len(colors)]
        for i, v in enumerate(vals):
            if v is None: continue
            x = pad_l + i * group_w + 3 + gi * bar_w
            y = y_for(v)
            h_ = abs(zero_y - y)
            y0 = min(y, zero_y)
            parts.append(f'<rect x="{x:.1f}" y="{y0:.1f}" width="{bar_w:.1f}" height="{h_:.1f}" '
                         f'rx="2" fill="{c}" opacity="0.9"/>')
    for i, lab in enumerate(labels):
        cx = pad_l + i * group_w + group_w / 2
        parts.append(f'<text x="{cx:.1f}" y="{height-8}" font-size="10" text-anchor="middle" '
                     f'fill="#64748b" font-family="Inter,sans-serif">{html_mod.escape(str(lab))}</text>')
    # legend
    lx = pad_l
    for gi, (name, _) in enumerate(cleaned_series):
        c = colors[gi % len(colors)]
        parts.append(f'<rect x="{lx}" y="2" width="9" height="9" rx="2" fill="{c}"/>'
                     f'<text x="{lx+13}" y="10" font-size="10" fill="#475569" '
                     f'font-family="Inter,sans-serif">{html_mod.escape(name)}</text>')
        lx += 70
    parts.append('</svg>')
    return "".join(parts)


def _svg_sparkline(values: list, width: int = 220, height: int = 46,
                   color: str = "#2563eb", fill: str = "rgba(37,99,235,.12)") -> str:
    vs = _safe_floats(values)
    if len(vs) < 2: return ""
    vmin, vmax = min(vs), max(vs)
    if vmax == vmin: vmax = vmin + 1
    pad = 3
    cw, ch = width - 2*pad, height - 2*pad
    pts = []
    for i, v in enumerate(vs):
        x = pad + i * cw / (len(vs)-1)
        y = pad + ch - (v - vmin)/(vmax - vmin)*ch
        pts.append(f"{x:.1f},{y:.1f}")
    pl = " ".join(pts)
    area = f"M{pts[0]} L" + " L".join(pts[1:]) + f" L{pad+cw:.1f},{pad+ch:.1f} L{pad:.1f},{pad+ch:.1f} Z"
    last_y = pts[-1].split(",")[1]
    last_x = pts[-1].split(",")[0]
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
            f'xmlns="http://www.w3.org/2000/svg" style="display:block">'
            f'<path d="{area}" fill="{fill}" stroke="none"/>'
            f'<polyline points="{pl}" fill="none" stroke="{color}" stroke-width="1.6" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{last_x}" cy="{last_y}" r="2.5" fill="{color}"/>'
            f'</svg>')


def _svg_gauge(score: float | None, max_val: float = 10.0,
               width: int = 170, height: int = 100) -> str:
    """Semi-circular gauge for risk score (0=green, 10=red)."""
    if score is None: return ""
    s = max(0.0, min(float(score), max_val))
    cx, cy, r = width/2, height-10, width/2 - 10
    import math
    def pt(theta):
        return (cx + r*math.cos(theta), cy + r*math.sin(theta))
    # arc from 180° to 0°  → in SVG y-down: theta from π to 2π is upper half
    def arc(t1, t2, color, w=12):
        x1, y1 = pt(t1); x2, y2 = pt(t2)
        large = 1 if (t2 - t1) > math.pi else 0
        return f'<path d="M{x1:.1f},{y1:.1f} A{r},{r} 0 {large} 1 {x2:.1f},{y2:.1f}" stroke="{color}" stroke-width="{w}" fill="none" stroke-linecap="round"/>'
    # 3 colored arc segments (low/med/high)
    bg = arc(math.pi, 2*math.pi, "#e5e7eb", 12)
    seg_low = arc(math.pi, math.pi + math.pi*0.3, "#16a34a", 12)
    seg_med = arc(math.pi + math.pi*0.3, math.pi + math.pi*0.6, "#d97706", 12)
    seg_high = arc(math.pi + math.pi*0.6, 2*math.pi, "#b91c1c", 12)
    # needle
    theta = math.pi + math.pi * (s / max_val)
    nx, ny = pt(theta)
    needle = (f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{nx:.1f}" y2="{ny:.1f}" '
              f'stroke="#0f172a" stroke-width="2.5" stroke-linecap="round"/>'
              f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="#0f172a"/>')
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
            f'xmlns="http://www.w3.org/2000/svg">{bg}{seg_low}{seg_med}{seg_high}{needle}</svg>')


def _svg_targets(last: float | None, entry_low: float | None, entry_high: float | None,
                 stop: float | None, t1: float | None, t2: float | None, t3: float | None,
                 width: int = 480, height: int = 80) -> str:
    """Horizontal price ladder: stop ─ entry zone ─ current ─ T1 ─ T2 ─ T3."""
    pts = [v for v in (last, entry_low, entry_high, stop, t1, t2, t3) if v is not None]
    if len(pts) < 3 or last is None: return ""
    try: pts = [float(p) for p in pts]
    except (TypeError, ValueError): return ""
    vmin, vmax = min(pts)*0.97, max(pts)*1.03
    if vmax == vmin: return ""
    pad_l, pad_r = 10, 10
    cw = width - pad_l - pad_r
    yline = height/2
    def x(v): return pad_l + (float(v)-vmin)/(vmax-vmin)*cw
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
             f'xmlns="http://www.w3.org/2000/svg" style="display:block">']
    # base line
    parts.append(f'<line x1="{pad_l}" y1="{yline}" x2="{pad_l+cw}" y2="{yline}" stroke="#cbd5e1" stroke-width="2"/>')
    # entry zone band
    if entry_low is not None and entry_high is not None:
        xl, xh = x(entry_low), x(entry_high)
        parts.append(f'<rect x="{xl:.1f}" y="{yline-9}" width="{max(2,xh-xl):.1f}" height="18" '
                     f'fill="rgba(37,99,235,.18)" stroke="#2563eb" stroke-width="1"/>')
    # markers
    def marker(v, color, label, above=True):
        if v is None: return ""
        xx = x(v)
        ty = yline - 14 if above else yline + 24
        return (f'<line x1="{xx:.1f}" y1="{yline-10}" x2="{xx:.1f}" y2="{yline+10}" stroke="{color}" stroke-width="2"/>'
                f'<text x="{xx:.1f}" y="{ty}" font-size="10" font-weight="700" text-anchor="middle" fill="{color}" '
                f'font-family="Inter,sans-serif">{html_mod.escape(label)}</text>'
                f'<text x="{xx:.1f}" y="{ty + (-10 if above else 12)}" font-size="9" text-anchor="middle" fill="#64748b" '
                f'font-family="Inter,sans-serif">₹{float(v):,.0f}</text>')
    parts.append(marker(stop, "#b91c1c", "STOP", above=False))
    parts.append(marker(last, "#0f172a", "NOW", above=True))
    parts.append(marker(t1, "#0f766e", "T1", above=False))
    parts.append(marker(t2, "#16a34a", "T2", above=True))
    parts.append(marker(t3, "#7c3aed", "T3", above=False))
    parts.append('</svg>')
    return "".join(parts)


def _svg_donut(slices: list[tuple[str, float]], width: int = 170, height: int = 170,
               palette: list[str] | None = None) -> str:
    palette = palette or ["#2563eb","#0f766e","#d97706","#7c3aed","#0891b2","#16a34a","#b91c1c","#475569","#db2777","#65a30d"]
    total = sum(v for _, v in slices if v)
    if total <= 0: return ""
    import math
    cx, cy, r, rin = width/2, height/2, min(width, height)/2 - 6, min(width, height)/4
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
             f'xmlns="http://www.w3.org/2000/svg">']
    start = -math.pi/2
    for i, (label, val) in enumerate(slices):
        if not val: continue
        frac = val/total
        end = start + frac*2*math.pi
        x1, y1 = cx + r*math.cos(start), cy + r*math.sin(start)
        x2, y2 = cx + r*math.cos(end),   cy + r*math.sin(end)
        x3, y3 = cx + rin*math.cos(end), cy + rin*math.sin(end)
        x4, y4 = cx + rin*math.cos(start), cy + rin*math.sin(start)
        large = 1 if frac > 0.5 else 0
        color = palette[i % len(palette)]
        d = (f"M{x1:.1f},{y1:.1f} A{r},{r} 0 {large} 1 {x2:.1f},{y2:.1f} "
             f"L{x3:.1f},{y3:.1f} A{rin},{rin} 0 {large} 0 {x4:.1f},{y4:.1f} Z")
        parts.append(f'<path d="{d}" fill="{color}" stroke="#fff" stroke-width="1"/>')
        start = end
    parts.append(f'<text x="{cx}" y="{cy-2}" text-anchor="middle" font-size="14" font-weight="800" fill="#0f172a" '
                 f'font-family="Inter,sans-serif">{int(total)}</text>'
                 f'<text x="{cx}" y="{cy+12}" text-anchor="middle" font-size="9" fill="#64748b" '
                 f'font-family="Inter,sans-serif">PICKS</text>')
    parts.append('</svg>')
    return "".join(parts)


def _detect_patterns(chart: dict, swing_window: int = 5) -> list[dict]:
    """Detect classic chart, candle, and trend patterns. Returns list of:
       {kind, label, color, anchors: [(i, price), ...], note}
    Covers: double bottom/top, head-and-shoulders (regular + inverse),
    ascending/descending/symmetrical triangles, bull/bear flags, rising/falling
    wedges, golden/death cross, EMA pullback test, 52W-high touch, volume
    surge, three white soldiers / black crows, morning/evening star, bullish/
    bearish engulfing, hammer, shooting star, doji, piercing line, dark cloud
    cover, inside bar, gap up/down, higher-highs / lower-lows channels.
    """
    bars = chart.get("bars") or []
    n = len(bars)
    if n < 12: return []
    highs  = [b["high"] for b in bars]
    lows   = [b["low"]  for b in bars]
    opens  = [b["open"] for b in bars]
    closes = [b["close"] for b in bars]
    vols   = [b["volume"] for b in bars]
    ema20_s  = chart.get("ema20_series")  or [None]*n
    ema50_s  = chart.get("ema50_series")  or [None]*n
    ema200_s = chart.get("ema200_series") or [None]*n
    out: list[dict] = []

    # ── Swing pivots
    swing_h: list[tuple[int, float]] = []
    swing_l: list[tuple[int, float]] = []
    for i in range(swing_window, n - swing_window):
        if highs[i] == max(highs[i-swing_window:i+swing_window+1]):
            swing_h.append((i, highs[i]))
        if lows[i] == min(lows[i-swing_window:i+swing_window+1]):
            swing_l.append((i, lows[i]))

    # ── Double bottom (W)
    if len(swing_l) >= 2:
        a, b = swing_l[-2], swing_l[-1]
        gap_pct = abs(a[1] - b[1]) / max(a[1], b[1]) * 100
        if gap_pct <= 3.5 and (b[0] - a[0]) >= 8:
            peak = max(((i, highs[i]) for i in range(a[0], b[0]+1)),
                       key=lambda x: x[1])
            if peak[1] > max(a[1], b[1]) * 1.03:
                out.append({"kind":"double_bottom","label":"Double Bottom (W)","color":"#22c55e",
                            "anchors":[a, peak, b],
                            "note":f"Two lows ~₹{(a[1]+b[1])/2:,.0f}; neckline ₹{peak[1]:,.0f}"})

    # ── Double top (M)
    if len(swing_h) >= 2:
        a, b = swing_h[-2], swing_h[-1]
        gap_pct = abs(a[1] - b[1]) / max(a[1], b[1]) * 100
        if gap_pct <= 3.5 and (b[0] - a[0]) >= 8:
            trough = min(((i, lows[i]) for i in range(a[0], b[0]+1)),
                         key=lambda x: x[1])
            if trough[1] < min(a[1], b[1]) * 0.97:
                out.append({"kind":"double_top","label":"Double Top (M)","color":"#ef4444",
                            "anchors":[a, trough, b],
                            "note":f"Two highs ~₹{(a[1]+b[1])/2:,.0f}; neckline ₹{trough[1]:,.0f}"})

    # ── Head & Shoulders (3 highs: middle highest, shoulders within 4%)
    if len(swing_h) >= 3:
        ls, hd, rs = swing_h[-3], swing_h[-2], swing_h[-1]
        if (hd[1] > ls[1] * 1.02 and hd[1] > rs[1] * 1.02
            and abs(ls[1] - rs[1]) / max(ls[1], rs[1]) <= 0.04
            and (rs[0] - ls[0]) >= 15):
            out.append({"kind":"hns","label":"Head & Shoulders","color":"#ef4444",
                        "anchors":[ls, hd, rs],
                        "note":f"Top ₹{hd[1]:,.0f}; shoulders ~₹{(ls[1]+rs[1])/2:,.0f} — bearish"})
    # ── Inverse Head & Shoulders
    if len(swing_l) >= 3:
        ls, hd, rs = swing_l[-3], swing_l[-2], swing_l[-1]
        if (hd[1] < ls[1] * 0.98 and hd[1] < rs[1] * 0.98
            and abs(ls[1] - rs[1]) / max(ls[1], rs[1]) <= 0.04
            and (rs[0] - ls[0]) >= 15):
            out.append({"kind":"ihns","label":"Inverse H&S","color":"#22c55e",
                        "anchors":[ls, hd, rs],
                        "note":f"Bottom ₹{hd[1]:,.0f}; shoulders ~₹{(ls[1]+rs[1])/2:,.0f} — bullish"})

    # ── Triangles (using last 3 swings each side)
    if len(swing_h) >= 2 and len(swing_l) >= 2:
        h1, h2 = swing_h[-2], swing_h[-1]
        l1, l2 = swing_l[-2], swing_l[-1]
        h_diff = (h2[1] - h1[1]) / h1[1]
        l_diff = (l2[1] - l1[1]) / l1[1]
        # Ascending triangle: flat top, rising bottoms
        if abs(h_diff) <= 0.015 and l_diff > 0.02:
            out.append({"kind":"asc_tri","label":"Ascending Triangle","color":"#34d399",
                        "anchors":[h1, h2, l1, l2],
                        "note":f"Flat resistance ~₹{(h1[1]+h2[1])/2:,.0f}; rising lows — bullish"})
        # Descending triangle: falling tops, flat bottom
        elif abs(l_diff) <= 0.015 and h_diff < -0.02:
            out.append({"kind":"desc_tri","label":"Descending Triangle","color":"#f87171",
                        "anchors":[h1, h2, l1, l2],
                        "note":f"Flat support ~₹{(l1[1]+l2[1])/2:,.0f}; falling highs — bearish"})
        # Symmetrical triangle: converging
        elif h_diff < -0.015 and l_diff > 0.015:
            out.append({"kind":"sym_tri","label":"Symmetrical Triangle","color":"#fbbf24",
                        "anchors":[h1, h2, l1, l2],
                        "note":"Converging range — await directional break"})
        # Rising wedge (bearish): both rising, tops rising slower
        elif h_diff > 0 and l_diff > 0 and l_diff > h_diff + 0.02:
            out.append({"kind":"rising_wedge","label":"Rising Wedge","color":"#fb7185",
                        "anchors":[h1, h2, l1, l2],
                        "note":"Both sides rising, lows faster — bearish exhaustion"})
        # Falling wedge (bullish): both falling, bottoms falling slower
        elif h_diff < 0 and l_diff < 0 and h_diff < l_diff - 0.02:
            out.append({"kind":"falling_wedge","label":"Falling Wedge","color":"#34d399",
                        "anchors":[h1, h2, l1, l2],
                        "note":"Both sides falling, highs faster — bullish reversal"})

    # ── Flag / Pennant: strong move then tight consolidation
    if n >= 22:
        pre_lo = min(closes[-22:-10]); pre_hi = max(closes[-22:-10])
        pole = (closes[-10] - closes[-22]) / closes[-22]
        cons_rng = (max(highs[-9:]) - min(lows[-9:])) / closes[-1]
        if pole > 0.10 and cons_rng < 0.05:
            out.append({"kind":"bull_flag","label":"Bull Flag","color":"#26a69a",
                        "anchors":[(n-22, closes[-22]), (n-10, closes[-10]), (n-1, closes[-1])],
                        "note":f"Pole +{pole*100:.0f}%; tight {cons_rng*100:.1f}% flag — continuation"})
        elif pole < -0.10 and cons_rng < 0.05:
            out.append({"kind":"bear_flag","label":"Bear Flag","color":"#ef5350",
                        "anchors":[(n-22, closes[-22]), (n-10, closes[-10]), (n-1, closes[-1])],
                        "note":f"Pole {pole*100:.0f}%; tight {cons_rng*100:.1f}% flag — continuation down"})

    # ── Golden cross / Death cross (EMA50 over/under EMA200, fresh in last 15 bars)
    cross_idx = None; cross_dir = None
    for i in range(max(1, n-15), n):
        if ema50_s[i] is None or ema200_s[i] is None or ema50_s[i-1] is None or ema200_s[i-1] is None:
            continue
        if ema50_s[i-1] < ema200_s[i-1] and ema50_s[i] >= ema200_s[i]:
            cross_idx = i; cross_dir = "golden"; break
        if ema50_s[i-1] > ema200_s[i-1] and ema50_s[i] <= ema200_s[i]:
            cross_idx = i; cross_dir = "death"; break
    if cross_idx is not None:
        if cross_dir == "golden":
            out.append({"kind":"golden_x","label":"Golden Cross","color":"#facc15",
                        "anchors":[(cross_idx, ema50_s[cross_idx])],
                        "note":f"EMA50 ({ema50_s[cross_idx]:,.0f}) crossed above EMA200 — major bullish"})
        else:
            out.append({"kind":"death_x","label":"Death Cross","color":"#ef4444",
                        "anchors":[(cross_idx, ema50_s[cross_idx])],
                        "note":f"EMA50 ({ema50_s[cross_idx]:,.0f}) crossed below EMA200 — major bearish"})

    # ── EMA pullback (price tagging EMA50 or EMA200 in uptrend)
    if ema50_s[-1] is not None and ema200_s[-1] is not None and closes[-1] > ema200_s[-1]:
        dist50 = (closes[-1] - ema50_s[-1]) / ema50_s[-1]
        if -0.02 <= dist50 <= 0.015 and lows[-1] <= ema50_s[-1] * 1.005:
            out.append({"kind":"ema50_test","label":"EMA50 Pullback","color":"#42a5f5",
                        "anchors":[(n-1, ema50_s[-1])],
                        "note":f"Price testing EMA50 ₹{ema50_s[-1]:,.0f} in uptrend — buy-the-dip zone"})

    # ── 52W high touch
    wk52_high = chart.get("wk52_high")
    if wk52_high and highs[-1] >= float(wk52_high) * 0.998:
        out.append({"kind":"new_high","label":"52W High Touch","color":"#a78bfa",
                    "anchors":[(n-1, highs[-1])],
                    "note":f"Tagging 52W high ₹{float(wk52_high):,.0f} — breakout watch"})

    # ── Volume surge (today >2× 20d avg, separate from breakout)
    if n >= 22:
        avg_v = sum(vols[-22:-2]) / 20
        if avg_v > 0 and vols[-1] > avg_v * 2.0:
            out.append({"kind":"vol_spike","label":"Volume Surge","color":"#06b6d4",
                        "anchors":[(n-1, closes[-1])],
                        "note":f"Today {vols[-1]/avg_v:.1f}× 20d avg volume — institutional interest"})

    # ── Higher highs / higher lows (or lower)
    if len(swing_h) >= 2 and len(swing_l) >= 2:
        if swing_h[-1][1] > swing_h[-2][1] and swing_l[-1][1] > swing_l[-2][1]:
            out.append({"kind":"hh_hl","label":"Higher Highs · Higher Lows","color":"#26a69a",
                        "anchors":[swing_l[-2], swing_h[-2], swing_l[-1], swing_h[-1]],
                        "note":"Confirmed uptrend channel"})
        elif swing_h[-1][1] < swing_h[-2][1] and swing_l[-1][1] < swing_l[-2][1]:
            out.append({"kind":"lh_ll","label":"Lower Highs · Lower Lows","color":"#ef5350",
                        "anchors":[swing_h[-2], swing_l[-2], swing_h[-1], swing_l[-1]],
                        "note":"Confirmed downtrend channel"})

    # ── Breakout / breakdown (close above/below 20d hi/lo with volume)
    if n >= 25:
        prior_hi = max(highs[-22:-2])
        avg_vol = sum(vols[-22:-2]) / 20
        if closes[-1] > prior_hi and vols[-1] > avg_vol * 1.4:
            anchor_i = max(range(n-22, n-2), key=lambda k: highs[k])
            out.append({"kind":"breakout","label":"Breakout ↑","color":"#a78bfa",
                        "anchors":[(anchor_i, prior_hi), (n-1, closes[-1])],
                        "note":f"Close ₹{closes[-1]:,.0f} > 20d hi ₹{prior_hi:,.0f}, vol {vols[-1]/avg_vol:.1f}×"})
        prior_lo = min(lows[-22:-2])
        if closes[-1] < prior_lo and vols[-1] > avg_vol * 1.4:
            anchor_i = min(range(n-22, n-2), key=lambda k: lows[k])
            out.append({"kind":"breakdown","label":"Breakdown ↓","color":"#fb7185",
                        "anchors":[(anchor_i, prior_lo), (n-1, closes[-1])],
                        "note":f"Close ₹{closes[-1]:,.0f} < 20d lo ₹{prior_lo:,.0f}, vol {vols[-1]/avg_vol:.1f}×"})

    # ── Three White Soldiers / Three Black Crows
    if n >= 3:
        c0,c1,c2 = closes[-3], closes[-2], closes[-1]
        o0,o1,o2 = opens[-3],  opens[-2],  opens[-1]
        if (c0>o0 and c1>o1 and c2>o2 and c0<c1<c2 and o1>o0 and o2>o1):
            out.append({"kind":"3soldiers","label":"Three White Soldiers","color":"#22c55e",
                        "anchors":[(n-3,c0),(n-2,c1),(n-1,c2)],
                        "note":"Three rising green closes — strong bullish continuation"})
        if (c0<o0 and c1<o1 and c2<o2 and c0>c1>c2 and o1<o0 and o2<o1):
            out.append({"kind":"3crows","label":"Three Black Crows","color":"#ef4444",
                        "anchors":[(n-3,c0),(n-2,c1),(n-1,c2)],
                        "note":"Three falling red closes — strong bearish continuation"})

    # ── Morning / Evening Star (3-candle reversal)
    if n >= 3:
        c0,c1,c2 = closes[-3], closes[-2], closes[-1]
        o0,o1,o2 = opens[-3],  opens[-2],  opens[-1]
        b0,b1,b2 = abs(c0-o0), abs(c1-o1), abs(c2-o2)
        if c0<o0 and b1 < b0*0.4 and c2>o2 and c2 > (o0+c0)/2:
            out.append({"kind":"morning_star","label":"Morning Star","color":"#22c55e",
                        "anchors":[(n-3,(o0+c0)/2),(n-2,(o1+c1)/2),(n-1,(o2+c2)/2)],
                        "note":"3-bar bottom reversal — bullish"})
        if c0>o0 and b1 < b0*0.4 and c2<o2 and c2 < (o0+c0)/2:
            out.append({"kind":"evening_star","label":"Evening Star","color":"#ef4444",
                        "anchors":[(n-3,(o0+c0)/2),(n-2,(o1+c1)/2),(n-1,(o2+c2)/2)],
                        "note":"3-bar top reversal — bearish"})

    # ── Last-candle patterns
    o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
    po, ph, pl, pc = opens[-2], highs[-2], lows[-2], closes[-2]
    body = abs(c - o); rng = max(h - l, 1e-9)
    upper_wick = h - max(o, c); lower_wick = min(o, c) - l

    # Bullish/bearish engulfing
    if pc < po and c > o and c >= po and o <= pc and body > abs(pc - po) * 0.9:
        out.append({"kind":"engulf_up","label":"Bullish Engulfing","color":"#26a69a",
                    "anchors":[(n-2, pc),(n-1, c)],"note":"Prior red body engulfed — reversal"})
    elif pc > po and c < o and c <= po and o >= pc and body > abs(pc - po) * 0.9:
        out.append({"kind":"engulf_dn","label":"Bearish Engulfing","color":"#ef5350",
                    "anchors":[(n-2, pc),(n-1, c)],"note":"Prior green body engulfed — reversal"})
    # Piercing line (bullish): prior red, today green, closes above prior midpoint
    elif pc < po and c > o and o < pl and c > (po+pc)/2 and c < po:
        out.append({"kind":"piercing","label":"Piercing Line","color":"#22c55e",
                    "anchors":[(n-2,pc),(n-1,c)],"note":"Gap-down recovery > prior midpoint — bullish"})
    # Dark cloud cover (bearish): prior green, today red, closes below prior midpoint
    elif pc > po and c < o and o > ph and c < (po+pc)/2 and c > po:
        out.append({"kind":"dark_cloud","label":"Dark Cloud Cover","color":"#ef4444",
                    "anchors":[(n-2,pc),(n-1,c)],"note":"Gap-up failure < prior midpoint — bearish"})
    # Hammer
    elif lower_wick > body * 2 and upper_wick < body * 0.6 and body < rng * 0.4:
        out.append({"kind":"hammer","label":"Hammer","color":"#22c55e",
                    "anchors":[(n-1, l)],"note":f"Long lower wick {lower_wick/rng*100:.0f}% of range"})
    # Shooting star
    elif upper_wick > body * 2 and lower_wick < body * 0.6 and body < rng * 0.4:
        out.append({"kind":"shoot","label":"Shooting Star","color":"#ef4444",
                    "anchors":[(n-1, h)],"note":f"Long upper wick {upper_wick/rng*100:.0f}% of range"})
    # Doji
    elif body < rng * 0.1 and rng > 0:
        out.append({"kind":"doji","label":"Doji","color":"#94a3b8",
                    "anchors":[(n-1, (h+l)/2)],"note":"Open ≈ close — indecision / potential reversal"})
    # Inside bar
    elif h <= ph and l >= pl:
        out.append({"kind":"inside","label":"Inside Bar","color":"#94a3b8",
                    "anchors":[(n-1, (h+l)/2)],"note":"Range compression — pending expansion"})

    # Gap up / down
    if l > ph and (l - ph) / pc > 0.01:
        out.append({"kind":"gap_up","label":"Gap Up","color":"#34d399",
                    "anchors":[(n-1, (l+ph)/2)],"note":f"Opened {(l-ph)/pc*100:.1f}% above prior high"})
    elif h < pl and (pl - h) / pc > 0.01:
        out.append({"kind":"gap_dn","label":"Gap Down","color":"#f87171",
                    "anchors":[(n-1, (h+pl)/2)],"note":f"Opened {(pl-h)/pc*100:.1f}% below prior low"})

    # Limit & prioritise (most significant patterns first)
    priority = {
        "golden_x":0,"death_x":0,
        "hns":1,"ihns":1,"double_bottom":1,"double_top":1,
        "breakout":2,"breakdown":2,
        "asc_tri":3,"desc_tri":3,"sym_tri":3,"rising_wedge":3,"falling_wedge":3,
        "bull_flag":4,"bear_flag":4,
        "morning_star":5,"evening_star":5,"3soldiers":5,"3crows":5,
        "engulf_up":6,"engulf_dn":6,"piercing":6,"dark_cloud":6,
        "hammer":7,"shoot":7,
        "ema50_test":8,"new_high":8,"vol_spike":8,
        "hh_hl":9,"lh_ll":9,
        "gap_up":10,"gap_dn":10,"doji":11,"inside":12,
    }
    out.sort(key=lambda d: priority.get(d["kind"], 99))
    return out[:6]


def _svg_candlestick(chart: dict, *, symbol: str = "", entry_low=None, entry_high=None, stop=None,
                     t1=None, t2=None, t3=None,
                     width: int = 1000, price_h: int = 380, vol_h: int = 80,
                     rsi_h: int = 70, profile_w: int = 80) -> str:
    """TradingView-style chart: dark theme, right-side price axis with last-price flag,
    OHLC + EMA legend overlay, symbol watermark, separate volume + RSI sub-panels,
    S/R + pivots + entry/stop/targets + volume profile."""
    bars = chart.get("bars") or []
    if not bars:
        return ""
    n = len(bars)

    # ── TradingView dark palette
    BG          = "#131722"
    PANEL_LINE  = "#1e222d"
    GRID        = "#1e222d"
    AXIS_TEXT   = "#787b86"
    TEXT        = "#d1d4dc"
    TEXT_BRIGHT = "#f0f3fa"
    UP          = "#26a69a"
    DOWN        = "#ef5350"
    EMA20_C     = "#ffb74d"
    EMA50_C     = "#42a5f5"
    EMA200_C    = "#ab47bc"

    # ── Layout: price axis on RIGHT (TV convention)
    pad_l       = 12
    pad_r       = 64   # space for right-side price axis
    pad_t       = 44   # room for legend overlay
    pad_b       = 24
    panel_gap   = 6
    chart_w     = width - pad_l - pad_r - profile_w - 6
    if chart_w <= 50:
        chart_w = width - pad_l - pad_r; profile_w = 0
    rsi_series  = chart.get("rsi_series") or []
    has_rsi     = any(v is not None for v in rsi_series)
    rsi_panel_h = rsi_h if has_rsi else 0
    height = pad_t + price_h + panel_gap + vol_h + (panel_gap + rsi_panel_h if has_rsi else 0) + pad_b

    highs  = [b["high"] for b in bars]
    lows   = [b["low"]  for b in bars]
    opens  = [b["open"] for b in bars]
    closes = [b["close"] for b in bars]
    vols   = [b["volume"] for b in bars]

    def _num(v):
        if v is None: return None
        if isinstance(v, (int, float)): return float(v)
        try:
            import re as _re
            m = _re.search(r"-?\d[\d,]*\.?\d*", str(v))
            return float(m.group(0).replace(",", "")) if m else None
        except Exception:
            return None
    entry_low = _num(entry_low); entry_high = _num(entry_high)
    stop = _num(stop); t1 = _num(t1); t2 = _num(t2); t3 = _num(t3)
    extra = [v for v in (entry_low, entry_high, stop, t1, t2, t3) if v is not None]
    extra += [chart.get("wk52_high"), chart.get("wk52_low")]
    extra += chart.get("support_levels") or []
    extra += chart.get("resistance_levels") or []
    pv = chart.get("pivots") or {}
    extra += [pv.get(k) for k in ("PP","R1","S1") if pv.get(k) is not None]
    extra = [_num(v) for v in extra]
    extra = [v for v in extra if v is not None]

    p_min = min(min(lows), min(extra) if extra else min(lows)) * 0.985
    p_max = max(max(highs), max(extra) if extra else max(highs)) * 1.015
    if p_max <= p_min: return ""
    v_max = max(vols) if vols else 1
    if v_max == 0: v_max = 1

    def x_for(i): return pad_l + (i + 0.5) * (chart_w / n)
    def y_price(v): return pad_t + (p_max - float(v)) / (p_max - p_min) * price_h

    vol_top = pad_t + price_h + panel_gap
    def y_vol(v): return vol_top + vol_h - (float(v) / v_max) * vol_h

    rsi_top = vol_top + vol_h + panel_gap
    def y_rsi(v): return rsi_top + rsi_panel_h - (float(v) / 100.0) * rsi_panel_h

    bar_w = max(1.5, chart_w / n * 0.72)
    axis_x = pad_l + chart_w + 4   # right axis baseline

    # Unique chart id for JS-driven crosshair tooltip
    global _CANDLE_CHART_SEQ
    try: _CANDLE_CHART_SEQ += 1
    except NameError: _CANDLE_CHART_SEQ = 1
    chart_id = f"tpc-{_CANDLE_CHART_SEQ}"

    parts = [
        f'<svg id="{chart_id}" class="tp-tv-chart" '
        f'viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg" style="display:block;background:{BG};'
        f'border-radius:8px;font-family:-apple-system,BlinkMacSystemFont,Inter,sans-serif" '
        f'data-pad-l="{pad_l}" data-pad-t="{pad_t}" data-chart-w="{chart_w}" '
        f'data-price-h="{price_h}" data-vol-top="{vol_top}" data-vol-h="{vol_h}" '
        f'data-rsi-top="{rsi_top}" data-rsi-h="{rsi_panel_h}" data-has-rsi="{int(has_rsi)}" '
        f'data-p-min="{p_min}" data-p-max="{p_max}" data-v-max="{v_max}" '
        f'data-n="{n}" data-symbol="{html_mod.escape(symbol)}">',
        # full background
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="{BG}"/>',
        # panel separators
        f'<line x1="{pad_l}" y1="{pad_t+price_h+1}" x2="{pad_l+chart_w}" y2="{pad_t+price_h+1}" '
        f'stroke="{PANEL_LINE}" stroke-width="1"/>',
        f'<line x1="{pad_l}" y1="{vol_top+vol_h+1}" x2="{pad_l+chart_w}" y2="{vol_top+vol_h+1}" '
        f'stroke="{PANEL_LINE}" stroke-width="1"/>' if has_rsi else "",
    ]

    # ── Symbol watermark (TV signature look)
    if symbol:
        parts.append(
            f'<text x="{pad_l+chart_w/2:.0f}" y="{pad_t+price_h/2+10:.0f}" '
            f'font-size="64" font-weight="800" text-anchor="middle" '
            f'fill="{TEXT_BRIGHT}" opacity="0.045" letter-spacing="6">{html_mod.escape(symbol)}</text>'
            f'<text x="{pad_l+chart_w/2:.0f}" y="{pad_t+price_h/2+38:.0f}" '
            f'font-size="14" text-anchor="middle" font-weight="600" '
            f'fill="{TEXT_BRIGHT}" opacity="0.05" letter-spacing="4">NSE · 1D · 6M</text>'
        )

    # ── Price grid lines + right-side y-axis labels
    def _nice_step(rng, target_ticks=7):
        import math as _m
        raw = rng / max(target_ticks, 1)
        mag = 10 ** _m.floor(_m.log10(raw))
        for m in (1, 2, 2.5, 5, 10):
            if m * mag >= raw: return m * mag
        return mag * 10
    step = _nice_step(p_max - p_min)
    import math as _m
    t = _m.floor(p_min / step) * step
    while t <= p_max:
        if p_min <= t <= p_max:
            gy = y_price(t)
            parts.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{pad_l+chart_w}" y2="{gy:.1f}" '
                         f'stroke="{GRID}" stroke-width="1" stroke-dasharray="2,3" opacity="0.55"/>')
            parts.append(f'<text x="{axis_x}" y="{gy+3:.1f}" font-size="10" text-anchor="start" '
                         f'fill="{AXIS_TEXT}" font-variant-numeric="tabular-nums">{t:,.0f}</text>')
        t += step

    # ── Vertical grid (5 month-ish gridlines through chart panels)
    grid_bottom = (rsi_top + rsi_panel_h) if has_rsi else (vol_top + vol_h)
    seen_months: set[str] = set()
    for i, b in enumerate(bars):
        ym = str(b.get("date",""))[:7]
        if ym and ym not in seen_months:
            seen_months.add(ym)
            xv = x_for(i)
            parts.append(f'<line x1="{xv:.1f}" y1="{pad_t}" x2="{xv:.1f}" y2="{grid_bottom:.1f}" '
                         f'stroke="{GRID}" stroke-width="1" stroke-dasharray="2,4" opacity="0.45"/>')

    # ── Vol panel label + RSI panel header (TV-style left-side small caps)
    parts.append(f'<text x="{pad_l+4}" y="{vol_top+11:.0f}" font-size="9.5" font-weight="700" '
                 f'fill="{AXIS_TEXT}" letter-spacing="0.6">Vol</text>')
    if has_rsi:
        parts.append(f'<text x="{pad_l+4}" y="{rsi_top+11:.0f}" font-size="9.5" font-weight="700" '
                     f'fill="{AXIS_TEXT}" letter-spacing="0.6">RSI 14</text>')

    # ── Entry zone band
    if entry_low is not None and entry_high is not None:
        try:
            y_lo = y_price(float(entry_high))
            y_hi = y_price(float(entry_low))
            parts.append(f'<rect x="{pad_l}" y="{y_lo:.1f}" width="{chart_w}" '
                         f'height="{max(2,y_hi-y_lo):.1f}" fill="rgba(66,165,245,.10)" '
                         f'stroke="#42a5f5" stroke-width="1" stroke-dasharray="4,3"/>')
        except (TypeError, ValueError): pass

    # ── Marker lines (with collision-avoid labels on right-axis side)
    def _hline_only(v, color, dash="4,3", opacity=0.78):
        if v is None: return ""
        try: v = float(v)
        except (TypeError, ValueError): return ""
        y = y_price(v)
        if y < pad_t-2 or y > pad_t + price_h+2: return ""
        return (f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l+chart_w}" y2="{y:.1f}" '
                f'stroke="{color}" stroke-width="1" stroke-dasharray="{dash}" opacity="{opacity}"/>')

    # Stacks labels by row — we draw filled pill tags on the right axis
    right_lbls: list[tuple[float, str, str]] = []
    left_lbls:  list[tuple[float, str, str]] = []
    def _add_lbl(v, color, text, side):
        if v is None: return
        try: v = float(v)
        except (TypeError, ValueError): return
        y = y_price(v)
        if y < pad_t or y > pad_t + price_h: return
        (right_lbls if side=="right" else left_lbls).append((y, text, color))

    # 52w
    parts.append(_hline_only(chart.get("wk52_high"), "#5d636f", dash="1,4", opacity=0.5))
    parts.append(_hline_only(chart.get("wk52_low"),  "#5d636f", dash="1,4", opacity=0.5))
    if chart.get("wk52_high") is not None:
        _add_lbl(chart["wk52_high"], "#6b7280", f"52wH {float(chart['wk52_high']):,.0f}", "left")
    if chart.get("wk52_low") is not None:
        _add_lbl(chart["wk52_low"],  "#6b7280", f"52wL {float(chart['wk52_low']):,.0f}", "left")
    # pivots
    for lab, color in [("PP","#a78bfa"),("R1","#fb923c"),("S1","#34d399")]:
        v = pv.get(lab)
        if v is None: continue
        parts.append(_hline_only(v, color, dash="1,3", opacity=0.6))
        _add_lbl(v, color, f"{lab} {float(v):,.0f}", "left")
    # S/R
    for v in (chart.get("resistance_levels") or []):
        parts.append(_hline_only(v, "#ef5350", dash="3,3", opacity=0.65))
        _add_lbl(v, "#ef5350", f"R {float(v):,.0f}", "right")
    for v in (chart.get("support_levels") or []):
        parts.append(_hline_only(v, "#26a69a", dash="3,3", opacity=0.65))
        _add_lbl(v, "#26a69a", f"S {float(v):,.0f}", "right")
    # Stop/Targets
    for v, color, prefix in [
        (stop, "#ef4444", "STOP"),
        (t1,   "#2dd4bf", "T1"),
        (t2,   "#22c55e", "T2"),
        (t3,   "#a78bfa", "T3"),
    ]:
        if v is None: continue
        parts.append(_hline_only(v, color, dash="5,3", opacity=0.85))
        try: _add_lbl(v, color, f"{prefix} {float(v):,.0f}", "right")
        except (TypeError, ValueError): pass
    if entry_low is not None and entry_high is not None:
        try:
            mid = (float(entry_low) + float(entry_high)) / 2
            _add_lbl(mid, "#42a5f5", "ENTRY", "right")
        except (TypeError, ValueError): pass

    # ── Resolve overlapping labels (vertical push)
    def _resolve(labels, min_gap=13.0, y_min=pad_t+5, y_max=pad_t+price_h-3):
        if not labels: return []
        labels = sorted(labels, key=lambda x: x[0])
        ys = [y for y,_,_ in labels]
        for i in range(1, len(ys)):
            if ys[i] < ys[i-1] + min_gap:
                ys[i] = ys[i-1] + min_gap
        if ys[-1] > y_max:
            ys[-1] = y_max
            for i in range(len(ys)-2, -1, -1):
                if ys[i] > ys[i+1] - min_gap:
                    ys[i] = ys[i+1] - min_gap
        if ys[0] < y_min: ys[0] = y_min
        for i in range(1, len(ys)):
            if ys[i] < ys[i-1] + min_gap:
                ys[i] = ys[i-1] + min_gap
        return [(ys[i], labels[i][1], labels[i][2]) for i in range(len(labels))]

    def _draw_lbl(y, text, color, side):
        if side == "right":
            x_rect = pad_l + chart_w + 2
            tx = x_rect + 3
            anchor = "start"
            w = pad_r - 4
        else:
            x_rect = pad_l + 2
            tx = x_rect + 3
            anchor = "start"
            w = 70
        return (f'<g class="tp-lvl"><title>{html_mod.escape(text)}</title>'
                f'<rect x="{x_rect:.1f}" y="{y-7.5:.1f}" width="{w}" height="13" rx="2.5" '
                f'fill="{color}" opacity="0.92"/>'
                f'<text x="{tx:.1f}" y="{y+3:.1f}" font-size="9" text-anchor="{anchor}" '
                f'fill="#fff" font-weight="700" font-variant-numeric="tabular-nums">'
                f'{html_mod.escape(text)}</text></g>')
    for y, text, color in _resolve(left_lbls):
        parts.append(_draw_lbl(y, text, color, "left"))
    for y, text, color in _resolve(right_lbls):
        parts.append(_draw_lbl(y, text, color, "right"))

    # ── Candles
    for i, b in enumerate(bars):
        x = x_for(i)
        o, hh, ll, c = b["open"], b["high"], b["low"], b["close"]
        up = c >= o
        color = UP if up else DOWN
        chg = c - o
        chg_pct = (chg / o * 100) if o else 0
        tip = (f"{b.get('date','')}  O {o:,.2f}  H {hh:,.2f}  L {ll:,.2f}  "
               f"C {c:,.2f}  ({chg:+.2f} / {chg_pct:+.2f}%)  Vol {b.get('volume',0):,.0f}")
        parts.append(
            f'<g class="tp-candle">'
            f'<title>{html_mod.escape(tip)}</title>'
            f'<line x1="{x:.1f}" y1="{y_price(hh):.1f}" x2="{x:.1f}" y2="{y_price(ll):.1f}" '
            f'stroke="{color}" stroke-width="1"/>'
            f'<rect x="{x-bar_w/2:.1f}" y="{y_price(max(o,c)):.1f}" width="{bar_w:.1f}" '
            f'height="{max(1.0, abs(y_price(o)-y_price(c))):.1f}" fill="{color}" '
            f'stroke="{color}" stroke-width="0.5"/>'
            # transparent wider hit area for easier hover
            f'<rect x="{x-bar_w/2-1.5:.1f}" y="{y_price(hh)-1:.1f}" width="{bar_w+3:.1f}" '
            f'height="{max(2,y_price(ll)-y_price(hh)+2):.1f}" fill="transparent"/>'
            f'</g>'
        )
        # volume bar with its own tooltip
        vtip = f"{b.get('date','')}  Vol {b.get('volume',0):,.0f}"
        parts.append(
            f'<g class="tp-vol"><title>{html_mod.escape(vtip)}</title>'
            f'<rect x="{x-bar_w/2:.1f}" y="{y_vol(b["volume"]):.1f}" width="{bar_w:.1f}" '
            f'height="{(vol_top+vol_h)-y_vol(b["volume"]):.1f}" fill="{color}" opacity="0.55"/>'
            f'</g>'
        )

    # ── EMA polylines
    def _poly(series, color, w=1.6, dash=None):
        pts = [f"{x_for(i):.1f},{y_price(v):.1f}" for i, v in enumerate(series) if v is not None]
        if len(pts) < 2: return ""
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        return (f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" '
                f'stroke-width="{w}" stroke-linejoin="round" opacity="0.95"{dash_attr}/>')
    ema20_s = chart.get("ema20_series") or []
    ema50_s = chart.get("ema50_series") or []
    ema200_s= chart.get("ema200_series") or []
    parts.append(_poly(ema20_s,  EMA20_C))
    parts.append(_poly(ema50_s,  EMA50_C))
    parts.append(_poly(ema200_s, EMA200_C, w=1.8))

    # ── Pattern annotations (drawn over candles, under legend)
    patterns = _detect_patterns(chart)
    PATTERN_BG = "#1f2937"
    for idx, pat in enumerate(patterns):
        col = pat["color"]
        anchors = pat.get("anchors") or []
        if not anchors: continue
        pts = [(x_for(i), y_price(p)) for (i, p) in anchors]
        # connecting polyline for multi-anchor patterns
        if len(pts) >= 2:
            poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            parts.append(f'<polyline points="{poly}" fill="none" stroke="{col}" '
                         f'stroke-width="1.6" stroke-dasharray="4,3" opacity="0.85"/>')
        # circle markers at each anchor
        for x, y in pts:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{BG}" '
                         f'stroke="{col}" stroke-width="2"/>')
        # label tag near last anchor, with offset
        lx, ly = pts[-1]
        # offset to keep tags from overlapping each other
        offy = -18 - (idx * 22)
        # if too high, push down on same side
        if ly + offy < pad_t + 6:
            offy = 26 + (idx * 22)
        tx = lx + 10
        ty = ly + offy
        # clamp horizontally
        if tx + 160 > pad_l + chart_w:
            tx = lx - 170
        label = pat["label"]
        note = pat.get("note", "")
        # connector line from anchor to label
        parts.append(f'<line x1="{lx:.1f}" y1="{ly:.1f}" x2="{tx+4:.1f}" y2="{ty+4:.1f}" '
                     f'stroke="{col}" stroke-width="1" opacity="0.7"/>')
        # rounded label box
        text_len = max(len(label), len(note)) * 5.6 + 16
        box_w = min(220, max(110, int(text_len)))
        parts.append(
            f'<g class="tp-pat"><title>{html_mod.escape(label + " — " + note)}</title>'
            f'<rect x="{tx:.1f}" y="{ty-3:.1f}" width="{box_w}" height="30" rx="4" '
            f'fill="{PATTERN_BG}" stroke="{col}" stroke-width="1.2" opacity="0.96"/>'
            f'<text x="{tx+7:.1f}" y="{ty+9:.1f}" font-size="10" font-weight="800" '
            f'fill="{col}">{html_mod.escape(label)}</text>'
            f'<text x="{tx+7:.1f}" y="{ty+22:.1f}" font-size="8.5" '
            f'fill="#cbd5e1">{html_mod.escape(note[:38])}</text>'
            f'</g>'
        )

    # ── Last-price flag on right axis (TV signature)
    last_close = closes[-1]
    last_open  = opens[-1]
    last_color = UP if last_close >= last_open else DOWN
    ly = y_price(last_close)
    parts.append(
        f'<line x1="{pad_l}" y1="{ly:.1f}" x2="{pad_l+chart_w}" y2="{ly:.1f}" '
        f'stroke="{last_color}" stroke-width="1" stroke-dasharray="2,2" opacity="0.6"/>'
        f'<polygon points="{pad_l+chart_w},{ly:.1f} {pad_l+chart_w+5},{ly-7:.1f} '
        f'{pad_l+chart_w+pad_r-2},{ly-7:.1f} {pad_l+chart_w+pad_r-2},{ly+7:.1f} '
        f'{pad_l+chart_w+5},{ly+7:.1f}" fill="{last_color}"/>'
        f'<text x="{pad_l+chart_w+9}" y="{ly+3.5:.1f}" font-size="10.5" font-weight="800" '
        f'fill="#fff" font-variant-numeric="tabular-nums">{last_close:,.2f}</text>'
    )

    # ── Volume profile (right gutter, inside chart but offset left of axis)
    if profile_w > 0:
        vp = chart.get("volume_profile") or []
        if vp:
            vp_max = max(v for _, v in vp) or 1
            pf_x = pad_l + chart_w - profile_w - 4
            bin_h = price_h / len(vp)
            poc_idx = max(range(len(vp)), key=lambda k: vp[k][1])
            for i, (price, v) in enumerate(vp):
                y = y_price(price) - bin_h / 2
                w = (v / vp_max) * profile_w
                color = "#a78bfa" if i == poc_idx else "#3a3f4b"
                parts.append(f'<rect x="{pf_x+profile_w-w:.1f}" y="{y:.1f}" width="{w:.1f}" '
                             f'height="{max(1, bin_h-1):.1f}" fill="{color}" opacity="0.55"/>')
            poc_price = vp[poc_idx][0]
            parts.append(f'<text x="{pf_x+profile_w-4}" y="{y_price(poc_price)-3:.1f}" font-size="8.5" '
                         f'fill="#c4b5fd" font-weight="800" text-anchor="end">POC {poc_price:,.0f}</text>')

    # ── RSI panel
    if has_rsi:
        # 30/70 zones
        y70 = y_rsi(70); y30 = y_rsi(30); y50 = y_rsi(50)
        parts.append(f'<rect x="{pad_l}" y="{y70:.1f}" width="{chart_w}" height="{y30-y70:.1f}" '
                     f'fill="#1a1f2c" opacity="0.45"/>')
        for lvl, lbl, col in [(70,"70","#ef5350"),(50,"50","#5d636f"),(30,"30","#26a69a")]:
            yv = y_rsi(lvl)
            parts.append(f'<line x1="{pad_l}" y1="{yv:.1f}" x2="{pad_l+chart_w}" y2="{yv:.1f}" '
                         f'stroke="{col}" stroke-width="1" stroke-dasharray="2,3" opacity="0.55"/>')
            parts.append(f'<text x="{axis_x}" y="{yv+3:.1f}" font-size="9" fill="{AXIS_TEXT}" '
                         f'font-variant-numeric="tabular-nums">{lbl}</text>')
        # RSI line
        pts = [f"{x_for(i):.1f},{y_rsi(v):.1f}" for i,v in enumerate(rsi_series) if v is not None]
        if len(pts) >= 2:
            parts.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="#e879f9" '
                         f'stroke-width="1.5" stroke-linejoin="round"/>')
        # last RSI flag
        last_rsi = next((v for v in reversed(rsi_series) if v is not None), None)
        if last_rsi is not None:
            ry = y_rsi(last_rsi)
            rsi_col = "#ef5350" if last_rsi >= 70 else "#26a69a" if last_rsi <= 30 else "#e879f9"
            parts.append(
                f'<rect x="{pad_l+chart_w+2}" y="{ry-7:.1f}" width="{pad_r-4}" height="13" rx="2.5" '
                f'fill="{rsi_col}"/>'
                f'<text x="{pad_l+chart_w+5}" y="{ry+3.5:.1f}" font-size="10" font-weight="800" '
                f'fill="#fff" font-variant-numeric="tabular-nums">{last_rsi:.1f}</text>'
            )

    # ── Date axis (month labels, TV-style "Jan 'YY" formatting)
    if n > 1:
        import datetime as _dt
        axis_y = height - 8
        seen: set[str] = set()
        for i, b in enumerate(bars):
            ym = str(b.get("date",""))[:7]
            if not ym or ym in seen: continue
            seen.add(ym)
            try:
                d = _dt.datetime.strptime(ym + "-01", "%Y-%m-%d")
                lbl = d.strftime("%b '%y") if d.month in (1,) else d.strftime("%b")
            except Exception:
                lbl = ym
            xt = x_for(i)
            if xt < pad_l + 18 or xt > pad_l + chart_w - 30: continue
            parts.append(f'<text x="{xt:.1f}" y="{axis_y}" font-size="9.5" text-anchor="middle" '
                         f'fill="{AXIS_TEXT}">{html_mod.escape(lbl)}</text>')

    # ── Legend overlay (top-left): symbol · OHLC of last bar · EMAs with last values
    o0, h0, l0, c0, v0 = opens[-1], highs[-1], lows[-1], closes[-1], vols[-1]
    chg = c0 - o0
    chg_pct = (chg / o0 * 100) if o0 else 0
    chg_color = UP if chg >= 0 else DOWN
    last_e20 = next((v for v in reversed(ema20_s) if v is not None), None)
    last_e50 = next((v for v in reversed(ema50_s) if v is not None), None)
    last_e200= next((v for v in reversed(ema200_s) if v is not None), None)
    def _val(v): return f"{v:,.2f}" if v is not None else "—"
    legend_x = pad_l + 6
    legend_y = pad_t - 22
    legend = (
        f'<text x="{legend_x}" y="{legend_y}" font-size="12" font-weight="800" '
        f'fill="{TEXT_BRIGHT}">{html_mod.escape(symbol or "")} '
        f'<tspan font-size="10" fill="{AXIS_TEXT}" font-weight="600">· 1D · NSE</tspan></text>'
        f'<text x="{legend_x}" y="{legend_y+15}" font-size="10" '
        f'fill="{TEXT}" font-variant-numeric="tabular-nums">'
        f'<tspan fill="{AXIS_TEXT}">O</tspan> {_val(o0)} '
        f'<tspan fill="{AXIS_TEXT}">H</tspan> {_val(h0)} '
        f'<tspan fill="{AXIS_TEXT}">L</tspan> {_val(l0)} '
        f'<tspan fill="{AXIS_TEXT}">C</tspan> <tspan fill="{chg_color}" font-weight="700">{_val(c0)}</tspan> '
        f'<tspan fill="{chg_color}" font-weight="700">{chg:+,.2f} ({chg_pct:+.2f}%)</tspan>'
        f'</text>'
        f'<text x="{legend_x + 480}" y="{legend_y+15}" font-size="10" '
        f'fill="{TEXT}" font-variant-numeric="tabular-nums">'
        f'<tspan fill="{EMA20_C}" font-weight="700">EMA 20</tspan> {_val(last_e20)}   '
        f'<tspan fill="{EMA50_C}" font-weight="700">EMA 50</tspan> {_val(last_e50)}   '
        f'<tspan fill="{EMA200_C}" font-weight="700">EMA 200</tspan> {_val(last_e200)}'
        f'</text>'
    )
    parts.append(legend)

    # ── Crosshair group (hidden until mousemove) + capture overlay + JSON payload
    chart_bottom = (rsi_top + rsi_panel_h) if has_rsi else (vol_top + vol_h)
    import json as _json
    bar_payload = [
        {"d": b.get("date",""), "o": b["open"], "h": b["high"], "l": b["low"],
         "c": b["close"], "v": b["volume"]}
        for b in bars
    ]
    payload = {
        "bars": bar_payload,
        "ema20":  [None if v is None else round(v,3) for v in (chart.get("ema20_series")  or [])],
        "ema50":  [None if v is None else round(v,3) for v in (chart.get("ema50_series")  or [])],
        "ema200": [None if v is None else round(v,3) for v in (chart.get("ema200_series") or [])],
        "rsi":    [None if v is None else round(v,2) for v in (chart.get("rsi_series")    or [])],
    }
    parts.append(
        f'<g class="cx-hover" pointer-events="none" visibility="hidden">'
        f'<line class="cx-v" x1="0" y1="{pad_t}" x2="0" y2="{chart_bottom}" '
        f'stroke="#787b86" stroke-width="1" stroke-dasharray="3,3" opacity="0.85"/>'
        f'<line class="cx-h" x1="{pad_l}" y1="0" x2="{pad_l+chart_w}" y2="0" '
        f'stroke="#787b86" stroke-width="1" stroke-dasharray="3,3" opacity="0.85"/>'
        f'<rect class="cx-pricetag" x="{pad_l+chart_w}" y="-7" width="{pad_r-2}" height="14" rx="2" '
        f'fill="#2a2e39"/>'
        f'<text class="cx-pricetxt" x="{pad_l+chart_w+5}" y="3.5" font-size="10.5" font-weight="800" '
        f'fill="#fff" font-variant-numeric="tabular-nums">—</text>'
        f'<rect class="cx-datetag" x="-30" y="{chart_bottom+2}" width="60" height="14" rx="2" '
        f'fill="#2a2e39"/>'
        f'<text class="cx-datetxt" x="0" y="{chart_bottom+12}" font-size="9.5" '
        f'text-anchor="middle" fill="#fff" font-weight="700">—</text>'
        f'<g class="cx-tooltip" transform="translate(0,0)">'
        f'<rect class="cx-tipbg" x="0" y="0" width="170" height="118" rx="4" '
        f'fill="#1e222d" stroke="#363a45" stroke-width="1" opacity="0.97"/>'
        f'<text class="cx-tiptxt" x="8" y="14" font-size="10.5" '
        f'fill="#d1d4dc" font-family="-apple-system,Inter,sans-serif" '
        f'font-variant-numeric="tabular-nums"></text>'
        f'</g></g>'
    )
    # capture overlay (above everything in event-order)
    parts.append(
        f'<rect class="cx-area" x="{pad_l}" y="{pad_t}" '
        f'width="{chart_w}" height="{chart_bottom-pad_t}" '
        f'fill="transparent" pointer-events="all" style="cursor:crosshair"/>'
    )
    # JSON data block adjacent to SVG (in DOM order — script reads via id-suffix)
    parts.append('</svg>')
    parts.append(
        f'<script type="application/json" id="{chart_id}-data">'
        f'{_json.dumps(payload, separators=(",", ":"))}'
        f'</script>'
    )
    return "".join(parts)


def _hbar(label: str, value: float | None, max_val: float, color_hint: str = "blue") -> str:
    # Append info icon if we have a definition for this metric
    try:
        tip = _METRIC_TOOLTIPS.get(label) or _METRIC_TOOLTIPS.get(label.split("(")[0].strip())
    except Exception:
        tip = None
    info_html = (f'<span class="tp-info" title="{html_mod.escape(tip)}">i</span>'
                 if tip else "")
    label_html = f'{html_mod.escape(label)}{info_html}'
    if value is None:
        return f'<div class="tp-bar"><span class="lab">{label_html}</span><span class="trk"></span><span class="val">—</span></div>'
    try: v = float(value)
    except (TypeError, ValueError): v = 0.0
    pct = max(0.0, min(100.0, (v / max_val) * 100)) if max_val else 0
    color_cls = ""
    if color_hint == "auto":
        ratio = v / max_val if max_val else 0
        color_cls = "green" if ratio >= 0.7 else "amber" if ratio >= 0.4 else "red"
    elif color_hint in ("green","amber","red"):
        color_cls = color_hint
    return (f'<div class="tp-bar"><span class="lab">{label_html}</span>'
            f'<span class="trk"><span class="fill {color_cls}" style="width:{pct:.1f}%"></span></span>'
            f'<span class="val">{v:.1f}</span></div>')


# ─────────────────────────────────────────────────────────────────────────────
# CANSLIM (O'Neil) component breakdown — recomputes the 5 stored components
# (C/A/N/S/L) using the same thresholds as fixed_nse_universe_analysis.py so
# the sum reproduces snap.can_slim_score, and adds two informational signals
# (I = institutional, M = market) sourced from fundamentals + market regime.
# ─────────────────────────────────────────────────────────────────────────────
def _canslim_breakdown(snap: dict, tech: dict, fund: dict | None,
                       qtr: list[dict], ann: list[dict],
                       parsed: dict | None, market_regime: str | None = None) -> dict:
    fund = fund or {}
    parsed = parsed or {}
    comps: dict[str, dict] = {}

    # ── Enrich parsed from stage_snapshots.fund_details when scores.fundamentals
    #    is incomplete (e.g. newly listed or not yet backfilled).
    #    snap["fund_details"] is a jsonb dict coming from the PG query in get_snapshot().
    if not parsed.get("pat_yoy_pct"):
        raw_fd = snap.get("fund_details") if snap else None
        if raw_fd:
            try:
                fd_dict = raw_fd if isinstance(raw_fd, dict) else json.loads(raw_fd)
                snap_fund = {"pnl_summary": fd_dict.get("pnl_summary"),
                             "quarterly_summary": fd_dict.get("quarterly_summary"),
                             "balance_sheet_summary": fd_dict.get("balance_sheet_summary"),
                             "ratios_summary": fd_dict.get("ratios_summary"),
                             "investor_summary": fd_dict.get("investor_summary")}
                snap_parsed = _parse_summaries(snap_fund)
                # Merge: snap_parsed fills gaps in parsed without overwriting real data
                for k, v in snap_parsed.items():
                    if v is not None and parsed.get(k) is None:
                        parsed[k] = v
            except (TypeError, ValueError, KeyError):
                pass

    # ── C: Current quarterly earnings (5 pts)
    #   Tier 1 (real):   structured scores.quarterly_results — PAT YoY (same quarter last year)
    #   Tier 2 (real):   fund_details.pnl_summary parsed pat_yoy_pct — still actual reported data
    #   Tier 3 (real):   fund_details.quarterly_summary pat_q_trend — derive QoQ from last 4 qtrs
    #   Tier 4 (proxy):  20-day price momentum — last resort when no financial data exists at all
    c_score = None; c_label = "—"; c_method = ""
    try:
        if len(qtr) >= 5 and qtr[0].get("pat") and qtr[4].get("pat"):
            p_now, p_yoy = float(qtr[0]["pat"]), float(qtr[4]["pat"])
            if p_yoy != 0:
                g = (p_now - p_yoy) / abs(p_yoy)
                c_score = 5 if g > 0.25 else 3 if g > 0.10 else 1 if g > 0 else 0
                c_label = f"PAT YoY {g*100:+.1f}%"; c_method = "real"
    except Exception:
        pass
    # Tier 2: pat_yoy_pct from parsed fund_details (actual YoY from screener.in summary)
    if c_score is None and parsed.get("pat_yoy_pct") is not None:
        try:
            g = float(parsed["pat_yoy_pct"]) / 100.0
            c_score = 5 if g > 0.25 else 3 if g > 0.10 else 1 if g > 0 else 0
            c_label = f"PAT YoY {g*100:+.1f}% (fund_details)"; c_method = "real"
        except (TypeError, ValueError):
            pass
    # Tier 3: quarterly trend from fund_details — use most recent quarter vs year-ago quarter
    if c_score is None and parsed.get("pat_q_trend") and len(parsed["pat_q_trend"]) >= 4:
        try:
            qt = parsed["pat_q_trend"]
            # qt[0] = oldest visible, qt[-1] = most recent; derive Q1 vs Q1 last year
            # With 4 quarters: [Q-4, Q-3, Q-2, Q-1] → QoQ trend as C-signal proxy
            q_now, q_yoy = float(qt[-1]), float(qt[0])
            if q_yoy != 0:
                g = (q_now - q_yoy) / abs(q_yoy)
                c_score = 5 if g > 0.25 else 3 if g > 0.10 else 1 if g > 0 else 0
                c_label = f"Qtr trend {g*100:+.1f}% (4Q)"; c_method = "real"
        except (TypeError, ValueError, IndexError):
            pass
    # Tier 4: 20-day price momentum proxy (last resort — no financial data at all)
    if c_score is None:
        m20 = (tech.get("ret_1m") or 0) / 100.0 if tech.get("ret_1m") is not None else None
        if m20 is not None:
            c_score = 5 if m20 > 0.10 else 3 if m20 > 0.05 else 1 if m20 > 0 else 0
            c_label = f"1M return {m20*100:+.1f}% (proxy)"; c_method = "proxy"
    comps["C"] = {"name": "Current Earnings", "score": c_score, "max": 5,
                  "detail": c_label, "method": c_method}

    # ── A: Annual earnings growth (5 pts)
    #   Tier 1 (real):  structured scores.annual_results — PAT CAGR 3Y/2Y
    #   Tier 2 (real):  fund_details.pnl_summary pat_yoy_pct as a 1Y growth signal
    #   Tier 3 (real):  quarterly trend — annualise trailing 4Q vs prior 4Q if available
    #   Tier 4 (proxy): 3M price momentum
    a_score = None; a_label = "—"; a_method = ""
    try:
        if len(ann) >= 3:
            p_now = float(ann[0].get("pat") or 0)
            p_back = float(ann[2].get("pat") or 0)
            years = 2
        elif len(ann) >= 2:
            p_now = float(ann[0].get("pat") or 0)
            p_back = float(ann[1].get("pat") or 0)
            years = 1
        else:
            p_now = p_back = 0; years = 0
        if p_now > 0 and p_back > 0 and years > 0:
            cagr = (p_now / p_back) ** (1 / years) - 1
            a_score = 5 if cagr > 0.25 else 3 if cagr > 0.15 else 1 if cagr > 0.05 else 0
            a_label = f"PAT CAGR {cagr*100:+.1f}% ({years}Y)"; a_method = "real"
    except Exception:
        pass
    # Tier 2: pat_yoy_pct from fund_details pnl_summary (1Y growth, real reported data)
    if a_score is None and parsed.get("pat_yoy_pct") is not None:
        try:
            g = float(parsed["pat_yoy_pct"]) / 100.0
            a_score = 5 if g > 0.25 else 3 if g > 0.15 else 1 if g > 0.05 else 0
            a_label = f"PAT YoY {g*100:+.1f}% (fund_details 1Y)"; a_method = "real"
        except (TypeError, ValueError):
            pass
    # Tier 3: annualise trailing 4Q vs prior 4Q from quarterly trend
    if a_score is None and parsed.get("pat_q_trend") and len(parsed["pat_q_trend"]) >= 4:
        try:
            qt = parsed["pat_q_trend"]
            ttm_now  = sum(float(v) for v in qt[-4:]) if len(qt) >= 4 else None
            ttm_prev = sum(float(v) for v in qt[:4])  if len(qt) >= 8 else None
            if ttm_now and ttm_prev and ttm_prev != 0:
                g = (ttm_now - ttm_prev) / abs(ttm_prev)
                a_score = 5 if g > 0.25 else 3 if g > 0.15 else 1 if g > 0.05 else 0
                a_label = f"TTM PAT {g*100:+.1f}% (4Q vs 4Q)"; a_method = "real"
        except (TypeError, ValueError, IndexError):
            pass
    # Tier 4: 3M price momentum proxy (last resort)
    if a_score is None:
        m3 = (tech.get("ret_3m") or 0) / 100.0 if tech.get("ret_3m") is not None else None
        if m3 is not None:
            a_score = 5 if m3 > 0.20 else 3 if m3 > 0.10 else 1 if m3 > 0.05 else 0
            a_label = f"3M return {m3*100:+.1f}% (proxy)"; a_method = "proxy"
    comps["A"] = {"name": "Annual Earnings", "score": a_score, "max": 5,
                  "detail": a_label, "method": a_method}

    # ── N: New Highs / Volume (5 pts)
    #   Volume surge (institutional accumulation) + distance from 52-week high.
    #   These are the standard O'Neil N screener signals — computed from real
    #   market data, not an inferior substitute. Method = "derived".
    n_score = None; n_label = "—"; n_method = "derived"
    vr = tech.get("last_vol_ratio")
    dfh = tech.get("dist_from_high_pct")
    if vr is not None:
        try:
            vr_f = float(vr)
            n_score = 5 if vr_f > 2.0 else 3 if vr_f > 1.5 else 1 if vr_f > 1.0 else 0
            n_label = f"Vol {vr_f:.1f}x 20d avg"
        except Exception:
            pass
    if n_score is None and dfh is not None:
        try:
            d = float(dfh)
            n_score = 5 if d > -5 else 3 if d > -15 else 1 if d > -25 else 0
            n_label = f"{d:+.1f}% from 52w high"
        except Exception:
            pass
    comps["N"] = {"name": "New Highs / Volume", "score": n_score, "max": 5,
                  "detail": n_label, "method": n_method}

    # ── S: Supply & Demand (5 pts)
    #   EMA stack (price > EMA50 > EMA200) — this IS the O'Neil demand signal.
    #   Institutional demand is proven by price staying above its moving averages.
    #   Method = "derived" (real price data, not an earnings proxy).
    s_score = None; s_label = "—"; s_method = "derived"
    try:
        last = float(tech.get("last") or 0)
        e50 = float(tech.get("ema50") or 0)
        e200 = float(tech.get("ema200") or 0)
        if last and e50 and e200:
            if last > e50 > e200: s_score, s_label = 5, "Price > EMA50 > EMA200 (full stack)"
            elif last > e50:       s_score, s_label = 3, "Price > EMA50 (partial stack)"
            elif last > e200:      s_score, s_label = 1, "Price > EMA200 only"
            else:                  s_score, s_label = 0, "Below key EMAs"
    except Exception:
        pass
    comps["S"] = {"name": "Supply / Demand", "score": s_score, "max": 5,
                  "detail": s_label, "method": s_method}

    # ── L: Leader vs Laggard (5 pts) — relative strength vs Nifty 500
    l_score = None; l_label = "—"; l_method = "real"
    rs = snap.get("relative_strength") if snap else None
    if rs is not None:
        try:
            rs_f = float(rs)
            # Upstream uses raw decimals (0.10 = 10pp outperformance). Our DB
            # stores percentage points already (e.g. 12 = 12pp), so scale /100.
            rs_dec = rs_f / 100.0
            l_score = 5 if rs_dec > 0.10 else 3 if rs_dec > 0.05 else 1 if rs_dec > 0 else 0
            l_label = f"RS {rs_f:+.1f}pp vs Nifty 500"
        except Exception:
            pass
    comps["L"] = {"name": "Leader (RS)", "score": l_score, "max": 5,
                  "detail": l_label, "method": l_method}

    # ── I: Institutional Sponsorship (informational, 0-5 — NOT in stored total)
    i_score = None; i_label = "—"; i_method = "real"
    fii = parsed.get("fii_pct"); dii = parsed.get("dii_pct")
    if fii is not None or dii is not None:
        try:
            inst = (float(fii or 0) + float(dii or 0))
            i_score = 5 if inst > 30 else 3 if inst > 15 else 1 if inst > 5 else 0
            i_label = f"FII+DII {inst:.1f}%"
        except Exception:
            pass
    comps["I"] = {"name": "Institutional", "score": i_score, "max": 5,
                  "detail": i_label, "method": i_method,
                  "informational": True}

    # ── M: Market direction (informational, 0-5) — uses caller-supplied regime
    m_score = None; m_label = "—"; m_method = "context"
    if market_regime:
        mr = str(market_regime).lower()
        if any(k in mr for k in ("bull", "risk-on", "uptrend", "trending up", "strong")):
            m_score, m_label = 5, f"Market: {market_regime}"
        elif any(k in mr for k in ("bear", "risk-off", "downtrend", "weak")):
            m_score, m_label = 0, f"Market: {market_regime}"
        else:
            m_score, m_label = 3, f"Market: {market_regime}"
    comps["M"] = {"name": "Market Direction", "score": m_score, "max": 5,
                  "detail": m_label, "method": m_method,
                  "informational": True}

    # CANSL composite (the 5 components in the stored 25-pt score)
    core = [comps[k]["score"] for k in ("C", "A", "N", "S", "L")
            if comps[k]["score"] is not None]
    composite_25 = sum(core) if core else None

    return {
        "components": comps,
        "composite_25": composite_25,
        "stored_total": snap.get("can_slim_score") if snap else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Data access
# ─────────────────────────────────────────────────────────────────────────────
def _connect():
    return psycopg2.connect(PG_DSN)


def _resolve_snapshot_date(conn, override: str | None) -> str:
    if override:
        return override
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(snapshot_date)::text FROM scores.stage_snapshots")
        row = cur.fetchone()
    if not row or not row[0]:
        raise RuntimeError("No snapshots in scores.stage_snapshots")
    return row[0]


def _fetchall(conn, sql: str, params: tuple = ()) -> list[dict]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _fetchone(conn, sql: str, params: tuple = ()) -> dict | None:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        return cur.fetchone()


# ─────────────────────────────────────────────────────────────────────────────
# Pick selection — four-signal pipeline
#
# Signal 1: Dynamic sector rotation rank (scores.sector_top_stocks)
# Signal 2: Stage 2 VCP-confirmed picks  (scores.stage2_vcp_picks)
# Signal 3: Stage 2 universe             (scores.stage_snapshots WHERE stage=S2)
# Signal 4: Composite investment_score   (ties/fallback)
#
# Conviction tiers:
#   "vcp+sector"  — appears in both top-VCP picks AND a top-ranked sector  ★★★
#   "sector+s2"   — Stage 2 stock from a dynamically top-ranked sector     ★★
#   "vcp"         — VCP pick not in top sector (strong pattern, weak sector) ★★
#   "sector_rot"  — non-Stage-2 top of a leading sector                    ★
#   "stage2"      — Stage 2 fallback when above tiers are exhausted        ★
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class PickRationale:
    symbol: str
    sector: str
    source: str      # "vcp+sector" | "sector+s2" | "vcp" | "sector_rot" | "stage2"
    sector_rot_score: float | None
    stage2_score: float | None
    vcp_score: float | None
    sector_strength: float | None
    rationale: str


_SECTOR_EXCLUDE = frozenset({
    "Other", "N/A", "", "Unknown", "Miscellaneous",
})

def _load_top_sectors(conn, snap_date: str, top_n: int = 10) -> dict[str, float]:
    """Return {sector_name: sector_strength} for the top-N dynamically ranked sectors.

    Uses scores.sector_top_stocks (written by sector_rotation_tracker).
    Excludes generic catch-all buckets ("Other", "N/A", etc.) so sector
    rotation signal reflects actual thematic momentum.
    Falls back to a curated default list when no recent data is available.
    """
    # Find the freshest score_date on or before snap_date
    rows = _fetchall(conn, """
        SELECT sector_name, AVG(sector_strength) AS strength
        FROM scores.sector_top_stocks
        WHERE score_date = (
            SELECT MAX(score_date) FROM scores.sector_top_stocks
            WHERE score_date <= %s
        )
        GROUP BY sector_name
        ORDER BY strength DESC NULLS LAST
        LIMIT %s
    """, (snap_date, top_n + len(_SECTOR_EXCLUDE) + 5))
    if rows:
        filtered = [
            r for r in rows
            if (r["sector_name"] or "").strip() not in _SECTOR_EXCLUDE
        ][:top_n]
        if filtered:
            return {r["sector_name"]: float(r["strength"] or 0) for r in filtered}
    # Fallback: curated default when no sector_top_stocks data exists
    return {s: 70.0 for s in (
        "Capital Goods & Industrials", "EV & Auto Ancillaries",
        "Metals & Mining", "Pharma & Healthcare", "IT & Technology",
        "Defence & Aerospace", "Capital Markets", "Chemicals & Specialty",
        "Energy - Power", "PSU / CPSE",
    )}


def _load_vcp_picks(conn, snap_date: str, min_inv_score: float = 55.0) -> list[dict]:
    """Stage 2 VCP-confirmed picks from scores.stage2_vcp_picks."""
    return _fetchall(conn, """
        SELECT symbol, sector, price, investment_score, enhanced_fund_score,
               vcp_score, vcp_breakout_pct, vcp_contraction_pct,
               rsi, relative_strength, trading_signal, trend_signal,
               supertrend_state, narrative, fund_details
        FROM scores.stage2_vcp_picks
        WHERE snapshot_date = (
            SELECT MAX(snapshot_date) FROM scores.stage2_vcp_picks
            WHERE snapshot_date <= %s
        )
          AND investment_score >= %s
          AND supertrend_state = 'BULLISH'
        ORDER BY investment_score DESC NULLS LAST
        LIMIT 40
    """, (snap_date, min_inv_score))


def _load_stage2_leaders(conn, snap_date: str) -> list[dict]:
    """Stage 2 universe from the latest snapshot."""
    return _fetchall(conn, """
        SELECT symbol, sector, price, technical_score, relative_strength,
               enhanced_fund_score, investment_score, trading_signal,
               trend_signal, stance, stage
        FROM scores.stage_snapshots
        WHERE snapshot_date=%s
          AND stage='STAGE_2'
          AND supertrend_state='BULLISH'
          AND trend_signal IN ('BULLISH','STRONG_BULLISH')
        ORDER BY investment_score DESC NULLS LAST
        LIMIT 50
    """, (snap_date,))


_MAX_PER_SECTOR = 2   # cap to ensure diversification across sectors

def build_pick_list(conn, snap_date: str, n: int = MAX_PICKS) -> list[PickRationale]:
    """Build ranked pick list using four aligned signals."""
    top_sectors     = _load_top_sectors(conn, snap_date, top_n=12)
    vcp_picks       = _load_vcp_picks(conn, snap_date)
    stage2_leaders  = _load_stage2_leaders(conn, snap_date)

    vcp_syms  = {r["symbol"]: r for r in vcp_picks}
    st2_syms  = {r["symbol"]: r for r in stage2_leaders}

    picks: list[PickRationale] = []
    seen: set[str] = set()
    per_sector: dict[str, int] = {}

    def _add(sym: str, row: dict, source: str, rationale: str,
             vcp_row: dict | None = None) -> None:
        if sym in seen or len(picks) >= n:
            return
        sect = (row.get("sector") or "").strip()
        # Enforce diversification cap (higher-conviction tiers bypass it slightly)
        bypass = source in ("vcp+sector",)
        sector_cap = _MAX_PER_SECTOR + (1 if bypass else 0)
        if sect and per_sector.get(sect, 0) >= sector_cap:
            return
        per_sector[sect] = per_sector.get(sect, 0) + 1
        picks.append(PickRationale(
            symbol=sym,
            sector=row.get("sector") or "",
            source=source,
            sector_rot_score=float(row.get("investment_score") or 0),
            stage2_score=float(st2_syms[sym]["investment_score"] or 0) if sym in st2_syms else None,
            vcp_score=float((vcp_row or {}).get("vcp_score") or 0) if vcp_row else None,
            sector_strength=top_sectors.get(row.get("sector") or "", None),
            rationale=rationale,
        ))
        seen.add(sym)

    # ── Tier 1: VCP-confirmed + in a top-ranked sector  ───────────────────
    for r in vcp_picks:
        sym = r["symbol"]
        sect = r.get("sector") or ""
        if sect not in top_sectors:
            continue
        strength = top_sectors[sect]
        inv  = float(r.get("investment_score") or 0)
        vcp  = float(r.get("vcp_score") or 0)
        _add(sym, r, "vcp+sector",
             f"VCP-confirmed Stage 2 (vcp={vcp:.0f}, inv={inv:.1f}) "
             f"in top-ranked sector {sect} (strength={strength:.0f})",
             vcp_row=r)

    # ── Tier 2: Stage 2 + top-ranked sector (no VCP confirmation needed) ──
    for r in stage2_leaders:
        if len(picks) >= n: break
        sym  = r["symbol"]
        sect = r.get("sector") or ""
        if sect not in top_sectors:
            continue
        inv  = float(r.get("investment_score") or 0)
        strength = top_sectors[sect]
        vcp_row  = vcp_syms.get(sym)
        src = "vcp+sector" if vcp_row else "sector+s2"
        _add(sym, r, src,
             f"Stage 2 leader in top sector {sect} (strength={strength:.0f}), "
             f"inv={inv:.1f}" + (f", VCP confirmed" if vcp_row else ""),
             vcp_row=vcp_row)

    # ── Tier 3: VCP picks not already included ────────────────────────────
    for r in vcp_picks:
        if len(picks) >= n: break
        sym  = r["symbol"]
        inv  = float(r.get("investment_score") or 0)
        vcp  = float(r.get("vcp_score") or 0)
        _add(sym, r, "vcp",
             f"VCP-confirmed Stage 2 (vcp={vcp:.0f}, inv={inv:.1f}); "
             f"sector {r.get('sector','')} not in current top-10 rotation",
             vcp_row=r)

    # ── Tier 4: Stage 2 leaders by investment_score (broad fallback) ──────
    for r in stage2_leaders:
        if len(picks) >= n: break
        sym = r["symbol"]
        inv = float(r.get("investment_score") or 0)
        _add(sym, r, "stage2",
             f"Stage 2 momentum leader; inv={inv:.1f}, "
             f"fund={r.get('enhanced_fund_score')}")

    return picks[:n]


# ─────────────────────────────────────────────────────────────────────────────
# Per-stock technical + fundamental deep dive
# ─────────────────────────────────────────────────────────────────────────────
def _ema(values: list[float], span: int) -> float | None:
    if len(values) < span:
        return None
    k = 2 / (span + 1)
    e = sum(values[:span]) / span
    for v in values[span:]:
        e = v * k + e * (1 - k)
    return e


def _ema_series(values: list[float], span: int) -> list[float | None]:
    """Full EMA series aligned to `values` (None until enough warmup)."""
    out: list[float | None] = [None] * len(values)
    if len(values) < span:
        return out
    k = 2 / (span + 1)
    e = sum(values[:span]) / span
    out[span - 1] = e
    for i in range(span, len(values)):
        e = values[i] * k + e * (1 - k)
        out[i] = e
    return out


def _rsi_series(closes: list[float], period: int = 14) -> list[float | None]:
    """Wilder-smoothed RSI(14) series aligned to closes (None until warmup)."""
    n = len(closes)
    out: list[float | None] = [None] * n
    if n <= period:
        return out
    gains, losses = [], []
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    rs = avg_g / avg_l if avg_l > 0 else 999
    out[period] = 100 - 100 / (1 + rs)
    for i in range(period + 1, n):
        d = closes[i] - closes[i - 1]
        g = max(d, 0); l_ = max(-d, 0)
        avg_g = (avg_g * (period - 1) + g) / period
        avg_l = (avg_l * (period - 1) + l_) / period
        rs = avg_g / avg_l if avg_l > 0 else 999
        out[i] = 100 - 100 / (1 + rs)
    return out


def _swing_levels(highs: list[float], lows: list[float], window: int = 5,
                  top_n: int = 3, tolerance: float = 0.015) -> tuple[list[float], list[float]]:
    """Detect swing highs/lows (local extrema), cluster nearby ones, return top-N levels."""
    n = len(highs)
    swing_h, swing_l = [], []
    for i in range(window, n - window):
        if highs[i] == max(highs[i - window:i + window + 1]):
            swing_h.append(highs[i])
        if lows[i] == min(lows[i - window:i + window + 1]):
            swing_l.append(lows[i])

    def _cluster(vals: list[float], reverse: bool) -> list[float]:
        if not vals: return []
        vals_sorted = sorted(vals, reverse=reverse)
        merged: list[float] = []
        for v in vals_sorted:
            if not merged or abs(v - merged[-1]) / merged[-1] > tolerance:
                merged.append(v)
            else:
                merged[-1] = (merged[-1] + v) / 2
            if len(merged) >= top_n:
                break
        return merged

    return _cluster(swing_h, reverse=True), _cluster(swing_l, reverse=False)


def _pivots_classic(h: float, l: float, c: float) -> dict:
    pp = (h + l + c) / 3
    return {
        "PP": pp,
        "R1": 2 * pp - l, "S1": 2 * pp - h,
        "R2": pp + (h - l), "S2": pp - (h - l),
        "R3": h + 2 * (pp - l), "S3": l - 2 * (h - pp),
    }


def _weekly_pivots(highs: list[float], lows: list[float], closes: list[float]) -> dict:
    """Pivots based on last 5 trading days (≈ last week) — more useful on a 6-month chart."""
    if len(highs) < 5:
        return _pivots_classic(highs[-1], lows[-1], closes[-1])
    h = max(highs[-5:]); l = min(lows[-5:]); c = closes[-1]
    return _pivots_classic(h, l, c)


def _volume_profile(highs: list[float], lows: list[float], vols: list[float],
                    bins: int = 24) -> list[tuple[float, float]]:
    if not highs: return []
    pmin, pmax = min(lows), max(highs)
    if pmax <= pmin: return []
    step = (pmax - pmin) / bins
    buckets = [0.0] * bins
    for h_, l_, v in zip(highs, lows, vols):
        # distribute bar volume evenly across bins it spans
        b_lo = max(0, min(bins - 1, int((l_ - pmin) / step)))
        b_hi = max(0, min(bins - 1, int((h_ - pmin) / step)))
        span = max(1, b_hi - b_lo + 1)
        share = v / span
        for b in range(b_lo, b_hi + 1):
            buckets[b] += share
    return [(pmin + (i + 0.5) * step, buckets[i]) for i in range(bins)]


def compute_technicals(conn, sym: str, snap_date: str) -> dict:
    rows = _fetchall(conn, """
        SELECT trade_date, open, high, low, close, volume
        FROM market.equity_eod
        WHERE symbol=%s AND series='EQ' AND trade_date <= %s
        ORDER BY trade_date DESC LIMIT 260
    """, (sym, snap_date))
    if not rows or len(rows) < 30:
        return {"error": f"insufficient EOD ({len(rows)} rows)"}
    rows = list(reversed(rows))
    closes = [float(r["close"]) for r in rows]
    highs = [float(r["high"]) for r in rows]
    lows = [float(r["low"]) for r in rows]
    vols = [float(r["volume"] or 0) for r in rows]
    n = len(closes)
    last = closes[-1]

    ema20, ema50, ema200 = _ema(closes, 20), _ema(closes, 50), _ema(closes, 200)

    # RSI(14)
    rsi = None
    if n >= 15:
        gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, 15)]
        losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, 15)]
        avg_g = sum(gains) / 14
        avg_l = sum(losses) / 14
        for i in range(15, n):
            d = closes[i] - closes[i - 1]
            g = max(d, 0)
            l_ = max(-d, 0)
            avg_g = (avg_g * 13 + g) / 14
            avg_l = (avg_l * 13 + l_) / 14
        rs = avg_g / avg_l if avg_l > 0 else 999
        rsi = 100 - 100 / (1 + rs)

    # ATR(14)
    atr = None
    if n >= 15:
        trs = []
        for i in range(1, n):
            tr = max(highs[i] - lows[i],
                     abs(highs[i] - closes[i - 1]),
                     abs(lows[i] - closes[i - 1]))
            trs.append(tr)
        atr = sum(trs[-14:]) / 14

    win = min(252, n)
    wh = max(highs[-win:])
    wl = min(lows[-win:])
    dist_high = (last - wh) / wh * 100

    def _ret(d: int) -> float | None:
        return None if n <= d else (last / closes[-d - 1] - 1) * 100

    ema50_slope_pct = None
    if ema50 and n >= 70:
        prev = _ema(closes[:-20], 50)
        if prev:
            ema50_slope_pct = (ema50 - prev) / prev * 100

    vol20 = sum(vols[-20:]) / 20 if n >= 20 else None
    last_vol_ratio = vols[-1] / vol20 if vol20 else None

    # ── Chart data: last ~130 bars (≈6 months) with EMA series, S/R, pivots, vol profile
    CHART_BARS = 130
    bars_slice = rows[-CHART_BARS:] if n >= CHART_BARS else rows
    closes_c = [float(r["close"]) for r in bars_slice]
    highs_c = [float(r["high"]) for r in bars_slice]
    lows_c = [float(r["low"]) for r in bars_slice]
    opens_c = [float(r["open"]) for r in bars_slice]
    vols_c = [float(r["volume"] or 0) for r in bars_slice]
    dates_c = [str(r["trade_date"]) for r in bars_slice]
    ema20_s_full = _ema_series(closes, 20)
    ema50_s_full = _ema_series(closes, 50)
    ema200_s_full = _ema_series(closes, 200)
    rsi_s_full = _rsi_series(closes, 14)
    chart_offset = n - len(bars_slice)
    ema20_s = ema20_s_full[chart_offset:]
    ema50_s = ema50_s_full[chart_offset:]
    ema200_s = ema200_s_full[chart_offset:]
    rsi_s = rsi_s_full[chart_offset:]
    res_levels, sup_levels = _swing_levels(highs_c, lows_c, window=5, top_n=3)
    pivots = _weekly_pivots(highs_c, lows_c, closes_c)
    vol_profile = _volume_profile(highs_c, lows_c, vols_c, bins=24)

    chart_bars = [
        {"date": dates_c[i], "open": opens_c[i], "high": highs_c[i],
         "low": lows_c[i], "close": closes_c[i], "volume": vols_c[i]}
        for i in range(len(bars_slice))
    ]

    return {
        "trade_date": rows[-1]["trade_date"],
        "last": last,
        "ema20": ema20, "ema50": ema50, "ema200": ema200,
        "ema50_slope_pct": ema50_slope_pct,
        "rsi": rsi,
        "atr": atr, "atr_pct": (atr / last * 100) if atr else None,
        "wk52_high": wh, "wk52_low": wl,
        "dist_from_high_pct": dist_high,
        "ret_1m": _ret(21), "ret_3m": _ret(63),
        "ret_6m": _ret(126), "ret_1y": _ret(252),
        "last_vol_ratio": last_vol_ratio,
        # chart payload
        "chart": {
            "bars": chart_bars,
            "ema20_series": ema20_s,
            "ema50_series": ema50_s,
            "ema200_series": ema200_s,
            "rsi_series": rsi_s,
            "support_levels": sup_levels,
            "resistance_levels": res_levels,
            "pivots": pivots,
            "volume_profile": vol_profile,
            "wk52_high": wh, "wk52_low": wl,
        },
    }


def get_snapshot(conn, sym: str, snap_date: str) -> dict | None:
    return _fetchone(conn, """
        SELECT * FROM scores.stage_snapshots
        WHERE snapshot_date=%s AND symbol=%s
    """, (snap_date, sym))


# ─────────────────────────────────────────────────────────────────────────────
# Structured financials (P&L, BS, CF, Fund-score breakdown, Sector context, News)
# ─────────────────────────────────────────────────────────────────────────────
def get_quarterly(conn, sym: str, n: int = 8) -> list[dict]:
    return _fetchall(conn, """
        SELECT period_label, period_end, revenue, operating_profit, opm_pct,
               pat, eps, interest, tax_pct
        FROM scores.quarterly_results
        WHERE symbol=%s ORDER BY period_end DESC LIMIT %s
    """, (sym, n))


def get_annual(conn, sym: str, n: int = 5) -> list[dict]:
    return _fetchall(conn, """
        SELECT period_label, period_end, revenue, operating_profit, opm_pct,
               pat, eps, dividend_payout_pct, pbt, interest, depreciation, expenses
        FROM scores.annual_results
        WHERE symbol=%s ORDER BY period_end DESC LIMIT %s
    """, (sym, n))


def get_balance_sheet(conn, sym: str, n: int = 3) -> list[dict]:
    return _fetchall(conn, """
        SELECT period_label, period_end, equity_capital, reserves,
               borrowings, net_debt, total_assets, fixed_assets, investments
        FROM scores.balance_sheet
        WHERE symbol=%s ORDER BY period_end DESC LIMIT %s
    """, (sym, n))


def get_cash_flow(conn, sym: str, n: int = 3) -> list[dict]:
    return _fetchall(conn, """
        SELECT period_label, period_end, operating_cf, investing_cf,
               financing_cf, net_cf
        FROM scores.cash_flow
        WHERE symbol=%s ORDER BY period_end DESC LIMIT %s
    """, (sym, n))


def get_fund_score_breakdown(conn, sym: str) -> dict | None:
    return _fetchone(conn, """
        SELECT score_date, enhanced_fund_score, earnings_quality,
               sales_growth, financial_strength, institutional_backing
        FROM scores.fundamental_scores
        WHERE symbol=%s ORDER BY score_date DESC LIMIT 1
    """, (sym,))


def get_sector_context(conn, sector: str, snap_date: str) -> dict | None:
    """Sector-level read: strength, peer rank stats."""
    row = _fetchone(conn, """
        SELECT sector_name, sector_strength, total_stocks,
               AVG(relative_strength) AS avg_rs,
               AVG(technical_score) AS avg_tech,
               AVG(enhanced_fund_score) AS avg_fund
        FROM scores.sector_top_stocks
        WHERE sector_name=%s
          AND score_date=(SELECT MAX(score_date) FROM scores.sector_top_stocks WHERE sector_name=%s)
        GROUP BY sector_name, sector_strength, total_stocks
    """, (sector, sector))
    return row


def get_corporate_events(conn, sym: str, days_past: int = 90,
                          days_future: int = 90) -> list[dict]:
    """Corporate events for ``sym`` within a symmetric window.

    Many actions (ex-dividend, results, board meetings) are *future-dated* —
    the previous past-only window of 90d hid these. We now include both
    recent history and the next 90 days so the report surfaces upcoming
    catalysts as well as completed ones.
    """
    return _fetchall(conn, """
        SELECT event_date, event_type, purpose_raw, detail
        FROM signals.corporate_events
        WHERE symbol=%s
          AND event_date >= (CURRENT_DATE - INTERVAL '%s days')
          AND event_date <= (CURRENT_DATE + INTERVAL '%s days')
        ORDER BY event_date DESC LIMIT 15
    """, (sym, days_past, days_future))


def get_insider_activity(conn, sym: str, days: int = 90) -> list[dict]:
    return _fetchall(conn, """
        SELECT alert_date, alert_type, entity, value_cr, category, insider_score
        FROM signals.insider_alerts
        WHERE symbol=%s AND alert_date >= (CURRENT_DATE - INTERVAL '%s days')
        ORDER BY alert_date DESC LIMIT 10
    """, (sym, days))


def get_bulk_block_deals(conn, sym: str, days: int = 90) -> list[dict]:
    """Fallback news flow: bulk & block deals from `signals.bulk_block_deals`."""
    return _fetchall(conn, """
        SELECT deal_date, deal_type, side, entity, qty, price, remarks
        FROM signals.bulk_block_deals
        WHERE symbol=%s AND deal_date >= (CURRENT_DATE - INTERVAL '%s days')
        ORDER BY deal_date DESC LIMIT 10
    """, (sym, days))


def get_upcoming_events(conn, sym: str) -> list[dict]:
    """Forward-looking corporate calendar from `signals.v_upcoming_events`."""
    try:
        return _fetchall(conn, """
            SELECT event_date, event_type, detail
            FROM signals.v_upcoming_events
            WHERE symbol=%s
            ORDER BY event_date ASC LIMIT 5
        """, (sym,))
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Financial analytics — derive trends, CAGRs, quality ratios from raw filings
# ─────────────────────────────────────────────────────────────────────────────
def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _cagr(end_v: float | None, start_v: float | None, years: int) -> float | None:
    if not end_v or not start_v or start_v <= 0 or years <= 0:
        return None
    try:
        return ((end_v / start_v) ** (1 / years) - 1) * 100
    except (ValueError, ZeroDivisionError):
        return None


def compute_financial_analytics(qtr: list[dict], ann: list[dict],
                                bs: list[dict], cf: list[dict]) -> dict:
    """Derive growth, momentum, quality metrics from raw filings."""
    a: dict = {}

    # ---- Quarterly trajectory (newest first in list) ----
    if qtr:
        qs = list(reversed(qtr))  # chronological
        revs = [_safe_float(r["revenue"]) for r in qs]
        pats = [_safe_float(r["pat"]) for r in qs]
        opms = [_safe_float(r["opm_pct"]) for r in qs]
        a["q_count"] = len(qs)
        if len(revs) >= 2 and revs[-1] and revs[-2]:
            a["rev_qoq_pct"] = (revs[-1] - revs[-2]) / revs[-2] * 100
        if len(revs) >= 5 and revs[-1] and revs[-5]:
            a["rev_yoy_pct"] = (revs[-1] - revs[-5]) / revs[-5] * 100
        if len(pats) >= 2 and pats[-1] and pats[-2]:
            a["pat_qoq_pct"] = (pats[-1] - pats[-2]) / pats[-2] * 100
        if len(pats) >= 5 and pats[-1] and pats[-5]:
            a["pat_yoy_pct"] = (pats[-1] - pats[-5]) / pats[-5] * 100
        # OPM trend (latest minus 4-qtr avg)
        latest_opm = opms[-1] if opms else None
        opm_avg_prev = [o for o in opms[:-1] if o is not None]
        if latest_opm is not None and opm_avg_prev:
            avg = sum(opm_avg_prev) / len(opm_avg_prev)
            a["opm_latest_pct"] = latest_opm
            a["opm_avg_4q_pct"] = avg
            a["opm_delta_bps"] = (latest_opm - avg) * 100
        # Tag direction
        if a.get("rev_qoq_pct") is not None and a.get("rev_yoy_pct") is not None:
            if a["rev_qoq_pct"] > 5 and a["rev_yoy_pct"] > 15:
                a["q_trend"] = "accelerating"
            elif a["rev_yoy_pct"] > 0:
                a["q_trend"] = "expanding"
            else:
                a["q_trend"] = "contracting"

    # ---- Annual CAGRs ----
    if ann and len(ann) >= 2:
        anns = list(reversed(ann))
        rev_first = _safe_float(anns[0]["revenue"])
        rev_last = _safe_float(anns[-1]["revenue"])
        pat_first = _safe_float(anns[0]["pat"])
        pat_last = _safe_float(anns[-1]["pat"])
        eps_first = _safe_float(anns[0]["eps"])
        eps_last = _safe_float(anns[-1]["eps"])
        yrs = len(anns) - 1
        a["rev_cagr_pct"] = _cagr(rev_last, rev_first, yrs)
        a["pat_cagr_pct"] = _cagr(pat_last, pat_first, yrs)
        a["eps_cagr_pct"] = _cagr(eps_last, eps_first, yrs)
        a["cagr_years"] = yrs
        # OPM stability
        opms_y = [_safe_float(r["opm_pct"]) for r in anns if r["opm_pct"] is not None]
        if opms_y:
            mn, mx = min(opms_y), max(opms_y)
            a["opm_band"] = (mn, mx)
            a["opm_stable"] = (mx - mn) <= 4

    # ---- Balance sheet trend ----
    if bs:
        bss = list(reversed(bs))
        borrows = [_safe_float(r["borrowings"]) for r in bss]
        nets = [_safe_float(r["net_debt"]) for r in bss]
        if len(borrows) >= 2 and borrows[0] is not None and borrows[-1] is not None:
            delta = borrows[-1] - borrows[0]
            a["debt_change_cr"] = delta
            a["debt_trend"] = "rising" if delta > 50 else ("falling" if delta < -50 else "stable")
        if nets and nets[-1] is not None:
            a["net_debt_cr"] = nets[-1]
            a["net_cash_positive"] = nets[-1] < 0
        eqs = [(_safe_float(r["equity_capital"]) or 0) + (_safe_float(r["reserves"]) or 0) for r in bss]
        if eqs and eqs[-1] > 0 and borrows and borrows[-1] is not None:
            a["de_ratio"] = borrows[-1] / eqs[-1]
        assets = [_safe_float(r["total_assets"]) for r in bss]
        if len(assets) >= 2 and assets[0] and assets[-1]:
            a["asset_growth_pct"] = (assets[-1] - assets[0]) / assets[0] * 100

    # ---- Cash flow quality ----
    if cf and ann:
        latest_cf = cf[0]
        ocf = _safe_float(latest_cf.get("operating_cf"))
        latest_pat = _safe_float(ann[0].get("pat"))
        if ocf is not None and latest_pat and latest_pat != 0:
            a["ocf_to_pat"] = ocf / latest_pat
            a["earnings_quality_flag"] = (
                "high" if a["ocf_to_pat"] >= 0.8 else
                "watch" if a["ocf_to_pat"] >= 0.4 else "weak"
            )
        # Free cash flow proxy
        inv_cf = _safe_float(latest_cf.get("investing_cf")) or 0
        if ocf is not None:
            a["fcf_proxy_cr"] = ocf + inv_cf  # investing usually negative

    # ---- ROE (latest PAT / latest book equity) ----
    if ann and bs:
        latest_pat = _safe_float(ann[0].get("pat"))
        latest_eq = (_safe_float(bs[0].get("equity_capital")) or 0) + (_safe_float(bs[0].get("reserves")) or 0)
        if latest_pat is not None and latest_eq > 0:
            a["roe_computed_pct"] = latest_pat / latest_eq * 100

    # ---- ROCE (EBIT / Capital Employed) ≈ (PBT + Interest) / (Equity + Borrowings) ----
    if ann and bs:
        latest = ann[0]
        pbt = _safe_float(latest.get("pbt"))
        interest = _safe_float(latest.get("interest")) or 0
        eq = (_safe_float(bs[0].get("equity_capital")) or 0) + (_safe_float(bs[0].get("reserves")) or 0)
        borrow = _safe_float(bs[0].get("borrowings")) or 0
        cap_emp = eq + borrow
        if pbt is not None and cap_emp > 0:
            a["roce_computed_pct"] = (pbt + interest) / cap_emp * 100

    # ---- Altman Z' (private-firm variant — uses book equity, no market cap) ----
    # Z' = 0.717*A + 0.847*B + 3.107*C + 0.420*D + 0.998*E
    #   A = Working Capital / Total Assets (proxy: reserves+equity-borrowings vs assets — rough)
    #   B = Retained Earnings / TA   (reserves / TA)
    #   C = EBIT / TA                (PBT + interest) / TA
    #   D = Book Equity / Total Liab (equity+reserves) / (TA - equity)
    #   E = Sales / TA
    if ann and bs:
        latest_ann = ann[0]
        latest_bs = bs[0]
        ta = _safe_float(latest_bs.get("total_assets"))
        reserves = _safe_float(latest_bs.get("reserves")) or 0
        eq_cap = _safe_float(latest_bs.get("equity_capital")) or 0
        borrow = _safe_float(latest_bs.get("borrowings")) or 0
        sales = _safe_float(latest_ann.get("revenue"))
        pbt = _safe_float(latest_ann.get("pbt"))
        interest = _safe_float(latest_ann.get("interest")) or 0
        if ta and ta > 0 and sales is not None and pbt is not None:
            book_eq = eq_cap + reserves
            total_liab = max(ta - book_eq, 1)
            B = reserves / ta
            C = (pbt + interest) / ta
            D = book_eq / total_liab
            E = sales / ta
            # WC proxy: book_eq minus borrowings (very rough; absent current asset detail)
            A = max(book_eq - borrow, 0) / ta
            a["altman_z_prime"] = 0.717*A + 0.847*B + 3.107*C + 0.420*D + 0.998*E

    # ---- Piotroski F-score approximation (4-5 of 9 checks given our data) ----
    # We can score: ROA>0, ΔROA>0, OCF>0, OCF>NI, Δleverage<0, Δasset turnover>0 (6/9)
    if ann and bs and cf and len(ann) >= 2 and len(bs) >= 2 and len(cf) >= 1:
        score = 0
        breakdown = []
        a_now, a_prev = ann[0], ann[1]
        b_now, b_prev = bs[0], bs[1]
        c_now = cf[0]
        ta_now = _safe_float(b_now.get("total_assets")) or 0
        ta_prev = _safe_float(b_prev.get("total_assets")) or 0
        pat_now = _safe_float(a_now.get("pat")) or 0
        pat_prev = _safe_float(a_prev.get("pat")) or 0
        rev_now = _safe_float(a_now.get("revenue")) or 0
        rev_prev = _safe_float(a_prev.get("revenue")) or 0
        bor_now = _safe_float(b_now.get("borrowings")) or 0
        bor_prev = _safe_float(b_prev.get("borrowings")) or 0
        ocf_now = _safe_float(c_now.get("operating_cf")) or 0
        if pat_now > 0: score += 1; breakdown.append("ROA>0")
        roa_now = pat_now / ta_now if ta_now else 0
        roa_prev = pat_prev / ta_prev if ta_prev else 0
        if roa_now > roa_prev: score += 1; breakdown.append("ΔROA>0")
        if ocf_now > 0: score += 1; breakdown.append("OCF>0")
        if ocf_now > pat_now: score += 1; breakdown.append("OCF>NI")
        lev_now = bor_now / ta_now if ta_now else 0
        lev_prev = bor_prev / ta_prev if ta_prev else 0
        if lev_now < lev_prev: score += 1; breakdown.append("Δleverage↓")
        at_now = rev_now / ta_now if ta_now else 0
        at_prev = rev_prev / ta_prev if ta_prev else 0
        if at_now > at_prev: score += 1; breakdown.append("Δasset turnover>0")
        a["piotroski_approx"] = score  # out of 6 testable criteria
        a["piotroski_max"] = 6
        a["piotroski_breakdown"] = breakdown

    # ---- Beneish M-score (simplified — 5 of 8 factors computable from our data) ----
    # Full M = -4.84 + 0.92·DSRI + 0.528·GMI + 0.404·AQI + 0.892·SGI + 0.115·DEPI
    #          - 0.172·SGAI + 4.679·TATA - 0.327·LVGI
    # We can compute SGI, DEPI (proxy 1), TATA, LVGI, GMI (proxy via OPM as gross-margin substitute).
    # AQI/SGAI/DSRI need balance items we don't store (receivables, current assets, SG&A).
    # Defaults of 1.0 are used for the unknown factors (consistent with steady-state
    # firms in the original paper) so the score remains comparable.
    if ann and bs and len(ann) >= 2 and len(bs) >= 2:
        try:
            a_now, a_prev = ann[0], ann[1]
            b_now, b_prev = bs[0], bs[1]
            rev_now  = _safe_float(a_now.get("revenue")) or 0
            rev_prev = _safe_float(a_prev.get("revenue")) or 0
            opm_now  = _safe_float(a_now.get("opm_pct"))
            opm_prev = _safe_float(a_prev.get("opm_pct"))
            pat_now  = _safe_float(a_now.get("pat")) or 0
            dep_now  = _safe_float(a_now.get("depreciation"))
            dep_prev = _safe_float(a_prev.get("depreciation"))
            ta_now   = _safe_float(b_now.get("total_assets")) or 0
            ta_prev  = _safe_float(b_prev.get("total_assets")) or 0
            eq_now   = (_safe_float(b_now.get("equity_capital")) or 0) + (_safe_float(b_now.get("reserves")) or 0)
            eq_prev  = (_safe_float(b_prev.get("equity_capital")) or 0) + (_safe_float(b_prev.get("reserves")) or 0)
            bor_now  = _safe_float(b_now.get("borrowings")) or 0
            bor_prev = _safe_float(b_prev.get("borrowings")) or 0
            ocf_now  = _safe_float(cf[0].get("operating_cf")) if cf else None

            SGI  = (rev_now / rev_prev) if rev_prev else 1.0
            GMI  = ((opm_prev / opm_now) if (opm_now and opm_prev) else 1.0)
            DEPI = ((dep_prev / dep_now) if (dep_now and dep_prev) else 1.0)
            LVGI_now  = ((bor_now  + (ta_now  - eq_now  - bor_now )) / ta_now ) if ta_now  else 0
            LVGI_prev = ((bor_prev + (ta_prev - eq_prev - bor_prev)) / ta_prev) if ta_prev else 0
            LVGI = (LVGI_now / LVGI_prev) if LVGI_prev else 1.0
            TATA = ((pat_now - (ocf_now or 0)) / ta_now) if ta_now else 0
            DSRI = AQI = SGAI = 1.0  # neutral (data unavailable)
            m = (-4.84 + 0.92*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI
                 + 0.115*DEPI - 0.172*SGAI + 4.679*TATA - 0.327*LVGI)
            a["beneish_m_simplified"] = m
            # < -2.22 → low manipulation risk; > -1.78 → high; in between → grey zone
            a["beneish_m_flag"] = (
                "low" if m < -2.22 else ("watch" if m < -1.78 else "high")
            )
        except (TypeError, ZeroDivisionError):
            pass

    # ---- Forensic risk synthesis (low / moderate / high) ----
    # Heuristic: combine Beneish flag, Piotroski strength, earnings-quality (OCF/PAT),
    # leverage and growth-quality signals into a single tier label.
    flags_high = 0
    flags_low  = 0
    if a.get("beneish_m_flag") == "high": flags_high += 2
    if a.get("beneish_m_flag") == "low":  flags_low  += 1
    if a.get("earnings_quality_flag") == "weak":  flags_high += 1
    if a.get("earnings_quality_flag") == "high":  flags_low  += 1
    if a.get("piotroski_approx") is not None:
        if a["piotroski_approx"] <= 2: flags_high += 1
        if a["piotroski_approx"] >= 5: flags_low  += 1
    if (a.get("de_ratio") or 0) > 2:          flags_high += 1
    if a.get("debt_trend") == "rising":        flags_high += 1
    # Aggressive revenue growth WITH weak earnings quality is a red flag
    if (a.get("rev_yoy_pct") or 0) > 50 and a.get("earnings_quality_flag") == "weak":
        flags_high += 1
    a["forensic_flags_high"] = flags_high
    a["forensic_flags_low"]  = flags_low
    if flags_high >= 3:
        a["forensic_risk_tier"] = "high"
    elif flags_high >= 1 and flags_low == 0:
        a["forensic_risk_tier"] = "moderate"
    elif flags_low >= 2 and flags_high == 0:
        a["forensic_risk_tier"] = "low"
    else:
        a["forensic_risk_tier"] = "moderate"

    # ---- NPM / EPS fallback from latest annual ----
    if ann:
        latest_ann = ann[0]
        rev  = _safe_float(latest_ann.get("revenue"))
        pat  = _safe_float(latest_ann.get("pat"))
        eps_v = _safe_float(latest_ann.get("eps"))
        if rev and rev > 0 and pat is not None:
            a["npm_computed_pct"] = pat / rev * 100
        if eps_v is not None:
            a["eps_latest"] = eps_v

    return a


# ─────────────────────────────────────────────────────────────────────────────
# Risk / Reward / Target computation
# ─────────────────────────────────────────────────────────────────────────────
def compute_risk_reward(tech: dict, snap: dict | None, fund: dict | None,
                        analytics: dict) -> dict:
    """Derive entry zone, targets, stop-loss, RR ratio, and a 0-10 risk score.

    The targets use ATR-multiple swings tempered by distance from 52w high
    (so we don't pin a 12m target past the breakout zone if stretched).
    Risk score blends ATR%, distance from 52w high, debt trend, OCF/PAT
    quality, Altman Z, Beneish M, and stage.
    """
    out: dict = {}
    if "error" in (tech or {}):
        return {"error": tech.get("error", "no technicals")}
    snap = snap or {}
    fund = fund or {}
    last = tech.get("last")
    atr = tech.get("atr")
    atr_pct = tech.get("atr_pct")
    wk52_high = tech.get("wk52_high")
    wk52_low = tech.get("wk52_low")
    dist_high = tech.get("dist_from_high_pct")  # negative when below high
    if not last or not atr:
        return {"error": "missing price/ATR"}

    # ----- Entry zone: anchor on EMA20 or 0.5 ATR pullback -----
    ema20 = tech.get("ema20") or last
    entry_low = min(ema20, last - 0.5 * atr)
    entry_high = last  # don't chase
    out["entry_low"] = entry_low
    out["entry_high"] = entry_high

    # ----- Stop loss: 2 ATR below entry, but never below EMA50 fail level -----
    ema50 = tech.get("ema50")
    stop = entry_low - 2 * atr
    if ema50:
        stop = min(stop, ema50 * 0.97)  # 3% below EMA50 invalidation
    out["stop_loss"] = stop
    out["risk_per_share"] = last - stop
    out["risk_pct"] = (last - stop) / last * 100 if last else None

    # ----- Targets: ATR-projection + breakout-extension (2M / 4M / 6M horizons) -----
    # T1 (2M): 3 ATR up
    t1 = last + 3 * atr
    # T2 (4M): 5 ATR up, but if within 5% of 52w high, project 1.10x breakout
    if dist_high is not None and dist_high > -5 and wk52_high:
        t2 = max(last + 5 * atr, wk52_high * 1.10)
    else:
        t2 = last + 5 * atr
    # T3 (6M): EPS-CAGR aware — apply growth premium if quality cohort
    cagr = analytics.get("pat_cagr_pct") or analytics.get("rev_cagr_pct") or 0
    growth_mult = 1.15 if cagr >= 20 else (1.08 if cagr >= 10 else 1.04)
    t3 = max(last + 7 * atr, t2 * growth_mult)

    out["target_2m"] = t1
    out["target_4m"] = t2
    out["target_6m"] = t3
    # Back-compat aliases (some downstream code still reads these)
    out["target_1m"] = t1
    out["target_3m"] = t2
    out["target_12m"] = t3

    # ----- Reward / Risk -----
    reward = t2 - last  # use medium-term as the headline RR
    risk = last - stop
    out["reward_per_share"] = reward
    out["rr_ratio_4m"] = (reward / risk) if risk > 0 else None
    out["rr_ratio_6m"] = ((t3 - last) / risk) if risk > 0 else None
    # Back-compat aliases
    out["rr_ratio_3m"] = out["rr_ratio_4m"]
    out["rr_ratio_12m"] = out["rr_ratio_6m"]

    # ----- Risk score (0=safe, 10=high risk) -----
    score = 0.0
    breakdown: list[str] = []
    # Volatility
    if atr_pct is not None:
        if atr_pct > 5: score += 2.5; breakdown.append(f"ATR {atr_pct:.1f}% (+2.5)")
        elif atr_pct > 3: score += 1.5; breakdown.append(f"ATR {atr_pct:.1f}% (+1.5)")
        elif atr_pct > 2: score += 0.5; breakdown.append(f"ATR {atr_pct:.1f}% (+0.5)")
    # Extension (penalise chasing far above high)
    if dist_high is not None:
        if dist_high > 0: score += 2.0; breakdown.append(f"At new high {dist_high:+.1f}% (+2.0)")
        elif dist_high > -3: score += 1.0; breakdown.append(f"Near high {dist_high:+.1f}% (+1.0)")
    # Overbought RSI
    rsi = tech.get("rsi")
    if rsi and rsi > 75: score += 1.5; breakdown.append(f"RSI {rsi:.0f} (+1.5)")
    elif rsi and rsi > 70: score += 1.0; breakdown.append(f"RSI {rsi:.0f} (+1.0)")
    # Stage
    stage = (snap.get("stage") or "")
    if stage == "STAGE_4": score += 3.0; breakdown.append("Stage 4 (+3.0)")
    elif stage == "STAGE_3": score += 1.5; breakdown.append("Stage 3 (+1.5)")
    elif stage == "STAGE_1": score += 1.0; breakdown.append("Stage 1 (+1.0)")
    # Fundamental quality red flags
    az = _safe_float(fund.get("altman_z_score"))
    if az is not None and az < 1.8: score += 1.5; breakdown.append(f"Altman Z {az:.1f} distress (+1.5)")
    bm = _safe_float(fund.get("beneish_m_score"))
    if bm is not None and bm > -1.78: score += 1.5; breakdown.append(f"Beneish M {bm:.2f} flag (+1.5)")
    # Debt
    if analytics.get("debt_trend") == "rising": score += 1.0; breakdown.append("Debt rising (+1.0)")
    if analytics.get("computed_de_ratio") is not None and analytics["computed_de_ratio"] > 1.5:
        score += 1.0; breakdown.append(f"D/E {analytics['computed_de_ratio']:.1f} (+1.0)")
    # Earnings quality
    if analytics.get("earnings_quality_flag") == "weak":
        score += 1.5; breakdown.append("OCF/PAT weak (+1.5)")
    elif analytics.get("earnings_quality_flag") == "watch":
        score += 0.5; breakdown.append("OCF/PAT watch (+0.5)")

    score = max(0.0, min(10.0, score))
    out["risk_score"] = round(score, 1)
    out["risk_tier"] = "LOW" if score <= 3 else ("MEDIUM" if score <= 6 else "HIGH")
    out["risk_factors"] = breakdown

    # Suggested position size — inverse risk + RR
    rr = out.get("rr_ratio_4m") or 0
    if score >= 7 or rr < 1: out["position_size_pct"] = 4
    elif score >= 5: out["position_size_pct"] = 6
    elif score >= 3 and rr >= 2: out["position_size_pct"] = 10
    elif rr >= 3: out["position_size_pct"] = 12
    else: out["position_size_pct"] = 8

    return out


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _grab(pattern: str, text: str) -> float | None:
    if not text:
        return None
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    try:
        return float(m.group(1))
    except (ValueError, IndexError):
        return None


def _parse_summaries(fund: dict) -> dict:
    """Extract numeric metrics from the free-text summary columns.

    The `scores.fundamentals` numeric columns are largely NULL right now;
    the actual data lives in pnl_summary / ratios_summary / balance_sheet_summary.
    Parse them so the report can still show real numbers.
    """
    if not fund:
        return {}
    pnl = fund.get("pnl_summary") or ""
    ratios = fund.get("ratios_summary") or ""
    bs = fund.get("balance_sheet_summary") or ""
    qtr = fund.get("quarterly_summary") or ""

    parsed: dict = {}
    parsed["sales_latest_cr"] = _grab(r"Sales[: ]+([\d.]+)\s*Cr", pnl)
    parsed["sales_yoy_pct"] = _grab(r"Sales[^()]*\(YoY\s*([+\-]?[\d.]+)%\)", pnl)
    parsed["pat_latest_cr"] = _grab(r"NetProfit[: ]+([\d.]+)\s*Cr", pnl)
    parsed["pat_yoy_pct"] = _grab(r"NetProfit[^()]*\(YoY\s*([+\-]?[\d.]+)%\)", pnl)
    parsed["eps"] = _grab(r"EPS[: ]+([\d.]+)", pnl) or _grab(r"EPS[: ]+([\d.]+)", ratios)
    parsed["roce_pct"] = _grab(r"ROCE[: ]+([\d.]+)\s*%", ratios)
    parsed["roe_pct"] = _grab(r"ROE[: ]+([\d.]+)\s*%", ratios)
    parsed["npm_pct"] = _grab(r"NPM[: ]+([\d.]+)\s*%", ratios)
    parsed["debt_cr"] = _grab(r"Debt[: ]+([\d.]+)\s*Cr", bs)
    parsed["pe_ratio"] = _grab(r"P/E[: ]+([\d.]+)", ratios)
    parsed["mkt_cap_cr"] = _grab(r"Mkt Cap[: ]+([\d.,]+)", ratios.replace(",", ""))
    parsed["book_value"] = _grab(r"Book Value[: ]+([\d.]+)", ratios)
    parsed["div_yield_pct"] = _grab(r"Div Yield[: ]+([\d.]+)", ratios)

    # ── Shareholding pattern (investor_summary)
    inv = fund.get("investor_summary") or ""
    parsed["promoter_pct"] = _grab(r"Promoter[s]?[: ]+([\d.]+)\s*%", inv)
    parsed["fii_pct"]      = _grab(r"FII[: ]+([\d.]+)\s*%", inv)
    parsed["dii_pct"]      = _grab(r"DII[: ]+([\d.]+)\s*%", inv)
    parsed["public_pct"]   = _grab(r"Public[: ]+([\d.]+)\s*%", inv)
    parsed["govt_pct"]     = _grab(r"Govt[: ]+([\d.]+)\s*%", inv)

    # Quarterly trajectory
    msales = re.search(r"Sales last 4Q[: ]+([\d.,\s]+)Cr", qtr)
    if msales:
        nums = [float(x) for x in _NUM_RE.findall(msales.group(1))]
        if len(nums) >= 2:
            parsed["sales_qoq_pct"] = round((nums[-1] - nums[-2]) / nums[-2] * 100, 1) if nums[-2] else None
            parsed["sales_q_trend"] = nums
    mpat = re.search(r"Net Profit last 4Q[: ]+([\d.,\s]+)Cr", qtr)
    if mpat:
        nums = [float(x) for x in _NUM_RE.findall(mpat.group(1))]
        if len(nums) >= 2:
            parsed["pat_qoq_pct"] = round((nums[-1] - nums[-2]) / nums[-2] * 100, 1) if nums[-2] else None
            parsed["pat_q_trend"] = nums
    return parsed


def get_fundamentals(conn, sym: str) -> dict | None:
    fund = _fetchone(conn, """
        SELECT symbol, piotroski_score, beneish_m_score, altman_z_score,
               forensic_risk, revenue_growth_3y, pat_growth_3y, roe, roce,
               debt_to_equity, promoter_holding,
               pnl_summary, quarterly_summary, balance_sheet_summary,
               cash_flow_summary, investor_summary, ratios_summary,
               updated_at
        FROM scores.fundamentals WHERE symbol=%s
    """, (sym,))
    if fund is None:
        return None
    parsed = _parse_summaries(fund)
    fund["_parsed"] = parsed
    # Backfill canonical numeric fields when they're NULL but text-derivable
    if fund.get("roce") is None and parsed.get("roce_pct") is not None:
        fund["roce"] = parsed["roce_pct"]
    if fund.get("roe") is None and parsed.get("roe_pct") is not None:
        fund["roe"] = parsed["roe_pct"]
    if fund.get("pat_growth_3y") is None and parsed.get("pat_yoy_pct") is not None:
        # YoY isn't 3Y CAGR but at least surfaces growth direction
        fund["pat_growth_3y_proxy"] = parsed["pat_yoy_pct"]
    if fund.get("revenue_growth_3y") is None and parsed.get("sales_yoy_pct") is not None:
        fund["revenue_growth_3y_proxy"] = parsed["sales_yoy_pct"]
    if fund.get("promoter_holding") is None and parsed.get("promoter_pct") is not None:
        fund["promoter_holding"] = parsed["promoter_pct"]
    return fund


# ─────────────────────────────────────────────────────────────────────────────
# LLM narrative generation
# ─────────────────────────────────────────────────────────────────────────────
def _rule_chart_narrative(tech: dict, rr: dict | None = None) -> str:
    """Build a fallback chart narrative when LLM is unavailable. Uses the
    detected chart patterns, EMA stack, RSI regime and key levels."""
    if not isinstance(tech, dict) or not tech.get("chart"):
        return "Chart data unavailable."
    chart = tech["chart"]
    patterns = _detect_patterns(chart)
    bars = chart.get("bars") or []
    if not bars: return "Insufficient price history to narrate."
    last = bars[-1]
    c = float(last.get("close") or 0)
    ema20  = tech.get("ema20"); ema50 = tech.get("ema50"); ema200 = tech.get("ema200")
    rsi    = tech.get("rsi")
    atr_p  = tech.get("atr_pct")
    dh     = tech.get("dist_from_high_pct")
    # Stack
    if ema20 and ema50 and ema200:
        if ema20 > ema50 > ema200:
            stack = (f"price ₹{c:,.0f} sits above EMA20 ₹{ema20:,.0f} > EMA50 ₹{ema50:,.0f} "
                     f"> EMA200 ₹{ema200:,.0f} — textbook bullish stack")
        elif ema20 < ema50 < ema200:
            stack = (f"price ₹{c:,.0f} trades below EMA20 ₹{ema20:,.0f} < EMA50 ₹{ema50:,.0f} "
                     f"< EMA200 ₹{ema200:,.0f} — bearish stack, trend down")
        else:
            stack = (f"EMAs are crossing (20:{ema20:,.0f} / 50:{ema50:,.0f} / 200:{ema200:,.0f}) "
                     "— trend transition in progress")
    else:
        stack = f"price ₹{c:,.0f}"
    # RSI regime
    if rsi is None: rsi_txt = "RSI unavailable"
    elif rsi >= 70: rsi_txt = f"RSI {rsi:.0f} is overbought — pullback risk elevated"
    elif rsi <= 30: rsi_txt = f"RSI {rsi:.0f} is oversold — mean-reversion bounce possible"
    elif rsi >= 60: rsi_txt = f"RSI {rsi:.0f} shows strong momentum but not stretched"
    elif rsi <= 40: rsi_txt = f"RSI {rsi:.0f} is weak, momentum has rolled over"
    else:           rsi_txt = f"RSI {rsi:.0f} is neutral"
    # Patterns
    if patterns:
        pat_names = ", ".join(p["label"] for p in patterns[:3])
        pat_txt = f"Detected patterns: {pat_names}."
    else:
        pat_txt = "No high-confidence pattern triggered on the latest bars."
    # Levels
    sup = (chart.get("support_levels") or [])
    res = (chart.get("resistance_levels") or [])
    lvl_bits = []
    if res:  lvl_bits.append(f"nearest resistance ₹{float(res[0]):,.0f}")
    if sup:  lvl_bits.append(f"nearest support ₹{float(sup[0]):,.0f}")
    lvl_txt = "; ".join(lvl_bits) if lvl_bits else ""
    # Distance from 52w high
    dh_txt = f"{abs(dh):.1f}% below 52W high" if (dh is not None and dh < 0) else (
        f"at fresh 52W highs" if (dh is not None and dh >= 0) else "")
    # Action hint
    if rr:
        ez_lo = rr.get("entry_low"); ez_hi = rr.get("entry_high"); stop = rr.get("stop_loss")
        try:
            act = f"Trader's plan: accumulate ₹{float(ez_lo):,.0f}–₹{float(ez_hi):,.0f} with stop below ₹{float(stop):,.0f}."
        except (TypeError, ValueError): act = ""
    else: act = ""
    parts = [
        f"Over the last 6 months {stack}.",
        f"{rsi_txt}; ATR(14) {atr_p:.1f}% indicates {'high' if (atr_p or 0)>3 else 'moderate' if (atr_p or 0)>1.5 else 'low'} day-to-day volatility." if atr_p is not None else f"{rsi_txt}.",
        pat_txt,
    ]
    if lvl_txt: parts.append(f"Watch {lvl_txt}; price is {dh_txt}.".strip())
    if act: parts.append(act)
    return " ".join(parts)


def _rule_analyst_consensus(s: dict, a: dict, fund: dict, snap: dict,
                             rr: dict, rs: float, bull: list, risk: list) -> dict:
    """Rule-based fallback analyst-consensus block when LLM is unavailable.

    Synthesises a structured BUY/HOLD/SELL view + 12m target range using
    deterministic logic on top of fundamentals (EPS × peer multiple),
    risk-reward levels and the bull/bear factor counts. No live broker
    feed — the rating_disclaimer makes this explicit in the UI.
    """
    p_ = (fund or {}).get("_parsed") or {}
    try:
        price = float(snap.get("price") or 0)
    except (TypeError, ValueError):
        price = 0
    eps  = p_.get("eps")
    roce = fund.get("roce")
    pat_cagr = a.get("pat_cagr_pct")
    # Heuristic peer-multiple by quality bucket
    if (roce or 0) >= 25 or (pat_cagr or 0) >= 30:
        peer_pe, quality = 35, "premium-quality compounder"
    elif (roce or 0) >= 18 or (pat_cagr or 0) >= 20:
        peer_pe, quality = 25, "quality growth"
    elif (roce or 0) >= 12:
        peer_pe, quality = 18, "average quality"
    else:
        peer_pe, quality = 14, "below-average quality / cyclical"
    target_median = float(eps) * peer_pe if eps else (rr.get("target_6m") or price * 1.15)
    target_low    = target_median * 0.80
    target_high   = target_median * 1.20
    upside_med    = ((target_median / price) - 1) * 100 if price else 0

    # Consensus rating logic
    if upside_med >= 20 and len(bull) >= 4 and len(risk) <= 1:
        rating = "BUY"
    elif upside_med >= 10 and len(bull) >= 3:
        rating = "OVERWEIGHT"
    elif upside_med >= 0 and len(risk) <= 2:
        rating = "HOLD"
    elif upside_med >= -10:
        rating = "UNDERWEIGHT"
    else:
        rating = "SELL"

    # Estimate-trend read from recent quarterly delivery
    py = a.get("pat_yoy_pct"); ry = a.get("rev_yoy_pct")
    if (py or 0) >= 15 and (ry or 0) >= 10:
        est_trend = "Upward"
    elif (py or 0) <= -10 or (ry or 0) <= -5:
        est_trend = "Downward"
    else:
        est_trend = "Stable"

    bull_pts = (bull[:3] if bull else
                ["Setup screens cleanly on momentum + quality factors"])
    bear_pts = (risk[:3] if risk else
                ["No quantitative red flag in dossier — confirm qualitative risks"])

    return {
        "consensus_rating": rating,
        "target_median": round(target_median, 1) if target_median else None,
        "target_low":    round(target_low, 1)    if target_low    else None,
        "target_high":   round(target_high, 1)   if target_high   else None,
        "target_rationale": (
            f"EPS ₹{eps:.1f} × {peer_pe}x ({quality}) = ₹{target_median:,.0f} median"
            if eps else f"Mid-target from RR-engine 6m level (no EPS in dossier)"
        ),
        "bull_points": bull_pts,
        "bear_points": bear_pts,
        "estimate_trend": est_trend,
        "rating_disclaimer": "Synthesised from dossier — no live broker poll wired.",
    }


def _decimal_to_float(obj):
    """Recursively convert Decimal/date for JSON serialisation."""
    from decimal import Decimal
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_float(v) for v in obj]
    return obj


def _serialize_stocks_for_llm(stocks: list[dict]) -> str:
    """Compact JSON dossier per stock — feeds the deep-analysis LLM pass."""
    rows = []
    for s in stocks:
        snap = s["snapshot"] or {}
        tech = s["tech"]
        fund = s["fund"] or {}
        a = s.get("analytics") or {}
        fscore = s.get("fund_scores") or {}
        sec = s.get("sector_ctx") or {}
        rows.append({
            "symbol": s["symbol"],
            "sector": s["sector"],
            "source_screen": s["source"],
            "sector_context": {
                "sector_strength": sec.get("sector_strength"),
                "sector_avg_rs_pct": sec.get("avg_rs"),
                "sector_avg_tech": sec.get("avg_tech"),
                "sector_avg_fund": sec.get("avg_fund"),
                "sector_peer_count": sec.get("total_stocks"),
            },
            "snapshot": {
                "price": snap.get("price"),
                "stage": snap.get("stage"),
                "stage_score": snap.get("stage_score"),
                "investment_score": snap.get("investment_score"),
                "technical_score": snap.get("technical_score"),
                "enhanced_fund_score": snap.get("enhanced_fund_score"),
                "rs_pct_vs_nifty500": snap.get("relative_strength"),
                "trading_signal": snap.get("trading_signal"),
                "stance": snap.get("stance"),
                "supertrend_state": snap.get("supertrend_state"),
                "change_1d": snap.get("change_1d_pct"),
                "change_1w": snap.get("change_1w_pct"),
                "change_1m": snap.get("change_1m_pct"),
            } if snap else {},
            "technicals": {
                "rsi14": tech.get("rsi"),
                "ema20_above_50_above_200": (
                    tech.get("ema20") and tech.get("ema50") and tech.get("ema200")
                    and tech["ema20"] > tech["ema50"] > tech["ema200"]
                ),
                "ema50_slope_20d_pct": tech.get("ema50_slope_pct"),
                "ret_1m_pct": tech.get("ret_1m"),
                "ret_3m_pct": tech.get("ret_3m"),
                "ret_6m_pct": tech.get("ret_6m"),
                "ret_1y_pct": tech.get("ret_1y"),
                "dist_from_52w_high_pct": tech.get("dist_from_high_pct"),
                "atr_pct": tech.get("atr_pct"),
                "vol_vs_20d_avg_x": tech.get("last_vol_ratio"),
            },
            "fundamental_scores": {
                "piotroski_9": fund.get("piotroski_score"),
                "altman_z": fund.get("altman_z_score"),
                "beneish_m": fund.get("beneish_m_score"),
                "forensic_risk": fund.get("forensic_risk"),
                "promoter_holding_pct": fund.get("promoter_holding"),
                "enhanced_fund_score": fscore.get("enhanced_fund_score"),
                "earnings_quality_score": fscore.get("earnings_quality"),
                "sales_growth_score": fscore.get("sales_growth"),
                "financial_strength_score": fscore.get("financial_strength"),
                "institutional_backing_score": fscore.get("institutional_backing"),
            },
            "latest_quarterly_4q": [
                {
                    "qtr": q["period_label"],
                    "revenue_cr": q["revenue"],
                    "op_profit_cr": q["operating_profit"],
                    "opm_pct": q["opm_pct"],
                    "pat_cr": q["pat"],
                    "eps": q["eps"],
                } for q in (s.get("quarterly") or [])[:4]
            ],
            "annual_5y": [
                {
                    "fy": ay["period_label"],
                    "revenue_cr": ay["revenue"],
                    "opm_pct": ay["opm_pct"],
                    "pat_cr": ay["pat"],
                    "eps": ay["eps"],
                } for ay in (s.get("annual") or [])
            ],
            "balance_sheet_3y": [
                {
                    "fy": b["period_label"],
                    "borrowings_cr": b["borrowings"],
                    "net_debt_cr": b["net_debt"],
                    "equity_cr": (float(b["equity_capital"] or 0) + float(b["reserves"] or 0)),
                    "total_assets_cr": b["total_assets"],
                } for b in (s.get("balance_sheet") or [])
            ],
            "cash_flow_3y": [
                {
                    "fy": c["period_label"],
                    "ocf_cr": c["operating_cf"],
                    "icf_cr": c["investing_cf"],
                    "fcf_proxy_cr": (float(c["operating_cf"] or 0) + float(c["investing_cf"] or 0)),
                } for c in (s.get("cash_flow") or [])
            ],
            "analytics_derived": {
                "rev_qoq_pct": a.get("rev_qoq_pct"),
                "rev_yoy_pct": a.get("rev_yoy_pct"),
                "pat_qoq_pct": a.get("pat_qoq_pct"),
                "pat_yoy_pct": a.get("pat_yoy_pct"),
                "rev_cagr_pct": a.get("rev_cagr_pct"),
                "pat_cagr_pct": a.get("pat_cagr_pct"),
                "eps_cagr_pct": a.get("eps_cagr_pct"),
                "cagr_years": a.get("cagr_years"),
                "opm_delta_bps_vs_4q_avg": a.get("opm_delta_bps"),
                "opm_stable_band": a.get("opm_stable"),
                "debt_trend_3y": a.get("debt_trend"),
                "debt_change_cr": a.get("debt_change_cr"),
                "net_cash_positive": a.get("net_cash_positive"),
                "computed_de_ratio": a.get("de_ratio"),
                "ocf_to_pat_ratio": a.get("ocf_to_pat"),
                "earnings_quality_flag": a.get("earnings_quality_flag"),
                "fcf_proxy_cr": a.get("fcf_proxy_cr"),
                "qtr_trend_tag": a.get("q_trend"),
            },
            "ratios_text_extract": (fund.get("ratios_summary") if fund else None),
            "investor_text_extract": (fund.get("investor_summary") if fund else None),
            "corporate_events_90d": [
                {"date": e["event_date"], "type": e["event_type"], "purpose": e["purpose_raw"]}
                for e in (s.get("corp_events") or [])
            ],
            "insider_activity_90d": [
                {"date": i["alert_date"], "type": i["alert_type"], "entity": i["entity"],
                 "value_cr": i["value_cr"], "category": i["category"]}
                for i in (s.get("insider") or [])
            ],
            "risk_reward_computed": s.get("risk_reward") or {},
            "chart_patterns_detected": [
                {"pattern": p["label"], "note": p.get("note","")}
                for p in (_detect_patterns(s["tech"]["chart"]) if isinstance(s.get("tech"), dict) and s["tech"].get("chart") else [])
            ],
        })
    return json.dumps(_decimal_to_float(rows), indent=1, default=str)


_DEEP_SYSTEM_MSG = (
    "You are a senior buy-side equity research analyst building a comprehensive "
    "investment thesis for each Indian (NSE) stock you are given. You reason "
    "FIRST PRINCIPLES across price action, sector context, fundamental scoring "
    "frameworks (Piotroski, Altman Z, Beneish M), P&L momentum, balance sheet "
    "health, cash-flow quality, and recent corporate actions. You are quantitative "
    "— every claim cites a number from the JSON dossier. You never invent figures."
)


def _build_deep_llm_prompt(stocks: list[dict], macro_context: str, snap_date: str) -> str:
    return "\n".join([
        f"Analysis date: {snap_date}",
        "",
        "MARKET / MACRO CONTEXT:",
        macro_context,
        "",
        "PER-STOCK DOSSIER (JSON) — each stock includes: technicals, snapshot, "
        "fundamental scores, last 4 quarterly results, last 5 annual results, "
        "last 3 years balance sheet, last 3 years cash flow, derived analytics "
        "(QoQ/YoY, CAGR, OPM trend, debt trend, OCF/PAT quality), sector context, "
        "corporate events (90d), insider activity (90d):",
        "",
        _serialize_stocks_for_llm(stocks),
        "",
        "TASK — for EVERY symbol produce a synthesised investment view by recursively "
        "weighing: (1) technical setup, (2) current market regime, (3) sector "
        "rotation context, (4) Piotroski/Altman/Beneish scores, (5) P&L momentum "
        "(QoQ + YoY + CAGR), (6) balance-sheet health (debt trend, net debt, D/E), "
        "(7) ROCE / ROE, (8) cash-flow quality (OCF/PAT, FCF), (9) corporate events, "
        "(10) latest quarterly result deltas vs trend. Also derive realistic price "
        "targets, stop-loss, reward/risk ratio, and a 0-10 risk score. Use "
        "`risk_reward_computed` in the dossier as a quantitative starting point "
        "(ATR-based entries/stops/targets) and adjust it qualitatively using the "
        "fundamental and sector view.",
        "",
        "Return STRICT JSON (no markdown fences, no commentary):",
        "{",
        '  "per_stock": {',
        '    "SYMBOL": {',
        '      "thesis": "3-4 sentence multi-dimensional bull case citing concrete numbers (RSI x, EMA stack, RS y%, revenue YoY z%, PAT CAGR w%, ROCE p%, etc.)",',
        '      "key_catalysts": ["catalyst 1 with metric", "catalyst 2", "catalyst 3"],',
        '      "fundamental_view": "2-3 sentences synthesising P&L + BS + CF: cite latest quarter revenue/PAT growth, OPM trend in bps, debt direction, OCF/PAT ratio, ROCE, EPS CAGR",',
        '      "technical_view": "2 sentences: trend stack, RS, momentum (RSI), distance from 52w high, volume",',
        '      "chart_narrative": "3-5 sentences narrating what the 6-month candlestick chart is actually showing — explicitly reference the detected chart_patterns_detected (e.g. \\"a Bullish Engulfing print on top of an Ascending Triangle\\"), where price sits vs EMA 20/50/200 stack, RSI regime (overbought / neutral / oversold / divergence), key support/resistance levels being tested, volume behaviour on the latest bars, and what a trader should watch next (breakout level, pullback zone, invalidation). Be specific and cite numbers.",',
        '      "sector_view": "1-2 sentences linking the stock to its sector strength and peer ranking",',
        '      "valuation_note": "1 sentence flagging valuation comfort or stretch — use EPS, growth, sector context (qualitative is fine if no PE)",',
        '      "street_view": "2-3 sentences synthesising the likely sell-side / broker consensus on this name: typical analyst rating bias, key bull/bear arguments brokerages would flag, peer-relative valuation read, recent estimate revisions narrative. State this is a synthesised consensus read (no live broker feed wired). Cite metrics from the dossier where possible.",',
        '      "analyst_consensus": {',
        '        "consensus_rating": "BUY | OVERWEIGHT | HOLD | UNDERWEIGHT | SELL (your synthesised inference based on the dossier — fundamentals, RS, stage, valuation; NOT a real broker poll)",',
        '        "target_median": "numeric ₹ — synthesised 12-month consensus target derived from EPS × peer-multiple logic (cite the math briefly in target_rationale)",',
        '        "target_low": "numeric ₹ — bear-case 12m target (sector de-rate / growth disappointment)",',
        '        "target_high": "numeric ₹ — bull-case 12m target (multiple expansion + earnings beat)",',
        '        "target_rationale": "1 short sentence on how the synthesised targets were built (e.g. \\"₹EPS × 22x peer median = median; ±20% for bull/bear\\")",',
        '        "bull_points": ["3 short bullets covering what brokerages would highlight — earnings momentum, margin expansion, order book, RS leadership, etc."],',
        '        "bear_points": ["3 short bullets covering what brokerages would flag — valuation, leverage, cyclical risk, governance, etc."],',
        '        "estimate_trend": "Upward | Stable | Downward — directional read on where EPS/revenue estimates likely sit vs 3 months ago given recent quarterly delivery",',
        '        "rating_disclaimer": "Always include: \\"Synthesised from dossier — no live broker poll wired.\\""',
        '      },',
        '      "key_risks": ["risk 1 with metric", "risk 2", "risk 3"],',
        '      "action": "1 sentence: entry zone or wait-for-pullback level, invalidation, stop guidance",',
        '      "potential_target_short_term": "numeric ₹ target for ~2 months (cite ATR/level used)",',
        '      "target_4m": "numeric ₹ target for ~4 months (cite ATR/breakout level used)",',
        '      "potential_target_long_term": "numeric ₹ target for ~6 months (cite growth/valuation logic)",',
        '      "stop_loss": "numeric ₹ stop-loss with reasoning (e.g. EMA50, prior swing)",',
        '      "risk_reward_ratio": "numeric ratio (target_upside ÷ stop_downside) for the 4-month view",',
        '      "risk_score_0_10": "integer 0-10 risk score with brief rationale (0=low, 10=high) considering volatility, valuation, leverage, stage, fundamentals",',
        '      "position_size_pct": "suggested % of portfolio capital for this name (1-15) given risk score and conviction",',
        '      "conviction": "HIGH | MEDIUM | LOW",',
        '      "conviction_rationale": "1 sentence justifying the conviction tier"',
        '    }',
        '  }',
        "}",
        "",
        "Rules:",
        "- Cover EVERY symbol in the input.",
        "- Be specific and numeric — generic phrasing will be rejected.",
        "- If a metric is missing/None, say so explicitly rather than fabricating.",
        "- Cite concrete numbers from the dossier (e.g., 'PAT QoQ +24.8%', 'ROCE 34%', 'Net cash ₹3,169 Cr').",
        "- The thesis must integrate at LEAST 5 of the 10 dimensions listed above.",
    ])


_PORTFOLIO_SYSTEM_MSG = (
    "You are a portfolio strategist constructing a 10-name India equity basket. "
    "You synthesise individual stock analyses, sector exposures, and macro context "
    "into an actionable portfolio plan."
)


def _build_portfolio_refine_prompt(per_stock: dict, stocks: list[dict],
                                   macro_context: str, snap_date: str) -> str:
    # Compact summary of each per_stock analysis + key metrics
    summaries = []
    for s in stocks:
        sym = s["symbol"]
        snap = s["snapshot"] or {}
        a = s.get("analytics") or {}
        ps = per_stock.get(sym, {})
        summaries.append({
            "symbol": sym,
            "sector": s["sector"],
            "conviction": ps.get("conviction"),
            "thesis": ps.get("thesis"),
            "key_risks": ps.get("key_risks"),
            "investment_score": (snap.get("investment_score")),
            "rs_pct": snap.get("relative_strength"),
            "rev_yoy_pct": a.get("rev_yoy_pct"),
            "pat_yoy_pct": a.get("pat_yoy_pct"),
        })
    return "\n".join([
        f"Date: {snap_date}",
        "",
        f"MACRO CONTEXT:\n{macro_context}",
        "",
        "PER-STOCK ANALYSIS SUMMARY (with conviction tiers from deep analysis):",
        json.dumps(_decimal_to_float(summaries), indent=1, default=str),
        "",
        "Return STRICT JSON:",
        "{",
        '  "executive_summary": "4-6 sentence portfolio-level read: what the basket expresses, dominant themes, regime fit, biggest cross-cutting risk",',
        '  "top_conviction_picks": ["SYM1", "SYM2", "SYM3"],',
        '  "portfolio_construction": "4-6 sentences on sizing logic (e.g., overweight HIGH conviction, equal-weight MEDIUM, half-weight LOW), sector cap, gross/cash exposure given the macro regime, stop-loss discipline, time horizon",',
        '  "sector_concentration_note": "1-2 sentences on sector spread risk and any rebalancing suggestion"',
        "}",
        "",
        "Reason explicitly about how the per-stock convictions and sector spread inform sizing.",
    ])


def _rule_based_narratives(stocks: list[dict]) -> dict:
    """Deterministic fallback that uses the new financial analytics layer."""
    per_stock = {}
    for s in stocks:
        snap = s["snapshot"] or {}
        tech = s["tech"]
        fund = s["fund"] or {}
        a = s.get("analytics") or {}
        sec = s.get("sector_ctx") or {}
        bull, risk = [], []
        cat: list[str] = []

        # Technicals
        if tech.get("ema20") and tech.get("ema50") and tech.get("ema200"):
            if tech["last"] > tech["ema20"] > tech["ema50"] > tech["ema200"]:
                bull.append(f"Stage-2 EMA stack (Price ₹{tech['last']:.0f} > EMA20 > EMA50 > EMA200)")
        rs = float(snap.get("relative_strength") or 0)
        if rs > 50:
            bull.append(f"RS {rs:.0f}% vs Nifty 500")
        if (tech.get("rsi") or 0) > 70:
            risk.append(f"RSI {tech['rsi']:.0f} overbought")
        elif (tech.get("rsi") or 0) > 60:
            bull.append(f"Momentum RSI {tech['rsi']:.0f}")
        if tech.get("dist_from_high_pct") is not None and tech["dist_from_high_pct"] > -5:
            bull.append("Within 5% of 52w high")

        # Fundamentals (scores)
        ps = float(fund.get("piotroski_score") or 0)
        if ps >= 7: bull.append(f"Piotroski {ps:.0f}/9")
        az = float(fund.get("altman_z_score") or 0)
        if az and az < 1.8: risk.append(f"Altman Z {az:.1f} distress zone")
        bm = float(fund.get("beneish_m_score") or 0)
        if bm and bm > -1.78: risk.append(f"Beneish M {bm:.2f}")

        # P&L momentum
        if a.get("pat_yoy_pct") is not None and a["pat_yoy_pct"] > 20:
            bull.append(f"PAT YoY +{a['pat_yoy_pct']:.0f}%")
        if a.get("rev_yoy_pct") is not None and a["rev_yoy_pct"] > 15:
            bull.append(f"Revenue YoY +{a['rev_yoy_pct']:.0f}%")
        if a.get("pat_cagr_pct") is not None and a["pat_cagr_pct"] > 20:
            bull.append(f"PAT {a['cagr_years']}Y CAGR {a['pat_cagr_pct']:.0f}%")
        if a.get("opm_delta_bps") is not None and a["opm_delta_bps"] > 50:
            cat.append(f"OPM expanded {a['opm_delta_bps']:.0f}bps vs 4Q avg")

        # Balance sheet
        if a.get("net_cash_positive"):
            bull.append(f"Net cash ₹{-a['net_debt_cr']:.0f} Cr")
        if a.get("debt_trend") == "rising":
            risk.append(f"Debt rising ₹{a['debt_change_cr']:+.0f} Cr (3Y)")
        if a.get("computed_de_ratio") is not None and a["computed_de_ratio"] > 1.5:
            risk.append(f"D/E {a['computed_de_ratio']:.1f}")

        # Cash flow quality
        if a.get("earnings_quality_flag") == "weak":
            risk.append(f"OCF/PAT {a.get('ocf_to_pat', 0):.2f} weak earnings quality")
        elif a.get("earnings_quality_flag") == "high":
            bull.append(f"OCF/PAT {a.get('ocf_to_pat', 0):.2f}")

        # ROCE/ROE
        roce = fund.get("roce")
        if roce is not None and roce >= 20:
            bull.append(f"ROCE {roce:.0f}%")
        roe = fund.get("roe")
        if roe is not None and roe >= 18:
            bull.append(f"ROE {roe:.0f}%")

        # Sector
        sec_strength = sec.get("sector_strength")
        sec_text = (f"Sector strength {sec_strength}" if sec_strength else
                    f"in {s['sector']}")

        action = f"{snap.get('trading_signal','HOLD')} bias; stage {snap.get('stage','—')}; size per regime"
        thesis = " · ".join(bull) if bull else "Mechanical screen pick; manual diligence recommended."
        def _f(v, fmt="{:.1f}"):
            try: return fmt.format(float(v))
            except (TypeError, ValueError): return "—"
        rr = s.get("risk_reward") or {}
        per_stock[s["symbol"]] = {
            "thesis": thesis,
            "key_catalysts": cat or ["Watch next quarterly print"],
            "fundamental_view": (
                f"Latest qtr revenue {_f(a.get('rev_yoy_pct'))}% YoY, PAT "
                f"{_f(a.get('pat_yoy_pct'))}% YoY; {a.get('cagr_years','—')}Y CAGR "
                f"revenue {_f(a.get('rev_cagr_pct'))}% / PAT {_f(a.get('pat_cagr_pct'))}%; "
                f"ROCE {_f(roce)}%; debt trend {a.get('debt_trend','—')}; "
                f"OCF/PAT {_f(a.get('ocf_to_pat'), '{:.2f}')}."
            ),
            "technical_view": (
                f"RSI {_f(tech.get('rsi'))}, 1Y return {_f(tech.get('ret_1y'))}%, "
                f"dist from 52w high {_f(tech.get('dist_from_high_pct'))}%."
            ),
            "chart_narrative": _rule_chart_narrative(tech, rr),
            "sector_view": sec_text,
            "valuation_note": "Quantitative valuation not in dossier — defer to qualitative read.",
            "street_view": (
                "Synthesised consensus view (no live broker feed): the name screens as "
                f"{'a high-quality compounder' if (roce or 0) >= 18 else 'a turnaround / cyclical'}; "
                f"buy-side would likely weight {'momentum + sector rotation' if rs > 50 else 'mean-reversion'}; "
                f"watch for re-rating triggers around the next quarterly print. "
                "Confirm against live broker reports before sizing."
            ),
            "analyst_consensus": _rule_analyst_consensus(s, a, fund, snap, rr, rs, bull, risk),
            "key_risks": risk or ["No quantitative red flag in dossier"],
            "action": (
                f"Enter ₹{_f(rr.get('entry_low'),'{:.0f}')}-₹{_f(rr.get('entry_high'),'{:.0f}')}; "
                f"stop ₹{_f(rr.get('stop_loss'),'{:.0f}')}; "
                f"signal {snap.get('trading_signal','HOLD')}."
            ) if rr and "error" not in rr else
            f"{snap.get('trading_signal','HOLD')} bias; stage {snap.get('stage','—')}; size per regime",
            "potential_target_short_term": rr.get("target_2m"),
            "potential_target_long_term": rr.get("target_6m"),
            "target_4m": rr.get("target_4m"),
            "stop_loss": rr.get("stop_loss"),
            "risk_reward_ratio": rr.get("rr_ratio_4m"),
            "risk_score_0_10": rr.get("risk_score"),
            "risk_tier": rr.get("risk_tier"),
            "risk_factors": rr.get("risk_factors") or [],
            "position_size_pct": rr.get("position_size_pct"),
            "conviction": "HIGH" if len(bull) >= 5 else ("MEDIUM" if len(bull) >= 3 else "LOW"),
            "conviction_rationale": f"{len(bull)} positive · {len(risk)} negative factors flagged",
        }
    return {
        "executive_summary": (
            f"Mechanically-synthesised basket of {len(stocks)} stocks combining sector-rotation "
            "leadership and Weinstein stage-2 momentum, deep-screened across "
            "P&L, BS, CF, fundamental scores and corporate events. LLM unavailable — "
            "rule-based narrative."
        ),
        "top_conviction_picks": [
            s["symbol"] for s in stocks
            if per_stock[s["symbol"]]["conviction"] == "HIGH"
        ][:3],
        "portfolio_construction": (
            "Equal-weight 10% per name baseline. Overweight HIGH-conviction names by +2%, "
            "halve LOW-conviction sizes. Cap sector exposure at 30%. Scale gross to 60-70% in "
            "elevated VIX regimes; cap per-trade risk at 1-2% of NAV via stop-distance × size."
        ),
        "sector_concentration_note": "Review sector weights against the spread shown below.",
        "per_stock": per_stock,
    }


def _build_llm_prompt(stocks: list[dict], macro_context: str, snap_date: str) -> str:
    """Backward-compatible entrypoint (now used only by tests/dry-runs)."""
    return _build_deep_llm_prompt(stocks, macro_context, snap_date)


def generate_narratives(stocks: list[dict], macro_context: str, snap_date: str,
                        use_llm: bool) -> dict:
    """Two-pass recursive analysis:
       Pass 1 — per-stock deep dive across technicals/sector/scores/P&L/BS/CF/events
       Pass 2 — portfolio-level synthesis (exec summary, sizing, conviction ranking)
       Falls back to rule-based on any LLM failure.
    """
    rule_fallback = _rule_based_narratives(stocks)
    if not use_llm:
        return rule_fallback

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("   ⚠️  OPENAI_API_KEY not set — using rule-based narrative")
        return rule_fallback

    # ---- Pass 1: per-stock deep analysis (chunked for reliable JSON) ----
    # PG 2026-05-31: a single 10-stock prompt produced ~30KB JSON and tripped
    # the model into emitting trailing junk → JSONDecodeError. Chunking into
    # batches of CHUNK_SIZE stocks keeps each response under ~10KB and lets
    # one bad batch fall back to rule-based without losing the rest.
    print("   🧠 LLM pass 1/2: per-stock deep analysis (chunked)…")
    CHUNK_SIZE = 3
    per_stock: dict = {}
    chunks = [stocks[i:i + CHUNK_SIZE] for i in range(0, len(stocks), CHUNK_SIZE)]
    chunks_ok = 0
    chunks_failed = 0
    for ci, chunk in enumerate(chunks, 1):
        syms = ",".join(s["symbol"] for s in chunk)
        try:
            deep_prompt = _build_deep_llm_prompt(chunk, macro_context, snap_date)
            deep_result = _llm_call(
                api_key=api_key,
                model=DEFAULT_MODEL,
                system_msg=_DEEP_SYSTEM_MSG,
                user_msg=deep_prompt,
                max_tokens=8192,
                timeout=180,
            )
            if "per_stock" not in deep_result or not isinstance(deep_result["per_stock"], dict):
                raise ValueError("missing per_stock dict")
            for sym, data in deep_result["per_stock"].items():
                per_stock[sym] = data
            chunks_ok += 1
            print(f"     chunk {ci}/{len(chunks)} ({syms}) ✓")
        except Exception as exc:
            chunks_failed += 1
            print(f"     chunk {ci}/{len(chunks)} ({syms}) ✗ {exc} — using rule-based for these")
            for s in chunk:
                per_stock[s["symbol"]] = rule_fallback["per_stock"].get(s["symbol"], {})

    # If every chunk failed, fall back wholesale so the report still ships.
    if chunks_ok == 0:
        print("   ⚠️  All deep-analysis chunks failed — using rule-based for all stocks")
        return rule_fallback

    # Fill any missing symbol from rule-based AND merge computed risk_reward
    # baseline as defaults (LLM-supplied targets/stops take precedence).
    for s in stocks:
        sym = s["symbol"]
        if sym not in per_stock:
            per_stock[sym] = rule_fallback["per_stock"][sym]
        rr = s.get("risk_reward") or {}
        if rr and "error" not in rr:
            ps = per_stock[sym]
            ps.setdefault("potential_target_short_term", rr.get("target_2m"))
            ps.setdefault("target_4m", rr.get("target_4m"))
            ps.setdefault("potential_target_long_term", rr.get("target_6m"))
            ps.setdefault("stop_loss", rr.get("stop_loss"))
            ps.setdefault("risk_reward_ratio", rr.get("rr_ratio_4m"))
            ps.setdefault("risk_score_0_10", rr.get("risk_score"))
            ps.setdefault("risk_tier", rr.get("risk_tier"))
            ps.setdefault("risk_factors", rr.get("risk_factors") or [])
            ps.setdefault("position_size_pct", rr.get("position_size_pct"))
        # Chart narrative fallback if LLM didn't emit one
        if not per_stock[sym].get("chart_narrative"):
            per_stock[sym]["chart_narrative"] = _rule_chart_narrative(s.get("tech") or {}, rr)
        # Analyst consensus fallback if LLM didn't emit a structured block
        if not isinstance(per_stock[sym].get("analyst_consensus"), dict):
            fb = (rule_fallback["per_stock"].get(sym) or {}).get("analyst_consensus")
            if isinstance(fb, dict):
                per_stock[sym]["analyst_consensus"] = fb
    print(f"   pass 1 done: {chunks_ok}/{len(chunks)} chunks ok, {chunks_failed} fell back to rule-based")

    # ---- Pass 2: portfolio-level refinement ----
    try:
        print("   🧠 LLM pass 2/2: portfolio-level synthesis…")
        port_prompt = _build_portfolio_refine_prompt(per_stock, stocks, macro_context, snap_date)
        port_result = _llm_call(
            api_key=api_key,
            model=DEFAULT_MODEL,
            system_msg=_PORTFOLIO_SYSTEM_MSG,
            user_msg=port_prompt,
            max_tokens=4096,
            timeout=200,
        )
    except Exception as exc:
        print(f"   ⚠️  Portfolio refinement LLM failed: {exc} — using rule-based portfolio summary")
        port_result = {}

    return {
        "executive_summary": port_result.get("executive_summary",
                                              rule_fallback["executive_summary"]),
        "portfolio_construction": port_result.get("portfolio_construction",
                                                   rule_fallback["portfolio_construction"]),
        "top_conviction_picks": port_result.get("top_conviction_picks",
                                                  rule_fallback["top_conviction_picks"]),
        "sector_concentration_note": port_result.get("sector_concentration_note",
                                                       rule_fallback["sector_concentration_note"]),
        "per_stock": per_stock,
    }


def get_macro_context(conn, snap_date: str) -> str:
    """Pull a short macro brief from the snapshot universe so the LLM has context."""
    rows = _fetchall(conn, """
        SELECT
          COUNT(*) FILTER (WHERE stage='STAGE_2') AS n_stage2,
          COUNT(*) FILTER (WHERE stage='STAGE_4') AS n_stage4,
          COUNT(*) FILTER (WHERE trading_signal IN ('BUY','STRONG_BUY')) AS n_buy,
          COUNT(*) AS n_total,
          AVG(relative_strength) AS avg_rs
        FROM scores.stage_snapshots
        WHERE snapshot_date=%s
    """, (snap_date,))
    if not rows:
        return ""
    r = rows[0]
    return (
        f"Snapshot {snap_date}: {r['n_total']} stocks scanned; "
        f"Stage 2 count {r['n_stage2']} vs Stage 4 {r['n_stage4']}; "
        f"BUY/STRONG_BUY signals {r['n_buy']}; mean RS vs Nifty 500 "
        f"{(float(r['avg_rs']) if r['avg_rs'] else 0):.1f}%."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────────────────────────────────────
def _nz(v: Any, fmt: str = "{:.2f}") -> str:
    if v is None or v == "":
        return "—"
    try:
        return fmt.format(float(v))
    except Exception:
        return str(v)


def _pct(v: Any, decimals: int = 1) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.{decimals}f}%"
    except Exception:
        return str(v)


# ─────────────────────────────────────────────────────────────────────────────
# Markdown + HTML rendering
# ─────────────────────────────────────────────────────────────────────────────
def render_markdown(snap_date: str, picks: list[PickRationale], enriched: list[dict],
                    narratives: dict, macro_context: str) -> str:
    out: list[str] = []
    out.append(f"# Top Investment Picks Analysis — {snap_date}\n\n")
    out.append(f"*{AGENT_BRAND}*\n\n")
    out.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M IST')}  \n")
    out.append("**Sources:** Sector Rotation Report + Stage 2 Tracker + PostgreSQL `scores.*`, `market.equity_eod`\n\n")
    out.append(f"> **Disclaimer:** {REPORT_DISCLAIMER}\n\n")
    out.append("## Executive Summary\n\n")
    out.append(f"{narratives.get('executive_summary','')}\n\n")
    out.append(f"**Macro context:** {macro_context}\n\n")

    out.append("## Methodology\n\n")
    out.append("Picks merge two independent screens:\n\n")
    out.append("1. **Sector Rotation Report** — top investment-score names within the leading sectors.\n")
    out.append("2. **Stage 2 Tracker** — Weinstein-stage-2 universe ranked by `scores.stage_snapshots.investment_score`.\n\n")
    out.append("Dual-confirmed names (both screens) are prioritised. Per-stock deep dive uses 260 trading days of EOD: EMA20/50/200 stack, EMA50 slope, RSI(14), ATR(14), 52w hi/lo, 1M/3M/6M/1Y returns, volume ratio. Fundamentals: Piotroski F-score, Altman Z, Beneish M, ROE/ROCE, 3Y growth, D/E, promoter holding.\n\n")

    out.append("## Pick Summary\n\n")
    out.append("| # | Symbol | Sector | Price | Stage | Inv.Score | RS% | 6M Tgt | RR(4M) | Risk | Source |\n")
    out.append("|---|---|---|---:|---|---:|---:|---:|---:|:---:|---|\n")
    per_stock_narr_pre = narratives.get("per_stock", {}) or {}
    for i, (p, e) in enumerate(zip(picks, enriched), 1):
        snap = e["snapshot"] or {}
        narr_i = per_stock_narr_pre.get(p.symbol, {})
        rr_i = e.get("risk_reward") or {}
        tgt = narr_i.get("potential_target_long_term") or rr_i.get("target_6m")
        try: tgt_d = f"₹{float(tgt):,.0f}" if tgt is not None else "—"
        except (TypeError, ValueError): tgt_d = "—"
        rrv = narr_i.get("risk_reward_ratio") or rr_i.get("rr_ratio_4m")
        try: rr_d = f"{float(rrv):.2f}x" if rrv is not None else "—"
        except (TypeError, ValueError): rr_d = "—"
        rsv = narr_i.get("risk_score_0_10") if narr_i.get("risk_score_0_10") is not None else rr_i.get("risk_score")
        try: rs_d = f"{float(rsv):.1f}" if rsv is not None else "—"
        except (TypeError, ValueError): rs_d = "—"
        out.append(
            f"| {i} | **{p.symbol}** | {p.sector} | {_nz(snap.get('price'))} | "
            f"{snap.get('stage','—')} | {_nz(snap.get('investment_score'))} | "
            f"{_pct(snap.get('relative_strength'))} | {tgt_d} | {rr_d} | {rs_d} | {p.source} |\n"
        )

    out.append("\n## Per-Stock Deep Dive\n\n")
    per_stock_narr = narratives.get("per_stock", {})

    for i, (p, e) in enumerate(zip(picks, enriched), 1):
        snap = e["snapshot"] or {}
        tech = e["tech"]
        fund = e["fund"] or {}
        narr = per_stock_narr.get(p.symbol, {})

        out.append(f"### {i}. {p.symbol} — {p.sector}\n\n")
        out.append(f"**Why selected:** {p.rationale}\n\n")
        if narr.get("thesis"):
            out.append(f"**Thesis:** {narr['thesis']}\n\n")
        if narr.get("technical_view"):
            out.append(f"**Technical view:** {narr['technical_view']}\n\n")
        if narr.get("fundamental_view"):
            out.append(f"**Fundamental view:** {narr['fundamental_view']}\n\n")
        if narr.get("sector_view"):
            out.append(f"**Sector view:** {narr['sector_view']}\n\n")
        if narr.get("valuation_note"):
            out.append(f"**Valuation:** {narr['valuation_note']}\n\n")
        catalysts = narr.get("key_catalysts")
        if catalysts:
            if isinstance(catalysts, list):
                out.append("**Key catalysts:**\n")
                for c in catalysts:
                    out.append(f"- {c}\n")
                out.append("\n")
            else:
                out.append(f"**Key catalysts:** {catalysts}\n\n")
        risks = narr.get("key_risks") or narr.get("risks")
        if risks:
            if isinstance(risks, list):
                out.append("**Key risks:**\n")
                for r in risks:
                    out.append(f"- {r}\n")
                out.append("\n")
            else:
                out.append(f"**Key risks:** {risks}\n\n")
        if narr.get("action"):
            out.append(f"**Action:** {narr['action']}\n\n")
        rr_md = e.get("risk_reward") or {}
        if rr_md and "error" not in rr_md:
            def _m(v): 
                try: return f"₹{float(v):,.0f}"
                except (TypeError, ValueError): return "—"
            t1 = narr.get('potential_target_short_term') or rr_md.get('target_2m')
            t3 = narr.get('target_4m') or rr_md.get('target_4m')
            t12 = narr.get('potential_target_long_term') or rr_md.get('target_6m')
            sl = narr.get('stop_loss') or rr_md.get('stop_loss')
            rr_v = narr.get('risk_reward_ratio') or rr_md.get('rr_ratio_4m')
            rs_v = narr.get('risk_score_0_10') if narr.get('risk_score_0_10') is not None else rr_md.get('risk_score')
            tier = narr.get('risk_tier') or rr_md.get('risk_tier','')
            try: rr_disp = f"{float(rr_v):.2f}x" if rr_v is not None else "—"
            except (TypeError, ValueError): rr_disp = "—"
            try: rs_disp = f"{float(rs_v):.1f}" if rs_v is not None else "—"
            except (TypeError, ValueError): rs_disp = "—"
            out.append(
                f"**Targets:** 2M {_m(t1)} · 4M {_m(t3)} · 6M {_m(t12)}  \n"
                f"**Stop:** {_m(sl)} · **Risk/Reward (4M):** {rr_disp}  \n"
                f"**Risk score:** {rs_disp} / 10 ({tier}) · **Suggested size:** "
                f"{narr.get('position_size_pct') or rr_md.get('position_size_pct','—')}%\n\n"
            )
        if narr.get("conviction"):
            out.append(f"**Conviction:** **{narr['conviction']}** — {narr.get('conviction_rationale','')}\n\n")

        if snap:
            out.append("**Snapshot:**\n\n")
            out.append(f"- Price ₹{_nz(snap.get('price'))} · 1D {_pct(snap.get('change_1d_pct'))} · 1W {_pct(snap.get('change_1w_pct'))} · 1M {_pct(snap.get('change_1m_pct'))}\n")
            out.append(f"- Stage **{snap.get('stage')}** (score {_nz(snap.get('stage_score'))}) · Stance **{snap.get('stance')}** · Signal **{snap.get('trading_signal')}**\n")
            out.append(f"- Investment score {_nz(snap.get('investment_score'))} (tech {_nz(snap.get('technical_score'))}, fund {_nz(snap.get('enhanced_fund_score'))})\n")
            out.append(f"- Relative Strength {_pct(snap.get('relative_strength'))} vs Nifty 500; Supertrend {snap.get('supertrend_state')} around ₹{_nz(snap.get('supertrend_value'))}\n\n")

        if "error" not in tech:
            out.append("**Technicals:**\n\n")
            out.append("| Metric | Value |\n|---|---:|\n")
            out.append(f"| Close ({tech['trade_date']}) | ₹{_nz(tech['last'])} |\n")
            out.append(f"| EMA 20 / 50 / 200 | ₹{_nz(tech['ema20'])} / ₹{_nz(tech['ema50'])} / ₹{_nz(tech['ema200'])} |\n")
            if tech.get('ema50_slope_pct') is not None:
                out.append(f"| EMA50 slope (20d) | {_pct(tech['ema50_slope_pct'], 2)} |\n")
            if tech.get('rsi') is not None:
                out.append(f"| RSI(14) | {_nz(tech['rsi'])} |\n")
            if tech.get('atr') is not None:
                out.append(f"| ATR(14) | ₹{_nz(tech['atr'])} ({_pct(tech['atr_pct'], 2)}) |\n")
            out.append(f"| 52W High / Low | ₹{_nz(tech['wk52_high'])} / ₹{_nz(tech['wk52_low'])} |\n")
            out.append(f"| Distance from 52W high | {_pct(tech['dist_from_high_pct'])} |\n")
            out.append(f"| Returns 1M / 3M / 6M / 1Y | {_pct(tech['ret_1m'])} / {_pct(tech['ret_3m'])} / {_pct(tech['ret_6m'])} / {_pct(tech['ret_1y'])} |\n")
            if tech.get('last_vol_ratio') is not None:
                out.append(f"| Last-day volume vs 20d avg | {_nz(tech['last_vol_ratio'])}x |\n")
            out.append("\n")

        if fund:
            out.append("**Fundamentals:**\n\n")
            out.append("| Metric | Value |\n|---|---:|\n")
            out.append(f"| Piotroski F-score | {_nz(fund.get('piotroski_score'))} / 9 |\n")
            out.append(f"| Altman Z-score | {_nz(fund.get('altman_z_score'))} |\n")
            out.append(f"| Beneish M-score | {_nz(fund.get('beneish_m_score'))} |\n")
            out.append(f"| Forensic risk | {fund.get('forensic_risk') or '—'} |\n")
            out.append(f"| Revenue growth 3Y | {_pct(fund.get('revenue_growth_3y'))} |\n")
            out.append(f"| PAT growth 3Y | {_pct(fund.get('pat_growth_3y'))} |\n")
            out.append(f"| ROE | {_pct(fund.get('roe'))} |\n")
            out.append(f"| ROCE | {_pct(fund.get('roce'))} |\n")
            out.append(f"| Debt / Equity | {_nz(fund.get('debt_to_equity'))} |\n")
            out.append(f"| Promoter holding | {_pct(fund.get('promoter_holding'))} |\n\n")
        out.append("---\n\n")

    out.append("## Portfolio Construction\n\n")
    out.append(f"{narratives.get('portfolio_construction','')}\n\n")
    sec_counts: dict[str, int] = {}
    for p in picks:
        sec_counts[p.sector] = sec_counts.get(p.sector, 0) + 1
    out.append("**Sector spread:**\n\n")
    for s, c in sorted(sec_counts.items(), key=lambda x: -x[1]):
        out.append(f"- {s}: **{c}** name(s)\n")
    out.append("\n")

    out.append("## Full Disclaimer\n\n")
    out.append(f"{FULL_LEGAL_DISCLAIMER}\n")
    return "".join(out)


def _stock_card_html(idx: int, p: PickRationale, e: dict, narr: dict) -> str:
    snap = e["snapshot"] or {}
    tech = e["tech"]
    fund = e["fund"] or {}
    qtr = e.get("quarterly") or []
    ann = e.get("annual") or []
    bs = e.get("balance_sheet") or []
    cf = e.get("cash_flow") or []
    analytics = e.get("analytics") or {}
    fscore = e.get("fund_scores") or {}
    sec = e.get("sector_ctx") or {}
    events = e.get("corp_events") or []
    insider = e.get("insider") or []
    bulk_deals = e.get("bulk_deals") or []
    upcoming = e.get("upcoming_events") or []
    rr = dict(e.get("risk_reward") or {})
    narr = dict(narr or {})
    # Coerce LLM string outputs (e.g. "₹9,704 based on PAT CAGR…") to numeric
    def _coerce_num(v):
        if v is None or isinstance(v, (int, float)): return v
        try:
            import re as _re
            m = _re.search(r"-?\d[\d,]*\.?\d*", str(v))
            return float(m.group(0).replace(",", "")) if m else None
        except Exception:
            return None
    for _k in ("stop_loss", "potential_target_short_term", "target_4m", "target_3m",
               "potential_target_long_term", "risk_reward_ratio",
               "risk_score_0_10", "position_size_pct"):
        if _k in narr:
            narr[_k] = _coerce_num(narr[_k])
    for _k in ("entry_low", "entry_high", "stop_loss",
               "target_2m", "target_4m", "target_6m",
               "target_1m", "target_3m", "target_12m",
               "rr_ratio_4m", "rr_ratio_6m", "rr_ratio_3m", "rr_ratio_12m",
               "risk_per_share", "position_size_pct"):
        if _k in rr:
            rr[_k] = _coerce_num(rr[_k])
    h = html_mod.escape
    src_badge = {
        "dual": '<span class="mbadge mbadge-date" style="background:#16a34a">DUAL-CONFIRMED</span>',
        "sector_rot": '<span class="mbadge mbadge-date" style="background:#2563eb">SECTOR LEADER</span>',
        "stage2": '<span class="mbadge mbadge-date" style="background:#7c3aed">STAGE 2</span>',
    }.get(p.source, "")

    conv = (narr.get("conviction") or "").upper()
    conv_color = {"HIGH": "#16a34a", "MEDIUM": "#d97706", "LOW": "#64748b"}.get(conv, "#64748b")
    conv_badge = (
        f'<span class="mbadge mbadge-date" style="background:{conv_color}">CONVICTION: {h(conv)}</span>'
        if conv else ""
    )

    rows_tech = []
    if "error" not in tech:
        rows_tech.append(("Close", f"₹{_nz(tech['last'])} ({tech['trade_date']})"))
        rows_tech.append(("EMA 20/50/200", f"₹{_nz(tech['ema20'])} / ₹{_nz(tech['ema50'])} / ₹{_nz(tech['ema200'])}"))
        if tech.get('ema50_slope_pct') is not None:
            rows_tech.append(("EMA50 slope (20d)", _pct(tech['ema50_slope_pct'], 2)))
        rows_tech.append(("RSI(14)", _nz(tech.get('rsi'))))
        if tech.get('atr'):
            rows_tech.append(("ATR(14)", f"₹{_nz(tech['atr'])} ({_pct(tech.get('atr_pct'), 2)})"))
        rows_tech.append(("52W High / Low", f"₹{_nz(tech['wk52_high'])} / ₹{_nz(tech['wk52_low'])}"))
        rows_tech.append(("From 52W high", _pct(tech.get('dist_from_high_pct'))))
        rows_tech.append(("Returns 1M/3M/6M/1Y", f"{_pct(tech.get('ret_1m'))} / {_pct(tech.get('ret_3m'))} / {_pct(tech.get('ret_6m'))} / {_pct(tech.get('ret_1y'))}"))
        if tech.get('last_vol_ratio') is not None:
            rows_tech.append(("Vol vs 20d avg", f"{_nz(tech['last_vol_ratio'])}x"))

    rows_fund = []
    if fund or analytics:
        p_ = (fund or {}).get("_parsed") or {}
        def _add(label, v):
            rows_fund.append((label, v if v not in (None, "") else "—"))
        # Piotroski — DB column or 6/9 approximation from BS/PNL/CF
        ps_v = (fund or {}).get('piotroski_score')
        if ps_v is not None:
            _add("Piotroski F-score", f"{ps_v:.0f} / 9")
        elif analytics.get("piotroski_approx") is not None:
            _add("Piotroski F-score",
                 f"{analytics['piotroski_approx']:.0f} / {analytics['piotroski_max']} (approx)")
        else:
            _add("Piotroski F-score", None)
        # Altman — DB column or Z' from BS/PNL
        az_v = (fund or {}).get('altman_z_score')
        if az_v is not None:
            _add("Altman Z-score", _nz(az_v))
        elif analytics.get("altman_z_prime") is not None:
            _add("Altman Z-score", f"{analytics['altman_z_prime']:.2f} (Z′ approx)")
        else:
            _add("Altman Z-score", None)
        bm_v = (fund or {}).get('beneish_m_score')
        if bm_v is not None:
            _add("Beneish M-score", _nz(bm_v))
        elif analytics.get("beneish_m_simplified") is not None:
            flag = analytics.get("beneish_m_flag") or ""
            _add("Beneish M-score",
                 f"{analytics['beneish_m_simplified']:.2f} ({flag}, simplified)")
        else:
            _add("Beneish M-score", None)
        fr_v = (fund or {}).get('forensic_risk')
        if fr_v is not None:
            _add("Forensic risk", fr_v)
        elif analytics.get("forensic_risk_tier"):
            _add("Forensic risk", f"{analytics['forensic_risk_tier']} (derived)")
        else:
            _add("Forensic risk", None)
        # ROE / ROCE — DB column or computed from BS+PNL
        roe = (fund or {}).get('roe') if fund else None
        roe_src = ""
        if roe is None and analytics.get("roe_computed_pct") is not None:
            roe = analytics["roe_computed_pct"]; roe_src = " (computed)"
        roce = (fund or {}).get('roce') if fund else None
        roce_src = ""
        if roce is None and analytics.get("roce_computed_pct") is not None:
            roce = analytics["roce_computed_pct"]; roce_src = " (computed)"
        if roe is not None or roce is not None:
            _add("ROE / ROCE",
                 f"{(_pct(roe)+roe_src) if roe is not None else '—'} / "
                 f"{(_pct(roce)+roce_src) if roce is not None else '—'}")
        else:
            _add("ROE / ROCE", None)
        rg = (fund or {}).get('revenue_growth_3y')
        if rg is None and analytics.get("rev_cagr_pct") is not None:
            _add("Revenue growth (3Y)",
                 f"{_pct(analytics['rev_cagr_pct'])} ({analytics.get('cagr_years','—')}Y CAGR)")
        else:
            _add("Revenue growth (3Y)", _pct(rg) if rg is not None else None)
        pg = (fund or {}).get('pat_growth_3y')
        if pg is None and analytics.get("pat_cagr_pct") is not None:
            _add("PAT growth (3Y)",
                 f"{_pct(analytics['pat_cagr_pct'])} ({analytics.get('cagr_years','—')}Y CAGR)")
        else:
            _add("PAT growth (3Y)", _pct(pg) if pg is not None else None)
        de = (fund or {}).get('debt_to_equity')
        if de is None and analytics.get("de_ratio") is not None:
            _add("Debt / Equity", f"{analytics['de_ratio']:.2f} (computed)")
        else:
            _add("Debt / Equity", _nz(de) if de is not None else None)
        ph = (fund or {}).get('promoter_holding')
        _add("Promoter holding",
             _pct(ph) if ph is not None else None)
        # FII / DII institutional ownership (parsed from investor_summary)
        fii = p_.get("fii_pct"); dii = p_.get("dii_pct")
        if fii is not None or dii is not None:
            _add("FII / DII holding",
                 f"{(_pct(fii) if fii is not None else '—')} / "
                 f"{(_pct(dii) if dii is not None else '—')}")
        npm_v = p_.get('npm_pct')
        if npm_v is None and analytics.get("npm_computed_pct") is not None:
            _add("NPM", f"{_pct(analytics['npm_computed_pct'])} (computed)")
        else:
            _add("NPM", _pct(npm_v) if npm_v is not None else None)
        eps_v = p_.get('eps')
        if eps_v is None and analytics.get("eps_latest") is not None:
            _add("EPS", f"{_nz(analytics['eps_latest'])} (latest FY)")
        else:
            _add("EPS", _nz(eps_v) if eps_v is not None else None)

    # ---- Valuation rows (P/E derived, market-cap bucket, etc.) ----
    rows_val = []
    if fund or snap:
        p_ = (fund or {}).get("_parsed") or {}
        try:
            price = float(snap.get("price")) if snap and snap.get("price") is not None else None
        except (TypeError, ValueError):
            price = None
        eps_v = p_.get("eps")
        pe = (price / eps_v) if (price and eps_v) else None
        def _addv(label, v):
            rows_val.append((label, v if v not in (None, "") else "—"))
        _addv("Price", f"₹{price:,.1f}" if price is not None else None)
        _addv("EPS (TTM proxy)", f"{eps_v:.2f}" if eps_v is not None else None)
        _addv("P/E (price ÷ EPS)", f"{pe:.1f}x" if pe is not None else None)
        _addv("Market-cap bucket", snap.get("market_cap_cat") if snap else None)
        _addv("Sales (latest)",
              f"₹{p_['sales_latest_cr']:,.0f} Cr ({_pct(p_.get('sales_yoy_pct'))} YoY)"
              if p_.get('sales_latest_cr') is not None else None)
        _addv("PAT (latest)",
              f"₹{p_['pat_latest_cr']:,.0f} Cr ({_pct(p_.get('pat_yoy_pct'))} YoY)"
              if p_.get('pat_latest_cr') is not None else None)
        _addv("Net debt (3Y)",
              f"₹{analytics['net_debt_cr']:,.0f} Cr" if analytics.get('net_debt_cr') is not None else None)

    # Enhanced fundamental sub-scores (incl. CANSLIM + Minervini from stage_snapshots)
    rows_subscore = []
    if fscore:
        for label, key in [
            ("Earnings Quality", "earnings_quality"),
            ("Sales Growth", "sales_growth"),
            ("Financial Strength", "financial_strength"),
            ("Institutional Backing", "institutional_backing"),
            ("Composite Fund Score", "enhanced_fund_score"),
        ]:
            v = fscore.get(key)
            if v is not None:
                rows_subscore.append((label, f"{float(v):.1f}"))
    if snap:
        cs = snap.get("can_slim_score")
        if cs is not None:
            try:
                csf = float(cs)
                tag = (
                    "elite" if csf >= 20 else
                    "strong" if csf >= 15 else
                    "watch" if csf >= 10 else "weak"
                )
                rows_subscore.append(("CANSLIM (O'Neil, /25)", f"{csf:.1f} ({tag})"))
            except (TypeError, ValueError):
                pass
        mv = snap.get("minervini_score")
        if mv is not None:
            try:
                rows_subscore.append(("Minervini Trend (/8)", f"{float(mv):.1f}"))
            except (TypeError, ValueError):
                pass

    def _table(rows):
        if not rows:
            return ""
        body = "".join(f"<tr><td>{h(str(label))}</td><td style='text-align:right;font-weight:600'>{h(str(val))}</td></tr>" for label, val in rows)
        return f"<table style='width:100%;border-collapse:collapse'>{body}</table>"

    # Quarterly trend table (latest 4 quarters)
    qtr_html = ""
    if qtr:
        cells = ["<tr><th style='text-align:left'>Quarter</th><th style='text-align:right'>Revenue (₹ Cr)</th><th style='text-align:right'>OPM %</th><th style='text-align:right'>PAT (₹ Cr)</th><th style='text-align:right'>EPS</th></tr>"]
        for q in qtr[:4]:
            cells.append(
                f"<tr><td>{h(q['period_label'])}</td>"
                f"<td style='text-align:right'>{_nz(q['revenue'], '{:.0f}')}</td>"
                f"<td style='text-align:right'>{_nz(q['opm_pct'], '{:.0f}')}</td>"
                f"<td style='text-align:right'>{_nz(q['pat'], '{:.0f}')}</td>"
                f"<td style='text-align:right'>{_nz(q['eps'])}</td></tr>"
            )
        qtr_html = f"<table style='width:100%;border-collapse:collapse;font-size:12px'>{''.join(cells)}</table>"
        derived = []
        if analytics.get("rev_qoq_pct") is not None:
            derived.append(f"Rev QoQ <strong>{analytics['rev_qoq_pct']:+.1f}%</strong>")
        if analytics.get("rev_yoy_pct") is not None:
            derived.append(f"YoY <strong>{analytics['rev_yoy_pct']:+.1f}%</strong>")
        if analytics.get("pat_qoq_pct") is not None:
            derived.append(f"PAT QoQ <strong>{analytics['pat_qoq_pct']:+.1f}%</strong>")
        if analytics.get("pat_yoy_pct") is not None:
            derived.append(f"YoY <strong>{analytics['pat_yoy_pct']:+.1f}%</strong>")
        if analytics.get("opm_delta_bps") is not None:
            derived.append(f"OPM vs 4Q avg <strong>{analytics['opm_delta_bps']:+.0f} bps</strong>")
        if derived:
            qtr_html += f"<p style='margin-top:6px;font-size:11px;color:#475569'>{' · '.join(derived)}</p>"

    # Annual trajectory
    ann_html = ""
    if ann:
        cells = ["<tr><th style='text-align:left'>FY</th><th style='text-align:right'>Revenue (₹ Cr)</th><th style='text-align:right'>OPM %</th><th style='text-align:right'>PAT (₹ Cr)</th><th style='text-align:right'>EPS</th></tr>"]
        for a in ann:
            cells.append(
                f"<tr><td>{h(a['period_label'])}</td>"
                f"<td style='text-align:right'>{_nz(a['revenue'], '{:.0f}')}</td>"
                f"<td style='text-align:right'>{_nz(a['opm_pct'], '{:.0f}')}</td>"
                f"<td style='text-align:right'>{_nz(a['pat'], '{:.0f}')}</td>"
                f"<td style='text-align:right'>{_nz(a['eps'])}</td></tr>"
            )
        ann_html = f"<table style='width:100%;border-collapse:collapse;font-size:12px'>{''.join(cells)}</table>"
        if analytics.get("rev_cagr_pct") is not None or analytics.get("pat_cagr_pct") is not None:
            yrs = analytics.get("cagr_years", "—")
            ann_html += (
                f"<p style='margin-top:6px;font-size:11px;color:#475569'>"
                f"{yrs}Y CAGR — Revenue <strong>{_pct(analytics.get('rev_cagr_pct'))}</strong> · "
                f"PAT <strong>{_pct(analytics.get('pat_cagr_pct'))}</strong> · "
                f"EPS <strong>{_pct(analytics.get('eps_cagr_pct'))}</strong></p>"
            )

    # Balance sheet trend (3Y)
    bs_html = ""
    if bs:
        cells = ["<tr><th style='text-align:left'>FY</th><th style='text-align:right'>Borrowings (₹ Cr)</th><th style='text-align:right'>Net Debt (₹ Cr)</th><th style='text-align:right'>Total Assets (₹ Cr)</th></tr>"]
        for b in bs:
            cells.append(
                f"<tr><td>{h(b['period_label'])}</td>"
                f"<td style='text-align:right'>{_nz(b['borrowings'], '{:.0f}')}</td>"
                f"<td style='text-align:right'>{_nz(b['net_debt'], '{:.0f}')}</td>"
                f"<td style='text-align:right'>{_nz(b['total_assets'], '{:.0f}')}</td></tr>"
            )
        bs_html = f"<table style='width:100%;border-collapse:collapse;font-size:12px'>{''.join(cells)}</table>"
        bits = []
        if analytics.get("debt_trend"):
            bits.append(f"Debt trend <strong>{analytics['debt_trend']}</strong>")
        if analytics.get("net_cash_positive"):
            bits.append("<strong style='color:#16a34a'>Net cash positive</strong>")
        if analytics.get("computed_de_ratio") is not None:
            bits.append(f"D/E <strong>{analytics['computed_de_ratio']:.2f}</strong>")
        if bits:
            bs_html += f"<p style='margin-top:6px;font-size:11px;color:#475569'>{' · '.join(bits)}</p>"

    # Cash flow + quality
    cf_html = ""
    if cf:
        cells = ["<tr><th style='text-align:left'>FY</th><th style='text-align:right'>Operating CF</th><th style='text-align:right'>Investing CF</th><th style='text-align:right'>FCF proxy</th></tr>"]
        for c in cf:
            fcf = (float(c['operating_cf'] or 0) + float(c['investing_cf'] or 0))
            cells.append(
                f"<tr><td>{h(c['period_label'])}</td>"
                f"<td style='text-align:right'>{_nz(c['operating_cf'], '{:.0f}')}</td>"
                f"<td style='text-align:right'>{_nz(c['investing_cf'], '{:.0f}')}</td>"
                f"<td style='text-align:right'>{fcf:.0f}</td></tr>"
            )
        cf_html = f"<table style='width:100%;border-collapse:collapse;font-size:12px'>{''.join(cells)}</table>"
        if analytics.get("ocf_to_pat") is not None:
            tag = analytics.get("earnings_quality_flag", "")
            color = {"high": "#16a34a", "watch": "#d97706", "weak": "#b91c1c"}.get(tag, "#475569")
            cf_html += (
                f"<p style='margin-top:6px;font-size:11px;color:{color}'>"
                f"OCF/PAT (latest FY) <strong>{analytics['ocf_to_pat']:.2f}</strong> "
                f"→ earnings quality: <strong>{tag.upper()}</strong></p>"
            )

    # Sector context
    sector_html = ""
    if sec:
        sector_html = (
            f"<ul class='rotation-context-list' style='font-size:12px'>"
            f"<li>Sector: <strong>{h(s := str(sec.get('sector_name') or p.sector))}</strong></li>"
            f"<li>Sector strength: <strong>{_nz(sec.get('sector_strength'))}</strong></li>"
            f"<li>Peer avg RS: {_pct(sec.get('avg_rs'))} · "
            f"Avg tech: {_nz(sec.get('avg_tech'))} · "
            f"Avg fund: {_nz(sec.get('avg_fund'))}</li>"
            f"<li>Sector universe: {_nz(sec.get('total_stocks'), '{:.0f}')} stocks</li>"
            f"</ul>"
        )

    # Corporate events + insider activity + bulk/block deals + upcoming calendar
    news_bits = []
    for ev in events[:6]:
        news_bits.append(
            f"<li><span style='color:#2563eb;font-weight:600'>{h(str(ev['event_date']))}</span> "
            f"— {h(ev['event_type'] or '')}: {h((ev.get('purpose_raw') or '')[:140])}</li>"
        )
    for ins in insider[:4]:
        news_bits.append(
            f"<li><span style='color:#7c3aed;font-weight:600'>{h(str(ins['alert_date']))}</span> "
            f"— INSIDER {h(ins['alert_type'] or '')} "
            f"{h(str(ins['category'] or ''))}: {h(str(ins['entity'] or ''))} "
            f"(₹{_nz(ins['value_cr'])} Cr)</li>"
        )
    for bd in bulk_deals[:6]:
        try:
            val_cr = (float(bd.get('qty') or 0) * float(bd.get('price') or 0)) / 1e7
        except (TypeError, ValueError):
            val_cr = 0
        news_bits.append(
            f"<li><span style='color:#0891b2;font-weight:600'>{h(str(bd['deal_date']))}</span> "
            f"— {h(str(bd.get('deal_type') or 'DEAL'))} ({h(str(bd.get('side') or '')).upper()}): "
            f"{h(str(bd.get('entity') or ''))} · "
            f"{_nz(bd.get('qty'),'{:,.0f}')} @ ₹{_nz(bd.get('price'),'{:.2f}')} "
            f"(≈ ₹{val_cr:,.1f} Cr)</li>"
        )
    if upcoming:
        for ue in upcoming[:5]:
            news_bits.append(
                f"<li><span style='color:#16a34a;font-weight:600'>🗓 {h(str(ue['event_date']))}</span> "
                f"— UPCOMING {h(str(ue.get('event_type') or ''))}: {h(str(ue.get('detail') or ''))[:140]}</li>"
            )
    news_html = (
        f"<ul class='rotation-context-list' style='font-size:12px'>{''.join(news_bits)}</ul>"
        if news_bits else
        "<p style='color:#64748b;font-size:12px;margin:0'>"
        "No corporate events, insider transactions, bulk/block deals, or upcoming-calendar items "
        "found in the last 90 days across <code>signals.corporate_events</code>, "
        "<code>signals.insider_alerts</code>, <code>signals.bulk_block_deals</code>, "
        "<code>signals.v_upcoming_events</code>."
        "</p>"
    )

    headline_metrics = []
    if snap:
        headline_metrics = [
            ("Price", f"₹{_nz(snap.get('price'))}"),
            ("Inv. Score", _nz(snap.get('investment_score'))),
            ("RS vs Nifty 500", _pct(snap.get('relative_strength'))),
            ("Stance", h(snap.get('stance') or '—')),
        ]
    headline_html = "".join(
        f'<div class="metric-card" style="flex:1 1 120px"><div class="metric-label">{h(lbl)}</div>'
        f'<div class="metric-value" style="font-size:1.2rem">{val}</div></div>'
        for lbl, val in headline_metrics
    )

    # Verbatim filings extract (the text-summary columns from scores.fundamentals)
    filings_bits = []
    if fund:
        for label, key in [
            ("P&L", "pnl_summary"),
            ("Quarterly", "quarterly_summary"),
            ("Balance Sheet", "balance_sheet_summary"),
            ("Cash Flow", "cash_flow_summary"),
            ("Ratios", "ratios_summary"),
            ("Investors", "investor_summary"),
        ]:
            v = fund.get(key)
            if v:
                filings_bits.append(
                    f"<li><strong>{h(label)}:</strong> {h(str(v))}</li>"
                )
    filings_html = (
        f'<ul class="rotation-context-list" style="font-size:12px">{"".join(filings_bits)}</ul>'
        if filings_bits else ""
    )

    # Narrative pieces (lists vs strings: tolerate both)
    def _list_or_text(v):
        if isinstance(v, list):
            return "<ul style='margin:4px 0;padding-left:18px'>" + "".join(f"<li>{h(str(x))}</li>" for x in v) + "</ul>"
        return f"<p>{h(str(v or '—'))}</p>"

    # ---- Targets / Risk / Reward block ----
    def _fmt_money(v):
        try: return f"₹{float(v):,.0f}"
        except (TypeError, ValueError): return "—"
    def _fmt_rr(v):
        try: return f"{float(v):.2f}×"
        except (TypeError, ValueError): return "—"
    risk_score = narr.get("risk_score_0_10")
    try: risk_score_n = float(risk_score) if risk_score is not None else None
    except (TypeError, ValueError): risk_score_n = None
    risk_tier = narr.get("risk_tier") or (
        "LOW" if risk_score_n is not None and risk_score_n <= 3 else
        "MEDIUM" if risk_score_n is not None and risk_score_n <= 6 else
        "HIGH" if risk_score_n is not None else ""
    )
    risk_color = {"LOW": "#16a34a", "MEDIUM": "#d97706", "HIGH": "#b91c1c"}.get(risk_tier, "#64748b")

    rr_rows = [
        ("Entry zone (low–high)",
         f"{_fmt_money(rr.get('entry_low'))} – {_fmt_money(rr.get('entry_high'))}" if rr else "—"),
        ("Stop loss", _fmt_money(narr.get('stop_loss') if narr.get('stop_loss') is not None else (rr or {}).get('stop_loss'))),
        ("Target 2M", _fmt_money(narr.get('potential_target_short_term') if narr.get('potential_target_short_term') is not None else (rr or {}).get('target_2m'))),
        ("Target 4M", _fmt_money(narr.get('target_4m') if narr.get('target_4m') is not None else (rr or {}).get('target_4m'))),
        ("Target 6M", _fmt_money(narr.get('potential_target_long_term') if narr.get('potential_target_long_term') is not None else (rr or {}).get('target_6m'))),
        ("Reward / Risk (4M)", _fmt_rr(narr.get('risk_reward_ratio') if narr.get('risk_reward_ratio') is not None else (rr or {}).get('rr_ratio_4m'))),
        ("Reward / Risk (6M)", _fmt_rr((rr or {}).get('rr_ratio_6m'))),
        ("Risk per share", _fmt_money((rr or {}).get('risk_per_share'))),
        ("Suggested position size", f"{narr.get('position_size_pct') or (rr or {}).get('position_size_pct') or '—'}% of portfolio"),
    ]
    risk_factors = narr.get("risk_factors") or (rr or {}).get("risk_factors") or []
    risk_factors_html = (
        f"<p style='margin:6px 0 0 0;font-size:11px;color:#64748b'>"
        f"Risk score breakdown: {h(' · '.join(map(str, risk_factors)))}</p>"
        if risk_factors else ""
    )
    rr_card_html = (
        "<div class='overview-grid' style='margin-top:12px'>"
        "<div class='summary-card' style='background:#fff7ed'>"
        "<h3>🎯 Targets &amp; Risk/Reward</h3>"
        f"{_table(rr_rows)}{risk_factors_html}"
        "</div>"
        "<div class='summary-card' style='background:#fef2f2'>"
        "<h3>🛡️ Risk Score</h3>"
        f"<div style='font-size:36px;font-weight:800;color:{risk_color};line-height:1.1'>"
        f"{(f'{risk_score_n:.1f}' if risk_score_n is not None else '—')} <span style='font-size:18px'>/ 10</span></div>"
        f"<div style='margin-top:4px;font-size:13px;color:{risk_color};font-weight:700'>{h(risk_tier)}</div>"
        "<p style='margin-top:8px;font-size:12px;color:#475569'>"
        "0–3 LOW · 4–6 MEDIUM · 7–10 HIGH. Blends ATR-volatility, distance-from-high, RSI, "
        "Weinstein stage, Altman Z / Beneish M, debt trend &amp; OCF/PAT quality.</p>"
        "</div></div>"
    )

    # ── Candlestick + volume + S/R + targets chart (6-month)
    candlestick_html = ""
    if isinstance(tech, dict) and tech.get("chart"):
        candle_svg = _svg_candlestick(
            tech["chart"],
            symbol=p.symbol,
            entry_low=rr.get("entry_low"),
            entry_high=rr.get("entry_high"),
            stop=narr.get("stop_loss") or rr.get("stop_loss"),
            t1=narr.get("potential_target_short_term") or rr.get("target_2m"),
            t2=narr.get("target_4m") or rr.get("target_4m"),
            t3=narr.get("potential_target_long_term") or rr.get("target_6m"),
        )
        pv = tech["chart"].get("pivots") or {}
        sup = tech["chart"].get("support_levels") or []
        res = tech["chart"].get("resistance_levels") or []
        meta_bits = []
        if sup: meta_bits.append("Support: " + " · ".join(f"₹{float(v):,.0f}" for v in sup))
        if res: meta_bits.append("Resistance: " + " · ".join(f"₹{float(v):,.0f}" for v in res))
        if pv:  meta_bits.append(
            f"Pivots — PP ₹{pv['PP']:,.0f} · R1 ₹{pv['R1']:,.0f} · R2 ₹{pv['R2']:,.0f} · "
            f"S1 ₹{pv['S1']:,.0f} · S2 ₹{pv['S2']:,.0f}"
        )
        meta_html = (f'<div style="margin-top:8px;font-size:.75rem;color:#475569;line-height:1.6">'
                     f'{"<br>".join(meta_bits)}</div>') if meta_bits else ""
        legend_chips = (
            '<div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:6px;font-size:.7rem;'
            'font-weight:700;letter-spacing:.04em;color:#fff">'
            '<span style="background:#ffb74d;padding:3px 8px;border-radius:3px">EMA 20</span>'
            '<span style="background:#42a5f5;padding:3px 8px;border-radius:3px">EMA 50</span>'
            '<span style="background:#ab47bc;padding:3px 8px;border-radius:3px">EMA 200</span>'
            '<span style="background:#26a69a;padding:3px 8px;border-radius:3px">Support</span>'
            '<span style="background:#ef5350;padding:3px 8px;border-radius:3px">Resistance</span>'
            '<span style="background:#42a5f5;padding:3px 8px;border-radius:3px">Entry zone</span>'
            '<span style="background:#ef4444;padding:3px 8px;border-radius:3px">Stop</span>'
            '<span style="background:#2dd4bf;padding:3px 8px;border-radius:3px">T1 (2M)</span>'
            '<span style="background:#22c55e;padding:3px 8px;border-radius:3px">T2 (4M)</span>'
            '<span style="background:#a78bfa;padding:3px 8px;border-radius:3px">T3 (6M)</span>'
            '<span style="background:#a78bfa;padding:3px 8px;border-radius:3px">POC (Vol Profile)</span>'
            '<span style="background:#e879f9;padding:3px 8px;border-radius:3px">RSI 14</span>'
            '</div>'
        )
        chart_narr = (narr.get("chart_narrative") or "").strip()
        chart_narr_html = (
            f'<div style="margin-top:12px;padding:12px 14px;background:#0b0e14;'
            f'border:1px solid #1e222d;border-left:3px solid #42a5f5;border-radius:6px">'
            f'<div style="font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;'
            f'font-weight:800;color:#42a5f5;margin-bottom:6px">🤖 Chart Narrative · AI Read</div>'
            f'<div style="font-size:.82rem;color:#d1d4dc;line-height:1.6">{h(chart_narr)}</div>'
            f'</div>'
        ) if chart_narr else ""
        candlestick_html = f"""
<div class="tp-sub" style="margin-top:12px;background:#0f1218;border-color:#1e222d">
  <h4 style="color:#d1d4dc"><span class="ico">📈</span> 6-Month Price Action — TradingView-style: Candles · EMAs · Volume · RSI · S/R · Pivots · Volume Profile · Entry/Stop/Targets</h4>
  {candle_svg}
  {legend_chips}
  {chart_narr_html}
  <div style="margin-top:8px;font-size:.75rem;color:#9ca3af;line-height:1.6">{"<br>".join(meta_bits)}</div>
</div>
"""
    # ── Mini chart bars: quarterly revenue/PAT and annual revenue
    qtr_chart = ""
    if qtr:
        q4 = list(reversed(qtr[:4]))
        qtr_chart = _svg_bar_chart(
            labels=[(q.get("period_label","") or "")[:8] for q in q4],
            series=[
                ("Revenue (₹ Cr)", [q.get("revenue") for q in q4]),
                ("PAT (₹ Cr)",     [q.get("pat") for q in q4]),
            ],
            colors=["#2563eb", "#0f766e"],
            height=130,
        )
    ann_chart = ""
    if ann:
        a5 = list(reversed(ann[:5]))
        ann_chart = _svg_bar_chart(
            labels=[(a.get("period_label","") or "")[:8] for a in a5],
            series=[("Revenue (₹ Cr)", [a.get("revenue") for a in a5])],
            colors=["#7c3aed"],
            height=130,
        )
    # Returns sparkline (use 1M/3M/6M/1Y as a 4-point line)
    ret_spark = ""
    if "error" not in tech:
        ret_vals = [tech.get('ret_1m'), tech.get('ret_3m'), tech.get('ret_6m'), tech.get('ret_1y')]
        ret_spark = _svg_sparkline(ret_vals, color="#16a34a", fill="rgba(22,163,74,.12)")

    # Sub-score horizontal bars
    subscore_bars = ""
    sub_defs = [
        ("Earnings Quality", "earnings_quality", 10),
        ("Sales Growth",     "sales_growth", 10),
        ("Financial Strength","financial_strength", 10),
        ("Institutional",     "institutional_backing", 10),
        ("Composite",         "enhanced_fund_score", 100),
    ]
    bars = []
    if fscore:
        for lbl, key, mx in sub_defs:
            v = fscore.get(key)
            try: vf = float(v) if v is not None else None
            except (TypeError, ValueError): vf = None
            bars.append(_hbar(lbl, vf, mx, color_hint="auto"))
    # CANSLIM (O'Neil) + Minervini Trend from stage_snapshots
    if snap:
        cs = snap.get("can_slim_score")
        try: cs_f = float(cs) if cs is not None else None
        except (TypeError, ValueError): cs_f = None
        if cs_f is not None:
            bars.append(_hbar("CANSLIM (O'Neil)", cs_f, 25, color_hint="auto"))
        mv = snap.get("minervini_score")
        try: mv_f = float(mv) if mv is not None else None
        except (TypeError, ValueError): mv_f = None
        if mv_f is not None:
            bars.append(_hbar("Minervini Trend", mv_f, 8, color_hint="auto"))
    if bars:
        subscore_bars = "".join(bars)

    # ── CANSLIM (O'Neil) — C/A/N/S/L/I/M component breakdown
    canslim_block = ""
    p_for_canslim = (fund or {}).get("_parsed") or {}
    cs_breakdown = _canslim_breakdown(snap or {}, tech or {}, fund or {},
                                       qtr or [], ann or [], p_for_canslim,
                                       market_regime=None)
    cs_comp25 = cs_breakdown["composite_25"]
    cs_stored = cs_breakdown["stored_total"]
    comps = cs_breakdown["components"]
    method_badge = {
        "real":    '<span style="font-size:.6rem;background:#dcfce7;color:#15803d;padding:1px 5px;border-radius:3px;margin-left:4px" title="Computed from actual reported financial data">✓ real</span>',
        "derived": '<span style="font-size:.6rem;background:#e0f2fe;color:#0369a1;padding:1px 5px;border-radius:3px;margin-left:4px" title="Derived from live market data (price, volume, EMA) — the standard O\'Neil screener signal for this criterion">derived</span>',
        "proxy":   '<span style="font-size:.6rem;background:#fef3c7;color:#92400e;padding:1px 5px;border-radius:3px;margin-left:4px" title="⚠ Price-momentum proxy used — structured earnings data not yet available for this stock. Check screener.in.">⚠ proxy</span>',
        "context": '<span style="font-size:.6rem;background:#e0e7ff;color:#3730a3;padding:1px 5px;border-radius:3px;margin-left:4px">context</span>',
        "":        "",
    }
    rows = []
    for key in ("C", "A", "N", "S", "L", "I", "M"):
        c = comps[key]
        sc = c["score"]
        sc_disp = f"{sc}/{c['max']}" if sc is not None else "—"
        ratio = (sc / c["max"]) if (sc is not None and c["max"]) else 0
        bar_cls = "green" if ratio >= 0.7 else "amber" if ratio >= 0.4 else ("red" if sc is not None else "")
        bar_pct = max(0, min(100, ratio * 100)) if sc is not None else 0
        info_flag = " · info-only" if c.get("informational") else ""
        tip = _METRIC_TOOLTIPS.get(f"CANSLIM-{key}") or c["name"]
        rows.append(
            f'<div class="cs-row">'
            f'  <div class="cs-key">{key}<span class="tp-info" title="{html_mod.escape(tip)}">i</span></div>'
            f'  <div class="cs-mid">'
            f'    <div class="cs-name">{html_mod.escape(c["name"])}{method_badge.get(c.get("method",""),"")}{html_mod.escape(info_flag)}</div>'
            f'    <div class="cs-detail">{html_mod.escape(c["detail"])}</div>'
            f'    <div class="cs-track"><div class="cs-fill {bar_cls}" style="width:{bar_pct:.0f}%"></div></div>'
            f'  </div>'
            f'  <div class="cs-score">{sc_disp}</div>'
            f'</div>'
        )
    header_bits = []
    if cs_comp25 is not None:
        header_bits.append(f"Composite (C+A+N+S+L): <b>{cs_comp25}/25</b>")
    if cs_stored is not None and cs_comp25 is not None and abs(int(cs_stored) - cs_comp25) > 0:
        header_bits.append(f"Stored: {int(cs_stored)}/25")
    header_html = (f'<div style="font-size:.75rem;color:#475569;margin-bottom:6px">'
                   f'{" · ".join(header_bits)}</div>') if header_bits else ""
    canslim_block = (
        f'<div class="cs-box">{header_html}{"".join(rows)}'
        f'<p style="margin:8px 0 0;font-size:.68rem;color:#64748b;line-height:1.5">'
        f'<b>real</b> = computed from financials · <b>proxy</b> = price/volume substitute when financials unavailable · '
        f'I (institutional) &amp; M (market) are informational and not part of the 25-pt composite.'
        f'</p></div>'
    )

    # Risk gauge SVG
    risk_gauge_svg = _svg_gauge(risk_score_n) if risk_score_n is not None else ""

    # Targets ladder
    last_price = None
    try: last_price = float((snap or {}).get("price") or tech.get("last"))
    except (TypeError, ValueError): pass
    targets_ladder = _svg_targets(
        last=last_price,
        entry_low=rr.get("entry_low"), entry_high=rr.get("entry_high"),
        stop=narr.get("stop_loss") or rr.get("stop_loss"),
        t1=narr.get("potential_target_short_term") or rr.get("target_2m"),
        t2=narr.get("target_4m") or rr.get("target_4m"),
        t3=narr.get("potential_target_long_term") or rr.get("target_6m"),
    )

    # KPI hero tiles
    kpi_tiles_html = ""
    if snap:
        change_1m = snap.get('change_1m_pct')
        try: ch_1m = float(change_1m) if change_1m is not None else None
        except (TypeError, ValueError): ch_1m = None
        ch_cls = "green" if (ch_1m or 0) > 0 else "red" if (ch_1m or 0) < 0 else ""
        rs_val_k = snap.get('relative_strength')
        try: rs_k = float(rs_val_k) if rs_val_k is not None else None
        except (TypeError, ValueError): rs_k = None
        rs_cls = "green" if (rs_k or 0) > 5 else "amber" if (rs_k or 0) > 0 else "red"
        inv_v = snap.get('investment_score')
        try: inv_n = float(inv_v) if inv_v is not None else None
        except (TypeError, ValueError): inv_n = None
        inv_cls = "green" if (inv_n or 0) >= 70 else "amber" if (inv_n or 0) >= 50 else "red"

        tiles = [
            ("green" if (ch_1m or 0) > 0 else "red" if (ch_1m or 0) < 0 else "",
             "Price", f"₹{_nz(snap.get('price'))}",
             f"1M {_pct(ch_1m)}" if ch_1m is not None else ""),
            (inv_cls, "Investment Score", _nz(inv_n) if inv_n is not None else "—",
             f"Tech {_nz(snap.get('technical_score'))} · Fund {_nz(snap.get('enhanced_fund_score'))}"),
            (rs_cls, "Relative Strength", _pct(rs_k), "vs Nifty 500"),
            ("violet", "Stage", h(snap.get('stage') or '—'),
             f"Stance: {h(snap.get('stance') or '—')}"),
            (("green" if risk_tier=="LOW" else "amber" if risk_tier=="MEDIUM" else "red" if risk_tier=="HIGH" else ""),
             "Risk Score", (f"{risk_score_n:.1f}/10" if risk_score_n is not None else "—"),
             risk_tier or ""),
            ("green",
             "6M Target",
             (f"₹{float(narr.get('potential_target_long_term') or rr.get('target_6m') or 0):,.0f}"
              if (narr.get('potential_target_long_term') or rr.get('target_6m')) else "—"),
             f"RR {_fmt_rr(narr.get('risk_reward_ratio') or rr.get('rr_ratio_4m'))}"),
        ]
        kpi_tiles_html = "".join(
            f'<div class="tp-kpi-tile {cls}"><div class="lbl">{h(lbl)}</div>'
            f'<div class="val">{val}</div><div class="sub">{sub}</div></div>'
            for cls, lbl, val, sub in tiles
        )

    # Narrative blocks
    def _narr_blk(cls, label, icon, value):
        if not value: return ""
        if isinstance(value, list):
            body = "<ul>" + "".join(f"<li>{h(str(x))}</li>" for x in value) + "</ul>"
        else:
            body = f"<p>{h(str(value))}</p>"
        return f'<div class="blk {cls}"><h5>{icon} {h(label)}</h5>{body}</div>'

    # Street View / Analyst consensus (collapsible per stock)
    street_view = (narr.get("street_view") or "").strip()
    ac = narr.get("analyst_consensus") if isinstance(narr.get("analyst_consensus"), dict) else None
    street_html = ""
    if street_view or ac:
        # ── Structured analyst-consensus pane (rating + targets + bull/bear)
        ac_html = ""
        if ac:
            rating = str(ac.get("consensus_rating") or "").upper().strip()
            rating_cls = {
                "BUY": "green", "OVERWEIGHT": "green",
                "HOLD": "amber",
                "UNDERWEIGHT": "red", "SELL": "red",
            }.get(rating, "slate")
            est = str(ac.get("estimate_trend") or "").strip()
            est_cls = {"Upward": "green", "Downward": "red", "Stable": "slate"}.get(est, "slate")

            def _t(v):
                try: return f"₹{float(v):,.0f}"
                except (TypeError, ValueError): return "—"
            tm, tl, th = ac.get("target_median"), ac.get("target_low"), ac.get("target_high")
            try:
                price_now = float((snap or {}).get("price") or 0)
                upside = ((float(tm) / price_now) - 1) * 100 if (tm and price_now) else None
            except (TypeError, ValueError):
                upside = None
            upside_txt = (
                f"<span style='color:{'#16a34a' if (upside or 0) >= 0 else '#b91c1c'};"
                f"font-weight:700;margin-left:6px'>({upside:+.1f}%)</span>"
                if upside is not None else ""
            )
            bulls = ac.get("bull_points") or []
            bears = ac.get("bear_points") or []
            bull_html = "".join(f"<li>{h(str(b))}</li>" for b in bulls[:4])
            bear_html = "".join(f"<li>{h(str(b))}</li>" for b in bears[:4])
            tr_text = ac.get("target_rationale") or ""
            disc = ac.get("rating_disclaimer") or "Synthesised from dossier — no live broker poll wired."

            ac_html = (
                "<div class='ac-grid'>"
                f"  <div class='ac-tile'>"
                f"    <div class='ac-cap'>Consensus Rating</div>"
                f"    <div><span class='tp-chip {rating_cls}' style='font-size:.85rem;padding:4px 12px'>{h(rating or '—')}</span></div>"
                f"  </div>"
                f"  <div class='ac-tile'>"
                f"    <div class='ac-cap'>12m Target (median){upside_txt}</div>"
                f"    <div class='ac-val'>{_t(tm)}</div>"
                f"    <div class='ac-sub'>Range: {_t(tl)} – {_t(th)}</div>"
                f"  </div>"
                f"  <div class='ac-tile'>"
                f"    <div class='ac-cap'>Estimate Trend (3M)</div>"
                f"    <div><span class='tp-chip {est_cls}' style='padding:3px 10px'>{h(est or '—')}</span></div>"
                f"  </div>"
                "</div>"
                f"<p class='ac-rationale'>📐 {h(tr_text)}</p>"
                "<div class='ac-bullbear'>"
                f"  <div class='ac-side bull'><div class='ac-cap'>📈 Bull case (would highlight)</div><ul>{bull_html}</ul></div>"
                f"  <div class='ac-side bear'><div class='ac-cap'>📉 Bear case (would flag)</div><ul>{bear_html}</ul></div>"
                "</div>"
                f"<p class='ac-disc'>⚠️ {h(disc)}</p>"
            )

        # Wrap narrative paragraph (street_view) + structured pane in one details
        body_html = ac_html
        if street_view:
            body_html += (
                f"<p style='margin:12px 0 0;color:#334155;font-size:.85rem;"
                f"line-height:1.55;border-top:1px dashed #cbd5e1;padding-top:10px'>"
                f"<b style='color:#0f172a'>Narrative:</b> {h(street_view)}</p>"
            )

        street_html = (
            "<details class='tp-street' open style='margin-top:10px;border:1px solid #cbd5e1;"
            "border-radius:10px;padding:12px 16px;background:#f8fafc'>"
            "<summary style='cursor:pointer;font-weight:700;color:#0f172a;font-size:.92rem;list-style:none'>"
            "🏛️ Analyst / Street Consensus "
            "<span style='font-weight:400;color:#64748b;font-size:.75rem'>(synthesised — no live broker feed)</span>"
            "</summary>"
            f"<div style='margin-top:10px'>{body_html}</div>"
            "</details>"
        )

    narr_blocks_html = "".join([
        _narr_blk("", "Thesis", "💡", narr.get("thesis")),
        _narr_blk("tech", "Technical View", "📈", narr.get("technical_view")),
        _narr_blk("fund", "Fundamental View", "🏦", narr.get("fundamental_view")),
        _narr_blk("sector", "Sector View", "🧭", narr.get("sector_view")),
        _narr_blk("val", "Valuation", "💰", narr.get("valuation_note")),
        _narr_blk("cat", "Key Catalysts", "🚀", narr.get("key_catalysts")),
        _narr_blk("risk", "Key Risks", "⚠️", narr.get("key_risks")),
        _narr_blk("act", "Action", "🎯", narr.get("action")),
    ])

    # Conviction chip
    conv_cls = {"HIGH":"green","MEDIUM":"amber","LOW":"slate"}.get(conv, "slate")
    src_label = {"dual":"Dual-Confirmed","sector_rot":"Sector Leader","stage2":"Stage 2"}.get(p.source, p.source or "")
    src_cls = {"dual":"green","sector_rot":"blue","stage2":"violet"}.get(p.source, "slate")
    risk_chip_cls = {"LOW":"green","MEDIUM":"amber","HIGH":"red"}.get(risk_tier, "slate")

    # Tech KV table
    def _kv(rows):
        if not rows: return ""
        def _label_html(k: str) -> str:
            tip = _METRIC_TOOLTIPS.get(k)
            if not tip:
                # Try a normalized key (strip trailing "(...)" or "/N" qualifiers)
                k2 = k.split("(")[0].strip().rstrip("·,;").strip()
                tip = _METRIC_TOOLTIPS.get(k2)
            if not tip:
                return h(k)
            return f'{h(k)}<span class="tp-info" title="{h(tip)}">i</span>'
        body = "".join(f"<tr><td>{_label_html(str(k))}</td><td>{h(str(v))}</td></tr>" for k, v in rows)
        return f"<table class='tp-tbl tp-kv'><tbody>{body}</tbody></table>"

    return f"""
<section class="tp-card" id="pick-{idx}">
  <div class="stripe"></div>
  <div class="tp-card-hd">
    <div class="tp-card-num">{idx}</div>
    <div style="flex:1 1 220px">
      <h2 class="tp-card-name">{h(p.symbol)} <small>· {h(p.sector)}</small></h2>
      <div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:6px">
        <span class="tp-chip {src_cls}">{h(src_label)}</span>
        {f'<span class="tp-chip {conv_cls}">Conviction: {h(conv)}</span>' if conv else ''}
        {f'<span class="tp-chip {risk_chip_cls}">Risk: {h(risk_tier)}</span>' if risk_tier else ''}
        <span class="tp-chip blue">Signal: {h(snap.get('trading_signal') or '—')}</span>
        <span class="tp-chip slate">Supertrend: {h(snap.get('supertrend_state') or '—')}</span>
      </div>
    </div>
    <div style="width:170px;flex:0 0 auto">{ret_spark}</div>
  </div>

  <div class="tp-card-bd">
    <div class="tp-kpi-row">{kpi_tiles_html}</div>

    {candlestick_html}

    <div class="tp-narr">{narr_blocks_html}</div>

    {street_html}

    <div class="tp-grid">
      <div class="tp-sub">
        <h4><span class="ico">T</span> Technicals</h4>
        {_kv(rows_tech) if rows_tech else f'<p style="color:#b45309;margin:0">{h(tech.get("error","no data"))}</p>'}
      </div>
      <div class="tp-sub teal">
        <h4><span class="ico">F</span> Fundamental Scores</h4>
        {_kv(rows_fund) if rows_fund else '<p style="color:#64748b;margin:0">No fundamentals row.</p>'}
      </div>
      <div class="tp-sub" style="background:#f5f3ff;border-color:#ddd6fe">
        <h4 style="color:#5b21b6"><span class="ico" style="background:#7c3aed">Q</span> Quality Score Breakdown</h4>
        {subscore_bars if subscore_bars else '<p style="color:#64748b;margin:0">No sub-scores available.</p>'}
        <p style="margin-top:8px;font-size:.7rem;color:#6b7280;line-height:1.5">
          Component sub-scores feeding the composite. Earnings Quality, Sales Growth,
          Financial Strength and Institutional Backing are each on a 0–10 scale;
          Composite is the blended 0–100 enhanced fundamental score.
        </p>
        <div style="margin-top:14px;padding-top:12px;border-top:1px dashed #c4b5fd">
          <h5 style="color:#5b21b6;margin:0 0 8px;font-size:.78rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase">CANSLIM Breakdown (C·A·N·S·L·I·M)</h5>
          {canslim_block}
        </div>
      </div>
      <div class="tp-sub" style="background:#fffbeb">
        <h4><span class="ico">$</span> Valuation</h4>
        {_kv(rows_val) if rows_val else '<p style="color:#64748b;margin:0">No valuation inputs.</p>'}
        <p style="margin-top:8px;font-size:.7rem;color:#64748b;line-height:1.5">
          P/E is derived as <code>price ÷ EPS (TTM proxy)</code> from <code>scores.fundamentals.ratios_summary</code>.
          Forward multiples (P/B, EV/EBITDA, div yield) not currently in dataset.
        </p>
      </div>
      <div class="tp-sub violet">
        <h4><span class="ico">S</span> Sector Context</h4>
        {sector_html or '<p style="color:#64748b;margin:0">No sector aggregate.</p>'}
      </div>
    </div>

    <div class="tp-grid">
      <div class="tp-sub warn" style="grid-column:span 2">
        <h4><span class="ico">🎯</span> Targets &amp; Risk / Reward</h4>
        {targets_ladder}
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:8px">
          {_kv(rr_rows[:5])}
          {_kv(rr_rows[5:])}
        </div>
        {risk_factors_html}
      </div>
      <div class="tp-sub bad">
        <h4><span class="ico">🛡</span> Risk Score</h4>
        <div class="tp-gauge">
          <div style="flex:1">{risk_gauge_svg}</div>
          <div>
            <div class="tp-gauge-num" style="color:{risk_color}">{(f'{risk_score_n:.1f}' if risk_score_n is not None else '—')}<small> / 10</small></div>
            <div class="tp-gauge-tier" style="color:{risk_color}">{h(risk_tier)}</div>
          </div>
        </div>
        <p style="margin-top:8px;font-size:.72rem;color:#64748b;line-height:1.5">
          0–3 LOW · 4–6 MEDIUM · 7–10 HIGH. Blends ATR-volatility, distance-from-high, RSI, Weinstein stage, Altman Z / Beneish M, debt &amp; OCF quality.
        </p>
      </div>
    </div>

    <div class="tp-grid">
      <div class="tp-sub">
        <h4><span class="ico">Q</span> Latest Quarterly Results</h4>
        {qtr_chart}
        {qtr_html or '<p style="color:#64748b">No quarterly data.</p>'}
      </div>
      <div class="tp-sub">
        <h4><span class="ico">A</span> 5-Year Annual Trajectory</h4>
        {ann_chart}
        {ann_html or '<p style="color:#64748b">No annual data.</p>'}
      </div>
    </div>

    <div class="tp-grid">
      <div class="tp-sub">
        <h4><span class="ico">B</span> Balance Sheet (3Y)</h4>
        {bs_html or '<p style="color:#64748b">No BS data.</p>'}
      </div>
      <div class="tp-sub">
        <h4><span class="ico">C</span> Cash Flow (3Y) &amp; Quality</h4>
        {cf_html or '<p style="color:#64748b">No CF data.</p>'}
      </div>
    </div>

    <div class="tp-grid">
      <div class="tp-sub">
        <h4><span class="ico">N</span> Corporate Events &amp; Insider Activity (90d)</h4>
        {news_html}
      </div>
      <div class="tp-sub">
        <h4><span class="ico">📄</span> Latest Filings Snapshot</h4>
        {filings_html or '<p style="color:#64748b;font-size:12px;margin:0">No filing summaries.</p>'}
      </div>
    </div>

    {f'<p style="margin-top:14px;font-size:.72rem;color:#64748b;border-top:1px dashed #e2e8f0;padding-top:8px"><strong>Why selected:</strong> {h(p.rationale)} · <em>{h(narr.get("conviction_rationale",""))}</em></p>' if narr else ''}
  </div>
</section>
"""


def render_html(snap_date: str, picks: list[PickRationale], enriched: list[dict],
                narratives: dict, macro_context: str) -> str:
    h = html_mod.escape
    logo_uri = _asset_data_uri(AGENT_LOGO_PATH)
    logo_html = f'<img class="brand-logo" src="{logo_uri}" alt="Agent adda logo">' if logo_uri else ''

    # Executive summary brief card (same look as sector rotation Market Brief)
    exec_summary = narratives.get("executive_summary", "")
    portfolio_text = narratives.get("portfolio_construction", "")
    per_stock_narr = narratives.get("per_stock", {})

    # Aggregate KPIs across all picks
    rs_vals = _safe_floats([(e.get("snapshot") or {}).get("relative_strength") for e in enriched])
    inv_vals = _safe_floats([(e.get("snapshot") or {}).get("investment_score") for e in enriched])
    risk_vals = _safe_floats([
        ((per_stock_narr.get(p.symbol, {}).get("risk_score_0_10"))
         or (e.get("risk_reward") or {}).get("risk_score"))
        for p, e in zip(picks, enriched)
    ])
    upside_vals = []
    for p, e in zip(picks, enriched):
        n = per_stock_narr.get(p.symbol, {})
        rr_i = e.get("risk_reward") or {}
        tgt = n.get("potential_target_long_term") or rr_i.get("target_6m")
        last = (e.get("snapshot") or {}).get("price") or (e.get("tech") or {}).get("last")
        try:
            if tgt is not None and last is not None and float(last) > 0:
                upside_vals.append((float(tgt)-float(last))/float(last)*100)
        except (TypeError, ValueError):
            pass

    def _avg(vs): return sum(vs)/len(vs) if vs else None
    avg_rs = _avg(rs_vals)
    avg_inv = _avg(inv_vals)
    avg_risk = _avg(risk_vals)
    avg_up = _avg(upside_vals)

    dual_n = sum(1 for p in picks if p.source == "dual")
    high_conv = sum(1 for p in picks
                    if (per_stock_narr.get(p.symbol, {}).get("conviction") or "").upper() == "HIGH")

    hero_kpis = "".join([
        f'<div class="tp-kpi"><div class="tp-kpi-lbl">Picks</div>'
        f'<div class="tp-kpi-val">{len(picks)}</div>'
        f'<div class="tp-kpi-sub">{dual_n} dual-confirmed</div></div>',
        f'<div class="tp-kpi"><div class="tp-kpi-lbl">Avg Inv. Score</div>'
        f'<div class="tp-kpi-val">{avg_inv:.0f}</div>'
        f'<div class="tp-kpi-sub">across portfolio</div></div>' if avg_inv is not None else '',
        f'<div class="tp-kpi"><div class="tp-kpi-lbl">Avg RS %</div>'
        f'<div class="tp-kpi-val">{avg_rs:+.1f}%</div>'
        f'<div class="tp-kpi-sub">vs Nifty 500</div></div>' if avg_rs is not None else '',
        f'<div class="tp-kpi"><div class="tp-kpi-lbl">Avg 12M Upside</div>'
        f'<div class="tp-kpi-val">{avg_up:+.0f}%</div>'
        f'<div class="tp-kpi-sub">computed targets</div></div>' if avg_up is not None else '',
        f'<div class="tp-kpi"><div class="tp-kpi-lbl">Avg Risk Score</div>'
        f'<div class="tp-kpi-val">{avg_risk:.1f}<span style="font-size:.9rem;color:#cbd5e1">/10</span></div>'
        f'<div class="tp-kpi-sub">0=low · 10=high</div></div>' if avg_risk is not None else '',
        f'<div class="tp-kpi"><div class="tp-kpi-lbl">High Conviction</div>'
        f'<div class="tp-kpi-val">{high_conv}</div>'
        f'<div class="tp-kpi-sub">of {len(picks)} picks</div></div>',
    ])

    hero_html = f"""
<section class="tp-hero">
  <div class="tp-hero-row">
    <div>
      <div class="tp-hero-kicker">{h(AGENT_BRAND)} · Equity Research</div>
      <h1 class="tp-hero-title">Top Investment Picks Analysis</h1>
      <p class="tp-hero-sub">Highest-conviction names merged from the Sector Rotation Report and Stage 2 Tracker, with deep technical · fundamental · risk-reward analysis and LLM-narrated investment thesis.</p>
      <div class="tp-hero-meta">
        <span class="tp-pill blue">Report Date · {h(snap_date)}</span>
        <span class="tp-pill green">{len(picks)} picks</span>
        <span class="tp-pill violet">{dual_n} dual-confirmed</span>
        <span class="tp-pill amber">Generated {datetime.now().strftime('%d %b %Y %H:%M IST')}</span>
      </div>
    </div>
    {logo_html if logo_html else ''}
  </div>
  <div class="tp-kpis">{hero_kpis}</div>
</section>
"""

    # Sticky TOC
    toc_links = "".join(
        f'<a href="#pick-{i}"><span class="num">{i}</span> {h(p.symbol)}</a>'
        for i, p in enumerate(picks, 1)
    )
    toc_html = f'<nav class="tp-toc"><span class="tp-toc-title">Jump to:</span>{toc_links}</nav>'

    # Sector donut card
    sector_counts: dict[str, int] = {}
    for p in picks:
        sector_counts[p.sector] = sector_counts.get(p.sector, 0) + 1
    sector_slices = sorted(sector_counts.items(), key=lambda x: -x[1])
    donut_svg = _svg_donut([(s, c) for s, c in sector_slices])
    legend_palette = ["#2563eb","#0f766e","#d97706","#7c3aed","#0891b2","#16a34a","#b91c1c","#475569","#db2777","#65a30d"]
    legend_html = "".join(
        f'<div style="display:flex;align-items:center;gap:6px;font-size:.78rem;color:#334155;margin:3px 0">'
        f'<span style="width:10px;height:10px;border-radius:3px;background:{legend_palette[i%len(legend_palette)]}"></span>'
        f'<span style="flex:1">{h(s)}</span><strong>{c}</strong></div>'
        for i, (s, c) in enumerate(sector_slices)
    )
    sector_card = f"""
<div class="tp-sub violet" style="display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin-top:14px">
  <div style="width:170px;flex:0 0 auto">{donut_svg}</div>
  <div style="flex:1 1 200px">
    <h4 style="margin-top:0"><span class="ico">📊</span> Sector Concentration</h4>
    {legend_html}
  </div>
</div>
"""
    summary_rows = []
    for i, (p, e) in enumerate(zip(picks, enriched), 1):
        snap = e["snapshot"] or {}
        narr_i = per_stock_narr.get(p.symbol, {})
        rr_i = e.get("risk_reward") or {}
        conv_i = (narr_i.get("conviction") or "").upper()
        conv_c = {"HIGH": "#16a34a", "MEDIUM": "#d97706", "LOW": "#64748b"}.get(conv_i, "#64748b")
        rs_val = narr_i.get("risk_score_0_10")
        try: rs_val = float(rs_val) if rs_val is not None else None
        except (TypeError, ValueError): rs_val = None
        if rs_val is None:
            rs_val = rr_i.get("risk_score")
        rs_disp = f"{rs_val:.1f}" if rs_val is not None else "—"
        rs_c = ("#16a34a" if (rs_val or 99) <= 3 else
                "#d97706" if (rs_val or 99) <= 6 else "#b91c1c") if rs_val is not None else "#64748b"
        rr_val = (narr_i.get("risk_reward_ratio")
                   if narr_i.get("risk_reward_ratio") is not None
                   else rr_i.get("rr_ratio_4m"))
        try: rr_disp = f"{float(rr_val):.2f}×" if rr_val is not None else "—"
        except (TypeError, ValueError): rr_disp = "—"
        tgt = (narr_i.get("potential_target_long_term")
               if narr_i.get("potential_target_long_term") is not None
               else rr_i.get("target_6m"))
        try: tgt_disp = f"₹{float(tgt):,.0f}" if tgt is not None else "—"
        except (TypeError, ValueError): tgt_disp = "—"
        conv_chip_cls = {"HIGH":"green","MEDIUM":"amber","LOW":"slate"}.get(conv_i, "slate")
        risk_chip_cls = ("green" if (rs_val is not None and rs_val <= 3) else
                         "amber" if (rs_val is not None and rs_val <= 6) else
                         "red"   if rs_val is not None else "slate")
        src_chip = {"dual":("green","Dual"),"sector_rot":("blue","Sector"),"stage2":("violet","Stage2")}.get(p.source,("slate", p.source or ""))
        summary_rows.append(
            f"<tr><td style='font-weight:700;color:#64748b'>{i}</td>"
            f"<td><a href='#pick-{i}'>{h(p.symbol)}</a></td>"
            f"<td style='color:#475569;font-size:.78rem'>{h(p.sector)}</td>"
            f"<td style='text-align:right'>₹{_nz(snap.get('price'))}</td>"
            f"<td><span class='tp-chip slate'>{h(snap.get('stage') or '—')}</span></td>"
            f"<td style='text-align:right;font-weight:700'>{_nz(snap.get('investment_score'))}</td>"
            f"<td style='text-align:right;color:{'#16a34a' if (snap.get('relative_strength') or 0) > 0 else '#b91c1c'}'>{_pct(snap.get('relative_strength'))}</td>"
            f"<td style='text-align:right;font-weight:700'>{tgt_disp}</td>"
            f"<td style='text-align:right;font-weight:700'>{rr_disp}</td>"
            f"<td style='text-align:center'><span class='tp-chip {risk_chip_cls}'>{rs_disp}</span></td>"
            f"<td><span class='tp-chip {conv_chip_cls}'>{h(conv_i or '—')}</span></td>"
            f"<td><span class='tp-chip {src_chip[0]}'>{h(src_chip[1])}</span></td></tr>"
        )

    summary_table_html = f"""
<div style="margin-top:18px">
  <h2 style="font-size:1.05rem;color:var(--tp-blue);margin:0 0 10px;letter-spacing:-.01em">📊 Pick Summary — {snap_date}</h2>
  <table class="tp-master">
    <thead><tr>
      <th>#</th><th style="text-align:left">Symbol</th><th style="text-align:left">Sector</th>
      <th style='text-align:right'>Price</th>
      <th>Stage</th><th style='text-align:right'>Inv.Score</th>
      <th style='text-align:right'>RS%</th>
      <th style='text-align:right'>6M Tgt</th>
      <th style='text-align:right'>RR (4M)</th>
      <th style='text-align:center'>Risk</th>
      <th>Conviction</th><th>Source</th>
    </tr></thead>
    <tbody>{''.join(summary_rows)}</tbody>
  </table>
</div>
"""

    cards_html = "".join(
        _stock_card_html(i, p, e, per_stock_narr.get(p.symbol, {}))
        for i, (p, e) in enumerate(zip(picks, enriched), 1)
    )

    # Build the rich investment brief panel
    brief_blocks_html = ""
    top_conv = narratives.get("top_conviction_picks") or []
    sec_note = narratives.get("sector_concentration_note") or ""
    blk_specs = [
        ("Executive Summary", "📋", exec_summary, "blue"),
        ("Macro Context",     "🌐", macro_context,  "violet"),
        ("Portfolio Construction", "🧱", portfolio_text, "teal"),
        ("Top Conviction",    "🏆", " · ".join(top_conv) if top_conv else "", "green"),
        ("Sector Concentration", "🧭", sec_note, "amber"),
    ]
    blk_color = {"blue":"#2563eb","violet":"#7c3aed","teal":"#0f766e","green":"#16a34a","amber":"#d97706"}
    def _to_bullets(text: str) -> str:
        import re as _re
        if not text:
            return ""
        # Split by bullet/newline markers first, else by sentence boundaries
        parts: list[str] = []
        if "\n" in text or "•" in text or " · " in text:
            raw = _re.split(r"[\n•]|\s·\s", text)
        else:
            raw = _re.split(r"(?<=[\.\?\!])\s+(?=[A-Z0-9])", text)
        for p in raw:
            s = p.strip(" -•\t").rstrip(".")
            if s and len(s) > 2:
                parts.append(s)
        if not parts:
            return ""
        lis = "".join(f"<li style=\"margin:0 0 6px 0\">{h(s)}.</li>" for s in parts)
        return f'<ul style="margin:0;padding-left:20px;font-size:.85rem;color:#334155;line-height:1.55">{lis}</ul>'

    cards = []
    for label, icon, body, color in blk_specs:
        if not body: continue
        cards.append(
            f'<div style="background:#fff;border:1px solid var(--tp-line);border-left:4px solid {blk_color[color]};'
            f'border-radius:10px;padding:14px 16px">'
            f'<div style="font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;color:{blk_color[color]};'
            f'font-weight:800;margin-bottom:8px">{icon} {h(label)}</div>'
            f'{_to_bullets(body)}</div>'
        )
    brief_html = (
        '<div style="display:flex;flex-direction:column;gap:12px;margin-top:14px">'
        + "".join(cards) + '</div>'
    ) if cards else ""

    methodology_html = """
<div class="tp-sub" style="margin-top:14px;background:#fff">
  <h4><span class="ico">📐</span> Methodology</h4>
  <p style="font-size:.83rem;color:#475569;margin:0 0 6px">Picks merge two independent screens:</p>
  <ol style="margin:0 0 6px 22px;font-size:.83rem;color:#334155;line-height:1.6">
    <li><strong>Sector Rotation Report</strong> — top investment-score names within leading sectors (RS, momentum, tech + fund score).</li>
    <li><strong>Stage 2 Tracker</strong> — Weinstein-stage-2 universe ranked by <code>scores.stage_snapshots.investment_score</code>.</li>
  </ol>
  <p style="font-size:.78rem;color:#64748b;margin:4px 0 0">Dual-confirmed names are prioritised. Per-stock dive uses 260d EOD (EMA 20/50/200, RSI/ATR, returns), 6-month candles with S/R + pivots + volume profile, and fundamentals (Piotroski F, Altman Z, Beneish M, ROE/ROCE, 3Y growth, D/E, promoter).</p>
</div>
"""

    disclaimer_html = f"""
<div class="tp-sub warn" style="margin-top:14px">
  <h4><span class="ico">⚖️</span> Full Disclaimer &amp; Use Restrictions</h4>
  <p style="font-size:12px;line-height:1.6;color:#78350f">{h(PRINT_FOOTER_DISCLAIMER)}</p>
  <p style="font-size:11px;line-height:1.55;color:#92400e">{h(FULL_LEGAL_DISCLAIMER)}</p>
</div>
"""

    parts = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>Top Investment Picks — {snap_date}</title>',
        f'<style>{_CSS}\n{_EXTRA_CSS}</style>',
        '</head>',
        '<body style="background:#f1f5f9;padding:0;margin:0">',
        f'<div class="print-page-header"><span>{h(AGENT_BRAND)}</span><span>Top Investment Picks</span></div>',
        f'<div class="print-page-footer">{h(PRINT_FOOTER_DISCLAIMER)}</div>',
        '<div style="max-width:1180px;margin:0 auto;padding:0 18px 30px">',
        hero_html,
        f'<div class="disc" style="margin-top:14px;padding:10px 14px;background:#fff7ed;border-left:4px solid #d97706;border-radius:8px;font-size:.78rem;color:#92400e"><strong>Disclaimer:</strong> {h(REPORT_DISCLAIMER)}</div>',
        brief_html,
        sector_card,
        toc_html,
        summary_table_html,
        methodology_html,
        '<h2 style="font-size:1.2rem;color:var(--tp-blue);margin:24px 0 6px;letter-spacing:-.01em">🔬 Per-Stock Deep Dive</h2>',
        '<p style="font-size:.82rem;color:#64748b;margin:0 0 10px">Each card: candlestick chart with EMAs, S/R, pivots &amp; entry/stop/targets · KPI tiles · LLM-narrated thesis · technicals · fundamentals · quarterly / annual / BS / CF · events · risk gauge.</p>',
        cards_html,
        disclaimer_html,
        '</div>',
        '<button class="tp-totop" onclick="window.scrollTo({top:0,behavior:\'smooth\'})" title="Back to top">↑</button>',
        TV_CROSSHAIR_JS,
        '</body></html>',
    ]
    return "".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline orchestration
# ─────────────────────────────────────────────────────────────────────────────
def build_report(snap_date: str | None = None, use_llm: bool = True,
                 dry_run: bool = False) -> tuple[Path, Path] | None:
    TOP_PICKS_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_DIR.mkdir(parents=True, exist_ok=True)

    conn = _connect()
    try:
        snap_date = _resolve_snapshot_date(conn, snap_date)
        print(f"   Snapshot date: {snap_date}")
        picks = build_pick_list(conn, snap_date, MAX_PICKS)
        if not picks:
            print("   ⚠️  No picks resolved — aborting")
            return None
        print(f"   Picks: {[p.symbol for p in picks]}")

        macro_context = get_macro_context(conn, snap_date)

        enriched = []
        for p in picks:
            qtr = get_quarterly(conn, p.symbol)
            ann = get_annual(conn, p.symbol)
            bs = get_balance_sheet(conn, p.symbol)
            cf = get_cash_flow(conn, p.symbol)
            snap_row = get_snapshot(conn, p.symbol, snap_date)
            tech_row = compute_technicals(conn, p.symbol, snap_date)
            fund_row = get_fundamentals(conn, p.symbol)
            analytics_row = compute_financial_analytics(qtr, ann, bs, cf)
            enriched.append({
                "symbol": p.symbol,
                "sector": p.sector,
                "source": p.source,
                "snapshot": snap_row,
                "tech": tech_row,
                "fund": fund_row,
                "quarterly": qtr,
                "annual": ann,
                "balance_sheet": bs,
                "cash_flow": cf,
                "fund_scores": get_fund_score_breakdown(conn, p.symbol),
                "sector_ctx": get_sector_context(conn, p.sector, snap_date),
                "corp_events": get_corporate_events(conn, p.symbol),
                "insider": get_insider_activity(conn, p.symbol),
                "bulk_deals": get_bulk_block_deals(conn, p.symbol),
                "upcoming_events": get_upcoming_events(conn, p.symbol),
                "analytics": analytics_row,
                "risk_reward": compute_risk_reward(tech_row, snap_row, fund_row, analytics_row),
            })

        narratives = generate_narratives(enriched, macro_context, snap_date, use_llm=use_llm)

        md = render_markdown(snap_date, picks, enriched, narratives, macro_context)
        html_doc = render_html(snap_date, picks, enriched, narratives, macro_context)

        stamp = snap_date.replace("-", "")
        md_path = TOP_PICKS_DIR / f"Top_Investment_Picks_Analysis_{stamp}.md"
        html_path = TOP_PICKS_DIR / f"Top_Investment_Picks_Analysis_{stamp}.html"

        if dry_run:
            print(f"   [DRY RUN] would write {md_path.name} ({len(md):,} chars) + {html_path.name} ({len(html_doc):,} chars)")
            return (md_path, html_path)

        md_path.write_text(md)
        html_path.write_text(html_doc)
        # Symlink-style copies for /latest
        (LATEST_DIR / "top_picks.md").write_text(md)
        (LATEST_DIR / "top_picks.html").write_text(html_doc)

        print(f"   ✅ MD:   {md_path}")
        print(f"   ✅ HTML: {html_path}")
        return (md_path, html_path)
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Top Investment Picks Analysis report")
    ap.add_argument("--date", default=None, help="Snapshot date YYYY-MM-DD (default: latest in PG)")
    ap.add_argument("--no-llm", action="store_true", help="Skip LLM narrative; use rule-based")
    ap.add_argument("--dry-run", action="store_true", help="Plan only, no writes")
    ap.add_argument("--print-picks", action="store_true",
                    help="Print today's top-pick symbols (comma-separated) and exit. "
                         "Used by daily_refresh to pre-refresh fundamentals.")
    args = ap.parse_args()

    if args.print_picks:
        try:
            conn = _connect()
            snap = _resolve_snapshot_date(conn, args.date)
            picks = build_pick_list(conn, snap)
            print(",".join(p.symbol for p in picks))
            return 0
        except Exception as exc:
            print(f"❌ print-picks failed: {exc}", file=sys.stderr)
            return 2

    try:
        result = build_report(
            snap_date=args.date,
            use_llm=not args.no_llm,
            dry_run=args.dry_run,
        )
        return 0 if result else 1
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(f"❌ top_picks_report failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
