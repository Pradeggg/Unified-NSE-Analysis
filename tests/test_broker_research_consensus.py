from broker_research.consensus import build_broker_consensus, recurring_fact_values
from broker_research.storage import record_broker_research_run


def test_build_broker_consensus_calculates_rating_and_target_spread():
    facts = [
        {
            "broker_code": "icici",
            "broker_report_id": 1,
            "fact_type": "rating",
            "fact_value": "BUY",
            "page_number": 1,
        },
        {
            "broker_code": "icici",
            "broker_report_id": 1,
            "fact_type": "target_price",
            "fact_value": "520",
            "page_number": 1,
        },
        {
            "broker_code": "hdfc_hsie",
            "broker_report_id": 2,
            "fact_type": "rating",
            "fact_value": "ADD",
            "page_number": 1,
        },
        {
            "broker_code": "hdfc_hsie",
            "broker_report_id": 2,
            "fact_type": "target_price",
            "fact_value": "475",
            "page_number": 1,
        },
    ]

    consensus = build_broker_consensus(symbol="BEL", facts=facts)

    assert consensus["symbol"] == "BEL"
    assert consensus["broker_count"] == 2
    assert consensus["ratings"] == {"ADD": 1, "BUY": 1}
    assert consensus["target_price"]["min"] == 475.0
    assert consensus["target_price"]["max"] == 520.0
    assert consensus["target_price"]["spread"] == 45.0
    assert "rating_disagreement" in consensus["disagreements"]


def test_build_broker_consensus_counts_one_rating_per_report():
    facts = [
        {"broker_code": "icici", "broker_report_id": 1, "fact_type": "rating", "fact_value": "BUY", "page_number": 2},
        {"broker_code": "icici", "broker_report_id": 1, "fact_type": "rating", "fact_value": "BUY", "page_number": 3},
        {"broker_code": "icici", "broker_report_id": 1, "fact_type": "target_price", "fact_value": "530", "page_number": 2},
        {"broker_code": "icici", "broker_report_id": 1, "fact_type": "target_price", "fact_value": "530", "page_number": 4},
    ]

    consensus = build_broker_consensus(symbol="BEL", facts=facts)

    assert consensus["ratings"] == {"BUY": 1}
    assert consensus["target_price"]["count"] == 1


def test_recurring_fact_values_counts_normalized_risks_and_catalysts():
    facts = [
        {"fact_type": "risk", "fact_value": "Risks include execution delay."},
        {"fact_type": "risk", "fact_value": "risks include execution delay"},
        {"fact_type": "catalyst", "fact_value": "Catalysts include defence order wins."},
    ]

    assert recurring_fact_values(facts, fact_type="risk") == [{"value": "risks include execution delay", "count": 2}]


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = [(91,)]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))

    def fetchone(self):
        return self.rows[0]


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.commits = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1


def test_record_broker_research_run_stores_consensus_artifact():
    conn = FakeConnection()

    run_id = record_broker_research_run(
        conn,
        symbol="BEL",
        objective="broker_consensus",
        broker_filter="public",
        status="ok",
        coverage={"broker_count": 2},
    )

    sql, params = conn.executed[0]
    assert "INSERT INTO company_intel.broker_research_runs" in sql
    assert params[0] == "BEL"
    assert params[3] == "ok"
    assert '"broker_count": 2' in params[7]
    assert run_id == 91
    assert conn.commits == 1
