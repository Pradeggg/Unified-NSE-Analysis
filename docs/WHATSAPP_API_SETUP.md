# Agent Adda WhatsApp API Setup

Agent Adda uses Meta WhatsApp Business Platform Cloud API for direct WhatsApp notifications. Keep secrets in `.env`; do not commit access tokens.

## Supported Paths

- Direct report notifications to opted-in recipients: supported by `terminal/whatsapp_dispatcher.py`.
- Dry-run payload generation before real sends: supported by `scripts/setup_whatsapp_api.py`.
- WhatsApp Channel post preparation: supported as a manual clipboard/open helper.
- Fully automated public Channel posting: not wired because the normal Cloud API messaging path is for WhatsApp Business messages, not Agent Adda channel publishing.

## Meta Setup Checklist

1. Create or use a Meta Business portfolio.
2. Create a Meta app with WhatsApp enabled.
3. Add or select a WhatsApp Business Account and phone number.
4. Copy the Phone Number ID from the WhatsApp API setup page.
5. Create a system-user access token with WhatsApp messaging permissions.
6. Add opted-in recipient numbers for initial delivery testing.
7. If sending business-initiated messages outside an active user window, create and approve a WhatsApp template such as `agent_adda_alert`.

Official references:

- WhatsApp Cloud API get started: https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started
- WhatsApp templates: https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/overview
- WhatsApp Groups API: https://developers.facebook.com/documentation/business-messaging/whatsapp/groups

## Environment

Add this to `Unified-NSE-Analysis/.env` or the parent finance `.env`:

```bash
WHATSAPP_ENABLED=true
WHATSAPP_DRY_RUN=true
WHATSAPP_GRAPH_API_VERSION=v23.0
WHATSAPP_PHONE_NUMBER_ID=123456789012345
WHATSAPP_ACCESS_TOKEN=EAAB...
WHATSAPP_RECIPIENTS=919xxxxxxxxx,919yyyyyyyyy
WHATSAPP_USE_TEMPLATE=false
WHATSAPP_TEMPLATE_NAME=agent_adda_alert
WHATSAPP_TEMPLATE_LANGUAGE=en
WHATSAPP_TIMEOUT_SECONDS=15
```

Keep `WHATSAPP_DRY_RUN=true` until dry-run and one controlled test pass.

## Validate

```bash
source .venv/bin/activate
python scripts/setup_whatsapp_api.py status
python scripts/setup_whatsapp_api.py dry-run --recipient 919xxxxxxxxx
```

The dry-run writes a payload JSON under `logs/whatsapp_dry_run_*.json`.

## Live Test

After checking the dry-run payload:

```bash
WHATSAPP_DRY_RUN=false python scripts/setup_whatsapp_api.py send-test \
  --recipient 919xxxxxxxxx \
  --confirm-live
```

## Channel Posting

For the Agent Adda WhatsApp Channel, use the manual helper:

```bash
python scripts/setup_whatsapp_api.py channel-post
```

It copies the report post to the clipboard and opens:

```text
https://whatsapp.com/channel/0029Vb8Nfus84Om5QuH2gG0r
```

Paste the content as a channel admin and publish.
