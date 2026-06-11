from terminal.execution_trace import ExecutionTrace


def test_trace_records_tool_success_filter_and_verification_as_json():
    trace = ExecutionTrace.start("quality_breakouts", command="/screen quality-breakouts")

    trace.add_step("Run new highs", detail="Collect candidates near 52-week highs")
    trace.add_tool_result("run_screener_query", status="ok", row_count=25)
    trace.add_filter_count("quality overlay", before=85, after=52)
    trace.add_artifact("tradingview", "reports/latest/quality_breakouts.txt")
    trace.add_verification("snapshot_date", "pass", "2026-06-03")
    trace.complete(status="ok")

    payload = trace.to_dict()

    assert payload["workflow_kind"] == "quality_breakouts"
    assert payload["status"] == "ok"
    assert payload["events"][0]["event_type"] == "workflow_started"
    assert any(e["event_type"] == "filter_applied" for e in payload["events"])
    assert payload["summary"]["tools_ok"] == 1
    assert payload["summary"]["verification_pass"] == 1


def test_trace_records_tool_failure_without_raising():
    trace = ExecutionTrace.start("report_verify")

    trace.add_tool_result("validate_report_links", status="failed", error="missing file")
    trace.complete(status="failed")

    assert trace.summary_counts()["tools_failed"] == 1
    assert trace.events[-1].event_type == "workflow_completed"

