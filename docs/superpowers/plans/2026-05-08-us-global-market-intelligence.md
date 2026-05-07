# US / Global Market Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a first-class daily US/global market intelligence layer with cached yfinance data, technical screeners, India read-through, HTML output, and terminal integration.

**Architecture:** Start with `global_market_intelligence.py` as a focused module that owns the US/global universe, cache loader, technical calculations, screeners, read-through rules, and report generation. Keep the first implementation additive and avoid refactoring existing NSE code until the US workflow proves useful.

**Tech Stack:** Python 3, pandas, numpy, optional yfinance, unittest, local CSV/JSON cache, existing `reports/` and `data/` folder conventions.

---

## File Structure

- Create `global_market_intelligence.py`: US/global universe, cache loader, technical engine, screeners, read-through, report CLI.
- Create `tests/test_global_market_intelligence.py`: deterministic unit tests using fixture DataFrames and fake fetchers.
- Modify `requirements.txt`: add `yfinance>=0.2.0` if not already present.
- Modify `docs/BACKLOG.md`: mark completed G items as each slice lands.
- Later modify `nse_agent.py`: terminal commands for `/us` and `/global readthrough`.
- Later modify `sector_rotation_report.py`: optional Global / US Context tab.

---

## Task 1: G1 US Universe + Cache Foundation

**Files:**
- Create: `global_market_intelligence.py`
- Create: `tests/test_global_market_intelligence.py`
- Modify: `requirements.txt`
- Modify: `docs/BACKLOG.md`

- [ ] **Step 1: Write failing tests**

Add tests that define the public API:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from global_market_intelligence import (
    DEFAULT_US_UNIVERSE,
    GlobalMarketDataLoader,
    cache_is_fresh,
    normalize_ohlcv,
    universe_records,
)


class GlobalMarketIntelligenceTests(unittest.TestCase):
    def test_default_universe_has_required_groups_and_benchmarks(self):
        records = universe_records(DEFAULT_US_UNIVERSE)
        symbols = {row["symbol"] for row in records}
        self.assertIn("SPY", symbols)
        self.assertIn("QQQ", symbols)
        self.assertIn("NVDA", symbols)
        for row in records:
            self.assertIn(row["asset_type"], {"index", "etf", "stock", "commodity", "currency", "rates_proxy"})
            self.assertTrue(row["benchmark"])

    def test_normalize_ohlcv_returns_standard_columns(self):
        raw = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-05-04", "2026-05-05"]),
                "Open": [100.0, 101.0],
                "High": [102.0, 103.0],
                "Low": [99.0, 100.0],
                "Close": [101.0, 102.0],
                "Volume": [1000, 1200],
            }
        )
        result = normalize_ohlcv("SPY", raw)
        self.assertEqual(list(result.columns), ["SYMBOL", "DATE", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME", "SOURCE"])
        self.assertEqual(result.loc[0, "SYMBOL"], "SPY")
        self.assertEqual(result.loc[0, "SOURCE"], "yfinance")

    def test_loader_fetches_writes_cache_and_latest_snapshot(self):
        def fake_fetch(symbols, lookback_days):
            return pd.DataFrame(
                {
                    "SYMBOL": ["SPY", "SPY", "QQQ"],
                    "DATE": pd.to_datetime(["2026-05-04", "2026-05-05", "2026-05-05"]),
                    "OPEN": [100.0, 101.0, 200.0],
                    "HIGH": [102.0, 103.0, 205.0],
                    "LOW": [99.0, 100.0, 198.0],
                    "CLOSE": [101.0, 102.0, 204.0],
                    "VOLUME": [1000, 1200, 1500],
                    "SOURCE": ["fake", "fake", "fake"],
                }
            )

        with TemporaryDirectory() as td:
            loader = GlobalMarketDataLoader(root_dir=Path(td), fetcher=fake_fetch)
            result = loader.load(symbols=["SPY", "QQQ"], force=True)
            self.assertEqual(result["status"], "ok")
            self.assertTrue((Path(td) / "prices.csv").exists())
            self.assertTrue((Path(td) / "latest_snapshot.csv").exists())
            self.assertEqual(len(result["prices"]), 3)

    def test_loader_uses_fresh_cache_without_fetching(self):
        calls = []

        def fake_fetch(symbols, lookback_days):
            calls.append(symbols)
            return pd.DataFrame(
                {
                    "SYMBOL": ["SPY"],
                    "DATE": pd.to_datetime(["2026-05-05"]),
                    "OPEN": [100.0],
                    "HIGH": [102.0],
                    "LOW": [99.0],
                    "CLOSE": [101.0],
                    "VOLUME": [1000],
                    "SOURCE": ["fake"],
                }
            )

        with TemporaryDirectory() as td:
            loader = GlobalMarketDataLoader(root_dir=Path(td), fetcher=fake_fetch)
            first = loader.load(symbols=["SPY"], force=True)
            second = loader.load(symbols=["SPY"], force=False)
            self.assertEqual(first["status"], "ok")
            self.assertEqual(second["status"], "ok")
            self.assertEqual(len(calls), 1)
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_global_market_intelligence -v
```

Expected: import failure because `global_market_intelligence.py` does not exist yet.

- [ ] **Step 3: Implement minimal G1 module**

Create `global_market_intelligence.py` with:

```python
DEFAULT_ROOT = Path("data") / "global_market"
PRICE_COLUMNS = ["SYMBOL", "DATE", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME", "SOURCE"]
DEFAULT_US_UNIVERSE = {...}
def universe_records(universe=DEFAULT_US_UNIVERSE) -> list[dict]: ...
def normalize_ohlcv(symbol: str, raw: pd.DataFrame, source: str = "yfinance") -> pd.DataFrame: ...
def cache_is_fresh(path: Path, ttl_hours: int = 24) -> bool: ...
class GlobalMarketDataLoader:
    def load(self, symbols=None, force=False, lookback_days=365) -> dict: ...
```

The loader must write:

- `prices.csv`
- `latest_snapshot.csv`
- `universe.json`

- [ ] **Step 4: Run tests and py_compile**

Run:

```bash
.venv/bin/python -m unittest tests.test_global_market_intelligence -v
.venv/bin/python -m py_compile global_market_intelligence.py tests/test_global_market_intelligence.py
```

Expected: all tests pass.

- [ ] **Step 5: Add dependency and backlog update**

Add `yfinance>=0.2.0` to `requirements.txt` under global market intelligence.

Update `docs/BACKLOG.md`:

- `G1 US Universe + yfinance Cache` from `READY` to `DONE`

- [ ] **Step 6: Commit**

```bash
git add global_market_intelligence.py tests/test_global_market_intelligence.py requirements.txt docs/BACKLOG.md
git commit -m "feat: add US global market data cache"
```

---

## Task 2: G2 Technical Engine

**Files:**
- Modify: `global_market_intelligence.py`
- Modify: `tests/test_global_market_intelligence.py`
- Modify: `docs/BACKLOG.md`

- [ ] **Step 1: Write failing tests for indicators**

Add fixture-price tests for `compute_technical_metrics(prices, benchmark_symbols=("SPY", "QQQ"))` covering:

- returns
- SMA 20/50/200
- RSI
- MACD state
- 52-week distance
- support/resistance
- RS vs SPY and QQQ
- Stage 2 compatibility

- [ ] **Step 2: Implement technical metrics**

Add focused helper functions:

```python
def _rsi(close: pd.Series, period: int = 14) -> pd.Series: ...
def _macd(close: pd.Series) -> pd.DataFrame: ...
def _support_resistance(hist: pd.DataFrame, window: int = 20) -> tuple[float | None, float | None]: ...
def compute_technical_metrics(prices: pd.DataFrame, benchmark_symbols=("SPY", "QQQ")) -> pd.DataFrame: ...
```

- [ ] **Step 3: Verify and commit**

Run tests and commit:

```bash
.venv/bin/python -m unittest tests.test_global_market_intelligence -v
git commit -m "feat: compute US global technical metrics"
```

---

## Task 3: G3 US Screeners

**Files:**
- Modify: `global_market_intelligence.py`
- Modify: `tests/test_global_market_intelligence.py`
- Modify: `docs/BACKLOG.md`

- [ ] **Step 1: Write failing tests for screeners**

Add tests for:

- `screen_stage2_leaders(metrics)`
- `screen_vcp_setups(metrics)`
- `rank_sector_rotation(metrics)`
- `build_risk_dashboard(metrics)`

- [ ] **Step 2: Implement screeners**

Keep outputs as DataFrames with stable column names and explicit empty DataFrames when unavailable.

- [ ] **Step 3: Verify and commit**

Run tests and commit:

```bash
.venv/bin/python -m unittest tests.test_global_market_intelligence -v
git commit -m "feat: add US global screeners"
```

---

## Task 4: G4 India Read-Through Engine

**Files:**
- Modify: `global_market_intelligence.py`
- Modify: `tests/test_global_market_intelligence.py`
- Modify: `docs/BACKLOG.md`

- [ ] **Step 1: Write failing tests for rule outputs**

Test that strong `QQQ` + `SMH` produces positive IT/electronics read-through, crude strength produces energy positive and aviation/paints risk, and VIX/credit weakness produces risk-off output.

- [ ] **Step 2: Implement `build_india_readthrough(metrics)`**

Return:

```python
{
  "global_regime": "risk-on|neutral|risk-off",
  "india_sector_implications": [...],
  "source_signals": [...]
}
```

- [ ] **Step 3: Verify and commit**

Run tests and commit:

```bash
.venv/bin/python -m unittest tests.test_global_market_intelligence -v
git commit -m "feat: add India read-through for US global signals"
```

---

## Task 5: G5 HTML Report

**Files:**
- Modify: `global_market_intelligence.py`
- Modify: `tests/test_global_market_intelligence.py`
- Modify: `docs/BACKLOG.md`

- [ ] **Step 1: Write failing report smoke test**

Assert generated HTML contains:

- Agent Adda heading
- US index tape
- sector ETF rotation
- screeners
- India read-through
- data freshness
- disclaimer

- [ ] **Step 2: Implement report rendering**

Add:

```python
def render_us_market_report(bundle: dict, output_dir: Path = Path("reports/global")) -> dict: ...
```

- [ ] **Step 3: Verify and commit**

Run tests and commit:

```bash
.venv/bin/python -m unittest tests.test_global_market_intelligence -v
git commit -m "feat: render US global market report"
```

---

## Task 6: G6 Terminal Integration

**Files:**
- Modify: `nse_agent.py`
- Create: `tests/test_nse_agent_global_us.py`
- Modify: `docs/BACKLOG.md`

- [ ] **Step 1: Write failing command-routing tests**

Test `/us`, `/us sectors`, `/us stock NVDA`, and `/global readthrough` mapping to deterministic helper functions.

- [ ] **Step 2: Implement terminal routing**

Add concise command handling that calls `global_market_intelligence` and prints terminal-friendly summaries plus report paths.

- [ ] **Step 3: Verify and commit**

Run:

```bash
.venv/bin/python -m unittest tests.test_nse_agent_global_us -v
git commit -m "feat: add US global terminal commands"
```

---

## Task 7: G7 Sector Report Global Tab

**Files:**
- Modify: `sector_rotation_report.py`
- Modify: `tests/test_sector_rotation_report.py`
- Modify: `docs/BACKLOG.md`

- [ ] **Step 1: Write failing HTML integration test**

Assert the sector rotation report includes a Global / US Context section when a global report bundle is available and still renders when it is unavailable.

- [ ] **Step 2: Implement optional report section**

Import defensively. If global data fails, show a short unavailable-data card and continue.

- [ ] **Step 3: Verify and commit**

Run:

```bash
.venv/bin/python -m unittest tests.test_sector_rotation_report -v
git commit -m "feat: add US global tab to sector report"
```

---

## Plan Self-Review

- Spec coverage: G1-G7 are covered; G8 is deferred as designed.
- No paid data sources are introduced.
- Tests are required before implementation in each task.
- Existing NSE report and terminal paths remain additive.
- Missing data is non-fatal in every task.
