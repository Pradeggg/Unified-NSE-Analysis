"""Background PostgreSQL OHLCV loader for intraday candles.

This daemon complements ``terminal.intraday_capture``:
quote snapshots land in ``intraday.quote_snapshots`` while full candle history
lands in ``intraday.ohlcv_bars``. Yahoo Finance is used only as the upstream
candle source; PostgreSQL remains the runtime store.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Any

import pandas as pd

from terminal.intraday import get_intraday_candles
from terminal.intraday_storage import persist_intraday_bars


LOAD_INTERVAL_SEC = int(os.environ.get("AGENT_ADDA_OHLCV_INTERVAL_SEC", "900"))
TOP_N_SYMBOLS = int(os.environ.get("AGENT_ADDA_OHLCV_TOP_N", "50"))
TIMEFRAMES = tuple(
    item.strip()
    for item in os.environ.get("AGENT_ADDA_OHLCV_TIMEFRAMES", "15m").split(",")
    if item.strip()
) or ("15m",)
CONFIG_SYMBOLS = tuple(
    dict.fromkeys(
        item.strip().upper()
        for item in os.environ.get("AGENT_ADDA_OHLCV_SYMBOLS", "").split(",")
        if item.strip()
    )
)
PG_DSN = os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"
INDEX_SYMBOLS = ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50")

IST = timezone(timedelta(hours=5, minutes=30))
MARKET_OPEN = dt_time(9, 0)
MARKET_CLOSE = dt_time(15, 45)

_started = False
_lock = threading.Lock()


def _is_market_window(now_ist: datetime | None = None) -> bool:
    now_ist = now_ist or datetime.now(IST)
    if now_ist.weekday() >= 5:
        return False
    return MARKET_OPEN <= now_ist.time() <= MARKET_CLOSE


def _env_symbols() -> list[str]:
    return list(CONFIG_SYMBOLS)


def _symbol_universe(top_n: int = TOP_N_SYMBOLS) -> list[str]:
    env_symbols = _env_symbols()
    if env_symbols:
        return env_symbols[:top_n]

    try:
        import psycopg2

        with psycopg2.connect(PG_DSN) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT UPPER(symbol)
                FROM scores.stage_snapshots
                WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM scores.stage_snapshots)
                  AND symbol IS NOT NULL
                ORDER BY UPPER(symbol)
                LIMIT %s
                """,
                (top_n,),
            )
            symbols = list(dict.fromkeys([*INDEX_SYMBOLS, *(row[0] for row in cur.fetchall() if row and row[0])]))
            if symbols:
                return symbols[:top_n]
    except Exception:
        pass

    return [
        *INDEX_SYMBOLS,
        "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "ITC",
        "BHARTIARTL", "LT", "AXISBANK", "BAJFINANCE", "TATAMOTORS",
    ][:top_n]


def _bars_from_df(df: pd.DataFrame) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    if df.empty:
        return bars
    for idx, row in df.sort_index().iterrows():
        bars.append(
            {
                "timestamp": idx,
                "open": row.get("Open"),
                "high": row.get("High"),
                "low": row.get("Low"),
                "close": row.get("Close"),
                "volume": row.get("Volume"),
            }
        )
    return bars


def _load_once(
    *,
    symbols: list[str] | None = None,
    timeframes: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    selected_symbols = list(dict.fromkeys((symbols or _symbol_universe(TOP_N_SYMBOLS))))
    selected_timeframes = tuple(timeframes or TIMEFRAMES)
    attempted = 0
    persisted_rows = 0
    errors: list[dict[str, str]] = []

    for sym in selected_symbols:
        for timeframe in selected_timeframes:
            attempted += 1
            try:
                df = get_intraday_candles(sym, timeframe)
                if df.empty:
                    errors.append({"symbol": sym, "timeframe": timeframe, "error": "no_candles"})
                    continue
                result = persist_intraday_bars(
                    sym,
                    _bars_from_df(df),
                    timeframe=timeframe,
                    source="Yahoo Finance (yfinance)",
                )
                persisted_rows += int(result.get("rows_inserted") or 0)
            except Exception as exc:
                errors.append({"symbol": sym, "timeframe": timeframe, "error": str(exc)})

    return {
        "data_mode": "intraday",
        "source": "Yahoo Finance (yfinance) -> PostgreSQL intraday.ohlcv_bars",
        "symbols_scanned": len(selected_symbols),
        "timeframes": list(selected_timeframes),
        "attempted": attempted,
        "persisted_rows": persisted_rows,
        "errors": errors,
    }


def _load_loop() -> None:
    while True:
        try:
            if _is_market_window():
                _load_once()
        except Exception:
            pass
        time.sleep(LOAD_INTERVAL_SEC)


def start_background_ohlcv_loader() -> bool:
    """Idempotently start the PostgreSQL OHLCV background loader."""
    global _started
    with _lock:
        if _started:
            return False
        threading.Thread(target=_load_loop, name="intraday-ohlcv-loader", daemon=True).start()
        _started = True
        return True
