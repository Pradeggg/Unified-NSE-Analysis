from __future__ import annotations

import time

import pandas as pd

from terminal import intraday


def test_run_intraday_screener_returns_after_scan_timeout(monkeypatch):
    def slow_candles(symbol, interval):
        time.sleep(0.4)
        return pd.DataFrame()

    monkeypatch.setattr(intraday, "_SCAN_TIMEOUT", 0.01)
    monkeypatch.setattr(intraday, "_STOCK_TIMEOUT", 0.01)
    monkeypatch.setattr(intraday, "_SCREENER_WORKERS", 2)
    monkeypatch.setattr(intraday, "get_intraday_candles", slow_candles)

    started = time.monotonic()
    result = intraday.run_intraday_screener(["AAA", "BBB"], interval="5m")
    elapsed = time.monotonic() - started

    assert elapsed < 0.2
    assert set(result["errors"]) == {"AAA", "BBB"}
    assert result["scanned"] == 0
