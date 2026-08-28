#!/usr/bin/env bash
# Agent Adda — Intraday Alerts launcher
# Called by com.agentadda.intraday_alerts launchd agent at 09:10 IST Mon–Fri.
# Sources .env from the parent finance/ directory so no secrets live in the plist.
#
# Watch live output:
#   tail -f ~/.agent-adda/logs/intraday_alerts.log
#   tail -f Unified-NSE-Analysis/logs/intraday_alerts_latest.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR/.."
ENV_FILE="$ROOT/../.env"

# Load environment secrets
if [[ -f "$ENV_FILE" ]]; then
    # Export only non-comment, non-blank lines
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

PYTHON="$ROOT/.venv/bin/python3"

exec "$PYTHON" -m terminal.live_intraday_alerts \
    --cycles 0 \
    --interval 60 \
    --send
