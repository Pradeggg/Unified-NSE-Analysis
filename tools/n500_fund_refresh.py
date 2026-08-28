#!/usr/bin/env python3
"""
n500_fund_refresh.py — NIFTY 500 Fund Dashboard Refresh
=========================================================
Reads  : data/fund_holdings_n500.json  (single source of truth)
Fetches: Live prices via yfinance + DB snapshots, fundamentals, quarterly results
Applies: NIFTY 500 fund rules compliance gate per position
Writes : reports/latest/n500_fund_dashboard.html
Opens  : Browser (unless --no-open)

Fund rules (NIFTY 500):
  Stage S1/S2 · RS ≥ 65 · TechScore ≥ 65 · FundScore ≥ 65
  Supertrend BULLISH · Signal BUY/HOLD · Stop-loss −5%

Usage:
  python tools/n500_fund_refresh.py
  python tools/n500_fund_refresh.py --no-open
  python tools/n500_fund_refresh.py --skip-prices
  python tools/n500_fund_refresh.py --skip-news
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).parent.parent

# Load parent .env
_env_file = ROOT.parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            if _k.strip() and not os.environ.get(_k.strip()):
                os.environ[_k.strip()] = _v.strip().strip('"').strip("'")

sys.path.insert(0, str(ROOT))
from postgres.loader import pg

# Import shared utilities from fund_refresh
from tools.fund_refresh import (
    CSS,
    fetch_live_prices as _fetch_prices_base,
    fetch_db_data,
    build_js_data,
    compute_rows,
    fund_summary,
    fetch_alerts_db,
    fetch_news_yf,
    summarize_news_llm,
    generate_technical_alerts,
    render_alerts_tab,
    render_orders_tab,
    _entry_label,
    _sparkline_svg,
    fetch_history_for_dashboard,
    persist_to_pg,
)

# ── Paths ──────────────────────────────────────────────────────────────────
HOLDINGS_FILE  = ROOT / "data" / "fund_holdings_n500.json"
PRICES_CACHE   = ROOT / "data" / "n500_prices_cache.json"
DASHBOARD_OUT  = ROOT / "reports" / "latest" / "n500_fund_dashboard.html"
TODAY          = date.today()
SL_PCT         = 0.05   # 5% stop-loss for NIFTY 500

# ── Fund rules ──────────────────────────────────────────────────────────────
N500_RULES = {
    "Stage S1/S2":      lambda d: d.get("stage") in ("S1", "S2"),
    "RS ≥ 65":          lambda d: (d.get("rs") or 0) >= 65,
    "TechScore ≥ 65":   lambda d: (d.get("tech") or 0) >= 65,
    "FundScore ≥ 65":   lambda d: (d.get("enh_fund") or 0) >= 65,
    "Supertrend BULL":  lambda d: d.get("supertrend") == "BULLISH",
    "Signal BUY/HOLD":  lambda d: d.get("signal") in ("BUY", "HOLD"),
}


# ─────────────────────────────────────────────────────────────────────────────
# Load holdings
# ─────────────────────────────────────────────────────────────────────────────
def load_holdings() -> tuple[dict, dict]:
    with open(HOLDINGS_FILE) as f:
        h = json.load(f)
    meta  = h.get("_meta", {})
    holds = h.get("n500", {})
    return meta, holds


# ─────────────────────────────────────────────────────────────────────────────
# Fetch live prices (with n500-specific cache)
# ─────────────────────────────────────────────────────────────────────────────
def fetch_live_prices(syms: list[str], skip: bool = False) -> dict[str, float]:
    cache = {}
    if PRICES_CACHE.exists():
        try:
            c = json.loads(PRICES_CACHE.read_text())
            if c.get("date") == str(TODAY):
                cache = c.get("prices", {})
        except Exception:
            pass

    if skip and cache:
        print(f"  [prices] using cache ({TODAY}, {len(cache)} symbols)")
        return cache

    prices = {}
    if syms:
        tickers = [f"{s}.NS" for s in syms]
        print(f"  [prices] fetching {len(tickers)} tickers from yfinance...")
        try:
            data = yf.download(tickers, period="2d", auto_adjust=True, progress=False, threads=True)
            close = data["Close"] if "Close" in data else data
            if hasattr(close, "columns"):
                for t in close.columns:
                    sym = t.replace(".NS", "")
                    vals = close[t].dropna()
                    if len(vals):
                        prices[sym] = float(round(vals.iloc[-1], 2))
            elif len(syms) == 1:
                vals = close.dropna()
                if len(vals):
                    prices[syms[0]] = float(round(vals.iloc[-1], 2))
        except Exception as e:
            print(f"  [prices] yfinance error: {e}")

    for sym in syms:
        if sym not in prices and sym in cache:
            prices[sym] = cache[sym]

    PRICES_CACHE.write_text(json.dumps({"date": str(TODAY), "prices": prices}, indent=2))
    print(f"  [prices] fetched {len(prices)}/{len(syms)} prices")
    return prices


# ─────────────────────────────────────────────────────────────────────────────
# Fetch NIFTY 500 candidates (by index membership, not cap category)
# ─────────────────────────────────────────────────────────────────────────────
_N500_CAND_SQL = """
    SELECT DISTINCT ON (ss.symbol)
        ss.symbol, ss.company_name, ss.sector, ss.market_cap_cat,
        ss.technical_score, ss.stage,
        ss.relative_strength, ss.enhanced_fund_score, ss.supertrend_state,
        ss.trading_signal, ss.investment_score, ss.financial_strength,
        ss.institutional_backing, ss.snapshot_date, ss.rsi,
        COALESCE(ss.live_price, ss.price) AS cmp,
        vcp.vcp_breakout_pct, vcp.vcp_contraction_pct, vcp.vcp_score
    FROM scores.stage_snapshots ss
    JOIN ref.index_compositions ic ON ic.symbol = ss.symbol
    LEFT JOIN LATERAL (
        SELECT vcp_breakout_pct, vcp_contraction_pct, vcp_score
        FROM scores.stage2_vcp_picks
        WHERE symbol = ss.symbol
        ORDER BY snapshot_date DESC
        LIMIT 1
    ) vcp ON true
    WHERE ic.index_symbol = 'NIFTY 500'
      AND ss.stage IN ('S1', 'S2', 'STAGE_1', 'STAGE_2')
      AND ss.relative_strength >= 65
      AND ss.technical_score >= 65
      AND ss.enhanced_fund_score >= 65
      AND ss.supertrend_state = 'BULLISH'
      AND ss.trading_signal IN ('BUY', 'HOLD')
      AND ss.stage IS DISTINCT FROM 'UNKNOWN'
      AND ss.symbol != ALL(%s)
    ORDER BY ss.symbol, ss.snapshot_date DESC
"""

def fetch_n500_candidates(existing_syms: list[str], n: int = 40) -> list[dict]:
    conn = pg()
    cur  = conn.cursor()
    cur.execute(_N500_CAND_SQL, (existing_syms or [],))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    for r in rows:
        r["entry_label"] = _entry_label(r)
    _order = {"IDEAL": 0, "AT_PIVOT": 1, "BASING": 2, "EXTENDED": 3}
    rows.sort(key=lambda r: (_order.get(r["entry_label"], 9),
                             -float(r.get("investment_score") or 0)))
    n_ideal = sum(1 for r in rows if r["entry_label"] == "IDEAL")
    print(f"  [candidates] N500={len(rows)} ({n_ideal} IDEAL)")
    return rows[:n]


# ─────────────────────────────────────────────────────────────────────────────
# Render candidates tab
# ─────────────────────────────────────────────────────────────────────────────
_ENTRY_COLOR = {"IDEAL": "#3fb950", "AT_PIVOT": "#58a6ff", "BASING": "#d29922", "EXTENDED": "#f85149"}
_ENTRY_HELP  = {
    "IDEAL":    "RSI 45–68, breakout 0–5%, contraction ≥15%. Best risk/reward.",
    "AT_PIVOT": "Breakout 0–8%, RSI ≤75. Acceptable — momentum confirmed.",
    "BASING":   "Price below pivot (breakout <0). Wait for trigger.",
    "EXTENDED": "RSI >75 or breakout >10%. Chased — wait for pullback.",
}

_CAP_BADGE = {
    "LARGE_CAP":  ("LC",  "#58a6ff"),
    "MID_CAP":    ("MC",  "#3fb950"),
    "SMALL_CAP":  ("SC",  "#d29922"),
    "MICRO_CAP":  ("μC",  "#a371f7"),
}

def _cap_badge(cat: str) -> str:
    label, color = _CAP_BADGE.get(cat or "", ("?", "#8b949e"))
    return f'<span style="font-size:10px;font-weight:700;padding:2px 5px;border-radius:4px;background:{color}22;color:{color};border:1px solid {color}55">{label}</span>'


def render_n500_candidates_tab(cands: list, meta: dict) -> str:
    budget   = float(meta.get("budget_n500") or 300_000)
    slots    = int(meta.get("slots_n500") or 20)
    slot_val = budget / max(slots, 1)
    n_held   = meta.get("_n_held", 0)
    n_dry    = slots - n_held

    if not cands:
        return '<div style="padding:20px;color:var(--muted)">No NIFTY 500 candidates pass all rules today.</div>'

    rows_html = []
    for r in cands:
        sym   = r["symbol"]
        cmp   = float(r.get("cmp") or 0)
        qty   = int(slot_val // cmp) if cmp > 0 else 0
        inv   = qty * cmp
        el    = r.get("entry_label", "AT_PIVOT")
        color = _ENTRY_COLOR.get(el, "#8b949e")
        tip   = _ENTRY_HELP.get(el, "")
        cap   = _cap_badge(r.get("market_cap_cat") or "")
        stage = (r.get("stage") or "").replace("STAGE_", "S")
        vcp   = r.get("vcp_score")
        vcp_s = f'VCP:{vcp:.0f}' if vcp else "—"
        rows_html.append(f"""
        <tr>
          <td><span class="clickable-sym" onclick="openCard('{sym}')">{sym}</span> {cap}</td>
          <td style="color:var(--muted);font-size:11px">{(r.get('sector') or '')[:22]}</td>
          <td>{stage}</td>
          <td>{float(r.get('relative_strength') or 0):.1f}</td>
          <td>{float(r.get('technical_score') or 0):.1f}</td>
          <td>{float(r.get('enhanced_fund_score') or 0):.1f}</td>
          <td>₹{cmp:,.2f}</td>
          <td>{qty}</td>
          <td>₹{inv:,.0f}</td>
          <td>{vcp_s}</td>
          <td><span style="color:{color};font-weight:600;font-size:11px" title="{tip}">{el}</span></td>
        </tr>""")

    ideal_n = sum(1 for r in cands if r.get("entry_label") == "IDEAL")
    return f"""
<div style="padding:0 20px 20px">
  <div style="display:flex;align-items:center;gap:16px;margin-bottom:12px;flex-wrap:wrap">
    <div>
      <span style="font-size:15px;font-weight:600">🎯 NIFTY 500 Candidates</span>
      <span style="color:var(--muted);font-size:12px;margin-left:8px">{len(cands)} qualify · {ideal_n} IDEAL</span>
    </div>
    <div style="color:var(--muted);font-size:12px">
      Slot budget ₹{slot_val:,.0f} ({slots} slots · {n_dry} dry powder) ·
      Qty = floor(slot / CMP)
    </div>
  </div>
  <div style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:12px">
      <thead>
        <tr style="color:var(--muted);border-bottom:1px solid var(--border);text-align:left">
          <th style="padding:6px 8px">Symbol</th>
          <th style="padding:6px 8px">Sector</th>
          <th style="padding:6px 8px">Stage</th>
          <th style="padding:6px 8px">RS</th>
          <th style="padding:6px 8px">Tech</th>
          <th style="padding:6px 8px">EFS</th>
          <th style="padding:6px 8px">CMP</th>
          <th style="padding:6px 8px">Qty</th>
          <th style="padding:6px 8px">~Invest</th>
          <th style="padding:6px 8px">VCP</th>
          <th style="padding:6px 8px">Entry</th>
        </tr>
      </thead>
      <tbody>{''.join(rows_html)}</tbody>
    </table>
  </div>
  <div style="margin-top:10px;font-size:11px;color:var(--muted)">
    <b>Entry labels:</b>
    <span style="color:#3fb950">IDEAL</span> — RSI 45–68, breakout 0–5%, contraction ≥15% &nbsp;|&nbsp;
    <span style="color:#58a6ff">AT_PIVOT</span> — breakout 0–8%, RSI ≤75 &nbsp;|&nbsp;
    <span style="color:#d29922">BASING</span> — wait for trigger &nbsp;|&nbsp;
    <span style="color:#f85149">EXTENDED</span> — wait for pullback
  </div>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Render fund rules tab
# ─────────────────────────────────────────────────────────────────────────────
def render_n500_rules_tab() -> str:
    return """
<div style="padding:20px;max-width:860px">
  <h2>📋 NIFTY 500 Fund Rules</h2>

  <div style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:16px">
    <h3>Entry Criteria (all must pass)</h3>
    <table style="width:100%;border-collapse:collapse;margin-top:10px;font-size:13px">
      <tr><td style="padding:6px 0;color:var(--muted);width:180px">Universe</td>
          <td>NIFTY 500 constituents only (535 stocks · all cap sizes)</td></tr>
      <tr><td style="padding:6px 0;color:var(--muted)">Stage</td>
          <td>S1 or S2 (Weinstein Stage 1 base or Stage 2 uptrend)</td></tr>
      <tr><td style="padding:6px 0;color:var(--muted)">Relative Strength</td>
          <td>RS ≥ 65 (top-half momentum vs NSE universe)</td></tr>
      <tr><td style="padding:6px 0;color:var(--muted)">Technical Score</td>
          <td>TechScore ≥ 65 (RSI, MACD, SMA alignment, ATR)</td></tr>
      <tr><td style="padding:6px 0;color:var(--muted)">Fundamental Score</td>
          <td>Enhanced Fund Score ≥ 65 (EQ + SG + FS + IB percentile composite)</td></tr>
      <tr><td style="padding:6px 0;color:var(--muted)">Supertrend</td>
          <td>BULLISH (10-period, 3× ATR)</td></tr>
      <tr><td style="padding:6px 0;color:var(--muted)">Signal</td>
          <td>BUY or HOLD</td></tr>
      <tr><td style="padding:6px 0;color:var(--muted)">Entry timing</td>
          <td>IDEAL or AT_PIVOT preferred. Avoid EXTENDED (RSI &gt;75 or breakout &gt;10%)</td></tr>
    </table>
  </div>

  <div style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:16px">
    <h3>Position Sizing &amp; Risk</h3>
    <table style="width:100%;border-collapse:collapse;margin-top:10px;font-size:13px">
      <tr><td style="padding:6px 0;color:var(--muted);width:180px">Fund Budget</td>
          <td>₹3,00,000 (₹3L)</td></tr>
      <tr><td style="padding:6px 0;color:var(--muted)">Max Slots</td>
          <td>20 positions</td></tr>
      <tr><td style="padding:6px 0;color:var(--muted)">Slot Size</td>
          <td>₹15,000 per position (₹3L ÷ 20)</td></tr>
      <tr><td style="padding:6px 0;color:var(--muted)">Stop-Loss</td>
          <td>−5% from entry (tighter vs SC/MC — larger caps, lower volatility)</td></tr>
      <tr><td style="padding:6px 0;color:var(--muted)">Qty</td>
          <td>floor(slot_budget / CMP) — round lots</td></tr>
      <tr><td style="padding:6px 0;color:var(--muted)">Concentration</td>
          <td>No single stock &gt; 10% of fund (i.e., &lt; 2 slots)</td></tr>
    </table>
  </div>

  <div style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:16px">
    <h3>Exit Rules</h3>
    <ul style="margin-left:16px;line-height:1.8;font-size:13px">
      <li>Hard stop at −5% from entry price (automatic review)</li>
      <li>Stage breaks to S3/S4 → exit within 2 sessions</li>
      <li>Supertrend flips BEARISH → exit or tight trail</li>
      <li>Signal changes to SELL → exit at next open</li>
      <li>RS drops below 50 for 5 consecutive sessions → review</li>
      <li>Profit target: trail stop at SMA20 after +15% gain</li>
    </ul>
  </div>

  <div style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px">
    <h3>vs SC/MC Fund Differences</h3>
    <table style="width:100%;border-collapse:collapse;margin-top:10px;font-size:13px">
      <thead><tr style="color:var(--muted)">
        <th style="padding:6px 0;text-align:left">Parameter</th>
        <th style="padding:6px 0;text-align:left">SC Fund</th>
        <th style="padding:6px 0;text-align:left">MC Fund</th>
        <th style="padding:6px 0;text-align:left">N500 Fund</th>
      </tr></thead>
      <tbody>
        <tr><td style="padding:5px 0;color:var(--muted)">Universe</td>
            <td>SMALL_CAP</td><td>MID_CAP</td><td>NIFTY 500 (all caps)</td></tr>
        <tr><td style="padding:5px 0;color:var(--muted)">Stage</td>
            <td>S2 only</td><td>S1/S2</td><td>S1/S2</td></tr>
        <tr><td style="padding:5px 0;color:var(--muted)">Stop-loss</td>
            <td>−8%</td><td>−7%</td><td>−5%</td></tr>
        <tr><td style="padding:5px 0;color:var(--muted)">Slots</td>
            <td>9</td><td>15</td><td>20</td></tr>
        <tr><td style="padding:5px 0;color:var(--muted)">Budget</td>
            <td>₹2L</td><td>₹2L</td><td>₹3L</td></tr>
        <tr><td style="padding:5px 0;color:var(--muted)">Liquidity</td>
            <td>Lower</td><td>Medium</td><td>Higher (index stocks)</td></tr>
      </tbody>
    </table>
  </div>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Render full HTML dashboard
# ─────────────────────────────────────────────────────────────────────────────
def render_n500_html(
    meta: dict,
    holds: dict,
    rows: list,
    summary: dict,
    js_data: dict,
    cands: list,
    generated_at: str,
    tech_alerts: list,
    db_alerts: dict,
    news_data: dict,
    active_nse_to_db: dict,
    history: dict,
) -> str:
    history = history or {"funds": {}, "positions": {}}

    def _fund_today(fund: str) -> dict:
        frows = history["funds"].get(fund, [])
        return frows[-1] if frows else {}

    n500_hist = _fund_today("N500")

    def _spark(fund: str, width: int = 72, height: int = 22) -> str:
        vals = [r["pnl_pct"] for r in history["funds"].get(fund, [])]
        return _sparkline_svg(vals, width=width, height=height)

    n500_spark = _spark("N500")

    def _delta_pill(val, prefix=""):
        if val is None or val == 0.0:
            return ""
        sg  = "+" if val >= 0 else ""
        cls = "pos" if val >= 0 else "neg"
        return f'<span class="delta-pill {cls}">{prefix}{sg}{val:.1f}%</span>'

    def _pos_day_pill(sym: str) -> str:
        prows = history["positions"].get(sym, [])
        if len(prows) >= 2:
            delta = round(prows[-1]["pnl_pct"] - prows[-2]["pnl_pct"], 1)
            return _delta_pill(delta)
        return ""

    pos_hist_js = "const POSITION_HISTORY = " + json.dumps({
        sym: [{"d": r["date"], "p": round(r["pnl_pct"], 2), "c": round(r["price"], 2)}
              for r in rrows]
        for sym, rrows in history["positions"].items()
    }, ensure_ascii=False) + ";"

    slots  = meta.get("slots_n500", 20)
    n_held = len(holds)
    n_dry  = slots - n_held
    inv    = summary["inv"]
    cur_v  = summary["cur"]
    pnl    = summary["pnl"]
    pct    = summary["pct"]
    s      = lambda x: "+" if x >= 0 else ""
    c      = lambda x: "pos" if x >= 0 else "neg"

    fund_membership = {sym: "N500" for sym in holds}
    js_stock_data   = "const STOCK_DATA = " + json.dumps(js_data, indent=2, ensure_ascii=False) + ";"
    js_membership   = "const FUND_MEMBERSHIP = " + json.dumps(fund_membership) + ";"

    def sym_span(sym):
        return f'<span class="clickable-sym" onclick="openCard(\'{sym}\')">{sym}</span>'

    def pnl_cell(r):
        cl  = "pos" if r["pnl"] >= 0 else "neg"
        sg  = "+" if r["pnl"] >= 0 else ""
        tag = ' <span class="new-tag">NEW</span>' if r.get("new") else ""
        day = _pos_day_pill(r["sym"])
        return f'<td class="{cl}">{sg}₹{r["pnl"]:,.0f} ({sg}{r["pnl_pct"]:.1f}%){day}{tag}</td>'

    def hold_row(r):
        return (
            f'<tr><td>{sym_span(r["sym"])}</td>'
            f'<td>₹{r["entry"]:,.2f}</td><td>₹{r["price"]:,.2f}</td><td>{r["qty"]}</td>'
            f'<td>₹{r["invested"]:,.0f}</td><td>₹{r["current"]:,.0f}</td>'
            f'{pnl_cell(r)}'
            f'<td>₹{r["sl"]:,.2f}</td><td>{r["buy_date"]}</td><td>{r["sell_date"]}</td><td>{r["days"]}d</td>'
            f'</tr>'
        )

    rows_html = "\n".join(hold_row(r) for r in rows) if rows else (
        '<tr><td colspan="11" style="text-align:center;color:var(--muted);padding:24px">'
        'No positions yet — see Candidates tab for qualified NIFTY 500 stocks.</td></tr>'
    )

    # Compliance gate for holdings
    compliance_rows = []
    for sym, h_data in holds.items():
        db_sym = active_nse_to_db.get(sym, sym)
        d = js_data.get(sym, {})
        checks = {k: fn(d) for k, fn in N500_RULES.items()}
        n_pass = sum(checks.values())
        all_ok = all(checks.values())
        gate_color = "#3fb950" if all_ok else "#f85149"
        checks_html = "".join(
            f'<span style="color:{"#3fb950" if v else "#f85149"};margin-right:6px">{"✅" if v else "❌"} {k}</span>'
            for k, v in checks.items()
        )
        compliance_rows.append(
            f'<tr><td><span class="clickable-sym" onclick="openCard(\'{sym}\')">{sym}</span></td>'
            f'<td style="color:{gate_color};font-weight:600">{"PASS" if all_ok else f"FAIL {n_pass}/6"}</td>'
            f'<td style="font-size:11px">{checks_html}</td></tr>'
        )
    compliance_html = ("\n".join(compliance_rows) if compliance_rows else
                       '<tr><td colspan="3" style="color:var(--muted);padding:12px">No positions to check.</td></tr>')

    alerts_badge = len([a for a in tech_alerts if a["severity"] in ("CRITICAL", "WARNING")])
    meta["_n_held"] = n_held
    cands_tab_html   = render_n500_candidates_tab(cands, meta)
    rules_tab_html   = render_n500_rules_tab()
    alerts_tab_html  = render_alerts_tab(tech_alerts, db_alerts, news_data, active_nse_to_db)

    # --- Orders tab (reuse SC rows slot) ---
    orders_html = render_orders_tab(rows, [])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>NIFTY 500 Fund Dashboard — {TODAY}</title>
<style>
{CSS}
.new-tag{{background:#238636;color:#fff;font-size:10px;padding:1px 5px;border-radius:3px;margin-left:4px}}
.delta-pill{{font-size:11px;padding:1px 5px;border-radius:3px;margin-left:4px}}
.delta-pill.pos{{background:#1a3a2a;color:#3fb950}}
.delta-pill.neg{{background:#3a1a1a;color:#f85149}}
.spark-wrap{{opacity:.7}}
.spark-stat-box{{display:flex;align-items:center;gap:10px}}
</style>
</head>
<body>
<div style="padding:20px 20px 0">
  <h1>📊 NIFTY 500 Fund Dashboard</h1>
  <div style="color:var(--muted);font-size:12px;margin-top:4px">
    As of {TODAY} · Inception {meta.get("inception_date","2026-08-18")} ·
    {n_held}/{slots} slots ({n_dry} dry powder) · Generated {generated_at}
  </div>
</div>

<div class="tabs">
  <div class="tab active" onclick="switchTab('tab-pl')">📊 Fund P&amp;L</div>
  <div class="tab" onclick="switchTab('tab-orders')">📒 Orders</div>
  <div class="tab" onclick="switchTab('tab-candidates')">🎯 Candidates</div>
  <div class="tab" onclick="switchTab('tab-rules')">📋 Fund Rules</div>
  <div class="tab" onclick="switchTab('tab-alerts')">🚨 Alerts{'<span class="alert-badge">' + str(alerts_badge) + '</span>' if alerts_badge else ''}</div>
</div>

<!-- ── P&L Tab ── -->
<div id="tab-pl" class="tab-content active">
  <div class="summary-bar">
    <div class="stat-box">
      <div class="label">Invested</div>
      <div class="value">₹{inv:,.0f}</div>
      <div class="sub">{n_held} positions</div>
    </div>
    <div class="stat-box">
      <div class="label">Current Value</div>
      <div class="value">₹{cur_v:,.0f}</div>
      <div class="sub">As of {TODAY}</div>
    </div>
    <div class="stat-box">
      <div class="label">P&amp;L</div>
      <div class="spark-stat-box">
        <div>
          <div class="value {c(pnl)}">{s(pnl)}₹{pnl:,.0f}</div>
          <div class="sub {c(pct)}">{s(pct)}{pct:.2f}%
            {n500_spark and f'&nbsp;{_delta_pill(n500_hist.get("day_pct"), "1d:")} {_delta_pill(n500_hist.get("wow_pct"), "WoW:")}' or ''}
          </div>
        </div>
        <div class="spark-wrap">{n500_spark}</div>
      </div>
    </div>
    <div class="stat-box">
      <div class="label">Win/Loss</div>
      <div class="value">{summary["W"]}W / {summary["L"]}L</div>
      <div class="sub">Stop-loss −5%</div>
    </div>
  </div>

  <div class="fund-card">
    <div class="fund-header">
      <div>
        <h2>🟠 NIFTY 500 Fund</h2>
        <div style="color:var(--muted);font-size:12px">{n_held}/{slots} slots · ₹3L budget · −5% SL</div>
      </div>
    </div>
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse">
        <thead>
          <tr style="color:var(--muted);border-bottom:1px solid var(--border);text-align:left;font-size:12px">
            <th style="padding:8px">Symbol</th>
            <th style="padding:8px">Entry ₹</th>
            <th style="padding:8px">CMP ₹</th>
            <th style="padding:8px">Qty</th>
            <th style="padding:8px">Invested</th>
            <th style="padding:8px">Current</th>
            <th style="padding:8px">P&amp;L</th>
            <th style="padding:8px">Stop ₹</th>
            <th style="padding:8px">Buy Date</th>
            <th style="padding:8px">Sell Date</th>
            <th style="padding:8px">Days</th>
          </tr>
        </thead>
        <tbody style="font-size:13px">{rows_html}</tbody>
      </table>
    </div>
  </div>

  <!-- Compliance Gate -->
  <div class="fund-card" style="margin-top:16px">
    <h3>🔍 Fund Rules Gate</h3>
    <table style="width:100%;border-collapse:collapse;margin-top:8px;font-size:12px">
      <thead>
        <tr style="color:var(--muted);border-bottom:1px solid var(--border)">
          <th style="padding:6px 8px;text-align:left">Symbol</th>
          <th style="padding:6px 8px;text-align:left">Status</th>
          <th style="padding:6px 8px;text-align:left">Checks</th>
        </tr>
      </thead>
      <tbody style="font-size:11px">{compliance_html}</tbody>
    </table>
  </div>
</div>

<!-- ── Orders Tab ── -->
<div id="tab-orders" class="tab-content">{orders_html}</div>

<!-- ── Candidates Tab ── -->
<div id="tab-candidates" class="tab-content">{cands_tab_html}</div>

<!-- ── Rules Tab ── -->
<div id="tab-rules" class="tab-content">{rules_tab_html}</div>

<!-- ── Alerts Tab ── -->
<div id="tab-alerts" class="tab-content">{alerts_tab_html}</div>

<!-- ── Stock Detail Side Panel ── -->
<div id="stockPanel" style="display:none;position:fixed;top:0;right:0;width:420px;height:100vh;
     background:var(--panel);border-left:1px solid var(--border);overflow-y:auto;z-index:1000;padding:16px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
    <h3 id="panelTitle" style="font-size:15px"></h3>
    <button onclick="closeCard()" style="background:none;border:none;color:var(--muted);cursor:pointer;font-size:18px">✕</button>
  </div>
  <div id="panelContent"></div>
</div>

<script>
{js_stock_data}
{js_membership}
{pos_hist_js}

const N500_RULES = {json.dumps({k: True for k in N500_RULES}, ensure_ascii=False)};

function switchTab(id) {{
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  const idx = ['tab-pl','tab-orders','tab-candidates','tab-rules','tab-alerts'].indexOf(id);
  document.querySelectorAll('.tab')[idx].classList.add('active');
}}

function openCard(sym) {{
  const d = STOCK_DATA[sym] || {{}};
  const fund = FUND_MEMBERSHIP[sym] || 'N500';
  let html = '<div style="font-size:12px">';

  // Rationale
  if (d.rationale) {{
    html += `<div style="background:var(--card);border-radius:6px;padding:10px;margin-bottom:12px;font-size:11px;color:var(--muted)">${{d.rationale}}</div>`;
  }}

  // Fund Rules Gate
  const rules = d.rules || {{}};
  const ruleKeys = Object.keys(rules);
  if (ruleKeys.length) {{
    html += '<div style="margin-bottom:12px"><b>Fund Rules Gate</b><br>';
    ruleKeys.forEach(k => {{
      const ok = rules[k];
      html += `<span style="color:${{ok?'#3fb950':'#f85149'}};margin-right:8px">${{ok?'✅':'❌'}} ${{k}}</span>`;
    }});
    html += '</div>';
  }}

  // Technical
  const tFields = [
    ['TechScore', d.tech], ['Stage', d.stage], ['RS', d.rs],
    ['RSI', d.rsi], ['Supertrend', d.supertrend], ['Signal', d.signal],
    ['Trend', d.trend], ['Stance', d.stance]
  ];
  html += '<div style="margin-bottom:12px"><b>Technical</b>';
  html += '<table style="width:100%;border-collapse:collapse;margin-top:6px">';
  tFields.forEach(([k,v]) => {{
    if (v !== undefined && v !== null && v !== '')
      html += `<tr><td style="color:var(--muted);padding:3px 0;width:120px">${{k}}</td><td>${{v}}</td></tr>`;
  }});
  html += '</table></div>';

  // Fund Scores
  const fFields = [
    ['Enh Fund Score', d.enh_fund], ['Earnings Quality', d.earnings_quality],
    ['Sales Growth', d.sales_growth], ['Fin Strength', d.fin_strength],
    ['Inst Backing', d.inst_backing], ['Inv Score', d.inv_score]
  ];
  html += '<div style="margin-bottom:12px"><b>Fund Scores</b>';
  html += '<table style="width:100%;border-collapse:collapse;margin-top:6px">';
  fFields.forEach(([k,v]) => {{
    if (v !== undefined && v !== null && v !== '')
      html += `<tr><td style="color:var(--muted);padding:3px 0;width:140px">${{k}}</td><td>${{v}}</td></tr>`;
  }});
  html += '</table></div>';

  // Fundamentals
  const funFields = [
    ['Piotroski F', d.piotroski], ['ROE %', d.roe], ['ROCE %', d.roce],
    ['D/E', d.de], ['Promoter %', d.promoter]
  ];
  html += '<div style="margin-bottom:12px"><b>Fundamentals</b>';
  html += '<table style="width:100%;border-collapse:collapse;margin-top:6px">';
  funFields.forEach(([k,v]) => {{
    if (v !== undefined && v !== null && v !== '')
      html += `<tr><td style="color:var(--muted);padding:3px 0;width:120px">${{k}}</td><td>${{v}}</td></tr>`;
  }});
  html += '</table></div>';

  // Quarterly
  if (d.quarterly && d.quarterly.length) {{
    html += '<div style="margin-bottom:12px"><b>Quarterly Results</b>';
    html += '<table style="width:100%;border-collapse:collapse;margin-top:6px;font-size:11px">';
    html += '<tr style="color:var(--muted)"><th style="text-align:left;padding:3px 0">Period</th><th>Rev ₹Cr</th><th>PAT ₹Cr</th><th>OPM%</th></tr>';
    d.quarterly.forEach(q => {{
      html += `<tr><td style="padding:3px 0">${{q.label}}</td><td style="text-align:right">${{q.revenue?.toFixed(0) ?? '—'}}</td><td style="text-align:right">${{q.pat?.toFixed(0) ?? '—'}}</td><td style="text-align:right">${{q.opm?.toFixed(1) ?? '—'}}</td></tr>`;
    }});
    html += '</table></div>';
  }}

  // Position sparkline
  const ph = POSITION_HISTORY[sym];
  if (ph && ph.length > 1) {{
    const vals = ph.map(r => r.p);
    const min = Math.min(...vals), max = Math.max(...vals);
    const range = max - min || 1;
    const W = 360, H = 60;
    const pts = vals.map((v, i) => `${{Math.round(i*(W/(vals.length-1)))}}, ${{Math.round(H - ((v-min)/range)*(H-4)+2)}}`).join(' ');
    const col = vals[vals.length-1] >= 0 ? '#3fb950' : '#f85149';
    html += `<div style="margin-top:8px"><b>P&L Trend (30d)</b><br><svg width="${{W}}" height="${{H}}" style="margin-top:4px"><polyline points="${{pts}}" fill="none" stroke="${{col}}" stroke-width="1.5"/></svg></div>`;
  }}

  html += '</div>';
  document.getElementById('panelTitle').textContent = sym + (d.company ? ' — ' + d.company : '');
  document.getElementById('panelContent').innerHTML = html;
  document.getElementById('stockPanel').style.display = 'block';
}}

function closeCard() {{
  document.getElementById('stockPanel').style.display = 'none';
}}
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Refresh NIFTY 500 Fund Dashboard")
    parser.add_argument("--no-open",     action="store_true", help="Don't open browser")
    parser.add_argument("--skip-prices", action="store_true", help="Use cached prices")
    parser.add_argument("--skip-news",   action="store_true", help="Skip yfinance news fetch")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  NIFTY 500 Fund Dashboard Refresh — {TODAY}")
    print(f"{'='*60}\n")

    # 1. Load holdings
    print("[1/6] Loading holdings from fund_holdings_n500.json ...")
    meta, holds = load_holdings()
    all_nse_syms = list(holds.keys())
    print(f"  N500: {len(holds)} positions ({meta.get('slots_n500', 20) - len(holds)} dry powder)")

    active_nse_to_db = {s: s for s in all_nse_syms}   # N500 symbols match DB directly
    active_db_syms   = list(active_nse_to_db.values())

    # 2. Fetch live prices
    print("\n[2/6] Fetching live prices ...")
    prices = fetch_live_prices(all_nse_syms, skip=args.skip_prices)

    # 3. Fetch DB data
    print("\n[3/6] Querying database ...")
    snaps, funds, qtrs = fetch_db_data(active_db_syms) if active_db_syms else ({}, {}, {})

    # 4. Build JS stock data
    print("\n[4/6] Building stock detail data ...")
    js_data = build_js_data(active_nse_to_db, snaps, funds, qtrs)

    # Inject N500 fund rules compliance into js_data
    for sym, d in js_data.items():
        d["rules"] = {k: fn(d) for k, fn in N500_RULES.items()}

    # 5. Compute P&L
    print("\n[5/6] Computing P&L ...")
    rows    = compute_rows(holds, prices, sl_pct=SL_PCT, entry_date_today=str(TODAY))
    summary = fund_summary(rows)
    s       = lambda x: "+" if x >= 0 else ""
    print(f"  N500: invested=₹{summary['inv']:,.0f}  P&L={s(summary['pnl'])}₹{summary['pnl']:,.0f} ({s(summary['pct'])}{summary['pct']:.1f}%)")

    # 5a. Persist
    print("\n[5a] Persisting to PostgreSQL ...")
    try:
        persist_to_pg(rows, [], summary, {"inv": 0, "cur": 0, "pnl": 0, "pct": 0, "W": 0, "L": 0},
                      snaps, active_nse_to_db)
    except Exception as e:
        print(f"  [persist] skipped: {e}")

    # 5b. History
    print("\n[5b] Loading historical trends ...")
    history = fetch_history_for_dashboard(all_nse_syms, lookback_days=30) if all_nse_syms else {}

    # SL alerts
    sl_breaches = [r["sym"] for r in rows if r["pnl_pct"] <= -5.0]
    if sl_breaches:
        print(f"\n  ⚠️  N500 STOP LOSS BREACH: {', '.join(sl_breaches)}")

    # 5c. Candidates
    print("\n[5c] Fetching NIFTY 500 candidates ...")
    cands = fetch_n500_candidates(active_db_syms, n=40)

    # 5d. DB Alerts
    print("\n[5d] Fetching DB alerts ...")
    db_alerts = fetch_alerts_db(active_db_syms) if active_db_syms else {}

    # 5e. News
    if args.skip_news:
        news_summaries = {}
        print("\n[5e] Skipping news fetch (--skip-news)")
    else:
        print("\n[5e] Fetching news from yfinance ...")
        news_data = fetch_news_yf(all_nse_syms) if all_nse_syms else {}
        print("\n[5f] Summarizing news with LLM ...")
        news_summaries = summarize_news_llm(news_data, db_alerts, active_nse_to_db) if all_nse_syms else {}

    # 5g. Technical alerts
    print("\n[5g] Generating technical alerts ...")
    tech_alerts = generate_technical_alerts(
        holds, {}, prices, snaps, qtrs, active_nse_to_db
    ) if holds else []
    n_crit = len([a for a in tech_alerts if a["severity"] == "CRITICAL"])
    n_warn = len([a for a in tech_alerts if a["severity"] == "WARNING"])
    print(f"  {n_crit} critical, {n_warn} warnings, {len(tech_alerts)-n_crit-n_warn} positive")

    # 6. Render
    print("\n[6/6] Rendering dashboard HTML ...")
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    DASHBOARD_OUT.parent.mkdir(parents=True, exist_ok=True)
    html = render_n500_html(
        meta=meta,
        holds=holds,
        rows=rows,
        summary=summary,
        js_data=js_data,
        cands=cands,
        generated_at=generated_at,
        tech_alerts=tech_alerts,
        db_alerts=db_alerts,
        news_data=news_summaries,
        active_nse_to_db=active_nse_to_db,
        history=history,
    )
    DASHBOARD_OUT.write_text(html)
    size_kb = DASHBOARD_OUT.stat().st_size // 1024
    print(f"  Written: {DASHBOARD_OUT}  ({size_kb} KB)")

    if not args.no_open:
        subprocess.run(["open", str(DASHBOARD_OUT)])
        print("  Opened in browser.")

    print(f"\n✅  Done — {generated_at}")
    print(f"   file://{DASHBOARD_OUT}\n")


if __name__ == "__main__":
    main()
