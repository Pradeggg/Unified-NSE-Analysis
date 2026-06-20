# Grounded Periodic Market Analysis Skills Design

Date: 2026-06-20

## Objective

Create reusable Agent Adda analysis skills for hourly, daily, and weekly market research. Each workflow must be grounded in local Agent Adda data first, then current web evidence, and must avoid unsupported market, stock, sector, or portfolio conclusions.

## Skills Created

Codex-discoverable skills:

- `agent-adda-hourly-analysis`
- `agent-adda-daily-analysis`
- `agent-adda-weekly-analysis`

Location:

- `/Users/pgorai/.codex/skills/`

## Shared Grounding Rules

Each skill requires:

- Local Agent Adda evidence first: reports, logs, PostgreSQL snapshots, generated outputs, CSV datasets.
- Web verification for current filings, events, macro/news, global markets, commodity moves, and other unstable facts.
- Explicit source trail.
- Missing-evidence handling.
- Separation of active candidates from watch-only/tracker context.
- Rationale and invalidation for every actionable name.

## Runtime Skill Store Backlog

Promote these into Agent Adda runtime skills:

1. `hourly_market_analysis`
   - Trigger: hourly, intraday, current market, live commentary, active alerts.
   - Inputs: latest dashboard, intraday alerts, F&O, breadth, sector strength, news.
   - Output: market state, changes, active/watch setups, next actions.

2. `daily_market_analysis`
   - Trigger: daily analysis, EOD, today's report, top picks, paper trading daily review.
   - Inputs: daily refresh outputs, EOD report, top picks, sector rotation, paper trading.
   - Output: daily market narrative, breadth, sectors, top picks, risk plan.

3. `weekly_market_analysis`
   - Trigger: weekly review, weekend report, next-week plan, sector rotation over week.
   - Inputs: week of EOD reports, sector breadth, paper trading, portfolio lab, web macro/news.
   - Output: weekly regime, leadership changes, portfolio impact, next-week playbook.

## Acceptance Criteria

- A user can ask "hourly analysis", "daily analysis", or "weekly analysis" and get a grounded report.
- The answer identifies data timestamp and mode.
- Web search is used for current or unstable facts.
- Any missing local or web evidence is called out.
- The final response includes rationale, levels, risks, and source trail.
