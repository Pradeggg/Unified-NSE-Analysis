from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pg_grounded_query_smoke_quick_mode_writes_report() -> None:
    report_dir = ROOT / "reports" / "pg_grounded_queries"
    report_json = report_dir / "pg_grounded_query_report.json"
    if report_json.exists():
        report_json.unlink()

    result = subprocess.run(
        [
            sys.executable,
            "scripts/smoke_pg_grounded_queries.py",
            "--quick",
            "--output-dir",
            str(report_dir),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert report_json.exists()

    payload = json.loads(report_json.read_text())
    categories = {case["category"]: case for case in payload["cases"]}
    assert set(categories) == {
        "technicals",
        "market_analysis",
        "stock_analysis",
        "index_analysis",
        "deep_fundamental_analysis",
    }
    assert all(case["status"] == "pass" for case in categories.values())
    assert all(case["pg_grounded"] is True for case in categories.values())
