from __future__ import annotations

from terminal.situation_assessment import TurnContext


class FakeCursor:
    def __init__(self, rows=None):
        self.executed = []
        self.rows = rows or []
        self.fetchone_calls = 0

    def execute(self, sql, params=None):
        self.executed.append((str(sql), params))

    def fetchone(self):
        self.fetchone_calls += 1
        return self.rows[0] if self.rows else None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self, rows=None):
        self.cursor_obj = FakeCursor(rows)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _pcbl_context() -> TurnContext:
    return TurnContext(
        user_input="PCBL analysis",
        intent="stock_brief",
        mode="historical",
        tools=["resolve_symbol", "get_symbol_snapshot", "get_technical_setup", "scrape_screener_in"],
        source_label="EOD CSV + DB snapshot + screener.in",
        freshness="2026-05-19",
        result_type="stock_brief",
        result_summary=(
            "stock brief for PCBL; price 273.55; signal SELL; stage STAGE_4; "
            "RS -3; RSI snapshot 38; technical RSI 43.5; MACD bearish; "
            "supertrend SELL; risk: low interest coverage; Report: /tmp/PCBL.md"
        ),
        symbols=["PCBL"],
        result_items=["/tmp/PCBL.md"],
    )


def test_memory_schema_creates_agent_memory_tables_and_indexes():
    from terminal.conversation_memory import ensure_memory_schema

    conn = FakeConnection()

    ensure_memory_schema(conn)

    sql_text = "\n".join(sql for sql, _ in conn.cursor_obj.executed)
    assert "CREATE SCHEMA IF NOT EXISTS agent_memory" in sql_text
    assert "CREATE TABLE IF NOT EXISTS agent_memory.turn_events" in sql_text
    assert "CREATE TABLE IF NOT EXISTS agent_memory.session_snapshots" in sql_text
    assert "idx_agent_memory_turn_events_session_turn" in sql_text
    assert "idx_agent_memory_turn_events_symbols" in sql_text
    assert conn.commits == 1


def test_memory_records_raw_event_and_compressed_entity_facts():
    from terminal.conversation_memory import ConversationMemory

    memory = ConversationMemory(session_id="test-session")
    memory.record_turn(
        user_input="PCBL analysis",
        answer="PCBL answer with SELL and STAGE_4",
        tool_results=[{"tool": "get_symbol_snapshot", "args": {"symbol": "PCBL"}, "result": {"symbol": "PCBL"}}],
        turn_context=_pcbl_context(),
    )

    assert len(memory.raw_events) == 1
    assert memory.raw_events[0].user_input == "PCBL analysis"
    assert memory.entities["PCBL"].symbol == "PCBL"
    assert "SELL" in memory.entities["PCBL"].evidence
    assert "STAGE_4" in memory.entities["PCBL"].evidence
    assert "snapshot RSI 38 vs technical RSI 43.5" in memory.entities["PCBL"].contradictions
    assert "/tmp/PCBL.md" in memory.report_paths
    assert memory.last_focus_symbols == ["PCBL"]


def test_memory_serializes_and_loads_snapshot_roundtrip():
    from terminal.conversation_memory import ConversationMemory

    memory = ConversationMemory(session_id="test-session")
    memory.record_turn(
        user_input="PCBL analysis",
        answer="PCBL answer",
        tool_results=[],
        turn_context=_pcbl_context(),
    )

    restored = ConversationMemory.from_snapshot("test-session", memory.to_snapshot())

    assert restored.session_id == "test-session"
    assert restored.entities["PCBL"].latest_stance == "cautious_avoid_fresh_entry"
    assert restored.entities["PCBL"].freshness == "2026-05-19"
    assert restored.raw_event_count == 1


def test_save_to_postgres_upserts_raw_event_and_snapshot(monkeypatch):
    import terminal.conversation_memory as cm

    memory = cm.ConversationMemory(session_id="test-session")
    memory.record_turn("PCBL analysis", "PCBL answer", [], _pcbl_context())
    conn = FakeConnection()
    monkeypatch.setattr(cm, "connect", lambda dsn=None: conn)

    result = memory.save_to_postgres()

    assert result["ok"] is True
    assert result["rows_inserted"] == 1
    assert conn.commits >= 1
    sql_text = "\n".join(sql for sql, _ in conn.cursor_obj.executed)
    assert "INSERT INTO agent_memory.turn_events" in sql_text
    assert "INSERT INTO agent_memory.session_snapshots" in sql_text


def test_load_from_postgres_restores_snapshot(monkeypatch):
    import terminal.conversation_memory as cm

    original = cm.ConversationMemory(session_id="test-session")
    original.record_turn("PCBL analysis", "PCBL answer", [], _pcbl_context())
    row = (original.to_snapshot(),)
    conn = FakeConnection(rows=[row])
    monkeypatch.setattr(cm, "connect", lambda dsn=None: conn)

    loaded = cm.ConversationMemory.load_from_postgres("test-session")

    assert loaded.session_id == "test-session"
    assert "PCBL" in loaded.entities
    assert loaded.entities["PCBL"].source_label == "EOD CSV + DB snapshot + screener.in"


def test_agent_fallback_context_uses_compressed_memory_when_history_trimmed(monkeypatch):
    import terminal.agent as agent_mod
    from terminal.conversation_memory import ConversationMemory

    monkeypatch.setenv("AGENT_ADDA_MEMORY_PG", "0")
    agent = agent_mod.Agent()
    agent._memory = ConversationMemory(session_id="test-session")
    agent._memory.record_turn("PCBL analysis", "PCBL answer", [], _pcbl_context())
    agent._history = []
    agent._last_turn_context = None

    ctx = agent._conversation_fallback_context(mode="historical", source_label="EOD CSV + DB snapshot")

    assert ctx is not None
    assert ctx.symbols == ["PCBL"]
    assert "PCBL" in ctx.result_summary
    assert "STAGE_4" in ctx.result_summary


def test_agent_situation_assessment_recovers_from_compressed_memory(monkeypatch):
    import terminal.agent as agent_mod
    from terminal.conversation_memory import ConversationMemory

    monkeypatch.setenv("AGENT_ADDA_MEMORY_PG", "0")
    agent = agent_mod.Agent()
    agent._memory = ConversationMemory(session_id="test-session")
    agent._memory.record_turn("PCBL analysis", "PCBL answer", [], _pcbl_context())
    agent._history = []
    agent._last_turn_context = None

    result = agent.query("based on the previous analysis what should be our approach")

    assert result["intent"] == "situation_assessment"
    assert "PCBL" in result["answer"]
    assert "SITUATION ASSESSMENT" in result["answer"]
    assert "PLAN OF THOUGHT (POT)" in result["answer"]
