from __future__ import annotations

import json
import subprocess
import sys


def test_terminal_generator_dry_run_filters_by_domain_and_keeps_generated_status(tmp_path):
    from terminal.skills.generator import generate_skill_scenarios

    result = generate_skill_scenarios(
        domain="screening",
        count=3,
        dry_run=True,
        output_dir=tmp_path,
    )

    rows = [json.loads(line) for line in result.jsonl_path.read_text(encoding="utf-8").splitlines()]

    assert result.generated == 3
    assert all(row["domain"] == "screening" for row in rows)
    assert all(row["status"] == "generated" for row in rows)
    assert all("output_contract" in row for row in rows)


def test_terminal_generator_rejects_unknown_domain(tmp_path):
    from terminal.skills.generator import generate_skill_scenarios

    try:
        generate_skill_scenarios(domain="unknown_domain", count=1, dry_run=True, output_dir=tmp_path)
    except ValueError as exc:
        assert "unknown domain" in str(exc)
    else:
        raise AssertionError("expected unknown domain to fail")


def test_generate_skill_scenarios_script_dry_run_writes_jsonl_under_requested_output_dir(tmp_path):
    script = "scripts/generate_skill_scenarios.py"

    result = subprocess.run(
        [
            sys.executable,
            script,
            "--domain",
            "portfolio_review",
            "--count",
            "2",
            "--dry-run",
            "--output-dir",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "generated=2" in result.stdout
    assert "dry_run=True" in result.stdout

    jsonl_lines = [line for line in result.stdout.splitlines() if line.startswith("jsonl=")]
    assert jsonl_lines
    jsonl_path = jsonl_lines[0].split("=", 1)[1].strip()
    rows = [json.loads(line) for line in open(jsonl_path, encoding="utf-8").read().splitlines()]
    assert len(rows) == 2
    assert {row["domain"] for row in rows} == {"portfolio_review"}
    assert {row["status"] for row in rows} == {"generated"}
