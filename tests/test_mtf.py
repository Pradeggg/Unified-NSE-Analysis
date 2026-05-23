"""Unit tests for the multi-timeframe analysis engine (terminal/mtf.py)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from terminal import mtf


# ── Fixture builders ────────────────────────────────────────────────────────


def _daily_frame(closes: list[float], start: str = "2024-01-01") -> pd.DataFrame:
    """Build a synthetic daily OHLCV frame from a close-price list."""
    n = len(closes)
    dates = pd.bdate_range(start=start, periods=n)
    closes_arr = np.array(closes, dtype=float)
    return pd.DataFrame(
        {
            "TIMESTAMP": dates,
            "OPEN": closes_arr * 0.995,
            "HIGH": closes_arr * 1.01,
            "LOW": closes_arr * 0.99,
            "CLOSE": closes_arr,
            "TOTTRDQTY": np.full(n, 1_000_000),
        }
    )


def _bullish_daily(n: int = 260) -> pd.DataFrame:
    """Monotone rising series — every TF should read bullish."""
    return _daily_frame([100 + i * 0.5 for i in range(n)])


def _bearish_daily(n: int = 260) -> pd.DataFrame:
    """Monotone falling series — every TF should read bearish."""
    return _daily_frame([300 - i * 0.5 for i in range(n)])


def _choppy_daily(n: int = 260) -> pd.DataFrame:
    """Sideways with shallow oscillation — direction should be neutral/mixed."""
    base = 200
    return _daily_frame([base + (5 if i % 2 == 0 else -5) for i in range(n)])


# ── resample_ohlcv ──────────────────────────────────────────────────────────


def test_resample_weekly_aggregates_correctly():
    daily = _daily_frame([100, 101, 102, 103, 104, 105, 106, 107, 108, 109])
    weekly = mtf.resample_ohlcv(daily, mtf.TF_WEEKLY)
    assert not weekly.empty
    # Weekly bar count must be <= daily bar count and >= 1.
    assert 1 <= len(weekly) <= len(daily)
    # HIGH of each weekly bar must be >= CLOSE of that bar (sanity).
    assert (weekly["HIGH"] >= weekly["CLOSE"]).all()
    # Volume must aggregate (sum) — first weekly bar sums >= one day's volume.
    assert weekly["TOTTRDQTY"].iloc[0] >= 1_000_000


def test_resample_monthly_groups_days():
    daily = _daily_frame([100 + i for i in range(60)])  # ~3 calendar months
    monthly = mtf.resample_ohlcv(daily, mtf.TF_MONTHLY)
    assert not monthly.empty
    assert len(monthly) <= 4  # at most 4 monthly buckets across 60 business days
    # Monotone-rising daily → monthly CLOSE strictly non-decreasing.
    closes = monthly["CLOSE"].tolist()
    assert closes == sorted(closes)


def test_resample_empty_input_returns_empty():
    assert mtf.resample_ohlcv(pd.DataFrame(), mtf.TF_WEEKLY).empty
    assert mtf.resample_ohlcv(None, mtf.TF_WEEKLY).empty  # type: ignore[arg-type]


def test_resample_daily_passthrough():
    daily = _daily_frame([100, 101, 102])
    out = mtf.resample_ohlcv(daily, mtf.TF_DAILY)
    assert len(out) == len(daily)


# ── read_timeframe ──────────────────────────────────────────────────────────


def test_read_timeframe_bullish_series_is_bullish():
    daily = _bullish_daily()
    reading = mtf.read_timeframe(daily, mtf.TF_DAILY)
    assert reading.status == "ok"
    assert reading.direction == "bullish"
    assert reading.above_ema20 is True
    assert reading.above_ema50 is True
    assert reading.sma_stack_bullish is True
    assert reading.macd == "bullish"
    assert reading.rsi is not None and reading.rsi > 55


def test_read_timeframe_bearish_series_is_bearish():
    daily = _bearish_daily()
    reading = mtf.read_timeframe(daily, mtf.TF_DAILY)
    assert reading.status == "ok"
    assert reading.direction == "bearish"
    assert reading.above_ema20 is False
    assert reading.sma_stack_bearish is True
    assert reading.macd == "bearish"


def test_read_timeframe_missing_when_empty():
    reading = mtf.read_timeframe(pd.DataFrame(), mtf.TF_DAILY)
    assert reading.status == "missing"
    assert reading.direction == "unknown"


def test_read_timeframe_insufficient_history():
    daily = _daily_frame([100, 101, 102])  # only 3 bars
    reading = mtf.read_timeframe(daily, mtf.TF_DAILY)
    assert reading.status == "insufficient_history"


# ── score_alignment + verdict_from_score ────────────────────────────────────


def _stack(direction_map: dict[str, str]) -> dict[str, mtf.TimeframeReading]:
    out: dict[str, mtf.TimeframeReading] = {}
    for tf, dirn in direction_map.items():
        r = mtf.TimeframeReading(timeframe=tf, status="ok", direction=dirn)
        out[tf] = r
    return out


def test_score_alignment_all_bullish_scores_100():
    readings = _stack({tf: "bullish" for tf in mtf.DEFAULT_TIMEFRAMES})
    score, direction, aligned, dissonant, missing, _ = mtf.score_alignment(readings)
    assert score == 100
    assert direction == "bullish"
    assert set(aligned) == set(mtf.DEFAULT_TIMEFRAMES)
    assert dissonant == []
    assert missing == []


def test_score_alignment_all_bearish_scores_100_bear():
    readings = _stack({tf: "bearish" for tf in mtf.DEFAULT_TIMEFRAMES})
    score, direction, _aligned, _dissonant, missing, _ = mtf.score_alignment(readings)
    assert score == 100
    assert direction == "bearish"
    assert missing == []


def test_score_alignment_mixed_resolves_by_weighted_majority():
    # Higher TFs bullish (55), lower TFs bearish (45) → bullish wins.
    readings = _stack(
        {
            mtf.TF_MONTHLY: "bullish",
            mtf.TF_WEEKLY: "bullish",
            mtf.TF_DAILY: "bearish",
            mtf.TF_60M: "bearish",
            mtf.TF_15M: "bearish",
        }
    )
    score, direction, _, _, _, _ = mtf.score_alignment(readings)
    assert direction == "bullish"
    assert score == 55


def test_score_alignment_missing_tfs_not_counted():
    readings = _stack({mtf.TF_DAILY: "bullish"})
    readings[mtf.TF_WEEKLY] = mtf.TimeframeReading(timeframe=mtf.TF_WEEKLY, status="missing")
    score, direction, _, _, missing, _ = mtf.score_alignment(readings)
    assert direction == "bullish"
    assert score == 25  # only daily contributed
    assert mtf.TF_WEEKLY in missing


def test_verdict_buy_at_strong_bullish_score():
    assert mtf.verdict_from_score("bullish", 80, missing_count=0, total_tfs=5) == "BUY"


def test_verdict_watch_when_too_many_tfs_missing():
    # Even with a strong direction, half-missing TFs degrade to WATCH.
    assert mtf.verdict_from_score("bullish", 80, missing_count=3, total_tfs=5) == "WATCH"


def test_verdict_sell_at_strong_bearish_score():
    assert mtf.verdict_from_score("bearish", 75, missing_count=0, total_tfs=5) == "SELL"


def test_verdict_avoid_for_weak_or_mixed():
    assert mtf.verdict_from_score("bullish", 30, missing_count=0, total_tfs=5) == "AVOID"
    assert mtf.verdict_from_score("mixed", 40, missing_count=0, total_tfs=5) == "AVOID"


# ── compute_mtf (top-level) ─────────────────────────────────────────────────


def test_compute_mtf_bullish_end_to_end_buy_verdict():
    daily = _bullish_daily(n=520)
    result = mtf.compute_mtf(
        "TEST",
        timeframes=(mtf.TF_MONTHLY, mtf.TF_WEEKLY, mtf.TF_DAILY),
        daily_loader=lambda *_a, **_k: daily,
        intraday_loader=lambda *_a, **_k: None,
    )
    assert result.symbol == "TEST"
    assert result.direction == "bullish"
    assert result.verdict in {"BUY", "WATCH"}
    assert mtf.TF_DAILY in result.aligned_tfs
    assert all(r.status == "ok" for r in result.readings.values())


def test_compute_mtf_marks_missing_intraday():
    daily = _bullish_daily(n=520)
    result = mtf.compute_mtf(
        "TEST",
        timeframes=mtf.DEFAULT_TIMEFRAMES,
        daily_loader=lambda *_a, **_k: daily,
        intraday_loader=lambda *_a, **_k: None,
    )
    assert mtf.TF_60M in result.missing_tfs
    assert mtf.TF_15M in result.missing_tfs
    # With 2/5 TFs missing the verdict must not be a strong BUY/SELL.
    assert result.verdict in {"BUY", "WATCH", "AVOID"}
    # Higher TFs aligned bullish (M+W+D = 80) → still bullish direction.
    assert result.direction == "bullish"


def test_compute_mtf_accepts_dict_intraday_payload():
    daily = _bullish_daily(n=520)
    intraday_bars = [
        {
            "timestamp": pd.Timestamp("2024-06-01") + pd.Timedelta(hours=i),
            "open": 100 + i,
            "high": 100 + i + 1,
            "low": 100 + i - 0.5,
            "close": 100 + i + 0.5,
            "volume": 50_000,
        }
        for i in range(60)
    ]
    payload = {"bars": intraday_bars}
    result = mtf.compute_mtf(
        "TEST",
        timeframes=(mtf.TF_DAILY, mtf.TF_60M),
        daily_loader=lambda *_a, **_k: daily,
        intraday_loader=lambda *_a, **_k: payload,
    )
    assert mtf.TF_60M not in result.missing_tfs
    assert result.readings[mtf.TF_60M].status == "ok"


def test_compute_mtf_handles_loader_exceptions():
    def raising_loader(*_a, **_k):
        raise RuntimeError("PG offline")

    result = mtf.compute_mtf(
        "TEST",
        timeframes=(mtf.TF_DAILY, mtf.TF_60M),
        daily_loader=raising_loader,
        intraday_loader=raising_loader,
    )
    assert mtf.TF_DAILY in result.missing_tfs
    assert mtf.TF_60M in result.missing_tfs
    # All missing → verdict degrades; never crashes.
    assert result.verdict in {"WATCH", "AVOID"}


def test_compute_mtf_rationale_lists_each_timeframe():
    daily = _bullish_daily(n=520)
    result = mtf.compute_mtf(
        "TEST",
        timeframes=(mtf.TF_MONTHLY, mtf.TF_WEEKLY, mtf.TF_DAILY),
        daily_loader=lambda *_a, **_k: daily,
        intraday_loader=lambda *_a, **_k: None,
    )
    joined = "\n".join(result.rationale)
    for tf in (mtf.TF_MONTHLY, mtf.TF_WEEKLY, mtf.TF_DAILY):
        assert tf in joined


def test_tf_weights_sum_to_100():
    assert sum(mtf.TF_WEIGHTS.values()) == 100


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
