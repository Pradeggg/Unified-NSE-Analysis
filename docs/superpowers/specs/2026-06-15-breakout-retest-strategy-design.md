# Breakout Retest Strategy Design

## Purpose

Build a first-class EOD swing strategy family for true breakout-retest setups in Agent Adda and the paper-trading strategy lab.

The strategy should not be a renamed breakout scan. It must detect a breakout above a prior pivot, wait for a valid retest of that pivot, then support two entry styles: entry on retest-hold close and entry after confirmation above the retest-day high.

The same computed evidence should power:

- PostgreSQL EOD strategy-lab backtests.
- Paper-trading strategy comparison and possible selection.
- Agent Adda natural-language queries.
- Swing playbook and candidate reports.

This is research-only infrastructure and does not provide personalized investment advice.

## Scope

Version 1 is EOD swing only.

Included:

- Breakout-retest derived features from daily OHLCV and existing technical/fundamental fields.
- Six strategy variants covering three retest windows and two entry modes.
- Technical and fundamental setup scoring.
- Missing-fundamental penalty and risk flag behavior.
- Agent Adda query and report exposure.
- Regression tests for feature derivation, strategy validation, strategy lab output, and Agent Adda routing/output.

Excluded from v1:

- Intraday breakout-retest strategies.
- Live broker execution.
- LLM-only pattern detection.
- TradingView or screenshot dependency.
- Personalized allocation advice.

## Strategy Family

The strategy family has three retest windows:

| Window | Days After Breakout | Use |
|---|---:|---|
| Tight | 1-5 trading days | Fast momentum retests with fewer stale setups |
| Balanced | 1-10 trading days | Default swing-trading window |
| Wide | 1-20 trading days | Slower bases and delayed pullbacks |

Each window has two entry modes:

| Entry Mode | Trigger | Tradeoff |
|---|---|---|
| Retest close | Enter when retest day closes back above pivot | Earlier, more signals, higher false-break risk |
| Confirmation | Enter after price breaks above retest-day high while holding pivot | Cleaner, fewer signals, may miss fast movers |

The six built-in strategy IDs are:

- `breakout_retest_tight_close_v1`
- `breakout_retest_tight_confirm_v1`
- `breakout_retest_balanced_close_v1`
- `breakout_retest_balanced_confirm_v1`
- `breakout_retest_wide_close_v1`
- `breakout_retest_wide_confirm_v1`

## Feature Model

The EOD replay frame should add derived breakout-retest fields. Field names should be stable because they become part of the strategy grammar and Agent Adda evidence contract.

Core fields:

- `br_pivot_20d`: prior 20-day high, excluding the current bar.
- `br_breakout_signal`: true when close clears `br_pivot_20d`.
- `br_breakout_date`: date of the most recent valid breakout.
- `br_days_since_breakout`: trading days since the most recent valid breakout.
- `br_retest_low_pct`: percentage distance of retest low from pivot.
- `br_retest_hold`: true when low dips no more than 2% below pivot and close finishes above pivot.
- `br_retest_date`: date of the most recent valid retest hold.
- `br_retest_high`: high of the retest-hold bar.
- `br_confirm_after_retest`: true when a later bar breaks above `br_retest_high` while close remains above pivot.
- `br_failed`: true when close is more than 2% below pivot after breakout/retest.
- `br_volume_quality`: normalized score or label for breakout/retest volume behavior.
- `br_setup_score`: composite setup score for ranking.
- `br_risk_flags`: machine-readable risk flags.

Recommended supporting numeric fields:

- `br_pivot_distance_pct`: close distance from pivot.
- `br_breakout_volume_ratio`: breakout volume versus 20-day average.
- `br_retest_volume_ratio`: retest volume versus 20-day average.
- `br_breakout_close_pct`: breakout close distance above pivot.
- `br_retest_depth_pct`: same numeric value as retest low distance, useful for ranking.

## Pivot And Retest Rules

Pivot:

- Primary pivot is the prior 20-day high.
- Pivot calculation must exclude the current day to avoid lookahead.
- A breakout requires close above the pivot.

Trend filters:

- Stage 2 preferred.
- Close above SMA50 and SMA200.
- SMA50 above SMA200, or improving SMA structure where available.
- Relative strength at least 65.

Volume:

- Breakout volume expansion is preferred at `volume_ratio_20d >= 1.2`.
- Retest volume should ideally be lower than breakout volume or not climactic.
- Weak volume does not necessarily exclude a candidate, but it should reduce score and add a risk flag.

Retest hold:

- Retest must occur inside the strategy window after breakout.
- Low can dip up to 2% below pivot.
- Close must reclaim or hold above pivot.

Failure:

- Close more than 2% below pivot marks the setup failed.
- Failed setups are not eligible for entry until a new breakout sequence forms.

## Entry Rules

Close-entry variants enter on the retest-hold close:

- `br_retest_hold = 1`
- `br_days_since_breakout` inside the variant window.
- Technical and eligibility filters pass.

Confirmation-entry variants enter after the retest:

- Prior valid retest hold exists.
- Current high or close breaks above `br_retest_high`.
- Current close remains above pivot.
- Technical and eligibility filters pass.

The implementation should avoid lookahead. A confirmation entry must only use a prior retest bar, not the current bar as both retest and confirmation.

## Fundamental Quality

Fundamental evidence is a quality and risk input, not the primary entry trigger.

Preferred filters and scoring inputs:

- Latest results age less than or equal to 220 days.
- Sales growth at least 10%.
- PAT growth at least 10%.
- EPS growth at least 10%.
- OPM YoY delta at least -3%.
- Debt-to-equity less than or equal to 1.5 when available.
- ROE or ROCE positive when available.

Missing fundamentals:

- Must not hard-exclude an otherwise valid technical setup.
- Should reduce `br_setup_score`.
- Should add a risk flag such as `missing_fundamentals`.

Weak fundamentals:

- Should reduce score and add specific flags such as `weak_sales_growth`, `weak_eps_growth`, `high_debt`, or `stale_results`.
- Severe negative evidence may exclude or downgrade the setup depending on the strategy-lab scoring policy.

## Risk And Exit Rules

Initial stop should be structure-aware. Use the tightest valid stop among:

- Pivot minus 2%.
- Retest low minus 0.5 ATR.
- Entry minus 2 ATR.

If structure data is incomplete, fall back to ATR stop.

Targets:

- Initial target uses 2R.
- Reports should show risk per share, estimated risk, and target.

Runtime risk rails:

- Existing position cap, planned single-trade loss cap, gap-risk cap, liquidity filter, max participation, and price-discontinuity guard apply.

Exit conditions:

- Hard invalidation: close more than 2% below pivot.
- Swing trend exit: close below SMA20.
- Structural exit: close below SMA50.
- Relative-strength exit: RS below 60.
- Stage exit: stage becomes Stage 3 or Stage 4.

## Agent Adda UX

Agent Adda should support queries such as:

- "find breakout retest stocks"
- "show tight retest setups"
- "show balanced breakout retest setups"
- "breakout retest candidates with fundamentals"
- "which stocks broke out and are retesting?"
- "compare breakout retest variants"
- "show confirm-entry retest setups"

Responses should include:

- Symbol and company name.
- Setup type: tight, balanced, or wide.
- Entry mode: close or confirm.
- Pivot level.
- Breakout date.
- Retest date.
- Retest low and close.
- Distance from pivot.
- Entry trigger.
- Stop, target, and risk per share.
- Volume quality.
- Stage, RS, RSI, and moving-average context.
- Fundamental quality summary.
- Risk flags.
- Source trail and data freshness.

The answer should distinguish between:

- Active entry candidate.
- Retest watchlist candidate.
- Confirm-entry pending candidate.
- Failed breakout.
- Missing evidence.

## Reports

Strategy lab:

- Include all six strategy variants in the leaderboard.
- Persist feature coverage and variant metrics.
- Compare total return, drawdown, win rate, profit factor, expectancy, open positions, and risk breaches.

Paper trading:

- If selected strategy is a breakout-retest variant, show variant, pivot, retest, entry mode, stop, and target.
- Preserve risk-rail breach reporting.

Swing playbook:

- Add a breakout-retest section.
- Include setup score and risk flags.

Candidate CSV:

- Include symbol, setup type, entry mode, pivot, breakout date, retest date, retest depth, entry trigger, stop, target, setup score, and risk flags.

## Data Flow

1. PostgreSQL EOD loader builds the standard replay frame.
2. Breakout-retest feature derivation appends `br_*` fields without lookahead.
3. Strategy schema allows the new `br_*` indicators.
4. Built-in strategy library defines six variants using those indicators.
5. Strategy lab backtests and ranks variants.
6. Paper portfolio can select a breakout-retest variant if it wins under the normal ranking policy.
7. Agent Adda and reports query the same derived evidence.

## Testing Plan

Feature derivation tests:

- Prior 20-day pivot excludes the current bar.
- Breakout fires only when close clears prior pivot.
- Retest hold is detected when low is within 2% below pivot and close is above pivot.
- Retest is rejected when close stays below pivot.
- Confirmation fires only after a prior retest high is broken.
- Failed breakout fires when close is more than 2% below pivot.

Strategy tests:

- New derived indicators validate in the strategy schema.
- All six built-in variants compile.
- Close-entry and confirmation-entry variants produce different signals on fixture data.
- Retest windows behave differently on fixture data.

Strategy-lab tests:

- Replay frame contains `br_*` fields.
- Six variants appear in the leaderboard.
- Metrics and state artifacts are written.
- Runtime risk rails still apply.

Agent Adda tests:

- Natural-language breakout-retest prompts route to the capability.
- Output includes pivot, breakout date, retest date, entry mode, stop, target, and risk flags.
- Missing fundamentals are presented as penalty/risk, not unsupported inference.

Regression commands should include:

- Focused feature and strategy tests.
- `tests/portfolio`.
- Agent Adda prompt scenarios for breakout-retest examples.
- A latest PostgreSQL strategy-lab run for manual inspection.

## Acceptance Criteria

- All six breakout-retest variants are available as built-in strategies.
- Derived features are computed without lookahead.
- Missing fundamentals do not exclude technical candidates but are visible as risk flags.
- Agent Adda can answer breakout-retest candidate queries with grounded evidence.
- Strategy lab compares the variants and writes metrics.
- Swing playbook or latest report surfaces breakout-retest candidates.
- Tests cover feature derivation, variant compilation, replay integration, and Agent Adda response shape.

