"""Watchlist price/RSI alert system for Agent Adda."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_ALERTS_FILE = _ROOT / "data" / "watchlist_alerts.json"

VALID_TRIGGERS = {"price_above", "price_below", "rsi_above", "rsi_below"}


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


def add_alert(symbol: str, trigger: str, value: float, note: str = "") -> dict:
    """Add a new alert and persist. Returns the new alert dict."""
    if trigger not in VALID_TRIGGERS:
        raise ValueError(f"Invalid trigger '{trigger}'. Must be one of {sorted(VALID_TRIGGERS)}")
    alerts = load_alerts()
    new_id = max((a["id"] for a in alerts), default=0) + 1
    alert = {
        "id": new_id,
        "symbol": symbol.upper(),
        "trigger": trigger,
        "value": float(value),
        "note": note,
        "active": True,
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
