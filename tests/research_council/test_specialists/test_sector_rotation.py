from terminal.research_council.agents.sector_rotation import SectorRotationAgent


def test_sector_rotation_classifies_leaders_and_deteriorating_sectors():
    evidence = {
        "sectors": {
            "items": [
                {
                    "sector": "Capital Goods",
                    "rs_1m": 14.0,
                    "rs_3m": 21.0,
                    "breadth_pct_above_50dma": 72.0,
                    "stage2_count": 18,
                    "top_stocks": ["AAA", "BBB"],
                },
                {
                    "sector": "FMCG",
                    "rs_1m": 8.0,
                    "rs_3m": 12.0,
                    "breadth_pct_above_50dma": 38.0,
                    "stage2_count": 3,
                    "top_stocks": ["CCC"],
                },
                {
                    "sector": "IT",
                    "rs_1m": -7.0,
                    "rs_3m": -11.0,
                    "breadth_pct_above_50dma": 29.0,
                    "stage2_count": 1,
                    "top_stocks": ["DDD"],
                },
            ],
            "macro_tailwinds": {"Capital Goods": 1.2, "IT": -0.4},
        }
    }

    finding = SectorRotationAgent().run(evidence)

    assert finding.agent == "sector_rotation"
    assert finding.stance == "constructive"
    assert "AAA" in finding.candidates
    assert "DDD" not in finding.candidates
    assert finding.body["leader_sectors"][0]["sector"] == "Capital Goods"
    assert finding.body["rotation_signals"][0]["signal"] == "BREADTH_BREAKDOWN"
    assert finding.body["laggard_sectors"][0]["sector"] == "IT"


def test_sector_rotation_returns_neutral_when_evidence_missing():
    finding = SectorRotationAgent().run({})

    assert finding.stance == "neutral"
    assert finding.confidence <= 0.3
    assert finding.candidates == []
    assert "sector evidence missing" in finding.risks


def test_sector_rotation_uses_targeted_sector_shortlist_when_breadth_metrics_missing():
    evidence = {
        "sector_opportunity": {"requested_sector": "NIFTY AUTO", "resolved_sector": "EV & Auto Ancillaries"},
        "sectors": {
            "items": [
                {
                    "sector": "EV & Auto Ancillaries",
                    "rs_1m": 1.84,
                    "rs_3m": 3.0,
                    "breadth_pct_above_50dma": None,
                    "stage2_count": 6,
                    "buy_signals": 4,
                    "top_stocks": ["BAJAJ-AUTO", "EXIDEIND"],
                }
            ]
        },
    }

    finding = SectorRotationAgent().run(evidence)

    assert finding.stance == "targeted_shortlist"
    assert finding.candidates == ["BAJAJ-AUTO", "EXIDEIND"]
    assert "sector breadth evidence missing" in finding.risks
