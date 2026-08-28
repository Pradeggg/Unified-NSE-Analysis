#!/usr/bin/env python3
"""Set up and validate Agent Adda WhatsApp Cloud API notifications."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal.whatsapp_dispatcher import WhatsAppConfig, load_config, send_whatsapp_message


DEFAULT_REPORT_BODY = """Published Agent Adda Market Intelligence for 24 Aug 2026:

Top Picks
https://agentadda.in/stocks/reports/top-picks-2026-08-24

Sector Rotation
https://agentadda.in/stocks/reports/sector-rotation-2026-08-24

Stage 2 Breakout Tracker
https://agentadda.in/stocks/reports/stage2-tracker-2026-08-24

Research only. Not investment advice."""


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _load_env() -> None:
    _load_env_file(ROOT / ".env")
    _load_env_file(ROOT.parent / ".env")


def _mask(value: str, *, keep: int = 4) -> str:
    if not value:
        return "missing"
    if len(value) <= keep:
        return "*" * len(value)
    return f"{'*' * max(4, len(value) - keep)}{value[-keep:]}"


def _recipient_list(args: argparse.Namespace, cfg: WhatsAppConfig) -> tuple[str, ...]:
    if args.recipient:
        return tuple(args.recipient)
    return cfg.default_recipients


def _print_status(cfg: WhatsAppConfig) -> int:
    print("Agent Adda WhatsApp Cloud API status")
    print(f"  enabled: {cfg.enabled}")
    print(f"  dry_run: {cfg.dry_run}")
    print(f"  graph_api_version: {cfg.graph_api_version}")
    print(f"  phone_number_id: {_mask(cfg.phone_number_id)}")
    print(f"  access_token: {_mask(cfg.access_token)}")
    print(f"  recipients: {len(cfg.default_recipients)} configured")
    print(f"  use_template: {cfg.use_template}")
    print(f"  template: {cfg.template_name} / {cfg.template_language}")

    gaps: list[str] = []
    if not cfg.enabled:
        gaps.append("WHATSAPP_ENABLED=true")
    if not cfg.phone_number_id:
        gaps.append("WHATSAPP_PHONE_NUMBER_ID")
    if not cfg.access_token and not cfg.dry_run:
        gaps.append("WHATSAPP_ACCESS_TOKEN")
    if not cfg.default_recipients:
        gaps.append("WHATSAPP_RECIPIENTS or --recipient")
    if gaps:
        print("\nSetup gaps:")
        for gap in gaps:
            print(f"  - {gap}")
        return 1
    print("\nSetup looks usable.")
    return 0


def _send(args: argparse.Namespace, *, live: bool) -> int:
    cfg = load_config()
    recipients = _recipient_list(args, cfg)
    if not recipients:
        print("No WhatsApp recipients configured. Pass --recipient or set WHATSAPP_RECIPIENTS.", file=sys.stderr)
        return 2

    if live and not args.confirm_live:
        print("Live send requires --confirm-live.", file=sys.stderr)
        return 2

    effective = replace(
        cfg,
        enabled=True,
        dry_run=not live,
        phone_number_id=cfg.phone_number_id or ("dry-run-phone-number-id" if not live else ""),
    )
    text = f"*Agent Adda Alert*\n{args.title}\n\n{args.body}\n\nResearch only. Not investment advice."
    result = send_whatsapp_message(text, recipients=recipients, config=effective)

    print(
        {
            "ok": result.ok,
            "status": result.status,
            "recipients_count": len(result.recipients),
            "dry_run_path": result.dry_run_path,
            "error": result.error,
        }
    )
    return 0 if result.ok else 1


def _open_channel_share(args: argparse.Namespace) -> int:
    body = (args.body or "").replace("—", "-").replace("–", "-").replace("•", "-")
    text = f"Agent Adda Market Intelligence\n\n{body.strip()}"
    if "Not investment advice." not in text:
        text += "\n\nResearch only. Not investment advice."
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=False)
    subprocess.run(["open", args.channel_url], check=False)
    share_url = "https://wa.me/?text=" + quote(text)
    print("Copied post text to clipboard.")
    print(f"Opened channel: {args.channel_url}")
    print(f"Fallback share URL: {share_url}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show sanitized WhatsApp API configuration status.")

    dry = sub.add_parser("dry-run", help="Create a WhatsApp payload without sending.")
    dry.add_argument("--recipient", action="append", help="Recipient phone number in international format.")
    dry.add_argument("--title", default="24 Aug 2026 reports published")
    dry.add_argument("--body", default=DEFAULT_REPORT_BODY)

    send = sub.add_parser("send-test", help="Send a live test message through Cloud API.")
    send.add_argument("--recipient", action="append", help="Recipient phone number in international format.")
    send.add_argument("--title", default="Agent Adda WhatsApp API test")
    send.add_argument("--body", default="This is an Agent Adda WhatsApp Cloud API test message.")
    send.add_argument("--confirm-live", action="store_true", help="Required for live sends.")

    channel = sub.add_parser("channel-post", help="Prepare a manual WhatsApp Channel post.")
    channel.add_argument(
        "--channel-url",
        default="https://whatsapp.com/channel/0029Vb8Nfus84Om5QuH2gG0r",
    )
    channel.add_argument("--body", default=DEFAULT_REPORT_BODY)
    return parser


def main() -> int:
    _load_env()
    args = build_parser().parse_args()
    if args.command == "status":
        return _print_status(load_config())
    if args.command == "dry-run":
        return _send(args, live=False)
    if args.command == "send-test":
        return _send(args, live=True)
    if args.command == "channel-post":
        return _open_channel_share(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
