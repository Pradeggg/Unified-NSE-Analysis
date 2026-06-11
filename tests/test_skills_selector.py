from terminal.skills.selector import select_skills
from terminal.entity_resolution import validate_requested_symbols


def test_selector_routes_eps_driver_questions_to_fundamental_driver_skill():
    selected = select_skills("Why is EPS of DMART going down?")

    assert selected
    assert selected[0].skill_id == "fundamental_driver_diagnosis"
    assert selected[0].metric == "eps"
    assert selected[0].symbol == "DMART"


def test_selector_routes_roce_driver_questions_to_fundamental_driver_skill():
    selected = select_skills("Why is ROCE high for POLYCAB?")

    assert selected
    assert selected[0].skill_id == "fundamental_driver_diagnosis"
    assert selected[0].metric == "roce"
    assert selected[0].symbol == "POLYCAB"


def test_selector_does_not_overroute_generic_stock_query():
    assert select_skills("Tell me about DMART") == []


def test_selector_does_not_overroute_comprehensive_fundamental_analysis():
    selected = select_skills(
        "Use LLM reasoning to perform a comprehensive deep fundamental analysis for DMART "
        "using cached PostgreSQL financial statements: quarterly sales, operating profit, "
        "PAT, EPS, annual ROCE, balance sheet and cash flow."
    )

    assert selected == []


def test_symbol_validation_ignores_accounting_metric_terms():
    validated = validate_requested_symbols(
        "Deep fundamental analysis for DMART with quarterly sales profit PAT EPS ROE ROCE and cash flow",
        executed_symbols=["DMART"],
    )

    assert validated["requested_symbols"] == ["DMART"]
    assert validated["missing_symbols"] == []
    assert validated["status"] == "ok"


def test_symbol_validation_ignores_pg_grounded_hyphenated_source_term():
    validated = validate_requested_symbols(
        "Use LLM reasoning for PG-grounded deep fundamental analysis of DMART",
        executed_symbols=["DMART"],
    )

    assert validated["requested_symbols"] == ["DMART"]
    assert validated["missing_symbols"] == []
