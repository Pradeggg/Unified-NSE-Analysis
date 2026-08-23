"""Agent Adda — Web API (FastAPI) for browser plugin and web app.

Start with:
    AGENT_ADDA_SKIP_VENV_CHECK=1 .venv/bin/python3 -m agent_adda.web_api.main

Serves on http://localhost:8765
"""
from __future__ import annotations

import os
from pathlib import Path

# Load .env from repo root, then parent workspace. Values already set in the
# shell wins; .env only fills missing keys such as OPENAI_API_KEY or PG_DSN.
_repo_root = Path(__file__).resolve().parent.parent.parent
for _env_file in (_repo_root / ".env", _repo_root.parent / ".env"):
    if not _env_file.exists():
        continue
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
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from .routes import analysis, backtest, chart, patterns, health, symbols, fno, ric, talk

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
app.include_router(fno.router,      prefix="/api/fno",       tags=["fno"])
app.include_router(ric.router,      prefix="/api/ric",       tags=["ric"])
app.include_router(talk.router,     prefix="/api/talk",      tags=["talk"])


@app.get("/", response_class=HTMLResponse)
@app.get("/talk-2-stocks", response_class=HTMLResponse)
async def talk_2_stocks_app():
    static_file = Path(__file__).resolve().parent / "static" / "talk_2_stocks.html"
    if not static_file.exists():
        raise HTTPException(status_code=404, detail="Talk 2 Stocks app not found")
    return HTMLResponse(static_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("AGENT_ADDA_WEB_PORT", "8765"))
    uvicorn.run("agent_adda.web_api.main:app", host="127.0.0.1", port=port, reload=True)
