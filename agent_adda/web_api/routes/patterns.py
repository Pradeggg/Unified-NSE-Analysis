"""Pattern detection routes — wraps K13 engine for chart analysis."""
from __future__ import annotations

import uuid
from datetime import datetime
from fastapi import APIRouter, Query, HTTPException
from ..schemas import PatternFinding, PatternStatus

router = APIRouter()


@router.get("/query")
async def query_patterns(
    symbol: str = Query(...),
    exchange: str = Query("NSE"),
    timeframe: str = Query("5m"),
):
    """Return K13 pattern findings for the given symbol/timeframe.
    
    Falls back gracefully when K13 engine is unavailable.
    """
    try:
        import os, sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
        os.environ.setdefault("AGENT_ADDA_SKIP_VENV_CHECK", "1")

        # Attempt to import and call K13 pattern detector.
        # K13 is not yet implemented; return engine_unavailable gracefully.
        try:
            from backtesting.strategies.patterns import detect_patterns  # type: ignore
            findings_raw = detect_patterns(symbol.upper(), timeframe=timeframe)
            patterns = [PatternFinding(**f) for f in (findings_raw or [])]
        except ImportError:
            # K13 not yet available — return placeholder.
            patterns = [
                PatternFinding(
                    pattern_type="K13 engine not yet available",
                    status="engine_unavailable",
                    detected_at=datetime.utcnow().isoformat(),
                )
            ]

        return {"symbol": symbol.upper(), "exchange": exchange, "timeframe": timeframe, "patterns": patterns}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
