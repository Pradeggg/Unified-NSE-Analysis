"""Agent Adda PostgreSQL context for financial research reports."""

from __future__ import annotations

from typing import Any


def _rollback_quietly(conn: Any) -> None:
    try:
        conn.rollback()
    except Exception:
        pass


def _dict_row(cursor: Any, row: tuple[Any, ...] | None) -> dict[str, Any]:
    if not row:
        return {}
    columns = [item[0] for item in cursor.description or []]
    return {columns[idx]: row[idx] for idx in range(min(len(columns), len(row)))}


def _select_one(conn: Any, sql: str, params: tuple[Any, ...]) -> dict[str, Any]:
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return _dict_row(cur, cur.fetchone())
    except Exception:
        _rollback_quietly(conn)
        return {}


def _select_many(conn: Any, sql: str, params: tuple[Any, ...], limit: int = 10) -> list[dict[str, Any]]:
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            columns = [item[0] for item in cur.description or []]
            rows = cur.fetchall()
        out = []
        for row in rows[:limit]:
            out.append({columns[idx]: row[idx] for idx in range(min(len(columns), len(row)))})
        return out
    except Exception:
        _rollback_quietly(conn)
        return []


def fetch_agent_adda_pg_context(conn: Any, *, symbol: str) -> dict[str, Any]:
    clean_symbol = symbol.strip().upper()
    context: dict[str, Any] = {"symbol": clean_symbol}
    context["instrument"] = _select_one(
        conn,
        """
        SELECT symbol, company_name, sector, industry, market_cap_cat, is_nifty50, is_nifty500, is_fno
        FROM ref.instruments
        WHERE symbol = %s
        """,
        (clean_symbol,),
    )
    context["latest_eod"] = _select_one(
        conn,
        """
        SELECT trade_date, close, change_pct, volume, turnover_cr, week52_high, week52_low, market_cap_cr
        FROM market.equity_eod
        WHERE symbol = %s
        ORDER BY trade_date DESC
        LIMIT 1
        """,
        (clean_symbol,),
    )
    context["daily_score"] = _select_one(
        conn,
        """
        SELECT score_date, current_price, change_1d_pct, change_1w_pct, change_1m_pct,
               technical_score, rsi, relative_strength, trend_signal, trading_signal,
               fundamental_score, enhanced_fund_score
        FROM scores.daily_scores
        WHERE symbol = %s
        ORDER BY score_date DESC
        LIMIT 1
        """,
        (clean_symbol,),
    )
    context["fundamental_snapshot"] = _select_one(
        conn,
        """
        SELECT revenue_growth_3y, pat_growth_3y, roe, roce, debt_to_equity,
               promoter_holding, piotroski_score, beneish_m_score, altman_z_score,
               forensic_risk, updated_at
        FROM scores.fundamentals
        WHERE symbol = %s
        """,
        (clean_symbol,),
    )
    context["fundamental_score"] = _select_one(
        conn,
        """
        SELECT score_date, enhanced_fund_score, earnings_quality, sales_growth,
               financial_strength, institutional_backing
        FROM scores.fundamental_scores
        WHERE symbol = %s
        ORDER BY score_date DESC
        LIMIT 1
        """,
        (clean_symbol,),
    )
    context["screener_summary"] = _select_one(
        conn,
        """
        SELECT run_date, price, screens_passed_total, screens_technical,
               screens_fundamental, screens_growth, investment_score,
               technical_score, enhanced_fund_score, stage, trading_signal,
               conviction_tier, passed_screens
        FROM screener.stock_screen_summary
        WHERE symbol = %s
        ORDER BY run_date DESC
        LIMIT 1
        """,
        (clean_symbol,),
    )
    context["quarterly_results"] = _select_many(
        conn,
        """
        SELECT period_label, revenue, operating_profit, opm_pct, pat, eps
        FROM scores.quarterly_results
        WHERE symbol = %s
        ORDER BY period_end DESC
        LIMIT 6
        """,
        (clean_symbol,),
        limit=6,
    )
    context["annual_results"] = _select_many(
        conn,
        """
        SELECT period_label, revenue, operating_profit, opm_pct, pat, eps, dividend_payout_pct
        FROM scores.annual_results
        WHERE symbol = %s
        ORDER BY period_end DESC
        LIMIT 6
        """,
        (clean_symbol,),
        limit=6,
    )
    context["sector_context"] = _select_one(
        conn,
        """
        WITH latest AS (SELECT max(score_date) AS d FROM scores.daily_scores),
             bel_sector AS (SELECT sector FROM ref.instruments WHERE symbol = %s)
        SELECT d.score_date, i.sector, count(*) AS stocks,
               round(avg(d.relative_strength), 2) AS avg_relative_strength,
               round(avg(d.change_1m_pct), 2) AS avg_1m_change_pct,
               count(*) FILTER (WHERE d.trading_signal = 'BUY') AS buy_signals,
               count(*) FILTER (WHERE d.trend_signal = 'STAGE_2') AS stage2_count
        FROM scores.daily_scores d
        JOIN ref.instruments i USING(symbol), latest, bel_sector
        WHERE d.score_date = latest.d
          AND i.sector = bel_sector.sector
        GROUP BY d.score_date, i.sector
        """,
        (clean_symbol,),
    )
    context["sector_peers"] = _select_many(
        conn,
        """
        WITH latest AS (SELECT max(score_date) AS d FROM scores.daily_scores),
             bel_sector AS (SELECT sector FROM ref.instruments WHERE symbol = %s)
        SELECT d.symbol, d.current_price, d.change_1m_pct, d.relative_strength,
               d.technical_score, d.rsi, d.trading_signal
        FROM scores.daily_scores d
        JOIN ref.instruments i USING(symbol), latest, bel_sector
        WHERE d.score_date = latest.d
          AND i.sector = bel_sector.sector
        ORDER BY d.relative_strength DESC NULLS LAST
        LIMIT 10
        """,
        (clean_symbol,),
        limit=10,
    )
    context["available"] = any(
        bool(context.get(key))
        for key in (
            "instrument",
            "latest_eod",
            "daily_score",
            "fundamental_score",
            "quarterly_results",
            "annual_results",
            "sector_context",
            "screener_summary",
        )
    )
    return context
