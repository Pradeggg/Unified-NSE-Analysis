from __future__ import annotations

from datetime import datetime
from datetime import timedelta

from rich.console import Console

from terminal.live_dashboard import LiveDashboardState, TrackedSymbolState
from terminal.live_intraday_alerts import (
    AlertCandidate,
    DEFAULT_BREAKOUT_STRATEGIES,
    IntradayAlertConfig,
    build_intraday_cycle_log_record,
    build_alert_email_body,
    build_email_commentary,
    collect_alert_candidates,
    config_from_args,
    build_arg_parser,
    _is_email_cadence_due,
    load_intraday_alert_symbols,
    load_fno_intraday_universe,
    render_intraday_alert_dashboard,
    save_intraday_alert_symbols,
    select_tracking_rows,
    write_intraday_cycle_log,
    write_intraday_latest_snapshot,
    run_intraday_alert_commentary,
    _candidate_action_line,
    _candidate_subject_label,
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
    assert "LOWRR" not in output
    assert "WATCHONLY" not in output
    assert "tracked context: 3" in output


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
    assert "Agent Adda Intraday Live Commentary Dashboard" in body
    assert 'width="1280"' in body
    assert "max-width:1280px" in body
    assert "min-width:1280px" in body
    assert "white-space:nowrap" in body
    assert "Current Read From The Tracker" in body
    assert "Cycle Changes" in body
    assert "Narrative / Commentary" in body
    assert "Source Health" in body
    assert "Priority Queue" in body
    assert "Active Trades" in body
    assert "Near Trigger / Watch" in body
    assert "Risk Rules" in body
    assert "S-ACTIVE" in body
    assert "BEL watch -&gt; short active" in body
    assert "get_live_market_overview ok | scan_symbols_intraday ok" in body
    assert "BEL" in body
    assert "SHORT" in body
    assert "426.63" in body
    assert "Watch invalidation" in body


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


def test_intraday_alert_config_accepts_email_cadence_flag():
    parser = build_arg_parser()
    args = parser.parse_args(["--email-every-mins", "15", "--no-llm"])
    config = config_from_args(args)

    assert config.email_every_mins == 15
    assert config.use_llm is False
    assert config.strategies == DEFAULT_BREAKOUT_STRATEGIES
    assert config.require_volume is True
    assert config.min_volume_ratio == 1.2


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


def test_intraday_loop_full_rescans_then_tracks_selected_subset(monkeypatch):
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
    assert record["fresh_alerts"][0]["rr"] == 3.0
    assert record["email_result"]["subject"] == "CDSL LONG"


def test_intraday_cycle_log_and_latest_snapshot_are_written(tmp_path):
    state = LiveDashboardState(started_at=datetime(2026, 6, 18, 10, 0, 0))
    state.last_updated_at = datetime(2026, 6, 18, 10, 5, 0)
    state.cycle = 1
    state.market_context = "NIFTY flat"
    state.source_health = ["get_nse_quotes ok"]
    state.tracked_symbols = [_row("BEL", "short active", "SHORT", 2.5)]
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
    assert "BEL" in snapshot
    assert "BEL short active" in snapshot
