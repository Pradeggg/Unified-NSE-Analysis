from pathlib import Path

from terminal.task_memory import TaskMemoryStore


def test_missing_memory_file_returns_empty_state(tmp_path: Path):
    store = TaskMemoryStore(tmp_path / "memory.json")

    state = store.load()

    assert state["schema_version"] == 1
    assert state["current_objective"] == ""
    assert state["recent_commands"] == []
    assert state["recent_artifacts"] == []


def test_memory_persists_commands_artifacts_and_quality_breakouts(tmp_path: Path):
    path = tmp_path / "memory.json"
    store = TaskMemoryStore(path)

    store.set_objective("build task memory")
    store.record_command("/screen quality-breakouts")
    store.record_artifact("quality_breakouts", "reports/latest/qb.txt")
    store.record_quality_breakouts(["NSE:AAA", "NSE:BBB"], source="smoke")

    restarted = TaskMemoryStore(path).load()
    assert restarted["current_objective"] == "build task memory"
    assert restarted["recent_commands"][0]["command"] == "/screen quality-breakouts"
    assert restarted["recent_artifacts"][0]["path"] == "reports/latest/qb.txt"
    assert restarted["latest_quality_breakouts"]["symbols"] == ["NSE:AAA", "NSE:BBB"]


def test_corrupt_memory_file_is_backed_up_and_recovered(tmp_path: Path):
    path = tmp_path / "memory.json"
    path.write_text("{not-json", encoding="utf-8")

    state = TaskMemoryStore(path).load()

    assert state["schema_version"] == 1
    assert list(tmp_path.glob("memory.json.corrupt-*"))
