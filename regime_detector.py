#!/usr/bin/env python3
"""Market regime detector using Gaussian HMM on Nifty500 daily features.

Detects 4 regimes:
  BULL_TREND  — sustained uptrend, low vol, broad participation
  ROTATION    — mixed returns, sector churn, moderate vol
  CHOP        — low directional movement, high noise
  BEAR_TREND  — sustained downtrend, high vol, narrow breadth

Output regimes gate signal weights in sector_rotation_report.py:
  - Momentum signals (RSI breakouts): 1.5x in BULL, 0.4x in CHOP, 0.2x in BEAR
  - Sector RS signals: 2.0x in ROTATION
  - Fundamental quality: 2.5x in BEAR (defensive tilt)
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
INDEX_CSV = ROOT / "data" / "nse_index_data.csv"
REGIME_HISTORY = ROOT / "data" / "regime_history.csv"
REGIME_CACHE = ROOT / "data" / "_regime_cache.json"
BREADTH_CSV = ROOT / "reports" / "latest" / "index_intelligence.csv"
CACHE_TTL_HOURS = 6

# Regime defensiveness rank (higher = more defensive)
_REGIME_RANK: dict[str, int] = {"BULL_TREND": 0, "ROTATION": 1, "CHOP": 2, "BEAR_TREND": 3}

REGIME_LABELS = {0: "BULL_TREND", 1: "ROTATION", 2: "CHOP", 3: "BEAR_TREND"}

# Signal weight multipliers per regime
REGIME_WEIGHTS: dict[str, dict[str, float]] = {
    "BULL_TREND": {
        "momentum":    1.5,
        "sector_rs":   1.0,
        "mean_revert": 0.5,
        "fundamental": 1.0,
        "defensive":   0.5,
    },
    "ROTATION": {
        "momentum":    1.2,
        "sector_rs":   2.0,
        "mean_revert": 0.8,
        "fundamental": 1.5,
        "defensive":   0.8,
    },
    "CHOP": {
        "momentum":    0.4,
        "sector_rs":   0.8,
        "mean_revert": 1.5,
        "fundamental": 2.0,
        "defensive":   1.5,
    },
    "BEAR_TREND": {
        "momentum":    0.2,
        "sector_rs":   0.5,
        "mean_revert": 1.0,
        "fundamental": 2.5,
        "defensive":   3.0,
    },
}


def _load_nifty500_series(lookback_days: int = 300) -> pd.DataFrame:
    """Load Nifty500 close prices from the index CSV."""
    if not INDEX_CSV.exists():
        raise FileNotFoundError(f"Index data not found: {INDEX_CSV}")
    df = pd.read_csv(INDEX_CSV, low_memory=False)
    # Normalise column names
    df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]
    # Find Nifty500 rows
    name_col = next((c for c in df.columns if "NAME" in c or "INDEX" in c or "SYMBOL" in c), None)
    date_col = next((c for c in df.columns if "DATE" in c or "TIMESTAMP" in c), None)
    close_col = next((c for c in df.columns if c == "CLOSE"), None)
    if not all([name_col, date_col, close_col]):
        raise ValueError(f"Cannot find required columns. Found: {df.columns.tolist()}")
    n500 = df[df[name_col].astype(str).str.contains("Nifty 500|NIFTY500|Nifty500", case=False, na=False)].copy()
    if n500.empty:
        # Fall back: use first available index
        first_name = df[name_col].dropna().iloc[0]
        n500 = df[df[name_col] == first_name].copy()
    n500[date_col] = pd.to_datetime(n500[date_col], errors="coerce")
    n500 = n500.dropna(subset=[date_col, close_col]).sort_values(date_col)
    n500 = n500.tail(lookback_days)
    return n500[[date_col, close_col]].rename(columns={date_col: "DATE", close_col: "CLOSE"}).reset_index(drop=True)


def _build_features(prices: pd.DataFrame) -> np.ndarray:
    """
    Build feature matrix for HMM from price series.
    Features: daily return, 10d realised vol, 20d momentum, vol ratio (5d/20d vol).
    """
    close = prices["CLOSE"].astype(float)
    ret = close.pct_change().fillna(0)
    vol_10 = ret.rolling(10).std().fillna(ret.std())
    mom_20 = close.pct_change(20).fillna(0)
    vol_ratio = (ret.rolling(5).std() / (ret.rolling(20).std() + 1e-9)).fillna(1.0)

    features = np.column_stack([
        ret.values,
        vol_10.values,
        mom_20.values,
        vol_ratio.values,
    ])
    return features


def _assign_regime_labels(hidden_states: np.ndarray, features: np.ndarray) -> dict[int, str]:
    """
    Map raw HMM state integers to semantic labels based on mean feature values.
    State with highest mean return → BULL_TREND
    State with lowest mean return → BEAR_TREND
    Among remaining: higher vol ratio → CHOP, lower → ROTATION
    """
    n_states = len(set(hidden_states))
    state_stats = {}
    for s in range(n_states):
        mask = hidden_states == s
        if mask.sum() == 0:
            continue
        state_stats[s] = {
            "mean_ret": features[mask, 0].mean(),
            "mean_vol": features[mask, 1].mean(),
            "vol_ratio": features[mask, 3].mean(),
        }

    sorted_by_ret = sorted(state_stats.keys(), key=lambda s: state_stats[s]["mean_ret"])
    mapping = {}
    if len(sorted_by_ret) >= 4:
        mapping[sorted_by_ret[-1]] = "BULL_TREND"
        mapping[sorted_by_ret[0]] = "BEAR_TREND"
        middle = sorted_by_ret[1:-1]
        mid_sorted = sorted(middle, key=lambda s: state_stats[s]["vol_ratio"])
        mapping[mid_sorted[0]] = "ROTATION"
        mapping[mid_sorted[-1]] = "CHOP"
    elif len(sorted_by_ret) == 3:
        mapping[sorted_by_ret[-1]] = "BULL_TREND"
        mapping[sorted_by_ret[0]] = "BEAR_TREND"
        mapping[sorted_by_ret[1]] = "ROTATION"
    elif len(sorted_by_ret) == 2:
        mapping[sorted_by_ret[-1]] = "BULL_TREND"
        mapping[sorted_by_ret[0]] = "BEAR_TREND"
    else:
        mapping[sorted_by_ret[0]] = "BULL_TREND"
    return mapping


def _breadth_regime_override(base_regime: str, breadth_csv: Path = BREADTH_CSV) -> str | None:
    """
    Apply cross-index breadth divergence as a regime override.

    Rules (B1 integration — backlog spec):
      Nifty50 STRONG/HEALTHY + SmallCap WEAK/BEARISH → ROTATION
        (large-caps leading, breadth narrow = selective not bull)
      Both Nifty50 + SmallCap BEARISH → BEAR_TREND
      Both Nifty50 + SmallCap STRONG → BULL_TREND

    Only overrides toward a more defensive regime (never upgrades).
    Returns override regime string, or None if no clear signal.
    """
    if not breadth_csv.exists():
        return None
    try:
        df = pd.read_csv(breadth_csv)
        by_index = df.set_index("INDEX_NAME")["breadth_signal"].to_dict()
        nifty50_sig = by_index.get("NIFTY 50", "NO_DATA")
        smallcap_sig = by_index.get("NIFTY SMALLCAP 250", by_index.get("NIFTY SMLCAP 250", "NO_DATA"))
        if nifty50_sig == "NO_DATA" or smallcap_sig == "NO_DATA":
            return None
        # Determine breadth-implied regime
        if nifty50_sig in ("STRONG", "HEALTHY") and smallcap_sig in ("WEAK", "BEARISH"):
            breadth_regime = "ROTATION"
        elif nifty50_sig == "BEARISH" and smallcap_sig == "BEARISH":
            breadth_regime = "BEAR_TREND"
        elif nifty50_sig == "STRONG" and smallcap_sig in ("STRONG", "HEALTHY"):
            breadth_regime = "BULL_TREND"
        else:
            return None
        # Only override toward more defensive (never upgrade via breadth alone)
        if _REGIME_RANK.get(breadth_regime, 1) > _REGIME_RANK.get(base_regime, 0):
            return breadth_regime
        return None
    except Exception:
        return None


def detect_regime(lookback_days: int = 300, n_states: int = 4) -> dict:
    """
    Fit a Gaussian HMM on Nifty500 returns and return current regime.

    Returns dict:
      {
        "current_regime": "ROTATION",
        "confidence": 0.81,
        "regime_duration_days": 12,
        "previous_regime": "BULL_TREND",
        "weights": {...},        # signal weight multipliers
        "regime_history": [...], # last 30 days [{date, regime}, ...]
      }
    """
    # Check cache
    if REGIME_CACHE.exists():
        try:
            cached = json.loads(REGIME_CACHE.read_text())
            cache_age = (datetime.now() - datetime.fromisoformat(cached["cached_at"])).total_seconds() / 3600
            if cache_age < CACHE_TTL_HOURS:
                return cached
        except Exception:
            pass

    # Run HMM in a subprocess with a hard timeout to avoid C-extension hangs
    prices = _load_nifty500_series(lookback_days)
    if len(prices) < 60:
        return _regime_rule_based()

    try:
        import subprocess as _sp, sys as _sys, tempfile as _tf, pickle as _pk
        features = _build_features(prices)
        with _tf.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            feat_path = f.name
            _pk.dump(features, f)
        hmm_script = (
            "import pickle, warnings, numpy as np\n"
            "warnings.filterwarnings('ignore')\n"
            "from hmmlearn.hmm import GaussianHMM\n"
            f"features = pickle.load(open({feat_path!r}, 'rb'))\n"
            "m = GaussianHMM(n_components=4, covariance_type='diag', n_iter=50, random_state=42, tol=1e-3)\n"
            "m.fit(features)\n"
            "states = m.predict(features)\n"
            "probs = m.predict_proba(features)\n"
            "print(int(states[-1]), float(probs[-1].max()), *[float(features[states==s, 0].mean()) for s in range(4)])\n"
        )
        # Prefer the project venv Python so hmmlearn is guaranteed to be available
        _venv_py = ROOT / ".venv" / "bin" / "python3"
        _python = str(_venv_py) if _venv_py.exists() else _sys.executable
        result = _sp.run(
            [_python, "-c", hmm_script],
            capture_output=True, text=True, timeout=20,
        )
        import os as _os
        try:
            _os.unlink(feat_path)
        except OSError:
            pass
        if result.returncode != 0:
            raise RuntimeError(f"HMM subprocess failed: {result.stderr[:100]}")
        parts = result.stdout.strip().split()
        raw_state = int(parts[0])
        confidence = float(parts[1])
        mean_rets = [float(p) for p in parts[2:6]]
        sorted_states = sorted(range(4), key=lambda i: mean_rets[i])
        label_map = {
            sorted_states[-1]: "BULL_TREND",
            sorted_states[0]:  "BEAR_TREND",
            sorted_states[1]:  "ROTATION",
            sorted_states[2]:  "CHOP",
        }
        current_regime = label_map.get(raw_state, "ROTATION")
    except Exception:
        return _regime_rule_based()

    # Build duration estimate from rule-based on recent data
    rb = _regime_rule_based()
    duration = rb.get("regime_duration_days", 1)
    prev_regime = rb.get("previous_regime", "UNKNOWN")
    history = rb.get("regime_history", [])

    # Apply cross-index breadth divergence override (B1 integration)
    breadth_override = _breadth_regime_override(current_regime)
    if breadth_override:
        prev_regime = current_regime
        current_regime = breadth_override

    result = {
        "current_regime": current_regime,
        "confidence": round(confidence, 3),
        "regime_duration_days": duration,
        "previous_regime": prev_regime,
        "weights": REGIME_WEIGHTS.get(current_regime, REGIME_WEIGHTS["ROTATION"]),
        "regime_history": history,
        "cached_at": datetime.now().isoformat(),
        "method": "hmm",
        "breadth_override": breadth_override is not None,
    }
    REGIME_CACHE.write_text(json.dumps(result, indent=2))
    return result


def _regime_rule_based() -> dict:
    """Fallback rule-based regime detection when hmmlearn is not available."""
    try:
        prices = _load_nifty500_series(60)
        close = prices["CLOSE"].astype(float)
        ret_20 = float((close.iloc[-1] / close.iloc[-20] - 1) * 100) if len(close) >= 20 else 0.0
        ret_5 = float((close.iloc[-1] / close.iloc[-5] - 1) * 100) if len(close) >= 5 else 0.0
        vol_20 = float(close.pct_change().tail(20).std() * 100)

        if ret_20 > 4 and vol_20 < 1.2:
            regime = "BULL_TREND"
        elif ret_20 < -4 or (ret_20 < 0 and vol_20 > 1.5):
            regime = "BEAR_TREND"
        elif abs(ret_20) < 2 and vol_20 > 1.0:
            regime = "CHOP"
        else:
            regime = "ROTATION"
        confidence = 0.60
    except Exception:
        regime = "ROTATION"
        confidence = 0.50
        ret_5 = 0.0

    return {
        "current_regime": regime,
        "confidence": confidence,
        "regime_duration_days": 1,
        "previous_regime": "UNKNOWN",
        "weights": REGIME_WEIGHTS.get(regime, REGIME_WEIGHTS["ROTATION"]),
        "regime_history": [],
        "cached_at": datetime.now().isoformat(),
        "method": "rule_based",
    }


def _persist_regime(history: list[dict], prices: pd.DataFrame) -> None:
    """Append new regime observations to the history CSV."""
    try:
        existing = pd.read_csv(REGIME_HISTORY) if REGIME_HISTORY.exists() else pd.DataFrame(columns=["date", "regime"])
        new_rows = pd.DataFrame(history)
        combined = pd.concat([existing, new_rows]).drop_duplicates("date", keep="last")
        combined = combined.sort_values("date").tail(500)
        combined.to_csv(REGIME_HISTORY, index=False)
    except Exception:
        pass


def regime_badge_html(regime_info: dict) -> str:
    """Return an HTML banner string for the report header."""
    regime = regime_info.get("current_regime", "UNKNOWN")
    conf = regime_info.get("confidence", 0)
    dur = regime_info.get("regime_duration_days", 1)
    prev = regime_info.get("previous_regime", "")
    method = regime_info.get("method", "hmm")

    color_map = {
        "BULL_TREND":  ("#dcfce7", "#14532d", "🟢"),
        "ROTATION":    ("#fef3c7", "#92400e", "🔄"),
        "CHOP":        ("#f1f5f9", "#475569", "〰️"),
        "BEAR_TREND":  ("#fee2e2", "#991b1b", "🔴"),
        "UNKNOWN":     ("#f9fafb", "#6b7280", "❓"),
    }
    bg, fg, icon = color_map.get(regime, color_map["UNKNOWN"])
    prev_str = f"← {prev}" if prev and prev != "UNKNOWN" else ""
    method_str = " (rule-based)" if method == "rule_based" else ""
    return (
        f'<div style="background:{bg};color:{fg};padding:10px 20px;border-radius:8px;'
        f'font-size:13px;font-weight:700;display:flex;align-items:center;gap:12px;'
        f'margin-bottom:16px;border:1px solid {fg}22">'
        f'{icon} Market Regime: <strong>{regime.replace("_", " ")}</strong>'
        f'&nbsp;|&nbsp;Confidence: {conf*100:.0f}%'
        f'&nbsp;|&nbsp;Duration: {dur}d'
        f'{f"&nbsp;|&nbsp;{prev_str}" if prev_str else ""}'
        f'{f"&nbsp;<em style=\'font-weight:400;font-size:11px\'>{method_str}</em>" if method_str else ""}'
        f'</div>'
    )


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    if force and REGIME_CACHE.exists():
        REGIME_CACHE.unlink()
    info = detect_regime()
    print(f"Regime: {info['current_regime']} (confidence {info['confidence']:.0%}, duration {info['regime_duration_days']}d)")
    print(f"Previous: {info['previous_regime']}")
    print(f"Signal weights: {json.dumps(info['weights'], indent=2)}")
