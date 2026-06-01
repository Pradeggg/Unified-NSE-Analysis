from terminal.research_council.agents.fundamental import FundamentalAgent


def test_fundamental_agent_classifies_supportive_mixed_and_weak_quality():
    evidence = {
        "fundamentals": {
            "items": [
                {
                    "symbol": "AAA",
                    "sales_growth": 22,
                    "profit_growth": 31,
                    "roe": 19,
                    "roce": 23,
                    "debt_to_equity": 0.2,
                    "promoter_pledge": 0,
                    "opm": 21,
                },
                {
                    "symbol": "BBB",
                    "sales_growth": 12,
                    "profit_growth": 8,
                    "roe": 11,
                    "roce": 13,
                    "debt_to_equity": 0.8,
                    "promoter_pledge": 5,
                    "opm": 14,
                },
                {
                    "symbol": "CCC",
                    "sales_growth": -4,
                    "profit_growth": -20,
                    "roe": 4,
                    "roce": 6,
                    "debt_to_equity": 2.8,
                    "promoter_pledge": 42,
                    "opm": 6,
                },
            ]
        }
    }

    finding = FundamentalAgent().run(evidence)

    quality = {item["symbol"]: item["quality"] for item in finding.body["quality"]}
    assert quality["AAA"] == "quality_supportive"
    assert quality["BBB"] == "quality_mixed"
    assert quality["CCC"] == "quality_weak"
    assert "AAA" in finding.candidates
    assert "CCC" in finding.rejects


def test_fundamental_agent_missing_evidence_is_unknown():
    finding = FundamentalAgent().run({"fundamentals": {"items": [{"symbol": "AAA"}]}})

    assert finding.stance == "neutral"
    assert finding.body["quality"][0]["quality"] == "quality_unknown"
    assert finding.candidates == []
