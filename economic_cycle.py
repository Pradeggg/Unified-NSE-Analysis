#!/usr/bin/env python3
"""Economic cycle phase detection and sector/stock positioning helpers.

The detector intentionally uses the macro proxies that already exist in
``fetch_macro_proxies.py``. When richer PMI/IIP/GST data is added later, this
module can absorb those inputs without changing report integration points.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


CYCLE_PHASES: dict[str, dict[str, Any]] = {
    "EARLY_EXPANSION": {
        "definition": "Growth improving with constructive market trend and contained inflation/rates.",
        "preferred_sectors": ["Banking", "Consumer Discretionary", "Real Estate", "Auto"],
        "avoid_sectors": ["Utilities", "FMCG"],
    },
    "LATE_EXPANSION": {
        "definition": "Growth firm but inflation, commodities, or rates are rising.",
        "preferred_sectors": ["Energy", "Metals", "Capital Goods"],
        "avoid_sectors": ["Banking", "NBFC", "Real Estate"],
    },
    "SLOWDOWN": {
        "definition": "Market trend weakens while volatility, inflation, rates, or input costs rise.",
        "preferred_sectors": ["FMCG", "Pharma", "IT"],
        "avoid_sectors": ["Metals", "Auto", "Real Estate"],
    },
    "RECOVERY": {
        "definition": "Risk indicators ease and market trend starts improving from a weak base.",
        "preferred_sectors": ["Banking", "Capital Goods", "Infrastructure", "Cement"],
        "avoid_sectors": ["Defensives"],
    },
}

FAVOURED_ADJUSTMENT = 4
UNFAVOURED_ADJUSTMENT = -3


def _clean_text(value: object) -> str:
    return str(value or "").strip().lower()


def _find_signal(macro_signals: pd.DataFrame, *needles: str) -> dict[str, Any]:
    if macro_signals is None or macro_signals.empty or "indicator" not in macro_signals.columns:
        return {}
    indicator = macro_signals["indicator"].astype(str).str.lower()
    mask = pd.Series(True, index=macro_signals.index)
    for needle in needles:
        mask &= indicator.str.contains(needle.lower(), regex=False, na=False)
    if not mask.any():
        return {}
    row = macro_signals[mask].iloc[-1]
    return row.to_dict()


def _signal_score(row: dict[str, Any]) -> float:
    try:
        value = float(row.get("signal_score", 0) or 0)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(value):
        return 0.0
    return value


def _trend(row: dict[str, Any]) -> str:
    return str(row.get("trend", "") or "").upper()


def _confidence(best: float, second: float) -> float:
    if best <= 0:
        return 0.35
    spread = max(0.0, best - second)
    return round(min(0.9, 0.55 + spread * 0.08), 2)


def detect_economic_cycle_phase(macro_signals: pd.DataFrame, market_regime: str = "ROTATION") -> dict[str, Any]:
    """Detect current economic cycle phase from cached macro proxy signals.

    Returns a stable dictionary consumed by the sector report:
    ``cycle_phase``, ``confidence``, ``preferred_sectors``, ``avoid_sectors``,
    ``regime_cycle_alignment``, and ``evidence``.
    """
    regime = str(market_regime or "ROTATION").upper()
    signals = {
        "nifty": _find_signal(macro_signals, "nifty"),
        "vix": _find_signal(macro_signals, "vix"),
        "cpi": _find_signal(macro_signals, "cpi"),
        "rate": _find_signal(macro_signals, "interest"),
        "us10y": _find_signal(macro_signals, "10y"),
        "crude": _find_signal(macro_signals, "brent", "crude"),
        "copper": _find_signal(macro_signals, "copper"),
        "fx": _find_signal(macro_signals, "usd/inr"),
        "pmi": _find_signal(macro_signals, "pmi"),
        "iip": _find_signal(macro_signals, "iip"),
        "gst": _find_signal(macro_signals, "gst"),
    }

    nifty = _signal_score(signals["nifty"])
    vix = _signal_score(signals["vix"])
    cpi = _signal_score(signals["cpi"])
    rate = _signal_score(signals["rate"]) or _signal_score(signals["us10y"])
    crude = _signal_score(signals["crude"])
    copper = _signal_score(signals["copper"])
    fx = _signal_score(signals["fx"])
    pmi = _signal_score(signals["pmi"])
    iip = _signal_score(signals["iip"])
    gst = _signal_score(signals["gst"])

    growth = nifty * 0.45 + copper * 0.20 + pmi * 0.15 + iip * 0.10 + gst * 0.10
    risk_easing = vix * 0.35 + rate * 0.20 + crude * 0.20 + fx * 0.15 + cpi * 0.10
    cost_pressure = -1 * (cpi * 0.30 + crude * 0.30 + rate * 0.25 + fx * 0.15)

    scores = {
        "RECOVERY": max(0.0, growth) * 1.0 + max(0.0, risk_easing) * 1.1,
        "EARLY_EXPANSION": max(0.0, growth) * 1.2 + max(0.0, risk_easing) * 0.5,
        "LATE_EXPANSION": max(0.0, growth) * 0.8 + max(0.0, cost_pressure) * 1.0,
        "SLOWDOWN": max(0.0, -growth) * 1.0 + max(0.0, -risk_easing) * 0.9,
    }

    if regime == "BEAR_TREND":
        scores["SLOWDOWN"] += 0.8
        scores["RECOVERY"] -= 0.2
    elif regime == "BULL_TREND":
        scores["EARLY_EXPANSION"] += 0.4
        scores["RECOVERY"] += 0.2
    elif regime == "ROTATION":
        scores["RECOVERY"] += 0.3 if risk_easing > 0 and growth >= 0 else 0.0

    if _trend(signals["vix"]) == "RISING" and nifty < 0:
        scores["SLOWDOWN"] += 0.6
    if _trend(signals["vix"]) == "FALLING" and nifty > 0:
        scores["RECOVERY"] += 0.5
    if cost_pressure > 0 and growth > 0:
        scores["LATE_EXPANSION"] += 0.4
    scores = {key: max(0.0, value) for key, value in scores.items()}

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    phase = ranked[0][0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    phase_def = CYCLE_PHASES[phase]

    alignment = "MIXED"
    if phase == "SLOWDOWN" and regime == "BEAR_TREND":
        alignment = "ALIGNED_RISK_OFF"
    elif phase in {"EARLY_EXPANSION", "RECOVERY"} and regime == "BULL_TREND":
        alignment = "ALIGNED_RISK_ON"
    elif phase in {"EARLY_EXPANSION", "RECOVERY"} and regime in {"BEAR_TREND", "ROTATION"}:
        alignment = "EARLY_MARKET_RECOVERY"
    elif phase == "SLOWDOWN" and regime == "BULL_TREND":
        alignment = "MARKET_AHEAD_OF_FUNDAMENTALS"

    evidence = {
        "growth_score": round(growth, 2),
        "risk_easing_score": round(risk_easing, 2),
        "cost_pressure_score": round(cost_pressure, 2),
        "market_regime": regime,
    }

    return {
        "cycle_phase": phase,
        "confidence": _confidence(ranked[0][1], second_score),
        "preferred_sectors": list(phase_def["preferred_sectors"]),
        "avoid_sectors": list(phase_def["avoid_sectors"]),
        "regime_cycle_alignment": alignment,
        "definition": phase_def["definition"],
        "scores": {key: round(value, 2) for key, value in scores.items()},
        "evidence": evidence,
    }


def _sector_tag(sector: object, cycle_info: dict[str, Any]) -> str:
    text = _clean_text(sector)
    preferred = [_clean_text(s) for s in cycle_info.get("preferred_sectors", [])]
    avoid = [_clean_text(s) for s in cycle_info.get("avoid_sectors", [])]
    if any(item and item in text for item in preferred):
        return "CYCLE_FAVOURED"
    if any(item and item in text for item in avoid):
        return "CYCLE_UNFAVOURED"
    return "CYCLE_NEUTRAL"


def _tag_adjustment(tag: str) -> int:
    if tag == "CYCLE_FAVOURED":
        return FAVOURED_ADJUSTMENT
    if tag == "CYCLE_UNFAVOURED":
        return UNFAVOURED_ADJUSTMENT
    return 0


def apply_cycle_to_sectors(sector_rank: pd.DataFrame, cycle_info: dict[str, Any]) -> pd.DataFrame:
    """Tag sectors and adjust ``ROTATION_SCORE`` using the detected cycle."""
    out = sector_rank.copy()
    if out.empty:
        return out
    phase = str(cycle_info.get("cycle_phase", "UNKNOWN") or "UNKNOWN")
    out["CYCLE_PHASE"] = phase
    out["CYCLE_TAG"] = out["SECTOR_NAME"].apply(lambda value: _sector_tag(value, cycle_info))
    out["CYCLE_ADJUSTMENT"] = out["CYCLE_TAG"].apply(_tag_adjustment)
    if "ROTATION_SCORE_BASE" not in out.columns:
        out["ROTATION_SCORE_BASE"] = pd.to_numeric(out.get("ROTATION_SCORE", 0), errors="coerce").fillna(0)
    out["ROTATION_SCORE"] = (
        pd.to_numeric(out["ROTATION_SCORE_BASE"], errors="coerce").fillna(0)
        + pd.to_numeric(out["CYCLE_ADJUSTMENT"], errors="coerce").fillna(0)
    ).round(2)
    return out.sort_values("ROTATION_SCORE", ascending=False).reset_index(drop=True)


def apply_cycle_to_candidates(candidates: pd.DataFrame, cycle_info: dict[str, Any]) -> pd.DataFrame:
    """Tag candidate stocks and adjust ``INVESTMENT_SCORE`` using the detected cycle."""
    out = candidates.copy()
    if out.empty:
        return out
    phase = str(cycle_info.get("cycle_phase", "UNKNOWN") or "UNKNOWN")
    out["CYCLE_PHASE"] = phase
    out["CYCLE_TAG"] = out["SECTOR_NAME"].apply(lambda value: _sector_tag(value, cycle_info))
    out["CYCLE_ADJUSTMENT"] = out["CYCLE_TAG"].apply(_tag_adjustment)
    if "INVESTMENT_SCORE_BASE" not in out.columns:
        out["INVESTMENT_SCORE_BASE"] = pd.to_numeric(out.get("INVESTMENT_SCORE", 0), errors="coerce").fillna(0)
    out["INVESTMENT_SCORE"] = (
        pd.to_numeric(out["INVESTMENT_SCORE_BASE"], errors="coerce").fillna(0)
        + pd.to_numeric(out["CYCLE_ADJUSTMENT"], errors="coerce").fillna(0)
    ).round(2)
    sort_cols = [c for c in ["INVESTMENT_SCORE", "TECHNICAL_SCORE", "RELATIVE_STRENGTH"] if c in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols, ascending=False).reset_index(drop=True)
    return out


def cycle_badge_html(cycle_info: dict[str, Any]) -> str:
    """Render a compact economic cycle banner for the HTML report."""
    import html

    phase = str(cycle_info.get("cycle_phase", "UNKNOWN") or "UNKNOWN")
    confidence = float(cycle_info.get("confidence", 0) or 0)
    alignment = str(cycle_info.get("regime_cycle_alignment", "MIXED") or "MIXED")
    definition = str(cycle_info.get("definition", "") or "")
    preferred = ", ".join(cycle_info.get("preferred_sectors", [])[:4])
    avoid = ", ".join(cycle_info.get("avoid_sectors", [])[:4])
    cls = {
        "RECOVERY": ("#ecfdf5", "#047857"),
        "EARLY_EXPANSION": ("#eef2ff", "#4338ca"),
        "LATE_EXPANSION": ("#fff7ed", "#c2410c"),
        "SLOWDOWN": ("#fef2f2", "#b91c1c"),
    }.get(phase, ("#f8fafc", "#475569"))
    return (
        f'<div style="display:inline-flex;gap:8px;align-items:center;flex-wrap:wrap;'
        f'background:{cls[0]};color:{cls[1]};border:1px solid rgba(0,0,0,.08);'
        f'border-radius:8px;padding:8px 10px;margin:4px 8px 4px 0;font-size:12px">'
        f'<strong>Economic Cycle: {html.escape(phase.replace("_", " "))}</strong>'
        f'<span>{confidence:.0%} confidence</span>'
        f'<span>{html.escape(alignment.replace("_", " ").title())}</span>'
        f'<span title="{html.escape(definition)}">Favours: {html.escape(preferred or "Neutral")}</span>'
        f'<span>Avoids: {html.escape(avoid or "None")}</span>'
        f'</div>'
    )
