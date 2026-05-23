"""Structured telemetry for hybrid symbol resolution."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schema import ResolveResult


TELEMETRY_PATH = Path("logs/symbol_resolution.jsonl")


def emit(
    result: ResolveResult,
    *,
    latency_ms: float,
    fallback_reason: str = "",
    path: Path | None = None,
    enabled: bool | None = None,
) -> bool:
    """Append one JSONL telemetry event.

    Tests pass ``enabled=True`` and a temp ``path``. Normal pytest runs are
    disabled by default to avoid polluting the repository's ``logs/`` folder;
    non-test runtime emits unless ``NSE_SYMBOL_RESOLUTION_TELEMETRY=0``.
    """
    if not _enabled(enabled):
        return False

    out_path = path or TELEMETRY_PATH
    payload = _payload(result, latency_ms=latency_ms, fallback_reason=fallback_reason)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        return True
    except Exception:
        return False


def _enabled(override: bool | None) -> bool:
    if override is not None:
        return bool(override)
    env_value = os.getenv("NSE_SYMBOL_RESOLUTION_TELEMETRY")
    if env_value is not None:
        return env_value.strip().lower() not in {"0", "false", "no", "off"}
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    return True


def _payload(result: ResolveResult, *, latency_ms: float, fallback_reason: str) -> dict[str, Any]:
    return {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "query": result.query,
        "winner": result.symbol,
        "method": result.method,
        "score": float(result.score),
        "raw_score": float(result.raw_score),
        "confidence_band": result.confidence_band,
        "legacy_confidence": result.legacy_confidence,
        "candidates": [
            {
                "sym": candidate.symbol,
                "score": float(candidate.score),
                "raw_score": float(candidate.raw_score),
                "methods": list(candidate.methods),
                "matched": candidate.matched,
            }
            for candidate in result.candidates
        ],
        "latency_ms": float(latency_ms),
        "fallback_reason": fallback_reason,
        "clarification_emitted": bool(result.needs_clarification),
    }


# ---------------------------------------------------------------------------
# AA-HSR-5: latency benchmark helper
# ---------------------------------------------------------------------------


import time as _time
from typing import Callable, Iterable


def benchmark(
    queries: Iterable[str],
    resolver: Callable[[str], Any],
) -> dict[str, float | int]:
    """Run *resolver* against *queries* and return latency summary in ms.

    Keys: ``n``, ``p50``, ``p95``, ``p99``, ``max``, ``mean``. Returns
    zeros for an empty input. Resolver exceptions are swallowed so a
    single bad query does not break the whole benchmark run; the call
    still contributes its latency to the summary.
    """
    latencies: list[float] = []
    for q in queries:
        start = _time.perf_counter()
        try:
            resolver(q)
        except Exception:
            pass
        latencies.append((_time.perf_counter() - start) * 1000.0)
    if not latencies:
        return {"n": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0, "mean": 0.0}
    latencies.sort()
    return {
        "n": len(latencies),
        "p50": _percentile(latencies, 50.0),
        "p95": _percentile(latencies, 95.0),
        "p99": _percentile(latencies, 99.0),
        "max": latencies[-1],
        "mean": sum(latencies) / len(latencies),
    }


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return float(sorted_values[f])
    return float(sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f))
