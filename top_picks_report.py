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

ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"
TOP_PICKS_DIR = REPORTS_DIR / "top_picks"
LATEST_DIR = REPORTS_DIR / "latest"
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
MAX_PICKS = 10


# ─────────────────────────────────────────────────────────────────────────────
# Data access
# ─────────────────────────────────────────────────────────────────────────────
def _connect():
    return psycopg2.connect(dbname="nse_market")


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
# Pick selection — merges sector-rotation candidates + stage-2 leaders
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class PickRationale:
    symbol: str
    sector: str
    source: str   # "sector_rot", "stage2", "dual"
    sector_rot_score: float | None
    stage2_score: float | None
    rationale: str


def _load_sector_candidates(conn, snap_date: str) -> list[dict]:
    """Pull sector-rotation candidates from the snapshot (richer than the MD)."""
    return _fetchall(conn, """
        SELECT symbol, sector, price, technical_score, relative_strength,
               enhanced_fund_score, investment_score, trading_signal, stance, stage
        FROM scores.stage_snapshots
        WHERE snapshot_date=%s
          AND sector IN (
            'Pharma & Healthcare','Capital Markets','Defence & Aerospace',
            'Metals & Mining','Energy - Power','Capital Goods & Industrials',
            'Commodities'
          )
        ORDER BY investment_score DESC NULLS LAST
        LIMIT 50
    """, (snap_date,))


def _load_stage2_leaders(conn, snap_date: str) -> list[dict]:
    return _fetchall(conn, """
        SELECT symbol, sector, price, technical_score, relative_strength,
               enhanced_fund_score, investment_score, trading_signal, stance, stage
        FROM scores.stage_snapshots
        WHERE snapshot_date=%s AND stage='STAGE_2'
        ORDER BY investment_score DESC NULLS LAST
        LIMIT 30
    """, (snap_date,))


def build_pick_list(conn, snap_date: str, n: int = MAX_PICKS) -> list[PickRationale]:
    sec = _load_sector_candidates(conn, snap_date)
    st2 = _load_stage2_leaders(conn, snap_date)

    sec_top_syms = {r["symbol"]: r for r in sec[:15]}
    st2_top_syms = {r["symbol"]: r for r in st2[:15]}
    dual = set(sec_top_syms) & set(st2_top_syms)

    picks: list[PickRationale] = []
    seen: set[str] = set()

    # Phase 1: dual-confirmed (highest conviction)
    for sym in sorted(dual, key=lambda s: -(float(sec_top_syms[s].get("investment_score") or 0))):
        if len(picks) >= n: break
        r = sec_top_syms[sym]
        picks.append(PickRationale(
            symbol=sym, sector=r["sector"], source="dual",
            sector_rot_score=float(r["investment_score"] or 0),
            stage2_score=float(st2_top_syms[sym]["investment_score"] or 0),
            rationale=f"Dual-confirmed: sector-rotation leader AND stage-2 momentum (inv.score {r['investment_score']})"
        ))
        seen.add(sym)

    # Phase 2: top sector-rotation only
    for r in sec:
        if len(picks) >= n: break
        sym = r["symbol"]
        if sym in seen: continue
        picks.append(PickRationale(
            symbol=sym, sector=r["sector"], source="sector_rot",
            sector_rot_score=float(r["investment_score"] or 0),
            stage2_score=None,
            rationale=f"Top of leading sector ({r['sector']}); inv.score {r['investment_score']}, RS {r['relative_strength']}%"
        ))
        seen.add(sym)

    # Phase 3: top stage-2 only
    for r in st2:
        if len(picks) >= n: break
        sym = r["symbol"]
        if sym in seen: continue
        picks.append(PickRationale(
            symbol=sym, sector=r["sector"], source="stage2",
            sector_rot_score=None,
            stage2_score=float(r["investment_score"] or 0),
            rationale=f"Stage-2 momentum leader; inv.score {r['investment_score']}, fund {r['enhanced_fund_score']}"
        ))
        seen.add(sym)

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
               pat, eps, dividend_payout_pct
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


def get_corporate_events(conn, sym: str, days: int = 90) -> list[dict]:
    return _fetchall(conn, """
        SELECT event_date, event_type, purpose_raw, detail
        FROM signals.corporate_events
        WHERE symbol=%s AND event_date >= (CURRENT_DATE - INTERVAL '%s days')
        ORDER BY event_date DESC LIMIT 10
    """, (sym, days))


def get_insider_activity(conn, sym: str, days: int = 90) -> list[dict]:
    return _fetchall(conn, """
        SELECT alert_date, alert_type, entity, value_cr, category, insider_score
        FROM signals.insider_alerts
        WHERE symbol=%s AND alert_date >= (CURRENT_DATE - INTERVAL '%s days')
        ORDER BY alert_date DESC LIMIT 10
    """, (sym, days))


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

    return a


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
    return fund


# ─────────────────────────────────────────────────────────────────────────────
# LLM narrative generation
# ─────────────────────────────────────────────────────────────────────────────
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
        "(10) latest quarterly result deltas vs trend.",
        "",
        "Return STRICT JSON (no markdown fences, no commentary):",
        "{",
        '  "per_stock": {',
        '    "SYMBOL": {',
        '      "thesis": "3-4 sentence multi-dimensional bull case citing concrete numbers (RSI x, EMA stack, RS y%, revenue YoY z%, PAT CAGR w%, ROCE p%, etc.)",',
        '      "key_catalysts": ["catalyst 1 with metric", "catalyst 2", "catalyst 3"],',
        '      "fundamental_view": "2-3 sentences synthesising P&L + BS + CF: cite latest quarter revenue/PAT growth, OPM trend in bps, debt direction, OCF/PAT ratio, ROCE, EPS CAGR",',
        '      "technical_view": "2 sentences: trend stack, RS, momentum (RSI), distance from 52w high, volume",',
        '      "sector_view": "1-2 sentences linking the stock to its sector strength and peer ranking",',
        '      "valuation_note": "1 sentence flagging valuation comfort or stretch — use EPS, growth, sector context (qualitative is fine if no PE)",',
        '      "key_risks": ["risk 1 with metric", "risk 2", "risk 3"],',
        '      "action": "1 sentence: entry zone or wait-for-pullback level, invalidation, stop guidance",',
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
            "sector_view": sec_text,
            "valuation_note": "Quantitative valuation not in dossier — defer to qualitative read.",
            "key_risks": risk or ["No quantitative red flag in dossier"],
            "action": action,
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

    # ---- Pass 1: per-stock deep analysis ----
    try:
        print("   🧠 LLM pass 1/2: per-stock deep analysis…")
        deep_prompt = _build_deep_llm_prompt(stocks, macro_context, snap_date)
        deep_result = _llm_call(
            api_key=api_key,
            model=DEFAULT_MODEL,
            system_msg=_DEEP_SYSTEM_MSG,
            user_msg=deep_prompt,
            max_tokens=16384,
            timeout=250,
        )
        if "per_stock" not in deep_result or not isinstance(deep_result["per_stock"], dict):
            raise ValueError("Deep-analysis response missing per_stock dict")
        per_stock = deep_result["per_stock"]
        # Fill any missing symbol from rule-based
        for sym in [s["symbol"] for s in stocks]:
            if sym not in per_stock:
                per_stock[sym] = rule_fallback["per_stock"][sym]
    except Exception as exc:
        print(f"   ⚠️  Deep-analysis LLM failed: {exc} — using rule-based for all stocks")
        return rule_fallback

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
    out.append("| # | Symbol | Sector | Price | Stage | Inv.Score | RS% | Fund | Stance | Source |\n")
    out.append("|---|---|---|---:|---|---:|---:|---:|---|---|\n")
    for i, (p, e) in enumerate(zip(picks, enriched), 1):
        snap = e["snapshot"] or {}
        out.append(
            f"| {i} | **{p.symbol}** | {p.sector} | {_nz(snap.get('price'))} | "
            f"{snap.get('stage','—')} | {_nz(snap.get('investment_score'))} | "
            f"{_pct(snap.get('relative_strength'))} | {_nz(snap.get('enhanced_fund_score'))} | "
            f"{snap.get('stance','—')} | {p.source} |\n"
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
    if fund:
        p_ = fund.get("_parsed") or {}
        def _add(label, v):
            if v not in (None, ""):
                rows_fund.append((label, v))
        _add("Piotroski F-score", f"{fund['piotroski_score']:.0f} / 9" if fund.get('piotroski_score') is not None else None)
        _add("Altman Z", _nz(fund.get('altman_z_score')) if fund.get('altman_z_score') is not None else None)
        _add("Beneish M", _nz(fund.get('beneish_m_score')) if fund.get('beneish_m_score') is not None else None)
        _add("Forensic risk", fund.get('forensic_risk'))
        roe, roce = fund.get('roe'), fund.get('roce')
        if roe is not None or roce is not None:
            _add("ROE / ROCE", f"{_pct(roe) if roe is not None else '—'} / {_pct(roce) if roce is not None else '—'}")
        _add("NPM", _pct(p_.get('npm_pct')) if p_.get('npm_pct') is not None else None)
        _add("EPS", _nz(p_.get('eps')) if p_.get('eps') is not None else None)
        if fund.get('debt_to_equity') is not None:
            _add("Debt / Equity", _nz(fund.get('debt_to_equity')))
        _add("Promoter holding", _pct(fund.get('promoter_holding')) if fund.get('promoter_holding') is not None else None)

    # Enhanced fundamental sub-scores
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

    # Corporate events + insider activity
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
    news_html = (
        f"<ul class='rotation-context-list' style='font-size:12px'>{''.join(news_bits)}</ul>"
        if news_bits else
        "<p style='color:#64748b;font-size:12px;margin:0'>No corporate events or insider transactions in last 90 days.</p>"
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

    return f"""
<div class="card" id="pick-{idx}" style="border-left:4px solid #1e3a5f">
  <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px">
    <h2 style="margin:0;font-size:1.2rem;color:#1e3a5f">{idx}. {h(p.symbol)}</h2>
    <span class="mbadge mbadge-data">{h(p.sector)}</span>
    {src_badge}
    {conv_badge}
  </div>
  <div class="metrics-row" style="margin-bottom:14px">{headline_html}</div>

  <div class="overview-grid">
    <div class="summary-card" style="background:#fafbfd">
      <h3>Investment Thesis</h3>
      <p style="margin-bottom:8px">{h(narr.get('thesis', '—'))}</p>

      <h3 style="color:#1d4ed8;margin-top:10px">Technical View</h3>
      <p style="margin-bottom:8px;font-size:13px">{h(narr.get('technical_view', '—'))}</p>

      <h3 style="color:#0f766e;margin-top:10px">Fundamental View</h3>
      <p style="margin-bottom:8px;font-size:13px">{h(narr.get('fundamental_view', '—'))}</p>

      <h3 style="color:#7c3aed;margin-top:10px">Sector View</h3>
      <p style="margin-bottom:8px;font-size:13px">{h(narr.get('sector_view', '—'))}</p>

      <h3 style="color:#d97706;margin-top:10px">Valuation</h3>
      <p style="margin-bottom:8px;font-size:13px">{h(narr.get('valuation_note', '—'))}</p>

      <h3 style="color:#16a34a;margin-top:10px">Key Catalysts</h3>
      {_list_or_text(narr.get('key_catalysts'))}

      <h3 style="color:#b91c1c;margin-top:10px">Key Risks</h3>
      {_list_or_text(narr.get('key_risks'))}

      <h3 style="color:#047857;margin-top:10px">Action</h3>
      <p>{h(narr.get('action', '—'))}</p>

      {f'<p style="margin-top:8px;font-size:11px;color:#64748b"><em>Conviction:</em> <strong style="color:{conv_color}">{h(conv)}</strong> — {h(narr.get("conviction_rationale", ""))}</p>' if conv else ''}
      <p style="margin-top:6px;font-size:11px;color:#64748b"><em>Why selected:</em> {h(p.rationale)}</p>
    </div>
    <div class="summary-card">
      <h3>Snapshot</h3>
      <ul class="rotation-context-list">
        <li>Stage: <strong>{h(snap.get('stage') or '—')}</strong> (score {_nz(snap.get('stage_score'))})</li>
        <li>Trading signal: <strong>{h(snap.get('trading_signal') or '—')}</strong></li>
        <li>Supertrend: {h(snap.get('supertrend_state') or '—')} around ₹{_nz(snap.get('supertrend_value'))}</li>
        <li>Tech score {_nz(snap.get('technical_score'))} / Fund score {_nz(snap.get('enhanced_fund_score'))}</li>
        <li>1D {_pct(snap.get('change_1d_pct'))} · 1W {_pct(snap.get('change_1w_pct'))} · 1M {_pct(snap.get('change_1m_pct'))}</li>
      </ul>
      <h3 style="margin-top:12px">Sector Context</h3>
      {sector_html or '<p style="color:#64748b;font-size:12px;margin:0">No sector aggregate available.</p>'}
    </div>
  </div>

  <div class="overview-grid" style="margin-top:12px">
    <div class="summary-card">
      <h3>Technicals</h3>
      {_table(rows_tech) if rows_tech else f'<p style="color:#b45309">{h(tech.get("error", "no data"))}</p>'}
    </div>
    <div class="summary-card">
      <h3>Fundamental Scores</h3>
      {_table(rows_fund) if rows_fund else '<p style="color:#64748b">No fundamentals row in scores.fundamentals.</p>'}
      {('<h4 style="margin-top:10px;color:#475569">Sub-Scores</h4>' + _table(rows_subscore)) if rows_subscore else ''}
    </div>
  </div>

  <div class="overview-grid" style="margin-top:12px">
    <div class="summary-card">
      <h3>Latest Quarterly Results</h3>
      {qtr_html or '<p style="color:#64748b">No quarterly data.</p>'}
    </div>
    <div class="summary-card">
      <h3>5-Year Annual Trajectory</h3>
      {ann_html or '<p style="color:#64748b">No annual data.</p>'}
    </div>
  </div>

  <div class="overview-grid" style="margin-top:12px">
    <div class="summary-card">
      <h3>Balance Sheet (3Y)</h3>
      {bs_html or '<p style="color:#64748b">No BS data.</p>'}
    </div>
    <div class="summary-card">
      <h3>Cash Flow (3Y) &amp; Quality</h3>
      {cf_html or '<p style="color:#64748b">No CF data.</p>'}
    </div>
  </div>

  <div class="overview-grid" style="margin-top:12px">
    <div class="summary-card">
      <h3>Recent Corporate Events &amp; Insider Activity (90d)</h3>
      {news_html}
    </div>
    <div class="summary-card">
      <h3>Latest Filings Snapshot</h3>
      {filings_html or '<p style="color:#64748b;font-size:12px;margin:0">No filing summaries.</p>'}
    </div>
  </div>
</div>
"""


def render_html(snap_date: str, picks: list[PickRationale], enriched: list[dict],
                narratives: dict, macro_context: str) -> str:
    h = html_mod.escape
    logo_uri = _asset_data_uri(AGENT_LOGO_PATH)
    logo_html = f'<img class="brand-logo" src="{logo_uri}" alt="Agent adda logo">' if logo_uri else ''

    # Executive summary brief card (same look as sector rotation Market Brief)
    exec_summary = narratives.get("executive_summary", "")
    portfolio_text = narratives.get("portfolio_construction", "")

    brief_html = ""
    if exec_summary or portfolio_text:
        brief_blocks = []
        if exec_summary:
            brief_blocks.append(
                f'<div class="brief-block"><div class="brief-label">Executive Summary</div>'
                f'<div class="brief-text">{h(exec_summary)}</div></div>'
            )
        if macro_context:
            brief_blocks.append(
                f'<div class="brief-block"><div class="brief-label">Macro Context</div>'
                f'<div class="brief-text">{h(macro_context)}</div></div>'
            )
        if portfolio_text:
            brief_blocks.append(
                f'<div class="brief-block"><div class="brief-label">Portfolio Construction</div>'
                f'<div class="brief-text">{h(portfolio_text)}</div></div>'
            )
        top_conv = narratives.get("top_conviction_picks") or []
        if top_conv:
            brief_blocks.append(
                f'<div class="brief-block"><div class="brief-label">Top Conviction</div>'
                f'<div class="brief-text">{h(" · ".join(top_conv))}</div></div>'
            )
        sec_note = narratives.get("sector_concentration_note")
        if sec_note:
            brief_blocks.append(
                f'<div class="brief-block"><div class="brief-label">Sector Concentration</div>'
                f'<div class="brief-text">{h(sec_note)}</div></div>'
            )
        sector_counts: dict[str, int] = {}
        for p in picks:
            sector_counts[p.sector] = sector_counts.get(p.sector, 0) + 1
        spread = " · ".join(f"{s}: {c}" for s, c in sorted(sector_counts.items(), key=lambda x: -x[1]))
        if spread:
            brief_blocks.append(
                f'<div class="brief-block"><div class="brief-label">Sector Spread</div>'
                f'<div class="brief-text">{h(spread)}</div></div>'
            )
        brief_html = (
            '<div class="content" style="padding-top:0;padding-bottom:0">'
            '<div class="brief-card"><div class="brief-title">Investment Brief</div>'
            f'<div class="brief-grid">{"".join(brief_blocks)}</div></div></div>'
        )

    # Pick summary table
    per_stock_narr = narratives.get("per_stock", {})
    summary_rows = []
    for i, (p, e) in enumerate(zip(picks, enriched), 1):
        snap = e["snapshot"] or {}
        narr_i = per_stock_narr.get(p.symbol, {})
        conv_i = (narr_i.get("conviction") or "").upper()
        conv_c = {"HIGH": "#16a34a", "MEDIUM": "#d97706", "LOW": "#64748b"}.get(conv_i, "#64748b")
        summary_rows.append(
            f"<tr><td>{i}</td>"
            f"<td><a href='#pick-{i}' style='font-weight:700'>{h(p.symbol)}</a></td>"
            f"<td>{h(p.sector)}</td>"
            f"<td style='text-align:right'>₹{_nz(snap.get('price'))}</td>"
            f"<td>{h(snap.get('stage') or '—')}</td>"
            f"<td style='text-align:right;font-weight:600'>{_nz(snap.get('investment_score'))}</td>"
            f"<td style='text-align:right'>{_pct(snap.get('relative_strength'))}</td>"
            f"<td style='text-align:right'>{_nz(snap.get('enhanced_fund_score'))}</td>"
            f"<td>{h(snap.get('stance') or '—')}</td>"
            f"<td><span style='color:{conv_c};font-weight:700'>{h(conv_i)}</span></td>"
            f"<td>{h(p.source)}</td></tr>"
        )

    summary_table_html = f"""
<div class="card">
  <div class="card-title">Top {len(picks)} Picks — {snap_date}</div>
  <table style="width:100%;border-collapse:collapse">
    <thead><tr>
      <th>#</th><th>Symbol</th><th>Sector</th><th style='text-align:right'>Price</th>
      <th>Stage</th><th style='text-align:right'>Inv.Score</th>
      <th style='text-align:right'>RS%</th><th style='text-align:right'>Fund</th>
      <th>Stance</th><th>Conviction</th><th>Source</th>
    </tr></thead>
    <tbody>{''.join(summary_rows)}</tbody>
  </table>
</div>
"""

    cards_html = "".join(
        _stock_card_html(i, p, e, per_stock_narr.get(p.symbol, {}))
        for i, (p, e) in enumerate(zip(picks, enriched), 1)
    )

    methodology_html = """
<div class="card">
  <div class="card-title">Methodology</div>
  <p>Picks merge two independent screens:</p>
  <ol style="margin-left:22px;line-height:1.7">
    <li><strong>Sector Rotation Report</strong> — top investment-score names within the leading sectors (1M RS, momentum, technical+fundamental score).</li>
    <li><strong>Stage 2 Tracker</strong> — Weinstein-stage-2 universe ranked by <code>scores.stage_snapshots.investment_score</code>.</li>
  </ol>
  <p>Dual-confirmed names (appearing in BOTH screens) are prioritised. Per-stock deep dive uses 260 trading days of EOD: EMA 20/50/200 stack, EMA50 slope, RSI(14), ATR(14), 52w hi/lo, 1M/3M/6M/1Y returns, volume ratio. Fundamentals: Piotroski F-score, Altman Z, Beneish M, ROE/ROCE, 3Y growth, D/E, promoter holding.</p>
</div>
"""

    disclaimer_html = f"""
<div class="card" style="background:#fef3c7;border-left:4px solid #d97706">
  <div class="card-title" style="color:#92400e">Full Disclaimer &amp; Use Restrictions</div>
  <p style="font-size:12px;line-height:1.6">{h(PRINT_FOOTER_DISCLAIMER)}</p>
  <p style="font-size:11px;line-height:1.55;color:#78350f">{h(FULL_LEGAL_DISCLAIMER)}</p>
</div>
"""

    parts = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>Top Investment Picks — {snap_date}</title>',
        f'<style>{_CSS}</style>',
        '</head>',
        '<body>',
        f'<div class="print-page-header"><span>{h(AGENT_BRAND)}</span><span>Top Investment Picks</span></div>',
        f'<div class="print-page-footer">{h(PRINT_FOOTER_DISCLAIMER)}</div>',
        '<header class="site-hdr">',
        '<div class="hdr-inner">',
        '<div class="hdr-brand">',
        logo_html,
        '<div class="hdr-copy">',
        f'<div class="hdr-kicker">{h(AGENT_BRAND)}</div>',
        '<div class="hdr-title">Top Investment Picks Analysis</div>',
        '</div></div>',
        '<div class="hdr-meta">',
        f'<span class="mbadge mbadge-date">Report Date: {snap_date}</span>',
        f'<span class="mbadge mbadge-data">Picks: {len(picks)}</span>',
        '</div></div></header>',
        f'<div class="disc"><strong>Disclaimer:</strong> {h(REPORT_DISCLAIMER)}</div>',
        brief_html,
        '<div class="content">',
        summary_table_html,
        methodology_html,
        '<h2 style="font-size:1.1rem;color:#1e3a5f;margin:24px 0 12px">Per-Stock Deep Dive</h2>',
        cards_html,
        disclaimer_html,
        '</div></body></html>',
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
            enriched.append({
                "symbol": p.symbol,
                "sector": p.sector,
                "source": p.source,
                "snapshot": get_snapshot(conn, p.symbol, snap_date),
                "tech": compute_technicals(conn, p.symbol, snap_date),
                "fund": get_fundamentals(conn, p.symbol),
                "quarterly": qtr,
                "annual": ann,
                "balance_sheet": bs,
                "cash_flow": cf,
                "fund_scores": get_fund_score_breakdown(conn, p.symbol),
                "sector_ctx": get_sector_context(conn, p.sector, snap_date),
                "corp_events": get_corporate_events(conn, p.symbol),
                "insider": get_insider_activity(conn, p.symbol),
                "analytics": compute_financial_analytics(qtr, ann, bs, cf),
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
    args = ap.parse_args()

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
