#!/usr/bin/env python3
"""Build a comprehensive end-of-day market report from local PostgreSQL data."""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")


PG_DSN = os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"
REPORT_ROOT = ROOT / "reports" / "eod_market"
LATEST_DIR = ROOT / "reports" / "latest"
IST_LABEL = "Asia/Kolkata"


@dataclass
class ReportPaths:
    html: Path
    md: Path
    latest_html: Path
    latest_md: Path


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _f(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        out = float(str(value).replace(",", ""))
    except Exception:
        return None
    return out if math.isfinite(out) else None


def _fmt(value: Any, digits: int = 2, suffix: str = "") -> str:
    val = _f(value)
    if val is None:
        return "-"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.{digits}f}{suffix}"


def _num(value: Any, digits: int = 2) -> str:
    val = _f(value)
    if val is None:
        return "-"
    return f"{val:,.{digits}f}"


def _int(value: Any) -> str:
    val = _f(value)
    if val is None:
        return "-"
    return f"{val:,.0f}"


def _class_pct(value: Any) -> str:
    val = _f(value) or 0.0
    if val > 0.05:
        return "pos"
    if val < -0.05:
        return "neg"
    return "flat"


def _h(text: Any) -> str:
    return html.escape("" if text is None else str(text))


def _inline_markdown_html(text: str) -> str:
    """Render the small markdown subset used in generated commentary."""
    escaped = _h(text)
    escaped = re.sub(r"\*\*([^*\n][^*]*?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*\n][^*]*?)\*(?!\*)", r"<em>\1</em>", escaped)
    return escaped


def _commentary_markdown_html(text: Any) -> str:
    """Safely render generated market commentary instead of showing raw markdown markers."""
    raw = str(text or "").strip()
    if not raw:
        return '<p class="muted">No commentary available for this session.</p>'
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", raw) if part.strip()]
    if not paragraphs:
        return '<p class="muted">No commentary available for this session.</p>'

    rendered: list[str] = []
    for para in paragraphs:
        lines = [line.strip() for line in para.splitlines() if line.strip()]
        if not lines:
            continue
        if all(line.startswith(("- ", "* ")) for line in lines):
            items = "".join(f"<li>{_inline_markdown_html(line[2:].strip())}</li>" for line in lines)
            rendered.append(f"<ul>{items}</ul>")
            continue
        body = "<br>".join(_inline_markdown_html(line) for line in lines)
        rendered.append(f"<p>{body}</p>")
    return "".join(rendered) or '<p class="muted">No commentary available for this session.</p>'


def _query(conn, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def load_eod_fallback_data(conn, report_date: date) -> dict[str, Any]:
    index_daily = _query(
        conn,
        """
        SELECT CASE
                   WHEN index_symbol = 'Nifty 50' THEN 'NIFTY'
                   WHEN index_symbol = 'Nifty Bank' THEN 'BANKNIFTY'
                   ELSE index_symbol
               END AS symbol,
               open AS day_open,
               close AS day_close,
               high AS day_high,
               low AS day_low,
               change_pct AS day_pct,
               volume
        FROM market.index_eod
        WHERE trade_date = %s
          AND index_symbol IN ('Nifty 50', 'Nifty Bank')
        ORDER BY symbol
        """,
        (report_date,),
    )
    symbol_day = _query(
        conn,
        """
        WITH latest_stage AS (
            SELECT DISTINCT ON (symbol) symbol, company_name, sector, market_cap_cat, stage,
                   trading_signal, technical_score, relative_strength
            FROM scores.stage_snapshots
            WHERE snapshot_date <= %s
            ORDER BY symbol, snapshot_date DESC
        ),
        ranked_eod AS (
            SELECT e.*,
                   row_number() OVER (
                       PARTITION BY e.symbol
                       ORDER BY (e.series = 'EQ') DESC, coalesce(e.volume, 0) DESC
                   ) AS rn
            FROM market.equity_eod e
            WHERE e.trade_date = %s
        )
        SELECT e.symbol, s.company_name, coalesce(nullif(s.sector,''), 'Unclassified') AS sector,
               s.market_cap_cat, s.stage, s.trading_signal, s.technical_score, s.relative_strength,
               e.open AS day_open, e.close AS day_close, e.high AS day_high, e.low AS day_low,
               e.change_pct AS day_pct, e.volume
        FROM ranked_eod e
        LEFT JOIN latest_stage s ON s.symbol = e.symbol
        WHERE e.rn = 1
        ORDER BY e.change_pct DESC NULLS LAST
        """,
        (report_date, report_date),
    )
    return {
        "index_daily": _jsonable(index_daily),
        "symbol_day": _jsonable(symbol_day),
    }


def latest_intraday_date(conn, requested: str | None = None) -> date:
    if requested:
        return datetime.strptime(requested, "%Y-%m-%d").date()
    rows = _query(
        conn,
        """
        SELECT max((timestamp AT TIME ZONE %s)::date) AS dt
        FROM intraday.ohlcv_bars
        WHERE timeframe = '15m'
        """,
        (IST_LABEL,),
    )
    intraday_dt = rows[0].get("dt") if rows else None

    # Always check equity EOD — use whichever is more recent so the report
    # doesn't get pinned to a stale intraday date when EOD is fresher.
    eod_rows = _query(conn, "SELECT max(trade_date) AS dt FROM market.equity_eod", ())
    eod_dt = eod_rows[0].get("dt") if eod_rows else None

    dt = max(filter(None, [intraday_dt, eod_dt]), default=None)
    if not dt:
        raise RuntimeError("No intraday bars or equity EOD data found in PostgreSQL.")
    return dt


def load_report_data(conn, report_date: date) -> dict[str, Any]:
    params = (IST_LABEL, report_date)
    index_daily = _query(
        conn,
        """
        WITH bars AS (
            SELECT symbol, timestamp AT TIME ZONE %s AS ts, open, high, low, close, volume
            FROM intraday.ohlcv_bars
            WHERE timeframe = '15m'
              AND symbol IN ('NIFTY', 'BANKNIFTY')
              AND (timestamp AT TIME ZONE %s)::date = %s
        ),
        marked AS (
            SELECT *,
                   first_value(open) OVER (PARTITION BY symbol ORDER BY ts) AS day_open,
                   first_value(close) OVER (PARTITION BY symbol ORDER BY ts DESC) AS day_close,
                   first_value(ts) OVER (PARTITION BY symbol ORDER BY high DESC, ts) AS high_time,
                   first_value(ts) OVER (PARTITION BY symbol ORDER BY low ASC, ts) AS low_time
            FROM bars
        )
        SELECT symbol, min(ts) AS first_bar, max(ts) AS last_bar,
               max(day_open) AS day_open, max(day_close) AS day_close,
               max(high) AS day_high, min(low) AS day_low,
               max(high_time) AS high_time, max(low_time) AS low_time,
               round(((max(day_close)-max(day_open))/nullif(max(day_open),0)*100)::numeric, 2) AS day_pct,
               sum(coalesce(volume,0)) AS volume
        FROM marked
        GROUP BY symbol
        ORDER BY symbol
        """,
        (IST_LABEL, IST_LABEL, report_date),
    )
    hourly = _query(
        conn,
        """
        WITH bars AS (
            SELECT symbol, timestamp AT TIME ZONE %s AS ts, open, high, low, close, volume
            FROM intraday.ohlcv_bars
            WHERE timeframe = '15m'
              AND (timestamp AT TIME ZONE %s)::date = %s
        ),
        marked AS (
            SELECT *,
                   date_trunc('hour', ts) AS hour_bucket,
                   first_value(open) OVER (PARTITION BY symbol, date_trunc('hour', ts) ORDER BY ts) AS hour_open,
                   first_value(close) OVER (PARTITION BY symbol, date_trunc('hour', ts) ORDER BY ts DESC) AS hour_close
            FROM bars
        ),
        per_symbol_hour AS (
            SELECT symbol, hour_bucket, min(ts) AS first_ts, max(ts) AS last_ts,
                   max(hour_open) AS hour_open, max(hour_close) AS hour_close,
                   max(high) AS hour_high, min(low) AS hour_low,
                   sum(coalesce(volume,0)) AS hour_volume
            FROM marked
            GROUP BY symbol, hour_bucket
        ),
        breadth AS (
            SELECT hour_bucket,
                   count(*) FILTER (WHERE symbol NOT IN ('NIFTY','BANKNIFTY','FINNIFTY','MIDCPNIFTY') AND hour_close > hour_open) AS adv,
                   count(*) FILTER (WHERE symbol NOT IN ('NIFTY','BANKNIFTY','FINNIFTY','MIDCPNIFTY') AND hour_close < hour_open) AS decl,
                   count(*) FILTER (WHERE symbol NOT IN ('NIFTY','BANKNIFTY','FINNIFTY','MIDCPNIFTY') AND hour_close = hour_open) AS unchanged,
                   count(*) FILTER (WHERE symbol NOT IN ('NIFTY','BANKNIFTY','FINNIFTY','MIDCPNIFTY')) AS universe,
                   round(avg(CASE WHEN symbol NOT IN ('NIFTY','BANKNIFTY','FINNIFTY','MIDCPNIFTY') AND hour_open > 0
                                  THEN ((hour_close-hour_open)/hour_open)*100 END)::numeric, 2) AS avg_stock_chg_pct,
                   sum(hour_volume) FILTER (WHERE symbol NOT IN ('NIFTY','BANKNIFTY','FINNIFTY','MIDCPNIFTY')) AS total_volume
            FROM per_symbol_hour
            GROUP BY hour_bucket
        ),
        nifty AS (
            SELECT hour_bucket, hour_open, hour_high, hour_low, hour_close,
                   round(((hour_close-hour_open)/nullif(hour_open,0)*100)::numeric, 2) AS chg_pct
            FROM per_symbol_hour WHERE symbol='NIFTY'
        ),
        bank AS (
            SELECT hour_bucket, hour_open, hour_high, hour_low, hour_close,
                   round(((hour_close-hour_open)/nullif(hour_open,0)*100)::numeric, 2) AS chg_pct
            FROM per_symbol_hour WHERE symbol='BANKNIFTY'
        )
        SELECT to_char(coalesce(n.hour_bucket,b.hour_bucket,br.hour_bucket), 'HH24:MI') AS hour_ist,
               coalesce(n.hour_bucket,b.hour_bucket,br.hour_bucket) AS hour_bucket,
               n.hour_open AS nifty_open, n.hour_high AS nifty_high, n.hour_low AS nifty_low,
               n.hour_close AS nifty_close, n.chg_pct AS nifty_pct,
               b.hour_open AS bank_open, b.hour_high AS bank_high, b.hour_low AS bank_low,
               b.hour_close AS bank_close, b.chg_pct AS bank_pct,
               br.adv, br.decl, br.unchanged, br.universe,
               round((br.adv::numeric/nullif(br.adv+br.decl,0))*100, 1) AS adv_pct,
               br.avg_stock_chg_pct, br.total_volume
        FROM nifty n
        FULL JOIN bank b USING(hour_bucket)
        FULL JOIN breadth br USING(hour_bucket)
        ORDER BY coalesce(n.hour_bucket,b.hour_bucket,br.hour_bucket)
        """,
        (IST_LABEL, IST_LABEL, report_date),
    )
    symbol_day = _query(
        conn,
        """
        WITH latest_stage AS (
            SELECT DISTINCT ON (symbol) symbol, company_name, sector, market_cap_cat, stage,
                   trading_signal, technical_score, relative_strength
            FROM scores.stage_snapshots
            WHERE snapshot_date <= %s
            ORDER BY symbol, snapshot_date DESC
        ),
        bars AS (
            SELECT b.symbol, b.timestamp AT TIME ZONE %s AS ts, b.open, b.high, b.low, b.close, b.volume
            FROM intraday.ohlcv_bars b
            WHERE b.timeframe = '15m'
              AND b.symbol NOT IN ('NIFTY','BANKNIFTY','FINNIFTY','MIDCPNIFTY')
              AND (b.timestamp AT TIME ZONE %s)::date = %s
        ),
        marked AS (
            SELECT *,
                   first_value(open) OVER (PARTITION BY symbol ORDER BY ts) AS day_open,
                   first_value(close) OVER (PARTITION BY symbol ORDER BY ts DESC) AS day_close
            FROM bars
        )
        SELECT m.symbol, s.company_name, coalesce(nullif(s.sector,''), 'Unclassified') AS sector,
               s.market_cap_cat, s.stage, s.trading_signal, s.technical_score, s.relative_strength,
               max(m.day_open) AS day_open, max(m.day_close) AS day_close,
               max(m.high) AS day_high, min(m.low) AS day_low,
               round(((max(m.day_close)-max(m.day_open))/nullif(max(m.day_open),0)*100)::numeric, 2) AS day_pct,
               sum(coalesce(m.volume,0)) AS volume
        FROM marked m
        LEFT JOIN latest_stage s ON s.symbol = m.symbol
        GROUP BY m.symbol, s.company_name, s.sector, s.market_cap_cat, s.stage,
                 s.trading_signal, s.technical_score, s.relative_strength
        ORDER BY day_pct DESC NULLS LAST
        """,
        (report_date, IST_LABEL, IST_LABEL, report_date),
    )
    hourly_leaders = _query(
        conn,
        """
        WITH bars AS (
            SELECT symbol, timestamp AT TIME ZONE %s AS ts, open, high, low, close, volume
            FROM intraday.ohlcv_bars
            WHERE timeframe='15m'
              AND symbol NOT IN ('NIFTY','BANKNIFTY','FINNIFTY','MIDCPNIFTY')
              AND (timestamp AT TIME ZONE %s)::date = %s
        ),
        marked AS (
            SELECT *,
                   date_trunc('hour', ts) AS hour_bucket,
                   first_value(open) OVER (PARTITION BY symbol, date_trunc('hour', ts) ORDER BY ts) AS hour_open,
                   first_value(close) OVER (PARTITION BY symbol, date_trunc('hour', ts) ORDER BY ts DESC) AS hour_close
            FROM bars
        ),
        per_symbol AS (
            SELECT symbol, hour_bucket, max(hour_open) AS hour_open, max(hour_close) AS hour_close,
                   sum(coalesce(volume,0)) AS hour_volume,
                   round(((max(hour_close)-max(hour_open))/nullif(max(hour_open),0)*100)::numeric, 2) AS chg_pct
            FROM marked
            GROUP BY symbol,hour_bucket
        ),
        ranked AS (
            SELECT *,
                   row_number() OVER (PARTITION BY hour_bucket ORDER BY chg_pct DESC NULLS LAST) AS gain_rank,
                   row_number() OVER (PARTITION BY hour_bucket ORDER BY chg_pct ASC NULLS LAST) AS lose_rank,
                   row_number() OVER (PARTITION BY hour_bucket ORDER BY hour_volume DESC NULLS LAST) AS vol_rank
            FROM per_symbol
        )
        SELECT to_char(hour_bucket,'HH24:MI') AS hour_ist,
               jsonb_agg(jsonb_build_object('symbol', symbol, 'chg_pct', chg_pct) ORDER BY gain_rank)
                   FILTER (WHERE gain_rank <= 3) AS top_gainers,
               jsonb_agg(jsonb_build_object('symbol', symbol, 'chg_pct', chg_pct) ORDER BY lose_rank)
                   FILTER (WHERE lose_rank <= 3) AS top_losers,
               jsonb_agg(jsonb_build_object('symbol', symbol, 'volume', hour_volume) ORDER BY vol_rank)
                   FILTER (WHERE vol_rank <= 3) AS volume_leaders
        FROM ranked
        WHERE gain_rank <= 3 OR lose_rank <= 3 OR vol_rank <= 3
        GROUP BY hour_bucket
        ORDER BY hour_bucket
        """,
        (IST_LABEL, IST_LABEL, report_date),
    )
    intraday_path = _query(
        conn,
        """
        SELECT symbol, to_char(timestamp AT TIME ZONE %s, 'HH24:MI') AS time_ist,
               open, high, low, close
        FROM intraday.ohlcv_bars
        WHERE timeframe='15m'
          AND symbol IN ('NIFTY','BANKNIFTY')
          AND (timestamp AT TIME ZONE %s)::date = %s
        ORDER BY symbol, timestamp
        """,
        (IST_LABEL, IST_LABEL, report_date),
    )
    # EOD daily candles for fallback candlestick chart (last 60 trading days)
    eod_candles = _query(
        conn,
        """
        SELECT index_symbol,
               to_char(trade_date, 'DD-Mon') AS trade_date,
               open, high, low, close
        FROM market.index_eod
        WHERE index_symbol IN ('Nifty 50', 'Nifty Bank')
          AND trade_date <= %s
        ORDER BY index_symbol, trade_date DESC
        LIMIT 120
        """,
        (report_date,),
    )
    # Reverse so oldest→newest per symbol for chart left-to-right order
    nifty_eod = list(reversed([r for r in eod_candles if r.get("index_symbol") == "Nifty 50"]))
    bank_eod  = list(reversed([r for r in eod_candles if r.get("index_symbol") == "Nifty Bank"]))
    eod_candles_sorted = nifty_eod + bank_eod

    # FII/DII flows
    fii_rows = _query(
        conn,
        "SELECT fii_net_today, dii_net_today, fii_net_5d, dii_net_5d FROM signals.fii_dii_flows WHERE trade_date = %s",
        (report_date,),
    )
    fii_dii = _jsonable(fii_rows[0]) if fii_rows else {}

    # Market regime
    regime_rows = _query(
        conn,
        "SELECT regime, confidence FROM signals.regime_history WHERE trade_date = %s",
        (report_date,),
    )
    regime = _jsonable(regime_rows[0]) if regime_rows else {}

    # McClellan from breadth.market_daily
    breadth_rows = _query(
        conn,
        "SELECT advances, declines, unchanged, ad_oscillator, trin, market_sentiment FROM breadth.market_daily WHERE trade_date = %s",
        (report_date,),
    )
    market_breadth = _jsonable(breadth_rows[0]) if breadth_rows else {}

    data = {
        "report_date": report_date.isoformat(),
        "index_daily": _jsonable(index_daily),
        "hourly": _jsonable(hourly),
        "symbol_day": _jsonable(symbol_day),
        "hourly_leaders": _jsonable(hourly_leaders),
        "intraday_path": _jsonable(intraday_path),
        "eod_candles": _jsonable(eod_candles_sorted),
        "fii_dii": fii_dii,
        "regime": regime,
        "market_breadth": market_breadth,
        "source_mode": "intraday_15m",
    }
    if not data["index_daily"] or not data["symbol_day"]:
        fallback = load_eod_fallback_data(conn, report_date)
        if not data["index_daily"] and fallback["index_daily"]:
            data["index_daily"] = fallback["index_daily"]
        if not data["symbol_day"] and fallback["symbol_day"]:
            data["symbol_day"] = fallback["symbol_day"]
        if fallback["index_daily"] or fallback["symbol_day"]:
            data["source_mode"] = "eod_only" if not data["hourly"] else "intraday_with_eod_fallback"
    return data


def enrich_data(data: dict[str, Any]) -> dict[str, Any]:
    symbols = data["symbol_day"]
    hourly = data["hourly"]
    sector_map: dict[str, list[dict[str, Any]]] = {}
    for row in symbols:
        sector_map.setdefault(row.get("sector") or "Unclassified", []).append(row)
    sectors = []
    for sector, rows in sector_map.items():
        chgs = [_f(r.get("day_pct")) for r in rows if _f(r.get("day_pct")) is not None]
        if not chgs:
            continue
        adv = sum(1 for r in rows if (_f(r.get("day_pct")) or 0) > 0)
        decl = sum(1 for r in rows if (_f(r.get("day_pct")) or 0) < 0)
        sectors.append({
            "sector": sector,
            "count": len(chgs),
            "avg_pct": round(sum(chgs) / len(chgs), 2),
            "adv": adv,
            "decl": decl,
            "adv_pct": round(adv / max(adv + decl, 1) * 100, 1),
        })
    sectors.sort(key=lambda r: r["avg_pct"], reverse=True)
    data["sectors"] = sectors
    data["top_gainers"] = sorted(symbols, key=lambda r: _f(r.get("day_pct")) or -999, reverse=True)[:12]
    data["top_losers"] = sorted(symbols, key=lambda r: _f(r.get("day_pct")) or 999)[:12]
    data["volume_leaders"] = sorted(symbols, key=lambda r: _f(r.get("volume")) or 0, reverse=True)[:12]
    data["events"] = build_events(data)
    data["deterministic_commentary"] = build_deterministic_commentary(data)
    data["llm_commentary"] = build_llm_commentary(data)
    return data


def build_events(data: dict[str, Any]) -> list[dict[str, str]]:
    hourly = data["hourly"]
    if not hourly:
        return []
    events = []
    first = hourly[0]
    last = hourly[-1]
    weak = min(hourly, key=lambda r: _f(r.get("adv_pct")) if _f(r.get("adv_pct")) is not None else 999)
    strong = max(hourly, key=lambda r: _f(r.get("adv_pct")) if _f(r.get("adv_pct")) is not None else -999)
    vol = max(hourly, key=lambda r: _f(r.get("total_volume")) or 0)
    nifty = next((r for r in data["index_daily"] if r.get("symbol") == "NIFTY"), {})
    bank = next((r for r in data["index_daily"] if r.get("symbol") == "BANKNIFTY"), {})
    events.append({
        "time": str(first.get("hour_ist")),
        "title": "Opening tone",
        "detail": f"NIFTY {_fmt(first.get('nifty_pct'), 2, '%')}, BANKNIFTY {_fmt(first.get('bank_pct'), 2, '%')}; breadth {first.get('adv')} advances vs {first.get('decl')} declines.",
    })
    events.append({
        "time": str(weak.get("hour_ist")),
        "title": "Breadth trough",
        "detail": f"Only {_fmt(weak.get('adv_pct'), 1, '%')} of moving stocks advanced; this was the broadest risk-off phase.",
    })
    events.append({
        "time": str(strong.get("hour_ist")),
        "title": "Breadth expansion",
        "detail": f"Advancers improved to {_fmt(strong.get('adv_pct'), 1, '%')}, confirming the strongest recovery window.",
    })
    events.append({
        "time": str(vol.get("hour_ist")),
        "title": "Highest participation",
        "detail": f"Stored universe volume peaked at {_int(vol.get('total_volume'))} shares; watch whether this marked distribution or accumulation.",
    })
    if nifty:
        events.append({
            "time": "day",
            "title": "NIFTY range",
            "detail": f"High {_num(nifty.get('day_high'))} near {str(nifty.get('high_time'))[11:16]}, low {_num(nifty.get('day_low'))} near {str(nifty.get('low_time'))[11:16]}.",
        })
    if bank:
        events.append({
            "time": "day",
            "title": "BANKNIFTY range",
            "detail": f"High {_num(bank.get('day_high'))}, low {_num(bank.get('day_low'))}; closed {_fmt(bank.get('day_pct'), 2, '%')} from open.",
        })
    events.append({
        "time": str(last.get("hour_ist")),
        "title": "Closing tone",
        "detail": f"NIFTY {_fmt(last.get('nifty_pct'), 2, '%')}, BANKNIFTY {_fmt(last.get('bank_pct'), 2, '%')}; late breadth {last.get('adv')} / {last.get('decl')}.",
    })
    return events


def build_deterministic_commentary(data: dict[str, Any]) -> str:
    hourly = data["hourly"]
    if not hourly:
        nifty = next((r for r in data["index_daily"] if r.get("symbol") == "NIFTY"), {})
        bank = next((r for r in data["index_daily"] if r.get("symbol") == "BANKNIFTY"), {})
        top_sector = data.get("sectors", [{}])[0] if data.get("sectors") else {}
        bottom_sector = data.get("sectors", [{}])[-1] if data.get("sectors") else {}
        top_gainer = data.get("top_gainers", [{}])[0] if data.get("top_gainers") else {}
        top_loser = data.get("top_losers", [{}])[0] if data.get("top_losers") else {}
        if not nifty and not bank and not data.get("symbol_day"):
            return "No hourly intraday data was available."
        return (
            f"EOD-only session report. NIFTY closed {_fmt(nifty.get('day_pct'), 2, '%')} at {_num(nifty.get('day_close'))}, "
            f"while BANKNIFTY closed {_fmt(bank.get('day_pct'), 2, '%')} at {_num(bank.get('day_close'))}. "
            "Hourly intraday breadth was not available, so breadth timing, opening tone, and closing-hour participation are not inferred. "
            f"Within the EOD equity universe, {top_sector.get('sector', 'the leading sector group')} led with an average move of {_fmt(top_sector.get('avg_pct'), 2, '%')}, "
            f"while {bottom_sector.get('sector', 'the weakest sector group')} lagged at {_fmt(bottom_sector.get('avg_pct'), 2, '%')}. "
            f"Top stock pressure points were {top_gainer.get('symbol', 'n/a')} on the upside at {_fmt(top_gainer.get('day_pct'), 2, '%')} "
            f"and {top_loser.get('symbol', 'n/a')} on the downside at {_fmt(top_loser.get('day_pct'), 2, '%')}. "
            "Use this report as an EOD close snapshot, not an intraday tape reconstruction."
        )
    weak = min(hourly, key=lambda r: _f(r.get("adv_pct")) if _f(r.get("adv_pct")) is not None else 999)
    strong = max(hourly, key=lambda r: _f(r.get("adv_pct")) if _f(r.get("adv_pct")) is not None else -999)
    nifty = next((r for r in data["index_daily"] if r.get("symbol") == "NIFTY"), {})
    bank = next((r for r in data["index_daily"] if r.get("symbol") == "BANKNIFTY"), {})
    top_sector = data.get("sectors", [{}])[0] if data.get("sectors") else {}
    bottom_sector = data.get("sectors", [{}])[-1] if data.get("sectors") else {}
    return (
        f"The day was a recovery-after-shakeout session. NIFTY closed {_fmt(nifty.get('day_pct'), 2, '%')} "
        f"from its first stored bar while BANKNIFTY closed {_fmt(bank.get('day_pct'), 2, '%')}, so the index-level finish was constructive but not uniformly led by banks. "
        f"The decisive intraday event was the breadth trough at {weak.get('hour_ist')}, where only {_fmt(weak.get('adv_pct'), 1, '%')} of moving stocks advanced. "
        f"That was followed by a breadth expansion at {strong.get('hour_ist')} with {_fmt(strong.get('adv_pct'), 1, '%')} advancers, which argues that the rebound was broader than a narrow heavyweight lift. "
        f"Within the covered universe, {top_sector.get('sector', 'the leading sector group')} was the strongest sector cluster, while {bottom_sector.get('sector', 'the weakest cluster')} lagged. "
        "For the next session, the key question is whether late-day breadth can persist; if it fades early, the recovery should be treated as a tactical bounce rather than a fresh trend impulse."
    )


def build_llm_commentary(data: dict[str, Any]) -> dict[str, str]:
    if os.environ.get("EOD_REPORT_LLM", "1") == "0" or not os.environ.get("OPENAI_API_KEY"):
        return {"source": "deterministic_fallback", "text": data.get("deterministic_commentary", "")}
    try:
        from openai import OpenAI

        model = os.environ.get("EOD_REPORT_LLM_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4o"
        client = OpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            timeout=float(os.environ.get("OPENAI_TIMEOUT_S", "45")),
            max_retries=int(os.environ.get("OPENAI_MAX_RETRIES", "0")),
        )
        facts = {
            "report_date": data["report_date"],
            "index_daily": data["index_daily"],
            "hourly": data["hourly"],
            "sectors_top": data.get("sectors", [])[:5],
            "sectors_bottom": data.get("sectors", [])[-5:],
            "top_gainers": data.get("top_gainers", [])[:8],
            "top_losers": data.get("top_losers", [])[:8],
            "events": data.get("events", []),
        }
        prompt = (
            "Write a grounded end-of-day market commentary for an NSE market report. "
            "Use only the supplied facts. Be specific, trader-readable, and evidence-first. "
            "Use this structure with compact section labels: Day Character, Hour-By-Hour Story, "
            "Breadth And Participation, Leadership And Pressure, Next Session Watch. "
            "Call out the 11:00 breadth trough and 13:00 breadth recovery if present. "
            "Mention when index action and breadth disagree. Do not give investment advice.\n\n"
            f"FACTS:\n{json.dumps(facts, default=str, indent=2)}"
        )
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a disciplined market commentator. Ground every claim in provided numbers."},
                {"role": "user", "content": prompt},
            ],
        }
        if model.lower().startswith(("gpt-5", "o1", "o3", "o4")):
            kwargs["max_completion_tokens"] = 1200
        else:
            kwargs["max_tokens"] = 1200
        response = client.chat.completions.create(**kwargs)
        text = (response.choices[0].message.content or "").strip()
        return {"source": f"llm:{getattr(response, 'model', model)}", "text": text or data.get("deterministic_commentary", "")}
    except Exception as exc:
        return {"source": f"deterministic_fallback: {exc}", "text": data.get("deterministic_commentary", "")}


def _polyline(points: list[tuple[float, float]], width: int, height: int, pad: int = 28) -> str:
    vals = [p[1] for p in points if p[1] is not None]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    if hi == lo:
        hi += 1
        lo -= 1
    n = max(len(points) - 1, 1)
    coords = []
    for i, (_, value) in enumerate(points):
        x = pad + i * ((width - pad * 2) / n)
        y = height - pad - ((value - lo) / (hi - lo)) * (height - pad * 2)
        coords.append(f"{x:.1f},{y:.1f}")
    return " ".join(coords)


def svg_index_path(data: dict[str, Any]) -> str:
    rows = data["intraday_path"]
    by_symbol: dict[str, list[dict[str, Any]]] = {"NIFTY": [], "BANKNIFTY": []}
    for row in rows:
        if row.get("symbol") in by_symbol:
            by_symbol[row["symbol"]].append(row)
    width, height = 880, 300
    series = {}
    for sym, vals in by_symbol.items():
        if not vals:
            continue
        base = _f(vals[0].get("open")) or _f(vals[0].get("close")) or 1.0
        series[sym] = [(i, ((_f(v.get("close")) or base) / base - 1) * 100) for i, v in enumerate(vals)]
    all_values = [v for points in series.values() for _, v in points]
    lo, hi = (min(all_values), max(all_values)) if all_values else (-1, 1)
    if lo == hi:
        lo -= 1
        hi += 1
    axis_y = height - 28 - ((0 - lo) / (hi - lo)) * (height - 56)
    lines = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='Intraday indexed line chart'>",
        "<rect width='100%' height='100%' rx='12' fill='#fbfcfc'/>",
        f"<line x1='28' x2='{width-28}' y1='{axis_y:.1f}' y2='{axis_y:.1f}' stroke='#aeb8b8' stroke-dasharray='4 5'/>",
    ]
    colors = {"NIFTY": "#0f766e", "BANKNIFTY": "#b45309"}
    for sym, points in series.items():
        coords = _polyline(points, width, height)
        lines.append(f"<polyline points='{coords}' fill='none' stroke='{colors[sym]}' stroke-width='3' stroke-linecap='round'/>")
        if points:
            lines.append(f"<text x='{width-118}' y='{42 if sym == 'NIFTY' else 68}' fill='{colors[sym]}' font-size='15' font-weight='700'>{sym} {_fmt(points[-1][1], 2, '%')}</text>")
    if by_symbol.get("NIFTY"):
        step = max(1, len(by_symbol["NIFTY"]) // 6)
        for idx in range(0, len(by_symbol["NIFTY"]), step):
            x = 28 + idx * ((width - 56) / max(len(by_symbol["NIFTY"]) - 1, 1))
            lines.append(f"<text x='{x:.1f}' y='{height-8}' text-anchor='middle' font-size='11' fill='#667'>{_h(by_symbol['NIFTY'][idx].get('time_ist'))}</text>")
    lines.append("</svg>")
    return "\n".join(lines)


def svg_breadth(data: dict[str, Any]) -> str:
    rows = data["hourly"]
    width, height = 880, 280
    pad = 40
    max_count = max([(_f(r.get("adv")) or 0) + (_f(r.get("decl")) or 0) for r in rows] or [1])
    slot = (width - pad * 2) / max(len(rows), 1)
    parts = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='Hourly advance decline bars'>",
        "<rect width='100%' height='100%' rx='12' fill='#fbfcfc'/>",
        f"<line x1='{pad}' x2='{width-pad}' y1='{height-pad}' y2='{height-pad}' stroke='#cad3d3'/>",
    ]
    for i, row in enumerate(rows):
        adv = _f(row.get("adv")) or 0
        decl = _f(row.get("decl")) or 0
        x = pad + i * slot + slot * 0.18
        bar_w = slot * 0.26
        adv_h = (adv / max_count) * (height - pad * 2)
        decl_h = (decl / max_count) * (height - pad * 2)
        parts.append(f"<rect x='{x:.1f}' y='{height-pad-adv_h:.1f}' width='{bar_w:.1f}' height='{adv_h:.1f}' rx='4' fill='#16a34a'/>")
        parts.append(f"<rect x='{x+bar_w+4:.1f}' y='{height-pad-decl_h:.1f}' width='{bar_w:.1f}' height='{decl_h:.1f}' rx='4' fill='#dc2626'/>")
        parts.append(f"<text x='{x+bar_w:.1f}' y='{height-12}' text-anchor='middle' font-size='11' fill='#667'>{_h(row.get('hour_ist'))}</text>")
    parts.append("<text x='52' y='28' fill='#16a34a' font-size='13' font-weight='700'>Advances</text>")
    parts.append("<text x='150' y='28' fill='#dc2626' font-size='13' font-weight='700'>Declines</text>")
    parts.append("</svg>")
    return "\n".join(parts)


def svg_sector_bars(data: dict[str, Any]) -> str:
    sectors = (data.get("sectors") or [])[:8] + (data.get("sectors") or [])[-8:]
    seen = set()
    rows = []
    for row in sectors:
        key = row["sector"]
        if key not in seen:
            seen.add(key)
            rows.append(row)
    width, height = 880, max(260, 34 * len(rows) + 36)
    vals = [_f(r.get("avg_pct")) or 0 for r in rows]
    max_abs = max([abs(v) for v in vals] or [1])
    mid = width * 0.52
    parts = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='Sector performance bars'>",
        "<rect width='100%' height='100%' rx='12' fill='#fbfcfc'/>",
        f"<line x1='{mid:.1f}' x2='{mid:.1f}' y1='20' y2='{height-18}' stroke='#cad3d3'/>",
    ]
    for i, row in enumerate(rows):
        y = 32 + i * 32
        val = _f(row.get("avg_pct")) or 0
        length = abs(val) / max_abs * (width * 0.35)
        x = mid if val >= 0 else mid - length
        color = "#0f766e" if val >= 0 else "#b91c1c"
        parts.append(f"<text x='24' y='{y+12}' font-size='12' fill='#243838'>{_h(row.get('sector'))[:38]}</text>")
        parts.append(f"<rect x='{x:.1f}' y='{y}' width='{length:.1f}' height='18' rx='5' fill='{color}' opacity='0.86'/>")
        parts.append(f"<text x='{mid + (length + 8 if val >= 0 else -length - 8):.1f}' y='{y+14}' text-anchor='{'start' if val >= 0 else 'end'}' font-size='12' fill='{color}' font-weight='700'>{_fmt(val, 2, '%')}</text>")
    parts.append("</svg>")
    return "\n".join(parts)


def svg_candlestick(data: dict[str, Any], symbol: str) -> str:
    bars = [row for row in data["intraday_path"] if row.get("symbol") == symbol]
    is_daily = False
    width, height = 880, 360
    pad_l, pad_r, pad_t, pad_b = 58, 68, 26, 38
    if not bars:
        # Fallback: use 60-day EOD OHLC from market.index_eod
        eod_sym = "Nifty 50" if symbol == "NIFTY" else "Nifty Bank"
        eod_bars = [
            r for r in data.get("eod_candles", [])
            if r.get("index_symbol") == eod_sym
        ]
        if not eod_bars:
            return f"<div class='empty-chart'>No intraday OHLC bars available for {_h(symbol)}</div>"
        bars = [
            {
                "open": r["open"], "high": r["high"], "low": r["low"],
                "close": r["close"], "time_ist": r["trade_date"],
            }
            for r in eod_bars
        ]
        is_daily = True
    prices: list[float] = []
    for row in bars:
        for key in ("open", "high", "low", "close"):
            val = _f(row.get(key))
            if val is not None:
                prices.append(val)
    if not prices:
        return f"<div class='empty-chart'>No usable price values available for {_h(symbol)}</div>"
    lo, hi = min(prices), max(prices)
    rng = max(hi - lo, hi * 0.002, 1.0)
    lo -= rng * 0.08
    hi += rng * 0.08
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    slot = plot_w / max(len(bars), 1)
    candle_w = max(4, min(16, slot * 0.58))

    def y(value: Any) -> float:
        val = _f(value)
        if val is None:
            val = lo
        return pad_t + ((hi - val) / (hi - lo)) * plot_h

    parts = [
        f"<svg class='tv-chart' viewBox='0 0 {width} {height}' role='img' aria-label='{_h(symbol)} intraday candlestick chart'>",
        "<rect width='100%' height='100%' rx='10' fill='#101722'/>",
        "<g stroke='#243142' stroke-width='1'>",
    ]
    for i in range(5):
        gy = pad_t + i * (plot_h / 4)
        parts.append(f"<line x1='{pad_l}' x2='{width-pad_r}' y1='{gy:.1f}' y2='{gy:.1f}'/>")
    for i in range(0, len(bars), max(1, len(bars) // 8)):
        gx = pad_l + i * slot + slot / 2
        parts.append(f"<line x1='{gx:.1f}' x2='{gx:.1f}' y1='{pad_t}' y2='{height-pad_b}'/>")
    parts.append("</g>")
    for i in range(5):
        val = hi - i * ((hi - lo) / 4)
        parts.append(f"<text x='{width-58}' y='{pad_t + i * (plot_h / 4) + 4:.1f}' fill='#9aa7b5' font-size='12'>{_num(val, 0)}</text>")
    for i, row in enumerate(bars):
        o, h, l, c = (_f(row.get("open")), _f(row.get("high")), _f(row.get("low")), _f(row.get("close")))
        if None in {o, h, l, c}:
            continue
        x = pad_l + i * slot + slot / 2
        color = "#22c7a9" if c >= o else "#ef5350"
        body_y = min(y(o), y(c))
        body_h = max(abs(y(o) - y(c)), 2)
        parts.append(f"<line x1='{x:.1f}' x2='{x:.1f}' y1='{y(h):.1f}' y2='{y(l):.1f}' stroke='{color}' stroke-width='1.4'/>")
        parts.append(f"<rect x='{x-candle_w/2:.1f}' y='{body_y:.1f}' width='{candle_w:.1f}' height='{body_h:.1f}' rx='2' fill='{color}'/>")
    step = max(1, len(bars) // 6)
    for i in range(0, len(bars), step):
        x = pad_l + i * slot + slot / 2
        parts.append(f"<text x='{x:.1f}' y='{height-12}' text-anchor='middle' fill='#9aa7b5' font-size='11'>{_h(bars[i].get('time_ist'))}</text>")
    last = bars[-1]
    last_close = _f(last.get("close"))
    if last_close is not None:
        ly = y(last_close)
        parts.append(f"<line x1='{pad_l}' x2='{width-pad_r}' y1='{ly:.1f}' y2='{ly:.1f}' stroke='#6dd3ff' stroke-dasharray='3 5' opacity='.75'/>")
        parts.append(f"<rect x='{width-66}' y='{ly-12:.1f}' width='58' height='24' rx='4' fill='#0ea5e9'/>")
        parts.append(f"<text x='{width-37}' y='{ly+4:.1f}' text-anchor='middle' fill='#ffffff' font-size='12' font-weight='800'>{_num(last_close, 0)}</text>")
    chart_label = f"{_h(symbol)} · Daily (60d)" if is_daily else f"{_h(symbol)} · 15m"
    parts.append(f"<text x='{pad_l}' y='22' fill='#e4edf4' font-size='15' font-weight='800'>{chart_label}</text>")
    parts.append("</svg>")
    return "\n".join(parts)


def svg_sector_heatmap(data: dict[str, Any]) -> str:
    rows = data.get("sectors", [])[:20]
    width, height = 880, 330
    cols = 5
    gap = 8
    pad = 18
    cell_w = (width - pad * 2 - gap * (cols - 1)) / cols
    cell_h = 62
    max_abs = max([abs(_f(r.get("avg_pct")) or 0) for r in rows] or [1])
    parts = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='Sector heatmap'>",
        "<rect width='100%' height='100%' rx='12' fill='#fbfcfc'/>",
    ]
    for idx, row in enumerate(rows):
        col = idx % cols
        line = idx // cols
        x = pad + col * (cell_w + gap)
        y = pad + line * (cell_h + gap)
        val = _f(row.get("avg_pct")) or 0
        intensity = min(0.95, 0.25 + abs(val) / max_abs * 0.7)
        color = f"rgba(15,118,110,{intensity:.2f})" if val >= 0 else f"rgba(185,28,28,{intensity:.2f})"
        text_color = "#ffffff" if intensity > 0.48 else "#102826"
        sector = str(row.get("sector") or "Unclassified")
        if len(sector) > 22:
            sector = sector[:21] + "..."
        parts.append(f"<rect x='{x:.1f}' y='{y:.1f}' width='{cell_w:.1f}' height='{cell_h}' rx='8' fill='{color}'/>")
        parts.append(f"<text x='{x+10:.1f}' y='{y+20:.1f}' fill='{text_color}' font-size='12' font-weight='800'>{_h(sector)}</text>")
        parts.append(f"<text x='{x+10:.1f}' y='{y+42:.1f}' fill='{text_color}' font-size='16' font-weight='900'>{_fmt(val, 2, '%')}</text>")
        parts.append(f"<text x='{x+cell_w-10:.1f}' y='{y+44:.1f}' text-anchor='end' fill='{text_color}' font-size='11'>{_int(row.get('adv'))}/{_int(row.get('decl'))}</text>")
    parts.append("</svg>")
    return "\n".join(parts)


def svg_stock_bubbles(data: dict[str, Any]) -> str:
    rows = sorted(data.get("symbol_day", []), key=lambda r: _f(r.get("volume")) or 0, reverse=True)[:42]
    width, height = 880, 490  # increased height for legend
    pad_l, pad_r, pad_t, pad_b = 74, 42, 46, 78  # increased left padding for Y-axis label
    if not rows:
        return "<div class='empty-chart'>No stock data available for bubble chart.</div>"
    chgs = [_f(r.get("day_pct")) or 0 for r in rows]
    vols = [_f(r.get("volume")) or 0 for r in rows]
    scores = [_f(r.get("technical_score")) for r in rows if _f(r.get("technical_score")) is not None]
    x_min, x_max = min(chgs), max(chgs)
    if x_min == x_max:
        x_min -= 1
        x_max += 1
    y_min, y_max = (min(scores), max(scores)) if scores else (0, 100)
    if y_min == y_max:
        y_min -= 5
        y_max += 5
    max_vol = max(vols or [1]) or 1  # guard against all-zero volumes
    score_mid = sorted(scores)[len(scores) // 2] if scores else 50.0

    def x(value: Any) -> float:
        val = _f(value) or 0
        return pad_l + ((val - x_min) / (x_max - x_min)) * (width - pad_l - pad_r)

    def y(value: Any) -> float:
        val = _f(value)
        if val is None:
            val = score_mid
        return pad_t + ((y_max - val) / (y_max - y_min)) * (height - pad_t - pad_b)

    zero_x = x(0)
    mid_y = y(score_mid)
    plot_left, plot_right = pad_l, width - pad_r
    plot_top, plot_bottom = pad_t, height - pad_b
    x_ticks = sorted({round(x_min, 1), 0.0, round(x_max, 1)})
    y_ticks = sorted({round(y_min, 0), round(score_mid, 0), round(y_max, 0)})
    label_symbols = {
        str(r.get("symbol") or "")
        for r in sorted(rows, key=lambda r: abs(_f(r.get("day_pct")) or 0), reverse=True)[:7]
    }
    label_symbols.update(
        str(r.get("symbol") or "")
        for r in sorted(rows, key=lambda r: _f(r.get("volume")) or 0, reverse=True)[:6]
    )
    parts = [
        f"<svg class='participation-map' viewBox='0 0 {width} {height}' role='img' aria-label='Stock participation map by day move, technical score, and volume'>",
        "<rect width='100%' height='100%' rx='12' fill='#fbfcfc'/>",
        f"<rect x='{plot_left}' y='{plot_top}' width='{plot_right-plot_left}' height='{plot_bottom-plot_top}' rx='8' fill='#ffffff' stroke='#dfe7e4'/>",
        f"<rect x='{zero_x:.1f}' y='{plot_top}' width='{max(plot_right-zero_x,0):.1f}' height='{max(mid_y-plot_top,0):.1f}' fill='#ecfdf5' opacity='.42'/>",
        f"<rect x='{plot_left}' y='{mid_y:.1f}' width='{max(zero_x-plot_left,0):.1f}' height='{max(plot_bottom-mid_y,0):.1f}' fill='#fff1f2' opacity='.5'/>",
        f"<line x1='{plot_left}' x2='{plot_right}' y1='{plot_bottom}' y2='{plot_bottom}' stroke='#b9c6c2'/>",
        f"<line x1='{plot_left}' x2='{plot_left}' y1='{plot_top}' y2='{plot_bottom}' stroke='#b9c6c2'/>",
        f"<line x1='{zero_x:.1f}' x2='{zero_x:.1f}' y1='{plot_top}' y2='{plot_bottom}' stroke='#7b8b87' stroke-dasharray='4 5'/>",
        f"<line x1='{plot_left}' x2='{plot_right}' y1='{mid_y:.1f}' y2='{mid_y:.1f}' stroke='#7b8b87' stroke-dasharray='4 5'/>",
        f"<text x='{plot_right-8}' y='{plot_top+18}' text-anchor='end' fill='#166534' font-size='12' font-weight='800'>Strength + participation</text>",
        f"<text x='{plot_left+8}' y='{plot_bottom-10}' fill='#991b1b' font-size='12' font-weight='800'>Pressure + weak score</text>",
        f"<text x='{plot_left}' y='24' fill='#172322' font-size='15' font-weight='900'>Participation Map</text>",
        f"<text x='{plot_left}' y='40' fill='#667370' font-size='12'>Day move vs technical score; circle area scales by stored intraday volume</text>",
    ]
    for tick in x_ticks:
        tx = x(tick)
        parts.append(f"<line x1='{tx:.1f}' x2='{tx:.1f}' y1='{plot_bottom}' y2='{plot_bottom+5}' stroke='#8fa09b'/>")
        parts.append(f"<text x='{tx:.1f}' y='{plot_bottom+21}' text-anchor='middle' fill='#667370' font-size='11'>{_fmt(tick,1,'%')}</text>")
    for tick in y_ticks:
        ty = y(tick)
        parts.append(f"<line x1='{plot_left-5}' x2='{plot_left}' y1='{ty:.1f}' y2='{ty:.1f}' stroke='#8fa09b'/>")
        parts.append(f"<text x='{plot_left-9}' y='{ty+4:.1f}' text-anchor='end' fill='#667370' font-size='11'>{_num(tick,0)}</text>")
    parts.append(f"<text x='{(plot_left+plot_right)//2}' y='{height-44}' text-anchor='middle' fill='#4c5b58' font-size='12' font-weight='800'>Day % move</text>")
    # Y-axis label positioned with proper rotation origin for visibility
    y_label_y = (plot_top + plot_bottom) // 2
    parts.append(f"<text x='24' y='{y_label_y}' fill='#4c5b58' font-size='12' font-weight='800' text-anchor='middle' transform='rotate(-90 24 {y_label_y})'>Technical Score</text>")
    
    # Tooltip container (hidden by default, positioned via JS)
    parts.append("<g id='bubble-tooltip' visibility='hidden' pointer-events='none'>")
    parts.append("<rect id='tt-bg' x='0' y='0' width='180' height='80' rx='6' fill='#1a2632' fill-opacity='.94'/>")
    parts.append("<text id='tt-sym' x='10' y='20' fill='#fff' font-size='13' font-weight='900'></text>")
    parts.append("<text id='tt-move' x='10' y='38' fill='#9ca3af' font-size='11'></text>")
    parts.append("<text id='tt-tech' x='10' y='52' fill='#9ca3af' font-size='11'></text>")
    parts.append("<text id='tt-vol' x='10' y='66' fill='#9ca3af' font-size='11'></text>")
    parts.append("</g>")
    
    for row in rows:
        vol = _f(row.get("volume")) or 0
        r = 5 + math.sqrt(vol / max_vol) * 20
        chg = _f(row.get("day_pct")) or 0
        score = _f(row.get("technical_score"))
        color = "#0f7a5f" if chg >= 0 else "#b4232b"
        stroke = "#0b5947" if chg >= 0 else "#7f1d1d"
        opacity = 0.74 if score is not None else 0.42
        cx, cy = x(chg), y(row.get("technical_score"))
        symbol = _h(row.get("symbol"))
        # Data attributes for tooltip
        data_attrs = f"data-sym='{symbol}' data-move='{_fmt(chg,2,'%')}' data-tech='{_num(score,1) or 'N/A'}' data-vol='{_num(vol/100000,1)}L'"
        nse_url = f"https://www.nseindia.com/get-quotes/equity?symbol={symbol}"
        parts.append(f"<a href='{nse_url}' target='_blank' rel='noopener'>")
        parts.append(f"<circle class='bubble' cx='{cx:.1f}' cy='{cy:.1f}' r='{r:.1f}' fill='{color}' fill-opacity='{opacity:.2f}' stroke='{stroke}' stroke-opacity='.55' stroke-width='1.2' style='cursor:pointer' {data_attrs}/>")
        parts.append("</a>")

    # Label placement with collision avoidance
    placed_labels: list[tuple[float, float, float, float]] = []  # (x1, y1, x2, y2) bboxes

    def _collides(lx: float, ly: float, tw: float = 50, th: float = 12) -> bool:
        """Check if label at (lx, ly) with width tw and height th collides with existing labels."""
        for bx1, by1, bx2, by2 in placed_labels:
            if not (lx + tw < bx1 or lx > bx2 or ly - th > by2 or ly < by1 - th):
                return True
        return False

    def _find_label_pos(cx: float, cy: float, r: float, symbol: str) -> tuple[float, float, str] | None:
        """Find non-colliding position for label. Returns (x, y, anchor) or None."""
        tw = len(symbol) * 6 + 8  # rough text width estimate
        th = 12
        # Try positions: right, left, top-right, top-left, bottom-right, bottom-left
        offsets = [
            (r + 6, 4, "start"),       # right
            (-r - 6 - tw, 4, "end"),   # left
            (r + 4, -r - 2, "start"),  # top-right
            (-r - 4, -r - 2, "end"),   # top-left
            (r + 4, r + 12, "start"),  # bottom-right
            (-r - 4, r + 12, "end"),   # bottom-left
        ]
        for ox, oy, anchor in offsets:
            lx = cx + ox if anchor == "start" else cx + ox + tw
            ly = cy + oy
            # Bounds check
            if lx < plot_left + 10 or lx + tw > plot_right - 10:
                continue
            if ly < plot_top + 10 or ly > plot_bottom - 4:
                continue
            if not _collides(lx if anchor == "start" else lx - tw, ly, tw, th):
                return (cx + ox if anchor == "start" else cx + ox, ly, anchor)
        return None

    for row in rows:
        symbol_raw = str(row.get("symbol") or "")
        if symbol_raw not in label_symbols:
            continue
        chg = _f(row.get("day_pct")) or 0
        vol = _f(row.get("volume")) or 0
        r = 5 + math.sqrt(vol / max_vol) * 20
        cx, cy = x(chg), y(row.get("technical_score"))
        pos = _find_label_pos(cx, cy, r, symbol_raw)
        if pos is None:
            continue  # skip if can't place without collision
        label_x, label_y, anchor = pos
        tw = len(symbol_raw[:11]) * 6 + 8
        # Register bbox
        if anchor == "start":
            placed_labels.append((label_x, label_y - 10, label_x + tw, label_y + 2))
        else:
            placed_labels.append((label_x - tw, label_y - 10, label_x, label_y + 2))
        # Add background for readability
        bg_x = label_x - 2 if anchor == "start" else label_x - tw - 2
        parts.append(f"<rect x='{bg_x:.1f}' y='{label_y - 10:.1f}' width='{tw + 4}' height='14' rx='2' fill='#fff' fill-opacity='.85'/>")
        parts.append(f"<text x='{label_x:.1f}' y='{label_y:.1f}' text-anchor='{anchor}' fill='#172322' font-size='10.5' font-weight='700'>{_h(symbol_raw[:11])}</text>")

    legend_x = width - 206
    legend_y = height - 58  # adjusted for increased height
    for i, frac in enumerate((0.25, 0.6, 1.0)):
        rr = 5 + math.sqrt(frac) * 20
        lx = legend_x + i * 58
        parts.append(f"<circle cx='{lx}' cy='{legend_y}' r='{rr:.1f}' fill='none' stroke='#71827e' stroke-width='1.1'/>")
        parts.append(f"<text x='{lx}' y='{legend_y+28}' text-anchor='middle' fill='#667370' font-size='10'>{_num((max_vol*frac)/100000,0)}L</text>")
    parts.append(f"<text x='{legend_x-28}' y='{legend_y+4}' text-anchor='end' fill='#4c5b58' font-size='11' font-weight='800'>Volume</text>")
    parts.append(f"<circle cx='{plot_right-142}' cy='26' r='6' fill='#0f7a5f' fill-opacity='.78'/><text x='{plot_right-130}' y='30' fill='#4c5b58' font-size='11'>Positive</text>")
    parts.append(f"<circle cx='{plot_right-72}' cy='26' r='6' fill='#b4232b' fill-opacity='.78'/><text x='{plot_right-60}' y='30' fill='#4c5b58' font-size='11'>Negative</text>")
    parts.append("</svg>")
    return "\n".join(parts)


def _leaders(items: Any, field: str = "chg_pct") -> str:
    rows = items or []
    out = []
    for item in rows:
        text = f"{item.get('symbol')} {_fmt(item.get(field), 2, '%' if field == 'chg_pct' else '')}"
        if field == "volume":
            text = f"{item.get('symbol')} {_num((_f(item.get('volume')) or 0) / 100000, 1)}L"
        out.append(_h(text))
    return ", ".join(out) if out else "-"


def _stock_button(symbol: Any) -> str:
    sym = str(symbol or "").upper()
    return f"<button class='stock-link' type='button' data-symbol='{_h(sym)}' aria-label='Show {_h(sym)} detail'>{_h(sym)}</button>"


def _safe_extreme(rows: list[dict[str, Any]], key: str, *, mode: str) -> dict[str, Any]:
    if not rows:
        return {}
    if mode == "max":
        return max(rows, key=lambda r: _f(r.get(key)) if _f(r.get(key)) is not None else -999999)
    return min(rows, key=lambda r: _f(r.get(key)) if _f(r.get(key)) is not None else 999999)


def _session_label(nifty_pct: Any, bank_pct: Any, best_breadth: Any, weak_breadth: Any) -> tuple[str, str]:
    nifty_val = _f(nifty_pct) or 0.0
    bank_val = _f(bank_pct) or 0.0
    best_val = _f(best_breadth) or 0.0
    weak_val = _f(weak_breadth) or 0.0
    if nifty_val > 0 and best_val >= 55 and weak_val < 45:
        return "Recovery After Shakeout", "Index finish improved after a weak breadth window."
    if nifty_val > 0 and bank_val > 0 and best_val >= 55:
        return "Constructive Breadth", "Indices and breadth closed with aligned support."
    if nifty_val < 0 and bank_val < 0 and best_val < 50:
        return "Risk-Off Session", "Index pressure was not offset by broad participation."
    if abs(nifty_val) < 0.15 and abs(bank_val) < 0.15:
        return "Range-Bound Session", "Index movement stayed contained; leadership quality matters."
    return "Mixed Market Tape", "Index action and breadth need confirmation next session."


def _latest_report_href(filename: str) -> str:
    return f"/reports/{filename}"


def _stock_detail_payload(data: dict[str, Any]) -> str:
    payload = {}
    for row in data.get("symbol_day", []):
        sym = str(row.get("symbol") or "").upper()
        if not sym:
            continue
        payload[sym] = {
            "symbol": sym,
            "company": row.get("company_name") or sym,
            "sector": row.get("sector") or "Unclassified",
            "marketCap": row.get("market_cap_cat") or "-",
            "stage": row.get("stage") or "-",
            "signal": row.get("trading_signal") or "-",
            "technicalScore": _f(row.get("technical_score")),
            "relativeStrength": _f(row.get("relative_strength")),
            "open": _f(row.get("day_open")),
            "close": _f(row.get("day_close")),
            "high": _f(row.get("day_high")),
            "low": _f(row.get("day_low")),
            "dayPct": _f(row.get("day_pct")),
            "volumeL": round((_f(row.get("volume")) or 0) / 100000, 1),
        }
    return json.dumps(payload, default=str)


def _stock_rows(rows: list[dict[str, Any]], *, sign_class: str) -> str:
    return "\n".join(
        f"<tr class='clickable-row' data-symbol='{_h(r.get('symbol'))}'>"
        f"<td>{_stock_button(r.get('symbol'))}</td>"
        f"<td>{_h(r.get('sector'))}</td>"
        f"<td class='{sign_class}'>{_fmt(r.get('day_pct'),2,'%')}</td>"
        f"<td>{_num((_f(r.get('volume')) or 0)/100000,1)}L</td>"
        f"<td>{_h(r.get('stage') or '-')}</td>"
        f"<td>{_h(r.get('trading_signal') or '-')}</td>"
        f"</tr>"
        for r in rows
    )


def build_html(data: dict[str, Any]) -> str:
    report_date = data["report_date"]
    nifty = next((r for r in data["index_daily"] if r.get("symbol") == "NIFTY"), {})
    bank = next((r for r in data["index_daily"] if r.get("symbol") == "BANKNIFTY"), {})
    commentary = data.get("llm_commentary") or {}
    generated = datetime.now().strftime("%Y-%m-%d %H:%M IST")
    source_mode = data.get("source_mode") or "intraday_15m"
    source_label = "EOD Close" if source_mode == "eod_only" else "15m Bars"
    source_note = (
        "PostgreSQL market.index_eod + market.equity_eod · intraday bars unavailable for this session"
        if source_mode == "eod_only"
        else "PostgreSQL intraday.ohlcv_bars · commentary grounded in computed facts"
    )
    source_coverage = (
        "Coverage note: this report uses NSE EOD close data from PostgreSQL because no 15m intraday bars were available for the session. "
        "Hourly breadth, intraday candles, and timing claims are intentionally omitted. Research and learning only; not investment advice."
        if source_mode == "eod_only"
        else "Coverage note: this report uses the stored intraday 15m universe available in PostgreSQL. It is not a complete NSE-wide breadth measure unless the intraday capture universe is complete. Research and learning only; not investment advice."
    )
    rows = data["hourly"]
    best_breadth = _safe_extreme(rows, "adv_pct", mode="max")
    weak_breadth = _safe_extreme(rows, "adv_pct", mode="min")
    best_volume = _safe_extreme(rows, "total_volume", mode="max")
    universe = max((_f(r.get("universe")) or 0 for r in rows), default=0)
    sectors = data.get("sectors", [])
    top_sector = sectors[0] if sectors else {}
    bottom_sector = sectors[-1] if sectors else {}
    session_title, session_detail = _session_label(
        nifty.get("day_pct"),
        bank.get("day_pct"),
        best_breadth.get("adv_pct"),
        weak_breadth.get("adv_pct"),
    )
    report_links = [
        ("Sector Rotation", "sector_rotation.html"),
        ("Stage 2 Tracker", "stage2_tracker.html"),
        ("Top Picks", "top_picks.html"),
        ("Swing Playbook", "swing_playbook.html"),
        ("Portfolio Lab", "portfolio_strategy_lab.html"),
    ]
    report_pack_html = "".join(
        f"<a class='report-link' href='{_h(_latest_report_href(filename))}'>{_h(label)}</a>"
        for label, filename in report_links
    )
    style = """
    :root{
    --bg:#f0f4f8;--card:#ffffff;--border:#e2e8f0;--soft-border:#f1f5f9;
    --text:#1a2332;--muted:#64748b;
    --primary:#1e3a5f;--primary-alt:#2563eb;
    --good:#16a34a;--risk:#dc2626;--watch:#d97706;
    --radius:8px;--shadow:0 1px 3px rgba(0,0,0,.08);--shadow-md:0 4px 8px rgba(0,0,0,.10);
    --panel:#111821;
    /* Backward-compat aliases — do not reference these in new CSS */
    --ink:var(--text);--line:var(--border);--soft-line:var(--soft-border);
    --green:var(--good);--red:var(--risk);--amber:var(--watch);--blue:var(--primary-alt);
    }
    *{box-sizing:border-box} html{scroll-behavior:smooth} body{margin:0;background:var(--bg);color:var(--text);font-family:'Inter','Segoe UI',-apple-system,BlinkMacSystemFont,sans-serif;font-size:14px;line-height:1.6}
    .wrap{max-width:1360px;margin:0 auto;padding:24px}.eyebrow{color:var(--muted);font-size:12px;text-transform:uppercase;font-weight:850;letter-spacing:.08em}
    header.hero{background:#ffffff;border:1px solid var(--line);border-radius:8px;padding:22px;box-shadow:var(--shadow);margin-bottom:16px}
    .hero-top{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}.title-block{max-width:760px}h1{margin:4px 0 8px;font-size:38px;line-height:1.06;letter-spacing:0}h2{font-size:19px;margin:0 0 14px}h3{font-size:15px;margin:0 0 8px;color:#223a37}.sub{color:var(--muted);font-size:14px}
    .session-badge{min-width:260px;border-left:4px solid var(--blue);padding:8px 0 8px 14px}.session-badge b{display:block;font-size:18px}.session-badge span{display:block;margin-top:4px;color:var(--muted);font-size:13px}
    .nav{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 0}.nav a,.report-link{display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:999px;padding:7px 10px;background:#fbfcfb;color:#243331;text-decoration:none;font-size:12px;font-weight:850}.nav a:hover,.report-link:hover{border-color:#95aaa5;background:#eef4f2}
    .report-pack{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:16px;padding-top:14px;border-top:1px solid var(--soft-line)}
    .grid{display:grid;gap:16px}.kpis{grid-template-columns:repeat(4,minmax(0,1fr))}.three{grid-template-columns:repeat(3,minmax(0,1fr))}.two{grid-template-columns:1.18fr .82fr}.halves{grid-template-columns:1fr 1fr}
    .card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:16px;box-shadow:0 1px 0 rgba(23,35,34,.04)}.section{margin-top:16px}.kpi .label{color:var(--muted);font-size:11px;text-transform:uppercase;font-weight:850;letter-spacing:.08em}.kpi .value{font-size:25px;font-weight:900;margin-top:5px;line-height:1.15}.kpi .note{margin-top:6px;color:var(--muted);font-size:13px}
    .pulse{display:grid;gap:10px}.pulse-row{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid var(--soft-line)}.pulse-row:last-child{border-bottom:0}.pulse-row span{color:var(--muted);font-size:13px}.pulse-row b{text-align:right}
    .pos{color:var(--green)}.neg{color:var(--red)}.flat{color:var(--amber)}.info{color:var(--blue)}
    .table-scroll{overflow-x:auto;border:1px solid var(--soft-line);border-radius:8px}.table-scroll table{min-width:760px}table{width:100%;border-collapse:collapse;font-size:13px}th,td{border-bottom:1px solid var(--soft-line);padding:9px 8px;text-align:left;vertical-align:top}th{color:#51625f;font-size:11px;text-transform:uppercase;letter-spacing:.06em;background:#fafbfb}tr:last-child td{border-bottom:0}
    .pill{display:inline-flex;border-radius:999px;padding:3px 9px;font-size:12px;font-weight:850;background:#eef4f2;color:#24413e}.pill.pos{background:#dcfce7;color:#166534}.pill.neg{background:#fee2e2;color:#991b1b}
    .event{display:grid;grid-template-columns:70px 1fr;gap:10px;padding:10px 0;border-bottom:1px solid var(--soft-line)}.event:last-child{border-bottom:0}.time{font-weight:900;color:#214744}.commentary{font-size:16px;max-width:92ch}.commentary p{margin:0 0 14px}.commentary p:last-child{margin-bottom:0}.commentary strong{color:#172322}.commentary ul{margin:0 0 14px 18px;padding:0}.commentary li{margin:4px 0}.muted{color:var(--muted)}
    .heat{display:inline-block;min-width:62px;font-weight:900;text-align:center;border-radius:6px;color:#fff;padding:3px 8px}.heat.g1{background:#166534}.heat.g2{background:#16a34a}.heat.n{background:#a16207}.heat.r1{background:#dc2626}.heat.r2{background:#991b1b}
    svg{max-width:100%;height:auto}.chart-dark{background:var(--panel);border-color:#1f2a38;color:#e4edf4}.chart-dark h2{color:#e4edf4}.empty-chart{min-height:220px;display:grid;place-items:center;color:var(--muted);border:1px dashed var(--line);border-radius:8px}
    .stock-link{border:0;background:transparent;color:var(--green);font-weight:900;font:inherit;cursor:pointer;padding:0;text-decoration:underline;text-underline-offset:3px}.stock-link:focus-visible,.nav a:focus-visible,.report-link:focus-visible{outline:3px solid rgba(31,95,153,.28);outline-offset:2px}.clickable-row{cursor:pointer}.clickable-row:hover{background:#f2f8f6}
    .detail-panel{position:sticky;top:12px}.detail-title{font-size:22px;font-weight:900}.detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:12px}.detail-kv{border:1px solid var(--soft-line);border-radius:8px;padding:10px;background:#fbfcfc}.detail-kv span{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;font-weight:850}.detail-kv b{font-size:16px;overflow-wrap:anywhere}
    .bubble-note{font-size:12px;color:var(--muted);margin-top:8px}.footer{margin-top:20px;color:var(--muted);font-size:12px;border-top:1px solid var(--line);padding-top:14px}
    .bubble{transition:stroke-width .15s ease, fill-opacity .15s ease}.participation-map a{text-decoration:none}
    @media(max-width:980px){.kpis,.three,.two,.halves{grid-template-columns:1fr}.wrap{padding:14px}.hero-top{display:block}h1{font-size:29px}.session-badge{min-width:0;margin-top:14px}.detail-panel{position:static}.table-scroll table{min-width:680px}}
    @media(max-width:560px){.card,header.hero{padding:13px}.event{grid-template-columns:58px 1fr}.kpi .value{font-size:21px}.detail-grid{grid-template-columns:1fr}}
    """
    hourly_rows = []
    for row in rows:
        adv_pct = _f(row.get("adv_pct")) or 0
        heat = "g1" if adv_pct >= 65 else "g2" if adv_pct >= 52 else "n" if adv_pct >= 45 else "r1" if adv_pct >= 30 else "r2"
        hourly_rows.append(
            f"<tr><td>{_h(row.get('hour_ist'))}</td>"
            f"<td class='{_class_pct(row.get('nifty_pct'))}'>{_fmt(row.get('nifty_pct'),2,'%')}</td>"
            f"<td class='{_class_pct(row.get('bank_pct'))}'>{_fmt(row.get('bank_pct'),2,'%')}</td>"
            f"<td>{_int(row.get('adv'))} / {_int(row.get('decl'))}</td>"
            f"<td><span class='heat {heat}'>{_fmt(row.get('adv_pct'),1,'%')}</span></td>"
            f"<td class='{_class_pct(row.get('avg_stock_chg_pct'))}'>{_fmt(row.get('avg_stock_chg_pct'),2,'%')}</td>"
            f"<td>{_num((_f(row.get('total_volume')) or 0)/100000,1)}L</td></tr>"
        )
    if not hourly_rows:
        hourly_rows.append("<tr><td colspan='7' class='muted'>No hourly intraday data available for this session.</td></tr>")
    events_html = "\n".join(
        f"<div class='event'><div class='time'>{_h(e['time'])}</div><div><strong>{_h(e['title'])}</strong><br><span class='muted'>{_h(e['detail'])}</span></div></div>"
        for e in data.get("events", [])
    ) or "<div class='muted'>No intraday event log available for this session.</div>"
    leaders = {r["hour_ist"]: r for r in data.get("hourly_leaders", [])}
    leader_rows = "\n".join(
        f"<tr><td>{_h(row.get('hour_ist'))}</td><td>{_leaders((leaders.get(row.get('hour_ist')) or {}).get('top_gainers'))}</td>"
        f"<td>{_leaders((leaders.get(row.get('hour_ist')) or {}).get('top_losers'))}</td>"
        f"<td>{_leaders((leaders.get(row.get('hour_ist')) or {}).get('volume_leaders'), 'volume')}</td></tr>"
        for row in rows
    ) or "<tr><td colspan='4' class='muted'>No hourly leadership data available for this session.</td></tr>"
    sector_rows = "\n".join(
        f"<tr><td>{_h(r.get('sector'))}</td><td>{_int(r.get('count'))}</td><td class='{_class_pct(r.get('avg_pct'))}'>{_fmt(r.get('avg_pct'),2,'%')}</td><td>{_int(r.get('adv'))} / {_int(r.get('decl'))}</td><td>{_fmt(r.get('adv_pct'),1,'%')}</td></tr>"
        for r in data.get("sectors", [])[:12]
    )
    losers_rows = _stock_rows(data.get("top_losers", [])[:10], sign_class="neg")
    gainers_rows = _stock_rows(data.get("top_gainers", [])[:10], sign_class="pos")
    stock_json = (
        _stock_detail_payload(data)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EOD Market Report {report_date}</title>
<style>{style}</style>
</head>
<body>
<main class="wrap">
  <header class="hero">
    <div class="hero-top">
      <div class="title-block">
        <div class="eyebrow">NSE Market Intelligence</div>
        <h1>EOD Market Report</h1>
        <div class="sub">{report_date} · generated {generated} · {_h(source_label)} from PostgreSQL</div>
      </div>
      <div class="session-badge">
        <b>{_h(session_title)}</b>
        <span>{_h(session_detail)}</span>
      </div>
    </div>
    <nav class="nav" aria-label="Report sections">
      <a href="#commentary">Commentary</a>
      <a href="#breadth">Breadth</a>
      <a href="#participation">Participation</a>
      <a href="#leaders">Leadership</a>
      <a href="#stocks">Stocks</a>
      <a href="#sectors">Sectors</a>
    </nav>
    <div class="report-pack">
      <span class="eyebrow">Report Pack</span>
      {report_pack_html}
    </div>
  </header>

  <section class="grid kpis">
    <div class="card kpi"><div class="label">NIFTY</div><div class="value {_class_pct(nifty.get('day_pct'))}">{_num(nifty.get('day_close'))} · {_fmt(nifty.get('day_pct'),2,'%')}</div><div class="sub">Range {_num(nifty.get('day_low'))} - {_num(nifty.get('day_high'))}</div></div>
    <div class="card kpi"><div class="label">BANKNIFTY</div><div class="value {_class_pct(bank.get('day_pct'))}">{_num(bank.get('day_close'))} · {_fmt(bank.get('day_pct'),2,'%')}</div><div class="sub">Range {_num(bank.get('day_low'))} - {_num(bank.get('day_high'))}</div></div>
    <div class="card kpi"><div class="label">Best Breadth Hour</div><div class="value info">{_h(best_breadth.get('hour_ist'))}</div><div class="note">{_fmt(best_breadth.get('adv_pct'),1,'%')} advancers</div></div>
    <div class="card kpi"><div class="label">Weakest Breadth Hour</div><div class="value flat">{_h(weak_breadth.get('hour_ist'))}</div><div class="note">{_fmt(weak_breadth.get('adv_pct'),1,'%')} advancers</div></div>
  </section>

  <section class="grid three section">
    <div class="card pulse">
      <h2>Market Pulse</h2>
      <div class="pulse-row"><span>Stored universe</span><b>{_int(universe)} stocks</b></div>
      <div class="pulse-row"><span>Volume peak</span><b>{_h(best_volume.get('hour_ist'))} · {_num((_f(best_volume.get('total_volume')) or 0)/100000,1)}L</b></div>
      <div class="pulse-row"><span>Leading sector</span><b class="{_class_pct(top_sector.get('avg_pct'))}">{_h(top_sector.get('sector'))} {_fmt(top_sector.get('avg_pct'),2,'%')}</b></div>
      <div class="pulse-row"><span>Pressure sector</span><b class="{_class_pct(bottom_sector.get('avg_pct'))}">{_h(bottom_sector.get('sector'))} {_fmt(bottom_sector.get('avg_pct'),2,'%')}</b></div>
    </div>
    <div class="card kpi">
      <div class="label">Breadth Swing</div>
      <div class="value">{_fmt(weak_breadth.get('adv_pct'),1,'%')} to {_fmt(best_breadth.get('adv_pct'),1,'%')}</div>
      <div class="note">{_h(weak_breadth.get('hour_ist'))} trough, {_h(best_breadth.get('hour_ist'))} expansion</div>
    </div>
    <div class="card kpi">
      <div class="label">Source Trail</div>
      <div class="value">{_h(source_label)}</div>
      <div class="note">{_h(source_note)}</div>
    </div>
  </section>

  <section class="grid two section" id="commentary">
    <div class="card">
      <h2>Market Desk Commentary</h2>
      <div class="commentary">{_commentary_markdown_html(commentary.get('text'))}</div>
    </div>
    <div class="card">
      <h2>Event Log</h2>
      {events_html}
    </div>
  </section>

  <section class="grid halves section">
    <div class="card chart-dark">
      <h2>NIFTY · Candlestick Tape</h2>
      {svg_candlestick(data, 'NIFTY')}
    </div>
    <div class="card chart-dark">
      <h2>BANKNIFTY · Candlestick Tape</h2>
      {svg_candlestick(data, 'BANKNIFTY')}
    </div>
  </section>

  <section class="grid two section" id="breadth">
    <div class="card">
      <h2>Hourly Advance / Decline</h2>
      {svg_breadth(data)}
    </div>
    <div class="card">
      <h2>Sector Heatmap</h2>
      {svg_sector_heatmap(data)}
    </div>
  </section>

  <section class="card section" id="participation">
    <h2>Participation Bubble Chart</h2>
    {svg_stock_bubbles(data)}
    <div class="bubble-note">Bubble size represents stored intraday volume. X-axis is day move; Y-axis is latest technical score where available.</div>
  </section>

  <section class="card section">
    <h2>Hour-By-Hour Tape</h2>
    <div class="table-scroll"><table><thead><tr><th>Hour</th><th>NIFTY</th><th>BANKNIFTY</th><th>A/D</th><th>Adv %</th><th>Avg Stock</th><th>Volume</th></tr></thead><tbody>{''.join(hourly_rows)}</tbody></table></div>
  </section>

  <section class="card section" id="leaders">
    <h2>Hourly Leadership And Pressure Points</h2>
    <div class="table-scroll"><table><thead><tr><th>Hour</th><th>Top Gainers</th><th>Top Losers</th><th>Volume Leaders</th></tr></thead><tbody>{leader_rows}</tbody></table></div>
  </section>

  <section class="grid two section" id="stocks">
    <div class="card">
      <h2>Top Advancers</h2>
      <div class="table-scroll"><table><thead><tr><th>Symbol</th><th>Sector</th><th>Day %</th><th>Volume</th><th>Stage</th><th>Signal</th></tr></thead><tbody>{gainers_rows}</tbody></table></div>
    </div>
    <div class="card">
      <h2>Top Decliners</h2>
      <div class="table-scroll"><table><thead><tr><th>Symbol</th><th>Sector</th><th>Day %</th><th>Volume</th><th>Stage</th><th>Signal</th></tr></thead><tbody>{losers_rows}</tbody></table></div>
    </div>
  </section>

  <section class="grid two section">
    <div class="card">
      <h2>Most Active Detail Panel</h2>
      <div class="table-scroll"><table><thead><tr><th>Most Active</th><th>Sector</th><th>Day %</th><th>Volume</th><th>Stage</th><th>Signal</th></tr></thead><tbody>{_stock_rows(data.get("volume_leaders", [])[:12], sign_class="flat")}</tbody></table></div>
    </div>
    <div class="card detail-panel" id="stock-detail">
      <div class="detail-title">Stock Detail</div>
      <div class="muted">Awaiting symbol selection.</div>
    </div>
  </section>

  <section class="card section" id="sectors">
    <h2>Sector Breadth</h2>
    <div class="table-scroll"><table><thead><tr><th>Sector</th><th>Stocks</th><th>Avg Day %</th><th>A/D</th><th>Adv %</th></tr></thead><tbody>{sector_rows}</tbody></table></div>
  </section>

  <div class="footer">
    {_h(source_coverage)}
  </div>
  <script type="application/json" id="stock-detail-data">{stock_json}</script>
  <script>
  const stockData = JSON.parse(document.getElementById('stock-detail-data').textContent);
  const panel = document.getElementById('stock-detail');
  function fmtNum(v, digits=2) {{
    if (v === null || v === undefined || Number.isNaN(Number(v))) return '-';
    return Number(v).toLocaleString('en-IN', {{minimumFractionDigits: digits, maximumFractionDigits: digits}});
  }}
  function fmtPct(v) {{
    if (v === null || v === undefined || Number.isNaN(Number(v))) return '-';
    const n = Number(v);
    return `${{n > 0 ? '+' : ''}}${{n.toFixed(2)}}%`;
  }}
  function renderStock(sym) {{
    const d = stockData[sym];
    if (!d) return;
    const cls = Number(d.dayPct || 0) >= 0 ? 'pos' : 'neg';
    panel.innerHTML = `
      <div class="detail-title">${{d.symbol}}</div>
      <div class="muted">${{d.company || d.symbol}} · ${{d.sector}}</div>
      <div class="detail-grid">
        <div class="detail-kv"><span>Day Move</span><b class="${{cls}}">${{fmtPct(d.dayPct)}}</b></div>
        <div class="detail-kv"><span>Volume</span><b>${{fmtNum(d.volumeL, 1)}}L</b></div>
        <div class="detail-kv"><span>Open / Close</span><b>${{fmtNum(d.open)}} → ${{fmtNum(d.close)}}</b></div>
        <div class="detail-kv"><span>Range</span><b>${{fmtNum(d.low)}} - ${{fmtNum(d.high)}}</b></div>
        <div class="detail-kv"><span>Stage</span><b>${{d.stage || '-'}}</b></div>
        <div class="detail-kv"><span>Signal</span><b>${{d.signal || '-'}}</b></div>
        <div class="detail-kv"><span>Technical Score</span><b>${{fmtNum(d.technicalScore, 1)}}</b></div>
        <div class="detail-kv"><span>Relative Strength</span><b>${{fmtNum(d.relativeStrength, 1)}}</b></div>
      </div>`;
  }}
  document.querySelectorAll('[data-symbol]').forEach(el => {{
    el.addEventListener('click', () => renderStock(el.dataset.symbol));
  }});
  const firstStock = Object.keys(stockData)[0];
  if (firstStock) renderStock(firstStock);

  // Bubble chart tooltip interactivity
  const tooltip = document.getElementById('bubble-tooltip');
  if (tooltip) {{
    const ttBg = document.getElementById('tt-bg');
    const ttSym = document.getElementById('tt-sym');
    const ttMove = document.getElementById('tt-move');
    const ttTech = document.getElementById('tt-tech');
    const ttVol = document.getElementById('tt-vol');
    const svg = tooltip.closest('svg');
    
    document.querySelectorAll('.bubble[data-sym]').forEach(bubble => {{
      bubble.addEventListener('mouseenter', (e) => {{
        const sym = bubble.getAttribute('data-sym');
        const move = bubble.getAttribute('data-move');
        const tech = bubble.getAttribute('data-tech');
        const vol = bubble.getAttribute('data-vol');
        
        ttSym.textContent = sym;
        ttMove.textContent = `Day Move: ${{move}}`;
        ttTech.textContent = `Technical: ${{tech}}`;
        ttVol.textContent = `Volume: ${{vol}}`;
        
        // Position tooltip near bubble
        const cx = parseFloat(bubble.getAttribute('cx'));
        const cy = parseFloat(bubble.getAttribute('cy'));
        const r = parseFloat(bubble.getAttribute('r'));
        let tx = cx + r + 10;
        let ty = cy - 40;
        
        // Keep within SVG bounds
        if (tx + 180 > 880) tx = cx - r - 190;
        if (ty < 10) ty = 10;
        if (ty + 80 > 480) ty = 400;
        
        tooltip.setAttribute('transform', `translate(${{tx}}, ${{ty}})`);
        tooltip.setAttribute('visibility', 'visible');
        
        // Highlight bubble on hover
        bubble.setAttribute('stroke-width', '3');
        bubble.setAttribute('fill-opacity', '0.95');
      }});
      
      bubble.addEventListener('mouseleave', () => {{
        tooltip.setAttribute('visibility', 'hidden');
        bubble.setAttribute('stroke-width', '1.2');
        const opacity = bubble.getAttribute('data-tech') !== 'N/A' ? '0.74' : '0.42';
        bubble.setAttribute('fill-opacity', opacity);
      }});
    }});
  }}
  </script>
</main>
</body>
</html>"""


def build_markdown(data: dict[str, Any]) -> str:
    report_date = data["report_date"]
    commentary = data.get("llm_commentary") or {}
    rows = data["hourly"]
    source_mode = data.get("source_mode") or "intraday_15m"
    nifty = next((r for r in data["index_daily"] if r.get("symbol") == "NIFTY"), {})
    bank = next((r for r in data["index_daily"] if r.get("symbol") == "BANKNIFTY"), {})
    best_breadth = max(rows, key=lambda r: _f(r.get("adv_pct")) or -1) if rows else {}
    weakest_breadth = min(rows, key=lambda r: _f(r.get("adv_pct")) or 999) if rows else {}
    coverage_note = (
        "Coverage note: NSE EOD close data from PostgreSQL; hourly intraday data was unavailable, so intraday timing claims are omitted."
        if source_mode == "eod_only"
        else "Coverage note: stored PostgreSQL 15m intraday universe; research only, not investment advice."
    )
    lines = [
        f"# End Of Day Market Report - {report_date}",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M IST')}",
        "",
        "## Summary",
        "",
        f"- NIFTY: {_num(nifty.get('day_close'))} ({_fmt(nifty.get('day_pct'), 2, '%')}) · Range: {_num(nifty.get('day_low'))}–{_num(nifty.get('day_high'))}",
        f"- BANKNIFTY: {_num(bank.get('day_close'))} ({_fmt(bank.get('day_pct'), 2, '%')}) · Range: {_num(bank.get('day_low'))}–{_num(bank.get('day_high'))}",
    ]
    # FII/DII
    fii = data.get("fii_dii") or {}
    if fii:
        lines.append(f"- FII: ₹{_fmt(fii.get('fii_net_today'), 2)} Cr · DII: ₹{_fmt(fii.get('dii_net_today'), 2)} Cr (5D FII: ₹{_fmt(fii.get('fii_net_5d'), 2)} Cr)")
    # Market breadth (EOD A/D + AD oscillator + TRIN)
    mb = data.get("market_breadth") or {}
    if mb:
        adv, dec = mb.get("advances") or 0, mb.get("declines") or 0
        ad_osc = mb.get("ad_oscillator")
        trin = mb.get("trin")
        sentiment = mb.get("market_sentiment") or ""
        breadth_parts = [f"A/D {_int(adv)}/{_int(dec)}"]
        if ad_osc is not None:
            breadth_parts.append(f"AD Oscillator {_fmt(ad_osc, 1)}")
        if trin is not None:
            breadth_parts.append(f"TRIN {_fmt(trin, 2)}")
        if sentiment:
            breadth_parts.append(sentiment)
        lines.append(f"- Breadth: {' · '.join(breadth_parts)}")
    # Intraday breadth hours (only when available)
    if best_breadth.get("hour_ist"):
        lines.append(f"- Best breadth hour: {best_breadth['hour_ist']} ({_fmt(best_breadth.get('adv_pct'),1,'%')} advancers)")
        lines.append(f"- Weakest breadth hour: {weakest_breadth.get('hour_ist')} ({_fmt(weakest_breadth.get('adv_pct'),1,'%')} advancers)")
    else:
        lines.append("- Best breadth hour: n/a")
        lines.append("- Weakest breadth hour: n/a")
    # Regime
    regime = data.get("regime") or {}
    if regime.get("regime"):
        lines.append(f"- Market Regime: **{regime['regime']}** (confidence {regime.get('confidence', '—')}%)")
    lines += [
        "",
        "## Commentary",
        "",
    ]
    # Format commentary: insert blank line before each bold subsection heading
    raw_commentary = str(commentary.get("text") or "").strip()
    formatted_commentary = raw_commentary
    import re as _re
    # Ensure each **Section** heading is preceded by a blank line and followed by a blank line
    formatted_commentary = _re.sub(r'(?<!\n)\n(\*\*[A-Z][^*]+\*\*)', r'\n\n\1', formatted_commentary)
    formatted_commentary = _re.sub(r'(\*\*[A-Z][^*]+\*\*)\n(?!\n)', r'\1\n\n', formatted_commentary)
    lines += [formatted_commentary, ""]

    # Hour-by-hour tape
    lines += [
        "## Hour-By-Hour Tape",
        "",
        "| Hour | NIFTY | BANKNIFTY | A/D | Adv % | Avg Stock | Volume |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('hour_ist')} | {_fmt(row.get('nifty_pct'),2,'%')} | {_fmt(row.get('bank_pct'),2,'%')} | "
            f"{_int(row.get('adv'))}/{_int(row.get('decl'))} | {_fmt(row.get('adv_pct'),1,'%')} | "
            f"{_fmt(row.get('avg_stock_chg_pct'),2,'%')} | {_num((_f(row.get('total_volume')) or 0)/100000,1)}L |"
        )
    if not rows:
        lines.append("| — | Intraday bars not available for this session | — | — | — | — | — |")

    # Event log — only include section if there are events
    events = data.get("events", [])
    if events:
        lines.extend(["", "## Event Log", ""])
        for event in events:
            lines.append(f"- **{event['time']} — {event['title']}:** {event['detail']}")

    top_gainers = data.get("top_gainers") or sorted(
        data.get("symbol_day", []),
        key=lambda row: _f(row.get("day_pct")) if _f(row.get("day_pct")) is not None else -999999,
        reverse=True,
    )
    top_losers = data.get("top_losers") or sorted(
        data.get("symbol_day", []),
        key=lambda row: _f(row.get("day_pct")) if _f(row.get("day_pct")) is not None else 999999,
    )
    lines.extend(["", "## Top Gainers", ""])
    for row in top_gainers[:10]:
        lines.append(f"- **{row.get('symbol')}**: {_fmt(row.get('day_pct'),2,'%')} ({row.get('sector')})")
    lines.extend(["", "## Top Losers", ""])
    for row in top_losers[:10]:
        lines.append(f"- **{row.get('symbol')}**: {_fmt(row.get('day_pct'),2,'%')} ({row.get('sector')})")
    lines.extend(["", f"> {coverage_note}", ""])
    return "\n".join(lines)


def write_report(data: dict[str, Any], paths: ReportPaths) -> None:
    paths.html.parent.mkdir(parents=True, exist_ok=True)
    LATEST_DIR.mkdir(parents=True, exist_ok=True)
    paths.html.write_text(build_html(data), encoding="utf-8")
    paths.md.write_text(build_markdown(data), encoding="utf-8")
    shutil.copy2(paths.html, paths.latest_html)
    shutil.copy2(paths.md, paths.latest_md)


def report_paths(report_date: date) -> ReportPaths:
    out_dir = REPORT_ROOT / str(report_date.year)
    stem = f"EOD_Market_Report_{report_date.strftime('%Y%m%d')}"
    return ReportPaths(
        html=out_dir / f"{stem}.html",
        md=out_dir / f"{stem}.md",
        latest_html=LATEST_DIR / "eod_market_report.html",
        latest_md=LATEST_DIR / "eod_market_report.md",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Report date in YYYY-MM-DD. Defaults to latest 15m intraday date.")
    parser.add_argument("--no-open", action="store_true", help="Do not open the HTML report after generation.")
    args = parser.parse_args()
    with psycopg2.connect(PG_DSN) as conn:
        report_date = latest_intraday_date(conn, args.date)
        data = enrich_data(load_report_data(conn, report_date))
    paths = report_paths(report_date)
    write_report(data, paths)
    print(f"HTML: {paths.html}")
    print(f"MD:   {paths.md}")
    print(f"Latest HTML: {paths.latest_html}")
    print(f"Latest MD:   {paths.latest_md}")
    if not args.no_open and sys.platform == "darwin":
        os.system(f"open {paths.html!s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
