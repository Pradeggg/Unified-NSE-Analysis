#!/usr/bin/env python3
"""Standalone intraday OHLCV and quote-snapshot capture daemon.

Designed to be launched by launchd via com.agentadda.intraday_capture.plist
at 09:00 IST on weekdays (Mon-Fri).  It starts both background loaders, then
blocks in the main thread until the market window ends (15:45 IST) and exits
cleanly — the daemon threads die with the process.

What it populates
-----------------
- intraday.ohlcv_bars       : 15-min OHLCV candles from yfinance (every 15 min)
- intraday.quote_snapshots  : live NSE overview snapshots (every 60 s)

These tables are consumed by scripts/build_eod_market_report.py:
  ohlcv_bars       → candlestick charts + hour-by-hour tape section
  quote_snapshots  → live intraday price trail

Configuration via environment
-----------------------------
AGENT_ADDA_OHLCV_INTERVAL_SEC   : seconds between OHLCV fetches (default 900)
AGENT_ADDA_OHLCV_TOP_N          : top-N symbols from stage snapshots (default 50)
AGENT_ADDA_OHLCV_TIMEFRAMES     : comma-separated timeframes (default "15m")
AGENT_ADDA_OHLCV_SYMBOLS        : override symbol list (default: indices + top-N)
AGENT_ADDA_PG_DSN / PG_DSN      : PostgreSQL DSN (default: dbname=nse_market user=nse_admin host=/tmp)

Usage
-----
  # Normal (started by launchd):
  python scripts/run_intraday_ohlcv_capture.py

  # Single OHLCV fetch + exit (useful for one-off backfill or testing):
  python scripts/run_intraday_ohlcv_capture.py --once

  # Dry-run — verify imports and show what would run, no DB writes:
  python scripts/run_intraday_ohlcv_capture.py --dry-run

  # Force-run even outside market hours (testing):
  python scripts/run_intraday_ohlcv_capture.py --force --once
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Market window constants (IST)
# ---------------------------------------------------------------------------
IST = timezone(timedelta(hours=5, minutes=30))
MARKET_OPEN_H, MARKET_OPEN_M = 9, 0
MARKET_CLOSE_H, MARKET_CLOSE_M = 15, 45

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [intraday-capture] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_ist() -> datetime:
    return datetime.now(IST)


def _is_weekday(now: datetime | None = None) -> bool:
    return (now or _now_ist()).weekday() < 5  # 0=Mon … 4=Fri


def _past_market_close(now: datetime | None = None) -> bool:
    now = now or _now_ist()
    return now.hour > MARKET_CLOSE_H or (
        now.hour == MARKET_CLOSE_H and now.minute >= MARKET_CLOSE_M
    )


def _before_market_open(now: datetime | None = None) -> bool:
    now = now or _now_ist()
    return now.hour < MARKET_OPEN_H or (
        now.hour == MARKET_OPEN_H and now.minute < MARKET_OPEN_M
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent Adda intraday OHLCV capture daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip DB writes — only verify imports and log what would run",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Trigger one OHLCV fetch cycle then exit (ignores market-window guard)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip market-hours / weekday checks (for testing outside hours)",
    )
    args = parser.parse_args()

    now = _now_ist()
    log.info(
        "Intraday capture daemon starting — %s IST  weekday=%s",
        now.strftime("%Y-%m-%d %H:%M:%S"),
        _is_weekday(now),
    )

    # ------------------------------------------------------------------
    # Early-exit guards (skipped by --force or --once)
    # ------------------------------------------------------------------
    if not args.force and not args.once:
        if not _is_weekday(now):
            log.info("Today is %s — not a trading day. Exiting.", now.strftime("%A"))
            sys.exit(0)

        if _past_market_close(now):
            log.info(
                "Market already closed for today (%02d:%02d IST). Exiting.",
                MARKET_CLOSE_H,
                MARKET_CLOSE_M,
            )
            sys.exit(0)

        if _before_market_open(now):
            wait_sec = (
                now.replace(hour=MARKET_OPEN_H, minute=MARKET_OPEN_M, second=0, microsecond=0)
                - now
            ).total_seconds()
            log.info(
                "Market opens at %02d:%02d IST — waiting %.0f s.",
                MARKET_OPEN_H,
                MARKET_OPEN_M,
                wait_sec,
            )
            time.sleep(max(0, wait_sec))

    # ------------------------------------------------------------------
    # Import loaders (these live inside the project package)
    # ------------------------------------------------------------------
    try:
        from terminal.intraday_ohlcv_loader import (   # noqa: PLC0415
            _load_once,
            start_background_ohlcv_loader,
        )
        from terminal.intraday_capture import (        # noqa: PLC0415
            start_background_capture,
        )
    except ImportError as exc:
        log.error(
            "Import failed. Run from the project root with .venv activated.\n"
            "  cd Unified-NSE-Analysis && source .venv/bin/activate\n"
            "  python scripts/run_intraday_ohlcv_capture.py\n"
            "Error: %s",
            exc,
        )
        sys.exit(1)

    # ------------------------------------------------------------------
    # --once: single fetch cycle then exit
    # ------------------------------------------------------------------
    if args.once:
        if args.dry_run:
            log.info("--dry-run + --once: skipping DB write. Import OK.")
            sys.exit(0)
        log.info("--once: running one OHLCV fetch cycle …")
        result = _load_once()
        log.info(
            "Fetch complete — symbols=%d  persisted_rows=%d  errors=%d",
            result.get("symbols_scanned", 0),
            result.get("persisted_rows", 0),
            len(result.get("errors", [])),
        )
        errors = result.get("errors") or []
        if errors:
            # errors may be a list of strings or a dict {sym: msg}
            if isinstance(errors, dict):
                for sym, msg in list(errors.items())[:5]:
                    log.warning("  %s: %s", sym, msg)
            else:
                for item in errors[:5]:
                    log.warning("  %s", item)
        sys.exit(0)

    # ------------------------------------------------------------------
    # Continuous mode: start daemons, block until market close
    # ------------------------------------------------------------------
    if args.dry_run:
        log.info("--dry-run: loaders NOT started. Verified imports OK.")
        log.info("Would run until %02d:%02d IST.", MARKET_CLOSE_H, MARKET_CLOSE_M)
        sys.exit(0)

    started_ohlcv = start_background_ohlcv_loader()
    started_capture = start_background_capture()
    log.info(
        "Loaders started — OHLCV=%s  quote-snapshots=%s",
        started_ohlcv,
        started_capture,
    )
    log.info(
        "Daemon active. Will exit after %02d:%02d IST. "
        "Tailing logs: tail -f ~/.agent-adda/logs/intraday_capture.log",
        MARKET_CLOSE_H,
        MARKET_CLOSE_M,
    )

    # Block until market closes, checking every 60 s
    while True:
        if not args.force and _past_market_close():
            log.info("Market window ended — shutting down capture daemon.")
            break
        time.sleep(60)

    sys.exit(0)


if __name__ == "__main__":
    main()
