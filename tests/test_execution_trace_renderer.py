from rich.console import Console

from terminal.execution_trace import ExecutionTrace
from terminal.renderers.execution_trace import render_execution_trace


def _render_to_text(trace: ExecutionTrace, *, expanded: bool = False) -> str:
    console = Console(record=True, width=120)
    render_execution_trace(console, trace, expanded=expanded)
    return console.export_text()


def test_renderer_handles_empty_trace():
    trace = ExecutionTrace.start("empty", command="/noop")

    text = _render_to_text(trace)

    assert "Execution Trail" in text
    assert "/noop" in text


def test_renderer_shows_counts_artifacts_and_failures():
    trace = ExecutionTrace.start("quality_breakouts", command="/screen quality-breakouts --explain")
    trace.add_step("Run breakouts")
    trace.add_tool_result("run_screener_query", status="ok", row_count=25)
    trace.add_filter_count("quality overlay", before=85, after=52)
    trace.add_artifact("TradingView", "reports/latest/quality_breakouts.txt")
    trace.add_tool_result("validate", status="failed", error="bad link")
    trace.add_verification("snapshot", "pass", "2026-06-03")
    trace.complete(status="failed")

    text = _render_to_text(trace, expanded=True)

    assert "Run breakouts" in text
    assert "25" in text
    assert "85" in text and "52" in text
    assert "reports/latest/quality_breakouts.txt" in text
    assert "bad link" in text
    assert "snapshot" in text

