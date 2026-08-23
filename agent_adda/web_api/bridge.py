"""
agent_adda/web_api/bridge.py — Agent bridge for Talk 2 Stocks.

Maintains a session-keyed pool of ``terminal.agent.Agent`` instances so the
T2S web routes can call the same 7-stage pipeline that the CLI uses, including
UnifiedRouter, _synthesize_and_narrate, render plans, guardrails, and full
multi-turn pronoun/context resolution.

Context isolation
-----------------
Each T2S browser session gets its own ``Agent`` instance with its own
``ConversationMemory``.  The memory ``session_id`` is set to the T2S
``session_id`` so ``_build_context_pack()`` returns the correct
``recent_turns`` and ``active_symbols`` for *that* session — not a shared
global default.

PG writes are disabled for T2S agents (``AGENT_ADDA_MEMORY_PG=0``) so
T2S conversations don't pollute the CLI's persistent Postgres memory.

Usage (inside an async FastAPI handler)::

    from agent_adda.web_api.bridge import agent_query

    result = await agent_query(session_id, question)
    # result: {"answer": str, "intent": str, "trace": list, "backend": str,
    #           "usage": dict, ...}

Session cleanup:  sessions older than SESSION_TTL_SECONDS are evicted on each
call.  A session that hasn't been used in that window gets a fresh Agent on its
next call — the agent re-initialises its backend and history automatically.
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

# ── environment bootstrap ─────────────────────────────────────────────────────
_REPO_ROOT = str(Path(__file__).resolve().parents[3])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
os.environ.setdefault("AGENT_ADDA_SKIP_VENV_CHECK", "1")
# Suppress interactive prompts / terminal-only setup
os.environ.setdefault("AGENT_ADDA_WEB_MODE", "1")

SESSION_TTL_SECONDS = int(os.getenv("T2S_SESSION_TTL_SECONDS", "3600"))  # 1 h

_lock = threading.Lock()
# {session_id: (Agent, last_used_ts)}
_pool: dict[str, tuple[Any, float]] = {}


def _evict_stale() -> None:
    cutoff = time.monotonic() - SESSION_TTL_SECONDS
    stale = [sid for sid, (_agent, ts) in _pool.items() if ts < cutoff]
    for sid in stale:
        del _pool[sid]


def _make_agent(session_id: str) -> Any:
    """Create an Agent isolated to *session_id*.

    Key isolation steps:
    1. Set AGENT_ADDA_MEMORY_SESSION_ID to the T2S session_id so
       ConversationMemory.build_context_pack() returns turns for THIS session
       (not the global CLI default).
    2. Disable Postgres writes (AGENT_ADDA_MEMORY_PG=0) so T2S turns don't
       pollute the CLI's persistent memory store.
    3. Restore both env vars after construction so other threads are unaffected.
    """
    from terminal.agent import Agent  # imported lazily — heavy module

    old_session = os.environ.get("AGENT_ADDA_MEMORY_SESSION_ID")
    old_pg      = os.environ.get("AGENT_ADDA_MEMORY_PG")
    try:
        os.environ["AGENT_ADDA_MEMORY_SESSION_ID"] = f"t2s_{session_id}"
        os.environ["AGENT_ADDA_MEMORY_PG"]         = "0"
        agent = Agent()
    finally:
        # Restore exactly — don't leave stale values for other threads.
        if old_session is None:
            os.environ.pop("AGENT_ADDA_MEMORY_SESSION_ID", None)
        else:
            os.environ["AGENT_ADDA_MEMORY_SESSION_ID"] = old_session
        if old_pg is None:
            os.environ.pop("AGENT_ADDA_MEMORY_PG", None)
        else:
            os.environ["AGENT_ADDA_MEMORY_PG"] = old_pg
    return agent


def _get_agent(session_id: str) -> Any:
    """Return the Agent for *session_id*, creating one if needed."""
    with _lock:
        _evict_stale()
        entry = _pool.get(session_id)
        if entry is None:
            entry = (_make_agent(session_id), time.monotonic())
            _pool[session_id] = entry
        else:
            agent, _ = entry
            _pool[session_id] = (agent, time.monotonic())
        return _pool[session_id][0]


def query_sync(session_id: str, question: str) -> dict[str, Any]:
    """Blocking call — runs Agent.query() on the calling thread.

    Suitable for use inside ``asyncio.get_event_loop().run_in_executor(None, ...)``
    or directly from synchronous code.

    Returns the same dict that the CLI pipeline returns::

        {
            "answer": str,          # synthesised Markdown answer
            "intent": str,          # e.g. "stock_brief", "compare", ...
            "trace": list[dict],    # per-tool results + step records
            "backend": str,         # "openai", "ollama", "keyword"
            "usage": {              # token counts (present for LLM backends)
                "input_tokens": int,
                "output_tokens": int,
                "cache_read_input_tokens": int,
                "cache_creation_input_tokens": int,
            },
        }
    """
    agent = _get_agent(session_id)
    try:
        return agent.query(question, show_trace=True)
    except Exception as exc:  # noqa: BLE001
        return {
            "answer": f"Agent pipeline error: {exc}",
            "intent": "error",
            "trace": [{"step": "bridge_error", "error": repr(exc)}],
            "backend": "error",
            "usage": {},
        }


async def agent_query(session_id: str, question: str) -> dict[str, Any]:
    """Async wrapper — runs the synchronous Agent.query() in a thread pool
    so it does not block the FastAPI event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, query_sync, session_id, question)


def session_count() -> int:
    """Return the number of live sessions in the pool (diagnostic only)."""
    with _lock:
        return len(_pool)
