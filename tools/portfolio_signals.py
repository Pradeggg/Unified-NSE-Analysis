#!/usr/bin/env python3
"""
portfolio_signals.py — Agent Adda Daily Portfolio Signal Digest
================================================================
From August 2026 onwards, a position must pass BOTH gates to be held:

  Gate 1 — Technical (Weinstein):
    SC S2 : Stage 2 + RS > 70th-pct of SC universe
    MC S1 : Stage 2 only

  Gate 2 — Fundamental (from scores.fundamental_scores):
    enhanced_fund_score ≥ 65  (B-grade floor)
    Subcomponents: Earnings Quality, Sales Growth, Financial Strength,
                   Institutional Backing

  Combined signal:
    HOLD   — both gates pass
    WEAKEN — technical Stage 2 but RS slipping; fundamentals pass
    EXIT   — technical gate broken (Stage exited) OR fund score < 65
    REVIEW — (informational) technical ok, fund borderline 55–64

Usage:
  python tools/portfolio_signals.py           # terminal digest
  python tools/portfolio_signals.py --html    # save HTML to reports/latest/
  python tools/portfolio_signals.py --json    # JSON output
  python tools/portfolio_signals.py --live    # also fetch live yfinance prices
  python tools/portfolio_signals.py --no-shadow  # Aug fund only
"""

import argparse
import json
import pathlib
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras

ROOT = pathlib.Path(__file__).parent.parent

FUND_SCORE_MIN  = 65    # B-grade floor — hard gate
FUND_SCORE_WARN = 55    # below this → hard fail even if borderline

# ── PORTFOLIO DEFINITIONS ────────────────────────────────────────────────────

FUND_SC = {
    "SYRMA":       {"entry": 1424.70, "entry_date": "2026-08-08", "fund": "Aug SC"},
    "CPPLUS":      {"entry": 3708.70, "entry_date": "2026-08-08", "fund": "Aug SC"},
    "KARURVYSYA":  {"entry":  335.55, "entry_date": "2026-08-08", "fund": "Aug SC"},
    "SKYGOLD":     {"entry":  719.40, "entry_date": "2026-08-08", "fund": "Aug SC"},
    "RUBICON":     {"entry": 1553.20, "entry_date": "2026-08-08", "fund": "Aug SC"},
    "GLAND":       {"entry": 2601.00, "entry_date": "2026-08-08", "fund": "Aug SC"},
    "RRKABEL":     {"entry": 2759.50, "entry_date": "2026-08-08", "fund": "Aug SC"},
    "RAINBOW":     {"entry": 1556.70, "entry_date": "2026-08-08", "fund": "Aug SC"},
    "SANSERA":     {"entry": 3863.80, "entry_date": "2026-08-08", "fund": "Aug SC"},
}

FUND_MC = {
    "OFSS":        {"entry": 11890.00, "entry_date": "2026-08-10", "fund": "Aug MC"},
    "COFORGE":     {"entry":  1810.00, "entry_date": "2026-08-10", "fund": "Aug MC"},
    "NYKAA":       {"entry":   323.70, "entry_date": "2026-08-10", "fund": "Aug MC"},
    "LLOYDSME":    {"entry":  2052.80, "entry_date": "2026-08-10", "fund": "Aug MC"},
    "KALYANKJIL":  {"entry":   600.25, "entry_date": "2026-08-10", "fund": "Aug MC"},
    "GODREJPROP":  {"entry":  2108.40, "entry_date": "2026-08-10", "fund": "Aug MC"},
    "SONACOMS":    {"entry":   812.50, "entry_date": "2026-08-10", "fund": "Aug MC"},
    "PRESTIGE":    {"entry":  1589.00, "entry_date": "2026-08-10", "fund": "Aug MC"},
    "AUROPHARMA":  {"entry":  1648.00, "entry_date": "2026-08-10", "fund": "Aug MC"},
    "OBEROIRLTY":  {"entry":  1793.00, "entry_date": "2026-08-10", "fund": "Aug MC"},
    "TATATECH":    {"entry":   879.15, "entry_date": "2026-08-10", "fund": "Aug MC"},
    "BHARATFORG":  {"entry":  2093.10, "entry_date": "2026-08-10", "fund": "Aug MC"},
    "FEDERALBNK":  {"entry":   358.35, "entry_date": "2026-08-10", "fund": "Aug MC"},
    "POLYCAB":     {"entry":  9275.00, "entry_date": "2026-08-10", "fund": "Aug MC"},
    "HEROMOTOCO":  {"entry":  5860.00, "entry_date": "2026-08-10", "fund": "Aug MC"},
}

FUND_STRATEGY = {
    "Aug SC":    "SC_S2",
    "Shadow SC": "SC_S2",
    "Aug MC":    "MC_S1",
    "Shadow MC": "MC_S1",
}

# Combined signal priority (most urgent = 0)
SIGNAL_ORDER = {"EXIT": 0, "WEAKEN": 1, "HOLD": 2, "NO_DATA": 3}


# ── DATA LOAD ────────────────────────────────────────────────────────────────

def load_shadow() -> dict:
    wl_path = ROOT / "data" / "fund_watchlist.json"
    if not wl_path.exists():
        return {}
    with open(wl_path) as f:
        wl = json.load(f)
    result = {}
    for sym, v in wl.get("smallcap", {}).items():
        result[sym] = {**v, "fund": "Shadow SC"}
    for sym, v in wl.get("midcap", {}).items():
        result.setdefault(sym, {**v, "fund": "Shadow MC"})
    return result


def load_all_entries(include_shadow: bool = True) -> dict:
    entries = {}
    for sym, meta in {**FUND_SC, **FUND_MC}.items():
        entries[sym] = meta
    if include_shadow:
        for sym, meta in load_shadow().items():
            entries.setdefault(sym, meta)
    return entries


def compute_rs_p70(conn, cap: str) -> float:
    cur = conn.cursor()
    cur.execute("""
        SELECT COALESCE(CAST(relative_strength AS float), 0)
        FROM scores.stage_snapshots
        WHERE market_cap_cat = %s
          AND snapshot_date = (SELECT MAX(snapshot_date) FROM scores.stage_snapshots)
          AND relative_strength IS NOT NULL
    """, (cap,))
    vals = [r[0] for r in cur.fetchall()]
    return float(np.percentile(vals, 70)) if vals else 0.0


def fetch_snapshots(symbols: list[str], conn) -> tuple[dict, dict]:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    sym_list = "','".join(symbols)
    cur.execute(f"""
        SELECT DISTINCT snapshot_date FROM scores.stage_snapshots
        WHERE symbol IN ('{sym_list}')
        ORDER BY snapshot_date DESC LIMIT 2
    """)
    dates = [r["snapshot_date"] for r in cur.fetchall()]
    today_date = dates[0] if dates else None
    yest_date  = dates[1] if len(dates) > 1 else None

    def _fetch(dt):
        if dt is None:
            return {}
        cur.execute(f"""
            SELECT symbol, snapshot_date::text,
                   ROUND(price::numeric, 2)             AS price,
                   stage, trading_signal, trend_signal,
                   ROUND(rsi::numeric, 1)               AS rsi,
                   ROUND(relative_strength::numeric, 1) AS rs,
                   ROUND(technical_score::numeric, 1)   AS tech_score
            FROM scores.stage_snapshots
            WHERE symbol IN ('{sym_list}') AND snapshot_date = %s
        """, (dt,))
        return {r["symbol"]: dict(r) for r in cur.fetchall()}

    return _fetch(today_date), _fetch(yest_date)


def fetch_fundamental_scores(symbols: list[str], conn) -> dict:
    """Latest enhanced_fund_score + sub-components per symbol."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    sym_list = "','".join(symbols)
    cur.execute(f"""
        SELECT DISTINCT ON (symbol)
            symbol, score_date::text,
            ROUND(enhanced_fund_score, 1) AS fund_score,
            ROUND(earnings_quality, 1)    AS eq,
            ROUND(sales_growth, 1)        AS sg,
            ROUND(financial_strength, 1)  AS fs,
            ROUND(institutional_backing, 1) AS ib
        FROM scores.fundamental_scores
        WHERE symbol IN ('{sym_list}')
        ORDER BY symbol, score_date DESC
    """)
    return {r["symbol"]: dict(r) for r in cur.fetchall()}


def fetch_signal_log_latest(symbols: list[str]) -> dict:
    log_path = ROOT / "data" / "signal_log.csv"
    if not log_path.exists():
        return {}
    df = pd.read_csv(log_path, parse_dates=["date_issued"])
    df = df[df["symbol"].isin(symbols)]
    if df.empty:
        return {}
    latest = df.sort_values("date_issued").groupby("symbol").last().reset_index()
    return {
        row["symbol"]: {
            "log_date":  str(row["date_issued"].date()),
            "stop_loss": row.get("stop_loss"),
            "target_1":  row.get("target_1"),
            "target_2":  row.get("target_2"),
        }
        for _, row in latest.iterrows()
    }


def fetch_live_prices(symbols: list[str]) -> dict:
    try:
        import yfinance as yf
    except ImportError:
        return {}
    prices = {}
    for sym in symbols:
        try:
            hist = yf.Ticker(sym + ".NS").history(period="5d", interval="1d", auto_adjust=True)
            if len(hist) >= 2:
                prices[sym] = {
                    "close": round(float(hist["Close"].iloc[-1]), 2),
                    "prev":  round(float(hist["Close"].iloc[-2]), 2),
                    "date":  str(hist.index[-1].date()),
                }
        except Exception:
            pass
    return prices


# ── SIGNAL LOGIC ────────────────────────────────────────────────────────────

def fund_grade(score) -> str:
    if score is None: return "?"
    s = float(score)
    if s >= 80: return "A"
    if s >= 65: return "B"
    if s >= 50: return "C"
    return "F"


def combined_signal(snap: dict, fund_row: dict, fund_type: str,
                    rs_p70_sc: float) -> tuple[str, str, str]:
    """
    Returns (signal, tech_reason, fund_reason).

    Technical gate (SC_S2 / MC_S1):
      PASS   → Stage 2 (+ RS > p70 for SC)
      WEAKEN → Stage 2 but RS slipping (SC only)
      FAIL   → Not Stage 2

    Fundamental gate (from Aug 2026):
      PASS   → fund_score ≥ 65
      FAIL   → fund_score < 65

    Combined:
      HOLD   → both gates pass
      WEAKEN → tech WEAKEN + fund pass  (watch RS; fundamentals ok)
      EXIT   → tech fail  OR  fund fail
    """
    # ── Technical ──
    if not snap:
        return "NO_DATA", "not in snapshot", "—"

    stage  = snap.get("stage", "")
    rs     = float(snap.get("rs") or 0)
    is_s2  = stage == "STAGE_2"

    if fund_type == "SC_S2":
        if is_s2 and rs > rs_p70_sc:
            tech = "PASS";    tech_r = f"Stage 2  RS {rs:+.1f} > p70 {rs_p70_sc:.1f}"
        elif is_s2:
            tech = "WEAKEN";  tech_r = f"Stage 2  RS {rs:+.1f} ≤ p70 {rs_p70_sc:.1f}"
        else:
            tech = "FAIL";    tech_r = f"{stage} — exited Stage 2"
    else:  # MC_S1
        if is_s2:
            tech = "PASS";    tech_r = "Stage 2"
        else:
            tech = "FAIL";    tech_r = f"{stage} — exited Stage 2"

    # ── Fundamental ──
    fs = float(fund_row.get("fund_score") or 0) if fund_row else 0
    grade = fund_grade(fs)
    if not fund_row:
        fund = "UNKNOWN"; fund_r = "no fundamental data"
    elif fs >= FUND_SCORE_MIN:
        fund = "PASS";  fund_r = f"Fund {fs} [{grade}]  EQ:{fund_row.get('eq')} SG:{fund_row.get('sg')} FS:{fund_row.get('fs')}"
    else:
        fund = "FAIL";  fund_r = f"Fund {fs} [{grade}] < {FUND_SCORE_MIN}  EQ:{fund_row.get('eq')} SG:{fund_row.get('sg')} FS:{fund_row.get('fs')}"

    # ── Combined ──
    if tech == "FAIL" and fund == "FAIL":
        return "EXIT", tech_r, fund_r + " ← dual exit"
    if tech == "FAIL":
        return "EXIT", tech_r, fund_r
    if fund == "FAIL":
        return "EXIT", tech_r, fund_r + " ← fund gate"
    if tech == "WEAKEN":
        return "WEAKEN", tech_r, fund_r
    return "HOLD", tech_r, fund_r


# ── BUILD ROWS ───────────────────────────────────────────────────────────────

def build_rows(entries: dict, today_snap: dict, yest_snap: dict,
               fund_scores: dict, log: dict, prices: dict,
               rs_p70_sc: float) -> list[dict]:
    rows = []
    for sym, meta in entries.items():
        ts = today_snap.get(sym, {})
        ys = yest_snap.get(sym, {})
        fr = fund_scores.get(sym, {})
        lg = log.get(sym, {})
        px = prices.get(sym, {})

        fund_type = FUND_STRATEGY.get(meta.get("fund", ""), "MC_S1")

        signal,      tech_r, fund_r = combined_signal(ts, fr, fund_type, rs_p70_sc)
        signal_yest, _,      _      = combined_signal(ys, fr, fund_type, rs_p70_sc)
        changed = signal != signal_yest and bool(ys)

        close   = px.get("close") or (float(ts["price"]) if ts.get("price") else None)
        entry   = meta.get("entry", 0)
        pnl_pct = ((float(close) / float(entry)) - 1) * 100 if (close and entry) else None

        sl = lg.get("stop_loss")
        t1 = lg.get("target_1")
        sl_breach = bool(sl and close and float(close) < float(sl))
        t1_hit    = bool(t1 and close and float(close) >= float(t1))

        rows.append({
            "symbol":       sym,
            "fund":         meta.get("fund", ""),
            "entry":        entry,
            "entry_date":   meta.get("entry_date", ""),
            "close":        close,
            "pnl_pct":      round(pnl_pct, 2) if pnl_pct is not None else None,
            # combined
            "signal":       signal,
            "signal_yest":  signal_yest,
            "changed":      changed,
            "tech_reason":  tech_r,
            "fund_reason":  fund_r,
            # raw
            "stage":        ts.get("stage"),
            "rsi":          ts.get("rsi"),
            "rs":           ts.get("rs"),
            "tech_score":   ts.get("tech_score"),
            # fundamentals
            "fund_score":   float(fr.get("fund_score") or 0) if fr else None,
            "fund_grade":   fund_grade(fr.get("fund_score")) if fr else "?",
            "fund_eq":      fr.get("eq"),
            "fund_sg":      fr.get("sg"),
            "fund_fs":      fr.get("fs"),
            "fund_ib":      fr.get("ib"),
            "fund_date":    fr.get("score_date"),
            # supplementary
            "stop_loss":    lg.get("stop_loss"),
            "target_1":     t1,
            "sl_breach":    sl_breach,
            "t1_hit":       t1_hit,
            "in_db":        bool(ts),
            "snap_date":    ts.get("snapshot_date"),
        })

    rows.sort(key=lambda r: (SIGNAL_ORDER.get(r["signal"], 9), r["fund"], r["symbol"]))
    return rows


# ── TERMINAL OUTPUT ──────────────────────────────────────────────────────────

def print_digest(rows: list[dict], run_date: str, rs_p70_sc: float) -> None:
    W = 140
    sep = "─" * W
    print(f"\n{'═'*W}")
    print(f"  PORTFOLIO SIGNAL DIGEST — {run_date}")
    print(f"  Technical gate: Stage 2 (SC: RS > {rs_p70_sc:.1f})  |  Fundamental gate: score ≥ {FUND_SCORE_MIN}")
    print(f"{'═'*W}")
    print(f"  {'Symbol':<14} {'Fund':<10} {'Signal':<8} {'Stage':<8} "
          f"{'Entry':>9} {'Close':>9} {'P&L%':>7} "
          f"{'Fund':>5} {'Gr':>2} {'EQ':>5} {'SG':>5} {'FS':>5}  Tech Reason")
    print(f"  {sep}")

    cur_sig = None
    for r in rows:
        if r["signal"] != cur_sig:
            cur_sig = r["signal"]
            label = {
                "EXIT":    "🔴  EXIT — fails technical or fundamental gate",
                "WEAKEN":  "🟠  WEAKEN — Stage 2 intact, RS slipping; fundamentals ok",
                "HOLD":    "🟢  HOLD — both gates pass",
                "NO_DATA": "⚪  NO DATA",
            }.get(cur_sig, cur_sig)
            print(f"\n  ── {label} ──")

        pnl   = f"{r['pnl_pct']:>+6.2f}%" if r["pnl_pct"] is not None else "    N/A"
        close = f"{r['close']:>9.2f}"      if r["close"] else "       N/A"
        fs    = f"{r['fund_score']:>5.1f}" if r["fund_score"] else "    ?"
        chg   = "  ← CHANGED" if r["changed"] else ""
        extras = ""
        if r["sl_breach"]: extras += "  ⚠SL"
        if r["t1_hit"]:    extras += "  🎯T1"

        # Determine why it's exiting
        exit_tag = ""
        if r["signal"] == "EXIT":
            if "fund gate" in r["fund_reason"]: exit_tag = " [FUND]"
            elif "exited Stage" in r["tech_reason"]: exit_tag = " [TECH]"
            elif "dual" in r["fund_reason"]: exit_tag = " [BOTH]"

        print(f"  {r['symbol']:<14} {r['fund']:<10} {r['signal']:<8}{exit_tag:<7} "
              f"{(r['stage'] or '?'):<8} {r['entry']:>9.2f} {close} {pnl} "
              f"{fs} {r['fund_grade']:>2} {str(r['fund_eq'] or '?'):>5} "
              f"{str(r['fund_sg'] or '?'):>5} {str(r['fund_fs'] or '?'):>5}"
              f"  {r['tech_reason']}{chg}{extras}")

    print(f"\n  {sep}")
    holds   = sum(1 for r in rows if r["signal"] == "HOLD")
    weakens = sum(1 for r in rows if r["signal"] == "WEAKEN")
    exits   = sum(1 for r in rows if r["signal"] == "EXIT")
    fund_exits = sum(1 for r in rows if r["signal"] == "EXIT" and "fund gate" in r["fund_reason"])
    tech_exits = exits - fund_exits
    changes = sum(1 for r in rows if r["changed"])
    print(f"  HOLD: {holds}   WEAKEN: {weakens}   EXIT: {exits}  "
          f"(tech: {tech_exits}  fund: {fund_exits})  | Changes today: {changes}")
    missing = [r["symbol"] for r in rows if not r["in_db"]]
    if missing:
        print(f"  ⚪ Not in DB snapshot: {', '.join(missing)}")


# ── HTML OUTPUT ──────────────────────────────────────────────────────────────

def build_html(rows: list[dict], run_date: str, rs_p70_sc: float) -> str:
    exits   = [r for r in rows if r["signal"] == "EXIT"]
    weakens = [r for r in rows if r["signal"] == "WEAKEN"]
    holds   = [r for r in rows if r["signal"] == "HOLD"]
    changes = [r for r in rows if r["changed"]]
    fund_exits = [r for r in exits if "fund gate" in r["fund_reason"]]
    tech_exits = [r for r in exits if "fund gate" not in r["fund_reason"]]

    def fmt(v, pre="", suf="", dec=2, plus=False):
        if v is None: return "—"
        s = f"{float(v):.{dec}f}"
        if plus and float(v) > 0: s = "+" + s
        return pre + s + suf

    def grade_cls(g):
        return {"A":"g-a","B":"g-b","C":"g-c","F":"g-f"}.get(g,"g-na")

    def stage_cls(s):
        return {"STAGE_2":"s2","STAGE_1":"s1","STAGE_3":"s3","STAGE_4":"s4"}.get(s or "","sna")

    def exit_tag(r):
        if r["signal"] != "EXIT": return ""
        if "dual" in r["fund_reason"]: return '<span class="xt xt-both">TECH+FUND</span>'
        if "fund gate" in r["fund_reason"]: return '<span class="xt xt-fund">FUND</span>'
        return '<span class="xt xt-tech">TECH</span>'

    rows_html = ""
    cur_sig = None
    for r in rows:
        if r["signal"] != cur_sig:
            cur_sig = r["signal"]
            label, cls = {
                "EXIT":    ("🔴 EXIT — fails technical or fundamental gate", "sep-exit"),
                "WEAKEN":  ("🟠 WEAKEN — Stage 2 intact, RS slipping; fundamentals ok", "sep-weak"),
                "HOLD":    ("🟢 HOLD — both gates pass", "sep-hold"),
                "NO_DATA": ("⚪ No snapshot data", "sep-na"),
            }.get(cur_sig, (cur_sig, ""))
            rows_html += f'<tr class="group-sep {cls}"><td colspan="13">{label}</td></tr>\n'

        sig_cls = {"EXIT":"sig-exit","WEAKEN":"sig-weak","HOLD":"sig-hold"}.get(r["signal"],"")
        pnl_cls = "pos" if (r["pnl_pct"] or 0) >= 0 else "neg"
        chg_html = ' <span class="chg-chip">CHANGED</span>' if r["changed"] else ""
        extras = ""
        if r["sl_breach"]: extras += ' <span class="chip-sl">⚠SL</span>'
        if r["t1_hit"]:    extras += ' <span class="chip-t1">🎯T1</span>'

        rows_html += f"""<tr class="row-{r['signal'].lower()}">
  <td class="sym-col">{r['symbol']}{extras}</td>
  <td><span class="fund-chip fc-{r['fund'].replace(' ','-').lower()}">{r['fund']}</span></td>
  <td><span class="sig {sig_cls}">{r['signal']}{chg_html}</span> {exit_tag(r)}</td>
  <td><span class="stage {stage_cls(r['stage'])}">{(r['stage'] or '—').replace('STAGE_','S')}</span></td>
  <td class="num">{fmt(r['entry'],'₹')}</td>
  <td class="num">{fmt(r['close'],'₹') if r['close'] else '—'}</td>
  <td class="num {pnl_cls}">{fmt(r['pnl_pct'],suf='%',plus=True)}</td>
  <td class="num"><span class="{grade_cls(r['fund_grade'])}">{fmt(r['fund_score'],dec=1)}</span></td>
  <td class="num">{fmt(r['fund_eq'],dec=1)}</td>
  <td class="num">{fmt(r['fund_sg'],dec=1)}</td>
  <td class="num">{fmt(r['fund_fs'],dec=1)}</td>
  <td class="num">{fmt(r['rsi'],dec=1)}</td>
  <td class="reason">{r['tech_reason']}</td>
</tr>"""

    exit_banner = ""
    if exits:
        tech_part = " · ".join(f"<b>{r['symbol']}</b>" for r in tech_exits) if tech_exits else ""
        fund_part = " · ".join(f"<b>{r['symbol']}</b>" for r in fund_exits) if fund_exits else ""
        inner = ""
        if tech_part: inner += f'<span class="eb-section">Tech exit: {tech_part}</span>'
        if fund_part: inner += f'<span class="eb-section">Fund exit: {fund_part}</span>'
        exit_banner = f'<div class="exit-banner">⚠ Exit at next rebalance: {inner}</div>'

    change_banner = ""
    if changes:
        items = " · ".join(f"<b>{r['symbol']}</b> → {r['signal']}" for r in changes)
        change_banner = f'<div class="change-banner">Signal changes today: {items}</div>'

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Portfolio Signals — {run_date}</title>
<style>
:root{{--bg:#f6f8fa;--surface:#fff;--surface2:#f0f3f7;--border:#d0d7de;--text:#1a2233;--text2:#57606a;--text3:#8b949e;--win:#1a7f37;--loss:#cf222e;--shadow:0 1px 3px rgba(0,0,0,.08)}}
@media(prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#0d1117;--surface:#161b22;--surface2:#1c2128;--border:#30363d;--text:#e6edf3;--text2:#8b949e;--text3:#6e7681;--win:#3fb950;--loss:#f85149}}}}
:root[data-theme="dark"]{{--bg:#0d1117;--surface:#161b22;--surface2:#1c2128;--border:#30363d;--text:#e6edf3;--text2:#8b949e;--text3:#6e7681;--win:#3fb950;--loss:#f85149}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;font-size:13px;background:var(--bg);color:var(--text);padding:20px 24px;max-width:1400px;margin:0 auto}}
h1{{font-size:16px;font-weight:700;margin-bottom:3px}}
.sub{{font-size:11px;color:var(--text2);margin-bottom:14px}}
.gates{{display:flex;gap:12px;margin-bottom:14px;flex-wrap:wrap}}
.gate{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:8px 14px;box-shadow:var(--shadow);flex:1;min-width:200px}}
.gate-label{{font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:var(--text2);font-weight:600}}
.gate-val{{font-size:13px;font-weight:500;margin-top:3px}}
.stat-row{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}}
.stat{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:8px 14px;box-shadow:var(--shadow)}}
.stat-label{{font-size:10px;text-transform:uppercase;letter-spacing:.4px;color:var(--text2)}}
.stat-val{{font-size:19px;font-weight:700;line-height:1.2;font-variant-numeric:tabular-nums}}
.exit-banner{{background:rgba(207,34,46,.07);border:1px solid rgba(207,34,46,.25);border-radius:8px;padding:9px 14px;margin-bottom:10px;font-size:12px;color:var(--loss);display:flex;align-items:flex-start;gap:10px;flex-wrap:wrap}}
.eb-section{{display:flex;align-items:center;gap:5px;flex-wrap:wrap}}
.change-banner{{background:rgba(9,105,218,.07);border:1px solid rgba(9,105,218,.2);border-radius:8px;padding:9px 14px;margin-bottom:14px;font-size:12px;color:#0969da}}
.tbl-wrap{{overflow-x:auto;background:var(--surface);border:1px solid var(--border);border-radius:10px;box-shadow:var(--shadow)}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}}
thead th{{background:var(--surface2);color:var(--text2);font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;padding:8px 10px;border-bottom:1px solid var(--border);white-space:nowrap;text-align:left}}
thead th.num{{text-align:right}}
.fund-header{{border-left:2px solid var(--border)}}
tbody td{{padding:7px 10px;border-bottom:1px solid var(--border);font-size:12px;vertical-align:middle;white-space:nowrap}}
td.num{{text-align:right}}
td.reason{{white-space:normal;min-width:220px;color:var(--text2);font-size:11px}}
tbody tr:hover td{{background:var(--surface2)}}
tr.group-sep td{{padding:6px 10px;font-size:11px;font-weight:600;background:var(--surface2);border-top:2px solid var(--border);border-bottom:1px solid var(--border)}}
tr.sep-exit td{{color:var(--loss)}}
tr.sep-weak td{{color:#b35c00}}
tr.sep-hold td{{color:var(--win)}}
tr.row-exit td{{background:rgba(207,34,46,.03)}}
tr.row-weaken td{{background:rgba(217,119,6,.03)}}
.sym-col{{font-weight:600}}
.fund-chip{{display:inline-block;padding:1px 7px;border-radius:4px;font-size:10px;font-weight:600}}
.fc-aug-sc{{background:rgba(26,127,55,.1);color:#1a7f37}}
.fc-aug-mc{{background:rgba(9,105,218,.1);color:#0969da}}
.fc-shadow-sc,.fc-shadow-mc{{background:rgba(124,58,237,.1);color:#7c3aed}}
.sig{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700}}
.sig-hold{{color:var(--win);background:rgba(26,127,55,.1);border:1px solid rgba(26,127,55,.2)}}
.sig-weak{{color:#b35c00;background:rgba(217,119,6,.1);border:1px solid rgba(217,119,6,.2)}}
.sig-exit{{color:var(--loss);background:rgba(207,34,46,.12);border:1px solid rgba(207,34,46,.25)}}
.stage{{display:inline-block;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600}}
.s2{{color:#1a7f37;background:rgba(26,127,55,.1)}}
.s1{{color:#0969da;background:rgba(9,105,218,.1)}}
.s3,.s4{{color:var(--loss);background:rgba(207,34,46,.1)}}
.sna{{color:var(--text3);background:var(--surface2)}}
.pos{{color:var(--win);font-weight:600}}
.neg{{color:var(--loss);font-weight:600}}
/* fund grade colours */
.g-a{{color:#1a7f37;font-weight:700}}
.g-b{{color:#0969da;font-weight:600}}
.g-c{{color:#b35c00;font-weight:600}}
.g-f{{color:var(--loss);font-weight:700}}
.g-na{{color:var(--text3)}}
/* exit type tags */
.xt{{font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;margin-left:4px;vertical-align:middle}}
.xt-tech{{background:rgba(207,34,46,.15);color:var(--loss)}}
.xt-fund{{background:rgba(217,119,6,.15);color:#b35c00}}
.xt-both{{background:rgba(207,34,46,.2);color:var(--loss)}}
.chg-chip{{background:#dbeafe;color:#1d4ed8;border-radius:3px;font-size:9px;padding:1px 4px;font-weight:700;vertical-align:middle}}
.chip-sl{{font-size:10px;font-weight:700;padding:1px 5px;border-radius:3px;background:rgba(207,34,46,.15);color:var(--loss)}}
.chip-t1{{font-size:10px;font-weight:700;padding:1px 5px;border-radius:3px;background:rgba(26,127,55,.15);color:var(--win)}}
.fund-col-group{{border-left:2px solid var(--border)}}
.footer{{font-size:11px;color:var(--text3);margin-top:12px;text-align:right}}
</style></head><body>

<h1>Portfolio Signal Digest — Technical + Fundamental</h1>
<div class="sub">Run date: {run_date}</div>

<div class="gates">
  <div class="gate">
    <div class="gate-label">Gate 1 — Technical</div>
    <div class="gate-val">SC: Stage 2 + RS &gt; {rs_p70_sc:.1f} (70th pct) · MC: Stage 2 only</div>
  </div>
  <div class="gate">
    <div class="gate-label">Gate 2 — Fundamental (from Aug 2026)</div>
    <div class="gate-val">Enhanced Fund Score ≥ {FUND_SCORE_MIN} (B-grade floor) · sub-components: EQ · SG · FS · IB</div>
  </div>
</div>

<div class="stat-row">
  <div class="stat"><div class="stat-label">Hold</div><div class="stat-val" style="color:var(--win)">{len(holds)}</div></div>
  <div class="stat"><div class="stat-label">Weaken</div><div class="stat-val" style="color:#b35c00">{len(weakens)}</div></div>
  <div class="stat"><div class="stat-label">Exit</div><div class="stat-val" style="color:var(--loss)">{len(exits)}</div></div>
  <div class="stat"><div class="stat-label">— Tech gate</div><div class="stat-val">{len(tech_exits)}</div></div>
  <div class="stat"><div class="stat-label">— Fund gate</div><div class="stat-val" style="color:#b35c00">{len(fund_exits)}</div></div>
  <div class="stat"><div class="stat-label">Changes</div><div class="stat-val">{len(changes)}</div></div>
</div>

{exit_banner}{change_banner}

<div class="tbl-wrap"><table>
<thead><tr>
  <th>Symbol</th><th>Fund</th><th>Signal</th><th>Stage</th>
  <th class="num">Entry ₹</th><th class="num">Close ₹</th><th class="num">P&amp;L %</th>
  <th class="num fund-header" title="Enhanced Fund Score">FScore</th>
  <th class="num" title="Earnings Quality">EQ</th>
  <th class="num" title="Sales Growth">SG</th>
  <th class="num" title="Financial Strength">FS</th>
  <th class="num">RSI</th>
  <th>Technical Reason</th>
</tr></thead>
<tbody>{rows_html}</tbody>
</table></div>
<div class="footer">Agent Adda · scores.stage_snapshots + scores.fundamental_scores · {run_date}</div>
</body></html>"""


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Portfolio Signal Digest (technical + fundamental)")
    parser.add_argument("--html",      action="store_true", help="Save HTML to reports/latest/")
    parser.add_argument("--json",      action="store_true", help="JSON output")
    parser.add_argument("--live",      action="store_true", help="Fetch live prices via yfinance")
    parser.add_argument("--no-shadow", action="store_true", help="Aug fund only")
    args = parser.parse_args()

    run_date = str(date.today())
    entries  = load_all_entries(include_shadow=not args.no_shadow)
    symbols  = sorted(entries.keys())

    print(f"Checking {len(symbols)} positions — technical + fundamental gates…", file=sys.stderr)

    conn = psycopg2.connect(dbname="nse_market", user="pgorai", host="localhost")
    rs_p70_sc    = compute_rs_p70(conn, "SMALL_CAP")
    today_s, yesterday_s = fetch_snapshots(symbols, conn)
    fund_scores  = fetch_fundamental_scores(symbols, conn)
    conn.close()

    log_data = fetch_signal_log_latest(symbols)
    prices   = fetch_live_prices(symbols) if args.live else {}

    rows = build_rows(entries, today_s, yesterday_s, fund_scores,
                      log_data, prices, rs_p70_sc)

    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return

    if args.html:
        html = build_html(rows, run_date, rs_p70_sc)
        out  = ROOT / "reports" / "latest" / f"portfolio_signals_{run_date.replace('-','')}.html"
        out.write_text(html)
        print(f"Saved: {out}", file=sys.stderr)

    print_digest(rows, run_date, rs_p70_sc)


if __name__ == "__main__":
    main()
