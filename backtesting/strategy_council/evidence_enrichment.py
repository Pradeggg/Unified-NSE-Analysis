"""Evidence pack enrichment with regime, factor exposure, and microstructure.

This module extends :func:`build_evidence_pack` with purely-computed signals
that downstream critics and strategists can consume without requiring new
external API integrations:

* **Regime** — bull / bear / sideways classification using a 200-bar SMA of
  the close plus its slope. Falls back to a shorter window when 200 bars are
  unavailable.
* **Factor exposure** — rolling-window beta of close-to-close returns against
  an optional benchmark series. If no benchmark is provided, the stub records
  ``available=False`` so downstream critics can skip cleanly.
* **Microstructure** — ATR-percent, average dollar volume, and high-low
  spread statistics derived from the EOD frame itself.

All enrichments are best-effort: failures leave the underlying pack untouched
and append a descriptive ``source_trail`` line so the audit trail captures
why a field is missing.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from backtesting.strategy_council.evidence import (
    build_strategy_council_evidence_pack,
)
from backtesting.strategy_council.types import EvidencePack


REGIME_BULL = "bull"
REGIME_BEAR = "bear"
REGIME_SIDEWAYS = "sideways"


def _safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(result):
        return None
    return result


def _normalize_closes(eod: pd.DataFrame) -> pd.Series:
    if "close" not in eod.columns:
        return pd.Series(dtype="float64")
    closes = pd.to_numeric(eod["close"], errors="coerce").dropna()
    return closes.reset_index(drop=True)


def detect_regime(eod: pd.DataFrame, *, window: int = 200, slope_window: int = 20) -> dict[str, Any]:
    """Classify the latest bar as bull, bear, or sideways.

    The decision uses:
      * ``close vs SMA(window)`` — directional bias
      * sign of ``SMA(window).diff(slope_window)`` — trend persistence

    Returns a dict with ``regime``, ``close``, ``sma``, ``slope``, and
    ``bars_used``. If the frame is too short, the function still returns a
    classification using the available history (annotated by ``bars_used``).
    """

    closes = _normalize_closes(eod)
    if closes.empty:
        return {"regime": REGIME_SIDEWAYS, "available": False, "reason": "no_close_data"}

    effective_window = min(window, len(closes))
    sma = closes.rolling(window=effective_window, min_periods=effective_window).mean()
    if sma.dropna().empty:
        return {
            "regime": REGIME_SIDEWAYS,
            "available": False,
            "reason": "insufficient_history",
            "bars_used": int(len(closes)),
        }

    last_close = float(closes.iloc[-1])
    last_sma = float(sma.iloc[-1])
    slope_lookback = min(slope_window, len(sma.dropna()) - 1)
    if slope_lookback <= 0:
        slope = 0.0
    else:
        slope = float(sma.iloc[-1] - sma.iloc[-1 - slope_lookback])

    bias = (last_close - last_sma) / last_sma * 100.0 if last_sma else 0.0
    if bias > 2.0 and slope >= 0:
        regime = REGIME_BULL
    elif bias < -2.0 and slope <= 0:
        regime = REGIME_BEAR
    else:
        regime = REGIME_SIDEWAYS

    return {
        "regime": regime,
        "available": True,
        "close": last_close,
        "sma": last_sma,
        "slope": slope,
        "bias_pct": round(bias, 4),
        "window": effective_window,
        "bars_used": int(len(closes)),
    }


def compute_factor_exposure(
    eod: pd.DataFrame,
    *,
    benchmark: pd.Series | None = None,
    window: int = 60,
) -> dict[str, Any]:
    """Estimate beta vs an optional benchmark over a trailing window.

    Returns ``{"available": False, ...}`` when a benchmark is not supplied or
    when overlap is insufficient. When available, returns ``beta``,
    ``correlation``, and ``window`` so :class:`FactorBasedCritic` can react.
    """

    closes = _normalize_closes(eod)
    if closes.empty:
        return {"available": False, "reason": "no_close_data"}
    if benchmark is None or benchmark.empty:
        return {"available": False, "reason": "no_benchmark_series"}

    bench = pd.to_numeric(benchmark, errors="coerce").dropna().reset_index(drop=True)
    overlap = min(len(closes), len(bench))
    if overlap < max(window // 2, 20):
        return {"available": False, "reason": "insufficient_overlap", "overlap": int(overlap)}

    sym_ret = closes.iloc[-overlap:].pct_change().dropna()
    bench_ret = bench.iloc[-overlap:].pct_change().dropna()
    join = pd.concat([sym_ret, bench_ret], axis=1, join="inner").dropna()
    if len(join) < max(window // 2, 20):
        return {"available": False, "reason": "insufficient_return_overlap", "overlap": int(len(join))}

    join.columns = ["sym", "bench"]
    used = join.tail(window)
    var_bench = float(used["bench"].var())
    if var_bench == 0 or pd.isna(var_bench):
        return {"available": False, "reason": "benchmark_zero_variance"}

    cov = float(used["sym"].cov(used["bench"]))
    beta = cov / var_bench
    corr = float(used["sym"].corr(used["bench"]))
    return {
        "available": True,
        "beta": round(beta, 4),
        "correlation": round(corr if pd.notna(corr) else 0.0, 4),
        "window": int(len(used)),
    }


def compute_microstructure(eod: pd.DataFrame, *, atr_window: int = 14) -> dict[str, Any]:
    """Compute ATR-percent, average dollar volume, and HL spread stats."""

    if eod.empty:
        return {"available": False, "reason": "empty_frame"}

    cols = {c.lower(): c for c in eod.columns}
    high = pd.to_numeric(eod[cols.get("high", "high")], errors="coerce") if "high" in cols else None
    low = pd.to_numeric(eod[cols.get("low", "low")], errors="coerce") if "low" in cols else None
    close = pd.to_numeric(eod[cols.get("close", "close")], errors="coerce") if "close" in cols else None
    volume = pd.to_numeric(eod[cols.get("volume", "volume")], errors="coerce") if "volume" in cols else None

    if close is None or close.dropna().empty:
        return {"available": False, "reason": "no_close"}

    out: dict[str, Any] = {"available": True}

    if high is not None and low is not None:
        spread = (high - low) / close.replace(0, pd.NA)
        spread = spread.dropna()
        if not spread.empty:
            out["avg_hl_spread_pct"] = round(float(spread.mean()) * 100.0, 4)
            out["latest_hl_spread_pct"] = round(float(spread.iloc[-1]) * 100.0, 4)

        prev_close = close.shift(1)
        tr = pd.concat(
            [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(window=atr_window, min_periods=atr_window).mean()
        if not atr.dropna().empty:
            latest_atr = float(atr.dropna().iloc[-1])
            latest_close = float(close.dropna().iloc[-1])
            if latest_close > 0:
                out["atr_pct"] = round(latest_atr / latest_close * 100.0, 4)
                out["atr_window"] = atr_window

    if volume is not None and not volume.dropna().empty:
        recent_close = close.tail(min(len(close), 30)).dropna()
        recent_volume = volume.tail(min(len(volume), 30)).dropna()
        if not recent_close.empty and not recent_volume.empty:
            joined = pd.concat([recent_close, recent_volume], axis=1, join="inner").dropna()
            if not joined.empty:
                joined.columns = ["close", "volume"]
                avg_dollar = float((joined["close"] * joined["volume"]).mean())
                out["avg_dollar_volume_30d"] = round(avg_dollar, 2)

    return out


def enrich_with_market_signals(
    pack: EvidencePack,
    eod: pd.DataFrame,
    *,
    benchmark: pd.Series | None = None,
) -> EvidencePack:
    """Attach regime, factor exposure, and microstructure to an existing pack."""

    try:
        regime = detect_regime(eod)
        pack.market["regime"] = regime
        if regime.get("available"):
            pack.freshness["regime"] = regime["regime"]
            pack.source_trail.append(f"regime: {regime['regime']} (bias_pct={regime.get('bias_pct')})")
        else:
            pack.missing.append("regime")
            pack.source_trail.append(f"regime: unavailable ({regime.get('reason')})")
    except Exception as exc:  # pragma: no cover - defensive
        pack.missing.append("regime")
        pack.source_trail.append(f"regime: ERROR: {exc}")

    try:
        factor = compute_factor_exposure(eod, benchmark=benchmark)
        pack.market["factor_exposure"] = factor
        if factor.get("available"):
            pack.freshness["factor_exposure"] = "available"
            pack.source_trail.append(f"factor_exposure: beta={factor.get('beta')}")
        else:
            pack.missing.append("factor_exposure")
            pack.source_trail.append(f"factor_exposure: unavailable ({factor.get('reason')})")
    except Exception as exc:  # pragma: no cover - defensive
        pack.missing.append("factor_exposure")
        pack.source_trail.append(f"factor_exposure: ERROR: {exc}")

    try:
        micro = compute_microstructure(eod)
        pack.market["microstructure"] = micro
        if micro.get("available"):
            pack.freshness["microstructure"] = "available"
            pack.source_trail.append(
                "microstructure: ok"
                + (f" (atr_pct={micro['atr_pct']})" if "atr_pct" in micro else "")
            )
        else:
            pack.missing.append("microstructure")
            pack.source_trail.append(f"microstructure: unavailable ({micro.get('reason')})")
    except Exception as exc:  # pragma: no cover - defensive
        pack.missing.append("microstructure")
        pack.source_trail.append(f"microstructure: ERROR: {exc}")

    return pack


def build_enriched_evidence_pack(
    symbol: str,
    eod: pd.DataFrame,
    *,
    benchmark: pd.Series | None = None,
    project_root=None,
) -> EvidencePack:
    """Build the base pack via existing helpers, then layer market signals."""

    pack = build_strategy_council_evidence_pack(symbol, project_root=project_root)
    return enrich_with_market_signals(pack, eod, benchmark=benchmark)


__all__ = [
    "REGIME_BULL",
    "REGIME_BEAR",
    "REGIME_SIDEWAYS",
    "detect_regime",
    "compute_factor_exposure",
    "compute_microstructure",
    "enrich_with_market_signals",
    "build_enriched_evidence_pack",
]
