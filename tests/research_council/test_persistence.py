from datetime import date, datetime
from decimal import Decimal

from terminal.research_council.evidence_pack_builder import build_research_evidence_pack
from terminal.research_council.persistence import (
    load_evidence_pack,
    save_council_plans,
    save_council_run_metadata,
    save_critic_reviews,
    save_evidence_pack,
    save_execution_results,
)
from terminal.research_council.schemas import CouncilState, CriticFinding, CriticReview, Decision, ExecutionResult, Plan, PlanStep, ToolCall
from terminal.research_council.schemas import AgentFinding


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        if "pg_advisory_xact_lock" in sql:
            return
        if "INSERT INTO recommendation_reports.evidence_packs" in sql:
            (
                pack_id,
                as_of,
                mode,
                universe_filter,
                symbols,
                pack_body,
                source_trail,
                missing_evidence,
            ) = params
            self.conn.rows[pack_id] = {
                "pack_id": pack_id,
                "as_of": as_of,
                "mode": mode,
                "universe_filter": universe_filter,
                "symbols": symbols,
                "pack_body": pack_body,
                "source_trail": source_trail,
                "missing_evidence": missing_evidence,
            }
            return
        if "INSERT INTO recommendation_reports.agent_findings" in sql:
            finding_id, run_id, agent_name, iteration, stance, confidence, thesis, body = params
            self.conn.rows[finding_id] = {
                "finding_id": finding_id,
                "run_id": run_id,
                "agent_name": agent_name,
                "iteration": iteration,
                "stance": stance,
                "confidence": confidence,
                "thesis": thesis,
                "body": body,
            }
            return
        if "INSERT INTO recommendation_reports.execution_results" in sql:
            result_id, plan_id, step_id, status, outputs, error, elapsed_ms = params
            self.conn.rows[result_id] = {
                "result_id": result_id,
                "plan_id": plan_id,
                "step_id": step_id,
                "status": status,
                "outputs": outputs,
                "error": error,
                "elapsed_ms": elapsed_ms,
            }
            return
        if "INSERT INTO recommendation_reports.runs" in sql:
            self.conn.rows[params[0]] = {"kind": "run", "params": params}
            return
        if "INSERT INTO recommendation_reports.council_plans" in sql:
            self.conn.rows[params[0]] = {"kind": "plan", "params": params}
            return
        if "INSERT INTO recommendation_reports.critic_reviews" in sql:
            self.conn.rows[params[0]] = {"kind": "critic_review", "params": params}
            return
        if "SELECT pack_body" in sql:
            self._row = self.conn.rows.get(params[0])
            return
        raise AssertionError(f"Unexpected SQL: {sql}")

    def fetchone(self):
        return self._row


class FakeConnection:
    def __init__(self):
        self.rows = {}
        self.commits = 0

    def cursor(self, *args, **kwargs):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1


def test_save_and_load_evidence_pack_roundtrip_with_connection():
    pack = build_research_evidence_pack(
        mode="market_council",
        as_of=date(2026, 5, 26),
        snapshot_loader=lambda: {
            "eod_latest": date(2026, 5, 26),
            "stage_latest": date(2026, 5, 26),
            "fno_latest": date(2026, 5, 22),
            "financials_latest": date(2026, 5, 26),
            "total_symbols": 2465,
            "liquid_symbols": 982,
            "analyzed_symbols": 968,
            "filters": ["close > 100", "volume > 100000", "at least 50 bars"],
        },
        section_loader=lambda: {
            "market": {"regime": "CHOP"},
            "sectors": {},
            "stocks": {"count": 0, "candidates": []},
            "derivatives": {},
            "fundamentals": {},
            "events": {},
            "reports": {},
        },
    )
    conn = FakeConnection()

    metadata = save_evidence_pack(pack, conn=conn)
    restored = load_evidence_pack(pack.pack_id, conn=conn)

    assert metadata == {"status": "saved", "pack_id": pack.pack_id, "schema": "recommendation_reports"}
    assert restored == pack
    assert conn.commits == 1


def test_save_agent_findings_uses_run_scoped_primary_key():
    from terminal.research_council.persistence import save_agent_findings

    conn = FakeConnection()
    finding = AgentFinding(
        finding_id="technical_1",
        agent="technical",
        stance="neutral",
        confidence=0.3,
        thesis="No actionable setups.",
    )

    metadata = save_agent_findings([finding], run_id="run_1", conn=conn)

    assert metadata == {"status": "saved", "count": 1, "schema": "recommendation_reports"}
    assert conn.rows["run_1:technical_1"]["run_id"] == "run_1"
    assert conn.rows["run_1:technical_1"]["body"].adapted["finding_id"] == "technical_1"


def test_load_evidence_pack_returns_none_for_missing_pack():
    assert load_evidence_pack("missing", conn=FakeConnection()) is None


def test_save_execution_results_with_connection():
    conn = FakeConnection()
    result = ExecutionResult(
        result_id="plan_1:a",
        step_id="a",
        status="success",
        outputs=[{"ok": True}],
        elapsed_ms=12,
    )

    metadata = save_execution_results([result], plan_id="plan_1", conn=conn)

    assert metadata == {"status": "saved", "count": 1, "schema": "recommendation_reports"}
    assert conn.rows["plan_1:a"]["status"] == "success"
    assert conn.rows["plan_1:a"]["outputs"].adapted == [{"ok": True}]
    assert conn.commits == 1


def test_save_execution_results_serializes_decimal_outputs():
    conn = FakeConnection()
    result = ExecutionResult(
        result_id="plan_1:a",
        step_id="a",
        status="success",
        outputs=[{"value": Decimal("12.34")}],
    )

    save_execution_results([result], plan_id="plan_1", conn=conn)

    assert conn.rows["plan_1:a"]["outputs"].adapted == [{"value": 12.34}]


def test_save_council_plans_with_connection():
    conn = FakeConnection()
    plan = Plan(
        plan_id="plan_1",
        run_id="run_1",
        iteration=0,
        central_question="test",
        steps=[PlanStep(step_id="a", sequence=1, question="a", tool_calls=[ToolCall("tool.a")])],
    )

    metadata = save_council_plans([plan], run_id="run_1", conn=conn)

    assert metadata == {"status": "saved", "count": 1, "schema": "recommendation_reports"}
    assert conn.rows["plan_1"]["kind"] == "plan"
    assert conn.rows["plan_1"]["params"][4].adapted[0]["step_id"] == "a"


def test_save_council_run_metadata_with_connection():
    conn = FakeConnection()
    pack = build_research_evidence_pack(
        mode="market_council",
        as_of=date(2026, 5, 27),
        snapshot_loader=lambda: {
            "eod_latest": date(2026, 5, 27),
            "stage_latest": date(2026, 5, 27),
            "fno_latest": date(2026, 5, 27),
            "financials_latest": date(2026, 5, 27),
            "total_symbols": 10,
            "liquid_symbols": 8,
            "analyzed_symbols": 7,
        },
    )
    state = CouncilState(
        run_id="run_1",
        session_id="s1",
        created_at=datetime(2026, 5, 27, 10, 0),
        mode="market_council",
        stage="persistence",
        objective="today",
        horizon="swing",
        risk_budget="moderate",
        universe_filter="liquid",
        evidence_pack=pack,
        evidence_pack_id=pack.pack_id,
        decision=Decision(final_label="RESEARCH_LONG", confidence=0.8, rationale="ok", candidates=[{"symbol": "AAA"}]),
        flags={"markdown_report_path": "reports/research_council/run_1.md"},
    )

    metadata = save_council_run_metadata(state, conn=conn)

    assert metadata == {"status": "saved", "run_id": "run_1", "schema": "recommendation_reports"}
    assert conn.rows["run_1"]["kind"] == "run"
    assert conn.rows["run_1"]["params"][16] == "RESEARCH_LONG"


def test_save_critic_reviews_with_connection():
    conn = FakeConnection()
    review = CriticReview(
        review_id="risk_run_1_0",
        critic="risk",
        run_id="run_1",
        iteration=0,
        severity_max="block",
        findings=[
            CriticFinding(
                finding_id="risk_1",
                severity="block",
                target={"kind": "candidate", "id": "AAA"},
                description="risk",
                recommendation="fix",
            )
        ],
    )

    metadata = save_critic_reviews([review], conn=conn)

    assert metadata == {"status": "saved", "count": 1, "schema": "recommendation_reports"}
    assert conn.rows["risk_run_1_0"]["kind"] == "critic_review"
    assert conn.rows["risk_run_1_0"]["params"][5].adapted[0]["finding_id"] == "risk_1"
