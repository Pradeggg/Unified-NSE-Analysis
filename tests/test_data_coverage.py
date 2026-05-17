"""Tests for /data-coverage terminal handler."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from terminal.data_coverage import (
    _canonical_index,
    _classify,
    _format_summary,
    handle_data_coverage_command,
)
from data_pipeline.equity_eod_backfill import SymbolCoverage


class TestDataCoverageHelpers(unittest.TestCase):
    def test_canonical_index_resolves_aliases(self):
        self.assertEqual(_canonical_index("nifty500"), "NIFTY 500")
        self.assertEqual(_canonical_index("NIFTY50"), "NIFTY 50")
        self.assertEqual(_canonical_index("nifty-midcap-150"), "NIFTY MIDCAP 150")
        self.assertEqual(_canonical_index("NIFTY 500"), "NIFTY 500")

    def test_classify_buckets_symbols(self):
        coverage = [
            SymbolCoverage("OK1", None, None, 1500),
            SymbolCoverage("SHORT1", None, None, 500),
            SymbolCoverage("MISSING", None, None, 0),
        ]
        buckets = _classify(coverage, min_bars=1200)
        self.assertEqual([c.symbol for c in buckets["ok"]], ["OK1"])
        self.assertEqual([c.symbol for c in buckets["short"]], ["SHORT1"])
        self.assertEqual([c.symbol for c in buckets["missing"]], ["MISSING"])

    def test_format_summary_includes_key_fields(self):
        coverage = [
            SymbolCoverage("OK1", None, None, 1500),
            SymbolCoverage("SHORT1", None, None, 500),
        ]
        out = _format_summary(
            index_name="NIFTY500",
            min_years=5,
            min_bars=1200,
            coverage=coverage,
            backfill_stats=None,
            details=False,
        )
        self.assertIn("NIFTY500", out)
        self.assertIn("Universe:** 2", out)
        self.assertIn("Fully covered:** 1", out)
        self.assertIn("Undercovered:** 1", out)


class TestDataCoverageHandler(unittest.TestCase):
    def test_handle_rejects_missing_index(self):
        out = handle_data_coverage_command("/data-coverage")
        self.assertIn("Data Coverage failed", out)
        self.assertIn("Usage:", out)

    def test_handle_audit_with_mocked_db(self):
        fake_coverage = [
            SymbolCoverage("DMART", None, None, 1500),
            SymbolCoverage("RELIANCE", None, None, 1500),
            SymbolCoverage("SWIGGY", None, None, 300),
        ]
        with patch(
            "terminal.data_coverage._load_index_symbols",
            return_value=["DMART", "RELIANCE", "SWIGGY"],
        ), patch(
            "terminal.data_coverage.coverage_for_symbols",
            return_value=fake_coverage,
        ), patch("terminal.data_coverage.psycopg2", create=True), patch(
            "psycopg2.connect"
        ):
            out = handle_data_coverage_command("/data-coverage NIFTY500")
        self.assertIn("Data Coverage — NIFTY500", out)
        self.assertIn("Universe:** 3", out)
        self.assertIn("Fully covered:** 2", out)
        self.assertIn("Undercovered:** 1", out)


if __name__ == "__main__":
    unittest.main()
