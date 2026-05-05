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
- `terminal/agent/`: natural-language query router, intent detection, entity resolution, tool planning, safe execution, and response synthesis.
- `terminal/tools/`: allowlisted callable tools used by both deterministic commands and the natural-language agent.
- Existing engines remain the source of analytics truth: `download_nse_bhavcopy.py`, `daily_refresh.py`, `sector_rotation_tracker.py`, `market_breadth.py`, `index_intelligence.py`, `sector_rotation_report.py`, `portfolio-analyzer`.

The UI should read from cached snapshots where possible. Heavy computations and EOD downloads should run as explicit jobs with logs and status records, not inside the per-second render loop.

## Natural-Language Query Agent

Add an **Agent Adda Query Agent** under the terminal. This is a controlled natural-language layer, not an unconstrained chatbot.

The v1 authority level is read-only research plus controlled safe tools:

- Read cached/internal market data, generated reports, portfolio outputs, and approved public research sources.
- Run allowlisted safe tools such as symbol lookup, scanner queries, health checks, market snapshot refresh, report lookup, and sourced web catalyst search.
- Do not run arbitrary shell commands.
- Do not place orders or provide execution instructions.
- Do not mutate data except for query logs and cache records.

Natural-language flow:

1. **Data-mode detection:** detect and strip explicit prefixes such as `/historical` and `/intraday` before intent detection.
2. **Situation assessment:** detect whether the user is asking about a stock, index, sector, technical setup, portfolio, report, data health, or latest external catalyst.
3. **Intent detection:** classify the request into a known intent such as `stock_latest_brief`, `stock_technical_setup`, `sector_scan`, `index_status`, `portfolio_question`, `report_lookup`, `data_health`, `web_catalyst_search`, or `custom_readonly_analysis`.
4. **Entity resolution:** resolve names and aliases such as "Reliance" to `RELIANCE`, "Nifty Bank" to the correct index name, and sector phrases to canonical sector labels.
5. **Tool plan:** create a small auditable execution plan using approved tools first. Every market-data or calculation tool receives the resolved `data_mode`.
6. **Execution:** execute the plan through the tool registry. Generated code is allowed only for read-only dataframe analysis when deterministic tools cannot answer the request.
7. **Synthesis:** produce a balanced, sourced response with data freshness and no-investment-advice framing.

### Data Modes

The NLP agent supports explicit data-source routing:

- `/historical <query>` uses only EOD-loaded data:
  - `data/nse_sec_full_data.csv`
  - `data/nse_index_data.csv`
  - latest EOD tracker snapshot in `data/sector_rotation_tracker.db.stage_snapshots`
- `/intraday <query>` uses intraday/live SQLite tables for price, OHLCV, derived intraday indicators, screeners, and calculations.
- No prefix defaults to `/historical` for reproducibility, unless the user clearly asks for live/current/today/now/intraday data. In that case the router may infer `intraday`, but must say so in the answer.

The router must not silently mix modes for calculations. `/intraday` may use EOD data only as reference metadata, such as company name, sector, prior Stage 2 status, and previous close. If intraday tables are missing or stale, the agent should say that and ask whether to fall back to `/historical`.

All market-data tool signatures should accept `data_mode`:

```python
get_symbol_snapshot(symbol="RELIANCE", data_mode="intraday")
get_technical_setup(symbol="RELIANCE", data_mode="historical")
run_screener_query(screen_type="stage2", data_mode="intraday")
get_sector_context(sector_or_symbol="Banking", data_mode="historical")
```

Example:

```text
User: /intraday show me the latest on Reliance

Plan:
  - resolve_symbol("Reliance") -> RELIANCE
  - get_symbol_snapshot("RELIANCE", data_mode="intraday")
  - get_technical_setup("RELIANCE", data_mode="intraday")
  - get_sector_context("RELIANCE", data_mode="intraday")
  - search_latest_catalysts("RELIANCE", max_results=5)
  - synthesize_balanced_brief()
```

The default response format for stock questions is a balanced brief:

```text
Reliance Industries - Market Brief
Mode: Intraday
Data source: SQLite live tables
Fallback: EOD snapshot used only for sector/stage labels
Data freshness: live/intraday snapshot <time or unavailable>

1. Snapshot
2. Technical Setup
3. Sector / Index Context
4. Latest Catalysts
5. Risks / Watch Items
6. Source Trail

Not investment advice. For learning and research only.
```

The terminal should expose a collapsed tool trace for debugging and trust:

```text
Tool trace:
resolve_symbol -> RELIANCE
get_symbol_snapshot -> fresh
get_technical_setup -> fresh
search_latest_catalysts -> 5 sources
synthesize_balanced_brief -> complete
```

## Tool Registry

The agent chooses from a fixed registry of typed tools. It must not call arbitrary scripts directly.

V1 tool categories:

- **Entity tools:** `resolve_symbol`, `resolve_index`, `resolve_sector`.
- **Market data tools:** `get_symbol_snapshot`, `get_index_snapshot`, `get_sector_context`, each with `data_mode`.
- **Technical tools:** `get_technical_setup`, `run_screener_query`, `explain_setup_score`, each with `data_mode`.
- **Report tools:** `find_latest_report`, `read_report_summary`, `open_report_artifact`.
- **Portfolio tools:** `get_portfolio_exposure`, `find_portfolio_overlap`.
- **Health tools:** `get_data_health`, `refresh_market_snapshot`.
- **Research tools:** `search_latest_catalysts`, `summarize_sources`.
- **Fallback analysis:** `run_readonly_dataframe_analysis`, limited to approved `data/` and `reports/generated_csv/` files.

Safety rules:

- No order placement or trading execution tools.
- No arbitrary shell execution from the agent.
- Generated analysis code cannot import network, subprocess, filesystem mutation, or secrets.
- Every tool call is logged with timestamp, intent, inputs, output summary, and source freshness.
- Every market-data tool call logs the selected `data_mode` and source tables/files used.
- Response language uses "setup", "risk", "watch", and "research priority" rather than "buy/sell recommendation".

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
- `ASK <natural-language query>` or natural language entered directly in the same input bar.

Commands should be case-insensitive and return useful errors for unknown symbols or stale data.

The same input bar should support deterministic commands and natural-language queries:

- `RELIANCE`
- `/historical show me Reliance setup`
- `/intraday show me Reliance setup`
- `show me the latest on Reliance`
- `why is Tata Motors showing up?`
- `compare Reliance vs ONGC`
- `show Stage 2 stocks in banking`
- `what changed since yesterday?`
- `is my portfolio exposed to weak sectors?`
- `open latest PDF report`
- `is data fresh?`

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
- Intent detection fixture tests.
- Data-mode parser tests:
  - `/historical show Reliance` -> `data_mode=historical`, cleaned query `show Reliance`.
  - `/intraday show Reliance` -> `data_mode=intraday`, cleaned query `show Reliance`.
  - `show Reliance live now` -> inferred `data_mode=intraday`.
  - `show Reliance setup` -> default `data_mode=historical`.
- Entity resolution fixture tests for common symbols, indices, and sector aliases.
- Tool-plan tests that confirm intents map to approved ordered tool calls with `data_mode` propagated to every market-data and calculation tool.
- Agent safety tests that block write operations, shell commands, network imports in generated code, secrets access, and unsupported imports.
- Synthesis tests that require data freshness, source trail, and no-investment-advice framing.
- Data-health classification tests.
- Opportunity scoring tests.
- Symbol drilldown assembly tests.
- Fixture-based NSE response tests.
- `terminal --once` smoke test.
- `python nse_terminal.py --ask "show me the latest on Reliance" --once` smoke test.
- EOD refresh dry-run integration test.

Manual QA checklist:

- Scanner home renders with full data.
- Scanner home renders with missing live NSE data.
- Symbol drilldown works for a known Stage 2 symbol.
- Portfolio screen works with and without portfolio outputs.
- Health screen flags stale sources.
- Report screen can trigger dry-run EOD flow.
- Natural-language stock brief works for `Reliance`, shows tool trace, and degrades gracefully when live data or web search fails.

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
- Natural-language query agent for read-only research and controlled safe tools.
- Explicit `/historical` and `/intraday` query modes.
- Balanced stock brief for latest-symbol queries.
- Tool trace and query logs.

Deferred:

- Realtime broker WebSocket integration.
- Multi-user accounts.
- Client-facing polish.
- Order execution or trade automation.
- Fully autonomous workflow agent.
- Generated read-only analysis code beyond tightly constrained dataframe queries.
- Heavy open-ended AI chat inside terminal.

## Implementation Phases

1. Stabilize current `nse_terminal.py` issues and extract services.
2. Add command palette and screen routing.
3. Add symbol drilldown and data health.
4. Add portfolio screen and report/EOD controls.
5. Add deterministic tool registry used by both commands and agent plans.
6. Add natural-language query router, intent detection, entity resolution, and balanced brief synthesis.
7. Add provider interface for future broker/live-feed adapters.
