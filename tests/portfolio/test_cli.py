from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import portfolio


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "portfolio.cli", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_module_import_does_not_depend_on_tests_package(tmp_path: Path):
    repo_root = Path(portfolio.__file__).resolve().parent.parent
    code = """
import importlib.abc
import sys

class BlockTests(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "tests" or fullname.startswith("tests."):
            raise ImportError("tests package import blocked")
        return None

sys.meta_path.insert(0, BlockTests())
import portfolio.cli
print("ok")
"""

    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(repo_root)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "ok"


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


def test_cli_status_reports_missing_artifacts_without_traceback(tmp_path: Path):
    proc = _run_cli("status", "--output-dir", str(tmp_path / "missing"))

    assert proc.returncode == 1
    assert "missing artifact:" in proc.stderr
    assert "replay_state.json" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_cli_status_reports_corrupt_artifacts_without_traceback(tmp_path: Path):
    output_dir = tmp_path / "paper"
    state_path = output_dir / "state" / "replay_state.json"
    metrics_path = output_dir / "metrics" / "metrics.json"
    state_path.parent.mkdir(parents=True)
    metrics_path.parent.mkdir(parents=True)
    state_path.write_text('{"run_id": "PT-0", "summary": {}}', encoding="utf-8")
    metrics_path.write_text("{bad json}", encoding="utf-8")

    proc = _run_cli("status", "--output-dir", str(output_dir))

    assert proc.returncode == 1
    assert "corrupt artifact:" in proc.stderr
    assert "metrics.json" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_cli_status_reports_semantically_corrupt_metrics_without_partial_output(tmp_path: Path):
    output_dir = tmp_path / "paper"
    state_path = output_dir / "state" / "replay_state.json"
    metrics_path = output_dir / "metrics" / "metrics.json"
    state_path.parent.mkdir(parents=True)
    metrics_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "run_id": "PT-0",
                "summary": {
                    "last_timestamp": "2025-01-08",
                    "strategy_ids": ["stage2_fixture_v1"],
                },
            }
        ),
        encoding="utf-8",
    )
    metrics_path.write_text(
        json.dumps(
            {
                "starting_equity": 100000.0,
                "ending_equity": "bad",
                "total_return_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "number_of_trades": 0,
                "number_of_fills": 1,
                "realized_pnl": 0.0,
                "winning_trades": 0,
                "losing_trades": 0,
                "flat_trades": 0,
                "open_positions_count": 1,
                "invalid_fill_sequences": 0,
                "strategy_ids": ["stage2_fixture_v1"],
            }
        ),
        encoding="utf-8",
    )

    proc = _run_cli("status", "--output-dir", str(output_dir))

    assert proc.returncode == 1
    assert proc.stdout == ""
    assert "corrupt artifact:" in proc.stderr
    assert "metrics.json" in proc.stderr
    assert "ending_equity" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_cli_status_reports_nonfinite_integer_metrics_without_traceback(tmp_path: Path):
    output_dir = tmp_path / "paper"
    state_path = output_dir / "state" / "replay_state.json"
    metrics_path = output_dir / "metrics" / "metrics.json"
    state_path.parent.mkdir(parents=True)
    metrics_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "run_id": "PT-0",
                "summary": {
                    "last_timestamp": "2025-01-08",
                    "strategy_ids": ["stage2_fixture_v1"],
                },
            }
        ),
        encoding="utf-8",
    )
    metrics_path.write_text(
        """
{
  "starting_equity": 100000.0,
  "ending_equity": 99620.0,
  "total_return_pct": -0.38,
  "max_drawdown_pct": 0.9446,
  "number_of_trades": 0,
  "number_of_fills": 1e309,
  "realized_pnl": 0.0,
  "winning_trades": 0,
  "losing_trades": 0,
  "flat_trades": 0,
  "open_positions_count": 1,
  "invalid_fill_sequences": 0,
  "strategy_ids": ["stage2_fixture_v1"]
}
""",
        encoding="utf-8",
    )

    proc = _run_cli("status", "--output-dir", str(output_dir))

    assert proc.returncode == 1
    assert proc.stdout == ""
    assert "corrupt artifact:" in proc.stderr
    assert "metrics.json" in proc.stderr
    assert "number_of_fills" in proc.stderr
    assert "Traceback" not in proc.stderr


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


def test_cli_report_reports_missing_artifacts_without_traceback(tmp_path: Path):
    proc = _run_cli("report", "--output-dir", str(tmp_path / "missing"))

    assert proc.returncode == 1
    assert "missing artifact:" in proc.stderr
    assert "replay_state.json" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_cli_report_reports_corrupt_artifacts_without_traceback(tmp_path: Path):
    output_dir = tmp_path / "paper"
    state_path = output_dir / "state" / "replay_state.json"
    metrics_path = output_dir / "metrics" / "metrics.json"
    state_path.parent.mkdir(parents=True)
    metrics_path.parent.mkdir(parents=True)
    state_path.write_text("{bad json}", encoding="utf-8")
    metrics_path.write_text('{"ending_equity": 0.0}', encoding="utf-8")

    proc = _run_cli("report", "--output-dir", str(output_dir))

    assert proc.returncode == 1
    assert "corrupt artifact:" in proc.stderr
    assert "replay_state.json" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_cli_report_reports_incomplete_metrics_without_traceback(tmp_path: Path):
    output_dir = tmp_path / "paper"
    replay = _run_cli("replay", "--output-dir", str(output_dir))
    assert replay.returncode == 0, replay.stderr
    (output_dir / "reports" / "paper_trading_report.md").unlink()
    metrics_path = output_dir / "metrics" / "metrics.json"
    metrics_path.write_text(json.dumps({"ending_equity": 99620.0}), encoding="utf-8")

    proc = _run_cli("report", "--output-dir", str(output_dir))

    assert proc.returncode == 1
    assert "corrupt artifact:" in proc.stderr
    assert "metrics.json" in proc.stderr
    assert "starting_equity" in proc.stderr
    assert "Traceback" not in proc.stderr
