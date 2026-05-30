from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import StrEnum


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET_NEXT_OPEN = "MARKET_NEXT_OPEN"
    MARKET_ON_CLOSE = "MARKET_ON_CLOSE"
    STOP = "STOP"
    LIMIT = "LIMIT"


class OrderStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class Order:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    order_type: OrderType
    submitted_at: str
    strategy_id: str
    reason: str
    limit_price: float | None = None
    stop_price: float | None = None
    status: OrderStatus = OrderStatus.SUBMITTED

    @property
    def created_date(self) -> str:
        return self.submitted_at

    def with_status(self, status: OrderStatus) -> Order:
        return replace(self, status=status)

    def as_dict(self) -> dict[str, object]:
        row = asdict(self)
        row["side"] = self.side.value
        row["order_type"] = self.order_type.value
        row["status"] = self.status.value
        return row


@dataclass(frozen=True)
class Fill:
    fill_id: str
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    fees: float
    slippage: float
    timestamp: str
    strategy_id: str

    @property
    def fill_price(self) -> float:
        return self.price

    @property
    def fill_date(self) -> str:
        return self.timestamp

    def with_price(self, price: float) -> Fill:
        return replace(self, price=price)

    def as_dict(self) -> dict[str, object]:
        row = asdict(self)
        row["side"] = self.side.value
        row["fill_price"] = self.price
        row["fill_date"] = self.timestamp
        return row
