TradingView's **free embed widget cannot plot NSE cash names**. It shows "This symbol is only available on TradingView" (or hangs / falls back to AAPL). This skill therefore:

1. Plots Agent Adda EOD with TradingView Lightweight Charts and the studies below.
2. Links to `https://www.tradingview.com/chart/?symbol=NSE:SYMBOL` for the live TradingView site.
3. Writes a Cursor Canvas (`build_chart_canvas.py`) with a **Yahoo 5m/15m** session pane (close + high/low) and a daily close + SMA 20/50/200 pane via `LineChart`. Canvas cannot reliably draw custom SVG candles. Index Yahoo tickers: NIFTY → `^NSEI`, BANKNIFTY → `^NSEBANK`, SENSEX → `^BSESN`.

| Agent Adda | Parameters | Chart pane |
|---|---|---|
| Candles + volume | daily EOD | price pane |
| SMA 20 / 50 / 200 | simple, close | price pane |
| Supertrend | ATR 10, multiplier 3.0 | price pane |
| RSI | 14 | RSI pane |
| MACD | 12 / 26 / 9 | MACD pane |
| ADX | 14 | sidebar snapshot |

Timezone label is `Asia/Kolkata`. Equity symbols use `NSE:SYMBOL`. Common indices:

- Nifty 50 → `NSE:NIFTY`
- Bank Nifty → `NSE:BANKNIFTY`
- Fin Nifty → `NSE:CNXFINANCE`
- Midcap Select → `NSE:NIFTYMIDSELECT`
- Sensex → `BSE:SENSEX`

Sidebar numbers come from `get_technical_setup`. The panes use the same local OHLC. If they disagree, show both.
