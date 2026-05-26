"""AA-CC-2: Permission mode enum and policy.

Inspired by Claude Code's permission modes. Agent Adda has historically
treated every clarification as blocking and every tool invocation as
implicitly approved. This module promotes that implicit policy to a
first-class enum so the agent can be operated in different stances:

* ``default`` — Ask clarifications when the assessor wants to. Execute
  routed tool plans. This matches the historical behavior.
* ``auto``    — Same as ``default`` for now but reserved for a future
  "auto-accept low-risk, ask only on risky" policy. Currently
  equivalent to ``default``.
* ``dontAsk`` — Never block on a clarification. When the assessor
  produces an ``ask_clarification``, the policy says: pick the
  default-labelled option's ``bound_action`` if one exists, else fall
  through to ``answer_from_context``. Risky-op gating *would* still
  log a warning (not exercised today — no destructive ops).
* ``plan``    — Plan-only mode. The agent should produce the routing
  plan / tool plan summary but **not** execute it. Useful for letting
  the user inspect what would happen before committing.
* ``bypassPermissions`` — Same as ``dontAsk`` and additionally
  reserved to disable any future approval gates. Equivalent to
  ``dontAsk`` for this codebase today.

Environment override::

    AGENT_ADDA_PERMISSION_MODE=plan agentadda

Slash flag (when wired): ``/mode plan`` or ``--permission-mode=plan``.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PermissionMode(str, Enum):
    DEFAULT = "default"
    AUTO = "auto"
    DONT_ASK = "dontAsk"
    PLAN = "plan"
    BYPASS_PERMISSIONS = "bypassPermissions"

    @classmethod
    def parse(cls, value: str | None) -> "PermissionMode":
        """Parse a string into a mode, accepting common case variants.

        Empty/None falls back to ``DEFAULT``. Unknown values raise
        ``ValueError``.
        """
        if not value:
            return cls.DEFAULT
        s = str(value).strip()
        if not s:
            return cls.DEFAULT
        # Normalise camelCase → casefold lookup.
        norm = s.replace("_", "").replace("-", "").lower()
        table = {m.value.lower(): m for m in cls}
        if norm in table:
            return table[norm]
        # Allow exact value too.
        for m in cls:
            if s == m.value:
                return m
        raise ValueError(
            f"Unknown permission mode {value!r}. Valid: {[m.value for m in cls]}"
        )


_PLAN_FLAG_RE = re.compile(
    r"(?:^|\s)(?:--permission-mode|--mode)\s*[= ]\s*([A-Za-z]+)", re.IGNORECASE
)


def parse_permission_mode_flag(text: str) -> tuple[PermissionMode | None, str]:
    """Extract ``--permission-mode=X`` or ``--mode=X`` from a slash command.

    Returns ``(mode, stripped_text)``. If no flag is found, returns
    ``(None, text)`` unchanged.
    """
    if not text:
        return None, text
    m = _PLAN_FLAG_RE.search(text)
    if not m:
        return None, text
    mode = PermissionMode.parse(m.group(1))
    stripped = (text[: m.start()] + text[m.end():]).strip()
    return mode, stripped


@dataclass(frozen=True)
class PermissionPolicy:
    """Semantic wrapper around a :class:`PermissionMode`.

    Exposes high-level questions the agent / router asks at decision
    time, keeping callers free of switch-case noise.
    """
    mode: PermissionMode = PermissionMode.DEFAULT

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "PermissionPolicy":
        env = env if env is not None else os.environ
        raw = env.get("AGENT_ADDA_PERMISSION_MODE", "").strip()
        try:
            return cls(mode=PermissionMode.parse(raw))
        except ValueError as exc:
            logger.warning("invalid AGENT_ADDA_PERMISSION_MODE=%r (%s); using default", raw, exc)
            return cls(mode=PermissionMode.DEFAULT)

    @classmethod
    def of(cls, value: str | PermissionMode | None) -> "PermissionPolicy":
        if isinstance(value, PermissionMode):
            return cls(mode=value)
        return cls(mode=PermissionMode.parse(value))

    @property
    def is_default(self) -> bool:
        return self.mode == PermissionMode.DEFAULT

    @property
    def is_plan(self) -> bool:
        return self.mode == PermissionMode.PLAN

    @property
    def is_bypass(self) -> bool:
        return self.mode == PermissionMode.BYPASS_PERMISSIONS

    def should_ask_clarification(self) -> bool:
        """Whether to surface ``ask_clarification`` assessments to the user.

        ``dontAsk`` and ``bypassPermissions`` short-circuit clarifications
        (the agent should auto-pick the default option, or fall back to
        ``answer_from_context``). ``plan`` and ``default``/``auto`` ask.
        """
        return self.mode not in {
            PermissionMode.DONT_ASK,
            PermissionMode.BYPASS_PERMISSIONS,
        }

    def should_execute_tools(self) -> bool:
        """Whether routed tool plans may actually run.

        ``plan`` mode emits the plan and stops. Every other mode
        executes.
        """
        return self.mode != PermissionMode.PLAN

    def allows_destructive_ops(self) -> bool:
        """Reserved for a future approval gate on risky operations.

        ``bypassPermissions`` allows everything; ``plan`` allows
        nothing (it doesn't execute anyway). ``dontAsk`` allows but
        the future gate would log. ``default`` / ``auto`` would
        prompt.
        """
        return self.mode in {
            PermissionMode.BYPASS_PERMISSIONS,
            PermissionMode.DONT_ASK,
        }


__all__ = [
    "PermissionMode",
    "PermissionPolicy",
    "parse_permission_mode_flag",
]
