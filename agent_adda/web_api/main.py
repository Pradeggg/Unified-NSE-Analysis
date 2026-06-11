"""Agent Adda — Web API (FastAPI) for browser plugin and web app.

Start with:
    AGENT_ADDA_SKIP_VENV_CHECK=1 .venv/bin/python3 -m agent_adda.web_api.main

Serves on http://localhost:8765
"""
from __future__ import annotations

import os
from pathlib import Path

# Load .env from repo root so all routes (including backtest PG persist) have env vars
_env_file = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_file.exists() and not os.environ.get("PG_DSN"):
    try:
        with open(_env_file) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _, _v = _line.partition("=")
                    os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
    except Exception:
        pass

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware

from .routes import analysis, backtest, chart, patterns, health, symbols

app = FastAPI(
    title="Agent Adda Web API",
    version="0.1.0",
    description="Local API for Agent Adda browser plugin and web charting workbench.",
)

# CORS: allow the browser extension origin (chrome-extension://*) and localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:*",
        "http://127.0.0.1:*",
        # Chrome extensions send requests as chrome-extension://<id>
        # We allow all origins for local-only deployments.
        "*",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health.router,   prefix="/api")
app.include_router(symbols.router,  prefix="/api/symbols",  tags=["symbols"])
app.include_router(chart.router,    prefix="/api/chart",    tags=["chart"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(patterns.router,  prefix="/api/patterns",  tags=["patterns"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["backtest"])


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("AGENT_ADDA_WEB_PORT", "8765"))
    uvicorn.run("agent_adda.web_api.main:app", host="127.0.0.1", port=port, reload=True)
