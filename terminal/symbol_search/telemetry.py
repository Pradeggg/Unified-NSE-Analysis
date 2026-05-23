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
