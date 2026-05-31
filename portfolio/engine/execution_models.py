from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import pandas as pd

from portfolio.engine.order_types import Fill, Order, OrderSide, OrderType


@dataclass(frozen=True)
class CostModel:
    brokerage_bps: float = 0.0
    transaction_tax_bps: float = 0.0
    slippage_bps: float = 0.0
    fixed_slippage: float = 0.0
    fixed_fee: float = 0.0
    max_participation_pct: float = 100.0


class NextOpenExecutionModel:
    def __init__(
        self,
        *,
        brokerage_bps: float = 0.0,
        slippage_bps: float = 0.0,
        cost_model: CostModel | None = None,
        transaction_tax_bps: float = 0.0,
        fixed_slippage: float = 0.0,
        fixed_fee: float = 0.0,
        max_participation_pct: float | None = None,
    ):
        self.cost_model = cost_model or CostModel(
            brokerage_bps=brokerage_bps,
            transaction_tax_bps=transaction_tax_bps,
            slippage_bps=slippage_bps,
            fixed_slippage=fixed_slippage,
            fixed_fee=fixed_fee,
            max_participation_pct=(
                max_participation_pct
                if max_participation_pct is not None
                else float("inf")
            ),
        )
        self.brokerage_bps = float(self.cost_model.brokerage_bps)
        self.slippage_bps = float(self.cost_model.slippage_bps)

    def try_fill(self, order: Order, next_bar: pd.Series) -> Fill | None:
        quantity = _positive_int_quantity(order.quantity)
        if quantity is None:
            return None

        bar = _valid_ohlc_bar(next_bar)
        if bar is None:
            return None

        if not self._within_participation_limit(quantity, next_bar):
            return None

        base_price = self._base_fill_price(order, bar)
        if base_price is None:
            return None

        price = self._slipped_price(base_price, order.side)
        if price is None:
            return None
        notional = price * quantity
        fees = self._fees(notional)
        if fees is None:
            return None
        return Fill(
            fill_id=f"{order.order_id}-fill-1",
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=quantity,
            price=round(price, 6),
            fees=round(fees, 6),
            slippage=round(abs(price - base_price) * quantity, 6),
            timestamp=_timestamp(next_bar.get("date")),
            strategy_id=order.strategy_id,
        )

    def _base_fill_price(self, order: Order, bar: _OhlcBar) -> float | None:
        if order.order_type == OrderType.MARKET_NEXT_OPEN:
            return bar.open
        if order.order_type == OrderType.MARKET_ON_CLOSE:
            return bar.close
        if order.order_type == OrderType.LIMIT:
            return self._limit_fill_price(order, bar)
        if order.order_type == OrderType.STOP:
            return self._stop_fill_price(order, bar)
        if order.order_type == OrderType.STOP_LIMIT:
            return self._stop_limit_fill_price(order, bar)
        return None

    def _limit_fill_price(self, order: Order, bar: _OhlcBar) -> float | None:
        limit_price = _positive_float(order.limit_price)
        if limit_price is None:
            return None
        if order.side == OrderSide.BUY and bar.low <= limit_price:
            return min(bar.open, limit_price)
        if order.side == OrderSide.SELL and bar.high >= limit_price:
            return max(bar.open, limit_price)
        return None

    def _stop_fill_price(self, order: Order, bar: _OhlcBar) -> float | None:
        stop_price = _positive_float(order.stop_price)
        if stop_price is None:
            return None
        if order.side == OrderSide.BUY and bar.high >= stop_price:
            return max(bar.open, stop_price)
        if order.side == OrderSide.SELL and bar.low <= stop_price:
            return min(bar.open, stop_price)
        return None

    def _stop_limit_fill_price(self, order: Order, bar: _OhlcBar) -> float | None:
        stop_price = _positive_float(order.stop_price)
        limit_price = _positive_float(order.limit_price)
        if stop_price is None or limit_price is None:
            return None
        if (
            order.side == OrderSide.BUY
            and bar.high >= stop_price
            and bar.low <= limit_price
        ):
            if stop_price <= bar.open <= limit_price:
                return bar.open
            return limit_price
        if (
            order.side == OrderSide.SELL
            and bar.low <= stop_price
            and bar.high >= limit_price
        ):
            if limit_price <= bar.open <= stop_price:
                return bar.open
            return limit_price
        return None

    def _slipped_price(self, price: float, side: OrderSide) -> float | None:
        slippage_bps = _finite_float(self.cost_model.slippage_bps)
        fixed_slippage = _finite_float(self.cost_model.fixed_slippage)
        if slippage_bps is None or fixed_slippage is None:
            return None
        if side == OrderSide.BUY:
            slipped = price * (1.0 + slippage_bps / 10_000.0) + fixed_slippage
        else:
            slipped = price * (1.0 - slippage_bps / 10_000.0) - fixed_slippage
        return slipped if math.isfinite(slipped) and slipped > 0 else None

    def _fees(self, notional: float) -> float | None:
        brokerage_bps = _finite_float(self.cost_model.brokerage_bps)
        transaction_tax_bps = _finite_float(self.cost_model.transaction_tax_bps)
        fixed_fee = _finite_float(self.cost_model.fixed_fee)
        if brokerage_bps is None or transaction_tax_bps is None or fixed_fee is None:
            return None
        fees = notional * (brokerage_bps + transaction_tax_bps) / 10_000.0 + fixed_fee
        return fees if math.isfinite(fees) and fees >= 0 else None

    def _within_participation_limit(self, quantity: int, next_bar: pd.Series) -> bool:
        try:
            max_participation_pct = float(self.cost_model.max_participation_pct)
        except (TypeError, ValueError):
            return False
        if math.isinf(max_participation_pct):
            return True
        if not math.isfinite(max_participation_pct) or max_participation_pct <= 0:
            return False
        volume = _positive_float(next_bar.get("volume"))
        if volume is None:
            return False
        return quantity <= volume * max_participation_pct / 100.0


@dataclass(frozen=True)
class _OhlcBar:
    open: float
    high: float
    low: float
    close: float


def _valid_ohlc_bar(next_bar: pd.Series) -> _OhlcBar | None:
    open_price = _positive_float(next_bar.get("open"))
    high_price = _positive_float(next_bar.get("high"))
    low_price = _positive_float(next_bar.get("low"))
    close_price = _positive_float(next_bar.get("close"))
    if (
        open_price is None
        or high_price is None
        or low_price is None
        or close_price is None
    ):
        return None
    if "volume" in next_bar:
        if high_price < max(open_price, close_price, low_price):
            return None
        if low_price > min(open_price, close_price, high_price):
            return None
    return _OhlcBar(open=open_price, high=high_price, low=low_price, close=close_price)


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed <= 0:
        return None
    return parsed


def _positive_int_quantity(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value <= 0:
        return None
    return value


def _timestamp(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(pd.to_datetime(value).date())
    except (TypeError, ValueError):
        return str(value)
