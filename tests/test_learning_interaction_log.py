from __future__ import annotations


class FakeLearningRepo:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.events = []

    def record_interaction_event(self, event):
        if self.fail:
            raise RuntimeError("learning db unavailable")
        self.events.append(dict(event))
        return 501


def test_capture_interaction_event_persists_sanitized_normal_query(monkeypatch):
    from terminal.learning.interaction_log import InteractionEvent, capture_interaction_event

    repo = FakeLearningRepo()
    event = InteractionEvent(
        raw_query="Analyze RELIANCE",
        selected_intent="symbol_quick_analysis",
        route_type="agent_query",
        detected_entities=("RELIANCE",),
        tools_executed=("get_symbol_snapshot",),
        payload={"api_key": "sk-secret", "ok": True},
    )

    event_id = capture_interaction_event(event, repository=repo)

    assert event_id == 501
    assert repo.events[0]["raw_query"] == "Analyze RELIANCE"
    assert repo.events[0]["normalized_query"] == "analyze reliance"
    assert repo.events[0]["selected_intent"] == "symbol_quick_analysis"
    assert repo.events[0]["detected_entities"] == ["RELIANCE"]
    assert repo.events[0]["tools_executed"] == ["get_symbol_snapshot"]
    assert "api_key" not in repo.events[0]["payload"]
    assert repo.events[0]["payload"]["ok"] is True


def test_capture_interaction_event_can_be_disabled(monkeypatch):
    from terminal.learning.interaction_log import InteractionEvent, capture_interaction_event

    repo = FakeLearningRepo()
    monkeypatch.setenv("AGENT_ADDA_LEARNING_CAPTURE", "0")

    event_id = capture_interaction_event(InteractionEvent(raw_query="top gainers"), repository=repo)

    assert event_id is None
    assert repo.events == []


def test_capture_interaction_event_is_best_effort(monkeypatch):
    from terminal.learning.interaction_log import InteractionEvent, capture_interaction_event

    event_id = capture_interaction_event(
        InteractionEvent(raw_query="top gainers"),
        repository=FakeLearningRepo(fail=True),
    )

    assert event_id is None


def test_agent_query_records_normal_interaction_event(monkeypatch):
    from terminal.agent import Agent

    repo = FakeLearningRepo()
    agent = Agent.__new__(Agent)
    agent.backend_name = "test"
    agent._learning_repository = repo
    agent._handle_mode_command = lambda user_input: None
    agent._query_single = lambda user_input, show_trace=False, entity_assessment=None: {
        "answer": "RELIANCE quick read",
        "trace": [{"tool": "get_symbol_snapshot", "args": {"symbol": "RELIANCE"}, "result": {"symbol": "RELIANCE"}}],
        "backend": "test",
        "intent": "symbol_quick_analysis",
    }

    result = agent.query("Analyze RELIANCE", show_trace=False)

    assert result["intent"] == "symbol_quick_analysis"
    assert len(repo.events) == 1
    assert repo.events[0]["selected_intent"] == "symbol_quick_analysis"
    assert repo.events[0]["detected_entities"] == ["RELIANCE"]
    assert repo.events[0]["tools_executed"] == ["get_symbol_snapshot"]


def test_build_agent_turn_event_records_failed_tool_plan_reason():
    from terminal.learning.interaction_log import build_agent_turn_event

    event = build_agent_turn_event(
        "latest quarterly results analysis",
        {
            "intent": "llm_driven_fallback",
            "backend": "OpenAI",
            "trace": [
                {
                    "tool": "get_latest_results",
                    "error": "missing required tool",
                    "result": {
                        "error": "missing required tool",
                        "missing_evidence": ["scores.quarterly_results"],
                    },
                }
            ],
        },
    )
    record = event.to_record()

    assert record["selected_intent"] == "llm_driven_fallback"
    assert record["tools_executed"] == ["get_latest_results"]
    assert "missing required tool" in record["errors"]
    assert "scores.quarterly_results" in record["missing_evidence"]


def test_build_command_action_event_records_email_without_body_or_recipients():
    from terminal.learning.interaction_log import build_command_action_event

    event = build_command_action_event(
        "/email top_picks --to pgorai@deloitte.com",
        action="report_email",
        report="reports/latest/top_picks.html",
        recipient_list_key="daily_reports",
        payload={
            "email_body": "<html>secret body</html>",
            "recipients": ["pgorai@deloitte.com"],
            "attachment": "reports/latest/top_picks.html",
        },
    )
    record = event.to_record()

    assert record["selected_intent"] == "report_email"
    assert record["artifacts"] == ["reports/latest/top_picks.html"]
    assert record["payload"]["recipient_list_key"] == "daily_reports"
    assert "email_body" not in record["payload"]
    assert "recipients" not in record["payload"]


def test_nse_agent_learning_action_helper_uses_interaction_logger(monkeypatch):
    import nse_agent

    captured = {}

    def fake_capture(event, *, repository=None, env=None):
        captured["record"] = event.to_record()
        return 91

    monkeypatch.setattr(nse_agent, "capture_interaction_event", fake_capture)

    assert nse_agent._record_learning_action(
        "/email top_picks --to pgorai@deloitte.com",
        action="report_email",
        report="reports/latest/top_picks.html",
        recipient_list_key="daily_reports",
        payload={"email_body": "secret", "recipients": ["pgorai@deloitte.com"]},
    ) == 91
    assert captured["record"]["selected_intent"] == "report_email"
    assert captured["record"]["payload"]["recipient_list_key"] == "daily_reports"
    assert "email_body" not in captured["record"]["payload"]


def test_nse_agent_learning_action_classifier_covers_command_actions():
    import nse_agent

    assert nse_agent._learning_action_for_query("/email top_picks --to a@x.com") == "report_email"
    assert nse_agent._learning_action_for_query("open the report") == "report_open"
    assert nse_agent._learning_action_for_query("/verify reports") == "report_validation"
    assert nse_agent._learning_action_for_query("run the daily refresh") == "daily_refresh"
    assert nse_agent._learning_action_for_query("fix report links") == "code_report_fix"
