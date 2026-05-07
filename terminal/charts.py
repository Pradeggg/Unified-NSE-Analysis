"""
terminal/charts.py — Charts for Agent Adda.

Two modes:
  1. ASCII terminal chart  (plotext)    — render_chart()  — immediate, in-terminal
  2. Interactive HTML chart (Plotly)    — render_html_chart() — opens in browser

ASCII fixes vs v1:
  - EMA overlays use numeric x-axis indices (no duplicate legend)
  - RSI / MACD indicator panels use numeric x-axis to avoid plotext
    misreading negative floats as date values
  - Each subplot sized independently; no shared ylim bug
"""

from __future__ import annotations

import re
import tempfile
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).parent.parent

# ── yfinance symbol helpers ────────────────────────────────────────────────────

_INDEX_MAP = {
    "NIFTY":        "^NSEI",
    "NIFTY 50":     "^NSEI",
    "BANKNIFTY":    "^NSEBANK",
    "NIFTY BANK":   "^NSEBANK",
    "SENSEX":       "^BSESN",
    "FINNIFTY":     "NIFTY_FIN_SERVICE.NS",
    "MIDCAP":       "^NSEMDCP50",
}

_TF_PERIOD_MAP = {
    "1d":   ("1d",  "5m"),
    "5d":   ("5d",  "15m"),
    "1w":   ("5d",  "15m"),
    "1mo":  ("1mo", "1d"),
    "3mo":  ("3mo", "1d"),
    "6mo":  ("6mo", "1d"),
    "1y":   ("1y",  "1d"),
    "2y":   ("2y",  "1wk"),
}


def _yf_symbol(symbol: str) -> str:
    sym = symbol.strip().upper()
    if sym in _INDEX_MAP:
        return _INDEX_MAP[sym]
    if not sym.endswith(".NS") and not sym.startswith("^"):
        return sym + ".NS"
    return sym


def _fetch_ohlcv(symbol: str, timeframe: str = "3mo") -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError:
        return pd.DataFrame()

    period, interval = _TF_PERIOD_MAP.get(timeframe, ("3mo", "1d"))
    yf_sym = _yf_symbol(symbol)
    try:
        df = yf.download(yf_sym, period=period, interval=interval,
                         progress=False, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df = df.reset_index()
        date_col = "Datetime" if "Datetime" in df.columns else "Date"
        df = df.rename(columns={date_col: "Date"})
        df = df.dropna(subset=["Close"])
        for col in ["Open", "High", "Low", "Close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()


# ── Indicator calculations ─────────────────────────────────────────────────────

def _rsi(closes: list[float], period: int = 14) -> list[float]:
    s = pd.Series(closes, dtype=float)
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    rs   = gain / loss.replace(0, 1e-9)
    return (100 - 100 / (1 + rs)).tolist()


def _macd(closes: list[float]) -> tuple[list[float], list[float], list[float]]:
    s     = pd.Series(closes, dtype=float)
    ema12 = s.ewm(span=12, adjust=False).mean()
    ema26 = s.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    sig   = macd.ewm(span=9, adjust=False).mean()
    hist  = macd - sig
    return macd.tolist(), sig.tolist(), hist.tolist()


def _ema(closes: list[float], span: int) -> list[float]:
    return pd.Series(closes, dtype=float).ewm(span=span, adjust=False).mean().tolist()


def _bb(closes: list[float], window: int = 20, num_std: float = 2.0):
    s    = pd.Series(closes, dtype=float)
    mid  = s.rolling(window).mean()
    std  = s.rolling(window).std()
    return (mid - num_std * std).tolist(), mid.tolist(), (mid + num_std * std).tolist()


def _strip_ansi(s: str) -> str:
    return re.sub(r'\x1b\[[0-9;]*m', '', s)


def _date_labels(df: pd.DataFrame) -> list[str]:
    col = df["Date"]
    if hasattr(col.iloc[0], 'strftime'):
        return [d.strftime('%d/%m/%Y') for d in col]
    parsed = pd.to_datetime(col, utc=True).dt.tz_localize(None)
    return [d.strftime('%d/%m/%Y') for d in parsed]


def _terminal_width() -> int:
    try:
        import shutil
        return min(shutil.get_terminal_size().columns - 2, 110)
    except Exception:
        return 90


# ═════════════════════════════════════════════════════════════════════════════
# ASCII CHART (plotext)
# ═════════════════════════════════════════════════════════════════════════════

def render_chart(
    symbol: str,
    timeframe: str = "3mo",
    indicators: Optional[list[str]] = None,
    width: Optional[int] = None,
) -> str:
    """
    Render an ASCII candlestick chart in the terminal using plotext.

    Key fixes vs v1:
    - EMAs rendered on numeric x-axis to avoid duplicate legend entries
    - RSI / MACD subplots use numeric x-axis so plotext never confuses
      negative floats with date strings
    - Volume bars colour-coded green/red per candle direction
    """
    try:
        import plotext as _plt
    except ImportError:
        return "❌  plotext not installed. Run: pip install plotext"

    if indicators is None:
        indicators = ["volume", "rsi"]
    indicators = [i.lower() for i in indicators]

    df = _fetch_ohlcv(symbol, timeframe)
    if df.empty:
        return f"❌  No data found for {symbol} (timeframe: {timeframe})"

    # Limit bars for readability
    max_bars = 55
    if len(df) > max_bars:
        df = df.tail(max_bars).reset_index(drop=True)

    n = len(df)
    dates  = _date_labels(df)
    opens  = df["Open"].tolist()
    highs  = df["High"].tolist()
    lows   = df["Low"].tolist()
    closes = df["Close"].tolist()
    vols   = df["Volume"].tolist() if "Volume" in df.columns else []
    xs     = list(range(n))            # numeric indices for indicator panels

    w = width or _terminal_width()

    show_volume = "volume" in indicators and vols
    show_rsi    = "rsi" in indicators
    show_macd   = "macd" in indicators

    n_panels = 1 + show_volume + show_rsi + show_macd

    # Height allocation
    h_candle = max(16, 30 - 4 * (n_panels - 1))
    h_vol    = 6
    h_rsi    = 7
    h_macd   = 7

    current_price = closes[-1]
    prev          = closes[-2] if n >= 2 else closes[-1]
    chg_pct       = 100 * (current_price - prev) / prev if prev else 0.0
    sign          = "▲" if chg_pct >= 0 else "▼"
    tf_label      = timeframe.upper()

    _plt.clf()
    _plt.theme("dark")

    if n_panels > 1:
        _plt.subplots(n_panels, 1)

    panel = 1

    # ── Panel 1: Candlestick ─────────────────────────────────────────────────
    if n_panels > 1:
        _plt.subplot(panel, 1)

    candle_data = {"Open": opens, "Close": closes, "High": highs, "Low": lows}
    _plt.candlestick(dates, candle_data)

    # EMA overlays — use same date x-axis, no label (avoids duplicate legend)
    if n >= 20:
        _plt.plot(dates, _ema(closes, 20), color="cyan")
    if n >= 50:
        _plt.plot(dates, _ema(closes, 50), color="orange")

    _plt.title(
        f"{symbol.upper()}  Rs.{current_price:,.1f}  "
        f"{sign}{abs(chg_pct):.2f}%  ({tf_label})"
        + ("  EMA20" if n >= 20 else "")
        + ("  EMA50" if n >= 50 else "")
    )
    _plt.plotsize(w, h_candle)
    panel += 1

    # ── Panel 2: Volume ──────────────────────────────────────────────────────
    if show_volume:
        if n_panels > 1:
            _plt.subplot(panel, 1)
        colors = ["green" if c >= o else "red" for c, o in zip(closes, opens)]
        # Use date x-axis for volume (same as candles, no confusion)
        _plt.bar(dates, vols, color=colors)
        _plt.title("Volume")
        _plt.plotsize(w, h_vol)
        panel += 1

    # ── Panel 3: RSI — numeric x-axis to avoid date misread ─────────────────
    if show_rsi:
        if n_panels > 1:
            _plt.subplot(panel, 1)
        rsi_vals = _rsi(closes, 14)
        _plt.plot(xs, rsi_vals, color="yellow")
        _plt.hline(70, color="red")
        _plt.hline(50, color="white")
        _plt.hline(30, color="green")
        _plt.title(f"RSI(14)  current={rsi_vals[-1]:.1f}")
        _plt.ylim(0, 100)
        _plt.plotsize(w, h_rsi)
        panel += 1

    # ── Panel 4: MACD — numeric x-axis ──────────────────────────────────────
    if show_macd:
        if n_panels > 1:
            _plt.subplot(panel, 1)
        macd_line, sig_line, hist_vals = _macd(closes)
        _plt.plot(xs, macd_line, color="cyan")
        _plt.plot(xs, sig_line,  color="orange")
        h_colors = ["green" if h >= 0 else "red" for h in hist_vals]
        _plt.bar(xs, hist_vals, color=h_colors)
        _plt.hline(0, color="white")
        sig_str = "BULL" if macd_line[-1] > sig_line[-1] else "BEAR"
        _plt.title(f"MACD(12,26,9)  {sig_str}  hist={hist_vals[-1]:.2f}")
        _plt.plotsize(w, h_macd)

    out = _plt.build()
    return _strip_ansi(out)


# ═════════════════════════════════════════════════════════════════════════════
# HTML CHART (Plotly) — first-class quality
# ═════════════════════════════════════════════════════════════════════════════

_HTML_CHART_DIR = ROOT / "data" / "charts"


def render_html_chart(
    symbol: str,
    timeframe: str = "3mo",
    indicators: Optional[list[str]] = None,
    open_browser: bool = True,
) -> str:
    """
    Generate a full-featured interactive HTML chart using Plotly.

    Panels (top to bottom):
      1. Candlestick with EMA20 / EMA50 / Bollinger Bands
      2. Volume bars (green/red)
      3. RSI(14) with overbought/oversold bands
      4. MACD(12,26,9) — line + signal + histogram

    Saves to data/charts/<symbol>_<timeframe>.html and auto-opens in browser.
    Returns the file path.
    """
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        return "❌  plotly not installed. Run: pip install plotly"

    if indicators is None:
        indicators = ["volume", "rsi", "macd"]
    indicators = [i.lower() for i in indicators]

    df = _fetch_ohlcv(symbol, timeframe)
    if df.empty:
        return f"❌  No data found for {symbol} (timeframe: {timeframe})"

    n = len(df)
    dates_raw = pd.to_datetime(df["Date"], utc=True).dt.tz_localize(None)
    opens  = df["Open"].tolist()
    highs  = df["High"].tolist()
    lows   = df["Low"].tolist()
    closes = df["Close"].tolist()
    vols   = df["Volume"].tolist() if "Volume" in df.columns else [0] * n

    show_volume = "volume" in indicators
    show_rsi    = "rsi" in indicators
    show_macd   = "macd" in indicators

    # ── Build subplot grid ───────────────────────────────────────────────────
    row_heights   = [0.55]
    subplot_titles = [f"{symbol.upper()} — {timeframe.upper()}"]
    specs         = [[ {"secondary_y": False} ]]

    if show_volume:
        row_heights.append(0.12)
        subplot_titles.append("Volume")
        specs.append([ {"secondary_y": False} ])
    if show_rsi:
        row_heights.append(0.15)
        subplot_titles.append("RSI (14)")
        specs.append([ {"secondary_y": False} ])
    if show_macd:
        row_heights.append(0.18)
        subplot_titles.append("MACD (12, 26, 9)")
        specs.append([ {"secondary_y": False} ])

    n_rows = len(row_heights)
    fig = make_subplots(
        rows=n_rows, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=row_heights,
        subplot_titles=subplot_titles,
        specs=specs,
    )

    row = 1

    # ── Row 1: Candlestick ───────────────────────────────────────────────────
    up_color   = "#26A69A"   # teal
    down_color = "#EF5350"   # red

    fig.add_trace(go.Candlestick(
        x=dates_raw,
        open=opens, high=highs, low=lows, close=closes,
        increasing_line_color=up_color,
        decreasing_line_color=down_color,
        increasing_fillcolor=up_color,
        decreasing_fillcolor=down_color,
        name="Price",
        showlegend=False,
    ), row=row, col=1)

    # EMA 20
    if n >= 20:
        ema20 = _ema(closes, 20)
        fig.add_trace(go.Scatter(
            x=dates_raw, y=ema20,
            line=dict(color="#00BCD4", width=1.2),
            name="EMA 20", mode="lines",
        ), row=row, col=1)

    # EMA 50
    if n >= 50:
        ema50 = _ema(closes, 50)
        fig.add_trace(go.Scatter(
            x=dates_raw, y=ema50,
            line=dict(color="#FF9800", width=1.2),
            name="EMA 50", mode="lines",
        ), row=row, col=1)

    # EMA 200
    if n >= 200:
        ema200 = _ema(closes, 200)
        fig.add_trace(go.Scatter(
            x=dates_raw, y=ema200,
            line=dict(color="#AB47BC", width=1.2, dash="dot"),
            name="EMA 200", mode="lines",
        ), row=row, col=1)

    # Bollinger Bands
    if n >= 20:
        bb_lo, bb_mid, bb_hi = _bb(closes, 20, 2.0)
        fig.add_trace(go.Scatter(
            x=dates_raw, y=bb_hi,
            line=dict(color="rgba(150,150,255,0.4)", width=1),
            name="BB Upper", mode="lines", showlegend=False,
        ), row=row, col=1)
        fig.add_trace(go.Scatter(
            x=dates_raw, y=bb_lo,
            fill="tonexty",
            fillcolor="rgba(150,150,255,0.06)",
            line=dict(color="rgba(150,150,255,0.4)", width=1),
            name="BB Bands", mode="lines",
        ), row=row, col=1)

    row += 1

    # ── Row 2: Volume ────────────────────────────────────────────────────────
    if show_volume:
        vol_colors = [up_color if c >= o else down_color
                      for c, o in zip(closes, opens)]
        fig.add_trace(go.Bar(
            x=dates_raw, y=vols,
            marker_color=vol_colors,
            name="Volume", showlegend=False,
        ), row=row, col=1)
        row += 1

    # ── Row 3: RSI ───────────────────────────────────────────────────────────
    if show_rsi:
        rsi_vals = _rsi(closes, 14)
        fig.add_trace(go.Scatter(
            x=dates_raw, y=rsi_vals,
            line=dict(color="#F9A825", width=1.5),
            name="RSI(14)", mode="lines",
        ), row=row, col=1)
        # Overbought/oversold fill bands
        fig.add_hrect(y0=70, y1=100, fillcolor="rgba(239,83,80,0.08)",
                      line_width=0, row=row, col=1)
        fig.add_hrect(y0=0,  y1=30,  fillcolor="rgba(38,166,154,0.08)",
                      line_width=0, row=row, col=1)
        for lvl, col in [(70, "#EF5350"), (50, "rgba(255,255,255,0.3)"), (30, "#26A69A")]:
            fig.add_hline(y=lvl, line_dash="dot",
                          line_color=col, line_width=0.8,
                          row=row, col=1)
        fig.update_yaxes(range=[0, 100], row=row, col=1)
        row += 1

    # ── Row 4: MACD ──────────────────────────────────────────────────────────
    if show_macd:
        macd_line, sig_line, hist_vals = _macd(closes)
        hist_colors = [up_color if h >= 0 else down_color for h in hist_vals]
        fig.add_trace(go.Bar(
            x=dates_raw, y=hist_vals,
            marker_color=hist_colors,
            name="MACD Hist", showlegend=False,
            opacity=0.7,
        ), row=row, col=1)
        fig.add_trace(go.Scatter(
            x=dates_raw, y=macd_line,
            line=dict(color="#00BCD4", width=1.5),
            name="MACD", mode="lines",
        ), row=row, col=1)
        fig.add_trace(go.Scatter(
            x=dates_raw, y=sig_line,
            line=dict(color="#FF9800", width=1.5),
            name="Signal", mode="lines",
        ), row=row, col=1)
        fig.add_hline(y=0, line_dash="dot",
                      line_color="rgba(255,255,255,0.3)", line_width=0.8,
                      row=row, col=1)

    # ── Layout — dark TradingView-like theme ─────────────────────────────────
    current_price = closes[-1]
    prev          = closes[-2] if n >= 2 else closes[-1]
    chg_pct       = 100 * (current_price - prev) / prev if prev else 0.0
    sign          = "▲" if chg_pct >= 0 else "▼"

    fig.update_layout(
        title=dict(
            text=(
                f"<b>{symbol.upper()}</b>  "
                f"₹{current_price:,.2f}  "
                f"<span style='color:{'#26A69A' if chg_pct >= 0 else '#EF5350'}'>"
                f"{sign} {abs(chg_pct):.2f}%</span>"
                f"  <span style='font-size:13px;color:#888'>{timeframe.upper()}</span>"
            ),
            font=dict(size=18, color="#E0E0E0"),
            x=0.01,
        ),
        paper_bgcolor="#131722",
        plot_bgcolor="#131722",
        font=dict(family="Inter, Arial, sans-serif", size=12, color="#D1D4DC"),
        legend=dict(
            bgcolor="rgba(19,23,34,0.8)",
            bordercolor="#2A2E39",
            borderwidth=1,
            font=dict(size=11),
            orientation="h",
            yanchor="bottom", y=1.01,
            xanchor="left", x=0,
        ),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="#1E222D",
            bordercolor="#2A2E39",
            font=dict(color="#D1D4DC", size=12),
        ),
        margin=dict(l=60, r=30, t=80, b=40),
        height=750 + 80 * (n_rows - 1),
    )

    # Style all axes
    axis_style = dict(
        gridcolor="#1E222D",
        gridwidth=1,
        linecolor="#2A2E39",
        tickcolor="#2A2E39",
        tickfont=dict(color="#787B86", size=11),
        zerolinecolor="#2A2E39",
        showgrid=True,
    )
    for i in range(1, n_rows + 1):
        fig.update_xaxes(axis_style, row=i, col=1)
        fig.update_yaxes(axis_style, row=i, col=1)

    # Spike lines for crosshair
    for i in range(1, n_rows + 1):
        fig.update_xaxes(
            showspikes=True, spikecolor="#787B86",
            spikethickness=1, spikedash="dot", spikemode="across",
            row=i, col=1,
        )
        fig.update_yaxes(
            showspikes=True, spikecolor="#787B86",
            spikethickness=1, spikedash="dot",
            row=i, col=1,
        )

    # ── Save and open ────────────────────────────────────────────────────────
    _HTML_CHART_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"{symbol.upper()}_{timeframe}.html"
    fpath = _HTML_CHART_DIR / fname
    fig.write_html(
        str(fpath),
        config={
            "scrollZoom": True,
            "displayModeBar": True,
            "modeBarButtonsToAdd": ["drawline", "drawopenpath", "eraseshape"],
            "modeBarButtonsToRemove": ["lasso2d", "select2d"],
        },
        include_plotlyjs="cdn",
        full_html=True,
    )

    if open_browser:
        webbrowser.open(f"file://{fpath}")

    return str(fpath)


# ── Shared summary ─────────────────────────────────────────────────────────────

def chart_summary(symbol: str, timeframe: str = "3mo") -> dict:
    """
    Return chart data summary dict for LLM context.
    Includes: current price, change%, RSI, MACD signal, EMA positions, key levels.
    """
    df = _fetch_ohlcv(symbol, timeframe)
    if df.empty:
        return {"error": f"No data for {symbol}"}

    closes = df["Close"].tolist()
    highs  = df["High"].tolist()
    lows   = df["Low"].tolist()
    c    = closes[-1]
    prev = closes[-2] if len(closes) >= 2 else c

    rsi_val = _rsi(closes, 14)[-1] if len(closes) >= 15 else None
    macd_line, sig_line, hist = _macd(closes)
    macd_signal = "bullish" if macd_line[-1] > sig_line[-1] else "bearish"

    ema20  = _ema(closes, 20)[-1] if len(closes) >= 20 else None
    ema50  = _ema(closes, 50)[-1] if len(closes) >= 50 else None
    ema200 = _ema(closes, 200)[-1] if len(closes) >= 200 else None

    return {
        "symbol":         symbol.upper(),
        "timeframe":      timeframe,
        "current_price":  round(c, 2),
        "prev_close":     round(prev, 2),
        "change_pct":     round(100 * (c - prev) / prev, 2) if prev else 0,
        "period_high":    round(max(highs), 2),
        "period_low":     round(min(lows), 2),
        "rsi_14":         round(rsi_val, 1) if rsi_val is not None else None,
        "macd_signal":    macd_signal,
        "macd_hist":      round(hist[-1], 3),
        "ema20":          round(ema20, 2) if ema20 else None,
        "ema50":          round(ema50, 2) if ema50 else None,
        "ema200":         round(ema200, 2) if ema200 else None,
        "price_vs_ema20": "above" if ema20 and c > ema20 else "below",
        "price_vs_ema50": "above" if ema50 and c > ema50 else "below",
        "bars":           len(closes),
    }


def render_sparkline(symbol: str, days: int = 20) -> str:
    """Compact one-line sparkline for inline use."""
    try:
        import plotext as _plt
    except ImportError:
        return "(plotext not installed)"
    df = _fetch_ohlcv(symbol, "1mo")
    if df.empty:
        return "(no data)"
    closes = df["Close"].tail(days).tolist()
    dates  = _date_labels(df.tail(days))
    _plt.clf()
    _plt.plot(dates, closes, color="cyan")
    _plt.plotsize(50, 5)
    _plt.title(f"{symbol} ({days}d)")
    return _strip_ansi(_plt.build())
