"""Train-only gauntlet for registered bottom-up discovery candidates.

This module implements the next stage after the trial registry: map registered
setup specs onto historical trigger events, score them net of costs, and reject
weak candidates before validation or lockbox data is touched.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from terminal.bottom_up_discovery import DiscoveryPartitionPlan, SetupSpec, TrialRegistry


@dataclass(frozen=True)
class ScreeningConfig:
    net_r_column: str = "net_r_multiple"
    gross_r_column: str = "r_multiple"
    cost_r_column: str = "estimated_cost_r"
    min_trades: int = 30
    min_net_expectancy_r: float = 0.0
    min_profit_factor: float = 1.05
    cost_sweep_extra_r: float = 0.05
    require_positive_time_halves: bool = True


@dataclass(frozen=True)
class ScreeningResult:
    candidate_trades: pd.DataFrame
    summary: pd.DataFrame
    survivors: pd.DataFrame
    rejections: pd.DataFrame


TRADE_COLUMNS = [
    "candidate_id",
    "date",
    "symbol",
    "sector",
    "trigger_setup",
    "scope_symbol",
    "scope_session_bucket",
    "scope_vol_regime",
    "confirmations",
    "context_gates",
    "r_net",
    "r_gross",
    "cost_r",
    "volume_ratio_20d",
    "turnover_cr_20d",
    "stage",
]


SUMMARY_COLUMNS = [
    "candidate_id",
    "trigger",
    "confirmations",
    "context_gates",
    "scope",
    "trades",
    "net_expectancy_r",
    "gross_expectancy_r",
    "avg_cost_r",
    "positive_net_rate_pct",
    "profit_factor",
    "max_drawdown_r",
    "first_date",
    "last_date",
    "first_half_expectancy_r",
    "second_half_expectancy_r",
    "cost_sweep_expectancy_r",
    "status",
    "rejection_stage",
    "rejection_reason",
]


def candidate_matches_event(candidate: SetupSpec, event: pd.Series | dict[str, Any]) -> bool:
    row = event if isinstance(event, pd.Series) else pd.Series(event)
    if str(row.get("setup") or "") != candidate.trigger.primitive_id:
        return False
    if not _scope_matches(candidate, row):
        return False
    return all(_primitive_matches(item.primitive_id, item.parameters, row) for item in candidate.confirmations) and all(
        _primitive_matches(item.primitive_id, item.parameters, row) for item in candidate.context_gates
    )


def build_candidate_train_trades(
    candidates: Iterable[SetupSpec],
    events: pd.DataFrame,
    partition: DiscoveryPartitionPlan,
    config: ScreeningConfig,
) -> pd.DataFrame:
    if events is None or events.empty:
        return pd.DataFrame(columns=["stage", *TRADE_COLUMNS])

    work = events.copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    train_mask = (work["date"] >= pd.Timestamp(partition.train_start)) & (work["date"] <= pd.Timestamp(partition.train_end))
    if "model_split" in work.columns:
        split = work["model_split"].fillna("").astype(str).str.lower()
        train_mask &= split.isin({"", "train"})
    work = work.loc[train_mask].copy()
    if work.empty:
        return pd.DataFrame(columns=["stage", *TRADE_COLUMNS])

    by_trigger: dict[str, list[SetupSpec]] = {}
    for candidate in candidates:
        by_trigger.setdefault(candidate.trigger.primitive_id, []).append(candidate)

    rows: list[dict[str, Any]] = []
    for trigger, candidates_for_trigger in by_trigger.items():
        subset = work.loc[work["setup"].astype(str) == trigger]
        if subset.empty:
            continue
        for event in subset.to_dict("records"):
            event_series = pd.Series(event)
            for candidate in candidates_for_trigger:
                if not candidate_matches_event(candidate, event_series):
                    continue
                rows.append(_trade_record(candidate, event_series, config))

    if not rows:
        return pd.DataFrame(columns=["stage", *TRADE_COLUMNS])
    out = pd.DataFrame(rows)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    return out.sort_values(["date", "symbol", "candidate_id"]).reset_index(drop=True)


def summarize_candidate_trades(
    candidates: Iterable[SetupSpec],
    candidate_trades: pd.DataFrame,
    config: ScreeningConfig,
) -> pd.DataFrame:
    trades = candidate_trades.copy() if candidate_trades is not None else pd.DataFrame()
    grouped = {candidate_id: frame for candidate_id, frame in trades.groupby("candidate_id", dropna=False)} if not trades.empty else {}
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        frame = grouped.get(candidate.candidate_id, pd.DataFrame())
        row = _base_summary_record(candidate)
        if frame.empty:
            row.update(_empty_metrics())
        else:
            r_net = pd.to_numeric(frame["r_net"], errors="coerce").dropna()
            r_gross = pd.to_numeric(frame["r_gross"], errors="coerce")
            cost_r = pd.to_numeric(frame["cost_r"], errors="coerce")
            row.update(
                {
                    "trades": int(len(r_net)),
                    "net_expectancy_r": _round(r_net.mean()),
                    "gross_expectancy_r": _round(r_gross.mean()),
                    "avg_cost_r": _round(cost_r.mean()),
                    "positive_net_rate_pct": _round((r_net > 0).mean() * 100.0),
                    "profit_factor": _round(_profit_factor(r_net)),
                    "max_drawdown_r": _round(_max_drawdown(r_net)),
                    "first_date": pd.to_datetime(frame["date"]).min().date().isoformat(),
                    "last_date": pd.to_datetime(frame["date"]).max().date().isoformat(),
                }
            )
            first_half, second_half = _time_half_expectancies(frame)
            row["first_half_expectancy_r"] = _round(first_half)
            row["second_half_expectancy_r"] = _round(second_half)
            row["cost_sweep_expectancy_r"] = _round((r_net - float(config.cost_sweep_extra_r)).mean())
        _apply_screening_status(row, config)
        rows.append(row)
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def run_train_screening(
    *,
    candidates: Iterable[SetupSpec],
    events: pd.DataFrame,
    partition: DiscoveryPartitionPlan,
    config: ScreeningConfig | None = None,
    registry: TrialRegistry | None = None,
) -> ScreeningResult:
    config = config or ScreeningConfig()
    candidate_tuple = tuple(candidates)
    trades = build_candidate_train_trades(candidate_tuple, events, partition, config)
    summary = summarize_candidate_trades(candidate_tuple, trades, config)
    survivors = summary.loc[summary["status"].eq("passed")].copy().reset_index(drop=True)
    rejections = summary.loc[summary["status"].eq("rejected")].copy().reset_index(drop=True)
    if registry is not None and not rejections.empty:
        for row in rejections.to_dict("records"):
            registry.record_rejection(
                str(row["candidate_id"]),
                stage=str(row["rejection_stage"]),
                reason=str(row["rejection_reason"]),
                details={
                    "trades": int(row.get("trades") or 0),
                    "net_expectancy_r": row.get("net_expectancy_r"),
                    "profit_factor": row.get("profit_factor"),
                    "cost_sweep_expectancy_r": row.get("cost_sweep_expectancy_r"),
                },
            )
    return ScreeningResult(candidate_trades=trades, summary=summary, survivors=survivors, rejections=rejections)


def write_screening_outputs(
    *,
    output_dir: str | Path,
    run_id: str,
    summary: pd.DataFrame,
    survivors: pd.DataFrame,
    candidate_trades: pd.DataFrame,
    n_trials: int,
    partition: DiscoveryPartitionPlan,
) -> dict[str, Path]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary_csv": out_dir / f"{run_id}_train_screening_summary.csv",
        "survivors_csv": out_dir / f"{run_id}_train_screening_survivors.csv",
        "trades_csv": out_dir / f"{run_id}_candidate_train_trades.csv",
        "markdown": out_dir / f"{run_id}_train_screening.md",
    }
    summary.to_csv(paths["summary_csv"], index=False)
    survivors.to_csv(paths["survivors_csv"], index=False)
    candidate_trades.to_csv(paths["trades_csv"], index=False)
    paths["markdown"].write_text(
        _screening_markdown(
            run_id=run_id,
            summary=summary,
            survivors=survivors,
            candidate_trades=candidate_trades,
            n_trials=n_trials,
            partition=partition,
        ),
        encoding="utf-8",
    )
    return paths


def _trade_record(candidate: SetupSpec, event: pd.Series, config: ScreeningConfig) -> dict[str, Any]:
    scope = candidate.scope.to_dict()
    return {
        "stage": "C2_train_screen",
        "candidate_id": candidate.candidate_id,
        "date": event.get("date"),
        "symbol": str(event.get("symbol") or "").upper(),
        "sector": event.get("sector"),
        "trigger_setup": candidate.trigger.primitive_id,
        "scope_symbol": scope["symbol"],
        "scope_session_bucket": scope["session_bucket"],
        "scope_vol_regime": scope["vol_regime"],
        "confirmations": ",".join(item.primitive_id for item in candidate.confirmations),
        "context_gates": ",".join(item.primitive_id for item in candidate.context_gates),
        "r_net": _num(event.get(config.net_r_column)),
        "r_gross": _num(event.get(config.gross_r_column)),
        "cost_r": _num(event.get(config.cost_r_column)),
        "volume_ratio_20d": _num(event.get("volume_ratio_20d")),
        "turnover_cr_20d": _num(event.get("turnover_cr_20d")),
        "stage_value": event.get("stage"),
    }


def _base_summary_record(candidate: SetupSpec) -> dict[str, Any]:
    scope = candidate.scope.to_dict()
    return {
        "candidate_id": candidate.candidate_id,
        "trigger": candidate.trigger.primitive_id,
        "confirmations": ",".join(item.primitive_id for item in candidate.confirmations),
        "context_gates": ",".join(item.primitive_id for item in candidate.context_gates),
        "scope": f"{scope['symbol']}|{scope['session_bucket']}|{scope['vol_regime']}",
    }


def _empty_metrics() -> dict[str, Any]:
    return {
        "trades": 0,
        "net_expectancy_r": np.nan,
        "gross_expectancy_r": np.nan,
        "avg_cost_r": np.nan,
        "positive_net_rate_pct": np.nan,
        "profit_factor": np.nan,
        "max_drawdown_r": np.nan,
        "first_date": "",
        "last_date": "",
        "first_half_expectancy_r": np.nan,
        "second_half_expectancy_r": np.nan,
        "cost_sweep_expectancy_r": np.nan,
    }


def _apply_screening_status(row: dict[str, Any], config: ScreeningConfig) -> None:
    trades = int(row.get("trades") or 0)
    net = _num(row.get("net_expectancy_r"))
    pf = _num(row.get("profit_factor"))
    cost_sweep = _num(row.get("cost_sweep_expectancy_r"))
    first_half = _num(row.get("first_half_expectancy_r"))
    second_half = _num(row.get("second_half_expectancy_r"))

    if trades < int(config.min_trades):
        row.update({"status": "rejected", "rejection_stage": "C2", "rejection_reason": "insufficient_train_trades"})
        return
    if not math.isfinite(net) or net <= float(config.min_net_expectancy_r):
        row.update({"status": "rejected", "rejection_stage": "C2", "rejection_reason": "nonpositive_net_expectancy"})
        return
    if not math.isfinite(pf) or pf < float(config.min_profit_factor):
        row.update({"status": "rejected", "rejection_stage": "C2", "rejection_reason": "profit_factor_below_floor"})
        return
    if not math.isfinite(cost_sweep) or cost_sweep <= 0:
        row.update({"status": "rejected", "rejection_stage": "C3", "rejection_reason": "cost_sensitivity_failed"})
        return
    if config.require_positive_time_halves and (
        not math.isfinite(first_half) or not math.isfinite(second_half) or first_half <= 0 or second_half <= 0
    ):
        row.update({"status": "rejected", "rejection_stage": "C3", "rejection_reason": "time_subsample_instability"})
        return
    row.update({"status": "passed", "rejection_stage": "", "rejection_reason": ""})


def _scope_matches(candidate: SetupSpec, row: pd.Series) -> bool:
    scope = candidate.scope.to_dict()
    symbol = str(row.get("symbol") or "").upper()
    if scope["symbol"] not in {"ALL", "*"} and scope["symbol"] != symbol:
        return False
    session = str(row.get("session_bucket") or "eod").lower()
    if scope["session_bucket"] not in {"any", "*"} and scope["session_bucket"] != session:
        return False
    row_regime = _row_vol_regime(row)
    if scope["vol_regime"] not in {"any", "*"} and scope["vol_regime"] != row_regime:
        return False
    return True


def _row_vol_regime(row: pd.Series) -> str:
    explicit = row.get("vol_regime", row.get("volatility_regime", ""))
    text = str(explicit or "").lower().strip()
    if text in {"low", "normal", "high"}:
        return text
    adr = _num(row.get("adr_pct_20"))
    if not math.isfinite(adr):
        return "normal"
    if adr < 2.5:
        return "low"
    if adr > 6.0:
        return "high"
    return "normal"


def _primitive_matches(primitive_id: str, parameters: dict[str, Any], row: pd.Series) -> bool:
    if primitive_id == "volume_surge_floor":
        return _num(row.get("volume_ratio_20d")) >= float(parameters.get("min_volume_ratio", 1.2))
    if primitive_id == "relative_strength_rank_top_quartile":
        return _num(row.get("relative_strength")) >= float(parameters.get("rank_pct", 75))
    if primitive_id == "stage2_trend_state":
        required = str(parameters.get("required_stage", 2))
        return str(row.get("stage") or "").upper().replace(" ", "_") in {f"STAGE_{required}", required.upper()}
    if primitive_id == "liquidity_turnover_floor":
        min_turnover_cr = float(parameters.get("min_turnover_inr", 50_000_000)) / 10_000_000.0
        return _num(row.get("turnover_cr_20d")) >= min_turnover_cr
    if primitive_id == "volatility_not_extreme":
        allowed = {str(item).lower() for item in parameters.get("allowed_regimes", ["low", "normal"])}
        return _row_vol_regime(row) in allowed
    if primitive_id == "breadth_positive":
        return _num(row.get("breadth_positive_pct")) >= float(parameters.get("min_breadth_pct", 55))
    if primitive_id == "sector_rotation_top_quartile":
        return _num(row.get("sector_rank_1d")) >= float(parameters.get("sector_rank_pct", 75))
    if primitive_id == "volatility_regime_allowed":
        allowed = {str(item).lower() for item in parameters.get("allowed_regimes", ["low", "normal", "high"])}
        return _row_vol_regime(row) in allowed
    if primitive_id == "fno_pcr_supportive":
        if _num(row.get("fno_available")) != 1:
            return False
        allowed = {str(item).lower() for item in parameters.get("allowed_pcr_regimes", ["balanced", "put_heavy"])}
        return _pcr_regime(_num(row.get("fno_pcr"))) in allowed
    return False


def _pcr_regime(value: float) -> str:
    if not math.isfinite(value):
        return "unknown"
    if value >= 1.1:
        return "put_heavy"
    if value <= 0.7:
        return "call_heavy"
    return "balanced"


def _profit_factor(r_values: pd.Series) -> float:
    positives = r_values[r_values > 0].sum()
    negatives = r_values[r_values < 0].sum()
    if negatives == 0:
        return 999.0 if positives > 0 else float("nan")
    return float(positives / abs(negatives))


def _max_drawdown(r_values: pd.Series) -> float:
    if r_values.empty:
        return float("nan")
    equity = r_values.cumsum()
    drawdown = equity - equity.cummax()
    return float(drawdown.min())


def _time_half_expectancies(frame: pd.DataFrame) -> tuple[float, float]:
    if frame.empty:
        return float("nan"), float("nan")
    ordered = frame.sort_values("date")
    midpoint = len(ordered) // 2
    if midpoint <= 0 or midpoint >= len(ordered):
        return float("nan"), float("nan")
    first = pd.to_numeric(ordered.iloc[:midpoint]["r_net"], errors="coerce").mean()
    second = pd.to_numeric(ordered.iloc[midpoint:]["r_net"], errors="coerce").mean()
    return float(first), float(second)


def _screening_markdown(
    *,
    run_id: str,
    summary: pd.DataFrame,
    survivors: pd.DataFrame,
    candidate_trades: pd.DataFrame,
    n_trials: int,
    partition: DiscoveryPartitionPlan,
) -> str:
    rejected = summary.loc[summary["status"].eq("rejected")] if not summary.empty else pd.DataFrame()
    reasons = (
        rejected.groupby(["rejection_stage", "rejection_reason"]).size().reset_index(name="count").sort_values("count", ascending=False)
        if not rejected.empty
        else pd.DataFrame(columns=["rejection_stage", "rejection_reason", "count"])
    )
    top = survivors.sort_values(["net_expectancy_r", "profit_factor", "trades"], ascending=[False, False, False]).head(20) if not survivors.empty else survivors
    return "\n".join(
        [
            f"# Bottom-Up Discovery Train Screening - {run_id}",
            "",
            f"- N Trials: {n_trials}",
            f"- Candidate train trades: {len(candidate_trades):,}",
            f"- Passed C2/C3: {len(survivors):,}",
            f"- Rejected: {len(rejected):,}",
            f"- Train window: {partition.train_start.isoformat()} to {partition.train_end.isoformat()}",
            f"- Validation untouched: {partition.validation_start.isoformat()} to {partition.validation_end.isoformat()}",
            f"- Lockbox untouched: {partition.lockbox_start.isoformat()} to {partition.lockbox_end.isoformat()}",
            "",
            "## Top Survivors",
            "",
            _md_table(top[["candidate_id", "trigger", "confirmations", "context_gates", "scope", "trades", "net_expectancy_r", "profit_factor"]] if not top.empty else top),
            "",
            "## Rejection Reasons",
            "",
            _md_table(reasons),
            "",
            "Research only. This is train-only screening; validation and lockbox data are not used here.",
            "",
        ]
    )


def _md_table(frame: pd.DataFrame) -> str:
    if frame is None or frame.empty:
        return "_None._"
    display = frame.copy()
    display = display.replace({np.nan: ""})
    headers = list(display.columns)
    rows = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for record in display.to_dict("records"):
        rows.append("| " + " | ".join(str(record.get(column, "")) for column in headers) + " |")
    return "\n".join(rows)


def _num(value: Any) -> float:
    try:
        if value is None:
            return float("nan")
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", "").strip()
            if value == "":
                return float("nan")
        out = float(value)
        return out if math.isfinite(out) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _round(value: Any, ndigits: int = 4) -> float:
    number = _num(value)
    return round(float(number), ndigits) if math.isfinite(number) else float("nan")
