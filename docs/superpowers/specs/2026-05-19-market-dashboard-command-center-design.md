# Market Dashboard Command Center Design

Date: 2026-05-19
Scope: `/dashboard` and `/dash` in `nse_agent.py`

## Goal

Upgrade the existing live Rich terminal `/dashboard` into a market command center and add an optional HTML dashboard artifact. The dashboard must provide more details, reactions, and research actions while preserving source-backed discipline and research-only framing.

## Current Baseline

The current terminal dashboard already fetches:

- Live market overview.
- Intraday recap.
- Market breadth.
- Top gainers and losers.
- FII/DII activity.
- Global market assessment.
- Latest catalysts.
- NIFTY option chain.
- NIFTY futures analysis.
- High relative-strength screener.

It renders a Rich terminal dashboard with tape, ticker, breadth gauge, index momentum, sector strength, movers, F&O, RS screener, alerts, and narrative.

## Desired Behavior

`/dashboard` and `/dash` remain live terminal dashboards by default.

New flags:

- `/dashboard --html`: generate a standalone HTML command-center dashboard and print the file path.
- `/dashboard --open`: generate the HTML dashboard and open it with the OS browser opener.
- `/dashboard --once`: render one terminal snapshot and exit, useful for tests and quick checks.
- `/dashboard --drilldown`: start the terminal dashboard with top-index stock drilldown expanded.

Focus text still works:

- `/dashboard banks`
- `/dashboard banks --html`

## Reaction Engine

Add deterministic reaction helpers that convert existing snapshot evidence into concise market reactions. Reactions are labels with evidence, not advice.

Examples:

- `Risk-on confirmation`: NIFTY positive, breadth positive, VIX not rising.
- `Risk-off pressure`: NIFTY negative, breadth negative, VIX rising.
- `Breadth divergence`: headline index up while declines exceed advances.
- `F&O support active`: PCR constructive and put OI support visible.
- `F&O resistance overhead`: call OI concentration above spot and weak futures basis.
- `Sector rotation active`: sector leadership clearly differs from headline index.
- `Mover anomaly`: top mover above configured percentage threshold.
- `Data degraded`: required source failed or returned stale/unavailable data.

Each reaction includes:

- Label.
- Severity: `positive`, `warning`, `negative`, or `neutral`.
- Confidence: `high`, `medium`, or `low`.
- Evidence string.
- Suggested research command.

## Action Board

Add deterministic action cards based on reactions. These are research actions, not trading instructions.

Examples:

- `Confirm momentum`: `/scan momentum`
- `Check F&O map`: `/fno NIFTY`
- `Find relative strength`: `/screen highrs`
- `Review events/results`: `/results-feed`
- `Inspect movers`: `/analyze SYMBOL`
- `Run strategy research`: `/strategy-council SYMBOL`
- `Stay defensive`: wait for breadth repair and avoid chase wording.
- `Inspect VCP pocket`: `/scan vcp`
- `Check Supertrend alignment`: `/scan supertrend`
- `Confirm MTF setup`: `/intraday SYMBOL`
- `Watch VWAP reclaim`: `/scan vwap`

Each action card includes:

- Action title.
- Command.
- Why this action appears.
- Risk note.

## Opportunity Radar

Add an action-driven opportunity panel that identifies research candidates and market pockets worth inspecting. It must rank opportunities by evidence alignment, not by a buy/sell claim.

Opportunity inputs:

- Strongest indices and sectors from live index tape.
- Top gainers and losers from the current mover feed.
- High relative-strength screener rows.
- Intraday screener evidence when already available in the snapshot.
- Existing setup names from the platform: VCP, Supertrend, VWAP reclaim, ORB/breakout, momentum, and multi-timeframe confirmation.

Opportunity fields:

- Label, for example `Pocket of Strength`, `VCP Candidate`, `Supertrend Confirmation`, `MTF Confirmation`, `VWAP Reclaim Watch`, or `ORB Follow-through`.
- Symbol or scope.
- Directional research side: `long-watch`, `short-watch`, or `neutral`.
- Confidence: `high`, `medium`, or `low`.
- Evidence string with source fields.
- Setup tags.
- Suggested command.
- Risk note and invalidation prompt.

The dashboard may use deterministic inference only from returned fields. If a VCP, Supertrend, VWAP, ORB, or multi-timeframe signal is not present, it can suggest the relevant scan command but must not claim that formation is confirmed.

## F&O Detail Layer

Add a richer F&O section for NIFTY and BANKNIFTY when data is available. If BANKNIFTY data is unavailable from the existing tool path, the dashboard must show it as unavailable rather than infer.

Fields:

- Expiry.
- Spot/underlying reference when returned by the tool.
- PCR.
- Max pain.
- Top call OI strikes as resistance zones.
- Top put OI strikes as support zones.
- Futures basis and basis percentage.
- Cost of carry.
- Rollover when returned by the tool.
- Tool/source status.

F&O reactions:

- `Put support active`: high put OI support with constructive PCR.
- `Call wall overhead`: high call OI resistance near/above spot.
- `Futures premium expanding`: positive futures basis and constructive tape.
- `Futures discount warning`: negative basis with weak tape.
- `Expiry compression`: close-to-expiry context when available.

F&O actions:

- `/fno NIFTY`
- `/fno BANKNIFTY`
- `/options NIFTY`
- `/strategy NIFTY`

All F&O language remains research-only and must avoid directional trade instructions.

## Top Indices Drilldown

Add a drilldown for the top moving/leading indices and their top stocks.

Terminal behavior:

- While `/dashboard` is running, pressing `Enter` toggles the expanded “Top Stocks in Top Indices” panel.
- `/dashboard --drilldown` starts with this panel expanded.
- `/dashboard --once --drilldown` renders one expanded snapshot for testing.
- If interactive key capture is unavailable in the current terminal environment, the dashboard should still support `--drilldown`.

HTML behavior:

- Clicking an index card expands/collapses its top stocks.
- The page should work without a server or external JavaScript.

Data source behavior:

- The dashboard identifies top indices from the current live overview by percentage move, excluding `INDIA VIX`.
- For the top 3 indices, fetch top constituents or top gainers/losers through existing tools where possible.
- If a constituent-level index scan is unavailable, show the nearest available evidence: index-level movement plus NIFTY 500 top movers.
- Missing drilldown data must be labeled.

Top-stock fields:

- Symbol.
- Price/last when available.
- Percent change.
- Volume/velocity when available.
- Source label.
- Quick research actions: `/analyze SYMBOL`, `/intraday SYMBOL`, `/strategy-council SYMBOL`.

## Terminal Layout

Keep terminal panels dense, readable, and screen-fitting.

Large terminal layout:

- Header ticker.
- Market pulse cockpit: tape bias, breadth gauge, index momentum, mover velocity.
- Reaction Engine panel.
- Action Board panel.
- Sector Radar panel.
- F&O Control panel.
- Top Stocks in Top Indices drilldown panel, toggled by `Enter`.
- Movers and catalysts panel.
- Evidence/freshness strip.

Compact terminal layout:

- Ticker.
- Tape bias and breadth gauge.
- Top reactions.
- Top actions.
- F&O one-line readout.
- Drilldown hint or expanded top-stock list when enabled.
- Movers/news one-line readout.

## HTML Dashboard

Generate a self-contained HTML file under `reports/dashboards/`.

The HTML dashboard should be a polished command-center view with:

- Market Pulse.
- Reaction Engine.
- Action Board.
- Opportunity Radar.
- Sector Radar.
- F&O Control Panel.
- Click-to-expand Top Indices and Top Stocks.
- Breadth Internals.
- Movers.
- Catalyst Tape.
- RS Leaders.
- Source/Freshness Audit.

The HTML can use static inline CSS and data embedded from the current snapshot. It must not require a dev server.

Visual style:

- Professional command-center interface.
- Dark, high-contrast but not one-note.
- Dense, scannable panels.
- Clear severity colors.
- No decorative orb/blob backgrounds.
- No marketing hero layout.

## Source and Safety Rules

- Every reaction and action must derive from existing snapshot fields.
- If evidence is missing, the dashboard must say unavailable rather than infer.
- No investment advice wording.
- Use research language: `monitor`, `confirm`, `review`, `inspect`, `screen`, `wait`.
- Avoid buy/sell commands.
- Show source/tool status where practical.

## Implementation Notes

Primary edits:

- `nse_agent.py`
  - Add reaction helper functions.
  - Add action helper functions.
  - Add opportunity radar helper functions for pockets of strength, VCP, Supertrend, VWAP, ORB, and multi-timeframe confirmation.
  - Add F&O detail helpers for NIFTY and BANKNIFTY.
  - Add top-index drilldown data helpers.
  - Extend terminal renderable.
  - Add HTML renderer/writer.
  - Extend `/dashboard` command parsing for `--html`, `--open`, `--once`, and `--drilldown`.

Tests:

- `tests/test_market_dashboard_view.py`
  - Reaction engine returns expected labels from fixture snapshots.
  - Action board includes source-backed research commands.
  - Opportunity radar identifies strength pockets and setup watch actions from fixture snapshots.
  - Opportunity radar does not claim VCP/Supertrend/MTF confirmation when evidence is absent.
  - F&O detail section includes NIFTY/BANKNIFTY status and support/resistance fields.
  - Top-index drilldown returns top-stock rows or labeled missing evidence.
  - Terminal renderable includes Reaction Engine and Action Board.
  - Terminal renderable includes drilldown content when expanded.
  - HTML renderer includes all major sections.
  - HTML renderer includes clickable index drilldown markup.

- `tests/test_nse_agent_monitor_scan.py`
  - Existing live loop tests remain passing.
  - `--once` behavior can be tested without an infinite live loop.

## Acceptance Criteria

- `/dashboard` still launches the live terminal dashboard.
- `/dash` still aliases `/dashboard`.
- `/dashboard --once` renders a single snapshot and exits.
- Pressing `Enter` in the running terminal dashboard toggles the top-index stock drilldown where terminal key handling is available.
- `/dashboard --drilldown` starts expanded.
- `/dashboard --html` writes a standalone HTML file and prints its path.
- `/dashboard --open` writes the HTML file and attempts to open it.
- Terminal dashboard contains Reaction Engine and Action Board.
- Terminal dashboard contains Opportunity Radar with action-driven research candidates.
- Terminal dashboard contains richer F&O details and top-index stock drilldown.
- HTML dashboard contains Market Pulse, Reaction Engine, Action Board, Opportunity Radar, Sector Radar, F&O Control, clickable top-index stock drilldown, Movers, News/Catalysts, RS Leaders, and Source/Freshness Audit.
- Missing data is labeled clearly.
- Focus text such as `banks` still appears in both terminal and HTML versions.
- Existing dashboard tests and new dashboard tests pass.
