"""Interaction profile settings for Agent Adda copilot behavior."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any


class StepVisibility(str, Enum):
    OFF = "off"
    AUTO = "auto"
    ON = "on"


class VerbosityLevel(str, Enum):
    CONCISE = "concise"
    NORMAL = "normal"
    DEEP = "deep"


class ToneStyle(str, Enum):
    DEFAULT = "default"
    CODEX = "codex"
    INSTITUTIONAL = "institutional"
    TEACHER = "teacher"
    TRADER = "trader"


@dataclass(frozen=True)
class InteractionProfile:
    style: str = ToneStyle.DEFAULT.value
    verbosity: VerbosityLevel = VerbosityLevel.NORMAL
    steps: StepVisibility = StepVisibility.AUTO
    show_assumptions: bool = False
    show_verification: bool = True
    show_next_actions: bool = True
    research_only: bool = True
    warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "style": self.style,
            "verbosity": self.verbosity.value,
            "steps": self.steps.value,
            "show_assumptions": self.show_assumptions,
            "show_verification": self.show_verification,
            "show_next_actions": self.show_next_actions,
            "research_only": self.research_only,
            "warning": self.warning,
        }


def _coerce_enum(enum_cls: type[Enum], value: Any, default: Enum) -> Enum:
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(str(value).lower())
    except Exception:
        return default


def default_profile() -> InteractionProfile:
    return InteractionProfile()


def profile_for_style(style: str | None) -> InteractionProfile:
    key = (style or "default").strip().lower()
    if key in {"", "default"}:
        return default_profile()
    if key == "codex":
        return InteractionProfile(
            style="codex",
            verbosity=VerbosityLevel.NORMAL,
            steps=StepVisibility.AUTO,
            show_assumptions=True,
            show_verification=True,
            show_next_actions=True,
            research_only=True,
        )
    if key == "institutional":
        return InteractionProfile(
            style="institutional",
            verbosity=VerbosityLevel.DEEP,
            steps=StepVisibility.AUTO,
            show_assumptions=True,
            show_verification=True,
            show_next_actions=True,
            research_only=True,
        )
    if key == "teacher":
        return InteractionProfile(
            style="teacher",
            verbosity=VerbosityLevel.DEEP,
            steps=StepVisibility.ON,
            show_assumptions=True,
            show_verification=True,
            show_next_actions=True,
            research_only=True,
        )
    if key == "trader":
        return InteractionProfile(
            style="trader",
            verbosity=VerbosityLevel.CONCISE,
            steps=StepVisibility.AUTO,
            show_assumptions=False,
            show_verification=True,
            show_next_actions=True,
            research_only=True,
        )
    return replace(default_profile(), warning=f"Unknown style '{style}', using default.")


def merge_profile(base: InteractionProfile, overrides: dict[str, Any] | None) -> InteractionProfile:
    if not overrides:
        return base

    style = str(overrides.get("style", base.style)).strip().lower()
    if style != base.style:
        merged = profile_for_style(style)
        if merged.warning:
            merged = replace(merged, warning=merged.warning)
    else:
        merged = base

    verbosity = _coerce_enum(
        VerbosityLevel,
        overrides.get("verbosity", merged.verbosity),
        merged.verbosity,
    )
    steps = _coerce_enum(
        StepVisibility,
        overrides.get("steps", merged.steps),
        merged.steps,
    )

    bool_fields: dict[str, bool] = {}
    for field_name in ("show_assumptions", "show_verification", "show_next_actions", "research_only"):
        if field_name in overrides:
            bool_fields[field_name] = bool(overrides[field_name])

    return replace(
        merged,
        verbosity=verbosity,  # type: ignore[arg-type]
        steps=steps,          # type: ignore[arg-type]
        **bool_fields,
    )


def should_show_steps(profile: InteractionProfile, workflow_kind: str | None = None) -> bool:
    if profile.steps == StepVisibility.ON:
        return True
    if profile.steps == StepVisibility.OFF:
        return False
    return (workflow_kind or "") in {
        "composite_screener",
        "quality_breakouts",
        "research",
        "ric",
        "portfolio",
        "report_verification",
    }

