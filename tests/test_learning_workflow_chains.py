from __future__ import annotations


class FakeWorkflowRepo:
    def __init__(self):
        self.chains = []

    def record_workflow_chain(self, chain):
        self.chains.append(dict(chain))
        return 700 + len(self.chains)


def _event(event_id, intent, query, *, artifacts=(), entities=(), tools=(), ts="2026-06-06T09:00:00+00:00", payload=None, errors=()):
    return {
        "event_id": event_id,
        "event_ts": ts,
        "raw_query": query,
        "normalized_query": query.lower(),
        "selected_intent": intent,
        "route_type": "command_action" if intent.startswith(("report_", "daily_", "code_")) else "agent_query",
        "detected_entities": list(entities),
        "tools_executed": list(tools),
        "artifacts": list(artifacts),
        "errors": list(errors),
        "missing_evidence": [],
        "payload": dict(payload or {}),
    }


def test_daily_refresh_open_reports_email_top_picks_is_one_chain():
    from terminal.learning.workflow_chains import detect_workflow_chains

    events = [
        _event(1, "daily_refresh", "run the daily refresh", ts="2026-06-06T09:00:00+00:00"),
        _event(2, "report_open", "open reports/latest/top_picks.html", artifacts=("reports/latest/top_picks.html",), ts="2026-06-06T09:05:00+00:00"),
        _event(3, "report_email", "/email top picks", artifacts=("reports/latest/top_picks.html",), ts="2026-06-06T09:08:00+00:00", payload={"recipient_list_key": "daily_reports"}),
    ]

    chains = detect_workflow_chains(events)

    assert len(chains) == 1
    assert chains[0].chain_type == "daily_refresh_report_review_email"
    assert chains[0].event_ids == (1, 2, 3)
    assert "reports/latest/top_picks.html" in chains[0].artifacts


def test_report_debug_fix_regenerate_validate_open_is_one_chain():
    from terminal.learning.workflow_chains import detect_workflow_chains

    events = [
        _event(10, "report_debug", "links not working in results_analysis", artifacts=("reports/latest/results_analysis.html",), ts="2026-06-06T10:00:00+00:00", errors=("broken links",)),
        _event(11, "code_report_fix", "fix report links", artifacts=("reports/latest/results_analysis.html",), ts="2026-06-06T10:08:00+00:00"),
        _event(12, "report_generate", "/report results-analysis", artifacts=("reports/latest/results_analysis.html",), ts="2026-06-06T10:15:00+00:00"),
        _event(13, "report_validation", "/verify reports", artifacts=("reports/latest/results_analysis.html",), ts="2026-06-06T10:18:00+00:00"),
        _event(14, "report_open", "open report", artifacts=("reports/latest/results_analysis.html",), ts="2026-06-06T10:20:00+00:00"),
    ]

    chains = detect_workflow_chains(events)

    assert len(chains) == 1
    assert chains[0].chain_type == "report_debug_regenerate_validate"
    assert chains[0].event_ids == (10, 11, 12, 13, 14)
    assert "broken links" in chains[0].errors


def test_unrelated_queries_are_not_forced_into_one_chain():
    from terminal.learning.workflow_chains import detect_workflow_chains

    events = [
        _event(21, "symbol_quick_analysis", "analyze RELIANCE", entities=("RELIANCE",), ts="2026-06-06T09:00:00+00:00"),
        _event(22, "portfolio_review", "review my portfolio", ts="2026-06-06T12:30:00+00:00"),
        _event(23, "report_email", "/email top picks", artifacts=("reports/latest/top_picks.html",), ts="2026-06-06T16:00:00+00:00"),
    ]

    assert detect_workflow_chains(events) == []


def test_stock_research_scanner_portfolio_and_fallback_chain_types_are_detected():
    from terminal.learning.workflow_chains import detect_workflow_chains

    events = [
        _event(31, "symbol_quick_analysis", "analyze CGPOWER", entities=("CGPOWER",), ts="2026-06-06T09:00:00+00:00"),
        _event(32, "company_360_research_report", "research CGPOWER", entities=("CGPOWER",), ts="2026-06-06T09:04:00+00:00"),
        _event(33, "report_open", "open CGPOWER research", artifacts=("reports/generated/CGPOWER.html",), entities=("CGPOWER",), ts="2026-06-06T09:09:00+00:00"),
        _event(41, "quality_breakouts", "stocks creating new highs", tools=("run_quality_breakout_screener",), ts="2026-06-06T10:00:00+00:00"),
        _event(42, "watchlist_export", "add to trading view", artifacts=("reports/latest/stage2_buy_tradingview.txt",), ts="2026-06-06T10:04:00+00:00"),
        _event(51, "portfolio_review", "review my portfolio", ts="2026-06-06T11:00:00+00:00"),
        _event(52, "code_report_fix", "fix portfolio percentages", artifacts=("reports/latest/portfolio_intraday.html",), ts="2026-06-06T11:03:00+00:00"),
        _event(61, "llm_driven_fallback", "latest quarterly results analysis", errors=("missing tool",), ts="2026-06-06T12:00:00+00:00"),
        _event(62, "route_failure_diagnostics", "why did agent go off rails", errors=("missing tool",), ts="2026-06-06T12:02:00+00:00"),
    ]

    chain_types = {chain.chain_type for chain in detect_workflow_chains(events)}

    assert "stock_research_deep_dive" in chain_types
    assert "scanner_to_watchlist" in chain_types
    assert "portfolio_review_debug" in chain_types
    assert "fallback_failure_recovery" in chain_types


def test_store_workflow_chains_persists_summary_and_event_ids():
    from terminal.learning.workflow_chains import detect_workflow_chains, store_workflow_chains

    repo = FakeWorkflowRepo()
    events = [
        _event(1, "daily_refresh", "run refresh", ts="2026-06-06T09:00:00+00:00"),
        _event(2, "report_open", "open report", artifacts=("reports/latest/top_picks.html",), ts="2026-06-06T09:03:00+00:00"),
        _event(3, "report_email", "email report", artifacts=("reports/latest/top_picks.html",), ts="2026-06-06T09:04:00+00:00"),
    ]
    chains = detect_workflow_chains(events)

    ids = store_workflow_chains(chains, repository=repo)

    assert ids == [701]
    assert repo.chains[0]["chain_key"].startswith("daily_refresh_report_review_email:")
    assert repo.chains[0]["event_ids"] == [1, 2, 3]
    assert repo.chains[0]["chain_payload"]["chain_type"] == "daily_refresh_report_review_email"
