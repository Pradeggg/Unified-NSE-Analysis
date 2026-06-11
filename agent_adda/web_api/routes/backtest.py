"""Intraday backtest route — walk OHLCV history with existing signal functions."""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter()


class _NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        try:
            import numpy as np
            if isinstance(obj, (np.integer,)): return int(obj)
            if isinstance(obj, (np.floating,)): return float(obj)
            if isinstance(obj, np.ndarray): return obj.tolist()
        except ImportError:
            pass
        return super().default(obj)


def _dumps(obj) -> str:
    return json.dumps(obj, cls=_NumpyEncoder)

_HERE      = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))


def _pg():
    """Return a psycopg2 connection using PG_DSN from environment."""
    import psycopg2
    dsn = os.environ.get("PG_DSN", "")
    if not dsn:
        raise RuntimeError("PG_DSN not set")
    return psycopg2.connect(dsn)


def _options_score(m: dict, trades: int) -> float:
    if trades < 3:
        return -999.0
    return round(
        m["win_rate"] * 0.5
        + m["sharpe"] * 25
        + m["return_pct"] * 0.5
        - m["max_drawdown_pct"] * 0.4,
        2,
    )


def _persist_run(sym: str, req, strategy_name: str, bars_used: int,
                 metrics: dict, trades: list, equity: list) -> int | None:
    """Insert run into backtesting.strategy_runs; return new row id."""
    try:
        # Cast all metric values to native Python types (psycopg2 rejects np.float64)
        def _f(v):
            try: return float(v)
            except: return None
        def _i(v):
            try: return int(v)
            except: return None

        score = _options_score(metrics, metrics.get("total_trades", 0))
        conn  = _pg()
        cur   = conn.cursor()
        cur.execute("""
            INSERT INTO backtesting.strategy_runs
                (symbol, timeframe, strategy_id, strategy_name,
                 initial_capital, risk_pct, max_hold_bars, bars_used,
                 total_trades, wins, losses, win_rate,
                 total_pnl, return_pct, avg_pnl, avg_win, avg_loss,
                 max_drawdown_pct, sharpe, options_score,
                 trades_json, equity_json)
            VALUES (%s,%s,%s,%s, %s,%s,%s,%s, %s,%s,%s,%s,
                    %s,%s,%s,%s,%s, %s,%s,%s, %s,%s)
            RETURNING id
        """, (
            sym, req.timeframe, req.strategy, strategy_name,
            _f(req.initial_capital), _f(req.risk_per_trade_pct), _i(req.max_holding_bars), _i(bars_used),
            _i(metrics["total_trades"]), _i(metrics["wins"]), _i(metrics["losses"]), _f(metrics["win_rate"]),
            _f(metrics["total_pnl"]), _f(metrics["return_pct"]), _f(metrics["avg_pnl"]),
            _f(metrics["avg_win"]), _f(metrics["avg_loss"]),
            _f(metrics["max_drawdown_pct"]), _f(metrics["sharpe"]), _f(score),
            json.dumps(trades, cls=_NumpyEncoder), json.dumps(equity, cls=_NumpyEncoder),
        ))
        row_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        return row_id
    except Exception as _exc:
        import traceback as _tb
        print(f"[backtest persist error] {_exc}")
        return None

# ── Available strategies ──────────────────────────────────────────────────────

STRATEGIES = [
    # ── Original ──────────────────────────────────────────────────────────────
    {"id": "macd",                 "name": "MACD Crossover",           "min_bars": 35},
    {"id": "rsi",                  "name": "RSI Reversal",             "min_bars": 25},
    {"id": "ema_crossover",        "name": "EMA 9/21 Crossover",       "min_bars": 60},
    {"id": "supertrend",           "name": "Supertrend",               "min_bars": 25},
    {"id": "bollinger",            "name": "Bollinger Band Bounce",    "min_bars": 25},
    {"id": "vwap",                 "name": "VWAP Bounce",              "min_bars": 20},
    {"id": "orb",                  "name": "ORB Breakout",             "min_bars": 15},
    {"id": "ema_ribbon",           "name": "EMA Ribbon",               "min_bars": 60},
    {"id": "volume_spike",         "name": "Volume Spike",             "min_bars": 25},
    {"id": "engulfing",            "name": "Engulfing Candle",         "min_bars": 15},
    # ── New ───────────────────────────────────────────────────────────────────
    {"id": "vcp",                  "name": "VCP Breakout",             "min_bars": 40},
    {"id": "darvas",               "name": "Darvas Box Breakout",      "min_bars": 25},
    {"id": "supertrend_breakout",  "name": "Supertrend Flip",          "min_bars": 30},
    {"id": "volume_profile",       "name": "Volume Profile POC",       "min_bars": 30},
    {"id": "positional",           "name": "Positional EMA Bounce",    "min_bars": 60},
    {"id": "orb_vwap",             "name": "ORB + VWAP Confluence",    "min_bars": 15},
    {"id": "rsi_divergence",       "name": "RSI Divergence",           "min_bars": 30},
    {"id": "multi_confirm",        "name": "Multi-Confirm",            "min_bars": 50},
]

_STRATEGY_IDS = {s["id"] for s in STRATEGIES}


def _intraday():
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    os.environ.setdefault("AGENT_ADDA_SKIP_VENV_CHECK", "1")
    import terminal.intraday as intraday
    return intraday


# ── Request / response models ─────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    symbol:             str   = Field(..., description="NSE symbol, e.g. BANKNIFTY")
    timeframe:          str   = Field("5m", description="Intraday TF: 1m, 5m, 15m, 30m")
    strategy:           str   = Field("macd", description="Strategy id from /list")
    initial_capital:    float = Field(100_000, ge=10_000, le=10_000_000)
    risk_per_trade_pct: float = Field(1.0, ge=0.1, le=10.0,
                                      description="% of capital risked per trade (SL distance × qty)")
    max_holding_bars:   int   = Field(20, ge=1, le=200,
                                      description="Exit trade after this many bars if SL/Target not hit")


# ── Core backtest walker ──────────────────────────────────────────────────────

def _walk(df_raw, signal_fn, initial_capital: float, risk_pct: float, max_hold: int):
    """Walk OHLCV DataFrame bar-by-bar, apply signal_fn on each slice."""
    import pandas as pd

    df = df_raw.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    # Rename to match signal functions' expectations
    renames = {"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume",
               "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    df = df.rename(columns={k: v for k, v in renames.items() if k in df.columns})

    # Attach unix timestamps (stored in the index or a column)
    ts_col = [c for c in df_raw.columns if c.lower() in ("timestamp","time","date","dt")]
    if ts_col:
        df["_ts"] = pd.to_datetime(df_raw[ts_col[0]], errors="coerce")
    elif hasattr(df.index, "to_pydatetime"):
        df["_ts"] = df.index

    required = {"Open", "High", "Low", "Close"}
    if not required.issubset(df.columns):
        raise ValueError(f"DataFrame missing columns: {required - set(df.columns)}")

    capital    = initial_capital
    equity     = [{"time": None, "value": round(capital, 2)}]
    trades     = []
    in_trade   = False
    trade_meta: dict[str, Any] = {}

    n = len(df)
    for i in range(5, n):
        # ── Manage open trade ────────────────────────────────────────────────
        if in_trade:
            bar = df.iloc[i]
            ep  = trade_meta["entry_price"]
            sl  = trade_meta["stoploss"]
            tgt = trade_meta["target"]
            qty = trade_meta["qty"]
            d   = trade_meta["direction"]
            bars_held = i - trade_meta["entry_bar"]

            hit_sl  = bar["Low"]  <= sl  if d == "BUY" else bar["High"] >= sl
            hit_tgt = bar["High"] >= tgt if d == "BUY" else bar["Low"]  <= tgt
            force_exit = bars_held >= max_hold

            if hit_tgt or hit_sl or force_exit:
                if hit_tgt:
                    exit_price  = tgt
                    exit_reason = "target"
                elif hit_sl:
                    exit_price  = sl
                    exit_reason = "stoploss"
                else:
                    exit_price  = bar["Close"]
                    exit_reason = "timeout"

                pnl = (exit_price - ep) * qty if d == "BUY" else (ep - exit_price) * qty
                capital += pnl

                ts = df.iloc[i]["_ts"] if "_ts" in df.columns else None
                ts_int = int(ts.timestamp()) if ts is not None and not pd.isna(ts) else None
                trades.append({
                    "entry_time":   trade_meta["entry_ts"],
                    "exit_time":    ts_int,
                    "direction":    d,
                    "entry_price":  round(ep, 2),
                    "exit_price":   round(exit_price, 2),
                    "qty":          qty,
                    "pnl":          round(pnl, 2),
                    "exit_reason":  exit_reason,
                    "note":         trade_meta.get("note", ""),
                    "rr":           trade_meta.get("rr", 0),
                })
                equity.append({"time": ts_int, "value": round(capital, 2)})
                in_trade = False

            continue  # skip signal check while in trade

        # ── Scan for new signal ──────────────────────────────────────────────
        sig = signal_fn(df.iloc[:i + 1])
        if sig is None or sig.get("direction") not in ("BUY", "SELL"):
            continue

        # Enter at NEXT bar's open (realistic execution)
        next_i = i + 1
        if next_i >= n:
            break

        next_bar   = df.iloc[next_i]
        entry_px   = next_bar["Open"]
        sl         = sig["stoploss"]
        tgt        = sig["target"]
        direction  = sig["direction"]

        sl_dist = abs(entry_px - sl)
        if sl_dist < 0.01:
            continue  # degenerate signal

        risk_amount = capital * (risk_pct / 100)
        qty = max(1, int(risk_amount / sl_dist))

        ts = df.iloc[next_i]["_ts"] if "_ts" in df.columns else None
        ts_int = int(ts.timestamp()) if ts is not None and not pd.isna(ts) else None

        in_trade   = True
        trade_meta = {
            "entry_bar":  next_i,
            "entry_ts":   ts_int,
            "entry_price": entry_px,
            "stoploss":   sl,
            "target":     tgt,
            "direction":  direction,
            "qty":        qty,
            "note":       sig.get("note", ""),
            "rr":         sig.get("rr", 0),
        }

    # Fix equity curve first point
    if equity and equity[0]["time"] is None and trades:
        equity[0]["time"] = trades[0]["entry_time"]

    return trades, equity, capital


def _metrics(trades: list[dict], initial_capital: float, final_capital: float, equity: list[dict]) -> dict:
    if not trades:
        return {"total_trades": 0}

    pnls    = [t["pnl"] for t in trades]
    wins    = [p for p in pnls if p > 0]
    losses  = [p for p in pnls if p <= 0]

    # Max drawdown from equity curve
    peak = initial_capital
    max_dd = 0.0
    for pt in equity:
        v = pt["value"]
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Sharpe (daily-ish approximation from per-trade returns)
    import math
    returns = [(t["pnl"] / initial_capital) * 100 for t in trades]
    if len(returns) > 1:
        mean_r = sum(returns) / len(returns)
        std_r  = math.sqrt(sum((r - mean_r) ** 2 for r in returns) / len(returns))
        sharpe = round((mean_r / std_r) * math.sqrt(252) if std_r > 0 else 0, 2)
    else:
        sharpe = 0.0

    return {
        "total_trades":    len(trades),
        "wins":            len(wins),
        "losses":          len(losses),
        "win_rate":        round(len(wins) / len(trades) * 100, 1),
        "total_pnl":       round(sum(pnls), 2),
        "return_pct":      round((final_capital - initial_capital) / initial_capital * 100, 2),
        "avg_pnl":         round(sum(pnls) / len(pnls), 2),
        "avg_win":         round(sum(wins) / len(wins), 2) if wins else 0,
        "avg_loss":        round(sum(losses) / len(losses), 2) if losses else 0,
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe":          sharpe,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/strategies")
def list_strategies():
    """Return available backtest strategies."""
    return {"strategies": STRATEGIES}


@router.post("/run")
async def run_backtest(req: BacktestRequest):
    """Run intraday backtest on historical OHLCV from PostgreSQL."""
    sym = req.symbol.strip().upper()
    strategy_id = req.strategy.strip().lower()

    if strategy_id not in _STRATEGY_IDS:
        raise HTTPException(400, f"Unknown strategy '{strategy_id}'. Valid: {sorted(_STRATEGY_IDS)}")

    intraday = _intraday()

    # Map strategy id → signal function
    fn_map = {
        "macd":                 intraday.signal_macd,
        "rsi":                  intraday.signal_rsi,
        "ema_crossover":        intraday.signal_ema_crossover,
        "supertrend":           intraday.signal_supertrend,
        "bollinger":            intraday.signal_bollinger,
        "vwap":                 intraday.signal_vwap,
        "orb":                  intraday.signal_orb,
        "ema_ribbon":           intraday.signal_ema_ribbon,
        "volume_spike":         intraday.signal_volume_spike,
        "engulfing":            intraday.signal_engulfing,
        "vcp":                  intraday.signal_vcp,
        "darvas":               intraday.signal_darvas,
        "supertrend_breakout":  intraday.signal_supertrend_breakout,
        "volume_profile":       intraday.signal_volume_profile,
        "positional":           intraday.signal_positional,
        "orb_vwap":             intraday.signal_orb_vwap,
        "rsi_divergence":       intraday.signal_rsi_divergence,
        "multi_confirm":        intraday.signal_multi_confirm,
    }
    signal_fn = fn_map[strategy_id]

    try:
        # Fetch OHLCV from DB — get max available bars
        result = intraday.get_intraday_candles(sym, req.timeframe)
        if result is None or (hasattr(result, "empty") and result.empty):
            # Fall back via tools
            if _REPO_ROOT not in sys.path:
                sys.path.insert(0, _REPO_ROOT)
            import terminal.tools as t
            r = t.get_intraday_bars(sym, timeframe=req.timeframe, lookback=2000)
            if not r.get("bars"):
                raise HTTPException(404, f"No {req.timeframe} bars for {sym}")
            import pandas as pd
            bars = r["bars"]
            df_raw = pd.DataFrame(bars)
            df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"])
            df_raw = df_raw.rename(columns={
                "open": "Open", "high": "High", "low": "Low",
                "close": "Close", "volume": "Volume",
            }).set_index("timestamp")
        else:
            df_raw = result

        if len(df_raw) < 20:
            raise HTTPException(422, f"Not enough bars for {sym} {req.timeframe} (got {len(df_raw)})")

        # Attach timestamp column for the walker
        import pandas as pd
        df_for_walk = df_raw.copy()
        df_for_walk["timestamp"] = df_raw.index if hasattr(df_raw.index, "to_pydatetime") else pd.to_datetime(df_for_walk.get("timestamp", df_for_walk.index))

        trades, equity, final_cap = _walk(
            df_for_walk, signal_fn,
            req.initial_capital, req.risk_per_trade_pct, req.max_holding_bars,
        )
        metrics = _metrics(trades, req.initial_capital, final_cap, equity)
        strategy_name = next(s["name"] for s in STRATEGIES if s["id"] == strategy_id)

        # Persist to PostgreSQL (fire-and-forget, never fail the request)
        run_id = _persist_run(sym, req, strategy_name, len(df_raw), metrics, trades, equity)

        return {
            "symbol":    sym,
            "timeframe": req.timeframe,
            "strategy":  strategy_name,
            "bars_used": len(df_raw),
            "metrics":   metrics,
            "trades":    trades,
            "equity_curve": equity,
            "run_id":    run_id,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ── Results / leaderboard endpoints ──────────────────────────────────────────

@router.get("/leaderboard")
def get_leaderboard(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    timeframe: Optional[str] = Query(None, description="Filter by timeframe"),
    min_trades: int = Query(3, description="Minimum trades to include"),
    limit: int = Query(100, le=500),
):
    """Return best backtest run per strategy (highest options_score), sorted desc."""
    try:
        conn = _pg()
        cur  = conn.cursor()
        filters = ["total_trades >= %s"]
        params: list = [min_trades]
        if symbol:
            filters.append("UPPER(symbol) = UPPER(%s)")
            params.append(symbol)
        if timeframe:
            filters.append("timeframe = %s")
            params.append(timeframe)
        where = " AND ".join(filters)
        # Use a subquery to pick best run per (symbol, tf, strategy), then sort overall
        cur.execute(f"""
            WITH best AS (
                SELECT DISTINCT ON (symbol, timeframe, strategy_id)
                    id, run_at, symbol, timeframe, strategy_id, strategy_name,
                    total_trades, wins, losses, win_rate,
                    return_pct, sharpe, max_drawdown_pct, total_pnl, options_score
                FROM backtesting.strategy_runs
                WHERE {where}
                ORDER BY symbol, timeframe, strategy_id, options_score DESC NULLS LAST
            )
            SELECT * FROM best
            ORDER BY options_score DESC NULLS LAST
            LIMIT %s
        """, params + [limit])
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        conn.close()
        for i, r in enumerate(rows):
            r["rank"] = i + 1
            r["run_at"] = r["run_at"].isoformat() if r.get("run_at") else None
        return {"leaderboard": rows, "count": len(rows)}
    except Exception as exc:
        # PG unavailable — return empty leaderboard rather than 500
        import logging
        logging.getLogger(__name__).warning("leaderboard PG error: %s", exc)
        return {"leaderboard": [], "count": 0, "pg_error": str(exc)}


@router.get("/results/{run_id}")
def get_run_detail(run_id: int):
    """Return full trades + equity curve for a specific run."""
    try:
        conn = _pg()
        cur  = conn.cursor()
        cur.execute("""
            SELECT id, run_at, symbol, timeframe, strategy_id, strategy_name,
                   initial_capital, risk_pct, max_hold_bars, bars_used,
                   total_trades, wins, losses, win_rate,
                   total_pnl, return_pct, avg_pnl, avg_win, avg_loss,
                   max_drawdown_pct, sharpe, options_score,
                   trades_json, equity_json
            FROM backtesting.strategy_runs
            WHERE id = %s
        """, (run_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            raise HTTPException(404, f"Run {run_id} not found")
        cols = [d[0] for d in cur.description]
        data = dict(zip(cols, row))
        data["run_at"] = data["run_at"].isoformat() if data.get("run_at") else None
        return data
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@router.get("/history")
def get_history(
    symbol: Optional[str] = Query(None),
    timeframe: Optional[str] = Query(None),
    strategy_id: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
):
    """All runs sorted newest first (no deduplication — full history)."""
    try:
        conn = _pg()
        cur  = conn.cursor()
        filters: list[str] = []
        params: list = []
        if symbol:
            filters.append("UPPER(symbol) = UPPER(%s)")
            params.append(symbol)
        if timeframe:
            filters.append("timeframe = %s")
            params.append(timeframe)
        if strategy_id:
            filters.append("strategy_id = %s")
            params.append(strategy_id)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        cur.execute(f"""
            SELECT id, run_at, symbol, timeframe, strategy_id, strategy_name,
                   total_trades, win_rate, return_pct, sharpe, max_drawdown_pct,
                   total_pnl, options_score
            FROM backtesting.strategy_runs
            {where}
            ORDER BY run_at DESC
            LIMIT %s
        """, params + [limit])
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        conn.close()
        for r in rows:
            r["run_at"] = r["run_at"].isoformat() if r.get("run_at") else None
        return {"history": rows, "count": len(rows)}
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("history PG error: %s", exc)
        return {"history": [], "count": 0, "pg_error": str(exc)}
