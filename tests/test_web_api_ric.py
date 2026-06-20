import asyncio

from agent_adda.web_api.routes import ric
from agent_adda.web_api.routes.ric import (
    _fallback_text,
    _options_play,
    _quality_gate_setup,
)


def test_quality_gate_marks_low_rr_and_low_potential_as_watch_only():
    setup = {
        "bias": "BULLISH",
        "trigger": 36040.0,
        "stop": 35831.67,
        "targets": [36073.33, 36161.67],
        "rr": 0.16,
        "strategy": "Pivot breakout - long above R1 with volume",
        "potential_pct": 0.092,
        "holding": "same-day (exit before 3:15 PM)",
    }

    gated = _quality_gate_setup(
        setup,
        min_rr=1.5,
        min_potential_pct=0.25,
        label="intraday",
    )

    assert gated["actionable"] is False
    assert gated["quality_label"] == "WATCH_ONLY"
    assert "R:R 0.16x below 1.5x minimum" in gated["quality_reasons"]
    assert "potential 0.092% below 0.25% minimum" in gated["quality_reasons"]
    assert gated["strategy"].startswith("No clean intraday trade")


def test_fallback_does_not_promote_failed_quality_gate():
    safety = {
        "rating": "MODERATE",
        "score": 6,
        "reasons": ["PCR 0.79 - heavy call writing, cautious"],
    }
    intraday = _quality_gate_setup(
        {
            "bias": "BULLISH",
            "trigger": 36040.0,
            "stop": 35831.67,
            "targets": [36073.33, 36161.67],
            "rr": 0.16,
            "strategy": "Pivot breakout - long above R1 with volume",
            "potential_pct": 0.092,
            "holding": "same-day (exit before 3:15 PM)",
        },
        min_rr=1.5,
        min_potential_pct=0.25,
        label="intraday",
    )
    swing = _quality_gate_setup(
        {
            "bias": "BULLISH",
            "trigger": 36161.67,
            "stop": 35645.16,
            "targets": [36812.58, 37427.33],
            "rr": 1.26,
            "strategy": "Trend continuation - buy breakout; hold 3-7 days",
            "potential_pct": 1.8,
            "holding": "3-7 days (positional)",
        },
        min_rr=1.5,
        min_potential_pct=1.0,
        label="swing",
    )

    text = _fallback_text("POWERINDIA", safety, intraday, swing)

    assert "Overall verdict: MODERATE (6/10)" in text
    assert "Best intraday trade: No clean trade" in text
    assert "Swing opportunity: Watch only" in text
    assert "Go long" not in text
    assert "Safe -" not in text


def test_options_play_stays_out_when_underlying_setups_are_not_actionable():
    intraday = {"bias": "BULLISH", "actionable": False}
    swing = {"bias": "BULLISH", "actionable": False}

    options = _options_play(intraday, swing, pcr=0.79, atm=36000, expiry="2026-06-30")

    assert options["strategy"] == "No directional options trade"
    assert "watch-only" in options["description"]


def test_ric_endpoint_gates_powerindia_style_low_quality_trade(monkeypatch):
    class FakeTools:
        @staticmethod
        def get_intraday_levels(symbol, timeframe):
            return {
                "latest_close": 36020.0,
                "pivot": 35800.0,
                "supports": [35831.67],
                "resistances": [36040.0, 36073.33, 36161.67],
                "ema_levels": {
                    "ema9": 35990.0,
                    "ema21": 35950.0,
                    "ema50": 35645.16,
                    "ema200": 35000.0,
                },
            }

        @staticmethod
        def get_index_snapshot(name):
            return {
                "close": 24085.7,
                "chg_pct": 0.4,
                "trend_10d": {"up_days": 5, "chg_pct": 0.3},
            }

        @staticmethod
        def get_options_chain(symbol):
            return {
                "pcr": 0.788,
                "atm": 36000.0,
                "max_pain": 36500.0,
                "expiry": "2026-06-30",
                "calls": [{"strike": 40000, "oi": 10}],
                "puts": [{"strike": 31000, "oi": 10}],
            }

        @staticmethod
        def get_futures_analysis(symbol):
            return {}

        @staticmethod
        def _quick_analysis_fno(symbol):
            return {"fno_signal": "NEUTRAL", "pcr": 0.788}

    monkeypatch.setattr(ric, "_tools", lambda: FakeTools)

    result = asyncio.run(
        ric.ric_analyze(symbol="POWERINDIA", timeframe="5m", exchange="NSE")
    )

    assert result["safety"]["rating"] == "MODERATE"
    assert result["intraday"]["actionable"] is False
    assert result["swing"]["actionable"] is False
    assert result["options_play"]["strategy"] == "No directional options trade"
    assert "Best intraday trade: No clean trade" in result["recommendation"]
    assert "Go long" not in result["recommendation"]
