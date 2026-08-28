from company_intelligence.company_intelligence_pg import REQUIRED_TABLES, schema_sql


BROKER_TABLES = [
    "broker_sources",
    "broker_index_runs",
    "broker_reports",
    "broker_report_pages",
    "broker_report_tables",
    "broker_research_facts",
    "broker_research_runs",
]


def test_company_intel_schema_contains_broker_research_tables():
    sql = schema_sql()

    for table in BROKER_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS company_intel.{table}" in sql
        assert table in REQUIRED_TABLES


def test_company_intel_schema_contains_broker_research_indexes():
    sql = schema_sql()

    assert "idx_company_intel_broker_sources_active" in sql
    assert "idx_company_intel_broker_reports_symbol" in sql
    assert "idx_company_intel_broker_pages_search" in sql
    assert "idx_company_intel_broker_facts_symbol" in sql
