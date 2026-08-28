#!/bin/zsh
set -e

service="agent-adda-icloud-smtp"
account="pgorai@icloud.com"

echo "Agent Adda iCloud SMTP setup"
echo "Enter an Apple app-specific password (not your normal Apple Account password)."
read -s "app_password?App-specific password: "
echo

if [[ -z "$app_password" ]]; then
  echo "No password entered; nothing changed."
  exit 1
fi

if [[ ! "$app_password" =~ '^[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}$' ]]; then
  unset app_password
  echo "Invalid format. Expected: xxxx-xxxx-xxxx-xxxx"
  echo "Create an app-specific password at account.apple.com, then run this helper again."
  exit 1
fi

security add-generic-password -U -s "$service" -a "$account" -w "$app_password" >/dev/null
unset app_password
echo "Saved securely in macOS Keychain for $account."
echo "You may close this window and tell Codex: configured"
