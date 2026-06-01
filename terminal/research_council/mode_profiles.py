"""Mode profile definitions for Research Council runs."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModeProfile:
    mode: str
    plan_loop_cap: int
    revision_cap: int
    wall_clock_s: int
    token_budget: int
    specialists: tuple[str, ...]
    critics: tuple[str, ...]
    coder_enabled: bool
    html_report: str
    required_freshness: dict[str, int | str | bool] = field(default_factory=dict)


ALL_SPECIALISTS = (
    "macro_regime",
    "sector_rotation",
    "technical",
    "minervini",
    "fundamental",
    "fno_risk",
    "catalyst",
    "hedge_fund_owner",
)

ALL_CRITICS = ("data_quality", "leakage", "overfit", "risk", "evidence")


PROFILES: dict[str, ModeProfile] = {
    "market_council": ModeProfile(
        mode="market_council",
        plan_loop_cap=3,
        revision_cap=2,
        wall_clock_s=480,
        token_budget=200_000,
        specialists=ALL_SPECIALISTS,
        critics=ALL_CRITICS,
        coder_enabled=True,
        html_report="full",
        required_freshness={"eod_max_lag_days": 1, "fno_max_lag_days": 1, "fundamentals_max_age_days": 21},
    ),
    "sector_opportunity": ModeProfile(
        mode="sector_opportunity",
        plan_loop_cap=3,
        revision_cap=2,
        wall_clock_s=480,
        token_budget=220_000,
        specialists=("macro_regime", "sector_rotation", "technical", "minervini", "fundamental", "catalyst", "coder_quant", "hedge_fund_owner"),
        critics=ALL_CRITICS,
        coder_enabled=True,
        html_report="sector_opportunity",
        required_freshness={"eod_max_lag_days": 1, "fundamentals_max_age_days": 21},
    ),
    "stock_deep_dive": ModeProfile(
        mode="stock_deep_dive",
        plan_loop_cap=3,
        revision_cap=2,
        wall_clock_s=480,
        token_budget=150_000,
        specialists=("macro_regime", "technical", "fundamental", "fno_risk", "catalyst", "hedge_fund_owner"),
        critics=ALL_CRITICS,
        coder_enabled=True,
        html_report="full",
        required_freshness={"eod_max_lag_days": 1, "fno_max_lag_days": 1, "fundamentals_max_age_days": 21},
    ),
    "strategy_build": ModeProfile(
        mode="strategy_build",
        plan_loop_cap=5,
        revision_cap=3,
        wall_clock_s=720,
        token_budget=350_000,
        specialists=("technical", "minervini", "fundamental", "fno_risk", "coder_quant", "hedge_fund_owner"),
        critics=ALL_CRITICS,
        coder_enabled=True,
        html_report="full_backtest",
        required_freshness={"eod_max_lag_days": 1, "fno_max_lag_days": 1, "fundamentals_max_age_days": 21},
    ),
    "intraday_tactical": ModeProfile(
        mode="intraday_tactical",
        plan_loop_cap=1,
        revision_cap=0,
        wall_clock_s=90,
        token_budget=50_000,
        specialists=("macro_regime", "technical", "fno_risk"),
        critics=("data_quality", "risk"),
        coder_enabled=False,
        html_report="minimal",
        required_freshness={"intraday_max_age_minutes": 5, "fno_max_lag_days": 1},
    ),
    "report_review": ModeProfile(
        mode="report_review",
        plan_loop_cap=0,
        revision_cap=0,
        wall_clock_s=180,
        token_budget=30_000,
        specialists=("data_quality",),
        critics=("data_quality", "evidence"),
        coder_enabled=False,
        html_report="review_summary",
        required_freshness={"report_max_age_days": 7},
    ),
}


def load_mode_profile(mode: str) -> ModeProfile:
    return PROFILES[mode]
