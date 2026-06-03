from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd

from portfolio.agents.report_agent import ReportAgent
from portfolio.data_sources.postgres import default_dsn, load_postgres_replay_data
from portfolio.defaults import sample_ohlcv, valid_strategy_spec
from portfolio.engine.audit_log import AuditLog
from portfolio.engine.benchmark import compare_to_benchmark
from portfolio.engine.event_loop import ReplayConfig, run_replay
from portfolio.engine.leaderboard import calculate_strategy_diagnostics
from portfolio.engine.managed_portfolio import build_managed_portfolio, load_policy
from portfolio.engine.metrics import PortfolioMetrics, calculate_metrics
from portfolio.engine.paper_portfolio import publish_daily_paper_portfolio
from portfolio.engine.run_manifest import build_run_manifest
from portfolio.engine.strategy_library import built_in_strategy_specs
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

    strategy_lab = subcommands.add_parser("strategy-lab", help="Compare built-in strategies on PostgreSQL NSE EOD data")
    strategy_lab.add_argument("--output-dir", type=Path, default=Path("portfolio/data/nse_pg_strategy_lab/latest"))
    strategy_lab.add_argument("--source", choices=["postgres"], default="postgres")
    strategy_lab.add_argument("--dsn", default=default_dsn())
    strategy_lab.add_argument("--start", default="2025-01-01")
    strategy_lab.add_argument("--lookback", default="2024-01-01")
    strategy_lab.add_argument("--end", default=None)
    strategy_lab.add_argument("--top-n", type=int, default=200)
    strategy_lab.add_argument("--benchmark-id", default="Nifty 500")
    strategy_lab.add_argument("--initial-capital", type=float, default=1_000_000.0)
    strategy_lab.add_argument("--slippage-bps", type=float, default=5.0)
    strategy_lab.add_argument("--brokerage-bps", type=float, default=3.0)
    strategy_lab.add_argument("--run-id", default="NSE-PG-STRATEGY-LAB")
    strategy_lab.add_argument("--no-db-persist", action="store_true")
    strategy_lab.add_argument("--managed-portfolio", action="store_true")
    strategy_lab.add_argument("--policy", type=Path, default=Path("portfolio/config/portfolio_policy.yaml"))
    strategy_lab.add_argument("--llm-council", choices=["off", "optional"], default="off")
    strategy_lab.set_defaults(func=_cmd_strategy_lab)

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
    if not validation.is_usable:
        _remove_artifacts(
            state_path,
            metrics_path,
            audit_path,
            report_path,
            benchmark_path,
            manifest_path,
        )
        raise CliArtifactError(
            f"data validation failed: {validation.error_count} error(s), "
            f"{validation.warning_count} warning(s); see {validation_path}"
        )

    result = run_replay(
        data,
        strategy_specs,
        ReplayConfig(initial_capital=args.initial_capital),
    )
    metrics = calculate_metrics(result)
    state = _state_payload(args.run_id, result, metrics.as_dict())
    benchmark = compare_to_benchmark(
        _benchmark_nav_history(state["nav_history"]),
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
        generated_at=_manifest_generated_at(state),
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


def _cmd_strategy_lab(args: argparse.Namespace) -> int:
    output_dir = args.output_dir
    data_bundle = load_postgres_replay_data(
        dsn=args.dsn,
        start_date=args.start,
        lookback_date=args.lookback,
        end_date=args.end,
        top_n=args.top_n,
        benchmark_id=args.benchmark_id,
    )
    data = data_bundle.features
    validation = validate_ohlcv(data)
    validation_path = output_dir / VALIDATION_RELATIVE_PATH
    _write_json(validation_path, validation.as_dict())
    if not validation.is_usable:
        raise CliArtifactError(
            f"data validation failed: {validation.error_count} error(s), "
            f"{validation.warning_count} warning(s); see {validation_path}"
        )

    data_path = output_dir / "data/replay_features.csv"
    benchmark_path = output_dir / "data/benchmark.csv"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(data_path, index=False)
    data_bundle.benchmark.to_csv(benchmark_path, index=False)

    strategy_specs = built_in_strategy_specs()
    leaderboard_rows: list[dict[str, Any]] = []
    report_agent = ReportAgent()
    run_config = ReplayConfig(
        initial_capital=args.initial_capital,
        slippage_bps=args.slippage_bps,
        brokerage_bps=args.brokerage_bps,
    )
    for spec in strategy_specs:
        strategy_id = str(spec["strategy_id"])
        run_dir = output_dir / "runs" / strategy_id
        result = run_replay(data, [spec], run_config)
        metrics = calculate_metrics(result)
        benchmark = compare_to_benchmark(
            _benchmark_nav_history(result.nav_history),
            data_bundle.benchmark,
            benchmark_id=args.benchmark_id,
        )
        diagnostics = calculate_strategy_diagnostics(result, metrics.as_dict())
        state = _strategy_lab_state_payload(
            run_id=f"{args.run_id}-{strategy_id}",
            result=result,
            metrics=metrics.as_dict(),
            config={
                "source": args.source,
                "stage_source": "scores.stage_snapshots",
                "start": args.start,
                "lookback": args.lookback,
                "end": args.end,
                "top_n": args.top_n,
                "latest_eod_date": data_bundle.latest_eod_date,
                "initial_capital": args.initial_capital,
                "slippage_bps": args.slippage_bps,
                "brokerage_bps": args.brokerage_bps,
            },
        )
        _write_json(run_dir / STATE_RELATIVE_PATH, state)
        _write_json(run_dir / METRICS_RELATIVE_PATH, metrics.as_dict())
        _write_json(run_dir / BENCHMARK_RELATIVE_PATH, benchmark.as_dict())
        _write_json(run_dir / "diagnostics/diagnostics.json", diagnostics.as_dict())
        report_agent.write_markdown_report(
            run_dir / REPORT_RELATIVE_PATH,
            replay_result=result,
            metrics=metrics,
            audit_log_path=run_dir / AUDIT_RELATIVE_PATH,
        )
        closed_trades = metrics.winning_trades + metrics.losing_trades + metrics.flat_trades
        win_rate_pct = round(metrics.winning_trades / closed_trades * 100.0, 4) if closed_trades else 0.0
        leaderboard_rows.append(
            {
                "active": metrics.number_of_fills > 0,
                "strategy_id": strategy_id,
                "name": str(spec.get("name", strategy_id)),
                "ending_equity": metrics.ending_equity,
                "total_return_pct": metrics.total_return_pct,
                "max_drawdown_pct": metrics.max_drawdown_pct,
                "benchmark_return_pct": benchmark.benchmark_return_pct,
                "excess_return_pct": benchmark.excess_return_pct,
                "fills": metrics.number_of_fills,
                "closed_trades": metrics.number_of_trades,
                "win_rate_pct": win_rate_pct,
                "realized_pnl": metrics.realized_pnl,
                "open_positions": metrics.open_positions_count,
                **diagnostics.as_dict(),
                "report_path": str(run_dir / REPORT_RELATIVE_PATH),
            }
        )

    leaderboard = _strategy_lab_leaderboard(leaderboard_rows)
    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    leaderboard_path = reports_dir / "strategy_leaderboard.csv"
    leaderboard.to_csv(leaderboard_path, index=False)
    summary = {
        "run_id": args.run_id,
        "source": "PostgreSQL market.equity_eod + scores.stage_snapshots",
        "stage_source": "scores.stage_snapshots",
        "latest_eod_date": data_bundle.latest_eod_date,
        "data_path": str(data_path),
        "benchmark_path": str(benchmark_path),
        "output_dir": str(output_dir),
        "row_count": int(len(data)),
        "symbol_count": int(data["symbol"].nunique()) if "symbol" in data.columns else 0,
        "start_date": str(data["date"].min()) if not data.empty else args.start,
        "end_date": str(data["date"].max()) if not data.empty else args.end,
        "initial_capital": args.initial_capital,
        "slippage_bps": args.slippage_bps,
        "brokerage_bps": args.brokerage_bps,
        "benchmark_id": args.benchmark_id,
        "data_quality": validation.as_dict(),
        "stage_counts": data["stage"].value_counts().to_dict() if "stage" in data.columns else {},
        "leaderboard": leaderboard.to_dict(orient="records"),
    }
    summary["paper_portfolio"] = publish_daily_paper_portfolio(
        output_dir=output_dir,
        summary=summary,
        leaderboard=leaderboard,
        features=data,
        dsn=None if getattr(args, "no_db_persist", False) else args.dsn,
    )
    if getattr(args, "managed_portfolio", False):
        selected_id = str(summary["paper_portfolio"].get("selected_strategy_id") or "")
        selected_name = str(summary["paper_portfolio"].get("selected_strategy_name") or selected_id)
        state_path = output_dir / "runs" / selected_id / "state" / "replay_state.json"
        selected_state = _read_json(state_path) if state_path.exists() else {}
        policy = load_policy(args.policy)
        summary["managed_portfolio"] = build_managed_portfolio(
            output_dir=output_dir,
            run_id=args.run_id,
            selected_strategy_id=selected_id,
            selected_strategy_name=selected_name,
            features=data,
            strategy_orders=selected_state.get("orders", []),
            policy=policy,
            llm_council=args.llm_council,
        )
    _write_json(reports_dir / "strategy_comparison_summary.json", summary)
    _write_strategy_lab_report(reports_dir / "strategy_comparison_report.md", summary)

    print(f"Strategy lab complete: {output_dir}")
    print(f"Leaderboard: {leaderboard_path}")
    print(f"Report: {reports_dir / 'strategy_comparison_report.md'}")
    print(f"Summary: {reports_dir / 'strategy_comparison_summary.json'}")
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


def _strategy_lab_leaderboard(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame = frame.sort_values(
        ["active", "rank_score", "total_return_pct"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    frame.insert(0, "rank", frame.index + 1)
    return frame.drop(columns=["active"])


def _strategy_lab_state_payload(
    *,
    run_id: str,
    result: Any,
    metrics: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    state = _state_payload(run_id, result, metrics)
    state["config"] = config
    state["events"] = []
    state["summary"]["events"] = len(result.events)
    return state


def _write_strategy_lab_report(path: Path, summary: dict[str, Any]) -> None:
    rows = list(summary.get("leaderboard") or [])
    lines = [
        "# NSE PostgreSQL Strategy Lab",
        "",
        "Source: PostgreSQL `market.equity_eod` joined to `scores.stage_snapshots`.",
        f"Benchmark: `{summary.get('benchmark_id')}`.",
        (
            f"Window: {summary.get('start_date')} to {summary.get('end_date')}; "
            f"rows: {summary.get('row_count')}; symbols: {summary.get('symbol_count')}."
        ),
        (
            f"Costs: {summary.get('slippage_bps')} bps slippage + "
            f"{summary.get('brokerage_bps')} bps brokerage. "
            f"Starting capital: {summary.get('initial_capital')}."
        ),
        "",
        "## Leaderboard",
        "",
        (
            "| Rank | Strategy | Return % | Max DD % | Excess % | Profit Factor | "
            "Expectancy | Turnover % | Cost Drag % | Fills | Win Rate % |"
        ),
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {rank} | {strategy_id} | {total_return_pct:.2f} | {max_drawdown_pct:.2f} | "
            "{excess_return_pct:.2f} | {profit_factor:.2f} | {expectancy:.2f} | "
            "{turnover_pct:.2f} | {cost_drag_pct:.2f} | {fills} | {win_rate_pct:.2f} |".format(
                **row
            )
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Ranking sorts active strategies first, then by `rank_score`.",
            "- `rank_score` is return minus max drawdown, with inactive strategies penalized.",
            "- Stage values are sourced from `scores.stage_snapshots`.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fixture_buy_hold_benchmark(data: pd.DataFrame) -> pd.DataFrame:
    if not {"date", "close"}.issubset(data.columns):
        return pd.DataFrame(columns=["date", "close"])
    return data.loc[:, ["date", "close"]].copy()


def _manifest_generated_at(state: dict[str, Any]) -> str:
    timestamp = str(state.get("summary", {}).get("last_timestamp") or "no_data")
    if timestamp == "no_data":
        return "no_data"
    if "T" in timestamp:
        return timestamp
    return f"{timestamp}T00:00:00Z"


def _benchmark_nav_history(nav_history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "timestamp": row.get("timestamp"),
            "equity": row.get("equity", row.get("nav")),
        }
        for row in nav_history
    ]


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
        json.dumps(_json_safe(payload), allow_nan=False, indent=2, sort_keys=True) + "\n",
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
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str) or value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Sequence):
        return [_json_safe(item) for item in value]
    if pd.isna(value):
        return None
    return str(value)


def _remove_artifacts(*paths: Path) -> None:
    for path in paths:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _first_or_none(values: list[str]) -> str | None:
    return values[0] if values else None


if __name__ == "__main__":
    sys.exit(main())
