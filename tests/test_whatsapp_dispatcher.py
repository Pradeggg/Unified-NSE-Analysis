from __future__ import annotations

import json
from pathlib import Path

from terminal.whatsapp_dispatcher import WhatsAppConfig, send_whatsapp_message


def test_send_whatsapp_message_disabled_is_non_fatal() -> None:
    result = send_whatsapp_message(
        "Test",
        recipients=["+91 98765 43210"],
        config=WhatsAppConfig(enabled=False),
    )

    assert result.ok is False
    assert result.status == "disabled"
    assert result.recipients == ["919876543210"]


def test_send_whatsapp_message_dry_run_writes_payload() -> None:
    result = send_whatsapp_message(
        "Breakout alert",
        recipients=["+91 98765 43210"],
        config=WhatsAppConfig(
            enabled=True,
            dry_run=True,
            phone_number_id="1234567890",
            access_token="not-used-in-dry-run",
        ),
    )

    assert result.ok is True
    assert result.status == "dry_run"
    assert result.recipients == ["919876543210"]
    path = Path(result.dry_run_path)
    assert path.exists()
    payloads = json.loads(path.read_text(encoding="utf-8"))
    assert payloads[0]["messaging_product"] == "whatsapp"
    assert payloads[0]["to"] == "919876543210"
    assert payloads[0]["text"]["body"] == "Breakout alert"

