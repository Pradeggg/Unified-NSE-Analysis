"""WhatsApp notification delivery for Agent Adda.

Uses Meta's WhatsApp Business Platform Cloud API. The module is intentionally
small and env/config driven so alerts can opt in without hardcoding secrets.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "whatsapp.yml"
LOG_DIR = ROOT / "logs"


@dataclass(frozen=True)
class WhatsAppConfig:
    enabled: bool = False
    dry_run: bool = True
    access_token: str = ""
    phone_number_id: str = ""
    graph_api_version: str = "v23.0"
    default_recipients: tuple[str, ...] = ()
    timeout_seconds: int = 15
    template_name: str = "agent_adda_alert"
    template_language: str = "en"
    use_template: bool = False


@dataclass
class WhatsAppSendResult:
    ok: bool
    status: str
    recipients: list[str] = field(default_factory=list)
    error: str = ""
    responses: list[dict[str, Any]] = field(default_factory=list)
    dry_run_path: str = ""


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _load_yaml_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        import yaml

        loaded = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _split_recipients(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        parts = value.replace(";", ",").split(",")
    elif isinstance(value, (list, tuple)):
        parts = [str(v) for v in value]
    else:
        parts = []
    return tuple(p.strip() for p in parts if p and p.strip())


def load_config() -> WhatsAppConfig:
    """Load WhatsApp config from config/whatsapp.yml and environment.

    Environment variables take precedence:
      WHATSAPP_ENABLED, WHATSAPP_DRY_RUN, WHATSAPP_ACCESS_TOKEN,
      WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_RECIPIENTS, WHATSAPP_USE_TEMPLATE,
      WHATSAPP_TEMPLATE_NAME, WHATSAPP_TEMPLATE_LANGUAGE,
      WHATSAPP_GRAPH_API_VERSION.
    """

    data = _load_yaml_config()
    recipients = _split_recipients(
        os.getenv("WHATSAPP_RECIPIENTS") or data.get("default_recipients")
    )

    return WhatsAppConfig(
        enabled=_truthy(os.getenv("WHATSAPP_ENABLED", data.get("enabled", False))),
        dry_run=_truthy(os.getenv("WHATSAPP_DRY_RUN", data.get("dry_run", True))),
        access_token=os.getenv("WHATSAPP_ACCESS_TOKEN", str(data.get("access_token") or "")),
        phone_number_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID", str(data.get("phone_number_id") or "")),
        graph_api_version=os.getenv(
            "WHATSAPP_GRAPH_API_VERSION",
            str(data.get("graph_api_version") or "v23.0"),
        ),
        default_recipients=recipients,
        timeout_seconds=int(os.getenv("WHATSAPP_TIMEOUT_SECONDS", data.get("timeout_seconds", 15))),
        template_name=os.getenv("WHATSAPP_TEMPLATE_NAME", str(data.get("template_name") or "agent_adda_alert")),
        template_language=os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", str(data.get("template_language") or "en")),
        use_template=_truthy(os.getenv("WHATSAPP_USE_TEMPLATE", data.get("use_template", False))),
    )


def _normalise_msisdn(value: str) -> str:
    """Return digits-only international phone number, e.g. 919876543210."""
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _message_payload(to: str, text: str, config: WhatsAppConfig) -> dict[str, Any]:
    if config.use_template:
        return {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": config.template_name,
                "language": {"code": config.template_language},
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": text[:1024]}],
                    }
                ],
            },
        }

    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": text[:4096]},
    }


def _write_dry_run(messages: list[dict[str, Any]]) -> str:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"whatsapp_dry_run_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(messages, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def send_whatsapp_message(
    text: str,
    *,
    recipients: list[str] | tuple[str, ...] | None = None,
    config: WhatsAppConfig | None = None,
) -> WhatsAppSendResult:
    """Send one WhatsApp message to configured recipients.

    Returns ok=False when disabled or misconfigured; callers should treat this
    as non-fatal for market alerts.
    """

    cfg = config or load_config()
    tos = [_normalise_msisdn(r) for r in (recipients or cfg.default_recipients)]
    tos = [r for r in tos if r]
    if not cfg.enabled:
        return WhatsAppSendResult(ok=False, status="disabled", recipients=tos)
    if not tos:
        return WhatsAppSendResult(ok=False, status="no_recipients", error="No WhatsApp recipients configured")
    if not cfg.phone_number_id:
        return WhatsAppSendResult(ok=False, status="missing_phone_number_id", recipients=tos)
    if not cfg.access_token and not cfg.dry_run:
        return WhatsAppSendResult(ok=False, status="missing_access_token", recipients=tos)

    messages = [_message_payload(to, text, cfg) for to in tos]
    if cfg.dry_run:
        path = _write_dry_run(messages)
        return WhatsAppSendResult(ok=True, status="dry_run", recipients=tos, dry_run_path=path)

    url = f"https://graph.facebook.com/{cfg.graph_api_version}/{cfg.phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {cfg.access_token}",
        "Content-Type": "application/json",
    }
    responses: list[dict[str, Any]] = []
    errors: list[str] = []
    for payload in messages:
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=cfg.timeout_seconds)
            try:
                body: Any = response.json()
            except ValueError:
                body = {"text": response.text}
            responses.append({"status_code": response.status_code, "body": body})
            if response.status_code >= 300:
                errors.append(f"{payload.get('to')}: HTTP {response.status_code}")
        except Exception as exc:
            errors.append(f"{payload.get('to')}: {exc}")

    return WhatsAppSendResult(
        ok=not errors,
        status="sent" if not errors else "partial_failure",
        recipients=tos,
        error="; ".join(errors),
        responses=responses,
    )


def send_market_alert(
    *,
    title: str,
    body: str,
    recipients: list[str] | tuple[str, ...] | None = None,
) -> WhatsAppSendResult:
    text = f"*Agent Adda Alert*\n{title}\n\n{body}\n\nResearch only. Not investment advice."
    return send_whatsapp_message(text, recipients=recipients)

