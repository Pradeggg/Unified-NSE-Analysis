from pathlib import Path

import nse_agent


def test_interaction_command_status_uses_loaded_preferences(monkeypatch, tmp_path: Path):
    pref_path = tmp_path / "prefs.json"
    monkeypatch.setenv("AGENT_ADDA_PREFS_PATH", str(pref_path))

    result = nse_agent._handle_interaction_command("/style")

    assert result["handled"] is True
    assert result["action"] == "status"
    assert result["profile"]["style"] == "default"


def test_style_command_persists_codex_profile(monkeypatch, tmp_path: Path):
    pref_path = tmp_path / "prefs.json"
    monkeypatch.setenv("AGENT_ADDA_PREFS_PATH", str(pref_path))

    result = nse_agent._handle_interaction_command("/style codex")
    status = nse_agent._handle_interaction_command("/style")

    assert result["status"] == "ok"
    assert result["profile"]["style"] == "codex"
    assert status["profile"]["style"] == "codex"
    assert pref_path.exists()


def test_verbosity_and_steps_update_existing_profile(monkeypatch, tmp_path: Path):
    pref_path = tmp_path / "prefs.json"
    monkeypatch.setenv("AGENT_ADDA_PREFS_PATH", str(pref_path))

    nse_agent._handle_interaction_command("/style codex")
    verbosity = nse_agent._handle_interaction_command("/verbosity deep")
    steps = nse_agent._handle_interaction_command("/steps on")

    assert verbosity["profile"]["style"] == "codex"
    assert verbosity["profile"]["verbosity"] == "deep"
    assert steps["profile"]["style"] == "codex"
    assert steps["profile"]["steps"] == "on"


def test_interaction_command_rejects_unknown_values(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AGENT_ADDA_PREFS_PATH", str(tmp_path / "prefs.json"))

    result = nse_agent._handle_interaction_command("/verbosity loud")

    assert result["handled"] is True
    assert result["status"] == "error"
    assert "concise" in result["valid"]
    assert "deep" in result["valid"]


def test_interaction_commands_are_registered_in_slash_catalog():
    labels = [label for label, _description in nse_agent._SLASH_COMMANDS]

    assert "/style" in labels
    assert "/style codex" in labels
    assert "/verbosity" in labels
    assert "/steps" in labels

