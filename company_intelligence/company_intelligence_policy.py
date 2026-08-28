"""Policy event storage and deterministic company impact mapping."""

from __future__ import annotations

import sqlite3
from typing import Any


def store_policy_event(
    conn: sqlite3.Connection,
    event_type: str,
    event_date: str,
    title: str,
    source_url: str,
    summary: str,
    raw_path: str = "",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO macro_policy_events
            (event_type, event_date, title, source_url, summary, raw_path)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (event_type, event_date, title, source_url, summary, raw_path),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_policy_events(
    conn: sqlite3.Connection,
    event_type: str | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    if event_type:
        where = "WHERE event_type = ?"
        params.append(event_type)
    rows = conn.execute(
        f"""
        SELECT event_id, event_type, event_date, title, source_url, summary, raw_path
        FROM macro_policy_events
        {where}
        ORDER BY event_date DESC, event_id DESC
        """,
        params,
    ).fetchall()
    keys = ["event_id", "event_type", "event_date", "title", "source_url", "summary", "raw_path"]
    return [dict(zip(keys, row)) for row in rows]


def assess_policy_impact(
    company_profile: dict,
    event: dict,
    evidence: list[dict],
) -> dict:
    sector = str(company_profile.get("sector", "")).lower()
    summary = str(event.get("summary", "")).lower()
    event_type = str(event.get("event_type", "")).lower()
    demand_drivers = {str(item).lower() for item in company_profile.get("demand_drivers", [])}

    if (
        event_type == "rbi_policy"
        and ("rate cut" in summary or "repo rate cut" in summary)
        and str(company_profile.get("debt_level", "")).lower() == "high"
    ):
        return _impact("borrowing_cost", "positive", "medium", "Rate cuts can reduce interest burden for highly leveraged companies.", evidence)

    if (
        event_type == "union_budget"
        and ("tax relief" in summary or "consumption" in summary)
        and ("retail" in sector or "consumption" in demand_drivers)
    ):
        return _impact("consumer_demand", "positive", "medium", "Household tax relief can support discretionary and staples consumption.", evidence)

    if (
        event_type == "union_budget"
        and ("capex" in summary or "infrastructure" in summary)
        and ("infrastructure" in sector or "capital goods" in sector or "capex" in demand_drivers)
    ):
        return _impact("infrastructure_demand", "positive", "high", "Higher public capex can support order flow for infrastructure-linked companies.", evidence)

    if (
        ("inr weakness" in summary or "rupee weakness" in summary or "import cost" in summary)
        and str(company_profile.get("import_exposure", "")).lower() == "high"
    ):
        return _impact("import_cost", "negative", "medium", "INR weakness can increase landed input costs for import-heavy companies.", evidence)

    return _impact("general_policy_sensitivity", "neutral", "low", "No strong deterministic company-policy sensitivity was identified.", evidence)


def _impact(
    area: str,
    direction: str,
    magnitude: str,
    rationale: str,
    evidence: list[dict],
) -> dict:
    confidence = 0.65 if evidence else 0.5
    return {
        "impact_area": area,
        "direction": direction,
        "magnitude": magnitude,
        "rationale": rationale,
        "confidence": confidence,
    }
