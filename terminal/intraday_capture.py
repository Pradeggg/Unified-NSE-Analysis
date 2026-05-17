"""Background intraday tape capture.

PG-intraday-capture: When the Agent Adda REPL starts, a daemon thread begins
polling the NSE live overview and persisting snapshots into
``intraday.quote_snapshots``. A second daemon thread periodically prunes rows
older than the configured retention window while preserving enough history for
simulation and analysis.

Both threads are short-circuited outside Indian market hours and on any
exception (so they never break the chat loop).
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, time as dt_time, timezone, timedelta

# Defaults — overridable via env so we don't need to touch code in production.
CAPTURE_INTERVAL_SEC = int(os.environ.get("AGENT_ADDA_CAPTURE_INTERVAL_SEC", "60"))
RETENTION_MINUTES    = int(os.environ.get("AGENT_ADDA_CAPTURE_RETENTION_MIN", "129600"))
PRUNE_INTERVAL_SEC   = int(os.environ.get("AGENT_ADDA_CAPTURE_PRUNE_SEC", "1800"))
PG_DSN               = os.environ.get("AGENT_ADDA_PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"

IST = timezone(timedelta(hours=5, minutes=30))
MARKET_OPEN  = dt_time(9, 0)    # buffer 15 min before open for pre-open snaps
MARKET_CLOSE = dt_time(15, 45)  # 15 min after close

_started = False
_lock = threading.Lock()


def _is_market_window(now_ist: datetime | None = None) -> bool:
    now_ist = now_ist or datetime.now(IST)
    if now_ist.weekday() >= 5:           # Sat/Sun
        return False
    return MARKET_OPEN <= now_ist.time() <= MARKET_CLOSE


# ── capture loop ────────────────────────────────────────────────────────────
def _capture_once() -> int:
    """Pull live overview and persist one snapshot per preferred index.
    Returns rows inserted (0 on any failure)."""
    if not _is_market_window():
        return 0

    try:
        from terminal.tools import get_live_market_overview
        from terminal.intraday_storage import persist_intraday_snapshot
    except Exception:
        return 0

    overview = get_live_market_overview()
    if not overview or overview.get("error"):
        return 0

    indices = overview.get("indices") or {}
    preferred = [
        "NIFTY 50", "NIFTY BANK", "NIFTY MIDCAP SELECT",
        "NIFTY MIDCAP 50", "NIFTY MIDCAP 100",
        "NIFTY NEXT 50", "NIFTY IT", "NIFTY FMCG", "NIFTY AUTO", "NIFTY PHARMA",
    ]
    inserted = 0
    for name in preferred:
        row = indices.get(name)
        if not row:
            continue
        try:
            persist_intraday_snapshot({
                "symbol": name,
                "source": overview.get("source", "NSE live API"),
                "as_of":  overview.get("as_of"),
                "name":   name,
                "last_price": row.get("last"),
                "change":     row.get("change"),
                "pct_change": row.get("pct_change"),
                "day_high":   row.get("day_high"),
                "day_low":    row.get("day_low"),
            })
            inserted += 1
        except Exception:
            pass
    return inserted


def _capture_loop() -> None:
    while True:
        try:
            if _is_market_window():
                _capture_once()
        except Exception:
            pass
        time.sleep(CAPTURE_INTERVAL_SEC)


# ── prune loop ──────────────────────────────────────────────────────────────
def _prune_once() -> int:
    """Delete snapshots older than RETENTION_MINUTES. Returns rows deleted."""
    try:
        import psycopg2
        with psycopg2.connect(PG_DSN) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM intraday.quote_snapshots "
                "WHERE captured_at < now() - (%s::text || ' minutes')::interval",
                (str(RETENTION_MINUTES),),
            )
            return cur.rowcount or 0
    except Exception:
        return 0


def _prune_loop() -> None:
    # Run once at startup so we don't carry over stale tape from a prior session.
    try:
        _prune_once()
    except Exception:
        pass
    while True:
        time.sleep(PRUNE_INTERVAL_SEC)
        try:
            _prune_once()
        except Exception:
            pass


# ── public entry point ──────────────────────────────────────────────────────
def start_background_capture() -> bool:
    """Idempotently spawn the capture + prune daemons. Returns True on first start."""
    global _started
    with _lock:
        if _started:
            return False
        threading.Thread(target=_capture_loop, name="intraday-capture",
                         daemon=True).start()
        threading.Thread(target=_prune_loop,   name="intraday-prune",
                         daemon=True).start()
        _started = True
        return True
