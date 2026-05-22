# Visual Scan Capability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `/visual-scan SYMBOL` and natural-language visual scan routing that generates a grounded swing/EOD visual scan HTML report with deterministic chart-pattern evidence.

**Architecture:** Add a focused `terminal/visual_scan/` package with dataclasses, data loading, deterministic detectors, chart rendering, optional TradingView screenshot capture, report rendering, and command handling. Local OHLCV and computed detectors are the source of truth; TradingView is optional corroboration. Integrate with `terminal.agent` and `nse_agent.py` through deterministic routing, not general LLM planning.

**Tech Stack:** Python dataclasses, pandas, plotly/kaleido or matplotlib fallback for chart assets, existing `terminal.tools`, existing `terminal.mtf`, existing `terminal.reports` standard HTML styling, pytest, optional Playwright for TradingView capture.

---

## File Structure

- Create `terminal/visual_scan/__init__.py`
  - Public package exports.
- Create `terminal/visual_scan/models.py`
  - Dataclasses and typed status constants.
- Create `terminal/visual_scan/data_loader.py`
  - Symbol resolution and local evidence loading.
- Create `terminal/visual_scan/detectors.py`
  - Trend, VCP, cup-with-handle, breakout/retest, volume, and MTF evidence detectors.
- Create `terminal/visual_scan/chart_renderer.py`
  - Local annotated daily/weekly chart asset generation.
- Create `terminal/visual_scan/tradingview.py`
  - Optional TradingView URL and screenshot capture.
- Create `terminal/visual_scan/report.py`
  - Balanced report markdown/HTML generation.
- Create `terminal/visual_scan/command.py`
  - End-to-end command handler returning terminal summary and report paths.
- Modify `terminal/agent.py`
  - Add natural-language deterministic routing and no-LLM rendering for `visual_scan`.
- Modify `nse_agent.py`
  - Add `/visual-scan` slash command handling in interactive loop and help surfaces.
- Create `tests/test_visual_scan_detectors.py`
- Create `tests/test_visual_scan_report.py`
- Create `tests/test_visual_scan_command.py`
- Modify `tests/test_terminal_agent_market_prompt.py`
  - Add deterministic routing tests.

---

## Task 1: Create Visual Scan Models

**Files:**
- Create: `terminal/visual_scan/__init__.py`
- Create: `terminal/visual_scan/models.py`
- Test: `tests/test_visual_scan_detectors.py`

- [ ] **Step 1: Write failing model tests**

Add this to `tests/test_visual_scan_detectors.py`:

```python
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
```

- [ ] **Step 2: Run model tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_visual_scan_detectors.py::test_pattern_evidence_serializes_with_status_confidence_and_zones tests/test_visual_scan_detectors.py::test_visual_scan_pack_tracks_missing_evidence_and_annotations -q
```

Expected: fails with `ModuleNotFoundError: No module named 'terminal.visual_scan'`.

- [ ] **Step 3: Implement models**

Create `terminal/visual_scan/__init__.py`:

```python
"""Visual scan package for grounded swing/EOD chart analysis."""
```

Create `terminal/visual_scan/models.py`:

```python
"""Typed data models for visual scan evidence and reports."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


class PatternStatus:
    CONFIRMED = "confirmed"
    CANDIDATE = "candidate"
    ABSENT = "absent"
    INSUFFICIENT_DATA = "insufficient_data"


PatternStatusValue = Literal["confirmed", "candidate", "absent", "insufficient_data"]


@dataclass
class Zones:
    pivot: float | None = None
    support: float | None = None
    invalidation: float | None = None
    target_1: float | None = None
    target_2: float | None = None

    def to_dict(self) -> dict[str, float | None]:
        return asdict(self)


@dataclass
class PatternEvidence:
    pattern: str
    status: PatternStatusValue
    confidence: float
    evidence: list[str] = field(default_factory=list)
    zones: Zones = field(default_factory=Zones)
    caveats: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["zones"] = self.zones.to_dict()
        return payload


@dataclass
class ChartAnnotation:
    kind: str
    label: str
    price: float | None = None
    start: str | None = None
    end: str | None = None
    color: str = "#0f766e"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VisualScanVerdict:
    stance: str
    score: float
    confidence: str
    trigger: str
    invalidation: str
    targets: list[str] = field(default_factory=list)
    summary: str = ""
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VisualScanPack:
    run_id: str
    symbol: str
    as_of: str
    verdict: VisualScanVerdict
    patterns: list[PatternEvidence] = field(default_factory=list)
    annotations: list[ChartAnnotation] = field(default_factory=list)
    chart_paths: dict[str, str] = field(default_factory=dict)
    tradingview: dict[str, Any] = field(default_factory=dict)
    source_trail: dict[str, Any] = field(default_factory=dict)
    missing_evidence: list[str] = field(default_factory=list)
    raw_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "symbol": self.symbol,
            "as_of": self.as_of,
            "verdict": self.verdict.to_dict(),
            "patterns": [pattern.to_dict() for pattern in self.patterns],
            "annotations": [annotation.to_dict() for annotation in self.annotations],
            "chart_paths": dict(self.chart_paths),
            "tradingview": dict(self.tradingview),
            "source_trail": dict(self.source_trail),
            "missing_evidence": list(self.missing_evidence),
            "raw_metrics": dict(self.raw_metrics),
        }
```

- [ ] **Step 4: Run model tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_visual_scan_detectors.py::test_pattern_evidence_serializes_with_status_confidence_and_zones tests/test_visual_scan_detectors.py::test_visual_scan_pack_tracks_missing_evidence_and_annotations -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit models**

Run:

```bash
git add terminal/visual_scan/__init__.py terminal/visual_scan/models.py tests/test_visual_scan_detectors.py
git commit -m "feat: add visual scan evidence models"
```

---

## Task 2: Implement Deterministic Pattern Detectors

**Files:**
- Modify: `terminal/visual_scan/detectors.py`
- Test: `tests/test_visual_scan_detectors.py`

- [ ] **Step 1: Add detector tests**

Append to `tests/test_visual_scan_detectors.py`:

```python
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
```

- [ ] **Step 2: Run detector tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_visual_scan_detectors.py -q
```

Expected: fails because `terminal.visual_scan.detectors` does not exist.

- [ ] **Step 3: Implement detector functions**

Create `terminal/visual_scan/detectors.py`:

```python
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
        metrics={"latest_close": _round(latest), "sma20": _round(sma20), "sma50": _round(sma50), "sma200": _round(sma200), "distance_52w_high_pct": _round(dist_high)},
    )


def detect_vcp(daily: pd.DataFrame) -> PatternEvidence:
    df = _prep(daily)
    if len(df) < 10 or not {"high", "low", "volume"}.issubset(df.columns):
        return PatternEvidence("VCP", PatternStatus.INSUFFICIENT_DATA, 0.0, caveats=["Need high, low, volume, and at least 10 candles."])
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
    if len(df) < 20 or "volume" not in df.columns:
        return PatternEvidence("Volume Quality", PatternStatus.INSUFFICIENT_DATA, 0.0, caveats=["Need at least 20 volume bars."])
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
    for pattern in pattern_list:
        weight = weights.get(pattern.pattern, 0)
        multiplier = 1.0 if pattern.status == PatternStatus.CONFIRMED else 0.7 if pattern.status == PatternStatus.CANDIDATE else 0.0
        score += weight * pattern.confidence * multiplier
    score = min(100.0, score)
    breakout = next((p for p in pattern_list if p.pattern == "Breakout / Retest"), None)
    trend = next((p for p in pattern_list if p.pattern == "Trend Structure"), None)
    base = [p for p in pattern_list if p.pattern in {"VCP", "Cup With Handle"} and p.status == PatternStatus.CANDIDATE]
    if breakout and breakout.status == PatternStatus.CONFIRMED and score >= 70:
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
        trigger="Daily close above pivot with volume greater than 1.5x the 20D average.",
        invalidation="Close below the detected support or handle low.",
        targets=["Target 1 uses the measured move from the detected base.", "Target 2 trails after breakout confirmation."],
        summary=f"{symbol} visual scan stance: {stance}.",
    )
```

- [ ] **Step 4: Run detector tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_visual_scan_detectors.py -q
```

Expected: detector tests pass.

- [ ] **Step 5: Commit detectors**

Run:

```bash
git add terminal/visual_scan/detectors.py tests/test_visual_scan_detectors.py
git commit -m "feat: add visual scan pattern detectors"
```

---

## Task 3: Load Visual Scan Evidence

**Files:**
- Create: `terminal/visual_scan/data_loader.py`
- Test: `tests/test_visual_scan_command.py`

- [ ] **Step 1: Write failing data loader tests**

Create `tests/test_visual_scan_command.py`:

```python
import pandas as pd

from terminal.visual_scan.data_loader import VisualScanInput, load_visual_scan_input, resample_weekly


def test_resample_weekly_produces_ohlcv_weeks():
    dates = pd.date_range("2026-01-01", periods=20, freq="B")
    daily = pd.DataFrame(
        {
            "trade_date": dates,
            "open": range(20),
            "high": [value + 1 for value in range(20)],
            "low": [value - 1 for value in range(20)],
            "close": range(20),
            "volume": [1000] * 20,
        }
    )

    weekly = resample_weekly(daily)

    assert not weekly.empty
    assert {"trade_date", "open", "high", "low", "close", "volume"}.issubset(weekly.columns)
    assert weekly["volume"].iloc[0] >= 1000


def test_load_visual_scan_input_uses_injected_frames_without_database():
    daily = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=60, freq="B"),
            "open": [100] * 60,
            "high": [102] * 60,
            "low": [98] * 60,
            "close": [100 + i * 0.2 for i in range(60)],
            "volume": [100_000] * 60,
        }
    )

    data = load_visual_scan_input("DMART", input_data=VisualScanInput(daily=daily))

    assert data.symbol == "DMART"
    assert len(data.daily) == 60
    assert not data.weekly.empty
    assert data.source_trail["daily"]["status"] == "injected"
```

- [ ] **Step 2: Run data loader tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_visual_scan_command.py::test_resample_weekly_produces_ohlcv_weeks tests/test_visual_scan_command.py::test_load_visual_scan_input_uses_injected_frames_without_database -q
```

Expected: fails because `terminal.visual_scan.data_loader` does not exist.

- [ ] **Step 3: Implement data loader**

Create `terminal/visual_scan/data_loader.py`:

```python
"""Evidence loading for visual scan reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class VisualScanInput:
    daily: pd.DataFrame = field(default_factory=pd.DataFrame)
    benchmark: pd.DataFrame = field(default_factory=pd.DataFrame)
    snapshot: dict[str, Any] = field(default_factory=dict)
    sector_context: dict[str, Any] = field(default_factory=dict)
    mtf: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoadedVisualScanInput:
    symbol: str
    daily: pd.DataFrame
    weekly: pd.DataFrame
    benchmark: pd.DataFrame
    snapshot: dict[str, Any]
    sector_context: dict[str, Any]
    mtf: dict[str, Any]
    source_trail: dict[str, Any]
    missing_evidence: list[str]


def _normalize_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "volume"])
    df = frame.copy()
    df.columns = [str(col).lower().strip() for col in df.columns]
    if "date" in df.columns and "trade_date" not in df.columns:
        df = df.rename(columns={"date": "trade_date"})
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["trade_date", "close"]).sort_values("trade_date").reset_index(drop=True)


def resample_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    df = _normalize_ohlcv(daily)
    if df.empty:
        return pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "volume"])
    indexed = df.set_index("trade_date")
    weekly = indexed.resample("W-FRI").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    return weekly.dropna(subset=["close"]).reset_index()


def _load_daily_from_market(symbol: str) -> pd.DataFrame:
    try:
        from terminal.recommendation_report import load_recommendation_input_data

        data = load_recommendation_input_data()
        frame = data.equity_history
        if frame is None or frame.empty:
            return pd.DataFrame()
        cols = {str(col).lower(): col for col in frame.columns}
        sym_col = cols.get("symbol")
        if not sym_col:
            return pd.DataFrame()
        return frame[frame[sym_col].astype(str).str.upper() == symbol.upper()].copy()
    except Exception:
        return pd.DataFrame()


def load_visual_scan_input(symbol: str, input_data: VisualScanInput | None = None) -> LoadedVisualScanInput:
    sym = str(symbol or "").strip().upper()
    source_trail: dict[str, Any] = {}
    missing: list[str] = []
    if input_data is not None and not input_data.daily.empty:
        daily = _normalize_ohlcv(input_data.daily)
        source_trail["daily"] = {"status": "injected", "rows": len(daily)}
    else:
        daily = _normalize_ohlcv(_load_daily_from_market(sym))
        source_trail["daily"] = {"status": "loaded" if not daily.empty else "missing", "rows": len(daily)}
    if daily.empty:
        missing.append("daily_history")
    weekly = resample_weekly(daily)
    if weekly.empty:
        missing.append("weekly_history")
    source_trail["weekly"] = {"status": "derived" if not weekly.empty else "missing", "rows": len(weekly)}
    injected = input_data or VisualScanInput()
    return LoadedVisualScanInput(
        symbol=sym,
        daily=daily,
        weekly=weekly,
        benchmark=_normalize_ohlcv(injected.benchmark),
        snapshot=dict(injected.snapshot),
        sector_context=dict(injected.sector_context),
        mtf=dict(injected.mtf),
        source_trail=source_trail,
        missing_evidence=missing,
    )
```

- [ ] **Step 4: Run data loader tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_visual_scan_command.py::test_resample_weekly_produces_ohlcv_weeks tests/test_visual_scan_command.py::test_load_visual_scan_input_uses_injected_frames_without_database -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit data loader**

Run:

```bash
git add terminal/visual_scan/data_loader.py tests/test_visual_scan_command.py
git commit -m "feat: load visual scan evidence"
```

---

## Task 4: Render Annotated Local Charts

**Files:**
- Create: `terminal/visual_scan/chart_renderer.py`
- Test: `tests/test_visual_scan_report.py`

- [ ] **Step 1: Write failing chart renderer test**

Create `tests/test_visual_scan_report.py`:

```python
from pathlib import Path

import pandas as pd

from terminal.visual_scan.chart_renderer import render_visual_scan_charts
from terminal.visual_scan.models import ChartAnnotation


def test_render_visual_scan_charts_writes_daily_and_weekly_html_assets(tmp_path):
    daily = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=80, freq="B"),
            "open": [100] * 80,
            "high": [103] * 80,
            "low": [97] * 80,
            "close": [100 + i * 0.5 for i in range(80)],
            "volume": [100_000] * 80,
        }
    )
    weekly = daily.iloc[::5].copy()
    paths = render_visual_scan_charts(
        symbol="DMART",
        run_id="run1",
        daily=daily,
        weekly=weekly,
        annotations=[ChartAnnotation(kind="pivot", label="Pivot", price=130.0)],
        output_dir=tmp_path,
    )

    assert Path(paths["daily"]).exists()
    assert Path(paths["weekly"]).exists()
    assert Path(paths["daily"]).suffix == ".html"
    assert "DMART" in Path(paths["daily"]).read_text()
```

- [ ] **Step 2: Run chart renderer test to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_visual_scan_report.py::test_render_visual_scan_charts_writes_daily_and_weekly_html_assets -q
```

Expected: fails because `terminal.visual_scan.chart_renderer` does not exist.

- [ ] **Step 3: Implement chart renderer**

Create `terminal/visual_scan/chart_renderer.py`:

```python
"""Annotated local chart rendering for visual scan reports."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .models import ChartAnnotation


def _prep(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    df.columns = [str(col).lower().strip() for col in df.columns]
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    return df.dropna(subset=["trade_date", "close"]).sort_values("trade_date")


def _render_one(symbol: str, label: str, frame: pd.DataFrame, annotations: list[ChartAnnotation], path: Path) -> None:
    df = _prep(frame)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.04)
    fig.add_trace(
        go.Candlestick(
            x=df["trade_date"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name=f"{symbol} {label}",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(go.Bar(x=df["trade_date"], y=df["volume"], name="Volume", marker_color="#64748b"), row=2, col=1)
    for window, color in ((20, "#2563eb"), (50, "#16a34a"), (200, "#dc2626")):
        if len(df) >= window:
            fig.add_trace(
                go.Scatter(x=df["trade_date"], y=df["close"].rolling(window).mean(), mode="lines", name=f"SMA{window}", line={"color": color, "width": 1.2}),
                row=1,
                col=1,
            )
    for annotation in annotations:
        if annotation.price is None:
            continue
        fig.add_hline(
            y=annotation.price,
            line_dash="dot",
            line_color=annotation.color,
            annotation_text=annotation.label,
            annotation_position="top left",
            row=1,
            col=1,
        )
    fig.update_layout(
        title=f"{symbol} Visual Scan - {label}",
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        height=760,
        margin={"l": 50, "r": 30, "t": 60, "b": 40},
    )
    path.write_text(fig.to_html(full_html=True, include_plotlyjs="cdn"))


def render_visual_scan_charts(
    *,
    symbol: str,
    run_id: str,
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    annotations: list[ChartAnnotation],
    output_dir: str | Path,
) -> dict[str, str]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    daily_path = target / f"{symbol}_{run_id}_daily.html"
    weekly_path = target / f"{symbol}_{run_id}_weekly.html"
    _render_one(symbol, "Daily", daily, annotations, daily_path)
    _render_one(symbol, "Weekly", weekly, annotations, weekly_path)
    return {"daily": str(daily_path), "weekly": str(weekly_path)}
```

- [ ] **Step 4: Run chart renderer test to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_visual_scan_report.py::test_render_visual_scan_charts_writes_daily_and_weekly_html_assets -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit chart renderer**

Run:

```bash
git add terminal/visual_scan/chart_renderer.py tests/test_visual_scan_report.py
git commit -m "feat: render visual scan chart assets"
```

---

## Task 5: Add Optional TradingView Capture

**Files:**
- Create: `terminal/visual_scan/tradingview.py`
- Test: `tests/test_visual_scan_report.py`

- [ ] **Step 1: Add TradingView tests**

Append to `tests/test_visual_scan_report.py`:

```python
from terminal.visual_scan.tradingview import build_tradingview_url, capture_tradingview_screenshot


def test_build_tradingview_url_uses_nse_prefix():
    assert build_tradingview_url("DMART") == "https://www.tradingview.com/chart/?symbol=NSE%3ADMART"


def test_capture_tradingview_screenshot_fail_open_when_playwright_unavailable(tmp_path, monkeypatch):
    def raise_import_error(*_args, **_kwargs):
        raise ImportError("playwright missing")

    monkeypatch.setattr("builtins.__import__", lambda name, *args, **kwargs: raise_import_error() if name.startswith("playwright") else __import__(name, *args, **kwargs))

    result = capture_tradingview_screenshot("DMART", output_dir=tmp_path, run_id="run1", timeout_ms=100)

    assert result["status"] == "unavailable"
    assert "TradingView screenshot unavailable" in result["message"]
```

- [ ] **Step 2: Run TradingView tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_visual_scan_report.py::test_build_tradingview_url_uses_nse_prefix tests/test_visual_scan_report.py::test_capture_tradingview_screenshot_fail_open_when_playwright_unavailable -q
```

Expected: fails because `terminal.visual_scan.tradingview` does not exist.

- [ ] **Step 3: Implement TradingView helper**

Create `terminal/visual_scan/tradingview.py`:

```python
"""Optional TradingView screenshot capture for visual scans."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote


def build_tradingview_url(symbol: str) -> str:
    return "https://www.tradingview.com/chart/?symbol=" + quote(f"NSE:{str(symbol).upper()}", safe="")


def capture_tradingview_screenshot(
    symbol: str,
    *,
    output_dir: str | Path,
    run_id: str,
    timeout_ms: int = 12_000,
) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return {
            "status": "unavailable",
            "message": f"TradingView screenshot unavailable; report generated from local OHLCV evidence. Reason: {exc}",
            "url": build_tradingview_url(symbol),
        }
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{str(symbol).upper()}_{run_id}_tradingview_daily.png"
    url = build_tradingview_url(symbol)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 920})
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(2500)
            page.screenshot(path=str(path), full_page=True)
            browser.close()
        return {"status": "captured", "path": str(path), "url": url, "message": "TradingView screenshot captured as corroboration only."}
    except Exception as exc:
        return {
            "status": "unavailable",
            "message": f"TradingView screenshot unavailable; report generated from local OHLCV evidence. Reason: {exc}",
            "url": url,
        }
```

- [ ] **Step 4: Run TradingView tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_visual_scan_report.py::test_build_tradingview_url_uses_nse_prefix tests/test_visual_scan_report.py::test_capture_tradingview_screenshot_fail_open_when_playwright_unavailable -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit TradingView helper**

Run:

```bash
git add terminal/visual_scan/tradingview.py tests/test_visual_scan_report.py
git commit -m "feat: add optional tradingview capture"
```

---

## Task 6: Generate Balanced HTML Report and JSON Evidence

**Files:**
- Create: `terminal/visual_scan/report.py`
- Test: `tests/test_visual_scan_report.py`

- [ ] **Step 1: Add report tests**

Append to `tests/test_visual_scan_report.py`:

```python
from terminal.visual_scan.models import PatternEvidence, PatternStatus, VisualScanPack, VisualScanVerdict, Zones
from terminal.visual_scan.report import render_visual_scan_markdown, save_visual_scan_outputs


def test_render_visual_scan_markdown_contains_balanced_sections():
    pack = VisualScanPack(
        run_id="run1",
        symbol="DMART",
        as_of="2026-05-22",
        verdict=VisualScanVerdict(
            stance="Watchlist / base building",
            score=68,
            confidence="medium",
            trigger="Daily close above pivot with volume confirmation.",
            invalidation="Close below support.",
            targets=["Target 1 near 4550."],
            summary="Constructive base, breakout not confirmed.",
        ),
        patterns=[
            PatternEvidence("VCP", PatternStatus.CANDIDATE, 0.72, evidence=["Range contracted."], zones=Zones(pivot=4210)),
        ],
        chart_paths={"daily": "assets/daily.html", "weekly": "assets/weekly.html"},
        tradingview={"status": "unavailable", "message": "TradingView screenshot unavailable; report generated from local OHLCV evidence."},
        source_trail={"daily": {"status": "loaded", "rows": 240}},
    )

    markdown = render_visual_scan_markdown(pack)

    assert "# DMART Visual Scan" in markdown
    assert "## Verdict" in markdown
    assert "## Annotated Charts" in markdown
    assert "## Pattern Evidence" in markdown
    assert "Watchlist / base building" in markdown
    assert "TradingView screenshot unavailable" in markdown


def test_save_visual_scan_outputs_writes_html_and_json(tmp_path):
    pack = VisualScanPack(
        run_id="run1",
        symbol="DMART",
        as_of="2026-05-22",
        verdict=VisualScanVerdict("Manual review", 10, "low", "Collect data.", "No action.", summary="Missing data."),
    )

    result = save_visual_scan_outputs(pack, output_dir=tmp_path)

    assert result["success"] is True
    assert result["html_path"].endswith(".html")
    assert result["json_path"].endswith(".json")
    assert Path(result["html_path"]).exists()
    assert Path(result["json_path"]).exists()
```

- [ ] **Step 2: Run report tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_visual_scan_report.py::test_render_visual_scan_markdown_contains_balanced_sections tests/test_visual_scan_report.py::test_save_visual_scan_outputs_writes_html_and_json -q
```

Expected: fails because `terminal.visual_scan.report` does not exist.

- [ ] **Step 3: Implement report rendering**

Create `terminal/visual_scan/report.py`:

```python
"""Report rendering for visual scan outputs."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from terminal.reports import generate_report

from .models import VisualScanPack


def _table(headers: list[str], rows: list[list[object]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(value if value is not None else "") for value in row) + " |")
    return "\n".join(out)


def render_visual_scan_markdown(pack: VisualScanPack) -> str:
    verdict = pack.verdict
    lines = [
        f"# {pack.symbol} Visual Scan",
        "",
        "Research and learning only. Not investment advice.",
        "",
        "## Verdict",
        "",
        f"**{verdict.stance}** | Score: **{verdict.score}** | Confidence: **{verdict.confidence.title()}**",
        "",
        verdict.summary,
        "",
        f"- Trigger: {verdict.trigger}",
        f"- Invalidation: {verdict.invalidation}",
    ]
    for target in verdict.targets:
        lines.append(f"- Target: {target}")
    if verdict.caveats:
        lines.extend(["", "Caveats:"])
        lines.extend(f"- {item}" for item in verdict.caveats)
    lines.extend(["", "## Annotated Charts", ""])
    if pack.chart_paths:
        for label, path in pack.chart_paths.items():
            lines.append(f"- {label.title()}: `{path}`")
    else:
        lines.append("- Chart assets unavailable.")
    lines.extend(["", "## Decision Panel", ""])
    lines.append(_table(["Item", "Value"], [["Trigger", verdict.trigger], ["Invalidation", verdict.invalidation], ["Confidence", verdict.confidence], ["Score", verdict.score]]))
    lines.extend(["", "## Pattern Evidence", ""])
    rows = []
    for pattern in pack.patterns:
        rows.append([pattern.pattern, pattern.status, pattern.confidence, "; ".join(pattern.evidence), "; ".join(pattern.caveats)])
    lines.append(_table(["Pattern", "Status", "Confidence", "Evidence", "Caveats"], rows or [["No detector evidence", "", "", "", ""]]))
    lines.extend(["", "## TradingView Corroboration", ""])
    tv = pack.tradingview or {}
    lines.append(f"- Status: {tv.get('status', 'not_attempted')}")
    if tv.get("path"):
        lines.append(f"- Screenshot: `{tv.get('path')}`")
    if tv.get("message"):
        lines.append(f"- Note: {tv.get('message')}")
    lines.extend(["", "## Source & Audit Trail", ""])
    source_rows = [[name, row.get("status"), row.get("rows", ""), row.get("latest", "")] for name, row in pack.source_trail.items() if isinstance(row, dict)]
    lines.append(_table(["Source", "Status", "Rows", "Latest"], source_rows or [["No source trail", "", "", ""]]))
    lines.extend(["", "## Missing Evidence", ""])
    lines.extend(f"- {item}" for item in pack.missing_evidence) if pack.missing_evidence else lines.append("- none")
    return "\n".join(lines)


def save_visual_scan_outputs(pack: VisualScanPack, output_dir: str | Path = "reports/visual_scan") -> dict:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    stem = f"{pack.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{pack.run_id[:8]}"
    markdown = render_visual_scan_markdown(pack)
    report_result = generate_report(
        markdown,
        report_type="research",
        symbol=pack.symbol,
        output_format="html",
        title=f"{pack.symbol} Visual Scan",
        filename=stem,
    )
    html_path = report_result.get("path") or str(target / f"{stem}.html")
    json_path = target / f"{stem}.json"
    json_path.write_text(json.dumps(pack.to_dict(), indent=2, default=str))
    return {
        "success": bool(report_result.get("success", True)),
        "html_path": html_path,
        "json_path": str(json_path),
        "markdown": markdown,
    }
```

- [ ] **Step 4: Run report tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_visual_scan_report.py -q
```

Expected: report tests pass.

- [ ] **Step 5: Commit report rendering**

Run:

```bash
git add terminal/visual_scan/report.py tests/test_visual_scan_report.py
git commit -m "feat: render visual scan reports"
```

---

## Task 7: Build End-to-End Command Handler

**Files:**
- Create: `terminal/visual_scan/command.py`
- Modify: `terminal/visual_scan/__init__.py`
- Test: `tests/test_visual_scan_command.py`

- [ ] **Step 1: Add command handler tests**

Append to `tests/test_visual_scan_command.py`:

```python
from terminal.visual_scan.command import run_visual_scan


def test_run_visual_scan_with_injected_data_returns_report_paths(tmp_path):
    daily = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=260, freq="B"),
            "open": [100 + i * 0.2 for i in range(260)],
            "high": [102 + i * 0.2 for i in range(260)],
            "low": [98 + i * 0.2 for i in range(260)],
            "close": [100 + i * 0.2 for i in range(260)],
            "volume": [100_000] * 260,
        }
    )

    result = run_visual_scan(
        "DMART",
        input_data=VisualScanInput(daily=daily),
        output_dir=tmp_path,
        capture_tradingview=False,
    )

    assert result["success"] is True
    assert result["symbol"] == "DMART"
    assert result["html_path"].endswith(".html")
    assert "Visual Scan" in result["summary"]
```

- [ ] **Step 2: Run command test to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_visual_scan_command.py::test_run_visual_scan_with_injected_data_returns_report_paths -q
```

Expected: fails because `terminal.visual_scan.command` does not exist.

- [ ] **Step 3: Implement command handler**

Create `terminal/visual_scan/command.py`:

```python
"""End-to-end visual scan command handler."""

from __future__ import annotations

import uuid
from pathlib import Path

from .chart_renderer import render_visual_scan_charts
from .data_loader import VisualScanInput, load_visual_scan_input
from .detectors import (
    detect_breakout_retest,
    detect_cup_with_handle,
    detect_trend_structure,
    detect_vcp,
    detect_volume_quality,
    score_visual_scan,
)
from .models import ChartAnnotation, PatternEvidence, PatternStatus, VisualScanPack
from .report import save_visual_scan_outputs
from .tradingview import capture_tradingview_screenshot


def _mtf_pattern(mtf_payload: dict) -> PatternEvidence:
    if not mtf_payload:
        return PatternEvidence("MTF Alignment", PatternStatus.INSUFFICIENT_DATA, 0.0, caveats=["MTF evidence unavailable."])
    score = float(mtf_payload.get("confluence_score") or mtf_payload.get("score") or 0)
    status = PatternStatus.CONFIRMED if score >= 70 else PatternStatus.CANDIDATE if score >= 45 else PatternStatus.ABSENT
    return PatternEvidence(
        pattern="MTF Alignment",
        status=status,
        confidence=round(min(score / 100.0, 1.0), 2),
        evidence=[str(item) for item in (mtf_payload.get("rationale") or [])[:5]],
        metrics=mtf_payload,
    )


def _annotations_from_patterns(patterns: list[PatternEvidence]) -> list[ChartAnnotation]:
    annotations: list[ChartAnnotation] = []
    for pattern in patterns:
        if pattern.zones.pivot is not None:
            annotations.append(ChartAnnotation(kind="pivot", label=f"{pattern.pattern} Pivot", price=pattern.zones.pivot, color="#22c55e"))
        if pattern.zones.support is not None:
            annotations.append(ChartAnnotation(kind="support", label=f"{pattern.pattern} Support", price=pattern.zones.support, color="#38bdf8"))
        if pattern.zones.invalidation is not None:
            annotations.append(ChartAnnotation(kind="invalidation", label="Invalidation", price=pattern.zones.invalidation, color="#ef4444"))
        if pattern.zones.target_1 is not None:
            annotations.append(ChartAnnotation(kind="target", label="Target 1", price=pattern.zones.target_1, color="#f59e0b"))
    return annotations


def run_visual_scan(
    symbol: str,
    *,
    input_data: VisualScanInput | None = None,
    output_dir: str | Path = "reports/visual_scan",
    capture_tradingview: bool = True,
) -> dict:
    run_id = str(uuid.uuid4())
    loaded = load_visual_scan_input(symbol, input_data=input_data)
    trend = detect_trend_structure(loaded.daily, benchmark=loaded.benchmark)
    vcp = detect_vcp(loaded.daily)
    cup = detect_cup_with_handle(loaded.daily)
    pivot = vcp.zones.pivot or cup.zones.pivot
    breakout = detect_breakout_retest(loaded.daily, pivot=pivot)
    volume = detect_volume_quality(loaded.daily)
    mtf = _mtf_pattern(loaded.mtf)
    patterns = [trend, mtf, vcp, cup, breakout, volume]
    verdict = score_visual_scan(loaded.symbol, patterns)
    annotations = _annotations_from_patterns(patterns)
    asset_dir = Path(output_dir) / "assets"
    chart_paths = {}
    try:
        chart_paths = render_visual_scan_charts(
            symbol=loaded.symbol,
            run_id=run_id[:8],
            daily=loaded.daily,
            weekly=loaded.weekly,
            annotations=annotations,
            output_dir=asset_dir,
        )
    except Exception as exc:
        loaded.missing_evidence.append(f"chart_assets: {exc}")
    tradingview = {"status": "not_attempted", "message": "TradingView capture disabled."}
    if capture_tradingview:
        tradingview = capture_tradingview_screenshot(loaded.symbol, output_dir=asset_dir, run_id=run_id[:8])
    pack = VisualScanPack(
        run_id=run_id,
        symbol=loaded.symbol,
        as_of=str(loaded.daily["trade_date"].max().date()) if not loaded.daily.empty else "",
        verdict=verdict,
        patterns=patterns,
        annotations=annotations,
        chart_paths=chart_paths,
        tradingview=tradingview,
        source_trail=loaded.source_trail,
        missing_evidence=loaded.missing_evidence,
    )
    saved = save_visual_scan_outputs(pack, output_dir=output_dir)
    summary = f"{loaded.symbol} Visual Scan: {verdict.stance} | Score {verdict.score} | Confidence {verdict.confidence}. Report: {saved['html_path']}"
    return {
        "success": True,
        "symbol": loaded.symbol,
        "run_id": run_id,
        "summary": summary,
        **saved,
        "pack": pack.to_dict(),
    }
```

Update `terminal/visual_scan/__init__.py`:

```python
"""Visual scan package for grounded swing/EOD chart analysis."""

from .command import run_visual_scan

__all__ = ["run_visual_scan"]
```

- [ ] **Step 4: Run command tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_visual_scan_command.py -q
```

Expected: command tests pass.

- [ ] **Step 5: Commit command handler**

Run:

```bash
git add terminal/visual_scan/__init__.py terminal/visual_scan/command.py tests/test_visual_scan_command.py
git commit -m "feat: add visual scan command handler"
```

---

## Task 8: Add Agent and CLI Routing

**Files:**
- Modify: `terminal/agent.py`
- Modify: `nse_agent.py`
- Test: `tests/test_terminal_agent_market_prompt.py`
- Test: `tests/test_visual_scan_command.py`

- [ ] **Step 1: Add routing tests**

Append to `tests/test_terminal_agent_market_prompt.py`:

```python
def test_visual_scan_prompt_routes_to_visual_scan_tool(self):
    routed = _keyword_intent("Perform a visual scan of DMART", data_mode="historical")

    self.assertEqual(routed["intent"], "visual_scan")
    self.assertEqual(routed["plan"], [("run_visual_scan", {"symbol": "DMART"})])


def test_visual_scan_slash_prompt_routes_to_visual_scan_tool(self):
    routed = _keyword_intent("/visual-scan DMART", data_mode="historical")

    self.assertEqual(routed["intent"], "visual_scan")
    self.assertEqual(routed["plan"], [("run_visual_scan", {"symbol": "DMART"})])
```

Append to `tests/test_visual_scan_command.py`:

```python
from unittest.mock import patch

import nse_agent


def test_slash_command_list_includes_visual_scan():
    labels = [label for label, _description in nse_agent._SLASH_COMMANDS]

    assert "/visual-scan" in labels
```

- [ ] **Step 2: Run routing tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_agent_market_prompt.py::TerminalAgentMarketPromptTests::test_visual_scan_prompt_routes_to_visual_scan_tool tests/test_terminal_agent_market_prompt.py::TerminalAgentMarketPromptTests::test_visual_scan_slash_prompt_routes_to_visual_scan_tool tests/test_visual_scan_command.py::test_slash_command_list_includes_visual_scan -q
```

Expected: tests fail because routing and command list do not include visual scan.

- [ ] **Step 3: Register visual scan tool**

Add to `terminal/tools.py` imports near other visual/MTF helpers:

```python
from terminal.visual_scan.command import run_visual_scan
```

Add to `TOOL_REGISTRY`:

```python
"run_visual_scan": (
    run_visual_scan,
    "Generate a grounded swing/EOD visual scan report for one NSE symbol with annotated charts, deterministic pattern evidence, MTF alignment, optional TradingView corroboration, and a research stance.",
    {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "capture_tradingview": {"type": "boolean", "default": True},
        },
        "required": ["symbol"],
    },
),
```

If `TOOL_REGISTRY` is generated in a different section, place this entry beside `open_html_chart`, `analyze_mtf`, or other report tools.

- [ ] **Step 4: Add deterministic routing in `terminal/agent.py`**

In `_keyword_intent`, before generic stock/technical routing, add:

```python
visual_scan_match = re.search(
    r"^(?:/visual-scan|/visual_scan|visual scan|perform a visual scan of|deep visual qa of)\s+(.+)$",
    routing_text.strip(),
    flags=re.IGNORECASE,
)
if visual_scan_match:
    raw_symbol = visual_scan_match.group(1).strip(" .,:;")
    raw_symbol = re.sub(r"\bchart\b", "", raw_symbol, flags=re.IGNORECASE).strip()
    sym_q = _primary_symbol_query([raw_symbol], [], raw_symbol)
    return {"intent": "visual_scan", "plan": [("run_visual_scan", {"symbol": sym_q.upper()})]}
```

In `_synthesize_no_llm`, near other report-oriented results, add:

```python
visual_scan = _get("run_visual_scan")
if intent == "visual_scan" and visual_scan:
    lines.append(f"━━━ {visual_scan.get('symbol', '—')} — Visual Scan ━━━")
    lines.append(visual_scan.get("summary", "Visual scan completed."))
    if visual_scan.get("html_path"):
        lines.append(f"Report: {visual_scan.get('html_path')}")
    if visual_scan.get("json_path"):
        lines.append(f"Evidence: {visual_scan.get('json_path')}")
    lines.append("\n▶ SOURCE TRAIL")
    lines.extend(_source_trail_lines(tool_results))
    lines.append("\n━━━ Not investment advice. For research and learning only. ━━━")
    return "\n".join(line for line in lines if str(line).strip())
```

Add `"visual_scan"` to the deterministic intent set that executes tool plans without LLM. Search for the intent set containing `"fno_overview", "market_dashboard", "screener"` and add `"visual_scan"`.

- [ ] **Step 5: Add slash command listing in `nse_agent.py`**

Add to `_SLASH_COMMANDS` near chart/report commands:

```python
("/visual-scan", "Grounded swing/EOD visual scan report with annotated charts and pattern evidence"),
```

Add help examples near chart help:

```python
("/visual-scan DMART", "Balanced visual scan report: trend, VCP, cup-handle, breakout, volume, MTF"),
```

- [ ] **Step 6: Run routing tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_agent_market_prompt.py::TerminalAgentMarketPromptTests::test_visual_scan_prompt_routes_to_visual_scan_tool tests/test_terminal_agent_market_prompt.py::TerminalAgentMarketPromptTests::test_visual_scan_slash_prompt_routes_to_visual_scan_tool tests/test_visual_scan_command.py::test_slash_command_list_includes_visual_scan -q
```

Expected: routing tests pass.

- [ ] **Step 7: Run tool registry tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_tools_registry.py -q
```

Expected: tool registry tests pass.

- [ ] **Step 8: Commit routing**

Run:

```bash
git add terminal/tools.py terminal/agent.py nse_agent.py tests/test_terminal_agent_market_prompt.py tests/test_visual_scan_command.py
git commit -m "feat: route visual scan command"
```

---

## Task 9: End-to-End Verification With Actual Data

**Files:**
- No new files required.
- Generated artifacts under `reports/visual_scan/`.

- [ ] **Step 1: Run full visual scan tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_visual_scan_detectors.py tests/test_visual_scan_report.py tests/test_visual_scan_command.py -q
```

Expected: all visual scan tests pass.

- [ ] **Step 2: Run related agent tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_agent_market_prompt.py tests/test_terminal_tools_registry.py tests/test_mtf.py -q
```

Expected: related tests pass.

- [ ] **Step 3: Generate an actual DMART report without requiring TradingView**

Run:

```bash
.venv/bin/python - <<'PY'
from terminal.visual_scan.command import run_visual_scan
result = run_visual_scan("DMART", capture_tradingview=False)
print(result["success"])
print(result["summary"])
print(result["html_path"])
print(result["json_path"])
PY
```

Expected:

```text
True
DMART Visual Scan: ...
...reports...visual_scan...html
...reports...visual_scan...json
```

- [ ] **Step 4: Inspect generated report content**

Run:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
path = sorted(Path("reports/visual_scan").glob("DMART_*.json"))[-1]
text = path.read_text()
for required in ["Trend Structure", "VCP", "Cup With Handle", "Breakout / Retest", "Volume Quality"]:
    assert required in text, required
print(path)
PY
```

Expected: prints the latest JSON path and raises no assertion.

- [ ] **Step 5: Open the generated HTML report**

Run:

```bash
open "$(ls -t reports/visual_scan/DMART_*.html | head -1)"
```

Expected: browser opens the report. Confirm it has:

- Verdict strip.
- Annotated daily chart path.
- Weekly chart path.
- Pattern evidence table.
- TradingView status.
- Source and audit trail.

- [ ] **Step 6: Commit verification adjustments if needed**

If verification required code changes, run the specific failing tests again and commit only the changed source/tests:

```bash
git status --short
git add <changed-source-and-test-files>
git commit -m "fix: stabilize visual scan verification"
```

If no code changes were required, do not create a commit for generated report artifacts.

---

## Plan Self-Review

Spec coverage:

- Swing/EOD scope: Tasks 2, 3, 4, 6, 7.
- Local deterministic evidence as source of truth: Tasks 2, 3, 7.
- TradingView optional corroboration: Task 5.
- Balanced HTML report: Task 6.
- JSON replay evidence pack: Task 6.
- Deterministic routing: Task 8.
- Error handling: Tasks 3, 5, 6, 7.
- Testing of detectors/report/command/routing: Tasks 1-9.

Placeholder scan:

- No unresolved placeholders are intentionally present in this plan.
- Every code-writing task includes concrete code or exact insertion snippets.
- Every verification step includes exact commands and expected outcomes.

Type consistency:

- `PatternEvidence`, `Zones`, `ChartAnnotation`, `VisualScanVerdict`, and `VisualScanPack` are introduced in Task 1 and reused consistently.
- `VisualScanInput` and `LoadedVisualScanInput` are introduced in Task 3 and reused in Task 7.
- `run_visual_scan()` is introduced in Task 7 and registered in Task 8.

