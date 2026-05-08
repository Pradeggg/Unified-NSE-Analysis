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

# Friendly aliases accepted at add-time → canonical trigger name
_TRIGGER_ALIASES = {
    "breakout":        "intraday_breakout",
    "orb":             "intraday_breakout",
    "intraday":        "intraday_breakout",
    "above":           "breakout_above",
    "below":           "breakout_below",
}


# ── Storage ────────────────────────────────────────────────────────────────


def load_alerts() -> list[dict]:
    """Read alerts from JSON file; return [] if missing or corrupt."""
    try:
        return json.loads(_ALERTS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_alerts(alerts: list[dict]) -> None:
    """Persist alerts list to JSON file."""
    _ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ALERTS_FILE.write_text(json.dumps(alerts, indent=2))


def list_alerts() -> list[dict]:
    """Return all current alerts."""
    return load_alerts()


def add_alert(symbol: str, trigger: str, value: float = 0.0, note: str = "") -> dict:
    """Add a new alert and persist. Returns the new alert dict."""
    trigger = _TRIGGER_ALIASES.get(trigger.lower(), trigger.lower())
    if trigger not in VALID_TRIGGERS:
        raise ValueError(
            f"Invalid trigger '{trigger}'. Valid: "
            + ", ".join(sorted(VALID_TRIGGERS))
            + "\n  Aliases: breakout/orb/intraday → intraday_breakout"
        )
    alerts = load_alerts()
    new_id = max((a["id"] for a in alerts), default=0) + 1
    alert = {
        "id":      new_id,
        "symbol":  symbol.upper(),
        "trigger": trigger,
        "value":   float(value),
        "note":    note,
        "active":  True,
    }
    alerts.append(alert)
    save_alerts(alerts)
    return alert


def delete_alert(alert_id: int) -> bool:
    """Remove alert by id. Returns True if found and deleted, False otherwise."""
    alerts = load_alerts()
    new_alerts = [a for a in alerts if a["id"] != alert_id]
    if len(new_alerts) == len(alerts):
        return False
    save_alerts(new_alerts)
    return True


# ── Intraday breakout helpers ──────────────────────────────────────────────


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


def _fetch_15m_today(symbol: str):
    """Return today's 15-minute OHLCV DataFrame, or empty DataFrame on failure."""
    try:
        import yfinance as yf
        import pandas as pd
        df = yf.download(_yf_symbol(symbol), period="1d", interval="15m",
                         progress=False, auto_adjust=True)
        if df.empty:
            return df
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        return df.dropna(subset=["Close"])
    except Exception:
        return __import__("pandas").DataFrame()


def _orb_levels(symbol: str, orb_bars: int = 2) -> dict:
    """Return opening-range high/low/current from 15m data."""
    df = _fetch_15m_today(symbol)
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
    Fires macOS notifications for triggered alerts.
    Returns list of triggered alert dicts (with 'triggered_value')."""
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
        snap    = call_tool("get_symbol_snapshot", {"symbol": sym})
        price   = snap.get("price") if not snap.get("error") else None
        rsi     = snap.get("rsi")   if not snap.get("error") else None
        orb     = None   # lazy-loaded only for breakout triggers

        for alert in sym_alerts:
            ttype   = alert["trigger"]
            val     = alert["value"]
            current: float | None = None
            fired   = False
            msg_extra = ""

            if ttype == "price_above" and price is not None:
                fired, current = price > val, price

            elif ttype == "price_below" and price is not None:
                fired, current = price < val, price

            elif ttype in ("rsi_above", "rsi_below"):
                if rsi is None:
                    rsi = call_tool("get_technical_setup", {"symbol": sym}).get("rsi")
                if rsi is not None:
                    fired = (rsi > val) if ttype == "rsi_above" else (rsi < val)
                    current = rsi

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
                # Check 15m close crossed above the stored level
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

    return triggered


# ── Storage ────────────────────────────────────────────────────────────────


def load_alerts() -> list[dict]:
    """Read alerts from JSON file; return [] if missing or corrupt."""
    try:
        return json.loads(_ALERTS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_alerts(alerts: list[dict]) -> None:
    """Persist alerts list to JSON file."""
    _ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ALERTS_FILE.write_text(json.dumps(alerts, indent=2))


def list_alerts() -> list[dict]:
    """Return all current alerts."""
    return load_alerts()


def delete_alert(alert_id: int) -> bool:
    """Remove alert by id. Returns True if found and deleted, False otherwise."""
    alerts = load_alerts()
    new_alerts = [a for a in alerts if a["id"] != alert_id]
    if len(new_alerts) == len(alerts):
        return False
    save_alerts(new_alerts)
    return True


# ── Alert checker ──────────────────────────────────────────────────────────


def check_alerts() -> list[dict]:
    """Check all active alerts against live prices/RSI. Fire macOS notifications
    for triggered alerts. Returns list of triggered alert dicts (with 'triggered_value')."""
    sys.path.insert(0, str(_ROOT))
    from terminal.tools import call_tool  # noqa: PLC0415

    alerts = [a for a in load_alerts() if a.get("active", True)]
    if not alerts:
        return []

    # Group by symbol to minimise API calls
    symbols: dict[str, list[dict]] = {}
    for alert in alerts:
        symbols.setdefault(alert["symbol"], []).append(alert)

    triggered: list[dict] = []

    for sym, sym_alerts in symbols.items():
        snap = call_tool("get_symbol_snapshot", {"symbol": sym})
        price = snap.get("price") if not snap.get("error") else None

        # Fetch RSI from snapshot (already computed there); fall back to technical setup
        rsi = snap.get("rsi") if not snap.get("error") else None

        for alert in sym_alerts:
            ttype = alert["trigger"]
            val = alert["value"]
            current: float | None = None
            fired = False

            if ttype == "price_above" and price is not None:
                fired = price > val
                current = price
            elif ttype == "price_below" and price is not None:
                fired = price < val
                current = price
            elif ttype in ("rsi_above", "rsi_below"):
                if rsi is None:
                    indicators = call_tool("get_technical_setup", {"symbol": sym})
                    rsi = indicators.get("rsi")
                if rsi is not None:
                    fired = (rsi > val) if ttype == "rsi_above" else (rsi < val)
                    current = rsi
            else:
                continue

            if fired:
                result = dict(alert)
                result["triggered_value"] = round(current, 2) if current is not None else None
                triggered.append(result)
                msg = (
                    f"{sym} — {ttype.replace('_', ' ')} {val} "
                    f"(current: {result['triggered_value']})"
                )
                if alert.get("note"):
                    msg += f" | {alert['note']}"
                subprocess.run(
                    [
                        "osascript",
                        "-e",
                        f'display notification "{msg}" with title "Agent Adda 🔔" sound name "Ping"',
                    ],
                    check=False,
                )

    return triggered
