"""Symbol search and metadata routes."""
from __future__ import annotations

import csv
import os
from pathlib import Path
import sys

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

_HERE = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_ROOT_PATH = Path(_REPO_ROOT)


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


def _add_symbol(
    rows: dict[str, dict],
    symbol: object,
    *,
    name: object = "",
    score: float = 1.0,
) -> None:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return
    clean = "".join(ch for ch in sym if ch.isalnum() or ch in {"&", "-"})
    if not clean:
        return
    existing = rows.get(clean)
    label = str(name or "").strip()
    if existing:
        if label and not existing.get("name"):
            existing["name"] = label
        existing["score"] = max(float(existing.get("score") or 0), score)
        return
    rows[clean] = {"symbol": clean, "name": label, "score": score}


def _merge_pg_stage_snapshot(rows: dict[str, dict]) -> None:
    try:
        import psycopg2
        import psycopg2.extras
    except Exception:
        return

    dsn = (
        os.environ.get("AGENT_ADDA_PG_DSN")
        or os.environ.get("PG_DSN")
        or "dbname=nse_market user=nse_admin host=/tmp"
    )
    try:
        with psycopg2.connect(dsn, connect_timeout=2) as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT symbol, COALESCE(company_name, '') AS company_name
                FROM scores.stage_snapshots
                WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM scores.stage_snapshots)
                ORDER BY symbol
                """
            )
            for row in cur.fetchall():
                _add_symbol(rows, row["symbol"], name=row["company_name"], score=0.95)
    except Exception:
        return


def _merge_local_csv_universe(rows: dict[str, dict]) -> None:
    csv_paths = [
        _ROOT_PATH / "data" / "nse_sec_full_data.csv",
        _ROOT_PATH / "data" / "signal_log.csv",
        _ROOT_PATH / "data" / "fno_signals.csv",
    ]
    for path in csv_paths:
        if not path.exists():
            continue
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    _add_symbol(
                        rows,
                        row.get("SYMBOL") or row.get("symbol"),
                        name=row.get("company") or row.get("company_name") or "",
                        score=0.75,
                    )
        except Exception:
            continue

    profiles = _ROOT_PATH / "data" / "company_profiles"
    if profiles.exists():
        for path in profiles.glob("*.json"):
            _add_symbol(rows, path.name.split(".")[0], score=0.7)


def _universe_candidates(limit: int) -> list[dict]:
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    from terminal.live_intraday_alerts import load_fno_intraday_universe

    rows: dict[str, dict] = {}
    for symbol in load_fno_intraday_universe():
        _add_symbol(rows, symbol, score=1.0)
    _merge_pg_stage_snapshot(rows)
    _merge_local_csv_universe(rows)
    return sorted(rows.values(), key=lambda row: (-float(row.get("score") or 0), row["symbol"]))[:limit]


@router.get("/universe")
async def get_symbol_universe(
    limit: int = Query(1500, ge=1, le=3000),
):
    """Return the default NSE/F&O symbol universe used by live intraday tracking."""
    try:
        results = _universe_candidates(limit)
        return {"query": "", "results": results, "count": len(results)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


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
