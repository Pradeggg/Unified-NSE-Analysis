from __future__ import annotations


def test_skill_store_feature_flag_defaults_enabled(monkeypatch):
    from terminal.skills.config import skill_store_enabled

    monkeypatch.delenv("AGENT_ADDA_SKILL_STORE", raising=False)

    assert skill_store_enabled() is True


def test_skill_store_feature_flag_accepts_truthy_values(monkeypatch):
    from terminal.skills.config import skill_store_enabled

    for value in ("1", "true", "TRUE", "yes", "on", "enabled"):
        monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", value)
        assert skill_store_enabled() is True


def test_skill_store_feature_flag_accepts_falsey_values(monkeypatch):
    from terminal.skills.config import skill_store_enabled

    for value in ("0", "false", "FALSE", "no", "off", "disabled", ""):
        monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", value)
        assert skill_store_enabled() is False


def test_skill_store_enabled_supports_explicit_override(monkeypatch):
    from terminal.skills.config import skill_store_enabled

    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "0")

    assert skill_store_enabled(enabled=True) is True
    assert skill_store_enabled(enabled=False) is False


def test_skill_store_dry_run_retrieval_allowed_only_when_enabled(monkeypatch):
    from terminal.skills.config import skill_store_dry_run_enabled

    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "0")
    assert skill_store_dry_run_enabled() is False

    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "1")
    assert skill_store_dry_run_enabled() is True


def test_agent_skill_store_guard_uses_feature_flag(monkeypatch):
    from terminal.agent import _skill_store_runtime_enabled

    monkeypatch.delenv("AGENT_ADDA_SKILL_STORE", raising=False)
    assert _skill_store_runtime_enabled() is True

    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "0")
    assert _skill_store_runtime_enabled() is False

    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "1")
    assert _skill_store_runtime_enabled() is True
