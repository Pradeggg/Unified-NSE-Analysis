from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from portfolio.engine.events import (
    EngineEvent,
    FillEvent,
    MarketDataEvent,
    OrderEvent,
    PortfolioSnapshotEvent,
    SignalEvent,
)
from portfolio.engine.execution_models import NextOpenExecutionModel
from portfolio.engine.order_types import Fill, Order, OrderSide, OrderType
from portfolio.engine.portfolio_account import PortfolioAccount
from portfolio.engine.strategy_compiler import CompiledStrategy, compile_strategy


@dataclass(frozen=True)
class ReplayConfig:
    initial_capital: float = 1_000_000.0
    max_position_pct: float | None = None
    slippage_bps: float = 0.0
    brokerage_bps: float = 0.0


@dataclass
class ReplayResult:
    account: PortfolioAccount
    events: list[EngineEvent] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    equity_snapshots: list[dict[str, Any]] = field(default_factory=list)

    @property
    def trade_ledger(self) -> list[dict[str, Any]]:
        return [fill.as_dict() for fill in self.fills]

    @property
    def nav_history(self) -> list[dict[str, Any]]:
        return self.equity_snapshots

    @property
    def positions(self) -> list[dict[str, Any]]:
        return self.account.positions_as_dicts()

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "events": [event.as_dict() for event in self.events],
            "orders": [order.as_dict() for order in self.orders],
            "fills": [fill.as_dict() for fill in self.fills],
            "equity_snapshots": list(self.equity_snapshots),
            "positions": self.positions,
            "cash": self.account.cash,
            "realized_pnl": self.account.realized_pnl,
        }


def run_replay(df: pd.DataFrame, strategy_specs: list[dict[str, Any]], config: ReplayConfig) -> ReplayResult:
    data = _normalize(df)
    strategies = [compile_strategy(raw) for raw in strategy_specs]
    account = PortfolioAccount(initial_capital=config.initial_capital)
    execution = NextOpenExecutionModel(
        slippage_bps=config.slippage_bps,
        brokerage_bps=config.brokerage_bps,
    )
    result = ReplayResult(account=account)
    pending_orders: list[Order] = []
    order_seq = 0
    event_seq = 0

    def emit(event: type[EngineEvent], timestamp: str, **kwargs: Any) -> None:
        nonlocal event_seq
        event_seq += 1
        result.events.append(event(sequence=event_seq, timestamp=timestamp, **kwargs))

    for as_of, day in data.groupby("date", sort=True):
        date_str = _date_str(as_of)
        prices: dict[str, float] = {}

        for _, row in day.sort_values("symbol", kind="mergesort").iterrows():
            symbol = str(row["symbol"]).upper()
            prices[symbol] = float(row["close"])
            emit(
                MarketDataEvent,
                date_str,
                symbol=symbol,
                payload=_market_payload(row),
            )

            fills = _fill_eligible_orders(
                pending_orders=pending_orders,
                symbol=symbol,
                current_date=date_str,
                row=row,
                execution=execution,
                account=account,
            )
            for fill in fills:
                result.fills.append(fill)
                emit(
                    FillEvent,
                    date_str,
                    strategy_id=fill.strategy_id,
                    symbol=fill.symbol,
                    reason=f"{fill.side.value.lower()} filled at next open",
                    payload=fill.as_dict(),
                )

            for strategy in strategies:
                order_seq = _evaluate_strategy_row(
                    strategy=strategy,
                    row=row,
                    date_str=date_str,
                    account=account,
                    pending_orders=pending_orders,
                    result=result,
                    emit=emit,
                    order_seq=order_seq,
                    config=config,
                )

        snapshot = account.mark_to_market(prices, date_str)
        result.equity_snapshots.append(snapshot)
        emit(PortfolioSnapshotEvent, date_str, payload=snapshot)

    result.orders = [account.orders[order.order_id] for order in result.orders]
    return result


def _evaluate_strategy_row(
    *,
    strategy: CompiledStrategy,
    row: pd.Series,
    date_str: str,
    account: PortfolioAccount,
    pending_orders: list[Order],
    result: ReplayResult,
    emit: Any,
    order_seq: int,
    config: ReplayConfig,
) -> int:
    symbol = str(row["symbol"]).upper()
    strategy_id = strategy.spec.strategy_id
    position = account.positions.get(symbol)
    has_pending = any(order.symbol == symbol and order.strategy_id == strategy_id for order in pending_orders)

    if position is None and not has_pending and strategy.should_enter(row):
        reason = "entry rule matched"
        emit(SignalEvent, date_str, strategy_id=strategy_id, symbol=symbol, reason=reason)
        quantity = _entry_quantity(account, strategy, row, config)
        if quantity <= 0:
            return order_seq
        order_seq += 1
        order = _order(
            order_seq=order_seq,
            strategy_id=strategy_id,
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            date_str=date_str,
            reason=reason,
        )
        account.submit_order(order)
        pending_orders.append(order)
        result.orders.append(order)
        emit(OrderEvent, date_str, strategy_id=strategy_id, symbol=symbol, reason=reason, payload=order.as_dict())
        return order_seq

    if position is not None and not has_pending and strategy.should_exit(row):
        reason = "exit rule matched"
        emit(SignalEvent, date_str, strategy_id=strategy_id, symbol=symbol, reason=reason)
        order_seq += 1
        order = _order(
            order_seq=order_seq,
            strategy_id=strategy_id,
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=position.quantity,
            date_str=date_str,
            reason=reason,
        )
        account.submit_order(order)
        pending_orders.append(order)
        result.orders.append(order)
        emit(OrderEvent, date_str, strategy_id=strategy_id, symbol=symbol, reason=reason, payload=order.as_dict())
        return order_seq

    if position is not None and not has_pending and strategy.should_add(row, {"quantity": position.quantity}):
        reason = "add rule matched"
        emit(SignalEvent, date_str, strategy_id=strategy_id, symbol=symbol, reason=reason)
        quantity = _entry_quantity(account, strategy, row, config)
        if quantity <= 0:
            return order_seq
        order_seq += 1
        order = _order(
            order_seq=order_seq,
            strategy_id=strategy_id,
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            date_str=date_str,
            reason=reason,
        )
        account.submit_order(order)
        pending_orders.append(order)
        result.orders.append(order)
        emit(OrderEvent, date_str, strategy_id=strategy_id, symbol=symbol, reason=reason, payload=order.as_dict())
        return order_seq

    return order_seq


def _fill_eligible_orders(
    *,
    pending_orders: list[Order],
    symbol: str,
    current_date: str,
    row: pd.Series,
    execution: NextOpenExecutionModel,
    account: PortfolioAccount,
) -> list[Fill]:
    fills: list[Fill] = []
    for order in list(pending_orders):
        if order.symbol != symbol or order.submitted_at >= current_date:
            continue
        fill = execution.try_fill(order, row)
        if fill is None:
            continue
        account.apply_fill(fill)
        pending_orders.remove(order)
        fills.append(fill)
    return fills


def _entry_quantity(
    account: PortfolioAccount,
    strategy: CompiledStrategy,
    row: pd.Series,
    config: ReplayConfig,
) -> int:
    price = _positive_float(row.get("close"))
    if price is None:
        return 0
    position_pct = strategy.spec.risk.max_position_pct
    if config.max_position_pct is not None:
        position_pct = min(position_pct, config.max_position_pct)
    budget = min(account.cash, account.equity({}) * (position_pct / 100.0))
    return int(budget // price)


def _order(
    *,
    order_seq: int,
    strategy_id: str,
    symbol: str,
    side: OrderSide,
    quantity: int,
    date_str: str,
    reason: str,
) -> Order:
    return Order(
        order_id=f"ord_{order_seq:06d}",
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type=OrderType.MARKET_NEXT_OPEN,
        submitted_at=date_str,
        strategy_id=strategy_id,
        reason=reason,
    )


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.rename(columns={col: col.strip().lower() for col in df.columns}).copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["symbol"] = out["symbol"].astype(str).str.upper()
    for col in ("open", "high", "low", "close"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.dropna(subset=["date", "symbol", "open", "high", "low", "close"]).sort_values(
        ["date", "symbol"],
        kind="mergesort",
    )


def _market_payload(row: pd.Series) -> dict[str, Any]:
    return {
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": int(row["volume"]) if "volume" in row and pd.notna(row["volume"]) else None,
    }


def _positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not pd.notna(parsed) or parsed <= 0:
        return None
    return parsed


def _date_str(value: Any) -> str:
    return str(pd.to_datetime(value).date())
