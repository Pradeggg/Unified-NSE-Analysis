#!/usr/bin/env python3
"""NSE Market Breadth & Relative Rotation Graph (RRG) Report.

Outputs reports/latest/market_breadth_rrg.html with:
  1. Broad-market RRG   — cap-size universes vs Nifty 500 (current + 4-week trail)
  2. Sector timeline    — 4 snapshot RRGs showing sector rotation over time
  3. Breadth table      — constituent-level % above 50D / 150D / 200D + Stage-2 count
"""

from __future__ import annotations

import json
import os
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

ROOT = Path(__file__).resolve().parent

# Load .env so OPENAI_API_KEY and OPENAI_MODEL are available
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass
REPORTS_DIR = ROOT / "reports" / "latest"
MAPPING_CSV = ROOT / "data" / "index_stock_mapping.csv"
INDEX_DATA_CSV = ROOT / "data" / "nse_index_data.csv"

PG_DSN = (
    os.environ.get("AGENT_ADDA_PG_DSN")
    or os.environ.get("PG_DSN")
    or "dbname=nse_market user=nse_admin host=/tmp"
)

RRG_BENCHMARK = "Nifty 500"

# ── Index universe config for broad-market RRG ────────────────────────────────
BROAD_INDICES = [
    {"sym": "Nifty 50",          "label": "NIFTY 50",       "color": "#f59e0b", "mapping": "NIFTY 50"},
    {"sym": "Nifty Next 50",     "label": "NEXT 50",         "color": "#fbbf24", "mapping": "NIFTY NEXT 50"},
    {"sym": "Nifty 100",         "label": "NIFTY 100",       "color": "#f59e0b", "mapping": "NIFTY 100"},
    {"sym": "Nifty 200",         "label": "NIFTY 200",       "color": "#f59e0b", "mapping": "NIFTY 200"},
    {"sym": "NIFTY TOTAL MKT",   "label": "TOTAL MKT",       "color": "#94a3b8", "mapping": None},
    {"sym": "NIFTY LARGEMID250", "label": "LARGEMID 250",    "color": "#60a5fa", "mapping": "NIFTY LARGEMIDCAP 250"},
    {"sym": "NIFTY MIDSML 400",  "label": "MIDSML 400",      "color": "#60a5fa", "mapping": None},
    {"sym": "NIFTY MID SELECT",  "label": "MIDCAP SELECT",   "color": "#34d399", "mapping": "NIFTY MIDCAP SELECT"},
    {"sym": "NIFTY MIDCAP 100",  "label": "MIDCAP 100",      "color": "#34d399", "mapping": "NIFTY MIDCAP 100"},
    {"sym": "NIFTY MIDCAP 150",  "label": "MIDCAP 150",      "color": "#34d399", "mapping": "NIFTY MIDCAP 150"},
    {"sym": "Nifty Midcap 50",   "label": "MIDCAP 50",       "color": "#34d399", "mapping": "NIFTY MIDCAP 50"},
    {"sym": "NIFTY SMLCAP 50",   "label": "SMALLCAP 50",     "color": "#a78bfa", "mapping": None},
    {"sym": "NIFTY SMLCAP 100",  "label": "SMALLCAP 100",    "color": "#a78bfa", "mapping": None},
    {"sym": "NIFTY SMLCAP 250",  "label": "SMALLCAP 250",    "color": "#a78bfa", "mapping": None},
    {"sym": "NIFTY MICROCAP250", "label": "MICROCAP 250",    "color": "#c084fc", "mapping": "NIFTY MICROCAP 250"},
    {"sym": "Nifty Bank",        "label": "BANK NIFTY",      "color": "#22d3ee", "mapping": "NIFTY BANK"},
]

# ── Sector indices for the rotation timeline ──────────────────────────────────
SECTOR_INDICES = [
    {"sym": "Nifty Auto",        "label": "Auto"},
    {"sym": "Nifty Bank",        "label": "Bank"},
    {"sym": "Nifty Capital Mkt", "label": "Capital Mkt"},
    {"sym": "Nifty Cement",      "label": "Cement"},
    {"sym": "Nifty Chemicals",   "label": "Chemicals"},
    {"sym": "Nifty Commodities", "label": "Commodities"},
    {"sym": "NIFTY CONSR DURBL", "label": "Cons Durables"},
    {"sym": "Nifty Energy",      "label": "Energy"},
    {"sym": "Nifty Fin Service", "label": "Fin Services"},
    {"sym": "Nifty FMCG",        "label": "FMCG"},
    {"sym": "Nifty Housing",     "label": "Housing"},
    {"sym": "Nifty Ind Defence", "label": "Defence"},
    {"sym": "Nifty Infra",       "label": "Infra"},
    {"sym": "Nifty IT",          "label": "IT"},
    {"sym": "Nifty Media",       "label": "Media"},
    {"sym": "Nifty Metal",       "label": "Metal"},
    {"sym": "Nifty Pharma",      "label": "Pharma"},
    {"sym": "Nifty PSU Bank",    "label": "PSU Bank"},
    {"sym": "Nifty Pvt Bank",    "label": "Pvt Bank"},
    {"sym": "Nifty Realty",      "label": "Realty"},
]

# ── Sector RRG indices (current snapshot, colored by sector group) ─────────
SECTOR_RRG_INDICES = [
    # Financials — blue family
    {"sym": "Nifty Bank",        "label": "BANK",          "color": "#3b82f6"},
    {"sym": "Nifty Pvt Bank",    "label": "PVT BANK",      "color": "#60a5fa"},
    {"sym": "Nifty PSU Bank",    "label": "PSU BANK",      "color": "#93c5fd"},
    {"sym": "Nifty Fin Service", "label": "FIN SERVICES",  "color": "#2563eb"},
    {"sym": "Nifty Capital Mkt", "label": "CAPITAL MKT",   "color": "#1d4ed8"},
    # Energy / Commodities — red-orange family
    {"sym": "Nifty Energy",      "label": "ENERGY",        "color": "#ef4444"},
    {"sym": "Nifty Commodities", "label": "COMMODITIES",   "color": "#f97316"},
    {"sym": "Nifty Metal",       "label": "METAL",         "color": "#fb923c"},
    {"sym": "Nifty Cement",      "label": "CEMENT",        "color": "#fbbf24"},
    {"sym": "Nifty Chemicals",   "label": "CHEMICALS",     "color": "#f59e0b"},
    # Consumer / FMCG — green-teal family
    {"sym": "Nifty FMCG",        "label": "FMCG",          "color": "#10b981"},
    {"sym": "NIFTY CONSR DURBL", "label": "CONS DURABLE",  "color": "#34d399"},
    {"sym": "Nifty Media",       "label": "MEDIA",         "color": "#6ee7b7"},
    {"sym": "Nifty Realty",      "label": "REALTY",        "color": "#059669"},
    {"sym": "Nifty Housing",     "label": "HOUSING",       "color": "#0d9488"},
    # Tech — purple
    {"sym": "Nifty IT",          "label": "IT",            "color": "#a78bfa"},
    # Healthcare — cyan
    {"sym": "Nifty Pharma",      "label": "PHARMA",        "color": "#06b6d4"},
    # Infra / Capital Goods — lime
    {"sym": "Nifty Infra",       "label": "INFRA",         "color": "#84cc16"},
    {"sym": "Nifty Ind Defence", "label": "DEFENCE",       "color": "#65a30d"},
    # Auto — yellow
    {"sym": "Nifty Auto",        "label": "AUTO",          "color": "#eab308"},
]

# ── Thematic RRG indices (colored by theme cluster) ───────────────────────
THEMATIC_RRG_INDICES = [
    # New Economy — purple
    {"sym": "Nifty EV",          "label": "EV",            "color": "#a78bfa"},
    {"sym": "Nifty Internet",    "label": "INTERNET",      "color": "#c084fc"},
    {"sym": "NIFTY IND DIGITAL", "label": "DIGITAL",       "color": "#818cf8"},
    {"sym": "Nifty IPO",         "label": "IPO",           "color": "#6d28d9"},
    {"sym": "Nifty Mobility",    "label": "MOBILITY",      "color": "#7c3aed"},
    # Government / PSU / Infra — amber-gold
    {"sym": "Nifty CPSE",        "label": "CPSE",          "color": "#f59e0b"},
    {"sym": "Nifty RailwaysPSU", "label": "RAILWAYS PSU",  "color": "#fbbf24"},
    {"sym": "Nifty Multi Infra", "label": "MULTI INFRA",   "color": "#d97706"},
    {"sym": "Nifty Multi Mfg",   "label": "MULTI MFG",     "color": "#b45309"},
    {"sym": "NIFTY INDIA MFG",   "label": "INDIA MFG",     "color": "#92400e"},
    # Consumption / Rural — green
    {"sym": "Nifty Consumption", "label": "CONSUMPTION",   "color": "#34d399"},
    {"sym": "Nifty New Consump", "label": "NEW CONSUMP",   "color": "#10b981"},
    {"sym": "Nifty Rural",       "label": "RURAL",         "color": "#059669"},
    # Tourism / MNC / Other — cyan-teal
    {"sym": "Nifty Ind Tourism", "label": "TOURISM",       "color": "#22d3ee"},
    {"sym": "Nifty MNC",         "label": "MNC",           "color": "#06b6d4"},
    {"sym": "NiftyConglomerate", "label": "CONGLOMERATES", "color": "#0891b2"},
]

# Breadth indices (those with constituent mapping)
BREADTH_INDICES = [
    {"sym": "Nifty 500",         "label": "NIFTY 500",       "mapping": "NIFTY 500"},
    {"sym": "Nifty 50",          "label": "NIFTY 50",        "mapping": "NIFTY 50"},
    {"sym": "Nifty 100",         "label": "NIFTY 100",       "mapping": "NIFTY 100"},
    {"sym": "Nifty 200",         "label": "NIFTY 200",       "mapping": "NIFTY 200"},
    {"sym": "NIFTY LARGEMID250", "label": "LARGEMID 250",    "mapping": "NIFTY LARGEMIDCAP 250"},
    {"sym": "NIFTY MID SELECT",  "label": "MIDCAP SELECT",   "mapping": "NIFTY MIDCAP SELECT"},
    {"sym": "NIFTY MIDCAP 100",  "label": "MIDCAP 100",      "mapping": "NIFTY MIDCAP 100"},
    {"sym": "NIFTY MIDCAP 150",  "label": "MIDCAP 150",      "mapping": "NIFTY MIDCAP 150"},
    {"sym": "Nifty Midcap 50",   "label": "MIDCAP 50",       "mapping": "NIFTY MIDCAP 50"},
    {"sym": "NIFTY MICROCAP250", "label": "MICROCAP 250",    "mapping": "NIFTY MICROCAP 250"},
    {"sym": "Nifty Bank",        "label": "BANK NIFTY",      "mapping": "NIFTY BANK"},
    {"sym": "Nifty Next 50",     "label": "NEXT 50",         "mapping": "NIFTY NEXT 50"},
]

# 4 snapshot dates for the sector timeline
SNAPSHOT_TARGETS = ["2025-12-15", "2026-02-03", "2026-04-01", "2026-06-25"]


# ── Data loading ──────────────────────────────────────────────────────────────

def _pg():
    return psycopg2.connect(PG_DSN)


def load_index_history() -> pd.DataFrame:
    all_syms = list(dict.fromkeys(
        [RRG_BENCHMARK]
        + [d["sym"] for d in BROAD_INDICES]
        + [d["sym"] for d in SECTOR_INDICES]
        + [d["sym"] for d in SECTOR_RRG_INDICES]
        + [d["sym"] for d in THEMATIC_RRG_INDICES]
    ))
    try:
        conn = _pg()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = pd.read_sql_query(
                """SELECT index_symbol AS "SYMBOL",
                          trade_date  AS "TIMESTAMP",
                          close       AS "CLOSE"
                   FROM market.index_eod
                   ORDER BY index_symbol, trade_date""",
                conn,
            )
        conn.close()
    except Exception as exc:
        print(f"Postgres unavailable ({exc}); using CSV fallback")
        df = pd.read_csv(INDEX_DATA_CSV, parse_dates=["TIMESTAMP"])
        df = df[["SYMBOL", "TIMESTAMP", "CLOSE"]]
    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"])
    return df


def load_equity_history(symbols: list[str]) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame()
    try:
        conn = _pg()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = pd.read_sql_query(
                """SELECT symbol, trade_date, close
                   FROM market.equity_eod
                   WHERE symbol = ANY(%s)
                     AND trade_date >= (SELECT MAX(trade_date) FROM market.equity_eod)
                                       - INTERVAL '400 days'
                   ORDER BY symbol, trade_date""",
                conn,
                params=[symbols],
            )
        conn.close()
    except Exception as exc:
        print(f"Equity data error: {exc}")
        return pd.DataFrame()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df


# ── RRG computation (broad market) ───────────────────────────────────────────

def compute_rrg(
    index_df: pd.DataFrame,
    indices: list[dict] | None = None,
    trail_weeks: int = 4,
) -> list[dict]:
    """
    Compute JdK-style RS-Ratio and RS-Momentum for each index in `indices` vs Nifty 500.
    If `indices` is None, defaults to BROAD_INDICES.

    RS-Ratio  = (EMA10 / EMA40 - 1) * 100  (% deviation of fast RS from slow RS)
    RS-Mom    = smoothed diff(10) of RS-Ratio
    Quadrant  = Leading / Improving / Weakening / Lagging based on sign of each
    """
    if indices is None:
        indices = BROAD_INDICES

    df = index_df.copy()
    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"])
    pivot = df.pivot_table(index="TIMESTAMP", columns="SYMBOL", values="CLOSE", aggfunc="last").sort_index()

    if RRG_BENCHMARK not in pivot.columns:
        print(f"Benchmark {RRG_BENCHMARK!r} missing"); return []

    bm = pivot[RRG_BENCHMARK].dropna()
    results: list[dict] = []

    for cfg in indices:
        sym = cfg["sym"]
        if sym not in pivot.columns:
            continue

        idx = pivot[sym].dropna()
        both = pd.DataFrame({"i": idx, "b": bm}).dropna()
        if len(both) < 30:
            continue

        rs_raw  = both["i"] / both["b"] * 100
        rs_fast = rs_raw.ewm(span=10, adjust=False, min_periods=5).mean()
        rs_slow = rs_raw.ewm(span=40, adjust=False, min_periods=20).mean()
        rs_ratio  = (rs_fast / rs_slow - 1) * 100          # % deviation, centred at 0
        # Smooth RS-Ratio before differencing to suppress daily noise in trail lines
        rs_ratio_s = rs_ratio.ewm(span=5, adjust=False).mean()
        rs_mom = rs_ratio_s.diff(10).fillna(0)              # 2-week rate of change

        def _safe_val(series, offset=0):
            idx2 = -(offset + 1)
            if abs(idx2) > len(series):
                return None
            v = float(series.iloc[idx2])
            return round(v, 3) if not np.isnan(v) else None

        # Use smoothed series for both current position and trail to reduce jaggedness
        current_x = _safe_val(rs_ratio_s)
        current_y = _safe_val(rs_mom)
        if current_x is None or current_y is None:
            continue

        trail = []
        for step in range(trail_weeks, 0, -1):
            # Weekly (5-day) steps back on the smoothed series
            tx = _safe_val(rs_ratio_s, step * 5)
            ty = _safe_val(rs_mom,     step * 5)
            if tx is not None and ty is not None:
                trail.append({"x": tx, "y": ty})

        quadrant = _quad(current_x, current_y)
        results.append({
            "sym": sym, "label": cfg["label"], "color": cfg["color"],
            "x": current_x, "y": current_y,
            "trail": trail, "quadrant": quadrant,
        })

    return results


def _quad(x: float, y: float) -> str:
    if x >= 0 and y >= 0: return "LEADING"
    if x <  0 and y >= 0: return "IMPROVING"
    if x >= 0 and y <  0: return "WEAKENING"
    return "LAGGING"


# ── Sector rotation timeline ──────────────────────────────────────────────────

def _nearest_date(pivot: pd.DataFrame, target: str) -> pd.Timestamp | None:
    t = pd.Timestamp(target)
    candidates = pivot.index[pivot.index <= t]
    return candidates[-1] if len(candidates) > 0 else None


def compute_sector_timeline(index_df: pd.DataFrame) -> dict[str, list[dict]]:
    """
    For each snapshot date compute percentile-ranked RS and Momentum (0–100).
    RS       = 63-day excess return vs Nifty 500 → percentile rank
    Momentum = 21-day excess return vs Nifty 500 → percentile rank
    Color    = gradient from orange (weak) to green (strong) by Momentum rank
    """
    df = index_df.copy()
    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"])
    pivot = df.pivot_table(index="TIMESTAMP", columns="SYMBOL", values="CLOSE", aggfunc="last").sort_index()

    bm_col = RRG_BENCHMARK
    if bm_col not in pivot.columns:
        return {}

    label_map = {d["sym"]: d["label"] for d in SECTOR_INDICES}
    sector_syms = [d["sym"] for d in SECTOR_INDICES if d["sym"] in pivot.columns]

    timeline: dict[str, list[dict]] = {}

    for target in SNAPSHOT_TARGETS:
        snap_ts = _nearest_date(pivot, target)
        if snap_ts is None:
            continue
        hist = pivot[:snap_ts]

        bm_series = hist[bm_col].dropna()
        if len(bm_series) < 25:
            continue

        rows = []
        for sym in sector_syms:
            if sym not in hist.columns:
                continue
            idx_series = hist[sym].dropna()
            both = pd.DataFrame({"i": idx_series, "b": bm_series}).dropna()
            if len(both) < 25:
                continue

            n63 = min(63, len(both) - 1)
            n21 = min(21, len(both) - 1)

            rs_63 = (both["i"].iloc[-1] / both["b"].iloc[-1]) / \
                    (both["i"].iloc[-(n63+1)] / both["b"].iloc[-(n63+1)]) - 1
            rs_21 = (both["i"].iloc[-1] / both["b"].iloc[-1]) / \
                    (both["i"].iloc[-(n21+1)] / both["b"].iloc[-(n21+1)]) - 1

            rows.append({"sym": sym, "label": label_map.get(sym, sym),
                         "rs_63": rs_63 * 100, "rs_21": rs_21 * 100})

        if not rows:
            continue

        sc = pd.DataFrame(rows)
        sc["x"] = sc["rs_63"].rank(pct=True) * 100   # 0–100 percentile
        sc["y"] = sc["rs_21"].rank(pct=True) * 100

        def _color(mom: float) -> str:
            if mom >= 70: return "#34d399"    # strong green
            if mom >= 55: return "#a3e635"    # yellow-green
            if mom >= 40: return "#fbbf24"    # amber
            return "#f97316"                  # orange (weak)

        sc["color"] = sc["y"].apply(_color)
        date_label = snap_ts.strftime("%d %b %Y").upper()
        timeline[date_label] = sc[["sym","label","x","y","color"]].round(1).to_dict("records")

    return timeline


def _rotation_narrative(timeline: dict, current_sector_rrg: list[dict] | None = None) -> str:
    """Describe current sector leaders plus historical timeline movements."""
    dates = list(timeline.keys())
    current_sector_rrg = current_sector_rrg or []
    parts = []

    current_leaders = [r["label"] for r in current_sector_rrg if r.get("quadrant") == "LEADING"]
    current_laggards = [r["label"] for r in current_sector_rrg if r.get("quadrant") == "LAGGING"]
    if current_leaders:
        parts.append(f"<strong>Current sector leaders:</strong> {', '.join(current_leaders[:5])}")
    if current_laggards:
        parts.append(f"<strong>Current sector laggards:</strong> {', '.join(current_laggards[:5])}")

    if len(dates) < 2:
        return " &nbsp;·&nbsp; ".join(parts)
    first, last = timeline[dates[0]], timeline[dates[-1]]

    def quadrant(pts, sym):
        for p in pts:
            if p["sym"] == sym:
                return _quad(p["x"] - 50, p["y"] - 50)
        return None

    movers = []
    for d in SECTOR_INDICES:
        s = d["sym"]
        q0, q1 = quadrant(first, s), quadrant(last, s)
        if q0 and q1 and q0 != q1:
            movers.append(f"{d['label']} ({q0} → {q1})")

    leaders = [p["label"] for p in last if _quad(p["x"]-50, p["y"]-50) == "LEADING"]
    laggards = [p["label"] for p in last if _quad(p["x"]-50, p["y"]-50) == "LAGGING"]

    if leaders:
        parts.append(f"<strong>Historical checkpoint leaders ({dates[-1]}):</strong> {', '.join(leaders[:5])}")
    if laggards:
        parts.append(f"<strong>Historical checkpoint laggards ({dates[-1]}):</strong> {', '.join(laggards[:5])}")
    if movers:
        parts.append(f"<strong>Big moves ({dates[0]} → {dates[-1]}):</strong> {'; '.join(movers[:6])}")
    return " &nbsp;·&nbsp; ".join(parts)


# ── Breadth computation ───────────────────────────────────────────────────────

def compute_breadth(equity_df: pd.DataFrame, mapping_df: pd.DataFrame) -> list[dict]:
    if equity_df.empty:
        return []

    equity_df = equity_df.copy()
    equity_df["trade_date"] = pd.to_datetime(equity_df["trade_date"])
    pivot = equity_df.pivot_table(index="trade_date", columns="symbol", values="close", aggfunc="last").sort_index()

    results = []
    for cfg in BREADTH_INDICES:
        mapping_name = cfg.get("mapping")
        if not mapping_name:
            continue
        members = mapping_df[mapping_df["INDEX_NAME"] == mapping_name]["STOCK_SYMBOL"].tolist()
        available = [s for s in members if s in pivot.columns]
        if len(available) < 5:
            continue

        mc = pivot[available]
        sma50  = mc.rolling(50,  min_periods=35).mean()
        sma150 = mc.rolling(150, min_periods=100).mean()
        sma200 = mc.rolling(200, min_periods=150).mean()

        lc    = mc.iloc[-1]
        l50   = sma50.iloc[-1]
        l150  = sma150.iloc[-1]
        l200  = sma200.iloc[-1]

        n = lc.notna().sum()
        if n == 0:
            continue

        pct50  = round((lc > l50).sum()  / n * 100)
        pct150 = round((lc > l150).sum() / n * 100)
        pct200 = round((lc > l200).sum() / n * 100)

        # RS: % with positive 3M excess return vs Nifty 500 (using Nifty 500 median as proxy)
        pct_rs = None
        if len(mc) >= 63:
            ret_3m = (mc.iloc[-1] / mc.iloc[-63].replace(0, np.nan) - 1) * 100
            pct_rs = round((ret_3m > 0).sum() / n * 100)

        # Stage 2: above 50D + above 200D + within 25% of 52W high
        # Compute 52W high from available price history
        high_252 = mc.rolling(252, min_periods=180).max().iloc[-1]
        stg2 = 0
        for sym in available:
            c, s50, s200, h52 = lc.get(sym), l50.get(sym), l200.get(sym), high_252.get(sym)
            if any(pd.isna(v) for v in [c, s50, s200, h52]) or h52 == 0:
                continue
            if c > s50 and c > s200 and c / h52 >= 0.75:
                stg2 += 1

        comp_vals = [v for v in [pct_rs, pct50, pct150, pct200] if v is not None]
        comp = round(sum(comp_vals) / len(comp_vals)) if comp_vals else None

        results.append({
            "label": cfg["label"], "n": n,
            "comp": comp, "rs": pct_rs,
            "above_50d": pct50, "above_150d": pct150, "above_200d": pct200,
            "stg2": stg2,
        })

    results.sort(key=lambda r: r["comp"] or 0, reverse=True)
    return results


# ── LLM Narrative ────────────────────────────────────────────────────────────

def generate_llm_narrative(
    rrg_results: list[dict],
    timeline: dict[str, list[dict]],
    breadth_results: list[dict],
    as_of: str,
    view: str = "broad_market",
    current_sector_rrg: list[dict] | None = None,
) -> str:
    """Call OpenAI to generate a rich market analyst narrative from the computed data.
    Returns HTML string. Falls back to empty string on error."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key or api_key.startswith("your-"):
        return ""

    # Build structured context for the LLM
    by_q: dict[str, list[str]] = {"LEADING": [], "IMPROVING": [], "WEAKENING": [], "LAGGING": []}
    for r in rrg_results:
        by_q[r["quadrant"]].append(f"{r['label']} (RS={r['x']:+.2f}%, Mom={r['y']:+.2f}%)")

    sector_by_q: dict[str, list[str]] = {"LEADING": [], "IMPROVING": [], "WEAKENING": [], "LAGGING": []}
    for r in current_sector_rrg or []:
        sector_by_q[r["quadrant"]].append(f"{r['label']} (RS={r['x']:+.2f}%, Mom={r['y']:+.2f}%)")

    breadth_summary = "\n".join(
        f"  {r['label']:20s}  COMP={r['comp'] or '?':>3}  >50D={r['above_50d']:>3}%  "
        f">200D={r['above_200d']:>3}%  >30W={r['above_150d']:>3}%  STG2={r['stg2']}"
        for r in breadth_results
    )

    timeline_dates = list(timeline.keys())
    timeline_summary = ""
    for d, pts in timeline.items():
        leaders  = [p["label"] for p in pts if _quad(p["x"]-50, p["y"]-50) == "LEADING"]
        laggards = [p["label"] for p in pts if _quad(p["x"]-50, p["y"]-50) == "LAGGING"]
        timeline_summary += f"  {d}: Leaders={leaders[:4]}  Laggards={laggards[:4]}\n"

    # Biggest sector movers (first → last snapshot)
    movers = []
    if len(timeline_dates) >= 2:
        first_pts = {p["label"]: _quad(p["x"]-50, p["y"]-50) for p in timeline[timeline_dates[0]]}
        last_pts  = {p["label"]: _quad(p["x"]-50, p["y"]-50) for p in timeline[timeline_dates[-1]]}
        for label in first_pts:
            if label in last_pts and first_pts[label] != last_pts[label]:
                movers.append(f"{label}: {first_pts[label]} → {last_pts[label]}")

    context = f"""NSE MARKET BREADTH & RRG SNAPSHOT — As of {as_of}
Benchmark: Nifty 500

═══ BROAD MARKET RRG (16 cap-size universes vs Nifty 500) ═══
LEADING   (outperforming, accelerating): {', '.join(by_q['LEADING']) or 'None'}
IMPROVING (underperforming, momentum +): {', '.join(by_q['IMPROVING']) or 'None'}
WEAKENING (outperforming, momentum -):  {', '.join(by_q['WEAKENING']) or 'None'}
LAGGING   (underperforming, declining): {', '.join(by_q['LAGGING']) or 'None'}

═══ CONSTITUENT BREADTH (sorted by COMP score) ═══
{breadth_summary}

═══ CURRENT SECTOR RRG ({as_of}; use this for any current sector-leadership claim) ═══
LEADING: {', '.join(sector_by_q['LEADING']) or 'Not supplied'}
IMPROVING: {', '.join(sector_by_q['IMPROVING']) or 'Not supplied'}
WEAKENING: {', '.join(sector_by_q['WEAKENING']) or 'Not supplied'}
LAGGING: {', '.join(sector_by_q['LAGGING']) or 'Not supplied'}

═══ SECTOR ROTATION TIMELINE ═══
(historical checkpoints only; do not describe the latest checkpoint as current if CURRENT SECTOR RRG is supplied)
(X = RS percentile rank 0-100; Y = Momentum rank 0-100; quadrant boundary at 50)
{timeline_summary}

═══ BIGGEST SECTOR MOVERS ({timeline_dates[0] if timeline_dates else ''} → {timeline_dates[-1] if timeline_dates else ''}) ═══
{chr(10).join(movers) or 'No major quadrant crossings detected'}
"""

    view_context = {
        "broad_market": "cap-size universe rotation (Nifty 50 vs Midcap vs Smallcap vs Microcap)",
        "sector": "NSE sector rotation (Auto, Bank, IT, Metal, Pharma etc. vs Nifty 500)",
        "thematic": "NSE thematic index rotation (EV, Digital, Railways, Manufacturing, Rural etc. vs Nifty 500)",
    }.get(view, "market rotation")

    prompt = f"""You are a senior Indian equity market analyst with deep knowledge of NSE indices,
sector rotation, and market breadth. This is a {view_context} RRG analysis.
Based on the following data snapshot, write a structured market intelligence report
with exactly these 4 sections. Be specific, use the data, write like a real analyst — not a textbook.

DATA:
{context}

Write the report in this exact format (use HTML tags for formatting):

<h3>Market Character</h3>
<p>[2-3 sentences on the overall picture from this RRG view — what is leading, what is lagging,
and what that reveals about the current market cycle. Reference specific index names and RS values.]</p>

<h3>Who's Leading & Why It Matters</h3>
<p>[2-3 sentences specifically on the LEADING quadrant indices in this view.
What does their leadership mean for investors? Reference RS and momentum values.]</p>

<h3>The Rotation Story</h3>
<p>[2-3 sentences on the notable movements — what has shifted quadrant, what was previously
leading and is now weakening, what was lagging and is now improving. Be specific.]</p>

<h3>Trade Implications</h3>
<p>[2-3 actionable sentences. Where should a swing trader be looking? Which cap segment?
Which sectors? What to avoid? Be direct and specific.]</p>

Keep each section tight — 2-3 sentences maximum. Do NOT add disclaimers or preambles.
Start directly with the <h3> tag."""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        model = os.environ.get("OPENAI_MODEL", "gpt-4o")
        create_kwargs: dict = dict(
            model=model,
            messages=[
                {"role": "system", "content": "You are a senior NSE equity market analyst. Be concise, data-specific, and actionable."},
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=700,
        )
        # gpt-5.5 and o-series models don't support temperature; skip if default
        if not model.startswith(("o1", "o3", "gpt-5")):
            create_kwargs["temperature"] = 0.4
        resp = client.chat.completions.create(**create_kwargs)
        raw = resp.choices[0].message.content or ""
        return raw.strip()
    except Exception as exc:
        print(f"  LLM narrative error: {exc}")
        return ""


# ── HTML generator ────────────────────────────────────────────────────────────

def _heat_bg(val: float | None, lo: int = 40, hi: int = 75) -> str:
    if val is None:
        return "rgba(30,41,59,0.5)"
    t = max(0.0, min(1.0, (val - lo) / (hi - lo)))
    if t < 0.5:
        r = int(160 + (80-160) * t * 2)
        g = int(60  + (160-60) * t * 2)
        b = 60
    else:
        r = int(80  + (40-80)  * (t-0.5) * 2)
        g = int(160 + (190-160)* (t-0.5) * 2)
        b = int(60  + (80-60)  * (t-0.5) * 2)
    return f"rgba({r},{g},{b},0.38)"


def _breadth_row(r: dict) -> str:
    def cell(val, lo=40, hi=75):
        bg = _heat_bg(val, lo, hi)
        txt = str(val) if val is not None else "—"
        return (f'<td style="background:{bg};color:#e2e8f0;text-align:center;'
                f'padding:8px 6px;font-weight:600;font-size:13px">{txt}</td>')

    stg2_c = "#60a5fa" if (r["stg2"] or 0) >= 30 else "#94a3b8"
    return (f'<tr>'
            f'<td style="padding:8px 14px;font-weight:600;color:#e2e8f0;font-size:13px">{r["label"]}</td>'
            f'<td style="padding:8px 6px;color:#475569;text-align:center;font-size:11px">{r["n"]}</td>'
            + cell(r["comp"]) + cell(r["rs"]) + cell(r["above_50d"])
            + cell(r["above_200d"]) + cell(r["above_150d"])
            + f'<td style="padding:8px 6px;color:{stg2_c};text-align:center;font-weight:700">{r["stg2"]}</td>'
            + '</tr>')


def _focus_avoid_strip(rrg_results: list[dict]) -> str:
    """Render the three-column Focus / Caution / Avoid strip."""
    focus   = " ".join(f'<span class="focus-pill">▲ {r["label"]}</span>'   for r in rrg_results if r["quadrant"] == "LEADING")
    caution = " ".join(f'<span class="caution-pill">↘ {r["label"]}</span>' for r in rrg_results if r["quadrant"] == "WEAKENING")
    avoid   = " ".join(f'<span class="avoid-pill">▼ {r["label"]}</span>'   for r in rrg_results if r["quadrant"] == "LAGGING")
    improving = " ".join(f'<span style="display:inline-flex;align-items:center;gap:5px;background:#0c1a2e;border:1px solid #1e3a5f;color:#60a5fa;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;margin:2px">↗ {r["label"]}</span>' for r in rrg_results if r["quadrant"] == "IMPROVING")
    return f"""
<div style="background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:14px 18px;margin-bottom:16px;display:flex;flex-wrap:wrap;gap:14px;align-items:flex-start">
  <div style="flex:1;min-width:180px">
    <div style="font-size:10px;font-weight:800;letter-spacing:.08em;color:#4ade80;margin-bottom:5px">▲ LEADING — focus</div>
    <div>{focus or '<span style="color:#334155;font-size:11px">—</span>'}</div>
  </div>
  <div style="flex:1;min-width:180px">
    <div style="font-size:10px;font-weight:800;letter-spacing:.08em;color:#60a5fa;margin-bottom:5px">↗ IMPROVING — watch</div>
    <div>{improving or '<span style="color:#334155;font-size:11px">—</span>'}</div>
  </div>
  <div style="flex:1;min-width:180px">
    <div style="font-size:10px;font-weight:800;letter-spacing:.08em;color:#fb923c;margin-bottom:5px">↘ WEAKENING — caution</div>
    <div>{caution or '<span style="color:#334155;font-size:11px">—</span>'}</div>
  </div>
  <div style="flex:1;min-width:180px">
    <div style="font-size:10px;font-weight:800;letter-spacing:.08em;color:#f87171;margin-bottom:5px">▼ LAGGING — avoid</div>
    <div>{avoid or '<span style="color:#334155;font-size:11px">—</span>'}</div>
  </div>
  <div style="width:100%;margin-top:4px;font-size:10px;color:#334155">
    Chart: <span style="color:#34d399;font-weight:700">▲ glow = leading</span> &nbsp;·&nbsp;
    <span style="color:#fb923c;font-weight:700">↘ normal = weakening</span> &nbsp;·&nbsp;
    <span style="color:#f87171;font-weight:700">▼ dashed ring = lagging</span>
  </div>
</div>"""


def _rrg_chart_section(
    title: str,
    kicker: str,
    canvas_id: str,
    rrg_results: list[dict],
    llm_narrative: str = "",
    as_of: str = "",
) -> str:
    """Render a self-contained RRG chart card (focus strip + chart + narrative)."""
    json_var  = f"RRG_{canvas_id}"
    strip_html = _focus_avoid_strip(rrg_results)
    narr_block = ""
    if llm_narrative:
        narr_block = f"""
<div style="margin-top:14px;background:#0f172a;border-left:3px solid #3b82f6;border-radius:0 8px 8px 0;padding:14px 18px">
  <div style="font-size:10px;font-weight:800;letter-spacing:.08em;color:#60a5fa;margin-bottom:8px">&#x1F9E0; AI ANALYSIS — {as_of}</div>
  <style>
    .ai-narr-{canvas_id} h3{{font-size:11px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:#93c5fd;margin:12px 0 3px 0}}
    .ai-narr-{canvas_id} p{{margin:0 0 2px 0;color:#cbd5e1;font-size:13px;line-height:1.75}}
  </style>
  <div class="ai-narr-{canvas_id}">{llm_narrative}</div>
  <div style="margin-top:8px;font-size:10px;color:#334155">Generated by {os.environ.get("OPENAI_MODEL","GPT")}. Not investment advice.</div>
</div>"""

    chart_js = f"""
const {json_var} = {json.dumps(rrg_results, ensure_ascii=False)};
(function() {{
  const Q_R = {{LEADING:13,IMPROVING:9,WEAKENING:10,LAGGING:8}};
  const Q_O = {{LEADING:'ff',IMPROVING:'cc',WEAKENING:'bb',LAGGING:'88'}};
  new Chart(document.getElementById('{canvas_id}'), {{
    type: 'scatter',
    data: {{ datasets: [{{
      data: {json_var}.map(d => ({{x:d.x, y:d.y}})),
      backgroundColor: {json_var}.map(d => d.color + (Q_O[d.quadrant]||'cc')),
      pointRadius: {json_var}.map(d => Q_R[d.quadrant]||10),
      pointHoverRadius: {json_var}.map(d => (Q_R[d.quadrant]||10)+3),
      datalabels: {{
        align: 'top', anchor: 'center', offset: 8,
        color: {json_var}.map(d => d.color),
        font: ctx => ({{size: {json_var}[ctx.dataIndex]?.quadrant==='LEADING'?11:9,
                       weight: {json_var}[ctx.dataIndex]?.quadrant==='LEADING'?'800':'600'}}),
        formatter: (_,ctx) => {{
          const d = {json_var}[ctx.dataIndex]; if(!d) return '';
          const ic = d.quadrant==='LEADING'?' ▲':d.quadrant==='WEAKENING'?' ↘':d.quadrant==='LAGGING'?' ▼':' ↗';
          return d.label+ic;
        }},
      }},
    }}] }},
    options: {{
      responsive:true, maintainAspectRatio:false, animation:false,
      layout:{{padding:{{top:24,right:30,bottom:10,left:10}}}},
      scales:{{
        x:{{type:'linear',grid:{{color:'rgba(148,163,184,0.1)'}},
            ticks:{{color:'#475569',callback:v=>v.toFixed(1)+'%'}},
            title:{{display:true,text:'RS-Ratio (% deviation vs Nifty 500)',color:'#475569',font:{{size:11}}}}}},
        y:{{type:'linear',grid:{{color:'rgba(148,163,184,0.1)'}},
            ticks:{{color:'#475569',callback:v=>v.toFixed(1)+'%'}},
            title:{{display:true,text:'RS-Momentum (rate of change)',color:'#475569',font:{{size:11}}}}}},
      }},
      plugins:{{
        legend:{{display:false}},
        datalabels:{{display:true}},
        tooltip:{{
          backgroundColor:'#1e293b',borderColor:'#334155',borderWidth:1,
          titleColor:'#e2e8f0',bodyColor:'#94a3b8',
          callbacks:{{
            title: items => {json_var}[items[0].dataIndex]?.label||'',
            label: item => [
              'RS-Ratio: '+item.raw.x.toFixed(2)+'%',
              'RS-Momentum: '+item.raw.y.toFixed(2)+'%',
              'Quadrant: '+({json_var}[item.dataIndex]?.quadrant||''),
            ],
          }},
        }},
      }},
    }},
    plugins: [makeQPlugin(0,0), makeTrailPlugin({json_var})],
  }});
}})();
"""
    return strip_html + f"""
<div class="card">
  <div class="sec-title">{kicker}</div>
  <div style="font-size:1rem;font-weight:700;color:#e2e8f0;margin-bottom:14px">{title}</div>
  <div style="position:relative;height:520px"><canvas id="{canvas_id}"></canvas></div>
  <div style="margin-top:8px;font-size:11px;color:#475569;text-align:center">
    X = RS-Ratio (outperforming Nifty 500 = positive) &nbsp;·&nbsp;
    Y = RS-Momentum (accelerating = positive) &nbsp;·&nbsp; Trail = 4 weekly checkpoints
  </div>
  {narr_block}
</div>
<script>{chart_js}</script>
"""


def generate_html(
    rrg_results: list[dict],
    sector_rrg: list[dict],
    thematic_rrg: list[dict],
    timeline: dict[str, list[dict]],
    breadth_results: list[dict],
    as_of: str,
    llm_broad: str = "",
    llm_sector: str = "",
    llm_thematic: str = "",
) -> str:

    # Quadrant summary cards
    by_q: dict[str, list[str]] = {"LEADING": [], "IMPROVING": [], "WEAKENING": [], "LAGGING": []}
    for r in rrg_results:
        by_q[r["quadrant"]].append(r["label"])

    q_card_html = ""
    for q, color, desc in [
        ("LEADING",   "#34d399", "Outperforming — momentum accelerating"),
        ("IMPROVING", "#fbbf24", "Underperforming — momentum turning positive"),
        ("WEAKENING", "#f97316", "Outperforming — momentum fading"),
        ("LAGGING",   "#f87171", "Underperforming — momentum declining"),
    ]:
        badges = "".join(
            f'<span style="display:inline-block;background:{color}20;color:{color};'
            f'padding:2px 8px;border-radius:10px;margin:2px 2px 0 0;'
            f'font-size:11px;font-weight:600">{l}</span>'
            for l in by_q[q]
        ) or f'<span style="color:#475569;font-size:11px">—</span>'
        q_card_html += (
            f'<div style="background:{color}0f;border:1px solid {color}30;border-radius:10px;'
            f'padding:14px;flex:1;min-width:190px">'
            f'<div style="font-size:10px;font-weight:800;letter-spacing:.08em;color:{color};'
            f'margin-bottom:3px">{q}</div>'
            f'<div style="font-size:11px;color:#64748b;margin-bottom:8px">{desc}</div>'
            f'<div>{badges}</div></div>'
        )

    # Breadth table
    breadth_html = "".join(_breadth_row(r) for r in breadth_results)

    # Timeline captions
    timeline_dates = list(timeline.keys())
    snap_narr = _rotation_narrative(timeline, sector_rrg)

    # JSON payloads
    rrg_json     = json.dumps(rrg_results,  ensure_ascii=False)
    timeline_json = json.dumps(timeline,     ensure_ascii=False)

    timeline_grid = ""
    for d in timeline_dates:
        timeline_grid += (
            f'<div style="flex:1;min-width:240px">'
            f'<div style="text-align:center;font-size:12px;font-weight:800;letter-spacing:.08em;'
            f'color:#94a3b8;margin-bottom:8px">{d}</div>'
            f'<div style="position:relative;height:300px">'
            f'<canvas id="tl_{d.replace(" ","")}"></canvas></div></div>'
        )

    # Render the three RRG chart sections
    broad_section    = _rrg_chart_section(
        "Cap-Size Universe RRG",
        "BROAD MARKET — MOMENTUM VS RELATIVE STRENGTH (vs Nifty 500)",
        "rrgBroad", rrg_results, llm_broad, as_of,
    )
    sector_section   = _rrg_chart_section(
        "Sectoral RRG",
        "SECTOR ROTATION — 20 NSE SECTORS vs Nifty 500",
        "rrgSector", sector_rrg, llm_sector, as_of,
    )
    thematic_section = _rrg_chart_section(
        "Thematic Indices RRG",
        "THEMATIC ROTATION — EV · DIGITAL · RAILWAYS · RURAL · MNC vs Nifty 500",
        "rrgThematic", thematic_rrg, llm_thematic, as_of,
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NSE Market Breadth &amp; RRG — {as_of}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0/dist/chartjs-plugin-datalabels.min.js"></script>
<style>
:root{{--bg:#0f172a;--card:#1e293b;--bdr:#334155;--txt:#e2e8f0;--mu:#94a3b8;--rad:12px}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--txt);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Inter",sans-serif;font-size:14px;line-height:1.6}}
.hdr{{background:linear-gradient(135deg,#1e3a5f,#0f172a);padding:22px 28px;border-bottom:1px solid var(--bdr)}}
.kicker{{font-size:10px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:#60a5fa;margin-bottom:3px}}
.htitle{{font-size:1.5rem;font-weight:800;letter-spacing:-.02em;margin-bottom:2px}}
.hsub{{font-size:12px;color:var(--mu)}}
.wrap{{max-width:1440px;margin:0 auto;padding:20px 24px}}
.card{{background:var(--card);border:1px solid var(--bdr);border-radius:var(--rad);padding:20px;margin-bottom:20px}}
.sec-title{{font-size:10px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--mu);margin-bottom:14px}}
.disc{{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:8px 14px;font-size:11px;color:#475569;margin-bottom:16px}}
table{{width:100%;border-collapse:collapse}}
th{{padding:8px 6px;font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--mu);text-align:center;border-bottom:1px solid var(--bdr)}}
th.left{{text-align:left;padding-left:14px}}
tr:hover{{background:rgba(59,130,246,.04)}}
.focus-pill{{display:inline-flex;align-items:center;gap:5px;background:#052e16;border:1px solid #166534;color:#4ade80;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;margin:2px}}
.avoid-pill{{display:inline-flex;align-items:center;gap:5px;background:#2d0a0a;border:1px solid #7f1d1d;color:#f87171;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;margin:2px}}
.caution-pill{{display:inline-flex;align-items:center;gap:5px;background:#1c1004;border:1px solid #78350f;color:#fb923c;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;margin:2px}}
.view-nav{{display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap}}
.view-nav a{{display:inline-block;padding:6px 16px;border-radius:20px;border:1px solid #334155;
  background:#1e293b;color:#94a3b8;font-size:11px;font-weight:700;text-decoration:none;letter-spacing:.05em}}
.view-nav a:hover{{background:#334155;color:#e2e8f0}}
</style>
</head>
<body>

<!-- ── Shared plugin definitions — must precede all chart scripts ──────── -->
<script>
Chart.register(ChartDataLabels);

function makeQPlugin(cx0, cy0) {{
  return {{
    id: 'quad_' + cx0 + '_' + cy0,
    beforeDraw(chart) {{
      const {{ctx, chartArea:{{left:L,top:T,right:R,bottom:B}}, scales:{{x,y}}}} = chart;
      const cx = x.getPixelForValue(cx0), cy = y.getPixelForValue(cy0);
      const fill = (x1,y1,x2,y2,c) => {{ ctx.fillStyle=c; ctx.fillRect(x1,y1,x2-x1,y2-y1); }};
      fill(cx,T,R,cy,  'rgba(52,211,153,0.08)');
      fill(L, T,cx,cy, 'rgba(245,158,11,0.08)');
      fill(L, cy,cx,B, 'rgba(239,68,68,0.08)');
      fill(cx,cy,R,B,  'rgba(249,115,22,0.08)');
      ctx.save();
      ctx.strokeStyle='rgba(148,163,184,0.3)'; ctx.lineWidth=1; ctx.setLineDash([5,5]);
      ctx.beginPath(); ctx.moveTo(cx,T); ctx.lineTo(cx,B);
      ctx.moveTo(L,cy); ctx.lineTo(R,cy); ctx.stroke(); ctx.setLineDash([]);
      ctx.font='bold 9px -apple-system,sans-serif'; ctx.fillStyle='rgba(148,163,184,0.5)';
      ctx.textAlign='right';  ctx.fillText('LEADING',   R-6,T+13);
      ctx.textAlign='left';   ctx.fillText('IMPROVING', L+6,T+13);
      ctx.textAlign='left';   ctx.fillText('LAGGING',   L+6,B-4);
      ctx.textAlign='right';  ctx.fillText('WEAKENING', R-6,B-4);
      ctx.restore();
    }}
  }};
}}

function makeTrailPlugin(data) {{
  return {{
    id: 'trails_' + Math.random().toString(36).slice(2),
    afterDatasetsDraw(chart) {{
      const {{ctx, scales:{{x,y}}}} = chart;
      data.forEach(d => {{
        const pts = [...d.trail, {{x:d.x, y:d.y}}];
        const px_now = x.getPixelForValue(d.x), py_now = y.getPixelForValue(d.y);

        if (d.quadrant === 'LEADING') {{
          ctx.save();
          const grad = ctx.createRadialGradient(px_now,py_now,8,px_now,py_now,22);
          grad.addColorStop(0, d.color+'50'); grad.addColorStop(1, d.color+'00');
          ctx.beginPath(); ctx.arc(px_now,py_now,22,0,Math.PI*2);
          ctx.fillStyle=grad; ctx.fill();
          ctx.beginPath(); ctx.arc(px_now,py_now,14,0,Math.PI*2);
          ctx.strokeStyle=d.color+'aa'; ctx.lineWidth=2; ctx.stroke();
          ctx.restore();
        }}
        if (d.quadrant === 'LAGGING') {{
          ctx.save(); ctx.beginPath(); ctx.arc(px_now,py_now,13,0,Math.PI*2);
          ctx.strokeStyle='#f8717160'; ctx.lineWidth=1.5; ctx.setLineDash([3,3]);
          ctx.stroke(); ctx.setLineDash([]); ctx.restore();
        }}
        if (pts.length < 2) return;
        ctx.save();
        ctx.strokeStyle=d.color+'70'; ctx.lineWidth=1.5;
        ctx.beginPath();
        pts.forEach((p,i) => {{
          const px=x.getPixelForValue(p.x), py=y.getPixelForValue(p.y);
          i===0 ? ctx.moveTo(px,py) : ctx.lineTo(px,py);
        }});
        ctx.stroke();
        pts.slice(0,-1).forEach((p,i) => {{
          const a = Math.round((i+1)/pts.length*140).toString(16).padStart(2,'0');
          ctx.beginPath(); ctx.fillStyle=d.color+a;
          ctx.arc(x.getPixelForValue(p.x),y.getPixelForValue(p.y),3,0,Math.PI*2); ctx.fill();
        }});
        ctx.restore();
      }});
    }}
  }};
}}
</script>

<div class="hdr">
  <div class="kicker">NSE Equity Dashboard &nbsp;·&nbsp; RRG &amp; Breadth</div>
  <div class="htitle">Market Rotation Intelligence</div>
  <div class="hsub">As of {as_of} &nbsp;·&nbsp; Benchmark: Nifty 500 &nbsp;·&nbsp; Three views: Cap-Size · Sector · Thematic</div>
</div>

<div class="wrap">
<div class="disc">Not investment advice. Educational AI/rules-based market intelligence only. Validate all data independently before acting.</div>

<nav class="view-nav">
  <a href="#broad">&#x1F4CA; Broad Market (Cap-Size)</a>
  <a href="#sector">&#x1F3ED; Sectoral (20 sectors)</a>
  <a href="#thematic">&#x1F680; Thematic (EV·Digital·Railways·Rural)</a>
  <a href="#timeline">&#x23F3; Rotation Timeline</a>
  <a href="#breadth">&#x1F4C8; Breadth Table</a>
</nav>

<!-- ── Broad-market quadrant summary ──────────────────────────────────── -->
<div id="broad">
<div class="card">
  <div class="sec-title">Broad Market — The Rotation (Cap-Size Universes)</div>
  <div style="display:flex;flex-wrap:wrap;gap:12px">{q_card_html}</div>
</div>
{broad_section}
</div>

<!-- ── Sector rotation timeline ───────────────────────────────────────── -->
<div id="timeline" class="card">
  <div class="sec-title">Sector Rotation — Historical Snapshots (4 checkpoints)</div>
  <div style="display:flex;flex-wrap:wrap;gap:16px">{timeline_grid}</div>
  <div style="margin-top:10px;font-size:10px;color:#334155;text-align:center">
    Dot size = distance from quadrant boundary · Labels for extreme-quadrant sectors · Boundary at 50
  </div>
  <div style="margin-top:14px;display:flex;flex-wrap:wrap;gap:10px" id="sectorArcLabels"></div>
  {'<div style="margin-top:12px;background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:12px 16px;font-size:12px;color:#94a3b8;line-height:1.85">' + snap_narr + '</div>' if snap_narr else ''}
</div>

<!-- ── Sectoral RRG ────────────────────────────────────────────────────── -->
<div id="sector">
{sector_section}
</div>

<!-- ── Thematic RRG ───────────────────────────────────────────────────── -->
<div id="thematic">
{thematic_section}
</div>

<!-- ── Breadth table ──────────────────────────────────────────────────── -->
<div id="breadth" class="card">
  <div class="sec-title">Trend Health — % Stocks Above Key Moving Averages</div>
  <div style="overflow-x:auto">
  <table>
    <thead><tr>
      <th class="left">Universe</th>
      <th style="color:#475569;font-weight:500">Count</th>
      <th>Composite</th><th>RS</th><th>&gt;50D</th><th>&gt;200D</th><th>&gt;30W</th>
      <th style="color:#60a5fa">STG2</th>
    </tr></thead>
    <tbody>{breadth_html}</tbody>
  </table>
  </div>
  <div style="margin-top:10px;font-size:11px;color:#475569">
    Colour: red=weak → green=strong &nbsp;·&nbsp; RS = % stocks with positive 3M return &nbsp;·&nbsp;
    STG2 = Stage 2 (above 50D &amp; 200D SMA, within 25% of 52W high) &nbsp;·&nbsp; 30W ≈ 150-day SMA
  </div>
</div>

</div><!-- /wrap -->

<script>
const TIMELINE = {timeline_json};

// ── Sector timeline charts ───────────────────────────────────────────────
Object.entries(TIMELINE).forEach(([dateLabel, pts]) => {{
  const canvasId = 'tl_' + dateLabel.replace(/ /g,'');
  const el = document.getElementById(canvasId);
  if (!el) return;
  const sorted_x = [...pts].sort((a,b) => a.x-b.x);
  const q25_x = sorted_x[Math.floor(sorted_x.length*0.25)]?.x ?? 25;
  const q75_x = sorted_x[Math.floor(sorted_x.length*0.75)]?.x ?? 75;
  const sorted_y = [...pts].sort((a,b) => a.y-b.y);
  const q25_y = sorted_y[Math.floor(sorted_y.length*0.25)]?.y ?? 25;
  const q75_y = sorted_y[Math.floor(sorted_y.length*0.75)]?.y ?? 75;
  new Chart(el, {{
    type: 'scatter',
    data: {{ datasets: [{{
      data: pts.map(p => ({{x:p.x, y:p.y}})),
      backgroundColor: pts.map(p => p.color),
      pointRadius: pts.map(p => {{
        const dist = Math.sqrt((p.x-50)**2 + (p.y-50)**2);
        return dist > 30 ? 9 : dist > 18 ? 7 : 5;
      }}),
      pointHoverRadius: 12,
      datalabels: {{
        display: (ctx) => {{
          const p = pts[ctx.dataIndex];
          return (p.x > q75_x && p.y > q75_y) || (p.x < q25_x && p.y < q25_y)
              || (p.x > q75_x && p.y < q25_y) || (p.x < q25_x && p.y > q75_y);
        }},
        formatter: (_,ctx) => pts[ctx.dataIndex]?.label || '',
        color: (ctx) => pts[ctx.dataIndex]?.color || '#e2e8f0',
        font: {{size: 8, weight: '700'}},
        align: 'top', anchor: 'center', offset: 4,
        backgroundColor: 'rgba(15,23,42,0.75)', borderRadius: 3,
        padding: {{top:2,bottom:2,left:4,right:4}},
      }},
    }}] }},
    options: {{
      responsive:true, maintainAspectRatio:false, animation:false, layout:{{padding:4}},
      scales: {{
        x: {{type:'linear',min:0,max:100,grid:{{color:'rgba(148,163,184,0.08)'}},ticks:{{color:'#475569',font:{{size:9}},maxTicksLimit:5}},title:{{display:false}}}},
        y: {{type:'linear',min:0,max:100,grid:{{color:'rgba(148,163,184,0.08)'}},ticks:{{color:'#475569',font:{{size:9}},maxTicksLimit:5}},title:{{display:false}}}},
      }},
      plugins: {{
        legend:{{display:false}}, datalabels:{{display:false}},
        tooltip:{{backgroundColor:'#1e293b',borderColor:'#334155',borderWidth:1,
          titleColor:'#e2e8f0',bodyColor:'#94a3b8',
          callbacks:{{title:items=>pts[items[0].dataIndex]?.label||'',
            label:item=>['RS rank: '+item.raw.x.toFixed(0),'Mom rank: '+item.raw.y.toFixed(0)]}}}},
      }},
    }},
    plugins: [makeQPlugin(50,50)],
  }});
}});

// ── Sector arc legend ────────────────────────────────────────────────────
(function() {{
  const container = document.getElementById('sectorArcLabels');
  if (!container) return;
  Object.entries(TIMELINE).forEach(([dateLabel, pts]) => {{
    const leaders  = pts.filter(p => p.x > 60 && p.y > 60).sort((a,b)=>(b.x+b.y)-(a.x+a.y));
    const laggards = pts.filter(p => p.x < 40 && p.y < 40).sort((a,b)=>(a.x+a.y)-(b.x+b.y));
    const col = document.createElement('div');
    col.style.cssText = 'flex:1;min-width:180px;background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:10px 12px';
    let html = `<div style="font-size:10px;font-weight:800;letter-spacing:.06em;color:#64748b;margin-bottom:6px">${{dateLabel}}</div>`;
    if (leaders.length) {{
      html += `<div style="font-size:10px;color:#4ade80;font-weight:700;margin-bottom:3px">▲ Leading</div>`;
      leaders.slice(0,4).forEach(p => {{ html += `<div style="font-size:11px;color:#e2e8f0;padding:1px 0">${{p.label}}</div>`; }});
    }}
    if (laggards.length) {{
      html += `<div style="font-size:10px;color:#f87171;font-weight:700;margin-top:6px;margin-bottom:3px">▼ Lagging</div>`;
      laggards.slice(0,4).forEach(p => {{ html += `<div style="font-size:11px;color:#94a3b8;padding:1px 0">${{p.label}}</div>`; }});
    }}
    col.innerHTML = html;
    container.appendChild(col);
  }});
}})();
</script>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> str:
    print("─" * 60)
    print("NSE Market Breadth & RRG Report")
    print("─" * 60)

    print("\n[1/5] Loading index EOD data from postgres...")
    index_df = load_index_history()
    as_of = index_df["TIMESTAMP"].max().strftime("%d %b %Y") if not index_df.empty else datetime.now().strftime("%d %b %Y")
    print(f"      Data as of: {as_of} | {index_df['SYMBOL'].nunique()} indices, {len(index_df):,} rows")

    print("\n[2/5] Computing RRGs (broad + sector + thematic)...")
    rrg_results  = compute_rrg(index_df, BROAD_INDICES)
    sector_rrg   = compute_rrg(index_df, SECTOR_RRG_INDICES)
    thematic_rrg = compute_rrg(index_df, THEMATIC_RRG_INDICES)
    for label, data in [("Broad", rrg_results), ("Sector", sector_rrg), ("Thematic", thematic_rrg)]:
        print(f"      [{label}] {len(data)} indices")
        for r in data:
            print(f"        {r['label']:22s}  x={r['x']:+.2f}%  y={r['y']:+.2f}%  [{r['quadrant']}]")

    print("\n[3/5] Computing sector rotation timeline...")
    timeline = compute_sector_timeline(index_df)
    for d, pts in timeline.items():
        leaders  = [p["label"] for p in pts if _quad(p["x"]-50, p["y"]-50) == "LEADING"]
        laggards = [p["label"] for p in pts if _quad(p["x"]-50, p["y"]-50) == "LAGGING"]
        print(f"      {d}: {len(pts)} sectors | Leaders: {leaders[:3]} | Laggards: {laggards[:3]}")

    print("\n[4/5] Computing constituent breadth...")
    mapping_df = pd.read_csv(MAPPING_CSV)
    all_syms = mapping_df["STOCK_SYMBOL"].unique().tolist()
    equity_df = load_equity_history(all_syms)
    print(f"      {len(equity_df):,} rows | {equity_df['symbol'].nunique() if not equity_df.empty else 0} symbols")
    breadth_results = compute_breadth(equity_df, mapping_df)
    for r in breadth_results:
        print(f"      {r['label']:20s}  COMP={r['comp']}  >50D={r['above_50d']}  >200D={r['above_200d']}  STG2={r['stg2']}")

    print("\n[5/6] Generating LLM narratives (broad + sector + thematic)...")
    llm_broad    = generate_llm_narrative(rrg_results,  timeline, breadth_results, as_of, view="broad_market", current_sector_rrg=sector_rrg)
    llm_sector   = generate_llm_narrative(sector_rrg,   {},       [],              as_of, view="sector")
    llm_thematic = generate_llm_narrative(thematic_rrg, {},       [],              as_of, view="thematic")
    for label, narr in [("broad", llm_broad), ("sector", llm_sector), ("thematic", llm_thematic)]:
        print(f"      [{label}] {'OK' if narr else 'skipped'}")

    print("\n[6/6] Generating HTML...")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    html = generate_html(
        rrg_results, sector_rrg, thematic_rrg,
        timeline, breadth_results, as_of,
        llm_broad, llm_sector, llm_thematic,
    )
    out = REPORTS_DIR / "market_breadth_rrg.html"
    out.write_text(html, encoding="utf-8")
    print(f"\n✓ Report → {out}")
    print("─" * 60)
    return str(out)


if __name__ == "__main__":
    main()
