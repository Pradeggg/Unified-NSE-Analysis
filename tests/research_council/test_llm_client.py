from __future__ import annotations

import time

import pytest


def test_call_llm_json_requires_api_key(monkeypatch, tmp_path):
    from terminal.research_council import llm_client
    from terminal.research_council.llm_client import ResearchCouncilLLMUnavailable, call_llm_json

    def unavailable_ollama(**kwargs):
        raise ResearchCouncilLLMUnavailable("Ollama down")

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(llm_client, "_call_ollama_json", unavailable_ollama)

    with pytest.raises(ResearchCouncilLLMUnavailable, match="No LLM provider"):
        call_llm_json(system="system", user="user", schema={"type": "object"})


def test_call_llm_json_parses_chat_completion_json(monkeypatch):
    from terminal.research_council import llm_client

    captured = {}

    class FakeMessage:
        content = '{"strategy_family": "stage2_breakout"}'

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(llm_client, "_openai_client", lambda: FakeClient())

    output = llm_client.call_llm_json(
        system="system prompt",
        user="user prompt",
        schema={"type": "object"},
        model="test-model",
    )

    assert output == {"strategy_family": "stage2_breakout"}
    assert captured["model"] == "test-model"
    assert captured["response_format"] == {"type": "json_object"}
    assert captured["messages"][0] == {"role": "system", "content": "system prompt"}


def test_call_llm_json_defaults_research_council_to_gpt_55(monkeypatch):
    from terminal.research_council import llm_client

    captured = {}

    class FakeMessage:
        content = "{}"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("RESEARCH_COUNCIL_LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setattr(llm_client, "_openai_client", lambda: FakeClient())

    llm_client.call_llm_json(system="system", user="user", schema={"type": "object"})

    # PG 2026-05-27: default model switched gpt-5.5 -> gpt-4o (gpt-5.5 is not
    # a real OpenAI model id). gpt-4o accepts an explicit temperature, unlike
    # reasoning-only models, so the call now passes temperature=0.1.
    assert captured["model"] == "gpt-4o"
    assert captured["temperature"] == 0.1
    assert captured["timeout"] == 20.0


def test_call_llm_json_uses_research_council_timeout_env(monkeypatch):
    from terminal.research_council import llm_client

    captured = {}

    class FakeMessage:
        content = "{}"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("RESEARCH_COUNCIL_LLM_TIMEOUT_S", "3.5")
    monkeypatch.setattr(llm_client, "_openai_client", lambda: FakeClient())

    llm_client.call_llm_json(system="system", user="user", schema={"type": "object"})

    assert captured["timeout"] == 3.5


def test_call_llm_json_wraps_provider_timeout(monkeypatch):
    from terminal.research_council import llm_client
    from terminal.research_council.llm_client import ResearchCouncilLLMUnavailable

    class FakeCompletions:
        def create(self, **kwargs):
            raise TimeoutError("timed out")

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(llm_client, "_openai_client", lambda: FakeClient())

    with pytest.raises(ResearchCouncilLLMUnavailable, match="request failed"):
        llm_client.call_llm_json(system="system", user="user", schema={"type": "object"})


def test_call_llm_json_enforces_application_level_timeout(monkeypatch):
    from terminal.research_council import llm_client
    from terminal.research_council.llm_client import ResearchCouncilLLMUnavailable

    class FakeCompletions:
        def create(self, **kwargs):
            time.sleep(2)
            raise AssertionError("call should have timed out before this point")

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("RESEARCH_COUNCIL_LLM_TIMEOUT_S", "0.01")
    monkeypatch.setattr(llm_client, "_openai_client", lambda: FakeClient())

    started = time.monotonic()
    with pytest.raises(ResearchCouncilLLMUnavailable, match="LLM request timed out"):
        llm_client.call_llm_json(system="system", user="user", schema={"type": "object"})

    assert time.monotonic() - started < 1.5


def test_call_llm_json_loads_api_key_from_dotenv(monkeypatch, tmp_path):
    from terminal.research_council import llm_client

    captured = {}

    class FakeMessage:
        content = "{}"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=test-dotenv-key\n", encoding="utf-8")
    monkeypatch.setattr(llm_client, "_openai_client", lambda: FakeClient())

    llm_client.call_llm_json(system="system", user="user", schema={"type": "object"})

    assert captured["model"] == "gpt-4o"
    assert __import__("os").environ["OPENAI_API_KEY"] == "test-dotenv-key"


def test_call_llm_json_retries_once_after_schema_validation_error(monkeypatch):
    from terminal.research_council import llm_client

    calls = []
    responses = [
        '{"strategy_family": "not_allowed"}',
        '{"strategy_family": "stage2_breakout", "entry_rules": ["stage is Stage 2"]}',
    ]

    class FakeMessage:
        def __init__(self, content):
            self.content = content

    class FakeChoice:
        def __init__(self, content):
            self.message = FakeMessage(content)

    class FakeResponse:
        def __init__(self, content):
            self.choices = [FakeChoice(content)]

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return FakeResponse(responses.pop(0))

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(llm_client, "_openai_client", lambda: FakeClient())

    output = llm_client.call_llm_json(
        system="system",
        user="user",
        schema={
            "type": "object",
            "required": ["strategy_family", "entry_rules"],
            "properties": {
                "strategy_family": {"type": "string", "enum": ["stage2_breakout"]},
                "entry_rules": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            },
        },
    )

    assert output == {"strategy_family": "stage2_breakout", "entry_rules": ["stage is Stage 2"]}
    assert len(calls) == 2
    assert "Validation error" in calls[1]["messages"][1]["content"]


def test_call_llm_json_raises_after_second_schema_validation_error(monkeypatch):
    from terminal.research_council import llm_client
    from terminal.research_council.llm_client import ResearchCouncilLLMUnavailable

    class FakeMessage:
        content = '{"strategy_family": "not_allowed"}'

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(llm_client, "_openai_client", lambda: FakeClient())

    with pytest.raises(ResearchCouncilLLMUnavailable, match="schema validation failed"):
        llm_client.call_llm_json(
            system="system",
            user="user",
            schema={
                "type": "object",
                "required": ["strategy_family"],
                "properties": {
                    "strategy_family": {"type": "string", "enum": ["stage2_breakout"]},
                },
            },
        )


# ── Ollama cascade tests ───────────────────────────────────────────────────────

def test_ollama_cascade_used_when_no_openai_key(monkeypatch, tmp_path):
    """Without OPENAI_API_KEY, call_llm_json routes to _call_ollama_json."""
    from terminal.research_council import llm_client
    from terminal.research_council.llm_client import ResearchCouncilLLMUnavailable

    calls = []

    def fake_ollama(*, system, user, schema, host, model):
        calls.append({"host": host, "model": model})
        return {"ok": True}

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(llm_client, "_call_ollama_json", fake_ollama)

    result = llm_client.call_llm_json(system="sys", user="usr", schema={"type": "object"})

    assert result == {"ok": True}
    assert len(calls) == 1
    assert calls[0]["host"] == "http://localhost:11434"


def test_ollama_model_override_via_env(monkeypatch, tmp_path):
    from terminal.research_council import llm_client

    calls = []

    def fake_ollama(*, system, user, schema, host, model):
        calls.append(model)
        return {}

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("RESEARCH_COUNCIL_OLLAMA_MODEL", "mistral")
    monkeypatch.setattr(llm_client, "_call_ollama_json", fake_ollama)

    llm_client.call_llm_json(system="s", user="u", schema={"type": "object"})

    assert calls[0] == "mistral"


def test_deterministic_fallback_returns_empty_dict_when_no_provider(monkeypatch, tmp_path):
    from terminal.research_council import llm_client

    def unavailable_ollama(**kwargs):
        from terminal.research_council.llm_client import ResearchCouncilLLMUnavailable
        raise ResearchCouncilLLMUnavailable("Ollama down")

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(llm_client, "_call_ollama_json", unavailable_ollama)

    result = llm_client.call_llm_json(
        system="s", user="u", schema={"type": "object"},
        allow_deterministic_fallback=True,
    )

    assert result == {}


def test_deterministic_fallback_raises_by_default_when_no_provider(monkeypatch, tmp_path):
    from terminal.research_council import llm_client
    from terminal.research_council.llm_client import ResearchCouncilLLMUnavailable

    def unavailable_ollama(**kwargs):
        raise ResearchCouncilLLMUnavailable("Ollama down")

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(llm_client, "_call_ollama_json", unavailable_ollama)

    with pytest.raises(ResearchCouncilLLMUnavailable, match="No LLM provider"):
        llm_client.call_llm_json(system="s", user="u", schema={"type": "object"})


# ── Real LLM smoke test (skipped in CI unless RESEARCH_COUNCIL_RUN_LLM_TESTS=1) ─

@pytest.mark.llm
def test_call_llm_json_real_openai_smoke(monkeypatch):
    """Smoke test that actually calls OpenAI. Skipped unless marker enabled."""
    import os
    if not os.environ.get("RESEARCH_COUNCIL_RUN_LLM_TESTS"):
        pytest.skip("set RESEARCH_COUNCIL_RUN_LLM_TESTS=1 to run real LLM tests")

    from terminal.research_council.llm_client import call_llm_json

    result = call_llm_json(
        system="You are a helpful assistant. Respond only with valid JSON.",
        user="Return a JSON object with key 'status' set to 'ok'.",
        schema={
            "type": "object",
            "required": ["status"],
            "properties": {"status": {"type": "string"}},
        },
    )

    assert isinstance(result, dict)
    assert result.get("status") == "ok"
