# Strategy Lab Risk Governance Design

## Goal

Harden the Portfolio Strategy Lab replay path so paper-trading confidence separates entry-strategy edge from portfolio-manager discipline.

## Scope

This change applies to `portfolio.engine.event_loop.run_replay`, the path used by the Strategy Lab CLI replay. It does not migrate the lab to `managed_portfolio.py`.

## Policy

Add a replay risk policy with these defaults:

- max gross exposure: 95%
- max single-stock weight: 12%
- max sector weight: 25%
- max positions: 15
- drawdown pause: -15%
- max turnover: 2500%
- trim when position weight exceeds 12%
- trim target: 10%
- block adds when an existing Stage 2 strategy position drifts to Stage 1

## Behavior

Before a new entry or add order is submitted, the replay checks the policy using current marks, cash, existing positions, pending buy reservations, latest drawdown, and accumulated filled notional. If a check fails, no order is emitted for that signal.

For existing positions that grow beyond the trim threshold, the replay submits a sell order sized to bring the position back toward the trim target. Normal strategy exits remain full exits.

## Reporting

Replay output exposes policy defaults and block/trim counters so reports can distinguish:

- entry strategy confidence
- portfolio manager confidence
- execution and risk confidence

## Testing

Use test-first coverage in `tests/portfolio/test_event_loop.py` for gross exposure, single-stock cap, sector cap, drawdown pause, turnover cap, Stage 1 drift add blocking, and trim order generation.
