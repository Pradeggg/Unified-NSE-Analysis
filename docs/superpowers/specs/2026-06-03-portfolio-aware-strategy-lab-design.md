# Portfolio-Aware Strategy Lab Design

## Objective

Upgrade the portfolio strategy lab from a daily signal replay into a stateful,
portfolio-aware paper manager starting from `2025-01-01`. The manager must use
defined capital, risk, stock exposure, sector exposure, stops, targets, and
incremental add/reduce rules before publishing final paper orders.

The strategy lab remains the research engine. It finds and ranks strategies,
generates entry and exit signals, and supplies technical risk levels. A new
portfolio manager layer turns those signals into portfolio-aware decisions.

## Current Problem

The current flow selects the top ranked strategy and publishes that strategy's
raw paper positions and next orders. It understands the replay account state,
but it does not explicitly manage:

- existing holdings as constraints on new orders
- target position size per stock
- sector exposure limits
- total open portfolio risk
- staged adds and trims
- persistent targets and trailing stops
- reasoned skip decisions when a signal is valid but portfolio risk is full

That makes the output useful for strategy discovery, but incomplete as a daily
portfolio management workflow.

## Proposed Architecture

The new flow has five stages:

```text
PostgreSQL replay data
  -> Strategy Lab signal replay
  -> Portfolio Manager policy engine
  -> Optional LLM council critique
  -> Validated managed portfolio artifacts and report
```

### Strategy Lab

The existing `portfolio.cli strategy-lab` command continues to:

- load EOD bars, stage snapshots, fundamentals, and VCP picks
- prepare replay features from `2025-01-01`
- replay built-in strategy specs
- rank strategies by return, drawdown, trade quality, turnover, and costs
- select the top ranked active strategy

This layer should not import broker holdings or override portfolio sizing
decisions. It produces candidate signals and raw strategy diagnostics.

### Portfolio Manager

Add a deterministic manager that replays selected-strategy signals from
`2025-01-01` into a managed paper portfolio. It owns:

- cash and NAV
- open positions
- position lots
- average cost
- realized and unrealized P&L
- active stop and target per position
- sector and stock exposure
- open risk by stock and portfolio
- pending next-session orders
- decision audit rows

The manager consumes the selected strategy's orders/fills/features, but it does
not blindly mirror the strategy account. Every action must pass policy checks.

### LLM Council

An optional LLM council may review the deterministic decisions. It can explain,
challenge, and flag conflicts, but it cannot create executable orders directly.

LLM output must be structured as advisory review rows:

- `decision_id`
- `severity`
- `concern`
- `suggested_change`
- `evidence`

Any suggested change must be passed back through deterministic validation before
appearing as a final managed order.

## Default Policy

Create a default policy file at `portfolio/config/portfolio_policy.yaml`:

```yaml
start_date: 2025-01-01
initial_capital: 1000000
max_gross_exposure_pct: 95
max_single_stock_pct: 10
max_sector_pct: 25
risk_per_new_position_pct: 1.0
risk_per_add_pct: 0.5
max_portfolio_open_risk_pct: 8
max_positions: 15
initial_entry_pct_of_target: 50
first_add_pct_of_target: 25
second_add_pct_of_target: 25
trim_when_position_pct_above: 12
trim_to_position_pct: 8
stop_method: atr
target_method: reward_risk
default_reward_risk: 2.0
```

The policy is risk-first. Position size is determined by allowed rupee risk
against the stop, then constrained by stock, sector, cash, exposure, and max
position count limits.

## Decision Rules

### New Entry

A candidate buy becomes `ENTER` only when all of these are true:

- the symbol is not already held
- available cash is sufficient
- target risk does not breach `risk_per_new_position_pct`
- portfolio open risk stays below `max_portfolio_open_risk_pct`
- position value stays below `max_single_stock_pct`
- sector value stays below `max_sector_pct`
- total exposure stays below `max_gross_exposure_pct`
- open positions stay within `max_positions`

If any check fails, write a `SKIP` decision with machine-readable reason codes.

### Incremental Add

A candidate buy for an already held symbol becomes `ADD`, not another independent
entry. Adds are allowed only when:

- the current setup still passes the strategy entry or add rule
- price is above current stop
- the position has not consumed all staged add slots
- the new lot fits the add risk budget
- stock, sector, cash, exposure, and open-risk limits still pass

Default staging:

- initial entry: 50% of target position
- first add: 25% of target position
- second add: 25% of target position

### Hold

If a position remains valid but no add or trim is required, write `HOLD`. The
hold row should still update mark-to-market metrics, stop, target, age, and risk.

### Trim

Write `TRIM` when a position exceeds policy size without a full exit trigger.
The default rule trims a position above 12% of NAV down toward 8% of NAV.

Additional trim reasons may include:

- sector cap pressure
- open-risk pressure
- partial target reached
- deteriorating relative strength without a hard exit

### Exit

Write `EXIT` when the selected strategy emits an exit signal or the managed stop
is breached. Exits close the managed position unless a later policy adds partial
exit rules.

### Stops And Targets

Each position must persist stop and target levels in state. Initial values come
from the selected strategy's ATR/risk settings:

- stop = entry price minus ATR multiple
- target = entry price plus reward-risk multiple times risk per share

Trailing rules may only raise stops for long positions. Targets may be raised
only by an explicit target-update rule; they must not disappear between runs.

## Artifacts

Write managed portfolio outputs under the existing strategy-lab output directory:

- `managed/portfolio_policy.yaml`
- `managed/managed_portfolio_state.json`
- `managed/managed_positions.csv`
- `managed/managed_orders.csv`
- `managed/managed_decisions.csv`
- `managed/managed_daily_pnl.csv`
- `managed/llm_council_review.jsonl` when enabled

Add a new section to `reports/latest/portfolio_strategy_lab.html`:

- managed NAV, cash, exposure, open risk
- current managed positions
- enter/add/trim/exit/hold/skip decisions
- sector exposure table
- next-session managed orders
- LLM council critique when available

## Data Model

The managed state must be replayable from artifacts alone. At minimum it stores:

- run ID and as-of date
- policy checksum
- selected strategy ID
- cash and NAV
- positions keyed by symbol
- lots keyed by symbol and lot ID
- stop, target, and risk per lot
- realized P&L
- decision audit trail path
- pending order path

The CSV decision rows should include:

- `date`
- `symbol`
- `action`
- `quantity`
- `price_reference`
- `stop_price`
- `target_price`
- `risk_amount`
- `position_value_after`
- `sector_exposure_after_pct`
- `portfolio_open_risk_after_pct`
- `reason_codes`
- `source_strategy_order_id`

## PostgreSQL Persistence

Add tables in the `portfolio` schema after the file artifacts are working:

- `portfolio.managed_runs`
- `portfolio.managed_positions`
- `portfolio.managed_orders`
- `portfolio.managed_decisions`
- `portfolio.managed_daily_pnl`
- `portfolio.managed_llm_reviews`

The first implementation can write file artifacts and include DB persistence in
the same code path if it follows the existing paper portfolio persistence style.

## Error Handling

The manager should fail closed:

- missing sector data: allow stock-level sizing but mark sector checks as
  unavailable and cap the position at half size
- missing ATR or invalid stop: skip new entries and adds
- missing price: skip decision for that date/symbol
- malformed policy: fail command with a validation error
- LLM failure: continue with deterministic decisions and record review failure

## Testing

Unit tests should cover:

- policy parsing and validation
- risk-based quantity sizing
- stock cap enforcement
- sector cap enforcement
- max open-risk enforcement
- new entry, add, trim, exit, hold, and skip decisions
- stop and target persistence
- deterministic replay from `2025-01-01`
- LLM council advisory output not becoming orders without validation
- report generation includes managed portfolio sections

Regression tests should run without network access and should use small fixture
data frames.

## Initial CLI Shape

Extend `strategy-lab` with:

```bash
.venv/bin/python -m portfolio.cli strategy-lab \
  --start 2025-01-01 \
  --lookback 2024-01-01 \
  --top-n 200 \
  --policy portfolio/config/portfolio_policy.yaml \
  --managed-portfolio \
  --llm-council optional
```

Default behavior can enable managed portfolio generation once stable. During the
first implementation, keep it behind `--managed-portfolio` to avoid disrupting
the existing report.

## Non-Goals

This design does not place broker orders, rebalance the real broker portfolio,
or let an LLM decide trades. It is paper-only and deterministic by default.

Real broker portfolio overlay can be added later as a comparison section. The
first version manages a clean strategy-lab paper portfolio from `2025-01-01`.
