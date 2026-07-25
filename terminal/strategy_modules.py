"""Named Agent Adda strategy modules for EOD signal-effectiveness research."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd


@dataclass(frozen=True)
class StrategyModule:
    module_id: str
    name: str
    inspiration: str
    purpose: str
    mapped_setups: tuple[str, ...]
    entry_rules: tuple[str, ...]
    no_trade_rules: tuple[str, ...]
    failure_modes: tuple[str, ...]
    gate_notes: tuple[str, ...]


STRATEGY_MODULES: tuple[StrategyModule, ...] = (
    StrategyModule(
        module_id="oneil_canslim_growth_breakout",
        name="O'Neil-Inspired CAN SLIM Growth Breakout",
        inspiration="William O'Neil / CAN SLIM interpreted through Agent Adda EOD evidence.",
        purpose="Find growth and relative-strength breakouts with volume, market, and quality confirmation.",
        mapped_setups=(
            "relative_strength_breakout",
            "breakout_20_volume",
            "breakout_50_volume",
            "combo_rs_volume_sector",
            "combo_momentum_quality",
            "combo_risk_filtered_breakout",
        ),
        entry_rules=(
            "Prefer Stage 2 or strong relative-strength breakouts.",
            "Require volume, liquidity, and market breadth support.",
            "Use cost-adjusted expectancy as the final evidence gate.",
        ),
        no_trade_rules=(
            "Avoid weak breadth or negative net expectancy.",
            "Avoid low-liquidity spikes where cost drag overwhelms edge.",
        ),
        failure_modes=(
            "Breakout failure after broad-market reversal.",
            "High-volume exhaustion mistaken for accumulation.",
        ),
        gate_notes=("Promote only when net edge, profit factor, and evidence quality agree.",),
    ),
    StrategyModule(
        module_id="weinstein_stage2_leader",
        name="Weinstein Stage 2 Leader",
        inspiration="Stan Weinstein Stage 2 trend leadership interpreted through Agent Adda trend evidence.",
        purpose="Identify Stage 2 leaders with sector confirmation and constructive breakouts or pullback reclaims.",
        mapped_setups=(
            "stage2_supertrend_volume",
            "combo_stage2_supertrend_breakout",
            "ema20_pullback_reclaim",
            "combo_ema_reclaim_regime",
            "relative_strength_breakout",
            "combo_rs_volume_sector",
        ),
        entry_rules=(
            "Prefer Stage 2 trend state with relative-strength leadership.",
            "Accept breakout or EMA reclaim only when sector and breadth are constructive.",
        ),
        no_trade_rules=(
            "Avoid Stage 3/4 deterioration.",
            "Avoid reclaim attempts without enough volume or market support.",
        ),
        failure_modes=(
            "Late-stage trend exhaustion.",
            "Sector rotation reversal after apparent leadership.",
        ),
        gate_notes=("Stage evidence needs positive net setup history before promotion.",),
    ),
    StrategyModule(
        module_id="minervini_sepa_vcp",
        name="Minervini-Style SEPA / VCP",
        inspiration="Mark Minervini SEPA and volatility-contraction concepts as a practical proxy.",
        purpose="Find high relative-strength names emerging from tighter ranges with breakout confirmation.",
        mapped_setups=(
            "vcp_breakout_proxy",
            "combo_vcp_volume_sector",
            "relative_strength_breakout",
            "combo_momentum_quality",
        ),
        entry_rules=(
            "Prefer tight-range breakout or VCP proxy with RS leadership.",
            "Require liquidity, ADR, and sector participation.",
        ),
        no_trade_rules=(
            "Avoid loose, wide bases.",
            "Avoid proxy VCP rows without volume or trend confirmation.",
        ),
        failure_modes=(
            "Contraction proxy misses true base quality.",
            "Breakout extends too far before entry.",
        ),
        gate_notes=("Breakout-sensitive rows may wait for retest if retest evidence is better.",),
    ),
    StrategyModule(
        module_id="darvas_box_breakout",
        name="Darvas Box Breakout",
        inspiration="Nicolas Darvas box breakout interpreted with Agent Adda range and volume evidence.",
        purpose="Capture compact range breakouts with enough reward versus box or ATR risk.",
        mapped_setups=(
            "darvas_box_breakout",
            "breakout_20_volume",
            "breakout_50_volume",
        ),
        entry_rules=(
            "Prefer compact boxes that break with volume confirmation.",
            "Respect ATR/recent-low stop distance and cost-adjusted edge.",
        ),
        no_trade_rules=(
            "Avoid wide boxes with poor reward/risk.",
            "Avoid illiquid breakouts and high impact cost profiles.",
        ),
        failure_modes=(
            "False breakouts above obvious range highs.",
            "Gap entries that remove reward/risk.",
        ),
        gate_notes=("Wait for retest when breakout-retest evidence materially exceeds close breakout evidence.",),
    ),
    StrategyModule(
        module_id="graham_quality_value_confirmation",
        name="Graham Quality Value With Technical Confirmation",
        inspiration="Benjamin Graham quality and margin-of-safety ideas with technical confirmation.",
        purpose="Surface financially cleaner names only after technical confirmation appears.",
        mapped_setups=(
            "ema20_pullback_reclaim",
            "combo_ema_reclaim_regime",
            "combo_momentum_quality",
            "combo_risk_filtered_breakout",
        ),
        entry_rules=(
            "Require technical confirmation before value-oriented interest becomes actionable.",
            "Prefer clean forensic and balance-sheet evidence when available.",
        ),
        no_trade_rules=(
            "Avoid technical weakness even when valuation appears attractive.",
            "Avoid missing or adverse quality evidence.",
        ),
        failure_modes=(
            "Value trap with deteriorating trend.",
            "Delayed rerating despite clean financials.",
        ),
        gate_notes=("Conservative module downgrades to watch when evidence quality is thin.",),
    ),
    StrategyModule(
        module_id="fisher_quality_growth",
        name="Fisher Quality Growth",
        inspiration="Philip Fisher quality-growth ideas interpreted through Agent Adda fundamentals and trend evidence.",
        purpose="Find quality-growth names with durable financial strength and constructive technical structure.",
        mapped_setups=(
            "combo_momentum_quality",
            "combo_rs_volume_sector",
            "relative_strength_breakout",
            "ema20_pullback_reclaim",
        ),
        entry_rules=(
            "Prefer quality-growth names with momentum and RS confirmation.",
            "Require controlled cost and survivable risk.",
        ),
        no_trade_rules=(
            "Avoid quality stories without trend confirmation.",
            "Avoid crowded spikes with poor net expectancy.",
        ),
        failure_modes=(
            "Growth deceleration after high expectations.",
            "Quality premium compresses in risk-off markets.",
        ),
        gate_notes=("Quality-growth signals still require positive historical net edge.",),
    ),
    StrategyModule(
        module_id="wyckoff_accumulation_breakout_proxy",
        name="Wyckoff Accumulation / Breakout Proxy",
        inspiration="Wyckoff accumulation-to-markup concepts approximated using available EOD structure.",
        purpose="Convert base, range, volume, and relative-strength evidence into an accumulation breakout proxy.",
        mapped_setups=(
            "vcp_breakout_proxy",
            "darvas_box_breakout",
            "relative_strength_breakout",
            "combo_vcp_volume_sector",
        ),
        entry_rules=(
            "Prefer base breakout with improving RS and volume confirmation.",
            "Treat early accumulation reads as watch or retest candidates.",
        ),
        no_trade_rules=(
            "Avoid distribution-like breakdowns and failed springs.",
            "Avoid weak volume on breakout attempts.",
        ),
        failure_modes=(
            "Base proxy misclassifies distribution as accumulation.",
            "Breakout fails before markup phase begins.",
        ),
        gate_notes=("This proxy is conservative without a full Wyckoff phase detector.",),
    ),
    StrategyModule(
        module_id="agent_adda_composite_edge",
        name="Agent Adda Composite Edge",
        inspiration="Agent Adda evidence stack: technical, regime, cost, sector, and F&O context.",
        purpose="Promote the strongest net evidence stacks into a practical decision-engine view.",
        mapped_setups=(
            "combo_rs_volume_sector",
            "combo_momentum_quality",
            "ema20_pullback_reclaim",
            "relative_strength_breakout",
            "combo_risk_filtered_breakout",
            "combo_vcp_volume_sector",
        ),
        entry_rules=(
            "Prefer candidates with positive net expectancy and supportive market context.",
            "Use no-trade filters before ranking.",
        ),
        no_trade_rules=(
            "Avoid negative net expectancy.",
            "Avoid weak breadth, poor liquidity, and unsupported F&O context.",
        ),
        failure_modes=(
            "Composite score hides a weak underlying component.",
            "Historical edge decays in a new regime.",
        ),
        gate_notes=("Requires fewer but cleaner candidates with explicit risk filters.",),
    ),
)


GATE_PRIORITY = {
    "TRADE_CANDIDATE": 0,
    "HALF_SIZE_CANDIDATE": 1,
    "WAIT_RETEST": 2,
    "WATCH": 3,
    "BLOCK": 4,
}


def validate_strategy_modules() -> None:
    ids = [module.module_id for module in STRATEGY_MODULES]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate strategy module IDs")
    for module in STRATEGY_MODULES:
        for field_name in (
            "module_id",
            "name",
            "inspiration",
            "purpose",
            "mapped_setups",
            "entry_rules",
            "no_trade_rules",
            "failure_modes",
            "gate_notes",
        ):
            if not getattr(module, field_name):
                raise ValueError(f"Strategy module {module.module_id or '<missing>'} has empty {field_name}")


def setup_to_modules(setup: str) -> list[StrategyModule]:
    normalized = str(setup or "").strip()
    if not normalized:
        return []
    return [module for module in STRATEGY_MODULES if normalized in module.mapped_setups]


def module_ids_for_setup(setup: str) -> list[str]:
    return [module.module_id for module in setup_to_modules(setup)]


def attach_modules_to_events(events: pd.DataFrame) -> pd.DataFrame:
    out = events.copy()
    if out.empty:
        if "module_ids" not in out.columns:
            out["module_ids"] = pd.Series(dtype="object")
        if "module_count" not in out.columns:
            out["module_count"] = pd.Series(dtype="int64")
        return out
    out["module_ids"] = out.get("setup", "").map(lambda setup: ", ".join(module_ids_for_setup(str(setup))))
    out["module_count"] = out["module_ids"].map(lambda value: 0 if not value else len(str(value).split(", ")))
    return out


def classify_module_gate(row: Mapping[str, Any]) -> tuple[str, str]:
    trades = _num(row.get("trades"))
    quality = str(row.get("sample_quality", "") or "").lower()
    net_expectancy = _num(row.get("net_expectancy_r"))
    net_profit_factor = _num(row.get("net_profit_factor"))
    retest_edge = _num(row.get("retest_net_expectancy_r"))
    best_entry_variant = str(row.get("best_entry_variant", "") or "")

    if trades < 3 or quality not in {"higher", "medium"}:
        return "WATCH", "Evidence quality is still provisional."
    if math.isfinite(net_expectancy) and net_expectancy < -0.05:
        return "BLOCK", "Net expectancy is materially negative."
    if (
        best_entry_variant == "breakout_retest_hold"
        and math.isfinite(retest_edge)
        and math.isfinite(net_expectancy)
        and retest_edge > net_expectancy + 0.05
    ):
        return "WAIT_RETEST", "Retest evidence is materially better than immediate breakout evidence."
    if (
        math.isfinite(net_expectancy)
        and net_expectancy > 0
        and math.isfinite(net_profit_factor)
        and net_profit_factor > 1.0
    ):
        return "TRADE_CANDIDATE", "Positive net expectancy and positive net profit factor."
    if math.isfinite(net_expectancy) and -0.05 <= net_expectancy <= 0:
        return "HALF_SIZE_CANDIDATE", "Net expectancy is marginal; treat as reduced-size evidence."
    return "WATCH", "Evidence is incomplete or mixed."


def aggregate_module_summary(setup_summary: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "module_id",
        "module_name",
        "source_setups",
        "mapped_setup_count",
        "trades",
        "win_rate_pct",
        "expectancy_r",
        "net_expectancy_r",
        "net_profit_factor",
        "avg_cost_r",
        "sample_quality",
        "module_gate",
        "gate_reason",
    ]
    if setup_summary.empty:
        return pd.DataFrame(columns=columns)

    expanded: list[dict[str, Any]] = []
    for _, row in setup_summary.iterrows():
        setup = str(row.get("setup", "") or "").strip()
        for module in setup_to_modules(setup):
            item = row.to_dict()
            item["module_id"] = module.module_id
            item["module_name"] = module.name
            item["source_setup"] = setup
            expanded.append(item)
    if not expanded:
        return pd.DataFrame(columns=columns)

    expanded_frame = pd.DataFrame(expanded)
    rows: list[dict[str, Any]] = []
    for (module_id, module_name), group in expanded_frame.groupby(["module_id", "module_name"], dropna=False):
        trades = float(pd.to_numeric(group.get("trades", 0), errors="coerce").fillna(0).sum())
        row = {
            "module_id": module_id,
            "module_name": module_name,
            "source_setups": ", ".join(sorted(set(group["source_setup"].astype(str)))),
            "mapped_setup_count": int(group["source_setup"].nunique()),
            "trades": int(trades),
            "win_rate_pct": _weighted_average(group, "win_rate_pct"),
            "expectancy_r": _weighted_average(group, "expectancy_r"),
            "net_expectancy_r": _weighted_average(group, "net_expectancy_r"),
            "net_profit_factor": _weighted_average(group, "net_profit_factor"),
            "avg_cost_r": _weighted_average(group, "avg_cost_r"),
            "sample_quality": _best_sample_quality(group.get("sample_quality", pd.Series(dtype="object"))),
        }
        row["module_gate"], row["gate_reason"] = classify_module_gate(row)
        rows.append(row)

    out = pd.DataFrame(rows, columns=columns)
    out["_gate_priority"] = out["module_gate"].map(GATE_PRIORITY).fillna(99)
    out = out.sort_values(
        ["_gate_priority", "net_expectancy_r", "win_rate_pct", "trades"],
        ascending=[True, False, False, False],
    ).drop(columns=["_gate_priority"])
    return out.reset_index(drop=True)


def build_module_candidates(current_decision_queue: pd.DataFrame, setup_summary: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "module_id",
        "module_name",
        "symbol",
        "sector",
        "setup",
        "action",
        "decision_score",
        "close",
        "cost_profile",
        "estimated_cost_r",
        "market_regime",
        "breadth_positive_pct",
        "fno_pcr",
        "fno_buildup",
        "setup_expectancy_r",
        "setup_net_expectancy_r",
        "setup_win_rate_pct",
        "module_gate",
        "gate_reason",
        "decision_reasons",
    ]
    if current_decision_queue.empty:
        return pd.DataFrame(columns=columns)

    metric_cols = [
        column
        for column in ["setup", "expectancy_r", "net_expectancy_r", "win_rate_pct", "net_profit_factor", "sample_quality"]
        if column in setup_summary.columns
    ]
    metrics = setup_summary.loc[:, metric_cols].copy() if metric_cols else pd.DataFrame(columns=["setup"])
    if not metrics.empty:
        metrics = metrics.rename(
            columns={
                "expectancy_r": "setup_expectancy_r",
                "net_expectancy_r": "setup_net_expectancy_r",
                "win_rate_pct": "setup_win_rate_pct",
            }
        )

    source = current_decision_queue.copy()
    if not metrics.empty and "setup" in source.columns:
        source = source.merge(metrics, on="setup", how="left", suffixes=("", "_summary"))

    rows: list[dict[str, Any]] = []
    for _, candidate in source.iterrows():
        setup = str(candidate.get("setup", "") or "")
        for module in setup_to_modules(setup):
            row = {column: candidate.get(column, "") for column in columns}
            row["module_id"] = module.module_id
            row["module_name"] = module.name
            gate_input = {
                "trades": candidate.get("setup_trades", candidate.get("trades", 0)),
                "sample_quality": candidate.get("sample_quality", candidate.get("setup_sample_quality", "")),
                "net_expectancy_r": candidate.get("setup_net_expectancy_r", candidate.get("net_expectancy_r")),
                "net_profit_factor": candidate.get("net_profit_factor"),
            }
            row["module_gate"], row["gate_reason"] = classify_module_gate(gate_input)
            rows.append(row)

    if not rows:
        return pd.DataFrame(columns=columns)
    out = pd.DataFrame(rows, columns=columns)
    out["_gate_priority"] = out["module_gate"].map(GATE_PRIORITY).fillna(99)
    sort_cols = [column for column in ["_gate_priority", "decision_score", "setup_net_expectancy_r"] if column in out.columns]
    ascending = [True] + [False] * (len(sort_cols) - 1)
    return out.sort_values(sort_cols, ascending=ascending).drop(columns=["_gate_priority"]).reset_index(drop=True)


def _weighted_average(frame: pd.DataFrame, column: str) -> float:
    if column not in frame.columns:
        return float("nan")
    values = pd.to_numeric(frame[column], errors="coerce")
    weights = pd.to_numeric(frame.get("trades", 1), errors="coerce").fillna(0)
    valid = values.notna() & weights.gt(0)
    if not valid.any():
        return float("nan")
    return round(float((values[valid] * weights[valid]).sum() / weights[valid].sum()), 6)


def _best_sample_quality(values: pd.Series) -> str:
    priority = {"higher": 0, "medium": 1, "low": 2, "provisional": 3, "": 4}
    best = ""
    best_rank = 99
    for value in values.fillna("").astype(str).str.lower():
        rank = priority.get(value, 50)
        if rank < best_rank:
            best = value
            best_rank = rank
    return best


def _num(value: Any) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else float("nan")
    except Exception:
        return float("nan")
