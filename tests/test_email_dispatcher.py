from __future__ import annotations

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


def test_applemail_script_builds_message_with_sender_recipients_and_attachments(tmp_path):
    html_path = tmp_path / "body.html"
    plain_path = tmp_path / "body.txt"
    attachment = tmp_path / "report.html"
    html_path.write_text("<html><body><b>Hello</b></body></html>", encoding="utf-8")
    plain_path.write_text("Hello", encoding="utf-8")
    attachment.write_text("<html>report</html>", encoding="utf-8")

    script = email_dispatcher._build_applemail_applescript(
        subject="Apple Mail check",
        html_body_path=html_path,
        plain_body_path=plain_path,
        to_addrs=["pgorai@example.com"],
        bcc_addrs=["team@example.com"],
        attachments=[attachment],
        send_immediately=False,
        sender="pgorai@icloud.com",
    )

    assert 'tell application "Mail"' in script
    assert 'set sender of newMsg to "pgorai@icloud.com"' in script
    assert "make new to recipient" in script
    assert "make new bcc recipient" in script
    assert "make new attachment" in script
    assert "set visible of newMsg to true" in script


def test_icloud_provider_defaults_to_icloud_smtp(monkeypatch):
    monkeypatch.setenv("AGENT_ADDA_EMAIL_PROVIDER", "icloud")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.setenv("SMTP_USER", "pgorai@icloud.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-specific-password")
    monkeypatch.setenv("SMTP_FROM", "pgorai@icloud.com")

    cfg = email_dispatcher._smtp_config()

    assert cfg["provider"] == "icloud"
    assert cfg["host"] == "smtp.mail.me.com"
    assert cfg["port"] == 587
    assert cfg["user"] == "pgorai@icloud.com"
    assert cfg["from_addr"] == "pgorai@icloud.com"


def test_icloud_sent_archive_uses_special_use_mailbox(monkeypatch):
    calls = {}

    class FakeIMAP:
        def __init__(self, host, port, timeout):
            calls["connect"] = (host, port, timeout)

        def login(self, user, password):
            calls["login"] = (user, password)
            return "OK", []

        def list(self):
            return "OK", [
                b'(\\HasNoChildren) "/" "Archive"',
                b'(\\HasNoChildren \\Sent) "/" "Sent Messages"',
            ]

        def append(self, folder, flags, date_time, message):
            calls["append"] = (folder, flags, message)
            return "OK", [b"saved"]

        def logout(self):
            calls["logout"] = True

    monkeypatch.setattr(email_dispatcher.imaplib, "IMAP4_SSL", FakeIMAP)
    message = email_dispatcher.MimeEmailMessage()
    message["Subject"] = "Archive check"
    message.set_content("Hello")

    folder = email_dispatcher._archive_icloud_sent_copy(
        message,
        {"user": "pgorai@icloud.com", "password": "app-password"},
    )

    assert folder == "Sent Messages"
    assert calls["connect"] == ("imap.mail.me.com", 993, 45)
    assert calls["login"] == ("pgorai@icloud.com", "app-password")
    assert calls["append"][0] == '"Sent Messages"'
    assert calls["logout"] is True


def test_applemail_provider_dispatches_via_applemail_script(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ADDA_EMAIL_PROVIDER", "applemail")
    monkeypatch.setenv("SMTP_FROM", "pgorai@icloud.com")
    monkeypatch.setattr(email_dispatcher, "LOG_DIR", tmp_path)

    captured = {}

    def fake_run(cmd, capture_output, text):
        captured["cmd"] = cmd

        class Result:
            returncode = 0
            stderr = ""

        return Result()

    monkeypatch.setattr(email_dispatcher.subprocess, "run", fake_run)

    status = email_dispatcher.send_via_outlook(
        subject="Apple Mail dispatch",
        html_body="<b>Hello</b>",
        to_addrs=["pgorai@example.com"],
        bcc_addrs=[],
        attachments=[],
        send_immediately=False,
    )

    assert status == "draft opened in Apple Mail"
    assert captured["cmd"][0] == "osascript"
    assert 'tell application "Mail"' in captured["cmd"][2]
