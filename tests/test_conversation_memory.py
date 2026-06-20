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
    memory.agentic_state = {
        "workflow": "market_scan",
        "next_actions": [{"id": "next_deep_dive_top_symbols"}],
    }
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
    assert restored.agentic_state == {
        "workflow": "market_scan",
        "next_actions": [{"id": "next_deep_dive_top_symbols"}],
    }


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


# ---------------------------------------------------------------------------
# AA-UR-2 — ContextPack + structured workflows / reports / pending options
# ---------------------------------------------------------------------------

from terminal.conversation_memory import ConversationMemory
from terminal.router import (
    ActiveReport,
    ContextPack,
    PendingOption,
    WorkflowStep,
)


def _record_turn(memory: ConversationMemory, *, symbol: str, summary: str, report: str | None = None) -> None:
    ctx = TurnContext(
        user_input=f"analyse {symbol}",
        intent="analysis",
        mode="eod",
        tools=["mtf_analysis"],
        source_label="PostgreSQL: eod",
        result_type="mtf_summary",
        result_summary=summary,
        symbols=[symbol],
        result_items=[report] if report else [],
        freshness="EOD 2026-05-22",
    )
    memory.record_turn(f"analyse {symbol}", "ok", [], turn_context=ctx)


def test_register_report_addressable_by_path_type_and_symbol():
    memory = ConversationMemory(session_id="s-ur2")
    memory.register_report("reports/DIXON_mtf.md", report_type="mtf", symbol="dixon")
    memory.register_report("reports/sector_rotation.md", report_type="sector")
    pack = memory.build_context_pack()
    assert pack.report_for(symbol="DIXON").path == "reports/DIXON_mtf.md"
    assert pack.report_for(report_type="sector").path == "reports/sector_rotation.md"
    assert pack.report_for(path="reports/DIXON_mtf.md").report_type == "mtf"
    assert pack.report_for(symbol="UNKNOWN") is None


def test_register_report_is_idempotent_on_path():
    memory = ConversationMemory(session_id="s-ur2")
    memory.register_report("reports/x.md", report_type="mtf", symbol="DIXON")
    memory.register_report("reports/x.md", report_type="mtf-v2", symbol="DIXON")
    pack = memory.build_context_pack()
    assert len(pack.active_reports) == 1
    assert pack.active_reports[0].report_type == "mtf-v2"


def test_workflow_persists_five_step_evidence_with_structured_facts():
    memory = ConversationMemory(session_id="s-ur2")
    memory.start_workflow("sherlock-1", "sherlock")
    for i in range(5):
        memory.append_workflow_step(
            "sherlock-1",
            WorkflowStep(
                step_id=f"step-{i+1}",
                kind=f"phase-{i+1}",
                summary=f"phase {i+1} note",
                evidence=[
                    {
                        "symbol": "MANINDS",
                        "fact": f"signal_{i+1}",
                        "value": f"value-{i+1}",
                        "source_label": "PostgreSQL: maninds_facts",
                        "freshness": "EOD 2026-05-22",
                    }
                ],
                source_label="PostgreSQL: maninds_facts",
                freshness="EOD 2026-05-22",
            ),
        )
    pack = memory.build_context_pack()
    assert pack.active_workflow is not None
    assert pack.active_workflow.status == "open"
    assert len(pack.active_workflow.steps) == 5
    # Acceptance: evidence is structured (dicts with explicit fields),
    # NOT a prose summary.
    for step in pack.active_workflow.steps:
        for fact in step.evidence:
            assert isinstance(fact, dict)
            assert "source_label" in fact and fact["source_label"]
            assert "fact" in fact and "value" in fact
    assert pack.active_workflow.symbols == ("MANINDS",)


def test_close_workflow_marks_status_closed_and_clears_current_pointer():
    memory = ConversationMemory(session_id="s-ur2")
    memory.start_workflow("wf-A", "sherlock")
    memory.close_workflow("wf-A")
    assert memory.active_workflows["wf-A"].status == "closed"
    assert memory.current_workflow_id == ""


def test_pending_options_round_trip_and_consume_by_label():
    memory = ConversationMemory(session_id="s-ur2")
    memory.register_pending_options([
        PendingOption(label="A", text="run intraday scan", bound_action={"cmd": "/scan"}),
        PendingOption(label="B", text="generate MTF report", bound_action={"cmd": "/mtf"}),
    ])
    pack = memory.build_context_pack()
    assert pack.find_pending_option("a").bound_action == {"cmd": "/scan"}
    consumed = memory.consume_pending_option("A")
    assert consumed is not None and consumed.label == "A"
    assert memory.consume_pending_option("A") is None
    assert len(memory.pending_options) == 1


def test_recent_turns_depth_is_five_and_reflects_actual_turns():
    memory = ConversationMemory(session_id="s-ur2")
    for i in range(7):
        _record_turn(memory, symbol=f"SYM{i}", summary=f"summary {i}")
    pack = memory.build_context_pack(depth=5)
    assert len(pack.recent_turns) == 5
    assert pack.recent_turns[0].turn_index == 3  # turns 3..7
    assert pack.recent_turns[-1].turn_index == 7
    assert "SYM6" in pack.recent_turns[-1].symbols


def test_context_pack_survives_snapshot_round_trip():
    memory = ConversationMemory(session_id="s-roundtrip")
    memory.register_report("reports/DIXON_mtf.md", report_type="mtf", symbol="DIXON")
    memory.register_active_indices(["NIFTY50"])
    memory.register_active_sectors(["IT"])
    memory.start_workflow("wf-1", "sherlock")
    memory.append_workflow_step(
        "wf-1",
        WorkflowStep(
            step_id="s1",
            kind="liquidity",
            evidence=[{"symbol": "DIXON", "fact": "volume", "value": "12M", "source_label": "PG"}],
            source_label="PG",
            freshness="EOD",
        ),
    )
    memory.register_pending_options([PendingOption(label="A", text="run scan", bound_action={"cmd": "/scan"})])
    memory.record_source_trail("PostgreSQL: eod", freshness="EOD 2026-05-22")
    _record_turn(memory, symbol="DIXON", summary="bullish MTF", report="reports/DIXON_mtf.md")

    snapshot = memory.to_snapshot()
    restored = ConversationMemory.from_snapshot("s-roundtrip", snapshot)
    pack = restored.build_context_pack()

    assert pack.session_id == "s-roundtrip"
    assert pack.report_for(symbol="DIXON").path == "reports/DIXON_mtf.md"
    assert pack.active_indices == ("NIFTY50",)
    assert pack.active_sectors == ("IT",)
    assert pack.active_workflow is not None
    assert len(pack.active_workflow.steps) == 1
    assert pack.active_workflow.steps[0].evidence[0]["fact"] == "volume"
    assert pack.find_pending_option("A").text == "run scan"
    assert pack.source_trails[-1]["source_label"] == "PostgreSQL: eod"
    assert any(t.symbols == ("DIXON",) for t in pack.recent_turns)


def test_evidence_is_not_sourced_only_from_prose_summary():
    """AA-UR-2 acceptance: workflow evidence must be structured facts, not prose.

    We assert that the structured workflow evidence carries explicit
    ``fact`` / ``value`` / ``source_label`` keys independent of the
    free-text turn ``result_summary``.
    """
    memory = ConversationMemory(session_id="s-ur2")
    _record_turn(memory, symbol="DIXON", summary="DIXON looks bullish on the daily chart.")
    memory.start_workflow("wf-evidence", "sherlock")
    memory.append_workflow_step(
        "wf-evidence",
        WorkflowStep(
            step_id="s1",
            kind="setup",
            evidence=[
                {
                    "symbol": "DIXON",
                    "fact": "ema21_cross_above_ema55",
                    "value": "true",
                    "source_label": "PostgreSQL: ohlcv_eod",
                    "freshness": "EOD 2026-05-22",
                }
            ],
        ),
    )
    pack = memory.build_context_pack()
    fact = pack.active_workflow.steps[0].evidence[0]
    # The structured fact is not derived from the prose summary.
    assert fact["fact"] not in pack.recent_turns[-1].user_input
    assert fact["source_label"].startswith("PostgreSQL")
    assert fact["value"] == "true"
