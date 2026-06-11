"""Chart data routes — OHLCV, key levels, technical snapshots from PostgreSQL."""
from __future__ import annotations

import os
import sys
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from ..schemas import KeyLevels

router = APIRouter()

_HERE = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))


def _tools():
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    os.environ.setdefault("AGENT_ADDA_SKIP_VENV_CHECK", "1")
    import terminal.tools as t
    return t


# ── Key levels ────────────────────────────────────────────────────────────────

@router.get("/levels", response_model=KeyLevels)
async def get_key_levels(
    symbol: str = Query(..., description="NSE/BSE symbol, e.g. RELIANCE or BANKNIFTY"),
    exchange: str = Query("NSE"),
    timeframe: str = Query("5m"),
):
    """Return key levels from PG. For indices/intraday uses get_intraday_levels;
    for equities with EOD history uses get_technical_setup."""
    t = _tools()
    sym = symbol.strip().upper()
    try:
        # Try EOD-based technical setup first.
        snap = t.get_technical_setup(sym)
        if not snap.get("error"):
            return KeyLevels(
                ema20=snap.get("ema_20") or snap.get("ema20"),
                ema50=snap.get("ema_50") or snap.get("ema50"),
                ema100=snap.get("ema_100") or snap.get("ema100"),
                ema200=snap.get("ema_200") or snap.get("ema200"),
                supertrend=snap.get("supertrend"),
                supertrend_direction=(
                    "bullish" if str(snap.get("supertrend_signal", "")).upper() in ("BUY", "BULLISH")
                    else "bearish" if str(snap.get("supertrend_signal", "")).upper() in ("SELL", "BEARISH")
                    else None
                ),
                support=snap.get("support"),
                resistance=snap.get("resistance"),
                vwap=snap.get("vwap"),
            )

        # Fallback: intraday levels (works for indices + futures).
        intra = t.get_intraday_levels(sym, timeframe=timeframe.lower())
        if intra.get("error"):
            raise HTTPException(status_code=404, detail=intra["error"])

        ema_levels = intra.get("ema_levels", {})
        supports = intra.get("supports", [])
        resistances = intra.get("resistances", [])

        return KeyLevels(
            ema20=ema_levels.get("ema9") or ema_levels.get("ema20"),   # map ema9 → ema20 slot
            ema50=ema_levels.get("ema21") or ema_levels.get("ema50"),
            ema100=None,
            ema200=ema_levels.get("ema200"),
            supertrend=None,
            supertrend_direction=None,
            support=supports[0] if supports else None,
            resistance=resistances[0] if resistances else None,
            vwap=intra.get("pivot"),   # pivot ≈ VWAP proxy for intraday
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── OHLCV bars ────────────────────────────────────────────────────────────────

# Bars per trading day for each intraday timeframe (NSE: 9:15–15:30 = 375 min).
_BARS_PER_DAY = {"1m": 375, "3m": 125, "5m": 75, "10m": 38, "15m": 25, "30m": 13, "1h": 7, "60m": 7}
_DEFAULT_DAYS = 10  # how many trading days to show by default for intraday TFs

@router.get("/ohlcv")
async def get_ohlcv(
    symbol: str = Query(..., description="NSE/BSE symbol, e.g. RELIANCE or BANKNIFTY"),
    exchange: str = Query("NSE"),
    timeframe: str = Query("1D"),
    limit: int = Query(200, ge=1, le=1000),
):
    """Return OHLCV bars from PostgreSQL (intraday) or price history (EOD).
    
    Bars use UNIX timestamp (seconds) — compatible with lightweight-charts.
    For 1D/1W/1M when no EOD data exists, falls back to aggregated daily bars.
    """
    t = _tools()
    sym = symbol.strip().upper()
    INTRADAY_TF = {"1m", "3m", "5m", "10m", "15m", "30m", "1h", "60m"}
    is_intraday = timeframe.lower() in INTRADAY_TF

    try:
        import pandas as pd
        import datetime as _dt
        from collections import defaultdict as _dd

        # Normalise lookback: for intraday, use _DEFAULT_DAYS × bars/day so all TFs
        # show the same TIME WINDOW (prevents jarring range jump when switching TF).
        if is_intraday:
            bars_per_day = _BARS_PER_DAY.get(timeframe.lower(), 75)
            safe_lookback = bars_per_day * _DEFAULT_DAYS
        else:
            safe_lookback = max(limit, 1)

        result = (
            t.get_intraday_bars(sym, timeframe=timeframe.lower(), lookback=safe_lookback)
            if is_intraday
            else t.get_symbol_snapshot(sym)
        )

        # EOD failed (index / no daily history) → fall back + aggregate to daily.
        if not is_intraday and (result.get("error") or not result.get("bars")):
            result = t.get_intraday_bars(sym, timeframe="5m", lookback=1000)

        if result.get("error") and not result.get("bars"):
            raise HTTPException(status_code=404, detail=result["error"])

        raw_bars = result.get("bars", [])

        # For EOD timeframes that fell back to intraday, aggregate to daily OHLCV.
        if not is_intraday and raw_bars:
            sample_ts = str(raw_bars[0].get("timestamp") or raw_bars[0].get("time") or "")
            if ":" in sample_ts:  # has time component → intraday, needs aggregation
                daily: dict = _dd(lambda: {"open": None, "high": None, "low": None, "close": None, "volume": 0})
                for b in sorted(raw_bars, key=lambda x: str(x.get("timestamp") or "")):
                    ts_str = str(b.get("timestamp") or b.get("time") or "")
                    try:
                        day_key = ts_str[:10]  # "YYYY-MM-DD"
                        if daily[day_key]["open"] is None:
                            daily[day_key]["open"] = float(b.get("open", 0))
                        daily[day_key]["high"] = max(daily[day_key]["high"] or 0, float(b.get("high", 0)))
                        daily[day_key]["low"] = min(daily[day_key]["low"] or 1e9, float(b.get("low", 0)))
                        daily[day_key]["close"] = float(b.get("close", 0))
                        daily[day_key]["volume"] = int(daily[day_key]["volume"]) + int(b.get("volume") or 0)
                    except Exception:
                        pass
                agg = []
                for day_str in sorted(daily.keys()):
                    d = daily[day_str]
                    if d["open"] is None:
                        continue
                    # Midnight UTC of that date as Unix timestamp.
                    day_dt = _dt.datetime.strptime(day_str, "%Y-%m-%d").replace(tzinfo=_dt.timezone.utc)
                    agg.append({
                        "time": int(day_dt.timestamp()),
                        "open": d["open"], "high": d["high"], "low": d["low"],
                        "close": d["close"], "volume": d["volume"],
                    })
                return {
                    "symbol": sym, "exchange": exchange, "timeframe": timeframe,
                    "source": result.get("source", "agent_adda") + " (daily aggregated)",
                    "bars": agg[-limit:],
                }

        bars = []
        for b in raw_bars:
            ts = b.get("timestamp") or b.get("time") or b.get("date")
            if ts is None:
                continue
            bars.append({
                "time":   int(pd.to_datetime(ts).timestamp()),
                "open":   float(b.get("open", 0)),
                "high":   float(b.get("high", 0)),
                "low":    float(b.get("low", 0)),
                "close":  float(b.get("close", 0)),
                "volume": int(b.get("volume", 0)),
            })

        return {
            "symbol": sym,
            "exchange": exchange,
            "timeframe": timeframe,
            "source": result.get("source", "agent_adda"),
            "bars": sorted(bars, key=lambda x: x["time"])[-limit:],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Technical snapshot ────────────────────────────────────────────────────────

@router.get("/snapshot")
async def get_technical_snapshot(
    symbol: str = Query(...),
    exchange: str = Query("NSE"),
):
    """Return combined EOD summary + indicator values for the symbol."""
    t = _tools()
    sym = symbol.strip().upper()
    try:
        snap = t.get_symbol_snapshot(sym)
        tech = t.get_technical_setup(sym)
        if snap.get("error") and tech.get("error"):
            raise HTTPException(status_code=404, detail=snap.get("error", "Symbol not found"))
        return {"symbol": sym, "exchange": exchange, "snapshot": snap, "technicals": tech}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
