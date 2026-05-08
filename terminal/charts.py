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


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float]:
    h = pd.Series(highs, dtype=float)
    l = pd.Series(lows, dtype=float)
    c = pd.Series(closes, dtype=float)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean().tolist()


def _stoch(highs: list[float], lows: list[float], closes: list[float], k: int = 14, d: int = 3):
    h = pd.Series(highs, dtype=float)
    l = pd.Series(lows, dtype=float)
    c = pd.Series(closes, dtype=float)
    lo = l.rolling(k).min()
    hi = h.rolling(k).max()
    pct_k = 100 * (c - lo) / (hi - lo + 1e-9)
    pct_d = pct_k.rolling(d).mean()
    return pct_k.tolist(), pct_d.tolist()


def _heikin_ashi(opens, highs, lows, closes):
    ha_c = [(o + h + l + c) / 4 for o, h, l, c in zip(opens, highs, lows, closes)]
    ha_o = [0.0] * len(opens)
    ha_o[0] = (opens[0] + closes[0]) / 2
    for i in range(1, len(opens)):
        ha_o[i] = (ha_o[i - 1] + ha_c[i - 1]) / 2
    ha_h = [max(h, ho, hc) for h, ho, hc in zip(highs, ha_o, ha_c)]
    ha_l = [min(l, lo, lc) for l, lo, lc in zip(lows, ha_o, ha_c)]
    return ha_o, ha_h, ha_l, ha_c


def _supertrend(highs, lows, closes, period: int = 7, mult: float = 3.0):
    atr = pd.Series(_atr(highs, lows, closes, period))
    hl2 = pd.Series([(h + l) / 2 for h, l in zip(highs, lows)])
    upper = (hl2 + mult * atr).tolist()
    lower = (hl2 - mult * atr).tolist()
    n = len(closes)
    st = [0.0] * n
    direction = [1] * n  # 1=bullish, -1=bearish
    for i in range(1, n):
        upper[i] = min(upper[i], upper[i - 1]) if closes[i - 1] > upper[i - 1] else upper[i]
        lower[i] = max(lower[i], lower[i - 1]) if closes[i - 1] < lower[i - 1] else lower[i]
        if direction[i - 1] == -1 and closes[i] > upper[i - 1]:
            direction[i] = 1
        elif direction[i - 1] == 1 and closes[i] < lower[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]
        st[i] = lower[i] if direction[i] == 1 else upper[i]
    return direction, st


def _pivot_sr(highs: list[float], lows: list[float], n: int = 5, tol: float = 0.005) -> list[float]:
    """Swing-pivot S/R: local max/min over n bars each side, clustered within tol."""
    hi = pd.Series(highs)
    lo = pd.Series(lows)
    levels: list[float] = []
    for i in range(n, len(hi) - n):
        if hi[i] == hi[i - n: i + n + 1].max():
            levels.append(float(hi[i]))
        if lo[i] == lo[i - n: i + n + 1].min():
            levels.append(float(lo[i]))
    levels.sort()
    clustered: list[float] = []
    for lv in levels:
        if clustered and abs(lv - clustered[-1]) / (clustered[-1] + 1e-9) < tol:
            clustered[-1] = (clustered[-1] + lv) / 2
        else:
            clustered.append(lv)
    return clustered


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
    height: Optional[int] = None,
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

    show_volume = "volume" in indicators and len(vols) > 0
    show_rsi    = "rsi" in indicators
    show_macd   = "macd" in indicators

    n_panels = 1 + show_volume + show_rsi + show_macd

    # Height allocation — use caller-supplied height if provided
    if height is not None:
        h_candle = max(10, height - 4 * (n_panels - 1))
    else:
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

    chg_colour = "green" if chg_pct >= 0 else "red"
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
        cur_rsi  = rsi_vals[-1]
        # Color the RSI line: red if overbought, green if oversold, yellow otherwise
        rsi_color = "red" if cur_rsi >= 70 else ("green" if cur_rsi <= 30 else "yellow")
        _plt.plot(xs, rsi_vals, color=rsi_color)
        _plt.hline(70, color="red")
        _plt.hline(50, color=(204, 204, 204))   # light gray midline
        _plt.hline(30, color="green")
        _plt.title(f"RSI(14)  current={cur_rsi:.1f}")
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
        _plt.hline(0, color=(204, 204, 204))
        sig_str = "BULL" if macd_line[-1] > sig_line[-1] else "BEAR"
        _plt.title(f"MACD(12,26,9)  {sig_str}  hist={hist_vals[-1]:.2f}")
        _plt.plotsize(w, h_macd)

    out = _plt.build()
    return out   # return with ANSI colors intact


# ═════════════════════════════════════════════════════════════════════════════
# HTML CHART (Plotly) — enhanced, first-class quality
# ═════════════════════════════════════════════════════════════════════════════

_HTML_CHART_DIR = ROOT / "data" / "charts"


def _build_chart_html(
    symbol: str,
    timeframe: str,
    plotly_div: str,
    sr_count: int,
    ema_spans: list[int],
    panel_traces: "dict[str, list[int]]",
) -> str:
    """Wrap Plotly chart div in a dark GitHub-style HTML page with toolbar."""
    import json as _json

    ema_btns = " ".join(
        f'<button class="tb-btn active" data-name="EMA {s}" '
        f"onclick=\"toggleTrace('EMA {s}')\">EMA{s}</button>"
        for s in ema_spans
    )
    sr_label  = f"S/R ({sr_count})" if sr_count else "S/R"
    sr_active = "active" if sr_count else ""

    # Indicator panel toggle buttons (only for panels that were actually added)
    _panel_order = [("volume", "Volume"), ("rsi", "RSI"), ("stoch", "Stoch"), ("macd", "MACD")]
    panel_btns = " ".join(
        f'<button class="tb-btn active" data-panel="{key}" onclick="togglePanel(\'{key}\')">{label}</button>'
        for key, label in _panel_order
        if key in panel_traces
    )
    # JS data for panel → trace indices mapping
    pt_json        = _json.dumps(panel_traces)
    active_json    = _json.dumps([k for k, _ in _panel_order if k in panel_traces])

    css = (
        "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');"
        "body{margin:0;background:#0d1117;font-family:'Inter',system-ui,sans-serif;"
        "color:#e6edf3;overflow-x:hidden}"
        "#toolbar{padding:8px 14px;background:#161b22;border-bottom:1px solid #30363d;"
        "display:flex;gap:6px;flex-wrap:wrap;align-items:center;"
        "position:sticky;top:0;z-index:999;user-select:none}"
        ".tb-sep{width:1px;height:20px;background:#30363d;margin:0 6px;flex-shrink:0}"
        ".tb-label{font-size:11px;color:#8b949e;font-weight:500;white-space:nowrap;margin-right:2px}"
        ".tb-btn{padding:3px 9px;border-radius:6px;border:1px solid #30363d;"
        "background:#21262d;color:#c9d1d9;font-size:12px;cursor:pointer;"
        "transition:background .12s,color .12s,border-color .12s;"
        "white-space:nowrap;line-height:1.6}"
        ".tb-btn.active{background:#1f6feb;color:#fff;border-color:#1f6feb}"
        ".tb-btn:hover:not(.active){background:#30363d;color:#e6edf3}"
        ".tb-shortcut{font-size:10px;color:#484f58;margin-left:auto;white-space:nowrap}"
        ".plotly-graph-div{display:block!important}"
    )

    sr_vis_init = "true" if sr_count else "false"
    js = (
        "var _gd=document.getElementById('chart');"
        "var _srVisible=" + sr_vis_init + ";"
        # ── Panel-toggle state ────────────────────────────────────────────────
        f"var _PT={pt_json};"
        f"var _activePanels={active_json};"
        # Redistributes y-axis domains whenever a panel is shown/hidden
        "function _computeDomains(active){"
        "var W={price:0.50,volume:0.10,rsi:0.13,stoch:0.13,macd:0.14},SP=0.025;"
        "var order=['macd','stoch','rsi','volume','price'].filter(function(p){"
        "  return p==='price'||active.indexOf(p)>=0;});"
        "var totalW=order.reduce(function(s,p){return s+W[p];},0);"
        "var usable=1.0-SP*(order.length-1),y=0.0,dom={};"
        "order.forEach(function(p){"
        "  var h=W[p]/totalW*usable;"
        "  dom[p]=[Math.round(y*1e4)/1e4,Math.round((y+h)*1e4)/1e4];y+=h+SP;});"
        "var AX={price:'',volume:'2',rsi:'3',stoch:'4',macd:'5'};"
        "var LABELS={volume:'Volume',rsi:'RSI (14)',stoch:'Stoch (14,3)',macd:'MACD (12,26,9)'};"
        "var upd={};"
        "['price','volume','rsi','stoch','macd'].forEach(function(p){"
        "  var ax='yaxis'+AX[p];"
        "  if(dom[p]){upd[ax+'.domain']=dom[p];upd[ax+'.visible']=true;}"
        "  else{upd[ax+'.domain']=[0,0.001];upd[ax+'.visible']=false;}});"
        "upd['annotations']=['volume','rsi','stoch','macd']"
        "  .filter(function(p){return !!dom[p];})"
        "  .map(function(p){return{font:{size:11,color:'#8b949e'},showarrow:false,"
        "    text:LABELS[p],x:0.5,xanchor:'center',xref:'paper',"
        "    y:dom[p][0],yanchor:'bottom',yref:'paper'};});"
        "return upd;}"
        "function togglePanel(panel){"
        "  var i=_activePanels.indexOf(panel);"
        "  if(i>=0)_activePanels.splice(i,1); else _activePanels.push(panel);"
        "  var allT=Object.keys(_PT).reduce(function(a,k){return a.concat(_PT[k]);},[]);"
        "  var visT=_activePanels.reduce(function(a,k){return _PT[k]?a.concat(_PT[k]):a;},[]);"
        "  var hideT=allT.filter(function(x){return visT.indexOf(x)<0;});"
        "  if(hideT.length)Plotly.restyle(_gd,{visible:false},hideT);"
        "  if(visT.length)Plotly.restyle(_gd,{visible:true},visT);"
        "  Plotly.relayout(_gd,_computeDomains(_activePanels));"
        "  var btn=document.querySelector('[data-panel=\"'+panel+'\"]');"
        "  if(btn)btn.classList.toggle('active',_activePanels.indexOf(panel)>=0);}"
        # ── Overlay / EMA toggles ─────────────────────────────────────────────
        "function _getIdxs(name){"
        "  if(!_gd||!_gd.data)return [];"
        "  var r=[];_gd.data.forEach(function(t,i){if(t.name===name)r.push(i);});return r;}"
        "function toggleTrace(name){"
        "  var ids=_getIdxs(name);if(!ids.length)return;"
        "  var nxt=(_gd.data[ids[0]].visible===false)?true:false;"
        "  Plotly.restyle(_gd,{visible:nxt},ids);"
        "  document.querySelectorAll('[data-name=\"'+name+'\"]').forEach(function(b){"
        "    b.classList.toggle('active',nxt!==false);});}"
        # ── Chart type switching ──────────────────────────────────────────────
        "var _CT=['Candlestick','OHLC','Price','Heikin Ashi'];"
        "function setChartType(name){"
        "  var ids=[],vis=[];"
        "  _CT.forEach(function(n){var i=_getIdxs(n);if(i.length){ids.push(i[0]);vis.push(n===name);}});"
        "  Plotly.restyle(_gd,{visible:vis},ids);"
        "  document.querySelectorAll('.tb-ctype').forEach(function(b){"
        "    b.classList.toggle('active',b.dataset.name===name);});}"
        # ── S/R toggle ────────────────────────────────────────────────────────
        "function toggleSR(){"
        "  var ids=[];if(_gd&&_gd.data)_gd.data.forEach(function(t,i){if(t.name==='S/R')ids.push(i);});"
        "  _srVisible=!_srVisible;"
        "  if(ids.length)Plotly.restyle(_gd,{visible:_srVisible},ids);"
        "  var b=document.getElementById('sr-btn');"
        "  if(b)b.classList.toggle('active',_srVisible);}"
        # ── Keyboard shortcuts ────────────────────────────────────────────────
        "document.addEventListener('keydown',function(e){"
        "  if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA')return;"
        "  if(e.key==='1')setChartType('Candlestick');"
        "  else if(e.key==='2')setChartType('OHLC');"
        "  else if(e.key==='3')setChartType('Price');"
        "  else if(e.key==='4')setChartType('Heikin Ashi');});"
    )

    return (
        "<!DOCTYPE html>\n"
        "<html lang=\"en\">\n"
        "<head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{symbol.upper()} \u2014 {timeframe.upper()} Chart</title>"
        f"<style>{css}</style></head>\n"
        "<body>"
        "<div id=\"toolbar\">"
        "  <span class=\"tb-label\">Type</span>"
        "  <button class=\"tb-btn tb-ctype active\" data-name=\"Candlestick\" onclick=\"setChartType('Candlestick')\">Candle</button>"
        "  <button class=\"tb-btn tb-ctype\" data-name=\"OHLC\" onclick=\"setChartType('OHLC')\">OHLC</button>"
        "  <button class=\"tb-btn tb-ctype\" data-name=\"Price\" onclick=\"setChartType('Price')\">Line</button>"
        "  <button class=\"tb-btn tb-ctype\" data-name=\"Heikin Ashi\" onclick=\"setChartType('Heikin Ashi')\">Heikin Ashi</button>"
        "  <div class=\"tb-sep\"></div>"
        "  <span class=\"tb-label\">EMA</span>"
        f"  {ema_btns}"
        "  <div class=\"tb-sep\"></div>"
        "  <span class=\"tb-label\">Overlay</span>"
        "  <button class=\"tb-btn active\" data-name=\"BB Bands\" onclick=\"toggleTrace('BB Bands')\">BB</button>"
        "  <button class=\"tb-btn active\" data-name=\"Supertrend\" onclick=\"toggleTrace('Supertrend')\">Supertrend</button>"
        f"  <button class=\"tb-btn {sr_active}\" id=\"sr-btn\" onclick=\"toggleSR()\">{sr_label}</button>"
        "  <div class=\"tb-sep\"></div>"
        "  <span class=\"tb-label\">Panels</span>"
        f"  {panel_btns}"
        "  <span class=\"tb-shortcut\">Keys: 1=Candle &middot; 2=OHLC &middot; 3=Line &middot; 4=HA</span>"
        "</div>\n"
        f"{plotly_div}\n"
        f"<script>{js}</script>\n"
        "</body></html>"
    )


def render_html_chart(
    symbol: str,
    timeframe: str = "3mo",
    indicators: Optional[list[str]] = None,
    open_browser: bool = True,
) -> str:
    """
    Generate an enhanced interactive HTML chart.

    Chart types: Candlestick / OHLC / Line / Heikin Ashi (toolbar + keys 1-4).
    Overlays: EMA 9/13/20/50/100/200, Bollinger Bands, Supertrend(7,3), S/R pivot levels.
    Panels: Volume | RSI(14) | Stochastic(14,3) | MACD(12,26,9).
    Non-trading weekend gaps removed on daily/weekly charts.

    Saves to data/charts/<SYMBOL>_<timeframe>.html and auto-opens in browser.
    Returns the file path.
    """
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        return "❌  plotly not installed. Run: pip install plotly"

    df = _fetch_ohlcv(symbol, timeframe)
    if df.empty:
        return f"❌  No data found for {symbol} (timeframe: {timeframe})"

    period, interval = _TF_PERIOD_MAP.get(timeframe, ("3mo", "1d"))
    n = len(df)
    dates_raw = pd.to_datetime(df["Date"], utc=True).dt.tz_localize(None)
    opens  = df["Open"].tolist()
    highs  = df["High"].tolist()
    lows   = df["Low"].tolist()
    closes = df["Close"].tolist()
    vols   = df["Volume"].tolist() if "Volume" in df.columns else [0] * n

    up_color   = "#26A69A"
    down_color = "#EF5350"

    # 5 fixed panels: Price | Volume | RSI | Stoch | MACD
    n_rows = 5
    fig = make_subplots(
        rows=n_rows, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        row_heights=[0.50, 0.10, 0.13, 0.13, 0.14],
        # Empty string for row-1 — title lives in layout.title, not here
        subplot_titles=["", "Volume", "RSI (14)", "Stoch (14,3)", "MACD (12,26,9)"],
    )

    # ── Row 1: four chart types ──────────────────────────────────────────────

    # Candlestick (default)
    fig.add_trace(go.Candlestick(
        x=dates_raw, open=opens, high=highs, low=lows, close=closes,
        increasing_line_color=up_color, decreasing_line_color=down_color,
        increasing_fillcolor=up_color, decreasing_fillcolor=down_color,
        name="Candlestick", showlegend=False,
    ), row=1, col=1)

    # OHLC (hidden)
    fig.add_trace(go.Ohlc(
        x=dates_raw, open=opens, high=highs, low=lows, close=closes,
        increasing_line_color=up_color, decreasing_line_color=down_color,
        name="OHLC", showlegend=False, visible=False,
    ), row=1, col=1)

    # Line (hidden)
    fig.add_trace(go.Scatter(
        x=dates_raw, y=closes,
        line=dict(color="#58A6FF", width=2),
        name="Price", showlegend=False, visible=False, mode="lines",
    ), row=1, col=1)

    # Heikin Ashi (hidden)
    ha_o, ha_h, ha_l, ha_c = _heikin_ashi(opens, highs, lows, closes)
    fig.add_trace(go.Candlestick(
        x=dates_raw, open=ha_o, high=ha_h, low=ha_l, close=ha_c,
        increasing_line_color=up_color, decreasing_line_color=down_color,
        increasing_fillcolor=up_color, decreasing_fillcolor=down_color,
        name="Heikin Ashi", showlegend=False, visible=False,
    ), row=1, col=1)

    # ── EMAs ────────────────────────────────────────────────────────────────
    ema_configs = [
        (9,   "#FFB300", 1.0, "solid"),
        (13,  "#FF7043", 1.0, "solid"),
        (20,  "#00BCD4", 1.2, "solid"),
        (50,  "#FF9800", 1.2, "solid"),
        (100, "#66BB6A", 1.0, "solid"),
        (200, "#AB47BC", 1.2, "dot"),
    ]
    ema_spans_added: list[int] = []
    for span, color, width, dash in ema_configs:
        if n >= span:
            fig.add_trace(go.Scatter(
                x=dates_raw, y=_ema(closes, span),
                line=dict(color=color, width=width, dash=dash),
                name=f"EMA {span}", mode="lines",
            ), row=1, col=1)
            ema_spans_added.append(span)

    # ── Bollinger Bands ──────────────────────────────────────────────────────
    if n >= 20:
        bb_lo, _bb_mid, bb_hi = _bb(closes, 20, 2.0)
        fig.add_trace(go.Scatter(
            x=dates_raw, y=bb_hi,
            line=dict(color="rgba(150,150,255,0.4)", width=1),
            name="BB Bands", mode="lines", showlegend=False,
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=dates_raw, y=bb_lo,
            fill="tonexty", fillcolor="rgba(150,150,255,0.06)",
            line=dict(color="rgba(150,150,255,0.4)", width=1),
            name="BB Bands", mode="lines", showlegend=False,
        ), row=1, col=1)

    # ── Supertrend(7, 3) — two traces (bullish / bearish segments) ───────────
    if n >= 14:
        direction, st_vals = _supertrend(highs, lows, closes)
        st_up = [v if d == 1  else None for v, d in zip(st_vals, direction)]
        st_dn = [v if d == -1 else None for v, d in zip(st_vals, direction)]
        fig.add_trace(go.Scatter(
            x=dates_raw, y=st_up,
            line=dict(color="#26A69A", width=1.5),
            name="Supertrend", mode="lines", showlegend=False, connectgaps=False,
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=dates_raw, y=st_dn,
            line=dict(color="#EF5350", width=1.5),
            name="Supertrend", mode="lines", showlegend=False, connectgaps=False,
        ), row=1, col=1)

    # ── S/R pivot levels ─────────────────────────────────────────────────────
    sr_count = 0
    if n >= 15:
        sr_levels = _pivot_sr(highs, lows)
        x0, x1 = dates_raw.iloc[0], dates_raw.iloc[-1]
        for lv in sr_levels:
            fig.add_trace(go.Scatter(
                x=[x0, x1], y=[lv, lv],
                mode="lines",
                line=dict(color="rgba(255,210,80,0.5)", width=1, dash="dot"),
                name="S/R", showlegend=False, hoverinfo="skip",
            ), row=1, col=1)
            sr_count += 1

    # ── Row 2: Volume ────────────────────────────────────────────────────────
    panel_traces: dict[str, list[int]] = {}
    vol_colors = [up_color if c >= o else down_color for c, o in zip(closes, opens)]
    panel_traces["volume"] = [len(fig.data)]
    fig.add_trace(go.Bar(
        x=dates_raw, y=vols, marker_color=vol_colors,
        name="Volume", showlegend=False,
    ), row=2, col=1)

    # ── Row 3: RSI(14) ───────────────────────────────────────────────────────
    rsi_vals = _rsi(closes, 14)
    panel_traces["rsi"] = [len(fig.data)]
    fig.add_trace(go.Scatter(
        x=dates_raw, y=rsi_vals,
        line=dict(color="#F9A825", width=1.5),
        name="RSI(14)", mode="lines", showlegend=False,
    ), row=3, col=1)
    fig.add_hrect(y0=70, y1=100, fillcolor="rgba(239,83,80,0.08)",  line_width=0, row=3, col=1)
    fig.add_hrect(y0=0,  y1=30,  fillcolor="rgba(38,166,154,0.08)", line_width=0, row=3, col=1)
    for lvl, lc in [(70, "#EF5350"), (50, "rgba(255,255,255,0.2)"), (30, "#26A69A")]:
        fig.add_hline(y=lvl, line_dash="dot", line_color=lc, line_width=0.8, row=3, col=1)
    fig.update_yaxes(range=[0, 100], row=3, col=1)

    # ── Row 4: Stochastic(14,3) ───────────────────────────────────────────────
    stoch_k, stoch_d = _stoch(highs, lows, closes)
    panel_traces["stoch"] = [len(fig.data), len(fig.data) + 1]
    fig.add_trace(go.Scatter(
        x=dates_raw, y=stoch_k,
        line=dict(color="#42A5F5", width=1.5),
        name="Stoch %K", mode="lines", showlegend=False,
    ), row=4, col=1)
    fig.add_trace(go.Scatter(
        x=dates_raw, y=stoch_d,
        line=dict(color="#FF7043", width=1.5),
        name="Stoch %D", mode="lines", showlegend=False,
    ), row=4, col=1)
    fig.add_hrect(y0=80, y1=100, fillcolor="rgba(239,83,80,0.08)",  line_width=0, row=4, col=1)
    fig.add_hrect(y0=0,  y1=20,  fillcolor="rgba(38,166,154,0.08)", line_width=0, row=4, col=1)
    for lvl in [80, 50, 20]:
        fig.add_hline(y=lvl, line_dash="dot", line_color="rgba(255,255,255,0.2)",
                      line_width=0.8, row=4, col=1)
    fig.update_yaxes(range=[0, 100], row=4, col=1)

    # ── Row 5: MACD(12,26,9) ─────────────────────────────────────────────────
    macd_line, sig_line, hist_vals = _macd(closes)
    hist_colors = [up_color if h >= 0 else down_color for h in hist_vals]
    panel_traces["macd"] = [len(fig.data), len(fig.data) + 1, len(fig.data) + 2]
    fig.add_trace(go.Bar(
        x=dates_raw, y=hist_vals, marker_color=hist_colors,
        name="MACD Hist", showlegend=False, opacity=0.7,
    ), row=5, col=1)
    fig.add_trace(go.Scatter(
        x=dates_raw, y=macd_line,
        line=dict(color="#00BCD4", width=1.5),
        name="MACD", mode="lines", showlegend=False,
    ), row=5, col=1)
    fig.add_trace(go.Scatter(
        x=dates_raw, y=sig_line,
        line=dict(color="#FF9800", width=1.5),
        name="Signal", mode="lines", showlegend=False,
    ), row=5, col=1)
    fig.add_hline(y=0, line_dash="dot", line_color="rgba(255,255,255,0.2)",
                  line_width=0.8, row=5, col=1)

    # ── Layout ───────────────────────────────────────────────────────────────
    current_price = closes[-1]
    prev    = closes[-2] if n >= 2 else closes[-1]
    chg_pct = 100 * (current_price - prev) / prev if prev else 0.0
    sign    = "\u25b2" if chg_pct >= 0 else "\u25bc"
    chg_clr = "#26A69A" if chg_pct >= 0 else "#EF5350"

    fig.update_layout(
        title=dict(
            text=(
                f"<b>{symbol.upper()}</b>  "
                f"\u20b9{current_price:,.2f}  "
                f"<span style='color:{chg_clr}'>{sign} {abs(chg_pct):.2f}%</span>"
                f"  <span style='font-size:12px;color:#6e7681'>{timeframe.upper()}</span>"
            ),
            font=dict(size=17, color="#e6edf3"),
            x=0.01,
            y=0.99,
            yanchor="top",
        ),
        paper_bgcolor="#0d1117",
        plot_bgcolor="#0d1117",
        font=dict(family="Inter, system-ui, sans-serif", size=12, color="#8b949e"),
        # Legend inside the top-right of the price pane — no collision with title
        showlegend=True,
        legend=dict(
            bgcolor="rgba(13,17,23,0.8)",
            bordercolor="#30363d", borderwidth=1,
            font=dict(size=10, color="#c9d1d9"),
            orientation="h",
            yanchor="top", y=0.99,
            xanchor="right", x=0.99,
        ),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#161b22", bordercolor="#30363d",
                        font=dict(color="#e6edf3", size=12)),
        margin=dict(l=10, r=70, t=60, b=30),
        height=920,
        autosize=True,
    )

    # Style subplot title annotations — make them legible on dark background
    fig.update_annotations(
        font=dict(size=11, color="#8b949e"),
    )

    axis_style = dict(
        gridcolor="#21262d", gridwidth=1,
        linecolor="#30363d", tickcolor="#30363d",
        tickfont=dict(color="#6e7681", size=10),
        zerolinecolor="#30363d", showgrid=True,
    )
    for i in range(1, n_rows + 1):
        fig.update_xaxes(axis_style, row=i, col=1)
        fig.update_yaxes({**axis_style, "side": "right", "ticklen": 4}, row=i, col=1)

    # Crosshair spike lines
    for i in range(1, n_rows + 1):
        fig.update_xaxes(
            showspikes=True, spikecolor="#6e7681",
            spikethickness=1, spikedash="dot", spikemode="across", row=i, col=1,
        )
        fig.update_yaxes(
            showspikes=True, spikecolor="#6e7681",
            spikethickness=1, spikedash="dot", row=i, col=1,
        )

    # Remove weekend gaps on daily/weekly charts
    if interval in ("1d", "1wk"):
        rb = [dict(bounds=["sat", "mon"])]
        for i in range(1, n_rows + 1):
            fig.update_xaxes(rangebreaks=rb, row=i, col=1)

    # ── Build and save ────────────────────────────────────────────────────────
    plotly_div = fig.to_html(
        full_html=False,
        include_plotlyjs=True,
        div_id="chart",
        config={
            "scrollZoom": True,
            "displayModeBar": True,
            "responsive": True,
            "modeBarButtonsToAdd": ["drawline", "drawopenpath", "eraseshape"],
            "modeBarButtonsToRemove": ["lasso2d", "select2d"],
        },
    )

    html = _build_chart_html(symbol, timeframe, plotly_div, sr_count, ema_spans_added, panel_traces)
    _HTML_CHART_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"{symbol.upper()}_{timeframe}.html"
    fpath = _HTML_CHART_DIR / fname
    fpath.write_text(html, encoding="utf-8")

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
