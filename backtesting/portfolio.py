"""Portfolio sizing helpers for EOD backtests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PositionSize:
    quantity: int
    notional: float
    remaining_cash: float


def size_position(*, cash: float, price: float, allocation_pct: float) -> PositionSize:
    if price <= 0:
        raise ValueError("price must be positive")
    if cash < 0:
        raise ValueError("cash must be non-negative")
    if allocation_pct <= 0:
        raise ValueError("allocation_pct must be positive")

    budget = min(cash, cash * allocation_pct)
    quantity = int(budget // price)
    notional = round(quantity * price, 6)
    return PositionSize(
        quantity=quantity,
        notional=notional,
        remaining_cash=round(cash - notional, 6),
    )
