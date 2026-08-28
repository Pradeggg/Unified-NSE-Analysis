"""
Agent Adda — Midcap Leaders Fund Dashboard (themed renderer)
============================================================
Reads the latest Midcap Leaders preselection CSV and renders a self-contained
dark-terminal HTML report matching the Agent Adda visual identity.

Output:
  reports/latest/midcap_fund_dashboard.html          ← live symlink target
  reports/fund/{YEAR}/Midcap_Leaders_{YYYYMMDD}.html ← archive copy

Usage:
  python scripts/generate_midcap_fund_report.py
  python scripts/generate_midcap_fund_report.py --run-date 20260824
  python scripts/generate_midcap_fund_report.py --no-open
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parents[1]
MF_DIR = ROOT / "Mutual Funds"
REPORTS_LATEST = ROOT / "reports" / "latest"
REPORTS_ARCHIVE = ROOT / "reports" / "fund"

# ── helpers ───────────────────────────────────────────────────────────────────

def _f(v, default=0.0):
    try:
        return float(str(v).replace(",", "").strip() or default)
    except (ValueError, TypeError):
        return default


def _latest_csv(run_date: str | None) -> Path:
    pattern = f"agent_adda_midcap_leaders_preselection_{run_date or '*'}.csv"
    candidates = sorted((MF_DIR / "extracted").glob(pattern), reverse=True)
    if not candidates:
        sys.exit(f"[midcap] No preselection CSV found in {MF_DIR}/extracted/ for pattern {pattern}")
    return candidates[0]


def _load_rows(csv_path: Path) -> list[dict]:
    text = csv_path.read_text(encoding="utf-8")
    rows = list(csv.DictReader(text.splitlines()))
    return [r for r in rows if r.get("symbol")]


def _gate_chip(val: str) -> str:
    """Return pass/watch/fail flag from gate column value."""
    v = str(val).strip().upper()
    if v == "PASS":
        return "pass"
    if v in ("WATCH", "WARN"):
        return "watch"
    return "fail"


def _bucket_class(bucket: str) -> str:
    b = bucket.upper()
    if "CORE" in b:
        return "core"
    if "WATCH" in b or "PREPARE" in b:
        return "watch"
    return "refresh"


def _signal_class(sig: str) -> str:
    s = sig.upper()
    if s in ("BUY", "STRONG_BUY"):
        return "buy"
    if s in ("SELL", "STRONG_SELL"):
        return "sell"
    return "hold"


def build_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        score = _f(r.get("overall_score_100"))
        tech_s = _f(r.get("technical_score"))
        rsi = _f(r.get("rsi"))
        rs = _f(r.get("relative_strength"))
        price = _f(r.get("latest_price"))
        sma50 = _f(r.get("sma50"))
        sma200 = _f(r.get("sma200"))
        dist_52h = _f(r.get("distance_52w_high_pct"))
        ret_6m = _f(r.get("six_month_return_pct"))
        ret_1y = _f(r.get("one_year_return_pct"))
        fund_score = _f(r.get("enhanced_fund_score"))
        tech_comp = _f(r.get("technical_component_30"))
        fund_comp = _f(r.get("fundamental_component_35"))
        theme_comp = _f(r.get("theme_component_20"))

        bucket = r.get("decision_bucket", "").strip()
        stage = r.get("stage", "").strip()
        trading_signal = r.get("trading_signal", "HOLD").strip()
        gov_theme = r.get("government_investment_theme", "").strip()
        sector_theme = r.get("sector_theme", "").strip()
        blockers_raw = r.get("blockers", "").strip()
        blockers = [b.strip() for b in blockers_raw.split(";") if b.strip() and b.strip() != "FUNDAMENTAL_REFRESH_REQUIRED"]

        out.append({
            "sym": r.get("symbol", "").strip(),
            "company": r.get("company", "").strip(),
            "sector": r.get("sector", "").strip(),
            "gov_theme": gov_theme,
            "sector_theme": sector_theme,
            "score": round(score, 1),
            "tech_comp": round(tech_comp, 1),
            "fund_comp": round(fund_comp, 1),
            "theme_comp": round(theme_comp, 1),
            "fund_score": round(fund_score, 1),
            "tech_score": round(tech_s, 1),
            "bucket": bucket,
            "bucket_cls": _bucket_class(bucket),
            "stage": stage,
            "g_stage2": _gate_chip(r.get("stage2_gate", "")),
            "g_growth": _gate_chip(r.get("growth_gate", "")),
            "g_eps": _gate_chip(r.get("high_eps_gate", "")),
            "g_yoy": _gate_chip(r.get("yoy_sales_gate", "")),
            "g_gov": _gate_chip(r.get("government_investment_gate", "")),
            "rsi": round(rsi, 1),
            "rs": round(rs, 2),
            "price": price,
            "sma50": round(sma50, 2),
            "sma200": round(sma200, 2),
            "vs_sma50": round((price / sma50 - 1) * 100, 1) if sma50 else 0,
            "vs_sma200": round((price / sma200 - 1) * 100, 1) if sma200 else 0,
            "dist_52h": round(dist_52h, 1),
            "ret_6m": round(ret_6m, 1),
            "ret_1y": round(ret_1y, 1),
            "signal": trading_signal,
            "signal_cls": _signal_class(trading_signal),
            "blockers": blockers,
            "fund_refresh": "FUNDAMENTAL_REFRESH_REQUIRED" in blockers_raw,
        })
    return out


def _summary(rows_built: list[dict]) -> dict:
    total = len(rows_built)
    core = sum(1 for r in rows_built if r["bucket_cls"] == "core")
    watch = sum(1 for r in rows_built if r["bucket_cls"] == "watch")
    stage2 = sum(1 for r in rows_built if "STAGE_2" in r["stage"].upper())
    buy_sig = sum(1 for r in rows_built if r["signal_cls"] == "buy")
    avg_score = round(sum(r["score"] for r in rows_built) / total, 1) if total else 0
    return {"total": total, "core": core, "watch": watch, "stage2": stage2,
            "buy_sig": buy_sig, "avg_score": avg_score}


# ── HTML template ─────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Midcap Leaders Dashboard</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Inter:wght@400;500;600;700&display=swap">
<style>
:root {
  --bg:       #0d1117;
  --surface:  #161b22;
  --surface2: #21262d;
  --border:   #30363d;
  --accent:   #388bfd;
  --green:    #3fb950;
  --red:      #f85149;
  --yellow:   #d29922;
  --amber:    #e3b341;
  --text:     #e6edf3;
  --muted:    #8b949e;
  --mono:     'JetBrains Mono', monospace;
  --sans:     'Inter', system-ui, sans-serif;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { font-size: 14px; }
body { font-family: var(--sans); background: var(--bg); color: var(--text); min-height: 100vh; }

/* ── header ── */
.hdr { background: var(--surface); border-bottom: 1px solid var(--border); padding: 20px 28px; display: flex; align-items: center; gap: 16px; }
.hdr-logo { font-family: var(--mono); font-weight: 600; font-size: 18px; color: var(--accent); letter-spacing: -0.5px; }
.hdr-logo span { color: var(--muted); font-weight: 400; font-size: 13px; margin-left: 8px; }
.hdr-right { margin-left: auto; font-family: var(--mono); font-size: 12px; color: var(--muted); text-align: right; }

/* ── metrics bar ── */
.metrics { display: flex; gap: 12px; padding: 20px 28px; flex-wrap: wrap; }
.metric { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 14px 18px; min-width: 130px; flex: 1; }
.metric .label { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin-bottom: 6px; }
.metric .val { font-family: var(--mono); font-size: 26px; font-weight: 600; color: var(--text); }
.metric .val.green { color: var(--green); }
.metric .val.yellow { color: var(--yellow); }
.metric .val.blue { color: var(--accent); }

/* ── filter tabs ── */
.tabs { display: flex; gap: 6px; padding: 0 28px 16px; flex-wrap: wrap; }
.tab { background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 6px 14px; font-size: 12px; font-weight: 500; color: var(--muted); cursor: pointer; transition: all .15s; }
.tab:hover { border-color: var(--accent); color: var(--accent); }
.tab.active { background: var(--accent); border-color: var(--accent); color: #fff; }

/* ── theme pills ── */
.theme-row { display: flex; gap: 8px; padding: 0 28px 20px; flex-wrap: wrap; }
.theme-pill { background: var(--surface2); border: 1px solid var(--border); border-radius: 20px; padding: 4px 12px; font-size: 11px; color: var(--muted); }
.theme-pill strong { color: var(--text); }

/* ── table wrap ── */
.tbl-wrap { padding: 0 28px 28px; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; font-size: 12.5px; min-width: 900px; }
thead th { background: var(--surface2); color: var(--muted); font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; padding: 10px 10px; border-bottom: 1px solid var(--border); text-align: left; }
tbody tr { border-bottom: 1px solid var(--border); transition: background .1s; }
tbody tr:last-child { border-bottom: none; }
tbody tr:hover { background: var(--surface2); }
td { padding: 9px 10px; vertical-align: middle; }
.sym-cell { font-family: var(--mono); font-weight: 600; font-size: 13px; color: var(--accent); white-space: nowrap; }
.sym-cell .company { display: block; font-family: var(--sans); font-weight: 400; font-size: 11px; color: var(--muted); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 160px; }
.sym-links { display: flex; gap: 6px; margin-top: 4px; }
.sym-links a { font-size: 10px; color: var(--muted); text-decoration: none; padding: 1px 5px; border: 1px solid var(--border); border-radius: 3px; transition: color .15s, border-color .15s; }
.sym-links a:hover { color: var(--accent); border-color: var(--accent); }

/* ── score bar ── */
.score-cell { min-width: 90px; }
.score-val { font-family: var(--mono); font-size: 14px; font-weight: 600; }
.score-bar { height: 4px; border-radius: 2px; margin-top: 4px; background: var(--border); overflow: hidden; }
.score-fill { height: 100%; border-radius: 2px; }
.score-fill.high { background: var(--green); }
.score-fill.mid  { background: var(--yellow); }
.score-fill.low  { background: var(--red); }

/* ── chips ── */
.chip { display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; letter-spacing: .02em; white-space: nowrap; }
.chip.core    { background: rgba(63,185,80,.15); color: var(--green); border: 1px solid rgba(63,185,80,.3); }
.chip.watch   { background: rgba(210,153,34,.15); color: var(--yellow); border: 1px solid rgba(210,153,34,.3); }
.chip.refresh { background: rgba(248,81,73,.12); color: var(--red); border: 1px solid rgba(248,81,73,.25); }
.chip.stage2  { background: rgba(56,139,253,.15); color: var(--accent); border: 1px solid rgba(56,139,253,.3); }
.chip.stage1  { background: rgba(139,148,158,.12); color: var(--muted); border: 1px solid rgba(139,148,158,.2); }
.chip.buy     { background: rgba(63,185,80,.15); color: var(--green); border: 1px solid rgba(63,185,80,.3); }
.chip.sell    { background: rgba(248,81,73,.12); color: var(--red); border: 1px solid rgba(248,81,73,.25); }
.chip.hold    { background: rgba(139,148,158,.12); color: var(--muted); border: 1px solid rgba(139,148,158,.2); }

/* ── gate dots ── */
.gates { display: flex; gap: 5px; flex-wrap: wrap; }
.gate { width: 22px; height: 22px; border-radius: 4px; display: flex; align-items: center; justify-content: center; font-size: 9px; font-weight: 700; }
.gate.pass  { background: rgba(63,185,80,.2);  color: var(--green); }
.gate.watch { background: rgba(210,153,34,.2); color: var(--yellow); }
.gate.fail  { background: rgba(248,81,73,.15); color: var(--red); }

/* ── mono numbers ── */
.mono { font-family: var(--mono); }
.pos { color: var(--green); }
.neg { color: var(--red); }

/* ── refresh badge ── */
.refresh-badge { font-size: 9px; color: var(--amber); margin-top: 3px; }

/* ── section label ── */
.section-label { padding: 4px 28px 10px; font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .07em; }

/* ── disclaimer ── */
.disclaimer { margin: 0 28px 40px; background: var(--surface); border: 1px solid var(--border); border-left: 3px solid var(--yellow); border-radius: 8px; padding: 18px 20px; }
.disclaimer h4 { font-size: 12px; text-transform: uppercase; letter-spacing: .07em; color: var(--yellow); margin-bottom: 10px; }
.disclaimer p { font-size: 11.5px; color: var(--muted); line-height: 1.7; margin-bottom: 8px; }
.disclaimer p:last-child { margin-bottom: 0; }

@media (max-width: 700px) {
  .hdr, .metrics, .tabs, .theme-row, .tbl-wrap, .section-label, .disclaimer { padding-left: 16px; padding-right: 16px; }
  .metrics { gap: 8px; }
  .metric { min-width: 100px; }
}
</style>
</head>
<body>

<header class="hdr">
  <div class="hdr-logo">Agent Adda<span>Midcap Leaders · Research Dashboard</span></div>
  <div class="hdr-right">
    Run date: $DATE_LABEL<br>
    <span style="color:var(--red);font-size:11px;">Research only — not investment advice</span>
  </div>
</header>

<div class="metrics" id="metrics"></div>

<div class="tabs" id="tabs">
  <button class="tab active" data-filter="all">All</button>
  <button class="tab" data-filter="core">Core Candidates</button>
  <button class="tab" data-filter="watch">Watch / Prepare</button>
  <button class="tab" data-filter="stage2">Stage 2 Only</button>
  <button class="tab" data-filter="buy">Buy Signal</button>
</div>

<div class="section-label">Sector / Government Theme Distribution</div>
<div class="theme-row" id="theme-row"></div>

<div class="tbl-wrap">
  <table>
    <thead>
      <tr>
        <th>Symbol</th>
        <th>Score</th>
        <th>Bucket</th>
        <th>Stage</th>
        <th title="Stage2 | Growth | EPS | YoY Sales | Gov Theme">Gates S·G·E·Y·V</th>
        <th>RSI / RS</th>
        <th>Price</th>
        <th>vs SMA50 / 200</th>
        <th>52w High</th>
        <th>6m / 1y Ret</th>
        <th>Signal</th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
</div>

<div class="disclaimer">
  <h4>⚠ SEBI Research Analyst Disclaimer</h4>
  <p>This report is generated by Agent Adda, an automated rules-based research and analysis tool. It is intended purely for educational and informational purposes. It does not constitute investment advice, a recommendation, solicitation, or offer to buy or sell any security. The analysis is based on publicly available data and algorithmic scoring models.</p>
  <p>Agent Adda is not registered as a Research Analyst under SEBI (Research Analysts) Regulations, 2014, nor as an Investment Adviser under SEBI (Investment Advisers) Regulations, 2013. Nothing in this report should be construed as personalised investment advice. Past performance of any stock, sector, or strategy mentioned herein is not indicative of future results.</p>
  <p>All fundamental data is sourced from official exchange filings, Screener.in, and yfinance. Fundamental refresh is marked as required where the local cache is stale. Do not act on any screening output until you have independently verified current financial disclosures directly from the company's investor-relations page, NSE/BSE exchange filings, and the Ministry of Corporate Affairs. Perform your own due diligence before making any financial decision.</p>
  <p>Investors should consult a SEBI-registered Investment Adviser and consider their individual risk appetite, investment horizon, and financial situation before acting on any information in this report.</p>
</div>

<script>
const DATA = $DATA_JSON;
const SUMMARY = $SUMMARY_JSON;

// ── metrics ──────────────────────────────────────────────────────────────────
(function buildMetrics() {
  const m = document.getElementById('metrics');
  const items = [
    { label: 'Symbols Scored', val: SUMMARY.total, cls: '' },
    { label: 'Core Candidates', val: SUMMARY.core, cls: 'green' },
    { label: 'Watch / Prepare', val: SUMMARY.watch, cls: 'yellow' },
    { label: 'Stage 2', val: SUMMARY.stage2, cls: 'blue' },
    { label: 'Buy Signal', val: SUMMARY.buy_sig, cls: 'green' },
    { label: 'Avg Score', val: SUMMARY.avg_score, cls: '' },
  ];
  m.innerHTML = items.map(i =>
    `<div class="metric"><div class="label">${i.label}</div><div class="val ${i.cls}">${i.val}</div></div>`
  ).join('');
})();

// ── theme pills ───────────────────────────────────────────────────────────────
(function buildThemes() {
  const counts = {};
  DATA.forEach(r => {
    const t = r.gov_theme || r.sector_theme || 'Other';
    counts[t] = (counts[t] || 0) + 1;
  });
  const sorted = Object.entries(counts).sort((a,b) => b[1]-a[1]);
  document.getElementById('theme-row').innerHTML = sorted.map(([t,n]) =>
    `<div class="theme-pill"><strong>${n}</strong> ${t}</div>`
  ).join('');
})();

// ── table ─────────────────────────────────────────────────────────────────────
function scoreColor(s) { return s >= 75 ? 'high' : s >= 60 ? 'mid' : 'low'; }
function stageChip(stage) {
  const s = (stage||'').toUpperCase();
  const cls = s.includes('2') ? 'stage2' : 'stage1';
  return `<span class="chip ${cls}">${stage || 'N/A'}</span>`;
}
function gateBox(g, title) {
  const icon = g==='pass' ? '✓' : g==='watch' ? '~' : '✕';
  return `<div class="gate ${g}" title="${title}">${icon}</div>`;
}
function retClass(v) { return v > 0 ? 'pos' : v < 0 ? 'neg' : ''; }
function pct(v) { const sign = v>=0?'+':''; return sign+v+'%'; }

function buildRow(d) {
  const tv = `https://in.tradingview.com/chart/?symbol=NSE%3A${d.sym}`;
  const sc = `https://www.screener.in/company/${d.sym}/`;
  const scoreVal = d.score;
  const fillClass = scoreColor(scoreVal);
  const bucketLabel = d.bucket || '—';
  const vs50Cls = d.vs_sma50 >= 0 ? 'pos' : 'neg';
  const vs200Cls = d.vs_sma200 >= 0 ? 'pos' : 'neg';
  return `<tr data-bucket="${d.bucket_cls}" data-stage="${d.stage.toLowerCase()}" data-signal="${d.signal_cls}">
    <td class="sym-cell">
      ${d.sym}
      <span class="company">${d.company}</span>
      <div class="sym-links">
        <a href="${tv}" target="_blank" rel="noopener">TV</a>
        <a href="${sc}" target="_blank" rel="noopener">SCR</a>
      </div>
    </td>
    <td class="score-cell">
      <span class="score-val mono">${scoreVal}</span>
      <div class="score-bar"><div class="score-fill ${fillClass}" style="width:${scoreVal}%"></div></div>
      ${d.fund_refresh ? '<div class="refresh-badge">⟳ Fundamental refresh reqd</div>' : ''}
    </td>
    <td><span class="chip ${d.bucket_cls}">${bucketLabel}</span></td>
    <td>${stageChip(d.stage)}</td>
    <td>
      <div class="gates">
        ${gateBox(d.g_stage2,'Stage 2')}
        ${gateBox(d.g_growth,'Growth')}
        ${gateBox(d.g_eps,'High EPS')}
        ${gateBox(d.g_yoy,'YoY Sales')}
        ${gateBox(d.g_gov,'Gov Theme')}
      </div>
    </td>
    <td class="mono"><span style="color:var(--amber)">${d.rsi}</span> <span style="color:var(--muted);font-size:10px">RSI</span><br><span style="color:var(--accent)">${d.rs}</span> <span style="color:var(--muted);font-size:10px">RS</span></td>
    <td class="mono">₹${d.price.toLocaleString('en-IN')}</td>
    <td class="mono">
      <span class="${vs50Cls}">${pct(d.vs_sma50)}</span> <span style="color:var(--muted);font-size:10px">50d</span><br>
      <span class="${vs200Cls}">${pct(d.vs_sma200)}</span> <span style="color:var(--muted);font-size:10px">200d</span>
    </td>
    <td class="mono ${retClass(d.dist_52h)}">${pct(d.dist_52h)}</td>
    <td class="mono">
      <span class="${retClass(d.ret_6m)}">${pct(d.ret_6m)}</span><br>
      <span class="${retClass(d.ret_1y)}">${pct(d.ret_1y)}</span>
    </td>
    <td><span class="chip ${d.signal_cls}">${d.signal}</span></td>
  </tr>`;
}

let currentFilter = 'all';
function renderTable() {
  const tbody = document.getElementById('tbody');
  const filtered = DATA.filter(d => {
    if (currentFilter === 'all') return true;
    if (currentFilter === 'core') return d.bucket_cls === 'core';
    if (currentFilter === 'watch') return d.bucket_cls === 'watch';
    if (currentFilter === 'stage2') return d.stage.toUpperCase().includes('2');
    if (currentFilter === 'buy') return d.signal_cls === 'buy';
    return true;
  });
  tbody.innerHTML = filtered.length ? filtered.map(buildRow).join('') :
    `<tr><td colspan="11" style="text-align:center;color:var(--muted);padding:20px">No rows match this filter</td></tr>`;
}
renderTable();

// ── tab filter ────────────────────────────────────────────────────────────────
document.getElementById('tabs').addEventListener('click', e => {
  const btn = e.target.closest('.tab');
  if (!btn) return;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  currentFilter = btn.dataset.filter;
  renderTable();
});
</script>
</body>
</html>
"""


# ── main ──────────────────────────────────────────────────────────────────────

def render(run_date: str | None = None, no_open: bool = False) -> Path:
    csv_path = _latest_csv(run_date)
    date_str = csv_path.stem.split("_")[-1]          # YYYYMMDD
    date_label = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

    raw_rows = _load_rows(csv_path)
    built = build_rows(raw_rows)
    summary = _summary(built)

    html = Template(HTML_TEMPLATE).safe_substitute(
        DATE_LABEL=date_label,
        DATA_JSON=json.dumps(built, indent=2),
        SUMMARY_JSON=json.dumps(summary),
    )

    # output paths
    REPORTS_LATEST.mkdir(parents=True, exist_ok=True)
    out_latest = REPORTS_LATEST / "midcap_fund_dashboard.html"
    out_latest.write_text(html, encoding="utf-8")

    year = date_str[:4]
    archive_dir = REPORTS_ARCHIVE / year
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"Midcap_Leaders_{date_str}.html"
    shutil.copy2(out_latest, archive_path)

    print(f"[midcap] Rendered {len(built)} rows → {out_latest.relative_to(ROOT)}")
    print(f"[midcap] Archive  → {archive_path.relative_to(ROOT)}")
    print(f"[midcap] Summary  → core={summary['core']} watch={summary['watch']} stage2={summary['stage2']} buy={summary['buy_sig']}")

    if not no_open:
        try:
            subprocess.Popen(["open", str(out_latest)])
        except Exception:
            pass

    return out_latest


def _cli(argv=None):
    p = argparse.ArgumentParser(description="Generate Agent Adda Midcap Leaders themed HTML dashboard")
    p.add_argument("--run-date", default=None, help="YYYYMMDD date suffix to select CSV (default: latest)")
    p.add_argument("--no-open", action="store_true", help="Don't open browser after render")
    args = p.parse_args(argv)
    render(run_date=args.run_date, no_open=args.no_open)


if __name__ == "__main__":
    _cli()
