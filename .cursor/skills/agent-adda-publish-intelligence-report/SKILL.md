---
name: agent-adda-publish-intelligence-report
description: Publish Agent Adda research/report HTML to agentadda.in Market Intelligence and prepare or send the recipient notification. Use when the user asks to post, publish, deploy, email, or notify recipients about an Agent Adda report.
---

# Agent Adda Publish Intelligence Report

Use this skill for the public report distribution workflow: validate a generated Agent Adda report, publish it into the `agentadda/www` website, verify the live `agentadda.in` URL, and prepare the email notification for the Agent Adda recipients.

## Scope

This skill applies to generated reports such as Deep Research, morning market, EOD market, sector rotation, top picks, portfolio analysis, and other Market Intelligence artifacts. It does not create the research from scratch; use the relevant research/report skill first, then use this skill for publication and notification.

## Repositories And Paths

Run commands from:

```bash
cd /Users/pradeepgorai/Documents/Projects/finance/Unified-NSE-Analysis
source .venv/bin/activate
```

Expected website repo:

```bash
/Users/pradeepgorai/Documents/Projects/agentadda-www
```

Publisher script:

```bash
.venv/bin/python scripts/push_to_www.py
```

The publisher copies HTML to `agentadda-www/public/reports/{slug}.html`, writes MDX metadata to `agentadda-www/src/content/stocks/reports/{slug}.mdx`, commits the website repo, and optionally pushes `origin main`.

## Required Inputs

Confirm or infer these before publishing:

- `html_path`: generated report HTML, preferably standalone/self-contained.
- `slug`: URL-safe slug, usually `{topic}-{report-type}-{yyyy-mm-dd}`.
- `title`: public report title.
- `excerpt`: short site-card description.
- `report_type`: one of the site-supported report types, especially `deep-research`, `morning-market`, `eod-report`, `sector-rotation`, `stage2-tracker`, `swing-playbook`, `top-picks`, `portfolio-analysis`, or `fo-alert`.
- `tickers`, `sector`, `tags`, `read_time`, and `date`.

For a Deep Research report, prefer:

```bash
--type deep-research
--tags "Deep Research,Fundamentals,Technical Analysis,Concall,NSE"
```

## Pre-Publish QA

Before pushing anything public:

1. Verify the report exists and is not truncated:

   ```bash
   ls -lh reports/path/to/report.html
   ```

2. Scan for obvious broken visible content:

   ```bash
   rg -n "Traceback|REPORT GENERATION FAILED|nan%|>nan<|undefined|PLACEHOLDER|TODO|file://|Embedded -" reports/path/to/report.html
   ```

3. Confirm the report has a title, explicit as-of date, source/evidence trail, and Agent Adda/SEBI research-only disclaimer.
4. If the report embeds charts, ensure publishable assets are same-origin or base64/self-contained. Avoid local `file://` links in public HTML.
5. If the user asked for report QA, use `agent-adda-report-qa` before publication.

## Publish Workflow

Always dry-run first:

```bash
.venv/bin/python scripts/push_to_www.py \
  --html reports/path/to/report.html \
  --slug public-slug-2026-08-24 \
  --title "Public Report Title - 24 Aug 2026" \
  --excerpt "Short public summary." \
  --type deep-research \
  --tickers LTFOODS \
  --sector "FMCG,Packaged Foods" \
  --tags "Deep Research,Fundamentals,Technical Analysis,NSE" \
  --read-time "18 min read" \
  --date 2026-08-24 \
  --dry-run
```

If the dry-run quality gate passes, publish into the website repo:

```bash
.venv/bin/python scripts/push_to_www.py \
  --html reports/path/to/report.html \
  --slug public-slug-2026-08-24 \
  --title "Public Report Title - 24 Aug 2026" \
  --excerpt "Short public summary." \
  --type deep-research \
  --tickers LTFOODS \
  --sector "FMCG,Packaged Foods" \
  --tags "Deep Research,Fundamentals,Technical Analysis,NSE" \
  --read-time "18 min read" \
  --date 2026-08-24
```

Then validate the website build:

```bash
cd /Users/pradeepgorai/Documents/Projects/agentadda-www
npm run build
git status --short
```

Push only after the build passes and the publish commit is the intended change:

```bash
git push origin main
```

The public URLs are:

```text
https://agentadda.in/stocks/reports/{slug}
https://agentadda.in/reports/{slug}.html
```

Poll until both return HTTP 200 and `latest.json` reflects the new metadata:

```bash
curl -s -L -o /tmp/agentadda_report.html -w '%{http_code} %{url_effective} %{size_download}\n' https://agentadda.in/stocks/reports/{slug}
curl -s -L -o /tmp/agentadda_standalone.html -w '%{http_code} %{url_effective} %{size_download}\n' https://agentadda.in/reports/{slug}.html
curl -s -L https://agentadda.in/stocks/reports/latest.json | python3 -m json.tool | rg "{slug}|deep-research"
```

If `wrangler deploy` is needed, do not use a temporary Cloudflare account. Use the configured production credentials only. If `CLOUDFLARE_API_TOKEN` is missing, report that manual deploy is blocked and rely on the GitHub/Vercel/Cloudflare integration or ask the user to provide the credential in the environment.

## Notification Workflow

Recipient lists live in:

```text
config/report_recipients.yml
```

Email provider settings come from `.env`; do not print secrets. Check presence only:

```bash
security find-generic-password -s agent-adda-icloud-smtp -a pgorai@icloud.com -w >/dev/null 2>&1; echo $?
```

Prepare a dry-run notification first. If `OPENAI_API_KEY` is present, the email dispatcher can synthesize the body. If it is missing, create a concise hand-authored HTML notification under `reports/generated/` and use that body or use `/email --dry-run` as a fallback preview.

Dry-run example:

```bash
.venv/bin/python - <<'PY'
from terminal.email_dispatcher import run_email_command
cmd = (
    '/email reports/path/to/report.html '
    '--to pgorai@icloud.com '
    '--bcc recipient1@example.com,recipient2@example.com '
    '--as both --dry-run '
    '--subject "Agent Adda Deep Research: Report Title - 24 Aug 2026" '
    '--note "Mention the published Market Intelligence > Deep Research URL, key evidence-backed sections, and research-only disclaimer."'
)
print(run_email_command(cmd, agent=None))
PY
```

Before actually sending, explicitly confirm with the user:

- live report URL;
- subject;
- To and Bcc counts or addresses;
- whether the report is attached, linked, or both.

Do not send email to the distribution list without explicit confirmation in the current conversation. When approved, use the same command without `--dry-run` and with `--send`, or call `send_report_email` with `send=True`.

## Safety And Compliance

- Public publish and email send are external side effects. Treat them as high visibility.
- Never expose API keys, SMTP passwords, Cloudflare tokens, or raw `.env` secrets.
- Preserve unrelated dirty worktree changes in both repos.
- Avoid investment-instruction language. Use research stance, watch plan, invalidation, and risk language.
- Published report and notification must state that Agent Adda is not acting as a SEBI-registered investment adviser, research analyst, broker, or portfolio manager.
- If live data and EOD data differ, preserve both timestamps and explain the difference.

## Completion Report

When finished, report:

- local report path;
- website repo commit hash;
- build result;
- live report URL and standalone HTML URL;
- `latest.json` verification;
- email preview path;
- whether notification was sent or awaiting confirmation.
