from __future__ import annotations

from pathlib import Path


def _schema_sql() -> str:
    return Path("postgres/schema.sql").read_text(encoding="utf-8")


def _normalized_schema_sql() -> str:
    return " ".join(_schema_sql().split()).lower()


def test_agent_skills_schema_and_pgvector_extension_are_declared():
    sql = _normalized_schema_sql()

    assert "create extension if not exists vector" in sql
    assert "create schema if not exists agent_skills" in sql


def test_agent_skills_required_tables_are_declared():
    sql = _normalized_schema_sql()

    for table in [
        "agent_skills.skill_cards",
        "agent_skills.skill_embeddings",
        "agent_skills.skill_sql_templates",
        "agent_skills.skill_tests",
        "agent_skills.skill_validation_runs",
        "agent_skills.skill_retrieval_logs",
        "agent_skills.skill_execution_logs",
        "agent_skills.skill_feedback",
    ]:
        assert f"create table if not exists {table}" in sql


def test_agent_skills_status_lifecycle_is_constrained():
    sql = _normalized_schema_sql()

    for status in [
        "generated",
        "test_failed",
        "review_pending",
        "validated",
        "production",
        "deprecated",
    ]:
        assert f"'{status}'" in sql
    assert "check (status in (" in sql


def test_agent_skills_identity_embedding_and_indexes_are_declared():
    sql = _normalized_schema_sql()

    assert "unique (id, version)" in sql
    assert "embedding_model" in sql
    assert "embedding_dimension" in sql
    assert "vector(384)" in sql
    assert "using ivfflat" in sql or "using hnsw" in sql

    for index_name in [
        "idx_agent_skill_cards_status",
        "idx_agent_skill_cards_domain",
        "idx_agent_skill_cards_tags",
        "idx_agent_skill_embeddings_embedding",
    ]:
        assert index_name in sql
