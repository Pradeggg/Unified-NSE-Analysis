#!/usr/bin/env python3
"""Build a standalone visual market overview from the latest Agent Adda data."""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "latest" / "market_overview_20260820.html"
DATED = ROOT / "reports" / "market_overview" / "market_overview_20260820.html"


def pct(value: float) -> str:
    return f"{value:+.2f}%"


def colour(value: float) -> str:
    return "#16a34a" if value > 0 else "#dc2626" if value < 0 else "#64748b"


def bar_chart(rows: list[dict], key: str, title: str, subtitle: str) -> str:
    scale = max(abs(float(row[key])) for row in rows) or 1
    items = []
    for row in rows:
        value = float(row[key])
        width = max(2.5, abs(value) / scale * 100)
        items.append(
            f'<div class="bar-row"><div class="bar-label">{html.escape(row["name"])}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{width:.1f}%;background:{colour(value)}"></div></div>'
            f'<div class="bar-value" style="color:{colour(value)}">{pct(value)}</div></div>'
        )
    return f'<section class="panel"><h2>{title}</h2><p class="sub">{subtitle}</p>{"".join(items)}</section>'


def breadth_chart(rows: list[dict]) -> str:
    items = []
    for row in rows:
        value = float(row["breadth"])
        state = "healthy" if value >= 65 else "neutral" if value >= 40 else "weak"
        items.append(
            f'<div class="breadth-row"><div><strong>{html.escape(row["name"])}</strong>'
            f'<small>{html.escape(row["signal"])}</small></div>'
            f'<div class="gauge"><span style="width:{value:.1f}%" class="{state}"></span></div>'
            f'<b>{value:.1f}%</b></div>'
        )
    return '<section class="panel span-2"><h2>Sector participation</h2><p class="sub">Percentage of constituents above their 50-day moving average</p>' + "".join(items) + '</section>'


def line_chart(history: pd.DataFrame) -> str:
    data = history.tail(35)
    values = data["summation"].astype(float).tolist()
    width, height, pad = 760, 230, 28
    lo, hi = min(values), max(values)
    spread = hi - lo or 1
    points = []
    for index, value in enumerate(values):
        x = pad + index * (width - 2 * pad) / max(1, len(values) - 1)
        y = pad + (hi - value) * (height - 2 * pad) / spread
        points.append(f"{x:.1f},{y:.1f}")
    zero_y = pad + (hi - 0) * (height - 2 * pad) / spread
    return f'''<section class="panel span-2"><h2>Market breadth trend</h2>
    <p class="sub">McClellan-style summation proxy · persistent decline indicates narrowing participation</p>
    <svg viewBox="0 0 {width} {height}" role="img" aria-label="Breadth summation trend">
      <defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ef4444" stop-opacity=".32"/><stop offset="1" stop-color="#ef4444" stop-opacity=".03"/></linearGradient></defs>
      <line x1="{pad}" y1="{zero_y:.1f}" x2="{width-pad}" y2="{zero_y:.1f}" stroke="#94a3b8" stroke-dasharray="5 5"/>
      <polyline points="{' '.join(points)}" fill="none" stroke="#dc2626" stroke-width="4" stroke-linejoin="round"/>
      <text x="{pad}" y="{height-5}" class="svg-label">{data.iloc[0]['date']}</text>
      <text x="{width-pad}" y="{height-5}" text-anchor="end" class="svg-label">{data.iloc[-1]['date']}</text>
      <text x="{width-pad}" y="{pad}" text-anchor="end" class="svg-value">Latest {values[-1]:,.0f}</text>
    </svg></section>'''


def main() -> None:
    indices = pd.read_csv(ROOT / "data" / "nse_index_data.csv")
    indices["TIMESTAMP"] = pd.to_datetime(indices["TIMESTAMP"])
    indices = indices.sort_values(["SYMBOL", "TIMESTAMP"])
    selected = [
        ("Nifty 50", "NIFTY 50"), ("Nifty 500", "NIFTY 500"),
        ("Nifty Midcap 150", "MIDCAP 150"), ("Nifty Smallcap 500", "SMALLCAP 500"),
        ("Nifty Bank", "BANK"), ("Nifty IT", "IT"), ("Nifty Auto", "AUTO"),
        ("Nifty Metal", "METAL"), ("Nifty Pharma", "PHARMA"),
        ("Nifty FMCG", "FMCG"), ("Nifty Realty", "REALTY"),
        ("Nifty PSU Bank", "PSU BANK"),
    ]
    perf = []
    for symbol, label in selected:
        frame = indices[indices["SYMBOL"].str.casefold() == symbol.casefold()]
        closes = frame["CLOSE"].astype(float).reset_index(drop=True)
        if len(closes) < 64:
            continue
        perf.append({
            "name": label, "close": closes.iloc[-1],
            "d1": (closes.iloc[-1] / closes.iloc[-2] - 1) * 100,
            "d5": (closes.iloc[-1] / closes.iloc[-6] - 1) * 100,
            "m1": (closes.iloc[-1] / closes.iloc[-22] - 1) * 100,
            "m3": (closes.iloc[-1] / closes.iloc[-64] - 1) * 100,
        })

    live = json.loads((ROOT / "data" / "_macro_cache" / "nse_indices_20260820.json").read_text())
    live_rows = []
    for key in ["NIFTY 50", "NIFTY 500", "NIFTY MIDCAP 150", "NIFTY SMALLCAP 250", "NIFTY BANK", "NIFTY IT"]:
        row = live[key]
        live_rows.append((key.replace("NIFTY ", ""), row["last"], row["percentChange"]))

    breadth = pd.read_csv(ROOT / "data" / "sector_breadth.csv")
    breadth_rows = [
        {"name": row.sector, "breadth": row.pct_above_50dma,
         "signal": f'{row.breadth_signal} · 5D {row.change_5d:+.1f} pts' + (" · internal weakness" if row.divergence_alert == "INT_WEAKNESS" else "")}
        for row in breadth.itertuples()
    ]
    breadth_rows.sort(key=lambda row: row["breadth"], reverse=True)
    history = pd.read_csv(ROOT / "data" / "breadth_history.csv")
    latest_breadth = history.iloc[-1]
    flows = pd.read_csv(ROOT / "data" / "fii_dii_flows.csv").iloc[-1]

    live_cards = "".join(
        f'<div class="metric"><span>{name}</span><strong>{value:,.2f}</strong><em style="color:{colour(change)}">{pct(change)}</em></div>'
        for name, value, change in live_rows
    )
    leaders = sorted([row for row in perf if row["name"] not in {"NIFTY 50", "NIFTY 500", "MIDCAP 150", "SMALLCAP 500", "BANK"}], key=lambda row: row["m3"], reverse=True)
    broad = [row for row in perf if row["name"] in {"NIFTY 50", "NIFTY 500", "MIDCAP 150", "SMALLCAP 500", "BANK"}]
    risk_cards = '''
      <div class="risk amber"><b>Breadth divergence</b><span>852 advances vs 1,777 declines on Aug 19; summation fell to -2,282.</span></div>
      <div class="risk amber"><b>Do not chase</b><span>Several Defence, Auto and industrial leaders have RSI above 70.</span></div>
      <div class="risk red"><b>Weak participation</b><span>Energy, Financial Services, Infrastructure and FMCG remain below 40% breadth.</span></div>
      <div class="risk blue"><b>Liquidity support</b><span>DII 5-day net buying is ₹12,452 crore; FII 5-day flow is broadly neutral.</span></div>'''
    generated = datetime.now().astimezone().strftime("%d %b %Y · %H:%M %Z")
    doc = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agent Adda Market Overview · 20 Aug 2026</title><style>
:root{{--ink:#10233f;--muted:#64748b;--line:#dbe5ef;--green:#16a34a;--red:#dc2626;--amber:#d97706;--blue:#2563eb;--panel:#fff}}
*{{box-sizing:border-box}} body{{margin:0;background:#eef3f8;color:var(--ink);font:14px/1.5 Inter,Segoe UI,Arial,sans-serif}}
.hero{{background:linear-gradient(130deg,#071b35,#123d70 62%,#0e7490);color:white;padding:44px max(5vw,28px) 54px}} .hero h1{{font-size:38px;margin:0 0 8px}} .hero p{{max-width:920px;color:#dbeafe;margin:0}}
.stamp{{display:inline-block;margin-bottom:15px;padding:5px 10px;border:1px solid #60a5fa;border-radius:999px;font-size:12px}} .wrap{{max-width:1220px;margin:-25px auto 50px;padding:0 20px}}
.metrics{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}} .metric,.panel{{background:#fff;border:1px solid var(--line);border-radius:14px;box-shadow:0 8px 24px #1e3a5f12}}
.metric{{padding:15px}} .metric span,.metric em{{display:block;font-size:11px;font-style:normal}} .metric strong{{font-size:19px}} .grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}} .panel{{padding:22px}}
.span-2{{grid-column:span 2}} h2{{margin:0;font-size:19px}} .sub{{color:var(--muted);font-size:12px;margin:3px 0 18px}}
.bar-row{{display:grid;grid-template-columns:105px 1fr 65px;align-items:center;gap:10px;margin:11px 0}} .bar-label{{font-size:12px;font-weight:700}} .bar-track,.gauge{{height:9px;background:#e8eef5;border-radius:9px;overflow:hidden}} .bar-fill{{height:100%;border-radius:9px}} .bar-value{{text-align:right;font-weight:800}}
.breadth-row{{display:grid;grid-template-columns:220px 1fr 55px;gap:14px;align-items:center;padding:8px 0;border-bottom:1px solid #edf2f7}} .breadth-row small{{display:block;color:var(--muted)}} .breadth-row b{{text-align:right}} .gauge span{{display:block;height:100%}} .healthy{{background:#16a34a}} .neutral{{background:#d97706}} .weak{{background:#dc2626}}
.callout{{padding:18px;border-left:5px solid #2563eb;background:#eff6ff;border-radius:10px;font-size:16px}} .risks{{display:grid;grid-template-columns:1fr 1fr;gap:10px}} .risk{{padding:15px;border-radius:10px;border-left:5px solid}} .risk b,.risk span{{display:block}} .risk span{{color:#475569;font-size:12px;margin-top:4px}} .amber{{background:#fffbeb;border-color:#d97706}} .red{{background:#fef2f2;border-color:#dc2626}} .blue{{background:#eff6ff;border-color:#2563eb}}
.matrix{{width:100%;border-collapse:collapse}} .matrix th,.matrix td{{padding:10px;border-bottom:1px solid var(--line);text-align:right}} .matrix th:first-child,.matrix td:first-child{{text-align:left}} .tag{{font-size:11px;font-weight:800;padding:4px 8px;border-radius:999px}} .tag.good{{background:#dcfce7;color:#166534}} .tag.watch{{background:#fef3c7;color:#92400e}} .tag.avoid{{background:#fee2e2;color:#991b1b}}
svg{{width:100%;height:auto;background:#fbfdff;border-radius:10px}} .svg-label{{font-size:11px;fill:#64748b}} .svg-value{{font-size:13px;fill:#991b1b;font-weight:bold}} footer{{color:#64748b;font-size:11px;margin-top:18px;text-align:center}}
@media(max-width:800px){{.metrics{{grid-template-columns:repeat(2,1fr)}}.grid{{grid-template-columns:1fr}}.span-2{{grid-column:auto}}.breadth-row{{grid-template-columns:130px 1fr 48px}}.risks{{grid-template-columns:1fr}}}}
</style></head><body><header class="hero"><span class="stamp">AGENT ADDA · MARKET INTELLIGENCE</span><h1>India Market Overview</h1><p>Leadership, participation, rotation and risk dashboard · Live snapshot 20 August 2026; breadth and return analytics through 19 August close.</p></header>
<main class="wrap"><div class="metrics">{live_cards}</div><div class="grid">
<section class="panel span-2"><div class="callout"><strong>Market stance: selective risk-on / rotation.</strong> The positive opening is constructive, but it follows a broad negative session and does not yet repair the multi-day breadth divergence. Prefer quality leaders at controlled entries; avoid chasing vertical moves.</div></section>
{bar_chart(broad, 'm3', 'Broad-index leadership', 'Three-month performance through 19 August close')}
{bar_chart(leaders, 'm1', 'Sector momentum', 'One-month performance · green is leadership, red is underperformance')}
{line_chart(history)}
{breadth_chart(breadth_rows[:14])}
<section class="panel span-2"><h2>Rotation map</h2><p class="sub">Where evidence is strongest and where confirmation is still required</p><table class="matrix"><thead><tr><th>Area</th><th>Trend</th><th>Breadth</th><th>Action</th></tr></thead><tbody>
<tr><td>IT</td><td>1M +5.0%</td><td>100%</td><td><span class="tag good">LEADER</span></td></tr><tr><td>Auto & ancillaries</td><td>1M +7.0% · 3M +12.6%</td><td>76.5%</td><td><span class="tag good">LEADER</span></td></tr><tr><td>Defence</td><td>1M +4.9% · 3M +9.2%</td><td>82.4%</td><td><span class="tag good">BUY PULLBACKS</span></td></tr><tr><td>Manufacturing / capital goods</td><td>1M +3.0%</td><td>Mixed</td><td><span class="tag good">SELECTIVE</span></td></tr><tr><td>Logistics</td><td>1M +6.2% · 3M +13.4%</td><td>63.3%, falling</td><td><span class="tag watch">WATCH BREADTH</span></td></tr><tr><td>Banks</td><td>1M -1.0% · 3M +6.9%</td><td>40–58%</td><td><span class="tag watch">NEEDS CONFIRMATION</span></td></tr><tr><td>Realty</td><td>1M -3.5% · 3M +16.7%</td><td>60%, falling sharply</td><td><span class="tag watch">CONSOLIDATION</span></td></tr><tr><td>FMCG / Energy / broad Financials</td><td>Underperforming</td><td>24–38%</td><td><span class="tag avoid">CAUTION</span></td></tr></tbody></table></section>
<section class="panel span-2"><h2>Areas to watch out for</h2><p class="sub">Signals that could change the constructive rotation view</p><div class="risks">{risk_cards}</div></section>
<section class="panel"><h2>Institutional flows</h2><p class="sub">Cash-market flows through 19 August</p><div class="metric"><span>FII today / 5D</span><strong>₹{flows.fii_net_today:,.0f}cr / ₹{flows.fii_net_5d:,.0f}cr</strong></div><div class="metric"><span>DII today / 5D</span><strong>₹{flows.dii_net_today:,.0f}cr / ₹{flows.dii_net_5d:,.0f}cr</strong></div></section>
<section class="panel"><h2>Decision checklist</h2><p class="sub">What confirms a broader risk-on move</p><ul><li>Multiple sessions with advances exceeding declines.</li><li>NIFTY 500 holds above the rebound while 50-DMA breadth expands.</li><li>Private-bank and financial breadth improve above 50%.</li><li>Breakouts show volume confirmation; VIX remains controlled.</li></ul></section>
</div><footer>Generated {generated} from Agent Adda NSE index, sector-breadth, institutional-flow and intraday datasets. Educational research only; not investment advice. Agent Adda is not SEBI registered.</footer></main></body></html>'''
    OUT.parent.mkdir(parents=True, exist_ok=True)
    DATED.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc, encoding="utf-8")
    DATED.write_text(doc, encoding="utf-8")
    print(OUT)
    print(DATED)


if __name__ == "__main__":
    main()
