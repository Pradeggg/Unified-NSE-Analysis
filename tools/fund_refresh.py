#!/usr/bin/env python3
"""
fund_refresh.py — End-to-end Aug Fund Dashboard Refresh
========================================================
Reads  : data/fund_holdings.json  (single source of truth for all positions)
Fetches: Live prices via yfinance + DB snapshots, fundamentals, quarterly results
Applies: Fund rules compliance gate for each position
Writes : reports/latest/fund_dashboard.html  (self-contained, clickable modals)
Opens  : Browser (unless --no-open)

Usage:
  python tools/fund_refresh.py                # full refresh + open browser
  python tools/fund_refresh.py --no-open      # refresh only, don't open
  python tools/fund_refresh.py --prices-only  # refresh live prices only then regenerate
  python tools/fund_refresh.py --skip-prices  # use cached prices, just regenerate HTML
  python tools/fund_refresh.py --skip-news    # skip yfinance news fetch (~3-8s saved)
"""

import argparse
import json
import sys
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

import os
import yfinance as yf

ROOT = Path(__file__).parent.parent

# Load parent .env so OPENAI_API_KEY etc. are available when run standalone
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

# ── Paths ──────────────────────────────────────────────────────────────────
HOLDINGS_FILE  = ROOT / "data" / "fund_holdings.json"
EXITS_FILE     = ROOT / "data" / "fund_exits.json"
PRICES_CACHE   = ROOT / "data" / "fund_prices_cache.json"
DASHBOARD_OUT  = ROOT / "reports" / "latest" / "fund_dashboard.html"
TODAY          = date.today()

# ── NSE symbol → DB symbol map (where they differ) ────────────────────────
NSE_TO_DB = {
    "BLSE":       "BLSE",
    "EIMCOELECO": "EIMCOELECO",
    "RATNAVEER":  "RATNAVEER",
    "SKYGOLD":    "SKYGOLD",
    "SANSERA":    "SANSERA",
    "RUBCORP":    "RUBICON",      # screener/DB slug: RUBICON
    "RRKABEL":    "RRKABEL",
    "CUPID":      "CUPID",
    "MANORAMA":   "MANORAMA",
    "SYRMA":      "SYRMA",
    "ENDURANCE":  "ENDURANCE",
    "COFORGE":    "COFORGE",
    "FEDERALBNK": "FEDERALBNK",
    "ATHERENERG": "ATHERENERG",
    "NYKAA":      "NYKAA",
    "OFSS":       "OFSS",
    "SONACOMS":   "SONACOMS",
    "SENORES":    "SENORES",
    "GNA":        "GNA",
    "WSTCSTPAPR": "WSTCSTPAPR",
    "LLOYDSME":   "LLOYDSME",
    "CARYSIL":    "CARYSIL",
    "SGMART":     "SGMART",
    "HSCL":       "HSCL",
    "ASIANENE":   "ASIANENE",
    "THYROCARE":  "THYROCARE",
    "LAURUSLABS": "LAURUSLABS",
    "SAILIFE":    "SAILIFE",
    "MINDACORP":  "MINDACORP",
}

# ── yfinance ticker overrides (NSE symbol → actual yfinance ticker without .NS) ──
# Use when the NSE symbol differs from what Yahoo Finance indexes
YF_TICKER_OVERRIDE = {
    "RUBCORP": "RUBICON",   # Yahoo Finance uses RUBICON.NS, not RUBCORP.NS
}

# ── Fund rules ──────────────────────────────────────────────────────────────
SC_RULES = {
    "Stage S2":         lambda d: d.get("stage") == "S2",
    "RS ≥ 65":          lambda d: (d.get("rs") or 0) >= 65,
    "TechScore ≥ 65":   lambda d: (d.get("tech") or 0) >= 65,
    "FundScore ≥ 65":   lambda d: (d.get("enh_fund") or 0) >= 65,
    "Supertrend BULL":  lambda d: d.get("supertrend") == "BULLISH",
    "Signal BUY/HOLD":  lambda d: d.get("signal") in ("BUY", "HOLD"),
}
MC_RULES = {
    "Stage S1/S2":      lambda d: d.get("stage") in ("S1", "S2"),
    "RS ≥ 65":          lambda d: (d.get("rs") or 0) >= 65,
    "TechScore ≥ 65":   lambda d: (d.get("tech") or 0) >= 65,
    "FundScore ≥ 65":   lambda d: (d.get("enh_fund") or 0) >= 65,
    "Supertrend BULL":  lambda d: d.get("supertrend") == "BULLISH",
    "Signal BUY/HOLD":  lambda d: d.get("signal") in ("BUY", "HOLD"),
}


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Load holdings
# ─────────────────────────────────────────────────────────────────────────────
def load_holdings():
    with open(HOLDINGS_FILE) as f:
        h = json.load(f)
    meta = h.get("_meta", {})
    sc = h.get("smallcap", {})
    mc = h.get("midcap", {})
    return meta, sc, mc


def load_exits() -> list[dict]:
    """Load realized exits from data/fund_exits.json. Returns [] if file missing."""
    if not EXITS_FILE.exists():
        return []
    try:
        data = json.loads(EXITS_FILE.read_text())
        exits = data.get("exits", [])
        # Compute realized_pnl from prices if not stored
        for e in exits:
            if "realized_pnl" not in e:
                e["realized_pnl"] = round(
                    (float(e["exit_price"]) - float(e["entry_price"])) * int(e["qty"]), 2
                )
            if "realized_pct" not in e:
                ep = float(e["entry_price"])
                e["realized_pct"] = round(
                    (float(e["exit_price"]) - ep) / ep * 100, 2
                ) if ep else 0
        return exits
    except Exception as exc:
        print(f"  [exits] load failed: {exc}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Fetch live prices via yfinance
# ─────────────────────────────────────────────────────────────────────────────
def fetch_live_prices(syms: list[str], skip: bool = False) -> dict[str, float]:
    """Returns {NSE_SYM: price}. Falls back to cache then DB price."""
    cache = {}
    if PRICES_CACHE.exists():
        try:
            c = json.loads(PRICES_CACHE.read_text())
            if c.get("date") == str(TODAY):
                cache = c.get("prices", {})
        except Exception:
            pass

    if skip and cache:
        print(f"  [prices] using cache ({str(TODAY)}, {len(cache)} symbols)")
        return cache

    prices = {}
    # Build yf_sym → nse_sym reverse map using overrides
    yf_to_nse = {}
    for s in syms:
        yf_sym = YF_TICKER_OVERRIDE.get(s, s)
        yf_to_nse[yf_sym] = s
    tickers = [f"{yf_sym}.NS" for yf_sym in yf_to_nse]
    print(f"  [prices] fetching {len(tickers)} tickers from yfinance...")
    try:
        data = yf.download(tickers, period="2d", auto_adjust=True, progress=False, threads=True)
        close = data["Close"] if "Close" in data else data
        if hasattr(close, "columns"):
            for t in close.columns:
                yf_sym = t.replace(".NS", "")
                sym = yf_to_nse.get(yf_sym, yf_sym)
                vals = close[t].dropna()
                if len(vals):
                    prices[sym] = float(round(vals.iloc[-1], 2))
        elif len(syms) == 1:
            vals = close.dropna()
            if len(vals):
                prices[syms[0]] = float(round(vals.iloc[-1], 2))
    except Exception as e:
        print(f"  [prices] yfinance error: {e}")

    # Fill missing from cache
    for sym in syms:
        if sym not in prices and sym in cache:
            prices[sym] = cache[sym]
            print(f"  [prices] {sym} fallback to cache")

    # Save cache
    PRICES_CACHE.write_text(json.dumps({"date": str(TODAY), "prices": prices}, indent=2))
    print(f"  [prices] fetched {len(prices)}/{len(syms)} prices, saved to {PRICES_CACHE.name}")
    return prices


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Fetch DB data (snapshots, fundamentals, quarterly)
# ─────────────────────────────────────────────────────────────────────────────
def fetch_db_data(db_syms: list[str]) -> tuple[dict, dict, dict]:
    conn = pg()
    cur  = conn.cursor()

    # Snapshots — skip UNKNOWN-stage dates (corrupted pipeline runs)
    cur.execute("""
        SELECT DISTINCT ON (symbol)
            symbol, company_name, sector, market_cap_cat, price, snapshot_date,
            technical_score, stage, relative_strength, rsi,
            trend_signal, trading_signal, supertrend_state,
            enhanced_fund_score, earnings_quality, sales_growth,
            financial_strength, institutional_backing, investment_score,
            stance, narrative, change_1d_pct
        FROM scores.stage_snapshots
        WHERE symbol = ANY(%s)
          AND stage IS DISTINCT FROM 'UNKNOWN'
        ORDER BY symbol, snapshot_date DESC
    """, (db_syms,))
    cols  = [d[0] for d in cur.description]
    snaps = {}
    for row in cur.fetchall():
        d = dict(zip(cols, row))
        snaps[d["symbol"]] = d

    # EOD bhavcopy is the canonical source for the previous completed-session
    # close.  Do not reverse-engineer it from stage_snapshots.change_1d_pct:
    # that percentage belongs to the snapshot date and can be stale relative
    # to today's live quote.  If the latest EOD row is from a prior session,
    # its close is today's previous close; if it is today's EOD row, its own
    # prev_close is the correct reference.
    cur.execute("""
        SELECT DISTINCT ON (symbol)
            symbol, trade_date, close, prev_close
        FROM market.equity_eod
        WHERE symbol = ANY(%s) AND series = 'EQ'
        ORDER BY symbol, trade_date DESC
    """, (db_syms,))
    for symbol, trade_date, close, prev_close in cur.fetchall():
        if symbol not in snaps:
            continue
        reference_close = prev_close if trade_date >= TODAY else close
        snaps[symbol]["eod_prev_close"] = float(reference_close) if reference_close is not None else None
        snaps[symbol]["eod_prev_close_date"] = str(trade_date)

    # Fundamentals
    cur.execute("""
        SELECT symbol, ratios_summary, pnl_summary,
               piotroski_score, revenue_growth_3y, pat_growth_3y,
               roe, roce, debt_to_equity, promoter_holding
        FROM scores.fundamentals WHERE symbol = ANY(%s)
    """, (db_syms,))
    funds = {}
    for row in cur.fetchall():
        d = dict(zip([c[0] for c in cur.description], row))
        funds[d["symbol"]] = d

    # Quarterly results
    cur.execute("""
        SELECT symbol, period_label, period_end, revenue, pat, opm_pct
        FROM scores.quarterly_results
        WHERE symbol = ANY(%s) AND period_type = 'quarter'
        ORDER BY symbol, period_end DESC
    """, (db_syms,))
    qtrs = {}
    for row in cur.fetchall():
        sym, lbl, end, rev, pat, opm = row
        qtrs.setdefault(sym, []).append({
            "label":   str(lbl),
            "revenue": float(rev or 0),
            "pat":     float(pat or 0),
            "opm":     float(opm or 0),
        })

    # Override enhanced_fund_score from fundamental_scores when snapshot has
    # stale sentinel value (≤20 = March-2026 CSV initialisation placeholder).
    # The 4 sub-scores are populated correctly by the screener.in backfill, but
    # EFS can get overwritten by fundamental_scores_database.csv defaults.
    efs_syms = [s for s, d in snaps.items() if (d.get("enhanced_fund_score") or 0) <= 20]
    if efs_syms:
        cur.execute("""
            SELECT DISTINCT ON (symbol) symbol, enhanced_fund_score
            FROM scores.fundamental_scores
            WHERE symbol = ANY(%s) AND enhanced_fund_score > 20
            ORDER BY symbol, score_date DESC
        """, (efs_syms,))
        for sym, efs in cur.fetchall():
            snaps[sym]["enhanced_fund_score"] = float(efs)

    conn.close()
    print(f"  [db] snaps={len(snaps)}, funds={len(funds)}, qtrs={len(qtrs)}")
    return snaps, funds, qtrs


# ─────────────────────────────────────────────────────────────────────────────
# Step 3b: Fetch next candidates (stocks passing fund rules, not in portfolio)
# ─────────────────────────────────────────────────────────────────────────────
def _entry_label(row: dict) -> str:
    """Classify entry timing from RSI, VCP breakout %, and contraction %.

    IDEAL        — RSI 45–68, at/near pivot (breakout 0–5%), contraction ≥ 15%.
                   Best risk/reward: still in the base, not yet extended.
    AT_PIVOT     — Breakout 0–8%, RSI ≤ 75. Acceptable; momentum confirmed.
    BASING       — Price below the 20-day pivot (breakout < 0). Not yet triggered.
                   Watch: wait for price to re-enter the breakout zone.
    EXTENDED     — RSI > 75 OR breakout > 10%. Chased; risk/reward is poor.
                   Do NOT add new exposure. Wait for a pullback to the 10-week MA.
    """
    rsi        = float(row.get("rsi")                or 0)
    breakout   = float(row.get("vcp_breakout_pct")   or 0)
    contraction= float(row.get("vcp_contraction_pct")or 0)

    if rsi > 75 or breakout > 10:
        return "EXTENDED"
    if breakout < -2:
        return "BASING"
    if 45 <= rsi <= 68 and 0 <= breakout <= 5 and contraction >= 15:
        return "IDEAL"
    return "AT_PIVOT"


_CAND_SQL = """
    SELECT DISTINCT ON (ss.symbol)
        ss.symbol, ss.company_name, ss.sector, ss.technical_score, ss.stage,
        ss.relative_strength, ss.enhanced_fund_score, ss.supertrend_state,
        ss.trading_signal, ss.investment_score, ss.financial_strength,
        ss.institutional_backing, ss.snapshot_date, ss.rsi,
        COALESCE(ss.live_price, ss.price) AS cmp,
        vcp.vcp_breakout_pct, vcp.vcp_contraction_pct, vcp.vcp_score
    FROM scores.stage_snapshots ss
    LEFT JOIN LATERAL (
        SELECT vcp_breakout_pct, vcp_contraction_pct, vcp_score
        FROM scores.stage2_vcp_picks
        WHERE symbol = ss.symbol
        ORDER BY snapshot_date DESC
        LIMIT 1
    ) vcp ON true
    WHERE ss.market_cap_cat = %s
      AND (ss.stage IN ('S2', 'STAGE_2') {extra_stage})
      AND ss.relative_strength >= 65
      AND ss.technical_score >= 65
      AND ss.enhanced_fund_score >= 65
      AND ss.supertrend_state = 'BULLISH'
      AND ss.trading_signal IN ('BUY', 'HOLD')
      AND ss.stage IS DISTINCT FROM 'UNKNOWN'
      AND ss.symbol != ALL(%s)
    ORDER BY ss.symbol, ss.snapshot_date DESC
"""


def fetch_candidates(existing_syms: list[str], n: int = 20) -> tuple[list, list]:
    """Returns (sc_candidates, mc_candidates) with entry-timing labels (IDEAL/AT_PIVOT/BASING/EXTENDED)."""
    conn = pg()
    cur  = conn.cursor()
    exclude = existing_syms

    sc_sql = _CAND_SQL.format(extra_stage="")
    cur.execute(sc_sql, ("SMALL_CAP", exclude))
    cols   = [d[0] for d in cur.description]
    sc_rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    for r in sc_rows:
        r["entry_label"] = _entry_label(r)
    # Sort: IDEAL first → AT_PIVOT → BASING → EXTENDED; break ties by investment_score
    _order = {"IDEAL": 0, "AT_PIVOT": 1, "BASING": 2, "EXTENDED": 3}
    sc_rows.sort(key=lambda r: (_order.get(r["entry_label"], 9),
                                -float(r.get("investment_score") or 0)))

    mc_sql = _CAND_SQL.format(extra_stage="OR ss.stage IN ('S1', 'STAGE_1')")
    cur.execute(mc_sql, ("MID_CAP", exclude))
    mc_rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    for r in mc_rows:
        r["entry_label"] = _entry_label(r)
    mc_rows.sort(key=lambda r: (_order.get(r["entry_label"], 9),
                                -float(r.get("investment_score") or 0)))

    conn.close()
    n_ideal_sc = sum(1 for r in sc_rows if r["entry_label"] == "IDEAL")
    n_ideal_mc = sum(1 for r in mc_rows if r["entry_label"] == "IDEAL")
    print(f"  [candidates] SC={len(sc_rows)} ({n_ideal_sc} IDEAL), MC={len(mc_rows)} ({n_ideal_mc} IDEAL)")
    return sc_rows[:n], mc_rows[:n]


# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Build JS stock data with fund rules evaluation
# ─────────────────────────────────────────────────────────────────────────────
RATIONALE: dict[str, str] = {
    "BLSE":       "BLS E-Services dominates government digital service delivery. Stage 1 base near highs, extreme RS=97.8 — top RS in SC universe. Govt digitisation + Aadhaar-linked services momentum.",
    "EIMCOELECO": "EIMCO Elecon: niche underground mining equipment near-monopoly. Stage 2 uptrend, RS=87, TechScore=92.7. Capital goods capex cycle play. ROCE 17%+. Strong order book visibility.",
    "RATNAVEER":  "Ratnaveer Precision: stainless steel tubes/pipes for industrial use. Stage 2, RS=88.3, TechScore=93.4. Infra + export capex beneficiary. Clean balance sheet.",
    "SKYGOLD":    "Sky Gold: organized jewelry manufacturer expanding brand. Stage 2, RS=98.5 (extreme leader), TechScore=95.8. ROCE 27%, ROE 29%. Gold jewelry structural demand + premiumization.",
    "SANSERA":    "Sansera Engineering: precision auto + aerospace components, diversifying to EVs. Stage 2, RS=98.0, TechScore=92.5. Sales +8.8%, NetProfit +21.2%. Auto + EV pivot.",
    "RUBCORP":    "Rubfila International (RUBICON): specialty rubber products. Stage 2, RS=98.2 — highest RS in portfolio. TechScore=98.8. Small-cap momentum leader.",
    "RRKABEL":    "RR Kabel: cables/wires + FMEG electrical fittings. Stage 2, RS=93.7, TechScore=90.9. Power infra boom + housing electrification drive. ✅ Added Aug-17.",
    "CUPID":      "Cupid Limited: monopoly condom + medical device manufacturer. Stage 2, RS=100 (top-ranked in SC universe), TechScore=83, FundScore=88. Existing broker holding +46% from ₹182.70. Strong export + domestic demand. ✅ Moved from candidates to SC fund Aug-18.",
    "MANORAMA":   "Manorama Industries: specialty fats (sal/shea/kokum) for food & cosmetics. Stage 2, RS=90.5, TechScore=97.0. Niche agri-specialty, strong exports.",
    "SYRMA":      "Syrma SGS: EMS for defense, auto, industrial electronics. Stage 2, RS=94.1, TechScore=92.3. PLI + import substitution beneficiary.",
    "ENDURANCE":  "Endurance Technologies: leading auto components (Bajaj ecosystem) + expanding into EVs. Stage 1 consolidation base. RS=74.1, TechScore=77.4. Existing holding. Auto cycle + EV expansion.",
    "COFORGE":    "Coforge: IT services with deep BFSI + travel vertical specialization. Stage 1. RS=93.4, TechScore=72. Existing ICICI holding. IT sector rotation beneficiary.",
    "FEDERALBNK": "Federal Bank: fast-growing BFSI franchise, Bajaj Finance distribution tie-up. Stage 2, RS=85.7, TechScore=89.5. Existing hold +72% from ₹204. Strong CASA + credit growth.",
    "ATHERENERG": "Ather Energy: India #2 premium EV 2-wheeler (Hero MotoCorp backed). Stage 2, RS=97.3. Existing hold +73% from ₹868. EV market leader. Sales +62.8% YoY.",
    "NYKAA":      "Nykaa: dominant beauty/fashion ecommerce platform. Stage 2, RS=82.6, TechScore=93.2. Existing hold +36.5% from ₹240. Premium consumption + D2C brand building.",
    "OFSS":       "Oracle Financial Services: banking software, US/EU bank clients. Stage 2, RS=89.2, TechScore=94.9. 2-slot position. High-quality recurring revenues.",
    "SONACOMS":   "Sona BLW Precision: EV drivetrain components. Stage 2, RS=92.4, TechScore=93.8. EV structural play with global OEM clients. R&D investment in EV tech.",
    "SENORES":    "Senores Pharma: CRAMS + regulated market pharma exports (US/EU). Stage 2, RS=93.1, TechScore=97.5. Pharma export cycle + API quality play. ✅ Added Aug-17.",
    "GNA":        "GNA Axles: CV rear axle shafts (dominant India share) + export expansion. Stage 2, RS=94.4, TechScore=96.1. CV upcycle + export order book growth.",
    "WSTCSTPAPR": "West Coast Paper Mills: paper + boards + captive power. Stage 2, RS=88.9, TechScore=96.7. Low valuation vs peers. Packaging demand + import substitution.",
    "LLOYDSME":   "Lloyds Metals & Energy: sponge iron + greenfield steel. Stage 2, RS=69.2, TechScore=83.5. Capacity expansion play. Steel cycle beneficiary.",
    "CARYSIL":    "Carysil: premium quartz sinks (global leader) + sanitaryware. Stage 2, RS=87.8, TechScore=93.9. Housing + luxury fittings + export demand.",
    "SGMART":     "Shree Ganesh Metal: steel/metal distribution + processing. Stage 2, RS=83.9, TechScore=94.9. Metal cycle beneficiary.",
    "HSCL":       "Himadri Speciality Chemical: carbon black + coal tar derivatives for EV batteries (anode material). Stage 2, RS=89.1, TechScore=91.0. EV battery value chain leader.",
}


def _parse_ratios(text: str) -> dict:
    """Parse ratios_summary text → {pe, roce, roe, eps, npm, bv, mktcap, divy}."""
    import re
    r = {}
    if not text:
        return r
    patterns = [
        ("pe",     r"P/E:\s*([-\d.,]+)"),
        ("roce",   r"ROCE:\s*([-\d.,]+)%?"),
        ("roe",    r"ROE:\s*([-\d.,]+)"),
        ("eps",    r"EPS:\s*([-\d.,]+)"),
        ("npm",    r"NPM:\s*([-\d.,]+)%?"),
        ("bv",     r"Book Value:\s*([\d.,]+)"),
        ("mktcap", r"Mkt Cap:\s*([\d.,]+)"),
        ("divy",   r"Div Yield:\s*([\d.,]+)"),
    ]
    for key, pat in patterns:
        m = re.search(pat, text)
        if m:
            try:
                r[key] = round(float(m.group(1).replace(",", "")), 2)
            except ValueError:
                pass
    return r


def _parse_pnl(text: str) -> dict:
    """Parse pnl_summary text → {sales_cr, sales_yoy, pat_cr, pat_yoy, eps}."""
    import re
    r = {}
    if not text:
        return r
    # Sales: 1,178 Cr (YoY +5.4%)
    m = re.search(r"Sales:\s*([-\d,.]+)\s*Cr\s*\(YoY\s*([+-]?[\d.]+)%\)", text)
    if m:
        try:
            r["sales_cr"]  = float(m.group(1).replace(",", ""))
            r["sales_yoy"] = float(m.group(2))
        except ValueError:
            pass
    # NetProfit: 70 Cr (YoY +1.4%)
    m = re.search(r"NetProfit:\s*([-\d,.]+)\s*Cr\s*\(YoY\s*([+-]?[\d.]+)%\)", text)
    if m:
        try:
            r["pat_cr"]  = float(m.group(1).replace(",", ""))
            r["pat_yoy"] = float(m.group(2))
        except ValueError:
            pass
    # EPS: 6.39
    m = re.search(r"EPS:\s*([-\d.,]+)", text)
    if m:
        try:
            r["eps"] = float(m.group(1))
        except ValueError:
            pass
    return r


def build_js_data(nse_to_db: dict, snaps: dict, funds: dict, qtrs: dict) -> dict:
    js = {}
    for nse_sym, db_sym in nse_to_db.items():
        s  = snaps.get(db_sym, {})
        f  = funds.get(db_sym, {})
        q  = qtrs.get(db_sym, [])[:5]
        rt = _parse_ratios(f.get("ratios_summary") or "")
        pn = _parse_pnl(f.get("pnl_summary") or "")
        js[nse_sym] = {
            # Identity
            "company":   s.get("company_name", nse_sym),
            "sector":    s.get("sector", "—"),
            "cap":       s.get("market_cap_cat", "—"),
            "date":      str(s.get("snapshot_date", "")),
            # Technical
            "tech":      round(float(s.get("technical_score")     or 0), 1),
            "stage":     (s.get("stage") or "—").replace("STAGE_", "S"),
            "rs":        round(float(s.get("relative_strength")   or 0), 1),
            "rsi":       round(float(s.get("rsi")                 or 0), 1),
            "trend":     s.get("trend_signal",  "—"),
            "signal":    s.get("trading_signal", "—"),
            "supertrend":s.get("supertrend_state", "—"),
            # Fund scores (from stage_snapshots — correctly populated)
            "enh_fund":  round(float(s.get("enhanced_fund_score")   or 0), 1),
            "eq":        round(float(s.get("earnings_quality")      or 0), 1),
            "sales_g":   round(float(s.get("sales_growth")          or 0), 1),
            "fin_str":   round(float(s.get("financial_strength")    or 0), 1),
            "inst_bk":   round(float(s.get("institutional_backing") or 0), 1),
            "inv_score": round(float(s.get("investment_score")      or 0), 1),
            "stance":    s.get("stance", "—"),
            "narrative": (s.get("narrative") or "")[:400],
            # Fundamentals — parsed from text summaries (structured cols are null)
            "pe":        rt.get("pe",       0),
            "roce":      rt.get("roce",     0),
            "roe":       rt.get("roe",      0),
            "eps":       rt.get("eps",      0) or pn.get("eps", 0),
            "npm":       rt.get("npm",      0),
            "bv":        rt.get("bv",       0),
            "mktcap":    rt.get("mktcap",   0),
            "divy":      rt.get("divy",     0),
            "sales_cr":  pn.get("sales_cr",  0),
            "sales_yoy": pn.get("sales_yoy", 0),
            "pat_cr":    pn.get("pat_cr",    0),
            "pat_yoy":   pn.get("pat_yoy",   0),
            # Quarterly
            "quarterly": q,
            # Rationale
            "rationale": RATIONALE.get(nse_sym, ""),
        }
    return js


# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Compute P&L rows
# ─────────────────────────────────────────────────────────────────────────────
def compute_rows(holds: dict, prices: dict, sl_pct: float, entry_date_today: str) -> list:
    """holds = {SYM: {entry, entry_date, qty, ...}}  →  list of row dicts."""
    rows = []
    for sym, h in holds.items():
        entry    = float(h["entry"])
        qty      = int(h["qty"])
        edt      = h["entry_date"]
        # Same-day fill → P&L = 0 (use entry as current)
        if edt == entry_date_today:
            price = entry
        else:
            price = prices.get(sym) or entry
        invested  = round(entry * qty, 2)
        current   = round(price * qty, 2)
        pnl       = round(current - invested, 2)
        pnl_pct   = round((price - entry) / entry * 100, 2) if entry else 0
        sl_price  = round(entry * (1 - sl_pct), 2)
        days      = (TODAY - date.fromisoformat(edt)).days
        new_tag   = edt == entry_date_today
        rows.append({
            "sym": sym, "entry": entry, "price": price, "qty": qty,
            "invested": invested, "current": current,
            "pnl": pnl, "pnl_pct": pnl_pct, "sl": sl_price,
            "buy_date": edt, "sell_date": "—", "days": days, "new": new_tag,
        })
    return rows


def fund_summary(rows: list) -> dict:
    inv  = sum(r["invested"] for r in rows)
    cur  = sum(r["current"]  for r in rows)
    pnl  = sum(r["pnl"]      for r in rows)
    pct  = (pnl / inv * 100) if inv else 0
    W    = sum(1 for r in rows if r["pnl"] >= 0)
    L    = sum(1 for r in rows if r["pnl"] < 0)
    return {"inv": inv, "cur": cur, "pnl": pnl, "pct": pct, "W": W, "L": L}


# ─────────────────────────────────────────────────────────────────────────────
# History: PostgreSQL persistence + fetch for trend display
# ─────────────────────────────────────────────────────────────────────────────

def _sparkline_svg(values: list[float], width: int = 80, height: int = 24) -> str:
    """Minimal inline SVG area-line sparkline. Returns '' if < 2 data points."""
    if not values or len(values) < 2:
        return ""
    mn, mx = min(values), max(values)
    rng = (mx - mn) or 0.001
    n = len(values)
    pts = []
    for i, v in enumerate(values):
        x = round(i / (n - 1) * width, 1)
        y = round(height - (v - mn) / rng * (height - 3) - 1.5, 1)
        pts.append(f"{x},{y}")
    col  = "#3fb950" if values[-1] >= 0 else "#f85149"
    poly = " ".join(pts)
    area = f"0,{height} {poly} {width},{height}"
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'style="display:block;overflow:visible;opacity:.9">'
        f'<polygon points="{area}" fill="{col}" fill-opacity="0.12"/>'
        f'<polyline points="{poly}" fill="none" stroke="{col}" stroke-width="1.5" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )


def _ensure_history_tables(cur) -> None:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS portfolio.fund_daily_pnl (
            snapshot_date   date         NOT NULL,
            fund            text         NOT NULL,
            invested        numeric(16,2),
            market_value    numeric(16,2),
            unrealised_pnl  numeric(16,2),
            pnl_pct         numeric(8,4),
            day_pnl         numeric(16,2),
            day_pnl_pct     numeric(8,4),
            wow_pnl         numeric(16,2),
            wow_pnl_pct     numeric(8,4),
            positions       int,
            winners         int,
            losers          int,
            PRIMARY KEY (snapshot_date, fund)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS portfolio.fund_position_history (
            snapshot_date       date         NOT NULL,
            fund                text         NOT NULL,
            symbol              text         NOT NULL,
            entry_price         numeric(12,4),
            current_price       numeric(12,4),
            qty                 int,
            invested            numeric(16,2),
            market_value        numeric(16,2),
            unrealised_pnl      numeric(16,2),
            pnl_pct             numeric(8,4),
            sl_price            numeric(12,4),
            days_held           int,
            stage               text,
            technical_score     numeric(8,2),
            relative_strength   numeric(8,2),
            enhanced_fund_score numeric(8,2),
            supertrend_state    text,
            PRIMARY KEY (snapshot_date, fund, symbol)
        )
    """)


def _prev_fund_row(cur, fund: str, days_back: int) -> tuple:
    """Return (pnl_pct, unrealised_pnl) from the most recent row at least `days_back` days ago."""
    cur.execute("""
        SELECT pnl_pct, unrealised_pnl
        FROM portfolio.fund_daily_pnl
        WHERE fund = %s AND snapshot_date <= CURRENT_DATE - %s
        ORDER BY snapshot_date DESC
        LIMIT 1
    """, (fund, days_back))
    row = cur.fetchone()
    return (float(row[0]), float(row[1])) if row else (None, None)


def persist_to_pg(
    sc_rows: list, mc_rows: list,
    sc_sum: dict, mc_sum: dict,
    snaps: dict, active_nse_to_db: dict,
) -> None:
    """Persist today's fund P&L snapshot to portfolio.fund_daily_pnl and fund_position_history."""
    conn = pg()
    cur  = conn.cursor()
    today_str = str(TODAY)

    try:
        _ensure_history_tables(cur)
        conn.commit()

        comb_inv = sc_sum["inv"] + mc_sum["inv"]
        comb_cur = sc_sum["cur"] + mc_sum["cur"]
        comb_pnl = sc_sum["pnl"] + mc_sum["pnl"]
        comb_pct = (comb_pnl / comb_inv * 100) if comb_inv else 0

        fund_rows = [
            ("SC",       sc_sum["inv"],  sc_sum["cur"],  sc_sum["pnl"],  sc_sum["pct"],
             len(sc_rows),              sc_sum["W"],  sc_sum["L"]),
            ("MC",       mc_sum["inv"],  mc_sum["cur"],  mc_sum["pnl"],  mc_sum["pct"],
             len(mc_rows),              mc_sum["W"],  mc_sum["L"]),
            ("COMBINED", comb_inv,       comb_cur,       comb_pnl,       comb_pct,
             len(sc_rows)+len(mc_rows), sc_sum["W"]+mc_sum["W"], sc_sum["L"]+mc_sum["L"]),
        ]

        for fund, inv, cur_val, pnl, pct, n_pos, wins, losses in fund_rows:
            prev_pct, prev_pnl = _prev_fund_row(cur, fund, days_back=1)
            wow_pct,  wow_pnl  = _prev_fund_row(cur, fund, days_back=7)

            day_pnl     = pnl - prev_pnl if prev_pnl is not None else 0.0
            day_pnl_pct = pct - prev_pct if prev_pct is not None else 0.0
            wow_pnl_v   = pnl - wow_pnl  if wow_pnl  is not None else 0.0
            wow_pnl_pct = pct - wow_pct  if wow_pct  is not None else 0.0

            cur.execute("""
                INSERT INTO portfolio.fund_daily_pnl
                    (snapshot_date, fund, invested, market_value, unrealised_pnl, pnl_pct,
                     day_pnl, day_pnl_pct, wow_pnl, wow_pnl_pct, positions, winners, losers)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (snapshot_date, fund) DO UPDATE SET
                    market_value    = EXCLUDED.market_value,
                    unrealised_pnl  = EXCLUDED.unrealised_pnl,
                    pnl_pct         = EXCLUDED.pnl_pct,
                    day_pnl         = EXCLUDED.day_pnl,
                    day_pnl_pct     = EXCLUDED.day_pnl_pct,
                    wow_pnl         = EXCLUDED.wow_pnl,
                    wow_pnl_pct     = EXCLUDED.wow_pnl_pct,
                    positions       = EXCLUDED.positions,
                    winners         = EXCLUDED.winners,
                    losers          = EXCLUDED.losers
            """, (today_str, fund, round(inv, 2), round(cur_val, 2), round(pnl, 2), round(pct, 4),
                  round(day_pnl, 2), round(day_pnl_pct, 4),
                  round(wow_pnl_v, 2), round(wow_pnl_pct, 4),
                  n_pos, wins, losses))

        # Per-position history
        all_pos = [("SC", r) for r in sc_rows] + [("MC", r) for r in mc_rows]
        for fund, r in all_pos:
            db_sym  = active_nse_to_db.get(r["sym"], r["sym"])
            s_snap  = snaps.get(db_sym, {})
            cur.execute("""
                INSERT INTO portfolio.fund_position_history
                    (snapshot_date, fund, symbol, entry_price, current_price, qty,
                     invested, market_value, unrealised_pnl, pnl_pct, sl_price, days_held,
                     stage, technical_score, relative_strength, enhanced_fund_score, supertrend_state)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (snapshot_date, fund, symbol) DO UPDATE SET
                    current_price       = EXCLUDED.current_price,
                    market_value        = EXCLUDED.market_value,
                    unrealised_pnl      = EXCLUDED.unrealised_pnl,
                    pnl_pct             = EXCLUDED.pnl_pct,
                    days_held           = EXCLUDED.days_held,
                    stage               = EXCLUDED.stage,
                    technical_score     = EXCLUDED.technical_score,
                    relative_strength   = EXCLUDED.relative_strength,
                    enhanced_fund_score = EXCLUDED.enhanced_fund_score,
                    supertrend_state    = EXCLUDED.supertrend_state
            """, (
                today_str, fund, r["sym"],
                round(r["entry"], 4), round(r["price"], 4), int(r["qty"]),
                round(r["invested"], 2), round(r["current"], 2),
                round(r["pnl"], 2), round(r["pnl_pct"], 4),
                round(r["sl"], 4), int(r["days"]),
                (s_snap.get("stage") or "").replace("STAGE_", "S"),
                float(s_snap.get("technical_score") or 0),
                float(s_snap.get("relative_strength") or 0),
                float(s_snap.get("enhanced_fund_score") or 0),
                s_snap.get("supertrend_state") or "",
            ))

        conn.commit()
        print(f"  [pg] persisted: 3 fund rows + {len(all_pos)} position rows → "
              f"portfolio.fund_daily_pnl / fund_position_history")
    except Exception as exc:
        conn.rollback()
        print(f"  [pg] persist failed: {exc}")
    finally:
        conn.close()


def fetch_history_for_dashboard(all_nse_syms: list[str], lookback_days: int = 30) -> dict:
    """Fetch historical P&L series for sparklines and trend display in the dashboard."""
    conn = pg()
    cur  = conn.cursor()
    history: dict = {"funds": {}, "positions": {}}

    try:
        cur.execute("""
            SELECT fund, snapshot_date, pnl_pct, unrealised_pnl, day_pnl_pct, wow_pnl_pct,
                   day_pnl, wow_pnl
            FROM portfolio.fund_daily_pnl
            WHERE snapshot_date >= CURRENT_DATE - %s
            ORDER BY fund, snapshot_date
        """, (lookback_days,))
        for fund, dt, pct, pnl, day_pct, wow_pct, day_pnl, wow_pnl in cur.fetchall():
            history["funds"].setdefault(fund, []).append({
                "date":          str(dt),
                "pnl_pct":       float(pct      or 0),
                "unrealised_pnl":float(pnl      or 0),
                "day_pct":       float(day_pct  or 0),
                "wow_pct":       float(wow_pct  or 0),
                "day_pnl":       float(day_pnl  or 0),
                "wow_pnl":       float(wow_pnl  or 0),
            })

        cur.execute("""
            SELECT symbol, snapshot_date, pnl_pct, current_price
            FROM portfolio.fund_position_history
            WHERE symbol = ANY(%s) AND snapshot_date >= CURRENT_DATE - %s
            ORDER BY symbol, snapshot_date
        """, (all_nse_syms, lookback_days))
        for sym, dt, pct, price in cur.fetchall():
            history["positions"].setdefault(sym, []).append({
                "date":    str(dt),
                "pnl_pct": float(pct   or 0),
                "price":   float(price or 0),
            })
    except Exception as exc:
        print(f"  [history] fetch failed: {exc}")
    finally:
        conn.close()

    nf = sum(len(v) for v in history["funds"].values())
    np = sum(len(v) for v in history["positions"].values())
    print(f"  [history] loaded {nf} fund rows + {np} position rows (last {lookback_days}d)")
    return history


# ─────────────────────────────────────────────────────────────────────────────
# Step 6: Render HTML
# ─────────────────────────────────────────────────────────────────────────────
CSS = """
:root{--bg:#0d1117;--card:#161b22;--border:#30363d;--text:#e6edf3;--muted:#8b949e;
      --accent:#58a6ff;--pos:#3fb950;--neg:#f85149;--warn:#d29922;--panel:#1c2128}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;font-size:13px}
h1{font-size:20px;font-weight:700}h2{font-size:16px;font-weight:600;margin-bottom:12px}
h3{font-size:14px;font-weight:600;margin-bottom:8px}
.tabs{display:flex;gap:4px;padding:16px 20px 0;border-bottom:1px solid var(--border)}
.tab{padding:8px 18px;border-radius:6px 6px 0 0;cursor:pointer;border:1px solid transparent;
     border-bottom:none;color:var(--muted);transition:all .2s;font-size:13px;font-weight:500}
.tab:hover{color:var(--text);background:var(--card)}
.tab.active{color:var(--accent);background:var(--card);border-color:var(--border)}
.tab-content{display:none;padding:20px}.tab-content.active{display:block}
.summary-bar{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px}
.stat-box{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px 18px;min-width:140px}
.stat-box .label{color:var(--muted);font-size:11px;text-transform:uppercase;margin-bottom:4px}
.stat-box .value{font-size:18px;font-weight:700}
.stat-box .sub{color:var(--muted);font-size:11px;margin-top:2px}
.pos{color:var(--pos)}.neg{color:var(--neg)}.warn{color:var(--warn)}
.fund-card{background:var(--card);border:1px solid var(--border);border-radius:10px;margin-bottom:24px;overflow:hidden}
.fund-header{padding:14px 20px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}
.fund-meta{display:flex;gap:20px;flex-wrap:wrap}.fund-meta .m{font-size:12px}.fund-meta .m .k{color:var(--muted)}
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse}
th{background:#1c2128;color:var(--muted);font-size:11px;text-transform:uppercase;
   padding:8px 12px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--border)}
th:first-child{text-align:left}
td{padding:8px 12px;text-align:right;border-bottom:1px solid #21262d;white-space:nowrap}
td:first-child{text-align:left}
tr:hover td{background:rgba(88,166,255,.04)}
.clickable-sym{color:var(--accent);cursor:pointer;font-weight:600;text-decoration:underline dotted}
.clickable-sym:hover{color:#79c0ff}
.new-tag{background:#1a3a1a;color:var(--pos);font-size:10px;padding:1px 5px;border-radius:3px;font-weight:600}
.alert-tag{background:#3a2a0a;color:var(--warn);font-size:10px;padding:1px 5px;border-radius:3px;font-weight:600}
#stock-panel{position:fixed;top:0;right:-480px;width:460px;height:100vh;
  background:var(--panel);border-left:1px solid var(--border);overflow-y:auto;z-index:1000;transition:right .3s ease}
#stock-panel.open{right:0}
.panel-header{position:sticky;top:0;background:var(--panel);z-index:10;
  padding:16px 20px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:flex-start}
.panel-header h2{font-size:15px;line-height:1.3}
.panel-close{background:none;border:none;color:var(--muted);font-size:20px;cursor:pointer;padding:0 4px;line-height:1}
.panel-close:hover{color:var(--text)}
.panel-body{padding:16px 20px}
.panel-section{margin-bottom:18px}
.panel-section h3{font-size:12px;text-transform:uppercase;color:var(--muted);letter-spacing:.5px;
  margin-bottom:10px;border-bottom:1px solid var(--border);padding-bottom:6px}
.kv-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.kv-3{grid-template-columns:1fr 1fr 1fr}
.kv{display:flex;flex-direction:column;background:var(--card);border-radius:6px;padding:8px 10px}
.kv .k{font-size:10px;color:var(--muted);text-transform:uppercase}
.kv .v{font-size:14px;font-weight:600;margin-top:2px}
.pass{color:var(--pos)}.fail{color:var(--neg)}
.gate-row{display:flex;justify-content:space-between;align-items:center;
  padding:5px 0;border-bottom:1px solid #21262d;font-size:12px}
.gate-row:last-child{border-bottom:none}
.overall-badge{font-size:13px;font-weight:700;padding:4px 12px;border-radius:6px;margin-bottom:10px;display:inline-block}
.overall-badge.PASS{background:#1a3a1a;color:var(--pos);border:1px solid var(--pos)}
.overall-badge.REVIEW{background:#3a1a1a;color:var(--neg);border:1px solid var(--neg)}
.rationale-box{background:var(--card);border-radius:8px;padding:12px;font-size:12px;
  color:var(--text);line-height:1.6;border-left:3px solid var(--accent)}
.q-table{width:100%;border-collapse:collapse;font-size:11px}
.q-table th{background:#1c2128;color:var(--muted);padding:4px 8px;text-align:right}
.q-table th:first-child{text-align:left}
.q-table td{padding:4px 8px;text-align:right;border-bottom:1px solid #21262d}
.q-table td:first-child{text-align:left}
.fund-rules-content{max-width:960px}
.rules-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:700px){.rules-grid{grid-template-columns:1fr}}
.rule-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px}
.rule-card ul{list-style:none;padding:0}
.rule-card li{padding:4px 0;border-bottom:1px solid #21262d;font-size:12px;line-height:1.5}
.rule-card li:last-child{border-bottom:none}
#overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:999}
#overlay.open{display:block}
.alert-card{border-left:4px solid;border-radius:6px;padding:12px;margin:8px 0}
.alert-card.critical{border-color:#ef4444;background:rgba(239,68,68,.09)}
.alert-card.warning{border-color:#f59e0b;background:rgba(245,158,11,.09)}
.alert-card.positive{border-color:#10b981;background:rgba(16,185,129,.09)}
.alert-badge{background:#ef4444;color:#fff;border-radius:10px;padding:2px 7px;font-size:11px;margin-left:6px}
.news-summary{border-left:4px solid;border-radius:6px;padding:10px 14px;margin:0 0 10px}
.news-summary.bullish{border-color:#10b981;background:rgba(16,185,129,.08)}
.news-summary.bearish{border-color:#ef4444;background:rgba(239,68,68,.08)}
.news-summary.neutral{border-color:#6b7280;background:rgba(107,114,128,.07)}
.news-sentiment{font-size:10px;font-weight:700;letter-spacing:.04em;padding:2px 6px;border-radius:4px;margin-left:6px}
.news-sentiment.bullish{background:#10b981;color:#fff}
.news-sentiment.bearish{background:#ef4444;color:#fff}
.news-sentiment.neutral{background:#6b7280;color:#fff}
.delta-pill{display:inline-block;font-size:9.5px;font-weight:700;padding:1px 5px;border-radius:3px;margin-left:3px;vertical-align:middle}
.delta-pill.pos{background:rgba(63,185,80,.18);color:#3fb950}
.delta-pill.neg{background:rgba(248,81,73,.18);color:#f85149}
.spark-wrap{line-height:0;margin-top:5px}
.trend-chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px;font-size:10.5px}
.trend-chip{padding:2px 7px;border-radius:3px;font-weight:700}
/* Risk tab */
.risk-bar-wrap{display:flex;align-items:center;gap:6px}
.risk-bar{height:6px;border-radius:3px;min-width:2px;max-width:140px;flex-shrink:0}
.sl-safe{color:#3fb950}.sl-warn{color:#d29922}.sl-danger{color:#f85149}
.alloc-bar{height:8px;border-radius:4px;background:var(--accent);opacity:.6;min-width:2px;max-width:120px}
.aging-badge{font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;
  background:rgba(210,153,34,.15);color:#d29922;border:1px solid #d2992244;margin-left:4px}
"""

JS_TEMPLATE = """
function switchTab(id){
  document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  const TAB_IDS=['tab-actions','tab-pl','tab-orders','tab-risk','tab-candidates','tab-rules','tab-alerts','tab-exits'];
  const idx=TAB_IDS.indexOf(id);
  if(idx>=0) document.querySelectorAll('.tab')[idx].classList.add('active');
}
function closeCard(){
  document.getElementById('stock-panel').classList.remove('open');
  document.getElementById('overlay').classList.remove('open');
}
function openCard(sym){
  const d=STOCK_DATA[sym];
  if(!d)return;
  document.getElementById('panel-title').textContent=d.company||sym;
  document.getElementById('panel-subtitle').textContent=sym+' · '+(d.sector||'')+' · '+(d.cap||'')+' · '+(d.date||'');
  const SC_SYMS=Object.keys(FUND_MEMBERSHIP).filter(k=>FUND_MEMBERSHIP[k]==='SC');
  const isSC=SC_SYMS.includes(sym);
  const ft=isSC?'SC':'MC';
  const rules=isSC?[
    ['Stage S2', d.stage==='S2'],
    ['RS ≥ 65', d.rs>=65],
    ['TechScore ≥ 65', d.tech>=65],
    ['FundScore ≥ 65', d.enh_fund>=65],
    ['Supertrend BULL', d.supertrend==='BULLISH'],
    ['Signal BUY/HOLD', ['BUY','HOLD'].includes(d.signal)],
  ]:[
    ['Stage S1/S2', ['S1','S2'].includes(d.stage)],
    ['RS ≥ 65', d.rs>=65],
    ['TechScore ≥ 65', d.tech>=65],
    ['FundScore ≥ 65', d.enh_fund>=65],
    ['Supertrend BULL', d.supertrend==='BULLISH'],
    ['Signal BUY/HOLD', ['BUY','HOLD'].includes(d.signal)],
  ];
  const allPass=rules.every(r=>r[1]);
  const bc=allPass?'PASS':'REVIEW';
  let gate=`<span class="overall-badge ${bc}">${allPass?'✅ FUND RULES: PASS':'⚠️ FUND RULES: REVIEW'}</span><br><br>`;
  gate+=rules.map(([l,ok])=>`<div class="gate-row"><span>${l}</span><span>${ok?'✅':'❌'}</span></div>`).join('');
  const p=d.position;
  const money=v=>Number(v||0).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2});
  const signed=v=>(Number(v)>=0?'+':'')+money(v);
  const posHtml=p?`<div class="panel-section"><h3>💼 Fund Position (${p.fund})</h3>
    <div class="kv-grid kv-3">
      <div class="kv"><span class="k">Entry ₹</span><span class="v">₹${money(p.entry)}</span></div>
      <div class="kv"><span class="k">Portfolio Price ₹</span><span class="v">₹${money(p.price)}</span></div>
      <div class="kv"><span class="k">Quantity</span><span class="v">${p.qty}</span></div>
      <div class="kv"><span class="k">Invested</span><span class="v">₹${money(p.invested)}</span></div>
      <div class="kv"><span class="k">Current Value</span><span class="v">₹${money(p.current)}</span></div>
      <div class="kv"><span class="k">Unrealised P&amp;L</span><span class="v ${p.pnl>=0?'pass':'fail'}">${signed(p.pnl)} (${p.pnl_pct>=0?'+':''}${Number(p.pnl_pct).toFixed(1)}%)</span></div>
    </div>
    <div style="color:var(--muted);font-size:11px;margin-top:8px">Logged ${p.buy_date} · Stop ₹${money(p.sl)} · Portfolio price is the value used across dashboard cards.</div>
  </div>`:'';
  let qHtml='<em style="color:var(--muted);font-size:11px">No quarterly data</em>';
  if(d.quarterly&&d.quarterly.length>0){
    qHtml='<table class="q-table"><thead><tr><th>Period</th><th>Rev ₹Cr</th><th>PAT ₹Cr</th><th>OPM%</th></tr></thead><tbody>';
    d.quarterly.forEach(q=>{
      const pc=q.pat>=0?'pos':'neg';
      qHtml+=`<tr><td>${q.label}</td><td>${q.revenue.toFixed(1)}</td><td class="${pc}">${q.pat.toFixed(1)}</td><td>${q.opm.toFixed(1)}%</td></tr>`;
    });
    qHtml+='</tbody></table>';
  }
  function sc(v,hi,lo){return v>=hi?'pass':v>=lo?'warn':'fail'}
  const body=`
    ${posHtml}
    <div class="panel-section"><h3>💡 Rationale</h3>
      <div class="rationale-box">${d.rationale||d.narrative||'—'}</div>
    </div>
    <div class="panel-section"><h3>📋 Fund Rules Gate (${ft})</h3>${gate}</div>
    <div class="panel-section"><h3>📈 Technical</h3>
      <div class="kv-grid">
        <div class="kv"><span class="k">Tech Score</span><span class="v ${sc(d.tech,80,65)}">${d.tech}</span></div>
        <div class="kv"><span class="k">Stage</span><span class="v">${d.stage}</span></div>
        <div class="kv"><span class="k">Rel. Strength</span><span class="v ${sc(d.rs,85,65)}">${d.rs}</span></div>
        <div class="kv"><span class="k">RSI</span><span class="v">${d.rsi}</span></div>
        <div class="kv"><span class="k">Supertrend</span><span class="v ${d.supertrend==='BULLISH'?'pass':'fail'}">${d.supertrend}</span></div>
        <div class="kv"><span class="k">Signal</span><span class="v ${['BUY','HOLD'].includes(d.signal)?'pass':'fail'}">${d.signal}</span></div>
        <div class="kv"><span class="k">Trend</span><span class="v">${d.trend}</span></div>
        <div class="kv"><span class="k">Stance</span><span class="v">${d.stance}</span></div>
      </div>
    </div>
    <div class="panel-section"><h3>💰 Fund Scores</h3>
      <div class="kv-grid kv-3">
        <div class="kv"><span class="k">Enh Fund Score</span><span class="v ${sc(d.enh_fund,75,65)}">${d.enh_fund}</span></div>
        <div class="kv"><span class="k">Earnings Quality</span><span class="v ${sc(d.eq,75,60)}">${d.eq}</span></div>
        <div class="kv"><span class="k">Sales Growth %</span><span class="v ${sc(d.sales_g,20,10)}">${d.sales_g}</span></div>
        <div class="kv"><span class="k">Fin Strength</span><span class="v ${sc(d.fin_str,75,60)}">${d.fin_str}</span></div>
        <div class="kv"><span class="k">Inst Backing</span><span class="v ${sc(d.inst_bk,70,55)}">${d.inst_bk}</span></div>
        <div class="kv"><span class="k">Inv Score</span><span class="v ${sc(d.inv_score,80,65)}">${d.inv_score}</span></div>
      </div>
    </div>
    <div class="panel-section"><h3>🏦 Key Financials</h3>
      <div class="kv-grid kv-3">
        <div class="kv"><span class="k">ROCE %</span><span class="v ${sc(d.roce,20,12)}">${d.roce||'—'}</span></div>
        <div class="kv"><span class="k">ROE %</span><span class="v ${sc(d.roe,18,10)}">${d.roe||'—'}</span></div>
        <div class="kv"><span class="k">P/E</span><span class="v">${d.pe||'—'}</span></div>
        <div class="kv"><span class="k">EPS ₹</span><span class="v">${d.eps||'—'}</span></div>
        <div class="kv"><span class="k">NPM %</span><span class="v ${sc(d.npm,12,6)}">${d.npm||'—'}</span></div>
        <div class="kv"><span class="k">Div Yield %</span><span class="v">${d.divy||'—'}</span></div>
      </div>
    </div>
    <div class="panel-section"><h3>📈 Financial Performance</h3>
      <div class="kv-grid">
        <div class="kv"><span class="k">Sales ₹Cr</span><span class="v">${d.sales_cr?d.sales_cr.toLocaleString('en-IN'):'—'}</span></div>
        <div class="kv"><span class="k">Sales YoY %</span><span class="v ${d.sales_yoy>15?'pass':d.sales_yoy>5?'warn':'fail'}">${d.sales_yoy?'+'+d.sales_yoy+'%':'—'}</span></div>
        <div class="kv"><span class="k">PAT ₹Cr</span><span class="v ${(d.pat_cr||0)>=0?'pass':'fail'}">${d.pat_cr?d.pat_cr.toLocaleString('en-IN'):'—'}</span></div>
        <div class="kv"><span class="k">PAT YoY %</span><span class="v ${d.pat_yoy>20?'pass':d.pat_yoy>5?'warn':'fail'}">${d.pat_yoy?'+'+d.pat_yoy+'%':'—'}</span></div>
      </div>
    </div>
    <div class="panel-section"><h3>📊 Quarterly Results</h3>${qHtml}</div>
    ${(()=>{
      const ph=(typeof POSITION_HISTORY!=='undefined'&&POSITION_HISTORY[sym])||[];
      if(ph.length<2) return '';
      const W=180,H=40;
      const vals=ph.map(r=>r.p);
      const mn=Math.min(...vals),mx=Math.max(...vals),rng=(mx-mn)||0.001;
      const pts=vals.map((v,i)=>{
        const x=Math.round(i/(vals.length-1)*W*10)/10;
        const y=Math.round((H-(v-mn)/rng*(H-4)-2)*10)/10;
        return x+','+y;
      }).join(' ');
      const area='0,'+H+' '+pts+' '+W+','+H;
      const last=vals[vals.length-1];
      const col=last>=0?'#3fb950':'#f85149';
      const latest=ph[ph.length-1];
      const prev=ph[ph.length-2];
      const dayDelta=Math.round((latest.p-prev.p)*10)/10;
      const sg=dayDelta>=0?'+':'';
      const dcol=dayDelta>=0?'#3fb950':'#f85149';
      const allTime=Math.round(last*10)/10;
      const label='<span style="font-size:11px;color:var(--muted)">30-day P&L % · Day: <strong style="color:'+dcol+'">'+sg+dayDelta+'%</strong> · All-time: <strong style="color:'+col+'">'+sg+allTime+'%</strong></span>';
      const svg='<svg width="'+W+'" height="'+H+'" viewBox="0 0 '+W+' '+H+'" style="display:block;overflow:visible"><polygon points="'+area+'" fill="'+col+'" fill-opacity="0.12"/><polyline points="'+pts+'" fill="none" stroke="'+col+'" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/></svg>';
      return '<div class="panel-section"><h3>📈 P&L Trend</h3>'+label+'<div style="margin-top:8px">'+svg+'</div></div>';
    })()}`;
  document.getElementById('panel-body').innerHTML=body;
  document.getElementById('stock-panel').classList.add('open');
  document.getElementById('overlay').classList.add('open');
}
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeCard()});
"""

FUND_RULES_HTML = """
<div class="fund-rules-content">
<h2>📋 Aug Fund — Rules &amp; Governance</h2>
<div class="rules-grid">

<div class="rule-card"><h3>🔵 Small-Cap Fund (₹{SC_BUDGET_LAKH}L / {SC_SLOT_COUNT} slots)</h3><ul>
<li><strong>Stage:</strong> Stage 2 only (S2) — price &gt; SMA50 &gt; SMA150 &gt; SMA200</li>
<li><strong>Relative Strength:</strong> RS ≥ 65 (outperforming index)</li>
<li><strong>Technical Score:</strong> TechScore ≥ 65</li>
<li><strong>Fund Score:</strong> EnhFundScore ≥ 65</li>
<li><strong>Supertrend:</strong> BULLISH (below price)</li>
<li><strong>Signal:</strong> BUY or HOLD</li>
<li><strong>Stop Loss:</strong> −7% from entry (hard stop, no exceptions)</li>
<li><strong>Position Size:</strong> ₹{SC_SLOT_SIZE} per slot (1/{SC_SLOT_COUNT} of ₹{SC_BUDGET_LAKH}L)</li>
</ul></div>

<div class="rule-card"><h3>🟡 Mid-Cap Fund (₹{MC_BUDGET_LAKH}L / {MC_SLOT_COUNT} slots)</h3><ul>
<li><strong>Stage:</strong> Stage 1 or Stage 2 (S1/S2)</li>
<li><strong>Relative Strength:</strong> RS ≥ 65</li>
<li><strong>Technical Score:</strong> TechScore ≥ 65</li>
<li><strong>Fund Score:</strong> EnhFundScore ≥ 65</li>
<li><strong>Supertrend:</strong> BULLISH preferred</li>
<li><strong>Signal:</strong> BUY or HOLD</li>
<li><strong>Stop Loss:</strong> −6% from entry (hard stop)</li>
<li><strong>Position Size:</strong> ₹{MC_SLOT_SIZE} per slot (1/{MC_SLOT_COUNT} of ₹{MC_BUDGET_LAKH}L)</li>
</ul></div>

<div class="rule-card" style="grid-column:1/-1"><h3>🎯 Stock Selection Process — How We Pick Stocks</h3>
<ol style="padding-left:18px;line-height:2">
<li><strong>Universe:</strong> All NSE-listed stocks (EQ/BE series) with ≥ 1 year of history — ~2,800 symbols scored daily.</li>
<li><strong>Stage filter:</strong> Keep only Stage 2 (SC) or Stage 1/2 (MC). Stage 2 = price above SMA50 &gt; SMA150 &gt; SMA200 — a structurally healthy uptrend.</li>
<li><strong>Relative Strength ≥ 65:</strong> Stock must be outperforming the broad market on a percentile basis. RS &lt; 65 = market laggard, skip.</li>
<li><strong>Technical Score ≥ 65:</strong> Composite of RSI (30%), MACD (25%), SMA alignment (20%), trend momentum (15%), ATR (10%). Filters out weak setups.</li>
<li><strong>EnhFundScore ≥ 65:</strong> Fundamental quality gate — Earnings Quality + Sales Growth + Financial Strength + Institutional Backing (percentile-normalised within sector/size peer group).</li>
<li><strong>Supertrend = BULLISH + Signal = BUY/HOLD:</strong> Short-term momentum confirmation. BEARISH Supertrend = do not enter.</li>
<li><strong>Entry timing:</strong> Among qualifying stocks, prefer IDEAL zone entries (RSI 45–68, near pivot, not overextended). Avoid EXTENDED entries.</li>
<li><strong>Rank by Investment Score:</strong> Final sort by composite Investment Score (higher = better risk/reward). Top candidates per fund are reviewed for slot allocation.</li>
</ol>
</div>

<div class="rule-card" style="grid-column:1/-1"><h3>📐 Entry Timing &amp; Overextension Guide</h3>
<p style="font-size:12px;color:var(--muted);margin-bottom:12px">Every holding and candidate is classified into one of four zones based on RSI and VCP (Volatility Contraction Pattern) breakout metrics. Zone is shown as a badge on every position in the P&amp;L tab.</p>
<table style="width:100%;border-collapse:collapse;font-size:12px">
<thead><tr style="border-bottom:1px solid var(--border)">
  <th style="padding:6px 10px;text-align:left;color:var(--muted)">Zone</th>
  <th style="padding:6px 10px;text-align:left;color:var(--muted)">RSI</th>
  <th style="padding:6px 10px;text-align:left;color:var(--muted)">Breakout %</th>
  <th style="padding:6px 10px;text-align:left;color:var(--muted)">Action</th>
  <th style="padding:6px 10px;text-align:left;color:var(--muted)">Risk/Reward</th>
</tr></thead>
<tbody>
<tr style="border-bottom:1px solid #21262d">
  <td style="padding:6px 10px"><span style="font-size:10px;font-weight:700;padding:2px 7px;border-radius:4px;background:#1a3a1a;color:#3fb950;border:1px solid #3fb950">✅ IDEAL</span></td>
  <td style="padding:6px 10px">45 – 68</td>
  <td style="padding:6px 10px">0 – 5%</td>
  <td style="padding:6px 10px;color:#3fb950"><strong>BUY / Add</strong></td>
  <td style="padding:6px 10px">Best — in base, not yet extended. Close stop, maximum upside.</td>
</tr>
<tr style="border-bottom:1px solid #21262d">
  <td style="padding:6px 10px"><span style="font-size:10px;font-weight:700;padding:2px 7px;border-radius:4px;background:#1a2a3a;color:#58a6ff;border:1px solid #58a6ff">🎯 AT PIVOT</span></td>
  <td style="padding:6px 10px">≤ 75</td>
  <td style="padding:6px 10px">0 – 8%</td>
  <td style="padding:6px 10px;color:#58a6ff"><strong>Buy / Hold</strong></td>
  <td style="padding:6px 10px">Acceptable. Momentum confirmed but slightly above base. Tight stop still works.</td>
</tr>
<tr style="border-bottom:1px solid #21262d">
  <td style="padding:6px 10px"><span style="font-size:10px;font-weight:700;padding:2px 7px;border-radius:4px;background:#2a2a1a;color:#d29922;border:1px solid #d29922">⏳ BASING</span></td>
  <td style="padding:6px 10px">Any</td>
  <td style="padding:6px 10px">&lt; 0%</td>
  <td style="padding:6px 10px;color:#d29922"><strong>Watch / Wait</strong></td>
  <td style="padding:6px 10px">Price below pivot. Wait for breakout. Do not add exposure here.</td>
</tr>
<tr>
  <td style="padding:6px 10px"><span style="font-size:10px;font-weight:700;padding:2px 7px;border-radius:4px;background:#3a1a1a;color:#f85149;border:1px solid #f85149">⛔ EXTENDED</span></td>
  <td style="padding:6px 10px">&gt; 75</td>
  <td style="padding:6px 10px">&gt; 10%</td>
  <td style="padding:6px 10px;color:#f85149"><strong>Do NOT add</strong></td>
  <td style="padding:6px 10px">Overextended. Risk/reward is poor. For holdings: hold with trailing stop. For new entries: wait for pullback to 10-week MA.</td>
</tr>
</tbody>
</table>
<p style="font-size:11px;color:var(--muted);margin-top:10px">⚠️ <strong>Existing holdings in EXTENDED zone:</strong> Do not add to the position. Consider booking 25% at +30% and another 25% at +40%. Trail stop-loss to entry price at +20%.</p>
</div>

<div class="rule-card"><h3>🔁 Rebalancing &amp; Exit Rules</h3><ul>
<li><strong>Monthly review:</strong> Last trading day of each month</li>
<li><strong>Hard stop hit:</strong> Exit immediately</li>
<li><strong>Stage 2 failure:</strong> Exit within 2 days</li>
<li><strong>RS &lt; 55:</strong> Exit at next monthly review</li>
<li><strong>Trend → BEARISH:</strong> Exit within 2 days</li>
<li><strong>Profit booking:</strong> +20% → trail SL to entry; +30% → take 25% off; +40% → take another 25% off</li>
<li><strong>Max drawdown guard:</strong> Fund −15% from peak → pause new entries</li>
<li><strong>Slot reuse:</strong> Exited slot reused for next qualifying stock</li>
</ul></div>

<div class="rule-card"><h3>📊 Scoring Reference</h3><ul>
<li><strong>TechScore:</strong> ≥80 Strong · 65–80 OK · &lt;65 FAIL</li>
<li><strong>EnhFundScore:</strong> ≥75 Strong · 65–75 OK · &lt;65 FAIL</li>
<li><strong>RS:</strong> ≥85 Leader · 65–85 OK · &lt;65 FAIL</li>
<li><strong>Financial Strength:</strong> ≥70 preferred</li>
<li><strong>Inst Backing:</strong> ≥60 preferred</li>
<li><strong>Inv Score:</strong> ≥80 preferred</li>
</ul></div>

</div></div>
"""


def render_risk_tab(sc_rows: list, mc_rows: list) -> str:
    """Risk & position sizing tab — SL distance, capital at risk, allocation, aging."""
    all_rows = [dict(r, _fund="SC") for r in sc_rows] + [dict(r, _fund="MC") for r in mc_rows]
    total_invested = sum(r["invested"] for r in all_rows) or 1

    def _sl_dist(r):
        """% buffer between CMP and stop-loss (positive = above SL, negative = breached)."""
        return (r["price"] - r["sl"]) / r["price"] * 100 if r["price"] else 0

    def _cap_at_risk(r):
        """₹ loss if SL is hit from current price."""
        return max(0, (r["price"] - r["sl"]) * r["qty"])

    enriched = []
    for r in all_rows:
        d = dict(r)
        d["sl_dist"]     = _sl_dist(r)
        d["cap_at_risk"] = _cap_at_risk(r)
        d["alloc_pct"]   = r["invested"] / total_invested * 100
        enriched.append(d)

    # Sort by SL distance ascending (most vulnerable first)
    enriched.sort(key=lambda r: r["sl_dist"])

    total_cap_at_risk = sum(r["cap_at_risk"] for r in enriched)
    max_alloc         = max(r["alloc_pct"] for r in enriched) if enriched else 0
    avg_days          = sum(r["days"] for r in enriched) / len(enriched) if enriched else 0
    at_risk_count     = sum(1 for r in enriched if r["sl_dist"] < 10)
    aging_count       = sum(1 for r in enriched if r["days"] > 90)

    # ── Summary cards ─────────────────────────────────────────────────────────
    summary_html = f"""
<div class="summary-bar" style="margin-bottom:20px">
  <div class="stat-box">
    <div class="label">Capital at Risk</div>
    <div class="value neg">−₹{total_cap_at_risk:,.0f}</div>
    <div class="sub">If all SLs hit from current price</div>
  </div>
  <div class="stat-box">
    <div class="label">Largest Position</div>
    <div class="value {'warn' if max_alloc > 25 else 'pos'}">{max_alloc:.1f}%</div>
    <div class="sub">of total portfolio · rule: ≤25%</div>
  </div>
  <div class="stat-box">
    <div class="label">Avg Hold Period</div>
    <div class="value">{avg_days:.0f}d</div>
    <div class="sub">{aging_count} position{'s' if aging_count != 1 else ''} aging (>90d)</div>
  </div>
  <div class="stat-box">
    <div class="label">Near Stop-Loss</div>
    <div class="value {'neg' if at_risk_count else 'pos'}">{at_risk_count}</div>
    <div class="sub">position{'s' if at_risk_count != 1 else ''} within 10% of SL</div>
  </div>
</div>"""

    # ── Risk rows ──────────────────────────────────────────────────────────────
    def _sl_cls(d): return "sl-danger" if d < 10 else ("sl-warn" if d < 20 else "sl-safe")
    def _sl_bar_color(d): return "#f85149" if d < 10 else ("#d29922" if d < 20 else "#3fb950")
    def _alloc_flag(a): return ' <span style="color:#d29922;font-size:10px">▲</span>' if a > 25 else ""

    risk_rows = []
    for r in enriched:
        d = r["sl_dist"]
        bar_w   = min(120, max(2, int(d * 4)))      # scale: 30% SL-dist → full bar
        alloc_w = min(120, max(2, int(r["alloc_pct"] * 4)))
        aging   = ' <span class="aging-badge">AGING</span>' if r["days"] > 90 else ""
        fund_col = "#f0a500" if r["_fund"] == "MC" else "#58a6ff"
        fund_lbl = (f'<span style="font-size:10px;font-weight:700;padding:1px 5px;border-radius:3px;'
                    f'background:{fund_col}22;color:{fund_col};border:1px solid {fund_col}44">'
                    f'{r["_fund"]}</span>')

        risk_rows.append(
            f'<tr>'
            f'<td><span class="clickable-sym" onclick="openCard(\'{r["sym"]}\')">{r["sym"]}</span>{aging}</td>'
            f'<td>{fund_lbl}</td>'
            f'<td>₹{r["price"]:,.2f}</td>'
            f'<td>₹{r["entry"]:,.2f}</td>'
            f'<td style="color:var(--muted)">₹{r["sl"]:,.2f}</td>'
            # SL distance
            f'<td class="{_sl_cls(d)}">'
            f'<div class="risk-bar-wrap">'
            f'<div class="risk-bar" style="width:{bar_w}px;background:{_sl_bar_color(d)}"></div>'
            f'<span>{d:.1f}%</span></div></td>'
            # Capital at risk
            f'<td class="neg">−₹{r["cap_at_risk"]:,.0f}</td>'
            # Allocation
            f'<td>'
            f'<div class="risk-bar-wrap">'
            f'<div class="alloc-bar" style="width:{alloc_w}px"></div>'
            f'<span>{r["alloc_pct"]:.1f}%{_alloc_flag(r["alloc_pct"])}</span></div></td>'
            # Days
            f'<td style="color:{"#d29922" if r["days"] > 90 else "var(--muted)"}">{r["days"]}d</td>'
            f'</tr>'
        )

    rows_html = "\n".join(risk_rows)

    return f"""
<div style="max-width:1200px">
  {summary_html}
  <div class="fund-card">
    <div class="fund-header">
      <strong>Position Risk Monitor</strong>
      <span style="color:var(--muted);font-size:12px">Sorted by SL proximity · most vulnerable first</span>
    </div>
    <div class="tbl-wrap">
    <table>
      <thead><tr>
        <th>Symbol</th><th>Fund</th><th>CMP ₹</th><th>Entry ₹</th><th>Stop ₹</th>
        <th>SL Buffer</th><th>Cap at Risk</th><th>Allocation</th><th>Days Held</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    </div>
  </div>
</div>"""


def render_orders_tab(sc_rows: list, mc_rows: list) -> str:
    """Trade log tab — all filled positions with full detail."""
    def order_row(r, fund_label, sl_pct):
        c = "pos" if r["pnl"] >= 0 else "neg"
        s = "+" if r["pnl"] >= 0 else ""
        new = ' <span class="new-tag">NEW</span>' if r["new"] else ""
        return (
            f'<tr>'
            f'<td><span class="clickable-sym" onclick="openCard(\'{r["sym"]}\')">{r["sym"]}</span></td>'
            f'<td>{fund_label}</td>'
            f'<td>₹{r["entry"]:,.2f}</td>'
            f'<td>₹{r["price"]:,.2f}</td>'
            f'<td>{r["qty"]}</td>'
            f'<td>₹{r["invested"]:,.0f}</td>'
            f'<td class="{c}">{s}₹{r["pnl"]:,.0f} ({s}{r["pnl_pct"]:.1f}%){new}</td>'
            f'<td>₹{r["sl"]:,.2f} (−{int(sl_pct*100)}%)</td>'
            f'<td>{r["buy_date"]}</td>'
            f'<td>{r["sell_date"]}</td>'
            f'<td>{r["days"]}d</td>'
            f'</tr>'
        )

    all_rows = (
        [order_row(r, "Aug SC", 0.07) for r in sc_rows] +
        [order_row(r, "Aug MC", 0.06) for r in mc_rows]
    )
    rows_html = "\n".join(all_rows)

    return f"""
<div style="margin-bottom:16px">
  <h2 style="margin-bottom:6px">📒 Trade Log</h2>
  <div style="color:var(--muted);font-size:12px">All filled positions · Click symbol for detail</div>
</div>
<div class="fund-card">
  <div class="tbl-wrap"><table>
    <thead><tr>
      <th>Symbol</th><th>Fund</th><th>Entry ₹</th><th>CMP ₹</th><th>Qty</th>
      <th>Invested</th><th>P&amp;L</th><th>Stop ₹</th>
      <th>Buy Date</th><th>Sell Date</th><th>Days Held</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
  </table></div>
</div>"""


def render_candidates_tab(
    sc_cands: list, mc_cands: list, n_sc_dry: int, n_mc_dry: int,
    meta: dict | None = None,
) -> str:
    """Next potential candidates tab — stocks passing fund rules, not in portfolio."""
    meta = meta or {}
    slot_sc = (meta.get("budget_sc") or 200_000) / max(meta.get("slots_sc") or 9, 1)
    slot_mc = (meta.get("budget_mc") or 200_000) / max(meta.get("slots_mc") or 15, 1)

    def score_cls(v, hi, lo):
        if v >= hi: return "pos"
        if v >= lo: return "warn"
        return "neg"

    # Entry label → display colour
    ENTRY_STYLE = {
        "IDEAL":    ("background:#1a3a1a;color:#3fb950;border:1px solid #3fb950",    "✅ IDEAL"),
        "AT_PIVOT": ("background:#1a2a3a;color:#58a6ff;border:1px solid #58a6ff",   "🎯 AT PIVOT"),
        "BASING":   ("background:#2a2a1a;color:#d29922;border:1px solid #d29922",   "⏳ BASING"),
        "EXTENDED": ("background:#3a1a1a;color:#f85149;border:1px solid #f85149",   "⛔ EXTENDED"),
    }

    def entry_badge(label: str) -> str:
        style, text = ENTRY_STYLE.get(label, ("", label))
        return (f'<span style="display:inline-block;font-size:9.5px;font-weight:700;'
                f'padding:2px 7px;border-radius:4px;white-space:nowrap;{style}">{text}</span>')

    def cand_row(r, slot_budget):
        stage   = (r.get("stage") or "—").replace("STAGE_", "S")
        tech    = float(r.get("technical_score")      or 0)
        rs      = float(r.get("relative_strength")    or 0)
        fund    = float(r.get("enhanced_fund_score")  or 0)
        inv     = float(r.get("investment_score")     or 0)
        fin     = float(r.get("financial_strength")   or 0)
        inst    = float(r.get("institutional_backing")or 0)
        rsi     = float(r.get("rsi")                  or 0)
        bo_pct  = float(r.get("vcp_breakout_pct")     or 0)
        con_pct = float(r.get("vcp_contraction_pct")  or 0)
        vcp_s   = float(r.get("vcp_score")            or 0)
        sig     = r.get("trading_signal", "—")
        sig_cls = "pos" if sig == "BUY" else ("warn" if sig == "HOLD" else "neg")
        cmp     = float(r.get("cmp") or 0)
        label   = r.get("entry_label", "AT_PIVOT")

        # RSI: green 45-68, amber 40-75, red outside
        rsi_cls = "pos" if 45 <= rsi <= 68 else ("warn" if 40 <= rsi <= 75 else "neg")
        # Breakout %: green 0-5%, amber 5-10%, red >10% or negative
        bo_cls  = "pos" if 0 <= bo_pct <= 5 else ("warn" if 5 < bo_pct <= 10 else "neg")
        # Contraction: green ≥ 20%, amber 10-20%, red < 10%
        con_cls = "pos" if con_pct >= 20 else ("warn" if con_pct >= 10 else "neg")

        if cmp > 0:
            qty    = int(slot_budget // cmp)
            invest = qty * cmp
            qty_html = (
                f'<td style="font-weight:600;color:#58a6ff">{qty:,}</td>'
                f'<td style="color:var(--muted);font-size:11px">₹{invest:,.0f}</td>'
                f'<td style="color:var(--muted);font-size:11px">₹{cmp:,.2f}</td>'
            )
        else:
            qty_html = '<td>—</td><td>—</td><td>—</td>'

        vcp_score_html = (f'<td style="color:var(--muted);font-size:11px">{vcp_s:.0f}</td>'
                          if vcp_s > 0 else '<td style="color:var(--muted)">—</td>')

        return (
            f'<tr>'
            f'<td><strong>{r["symbol"]}</strong></td>'
            f'<td style="color:var(--muted);font-size:11px">{(r.get("company_name") or "")[:22]}</td>'
            f'<td style="color:var(--muted);font-size:11px">{(r.get("sector") or "")[:18]}</td>'
            f'<td>{stage}</td>'
            f'<td>{entry_badge(label)}</td>'
            f'<td class="{rsi_cls}">{rsi:.0f}</td>'
            f'<td class="{bo_cls}">{bo_pct:+.1f}%</td>'
            f'<td class="{con_cls}">{con_pct:.0f}%</td>'
            f'{vcp_score_html}'
            f'<td class="{score_cls(tech,80,65)}">{tech:.0f}</td>'
            f'<td class="{score_cls(rs,85,65)}">{rs:.0f}</td>'
            f'<td class="{score_cls(fund,75,65)}">{fund:.0f}</td>'
            f'<td class="{score_cls(inv,90,80)}">{inv:.0f}</td>'
            f'<td class="{sig_cls}">{sig}</td>'
            f'{qty_html}'
            f'</tr>'
        )

    def cand_table(rows, title, dry, color, slot_budget):
        if not rows:
            return f'<div class="fund-card" style="padding:20px;color:var(--muted)">No candidates found for {title}</div>'
        slot_fmt = f"₹{slot_budget:,.0f}"
        n_ideal  = sum(1 for r in rows if r.get("entry_label") == "IDEAL")
        n_pivot  = sum(1 for r in rows if r.get("entry_label") == "AT_PIVOT")
        n_ext    = sum(1 for r in rows if r.get("entry_label") == "EXTENDED")
        rows_html = "\n".join(cand_row(r, slot_budget) for r in rows)
        legend = (
            f'<span style="margin-left:12px;font-size:11px;color:var(--muted)">'
            f'Entry: <span style="color:#3fb950">{n_ideal} IDEAL</span>'
            f' · <span style="color:#58a6ff">{n_pivot} AT PIVOT</span>'
            f' · <span style="color:#f85149">{n_ext} EXTENDED</span></span>'
        )
        return f"""
<div class="fund-card">
  <div class="fund-header">
    <div>
      <h2 style="color:{color}">{title}</h2>
      <div style="color:var(--muted);font-size:12px">{dry} slot(s) available · Slot size {slot_fmt} · All pass fund rules gate{legend}</div>
    </div>
  </div>
  <div class="tbl-wrap"><table>
    <thead><tr>
      <th>Symbol</th><th>Company</th><th>Sector</th><th>Stage</th>
      <th>Entry</th><th>RSI</th><th>BO%</th><th>Contraction</th><th>VCP Score</th>
      <th>Tech</th><th>RS</th><th>Fund</th><th>Inv Score</th><th>Signal</th>
      <th>Qty</th><th>~Invest</th><th>CMP</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
  </table></div>
</div>"""

    sc_html = cand_table(sc_cands, "🔵 Next SC Candidates", n_sc_dry, "#58a6ff", slot_sc)
    mc_html = cand_table(mc_cands, "🟡 Next MC Candidates", n_mc_dry, "#d29922", slot_mc)

    return f"""
<div style="margin-bottom:16px">
  <h2 style="margin-bottom:6px">🎯 Next Potential Candidates</h2>
  <div style="color:var(--muted);font-size:12px">
    Stocks passing all fund rules · Not already in portfolio · Ranked by Investment Score
  </div>
</div>
{sc_html}
{mc_html}"""


# ─────────────────────────────────────────────────────────────────────────────
# Alerts helpers
# ─────────────────────────────────────────────────────────────────────────────
def fetch_alerts_db(db_syms: list[str]) -> dict:
    """Query signals schema for corporate events, bulk/block deals, insider alerts."""
    conn = pg()
    cur  = conn.cursor()

    events = {}
    try:
        cur.execute("""
            SELECT symbol, event_type, event_date, detail
            FROM signals.corporate_events
            WHERE symbol = ANY(%s) AND event_date >= CURRENT_DATE - INTERVAL '7 days'
            ORDER BY event_date
        """, (db_syms,))
        for sym, etype, edate, detail in cur.fetchall():
            events.setdefault(sym, []).append({
                "type": str(etype or ""), "date": str(edate), "detail": str(detail or "")
            })
    except Exception as e:
        print(f"  [alerts] corporate_events: {e}")

    deals = {}
    try:
        cur.execute("""
            SELECT symbol, deal_date, entity, side, qty, price, deal_type
            FROM signals.bulk_block_deals
            WHERE symbol = ANY(%s) AND deal_date >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY deal_date DESC
        """, (db_syms,))
        for sym, ddate, entity, side, qty, price, dtype in cur.fetchall():
            val_cr = round(float(qty or 0) * float(price or 0) / 1e7, 2)
            deals.setdefault(sym, []).append({
                "date": str(ddate), "entity": str(entity or ""),
                "side": str(side or ""), "qty": int(qty or 0),
                "value_cr": val_cr, "type": str(dtype or ""),
            })
    except Exception as e:
        print(f"  [alerts] bulk_block_deals: {e}")

    insider = {}
    try:
        cur.execute("""
            SELECT symbol, alert_date, entity, alert_type, qty, value_cr
            FROM signals.insider_alerts
            WHERE symbol = ANY(%s) AND alert_date >= CURRENT_DATE - INTERVAL '30 days'
              AND alert_type NOT IN ('BULK_DEAL_BUY', 'BULK_DEAL_SELL')
        """, (db_syms,))
        for sym, adate, entity, atype, qty, val in cur.fetchall():
            insider.setdefault(sym, []).append({
                "date": str(adate), "person": str(entity or ""),
                "type": str(atype or ""), "shares": int(qty or 0),
                "value_cr": float(val or 0),
            })
    except Exception as e:
        print(f"  [alerts] insider_alerts: {e}")

    conn.close()
    n_ev = sum(len(v) for v in events.values())
    n_dl = sum(len(v) for v in deals.values())
    n_in = sum(len(v) for v in insider.values())
    print(f"  [alerts] events={n_ev}, deals={n_dl}, insider={n_in}")
    return {"events": events, "deals": deals, "insider": insider}


def fetch_news_yf(nse_syms: list[str], max_per: int = 4) -> dict:
    """Parallel yfinance news fetch for all fund symbols. Returns {NSE_SYM: [articles]}."""
    def _fetch_one(sym):
        try:
            raw = yf.Ticker(f"{sym}.NS").news or []
            articles = []
            for item in raw[:max_per]:
                content = item.get("content", item) if isinstance(item, dict) else {}
                if isinstance(content, dict):
                    title   = content.get("title", "")
                    url_obj = content.get("canonicalUrl", {})
                    url     = url_obj.get("url", "") if isinstance(url_obj, dict) else content.get("url", "")
                    prov    = content.get("provider", {})
                    source  = prov.get("displayName", "") if isinstance(prov, dict) else content.get("source", "")
                    pub     = content.get("pubDate", "") or content.get("displayDate", "")
                else:
                    title  = item.get("title", "")
                    url    = item.get("link", "") or item.get("url", "")
                    source = item.get("publisher", "") or item.get("source", "")
                    pub    = item.get("providerPublishTime", "")
                    if isinstance(pub, (int, float)) and pub:
                        pub = datetime.fromtimestamp(pub).strftime("%Y-%m-%d")
                if title:
                    articles.append({
                        "title": title, "url": url,
                        "source": source, "date": str(pub)[:10],
                    })
            return sym, articles
        except Exception:
            return sym, []

    with ThreadPoolExecutor(max_workers=5) as ex:
        results = list(ex.map(_fetch_one, nse_syms))
    news = {sym: arts for sym, arts in results}
    total = sum(len(v) for v in news.values())
    print(f"  [news] {total} articles across {len(nse_syms)} symbols")
    return news


def summarize_news_llm(
    news: dict,
    db_alerts: dict,
    nse_to_db: dict,
) -> dict:
    """Summarize news + events + bulk deals per stock using OpenAI (gpt-4o-mini) with
    Ollama (granite4 / llama3) as fallback.

    Returns {NSE_SYM: {"summary": str|None, "sentiment": str, "action": str|None, "articles": list}}
    """
    # ── pick a chat completion client ──────────────────────────────────────
    client = None
    model  = None
    backend = None

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        try:
            from openai import OpenAI
            client  = OpenAI(api_key=openai_key)
            model   = "gpt-4o-mini"
            backend = "openai"
        except ImportError:
            pass

    if client is None:
        # Try Ollama local endpoint
        try:
            from openai import OpenAI as _OAI
            _ollama = _OAI(base_url="http://localhost:11434/v1", api_key="ollama")
            _ollama.models.list()          # quick ping
            client  = _ollama
            model   = "granite3.2:latest"
            backend = "ollama"
        except Exception:
            pass

    if client is None:
        print("  [llm] no LLM available (set OPENAI_API_KEY or start Ollama) — skipping summaries")
        return {sym: {"summary": None, "sentiment": "NEUTRAL", "action": None,
                      "articles": news.get(sym, [])} for sym in nse_to_db}

    print(f"  [llm] using {backend}/{model}")

    # ── build per-stock context + call LLM ─────────────────────────────────
    SYSTEM = (
        "You are a concise Indian equity research analyst. "
        "Respond ONLY in the exact format requested — no extra text."
    )
    PROMPT_TMPL = (
        "For NSE stock {sym}, summarize the information below.\n\n"
        "Respond in EXACTLY this format:\n"
        "SUMMARY: [2-3 sentences covering news, results, events, institutional activity]\n"
        "SENTIMENT: [BULLISH or BEARISH or NEUTRAL]\n"
        "ACTION: [one sentence — key risk or opportunity to watch]\n\n"
        "---\n{context}"
    )

    def _build_context(nse_sym: str) -> str:
        db_sym = nse_to_db.get(nse_sym, nse_sym)
        parts  = []
        articles = news.get(nse_sym, [])
        if articles:
            lines = "\n".join(f"- {a['title']} ({a['source']}, {a['date']})" for a in articles)
            parts.append(f"Recent news:\n{lines}")
        events = db_alerts.get("events", {}).get(db_sym, [])
        if events:
            lines = "\n".join(
                f"- {e.get('event_type','')} on {e.get('event_date','')}: {e.get('detail','')}"
                for e in events
            )
            parts.append(f"Corporate events:\n{lines}")
        deals = db_alerts.get("deals", {}).get(db_sym, [])
        if deals:
            buy_q  = sum(d["qty"] for d in deals if str(d.get("side","")).upper() == "BUY")
            sell_q = sum(d["qty"] for d in deals if str(d.get("side","")).upper() == "SELL")
            ents   = list({d["entity"] for d in deals if d.get("entity")})[:4]
            parts.append(
                f"Bulk/block deals (30d): BUY {buy_q:,} · SELL {sell_q:,} shares. "
                f"Participants: {', '.join(ents)}"
            )
        return "\n\n".join(parts)

    def _parse(text: str) -> tuple[str, str, str]:
        summary = sentiment = action = ""
        for line in text.splitlines():
            if line.startswith("SUMMARY:"):
                summary = line[8:].strip()
            elif line.startswith("SENTIMENT:"):
                sentiment = line[10:].strip().upper()
            elif line.startswith("ACTION:"):
                action = line[7:].strip()
        if sentiment not in ("BULLISH", "BEARISH", "NEUTRAL"):
            sentiment = "NEUTRAL"
        return summary, sentiment, action

    def _summarize_one(nse_sym: str) -> dict:
        articles = news.get(nse_sym, [])
        ctx = _build_context(nse_sym)
        if not ctx:
            return {"summary": None, "sentiment": "NEUTRAL", "action": None, "articles": articles}
        try:
            resp = client.chat.completions.create(
                model=model,
                max_tokens=250,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user",   "content": PROMPT_TMPL.format(sym=nse_sym, context=ctx)},
                ],
            )
            text = resp.choices[0].message.content.strip()
            summary, sentiment, action = _parse(text)
            return {"summary": summary or None, "sentiment": sentiment,
                    "action": action or None, "articles": articles}
        except Exception as exc:
            print(f"  [llm] {nse_sym}: {exc}")
            return {"summary": None, "sentiment": "NEUTRAL", "action": None, "articles": articles}

    summaries = {sym: _summarize_one(sym) for sym in nse_to_db}
    n_done = sum(1 for v in summaries.values() if v.get("summary"))
    print(f"  [llm] summarized {n_done}/{len(nse_to_db)} stocks")
    return summaries


def generate_technical_alerts(
    sc_holds: dict, mc_holds: dict,
    prices: dict, snaps: dict, qtrs: dict,
    nse_to_db: dict,
) -> list[dict]:
    """Compute alert dicts from DB data + live prices. Sorted CRITICAL→WARNING→POSITIVE."""
    alerts = []

    all_holds = (
        [(sym, h, 0.07) for sym, h in sc_holds.items()] +
        [(sym, h, 0.06) for sym, h in mc_holds.items()]
    )

    for sym, h, sl_pct in all_holds:
        entry    = float(h["entry"])
        sl_price = round(entry * (1 - sl_pct), 2)
        price    = prices.get(sym) or entry
        db_sym   = nse_to_db.get(sym, sym)
        snap     = snaps.get(db_sym, {})

        tech       = float(snap.get("technical_score")    or 0)
        stage      = (snap.get("stage") or "").replace("STAGE_", "S")
        rs         = float(snap.get("relative_strength")  or 0)
        supertrend = snap.get("supertrend_state", "")
        signal     = snap.get("trading_signal", "")

        # ── Price alerts ──────────────────────────────────────────────────────
        if price <= sl_price:
            pct = (price - sl_price) / sl_price * 100
            alerts.append({
                "sym": sym, "severity": "CRITICAL", "category": "PRICE", "icon": "🔴",
                "title": "Stop-loss breached",
                "detail": f"CMP ₹{price:,.2f} is below stop ₹{sl_price:,.2f} ({pct:+.1f}% vs entry ₹{entry:,.2f})",
            })
        elif price > sl_price and (price - sl_price) / price < 0.03:
            gap = (price - sl_price) / price * 100
            alerts.append({
                "sym": sym, "severity": "WARNING", "category": "PRICE", "icon": "⚠️",
                "title": f"Near stop-loss ({gap:.1f}% gap)",
                "detail": f"CMP ₹{price:,.2f}  |  Stop ₹{sl_price:,.2f}  |  only {gap:.1f}% buffer",
            })

        # ── Technical alerts ──────────────────────────────────────────────────
        if supertrend == "BEARISH":
            alerts.append({
                "sym": sym, "severity": "CRITICAL", "category": "TECHNICAL", "icon": "🔴",
                "title": "Supertrend BEARISH",
                "detail": "Supertrend flipped bearish — fund rule violation, consider exit within 2 days",
            })

        if signal == "SELL":
            alerts.append({
                "sym": sym, "severity": "CRITICAL", "category": "TECHNICAL", "icon": "🔴",
                "title": "Signal: SELL",
                "detail": f"Trading signal = SELL for {sym}",
            })

        if stage and stage not in ("S1", "S2"):
            alerts.append({
                "sym": sym, "severity": "CRITICAL", "category": "TECHNICAL", "icon": "🔴",
                "title": f"Stage broken ({stage})",
                "detail": f"Stage has moved to {stage} — fund rule violation (SC requires S2, MC requires S1/S2)",
            })

        if 0 < rs < 55:
            alerts.append({
                "sym": sym, "severity": "WARNING", "category": "TECHNICAL", "icon": "⚠️",
                "title": f"RS weak (RS={rs:.0f} < 55)",
                "detail": f"Relative Strength {rs:.1f} — exit trigger at next monthly review",
            })
        elif 55 <= rs < 65:
            alerts.append({
                "sym": sym, "severity": "WARNING", "category": "TECHNICAL", "icon": "⚠️",
                "title": f"RS borderline (RS={rs:.0f})",
                "detail": f"Relative Strength {rs:.1f} is in the 55–65 borderline zone",
            })

        if 0 < tech < 55:
            alerts.append({
                "sym": sym, "severity": "WARNING", "category": "TECHNICAL", "icon": "⚠️",
                "title": f"TechScore degraded ({tech:.0f})",
                "detail": f"Technical score {tech:.1f} is below fund threshold of 65",
            })

        # ── Fundamental / quarterly alerts ────────────────────────────────────
        sym_qtrs = qtrs.get(db_sym, [])
        if len(sym_qtrs) >= 2:
            q0, q1 = sym_qtrs[0], sym_qtrs[1]
            if q1["revenue"] > 0:
                rev_chg = (q0["revenue"] - q1["revenue"]) / q1["revenue"] * 100
                if rev_chg < -15:
                    alerts.append({
                        "sym": sym, "severity": "WARNING", "category": "FUNDAMENTAL", "icon": "⚠️",
                        "title": f"Revenue declined QoQ ({rev_chg:.1f}%)",
                        "detail": f"{q0['label']}: ₹{q0['revenue']:.1f}Cr  ←  {q1['label']}: ₹{q1['revenue']:.1f}Cr",
                    })
            if q1["pat"] > 0:
                pat_chg = (q0["pat"] - q1["pat"]) / q1["pat"] * 100
                if pat_chg < -20:
                    alerts.append({
                        "sym": sym, "severity": "WARNING", "category": "FUNDAMENTAL", "icon": "⚠️",
                        "title": f"PAT declined QoQ ({pat_chg:.1f}%)",
                        "detail": f"{q0['label']}: ₹{q0['pat']:.1f}Cr  ←  {q1['label']}: ₹{q1['pat']:.1f}Cr",
                    })

        # ── Positive signals ──────────────────────────────────────────────────
        if rs >= 85 and tech >= 80:
            alerts.append({
                "sym": sym, "severity": "POSITIVE", "category": "TECHNICAL", "icon": "✅",
                "title": f"Strong momentum (RS={rs:.0f}, Tech={tech:.0f})",
                "detail": "Both RS and TechScore well above thresholds — hold with confidence",
            })

        if supertrend == "BULLISH" and signal == "BUY":
            alerts.append({
                "sym": sym, "severity": "POSITIVE", "category": "TECHNICAL", "icon": "✅",
                "title": "Buy signal confirmed",
                "detail": "Supertrend BULLISH + Signal BUY — fully aligned for continuation",
            })

    order = {"CRITICAL": 0, "WARNING": 1, "POSITIVE": 2, "INFO": 3}
    alerts.sort(key=lambda x: order.get(x["severity"], 3))
    return alerts


def render_action_items_tab(tech_alerts: list) -> str:
    """Render the top-level action queue from critical and warning alerts."""
    action_alerts = [a for a in tech_alerts if a.get("severity") in {"CRITICAL", "WARNING"}]
    severity_order = {"CRITICAL": 0, "WARNING": 1}
    action_alerts.sort(key=lambda a: (severity_order.get(a.get("severity"), 9), a.get("sym", "")))

    def next_step(a: dict) -> str:
        title = str(a.get("title", ""))
        category = str(a.get("category", ""))
        if "Stop-loss breached" in title:
            return "Review exit/reduction against the fund stop policy"
        if "Supertrend BEARISH" in title or "Signal: SELL" in title:
            return "Review position; avoid fresh additions"
        if "Stage broken" in title:
            return "Reassess thesis and position sizing at the next review"
        if "Near stop-loss" in title:
            return "Set a close alert and monitor the stop buffer closely"
        if category == "FUNDAMENTAL":
            return "Review the next result and earnings-quality trend"
        return "Review at the next portfolio checkpoint"

    if not action_alerts:
        body = '<div style="color:var(--pos);font-weight:600;padding:16px">✅ No critical or warning action items</div>'
    else:
        rows = []
        for a in action_alerts:
            sev = a["severity"]
            color = "#ef4444" if sev == "CRITICAL" else "#f59e0b"
            rows.append(
                f'<tr><td><span style="color:{color};font-weight:700">{a.get("icon", "⚠️")} {sev}</span></td>'
                f'<td><strong>{a.get("sym", "—")}</strong></td><td>{a.get("title", "—")}</td>'
                f'<td style="color:var(--muted);font-size:11px">{a.get("detail", "")}</td>'
                f'<td style="color:var(--accent);font-size:11px">{next_step(a)}</td></tr>'
            )
        body = (
            '<div class="tbl-wrap"><table><thead><tr>'
            '<th>Priority</th><th>Symbol</th><th>Trigger</th><th>Evidence</th><th>Suggested next step</th>'
            '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>'
        )
    count_color = "#ef4444" if any(a.get("severity") == "CRITICAL" for a in action_alerts) else "#f59e0b" if action_alerts else "#3fb950"
    return f'''
<div id="tab-actions" class="tab-content active">
  <div class="fund-card">
    <div class="fund-header"><div><h2>✅ Action Items</h2>
      <div style="color:var(--muted);font-size:12px">Prioritised from the current alert engine · review queue only, not auto-trade instructions</div>
    </div><div style="font-size:22px;font-weight:700;color:{count_color}">{len(action_alerts)}</div></div>
    {body}
  </div>
</div>'''


def render_alerts_tab(
    tech_alerts: list, db_alerts: dict, news_summaries: dict, nse_to_db: dict
) -> str:
    """Render the full Alerts & Research tab HTML."""
    critical = [a for a in tech_alerts if a["severity"] == "CRITICAL"]
    warnings  = [a for a in tech_alerts if a["severity"] == "WARNING"]
    positives = [a for a in tech_alerts if a["severity"] == "POSITIVE"]

    # ── Section 1: Action Alerts — grouped by stock ───────────────────────────
    SEV_ORDER  = {"CRITICAL": 0, "WARNING": 1, "POSITIVE": 2, "INFO": 3}
    SEV_COLOR  = {"CRITICAL": "#ef4444", "WARNING": "#f59e0b", "POSITIVE": "#10b981", "INFO": "#8b949e"}
    SEV_LABEL  = {"CRITICAL": "CRITICAL", "WARNING": "WARNING", "POSITIVE": "OK", "INFO": "INFO"}

    # Group alerts per symbol, preserving their order
    from collections import defaultdict
    by_sym: dict = defaultdict(list)
    for a in tech_alerts:
        by_sym[a["sym"]].append(a)

    def worst(alerts):
        return min(alerts, key=lambda a: SEV_ORDER.get(a["severity"], 3))["severity"]

    # Sort symbols: CRITICAL stocks first, then WARNING, then POSITIVE
    syms_sorted = sorted(by_sym.keys(), key=lambda s: SEV_ORDER.get(worst(by_sym[s]), 3))

    def alert_card(a):
        cls = a["severity"].lower()
        return (
            f'<div class="alert-card {cls}" style="margin:4px 0">'
            f'<div style="display:flex;justify-content:space-between;align-items:center">'
            f'<strong>{a["icon"]} {a["title"]}</strong>'
            f'<span style="font-size:10px;color:var(--muted)">{a["category"]}</span>'
            f'</div>'
            f'<div style="font-size:12px;margin-top:3px;color:var(--muted)">{a["detail"]}</div>'
            f'</div>'
        )

    def stock_group(sym):
        alerts = by_sym[sym]
        w = worst(alerts)
        col = SEV_COLOR[w]
        lbl = SEV_LABEL[w]
        n_crit = sum(1 for a in alerts if a["severity"] == "CRITICAL")
        n_warn = sum(1 for a in alerts if a["severity"] == "WARNING")
        badge_parts = []
        if n_crit: badge_parts.append(f'<span style="background:#ef4444;color:#fff;border-radius:8px;padding:1px 6px;font-size:10px;margin-left:4px">{n_crit} CRITICAL</span>')
        if n_warn: badge_parts.append(f'<span style="background:#b45309;color:#fff;border-radius:8px;padding:1px 6px;font-size:10px;margin-left:4px">{n_warn} WARNING</span>')
        cards = "".join(alert_card(a) for a in sorted(alerts, key=lambda a: SEV_ORDER.get(a["severity"], 3)))
        return (
            f'<div style="margin-bottom:12px;border:1px solid {col};border-radius:8px;overflow:hidden">'
            f'<div style="background:rgba(0,0,0,.25);padding:8px 14px;display:flex;align-items:center;gap:8px;border-bottom:1px solid {col}">'
            f'<strong style="font-size:13px;color:{col}">{sym}</strong>'
            f'{"".join(badge_parts)}'
            f'</div>'
            f'<div style="padding:6px 10px">{cards}</div>'
            f'</div>'
        )

    if syms_sorted:
        alerts_html = "".join(stock_group(s) for s in syms_sorted)
    else:
        alerts_html = '<div style="color:var(--pos);font-weight:600;padding:16px">✅ All positions clear — no action required</div>'

    # ── Section 2: Corporate Events ───────────────────────────────────────────
    db_sym_to_nse = {v: k for k, v in nse_to_db.items()}
    all_events = []
    for db_sym, evts in db_alerts.get("events", {}).items():
        nse_sym = db_sym_to_nse.get(db_sym, db_sym)
        for e in evts:
            all_events.append((nse_sym, e["type"], e["date"], e["detail"]))

    if all_events:
        hdr = "".join(
            f'<th style="text-align:left;padding:6px 10px;background:#1c2128;color:var(--muted);font-size:11px">{h}</th>'
            for h in ["Symbol", "Event", "Date", "Detail"]
        )
        rows = "".join(
            f'<tr><td style="padding:5px 10px">{sym}</td>'
            f'<td style="padding:5px 10px">{etype}</td>'
            f'<td style="padding:5px 10px">{edate}</td>'
            f'<td style="padding:5px 10px;font-size:11px;color:var(--muted)">{detail[:100]}</td></tr>'
            for sym, etype, edate, detail in all_events
        )
        events_html = f'<table style="width:100%;border-collapse:collapse"><thead><tr>{hdr}</tr></thead><tbody>{rows}</tbody></table>'
    else:
        events_html = '<div style="color:var(--muted);font-size:12px;padding:8px">No upcoming events in signals.corporate_events for fund positions (last 7 days)</div>'

    # ── Section 3: Institutional Activity ────────────────────────────────────
    all_inst = []
    for db_sym, dlist in db_alerts.get("deals", {}).items():
        nse_sym = db_sym_to_nse.get(db_sym, db_sym)
        for d in dlist:
            all_inst.append((d["date"], nse_sym, d["entity"][:28], d["side"], d["qty"], d["value_cr"], d["type"]))
    for db_sym, ilist in db_alerts.get("insider", {}).items():
        nse_sym = db_sym_to_nse.get(db_sym, db_sym)
        for i in ilist:
            all_inst.append((i["date"], nse_sym, i["person"][:28], i["type"], i["shares"], i["value_cr"], "Insider"))
    all_inst.sort(key=lambda x: x[0], reverse=True)

    if all_inst:
        hdr = "".join(
            f'<th style="text-align:left;padding:6px 10px;background:#1c2128;color:var(--muted);font-size:11px">{h}</th>'
            for h in ["Date", "Symbol", "Entity", "Side", "Qty", "Value ₹Cr", "Type"]
        )
        rows = "".join(
            f'<tr><td style="padding:5px 10px">{d}</td><td style="padding:5px 10px">{s}</td>'
            f'<td style="padding:5px 10px;font-size:11px">{e}</td>'
            f'<td style="padding:5px 10px">{side}</td>'
            f'<td style="padding:5px 10px;text-align:right">{q:,}</td>'
            f'<td style="padding:5px 10px;text-align:right">{v:.2f}</td>'
            f'<td style="padding:5px 10px;font-size:11px;color:var(--muted)">{t}</td></tr>'
            for d, s, e, side, q, v, t in all_inst
        )
        inst_html = f'<table style="width:100%;border-collapse:collapse"><thead><tr>{hdr}</tr></thead><tbody>{rows}</tbody></table>'
    else:
        inst_html = '<div style="color:var(--muted);font-size:12px;padding:8px">No institutional activity for fund positions in the last 30 days</div>'

    # ── Section 4: News & Research (LLM summaries + raw links) ──────────────
    SENT_ICON = {"BULLISH": "📈", "BEARISH": "📉", "NEUTRAL": "➡️"}
    news_parts = []
    for nse_sym in nse_to_db.keys():
        info     = news_summaries.get(nse_sym, {})
        articles = info.get("articles", [])
        summary  = info.get("summary")
        sentiment = (info.get("sentiment") or "NEUTRAL").upper()
        action   = info.get("action")
        sent_cls = sentiment.lower() if sentiment in ("BULLISH", "BEARISH", "NEUTRAL") else "neutral"
        sent_icon = SENT_ICON.get(sentiment, "➡️")

        # LLM summary card
        if summary:
            action_html = (
                f'<div style="margin-top:6px;font-size:11px;color:var(--muted)">'
                f'<strong>Watch:</strong> {action}</div>'
            ) if action else ""
            summary_html = (
                f'<div class="news-summary {sent_cls}">'
                f'<div style="display:flex;align-items:center;margin-bottom:4px">'
                f'<span style="font-size:11px;font-weight:600">{sent_icon} LLM Analysis</span>'
                f'<span class="news-sentiment {sent_cls}">{sentiment}</span>'
                f'</div>'
                f'<div style="font-size:12px;line-height:1.5">{summary}</div>'
                f'{action_html}'
                f'</div>'
            )
        else:
            summary_html = ""

        # Raw article links
        if articles:
            arts_html = "".join(
                f'<div style="padding:4px 0;border-bottom:1px solid rgba(255,255,255,.05)">'
                f'<a href="{a["url"]}" target="_blank" '
                f'style="color:var(--accent);font-size:11px;text-decoration:none">{a["title"]}</a>'
                f'<span style="color:var(--muted);font-size:10px"> · {a["source"]} · {a["date"]}</span>'
                f'</div>'
                for a in articles
            )
        else:
            arts_html = (
                '<div style="color:var(--muted);font-size:11px;padding:3px 0">'
                'No recent news available via yfinance</div>'
            )

        news_parts.append(
            f'<div style="margin-bottom:18px">'
            f'<strong style="font-size:13px;color:var(--accent)">{nse_sym}</strong>'
            f'<div style="margin-top:6px">{summary_html}{arts_html}</div>'
            f'</div>'
        )
    news_html = "".join(news_parts)

    n_crit = len(critical)
    n_warn = len(warnings)
    n_pos  = len(positives)
    return f"""
<div style="margin-bottom:16px">
  <h2 style="margin-bottom:6px">🚨 Alerts &amp; Research</h2>
  <div style="color:var(--muted);font-size:12px">{n_crit} critical · {n_warn} warnings · {n_pos} positive signals</div>
</div>

<div class="fund-card">
  <div class="fund-header"><h2>🚨 Action Alerts</h2></div>
  <div style="padding:16px">{alerts_html}</div>
</div>

<div class="fund-card">
  <div class="fund-header">
    <h2>📋 Corporate Events <span style="font-size:11px;color:var(--muted);font-weight:400">(last 7 days)</span></h2>
  </div>
  <div style="padding:16px">{events_html}</div>
</div>

<div class="fund-card">
  <div class="fund-header">
    <h2>🏦 Institutional Activity <span style="font-size:11px;color:var(--muted);font-weight:400">(last 30 days)</span></h2>
  </div>
  <div style="padding:16px">{inst_html}</div>
</div>

<div class="fund-card">
  <div class="fund-header"><h2>📰 News Feed</h2></div>
  <div style="padding:16px">{news_html}</div>
</div>
"""


def _render_fund_summary_banner(
    sc_sum: dict, mc_sum: dict, exits: list,
    tech_alerts: list, n_sc: int, n_mc: int,
    sc_rows: list, mc_rows: list,
    generated_at: str,
) -> str:
    """Top-of-page executive summary banner — fund health, P&L, exits, alerts."""
    tot_inv = sc_sum["inv"] + mc_sum["inv"]
    tot_pnl = sc_sum["pnl"] + mc_sum["pnl"]
    tot_pct = (tot_pnl / tot_inv * 100) if tot_inv else 0

    total_realized     = sum(float(e.get("realized_pnl", 0)) for e in exits)
    total_exit_inv     = sum(float(e["entry_price"]) * int(e["qty"]) for e in exits)
    total_exit_pct     = (total_realized / total_exit_inv * 100) if total_exit_inv else 0

    n_critical = len([a for a in tech_alerts if a.get("severity") == "CRITICAL"])
    n_warn     = len([a for a in tech_alerts if a.get("severity") == "WARNING"])
    n_pos      = len([a for a in tech_alerts if a.get("severity") == "POSITIVE"])

    all_rows   = sc_rows + mc_rows
    n_winners  = sum(1 for r in all_rows if r["pnl"] >= 0)
    n_losers   = sum(1 for r in all_rows if r["pnl"] < 0)

    best  = max(all_rows, key=lambda r: r["pnl_pct"]) if all_rows else None
    worst = min(all_rows, key=lambda r: r["pnl_pct"]) if all_rows else None

    # Health badge
    if n_critical > 0:
        health_style = "background:#3a1212;border:1px solid #f85149;color:#f85149"
        health_label = "⚠️ CAUTION"
    elif n_warn > 0:
        health_style = "background:#2a2210;border:1px solid #d29922;color:#d29922"
        health_label = "🟡 MONITORING"
    else:
        health_style = "background:#122a1a;border:1px solid #3fb950;color:#3fb950"
        health_label = "✅ HEALTHY"

    pnl_col = "#3fb950" if tot_pnl >= 0 else "#f85149"
    sg      = "+" if tot_pnl >= 0 else ""
    r_col   = "#3fb950" if total_realized >= 0 else "#f85149"
    r_sg    = "+" if total_realized >= 0 else ""

    best_html  = (f'<span style="color:#3fb950;font-weight:700">{best["sym"]} {sg}{best["pnl_pct"]:.1f}%</span>'
                  if best else "—")
    worst_html = (f'<span style="color:#f85149;font-weight:700">{worst["sym"]} {"+" if worst["pnl_pct"]>=0 else ""}{worst["pnl_pct"]:.1f}%</span>'
                  if worst else "—")

    exits_html = ""
    if exits:
        exit_rows = "".join(
            f'<span style="margin-right:12px;font-size:12px">'
            f'<strong>{e["symbol"]}</strong> '
            f'<span style="color:{"#3fb950" if float(e.get("realized_pct",0))>=0 else "#f85149"}">'
            f'{"+" if float(e.get("realized_pct",0))>=0 else ""}{float(e.get("realized_pct",0)):.1f}%</span>'
            f' ({e.get("type","FULL")}) {e["exit_date"]}'
            f'</span>'
            for e in sorted(exits, key=lambda x: x["exit_date"], reverse=True)
        )
        exits_html = f"""
    <div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--border)">
      <span style="color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.05em;margin-right:10px">Exits ({len(exits)})</span>
      {exit_rows}
      <span style="color:var(--muted);font-size:11px;margin-left:8px">|</span>
      <span style="margin-left:10px;font-size:12px">Total realized:
        <strong style="color:{r_col}">{r_sg}₹{abs(total_realized):,.0f} ({r_sg}{total_exit_pct:.1f}%)</strong>
      </span>
    </div>"""

    alert_html = ""
    if n_critical or n_warn:
        alert_html = (
            f'<span style="margin-left:12px;font-size:12px;color:#d29922">'
            f'{n_critical} critical · {n_warn} warnings · {n_pos} positive</span>'
        )

    return f"""
<div style="margin:16px 20px;padding:18px 22px;background:var(--card);border:1px solid var(--border);border-radius:12px">
  <div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:12px">

    <div>
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
        <span style="font-size:13px;font-weight:700;padding:3px 10px;border-radius:6px;{health_style}">{health_label}</span>
        <span style="color:var(--muted);font-size:12px">Generated {generated_at}</span>
        {alert_html}
      </div>
      <div style="font-size:28px;font-weight:800;color:{pnl_col};line-height:1">{sg}₹{abs(tot_pnl):,.0f}
        <span style="font-size:16px;font-weight:600"> {sg}{tot_pct:.1f}%</span>
      </div>
      <div style="color:var(--muted);font-size:12px;margin-top:4px">
        Combined open P&amp;L on ₹{tot_inv:,.0f} invested · {n_sc+n_mc} positions
      </div>
    </div>

    <div style="display:flex;gap:24px;flex-wrap:wrap">
      <div>
        <div style="color:var(--muted);font-size:11px;text-transform:uppercase;margin-bottom:2px">SC Fund ({n_sc} pos)</div>
        <div style="font-size:18px;font-weight:700;color:{"#3fb950" if sc_sum["pnl"]>=0 else "#f85149"}">
          {"+" if sc_sum["pnl"]>=0 else ""}₹{abs(sc_sum["pnl"]):,.0f}
          <span style="font-size:13px"> {"+" if sc_sum["pct"]>=0 else ""}{sc_sum["pct"]:.1f}%</span>
        </div>
        <div style="color:var(--muted);font-size:11px">{sc_sum["W"]}W · {sc_sum["L"]}L</div>
      </div>
      <div>
        <div style="color:var(--muted);font-size:11px;text-transform:uppercase;margin-bottom:2px">MC Fund ({n_mc} pos)</div>
        <div style="font-size:18px;font-weight:700;color:{"#3fb950" if mc_sum["pnl"]>=0 else "#f85149"}">
          {"+" if mc_sum["pnl"]>=0 else ""}₹{abs(mc_sum["pnl"]):,.0f}
          <span style="font-size:13px"> {"+" if mc_sum["pct"]>=0 else ""}{mc_sum["pct"]:.1f}%</span>
        </div>
        <div style="color:var(--muted);font-size:11px">{mc_sum["W"]}W · {mc_sum["L"]}L</div>
      </div>
      <div>
        <div style="color:var(--muted);font-size:11px;text-transform:uppercase;margin-bottom:2px">Best / Worst</div>
        <div style="font-size:13px;line-height:1.6">{best_html}</div>
        <div style="font-size:13px">{worst_html}</div>
      </div>
    </div>

  </div>
  {exits_html}
</div>"""


def _render_realized_pnl_card(exits: list[dict]) -> str:
    """Card showing all realized exits with P&L. Shown only when exits exist."""
    if not exits:
        return ""

    total_realized = sum(float(e.get("realized_pnl", 0)) for e in exits)
    total_invested = sum(float(e["entry_price"]) * int(e["qty"]) for e in exits)
    total_pct      = (total_realized / total_invested * 100) if total_invested else 0

    FUND_COL = {"Aug SC": "#58a6ff", "Aug MC": "#f0a500"}
    TYPE_STYLE = {
        "PARTIAL": ("background:#1a2a3a;color:#58a6ff;border:1px solid #58a6ff", "PARTIAL"),
        "FULL":    ("background:#3a1a1a;color:#f85149;border:1px solid #f85149",  "FULL EXIT"),
    }

    def _tr(e) -> str:
        pnl     = float(e.get("realized_pnl", 0))
        pct     = float(e.get("realized_pct", 0))
        col     = "#3fb950" if pnl >= 0 else "#f85149"
        sg      = "+" if pnl >= 0 else ""
        fc      = FUND_COL.get(e.get("fund", ""), "#8b949e")
        ts, tl  = TYPE_STYLE.get(e.get("type", "FULL"), ("", e.get("type", "")))
        invested = float(e["entry_price"]) * int(e["qty"])
        return (
            f'<tr>'
            f'<td><strong>{e["symbol"]}</strong></td>'
            f'<td><span style="font-size:10px;font-weight:700;padding:1px 5px;border-radius:3px;'
            f'background:{fc}22;color:{fc};border:1px solid {fc}44">{e.get("fund","—")}</span></td>'
            f'<td>{e["exit_date"]}</td>'
            f'<td>{e["qty"]}</td>'
            f'<td>₹{float(e["entry_price"]):,.2f}</td>'
            f'<td>₹{float(e["exit_price"]):,.2f}</td>'
            f'<td>₹{invested:,.0f}</td>'
            f'<td style="color:{col};font-weight:700">{sg}₹{abs(pnl):,.0f}</td>'
            f'<td style="color:{col};font-weight:700">{sg}{pct:.1f}%</td>'
            f'<td><span style="font-size:9.5px;font-weight:700;padding:1px 5px;border-radius:3px;{ts}">{tl}</span></td>'
            f'<td style="color:var(--muted);font-size:11px">{e.get("note","")[:60]}</td>'
            f'</tr>'
        )

    rows_html = "".join(_tr(e) for e in sorted(exits, key=lambda x: x["exit_date"], reverse=True))
    pnl_col   = "#3fb950" if total_realized >= 0 else "#f85149"
    sg        = "+" if total_realized >= 0 else ""

    return f"""
<div class="fund-card" style="margin-bottom:16px">
  <div class="fund-header">
    <div>
      <h2>💰 Realized P&amp;L</h2>
      <div style="color:var(--muted);font-size:12px">{len(exits)} exit(s) · Total booked:
        <strong style="color:{pnl_col}">{sg}₹{abs(total_realized):,.0f} ({sg}{total_pct:.1f}%)</strong>
      </div>
    </div>
    <div style="font-size:22px;font-weight:700;color:{pnl_col}">{sg}₹{abs(total_realized):,.0f}</div>
  </div>
  <div class="tbl-wrap"><table>
    <thead><tr>
      <th>Symbol</th><th>Fund</th><th>Exit Date</th><th>Qty</th>
      <th>Entry ₹</th><th>Exit ₹</th><th>Invested</th>
      <th>Realized P&amp;L</th><th>Return %</th><th>Type</th><th>Note</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
  </table></div>
</div>"""


def _render_price_movement_card(
    sc_rows: list, mc_rows: list,
    snaps: dict, active_nse_to_db: dict,
) -> str:
    """Card showing today's intraday price movement for every position.

    Prev Close = last DB snapshot price (yesterday's EOD).
    CMP        = today's yfinance price (live / last traded).
    Today %    = (CMP − Prev Close) / Prev Close × 100.
    """
    sc_set = {r["sym"] for r in sc_rows}

    def _badge(sym):
        col = "#58a6ff" if sym in sc_set else "#f0a500"
        lbl = "SC"      if sym in sc_set else "MC"
        return col, lbl

    rows_data = []
    for r in sc_rows + mc_rows:
        sym    = r["sym"]
        db_sym = active_nse_to_db.get(sym, sym)
        snap   = snaps.get(db_sym, {})
        cmp    = r["price"]
        # Use the latest completed-session EOD close loaded from NSE bhavcopy.
        # The old reverse calculation from change_1d_pct was unsafe because
        # that percentage describes the snapshot date, not today's CMP.
        prev = snap.get("eod_prev_close")
        if prev is None:
            prev = float(snap.get("price") or cmp)
        prev = round(float(prev), 2)
        today_pct = round((cmp - prev) / prev * 100, 2) if prev else 0.0
        rows_data.append({
            "sym":       sym,
            "prev":      prev,
            "cmp":       cmp,
            "today_pct": today_pct,
            "pnl_pct":   r["pnl_pct"],
        })

    # Sort: biggest movers first by absolute move, while retaining direction.
    rows_data.sort(key=lambda x: abs(x["today_pct"]), reverse=True)

    eod_dates = {
        str((snaps.get(active_nse_to_db.get(r["sym"], r["sym"]), {}) or {}).get("eod_prev_close_date"))
        for r in sc_rows + mc_rows
        if (snaps.get(active_nse_to_db.get(r["sym"], r["sym"]), {}) or {}).get("eod_prev_close_date")
    }
    if len(eod_dates) == 1:
        eod_date_label = date.fromisoformat(next(iter(eod_dates))).strftime("%d-%b-%Y")
        reference_label = f"Prev Close ({eod_date_label} NSE EOD)"
    elif eod_dates:
        reference_label = "Prev Close (latest NSE EOD per stock)"
    else:
        reference_label = "Prev Close (latest available)"

    def _tr(d) -> str:
        col, lbl = _badge(d["sym"])
        tc   = "#3fb950" if d["today_pct"] >= 0 else "#f85149"
        sg   = "+" if d["today_pct"] >= 0 else ""
        pc   = "#3fb950" if d["pnl_pct"] >= 0 else "#f85149"
        psg  = "+" if d["pnl_pct"] >= 0 else ""
        bar_w = min(abs(d["today_pct"]) * 8, 60)  # 7.5% → 60px
        bar_c = "#3fb95030" if d["today_pct"] >= 0 else "#f8514930"
        return (
            f'<tr style="position:relative">'
            f'<td style="position:relative">'
            f'<div style="position:absolute;left:0;top:0;bottom:0;width:{bar_w:.0f}px;background:{bar_c}"></div>'
            f'<span class="clickable-sym" onclick="openCard(\'{d["sym"]}\')" style="position:relative">{d["sym"]}</span>'
            f'</td>'
            f'<td><span style="font-size:10px;font-weight:700;padding:1px 5px;border-radius:3px;'
            f'background:{col}22;color:{col};border:1px solid {col}44">{lbl}</span></td>'
            f'<td>₹{d["prev"]:,.2f}</td>'
            f'<td style="font-weight:600">₹{d["cmp"]:,.2f}</td>'
            f'<td style="color:{tc};font-weight:700">{sg}{d["today_pct"]:.2f}%</td>'
            f'<td style="color:{pc}">{psg}{d["pnl_pct"]:.1f}%</td>'
            f'</tr>'
        )

    rows_html = "".join(_tr(d) for d in rows_data)
    n_up   = sum(1 for d in rows_data if d["today_pct"] > 0)
    n_dn   = sum(1 for d in rows_data if d["today_pct"] < 0)
    n_flat = len(rows_data) - n_up - n_dn

    return f"""
<div class="fund-card" style="margin-bottom:16px">
  <div class="fund-header">
    <div>
      <h2>📈 Today's Price Movement</h2>
      <div style="color:var(--muted);font-size:12px">
        {reference_label} vs Portfolio Price · {n_up} up · {n_dn} down · {n_flat} flat
      </div>
    </div>
  </div>
  <div class="tbl-wrap"><table>
    <thead><tr>
      <th>Symbol</th><th>Fund</th>
      <th>Prev Close ₹</th><th>CMP ₹</th>
      <th>Today %</th><th>Cum P&amp;L %</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
  </table></div>
</div>"""


def fetch_volume_data(db_syms: list[str]) -> dict[str, int]:
    """Latest day's volume for each holding from market.equity_eod."""
    conn = pg()
    cur  = conn.cursor()
    vols: dict[str, int] = {}
    try:
        cur.execute("""
            SELECT DISTINCT ON (symbol) symbol, volume
            FROM market.equity_eod
            WHERE symbol = ANY(%s)
              AND series IN ('EQ','BE','BZ','SM','ST')
            ORDER BY symbol, trade_date DESC
        """, (db_syms,))
        for sym, vol in cur.fetchall():
            vols[sym] = int(vol or 0)
    except Exception as e:
        print(f"  [volume] fetch failed: {e}")
    finally:
        conn.close()
    print(f"  [volume] {len(vols)} symbols with volume data")
    return vols


def _render_portfolio_stats(
    sc_rows: list, mc_rows: list,
    snaps: dict, volumes: dict,
    active_nse_to_db: dict,
    n: int = 5,
) -> str:
    """4-panel portfolio stats: Top Gainers · Worst Performers · Fund Rules Status · RS Leaders."""
    all_rows = sc_rows + mc_rows
    if not all_rows:
        return ""

    sc_set = {r["sym"] for r in sc_rows}

    def _badge(sym):
        return ("#58a6ff", "SC") if sym in sc_set else ("#f0a500", "MC")

    def _snap(sym):
        return snaps.get(active_nse_to_db.get(sym, sym), {})

    def _rs(sym):
        return float(_snap(sym).get("relative_strength") or 0)

    def _vol_str(sym):
        v = volumes.get(active_nse_to_db.get(sym, sym), 0)
        if v >= 1_000_000: return f"{v/1e5:.1f}L"
        if v >= 100_000:   return f"{v/1e5:.2f}L"
        if v >= 1_000:     return f"{v/1000:.0f}K"
        return str(v)

    # ── Panels 1 & 2: Gainers / Losers ────────────────────────────────────
    ranked  = sorted(all_rows, key=lambda r: r["pnl_pct"], reverse=True)
    gainers = ranked[:n]
    losers  = ranked[-n:][::-1]

    def _gl_row(r) -> str:
        pct     = r["pnl_pct"]
        pnl     = r["pnl"]
        sg      = "+" if pnl >= 0 else ""
        col     = "#3fb950" if pct >= 0 else "#f85149"
        badge   = _badge(r["sym"])
        bar_w   = min(abs(pct) * 4, 80)
        bar_col = "#3fb95040" if pct >= 0 else "#f8514940"
        return (
            f'<div style="display:flex;align-items:center;gap:8px;padding:6px 0;'
            f'border-bottom:1px solid var(--border);position:relative">'
            f'<div style="position:absolute;left:0;top:0;bottom:0;width:{bar_w:.0f}px;'
            f'background:{bar_col};border-radius:3px"></div>'
            f'<span style="font-size:10px;font-weight:700;padding:1px 5px;border-radius:3px;'
            f'background:{badge[0]}22;color:{badge[0]};border:1px solid {badge[0]}44;z-index:1">{badge[1]}</span>'
            f'<span class="clickable-sym" onclick="openCard(\'{r["sym"]}\')" '
            f'style="font-weight:600;z-index:1;min-width:85px">{r["sym"]}</span>'
            f'<span style="color:{col};font-weight:700;z-index:1">{sg}{pct:.1f}%</span>'
            f'<span style="color:var(--muted);font-size:11px;z-index:1">{sg}₹{abs(pnl):,.0f}</span>'
            f'<span style="color:var(--muted);font-size:11px;margin-left:auto;z-index:1">₹{r["price"]:,.2f}</span>'
            f'</div>'
        )

    gainer_rows = "".join(_gl_row(r) for r in gainers)
    loser_rows  = "".join(_gl_row(r) for r in losers)

    # ── Panel 3: Fund Rules Status (Active / Not Active) ──────────────────
    def _compliance(r, is_sc: bool) -> list[str]:
        s = _snap(r["sym"])
        d = {
            "stage":      (s.get("stage") or "").replace("STAGE_", "S"),
            "rs":         float(s.get("relative_strength")   or 0),
            "tech":       float(s.get("technical_score")     or 0),
            "enh_fund":   float(s.get("enhanced_fund_score") or 0),
            "supertrend": s.get("supertrend_state", ""),
            "signal":     s.get("trading_signal", ""),
        }
        rules = SC_RULES if is_sc else MC_RULES
        return [name for name, fn in rules.items() if not fn(d)]

    comp_rows: list[tuple] = []
    for r in sc_rows:
        comp_rows.append((r, _compliance(r, True)))
    for r in mc_rows:
        comp_rows.append((r, _compliance(r, False)))
    # Non-compliant first
    comp_rows.sort(key=lambda x: (len(x[1]) == 0, x[0]["sym"]))

    def _comp_row(r, fails) -> str:
        badge      = _badge(r["sym"])
        is_active  = len(fails) == 0
        st_col     = "#3fb950" if is_active else "#f85149"
        st_txt     = "✅ ACTIVE" if is_active else f"⚠️ {len(fails)} fail"
        fail_html  = (
            f'<span style="color:var(--neg);font-size:10px;margin-left:4px">{", ".join(fails)}</span>'
            if fails else ""
        )
        return (
            f'<div style="display:flex;align-items:center;gap:8px;padding:5px 0;'
            f'border-bottom:1px solid var(--border)">'
            f'<span style="font-size:10px;font-weight:700;padding:1px 5px;border-radius:3px;'
            f'background:{badge[0]}22;color:{badge[0]};border:1px solid {badge[0]}44">{badge[1]}</span>'
            f'<span class="clickable-sym" onclick="openCard(\'{r["sym"]}\')" '
            f'style="font-weight:600;min-width:85px">{r["sym"]}</span>'
            f'<span style="color:{st_col};font-weight:700;font-size:11px">{st_txt}</span>'
            f'{fail_html}'
            f'</div>'
        )

    comp_html = "".join(_comp_row(r, f) for r, f in comp_rows)
    n_active  = sum(1 for _, f in comp_rows if not f)
    n_review  = len(comp_rows) - n_active

    # ── Panel 4: RS Leaders with price + volume ────────────────────────────
    rs_sorted = sorted(all_rows, key=lambda r: _rs(r["sym"]), reverse=True)

    def _rs_row(r) -> str:
        rs      = _rs(r["sym"])
        s       = _snap(r["sym"])
        # Keep this panel aligned with Today's Price Movement: calculate the
        # move from the canonical bhavcopy previous close, not the snapshot's
        # historical change_1d_pct.
        eod_prev = s.get("eod_prev_close")
        chg1d   = (
            (float(r["price"]) / float(eod_prev) - 1) * 100
            if eod_prev not in (None, 0) and r.get("price")
            else float(s.get("change_1d_pct") or 0)
        )
        badge   = _badge(r["sym"])
        rs_col  = "#3fb950" if rs >= 85 else ("#d29922" if rs >= 65 else "#f85149")
        chg_col = "#3fb950" if chg1d >= 0 else "#f85149"
        sg      = "+" if chg1d >= 0 else ""
        vol     = _vol_str(r["sym"])
        return (
            f'<div style="display:flex;align-items:center;gap:8px;padding:6px 0;'
            f'border-bottom:1px solid var(--border)">'
            f'<span style="font-size:10px;font-weight:700;padding:1px 5px;border-radius:3px;'
            f'background:{badge[0]}22;color:{badge[0]};border:1px solid {badge[0]}44">{badge[1]}</span>'
            f'<span class="clickable-sym" onclick="openCard(\'{r["sym"]}\')" '
            f'style="font-weight:600;min-width:80px">{r["sym"]}</span>'
            f'<span style="color:{rs_col};font-weight:700;min-width:38px">RS {rs:.0f}</span>'
            f'<span style="color:var(--muted);font-size:11px">₹{r["price"]:,.2f}</span>'
            f'<span style="color:{chg_col};font-size:11px;margin-left:4px">{sg}{chg1d:.2f}%</span>'
            f'<span style="color:var(--muted);font-size:11px;margin-left:auto">{vol}</span>'
            f'</div>'
        )

    rs_html = "".join(_rs_row(r) for r in rs_sorted)

    return f"""
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
    <div class="fund-card" style="margin:0;padding:14px 16px">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:10px">
        <span>🏆</span><h3 style="margin:0">Top Gainers</h3>
        <span style="color:var(--muted);font-size:11px;margin-left:4px">cumulative P&amp;L %</span>
      </div>
      {gainer_rows}
    </div>
    <div class="fund-card" style="margin:0;padding:14px 16px">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:10px">
        <span>📉</span><h3 style="margin:0">Worst Performers</h3>
        <span style="color:var(--muted);font-size:11px;margin-left:4px">cumulative P&amp;L %</span>
      </div>
      {loser_rows}
    </div>
    <div class="fund-card" style="margin:0;padding:14px 16px">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:10px">
        <span>✅</span><h3 style="margin:0">Fund Rules Status</h3>
        <span style="color:var(--muted);font-size:11px;margin-left:4px">{n_active} active · {n_review} review</span>
      </div>
      {comp_html}
    </div>
    <div class="fund-card" style="margin:0;padding:14px 16px">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:10px">
        <span>🎯</span><h3 style="margin:0">RS Leaders</h3>
        <span style="color:var(--muted);font-size:11px;margin-left:4px">price · 1d % · volume</span>
      </div>
      {rs_html}
    </div>
  </div>"""


def render_html(
    meta: dict,
    sc_holds: dict, sc_rows: list, sc_sum: dict,
    mc_holds: dict, mc_rows: list, mc_sum: dict,
    js_data: dict,
    sc_sym_set: set, mc_sym_set: set,
    sc_cands: list, mc_cands: list,
    generated_at: str,
    tech_alerts: list | None = None,
    db_alerts: dict | None = None,
    news_data: dict | None = None,
    active_nse_to_db: dict | None = None,
    history: dict | None = None,
    snaps: dict | None = None,
    volumes: dict | None = None,
    exits: list | None = None,
) -> str:
    tech_alerts      = tech_alerts      or []
    db_alerts        = db_alerts        or {"events": {}, "deals": {}, "insider": {}}
    news_data        = news_data        or {}
    active_nse_to_db = active_nse_to_db or {}
    history          = history          or {"funds": {}, "positions": {}}
    snaps            = snaps            or {}
    volumes          = volumes          or {}
    exits            = exits            or []

    # ── History-derived display helpers ──────────────────────────────────────
    def _fund_today(fund: str) -> dict:
        rows = history["funds"].get(fund, [])
        return rows[-1] if rows else {}

    sc_hist   = _fund_today("SC")
    mc_hist   = _fund_today("MC")
    comb_hist = _fund_today("COMBINED")

    def _spark(fund: str, width: int = 72, height: int = 22) -> str:
        vals = [r["pnl_pct"] for r in history["funds"].get(fund, [])]
        return _sparkline_svg(vals, width=width, height=height)

    sc_spark   = _spark("SC")
    mc_spark   = _spark("MC")
    comb_spark = _spark("COMBINED")

    def _delta_pill(val: float | None, prefix: str = "") -> str:
        if val is None or val == 0.0:
            return ""
        sg  = "+" if val >= 0 else ""
        cls = "pos" if val >= 0 else "neg"
        return f'<span class="delta-pill {cls}">{prefix}{sg}{val:.1f}%</span>'

    def _pos_day_pill(sym: str) -> str:
        rows = history["positions"].get(sym, [])
        if len(rows) >= 2:
            delta = round(rows[-1]["pnl_pct"] - rows[-2]["pnl_pct"], 1)
            return _delta_pill(delta)
        return ""

    # Per-position history injected into JS for panel sparklines
    pos_hist_js = "const POSITION_HISTORY = " + json.dumps({
        sym: [{"d": r["date"], "p": round(r["pnl_pct"], 2), "c": round(r["price"], 2)}
              for r in rows]
        for sym, rows in history["positions"].items()
    }, ensure_ascii=False) + ";"

    n_sc_dry = meta.get("slots_sc", 9) - len(sc_holds)
    n_mc_dry = meta.get("slots_mc", 15) - len(mc_holds)
    orders_tab_html      = render_orders_tab(sc_rows, mc_rows)
    risk_tab_html        = render_risk_tab(sc_rows, mc_rows)
    candidates_tab_html  = render_candidates_tab(sc_cands, mc_cands, n_sc_dry, n_mc_dry, meta=meta)
    actions_tab_html     = render_action_items_tab(tech_alerts)
    alerts_tab_html      = render_alerts_tab(tech_alerts, db_alerts, news_data, active_nse_to_db)
    winners_losers_html   = _render_portfolio_stats(sc_rows, mc_rows, snaps, volumes, active_nse_to_db)
    price_movement_html   = _render_price_movement_card(sc_rows, mc_rows, snaps, active_nse_to_db)
    realized_pnl_html     = _render_realized_pnl_card(exits)
    total_realized        = sum(float(e.get("realized_pnl", 0)) for e in exits)
    tot_inv = sc_sum["inv"] + mc_sum["inv"]
    tot_cur = sc_sum["cur"] + mc_sum["cur"]
    tot_pnl = sc_sum["pnl"] + mc_sum["pnl"]
    tot_pct = (tot_pnl / tot_inv * 100) if tot_inv else 0

    s  = lambda x: "+" if x >= 0 else ""
    c  = lambda x: "pos" if x >= 0 else "neg"
    n_sc = len(sc_holds)
    n_mc = len(mc_holds)
    summary_banner_html   = _render_fund_summary_banner(
        sc_sum, mc_sum, exits, tech_alerts,
        n_sc, n_mc, sc_rows, mc_rows, generated_at,
    )
    slots_sc = meta.get("slots_sc", 9)
    slots_mc = meta.get("slots_mc", 15)
    budget_sc = int(meta.get("budget_sc", 200_000))
    budget_mc = int(meta.get("budget_mc", 200_000))
    rules_html = (FUND_RULES_HTML
                  .replace("{SC_BUDGET_LAKH}", f"{budget_sc / 100_000:g}")
                  .replace("{SC_SLOT_COUNT}", str(slots_sc))
                  .replace("{SC_SLOT_SIZE}", f"₹{budget_sc / max(slots_sc, 1):,.0f}".replace("₹", ""))
                  .replace("{MC_BUDGET_LAKH}", f"{budget_mc / 100_000:g}")
                  .replace("{MC_SLOT_COUNT}", str(slots_mc))
                  .replace("{MC_SLOT_SIZE}", f"₹{budget_mc / max(slots_mc, 1):,.0f}".replace("₹", "")))

    fund_membership = {sym: "SC" for sym in sc_sym_set}
    fund_membership.update({sym: "MC" for sym in mc_sym_set})

    _ZONE_STYLE = {
        "IDEAL":    ("background:#1a3a1a;color:#3fb950;border:1px solid #3fb950", "✅ IDEAL"),
        "AT_PIVOT": ("background:#1a2a3a;color:#58a6ff;border:1px solid #58a6ff", "🎯 AT PIVOT"),
        "BASING":   ("background:#2a2a1a;color:#d29922;border:1px solid #d29922", "⏳ BASING"),
        "EXTENDED": ("background:#3a1a1a;color:#f85149;border:1px solid #f85149", "⛔ EXTENDED"),
    }

    def _entry_zone_badge(sym: str) -> str:
        """RSI-based entry zone badge for existing holdings."""
        db_sym = active_nse_to_db.get(sym, sym)
        rsi    = float((snaps.get(db_sym) or {}).get("rsi") or 0)
        if rsi <= 0:
            return ""
        if rsi > 75:
            zone = "EXTENDED"
        elif rsi > 68:
            zone = "AT_PIVOT"
        elif rsi >= 45:
            zone = "IDEAL"
        else:
            zone = "BASING"
        st, lbl = _ZONE_STYLE[zone]
        return (f'<span style="display:inline-block;font-size:9px;font-weight:700;'
                f'padding:1px 5px;border-radius:3px;white-space:nowrap;margin-left:4px;{st}">{lbl}</span>')

    def sym_span(sym):
        return (f'<span class="clickable-sym" onclick="openCard(\'{sym}\')">{sym}</span>'
                f'{_entry_zone_badge(sym)}')

    def pnl_cell(r):
        cl  = "pos" if r["pnl"] >= 0 else "neg"
        sg  = "+" if r["pnl"] >= 0 else ""
        tag = ' <span class="new-tag">NEW</span>' if r["new"] else ""
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

    sc_rows_html = "\n".join(hold_row(r) for r in sc_rows)
    mc_rows_html = "\n".join(hold_row(r) for r in mc_rows)
    js_stock_data = "const STOCK_DATA = " + json.dumps(js_data, indent=2, ensure_ascii=False) + ";"
    js_membership  = "const FUND_MEMBERSHIP = " + json.dumps(fund_membership) + ";"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Fund Dashboard — Aug 2026</title>
<style>{CSS}</style>
</head>
<body>
<div style="padding:20px 20px 0">
  <h1>📊 Aug 2026 Fund Dashboard</h1>
  <div style="color:var(--muted);font-size:12px;margin-top:4px">
    As of {TODAY} · Inception 2026-08-15 · {n_sc} SC + {n_mc} MC positions · Generated {generated_at}
  </div>
</div>
{summary_banner_html}
<div class="tabs">
  <div class="tab active" onclick="switchTab('tab-actions')">✅ Action Items{f'<span class="alert-badge">{len([a for a in tech_alerts if a["severity"] in ("CRITICAL","WARNING")])}</span>' if tech_alerts else ''}</div>
  <div class="tab" onclick="switchTab('tab-pl')">📊 Fund P&amp;L</div>
  <div class="tab" onclick="switchTab('tab-orders')">📒 Orders</div>
  <div class="tab" onclick="switchTab('tab-risk')">⚠️ Risk</div>
  <div class="tab" onclick="switchTab('tab-candidates')">🎯 Next Candidates</div>
  <div class="tab" onclick="switchTab('tab-rules')">📋 Fund Rules</div>
  <div class="tab" onclick="switchTab('tab-alerts')">🚨 Alerts{f'<span class="alert-badge">{len([a for a in tech_alerts if a["severity"] in ("CRITICAL","WARNING")])}</span>' if tech_alerts else ''}</div>
  {f'<div class="tab" onclick="switchTab(\'tab-exits\')">💰 Exits<span class="alert-badge" style="background:#3fb950">{len(exits)}</span></div>' if exits else ''}
</div>

{actions_tab_html}

<div id="tab-pl" class="tab-content">
  <div class="summary-bar">
    <div class="stat-box">
      <div class="label">Combined Invested</div>
      <div class="value">₹{tot_inv:,.0f}</div>
      <div class="sub">SC + MC · {n_sc+n_mc} positions</div>
    </div>
    <div class="stat-box">
      <div class="label">Combined Current</div>
      <div class="value">₹{tot_cur:,.0f}</div>
      <div class="sub">As of {TODAY}</div>
    </div>
    <div class="stat-box">
      <div class="label">Combined P&amp;L</div>
      <div class="spark-stat-box">
        <div>
          <div class="value {c(tot_pnl)}">{s(tot_pnl)}₹{tot_pnl:,.0f}</div>
          <div class="sub {c(tot_pnl)}">{s(tot_pct)}{tot_pct:.2f}%
            {comb_spark and f'&nbsp;{_delta_pill(comb_hist.get("day_pct"), "1d:")} {_delta_pill(comb_hist.get("wow_pct"), "WoW:")}' or ''}
          </div>
        </div>
        <div class="spark-wrap">{comb_spark}</div>
      </div>
    </div>
    <div class="stat-box">
      <div class="label">SC ({n_sc}/{slots_sc} slots)</div>
      <div class="spark-stat-box">
        <div>
          <div class="value {c(sc_sum['pnl'])}">{s(sc_sum['pnl'])}₹{sc_sum['pnl']:,.0f}</div>
          <div class="sub {c(sc_sum['pct'])}">{s(sc_sum['pct'])}{sc_sum['pct']:.1f}% · {sc_sum['W']}W {sc_sum['L']}L
            {sc_spark and f'&nbsp;{_delta_pill(sc_hist.get("day_pct"), "1d:")} {_delta_pill(sc_hist.get("wow_pct"), "WoW:")}' or ''}
          </div>
        </div>
        <div class="spark-wrap">{sc_spark}</div>
      </div>
    </div>
    <div class="stat-box">
      <div class="label">MC ({n_mc}/{slots_mc} slots)</div>
      <div class="spark-stat-box">
        <div>
          <div class="value {c(mc_sum['pnl'])}">{s(mc_sum['pnl'])}₹{mc_sum['pnl']:,.0f}</div>
          <div class="sub {c(mc_sum['pct'])}">{s(mc_sum['pct'])}{mc_sum['pct']:.1f}% · {mc_sum['W']}W {mc_sum['L']}L
            {mc_spark and f'&nbsp;{_delta_pill(mc_hist.get("day_pct"), "1d:")} {_delta_pill(mc_hist.get("wow_pct"), "WoW:")}' or ''}
          </div>
        </div>
        <div class="spark-wrap">{mc_spark}</div>
      </div>
    </div>
    {f'''<div class="stat-box">
      <div class="label">Realized P&amp;L</div>
      <div class="value {("pos" if total_realized >= 0 else "neg")}">{("+" if total_realized >= 0 else "")}₹{abs(total_realized):,.0f}</div>
      <div class="sub">{len(exits)} exit(s) booked</div>
    </div>''' if exits else ''}
  </div>

{winners_losers_html}
{price_movement_html}
{realized_pnl_html}
  <div class="fund-card">
    <div class="fund-header">
      <div>
        <h2>🔵 Aug Small-Cap Fund</h2>
        <div style="color:var(--muted);font-size:12px">{n_sc}/{slots_sc} slots · {slots_sc-n_sc} dry powder · Budget ₹{meta.get('budget_sc',200000):,} · Stop −7%</div>
      </div>
      <div class="fund-meta">
        <div class="m"><span class="k">Invested</span><br>₹{sc_sum['inv']:,.0f}</div>
        <div class="m"><span class="k">Current</span><br>₹{sc_sum['cur']:,.0f}</div>
        <div class="m"><span class="k">P&amp;L</span><br><span class="{c(sc_sum['pnl'])}">{s(sc_sum['pnl'])}₹{sc_sum['pnl']:,.0f} ({s(sc_sum['pct'])}{sc_sum['pct']:.1f}%)</span></div>
        <div class="m"><span class="k">W/L</span><br>{sc_sum['W']}W {sc_sum['L']}L</div>
      </div>
    </div>
    <div class="tbl-wrap"><table>
      <thead><tr>
        <th>Symbol</th><th>Entry ₹</th><th>CMP ₹</th><th>Qty</th>
        <th>Invested</th><th>Current</th><th>P&amp;L</th>
        <th>Stop ₹</th><th>Buy Date</th><th>Sell Date</th><th>Days</th>
      </tr></thead>
      <tbody>{sc_rows_html}</tbody>
    </table></div>
  </div>

  <div class="fund-card">
    <div class="fund-header">
      <div>
        <h2>🟡 Aug Mid-Cap Fund</h2>
        <div style="color:var(--muted);font-size:12px">{n_mc}/{slots_mc} slots · {slots_mc-n_mc} dry powder · Budget ₹{meta.get('budget_mc',200000):,} · Stop −6%</div>
      </div>
      <div class="fund-meta">
        <div class="m"><span class="k">Invested</span><br>₹{mc_sum['inv']:,.0f}</div>
        <div class="m"><span class="k">Current</span><br>₹{mc_sum['cur']:,.0f}</div>
        <div class="m"><span class="k">P&amp;L</span><br><span class="{c(mc_sum['pnl'])}">{s(mc_sum['pnl'])}₹{mc_sum['pnl']:,.0f} ({s(mc_sum['pct'])}{mc_sum['pct']:.1f}%)</span></div>
        <div class="m"><span class="k">W/L</span><br>{mc_sum['W']}W {mc_sum['L']}L</div>
      </div>
    </div>
    <div class="tbl-wrap"><table>
      <thead><tr>
        <th>Symbol</th><th>Entry ₹</th><th>CMP ₹</th><th>Qty</th>
        <th>Invested</th><th>Current</th><th>P&amp;L</th>
        <th>Stop ₹</th><th>Buy Date</th><th>Sell Date</th><th>Days</th>
      </tr></thead>
      <tbody>{mc_rows_html}</tbody>
    </table></div>
  </div>
</div>

<div id="tab-orders" class="tab-content">{orders_tab_html}</div>
<div id="tab-risk" class="tab-content">{risk_tab_html}</div>
<div id="tab-candidates" class="tab-content">{candidates_tab_html}</div>
<div id="tab-rules" class="tab-content">{rules_html}</div>
<div id="tab-alerts" class="tab-content">{alerts_tab_html}</div>
{f'<div id="tab-exits" class="tab-content">{realized_pnl_html}</div>' if exits else ''}

<div id="overlay" onclick="closeCard()"></div>
<div id="stock-panel">
  <div class="panel-header">
    <div>
      <h2 id="panel-title">Stock Detail</h2>
      <div id="panel-subtitle" style="color:var(--muted);font-size:12px;margin-top:4px"></div>
    </div>
    <button class="panel-close" onclick="closeCard()">✕</button>
  </div>
  <div class="panel-body" id="panel-body"></div>
</div>

<div style="margin:24px 20px 32px;padding:14px 18px;background:var(--card);border:1px solid var(--border);border-radius:8px;color:var(--muted);font-size:11px;line-height:1.55">
  <strong style="color:var(--text)">Research and AI disclaimer:</strong> This dashboard is an AI-assisted research and education tool, not personalised investment advice and not a recommendation, solicitation or offer to buy or sell securities. Agent Adda is not a SEBI-registered Investment Adviser, Research Analyst, broker or portfolio manager. AI summaries and market data may be delayed, incomplete or inaccurate; verify material figures against company filings and exchange disclosures. Securities markets involve risk, including possible loss of capital. Past performance is not indicative of future results, and no assured or guaranteed return is promised. Consult a SEBI-registered professional for advice suited to your circumstances.
</div>

<script>
{js_stock_data}
{js_membership}
{pos_hist_js}
{JS_TEMPLATE}
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Refresh Aug Fund Dashboard")
    parser.add_argument("--no-open",      action="store_true", help="Don't open browser")
    parser.add_argument("--skip-prices",  action="store_true", help="Use cached prices")
    parser.add_argument("--prices-only",  action="store_true", help="Only fetch prices then regenerate")
    parser.add_argument("--skip-news",    action="store_true", help="Skip yfinance news fetch")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  Aug Fund Dashboard Refresh — {TODAY}")
    print(f"{'='*60}\n")

    # 1. Load holdings
    print("[1/6] Loading holdings from data/fund_holdings.json ...")
    meta, sc_holds, mc_holds = load_holdings()
    all_nse_syms = list(sc_holds.keys()) + list(mc_holds.keys())
    print(f"  SC: {len(sc_holds)} positions, MC: {len(mc_holds)} positions")

    # Build nse→db map for active holdings only
    active_nse_to_db = {s: NSE_TO_DB.get(s, s) for s in all_nse_syms}
    active_db_syms   = list(set(active_nse_to_db.values()))

    # 2. Fetch live prices
    print("\n[2/6] Fetching live prices ...")
    prices = fetch_live_prices(all_nse_syms, skip=args.skip_prices)

    # 2b. Verify PostgreSQL is reachable (dashboard requires DB)
    try:
        _c = pg()
        _c.close()
    except Exception as exc:
        print(f"\n[pg] PostgreSQL is required but unavailable: {exc}")
        print("     Start it via `./postgres/start_pg.sh start` (or `python tools/command_center.py --run pg_start`).")
        raise SystemExit(2)

    # 3. Fetch DB data
    print("\n[3/6] Querying database ...")
    snaps, funds, qtrs = fetch_db_data(active_db_syms)

    # 3b. Fetch volume data
    print("\n[3b] Fetching volume data ...")
    volumes = fetch_volume_data(active_db_syms)

    # 4. Build JS stock data
    print("\n[4/6] Building stock detail data ...")
    js_data = build_js_data(active_nse_to_db, snaps, funds, qtrs)

    # 5. Compute P&L rows
    print("\n[5/6] Computing P&L ...")
    today_str = str(TODAY)
    sc_rows = compute_rows(sc_holds, prices, sl_pct=0.07, entry_date_today=today_str)
    mc_rows = compute_rows(mc_holds, prices, sl_pct=0.06, entry_date_today=today_str)

    # The detail drawer, rules card, RS card, and P&L tables must all point to
    # the same portfolio position values. Same-day fills use the logged entry
    # price by design, so expose that explicitly instead of implying a live
    # quote that was not used for P&L.
    for fund_name, rows in (("SC", sc_rows), ("MC", mc_rows)):
        for row in rows:
            js_data.setdefault(row["sym"], {})["position"] = {
                "fund": fund_name,
                "entry": row["entry"],
                "price": row["price"],
                "qty": row["qty"],
                "invested": row["invested"],
                "current": row["current"],
                "pnl": row["pnl"],
                "pnl_pct": row["pnl_pct"],
                "sl": row["sl"],
                "buy_date": row["buy_date"],
            }
    sc_sum  = fund_summary(sc_rows)
    mc_sum  = fund_summary(mc_rows)

    sign = lambda x: "+" if x >= 0 else ""
    print(f"  SC: invested=₹{sc_sum['inv']:,.0f}  P&L={sign(sc_sum['pnl'])}₹{sc_sum['pnl']:,.0f} ({sign(sc_sum['pct'])}{sc_sum['pct']:.1f}%)")
    print(f"  MC: invested=₹{mc_sum['inv']:,.0f}  P&L={sign(mc_sum['pnl'])}₹{mc_sum['pnl']:,.0f} ({sign(mc_sum['pct'])}{mc_sum['pct']:.1f}%)")

    # 5a. Persist to PostgreSQL
    print("\n[5a] Persisting to PostgreSQL ...")
    persist_to_pg(sc_rows, mc_rows, sc_sum, mc_sum, snaps, active_nse_to_db)

    # 5b. Fetch history for trend display
    print("\n[5b-hist] Loading historical trends ...")
    history = fetch_history_for_dashboard(all_nse_syms, lookback_days=30)

    # Check for stop-loss breaches
    sc_sl_alert = [r["sym"] for r in sc_rows if r["pnl_pct"] <= -8.0]
    mc_sl_alert = [r["sym"] for r in mc_rows if r["pnl_pct"] <= -7.0]
    if sc_sl_alert:
        print(f"\n  ⚠️  SC STOP LOSS BREACH: {', '.join(sc_sl_alert)}")
    if mc_sl_alert:
        print(f"  ⚠️  MC STOP LOSS BREACH: {', '.join(mc_sl_alert)}")

    # 5c. Fetch next candidates
    print("\n[5c] Fetching next candidates ...")
    # Do not immediately re-surface a symbol that was already exited. A
    # deliberate re-entry can be added later as a new broker fill, but the
    # candidate queue should not silently turn a completed exit into a buy.
    exits = load_exits()
    excluded_db = list(active_nse_to_db.values()) + [
        NSE_TO_DB.get(str(e.get("symbol", "")).upper(), str(e.get("symbol", "")).upper())
        for e in exits
        if e.get("symbol")
    ]
    sc_cands, mc_cands = fetch_candidates(list(dict.fromkeys(excluded_db)), n=20)

    # 5d. Fetch DB alerts (corporate events, bulk/block deals, insider)
    print("\n[5d] Fetching DB alerts ...")
    db_alerts = fetch_alerts_db(active_db_syms)

    # 5d. Fetch news via yfinance (parallel)
    if args.skip_news:
        news_data = {}
        news_summaries = {sym: {"summary": None, "sentiment": "NEUTRAL", "action": None, "articles": []}
                          for sym in all_nse_syms}
        print("\n[5d] Skipping news fetch (--skip-news)")
    else:
        print("\n[5d] Fetching news from yfinance ...")
        news_data = fetch_news_yf(all_nse_syms)

        # 5f. LLM summarization (Claude Haiku) — news + events + bulk deals per stock
        print("\n[5f] Summarizing news with LLM ...")
        news_summaries = summarize_news_llm(news_data, db_alerts, active_nse_to_db)

    # 5e. Realized exits were loaded before candidate selection so completed
    # exits are excluded from the candidate queue.
    print(f"\n[5e] Loaded {len(exits)} realized exit(s) from fund_exits.json")

    # 5f. Generate technical alerts
    print("\n[5f] Generating technical alerts ...")
    tech_alerts = generate_technical_alerts(
        sc_holds, mc_holds, prices, snaps, qtrs, active_nse_to_db
    )
    n_crit = len([a for a in tech_alerts if a["severity"] == "CRITICAL"])
    n_warn = len([a for a in tech_alerts if a["severity"] == "WARNING"])
    print(f"  {n_crit} critical, {n_warn} warnings, {len(tech_alerts)-n_crit-n_warn} positive")

    # 6. Render HTML
    print("\n[6/6] Rendering dashboard HTML ...")
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = render_html(
        meta=meta,
        sc_holds=sc_holds, sc_rows=sc_rows, sc_sum=sc_sum,
        mc_holds=mc_holds, mc_rows=mc_rows, mc_sum=mc_sum,
        js_data=js_data,
        sc_sym_set=set(sc_holds.keys()),
        mc_sym_set=set(mc_holds.keys()),
        sc_cands=sc_cands, mc_cands=mc_cands,
        generated_at=generated_at,
        tech_alerts=tech_alerts,
        db_alerts=db_alerts,
        news_data=news_summaries,
        active_nse_to_db=active_nse_to_db,
        history=history,
        snaps=snaps,
        volumes=volumes,
        exits=exits,
    )
    DASHBOARD_OUT.write_text(html)
    size_kb = DASHBOARD_OUT.stat().st_size // 1024
    print(f"  Written: {DASHBOARD_OUT}  ({size_kb} KB)")

    # Open browser
    if not args.no_open:
        subprocess.run(["open", str(DASHBOARD_OUT)])
        print(f"  Opened in browser.")

    print(f"\n✅  Done — {generated_at}")
    print(f"   file://{DASHBOARD_OUT}\n")


if __name__ == "__main__":
    main()
