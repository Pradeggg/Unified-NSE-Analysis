#!/usr/bin/env python3
"""Render an NSE chart with Agent Adda studies using TradingView Lightweight Charts.

TradingView's free embed widget rejects NSE cash symbols with
"This symbol is only available on TradingView." This script plots local EOD
bars with the same studies as get_technical_setup and links to the full site.
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import math
import re
import sys
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import quote


PROJECT_ROOT = Path(__file__).resolve().parents[4]
CHART_ROOT = PROJECT_ROOT / "reports/tradingview"
INTERVALS = {"D", "W", "M", "120", "60", "30", "15", "5", "1"}

INDEX_SYMBOLS = {
    "NIFTY": "NSE:NIFTY",
    "NIFTY50": "NSE:NIFTY",
    "NIFTY 50": "NSE:NIFTY",
    "BANKNIFTY": "NSE:BANKNIFTY",
    "NIFTY BANK": "NSE:BANKNIFTY",
    "FINNIFTY": "NSE:CNXFINANCE",
    "MIDCPNIFTY": "NSE:NIFTYMIDSELECT",
    "SENSEX": "BSE:SENSEX",
}

YF_INDEX_TICKERS = {
    "NIFTY": "^NSEI",
    "NIFTY50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "SENSEX": "^BSESN",
}


def canonical_symbol(raw: str) -> str:
    token = re.sub(r"\s+", " ", str(raw or "").strip().upper())
    token = token.removesuffix(".NS").removesuffix(".BO")
    if not token:
        raise ValueError("symbol is required")
    return token


def tradingview_symbol(raw: str) -> str:
    token = canonical_symbol(raw)
    if ":" in token:
        exchange, ticker = token.split(":", 1)
        return f"{exchange.strip()}:{ticker.strip()}"
    mapped = INDEX_SYMBOLS.get(token)
    if mapped:
        return mapped
    return f"NSE:{token}"


def yahoo_ticker(raw: str) -> str:
    token = canonical_symbol(raw)
    if ":" in token:
        token = token.split(":", 1)[1]
    return YF_INDEX_TICKERS.get(token, f"{token}.NS")


def tradingview_page_url(tv_symbol: str, interval: str) -> str:
    return (
        "https://www.tradingview.com/chart/?symbol="
        + quote(tv_symbol, safe=":")
        + "&interval="
        + quote(interval, safe="")
    )


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _series(times: list[str], values: list[Any]) -> list[dict[str, Any]]:
    points = []
    for time, value in zip(times, values, strict=False):
        number = _finite(value)
        if number is None:
            continue
        points.append({"time": time, "value": round(number, 4)})
    return points


def _rsi(closes: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains, losses = [], []
    for i in range(1, period + 1):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    rs = avg_gain / (avg_loss or 1e-9)
    out[period] = 100 - 100 / (1 + rs)
    for i in range(period + 1, len(closes)):
        change = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(change, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-change, 0.0)) / period
        rs = avg_gain / (avg_loss or 1e-9)
        out[i] = 100 - 100 / (1 + rs)
    return out


def _ema(values: list[float], span: int) -> list[float]:
    k = 2 / (span + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(value * k + out[-1] * (1 - k))
    return out


def _macd(closes: list[float]) -> tuple[list[float | None], list[float | None], list[float | None]]:
    if len(closes) < 26:
        empty = [None] * len(closes)
        return empty, empty, empty
    ema12, ema26 = _ema(closes, 12), _ema(closes, 26)
    macd = [a - b for a, b in zip(ema12, ema26, strict=True)]
    signal = _ema(macd, 9)
    hist = [a - b for a, b in zip(macd, signal, strict=True)]
    return macd, signal, hist


def _sma(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    total = 0.0
    for i, value in enumerate(values):
        total += value
        if i >= window:
            total -= values[i - window]
        if i >= window - 1:
            out[i] = total / window
    return out


def _supertrend(highs: list[float], lows: list[float], closes: list[float], period: int = 10, mult: float = 3.0) -> tuple[list[float | None], str | None]:
    n = len(closes)
    line: list[float | None] = [None] * n
    if n < period + 2:
        return line, None
    tr = [0.0]
    for i in range(1, n):
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    atr = _ema(tr, period)
    direction = 1
    st = (highs[period] + lows[period]) / 2
    for i in range(period, n):
        mid = (highs[i] + lows[i]) / 2
        upper, lower = mid + mult * atr[i], mid - mult * atr[i]
        if closes[i] > st:
            direction = 1
            st = lower
        else:
            direction = -1
            st = upper
        line[i] = st
    return line, ("BUY" if direction == 1 else "SELL")


def load_bars(symbol: str, days: int = 400) -> list[dict[str, Any]]:
    try:
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from terminal.tools import _canonical_symbol, _load_price_history

        frame = _load_price_history(_canonical_symbol(symbol), days)
        if frame is None or getattr(frame, "empty", True):
            return []
        rows = []
        for _, row in frame.iterrows():
            stamp = row.get("TIMESTAMP")
            time = str(stamp)[:10] if stamp is not None else ""
            open_, high, low, close = _finite(row.get("OPEN")), _finite(row.get("HIGH")), _finite(row.get("LOW")), _finite(row.get("CLOSE"))
            volume = _finite(row.get("TOTTRDQTY")) or 0.0
            if time and None not in (open_, high, low, close):
                rows.append({"time": time, "open": open_, "high": high, "low": low, "close": close, "volume": volume})
        return rows
    except Exception:
        return []


def load_intraday_bars(symbol: str, interval: str = "5m") -> list[dict[str, Any]]:
    """Load today's (or recent) intraday OHLC from Yahoo as a Lightweight Charts fallback."""
    token = str(interval or "5m").lower().replace(" ", "")
    if token in {"15", "15m"}:
        yf_interval, period, stamp_mode = "15m", "5d", "multi"
        label = "15m"
    else:
        yf_interval, period, stamp_mode = "5m", "1d", "today"
        label = "5m"
    try:
        import yfinance as yf

        hist = yf.Ticker(yahoo_ticker(symbol)).history(
            period=period, interval=yf_interval, auto_adjust=True
        )
    except Exception:
        return []
    if hist is None or getattr(hist, "empty", True):
        return []
    rows: list[dict[str, Any]] = []
    for ts, row in hist.iterrows():
        open_, high, low, close = _finite(row.get("Open")), _finite(row.get("High")), _finite(row.get("Low")), _finite(row.get("Close"))
        volume = _finite(row.get("Volume")) or 0.0
        if None in (open_, high, low, close):
            continue
        if volume <= 0 and high == low:
            continue
        try:
            local = ts.tz_convert("Asia/Kolkata") if getattr(ts, "tzinfo", None) else ts
            stamp = local.strftime("%H:%M") if stamp_mode == "today" else local.strftime("%m-%d %H:%M")
        except Exception:
            stamp = str(ts)[11:16]
        rows.append({
            "time": stamp,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "interval": label,
        })
    return rows[-80:]


def load_snapshot(symbol: str) -> dict[str, Any]:
    try:
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from terminal.tools import get_technical_setup, resolve_symbol

        resolved = resolve_symbol(symbol)
        ticker = str(resolved.get("symbol") or symbol)
        setup = get_technical_setup(ticker)
        setup["resolved_symbol"] = ticker
        setup["resolve_method"] = resolved.get("method")
        return setup
    except Exception as exc:
        return {"symbol": canonical_symbol(symbol), "error": str(exc)}


def build_payload(bars: list[dict[str, Any]]) -> dict[str, Any]:
    times = [row["time"] for row in bars]
    closes = [float(row["close"]) for row in bars]
    highs = [float(row["high"]) for row in bars]
    lows = [float(row["low"]) for row in bars]
    st_line, st_state = _supertrend(highs, lows, closes)
    macd, signal, hist = _macd(closes)
    return {
        "candles": [{"time": row["time"], "open": row["open"], "high": row["high"], "low": row["low"], "close": row["close"]} for row in bars],
        "volume": [{"time": row["time"], "value": row["volume"], "color": "#14b8a680" if row["close"] >= row["open"] else "#f43f5e80"} for row in bars],
        "sma20": _series(times, _sma(closes, 20)),
        "sma50": _series(times, _sma(closes, 50)),
        "sma200": _series(times, _sma(closes, 200)),
        "rsi": _series(times, _rsi(closes, 14)),
        "macd": _series(times, macd),
        "macd_signal": _series(times, signal),
        "macd_hist": [
            {"time": time, "value": round(value, 4), "color": "#14b8a6" if value >= 0 else "#f43f5e"}
            for time, value in zip(times, hist, strict=False)
            if _finite(value) is not None
        ],
        "supertrend": _series(times, st_line),
        "supertrend_state": st_state,
    }


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, float):
        if value != value:
            return "—"
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return html.escape(str(value))


def render_html(tv_symbol: str, interval: str, snapshot: dict[str, Any], payload: dict[str, Any], page_url: str) -> str:
    rows = [
        ("Agent Adda symbol", snapshot.get("resolved_symbol") or snapshot.get("symbol") or tv_symbol.split(":")[-1]),
        ("As of", snapshot.get("as_of")),
        ("Price", snapshot.get("price")),
        ("SMA 20", snapshot.get("sma20")),
        ("SMA 50", snapshot.get("sma50")),
        ("SMA 200", snapshot.get("sma200")),
        ("RSI 14", snapshot.get("rsi")),
        ("MACD", snapshot.get("macd")),
        ("Supertrend 10×3", snapshot.get("supertrend") or payload.get("supertrend_state")),
        ("ADX 14", snapshot.get("adx")),
        ("Vol vs 20d", snapshot.get("vol_ratio")),
        ("Technical score", snapshot.get("technical_score")),
        ("Bars", len(payload.get("candles") or [])),
        ("Data source", snapshot.get("data_source") or snapshot.get("error") or "local EOD"),
    ]
    metrics = "".join(
        f"<div class='metric'><span>{html.escape(label)}</span><strong>{_fmt(value)}</strong></div>"
        for label, value in rows
    )
    warning = ""
    if not payload.get("candles"):
        warning = "<p class='warn'>No local OHLC bars. Use the TradingView link for the live chart.</p>"
    payload_json = json.dumps(payload)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Chart · {html.escape(tv_symbol)}</title>
  <script src="https://unpkg.com/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js"></script>
  <style>
    :root {{ --bg:#0b1220; --panel:#111827; --ink:#e5eef5; --muted:#8aa0b5; --line:#1f3347; --brand:#38bdf8; --on:#155e75; }}
    * {{ box-sizing:border-box; }}
    html, body {{ margin:0; height:100%; background:var(--bg); color:var(--ink); font:13px/1.4 ui-sans-serif,system-ui,sans-serif; }}
    .shell {{ display:grid; grid-template-columns:260px 1fr; grid-template-rows:auto 1fr; height:100%; }}
    aside {{ grid-row:1 / span 2; padding:16px; border-right:1px solid var(--line); overflow:auto; background:var(--panel); }}
    .toolbar {{ display:flex; flex-wrap:wrap; gap:6px; align-items:center; padding:8px 10px; border-bottom:1px solid var(--line); background:#0f172a; }}
    .group {{ display:flex; gap:4px; align-items:center; padding-right:8px; border-right:1px solid var(--line); }}
    .group:last-child {{ border:0; }}
    button {{ background:#1e293b; color:var(--ink); border:1px solid #334155; border-radius:6px; padding:4px 8px; cursor:pointer; }}
    button.active, button[aria-pressed="true"] {{ background:var(--on); border-color:#22d3ee; }}
    button:hover {{ border-color:var(--brand); }}
    .ohlc {{ color:var(--muted); font-variant-numeric:tabular-nums; }}
    h1 {{ font-size:18px; margin:0 0 6px; }}
    .sub, .note {{ color:var(--muted); font-size:12px; }}
    .warn {{ color:#fca5a5; }}
    .metric {{ padding:7px 0; border-bottom:1px solid var(--line); }}
    .metric span {{ display:block; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.04em; }}
    .stage {{ display:flex; flex-direction:column; min-width:0; min-height:0; }}
    .charts {{ display:grid; grid-template-rows:3fr 1fr 1fr; flex:1; min-height:0; }}
    .charts.hide-rsi {{ grid-template-rows:4fr 0 1fr; }}
    .charts.hide-macd {{ grid-template-rows:4fr 1fr 0; }}
    .charts.hide-rsi.hide-macd {{ grid-template-rows:1fr 0 0; }}
    #price, #rsi, #macd {{ width:100%; height:100%; min-height:0; border-bottom:1px solid var(--line); }}
    .charts.hide-rsi #rsi, .charts.hide-macd #macd {{ display:none; }}
    a {{ color:var(--brand); }}
    @media (max-width:900px) {{ .shell {{ grid-template-columns:1fr; }} aside {{ grid-row:auto; }} }}
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <h1>{html.escape(tv_symbol)}</h1>
      <p class="sub">Agent Adda studies · Asia/Kolkata · click legend buttons to hide lines</p>
      {warning}
      {metrics}
      <p class="note">NSE cash names are blocked on TradingView's embed widget. Chart type, ranges, and studies are toggles on this page. <a href="{html.escape(page_url)}" target="_blank" rel="noopener">Open live TradingView</a></p>
    </aside>
    <div class="toolbar" role="toolbar" aria-label="Chart controls">
      <div class="group" data-chart-types>
        <button type="button" data-chart-type="candles" class="active" title="Candles">Candles</button>
        <button type="button" data-chart-type="bars" title="OHLC bars">Bars</button>
        <button type="button" data-chart-type="line" title="Close line">Line</button>
        <button type="button" data-chart-type="area" title="Area">Area</button>
      </div>
      <div class="group" data-ranges>
        <button type="button" data-range="1M">1M</button>
        <button type="button" data-range="3M">3M</button>
        <button type="button" data-range="6M">6M</button>
        <button type="button" data-range="1Y">1Y</button>
        <button type="button" data-range="ALL" class="active">All</button>
      </div>
      <div class="group" data-indicators>
        <button type="button" data-indicator="volume" aria-pressed="true">Vol</button>
        <button type="button" data-indicator="sma20" aria-pressed="true">SMA20</button>
        <button type="button" data-indicator="sma50" aria-pressed="true">SMA50</button>
        <button type="button" data-indicator="sma200" aria-pressed="true">SMA200</button>
        <button type="button" data-indicator="supertrend" aria-pressed="true">ST</button>
        <button type="button" data-indicator="rsi" aria-pressed="true">RSI</button>
        <button type="button" data-indicator="macd" aria-pressed="true">MACD</button>
      </div>
      <div class="group">
        <button type="button" data-tool="crosshair" class="active">Crosshair</button>
        <button type="button" data-tool="hline">H-line</button>
        <button type="button" data-tool="trend">Trend</button>
        <button type="button" data-tool="clear">Clear lines</button>
      </div>
      <span class="ohlc" id="ohlc">O — H — L — C —</span>
    </div>
    <div class="stage">
      <div class="charts" id="layout">
        <div id="price"></div>
        <div id="rsi"></div>
        <div id="macd"></div>
      </div>
    </div>
  </div>
  <script>
    const data = {payload_json};
    const candles = data.candles || [];
    const dark = {{ layout: {{ background: {{ color: '#0b1220' }}, textColor: '#9fb0c3' }},
      grid: {{ vertLines: {{ color: '#1f3347' }}, horzLines: {{ color: '#1f3347' }} }},
      rightPriceScale: {{ borderColor: '#1f3347' }},
      timeScale: {{ borderColor: '#1f3347', timeVisible: true }},
      crosshair: {{ mode: 0 }} }};
    function makeChart(el, extra) {{
      const chart = LightweightCharts.createChart(el, Object.assign({{ autosize: true }}, dark, extra || {{}}));
      new ResizeObserver(() => chart.applyOptions({{ width: el.clientWidth, height: el.clientHeight }})).observe(el);
      return chart;
    }}
    const priceEl = document.getElementById('price');
    const layout = document.getElementById('layout');
    const priceChart = makeChart(priceEl);
    const rsiChart = makeChart(document.getElementById('rsi'), {{ timeScale: {{ visible: false, borderColor: '#1f3347' }} }});
    const macdChart = makeChart(document.getElementById('macd'));
    let priceSeries = null;
    const overlays = {{
      volume: priceChart.addHistogramSeries({{ priceFormat: {{ type: 'volume' }}, priceScaleId: 'vol' }}),
      sma20: priceChart.addLineSeries({{ color: '#38bdf8', lineWidth: 2, title: 'SMA 20' }}),
      sma50: priceChart.addLineSeries({{ color: '#22c55e', lineWidth: 2, title: 'SMA 50' }}),
      sma200: priceChart.addLineSeries({{ color: '#f97316', lineWidth: 2, title: 'SMA 200' }}),
      supertrend: priceChart.addLineSeries({{ color: '#a78bfa', lineWidth: 2, title: 'Supertrend 10x3' }})
    }};
    priceChart.priceScale('vol').applyOptions({{ scaleMargins: {{ top: 0.82, bottom: 0 }} }});
    overlays.volume.setData(data.volume || []);
    overlays.sma20.setData(data.sma20 || []);
    overlays.sma50.setData(data.sma50 || []);
    overlays.sma200.setData(data.sma200 || []);
    overlays.supertrend.setData(data.supertrend || []);
    rsiChart.addLineSeries({{ color: '#c084fc', lineWidth: 2, title: 'RSI 14' }}).setData(data.rsi || []);
    macdChart.addHistogramSeries({{ title: 'MACD hist' }}).setData(data.macd_hist || []);
    macdChart.addLineSeries({{ color: '#38bdf8', lineWidth: 2, title: 'MACD' }}).setData(data.macd || []);
    macdChart.addLineSeries({{ color: '#f59e0b', lineWidth: 2, title: 'Signal' }}).setData(data.macd_signal || []);
    function setChartType(type) {{
      if (priceSeries) priceChart.removeSeries(priceSeries);
      if (type === 'bars') priceSeries = priceChart.addBarSeries({{ upColor: '#14b8a6', downColor: '#f43f5e' }});
      else if (type === 'line') priceSeries = priceChart.addLineSeries({{ color: '#e2e8f0', lineWidth: 2 }});
      else if (type === 'area') priceSeries = priceChart.addAreaSeries({{ lineColor: '#38bdf8', topColor: '#38bdf855', bottomColor: '#38bdf800' }});
      else priceSeries = priceChart.addCandlestickSeries({{ upColor: '#14b8a6', downColor: '#f43f5e', borderVisible: false, wickUpColor: '#14b8a6', wickDownColor: '#f43f5e' }});
      const seriesData = (type === 'line' || type === 'area')
        ? candles.map(row => ({{ time: row.time, value: row.close }}))
        : candles;
      priceSeries.setData(seriesData);
      document.querySelectorAll('[data-chart-type]').forEach(btn => btn.classList.toggle('active', btn.dataset.chartType === type));
    }}
    setChartType('candles');
    function setRange(key) {{
      if (!candles.length) return;
      const last = candles[candles.length - 1].time;
      const end = Date.parse(last + 'T00:00:00Z');
      const days = {{ '1M': 31, '3M': 93, '6M': 186, '1Y': 366 }}[key];
      if (!days) {{ priceChart.timeScale().fitContent(); }}
      else {{
        const start = new Date(end - days * 86400000).toISOString().slice(0, 10);
        priceChart.timeScale().setVisibleRange({{ from: start, to: last }});
      }}
      document.querySelectorAll('[data-range]').forEach(btn => btn.classList.toggle('active', btn.dataset.range === key));
    }}
    function setVisible(name, on) {{
      if (overlays[name]) overlays[name].applyOptions({{ visible: on }});
      if (name === 'rsi') layout.classList.toggle('hide-rsi', !on);
      if (name === 'macd') layout.classList.toggle('hide-macd', !on);
      const btn = document.querySelector('[data-indicator="' + name + '"]');
      if (btn) btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    }}
    let tool = 'crosshair';
    let trendStart = null;
    const drawings = [];
    function setTool(name) {{
      tool = name;
      trendStart = null;
      document.querySelectorAll('[data-tool]').forEach(btn => btn.classList.toggle('active', btn.dataset.tool === name));
    }}
    priceChart.subscribeCrosshairMove(param => {{
      const bar = param && param.time ? candles.find(row => row.time === param.time) : candles[candles.length - 1];
      if (!bar) return;
      document.getElementById('ohlc').textContent =
        'O ' + bar.open.toFixed(2) + '  H ' + bar.high.toFixed(2) + '  L ' + bar.low.toFixed(2) + '  C ' + bar.close.toFixed(2);
    }});
    function clickPrice(param) {{
      if (!param || param.time == null || !priceSeries) return null;
      if (param.seriesData && param.seriesData.get) {{
        const point = param.seriesData.get(priceSeries);
        if (point) return point.close != null ? point.close : point.value;
      }}
      return param.point ? priceSeries.coordinateToPrice(param.point.y) : null;
    }}
    priceChart.subscribeClick(param => {{
      const value = clickPrice(param);
      if (value == null) return;
      if (tool === 'hline') {{
        drawings.push({{ kind: 'hline', obj: priceSeries.createPriceLine({{ price: value, color: '#fbbf24', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'H ' + Number(value).toFixed(2) }}) }});
      }}
      if (tool === 'trend') {{
        if (!trendStart) {{ trendStart = {{ time: param.time, value: Number(value) }}; return; }}
        const line = priceChart.addLineSeries({{ color: '#fbbf24', lineWidth: 2, lastValueVisible: false, priceLineVisible: false }});
        const points = [trendStart, {{ time: param.time, value: Number(value) }}].sort((a, b) => a.time < b.time ? -1 : 1);
        line.setData(points);
        drawings.push({{ kind: 'series', obj: line }});
        trendStart = null;
      }}
    }});
    document.querySelector('[data-chart-types]').addEventListener('click', event => {{
      const type = event.target.dataset.chartType; if (type) setChartType(type);
    }});
    document.querySelector('[data-ranges]').addEventListener('click', event => {{
      const range = event.target.dataset.range; if (range) setRange(range);
    }});
    document.querySelector('[data-indicators]').addEventListener('click', event => {{
      const name = event.target.dataset.indicator;
      if (!name) return;
      const on = event.target.getAttribute('aria-pressed') !== 'true';
      setVisible(name, on);
    }});
    document.querySelectorAll('[data-tool]').forEach(btn => btn.addEventListener('click', () => {{
      if (btn.dataset.tool === 'clear') {{
        drawings.splice(0).forEach(item => {{
          try {{ if (item.kind === 'series') priceChart.removeSeries(item.obj); }} catch (err) {{}}
          try {{ if (item.kind === 'hline' && priceSeries) priceSeries.removePriceLine(item.obj); }} catch (err) {{}}
        }});
        return;
      }}
      setTool(btn.dataset.tool);
    }}));
    const charts = [priceChart, rsiChart, macdChart];
    charts.forEach(source => {{
      source.timeScale().subscribeVisibleLogicalRangeChange(range => {{
        charts.forEach(target => {{ if (target !== source && range) target.timeScale().setVisibleLogicalRange(range); }});
      }});
    }});
    priceChart.timeScale().fitContent();
  </script>
</body>
</html>
"""


def write_chart(
    symbol: str,
    interval: str = "D",
    output_path: Path | None = None,
    include_snapshot: bool = True,
) -> dict[str, Any]:
    interval = str(interval or "D").upper()
    if interval not in INTERVALS:
        raise ValueError(f"interval must be one of {sorted(INTERVALS)}")
    tv_symbol = tradingview_symbol(symbol)
    snapshot = load_snapshot(symbol) if include_snapshot else {"symbol": canonical_symbol(symbol)}
    resolved = str(snapshot.get("resolved_symbol") or snapshot.get("symbol") or canonical_symbol(symbol))
    if include_snapshot and resolved and ":" not in str(symbol):
        tv_symbol = tradingview_symbol(resolved)
    bars = load_bars(resolved)
    payload = build_payload(bars)
    html_doc = render_html(tv_symbol, interval, snapshot, payload, tradingview_page_url(tv_symbol, interval))
    destination = output_path or (CHART_ROOT / f"{resolved.lower()}_{interval.lower()}.html")
    if not destination.is_absolute():
        destination = PROJECT_ROOT / destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html_doc, encoding="utf-8")
    return {
        "success": True,
        "symbol": resolved,
        "tradingview_symbol": tv_symbol,
        "interval": interval,
        "path": str(destination),
        "url": tradingview_page_url(tv_symbol, interval),
        "bar_count": len(bars),
        "snapshot_error": snapshot.get("error"),
        "widget_note": "NSE cash symbols are blocked on TradingView's embed widget; this file plots Agent Adda EOD with the same studies.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", help="NSE ticker or company name")
    parser.add_argument("--interval", default="D", help="Displayed interval label and TradingView link interval")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--open", action="store_true", help="Open the HTML chart in the default browser")
    parser.add_argument("--no-snapshot", action="store_true", help="Skip get_technical_setup sidebar")
    parser.add_argument("--canvas", action="store_true", help="Also write a Cursor Canvas (.canvas.tsx) with LineChart visuals")
    parser.add_argument("--canvas-output", type=Path, help="Override canvas output path")
    parser.add_argument("--intraday-interval", default="5m", help="Canvas intraday interval: 5m or 15m")
    parser.add_argument("--no-intraday", action="store_true", help="Skip the canvas 5m/15m pane")
    args = parser.parse_args()
    try:
        result = write_chart(
            args.symbol,
            interval=args.interval,
            output_path=args.output,
            include_snapshot=not args.no_snapshot,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    if args.canvas:
        canvas_mod_path = Path(__file__).resolve().parent / "build_chart_canvas.py"
        spec = importlib.util.spec_from_file_location("build_chart_canvas", canvas_mod_path)
        if spec is None or spec.loader is None:
            print("error: cannot load build_chart_canvas.py", file=sys.stderr)
            return 2
        canvas_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(canvas_mod)
        canvas_result = canvas_mod.write_chart_canvas(
            [result["symbol"]],
            output_path=args.canvas_output,
            include_snapshot=not args.no_snapshot,
            include_intraday=not args.no_intraday,
            intra_interval=args.intraday_interval,
        )
        print(json.dumps({"canvas": canvas_result}, indent=2))
    if args.open:
        webbrowser.open(Path(result["path"]).resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
