from __future__ import annotations

import json
from datetime import datetime
from datetime import timedelta

from rich.console import Console

from terminal.market_calendar import market_session_status
from terminal.live_dashboard import LiveDashboardState, TrackedSymbolState
from terminal.live_intraday_alerts import (
    AlertCandidate,
    DEFAULT_BREAKOUT_STRATEGIES,
    IntradayAlertConfig,
    apply_edge_memory_to_tracked_symbols,
    apply_options_execution_to_tracked_symbols,
    apply_trade_timing_score,
    build_intraday_cycle_log_record,
    build_sharp_movers_section,
    build_trading_stance,
    build_alert_email_body,
    build_email_commentary,
    build_options_execution_section,
    collect_sharp_movers,
    collect_alert_candidates,
    config_from_args,
    dispatch_alert_email,
    evaluate_trade_timing_outcomes,
    extract_trade_timing_rows,
    build_arg_parser,
    _is_email_cadence_due,
    load_intraday_alert_symbols,
    load_fno_intraday_universe,
    render_intraday_alert_dashboard,
    save_intraday_alert_symbols,
    select_tracking_rows,
    write_intraday_cycle_log,
    write_intraday_latest_snapshot,
    write_trade_timing_audit_report,
    run_intraday_alert_commentary,
    _active_intraday_strategies,
    _candidate_action_line,
    _candidate_subject_label,
    _email_delivery_confirmation,
)


def _row(symbol: str, status: str, direction: str = "LONG", rr: float = 3.0) -> TrackedSymbolState:
    return TrackedSymbolState(
        symbol=symbol,
        last_price=100.0,
        pct_change=1.2,
        direction=direction,
        status=status,
        trigger=100.0,
        invalidation=97.0,
        target1=109.0,
        rr=rr,
        strategy="Multi-Confirm",
        note="test setup",
    )


def _patch_market_open(monkeypatch) -> None:
    open_status = market_session_status(datetime(2026, 5, 11, 10, 30, 0))
    monkeypatch.setattr(
        "terminal.live_intraday_alerts.market_session_status",
        lambda _now=None: open_status,
    )


def test_collect_alert_candidates_filters_by_trigger_and_min_rr():
    config = IntradayAlertConfig(min_rr=2.0, trigger="active_or_near")
    rows = [
        _row("RELIANCE", "long active", "LONG", 3.0),
        _row("DIXON", "near trigger / watch", "SHORT", 2.5),
        _row("MCX", "short active", "SHORT", 1.2),
        _row("SBIN", "watch", "WATCH", 5.0),
    ]

    candidates = collect_alert_candidates(rows, config)

    assert [(item.symbol, item.side) for item in candidates] == [
        ("RELIANCE", "LONG"),
        ("DIXON", "SHORT"),
    ]


def test_collect_alert_candidates_suppresses_avoid_decisions():
    config = IntradayAlertConfig(min_rr=1.3, trigger="active_or_near")
    avoid = _row("HDFCBANK", "near trigger / watch", "LONG", 4.0)
    avoid.decision_context = {
        "final_action": "AVOID",
        "options_suitability": "Avoid Options",
        "decision_score": 20,
    }
    wait = _row("TRENT", "near trigger / watch", "SHORT", 2.0)
    wait.decision_context = {
        "final_action": "WAIT FOR RETEST",
        "options_suitability": "Prefer Spread",
        "decision_score": 55,
    }

    candidates = collect_alert_candidates([avoid, wait], config)

    assert [(item.symbol, item.side) for item in candidates] == [("TRENT", "SHORT")]
    assert candidates[0].decision["final_action"] == "WAIT FOR RETEST"


def test_edge_memory_retires_matching_live_candidate_before_alert_collection():
    config = IntradayAlertConfig(min_rr=1.3, trigger="active_or_near")
    row = _row("NIFTY", "long active", "LONG", 3.0)
    row.decision_context = {
        "final_action": "TRADE NOW",
        "options_suitability": "Option Buy OK",
        "decision_score": 76,
        "reasons": ["live trigger active"],
    }

    apply_edge_memory_to_tracked_symbols(
        [row],
        [
            {
                "symbol": "NIFTY",
                "setup": "ORB + VWAP",
                "direction": "LONG",
                "timeframe": "15m",
                "status": "retired",
                "edge_role": "edge_diluter",
                "confidence": 0.51,
                "persistence_count": 2,
            }
        ],
        timeframe="15m",
    )
    candidates = collect_alert_candidates([row], config)

    assert candidates == []
    assert row.decision_context["final_action"] == "AVOID"
    assert row.decision_context["options_suitability"] == "No Trade"
    assert row.decision_context["edge_memory"]["status"] == "retired"
    assert any("retired edge memory" in reason for reason in row.decision_context["reasons"])


def test_edge_memory_marks_watch_row_when_symbol_has_retired_directional_edge():
    row = _row("BANKNIFTY", "watch", "WATCH", 3.0)
    row.decision_context = {
        "final_action": "WATCH ONLY",
        "options_suitability": "Option Buy OK",
        "decision_score": 48,
        "reasons": ["watching index"],
    }

    apply_edge_memory_to_tracked_symbols(
        [row],
        [
            {
                "symbol": "BANKNIFTY",
                "setup": "ORB + VWAP",
                "direction": "LONG",
                "timeframe": "15m",
                "status": "retired",
                "edge_role": "edge_diluter",
                "confidence": 0.54,
                "persistence_count": 2,
            }
        ],
        timeframe="15m",
    )

    assert row.decision_context["final_action"] == "AVOID"
    assert row.decision_context["edge_memory"]["status"] == "retired"
    assert row.decision_context["edge_memory"]["direction"] == "LONG"
    assert any("ORB + VWAP LONG is edge_diluter" in reason for reason in row.decision_context["reasons"])


def test_edge_memory_promotes_active_candidate_and_adds_reason():
    row = _row("MIDCPNIFTY", "long active", "LONG", 2.2)
    row.decision_context = {
        "final_action": "WATCH ONLY",
        "options_suitability": "Option Buy OK",
        "decision_score": 58,
        "reasons": ["technical setup active"],
    }

    apply_edge_memory_to_tracked_symbols(
        [row],
        [
            {
                "symbol": "MIDCPNIFTY",
                "setup": "ORB + VWAP",
                "direction": "LONG",
                "timeframe": "15m",
                "status": "promoted",
                "edge_role": "core_carrier",
                "confidence": 0.84,
                "persistence_count": 2,
            }
        ],
        timeframe="15m",
    )

    assert row.decision_context["final_action"] == "TRADE NOW"
    assert row.decision_context["decision_score"] == 68
    assert row.decision_context["edge_memory"]["status"] == "promoted"
    assert any("promoted edge memory" in reason for reason in row.decision_context["reasons"])


def test_trade_timing_score_marks_opening_promoted_active_setup_as_trade_window():
    row = _row("MIDCPNIFTY", "long active", "LONG", 2.4)
    row.fno_context = {"bias": "bullish"}
    row.decision_context = {
        "final_action": "TRADE NOW",
        "decision_score": 72,
        "edge_memory": {
            "status": "promoted",
            "edge_role": "core_carrier",
            "setup": "ORB + VWAP",
            "confidence": 0.84,
            "persistence_count": 2,
        },
        "reasons": ["promoted edge memory"],
    }

    apply_trade_timing_score([row], as_of=datetime(2026, 6, 22, 9, 45))

    timing = row.decision_context["trade_timing"]
    assert timing["time_bucket"] == "opening_drive"
    assert timing["score"] >= 80
    assert timing["window"] == "TRADE_WINDOW"
    assert "promoted edge" in "; ".join(timing["reasons"])


def test_trade_timing_score_keeps_retired_edge_as_no_trade_window():
    row = _row("BANKNIFTY", "watch", "WATCH", 3.0)
    row.fno_context = {"bias": "bullish"}
    row.decision_context = {
        "final_action": "AVOID",
        "decision_score": 3,
        "edge_memory": {
            "status": "retired",
            "edge_role": "edge_diluter",
            "setup": "ORB + VWAP",
            "direction": "LONG",
            "confidence": 0.54,
            "persistence_count": 2,
        },
        "reasons": ["retired edge memory"],
    }

    apply_trade_timing_score([row], as_of=datetime(2026, 6, 22, 9, 45))

    timing = row.decision_context["trade_timing"]
    assert timing["time_bucket"] == "opening_drive"
    assert timing["window"] == "NO_TRADE_WINDOW"
    assert timing["score"] <= 25
    assert "retired edge" in "; ".join(timing["reasons"])


def test_extract_trade_timing_rows_flattens_cycle_state_for_audit():
    state = LiveDashboardState(started_at=datetime(2026, 6, 22, 9, 30))
    state.last_updated_at = datetime(2026, 6, 22, 9, 45)
    state.cycle = 4
    row = _row("MIDCPNIFTY", "long active", "LONG", 2.4)
    row.decision_context = {
        "final_action": "TRADE NOW",
        "decision_score": 72,
        "edge_memory": {
            "status": "promoted",
            "edge_role": "core_carrier",
            "setup": "ORB + VWAP",
            "confidence": 0.84,
            "persistence_count": 2,
        },
        "trade_timing": {
            "score": 85,
            "window": "TRADE_WINDOW",
            "time_bucket": "opening_drive",
            "reasons": ["promoted edge", "trigger active"],
        },
    }
    state.tracked_symbols = [row]

    rows = extract_trade_timing_rows(state)

    assert rows == [
        {
            "timestamp": "2026-06-22T09:45:00",
            "cycle": 4,
            "symbol": "MIDCPNIFTY",
            "direction": "LONG",
            "status": "long active",
            "last_price": 100.0,
            "trigger": 100.0,
            "invalidation": 97.0,
            "target1": 109.0,
            "rr": 2.4,
            "final_action": "TRADE NOW",
            "decision_score": 72,
            "timing_window": "TRADE_WINDOW",
            "timing_score": 85,
            "time_bucket": "opening_drive",
            "timing_reasons": ["promoted edge", "trigger active"],
            "edge_status": "promoted",
            "edge_role": "core_carrier",
            "edge_setup": "ORB + VWAP",
            "edge_confidence": 0.84,
        }
    ]


def test_evaluate_trade_timing_outcomes_compares_later_cycle_prices():
    records = [
        {
            "cycle": 1,
            "timestamp": "2026-06-22T09:45:00",
            "trade_timing_scores": [
                {
                    "cycle": 1,
                    "timestamp": "2026-06-22T09:45:00",
                    "symbol": "MIDCPNIFTY",
                    "direction": "LONG",
                    "last_price": 100.0,
                    "timing_window": "TRADE_WINDOW",
                    "timing_score": 85,
                    "time_bucket": "opening_drive",
                }
            ],
        },
        {
            "cycle": 2,
            "timestamp": "2026-06-22T10:00:00",
            "trade_timing_scores": [
                {
                    "cycle": 2,
                    "timestamp": "2026-06-22T10:00:00",
                    "symbol": "MIDCPNIFTY",
                    "direction": "LONG",
                    "last_price": 103.0,
                    "timing_window": "TRADE_WINDOW",
                    "timing_score": 88,
                    "time_bucket": "opening_drive",
                }
            ],
        },
    ]

    outcomes = evaluate_trade_timing_outcomes(records, horizon_cycles=2)

    assert len(outcomes) == 1
    assert outcomes[0]["symbol"] == "MIDCPNIFTY"
    assert outcomes[0]["entry_price"] == 100.0
    assert outcomes[0]["future_price"] == 103.0
    assert outcomes[0]["directional_return_pct"] == 3.0
    assert outcomes[0]["outcome_label"] == "positive"


def test_write_trade_timing_audit_report_summarizes_outcomes(tmp_path):
    records = [
        {
            "cycle": 1,
            "timestamp": "2026-06-22T09:45:00",
            "trade_timing_scores": [
                {
                    "cycle": 1,
                    "timestamp": "2026-06-22T09:45:00",
                    "symbol": "MIDCPNIFTY",
                    "direction": "LONG",
                    "last_price": 100.0,
                    "timing_window": "TRADE_WINDOW",
                    "timing_score": 85,
                    "time_bucket": "opening_drive",
                    "edge_status": "promoted",
                }
            ],
        },
        {
            "cycle": 2,
            "timestamp": "2026-06-22T10:00:00",
            "trade_timing_scores": [
                {
                    "cycle": 2,
                    "timestamp": "2026-06-22T10:00:00",
                    "symbol": "MIDCPNIFTY",
                    "direction": "LONG",
                    "last_price": 103.0,
                    "timing_window": "TRADE_WINDOW",
                    "timing_score": 88,
                    "time_bucket": "opening_drive",
                    "edge_status": "promoted",
                }
            ],
        },
    ]

    paths = write_trade_timing_audit_report(records, output_dir=tmp_path, horizon_cycles=2)
    markdown = (tmp_path / "trade_timing_audit.md").read_text(encoding="utf-8")

    assert paths["markdown"].endswith("trade_timing_audit.md")
    assert paths["json"].endswith("trade_timing_audit.json")
    assert "Trade Timing Outcome Audit" in markdown
    assert "TRADE_WINDOW" in markdown
    assert "100.0%" in markdown


def test_collect_alert_candidates_can_require_active_only():
    config = IntradayAlertConfig(min_rr=1.3, trigger="active")
    rows = [
        _row("RELIANCE", "long active", "LONG", 3.0),
        _row("DIXON", "near trigger / watch", "SHORT", 3.0),
    ]

    candidates = collect_alert_candidates(rows, config)

    assert [item.symbol for item in candidates] == ["RELIANCE"]


def test_intraday_alert_dashboard_shows_only_alert_qualified_rows():
    config = IntradayAlertConfig(min_rr=2.0, trigger="active_or_near")
    state = LiveDashboardState(started_at=datetime(2026, 6, 19, 9, 30, 0))
    state.last_updated_at = datetime(2026, 6, 19, 9, 45, 0)
    state.cycle = 3
    state.market_context = "NIFTY flat"
    state.source_health = ["scan_symbols_intraday ok"]
    state.tracked_symbols = [
        _row("LOWRR", "long active", "LONG", 1.2),
        _row("GOOD", "long active", "LONG", 3.0),
        _row("WATCHONLY", "watch", "WATCH", 5.0),
    ]
    state.last_commentary = "LOWRR is active but should stay hidden from the alert dashboard."
    candidates = collect_alert_candidates(state.tracked_symbols, config)

    console = Console(record=True, width=180, force_terminal=False)
    console.print(render_intraday_alert_dashboard(state, candidates, candidates, config))
    output = console.export_text()

    assert "Agent Adda Intraday Alert Dashboard" in output
    assert "Alert-qualified setups" in output
    assert "GOOD" in output
    alert_section = output.split("Why No Trade - Top 5 Blocked")[0]
    assert "LOWRR" not in alert_section
    assert "WATCHONLY" not in alert_section
    assert "Why No Trade - Top 5 Blocked" in output
    assert "LOWRR" in output
    assert "WATCHONLY" in output
    assert "tracked context: 3" in output


def test_intraday_alert_dashboard_formats_options_execution_without_raw_markdown():
    config = IntradayAlertConfig(min_rr=2.0, trigger="active_or_near")
    state = LiveDashboardState(started_at=datetime(2026, 6, 22, 15, 45, 0))
    state.last_updated_at = datetime(2026, 6, 22, 15, 52, 0)
    state.cycle = 7
    state.market_context = "NIFTY flat"
    row = _row("AUBANK", "near trigger / watch", "LONG", 3.0)
    row.decision_context = {
        "final_action": "TRADE NOW",
        "decision_score": 85,
        "options_execution": {
            "status": "ok",
            "verdict": "BUY CE",
            "option_type": "CE",
            "moneyness": "ATM",
            "strike": 1050.0,
            "premium": 10.10,
            "breakeven": 1060.10,
            "expiry": "2026-06-30",
            "dte": 8,
            "iv_pct": 26.5,
            "delta": 0.36,
            "theta_per_day": -1.01,
            "expected_move": 40.51,
            "oi_wall": "CE wall 1050, 1040",
            "strategy": {
                "verdict": "LONG OPTION OK",
                "structure": "Long Call",
                "risk_mode": "defined_premium",
                "naked_buy_allowed": True,
                "management": "Use premium stop/target from the alert.",
                "reasons": ["IV acceptable"],
            },
            "reasons": [
                "\u26a0\ufe0f IV 26.5% is moderate - prefer spreads to reduce cost",
                "\u2705 IV rank 26% - historically cheap",
            ],
        },
    }
    state.tracked_symbols = [row]
    candidates = collect_alert_candidates(state.tracked_symbols, config)

    console = Console(record=True, width=100, force_terminal=False)
    console.print(render_intraday_alert_dashboard(state, candidates, [], config))
    output = console.export_text()

    assert "Options Execution" in output
    assert "BUY CE" in output
    assert "Long Call" in output
    assert "AUBANK" in output
    assert "|---|" not in output
    assert "| Symbol | Verdict" not in output


def test_near_trigger_candidate_is_worded_as_watch_not_active_long():
    item = AlertCandidate(
        symbol="NHPC",
        side="LONG",
        status="near trigger / watch",
        last_price=75.22,
        pct_change=-0.9,
        trigger=75.30,
        stop=75.20,
        target=75.68,
        rr=3.8,
        strategy="MTF breakout levels",
        note="last 30m breakout watch",
    )

    line = _candidate_action_line(item)

    assert "watch only; wait for break and 5m hold above trigger 75.30" in line
    assert "hold above trigger 75.30" not in line.replace("wait for break and 5m hold above trigger 75.30", "")
    assert _candidate_subject_label(item) == "NHPC LONG WATCH"


def test_candidate_action_line_includes_trade_timing_when_available():
    item = AlertCandidate(
        symbol="MIDCPNIFTY",
        side="LONG",
        status="near trigger / watch",
        last_price=14635.0,
        pct_change=0.6,
        trigger=14637.0,
        stop=14527.0,
        target=14750.0,
        rr=2.0,
        strategy="ORB + VWAP",
        note="promoted edge",
        decision={
            "final_action": "WAIT FOR RETEST",
            "options_suitability": "Option Buy OK",
            "decision_score": 69,
            "trade_timing": {
                "window": "RETEST_WINDOW",
                "score": 70,
                "time_bucket": "opening_drive",
            },
        },
    )

    line = _candidate_action_line(item)

    assert "Timing RETEST_WINDOW 70/opening_drive" in line


def test_collect_sharp_movers_classifies_large_moves_with_mtf_context():
    falling = _row("HINDALCO", "near trigger / watch", "SHORT", 2.5)
    falling.pct_change = -3.1
    falling.last_price = 982.2
    falling.mtf_levels = {"support": 982.3, "breakout": 997.9, "breakdown_target": 970.0}
    rising = _row("ABCAPITAL", "near trigger / watch", "LONG", 2.1)
    rising.pct_change = 2.4
    rising.last_price = 391.2
    rising.mtf_levels = {"support": 386.3, "breakout": 390.0, "target": 394.4}
    normal = _row("TRENT", "near trigger / watch", "SHORT", 4.0)
    normal.pct_change = -1.4

    movers = collect_sharp_movers([falling, rising, normal])

    assert [item["symbol"] for item in movers] == ["HINDALCO", "ABCAPITAL"]
    assert movers[0]["move"] == "Sharp Fall"
    assert movers[0]["level_state"] == "breaking support"
    assert movers[0]["reference_level"] == 982.3
    assert movers[1]["move"] == "Sharp Rise"
    assert movers[1]["level_state"] == "breaking resistance"
    assert movers[1]["reference_level"] == 390.0


def test_sharp_movers_render_in_dashboard_snapshot_and_email(tmp_path):
    config = IntradayAlertConfig(min_rr=2.0, trigger="active_or_near")
    state = LiveDashboardState(started_at=datetime(2026, 6, 23, 13, 10, 0))
    state.last_updated_at = datetime(2026, 6, 23, 13, 10, 17)
    state.cycle = 3
    state.market_context = "NIFTY weak"
    row = _row("HINDALCO", "near trigger / watch", "SHORT", 2.5)
    row.pct_change = -3.1
    row.last_price = 982.2
    row.mtf_levels = {"support": 982.3, "breakout": 997.9, "breakdown_target": 970.0}
    state.tracked_symbols = [row]

    console = Console(record=True, width=180, force_terminal=False)
    console.print(render_intraday_alert_dashboard(state, [], [], config))
    output = console.export_text()
    assert "Sharp Movers" in output
    assert "HINDALCO" in output
    assert "Sharp Fall" in output

    snapshot_path = write_intraday_latest_snapshot(
        state=state,
        candidates=[],
        fresh_candidates=[],
        email_result=None,
        path=tmp_path / "latest.md",
    )
    snapshot = snapshot_path.read_text(encoding="utf-8")
    assert "## Sharp Movers" in snapshot
    assert "breaking support" in snapshot

    html = build_alert_email_body(
        [],
        market_context=state.market_context,
        commentary="No fresh trade from the scanner.",
        as_of=state.last_updated_at,
        state=state,
    )
    assert "Sharp Movers" in html
    assert "HINDALCO" in html
    assert "Sharp Fall" in html
    assert "breaking support" in html

    section = build_sharp_movers_section(state.tracked_symbols)
    assert "Sharp Fall" in section


def test_trading_stance_waits_when_no_candidates_and_timing_blocks_trade():
    config = IntradayAlertConfig(min_rr=2.0, trigger="active_or_near")
    state = LiveDashboardState(started_at=datetime(2026, 6, 22, 9, 30, 0))
    state.market_context = "NIFTY 24,165 +0.63%, BANKNIFTY 57,877 +0.33%, VIX 12.90 -0.53%, breadth 528A/222D"
    row = _row("BDL", "near trigger / watch", "LONG", 1.8)
    row.decision_context = {
        "final_action": "WAIT FOR RETEST",
        "options_suitability": "Option Buy OK",
        "decision_score": 74,
        "reasons": ["near trigger only", "volume not confirmed"],
        "trade_timing": {
            "window": "NO_TRADE_WINDOW",
            "score": 36,
            "time_bucket": "late_morning",
            "reasons": ["late-morning timing", "near trigger", "R:R >= 2"],
        },
    }
    state.tracked_symbols = [row]

    stance = build_trading_stance(
        state=state,
        candidates=[],
        fresh_candidates=[],
        config=config,
    )

    assert stance["label"] == "WAIT"
    assert stance["headline"] == "Wait; do not force trades right now."
    assert "Fresh alerts: 0" in stance["reasons"]
    assert "Alert candidates: 0" in stance["reasons"]
    assert "late_morning / NO_TRADE_WINDOW" in stance["reasons"]
    assert "volume confirmation missing" in stance["reasons"]


def test_latest_snapshot_includes_trading_stance(tmp_path):
    state = LiveDashboardState(started_at=datetime(2026, 6, 22, 9, 30, 0))
    state.last_updated_at = datetime(2026, 6, 22, 10, 59, 38)
    state.cycle = 8
    state.market_context = "NIFTY 24,165 +0.63%, BANKNIFTY 57,877 +0.33%, VIX 12.90 -0.53%, breadth 528A/222D"
    state.source_health = ["scan_symbols_intraday ok"]
    row = _row("BDL", "near trigger / watch", "LONG", 1.8)
    row.decision_context = {
        "final_action": "WAIT FOR RETEST",
        "options_suitability": "Option Buy OK",
        "decision_score": 74,
        "reasons": ["volume not confirmed"],
        "trade_timing": {
            "window": "NO_TRADE_WINDOW",
            "score": 36,
            "time_bucket": "late_morning",
            "reasons": ["late-morning timing"],
        },
    }
    state.tracked_symbols = [row]

    path = write_intraday_latest_snapshot(
        state=state,
        candidates=[],
        fresh_candidates=[],
        email_result=None,
        path=tmp_path / "latest.md",
    )

    markdown = path.read_text(encoding="utf-8")
    assert "## Trading Stance" in markdown
    assert "- Stance: WAIT" in markdown
    assert "Wait; do not force trades right now." in markdown
    assert "late_morning / NO_TRADE_WINDOW" in markdown


def test_latest_snapshot_includes_top_blocked_no_trade_rows(tmp_path):
    config = IntradayAlertConfig(min_rr=1.3, trigger="active_or_near")
    state = LiveDashboardState(started_at=datetime(2026, 6, 25, 10, 50, 0))
    state.last_updated_at = datetime(2026, 6, 25, 11, 0, 0)
    state.cycle = 18
    state.market_context = "NIFTY green"
    row = _row("HINDALCO", "T1 hit / trail", "SHORT", 0.36)
    row.last_price = 956.0
    row.trigger = 959.2
    row.invalidation = 965.6
    row.target1 = 956.9
    row.decision_context = {
        "final_action": "AVOID",
        "options_suitability": "No Trade",
        "decision_score": 3,
        "reasons": ["volume not confirmed", "F&O bearish"],
        "trade_timing": {
            "window": "NO_TRADE_WINDOW",
            "time_bucket": "late_morning",
            "reasons": ["R:R weak"],
        },
    }
    state.tracked_symbols = [row]

    path = write_intraday_latest_snapshot(
        state=state,
        candidates=[],
        fresh_candidates=[],
        email_result=None,
        path=tmp_path / "latest.md",
        config=config,
    )

    markdown = path.read_text(encoding="utf-8")
    assert "## Why No Trade - Top 5 Blocked" in markdown
    assert "HINDALCO" in markdown
    assert "R:R 0.4 &lt; min 1.3" not in markdown
    assert "R:R 0.4 < min 1.3" in markdown
    assert "volume not confirmed" in markdown
    assert "late_morning / NO_TRADE_WINDOW" in markdown


def test_intraday_alert_dashboard_shows_trading_stance_when_waiting():
    config = IntradayAlertConfig(min_rr=2.0, trigger="active_or_near")
    state = LiveDashboardState(started_at=datetime(2026, 6, 22, 9, 30, 0))
    state.last_updated_at = datetime(2026, 6, 22, 10, 59, 38)
    state.cycle = 8
    state.market_context = "NIFTY 24,165 +0.63%, BANKNIFTY 57,877 +0.33%, VIX 12.90 -0.53%, breadth 528A/222D"
    state.source_health = ["scan_symbols_intraday ok"]
    row = _row("BDL", "near trigger / watch", "LONG", 1.8)
    row.decision_context = {
        "final_action": "WAIT FOR RETEST",
        "options_suitability": "Option Buy OK",
        "decision_score": 74,
        "reasons": ["volume not confirmed"],
        "trade_timing": {
            "window": "NO_TRADE_WINDOW",
            "score": 36,
            "time_bucket": "late_morning",
            "reasons": ["late-morning timing"],
        },
    }
    state.tracked_symbols = [row]

    console = Console(record=True, width=180, force_terminal=False)
    console.print(render_intraday_alert_dashboard(state, [], [], config))
    output = console.export_text()

    assert "Trading Stance" in output
    assert "WAIT" in output
    assert "Wait; do not force trades right now." in output
    assert "volume confirmation missing" in output
    assert "Why No Trade - Top 5 Blocked" in output
    assert "BDL" in output
    assert "volume not confirmed" in output


def test_build_alert_email_body_includes_levels_and_commentary():
    state = LiveDashboardState(started_at=datetime(2026, 6, 18, 9, 30, 0))
    state.cycle = 7
    state.market_context = "NIFTY flat, BANKNIFTY green"
    state.source_health = ["get_live_market_overview ok", "scan_symbols_intraday ok"]
    state.tracked_symbols = [
        TrackedSymbolState(
            symbol="BEL",
            last_price=424.2,
            pct_change=1.0,
            direction="SHORT",
            status="short active",
            trigger=424.2,
            invalidation=426.63,
            target1=420.96,
            rr=1.33,
            strategy="RSI Reversal",
            note="deeply overbought",
        )
    ]
    state.cycle_changes = {
        "new_added": [{"symbol": "BEL"}],
        "removed": [],
        "forming": [],
        "confirmed": [],
        "active": [{"symbol": "BEL"}],
        "status_changes": [{"symbol": "BEL", "from": "watch", "to": "short active"}],
    }
    state.last_commentary = "Current read from the tracker\nBEL short active\nWatch invalidation."
    body = build_alert_email_body(
        [
            AlertCandidate(
                symbol="BEL",
                side="SHORT",
                status="short active",
                last_price=424.2,
                pct_change=1.0,
                trigger=424.2,
                stop=426.63,
                target=420.96,
                rr=1.33,
                strategy="RSI Reversal",
                note="deeply overbought",
            )
        ],
        market_context="NIFTY flat, BANKNIFTY green",
        commentary="BEL short active\nWatch invalidation.",
        as_of=datetime(2026, 6, 18, 9, 45, 0),
        state=state,
    )

    assert "Agent Adda Intraday Live Commentary" in body
    assert "Agent Adda Intraday Live Commentary Dashboard" not in body
    assert 'width="760"' in body
    assert "max-width:760px" in body
    assert "min-width:1280px" not in body
    assert "white-space:nowrap" in body
    assert "Current Read From The Tracker" in body
    assert "Cycle Changes" in body
    assert "Narrative / Commentary" in body
    assert "Source Health" in body
    assert "Priority Queue" in body
    assert "Active Trades" in body
    assert "Near Trigger / Watch" in body
    assert "Risk Rules" in body
    assert "Fresh alerts: 1" in body
    assert "S-ACTIVE" in body
    assert "BEL watch -&gt; short active" in body
    assert "get_live_market_overview ok | scan_symbols_intraday ok" in body
    assert "BEL" in body
    assert "SHORT" in body
    assert "426.63" in body
    assert "Watch invalidation" in body


def test_build_alert_email_body_includes_trading_stance_when_waiting():
    state = LiveDashboardState(started_at=datetime(2026, 6, 22, 9, 30, 0))
    state.cycle = 8
    state.market_context = "NIFTY 24,165 +0.63%, BANKNIFTY 57,877 +0.33%, VIX 12.90 -0.53%, breadth 528A/222D"
    row = _row("BDL", "near trigger / watch", "LONG", 1.8)
    row.decision_context = {
        "final_action": "WAIT FOR RETEST",
        "options_suitability": "Option Buy OK",
        "decision_score": 74,
        "reasons": ["volume not confirmed"],
        "trade_timing": {
            "window": "NO_TRADE_WINDOW",
            "score": 36,
            "time_bucket": "late_morning",
            "reasons": ["late-morning timing"],
        },
    }
    state.tracked_symbols = [row]

    body = build_alert_email_body(
        [],
        market_context=state.market_context,
        commentary="No fresh trade from the scanner.",
        as_of=datetime(2026, 6, 22, 10, 59, 38),
        state=state,
    )

    assert "Trading Stance" in body
    assert "WAIT" in body
    assert "Wait; do not force trades right now." in body
    assert "volume confirmation missing" in body


def test_build_alert_email_body_includes_scheduled_cadence():
    body = build_alert_email_body(
        [
            AlertCandidate(
                symbol="CDSL",
                side="LONG",
                status="long active",
                last_price=1373.5,
                pct_change=6.4,
                trigger=1382.0,
                stop=1364.8,
                target=1398.0,
                rr=1.6,
                strategy="Supertrend + VWAP",
                note="RSI hot",
            )
        ],
        market_context="NIFTY green",
        commentary="CDSL is extended; prefer retest.",
        as_of=datetime(2026, 6, 18, 10, 45, 0),
        email_every_mins=15,
    )

    assert "15-minute scheduled update" in body
    assert "CDSL is extended" in body


def test_build_email_commentary_replaces_placeholder_with_candidate_read():
    commentary = build_email_commentary(
        [
            AlertCandidate(
                symbol="POWERINDIA",
                side="LONG",
                status="long active",
                last_price=36020.0,
                pct_change=1.2,
                trigger=36040.0,
                stop=35831.67,
                target=36161.67,
                rr=2.1,
                strategy="Multi-Confirm",
                note="breakout hold",
            )
        ],
        market_context="NIFTY flat",
        commentary="commentary",
    )

    assert "Current read from the tracker" in commentary
    assert "POWERINDIA: LONG long active" in commentary
    assert "invalidation 35,832" in commentary
    assert commentary.strip().lower() != "commentary"


def test_alert_email_body_does_not_render_placeholder_commentary():
    body = build_alert_email_body(
        [
            AlertCandidate(
                symbol="POWERINDIA",
                side="LONG",
                status="long active",
                last_price=36020.0,
                pct_change=1.2,
                trigger=36040.0,
                stop=35831.67,
                target=36161.67,
                rr=2.1,
                strategy="Multi-Confirm",
                note="breakout hold",
            )
        ],
        market_context="NIFTY flat",
        commentary="commentary",
        as_of=datetime(2026, 6, 18, 15, 28, 3),
    )

    assert "State-Machine Commentary" in body
    assert "POWERINDIA: LONG long active" in body
    assert "<br>        commentary" not in body


def test_alert_email_body_renders_markdown_commentary_cleanly():
    body = build_alert_email_body(
        [],
        market_context="NIFTY flat",
        commentary=(
            "### Current read from the tracker\n\n"
            "**Cycle changes**\n\n"
            "----------------------------------------------------------------\n\n"
            "- **BEL** near trigger `429`\n"
            "• DIXON watch, RR 3.96\n\n"
            "Watch next"
        ),
        as_of=datetime(2026, 6, 18, 15, 28, 3),
    )

    assert "###" not in body
    assert "**" not in body
    assert "----------------------------------------------------------------" not in body
    assert "<b>BEL</b> near trigger" in body
    assert "&bull;" in body
    assert "DIXON watch, RR 3.96" in body
    assert "Watch next" in body


def test_dispatch_alert_email_reports_send_failure_without_raising(monkeypatch):
    state = LiveDashboardState(started_at=datetime(2026, 6, 23, 13, 10, 0))
    state.market_context = "NIFTY weak"
    state.last_commentary = "TRENT short watch"
    state.last_updated_at = datetime(2026, 6, 23, 13, 10, 17)
    candidate = AlertCandidate(
        symbol="TRENT",
        side="SHORT",
        status="near trigger / watch",
        last_price=3159.0,
        pct_change=-0.7,
        trigger=3155.0,
        stop=3168.0,
        target=3105.0,
        rr=4.0,
        strategy="MTF breakdown levels",
        note="below support",
        decision={"final_action": "WAIT FOR RETEST"},
    )

    monkeypatch.setattr(
        "terminal.live_intraday_alerts._load_recipients",
        lambda _key: {"to": ["pgorai@example.com"], "bcc": []},
    )

    def fail_send(**_kwargs):
        raise RuntimeError("Outlook AppleScript failed")

    monkeypatch.setattr("terminal.live_intraday_alerts.send_via_outlook", fail_send)

    result = dispatch_alert_email(
        [candidate],
        state=state,
        config=IntradayAlertConfig(send=True, email_every_mins=30),
    )

    assert result["ok"] is False
    assert "email dispatch failed" in result["message"]
    assert "Outlook AppleScript failed" in result["message"]
    assert result["subject"] == "Agent Adda Intraday F&O Alert: TRENT SHORT WATCH"


def test_email_delivery_confirmation_names_successful_send():
    line = _email_delivery_confirmation(
        {
            "ok": True,
            "message": "sent",
            "subject": "Agent Adda Intraday F&O Alert: TRENT SHORT WATCH",
        },
        IntradayAlertConfig(send=True, dry_run=False),
    )

    assert line == "Email sent successfully: Agent Adda Intraday F&O Alert: TRENT SHORT WATCH"


def test_intraday_alert_config_accepts_email_cadence_flag():
    parser = build_arg_parser()
    args = parser.parse_args(["--email-every-mins", "15", "--no-llm"])
    config = config_from_args(args)

    assert config.email_every_mins == 15
    assert config.use_llm is False
    assert config.strategies == DEFAULT_BREAKOUT_STRATEGIES
    assert "orb_vwap" in config.strategies
    assert config.require_volume is True
    assert config.min_volume_ratio == 1.2


def test_intraday_alert_config_defaults_to_15_minute_email_cadence():
    parser = build_arg_parser()
    args = parser.parse_args(["--no-llm"])
    config = config_from_args(args)

    assert config.email_every_mins == 15


def test_intraday_alert_defaults_include_orb_vwap_after_research():
    assert "orb_vwap" in DEFAULT_BREAKOUT_STRATEGIES


def test_active_intraday_strategies_keeps_orb_vwap_during_opening_drive():
    strategies = ["supertrend_breakout", "orb_vwap", "vcp"]

    active = _active_intraday_strategies(strategies, as_of=datetime(2026, 6, 22, 9, 45))

    assert active == strategies


def test_active_intraday_strategies_suppresses_orb_vwap_after_opening_drive():
    strategies = ["supertrend_breakout", "orb_vwap", "vcp"]

    active = _active_intraday_strategies(strategies, as_of=datetime(2026, 6, 22, 15, 5))

    assert active == ["supertrend_breakout", "vcp"]


def test_intraday_alert_config_accepts_strategy_override():
    parser = build_arg_parser()
    args = parser.parse_args(["--strategies", "darvas,supertrend_breakout,vcp", "--no-llm"])
    config = config_from_args(args)

    assert config.strategies == ["darvas", "supertrend_breakout", "vcp"]


def test_intraday_alert_config_accepts_volume_override():
    parser = build_arg_parser()
    args = parser.parse_args(["--min-volume-ratio", "1.5", "--allow-no-volume", "--no-llm"])
    config = config_from_args(args)

    assert config.min_volume_ratio == 1.5
    assert config.require_volume is False


def test_intraday_alert_config_accepts_no_fno_flag():
    parser = build_arg_parser()
    args = parser.parse_args(["--no-fno", "--no-llm"])
    config = config_from_args(args)

    assert config.include_fno is False


def test_email_cadence_due_helper_enforces_interval():
    now = datetime(2026, 6, 18, 10, 30, 0)

    assert _is_email_cadence_due(None, now=now, every_mins=15)
    assert not _is_email_cadence_due(now - timedelta(minutes=14, seconds=59), now=now, every_mins=15)
    assert _is_email_cadence_due(now - timedelta(minutes=15), now=now, every_mins=15)
    assert not _is_email_cadence_due(None, now=now, every_mins=0)


def test_intraday_alert_symbols_are_saved_cleanly(tmp_path):
    state_path = tmp_path / "intraday_alerts_state.json"

    save_intraday_alert_symbols(["bankbaroda", "CDSL", "cdsl", " "], state_path)

    assert load_intraday_alert_symbols(state_path) == ["BANKBARODA", "CDSL"]


def test_config_from_args_remembers_provided_symbols(tmp_path):
    state_path = tmp_path / "intraday_alerts_state.json"
    parser = build_arg_parser()
    args = parser.parse_args([
        "--symbols",
        "bankbaroda,CDSL",
        "--state-path",
        str(state_path),
        "--no-llm",
    ])

    config = config_from_args(args)

    assert config.symbols == ["BANKBARODA", "CDSL"]
    assert load_intraday_alert_symbols(state_path) == ["BANKBARODA", "CDSL"]


def test_config_from_args_reuses_remembered_symbols_by_default(tmp_path):
    state_path = tmp_path / "intraday_alerts_state.json"
    save_intraday_alert_symbols(["BEL", "TRENT"], state_path)
    parser = build_arg_parser()
    args = parser.parse_args(["--state-path", str(state_path), "--no-llm"])

    config = config_from_args(args)

    assert config.symbols == ["BEL", "TRENT"]


def test_config_from_args_filters_index_underlyings_from_auto_universe(tmp_path, monkeypatch):
    state_path = tmp_path / "intraday_alerts_state.json"
    monkeypatch.setattr(
        "terminal.live_intraday_alerts.load_fno_intraday_universe",
        lambda: ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "INFY", "HCLTECH"],
    )
    parser = build_arg_parser()
    args = parser.parse_args(["--state-path", str(state_path), "--no-llm"])

    config = config_from_args(args)

    assert config.symbols == ["INFY", "HCLTECH"]


def test_config_from_args_filters_index_underlyings_from_remembered_auto_basket(tmp_path):
    state_path = tmp_path / "intraday_alerts_state.json"
    save_intraday_alert_symbols(["NIFTY", "BEL", "BANKNIFTY", "TRENT"], state_path)
    parser = build_arg_parser()
    args = parser.parse_args(["--state-path", str(state_path), "--no-llm"])

    config = config_from_args(args)

    assert config.symbols == ["BEL", "TRENT"]


def test_config_from_args_keeps_explicit_index_symbols(tmp_path):
    state_path = tmp_path / "intraday_alerts_state.json"
    parser = build_arg_parser()
    args = parser.parse_args([
        "--symbols",
        "NIFTY,BANKNIFTY,INFY",
        "--state-path",
        str(state_path),
        "--no-remember-symbols",
        "--no-llm",
    ])

    config = config_from_args(args)

    assert config.symbols == ["NIFTY", "BANKNIFTY", "INFY"]


def test_config_from_args_can_skip_symbol_memory_update(tmp_path):
    state_path = tmp_path / "intraday_alerts_state.json"
    parser = build_arg_parser()
    args = parser.parse_args([
        "--symbols",
        "BEL,CDSL",
        "--state-path",
        str(state_path),
        "--no-remember-symbols",
        "--no-llm",
    ])

    config = config_from_args(args)

    assert config.symbols == ["BEL", "CDSL"]
    assert load_intraday_alert_symbols(state_path) == []


def test_select_tracking_rows_prioritizes_best_actionable_names():
    config = IntradayAlertConfig(min_rr=1.5, max_tracked_symbols=2)
    rows = [
        _row("LOWRR", "long active", "LONG", 1.0),
        _row("WATCH", "watch", "WATCH", 5.0),
        _row("ACTIVE", "long active", "LONG", 2.0),
        _row("NEAR", "near trigger / watch", "SHORT", 3.0),
    ]

    selected = select_tracking_rows(rows, config)

    assert [row.symbol for row in selected] == ["ACTIVE", "NEAR"]


def test_select_tracking_rows_uses_fno_alignment_when_available():
    config = IntradayAlertConfig(min_rr=1.5, max_tracked_symbols=2, include_fno=True)
    bullish = _row("BULLFNO", "long active", "LONG", 2.0)
    bullish.fno_context = {"bias": "bullish", "pcr": 1.2, "basis": 1.0}
    sideways = _row("SIDEWAYS", "long active", "LONG", 2.0)
    sideways.fno_context = {"bias": "sideways", "pcr": 0.9, "basis": 0.2}
    bearish = _row("BEARFNO", "long active", "LONG", 2.0)
    bearish.fno_context = {"bias": "bearish", "pcr": 0.6, "basis": -1.0}

    selected = select_tracking_rows([bearish, sideways, bullish], config)

    assert [row.symbol for row in selected] == ["BULLFNO", "SIDEWAYS"]


def test_intraday_loop_skips_analysis_and_email_when_market_closed(monkeypatch):
    closed_status = market_session_status(datetime(2026, 5, 11, 8, 45, 0))

    monkeypatch.setattr(
        "terminal.live_intraday_alerts.market_session_status",
        lambda _now=None: closed_status,
        raising=False,
    )
    monkeypatch.setattr(
        "terminal.live_intraday_alerts.load_edge_memory_rows",
        lambda: (_ for _ in ()).throw(AssertionError("edge memory should not load when market is closed")),
    )
    monkeypatch.setattr(
        "terminal.live_intraday_alerts.fetch_live_dashboard_cycle",
        lambda _config: (_ for _ in ()).throw(AssertionError("live scan should not run when market is closed")),
    )
    monkeypatch.setattr(
        "terminal.live_intraday_alerts.generate_live_commentary",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("commentary analysis should not run when market is closed")),
    )
    monkeypatch.setattr(
        "terminal.live_intraday_alerts.dispatch_alert_email",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("email should not dispatch when market is closed")),
    )

    console = Console(record=True, width=160, force_terminal=False)
    state = run_intraday_alert_commentary(
        IntradayAlertConfig(
            symbols=["BEL"],
            cycles=1,
            interval_secs=1,
            use_llm=True,
            dry_run=True,
            send=True,
            email_every_mins=15,
            write_cycle_log=False,
        ),
        console=console,
    )

    output = console.export_text()
    assert state.tracked_symbols == []
    assert "NSE equity market is CLOSED" in state.market_context
    assert "Intraday alert analysis skipped" in state.last_commentary
    assert "No alert email or draft was created" in state.last_commentary
    assert "NSE equity market is CLOSED" in output
    assert "No alert email or draft was created" in output


def test_intraday_closed_market_cycle_is_logged_without_alerts(tmp_path, monkeypatch):
    closed_status = market_session_status(datetime(2026, 5, 28, 10, 30, 0))
    log_path = tmp_path / "alerts.jsonl"
    snapshot_path = tmp_path / "latest.md"

    monkeypatch.setattr(
        "terminal.live_intraday_alerts.market_session_status",
        lambda _now=None: closed_status,
        raising=False,
    )
    monkeypatch.setattr(
        "terminal.live_intraday_alerts.fetch_live_dashboard_cycle",
        lambda _config: (_ for _ in ()).throw(AssertionError("live scan should not run when market is closed")),
    )
    monkeypatch.setattr(
        "terminal.live_intraday_alerts.dispatch_alert_email",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("email should not dispatch when market is closed")),
    )

    run_intraday_alert_commentary(
        IntradayAlertConfig(
            symbols=["BEL"],
            cycles=1,
            interval_secs=1,
            use_llm=False,
            dry_run=True,
            send=True,
            email_every_mins=15,
            log_path=log_path,
            latest_snapshot_path=snapshot_path,
        )
    )

    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    snapshot = snapshot_path.read_text(encoding="utf-8")

    assert record["market_context"].startswith("NSE equity market is CLOSED")
    assert record["tracked_symbols"] == []
    assert record["alert_candidates"] == []
    assert record["fresh_alerts"] == []
    assert record["email_result"]["message"].startswith("market closed; no alert sent")
    assert record["trading_stance"]["label"] == "NO_TRADE"
    assert any("market_session closed" in item for item in record["source_health"])
    assert "NSE equity market is CLOSED" in snapshot
    assert "Intraday alert analysis skipped" in snapshot
    assert "No alert email or draft was created" in snapshot


def test_intraday_loop_full_rescans_then_tracks_selected_subset(monkeypatch):
    _patch_market_open(monkeypatch)
    scanned: list[list[str]] = []

    def fake_fetch(config):
        symbols = list(config.symbols)
        scanned.append(symbols)
        rows = [
            _row(symbol, "long active", "LONG", {"AAA": 4.0, "BBB": 3.0}.get(symbol, 1.0))
            for symbol in symbols
        ]
        return {
            "market_context": "NIFTY flat",
            "tracked_symbols": rows,
            "source_health": ["scan_symbols_intraday ok"],
        }

    monkeypatch.setattr("terminal.live_intraday_alerts.fetch_live_dashboard_cycle", fake_fetch)
    monkeypatch.setattr("terminal.live_intraday_alerts.generate_live_commentary", lambda *args, **kwargs: "commentary")
    monkeypatch.setattr("terminal.live_intraday_alerts.render_intraday_alert_dashboard", lambda *args, **kwargs: "dashboard")
    monkeypatch.setattr("terminal.live_intraday_alerts.time.sleep", lambda seconds: None)

    state = run_intraday_alert_commentary(
        IntradayAlertConfig(
            symbols=["AAA", "BBB", "CCC", "DDD"],
            cycles=2,
            interval_secs=1,
            use_llm=False,
            min_rr=99.0,
            max_tracked_symbols=2,
            email_every_mins=15,
            write_cycle_log=False,
        )
    )

    assert scanned == [["AAA", "BBB", "CCC", "DDD"], ["AAA", "BBB"]]
    assert [row.symbol for row in state.tracked_symbols] == ["AAA", "BBB"]


def test_intraday_loop_applies_fno_before_final_rescan_selection(monkeypatch):
    _patch_market_open(monkeypatch)

    def fake_fetch(config):
        return {
            "market_context": "NIFTY flat",
            "tracked_symbols": [_row(symbol, "long active", "LONG", 2.0) for symbol in config.symbols],
            "source_health": ["scan_symbols_intraday ok"],
        }

    def fake_enrich_fno(rows):
        for row in rows:
            row.fno_context = {"bias": "bullish" if row.symbol == "BBB" else "bearish"}
        return rows

    monkeypatch.setattr("terminal.live_intraday_alerts.fetch_live_dashboard_cycle", fake_fetch)
    monkeypatch.setattr("terminal.live_intraday_alerts.enrich_tracked_symbols_with_mtf_levels", lambda rows, **kwargs: rows)
    monkeypatch.setattr("terminal.live_intraday_alerts.enrich_tracked_symbols_with_fno_context", fake_enrich_fno)
    monkeypatch.setattr("terminal.live_intraday_alerts.generate_live_commentary", lambda *args, **kwargs: "commentary")
    monkeypatch.setattr("terminal.live_intraday_alerts.render_intraday_alert_dashboard", lambda *args, **kwargs: "dashboard")
    monkeypatch.setattr("terminal.live_intraday_alerts.time.sleep", lambda seconds: None)

    state = run_intraday_alert_commentary(
        IntradayAlertConfig(
            symbols=["AAA", "BBB", "CCC"],
            cycles=1,
            interval_secs=1,
            use_llm=False,
            min_rr=1.5,
            max_tracked_symbols=1,
            write_cycle_log=False,
        )
    )

    assert [row.symbol for row in state.tracked_symbols] == ["BBB"]


def test_intraday_loop_applies_edge_memory_before_candidates(monkeypatch):
    _patch_market_open(monkeypatch)

    def fake_fetch(config):
        return {
            "market_context": "NIFTY flat",
            "tracked_symbols": [_row("NIFTY", "long active", "LONG", 3.0)],
            "source_health": ["scan_symbols_intraday ok"],
        }

    monkeypatch.setattr("terminal.live_intraday_alerts.fetch_live_dashboard_cycle", fake_fetch)
    monkeypatch.setattr("terminal.live_intraday_alerts.enrich_tracked_symbols_with_mtf_levels", lambda rows, **kwargs: rows)
    monkeypatch.setattr("terminal.live_intraday_alerts.enrich_tracked_symbols_with_fno_context", lambda rows: rows)
    monkeypatch.setattr(
        "terminal.live_intraday_alerts.load_edge_memory_rows",
        lambda: [
            {
                "symbol": "NIFTY",
                "setup": "ORB + VWAP",
                "direction": "LONG",
                "timeframe": "15m",
                "status": "retired",
                "edge_role": "edge_diluter",
                "confidence": 0.51,
                "persistence_count": 2,
            }
        ],
    )
    monkeypatch.setattr("terminal.live_intraday_alerts.generate_live_commentary", lambda *args, **kwargs: "commentary")
    rendered = []

    def fake_render(state, candidates, fresh, config):
        rendered.append((state, candidates, fresh))
        return "dashboard"

    monkeypatch.setattr("terminal.live_intraday_alerts.render_intraday_alert_dashboard", fake_render)
    monkeypatch.setattr("terminal.live_intraday_alerts.time.sleep", lambda seconds: None)

    state = run_intraday_alert_commentary(
        IntradayAlertConfig(
            symbols=["NIFTY"],
            cycles=1,
            interval_secs=1,
            use_llm=False,
            write_cycle_log=False,
        )
    )

    assert rendered[0][1] == []
    assert state.tracked_symbols[0].decision_context["final_action"] == "AVOID"
    assert state.tracked_symbols[0].decision_context["edge_memory"]["status"] == "retired"
    assert any("edge_memory ok: 1" in item for item in state.source_health)


def test_load_fno_intraday_universe_includes_symbols_from_latest_cache(tmp_path, monkeypatch):
    cache = tmp_path / "_fno_cache"
    cache.mkdir()
    (cache / "fo_bhav_test.csv").write_text("<!DOCTYPE html>", encoding="utf-8")
    (cache / "fo_bhav_20260617.csv").write_text(
        "INSTRUMENT,SYMBOL,EXPIRY_DT,OPTION_TYP\n"
        "STF,CDSL,2026-06-30,\n"
        "STO,CDSL,2026-06-30,CE\n"
        "STF,RELIANCE,2026-06-30,\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("terminal.live_intraday_alerts.FNO_CACHE_DIR", cache)

    universe = load_fno_intraday_universe()

    assert "CDSL" in universe
    assert "RELIANCE" in universe


def test_intraday_cycle_log_record_is_auditable():
    state = LiveDashboardState(started_at=datetime(2026, 6, 18, 10, 0, 0))
    state.last_updated_at = datetime(2026, 6, 18, 10, 5, 0)
    state.cycle = 2
    state.market_context = "NIFTY 24,111 +0.11%, BANKNIFTY 57,780 +0.34%"
    state.source_health = ["get_live_market_overview ok", "scan_symbols_intraday ok"]
    state.tracked_symbols = [_row("CDSL", "long active", "LONG", 3.0)]
    state.tracked_symbols[0].decision_context = {
        "final_action": "TRADE NOW",
        "decision_score": 82,
        "trade_timing": {
            "score": 84,
            "window": "TRADE_WINDOW",
            "time_bucket": "opening_drive",
            "reasons": ["trigger active"],
        },
    }
    state.last_commentary = "Current read from the tracker:\n- CDSL long active"
    candidate = AlertCandidate(
        symbol="CDSL",
        side="LONG",
        status="long active",
        last_price=1346.0,
        pct_change=1.1,
        trigger=1346.0,
        stop=1287.0,
        target=1522.0,
        rr=3.0,
        strategy="Multi-Confirm",
        note="F&O breakout tracker",
    )

    record = build_intraday_cycle_log_record(
        state=state,
        candidates=[candidate],
        fresh_candidates=[candidate],
        email_result={"ok": True, "message": "dry-run", "subject": "CDSL LONG"},
        config=IntradayAlertConfig(symbols=["CDSL"], dry_run=True, use_llm=False),
    )

    assert record["event"] == "intraday_alert_cycle"
    assert record["cycle"] == 2
    assert record["config"]["symbols_count"] == 1
    assert record["config"]["email_every_mins"] == 0
    assert record["config"]["strategies"] == DEFAULT_BREAKOUT_STRATEGIES
    assert record["config"]["require_volume"] is True
    assert record["config"]["min_volume_ratio"] == 1.2
    assert record["config"]["include_fno"] is True
    assert record["tracked_symbols"][0]["symbol"] == "CDSL"
    assert record["trade_timing_scores"][0]["symbol"] == "CDSL"
    assert record["trade_timing_scores"][0]["timing_window"] == "TRADE_WINDOW"
    assert record["fresh_alerts"][0]["rr"] == 3.0
    assert record["email_result"]["subject"] == "CDSL LONG"


def test_intraday_cycle_log_and_latest_snapshot_are_written(tmp_path):
    state = LiveDashboardState(started_at=datetime(2026, 6, 18, 10, 0, 0))
    state.last_updated_at = datetime(2026, 6, 18, 10, 5, 0)
    state.cycle = 1
    state.market_context = "NIFTY flat"
    state.source_health = ["get_nse_quotes ok"]
    state.tracked_symbols = [_row("BEL", "short active", "SHORT", 2.5)]
    state.tracked_symbols[0].decision_context = {
        "final_action": "TRADE NOW",
        "options_suitability": "Option Buy OK",
        "decision_score": 78,
        "edge_memory": {
            "status": "promoted",
            "edge_role": "core_carrier",
            "setup": "ORB + VWAP",
            "confidence": 0.84,
            "persistence_count": 2,
        },
        "trade_timing": {
            "score": 85,
            "window": "TRADE_WINDOW",
            "time_bucket": "opening_drive",
            "reasons": ["promoted edge", "opening-drive timing"],
        },
    }
    state.last_commentary = "BEL short active"
    candidate = AlertCandidate(
        symbol="BEL",
        side="SHORT",
        status="short active",
        last_price=424.2,
        pct_change=1.0,
        trigger=424.2,
        stop=426.6,
        target=420.9,
        rr=2.5,
        strategy="Retest",
        note="weak below trigger",
    )
    record = build_intraday_cycle_log_record(
        state=state,
        candidates=[candidate],
        fresh_candidates=[candidate],
        email_result=None,
        config=IntradayAlertConfig(symbols=["BEL"], use_llm=False),
    )

    log_path = write_intraday_cycle_log(record, tmp_path / "alerts.jsonl")
    snapshot_path = write_intraday_latest_snapshot(
        state=state,
        candidates=[candidate],
        fresh_candidates=[candidate],
        email_result=None,
        path=tmp_path / "latest.md",
    )

    assert log_path.read_text(encoding="utf-8").count("intraday_alert_cycle") == 1
    snapshot = snapshot_path.read_text(encoding="utf-8")
    assert "Cycle Changes" in snapshot
    assert "Fresh Alerts" in snapshot
    assert "Edge Memory" in snapshot
    assert "Trade Timing" in snapshot
    assert "TRADE_WINDOW" in snapshot
    assert "opening_drive" in snapshot
    assert "promoted" in snapshot
    assert "BEL" in snapshot
    assert "BEL short active" in snapshot


def test_options_execution_verdict_maps_long_setup_to_ce_buy():
    row = _row("INFY", "long active", "LONG", 2.5)
    row.fno_context = {"status": "ok", "bias": "bullish", "pcr": 1.2, "basis": 1.5, "max_pain": 1040}
    row.decision_context = {"final_action": "TRADE NOW", "decision_score": 78}

    def fake_analyzer(symbol, direction):
        assert symbol == "INFY"
        assert direction == "bullish"
        return {
            "symbol": "INFY",
            "underlying": 1051.4,
            "expiry": "2026-06-30",
            "dte": 8,
            "verdict": {"label": "GOOD BUYING OPPORTUNITY", "score": 5, "reasons": ["IV fair"]},
            "strike_guide": {
                "option_type": "CE",
                "atm_iv": 18.5,
                "expected_move": {"expected_move_1sd": 52.0, "upper_1sd": 1103.4, "lower_1sd": 999.4},
            },
            "recommended_strikes": [
                {
                    "label": "ATM",
                    "strike": 1050.0,
                    "option_type": "CE",
                    "ltp": 22.4,
                    "breakeven": 1072.4,
                    "delta": 0.51,
                    "theta_per_day": -1.2,
                    "vs_expected_move": "Breakeven inside 1sd",
                }
            ],
            "oi_context": {
                "resistance_walls": [{"strike": 1100.0, "ce_oi": 500000, "ce_ltp": 3.5}],
                "note": "Call OI above spot = resistance.",
            },
        }

    apply_options_execution_to_tracked_symbols([row], analyzer=fake_analyzer)

    verdict = row.decision_context["options_execution"]
    assert verdict["verdict"] == "BUY CE"
    assert verdict["strategy"]["structure"] == "Long Call"
    assert verdict["strategy"]["verdict"] == "LONG OPTION OK"
    assert verdict["option_type"] == "CE"
    assert verdict["strike"] == 1050.0
    assert verdict["premium"] == 22.4
    assert verdict["breakeven"] == 1072.4
    assert verdict["dte"] == 8
    assert verdict["iv_pct"] == 18.5
    assert "1100" in verdict["oi_wall"]


def test_options_execution_marks_missing_fno_as_no_options_trade():
    row = _row("THANGAMAYL", "near trigger / watch", "LONG", 4.4)
    row.fno_context = {"status": "missing", "missing_evidence": ["option_chain", "futures"]}
    row.decision_context = {"final_action": "WAIT FOR RETEST", "decision_score": 48}

    apply_options_execution_to_tracked_symbols([row], analyzer=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not call analyzer")))

    verdict = row.decision_context["options_execution"]
    assert verdict["verdict"] == "NO OPTIONS TRADE"
    assert verdict["status"] == "missing_evidence"
    assert "option_chain" in "; ".join(verdict["reasons"])


def test_latest_snapshot_and_email_render_options_execution_section(tmp_path):
    state = LiveDashboardState(started_at=datetime(2026, 6, 22, 9, 30, 0))
    state.last_updated_at = datetime(2026, 6, 22, 10, 5, 0)
    state.cycle = 1
    state.market_context = "NIFTY flat"
    row = _row("INFY", "long active", "LONG", 2.5)
    row.decision_context = {
        "final_action": "TRADE NOW",
        "decision_score": 78,
        "options_execution": {
            "status": "ok",
            "verdict": "BUY CE",
            "option_type": "CE",
            "strike": 1050.0,
            "premium": 22.4,
            "breakeven": 1072.4,
            "expiry": "2026-06-30",
            "dte": 8,
            "iv_pct": 18.5,
            "theta_per_day": -1.2,
            "delta": 0.51,
            "expected_move": 52.0,
            "oi_wall": "CE wall 1100",
            "strategy": {
                "verdict": "LONG OPTION OK",
                "structure": "Long Call",
                "risk_mode": "defined_premium",
                "naked_buy_allowed": True,
                "reasons": ["cash-settled index option"],
                "management": "Use premium stop/target from the alert.",
            },
            "reasons": ["IV fair", "ATM strike selected"],
        },
    }
    state.tracked_symbols = [row]
    candidate = AlertCandidate(
        symbol="INFY",
        side="LONG",
        status="long active",
        last_price=1051.4,
        pct_change=1.2,
        trigger=1051.4,
        stop=1038.0,
        target=1080.0,
        rr=2.5,
        strategy="MTF breakout",
        note="holds above trigger",
        decision=row.decision_context,
    )

    snapshot_path = write_intraday_latest_snapshot(
        state=state,
        candidates=[candidate],
        fresh_candidates=[candidate],
        email_result=None,
        path=tmp_path / "latest.md",
    )
    snapshot = snapshot_path.read_text(encoding="utf-8")
    assert "## Options Execution" in snapshot
    assert "BUY CE" in snapshot
    assert "Long Call" in snapshot
    assert "1,050" in snapshot
    assert "CE wall 1100" in snapshot

    html = build_alert_email_body(
        [candidate],
        market_context=state.market_context,
        commentary="INFY long active",
        as_of=state.last_updated_at,
        state=state,
    )
    assert "Options Execution" in html
    assert "BUY CE" in html
    assert "Long Call" in html
    assert "1,050" in html

    section = build_options_execution_section(state.tracked_symbols)
    assert "BUY CE" in section
    assert "Long Call" in section
