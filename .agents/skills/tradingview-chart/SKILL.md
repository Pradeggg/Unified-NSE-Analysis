---
name: tradingview-chart
description: Open a TradingView-style NSE/BSE chart with Agent Adda studies (SMA 20/50/200, RSI 14, MACD 12/26/9, Supertrend 10x3, ADX 14, volume) and also build daily plus intraday Cursor Canvas LineCharts. Use when the user asks to view, open, or show a TradingView chart, candlestick chart, technical chart, intraday chart, 5-minute chart, or canvas chart for a stock.
---

# TradingView Chart

Render a TradingView-style chart with Agent Adda’s indicator set. Do not use TradingView’s embed widget for NSE cash names; it errors with “This symbol is only available on TradingView.”

Always produce **both**:

1. Local HTML (candles, RSI, MACD, Supertrend, drawing tools).
2. A Cursor Canvas: Yahoo **5m (default) or 15m** session close/high/low, plus daily close + SMA 20/50/200.

## Workflow

1. Resolve the company to an NSE (or BSE index) ticker. Default exchange prefix is `NSE:`.
2. From the repository root, write HTML **and** a canvas:

   ```bash
   python3 .agents/skills/tradingview-chart/scripts/open_tradingview_chart.py SYMBOL --open --canvas
   ```

   Several names:

   ```bash
   python3 .agents/skills/tradingview-chart/scripts/build_chart_canvas.py SYM1 SYM2 SYM3
   python3 .agents/skills/tradingview-chart/scripts/open_tradingview_chart.py SYM1 --open --canvas
   ```

   Interval for HTML defaults to daily (`D`). Use `--interval W` for weekly. Canvas always adds a 5m pane unless `--no-intraday`; use `--intraday-interval 15m` for 15-minute bars. Add `--no-snapshot` only if Postgres is unavailable.
3. Tell the user:
   - The HTML path (toolbar: candles/bars/line/area, 1M–All, Vol/SMA/ST/RSI/MACD).
   - A markdown link to the `.canvas.tsx` file using its **full absolute path**. Ask them to open it as a canvas beside chat, not as source.
4. Read the HTML sidebar as Agent Adda’s numbers. Canvas LineCharts are the in-IDE visual.

## Cursor Canvas rules

Read `~/.cursor/skills-cursor/canvas/SKILL.md` if you hand-edit a canvas. Prefer the generator above.

- Write exactly one file under `~/.cursor/projects/<workspace-slug>/canvases/<name>.canvas.tsx`. Slug is the repo path with `/` stripped and remaining `/` replaced by `-`.
- Import **only** from `cursor/canvas`. Embed OHLC-derived series inline. No `fetch()`.
- Use `LineChart` with `beginAtZero={false}` for prices, plus `Stat` / `Pill`. Put the **intraday** pane first (close + session high/low envelopes), then daily SMA. Omit the intraday pane if Yahoo returns no bars. Do **not** draw custom SVG candles — they often render blank in the preview.
- Do not put a React `key` prop on custom components (`Pill`, `LineChart`, or helpers). Unroll a few symbols instead of `.map()` if the canvas type-check rejects `key`.
- After writing, mention the canvas with a markdown link: `[label](/absolute/path/to/file.canvas.tsx)`.

## Required chart studies

Load exactly the studies in [references/indicators.md](references/indicators.md). HTML has the full daily set. Canvas shows session 5m/15m plus daily SMA 20/50/200; point users at HTML for RSI/MACD/Supertrend panes, and at the live TradingView 5m link for a full intraday workstation.

## Do not

- Embed `tradingview-widget.com` / `embed-widget-advanced-chart.js` for NSE equities.
- Open a blank TradingView chart and ask the user to add indicators by hand.
- Use the visual-scan SVG as a substitute unless this chart script fails.
- Skip the canvas when running inside Cursor and the user asked to see a chart.
