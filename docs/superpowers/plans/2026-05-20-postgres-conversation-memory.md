# Postgres Conversation Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add lossless PostgreSQL-backed conversation archive plus structured compressed memory that Agent Adda can load and use across turns/restarts.

**Architecture:** Create a focused `terminal.conversation_memory` module that owns schema creation, raw event persistence, deterministic compression, and Postgres load/save. Wire `terminal.agent.Agent` to maintain this memory fail-open, update it from `_remember_interaction`, and use it as fallback context when `_last_turn_context` is unavailable or raw history has been trimmed.

**Tech Stack:** Python dataclasses, psycopg2/PostgreSQL JSONB, existing `TurnContext`, pytest fake-connection tests.

---

### Task 1: Memory Module and Schema

**Files:**
- Create: `terminal/conversation_memory.py`
- Create: `tests/test_conversation_memory.py`
- Create: `postgres/migrations/20260520_agent_memory.sql`

- [ ] Write tests for idempotent schema SQL and deterministic memory extraction.
- [ ] Implement `ConversationMemory`, `MemoryEvent`, `EntityMemory`, and schema helpers.
- [ ] Verify with `.venv/bin/pytest -q tests/test_conversation_memory.py`.

### Task 2: Postgres Persistence and Load

**Files:**
- Modify: `terminal/conversation_memory.py`
- Modify: `tests/test_conversation_memory.py`

- [ ] Write fake-connection tests for `save_to_postgres` and `load_from_postgres`.
- [ ] Implement `connect`, `ensure_memory_schema`, `save_to_postgres`, and `load_from_postgres`.
- [ ] Keep all database failures fail-open at the Agent integration boundary.

### Task 3: Agent Integration

**Files:**
- Modify: `terminal/agent.py`
- Modify: `tests/test_conversation_memory.py`

- [ ] Write tests proving Agent updates memory and can recover PCBL context after raw history trimming.
- [ ] Add `_memory`, `_memory_session_id`, and `_memory_pg_enabled`.
- [ ] Update `_remember_interaction` to record turns and persist snapshots.
- [ ] Update `_conversation_fallback_context` and `_tool_selection_text` to include compressed memory.

### Task 4: Verification

**Files:**
- No new files.

- [ ] Run `.venv/bin/pytest -q tests/test_conversation_memory.py tests/test_situation_assessment.py tests/test_situation_assessment_scenarios.py tests/test_terminal_agent_market_prompt.py`.
- [ ] Run a direct multi-turn probe with a trimmed history and prior PCBL memory.
- [ ] Run `.venv/bin/pytest -q` if targeted tests are green.

