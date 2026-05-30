# Paper Trading Strategy Lab Design

## Purpose

Build a paper-trading strategy lab that starts from zero positions on `2025-01-01`, replays EOD market data, lets an LLM propose strategy definitions from allowed building blocks, compiles those definitions into deterministic rules, executes paper trades, compares strategy performance, and generates comprehensive daily reports.

This is a research and strategy-assessment system only. It must not place real broker orders in the MVP.

The long-term target is a comprehensive local strategy engine comparable in discipline to mature backtesting platforms: event-driven execution, reproducible data snapshots, realistic order simulation, transaction-cost models, analyzers, benchmark comparison, parameter sweeps, walk-forward validation, and multi-strategy portfolio attribution.

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
- Support a strategy library broad enough to test popular systematic trading families, not only Stage 2 variants.
- Separate strategy definition, signal generation, portfolio construction, risk management, execution simulation, and analytics.
- Make backtest assumptions visible in every report.

The system must not:

- Execute live broker orders.
- Use leverage, shorts, options, or futures in the MVP.
- Let LLM narrative directly place or mutate trades without deterministic validation.
- Rewrite existing reports or portfolio analyzer behavior unless explicitly needed for integration.

## Platform-Grade Engine Requirements

The engine should be designed as a modular research platform, not a single strategy script.

Required capabilities:

- Event-driven replay loop with explicit event order: data update, signal generation, portfolio target generation, risk checks, order creation, order fill simulation, position accounting, metrics, logging, report generation.
- Deterministic runs for a fixed data snapshot, strategy registry, and config.
- Point-in-time data access so strategies cannot use future data.
- Separate portfolio target model from order model so agents express desired exposure and the paper broker decides fills.
- Multiple order types for simulation: market-next-open, market-on-close, limit, stop, stop-limit, trailing stop, bracket order, and cancel/replace.
- Transaction-cost model: brokerage, taxes/fees, slippage in basis points, fixed slippage, liquidity participation cap, and gap slippage.
- Corporate-action adjustment handling where available: splits, bonuses, dividends, symbol changes, and delistings.
- Data-quality gates: missing OHLCV, stale prices, outlier candles, zero-volume bars, suspended symbols, duplicate bars, and insufficient lookback.
- Benchmark support: Nifty 50, Nifty 500, relevant sector index, equal-weight universe, and buy-and-hold baseline.
- Parameter sweep support for deterministic strategy variants.
- Walk-forward validation with train, validation, and locked test periods.
- Regime-aware attribution by trend regime, breadth regime, volatility regime, and FII/DII flow regime.
- Reproducibility bundle per run: config, strategy specs, data snapshot references, code version, generated outputs, and run checksum.
- Failure-mode reporting: strategies that fail due to insufficient data, low trade count, excessive turnover, high drawdown, or unstable validation.

The MVP may implement a narrow subset, but the folder and interfaces must leave room for these features without redesigning the engine.

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
    event_loop.py
    events.py
    execution_models.py
    feature_engine.py
    metrics.py
    order_types.py
    paper_broker.py
    portfolio_account.py
    risk_models.py
    run_manifest.py
    strategy_compiler.py
    strategy_schema.py
    strategy_library.py
    validation.py
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
- `portfolio/engine/events.py`: defines replay event contracts for market data, signals, targets, orders, fills, risk alerts, and reports.
- `portfolio/engine/event_loop.py`: orchestrates event-driven replay in a deterministic sequence.
- `portfolio/engine/feature_engine.py`: computes reusable point-in-time indicators and multi-timeframe features.
- `portfolio/engine/order_types.py`: defines supported paper order contracts.
- `portfolio/engine/execution_models.py`: simulates fills, slippage, fees, and liquidity constraints.
- `portfolio/engine/strategy_schema.py`: defines the allowed JSON strategy schema.
- `portfolio/engine/strategy_compiler.py`: validates LLM strategy proposals and compiles them into deterministic rule objects.
- `portfolio/engine/strategy_library.py`: provides built-in reference strategies and templates for the LLM to modify.
- `portfolio/engine/risk_models.py`: enforces trade-level, position-level, and portfolio-level risk rails.
- `portfolio/engine/paper_broker.py`: simulates paper orders and fills.
- `portfolio/engine/portfolio_account.py`: tracks cash, positions, orders, realized/unrealized P&L, and NAV.
- `portfolio/engine/metrics.py`: computes trade, portfolio, and per-strategy metrics.
- `portfolio/engine/validation.py`: runs data-quality, lookahead, and strategy-validity checks.
- `portfolio/engine/run_manifest.py`: records reproducibility metadata for every replay.
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

## Strategy Library Coverage

The system should support a broad strategy catalog so the Trading Strategy Agent can compare Stage 2 concepts against popular global systematic families.

Initial strategy families:

- Stage 2 continuation: Weinstein-style price above rising moving-average stack.
- Stage 2 pullback: buy pullbacks to SMA/EMA support inside confirmed uptrends.
- Minervini / superperformance: near 52-week high, high relative strength, tightening volatility, strong trend template.
- CAN SLIM-inspired: technical strength plus earnings/sales/fundamental quality filters where data exists.
- Donchian / Turtle breakout: 20-day and 55-day breakout entries with ATR-based exits.
- Moving-average trend following: golden cross, EMA ribbon, SMA 50/200 trend filters.
- Momentum rotation: rank securities by 3-month/6-month/12-month momentum and rebalance periodically.
- Relative-strength leaders: top percentile RS versus Nifty 500 or sector index.
- Volatility contraction pattern: narrowing ranges and volume contraction before breakout.
- Darvas box breakout: box high breakout with stop below box low.
- Mean reversion in uptrend: RSI pullback or Bollinger-band pullback while higher timeframe remains bullish.
- Opening gap continuation as an alert-only family until intraday execution is added.
- Supertrend continuation: bullish supertrend state with trend and volume confirmation.
- Sector rotation overlay: only trade stocks from leading sectors or sectors improving relative strength.
- Fundamental quality overlay: apply earnings quality, sales growth, financial strength, and institutional backing filters.

The LLM may propose new combinations, but the compiler must map them to these allowed primitives. Unsupported strategies should be rejected with a reason rather than approximated silently.

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
- Breakout filters: 20-day high, 55-day high, Donchian breakout, Darvas box breakout, volume confirmation.
- Pullback filters: moving-average support, ATR pullback, RSI reset.
- Fundamental filters: enhanced fundamental score, earnings quality, sales growth, financial strength, institutional backing.
- Risk rules: ATR stop, swing-low stop, fixed-percent stop, trailing stop, portfolio heat cap, sector exposure cap.
- Add rules: add after `+1R`, add on new high, add after pullback holds support.
- Exit rules: stop hit, stage deterioration, close below moving average, technical damage, time stop.
- Rebalance rules: daily, weekly, monthly, signal-triggered, volatility-triggered.

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

1. `MarketDataEvent`: load the current trading date's point-in-time EOD feature set.
2. `SignalEvent`: generate strategy signals from validated strategies.
3. `PortfolioTargetEvent`: let the Portfolio Manager Agent choose target exposure within hard rails.
4. `RiskCheckEvent`: apply trade, symbol, sector, strategy, liquidity, and portfolio heat limits.
5. `OrderEvent`: convert approved targets into paper orders.
6. `FillEvent`: fill entries at the next available open by default.
7. `FallbackFillEvent`: if open is unavailable, fill at the next available close and mark the fill as degraded.
8. `StopEvent`: evaluate stops using daily high/low where available.
9. `ExitEvent`: apply stop exits before rule exits, then time exits and portfolio-level risk exits.
10. `AddEvent`: apply add-on trades only after the original trade has positive risk progress and the add rule fires.
11. `AccountingEvent`: record every order, fill, position change, cash movement, fee, and daily account mark.
12. `ReportEvent`: write logs, metrics, and reports.

If multiple strategies select the same stock, the MVP should merge exposure by symbol and keep per-strategy attribution on the order record. The portfolio manager cannot exceed the symbol-level max position cap.

## Backtest Validation And Research Workflow

The engine must support both portfolio replay and strategy research workflows.

Validation workflow:

- Split data into train, validation, and locked test periods.
- Allow the Trading Strategy Agent to design or tune strategies only on train and validation periods.
- Keep the locked test period unavailable until the strategy is frozen.
- Run benchmark comparisons on the same dates and universe.
- Require minimum trade count before ranking a strategy as reliable.
- Flag overfit strategies when train results are strong but validation results deteriorate materially.
- Track parameter sensitivity across sweeps.
- Track implementation assumptions that can change conclusions, especially slippage, fees, order timing, and liquidity.

Strategy comparison modes:

- Single-strategy backtest.
- Multi-strategy independent backtest.
- Multi-strategy combined portfolio simulation.
- Walk-forward strategy selection where the agent chooses active strategies based only on prior metrics.
- Strategy ensemble where multiple strategies contribute to one target allocation.

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
- Alpha and beta versus benchmark where benchmark data exists.
- Information ratio versus benchmark where enough observations exist.
- Calmar ratio.
- Sortino ratio.
- Rolling return and rolling drawdown.
- Capacity proxy based on turnover and average traded value.

Trade metrics:

- Entry date, exit date, holding period.
- Entry price, exit price, stop, target where available.
- Exit reason.
- Gross P&L and P&L percent.
- R multiple.
- MAE/MFE where high/low data supports it.
- Add-on count and add-on contribution.
- Slippage and fee impact.
- Planned R versus realized R.
- Entry quality: next-day gap, follow-through, and adverse excursion.

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
- Parameter sensitivity.
- Walk-forward stability.
- Train/validation/test consistency.
- Benchmark-relative return.
- Cost sensitivity under multiple fee/slippage assumptions.

Stage 2 metrics:

- Stage 2 entry follow-through.
- Stage 2 failure rate.
- Performance after new Stage 2 entry.
- Performance after Stage 2 exit.
- Signal decay by days since Stage 2 transition.

Risk metrics:

- Portfolio heat.
- Concentration by symbol, sector, strategy, and theme.
- Correlation concentration between open positions.
- Worst single-position loss.
- Worst sector loss.
- Gap risk on open positions.
- Stop distance and capital at risk.
- Liquidity participation estimate.

Data and engine integrity metrics:

- Symbols skipped due to missing data.
- Bars skipped due to data quality.
- Degraded fills.
- Corporate-action warnings.
- Lookahead validation status.
- Run checksum and reproducibility metadata.

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
- Benchmark comparison.
- Data-quality and degraded-fill summary.
- Backtest assumption summary.

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
- Parameter sweep table.
- Walk-forward validation table.
- Cost sensitivity table.
- Benchmark-relative performance.

Platform-grade report sections:

- Strategy catalog coverage.
- Strategy leaderboard across families.
- Portfolio construction attribution.
- Risk model decisions.
- Execution model assumptions.
- Data integrity and reproducibility manifest.

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
.venv/bin/python -m portfolio.cli backtest --strategy stage2_pullback_quality_v1 --from 2025-01-01 --to latest
.venv/bin/python -m portfolio.cli sweep --strategy turtle_breakout --param atr_multiple=1.5,2.0,2.5
.venv/bin/python -m portfolio.cli walk-forward --from 2025-01-01 --to latest
.venv/bin/python -m portfolio.cli leaderboard --date latest
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
- Event loop emits events in the documented order.
- Limit, stop, trailing stop, and bracket orders produce deterministic fills in fixtures.
- Slippage and fees change results predictably.
- Lookahead validation catches future feature leakage.
- Walk-forward validation prevents the agent from accessing locked test results before freeze.
- Benchmark comparison uses the same date window as the strategy.
- Parameter sweep produces stable strategy IDs and metrics.
- Strategy leaderboard ranks by configured objective and includes reliability warnings.
- Data-quality gates skip stale or malformed bars with logged reasons.

## Implementation Phasing

Phase 1: Deterministic foundation.

- Build schema, compiler, event contracts, paper account, paper broker, metrics, and replay over a small fixture.
- Use a static sample strategy spec before invoking an LLM.
- Produce CSV logs and a Markdown daily report.

Phase 2: Platform-grade backtest core.

- Add order types, execution models, slippage, fees, benchmark comparison, data-quality gates, and run manifests.
- Add strategy library templates for Stage 2, Donchian/Turtle, moving average, momentum rotation, VCP, Darvas, mean reversion in uptrend, and Minervini-style trend templates.
- Add parameter sweep support.

Phase 3: LLM strategy proposal.

- Add Trading Strategy Agent prompt and JSON validation.
- Store accepted/rejected proposals.
- Compare multiple strategies in a replay.

Phase 4: Walk-forward and portfolio manager.

- Add train/validation/test splits and walk-forward strategy selection.
- Add strategy allocation and conflict resolution.
- Add combined multi-strategy portfolio simulation.

Phase 5: Report agent.

- Add comprehensive HTML reports.
- Add strategy leaderboard, cost sensitivity, benchmark comparison, data integrity, and reproducibility sections.

Phase 6: Monitoring.

- Add EOD monitoring of open positions and alert reports.
- Later add intraday monitoring as alerts only, not execution.

## Open Design Decisions For Implementation

The implementation plan should choose conservative defaults for:

- Initial paper capital, unless the user provides a value before implementation.
- Whether strategy proposals run once at the start of replay or periodically during replay.
- Whether HTML reports use a new lightweight template or adapt an existing report style.

These defaults must remain configurable in `portfolio/config.yaml`.
