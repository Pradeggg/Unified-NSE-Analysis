import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "tests" / "e2e" / "e2e_scenarios.json"
RUNNER = ROOT / "scripts" / "run_e2e.py"
VALID_TIERS = {"smoke", "critical", "full"}


def _scenarios():
    return json.loads(MATRIX.read_text(encoding="utf-8"))["scenarios"]


@pytest.mark.e2e
def test_e2e_matrix_is_comprehensive_and_well_formed():
    scenarios = _scenarios()
    ids = [scenario["id"] for scenario in scenarios]

    assert len(scenarios) >= 12
    assert len(ids) == len(set(ids))
    assert {"smoke", "critical", "full"}.issubset({scenario["tier"] for scenario in scenarios})

    required_areas = {
        "cli",
        "data-readiness",
        "refresh",
        "terminal-agent",
        "intraday",
        "sector-rotation",
        "screeners",
        "postgres",
        "reports",
        "documents",
        "strategy",
        "global-macro",
        "knowledge-base",
    }
    assert required_areas.issubset({scenario["area"] for scenario in scenarios})

    for scenario in scenarios:
        assert scenario["tier"] in VALID_TIERS
        assert scenario.get("title")
        assert scenario.get("command")
        assert scenario.get("assertions")
        for entrypoint in scenario.get("entrypoints", []):
            assert (ROOT / entrypoint).exists(), f"{scenario['id']} references missing {entrypoint}"


@pytest.mark.e2e
def test_e2e_runner_lists_smoke_scenarios():
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--tier", "smoke", "--list"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "cli-bootstrap-smoke" in result.stdout
    assert "daily-refresh-dry-run" in result.stdout


@pytest.mark.e2e
def test_e2e_runner_dry_run_smoke_suite():
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--tier", "smoke", "--dry-run"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "DRY_RUN" in result.stdout
    assert "syntax-entrypoints-smoke" in result.stdout
