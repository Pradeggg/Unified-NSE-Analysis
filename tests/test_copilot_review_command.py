from terminal.copilot_workflows.review import handle_review_command, render_review


def test_review_findings_first_for_missing_target():
    text = handle_review_command("/review portfolio strategy")

    assert text.startswith("# Review")
    assert "**Findings First**" in text
    assert "Evidence Gaps" in text
    assert "Suggested Next Checks" in text


def test_review_inspects_local_artifact(tmp_path):
    report = tmp_path / "report.html"
    report.write_text("<a href=\"#stock-AAA\">AAA</a>\nNo data", encoding="utf-8")

    text = render_review(str(report), cwd=tmp_path)

    assert "Artifact exists" in text
    assert "anchor-style links" in text
    assert "missing-data markers" in text
