"""Watchlist price/RSI/breakout alert system for Agent Adda."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_ALERTS_FILE = _ROOT / "data" / "watchlist_alerts.json"

VALID_TRIGGERS = {
    "price_above", "price_below",
    "rsi_above", "rsi_below",
    "breakout_above", "breakout_below",
    "intraday_breakout",           # ORB auto-detect: no value needed (store 0)
}

_TRIGGER_ALIASES = {
    "breakout":  "intraday_breakout",
    "orb":       "intraday_breakout",
    "intraday":  "intraday_breakout",
    "above":     "breakout_above",
    "below":     "breakout_below",
}

# Valid yfinance intraday intervals
_INTRADAY_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"}


# ── Storage ────────────────────────────────────────────────────────────────


def load_alerts() -> list[dict]:
    try:
        return json.loads(_ALERTS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_alerts(alerts: list[dict]) -> None:
    _ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ALERTS_FILE.write_text(json.dumps(alerts, indent=2))


def list_alerts() -> list[dict]:
    return load_alerts()


def add_alert(
    symbol: str,
    trigger: str,
    value: float = 0.0,
    note: str = "",
    tf: str = "1d",
) -> dict:
    """Add a new alert and persist. Returns the new alert dict."""
    trigger = _TRIGGER_ALIASES.get(trigger.lower(), trigger.lower())
    if trigger not in VALID_TRIGGERS:
        raise ValueError(
            f"Invalid trigger '{trigger}'. Valid: "
            + ", ".join(sorted(VALID_TRIGGERS))
            + "\n  Aliases: breakout/orb/intraday → intraday_breakout"
        )
    # Normalise timeframe
    tf = tf.strip().lower() if tf else "1d"
    alerts = load_alerts()
    new_id = max((a["id"] for a in alerts), default=0) + 1
    alert = {
        "id":      new_id,
        "symbol":  symbol.upper(),
        "trigger": trigger,
        "value":   float(value),
        "tf":      tf,
        "note":    note,
        "active":  True,
    }
    alerts.append(alert)
    save_alerts(alerts)
    return alert


def delete_alert(alert_id: int) -> bool:
    alerts = load_alerts()
    new_alerts = [a for a in alerts if a["id"] != alert_id]
    if len(new_alerts) == len(alerts):
        return False
    save_alerts(new_alerts)
    return True


# ── Intraday helpers ───────────────────────────────────────────────────────


def _yf_symbol(symbol: str) -> str:
    _INDEX_MAP = {
        "NIFTY": "^NSEI", "NIFTY50": "^NSEI",
        "BANKNIFTY": "^NSEBANK", "SENSEX": "^BSESN",
    }
    sym = symbol.upper()
    if sym in _INDEX_MAP:
        return _INDEX_MAP[sym]
    if not sym.endswith(".NS") and not sym.startswith("^"):
        return sym + ".NS"
    return sym


def _fetch_ohlcv(symbol: str, interval: str = "15m", period: str = "1d"):
    """Return OHLCV DataFrame for the given interval and lookback period."""
    try:
        import yfinance as yf
        df = yf.download(
            _yf_symbol(symbol), period=period, interval=interval,
            progress=False, auto_adjust=True,
        )
        if df.empty:
            return df
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        return df.dropna(subset=["Close"])
    except Exception:
        return __import__("pandas").DataFrame()


def _compute_rsi_tf(symbol: str, tf: str, period: int = 14) -> float | None:
    """Compute RSI for the given timeframe using yfinance data.

    tf: yfinance interval string ('15m', '5m', '1h', '1d', etc.)
    For intraday intervals, fetches last 5d of bars to get enough history.
    """
    lookback = "5d" if tf in _INTRADAY_INTERVALS else "3mo"
    df = _fetch_ohlcv(symbol, interval=tf, period=lookback)
    if len(df) < period + 2:
        return None
    try:
        import pandas as pd
        close = df["Close"].astype(float)
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, float("nan"))
        rsi = 100 - (100 / (1 + rs))
        val = float(rsi.iloc[-1])
        return round(val, 2) if not __import__("math").isnan(val) else None
    except Exception:
        return None


def _orb_levels(symbol: str, orb_bars: int = 2) -> dict:
    """Return opening-range high/low/current from 15m data."""
    df = _fetch_ohlcv(symbol, interval="15m", period="1d")
    if len(df) < orb_bars + 1:
        return {}
    opening = df.head(orb_bars)
    orh = float(opening["High"].max())
    orl = float(opening["Low"].min())
    current = float(df["Close"].iloc[-1])
    return {"orh": orh, "orl": orl, "current": current, "bars": len(df)}


# ── Alert checker ──────────────────────────────────────────────────────────


def check_alerts() -> list[dict]:
    """Check all active alerts against live prices/RSI/breakout.

    Respects the 'tf' field on each alert — RSI triggers on non-daily
    timeframes fetch intraday bars and compute RSI from them directly.

    Fires macOS notifications for triggered alerts.
    Returns list of triggered alert dicts (with 'triggered_value').
    """
    sys.path.insert(0, str(_ROOT))
    from terminal.tools import call_tool  # noqa: PLC0415

    alerts = [a for a in load_alerts() if a.get("active", True)]
    if not alerts:
        return []

    symbols: dict[str, list[dict]] = {}
    for alert in alerts:
        symbols.setdefault(alert["symbol"], []).append(alert)

    triggered: list[dict] = []

    for sym, sym_alerts in symbols.items():
        snap   = call_tool("get_symbol_snapshot", {"symbol": sym})
        price  = snap.get("price") if not snap.get("error") else None
        daily_rsi = snap.get("rsi") if not snap.get("error") else None
        orb    = None  # lazy-loaded only for breakout triggers

        for alert in sym_alerts:
            ttype     = alert["trigger"]
            val       = alert["value"]
            tf        = alert.get("tf", "1d")
            current: float | None = None
            fired  = False
            msg_extra = ""

            if ttype == "price_above" and price is not None:
                fired, current = price > val, price

            elif ttype == "price_below" and price is not None:
                fired, current = price < val, price

            elif ttype in ("rsi_above", "rsi_below"):
                # Use timeframe-specific RSI if tf is not daily
                if tf in _INTRADAY_INTERVALS:
                    rsi = _compute_rsi_tf(sym, tf)
                else:
                    rsi = daily_rsi
                    if rsi is None:
                        rsi = call_tool("get_technical_setup", {"symbol": sym}).get("rsi")
                if rsi is not None:
                    fired = (rsi > val) if ttype == "rsi_above" else (rsi < val)
                    current = rsi
                    if tf in _INTRADAY_INTERVALS:
                        msg_extra = f" [{tf}]"

            elif ttype == "intraday_breakout":
                if orb is None:
                    orb = _orb_levels(sym)
                if orb:
                    c = orb["current"]
                    if c > orb["orh"]:
                        fired, current = True, c
                        msg_extra = f" ORH={orb['orh']:.2f}"
                    elif c < orb["orl"]:
                        fired, current = True, c
                        msg_extra = f" ORL={orb['orl']:.2f}"
                    else:
                        current = c

            elif ttype == "breakout_above" and price is not None:
                if orb is None:
                    orb = _orb_levels(sym)
                c = (orb or {}).get("current", price)
                fired, current = c > val, c

            elif ttype == "breakout_below" and price is not None:
                if orb is None:
                    orb = _orb_levels(sym)
                c = (orb or {}).get("current", price)
                fired, current = c < val, c

            else:
                continue

            if fired:
                result = dict(alert)
                result["triggered_value"] = round(current, 2) if current is not None else None
                triggered.append(result)
                note_part = f" | {alert['note']}" if alert.get("note") else ""
                msg = (
                    f"{sym} — {ttype.replace('_', ' ')} "
                    + (f"{val} " if val else "")
                    + f"(current: {result['triggered_value']}){msg_extra}{note_part}"
                )
                subprocess.run(
                    ["osascript", "-e",
                     f'display notification "{msg}" with title "Agent Adda 🔔" sound name "Ping"'],
                    check=False,
                )
                try:
                    from terminal.whatsapp_dispatcher import send_market_alert

                    wa = send_market_alert(
                        title=f"{sym} {ttype.replace('_', ' ')}",
                        body=msg,
                    )
                    result["whatsapp_status"] = wa.status
                    if wa.dry_run_path:
                        result["whatsapp_dry_run_path"] = wa.dry_run_path
                    if wa.error:
                        result["whatsapp_error"] = wa.error
                except Exception as exc:
                    result["whatsapp_status"] = "error"
                    result["whatsapp_error"] = str(exc)

    return triggered
