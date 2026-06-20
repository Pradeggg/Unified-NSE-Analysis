"""Run Agent Adda's F&O intraday monitor every three minutes."""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal.live_intraday_alerts import (
    IntradayAlertConfig,
    load_fno_intraday_universe,
    run_intraday_alert_commentary,
)

INDEX_UNDERLYINGS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"}


def main() -> None:
    symbols = [
        symbol
        for symbol in load_fno_intraday_universe()
        if symbol not in INDEX_UNDERLYINGS
    ]
    log_dir = ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    cycle_log = log_dir / f"intraday_monitor_3min_cycles_{datetime.now():%Y%m%d}.jsonl"
    latest_snapshot = log_dir / "intraday_monitor_3min_latest.md"
    print(
        f"Starting Agent Adda intraday monitor: {len(symbols)} F&O symbols, "
        "5m candles, 3-minute loop",
        flush=True,
    )
    run_intraday_alert_commentary(
        IntradayAlertConfig(
            symbols=symbols,
            candle_interval="5m",
            cycles=None,
            interval_secs=180,
            min_rr=2.0,
            max_tracked_symbols=15,
            dry_run=True,
            use_llm=False,
            remember_symbols=False,
            require_volume=False,
            email_every_mins=0,
            write_cycle_log=True,
            log_path=cycle_log,
            latest_snapshot_path=latest_snapshot,
        )
    )


if __name__ == "__main__":
    main()
