"""Persisted Agent Adda interaction preferences."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .interaction_profile import InteractionProfile, default_profile, merge_profile


PREFS_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class LoadedInteractionPreferences:
    profile: InteractionProfile
    path: Path
    warning: str | None = None


def default_preferences_path() -> Path:
    raw = os.environ.get("AGENT_ADDA_PREFS_PATH")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".agent_adda" / "interaction_preferences.json"


def _payload_from_profile(profile: InteractionProfile) -> dict[str, Any]:
    return {
        "schema_version": PREFS_SCHEMA_VERSION,
        "interaction_profile": profile.to_dict(),
    }


def save_interaction_preferences(
    profile: InteractionProfile,
    *,
    path: str | Path | None = None,
) -> Path:
    target = Path(path).expanduser() if path is not None else default_preferences_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(_payload_from_profile(profile), indent=2, sort_keys=True), encoding="utf-8")
    return target


def load_interaction_preferences(
    *,
    path: str | Path | None = None,
) -> LoadedInteractionPreferences:
    target = Path(path).expanduser() if path is not None else default_preferences_path()
    if not target.exists():
        return LoadedInteractionPreferences(default_profile(), target)

    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        profile_data = payload.get("interaction_profile", payload)
        profile = merge_profile(default_profile(), profile_data)
        return LoadedInteractionPreferences(profile, target)
    except Exception as exc:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = target.with_name(f"{target.name}.corrupt-{stamp}")
        try:
            target.replace(backup)
        except Exception:
            backup = target
        return LoadedInteractionPreferences(
            default_profile(),
            target,
            warning=f"Interaction preferences were unreadable and defaults were used: {exc}. Backup: {backup}",
        )

