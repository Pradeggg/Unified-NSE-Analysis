"""Recursive Insights Composite (RIC) — multi-layer market analysis.

Pipeline (all data fetched in parallel):
  1. Intraday levels (pivot, S/R, EMAs) from PG
  2. Options chain (PCR, max pain, CE/PE walls)  from PG EOD
  3. NIFTY 50 index snapshot (broader market)
  4. Futures analysis (basis, OI change)
  5. PG FNO signals (historical PCR, buildup)

Outputs:
  - safety  : score 1-10 + rating + reasons
  - intraday : trigger/stop/targets/R:R/potential_pct
  - swing    : trigger/stop/targets/R:R/holding_period
  - fno      : PCR, max pain, CE/PE walls, signal
  - market   : NIFTY bias, 10d trend
  - draw_signals : list of {price, label, color, width, dash} for TV overlay
  - recommendation : LLM-synthesized 5-bullet action plan
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import sys
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

router = APIRouter()
log = logging.getLogger(__name__)
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_FNO_INDICES = {"BANKNIFTY", "NIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50", "SENSEX"}


# ── Symbol → NSE index name mapping (for get_index_snapshot) ─────────────────

_SYMBOL_TO_INDEX: dict[str, str] = {
    "NIFTY":       "Nifty 50",
    "BANKNIFTY":   "Nifty Bank",
    "FINNIFTY":    "Nifty Fin Service",
    "MIDCPNIFTY":  "NIFTY MID SELECT",
    "NIFTYNXT50":  "Nifty Next 50",
    "SENSEX":      "SENSEX",
}


def _sym_index_name(sym: str) -> str | None:
    return _SYMBOL_TO_INDEX.get(sym.upper())


def _tools():
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    import terminal.tools as t
    return t


async def _run(fn, *args):
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return await loop.run_in_executor(pool, fn, *args)


def _safe(fn, *args, default=None):
    try:
        return fn(*args)
    except Exception as exc:
        log.debug("_safe %s failed: %s", getattr(fn, "__name__", fn), exc)
        return default if default is not None else {}


def _sym_trend(snap: dict) -> str:
    """Derive trend label from index snapshot's trend_10d up_days."""
    up = int((snap.get("trend_10d") or {}).get("up_days", -1) or -1)
    if up < 0:
        return "unknown"
    return "bullish" if up >= 6 else "bearish" if up <= 4 else "neutral"


# ── Safety score ──────────────────────────────────────────────────────────────

def _compute_safety(price: float, pivot: float, ema21: float,
                    nifty_up_days: int, pcr: float, max_pain: float) -> dict:
    score = 5.0
    reasons: list[str] = []

    # Broader market momentum
    if nifty_up_days >= 7:
        score += 1.5
        reasons.append(f"NIFTY strong bull — {nifty_up_days}/10 up days")
    elif nifty_up_days >= 5:
        score += 0.5
        reasons.append(f"NIFTY mildly bullish — {nifty_up_days}/10 up days")
    elif nifty_up_days <= 2:
        score -= 1.5
        reasons.append(f"NIFTY bearish — only {nifty_up_days}/10 up days")
    elif nifty_up_days <= 4:
        score -= 0.5
        reasons.append(f"NIFTY weak — {nifty_up_days}/10 up days")

    # Put-Call Ratio sentiment
    if pcr > 1.2:
        score += 0.5
        reasons.append(f"PCR {pcr:.2f} — heavy put writing, bulls in control")
    elif pcr > 0 and pcr < 0.8:
        score -= 0.5
        reasons.append(f"PCR {pcr:.2f} — heavy call writing, cautious")
    elif pcr > 0:
        reasons.append(f"PCR {pcr:.2f} — balanced options activity")

    # Max pain gravitational pull
    if max_pain > 0 and price > 0:
        mp_diff_pct = (max_pain - price) / price * 100
        if mp_diff_pct > 1.5:
            score += 0.5
            reasons.append(f"Max pain ₹{max_pain:.0f} well above spot — upward pull")
        elif mp_diff_pct < -1.5:
            score -= 0.5
            reasons.append(f"Max pain ₹{max_pain:.0f} below spot — downward pull")

    # Price vs EMA21 (short-term momentum)
    if ema21 > 0 and price > 0:
        if price > ema21 * 1.005:
            score += 0.5
            reasons.append("Price above EMA21 — short-term momentum positive")
        elif price < ema21 * 0.995:
            score -= 0.5
            reasons.append("Price below EMA21 — short-term momentum negative")

    # Price vs intraday pivot
    if pivot > 0 and price > 0:
        if price > pivot * 1.002:
            score += 0.3
            reasons.append("Above day pivot — intraday strength")
        elif price < pivot * 0.998:
            score -= 0.3
            reasons.append("Below day pivot — intraday weakness")

    score = max(1.0, min(10.0, round(score * 2) / 2))  # round to 0.5
    iscore = round(score)

    if iscore >= 8:
        rating, color = "SAFE", "#00c853"
    elif iscore >= 6:
        rating, color = "MODERATE", "#ffd740"
    elif iscore >= 4:
        rating, color = "CAUTION", "#ff9100"
    else:
        rating, color = "RISKY", "#ff1744"

    return {"score": iscore, "rating": rating, "color": color, "reasons": reasons[:5]}


# ── Intraday setup ────────────────────────────────────────────────────────────

def _compute_intraday(price: float, pivot: float, supports: list,
                      resistances: list, ema9: float, ema21: float) -> dict:
    if not price:
        return {}

    if price >= pivot:
        bias = "BULLISH"
        trigger  = resistances[0] if resistances else round(price * 1.005, 2)
        stop     = supports[0]    if supports    else round(pivot * 0.998, 2)
        t1       = resistances[1] if len(resistances) > 1 else round(trigger * 1.006, 2)
        t2       = resistances[2] if len(resistances) > 2 else round(trigger * 1.012, 2)
        strategy = "Pivot breakout — long above R1 with volume"
    else:
        bias = "BEARISH"
        trigger  = supports[0]    if supports    else round(price * 0.995, 2)
        stop     = resistances[0] if resistances else round(pivot * 1.002, 2)
        t1       = supports[1]    if len(supports) > 1 else round(trigger * 0.994, 2)
        t2       = supports[2]    if len(supports) > 2 else round(trigger * 0.988, 2)
        strategy = "Pivot rejection — short below S1 on confirmation"

    risk   = abs(trigger - stop)
    reward = abs(t1 - trigger)
    rr     = round(reward / risk, 2) if risk > 0 else 0.0
    potential_pct = round(reward / trigger * 100, 3) if trigger > 0 else 0.0

    return {
        "bias": bias,
        "trigger": round(trigger, 2),
        "stop":    round(stop, 2),
        "targets": [round(t1, 2), round(t2, 2)],
        "rr": rr,
        "strategy": strategy,
        "potential_pct": potential_pct,
        "holding": "same-day (exit before 3:15 PM)",
    }


# ── Swing setup ───────────────────────────────────────────────────────────────

def _compute_swing(price: float, ema50: float, ema200: float,
                   nifty_chg_10d: float, supports: list, resistances: list) -> dict:
    if not price:
        return {}

    above_ema50  = price > ema50  if ema50  > 0 else None
    above_ema200 = price > ema200 if ema200 > 0 else None

    if above_ema50 and above_ema200:
        bias     = "BULLISH"
        trigger  = resistances[-1] if resistances else round(price * 1.012, 2)
        stop     = ema50 if ema50 > 0 else (supports[-1] if supports else round(price * 0.96, 2))
        t1       = round(trigger * 1.018, 2)
        t2       = round(trigger * 1.035, 2)
        strategy = "Trend continuation — buy breakout; hold 3-7 days"
    elif above_ema50 is False and above_ema200 is False:
        bias     = "BEARISH"
        trigger  = supports[-1] if supports else round(price * 0.988, 2)
        stop     = ema50 if ema50 > 0 else (resistances[0] if resistances else round(price * 1.03, 2))
        t1       = round(trigger * 0.982, 2)
        t2       = round(trigger * 0.965, 2)
        strategy = "Downtrend — sell bounce near EMA50; hold 3-5 days"
    else:
        bias     = "NEUTRAL"
        trigger  = resistances[0] if resistances else round(price * 1.01, 2)
        stop     = supports[0]    if supports    else round(price * 0.97, 2)
        t1       = round(trigger * 1.012, 2)
        t2       = round(trigger * 1.025, 2)
        strategy = "EMA crossover pending — wait for EMA50/200 resolution"

    risk   = abs(trigger - stop)
    reward = abs(t1 - trigger)
    rr     = round(reward / risk, 2) if risk > 0 else 0.0
    potential_pct = round(reward / trigger * 100, 3) if trigger > 0 else 0.0

    return {
        "bias": bias,
        "trigger": round(trigger, 2),
        "stop":    round(stop, 2),
        "targets": [round(t1, 2), round(t2, 2)],
        "rr": rr,
        "strategy": strategy,
        "potential_pct": potential_pct,
        "holding": "3-7 days (positional)",
    }


# ── Options strategy suggestion ───────────────────────────────────────────────

def _options_play(intraday_bias: str, swing_bias: str, pcr: float,
                  atm: float, expiry: str) -> dict:
    """Suggest a simple options strategy based on bias + PCR."""
    if not atm:
        return {}

    if intraday_bias == "BULLISH" and swing_bias == "BULLISH":
        strat = "Bull Call Spread"
        desc  = f"Buy {atm:.0f}CE, Sell {atm*1.01:.0f}CE — limited risk, capped upside"
        risk  = "Max loss: premium paid"
    elif intraday_bias == "BEARISH" and swing_bias == "BEARISH":
        strat = "Bear Put Spread"
        desc  = f"Buy {atm:.0f}PE, Sell {atm*0.99:.0f}PE — limited risk, capped downside"
        risk  = "Max loss: premium paid"
    elif pcr > 1.1:
        strat = "Short Strangle (sell premium)"
        desc  = f"Sell {atm*1.015:.0f}CE + Sell {atm*0.985:.0f}PE — profit from time decay in range"
        risk  = "Unlimited risk — use only with hedges"
    else:
        strat = "ATM Straddle (neutral)"
        desc  = f"Buy {atm:.0f}CE + Buy {atm:.0f}PE — profit from big move either way"
        risk  = "Max loss: both premiums if price stays near ATM"

    return {
        "strategy": strat,
        "description": desc,
        "expiry": expiry,
        "risk_note": risk,
    }


# ── Draw signals builder ──────────────────────────────────────────────────────

def _build_draw_signals(levels: dict, intraday: dict, swing: dict) -> list[dict]:
    sigs: list[dict] = []
    pivot       = levels.get("pivot", 0)
    supports    = levels.get("supports", [])
    resistances = levels.get("resistances", [])
    emas        = levels.get("ema_levels", {})

    if pivot:
        sigs.append({"type": "pivot",      "price": round(pivot, 2), "label": "PP",   "color": "#ffd740", "width": 1, "dash": True})
    for i, s in enumerate(supports[:3]):
        sigs.append({"type": "support",    "price": round(s, 2),     "label": f"S{i+1}", "color": "#00c853", "width": 1, "dash": True})
    for i, r in enumerate(resistances[:3]):
        sigs.append({"type": "resistance", "price": round(r, 2),     "label": f"R{i+1}", "color": "#ff1744", "width": 1, "dash": True})

    _EMA_COLORS = {"ema9": "#ff9800", "ema21": "#e040fb", "ema50": "#29b6f6", "ema200": "#26c6da"}
    for name, p in emas.items():
        if p:
            sigs.append({"type": "ema", "price": round(p, 2), "label": name.upper(),
                         "color": _EMA_COLORS.get(name, "#aaaaaa"), "width": 1, "dash": False})

    # Intraday signals (thicker / solid)
    if intraday.get("trigger"):
        icon = "⚡ BUY" if intraday.get("bias") == "BULLISH" else "⚡ SELL"
        sigs.append({"type": "intraday_trigger", "price": intraday["trigger"],
                     "label": icon, "color": "#00e676", "width": 2, "dash": False})
    if intraday.get("stop"):
        sigs.append({"type": "intraday_stop", "price": intraday["stop"],
                     "label": "🛑 SL·I", "color": "#ff5252", "width": 2, "dash": False})
    for i, t in enumerate(intraday.get("targets", [])[:2]):
        sigs.append({"type": "intraday_target", "price": t,
                     "label": f"🎯 T{i+1}·I", "color": "#69f0ae", "width": 1, "dash": False})

    # Swing signals (dashed, lighter)
    if swing.get("trigger") and swing.get("bias") != "NEUTRAL":
        icon = "↑ SWING" if swing.get("bias") == "BULLISH" else "↓ SWING"
        sigs.append({"type": "swing_trigger", "price": swing["trigger"],
                     "label": icon, "color": "#80cbc4", "width": 1, "dash": True})
    if swing.get("stop") and swing.get("bias") != "NEUTRAL":
        sigs.append({"type": "swing_stop", "price": swing["stop"],
                     "label": "🛑 SL·S", "color": "#ff80ab", "width": 1, "dash": True})
    for i, t in enumerate(swing.get("targets", [])[:2]):
        if swing.get("bias") != "NEUTRAL":
            sigs.append({"type": "swing_target", "price": t,
                         "label": f"🎯 T{i+1}·S", "color": "#80deea", "width": 1, "dash": True})

    return sigs


# ── LLM recommendation ────────────────────────────────────────────────────────

def _llm_recommendation(symbol: str, timeframe: str, safety: dict,
                         intraday: dict, swing: dict, fno: dict,
                         market: dict, options_play: dict,
                         capture_answer: str = "") -> tuple[str, int, int]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _fallback_text(symbol, safety, intraday, swing), 0, 0

    try:
        from openai import OpenAI  # type: ignore
        client = OpenAI(api_key=api_key)
        model  = os.getenv("AGENT_ADDA_VISION_MODEL", "gpt-4o")

        data_block = (
            f"Symbol: {symbol} | TF: {timeframe}\n"
            f"Safety: {safety.get('rating')} ({safety.get('score')}/10)\n"
            f"Reasons: {'; '.join(safety.get('reasons', []))}\n\n"
            f"INTRADAY ({intraday.get('bias','?')})\n"
            f"  Trigger ₹{intraday.get('trigger','?')} | SL ₹{intraday.get('stop','?')} | "
            f"T1 ₹{(intraday.get('targets') or ['?'])[0]} | T2 ₹{(intraday.get('targets') or ['?','?'])[1]} | "
            f"RR {intraday.get('rr','?')}x | Potential {intraday.get('potential_pct','?')}%\n"
            f"  Strategy: {intraday.get('strategy','')}\n\n"
            f"SWING ({swing.get('bias','?')})\n"
            f"  Trigger ₹{swing.get('trigger','?')} | SL ₹{swing.get('stop','?')} | "
            f"T1 ₹{(swing.get('targets') or ['?'])[0]} | T2 ₹{(swing.get('targets') or ['?','?'])[1]} | "
            f"RR {swing.get('rr','?')}x | Potential {swing.get('potential_pct','?')}%\n"
            f"  Strategy: {swing.get('strategy','')}\n\n"
            f"F&O: PCR={fno.get('pcr','?')} | ATM={fno.get('atm','?')} | MaxPain={fno.get('max_pain','?')}\n"
            f"  CE Resistance: {fno.get('ce_resistance',[])} | PE Support: {fno.get('pe_support',[])}\n"
            f"  Signal: {fno.get('fno_signal','?')}\n\n"
            f"MARKET: NIFTY {market.get('nifty_chg_pct','?')}% | 10d up_days={market.get('nifty_up_days','?')} "
            f"({market.get('nifty_trend','?')})\n\n"
            f"OPTIONS PLAY: {options_play.get('strategy','?')} — {options_play.get('description','')}\n"
        )
        if capture_answer:
            data_block += f"\nCHART ANALYSIS:\n{capture_answer[:500]}\n"

        prompt = (
            "You are Agent Adda — an NSE trading analyst. "
            "Given this RIC multi-layer analysis, write exactly 5 concise bullet points:\n"
            "1) Overall verdict: safe/risky + 1-line reason\n"
            "2) Best intraday trade: action, entry, stop, target, R:R\n"
            "3) Swing opportunity: action, entry, stop, target, holding\n"
            "4) Options play: strategy + strikes + why\n"
            "5) Key risk/watch: what would invalidate — be specific\n\n"
            "Rules: use ₹ for prices; be specific; no generic disclaimers; "
            "if no clean trade exists, say so.\n\n"
            f"{data_block}"
        )

        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=380,
        )
        text    = resp.choices[0].message.content or ""
        in_tok  = resp.usage.prompt_tokens     if resp.usage else 0
        out_tok = resp.usage.completion_tokens if resp.usage else 0
        return text, in_tok, out_tok
    except Exception as exc:
        log.warning("RIC LLM failed: %s", exc)
        return _fallback_text(symbol, safety, intraday, swing), 0, 0


def _fallback_text(symbol: str, safety: dict, intraday: dict, swing: dict) -> str:
    i = intraday
    s = swing
    return "\n".join([
        f"• {safety.get('rating','?')} ({safety.get('score','?')}/10) — {(safety.get('reasons') or ['n/a'])[0]}",
        f"• Intraday {i.get('bias','?')}: enter ₹{i.get('trigger','?')}, SL ₹{i.get('stop','?')}, "
        f"T1 ₹{(i.get('targets') or ['?'])[0]} (RR {i.get('rr','?')}x, +{i.get('potential_pct','?')}%)",
        f"• Swing {s.get('bias','?')}: enter ₹{s.get('trigger','?')}, SL ₹{s.get('stop','?')}, "
        f"T1 ₹{(s.get('targets') or ['?'])[0]} (RR {s.get('rr','?')}x, +{s.get('potential_pct','?')}%)",
        f"• {s.get('strategy','')}",
        f"• Invalidation: price breaks below intraday SL ₹{i.get('stop','?')} on high volume",
    ])


# ── Main endpoint ─────────────────────────────────────────────────────────────

@router.get("/analyze")
async def ric_analyze(
    symbol:     str           = Query(...,    description="NSE symbol e.g. BANKNIFTY, RELIANCE"),
    timeframe:  str           = Query("15m",  description="Intraday timeframe: 5m,15m,1h"),
    exchange:   str           = Query("NSE"),
    capture_id: Optional[str] = Query(None,   description="Existing chart capture session to include in recommendation"),
):
    """
    Recursive Insights Composite — aggregates intraday levels, F&O, market context
    and daily trend into a unified safety score + trade plan + TradingView draw signals.
    """
    sym = symbol.strip().upper()
    tf  = timeframe.lower().strip()
    t   = _tools()

    # ── Parallel data fetch ───────────────────────────────────────────────────
    sym_index_name = _sym_index_name(sym)   # e.g. MIDCPNIFTY → "NIFTY MIDCAP SELECT"
    fetch_results = await asyncio.gather(
        _run(lambda: _safe(t.get_intraday_levels, sym, tf)),
        _run(lambda: _safe(t.get_index_snapshot, "NIFTY 50")),
        _run(lambda: _safe(t.get_options_chain, sym)),
        _run(lambda: _safe(t.get_futures_analysis, sym)),
        _run(lambda: _safe(t._quick_analysis_fno, sym)),
        # Fetch the symbol's own index snapshot (non-null only for known indices)
        _run(lambda: _safe(t.get_index_snapshot, sym_index_name) if sym_index_name else {}),
        return_exceptions=True,
    )

    def _unpack(r, default=None):
        return r if not isinstance(r, Exception) else (default or {})

    levels   = _unpack(fetch_results[0])
    nifty    = _unpack(fetch_results[1])
    options  = _unpack(fetch_results[2])
    futures  = _unpack(fetch_results[3])
    pg_fno   = _unpack(fetch_results[4])
    sym_snap = _unpack(fetch_results[5])   # symbol's own index snapshot (may be {})

    # ── Extract primitives ────────────────────────────────────────────────────
    price       = float(levels.get("latest_close", 0) or 0)
    pivot       = float(levels.get("pivot", 0) or 0)
    supports    = [float(x) for x in levels.get("supports", [])]
    resistances = [float(x) for x in levels.get("resistances", [])]
    ema_map     = levels.get("ema_levels", {}) or {}
    ema9        = float(ema_map.get("ema9",  0) or 0)
    ema21       = float(ema_map.get("ema21", 0) or 0)
    ema50       = float(ema_map.get("ema50", 0) or 0)
    ema200      = float(ema_map.get("ema200",0) or 0)

    nifty_trend  = nifty.get("trend_10d", {}) or {}
    nifty_up_days = int(nifty_trend.get("up_days", 5) or 5)
    nifty_chg_10d = float(nifty_trend.get("chg_pct", 0) or 0)

    # Options — prefer live, fall back to PG
    pcr      = float(options.get("pcr", 0) or pg_fno.get("pcr", 0) or 0)
    max_pain = float(options.get("max_pain", 0) or 0)
    atm      = float(options.get("atm", 0) or 0)
    expiry   = str(options.get("expiry", "") or "")
    calls    = options.get("calls", []) or []
    puts     = options.get("puts",  []) or []
    ce_top   = [float(c["strike"]) for c in sorted(calls, key=lambda x: x.get("oi", 0), reverse=True)[:3] if "strike" in c]
    pe_top   = [float(p["strike"]) for p in sorted(puts,  key=lambda x: x.get("oi", 0), reverse=True)[:3] if "strike" in p]

    fut_ok       = not futures.get("error")
    basis_pct    = float(futures.get("basis_pct") or 0) if fut_ok else None
    fno_signal   = str(pg_fno.get("fno_signal", "") or futures.get("signal", "") or "NEUTRAL")

    # ── Compute components ────────────────────────────────────────────────────
    safety   = _compute_safety(price, pivot, ema21, nifty_up_days, pcr, max_pain)
    intraday = _compute_intraday(price, pivot, supports, resistances, ema9, ema21)
    swing    = _compute_swing(price, ema50, ema200, nifty_chg_10d, supports, resistances)

    fno_data = {
        "pcr":          round(pcr, 3),
        "atm":          atm,
        "max_pain":     max_pain,
        "ce_resistance": ce_top,
        "pe_support":    pe_top,
        "basis_pct":     round(basis_pct, 3) if basis_pct is not None else None,
        "fno_signal":    fno_signal,
        "expiry":        expiry,
    }

    market_data = {
        "nifty_close":    float(nifty.get("close", 0) or 0),
        "nifty_chg_pct":  float(nifty.get("chg_pct", 0) or 0),
        "nifty_up_days":  nifty_up_days,
        "nifty_trend":    "bullish" if nifty_up_days >= 6 else "bearish" if nifty_up_days <= 4 else "neutral",
        "nifty_52w_high": float(nifty.get("52w_high", 0) or 0),
        "nifty_52w_low":  float(nifty.get("52w_low",  0) or 0),
        # Symbol's own snapshot (e.g. MIDCPNIFTY vs NIFTY 50 as broad market)
        "symbol_close":    float(sym_snap.get("close", price) or price),
        "symbol_chg_pct":  float(sym_snap.get("chg_pct", 0) or 0),
        "symbol_52w_high": float(sym_snap.get("52w_high", 0) or 0),
        "symbol_52w_low":  float(sym_snap.get("52w_low",  0) or 0),
        "symbol_trend":    _sym_trend(sym_snap),
        "symbol_up_days":  int((sym_snap.get("trend_10d") or {}).get("up_days", 0) or 0),
        "is_index":        sym_index_name is not None,
    }

    key_levels_data = {
        "price":       price,
        "pivot":       pivot,
        "supports":    supports[:4],
        "resistances": resistances[:4],
        "ema9":   ema9,
        "ema21":  ema21,
        "ema50":  ema50,
        "ema200": ema200,
        "pivot_levels": levels.get("pivot_levels", {}),
    }

    options_play = _options_play(
        intraday.get("bias", "NEUTRAL"),
        swing.get("bias", "NEUTRAL"),
        pcr, atm, expiry,
    )

    draw_signals = _build_draw_signals(levels, intraday, swing)

    # ── Optional: pull prior chart analysis text from session ─────────────────
    capture_answer = ""
    if capture_id:
        try:
            from .analysis import _sessions  # noqa: PLC0415
            sess = _sessions.get(capture_id, {})
            for h in reversed(sess.get("history", [])):
                if h.get("role") == "assistant":
                    content = h.get("content", "")
                    if isinstance(content, list):
                        content = " ".join(
                            c.get("text", "") for c in content if isinstance(c, dict)
                        )
                    capture_answer = str(content)[:600]
                    break
        except Exception:
            pass

    # ── LLM synthesis ─────────────────────────────────────────────────────────
    recommendation, in_tok, out_tok = _llm_recommendation(
        sym, tf, safety, intraday, swing, fno_data, market_data,
        options_play, capture_answer,
    )

    return {
        "symbol":       sym,
        "timeframe":    tf,
        "as_of":        datetime.now().isoformat(),
        "safety":       safety,
        "market":       market_data,
        "fno":          fno_data,
        "intraday":     intraday,
        "swing":        swing,
        "options_play": options_play,
        "key_levels":   key_levels_data,
        "draw_signals": draw_signals,
        "recommendation": recommendation,
        "model":        os.getenv("AGENT_ADDA_VISION_MODEL", "gpt-4o"),
        "input_tokens": in_tok,
        "output_tokens": out_tok,
    }
