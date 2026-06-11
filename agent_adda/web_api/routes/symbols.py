"""Symbol search and metadata routes."""
from __future__ import annotations

import os
import sys

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

_HERE = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))


def _tools():
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    os.environ.setdefault("AGENT_ADDA_SKIP_VENV_CHECK", "1")
    import terminal.tools as t
    return t


def _normalise_candidates(result: dict) -> list[dict]:
    """Normalise resolve_symbol candidates to [{symbol, name, score}] list."""
    raw = result.get("candidates", [])
    out = []
    for c in raw:
        if isinstance(c, dict):
            out.append({"symbol": c.get("symbol", ""), "name": c.get("name", ""), "score": c.get("score", 0.5)})
        elif isinstance(c, str):
            # Single string candidate — use top-level score if available.
            out.append({"symbol": c, "name": "", "score": result.get("score", 0.5)})
    if not out and result.get("symbol"):
        out.append({"symbol": result["symbol"], "name": result.get("name", ""), "score": result.get("score", 1.0)})
    return out


@router.get("/search")
async def search_symbols(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
):
    """Resolve a query to matching NSE/BSE symbols."""
    t = _tools()
    try:
        result = t.resolve_symbol(q.strip())
        if result.get("error"):
            return {"query": q, "results": [], "error": result["error"]}
        return {"query": q, "results": _normalise_candidates(result)[:limit]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{symbol}")
async def get_symbol_info(symbol: str):
    """Return basic metadata for a symbol."""
    t = _tools()
    sym = symbol.strip().upper()
    try:
        snap = t.get_symbol_snapshot(sym)
        if snap.get("error"):
            raise HTTPException(status_code=404, detail=snap["error"])
        return {
            "symbol":     snap.get("symbol", sym),
            "name":       snap.get("company_name") or snap.get("name", ""),
            "sector":     snap.get("sector", ""),
            "industry":   snap.get("industry", ""),
            "exchange":   snap.get("exchange", "NSE"),
            "stage":      snap.get("stage"),
            "rs_rank":    snap.get("rs_rank"),
            "market_cap": snap.get("market_cap_cr"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
