"""Decision math helpers for Research Council reports."""

from __future__ import annotations

from typing import Any


DISCLAIMER = "Research-only calculation; not a live order instruction."


def unavailable(reason: str) -> dict:
    return {"available": False, "reason": reason}


def atr_stop(*, entry: Any, atr: Any, multiple: float = 2.0, side: str = "long") -> dict:
    entry_n = _positive_float(entry)
    atr_n = _positive_float(atr)
    if entry_n is None or atr_n is None:
        if entry is None or atr is None:
            return unavailable("entry and atr are required")
        return unavailable("entry and atr must be positive")
    multiple_n = float(multiple)
    if side != "long":
        return unavailable("only long research stops are supported")
    risk_per_share = round(multiple_n * atr_n, 2)
    return {
        "available": True,
        "side": side,
        "entry": entry_n,
        "atr": atr_n,
        "multiple": multiple_n,
        "stop": round(entry_n - risk_per_share, 2),
        "risk_per_share": risk_per_share,
        "disclaimer": DISCLAIMER,
    }


def atr_target(*, entry: Any, atr: Any, multiple: float = 2.0, side: str = "long") -> dict:
    entry_n = _positive_float(entry)
    atr_n = _positive_float(atr)
    if entry_n is None or atr_n is None:
        if entry is None or atr is None:
            return unavailable("entry and atr are required")
        return unavailable("entry and atr must be positive")
    multiple_n = float(multiple)
    if side != "long":
        return unavailable("only long research targets are supported")
    reward_per_share = round(multiple_n * atr_n, 2)
    return {
        "available": True,
        "side": side,
        "entry": entry_n,
        "atr": atr_n,
        "multiple": multiple_n,
        "target": round(entry_n + reward_per_share, 2),
        "reward_per_share": reward_per_share,
        "disclaimer": DISCLAIMER,
    }


def research_book_size(*, capital: Any, risk_pct: Any, entry: Any, stop: Any) -> dict:
    capital_n = _positive_float(capital)
    risk_pct_n = _positive_float(risk_pct)
    entry_n = _positive_float(entry)
    stop_n = _positive_float(stop)
    if None in {capital_n, risk_pct_n, entry_n, stop_n}:
        return unavailable("capital, risk_pct, entry, and stop must be positive")
    if entry_n <= stop_n:
        return unavailable("entry must be above stop for long research sizing")
    risk_amount = round(capital_n * risk_pct_n, 2)
    risk_per_share = round(entry_n - stop_n, 2)
    quantity = int(risk_amount // risk_per_share)
    return {
        "available": True,
        "capital": capital_n,
        "risk_pct": risk_pct_n,
        "risk_amount": risk_amount,
        "entry": entry_n,
        "stop": stop_n,
        "risk_per_share": risk_per_share,
        "max_research_quantity": quantity,
        "estimated_notional": round(quantity * entry_n, 2),
        "notes": "Hypothetical research-book sizing for comparison only.",
        "disclaimer": DISCLAIMER,
    }


def _positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
