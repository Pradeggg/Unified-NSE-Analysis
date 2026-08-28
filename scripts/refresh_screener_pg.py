#!/usr/bin/env python3
"""Refresh structured Screener financials into PostgreSQL.

Usage:
    .venv/bin/python scripts/refresh_screener_pg.py ATHERENERG
"""
from __future__ import annotations

import argparse

from terminal.web_research import scrape_screener_in
from terminal.financials_cache import upsert_screener_payload


def refresh_symbol(symbol: str) -> dict[str, int]:
    payload = scrape_screener_in(symbol)
    if payload.get("error"):
        raise RuntimeError(f"Screener refresh failed for {symbol}: {payload['error']}")
    counts = upsert_screener_payload(symbol.upper(), payload, source="screener_standalone_or_consolidated")
    print(
        f"{symbol.upper()}: quarterly={counts['quarterly']} annual={counts['annual']} "
        f"balance_sheet={counts['balance_sheet']} cash_flow={counts['cash_flow']}"
    )
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol")
    args = parser.parse_args()
    refresh_symbol(args.symbol)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
