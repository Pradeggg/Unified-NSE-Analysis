from __future__ import annotations

from rich.console import Console


class E2ERepo:
    def __init__(self):
        self.cards = [
            _card(
                "market_3m_rotation_swing_v1",
                "validated",
                "market_analysis",
                ["market_regime", "sector_rotation", "swing", "3m", "stage_analysis"],
                ["last 3 months market analysis and swing candidates"],
                ["market.index_eod", "scores.stage_snapshots"],
                ["ranked_candidates", "risks"],
            ),
            _card(
                "vcp_breakouts_with_fundamentals_v1",
                "validated",
                "screening",
                ["vcp", "breakout", "new_high", "fundamentals", "tradingview"],
                ["stocks creating new highs or VCP or breakouts with good fundamentals"],
                ["market.equity_eod", "scores.stage_snapshots"],
                ["candidates", "tradingview_symbols", "risks"],
            ),
            _card(
                "portfolio_incremental_add_trim_v1",
                "validated",
                "portfolio_review",
                ["portfolio", "position_sizing", "sector_exposure", "add_trim", "holdings"],
                ["should we add incrementally or reduce exposure"],
                ["portfolio.holdings", "scores.stage_snapshots"],
                ["portfolio_state", "add_candidates", "trim_candidates", "risk_flags"],
            ),
            _card(
                "generated_decoy_v1",
                "generated",
                "screening",
                ["vcp", "breakout", "portfolio", "market_regime"],
                ["stocks creating new highs or VCP"],
                ["market.equity_eod"],
                ["decoy"],
            ),
            _card(
                "test_failed_decoy_v1",
                "test_failed",
                "portfolio_review",
                ["portfolio", "add_trim", "holdings"],
                ["should we add incrementally or reduce exposure"],
                ["portfolio.holdings"],
                ["decoy"],
            ),
        ]

    def list_runtime_eligible(self, domain=None):
        rows = [row for row in self.cards if row["status"] in {"validated", "production"}]
        if domain:
            rows = [row for row in rows if row["domain"] == domain]
        return rows

    def search_vector_candidates(self, vector, model, *, limit=30, statuses=("validated", "production")):
        return []

    def log_retrieval(self, event):
        return 1


def test_skill_store_e2e_selects_core_flows_and_renders_trace(monkeypatch):
    from terminal.renderers.skill_store import render_skill_store_trace
    from terminal.skills.runtime_assessment import stage_skill_store_assessment

    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "1")
    repo = E2ERepo()
    cases = [
        ("last 3 months market analysis and swing candidates", "market_3m_rotation_swing_v1"),
        ("stocks creating new highs or VCP or breakouts with good fundamentals", "vcp_breakouts_with_fundamentals_v1"),
        ("should we add incrementally or reduce exposure", "portfolio_incremental_add_trim_v1"),
    ]

    selected = []
    for query, expected_skill_id in cases:
        assessment = stage_skill_store_assessment(
            query,
            repo=repo,
            feature_enabled=True,
            plan_mode=True,
        )
        assert assessment is not None
        assert assessment.selected_skill_id == expected_skill_id
        selected.append(assessment.selected_skill_id)

        console = Console(record=True, width=120)
        render_skill_store_trace(console, assessment)
        text = console.export_text()
        assert "Skill Store Trace" in text
        assert "Source trail" in text
        assert "Validation" in text
        assert "Evidence plan" in text
        assert expected_skill_id in text

    assert "generated_decoy_v1" not in selected
    assert "test_failed_decoy_v1" not in selected


def test_skill_store_e2e_bypasses_deterministic_slash_command(monkeypatch):
    from terminal.skills.runtime_assessment import stage_skill_store_assessment

    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "1")

    assert stage_skill_store_assessment("/screen stage2", repo=E2ERepo(), feature_enabled=True) is None


def _card(skill_id, status, domain, tags, input_patterns, tables, output_contract):
    return {
        "id": skill_id,
        "version": 1,
        "status": status,
        "domain": domain,
        "title": skill_id,
        "tags": tags,
        "input_patterns": input_patterns,
        "card_payload": {
            "id": skill_id,
            "version": 1,
            "status": status,
            "domain": domain,
            "title": skill_id,
            "description": skill_id,
            "input_patterns": input_patterns,
            "tags": tags,
            "evidence_required": {"tables": tables},
            "available_tables": tables,
            "tool_plan_template": [],
            "sql_templates": [],
            "output_contract": output_contract,
            "validation_rules": ["required_tables_exist", "sql_is_read_only"],
            "synthesis_guidance": "Use validated evidence only.",
            "intent_score": 0.9,
            "runtime_success_rate": 0.9,
        },
    }
