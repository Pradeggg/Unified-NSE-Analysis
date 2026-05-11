# EOD Strategy Lab Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first usable EOD Strategy Lab foundation: data readiness, strategy registry, technical pattern feature library, and deterministic terminal commands for listing/validating strategies.

**Architecture:** Add a focused `backtesting/` package with pure-Python contracts and deterministic helpers. Keep simulation/reporting for the next slice; this slice makes strategies discoverable and validates that local EOD data exists before backtests run.

**Tech Stack:** Python standard library, pandas/numpy if already available, SQLite via existing data files, unittest, Rich terminal rendering through existing `nse_agent.py` patterns.

---

### Task 1: Backtesting Data Contract

**Files:**
- Create: `backtesting/__init__.py`
- Create: `backtesting/data.py`
- Test: `tests/test_backtesting_data.py`

- [ ] **Step 1: Write failing tests**

```python
import tempfile
import unittest
from pathlib import Path

from backtesting.data import inspect_backtest_data


class BacktestingDataTests(unittest.TestCase):
    def test_missing_required_eod_file_blocks_backtests(self):
        with tempfile.TemporaryDirectory() as tmp:
            status = inspect_backtest_data(Path(tmp))
        self.assertFalse(status.ok_to_backtest)
        self.assertIn("missing_eod_ohlcv", status.blockers)

    def test_present_minimal_eod_file_allows_technical_only_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            (root / "data" / "nse_sec_full_data.csv").write_text(
                "SYMBOL,DATE,OPEN,HIGH,LOW,CLOSE,VOLUME\nDMART,2026-05-08,1,2,1,2,1000\n",
                encoding="utf-8",
            )
            status = inspect_backtest_data(root)
        self.assertTrue(status.ok_to_backtest)
        self.assertIn("technical-only", status.modes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m unittest tests.test_backtesting_data -v`
Expected: FAIL because `backtesting.data` does not exist.

- [ ] **Step 3: Implement minimal data contract**

Create `BacktestDataReadiness` dataclass and `inspect_backtest_data(project_root: Path)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m unittest tests.test_backtesting_data -v`
Expected: PASS.

### Task 2: Strategy Registry

**Files:**
- Create: `backtesting/strategy_registry.py`
- Test: `tests/test_backtesting_strategy_registry.py`

- [ ] **Step 1: Write failing tests**

```python
import unittest

from backtesting.strategy_registry import get_strategy, list_strategies


class StrategyRegistryTests(unittest.TestCase):
    def test_core_and_pattern_strategies_are_registered(self):
        ids = {strategy.id for strategy in list_strategies()}
        self.assertIn("stage2", ids)
        self.assertIn("minervini", ids)
        self.assertIn("supertrend_continuation", ids)
        self.assertIn("vcp", ids)
        self.assertIn("head_shoulders", ids)

    def test_unknown_strategy_reports_available_choices(self):
        with self.assertRaisesRegex(ValueError, "Available strategies"):
            get_strategy("unknown")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m unittest tests.test_backtesting_strategy_registry -v`
Expected: FAIL because `backtesting.strategy_registry` does not exist.

- [ ] **Step 3: Implement registry**

Create `StrategyDefinition`, register V1, V1.5, and experimental V2 technical strategies with required fields and status.

- [ ] **Step 4: Run tests**

Run: `./.venv/bin/python -m unittest tests.test_backtesting_strategy_registry -v`
Expected: PASS.

### Task 3: Technical Pattern Feature Library

**Files:**
- Create: `backtesting/patterns.py`
- Test: `tests/test_backtesting_patterns.py`

- [ ] **Step 1: Write failing tests**

```python
import unittest
import pandas as pd

from backtesting.patterns import compute_pattern_features, detect_vcp


class BacktestingPatternTests(unittest.TestCase):
    def test_compute_pattern_features_adds_indicators(self):
        df = pd.DataFrame({
            "date": pd.date_range("2026-01-01", periods=260, freq="D"),
            "open": range(260),
            "high": [x + 2 for x in range(260)],
            "low": [x - 1 for x in range(260)],
            "close": [x + 1 for x in range(260)],
            "volume": [1000 + x for x in range(260)],
        })
        out = compute_pattern_features(df)
        self.assertIn("sma_50", out.columns)
        self.assertIn("sma_200", out.columns)
        self.assertIn("atr_14", out.columns)
        self.assertIn("rsi_14", out.columns)
        self.assertIn("range_pct", out.columns)

    def test_detect_vcp_returns_rejection_reason_when_ranges_do_not_contract(self):
        df = pd.DataFrame({
            "date": pd.date_range("2026-01-01", periods=80, freq="D"),
            "open": [100] * 80,
            "high": [110] * 80,
            "low": [90] * 80,
            "close": [100] * 79 + [111],
            "volume": [1000] * 80,
        })
        signals = detect_vcp(df)
        self.assertTrue(signals)
        self.assertIn("range_not_contracting", signals[0].rejection_reasons)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m unittest tests.test_backtesting_patterns -v`
Expected: FAIL because `backtesting.patterns` does not exist.

- [ ] **Step 3: Implement minimal indicators and VCP detector contract**

Create `PatternSignal`, `compute_pattern_features()`, and `detect_vcp()` with deterministic no-lookahead rolling features.

- [ ] **Step 4: Run tests**

Run: `./.venv/bin/python -m unittest tests.test_backtesting_patterns -v`
Expected: PASS.

### Task 4: Terminal Backtest Commands

**Files:**
- Create: `terminal/backtest.py`
- Modify: `nse_agent.py`
- Test: `tests/test_nse_agent_backtest.py`

- [ ] **Step 1: Write failing tests**

```python
import unittest

from terminal.backtest import handle_backtest_command


class NSEAgentBacktestTests(unittest.TestCase):
    def test_backtest_list_renders_registered_strategies(self):
        output = handle_backtest_command("/backtest list")
        self.assertIn("stage2", output)
        self.assertIn("vcp", output)

    def test_strategy_lab_validate_reports_readiness(self):
        output = handle_backtest_command("/strategy-lab validate")
        self.assertIn("Strategy Lab", output)
        self.assertIn("EOD", output)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m unittest tests.test_nse_agent_backtest -v`
Expected: FAIL because `terminal.backtest` does not exist.

- [ ] **Step 3: Implement deterministic command handler and route in `nse_agent.py`**

Add `handle_backtest_command()` and route `/backtest` plus `/strategy-lab` before generic LLM handling.

- [ ] **Step 4: Run focused tests**

Run: `./.venv/bin/python -m unittest tests.test_backtesting_data tests.test_backtesting_strategy_registry tests.test_backtesting_patterns tests.test_nse_agent_backtest -v`
Expected: PASS.

### Task 5: Verification

- [ ] Run py_compile:

`./.venv/bin/python -m py_compile backtesting/data.py backtesting/strategy_registry.py backtesting/patterns.py terminal/backtest.py nse_agent.py`

- [ ] Run focused regression:

`./.venv/bin/python -m unittest tests.test_backtesting_data tests.test_backtesting_strategy_registry tests.test_backtesting_patterns tests.test_nse_agent_backtest -v`

- [ ] Run relevant existing terminal regression:

`./.venv/bin/python -m unittest tests.test_nse_agent_monitor_scan tests.test_market_knowledge -v`
