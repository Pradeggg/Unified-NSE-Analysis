---
applyTo: "**"
---

# Agent Adda Publish Intelligence Report

When asked to post, publish, deploy, email, or notify recipients about an Agent Adda Market Intelligence report, follow `.agents/skills/agent-adda-publish-intelligence-report/SKILL.md`.

Core requirements:

- Validate the generated HTML before publication.
- Dry-run `scripts/push_to_www.py` before writing into `agentadda-www`.
- Run `npm run build` in `/Users/pradeepgorai/Documents/Projects/agentadda-www` before pushing.
- Verify the public `agentadda.in/stocks/reports/{slug}` and `agentadda.in/reports/{slug}.html` URLs return HTTP 200.
- Prepare an email dry-run or preview first.
- Do not send to the Agent Adda recipient list without explicit confirmation in the current conversation.
- Do not print API keys, SMTP passwords, Cloudflare tokens, or raw `.env` secrets.
- Keep all report and email language research-only and include Agent Adda/SEBI disclaimer framing.
