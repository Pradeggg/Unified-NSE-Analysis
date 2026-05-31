from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd

from portfolio.agents.report_agent import ReportAgent
from portfolio.defaults import sample_ohlcv, valid_strategy_spec
from portfolio.engine.audit_log import AuditLog
from portfolio.engine.benchmark import compare_to_benchmark
from portfolio.engine.event_loop import ReplayConfig, run_replay
from portfolio.engine.metrics import PortfolioMetrics, calculate_metrics
from portfolio.engine.run_manifest import build_run_manifest
from portfolio.engine.validation import validate_ohlcv


DEFAULT_RUN_ID = "PT-0"
DEFAULT_OUTPUT_DIR = Path("portfolio/data/paper")
STATE_RELATIVE_PATH = Path("state/replay_state.json")
METRICS_RELATIVE_PATH = Path("metrics/metrics.json")
AUDIT_RELATIVE_PATH = Path("logs/audit.jsonl")
REPORT_RELATIVE_PATH = Path("reports/paper_trading_report.md")
VALIDATION_RELATIVE_PATH = Path("validation/data_quality.json")
BENCHMARK_RELATIVE_PATH = Path("benchmarks/benchmark.json")
MANIFEST_RELATIVE_PATH = Path("manifest/run_manifest.json")


class CliArtifactError(RuntimeError):
    pass


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
    try:
        return int(args.func(args))
    except CliArtifactError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _cmd_replay(args: argparse.Namespace) -> int:
    output_dir = args.output_dir
    state_path = output_dir / STATE_RELATIVE_PATH
    metrics_path = output_dir / METRICS_RELATIVE_PATH
    audit_path = output_dir / AUDIT_RELATIVE_PATH
    report_path = output_dir / REPORT_RELATIVE_PATH
    validation_path = output_dir / VALIDATION_RELATIVE_PATH
    benchmark_path = output_dir / BENCHMARK_RELATIVE_PATH
    manifest_path = output_dir / MANIFEST_RELATIVE_PATH

    data = _load_ohlcv(args.data)
    strategy_specs = _load_strategy_specs(args.strategy)
    validation = validate_ohlcv(data)
    _write_json(validation_path, validation.as_dict())

    result = run_replay(
        data,
        strategy_specs,
        ReplayConfig(initial_capital=args.initial_capital),
    )
    metrics = calculate_metrics(result)
    state = _state_payload(args.run_id, result, metrics.as_dict())
    benchmark = compare_to_benchmark(
        state["nav_history"],
        _fixture_buy_hold_benchmark(data),
        benchmark_id="fixture_buy_hold",
    )
    artifact_paths = {
        "state": state_path,
        "metrics": metrics_path,
        "audit": audit_path,
        "report": report_path,
        "validation": validation_path,
        "benchmark": benchmark_path,
        "manifest": manifest_path,
    }
    manifest = build_run_manifest(
        run_id=args.run_id,
        config={"initial_capital": args.initial_capital},
        strategy_specs=strategy_specs,
        data=data,
        artifacts=artifact_paths,
    )

    _write_json(state_path, state)
    _write_json(metrics_path, metrics.as_dict())
    _write_json(benchmark_path, benchmark.as_dict())
    _write_json(manifest_path, manifest.as_dict())

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
            "audit_path": str(audit_path),
            "report_path": str(report_path),
            "validation_path": str(validation_path),
            "benchmark_path": str(benchmark_path),
            "manifest_path": str(manifest_path),
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
    print(f"Validation: {validation_path}")
    print(f"Benchmark: {benchmark_path}")
    print(f"Manifest: {manifest_path}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    state_path = args.state or args.output_dir / STATE_RELATIVE_PATH
    metrics_path = args.metrics or args.output_dir / METRICS_RELATIVE_PATH
    state = _read_json(state_path)
    metrics = _read_metrics(metrics_path)
    summary = state.get("summary", {})

    print(f"Run: {state.get('run_id', 'unknown')}")
    print(f"Last date: {summary.get('last_timestamp', 'n/a')}")
    print(f"Strategy: {', '.join(summary.get('strategy_ids') or metrics.strategy_ids or ['n/a'])}")
    print(f"Ending equity: {metrics.ending_equity:.2f}")
    print(f"Total return: {metrics.total_return_pct:.3f}%")
    print(f"Fills: {metrics.number_of_fills}")
    print(f"Open positions: {metrics.open_positions_count}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    output_dir = args.output_dir
    report_path = args.report or output_dir / REPORT_RELATIVE_PATH
    state_path = args.state or output_dir / STATE_RELATIVE_PATH
    metrics_path = args.metrics or output_dir / METRICS_RELATIVE_PATH
    audit_path = output_dir / AUDIT_RELATIVE_PATH

    if not report_path.exists():
        state = _read_json(state_path)
        metrics = _read_metrics(metrics_path)
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


def _fixture_buy_hold_benchmark(data: pd.DataFrame) -> pd.DataFrame:
    if not {"date", "close"}.issubset(data.columns):
        return pd.DataFrame(columns=["date", "close"])
    return data.loc[:, ["date", "close"]].copy()


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
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise CliArtifactError(f"missing artifact: {path}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliArtifactError(f"corrupt artifact: {path}") from exc
    if not isinstance(payload, dict):
        raise CliArtifactError(f"corrupt artifact: {path}")
    return payload


def _read_metrics(path: Path) -> PortfolioMetrics:
    payload = _read_json(path)
    return _coerce_metrics(path, payload)


def _coerce_metrics(path: Path, payload: dict[str, Any]) -> PortfolioMetrics:
    try:
        return PortfolioMetrics(
            starting_equity=_float_metric(path, payload, "starting_equity"),
            ending_equity=_float_metric(path, payload, "ending_equity"),
            total_return_pct=_float_metric(path, payload, "total_return_pct"),
            max_drawdown_pct=_float_metric(path, payload, "max_drawdown_pct"),
            number_of_trades=_int_metric(path, payload, "number_of_trades"),
            number_of_fills=_int_metric(path, payload, "number_of_fills"),
            realized_pnl=_float_metric(path, payload, "realized_pnl"),
            winning_trades=_int_metric(path, payload, "winning_trades"),
            losing_trades=_int_metric(path, payload, "losing_trades"),
            flat_trades=_int_metric(path, payload, "flat_trades"),
            open_positions_count=_int_metric(path, payload, "open_positions_count"),
            invalid_fill_sequences=_int_metric(path, payload, "invalid_fill_sequences", default=0),
            strategy_ids=_strategy_ids_metric(path, payload),
        )
    except CliArtifactError:
        raise
    except (TypeError, ValueError) as exc:
        raise CliArtifactError(f"corrupt artifact: {path}: invalid metrics") from exc


def _float_metric(path: Path, payload: dict[str, Any], field: str) -> float:
    value = _required_metric(path, payload, field)
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise CliArtifactError(f"corrupt artifact: {path}: invalid metric {field}") from exc
    if parsed != parsed or parsed in {float("inf"), float("-inf")}:
        raise CliArtifactError(f"corrupt artifact: {path}: invalid metric {field}")
    return parsed


def _int_metric(path: Path, payload: dict[str, Any], field: str, *, default: int | None = None) -> int:
    if field not in payload and default is not None:
        return default
    value = _required_metric(path, payload, field)
    if isinstance(value, bool):
        raise CliArtifactError(f"corrupt artifact: {path}: invalid metric {field}")
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CliArtifactError(f"corrupt artifact: {path}: invalid metric {field}") from exc
    if numeric != numeric or numeric in {float("inf"), float("-inf")}:
        raise CliArtifactError(f"corrupt artifact: {path}: invalid metric {field}")
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CliArtifactError(f"corrupt artifact: {path}: invalid metric {field}") from exc
    if parsed != numeric:
        raise CliArtifactError(f"corrupt artifact: {path}: invalid metric {field}")
    return parsed


def _strategy_ids_metric(path: Path, payload: dict[str, Any]) -> list[str]:
    value = payload.get("strategy_ids", [])
    if not isinstance(value, list):
        raise CliArtifactError(f"corrupt artifact: {path}: invalid metric strategy_ids")
    return [str(item) for item in value]


def _required_metric(path: Path, payload: dict[str, Any], field: str) -> Any:
    if field not in payload:
        raise CliArtifactError(f"corrupt artifact: {path}: missing metric {field}")
    return payload[field]


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _first_or_none(values: list[str]) -> str | None:
    return values[0] if values else None


if __name__ == "__main__":
    sys.exit(main())
