from terminal.research_council.agents.macro_regime import MacroRegimeAgent


def test_macro_regime_classifies_risk_on_from_breadth_and_flows():
    finding = MacroRegimeAgent().run(
        {
            "market": {
                "regime": "RISK_ON",
                "breadth_pct_above_50dma": 68,
                "fii_dii_flow_5d_cr": 1200,
                "fii_dii_flow_1d_cr": -100,
            },
            "sectors": {
                "items": [
                    {"sector": "Capital Goods", "rs_1m": 12, "breadth_pct_above_50dma": 70},
                    {"sector": "IT", "rs_1m": -4, "breadth_pct_above_50dma": 35},
                ]
            },
        }
    )

    assert finding.stance == "risk_on"
    assert finding.body["risk_regime"] == "risk_on"
    assert finding.body["tailwinds"] == ["Capital Goods"]
    assert finding.body["headwinds"] == ["IT"]


def test_breadth_deterioration_downgrades_risk_stance():
    finding = MacroRegimeAgent().run(
        {
            "market": {
                "regime": "RISK_ON",
                "breadth_pct_above_50dma": 32,
                "fii_dii_flow_5d_cr": 900,
            }
        }
    )

    assert finding.stance == "risk_mixed"
    assert "breadth deterioration" in finding.risks


def test_one_day_flow_spike_does_not_override_five_day_context():
    finding = MacroRegimeAgent().run(
        {
            "market": {
                "breadth_pct_above_50dma": 58,
                "fii_dii_flow_5d_cr": -700,
                "fii_dii_flow_1d_cr": 2000,
            }
        }
    )

    assert finding.stance == "risk_mixed"
    assert finding.body["flow_context"] == "five_day_negative"
