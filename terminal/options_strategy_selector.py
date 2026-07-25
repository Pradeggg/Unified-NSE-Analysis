"""Rules for choosing an options structure from a directional alert.

This is intentionally a lightweight, deterministic selector. It does not
pretend to be a full options backtest engine; it turns the existing CE/PE
execution evidence into a safer structure recommendation for live alerts.
"""

from __future__ import annotations

from typing import Any


INDEX_OPTION_UNDERLYINGS = {
    "NIFTY",
    "BANKNIFTY",
    "FINNIFTY",
    "MIDCPNIFTY",
    "NIFTYNXT50",
    "SENSEX",
}


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_index_underlying(symbol: str) -> bool:
    return str(symbol or "").strip().upper().replace(".NS", "") in INDEX_OPTION_UNDERLYINGS


def _option_side(option_type: str | None, direction: str | None) -> str:
    opt = str(option_type or "").strip().upper()
    if opt in {"CE", "PE"}:
        return opt
    return "PE" if str(direction or "").upper() == "SHORT" else "CE"


def _long_structure(option_type: str) -> str:
    return "Long Put" if option_type == "PE" else "Long Call"


def _debit_spread_structure(option_type: str) -> str:
    return "Bear Put Debit Spread" if option_type == "PE" else "Bull Call Debit Spread"


def _no_strategy(structure: str, reasons: list[str]) -> dict[str, Any]:
    return {
        "verdict": "NO OPTIONS STRATEGY",
        "structure": structure,
        "risk_mode": "none",
        "naked_buy_allowed": False,
        "management": "Do not express this alert through options until the blocked condition clears.",
        "reasons": reasons,
    }


def select_options_strategy(
    *,
    symbol: str,
    direction: str | None,
    execution: dict[str, Any],
) -> dict[str, Any]:
    """Select a practical options structure for the normalized alert evidence."""
    option_type = _option_side(execution.get("option_type"), direction)
    verdict = str(execution.get("verdict") or "").upper()
    status = str(execution.get("status") or "").lower()
    if status not in {"ok", "no_trade"} or verdict.startswith("NO OPTIONS"):
        return _no_strategy(
            "No options structure",
            [f"options execution status is {status or 'missing'}"],
        )

    dte = _num(execution.get("dte"))
    iv_pct = _num(execution.get("iv_pct"))
    delta = _num(execution.get("delta"))
    is_index = _is_index_underlying(symbol)
    is_stock_option = not is_index
    reasons: list[str] = []

    if is_index:
        reasons.append("cash-settled index option")
    else:
        reasons.append("stock-option physical settlement risk: square off before expiry")

    if is_stock_option and dte is not None and dte <= 3:
        return _no_strategy(
            "Avoid stock option near expiry",
            reasons + ["physical settlement risk is too high inside 3 DTE"],
        )

    high_iv = iv_pct is not None and iv_pct >= 28
    very_high_iv = iv_pct is not None and iv_pct >= 40
    spread_requested = "SPREAD" in verdict or "SELECTIVE" in verdict
    weak_delta = delta is not None and abs(delta) < 0.35
    too_close_to_expiry = dte is not None and dte < 5

    if very_high_iv:
        return _no_strategy(
            "Avoid naked long option",
            reasons + [f"very high IV {iv_pct:.1f}% makes long premium unattractive"],
        )

    if high_iv or spread_requested or weak_delta or too_close_to_expiry:
        if high_iv:
            reasons.append(f"high IV {iv_pct:.1f}%: reduce long-premium cost")
        if spread_requested:
            reasons.append("buying model requested spread/ selective execution")
        if weak_delta:
            reasons.append(f"delta {abs(delta):.2f} is low for a naked directional buy")
        if too_close_to_expiry:
            reasons.append(f"{int(dte)} DTE: theta/gamma risk favours capped debit")
        return {
            "verdict": "USE DEBIT SPREAD",
            "structure": _debit_spread_structure(option_type),
            "risk_mode": "defined_spread_debit",
            "naked_buy_allowed": False,
            "management": "Use the alert trigger/invalidation; target 30-60% spread gain or exit on underlying invalidation.",
            "reasons": reasons,
        }

    if iv_pct is not None:
        reasons.append(f"IV {iv_pct:.1f}% is acceptable for directional long premium")
    if dte is not None:
        reasons.append(f"{int(dte)} DTE leaves enough time for the move")
    if delta is not None:
        reasons.append(f"delta {abs(delta):.2f} is usable for directional exposure")

    return {
        "verdict": "LONG OPTION OK",
        "structure": _long_structure(option_type),
        "risk_mode": "defined_premium",
        "naked_buy_allowed": True,
        "management": "Use premium stop/target from the alert and exit on underlying invalidation.",
        "reasons": reasons,
    }
