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
from portfolio.engine.order_types import Fill, Order, OrderSide, OrderStatus, OrderType
from portfolio.engine.portfolio_account import PortfolioAccount
from portfolio.engine.strategy_compiler import CompiledStrategy, compile_strategy


@dataclass(frozen=True)
class ReplayRiskPolicy:
    max_gross_exposure_pct: float = 95.0
    max_single_stock_pct: float = 12.0
    max_sector_pct: float = 25.0
    max_positions: int = 15
    drawdown_pause_pct: float = -15.0
    max_turnover_pct: float = 2500.0
    trim_when_position_pct_above: float = 12.0
    trim_to_position_pct: float = 10.0
    block_stage1_adds: bool = True


@dataclass(frozen=True)
class ReplayConfig:
    initial_capital: float = 1_000_000.0
    max_position_pct: float | None = None
    slippage_bps: float = 0.0
    brokerage_bps: float = 0.0
    risk_policy: ReplayRiskPolicy | None = None


@dataclass
class ReplayResult:
    account: PortfolioAccount
    events: list[EngineEvent] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    equity_snapshots: list[dict[str, Any]] = field(default_factory=list)
    strategy_positions: dict[tuple[str, str], int] = field(default_factory=dict)
    risk_events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def trade_ledger(self) -> list[dict[str, Any]]:
        return [fill.as_dict() for fill in self.fills]

    @property
    def nav_history(self) -> list[dict[str, Any]]:
        return self.equity_snapshots

    @property
    def positions(self) -> list[dict[str, Any]]:
        rows = []
        for position in self.account.positions_as_dicts():
            symbol = str(position["symbol"]).upper()
            strategy_ids = tuple(
                sorted(
                    strategy_id
                    for (strategy_id, owned_symbol), quantity in self.strategy_positions.items()
                    if owned_symbol == symbol and quantity > 0
                )
            )
            rows.append({**position, "strategy_ids": strategy_ids})
        return rows

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
    pending_reservations: dict[str, float] = {}
    strategy_positions: dict[tuple[str, str], int] = {}
    last_marks: dict[str, float] = {}
    sector_by_symbol: dict[str, str] = {}
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
            last_marks[symbol] = float(row["close"])
            sector_by_symbol[symbol] = str(row.get("sector") or "Unknown")
            prices = dict(last_marks)
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
                pending_reservations=pending_reservations,
                strategy_positions=strategy_positions,
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
                    pending_reservations=pending_reservations,
                    strategy_positions=strategy_positions,
                    prices=prices,
                    sector_by_symbol=sector_by_symbol,
                    result=result,
                    emit=emit,
                    order_seq=order_seq,
                    config=config,
                )

        snapshot = account.mark_to_market(prices, date_str)
        result.equity_snapshots.append(snapshot)
        emit(PortfolioSnapshotEvent, date_str, payload=snapshot)

    result.orders = [account.orders[order.order_id] for order in result.orders]
    result.strategy_positions = dict(strategy_positions)
    return result


def _evaluate_strategy_row(
    *,
    strategy: CompiledStrategy,
    row: pd.Series,
    date_str: str,
    account: PortfolioAccount,
    pending_orders: list[Order],
    pending_reservations: dict[str, float],
    strategy_positions: dict[tuple[str, str], int],
    prices: dict[str, float],
    sector_by_symbol: dict[str, str],
    result: ReplayResult,
    emit: Any,
    order_seq: int,
    config: ReplayConfig,
) -> int:
    symbol = str(row["symbol"]).upper()
    strategy_id = strategy.spec.strategy_id
    owned_quantity = strategy_positions.get((strategy_id, symbol), 0)
    has_pending = any(order.symbol == symbol and order.strategy_id == strategy_id for order in pending_orders)

    trim_quantity = _trim_quantity(
        account=account,
        symbol=symbol,
        prices=prices,
        policy=config.risk_policy,
    )
    if owned_quantity > 0 and trim_quantity > 0 and not has_pending:
        reason = "risk trim"
        order_seq += 1
        order = _order(
            order_seq=order_seq,
            strategy_id=strategy_id,
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=trim_quantity,
            date_str=date_str,
            reason=reason,
        )
        account.submit_order(order)
        pending_orders.append(order)
        pending_reservations[order.order_id] = 0.0
        result.orders.append(order)
        result.risk_events.append(
            {
                "date": date_str,
                "symbol": symbol,
                "strategy_id": strategy_id,
                "action": "TRIM",
                "reason_codes": ["POSITION_TRIM"],
                "quantity": trim_quantity,
            }
        )
        emit(OrderEvent, date_str, strategy_id=strategy_id, symbol=symbol, reason=reason, payload=order.as_dict())
        return order_seq

    if owned_quantity <= 0 and not has_pending and strategy.should_enter(row):
        reason = "entry rule matched"
        emit(SignalEvent, date_str, strategy_id=strategy_id, symbol=symbol, reason=reason)
        quantity = _entry_quantity(account, strategy, row, config, pending_reservations)
        if quantity <= 0:
            return order_seq
        block_reasons = _risk_block_reasons(
            account=account,
            strategy_id=strategy_id,
            symbol=symbol,
            quantity=quantity,
            row=row,
            config=config,
            pending_orders=pending_orders,
            pending_reservations=pending_reservations,
            prices=prices,
            sector_by_symbol=sector_by_symbol,
            is_add=False,
            filled_notional=_filled_notional(result.fills),
        )
        if block_reasons:
            result.risk_events.append(
                {
                    "date": date_str,
                    "symbol": symbol,
                    "strategy_id": strategy_id,
                    "action": "BLOCK_BUY",
                    "reason_codes": block_reasons,
                    "quantity": quantity,
                }
            )
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
        pending_reservations[order.order_id] = _estimated_buy_cost(order, row, config)
        result.orders.append(order)
        emit(OrderEvent, date_str, strategy_id=strategy_id, symbol=symbol, reason=reason, payload=order.as_dict())
        return order_seq

    if owned_quantity > 0 and not has_pending and strategy.should_exit(row):
        reason = "exit rule matched"
        emit(SignalEvent, date_str, strategy_id=strategy_id, symbol=symbol, reason=reason)
        order_seq += 1
        order = _order(
            order_seq=order_seq,
            strategy_id=strategy_id,
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=owned_quantity,
            date_str=date_str,
            reason=reason,
        )
        account.submit_order(order)
        pending_orders.append(order)
        pending_reservations[order.order_id] = 0.0
        result.orders.append(order)
        emit(OrderEvent, date_str, strategy_id=strategy_id, symbol=symbol, reason=reason, payload=order.as_dict())
        return order_seq

    if owned_quantity > 0 and not has_pending and strategy.should_add(row, {"quantity": owned_quantity}):
        reason = "add rule matched"
        emit(SignalEvent, date_str, strategy_id=strategy_id, symbol=symbol, reason=reason)
        quantity = _entry_quantity(account, strategy, row, config, pending_reservations)
        if quantity <= 0:
            return order_seq
        block_reasons = _risk_block_reasons(
            account=account,
            strategy_id=strategy_id,
            symbol=symbol,
            quantity=quantity,
            row=row,
            config=config,
            pending_orders=pending_orders,
            pending_reservations=pending_reservations,
            prices=prices,
            sector_by_symbol=sector_by_symbol,
            is_add=True,
            filled_notional=_filled_notional(result.fills),
        )
        if block_reasons:
            result.risk_events.append(
                {
                    "date": date_str,
                    "symbol": symbol,
                    "strategy_id": strategy_id,
                    "action": "BLOCK_BUY",
                    "reason_codes": block_reasons,
                    "quantity": quantity,
                }
            )
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
        pending_reservations[order.order_id] = _estimated_buy_cost(order, row, config)
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
    pending_reservations: dict[str, float],
    strategy_positions: dict[tuple[str, str], int],
) -> list[Fill]:
    fills: list[Fill] = []
    for order in list(pending_orders):
        if order.symbol != symbol or order.submitted_at >= current_date:
            continue
        fill = execution.try_fill(order, row)
        if fill is None:
            continue
        if fill.side == OrderSide.BUY and _fill_cost(fill) > account.cash:
            account.orders[order.order_id] = order.with_status(OrderStatus.REJECTED)
            pending_orders.remove(order)
            pending_reservations.pop(order.order_id, None)
            continue
        account.apply_fill(fill)
        pending_orders.remove(order)
        pending_reservations.pop(order.order_id, None)
        key = (fill.strategy_id, fill.symbol)
        if fill.side == OrderSide.BUY:
            strategy_positions[key] = strategy_positions.get(key, 0) + fill.quantity
        else:
            remaining = strategy_positions.get(key, 0) - fill.quantity
            if remaining > 0:
                strategy_positions[key] = remaining
            else:
                strategy_positions.pop(key, None)
        fills.append(fill)
    return fills


def _entry_quantity(
    account: PortfolioAccount,
    strategy: CompiledStrategy,
    row: pd.Series,
    config: ReplayConfig,
    pending_reservations: dict[str, float],
) -> int:
    price = _positive_float(row.get("close"))
    if price is None:
        return 0
    position_pct = strategy.spec.risk.max_position_pct
    if config.max_position_pct is not None:
        position_pct = min(position_pct, config.max_position_pct)
    available_cash = max(0.0, account.cash - sum(pending_reservations.values()))
    budget = min(available_cash, account.equity({}) * (position_pct / 100.0))
    return int(budget // price)


def _risk_block_reasons(
    *,
    account: PortfolioAccount,
    strategy_id: str,
    symbol: str,
    quantity: int,
    row: pd.Series,
    config: ReplayConfig,
    pending_orders: list[Order],
    pending_reservations: dict[str, float],
    prices: dict[str, float],
    sector_by_symbol: dict[str, str],
    is_add: bool,
    filled_notional: float,
) -> list[str]:
    policy = config.risk_policy
    if policy is None:
        return []
    price = _positive_float(row.get("close"))
    if price is None or quantity <= 0:
        return ["INVALID_PRICE_OR_QUANTITY"]

    nav = max(account.equity(prices), 1.0)
    order_value = _estimated_notional(quantity, price, config)
    market_value = _market_value(account, prices)
    reasons: list[str] = []

    if is_add and policy.block_stage1_adds and str(row.get("stage") or "").upper() == "STAGE_1":
        reasons.append("STAGE_DRIFT")

    if _drawdown_pct(account, prices) <= policy.drawdown_pause_pct:
        reasons.append("DRAWDOWN_PAUSE")

    if _turnover_pct(filled_notional, account.initial_capital) >= policy.max_turnover_pct:
        reasons.append("TURNOVER_CAP")

    projected_gross = market_value + _pending_buy_value(pending_orders, pending_reservations) + order_value
    if projected_gross > nav * policy.max_gross_exposure_pct / 100.0:
        reasons.append("GROSS_EXPOSURE_CAP")

    projected_symbol = (
        _symbol_value(account, symbol, prices)
        + _pending_buy_value(pending_orders, pending_reservations, symbol=symbol)
        + order_value
    )
    if projected_symbol > nav * policy.max_single_stock_pct / 100.0:
        reasons.append("STOCK_CAP")

    sector = str(row.get("sector") or sector_by_symbol.get(symbol) or "Unknown")
    projected_sector = (
        _sector_value(account, sector, prices, sector_by_symbol)
        + _pending_buy_value(pending_orders, pending_reservations, sector=sector, sector_by_symbol=sector_by_symbol)
        + order_value
    )
    if projected_sector > nav * policy.max_sector_pct / 100.0:
        reasons.append("SECTOR_CAP")

    pending_new_symbols = {
        order.symbol
        for order in pending_orders
        if order.side == OrderSide.BUY and order.symbol not in account.positions
    }
    projected_symbols = set(account.positions) | pending_new_symbols
    if symbol not in account.positions:
        projected_symbols.add(symbol)
    if len(projected_symbols) > policy.max_positions:
        reasons.append("MAX_POSITIONS")

    return reasons


def _trim_quantity(
    *,
    account: PortfolioAccount,
    symbol: str,
    prices: dict[str, float],
    policy: ReplayRiskPolicy | None,
) -> int:
    if policy is None:
        return 0
    position = account.positions.get(symbol)
    if position is None:
        return 0
    price = _positive_float(prices.get(symbol))
    if price is None:
        return 0
    nav = account.equity(prices)
    if nav <= 0:
        return 0
    current_value = position.quantity * price
    current_weight_pct = current_value / nav * 100.0
    if current_weight_pct <= policy.trim_when_position_pct_above:
        return 0
    target_value = nav * policy.trim_to_position_pct / 100.0
    excess_value = max(0.0, current_value - target_value)
    quantity = int(excess_value // price)
    return min(quantity, position.quantity)


def _market_value(account: PortfolioAccount, prices: dict[str, float]) -> float:
    return sum(_symbol_value(account, symbol, prices) for symbol in account.positions)


def _symbol_value(account: PortfolioAccount, symbol: str, prices: dict[str, float]) -> float:
    position = account.positions.get(symbol)
    if position is None:
        return 0.0
    price = _positive_float(prices.get(symbol)) or position.avg_price
    return position.quantity * price


def _sector_value(
    account: PortfolioAccount,
    sector: str,
    prices: dict[str, float],
    sector_by_symbol: dict[str, str],
) -> float:
    return sum(
        _symbol_value(account, symbol, prices)
        for symbol in account.positions
        if sector_by_symbol.get(symbol, "Unknown") == sector
    )


def _pending_buy_value(
    pending_orders: list[Order],
    pending_reservations: dict[str, float],
    *,
    symbol: str | None = None,
    sector: str | None = None,
    sector_by_symbol: dict[str, str] | None = None,
) -> float:
    total = 0.0
    for order in pending_orders:
        if order.side != OrderSide.BUY:
            continue
        if symbol is not None and order.symbol != symbol:
            continue
        if sector is not None and (sector_by_symbol or {}).get(order.symbol, "Unknown") != sector:
            continue
        total += pending_reservations.get(order.order_id, 0.0)
    return total


def _drawdown_pct(account: PortfolioAccount, prices: dict[str, float]) -> float:
    nav = account.equity(prices)
    prior_navs = [_positive_float(row.get("nav")) for row in account.nav_history]
    high_water = max([nav] + [value for value in prior_navs if value is not None])
    if high_water <= 0:
        return 0.0
    return (nav / high_water - 1.0) * 100.0


def _filled_notional(fills: list[Fill]) -> float:
    return sum(abs(fill.quantity * fill.price) for fill in fills)


def _turnover_pct(filled_notional: float, initial_capital: float) -> float:
    if initial_capital <= 0:
        return 0.0
    return filled_notional / initial_capital * 100.0


def _estimated_notional(quantity: int, price: float, config: ReplayConfig) -> float:
    slipped = price * (1.0 + config.slippage_bps / 10_000.0)
    notional = slipped * quantity
    fees = notional * config.brokerage_bps / 10_000.0
    return round(notional + fees, 6)


def _estimated_buy_cost(order: Order, row: pd.Series, config: ReplayConfig) -> float:
    if order.side != OrderSide.BUY:
        return 0.0
    close = _positive_float(row.get("close"))
    if close is None:
        return 0.0
    slipped = close * (1.0 + config.slippage_bps / 10_000.0)
    notional = slipped * order.quantity
    fees = notional * config.brokerage_bps / 10_000.0
    return round(notional + fees, 6)


def _fill_cost(fill: Fill) -> float:
    if fill.side != OrderSide.BUY:
        return 0.0
    return round(fill.quantity * fill.price + fill.fees, 6)


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
    out = out.dropna(subset=["date", "symbol", "open", "high", "low", "close"])
    out["symbol"] = out["symbol"].astype(str).str.strip()
    out = out[out["symbol"] != ""]
    out = out[~out["symbol"].str.casefold().isin(_SYMBOL_SENTINELS)]
    out["symbol"] = out["symbol"].str.upper()
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


_SYMBOL_SENTINELS = {"nan", "none", "null", "na", "n/a", "nat"}
