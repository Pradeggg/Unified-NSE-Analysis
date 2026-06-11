from __future__ import annotations


def test_safe_select_and_with_queries_pass():
    from terminal.skills.sql_safety import validate_sql_template

    select_result = validate_sql_template("SELECT symbol, close FROM prices.eod WHERE symbol = :symbol LIMIT 20")
    with_result = validate_sql_template(
        """
        WITH latest AS (
            SELECT symbol, close FROM prices.eod WHERE symbol = :symbol
        )
        SELECT symbol, close FROM latest LIMIT 20
        """,
        required_params=["symbol"],
        params={"symbol": "RELIANCE"},
    )

    assert select_result.passed is True
    assert with_result.passed is True
    assert with_result.errors == []


def test_dml_ddl_and_dangerous_functions_fail():
    from terminal.skills.sql_safety import validate_sql_template

    cases = [
        "INSERT INTO agent_skills.skill_cards(id) VALUES ('x')",
        "UPDATE scores.stage_snapshots SET trading_signal = 'BUY'",
        "DELETE FROM scores.stage_snapshots",
        "DROP TABLE scores.stage_snapshots",
        "CREATE TABLE tmp AS SELECT 1",
        "ALTER TABLE scores.stage_snapshots ADD COLUMN x text",
        "TRUNCATE scores.stage_snapshots",
        "GRANT SELECT ON scores.stage_snapshots TO public",
        "COPY scores.stage_snapshots TO '/tmp/x.csv'",
        "CALL refresh_scores()",
        "DO $$ BEGIN RAISE NOTICE 'x'; END $$",
        "SELECT pg_sleep(5)",
        "SELECT * INTO temp_results FROM scores.stage_snapshots",
        "SELECT * FROM scores.stage_snapshots FOR UPDATE",
        "SELECT * FROM scores.stage_snapshots FOR SHARE",
        "LOCK TABLE scores.stage_snapshots",
    ]

    for sql in cases:
        result = validate_sql_template(sql)
        assert result.passed is False, sql
        assert result.errors, sql


def test_multiple_statements_and_format_markers_fail():
    from terminal.skills.sql_safety import validate_sql_template

    chained = validate_sql_template("SELECT 1; SELECT 2")
    percent_format = validate_sql_template("SELECT * FROM scores.stage_snapshots WHERE symbol = '%s'")
    brace_format = validate_sql_template("SELECT * FROM {table_name} WHERE symbol = :symbol")
    f_string_marker = validate_sql_template("SELECT * FROM scores.stage_snapshots WHERE symbol = f'{symbol}'")

    assert chained.passed is False
    assert "multiple SQL statements are not allowed" in chained.errors
    assert percent_format.passed is False
    assert brace_format.passed is False
    assert f_string_marker.passed is False


def test_required_params_are_validated_against_supplied_params():
    from terminal.skills.sql_safety import validate_sql_template

    result = validate_sql_template(
        "SELECT * FROM scores.stage_snapshots WHERE symbol = :symbol AND snapshot_date >= :start_date",
        required_params=["symbol", "start_date"],
        params={"symbol": "RELIANCE"},
    )

    assert result.passed is False
    assert "missing required parameter: start_date" in result.errors


def test_expected_columns_are_validated_when_actual_columns_are_supplied():
    from terminal.skills.sql_safety import validate_sql_template

    result = validate_sql_template(
        "SELECT symbol, close FROM scores.stage_snapshots WHERE symbol = :symbol",
        expected_columns=["symbol", "close", "rsi"],
        actual_columns=["symbol", "close"],
    )

    assert result.passed is False
    assert "missing expected output column: rsi" in result.errors


def test_validation_result_is_json_serializable():
    from terminal.skills.sql_safety import validate_sql_template

    result = validate_sql_template("SELECT 1", required_params=["symbol"])

    assert result.to_dict() == {
        "passed": False,
        "errors": ["missing required parameter: symbol"],
        "warnings": [],
    }
