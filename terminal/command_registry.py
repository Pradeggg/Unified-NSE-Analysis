"""terminal/command_registry.py — Unified slash-command dispatch registry.

Provides :class:`CommandHandler` and :class:`CommandRegistry` so that slash
commands shared between ``_single_query`` (--query CLI) and ``_chat_loop``
(interactive REPL) are registered once and dispatched consistently.

Handler callable signature::

    handler_fn(query: str, agent, show_trace: bool) -> bool

Return ``True`` when the command was handled (caller should stop dispatch).
Return ``False`` to let the next handler (or fallback LLM path) run.

Commands are matched using ``match_fn(lowercased_query: str) -> bool``.  The
registry is ordered; the first match wins.

Handler functions and registration happen in nse_agent.py to avoid circular
imports — this module is pure infrastructure.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Callable

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class CommandHandler:
    """A single slash-command binding.

    Attributes:
        name: Human-readable identifier used for logging/introspection.
        match_fn: Predicate called with the lowercased, stripped query string.
        handler_fn: Called with ``(query, agent, show_trace)`` when matched.
            Should return ``True`` if the command was fully handled, ``False``
            to fall through to the next handler.
        modes: Which dispatch contexts this handler is active in.
            ``"interactive"`` = REPL loop, ``"single_query"`` = --query CLI.
        description: One-line description shown by /commands.
    """

    name: str
    match_fn: Callable[[str], bool]
    handler_fn: Callable[[str, object, bool], bool]
    modes: frozenset[str] = dataclasses.field(
        default_factory=lambda: frozenset({"interactive", "single_query"})
    )
    description: str = ""


class CommandRegistry:
    """Ordered registry of :class:`CommandHandler` instances.

    Usage::

        registry = CommandRegistry()
        registry.register(CommandHandler(...))

        # In dispatch loop:
        if registry.dispatch(query, agent, show_trace, mode="single_query"):
            return  # handled
    """

    def __init__(self) -> None:
        self._handlers: list[CommandHandler] = []

    def register(self, handler: CommandHandler) -> None:
        """Append a handler to the end of the dispatch chain."""
        self._handlers.append(handler)

    def dispatch(
        self,
        query: str,
        agent,
        show_trace: bool,
        mode: str = "interactive",
    ) -> bool:
        """Try each registered handler in order. Return True if any handled it."""
        q_lower = (query or "").strip().lower()
        for h in self._handlers:
            if mode not in h.modes:
                continue
            try:
                if h.match_fn(q_lower):
                    logger.debug(
                        "CommandRegistry: %s matched %r", h.name, query[:60]
                    )
                    return h.handler_fn(query, agent, show_trace)
            except Exception:
                logger.debug(
                    "CommandRegistry: handler %s raised", h.name, exc_info=True
                )
        return False

    @property
    def handler_names(self) -> list[str]:
        """Names of all registered handlers in dispatch order."""
        return [h.name for h in self._handlers]

    def __len__(self) -> int:
        return len(self._handlers)


__all__ = ["CommandHandler", "CommandRegistry"]
