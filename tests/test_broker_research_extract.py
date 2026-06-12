from broker_research.extract import (
    build_page_bounded_fact_prompt,
    extract_deterministic_facts,
    extract_and_store_facts_from_pages,
    extract_facts_from_pages,
    validate_llm_fact_payload,
)


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def executemany(self, sql, params):
        self.conn.executed.append((sql, list(params)))


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.commits = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1


def test_extract_deterministic_facts_finds_rating_target_and_valuation():
    facts = extract_deterministic_facts(
        broker_report_id=10,
        symbol="BEL",
        page_number=1,
        text="We maintain BUY rating with a target price of Rs 520. Valuation: 36x FY27E P/E.",
    )

    by_type = {fact["fact_type"]: fact for fact in facts}
    assert by_type["rating"]["fact_value"] == "BUY"
    assert by_type["target_price"]["fact_value"] == "520"
    assert by_type["target_price"]["unit"] == "INR"
    assert by_type["valuation_method"]["fact_value"] == "P/E"
    assert by_type["valuation_method"]["period"] == "FY27E"


def test_extract_facts_from_pages_captures_risk_and_catalyst_snippets():
    pages = [
        {
            "page_number": 2,
            "text": "Key catalysts include defence order wins and margin expansion. Risks include execution delay and slower ordering.",
        }
    ]

    facts = extract_facts_from_pages(broker_report_id=10, symbol="BEL", pages=pages)

    fact_types = [fact["fact_type"] for fact in facts]
    assert "catalyst" in fact_types
    assert "risk" in fact_types
    assert all(fact["page_number"] == 2 for fact in facts)


def test_build_page_bounded_fact_prompt_includes_only_requested_chunks():
    prompt = build_page_bounded_fact_prompt(
        symbol="BEL",
        pages=[
            {"page_number": 1, "text": "BUY target Rs 520"},
            {"page_number": 2, "text": "Risks include execution delay"},
        ],
    )

    assert "Return JSON only" in prompt
    assert "Page 1:" in prompt
    assert "Page 2:" in prompt
    assert "page_number" in prompt


def test_validate_llm_fact_payload_rejects_out_of_bounds_pages():
    payload = {
        "facts": [
            {
                "fact_type": "thesis",
                "fact_name": "core_thesis",
                "fact_value": "Order book supports growth.",
                "page_number": 1,
                "confidence": 0.8,
            },
            {
                "fact_type": "risk",
                "fact_name": "unsupported_page",
                "fact_value": "Unsupported.",
                "page_number": 9,
                "confidence": 0.9,
            },
        ]
    }

    facts, rejected = validate_llm_fact_payload(
        payload,
        broker_report_id=10,
        symbol="BEL",
        allowed_page_numbers={1, 2},
    )

    assert len(facts) == 1
    assert facts[0]["extractor"] == "llm"
    assert facts[0]["page_number"] == 1
    assert rejected == [{"fact_name": "unsupported_page", "reason": "page_number_not_in_context"}]


def test_extract_and_store_facts_from_pages_persists_deterministic_facts():
    conn = FakeConnection()

    result = extract_and_store_facts_from_pages(
        conn,
        broker_report_id=10,
        symbol="BEL",
        pages=[{"page_number": 1, "text": "BUY with target price Rs 520", "char_count": 28}],
    )

    sql = conn.executed[0][0]
    params = conn.executed[0][1]
    assert result["facts_stored"] == 2
    assert "INSERT INTO company_intel.broker_research_facts" in sql
    assert params[0][1] == "BEL"
