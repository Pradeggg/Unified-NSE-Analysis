"""Multiple-testing defense for bottom-up discovery survivors.

This is the first C4 statistics gate. It applies bootstrap confidence intervals,
one-sided bootstrap p-values, Benjamini-Hochberg FDR using the registered trial
count, a max-statistic reality-check bootstrap over the C4 candidate set, and a
simple trial-adjusted z score. It does not claim to be a full DSR/SPA/CSCV
implementation yet.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MultipleTestingConfig:
    n_boot: int = 5_000
    alpha: float = 0.05
    fdr_alpha: float = 0.05
    confidence: float = 0.95
    seed: int = 20260622
    r_col: str = "r_net"


@dataclass(frozen=True)
class BootstrapMeanResult:
    n: int
    mean_r: float
    std_r: float
    ci_low_r: float
    ci_high_r: float
    p_value: float
    z_score: float


def bootstrap_mean_test(
    values: Iterable[float],
    *,
    n_boot: int = 5_000,
    confidence: float = 0.95,
    seed: int = 20260622,
) -> BootstrapMeanResult:
    r = _clean_returns(values)
    n = int(r.size)
    if n == 0:
        return BootstrapMeanResult(0, np.nan, np.nan, np.nan, np.nan, 1.0, np.nan)

    mean = float(r.mean())
    std = float(r.std(ddof=1)) if n > 1 else 0.0
    z_score = _z_score(mean, std, n)
    rng = np.random.default_rng(seed)
    boot_means = _bootstrap_means(r, int(n_boot), rng)
    tail = (1.0 - float(confidence)) / 2.0
    ci_low, ci_high = np.quantile(boot_means, [tail, 1.0 - tail])

    centered = r - mean
    null_means = _bootstrap_means(centered, int(n_boot), rng)
    p_value = (float((null_means >= mean).sum()) + 1.0) / (float(n_boot) + 1.0)
    return BootstrapMeanResult(
        n=n,
        mean_r=mean,
        std_r=std,
        ci_low_r=float(ci_low),
        ci_high_r=float(ci_high),
        p_value=float(min(max(p_value, 0.0), 1.0)),
        z_score=z_score,
    )


def benjamini_hochberg(frame: pd.DataFrame, *, p_col: str = "bootstrap_p_value", n_tests: int | None = None) -> pd.DataFrame:
    if frame is None or frame.empty:
        out = pd.DataFrame() if frame is None else frame.copy()
        out["fdr_q_value"] = []
        return out
    out = frame.copy()
    p = pd.to_numeric(out[p_col], errors="coerce").fillna(1.0).clip(0.0, 1.0)
    total_tests = max(int(n_tests or len(out)), len(out), 1)
    order = np.argsort(p.to_numpy())
    sorted_p = p.to_numpy()[order]
    raw_q = np.minimum(sorted_p * total_tests / np.arange(1, len(sorted_p) + 1), 1.0)
    monotonic = np.minimum.accumulate(raw_q[::-1])[::-1]
    q = np.empty_like(monotonic)
    q[order] = monotonic
    out["fdr_q_value"] = q
    return out


def run_c4_multiple_testing(
    *,
    representatives: pd.DataFrame,
    candidate_trades: pd.DataFrame,
    n_trials: int,
    config: MultipleTestingConfig | None = None,
) -> pd.DataFrame:
    config = config or MultipleTestingConfig()
    if representatives is None or representatives.empty:
        return pd.DataFrame()
    trades = candidate_trades.copy()
    if trades.empty:
        return pd.DataFrame()

    ids = representatives["candidate_id"].astype(str).tolist()
    groups = {
        str(candidate_id): frame
        for candidate_id, frame in trades.loc[trades["candidate_id"].astype(str).isin(ids)].groupby("candidate_id", dropna=False)
    }

    rows: list[dict] = []
    for ordinal, rep in enumerate(representatives.to_dict("records"), start=1):
        candidate_id = str(rep["candidate_id"])
        returns = groups.get(candidate_id, pd.DataFrame()).get(config.r_col, pd.Series(dtype=float))
        stats = bootstrap_mean_test(
            returns,
            n_boot=config.n_boot,
            confidence=config.confidence,
            seed=config.seed + ordinal,
        )
        expected_max_z = _expected_max_null_z(n_trials)
        deflated_z = stats.z_score - expected_max_z if math.isfinite(stats.z_score) else np.nan
        row = dict(rep)
        row.update(
            {
                "trades": stats.n,
                "observed_mean_r": round(stats.mean_r, 6) if math.isfinite(stats.mean_r) else np.nan,
                "bootstrap_ci_low_r": round(stats.ci_low_r, 6) if math.isfinite(stats.ci_low_r) else np.nan,
                "bootstrap_ci_high_r": round(stats.ci_high_r, 6) if math.isfinite(stats.ci_high_r) else np.nan,
                "bootstrap_p_value": round(stats.p_value, 8),
                "z_score": round(stats.z_score, 6) if math.isfinite(stats.z_score) else np.nan,
                "expected_max_null_z": round(expected_max_z, 6),
                "deflated_z": round(deflated_z, 6) if math.isfinite(deflated_z) else np.nan,
            }
        )
        rows.append(row)

    result = benjamini_hochberg(pd.DataFrame(rows), p_col="bootstrap_p_value", n_tests=n_trials)
    reality_p = reality_check_p_value(
        {
            str(candidate_id): groups.get(str(candidate_id), pd.DataFrame()).get(config.r_col, pd.Series(dtype=float))
            for candidate_id in ids
        },
        n_boot=config.n_boot,
        seed=config.seed + 99_001,
    )
    result["reality_check_p_value"] = round(reality_p, 8)
    status_rows = result.apply(lambda row: _c4_status(row, config), axis=1, result_type="expand")
    result = pd.concat([result.reset_index(drop=True), status_rows.reset_index(drop=True)], axis=1)
    return result.sort_values(["c4_status", "observed_mean_r", "fdr_q_value"], ascending=[True, False, True]).reset_index(drop=True)


def reality_check_p_value(candidate_returns: dict[str, Iterable[float]], *, n_boot: int = 5_000, seed: int = 20260622) -> float:
    cleaned = {key: _clean_returns(values) for key, values in candidate_returns.items()}
    cleaned = {key: values for key, values in cleaned.items() if values.size > 0}
    if not cleaned:
        return 1.0
    observed_best = max(float(values.mean()) for values in cleaned.values())
    rng = np.random.default_rng(seed)
    max_null = np.full(int(n_boot), -np.inf)
    for values in cleaned.values():
        centered = values - float(values.mean())
        null_means = _bootstrap_means(centered, int(n_boot), rng)
        max_null = np.maximum(max_null, null_means)
    return float(((max_null >= observed_best).sum() + 1.0) / (float(n_boot) + 1.0))


def write_c4_outputs(*, output_dir: str | Path, run_id: str, result: pd.DataFrame, n_trials: int) -> dict[str, Path]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    passed = result.loc[result["c4_status"].eq("passed")].copy() if result is not None and not result.empty else pd.DataFrame()
    rejected = result.loc[result["c4_status"].eq("rejected")].copy() if result is not None and not result.empty else pd.DataFrame()
    paths = {
        "result_csv": out_dir / f"{run_id}_c4_multiple_testing.csv",
        "passed_csv": out_dir / f"{run_id}_c4_passed.csv",
        "rejections_jsonl": out_dir / f"{run_id}_c4_rejections.jsonl",
        "markdown": out_dir / f"{run_id}_c4_multiple_testing.md",
    }
    result.to_csv(paths["result_csv"], index=False)
    passed.to_csv(paths["passed_csv"], index=False)
    with paths["rejections_jsonl"].open("w", encoding="utf-8") as handle:
        for row in rejected.to_dict("records"):
            handle.write(
                json.dumps(
                    {
                        "run_id": run_id,
                        "candidate_id": row.get("candidate_id"),
                        "stage": "C4",
                        "reason": row.get("c4_rejection_reason"),
                        "details": {
                            "bootstrap_p_value": row.get("bootstrap_p_value"),
                            "fdr_q_value": row.get("fdr_q_value"),
                            "deflated_z": row.get("deflated_z"),
                            "reality_check_p_value": row.get("reality_check_p_value"),
                        },
                        "recorded_at": datetime.now(timezone.utc).isoformat(),
                    },
                    sort_keys=True,
                    default=str,
                )
                + "\n"
            )
    paths["markdown"].write_text(_c4_markdown(run_id=run_id, result=result, passed=passed, n_trials=n_trials), encoding="utf-8")
    return paths


def _c4_status(row: pd.Series, config: MultipleTestingConfig) -> dict[str, str]:
    if _num(row.get("bootstrap_ci_low_r")) <= 0:
        return {"c4_status": "rejected", "c4_rejection_reason": "bootstrap_ci_includes_zero"}
    if _num(row.get("bootstrap_p_value")) > config.alpha:
        return {"c4_status": "rejected", "c4_rejection_reason": "bootstrap_p_value_above_alpha"}
    if _num(row.get("fdr_q_value")) > config.fdr_alpha:
        return {"c4_status": "rejected", "c4_rejection_reason": "fdr_q_value_above_alpha"}
    if _num(row.get("deflated_z")) <= 0:
        return {"c4_status": "rejected", "c4_rejection_reason": "trial_adjusted_z_not_positive"}
    if _num(row.get("reality_check_p_value")) > config.alpha:
        return {"c4_status": "rejected", "c4_rejection_reason": "reality_check_p_value_above_alpha"}
    return {"c4_status": "passed", "c4_rejection_reason": ""}


def _c4_markdown(*, run_id: str, result: pd.DataFrame, passed: pd.DataFrame, n_trials: int) -> str:
    rejected = result.loc[result["c4_status"].eq("rejected")] if result is not None and not result.empty else pd.DataFrame()
    reasons = (
        rejected.groupby("c4_rejection_reason").size().reset_index(name="count").sort_values("count", ascending=False)
        if not rejected.empty
        else pd.DataFrame(columns=["c4_rejection_reason", "count"])
    )
    cols = [
        "candidate_id",
        "trigger",
        "confirmations",
        "context_gates",
        "scope",
        "trades",
        "observed_mean_r",
        "bootstrap_ci_low_r",
        "bootstrap_p_value",
        "fdr_q_value",
        "deflated_z",
        "reality_check_p_value",
        "c4_status",
        "c4_rejection_reason",
    ]
    available = [col for col in cols if col in result.columns]
    return "\n".join(
        [
            f"# C4 Multiple-Testing Defense - {run_id}",
            "",
            f"- Registered N Trials: {n_trials}",
            f"- Candidates Tested At C4: {len(result):,}",
            f"- Passed C4: {len(passed):,}",
            f"- Rejected C4: {len(rejected):,}",
            "",
            "## Candidate Results",
            "",
            _md_table(result.loc[:, available] if available else result),
            "",
            "## C4 Rejection Reasons",
            "",
            _md_table(reasons),
            "",
            "Method note: this is a conservative C4 v1 using bootstrap CIs/p-values, BH FDR with the full registered trial count, a survivor-set max-statistic reality check, and a simple trial-adjusted z score. Full DSR, SPA, and CSCV are still separate implementation steps.",
            "",
        ]
    )


def _bootstrap_means(values: np.ndarray, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    if values.size == 0:
        return np.array([np.nan])
    if values.size == 1:
        return np.repeat(float(values[0]), int(n_boot))
    samples = rng.choice(values, size=(int(n_boot), int(values.size)), replace=True)
    return samples.mean(axis=1)


def _clean_returns(values: Iterable[float]) -> np.ndarray:
    arr = pd.to_numeric(pd.Series(list(values)), errors="coerce").dropna().to_numpy(dtype=float)
    arr = arr[np.isfinite(arr)]
    return arr


def _expected_max_null_z(n_trials: int) -> float:
    trials = max(int(n_trials), 2)
    probability = min(max(1.0 - 1.0 / trials, 0.5), 0.999999)
    return float(NormalDist().inv_cdf(probability))


def _z_score(mean: float, std: float, n: int) -> float:
    if n <= 0:
        return float("nan")
    if std <= 0:
        if mean > 0:
            return float("inf")
        if mean < 0:
            return float("-inf")
        return 0.0
    return float(mean / (std / math.sqrt(n)))


def _num(value) -> float:
    try:
        if value is None:
            return float("nan")
        number = float(value)
        return number if math.isfinite(number) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _md_table(frame: pd.DataFrame) -> str:
    if frame is None or frame.empty:
        return "_None._"
    display = frame.copy().replace({np.nan: ""})
    headers = list(display.columns)
    rows = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for record in display.to_dict("records"):
        rows.append("| " + " | ".join(str(record.get(column, "")) for column in headers) + " |")
    return "\n".join(rows)
