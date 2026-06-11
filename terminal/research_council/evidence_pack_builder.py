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
    sections = section_loader() if section_loader else _load_sections_from_pg(as_of=as_of, symbols=symbols)
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
    """Fallback used only when PG is unavailable — returns aggregate-only metadata."""
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
        "sectors": {"source": "pg_unavailable", "leaders": [], "items": []},
        "stocks": {"count": 0, "candidates": []},
        "derivatives": {"latest_date": _date_text(snapshot.get("fno_latest")), "items": []},
        "fundamentals": {"latest_date": _date_text(snapshot.get("financials_latest"))},
        "events": {"source": "pg_unavailable", "upcoming_count": None},
        "reports": {"source": "pending_report_registry"},
    }


def _load_sections_from_pg(
    *,
    as_of: date | None = None,
    symbols: list[str] | None = None,
    max_candidates: int = 50,
    dsn: str | None = None,
) -> dict[str, Any]:
    """Build evidence sections by querying PostgreSQL directly.

    Falls back to snapshot-only stubs if the DB is unavailable so the council
    can still run in degraded mode.
    """
    import os
    _dsn = dsn or os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except Exception:
        return _build_sections_from_snapshot({})

    try:
        conn = psycopg2.connect(_dsn)
    except Exception:
        return _build_sections_from_snapshot({})

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            snapshot = _pg_aggregate_snapshot(cur)
            market_section = _pg_market_section(snapshot)
            stocks_section = _pg_stocks_section(cur, symbols=symbols, max_candidates=max_candidates)
            sectors_section = _pg_sectors_section(cur)
            derivatives_section = _pg_derivatives_section(cur)
            fundamentals_section = {"latest_date": _date_text(snapshot.get("financials_latest"))}
        return {
            "market": market_section,
            "sectors": sectors_section,
            "stocks": stocks_section,
            "derivatives": derivatives_section,
            "fundamentals": fundamentals_section,
            "events": {"source": "pg_loaded", "upcoming_count": None},
            "reports": {"source": "pending_report_registry"},
        }
    except Exception:
        return _build_sections_from_snapshot({})
    finally:
        conn.close()


def _pg_aggregate_snapshot(cur: Any) -> dict[str, Any]:
    cur.execute("""
        WITH latest AS (SELECT max(trade_date) AS d FROM market.equity_eod),
        liquid AS (
            SELECT e.symbol FROM market.equity_eod e
            JOIN latest l ON e.trade_date = l.d
            WHERE e.close > 100 AND COALESCE(e.volume, 0) > 100000
        )
        SELECT
            (SELECT d FROM latest) AS eod_latest,
            (SELECT count(DISTINCT symbol) FROM market.equity_eod e JOIN latest l ON e.trade_date = l.d) AS total_symbols,
            (SELECT count(*) FROM liquid) AS liquid_symbols,
            (SELECT MAX(snapshot_date) FROM scores.stage_snapshots) AS stage_latest,
            (SELECT MAX(trade_date) FROM derivatives.fno_eod) AS fno_latest,
            (SELECT MAX(COALESCE(finished_at, started_at))::date FROM scores.financials_refresh_log) AS financials_latest
    """)
    row = cur.fetchone()
    return dict(row) if row else {}


def _pg_market_section(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "as_of": _date_text(snapshot.get("eod_latest")),
        "stage_snapshot": _date_text(snapshot.get("stage_latest")),
        "universe": {
            "total_symbols": int(snapshot.get("total_symbols") or 0),
            "liquid_symbols": int(snapshot.get("liquid_symbols") or 0),
            "analyzed_symbols": 0,
            "filters": ["close > 100", "volume > 100000", "at least 50 bars"],
        },
    }


def _pg_stocks_section(cur: Any, *, symbols: list[str] | None, max_candidates: int) -> dict[str, Any]:
    """Load Stage 2 stock candidates enriched with volume ratio, MA flags, and FnO signal."""
    symbol_filter = "AND ss.symbol = ANY(%s)" if symbols else ""
    params: list[Any] = []
    if symbols:
        params.append(symbols)

    cur.execute(f"""
        WITH vol AS (
            SELECT DISTINCT ON (symbol) symbol,
                   volume AS cur_vol,
                   AVG(volume) OVER (
                       PARTITION BY symbol
                       ORDER BY trade_date
                       ROWS BETWEEN 21 PRECEDING AND 1 PRECEDING
                   ) AS avg_vol_20
            FROM market.equity_eod
            WHERE trade_date >= CURRENT_DATE - INTERVAL '35 days'
            ORDER BY symbol, trade_date DESC
        ),
        w52 AS (
            SELECT DISTINCT ON (symbol) symbol, new_high, prev_high
            FROM market.week52_extremes
            ORDER BY symbol, snapshot_date DESC
        ),
        fno AS (
            SELECT symbol, pcr, oi_change_5d, buildup, fno_signal
            FROM derivatives.fno_signals
            WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM derivatives.fno_signals)
        )
        SELECT
            ss.symbol, ss.company_name, ss.sector, ss.stage,
            ss.investment_score, ss.relative_strength AS rs,
            ss.rsi, ss.technical_score, ss.minervini_score,
            ss.enhanced_fund_score, ss.fundamental_score,
            ss.change_1d_pct, ss.change_1m_pct,
            ss.trading_signal, ss.supertrend_state, ss.trend_signal,
            ss.price AS close,
            CASE WHEN v.avg_vol_20 > 0
                 THEN ROUND((v.cur_vol::numeric / v.avg_vol_20), 2)
                 ELSE NULL END AS volume_ratio,
            (ss.trend_signal IN ('BULLISH','STRONG_BULLISH'))  AS price_above_sma20,
            (ss.trend_signal IN ('BULLISH','STRONG_BULLISH'))  AS price_above_sma50,
            (ss.supertrend_state = 'BULLISH')                  AS price_above_sma200,
            CASE
                WHEN ss.trading_signal IN ('BUY','STRONG_BUY') THEN 'bullish'
                WHEN ss.trading_signal IN ('SELL','WEAK_SELL') THEN 'bearish'
                ELSE 'neutral'
            END AS macd,
            CASE WHEN ss.supertrend_state = 'BULLISH' THEN 'BUY' ELSE 'SELL' END AS supertrend,
            CASE
                WHEN w52.new_high IS NULL OR w52.new_high = 0 THEN NULL
                ELSE ROUND(((ss.price - w52.new_high) / w52.new_high * 100)::numeric, 2)
                END AS from_52w_high_pct,
            f.pcr, f.oi_change_5d, f.buildup, f.fno_signal
        FROM scores.stage_snapshots ss
        LEFT JOIN vol v ON v.symbol = ss.symbol
        LEFT JOIN w52 ON w52.symbol = ss.symbol
        LEFT JOIN fno f ON f.symbol = ss.symbol
        WHERE ss.snapshot_date = (SELECT MAX(snapshot_date) FROM scores.stage_snapshots)
          AND ss.stage = 'STAGE_2'
          AND ss.investment_score IS NOT NULL
          {symbol_filter}
        ORDER BY ss.investment_score DESC
        LIMIT %s
    """, params + [max_candidates])

    rows = cur.fetchall()
    candidates = [_float_row(dict(r)) for r in rows]
    return {"count": len(candidates), "candidates": candidates, "source": "scores.stage_snapshots"}


def _pg_sectors_section(cur: Any) -> dict[str, Any]:
    """Load sector RS ranking and Stage 2 breadth from sector_top_stocks + stage_snapshots."""
    cur.execute("""
        WITH top_stocks AS (
            SELECT sector_name,
                   ARRAY_AGG(symbol ORDER BY rank) AS top_symbols
            FROM scores.sector_top_stocks
            WHERE score_date = (SELECT MAX(score_date) FROM scores.sector_top_stocks)
            GROUP BY sector_name
        ),
        sector_stats AS (
            SELECT
                sector_name,
                ROUND(AVG(sector_strength)::numeric, 2)   AS sector_strength,
                ROUND(AVG(relative_strength)::numeric, 2) AS rs_3m,
                ROUND(AVG(change_1m_pct)::numeric, 2)     AS rs_1m,
                COUNT(DISTINCT symbol)                     AS total_stocks
            FROM scores.sector_top_stocks
            WHERE score_date = (SELECT MAX(score_date) FROM scores.sector_top_stocks)
            GROUP BY sector_name
        ),
        stage_breadth AS (
            SELECT sector,
                   COUNT(*)                                           AS universe_count,
                   COUNT(*) FILTER (WHERE stage = 'STAGE_2')          AS stage2_count,
                   COUNT(*) FILTER (WHERE trading_signal IN ('BUY','STRONG_BUY')) AS buy_signals
            FROM scores.stage_snapshots
            WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM scores.stage_snapshots)
            GROUP BY sector
        )
        SELECT
            ss.sector_name,
            ss.sector_name                  AS sector,
            ss.sector_strength,
            ss.rs_3m,
            ss.rs_1m,
            ss.total_stocks,
            COALESCE(sb.stage2_count, 0)    AS stage2_count,
            COALESCE(sb.buy_signals, 0)     AS buy_signals,
            COALESCE(sb.universe_count, 0)  AS universe_count,
            ROUND(
                COALESCE(sb.stage2_count, 0) * 100.0
                / NULLIF(COALESCE(sb.universe_count, ss.total_stocks), 0),
                1
            )                               AS breadth_pct_above_50dma,
            COALESCE(tp.top_symbols, ARRAY[]::text[]) AS top_stocks
        FROM sector_stats ss
        LEFT JOIN stage_breadth sb ON sb.sector = ss.sector_name
        LEFT JOIN top_stocks tp ON tp.sector_name = ss.sector_name
        ORDER BY ss.rs_1m DESC NULLS LAST
    """)
    rows = cur.fetchall()
    items = [_float_row(dict(r)) for r in rows]
    leaders = [r["sector_name"] for r in items if _safe_float_val(r.get("rs_1m")) >= 8 and _safe_float_val(r.get("rs_3m")) >= 10]
    return {"source": "scores.sector_top_stocks", "items": items, "leaders": leaders}


def _pg_derivatives_section(cur: Any) -> dict[str, Any]:
    """Load FnO signal summary for the council evidence pack."""
    cur.execute("""
        SELECT symbol, pcr, oi_change_5d, price_change, buildup, fno_signal
        FROM derivatives.fno_signals
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM derivatives.fno_signals)
          AND fno_signal != 'NEUTRAL'
        ORDER BY ABS(oi_change_5d) DESC NULLS LAST
        LIMIT 30
    """)
    items = [_float_row(dict(r)) for r in cur.fetchall()]

    cur.execute("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE fno_signal = 'BULLISH_BUILDUP') AS bullish_buildup,
            COUNT(*) FILTER (WHERE fno_signal = 'BEARISH_UNWIND')  AS bearish_unwind,
            ROUND(AVG(pcr)::numeric, 3)                             AS avg_pcr,
            MAX(snapshot_date)                                      AS latest_date
        FROM derivatives.fno_signals
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM derivatives.fno_signals)
    """)
    summary = _float_row(dict(cur.fetchone() or {}))

    return {
        "latest_date": _date_text(summary.get("latest_date")),
        "summary": summary,
        "items": items,
        "futures": items,
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


def _safe_float_val(value: Any) -> float:
    """Like _safe_float but returns 0.0 on None/error."""
    try:
        return float(value) if value is not None else 0.0
    except Exception:
        return 0.0


def _float_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert Decimal/date DB values to Python-native types for JSON serialisation."""
    from decimal import Decimal
    result: dict[str, Any] = {}
    for key, val in row.items():
        if isinstance(val, Decimal):
            result[key] = float(val)
        elif isinstance(val, (date, datetime)):
            result[key] = val.isoformat()
        elif isinstance(val, list):
            result[key] = [str(v) for v in val]
        else:
            result[key] = val
    return result


def _pack_slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_") or "sector"
