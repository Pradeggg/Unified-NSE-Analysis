"""Strategy registry for the EOD Strategy Lab."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StrategyDefinition:
    id: str
    name: str
    family: str
    description: str
    timeframe: str = "EOD"
    status: str = "ready"
    required_fields: tuple[str, ...] = ("date", "symbol", "close", "volume")
    optional_fields: tuple[str, ...] = ()
    entry_labels: tuple[str, ...] = field(default_factory=tuple)
    exit_labels: tuple[str, ...] = field(default_factory=tuple)


_COMMON_TECH_FIELDS = ("date", "symbol", "open", "high", "low", "close", "volume")


_STRATEGIES: tuple[StrategyDefinition, ...] = (
    StrategyDefinition(
        id="stage2",
        name="Stage 2 Uptrend Breakout",
        family="trend",
        description="Stage 2 trend, relative strength, moving-average alignment, and breakout behavior.",
        required_fields=_COMMON_TECH_FIELDS + ("stage", "relative_strength"),
        optional_fields=("supertrend_state", "fundamental_score"),
        entry_labels=("entered_stage2", "rs_above_threshold", "breakout_confirmed"),
        exit_labels=("stage2_exit", "supertrend_sell", "trailing_stop"),
    ),
    StrategyDefinition(
        id="canslim",
        name="CANSLIM Momentum + Quality",
        family="growth",
        description="Growth and quality filter combined with Stage 2 momentum.",
        required_fields=_COMMON_TECH_FIELDS + ("stage", "relative_strength", "can_slim_score"),
        optional_fields=("earnings_quality", "sales_growth", "institutional_backing"),
        entry_labels=("stage2", "canslim_quality", "rs_leader"),
        exit_labels=("technical_failure", "fundamental_deterioration", "stop_loss"),
    ),
    StrategyDefinition(
        id="minervini",
        name="Minervini Trend Template",
        family="trend",
        description="SMA alignment, price near 52-week high, and strong relative strength.",
        required_fields=_COMMON_TECH_FIELDS + ("sma_50", "sma_150", "sma_200", "relative_strength"),
        entry_labels=("price_above_sma", "ma_alignment", "near_52w_high"),
        exit_labels=("sma50_break", "atr_trailing"),
    ),
    StrategyDefinition(
        id="supertrend_continuation",
        name="Supertrend Continuation",
        family="supertrend",
        description="Bullish Supertrend continuation with trend and volume confirmation.",
        required_fields=_COMMON_TECH_FIELDS + ("supertrend_state", "supertrend_value", "atr_14"),
        entry_labels=("supertrend_buy", "trend_continuation"),
        exit_labels=("supertrend_sell", "volatility_stop"),
    ),
    StrategyDefinition(
        id="rsi_pullback_stage2",
        name="RSI Pullback Inside Stage 2",
        family="pullback",
        description="Healthy RSI reset inside an existing Stage 2 uptrend.",
        required_fields=_COMMON_TECH_FIELDS + ("stage", "rsi_14", "relative_strength"),
        entry_labels=("stage2", "rsi_recovery", "rs_leader"),
        exit_labels=("failed_recovery", "trend_break"),
    ),
    StrategyDefinition(
        id="52w_high",
        name="52-Week High Breakout",
        family="momentum",
        description="Breakout or close near 52-week high with volume and relative strength confirmation.",
        required_fields=_COMMON_TECH_FIELDS + ("high_52w", "relative_strength"),
        entry_labels=("near_52w_high", "volume_expansion"),
        exit_labels=("failed_breakout", "atr_trailing"),
    ),
    StrategyDefinition(
        id="vcp",
        name="Volatility Contraction Pattern",
        family="compression",
        description="Range and volume contraction followed by pivot breakout.",
        required_fields=_COMMON_TECH_FIELDS,
        entry_labels=("range_contracting", "volume_contracting", "pivot_breakout"),
        exit_labels=("pivot_failure", "atr_trailing"),
    ),
    StrategyDefinition(
        id="darvas",
        name="Darvas Box Breakout",
        family="compression",
        description="Box consolidation followed by breakout above box high.",
        required_fields=_COMMON_TECH_FIELDS,
        entry_labels=("box_defined", "box_breakout"),
        exit_labels=("box_low_break", "atr_trailing"),
    ),
    StrategyDefinition(
        id="bollinger_squeeze",
        name="Bollinger Squeeze Breakout",
        family="compression",
        description="Low Bollinger bandwidth followed by directional breakout.",
        required_fields=_COMMON_TECH_FIELDS,
        entry_labels=("bandwidth_compressed", "squeeze_breakout"),
        exit_labels=("range_reclaim_failure", "atr_trailing"),
    ),
    StrategyDefinition(
        id="head_shoulders",
        name="Head-and-Shoulders Breakdown",
        family="chart-pattern",
        description="Bearish shoulder/head/right-shoulder structure with neckline breakdown.",
        status="experimental",
        required_fields=_COMMON_TECH_FIELDS,
        entry_labels=("left_shoulder", "head", "right_shoulder", "neckline_break"),
        exit_labels=("neckline_reclaim", "measured_move"),
    ),
    StrategyDefinition(
        id="inverse_head_shoulders",
        name="Inverse Head-and-Shoulders Breakout",
        family="chart-pattern",
        description="Bullish inverse shoulder/head/right-shoulder structure with neckline breakout.",
        status="experimental",
        required_fields=_COMMON_TECH_FIELDS,
        entry_labels=("inverse_structure", "neckline_breakout"),
        exit_labels=("neckline_failure", "measured_move"),
    ),
    StrategyDefinition(
        id="cup_handle",
        name="Cup-and-Handle Breakout",
        family="chart-pattern",
        description="Rounded base, handle pullback, and breakout above handle pivot.",
        status="experimental",
        required_fields=_COMMON_TECH_FIELDS,
        entry_labels=("rounded_base", "handle", "handle_pivot_breakout"),
        exit_labels=("handle_failure", "atr_trailing"),
    ),
)


def list_strategies() -> list[StrategyDefinition]:
    return sorted(_STRATEGIES, key=lambda item: (item.family, item.id))


def get_strategy(strategy_id: str) -> StrategyDefinition:
    normalized = strategy_id.strip().lower().replace("-", "_")
    for strategy in _STRATEGIES:
        if strategy.id == normalized:
            return strategy
    available = ", ".join(strategy.id for strategy in list_strategies())
    raise ValueError(f"Unknown strategy '{strategy_id}'. Available strategies: {available}")
