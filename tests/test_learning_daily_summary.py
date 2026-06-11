from __future__ import annotations

from datetime import date


class FakeDailySummaryRepo:
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

    def save_daily_summary(self, summary):
        self.saved.append(dict(summary))
        return 901


def _event(
    event_id,
    intent,
    raw_query,
    *,
    route_type="agent_query",
    entities=(),
    tools=(),
    artifacts=(),
    errors=(),
    missing=(),
    payload=None,
):
    return {
        "event_id": event_id,
        "event_ts": "2026-06-06T09:00:00+00:00",
        "raw_query": raw_query,
        "normalized_query": raw_query.lower(),
        "selected_intent": intent,
        "route_type": route_type,
        "detected_entities": list(entities),
        "tools_executed": list(tools),
        "artifacts": list(artifacts),
        "errors": list(errors),
        "missing_evidence": list(missing),
        "payload": dict(payload or {}),
    }


def _chain(chain_id, chain_type, *, errors=(), event_ids=(1, 2), artifacts=(), entities=()):
    return {
        "chain_id": chain_id,
        "chain_key": f"{chain_type}:{event_ids[0]}-{event_ids[-1]}",
        "started_at": "2026-06-06T09:00:00+00:00",
        "ended_at": "2026-06-06T09:05:00+00:00",
        "event_ids": list(event_ids),
        "chain_payload": {
            "chain_type": chain_type,
            "event_ids": list(event_ids),
            "intents": ["daily_refresh", "report_open"],
            "artifacts": list(artifacts),
            "entities": list(entities),
            "tools": [],
            "errors": list(errors),
        },
    }


def test_daily_learning_summary_counts_activity_deterministically():
    from terminal.learning.daily_summary import build_daily_learning_summary

    events = [
        _event(
            1,
            "quality_breakouts",
            "stocks creating new highs",
            entities=("RELIANCE", "CGPOWER"),
            tools=("run_quality_breakout_screener",),
            artifacts=("reports/latest/stage2_buy_tradingview.txt",),
        ),
        _event(
            2,
            "report_email",
            "/email top picks",
            route_type="command_action",
            artifacts=("reports/latest/top_picks.html",),
            payload={"recipient_list_key": "daily_reports"},
        ),
        _event(
            3,
            "llm_driven_fallback",
            "latest quarterly results analysis",
            tools=("get_latest_results",),
            errors=("missing required tool: get_latest_results",),
            missing=("scores.quarterly_results",),
        ),
        _event(
            4,
            "report_debug",
            "portfolio report percentages are off",
            route_type="command_action",
            artifacts=("reports/latest/portfolio_intraday.html",),
            errors=("report percentages are off",),
        ),
    ]
    chains = [
        _chain(11, "daily_refresh_report_review_email", event_ids=(1, 2), artifacts=("reports/latest/top_picks.html",)),
        _chain(12, "fallback_failure_recovery", errors=("missing required tool",), event_ids=(3, 4)),
    ]

    summary = build_daily_learning_summary(date(2026, 6, 6), events=events, workflow_chains=chains)
    payload = summary.to_payload()

    assert payload["summary_date"] == "2026-06-06"
    assert payload["event_count"] == 4
    assert payload["top_intents"] == [
        {"value": "llm_driven_fallback", "count": 1},
        {"value": "quality_breakouts", "count": 1},
        {"value": "report_debug", "count": 1},
        {"value": "report_email", "count": 1},
    ]
    assert payload["top_entities"] == [{"value": "CGPOWER", "count": 1}, {"value": "RELIANCE", "count": 1}]
    assert payload["commands_run"] == [
        {"value": "report_debug", "count": 1},
        {"value": "report_email", "count": 1},
    ]
    assert payload["tools_used"] == [
        {"value": "get_latest_results", "count": 1},
        {"value": "run_quality_breakout_screener", "count": 1},
    ]
    assert payload["artifacts_created"] == [
        {"value": "reports/latest/portfolio_intraday.html", "count": 1},
        {"value": "reports/latest/stage2_buy_tradingview.txt", "count": 1},
        {"value": "reports/latest/top_picks.html", "count": 1},
    ]
    assert payload["failures"] == [{"value": "missing required tool: get_latest_results", "count": 1}]
    assert payload["report_issues"] == [{"value": "report percentages are off", "count": 1}]
    assert payload["missing_evidence"] == [{"value": "scores.quarterly_results", "count": 1}]
    assert payload["workflow_counts"] == [
        {"value": "daily_refresh_report_review_email", "count": 1},
        {"value": "fallback_failure_recovery", "count": 1},
    ]
    assert payload["successful_workflows"] == [{"chain_id": 11, "chain_type": "daily_refresh_report_review_email"}]
    assert payload["failed_workflows"] == [{"chain_id": 12, "chain_type": "fallback_failure_recovery"}]
    assert "No learning activity" not in summary.markdown
    assert "## Failures" in summary.markdown
    assert "fallback_failure_recovery" in summary.markdown


def test_empty_daily_learning_summary_is_clear():
    from terminal.learning.daily_summary import build_daily_learning_summary

    summary = build_daily_learning_summary("2026-06-07", events=[], workflow_chains=[])
    payload = summary.to_payload()

    assert payload["event_count"] == 0
    assert payload["activity_status"] == "no_activity"
    assert "No learning activity was logged for 2026-06-07." in summary.markdown


def test_summarize_daily_learning_loads_saves_and_writes_markdown(tmp_path):
    from terminal.learning.daily_summary import summarize_daily_learning

    repo = FakeDailySummaryRepo(
        events=[_event(1, "report_open", "open top picks", route_type="command_action")],
        chains=[_chain(21, "daily_refresh_report_review_email")],
    )

    result = summarize_daily_learning(
        "2026-06-06",
        repository=repo,
        save=True,
        write_markdown=True,
        output_dir=tmp_path,
    )

    assert repo.event_queries == [(date(2026, 6, 6), date(2026, 6, 6))]
    assert repo.chain_queries == [(date(2026, 6, 6), date(2026, 6, 6))]
    assert repo.saved[0]["summary_date"] == date(2026, 6, 6)
    assert repo.saved[0]["summary_payload"]["event_count"] == 1
    assert result.summary_id == 901
    assert result.markdown_path == tmp_path / "learning_summary_2026-06-06.md"
    assert result.markdown_path.read_text(encoding="utf-8").startswith("# Agent Adda Daily Learning Summary")


def test_agent_adda_parser_accepts_learning_summary_commands():
    from agent_adda.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["learning", "summarize", "--date", "2026-06-06"])
    assert args.command == "learning"
    assert args.learning_command == "summarize"
    assert args.date == "2026-06-06"

    today_args = parser.parse_args(["learning", "summarize", "--today", "--write-md"])
    assert today_args.today is True
    assert today_args.write_md is True
