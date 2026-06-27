from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import date
from typing import Any, Callable

from terminal.governance.audit_parser import parse_audit_text
from terminal.governance.annual_report_review import generate_annual_report_review
from terminal.governance.cache_sources import load_cached_sources
from terminal.governance.live_sources import refresh_live_sources
from terminal.governance.markdown import render_markdown
from terminal.governance.models import GovernanceEvidence, GovernanceMissingEvidence, GovernanceRawSources, GovernanceReport
from terminal.governance.opinion import generate_governance_opinion
from terminal.governance.parsers import (
    parse_complaint_signal,
    parse_deal_rows,
    parse_governance_announcements,
    parse_nse_insider_disclosures,
    parse_nse_shareholding,
    parse_screener_capital_allocation,
)
from terminal.governance.scorer import score_governance


def _build_evidence(symbol: str, raw: GovernanceRawSources, as_of: date) -> GovernanceEvidence:
    target = symbol.upper()

    shareholding = []
    for payload in raw.shareholding_payloads:
        shareholding.extend(parse_nse_shareholding(payload))
    shareholding = sorted(shareholding, key=lambda item: item.quarter_end or date.min, reverse=True)

    insider_disclosures = []
    for payload in raw.insider_payloads:
        insider_disclosures.extend(parse_nse_insider_disclosures(payload, symbol=target))
    insider_disclosures = sorted(
        insider_disclosures,
        key=lambda item: item.trade_date or date.min,
        reverse=True,
    )

    complaints = parse_complaint_signal(raw.complaint_payloads[0]) if raw.complaint_payloads else None
    audit = parse_audit_text(raw.annual_report_text) if raw.annual_report_text else None
    capital_allocation = parse_screener_capital_allocation(raw.screener_payload)
    announcements = parse_governance_announcements(raw.announcement_rows, symbol=target)
    missing_evidence = _with_synthetic_missing(
        target,
        list(raw.missing_evidence),
        shareholding=shareholding,
        insider_disclosures=insider_disclosures,
        audit=audit,
        announcements=announcements,
        complaints=complaints,
        capital_allocation=capital_allocation,
    )

    return GovernanceEvidence(
        symbol=target,
        as_of=as_of,
        shareholding=shareholding,
        insider_disclosures=insider_disclosures,
        deals=parse_deal_rows(raw.deal_rows, symbol=target),
        announcements=announcements,
        audit=audit,
        complaints=complaints,
        capital_allocation=capital_allocation,
        source_trail=list(raw.source_trail),
        missing_evidence=missing_evidence,
    )


def evaluate_governance(
    symbol: str,
    *,
    use_llm: bool = False,
    use_annual_report_llm: bool = False,
    refresh_live: bool = False,
    raw_sources: GovernanceRawSources | None = None,
    live_source_loader: Callable[..., GovernanceRawSources] | None = None,
    llm_client: Callable[..., dict[str, Any]] | None = None,
    as_of: date | None = None,
    data_dir: str = "data",
) -> GovernanceReport:
    target = symbol.upper()
    if refresh_live:
        loader = live_source_loader or refresh_live_sources
        raw = loader(target, data_dir=data_dir)
    else:
        raw = raw_sources or load_cached_sources(target, data_dir=data_dir)
    evidence = _build_evidence(target, raw, as_of or date.today())
    report = score_governance(evidence)

    if use_annual_report_llm:
        review = generate_annual_report_review(report, raw.annual_report_text, llm_client=llm_client)
        status = str(review.get("status") or "invalid")
        if status == "ok":
            review_payload = dict(review)
            review_payload.pop("status", None)
            report = replace(
                report,
                annual_report_review_status="ok",
                annual_report_review=review_payload,
            )
        else:
            report = replace(
                report,
                annual_report_review_status=status,
                annual_report_review=None,
            )

    if not use_llm:
        return report

    opinion = generate_governance_opinion(report, llm_client=llm_client)
    status = str(opinion.get("status") or "invalid")
    if status != "ok":
        return replace(report, llm_status=status, llm_opinion=None)

    opinion_payload = dict(opinion)
    opinion_payload.pop("status", None)
    return replace(report, llm_status="ok", llm_opinion=opinion_payload)


def main(argv: list[str] | None = None, *, evaluator: Callable[..., GovernanceReport] = evaluate_governance) -> int:
    parser = argparse.ArgumentParser(description="Evaluate governance evidence for an NSE-listed company.")
    parser.add_argument("symbol")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument("--llm", action="store_true", help="Attach an LLM governance opinion")
    parser.add_argument("--llm-read", action="store_true", help="Attach an LLM annual-report governance review")
    parser.add_argument("--markdown", action="store_true", help="Print Markdown output")
    parser.add_argument("--refresh-live", action="store_true", help="Fetch live evidence and update governance cache")
    args = parser.parse_args(argv)

    report = evaluator(
        args.symbol,
        use_llm=args.llm,
        use_annual_report_llm=args.llm_read,
        refresh_live=args.refresh_live,
    )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


def _with_synthetic_missing(
    symbol: str,
    missing: list[GovernanceMissingEvidence],
    *,
    shareholding,
    insider_disclosures,
    audit,
    announcements,
    complaints,
    capital_allocation,
) -> list[GovernanceMissingEvidence]:
    output = list(missing)
    existing_fields = {item.field for item in output}
    checks = {
        "shareholding": bool(shareholding),
        "insider_disclosures": bool(insider_disclosures),
        "annual_report_text": audit is not None,
        "corporate_events": bool(announcements),
        "complaints": complaints is not None,
        "screener_payload": capital_allocation is not None,
    }
    for field, present in checks.items():
        if not present and field not in existing_fields:
            output.append(
                GovernanceMissingEvidence(
                    scope="governance",
                    subject=symbol,
                    field=field,
                    severity="warn",
                    reason="No evidence available in provided raw sources",
                )
            )
    return output


if __name__ == "__main__":
    raise SystemExit(main())
