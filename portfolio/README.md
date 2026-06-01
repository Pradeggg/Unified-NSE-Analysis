# Paper Trading Foundation (PT-0)

PT-0 is the deterministic, paper-only foundation for the portfolio strategy lab.
It does not call LLMs, connect to live brokers, or place live trades. The current
runtime uses fixture/default data unless explicit local CSV/JSON inputs are
passed to the CLI.

## Quick Start

Run the deterministic replay and write artifacts under `portfolio/data/demo`:

```bash
.venv/bin/python -m portfolio.cli replay --output-dir portfolio/data/demo
```

Inspect the saved state and metrics:

```bash
.venv/bin/python -m portfolio.cli status --output-dir portfolio/data/demo
```

Print the Markdown report:

```bash
.venv/bin/python -m portfolio.cli report --output-dir portfolio/data/demo --print
```

Run the PostgreSQL-backed NSE strategy comparison after historical
`scores.stage_snapshots` are available:

```bash
.venv/bin/python -m portfolio.cli strategy-lab \
  --output-dir portfolio/data/nse_pg_strategy_lab/latest \
  --start 2025-01-01 \
  --lookback 2024-01-01 \
  --top-n 200 \
  --slippage-bps 5 \
  --brokerage-bps 3
```

Verify the portfolio test suite:

```bash
.venv/bin/python -m pytest tests/portfolio -q
```

## Generated Artifacts

The CLI writes these files below the selected `--output-dir`:

- `state/replay_state.json`: replay summary, account state, NAV history, orders,
  fills, positions, and emitted engine events.
- `metrics/metrics.json`: deterministic portfolio metrics such as starting and
  ending equity, total return, max drawdown, fill/trade counts, realized P&L,
  open positions, invalid fill sequences, and strategy IDs.
- `logs/audit.jsonl`: append-only JSONL audit entries for the replay and report
  generation actions.
- `reports/paper_trading_report.md`: deterministic Markdown report with summary
  metrics, strategy metrics, open positions, fills/trades, and audit reference.
- `validation/data_quality.json`: PT-1 OHLCV data-quality report from
  `validate_ohlcv`, including row/symbol counts, error and warning counts, and
  deterministic issue metadata.
- `benchmarks/benchmark.json`: PT-1 benchmark comparison from
  `compare_to_benchmark` against the deterministic `fixture_buy_hold` close
  series baseline.
- `manifest/run_manifest.json`: PT-1 reproducibility manifest from
  `build_run_manifest`, including run ID, strategy/data counts, git commit when
  available, stable checksums, and paths for replay artifacts.

## Components

- Strategy schema/compiler: validates strategy JSON against a static grammar,
  rejects unknown blocks/operators/indicators, and clamps risk rails before
  replay.
- Paper account/execution: models long-only cash, positions, submitted orders,
  fills, fees, realized P&L, duplicate-fill protection, and next-open fills.
- Event replay: normalizes OHLCV data, emits market/signal/order/fill/snapshot
  events, evaluates compiled strategies in date order, and records NAV history.
- Metrics/audit/report: calculates deterministic performance and trade metrics,
  writes JSONL audit rows, and renders a Markdown paper trading report.
- PT-1 validation/benchmark/manifest: records OHLCV data-quality gates, compares
  replay NAV to a deterministic buy-hold fixture baseline, and writes a
  reproducibility manifest with config, strategy, data, and artifact checksums.
- CLI defaults: `replay`, `status`, and `report` default to run ID `PT-0`,
  initial capital `1000000`, built-in fixture OHLCV data, and the built-in
  `stage2_fixture_v1` strategy unless local input files are supplied.
- PostgreSQL strategy lab: `strategy-lab` loads NSE EOD bars from
  `market.equity_eod`, joins historical stages from `scores.stage_snapshots`,
  runs each built-in strategy independently, compares to `Nifty 500`, and writes
  a leaderboard with return, drawdown, profit factor, expectancy, turnover, and
  cost drag.

## Current Limits And Backlog

- `replay` still uses fixture/default data by default; real EOD NSE data is
  available through the `strategy-lab` command.
- LLM strategy proposer agents and monitoring agents are not part of PT-0.
- There is no live trading or broker integration. Keep the engine paper-only
  unless a later design explicitly adds a broker path.
- Later PT-1+ backlog work is expected to add LLM proposal validation, portfolio
  management, monitoring, and live data integration around the paper-only core.
