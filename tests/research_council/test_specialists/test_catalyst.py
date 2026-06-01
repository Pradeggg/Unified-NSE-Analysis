from terminal.research_council.agents.catalyst import CatalystAgent


def test_catalyst_agent_flags_high_impact_event_risk_within_five_days():
    finding = CatalystAgent().run(
        {
            "events": {
                "items": [
                    {
                        "symbol": "AAA",
                        "event_type": "RESULTS",
                        "trading_days_ahead": 3,
                        "impact": "high",
                        "source": "bse",
                        "status": "verified",
                    }
                ]
            }
        }
    )

    assert finding.stance == "wait_for_confirmation"
    assert finding.candidates == ["AAA"]
    assert finding.risks == ["high-impact event within 5 trading days"]
    assert finding.body["catalysts"][0]["classification"] == "verified"


def test_catalyst_agent_does_not_claim_without_source_trail():
    finding = CatalystAgent().run(
        {
            "events": {
                "items": [
                    {
                        "symbol": "AAA",
                        "event_type": "BROKER_NOTE",
                        "trading_days_ahead": 2,
                        "impact": "high",
                    }
                ]
            }
        }
    )

    assert finding.stance == "unstructured"
    assert finding.candidates == []
    assert finding.required_next_steps == ["Add source trail for AAA catalyst evidence"]
    assert finding.body["catalysts"][0]["classification"] == "unstructured"


def test_catalyst_agent_classifies_stale_and_absent_evidence():
    stale = CatalystAgent().run(
        {
            "events": {
                "items": [
                    {
                        "symbol": "AAA",
                        "event_type": "CONCALL",
                        "trading_days_ahead": -8,
                        "impact": "medium",
                        "source": "exchange",
                    }
                ]
            }
        }
    )
    absent = CatalystAgent().run({"events": {"items": []}})

    assert stale.body["catalysts"][0]["classification"] == "stale"
    assert absent.stance == "absent"
    assert absent.thesis == "No catalyst evidence available."
