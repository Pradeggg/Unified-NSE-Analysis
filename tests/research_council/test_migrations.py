from pathlib import Path


MIGRATION = Path("postgres/migrations/20260526_research_council.sql")


def test_research_council_migration_exists_and_is_idempotent():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE SCHEMA IF NOT EXISTS recommendation_reports" in sql
    assert "ADD COLUMN IF NOT EXISTS council_mode" in sql
    assert "ADD COLUMN IF NOT EXISTS disclaimer_version" in sql
    assert "CREATE TABLE IF NOT EXISTS recommendation_reports.evidence_packs" in sql
    assert "CREATE TABLE IF NOT EXISTS recommendation_reports.agent_findings" in sql
    assert "CREATE TABLE IF NOT EXISTS recommendation_reports.execution_results" in sql
    assert "CREATE INDEX IF NOT EXISTS" in sql

    assert "ALTER TABLE recommendation_reports.runs\n    ADD COLUMN council_mode" not in sql
    assert "CREATE INDEX runs_council_mode_idx" not in sql


def test_research_council_migration_defines_required_artifact_tables():
    sql = MIGRATION.read_text(encoding="utf-8")

    required_tables = [
        "recommendation_reports.evidence_packs",
        "recommendation_reports.agent_findings",
        "recommendation_reports.branch_summaries",
        "recommendation_reports.council_plans",
        "recommendation_reports.execution_results",
        "recommendation_reports.strategy_specs",
        "recommendation_reports.backtest_results",
        "recommendation_reports.critic_reviews",
    ]

    for table in required_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql


def test_research_council_migration_keeps_existing_recommendation_schema_compatible():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "ALTER TABLE recommendation_reports.recommendations" in sql
    assert "ALTER TABLE signals.signal_log" in sql
    assert "council_run_id" in sql
    assert "v1.0_research_only" in sql
