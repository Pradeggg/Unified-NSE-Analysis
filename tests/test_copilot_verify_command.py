from terminal.copilot_workflows.verify import handle_verify_command, render_verify


def test_verify_reports_runs_without_llm(tmp_path):
    latest = tmp_path / "reports/latest"
    latest.mkdir(parents=True)
    (latest / "results_analysis.html").write_text("ok", encoding="utf-8")

    text = render_verify("reports", cwd=tmp_path)

    assert "Verification" in text
    assert "results analysis report" in text
    assert "PASS" in text
    assert "FAIL" in text


def test_verify_quality_breakouts_points_to_smoke_command():
    text = handle_verify_command("/verify screen quality-breakouts")

    assert "/screen quality-breakouts --explain --tv" in text
    assert "Summary" in text
