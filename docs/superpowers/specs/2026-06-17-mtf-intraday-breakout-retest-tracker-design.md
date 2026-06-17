# MTF Intraday Breakout-Retest Tracker Design

## Purpose

Build a first-class Agent Adda runtime capability that scans F&O stocks for multi-timeframe intraday breakout and breakout-retest setups, tracks each candidate through a state lifecycle, and creates email alert drafts for meaningful state changes until the trade is closed or invalidated.

This is an intraday strategy tracker, not a one-shot scanner. The objective is to start with a broad F&O universe, progressively eliminate weak candidates, and surface only trade-ready setups with levels, support/resistance, F&O evidence, option sizing, and lifecycle status.

The capability is research-only and does not execute broker orders.

## Scope

Included in v1:

- F&O stock universe as the default scan universe.
- Optional symbol override for focused watchlists.
- Multi-timeframe technical assessment using daily, 60m, 15m, and 5m evidence.
- Breakout and true breakout-retest state tracking.
- Stateful PostgreSQL persistence so candidates are not re-alerted every scan.
- F&O and option-chain validation before a setup becomes trade-ready.
- Option sizing using premium-defined risk and configured max-loss caps.
- Email draft generation for state changes using configured recipients.
- Agent Adda slash commands and natural-language routing for scan, status, candidates, active setups, and manual close.
- Tests for detection, lifecycle transitions, sizing, persistence, dedupe, rendering, and command routing.

Excluded from v1:

- Broker order placement.
- Auto-sending emails without user review.
- Non-F&O symbols by default.
- Screenshot or TradingView dependency.
- LLM-only pattern detection.
- Full paper-trading integration as the primary implementation path.

Paper trading can consume finalized trade-ready signals after the tracker is stable, but v1 should keep the tracker independent.

## Strategy Philosophy

The tracker combines higher-timeframe context with lower-timeframe triggers.

- Daily and 60m decide whether the stock deserves long-side attention.
- 15m identifies the main breakout structure and retest.
- 5m provides timing confirmation and reduces late entries.
- F&O evidence determines whether the setup is actionable through options.

The strategy should prefer long setups first. Short-side support can be added through the same state model later, but v1 should not complicate the first implementation with symmetric bearish logic unless the existing monitor framework requires a direction field.

## Universe

Default universe:

- F&O stocks only.
- Exclude indices from this tracker in v1 because index option strategy behavior and expiry mechanics are different from stock options.

Optional overrides:

- `/monitor start mtf_retest TRENT,DIXON,HDFCBANK`
- `/mtf-retest scan --symbols TRENT,DIXON,HDFCBANK`

Eligibility filters:

- Symbol resolves to a trusted NSE symbol.
- F&O overview or option-chain evidence is available.
- Intraday bars exist or can be seeded through the existing intraday data path.
- Liquidity filter passes before trade-ready status.

## Timeframes

Default timeframes:

| Layer | Timeframe | Purpose |
|---|---|---|
| Context | Daily | Stage, moving-average structure, broad trend, recent high/low |
| Context | 60m | Intraday swing direction and higher intraday support/resistance |
| Structure | 15m | Breakout level, breakout close, retest, stop, target |
| Timing | 5m | Retest-hold confirmation, entry trigger refinement |

The tracker should use PostgreSQL intraday bars where available. If a timeframe is unavailable, the symbol can remain in `watch` or `invalidated_missing_evidence`, but it must not become `trade_ready`.

## Candidate State Lifecycle

Each symbol should have at most one active tracker record per strategy version and direction.

States:

| State | Meaning | Alert |
|---|---|---|
| `watch` | Symbol is eligible but no actionable breakout pressure yet | No |
| `about_to_breakout` | Price is near resistance/pivot with MTF alignment and improving volume | Yes |
| `breakout` | 15m close clears breakout level with acceptable confirmation | Yes |
| `retest_pending` | Breakout happened; waiting for controlled pullback/retest | No, unless newly created from breakout |
| `retest_hold` | Price retested breakout zone and closed/held above it | Yes |
| `trade_ready` | Entry, stop, target, F&O validation, liquidity, and sizing are valid | Yes |
| `open` | User manually marks active, or future paper-trading integration opens it | Yes |
| `target_hit` | First or final target reached | Yes |
| `stop_hit` | Stop level breached | Yes |
| `invalidated` | Setup failed before entry or evidence deteriorated | Yes |
| `closed` | Trade lifecycle is finished | Yes |

State transitions:

- `watch` -> `about_to_breakout`
- `about_to_breakout` -> `breakout`
- `about_to_breakout` -> `watch` if pressure fades
- `breakout` -> `retest_pending`
- `retest_pending` -> `retest_hold`
- `retest_pending` -> `invalidated` if price closes below failure level
- `retest_hold` -> `trade_ready`
- `trade_ready` -> `open` only through explicit user action in v1
- `trade_ready` -> `invalidated` if trigger expires or price breaks setup support
- `open` -> `target_hit`, `stop_hit`, `invalidated`, or `closed`
- `target_hit` -> `closed` when final target is reached or manually closed
- Any active state -> `closed` through manual close

The tracker should store state history, not just the latest state, so alerts and analysis can explain how the candidate evolved.

## Breakout And Retest Rules

Breakout level:

- Primary level: recent 15m swing high or resistance from `get_intraday_levels`.
- Secondary context: 60m resistance and daily recent high.
- The chosen breakout level must be above the latest price when in `about_to_breakout`.

About-to-breakout:

- Current price is within a configurable threshold of the breakout level.
- Default threshold: 0.4% below resistance for stocks priced above ₹500, 0.7% for lower-priced symbols.
- 15m EMA structure is constructive, ideally price above EMA20/EMA50.
- 60m direction is bullish or neutral-improving.
- Volume is not dry; latest 15m volume should be above a recent median or rising.

Breakout:

- 15m candle closes above breakout level.
- Breakout close should not be excessively extended.
- Default extension cap: close no more than 1.5 ATR or 1.2% above breakout level, whichever is more conservative.
- Volume expansion is preferred; weak volume downgrades score and adds a risk flag.

Retest pending:

- After breakout, wait for price to revisit the breakout zone.
- Retest zone: breakout level down to breakout level minus 0.5 ATR or 0.4%, whichever is wider.

Retest hold:

- Price trades into the retest zone and closes back above breakout level, or
- 5m candles show a higher-low hold above the breakout level after touching the zone.
- Retest volume should ideally be lower than breakout volume, or at least not a high-volume selloff.

Trade-ready:

- Retest hold is valid.
- Entry trigger exists:
  - Mode 1: retest-hold close.
  - Mode 2: break above retest candle high.
- Stop is below retest low or structure support.
- At least one target offers acceptable reward-to-risk.
- F&O evidence passes.
- Liquidity and option sizing pass.

Invalidation:

- Price closes below breakout level by more than configured tolerance.
- Retest fails with high-volume breakdown.
- 60m direction turns bearish.
- F&O evidence becomes unusable.
- Setup exceeds max age.

Default max age:

- `about_to_breakout`: 3 scan cycles.
- `breakout` or `retest_pending`: 1 trading session.
- `trade_ready`: until trigger expiry or market close.
- `open`: until target, stop, manual close, or end-of-day close policy.

## Scoring

Each candidate should carry a deterministic score from 0 to 100.

Suggested weights:

- MTF alignment: 25
- Breakout structure quality: 20
- Retest quality: 20
- Volume quality: 10
- F&O/liquidity evidence: 15
- Risk/reward and sizing quality: 10

Risk flags should be machine-readable. Examples:

- `missing_5m_bars`
- `missing_60m_bars`
- `weak_breakout_volume`
- `extended_breakout`
- `late_retest`
- `wide_stop`
- `poor_rr`
- `low_option_oi`
- `wide_option_spread`
- `near_max_pain_pin`
- `futures_basis_unfavorable`
- `setup_expired`

Scores guide ranking but do not override hard evidence gates.

## F&O And Option Sizing

F&O evidence should be collected before `trade_ready`.

Required evidence:

- `get_fno_overview`
- `get_options_chain`
- Lot size where available.
- PCR and max pain.
- Futures basis/cost-of-carry when available.
- Strike availability around entry.

Liquidity checks:

- Prefer ATM or near-ATM strikes.
- Minimum option OI threshold should be configurable.
- Avoid strikes with missing price or unusable bid/ask evidence.
- If bid/ask spread is unavailable, mark sizing confidence as lower instead of pretending precision.

Sizing model:

- Use premium-defined risk for option buying or defined-risk spreads.
- Max single-trade loss cap applies.
- Default risk budget should come from existing portfolio policy if available.
- If no portfolio policy is available, use a conservative default max loss of ₹5,000 per setup and flag `default_risk_budget`.

Sizing output:

- Underlying entry trigger.
- Underlying stop.
- Underlying targets.
- Preferred option structure:
  - ATM/near-ATM CE after long trigger.
  - Bull call spread if premium is high or stop distance is wide.
- Estimated contracts/lots.
- Max premium at risk.
- Risk flags and sizing confidence.

The tracker should not claim exact option P&L unless live option premium evidence is present.

## Persistence

Add PostgreSQL tables under the existing `intraday` schema.

Suggested tables:

- `intraday.mtf_retest_candidates`
- `intraday.mtf_retest_state_events`
- `intraday.mtf_retest_alerts`

`intraday.mtf_retest_candidates` should store the latest state:

- `tracker_id`
- `strategy_version`
- `symbol`
- `direction`
- `state`
- `score`
- `breakout_level`
- `retest_low`
- `retest_high`
- `entry_trigger`
- `stop`
- `target_1`
- `target_2`
- `rr`
- `position_size`
- `option_structure`
- `option_symbol`
- `max_loss`
- `risk_flags`
- `evidence_json`
- `created_at`
- `updated_at`
- `expires_at`

`intraday.mtf_retest_state_events` should append every transition:

- `event_id`
- `tracker_id`
- `from_state`
- `to_state`
- `reason`
- `snapshot_json`
- `created_at`

`intraday.mtf_retest_alerts` should prevent duplicate emails:

- `alert_id`
- `tracker_id`
- `state`
- `dedupe_key`
- `subject`
- `body_html`
- `draft_path`
- `status`
- `created_at`

## Alerts And Email

v1 should create Outlook drafts, not auto-send emails.

Recipient config:

- Add `intraday_trade_alerts` to `config/report_recipients.yml`.
- Default `to` can stay as the user’s address.
- Use existing BCC distribution only after review.

Alert dedupe:

- Email draft only when the candidate enters a new alertable state.
- Do not repeat the same state alert unless price/levels changed materially.
- Suggested dedupe key: `strategy_version:symbol:direction:state:entry_trigger:stop:target_1`.

Email body:

- Subject should include state, symbol, direction, and key level.
- Body should include:
  - State and state-change reason.
  - Current price and timestamp.
  - MTF summary.
  - Breakout/retest evidence.
  - Entry, stop, target, R:R.
  - F&O context.
  - Option sizing and risk cap.
  - Invalidations.
  - Source trail.
  - Research-only disclaimer.

Alertable states:

- `about_to_breakout`
- `breakout`
- `retest_hold`
- `trade_ready`
- `open`
- `target_hit`
- `stop_hit`
- `invalidated`
- `closed`

## Agent Adda UX

Slash commands:

- `/monitor start mtf_retest`
- `/monitor stop mtf_retest`
- `/monitor status`
- `/mtf-retest scan`
- `/mtf-retest candidates`
- `/mtf-retest active`
- `/mtf-retest history SYMBOL`
- `/mtf-retest close SYMBOL --reason target|stop|manual|expired`
- `/mtf-retest email SYMBOL --draft`

Natural-language examples:

- "show intraday breakout retest candidates with F&O sizing"
- "which F&O stocks are about to breakout intraday"
- "track breakout and retest setups today"
- "show trade-ready retest setups"
- "close TRENT retest trade as target hit"

Terminal output should distinguish:

- Watchlist candidates.
- About-to-breakout candidates.
- Breakout but retest-pending candidates.
- Trade-ready candidates.
- Active/open candidates.
- Closed or invalidated candidates.

Every response should include evidence freshness and source trail.

## Reports And Paper Trading

v1 should expose a compact HTML/Markdown report:

- Latest candidates by state.
- Trade-ready setups.
- Open/closed lifecycle table.
- Alert history.
- Risk flags.
- F&O sizing summary.

Paper trading integration should be a follow-up:

- The tracker emits a normalized `trade_ready` signal.
- Paper trading can later subscribe to those signals.
- The tracker should not depend on paper trading to function.

## Testing Strategy

Unit tests:

- MTF readings are combined correctly.
- About-to-breakout detection requires level proximity and MTF alignment.
- Breakout detection requires a close above breakout level.
- Retest-hold detection requires pullback into zone and reclaim/hold.
- Invalidations fire on failed breakout and stale setup.
- F&O gating blocks trade-ready if option-chain evidence is missing.
- Option sizing respects max single-trade loss.
- Dedupe key prevents duplicate alerts.

Persistence tests:

- Candidate upsert preserves one active record per symbol/direction/version.
- State event append records every transition.
- Alert table suppresses repeated drafts.

Agent tests:

- Slash commands route to the tracker.
- Natural-language prompts produce tracker intent and not generic intraday output.
- Renderer includes levels, state, F&O, sizing, risk flags, and source trail.

Interactive tests:

- Start monitor in dry-run mode.
- Scan a small symbol list.
- Verify state transitions across synthetic snapshots.
- Verify email draft generation is suppressed for duplicate state.

## Rollout Plan

Phase 1:

- Build deterministic detector, state model, PostgreSQL persistence, and renderer.
- Provide scan and candidates commands.
- No background monitor yet.

Phase 2:

- Add monitor worker integration.
- Add email draft generation and dedupe.
- Add manual close and active/history commands.

Phase 3:

- Add report output.
- Add optional paper-trading consumer.
- Add strategy quality analytics from historical intraday bars.

## Open Decisions

The following defaults are acceptable for v1 and should be configurable later:

- Long-only F&O stock setups.
- Outlook drafts instead of auto-send.
- 15m primary structure with 5m timing confirmation.
- Trade-ready expiry at market close.
- Manual open/close in v1.
