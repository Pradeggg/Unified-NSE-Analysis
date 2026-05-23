"""Multi-timeframe (MTF) analysis engine.

Computes a per-timeframe indicator stack (Monthly / Weekly / Daily / 60m / 15m)
for a symbol and scores cross-timeframe confluence into a single verdict.

Design notes
------------
* Daily history is the source of truth. Weekly and Monthly bars are derived
  from daily via pandas resample (W-FRI / M).
* Intraday timeframes (60m, 15m) are pulled from PostgreSQL intraday.ohlcv_bars
  via ``terminal.tools.get_intraday_bars``. If PG has no bars, the timeframe
  is reported as ``status="missing"`` — we never fabricate a verdict from
  fallback data.
* The scorer is intentionally explicit and deterministic so that every verdict
  is auditable (callers can show ``aligned_tfs`` / ``dissonant_tfs`` to the
  user). It does NOT call any LLM.

This module is consumed by:
  * ``analyze_mtf`` / ``scan_mtf_aligned`` tools (terminal/tools.py)
  * ``/mtf`` slash command (nse_agent.py)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import pandas as pd

# Timeframe identifiers used throughout the module + tool surface.
TF_MONTHLY = "monthly"
TF_WEEKLY = "weekly"
TF_DAILY = "daily"
TF_60M = "60m"
TF_15M = "15m"

DEFAULT_TIMEFRAMES: tuple[str, ...] = (
    TF_MONTHLY,
    TF_WEEKLY,
    TF_DAILY,
    TF_60M,
    TF_15M,
)

# Per-timeframe weights for the confluence scorer. Higher timeframes dominate
# (Stan Weinstein / Minervini convention: weekly trend governs daily setups).
TF_WEIGHTS: dict[str, int] = {
    TF_MONTHLY: 30,
    TF_WEEKLY: 25,
    TF_DAILY: 25,
    TF_60M: 12,
    TF_15M: 8,
}
assert sum(TF_WEIGHTS.values()) == 100, "TF_WEIGHTS must sum to 100"

_DAILY_TFS: frozenset[str] = frozenset({TF_MONTHLY, TF_WEEKLY, TF_DAILY})
_INTRADAY_TFS: frozenset[str] = frozenset({TF_60M, TF_15M})


@dataclass
class TimeframeReading:
    """Indicator snapshot for one timeframe."""

    timeframe: str
    status: str  # "ok" | "missing" | "insufficient_history"
    direction: str = "unknown"  # "bullish" | "bearish" | "neutral" | "unknown"
    bars: int = 0
    close: float | None = None
    rsi: float | None = None
    macd: str | None = None  # "bullish" | "bearish" | None
    ema20: float | None = None
    ema50: float | None = None
    above_ema20: bool | None = None
    above_ema50: bool | None = None
    sma_stack_bullish: bool | None = None  # close > sma20 > sma50 > sma200
    sma_stack_bearish: bool | None = None
    pct_from_period_high: float | None = None
    pct_from_period_low: float | None = None
    note: str = ""

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class MTFResult:
    symbol: str
    timeframes: list[str]
    readings: dict[str, TimeframeReading]
    confluence_score: int
    direction: str  # "bullish" | "bearish" | "mixed" | "neutral"
    verdict: str  # "BUY" | "WATCH" | "AVOID" | "SELL"
    aligned_tfs: list[str]
    dissonant_tfs: list[str]
    missing_tfs: list[str]
    rationale: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframes": self.timeframes,
            "readings": {tf: r.as_dict() for tf, r in self.readings.items()},
            "confluence_score": self.confluence_score,
            "direction": self.direction,
            "verdict": self.verdict,
            "aligned_tfs": self.aligned_tfs,
            "dissonant_tfs": self.dissonant_tfs,
            "missing_tfs": self.missing_tfs,
            "rationale": self.rationale,
        }


# ── Resampling helpers ──────────────────────────────────────────────────────


_RESAMPLE_RULES: dict[str, str] = {
    TF_WEEKLY: "W-FRI",
    # pandas >=2.2 deprecates "M"; ME (month-end) is the supported alias.
    TF_MONTHLY: "ME",
}


def resample_ohlcv(daily: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Resample a daily OHLCV frame to weekly/monthly.

    Expects columns: TIMESTAMP, OPEN, HIGH, LOW, CLOSE, TOTTRDQTY. Returns an
    empty frame if input is empty or the timeframe is not supported.
    """
    if daily is None or daily.empty:
        return pd.DataFrame()
    if timeframe == TF_DAILY:
        return daily.copy()
    rule = _RESAMPLE_RULES.get(timeframe)
    if rule is None:
        return pd.DataFrame()
    df = daily.copy()
    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"])
    df = df.set_index("TIMESTAMP").sort_index()
    agg = {
        "OPEN": "first",
        "HIGH": "max",
        "LOW": "min",
        "CLOSE": "last",
        "TOTTRDQTY": "sum",
    }
    out = df.resample(rule).agg(agg).dropna(subset=["CLOSE"])
    out = out.reset_index()
    return out


# ── Indicator helpers (re-exported lightweight variants) ────────────────────


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(closes: pd.Series, period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    delta = closes.diff().dropna()
    gain = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-9)
    return round(float(100 - 100 / (1 + rs.iloc[-1])), 1)


def _macd_signal(closes: pd.Series) -> str | None:
    if len(closes) < 26:
        return None
    ema12 = closes.ewm(span=12, adjust=False).mean()
    ema26 = closes.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return "bullish" if float(macd.iloc[-1] - signal.iloc[-1]) > 0 else "bearish"


# ── Per-timeframe reading ───────────────────────────────────────────────────


def read_timeframe(frame: pd.DataFrame, timeframe: str) -> TimeframeReading:
    """Compute a single ``TimeframeReading`` from a resampled OHLCV frame."""
    reading = TimeframeReading(timeframe=timeframe, status="ok")
    if frame is None or frame.empty:
        reading.status = "missing"
        return reading
    closes = pd.to_numeric(frame["CLOSE"], errors="coerce").dropna()
    if len(closes) < 5:
        reading.status = "insufficient_history"
        reading.bars = int(len(closes))
        return reading

    reading.bars = int(len(closes))
    reading.close = round(float(closes.iloc[-1]), 2)
    reading.rsi = _rsi(closes)
    reading.macd = _macd_signal(closes)

    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    reading.ema20 = round(float(ema20.iloc[-1]), 2)
    reading.ema50 = round(float(ema50.iloc[-1]), 2)
    reading.above_ema20 = bool(reading.close > reading.ema20)
    reading.above_ema50 = bool(reading.close > reading.ema50)

    sma20 = float(closes.tail(20).mean()) if len(closes) >= 20 else None
    sma50 = float(closes.tail(50).mean()) if len(closes) >= 50 else None
    sma200 = float(closes.tail(200).mean()) if len(closes) >= 200 else None
    if sma20 is not None and sma50 is not None:
        reading.sma_stack_bullish = bool(
            reading.close > sma20 > sma50 and (sma200 is None or sma50 > sma200)
        )
        reading.sma_stack_bearish = bool(
            reading.close < sma20 < sma50 and (sma200 is None or sma50 < sma200)
        )

    period_high = float(frame["HIGH"].astype(float).tail(min(len(frame), 52)).max())
    period_low = float(frame["LOW"].astype(float).tail(min(len(frame), 52)).min())
    if period_high:
        reading.pct_from_period_high = round((reading.close / period_high - 1) * 100, 1)
    if period_low:
        reading.pct_from_period_low = round((reading.close / period_low - 1) * 100, 1)

    reading.direction = _direction_from_reading(reading)
    return reading


def _direction_from_reading(r: TimeframeReading) -> str:
    """Derive a single bullish/bearish/neutral label from an indicator stack.

    Each of {sma_stack, above_ema20, above_ema50, macd, rsi-tilt} contributes
    one vote. Majority wins; ties are neutral.
    """
    bull = 0
    bear = 0
    if r.sma_stack_bullish:
        bull += 1
    if r.sma_stack_bearish:
        bear += 1
    if r.above_ema20 is True:
        bull += 1
    elif r.above_ema20 is False:
        bear += 1
    if r.above_ema50 is True:
        bull += 1
    elif r.above_ema50 is False:
        bear += 1
    if r.macd == "bullish":
        bull += 1
    elif r.macd == "bearish":
        bear += 1
    if isinstance(r.rsi, (int, float)):
        if r.rsi >= 55:
            bull += 1
        elif r.rsi <= 45:
            bear += 1
    if bull > bear:
        return "bullish"
    if bear > bull:
        return "bearish"
    return "neutral"


# ── Confluence scorer + verdict ─────────────────────────────────────────────


def score_alignment(readings: dict[str, TimeframeReading]) -> tuple[int, str, list[str], list[str], list[str], list[str]]:
    """Aggregate per-TF directions into (score, direction, aligned, dissonant, missing, rationale)."""
    bull_score = 0
    bear_score = 0
    aligned_bull: list[str] = []
    aligned_bear: list[str] = []
    dissonant: list[str] = []
    missing: list[str] = []
    rationale: list[str] = []
    for tf, r in readings.items():
        weight = TF_WEIGHTS.get(tf, 0)
        if r.status != "ok":
            missing.append(tf)
            rationale.append(f"{tf}: {r.status} (no contribution)")
            continue
        if r.direction == "bullish":
            bull_score += weight
            aligned_bull.append(tf)
            rationale.append(f"{tf}: bullish (+{weight})")
        elif r.direction == "bearish":
            bear_score += weight
            aligned_bear.append(tf)
            rationale.append(f"{tf}: bearish (+{weight})")
        else:
            dissonant.append(tf)
            rationale.append(f"{tf}: neutral (0)")

    if bull_score > bear_score:
        direction = "bullish"
        confluence = bull_score
        aligned = aligned_bull
        dissonant = dissonant + aligned_bear
    elif bear_score > bull_score:
        direction = "bearish"
        confluence = bear_score
        aligned = aligned_bear
        dissonant = dissonant + aligned_bull
    else:
        direction = "mixed" if (aligned_bull and aligned_bear) else "neutral"
        confluence = max(bull_score, bear_score)
        aligned = []
        dissonant = aligned_bull + aligned_bear + dissonant

    return confluence, direction, aligned, dissonant, missing, rationale


def verdict_from_score(direction: str, score: int, missing_count: int, total_tfs: int) -> str:
    """Map (direction, score) → BUY / WATCH / AVOID / SELL.

    Thresholds are intentionally conservative; the higher-timeframe weights
    (M+W = 55) already gate strong calls. If too many TFs are missing the
    capability degrades to WATCH/AVOID rather than committing to BUY/SELL.
    """
    if total_tfs and missing_count >= max(2, total_tfs // 2):
        return "WATCH" if direction == "bullish" else "AVOID"
    if direction == "bullish":
        if score >= 70:
            return "BUY"
        if score >= 50:
            return "WATCH"
        return "AVOID"
    if direction == "bearish":
        if score >= 70:
            return "SELL"
        if score >= 50:
            return "AVOID"
        return "WATCH"
    return "AVOID"


# ── Top-level entry point ───────────────────────────────────────────────────


def compute_mtf(
    symbol: str,
    timeframes: Iterable[str] = DEFAULT_TIMEFRAMES,
    *,
    daily_loader=None,
    intraday_loader=None,
    days: int = 800,
) -> MTFResult:
    """Compute the full MTF stack + verdict for a symbol.

    Parameters
    ----------
    symbol
        NSE ticker (will be uppercased; caller should canonicalise first).
    timeframes
        Subset of ``DEFAULT_TIMEFRAMES``.
    daily_loader
        Callable ``(symbol, days) -> pd.DataFrame`` returning daily OHLCV with
        columns TIMESTAMP/OPEN/HIGH/LOW/CLOSE/TOTTRDQTY. Defaults to
        ``terminal.tools._load_price_history`` (imported lazily). Allows tests
        to inject fixtures.
    intraday_loader
        Callable ``(symbol, timeframe) -> dict | pd.DataFrame`` returning
        intraday OHLCV. Defaults to ``terminal.tools.get_intraday_bars``.
        Tests may pass ``lambda *_: None`` to force the missing-data path.
    days
        Daily history depth (default 800 ≈ 3 years, enough for monthly TF).
    """
    sym = (symbol or "").strip().upper()
    tfs = list(timeframes) or list(DEFAULT_TIMEFRAMES)

    if daily_loader is None:
        from terminal.tools import _load_price_history as daily_loader  # type: ignore
    if intraday_loader is None:
        try:
            from terminal.tools import get_intraday_bars as intraday_loader  # type: ignore
        except Exception:  # pragma: no cover - defensive
            intraday_loader = lambda *_a, **_k: None  # noqa: E731

    daily = pd.DataFrame()
    if any(tf in _DAILY_TFS for tf in tfs):
        try:
            daily = daily_loader(sym, days) if daily_loader is not None else pd.DataFrame()
        except Exception:
            daily = pd.DataFrame()

    readings: dict[str, TimeframeReading] = {}
    for tf in tfs:
        if tf in _DAILY_TFS:
            frame = resample_ohlcv(daily, tf) if tf != TF_DAILY else daily
            readings[tf] = read_timeframe(frame, tf)
        elif tf in _INTRADAY_TFS:
            readings[tf] = _read_intraday(sym, tf, intraday_loader)
        else:
            r = TimeframeReading(timeframe=tf, status="missing", note="unsupported timeframe")
            readings[tf] = r

    score, direction, aligned, dissonant, missing, rationale = score_alignment(readings)
    verdict = verdict_from_score(direction, score, len(missing), len(tfs))
    return MTFResult(
        symbol=sym,
        timeframes=tfs,
        readings=readings,
        confluence_score=score,
        direction=direction,
        verdict=verdict,
        aligned_tfs=aligned,
        dissonant_tfs=dissonant,
        missing_tfs=missing,
        rationale=rationale,
    )


def _read_intraday(symbol: str, timeframe: str, loader) -> TimeframeReading:
    """Adapt ``get_intraday_bars`` output (dict or DataFrame) to a TimeframeReading."""
    try:
        raw = loader(symbol, timeframe=timeframe) if loader else None
    except Exception:
        raw = None
    frame: pd.DataFrame | None = None
    if isinstance(raw, pd.DataFrame):
        frame = raw
    elif isinstance(raw, dict):
        bars = raw.get("bars") or raw.get("data") or raw.get("rows")
        if isinstance(bars, list) and bars:
            frame = pd.DataFrame(bars)
        elif raw.get("error"):
            r = TimeframeReading(timeframe=timeframe, status="missing", note=str(raw.get("error"))[:120])
            return r
    if frame is None or frame.empty:
        return TimeframeReading(timeframe=timeframe, status="missing")
    # Normalise column names — intraday bars may come back lower-case.
    rename = {
        "timestamp": "TIMESTAMP",
        "ts": "TIMESTAMP",
        "open": "OPEN",
        "high": "HIGH",
        "low": "LOW",
        "close": "CLOSE",
        "volume": "TOTTRDQTY",
        "vol": "TOTTRDQTY",
    }
    frame = frame.rename(columns={k: v for k, v in rename.items() if k in frame.columns})
    required = {"OPEN", "HIGH", "LOW", "CLOSE"}
    if not required.issubset(frame.columns):
        return TimeframeReading(timeframe=timeframe, status="missing", note="intraday bars missing OHLC columns")
    return read_timeframe(frame, timeframe)


__all__ = [
    "DEFAULT_TIMEFRAMES",
    "TF_DAILY",
    "TF_WEEKLY",
    "TF_MONTHLY",
    "TF_60M",
    "TF_15M",
    "TF_WEIGHTS",
    "TimeframeReading",
    "MTFResult",
    "resample_ohlcv",
    "read_timeframe",
    "score_alignment",
    "verdict_from_score",
    "compute_mtf",
]
