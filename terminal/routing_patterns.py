"""terminal/routing_patterns.py — Centralised routing pattern registry.

Loads ``config/routing_patterns.yml`` once at import time and exposes typed
constants that situation_assessment.py, providers.py, and talk.py consume.

All three consumers used to maintain their own inline copies of these lists.
This module is the single source of truth; to tune routing behaviour, edit
``config/routing_patterns.yml`` — no Python source changes required.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "routing_patterns.yml"


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:  # noqa: BLE001 — file missing or malformed; fall back to empty
        return {}


# ── Contextual patterns ──────────────────────────────────────────────────────
def get_contextual_patterns() -> tuple[str, ...]:
    """Phrases that make needs_situation_assessment() return True."""
    return tuple(_load().get("contextual_patterns") or [])


# ── Affirmative follow-ups ───────────────────────────────────────────────────
def get_affirmative_followups() -> frozenset[str]:
    """Exact-match words that mean 'yes / continue / proceed'."""
    return frozenset(_load().get("affirmative_followups") or [])


# ── ContextualFollowupProvider trigger phrases ───────────────────────────────
def get_followup_phrases() -> tuple[str, ...]:
    """Phrases that fire ContextualFollowupProvider when context exists."""
    return tuple(_load().get("followup_phrases") or [])


# ── Off-domain detection ─────────────────────────────────────────────────────
def get_off_domain_regex() -> re.Pattern[str]:
    """Compiled regex that matches clearly non-NSE queries."""
    raw = _load().get("off_domain") or {}
    patterns = raw.get("patterns") or []
    combined = "|".join(f"(?:{p})" for p in patterns) if patterns else r"(?!x)x"  # never-match fallback
    # No ^ anchor — use re.search() at the call site so patterns match anywhere
    # in the query ("what is the current cricket score" would not match with ^).
    return re.compile(combined, re.IGNORECASE)


def get_off_domain_response() -> str:
    """Standard 'outside my coverage' response text."""
    raw = _load().get("off_domain") or {}
    return (raw.get("response") or "").strip()


# ── Advice boundary ──────────────────────────────────────────────────────────
def get_advice_boundary_regex() -> re.Pattern[str]:
    """Compiled regex that matches investment-advice requests."""
    raw = _load().get("advice_boundary") or {}
    patterns = raw.get("patterns") or []
    combined = "|".join(f"(?:{p})" for p in patterns) if patterns else r"(?!x)x"
    return re.compile(combined, re.IGNORECASE)


def get_advice_boundary_response() -> str:
    """Standard advice-boundary response text."""
    raw = _load().get("advice_boundary") or {}
    return (raw.get("response") or "").strip()


# ── Stopwords ────────────────────────────────────────────────────────────────
def get_stopwords() -> frozenset[str]:
    """Tokens to skip during T2S symbol extraction."""
    return frozenset(str(w).upper() for w in (_load().get("stopwords") or []))
