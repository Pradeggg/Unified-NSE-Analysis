"""Lazy LLM client facade for Research Council JSON overlays."""

from __future__ import annotations

import json
import os
import queue
import threading
from pathlib import Path
from typing import Any


class ResearchCouncilLLMUnavailable(RuntimeError):
    """Raised when no configured LLM provider can serve a Research Council request."""


def call_llm_json(
    *,
    system: str,
    user: str,
    schema: dict,
    model: str | None = None,
    allow_deterministic_fallback: bool = False,
) -> dict[str, Any]:
    """Call an LLM and return a validated JSON object.

    Provider cascade: OpenAI (if OPENAI_API_KEY set) → Ollama (if OLLAMA_HOST
    reachable) → deterministic empty dict (only when allow_deterministic_fallback=True).

    Raises ResearchCouncilLLMUnavailable when no provider is available and
    allow_deterministic_fallback is False (the default for strategy-build calls).
    """
    _load_dotenv_if_needed()

    # PG 2026-05-27: `gpt-5.5` does not exist on the OpenAI API — every call
    # was failing/hanging and being misreported as a timeout. Fall back to gpt-4o
    # which is the project default (OPENAI_MODEL).
    selected_model = model or os.environ.get("RESEARCH_COUNCIL_LLM_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4o"

    # ── 1. OpenAI provider (when API key is explicitly configured) ─────────
    # If a key is set, OpenAI is the intended provider — propagate its errors
    # rather than silently cascading to a local model.
    if os.environ.get("OPENAI_API_KEY"):
        return _call_openai_json(system=system, user=user, schema=schema, model=selected_model)

    # ── 2. Ollama provider (cascade for keyless / local-only setups) ───────
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    ollama_model = os.environ.get("RESEARCH_COUNCIL_OLLAMA_MODEL") or os.environ.get("OLLAMA_MODEL") or "llama3"
    last_error: str | None = None
    try:
        return _call_ollama_json(
            system=system, user=user, schema=schema,
            host=ollama_host, model=ollama_model,
        )
    except ResearchCouncilLLMUnavailable as exc:
        last_error = str(exc)

    # ── 3. Deterministic fallback (non-strategy-build overlays only) ───────
    if allow_deterministic_fallback:
        return {}

    raise ResearchCouncilLLMUnavailable(
        f"No LLM provider available for Research Council. "
        f"Set OPENAI_API_KEY or start Ollama. Last error: {last_error}"
    )
    raise ResearchCouncilLLMUnavailable(f"schema validation failed: {last_error}")


def _call_openai_json(*, system: str, user: str, schema: dict, model: str) -> dict[str, Any]:
    """Call OpenAI chat completions and return a validated JSON dict."""
    client = _openai_client()
    validation_error: str | None = None
    last_error: str | None = None
    for attempt in range(2):
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": _user_content(user=user, schema=schema, validation_error=validation_error)},
            ],
            "response_format": {"type": "json_object"},
            "timeout": _llm_timeout_s(),
        }
        if not _uses_default_temperature_only(model):
            kwargs["temperature"] = 0.1
        try:
            response = _create_completion_with_timeout(client, kwargs, timeout_s=_llm_timeout_s())
        except Exception as exc:
            raise ResearchCouncilLLMUnavailable(f"OpenAI request failed: {exc}") from exc
        content = response.choices[0].message.content
        try:
            parsed = json.loads(content or "{}")
        except json.JSONDecodeError as exc:
            raise ResearchCouncilLLMUnavailable(f"OpenAI returned invalid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ResearchCouncilLLMUnavailable("OpenAI returned JSON that is not an object")
        errors = validate_json_schema_subset(parsed, schema)
        if not errors:
            return parsed
        last_error = "; ".join(errors)
        validation_error = f"Validation error from attempt {attempt + 1}: {last_error}"
    raise ResearchCouncilLLMUnavailable(f"OpenAI schema validation failed: {last_error}")


def _call_ollama_json(*, system: str, user: str, schema: dict, host: str, model: str) -> dict[str, Any]:
    """Call Ollama /api/chat with JSON format and return a validated dict."""
    try:
        import urllib.request
        import urllib.error
    except Exception as exc:
        raise ResearchCouncilLLMUnavailable(f"urllib unavailable: {exc}") from exc

    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": _user_content(user=user, schema=schema, validation_error=None)},
        ],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.1},
    }).encode()

    url = f"{host.rstrip('/')}/api/chat"
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    timeout = int(_llm_timeout_s())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.URLError as exc:
        raise ResearchCouncilLLMUnavailable(f"Ollama unavailable at {host}: {exc}") from exc
    except Exception as exc:
        raise ResearchCouncilLLMUnavailable(f"Ollama request failed: {exc}") from exc

    content = (body.get("message") or {}).get("content") or ""
    try:
        parsed = json.loads(content or "{}")
    except json.JSONDecodeError as exc:
        raise ResearchCouncilLLMUnavailable(f"Ollama returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ResearchCouncilLLMUnavailable("Ollama returned JSON that is not an object")
    errors = validate_json_schema_subset(parsed, schema)
    if errors:
        raise ResearchCouncilLLMUnavailable(f"Ollama schema validation failed: {'; '.join(errors)}")
    return parsed


def _openai_client():
    try:
        from openai import OpenAI
    except Exception as exc:
        raise ResearchCouncilLLMUnavailable(f"openai package unavailable: {exc}") from exc
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=_llm_timeout_s())


def _create_completion_with_timeout(client: Any, kwargs: dict[str, Any], *, timeout_s: float) -> Any:
    result_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            result_queue.put(("ok", client.chat.completions.create(**kwargs)))
        except Exception as exc:
            result_queue.put(("error", exc))

    thread = threading.Thread(target=worker, name="research-council-llm-call", daemon=True)
    thread.start()
    try:
        status, payload = result_queue.get(timeout=timeout_s)
    except queue.Empty as exc:
        raise ResearchCouncilLLMUnavailable(f"LLM request timed out after {timeout_s:g}s") from exc
    if status == "error":
        raise payload
    return payload


def _llm_timeout_s() -> float:
    raw = os.environ.get("RESEARCH_COUNCIL_LLM_TIMEOUT_S")
    if not raw:
        return 20.0
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 20.0


def _uses_default_temperature_only(model: str) -> bool:
    normalized = model.lower()
    return normalized.startswith("gpt-5") or normalized.startswith("o1") or normalized.startswith("o3") or normalized.startswith("o4")


def _load_dotenv_if_needed() -> None:
    if os.environ.get("OPENAI_API_KEY"):
        return
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip().strip('"').strip("'")
    except OSError:
        return


def _user_content(*, user: str, schema: dict[str, Any], validation_error: str | None) -> str:
    payload: dict[str, Any] = {"payload": user, "schema": schema}
    if validation_error:
        payload["validation_error"] = validation_error
        payload["instruction"] = "Return corrected JSON only. Do not explain."
    return json.dumps(payload, default=str)


def validate_json_schema_subset(value: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Validate the JSON Schema subset used by Research Council prompts."""
    errors: list[str] = []
    if schema.get("type") == "object" and not isinstance(value, dict):
        return ["root must be an object"]
    required = schema.get("required") or []
    for key in required:
        if key not in value:
            errors.append(f"{key} is required")
    properties = schema.get("properties") or {}
    for key, prop in properties.items():
        if key not in value:
            continue
        errors.extend(_validate_property(key, value[key], prop))
    return errors


def _validate_property(path: str, value: Any, schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type == "string" and not isinstance(value, str):
        errors.append(f"{path} must be a string")
    elif expected_type == "integer" and not isinstance(value, int):
        errors.append(f"{path} must be an integer")
    elif expected_type == "boolean" and not isinstance(value, bool):
        errors.append(f"{path} must be a boolean")
    elif expected_type == "array":
        if not isinstance(value, list):
            errors.append(f"{path} must be an array")
            return errors
        min_items = schema.get("minItems")
        if min_items is not None and len(value) < int(min_items):
            errors.append(f"{path} must contain at least {min_items} item(s)")
        item_schema = schema.get("items") or {}
        for index, item in enumerate(value):
            errors.extend(_validate_property(f"{path}[{index}]", item, item_schema))
    enum = schema.get("enum")
    if enum is not None and value not in enum:
        errors.append(f"{path} must be one of {enum}")
    return errors
