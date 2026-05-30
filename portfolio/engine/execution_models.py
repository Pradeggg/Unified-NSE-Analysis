from __future__ import annotations

import math
from typing import Any

import pandas as pd

from portfolio.engine.order_types import Fill, Order, OrderSide, OrderType


class NextOpenExecutionModel:
    def __init__(self, *, brokerage_bps: float = 0.0, slippage_bps: float = 0.0):
        self.brokerage_bps = float(brokerage_bps)
        self.slippage_bps = float(slippage_bps)

    def try_fill(self, order: Order, next_bar: pd.Series) -> Fill | None:
        if int(order.quantity) <= 0:
            return None
        if order.order_type != OrderType.MARKET_NEXT_OPEN:
            return None

        open_price = _positive_float(next_bar.get("open"))
        if open_price is None:
            return None

        quantity = int(order.quantity)
        price = self._slipped_price(open_price, order.side)
        notional = price * quantity
        return Fill(
            fill_id=f"{order.order_id}-fill-1",
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=quantity,
            price=round(price, 6),
            fees=round(notional * self.brokerage_bps / 10_000.0, 6),
            slippage=round(abs(price - open_price) * quantity, 6),
            timestamp=_timestamp(next_bar.get("date")),
            strategy_id=order.strategy_id,
        )

    def _slipped_price(self, price: float, side: OrderSide) -> float:
        if side == OrderSide.BUY:
            return price * (1.0 + self.slippage_bps / 10_000.0)
        return price * (1.0 - self.slippage_bps / 10_000.0)


def _positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed <= 0:
        return None
    return parsed


def _timestamp(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(pd.to_datetime(value).date())
    except (TypeError, ValueError):
        return str(value)
