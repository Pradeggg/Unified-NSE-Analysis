# Paper Trading Strategy Lab Design

## Purpose

Build a paper-trading strategy lab that starts from zero positions on `2025-01-01`, replays EOD market data, lets an LLM propose strategy definitions from allowed building blocks, compiles those definitions into deterministic rules, executes paper trades, compares strategy performance, and generates comprehensive daily reports.

This is a research and strategy-assessment system only. It must not place real broker orders in the MVP.

## Scope

The first version covers long-only Indian equity paper trading using existing Agent Adda data and reports. The system uses Stage 2 signals as an important input, but the Trading Strategy Agent decides which strategies to propose from an allowed grammar. The deterministic engine validates and executes those strategies so the results remain reproducible and auditable.

The system must:

- Start with zero holdings on `2025-01-01`.
- Replay trading decisions day by day from EOD data.
- Let the Trading Strategy Agent propose strategies and parameters.
- Compile accepted LLM proposals into deterministic strategy rules.
- Reject or clamp strategy proposals that violate hard rails.
- Track paper orders, fills, positions, daily NAV, P&L, and metrics.
- Compare strategy performance over time.
- Generate daily portfolio, strategy, risk, and trade-analysis reports.
- Log every agent action with inputs, decision, rationale, outputs, and status.

The system must not:

- Execute live broker orders.
- Use leverage, shorts, options, or futures in the MVP.
- Let LLM narrative directly place or mutate trades without deterministic validation.
- Rewrite existing reports or portfolio analyzer behavior unless explicitly needed for integration.

## Hard Rails

The Trading Strategy Agent may choose working portfolio parameters, but only inside fixed safety constraints:

- Paper trades only.
- Long-only cash equities.
- No leverage.
- Maximum risk per trade capped at `2%` of current equity.
- Maximum position size capped at `15%` of current equity.
- Maximum total portfolio exposure capped at `95%` of current equity.
- Maximum open positions capped at `20`.
- Every position must have an explicit initial stop.
- Every accepted strategy must have explicit entry and exit rules.
- Unknown indicators, operators, instruments, or unsupported order types are rejected.

## Folder Layout

Create a new top-level folder:

```text
portfolio/
  README.md
  config.yaml
  data/
    state/
      portfolio_state.json
      strategy_registry.json
    logs/
      agent_actions.jsonl
      trade_ledger.csv
      daily_nav.csv
      strategy_metrics.csv
    reports/
      daily/
      strategy/
  engine/
    data_access.py
    metrics.py
    paper_broker.py
    portfolio_account.py
    strategy_compiler.py
    strategy_schema.py
  agents/
    monitoring_agent.py
    portfolio_manager.py
    report_agent.py
    strategy_agent.py
  cli.py
```

Responsibilities:

- `portfolio/config.yaml`: default simulation dates, initial paper capital, hard rails, and report paths.
- `portfolio/engine/data_access.py`: reads PostgreSQL and local data needed for EOD replay.
- `portfolio/engine/strategy_schema.py`: defines the allowed JSON strategy schema.
- `portfolio/engine/strategy_compiler.py`: validates LLM strategy proposals and compiles them into deterministic rule objects.
- `portfolio/engine/paper_broker.py`: simulates paper orders and fills.
- `portfolio/engine/portfolio_account.py`: tracks cash, positions, orders, realized/unrealized P&L, and NAV.
- `portfolio/engine/metrics.py`: computes trade, portfolio, and per-strategy metrics.
- `portfolio/agents/strategy_agent.py`: proposes strategies from the allowed grammar.
- `portfolio/agents/portfolio_manager.py`: allocates capital across validated strategies and open positions.
- `portfolio/agents/monitoring_agent.py`: monitors open positions, stops, add triggers, and deterioration signals.
- `portfolio/agents/report_agent.py`: writes comprehensive Markdown/HTML reports.
- `portfolio/cli.py`: exposes replay, daily update, report, and status commands.

## Existing Data And Code To Reuse

Primary data sources:

- `market.equity_eod`: EOD OHLCV data for replay and execution.
- `scores.stage_snapshots`: Stage 2 and stage transition history.
- `scores.daily_scores`: daily technical score, signal, RSI, price changes, and derived universe metrics.
- `scores.v_latest_fundamental_scores` and related fundamental tables where available.
- `reports/sector_rotation/` and `reports/latest/` as context references, not as the canonical data source.

Existing code patterns to reuse:

- `backtesting/portfolio.py` for position sizing concepts.
- `backtesting/strategy_council/` for deterministic strategy/backtest patterns.
- `terminal/monitor.py` for alert-worker and monitoring patterns.
- `terminal/research_council/agents/technical.py` and related agents for technical/fundamental evidence shaping.
- `portfolio-analyzer/` report and risk concepts where they fit the new paper portfolio output.

## Strategy Proposal Grammar

The LLM outputs structured JSON. It does not output executable code.

Example accepted strategy shape:

```json
{
  "strategy_id": "stage2_pullback_quality_v1",
  "name": "Stage 2 Pullback With Quality Filter",
  "universe": {
    "stage": "STAGE_2",
    "min_price": 100,
    "min_avg_turnover": 50000000
  },
  "entry": {
    "all": [
      {"indicator": "stage", "operator": "eq", "value": "STAGE_2"},
      {"indicator": "close", "operator": "above", "value": "sma_50"},
      {"indicator": "rsi_14", "operator": "between", "value": [45, 68]},
      {"indicator": "volume_ratio_20d", "operator": "gte", "value": 1.0}
    ]
  },
  "risk": {
    "initial_stop": {"type": "atr", "multiple": 2.0},
    "risk_per_trade_pct": 1.0,
    "max_position_pct": 10.0
  },
  "add_rules": [
    {"when": "close_above_entry_plus_1r", "add_pct_of_initial": 50}
  ],
  "exit": {
    "any": [
      {"indicator": "close", "operator": "below", "value": "sma_50"},
      {"indicator": "stage", "operator": "in", "value": ["STAGE_3", "STAGE_4"]},
      {"indicator": "trailing_stop", "operator": "hit"}
    ]
  }
}
```

Allowed building blocks:

- Universe filters: stage, price, liquidity, sector, market cap.
- Trend filters: SMA/EMA 20/50/100/200, slope, price above/below moving average, supertrend.
- Momentum filters: RSI, MACD, relative strength, 52-week-high distance.
- Breakout filters: 20-day high, 55-day high, Darvas box breakout, volume confirmation.
- Pullback filters: moving-average support, ATR pullback, RSI reset.
- Fundamental filters: enhanced fundamental score, earnings quality, sales growth, financial strength, institutional backing.
- Risk rules: ATR stop, swing-low stop, fixed-percent stop, trailing stop.
- Add rules: add after `+1R`, add on new high, add after pullback holds support.
- Exit rules: stop hit, stage deterioration, close below moving average, technical damage, time stop.

Validation rules:

- Reject unknown indicators and operators.
- Reject missing entry, exit, or stop rules.
- Reject shorts, leverage, options, futures, and real-order instructions.
- Clamp risk values to hard rails.
- Store every accepted and rejected proposal with reason codes.

## Agent Responsibilities

### Trading Strategy Agent

Reads market regime, Stage 2 signal history, recent strategy metrics, and prior rejected/accepted proposals. It proposes new or revised strategy specs as JSON and explains why each strategy should exist.

It cannot execute trades directly. Its output goes through `strategy_compiler.py`.

### Portfolio Manager Agent

Chooses active strategies and capital allocation after strategies are validated. It converts deterministic strategy signals into target paper orders, resolves conflicts when strategies select the same symbol, enforces hard portfolio rails, and logs every allocation decision.

### Monitoring Agent

Runs after EOD in the MVP and can later add intraday scans. It checks open positions for stop risk, exit triggers, add triggers, gap risk, and technical deterioration. It emits alerts and paper action recommendations but does not bypass the paper broker.

### Report Agent

Builds Markdown and HTML reports under `portfolio/data/reports/daily/`. It summarizes P&L, strategy comparison, open risks, agent decisions, trade journal, and next-day plan. It can reuse visual/report patterns from existing Agent Adda reports where practical.

## Execution Model

The MVP replay uses EOD data only:

1. At the end of each trading date, load the available EOD feature set.
2. Generate candidate signals from validated strategies.
3. Let the Portfolio Manager Agent choose paper orders within hard rails.
4. Fill entries at the next available open.
5. If open is unavailable, fill at the next available close and mark the fill as degraded.
6. Evaluate stops using daily high/low where available.
7. Apply stop exits before rule exits.
8. Apply add-on trades only after the original trade has positive risk progress and the add rule fires.
9. Record every order, fill, position change, and daily account mark.

If multiple strategies select the same stock, the MVP should merge exposure by symbol and keep per-strategy attribution on the order record. The portfolio manager cannot exceed the symbol-level max position cap.

## Metrics

Portfolio metrics:

- Daily NAV.
- Cash, gross exposure, net exposure.
- Open P&L and closed P&L.
- Daily return.
- Cumulative return.
- Max drawdown.
- Turnover.
- Exposure utilization.

Trade metrics:

- Entry date, exit date, holding period.
- Entry price, exit price, stop, target where available.
- Exit reason.
- Gross P&L and P&L percent.
- R multiple.
- MAE/MFE where high/low data supports it.
- Add-on count and add-on contribution.

Strategy metrics:

- Trade count.
- Win rate.
- Average win.
- Average loss.
- Expectancy.
- Profit factor.
- Return contribution.
- Max drawdown contribution.
- Hit rate by regime.
- Hit rate by sector.
- Add-on success rate.
- Exit reason distribution.

Stage 2 metrics:

- Stage 2 entry follow-through.
- Stage 2 failure rate.
- Performance after new Stage 2 entry.
- Performance after Stage 2 exit.
- Signal decay by days since Stage 2 transition.

## Reports

Daily report sections:

- Executive summary.
- Portfolio NAV and P&L.
- Active strategies and allocation.
- New paper trades.
- Closed trades.
- Add-on trades.
- Stops and exits.
- Open risk.
- Strategy leaderboard.
- Stage 2 signal performance.
- Agent action log summary.
- Next-day watchlist and plan.

Strategy report sections:

- Strategy definition.
- Accepted/rejected proposal history.
- Backtest period and data coverage.
- Performance metrics.
- Trade table.
- Sector and symbol attribution.
- Regime attribution.
- Failure modes.
- Suggested next experiment.

## Audit Log

Each agent action writes one JSONL record to `portfolio/data/logs/agent_actions.jsonl`.

Record shape:

```json
{
  "timestamp": "2026-05-31T00:00:00+05:30",
  "agent": "portfolio_manager",
  "run_id": "paper_20260531_001",
  "input_refs": ["scores.stage_snapshots:2026-05-29"],
  "decision": "activate_strategy",
  "rationale": "Strategy has positive expectancy and acceptable drawdown over replay window.",
  "outputs": {"strategy_id": "stage2_pullback_quality_v1"},
  "status": "accepted"
}
```

Rejected strategy proposals must be logged with `status: "rejected"` and a machine-readable `reason`.

## CLI

Initial commands:

```bash
.venv/bin/python -m portfolio.cli propose-strategies --as-of 2025-01-01
.venv/bin/python -m portfolio.cli replay --from 2025-01-01 --to latest
.venv/bin/python -m portfolio.cli daily --date latest
.venv/bin/python -m portfolio.cli report --date latest
.venv/bin/python -m portfolio.cli status
```

The replay command is the MVP integration path. It must be deterministic for a fixed strategy registry and data snapshot.

## Testing Strategy

Use test-driven development for implementation.

Minimum tests:

- Strategy schema accepts a valid Stage 2 strategy.
- Strategy schema rejects unknown indicators.
- Strategy schema rejects missing stop rules.
- Strategy compiler clamps excessive risk to hard rails.
- Paper broker fills next-open entries.
- Paper broker records degraded fills when open is unavailable.
- Stops execute before rule exits.
- Portfolio account prevents position sizes above the max cap.
- Portfolio account records daily NAV.
- Metrics compute win rate, expectancy, drawdown, and R multiple.
- Agent action logger writes valid JSONL records.
- Report agent writes a daily Markdown report with required sections.
- Replay from a tiny fixture produces deterministic trade ledger and NAV output.

## Implementation Phasing

Phase 1: Deterministic foundation.

- Build schema, compiler, paper account, paper broker, metrics, and replay over a small fixture.
- Use a static sample strategy spec before invoking an LLM.
- Produce CSV logs and a Markdown daily report.

Phase 2: LLM strategy proposal.

- Add Trading Strategy Agent prompt and JSON validation.
- Store accepted/rejected proposals.
- Compare multiple strategies in a replay.

Phase 3: Portfolio manager and report agent.

- Add strategy allocation and conflict resolution.
- Add comprehensive HTML reports.

Phase 4: Monitoring.

- Add EOD monitoring of open positions and alert reports.
- Later add intraday monitoring as alerts only, not execution.

## Open Design Decisions For Implementation

The implementation plan should choose conservative defaults for:

- Initial paper capital, unless the user provides a value before implementation.
- Whether strategy proposals run once at the start of replay or periodically during replay.
- Whether HTML reports use a new lightweight template or adapt an existing report style.

These defaults must remain configurable in `portfolio/config.yaml`.
