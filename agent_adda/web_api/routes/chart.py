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
    """Lazy import terminal.tools so the API can start without fully loading the app."""
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    os.environ.setdefault("AGENT_ADDA_SKIP_VENV_CHECK", "1")
    import terminal.tools as t
    return t


# ── Key levels ────────────────────────────────────────────────────────────────

@router.get("/levels", response_model=KeyLevels)
async def get_key_levels(
    symbol: str = Query(..., description="NSE/BSE symbol, e.g. RELIANCE"),
    exchange: str = Query("NSE"),
    timeframe: str = Query("5m"),
):
    """Return PG-sourced key levels for the given symbol/timeframe."""
    t = _tools()
    sym = symbol.strip().upper()
    try:
        snap = t.get_technical_setup(sym)
        if snap.get("error"):
            raise HTTPException(status_code=404, detail=snap["error"])
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
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── OHLCV bars ────────────────────────────────────────────────────────────────

@router.get("/ohlcv")
async def get_ohlcv(
    symbol: str = Query(..., description="NSE/BSE symbol, e.g. RELIANCE or BANKNIFTY"),
    exchange: str = Query("NSE"),
    timeframe: str = Query("1D"),
    limit: int = Query(200, ge=10, le=1000),
):
    """Return OHLCV bars from PostgreSQL.

    Bars use UNIX timestamp (seconds) for time — compatible with lightweight-charts.
    """
    t = _tools()
    sym = symbol.strip().upper()
    INTRADAY_TF = {"1m", "3m", "5m", "10m", "15m", "30m", "1h", "60m"}
    is_intraday = timeframe.lower() in INTRADAY_TF
    try:
        result = (
            t.get_intraday_bars(sym, timeframe=timeframe.lower(), lookback=limit)
            if is_intraday
            else t.get_symbol_snapshot(sym)
        )
        if result.get("error") and not result.get("bars"):
            raise HTTPException(status_code=404, detail=result["error"])

        import pandas as pd
        bars = []
        for b in result.get("bars", []):
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
            "bars": bars[-limit:],
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
