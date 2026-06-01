"""RC-9.3: Resume and export tests for Research Council runs."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from terminal.research_council.evidence_pack_builder import build_research_evidence_pack
from terminal.research_council.persistence import (
    export_council_run,
    resume_council_run,
    save_agent_findings,
    save_council_plans,
    save_council_run_metadata,
    save_critic_reviews,
    save_evidence_pack,
    save_execution_results,
)
from terminal.research_council.schemas import (
    AgentFinding,
    CriticFinding,
    CriticReview,
    Decision,
    ExecutionResult,
    Plan,
    PlanStep,
    ToolCall,
)


# ── Shared fixtures ────────────────────────────────────────────────────────────

def _make_pack(as_of: date = date(2026, 5, 27)) -> object:
    return build_research_evidence_pack(
        mode="market_council",
        as_of=as_of,
        snapshot_loader=lambda: {
            "eod_latest": as_of,
            "stage_latest": as_of,
            "fno_latest": as_of,
            "financials_latest": as_of,
            "total_symbols": 10,
            "liquid_symbols": 8,
            "analyzed_symbols": 7,
        },
    )


class FakeConnection:
    """In-memory DB-API2 fake with enough behaviour for resume/export tests."""

    def __init__(self):
        self.runs: dict = {}
        self.evidence_packs: dict = {}
        self.agent_findings: list = []
        self.plans: list = []
        self.execution_results: list = []
        self.critic_reviews: list = []
        self.commits = 0

    def cursor(self, *_, **__):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        pass


class FakeCursor:
    def __init__(self, conn: FakeConnection):
        self._conn = conn
        self._rows: list = []
        self._index = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql: str, params=None):
        sql_stripped = " ".join(sql.split())
        if "pg_advisory_xact_lock" in sql_stripped:
            return

        # ── INSERT INTO runs ───────────────────────────────────────────────
        if "INSERT INTO recommendation_reports.runs" in sql_stripped:
            self._conn.runs[params[0]] = {
                "run_id": params[0],
                "generated_at": params[1],
                "council_mode": params[9],
                "horizon": params[10],
                "risk_budget": params[11],
                "universe_filter": params[12],
                "evidence_pack_id": params[13],
                "final_label": params[16],
                "council_status": params[17],
                "budgets_remaining": params[18],
            }
            return

        # ── INSERT INTO evidence_packs ─────────────────────────────────────
        if "INSERT INTO recommendation_reports.evidence_packs" in sql_stripped:
            pack_id, as_of, mode, universe_filter, symbols, pack_body, source_trail, missing_evidence = params
            self._conn.evidence_packs[pack_id] = {
                "pack_id": pack_id,
                "pack_body": pack_body,
            }
            return

        # ── INSERT INTO agent_findings ─────────────────────────────────────
        if "INSERT INTO recommendation_reports.agent_findings" in sql_stripped:
            finding_id, run_id, agent_name, iteration, stance, confidence, thesis, body = params
            self._conn.agent_findings.append({
                "run_id": run_id,
                "finding_id": finding_id,
                "agent_name": agent_name,
                "body": body,
            })
            return

        # ── INSERT INTO council_plans ──────────────────────────────────────
        if "INSERT INTO recommendation_reports.council_plans" in sql_stripped:
            plan_id, run_id, iteration, central_question, steps = params
            self._conn.plans.append({
                "run_id": run_id,
                "plan_id": plan_id,
                "iteration": iteration,
                "central_question": central_question,
                "steps": steps,
            })
            return

        # ── INSERT INTO execution_results ──────────────────────────────────
        if "INSERT INTO recommendation_reports.execution_results" in sql_stripped:
            result_id, plan_id, step_id, status, outputs, error, elapsed_ms = params
            self._conn.execution_results.append({
                "plan_id": plan_id,
                "result_id": result_id,
                "step_id": step_id,
                "status": status,
                "outputs": outputs,
                "error": error,
                "elapsed_ms": elapsed_ms,
            })
            return

        # ── INSERT INTO critic_reviews ─────────────────────────────────────
        if "INSERT INTO recommendation_reports.critic_reviews" in sql_stripped:
            review_id, run_id, iteration, critic, severity_max, findings, summary = params
            self._conn.critic_reviews.append({
                "run_id": run_id,
                "review_id": review_id,
                "critic": critic,
                "iteration": iteration,
                "severity_max": severity_max,
                "findings": findings,
                "summary": summary,
            })
            return

        # ── SELECT runs ────────────────────────────────────────────────────
        if "FROM recommendation_reports.runs" in sql_stripped and "WHERE run_id" in sql_stripped:
            run = self._conn.runs.get(params[0])
            self._rows = [run] if run else []
            self._index = 0
            return

        # ── SELECT agent_findings ──────────────────────────────────────────
        if "FROM recommendation_reports.agent_findings" in sql_stripped and "WHERE run_id" in sql_stripped:
            self._rows = [
                (r["body"],)
                for r in self._conn.agent_findings
                if r["run_id"] == params[0]
            ]
            self._index = 0
            return

        # ── SELECT council_plans ───────────────────────────────────────────
        if "FROM recommendation_reports.council_plans" in sql_stripped and "WHERE run_id" in sql_stripped:
            self._rows = [
                (r["plan_id"], r["iteration"], r["central_question"], r["steps"])
                for r in self._conn.plans
                if r["run_id"] == params[0]
            ]
            self._index = 0
            return

        # ── SELECT execution_results ───────────────────────────────────────
        if "FROM recommendation_reports.execution_results" in sql_stripped and "WHERE plan_id IN" in sql_stripped:
            plan_ids = set(params)
            self._rows = [
                (r["plan_id"], r["result_id"], r["step_id"], r["status"],
                 r["outputs"], r["error"], r["elapsed_ms"])
                for r in self._conn.execution_results
                if r["plan_id"] in plan_ids
            ]
            self._index = 0
            return

        # ── SELECT critic_reviews ──────────────────────────────────────────
        if "FROM recommendation_reports.critic_reviews" in sql_stripped and "WHERE run_id" in sql_stripped:
            self._rows = [
                (r["review_id"], r["critic"], r["iteration"], r["severity_max"],
                 r["findings"], r["summary"])
                for r in self._conn.critic_reviews
                if r["run_id"] == params[0]
            ]
            self._index = 0
            return

        # ── SELECT evidence_packs ──────────────────────────────────────────
        if "SELECT pack_body" in sql_stripped and "WHERE pack_id" in sql_stripped:
            ep = self._conn.evidence_packs.get(params[0])
            self._rows = [(ep["pack_body"],)] if ep else []
            self._index = 0
            return

    def fetchone(self):
        if not self._rows:
            return None
        row = self._rows[self._index] if self._index < len(self._rows) else None
        self._index += 1
        return row

    def fetchall(self):
        rows = self._rows[self._index:]
        self._index = len(self._rows)
        return rows


# ── Helpers to populate a FakeConnection ──────────────────────────────────────

def _populate_fake_conn(run_id: str = "run_test_001") -> FakeConnection:
    conn = FakeConnection()

    # Save evidence pack
    pack = _make_pack()
    save_evidence_pack(pack, conn=conn)

    # Save run metadata
    from terminal.research_council.schemas import CouncilState
    state = CouncilState(
        run_id=run_id,
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
        decision=Decision(
            final_label="RESEARCH_LONG",
            confidence=0.75,
            rationale="test",
            candidates=[{"symbol": "RELIANCE"}],
        ),
        flags={"markdown_report_path": f"reports/research_council/{run_id}.md"},
    )
    save_council_run_metadata(state, conn=conn)

    # Save agent findings
    findings = [
        AgentFinding(finding_id="tech_1", agent="technical", stance="long", confidence=0.7, thesis="Bullish setup."),
        AgentFinding(finding_id="fund_1", agent="fundamental", stance="neutral", confidence=0.5, thesis="Fair value."),
    ]
    save_agent_findings(findings, run_id=run_id, conn=conn)

    # Save plan + execution results
    plan = Plan(
        plan_id=f"{run_id}:plan_0",
        run_id=run_id,
        iteration=0,
        central_question="What is the best opportunity today?",
        steps=[PlanStep(step_id="s1", sequence=1, question="Check momentum", tool_calls=[ToolCall("tool.momentum")])],
    )
    save_council_plans([plan], run_id=run_id, conn=conn)
    result = ExecutionResult(result_id=f"{run_id}:plan_0:s1", step_id="s1", status="success", outputs=[{"ok": True}])
    save_execution_results([result], plan_id=f"{run_id}:plan_0", conn=conn)

    # Save critic review
    review = CriticReview(
        review_id=f"risk_{run_id}_0",
        critic="risk",
        run_id=run_id,
        iteration=0,
        severity_max="info",
        findings=[
            CriticFinding(
                finding_id="cf_1",
                severity="info",
                target={"kind": "candidate", "id": "RELIANCE"},
                description="no issues",
                recommendation="proceed",
            )
        ],
    )
    save_critic_reviews([review], conn=conn)

    return conn


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_resume_returns_none_for_missing_run():
    conn = FakeConnection()
    result = resume_council_run("nonexistent_run", conn=conn)
    assert result is None


def test_resume_reconstructs_state_fields():
    conn = _populate_fake_conn("run_resume_001")
    state = resume_council_run("run_resume_001", conn=conn)

    assert state is not None
    assert state.run_id == "run_resume_001"
    assert state.mode == "market_council"
    assert state.horizon == "swing"
    assert state.risk_budget == "moderate"
    assert state.flags.get("resumed") is True


def test_resume_loads_evidence_pack():
    conn = _populate_fake_conn("run_ep_001")
    state = resume_council_run("run_ep_001", conn=conn)

    assert state is not None
    assert state.evidence_pack is not None
    assert state.evidence_pack_id is not None


def test_resume_loads_specialist_findings():
    conn = _populate_fake_conn("run_sf_001")
    state = resume_council_run("run_sf_001", conn=conn)

    assert state is not None
    assert "technical" in state.specialist_findings
    assert "fundamental" in state.specialist_findings
    assert state.specialist_findings["technical"].stance == "long"


def test_resume_loads_plans():
    conn = _populate_fake_conn("run_plans_001")
    state = resume_council_run("run_plans_001", conn=conn)

    assert state is not None
    assert len(state.plans) == 1
    assert state.plans[0].central_question == "What is the best opportunity today?"
    assert len(state.plans[0].steps) == 1


def test_resume_loads_execution_results():
    conn = _populate_fake_conn("run_er_001")
    state = resume_council_run("run_er_001", conn=conn)

    assert state is not None
    plan_id = "run_er_001:plan_0"
    assert plan_id in state.execution_results
    assert "s1" in state.execution_results[plan_id]
    assert state.execution_results[plan_id]["s1"].status == "success"


def test_resume_loads_critic_reviews():
    conn = _populate_fake_conn("run_cr_001")
    state = resume_council_run("run_cr_001", conn=conn)

    assert state is not None
    assert len(state.critic_reviews) == 1
    assert state.critic_reviews[0][0].critic == "risk"


def test_resume_reconstructs_partial_decision():
    conn = _populate_fake_conn("run_dec_001")
    state = resume_council_run("run_dec_001", conn=conn)

    assert state is not None
    assert state.decision is not None
    assert state.decision.final_label == "RESEARCH_LONG"


def test_export_returns_json_serialisable_dict():
    conn = _populate_fake_conn("run_export_001")
    result = export_council_run("run_export_001", conn=conn)

    assert result["ok"] is True
    assert result["run_id"] == "run_export_001"
    artifact = result["artifact"]
    # Verify fully serialisable
    dumped = json.dumps(artifact, default=str)
    reloaded = json.loads(dumped)
    assert reloaded["run_id"] == "run_export_001"


def test_export_writes_file_when_output_path_given(tmp_path):
    conn = _populate_fake_conn("run_file_001")
    out = tmp_path / "exports" / "run_file_001.json"
    result = export_council_run("run_file_001", output_path=str(out), conn=conn)

    assert result["ok"] is True
    assert result["export_path"] == str(out)
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["run_id"] == "run_file_001"


def test_export_returns_not_found_for_missing_run():
    conn = FakeConnection()
    result = export_council_run("nonexistent", conn=conn)
    assert result["ok"] is False
    assert "not found" in result["error"]
