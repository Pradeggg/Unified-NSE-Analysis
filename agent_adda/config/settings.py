from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    import tomli as tomllib  # type: ignore


DEFAULT_HOME = Path.home() / ".agent-adda"
VALID_MODEL_MODES = {"rules", "local-llm", "openai", "hybrid"}


@dataclass(frozen=True)
class AppConfig:
    home_dir: Path
    data_dir: Path
    reports_dir: Path
    database_path: Path
    model_mode: str
    openai_api_key_env: str
    ollama_model: str
    disclaimer_acknowledged: bool


def default_config(home_dir: Path | None = None) -> AppConfig:
    home = (home_dir or DEFAULT_HOME).expanduser()
    return AppConfig(
        home_dir=home,
        data_dir=home / "data",
        reports_dir=home / "reports",
        database_path=home / "data" / "market_data.sqlite",
        model_mode="rules",
        openai_api_key_env="OPENAI_API_KEY",
        ollama_model="llama3.1",
        disclaimer_acknowledged=False,
    )


def config_path(home_dir: Path | None = None) -> Path:
    return (home_dir or DEFAULT_HOME).expanduser() / "config.toml"


def _path_value(value: Path) -> str:
    return str(value.expanduser())


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    target = path or config.home_dir / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    config.data_dir.mkdir(parents=True, exist_ok=True)
    config.reports_dir.mkdir(parents=True, exist_ok=True)
    content = "\n".join(
        [
            "[paths]",
            f'home_dir = "{_path_value(config.home_dir)}"',
            f'data_dir = "{_path_value(config.data_dir)}"',
            f'reports_dir = "{_path_value(config.reports_dir)}"',
            f'database_path = "{_path_value(config.database_path)}"',
            "",
            "[models]",
            f'mode = "{config.model_mode}"',
            f'openai_api_key_env = "{config.openai_api_key_env}"',
            f'ollama_model = "{config.ollama_model}"',
            "",
            "[compliance]",
            f"disclaimer_acknowledged = {str(config.disclaimer_acknowledged).lower()}",
            "",
        ]
    )
    target.write_text(content, encoding="utf-8")
    return target


def _get_path(section: dict[str, Any], key: str, fallback: Path) -> Path:
    value = section.get(key)
    return Path(value).expanduser() if value else fallback


def load_config(path: Path | None = None) -> AppConfig:
    target = path or config_path()
    base = default_config(target.parent)
    if not target.exists():
        return base
    data = tomllib.loads(target.read_text(encoding="utf-8"))
    paths = data.get("paths", {})
    models = data.get("models", {})
    compliance = data.get("compliance", {})
    mode = str(models.get("mode", base.model_mode))
    if mode not in VALID_MODEL_MODES:
        mode = base.model_mode
    return AppConfig(
        home_dir=_get_path(paths, "home_dir", base.home_dir),
        data_dir=_get_path(paths, "data_dir", base.data_dir),
        reports_dir=_get_path(paths, "reports_dir", base.reports_dir),
        database_path=_get_path(paths, "database_path", base.database_path),
        model_mode=mode,
        openai_api_key_env=str(models.get("openai_api_key_env", base.openai_api_key_env)),
        ollama_model=str(models.get("ollama_model", base.ollama_model)),
        disclaimer_acknowledged=bool(
            compliance.get("disclaimer_acknowledged", base.disclaimer_acknowledged)
        ),
    )
