from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StrategyDiagnostics:
    profit_factor: float
    expectancy: float
    average_win: float
    average_loss: float
    turnover_pct: float
    cost_drag_pct: float
    exposure_pct: float
    rank_score: float

    def as_dict(self) -> dict[str, float]:
        return {
            "profit_factor": self.profit_factor,
            "expectancy": self.expectancy,
            "average_win": self.average_win,
            "average_loss": self.average_loss,
            "turnover_pct": self.turnover_pct,
            "cost_drag_pct": self.cost_drag_pct,
            "exposure_pct": self.exposure_pct,
            "rank_score": self.rank_score,
        }


def calculate_strategy_diagnostics(replay_result: Any, metrics: dict[str, Any]) -> StrategyDiagnostics:
    fills = list(getattr(replay_result, "fills", []))
    snapshots = list(getattr(replay_result, "nav_history", getattr(replay_result, "equity_snapshots", [])))
    starting_equity = _number(metrics.get("starting_equity")) or _number(getattr(getattr(replay_result, "account", None), "initial_capital", None)) or 0.0
    total_return_pct = _number(metrics.get("total_return_pct")) or 0.0
    max_drawdown_pct = _number(metrics.get("max_drawdown_pct")) or 0.0
    trade_pnls = _closed_trade_pnls(fills)
    wins = [pnl for pnl in trade_pnls if pnl > 0]
    losses = [pnl for pnl in trade_pnls if pnl < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_win / gross_loss if gross_loss > 0 else (gross_win if gross_win > 0 else 0.0)
    expectancy = sum(trade_pnls) / len(trade_pnls) if trade_pnls else 0.0
    notional = sum((_number(_field(fill, "quantity")) or 0.0) * (_number(_field(fill, "price")) or 0.0) for fill in fills)
    fees = sum(_number(_field(fill, "fees")) or 0.0 for fill in fills)
    slippage = sum(_number(_field(fill, "slippage")) or 0.0 for fill in fills)
    exposure_days = sum(1 for row in snapshots if (_number(_field(row, "market_value")) or 0.0) > 0)
    exposure_pct = exposure_days / len(snapshots) * 100.0 if snapshots else 0.0
    active_penalty = 0.0 if fills else 100.0
    return StrategyDiagnostics(
        profit_factor=_round(profit_factor),
        expectancy=_round(expectancy),
        average_win=_round(gross_win / len(wins) if wins else 0.0),
        average_loss=_round(sum(losses) / len(losses) if losses else 0.0),
        turnover_pct=_round(notional / starting_equity * 100.0 if starting_equity else 0.0),
        cost_drag_pct=_round((fees + slippage) / starting_equity * 100.0 if starting_equity else 0.0),
        exposure_pct=_round(exposure_pct),
        rank_score=_round(total_return_pct - max_drawdown_pct - active_penalty),
    )


def _closed_trade_pnls(fills: list[Any]) -> list[float]:
    positions: dict[str, dict[str, float]] = {}
    pnls: list[float] = []
    for fill in fills:
        symbol = str(_field(fill, "symbol") or "").upper()
        side = str(_field(fill, "side") or "").upper()
        quantity = _number(_field(fill, "quantity")) or 0.0
        price = _number(_field(fill, "price")) or 0.0
        fees = _number(_field(fill, "fees")) or 0.0
        if not symbol or quantity <= 0 or price <= 0:
            continue
        if side == "BUY":
            current = positions.get(symbol, {"quantity": 0.0, "avg_cost": 0.0})
            total_quantity = current["quantity"] + quantity
            total_cost = current["quantity"] * current["avg_cost"] + quantity * price + fees
            positions[symbol] = {"quantity": total_quantity, "avg_cost": total_cost / total_quantity}
            continue
        if side != "SELL" or symbol not in positions:
            continue
        current = positions[symbol]
        sell_quantity = min(quantity, current["quantity"])
        proceeds = sell_quantity * price - fees
        pnls.append(round(proceeds - current["avg_cost"] * sell_quantity, 6))
        remaining = current["quantity"] - sell_quantity
        if remaining > 0:
            positions[symbol] = {"quantity": remaining, "avg_cost": current["avg_cost"]}
        else:
            positions.pop(symbol, None)
    return pnls


def _field(row: Any, name: str) -> Any:
    if isinstance(row, dict):
        return row.get(name)
    value = getattr(row, name, None)
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


def _round(value: float) -> float:
    return round(float(value), 6)
