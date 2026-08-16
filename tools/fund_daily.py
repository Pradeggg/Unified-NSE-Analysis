#!/usr/bin/env python3
"""
fund_daily.py — Agent Adda Fund Daily Dashboard
================================================
One tool, two views, run every trading day after market close (~3:45 PM IST).

  SIGNALS   (daily)  : Are current positions still passing technical + fundamental gates?
  REBALANCE (weekly) : If we ran the universe scan today, what would change?
                       — Rebalance executes every Monday.

Usage:
  python tools/fund_daily.py            # terminal output
  python tools/fund_daily.py --html     # save HTML to reports/latest/
  python tools/fund_daily.py --rebalance # force rebalance view regardless of day
  python tools/fund_daily.py --no-shadow # Aug funds only
"""

import argparse
import json
import pathlib
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras

import csv as _csv

ROOT = pathlib.Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.fund_capital_policy import (  # noqa: E402
    CapitalPolicy,
    ExposureBook,
    apply_size_to_row,
    infer_stop,
    load_capital_policy,
    size_fresh_row,
)

# Shared capital policy — budgets, slots, and risk/sector caps.
_POLICY: CapitalPolicy = load_capital_policy()

# ── COMPANY NAME LOOKUP ───────────────────────────────────────────────────────
_COMPANY_NAMES: dict[str, str] = {}

def _load_company_names() -> dict[str, str]:
    """Load symbol → company name from NSE mcap CSV (mcap*.csv in project root)."""
    import glob
    mcap_files = sorted(glob.glob(str(ROOT / "mcap*.csv")), reverse=True)
    if not mcap_files:
        return {}
    names: dict[str, str] = {}
    with open(mcap_files[0], errors="ignore") as f:
        for row in _csv.DictReader(f):
            sym = (row.get("Symbol") or "").strip()
            name = (row.get("Security Name") or "").strip()
            if sym and name:
                names[sym] = name
    return names

def company_name(symbol: str) -> str:
    """Return the full company name for an NSE symbol, or the symbol if not found."""
    global _COMPANY_NAMES
    if not _COMPANY_NAMES:
        _COMPANY_NAMES = _load_company_names()
    return _COMPANY_NAMES.get(symbol, symbol)


# ── CONSTANTS ─────────────────────────────────────────────────────────────────

SC_N           = _POLICY.slots_sc
MC_N           = _POLICY.slots_mc
FUND_SCORE_MIN = _POLICY.fund_score_min
WATCH_N        = _POLICY.watch_n
NIFTY_MC150    = "NIFTY MIDCAP 150"

# ── PORTFOLIO DEFINITIONS — loaded from data/fund_holdings.json ───────────────

HOLDINGS_PATH = ROOT / "data" / "fund_holdings.json"

def load_holdings() -> tuple[dict, dict]:
    """
    Load SC and MC active holdings from data/fund_holdings.json.
    Returns (aug_sc, aug_mc) each as {symbol: {entry, entry_date, fund}}.
    If the file is missing or a sleeve is empty, returns {}.
    """
    if not HOLDINGS_PATH.exists():
        return {}, {}
    with open(HOLDINGS_PATH) as f:
        data = json.load(f)
    sc = {sym: {**v, "fund": v.get("fund", "Aug SC")}
          for sym, v in data.get("smallcap", {}).items()}
    mc = {sym: {**v, "fund": v.get("fund", "Aug MC")}
          for sym, v in data.get("midcap", {}).items()}
    return sc, mc


# Thin aliases kept for FUND_STRATEGY / FUND_BUDGETS references below
AUG_SC: dict = {}   # populated at runtime from load_holdings()
AUG_MC: dict = {}   # populated at runtime from load_holdings()

FUND_STRATEGY = {
    "Aug SC":    "SC_S2",
    "Shadow SC": "SC_S2",
    "Aug MC":    "MC_S1",
    "Shadow MC": "MC_S1",
}


# ── DATE HELPERS ─────────────────────────────────────────────────────────────

def next_monday(from_date: date) -> date:
    days = (0 - from_date.weekday()) % 7  # Monday=0
    return from_date + timedelta(days=days if days > 0 else 7)

def prev_monday(from_date: date) -> date:
    days = (from_date.weekday() - 0) % 7
    return from_date - timedelta(days=days if days > 0 else 7)

def is_monday(d: date) -> bool:
    return d.weekday() == 0


# ── HELPERS ───────────────────────────────────────────────────────────────────

def fund_grade(score) -> str:
    if score is None: return "?"
    s = float(score)
    if s >= 80: return "A"
    if s >= 65: return "B"
    if s >= 50: return "C"
    return "F"

def fmt(v, dec=1, plus=False, pre="", suf="") -> str:
    if v is None: return "—"
    s = f"{float(v):.{dec}f}"
    if plus and float(v) > 0: s = "+" + s
    return pre + s + suf

def signal_sort(sig: str) -> int:
    return {"EXIT": 0, "WEAKEN": 1, "HOLD": 2, "NO_DATA": 3}.get(sig, 9)


# ── DATA LOADERS ─────────────────────────────────────────────────────────────

def load_shadow() -> tuple[dict, dict]:
    wl = ROOT / "data" / "fund_watchlist.json"
    if not wl.exists():
        return {}, {}
    with open(wl) as f:
        data = json.load(f)
    sc = {sym: {**v, "fund": "Shadow SC"} for sym, v in data.get("smallcap", {}).items()}
    mc = {sym: {**v, "fund": "Shadow MC"} for sym, v in data.get("midcap", {}).items()}
    return sc, mc

def load_nifty_mc150() -> set:
    mapping = ROOT / "data" / "index_stock_mapping.csv"
    if not mapping.exists():
        return set()
    df = pd.read_csv(mapping)
    return set(df[df["INDEX_NAME"] == NIFTY_MC150]["STOCK_SYMBOL"].tolist())

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


# ── DAILY SIGNALS ─────────────────────────────────────────────────────────────

def fetch_snapshots(symbols: list, conn) -> tuple[dict, dict]:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    sym_list = "','".join(symbols)
    cur.execute(f"""
        SELECT DISTINCT snapshot_date FROM scores.stage_snapshots
        WHERE symbol IN ('{sym_list}') ORDER BY snapshot_date DESC LIMIT 2
    """)
    dates = [r["snapshot_date"] for r in cur.fetchall()]
    today_d = dates[0] if dates else None
    yest_d  = dates[1] if len(dates) > 1 else None

    def _fetch(dt):
        if dt is None: return {}
        cur.execute(f"""
            SELECT symbol, snapshot_date::text,
                   ROUND(price::numeric, 2) AS price, stage,
                   ROUND(rsi::numeric, 1) AS rsi,
                   ROUND(relative_strength::numeric, 1) AS rs,
                   ROUND(technical_score::numeric, 1) AS tech_score
            FROM scores.stage_snapshots
            WHERE symbol IN ('{sym_list}') AND snapshot_date = %s
        """, (dt,))
        return {r["symbol"]: dict(r) for r in cur.fetchall()}

    return _fetch(today_d), _fetch(yest_d)


def fetch_fundamental_scores(symbols: list, conn) -> dict:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    sym_list = "','".join(symbols)
    cur.execute(f"""
        SELECT DISTINCT ON (symbol) symbol, score_date::text,
               ROUND(enhanced_fund_score, 1) AS fund_score,
               ROUND(earnings_quality, 1) AS eq,
               ROUND(sales_growth, 1) AS sg,
               ROUND(financial_strength, 1) AS fs,
               ROUND(institutional_backing, 1) AS ib
        FROM scores.fundamental_scores
        WHERE symbol IN ('{sym_list}')
        ORDER BY symbol, score_date DESC
    """)
    return {r["symbol"]: dict(r) for r in cur.fetchall()}


def combined_signal(snap: dict, fund_row: dict, fund_type: str,
                    rs_p70_sc: float) -> tuple[str, str, str]:
    """Returns (signal, tech_reason, fund_reason)."""
    if not snap:
        return "NO_DATA", "not in snapshot", "—"

    stage = snap.get("stage", "")
    rs    = float(snap.get("rs") or 0)
    is_s2 = stage == "STAGE_2"

    if fund_type == "SC_S2":
        if is_s2 and rs > rs_p70_sc:
            tech = "PASS";   tech_r = f"Stage 2  RS {rs:+.1f} > p70 {rs_p70_sc:.1f}"
        elif is_s2:
            tech = "WEAKEN"; tech_r = f"Stage 2  RS {rs:+.1f} ≤ p70 {rs_p70_sc:.1f}"
        else:
            tech = "FAIL";   tech_r = f"{stage} — exited Stage 2"
    else:
        if is_s2:
            tech = "PASS";   tech_r = "Stage 2"
        else:
            tech = "FAIL";   tech_r = f"{stage} — exited Stage 2"

    fs = float(fund_row.get("fund_score") or 0) if fund_row else 0
    grade = fund_grade(fs)
    if not fund_row:
        fund = "UNKNOWN"; fund_r = "no fundamental data"
    elif fs >= FUND_SCORE_MIN:
        fund = "PASS"; fund_r = f"Fund {fs} [{grade}]"
    else:
        fund = "FAIL"; fund_r = f"Fund {fs} [{grade}] < {FUND_SCORE_MIN}"

    if tech == "FAIL":
        return "EXIT", tech_r, fund_r
    if fund == "FAIL":
        return "EXIT", tech_r, fund_r + " ← fund gate"
    if tech == "WEAKEN":
        return "WEAKEN", tech_r, fund_r
    return "HOLD", tech_r, fund_r


def build_signal_rows(entries: dict, today_s: dict, yest_s: dict,
                      fund_scores: dict, rs_p70_sc: float) -> list[dict]:
    rows = []
    for sym, meta in entries.items():
        ts = today_s.get(sym, {})
        ys = yest_s.get(sym, {})
        fr = fund_scores.get(sym, {})
        fund_type = FUND_STRATEGY.get(meta.get("fund", ""), "MC_S1")

        sig,  tech_r, fund_r = combined_signal(ts, fr, fund_type, rs_p70_sc)
        sig_y, _, _           = combined_signal(ys, fr, fund_type, rs_p70_sc)

        close = float(ts["price"]) if ts.get("price") else None
        entry = meta.get("entry", 0)
        pnl   = ((close / float(entry)) - 1) * 100 if (close and entry) else None

        rows.append({
            "symbol":      sym,
            "fund":        meta.get("fund", ""),
            "entry":       entry,
            "close":       close,
            "pnl_pct":     round(pnl, 2) if pnl is not None else None,
            "signal":      sig,
            "signal_yest": sig_y,
            "changed":     sig != sig_y and bool(ys),
            "tech_reason": tech_r,
            "fund_reason": fund_r,
            "stage":       ts.get("stage"),
            "rsi":         ts.get("rsi"),
            "rs":          ts.get("rs"),
            "tech_score":  ts.get("tech_score"),
            "fund_score":  float(fr.get("fund_score") or 0) if fr else None,
            "fund_grade":  fund_grade(fr.get("fund_score")) if fr else "?",
            "eq":          fr.get("eq"),
            "sg":          fr.get("sg"),
            "fs":          fr.get("fs"),
            "in_db":       bool(ts),
        })

    rows.sort(key=lambda r: (signal_sort(r["signal"]), r["fund"], r["symbol"]))
    return rows


# ── REBALANCE (weekly) ────────────────────────────────────────────────────────

def fetch_universe(conn, cap: str, rs_p70: float, mc150_syms: set) -> list[dict]:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if cap == "SMALL_CAP":
        where_cap = "s.market_cap_cat = 'SMALL_CAP'"
    else:
        sym_list = "','".join(sorted(mc150_syms))
        where_cap = f"s.symbol IN ('{sym_list}')"

    cur.execute(f"""
        SELECT s.symbol, s.company_name, s.market_cap_cat, s.sector,
               ROUND(s.price::numeric, 2) AS price, s.stage,
               ROUND(s.rsi::numeric, 1) AS rsi,
               ROUND(COALESCE(CAST(s.relative_strength AS float), 0)::numeric, 1) AS rs,
               ROUND(s.technical_score::numeric, 1) AS tech_score,
               COALESCE(s.trading_signal, 'HOLD')  AS trading_signal,
               COALESCE(s.trend_signal,   'UNKNOWN') AS trend_signal,
               COALESCE(s.supertrend_state,'UNKNOWN') AS supertrend_state,
               ROUND(s.supertrend_value::numeric, 2) AS supertrend_value
        FROM scores.stage_snapshots s
        WHERE {where_cap}
          AND s.snapshot_date = (SELECT MAX(snapshot_date) FROM scores.stage_snapshots)
          AND s.stage = 'STAGE_2'
          AND s.technical_score IS NOT NULL
        ORDER BY s.technical_score DESC NULLS LAST
    """)
    raw = {r["symbol"]: dict(r) for r in cur.fetchall()}
    if not raw:
        return []

    sym_list = "','".join(raw.keys())
    cur.execute(f"""
        SELECT DISTINCT ON (symbol) symbol,
               ROUND(enhanced_fund_score, 1) AS fund_score,
               ROUND(earnings_quality, 1) AS eq,
               ROUND(sales_growth, 1) AS sg,
               ROUND(financial_strength, 1) AS fs
        FROM scores.fundamental_scores
        WHERE symbol IN ('{sym_list}')
        ORDER BY symbol, score_date DESC
    """)
    fd_map = {r["symbol"]: dict(r) for r in cur.fetchall()}

    # SMA50 is the preferred structure stop when it sits below last price.
    sma_map: dict[str, float] = {}
    try:
        cur.execute(f"""
            SELECT DISTINCT ON (symbol) symbol,
                   ROUND(sma_50::numeric, 2) AS sma50
            FROM scores.ma_breadth
            WHERE symbol IN ('{sym_list}')
              AND sma_50 IS NOT NULL
            ORDER BY symbol, snapshot_date DESC
        """)
        sma_map = {r["symbol"]: float(r["sma50"]) for r in cur.fetchall() if r.get("sma50")}
    except Exception as exc:
        print(f"Warning: could not load SMA50 stops: {exc}", file=sys.stderr)
        conn.rollback()

    universe = []
    for sym, snap in raw.items():
        fd = fd_map.get(sym, {})
        fs  = float(fd.get("fund_score") or 0)
        rs  = float(snap.get("rs") or 0)
        ts  = (snap.get("trading_signal")   or "HOLD").upper()
        tr  = (snap.get("trend_signal")     or "UNKNOWN").upper()
        st  = (snap.get("supertrend_state") or "UNKNOWN").upper()

        rs_pass     = (rs > rs_p70) if cap == "SMALL_CAP" else True
        fund_pass   = fs >= FUND_SCORE_MIN
        darvas_pass = ts in ("BUY", "STRONG_BUY")
        trend_pass  = tr in ("STRONG_BULLISH", "BULLISH") and st == "BULLISH"

        universe.append({
            **snap,
            "sector":      (snap.get("sector") or "").strip(),
            "sma50":       sma_map.get(sym),
            "fund_score":  fs,
            "fund_grade":  fund_grade(fs),
            "eq":          fd.get("eq"),
            "sg":          fd.get("sg"),
            "fs_sub":      fd.get("fs"),
            "rs_pass":     rs_pass,
            "fund_pass":   fund_pass,
            "darvas_pass": darvas_pass,
            "trend_pass":  trend_pass,
            "both_pass":   rs_pass and fund_pass and darvas_pass and trend_pass,
        })
    universe.sort(key=lambda r: float(r.get("tech_score") or 0), reverse=True)
    return universe


def fetch_dropped_info(conn, symbols: set) -> dict:
    if not symbols: return {}
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    sym_list = "','".join(symbols)
    cur.execute(f"""
        SELECT symbol, stage, market_cap_cat,
               ROUND(COALESCE(CAST(relative_strength AS float), 0)::numeric, 1) AS rs,
               ROUND(technical_score::numeric, 1) AS tech_score
        FROM scores.stage_snapshots
        WHERE symbol IN ('{sym_list}')
          AND snapshot_date = (SELECT MAX(snapshot_date) FROM scores.stage_snapshots)
    """)
    return {r["symbol"]: dict(r) for r in cur.fetchall()}


def classify_rebalance(holdings: set, universe: list, n: int,
                       conn, cap: str, rs_p70: float) -> dict:
    u_map   = {r["symbol"]: r for r in universe}
    passing = [r for r in universe if r["both_pass"]]
    top_n   = passing[:n]
    watch   = passing[n : n + WATCH_N]
    top_n_set = {r["symbol"] for r in top_n}
    u_set   = set(u_map.keys())

    not_in_universe = holdings - u_set
    dropped_info = fetch_dropped_info(conn, not_in_universe)

    holds, drops = [], []

    for sym in sorted(holdings):
        if sym not in u_set:
            info    = dropped_info.get(sym, {})
            stage   = info.get("stage", "NOT_IN_DB")
            cur_cap = info.get("market_cap_cat", "?")
            if stage == "STAGE_2":
                drops.append({"symbol": sym, "drop_reason": "GRAD", "stage": stage,
                               "detail": f"Stage 2 ✓ but now {cur_cap} — graduated",
                               "tech_score": info.get("tech_score"), "rs": info.get("rs"),
                               "fund_score": None, "fund_grade": "?"})
            else:
                drops.append({"symbol": sym, "drop_reason": "TECH", "stage": stage,
                               "detail": f"{stage} — exited Stage 2" if stage not in ("NOT_IN_DB","") else "Not in snapshot",
                               "tech_score": info.get("tech_score"), "rs": info.get("rs"),
                               "fund_score": None, "fund_grade": "?"})
            continue

        snap = u_map[sym]
        if not snap["rs_pass"]:
            drops.append({**snap, "drop_reason": "RS",
                          "detail": f"RS {snap['rs']:+.1f} ≤ p70 {rs_p70:.1f}"})
        elif not snap["fund_pass"]:
            drops.append({**snap, "drop_reason": "FUND",
                          "detail": f"Fund {snap['fund_score']:.1f} < {FUND_SCORE_MIN}"})
        elif sym in top_n_set:
            holds.append({**snap, "action": "HOLD"})
        else:
            drops.append({**snap, "drop_reason": "RANK",
                          "detail": f"Ranked out (TechScore {snap['tech_score']})"})

    adds = [r for r in top_n if r["symbol"] not in holdings]
    return {"holds": holds, "drops": drops, "adds": adds, "watch": watch,
            "top_n": top_n, "passing": passing}


# ── TERMINAL OUTPUT ───────────────────────────────────────────────────────────

SIG_ICON = {"HOLD": "🟢", "WEAKEN": "🟠", "EXIT": "🔴", "NO_DATA": "⚪"}
DROP_LABEL = {"TECH": "🔴 TECH", "GRAD": "🟣 GRAD", "RS": "🟠 RS  ",
              "FUND": "🟡 FUND", "RANK": "🔵 RANK"}

def print_signals(rows: list, rs_p70: float, run_date: str) -> None:
    W = 140
    print(f"\n{'═'*W}")
    print(f"  DAILY SIGNALS — {run_date}  ·  SC RS p70 = {rs_p70:.1f}  ·  Fund gate ≥ {FUND_SCORE_MIN}")
    print(f"{'═'*W}")
    print(f"  {'Symbol':<14} {'Fund':<10} {'Signal':<8} {'Stage':<8} "
          f"{'Entry':>9} {'Close':>9} {'P&L%':>7} {'Fund':>5} {'Gr':>2}  Tech Reason")

    cur_sig = None
    for r in rows:
        if r["signal"] != cur_sig:
            cur_sig = r["signal"]
            icons = {"EXIT": "🔴 EXIT", "WEAKEN": "🟠 WEAKEN", "HOLD": "🟢 HOLD", "NO_DATA": "⚪ NO_DATA"}
            print(f"\n  ── {icons.get(cur_sig,cur_sig)} ──")
        pnl   = f"{r['pnl_pct']:>+6.2f}%" if r["pnl_pct"] is not None else "    N/A"
        close = f"{r['close']:>9.2f}"      if r["close"] else "       N/A"
        fs    = f"{r['fund_score']:>5.1f}" if r["fund_score"] else "    ?"
        chg   = "  ← CHANGED" if r["changed"] else ""
        tag   = ""
        if r["signal"] == "EXIT":
            if "fund gate" in r["fund_reason"]: tag = " [FUND]"
            else: tag = " [TECH]"
        print(f"  {r['symbol']:<14} {r['fund']:<10} {r['signal']:<8}{tag:<7} "
              f"{(r['stage'] or '?'):<8} {r['entry']:>9.2f} {close} {pnl} "
              f"{fs} {r['fund_grade']:>2}  {r['tech_reason']}{chg}")

    exits   = sum(1 for r in rows if r["signal"] == "EXIT")
    weakens = sum(1 for r in rows if r["signal"] == "WEAKEN")
    holds   = sum(1 for r in rows if r["signal"] == "HOLD")
    changes = sum(1 for r in rows if r["changed"])
    print(f"\n  HOLD {holds}  WEAKEN {weakens}  EXIT {exits}  (signals changed today: {changes})")


def print_rebalance(name: str, result: dict, rs_p70: float, cap: str, n: int) -> None:
    W = 130
    print(f"\n{'─'*W}")
    print(f"  {name}  ·  {len(result['passing'])} stocks pass both gates  →  top {n}")
    for kind, label, items in [
        ("HOLD", "HOLD", result["holds"]),
        ("ADD",  "ADD",  result["adds"]),
    ]:
        if items:
            print(f"\n  {'🟢' if kind=='HOLD' else '🔵'} {label} ({len(items)}):")
            for r in items:
                rank = result["top_n"].index(r) + 1 if kind == "ADD" else ""
                rank_s = f"#{rank}" if rank else ""
                print(f"    {r['symbol']:<14} {rank_s:<5} TechSc {fmt(r.get('tech_score'))}  "
                      f"RS {fmt(r.get('rs'), plus=True)}  Fund {fmt(r.get('fund_score'))} [{r.get('fund_grade','?')}]")
    if result["drops"]:
        print(f"\n  🔻 DROP ({len(result['drops'])}):")
        for r in result["drops"]:
            lbl = DROP_LABEL.get(r.get("drop_reason",""), r.get("drop_reason",""))
            print(f"    {r['symbol']:<14} {lbl}  {r.get('detail','')}")
    if result["watch"]:
        print(f"\n  👁 WATCH (next {WATCH_N} after top {n}):")
        for i, r in enumerate(result["watch"], start=n+1):
            print(f"    #{i:<3} {r['symbol']:<14} TechSc {fmt(r.get('tech_score'))}  "
                  f"RS {fmt(r.get('rs'), plus=True)}  Fund {fmt(r.get('fund_score'))} [{r.get('fund_grade','?')}]")
    nc = len(result["adds"])
    print(f"\n  Changes: {nc} in / {len(result['drops'])} out  |  Holds: {len(result['holds'])} / {n}")


# ── TRADE EXECUTION LIST ──────────────────────────────────────────────────────

FUND_BUDGETS = {
    "Aug SC": (_POLICY.budget_sc, SC_N), "Shadow SC": (_POLICY.budget_sc, SC_N),
    "Aug MC": (_POLICY.budget_mc, MC_N), "Shadow MC": (_POLICY.budget_mc, MC_N),
}

def _fund_budget(fname: str, n: int | None = None) -> tuple[float, int]:
    """Look up sleeve budget from the shared policy, with a name-based fallback."""
    if fname in FUND_BUDGETS:
        return FUND_BUDGETS[fname]
    budget = _POLICY.budget_sc if "SC" in fname else _POLICY.budget_mc
    slots = _POLICY.slots_sc if "SC" in fname else _POLICY.slots_mc
    return budget, n if n is not None else slots

# Canonical short name from rebalance fund name
def _fname(name: str) -> str:
    for k in FUND_BUDGETS:
        if k in name: return k
    return name


def build_trade_list(signal_rows: list, rebalance_funds: list,
                     next_reb: date) -> dict:
    """
    Translate signals + rebalance view into prioritised, sized trade orders.

    Priority:
      1. SELL NOW        — EXIT [TECH]: Stage 2 broken, act immediately
      2. SELL at rebalance — all DROP categories on rebalance day (Monday)
      3. BUY  at rebalance — ADD entries with quantity + estimated cost
      4. WATCH           — WEAKEN signals, no order yet
    """
    sell_now, sell_reb, buy_reb, watch = [], [], [], []

    # ── From daily signals ──
    for r in signal_rows:
        if r["signal"] == "EXIT":
            is_tech = "fund gate" not in r["fund_reason"]
            entry = {
                "symbol":    r["symbol"],
                "fund":      r["fund"],
                "reason":    r["tech_reason"],
                "detail":    r["fund_reason"],
                "entry":     r["entry"],
                "close":     r["close"],
                "pnl_pct":   r["pnl_pct"],
                "stage":     r["stage"],
                "exit_type": "TECH" if is_tech else "FUND",
            }
            if is_tech:
                sell_now.append(entry)    # Stage 2 broken → sell immediately
            # Fund gate exits will also appear in rebalance drops — captured below

        elif r["signal"] == "WEAKEN":
            watch.append({
                "symbol": r["symbol"],
                "fund":   r["fund"],
                "reason": r["tech_reason"],
                "note":   "RS slipping — holds until rebalance; will be dropped if still weak",
            })

    # ── From rebalance view ──
    for fd in rebalance_funds:
        fname  = _fname(fd["name"])
        result = fd["result"]
        n      = fd["n"]
        budget, _ = _fund_budget(fname, n)
        alloc_per = budget / n          # equal-weight per position

        # Sells at rebalance
        for drop in result["drops"]:
            # Skip if already in sell_now list (same stock, TECH reason)
            already_now = any(s["symbol"] == drop["symbol"] and s["fund"] == fname
                              for s in sell_now)
            if not already_now:
                sell_reb.append({
                    "symbol":      drop["symbol"],
                    "fund":        fname,
                    "drop_reason": drop.get("drop_reason", ""),
                    "detail":      drop.get("detail", ""),
                    "stage":       drop.get("stage", ""),
                    "pnl_pct":     None,  # filled below if in signal_rows
                })

        # Buys at rebalance — sized
        for add_r in result["adds"]:
            rank  = result["top_n"].index(add_r) + 1
            price = float(add_r.get("price") or 0)
            qty   = int(alloc_per / price) if price > 0 else 0
            buy_reb.append({
                "symbol":     add_r["symbol"],
                "fund":       fname,
                "rank":       rank,
                "price":      round(price, 2),
                "alloc":      round(alloc_per),
                "qty":        qty,
                "est_cost":   round(qty * price),
                "shortfall":  round(alloc_per - qty * price) if qty else round(alloc_per),
                "tech_score": add_r.get("tech_score"),
                "rs":         add_r.get("rs"),
                "fund_score": add_r.get("fund_score"),
                "fund_grade": add_r.get("fund_grade"),
            })

    # Fill P&L for rebalance sells from signal rows
    sig_map = {r["symbol"]: r for r in signal_rows}
    for s in sell_reb:
        sr = sig_map.get(s["symbol"])
        if sr:
            s["pnl_pct"] = sr.get("pnl_pct")
            s["entry"]   = sr.get("entry")
            s["close"]   = sr.get("close")

    # Sort buys: by fund then rank
    buy_reb.sort(key=lambda r: (r["fund"], r["rank"]))

    return {
        "sell_now":   sell_now,
        "sell_reb":   sell_reb,
        "buy_reb":    buy_reb,
        "watch":      watch,
        "next_reb":   next_reb,
    }


def print_trade_list(tl: dict) -> None:
    nxt = tl["next_reb"].strftime("%a %b %d")
    print(f"\n{'▓'*70}")
    print(f"  TRADE EXECUTION LIST")
    print(f"  Rebalance day: Monday {nxt}  ·  Equal-weight ₹{_POLICY.budget_sc:,.0f} SC / ₹{_POLICY.budget_mc:,.0f} MC")
    print(f"{'▓'*70}")

    if tl["sell_now"]:
        print(f"\n  ⚡ SELL NOW — Stage 2 broken, do not wait for rebalance")
        print(f"  {'Symbol':<14} {'Fund':<12} {'Stage':<10} {'P&L%':>7}  Reason")
        print(f"  {'─'*65}")
        for s in tl["sell_now"]:
            pnl = f"{s['pnl_pct']:>+6.2f}%" if s.get("pnl_pct") is not None else "    N/A"
            print(f"  {s['symbol']:<14} {s['fund']:<12} {(s['stage'] or '?'):<10} {pnl}  {s['reason']}")
    else:
        print(f"\n  ⚡ SELL NOW — none (no Stage 2 exits today)")

    if tl["sell_reb"]:
        print(f"\n  📅 SELL at rebalance — Monday {nxt}")
        cur_fund = None
        for s in sorted(tl["sell_reb"], key=lambda x: (x["fund"], x["drop_reason"])):
            if s["fund"] != cur_fund:
                cur_fund = s["fund"]
                budget, n = _fund_budget(cur_fund)
                print(f"\n     {cur_fund}  ·  ₹{budget:,} / {n} positions = ₹{budget//n:,} each")
            pnl = f"{s['pnl_pct']:>+6.2f}%" if s.get("pnl_pct") is not None else "    N/A"
            lbl = {"TECH":"EXIT","GRAD":"GRAD","RS":"RS  ","FUND":"FUND","RANK":"RANK"}.get(s["drop_reason"], s["drop_reason"])
            print(f"     [{lbl}] {s['symbol']:<14} {pnl}  {s['detail']}")

    if tl["buy_reb"]:
        print(f"\n  🔵 BUY at rebalance — Monday {nxt}")
        cur_fund = None
        for b in tl["buy_reb"]:
            if b["fund"] != cur_fund:
                cur_fund = b["fund"]
                budget, n = _fund_budget(cur_fund)
                print(f"\n     {cur_fund}  ·  ₹{budget//n:,} per slot")
                print(f"     {'#':<3} {'Symbol':<14} {'Price':>8} {'Qty':>5} {'Est.Cost':>10} {'TechSc':>7} {'Fund':>6}")
                print(f"     {'─'*60}")
            price_s = f"₹{b['price']:>8.2f}" if b["price"] else "    N/A"
            cost_s  = f"₹{b['est_cost']:>8,.0f}" if b["qty"] else "  NO PRICE"
            print(f"     {b['rank']:<3} {b['symbol']:<14} {price_s} {b['qty']:>5}   {cost_s} "
                  f"{str(b.get('tech_score') or '?'):>7} {str(b.get('fund_score') or '?'):>6} [{b.get('fund_grade','?')}]")

    if tl["watch"]:
        print(f"\n  🟠 WATCH — no order, monitor daily")
        for w in tl["watch"]:
            print(f"     {w['symbol']:<14} {w['fund']:<12}  {w['note']}")

    total_buys  = len(tl["buy_reb"])
    total_sells = len(tl["sell_now"]) + len(tl["sell_reb"])
    est_spend   = sum(b["est_cost"] for b in tl["buy_reb"] if b["qty"])
    print(f"\n  SUMMARY:  {len(tl['sell_now'])} sell-now  +  {len(tl['sell_reb'])} sell-at-rebalance"
          f"  |  {total_buys} buys  ·  est. outlay ₹{est_spend:,.0f}")


# ── PORTFOLIO P&L ────────────────────────────────────────────────────────────

def compute_fund_pnl(signal_rows: list) -> dict:
    """
    Compute per-fund and combined P&L using snapshot close prices + entry prices.
    Slot size = FUND_BUDGETS alloc_per (equal-weight).
    Returns {fund_name: {invested, current, pnl_rs, pnl_pct, winners, losers, n_pos}, "_combined": {...}}
    """
    fund_rows: dict[str, list] = {}
    for r in signal_rows:
        fname = r.get("fund", "")
        if fname:
            fund_rows.setdefault(fname, []).append(r)

    result: dict = {}
    total_inv = total_curr = 0.0
    total_w = total_l = total_n = 0

    for fname, rows in fund_rows.items():
        budget, n = _fund_budget(fname)
        alloc_per = budget / n
        inv = curr = 0.0
        w = l = 0

        for r in rows:
            entry = float(r.get("entry") or 0)
            close = r.get("close")
            if not entry or not close:
                continue
            qty      = int(alloc_per / entry)
            pos_inv  = qty * entry
            pos_curr = qty * float(close)
            inv  += pos_inv
            curr += pos_curr
            diff  = pos_curr - pos_inv
            if diff > 0:   w += 1
            elif diff < 0: l += 1

        pnl_rs  = curr - inv
        pnl_pct = (pnl_rs / inv * 100) if inv else 0.0
        n_pos   = sum(1 for r in rows if r.get("close"))

        result[fname] = {"invested": inv, "current": curr, "pnl_rs": pnl_rs,
                         "pnl_pct": pnl_pct, "winners": w, "losers": l, "n_pos": n_pos}
        total_inv  += inv;  total_curr += curr
        total_w += w;  total_l += l;  total_n += n_pos

    result["_combined"] = {
        "invested": total_inv, "current": total_curr,
        "pnl_rs":  total_curr - total_inv,
        "pnl_pct": ((total_curr - total_inv) / total_inv * 100) if total_inv else 0.0,
        "winners": total_w, "losers": total_l, "n_pos": total_n,
    }
    return result


def html_pnl_panel(pnl: dict) -> str:
    fund_order = [k for k in pnl if not k.startswith("_")]
    rows_html  = ""

    for fname in fund_order:
        d       = pnl[fname]
        is_pos  = d["pnl_pct"] >= 0
        pcls    = "pos" if is_pos else "neg"
        arrow   = "▲" if is_pos else "▼"
        fc_cls  = fname.replace(" ", "-").lower()
        bar_w   = min(abs(d["pnl_pct"]) * 8, 100)   # visual bar, capped at 100px
        bar_col = "var(--hold)" if is_pos else "var(--exit)"
        rows_html += f"""<div class="pnl-row">
  <span class="pnl-fname"><span class="fc fc-{fc_cls}">{fname}</span></span>
  <span class="pnl-inv">₹{d['invested']:>10,.0f}</span>
  <span class="pnl-rarr">→</span>
  <span class="pnl-curr">₹{d['current']:>10,.0f}</span>
  <span class="pnl-divider">|</span>
  <span class="pnl-rs {pcls}">{arrow} ₹{d['pnl_rs']:>+10,.0f}</span>
  <span class="pnl-pct {pcls}">{d['pnl_pct']:>+6.2f}%</span>
  <div class="pnl-bar-wrap"><div class="pnl-bar" style="width:{bar_w:.0f}px;background:{bar_col}"></div></div>
  <span class="pnl-wl muted">{d['winners']}W&nbsp;{d['losers']}L</span>
</div>"""

    c = pnl["_combined"]
    is_pos  = c["pnl_pct"] >= 0
    pcls    = "pos" if is_pos else "neg"
    arrow   = "▲" if is_pos else "▼"
    rows_html += f"""<div class="pnl-row pnl-total">
  <span class="pnl-fname"><strong>Combined</strong></span>
  <span class="pnl-inv">₹{c['invested']:>10,.0f}</span>
  <span class="pnl-rarr">→</span>
  <span class="pnl-curr">₹{c['current']:>10,.0f}</span>
  <span class="pnl-divider">|</span>
  <span class="pnl-rs {pcls}"><strong>{arrow} ₹{c['pnl_rs']:>+10,.0f}</strong></span>
  <span class="pnl-pct {pcls}"><strong>{c['pnl_pct']:>+6.2f}%</strong></span>
  <div class="pnl-bar-wrap"></div>
  <span class="pnl-wl muted">{c['winners']}W&nbsp;{c['losers']}L&nbsp;/&nbsp;{c['n_pos']}</span>
</div>"""

    return f"""<div class="pnl-card">
  <div class="pnl-card-hdr">💰 Portfolio P&amp;L <span class="pnl-note">(snapshot prices · equal-weight slots)</span></div>
  <div class="pnl-rows">{rows_html}</div>
</div>"""


def print_pnl_summary(pnl: dict) -> None:
    W = 80
    print(f"\n  {'─'*W}")
    print(f"  PORTFOLIO P&L  (snapshot prices · equal-weight slots)")
    print(f"  {'Fund':<14} {'Invested':>12} {'Current':>12} {'P&L ₹':>10} {'P&L %':>8}  W/L")
    print(f"  {'─'*W}")
    for fname, d in pnl.items():
        if fname.startswith("_"): continue
        sign = "▲" if d["pnl_pct"] >= 0 else "▼"
        print(f"  {fname:<14} ₹{d['invested']:>10,.0f} ₹{d['current']:>10,.0f} "
              f"₹{d['pnl_rs']:>+9,.0f} {d['pnl_pct']:>+7.2f}%  {sign} {d['winners']}W {d['losers']}L")
    c = pnl["_combined"]
    sign = "▲" if c["pnl_pct"] >= 0 else "▼"
    print(f"  {'─'*W}")
    print(f"  {'Combined':<14} ₹{c['invested']:>10,.0f} ₹{c['current']:>10,.0f} "
          f"₹{c['pnl_rs']:>+9,.0f} {c['pnl_pct']:>+7.2f}%  {sign} {c['winners']}W {c['losers']}L")
    print(f"  {'─'*W}")


# ── HTML ──────────────────────────────────────────────────────────────────────

def _gc(g): return {"A":"ga","B":"gb","C":"gc","F":"gf"}.get(g,"gna")
def _sc(sig): return {"HOLD":"sig-hold","WEAKEN":"sig-weak","EXIT":"sig-exit"}.get(sig,"")

def _buy_signal_html(trading_signal: str, trend_signal: str,
                     supertrend_state: str = "UNKNOWN") -> str:
    """
    Render a conviction pill for a new buy row using DB-derived signals.

    trading_signal  : STRONG_BUY / BUY / HOLD / WEAK_HOLD / SELL
    trend_signal    : STRONG_BULLISH / BULLISH / BEARISH / UNKNOWN
    supertrend_state: BULLISH / BEARISH / UNKNOWN
    """
    ts  = (trading_signal  or "HOLD").upper()
    tr  = (trend_signal    or "UNKNOWN").upper()
    st  = (supertrend_state or "UNKNOWN").upper()

    strong_trend = tr == "STRONG_BULLISH" and st == "BULLISH"
    any_bullish  = tr in ("STRONG_BULLISH", "BULLISH") and st == "BULLISH"

    if ts == "STRONG_BUY" and strong_trend:
        label, bg, col = "STRONG BUY",  "rgba(30,217,122,.18)", "#1ed97a"
    elif ts == "STRONG_BUY":
        label, bg, col = "STRONG BUY",  "rgba(30,217,122,.12)", "#1ed97a"
    elif ts == "BUY" and strong_trend:
        label, bg, col = "BUY",         "rgba(88,166,255,.18)", "#58a6ff"
    elif ts == "BUY" and any_bullish:
        label, bg, col = "BUY",         "rgba(88,166,255,.13)", "#58a6ff"
    elif ts == "BUY":
        label, bg, col = "BUY ⚠trend",  "rgba(245,166,35,.15)", "#f5a623"
    elif ts == "WEAK_HOLD":
        label, bg, col = "SPECULATIVE", "rgba(245,166,35,.12)", "#f5a623"
    else:
        label, bg, col = "SPECULATIVE", "rgba(139,148,158,.12)", "#8b949e"

    return (f'<span style="font-size:10px;font-weight:700;padding:1px 7px;'
            f'border-radius:4px;background:{bg};color:{col}">{label}</span>')

def html_trade_list(tl: dict) -> str:
    nxt = tl["next_reb"].strftime("%a %b %d, %Y")

    # ── Sell NOW ──
    if tl["sell_now"]:
        now_rows = ""
        for s in tl["sell_now"]:
            pnl_cls = "pos" if (s.get("pnl_pct") or 0) >= 0 else "neg"
            pnl_s   = fmt(s.get("pnl_pct"), dec=2, plus=True, suf="%") if s.get("pnl_pct") is not None else "—"
            now_rows += f"""<tr>
  <td class="sym">{s['symbol']}</td>
  <td><span class="fc fc-{s['fund'].replace(' ','-').lower()}">{s['fund']}</span></td>
  <td><span class="stg stg-{(s.get('stage') or 'na').lower()}">{(s.get('stage') or '?').replace('STAGE_','S')}</span></td>
  <td class="n {pnl_cls}">{pnl_s}</td>
  <td class="detail">{s['reason']}</td>
</tr>"""
        sell_now_html = f"""<div class="tl-group tl-urgent">
  <div class="tl-hdr">
    <span class="tl-icon">⚡</span>
    <strong>Sell NOW</strong>
    <span class="tl-sub">Stage 2 broken — do not wait for Monday's rebalance</span>
    <span class="tl-count tl-count-red">{len(tl['sell_now'])} order{'s' if len(tl['sell_now'])!=1 else ''}</span>
  </div>
  <div class="tbl-wrap"><table>
    <thead><tr><th>Symbol</th><th>Fund</th><th>Stage</th><th class="n">P&amp;L %</th><th>Reason</th></tr></thead>
    <tbody>{now_rows}</tbody>
  </table></div>
</div>"""
    else:
        sell_now_html = """<div class="tl-group tl-clean">
  <div class="tl-hdr"><span class="tl-icon">⚡</span>
    <strong>Sell NOW</strong>
    <span class="tl-sub">None — no Stage 2 exits today</span></div>
</div>"""

    # ── Sell at rebalance ──
    sell_reb_rows = ""
    cur_fund = None
    for s in sorted(tl["sell_reb"], key=lambda x: (x["fund"], x["drop_reason"])):
        if s["fund"] != cur_fund:
            cur_fund = s["fund"]
            budget, n = _fund_budget(cur_fund)
            sell_reb_rows += f'<tr class="grp-sep sep-fund"><td colspan="5">{cur_fund} · ₹{budget:,} / {n} positions</td></tr>'
        pnl_cls = "pos" if (s.get("pnl_pct") or 0) >= 0 else "neg"
        pnl_s   = fmt(s.get("pnl_pct"), dec=2, plus=True, suf="%") if s.get("pnl_pct") is not None else "—"
        dr = s.get("drop_reason","")
        badge_map = {"TECH":"b-tech","GRAD":"b-grad","RS":"b-rs","FUND":"b-fund","RANK":"b-rank"}
        sell_reb_rows += f"""<tr>
  <td class="sym">{s['symbol']}</td>
  <td><span class="badge {badge_map.get(dr,'')}">{dr}</span></td>
  <td><span class="stg stg-{(s.get('stage') or 'na').lower()}">{(s.get('stage') or '?').replace('STAGE_','S')}</span></td>
  <td class="n {pnl_cls}">{pnl_s}</td>
  <td class="detail muted">{s.get('detail','')}</td>
</tr>"""

    sell_reb_html = f"""<div class="tl-group tl-sell">
  <div class="tl-hdr">
    <span class="tl-icon">📅</span>
    <strong>Sell at rebalance — Monday {nxt}</strong>
    <span class="tl-sub">Execute at market open or VWAP</span>
    <span class="tl-count tl-count-orange">{len(tl['sell_reb'])} order{'s' if len(tl['sell_reb'])!=1 else ''}</span>
  </div>
  <div class="tbl-wrap"><table>
    <thead><tr><th>Symbol</th><th>Reason</th><th>Stage</th><th class="n">P&amp;L %</th><th>Detail</th></tr></thead>
    <tbody>{sell_reb_rows}</tbody>
  </table></div>
</div>"""

    # ── Buy at rebalance ──
    buy_rows = ""
    cur_fund = None
    total_outlay = 0
    for b in tl["buy_reb"]:
        if b["fund"] != cur_fund:
            cur_fund = b["fund"]
            budget, n = _fund_budget(cur_fund)
            buy_rows += f'<tr class="grp-sep sep-fund"><td colspan="8">{cur_fund} · ₹{budget//n:,} per slot (₹{budget:,} / {n})</td></tr>'
        price_s  = f"₹{b['price']:,.2f}" if b["price"] else "—"
        cost_s   = f"₹{b['est_cost']:,.0f}" if b["qty"] else "No price"
        short_s  = f"₹{b['shortfall']:,.0f}" if b["qty"] else "—"
        total_outlay += b.get("est_cost", 0)
        buy_rows += f"""<tr class="r-add">
  <td class="n rank-num">#{b['rank']}</td>
  <td class="sym">{b['symbol']}</td>
  <td><span class="fc fc-{b['fund'].replace(' ','-').lower()}">{b['fund']}</span></td>
  <td class="n">{price_s}</td>
  <td class="n qty-cell">{b['qty'] if b['qty'] else '—'}</td>
  <td class="n cost-cell">{cost_s}</td>
  <td class="n">{fmt(b.get('tech_score'))}</td>
  <td class="n"><span class="{_gc(b.get('fund_grade','?'))}">{fmt(b.get('fund_score'))}</span> <small>{b.get('fund_grade','?')}</small></td>
</tr>"""

    buy_html = f"""<div class="tl-group tl-buy">
  <div class="tl-hdr">
    <span class="tl-icon">🔵</span>
    <strong>Buy at rebalance — Monday {nxt}</strong>
    <span class="tl-sub">Use proceeds from sells + idle cash · Est. outlay ₹{total_outlay:,.0f}</span>
    <span class="tl-count tl-count-blue">{len(tl['buy_reb'])} order{'s' if len(tl['buy_reb'])!=1 else ''}</span>
  </div>
  <div class="tbl-wrap"><table>
    <thead><tr>
      <th class="n">#</th><th>Symbol</th><th>Fund</th>
      <th class="n">Last Price</th><th class="n">Qty</th>
      <th class="n">Est. Cost</th>
      <th class="n">TechSc</th><th class="n">FScore</th>
    </tr></thead>
    <tbody>{buy_rows}</tbody>
  </table></div>
</div>"""

    # ── Watch ──
    watch_html = ""
    if tl["watch"]:
        watch_rows = "".join(f"""<tr>
  <td class="sym">{w['symbol']}</td>
  <td><span class="fc fc-{w['fund'].replace(' ','-').lower()}">{w['fund']}</span></td>
  <td class="detail muted">{w['note']}</td>
</tr>""" for w in tl["watch"])
        watch_html = f"""<div class="tl-group tl-watch">
  <div class="tl-hdr">
    <span class="tl-icon">🟠</span>
    <strong>Watch — no order yet</strong>
    <span class="tl-sub">Monitor daily; sell at rebalance if condition persists</span>
  </div>
  <div class="tbl-wrap"><table>
    <thead><tr><th>Symbol</th><th>Fund</th><th>Note</th></tr></thead>
    <tbody>{watch_rows}</tbody>
  </table></div>
</div>"""

    return f"""<div class="trade-list">
{sell_now_html}
{sell_reb_html}
{buy_html}
{watch_html}
</div>"""

def html_signal_table(rows: list) -> str:
    body = ""
    cur_sig = None
    for r in rows:
        if r["signal"] != cur_sig:
            cur_sig = r["signal"]
            labels = {"EXIT":"🔴 EXIT — fails gate","WEAKEN":"🟠 WEAKEN — RS slipping",
                      "HOLD":"🟢 HOLD — both gates pass","NO_DATA":"⚪ No data"}
            sep_cls = {"EXIT":"sep-exit","WEAKEN":"sep-weak","HOLD":"sep-hold","NO_DATA":"sep-na"}
            body += f'<tr class="grp-sep {sep_cls.get(cur_sig,"")}"><td colspan="10">{labels.get(cur_sig,cur_sig)}</td></tr>'

        pnl_cls = "pos" if (r["pnl_pct"] or 0) >= 0 else "neg"
        close_s = fmt(r["close"], dec=2, pre="₹") if r["close"] else "—"
        pnl_s   = fmt(r["pnl_pct"], dec=2, plus=True, suf="%") if r["pnl_pct"] is not None else "—"
        fs_s    = fmt(r["fund_score"], dec=1)
        chg     = ' <span class="chg">CHG</span>' if r["changed"] else ""
        tag     = ""
        if r["signal"] == "EXIT":
            if "fund gate" in r["fund_reason"]: tag = '<span class="xt xt-f">FUND</span>'
            else: tag = '<span class="xt xt-t">TECH</span>'

        body += f"""<tr class="r-{r['signal'].lower()}">
  <td class="sym">{r['symbol']}</td>
  <td><span class="fc fc-{r['fund'].replace(' ','-').lower()}">{r['fund']}</span></td>
  <td><span class="sig {_sc(r['signal'])}">{r['signal']}</span>{tag}{chg}</td>
  <td><span class="stg stg-{(r['stage'] or 'na').lower()}">{(r['stage'] or '—').replace('STAGE_','S')}</span></td>
  <td class="n">₹{fmt(r['entry'],dec=2)}</td>
  <td class="n">{close_s}</td>
  <td class="n {pnl_cls}">{pnl_s}</td>
  <td class="n"><span class="{_gc(r['fund_grade'])}">{fs_s}</span></td>
  <td class="n">{fmt(r['eq'])}</td><td class="detail">{r['tech_reason']}</td>
</tr>"""
    return body

def html_rebalance_section(name: str, result: dict, cap: str, n: int, rs_p70: float) -> str:
    filter_str = (f"Stage 2 + RS &gt; {rs_p70:.1f} + Fund ≥ {FUND_SCORE_MIN} + Darvas BUY + ST Bullish"
                  if cap == "SMALL_CAP" else f"Stage 2 + Fund ≥ {FUND_SCORE_MIN} + Darvas BUY + ST Bullish")
    changes = len(result["adds"])

    rows_html = ""

    if result["holds"]:
        rows_html += f'<tr class="grp-sep sep-hold"><td colspan="8">🟢 Hold ({len(result["holds"])}) — stays in portfolio</td></tr>'
        for r in result["holds"]:
            rows_html += f"""<tr class="r-hold">
  <td class="sym">{r['symbol']}</td><td><span class="badge b-hold">HOLD</span></td>
  <td class="n">{fmt(r.get('tech_score'))}</td><td class="n">{fmt(r.get('rs'),plus=True)}</td>
  <td class="n"><span class="{_gc(r.get('fund_grade','?'))}">{fmt(r.get('fund_score'))}</span></td>
  <td class="n">{fmt(r.get('eq'))}</td><td class="n">{fmt(r.get('sg'))}</td><td></td>
</tr>"""

    if result["adds"]:
        rows_html += f'<tr class="grp-sep sep-add"><td colspan="8">🔵 Add ({len(result["adds"])}) — enter at rebalance</td></tr>'
        for r in result["adds"]:
            rank = result["top_n"].index(r) + 1
            rows_html += f"""<tr class="r-add">
  <td class="sym">{r['symbol']}</td><td><span class="badge b-add">ADD #{rank}</span></td>
  <td class="n">{fmt(r.get('tech_score'))}</td><td class="n">{fmt(r.get('rs'),plus=True)}</td>
  <td class="n"><span class="{_gc(r.get('fund_grade','?'))}">{fmt(r.get('fund_score'))}</span></td>
  <td class="n">{fmt(r.get('eq'))}</td><td class="n">{fmt(r.get('sg'))}</td>
  <td class="detail muted">New position</td>
</tr>"""

    DROP_GROUPS = [
        ("TECH","🔴 Tech exit — Stage 2 broken"),
        ("GRAD","🟣 Graduated — outgrown universe"),
        ("RS",  "🟠 RS exit — below threshold"),
        ("FUND","🟡 Fund gate — score below 65"),
        ("RANK","🔵 Ranked out — displaced"),
    ]
    for reason, label in DROP_GROUPS:
        sub = [r for r in result["drops"] if r.get("drop_reason") == reason]
        if not sub: continue
        bdg = {"TECH":"b-tech","GRAD":"b-grad","RS":"b-rs","FUND":"b-fund","RANK":"b-rank"}.get(reason,"")
        rows_html += f'<tr class="grp-sep sep-drop"><td colspan="8">DROP [{reason}]: {label} ({len(sub)})</td></tr>'
        for r in sub:
            rows_html += f"""<tr class="r-drop">
  <td class="sym">{r['symbol']}</td><td><span class="badge {bdg}">{reason}</span></td>
  <td class="n">{fmt(r.get('tech_score'))}</td><td class="n">{fmt(r.get('rs'),plus=True)}</td>
  <td class="n"><span class="{_gc(r.get('fund_grade','?'))}">{fmt(r.get('fund_score'))}</span></td>
  <td></td><td></td><td class="detail muted">{r.get('detail','')}</td>
</tr>"""

    if result["watch"]:
        rows_html += f'<tr class="grp-sep sep-watch"><td colspan="8">👁 Watch — next {WATCH_N} after top {n}</td></tr>'
        for i, r in enumerate(result["watch"], start=n+1):
            rows_html += f"""<tr class="r-watch">
  <td class="sym">{r['symbol']}</td><td><span class="badge b-watch">#{i}</span></td>
  <td class="n">{fmt(r.get('tech_score'))}</td><td class="n">{fmt(r.get('rs'),plus=True)}</td>
  <td class="n"><span class="{_gc(r.get('fund_grade','?'))}">{fmt(r.get('fund_score'))}</span></td>
  <td class="n">{fmt(r.get('eq'))}</td><td class="n">{fmt(r.get('sg'))}</td>
  <td class="detail muted">Available if needed</td>
</tr>"""

    return f"""<div class="rb-fund">
  <div class="rb-fund-hdr">
    <strong>{name}</strong>
    <span class="rb-meta">{filter_str} · top {n} by TechScore · {len(result['passing'])} pass both gates</span>
    <span class="rb-changes {'rb-has-changes' if changes else 'rb-clean'}">
      {'⚠ ' + str(changes) + ' change' + ('s' if changes != 1 else '') if changes else '✓ No changes'}
    </span>
  </div>
  <div class="tbl-wrap"><table>
    <thead><tr>
      <th>Symbol</th><th>Action</th>
      <th class="n">TechSc</th><th class="n">RS</th>
      <th class="n">FScore</th><th class="n">EQ</th><th class="n">SG</th><th>Detail</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
  </table></div>
</div>"""


def build_html(signal_rows: list, rebalance_funds: list,
               run_date: str, snap_date: str,
               is_rebalance_day: bool, next_reb: date,
               rs_p70: float) -> str:

    exits   = [r for r in signal_rows if r["signal"] == "EXIT"]
    weakens = [r for r in signal_rows if r["signal"] == "WEAKEN"]
    holds   = [r for r in signal_rows if r["signal"] == "HOLD"]
    fund_exits = [r for r in exits if "fund gate" in r["fund_reason"]]
    changes = [r for r in signal_rows if r["changed"]]
    total_rb_changes = sum(len(f["result"]["adds"]) for f in rebalance_funds)

    reb_banner = (
        '<div class="reb-day">📅 REBALANCE DAY — execute swaps today</div>'
        if is_rebalance_day else
        f'<div class="reb-next">Next weekly rebalance: <strong>Monday {next_reb.strftime("%b %d, %Y")}</strong></div>'
    )

    exit_banner = ""
    if exits:
        tech_e = [r for r in exits if "fund gate" not in r["fund_reason"]]
        fund_e = fund_exits
        inner = ""
        if tech_e:
            inner += f'<span class="eb-s">Stage exit: {" · ".join("<b>"+r["symbol"]+"</b>" for r in tech_e)}</span>'
        if fund_e:
            inner += f'<span class="eb-s">Fund exit: {" · ".join("<b>"+r["symbol"]+"</b>" for r in fund_e)}</span>'
        exit_banner = f'<div class="exit-banner">⚠ EXIT signals: {inner}</div>'

    pnl         = compute_fund_pnl(signal_rows)
    pnl_html    = html_pnl_panel(pnl)
    trade_list  = build_trade_list(signal_rows, rebalance_funds, next_reb)
    tl_html     = html_trade_list(trade_list)
    sig_table   = html_signal_table(signal_rows)
    rb_sections = "\n".join(
        html_rebalance_section(f["name"], f["result"], f["cap"], f["n"], f["rs_p70"])
        for f in rebalance_funds
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fund Daily — {run_date}</title>
<style>
:root{{
  --bg:#f5f7fa;--surface:#fff;--surface2:#eef1f5;--border:#d0d7de;
  --text:#1a2233;--text2:#57606a;--text3:#8b949e;
  --hold:#1a7f37;--add:#0969da;--exit:#cf222e;--weak:#b35c00;
  --shadow:0 1px 3px rgba(0,0,0,.06);
}}
@media(prefers-color-scheme:dark){{:root:not([data-theme="light"]){{
  --bg:#0d1117;--surface:#161b22;--surface2:#1c2128;--border:#30363d;
  --text:#e6edf3;--text2:#8b949e;--text3:#6e7681;
  --hold:#3fb950;--add:#58a6ff;--exit:#f85149;--weak:#fbbf24;
}}}}
:root[data-theme="dark"]{{
  --bg:#0d1117;--surface:#161b22;--surface2:#1c2128;--border:#30363d;
  --text:#e6edf3;--text2:#8b949e;--text3:#6e7681;
  --hold:#3fb950;--add:#58a6ff;--exit:#f85149;--weak:#fbbf24;
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
  font-size:13px;background:var(--bg);color:var(--text);padding:20px 24px;max-width:1300px;margin:0 auto}}
h1{{font-size:17px;font-weight:700}}
h2{{font-size:14px;font-weight:700;margin:0}}
.page-sub{{font-size:11px;color:var(--text2);margin-top:2px;margin-bottom:12px}}

/* ── Banner ── */
.reb-day{{background:#1a7f37;color:#fff;border-radius:7px;padding:8px 14px;font-weight:600;
  font-size:12px;margin-bottom:10px}}
.reb-next{{background:var(--surface);border:1px solid var(--border);border-radius:7px;
  padding:8px 14px;font-size:12px;color:var(--text2);margin-bottom:10px}}
.exit-banner{{background:rgba(207,34,46,.07);border:1px solid rgba(207,34,46,.25);
  border-radius:7px;padding:8px 14px;font-size:12px;color:var(--exit);
  margin-bottom:10px;display:flex;gap:12px;flex-wrap:wrap;align-items:center}}
.eb-s{{display:flex;gap:5px;align-items:center;flex-wrap:wrap}}

/* ── Stats ── */
.stats{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}}
.stat{{background:var(--surface);border:1px solid var(--border);border-radius:8px;
  padding:8px 14px;box-shadow:var(--shadow)}}
.stat-lbl{{font-size:10px;text-transform:uppercase;letter-spacing:.4px;color:var(--text2)}}
.stat-val{{font-size:18px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.2}}

/* ── Section headers ── */
.section-hdr{{font-size:13px;font-weight:700;padding:12px 0 6px;
  border-bottom:2px solid var(--border);margin-bottom:10px;display:flex;
  align-items:baseline;gap:8px}}
.section-hdr .sh-meta{{font-size:11px;font-weight:400;color:var(--text2)}}

/* ── Signal table ── */
.tbl-card{{background:var(--surface);border:1px solid var(--border);border-radius:10px;
  box-shadow:var(--shadow);overflow:hidden;margin-bottom:20px}}
.tbl-wrap{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}}
thead th{{background:var(--surface2);color:var(--text2);font-size:10px;font-weight:700;
  text-transform:uppercase;letter-spacing:.4px;padding:7px 10px;
  border-bottom:1px solid var(--border);white-space:nowrap;text-align:left}}
thead th.n{{text-align:right}}
tbody td{{padding:6px 10px;border-bottom:1px solid var(--border);
  font-size:12px;vertical-align:middle;white-space:nowrap}}
td.n{{text-align:right}}
td.detail{{min-width:160px;white-space:normal;font-size:11px;color:var(--text2)}}
td.muted{{color:var(--text2)}}
.sym{{font-weight:600}}
tbody tr:hover td{{background:var(--surface2)}}
.grp-sep td{{padding:6px 10px;font-size:11px;font-weight:600;
  border-top:2px solid var(--border);border-bottom:1px solid var(--border)}}
.sep-hold td{{color:var(--hold);background:rgba(26,127,55,.04)}}
.sep-add  td{{color:var(--add); background:rgba(9,105,218,.04)}}
.sep-drop td{{color:var(--exit);background:rgba(207,34,46,.04)}}
.sep-weak td{{color:var(--weak)}}
.sep-exit td{{color:var(--exit)}}
.sep-na   td{{color:var(--text3)}}
.sep-watch td{{color:var(--text3);background:var(--surface2)}}
.r-exit td{{background:rgba(207,34,46,.02)}}
.r-weaken td{{background:rgba(217,119,6,.02)}}
.r-add td{{background:rgba(9,105,218,.03)}}
.r-drop td{{background:rgba(207,34,46,.02)}}
.r-watch td{{opacity:.75}}

/* fund chip */
.fc{{display:inline-block;padding:1px 6px;border-radius:4px;font-size:10px;font-weight:600}}
.fc-aug-sc{{background:rgba(26,127,55,.1);color:var(--hold)}}
.fc-aug-mc{{background:rgba(9,105,218,.1);color:var(--add)}}
.fc-shadow-sc,.fc-shadow-mc{{background:rgba(124,58,237,.1);color:#7c3aed}}

/* signal badge */
.sig{{display:inline-block;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:700}}
.sig-hold{{color:var(--hold);background:rgba(26,127,55,.1)}}
.sig-weak{{color:var(--weak);background:rgba(217,119,6,.1)}}
.sig-exit{{color:var(--exit);background:rgba(207,34,46,.12)}}

/* stage */
.stg{{display:inline-block;padding:1px 5px;border-radius:3px;font-size:10px;font-weight:600}}
.stg-stage_2{{color:var(--hold);background:rgba(26,127,55,.1)}}
.stg-stage_1{{color:var(--add);background:rgba(9,105,218,.1)}}
.stg-stage_3,.stg-stage_4{{color:var(--exit);background:rgba(207,34,46,.1)}}
.stg-na{{color:var(--text3)}}

/* fund grade */
.ga{{color:var(--hold);font-weight:700}}
.gb{{color:var(--add);font-weight:600}}
.gc{{color:var(--weak);font-weight:600}}
.gf{{color:var(--exit);font-weight:700}}
.gna{{color:var(--text3)}}

/* exit tags / change chip */
.xt{{font-size:9px;font-weight:700;padding:1px 4px;border-radius:3px;margin-left:3px}}
.xt-t{{background:rgba(207,34,46,.15);color:var(--exit)}}
.xt-f{{background:rgba(217,119,6,.15);color:var(--weak)}}
.chg{{font-size:9px;font-weight:700;padding:1px 4px;border-radius:3px;
  background:#dbeafe;color:#1d4ed8;margin-left:3px}}
.pos{{color:var(--hold);font-weight:600}}
.neg{{color:var(--exit);font-weight:600}}

/* ── Rebalance section ── */
.rb-fund{{background:var(--surface);border:1px solid var(--border);border-radius:10px;
  box-shadow:var(--shadow);margin-bottom:14px;overflow:hidden}}
.rb-fund-hdr{{padding:10px 14px;display:flex;align-items:center;gap:10px;
  flex-wrap:wrap;border-bottom:1px solid var(--border)}}
.rb-meta{{font-size:11px;color:var(--text2);flex:1}}
.rb-changes{{font-size:11px;font-weight:600;padding:3px 9px;border-radius:5px}}
.rb-has-changes{{background:rgba(207,34,46,.1);color:var(--exit)}}
.rb-clean{{background:rgba(26,127,55,.1);color:var(--hold)}}
.badge{{display:inline-block;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:700}}
.b-hold{{background:rgba(26,127,55,.12);color:var(--hold)}}
.b-add{{background:rgba(9,105,218,.12);color:var(--add)}}
.b-tech{{background:rgba(207,34,46,.15);color:var(--exit)}}
.b-grad{{background:rgba(139,92,246,.15);color:#7c3aed}}
.b-rs{{background:rgba(217,119,6,.15);color:#b35c00}}
.b-fund{{background:rgba(234,179,8,.15);color:#92400e}}
.b-rank{{background:rgba(99,102,241,.15);color:#4f46e5}}
.b-watch{{background:var(--surface2);color:var(--text3);border:1px solid var(--border)}}

/* ── Trade list ── */
.trade-list{{display:flex;flex-direction:column;gap:12px;margin-bottom:20px}}
.tl-group{{background:var(--surface);border:1px solid var(--border);border-radius:10px;
  box-shadow:var(--shadow);overflow:hidden}}
.tl-urgent{{border-color:rgba(207,34,46,.4)}}
.tl-clean{{border-color:rgba(26,127,55,.3)}}
.tl-buy{{border-color:rgba(9,105,218,.25)}}
.tl-hdr{{display:flex;align-items:center;gap:10px;padding:10px 14px;
  border-bottom:1px solid var(--border);flex-wrap:wrap}}
.tl-urgent .tl-hdr{{background:rgba(207,34,46,.05)}}
.tl-clean  .tl-hdr{{background:rgba(26,127,55,.04)}}
.tl-buy    .tl-hdr{{background:rgba(9,105,218,.04)}}
.tl-sell   .tl-hdr{{background:rgba(217,119,6,.04)}}
.tl-watch  .tl-hdr{{background:var(--surface2)}}
.tl-icon{{font-size:16px}}
.tl-hdr strong{{font-size:13px;font-weight:700}}
.tl-sub{{font-size:11px;color:var(--text2);flex:1}}
.tl-count{{font-size:11px;font-weight:700;padding:2px 9px;border-radius:10px}}
.tl-count-red{{background:rgba(207,34,46,.1);color:var(--exit)}}
.tl-count-orange{{background:rgba(217,119,6,.1);color:var(--weak)}}
.tl-count-blue{{background:rgba(9,105,218,.1);color:var(--add)}}
.rank-num{{color:var(--text2);font-size:11px;min-width:30px}}
.qty-cell{{font-weight:700;color:var(--add)}}
.cost-cell{{font-weight:600}}
.sep-fund td{{padding:5px 10px;font-size:11px;font-weight:600;color:var(--text2);
  background:var(--surface2);border-top:1px solid var(--border);border-bottom:1px solid var(--border)}}
.footer{{font-size:11px;color:var(--text3);margin-top:12px;text-align:right}}

/* ── Portfolio P&L card ── */
.pnl-card{{background:var(--surface);border:1px solid var(--border);border-radius:10px;
  box-shadow:var(--shadow);margin-bottom:16px;overflow:hidden}}
.pnl-card-hdr{{padding:9px 14px;font-size:12px;font-weight:700;
  border-bottom:1px solid var(--border);background:var(--surface2)}}
.pnl-note{{font-size:10px;font-weight:400;color:var(--text3);margin-left:6px}}
.pnl-rows{{padding:6px 0}}
.pnl-row{{display:flex;align-items:center;gap:10px;padding:6px 14px;
  font-size:12px;font-variant-numeric:tabular-nums;flex-wrap:wrap}}
.pnl-row:not(:last-child){{border-bottom:1px solid var(--border)}}
.pnl-total{{border-top:2px solid var(--border)!important;background:var(--surface2);font-size:13px}}
.pnl-fname{{min-width:100px}}
.pnl-inv,.pnl-curr{{color:var(--text2);min-width:110px;text-align:right}}
.pnl-rarr{{color:var(--text3)}}
.pnl-divider{{color:var(--border);margin:0 2px}}
.pnl-rs{{min-width:130px;text-align:right;font-weight:600}}
.pnl-pct{{min-width:70px;text-align:right;font-weight:600}}
.pnl-bar-wrap{{flex:1;min-width:0}}
.pnl-bar{{height:4px;border-radius:2px;transition:width .2s}}
.pnl-wl{{font-size:11px;color:var(--text3);white-space:nowrap}}
</style></head><body>

<h1>Fund Daily Dashboard</h1>
<div class="page-sub">
  {run_date}  ·  Snapshot: {snap_date}  ·  SC RS p70 = {rs_p70:.1f}  ·  Fund gate ≥ {FUND_SCORE_MIN}  ·
  Weekly rebalance every Monday
</div>

{reb_banner}
{exit_banner}

<div class="stats">
  <div class="stat"><div class="stat-lbl">Hold</div>
    <div class="stat-val" style="color:var(--hold)">{len(holds)}</div></div>
  <div class="stat"><div class="stat-lbl">Weaken</div>
    <div class="stat-val" style="color:var(--weak)">{len(weakens)}</div></div>
  <div class="stat"><div class="stat-lbl">Exit</div>
    <div class="stat-val" style="color:var(--exit)">{len(exits)}</div></div>
  <div class="stat"><div class="stat-lbl">Fund gate exits</div>
    <div class="stat-val">{len(fund_exits)}</div></div>
  <div class="stat"><div class="stat-lbl">Signal changes</div>
    <div class="stat-val">{len(changes)}</div></div>
  <div class="stat"><div class="stat-lbl">Rebalance swaps</div>
    <div class="stat-val" style="color:{'var(--exit)' if total_rb_changes else 'var(--hold)'}">{total_rb_changes}</div></div>
</div>

<!-- ── PORTFOLIO P&L ── -->
{pnl_html}

<!-- ── TRADE EXECUTION LIST ── -->
<div class="section-hdr">
  🎯 What to Do
  <span class="sh-meta">Prioritised orders with position sizing — run this list on rebalance day</span>
</div>
{tl_html}

<!-- ── DAILY SIGNALS ── -->
<div class="section-hdr">
  📊 Daily Position Check
  <span class="sh-meta">Full signal status — HOLD / WEAKEN / EXIT for every position</span>
</div>
<div class="tbl-card"><div class="tbl-wrap"><table>
  <thead><tr>
    <th>Symbol</th><th>Fund</th><th>Signal</th><th>Stage</th>
    <th class="n">Entry ₹</th><th class="n">Close ₹</th><th class="n">P&amp;L %</th>
    <th class="n">FScore</th><th class="n">EQ</th><th>Tech Reason</th>
  </tr></thead>
  <tbody>{sig_table}</tbody>
</table></div></div>

<!-- ── WEEKLY REBALANCE ── -->
<div class="section-hdr">
  🔄 Universe Scan (Rebalance Detail)
  <span class="sh-meta">Full breakdown — HOLD / DROP / ADD / WATCH per fund</span>
</div>
{rb_sections}

<div class="footer">Agent Adda · stage_snapshots + fundamental_scores · {run_date}</div>
</body></html>"""


# ── FRESH START / INCEPTION MODE ─────────────────────────────────────────────

def _fresh_entry_qty(row: dict, alloc_per: float) -> int:
    """Slot-only quantity kept as a fallback for older HTML/order helpers."""
    price = float(row.get("price") or 0)
    return int(alloc_per / price) if price > 0 else 0


def _sleeve_key(cap: str) -> str:
    return "smallcap" if cap == "SMALL_CAP" else "midcap"


def seed_exposure_from_holdings(
    book: ExposureBook,
    holdings: dict,
    universe_map: dict,
    sleeve: str,
    policy: CapitalPolicy | None = None,
) -> None:
    """Seed already-held cost, sector, and open risk before filling new slots."""
    policy = policy or book.policy
    for symbol, meta in holdings.items():
        entry = float(meta.get("entry") or 0)
        qty = int(meta.get("qty") or 0)
        if qty < 1 or entry <= 0:
            continue
        snap = universe_map.get(symbol) or {}
        sector = str(snap.get("sector") or meta.get("sector") or "").strip()
        stop_row = {**snap, "price": entry}
        stop, _source = infer_stop(stop_row, policy)
        risk_rs = qty * (entry - stop) if stop and stop < entry else 0.0
        book.seed(symbol, qty * entry, sector, risk_rs=risk_rs, sleeve=sleeve)


def build_fresh_selection(result: dict, n: int, alloc_per: float,
                          skip_syms: set | None = None,
                          *,
                          sleeve: str = "midcap",
                          policy: CapitalPolicy | None = None,
                          book: ExposureBook | None = None) -> dict:
    """Select the first n purchasable passing rows, backfilling over 0-qty names.

    Quantity is the minimum of slot, stop-loss risk, single-stock cap,
    sector cap, and remaining sleeve cash. skip_syms are already-held
    names and are excluded so staged tranches do not re-buy them.
    """
    policy = policy or load_capital_policy()
    book = book or ExposureBook(policy)
    skip_syms = skip_syms or set()
    selected = []
    skipped = []
    selected_symbols = set()
    watch_n = policy.watch_n

    for source_rank, row in enumerate(result.get("passing", []), start=1):
        symbol = row.get("symbol")
        if not symbol or symbol in skip_syms:
            continue
        sized = size_fresh_row(
            row, alloc_per=alloc_per, sleeve=sleeve, policy=policy, book=book,
        )
        row_copy = apply_size_to_row(row, sized, alloc_per)
        row_copy["_fresh_rank"] = source_rank

        if not sized.accepted:
            skipped.append(row_copy)
            continue

        if len(selected) < n:
            selected.append(row_copy)
            selected_symbols.add(symbol)
            book.commit(symbol, sized, sleeve)
            continue

        break

    watch = []
    skipped_symbols = {r.get("symbol") for r in skipped}
    for source_rank, row in enumerate(result.get("passing", []), start=1):
        symbol = row.get("symbol")
        if symbol in selected_symbols or symbol in skipped_symbols or symbol in skip_syms:
            continue
        watch.append({**row, "_fresh_rank": source_rank})
        if len(watch) >= watch_n:
            break

    return {
        **result,
        "adds": selected,
        "top_n": selected,
        "watch": watch,
        "skipped": skipped,
    }


def _build_icici_order_sheet(fresh_funds: list, run_date: str = "") -> str:
    """Build ICICI Direct order entry table for all buy-this-week positions."""
    all_orders  = []
    held_rows   = []   # already-held positions to show as reference rows

    for fd in fresh_funds:
        result      = fd["result"]
        budget      = fd["budget"]
        n           = fd["n"]
        alloc_per   = budget / n
        sleeve      = "SC" if fd["cap"] == "SMALL_CAP" else "MC"
        already_held = fd.get("already_held", {})

        for add_r in result["adds"]:
            price    = float(add_r.get("price") or 0)
            qty      = int(add_r.get("_fresh_qty") or _fresh_entry_qty(add_r, alloc_per))
            est_cost = float(add_r.get("_fresh_est_cost") or (qty * price))
            if qty <= 0:
                continue
            all_orders.append({
                "sleeve":   sleeve,
                "symbol":   add_r["symbol"],
                "company":  company_name(add_r["symbol"]),
                "qty":      qty,
                "price":    price,
                "est_cost": est_cost,
            })

        for sym, meta in sorted(already_held.items()):
            held_rows.append({
                "sleeve":     sleeve,
                "symbol":     sym,
                "company":    company_name(sym),
                "entry":      float(meta.get("entry") or 0),
                "qty":        int(meta.get("qty") or 0),
                "entry_date": meta.get("entry_date", ""),
                "note":       meta.get("note", ""),
            })

    if not all_orders and not held_rows:
        return ""

    # ── New-order rows ──────────────────────────────────────────────────────────
    rows_html  = ""
    copy_lines = ["#\tExchange\tSymbol\tCompany\tQty\tOrder Type\tProduct\tEst. Price\tEst. Amount"]
    for i, o in enumerate(all_orders, 1):
        sleeve_chip = (
            '<span style="background:#1a7f3720;color:#1a7f37;border-radius:4px;'
            'padding:1px 6px;font-size:10px;font-weight:700">SC</span>'
            if o["sleeve"] == "SC" else
            '<span style="background:#e8932d20;color:#c97418;border-radius:4px;'
            'padding:1px 6px;font-size:10px;font-weight:700">MC</span>'
        )
        company = o.get("company", "") or ""
        rows_html += f"""<tr>
  <td class="n muted" style="min-width:24px">{i}</td>
  <td><strong>NSE</strong></td>
  <td>{sleeve_chip} <strong style="font-family:monospace">{o['symbol']}</strong></td>
  <td style="color:var(--text2);font-size:11px">{company}</td>
  <td class="n" style="font-weight:700;color:var(--add)">{o['qty']}</td>
  <td style="color:var(--text2)">MARKET</td>
  <td><span style="background:var(--surface2);border-radius:4px;padding:1px 6px;font-size:11px">CNC</span></td>
  <td class="n muted">₹{o['price']:,.2f}</td>
  <td class="n" style="font-weight:600">₹{o['est_cost']:,.0f}</td>
</tr>"""
        copy_lines.append(f"{i}\tNSE\t{o['symbol']}\t{company}\t{o['qty']}\tMARKET\tCNC\t{o['price']:.2f}\t{o['est_cost']:.0f}")

    # ── Already-held reference rows ─────────────────────────────────────────────
    if held_rows:
        rows_html += (
            '<tr class="grp-sep" style="background:var(--surface2)">'
            '<td colspan="9" style="font-size:11px;color:var(--text2);padding:6px 10px;font-weight:600">'
            f'✅ Already held in ICICI Direct — {len(held_rows)} position(s) · slot(s) covered — no new order needed'
            '</td></tr>'
        )
        for h in held_rows:
            sleeve_chip = (
                '<span style="background:#1a7f3720;color:#1a7f37;border-radius:4px;'
                'padding:1px 6px;font-size:10px;font-weight:700">SC</span>'
                if h["sleeve"] == "SC" else
                '<span style="background:#e8932d20;color:#c97418;border-radius:4px;'
                'padding:1px 6px;font-size:10px;font-weight:700">MC</span>'
            )
            rows_html += f"""<tr style="opacity:.6">
  <td class="n muted">—</td>
  <td style="color:var(--text2)">NSE</td>
  <td>{sleeve_chip} <strong style="font-family:monospace">{h['symbol']}</strong></td>
  <td style="color:var(--text2);font-size:11px">{h['company']}</td>
  <td class="n muted">{h['qty']}</td>
  <td style="color:var(--text2)">—</td>
  <td><span style="background:var(--surface2);border-radius:4px;padding:1px 6px;font-size:11px">CNC</span></td>
  <td class="n muted">₹{h['entry']:,.2f} avg</td>
  <td class="n muted" style="font-size:11px">held since {h['entry_date']}</td>
</tr>"""

    total_est = sum(o["est_cost"] for o in all_orders)

    return f"""
<div class="icici-sheet">
  <div class="icici-hdr">
    <span>🏦 ICICI Direct — Order Sheet &nbsp;<span class="icici-date">{run_date} &nbsp;·&nbsp; {len(all_orders)} new order(s) &nbsp;·&nbsp; Est. ₹{total_est:,.0f}</span></span>
    <button class="copy-btn" onclick="copyOrders()">⎘ Copy</button>
  </div>
  <table class="icici-tbl">
    <thead><tr>
      <th>#</th><th>Exchange</th><th>Symbol</th><th>Company</th><th>Qty</th>
      <th>Order Type</th><th>Product</th><th>Ref. Price</th><th>Est. Amount</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
    <tfoot><tr>
      <td colspan="8" style="text-align:right;font-size:12px;color:var(--text2);padding-top:6px">Total new outlay this week</td>
      <td class="n" style="font-weight:700;font-size:13px">₹{total_est:,.0f}</td>
    </tr></tfoot>
  </table>
  <div class="icici-note">
    ⚠ Quantities based on last snapshot price. Verify live price at market open before placing.
    Use <strong>Market order + CNC</strong> for delivery. Exchange: <strong>NSE</strong>.
  </div>
</div>
<textarea id="copyBuf" style="position:absolute;left:-9999px" readonly>{chr(10).join(copy_lines)}</textarea>
<script>
function copyOrders() {{
  var t = document.getElementById('copyBuf');
  t.select(); document.execCommand('copy');
  var b = document.querySelector('.copy-btn');
  b.textContent = '✓ Copied';
  setTimeout(function(){{b.textContent='⎘ Copy'}}, 1800);
}}
</script>"""


def build_fresh_html(fresh_funds: list, run_date: str, rs_p70: float,
                     total_budget: float, next_reb: date,
                     tranche_meta: dict | None = None) -> str:
    """HTML report for inception / staged deployment."""
    total_outlay = 0

    # Pre-compute outlay per fund for the summary bar
    fund_outlays = []
    for fd in fresh_funds:
        result = fd["result"]
        budget = fd["budget"]
        n = fd["n"]
        alloc_per = budget / n
        fo = sum(float(r.get("_fresh_est_cost") or 0) for r in result["adds"])
        fund_outlays.append(fo)
        total_outlay += fo

    fund_sections = ""
    for fd, fund_outlay in zip(fresh_funds, fund_outlays):
        result       = fd["result"]
        budget       = fd["budget"]
        n            = fd["n"]
        n_this_week  = fd.get("n_this_week", n)
        alloc_per    = budget / n
        cap          = fd["cap"]
        already_held = fd.get("already_held", {})

        filter_str = (f"Stage 2 + RS &gt; {fd['rs_p70']:.1f} + Fund ≥ {FUND_SCORE_MIN} + Darvas BUY + ST Bullish"
                      if cap == "SMALL_CAP"
                      else f"Stage 2 + Fund ≥ {FUND_SCORE_MIN} + Darvas BUY + ST Bullish")

        rows_html = ""

        # ── Already-held rows (tranche mode only) ──
        if already_held:
            rows_html += (f'<tr class="grp-sep sep-held"><td colspan="14">'
                          f'✅ Already held — {len(already_held)}/{n} slots</td></tr>')
            for sym, meta in sorted(already_held.items()):
                entry = float(meta.get("entry") or 0)
                edate = meta.get("entry_date", "")
                qty   = int(meta.get("qty") or (alloc_per / entry if entry > 0 else 0))
                hold_sig = ('<span style="font-size:10px;font-weight:700;padding:1px 7px;'
                            'border-radius:4px;background:rgba(30,217,122,.15);color:#1ed97a">HOLD</span>')
                rows_html += f"""<tr class="r-held">
  <td class="n rank-num muted">—</td>
  <td class="sym">{sym}</td>
  <td class="muted">—</td>
  <td class="n muted">₹{entry:,.2f}</td>
  <td class="n muted">—</td>
  <td class="n muted">{qty}</td>
  <td class="n muted">₹{qty*entry:,.0f}</td>
  <td class="n muted">—</td>
  <td class="muted" colspan="4">held since {edate}</td>
  <td></td>
  <td>{hold_sig}</td>
</tr>"""

        rows_html += (f'<tr class="grp-sep sep-add"><td colspan="14">'
                      f'🔵 Buy this week — {len(result["adds"])} of {n_this_week} target slots'
                      f'</td></tr>')

        for add_r in result["adds"]:
            rank  = int(add_r.get("_fresh_rank") or (result["top_n"].index(add_r) + 1))
            price = float(add_r.get("price") or 0)
            qty   = int(add_r.get("_fresh_qty") or _fresh_entry_qty(add_r, alloc_per))
            est_cost  = float(add_r.get("_fresh_est_cost") or (qty * price))
            shortfall = float(add_r.get("_fresh_shortfall") or (alloc_per - est_cost))
            stop = add_r.get("_fresh_stop")
            risk = float(add_r.get("_fresh_risk_rs") or 0)
            sector = add_r.get("_fresh_sector") or add_r.get("sector") or "—"
            binding = add_r.get("_fresh_binding") or "slot"
            price_s   = f"₹{price:,.2f}" if price else "—"
            cost_s    = f"₹{est_cost:,.0f}" if qty else "—"
            short_s   = f"₹{shortfall:,.0f}" if qty else "—"
            stop_s    = f"₹{float(stop):,.2f}" if stop else "—"
            risk_s    = f"₹{risk:,.0f}" if qty else "—"
            sig_html  = _buy_signal_html(
                add_r.get('trading_signal', 'HOLD'),
                add_r.get('trend_signal',   'UNKNOWN'),
                add_r.get('supertrend_state','UNKNOWN'),
            )
            rows_html += f"""<tr class="r-add">
  <td class="n rank-num">#{rank}</td>
  <td class="sym">{add_r['symbol']}</td>
  <td class="muted">{sector}</td>
  <td class="n">{price_s}</td>
  <td class="n muted">{stop_s}</td>
  <td class="n qty-cell">{qty if qty else '—'}</td>
  <td class="n cost-cell">{cost_s}</td>
  <td class="n">{risk_s}</td>
  <td class="n muted">{short_s}</td>
  <td class="muted">{binding}</td>
  <td class="n">{fmt(add_r.get('tech_score'))}</td>
  <td class="n"><span class="{_gc(add_r.get('fund_grade','?'))}">{fmt(add_r.get('fund_score'))}</span> <small>{add_r.get('fund_grade','?')}</small></td>
  <td class="n">{fmt(add_r.get('eq'))}</td>
  <td>{sig_html}</td>
</tr>"""

        if result.get("skipped"):
            rows_html += (f'<tr class="grp-sep sep-watch"><td colspan="14">'
                          f'Skipped before fill — slot / risk / sector / stock cap</td></tr>')
            for skip in result["skipped"]:
                rank = int(skip.get("_fresh_rank") or 0)
                price = float(skip.get("price") or 0)
                price_s = f"₹{price:,.2f}" if price else "—"
                sector = skip.get("_fresh_sector") or skip.get("sector") or "—"
                rows_html += f"""<tr class="r-watch">
  <td class="n rank-num">#{rank}</td>
  <td class="sym">{skip['symbol']}</td>
  <td class="muted">{sector}</td>
  <td class="n muted">{price_s}</td>
  <td class="muted">0</td><td class="muted">—</td>
  <td class="detail" colspan="8">{skip.get('_fresh_skip_reason','not purchasable in this slot')}</td>
</tr>"""

        if len(result["adds"]) < n:
            vacant = n - len(result["adds"])
            rows_html += (f'<tr><td colspan="14" class="detail" style="color:var(--weak);padding:8px 10px">'
                          f'⚠ {vacant} slot(s) vacant — not enough purchasable stocks pass all gates today. '
                          f'Check WATCH list below.</td></tr>')

        if result["watch"]:
            rows_html += (f'<tr class="grp-sep sep-watch"><td colspan="14">'
                          f'👁 Watch — next {WATCH_N} after top {n} (available if a slot opens)</td></tr>')
            for i, w in enumerate(result["watch"], start=1):
                rank = int(w.get("_fresh_rank") or (n + i))
                price_w = float(w.get("price") or 0)
                price_ws = f"₹{price_w:,.2f}" if price_w else "—"
                watch_sig = ('<span style="font-size:10px;font-weight:700;padding:1px 7px;'
                             'border-radius:4px;background:rgba(139,148,158,.12);color:#8b949e">WATCH</span>')
                rows_html += f"""<tr class="r-watch">
  <td class="n rank-num">#{rank}</td>
  <td class="sym">{w['symbol']}</td>
  <td class="muted">{w.get('sector') or '—'}</td>
  <td class="n muted">{price_ws}</td>
  <td></td><td></td><td class="muted">—</td><td></td><td></td><td></td>
  <td class="n">{fmt(w.get('tech_score'))}</td>
  <td class="n"><span class="{_gc(w.get('fund_grade','?'))}">{fmt(w.get('fund_score'))}</span> <small>{w.get('fund_grade','?')}</small></td>
  <td class="n">{fmt(w.get('eq'))}</td>
  <td>{watch_sig}</td>
</tr>"""

        slots_badge = (f'<span class="rb-has-changes">⚠ {len(result["adds"])}/{n} slots filled</span>'
                       if len(result["adds"]) < n
                       else f'<span class="rb-clean">✓ {n}/{n} slots filled</span>')

        fund_sections += f"""<div class="rb-fund">
  <div class="rb-fund-hdr">
    <strong>{fd['name']}</strong>
    <span class="rb-meta">{filter_str} · {len(result['passing'])} pass both gates · ₹{alloc_per:,.0f}/slot</span>
    {slots_badge}
  </div>
  <div class="budget-bar">
    <span>Budget: <strong>₹{budget:,.0f}</strong></span>
    <span style="color:var(--add)">Est. outlay: <strong>₹{fund_outlay:,.0f}</strong></span>
    <span style="color:var(--text3)">Idle cash: <strong>₹{budget - fund_outlay:,.0f}</strong></span>
    <span>Sector cap ₹{_POLICY.sector_cap:,.0f} · Stock cap ₹{_POLICY.single_stock_cap:,.0f} · Risk ₹{_POLICY.trade_risk_normal:,.0f}</span>
  </div>
  <div class="tbl-wrap"><table>
    <thead><tr>
      <th class="n">#</th><th>Symbol</th><th>Sector</th>
      <th class="n">Last Price</th><th class="n">Stop</th><th class="n">Qty</th>
      <th class="n">Est. Cost</th><th class="n">Risk</th><th class="n">Shortfall</th><th>Limit</th>
      <th class="n">TechSc</th><th class="n">FScore</th><th class="n">EQ</th><th>Signal</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
  </table></div>
</div>"""

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Inception Portfolio — {run_date}</title>
<style>
:root{{
  --bg:#f5f7fa;--surface:#fff;--surface2:#eef1f5;--border:#d0d7de;
  --text:#1a2233;--text2:#57606a;--text3:#8b949e;
  --hold:#1a7f37;--add:#0969da;--exit:#cf222e;--weak:#b35c00;
  --shadow:0 1px 3px rgba(0,0,0,.06);
}}
@media(prefers-color-scheme:dark){{:root:not([data-theme="light"]){{
  --bg:#0d1117;--surface:#161b22;--surface2:#1c2128;--border:#30363d;
  --text:#e6edf3;--text2:#8b949e;--text3:#6e7681;
  --hold:#3fb950;--add:#58a6ff;--exit:#f85149;--weak:#fbbf24;
}}}}
:root[data-theme="dark"]{{
  --bg:#0d1117;--surface:#161b22;--surface2:#1c2128;--border:#30363d;
  --text:#e6edf3;--text2:#8b949e;--text3:#6e7681;
  --hold:#3fb950;--add:#58a6ff;--exit:#f85149;--weak:#fbbf24;
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
  font-size:13px;background:var(--bg);color:var(--text);padding:20px 24px;
  max-width:1400px;margin:0 auto}}
h1{{font-size:17px;font-weight:700}}
.page-sub{{font-size:11px;color:var(--text2);margin-top:2px;margin-bottom:14px}}

.inception-banner{{
  background:linear-gradient(135deg,#0550ae 0%,#1a7f37 100%);
  color:#fff;border-radius:10px;padding:18px 22px;margin-bottom:16px}}
.inception-banner h2{{font-size:17px;color:#fff;margin-bottom:5px;font-weight:700}}
.inception-banner p{{font-size:12px;opacity:.88;line-height:1.5}}

.summary-bar{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px}}
.sum-card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;
  padding:10px 16px;box-shadow:var(--shadow)}}
.sum-lbl{{font-size:10px;text-transform:uppercase;letter-spacing:.4px;color:var(--text2)}}
.sum-val{{font-size:18px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.2}}

.section-hdr{{font-size:13px;font-weight:700;padding:12px 0 6px;
  border-bottom:2px solid var(--border);margin-bottom:12px}}

.tbl-wrap{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}}
thead th{{background:var(--surface2);color:var(--text2);font-size:10px;font-weight:700;
  text-transform:uppercase;letter-spacing:.4px;padding:7px 10px;
  border-bottom:1px solid var(--border);white-space:nowrap;text-align:left}}
thead th.n{{text-align:right}}
tbody td{{padding:6px 10px;border-bottom:1px solid var(--border);
  font-size:12px;vertical-align:middle;white-space:nowrap}}
td.n{{text-align:right}}
td.detail{{min-width:160px;white-space:normal;font-size:11px;color:var(--text2)}}
td.muted{{color:var(--text2)}}
.sym{{font-weight:600}}
tbody tr:hover td{{background:var(--surface2)}}
.grp-sep td{{padding:6px 10px;font-size:11px;font-weight:600;
  border-top:2px solid var(--border);border-bottom:1px solid var(--border)}}
.sep-add  td{{color:var(--add);background:rgba(9,105,218,.04)}}
.sep-held td{{color:var(--hold);background:rgba(26,127,55,.04)}}
.sep-watch td{{color:var(--text3);background:var(--surface2)}}
.r-add  td{{background:rgba(9,105,218,.02)}}
.r-held td{{opacity:.55}}
.r-watch td{{opacity:.7}}

/* tranche progress */
.tranche-banner{{background:linear-gradient(135deg,#0550ae,#1a7f37);color:#fff;
  border-radius:10px;padding:16px 20px;margin-bottom:14px}}
.tranche-banner h2{{font-size:16px;font-weight:700;margin-bottom:4px}}
.tranche-banner p{{font-size:12px;opacity:.9}}
.progress-track{{background:rgba(255,255,255,.2);border-radius:6px;height:8px;margin-top:10px}}
.progress-fill{{height:8px;border-radius:6px;background:#fff;transition:width .3s}}

.rb-fund{{background:var(--surface);border:1px solid var(--border);border-radius:10px;
  box-shadow:var(--shadow);margin-bottom:16px;overflow:hidden}}
.rb-fund-hdr{{padding:10px 14px;display:flex;align-items:center;gap:10px;
  flex-wrap:wrap;border-bottom:1px solid var(--border)}}
.rb-meta{{font-size:11px;color:var(--text2);flex:1}}
.rb-has-changes{{font-size:11px;font-weight:600;padding:3px 9px;border-radius:5px;
  background:rgba(217,119,6,.1);color:var(--weak)}}
.rb-clean{{font-size:11px;font-weight:600;padding:3px 9px;border-radius:5px;
  background:rgba(26,127,55,.1);color:var(--hold)}}

.budget-bar{{display:flex;gap:20px;padding:8px 14px;background:var(--surface2);
  border-bottom:1px solid var(--border);font-size:12px;color:var(--text2)}}
.budget-bar strong{{color:var(--text)}}

.ga{{color:var(--hold);font-weight:700}}
.gb{{color:var(--add);font-weight:600}}
.gc{{color:var(--weak);font-weight:600}}
.gf{{color:var(--exit);font-weight:700}}
.gna{{color:var(--text3)}}
.rank-num{{color:var(--text2);font-size:11px;min-width:30px}}
.qty-cell{{font-weight:700;color:var(--add)}}
.cost-cell{{font-weight:600}}

.how-to{{background:var(--surface);border:1px solid var(--border);border-radius:10px;
	  padding:14px 18px;margin-bottom:16px;box-shadow:var(--shadow)}}
  .how-to h3{{font-size:13px;font-weight:700;margin-bottom:10px}}
.how-to ol{{padding-left:18px;line-height:2;font-size:12px}}
.how-to li strong{{color:var(--add)}}
.how-to .note{{font-size:11px;color:var(--text3);margin-top:8px;
  border-top:1px solid var(--border);padding-top:8px}}

.footer{{font-size:11px;color:var(--text3);margin-top:14px;text-align:right}}

/* ── ICICI Direct order sheet ─────────────────── */
.icici-sheet{{background:var(--surface);border:1px solid var(--border);
  border-radius:10px;overflow:hidden;margin-bottom:20px;box-shadow:var(--shadow)}}
.icici-hdr{{display:flex;align-items:center;justify-content:space-between;
  padding:10px 16px;background:linear-gradient(135deg,#f97316,#ea580c);color:#fff;
  font-size:13px;font-weight:700}}
.icici-date{{font-weight:400;opacity:.85;font-size:12px}}
.copy-btn{{background:rgba(255,255,255,.2);border:1px solid rgba(255,255,255,.35);
  color:#fff;border-radius:6px;padding:4px 12px;font-size:12px;cursor:pointer;
  font-weight:600;transition:background .15s}}
.copy-btn:hover{{background:rgba(255,255,255,.35)}}
.icici-tbl{{width:100%;border-collapse:collapse;font-size:12px}}
.icici-tbl thead tr{{background:var(--surface2);font-size:11px;
  text-transform:uppercase;letter-spacing:.04em;color:var(--text3)}}
.icici-tbl th,.icici-tbl td{{padding:8px 12px;border-bottom:1px solid var(--border);
  text-align:left}}
.icici-tbl th{{font-weight:600}}
.icici-tbl tbody tr:hover{{background:var(--surface2)}}
.icici-tbl tfoot tr td{{border-top:2px solid var(--border);border-bottom:none;
  background:var(--surface2)}}
.icici-note{{font-size:11px;color:var(--text3);padding:8px 14px;
  border-top:1px solid var(--border)}}
</style></head><body>

{f'''<div class="tranche-banner">
  <h2>📅 Staged Deployment — {tranche_meta["pct"]:.0f}% tranche</h2>
  <p>{run_date} &nbsp;·&nbsp; Total budget ₹{total_budget:,.0f} &nbsp;·&nbsp;
     Slots: {tranche_meta["held"]} held + {tranche_meta["buying"]} buying today
     → {tranche_meta["after_this"]}/{tranche_meta["total"]} filled
     &nbsp;·&nbsp; Next rebalance Monday {next_reb.strftime("%b %d, %Y")}</p>
  <div class="progress-track">
    <div class="progress-fill" style="width:{min(tranche_meta["after_this"]/tranche_meta["total"]*100,100):.0f}%"></div>
  </div>
</div>''' if tranche_meta else f'''<div class="inception-banner">
  <h2>🚀 Day 1 — Inception Portfolio</h2>
  <p>Starting from zero &nbsp;·&nbsp; {run_date} &nbsp;·&nbsp;
     Total budget ₹{total_budget:,.0f} &nbsp;·&nbsp;
     Next rebalance Monday {next_reb.strftime("%b %d, %Y")}</p>
</div>'''}

<div class="summary-bar">
  <div class="sum-card">
    <div class="sum-lbl">Total budget</div>
    <div class="sum-val">₹{total_budget:,.0f}</div>
  </div>
  <div class="sum-card">
    <div class="sum-lbl">Est. outlay</div>
    <div class="sum-val" style="color:var(--add)">₹{total_outlay:,.0f}</div>
  </div>
  <div class="sum-card">
    <div class="sum-lbl">Idle cash</div>
    <div class="sum-val" style="color:var(--text2)">₹{total_budget - total_outlay:,.0f}</div>
  </div>
  <div class="sum-card">
    <div class="sum-lbl">SC RS p70</div>
    <div class="sum-val">{rs_p70:.1f}</div>
  </div>
  <div class="sum-card">
    <div class="sum-lbl">Fund gate</div>
    <div class="sum-val">≥ {FUND_SCORE_MIN}</div>
  </div>
</div>

<div class="how-to">
  <h3>📋 How to use this paper list</h3>
  <ol>
    <li><strong>Review paper buy rows</strong> for every stock in the table below — verify live price before any execution decision</li>
    <li><strong>Quantity</strong> = min of slot, stop-loss risk, single-stock cap, sector cap, and remaining cash — verify live price and stop before placing</li>
    <li><strong>Idle cash</strong> from fractional shares stays in your account; deploy at next rebalance if a new slot opens</li>
    <li><strong>Daily monitoring</strong> — run <code>python tools/fund_daily.py --html</code> after market close</li>
    <li><strong>Every Monday</strong> — run with <code>--rebalance</code> to see what swaps (if any) to execute</li>
  </ol>
  <div class="note">⚠ Quantities are estimates based on last snapshot price. Always confirm the live price before executing. This is not investment advice.</div>
</div>

<div class="section-hdr">🔵 Your Day 1 Buy List</div>
{fund_sections}

{_build_icici_order_sheet(fresh_funds, run_date)}

<div class="footer">Agent Adda &nbsp;·&nbsp; Inception mode &nbsp;·&nbsp; {run_date} &nbsp;·&nbsp; SC RS p70 = {rs_p70:.1f} &nbsp;·&nbsp; Fund gate ≥ {FUND_SCORE_MIN} &nbsp;·&nbsp; policy {_POLICY.as_of}</div>
</body></html>"""


def _tranche_slots_this_week(n_total: int, pct: float, already_held: int) -> int:
    """How many new slots to fill this week given a staged deployment percentage."""
    import math
    per_tranche = math.ceil(n_total * pct / 100)
    remaining   = n_total - already_held
    return min(per_tranche, remaining)


def run_fresh_start(args, run_date: date, nxt_reb: date) -> None:
    """
    Inception / fresh-start mode.

    Without --tranche : show the full top-N buy list from the current universe.
    With --tranche PCT: staged deployment — reads existing holdings, buys only
                        the next ceil(N × PCT/100) unfilled slots each week.

    Usage:
        python tools/fund_daily.py --fresh --html               # full buy list
        python tools/fund_daily.py --fresh --tranche 25 --html  # week-by-week, 25 % each
    """
    show_sc     = not getattr(args, "mc_only", False)
    show_mc     = not getattr(args, "sc_only", False)
    tranche_pct = getattr(args, "tranche", None)   # float or None

    # ── Load what's already held (empty on Day 1, partial on later tranches)
    existing_sc, existing_mc = load_holdings()
    already_sc = set(existing_sc.keys())
    already_mc = set(existing_mc.keys())

    # ── Budget from shared capital policy (CLI --budget overrides sleeve totals)
    policy = load_capital_policy()
    if args.budget:
        n_funds   = (1 if show_sc else 0) + (1 if show_mc else 0)
        per_fund  = args.budget / max(n_funds, 1)
        sc_budget = per_fund if show_sc else 0.0
        mc_budget = per_fund if show_mc else 0.0
    else:
        sc_budget = policy.budget_sc if show_sc else 0.0
        mc_budget = policy.budget_mc if show_mc else 0.0

    total_budget = sc_budget + mc_budget
    book = ExposureBook(policy, budget_sc=sc_budget, budget_mc=mc_budget)

    print("Connecting to DB…", file=sys.stderr)
    conn = psycopg2.connect(dbname="nse_market", user="pgorai", host="localhost")

    mc150_syms = load_nifty_mc150()
    rs_p70_sc  = compute_rs_p70(conn, "SMALL_CAP")
    print(f"SC RS p70 = {rs_p70_sc:.1f}  |  MC150: {len(mc150_syms)} stocks", file=sys.stderr)

    fresh_funds = []
    if show_sc:
        sc_univ   = fetch_universe(conn, "SMALL_CAP", rs_p70_sc, mc150_syms)
        # Pass already-held holdings so classify_rebalance.adds = unfilled slots only
        sc_result = classify_rebalance(already_sc, sc_univ, SC_N, conn, "SMALL_CAP", rs_p70_sc)
        n_sc_this = (_tranche_slots_this_week(SC_N, tranche_pct, len(already_sc))
                     if tranche_pct else SC_N - len(already_sc))
        fresh_funds.append({
            "name":         "SC S2 — SmallCap Super Performers",
            "cap":          "SMALL_CAP", "n": SC_N,
            "rs_p70":       rs_p70_sc,   "budget": sc_budget,
            "result":       sc_result,
            "already_held": existing_sc,
            "n_this_week":  n_sc_this,
        })
    if show_mc:
        mc_univ   = fetch_universe(conn, "MID_CAP", 0.0, mc150_syms)
        mc_result = classify_rebalance(already_mc, mc_univ, MC_N, conn, "MID_CAP", 0.0)
        n_mc_this = (_tranche_slots_this_week(MC_N, tranche_pct, len(already_mc))
                     if tranche_pct else MC_N - len(already_mc))
        fresh_funds.append({
            "name":         "MC S1 — MidCap Leaders",
            "cap":          "MID_CAP", "n": MC_N,
            "rs_p70":       0.0,       "budget": mc_budget,
            "result":       mc_result,
            "already_held": existing_mc,
            "n_this_week":  n_mc_this,
        })

    conn.close()

    # Seed already-held cost/sector/risk so new rows respect combined caps.
    universe_map = {}
    for fd in fresh_funds:
        for row in fd["result"].get("passing", []):
            universe_map[row["symbol"]] = row
        for row in fd["result"].get("holds", []):
            universe_map.setdefault(row["symbol"], row)
        seed_exposure_from_holdings(
            book, fd["already_held"], universe_map, _sleeve_key(fd["cap"]), policy,
        )

    # ── Select purchasable slots for this week (shared exposure book)
    for fd in fresh_funds:
        fd["result"] = build_fresh_selection(
            fd["result"],
            fd["n_this_week"],
            fd["budget"] / fd["n"],
            skip_syms=set(fd["already_held"].keys()),
            sleeve=_sleeve_key(fd["cap"]),
            policy=policy,
            book=book,
        )

    run_date_str = str(run_date)

    # ── Tranche summary numbers
    tranche_meta = None
    if tranche_pct:
        total_slots = sum(fd["n"] for fd in fresh_funds)
        held_slots  = sum(len(fd["already_held"]) for fd in fresh_funds)
        buy_slots   = sum(len(fd["result"]["adds"]) for fd in fresh_funds)
        tranche_num = (held_slots // (total_slots // (100 // int(tranche_pct)))) + 1 if held_slots < total_slots else None
        tranche_meta = {
            "pct":        tranche_pct,
            "held":       held_slots,
            "buying":     buy_slots,
            "total":      total_slots,
            "after_this": held_slots + buy_slots,
        }

    # ── Terminal output ────────────────────────────────────────────────────────
    W = 80
    if tranche_pct:
        tm = tranche_meta
        print(f"\n{'▶'*W}")
        print(f"  STAGED DEPLOYMENT — {tranche_pct:.0f}% TRANCHE  ·  {run_date_str}")
        print(f"  Holdings: {tm['held']}/{tm['total']} slots filled  →  buying {tm['buying']} more today")
        print(f"  After this: {tm['after_this']}/{tm['total']} slots filled  "
              f"({tm['after_this']/tm['total']*100:.0f}% of portfolio)")
        print(f"  Budget: ₹{total_budget:,.0f}  ·  SC RS p70 = {rs_p70_sc:.1f}  ·  Fund gate ≥ {FUND_SCORE_MIN}")
        print(f"{'▶'*W}")
    else:
        print(f"\n{'★'*W}")
        print(f"  INCEPTION PORTFOLIO  ·  {run_date_str}")
        print(f"  Budget: ₹{total_budget:,.0f}  ·  SC RS p70 = {rs_p70_sc:.1f}  ·  Fund gate ≥ {FUND_SCORE_MIN}")
        print(f"{'★'*W}")

    total_est = 0
    for fd in fresh_funds:
        result    = fd["result"]
        budget    = fd["budget"]
        n         = fd["n"]
        n_this    = fd["n_this_week"]
        alloc_per = budget / n
        held      = fd["already_held"]
        filter_s  = (f"Stage 2 + RS > {fd['rs_p70']:.1f} + Fund ≥ {FUND_SCORE_MIN} + Darvas BUY + ST Bullish"
                     if fd["cap"] == "SMALL_CAP" else f"Stage 2 + Fund ≥ {FUND_SCORE_MIN} + Darvas BUY + ST Bullish")

        print(f"\n  ── {fd['name']}")
        print(f"     Budget ₹{budget:,.0f} / {n} slots = ₹{alloc_per:,.0f}/position")
        if tranche_pct and held:
            print(f"     Already held ({len(held)}): {', '.join(sorted(held.keys()))}")
        print(f"     Buying this week: {len(result['adds'])} of {n_this} target slots")
        print(f"     Filter: {filter_s}  ·  {len(result['passing'])} pass both gates")
        print(f"     Caps: sector ₹{policy.sector_cap:,.0f}  ·  stock ₹{policy.single_stock_cap:,.0f}"
              f"  ·  risk ₹{policy.trade_risk_normal:,.0f}/trade")
        print(f"\n     {'#':<3} {'Symbol':<14} {'Sector':<16} {'Price':>9} {'Stop':>9} {'Qty':>5}"
              f" {'Est.Cost':>10} {'Risk':>8} {'Limit':<8}")
        print(f"     {'─'*96}")

        for add_r in result["adds"]:
            rank  = int(add_r.get("_fresh_rank") or 0)
            price = float(add_r.get("price") or 0)
            qty   = int(add_r.get("_fresh_qty") or _fresh_entry_qty(add_r, alloc_per))
            est   = float(add_r.get("_fresh_est_cost") or (qty * price))
            stop  = add_r.get("_fresh_stop")
            risk  = float(add_r.get("_fresh_risk_rs") or 0)
            total_est += est
            cost_s = f"₹{est:>8,.0f}" if qty else "  no price"
            stop_s = f"₹{float(stop):>8,.2f}" if stop else "        —"
            print(f"     {rank:<3} {add_r['symbol']:<14} {(add_r.get('_fresh_sector') or add_r.get('sector') or '—'):<16}"
                  f" ₹{price:>8,.2f} {stop_s} {qty:>5}  {cost_s} ₹{risk:>6,.0f}"
                  f"  {str(add_r.get('_fresh_binding') or 'slot'):<8}")

        if not result["adds"] and n_this == 0:
            print(f"     ✓ All {n} slots filled — nothing to buy this week")
        elif len(result["adds"]) < n_this:
            print(f"\n     ⚠ Only {len(result['adds'])}/{n_this} slots filled — universe thin today")

        if result.get("skipped"):
            print("\n     Skipped (not purchasable under slot / risk / sector / stock caps):")
            for skip in result["skipped"]:
                rank = int(skip.get("_fresh_rank") or 0)
                print(f"       #{rank:<3} {skip['symbol']:<14}  {skip.get('_fresh_skip_reason','')}")

        if result["watch"]:
            print(f"\n     👁 WATCH (next {WATCH_N} unfilled, available next week):")
            for i, w in enumerate(result["watch"], start=1):
                rank = int(w.get("_fresh_rank") or (n + i))
                print(f"       #{rank:<3} {w['symbol']:<14}  TechSc {fmt(w.get('tech_score'))}"
                      f"  RS {fmt(w.get('rs'), plus=True)}"
                      f"  Fund {fmt(w.get('fund_score'))} [{w.get('fund_grade','?')}]")

    print(f"\n  {'═'*W}")
    idle = total_budget - total_est
    print(f"  THIS WEEK est. outlay: ₹{total_est:,.0f}  (idle cash staying: ₹{idle:,.0f})")
    if tranche_pct and tranche_meta:
        tm = tranche_meta
        remaining_slots = tm["total"] - tm["after_this"]
        remaining_budget = total_budget - (total_budget * tm["after_this"] / tm["total"])
        print(f"  After today: {tm['after_this']}/{tm['total']} slots  ·  "
              f"~₹{remaining_budget:,.0f} remaining for {remaining_slots} slots over next weeks")
    print(f"  Next rebalance: Monday {nxt_reb}")
    print(f"  After buying — update data/fund_holdings.json with fill prices")
    print(f"{'═'*W}")

    # ── HTML ──────────────────────────────────────────────────────────────────
    if getattr(args, "html", False):
        html = build_fresh_html(fresh_funds, run_date_str, rs_p70_sc, total_budget, nxt_reb,
                                tranche_meta=tranche_meta)
        out  = ROOT / "reports" / "latest" / f"fund_inception_{run_date_str.replace('-','')}.html"
        out.write_text(html)
        print(f"Saved: {out}", file=sys.stderr)


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fund Daily Dashboard")
    parser.add_argument("--html",      action="store_true", help="Save HTML")
    parser.add_argument("--rebalance", action="store_true", help="Force rebalance view")
    parser.add_argument("--no-shadow", action="store_true", help="Aug funds only")
    parser.add_argument("--fresh",     action="store_true",
                        help="Fresh start — no existing holdings, show Day 1 buy list")
    parser.add_argument("--budget",    type=float, default=None,
                        help="Total budget in ₹ for fresh start "
                             f"(default: {int(_POLICY.total_nav)} from data/fund_capital_policy.yaml)")
    parser.add_argument("--sc-only",   action="store_true", help="SC fund only (fresh mode)")
    parser.add_argument("--mc-only",   action="store_true", help="MC fund only (fresh mode)")
    parser.add_argument("--tranche",   type=float, default=None, metavar="PCT",
                        help="Staged deployment: buy PCT%% of slots per week (e.g. --tranche 25)")
    args = parser.parse_args()

    run_date = date.today()
    reb_day  = is_monday(run_date) or args.rebalance
    nxt_reb  = next_monday(run_date)

    # ── Fresh start mode ──────────────────────────────────────────────────────
    if args.fresh:
        return run_fresh_start(args, run_date, nxt_reb)

    # ── Load active holdings ──
    global AUG_SC, AUG_MC
    AUG_SC, AUG_MC = load_holdings()
    n_sc = len(AUG_SC);  n_mc = len(AUG_MC)
    if n_sc == 0 and n_mc == 0:
        print("ℹ  No active holdings in fund_holdings.json.", file=sys.stderr)
        print("   Run with --fresh to see the Day 1 buy list.", file=sys.stderr)
        print("   After you buy, add your entries to data/fund_holdings.json.", file=sys.stderr)
        return
    print(f"Holdings: {n_sc} SC + {n_mc} MC positions loaded from fund_holdings.json", file=sys.stderr)

    shadow_sc_map, shadow_mc_map = ({}, {}) if args.no_shadow else load_shadow()
    mc150_syms = load_nifty_mc150()

    # ── All current holdings ──
    all_entries: dict = {**AUG_SC, **AUG_MC}
    for sym, v in {**shadow_sc_map, **shadow_mc_map}.items():
        all_entries.setdefault(sym, v)
    all_syms = sorted(all_entries.keys())

    print(f"Connecting to DB…", file=sys.stderr)
    conn = psycopg2.connect(dbname="nse_market", user="pgorai", host="localhost")

    rs_p70_sc = compute_rs_p70(conn, "SMALL_CAP")
    print(f"SC RS p70 = {rs_p70_sc:.1f}  |  Nifty MC150: {len(mc150_syms)} stocks", file=sys.stderr)

    # ── Daily signals ──
    today_s, yest_s  = fetch_snapshots(all_syms, conn)
    fund_scores      = fetch_fundamental_scores(all_syms, conn)
    signal_rows      = build_signal_rows(all_entries, today_s, yest_s, fund_scores, rs_p70_sc)

    snap_date = next(iter(today_s.values()), {}).get("snapshot_date", str(run_date))

    # ── Rebalance ──
    sc_universe = fetch_universe(conn, "SMALL_CAP", rs_p70_sc, mc150_syms)
    mc_universe = fetch_universe(conn, "MID_CAP",   0.0,       mc150_syms)

    aug_sc_holdings    = set(AUG_SC.keys())
    aug_mc_holdings    = set(AUG_MC.keys())
    shadow_sc_holdings = set(shadow_sc_map.keys())
    shadow_mc_holdings = set(shadow_mc_map.keys())

    rebalance_funds = [
        {"name": "Aug SC  (S2 — Stage 2 + RS + Fund)",
         "result": classify_rebalance(aug_sc_holdings, sc_universe, SC_N, conn, "SMALL_CAP", rs_p70_sc),
         "cap": "SMALL_CAP", "n": SC_N, "rs_p70": rs_p70_sc},
        {"name": "Aug MC  (S1 — Stage 2 + Fund)",
         "result": classify_rebalance(aug_mc_holdings, mc_universe, MC_N, conn, "MID_CAP", 0.0),
         "cap": "MID_CAP", "n": MC_N, "rs_p70": 0.0},
    ]
    if not args.no_shadow and shadow_sc_holdings:
        rebalance_funds.append({
            "name": "Shadow SC (S2)",
            "result": classify_rebalance(shadow_sc_holdings, sc_universe, SC_N, conn, "SMALL_CAP", rs_p70_sc),
            "cap": "SMALL_CAP", "n": SC_N, "rs_p70": rs_p70_sc,
        })
    if not args.no_shadow and shadow_mc_holdings:
        rebalance_funds.append({
            "name": "Shadow MC (S1)",
            "result": classify_rebalance(shadow_mc_holdings, mc_universe, MC_N, conn, "MID_CAP", 0.0),
            "cap": "MID_CAP", "n": MC_N, "rs_p70": 0.0,
        })

    conn.close()

    # ── Output ──
    run_date_str = str(run_date)

    if args.html:
        html = build_html(signal_rows, rebalance_funds, run_date_str, snap_date,
                          reb_day, nxt_reb, rs_p70_sc)
        out = ROOT / "reports" / "latest" / f"fund_daily_{run_date_str.replace('-','')}.html"
        out.write_text(html)
        print(f"Saved: {out}", file=sys.stderr)

    # Terminal
    if reb_day:
        print(f"\n{'★'*60}")
        print(f"  REBALANCE DAY — {run_date_str}")
        print(f"{'★'*60}")
    else:
        days_to = (nxt_reb - run_date).days
        print(f"\nNext rebalance: Monday {nxt_reb} ({days_to} day{'s' if days_to!=1 else ''} away)")

    # P&L summary — how is the portfolio doing?
    pnl = compute_fund_pnl(signal_rows)
    print_pnl_summary(pnl)

    # Trade list — the actionable layer
    trade_list = build_trade_list(signal_rows, rebalance_funds, nxt_reb)
    print_trade_list(trade_list)

    print_signals(signal_rows, rs_p70_sc, run_date_str)

    print(f"\n{'═'*80}")
    print(f"  WEEKLY REBALANCE VIEW {'— EXECUTE TODAY' if reb_day else '(preview)'}")
    print(f"{'═'*80}")
    for f in rebalance_funds:
        print_rebalance(f["name"], f["result"], f["rs_p70"], f["cap"], f["n"])

    total = sum(len(f["result"]["adds"]) for f in rebalance_funds)
    print(f"\n  Total swaps if rebalancing today: {total}")


if __name__ == "__main__":
    main()
