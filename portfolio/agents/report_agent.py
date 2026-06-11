from __future__ import annotations

from pathlib import Path
from typing import Any

from portfolio.engine.metrics import PortfolioMetrics, calculate_metrics


class ReportAgent:
    """Deterministic Markdown report writer for paper trading PT-0."""

    def write_markdown_report(
        self,
        path: str | Path,
        *,
        replay_result: Any | None = None,
        metrics: PortfolioMetrics | dict[str, Any] | None = None,
        audit_log_path: str | Path | None = None,
        title: str = "Paper Trading Report",
    ) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        markdown = self.generate_markdown_report(
            replay_result=replay_result,
            metrics=metrics,
            audit_log_path=audit_log_path,
            title=title,
        )
        destination.write_text(markdown, encoding="utf-8")
        return destination

    def generate_markdown_report(
        self,
        *,
        replay_result: Any | None = None,
        metrics: PortfolioMetrics | dict[str, Any] | None = None,
        audit_log_path: str | Path | None = None,
        title: str = "Paper Trading Report",
    ) -> str:
        metric_obj = _metrics(metrics, replay_result)
        positions = list(getattr(replay_result, "positions", []) if replay_result is not None else [])
        fills = list(getattr(replay_result, "fills", []) if replay_result is not None else [])
        snapshots = list(getattr(replay_result, "equity_snapshots", []) if replay_result is not None else [])

        sections = [
            f"# {title}",
            self._summary(metric_obj),
            self._strategy_metrics(metric_obj),
            self._pnl_breakdown(metric_obj, positions, fills, snapshots),
            self._open_positions(positions, snapshots),
            self._closed_trades(fills),
            self._fills(fills),
            self._audit_references(audit_log_path),
        ]
        return "\n\n".join(sections).rstrip() + "\n"

    def _summary(self, metrics: PortfolioMetrics) -> str:
        return "\n".join(
            [
                "## Summary",
                "| Metric | Value |",
                "| --- | ---: |",
                f"| Starting equity | {metrics.starting_equity:.2f} |",
                f"| Ending equity | {metrics.ending_equity:.2f} |",
                f"| Total return | {metrics.total_return_pct:.3f}% |",
                f"| Max drawdown | {metrics.max_drawdown_pct:.3f}% |",
                f"| Realized P&L | {metrics.realized_pnl:.2f} |",
                f"| Open positions | {metrics.open_positions_count} |",
            ]
        )

    def _pnl_breakdown(
        self,
        metrics: PortfolioMetrics,
        positions: list[Any],
        fills: list[Any],
        snapshots: list[Any],
    ) -> str:
        latest = snapshots[-1] if snapshots else {}
        cash = _number(_field(latest, "cash"))
        market_value = _number(_field(latest, "market_value"))
        open_cost_basis = _open_cost_basis(positions)
        unrealized_pnl = None
        if market_value is not None and open_cost_basis is not None:
            unrealized_pnl = market_value - open_cost_basis
        total_pnl = metrics.ending_equity - metrics.starting_equity
        total_fees = sum(_number(_field(fill, "fees")) or 0.0 for fill in fills)
        total_slippage = sum(_number(_field(fill, "slippage")) or 0.0 for fill in fills)

        return "\n".join(
            [
                "## P&L Breakdown",
                "| Metric | Value |",
                "| --- | ---: |",
                f"| Cash | {_money_text(cash)} |",
                f"| Open market value | {_money_text(market_value)} |",
                f"| Open cost basis | {_money_text(open_cost_basis)} |",
                f"| Realized P&L | {metrics.realized_pnl:.2f} |",
                f"| Unrealized P&L | {_money_text(unrealized_pnl)} |",
                f"| Total P&L | {total_pnl:.2f} |",
                f"| Total fees | {total_fees:.2f} |",
                f"| Total slippage | {total_slippage:.2f} |",
            ]
        )

    def _strategy_metrics(self, metrics: PortfolioMetrics) -> str:
        strategy_ids = ", ".join(metrics.strategy_ids) if metrics.strategy_ids else "n/a"
        return "\n".join(
            [
                "## Strategy Metrics",
                "| Metric | Value |",
                "| --- | ---: |",
                f"| Strategy IDs | {strategy_ids} |",
                f"| Fills | {metrics.number_of_fills} |",
                f"| Closed trades | {metrics.number_of_trades} |",
                f"| Winning trades | {metrics.winning_trades} |",
                f"| Losing trades | {metrics.losing_trades} |",
                f"| Flat trades | {metrics.flat_trades} |",
            ]
        )

    def _open_positions(self, positions: list[Any], snapshots: list[Any]) -> str:
        lines = [
            "## Open Positions",
            "| Symbol | Quantity | Avg Price | Avg Cost | Cost Basis | Mark Price | Market Value | Unrealized P&L | Strategy IDs |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
        if not positions:
            lines.append("| n/a | 0 | 0.00 | 0.00 | 0.00 | n/a | n/a | n/a | n/a |")
            return "\n".join(lines)

        market_value = _number(_field(snapshots[-1], "market_value")) if snapshots else None
        for position in positions:
            quantity = int(_number(_field(position, "quantity")) or 0)
            avg_price = _number(_field(position, "avg_price")) or 0.0
            avg_cost = _number(_field(position, "avg_cost")) or avg_price
            cost_basis = avg_cost * quantity
            row_market_value = market_value if len(positions) == 1 else None
            mark_price = row_market_value / quantity if row_market_value is not None and quantity else None
            unrealized_pnl = row_market_value - cost_basis if row_market_value is not None else None
            lines.append(
                "| {symbol} | {quantity} | {avg_price:.2f} | {avg_cost:.2f} | {cost_basis:.2f} | "
                "{mark_price} | {market_value} | {unrealized_pnl} | {strategy_ids} |".format(
                    symbol=_field(position, "symbol", "n/a"),
                    quantity=quantity,
                    avg_price=avg_price,
                    avg_cost=avg_cost,
                    cost_basis=cost_basis,
                    mark_price=_money_text(mark_price),
                    market_value=_money_text(row_market_value),
                    unrealized_pnl=_money_text(unrealized_pnl),
                    strategy_ids=_format_strategy_ids(_field(position, "strategy_ids")),
                )
            )
        return "\n".join(lines)

    def _closed_trades(self, fills: list[Any]) -> str:
        lines = [
            "## Closed Trades",
            "| Exit Date | Strategy | Symbol | Quantity | Avg Cost | Exit Price | Fees | Realized P&L |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        trades = _closed_trade_rows(fills)
        if not trades:
            lines.append("| n/a | n/a | n/a | 0 | 0.00 | 0.00 | 0.00 | 0.00 |")
            return "\n".join(lines)

        for trade in trades:
            lines.append(
                "| {date} | {strategy_id} | {symbol} | {quantity} | {avg_cost:.2f} | {exit_price:.2f} | "
                "{fees:.2f} | {realized_pnl:.2f} |".format(**trade)
            )
        return "\n".join(lines)

    def _fills(self, fills: list[Any]) -> str:
        lines = [
            "## Fills",
            "| Date | Strategy | Symbol | Side | Quantity | Price | Fees |",
            "| --- | --- | --- | --- | ---: | ---: | ---: |",
        ]
        if not fills:
            lines.append("| n/a | n/a | n/a | n/a | 0 | 0.00 | 0.00 |")
            return "\n".join(lines)

        for fill in fills:
            lines.append(
                "| {date} | {strategy_id} | {symbol} | {side} | {quantity} | {price:.2f} | {fees:.2f} |".format(
                    date=_field(fill, "timestamp", _field(fill, "fill_date", "n/a")),
                    strategy_id=_field(fill, "strategy_id", "n/a"),
                    symbol=_field(fill, "symbol", "n/a"),
                    side=str(_field(fill, "side", "n/a")).upper(),
                    quantity=int(_number(_field(fill, "quantity")) or 0),
                    price=_number(_field(fill, "price", _field(fill, "fill_price"))) or 0.0,
                    fees=_number(_field(fill, "fees")) or 0.0,
                )
            )
        return "\n".join(lines)

    def _audit_references(self, audit_log_path: str | Path | None) -> str:
        reference = "n/a" if audit_log_path is None else str(audit_log_path)
        return "\n".join(
            [
                "## Audit / Log References",
                "| Reference | Value |",
                "| --- | --- |",
                f"| Audit log | {reference} |",
            ]
        )


def _metrics(metrics: PortfolioMetrics | dict[str, Any] | None, replay_result: Any | None) -> PortfolioMetrics:
    if isinstance(metrics, PortfolioMetrics):
        return metrics
    if isinstance(metrics, dict):
        return PortfolioMetrics(**metrics)
    return calculate_metrics(replay_result)


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


def _format_strategy_ids(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item) for item in value) or "n/a"
    return str(value)


def _money_text(value: Any) -> str:
    parsed = _number(value)
    return "n/a" if parsed is None else f"{parsed:.2f}"


def _open_cost_basis(positions: list[Any]) -> float | None:
    if not positions:
        return 0.0
    total = 0.0
    has_position = False
    for position in positions:
        quantity = _number(_field(position, "quantity")) or 0.0
        avg_cost = _number(_field(position, "avg_cost", _field(position, "avg_price")))
        if quantity <= 0 or avg_cost is None:
            continue
        has_position = True
        total += quantity * avg_cost
    return total if has_position else None


def _closed_trade_rows(fills: list[Any]) -> list[dict[str, Any]]:
    positions: dict[str, dict[str, float]] = {}
    rows: list[dict[str, Any]] = []

    for fill in fills:
        side = str(_field(fill, "side") or "").upper()
        symbol = str(_field(fill, "symbol") or "").upper()
        strategy_id = str(_field(fill, "strategy_id") or "n/a")
        quantity = _number(_field(fill, "quantity")) or 0.0
        price = _number(_field(fill, "price", _field(fill, "fill_price"))) or 0.0
        fees = _number(_field(fill, "fees")) or 0.0
        if not symbol or quantity <= 0 or price <= 0:
            continue

        if side == "BUY":
            current = positions.get(symbol)
            cost = quantity * price + fees
            if current is None:
                positions[symbol] = {"quantity": quantity, "avg_cost": cost / quantity}
                continue
            total_quantity = current["quantity"] + quantity
            total_cost = current["quantity"] * current["avg_cost"] + cost
            positions[symbol] = {"quantity": total_quantity, "avg_cost": total_cost / total_quantity}
            continue

        if side != "SELL":
            continue

        current = positions.get(symbol)
        if current is None or quantity > current["quantity"]:
            continue
        proceeds = quantity * price - fees
        realized = proceeds - current["avg_cost"] * quantity
        rows.append(
            {
                "date": _field(fill, "timestamp", _field(fill, "fill_date", "n/a")),
                "strategy_id": strategy_id,
                "symbol": symbol,
                "quantity": int(quantity),
                "avg_cost": current["avg_cost"],
                "exit_price": price,
                "fees": fees,
                "realized_pnl": realized,
            }
        )
        remaining = current["quantity"] - quantity
        if remaining > 0:
            positions[symbol] = {"quantity": remaining, "avg_cost": current["avg_cost"]}
        else:
            positions.pop(symbol, None)

    return rows
