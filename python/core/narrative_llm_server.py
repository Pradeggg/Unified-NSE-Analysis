#!/usr/bin/env python3
"""
Local FastAPI service: Ollama narratives persisted in SQLite (llm_narratives).

Generation logic lives in narrative_llm_core.py (also used by narrative_pipeline_runner.py).

Usage:
  pip install fastapi uvicorn pandas
  export OLLAMA_MODEL=granite4
  uvicorn narrative_llm_server:app --host 127.0.0.1 --port 8765 --app-dir python/core
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from narrative_db import DEFAULT_DB_PATH, connect_db, get_latest_analysis_date, get_narrative, upsert_narrative
from narrative_llm_core import synthesize_market_narrative, synthesize_stock_narrative

OLLAMA_BASE = os.environ.get("OLLAMA_BASE", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "granite4")
DB_PATH = Path(os.environ.get("NSE_DB_PATH", str(DEFAULT_DB_PATH)))

app = FastAPI(title="NSE LLM Narratives", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("NARRATIVE_CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "ollama_base": OLLAMA_BASE, "model": OLLAMA_MODEL, "db": str(DB_PATH)}


@app.get("/api/market-narrative")
def market_narrative(
    analysis_date: Optional[str] = Query(None, description="YYYY-MM-DD; default = latest in DB"),
    refresh: bool = Query(False, description="If true, regenerate via Ollama and upsert SQLite"),
) -> dict[str, Any]:
    conn = connect_db(DB_PATH)
    try:
        ad = analysis_date or get_latest_analysis_date(conn)
        if not ad:
            raise HTTPException(status_code=404, detail="No stocks_analysis dates in database.")
        if not refresh:
            row = get_narrative(conn, "market", ad, "")
            if row:
                return {
                    "cached": True,
                    "analysis_date": ad,
                    "ollama_model": row["ollama_model"],
                    "content": row["content"],
                    "updated_at": row["updated_at"],
                }
        try:
            text, ctx = synthesize_market_narrative(conn, ad, ollama_base=OLLAMA_BASE, ollama_model=OLLAMA_MODEL)
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        upsert_narrative(conn, "market", ad, "", OLLAMA_MODEL, text, context_obj=ctx)
        return {
            "cached": False,
            "analysis_date": ad,
            "ollama_model": OLLAMA_MODEL,
            "content": text,
        }
    finally:
        conn.close()


@app.get("/api/stock-narrative")
def stock_narrative(
    symbol: str = Query(..., min_length=1, max_length=32),
    analysis_date: Optional[str] = Query(None),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    conn = connect_db(DB_PATH)
    try:
        ad = analysis_date or get_latest_analysis_date(conn)
        if not ad:
            raise HTTPException(status_code=404, detail="No stocks_analysis dates in database.")
        sym = symbol.strip().upper()
        if not refresh:
            row = get_narrative(conn, "stock", ad, sym)
            if row:
                return {
                    "cached": True,
                    "analysis_date": ad,
                    "symbol": sym,
                    "ollama_model": row["ollama_model"],
                    "content": row["content"],
                    "updated_at": row["updated_at"],
                }
        try:
            text, store_ctx = synthesize_stock_narrative(
                conn, ad, sym, ollama_base=OLLAMA_BASE, ollama_model=OLLAMA_MODEL
            )
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        upsert_narrative(conn, "stock", ad, sym, OLLAMA_MODEL, text, context_obj=store_ctx)
        return {
            "cached": False,
            "analysis_date": ad,
            "symbol": sym,
            "ollama_model": OLLAMA_MODEL,
            "content": text,
        }
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8765")), reload=False)
