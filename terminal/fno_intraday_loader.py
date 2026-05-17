"""Background PostgreSQL loader for live index-futures snapshots."""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Any

from terminal.fno_data import fetch_live_futures, get_lot_size
from terminal.intraday_storage import persist_live_futures_snapshot


LOAD_INTERVAL_SEC = int(os.environ.get("AGENT_ADDA_FNO_INTERVAL_SEC", "900"))
INDEX_FUTURE_SYMBOLS = ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50")
CONFIG_SYMBOLS = tuple(
    dict.fromkeys(
        item.strip().upper()
        for item in os.environ.get("AGENT_ADDA_FNO_SYMBOLS", "").split(",")
        if item.strip()
    )
)

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


def _symbol_universe() -> list[str]:
    if CONFIG_SYMBOLS:
        return list(CONFIG_SYMBOLS)
    return list(INDEX_FUTURE_SYMBOLS)


def _load_once(symbols: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    selected_symbols = list(dict.fromkeys(symbols or _symbol_universe()))
    attempted = 0
    persisted_rows = 0
    errors: list[dict[str, str]] = []

    for symbol in selected_symbols:
        attempted += 1
        try:
            snapshot = fetch_live_futures(symbol)
            if snapshot.get("error"):
                errors.append({"symbol": symbol, "error": str(snapshot["error"])})
                continue
            if snapshot.get("source") != "live-nse-api":
                errors.append({"symbol": symbol, "error": f"non_live_source:{snapshot.get('source')}"})
                continue
            snapshot = {
                **snapshot,
                "as_of": datetime.now(IST).isoformat(),
                "lot_size": get_lot_size(symbol),
            }
            result = persist_live_futures_snapshot(snapshot)
            persisted_rows += int(result.get("rows_inserted") or 0)
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc)})

    return {
        "data_mode": "intraday",
        "source": "NSE live derivatives API -> PostgreSQL intraday.futures_snapshots",
        "symbols_scanned": len(selected_symbols),
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


def start_background_fno_loader() -> bool:
    """Idempotently start the index-futures snapshot loader."""
    global _started
    with _lock:
        if _started:
            return False
        threading.Thread(target=_load_loop, name="fno-intraday-loader", daemon=True).start()
        _started = True
        return True
