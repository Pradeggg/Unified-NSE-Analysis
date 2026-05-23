"""Optional TradingView screenshot capture for visual scans."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any
from urllib.parse import quote


def _safe_filename_part(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned or fallback


def build_tradingview_url(symbol: str) -> str:
    return "https://www.tradingview.com/chart/?symbol=" + quote(f"NSE:{str(symbol).upper()}", safe="")


def capture_tradingview_screenshot(
    symbol: str,
    output_dir: str | Path,
    run_id: str,
    timeout_ms: int = 12_000,
) -> dict[str, Any]:
    url = build_tradingview_url(symbol)
    target = Path(output_dir)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return {
            "status": "unavailable",
            "message": (
                "TradingView screenshot unavailable; report generated from local OHLCV evidence. "
                f"Reason: {exc}"
            ),
            "url": url,
        }

    safe_symbol = _safe_filename_part(str(symbol).upper(), "SYMBOL")
    safe_run_id = _safe_filename_part(run_id, "run")
    path = target / f"{safe_symbol}_{safe_run_id}_tradingview_daily.png"

    try:
        target.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            page.screenshot(path=str(path), full_page=True)
            browser.close()
        return {
            "status": "captured",
            "path": str(path),
            "url": url,
            "message": "TradingView screenshot captured as corroboration only.",
        }
    except Exception as exc:
        return {
            "status": "unavailable",
            "message": (
                "TradingView screenshot unavailable; report generated from local OHLCV evidence. "
                f"Reason: {exc}"
            ),
            "url": url,
        }
