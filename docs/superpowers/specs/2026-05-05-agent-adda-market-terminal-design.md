# Agent Adda Market Terminal Design

## Purpose

Build a first-class, terminal-first Indian markets product for a power user. The terminal should make the existing NSE analytics stack usable as a daily operating system: scan intraday opportunities, drill into symbols, monitor portfolio exposure, check data health, and trigger EOD report workflows from one command surface.

The product is not a trading execution system and must not present outputs as investment advice. It should frame outputs as setup quality, risk context, research priority, and learning-oriented market intelligence.

## Target User

The v1 target user is the project owner as a power researcher/operator. The terminal must be fast enough for daily market use, reliable enough to run the refresh/report pipeline, and structured so a future broker or live-feed adapter can replace free/public data sources.

## Product Approach

Use the **Terminal Operating System** approach:

- Keep the terminal as the main daily UI.
- Reuse the existing analytics engines instead of rebuilding them.
- Start with free/public NSE and Yahoo sources.
- Design the data-provider boundary so Kite, Upstox, TrueData, or another broker/feed provider can be added later.
- Implement in phases so v1 ships a useful scanner and research cockpit before attempting institutional completeness.

Alternatives considered:

- **Scanner First:** Faster to ship, but risks producing another isolated screen without refresh health, drilldowns, or portfolio context.
- **Report Command Center:** Reliable for EOD workflows, but weaker for intraday discovery and less Bloomberg-like.

## Architecture

Create a modular terminal package rather than growing `nse_terminal.py` indefinitely.

Proposed modules:

- `terminal/app.py`: TUI shell, layout, keyboard loop, command palette, screen routing.
- `terminal/screens/`: scanner, symbol drilldown, portfolio, data health, and reports screens.
- `terminal/services/`: scoring, alerts, source health, command parsing, symbol drilldown assembly.
- `terminal/adapters/`: free NSE/Yahoo provider first; broker/live-feed provider interface later.
- Existing engines remain the source of analytics truth: `download_nse_bhavcopy.py`, `daily_refresh.py`, `sector_rotation_tracker.py`, `market_breadth.py`, `index_intelligence.py`, `sector_rotation_report.py`, `portfolio-analyzer`.

The UI should read from cached snapshots where possible. Heavy computations and EOD downloads should run as explicit jobs with logs and status records, not inside the per-second render loop.

## Screens

### Scanner Home

Default live dashboard for passive scanning.

Shows:

- Live index strip and sector performance.
- Market regime and breadth context.
- Sector/index leadership.
- Ranked stock opportunities.
- Top Stage 2 leaders, breakouts, VCP setups, Supertrend flips, and volume expansion candidates.
- Held-stock badges when portfolio data exists.
- Stale-data markers when a panel is using cached or EOD data.

### Symbol Drilldown

Command-driven drilldown for a symbol such as `RELIANCE`.

Tabs:

- `Setup`: trend, stage, relative strength, breakout levels, stop/target zones, volume, Supertrend, moving averages.
- `Fundamentals`: financial strength, growth, valuation, earnings quality, peer context where available.
- `Catalysts`: F&O, FII/DII context, insider/promoter activity, corporate events, result dates, event risk.
- `Narrative`: latest generated narrative, key reasons, risk flags, learning notes.
- `History`: recent price/volume changes, prior signal appearances, stage transitions, report links.

Default tab is `Setup`.

### Portfolio Cockpit

Portfolio awareness is layered:

- Terminal works without portfolio data.
- Held names receive badges and scanner alerts.
- Dedicated portfolio screen shows holdings, sector exposure, risk/concentration, and symbols that overlap with scanner signals.

### Data Health

Shows source freshness and reliability:

- Latest EOD stock date.
- Latest EOD index date.
- NSE live API status.
- Yahoo fallback status.
- F&O, FII/DII, insider, macro, corporate-events freshness.
- Tracker database status.
- Report artifact freshness.
- Failed/stale/missing source list.

### Reports

Control plane for EOD work:

- Run/download missing bhavcopy.
- Run analytics.
- Update sector tracker.
- Generate HTML/MD/PDF reports.
- Open latest report paths.
- Show last job log and failures.

## Commands

V1 command palette should support:

- `STAGE2`
- `BREAKOUTS`
- `VCP`
- `SUPERTREND`
- `SECTOR <name>`
- `<SYMBOL>`
- `PORT`
- `HEALTH`
- `REPORT`
- `REFRESH`
- `EOD`

Commands should be case-insensitive and return useful errors for unknown symbols or stale data.

## Data Flow

1. `download_nse_bhavcopy.py` updates:
   - `data/nse_sec_full_data.csv`
   - `data/nse_index_data.csv`
2. Existing analytics produce derived outputs:
   - stage and sector tracker snapshots
   - regime and breadth
   - F&O, FII/DII, insider/events, macro, fundamentals
   - HTML/MD/PDF reports
3. Live overlay pulls:
   - NSE `allIndices`
   - NSE `equity-stockIndices`
   - Yahoo fallback for missing symbols
4. Terminal services combine EOD, derived, and live data into cached scanner snapshots.
5. Screens render from terminal snapshots and surface health/staleness explicitly.

## Ranking Model

Ranking should be layered and explainable:

1. **Market backdrop:** regime, breadth, index health, McClellan/TRIN when available.
2. **Sector leadership:** RS vs Nifty 500, sector breadth, macro tailwind.
3. **Stock technical score:** Stage 2, RS rank, breakout proximity, volume expansion, Supertrend, VCP, moving-average structure.
4. **Conviction boosters:** fundamentals, F&O buildup/PCR, FII/DII context, insider/promoter activity, events, portfolio ownership.
5. **Risk flags:** weak breadth, event risk, promoter selling/pledge, overextended RSI, poor fundamentals, stale data.

Every ranked stock should expose a concise "why ranked" breakdown. The UX should avoid primary buy/sell recommendation language and prefer setup quality, risk flags, and research priority.

## Reliability

The terminal must not fail hard because one source is down.

Rules:

- Each source reports one of `fresh`, `stale`, `missing`, or `failed`.
- Panels render partial data with clear stale markers.
- NSE live calls use browser-like headers, cookie warmup, timeouts, retries, and cached fallback.
- EOD refresh writes logs and a summary record.
- The UI does not recompute heavy analytics every second.
- Broker/live-feed providers are isolated behind adapters.

## Testing

Required test coverage:

- Command parser unit tests.
- Data-health classification tests.
- Opportunity scoring tests.
- Symbol drilldown assembly tests.
- Fixture-based NSE response tests.
- `terminal --once` smoke test.
- EOD refresh dry-run integration test.

Manual QA checklist:

- Scanner home renders with full data.
- Scanner home renders with missing live NSE data.
- Symbol drilldown works for a known Stage 2 symbol.
- Portfolio screen works with and without portfolio outputs.
- Health screen flags stale sources.
- Report screen can trigger dry-run EOD flow.

## V1 Scope

Must ship:

- Scanner home.
- Command palette.
- Symbol drilldown with tabs.
- Data health screen.
- One-command EOD refresh path.
- Portfolio badges and basic portfolio screen.
- Report shortcuts.
- Public/free data providers.

Deferred:

- Realtime broker WebSocket integration.
- Multi-user accounts.
- Client-facing polish.
- Order execution or trade automation.
- Heavy AI chat inside terminal.

## Implementation Phases

1. Stabilize current `nse_terminal.py` issues and extract services.
2. Add command palette and screen routing.
3. Add symbol drilldown and data health.
4. Add portfolio screen and report/EOD controls.
5. Add provider interface for future broker/live-feed adapters.

