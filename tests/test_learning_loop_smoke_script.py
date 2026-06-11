from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_learning_loop_smoke_script_runs_e2e_and_writes_artifacts(tmp_path):
    script = Path("scripts/smoke_learning_loop.sh")

    env = {
        **os.environ,
        "OUTPUT_DIR": str(tmp_path),
        "PYTHON": sys.executable,
    }
    result = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "E2E_OK" in result.stdout
    assert (tmp_path / "learning_audit_14d.html").exists()
    assert (tmp_path / "learning_audit_14d.md").exists()
    assert any((tmp_path / "backlog").glob("proposal_*_*.md"))
    assert "Agent Adda Fortnightly Learning Audit" in (tmp_path / "learning_audit_14d.html").read_text(encoding="utf-8")
