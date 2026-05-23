from terminal.visual_scan.models import (
    ChartAnnotation,
    PatternEvidence,
    PatternStatus,
    VisualScanPack,
    VisualScanVerdict,
    Zones,
)


def test_pattern_evidence_serializes_with_status_confidence_and_zones():
    evidence = PatternEvidence(
        pattern="VCP",
        status=PatternStatus.CANDIDATE,
        confidence=0.72,
        evidence=["range contracted from 12% to 5%"],
        zones=Zones(pivot=4210.0, support=3890.0, invalidation=3740.0, target_1=4550.0),
        caveats=["breakout volume not confirmed"],
    )

    payload = evidence.to_dict()

    assert payload["pattern"] == "VCP"
    assert payload["status"] == "candidate"
    assert payload["confidence"] == 0.72
    assert payload["zones"]["pivot"] == 4210.0
    assert payload["caveats"] == ["breakout volume not confirmed"]


def test_visual_scan_pack_tracks_missing_evidence_and_annotations():
    pack = VisualScanPack(
        run_id="run-1",
        symbol="DMART",
        as_of="2026-05-22",
        verdict=VisualScanVerdict(
            stance="Watchlist / base building",
            score=68.0,
            confidence="medium",
            trigger="Daily close above pivot with volume confirmation.",
            invalidation="Close below handle low.",
            targets=["Target 1 near measured move."],
            summary="Base is constructive but breakout is not confirmed.",
        ),
        patterns=[],
        annotations=[ChartAnnotation(kind="pivot", label="Pivot", price=4210.0)],
        missing_evidence=["weekly_history"],
    )

    payload = pack.to_dict()

    assert payload["symbol"] == "DMART"
    assert payload["verdict"]["stance"] == "Watchlist / base building"
    assert payload["annotations"][0]["kind"] == "pivot"
    assert payload["missing_evidence"] == ["weekly_history"]


import pandas as pd

from terminal.visual_scan.detectors import (
    detect_breakout_retest,
    detect_cup_with_handle,
    detect_trend_structure,
    detect_vcp,
    detect_volume_quality,
    score_visual_scan,
)
from terminal.visual_scan.models import PatternStatus


def _ohlcv(closes, highs=None, lows=None, volumes=None):
    dates = pd.date_range("2026-01-01", periods=len(closes), freq="B")
    highs = highs or [c * 1.02 for c in closes]
    lows = lows or [c * 0.98 for c in closes]
    volumes = volumes or [100_000 for _ in closes]
    return pd.DataFrame(
        {
            "trade_date": dates,
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )


def test_detect_trend_structure_marks_constructive_stage_two_shape():
    closes = [100 + i for i in range(240)]
    evidence = detect_trend_structure(_ohlcv(closes), benchmark=None)

    assert evidence.pattern == "Trend Structure"
    assert evidence.status == PatternStatus.CONFIRMED
    assert evidence.confidence >= 0.7
    assert any("above SMA50" in item for item in evidence.evidence)


def test_detect_vcp_candidate_finds_contracting_ranges_and_dry_volume():
    closes = [100, 112, 104, 115, 109, 117, 113, 118, 116, 119, 118, 120]
    highs = [c + w for c, w in zip(closes, [12, 11, 9, 8, 6, 6, 4, 4, 3, 3, 2, 2])]
    lows = [c - w for c, w in zip(closes, [12, 11, 9, 8, 6, 6, 4, 4, 3, 3, 2, 2])]
    volumes = [300_000, 280_000, 250_000, 220_000, 190_000, 170_000, 150_000, 130_000, 115_000, 105_000, 95_000, 90_000]

    evidence = detect_vcp(_ohlcv(closes, highs=highs, lows=lows, volumes=volumes))

    assert evidence.pattern == "VCP"
    assert evidence.status == PatternStatus.CANDIDATE
    assert evidence.confidence >= 0.55
    assert evidence.zones.pivot is not None
    assert any("contract" in item.lower() for item in evidence.evidence)


def test_detect_cup_with_handle_candidate_marks_rounded_recovery():
    closes = [100, 96, 91, 87, 84, 82, 83, 86, 90, 95, 99, 103, 101, 100, 102]

    evidence = detect_cup_with_handle(_ohlcv(closes))

    assert evidence.pattern == "Cup With Handle"
    assert evidence.status == PatternStatus.CANDIDATE
    assert evidence.zones.invalidation is not None


def test_detect_breakout_retest_confirms_close_above_pivot_with_volume():
    closes = [100] * 30 + [106, 108, 111]
    highs = [102] * 30 + [107, 109, 112]
    lows = [98] * 30 + [103, 105, 108]
    volumes = [100_000] * 30 + [180_000, 190_000, 220_000]

    evidence = detect_breakout_retest(_ohlcv(closes, highs=highs, lows=lows, volumes=volumes), pivot=105.0)

    assert evidence.pattern == "Breakout / Retest"
    assert evidence.status == PatternStatus.CONFIRMED
    assert any("above pivot" in item.lower() for item in evidence.evidence)


def test_detect_volume_quality_marks_dry_up_and_breakout_expansion():
    closes = [100] * 25 + [104, 108]
    volumes = [200_000] * 10 + [90_000] * 15 + [260_000, 300_000]

    evidence = detect_volume_quality(_ohlcv(closes, volumes=volumes))

    assert evidence.pattern == "Volume Quality"
    assert evidence.status in {PatternStatus.CONFIRMED, PatternStatus.CANDIDATE}
    assert evidence.metrics["latest_volume_ratio_20d"] > 1.5


def test_score_visual_scan_uses_detector_weights_and_returns_stance():
    patterns = [
        detect_trend_structure(_ohlcv([100 + i for i in range(240)]), benchmark=None),
        PatternEvidence("MTF Alignment", PatternStatus.CONFIRMED, 0.8),
        PatternEvidence("VCP", PatternStatus.CANDIDATE, 0.65),
        PatternEvidence("Volume Quality", PatternStatus.CANDIDATE, 0.6),
        PatternEvidence("Breakout / Retest", PatternStatus.ABSENT, 0.2),
    ]

    verdict = score_visual_scan("DMART", patterns)

    assert verdict.stance == "Watchlist / base building"
    assert 50 <= verdict.score <= 80
    assert verdict.trigger
    assert verdict.invalidation


def test_detectors_return_insufficient_data_for_missing_close_column():
    frame = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=60, freq="B"),
            "high": [102] * 60,
            "low": [98] * 60,
            "volume": [100_000] * 60,
        }
    )

    evidence = detect_trend_structure(frame, benchmark=None)

    assert evidence.status == PatternStatus.INSUFFICIENT_DATA
    assert evidence.caveats


def test_score_visual_scan_requires_retest_hold_for_actionable_stance():
    patterns = [
        PatternEvidence("Trend Structure", PatternStatus.CONFIRMED, 0.95),
        PatternEvidence("MTF Alignment", PatternStatus.CONFIRMED, 0.9),
        PatternEvidence("VCP", PatternStatus.CONFIRMED, 0.9),
        PatternEvidence("Volume Quality", PatternStatus.CONFIRMED, 0.9),
        PatternEvidence(
            "Breakout / Retest",
            PatternStatus.CONFIRMED,
            0.9,
            metrics={"held_retest": False},
        ),
    ]

    verdict = score_visual_scan("DMART", patterns)

    assert verdict.stance != "Actionable after retest hold"


def test_score_visual_scan_avoids_trading_guidance_without_evidence():
    verdict = score_visual_scan("DMART", [])

    assert verdict.stance == "Insufficient evidence"
    assert verdict.score == 0.0
    assert "not available" in verdict.trigger.lower()
    assert "not available" in verdict.invalidation.lower()
    assert verdict.targets == []


def test_score_visual_scan_avoids_target_guidance_with_only_insufficient_evidence():
    patterns = [
        PatternEvidence("Trend Structure", PatternStatus.INSUFFICIENT_DATA, 0.0),
        PatternEvidence("VCP", PatternStatus.INSUFFICIENT_DATA, 0.0),
    ]

    verdict = score_visual_scan("DMART", patterns)

    assert verdict.stance == "Insufficient evidence"
    assert verdict.targets == []


def test_score_visual_scan_marks_absent_patterns_as_no_actionable_setup():
    patterns = [
        PatternEvidence("Trend Structure", PatternStatus.ABSENT, 0.26),
        PatternEvidence("VCP", PatternStatus.ABSENT, 0.41),
        PatternEvidence("Cup With Handle", PatternStatus.ABSENT, 0.6),
        PatternEvidence("Breakout / Retest", PatternStatus.ABSENT, 0.0),
        PatternEvidence("Volume Quality", PatternStatus.ABSENT, 0.2),
        PatternEvidence("MTF Alignment", PatternStatus.INSUFFICIENT_DATA, 0.0),
    ]

    verdict = score_visual_scan("NIFTY BANK", patterns)

    assert verdict.stance == "No actionable setup"
    assert verdict.score == 0.0
    assert verdict.targets == []
    assert "not available" in verdict.trigger.lower()


def test_volume_quality_marks_non_numeric_volume_as_insufficient_data():
    frame = _ohlcv([100] * 25)
    frame["volume"] = ["not-a-number"] * len(frame)

    evidence = detect_volume_quality(frame)

    assert evidence.status == PatternStatus.INSUFFICIENT_DATA
    assert evidence.caveats


def test_vcp_marks_non_numeric_high_low_volume_as_insufficient_data():
    frame = _ohlcv([100] * 12)
    frame["high"] = ["bad"] * len(frame)
    frame["low"] = ["bad"] * len(frame)
    frame["volume"] = ["bad"] * len(frame)

    evidence = detect_vcp(frame)

    assert evidence.status == PatternStatus.INSUFFICIENT_DATA
    assert evidence.caveats


def test_score_visual_scan_avoids_pivot_guidance_without_price_zones():
    patterns = [PatternEvidence("Volume Quality", PatternStatus.CANDIDATE, 0.6)]

    verdict = score_visual_scan("DMART", patterns)

    assert verdict.stance == "Avoid fresh entry"
    assert "not available" in verdict.trigger.lower()
    assert "not available" in verdict.invalidation.lower()
    assert verdict.targets == []


def test_breakout_retest_requires_numeric_low_and_volume():
    frame = _ohlcv([100] * 30 + [106, 108, 111])
    frame = frame.drop(columns=["low", "volume"])

    evidence = detect_breakout_retest(frame, pivot=105.0)

    assert evidence.status == PatternStatus.INSUFFICIENT_DATA
    assert evidence.caveats


def test_score_visual_scan_avoids_pivot_guidance_for_trend_only_support_zones():
    patterns = [
        PatternEvidence(
            "Trend Structure",
            PatternStatus.CONFIRMED,
            0.9,
            zones=Zones(support=100.0, invalidation=95.0),
        )
    ]

    verdict = score_visual_scan("DMART", patterns)

    assert verdict.stance == "Avoid fresh entry"
    assert "not available" in verdict.trigger.lower()
    assert verdict.targets == []
