from __future__ import annotations

from datetime import date


class FakePatternRepo:
    def __init__(self, *, events=None, chains=None):
        self.events = list(events or [])
        self.chains = list(chains or [])
        self.saved = []
        self.event_queries = []
        self.chain_queries = []

    def list_interaction_events(self, *, start_date, end_date=None):
        self.event_queries.append((start_date, end_date))
        return list(self.events)

    def list_workflow_chains(self, *, start_date, end_date=None):
        self.chain_queries.append((start_date, end_date))
        return list(self.chains)

    def save_pattern(self, pattern):
        self.saved.append(dict(pattern))
        return 1000 + len(self.saved)


def _event(
    event_id,
    intent,
    query,
    *,
    ts="2026-06-06T09:00:00+00:00",
    route_type="agent_query",
    entities=(),
    tools=(),
    artifacts=(),
    errors=(),
    missing=(),
):
    return {
        "event_id": event_id,
        "event_ts": ts,
        "raw_query": query,
        "normalized_query": " ".join(query.lower().split()),
        "selected_intent": intent,
        "route_type": route_type,
        "detected_entities": list(entities),
        "tools_executed": list(tools),
        "artifacts": list(artifacts),
        "errors": list(errors),
        "missing_evidence": list(missing),
        "payload": {},
    }


def _chain(chain_id, chain_type, *, ts="2026-06-06T09:00:00+00:00", errors=(), event_ids=(1, 2)):
    return {
        "chain_id": chain_id,
        "chain_key": f"{chain_type}:{event_ids[0]}-{event_ids[-1]}",
        "started_at": ts,
        "ended_at": ts,
        "event_ids": list(event_ids),
        "chain_payload": {
            "chain_type": chain_type,
            "event_ids": list(event_ids),
            "errors": list(errors),
        },
    }


def test_pattern_miner_identifies_recurring_workflows_failures_and_report_issues():
    from terminal.learning.pattern_miner import mine_learning_patterns

    events = [
        _event(1, "daily_refresh", "run the daily refresh and eod reports", route_type="command_action"),
        _event(2, "daily_refresh", "run the daily refresh and eod reports", route_type="command_action"),
        _event(3, "daily_refresh", "run the daily refresh and eod reports", route_type="command_action"),
        _event(
            4,
            "llm_driven_fallback",
            "latest quarterly results analysis",
            tools=("get_latest_results",),
            errors=("missing required tool: get_latest_results",),
            missing=("scores.quarterly_results",),
        ),
        _event(
            5,
            "llm_driven_fallback",
            "latest quarterly results analysis",
            tools=("get_latest_results",),
            errors=("missing required tool: get_latest_results",),
            missing=("scores.quarterly_results",),
        ),
        _event(
            6,
            "report_debug",
            "results analysis links are not working",
            route_type="command_action",
            artifacts=("reports/latest/results_analysis.html",),
            errors=("broken report links",),
        ),
        _event(
            7,
            "report_debug",
            "results analysis links are not working",
            route_type="command_action",
            artifacts=("reports/latest/results_analysis.html",),
            errors=("broken report links",),
        ),
        _event(8, "symbol_quick_analysis", "analyze RELIANCE", entities=("RELIANCE",)),
    ]
    chains = [
        _chain(11, "daily_refresh_report_review_email"),
        _chain(12, "daily_refresh_report_review_email"),
        _chain(13, "daily_refresh_report_review_email"),
        _chain(21, "scanner_to_watchlist"),
        _chain(22, "scanner_to_watchlist"),
        _chain(31, "portfolio_review_debug"),
    ]

    result = mine_learning_patterns(
        events=events,
        workflow_chains=chains,
        start_date=date(2026, 5, 25),
        end_date=date(2026, 6, 7),
    )
    payloads = {pattern.pattern_key: pattern.to_record()["pattern_payload"] for pattern in result.patterns}

    assert result.window_days == 14
    assert "workflow:daily_refresh_report_review_email" in payloads
    assert payloads["workflow:daily_refresh_report_review_email"]["frequency"] == 3
    assert payloads["workflow:daily_refresh_report_review_email"]["priority"] == "high"
    assert payloads["workflow:daily_refresh_report_review_email"]["candidate_type"] == "workflow_proposal"
    assert "workflow:scanner_to_watchlist" in payloads
    assert payloads["workflow:scanner_to_watchlist"]["priority"] in {"medium", "high"}
    assert "fallback_failure:missing required tool: get_latest_results" in payloads
    assert payloads["fallback_failure:missing required tool: get_latest_results"]["candidate_type"] == "route_tool_skill_candidate"
    assert payloads["fallback_failure:missing required tool: get_latest_results"]["failure_severity"] == 3
    assert "report_issue:broken report links" in payloads
    assert payloads["report_issue:broken report links"]["candidate_type"] == "report_validation_proposal"
    assert "query:run the daily refresh and eod reports" in payloads
    assert "query:analyze reliance" not in payloads
    assert [pattern.pattern_key for pattern in result.patterns] == sorted(
        [pattern.pattern_key for pattern in result.patterns],
        key=lambda key: (-payloads[key]["score"], key),
    )


def test_pattern_miner_loads_window_and_persists_patterns():
    from terminal.learning.pattern_miner import analyze_learning_patterns

    repo = FakePatternRepo(
        events=[
            _event(1, "quality_breakouts", "stocks creating new highs"),
            _event(2, "quality_breakouts", "stocks creating new highs"),
        ],
        chains=[_chain(11, "scanner_to_watchlist"), _chain(12, "scanner_to_watchlist")],
    )

    result = analyze_learning_patterns(
        repository=repo,
        end_date="2026-06-07",
        window="14d",
        save=True,
    )

    assert repo.event_queries == [(date(2026, 5, 25), date(2026, 6, 7))]
    assert repo.chain_queries == [(date(2026, 5, 25), date(2026, 6, 7))]
    assert len(repo.saved) == len(result.patterns)
    assert repo.saved[0]["status"] == "observed"
    assert repo.saved[0]["pattern_key"] == result.patterns[0].pattern_key
    assert result.saved_pattern_ids == list(range(1001, 1001 + len(result.patterns)))


def test_single_one_off_events_do_not_become_high_priority_patterns():
    from terminal.learning.pattern_miner import mine_learning_patterns

    result = mine_learning_patterns(
        events=[_event(1, "symbol_quick_analysis", "analyze RELIANCE", entities=("RELIANCE",))],
        workflow_chains=[],
        start_date="2026-05-25",
        end_date="2026-06-07",
    )

    assert all(pattern.priority != "high" for pattern in result.patterns)
    assert all(pattern.frequency > 1 for pattern in result.patterns)


def test_agent_adda_parser_accepts_learning_analyze_command():
    from agent_adda.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["learning", "analyze", "--window", "14d"])

    assert args.command == "learning"
    assert args.learning_command == "analyze"
    assert args.window == "14d"
