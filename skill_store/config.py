from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_MODEL = "gpt-4o"
MODEL_ALIASES = {
    "gpt-5.5": "gpt-5.5",
    "gpt-5-5": "gpt-5.5",
    "gpt-40": "gpt-4o",
    "gpt-4o": "gpt-4o",
}


@dataclass(frozen=True)
class GenerationConfig:
    model: str
    api_key_available: bool
    env_path: Path

    def __repr__(self) -> str:
        return (
            "GenerationConfig("
            f"model={self.model!r}, "
            f"api_key_available={self.api_key_available!r}, "
            f"env_path={str(self.env_path)!r})"
        )


def normalize_model_name(model: str | None) -> str:
    raw = str(model or "").strip()
    if not raw:
        return DEFAULT_MODEL
    normalized = raw.lower().replace("_", "-").replace(" ", "-")
    return MODEL_ALIASES.get(normalized, normalized if normalized.startswith(("gpt-", "o")) else raw)


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def load_generation_config(env_path: Path | None = None) -> GenerationConfig:
    path = env_path or Path.cwd() / ".env"
    _load_env_file(path)
    requested_model = os.environ.get("SKILL_STORE_MODEL") or DEFAULT_MODEL
    return GenerationConfig(
        model=normalize_model_name(requested_model),
        api_key_available=bool(os.environ.get("OPENAI_API_KEY")),
        env_path=path,
    )
