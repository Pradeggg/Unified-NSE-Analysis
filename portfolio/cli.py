from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd

from portfolio.agents.report_agent import ReportAgent
from portfolio.engine.audit_log import AuditLog
from portfolio.engine.event_loop import ReplayConfig, run_replay
from portfolio.engine.metrics import calculate_metrics
from tests.portfolio.fixtures import sample_ohlcv, valid_strategy_spec


DEFAULT_RUN_ID = "PT-0"
DEFAULT_OUTPUT_DIR = Path("portfolio/data/paper")
STATE_RELATIVE_PATH = Path("state/replay_state.json")
METRICS_RELATIVE_PATH = Path("metrics/metrics.json")
AUDIT_RELATIVE_PATH = Path("logs/audit.jsonl")
REPORT_RELATIVE_PATH = Path("reports/paper_trading_report.md")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="portfolio")
    subcommands = parser.add_subparsers(dest="command", required=True)

    replay = subcommands.add_parser("replay", help="Run deterministic PT-0 fixture replay")
    replay.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    replay.add_argument("--data", type=Path, default=None)
    replay.add_argument("--strategy", type=Path, default=None)
    replay.add_argument("--initial-capital", type=float, default=1_000_000.0)
    replay.add_argument("--run-id", default=DEFAULT_RUN_ID)
    replay.set_defaults(func=_cmd_replay)

    status = subcommands.add_parser("status", help="Print saved replay status")
    status.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    status.add_argument("--state", type=Path, default=None)
    status.add_argument("--metrics", type=Path, default=None)
    status.set_defaults(func=_cmd_status)

    report = subcommands.add_parser("report", help="Print or regenerate saved Markdown report")
    report.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    report.add_argument("--state", type=Path, default=None)
    report.add_argument("--metrics", type=Path, default=None)
    report.add_argument("--report", type=Path, default=None)
    report.add_argument("--print", action="store_true", dest="print_report")
    report.set_defaults(func=_cmd_report)

    args = parser.parse_args(argv)
    return int(args.func(args))


def _cmd_replay(args: argparse.Namespace) -> int:
    output_dir = args.output_dir
    state_path = output_dir / STATE_RELATIVE_PATH
    metrics_path = output_dir / METRICS_RELATIVE_PATH
    audit_path = output_dir / AUDIT_RELATIVE_PATH
    report_path = output_dir / REPORT_RELATIVE_PATH

    data = _load_ohlcv(args.data)
    strategy_specs = _load_strategy_specs(args.strategy)
    result = run_replay(
        data,
        strategy_specs,
        ReplayConfig(initial_capital=args.initial_capital),
    )
    metrics = calculate_metrics(result)
    state = _state_payload(args.run_id, result, metrics.as_dict())

    _write_json(state_path, state)
    _write_json(metrics_path, metrics.as_dict())

    report_agent = ReportAgent()
    report_agent.write_markdown_report(
        report_path,
        replay_result=result,
        metrics=metrics,
        audit_log_path=audit_path,
    )

    if audit_path.exists():
        audit_path.unlink()
    audit = AuditLog(audit_path)
    audit.append(
        timestamp=f"{state['summary']['last_timestamp']}T00:00:00",
        date=state["summary"]["last_timestamp"],
        agent="portfolio.cli",
        action="run_replay",
        strategy_id=_first_or_none(state["summary"]["strategy_ids"]),
        reason="deterministic PT-0 fixture replay completed",
        payload={
            "run_id": args.run_id,
            "state_path": str(state_path),
            "metrics_path": str(metrics_path),
            "fills": state["summary"]["fills"],
        },
    )
    audit.append(
        timestamp=f"{state['summary']['last_timestamp']}T00:00:00",
        date=state["summary"]["last_timestamp"],
        agent="report_agent",
        action="write_report",
        strategy_id=_first_or_none(state["summary"]["strategy_ids"]),
        reason="markdown report generated",
        payload={"report_path": str(report_path)},
    )

    print(f"Replay complete: {output_dir}")
    print(f"State: {state_path}")
    print(f"Metrics: {metrics_path}")
    print(f"Audit: {audit_path}")
    print(f"Report: {report_path}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    state_path = args.state or args.output_dir / STATE_RELATIVE_PATH
    metrics_path = args.metrics or args.output_dir / METRICS_RELATIVE_PATH
    state = _read_json(state_path)
    metrics = _read_json(metrics_path)
    summary = state.get("summary", {})

    print(f"Run: {state.get('run_id', 'unknown')}")
    print(f"Last date: {summary.get('last_timestamp', 'n/a')}")
    print(f"Strategy: {', '.join(summary.get('strategy_ids') or metrics.get('strategy_ids') or ['n/a'])}")
    print(f"Ending equity: {float(metrics.get('ending_equity', 0.0)):.2f}")
    print(f"Total return: {float(metrics.get('total_return_pct', 0.0)):.3f}%")
    print(f"Fills: {int(metrics.get('number_of_fills', summary.get('fills', 0)))}")
    print(f"Open positions: {int(metrics.get('open_positions_count', summary.get('open_positions', 0)))}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    output_dir = args.output_dir
    report_path = args.report or output_dir / REPORT_RELATIVE_PATH
    state_path = args.state or output_dir / STATE_RELATIVE_PATH
    metrics_path = args.metrics or output_dir / METRICS_RELATIVE_PATH
    audit_path = output_dir / AUDIT_RELATIVE_PATH

    if not report_path.exists():
        state = _read_json(state_path)
        metrics = _read_json(metrics_path)
        replay_result = _replay_result_from_state(state)
        ReportAgent().write_markdown_report(
            report_path,
            replay_result=replay_result,
            metrics=metrics,
            audit_log_path=audit_path,
        )

    if args.print_report:
        print(report_path.read_text(encoding="utf-8"), end="")
    else:
        print(f"Report: {report_path}")
    return 0


def _load_ohlcv(path: Path | None) -> pd.DataFrame:
    if path is None:
        return sample_ohlcv()
    return pd.read_csv(path)


def _load_strategy_specs(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return [valid_strategy_spec()]
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [dict(item) for item in raw]
    return [dict(raw)]


def _state_payload(run_id: str, result: Any, metrics: dict[str, Any]) -> dict[str, Any]:
    nav_history = _json_safe(result.nav_history)
    fills = _json_safe(result.trade_ledger)
    positions = _json_safe(result.positions)
    orders = _json_safe([order.as_dict() for order in result.orders])
    events = _json_safe([event.as_dict() for event in result.events])
    last_timestamp = nav_history[-1]["timestamp"] if nav_history else "no_data"

    return {
        "run_id": run_id,
        "summary": {
            "last_timestamp": last_timestamp,
            "strategy_ids": list(metrics.get("strategy_ids", [])),
            "events": len(events),
            "orders": len(orders),
            "fills": len(fills),
            "open_positions": len(positions),
            "ending_equity": metrics.get("ending_equity"),
            "realized_pnl": metrics.get("realized_pnl"),
        },
        "account": {
            "initial_capital": result.account.initial_capital,
            "cash": result.account.cash,
            "realized_pnl": result.account.realized_pnl,
        },
        "nav_history": nav_history,
        "fills": fills,
        "positions": positions,
        "orders": orders,
        "events": events,
    }


def _replay_result_from_state(state: dict[str, Any]) -> SimpleNamespace:
    account = SimpleNamespace(
        initial_capital=state.get("account", {}).get("initial_capital", 0.0),
        realized_pnl=state.get("account", {}).get("realized_pnl", 0.0),
    )
    return SimpleNamespace(
        account=account,
        equity_snapshots=state.get("nav_history", []),
        fills=state.get("fills", []),
        positions=state.get("positions", []),
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _first_or_none(values: list[str]) -> str | None:
    return values[0] if values else None


if __name__ == "__main__":
    sys.exit(main())
