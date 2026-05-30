from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True)
class PortfolioMetrics:
    starting_equity: float
    ending_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    number_of_trades: int
    number_of_fills: int
    realized_pnl: float
    winning_trades: int
    losing_trades: int
    flat_trades: int
    open_positions_count: int
    strategy_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_metrics(
    replay_result: Any | None = None,
    *,
    starting_equity: float | None = None,
    ending_equity: float | None = None,
    equity_snapshots: Iterable[Any] | None = None,
    fills: Iterable[Any] | None = None,
    positions: Iterable[Any] | None = None,
    realized_pnl: float | None = None,
) -> PortfolioMetrics:
    """Calculate deterministic portfolio and trade metrics.

    The function accepts the engine's ReplayResult, or plain inputs for tests and
    later CLI/report integrations.
    """

    snapshots = list(equity_snapshots if equity_snapshots is not None else _attr(replay_result, "equity_snapshots", []))
    fill_rows = list(fills if fills is not None else _attr(replay_result, "fills", []))
    position_rows = list(positions if positions is not None else _attr(replay_result, "positions", []))
    account = _attr(replay_result, "account", None)

    if starting_equity is None:
        starting_equity = _number(_attr(account, "initial_capital", None))
    if starting_equity is None and snapshots:
        starting_equity = _number(_field(snapshots[0], "nav"))
    if starting_equity is None:
        starting_equity = 0.0

    if ending_equity is None and snapshots:
        ending_equity = _number(_field(snapshots[-1], "nav"))
    if ending_equity is None:
        ending_equity = starting_equity

    if realized_pnl is None:
        realized_pnl = _number(_attr(account, "realized_pnl", None))
    if realized_pnl is None and snapshots:
        realized_pnl = _number(_field(snapshots[-1], "realized_pnl"))
    if realized_pnl is None:
        realized_pnl = 0.0

    nav_values = [_number(_field(row, "nav")) for row in snapshots]
    nav_values = [value for value in nav_values if value is not None]
    if nav_values and (not _same_money(nav_values[0], starting_equity)):
        nav_values.insert(0, float(starting_equity))

    trade_pnls = _closed_trade_pnls(fill_rows)
    strategy_ids = sorted(
        {
            strategy_id
            for strategy_id in (_field(fill, "strategy_id") for fill in fill_rows)
            if strategy_id not in {None, ""}
        }
    )

    return PortfolioMetrics(
        starting_equity=_money(starting_equity),
        ending_equity=_money(ending_equity),
        total_return_pct=_pct_return(starting_equity, ending_equity),
        max_drawdown_pct=_max_drawdown_pct(nav_values),
        number_of_trades=len(trade_pnls),
        number_of_fills=len(fill_rows),
        realized_pnl=_money(realized_pnl),
        winning_trades=sum(1 for pnl in trade_pnls if pnl > 0),
        losing_trades=sum(1 for pnl in trade_pnls if pnl < 0),
        flat_trades=sum(1 for pnl in trade_pnls if pnl == 0),
        open_positions_count=_open_positions_count(position_rows, snapshots),
        strategy_ids=strategy_ids,
    )


def _closed_trade_pnls(fills: list[Any]) -> list[float]:
    lots: dict[tuple[str, str], list[dict[str, float]]] = {}
    trade_pnls: list[float] = []

    for fill in fills:
        side = str(_field(fill, "side") or "").upper()
        symbol = str(_field(fill, "symbol") or "").upper()
        strategy_id = str(_field(fill, "strategy_id") or "")
        quantity = _number(_field(fill, "quantity")) or 0.0
        price = _number(_field(fill, "price", _field(fill, "fill_price"))) or 0.0
        fees = _number(_field(fill, "fees")) or 0.0
        if not symbol or not strategy_id or quantity <= 0 or price <= 0:
            continue

        key = (strategy_id, symbol)
        if side == "BUY":
            lots.setdefault(key, []).append(
                {
                    "quantity": quantity,
                    "cost_per_share": (quantity * price + fees) / quantity,
                }
            )
            continue

        if side != "SELL":
            continue

        remaining = quantity
        realized = -(fees)
        while remaining > 0 and lots.get(key):
            lot = lots[key][0]
            matched = min(remaining, lot["quantity"])
            realized += matched * (price - lot["cost_per_share"])
            lot["quantity"] -= matched
            remaining -= matched
            if lot["quantity"] <= 0:
                lots[key].pop(0)
        trade_pnls.append(_money(realized))

    return trade_pnls


def _open_positions_count(positions: list[Any], snapshots: list[Any]) -> int:
    if positions:
        return sum(1 for position in positions if (_number(_field(position, "quantity")) or 0.0) > 0)
    if snapshots:
        value = _number(_field(snapshots[-1], "open_positions"))
        if value is not None:
            return int(value)
    return 0


def _max_drawdown_pct(nav_values: list[float]) -> float:
    if not nav_values:
        return 0.0
    peak = nav_values[0]
    max_drawdown = 0.0
    for value in nav_values:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - value) / peak * 100.0)
    return round(max_drawdown, 4)


def _pct_return(starting: float, ending: float) -> float:
    if starting == 0:
        return 0.0
    return round((ending - starting) / starting * 100.0, 4)


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    return getattr(obj, name, default)


def _field(row: Any, name: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(name, default)
    value = getattr(row, name, default)
    if hasattr(value, "value"):
        return value.value
    return value


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in {float("inf"), float("-inf")}:
        return None
    return parsed


def _money(value: float) -> float:
    return round(float(value), 6)


def _same_money(left: float, right: float) -> bool:
    return _money(left) == _money(right)
