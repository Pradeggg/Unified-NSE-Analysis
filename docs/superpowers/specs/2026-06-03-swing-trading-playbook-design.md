# Swing Trading Playbook Design

## Purpose

Build a human trading playbook for NSE swing trading before automating live execution. The workflow should use deterministic rules to screen, score, and rank candidates, then produce a concise daily action sheet and a full evidence report for manual review.

This is research tooling, not investment advice. It must not place real trades. It may generate candidate plans, paper-trading ideas, and portfolio-aware action labels.

## Scope

The first version covers two swing horizons:

- Tactical swing: overnight to 2 weeks.
- Position swing: 2 to 8 weeks.

The report covers both:

- Fresh NSE-wide candidates.
- Existing portfolio holdings, with separate action labels.

The workflow must support both EOD and live usage:

- EOD-ready setups are valid at the latest close and provide a next-session plan.
- Intraday-confirmation setups require live trigger, breadth, or sector confirmation before action.

## Non-Goals

- No broker integration.
- No automatic real-money order placement.
- No optimization loop in the first release.
- No LLM-only ranking. LLM text may summarize evidence later, but ranking must be rules-based and auditable.
- No unrelated refactor of the strategy lab or portfolio engine.

## User-Facing Commands

Add a playbook command family:

- `/swing-playbook`: generate or open today's default playbook.
- `/swing-playbook --fresh`: recompute from latest PostgreSQL and report data.
- `/swing-playbook --portfolio`: show only portfolio-aware actions.
- `/swing-playbook --tactical`: show only overnight-to-2-week candidates.
- `/swing-playbook --position`: show only 2-to-8-week candidates.

The default output should include both a concise action sheet and a full report.

## Outputs

Write current reports to:

- `reports/latest/swing_playbook.html`
- `reports/latest/swing_playbook.md`
- `reports/latest/swing_playbook_candidates.csv`
- `reports/latest/swing_playbook_portfolio_actions.csv`

Archive dated reports to:

- `reports/swing_playbook/YYYY/Swing_Playbook_YYYYMMDD.html`
- `reports/swing_playbook/YYYY/Swing_Playbook_YYYYMMDD.md`

The action sheet should lead with:

1. Market regime and whether swing risk is allowed.
2. Top tactical swing candidates.
3. Top position swing candidates.
4. Portfolio action labels.
5. Risk limits and blocked-trade warnings.

The full report should include candidate evidence, scores, entry plans, stops, targets, source freshness, and portfolio exposure context.

## Data Sources

Use existing local data only:

- `scores.stage_snapshots` for stage, technical score, RS, price, and signal context.
- `scores.stage2_vcp_picks` for persisted VCP candidates.
- `market.equity_eod` and `market.index_eod` for EOD price history and indicators.
- Existing sector rotation outputs or tables for sector strength and breadth context.
- Existing live overview tooling for live breadth and index tone.
- Existing portfolio files/tables used by the portfolio monitor for holdings and exposure.
- Fundamentals from existing score snapshots or fundamentals tables where available.
- F&O enrichment only when existing cached/PostgreSQL data is available.

Missing optional evidence must degrade the score or be marked as missing. It must not be invented.

## Candidate Sleeves

### Tactical Swing Sleeve

Horizon: overnight to 2 weeks.

Candidate setup families:

- Stage 2 continuation above short moving averages.
- VCP or tight-range breakout near pivot.
- Pullback recovery inside a strong uptrend.
- Sector-leader momentum after breadth confirmation.

Core filters:

- Liquid NSE symbols.
- Price and volume thresholds consistent with the existing strategy lab defaults unless overridden.
- Avoid Stage 4 for fresh long candidates.
- Prefer Stage 2, strong relative strength, supportive sector context, and constructive market breadth.

Entry labels:

- `EOD_READY`: setup is valid at close and can be planned for the next session.
- `INTRADAY_CONFIRM`: setup exists, but action requires trigger confirmation, live breadth support, or sector confirmation.

Exit logic:

- Initial ATR stop or structure stop below pivot or pullback low.
- Partial target near 1.5R to 2R.
- Time stop after 5 sessions without follow-through.
- Exit or downgrade on SMA20 loss, failed breakout, or market risk-off flip.

### Position Swing Sleeve

Horizon: 2 to 8 weeks.

Candidate setup families:

- High-quality Stage 2 institutional trend.
- VCP with strong relative strength and healthy fundamentals.
- Sector rotation leader.
- Minervini-style trend template candidate.

Core filters:

- Stage 2 preferred.
- Price above key moving averages.
- Strong relative strength versus broad NSE universe.
- Fundamentals available and non-deteriorating where possible.
- Sector context supportive or improving.

Exit logic:

- Wider ATR or SMA50-based stop.
- Trailing stop as price advances.
- Trim if extended or sector weakens.
- Exit or downgrade if stage degrades to Stage 3 or Stage 4, or relative strength breaks down.

## Scoring Model

Each candidate receives a transparent numeric score and score breakdown.

Default weights:

- Technical setup: 35%.
- Relative strength and momentum: 20%.
- Pattern quality: 15%.
- Sector and market context: 15%.
- Fundamentals and catalysts: 10%.
- Liquidity and execution: 5%.

Scoring principles:

- Scores must be deterministic from available data.
- Missing optional evidence should reduce confidence or show a missing-evidence flag.
- Candidates with hard-blocking risk conditions should be excluded or marked `BLOCKED`.
- Tactical and position sleeves may use the same categories with different thresholds.

## Portfolio-Aware Overlay

Existing holdings should be evaluated separately from fresh candidates. Holdings do not have to pass all fresh-entry filters to appear in the portfolio section.

Portfolio labels:

- `ADD_OK`: existing position remains strong and a defined add trigger exists.
- `HOLD`: trend and evidence remain acceptable.
- `TIGHTEN_STOP`: setup is weakening or market risk is elevated.
- `TRIM`: position is extended, concentration is high, or evidence is deteriorating.
- `EXIT_WATCH`: invalidation is near or stage/RS has degraded.
- `NO_FRESH_ADD`: not a sell, but fresh capital is not justified.

Portfolio exposure checks:

- Sector concentration.
- Stage concentration.
- Number of open swing positions.
- Per-trade risk under the default risk model.
- Duplicate exposure between current holdings and fresh candidates.

## Risk Model

Default risk profile: balanced.

Rules:

- Maximum account risk per trade: 1%.
- Target open positions: 8 to 12.
- Position size capped by liquidity and portfolio concentration.
- No aggressive fresh entries when market regime is risk-off unless explicitly marked as an exception.
- Every candidate must show entry trigger, invalidation, initial stop, target zone, and estimated R multiple.

The first version can calculate theoretical sizing from a configurable account value if available. If account value is unavailable, report risk as percentages and stop distance.

## Architecture

Add a focused module:

- `terminal/swing_playbook.py`

Responsibilities:

- Load data from PostgreSQL and existing portfolio sources.
- Normalize candidate rows.
- Score tactical and position candidates.
- Apply portfolio overlay labels.
- Render Markdown, HTML, and CSV outputs.
- Return a command-friendly summary with generated paths.

Integrations:

- Add slash command routing in the Agent Adda command registry.
- Add a report preset hook in `terminal/reports.py` only if existing report-opening conventions require it.
- Optionally wire into `daily_refresh.py` after sector rotation and portfolio monitor steps once the standalone command is stable.

Keep scoring and rendering separate enough that score tests can run without generating files.

## Error Handling And Freshness

Required data failures:

- Missing EOD/stage snapshot should fail the playbook generation with a clear message.
- Missing portfolio source should still generate NSE-wide candidates and show portfolio section unavailable.

Optional data failures:

- Missing fundamentals, F&O, sector enrichment, or live data should not fail the full report.
- The report must label missing or stale evidence.

Freshness labels:

- Snapshot date.
- Market session label.
- Live data timestamp when used.
- Portfolio data timestamp or file modified time when available.

## Testing

Unit tests:

- Tactical scoring ranks stronger Stage 2/VCP candidates above weaker setups.
- Position scoring prefers durable Stage 2/RS/fundamental strength.
- Risk labels calculate stop distance and R multiple.
- Portfolio overlay emits each action label from fixture rows.
- Missing optional evidence produces warnings, not fabricated values.

Command tests:

- `/swing-playbook` dispatches to the playbook handler.
- Filtering flags return the correct sections.
- Generated latest report paths are returned.

Rendering tests:

- Markdown contains action sheet, tactical section, position section, portfolio section, and source freshness.
- HTML generation succeeds from fixture data.
- CSV output contains score breakdown and action labels.

Smoke test:

- Run the command against the current local database and verify reports are written under `reports/latest/`.

## Implementation Order

1. Build data models and scoring fixtures.
2. Implement deterministic tactical and position scoring.
3. Implement portfolio overlay labels.
4. Render Markdown and CSV.
5. Render HTML using existing report style conventions.
6. Add slash command.
7. Add optional daily refresh integration.
8. Add smoke verification command.

## Acceptance Criteria

- `/swing-playbook --fresh` produces Markdown, HTML, and CSV outputs.
- The action sheet shows both tactical and position swing candidates.
- Portfolio holdings are shown in a separate action section.
- Every candidate includes entry trigger, invalidation, stop, target zone, and risk note.
- EOD-ready and intraday-confirmation-required labels are visible.
- Missing optional evidence is explicitly labeled.
- Tests cover scoring, portfolio overlay, command dispatch, and report generation.
