from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "portfolio.cli", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_replay_writes_json_audit_and_markdown_outputs(tmp_path: Path):
    output_dir = tmp_path / "paper"

    proc = _run_cli("replay", "--output-dir", str(output_dir))

    assert proc.returncode == 0, proc.stderr
    assert "Replay complete" in proc.stdout

    state_path = output_dir / "state" / "replay_state.json"
    metrics_path = output_dir / "metrics" / "metrics.json"
    audit_path = output_dir / "logs" / "audit.jsonl"
    report_path = output_dir / "reports" / "paper_trading_report.md"
    assert state_path.exists()
    assert metrics_path.exists()
    assert audit_path.exists()
    assert report_path.exists()

    state = json.loads(state_path.read_text(encoding="utf-8"))
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    audit_rows = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    report = report_path.read_text(encoding="utf-8")

    assert state["run_id"] == "PT-0"
    assert state["summary"]["strategy_ids"] == ["stage2_fixture_v1"]
    assert state["summary"]["fills"] == 1
    assert state["summary"]["open_positions"] == 1
    assert metrics["strategy_ids"] == ["stage2_fixture_v1"]
    assert metrics["number_of_fills"] == 1
    assert all({"agent", "action"} <= row.keys() for row in audit_rows)
    assert {row["action"] for row in audit_rows} >= {"run_replay", "write_report"}
    assert "# Paper Trading Report" in report
    assert "stage2_fixture_v1" in report


def test_cli_replay_replaces_audit_log_for_repeatable_outputs(tmp_path: Path):
    output_dir = tmp_path / "paper"
    first = _run_cli("replay", "--output-dir", str(output_dir))
    assert first.returncode == 0, first.stderr
    audit_path = output_dir / "logs" / "audit.jsonl"
    first_audit = audit_path.read_text(encoding="utf-8")

    second = _run_cli("replay", "--output-dir", str(output_dir))

    assert second.returncode == 0, second.stderr
    assert audit_path.read_text(encoding="utf-8") == first_audit


def test_cli_status_reads_saved_state_and_metrics(tmp_path: Path):
    output_dir = tmp_path / "paper"
    replay = _run_cli("replay", "--output-dir", str(output_dir))
    assert replay.returncode == 0, replay.stderr

    proc = _run_cli(
        "status",
        "--state",
        str(output_dir / "state" / "replay_state.json"),
        "--metrics",
        str(output_dir / "metrics" / "metrics.json"),
    )

    assert proc.returncode == 0, proc.stderr
    assert "Run: PT-0" in proc.stdout
    assert "Strategy: stage2_fixture_v1" in proc.stdout
    assert "Fills: 1" in proc.stdout
    assert "Open positions: 1" in proc.stdout
    assert "Ending equity:" in proc.stdout


def test_cli_report_prints_saved_markdown_report(tmp_path: Path):
    output_dir = tmp_path / "paper"
    replay = _run_cli("replay", "--output-dir", str(output_dir))
    assert replay.returncode == 0, replay.stderr

    proc = _run_cli("report", "--output-dir", str(output_dir), "--print")

    assert proc.returncode == 0, proc.stderr
    assert "# Paper Trading Report" in proc.stdout
    assert "## Summary" in proc.stdout
    assert "stage2_fixture_v1" in proc.stdout


def test_cli_report_regenerates_markdown_from_saved_state(tmp_path: Path):
    output_dir = tmp_path / "paper"
    replay = _run_cli("replay", "--output-dir", str(output_dir))
    assert replay.returncode == 0, replay.stderr

    report_path = output_dir / "reports" / "paper_trading_report.md"
    report_path.unlink()

    proc = _run_cli("report", "--output-dir", str(output_dir))

    assert proc.returncode == 0, proc.stderr
    assert report_path.exists()
    assert str(report_path) in proc.stdout
