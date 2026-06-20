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


def test_outlook_html_body_is_normalized_to_full_document():
    html = email_dispatcher._ensure_html_document(
        '<div style="color:#111827;"><b>Rendered</b> alert</div>'
    )

    assert html.lstrip().lower().startswith("<!doctype html>")
    assert "<html>" in html.lower()
    assert '<meta http-equiv="Content-Type"' in html
    assert "<body" in html.lower()
    assert "<b>Rendered</b> alert" in html


def test_outlook_script_uses_html_mode_with_plain_text_fallback(tmp_path):
    html_path = tmp_path / "body.html"
    plain_path = tmp_path / "body.txt"
    html_path.write_text("<html><body><b>Hello</b></body></html>", encoding="utf-8")
    plain_path.write_text("Hello", encoding="utf-8")

    script = email_dispatcher._build_outlook_applescript(
        subject="HTML render check",
        html_body_path=html_path,
        plain_body_path=plain_path,
        to_addrs=["pgorai@example.com"],
        bcc_addrs=[],
        attachments=[],
        send_immediately=False,
    )

    assert "if has html of newMsg then" in script
    assert "set content of newMsg to htmlBody" in script
    assert "set plain text content of newMsg to plainBody" in script
    assert "make new to recipient" in script
    assert "open newMsg" in script
