#!/usr/bin/env python3
"""
Shared Ollama narrative generation (no FastAPI). Used by narrative_llm_server and narrative_pipeline_runner.

Prompts request a single JSON object (no markdown fences) so the HTML dashboard can render structured sections.
"""

from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
FUND_CSV = DATA_DIR / "fundamental_scores_database.csv"


def ollama_chat(
    messages: list[dict[str, str]],
    *,
    timeout_s: int = 480,
    ollama_base: Optional[str] = None,
    ollama_model: Optional[str] = None,
) -> str:
    """POST /api/chat to local Ollama; return assistant text. Raises RuntimeError if unreachable or bad response."""
    base = (ollama_base or os.environ.get("OLLAMA_BASE", "http://127.0.0.1:11434")).rstrip("/")
    model = ollama_model or os.environ.get("OLLAMA_MODEL", "granite4")
    url = f"{base}/api/chat"
    body = json.dumps({"model": model, "messages": messages, "stream": False}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama unreachable at {base}: {e}") from e
    msg = data.get("message") or {}
    content = msg.get("content")
    if not content:
        raise RuntimeError(f"Unexpected Ollama response: {data!r}")
    return str(content).strip()


def build_market_context(conn: sqlite3.Connection, analysis_date: str) -> dict[str, Any]:
    """Pull index rows + market breadth + signal mix for the prompt."""
    out: dict[str, Any] = {"analysis_date": analysis_date}
    try:
        idx = pd.read_sql_query(
            "SELECT * FROM index_analysis WHERE analysis_date = ? ORDER BY technical_score DESC",
            conn,
            params=(analysis_date,),
        )
        out["indices"] = idx.to_dict(orient="records") if not idx.empty else []
    except Exception:
        out["indices"] = []
    try:
        br = pd.read_sql_query(
            "SELECT * FROM market_breadth WHERE analysis_date = ? LIMIT 1",
            conn,
            params=(analysis_date,),
        )
        out["market_breadth"] = br.iloc[0].to_dict() if len(br) else {}
    except Exception:
        out["market_breadth"] = {}
    try:
        sig = pd.read_sql_query(
            """
            SELECT trading_signal AS signal, COUNT(*) AS n
            FROM stocks_analysis
            WHERE analysis_date = ?
            GROUP BY trading_signal
            """,
            conn,
            params=(analysis_date,),
        )
        out["signal_counts"] = sig.to_dict(orient="records") if not sig.empty else []
    except Exception:
        out["signal_counts"] = []
    return out


def build_stock_context(conn: sqlite3.Connection, analysis_date: str, symbol: str) -> dict[str, Any]:
    sym = symbol.strip().upper()
    out: dict[str, Any] = {"analysis_date": analysis_date, "symbol": sym}
    try:
        st = pd.read_sql_query(
            """
            SELECT * FROM stocks_analysis
            WHERE analysis_date = ? AND UPPER(symbol) = ?
            LIMIT 1
            """,
            conn,
            params=(analysis_date, sym),
        )
        out["stock_row"] = st.iloc[0].to_dict() if len(st) else {}
    except Exception:
        out["stock_row"] = {}
    try:
        nifty = pd.read_sql_query(
            """
            SELECT * FROM index_analysis
            WHERE analysis_date = ?
              AND (UPPER(index_name) LIKE '%NIFTY 50%' OR UPPER(index_name) LIKE '%NIFTY50%'
                   OR index_name = 'NIFTY 50')
            LIMIT 1
            """,
            conn,
            params=(analysis_date,),
        )
        if nifty.empty:
            nifty = pd.read_sql_query(
                "SELECT * FROM index_analysis WHERE analysis_date = ? ORDER BY technical_score DESC LIMIT 1",
                conn,
                params=(analysis_date,),
            )
        out["benchmark_index"] = nifty.iloc[0].to_dict() if len(nifty) else {}
    except Exception:
        out["benchmark_index"] = {}
    out["market_breadth"] = build_market_context(conn, analysis_date).get("market_breadth", {})
    out["fundamental_csv"] = {}
    if FUND_CSV.exists():
        try:
            fund = pd.read_csv(FUND_CSV, low_memory=False)
            scol = None
            for c in fund.columns:
                if str(c).upper() == "SYMBOL":
                    scol = c
                    break
            if scol:
                m = fund[fund[scol].astype(str).str.strip().str.upper() == sym]
                if len(m):
                    out["fundamental_csv"] = m.iloc[0].fillna("").to_dict()
        except Exception:
            pass
    out["yahoo_snippet"] = yahoo_finance_snippet(sym)
    return out


def yahoo_finance_snippet(symbol: str) -> dict[str, Any]:
    try:
        import yfinance as yf  # type: ignore
    except ImportError:
        return {"available": False, "note": "yfinance not installed (pip install yfinance)"}
    for suffix in (".NS", ".BO", ""):
        tkr = f"{symbol}{suffix}" if suffix else symbol
        try:
            t = yf.Ticker(tkr)
            news = getattr(t, "news", None) or []
            headlines = []
            for n in news[:12]:
                if isinstance(n, dict):
                    headlines.append(
                        {"title": n.get("title", "")[:200], "publisher": n.get("publisher", "")}
                    )
            info = {}
            try:
                inf = t.info or {}
                for k in ("longName", "shortName", "sector", "industry", "averageAnalystRating", "recommendationKey"):
                    v = inf.get(k)
                    if v is not None and v != "":
                        info[k] = v
            except Exception:
                pass
            if headlines or info:
                return {"available": True, "ticker_try": tkr, "headlines": headlines, "info": info}
        except Exception:
            continue
    return {"available": False, "note": "No Yahoo data for symbol variants tried"}


def quarterly_financial_snippet(symbol: str) -> dict[str, Any]:
    try:
        import yfinance as yf  # type: ignore
    except ImportError:
        return {"available": False}
    for suffix in (".NS", ".BO"):
        tkr = f"{symbol}{suffix}"
        try:
            t = yf.Ticker(tkr)
            q_inc = getattr(t, "quarterly_income_stmt", None)
            if q_inc is None or q_inc.empty:
                q_inc = getattr(t, "quarterly_financials", None)
            if q_inc is None or q_inc.empty:
                continue
            df = q_inc.copy()
            nq = min(3, df.shape[1])
            cols = list(df.columns[:nq])
            rows_keep = []
            keys = ("TOTAL REVENUE", "REVENUE", "NET INCOME", "EBITDA", "EPS", "DILUTED", "MARGIN", "GROSS PROFIT")
            for label in df.index:
                lu = str(label).upper()
                if any(k in lu for k in keys):
                    rows_keep.append(label)
            slim = df.loc[rows_keep[:25], cols] if rows_keep else df.iloc[:, :nq]
            records: list[dict[str, Any]] = []
            for col in cols:
                ser = slim[col]
                records.append(
                    {
                        "period": str(col)[:32],
                        "metrics": {
                            str(i): (
                                float(v)
                                if pd.notna(v) and isinstance(v, (int, float))
                                else str(v)[:40]
                            )
                            for i, v in ser.items()
                        },
                    }
                )
            return {"available": True, "ticker_try": tkr, "last_quarters": records}
        except Exception:
            continue
    return {"available": False}


MARKET_SYSTEM_PROMPT = (
    "You are an equity market analyst for Indian markets (NSE). "
    "Respond with ONLY a single valid JSON object — no markdown, no code fences, no text before or after the JSON. "
    'Use exactly these string keys: "analysis_date", "overall_sentiment", "breadth_analysis", "index_tone", "summary". '
    "Set analysis_date to the date from the context. "
    "overall_sentiment: one short label (e.g. Bullish, Bearish, Mixed). "
    "breadth_analysis, index_tone, summary: prose suitable for investors. "
    "Use only facts from the provided context JSON; do not invent numbers. If data is missing, say so in the relevant field."
)

STOCK_SYSTEM_PROMPT = (
    "You are a senior equity analyst covering NSE stocks. "
    "Respond with ONLY a single valid JSON object — no markdown, no code fences, no text before or after the JSON. "
    'Use exactly these string keys: "analysis_date", "symbol", "headline_view", "technical_summary", '
    '"fundamental_summary", "quarterly_trends", "yahoo_context", "summary". '
    "Set analysis_date and symbol from the context. "
    "Place the heaviest emphasis in quarterly_trends on the last 3 quarters: revenue/sales, EBITDA, margins, EPS — "
    "using quarterly_financials and fundamental_csv when present. "
    "yahoo_context: brief read of headlines/sentiment as soft context, not hard facts. "
    "Do not invent figures; state uncertainty if needed."
)


def synthesize_market_narrative(
    conn: sqlite3.Connection,
    analysis_date: str,
    *,
    ollama_base: Optional[str] = None,
    ollama_model: Optional[str] = None,
) -> tuple[str, dict[str, Any]]:
    ctx = build_market_context(conn, analysis_date)
    user = "Context (JSON):\n" + json.dumps(ctx, ensure_ascii=False, default=str)[:120000]
    text = ollama_chat(
        [
            {"role": "system", "content": MARKET_SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        ollama_base=ollama_base,
        ollama_model=ollama_model,
    )
    return text, ctx


def synthesize_stock_narrative(
    conn: sqlite3.Connection,
    analysis_date: str,
    symbol: str,
    *,
    ollama_base: Optional[str] = None,
    ollama_model: Optional[str] = None,
) -> tuple[str, dict[str, Any]]:
    sym = symbol.strip().upper()
    ctx = build_stock_context(conn, analysis_date, sym)
    ctx["quarterly_financials"] = quarterly_financial_snippet(sym)
    user = "Context (JSON):\n" + json.dumps(ctx, ensure_ascii=False, default=str)[:120000]
    text = ollama_chat(
        [
            {"role": "system", "content": STOCK_SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        ollama_base=ollama_base,
        ollama_model=ollama_model,
    )
    store_ctx = dict(ctx)
    if isinstance(store_ctx.get("yahoo_snippet"), dict):
        ys = store_ctx["yahoo_snippet"]
        if "headlines" in ys and len(ys["headlines"]) > 6:
            ys = {**ys, "headlines": ys["headlines"][:6]}
        store_ctx["yahoo_snippet"] = ys
    return text, store_ctx
