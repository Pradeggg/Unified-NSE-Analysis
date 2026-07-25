from __future__ import annotations

from datetime import datetime
import time

import pandas as pd
from rich.console import Console

from terminal.live_dashboard import (
    LiveDashboardConfig,
    LiveDashboardState,
    TrackedSymbolState,
    apply_trade_decisions,
    build_mtf_level_context,
    build_live_commentary_prompt,
    deterministic_commentary,
    enrich_tracked_symbols_with_fno_context,
    enrich_tracked_symbols_with_mtf_levels,
    _enrichment_timeout_secs,
    fetch_live_dashboard_cycle,
    generate_live_commentary,
    market_regime_from_context,
    render_live_dashboard,
    style_direction,
    style_status,
    update_live_dashboard_state,
)


def _symbol(symbol: str, status: str, price: float = 100.0) -> TrackedSymbolState:
    return TrackedSymbolState(
        symbol=symbol,
        last_price=price,
        pct_change=1.2,
        direction="LONG",
        status=status,
        trigger=price - 1,
        invalidation=price - 3,
        target1=price + 5,
        target2=price + 8,
        rr=2.5,
        strategy="Supertrend",
        note="Supertrend bullish",
        freshness="2026-06-17 13:15:00",
        source="test",
    )


def test_update_live_dashboard_state_records_initial_tracker_events():
    state = LiveDashboardState(started_at=datetime(2026, 6, 17, 13, 0, 0))

    updated = update_live_dashboard_state(
        state,
        market_context="NIFTY +0.2%, BANKNIFTY +0.4%",
        tracked_symbols=[_symbol("TRENT", "long active")],
        source_health=["get_nse_quotes ok"],
    )

    assert updated.cycle == 1
    assert updated.previous_zone_by_symbol["TRENT"] == "long active"
    assert updated.events[-1].symbol == "TRENT"
    assert "initialized" in updated.events[-1].message


def test_update_live_dashboard_state_emits_meaningful_change_on_status_flip():
    state = LiveDashboardState(started_at=datetime(2026, 6, 17, 13, 0, 0))
    state = update_live_dashboard_state(
        state,
        market_context="NIFTY flat",
        tracked_symbols=[_symbol("DIXON", "long active")],
        source_health=[],
    )

    updated = update_live_dashboard_state(
        state,
        market_context="NIFTY flat",
        tracked_symbols=[_symbol("DIXON", "breakdown / long invalid", price=96.0)],
        source_health=[],
    )

    assert updated.cycle == 2
    assert updated.previous_zone_by_symbol["DIXON"] == "breakdown / long invalid"
    assert any("changed from long active to breakdown / long invalid" in e.message for e in updated.events)
    assert updated.cycle_changes["status_changes"] == [
        {"symbol": "DIXON", "from": "long active", "to": "breakdown / long invalid"}
    ]


def test_update_live_dashboard_state_reports_added_removed_and_buckets():
    state = LiveDashboardState(started_at=datetime(2026, 6, 17, 13, 0, 0))
    state = update_live_dashboard_state(
        state,
        market_context="NIFTY flat",
        tracked_symbols=[
            _symbol("TRENT", "watch"),
            _symbol("BEL", "near trigger / watch"),
            _symbol("DIXON", "long active"),
        ],
        source_health=[],
    )

    assert [row["symbol"] for row in state.cycle_changes["new_added"]] == ["BEL", "DIXON", "TRENT"]
    assert [row["symbol"] for row in state.cycle_changes["forming"]] == ["TRENT"]
    assert [row["symbol"] for row in state.cycle_changes["confirmed"]] == ["BEL"]
    assert [row["symbol"] for row in state.cycle_changes["active"]] == ["DIXON"]

    updated = update_live_dashboard_state(
        state,
        market_context="NIFTY flat",
        tracked_symbols=[_symbol("BEL", "long active"), _symbol("CDSL", "watch")],
        source_health=[],
    )

    assert [row["symbol"] for row in updated.cycle_changes["new_added"]] == ["CDSL"]
    assert [row["symbol"] for row in updated.cycle_changes["removed"]] == ["DIXON", "TRENT"]
    assert updated.cycle_changes["status_changes"] == [
        {"symbol": "BEL", "from": "near trigger / watch", "to": "long active"}
    ]


def test_fno_context_enrichment_classifies_bias(monkeypatch):
    def fake_overview(symbol):
        return {
            "status": "ok",
            "symbol": symbol,
            "pcr": 1.25,
            "basis": 0.8,
            "max_pain": 95.0,
            "top_oi_strikes": {
                "calls": [{"strike": 110, "oi": 1000}],
                "puts": [{"strike": 95, "oi": 1200}],
            },
            "source_trail": {"get_options_chain": "ok", "get_futures_analysis": "ok"},
        }

    monkeypatch.setattr("terminal.live_dashboard.get_fno_overview", fake_overview)
    row = _symbol("BEL", "watch", price=100.0)

    enriched = enrich_tracked_symbols_with_fno_context([row])[0]

    assert enriched.fno_context["bias"] == "bullish"
    assert enriched.fno_context["pcr"] == 1.25
    assert "spot above max pain" in enriched.fno_context["reason"]


def test_mtf_enrichment_marks_missing_when_one_symbol_fails(monkeypatch):
    def fake_levels(symbol, last_price, interval="5m"):
        if symbol == "BAD":
            raise TimeoutError("provider timed out")
        return {
            "support": 98.0,
            "breakout": 104.0,
            "target": 110.0,
            "breakdown_target": 92.0,
            "last_price": last_price,
            "intraday_pct_change": 1.0,
        }

    monkeypatch.setattr("terminal.live_dashboard.build_mtf_level_context", fake_levels)

    bad = _symbol("BAD", "watch", price=100.0)
    good = _symbol("GOOD", "watch", price=100.0)

    enriched = enrich_tracked_symbols_with_mtf_levels([bad, good])

    assert enriched[0].mtf_levels["status"] == "missing"
    assert "provider timed out" in enriched[0].mtf_levels["reason"]
    assert enriched[0].source == "test"
    assert enriched[1].mtf_levels["breakout"] == 104.0


def test_mtf_enrichment_times_out_slow_provider(monkeypatch):
    def slow_levels(symbol, last_price, interval="5m"):
        time.sleep(0.2)
        return {"support": 98.0, "breakout": 104.0}

    monkeypatch.setattr("terminal.live_dashboard.build_mtf_level_context", slow_levels)

    row = _symbol("SLOW", "watch", price=100.0)

    enriched = enrich_tracked_symbols_with_mtf_levels([row], timeout_secs=0.01)

    assert enriched[0].mtf_levels["status"] == "missing"
    assert "timed out" in enriched[0].mtf_levels["reason"]


def test_enrichment_timeout_uses_environment_value(monkeypatch):
    monkeypatch.setenv("AGENT_ADDA_TEST_TIMEOUT", "2")

    assert _enrichment_timeout_secs("AGENT_ADDA_TEST_TIMEOUT", 6.0) == 2.0


def test_fno_enrichment_marks_missing_when_one_symbol_fails(monkeypatch):
    def fake_overview(symbol):
        if symbol == "BAD":
            raise TimeoutError("option chain timed out")
        return {
            "status": "ok",
            "symbol": symbol,
            "pcr": 0.55,
            "basis": -1.0,
            "max_pain": 105.0,
            "top_oi_strikes": {"calls": [], "puts": []},
        }

    monkeypatch.setattr("terminal.live_dashboard.get_fno_overview", fake_overview)

    bad = _symbol("BAD", "watch", price=100.0)
    good = _symbol("GOOD", "watch", price=100.0)

    enriched = enrich_tracked_symbols_with_fno_context([bad, good])

    assert enriched[0].fno_context["status"] == "missing"
    assert enriched[0].fno_context["bias"] == "unknown"
    assert "option chain timed out" in enriched[0].fno_context["reason"]
    assert enriched[1].fno_context["bias"] == "bearish"


def test_market_regime_detects_risk_off_high_vix_breadth():
    regime = market_regime_from_context(
        "NIFTY 23,931 -0.98%, BANKNIFTY 57,514 -0.78%, VIX 13.56 +6.96%, breadth 314A/438D"
    )

    assert regime["label"] == "risk_off"
    assert regime["vix_pct"] == 6.96
    assert regime["advances"] == 314
    assert regime["declines"] == 438


def test_trade_decision_suppresses_marginal_long_in_risk_off():
    row = TrackedSymbolState(
        symbol="ABC",
        last_price=100.0,
        pct_change=-1.0,
        direction="LONG",
        status="near trigger / watch",
        trigger=101.0,
        invalidation=99.0,
        target1=104.0,
        rr=1.5,
        source="mtf_levels",
    )
    row.fno_context = {"bias": "sideways", "pcr": 0.7, "basis": 0.2, "max_pain": 105}

    decided = apply_trade_decisions(
        [row],
        "NIFTY 23,931 -0.98%, BANKNIFTY 57,514 -0.78%, VIX 13.56 +6.96%, breadth 314A/438D",
    )[0]

    assert decided.decision_context["market_regime"]["label"] == "risk_off"
    assert decided.decision_context["final_action"] in {"AVOID", "NO TRADE"}
    assert decided.decision_context["options_suitability"] in {"Avoid Options", "No Trade"}


def test_trade_decision_accepts_short_retest_in_risk_off():
    row = TrackedSymbolState(
        symbol="HDFCBANK",
        last_price=778.2,
        pct_change=-1.0,
        direction="SHORT",
        status="near trigger / watch",
        trigger=777.5,
        invalidation=779.45,
        target1=773.41,
        rr=2.1,
        source="mtf_levels",
    )
    row.fno_context = {"bias": "sideways", "pcr": 0.71, "basis": 1.0, "max_pain": 785}

    decided = apply_trade_decisions(
        [row],
        "NIFTY 23,931 -0.98%, BANKNIFTY 57,514 -0.78%, VIX 13.56 +6.96%, breadth 314A/438D",
    )[0]

    assert decided.decision_context["final_action"] == "WAIT FOR RETEST"
    assert decided.decision_context["options_suitability"] in {"Prefer Spread", "Avoid Options"}
    assert decided.decision_context["decision_score"] >= 45


def test_mtf_enrichment_marks_breakout_watch_as_long(monkeypatch):
    monkeypatch.setattr(
        "terminal.live_dashboard.build_mtf_level_context",
        lambda symbol, price, interval="5m": {
            "support": 98.0,
            "breakout": 102.0,
            "target": 106.0,
            "note": "MTF breakout level",
        },
    )
    row = TrackedSymbolState(
        symbol="BEL",
        last_price=101.0,
        pct_change=1.0,
        direction="WATCH",
        status="watch",
        source="get_nse_quotes",
    )

    enriched = enrich_tracked_symbols_with_mtf_levels([row], interval="5m")[0]

    assert enriched.direction == "LONG"
    assert enriched.status == "near trigger / watch"
    assert enriched.trigger == 102.0
    assert enriched.invalidation == 98.0


def test_mtf_enrichment_marks_weak_intraday_watch_as_short(monkeypatch):
    monkeypatch.setattr(
        "terminal.live_dashboard.build_mtf_level_context",
        lambda symbol, price, interval="5m": {
            "support": 777.6,
            "breakout": 779.7,
            "target": 789.0,
            "breakdown_target": 773.4,
        },
    )
    row = TrackedSymbolState(
        symbol="HDFCBANK",
        last_price=778.2,
        pct_change=-1.0,
        direction="WATCH",
        status="watch",
        source="get_nse_quotes",
    )

    enriched = enrich_tracked_symbols_with_mtf_levels([row], interval="5m")[0]

    assert enriched.direction == "SHORT"
    assert enriched.status == "near trigger / watch"
    assert enriched.trigger == 777.6
    assert enriched.invalidation == 779.7
    assert enriched.target1 == 773.4
    assert enriched.rr == 2.0
    assert enriched.strategy == "MTF breakdown levels"


def test_mtf_enrichment_uses_candles_when_quote_price_missing(monkeypatch):
    daily = pd.DataFrame(
        {
            "Open": [785, 782, 780, 779],
            "High": [790, 789, 786, 785],
            "Low": [770, 768, 766, 765],
            "Close": [782, 779, 778, 776],
            "Volume": [1000, 1000, 1000, 1000],
        },
        index=pd.date_range("2026-06-15", periods=4, freq="D"),
    )
    intraday = pd.DataFrame(
        {
            "Open": [785, 782, 780, 779],
            "High": [786, 783, 781, 779.7],
            "Low": [781, 779, 777.6, 777.5],
            "Close": [785, 781, 779, 778.2],
            "Volume": [1000, 1200, 1400, 1600],
        },
        index=pd.date_range("2026-06-19 09:15", periods=4, freq="5min"),
    )

    def fake_candles(symbol, interval="15m", period=None):
        return daily if interval == "1d" else intraday

    monkeypatch.setattr("terminal.live_dashboard.get_intraday_candles", fake_candles)
    row = TrackedSymbolState(
        symbol="HDFCBANK",
        last_price=None,
        pct_change=None,
        direction="WATCH",
        status="watch",
        source="get_nse_quotes",
    )

    enriched = enrich_tracked_symbols_with_mtf_levels([row], interval="5m")[0]

    assert enriched.last_price == 778.2
    assert enriched.pct_change is not None
    assert enriched.pct_change < -0.5
    assert enriched.direction == "SHORT"
    assert enriched.status == "near trigger / watch"
    assert enriched.strategy == "MTF breakdown levels"


def test_confirmed_setup_locks_entry_stop_and_target_across_cycles():
    state = LiveDashboardState(started_at=datetime(2026, 6, 17, 13, 0, 0))
    first = TrackedSymbolState(
        symbol="BEL",
        last_price=99.0,
        pct_change=1.0,
        direction="LONG",
        status="near trigger / watch",
        trigger=100.0,
        invalidation=95.0,
        target1=110.0,
        rr=2.0,
        strategy="Near Breakout + Volume",
        source="scan_symbols_intraday",
    )

    state = update_live_dashboard_state(
        state,
        market_context="NIFTY flat",
        tracked_symbols=[first],
        source_health=[],
    )

    assert state.tracked_symbols[0].locked_setup is True
    assert state.locked_setups_by_symbol["BEL"]["trigger"] == 100.0

    moved = TrackedSymbolState(
        symbol="BEL",
        last_price=101.0,
        pct_change=1.2,
        direction="LONG",
        status="long active",
        trigger=105.0,
        invalidation=98.0,
        target1=120.0,
        rr=3.0,
        strategy="Near Breakout + Volume",
        source="scan_symbols_intraday",
    )
    state = update_live_dashboard_state(
        state,
        market_context="NIFTY flat",
        tracked_symbols=[moved],
        source_health=[],
    )

    locked = state.tracked_symbols[0]
    assert locked.locked_setup is True
    assert locked.trigger == 100.0
    assert locked.invalidation == 95.0
    assert locked.target1 == 110.0
    assert locked.rr == 2.0
    assert locked.status == "long active"


def test_locked_setup_unlocks_after_invalidation():
    state = LiveDashboardState(started_at=datetime(2026, 6, 17, 13, 0, 0))
    state = update_live_dashboard_state(
        state,
        market_context="NIFTY flat",
        tracked_symbols=[
            TrackedSymbolState(
                symbol="BEL",
                last_price=101.0,
                pct_change=1.0,
                direction="LONG",
                status="long active",
                trigger=100.0,
                invalidation=95.0,
                target1=110.0,
                rr=2.0,
                strategy="Near Breakout + Volume",
                source="scan_symbols_intraday",
            )
        ],
        source_health=[],
    )

    state = update_live_dashboard_state(
        state,
        market_context="NIFTY flat",
        tracked_symbols=[
            TrackedSymbolState(
                symbol="BEL",
                last_price=94.0,
                pct_change=-1.0,
                direction="LONG",
                status="long active",
                trigger=102.0,
                invalidation=96.0,
                target1=112.0,
                rr=2.0,
                strategy="Near Breakout + Volume",
                source="scan_symbols_intraday",
            )
        ],
        source_health=[],
    )

    row = state.tracked_symbols[0]
    assert row.status == "breakdown / long invalid"
    assert row.locked_setup is False
    assert "BEL" not in state.locked_setups_by_symbol


def test_deterministic_commentary_matches_tracker_style():
    state = LiveDashboardState(started_at=datetime(2026, 6, 17, 13, 0, 0))
    state = update_live_dashboard_state(
        state,
        market_context="NIFTY +0.2%, BANKNIFTY +0.4%",
        tracked_symbols=[_symbol("INDUSINDBK", "long active")],
        source_health=["scan_symbols_intraday ok"],
    )

    text = deterministic_commentary(state)

    assert "Current read from the tracker" in text
    assert "Best actionable names" in text
    assert "INDUSINDBK" in text
    assert "Above 99" in text


def test_build_live_commentary_prompt_is_compact_and_level_specific():
    state = LiveDashboardState(started_at=datetime(2026, 6, 17, 13, 0, 0))
    state = update_live_dashboard_state(
        state,
        market_context="NIFTY +0.2%, BANKNIFTY +0.4%",
        tracked_symbols=[_symbol("TRENT", "long active")],
        source_health=["get_nse_quotes ok"],
    )

    messages = build_live_commentary_prompt(state)
    joined = "\n".join(str(m["content"]) for m in messages)

    assert "tracker commentary" in joined
    assert "TRENT" in joined
    assert "invalidation" in joined
    assert "raw_signals" not in joined
    assert "get_live_market_overview" not in joined


def test_generate_live_commentary_falls_back_when_llm_disabled():
    state = LiveDashboardState(started_at=datetime(2026, 6, 17, 13, 0, 0))
    state = update_live_dashboard_state(
        state,
        market_context="NIFTY +0.2%",
        tracked_symbols=[_symbol("TRENT", "long active")],
        source_health=[],
    )

    text = generate_live_commentary(state, backend=None, use_llm=False)

    assert "Current read from the tracker" in text


def test_fetch_live_dashboard_cycle_uses_bounded_tools(monkeypatch):
    calls: list[str] = []

    def fake_overview():
        calls.append("overview")
        return {
            "indices": {
                "NIFTY 50": {"last": 24000, "pct_change": 0.2},
                "NIFTY BANK": {"last": 57500, "pct_change": 0.4},
                "INDIA VIX": {"last": 13.2, "pct_change": -0.3},
            },
            "adv_dec": {"advances": 430, "declines": 320},
        }

    def fake_movers(index="NIFTY 500", top_n=8, direction="both"):
        calls.append("movers")
        return {"gainers": [{"symbol": "TRENT"}], "losers": [{"symbol": "DIXON"}]}

    def fake_quotes(symbols):
        calls.append("quotes")
        return {
            "quotes": {
                "TRENT": {"last_price": 3048, "pct_change": 5.1},
                "DIXON": {"last_price": 12822, "pct_change": 4.7},
            },
            "as_of": "2026-06-17 13:15:00",
        }

    def fake_scan(symbols, interval="15m", strategies=None, top_n=10, **kwargs):
        calls.append("scan")
        assert strategies == ["vcp", "volume"]
        return {
            "top_buy": [
                {
                    "symbol": "TRENT",
                    "direction": "BUY",
                    "entry": 3048,
                    "stoploss": 3040,
                    "target": 3064,
                    "rr": 2.0,
                    "strategy": "Supertrend",
                    "note": "Supertrend bullish",
                    "indicator": {"volume_confirmed": True, "vol_ratio": 1.4, "range_pct": 1.6},
                }
            ],
            "top_sell": [],
        }

    monkeypatch.setattr("terminal.live_dashboard.get_live_market_overview", fake_overview)
    monkeypatch.setattr("terminal.live_dashboard.get_top_gainers_losers", fake_movers)
    monkeypatch.setattr("terminal.live_dashboard.get_nse_quotes", fake_quotes)
    monkeypatch.setattr("terminal.live_dashboard.scan_symbols_intraday", fake_scan)

    cycle = fetch_live_dashboard_cycle(
        LiveDashboardConfig(symbols=["TRENT", "DIXON"], interval="15m", top_n=5, strategies=["vcp", "volume"])
    )

    assert calls == ["overview", "movers", "quotes", "scan"]
    assert cycle["tracked_symbols"][0].symbol == "TRENT"
    assert "get_live_market_overview ok" in cycle["source_health"]


def test_fetch_live_dashboard_cycle_reports_bse_source_modes(monkeypatch):
    monkeypatch.setenv("AGENT_ADDA_QUOTE_SOURCE", "bse")
    monkeypatch.setenv("AGENT_ADDA_INTRADAY_OHLCV_SOURCE", "bse")
    monkeypatch.setattr(
        "terminal.live_dashboard.get_live_market_overview",
        lambda: {
            "indices": {
                "NIFTY 50": {"last": 24000, "pct_change": 0.2},
                "NIFTY BANK": {"last": 57500, "pct_change": 0.4},
                "INDIA VIX": {"last": 13.2, "pct_change": -0.3},
            },
            "adv_dec": {"advances": 430, "declines": 320},
        },
    )
    monkeypatch.setattr("terminal.live_dashboard.get_top_gainers_losers", lambda **kwargs: {"gainers": [], "losers": []})
    monkeypatch.setattr(
        "terminal.live_dashboard.get_nse_quotes",
        lambda symbols: {
            "quotes": {"INFY": {"last_price": 1068.5, "pct_change": 1.5}},
            "as_of": "22 Jun 26 | 11:00",
            "source": "BSE live API batch",
        },
    )
    monkeypatch.setattr("terminal.live_dashboard.scan_symbols_intraday", lambda **kwargs: {"top_buy": [], "top_sell": []})

    cycle = fetch_live_dashboard_cycle(LiveDashboardConfig(symbols=["INFY"], interval="15m", top_n=1))

    assert "quote_source=bse" in cycle["source_health"]
    assert "ohlcv_source=bse" in cycle["source_health"]
    assert "get_nse_quotes ok: BSE live API batch" in cycle["source_health"]


def test_fetch_live_dashboard_cycle_filters_signals_without_volume(monkeypatch):
    monkeypatch.setattr("terminal.live_dashboard.get_live_market_overview", lambda: {})
    monkeypatch.setattr(
        "terminal.live_dashboard.get_index_snapshot",
        lambda name: {
            "close": {"NIFTY 50": 24000, "NIFTY BANK": 57500, "INDIA VIX": 13.2}[name],
            "chg_pct": {"NIFTY 50": 0.2, "NIFTY BANK": 0.4, "INDIA VIX": -0.3}[name],
            "high": None,
            "low": None,
            "as_of": "2026-06-18",
        },
    )
    monkeypatch.setattr("terminal.live_dashboard.get_top_gainers_losers", lambda **kwargs: {})
    monkeypatch.setattr(
        "terminal.live_dashboard.get_nse_quotes",
        lambda symbols: {"quotes": {"TRENT": {"last_price": 3048, "pct_change": 1.1}}, "as_of": "now"},
    )
    monkeypatch.setattr(
        "terminal.live_dashboard.scan_symbols_intraday",
        lambda **kwargs: {
            "top_buy": [
                {
                    "symbol": "TRENT",
                    "direction": "BUY",
                    "entry": 3050,
                    "stoploss": 3020,
                    "target": 3110,
                    "rr": 2.0,
                    "strategy": "Supertrend Flip",
                    "indicator": {"vol_ratio": 1.0, "volume_confirmed": False},
                }
            ],
            "top_sell": [],
        },
    )

    cycle = fetch_live_dashboard_cycle(
        LiveDashboardConfig(symbols=["TRENT"], interval="5m", strategies=["supertrend_breakout"])
    )

    row = cycle["tracked_symbols"][0]
    assert row.symbol == "TRENT"
    assert row.status == "watch"
    assert row.source == "get_nse_quotes"


def test_fetch_live_dashboard_cycle_falls_back_when_overview_missing_indices(monkeypatch):
    monkeypatch.setattr("terminal.live_dashboard.get_live_market_overview", lambda: {"indices": {}, "adv_dec": {}})
    monkeypatch.setattr(
        "terminal.live_dashboard.get_index_snapshot",
        lambda name: {
            "close": {"NIFTY 50": 23955.7, "NIFTY BANK": 57559.5, "INDIA VIX": 13.39}[name],
            "chg_pct": {"NIFTY 50": -0.88, "NIFTY BANK": -0.70, "INDIA VIX": 5.64}[name],
            "high": None,
            "low": None,
            "as_of": "2026-06-18",
        },
    )
    monkeypatch.setattr("terminal.live_dashboard.get_top_gainers_losers", lambda **kwargs: {})
    monkeypatch.setattr("terminal.live_dashboard.get_nse_quotes", lambda symbols: {"quotes": {}, "as_of": "now"})
    monkeypatch.setattr("terminal.live_dashboard.scan_symbols_intraday", lambda **kwargs: {"top_buy": [], "top_sell": []})

    cycle = fetch_live_dashboard_cycle(LiveDashboardConfig(symbols=["NHPC"], interval="5m"))

    assert "NIFTY 23,956 -0.88%" in cycle["market_context"]
    assert "BANKNIFTY 57,560 -0.70%" in cycle["market_context"]
    assert "VIX 13.39 +5.64%" in cycle["market_context"]
    assert "n/a" not in cycle["market_context"]
    assert any("market_context fallback" in item for item in cycle["source_health"])


def test_update_live_dashboard_state_retains_previous_good_market_context():
    state = LiveDashboardState(started_at=datetime(2026, 6, 19, 9, 30, 0))
    state = update_live_dashboard_state(
        state,
        market_context="NIFTY 23,956 -0.88%, BANKNIFTY 57,560 -0.70%, VIX 13.39 +5.64%",
        tracked_symbols=[_symbol("NHPC", "near trigger / watch")],
        source_health=["get_live_market_overview ok"],
    )

    state = update_live_dashboard_state(
        state,
        market_context="NIFTY n/a n/a, BANKNIFTY n/a n/a, VIX n/a n/a",
        tracked_symbols=[_symbol("NHPC", "long active")],
        source_health=["get_live_market_overview incomplete"],
    )

    assert state.market_context == "NIFTY 23,956 -0.88%, BANKNIFTY 57,560 -0.70%, VIX 13.39 +5.64%"
    assert "market_context retained from previous good cycle" in state.source_health


def test_render_live_dashboard_returns_rich_renderable():
    state = LiveDashboardState(started_at=datetime(2026, 6, 17, 13, 0, 0))
    state = update_live_dashboard_state(
        state,
        market_context="NIFTY +0.2%",
        tracked_symbols=[_symbol("TRENT", "long active")],
        source_health=[],
    )
    state.last_commentary = deterministic_commentary(state)

    renderable = render_live_dashboard(state)

    assert renderable is not None


def test_live_dashboard_status_and_direction_styles_are_semantic():
    assert style_direction("LONG").plain == "LONG"
    assert "green" in str(style_direction("LONG").style)
    assert "red" in str(style_direction("SHORT").style)
    assert "yellow" in str(style_direction("WATCH").style)

    assert "green" in str(style_status("long active").style)
    assert "red" in str(style_status("short active").style)
    assert "yellow" in str(style_status("watch").style)
    assert "red" in str(style_status("breakdown / long invalid").style)


def test_render_live_dashboard_expands_tracker_columns_for_readability():
    state = LiveDashboardState(started_at=datetime(2026, 6, 17, 13, 0, 0))
    state = update_live_dashboard_state(
        state,
        market_context="NIFTY +0.2%, BANKNIFTY -0.1%, breadth 430A/320D",
        tracked_symbols=[
            _symbol("TRENT", "long active", price=3048),
            TrackedSymbolState(
                symbol="DIXON",
                last_price=12822,
                pct_change=-1.8,
                direction="SHORT",
                status="short active",
                trigger=12800,
                invalidation=12920,
                target1=12650,
                rr=1.8,
                strategy="Retest",
                source="test",
            ),
        ],
        source_health=["get_nse_quotes ok", "scan_symbols_intraday ok"],
    )
    state.last_commentary = deterministic_commentary(state)

    console = Console(record=True, width=220, force_terminal=True, color_system="truecolor")
    console.print(render_live_dashboard(state))
    text = console.export_text(styles=False)

    assert "Read" in text
    assert "LTP" in text
    assert "Chg" in text
    assert "Trigger" in text
    assert "Stop" in text
    assert "T1/RR" in text


def test_build_tracked_symbol_uses_signal_entry_when_live_quote_missing():
    from terminal.live_dashboard import build_tracked_symbol

    row = build_tracked_symbol(
        "CDSL",
        {"error": "'Close'"},
        {
            "symbol": "CDSL",
            "direction": "BUY",
            "entry": 1325.7,
            "stoploss": 1286.27,
            "target": 1443.99,
            "rr": 3.0,
            "strategy": "Multi-Confirm BUY",
            "note": "3/4 signals aligned bullish",
        },
        freshness="2026-06-18 10:11:24",
    )

    assert row.last_price == 1325.7
    assert row.status == "long active"


def test_build_tracked_symbol_keeps_same_tick_supertrend_continuation_as_watch():
    from terminal.live_dashboard import build_tracked_symbol

    row = build_tracked_symbol(
        "ONGC",
        {"last_price": 244.55, "pct_change": -0.31},
        {
            "symbol": "ONGC",
            "direction": "BUY",
            "entry": 244.55,
            "stoploss": 244.22,
            "target": 245.34,
            "rr": 2.39,
            "strategy": "Supertrend",
            "strength": "Moderate (in uptrend)",
            "note": "Supertrend bullish — support at 244.22",
        },
        freshness="2026-06-19 09:59:37",
    )

    assert row.status == "near trigger / watch"
    assert row.trigger == 244.55
    assert "needs next candle hold above trigger" in row.note


def test_build_tracked_symbol_allows_supertrend_flip_to_be_active():
    from terminal.live_dashboard import build_tracked_symbol

    row = build_tracked_symbol(
        "ONGC",
        {"last_price": 244.55},
        {
            "symbol": "ONGC",
            "direction": "BUY",
            "entry": 244.55,
            "stoploss": 244.22,
            "target": 245.34,
            "rr": 2.39,
            "strategy": "Supertrend",
            "strength": "Strong",
            "note": "Price crossed above Supertrend (244.22)",
        },
        freshness="2026-06-19 09:59:37",
    )

    assert row.status == "long active"


def test_mtf_level_enrichment_populates_watch_trigger_stop_target(monkeypatch):
    daily = pd.DataFrame(
        {
            "Open": [98, 101, 102, 104, 105, 106],
            "High": [102, 104, 106, 108, 110, 109],
            "Low": [96, 99, 100, 102, 103, 104],
            "Close": [101, 103, 105, 107, 108, 106],
            "Volume": [1000, 1100, 1200, 1300, 1400, 1500],
        },
        index=pd.date_range("2026-06-10", periods=6, freq="D"),
    )
    intraday = pd.DataFrame(
        {
            "Open": [104, 105, 106, 107, 108, 108.5, 109],
            "High": [105, 106, 107, 108, 109, 110, 111],
            "Low": [103, 104, 105, 106, 107, 108, 108.5],
            "Close": [104.5, 105.5, 106.5, 107.5, 108.5, 109.5, 110.5],
            "Volume": [1000, 1200, 1300, 1400, 1500, 1600, 1700],
        },
        index=pd.date_range("2026-06-18 09:15", periods=7, freq="5min"),
    )

    def fake_candles(symbol, interval="15m", period=None):
        return daily if interval == "1d" else intraday

    monkeypatch.setattr("terminal.live_dashboard.get_intraday_candles", fake_candles)

    row = TrackedSymbolState(
        symbol="TEST",
        last_price=110.5,
        pct_change=1.2,
        direction="WATCH",
        status="watch",
    )
    enriched = enrich_tracked_symbols_with_mtf_levels([row], interval="5m")[0]

    assert enriched.trigger == 111
    assert enriched.invalidation == 103
    assert enriched.target1 > enriched.trigger
    assert enriched.rr is not None
    assert enriched.mtf_levels["windows"]["previous_week"]["resistance"] == 110
    assert enriched.mtf_levels["windows"]["previous_3_days"]["support"] == 100
    assert "Last 30 mins" in enriched.note


def test_mtf_context_slices_intraday_fallback_to_latest_session(monkeypatch):
    daily = pd.DataFrame(
        {
            "Open": [98, 101, 102, 104],
            "High": [104, 106, 108, 110],
            "Low": [94, 96, 98, 100],
            "Close": [101, 103, 105, 107],
            "Volume": [1000, 1100, 1200, 1300],
        },
        index=pd.date_range("2026-06-19", periods=4, freq="D"),
    )
    intraday = pd.DataFrame(
        {
            "Open": [70, 71, 101, 102],
            "High": [75, 76, 104, 103],
            "Low": [50, 69, 99, 100],
            "Close": [72, 73, 101, 102],
            "Volume": [1000, 1000, 1200, 1300],
        },
        index=pd.to_datetime(
            [
                "2026-03-30 09:00",
                "2026-03-30 09:30",
                "2026-06-24 09:00",
                "2026-06-24 09:30",
            ]
        ),
    )

    def fake_candles(symbol, interval="15m", period=None):
        return daily if interval == "1d" else intraday

    monkeypatch.setattr("terminal.live_dashboard.get_intraday_candles", fake_candles)

    levels = build_mtf_level_context("TEST", 102, interval="15m")

    assert levels["windows"]["start_of_day"]["support"] == 99
    assert levels["windows"]["start_of_day"]["resistance"] == 104
    assert levels["intraday_pct_change"] == 0.99
    assert levels["breakdown_target"] != 50
    assert levels["range_pressure_pct"] < 20
