import pytest

from terminal.research_council.mode_profiles import PROFILES, load_mode_profile


def test_all_research_council_modes_are_declared():
    assert set(PROFILES) == {
        "market_council",
        "sector_opportunity",
        "stock_deep_dive",
        "strategy_build",
        "intraday_tactical",
        "report_review",
    }


@pytest.mark.parametrize(
    ("mode", "plan_cap", "revision_cap", "wall_clock_s", "tokens"),
    [
        ("market_council", 3, 2, 480, 200_000),
        ("sector_opportunity", 3, 2, 480, 220_000),
        ("stock_deep_dive", 3, 2, 480, 150_000),
        ("strategy_build", 5, 3, 720, 350_000),
        ("intraday_tactical", 1, 0, 90, 50_000),
        ("report_review", 0, 0, 180, 30_000),
    ],
)
def test_mode_profile_budget_and_loop_caps(mode, plan_cap, revision_cap, wall_clock_s, tokens):
    profile = load_mode_profile(mode)

    assert profile.mode == mode
    assert profile.plan_loop_cap == plan_cap
    assert profile.revision_cap == revision_cap
    assert profile.wall_clock_s == wall_clock_s
    assert profile.token_budget == tokens


def test_mode_profiles_declare_agents_critics_coder_and_report_shape():
    market = load_mode_profile("market_council")
    sector = load_mode_profile("sector_opportunity")
    strategy = load_mode_profile("strategy_build")
    intraday = load_mode_profile("intraday_tactical")
    report_review = load_mode_profile("report_review")

    assert market.specialists == (
        "macro_regime",
        "sector_rotation",
        "technical",
        "minervini",
        "fundamental",
        "fno_risk",
        "catalyst",
        "hedge_fund_owner",
    )
    assert market.critics == ("data_quality", "leakage", "overfit", "risk", "evidence")
    assert market.coder_enabled is True
    assert market.html_report == "full"

    assert sector.coder_enabled is True
    assert "sector_rotation" in sector.specialists
    assert "coder_quant" in sector.specialists
    assert sector.html_report == "sector_opportunity"

    assert strategy.coder_enabled is True
    assert "coder_quant" in strategy.specialists
    assert strategy.html_report == "full_backtest"

    assert intraday.coder_enabled is False
    assert intraday.required_freshness["intraday_max_age_minutes"] == 5

    assert report_review.coder_enabled is False
    assert report_review.critics == ("data_quality", "evidence")
    assert report_review.html_report == "review_summary"


def test_load_unknown_mode_raises_key_error():
    with pytest.raises(KeyError):
        load_mode_profile("unknown")
