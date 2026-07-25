import pandas as pd

from scripts.research_signal_effectiveness import (
    add_execution_costs,
    build_regime_conditional_edge_map,
    build_cost_adjusted_edge_map,
    _decision_score_row,
    markdown_to_html,
    render_regime_edge_markdown,
    summarize,
)


def _event(
    setup: str,
    regime: str,
    r_multiple: float,
    *,
    pcr: float | None = None,
    buildup: str = "UNKNOWN",
    breadth: float = 58.0,
    vix_change: float = 1.0,
    adr: float = 3.0,
) -> dict:
    return {
        "setup": setup,
        "market_regime": regime,
        "target_hit": int(r_multiple >= 1.8),
        "r_multiple": r_multiple,
        "breadth_positive_pct": breadth,
        "vix_change_pct": vix_change,
        "adr_pct_20": adr,
        "fno_available": 1 if pcr is not None else 0,
        "fno_pcr": pcr,
        "fno_buildup": buildup,
    }


def test_regime_edge_map_prefers_best_conditional_context_and_blocks_fno_stack():
    events = pd.DataFrame(
        [
            _event("combo_momentum_quality", "risk_off", 0.60, breadth=62, vix_change=6.0, adr=4.5),
            _event("combo_momentum_quality", "risk_off", 0.40, breadth=60, vix_change=5.2, adr=4.2),
            _event("combo_momentum_quality", "risk_off", -0.10, breadth=57, vix_change=4.8, adr=4.1),
            _event("combo_momentum_quality", "confirmation", -0.45, breadth=52, vix_change=0.5, adr=2.5),
            _event("combo_momentum_quality", "confirmation", -0.25, breadth=50, vix_change=0.7, adr=2.6),
            _event("combo_fno_confirmed_breakout", "risk_off", -0.40, pcr=0.70, buildup="LONG_BUILDUP"),
            _event("combo_fno_confirmed_breakout", "risk_off", -0.20, pcr=0.76, buildup="LONG_BUILDUP"),
            _event("combo_fno_confirmed_breakout", "confirmation", -0.60, pcr=0.95, buildup="LONG_BUILDUP"),
            _event("combo_fno_confirmed_breakout", "confirmation", -0.30, pcr=0.92, buildup="SHORT_COVERING"),
        ]
    )

    maps = build_regime_conditional_edge_map(events, min_trades=2)

    market = maps["market_regime"]
    risk_off_row = market[
        (market["setup"] == "combo_momentum_quality")
        & (market["market_regime"] == "risk_off")
    ].iloc[0]
    confirmation_row = market[
        (market["setup"] == "combo_momentum_quality")
        & (market["market_regime"] == "confirmation")
    ].iloc[0]
    assert risk_off_row["expectancy_r"] > confirmation_row["expectancy_r"]

    fno = maps["fno_postmortem"]
    assert "call_heavy" in set(fno["pcr_bucket"])

    gates = maps["live_gate"]
    fno_gate = gates[gates["setup"] == "combo_fno_confirmed_breakout"].iloc[0]
    assert fno_gate["gate_action"] == "block_rebuild"

    momentum_gate = gates[gates["setup"] == "combo_momentum_quality"].iloc[0]
    assert momentum_gate["best_market_regime"] == "risk_off"
    assert momentum_gate["gate_action"] in {"promote_best_regime", "half_size_best_regime"}


def test_execution_costs_convert_price_cost_to_r_and_net_outcome():
    events = pd.DataFrame(
        [
            {
                "setup": "ema20_pullback_reclaim",
                "entry": 100.0,
                "stop": 95.0,
                "close": 100.0,
                "turnover_cr_20d": 250.0,
                "volume_ratio_20d": 2.0,
                "r_multiple": 0.152,
            },
            {
                "setup": "ema20_pullback_reclaim",
                "entry": 100.0,
                "stop": 95.0,
                "close": 40.0,
                "turnover_cr_20d": 8.0,
                "volume_ratio_20d": 8.0,
                "r_multiple": 0.152,
            },
        ]
    )

    adjusted = add_execution_costs(events)

    liquid = adjusted.iloc[0]
    assert liquid["cost_profile"] == "liquid"
    assert liquid["risk_pct"] == 5.0
    assert liquid["estimated_cost_pct"] == 0.38
    assert round(float(liquid["estimated_cost_r"]), 3) == 0.076
    assert round(float(liquid["net_r_multiple"]), 3) == 0.076

    spike = adjusted.iloc[1]
    assert spike["cost_profile"] == "illiquid_spike"
    assert spike["estimated_cost_pct"] == 1.1
    assert round(float(spike["estimated_cost_r"]), 3) == 0.22
    assert round(float(spike["net_r_multiple"]), 3) == -0.068


def test_execution_costs_are_idempotent_for_report_reuse():
    events = pd.DataFrame(
        [
            {
                "setup": "ema20_pullback_reclaim",
                "entry": 100.0,
                "stop": 95.0,
                "close": 100.0,
                "turnover_cr_20d": 250.0,
                "volume_ratio_20d": 2.0,
                "r_multiple": 0.152,
                "target_hit": 0,
            }
        ]
    )

    once = add_execution_costs(events)
    twice = add_execution_costs(once)
    maps = build_cost_adjusted_edge_map(once, min_trades=1)

    assert not twice.columns.duplicated().any()
    assert round(float(twice.loc[0, "net_r_multiple"]), 3) == 0.076
    assert maps["setup_net"].loc[0, "net_expectancy_r"] == 0.076


def test_cost_adjusted_edge_map_splits_volume_spike_decay():
    events = pd.DataFrame(
        [
            {
                "setup": "relative_strength_breakout",
                "entry": 100.0,
                "stop": 95.0,
                "close": 100.0,
                "turnover_cr_20d": 250.0,
                "volume_ratio_20d": 2.0,
                "r_multiple": 0.20,
                "target_hit": 0,
            },
            {
                "setup": "relative_strength_breakout",
                "entry": 100.0,
                "stop": 95.0,
                "close": 100.0,
                "turnover_cr_20d": 250.0,
                "volume_ratio_20d": 2.2,
                "r_multiple": 0.10,
                "target_hit": 0,
            },
            {
                "setup": "relative_strength_breakout",
                "entry": 100.0,
                "stop": 95.0,
                "close": 50.0,
                "turnover_cr_20d": 12.0,
                "volume_ratio_20d": 8.0,
                "r_multiple": 0.20,
                "target_hit": 0,
            },
            {
                "setup": "relative_strength_breakout",
                "entry": 100.0,
                "stop": 95.0,
                "close": 50.0,
                "turnover_cr_20d": 12.0,
                "volume_ratio_20d": 9.5,
                "r_multiple": -0.10,
                "target_hit": 0,
            },
        ]
    )

    maps = build_cost_adjusted_edge_map(events, min_trades=2)

    setup = maps["setup_net"].iloc[0]
    assert "net_expectancy_r" in setup
    assert setup["net_expectancy_r"] < setup["expectancy_r"]

    volume = maps["volume_spike"]
    controlled = volume[volume["volume_spike_bucket"] == "confirmed_volume"].iloc[0]
    high_spike = volume[volume["volume_spike_bucket"] == "high_impact_spike"].iloc[0]
    assert controlled["net_expectancy_r"] > high_spike["net_expectancy_r"]


def test_decision_score_penalizes_high_cost_volume_spike():
    base = pd.Series(
        {
            "setup_expectancy_r": 0.15,
            "setup_net_expectancy_r": 0.08,
            "setup_trades": 200,
            "matches_stock_best_setup": 1,
            "volume_ratio_20d": 2.0,
            "relative_strength": 75,
            "breadth_positive_pct": 58,
            "sector_rank_1d": 70,
            "market_regime": "confirmation",
            "vix_change_pct": 0.5,
            "fno_bias_score": 0,
            "estimated_cost_r": 0.07,
            "cost_profile": "liquid",
        }
    )
    spike = base.copy()
    spike["setup_net_expectancy_r"] = -0.03
    spike["volume_ratio_20d"] = 8.0
    spike["estimated_cost_r"] = 0.22
    spike["cost_profile"] = "illiquid_spike"

    assert _decision_score_row(base) - _decision_score_row(spike) >= 20


def test_summarize_merges_model_probabilities_with_net_metrics():
    events = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "setup": "ema20_pullback_reclaim",
                "setup_type": "standalone",
                "date": "2026-06-01",
                "target_hit": 1,
                "r_multiple": 0.30,
                "net_r_multiple": 0.20,
                "estimated_cost_r": 0.10,
                "estimated_cost_pct": 0.50,
                "mfe_r": 0.60,
                "mae_r": -0.20,
                "bars_held": 4,
                "volume_ratio_20d": 2.0,
                "adr_pct_20": 3.0,
                "model_target_prob": 0.65,
                "relative_strength": 70,
            },
            {
                "symbol": "AAA",
                "setup": "ema20_pullback_reclaim",
                "setup_type": "standalone",
                "date": "2026-06-02",
                "target_hit": 0,
                "r_multiple": -0.10,
                "net_r_multiple": -0.20,
                "estimated_cost_r": 0.10,
                "estimated_cost_pct": 0.50,
                "mfe_r": 0.20,
                "mae_r": -0.40,
                "bars_held": 5,
                "volume_ratio_20d": 2.4,
                "adr_pct_20": 3.2,
                "model_target_prob": 0.35,
                "relative_strength": 72,
            },
        ]
    )

    setup_summary, _, _, best_by_stock, _ = summarize(events, min_trades=1)

    assert setup_summary.loc[0, "net_expectancy_r"] == 0.0
    assert setup_summary.loc[0, "avg_model_target_prob"] == 0.5
    assert best_by_stock.loc[0, "avg_model_target_prob"] == 0.5


def test_regime_edge_markdown_renders_research_sections():
    events = pd.DataFrame(
        [
            _event("relative_strength_breakout", "risk_off", 0.35, breadth=61, vix_change=5.5),
            _event("relative_strength_breakout", "risk_off", 0.15, breadth=59, vix_change=4.5),
            _event("relative_strength_breakout", "confirmation", -0.20, breadth=51, vix_change=1.0),
            _event("relative_strength_breakout", "confirmation", -0.10, breadth=50, vix_change=1.2),
        ]
    )
    maps = build_regime_conditional_edge_map(events, min_trades=2)

    markdown = render_regime_edge_markdown(maps)

    assert "## Regime-Conditional Edge Map" in markdown
    assert "### Market Regime / Setup Cross-Walk" in markdown
    assert "### Live Gate Recommendations" in markdown
    assert "relative_strength_breakout" in markdown


def test_regime_map_renders_calendar_and_theme_stress_test():
    events = pd.DataFrame(
        [
            {
                "date": "2023-07-03",
                "sector": "RAILWAYS & PSU INFRA",
                "setup": "relative_strength_breakout",
                "target_hit": 1,
                "r_multiple": 0.40,
                "net_r_multiple": 0.30,
                "estimated_cost_r": 0.10,
                "estimated_cost_pct": 0.60,
                "market_regime": "risk_off",
                "breadth_positive_pct": 62,
                "vix_change_pct": 1.0,
                "adr_pct_20": 4.0,
            },
            {
                "date": "2023-09-04",
                "sector": "RAILWAYS & PSU INFRA",
                "setup": "relative_strength_breakout",
                "target_hit": 0,
                "r_multiple": 0.20,
                "net_r_multiple": 0.10,
                "estimated_cost_r": 0.10,
                "estimated_cost_pct": 0.60,
                "market_regime": "risk_off",
                "breadth_positive_pct": 61,
                "vix_change_pct": 1.0,
                "adr_pct_20": 4.2,
            },
            {
                "date": "2023-10-05",
                "sector": "RAILWAYS & PSU INFRA",
                "setup": "relative_strength_breakout",
                "target_hit": 1,
                "r_multiple": 0.30,
                "net_r_multiple": 0.20,
                "estimated_cost_r": 0.10,
                "estimated_cost_pct": 0.60,
                "market_regime": "risk_off",
                "breadth_positive_pct": 63,
                "vix_change_pct": 1.0,
                "adr_pct_20": 4.2,
            },
            {
                "date": "2024-08-05",
                "sector": "RAILWAYS & PSU INFRA",
                "setup": "relative_strength_breakout",
                "target_hit": 0,
                "r_multiple": -0.20,
                "net_r_multiple": -0.30,
                "estimated_cost_r": 0.10,
                "estimated_cost_pct": 0.60,
                "market_regime": "confirmation",
                "breadth_positive_pct": 43,
                "vix_change_pct": 3.0,
                "adr_pct_20": 4.1,
            },
        ]
    )

    maps = build_regime_conditional_edge_map(events, min_trades=2)
    markdown = render_regime_edge_markdown(maps)

    assert "calendar_year" in maps
    assert "theme_rs_year_breadth" in maps
    assert "2023" in set(maps["calendar_year"]["calendar_year"].astype(str))
    assert maps["theme_rs_year_breadth"].iloc[0]["sector"] == "RAILWAYS & PSU INFRA"
    assert "### Calendar-Year / Setup Cross-Walk" in markdown
    assert "### Railways/PSU RS Breakout Year/Breadth Stress Test" in markdown


def test_markdown_to_html_renders_third_level_headings_after_tables():
    markdown = "\n".join(
        [
            "## Regime-Conditional Edge Map",
            "",
            "| setup | expectancy_r |",
            "| --- | --- |",
            "| relative_strength_breakout | 0.32 |",
            "",
            "### Live Gate Recommendations",
        ]
    )

    html = markdown_to_html(markdown)

    assert "<h3>Live Gate Recommendations</h3>" in html
    assert "<p>### Live Gate Recommendations</p>" not in html
