"""
Agent Adda — Smallcap Research Fund Dashboard (themed renderer)
==============================================================
Reads the smallcap research-update + market-check CSVs and renders a
self-contained dark-terminal HTML matching the Agent Adda visual identity.

Two tabs:
  Tab 1 — Research Update  (policy score, readiness, financials, trigger)
  Tab 2 — Market Check     (live price, shadow P&L, setup levels)

Output:
  reports/latest/smallcap_fund_dashboard.html
  reports/fund/{YEAR}/Smallcap_Research_{YYYYMMDD}.html

Usage:
  python scripts/generate_smallcap_fund_report.py
  python scripts/generate_smallcap_fund_report.py --run-date 20260824
  python scripts/generate_smallcap_fund_report.py --no-open
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
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


def _latest_csv(pattern: str) -> Path | None:
    candidates = sorted((MF_DIR / "extracted").glob(pattern), reverse=True)
    return candidates[0] if candidates else None


def _load_csv(path: Path) -> list[dict]:
    if path is None or not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return [r for r in csv.DictReader(text.splitlines()) if r.get("symbol")]


# ── research rows ─────────────────────────────────────────────────────────────

def _readiness_tags(notes: str) -> list[dict]:
    """Parse '+stage2; -rs_low' style notes into green/red tag dicts."""
    tags = []
    for part in notes.split(";"):
        part = part.strip()
        if not part:
            continue
        sign = part[0] if part[0] in "+-" else "+"
        label = part[1:].strip().replace("_", " ")
        tags.append({"ok": sign == "+", "label": label})
    return tags


def build_research_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        policy_score = _f(r.get("policy_score_100"))
        readiness = _f(r.get("readiness_overlay_100"))
        rsi = _f(r.get("rsi"))
        rs = _f(r.get("relative_strength"))
        price = _f(r.get("latest_price"))
        pct_chg = _f(r.get("latest_pct_change"))
        rev = _f(r.get("annual_revenue_cr"))
        pat = _f(r.get("annual_pat_cr"))
        rev_yoy = _f(r.get("annual_revenue_yoy_pct"))
        pat_yoy = _f(r.get("annual_pat_yoy_pct"))
        d_e = _f(r.get("debt_to_equity"))
        ocf = _f(r.get("operating_cash_flow_cr"))
        paper_val = _f(r.get("paper_position_value"))
        risk = _f(r.get("paper_risk_to_stop"))
        stop = _f(r.get("initial_stop"))
        target = _f(r.get("target_2r"))

        blockers_raw = r.get("blockers", "") or ""
        blockers = [b.strip() for b in blockers_raw.split(";") if b.strip()]

        notes_raw = r.get("readiness_notes", "") or ""
        tags = _readiness_tags(notes_raw)

        stage_sig = r.get("local_stage_signal", "").strip()
        supertrend = r.get("supertrend_state", "").strip()
        trigger = r.get("trigger_state", "").strip()
        action = r.get("action_bucket", "").strip()
        rating = r.get("policy_rating", "").strip()
        phase1 = r.get("phase1_status", "").strip()
        qtr = r.get("latest_quarter", "").strip()
        freshness = r.get("financial_freshness", "").strip()
        result_status = r.get("result_status", "").strip()

        out.append({
            "sym": r.get("symbol", "").strip(),
            "company": r.get("company", "").strip(),
            "sector": r.get("sector", "").strip(),
            "policy_score": round(policy_score, 1),
            "readiness": round(readiness, 1),
            "rating": rating,
            "phase1": phase1,
            "stage_sig": stage_sig,
            "supertrend": supertrend,
            "rsi": round(rsi, 1),
            "rs": round(rs, 2),
            "price": price,
            "pct_chg": round(pct_chg, 2),
            "stop": stop,
            "target": target,
            "paper_val": round(paper_val, 1),
            "risk": round(risk, 1),
            "rev_cr": rev,
            "pat_cr": pat,
            "rev_yoy": round(rev_yoy, 1),
            "pat_yoy": round(pat_yoy, 1),
            "d_e": round(d_e, 2),
            "ocf_cr": ocf,
            "qtr": qtr,
            "freshness": freshness,
            "result_status": result_status,
            "trigger": trigger,
            "action": action,
            "tags": tags,
            "blockers": blockers,
        })
    return out


# ── market-check rows ─────────────────────────────────────────────────────────

def build_market_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        pol = _f(r.get("policy_score_100"))
        ref_price = _f(r.get("reference_price"))
        latest = _f(r.get("latest_price"))
        pct_chg = _f(r.get("latest_pct_change"))
        move_vs_ref = _f(r.get("move_vs_reference_pct"))
        breakout = _f(r.get("breakout_level"))
        retest = _f(r.get("retest_level"))
        stop = _f(r.get("stop_price"))
        target = _f(r.get("target_2r_price"))
        d_breakout = _f(r.get("distance_to_breakout_pct"))
        d_retest = _f(r.get("distance_above_retest_pct"))
        d_stop = _f(r.get("distance_above_stop_pct"))
        paper_ref = _f(r.get("paper_position_value_reference"))
        paper_lat = _f(r.get("paper_position_value_latest"))
        shadow_pnl = _f(r.get("shadow_pnl"))
        shadow_pnl_pct = _f(r.get("shadow_pnl_pct_nav"))
        risk = _f(r.get("paper_risk_to_stop"))
        qty = _f(r.get("paper_quantity_by_policy"))

        rr = round((target - latest) / (latest - stop), 2) if (latest - stop) > 0 else None

        out.append({
            "sym": r.get("symbol", "").strip(),
            "company": r.get("company", "").strip(),
            "bucket": r.get("bucket", "").strip(),
            "theme_lens": r.get("theme_lens", "").strip(),
            "policy_score": round(pol, 1),
            "rating": r.get("policy_rating", "").strip(),
            "ref_price": ref_price,
            "latest": latest,
            "pct_chg": round(pct_chg, 2),
            "move_vs_ref": round(move_vs_ref, 2),
            "breakout": breakout,
            "retest": retest,
            "stop": stop,
            "target": target,
            "d_breakout": round(d_breakout, 1),
            "d_retest": round(d_retest, 1),
            "d_stop": round(d_stop, 1),
            "paper_ref": round(paper_ref, 1),
            "paper_lat": round(paper_lat, 1),
            "shadow_pnl": round(shadow_pnl, 1),
            "shadow_pnl_pct": round(shadow_pnl_pct * 100, 3),
            "risk": round(risk, 1),
            "qty": int(qty),
            "rr": rr,
            "trigger": r.get("trigger_state", "").strip(),
            "trigger_note": r.get("trigger_note", "").strip(),
            "blockers": r.get("evidence_blockers", "").strip(),
            "next_action": r.get("next_action", "").strip(),
        })
    return out


# ── summaries ─────────────────────────────────────────────────────────────────

def _research_summary(rows: list[dict]) -> dict:
    total = len(rows)
    core = sum(1 for r in rows if "core" in r["rating"].lower())
    wait = sum(1 for r in rows if r["trigger"] == "WAIT")
    avg_pol = round(sum(r["policy_score"] for r in rows) / total, 1) if total else 0
    avg_ready = round(sum(r["readiness"] for r in rows) / total, 1) if total else 0
    return {"total": total, "core": core, "wait": wait, "avg_pol": avg_pol, "avg_ready": avg_ready}


def _market_summary(rows: list[dict]) -> dict:
    total = len(rows)
    total_paper = round(sum(r["paper_lat"] for r in rows), 1)
    total_pnl = round(sum(r["shadow_pnl"] for r in rows), 1)
    clean_map = sum(1 for r in rows if "Clean" in r["bucket"])
    retest_map = sum(1 for r in rows if "Retest" in r["bucket"])
    pnl_cls = "green" if total_pnl >= 0 else "red"
    return {"total": total, "total_paper": total_paper, "total_pnl": total_pnl,
            "pnl_cls": pnl_cls, "clean_map": clean_map, "retest_map": retest_map}


# ── HTML template ─────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Smallcap Research Dashboard</title>
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

.hdr { background: var(--surface); border-bottom: 1px solid var(--border); padding: 20px 28px; display: flex; align-items: center; gap: 16px; }
.hdr-logo { font-family: var(--mono); font-weight: 600; font-size: 18px; color: var(--accent); }
.hdr-logo span { color: var(--muted); font-weight: 400; font-size: 13px; margin-left: 8px; }
.hdr-right { margin-left: auto; font-family: var(--mono); font-size: 12px; color: var(--muted); text-align: right; }

.metrics { display: flex; gap: 12px; padding: 20px 28px; flex-wrap: wrap; }
.metric { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 14px 18px; min-width: 130px; flex: 1; }
.metric .label { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin-bottom: 6px; }
.metric .val { font-family: var(--mono); font-size: 24px; font-weight: 600; }
.metric .val.green { color: var(--green); }
.metric .val.yellow { color: var(--yellow); }
.metric .val.red { color: var(--red); }
.metric .val.blue { color: var(--accent); }

/* ── tab nav ── */
.tab-nav { display: flex; gap: 0; border-bottom: 1px solid var(--border); margin: 0 28px; }
.tab-nav-btn { background: none; border: none; border-bottom: 2px solid transparent; padding: 10px 18px; font-family: var(--sans); font-size: 13px; font-weight: 500; color: var(--muted); cursor: pointer; transition: all .15s; }
.tab-nav-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
.tab-pane { display: none; }
.tab-pane.active { display: block; }

.tbl-wrap { padding: 20px 28px; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; font-size: 12.5px; min-width: 860px; }
thead th { background: var(--surface2); color: var(--muted); font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; padding: 10px; border-bottom: 1px solid var(--border); text-align: left; }
tbody tr { border-bottom: 1px solid var(--border); }
tbody tr:last-child { border-bottom: none; }
tbody tr:hover { background: var(--surface2); }
td { padding: 9px 10px; vertical-align: middle; }

.sym-cell { font-family: var(--mono); font-weight: 600; font-size: 13px; color: var(--accent); }
.sym-cell .co { display: block; font-family: var(--sans); font-weight: 400; font-size: 11px; color: var(--muted); margin-top: 2px; }
.sym-links { display: flex; gap: 5px; margin-top: 4px; }
.sym-links a { font-size: 10px; color: var(--muted); text-decoration: none; padding: 1px 5px; border: 1px solid var(--border); border-radius: 3px; }
.sym-links a:hover { color: var(--accent); border-color: var(--accent); }

.score-bar { height: 4px; border-radius: 2px; background: var(--border); overflow: hidden; margin-top: 4px; }
.score-fill { height: 100%; border-radius: 2px; }
.score-fill.high { background: var(--green); }
.score-fill.mid  { background: var(--yellow); }
.score-fill.low  { background: var(--red); }

.chip { display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; white-space: nowrap; }
.chip.core      { background: rgba(63,185,80,.15); color: var(--green);  border: 1px solid rgba(63,185,80,.3); }
.chip.watch     { background: rgba(210,153,34,.15);color: var(--yellow); border: 1px solid rgba(210,153,34,.3); }
.chip.blocked   { background: rgba(248,81,73,.12); color: var(--red);    border: 1px solid rgba(248,81,73,.25); }
.chip.neutral   { background: rgba(139,148,158,.12);color: var(--muted); border: 1px solid rgba(139,148,158,.2); }
.chip.bullish   { background: rgba(63,185,80,.15); color: var(--green);  border: 1px solid rgba(63,185,80,.3); }
.chip.bearish   { background: rgba(248,81,73,.12); color: var(--red);    border: 1px solid rgba(248,81,73,.25); }
.chip.stage2    { background: rgba(56,139,253,.15);color: var(--accent); border: 1px solid rgba(56,139,253,.3); }

.tags { display: flex; gap: 4px; flex-wrap: wrap; }
.tag { font-size: 10px; padding: 2px 6px; border-radius: 4px; }
.tag.ok  { background: rgba(63,185,80,.12);  color: var(--green); }
.tag.bad { background: rgba(248,81,73,.10);  color: var(--red); }

.mono { font-family: var(--mono); }
.pos  { color: var(--green); }
.neg  { color: var(--red); }
.mut  { color: var(--muted); }

.trigger-badge { font-size: 10px; font-family: var(--mono); color: var(--amber); }

/* shadow P&L cell */
.pnl-cell { font-family: var(--mono); }
.pnl-cell .main { font-size: 14px; font-weight: 600; }
.pnl-cell .sub  { font-size: 10px; color: var(--muted); }

/* setup levels mini-table */
.levels { display: grid; grid-template-columns: 1fr 1fr; gap: 2px 8px; }
.levels .lbl { font-size: 10px; color: var(--muted); }
.levels .lvl { font-family: var(--mono); font-size: 11px; }

/* disclaimer */
.disclaimer { margin: 0 28px 40px; background: var(--surface); border: 1px solid var(--border); border-left: 3px solid var(--yellow); border-radius: 8px; padding: 18px 20px; }
.disclaimer h4 { font-size: 12px; text-transform: uppercase; letter-spacing: .07em; color: var(--yellow); margin-bottom: 10px; }
.disclaimer p { font-size: 11.5px; color: var(--muted); line-height: 1.7; margin-bottom: 8px; }
.disclaimer p:last-child { margin-bottom: 0; }

@media (max-width: 700px) {
  .hdr, .metrics, .tab-nav, .tbl-wrap, .disclaimer { padding-left: 16px; padding-right: 16px; }
  .tab-nav { margin: 0 16px; }
}
</style>
</head>
<body>

<header class="hdr">
  <div class="hdr-logo">Agent Adda<span>Smallcap Research · Fund Dashboard</span></div>
  <div class="hdr-right">Run date: $DATE_LABEL<br><span style="color:var(--red);font-size:11px;">Research only — not investment advice</span></div>
</header>

<div class="metrics" id="metrics"></div>

<div class="tab-nav">
  <button class="tab-nav-btn active" data-tab="research">Research Update</button>
  <button class="tab-nav-btn" data-tab="market">Market Check</button>
</div>

<!-- ── TAB 1: Research Update ── -->
<div class="tab-pane active" id="tab-research">
  <div class="tbl-wrap">
    <table>
      <thead>
        <tr>
          <th>Symbol</th>
          <th>Policy / Readiness</th>
          <th>Rating</th>
          <th>Stage / Trend</th>
          <th>RSI / RS</th>
          <th>Price</th>
          <th>Readiness Signals</th>
          <th>Financials (annual)</th>
          <th>Quarter</th>
          <th>Trigger / Action</th>
        </tr>
      </thead>
      <tbody id="tbody-research"></tbody>
    </table>
  </div>
</div>

<!-- ── TAB 2: Market Check ── -->
<div class="tab-pane" id="tab-market">
  <div class="tbl-wrap">
    <table>
      <thead>
        <tr>
          <th>Symbol</th>
          <th>Bucket / Theme</th>
          <th>Policy</th>
          <th>Price / Δ</th>
          <th>Shadow P&amp;L</th>
          <th>Setup Levels</th>
          <th>Distances</th>
          <th>R:R</th>
          <th>Trigger State</th>
          <th>Next Action</th>
        </tr>
      </thead>
      <tbody id="tbody-market"></tbody>
    </table>
  </div>
</div>

<div class="disclaimer">
  <h4>⚠ SEBI Research Analyst Disclaimer</h4>
  <p>This report is generated by Agent Adda, an automated rules-based research and analysis tool. It is intended purely for educational and informational purposes. It does not constitute investment advice, a recommendation, solicitation, or offer to buy or sell any security. The analysis is based on publicly available data and algorithmic scoring models.</p>
  <p>Agent Adda is not registered as a Research Analyst under SEBI (Research Analysts) Regulations, 2014, nor as an Investment Adviser under SEBI (Investment Advisers) Regulations, 2013. Nothing in this report should be construed as personalised investment advice. Past performance of any stock, sector, or strategy mentioned herein is not indicative of future results.</p>
  <p>All fundamental data is sourced from official exchange filings, Screener.in, and yfinance. Fundamental refresh is mandatory before any paper order. Do not act on any screening output until you have independently verified current financial disclosures directly from the company's investor-relations page, NSE/BSE exchange filings, and the Ministry of Corporate Affairs.</p>
  <p>Investors should consult a SEBI-registered Investment Adviser and consider their individual risk appetite, investment horizon, and financial situation before acting on any information in this report.</p>
</div>

<script>
const RESEARCH = $RESEARCH_JSON;
const MARKET   = $MARKET_JSON;
const R_SUM    = $R_SUMMARY_JSON;
const M_SUM    = $M_SUMMARY_JSON;

// ── metrics (combines both datasets) ─────────────────────────────────────────
(function() {
  const m = document.getElementById('metrics');
  const items = [
    { label: 'Research Symbols', val: R_SUM.total, cls: '' },
    { label: 'Core Candidates',  val: R_SUM.core,  cls: 'green' },
    { label: 'Waiting (WAIT)',   val: R_SUM.wait,  cls: 'yellow' },
    { label: 'Avg Policy Score', val: R_SUM.avg_pol, cls: '' },
    { label: 'Paper Portfolio',  val: '₹'+M_SUM.total_paper.toLocaleString('en-IN'), cls: '' },
    { label: 'Shadow P&L',       val: (M_SUM.total_pnl >= 0 ? '+' : '') + '₹'+M_SUM.total_pnl.toLocaleString('en-IN'), cls: M_SUM.pnl_cls },
  ];
  m.innerHTML = items.map(i =>
    `<div class="metric"><div class="label">${i.label}</div><div class="val ${i.cls}">${i.val}</div></div>`
  ).join('');
})();

// ── tab nav ───────────────────────────────────────────────────────────────────
document.querySelector('.tab-nav').addEventListener('click', e => {
  const btn = e.target.closest('.tab-nav-btn');
  if (!btn) return;
  document.querySelectorAll('.tab-nav-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
});

// ── helpers ───────────────────────────────────────────────────────────────────
function sym(s, co) {
  const tv = `https://in.tradingview.com/chart/?symbol=NSE%3A${s}`;
  const sc = `https://www.screener.in/company/${s}/`;
  return `<td class="sym-cell">${s}<span class="co">${co}</span>
    <div class="sym-links"><a href="${tv}" target="_blank">TV</a><a href="${sc}" target="_blank">SCR</a></div></td>`;
}
function pct(v) { const s = v>=0?'+':''; return s+v+'%'; }
function cls(v) { return v>0?'pos':v<0?'neg':''; }
function scoreFill(v) { return v>=70?'high':v>=55?'mid':'low'; }

function chipRating(r) {
  const lo = r.toLowerCase();
  if (lo.includes('core')) return `<span class="chip core">${r}</span>`;
  if (lo.includes('watch')) return `<span class="chip watch">${r}</span>`;
  return `<span class="chip neutral">${r}</span>`;
}
function chipTrend(t) {
  const u = t.toUpperCase();
  if (u === 'BULLISH') return `<span class="chip bullish">↑ Bullish</span>`;
  if (u === 'BEARISH') return `<span class="chip bearish">↓ Bearish</span>`;
  return `<span class="chip neutral">${t}</span>`;
}
function chipStage(s) {
  if (s.includes('2')) return `<span class="chip stage2">${s}</span>`;
  return `<span class="chip neutral">${s}</span>`;
}
function chipTrigger(t) {
  if (t === 'WAIT') return `<span class="chip neutral">WAIT</span>`;
  if (t.includes('RETEST_TRIGGER')) return `<span class="chip watch">${t}</span>`;
  if (t.includes('BLOCKED') || t.includes('PRESSURE')) return `<span class="chip blocked">${t}</span>`;
  if (t.includes('READY')) return `<span class="chip core">${t}</span>`;
  return `<span class="chip neutral">${t}</span>`;
}

// ── research table ────────────────────────────────────────────────────────────
function buildResearchRow(d) {
  const stageParts = d.stage_sig.split('/').map(s => s.trim());
  const stageHtml = stageParts.map(s => chipStage(s)).join(' ');

  const tagsHtml = d.tags.map(t =>
    `<span class="tag ${t.ok ? 'ok' : 'bad'}">${t.ok ? '+' : '−'} ${t.label}</span>`
  ).join('');

  const freshClass = d.freshness.includes('fresh') ? 'pos' : (d.freshness.includes('needs') ? 'neg' : 'mut');

  return `<tr>
    ${sym(d.sym, d.company)}
    <td>
      <span class="mono" style="font-size:15px;font-weight:600">${d.policy_score}</span>
      <div class="score-bar"><div class="score-fill ${scoreFill(d.policy_score)}" style="width:${d.policy_score}%"></div></div>
      <div style="margin-top:4px">
        <span class="mono" style="font-size:11px;color:var(--muted)">Readiness </span>
        <span class="mono" style="font-size:12px;font-weight:600">${d.readiness}</span>
      </div>
    </td>
    <td>${chipRating(d.rating)}</td>
    <td>${stageHtml}<br>${chipTrend(d.supertrend)}</td>
    <td class="mono"><span style="color:var(--amber)">${d.rsi}</span> <span class="mut" style="font-size:10px">RSI</span><br>
        <span style="color:var(--accent)">${d.rs}</span> <span class="mut" style="font-size:10px">RS</span></td>
    <td class="mono">
      ₹${d.price.toLocaleString('en-IN')}
      <br><span class="${cls(d.pct_chg)}" style="font-size:11px">${pct(d.pct_chg)}</span>
    </td>
    <td><div class="tags">${tagsHtml || '<span class="mut">—</span>'}</div></td>
    <td class="mono" style="font-size:11px">
      Rev ₹${d.rev_cr.toLocaleString('en-IN')}cr <span class="${cls(d.rev_yoy)}">${pct(d.rev_yoy)}</span><br>
      PAT ₹${d.pat_cr.toLocaleString('en-IN')}cr <span class="${cls(d.pat_yoy)}">${pct(d.pat_yoy)}</span><br>
      D/E ${d.d_e} · OCF ₹${d.ocf_cr}cr
    </td>
    <td style="font-size:11px">
      <span class="mono ${freshClass.includes('pos')?'pos':freshClass.includes('neg')?'neg':'mut'}">${d.qtr}</span><br>
      <span class="mut" style="font-size:10px">${d.financial_freshness||d.freshness}</span>
    </td>
    <td>
      ${chipTrigger(d.trigger)}
      <div style="font-size:10px;color:var(--muted);margin-top:4px">${d.action}</div>
    </td>
  </tr>`;
}

// ── market-check table ────────────────────────────────────────────────────────
function buildMarketRow(d) {
  const bucketCls = d.bucket.toLowerCase().includes('clean') ? 'core' : 'watch';
  const moveCls = cls(d.move_vs_ref);
  const pnlCls = cls(d.shadow_pnl);
  const pnlSign = d.shadow_pnl >= 0 ? '+' : '';
  const rrStr = d.rr !== null ? d.rr.toFixed(2)+'R' : '—';
  return `<tr>
    ${sym(d.sym, d.company)}
    <td>
      <span class="chip ${bucketCls}" style="font-size:10px">${d.bucket}</span>
      <div style="font-size:10px;color:var(--muted);margin-top:4px">${d.theme_lens}</div>
    </td>
    <td>
      <span class="mono" style="font-weight:600">${d.policy_score}</span><br>
      <span style="font-size:10px;color:var(--muted)">${d.rating}</span>
    </td>
    <td class="mono">
      ₹${d.latest.toLocaleString('en-IN')} <span class="${cls(d.pct_chg)}">${pct(d.pct_chg)}</span><br>
      <span class="mut" style="font-size:10px">ref ₹${d.ref_price.toLocaleString('en-IN')}
        <span class="${moveCls}">${pct(d.move_vs_ref)}</span></span>
    </td>
    <td class="pnl-cell">
      <div class="main ${pnlCls}">${pnlSign}₹${d.shadow_pnl.toLocaleString('en-IN')}</div>
      <div class="sub">₹${d.paper_lat.toLocaleString('en-IN')} position</div>
      <div class="sub ${pnlCls}">${pnlSign}${d.shadow_pnl_pct}% NAV</div>
    </td>
    <td>
      <div class="levels">
        <span class="lbl">Breakout</span><span class="lvl">₹${d.breakout}</span>
        <span class="lbl">Retest</span><span class="lvl">₹${d.retest}</span>
        <span class="lbl">Stop</span><span class="lvl neg">₹${d.stop}</span>
        <span class="lbl">Target</span><span class="lvl pos">₹${d.target}</span>
      </div>
    </td>
    <td class="mono" style="font-size:11px">
      To brk <span class="${cls(-d.d_breakout)}">${pct(d.d_breakout)}</span><br>
      Abv ret <span class="pos">${pct(d.d_retest)}</span><br>
      Abv stp <span class="pos">${pct(d.d_stop)}</span>
    </td>
    <td class="mono" style="font-weight:600;font-size:14px">${rrStr}</td>
    <td>${chipTrigger(d.trigger)}</td>
    <td style="font-size:10px;color:var(--muted);max-width:160px">${d.next_action}</td>
  </tr>`;
}

document.getElementById('tbody-research').innerHTML = RESEARCH.map(buildResearchRow).join('');
document.getElementById('tbody-market').innerHTML   = MARKET.map(buildMarketRow).join('');
</script>
</body>
</html>
"""


# ── main ──────────────────────────────────────────────────────────────────────

def render(run_date: str | None = None, no_open: bool = False) -> Path:
    suffix = run_date or "*"
    res_csv = _latest_csv(f"agent_adda_smallcap_research_update_{suffix}.csv")
    mkt_csv = _latest_csv(f"agent_adda_smallcap_fund_latest_market_check_{suffix}.csv")

    if res_csv is None:
        sys.exit(f"[smallcap] No research CSV found in {MF_DIR}/extracted/")

    date_str = res_csv.stem.split("_")[-1]
    date_label = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

    res_rows = build_research_rows(_load_csv(res_csv))
    mkt_rows = build_market_rows(_load_csv(mkt_csv)) if mkt_csv else []

    r_summary = _research_summary(res_rows)
    m_summary = _market_summary(mkt_rows)

    html = Template(HTML_TEMPLATE).safe_substitute(
        DATE_LABEL=date_label,
        RESEARCH_JSON=json.dumps(res_rows, indent=2),
        MARKET_JSON=json.dumps(mkt_rows, indent=2),
        R_SUMMARY_JSON=json.dumps(r_summary),
        M_SUMMARY_JSON=json.dumps(m_summary),
    )

    REPORTS_LATEST.mkdir(parents=True, exist_ok=True)
    out_latest = REPORTS_LATEST / "smallcap_fund_dashboard.html"
    out_latest.write_text(html, encoding="utf-8")

    year = date_str[:4]
    archive_dir = REPORTS_ARCHIVE / year
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"Smallcap_Research_{date_str}.html"
    import shutil
    shutil.copy2(out_latest, archive_path)

    print(f"[smallcap] Rendered research={len(res_rows)} market={len(mkt_rows)} → {out_latest.relative_to(ROOT)}")
    print(f"[smallcap] Archive  → {archive_path.relative_to(ROOT)}")
    print(f"[smallcap] Summary  → core={r_summary['core']} wait={r_summary['wait']} shadow_pnl={m_summary['total_pnl']}")

    if not no_open:
        try:
            subprocess.Popen(["open", str(out_latest)])
        except Exception:
            pass

    return out_latest


def _cli(argv=None):
    p = argparse.ArgumentParser(description="Generate Agent Adda Smallcap Research themed HTML dashboard")
    p.add_argument("--run-date", default=None, help="YYYYMMDD date suffix (default: latest)")
    p.add_argument("--no-open", action="store_true")
    args = p.parse_args(argv)
    render(run_date=args.run_date, no_open=args.no_open)


if __name__ == "__main__":
    _cli()
