from pathlib import Path

from terminal.interaction_profile import StepVisibility, VerbosityLevel, profile_for_style
from terminal.session_preferences import (
    load_interaction_preferences,
    save_interaction_preferences,
)


def test_preferences_round_trip_survives_new_load(tmp_path: Path):
    path = tmp_path / "prefs.json"
    profile = profile_for_style("codex")
    profile = profile.__class__(
        **{**profile.__dict__, "verbosity": VerbosityLevel.DEEP, "steps": StepVisibility.ON}
    )

    save_interaction_preferences(profile, path=path)
    loaded = load_interaction_preferences(path=path)

    assert loaded.profile.style == "codex"
    assert loaded.profile.verbosity == VerbosityLevel.DEEP
    assert loaded.profile.steps == StepVisibility.ON
    assert loaded.warning is None


def test_missing_preferences_returns_default(tmp_path: Path):
    loaded = load_interaction_preferences(path=tmp_path / "missing.json")

    assert loaded.profile.style == "default"
    assert loaded.warning is None


def test_corrupt_preferences_fail_closed_and_preserve_bad_file(tmp_path: Path):
    path = tmp_path / "prefs.json"
    path.write_text("{bad json", encoding="utf-8")

    loaded = load_interaction_preferences(path=path)

    assert loaded.profile.style == "default"
    assert loaded.warning
    assert not path.exists()
    backups = list(tmp_path.glob("prefs.json.corrupt-*"))
    assert backups

