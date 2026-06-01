from terminal.research_council.agents.technical import TechnicalAgent


def test_technical_agent_classifies_actionable_extended_and_damaged_setups():
    evidence = {
        "stocks": {
            "candidates": [
                {
                    "symbol": "AAA",
                    "stage": "STAGE_2",
                    "rs": 82,
                    "price_above_sma20": True,
                    "price_above_sma50": True,
                    "price_above_sma200": True,
                    "rsi": 64,
                    "macd": "bullish",
                    "adx": 31,
                    "supertrend": "BUY",
                    "volume_ratio": 1.6,
                    "from_52w_high_pct": -4.0,
                    "close": 250,
                    "atr": 8,
                },
                {
                    "symbol": "BBB",
                    "stage": "STAGE_2",
                    "rs": 78,
                    "price_above_sma20": True,
                    "price_above_sma50": True,
                    "price_above_sma200": True,
                    "rsi": 83,
                    "volume_ratio": 2.2,
                    "from_52w_high_pct": -1.0,
                    "close": 500,
                    "atr": 15,
                },
                {
                    "symbol": "CCC",
                    "stage": "STAGE_4",
                    "rs": 21,
                    "price_above_sma20": False,
                    "price_above_sma50": False,
                    "price_above_sma200": False,
                    "rsi": 38,
                    "volume_ratio": 0.8,
                },
            ]
        }
    }

    finding = TechnicalAgent().run(evidence)

    buckets = {item["symbol"]: item["setup_bucket"] for item in finding.body["setups"]}
    assert buckets["AAA"] == "ACTIONABLE"
    assert buckets["BBB"] == "EXTENDED"
    assert buckets["CCC"] == "DAMAGED"
    assert finding.candidates == ["AAA"]
    assert finding.body["setups"][0]["entry_zone"] == {"low": 250, "high": 254.0}
    assert finding.body["setups"][0]["stop_loss"] == 234.0


def test_technical_agent_marks_missing_data_as_insufficient_not_actionable():
    finding = TechnicalAgent().run({"stocks": {"candidates": [{"symbol": "AAA"}]}})

    assert finding.stance == "neutral"
    assert finding.candidates == []
    assert finding.body["setups"][0]["setup_bucket"] == "INSUFFICIENT_DATA"
    assert "insufficient technical evidence" in finding.risks
