# Sector Rotation Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable Option B report generator for currently rotating NSE sectors, with sector ranking, stock shortlist, technical pattern diagnostics, and Markdown/HTML outputs.

**Architecture:** Add one focused Python module at `sector_rotation_report.py` with pure calculation functions plus a CLI. Unit tests cover sector rotation scoring, Supertrend direction, consolidation breakout classification, and candidate ranking. The CLI reads existing local outputs (`reports/comprehensive_nse_enhanced_*.csv`, `data/nse_index_data.csv`) and exports the R stock cache to a temporary CSV for historical OHLC-based pattern calculations.

**Tech Stack:** Python 3, pandas, numpy, pytest-style tests using stdlib `unittest`, optional Rscript for `data/nse_stock_cache.RData` export.

---

### Task 1: Calculation Tests

**Files:**
- Create: `tests/test_sector_rotation_report.py`
- Create: `sector_rotation_report.py`

- [ ] **Step 1: Write failing tests**

```python
import unittest
import pandas as pd

from sector_rotation_report import (
    compute_supertrend,
    classify_consolidation_breakout,
    rank_rotating_sectors,
    rank_stock_candidates,
)


class SectorRotationReportTests(unittest.TestCase):
    def test_rank_rotating_sectors_prefers_relative_strength_and_positive_short_term_returns(self):
        index_metrics = pd.DataFrame(
            [
                {"SYMBOL": "Nifty Defence", "RET_5D": 2.0, "RET_1M": 20.0, "RET_3M": 15.0, "RET_6M": 10.0},
                {"SYMBOL": "Nifty IT", "RET_5D": -5.0, "RET_1M": -2.0, "RET_3M": -20.0, "RET_6M": -18.0},
                {"SYMBOL": "Nifty 500", "RET_5D": -1.0, "RET_1M": 8.0, "RET_3M": 0.0, "RET_6M": -4.0},
            ]
        )

        ranked = rank_rotating_sectors(index_metrics, benchmark_symbol="Nifty 500")

        self.assertEqual(ranked.iloc[0]["SYMBOL"], "Nifty Defence")
        self.assertGreater(ranked.iloc[0]["ROTATION_SCORE"], ranked.iloc[-1]["ROTATION_SCORE"])
        self.assertAlmostEqual(ranked.iloc[0]["RS_1M"], 12.0)

    def test_compute_supertrend_marks_persistent_uptrend_as_bullish(self):
        prices = pd.DataFrame(
            {
                "HIGH": [10, 11, 12, 13, 14, 15, 16, 17],
                "LOW": [9, 10, 11, 12, 13, 14, 15, 16],
                "CLOSE": [9.5, 10.8, 11.7, 12.8, 13.6, 14.7, 15.8, 16.7],
            }
        )

        result = compute_supertrend(prices, period=3, multiplier=1.5)

        self.assertEqual(result["SUPERTREND_DIRECTION"].iloc[-1], 1)
        self.assertEqual(result["SUPERTREND_STATE"].iloc[-1], "BULLISH")

    def test_classify_consolidation_breakout_identifies_volume_breakout(self):
        history = pd.DataFrame(
            {
                "HIGH": [100, 101, 100.5, 101.2, 101, 102.5],
                "LOW": [98, 98.5, 98.2, 98.7, 98.6, 100.8],
                "CLOSE": [99, 100, 99.8, 100.5, 100.1, 102.2],
                "TOTTRDQTY": [1000, 1050, 950, 980, 1020, 2600],
            }
        )

        pattern = classify_consolidation_breakout(history, lookback=5, width_threshold=0.05, volume_multiplier=1.5)

        self.assertTrue(pattern["IS_CONSOLIDATION_BREAKOUT"])
        self.assertEqual(pattern["PATTERN"], "CONSOLIDATION_BREAKOUT")

    def test_rank_stock_candidates_blends_technical_rs_fundamental_and_pattern(self):
        stocks = pd.DataFrame(
            [
                {
                    "SYMBOL": "AAA",
                    "SECTOR_NAME": "Defence",
                    "TECHNICAL_SCORE": 80,
                    "RELATIVE_STRENGTH": 30,
                    "ENHANCED_FUND_SCORE": 70,
                    "TRADING_SIGNAL": "BUY",
                    "PATTERN": "CONSOLIDATION_BREAKOUT",
                    "SUPERTREND_STATE": "BULLISH",
                },
                {
                    "SYMBOL": "BBB",
                    "SECTOR_NAME": "Defence",
                    "TECHNICAL_SCORE": 60,
                    "RELATIVE_STRENGTH": 5,
                    "ENHANCED_FUND_SCORE": 80,
                    "TRADING_SIGNAL": "HOLD",
                    "PATTERN": "BASE_BUILDING",
                    "SUPERTREND_STATE": "BEARISH",
                },
            ]
        )

        ranked = rank_stock_candidates(stocks)

        self.assertEqual(ranked.iloc[0]["SYMBOL"], "AAA")
        self.assertGreater(ranked.iloc[0]["INVESTMENT_SCORE"], ranked.iloc[1]["INVESTMENT_SCORE"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests/test_sector_rotation_report.py -v`

Expected: import failure because `sector_rotation_report.py` does not exist yet.

### Task 2: Minimal Calculation Module

**Files:**
- Modify: `sector_rotation_report.py`
- Test: `tests/test_sector_rotation_report.py`

- [ ] **Step 1: Implement pure functions**

Implement `rank_rotating_sectors`, `compute_supertrend`, `classify_consolidation_breakout`, and `rank_stock_candidates` with deterministic pandas logic.

- [ ] **Step 2: Run unit tests**

Run: `python3 -m unittest tests/test_sector_rotation_report.py -v`

Expected: all tests pass.

### Task 3: CLI Report Generator

**Files:**
- Modify: `sector_rotation_report.py`

- [ ] **Step 1: Add CLI functions**

Add file discovery, optional RData export, sector mapping, pattern enrichment, Markdown rendering, HTML rendering, and a `main()` entry point.

- [ ] **Step 2: Run report generator**

Run: `python3 sector_rotation_report.py`

Expected: writes timestamped Markdown and HTML report under `reports/`.

### Task 4: Verification

**Files:**
- Read generated files only.

- [ ] **Step 1: Run unit tests again**

Run: `python3 -m unittest tests/test_sector_rotation_report.py -v`

Expected: all tests pass.

- [ ] **Step 2: Confirm generated report contains required sections**

Run: `rg -n "Sector Rotation|Supertrend|Consolidation|Relative Strength|Investment Candidates" reports/Sector_Rotation_Report_*.md`

Expected: all required headings are present in the latest report.
