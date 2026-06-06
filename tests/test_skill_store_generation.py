from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_model_alias_normalizes_gpt55_spacing_to_model_id():
    from skill_store.config import normalize_model_name

    assert normalize_model_name("gpt-5.5") == "gpt-5.5"
    assert normalize_model_name("gpt 5.5") == "gpt-5.5"
    assert normalize_model_name("gpt_5_5") == "gpt-5.5"
    assert normalize_model_name("gpt-40") == "gpt-4o"
    assert normalize_model_name("gpt 4o") == "gpt-4o"


def test_config_loads_project_env_without_exposing_secret(tmp_path, monkeypatch):
    from skill_store.config import load_generation_config

    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=sk-test-secret",
                "OPENAI_MODEL=gpt-4o",
                "SKILL_STORE_MODEL=gpt 5.5",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("SKILL_STORE_MODEL", raising=False)

    cfg = load_generation_config(env_path=env_path)

    assert cfg.api_key_available is True
    assert cfg.model == "gpt-5.5"
    assert "secret" not in repr(cfg)


def test_default_generation_model_is_known_working_model(monkeypatch):
    from skill_store.config import load_generation_config

    monkeypatch.delenv("SKILL_STORE_MODEL", raising=False)

    cfg = load_generation_config(env_path=Path("/tmp/nonexistent-skill-store-env"))

    assert cfg.model == "gpt-4o"


def test_validate_skill_card_requires_runtime_safe_status():
    from skill_store.schema import validate_skill_card

    card = {
        "id": "market_3m_rotation_swing_v1",
        "version": 1,
        "status": "generated",
        "domain": "market_analysis",
        "title": "3M Market Rotation Swing Assessment",
        "description": "Analyze market regime and swing candidates.",
        "input_patterns": ["last 3 months market analysis"],
        "tags": ["market_regime", "swing_trading"],
        "evidence_required": {"tables": ["market.index_eod"]},
        "output_contract": ["market_regime", "candidates"],
        "validation_rules": ["required_tables_exist"],
    }

    assert validate_skill_card(card) == []
    bad = {**card, "status": "production"}
    assert any("status" in err for err in validate_skill_card(bad, generated_only=True))
    runtime_with_errors = {**card, "status": "validated", "validation_errors": ["bad sql"]}
    assert "runtime-eligible cards must not include validation_errors" in validate_skill_card(runtime_with_errors)


def test_dry_run_generation_writes_jsonl_and_yaml(tmp_path):
    from skill_store.generator import generate_skill_cards
    from skill_store.seeds import default_seed_briefs

    result = generate_skill_cards(
        seed_briefs=default_seed_briefs()[:2],
        output_dir=tmp_path,
        dry_run=True,
        count=2,
    )

    assert result.generated == 2
    assert result.jsonl_path.exists()
    assert len(result.yaml_paths) == 2
    rows = [json.loads(line) for line in result.jsonl_path.read_text().splitlines()]
    assert [row["status"] for row in rows] == ["generated", "generated"]
    assert all(row["id"] for row in rows)
    assert all("output_contract" in row for row in rows)


def test_generation_can_run_review_heal_pipeline_when_requested(tmp_path):
    from skill_store.generator import generate_skill_cards
    from skill_store.seeds import default_seed_briefs

    result = generate_skill_cards(
        seed_briefs=default_seed_briefs()[:1],
        output_dir=tmp_path,
        dry_run=True,
        count=1,
        review_heal=True,
    )

    rows = [json.loads(line) for line in result.jsonl_path.read_text().splitlines()]

    assert result.errors == ()
    assert rows[0]["status"] == "review_pending"
    assert rows[0]["review"]["status"] == "pass"
    assert "validation_errors" not in rows[0]


def test_expanded_seed_briefs_generate_unique_schema_safe_varieties():
    from skill_store.schema_catalog import default_schema_catalog
    from skill_store.seeds import expanded_seed_briefs

    seeds = expanded_seed_briefs(1000)
    catalog = default_schema_catalog()

    assert len(seeds) == 1000
    assert len({seed.id for seed in seeds}) == 1000
    assert all(seed.input_patterns for seed in seeds)
    assert all(catalog.has_table(table) for seed in seeds for table in seed.evidence_tables)


def test_dry_run_generation_supports_target_count_batches_and_model_override(tmp_path):
    from skill_store.config import GenerationConfig
    from skill_store.generator import generate_skill_cards

    result = generate_skill_cards(
        output_dir=tmp_path,
        dry_run=True,
        target_count=15,
        batch_size=5,
        parallelism=3,
        config=GenerationConfig(model="gpt-4o", api_key_available=True, env_path=tmp_path / ".env"),
    )
    rows = [json.loads(line) for line in result.jsonl_path.read_text().splitlines()]

    assert result.generated == 15
    assert result.model == "gpt-4o"
    assert len(rows) == 15
    assert len({row["id"] for row in rows}) == 15
    assert {row["generation_model"] for row in rows} == {"gpt-4o"}


def test_generation_writes_batch_checkpoints(tmp_path):
    from skill_store.config import GenerationConfig
    from skill_store.generator import generate_skill_cards

    result = generate_skill_cards(
        output_dir=tmp_path,
        dry_run=True,
        target_count=12,
        batch_size=5,
        parallelism=3,
        config=GenerationConfig(model="gpt-4o", api_key_available=True, env_path=tmp_path / ".env"),
    )
    checkpoints = sorted(tmp_path.glob("checkpoint_*.jsonl"))

    assert result.generated == 12
    assert [path.name for path in checkpoints] == [
        "checkpoint_0001.jsonl",
        "checkpoint_0002.jsonl",
        "checkpoint_0003.jsonl",
    ]
    assert [len(path.read_text().splitlines()) for path in checkpoints] == [5, 5, 2]


def test_generation_prompt_includes_approved_schema_columns():
    from skill_store.generator import build_generation_prompt
    from skill_store.schema_catalog import default_schema_catalog
    from skill_store.seeds import default_seed_briefs

    prompt = build_generation_prompt(default_seed_briefs()[1], default_schema_catalog())
    schema = prompt["approved_schema"]

    assert schema["scores.stage2_vcp_picks"]["columns"] == [
        "snapshot_date",
        "rank",
        "symbol",
        "company_name",
        "sector",
        "price",
        "live_price",
        "price_date",
        "change_1d_pct",
        "change_1w_pct",
        "rsi",
        "relative_strength",
        "trading_signal",
        "trend_signal",
        "supertrend_state",
        "investment_score",
        "enhanced_fund_score",
        "earnings_quality",
        "sales_growth",
        "financial_strength",
        "vcp_score",
        "vcp_breakout_pct",
        "vcp_contraction_pct",
        "stance",
        "narrative",
        "fund_details",
        "source_report",
        "created_at",
        "updated_at",
    ]
    assert "pivot_price" not in schema["scores.stage2_vcp_picks"]["columns"]
    assert "Use only these approved tables and columns" in " ".join(prompt["rules"])
    assert "Python evidence tools are allowed only when SQL would become complex" in " ".join(prompt["rules"])
    assert prompt["python_tool_policy"]["required_function"] == "run(context)"
    assert "python_tools" in prompt["optional_keys"]


def test_generation_prompt_includes_data_model_join_and_column_semantics():
    from skill_store.generator import build_generation_prompt
    from skill_store.schema_catalog import default_schema_catalog
    from skill_store.seeds import default_seed_briefs

    prompt = build_generation_prompt(default_seed_briefs()[0], default_schema_catalog())
    schema = prompt["approved_schema"]

    stage = schema["scores.stage_snapshots"]
    assert stage["primary_key"] == ["snapshot_date", "symbol"]
    assert stage["latest_date_column"] == "snapshot_date"
    assert stage["column_details"]["stage"]["examples"] == [
        "STAGE_1",
        "STAGE_2",
        "STAGE_3",
        "STAGE_4",
        "UNKNOWN",
    ]
    assert "Use stage = 'STAGE_2'" in " ".join(stage["common_filters"])

    join_conditions = {rule["condition"] for rule in schema["_join_rules"]["rules"]}
    assert "market.equity_eod.symbol = scores.stage_snapshots.symbol" in join_conditions
    assert "market.equity_eod.trade_date = scores.stage_snapshots.snapshot_date" in join_conditions
    assert "scores.stage2_vcp_picks.symbol = scores.stage_snapshots.symbol" in join_conditions

    global_rules = " ".join(schema["_global_rules"]["rules"])
    assert "PostgreSQL syntax" in global_rules
    assert "never use stage = 2" in global_rules
    assert "Use approved_schema._join_rules for joins" in " ".join(prompt["rules"])


def test_schema_catalog_prompt_has_complete_column_metadata():
    from skill_store.schema_catalog import default_schema_catalog

    catalog = default_schema_catalog()
    payload = catalog.as_prompt_payload()
    incomplete = []

    for table_name, table_payload in payload.items():
        if table_name.startswith("_"):
            continue
        for column_name, detail in table_payload["column_details"].items():
            if detail["data_type"] in ("", "unknown") or not detail["description"]:
                incomplete.append(f"{table_name}.{column_name}")

    assert incomplete == []


def test_flow_regime_breadth_prompt_includes_date_grain_joins_and_top_level_rules():
    from skill_store.generator import build_generation_prompt
    from skill_store.schema_catalog import default_schema_catalog
    from skill_store.seeds import default_seed_briefs

    seed = next(seed for seed in default_seed_briefs() if seed.id == "fii_dii_regime_breadth_review")
    prompt = build_generation_prompt(seed, default_schema_catalog())
    nested_rules = prompt["approved_schema"]["_join_rules"]["rules"]
    top_level_rules = prompt["schema_join_rules"]
    conditions = {rule["condition"] for rule in nested_rules}

    assert top_level_rules == nested_rules
    assert "signals.fii_dii_flows.trade_date = signals.regime_history.trade_date" in conditions
    assert "signals.fii_dii_flows.trade_date = breadth.market_daily.trade_date" in conditions
    assert "signals.fii_dii_flows.trade_date = market.index_eod.trade_date" in conditions
    assert prompt["global_sql_rules"] == prompt["approved_schema"]["_global_rules"]["rules"]


def test_default_seed_evidence_tables_are_in_schema_catalog():
    from skill_store.schema_catalog import default_schema_catalog
    from skill_store.seeds import default_seed_briefs

    catalog = default_schema_catalog()

    missing = [
        table
        for seed in default_seed_briefs()
        for table in seed.evidence_tables
        if not catalog.has_table(table)
    ]

    assert missing == []


def test_default_seed_library_covers_real_life_agent_adda_usage():
    from skill_store.seeds import default_seed_briefs

    seeds = default_seed_briefs()
    domains = {seed.domain for seed in seeds}
    tags = {tag for seed in seeds for tag in seed.tags}

    assert len(seeds) >= 12
    assert {
        "market_analysis",
        "screening",
        "portfolio_review",
        "report_qa",
        "fundamental_analysis",
        "data_quality",
        "event_analysis",
    }.issubset(domains)
    assert {"quarterly_results", "fii_dii", "corporate_events", "breadth", "research"}.issubset(tags)


def test_schema_auditor_rejects_unknown_columns_and_tables():
    from skill_store.schema_auditor import audit_skill_card
    from skill_store.schema_catalog import default_schema_catalog

    bad_card = {
        "id": "bad_vcp_v1",
        "evidence_required": {"tables": ["scores.stage2_vcp_picks", "reports.files"]},
        "sql_templates": {
            "bad": (
                "SELECT symbol, pivot_price, as_of_date "
                "FROM scores.stage2_vcp_picks"
            )
        },
    }

    findings = audit_skill_card(bad_card, default_schema_catalog())

    assert "unknown table reports.files" in findings
    assert "scores.stage2_vcp_picks.pivot_price is not approved" in findings
    assert "scores.stage2_vcp_picks.as_of_date is not approved" in findings


def test_schema_auditor_rejects_common_generated_sql_semantic_mistakes():
    from skill_store.schema_auditor import audit_skill_card
    from skill_store.schema_catalog import default_schema_catalog

    card = {
        "id": "bad_stage_sql_v1",
        "evidence_required": {"tables": ["scores.stage_snapshots"]},
        "sql_templates": {
            "bad": (
                "SELECT symbol FROM scores.stage_snapshots "
                "WHERE stage = 2 AND snapshot_date >= date('now', '-3 months')"
            ),
            "bad_vcp": "SELECT symbol FROM scores.stage_snapshots WHERE stage = 'VCP'",
        },
    }

    findings = audit_skill_card(card, default_schema_catalog())

    assert "stage = 2 is not approved; use stage = 'STAGE_2'" in findings
    assert "stage = 'VCP' is not approved; use scores.stage2_vcp_picks for VCP evidence" in findings
    assert any("SQLite date('now', ...) syntax is not approved" in finding for finding in findings)


def test_schema_auditor_ignores_parameters_and_cte_columns():
    from skill_store.schema_auditor import audit_skill_card
    from skill_store.schema_catalog import default_schema_catalog

    card = {
        "id": "parameterized_vcp_v1",
        "evidence_required": {"tables": ["scores.stage2_vcp_picks"]},
        "sql_templates": {
            "ok": (
                "WITH params AS (SELECT :as_of_date AS as_of_date), "
                "latest AS (SELECT symbol, snapshot_date, vcp_score FROM scores.stage2_vcp_picks "
                "WHERE snapshot_date <= (SELECT as_of_date FROM params) "
                "AND vcp_score >= {{min_vcp_score}}) "
                "SELECT symbol, snapshot_date, vcp_score FROM latest ORDER BY vcp_score DESC"
            )
        },
    }

    assert audit_skill_card(card, default_schema_catalog()) == []


def test_schema_auditor_ignores_sql_operators_and_string_literals():
    from skill_store.schema_auditor import audit_skill_card
    from skill_store.schema_catalog import default_schema_catalog

    card = {
        "id": "eod_between_v1",
        "evidence_required": {"tables": ["market.equity_eod"]},
        "sql_templates": {
            "ok": (
                "SELECT symbol, trade_date, close FROM market.equity_eod "
                "WHERE trade_date BETWEEN :start_date AND :end_date "
                "AND series = 'EQ'"
            )
        },
    }

    assert audit_skill_card(card, default_schema_catalog()) == []


def test_schema_auditor_understands_table_alias_columns():
    from skill_store.schema_auditor import audit_skill_card
    from skill_store.schema_catalog import default_schema_catalog

    card = {
        "id": "alias_join_v1",
        "evidence_required": {"tables": ["market.equity_eod", "scores.stage_snapshots"]},
        "sql_templates": {
            "ok": (
                "SELECT e.symbol, e.close, s.stage, s.enhanced_fund_score "
                "FROM market.equity_eod e "
                "JOIN scores.stage_snapshots s ON s.symbol = e.symbol"
            )
        },
    }

    assert audit_skill_card(card, default_schema_catalog()) == []


def test_card_from_seed_keeps_deterministic_seed_id_for_expanded_variants():
    from skill_store.generator import _card_from_seed
    from skill_store.seeds import expanded_seed_briefs

    seed = expanded_seed_briefs(1)[0]
    card = _card_from_seed(
        seed,
        model="gpt-4o",
        llm_payload={"id": "agent_adda_skill_card_001", "title": "LLM title"},
    )

    assert card["id"] == "market_3m_rotation_swing_0001_v1"


def test_card_from_seed_normalizes_evidence_tables_and_marks_schema_failures():
    from skill_store.generator import _card_from_seed
    from skill_store.schema_auditor import audit_skill_card
    from skill_store.schema_catalog import default_schema_catalog
    from skill_store.seeds import default_seed_briefs

    seed = default_seed_briefs()[1]
    payload = {
        "id": "vcp_breakouts_with_fundamentals",
        "evidence_required": {"primary_tables": ["scores.stage2_vcp_picks"]},
        "sql_templates": {"bad": "SELECT symbol, pivot_price FROM scores.stage2_vcp_picks"},
    }
    card = _card_from_seed(seed, model="gpt-5.5", llm_payload=payload)

    assert card["evidence_required"]["tables"] == ["scores.stage2_vcp_picks"]
    assert audit_skill_card(card, default_schema_catalog()) == [
        "scores.stage2_vcp_picks.pivot_price is not approved"
    ]


def test_card_from_seed_normalizes_llm_shape_drift():
    from skill_store.generator import _card_from_seed
    from skill_store.seeds import default_seed_briefs

    seed = default_seed_briefs()[0]
    card = _card_from_seed(
        seed,
        model="gpt-4o",
        llm_payload={
            "input_patterns": "last 3 months market analysis",
            "tags": "market",
            "tool_plan_template": "run the approved SQL templates",
            "python_tools": {"id": "ignored_without_contract"},
            "output_contract": "summary",
            "validation_rules": "read_only",
        },
    )

    assert card["input_patterns"] == ["last 3 months market analysis"]
    assert card["tags"] == ["market"]
    assert card["tool_plan_template"] == [{"description": "run the approved SQL templates"}]
    assert card["python_tools"] == [{"id": "ignored_without_contract"}]
    assert card["output_contract"] == ["summary"]
    assert card["validation_rules"] == ["read_only"]


def test_skill_store_loads_generated_jsonl_and_keeps_cards_quarantined():
    from skill_store.testing import load_jsonl_cards, safety_findings

    cards = load_jsonl_cards(Path("skill_store/generated/generated_skill_cards_20260606_111519.jsonl"))

    assert len(cards) == 4
    assert {card["status"] for card in cards} == {"generated"}
    assert all(card["generation_model"] == "gpt-5.5" for card in cards)
    assert safety_findings(cards) == []


@pytest.mark.parametrize(
    ("query", "expected_skill_id"),
    [
        ("last 3 months market analysis and swing candidates", "market_3m_rotation_swing_v1"),
        ("get stocks creating new highs or VCP breakouts with good fundamentals", "vcp_breakouts_with_fundamentals_v1"),
        ("review my portfolio holdings for incremental add or trim by sector exposure", "portfolio_incremental_add_trim_v1"),
        ("review report links not working and underlying stock html files missing data", "report_link_data_validation_v1"),
    ],
)
def test_generated_skill_store_selects_expected_skill_for_realistic_queries(query, expected_skill_id):
    from skill_store.testing import load_jsonl_cards, select_candidate_skills

    cards = load_jsonl_cards(Path("skill_store/generated/generated_skill_cards_20260606_111519.jsonl"))
    selected = select_candidate_skills(query, cards, limit=2)

    assert selected
    assert selected[0]["id"] == expected_skill_id
    assert selected[0]["score"] > 0


def test_generated_skill_selector_does_not_route_unrelated_query():
    from skill_store.testing import load_jsonl_cards, select_candidate_skills

    cards = load_jsonl_cards(Path("skill_store/generated/generated_skill_cards_20260606_111519.jsonl"))

    assert select_candidate_skills("what is the weather in mumbai today", cards) == []


def test_runtime_skill_selector_only_routes_approved_runtime_cards():
    from skill_store.testing import select_runtime_skills

    cards = [
        {
            "id": "generated_market_v1",
            "status": "review_pending",
            "domain": "market_analysis",
            "title": "Market Review",
            "description": "last 3 months market analysis",
            "input_patterns": ["last 3 months market analysis"],
            "tags": ["market"],
        },
        {
            "id": "runtime_market_v1",
            "status": "validated",
            "domain": "market_analysis",
            "title": "Market Review",
            "description": "last 3 months market analysis",
            "input_patterns": ["last 3 months market analysis"],
            "tags": ["market"],
        },
    ]

    selected = select_runtime_skills("last 3 months market analysis", cards)

    assert [item["id"] for item in selected] == ["runtime_market_v1"]


def test_python_tool_policy_allows_read_only_run_function():
    from skill_store.code_policy import audit_python_tool

    tool = {
        "id": "sector_ranker",
        "language": "python",
        "mode": "read_only",
        "inputs": ["rows"],
        "outputs": ["ranked"],
        "approved_tables": ["scores.stage_snapshots"],
        "code": (
            "def run(context):\n"
            "    rows = context.get('rows', [])\n"
            "    ranked = sorted(rows, key=lambda row: row.get('score', 0), reverse=True)\n"
            "    return {'ranked': ranked[:10]}\n"
        ),
    }

    assert audit_python_tool(tool) == []


def test_python_tool_policy_blocks_writes_network_and_subprocess():
    from skill_store.code_policy import audit_python_tool

    tool = {
        "id": "unsafe",
        "language": "python",
        "mode": "read_only",
        "inputs": [],
        "outputs": [],
        "approved_tables": [],
        "code": (
            "import os\n"
            "import requests\n"
            "def run(context):\n"
            "    os.system('echo bad')\n"
            "    open('/tmp/x', 'w').write('bad')\n"
            "    return {}\n"
        ),
    }

    findings = audit_python_tool(tool)

    assert "import os is not allowed" in findings
    assert "import requests is not allowed" in findings
    assert "call os.system is not allowed" in findings
    assert "call open is not allowed" in findings


def test_python_tool_policy_rejects_non_string_outputs_without_crashing_runner():
    from skill_store.code_policy import audit_python_tool
    from skill_store.test_runner import run_python_tool_test

    tool = {
        "id": "bad_outputs",
        "language": "python",
        "mode": "read_only",
        "inputs": [],
        "outputs": [{"name": "ok"}],
        "approved_tables": ["report.enhanced_runs"],
        "code": "def run(context):\n    return {'ok': True}\n",
    }

    assert "bad_outputs: outputs must contain only strings" in audit_python_tool(tool)
    result = run_python_tool_test(tool, {})
    assert result.passed is False
    assert "bad_outputs: outputs must contain only strings" in result.findings


def test_python_tool_runner_executes_policy_clean_tool():
    from skill_store.test_runner import run_python_tool_test

    tool = {
        "id": "count_rows",
        "language": "python",
        "mode": "read_only",
        "inputs": ["rows"],
        "outputs": ["count"],
        "approved_tables": ["market.equity_eod"],
        "code": "def run(context):\n    return {'count': len(context.get('rows', []))}\n",
    }

    result = run_python_tool_test(tool, {"rows": [{"symbol": "ABC"}, {"symbol": "XYZ"}]})

    assert result.passed is True
    assert result.output == {"count": 2}
    assert result.findings == []


def test_python_tool_runner_times_out_infinite_loop():
    from skill_store.test_runner import run_python_tool_test

    tool = {
        "id": "loop",
        "language": "python",
        "mode": "read_only",
        "inputs": [],
        "outputs": ["ok"],
        "approved_tables": ["market.equity_eod"],
        "code": "def run(context):\n    while True:\n        pass\n    return {'ok': True}\n",
    }

    result = run_python_tool_test(tool, {}, timeout_seconds=0.2)

    assert result.passed is False
    assert result.findings == ["execution timed out"]


def test_pipeline_heals_bad_generated_python_tool():
    from skill_store.pipeline import run_review_heal_pipeline
    from skill_store.reviewer import ReviewDecision

    bad_card = {
        "id": "bad_python_tool_v1",
        "version": 1,
        "status": "generated",
        "domain": "report_qa",
        "title": "Bad Python Tool",
        "description": "Bad generated tool.",
        "input_patterns": ["bad generated tool"],
        "tags": ["test"],
        "evidence_required": {"tables": ["report.enhanced_runs"]},
        "python_tools": [
            {
                "id": "bad",
                "language": "python",
                "mode": "read_only",
                "inputs": [],
                "outputs": ["ok"],
                "approved_tables": ["report.enhanced_runs"],
                "code": "import os\ndef run(context):\n    os.system('echo bad')\n    return {'ok': False}\n",
            }
        ],
        "output_contract": ["ok"],
        "validation_rules": ["read_only_python"],
    }

    def reviewer(card, findings):
        return ReviewDecision(status="needs_heal" if findings else "pass", findings=findings)

    def healer(card, findings):
        healed = dict(card)
        healed["python_tools"] = [
            {
                "id": "good",
                "language": "python",
                "mode": "read_only",
                "inputs": [],
                "outputs": ["ok"],
                "approved_tables": ["report.enhanced_runs"],
                "code": "def run(context):\n    return {'ok': True}\n",
            }
        ]
        return healed

    result = run_review_heal_pipeline(bad_card, reviewer=reviewer, healer=healer, max_attempts=2)

    assert result.card["status"] == "review_pending"
    assert result.attempts == 2
    assert result.findings == []
    assert result.card["review"]["status"] == "pass"


def test_failed_corpus_healing_pass_promotes_repaired_cards(tmp_path):
    from skill_store.healing_pass import heal_failed_jsonl

    source = tmp_path / "failed.jsonl"
    source.write_text(
        json.dumps(
            {
                "id": "bad_python_tool_v1",
                "version": 1,
                "status": "test_failed",
                "domain": "report_qa",
                "title": "Bad Python Tool",
                "description": "Bad generated tool.",
                "input_patterns": ["bad generated tool"],
                "tags": ["test"],
                "evidence_required": {"tables": ["report.enhanced_runs"]},
                "python_tools": [
                    {
                        "id": "bad",
                        "language": "python",
                        "mode": "read_only",
                        "inputs": [],
                        "outputs": ["ok"],
                        "approved_tables": ["report.enhanced_runs"],
                        "code": "import os\ndef run(context):\n    os.system('echo bad')\n    return {'ok': False}\n",
                    }
                ],
                "output_contract": ["ok"],
                "validation_rules": ["read_only_python"],
                "validation_errors": ["import os is not allowed"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def healer(card, findings):
        healed = dict(card)
        healed["python_tools"] = [
            {
                "id": "good",
                "language": "python",
                "mode": "read_only",
                "inputs": [],
                "outputs": ["ok"],
                "approved_tables": ["report.enhanced_runs"],
                "code": "def run(context):\n    return {'ok': True}\n",
            }
        ]
        return healed

    result = heal_failed_jsonl(
        source,
        tmp_path / "healed",
        healer=healer,
        max_attempts=2,
        parallelism=1,
    )

    healed_rows = [json.loads(line) for line in result.jsonl_path.read_text().splitlines()]

    assert result.total == 1
    assert result.before_status_counts["test_failed"] == 1
    assert result.after_status_counts["review_pending"] == 1
    assert healed_rows[0]["status"] == "review_pending"


def test_failed_corpus_healing_pass_writes_checkpoints(tmp_path):
    from skill_store.healing_pass import heal_failed_jsonl

    source = tmp_path / "failed.jsonl"
    rows = []
    for idx in range(3):
        rows.append(
            {
                "id": f"bad_python_tool_{idx}_v1",
                "version": 1,
                "status": "test_failed",
                "domain": "report_qa",
                "title": "Bad Python Tool",
                "description": "Bad generated tool.",
                "input_patterns": ["bad generated tool"],
                "tags": ["test"],
                "evidence_required": {"tables": ["report.enhanced_runs"]},
                "python_tools": [
                    {
                        "id": "bad",
                        "language": "python",
                        "mode": "read_only",
                        "inputs": [],
                        "outputs": ["ok"],
                        "approved_tables": ["report.enhanced_runs"],
                        "code": "import os\ndef run(context):\n    os.system('echo bad')\n    return {'ok': False}\n",
                    }
                ],
                "output_contract": ["ok"],
                "validation_rules": ["read_only_python"],
            }
        )
    source.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")

    def healer(card, findings):
        healed = dict(card)
        healed["python_tools"] = [
            {
                "id": "good",
                "language": "python",
                "mode": "read_only",
                "inputs": [],
                "outputs": ["ok"],
                "approved_tables": ["report.enhanced_runs"],
                "code": "def run(context):\n    return {'ok': True}\n",
            }
        ]
        return healed

    result = heal_failed_jsonl(
        source,
        tmp_path / "healed",
        healer=healer,
        max_attempts=2,
        parallelism=1,
        checkpoint_size=2,
    )

    checkpoints = sorted((tmp_path / "healed").glob("checkpoint_*.jsonl"))

    assert result.after_status_counts["review_pending"] == 3
    assert len(checkpoints) == 2
    assert sum(1 for path in checkpoints for _ in path.read_text().splitlines()) == 3


def test_failed_corpus_healing_pass_preserves_identity_when_healer_omits_it(tmp_path):
    from skill_store.healing_pass import heal_failed_jsonl

    source = tmp_path / "failed.jsonl"
    source.write_text(
        json.dumps(
            {
                "id": "identity_should_survive_v1",
                "version": 1,
                "status": "test_failed",
                "domain": "report_qa",
                "title": "Identity Should Survive",
                "description": "Bad generated tool.",
                "input_patterns": ["bad generated tool"],
                "tags": ["test"],
                "evidence_required": {"tables": ["report.enhanced_runs"]},
                "output_contract": ["ok"],
                "validation_rules": ["read_only_python"],
                "validation_errors": ["synthetic failure"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = heal_failed_jsonl(
        source,
        tmp_path / "healed",
        healer=lambda card, findings: {"status": "generated"},
        max_attempts=1,
        parallelism=1,
    )
    row = json.loads(result.jsonl_path.read_text().splitlines()[0])

    assert row["id"] == "identity_should_survive_v1"
    assert row["title"] == "Identity Should Survive"
    assert "id is required" not in row.get("validation_errors", [])


def test_reaudit_jsonl_quarantines_runtime_statuses(tmp_path):
    from skill_store.reaudit import reaudit_jsonl

    source = tmp_path / "stale.jsonl"
    source.write_text(
        json.dumps(
            {
                "id": "stale_validated_v1",
                "version": 1,
                "status": "validated",
                "domain": "market_analysis",
                "title": "Stale Validated",
                "description": "Previously generated runtime card.",
                "input_patterns": ["last 3 months market analysis"],
                "tags": ["market"],
                "evidence_required": {"tables": ["market.index_eod"]},
                "sql_templates": [
                    {
                        "template": (
                            "SELECT trade_date, index_symbol, close "
                            "FROM market.index_eod "
                            "WHERE trade_date = (SELECT MAX(trade_date) FROM market.index_eod)"
                        )
                    }
                ],
                "tool_plan_template": [],
                "output_contract": ["rows"],
                "validation_rules": ["required_tables_exist"],
                "validation_errors": ["old error should be recomputed"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = reaudit_jsonl(source, tmp_path / "reaudited", checkpoint_size=1)
    row = json.loads(result.jsonl_path.read_text().splitlines()[0])

    assert result.before_status_counts["validated"] == 1
    assert result.after_status_counts["review_pending"] == 1
    assert row["status"] == "review_pending"
    assert row["reaudit"]["runtime_quarantined"] is True
    assert row["reaudit"]["original_status"] == "validated"
    assert "validation_errors" not in row
