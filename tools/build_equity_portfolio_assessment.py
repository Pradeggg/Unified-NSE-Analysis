#!/usr/bin/env python3
"""Build a grounded assessment of a downloaded equity portfolio CSV.

The script keeps the broker/downloaded portfolio file local and enriches it with
local Agent Adda PostgreSQL evidence: symbol resolution, stage/technical
snapshots, financial statements, sector context, and stored broker facts.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import psycopg2
import psycopg2.extras


DEFAULT_PORTFOLIO = Path("/Users/pgorai/Downloads/8500589913_PortFolioEqtSummary.csv")
DEFAULT_OUT_DIR = Path("reports/portfolio_assessments")
MASTER_CACHE = Path("data/_nse_master_cache/quote_equity_meta.json")
SECTOR_ROTATION_REPORT = Path("reports/latest/sector_rotation.md")
INDEX_STOCK_MAPPING = Path("data/index_stock_mapping.csv")

PUBLIC_RESEARCH_NOTES: dict[str, dict[str, Any]] = {
    "ICICIBANK": {
        "status": "deep_checked",
        "broker_view": "Consensus positive; portfolio action is concentration trim, not thesis rejection.",
        "summary": "Public broker aggregation showed a positive long-term ICICI Bank view with consensus target around Rs. 1,704.89 and recent Motilal Oswal buy coverage. Local evidence still caps exposure because this is the largest holding at more than 10% of portfolio value.",
        "sources": [
            {"label": "Trendlyne ICICI Bank research reports", "url": "https://trendlyne.com/research-reports/stock/584/ICICIBANK/icici-bank-ltd/"},
        ],
        "confidence": "medium",
    },
    "HDFCBANK": {
        "status": "deep_checked",
        "broker_view": "Consensus positive, but local trend is adverse.",
        "summary": "Public broker aggregation showed a positive HDFC Bank consensus target near Rs. 1,022.60 to Rs. 1,040 and multiple buy calls after Q4 FY26. Local technical evidence is Stage 4 / SELL, so the dashboard keeps this in sell-reduce review until price action repairs.",
        "sources": [
            {"label": "Trendlyne HDFC Bank research reports", "url": "https://trendlyne.com/research-reports/stock/533/HDFCBANK/hdfc-bank-ltd/"},
            {"label": "Trendlyne HDFC Bank consensus estimates", "url": "https://trendlyne.com/equity/consensus-estimates/533/HDFCBANK/hdfc-bank-ltd/"},
        ],
        "confidence": "medium",
    },
    "TCS": {
        "status": "deep_checked",
        "broker_view": "Consensus positive; local stance is hold/no fresh add.",
        "summary": "Public analyst aggregation showed TCS consensus target around Rs. 2,945 and several buy reports, but local stage evidence is not add-quality yet. The dashboard treats it as a quality large-cap hold until technical repair confirms.",
        "sources": [
            {"label": "Trendlyne TCS consensus estimates", "url": "https://trendlyne.com/equity/consensus-estimates/1372/TCS/tata-consultancy-services-ltd/"},
            {"label": "Trendlyne TCS research reports", "url": "https://trendlyne.com/research-reports/post/TCS/1372/tata-consultancy-services-ltd/"},
        ],
        "confidence": "medium",
    },
    "TATASTEEL": {
        "status": "deep_checked",
        "broker_view": "Consensus constructive, but cyclical and technically mixed.",
        "summary": "Public analyst aggregation showed Tata Steel target around Rs. 225 with FY27 growth expectations. Local evidence keeps this as hold/no fresh add because trading signal is weak and metals remain a cyclical exposure.",
        "sources": [
            {"label": "Trendlyne Tata Steel consensus estimates", "url": "https://trendlyne.com/equity/consensus-estimates/1366/TATASTEEL/tata-steel-ltd/"},
        ],
        "confidence": "medium",
    },
    "BEL": {
        "status": "deep_checked",
        "broker_view": "Consensus positive; local technical risk is high.",
        "summary": "Public broker aggregation showed BEL average target around Rs. 483.83 and recent buy reports, supported by defence order visibility. Local technical evidence is Stage 4 / SELL, so the dashboard keeps it in sell-reduce review despite the public long-term narrative.",
        "sources": [
            {"label": "Trendlyne BEL research reports", "url": "https://trendlyne.com/research-reports/stock/175/BEL/bharat-electronics-ltd/"},
            {"label": "ICICI Direct BEL FY26 outlook", "url": "https://www.icicidirect.com/research/equity/blog/bharat-electronics-fy26-numbers-in-line-outlook-intact-as-heavy-order-inflows-guided"},
        ],
        "confidence": "medium",
    },
    "TECHM": {
        "status": "deep_checked",
        "broker_view": "Public broker view constructive; local action remains hold.",
        "summary": "Public broker lists included Tech Mahindra as a buy idea with a target near Rs. 1,800. Local evidence is Stage 2 but not a fresh add because technical score is just below add threshold and the position already has gains.",
        "sources": [
            {"label": "ICICI Direct investing ideas", "url": "https://www.icicidirect.com/research/equity/investing-ideas/all/buy"},
        ],
        "confidence": "low",
    },
    "BSE": {
        "status": "deep_checked",
        "broker_view": "Recent public results positive; price reaction mixed.",
        "summary": "Recent public news reported BSE Q1 profit up 62% YoY to Rs. 874 crore and revenue up 63%, but the stock reaction was mixed. Local report keeps it hold/no fresh add until technical evidence strengthens.",
        "sources": [
            {"label": "Economic Times BSE Q1 results", "url": "https://m.economictimes.com/markets/stocks/earnings/bse-q1-results-profit-soars-62-yoy-to-rs-874-crore-revenue-surges-63/articleshow/132862347.cms"},
            {"label": "NSE BSE corporate filings", "url": "https://www.nseindia.com/companies-listing/corporate-filings-announcements?symbol=BSE&tabIndex=equity"},
        ],
        "confidence": "medium",
    },
    "EXIDEIND": {
        "status": "deep_checked",
        "broker_view": "Public broker report constructive; local action is add on pullback.",
        "summary": "Public broker research lists Exide Industries with ICICI Direct buy coverage and target around Rs. 480. Local evidence also shows Stage 2 with strong technicals, so the dashboard marks add on pullback rather than chase.",
        "sources": [
            {"label": "Trendlyne all broker reports", "url": "https://trendlyne.com/research-reports/all/"},
        ],
        "confidence": "low",
    },
}


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    text = text.replace("%", "")
    text = re.sub(r"^\-\s+", "-", text)
    accounting_negative = text.startswith("(") and text.endswith(")")
    if accounting_negative:
        text = text[1:-1].strip()
    try:
        number = float(text)
        return -number if accounting_negative else number
    except ValueError:
        return None


def pct_change(new: Any, old: Any) -> float | None:
    new_v = parse_number(new)
    old_v = parse_number(old)
    if new_v is None or old_v in (None, 0):
        return None
    return (new_v - old_v) / abs(old_v) * 100.0


def fmt_inr(value: Any) -> str:
    number = parse_number(value)
    if number is None:
        return "-"
    return f"Rs. {number:,.0f}"


def fmt_pct(value: Any, digits: int = 1) -> str:
    number = parse_number(value)
    if number is None:
        return "-"
    return f"{number:.{digits}f}%"


def clean_json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: clean_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_json(v) for v in value]
    return value


def load_holdings(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        holdings = []
        for row_number, row in enumerate(reader, start=2):
            market_value = parse_number(row.get("Value At Market Price")) or 0.0
            cost_value = parse_number(row.get("Value At Cost")) or 0.0
            unrealized_pl = parse_number(row.get("Unrealized Profit/Loss"))
            unrealized_pl_pct = parse_number(row.get("Unrealized Profit/Loss %"))
            if unrealized_pl_pct is None and cost_value:
                unrealized_pl_pct = ((market_value - cost_value) / abs(cost_value)) * 100.0
            holdings.append(
                {
                    "row_number": row_number,
                    "broker_symbol": (row.get("Stock Symbol") or "").strip().upper(),
                    "company_name": (row.get("Company Name") or "").strip(),
                    "isin": (row.get("ISIN Code") or "").strip().upper(),
                    "quantity": parse_number(row.get("Qty")),
                    "average_cost_price": parse_number(row.get("Average Cost Price")),
                    "current_market_price": parse_number(row.get("Current Market Price")),
                    "change_prev_close_pct": parse_number(row.get("% Change over prev close")),
                    "value_at_cost": cost_value,
                    "value_at_market": market_value,
                    "realized_pl": parse_number(row.get("Realized Profit / Loss")),
                    "unrealized_pl": unrealized_pl if unrealized_pl is not None else market_value - cost_value,
                    "unrealized_pl_pct": unrealized_pl_pct,
                }
            )
    total = sum(h["value_at_market"] for h in holdings)
    for holding in holdings:
        holding["portfolio_weight_pct"] = (holding["value_at_market"] / total * 100.0) if total else 0.0
    return holdings


def load_master_cache(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    by_isin: dict[str, dict[str, Any]] = {}
    if isinstance(raw, dict):
        for symbol, meta in raw.items():
            isin = str((meta or {}).get("isin") or "").strip().upper()
            if isin:
                row = dict(meta)
                row["symbol"] = symbol
                by_isin[isin] = row
    return by_isin


def load_index_memberships(path: Path) -> dict[str, set[str]]:
    if not path.exists():
        return {}
    memberships: dict[str, set[str]] = defaultdict(set)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            index_name = str(row.get("INDEX_NAME") or "").strip().upper()
            symbol = str(row.get("STOCK_SYMBOL") or "").strip().upper()
            if index_name and symbol:
                memberships[symbol].add(index_name)
    return memberships


def public_overlay(symbol: str, company_name: str) -> dict[str, Any]:
    clean_symbol = symbol.strip().upper()
    query = quote_plus(clean_symbol or company_name)
    links = []
    if clean_symbol:
        links.extend(
            [
                {
                    "label": "NSE quote",
                    "url": f"https://www.nseindia.com/get-quotes/equity?symbol={quote_plus(clean_symbol)}",
                },
                {
                    "label": "NSE announcements",
                    "url": f"https://www.nseindia.com/companies-listing/corporate-filings-announcements?symbol={quote_plus(clean_symbol)}&tabIndex=equity",
                },
                {
                    "label": "Screener financials",
                    "url": f"https://www.screener.in/company/{quote_plus(clean_symbol)}/consolidated/",
                },
                {
                    "label": "Trendlyne research search",
                    "url": f"https://trendlyne.com/research-reports/all/?q={quote_plus(clean_symbol)}",
                },
            ]
        )
    links.extend(
        [
            {
                "label": "BSE announcements",
                "url": "https://www.bseindia.com/corporates/ann.html",
            },
            {
                "label": "Web search",
                "url": f"https://www.google.com/search?q={query}+NSE+BSE+results+broker+research",
            },
        ]
    )
    note = PUBLIC_RESEARCH_NOTES.get(clean_symbol, {})
    source_links = note.get("sources") or []
    return {
        "public_research_status": note.get("status") or ("link_only" if clean_symbol else "unresolved"),
        "public_broker_view": note.get("broker_view") or "No cached public broker note; use source links for fresh verification.",
        "public_research_summary": note.get("summary") or "Public source links are provided; no cached public research narrative was added for this holding in this run.",
        "public_research_confidence": note.get("confidence") or "needs_verification",
        "public_links": links + source_links,
        "public_source_trail": " | ".join(link["label"] for link in links + source_links),
    }


def connect_db() -> Any:
    dsn = (
        os.environ.get("PG_DSN")
        or os.environ.get("AGENT_ADDA_PG_DSN")
        or "dbname=nse_market user=nse_admin host=/tmp"
    )
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    return conn


def fetch_rows(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def fetch_one(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    rows = fetch_rows(conn, sql, params)
    return rows[0] if rows else {}


def index_by(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {str(row.get(key) or "").upper(): row for row in rows if row.get(key)}


def fetch_db_evidence(conn: Any, symbols: list[str], isins: list[str]) -> dict[str, Any]:
    instruments_by_isin = index_by(
        fetch_rows(
            conn,
            """
            SELECT symbol, isin, company_name, sector, industry, market_cap_cat, is_etf,
                   is_fno, is_nifty50, is_nifty500, status
            FROM ref.instruments
            WHERE isin = ANY(%s)
            """,
            (isins,),
        ),
        "isin",
    )
    instruments_by_symbol = index_by(
        fetch_rows(
            conn,
            """
            SELECT symbol, isin, company_name, sector, industry, market_cap_cat, is_etf,
                   is_fno, is_nifty50, is_nifty500, status
            FROM ref.instruments
            WHERE symbol = ANY(%s)
            """,
            (symbols,),
        ),
        "symbol",
    )
    resolved_symbols = sorted(
        {
            str(row.get("symbol") or "").upper()
            for row in list(instruments_by_isin.values()) + list(instruments_by_symbol.values())
            if row.get("symbol")
        }
        | {symbol.strip().upper() for symbol in symbols if symbol.strip()}
    )
    stage_snapshot = fetch_one(conn, "SELECT max(snapshot_date) AS snapshot_date FROM scores.stage_snapshots")
    latest_eod = fetch_one(conn, "SELECT max(trade_date) AS trade_date FROM market.equity_eod")
    if not resolved_symbols:
        return {
            "snapshot_date": stage_snapshot.get("snapshot_date"),
            "latest_eod_date": latest_eod.get("trade_date"),
            "instruments_by_isin": instruments_by_isin,
            "instruments_by_symbol": instruments_by_symbol,
        }

    stages = index_by(
        fetch_rows(
            conn,
            """
            WITH latest AS (SELECT max(snapshot_date) AS d FROM scores.stage_snapshots)
            SELECT s.*
            FROM scores.stage_snapshots s, latest
            WHERE s.snapshot_date = latest.d
              AND s.symbol = ANY(%s)
            """,
            (resolved_symbols,),
        ),
        "symbol",
    )
    eod = index_by(
        fetch_rows(
            conn,
            """
            SELECT DISTINCT ON (symbol)
                   symbol, trade_date, close, change_pct, volume, turnover_cr,
                   total_trades, delivery_pct, week52_high, week52_low, market_cap_cr
            FROM market.equity_eod
            WHERE symbol = ANY(%s)
            ORDER BY symbol, trade_date DESC
            """,
            (resolved_symbols,),
        ),
        "symbol",
    )
    quarterly = index_by(
        fetch_rows(
            conn,
            """
            WITH ranked AS (
                SELECT symbol, period_label, period_end, revenue, operating_profit, opm_pct, pat, eps,
                       row_number() OVER (PARTITION BY symbol ORDER BY period_end DESC) AS rn
                FROM scores.quarterly_results
                WHERE symbol = ANY(%s)
            )
            SELECT q1.symbol,
                   q1.period_label AS q_period, q1.period_end AS q_period_end,
                   q1.revenue AS q_revenue, q1.operating_profit AS q_operating_profit,
                   q1.opm_pct AS q_opm_pct, q1.pat AS q_pat, q1.eps AS q_eps,
                   q2.revenue AS prev_q_revenue, q2.pat AS prev_q_pat,
                   q5.revenue AS yoy_q_revenue, q5.pat AS yoy_q_pat
            FROM ranked q1
            LEFT JOIN ranked q2 ON q2.symbol = q1.symbol AND q2.rn = 2
            LEFT JOIN ranked q5 ON q5.symbol = q1.symbol AND q5.rn = 5
            WHERE q1.rn = 1
            """,
            (resolved_symbols,),
        ),
        "symbol",
    )
    annual = index_by(
        fetch_rows(
            conn,
            """
            WITH ranked AS (
                SELECT symbol, period_label, period_end, revenue, operating_profit, opm_pct, pat, eps,
                       dividend_payout_pct,
                       row_number() OVER (PARTITION BY symbol ORDER BY period_end DESC) AS rn
                FROM scores.annual_results
                WHERE symbol = ANY(%s)
            )
            SELECT a1.symbol,
                   a1.period_label AS a_period, a1.period_end AS a_period_end,
                   a1.revenue AS a_revenue, a1.operating_profit AS a_operating_profit,
                   a1.opm_pct AS a_opm_pct, a1.pat AS a_pat, a1.eps AS a_eps,
                   a1.dividend_payout_pct AS a_dividend_payout_pct,
                   a2.revenue AS prev_a_revenue, a2.pat AS prev_a_pat
            FROM ranked a1
            LEFT JOIN ranked a2 ON a2.symbol = a1.symbol AND a2.rn = 2
            WHERE a1.rn = 1
            """,
            (resolved_symbols,),
        ),
        "symbol",
    )
    balance_sheet = index_by(
        fetch_rows(
            conn,
            """
            SELECT DISTINCT ON (symbol)
                   symbol, period_label AS bs_period, period_end AS bs_period_end,
                   borrowings, total_liabilities, total_assets, net_debt
            FROM scores.balance_sheet
            WHERE symbol = ANY(%s)
            ORDER BY symbol, period_end DESC
            """,
            (resolved_symbols,),
        ),
        "symbol",
    )
    cash_flow = index_by(
        fetch_rows(
            conn,
            """
            SELECT DISTINCT ON (symbol)
                   symbol, period_label AS cf_period, period_end AS cf_period_end,
                   operating_cf, investing_cf, financing_cf, net_cf
            FROM scores.cash_flow
            WHERE symbol = ANY(%s)
            ORDER BY symbol, period_end DESC
            """,
            (resolved_symbols,),
        ),
        "symbol",
    )
    broker = index_by(
        fetch_rows(
            conn,
            """
            SELECT f.symbol,
                   count(*) AS broker_fact_count,
                   string_agg(DISTINCT r.broker_code, ', ' ORDER BY r.broker_code) AS broker_sources,
                   string_agg(DISTINCT r.report_title, ' | ' ORDER BY r.report_title) AS broker_titles,
                   string_agg(
                       DISTINCT concat_ws(': ', f.fact_type, NULLIF(left(f.fact_value, 120), '')),
                       ' | '
                       ORDER BY concat_ws(': ', f.fact_type, NULLIF(left(f.fact_value, 120), ''))
                   ) AS broker_fact_summary
            FROM company_intel.broker_research_facts f
            JOIN company_intel.broker_reports r ON r.broker_report_id = f.broker_report_id
            WHERE f.symbol = ANY(%s)
            GROUP BY f.symbol
            """,
            (resolved_symbols,),
        ),
        "symbol",
    )

    sector_context_rows = fetch_rows(
        conn,
        """
        WITH latest AS (SELECT max(snapshot_date) AS d FROM scores.stage_snapshots),
             wanted AS (
                 SELECT DISTINCT sector
                 FROM scores.stage_snapshots s, latest
                 WHERE s.snapshot_date = latest.d
                   AND s.symbol = ANY(%s)
                   AND sector IS NOT NULL
                   AND sector <> ''
             )
        SELECT i.sector,
               count(*) AS sector_stock_count,
               avg(s.change_1m_pct) AS sector_avg_1m_pct,
               avg(s.relative_strength) AS sector_avg_rs,
               avg(s.technical_score) AS sector_avg_technical,
               avg(coalesce(s.enhanced_fund_score, s.fundamental_score)) AS sector_avg_fundamental,
               count(*) FILTER (WHERE s.trading_signal IN ('BUY', 'STRONG_BUY')) AS sector_buy_count,
               count(*) FILTER (
                   WHERE upper(coalesce(s.stage, '')) LIKE '%%STAGE_2%%'
               ) AS sector_stage2_count
        FROM scores.stage_snapshots s
        JOIN scores.stage_snapshots i
          ON i.snapshot_date = s.snapshot_date
         AND i.symbol = s.symbol,
             latest, wanted
        WHERE s.snapshot_date = latest.d
          AND i.sector = wanted.sector
        GROUP BY i.sector
        """,
        (resolved_symbols,),
    )
    sector_context = index_by(sector_context_rows, "sector")

    return {
        "snapshot_date": stage_snapshot.get("snapshot_date"),
        "latest_eod_date": latest_eod.get("trade_date"),
        "instruments_by_isin": instruments_by_isin,
        "instruments_by_symbol": instruments_by_symbol,
        "stages": stages,
        "eod": eod,
        "quarterly": quarterly,
        "annual": annual,
        "balance_sheet": balance_sheet,
        "cash_flow": cash_flow,
        "broker": broker,
        "sector_context": sector_context,
    }


def parse_sector_rotation(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text().splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 12 or not cells[0].isdigit():
            continue
        out[cells[2].lower()] = {
            "rank": int(cells[0]),
            "index": cells[1],
            "sector_lens": cells[2],
            "one_month": cells[5],
            "score": parse_number(cells[11]),
        }
    return out


def read_market_context(path: Path) -> str:
    if not path.exists():
        return "Market context unavailable in local sector rotation report."
    text = path.read_text()
    match = re.search(r"## Market Brief\n(?P<body>.*?)\n## 1\. Sector Rotation", text, flags=re.S)
    if not match:
        return "Market context unavailable in local sector rotation report."
    body = match.group("body")
    body = re.sub(r"\*\*(.*?)\*\*", r"\1", body)
    body = re.sub(r"\n+", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    return body[:1800]


def sector_lens_for(sector: str | None, industry: str | None) -> str:
    text = f"{sector or ''} {industry or ''}".lower()
    if any(token in text for token in ("it", "technology", "software", "computer", "digital")):
        return "IT & Technology"
    if any(token in text for token in ("pharma", "health", "hospital", "diagnostic", "drug")):
        return "Pharma & Healthcare"
    if any(token in text for token in ("capital", "industrial", "engineering", "electrical", "machinery")):
        return "Capital Goods & Industrials"
    if any(token in text for token in ("logistics", "transport", "port", "shipping")):
        return "Logistics & Transport"
    if any(token in text for token in ("psu bank", "public sector bank")):
        return "Banking - PSU"
    if any(token in text for token in ("bank", "financial", "finance", "nbfc", "insurance")):
        return "Financials"
    if any(token in text for token in ("defence", "aerospace")):
        return "Defence & Aerospace"
    if any(token in text for token in ("metal", "steel", "mining")):
        return "Metals & Mining"
    if any(token in text for token in ("auto", "automobile", "ancillary")):
        return "Auto"
    if any(token in text for token in ("consumer", "fmcg", "retail")):
        return "Consumer"
    return sector or "Unclassified"


def is_etf_like(holding: dict[str, Any], instrument: dict[str, Any] | None) -> bool:
    if instrument and instrument.get("is_etf"):
        return True
    text = f"{holding.get('broker_symbol', '')} {holding.get('company_name', '')}".upper()
    return any(token in text for token in ("ETF", "BEES", "GOLD", "NIFTY", "INDEX FUND"))


def market_cap_bucket(
    instrument: dict[str, Any] | None,
    holding: dict[str, Any],
    etf_like: bool,
    eod: dict[str, Any] | None = None,
) -> str:
    if etf_like:
        return "ETF"
    market_cap_cr = parse_number((eod or {}).get("market_cap_cr"))
    if market_cap_cr is not None:
        if market_cap_cr >= 100000:
            return "Mega/Large"
        if market_cap_cr >= 40000:
            return "Large"
        if market_cap_cr >= 10000:
            return "Mid/Large"
        if market_cap_cr >= 3000:
            return "Small/Mid"
        return "Small/Micro"
    if not instrument:
        return "Unresolved"
    if instrument.get("is_nifty50"):
        return "Nifty50/Large"
    if instrument.get("market_cap_cat"):
        return str(instrument.get("market_cap_cat"))
    if instrument.get("is_nifty500"):
        return "Nifty500"
    return "Listed"


def target_weight_cap(
    instrument: dict[str, Any] | None,
    holding: dict[str, Any],
    etf_like: bool,
    eod: dict[str, Any] | None = None,
) -> float:
    name = f"{holding.get('broker_symbol', '')} {holding.get('company_name', '')}".upper()
    if etf_like:
        if any(token in name for token in ("NIFTY", "GOLD", "BEES")):
            return 6.0
        return 3.0
    market_cap_cr = parse_number((eod or {}).get("market_cap_cr"))
    if market_cap_cr is not None:
        if market_cap_cr >= 100000:
            return 7.0
        if market_cap_cr >= 40000:
            return 5.0
        if market_cap_cr >= 10000:
            return 3.0
        return 1.5
    if not instrument:
        return 0.0
    if instrument.get("is_nifty50"):
        return 7.0
    cap = str(instrument.get("market_cap_cat") or "").lower()
    if "large" in cap:
        return 5.0
    if "mid" in cap:
        return 3.0
    if "small" in cap:
        return 1.5
    if "micro" in cap:
        return 1.0
    return 2.0


def classify_sector_context(context: dict[str, Any] | None) -> str:
    if not context:
        return "No local sector context"
    one_month = parse_number(context.get("sector_avg_1m_pct"))
    stage2_count = parse_number(context.get("sector_stage2_count")) or 0.0
    count = parse_number(context.get("sector_stock_count")) or 0.0
    stage2_ratio = stage2_count / count if count else 0.0
    if one_month is not None and one_month >= 5 and stage2_ratio >= 0.25:
        return "Strong/rotating"
    if one_month is not None and one_month >= 0:
        return "Neutral-positive"
    if one_month is not None and one_month <= -5:
        return "Weak"
    return "Neutral"


def recommendation_for(
    holding: dict[str, Any],
    instrument: dict[str, Any] | None,
    stage: dict[str, Any] | None,
    eod: dict[str, Any] | None,
    quarterly: dict[str, Any] | None,
    annual: dict[str, Any] | None,
    sector_context: dict[str, Any] | None,
    broker: dict[str, Any] | None,
    total_market_value: float,
) -> dict[str, Any]:
    etf_like = is_etf_like(holding, instrument)
    weight = parse_number(holding.get("portfolio_weight_pct")) or 0.0
    pnl_pct = parse_number(holding.get("unrealized_pl_pct")) or 0.0
    value_at_market = parse_number(holding.get("value_at_market")) or 0.0
    tech = parse_number((stage or {}).get("technical_score"))
    fund = parse_number((stage or {}).get("enhanced_fund_score")) or parse_number((stage or {}).get("fundamental_score"))
    rsi = parse_number((stage or {}).get("rsi"))
    trade_signal = str((stage or {}).get("trading_signal") or "").upper()
    stage_value = str((stage or {}).get("stage") or "").upper()
    trend_signal = str((stage or {}).get("trend_signal") or "").upper()
    supertrend = str((stage or {}).get("supertrend_state") or "").upper()
    sector_view = classify_sector_context(sector_context)
    q_pat_yoy = pct_change((quarterly or {}).get("q_pat"), (quarterly or {}).get("yoy_q_pat"))
    q_revenue_yoy = pct_change((quarterly or {}).get("q_revenue"), (quarterly or {}).get("yoy_q_revenue"))
    a_pat_yoy = pct_change((annual or {}).get("a_pat"), (annual or {}).get("prev_a_pat"))

    stage2 = "STAGE_2" in stage_value or stage_value == "2"
    stage4 = "STAGE_4" in stage_value or "BEAR" in trend_signal
    buyish = trade_signal in {"BUY", "STRONG_BUY"}
    bearish = trade_signal in {"SELL", "STRONG_SELL", "WEAK_HOLD", "AVOID"} or supertrend == "BEARISH"
    strong_fund = fund is not None and fund >= 65
    weak_fund = fund is not None and fund < 45
    strong_tech = tech is not None and tech >= 65
    overbought = rsi is not None and rsi >= 75
    sector_strong = sector_view in {"Strong/rotating", "Neutral-positive"}

    flags: list[str] = []
    if weight >= 8:
        flags.append("high concentration")
    elif weight >= 5:
        flags.append("large position")
    if pnl_pct <= -25:
        flags.append("deep drawdown")
    elif pnl_pct <= -12:
        flags.append("drawdown")
    if pnl_pct >= 50:
        flags.append("large unrealized gain")
    if overbought:
        flags.append("RSI extended")
    if not instrument and not etf_like:
        flags.append("unresolved/corporate-action review")
    if not stage and not etf_like:
        flags.append("missing latest stage evidence")
    if broker:
        flags.append("local broker facts available")
    else:
        flags.append("no local broker facts")
    small_tail = value_at_market < total_market_value * 0.0025
    no_meaningful_gain = pnl_pct < 10.0
    if small_tail and not buyish:
        flags.append("tail holding")

    short_term = "HOLD"
    medium_term = "HOLD"
    long_term = "HOLD"
    primary_action = "HOLD / REVIEW"
    action_reason: list[str] = []
    add_allowed = False
    exit_candidate = False
    reduce_candidate = False

    if etf_like:
        primary_action = "HOLD / REBALANCE"
        short_term = "HOLD"
        medium_term = "HOLD or trim to asset-allocation cap"
        long_term = "HOLD as portfolio ballast if it matches allocation policy"
        action_reason.append("ETF/index exposure should be sized by asset allocation, not stock thesis")
        if weight > target_weight_cap(instrument, holding, etf_like, eod):
            primary_action = "TRIM TO ETF CAP"
            reduce_candidate = True
            action_reason.append("ETF/sector exposure is above model cap")
    elif not instrument:
        primary_action = "MANUAL REVIEW / NO ADD"
        short_term = "NO ADD"
        medium_term = "RESOLVE SYMBOL OR EXIT"
        long_term = "EXIT unless a current listing and thesis are confirmed"
        action_reason.append("ISIN was not resolved in the current NSE instrument master")
        if pnl_pct < -10:
            primary_action = "EXIT CANDIDATE / RESOLVE FIRST"
            exit_candidate = True
    elif stage4 or (bearish and weak_fund and pnl_pct < 0):
        primary_action = "SELL / REDUCE"
        short_term = "SELL or avoid fresh exposure"
        medium_term = "REDUCE unless trend recovers"
        long_term = "EXIT unless fundamentals and stage recover"
        exit_candidate = True
        action_reason.append("trend/technical evidence is adverse and fundamentals are not strong enough")
    elif pnl_pct <= -25 and not (stage2 and (buyish or strong_tech) and not weak_fund):
        primary_action = "SELL / REDUCE"
        short_term = "SELL into bounce"
        medium_term = "REDUCE"
        long_term = "HOLD only if fresh thesis is written"
        exit_candidate = True
        action_reason.append("deep drawdown without enough current stage evidence")
    elif weight > target_weight_cap(instrument, holding, etf_like, eod) and not (stage2 and strong_tech and strong_fund):
        primary_action = "TRIM TO CAP"
        short_term = "HOLD with trim levels"
        medium_term = "TRIM"
        long_term = "HOLD residual position if thesis remains valid"
        reduce_candidate = True
        action_reason.append("position weight is above model risk cap")
    elif stage2 and buyish and strong_tech and not weak_fund and sector_strong:
        if overbought:
            primary_action = "HOLD / ADD ONLY ON PULLBACK"
            short_term = "HOLD; wait for pullback"
            medium_term = "ADD on controlled pullback"
            long_term = "ACCUMULATE within cap"
            action_reason.append("constructive stage, but RSI is extended")
        else:
            primary_action = "ADD ON PULLBACK"
            short_term = "WATCH for entry"
            medium_term = "ADD within cap"
            long_term = "ACCUMULATE if financial trend persists"
            add_allowed = True
            action_reason.append("stage/technical/fundamental/sector evidence is constructive")
    elif stage2 and (strong_tech or buyish) and not weak_fund:
        primary_action = "HOLD / TRAIL"
        short_term = "HOLD"
        medium_term = "HOLD; add only on confirmed breakout/pullback"
        long_term = "HOLD if fundamentals remain acceptable"
        action_reason.append("stage evidence is constructive but not enough for a fresh add")
    elif weak_fund and not strong_tech:
        primary_action = "REDUCE / NO ADD"
        short_term = "NO ADD"
        medium_term = "REDUCE"
        long_term = "EXIT if financials do not improve"
        reduce_candidate = True
        action_reason.append("weak fundamental score without strong technical support")
    elif sector_view == "Weak" and not strong_tech:
        primary_action = "HOLD / NO ADD"
        short_term = "NO ADD"
        medium_term = "HOLD or reduce"
        long_term = "HOLD only for proven quality"
        action_reason.append("sector context is weak and stock evidence is not strong")
    elif pnl_pct >= 50 and not (stage2 and strong_tech):
        primary_action = "TRIM / PROTECT GAINS"
        short_term = "TRAIL STOP"
        medium_term = "TRIM partial"
        long_term = "HOLD residual if thesis remains"
        reduce_candidate = True
        action_reason.append("large gains without a current add-quality setup")
    else:
        primary_action = "HOLD / NO FRESH ADD"
        short_term = "HOLD"
        medium_term = "HOLD"
        long_term = "HOLD if fundamentals stay stable"
        action_reason.append("evidence is mixed or neutral")

    action_text = primary_action.upper()
    weak_or_no_add_action = any(
        token in action_text
        for token in ("SELL", "REDUCE", "NO ADD", "MANUAL REVIEW", "EXIT CANDIDATE")
    )
    add_quality_exception = stage2 and (buyish or strong_tech) and not weak_fund

    cleanup_priority = "P5 MONITOR"
    cleanup_reason = "No cleanup priority beyond the base portfolio action."
    sell_priority_score = 0
    if "SELL" in action_text or "EXIT" in action_text:
        sell_priority_score += 40
    elif "REDUCE" in action_text:
        sell_priority_score += 30
    elif "NO ADD" in action_text or "MANUAL" in action_text:
        sell_priority_score += 20
    if small_tail:
        sell_priority_score += 25
    if pnl_pct < 0:
        sell_priority_score += 20
    elif pnl_pct < 3:
        sell_priority_score += 15
    elif pnl_pct < 10:
        sell_priority_score += 10
    if not instrument and not etf_like:
        sell_priority_score += 10
    if stage4 or bearish:
        sell_priority_score += 10
    if add_quality_exception:
        sell_priority_score -= 20

    if small_tail and no_meaningful_gain and weak_or_no_add_action and not add_quality_exception:
        cleanup_priority = "P1 TAIL CLEANUP"
        cleanup_reason = "Small portfolio line, no meaningful gain, and no current add-quality setup; remove first to reduce holding count and monitoring load."
        if primary_action in {"HOLD / NO FRESH ADD", "HOLD / NO ADD", "MANUAL REVIEW / NO ADD"}:
            primary_action = "PRIORITY SELL / CLEANUP"
            short_term = "SELL or clean up"
            medium_term = "EXIT unless a fresh thesis is written"
            long_term = "REDEPLOY only into higher-conviction names"
            exit_candidate = True
            action_reason.append("small no-gain tail position should be prioritized for portfolio cleanup")
    elif ("SELL" in action_text or "EXIT" in action_text) and no_meaningful_gain:
        cleanup_priority = "P1 WEAK / NO-GAIN EXIT"
        cleanup_reason = "Weak exit signal with no meaningful cushion from gains."
    elif small_tail and weak_or_no_add_action:
        cleanup_priority = "P2 TAIL REVIEW"
        cleanup_reason = "Small line item with weak/no-add status; keep only if there is a written thesis or tax reason."
    elif "TRIM TO CAP" in action_text:
        cleanup_priority = "P3 CONCENTRATION TRIM"
        cleanup_reason = "Trim for position-size discipline rather than thesis failure."
    elif "TRIM" in action_text:
        cleanup_priority = "P4 PROTECT GAINS"
        cleanup_reason = "Profit-protection trim; lower urgency than small no-gain exits."

    cap = target_weight_cap(instrument, holding, etf_like, eod)
    if exit_candidate:
        target_weight = 0.0
    elif reduce_candidate:
        target_weight = min(weight, cap)
    elif add_allowed:
        target_weight = min(cap, max(weight + 0.50, 0.75))
    else:
        target_weight = min(weight, cap) if cap and weight > cap else weight
    action_value = (target_weight - weight) / 100.0 * total_market_value

    stop_value = None
    if stage and parse_number(stage.get("supertrend_value")):
        stop_value = parse_number(stage.get("supertrend_value"))
    stop_policy = (
        f"Use supertrend/weekly close stop near {stop_value:.2f}" if stop_value else "Use thesis stop plus 7-10% trailing risk guard"
    )
    if exit_candidate:
        stop_policy = "No add; exit/reduce on failed bounce or fresh low"

    if q_pat_yoy is not None and q_pat_yoy < -20:
        flags.append("latest quarter PAT YoY weak")
    if q_revenue_yoy is not None and q_revenue_yoy < -10:
        flags.append("latest quarter revenue YoY weak")
    if a_pat_yoy is not None and a_pat_yoy < -20:
        flags.append("latest annual PAT weak")

    return {
        "primary_action": primary_action,
        "short_term_view": short_term,
        "medium_term_view": medium_term,
        "long_term_view": long_term,
        "action_reason": "; ".join(action_reason),
        "risk_flags": "; ".join(dict.fromkeys(flags)),
        "cleanup_priority": cleanup_priority,
        "cleanup_reason": cleanup_reason,
        "sell_priority_score": sell_priority_score,
        "target_weight_cap_pct": cap,
        "model_target_weight_pct": target_weight,
        "model_action_value_rs": action_value,
        "stop_policy": stop_policy,
        "sector_view": sector_view,
        "quarter_revenue_yoy_pct": q_revenue_yoy,
        "quarter_pat_yoy_pct": q_pat_yoy,
        "annual_pat_yoy_pct": a_pat_yoy,
    }


def enrich_holdings(holdings: list[dict[str, Any]], evidence: dict[str, Any], sector_rotation: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    master_cache = load_master_cache(MASTER_CACHE)
    index_memberships = load_index_memberships(INDEX_STOCK_MAPPING)
    total_market_value = sum(parse_number(h.get("value_at_market")) or 0.0 for h in holdings)
    enriched: list[dict[str, Any]] = []

    for holding in holdings:
        instrument = evidence.get("instruments_by_isin", {}).get(holding["isin"])
        if not instrument:
            instrument = evidence.get("instruments_by_symbol", {}).get(holding["broker_symbol"])
        if not instrument and holding["isin"] in master_cache:
            meta = master_cache[holding["isin"]]
            instrument = {
                "symbol": meta.get("symbol"),
                "isin": holding["isin"],
                "company_name": holding["company_name"],
                "sector": meta.get("sector") or meta.get("macro"),
                "industry": meta.get("industry") or meta.get("basic_industry"),
                "market_cap_cat": None,
                "is_etf": False,
                "is_fno": False,
                "is_nifty50": False,
                "is_nifty500": False,
                "status": meta.get("status"),
                "resolution_source": "master_cache",
            }
        if instrument:
            instrument = dict(instrument)

        symbol = str((instrument or {}).get("symbol") or holding.get("broker_symbol") or "").upper()
        stage = evidence.get("stages", {}).get(symbol)
        memberships = index_memberships.get(symbol, set())
        if instrument and memberships:
            instrument["index_memberships"] = ", ".join(sorted(memberships))
            instrument["is_nifty50"] = "NIFTY 50" in memberships
            instrument["is_nifty500"] = "NIFTY 500" in memberships or bool(instrument.get("is_nifty500"))
            if "NIFTY 50" in memberships or "NIFTY NEXT 50" in memberships or "NIFTY 100" in memberships:
                instrument["market_cap_cat"] = "LARGE_CAP"
            elif "NIFTY MIDCAP 50" in memberships or "NIFTY MIDCAP 100" in memberships or "NIFTY MIDCAP 150" in memberships:
                instrument["market_cap_cat"] = "MID_CAP"
            elif "NIFTY SMALLCAP 50" in memberships or "NIFTY SMALLCAP 100" in memberships or "NIFTY SMALLCAP 250" in memberships:
                instrument["market_cap_cat"] = "SMALL_CAP"
        if instrument and not instrument.get("market_cap_cat") and stage and stage.get("market_cap_cat"):
            instrument["market_cap_cat"] = stage.get("market_cap_cat")
        eod = evidence.get("eod", {}).get(symbol)
        quarterly = evidence.get("quarterly", {}).get(symbol)
        annual = evidence.get("annual", {}).get(symbol)
        balance_sheet = evidence.get("balance_sheet", {}).get(symbol)
        cash_flow = evidence.get("cash_flow", {}).get(symbol)
        broker = evidence.get("broker", {}).get(symbol)
        sector = (instrument or {}).get("sector")
        industry = (instrument or {}).get("industry")
        stage_sector = (stage or {}).get("sector")
        sector_for_context = stage_sector or sector
        sector_context = evidence.get("sector_context", {}).get(str(sector_for_context or "").upper())
        sector_lens = sector_lens_for(stage_sector or sector, industry)
        sector_rotation_row = sector_rotation.get(sector_lens.lower(), {})
        etf_like = is_etf_like(holding, instrument)
        public = public_overlay(symbol if symbol else holding.get("broker_symbol", ""), holding.get("company_name", ""))
        recommendation = recommendation_for(
            holding,
            instrument,
            stage,
            eod,
            quarterly,
            annual,
            sector_context,
            broker,
            total_market_value,
        )

        row = {
            **holding,
            "nse_symbol": symbol if instrument else "",
            "resolution_source": (instrument or {}).get("resolution_source") or ("ref.instruments" if instrument else "unresolved"),
            "nse_company_name": (instrument or {}).get("company_name"),
            "sector": sector,
            "stage_sector": stage_sector,
            "industry": industry,
            "sector_lens": sector_lens,
            "sector_rotation_rank": sector_rotation_row.get("rank"),
            "sector_rotation_score": sector_rotation_row.get("score"),
            "sector_rotation_1m": sector_rotation_row.get("one_month"),
            "market_cap_bucket": market_cap_bucket(instrument, holding, etf_like, eod),
            "index_memberships": (instrument or {}).get("index_memberships"),
            "is_etf_like": etf_like,
            "is_fno": (instrument or {}).get("is_fno"),
            "is_nifty50": (instrument or {}).get("is_nifty50"),
            "is_nifty500": (instrument or {}).get("is_nifty500"),
            "listing_status": (instrument or {}).get("status"),
            "eod_trade_date": (eod or {}).get("trade_date"),
            "eod_close": (eod or {}).get("close"),
            "eod_change_pct": (eod or {}).get("change_pct"),
            "week52_high": (eod or {}).get("week52_high"),
            "week52_low": (eod or {}).get("week52_low"),
            "market_cap_cr": (eod or {}).get("market_cap_cr"),
            "stage": (stage or {}).get("stage"),
            "trend_signal": (stage or {}).get("trend_signal"),
            "trading_signal": (stage or {}).get("trading_signal"),
            "stage_score": (stage or {}).get("stage_score"),
            "technical_score": (stage or {}).get("technical_score"),
            "rsi": (stage or {}).get("rsi"),
            "relative_strength": (stage or {}).get("relative_strength"),
            "supertrend_state": (stage or {}).get("supertrend_state"),
            "supertrend_value": (stage or {}).get("supertrend_value"),
            "investment_score": (stage or {}).get("investment_score"),
            "fundamental_score": (stage or {}).get("fundamental_score"),
            "enhanced_fund_score": (stage or {}).get("enhanced_fund_score"),
            "earnings_quality": (stage or {}).get("earnings_quality"),
            "sales_growth": (stage or {}).get("sales_growth"),
            "financial_strength": (stage or {}).get("financial_strength"),
            "institutional_backing": (stage or {}).get("institutional_backing"),
            "q_period": (quarterly or {}).get("q_period"),
            "q_revenue": (quarterly or {}).get("q_revenue"),
            "q_pat": (quarterly or {}).get("q_pat"),
            "q_opm_pct": (quarterly or {}).get("q_opm_pct"),
            "a_period": (annual or {}).get("a_period"),
            "a_revenue": (annual or {}).get("a_revenue"),
            "a_pat": (annual or {}).get("a_pat"),
            "a_opm_pct": (annual or {}).get("a_opm_pct"),
            "borrowings": (balance_sheet or {}).get("borrowings"),
            "net_debt": (balance_sheet or {}).get("net_debt"),
            "operating_cf": (cash_flow or {}).get("operating_cf"),
            "broker_fact_count": (broker or {}).get("broker_fact_count", 0),
            "broker_sources": (broker or {}).get("broker_sources") or "",
            "broker_titles": (broker or {}).get("broker_titles") or "",
            "broker_fact_summary": (broker or {}).get("broker_fact_summary") or "",
            "sector_stock_count": (sector_context or {}).get("sector_stock_count"),
            "sector_avg_1m_pct": (sector_context or {}).get("sector_avg_1m_pct"),
            "sector_avg_rs": (sector_context or {}).get("sector_avg_rs"),
            "sector_buy_count": (sector_context or {}).get("sector_buy_count"),
            "sector_stage2_count": (sector_context or {}).get("sector_stage2_count"),
            **public,
            **recommendation,
        }
        enriched.append(row)
    enriched.sort(key=lambda item: parse_number(item.get("value_at_market")) or 0.0, reverse=True)
    return clean_json(enriched)


CSV_COLUMNS = [
    "broker_symbol",
    "nse_symbol",
    "company_name",
    "isin",
    "quantity",
    "average_cost_price",
    "current_market_price",
    "value_at_cost",
    "value_at_market",
    "portfolio_weight_pct",
    "unrealized_pl",
    "unrealized_pl_pct",
    "primary_action",
    "short_term_view",
    "medium_term_view",
    "long_term_view",
    "model_target_weight_pct",
    "model_action_value_rs",
    "target_weight_cap_pct",
    "risk_flags",
    "cleanup_priority",
    "cleanup_reason",
    "sell_priority_score",
    "action_reason",
    "stop_policy",
    "sector",
    "stage_sector",
    "industry",
    "sector_lens",
    "sector_view",
    "sector_rotation_rank",
    "sector_rotation_score",
    "market_cap_bucket",
    "index_memberships",
    "is_etf_like",
    "stage",
    "trend_signal",
    "trading_signal",
    "technical_score",
    "rsi",
    "relative_strength",
    "supertrend_state",
    "investment_score",
    "enhanced_fund_score",
    "fundamental_score",
    "earnings_quality",
    "sales_growth",
    "financial_strength",
    "q_period",
    "q_revenue",
    "q_pat",
    "q_opm_pct",
    "quarter_revenue_yoy_pct",
    "quarter_pat_yoy_pct",
    "a_period",
    "a_revenue",
    "a_pat",
    "a_opm_pct",
    "annual_pat_yoy_pct",
    "borrowings",
    "net_debt",
    "operating_cf",
    "broker_fact_count",
    "broker_sources",
    "broker_titles",
    "broker_fact_summary",
    "public_research_status",
    "public_broker_view",
    "public_research_summary",
    "public_research_confidence",
    "public_source_trail",
    "resolution_source",
    "listing_status",
    "eod_trade_date",
    "eod_close",
    "eod_change_pct",
    "week52_high",
    "week52_low",
    "market_cap_cr",
]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def action_groups(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups = {
        "sell_reduce": [],
        "add": [],
        "hold_core": [],
        "manual_review": [],
        "tail_cleanup": [],
    }
    for row in rows:
        action = str(row.get("primary_action") or "").upper()
        flags = str(row.get("risk_flags") or "").lower()
        if "SELL" in action or "REDUCE" in action or "TRIM" in action:
            groups["sell_reduce"].append(row)
        if action.startswith("ADD") or "ADD ONLY ON PULLBACK" in action:
            groups["add"].append(row)
        if "HOLD" in action and parse_number(row.get("portfolio_weight_pct")) and parse_number(row.get("portfolio_weight_pct")) >= 1:
            groups["hold_core"].append(row)
        if "MANUAL" in action or "unresolved" in flags:
            groups["manual_review"].append(row)
        if "tail holding" in flags:
            groups["tail_cleanup"].append(row)
    priority_order = {
        "P1 TAIL CLEANUP": 1,
        "P1 WEAK / NO-GAIN EXIT": 2,
        "P2 TAIL REVIEW": 3,
        "P3 CONCENTRATION TRIM": 4,
        "P4 PROTECT GAINS": 5,
        "P5 MONITOR": 6,
    }

    def priority_key(row: dict[str, Any]) -> tuple[int, float, float]:
        priority = priority_order.get(str(row.get("cleanup_priority") or ""), 99)
        score = parse_number(row.get("sell_priority_score")) or 0.0
        value = parse_number(row.get("value_at_market")) or 0.0
        return (priority, -score, value)

    for group_name in ("sell_reduce", "manual_review", "tail_cleanup"):
        groups[group_name].sort(key=priority_key)
    return groups


def top_table(rows: list[dict[str, Any]], columns: list[str], limit: int = 20) -> str:
    lines = []
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("|" + "|".join("---" for _ in columns) + "|")
    for row in rows[:limit]:
        values = []
        for col in columns:
            value = row.get(col)
            if col.endswith("_pct") or col in {"portfolio_weight_pct", "model_target_weight_pct"}:
                value = fmt_pct(value, 2)
            elif col in {"value_at_market", "unrealized_pl", "model_action_value_rs"}:
                value = fmt_inr(value)
            elif isinstance(value, float):
                value = f"{value:.2f}"
            elif value is None:
                value = "-"
            values.append(str(value).replace("|", "/"))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def build_summary(enriched: list[dict[str, Any]], evidence: dict[str, Any], source_path: Path) -> dict[str, Any]:
    total_market_value = sum(parse_number(row.get("value_at_market")) or 0.0 for row in enriched)
    total_cost = sum(parse_number(row.get("value_at_cost")) or 0.0 for row in enriched)
    total_unrealized = sum(parse_number(row.get("unrealized_pl")) or 0.0 for row in enriched)
    action_counts = Counter(row.get("primary_action") for row in enriched)
    cleanup_counts = Counter(row.get("cleanup_priority") for row in enriched)
    stage_counts = Counter(str(row.get("trend_signal") or row.get("stage") or "Missing") for row in enriched)
    public_counts = Counter(str(row.get("public_research_status") or "missing") for row in enriched)
    sector_weights: defaultdict[str, float] = defaultdict(float)
    for row in enriched:
        sector_weights[str(row.get("sector_lens") or row.get("sector") or "Unclassified")] += parse_number(row.get("portfolio_weight_pct")) or 0.0
    top_sectors = sorted(sector_weights.items(), key=lambda item: item[1], reverse=True)
    resolved_count = sum(1 for row in enriched if row.get("nse_symbol"))
    broker_covered_count = sum(1 for row in enriched if parse_number(row.get("broker_fact_count")) and parse_number(row.get("broker_fact_count")) > 0)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_file": str(source_path),
        "local_stage_snapshot_date": clean_json(evidence.get("snapshot_date")),
        "local_eod_date": clean_json(evidence.get("latest_eod_date")),
        "holding_count": len(enriched),
        "resolved_count": resolved_count,
        "unresolved_count": len(enriched) - resolved_count,
        "broker_covered_count": broker_covered_count,
        "total_cost": total_cost,
        "total_market_value": total_market_value,
        "total_unrealized": total_unrealized,
        "total_unrealized_pct": (total_unrealized / total_cost * 100.0) if total_cost else None,
        "top_10_weight_pct": sum(parse_number(row.get("portfolio_weight_pct")) or 0.0 for row in enriched[:10]),
        "action_counts": dict(action_counts),
        "cleanup_counts": dict(cleanup_counts),
        "stage_counts": dict(stage_counts),
        "public_research_counts": dict(public_counts),
        "top_sector_weights": top_sectors[:12],
        "market_context": read_market_context(SECTOR_ROTATION_REPORT),
    }


def write_markdown(path: Path, enriched: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    groups = action_groups(enriched)
    lines: list[str] = []
    lines.append("# Equity Portfolio Assessment")
    lines.append("")
    lines.append(f"Generated: {summary['generated_at']}")
    lines.append(f"Source file: `{summary['source_file']}`")
    lines.append(f"Local stage snapshot: `{summary['local_stage_snapshot_date']}`")
    lines.append(f"Local EOD price date: `{summary['local_eod_date']}`")
    lines.append("")
    lines.append("> Research-only portfolio assessment. This is not investment advice, not a SEBI-registered recommendation, and not an order list. Validate price, liquidity, tax, corporate action, and personal constraints before acting.")
    lines.append("")
    lines.append("## Portfolio Snapshot")
    lines.append("")
    lines.append(f"- Holdings: {summary['holding_count']} ({summary['resolved_count']} resolved, {summary['unresolved_count']} unresolved/legacy/ETF gaps)")
    lines.append(f"- Market value: {fmt_inr(summary['total_market_value'])}")
    lines.append(f"- Cost value: {fmt_inr(summary['total_cost'])}")
    lines.append(f"- Unrealized P/L: {fmt_inr(summary['total_unrealized'])} ({fmt_pct(summary['total_unrealized_pct'], 2)})")
    lines.append(f"- Top 10 weight: {fmt_pct(summary['top_10_weight_pct'], 2)}")
    lines.append(f"- Cleanup priority: {summary.get('cleanup_counts', {})}")
    lines.append(f"- Local broker evidence coverage: {summary['broker_covered_count']} holdings")
    lines.append(f"- Public overlay coverage: {summary.get('public_research_counts', {})}")
    lines.append("")
    lines.append("## Market Context")
    lines.append("")
    lines.append(summary["market_context"])
    lines.append("")
    lines.append("## Action Counts")
    lines.append("")
    for action, count in sorted(summary["action_counts"].items(), key=lambda item: (-item[1], str(item[0]))):
        lines.append(f"- {action}: {count}")
    lines.append("")
    lines.append("## Top Sector Weights")
    lines.append("")
    for sector, weight in summary["top_sector_weights"]:
        lines.append(f"- {sector}: {weight:.2f}%")
    lines.append("")
    lines.append("## Immediate Sell / Reduce / Trim Queue")
    lines.append("")
    lines.append(top_table(groups["sell_reduce"], ["cleanup_priority", "broker_symbol", "nse_symbol", "company_name", "value_at_market", "portfolio_weight_pct", "unrealized_pl_pct", "primary_action", "risk_flags", "action_reason"], 60))
    lines.append("")
    lines.append("## Tail Cleanup First")
    lines.append("")
    lines.append(top_table(groups["tail_cleanup"], ["cleanup_priority", "broker_symbol", "nse_symbol", "company_name", "value_at_market", "portfolio_weight_pct", "unrealized_pl_pct", "primary_action", "cleanup_reason"], 80))
    lines.append("")
    lines.append("## Add / Accumulate Queue")
    lines.append("")
    lines.append(top_table(groups["add"], ["broker_symbol", "nse_symbol", "company_name", "value_at_market", "portfolio_weight_pct", "primary_action", "technical_score", "enhanced_fund_score", "sector_view", "model_action_value_rs"], 40))
    lines.append("")
    lines.append("## Core Holds Above 1% Weight")
    lines.append("")
    lines.append(top_table(groups["hold_core"], ["broker_symbol", "nse_symbol", "company_name", "value_at_market", "portfolio_weight_pct", "unrealized_pl_pct", "primary_action", "short_term_view", "medium_term_view", "long_term_view"], 40))
    lines.append("")
    lines.append("## Manual Review / Resolution Queue")
    lines.append("")
    lines.append(top_table(groups["manual_review"], ["broker_symbol", "nse_symbol", "company_name", "isin", "value_at_market", "portfolio_weight_pct", "primary_action", "risk_flags"], 60))
    lines.append("")
    lines.append("## Full Portfolio Evidence Table")
    lines.append("")
    lines.append(top_table(enriched, ["broker_symbol", "nse_symbol", "company_name", "value_at_market", "portfolio_weight_pct", "unrealized_pl_pct", "primary_action", "trend_signal", "trading_signal", "technical_score", "enhanced_fund_score", "sector_view", "risk_flags"], len(enriched)))
    lines.append("")
    lines.append("## Method")
    lines.append("")
    lines.append("- Resolution: ISIN/symbol matched against `ref.instruments`, with `data/_nse_master_cache/quote_equity_meta.json` as a fallback.")
    lines.append("- Technical/stage: latest `scores.stage_snapshots` snapshot, including stage, trading signal, RSI, relative strength, and supertrend.")
    lines.append("- Financials: latest quarterly/annual `scores.*` financial tables, including YoY revenue/PAT where available.")
    lines.append("- Sector view: current local sector context from latest stage snapshot plus `reports/latest/sector_rotation.md` lens mapping.")
    lines.append("- Broker view: only stored `company_intel.broker_research_facts` are used in the local table; missing broker facts are explicitly marked.")
    lines.append("- Public overlay: source links are generated for all resolved symbols; cached public research notes are included only where a public source was checked in this run.")
    lines.append("- Sizing: model caps are risk-governance caps, not order instructions. They cap high concentration and suggest add capacity only when evidence is constructive.")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_html(path: Path, markdown_path: Path, csv_path: Path, summary: dict[str, Any], enriched: list[dict[str, Any]]) -> None:
    payload = {
        "summary": clean_json(summary),
        "holdings": clean_json(enriched),
        "files": {"markdown": markdown_path.name, "csv": csv_path.name},
    }
    payload_json = json.dumps(payload, ensure_ascii=True, default=str)
    payload_json = payload_json.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    doc = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Portfolio Intelligence Dashboard</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #16222a;
      --muted: #5b6b75;
      --line: #d8e0e5;
      --band: #f5f8fa;
      --band-2: #edf3f5;
      --accent: #176b87;
      --ok: #23745b;
      --warn: #9a5a16;
      --risk: #a63838;
      --neutral: #607080;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: #ffffff;
    }
    header {
      padding: 22px 28px 16px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfd;
    }
    main {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 420px;
      gap: 18px;
      padding: 18px 28px 36px;
    }
    h1 { margin: 0 0 6px; font-size: 27px; letter-spacing: 0; }
    h2 { margin: 24px 0 10px; font-size: 18px; letter-spacing: 0; }
    h3 { margin: 0 0 8px; font-size: 14px; letter-spacing: 0; }
    p, li { color: var(--muted); line-height: 1.45; }
    button, input, select { font: inherit; }
    button { cursor: pointer; }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .meta, .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
    .pill, .chip {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 6px 10px;
      background: #fff;
      font-size: 12px;
      color: var(--muted);
    }
    .chip.is-active { border-color: var(--accent); color: var(--accent); background: #edf7fa; }
    .notice { border-left: 4px solid var(--warn); padding: 10px 12px; background: #fff8ef; color: #4d3829; margin: 0 0 14px; }
    .toolbar {
      position: sticky;
      top: 0;
      z-index: 5;
      display: grid;
      grid-template-columns: minmax(220px, 2fr) repeat(4, minmax(130px, 1fr)) auto auto;
      gap: 8px;
      padding: 10px;
      margin: 0 0 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.96);
    }
    .toolbar input, .toolbar select {
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 8px 9px;
      background: #fff;
      color: var(--ink);
    }
    .toolbar button {
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 8px 10px;
      background: var(--band);
      color: var(--ink);
      white-space: nowrap;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
      margin: 14px 0;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: var(--band);
    }
    .metric span { display: block; color: var(--muted); font-size: 12px; }
    .metric strong { display: block; margin-top: 4px; font-size: 20px; }
    .viz-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 12px;
    }
    .panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fff;
    }
    .heat {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(128px, 1fr));
      gap: 8px;
    }
    .tile {
      min-height: 82px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: var(--tile-bg, var(--band));
      color: var(--ink);
      text-align: left;
    }
    .tile strong { display: block; font-size: 15px; overflow-wrap: anywhere; }
    .tile span { display: block; margin-top: 4px; font-size: 12px; color: var(--muted); }
    .tile[data-active="true"] { outline: 2px solid var(--accent); outline-offset: 1px; }
    .matrix {
      display: grid;
      grid-template-columns: repeat(4, minmax(90px, 1fr));
      gap: 7px;
    }
    .matrix .axis { display: flex; align-items: center; justify-content: center; min-height: 56px; color: var(--muted); font-size: 12px; }
    .table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; min-width: 1120px; }
    th, td { padding: 8px 9px; border-bottom: 1px solid #e8eef1; text-align: left; vertical-align: top; }
    th { background: #eef4f6; color: #22313a; position: sticky; top: 0; z-index: 1; white-space: nowrap; }
    th[data-sort] { cursor: pointer; }
    tbody tr { cursor: pointer; }
    tbody tr:hover td { background: #f0f6f8; }
    .badge {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 3px 7px;
      font-size: 11px;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--neutral);
      white-space: nowrap;
    }
    .badge.risk { color: var(--risk); border-color: #e5bcbc; background: #fff2f2; }
    .badge.warn { color: var(--warn); border-color: #efd6b8; background: #fff8ef; }
    .badge.ok { color: var(--ok); border-color: #bddfcf; background: #effaf5; }
    .detail {
      position: sticky;
      top: 12px;
      align-self: start;
      max-height: calc(100vh - 24px);
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }
    .detail-head { padding: 14px; border-bottom: 1px solid var(--line); background: var(--band); }
    .detail-head h2 { margin: 0 0 6px; }
    .detail-body { padding: 14px; }
    .detail-section { border: 1px solid var(--line); border-radius: 8px; padding: 10px; margin: 0 0 10px; }
    .kv {
      display: grid;
      grid-template-columns: 150px minmax(0, 1fr);
      gap: 6px 10px;
      font-size: 13px;
    }
    .kv span:nth-child(odd) { color: var(--muted); }
    .links { display: flex; flex-wrap: wrap; gap: 7px; }
    .links a {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 5px 8px;
      background: #fff;
      font-size: 12px;
    }
    .empty { color: var(--muted); padding: 24px; text-align: center; }
    @media (max-width: 1180px) {
      main { grid-template-columns: 1fr; }
      .detail { position: static; max-height: none; }
      .toolbar { grid-template-columns: 1fr 1fr; }
    }
    @media (max-width: 720px) {
      header, main { padding-left: 14px; padding-right: 14px; }
      .toolbar, .viz-grid { grid-template-columns: 1fr; }
      .matrix { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
      .kv { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Portfolio Intelligence Dashboard</h1>
    <p>Standalone research dashboard from local portfolio holdings, Agent Adda technical/fundamental evidence, sector context, and public-source overlays.</p>
    <div class="meta">
      <span class="pill" id="generatedPill"></span>
      <span class="pill" id="snapshotPill"></span>
      <span class="pill" id="holdingPill"></span>
      <span class="pill">Research only / no order list</span>
    </div>
  </header>
  <main>
    <section>
      <p class="notice">Not investment advice. Validate current prices, filings, broker suitability, tax, liquidity, corporate actions, and risk tolerance before acting.</p>
      <div class="toolbar">
        <input id="searchBox" type="search" placeholder="Search symbol, company, sector, action">
        <select id="actionFilter"><option value="">All actions</option></select>
        <select id="cleanupFilter"><option value="">All cleanup priorities</option></select>
        <select id="sectorFilter"><option value="">All sectors</option></select>
        <select id="stageFilter"><option value="">All stages</option></select>
        <select id="publicFilter"><option value="">All public overlay</option></select>
        <button id="clearFilters" type="button">Clear</button>
        <button id="exportCsv" type="button">Export View</button>
      </div>
      <div class="chips">
        <button class="chip" id="sellChip" type="button">Sell / Reduce</button>
        <button class="chip" id="tailCleanupChip" type="button">Tail Cleanup</button>
        <button class="chip" id="addChip" type="button">Add Candidates</button>
        <button class="chip" id="stage2Chip" type="button">Stage 2</button>
        <button class="chip" id="highWeightChip" type="button">High Weight</button>
        <button class="chip" id="gapsChip" type="button">Evidence Gaps</button>
      </div>
      <section class="grid" id="metricsGrid"></section>
      <section class="panel">
        <h2>Market Context</h2>
        <p id="marketContext"></p>
        <p class="links"><a id="markdownLink">Markdown report</a><a id="csvLink">Full CSV evidence table</a></p>
      </section>
      <section class="viz-grid">
        <div class="panel"><h2>Action Heat Map</h2><div class="heat" id="actionHeat"></div></div>
        <div class="panel"><h2>Cleanup Priority</h2><div class="heat" id="priorityHeat"></div></div>
        <div class="panel"><h2>Sector Weight Heat Map</h2><div class="heat" id="sectorHeat"></div></div>
        <div class="panel"><h2>P/L Heat Map</h2><div class="heat" id="plHeat"></div></div>
        <div class="panel"><h2>Technical vs Fundamental</h2><div class="matrix" id="matrixHeat"></div></div>
      </section>
      <section>
        <h2>Filtered Evidence Table <span class="pill" id="rowCount"></span></h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th data-sort="nse_symbol">Symbol</th>
                <th data-sort="company_name">Company</th>
                <th data-sort="value_at_market">Value</th>
                <th data-sort="portfolio_weight_pct">Weight</th>
                <th data-sort="unrealized_pl_pct">P/L</th>
                <th data-sort="primary_action">Action</th>
                <th data-sort="cleanup_priority">Priority</th>
                <th data-sort="stage">Stage</th>
                <th data-sort="trading_signal">Signal</th>
                <th data-sort="technical_score">Tech</th>
                <th data-sort="enhanced_fund_score">Fund</th>
                <th data-sort="quarter_pat_yoy_pct">Q PAT YoY</th>
                <th data-sort="sector_lens">Sector</th>
                <th data-sort="public_research_status">Public</th>
              </tr>
            </thead>
            <tbody id="evidenceRows"></tbody>
          </table>
        </div>
      </section>
    </section>
    <aside class="detail" id="detailPane">
      <div class="detail-head">
        <h2>Stock Narrative</h2>
        <p>Select a row or heat-map tile to inspect decision evidence, technicals, fundamentals, public sources, and sizing.</p>
      </div>
      <div class="detail-body" id="detailBody"></div>
    </aside>
  </main>
  <script type="application/json" id="portfolio-data">__DATA_JSON__</script>
  <script>
    const payload = JSON.parse(document.getElementById('portfolio-data').textContent);
    const rows = payload.holdings || [];
    const summary = payload.summary || {};
    const state = { search: '', action: '', cleanupPriority: '', sector: '', stage: '', publicStatus: '', quick: null, sort: 'sell_priority_score', dir: -1 };
    let currentRows = rows.slice();

    const visibleColumns = [
      'broker_symbol','nse_symbol','company_name','isin','value_at_market','portfolio_weight_pct','unrealized_pl_pct','primary_action',
      'cleanup_priority','cleanup_reason','sell_priority_score',
      'short_term_view','medium_term_view','long_term_view','stage','trend_signal','trading_signal','technical_score','rsi',
      'relative_strength','supertrend_state','enhanced_fund_score','fundamental_score','q_period','q_revenue','q_pat',
      'quarter_revenue_yoy_pct','quarter_pat_yoy_pct','a_period','a_revenue','a_pat','a_opm_pct','net_debt','operating_cf',
      'sector_lens','sector_view','market_cap_bucket','risk_flags','action_reason','stop_policy','public_research_status',
      'public_broker_view','public_research_summary','public_source_trail'
    ];

    function num(value) {
      if (value === null || value === undefined || value === '') return null;
      const n = Number(String(value).replace(/[% ,]/g, ''));
      return Number.isFinite(n) ? n : null;
    }
    function esc(value) {
      return String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    }
    function fmtInr(value) {
      const n = num(value);
      if (n === null) return '-';
      return 'Rs. ' + Math.round(n).toLocaleString('en-IN');
    }
    function fmtPct(value, digits = 1) {
      const n = num(value);
      if (n === null) return '-';
      return n.toFixed(digits) + '%';
    }
    function fmtNum(value, digits = 1) {
      const n = num(value);
      if (n === null) return '-';
      return n.toFixed(digits);
    }
    function actionTone(action) {
      const text = String(action || '').toUpperCase();
      if (text.includes('SELL') || text.includes('REDUCE')) return 'risk';
      if (text.includes('TRIM') || text.includes('NO ADD') || text.includes('REBALANCE')) return 'warn';
      if (text.includes('ADD') || text.includes('TRAIL')) return 'ok';
      return '';
    }
    function priorityTone(priority) {
      const text = String(priority || '').toUpperCase();
      if (text.startsWith('P1')) return 'risk';
      if (text.startsWith('P2') || text.startsWith('P3') || text.startsWith('P4')) return 'warn';
      return '';
    }
    function scoreBand(value) {
      const n = num(value);
      if (n === null) return 'Missing';
      if (n >= 70) return 'High';
      if (n >= 50) return 'Medium';
      return 'Low';
    }
    function pnlBucket(row) {
      const v = num(row.unrealized_pl_pct);
      if (v === null) return 'Missing';
      if (v <= -25) return 'Deep loss';
      if (v < 0) return 'Loss';
      if (v < 10) return 'Flat';
      if (v < 50) return 'Gain';
      return 'Big gain';
    }
    function matrixKey(row) {
      return scoreBand(row.technical_score) + ' tech / ' + scoreBand(row.enhanced_fund_score || row.fundamental_score) + ' fund';
    }
    function isGap(row) {
      return !row.nse_symbol || !row.stage || String(row.risk_flags || '').toLowerCase().includes('missing') || row.public_research_status === 'link_only';
    }
    function isHighWeight(row) {
      return (num(row.portfolio_weight_pct) || 0) >= 1;
    }
    function isSellReduce(row) {
      const action = String(row.primary_action || '').toUpperCase();
      return action.includes('SELL') || action.includes('REDUCE') || action.includes('TRIM');
    }
    function isAdd(row) {
      const action = String(row.primary_action || '').toUpperCase();
      return action.startsWith('ADD') || action.includes('ADD ONLY');
    }
    function isTailCleanup(row) {
      return String(row.cleanup_priority || '').toUpperCase().startsWith('P1 TAIL');
    }

    function populateSelect(id, values) {
      const select = document.getElementById(id);
      for (const value of values) {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
      }
    }
    function initFilters() {
      populateSelect('actionFilter', [...new Set(rows.map(r => r.primary_action).filter(Boolean))].sort());
      populateSelect('cleanupFilter', [...new Set(rows.map(r => r.cleanup_priority).filter(Boolean))].sort());
      populateSelect('sectorFilter', [...new Set(rows.map(r => r.sector_lens || r.sector || 'Unclassified'))].sort());
      populateSelect('stageFilter', [...new Set(rows.map(r => r.stage || 'Missing'))].sort());
      populateSelect('publicFilter', [...new Set(rows.map(r => r.public_research_status || 'missing'))].sort());
      document.getElementById('searchBox').addEventListener('input', (event) => { state.search = event.target.value.toLowerCase(); applyFilters(); });
      document.getElementById('actionFilter').addEventListener('change', (event) => { state.action = event.target.value; applyFilters(); });
      document.getElementById('cleanupFilter').addEventListener('change', (event) => { state.cleanupPriority = event.target.value; applyFilters(); });
      document.getElementById('sectorFilter').addEventListener('change', (event) => { state.sector = event.target.value; applyFilters(); });
      document.getElementById('stageFilter').addEventListener('change', (event) => { state.stage = event.target.value; applyFilters(); });
      document.getElementById('publicFilter').addEventListener('change', (event) => { state.publicStatus = event.target.value; applyFilters(); });
      document.getElementById('clearFilters').addEventListener('click', clearFilters);
      document.getElementById('exportCsv').addEventListener('click', exportFilteredCsv);
      document.getElementById('sellChip').addEventListener('click', () => setQuick('sell'));
      document.getElementById('tailCleanupChip').addEventListener('click', () => setQuick('tailCleanup'));
      document.getElementById('addChip').addEventListener('click', () => setQuick('add'));
      document.getElementById('stage2Chip').addEventListener('click', () => setQuick('stage2'));
      document.getElementById('highWeightChip').addEventListener('click', () => setQuick('highWeight'));
      document.getElementById('gapsChip').addEventListener('click', () => setQuick('gaps'));
      document.querySelectorAll('th[data-sort]').forEach(th => th.addEventListener('click', () => {
        const key = th.dataset.sort;
        if (state.sort === key) state.dir *= -1;
        else { state.sort = key; state.dir = key.includes('value') || key.includes('pct') || key.includes('score') ? -1 : 1; }
        applyFilters();
      }));
    }
    function setQuick(type, value = null) {
      state.quick = state.quick && state.quick.type === type && state.quick.value === value ? null : { type, value };
      document.querySelectorAll('.chip').forEach(button => button.classList.remove('is-active'));
      if (state.quick) {
        const map = { sell: 'sellChip', tailCleanup: 'tailCleanupChip', add: 'addChip', stage2: 'stage2Chip', highWeight: 'highWeightChip', gaps: 'gapsChip' };
        if (map[type]) document.getElementById(map[type]).classList.add('is-active');
      }
      applyFilters();
    }
    function clearFilters() {
      state.search = ''; state.action = ''; state.cleanupPriority = ''; state.sector = ''; state.stage = ''; state.publicStatus = ''; state.quick = null;
      document.getElementById('searchBox').value = '';
      ['actionFilter','cleanupFilter','sectorFilter','stageFilter','publicFilter'].forEach(id => document.getElementById(id).value = '');
      document.querySelectorAll('.chip').forEach(button => button.classList.remove('is-active'));
      applyFilters();
    }
    function passes(row) {
      const haystack = [row.broker_symbol,row.nse_symbol,row.company_name,row.sector_lens,row.primary_action,row.cleanup_priority,row.cleanup_reason,row.risk_flags,row.public_research_summary].join(' ').toLowerCase();
      if (state.search && !haystack.includes(state.search)) return false;
      if (state.action && row.primary_action !== state.action) return false;
      if (state.cleanupPriority && row.cleanup_priority !== state.cleanupPriority) return false;
      if (state.sector && (row.sector_lens || row.sector || 'Unclassified') !== state.sector) return false;
      if (state.stage && (row.stage || 'Missing') !== state.stage) return false;
      if (state.publicStatus && (row.public_research_status || 'missing') !== state.publicStatus) return false;
      if (state.quick) {
        if (state.quick.type === 'sell' && !isSellReduce(row)) return false;
        if (state.quick.type === 'tailCleanup' && !isTailCleanup(row)) return false;
        if (state.quick.type === 'add' && !isAdd(row)) return false;
        if (state.quick.type === 'stage2' && row.stage !== 'STAGE_2') return false;
        if (state.quick.type === 'highWeight' && !isHighWeight(row)) return false;
        if (state.quick.type === 'gaps' && !isGap(row)) return false;
        if (state.quick.type === 'action' && row.primary_action !== state.quick.value) return false;
        if (state.quick.type === 'priority' && row.cleanup_priority !== state.quick.value) return false;
        if (state.quick.type === 'sector' && (row.sector_lens || row.sector || 'Unclassified') !== state.quick.value) return false;
        if (state.quick.type === 'pnl' && pnlBucket(row) !== state.quick.value) return false;
        if (state.quick.type === 'matrix' && matrixKey(row) !== state.quick.value) return false;
      }
      return true;
    }
    function compareRows(a, b) {
      const av = num(a[state.sort]);
      const bv = num(b[state.sort]);
      if (av !== null || bv !== null) return ((av ?? -Infinity) - (bv ?? -Infinity)) * state.dir;
      return String(a[state.sort] || '').localeCompare(String(b[state.sort] || '')) * state.dir;
    }
    function applyFilters() {
      currentRows = rows.filter(passes).sort(compareRows);
      renderMetrics(currentRows);
      renderHeatMaps(currentRows);
      renderTable(currentRows);
      document.getElementById('rowCount').textContent = currentRows.length + ' rows';
    }
    function aggregate(data, keyFn) {
      const out = new Map();
      for (const row of data) {
        const key = keyFn(row) || 'Missing';
        const current = out.get(key) || { label: key, count: 0, value: 0 };
        current.count += 1;
        current.value += num(row.value_at_market) || 0;
        out.set(key, current);
      }
      return [...out.values()].sort((a, b) => b.value - a.value);
    }
    function renderMetrics(data) {
      const totalValue = data.reduce((sum, row) => sum + (num(row.value_at_market) || 0), 0);
      const totalCost = data.reduce((sum, row) => sum + (num(row.value_at_cost) || 0), 0);
      const totalPl = data.reduce((sum, row) => sum + (num(row.unrealized_pl) || 0), 0);
      const sellCount = data.filter(isSellReduce).length;
      const tailCount = data.filter(isTailCleanup).length;
      const addCount = data.filter(isAdd).length;
      const researched = data.filter(row => row.public_research_status === 'deep_checked').length;
      document.getElementById('metricsGrid').innerHTML = [
        metric('Filtered Value', fmtInr(totalValue)),
        metric('Filtered Cost', fmtInr(totalCost)),
        metric('Filtered P/L', fmtInr(totalPl)),
        metric('Filtered Return', totalCost ? fmtPct(totalPl / totalCost * 100, 2) : '-'),
        metric('Sell/Reduce/Trim', String(sellCount)),
        metric('Tail Cleanup', String(tailCount)),
        metric('Add/Pullback', String(addCount)),
        metric('Cached Public Notes', String(researched)),
        metric('Evidence Gaps', String(data.filter(isGap).length))
      ].join('');
    }
    function metric(label, value) {
      return `<div class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
    }
    function tileColor(label, value, total, kind) {
      const share = total ? Math.min(0.86, 0.12 + (value / total) * 1.8) : 0.12;
      if (kind === 'action') {
        const text = String(label).toUpperCase();
        if (text.includes('SELL') || text.includes('REDUCE') || text.startsWith('P1')) return `rgba(166, 56, 56, ${share})`;
        if (text.includes('ADD') || text.includes('TRAIL')) return `rgba(35, 116, 91, ${share})`;
        return `rgba(154, 90, 22, ${share})`;
      }
      if (kind === 'pnl') {
        if (String(label).includes('loss')) return `rgba(166, 56, 56, ${share})`;
        if (String(label).includes('gain') || String(label).includes('Gain')) return `rgba(35, 116, 91, ${share})`;
        return `rgba(96, 112, 128, ${share})`;
      }
      return `rgba(23, 107, 135, ${share})`;
    }
    function renderTiles(id, items, kind, quickType) {
      const total = items.reduce((sum, item) => sum + item.value, 0);
      document.getElementById(id).innerHTML = items.map(item => {
        const active = state.quick && state.quick.type === quickType && state.quick.value === item.label;
        return `<button class="tile" data-kind="${esc(quickType)}" data-value="${esc(item.label)}" data-active="${active}" style="--tile-bg:${tileColor(item.label, item.value, total, kind)}">
          <strong>${esc(item.label)}</strong><span>${item.count} holdings / ${fmtInr(item.value)}</span>
        </button>`;
      }).join('');
      document.querySelectorAll(`#${id} .tile`).forEach(tile => {
        tile.addEventListener('click', () => setQuick(tile.dataset.kind, tile.dataset.value));
      });
    }
    function renderMatrix(data) {
      const labels = ['High tech / High fund','High tech / Medium fund','High tech / Low fund','High tech / Missing fund','Medium tech / High fund','Medium tech / Medium fund','Medium tech / Low fund','Medium tech / Missing fund','Low tech / High fund','Low tech / Medium fund','Low tech / Low fund','Low tech / Missing fund','Missing tech / High fund','Missing tech / Medium fund','Missing tech / Low fund','Missing tech / Missing fund'];
      const byKey = new Map(aggregate(data, matrixKey).map(item => [item.label, item]));
      const total = data.reduce((sum, row) => sum + (num(row.value_at_market) || 0), 0);
      document.getElementById('matrixHeat').innerHTML = labels.map(label => {
        const item = byKey.get(label) || { label, count: 0, value: 0 };
        const active = state.quick && state.quick.type === 'matrix' && state.quick.value === label;
        return `<button class="tile" data-kind="matrix" data-value="${esc(label)}" data-active="${active}" style="--tile-bg:${tileColor(label, item.value, total, 'sector')}">
          <strong>${esc(label)}</strong><span>${item.count} / ${fmtInr(item.value)}</span>
        </button>`;
      }).join('');
      document.querySelectorAll('#matrixHeat .tile').forEach(tile => tile.addEventListener('click', () => setQuick('matrix', tile.dataset.value)));
    }
    function renderHeatMaps(data) {
      renderTiles('actionHeat', aggregate(data, row => row.primary_action || 'Missing'), 'action', 'action');
      renderTiles('priorityHeat', aggregate(data, row => row.cleanup_priority || 'Missing'), 'action', 'priority');
      renderTiles('sectorHeat', aggregate(data, row => row.sector_lens || row.sector || 'Unclassified'), 'sector', 'sector');
      renderTiles('plHeat', aggregate(data, pnlBucket), 'pnl', 'pnl');
      renderMatrix(data);
    }
    function renderTable(data) {
      const tbody = document.getElementById('evidenceRows');
      if (!data.length) {
        tbody.innerHTML = `<tr><td colspan="14" class="empty">No holdings match the current filters.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map((row, index) => {
        const symbol = row.nse_symbol || row.broker_symbol || '-';
        return `<tr data-index="${rows.indexOf(row)}">
          <td><strong>${esc(symbol)}</strong><br><span class="badge">${esc(row.broker_symbol || '')}</span></td>
          <td>${esc(row.company_name || '')}</td>
          <td>${fmtInr(row.value_at_market)}</td>
          <td>${fmtPct(row.portfolio_weight_pct, 2)}</td>
          <td>${fmtPct(row.unrealized_pl_pct, 1)}</td>
          <td><span class="badge ${actionTone(row.primary_action)}">${esc(row.primary_action || '-')}</span></td>
          <td><span class="badge ${priorityTone(row.cleanup_priority)}">${esc(row.cleanup_priority || '-')}</span></td>
          <td>${esc(row.stage || '-')}</td>
          <td>${esc(row.trading_signal || '-')}</td>
          <td>${fmtNum(row.technical_score, 1)}</td>
          <td>${fmtNum(row.enhanced_fund_score || row.fundamental_score, 1)}</td>
          <td>${fmtPct(row.quarter_pat_yoy_pct, 1)}</td>
          <td>${esc(row.sector_lens || row.sector || '-')}</td>
          <td><span class="badge ${row.public_research_status === 'deep_checked' ? 'ok' : 'warn'}">${esc(row.public_research_status || '-')}</span></td>
        </tr>`;
      }).join('');
      tbody.querySelectorAll('tr[data-index]').forEach(tr => tr.addEventListener('click', () => renderDetail(rows[Number(tr.dataset.index)])));
    }
    function valueLine(label, value) {
      return `<span>${esc(label)}</span><strong>${esc(value ?? '-')}</strong>`;
    }
    function section(title, html) {
      return `<section class="detail-section"><h3>${esc(title)}</h3>${html}</section>`;
    }
    function kv(items) {
      return `<div class="kv">${items.map(item => valueLine(item[0], item[1])).join('')}</div>`;
    }
    function links(row) {
      const items = row.public_links || [];
      if (!items.length) return '<p>No public links available.</p>';
      return `<div class="links">${items.map(link => `<a href="${esc(link.url)}" target="_blank" rel="noopener noreferrer">${esc(link.label)}</a>`).join('')}</div>`;
    }
    function renderDetail(row) {
      if (!row) return;
      const symbol = row.nse_symbol || row.broker_symbol || '-';
      document.querySelector('#detailPane .detail-head').innerHTML = `
        <h2>${esc(symbol)}</h2>
        <p>${esc(row.company_name || '')}</p>
        <div class="chips">
          <span class="badge ${actionTone(row.primary_action)}">${esc(row.primary_action || '-')}</span>
          <span class="badge ${priorityTone(row.cleanup_priority)}">${esc(row.cleanup_priority || 'No cleanup priority')}</span>
          <span class="badge">${esc(row.stage || 'No stage')}</span>
          <span class="badge ${row.public_research_status === 'deep_checked' ? 'ok' : 'warn'}">${esc(row.public_research_status || 'public missing')}</span>
        </div>`;
      const decisionText = `${row.primary_action || 'Review'} because ${row.action_reason || 'evidence is mixed'}. Short term: ${row.short_term_view || '-'}. Medium term: ${row.medium_term_view || '-'}. Long term: ${row.long_term_view || '-'}.`;
      document.getElementById('detailBody').innerHTML = [
        section('Decision Narrative', `<p>${esc(decisionText)}</p><p><strong>Cleanup priority:</strong> ${esc(row.cleanup_priority || '-')} - ${esc(row.cleanup_reason || '-')}</p><p><strong>Risk flags:</strong> ${esc(row.risk_flags || '-')}</p>`),
        section('Position And Sizing', kv([
          ['Market value', fmtInr(row.value_at_market)],
          ['Portfolio weight', fmtPct(row.portfolio_weight_pct, 2)],
          ['Sell priority score', fmtNum(row.sell_priority_score, 0)],
          ['Model cap', fmtPct(row.target_weight_cap_pct, 2)],
          ['Model target weight', fmtPct(row.model_target_weight_pct, 2)],
          ['Model action value', fmtInr(row.model_action_value_rs)],
          ['Stop policy', row.stop_policy || '-']
        ])),
        section('Technicals', kv([
          ['Stage', row.stage || '-'],
          ['Trend signal', row.trend_signal || '-'],
          ['Trading signal', row.trading_signal || '-'],
          ['Technical score', fmtNum(row.technical_score, 1)],
          ['RSI', fmtNum(row.rsi, 1)],
          ['Relative strength', fmtNum(row.relative_strength, 1)],
          ['Supertrend', `${row.supertrend_state || '-'} ${row.supertrend_value ? '(' + fmtNum(row.supertrend_value, 2) + ')' : ''}`]
        ])),
        section('Fundamentals', kv([
          ['Fund score', fmtNum(row.enhanced_fund_score || row.fundamental_score, 1)],
          ['Earnings quality', fmtNum(row.earnings_quality, 1)],
          ['Sales growth score', fmtNum(row.sales_growth, 1)],
          ['Financial strength', fmtNum(row.financial_strength, 1)],
          ['Latest quarter', row.q_period || '-'],
          ['Q revenue / PAT', `${fmtInr(row.q_revenue)} / ${fmtInr(row.q_pat)}`],
          ['Q revenue YoY', fmtPct(row.quarter_revenue_yoy_pct, 1)],
          ['Q PAT YoY', fmtPct(row.quarter_pat_yoy_pct, 1)],
          ['Annual period', row.a_period || '-'],
          ['Annual revenue / PAT', `${fmtInr(row.a_revenue)} / ${fmtInr(row.a_pat)}`],
          ['Annual OPM', fmtPct(row.a_opm_pct, 1)],
          ['Net debt / OCF', `${fmtInr(row.net_debt)} / ${fmtInr(row.operating_cf)}`]
        ])),
        section('Sector And Market', kv([
          ['Sector lens', row.sector_lens || '-'],
          ['Stage sector', row.stage_sector || row.sector || '-'],
          ['Sector view', row.sector_view || '-'],
          ['Sector avg 1M', fmtPct(row.sector_avg_1m_pct, 1)],
          ['Sector stage 2 count', row.sector_stage2_count || '-'],
          ['Index memberships', row.index_memberships || '-']
        ])),
        section('Public Website Overlay', `<p><strong>${esc(row.public_broker_view || '-')}</strong></p><p>${esc(row.public_research_summary || '-')}</p><p><strong>Confidence:</strong> ${esc(row.public_research_confidence || '-')}</p>${links(row)}`),
        section('Local Source Trail', kv([
          ['Resolution', row.resolution_source || '-'],
          ['Local EOD date', row.eod_trade_date || summary.local_eod_date || '-'],
          ['Broker facts', row.broker_fact_count || '0'],
          ['Broker sources', row.broker_sources || '-']
        ]))
      ].join('');
    }
    function exportFilteredCsv() {
      const lines = [visibleColumns.join(',')];
      for (const row of currentRows) {
        lines.push(visibleColumns.map(key => {
          const value = row[key] ?? '';
          return '"' + String(value).replace(/"/g, '""') + '"';
        }).join(','));
      }
      const blob = new Blob([lines.join('\\n')], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'filtered_portfolio_view.csv';
      a.click();
      URL.revokeObjectURL(url);
    }
    function init() {
      document.getElementById('generatedPill').textContent = `Generated ${summary.generated_at || '-'}`;
      document.getElementById('snapshotPill').textContent = `Stage ${summary.local_stage_snapshot_date || '-'} / EOD ${summary.local_eod_date || '-'}`;
      document.getElementById('holdingPill').textContent = `${summary.holding_count || rows.length} holdings`;
      document.getElementById('marketContext').textContent = summary.market_context || 'Market context unavailable.';
      document.getElementById('markdownLink').href = payload.files.markdown;
      document.getElementById('csvLink').href = payload.files.csv;
      initFilters();
      applyFilters();
      renderDetail(rows[0]);
    }
    init();
  </script>
</body>
</html>
"""
    path.write_text(doc.replace("__DATA_JSON__", payload_json), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio", type=Path, default=DEFAULT_PORTFOLIO)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--as-of", default=datetime.now().strftime("%Y%m%d"))
    args = parser.parse_args()

    holdings = load_holdings(args.portfolio)
    master_cache = load_master_cache(MASTER_CACHE)
    master_symbols = {
        str(master_cache[h["isin"]].get("symbol") or "").upper()
        for h in holdings
        if h.get("isin") in master_cache and master_cache[h["isin"]].get("symbol")
    }
    symbols = sorted({h["broker_symbol"] for h in holdings if h.get("broker_symbol")} | master_symbols)
    isins = sorted({h["isin"] for h in holdings if h.get("isin")})
    with connect_db() as conn:
        evidence = fetch_db_evidence(conn, symbols, isins)
    sector_rotation = parse_sector_rotation(SECTOR_ROTATION_REPORT)
    enriched = enrich_holdings(holdings, evidence, sector_rotation)
    summary = build_summary(enriched, evidence, args.portfolio)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"equity_portfolio_assessment_{args.as_of}"
    csv_path = args.out_dir / f"{stem}.csv"
    json_path = args.out_dir / f"{stem}.json"
    md_path = args.out_dir / f"{stem}.md"
    html_path = args.out_dir / f"{stem}.html"

    write_csv(csv_path, enriched)
    json_path.write_text(json.dumps({"summary": summary, "holdings": enriched}, indent=2, default=str), encoding="utf-8")
    write_markdown(md_path, enriched, summary)
    write_html(html_path, md_path, csv_path, summary, enriched)

    print(json.dumps({"summary": summary, "outputs": {"csv": str(csv_path), "json": str(json_path), "markdown": str(md_path), "html": str(html_path)}}, indent=2, default=str))


if __name__ == "__main__":
    main()
