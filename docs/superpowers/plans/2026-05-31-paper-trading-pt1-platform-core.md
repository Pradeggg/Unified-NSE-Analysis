# Paper Trading PT-1 Platform Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the PT-1 platform-grade backtest core on top of PT-0: data-quality gates, richer cost/fill simulation, reproducibility manifests, benchmark comparison, and built-in strategy templates.

**Architecture:** Keep PT-1 deterministic and paper-only. Add focused engine modules that can be used independently and then wire them into the existing CLI artifact path without changing the PT-0 replay semantics unless explicit options are used. Strategy templates remain declarative specs validated by the existing strategy schema/compiler.

**Tech Stack:** Python 3.13-compatible standard library, `pandas`, `pytest`, existing repo `.venv`, JSON/JSONL/Markdown artifacts.

---

## File Structure

Create:

- `portfolio/engine/validation.py`: deterministic OHLCV data-quality gates and JSON-safe reports.
- `portfolio/engine/run_manifest.py`: reproducibility manifest with config/spec/data/artifact checksums and git metadata.
- `portfolio/engine/benchmark.py`: benchmark/equity-curve comparison helpers.
- `portfolio/engine/strategy_library.py`: built-in strategy specs/templates for PT-1 families.
- `tests/portfolio/test_validation_manifest.py`: data-quality and manifest tests.
- `tests/portfolio/test_execution_costs.py`: richer execution model tests.
- `tests/portfolio/test_benchmark_strategy_library.py`: benchmark and strategy-template tests.

Modify:

- `portfolio/engine/order_types.py`: add bracket/trailing/stop-limit/cancel-replace simulation enum values while preserving existing fields.
- `portfolio/engine/execution_models.py`: add configurable cost model and support market-on-close, limit, stop, and stop-limit fills.
- `portfolio/cli.py`: write validation, benchmark, and manifest artifacts during `replay`; include manifest path in status/report where practical.
- `portfolio/README.md`: document PT-1 artifacts and limits.
- `tests/portfolio/test_cli.py`: prove new artifacts are written and remain JSON-safe.

Do not modify existing `backtesting/` behavior.

## Task 1: Data Quality Gates And Manifest

**Files:**
- Create: `portfolio/engine/validation.py`
- Create: `portfolio/engine/run_manifest.py`
- Test: `tests/portfolio/test_validation_manifest.py`

- [ ] **Step 1: Write failing tests**

Create `tests/portfolio/test_validation_manifest.py` with tests that assert:

```python
from __future__ import annotations

import json

import pandas as pd
import pytest

from portfolio.engine.run_manifest import build_run_manifest, checksum_payload
from portfolio.engine.validation import Severity, validate_ohlcv
from tests.portfolio.fixtures import sample_ohlcv, valid_strategy_spec


def test_validate_ohlcv_accepts_fixture_without_errors():
    report = validate_ohlcv(sample_ohlcv())

    assert report.error_count == 0
    assert report.row_count == 6
    assert report.symbol_count == 1
    assert report.is_usable
    assert report.as_dict()["issues"] == []


def test_validate_ohlcv_flags_malformed_bars_deterministically():
    frame = sample_ohlcv()
    frame.loc[1, "high"] = 99.0
    frame.loc[2, "volume"] = 0
    frame = pd.concat([frame, frame.iloc[[2]]], ignore_index=True)

    report = validate_ohlcv(frame)

    codes = [issue.code for issue in report.issues]
    assert "invalid_ohlc_range" in codes
    assert "zero_volume" in codes
    assert "duplicate_bar" in codes
    assert report.error_count == 1
    assert report.warning_count == 2


def test_validate_ohlcv_rejects_missing_required_columns():
    frame = sample_ohlcv().drop(columns=["close"])

    report = validate_ohlcv(frame)

    assert not report.is_usable
    assert report.error_count == 1
    assert report.issues[0].code == "missing_column"
    assert report.issues[0].severity == Severity.ERROR


def test_build_run_manifest_is_json_safe_and_checksum_stable(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"ok": true}', encoding="utf-8")

    manifest = build_run_manifest(
        run_id="PT-1",
        config={"initial_capital": 1000000.0},
        strategy_specs=[valid_strategy_spec()],
        data=sample_ohlcv(),
        artifacts={"state": state_path},
    )

    payload = manifest.as_dict()
    json.dumps(payload)
    assert payload["run_id"] == "PT-1"
    assert payload["strategy_count"] == 1
    assert payload["data"]["row_count"] == 6
    assert payload["checksums"]["strategies"] == checksum_payload([valid_strategy_spec()])
    assert payload["artifacts"]["state"].endswith("state.json")
```

- [ ] **Step 2: Run RED**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_validation_manifest.py -q
```

Expected: fails because `portfolio.engine.validation` and `portfolio.engine.run_manifest` do not exist.

- [ ] **Step 3: Implement `validation.py`**

Implement dataclasses:

```python
class Severity(StrEnum): ERROR = "ERROR"; WARNING = "WARNING"
@dataclass(frozen=True) class DataQualityIssue: code, severity, message, symbol, timestamp, row_index
@dataclass(frozen=True) class DataQualityReport: row_count, symbol_count, issues
```

`validate_ohlcv(data)` must:

- Require `date`, `symbol`, `open`, `high`, `low`, `close`, `volume`.
- Drop no rows; it reports issues only.
- Emit `missing_column` as an error.
- Emit `invalid_ohlc_range` as an error when high is below open/close/low or low is above open/close/high.
- Emit `zero_volume` as a warning for `volume <= 0`.
- Emit `duplicate_bar` as a warning for duplicated `date,symbol`.
- Provide `error_count`, `warning_count`, `is_usable`, and `as_dict()`.

- [ ] **Step 4: Implement `run_manifest.py`**

Implement:

```python
checksum_payload(payload: Any) -> str
build_run_manifest(run_id: str, config: dict, strategy_specs: list[dict], data: pd.DataFrame, artifacts: dict[str, Path | str]) -> RunManifest
```

The manifest must include run id, generated timestamp, git commit if available, config/spec/data checksums, artifact paths, strategy count, and data row/symbol counts. Use stable JSON sorting for checksums.

- [ ] **Step 5: Run tests and commit**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_validation_manifest.py -q
.venv/bin/python -m pytest tests/portfolio -q
```

Commit:

```bash
git add portfolio/engine/validation.py portfolio/engine/run_manifest.py tests/portfolio/test_validation_manifest.py
git commit -m "feat: add paper data validation manifest"
```

## Task 2: Richer Execution Cost Model

**Files:**
- Modify: `portfolio/engine/order_types.py`
- Modify: `portfolio/engine/execution_models.py`
- Test: `tests/portfolio/test_execution_costs.py`

- [ ] **Step 1: Write failing tests**

Create `tests/portfolio/test_execution_costs.py` with tests that assert:

```python
from __future__ import annotations

import pandas as pd

from portfolio.engine.execution_models import CostModel, NextOpenExecutionModel
from portfolio.engine.order_types import Order, OrderSide, OrderType


def _order(order_type: OrderType, side: OrderSide = OrderSide.BUY, **kwargs) -> Order:
    return Order(
        order_id="o1",
        symbol="AAA",
        side=side,
        quantity=10,
        order_type=order_type,
        submitted_at="2025-01-01",
        strategy_id="s1",
        reason="test",
        **kwargs,
    )


def _bar() -> pd.Series:
    return pd.Series(
        {
            "date": "2025-01-02",
            "open": 100.0,
            "high": 110.0,
            "low": 95.0,
            "close": 108.0,
            "volume": 1000,
        }
    )


def test_cost_model_combines_slippage_fees_and_tax():
    model = NextOpenExecutionModel(
        cost_model=CostModel(
            brokerage_bps=10.0,
            transaction_tax_bps=5.0,
            slippage_bps=20.0,
            fixed_fee=2.0,
        )
    )

    fill = model.try_fill(_order(OrderType.MARKET_NEXT_OPEN), _bar())

    assert fill is not None
    assert fill.price == 100.2
    assert fill.fees == 3.503
    assert fill.slippage == 2.0


def test_market_on_close_fills_at_close_with_sell_slippage():
    model = NextOpenExecutionModel(cost_model=CostModel(slippage_bps=10.0))

    fill = model.try_fill(_order(OrderType.MARKET_ON_CLOSE, OrderSide.SELL), _bar())

    assert fill is not None
    assert fill.price == 107.892


def test_limit_order_requires_price_touch():
    model = NextOpenExecutionModel()

    assert model.try_fill(_order(OrderType.LIMIT, limit_price=94.0), _bar()) is None
    fill = model.try_fill(_order(OrderType.LIMIT, limit_price=96.0), _bar())

    assert fill is not None
    assert fill.price == 96.0


def test_stop_limit_requires_stop_and_limit_touch():
    model = NextOpenExecutionModel()

    fill = model.try_fill(
        _order(OrderType.STOP_LIMIT, stop_price=106.0, limit_price=107.0),
        _bar(),
    )

    assert fill is not None
    assert fill.price == 107.0
```

- [ ] **Step 2: Run RED**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_execution_costs.py -q
```

Expected: fails because `CostModel` and `STOP_LIMIT` are missing.

- [ ] **Step 3: Extend order types**

Add enum values without removing existing values:

- `STOP_LIMIT`
- `TRAILING_STOP`
- `BRACKET`
- `CANCEL_REPLACE`

- [ ] **Step 4: Implement cost model and fill types**

Add `CostModel` dataclass to `execution_models.py` with:

- `brokerage_bps`
- `transaction_tax_bps`
- `slippage_bps`
- `fixed_slippage`
- `fixed_fee`
- `max_participation_pct`

`NextOpenExecutionModel` must accept either legacy `brokerage_bps/slippage_bps` or `cost_model`. Implement fills for:

- `MARKET_NEXT_OPEN`: open price.
- `MARKET_ON_CLOSE`: close price.
- `LIMIT`: buy fills when low <= limit, sell fills when high >= limit.
- `STOP`: buy fills when high >= stop, sell fills when low <= stop.
- `STOP_LIMIT`: buy requires high >= stop and low <= limit; sell requires low <= stop and high >= limit.

Unsupported `TRAILING_STOP`, `BRACKET`, and `CANCEL_REPLACE` return `None` in PT-1.

- [ ] **Step 5: Run tests and commit**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_execution_costs.py tests/portfolio/test_paper_broker.py tests/portfolio/test_event_loop.py -q
.venv/bin/python -m pytest tests/portfolio -q
```

Commit:

```bash
git add portfolio/engine/order_types.py portfolio/engine/execution_models.py tests/portfolio/test_execution_costs.py
git commit -m "feat: add paper execution cost model"
```

## Task 3: Benchmark Comparison

**Files:**
- Create: `portfolio/engine/benchmark.py`
- Test: `tests/portfolio/test_benchmark_strategy_library.py`

- [ ] **Step 1: Write benchmark tests**

Create `tests/portfolio/test_benchmark_strategy_library.py` with benchmark tests:

```python
from __future__ import annotations

import pandas as pd

from portfolio.engine.benchmark import compare_to_benchmark


def test_compare_to_benchmark_calculates_relative_return_and_drawdown():
    nav = [
        {"timestamp": "2025-01-01", "equity": 100.0},
        {"timestamp": "2025-01-02", "equity": 110.0},
        {"timestamp": "2025-01-03", "equity": 105.0},
    ]
    benchmark = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"]),
            "close": [200.0, 210.0, 220.0],
        }
    )

    result = compare_to_benchmark(nav, benchmark, benchmark_id="NIFTY_TEST")

    assert result.benchmark_id == "NIFTY_TEST"
    assert round(result.portfolio_return_pct, 4) == 5.0
    assert round(result.benchmark_return_pct, 4) == 10.0
    assert round(result.excess_return_pct, 4) == -5.0
    assert result.observation_count == 3
```

- [ ] **Step 2: Run RED**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_benchmark_strategy_library.py::test_compare_to_benchmark_calculates_relative_return_and_drawdown -q
```

Expected: fails because `portfolio.engine.benchmark` does not exist.

- [ ] **Step 3: Implement benchmark helper**

Implement `BenchmarkComparison` dataclass and `compare_to_benchmark(nav_history, benchmark_data, benchmark_id)` that:

- Aligns by date.
- Uses first and last aligned equity/close to compute returns.
- Computes portfolio and benchmark max drawdown.
- Exposes `as_dict()`.
- Returns zero/empty metrics when no alignment exists.

- [ ] **Step 4: Run test**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_benchmark_strategy_library.py -q
```

Expected: benchmark test passes; strategy-library tests will be added in Task 4.

## Task 4: Built-In Strategy Library

**Files:**
- Create: `portfolio/engine/strategy_library.py`
- Modify: `tests/portfolio/test_benchmark_strategy_library.py`

- [ ] **Step 1: Add strategy library tests**

Extend `tests/portfolio/test_benchmark_strategy_library.py` with:

```python
from portfolio.engine.strategy_library import built_in_strategy_specs, get_strategy_spec
from portfolio.engine.strategy_schema import validate_strategy_spec


def test_built_in_strategy_specs_cover_popular_families_and_validate():
    specs = built_in_strategy_specs()
    ids = {spec["strategy_id"] for spec in specs}

    assert {
        "stage2_continuation_v1",
        "donchian_turtle_breakout_v1",
        "moving_average_trend_v1",
        "momentum_rotation_v1",
        "vcp_breakout_v1",
        "darvas_box_breakout_v1",
        "mean_reversion_uptrend_v1",
        "minervini_trend_template_v1",
    }.issubset(ids)

    for spec in specs:
        validate_strategy_spec(spec)


def test_get_strategy_spec_returns_deep_copy():
    first = get_strategy_spec("stage2_continuation_v1")
    first["name"] = "mutated"
    second = get_strategy_spec("stage2_continuation_v1")

    assert second["name"] != "mutated"
```

- [ ] **Step 2: Run RED**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_benchmark_strategy_library.py -q
```

Expected: fails because `strategy_library` does not exist.

- [ ] **Step 3: Implement strategy library**

Implement:

```python
built_in_strategy_specs() -> list[dict[str, Any]]
get_strategy_spec(strategy_id: str) -> dict[str, Any]
```

Each template must be a valid strategy spec under the existing grammar and include explicit entry, exit, and ATR stop. The templates should map unavailable advanced concepts to currently supported indicators without inventing executable unsupported fields.

- [ ] **Step 4: Run tests and commit benchmark/library**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_benchmark_strategy_library.py -q
.venv/bin/python -m pytest tests/portfolio -q
```

Commit:

```bash
git add portfolio/engine/benchmark.py portfolio/engine/strategy_library.py tests/portfolio/test_benchmark_strategy_library.py
git commit -m "feat: add paper benchmark strategy library"
```

## Task 5: CLI PT-1 Artifacts

**Files:**
- Modify: `portfolio/cli.py`
- Modify: `portfolio/README.md`
- Test: `tests/portfolio/test_cli.py`

- [ ] **Step 1: Add failing CLI tests**

Add tests to `tests/portfolio/test_cli.py` proving replay writes:

- `validation/data_quality.json`
- `manifest/run_manifest.json`
- `benchmarks/benchmark.json`

The test should parse each JSON file and assert:

```python
assert validation["row_count"] == 6
assert manifest["run_id"] == "PT-0"
assert manifest["strategy_count"] == 1
assert benchmark["benchmark_id"] == "fixture_buy_hold"
```

- [ ] **Step 2: Run RED**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_cli.py -q
```

Expected: fails because PT-1 artifact files are not written.

- [ ] **Step 3: Wire validation, benchmark, and manifest**

In `portfolio/cli.py`:

- Define artifact paths:
  - `VALIDATION_RELATIVE_PATH = Path("validation/data_quality.json")`
  - `MANIFEST_RELATIVE_PATH = Path("manifest/run_manifest.json")`
  - `BENCHMARK_RELATIVE_PATH = Path("benchmarks/benchmark.json")`
- During `replay`, call `validate_ohlcv(data)` and write JSON report before replay.
- Build a simple fixture benchmark from the same OHLCV close series and compare against replay NAV with `benchmark_id="fixture_buy_hold"`.
- Build and write run manifest after all artifact paths are known.
- Add the new paths to replay stdout and audit payload.

- [ ] **Step 4: Update README**

Update `portfolio/README.md` generated artifacts section with the three new files and note PT-1 has validation, benchmark, and manifest outputs.

- [ ] **Step 5: Run tests and commit**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_cli.py tests/portfolio/test_validation_manifest.py tests/portfolio/test_benchmark_strategy_library.py -q
.venv/bin/python -m pytest tests/portfolio -q
```

Commit:

```bash
git add portfolio/cli.py portfolio/README.md tests/portfolio/test_cli.py
git commit -m "feat: write paper pt1 replay artifacts"
```

## Task 6: Backlog Status And Final Verification

**Files:**
- Modify: `docs/BACKLOG.md`

- [ ] **Step 1: Update backlog**

In `docs/BACKLOG.md`, update only the PT-1 row:

- Status: `✅ DONE`
- Design / Implementation: mention data-quality gates, richer execution cost model, run manifests, benchmark comparison, and built-in strategy templates.
- Acceptance Criteria: mention `.venv/bin/python -m pytest tests/portfolio -q` and the new CLI artifacts.

- [ ] **Step 2: Run final verification**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio -q
.venv/bin/python -m portfolio.cli replay --output-dir /tmp/portfolio-pt1-smoke
.venv/bin/python -m portfolio.cli status --output-dir /tmp/portfolio-pt1-smoke
.venv/bin/python -m portfolio.cli report --output-dir /tmp/portfolio-pt1-smoke --print
```

Expected:

- Portfolio tests pass.
- Replay exits 0 and writes PT-0/PT-1 artifacts.
- Status exits 0.
- Report prints Markdown beginning with `# Paper Trading Report`.

- [ ] **Step 3: Commit**

Commit:

```bash
git add docs/BACKLOG.md
git commit -m "docs: mark paper trading pt1 complete"
```

## Self-Review

Spec coverage:

- Data-quality warnings/errors are covered in Task 1 and wired to CLI in Task 5.
- Fees/slippage and richer order types are covered in Task 2.
- Benchmark comparison is covered in Task 3 and wired to CLI in Task 5.
- Run manifests are covered in Task 1 and wired to CLI in Task 5.
- Built-in Stage 2/Donchian/moving-average/momentum/VCP/Darvas/mean-reversion/Minervini templates are covered in Task 4.
- Final verification and backlog status are covered in Task 6.

Known PT-1 limits:

- Corporate actions, walk-forward validation, and LLM proposal agents remain PT-2/PT-3 work.
- The benchmark wired into the CLI is a deterministic fixture buy-and-hold baseline until real benchmark data is connected.
- Advanced order enums that require ongoing state, such as trailing stops and brackets, are declared but return no fill in PT-1.
