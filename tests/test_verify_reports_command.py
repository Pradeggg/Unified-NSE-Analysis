from pathlib import Path

from terminal.copilot_workflows.verify import render_verify
from terminal.task_memory import TaskMemoryStore


def test_verify_reports_validates_links_and_writes_markdown(tmp_path: Path):
    latest = tmp_path / "reports/latest"
    latest.mkdir(parents=True)
    (latest / "results_analysis.html").write_text('<a href="missing.html">broken</a>', encoding="utf-8")
    (latest / "stage2_tracker.html").write_text("<html><body>Stage 2</body></html>", encoding="utf-8")
    (latest / "top_picks.html").write_text("<html><body>Top Picks</body></html>", encoding="utf-8")
    store = TaskMemoryStore(tmp_path / "memory.json")

    text = render_verify("reports", cwd=tmp_path, memory_store=store)

    validation = latest / "report_validation.md"
    assert validation.exists()
    assert "missing_file" in validation.read_text(encoding="utf-8")
    assert "WARN" in text or "FAIL" in text
    memory = store.load()
    assert memory["latest_report_validation"]["artifact"].endswith("report_validation.md")
    assert memory["recent_artifacts"][0]["kind"] == "report_validation"


def test_verify_reports_handles_missing_reports_without_traceback(tmp_path: Path):
    text = render_verify("reports", cwd=tmp_path)

    assert "results analysis report" in text
    assert "FAIL" in text
    assert "Traceback" not in text
