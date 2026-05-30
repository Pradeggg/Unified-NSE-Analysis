from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from portfolio.engine.order_types import Fill, Order, OrderSide, OrderStatus


class PortfolioAccountError(ValueError):
    """Raised when a paper fill would create an impossible long-only account state."""


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: int
    avg_price: float
    strategy_ids: tuple[str, ...]


class PortfolioAccount:
    def __init__(self, *, initial_capital: float):
        self.initial_capital = _money(initial_capital)
        self.cash = _money(initial_capital)
        self.positions: dict[str, Position] = {}
        self.orders: dict[str, Order] = {}
        self.fills: list[Fill] = []
        self.realized_pnl = 0.0
        self.nav_history: list[dict[str, Any]] = []

    def submit_order(self, order: Order) -> Order:
        quantity = _positive_quantity(order.quantity)
        if quantity is None:
            raise PortfolioAccountError("quantity must be positive")
        if order.side not in {OrderSide.BUY, OrderSide.SELL}:
            raise PortfolioAccountError(f"unsupported order side: {order.side}")
        normalized = order.with_status(OrderStatus.SUBMITTED)
        self.orders[normalized.order_id] = normalized
        return normalized

    def apply_fill(self, fill: Fill | dict[str, Any]) -> None:
        normalized = self._normalize_fill(fill)
        self._validate_fill(normalized)

        try:
            if normalized.side == OrderSide.BUY:
                self._apply_buy(normalized)
            elif normalized.side == OrderSide.SELL:
                self._apply_sell(normalized)
            else:
                raise PortfolioAccountError(f"unsupported fill side: {normalized.side}")
        except PortfolioAccountError:
            self._set_order_status(normalized.order_id, OrderStatus.REJECTED)
            raise

        self.fills.append(normalized)
        self._set_order_status(normalized.order_id, OrderStatus.FILLED)

    def mark_to_market(self, prices: dict[str, float], as_of: str) -> dict[str, Any]:
        market_value = 0.0
        for symbol, position in self.positions.items():
            mark = _positive_price(prices.get(symbol))
            price = position.avg_price if mark is None else mark
            market_value += position.quantity * price

        row = {
            "timestamp": as_of,
            "cash": _money(self.cash),
            "market_value": _money(market_value),
            "nav": _money(self.cash + market_value),
            "realized_pnl": _money(self.realized_pnl),
            "open_positions": len(self.positions),
        }
        self.nav_history.append(row)
        return row

    def equity(self, prices: dict[str, float]) -> float:
        market_value = 0.0
        for symbol, position in self.positions.items():
            mark = _positive_price(prices.get(symbol))
            price = position.avg_price if mark is None else mark
            market_value += position.quantity * price
        return _money(self.cash + market_value)

    def positions_as_dicts(self) -> list[dict[str, Any]]:
        return [asdict(position) for position in self.positions.values()]

    def _apply_buy(self, fill: Fill) -> None:
        cost = _money(fill.quantity * fill.price + fill.fees)
        if cost > self.cash:
            raise PortfolioAccountError("insufficient cash")

        current = self.positions.get(fill.symbol)
        self.cash = _money(self.cash - cost)
        if current is None:
            self.positions[fill.symbol] = Position(
                symbol=fill.symbol,
                quantity=fill.quantity,
                avg_price=_money(fill.price),
                strategy_ids=(fill.strategy_id,),
            )
            return

        quantity = current.quantity + fill.quantity
        avg_price = ((current.quantity * current.avg_price) + (fill.quantity * fill.price)) / quantity
        strategy_ids = tuple(sorted(set(current.strategy_ids + (fill.strategy_id,))))
        self.positions[fill.symbol] = Position(
            symbol=fill.symbol,
            quantity=quantity,
            avg_price=_money(avg_price),
            strategy_ids=strategy_ids,
        )

    def _apply_sell(self, fill: Fill) -> None:
        current = self.positions.get(fill.symbol)
        held = 0 if current is None else current.quantity
        if fill.quantity > held:
            raise PortfolioAccountError("cannot sell more than held")
        if current is None:
            raise PortfolioAccountError("cannot sell more than held")

        proceeds = _money(fill.quantity * fill.price - fill.fees)
        self.cash = _money(self.cash + proceeds)
        self.realized_pnl = _money(self.realized_pnl + ((fill.price - current.avg_price) * fill.quantity) - fill.fees)
        remaining = current.quantity - fill.quantity
        if remaining == 0:
            self.positions.pop(fill.symbol, None)
            return
        self.positions[fill.symbol] = Position(
            symbol=current.symbol,
            quantity=remaining,
            avg_price=current.avg_price,
            strategy_ids=current.strategy_ids,
        )

    def _normalize_fill(self, fill: Fill | dict[str, Any]) -> Fill:
        if isinstance(fill, Fill):
            return fill
        side = fill.get("side")
        return Fill(
            fill_id=str(fill.get("fill_id") or f"{fill['order_id']}-fill-1"),
            order_id=str(fill["order_id"]),
            symbol=str(fill["symbol"]).upper(),
            side=side if isinstance(side, OrderSide) else OrderSide(str(side).upper()),
            quantity=_int_or_zero(fill.get("quantity")),
            price=_float_or_nan(fill.get("price", fill.get("fill_price"))),
            fees=_float_or_zero(fill.get("fees")),
            slippage=_float_or_zero(fill.get("slippage")),
            timestamp=str(fill.get("timestamp", fill.get("fill_date", ""))),
            strategy_id=str(fill["strategy_id"]),
        )

    def _validate_fill(self, fill: Fill) -> None:
        if _positive_quantity(fill.quantity) is None:
            self._set_order_status(fill.order_id, OrderStatus.REJECTED)
            raise PortfolioAccountError("quantity must be positive")
        if _positive_price(fill.price) is None:
            self._set_order_status(fill.order_id, OrderStatus.REJECTED)
            raise PortfolioAccountError("fill price must be positive")
        if not math.isfinite(float(fill.fees)) or fill.fees < 0:
            self._set_order_status(fill.order_id, OrderStatus.REJECTED)
            raise PortfolioAccountError("fees must be non-negative")

    def _set_order_status(self, order_id: str, status: OrderStatus) -> None:
        order = self.orders.get(order_id)
        if order is not None:
            self.orders[order_id] = order.with_status(status)


def _positive_quantity(value: Any) -> int | None:
    try:
        quantity = int(value)
    except (TypeError, ValueError):
        return None
    if quantity <= 0:
        return None
    return quantity


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _positive_price(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(price) or price <= 0:
        return None
    return price


def _float_or_nan(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _float_or_zero(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _money(value: float) -> float:
    return round(float(value), 6)
