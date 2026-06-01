"""Evidence Pack builder for Research Council runs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from terminal.research_council.schemas import EvidencePack, MissingEvidence, SourceTrailEntry, StewardVerdict
from terminal.research_council.states.data_steward import collect_pg_snapshot, compute_verdict
from terminal.research_council.mode_profiles import load_mode_profile


REQUIRED_SECTIONS = ("market", "sectors", "stocks", "derivatives", "fundamentals", "events", "reports")


def build_research_evidence_pack(
    *,
    mode: str = "market_council",
    as_of: date | None = None,
    universe_filter: str = "liquid",
    symbols: list[str] | None = None,
    steward_verdict: StewardVerdict | None = None,
    snapshot_loader: Callable[[], dict[str, Any]] | None = None,
    section_loader: Callable[[], dict[str, Any]] | None = None,
    max_stock_candidates: int = 50,
) -> EvidencePack:
    as_of = as_of or date.today()
    symbols = [s.upper() for s in (symbols or [])]
    snapshot = snapshot_loader() if snapshot_loader else collect_pg_snapshot()
    verdict = steward_verdict or compute_verdict(
        snapshot=snapshot,
        profile=load_mode_profile(mode),
        as_of=as_of,
        now=datetime.now(),
    )
    sections = section_loader() if section_loader else _build_sections_from_snapshot(snapshot)
    sections = _ensure_sections(sections)
    sections = _limit_stock_candidates(sections, max_stock_candidates)

    missing = _missing_from_verdict(verdict)
    source_trail = _source_trail_from_snapshot(snapshot)
    pack_id = f"evidence_{as_of.strftime('%Y%m%d')}_{mode}"

    return EvidencePack(
        pack_id=pack_id,
        as_of=as_of,
        mode=mode,
        universe_filter=universe_filter,
        symbols=symbols,
        sections=sections,
        source_trail=source_trail,
        missing_evidence=missing,
    )


def build_sector_opportunity_evidence_pack(
    *,
    sector: str,
    as_of: date | None = None,
    universe_filter: str = "liquid",
    steward_verdict: StewardVerdict | None = None,
    snapshot_loader: Callable[[], dict[str, Any]] | None = None,
    sector_context_loader: Callable[[str], dict[str, Any]] | None = None,
    max_stock_candidates: int = 10,
) -> EvidencePack:
    as_of = as_of or date.today()
    snapshot = snapshot_loader() if snapshot_loader else collect_pg_snapshot()
    verdict = steward_verdict or compute_verdict(
        snapshot=snapshot,
        profile=load_mode_profile("sector_opportunity"),
        as_of=as_of,
        now=datetime.now(),
    )
    context = sector_context_loader(sector) if sector_context_loader else _load_sector_context(sector)
    sections = _build_sector_opportunity_sections(snapshot, requested_sector=sector, context=context)
    sections = _ensure_sections(sections)
    sections = _limit_stock_candidates(sections, max_stock_candidates)

    missing = _missing_from_verdict(verdict)
    if context.get("error"):
        missing.append(
            MissingEvidence(
                scope="sector_opportunity",
                subject=sector,
                field="sector_context",
                severity="block",
                reason=str(context.get("error")),
            )
        )

    source_trail = _source_trail_from_snapshot(snapshot)
    source_trail.append(
        SourceTrailEntry(
            source="sector.top_stocks",
            rows=_safe_int(context.get("total_stocks")),
            latest_date=str(context.get("snapshot_date") or as_of.isoformat())[:10],
            metadata={
                "requested_sector": sector,
                "resolved_sector": context.get("sector"),
                "lookup_sector": context.get("_lookup_sector") or sector,
                "data_source": context.get("data_source"),
            },
        )
    )
    pack_id = f"evidence_{as_of.strftime('%Y%m%d')}_sector_opportunity_{_pack_slug(sector)}"

    return EvidencePack(
        pack_id=pack_id,
        as_of=as_of,
        mode="sector_opportunity",
        universe_filter=universe_filter,
        symbols=[row["symbol"] for row in sections.get("stocks", {}).get("candidates", []) if row.get("symbol")],
        sections=sections,
        source_trail=source_trail,
        missing_evidence=missing,
    )


def _build_sections_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "market": {
            "as_of": _date_text(snapshot.get("eod_latest")),
            "stage_snapshot": _date_text(snapshot.get("stage_latest")),
            "universe": {
                "total_symbols": int(snapshot.get("total_symbols") or 0),
                "liquid_symbols": int(snapshot.get("liquid_symbols") or 0),
                "analyzed_symbols": int(snapshot.get("analyzed_symbols") or 0),
                "filters": list(snapshot.get("filters") or []),
            },
        },
        "sectors": {"source": "pending_pg_adapter", "leaders": []},
        "stocks": {"count": 0, "candidates": []},
        "derivatives": {"latest_date": _date_text(snapshot.get("fno_latest"))},
        "fundamentals": {"latest_date": _date_text(snapshot.get("financials_latest"))},
        "events": {"source": "pending_pg_adapter", "upcoming_count": None},
        "reports": {"source": "pending_report_registry"},
    }


def _build_sector_opportunity_sections(
    snapshot: dict[str, Any],
    *,
    requested_sector: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    resolved_sector = str(context.get("sector") or requested_sector)
    candidates = [_normalize_sector_candidate(row, idx + 1) for idx, row in enumerate(context.get("top5_by_score") or [])]
    sector_item = {
        "sector": resolved_sector,
        "requested_sector": requested_sector,
        "snapshot_date": context.get("snapshot_date"),
        "rs_1m": _safe_float(context.get("avg_1m_pct")),
        "rs_3m": _safe_float(context.get("avg_rs_pct")),
        "breadth_pct_above_50dma": None,
        "stage2_count": _safe_int(context.get("stage2_count")),
        "buy_signals": _safe_int(context.get("buy_signals")),
        "total_stocks": _safe_int(context.get("total_stocks")),
        "top_stocks": [row["symbol"] for row in candidates if row.get("symbol")],
    }
    sections = _build_sections_from_snapshot(snapshot)
    sections["sector_opportunity"] = {
        "requested_sector": requested_sector,
        "resolved_sector": resolved_sector,
        "snapshot_date": context.get("snapshot_date"),
        "total_stocks": _safe_int(context.get("total_stocks")),
        "stage2_count": _safe_int(context.get("stage2_count")),
        "buy_signals": _safe_int(context.get("buy_signals")),
        "avg_rs_pct": _safe_float(context.get("avg_rs_pct")),
        "avg_1m_pct": _safe_float(context.get("avg_1m_pct")),
        "weakest": list(context.get("weakest_3") or []),
    }
    sections["sectors"] = {
        "source": "sector.top_stocks",
        "items": [sector_item],
        "leaders": [resolved_sector] if candidates else [],
    }
    sections["stocks"] = {
        "count": len(candidates),
        "candidates": candidates,
        "shortlist_policy": "rank_by_sector_investment_score",
    }
    return sections


def _normalize_sector_candidate(row: dict[str, Any], rank: int) -> dict[str, Any]:
    signal = str(row.get("trading_signal") or "").upper()
    return {
        "rank": rank,
        "symbol": str(row.get("symbol") or "").upper(),
        "company_name": row.get("company_name"),
        "stage": row.get("stage"),
        "score": _safe_float(row.get("investment_score")),
        "investment_score": _safe_float(row.get("investment_score")),
        "rs": _safe_float(row.get("relative_strength")),
        "relative_strength": _safe_float(row.get("relative_strength")),
        "change_1d_pct": _safe_float(row.get("change_1d_pct")),
        "change_1w_pct": _safe_float(row.get("change_1w_pct")),
        "change_1m_pct": _safe_float(row.get("change_1m_pct")),
        "rsi": _safe_float(row.get("rsi")),
        "trading_signal": row.get("trading_signal"),
        "source": "sector.top_stocks",
        "shortlist_reason": _shortlist_reason(row, signal),
    }


def _ensure_sections(sections: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(sections)
    for section in REQUIRED_SECTIONS:
        normalized.setdefault(section, {})
    return normalized


def _limit_stock_candidates(sections: dict[str, Any], max_stock_candidates: int) -> dict[str, Any]:
    normalized = dict(sections)
    stocks = dict(normalized.get("stocks") or {})
    candidates = list(stocks.get("candidates") or [])
    if len(candidates) > max_stock_candidates:
        stocks["candidates"] = candidates[:max_stock_candidates]
        stocks["truncated"] = True
        stocks["full_count"] = len(candidates)
    else:
        stocks.setdefault("truncated", False)
    normalized["stocks"] = stocks
    return normalized


def _missing_from_verdict(verdict: StewardVerdict) -> list[MissingEvidence]:
    missing: list[MissingEvidence] = []
    for gap in verdict.blocking_gaps:
        missing.append(MissingEvidence(scope="data_steward", subject="run", field=gap, severity="block"))
    for gap in verdict.non_blocking_gaps:
        missing.append(MissingEvidence(scope="data_steward", subject="run", field=gap, severity="warn"))
    return missing


def _source_trail_from_snapshot(snapshot: dict[str, Any]) -> list[SourceTrailEntry]:
    return [
        SourceTrailEntry(
            source="market.equity_eod",
            rows=int(snapshot.get("total_symbols") or 0),
            latest_date=_date_text(snapshot.get("eod_latest")),
        ),
        SourceTrailEntry(
            source="scores.stage_snapshots",
            rows=int(snapshot.get("analyzed_symbols") or 0),
            latest_date=_date_text(snapshot.get("stage_latest")),
        ),
        SourceTrailEntry(
            source="derivatives.fno_eod",
            rows=None,
            latest_date=_date_text(snapshot.get("fno_latest")),
        ),
        SourceTrailEntry(
            source="scores.financials_refresh_log",
            rows=None,
            latest_date=_date_text(snapshot.get("financials_latest")),
        ),
    ]


def _date_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _load_sector_context(sector: str) -> dict[str, Any]:
    from terminal.research_council.tool_adapters import sector_top_stocks

    last_result: dict[str, Any] | None = None
    for lookup_sector in _sector_lookup_candidates(sector):
        result = sector_top_stocks(sector=lookup_sector)
        if not isinstance(result, dict):
            last_result = {"error": "sector_context_unavailable", "raw": result, "_lookup_sector": lookup_sector}
            continue
        result = dict(result)
        result["_lookup_sector"] = lookup_sector
        last_result = result
        if not result.get("error") and result.get("top5_by_score"):
            return result
    return last_result or {"error": "sector_context_unavailable", "_lookup_sector": sector}


def _sector_lookup_candidates(sector: str) -> list[str]:
    candidates = [sector]
    normalized = sector.strip()
    upper = normalized.upper()
    if upper.startswith("NIFTY "):
        candidates.append(normalized[6:].strip())
    seen = set()
    ordered = []
    for candidate in candidates:
        key = candidate.upper()
        if candidate and key not in seen:
            seen.add(key)
            ordered.append(candidate)
    return ordered


def _shortlist_reason(row: dict[str, Any], signal: str) -> str:
    reasons = []
    if row.get("stage"):
        reasons.append(str(row["stage"]))
    if row.get("investment_score") is not None:
        reasons.append(f"score={row['investment_score']}")
    if row.get("relative_strength") is not None:
        reasons.append(f"rs={row['relative_strength']}")
    if signal:
        reasons.append(f"signal={signal}")
    return ", ".join(reasons) if reasons else "ranked by sector context"


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _pack_slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_") or "sector"
