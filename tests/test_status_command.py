from pathlib import Path

from terminal.copilot_workflows.status import handle_status_command, render_status
from terminal.task_memory import TaskMemoryStore


def test_status_empty_memory_prints_startup_guidance(tmp_path: Path):
    store = TaskMemoryStore(tmp_path / "memory.json")

    text = render_status(store)

    assert "No active task memory yet" in text
    assert "/brainstorm" in text
    assert "/screen quality-breakouts" in text


def test_status_shows_objective_watchlist_artifacts_and_issues(tmp_path: Path):
    store = TaskMemoryStore(tmp_path / "memory.json")
    store.set_objective("Slice 4 memory")
    store.record_quality_breakouts(["NSE:AAA", "NSE:BBB"], source="acceptance")
    store.record_artifact("report_validation", "reports/latest/report_validation.md")
    store.add_issue("Broken link in results analysis")

    text = render_status(store)

    assert "Slice 4 memory" in text
    assert "NSE:AAA" in text
    assert "report_validation.md" in text
    assert "Broken link" in text


def test_status_clear_resets_memory(tmp_path: Path):
    path = tmp_path / "memory.json"
    store = TaskMemoryStore(path)
    store.set_objective("temporary")

    text = handle_status_command("/status clear", store=store)

    assert "cleared" in text.lower()
    assert TaskMemoryStore(path).load()["current_objective"] == ""
