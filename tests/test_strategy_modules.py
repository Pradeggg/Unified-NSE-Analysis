import pandas as pd

from terminal.strategy_modules import (
    STRATEGY_MODULES,
    aggregate_module_summary,
    classify_module_gate,
    module_ids_for_setup,
    validate_strategy_modules,
)


EXPECTED_MODULE_IDS = {
    "oneil_canslim_growth_breakout",
    "weinstein_stage2_leader",
    "minervini_sepa_vcp",
    "darvas_box_breakout",
    "graham_quality_value_confirmation",
    "fisher_quality_growth",
    "wyckoff_accumulation_breakout_proxy",
    "agent_adda_composite_edge",
}


def test_strategy_module_registry_has_unique_complete_modules():
    validate_strategy_modules()

    ids = [module.module_id for module in STRATEGY_MODULES]
    assert len(ids) == len(set(ids))
    assert set(ids) == EXPECTED_MODULE_IDS

    for module in STRATEGY_MODULES:
        assert module.module_id
        assert module.name
        assert module.inspiration
        assert module.purpose
        assert module.mapped_setups
        assert module.entry_rules
        assert module.no_trade_rules
        assert module.failure_modes


def test_setup_family_maps_to_expected_named_modules():
    assert set(module_ids_for_setup("darvas_box_breakout")) == {
        "darvas_box_breakout",
        "wyckoff_accumulation_breakout_proxy",
    }

    assert set(module_ids_for_setup("vcp_breakout_proxy")) == {
        "minervini_sepa_vcp",
        "wyckoff_accumulation_breakout_proxy",
    }

    assert set(module_ids_for_setup("combo_rs_volume_sector")) == {
        "oneil_canslim_growth_breakout",
        "weinstein_stage2_leader",
        "fisher_quality_growth",
        "agent_adda_composite_edge",
    }

    assert set(module_ids_for_setup("combo_momentum_quality")) == {
        "oneil_canslim_growth_breakout",
        "minervini_sepa_vcp",
        "graham_quality_value_confirmation",
        "fisher_quality_growth",
        "agent_adda_composite_edge",
    }

    assert module_ids_for_setup("unknown_setup") == []


def test_module_summary_aggregates_setup_metrics():
    setup_summary = pd.DataFrame(
        [
            {
                "setup": "darvas_box_breakout",
                "trades": 10,
                "win_rate_pct": 60.0,
                "expectancy_r": 0.20,
                "net_expectancy_r": 0.10,
                "net_profit_factor": 1.40,
                "avg_cost_r": 0.05,
                "sample_quality": "medium",
            },
            {
                "setup": "breakout_20_volume",
                "trades": 30,
                "win_rate_pct": 40.0,
                "expectancy_r": 0.10,
                "net_expectancy_r": -0.02,
                "net_profit_factor": 0.95,
                "avg_cost_r": 0.08,
                "sample_quality": "higher",
            },
        ]
    )

    summary = aggregate_module_summary(setup_summary)

    darvas = summary[summary["module_id"] == "darvas_box_breakout"].iloc[0]
    assert darvas["trades"] == 40
    assert darvas["source_setups"] == "breakout_20_volume, darvas_box_breakout"
    assert darvas["mapped_setup_count"] == 2
    assert round(float(darvas["win_rate_pct"]), 2) == 45.00
    assert round(float(darvas["net_expectancy_r"]), 3) == 0.010

    assert set(summary["module_id"]).issuperset({"darvas_box_breakout", "oneil_canslim_growth_breakout"})


def test_module_gate_classification_is_deterministic():
    assert classify_module_gate(
        {
            "trades": 80,
            "sample_quality": "medium",
            "net_expectancy_r": 0.08,
            "net_profit_factor": 1.20,
        }
    )[0] == "TRADE_CANDIDATE"

    assert classify_module_gate(
        {
            "trades": 80,
            "sample_quality": "higher",
            "net_expectancy_r": -0.02,
            "net_profit_factor": 1.05,
        }
    )[0] == "HALF_SIZE_CANDIDATE"

    assert classify_module_gate(
        {
            "trades": 80,
            "sample_quality": "medium",
            "net_expectancy_r": 0.04,
            "net_profit_factor": 1.10,
            "best_entry_variant": "breakout_retest_hold",
            "retest_net_expectancy_r": 0.12,
        }
    )[0] == "WAIT_RETEST"

    assert classify_module_gate(
        {
            "trades": 80,
            "sample_quality": "medium",
            "net_expectancy_r": -0.08,
            "net_profit_factor": 0.70,
        }
    )[0] == "BLOCK"

    assert classify_module_gate(
        {
            "trades": 2,
            "sample_quality": "low",
            "net_expectancy_r": 0.20,
            "net_profit_factor": 1.50,
        }
    )[0] == "WATCH"
