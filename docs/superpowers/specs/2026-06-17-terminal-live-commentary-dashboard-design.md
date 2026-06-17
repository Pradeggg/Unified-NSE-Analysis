# Terminal Live Commentary Dashboard Design

## Objective

Enable Agent Adda's terminal `/dashboard` to run as a live, stateful market tracker that continuously alternates between tool calls and model commentary. The output should read like a trading desk tracker: current symbol status, key levels, meaningful changes since the last cycle, best actionable names, and what to watch next.

## Scope

This design is terminal-only. It does not build a browser dashboard, plugin UI, or HTML live surface. Existing HTML dashboard generation remains unchanged except for shared command parsing where needed.

The first runtime command is:

```bash
/dashboard --live-commentary
/dashboard --live-commentary --symbols TRENT,DIXON,SCHNEIDER,INDUSINDBK
/dashboard --live-commentary --interval 60
/dashboard --live-commentary --cycles 5
/dashboard --live-commentary --no-llm
```

## Runtime Flow

The live commentary mode runs this loop:

```text
tool calls -> state update -> event detection -> compact model prompt -> tracker render -> repeat
```

Each cycle collects bounded live evidence:

- Market tape: major NSE indices, breadth where available, VIX.
- Movers: NIFTY 500 top gainers/losers.
- Watchlist quotes: explicit `--symbols` or a default tracker watchlist seeded from current movers and common intraday focus names.
- Intraday setup evidence: `scan_symbols_intraday` on the bounded watchlist.

The loop must avoid the existing heavy full-dashboard path that calls several broad `run_intraday_screener` variants and can block refreshes. Slow or failed tools should be captured as source errors while the dashboard continues.

## State Model

The dashboard owns a session state object with:

- `cycle`: integer refresh count.
- `started_at` and `last_updated_at`.
- `symbols`: ordered active watchlist.
- `previous_zone_by_symbol`: last known zone such as `long active`, `T1 hit`, `invalidated`, `watch`.
- `tracked_symbols`: latest state per symbol.
- `events`: bounded event history for meaningful changes.
- `last_commentary`: last generated model or deterministic commentary.
- `source_health`: per-tool status and freshness.

Each tracked symbol stores:

- symbol
- last price and percent change
- direction: `LONG`, `SHORT`, or `WATCH`
- status text
- trigger/reference price
- stop/invalidation
- target 1 and target 2
- risk/reward if available
- strategy label
- note from the signal engine
- freshness/source

## Event Detection

The state engine compares current symbol zones against previous zones and emits events only for meaningful changes:

- setup activated
- setup flipped long/short
- target hit
- invalidation hit
- trail lost
- reclaimed trigger
- moved from watch to active
- stale data detected
- no longer actionable

Market-level events include:

- NIFTY or BANKNIFTY bias shift
- breadth flips positive/negative
- VIX spike or cooling
- sector leadership change when available
- new top mover entering the tracker

The first cycle prints the full tracker. Later cycles emphasize `Meaningful change` and keep unchanged setups compact.

## Model Commentary

The model should not receive raw tool payloads. It receives a compact, structured prompt containing:

```json
{
  "market_context": "NIFTY +0.19%, BANKNIFTY +0.37%, breadth positive",
  "tracked_symbols": [
    {
      "symbol": "DIXON",
      "status": "long active",
      "last_price": 12822.0,
      "trigger": 12814.0,
      "invalidation": 12787.5,
      "targets": [12877.1, 12888.0],
      "note": "Momentum strong but extended"
    }
  ],
  "events_since_last_cycle": [
    "DIXON reclaimed trigger and flipped long active"
  ],
  "source_health": [
    "scan_symbols_intraday ok",
    "get_market_breadth degraded"
  ],
  "style": "tracker commentary, concise, level-specific, no investment advice"
}
```

The system prompt instructs the model to:

- write in a tracker style matching the attached example
- mention only evidence supplied in the compact context
- prioritize level-specific commentary
- separate current read, meaningful changes, best actionable names, and watch-next
- avoid generic market prose
- avoid investment advice or certainty language

If the model fails or `--no-llm` is set, deterministic commentary renders the same sections from state.

## Terminal Rendering

The live terminal view shows:

1. Header: cycle, timestamp, interval, source health.
2. Market context: NIFTY, BANKNIFTY, VIX, breadth.
3. Tracker table:
   - Symbol
   - Status
   - Key Level
4. Commentary:
   - Current read from the tracker
   - Meaningful changes
   - Best actionable names
   - Watch next
5. Source health and stale-data warnings.

Rendering uses Rich tables and panels. It should fit normal terminal width and avoid flooding the scrollback. In live mode, Rich `Live` updates in-place; with `--cycles`, it exits after the requested count for tests and smoke runs.

## Command Parsing

`_parse_dashboard_command` expands to parse:

- `--live-commentary`
- `--no-llm`
- `--symbols A,B,C` or `--symbols A B C`
- `--interval N`
- `--cycles N`

Existing flags keep their behavior:

- `--once`
- `--html`
- `--open`
- `--drilldown`

When `--live-commentary` is present, `/dashboard` dispatches to the live commentary runner instead of the legacy full snapshot loop.

## Error Handling

- Tool errors are stored in `source_health` and rendered.
- A failed model call falls back to deterministic commentary.
- Stale intraday bars are flagged per symbol.
- Empty watchlists fall back to a small default NSE watchlist.
- Keyboard interrupt exits cleanly.

## Testing

Tests cover:

- dashboard command parsing for new flags
- state transition and event detection
- deterministic commentary fallback
- model prompt compactness and style constraints
- command registry route for `/dashboard --live-commentary`
- bounded runner behavior with `--cycles 1`

## Non-Goals

- Broker order execution
- Email alerts from the live loop
- Browser or HTML auto-refresh dashboard
- Full strategy-lab paper trading integration
- Persistent PostgreSQL dashboard state

