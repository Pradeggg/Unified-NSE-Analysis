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
- CLI defaults: `replay`, `status`, and `report` default to run ID `PT-0`,
  initial capital `1000000`, built-in fixture OHLCV data, and the built-in
  `stage2_fixture_v1` strategy unless local input files are supplied.

## Current Limits And Backlog

- PT-0 uses fixture/default data by default; real EOD NSE data integration is
  not wired into this package yet.
- LLM strategy proposer agents and monitoring agents are not part of PT-0.
- There is no live trading or broker integration. Keep the engine paper-only
  unless a later design explicitly adds a broker path.
- PT-1+ backlog work is expected to add richer backtest/data-quality features,
  benchmark comparison, strategy libraries, LLM proposal validation, portfolio
  management, and monitoring.
