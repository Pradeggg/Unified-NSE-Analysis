from pathlib import Path

from terminal.report_validation import validate_html_report
from report_validation import _required_term_present


def test_validate_html_report_reports_missing_and_empty_links(tmp_path: Path):
    report = tmp_path / "report.html"
    empty = tmp_path / "empty.html"
    empty.write_text("   ", encoding="utf-8")
    report.write_text(
        '<html><body><a href="missing.html">missing</a>'
        '<a href="empty.html">empty</a></body></html>',
        encoding="utf-8",
    )

    result = validate_html_report(report)

    issues = {(check.status, check.issue) for check in result.checks}
    assert ("fail", "missing_file") in issues
    assert ("warn", "empty_linked_html") in issues


def test_validate_html_report_checks_anchor_targets(tmp_path: Path):
    report = tmp_path / "report.html"
    report.write_text(
        '<html><body><a href="#present">present</a>'
        '<a href="#missing">missing</a><h2 id="present">Present</h2></body></html>',
        encoding="utf-8",
    )

    result = validate_html_report(report)

    assert any(check.issue == "missing_anchor" and check.href == "#missing" for check in result.checks)
    assert result.summary()["fail"] == 1


def test_validate_html_report_passes_nonempty_linked_stock_page(tmp_path: Path):
    detail = tmp_path / "AAA.html"
    detail.write_text("<html><body><table><tr><td>AAA</td></tr></table></body></html>", encoding="utf-8")
    report = tmp_path / "report.html"
    report.write_text('<html><body><a href="AAA.html">AAA</a></body></html>', encoding="utf-8")

    result = validate_html_report(report)

    assert result.summary()["fail"] == 0
    assert any(check.status == "pass" and check.href == "AAA.html" for check in result.checks)


def test_required_report_term_matching_is_case_insensitive_and_whitespace_tolerant():
    text = "Triple-confirmed names include Strategy + VCP + Sector and dual confirmations."

    assert _required_term_present(text, "vcp+sector")
