from __future__ import annotations

import json
import subprocess
import sys


def _safe_card() -> dict:
    return {
        "id": "market_safe_validation_example_v1",
        "version": 1,
        "status": "generated",
        "domain": "market_analysis",
        "title": "Market Safe Validation Example",
        "description": "Validate a simple generated market analysis skill card.",
        "input_patterns": ["validate market scenario"],
        "tags": ["market", "validation"],
        "evidence_required": {"tables": ["market.index_eod"]},
        "sql_templates": {
            "index_latest": "SELECT index_symbol, trade_date, close FROM market.index_eod LIMIT 5",
        },
        "tool_plan_template": [{"sql_templates": ["index_latest"]}],
        "output_contract": ["as_of_date", "index_rows"],
        "validation_rules": ["required_tables_exist", "sql_is_read_only"],
        "synthesis_guidance": "Summarize validated evidence only.",
    }


def test_validate_skill_scenarios_promotes_safe_and_marks_corrupt_failed(tmp_path):
    from terminal.skills.scenario_validation import validate_skill_scenarios

    source = tmp_path / "generated.jsonl"
    corrupt = {
        **_safe_card(),
        "id": "bad_runtime_card_v1",
        "status": "production",
        "title": "",
        "evidence_required": {"tables": ["not_a_schema.fake_table"]},
    }
    source.write_text(
        json.dumps(_safe_card(), sort_keys=True) + "\n" + json.dumps(corrupt, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = validate_skill_scenarios(source, output_dir=tmp_path / "validated")
    rows = [json.loads(line) for line in result.jsonl_path.read_text(encoding="utf-8").splitlines()]

    assert result.total == 2
    assert result.status_counts["review_pending"] == 1
    assert result.status_counts["test_failed"] == 1
    assert rows[0]["status"] == "review_pending"
    assert rows[0]["review"]["status"] == "pass"
    assert rows[1]["status"] == "test_failed"
    assert rows[1]["validation_errors"]

    report = result.report_path.read_text(encoding="utf-8")
    assert "Skill Scenario Validation Report" in report
    assert "review_pending: 1" in report
    assert "test_failed: 1" in report
    assert "bad_runtime_card_v1" in report


def test_validate_skill_scenarios_script_writes_report_for_safe_file(tmp_path):
    source = tmp_path / "generated.jsonl"
    source.write_text(json.dumps(_safe_card(), sort_keys=True) + "\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/validate_skill_scenarios.py",
            "--input-jsonl",
            str(source),
            "--output-dir",
            str(tmp_path / "validated"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "total=1" in result.stdout
    assert "review_pending=1" in result.stdout
    assert "report=" in result.stdout
