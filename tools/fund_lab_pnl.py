#!/usr/bin/env python3
"""
fund_lab_pnl.py — Agent Adda Fund Lab P&L Engine
Fetches latest closes and computes P&L for both SC and MC model portfolios,
plus the shadow portfolio (strategy-selected Stage 2 watchlist).

Usage:
  python tools/fund_lab_pnl.py                # print table to stdout
  python tools/fund_lab_pnl.py --json         # JSON output
  python tools/fund_lab_pnl.py --report       # generate HTML report
  python tools/fund_lab_pnl.py --date 20260814 # use specific date label
  python tools/fund_lab_pnl.py --no-shadow    # skip shadow portfolio section
"""

import argparse
import json
import pathlib
import sys
from datetime import date

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance not installed. Run: pip install yfinance", file=sys.stderr)
    sys.exit(1)

ROOT = pathlib.Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.fund_capital_policy import load_capital_policy  # noqa: E402

_POLICY = load_capital_policy()

try:
    import psycopg2
    _HAS_DB = True
except ImportError:
    _HAS_DB = False


FUND_SCORE_MIN = _POLICY.fund_score_min
RS_MIN_SC      = 0.0   # fetched dynamically; 0 = skip gate for MC

# ── SIGNAL HELPERS ────────────────────────────────────────────────────────────

def _compute_signal(stage: str, fund_pass: bool, rs_pass: bool,
                    tech_score: float | None, fund_score: float | None,
                    entry_date: str,
                    trading_signal: str = "HOLD",
                    trend_signal: str = "UNKNOWN",
                    supertrend_state: str = "UNKNOWN") -> tuple[str, str]:
    """
    Returns (label, css_colour_var) for a held position.

    Uses the same signal vocabulary as the Order Sheet so the question is
    always: "would I still buy this today?"

      NEW ENTRY   — bought today
      EXIT        — Stage 4 or SELL trading signal
      WEAKENING   — Stage 3/1, or supertrend flipped BEARISH inside Stage 2
      STRONG BUY  — Stage 2 + fund/RS pass + STRONG_BUY, or BUY + STRONG_BULLISH + ST BULLISH
      BUY         — Stage 2 + fund/RS pass + BUY signal (trend not fully confirmed)
      BUY ⚠trend  — Stage 2 + fund/RS pass + BUY but supertrend BEARISH
      HOLD        — Stage 2 + fund/RS pass, Darvas cooled to HOLD/WEAK_HOLD
      FUND WEAK   — Stage 2, FundScore below gate
      RS WEAK     — Stage 2, fund OK, RS below threshold
      WATCH       — fallback / no data
    """
    ts_sig = (trading_signal   or "HOLD").upper()
    tr_sig = (trend_signal     or "UNKNOWN").upper()
    st_sig = (supertrend_state or "UNKNOWN").upper()

    if stage == "STAGE_4" or ts_sig == "SELL":
        return "EXIT",      "#f85149"

    if stage in ("STAGE_3", "STAGE_1"):
        return "WEAKENING", "#f5a623"

    if stage == "STAGE_2" and st_sig == "BEARISH":
        return "WEAKENING", "#f5a623"

    if stage == "STAGE_2":
        if not fund_pass:
            return "FUND WEAK", "#fbbf24"
        if not rs_pass:
            return "RS WEAK",   "#fbbf24"

        strong_trend = tr_sig == "STRONG_BULLISH" and st_sig == "BULLISH"
        any_bullish  = tr_sig in ("STRONG_BULLISH", "BULLISH") and st_sig == "BULLISH"
        is_buy       = ts_sig in ("STRONG_BUY", "BUY")

        if ts_sig == "STRONG_BUY" or (is_buy and strong_trend):
            return "STRONG BUY",  "#1ed97a"
        if is_buy and any_bullish:
            return "BUY",         "#58a6ff"
        if is_buy:
            return "BUY ⚠trend",  "#f5a623"
        return "HOLD",            "#8b949e"

    return "WATCH", "#fbbf24"


def fetch_signals(symbols: list[str]) -> dict[str, dict]:
    """
    Query stage_snapshots + fundamental_scores for each symbol.
    Returns {sym: {stage, tech_score, rs, trading_signal, trend_signal,
                   supertrend_state, fund_score, fund_pass, rs_pass}}.
    Falls back to {} per symbol on error.
    """
    if not _HAS_DB or not symbols:
        return {}
    try:
        conn = psycopg2.connect(dbname="nse_market", user="pgorai", host="localhost",
                                options="-c statement_timeout=10000")
        cur  = conn.cursor()
        cur.execute("""
            SELECT s.symbol, s.stage, s.technical_score, s.relative_strength,
                   COALESCE(s.trading_signal,   'HOLD')    AS trading_signal,
                   COALESCE(s.trend_signal,     'UNKNOWN') AS trend_signal,
                   COALESCE(s.supertrend_state, 'UNKNOWN') AS supertrend_state,
                   f.enhanced_fund_score
            FROM   scores.stage_snapshots s
            LEFT JOIN scores.fundamental_scores f
                   ON f.symbol = s.symbol AND f.score_date = (
                       SELECT MAX(score_date) FROM scores.fundamental_scores
                       WHERE symbol = s.symbol
                   )
            WHERE  s.symbol = ANY(%s)
              AND  s.snapshot_date = (SELECT MAX(snapshot_date) FROM scores.stage_snapshots)
        """, (symbols,))
        rows = cur.fetchall()
        conn.close()
        out = {}
        for sym, stage, ts, rs, trading_sig, trend_sig, st_state, fs in rows:
            out[sym] = {
                "stage":           stage or "?",
                "tech_score":      float(ts or 0),
                "rs":              float(rs or 0),
                "trading_signal":  trading_sig,
                "trend_signal":    trend_sig,
                "supertrend_state": st_state,
                "fund_score":      float(fs or 0),
                "fund_pass":       (fs or 0) >= FUND_SCORE_MIN,
                "rs_pass":         True,   # SC RS gate checked separately; simplified here
            }
        return out
    except Exception as e:
        print(f"[signals] DB error: {e}", file=sys.stderr)
        return {}


def buy_conviction(tech_score: float, fund_score: float) -> tuple[str, str]:
    """Label + colour for a new buy based on TechScore + FundScore."""
    if tech_score >= 73 and fund_score >= 75:
        return "STRONG BUY", "var(--gain)"
    if tech_score >= 65 and fund_score >= 65:
        return "BUY", "#58a6ff"
    return "SPECULATIVE", "var(--warn)"

# ── FUND DEFINITIONS — loaded from data/fund_holdings.json ──────────────────

HOLDINGS_PATH = pathlib.Path(__file__).parent.parent / "data" / "fund_holdings.json"

def load_active_holdings() -> tuple[dict, dict, int, int]:
    """
    Load SC and MC entries from data/fund_holdings.json.
    Returns (sc_entries, mc_entries, budget_sc, budget_mc).
    """
    if not HOLDINGS_PATH.exists():
        return {}, {}, int(_POLICY.budget_sc), int(_POLICY.budget_mc)
    with open(HOLDINGS_PATH) as f:
        data = json.load(f)
    meta    = data.get("_meta", {})
    budget_sc = int(meta.get("budget_sc", _POLICY.budget_sc))
    budget_mc = int(meta.get("budget_mc", _POLICY.budget_mc))
    sc = {sym: {"entry": v["entry"], "entry_date": v["entry_date"],
                "qty": v.get("qty")}
          for sym, v in data.get("smallcap", {}).items()}
    mc = {sym: {"entry": v["entry"], "entry_date": v["entry_date"],
                "qty": v.get("qty")}
          for sym, v in data.get("midcap",   {}).items()}
    return sc, mc, budget_sc, budget_mc


SMALLCAP_ENTRIES, MIDCAP_ENTRIES, SC_BUDGET, MC_BUDGET = load_active_holdings()

# ── SHADOW PORTFOLIO (watchlist) ─────────────────────────────────────────────
WATCHLIST_PATH = pathlib.Path(__file__).parent.parent / "data" / "fund_watchlist.json"

def load_shadow_entries() -> tuple[dict, dict]:
    """Load shadow SC + MC entries from data/fund_watchlist.json."""
    if not WATCHLIST_PATH.exists():
        return {}, {}
    with open(WATCHLIST_PATH) as f:
        wl = json.load(f)
    def _to_entries(section: dict) -> dict:
        return {sym: {"entry": v["entry"], "entry_date": v["entry_date"],
                      "_ts": v.get("tech_score"), "_rs": v.get("rs")}
                for sym, v in section.items()}
    return _to_entries(wl.get("smallcap", {})), _to_entries(wl.get("midcap", {}))


def allocation(budget: float, n: int) -> float:
    return budget / n


def fetch_closes(symbols: list[str], period: str = "10d") -> dict:
    """
    Returns {symbol: {"close": float, "prev": float, "date": str}} for all symbols.
    Uses .NS suffix for NSE.
    """
    tickers = [s + ".NS" for s in symbols]
    result = {}

    for sym, ticker in zip(symbols, tickers):
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period=period, interval="1d", auto_adjust=True)
            if len(hist) < 2:
                result[sym] = {"close": None, "prev": None, "date": None, "error": "insufficient history"}
                continue
            result[sym] = {
                "close": round(float(hist["Close"].iloc[-1]), 2),
                "prev":  round(float(hist["Close"].iloc[-2]), 2),
                "date":  str(hist.index[-1].date()),
            }
        except Exception as e:
            result[sym] = {"close": None, "prev": None, "date": None, "error": str(e)}

    return result


def compute_positions(entries: dict, budget: float, closes: dict,
                      signals: dict | None = None) -> list[dict]:
    """Compute per-position P&L."""
    n = len(entries)
    alloc = allocation(budget, n)
    positions = []
    signals = signals or {}

    for sym, meta in entries.items():
        entry = meta["entry"]
        qty = int(meta["qty"]) if meta.get("qty") else int(alloc / entry)
        invested = qty * entry
        close_data = closes.get(sym, {})
        close = close_data.get("close")
        prev = close_data.get("prev")
        price_date = close_data.get("date", "N/A")

        if close is not None:
            current = qty * close
            pnl_rs = current - invested
            pnl_pct = (close / entry - 1) * 100
            day_pct = (close / prev - 1) * 100 if prev else None
        else:
            current = pnl_rs = pnl_pct = day_pct = None

        sig_data = signals.get(sym, {})
        sig_label, sig_col = _compute_signal(
            sig_data.get("stage", "?"),
            sig_data.get("fund_pass", True),
            sig_data.get("rs_pass",   True),
            sig_data.get("tech_score"),
            sig_data.get("fund_score"),
            meta["entry_date"],
            sig_data.get("trading_signal",   "HOLD"),
            sig_data.get("trend_signal",     "UNKNOWN"),
            sig_data.get("supertrend_state", "UNKNOWN"),
        )

        positions.append({
            "symbol":          sym,
            "entry":           entry,
            "entry_date":      meta["entry_date"],
            "qty":             qty,
            "invested":        round(invested, 2),
            "close":           close,
            "price_date":      price_date,
            "current":         round(current, 2) if current is not None else None,
            "pnl_rs":          round(pnl_rs, 2) if pnl_rs is not None else None,
            "pnl_pct":         round(pnl_pct, 4) if pnl_pct is not None else None,
            "day_pct":         round(day_pct, 4) if day_pct is not None else None,
            "error":           close_data.get("error"),
            "signal":          sig_label,
            "signal_col":      sig_col,
            "tech_score":      sig_data.get("tech_score"),
            "fund_score":      sig_data.get("fund_score"),
            "trading_signal":  sig_data.get("trading_signal", "—"),
            "trend_signal":    sig_data.get("trend_signal",   "—"),
            "supertrend_state":sig_data.get("supertrend_state","—"),
        })

    return sorted(positions, key=lambda x: (x["pnl_pct"] or 0), reverse=True)


def fund_summary(positions: list[dict]) -> dict:
    valid = [p for p in positions if p["pnl_rs"] is not None]
    total_inv = sum(p["invested"] for p in valid)
    total_curr = sum(p["current"] for p in valid)
    total_pnl = total_curr - total_inv
    pnl_pct = (total_pnl / total_inv * 100) if total_inv else 0
    return {
        "invested": round(total_inv, 2),
        "current": round(total_curr, 2),
        "pnl_rs": round(total_pnl, 2),
        "pnl_pct": round(pnl_pct, 4),
        "n_positions": len(valid),
        "n_winners": len([p for p in valid if p["pnl_pct"] > 0]),
        "n_losers": len([p for p in valid if p["pnl_pct"] < 0]),
    }


def print_table(fund_name: str, positions: list[dict], summary: dict) -> None:
    sep = "─" * 110
    print(f"\n{'═'*110}")
    print(f"  {fund_name.upper()}")
    print(f"{'═'*110}")
    print(f"  {'Symbol':<14} {'Entry':>9} {'Close':>9} {'Qty':>4}  {'Invested':>10}  {'Current':>10}  {'P&L ₹':>10}  {'P&L %':>8}  {'Day %':>7}")
    print(f"  {sep}")
    for p in positions:
        pnl_str  = f"{p['pnl_rs']:>+10.0f}"  if p["pnl_rs"]  is not None else "        N/A"
        pnl_pct  = f"{p['pnl_pct']:>+7.2f}%" if p["pnl_pct"] is not None else "     N/A"
        day_str  = f"{p['day_pct']:>+6.2f}%" if p["day_pct"] is not None else "   N/A"
        print(f"  {p['symbol']:<14} {p['entry']:>9.2f} {p['close'] or 0:>9.2f} {p['qty']:>4}  "
              f"{p['invested']:>10,.0f}  {p['current'] or 0:>10,.0f}  {pnl_str}  {pnl_pct}  {day_str}")
    print(f"  {sep}")
    print(f"  {'TOTAL':<14} {'':>9} {'':>9} {'':>4}  "
          f"{summary['invested']:>10,.0f}  {summary['current']:>10,.0f}  "
          f"{summary['pnl_rs']:>+10.0f}  {summary['pnl_pct']:>+7.2f}%")
    print(f"  Winners: {summary['n_winners']} | Losers: {summary['n_losers']} | Positions: {summary['n_positions']}")


def _pct_bar(pct: float, max_width: int = 80) -> str:
    """Return a CSS width string (px) capped at max_width, for sparkline bars."""
    return f"{min(abs(pct) * 5, max_width):.0f}px"


def build_html_report(
    sc_positions: list, sc_summary: dict,
    mc_positions: list, mc_summary: dict,
    combined_inv: float, combined_curr: float,
    combined_pnl: float, combined_pct: float,
    sh_sc_positions: list, sh_sc_summary: dict,
    sh_mc_positions: list, sh_mc_summary: dict,
    has_shadow: bool,
    label_date: str,
) -> str:
    today_str = str(date.today())

    def _pos_rows(positions: list, alloc: float) -> str:
        rows = ""
        for p in positions:
            pnl_rs  = p.get("pnl_rs")
            pnl_pct = p.get("pnl_pct")
            day_pct = p.get("day_pct")
            close   = p.get("close")
            is_gain = (pnl_pct or 0) >= 0
            is_day_gain = (day_pct or 0) >= 0
            g_cls   = "gain" if is_gain  else "loss"
            d_cls   = "gain" if is_day_gain else "loss"
            bar_w   = _pct_bar(pnl_pct or 0)
            bar_col = "var(--gain)" if is_gain else "var(--loss)"
            pnl_s   = f"{'+'if is_gain else ''}{pnl_pct:.2f}%" if pnl_pct is not None else "—"
            day_s   = f"{'+'if is_day_gain else ''}{day_pct:.2f}%" if day_pct is not None else "—"
            pnl_rs_s = f"₹{'+'if is_gain else ''}{pnl_rs:,.0f}" if pnl_rs is not None else "—"
            close_s = f"₹{close:,.2f}" if close else "—"
            sig_label = p.get("signal", "")
            sig_col   = p.get("signal_col", "#8b949e")
            # Build rgba background from hex colour — matches order-sheet pill style
            _bg_map = {
                "#1ed97a": "rgba(30,217,122,.15)",
                "#58a6ff": "rgba(88,166,255,.15)",
                "#f5a623": "rgba(245,166,35,.12)",
                "#fbbf24": "rgba(245,191,36,.12)",
                "#f85149": "rgba(248,81,73,.13)",
                "#8b949e": "rgba(139,148,158,.12)",
            }
            sig_bg = _bg_map.get(sig_col, "rgba(139,148,158,.12)")
            sig_html  = (f'<span style="font-size:10px;font-weight:700;'
                         f'padding:1px 7px;border-radius:4px;'
                         f'background:{sig_bg};color:{sig_col}">'
                         f'{sig_label}</span>') if sig_label else ""
            rows += f"""<tr>
  <td class="sym">{p['symbol']}</td>
  <td class="n">₹{p['entry']:,.2f}</td>
  <td class="n">{close_s}</td>
  <td class="n">{p['qty']}</td>
  <td class="n muted">₹{p['invested']:,.0f}</td>
  <td class="n">₹{p['current']:,.0f}</td>
  <td class="n {g_cls} fw">{pnl_rs_s}</td>
  <td class="n">
    <span class="{g_cls} fw">{pnl_s}</span>
    <div class="bar-wrap"><div class="bar" style="width:{bar_w};background:{bar_col}"></div></div>
  </td>
  <td class="n {d_cls}">{day_s}</td>
  <td>{sig_html}</td>
</tr>"""
        return rows

    def _fund_card(title: str, positions: list, summary: dict, budget: float,
                   colour_var: str, label: str) -> str:
        n         = len([p for p in positions if p.get("close")])
        alloc     = budget / len(positions) if positions else 0
        is_gain   = summary.get("pnl_pct", 0) >= 0
        g_cls     = "gain" if is_gain else "loss"
        sign      = "+" if is_gain else ""
        pnl_bar_w = _pct_bar(summary.get("pnl_pct", 0), 120)
        bar_col   = "var(--gain)" if is_gain else "var(--loss)"
        rows_html = _pos_rows(positions, alloc)
        return f"""<div class="fund-card">
  <div class="fund-hdr" style="border-left-color:{colour_var}">
    <div class="fund-title">{title}</div>
    <div class="fund-meta">{label} · budget ₹{budget:,.0f} · {len(positions)} slots · ₹{alloc:,.0f}/slot</div>
    <div class="fund-kpi">
      <span class="kpi-inv">invested <strong>₹{summary.get('invested',0):,.0f}</strong></span>
      <span class="kpi-curr">current <strong>₹{summary.get('current',0):,.0f}</strong></span>
      <span class="kpi-pnl {g_cls}"><strong>{sign}₹{summary.get('pnl_rs',0):,.0f}  ({sign}{summary.get('pnl_pct',0):.2f}%)</strong></span>
      <span class="kpi-wl muted">{summary.get('n_winners',0)}W · {summary.get('n_losers',0)}L</span>
    </div>
    <div class="fund-bar"><div style="width:{pnl_bar_w};height:3px;border-radius:2px;background:{bar_col}"></div></div>
  </div>
  <div class="tbl-wrap"><table>
    <thead><tr>
      <th>Symbol</th><th class="n">Entry</th><th class="n">Close</th><th class="n">Qty</th>
      <th class="n">Invested</th><th class="n">Current</th>
      <th class="n">P&amp;L ₹</th><th class="n">P&amp;L %</th><th class="n">Day %</th><th>Signal</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
  </table></div>
</div>"""

    is_gain_combined = combined_pct >= 0
    gc_cls = "gain" if is_gain_combined else "loss"
    sign_c = "+" if is_gain_combined else ""

    sc_card = _fund_card(
        "SmallCap Super Performers", sc_positions, sc_summary, SC_BUDGET,
        "var(--sc-col)", "SC S2 — Stage 2 + RS + Fund ≥ 65"
    )
    mc_card = _fund_card(
        "MidCap Leaders", mc_positions, mc_summary, MC_BUDGET,
        "var(--mc-col)", "MC S1 — Stage 2 + Fund ≥ 65"
    )

    shadow_html = ""
    if has_shadow:
        sh_inv  = sh_sc_summary.get("invested",0) + sh_mc_summary.get("invested",0)
        sh_curr = sh_sc_summary.get("current",0)  + sh_mc_summary.get("current",0)
        sh_pnl  = sh_curr - sh_inv
        sh_pct  = sh_pnl / sh_inv * 100 if sh_inv else 0
        sh_gain = sh_pct >= 0
        sh_cls  = "gain" if sh_gain else "loss"
        sh_sign = "+" if sh_gain else ""
        sh_sc_card = _fund_card(
            "Shadow SC", sh_sc_positions, sh_sc_summary, SC_BUDGET,
            "#7b90e8", "SC S2 — shadow / watchlist"
        )
        sh_mc_card = _fund_card(
            "Shadow MC", sh_mc_positions, sh_mc_summary, MC_BUDGET,
            "#9b70e8", "MC S1 — shadow / watchlist"
        )
        shadow_html = f"""
<details class="shadow-collapse">
<summary class="section-hdr shadow-summary">
  👁 Shadow Portfolio &nbsp;
  <span class="sh-summary-kpi {sh_cls}">{sh_sign}₹{sh_pnl:,.0f} ({sh_sign}{sh_pct:.2f}%)</span>
  <span class="sh-toggle-hint">▸ click to expand</span>
</summary>
<div class="combined-bar" style="border-color:rgba(123,144,232,.25);margin-top:12px">
  <span class="comb-lbl">Shadow combined</span>
  <span class="comb-inv">₹{sh_inv:,.0f}</span>
  <span class="comb-arr">→</span>
  <span class="comb-curr">₹{sh_curr:,.0f}</span>
  <span class="comb-pnl {sh_cls}"><strong>{sh_sign}₹{sh_pnl:,.0f}&nbsp;({sh_sign}{sh_pct:.2f}%)</strong></span>
</div>
{sh_sc_card}
{sh_mc_card}
</details>"""

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fund Lab — {today_str}</title>
<style>
:root {{
  --bg:#07101c;--surface:#0d1b2a;--card:#132337;--card-hi:#172b42;
  --bdr:#1e3348;--bdr-hi:#28466a;
  --tx:#dceaf8;--tx-m:#4d6f8e;--tx-d:#253d54;
  --acc:#00ccb0;--acc-dim:rgba(0,204,176,.13);
  --gain:#1ed97a;--gain-dim:rgba(30,217,122,.13);
  --loss:#ff4560;--loss-dim:rgba(255,69,96,.13);
  --warn:#f5a623;
  --sc-col:#7bc8f5;--mc-col:#e8932d;
  --mono:'SF Mono','Cascadia Code','Fira Code',ui-monospace,Menlo,monospace;
  --sans:-apple-system,BlinkMacSystemFont,'Inter','Helvetica Neue',sans-serif;
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{font-size:14px;background:var(--bg);color:var(--tx)}}
body{{font-family:var(--sans);padding:20px 24px;max-width:1300px;margin:0 auto;background:var(--bg)}}
h1{{font-family:var(--mono);font-size:15px;font-weight:700;letter-spacing:.08em;
  color:var(--acc);margin-bottom:4px}}
.page-sub{{font-size:11px;color:var(--tx-m);margin-bottom:16px}}

/* combined bar */
.combined-bar{{display:flex;align-items:center;gap:14px;flex-wrap:wrap;
  background:var(--surface);border:1px solid var(--bdr);border-radius:10px;
  padding:12px 18px;margin-bottom:14px;font-size:13px;font-variant-numeric:tabular-nums}}
.comb-lbl{{font-family:var(--mono);font-size:11px;color:var(--tx-m);min-width:120px;letter-spacing:.04em}}
.comb-inv,.comb-curr{{color:var(--tx-m)}}
.comb-arr{{color:var(--tx-d)}}
.comb-pnl{{font-size:15px}}

/* section header */
.section-hdr{{font-size:12px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;
  color:var(--tx-m);padding:16px 0 6px;border-bottom:1px solid var(--bdr);margin-bottom:12px}}

/* fund card */
.fund-card{{background:var(--card);border:1px solid var(--bdr);border-radius:10px;
  margin-bottom:14px;overflow:hidden}}
.fund-hdr{{padding:12px 16px;border-left:3px solid transparent;border-bottom:1px solid var(--bdr)}}
.fund-title{{font-size:14px;font-weight:700;margin-bottom:2px}}
.fund-meta{{font-size:11px;color:var(--tx-m);margin-bottom:8px}}
.fund-kpi{{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;font-variant-numeric:tabular-nums;
  margin-bottom:6px}}
.kpi-inv,.kpi-curr{{color:var(--tx-m)}}
.kpi-pnl{{font-size:13px}}
.kpi-wl{{font-size:11px}}
.fund-bar{{margin-top:4px}}

/* table */
.tbl-wrap{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:12px}}
thead th{{background:rgba(0,0,0,.2);color:var(--tx-m);font-size:10px;font-weight:700;
  text-transform:uppercase;letter-spacing:.05em;padding:6px 10px;
  border-bottom:1px solid var(--bdr);text-align:left;white-space:nowrap}}
thead th.n{{text-align:right}}
tbody td{{padding:6px 10px;border-bottom:1px solid var(--bdr);vertical-align:middle;white-space:nowrap}}
td.n{{text-align:right}}
td.muted{{color:var(--tx-m)}}
.sym{{font-family:var(--mono);font-weight:600;font-size:12px;letter-spacing:.04em}}
tbody tr:hover td{{background:var(--card-hi)}}

/* colours */
.gain{{color:var(--gain)}}
.loss{{color:var(--loss)}}
.fw{{font-weight:700}}
.muted{{color:var(--tx-m)}}

/* mini bar */
.bar-wrap{{height:3px;background:var(--bdr);border-radius:2px;margin-top:3px;min-width:60px}}
.bar{{height:3px;border-radius:2px;min-width:0}}
.footer{{font-size:11px;color:var(--tx-d);margin-top:16px;text-align:right;
  font-family:var(--mono);letter-spacing:.04em}}

/* shadow collapse */
.shadow-collapse{{border:none;margin:0;padding:0}}
.shadow-summary{{cursor:pointer;display:flex;align-items:center;gap:8px;
  list-style:none;user-select:none}}
.shadow-summary::-webkit-details-marker{{display:none}}
.sh-summary-kpi{{font-size:12px;font-weight:700;font-variant-numeric:tabular-nums}}
.sh-toggle-hint{{font-size:10px;color:var(--tx-d);margin-left:auto}}
.shadow-collapse[open] .sh-toggle-hint{{content:'▾ collapse'}}
.shadow-collapse[open] .sh-toggle-hint::before{{content:'▾ collapse'}}
.shadow-collapse:not([open]) .sh-toggle-hint::before{{content:'▸ click to expand'}}
</style></head><body>

<h1>AGENT ADDA · FUND LAB</h1>
<div class="page-sub">{today_str} · live prices via yfinance · ₹{SC_BUDGET+MC_BUDGET:,.0f} working budget</div>

<div class="combined-bar">
  <span class="comb-lbl">COMBINED</span>
  <span class="comb-inv">invested ₹{combined_inv:,.0f}</span>
  <span class="comb-arr">→</span>
  <span class="comb-curr">current ₹{combined_curr:,.0f}</span>
  <span class="comb-pnl {gc_cls}"><strong>{sign_c}₹{combined_pnl:,.0f}&nbsp;({sign_c}{combined_pct:.2f}%)</strong></span>
</div>

<div class="section-hdr">Active Portfolio</div>
{sc_card}
{mc_card}
{shadow_html}

<div class="footer">fund_lab_pnl.py · yfinance · {today_str}</div>
</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent Adda Fund Lab P&L")
    parser.add_argument("--json",   action="store_true", help="Output JSON")
    parser.add_argument("--report", action="store_true", help="Generate HTML report")
    parser.add_argument("--date", default=str(date.today()).replace("-", ""), help="Date label YYYYMMDD")
    parser.add_argument("--no-shadow", action="store_true", help="Skip shadow portfolio section")
    args = parser.parse_args()

    # Load shadow watchlist entries
    shadow_sc_entries, shadow_mc_entries = ({}, {}) if args.no_shadow else load_shadow_entries()
    has_shadow = bool(shadow_sc_entries or shadow_mc_entries)

    # Collect all symbols to fetch (deduplicated)
    all_syms_set = set(SMALLCAP_ENTRIES) | set(MIDCAP_ENTRIES) | set(shadow_sc_entries) | set(shadow_mc_entries)
    all_syms = sorted(all_syms_set)

    if not SMALLCAP_ENTRIES and not MIDCAP_ENTRIES and not shadow_sc_entries and not shadow_mc_entries:
        print("ℹ  No active holdings in fund_holdings.json.", file=sys.stderr)
        print("   Run: python tools/fund_daily.py --fresh --html", file=sys.stderr)
        print("   After you buy, add entries to data/fund_holdings.json.", file=sys.stderr)
        return

    if not args.json:
        print(f"Fetching closes for {len(all_syms)} symbols via yfinance...", file=sys.stderr)

    closes = fetch_closes(all_syms)

    # Fetch live signals from DB for active holdings
    active_syms = list(SMALLCAP_ENTRIES.keys()) + list(MIDCAP_ENTRIES.keys())
    signals_map = fetch_signals(active_syms)

    sc_positions = compute_positions(SMALLCAP_ENTRIES, SC_BUDGET, closes, signals_map) if SMALLCAP_ENTRIES else []
    mc_positions = compute_positions(MIDCAP_ENTRIES, MC_BUDGET, closes, signals_map)   if MIDCAP_ENTRIES else []

    sc_summary = fund_summary(sc_positions) if sc_positions else {"invested":0,"current":0,"pnl_rs":0,"pnl_pct":0,"n_positions":0,"n_winners":0,"n_losers":0}
    mc_summary = fund_summary(mc_positions) if mc_positions else {"invested":0,"current":0,"pnl_rs":0,"pnl_pct":0,"n_positions":0,"n_winners":0,"n_losers":0}

    combined_inv  = sc_summary["invested"]  + mc_summary["invested"]
    combined_curr = sc_summary["current"]   + mc_summary["current"]
    combined_pnl  = sc_summary["pnl_rs"]    + mc_summary["pnl_rs"]
    combined_pct  = combined_pnl / combined_inv * 100 if combined_inv else 0

    # Shadow portfolio
    sh_sc_positions = compute_positions(shadow_sc_entries, SC_BUDGET, closes) if shadow_sc_entries else []
    sh_mc_positions = compute_positions(shadow_mc_entries, MC_BUDGET, closes) if shadow_mc_entries else []
    sh_sc_summary   = fund_summary(sh_sc_positions) if sh_sc_positions else {}
    sh_mc_summary   = fund_summary(sh_mc_positions) if sh_mc_positions else {}

    if args.json:
        output = {
            "date": args.date,
            "smallcap": {"positions": sc_positions, "summary": sc_summary},
            "midcap":   {"positions": mc_positions, "summary": mc_summary},
            "combined": {
                "invested": round(combined_inv, 2),
                "current":  round(combined_curr, 2),
                "pnl_rs":   round(combined_pnl, 2),
                "pnl_pct":  round(combined_pct, 4),
            },
        }
        if has_shadow:
            sh_inv  = (sh_sc_summary.get("invested",0) + sh_mc_summary.get("invested",0))
            sh_curr = (sh_sc_summary.get("current",0)  + sh_mc_summary.get("current",0))
            sh_pnl  = (sh_sc_summary.get("pnl_rs",0)   + sh_mc_summary.get("pnl_rs",0))
            output["shadow"] = {
                "smallcap": {"positions": sh_sc_positions, "summary": sh_sc_summary},
                "midcap":   {"positions": sh_mc_positions, "summary": sh_mc_summary},
                "combined": {
                    "invested": round(sh_inv, 2),
                    "current":  round(sh_curr, 2),
                    "pnl_rs":   round(sh_pnl, 2),
                    "pnl_pct":  round(sh_pnl / sh_inv * 100, 4) if sh_inv else 0,
                },
            }
        print(json.dumps(output, indent=2))
        return

    n_sc_h = len(SMALLCAP_ENTRIES); n_mc_h = len(MIDCAP_ENTRIES)
    if sc_positions:
        print_table(f"SmallCap Super Performers ({n_sc_h} stocks · ₹{SC_BUDGET//1000}k)", sc_positions, sc_summary)
    if mc_positions:
        print_table(f"MidCap Leaders ({n_mc_h} stocks · ₹{MC_BUDGET//1000}k)", mc_positions, mc_summary)

    print(f"\n{'═'*60}")
    print(f"  COMBINED PORTFOLIO")
    print(f"  Invested : ₹{combined_inv:>12,.0f}")
    print(f"  Current  : ₹{combined_curr:>12,.0f}")
    print(f"  P&L      : ₹{combined_pnl:>+12,.0f}  ({combined_pct:>+.2f}%)")
    print(f"{'═'*60}")

    if has_shadow:
        print_table(
            "Shadow Portfolio — SC S2 Strategy (9 stocks · ₹2L · Entry Aug 15)",
            sh_sc_positions, sh_sc_summary
        )
        print_table(
            "Shadow Portfolio — MC S1 Strategy (15 stocks · ₹2L · Entry Aug 15)",
            sh_mc_positions, sh_mc_summary
        )
        sh_inv  = sh_sc_summary.get("invested",0) + sh_mc_summary.get("invested",0)
        sh_curr = sh_sc_summary.get("current",0)  + sh_mc_summary.get("current",0)
        sh_pnl  = sh_sc_summary.get("pnl_rs",0)   + sh_mc_summary.get("pnl_rs",0)
        sh_pct  = sh_pnl / sh_inv * 100 if sh_inv else 0
        print(f"\n{'═'*60}")
        print(f"  SHADOW COMBINED")
        print(f"  Invested : ₹{sh_inv:>12,.0f}")
        print(f"  Current  : ₹{sh_curr:>12,.0f}")
        print(f"  P&L      : ₹{sh_pnl:>+12,.0f}  ({sh_pct:>+.2f}%)")
        print(f"{'═'*60}")

    if args.report:
        out_dir = pathlib.Path(__file__).parent.parent / "reports" / "latest"
        out_dir.mkdir(parents=True, exist_ok=True)
        html = build_html_report(
            sc_positions, sc_summary,
            mc_positions, mc_summary,
            combined_inv, combined_curr, combined_pnl, combined_pct,
            sh_sc_positions, sh_sc_summary,
            sh_mc_positions, sh_mc_summary,
            has_shadow,
            args.date,
        )
        out = out_dir / f"fund_lab_{args.date}.html"
        out.write_text(html)
        # Also update the canonical latest
        (out_dir / "fund_lab.html").write_text(html)
        print(f"Saved: {out}", file=sys.stderr)
        print(f"Saved: {out_dir / 'fund_lab.html'}", file=sys.stderr)


if __name__ == "__main__":
    main()
