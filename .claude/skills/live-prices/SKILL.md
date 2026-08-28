---
name: live-prices
description: Fetch live NSE prices via yfinance (5-min candles, ~15-min delay during market hours) and open an HTML dashboard at reports/latest/live_prices.html. Use when the user asks for live prices, current prices, today's prices, intraday prices, or wants to refresh market data.
---

# Live Prices

Fetch live NSE prices and open a self-contained HTML dashboard.

## Source & latency

- **Data:** yfinance via `.NS` suffix (NSE equities)
- **Granularity:** 5-minute candles; last bar = live price (~15-min delayed during market hours)
- **After market close:** shows EOD data for the session
- **Market hours:** 09:15 – 15:30 IST

## Run it

```bash
cd /Users/pradeepgorai/Documents/Projects/finance/Unified-NSE-Analysis
source .venv/bin/activate 2>/dev/null || true
python tools/live_prices.py
```

Opens `reports/latest/live_prices.html` in the browser automatically.

## Options

```bash
# Built-in watchlists
python tools/live_prices.py --watchlist nifty50   # 20 Nifty 50 heavyweights (default)
python tools/live_prices.py --watchlist banks     # 10 banking stocks
python tools/live_prices.py --watchlist it        # 10 IT stocks

# Custom symbols (appended as a separate section)
python tools/live_prices.py --symbols RELIANCE,INFY,TCS,HDFCBANK

# Generate without opening browser
python tools/live_prices.py --no-open

# Combine: custom symbols on a specific watchlist
python tools/live_prices.py --watchlist banks --symbols BAJFINANCE,CHOLAFIN
```

## Dashboard columns

| Column | Meaning |
|---|---|
| LTP | Last traded price (last 5-min candle close) |
| Chg (prev) | % change vs previous session's close |
| Chg (open) | % change vs today's open |
| Day Hi / Lo | Intraday high and low |
| Volume | Total shares traded so far today |
| Day Range | Visual position bar — where LTP sits between day Lo and Hi |
| As of | Timestamp of the last 5-min bar |

## Refresh

Just re-run the script — it overwrites `live_prices.html` and re-opens the browser. The file is at:
```
reports/latest/live_prices.html
```

## Errors

| Error | Fix |
|---|---|
| `No data found` for a symbol | Symbol may not have a `.NS` suffix in yfinance; skip it |
| `ModuleNotFoundError: yfinance` | `pip install yfinance` |
| All blank / 0 rows | Market may be closed; check if within 09:15–15:30 IST |
