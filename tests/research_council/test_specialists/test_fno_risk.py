from terminal.research_council.agents.fno_risk import FnoRiskAgent


def test_missing_option_chain_returns_missing_evidence_not_strategy():
    finding = FnoRiskAgent().run(
        {
            "derivatives": {
                "futures": [
                    {
                        "symbol": "AAA",
                        "futures_buildup": "LONG_BUILDUP",
                        "oi_change_pct": 8,
                        "price_change_pct": 3,
                    }
                ]
            }
        }
    )

    assert finding.agent == "fno_risk"
    assert finding.stance == "needs_confirmation"
    assert finding.candidates == ["AAA"]
    assert finding.required_next_steps == ["Add option-chain evidence for AAA"]
    assert "option_strategy" not in finding.body
    assert finding.body["setups"][0]["cash_equity_view"] == "separate_from_fno"


def test_fno_agent_flags_crowded_positioning_and_hedge_needed():
    finding = FnoRiskAgent().run(
        {
            "derivatives": {
                "futures": [
                    {
                        "symbol": "AAA",
                        "futures_buildup": "LONG_BUILDUP",
                        "oi_change_pct": 32,
                        "price_change_pct": 6,
                    }
                ],
                "option_chain": {
                    "AAA": {
                        "pcr": 1.8,
                        "iv_percentile": 82,
                        "max_pain_distance_pct": 9,
                    }
                },
            }
        }
    )

    setup = finding.body["setups"][0]
    assert finding.stance == "hedge_required"
    assert finding.risks == ["crowded long positioning", "elevated IV"]
    assert setup["option_chain_available"] is True
    assert setup["crowding"] == "crowded_long"
    assert setup["hedge_needed"] is True


def test_fno_agent_separates_cash_equity_from_derivatives_setup():
    finding = FnoRiskAgent().run(
        {
            "stocks": {"candidates": [{"symbol": "AAA", "stage": "STAGE_2"}]},
            "derivatives": {
                "futures": [{"symbol": "AAA", "futures_buildup": "SHORT_BUILDUP", "oi_change_pct": 14}],
                "option_chain": {"AAA": {"pcr": 0.6, "iv_percentile": 35}},
            },
        }
    )

    setup = finding.body["setups"][0]
    assert setup["cash_equity_view"] == "separate_from_fno"
    assert setup["fno_view"] == "bearish_derivatives"
    assert finding.rejects == ["AAA"]
