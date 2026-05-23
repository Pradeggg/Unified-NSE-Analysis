"""Deterministic visual-pattern detectors for swing/EOD visual scans."""

from __future__ import annotations

import math
from typing import Iterable

import pandas as pd

from .models import PatternEvidence, PatternStatus, VisualScanVerdict, Zones


def _prep(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    df = frame.copy()
    df.columns = [str(col).lower().strip() for col in df.columns]
    if "close" not in df.columns:
        return pd.DataFrame()
    if "date" in df.columns and "trade_date" not in df.columns:
        df = df.rename(columns={"date": "trade_date"})
    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
        df = df.dropna(subset=["trade_date"]).sort_values("trade_date")
    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["close"])


def _sma(series: pd.Series, window: int) -> float | None:
    if len(series) < window:
        return None
    value = series.tail(window).mean()
    return float(value) if pd.notna(value) else None


def _round(value: float | None, ndigits: int = 2) -> float | None:
    if value is None or not math.isfinite(float(value)):
        return None
    return round(float(value), ndigits)


def _has_numeric_values(df: pd.DataFrame, columns: Iterable[str], min_rows: int) -> bool:
    if not set(columns).issubset(df.columns):
        return False
    return all(df[column].notna().sum() >= min_rows for column in columns)


def detect_trend_structure(daily: pd.DataFrame, benchmark: pd.DataFrame | None = None) -> PatternEvidence:
    df = _prep(daily)
    if len(df) < 50:
        return PatternEvidence(
            pattern="Trend Structure",
            status=PatternStatus.INSUFFICIENT_DATA,
            confidence=0.0,
            caveats=["Need at least 50 daily candles for trend structure."],
        )
    close = df["close"]
    latest = float(close.iloc[-1])
    sma20 = _sma(close, 20)
    sma50 = _sma(close, 50)
    sma200 = _sma(close, 200)
    high_52w = float(df["high"].tail(252).max()) if "high" in df.columns else float(close.tail(252).max())
    dist_high = ((latest / high_52w) - 1.0) * 100.0 if high_52w else None
    evidence: list[str] = []
    score = 0.0
    for label, avg in (("SMA20", sma20), ("SMA50", sma50), ("SMA200", sma200)):
        if avg is not None and latest > avg:
            evidence.append(f"Price is above {label}.")
            score += 0.22
        elif avg is not None:
            evidence.append(f"Price is below {label}.")
    if dist_high is not None and dist_high >= -15:
        evidence.append(f"Within {_round(abs(dist_high))}% of 52-week high.")
        score += 0.18
    if sma20 and sma50 and sma20 > sma50:
        evidence.append("Short-term average is above SMA50.")
        score += 0.08
    if sma50 and sma200 and sma50 > sma200:
        evidence.append("SMA50 is above SMA200.")
        score += 0.08
    confidence = min(1.0, score)
    status = PatternStatus.CONFIRMED if confidence >= 0.65 else PatternStatus.CANDIDATE if confidence >= 0.4 else PatternStatus.ABSENT
    return PatternEvidence(
        pattern="Trend Structure",
        status=status,
        confidence=_round(confidence, 2) or 0.0,
        evidence=evidence,
        zones=Zones(support=_round(sma50), invalidation=_round(sma200)),
        metrics={
            "latest_close": _round(latest),
            "sma20": _round(sma20),
            "sma50": _round(sma50),
            "sma200": _round(sma200),
            "distance_52w_high_pct": _round(dist_high),
        },
    )


def detect_vcp(daily: pd.DataFrame) -> PatternEvidence:
    df = _prep(daily)
    if len(df) < 10 or not _has_numeric_values(df, ("high", "low", "volume"), 10):
        return PatternEvidence("VCP", PatternStatus.INSUFFICIENT_DATA, 0.0, caveats=["Need numeric high, low, volume, and at least 10 candles."])
    recent = df.tail(min(len(df), 30)).copy()
    chunks = [recent.iloc[i : i + max(2, len(recent) // 4)] for i in range(0, len(recent), max(2, len(recent) // 4))]
    chunks = [chunk for chunk in chunks if len(chunk) >= 2][-4:]
    ranges = []
    for chunk in chunks:
        midpoint = float(chunk["close"].mean()) or 1.0
        ranges.append((float(chunk["high"].max()) - float(chunk["low"].min())) / midpoint * 100.0)
    contractions = sum(1 for prev, curr in zip(ranges, ranges[1:]) if curr < prev)
    latest_close = float(recent["close"].iloc[-1])
    pivot = float(recent["high"].max())
    support = float(recent["low"].tail(max(3, len(recent) // 3)).min())
    vol_first = float(recent["volume"].head(max(2, len(recent) // 3)).mean())
    vol_last = float(recent["volume"].tail(max(2, len(recent) // 3)).mean())
    dry_up = vol_last < vol_first * 0.75
    near_pivot = latest_close >= pivot * 0.94
    confidence = 0.25 + contractions * 0.16 + (0.18 if dry_up else 0.0) + (0.12 if near_pivot else 0.0)
    confidence = min(1.0, confidence)
    status = PatternStatus.CANDIDATE if contractions >= 2 and dry_up else PatternStatus.ABSENT
    evidence = [
        f"Detected {contractions} contracting range step(s).",
        f"Range sequence: {', '.join(str(_round(r)) + '%' for r in ranges)}.",
    ]
    if dry_up:
        evidence.append("Volume dried up during the latest contraction.")
    if near_pivot:
        evidence.append("Price is near the pivot/resistance area.")
    return PatternEvidence(
        pattern="VCP",
        status=status,
        confidence=_round(confidence, 2) or 0.0,
        evidence=evidence,
        zones=Zones(pivot=_round(pivot), support=_round(support), invalidation=_round(support * 0.98), target_1=_round(pivot + (pivot - support))),
        metrics={"ranges_pct": [_round(r) for r in ranges], "contractions": contractions, "volume_dry_up": dry_up},
        caveats=[] if status != PatternStatus.ABSENT else ["Contractions or volume dry-up are not strong enough."],
    )


def detect_cup_with_handle(daily: pd.DataFrame) -> PatternEvidence:
    df = _prep(daily)
    if len(df) < 12:
        return PatternEvidence("Cup With Handle", PatternStatus.INSUFFICIENT_DATA, 0.0, caveats=["Need at least 12 daily candles."])
    recent = df.tail(min(len(df), 90))
    close = recent["close"].reset_index(drop=True)
    left = float(close.iloc[: max(3, len(close) // 3)].max())
    trough_idx = int(close.idxmin())
    trough = float(close.iloc[trough_idx])
    right = float(close.iloc[-4:-1].max()) if len(close) >= 8 else float(close.iloc[-1])
    latest = float(close.iloc[-1])
    depth = (left - trough) / left * 100.0 if left else 0.0
    recovery = right >= left * 0.92
    handle_low = float(close.tail(5).min())
    handle_drift = handle_low >= right * 0.88 and latest <= max(right, latest) * 1.03
    valid_depth = 8 <= depth <= 40
    confidence = 0.2 + (0.25 if valid_depth else 0.0) + (0.25 if recovery else 0.0) + (0.15 if handle_drift else 0.0)
    status = PatternStatus.CANDIDATE if valid_depth and recovery and handle_drift else PatternStatus.ABSENT
    return PatternEvidence(
        pattern="Cup With Handle",
        status=status,
        confidence=_round(confidence, 2) or 0.0,
        evidence=[
            f"Base depth is {_round(depth)}%.",
            "Right side recovered near prior high." if recovery else "Right side has not recovered near prior high.",
            "Handle drift is within a constructive range." if handle_drift else "Handle structure is not constructive.",
        ],
        zones=Zones(pivot=_round(max(left, right)), support=_round(handle_low), invalidation=_round(handle_low * 0.98), target_1=_round(max(left, right) + (left - trough))),
        metrics={"depth_pct": _round(depth), "trough_index": trough_idx, "recovery": recovery, "handle_drift": handle_drift},
    )


def detect_breakout_retest(daily: pd.DataFrame, pivot: float | None) -> PatternEvidence:
    df = _prep(daily)
    if len(df) < 20 or pivot is None:
        return PatternEvidence("Breakout / Retest", PatternStatus.INSUFFICIENT_DATA, 0.0, caveats=["Need at least 20 candles and a pivot."])
    if not _has_numeric_values(df, ("low", "volume"), 20):
        return PatternEvidence("Breakout / Retest", PatternStatus.INSUFFICIENT_DATA, 0.0, caveats=["Need numeric low and volume data for breakout/retest confirmation."])
    latest = float(df["close"].iloc[-1])
    avg_vol = float(df["volume"].tail(20).mean()) if "volume" in df.columns else 0.0
    latest_vol = float(df["volume"].iloc[-1]) if "volume" in df.columns else 0.0
    volume_expanded = bool(avg_vol and latest_vol >= avg_vol * 1.5)
    above_pivot = latest > pivot
    held_retest = bool(above_pivot and float(df["low"].tail(5).min()) >= pivot * 0.98) if "low" in df.columns else False
    failed = bool(not above_pivot and float(df["high"].tail(5).max()) > pivot) if "high" in df.columns else False
    confidence = (0.45 if above_pivot else 0.0) + (0.25 if volume_expanded else 0.0) + (0.15 if held_retest else 0.0)
    status = PatternStatus.CONFIRMED if above_pivot and volume_expanded else PatternStatus.CANDIDATE if above_pivot else PatternStatus.ABSENT
    caveats = ["Recent breakout attempt failed."] if failed else []
    if above_pivot and not volume_expanded:
        caveats.append("Breakout volume is not confirmed.")
    return PatternEvidence(
        pattern="Breakout / Retest",
        status=status,
        confidence=_round(confidence, 2) or 0.0,
        evidence=[
            "Latest close is above pivot." if above_pivot else "Latest close is not above pivot.",
            "Volume expanded above 1.5x 20D average." if volume_expanded else "Volume expansion is not confirmed.",
            "Retest area held over recent candles." if held_retest else "Retest hold is not confirmed.",
        ],
        zones=Zones(pivot=_round(pivot), support=_round(pivot * 0.98), invalidation=_round(pivot * 0.95), target_1=_round(pivot * 1.08)),
        caveats=caveats,
        metrics={"latest_close": _round(latest), "volume_expanded": volume_expanded, "held_retest": held_retest, "failed": failed},
    )


def detect_volume_quality(daily: pd.DataFrame) -> PatternEvidence:
    df = _prep(daily)
    if len(df) < 20 or not _has_numeric_values(df, ("volume",), 20):
        return PatternEvidence("Volume Quality", PatternStatus.INSUFFICIENT_DATA, 0.0, caveats=["Need at least 20 numeric volume bars."])
    avg20 = float(df["volume"].tail(20).mean())
    latest = float(df["volume"].iloc[-1])
    ratio = latest / avg20 if avg20 else 0.0
    dry_window = df["volume"].iloc[-15:-2] if len(df) >= 17 else df["volume"].tail(10)
    dry_up = bool(float(dry_window.mean()) < avg20 * 0.8)
    expansion = ratio >= 1.5
    confidence = 0.2 + (0.25 if dry_up else 0.0) + (0.35 if expansion else 0.0)
    status = PatternStatus.CONFIRMED if dry_up and expansion else PatternStatus.CANDIDATE if dry_up or expansion else PatternStatus.ABSENT
    return PatternEvidence(
        pattern="Volume Quality",
        status=status,
        confidence=_round(confidence, 2) or 0.0,
        evidence=[
            "Volume dry-up detected in the recent base." if dry_up else "No clear volume dry-up.",
            f"Latest volume is {_round(ratio)}x the 20D average.",
        ],
        metrics={"latest_volume_ratio_20d": _round(ratio), "dry_up": dry_up, "expansion": expansion},
    )


def score_visual_scan(symbol: str, patterns: Iterable[PatternEvidence]) -> VisualScanVerdict:
    weights = {
        "Trend Structure": 25,
        "MTF Alignment": 20,
        "VCP": 20,
        "Cup With Handle": 20,
        "Volume Quality": 15,
        "Breakout / Retest": 15,
    }
    score = 0.0
    pattern_list = list(patterns)
    if not pattern_list:
        return VisualScanVerdict(
            stance="Insufficient evidence",
            score=0.0,
            confidence="low",
            trigger="Trigger not available until visual evidence is loaded.",
            invalidation="Invalidation not available until support evidence is loaded.",
            targets=[],
            summary=f"{symbol} visual scan has insufficient evidence.",
            caveats=["No visual scan evidence was supplied."],
        )
    for pattern in pattern_list:
        weight = weights.get(pattern.pattern, 0)
        multiplier = 1.0 if pattern.status == PatternStatus.CONFIRMED else 0.7 if pattern.status == PatternStatus.CANDIDATE else 0.0
        score += weight * pattern.confidence * multiplier
    score = min(100.0, score)
    breakout = next((p for p in pattern_list if p.pattern == "Breakout / Retest"), None)
    trend = next((p for p in pattern_list if p.pattern == "Trend Structure"), None)
    base = [p for p in pattern_list if p.pattern in {"VCP", "Cup With Handle"} and p.status == PatternStatus.CANDIDATE]
    has_usable_evidence = any(pattern.status in {PatternStatus.CONFIRMED, PatternStatus.CANDIDATE} for pattern in pattern_list)
    pivot_zone_patterns = [
        pattern
        for pattern in pattern_list
        if pattern.status in {PatternStatus.CONFIRMED, PatternStatus.CANDIDATE}
        and pattern.zones.pivot is not None
    ]
    has_pivot_zones = bool(pivot_zone_patterns)
    has_observed_absence = any(pattern.status == PatternStatus.ABSENT for pattern in pattern_list)
    if not has_usable_evidence:
        stance = "No actionable setup" if has_observed_absence else "Insufficient evidence"
    elif breakout and breakout.status == PatternStatus.CONFIRMED and breakout.metrics.get("held_retest") is True and score >= 70:
        stance = "Actionable after retest hold"
    elif trend and trend.status == PatternStatus.CONFIRMED and base and score >= 45:
        stance = "Watchlist / base building"
    elif score < 35:
        stance = "Avoid fresh entry"
    else:
        stance = "Manual review"
    return VisualScanVerdict(
        stance=stance,
        score=_round(score, 1) or 0.0,
        confidence="high" if score >= 75 else "medium" if score >= 45 else "low",
        trigger=(
            "Trigger not available until pivot/base evidence is loaded."
            if not has_pivot_zones
            else "Daily close above pivot with volume greater than 1.5x the 20D average."
        ),
        invalidation=(
            "Invalidation not available until support evidence is loaded."
            if not has_pivot_zones
            else "Close below the detected support or handle low."
        ),
        targets=[]
        if not has_pivot_zones
        else ["Target 1 uses the measured move from the detected base.", "Target 2 trails after breakout confirmation."],
        summary=f"{symbol} visual scan stance: {stance}.",
        caveats=(
            ["Pattern evidence is insufficient for a trading trigger."]
            if stance == "Insufficient evidence"
            else ["Price history was available, but no confirmed or candidate setup evidence was detected."]
            if stance == "No actionable setup"
            else []
        ),
    )
