from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass(frozen=True)
class EngineEvent:
    sequence: int
    timestamp: str
    strategy_id: str | None = None
    symbol: str | None = None
    reason: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    event_type: ClassVar[str] = "EngineEvent"

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "reason": self.reason,
            "payload": self.payload,
        }


@dataclass(frozen=True)
class MarketDataEvent(EngineEvent):
    event_type: ClassVar[str] = "MarketDataEvent"


@dataclass(frozen=True)
class SignalEvent(EngineEvent):
    event_type: ClassVar[str] = "SignalEvent"


@dataclass(frozen=True)
class OrderEvent(EngineEvent):
    event_type: ClassVar[str] = "OrderEvent"


@dataclass(frozen=True)
class FillEvent(EngineEvent):
    event_type: ClassVar[str] = "FillEvent"


@dataclass(frozen=True)
class PortfolioSnapshotEvent(EngineEvent):
    event_type: ClassVar[str] = "PortfolioSnapshotEvent"
