from terminal.research_council.agents.minervini import MinerviniAgent


def test_minervini_agent_accepts_strict_stage2_leader():
    finding = MinerviniAgent().run(
        {
            "stocks": {
                "candidates": [
                    {
                        "symbol": "AAA",
                        "stage": "STAGE_2",
                        "rs": 88,
                        "price_above_sma20": True,
                        "price_above_sma50": True,
                        "price_above_sma200": True,
                        "from_52w_high_pct": -5,
                        "volume_ratio": 1.6,
                        "tightness_pct": 6,
                    }
                ]
            }
        }
    )

    assert finding.stance == "selective_long"
    assert finding.candidates == ["AAA"]
    assert finding.body["setups"][0]["verdict"] == "MINERVINI_PASS"


def test_minervini_agent_rejects_extended_breakout():
    finding = MinerviniAgent().run(
        {
            "stocks": {
                "candidates": [
                    {
                        "symbol": "EXT",
                        "stage": "STAGE_2",
                        "rs": 92,
                        "price_above_sma20": True,
                        "price_above_sma50": True,
                        "price_above_sma200": True,
                        "from_52w_high_pct": 4,
                        "volume_ratio": 4.0,
                        "tightness_pct": 18,
                    }
                ]
            }
        }
    )

    assert finding.stance == "no_setup"
    assert finding.rejects == ["EXT"]
    assert "extended_or_loose" in finding.body["setups"][0]["reject_reasons"]


def test_minervini_agent_requires_tightness_evidence_when_missing():
    finding = MinerviniAgent().run(
        {
            "stocks": {
                "candidates": [
                    {
                        "symbol": "AAA",
                        "stage": "STAGE_2",
                        "rs": 88,
                        "price_above_sma20": True,
                        "price_above_sma50": True,
                        "price_above_sma200": True,
                        "from_52w_high_pct": -5,
                        "volume_ratio": 1.6,
                    }
                ]
            }
        }
    )

    assert finding.candidates == []
    assert finding.required_next_steps == ["Add VCP/tightness evidence for AAA"]
