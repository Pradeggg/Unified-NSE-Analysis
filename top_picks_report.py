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


def get_fundamentals(conn, sym: str) -> dict | None:
    return _fetchone(conn, """
        SELECT symbol, piotroski_score, beneish_m_score, altman_z_score,
               forensic_risk, revenue_growth_3y, pat_growth_3y, roe, roce,
               debt_to_equity, promoter_holding, updated_at
        FROM scores.fundamentals WHERE symbol=%s
    """, (sym,))


# ─────────────────────────────────────────────────────────────────────────────
# LLM narrative generation
# ─────────────────────────────────────────────────────────────────────────────
def _serialize_stocks_for_llm(stocks: list[dict]) -> str:
    """Build compact JSON-like list for LLM prompt."""
    rows = []
    for s in stocks:
        snap = s["snapshot"] or {}
        tech = s["tech"]
        fund = s["fund"] or {}
        rows.append({
            "symbol": s["symbol"],
            "sector": s["sector"],
            "source": s["source"],
            "price": float(snap.get("price") or 0) if snap else None,
            "stage": snap.get("stage") if snap else None,
            "investment_score": float(snap.get("investment_score") or 0) if snap else None,
            "technical_score": float(snap.get("technical_score") or 0) if snap else None,
            "enhanced_fund_score": float(snap.get("enhanced_fund_score") or 0) if snap else None,
            "rs_pct": float(snap.get("relative_strength") or 0) if snap else None,
            "trading_signal": snap.get("trading_signal") if snap else None,
            "stance": snap.get("stance") if snap else None,
            "rsi14": tech.get("rsi"),
            "ret_1m_pct": tech.get("ret_1m"),
            "ret_3m_pct": tech.get("ret_3m"),
            "ret_6m_pct": tech.get("ret_6m"),
            "ret_1y_pct": tech.get("ret_1y"),
            "dist_from_52w_high_pct": tech.get("dist_from_high_pct"),
            "atr_pct": tech.get("atr_pct"),
            "ema50_slope_pct": tech.get("ema50_slope_pct"),
            "piotroski": float(fund.get("piotroski_score") or 0) if fund.get("piotroski_score") is not None else None,
            "altman_z": float(fund.get("altman_z_score") or 0) if fund.get("altman_z_score") is not None else None,
            "beneish_m": float(fund.get("beneish_m_score") or 0) if fund.get("beneish_m_score") is not None else None,
            "roe": float(fund.get("roe") or 0) if fund.get("roe") is not None else None,
            "roce": float(fund.get("roce") or 0) if fund.get("roce") is not None else None,
            "debt_to_equity": float(fund.get("debt_to_equity") or 0) if fund.get("debt_to_equity") is not None else None,
            "pat_growth_3y_pct": float(fund.get("pat_growth_3y") or 0) if fund.get("pat_growth_3y") is not None else None,
            "promoter_holding_pct": float(fund.get("promoter_holding") or 0) if fund.get("promoter_holding") is not None else None,
        })
    return json.dumps(rows, indent=1)


def _rule_based_narratives(stocks: list[dict]) -> dict:
    """Deterministic fallback when LLM is unavailable."""
    per_stock = {}
    for s in stocks:
        snap = s["snapshot"] or {}
        tech = s["tech"]
        fund = s["fund"] or {}
        bull, risk, action = [], [], []

        if tech.get("ema20") and tech.get("ema50") and tech.get("ema200"):
            if tech["last"] > tech["ema20"] > tech["ema50"] > tech["ema200"]:
                bull.append("Classical Stage-2 trend stack (Price > EMA20 > EMA50 > EMA200)")
        if (tech.get("rsi") or 0) > 70:
            risk.append(f"RSI {tech['rsi']:.0f} — overbought; pullback risk")
        elif (tech.get("rsi") or 0) > 60:
            bull.append(f"Strong momentum (RSI {tech['rsi']:.0f})")
        if tech.get("dist_from_high_pct") is not None and tech["dist_from_high_pct"] > -5:
            bull.append("Within 5% of 52w high — breakout proximity")
        rs = float(snap.get("relative_strength") or 0)
        if rs > 50:
            bull.append(f"Outpacing Nifty 500 by {rs:.0f}% (RS)")
        ps = float(fund.get("piotroski_score") or 0)
        if ps >= 7:
            bull.append(f"High quality (Piotroski {ps:.0f}/9)")
        az = float(fund.get("altman_z_score") or 0)
        if az and az < 1.8:
            risk.append(f"Distress zone (Altman Z {az:.1f})")
        bm = float(fund.get("beneish_m_score") or 0)
        if bm and bm > -1.78:
            risk.append(f"Earnings-manipulation flag (Beneish M {bm:.2f})")
        de = float(fund.get("debt_to_equity") or 0)
        if de and de > 1.5:
            risk.append(f"Elevated leverage (D/E {de:.2f})")
        if not action:
            action.append(f"{snap.get('trading_signal','HOLD')} bias; stage {snap.get('stage','—')}")

        per_stock[s["symbol"]] = {
            "thesis": " · ".join(bull) or "Mechanical pick from screen overlap; manual review recommended.",
            "risks": " · ".join(risk) or "No quantitative red flags surfaced.",
            "action": " · ".join(action),
        }
    return {
        "executive_summary": (
            f"Mechanically-screened list of {len(stocks)} stocks combining sector-rotation "
            "leadership and stage-2 momentum. Rule-based narrative (LLM unavailable)."
        ),
        "portfolio_construction": (
            "Equal-weight 10% per name baseline. Under elevated VIX/bear regimes, scale gross "
            "exposure to 60-70% and hold residual in cash; cap per-trade risk at 1-2% of "
            "portfolio via stop-distance × position size."
        ),
        "per_stock": per_stock,
    }


def _build_llm_prompt(stocks: list[dict], macro_context: str, snap_date: str) -> str:
    return "\n".join([
        f"You are a markets analyst summarising 10 NSE India stock picks for {snap_date}.",
        "These were selected by overlapping two screens: a sector-rotation report and a Weinstein stage-2 tracker.",
        "",
        f"MARKET CONTEXT:\n{macro_context}",
        "",
        "STOCK DATA (JSON):",
        _serialize_stocks_for_llm(stocks),
        "",
        "Return STRICT JSON with this exact shape (no markdown, no commentary):",
        "{",
        '  "executive_summary": "2-3 sentence top-down read across the basket",',
        '  "portfolio_construction": "1-2 sentences on sizing / regime / exit triggers",',
        '  "per_stock": {',
        '    "SYMBOL": {',
        '      "thesis": "1 sentence bull case grounded in the metrics provided",',
        '      "risks": "1 sentence specific bear risk from the data (avoid generic warnings)",',
        '      "action": "1 short sentence: where to enter / what to wait for / which level invalidates"',
        '    }',
        "  }",
        "}",
        "Cover EVERY symbol in the input. Be specific and quantitative — cite RSI, RS, growth, leverage, Piotroski, distance-from-high etc. when relevant.",
    ])


def generate_narratives(stocks: list[dict], macro_context: str, snap_date: str, use_llm: bool) -> dict:
    if not use_llm:
        return _rule_based_narratives(stocks)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("   ⚠️  OPENAI_API_KEY not set — using rule-based narrative")
        return _rule_based_narratives(stocks)
    try:
        prompt = _build_llm_prompt(stocks, macro_context, snap_date)
        result = _llm_call(
            api_key=api_key,
            model=DEFAULT_MODEL,
            system_msg="You are a precise, quantitative equity research assistant. Return only valid JSON.",
            user_msg=prompt,
            max_tokens=8192,
            timeout=200,
        )
        # Validate shape
        if "per_stock" not in result or not isinstance(result["per_stock"], dict):
            raise ValueError("LLM response missing per_stock dict")
        rule_fallback = _rule_based_narratives(stocks)
        # Fill any missing stocks with rule-based fallback
        for sym in [s["symbol"] for s in stocks]:
            if sym not in result["per_stock"]:
                result["per_stock"][sym] = rule_fallback["per_stock"][sym]
        result.setdefault("executive_summary", rule_fallback["executive_summary"])
        result.setdefault("portfolio_construction", rule_fallback["portfolio_construction"])
        return result
    except Exception as exc:
        print(f"   ⚠️  LLM narrative failed: {exc} — using rule-based fallback")
        return _rule_based_narratives(stocks)


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
        if narr.get("risks"):
            out.append(f"**Key risks:** {narr['risks']}\n\n")
        if narr.get("action"):
            out.append(f"**Action:** {narr['action']}\n\n")

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
    h = html_mod.escape
    src_badge = {
        "dual": '<span class="mbadge mbadge-date" style="background:#16a34a">DUAL-CONFIRMED</span>',
        "sector_rot": '<span class="mbadge mbadge-date" style="background:#2563eb">SECTOR LEADER</span>',
        "stage2": '<span class="mbadge mbadge-date" style="background:#7c3aed">STAGE 2</span>',
    }.get(p.source, "")

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
        rows_fund.append(("Piotroski F-score", f"{_nz(fund.get('piotroski_score'))} / 9"))
        rows_fund.append(("Altman Z", _nz(fund.get('altman_z_score'))))
        rows_fund.append(("Beneish M", _nz(fund.get('beneish_m_score'))))
        rows_fund.append(("Forensic risk", fund.get('forensic_risk') or '—'))
        rows_fund.append(("Revenue 3Y CAGR", _pct(fund.get('revenue_growth_3y'))))
        rows_fund.append(("PAT 3Y CAGR", _pct(fund.get('pat_growth_3y'))))
        rows_fund.append(("ROE / ROCE", f"{_pct(fund.get('roe'))} / {_pct(fund.get('roce'))}"))
        rows_fund.append(("Debt / Equity", _nz(fund.get('debt_to_equity'))))
        rows_fund.append(("Promoter holding", _pct(fund.get('promoter_holding'))))

    def _table(rows):
        if not rows:
            return ""
        body = "".join(f"<tr><td>{h(label)}</td><td style='text-align:right;font-weight:600'>{h(val)}</td></tr>" for label, val in rows)
        return f"<table style='width:100%;border-collapse:collapse'>{body}</table>"

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

    return f"""
<div class="card" id="pick-{idx}" style="border-left:4px solid #1e3a5f">
  <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px">
    <h2 style="margin:0;font-size:1.2rem;color:#1e3a5f">{idx}. {h(p.symbol)}</h2>
    <span class="mbadge mbadge-data">{h(p.sector)}</span>
    {src_badge}
  </div>
  <div class="metrics-row" style="margin-bottom:14px">{headline_html}</div>
  <div class="overview-grid">
    <div class="summary-card" style="background:#fafbfd">
      <h3>Investment Thesis</h3>
      <p style="margin-bottom:8px">{h(narr.get('thesis', '—'))}</p>
      <h3 style="color:#b91c1c">Key Risks</h3>
      <p style="margin-bottom:8px">{h(narr.get('risks', '—'))}</p>
      <h3 style="color:#047857">Action</h3>
      <p>{h(narr.get('action', '—'))}</p>
      <p style="margin-top:10px;font-size:11px;color:#64748b"><em>Why selected:</em> {h(p.rationale)}</p>
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
    </div>
  </div>
  <div class="overview-grid" style="margin-top:12px">
    <div class="summary-card">
      <h3>Technicals</h3>
      {_table(rows_tech) if rows_tech else f'<p style="color:#b45309">{h(tech.get("error", "no data"))}</p>'}
    </div>
    <div class="summary-card">
      <h3>Fundamentals</h3>
      {_table(rows_fund) if rows_fund else '<p style="color:#64748b">No fundamentals row in scores.fundamentals.</p>'}
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
    summary_rows = []
    for i, (p, e) in enumerate(zip(picks, enriched), 1):
        snap = e["snapshot"] or {}
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
      <th>Stance</th><th>Source</th>
    </tr></thead>
    <tbody>{''.join(summary_rows)}</tbody>
  </table>
</div>
"""

    per_stock_narr = narratives.get("per_stock", {})
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
            enriched.append({
                "symbol": p.symbol,
                "sector": p.sector,
                "source": p.source,
                "snapshot": get_snapshot(conn, p.symbol, snap_date),
                "tech": compute_technicals(conn, p.symbol, snap_date),
                "fund": get_fundamentals(conn, p.symbol),
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
