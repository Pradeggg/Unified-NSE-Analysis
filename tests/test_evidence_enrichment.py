"""Tests for backtesting.strategy_council.evidence_enrichment."""

from __future__ import annotations

import pandas as pd
import pytest

from backtesting.strategy_council.evidence_enrichment import (
    REGIME_BEAR,
    REGIME_BULL,
    REGIME_SIDEWAYS,
    compute_factor_exposure,
    compute_microstructure,
    detect_regime,
    enrich_with_market_signals,
)
from backtesting.strategy_council.types import EvidencePack


def _bull_frame(n: int = 260) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2023-01-01", periods=n, freq="B"),
            "symbol": ["X"] * n,
            "open": [100 + i * 0.5 for i in range(n)],
            "high": [101 + i * 0.5 for i in range(n)],
            "low": [99 + i * 0.5 for i in range(n)],
            "close": [100 + i * 0.5 for i in range(n)],
            "volume": [1000 + i for i in range(n)],
        }
    )


def _bear_frame(n: int = 260) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2023-01-01", periods=n, freq="B"),
            "symbol": ["X"] * n,
            "open": [200 - i * 0.5 for i in range(n)],
            "high": [201 - i * 0.5 for i in range(n)],
            "low": [199 - i * 0.5 for i in range(n)],
            "close": [200 - i * 0.5 for i in range(n)],
            "volume": [1000] * n,
        }
    )


def _sideways_frame(n: int = 260) -> pd.DataFrame:
    closes = [100 + (i % 4) * 0.1 for i in range(n)]
    return pd.DataFrame(
        {
            "date": pd.date_range("2023-01-01", periods=n, freq="B"),
            "symbol": ["X"] * n,
            "open": closes,
            "high": [c + 0.5 for c in closes],
            "low": [c - 0.5 for c in closes],
            "close": closes,
            "volume": [1000] * n,
        }
    )


class TestDetectRegime:
    def test_bull_regime(self):
        result = detect_regime(_bull_frame())
        assert result["available"] is True
        assert result["regime"] == REGIME_BULL
        assert result["slope"] > 0

    def test_bear_regime(self):
        result = detect_regime(_bear_frame())
        assert result["available"] is True
        assert result["regime"] == REGIME_BEAR

    def test_sideways_regime(self):
        result = detect_regime(_sideways_frame())
        assert result["available"] is True
        assert result["regime"] == REGIME_SIDEWAYS

    def test_short_history_uses_available_bars(self):
        result = detect_regime(_bull_frame(n=50))
        assert result.get("bars_used") == 50
        # With 50 bars all rising, regime should still classify as bull
        assert result["regime"] == REGIME_BULL

    def test_empty_frame_returns_unavailable(self):
        result = detect_regime(pd.DataFrame())
        assert result["available"] is False


class TestFactorExposure:
    def test_no_benchmark_returns_unavailable(self):
        result = compute_factor_exposure(_bull_frame())
        assert result["available"] is False
        assert result["reason"] == "no_benchmark_series"

    def test_correlated_benchmark_yields_high_beta(self):
        df = _bull_frame()
        # Benchmark moves in lockstep with the symbol; beta should be ~1
        benchmark = df["close"].copy()
        result = compute_factor_exposure(df, benchmark=benchmark)
        assert result["available"] is True
        assert abs(result["beta"] - 1.0) < 0.1
        assert abs(result["correlation"]) > 0.95

    def test_insufficient_overlap(self):
        df = _bull_frame(n=10)
        benchmark = df["close"].copy()
        result = compute_factor_exposure(df, benchmark=benchmark)
        assert result["available"] is False


class TestMicrostructure:
    def test_basic_metrics(self):
        df = _bull_frame()
        result = compute_microstructure(df)
        assert result["available"] is True
        assert "atr_pct" in result
        assert "avg_hl_spread_pct" in result
        assert "avg_dollar_volume_30d" in result
        assert result["atr_pct"] > 0

    def test_empty_returns_unavailable(self):
        result = compute_microstructure(pd.DataFrame())
        assert result["available"] is False


class TestEnrichWithMarketSignals:
    def test_attaches_all_three_groups(self):
        pack = EvidencePack(symbol="X", as_of="2024-01-01")
        df = _bull_frame()
        enrich_with_market_signals(pack, df, benchmark=df["close"].copy())
        assert pack.market["regime"]["regime"] == REGIME_BULL
        assert pack.market["factor_exposure"]["available"] is True
        assert pack.market["microstructure"]["available"] is True
        # Source trail mentions each enrichment
        joined = " ".join(pack.source_trail)
        assert "regime" in joined
        assert "factor_exposure" in joined
        assert "microstructure" in joined

    def test_records_missing_when_benchmark_absent(self):
        pack = EvidencePack(symbol="X", as_of="2024-01-01")
        df = _bull_frame()
        enrich_with_market_signals(pack, df, benchmark=None)
        assert "factor_exposure" in pack.missing

    def test_does_not_raise_on_empty_eod(self):
        pack = EvidencePack(symbol="X", as_of="2024-01-01")
        enrich_with_market_signals(pack, pd.DataFrame())
        # all three should be marked missing without raising
        assert "regime" in pack.missing
        assert "factor_exposure" in pack.missing
        assert "microstructure" in pack.missing


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
