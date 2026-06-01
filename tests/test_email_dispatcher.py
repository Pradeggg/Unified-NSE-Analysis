from pathlib import Path

from terminal import email_dispatcher


class _Agent:
    backend = None


def test_parse_email_command_accepts_subject_override(tmp_path, monkeypatch):
    report = tmp_path / "apollo.md"
    report.write_text("Apollo Micro Systems analysis", encoding="utf-8")

    cmd = email_dispatcher.parse_email_command(
        f'/email {report} --to pgorai@example.com --subject "APOLLO MICROSYSTEMS ANALYSIS" --dry-run'
    )

    assert cmd.error == ""
    assert cmd.subject == "APOLLO MICROSYSTEMS ANALYSIS"
    assert cmd.to == ["pgorai@example.com"]
    assert cmd.report_path == report


def test_run_email_command_uses_subject_override_for_dry_run(tmp_path, monkeypatch):
    report = tmp_path / "apollo.md"
    report.write_text("Apollo Micro Systems analysis", encoding="utf-8")
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(email_dispatcher, "LOG_DIR", log_dir)

    result = email_dispatcher.run_email_command(
        f'/email {report} --to pgorai@example.com --subject "APOLLO MICROSYSTEMS ANALYSIS" --dry-run',
        _Agent(),
    )

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["subject"] == "APOLLO MICROSYSTEMS ANALYSIS"
    assert Path(result["body_path"]).exists()
