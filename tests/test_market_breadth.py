import unittest

import pandas as pd

from market_breadth import (
    build_breadth_history,
    compute_mcclellan,
    compute_sector_breadth,
    compute_trin,
    detect_mcclellan_divergence,
    get_advance_decline_series,
    load_sector_breadth,
    mcclellan_context_html,
    sector_breadth_divergence,
)


class MarketBreadthTests(unittest.TestCase):
    def test_get_advance_decline_series_counts_daily_advancers_and_decliners(self):
        universe = pd.DataFrame(
            [
                {"SYMBOL": "AAA", "TIMESTAMP": "2026-01-01", "CLOSE": 100, "PREVCLOSE": 99},
                {"SYMBOL": "BBB", "TIMESTAMP": "2026-01-01", "CLOSE": 50, "PREVCLOSE": 51},
                {"SYMBOL": "CCC", "TIMESTAMP": "2026-01-01", "CLOSE": 20, "PREVCLOSE": 19},
                {"SYMBOL": "AAA", "TIMESTAMP": "2026-01-02", "CLOSE": 101, "PREVCLOSE": 100},
                {"SYMBOL": "BBB", "TIMESTAMP": "2026-01-02", "CLOSE": 49, "PREVCLOSE": 50},
                {"SYMBOL": "CCC", "TIMESTAMP": "2026-01-02", "CLOSE": 18, "PREVCLOSE": 20},
            ]
        )

        net_ad = get_advance_decline_series(universe)

        self.assertEqual(net_ad.loc[pd.Timestamp("2026-01-01")], 1)
        self.assertEqual(net_ad.loc[pd.Timestamp("2026-01-02")], -1)
        self.assertEqual(net_ad.name, "net_ad")

    def test_compute_mcclellan_marks_crosses_and_extremes(self):
        net_ad = pd.Series(
            [-500, -450, -400, -350, -300, 900, 950, 1000, 1050, 1100],
            index=pd.date_range("2026-01-01", periods=10),
            name="net_ad",
        )

        result = compute_mcclellan(net_ad)

        self.assertIn("oscillator", result.columns)
        self.assertIn("summation", result.columns)
        self.assertIn("signal", result.columns)
        self.assertIn("BULLISH_CROSS", set(result["signal"]))
        self.assertEqual(result["signal"].iloc[-1], "OVERBOUGHT")

    def test_detect_mcclellan_divergence_flags_bullish_higher_low(self):
        dates = pd.date_range("2026-01-01", periods=6)
        price = pd.Series([100, 96, 92, 95, 90, 93], index=dates, name="close")
        oscillator = pd.Series([-20, -55, -80, -45, -35, -25], index=dates, name="oscillator")

        signal = detect_mcclellan_divergence(price, oscillator, lookback=6)

        self.assertEqual(signal, "BULLISH_DIVERGENCE")

    def test_mcclellan_context_html_summarizes_latest_signal(self):
        history = pd.DataFrame(
            [
                {
                    "date": "2026-01-02",
                    "net_ad": 125,
                    "oscillator": 72.4,
                    "summation": 1300,
                    "signal": "OVERBOUGHT",
                    "divergence": "NONE",
                }
            ]
        )

        html = mcclellan_context_html(history)

        self.assertIn("McClellan", html)
        self.assertIn("OVERBOUGHT", html)
        self.assertIn("+72.4", html)

    def test_compute_trin_uses_advance_decline_and_volume_ratios(self):
        universe = pd.DataFrame(
            [
                {"SYMBOL": "AAA", "TIMESTAMP": "2026-01-01", "CLOSE": 110, "PREVCLOSE": 100, "TOTTRDQTY": 400},
                {"SYMBOL": "BBB", "TIMESTAMP": "2026-01-01", "CLOSE": 105, "PREVCLOSE": 100, "TOTTRDQTY": 300},
                {"SYMBOL": "CCC", "TIMESTAMP": "2026-01-01", "CLOSE": 95, "PREVCLOSE": 100, "TOTTRDQTY": 100},
                {"SYMBOL": "DDD", "TIMESTAMP": "2026-01-01", "CLOSE": 94, "PREVCLOSE": 100, "TOTTRDQTY": 100},
            ]
        )

        trin = compute_trin(universe)

        self.assertAlmostEqual(trin.loc[pd.Timestamp("2026-01-01"), "trin"], 0.29, places=2)
        self.assertEqual(trin.loc[pd.Timestamp("2026-01-01"), "trin_signal"], "VERY_BULLISH")

    def test_compute_trin_adds_rolling_5d_signal(self):
        rows = []
        for day in pd.date_range("2026-01-01", periods=5):
            rows.extend(
                [
                    {"SYMBOL": "AAA", "TIMESTAMP": day, "CLOSE": 110, "PREVCLOSE": 100, "TOTTRDQTY": 400},
                    {"SYMBOL": "BBB", "TIMESTAMP": day, "CLOSE": 105, "PREVCLOSE": 100, "TOTTRDQTY": 300},
                    {"SYMBOL": "CCC", "TIMESTAMP": day, "CLOSE": 95, "PREVCLOSE": 100, "TOTTRDQTY": 100},
                    {"SYMBOL": "DDD", "TIMESTAMP": day, "CLOSE": 94, "PREVCLOSE": 100, "TOTTRDQTY": 100},
                ]
            )

        trin = compute_trin(pd.DataFrame(rows))

        self.assertAlmostEqual(trin["trin_5d"].iloc[-1], 0.29, places=2)
        self.assertEqual(trin["trin_5d_signal"].iloc[-1], "INTERNALLY_STRONG")

    def test_build_breadth_history_includes_trin_columns(self):
        rows = []
        for day in pd.date_range("2026-01-01", periods=6):
            rows.extend(
                [
                    {"SYMBOL": "AAA", "TIMESTAMP": day, "CLOSE": 110, "PREVCLOSE": 100, "TOTTRDQTY": 400},
                    {"SYMBOL": "BBB", "TIMESTAMP": day, "CLOSE": 95, "PREVCLOSE": 100, "TOTTRDQTY": 100},
                ]
            )

        history = build_breadth_history(pd.DataFrame(rows))

        self.assertIn("trin", history.columns)
        self.assertIn("trin_5d", history.columns)
        self.assertIn("trin_signal", history.columns)


# ---------------------------------------------------------------------------
# C3: Sector Breadth Divergence tests
# ---------------------------------------------------------------------------

class SectorBreadthTests(unittest.TestCase):
    def _make_stock_metrics(self, stocks: list[dict]) -> pd.DataFrame:
        """Helper: build a minimal stock_metrics DataFrame for compute_sector_breadth."""
        return pd.DataFrame([
            {"SYMBOL": s["sym"], "CLOSE": s["close"], "SMA_50": s["sma50"], "SMA_200": s.get("sma200", s["sma50"])}
            for s in stocks
        ])

    def test_compute_sector_breadth_classifies_signals(self):
        """Verify HEALTHY/NEUTRAL/WEAK thresholds from pct_above_50dma."""
        stocks = [
            # 4 of 5 above SMA_50 → 80% → HEALTHY
            {"sym": "AA", "close": 110, "sma50": 100},
            {"sym": "AB", "close": 110, "sma50": 100},
            {"sym": "AC", "close": 110, "sma50": 100},
            {"sym": "AD", "close": 110, "sma50": 100},
            {"sym": "AE", "close": 90,  "sma50": 100},
        ]
        metrics = self._make_stock_metrics(stocks)
        constituents = {"NIFTY AUTO": ["AA", "AB", "AC", "AD", "AE"]}
        sector_indices = {"NIFTY AUTO": "Auto"}

        result = compute_sector_breadth(metrics, constituents, sector_indices=sector_indices)

        self.assertEqual(len(result), 1)
        row = result.iloc[0]
        self.assertAlmostEqual(row["pct_above_50dma"], 80.0, places=1)
        self.assertEqual(row["breadth_signal"], "HEALTHY")

    def test_compute_sector_breadth_neutral_signal(self):
        """50% above SMA_50 → NEUTRAL."""
        stocks = [
            {"sym": "BA", "close": 110, "sma50": 100},
            {"sym": "BB", "close": 110, "sma50": 100},
            {"sym": "BC", "close": 90,  "sma50": 100},
            {"sym": "BD", "close": 90,  "sma50": 100},
        ]
        metrics = self._make_stock_metrics(stocks)
        constituents = {"NIFTY BANK": ["BA", "BB", "BC", "BD"]}
        sector_indices = {"NIFTY BANK": "Banking"}

        result = compute_sector_breadth(metrics, constituents, sector_indices=sector_indices)

        self.assertEqual(result.iloc[0]["breadth_signal"], "NEUTRAL")

    def test_compute_sector_breadth_weak_signal(self):
        """1 of 5 above SMA_50 → 20% → WEAK."""
        stocks = [
            {"sym": "CA", "close": 110, "sma50": 100},
            {"sym": "CB", "close": 80,  "sma50": 100},
            {"sym": "CC", "close": 80,  "sma50": 100},
            {"sym": "CD", "close": 80,  "sma50": 100},
            {"sym": "CE", "close": 80,  "sma50": 100},
        ]
        metrics = self._make_stock_metrics(stocks)
        constituents = {"NIFTY IT": ["CA", "CB", "CC", "CD", "CE"]}
        sector_indices = {"NIFTY IT": "IT"}

        result = compute_sector_breadth(metrics, constituents, sector_indices=sector_indices)

        self.assertEqual(result.iloc[0]["breadth_signal"], "WEAK")

    def test_compute_sector_breadth_no_data_for_missing_constituents(self):
        """Index with no matching symbols gets NO_DATA signal."""
        metrics = self._make_stock_metrics([{"sym": "ZZ", "close": 100, "sma50": 90}])
        constituents = {"NIFTY METAL": ["AA", "AB", "AC"]}  # none in metrics
        sector_indices = {"NIFTY METAL": "Metal"}

        result = compute_sector_breadth(metrics, constituents, sector_indices=sector_indices)

        self.assertEqual(result.iloc[0]["breadth_signal"], "NO_DATA")

    def _make_divergence_stock_data(self, n_days: int = 10) -> pd.DataFrame:
        """Build multi-date stock data for sector_breadth_divergence tests."""
        dates = pd.date_range("2026-01-01", periods=n_days)
        rows = []
        for i, d in enumerate(dates):
            # Stock prices: first half below SMA_50, second half above
            close = 90 if i < 5 else 110
            rows.append({"SYMBOL": "S1", "TIMESTAMP": d, "CLOSE": close, "PREVCLOSE": close - 2})
            rows.append({"SYMBOL": "S2", "TIMESTAMP": d, "CLOSE": close, "PREVCLOSE": close - 2})
            rows.append({"SYMBOL": "S3", "TIMESTAMP": d, "CLOSE": close, "PREVCLOSE": close - 2})
        return pd.DataFrame(rows)

    def test_sector_breadth_divergence_detects_bullish_div(self):
        """Price down + breadth improved → BULLISH_DIV.

        Stock closes are 80 for days 1-55 (below rolling SMA50=80, so pct50=0%),
        then jump to 130 for days 56-60 (above SMA50≈85, pct50=100%).
        Sector index falls 4% over the lookback window → BULLISH_DIV.
        """
        dates = pd.date_range("2026-01-01", periods=60)
        stock_rows = []
        index_rows = []
        for i, d in enumerate(dates):
            close = 80 if i < 55 else 130
            for sym in ["S1", "S2", "S3", "S4", "S5"]:
                stock_rows.append({"SYMBOL": sym, "TIMESTAMP": d, "CLOSE": close})
            # Index dips over final 5 days: 1000 → 960
            idx_close = 1000 if i < 55 else 1000 - (i - 54) * 8
            index_rows.append({"SYMBOL": "NIFTY METAL", "TIMESTAMP": d, "CLOSE": idx_close})

        stock_data = pd.DataFrame(stock_rows)
        index_data = pd.DataFrame(index_rows)
        constituents = {"NIFTY METAL": ["S1", "S2", "S3", "S4", "S5"]}

        result = sector_breadth_divergence(
            stock_data, index_data=index_data,
            constituents=constituents,
            sector_indices={"NIFTY METAL": "Metal"},
            lookback_days=5,
        )

        self.assertFalse(result.empty)
        self.assertEqual(result.iloc[0]["divergence_alert"], "BULLISH_DIV")

    def test_sector_breadth_divergence_detects_int_weakness(self):
        """Flat index price + breadth drops >10pp → INT_WEAKNESS.

        Stocks rise from 100 to 150 over days 1-55 (pct50=100%), then plunge
        to 80 on days 56-60 (below SMA50≈120, pct50=0%).
        Sector index held flat → INT_WEAKNESS triggered.
        """
        dates = pd.date_range("2026-01-01", periods=60)
        stock_rows = []
        index_rows = []
        for i, d in enumerate(dates):
            close = 100 + i if i < 55 else 80
            for sym in ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10"]:
                stock_rows.append({"SYMBOL": sym, "TIMESTAMP": d, "CLOSE": close})
            index_rows.append({"SYMBOL": "NIFTY METAL", "TIMESTAMP": d, "CLOSE": 1000.0})

        stock_data = pd.DataFrame(stock_rows)
        index_data = pd.DataFrame(index_rows)
        constituents = {"NIFTY METAL": ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10"]}

        result = sector_breadth_divergence(
            stock_data, index_data=index_data,
            constituents=constituents,
            sector_indices={"NIFTY METAL": "Metal"},
            lookback_days=5,
        )

        self.assertFalse(result.empty)
        self.assertEqual(result.iloc[0]["divergence_alert"], "INT_WEAKNESS")

    def test_load_sector_breadth_returns_empty_on_missing_file(self):
        """load_sector_breadth returns empty DataFrame when CSV file is absent."""
        from pathlib import Path
        missing = Path("/tmp/definitely_does_not_exist_sector_breadth.csv")
        result = load_sector_breadth(missing)
        self.assertIsInstance(result, pd.DataFrame)
        self.assertTrue(result.empty)


if __name__ == "__main__":
    unittest.main()
