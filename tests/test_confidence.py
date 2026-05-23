"""Tests for terminal/confidence.py + intent-confidence wiring."""

import io
import sys

import pytest


# ── ConfidenceScore basics ────────────────────────────────────────────


def test_band_thresholds():
    from terminal.confidence import ConfidenceScore

    assert ConfidenceScore(0.95, "intent").band == "high"
    assert ConfidenceScore(0.70, "intent").band == "medium"
    assert ConfidenceScore(0.50, "intent").band == "low"
    assert ConfidenceScore(0.20, "intent").band == "very_low"


def test_needs_clarification_threshold():
    from terminal.confidence import ConfidenceScore, CLARIFY_THRESHOLD

    assert ConfidenceScore(CLARIFY_THRESHOLD - 0.01, "intent").needs_clarification
    assert not ConfidenceScore(CLARIFY_THRESHOLD + 0.01, "intent").needs_clarification


def test_to_dict_roundtrip():
    from terminal.confidence import ConfidenceScore

    s = ConfidenceScore(0.55, "plan", decision="x", reasons=["r1"], alternatives=["a"])
    d = s.to_dict()
    assert d["score"] == 0.55
    assert d["band"] == "low"
    assert d["stage"] == "plan"
    assert d["reasons"] == ["r1"]
    assert d["alternatives"] == ["a"]


# ── Stage scorers ─────────────────────────────────────────────────────


def test_score_intent_clean_prompt():
    from terminal.confidence import score_intent

    s = score_intent(
        decision="/mtf scan NIFTY 50 bullish",
        has_direction_conflict=False,
        direction_explicit=True,
        has_index_or_symbol=True,
    )
    assert s.score == 1.0
    assert s.band == "high"
    assert not s.needs_clarification


def test_score_intent_direction_conflict_triggers_clarification():
    from terminal.confidence import score_intent

    s = score_intent(
        decision="/mtf scan NIFTY 500 bullish",
        has_direction_conflict=True,
        direction_explicit=True,
        has_index_or_symbol=True,
    )
    # Conflict alone (0.40 penalty) must drop us below the clarify
    # threshold so the user always sees the panel for contradictions.
    assert s.score < 0.65
    assert s.needs_clarification
    assert any("ambiguous" in r.lower() for r in s.reasons)


def test_score_intent_missing_index_alone_does_not_clarify():
    from terminal.confidence import score_intent

    s = score_intent(
        decision="/mtf scan NIFTY 50 bullish",
        has_direction_conflict=False,
        direction_explicit=True,
        has_index_or_symbol=False,
    )
    # Just defaulting to NIFTY 50 isn't a clarification-worthy event.
    assert not s.needs_clarification


def test_score_plan_with_multiple_triggers():
    from terminal.confidence import score_plan

    s = score_plan(
        decision="situation_assessment_plan",
        trigger_count=3,
        has_mtf_or_recommendation=True,
        has_market_word=True,
    )
    assert s.score >= 0.85


def test_score_plan_single_trigger_no_market_word():
    from terminal.confidence import score_plan

    s = score_plan(
        decision="situation_assessment_plan",
        trigger_count=1,
        has_mtf_or_recommendation=True,
        has_market_word=False,
    )
    # 1 trigger (0.85) - 0.10 (no market word flag) = 0.75 — medium band
    # but still above the clarify threshold (0.65). Single clear MTF
    # intent is a high-confidence ask; the small deduction just flags
    # the missing market-word context for transparency.
    assert 0.65 <= s.score < 0.85
    assert any("market" in r.lower() for r in s.reasons)


def test_score_synthesis_clean_text():
    from terminal.confidence import score_synthesis

    s = score_synthesis(
        "NIFTY 50 closed at 25,000 with broad participation. Top gainers: "
        "RELIANCE, HDFCBANK. Sector rotation favoured PHARMA and METAL."
    )
    assert s.score >= 0.85


def test_score_synthesis_hedge_heavy_text():
    from terminal.confidence import score_synthesis

    s = score_synthesis(
        "The market appears to be uncertain. It might be that flows are "
        "ambiguous. Direction is unclear and the trend could be either way."
    )
    assert s.needs_clarification
    assert s.signals["hedge_hits"] >= 3


def test_score_synthesis_stale_data_text():
    from terminal.confidence import score_synthesis

    s = score_synthesis(
        "Data unavailable for top movers; tool error on FII flows. "
        "Fallback to cached snapshot. No matches returned for the scan."
    )
    assert s.needs_clarification
    assert s.signals["stale_hits"] >= 1


def test_score_synthesis_empty_text():
    from terminal.confidence import score_synthesis

    s = score_synthesis("")
    assert s.needs_clarification


# ── Renderer ──────────────────────────────────────────────────────────


def test_render_clarification_does_not_render_high_confidence():
    from terminal.confidence import ConfidenceScore, render_clarification
    from rich.console import Console

    buf = io.StringIO()
    out = render_clarification(
        ConfidenceScore(0.95, "intent", decision="x"), Console(file=buf)
    )
    assert out is False
    assert buf.getvalue() == ""


def test_render_clarification_renders_low_confidence():
    from terminal.confidence import ConfidenceScore, render_clarification
    from rich.console import Console

    buf = io.StringIO()
    out = render_clarification(
        ConfidenceScore(
            0.40, "intent",
            decision="/mtf scan NIFTY 50 bullish",
            reasons=["test reason"],
            alternatives=["/mtf scan NIFTY 500 bearish"],
        ),
        Console(file=buf, force_terminal=False),
    )
    assert out is True
    text = buf.getvalue()
    assert "Clarification" in text
    assert "test reason" in text
    assert "NIFTY 500 bearish" in text


def test_render_clarification_force_overrides_threshold():
    from terminal.confidence import ConfidenceScore, render_clarification
    from rich.console import Console

    buf = io.StringIO()
    out = render_clarification(
        ConfidenceScore(0.95, "synthesis"),
        Console(file=buf, force_terminal=False),
        force=True,
    )
    assert out is True


# ── Wiring into _detect_mtf_intent_scored ─────────────────────────────


def test_detect_mtf_intent_scored_conflict_lowers_confidence():
    from nse_agent import _detect_mtf_intent_scored

    rewrite, score = _detect_mtf_intent_scored(
        "find bullish MTF aligned stocks for short in NIFTY500"
    )
    assert rewrite == "/mtf scan NIFTY 500 bullish --min-score 70"
    assert score is not None
    assert score.needs_clarification
    assert any("ambiguous" in r.lower() for r in score.reasons)
    # Alternatives should include the opposite direction.
    assert any("bearish" in alt for alt in score.alternatives)


def test_detect_mtf_intent_scored_clean_prompt_high_confidence():
    from nse_agent import _detect_mtf_intent_scored

    rewrite, score = _detect_mtf_intent_scored(
        "show me bullish MTF confluence in NIFTY 50"
    )
    assert rewrite == "/mtf scan NIFTY 50 bullish --min-score 70"
    assert score is not None
    assert not score.needs_clarification
    assert score.score >= 0.95


def test_detect_mtf_intent_scored_no_mtf_intent_returns_none():
    from nse_agent import _detect_mtf_intent_scored

    rewrite, score = _detect_mtf_intent_scored("what's the weather like")
    assert rewrite is None and score is None


def test_detect_mtf_intent_legacy_returns_str_only():
    """Backward-compat: legacy helper still returns just the rewrite."""
    from nse_agent import _detect_mtf_intent

    out = _detect_mtf_intent("show me bullish MTF confluence in NIFTY 50")
    assert isinstance(out, str)
    assert out.startswith("/mtf")
