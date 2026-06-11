from __future__ import annotations

from pathlib import Path


class FakeSkillRepo:
    def __init__(self):
        self.cards = [
            {
                "id": "market_3m_rotation_swing_v1",
                "version": 1,
                "status": "production",
                "domain": "market_analysis",
                "title": "3M Market Rotation Swing",
                "description": "Market regime, sector rotation, and swing candidates.",
                "tags": ["market", "3m", "swing"],
                "input_patterns": ["last 3 months market analysis and swing candidates"],
                "output_contract": ["index_returns", "leading_sectors", "ranked_candidates"],
                "validation_rules": ["required_tables_exist", "sql_is_read_only"],
                "updated_at": "2026-06-07T10:00:00+05:30",
            },
            {
                "id": "vcp_breakouts_with_fundamentals_v1",
                "version": 1,
                "status": "validated",
                "domain": "screening",
                "title": "VCP Breakouts With Fundamentals",
                "description": "VCP and breakout candidates with fundamental quality.",
                "tags": ["vcp", "breakout", "fundamentals"],
                "input_patterns": ["VCP breakouts with fundamentals"],
                "output_contract": ["candidates", "tradingview_symbols", "risks"],
                "validation_rules": ["required_tables_exist", "sql_is_read_only"],
                "updated_at": "2026-06-07T09:00:00+05:30",
            },
            {
                "id": "generated_decoy_v1",
                "version": 1,
                "status": "generated",
                "domain": "screening",
                "title": "Generated Decoy",
                "description": "Untrusted generated card.",
                "tags": ["vcp"],
                "input_patterns": ["VCP"],
                "output_contract": ["decoy"],
                "validation_rules": [],
                "updated_at": "2026-06-06T09:00:00+05:30",
            },
        ]

    def list_skill_cards(self, status=None, domain=None):
        rows = list(self.cards)
        if status:
            rows = [row for row in rows if row["status"] == status]
        if domain:
            rows = [row for row in rows if row["domain"] == domain]
        return rows

    def list_runtime_eligible(self, domain=None):
        rows = [row for row in self.cards if row["status"] in {"validated", "production"}]
        if domain:
            rows = [row for row in rows if row["domain"] == domain]
        return rows

    def get_skill_card(self, skill_id, version=None):
        rows = [row for row in self.cards if row["id"] == skill_id]
        return rows[0] if rows else None

    def recent_activity(self, limit=10):
        return [
            {
                "kind": "retrieval",
                "skill_id": "vcp_breakouts_with_fundamentals_v1",
                "created_at": "2026-06-08T10:00:00+05:30",
                "validation_status": None,
                "elapsed_ms": 42,
            },
            {
                "kind": "execution",
                "skill_id": "market_3m_rotation_swing_v1",
                "created_at": "2026-06-08T09:55:00+05:30",
                "validation_status": "passed",
                "elapsed_ms": 120,
            },
        ][:limit]


def test_skills_summary_lists_status_counts_and_runtime_eligible_cards():
    from terminal.skills.commands_store import handle_skills_command

    output = handle_skills_command("/skills", repo=FakeSkillRepo())

    assert "Skill Store" in output
    assert "production: 1" in output
    assert "validated: 1" in output
    assert "generated: 1" in output
    assert "Runtime eligible: 2" in output
    assert "market_3m_rotation_swing_v1" in output


def test_skills_search_only_shows_runtime_eligible_matches():
    from terminal.skills.commands_store import handle_skills_command

    output = handle_skills_command("/skills search VCP fundamentals", repo=FakeSkillRepo())

    assert "vcp_breakouts_with_fundamentals_v1" in output
    assert "validated" in output
    assert "generated_decoy_v1" not in output


def test_skills_show_renders_contract_and_validation_details():
    from terminal.skills.commands_store import handle_skills_command

    output = handle_skills_command("/skills show market_3m_rotation_swing_v1", repo=FakeSkillRepo())

    assert "market_3m_rotation_swing_v1" in output
    assert "Output contract" in output
    assert "index_returns" in output
    assert "Validation rules" in output
    assert "sql_is_read_only" in output
    assert "2026-06-07" in output


def test_skills_recent_is_read_only_activity_view():
    from terminal.skills.commands_store import handle_skills_command

    output = handle_skills_command("/skills recent", repo=FakeSkillRepo())

    assert "Recent Skill Store Activity" in output
    assert "retrieval" in output
    assert "execution" in output
    assert "passed" in output


def test_skill_store_operator_docs_cover_required_topics():
    text = Path("docs/agent_adda_skill_store.md").read_text()

    required = [
        "generated skills are untrusted",
        "pgvector",
        "validate",
        "promote",
        "deprecate",
        "learning analyze",
        "proposal",
        "retrieval logs",
    ]
    lowered = text.lower()
    for term in required:
        assert term in lowered


def test_skills_command_is_documented_and_registered():
    nse_agent_text = Path("nse_agent.py").read_text()
    help_text = Path("terminal/help.py").read_text()

    assert 'name="skills"' in nse_agent_text
    assert '"/skills"' in nse_agent_text
    assert '"/skills"' in help_text
    assert '"skills"' in help_text


def test_skill_store_release_gate_preflight_does_not_enable_feature_flag(monkeypatch):
    from terminal.skills.config import skill_store_enabled
    from terminal.skills.release_gate import build_release_gate_report

    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "0")
    report = build_release_gate_report(
        benchmark_pass_rate=0.95,
        disabled_routing_passed=True,
        enabled_skill_tests_passed=True,
        unsafe_sql_tests_passed=True,
        retrieval_logs_written=True,
        learning_capture_safe=True,
        user_approved_enablement=False,
    )

    assert report["ready"] is False
    assert "user_approved_enablement" in report["blocked_by"]
    assert skill_store_enabled() is False


def test_skill_store_release_gate_allows_approved_runtime_enablement(monkeypatch):
    from terminal.skills.config import skill_store_enabled
    from terminal.skills.release_gate import build_release_gate_report

    monkeypatch.delenv("AGENT_ADDA_SKILL_STORE", raising=False)
    report = build_release_gate_report(
        benchmark_pass_rate=0.95,
        disabled_routing_passed=True,
        enabled_skill_tests_passed=True,
        unsafe_sql_tests_passed=True,
        retrieval_logs_written=True,
        learning_capture_safe=True,
        user_approved_enablement=True,
    )

    assert report["ready"] is True
    assert report["blocked_by"] == []
    assert report["would_enable_default"] is True
    assert skill_store_enabled() is True
