import json
from datetime import date, datetime

from terminal.governance.models import (
    AuditSignal,
    ComponentScore,
    GovernanceEvidence,
    GovernanceMissingEvidence,
    GovernanceRawSources,
    GovernanceReport,
    GovernanceSource,
    ShareholdingSnapshot,
)


def test_governance_report_to_dict_is_json_safe():
    source = GovernanceSource(
        name="nse.corporates-shp",
        status="ok",
        rows=2,
        latest_date=date(2026, 6, 30),
        fallback=False,
    )
    evidence = GovernanceEvidence(
        symbol="INFY",
        as_of=date(2026, 6, 27),
        shareholding=[
            ShareholdingSnapshot(
                quarter="Jun 2026",
                quarter_end=date(2026, 6, 30),
                promoter_pct=14.7,
                pledge_pct=0.0,
                pledge_of_total_pct=0.0,
                fii_pct=32.0,
                dii_pct=36.0,
                public_pct=17.3,
                source="NSE",
            )
        ],
        audit=AuditSignal(
            auditor_name="Deloitte Haskins & Sells LLP",
            auditor_tier="Big4",
            opinion_type="Clean",
            emphasis_of_matter=False,
            key_audit_matters_count=3,
            auditor_tenure_years=5,
            related_party_txn_pct_revenue=2.5,
            source="annual_report",
        ),
        source_trail=[source],
    )
    report = GovernanceReport(
        symbol="INFY",
        as_of=date(2026, 6, 27),
        score=91.5,
        rating="STRONG",
        confidence="High",
        component_scores=[
            ComponentScore(
                name="promoter_pledge",
                score=20.0,
                max_score=20.0,
                status="green",
                notes=["No pledge"],
                source_names=["nse.corporates-shp"],
            )
        ],
        flags=[],
        evidence=evidence,
        source_trail=[source],
        missing_evidence=[],
        llm_status="not_requested",
    )

    data = report.to_dict()

    json.dumps(data, allow_nan=False)
    assert data["as_of"] == "2026-06-27"
    assert data["evidence"]["shareholding"][0]["quarter_end"] == "2026-06-30"
    assert data["source_trail"][0]["latest_date"] == "2026-06-30"
    assert data["component_scores"][0]["name"] == "promoter_pledge"


def test_raw_sources_can_capture_source_errors_and_missing_evidence():
    raw = GovernanceRawSources(
        symbol="AAA",
        shareholding_payloads=[
            {
                "nested_date": date(2026, 6, 30),
                "nested_datetime": datetime(2026, 6, 27, 9, 30),
                "tuple_value": ("a", 1),
            }
        ],
        source_trail=[
            GovernanceSource(
                name="nse.corporates-cgr",
                status="error",
                error="HTTP 404",
                metadata={"as_of": date(2026, 6, 27)},
            )
        ],
        missing_evidence=[
            GovernanceMissingEvidence(
                scope="governance",
                subject="AAA",
                field="corporate_governance_report",
                severity="warn",
                reason="NSE endpoint unavailable",
            )
        ],
    )

    data = raw.to_dict()

    json.dumps(data, allow_nan=False)
    assert data["symbol"] == "AAA"
    assert data["shareholding_payloads"][0]["nested_date"] == "2026-06-30"
    assert data["shareholding_payloads"][0]["nested_datetime"] == "2026-06-27T09:30:00"
    assert data["shareholding_payloads"][0]["tuple_value"] == ["a", 1]
    assert data["source_trail"][0]["metadata"]["as_of"] == "2026-06-27"
    assert data["source_trail"][0]["status"] == "error"
    assert data["missing_evidence"][0]["field"] == "corporate_governance_report"
