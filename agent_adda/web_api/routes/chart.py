"""Chart data routes — OHLCV, key levels, technical snapshots from PostgreSQL."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from ..schemas import KeyLevels

router = APIRouter()


@router.get("/levels", response_model=KeyLevels)
async def get_key_levels(
    symbol: str = Query(...),
    exchange: str = Query("NSE"),
    timeframe: str = Query("5m"),
):
    """Return PG-sourced key levels for the given symbol/timeframe."""
    try:
        import os, sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
        os.environ.setdefault("AGENT_ADDA_SKIP_VENV_CHECK", "1")
        from terminal.tools import call_tool

        snap = call_tool("get_technical_setup", {"symbol": symbol.upper()})
        if snap.get("error"):
            raise HTTPException(status_code=404, detail=snap["error"])

        levels = KeyLevels(
            ema20=snap.get("ema20"),
            ema50=snap.get("ema50"),
            ema100=snap.get("ema100"),
            ema200=snap.get("ema200"),
            supertrend=snap.get("supertrend"),
            supertrend_direction="bullish" if snap.get("supertrend_signal") == "BUY" else
                                 "bearish" if snap.get("supertrend_signal") == "SELL" else None,
            support=snap.get("support"),
            resistance=snap.get("resistance"),
        )
        return levels
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/ohlcv")
async def get_ohlcv(
    symbol: str = Query(...),
    exchange: str = Query("NSE"),
    timeframe: str = Query("1D"),
    limit: int = Query(200),
):
    """Return OHLCV bars from PostgreSQL for the given symbol/timeframe."""
    try:
        import os, sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
        os.environ.setdefault("AGENT_ADDA_SKIP_VENV_CHECK", "1")
        from terminal.tools import call_tool

        result = call_tool("get_symbol_snapshot", {"symbol": symbol.upper()})
        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])

        return {"symbol": symbol.upper(), "exchange": exchange, "timeframe": timeframe, "data": result}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
