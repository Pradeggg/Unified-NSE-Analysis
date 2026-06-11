from __future__ import annotations

import os
from typing import Any


SKILL_STORE_ENV = "AGENT_ADDA_SKILL_STORE"
DEFAULT_SKILL_STORE_ENABLED = True
TRUTHY_VALUES = frozenset({"1", "true", "yes", "on", "enabled"})
FALSEY_VALUES = frozenset({"0", "false", "no", "off", "disabled", ""})


def skill_store_enabled(*, enabled: bool | None = None, env: dict[str, str] | None = None) -> bool:
    if enabled is not None:
        return bool(enabled)
    source = env if env is not None else os.environ
    if SKILL_STORE_ENV not in source:
        return DEFAULT_SKILL_STORE_ENABLED
    raw = str(source.get(SKILL_STORE_ENV, "")).strip().lower()
    if raw in TRUTHY_VALUES:
        return True
    if raw in FALSEY_VALUES:
        return False
    return False


def skill_store_dry_run_enabled(*, enabled: bool | None = None, env: dict[str, str] | None = None) -> bool:
    return skill_store_enabled(enabled=enabled, env=env)


def skill_store_config_snapshot(*, env: dict[str, str] | None = None) -> dict[str, Any]:
    source = env if env is not None else os.environ
    return {
        "env_var": SKILL_STORE_ENV,
        "raw_value": source.get(SKILL_STORE_ENV),
        "enabled": skill_store_enabled(env=source),
        "dry_run_enabled": skill_store_dry_run_enabled(env=source),
    }
