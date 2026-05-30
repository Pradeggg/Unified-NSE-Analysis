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

        sections = [
            f"# {title}",
            self._summary(metric_obj),
            self._strategy_metrics(metric_obj),
            self._open_positions(positions),
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

    def _open_positions(self, positions: list[Any]) -> str:
        lines = [
            "## Open Positions",
            "| Symbol | Quantity | Avg Price | Strategy IDs |",
            "| --- | ---: | ---: | --- |",
        ]
        if not positions:
            lines.append("| n/a | 0 | 0.00 | n/a |")
            return "\n".join(lines)

        for position in positions:
            lines.append(
                "| {symbol} | {quantity} | {avg_price:.2f} | {strategy_ids} |".format(
                    symbol=_field(position, "symbol", "n/a"),
                    quantity=int(_number(_field(position, "quantity")) or 0),
                    avg_price=_number(_field(position, "avg_price")) or 0.0,
                    strategy_ids=_format_strategy_ids(_field(position, "strategy_ids")),
                )
            )
        return "\n".join(lines)

    def _fills(self, fills: list[Any]) -> str:
        lines = [
            "## Fills / Trades",
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
