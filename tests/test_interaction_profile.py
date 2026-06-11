from terminal.interaction_profile import (
    StepVisibility,
    VerbosityLevel,
    default_profile,
    merge_profile,
    profile_for_style,
    should_show_steps,
)


def test_default_profile_is_quiet_and_research_safe():
    profile = default_profile()

    assert profile.style == "default"
    assert profile.verbosity == VerbosityLevel.NORMAL
    assert profile.steps == StepVisibility.AUTO
    assert profile.show_assumptions is False
    assert profile.show_verification is True
    assert profile.research_only is True


def test_codex_profile_enables_visible_copilot_behaviour():
    profile = profile_for_style("codex")

    assert profile.style == "codex"
    assert profile.verbosity == VerbosityLevel.NORMAL
    assert profile.steps == StepVisibility.AUTO
    assert profile.show_assumptions is True
    assert profile.show_next_actions is True
    assert profile.show_verification is True
    assert should_show_steps(profile, "composite_screener") is True


def test_unknown_style_fails_closed_with_warning():
    resolved = profile_for_style("wizard")

    assert resolved.style == "default"
    assert resolved.warning
    assert "wizard" in resolved.warning


def test_merge_profile_applies_string_overrides_without_mutating_base():
    base = default_profile()
    merged = merge_profile(base, {"style": "codex", "verbosity": "deep", "steps": "on"})

    assert base.style == "default"
    assert merged.style == "codex"
    assert merged.verbosity == VerbosityLevel.DEEP
    assert merged.steps == StepVisibility.ON
    assert should_show_steps(merged, "single_tool") is True

