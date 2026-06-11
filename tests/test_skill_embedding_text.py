from __future__ import annotations


def _skill_payload():
    return {
        "id": "vcp_breakouts_with_fundamentals_v1",
        "version": 1,
        "status": "validated",
        "domain": "screening",
        "title": "VCP Breakouts With Fundamentals",
        "description": "Find stocks making new highs, VCP setups, and breakouts with strong fundamentals.",
        "input_patterns": [
            "stocks creating new highs or VCP or breakouts with good fundamentals",
            "quality breakout candidates for TradingView",
        ],
        "tags": ["vcp", "breakout", "new_high", "fundamentals"],
        "evidence_required": {
            "tables": ["scores.stage_snapshots", "scores.fundamental_scores"],
            "freshness": {"max_eod_age_days": 3},
            "intent_tags": ["screening", "quality_breakouts"],
        },
        "tool_plan_template": [
            {
                "name": "screen_candidates",
                "tool_name": "run_quality_breakout_screen",
                "params": {"min_score": 70},
            }
        ],
        "sql_templates": [
            {
                "name": "candidate_query",
                "sql": "SELECT secret_column FROM scores.stage_snapshots WHERE symbol = :symbol",
                "required_params": ["symbol"],
                "safety_status": "passed",
            }
        ],
        "output_contract": ["symbol", "setup_type", "technical_score", "fundamental_score", "tradingview_list"],
        "validation_rules": ["sql_is_read_only"],
        "metadata": {"owner": "agent_adda"},
    }


def test_embedding_text_contains_user_facing_skill_context():
    from terminal.skills.embedding_text import build_skill_embedding_text

    text = build_skill_embedding_text(_skill_payload())

    assert "Title: VCP Breakouts With Fundamentals" in text
    assert "Domain: screening" in text
    assert "Find stocks making new highs" in text
    assert "stocks creating new highs or VCP" in text
    assert "Tags: breakout, fundamentals, new_high, vcp" in text
    assert "Intent Tags: quality_breakouts, screening" in text
    assert "Evidence Tables: scores.fundamental_scores, scores.stage_snapshots" in text
    assert "Freshness: max_eod_age_days=3" in text
    assert "Output Contract: fundamental_score, setup_type, symbol, technical_score, tradingview_list" in text


def test_embedding_text_excludes_sql_by_default():
    from terminal.skills.embedding_text import build_skill_embedding_text

    text = build_skill_embedding_text(_skill_payload())

    assert "SELECT secret_column" not in text
    assert "scores.stage_snapshots WHERE" not in text
    assert "candidate_query" not in text


def test_embedding_text_is_normalized_and_deterministic():
    from terminal.skills.embedding_text import build_skill_embedding_text

    payload = _skill_payload()
    payload["description"] = "Find stocks\n\n     making new highs,\tVCP setups, and breakouts."

    first = build_skill_embedding_text(payload)
    second = build_skill_embedding_text({**payload, "tags": list(reversed(payload["tags"]))})

    assert "\n\n" not in first
    assert "\t" not in first
    assert "     " not in first
    assert first == second


def test_embedding_text_accepts_skill_card_objects():
    from terminal.skills.embedding_text import build_skill_embedding_text
    from terminal.skills.store_schema import skill_card_from_dict

    card = skill_card_from_dict(_skill_payload())

    assert build_skill_embedding_text(card) == build_skill_embedding_text(_skill_payload())


def test_embedding_text_can_include_sql_when_explicitly_requested():
    from terminal.skills.embedding_text import build_skill_embedding_text

    text = build_skill_embedding_text(_skill_payload(), include_sql=True)

    assert "SQL Templates: candidate_query" in text
    assert "SELECT secret_column FROM scores.stage_snapshots WHERE symbol = :symbol" in text
