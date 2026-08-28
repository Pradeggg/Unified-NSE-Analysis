#!/bin/zsh
set -e

service="agent-adda-gmail-smtp"
account="agentadda.in@gmail.com"

echo "Agent Adda Gmail SMTP setup"
echo "Enter the 16-character Google app password (not the normal account password)."
read -s "app_password?Google app password: "
echo

# Google displays app passwords in four groups. Accept copied spaces or
# hyphens, then store the normalized 16-character value for SMTP.
app_password="${app_password// /}"
app_password="${app_password//$'\t'/}"
app_password="${app_password//-/}"
if [[ ! "$app_password" =~ '^[A-Za-z0-9]{16}$' ]]; then
  unset app_password
  echo "Invalid format. Expected a 16-character Google app password."
  echo "Create one at myaccount.google.com/apppasswords, then run this helper again."
  exit 1
fi

security add-generic-password -U -s "$service" -a "$account" -w "$app_password" >/dev/null
unset app_password
echo "Saved securely in macOS Keychain for $account."
echo "You may close this window and tell Codex: configured"
