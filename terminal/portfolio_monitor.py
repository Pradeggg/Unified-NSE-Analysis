"""terminal/portfolio_monitor.py — First-class portfolio monitoring capability.

Two operating modes
-------------------
intraday (market hours 09:15–15:30 IST)
    Live P&L table with today's moves, intraday signals, and top-movers alert.
    Writes  reports/latest/portfolio_intraday.html  (auto-refresh every 60 s).

eod (after market close)
    Full multi-strategy analysis: Momentum · CANSLIM · Minervini · Fundamental
    · Value/PnL · RSI.  Writes  reports/latest/portfolio_analysis.html  with
    per-stock rationale and sector breakdown.

Public API
----------
run_intraday_view(filter_signal=None) -> str
    Returns a Rich-flavoured markdown table for terminal display and
    writes the HTML live-dashboard.

run_eod_report() -> dict
    Builds the comprehensive EOD HTML report.
    Returns {"path": ..., "success": True/False, "note": ...}

Both functions can be called directly from:
  • nse_agent.py  /my-portfolio  command handler
  • daily_refresh.py  step_portfolio_monitor()
  • terminal/reports.py  generate_preset_report("portfolio-monitor")
"""

from __future__ import annotations

import csv
import datetime
import html
import json
import os
import re
import sqlite3
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import psycopg2

_PG_DSN = (
    os.environ.get("AGENT_ADDA_PG_DSN")
    or os.environ.get("PG_DSN")
    or "dbname=nse_market user=nse_admin host=/tmp"
)

def pg_connect():
    """Open a PostgreSQL connection using the project-standard DSN."""
    return psycopg2.connect(_PG_DSN)

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent.parent          # project root
_DATA_ROOT = _HERE.parent.parent if _HERE.parent.name == ".worktrees" else _HERE
_BROKER_PORTFOLIO_CSV = _DATA_ROOT / "docs" / "my_portfolio.csv.csv"
_SIMPLE_PORTFOLIO_CSV = _DATA_ROOT / "data" / "holdings.csv"
PORTFOLIO_CSV = Path(
    os.environ.get(
        "AGENT_ADDA_PORTFOLIO_CSV",
        str(_BROKER_PORTFOLIO_CSV if _BROKER_PORTFOLIO_CSV.exists() else _SIMPLE_PORTFOLIO_CSV),
    )
)
REPORTS_DIR   = _HERE / "reports" / "latest"

INTRADAY_REPORT = REPORTS_DIR / "portfolio_intraday.html"
EOD_REPORT      = REPORTS_DIR / "portfolio_analysis.html"
TRANSACTIONS_CSV = Path(
    os.environ.get(
        "AGENT_ADDA_TRANSACTIONS_CSV",
        str(_DATA_ROOT / "portfolio-analyzer" / "output" / "closed_pnl.csv"),
    )
)

# ── Symbol mapping: broker short-code → NSE ticker ────────────────────────────
_BROKER_TO_NSE: dict[str, str] = {
    "ACTCON": "ACE",          "ADAENT": "ADANIENT",    "ADAPOR": "ADANIPORTS",
    "ADAPOW": "ADANIPOWER",   "ADOWEL": "ADOR",        "AFFIND": "AFFLE",
    "ANARAJ": "ANANTRAJ",     "ANARAT": "ANANDRATHI",  "APLAPO": "APLAPOLLO",
    "APMFIN": "MUFIN",        "APOHOS": "APOLLOHOSP",  "APOMIC": "APOLLOMICRO",
    "APOTYR": "APOLLOTYRE",   "ARTMED": "ARTEMISMED",  "ARVFAS": "ARVINDFA",
    "ASHLEY": "ASHOKLEY",     "ASTDM":  "ASTERDM",     "ASTMIC": "ASTRAMICRO",
    "ATHENE": "ATHER",        "AUSMA":  "AUBANK",      "AVESUP": "DMART",
    "AXIBAN": "AXISBANK",     "BAAUTO": "BAJAJAUTO",   "BAFINS": "BAJAJFINSV",
    "BAJFI":  "BAJFINANCE",   "BAJHOL": "BAJAJHLDNG",  "BANBAR": "BANKBARODA",
    "BANBEE": "BANKBEES",     "BELLIM": "BELRISE",     "BHA22":  "ICICIB22",
    "BHAAIR": "BHARTIARTL",   "BHADYN": "BHARATDYNAM", "BHAELE": "BEL",
    "BHAFOR": "BHARATFORG",   "BHAGEA": "BHARATGEAR",  "BHAPET": "BPCL",
    "BHEL":   "BHEL",         "BLIGVS": "BLISSGVS",    "BLUSTA": "BLUESTAR",
    "BOSLIM": "BOSCHLTD",     "BSE":    "BSE",          "CANBAN": "CANARABANK",
    "CDSL":   "CDSL",         "CESC":   "CESC",         "CHOINT": "CHOICEIN",
    "CITUNI": "CITYUNIONBANK","COCSHI": "COCHINSHIP",  "CONCOR": "CONCOR",
    "CORINT": "COROMANDEL",   "CPSETF": "CPSEETF",     "CROGR":  "CROMPTON",
    "CROGRE": "CGPOWER",      "CUMIND": "CUMMINSIND",  "CUPRUB": "CUPID",
    "DATPAT": "DATAPATTERNSIND","DECBEA":"NRBBEARING",  "DELLIM": "DELHIVERY",
    "DHABIO": "DHAMPURBIO",   "DIXTEC": "DIXON",       "DLFLIM": "DLF",
    "DRLAL":  "LALPATHLAB",   "ECLSER": "ECLERX",      "EICMOT": "EICHERMOT",
    "ENDTEC": "ENDURANCE",    "EXIIND": "EXIDEIND",    "FEDBAN": "FEDERALBNK",
    "FORHEA": "FORTIS",       "FSNECO": "NYKAA",       "GABIND": "GABRIEL",
    "GARREA": "GRSE",         "GESHIP": "GREATSHIP",   "GLAPHA": "GLAXO",
    "GLELIF": "GLENMARK",     "GLEPHA": "GLENMARK",    "GODAGR": "GODREJAGROVET",
    "GODIND": "GODREJIND",    "GOKAGR": "GOKULAGRO",   "GRANUL": "GRANULES",
    "GRAVIN": "GRAVITA",      "GUJAE":  "GUJAMBEXPORTS","GUJMI": "GMDCLTD",
    "HAVIND": "HAVELLS",      "HAWCOO": "HAWKINCOOK",  "HBLPOW": "HBLPOWER",
    "HDFAMC": "HDFCAMC",      "HDFBAN": "HDFCBANK",    "HEG":    "HEG",
    "HGINF":  "HGINFRA",      "HIMFUT": "HFCL",        "HINAER": "HAL",
    "HINCOP": "HINDCOPPER",   "HINDAL": "HINDALCO",    "HINLEV": "HINDUNILVR",
    "HINREC": "HIRECT",       "ICIBAN": "ICICIBANK",   "ICILOM": "ICICIGI",
    "ICIPRU": "ICICIPRULI",   "IDBI":   "IDBIBANK",    "IDFC":   "IDFCFIRSTB",
    "INDHOT": "INDHOTEL",     "INDOIL": "IOC",         "INDREN": "IREDA",
    "INFTEC": "INFY",         "INTAVI": "INDIGO",      "ITC":    "ITC",
    "ITCHOT": "ITCHOTELS",    "JINSP":  "JINDALSTEL",  "JKCEME": "JKCEMENT",
    "JSWENE": "JSWENERGY",    "JSWSTE": "JSWSTEEL",    "JUBLIF": "JUBILANTPHARMA",
    "JYOLAB": "JYOTHYLAB",    "KANNER": "KANSAINER",   "KARVYS": "KARURVYSYA",
    "KERMIC": "KERNEX",       "KIRENG": "KIRLOSENG",   "KOTMAH": "KOTAKBANK",
    "KRBL":   "KRBL",         "KRIINS": "KIMS",        "KWAWAL": "KWALITY",
    "LARTOU": "LT",           "LAULAB": "LAURUSLABS",  "LIC":    "LICI",
    "LKPMER": "GYFTR",        "LTOVER": "LTFOODS",     "MAHCIE": "CIEINDIA",
    "MAHMAH": "M&M",          "MAIALL": "MAITHANALLOYS","MANAFI":"MANAPPURAM",
    "MARLIM": "MARICO",       "MARUTI": "MARUTI",      "MAXHEA": "MAXHEALTH",
    "MAZDOC": "MAZDOCK",      "MCX":    "MCX",          "MEDHEA": "MEDPLUS",
    "MOTSU":  "MOTHERSON",    "MOTSUM": "MOTHERSON",   "MPHLIM": "MPHASIS",
    "MTATEC": "MTARTECH",     "MUTFIN": "MUTHOOTFIN",  "NAGCON": "NCC",
    "NARHRU": "NH",           "NAVBHA": "NAVA",        "NAVFLU": "NAVINFLUOR",
    "NESIND": "NESTLEIND",    "NEYLIG": "NLCINDIA",    "NHPC":   "NHPC",
    "NIITEC": "COFORGE",      "NRBBEA": "NRBBEARING",  "NTPC":   "NTPC",
    "OBEREA": "OBEROIRLTY",   "ORIREF": "RHIMAGNESITA","PGELEC": "PGEL",
    "PIDIND": "PIDILITIND",   "PNCINF": "PNCINFRA",    "POLI":   "POLYCAB",
    "PONOXI": "PONDYOX",      "POWGRI": "POWERGRID",   "PREEXP": "PREMIEREXP",
    "PSUBAN": "PSUBNKBEES",   "PUNBAN": "PNB",         "RAIVIK": "RVNL",
    "RAYMON": "RAYMOND",      "RELNIP": "NAM-INDIA",   "ROSTEC": "ROSSELTECHSYS",
    "SAGCEM": "SAGARCEM",     "SAIL":   "SAIL",         "SANEN":  "SANSERA",
    "SBFFIN": "SBFC",         "SBICAR": "SBICARD",     "SBIGOL": "SBIETFGOLD",
    "SBILIF": "SBILIFE",      "SCHELE": "SCHNEIDER",   "SHAILY": "SHAILYENG",
    "SHRPIS": "SHRIPISTON",   "SHRTRA": "SHRIRAMFIN",  "SIEMEN": "SIEMENS",
    "SKYGOL": "SKYGOLD",      "SOLIN":  "SOLARINDS",   "SOMCER": "SOMANYCERA",
    "STABAN": "SBIN",         "SUNF":   "SUNFLAG",     "SUNIRO": "SUNFLAGIRON",
    "SUNPHA": "SUNPHARMA",    "SUPLIF": "SUPRIYA",     "TATCO":  "TATACOFFEE",
    "TATCOV": "TATAMOTORS",   "TATELX": "TATAELXSI",   "TATMOT": "TATAMTRDVR",
    "TATNID": "TATANIFTYDIGITAL","TATPOW":"TATAPOWER",  "TATSPO": "TATASTEEL",
    "TATSTE": "TATASTEEL",    "TCS":    "TCS",          "TDPSYS": "TDPOWERSYS",
    "TECMAH": "TECHM",        "TIMGRO": "TIMEXIND",    "TITIND": "TITAN",
    "TMLDVR": "TATAMTRDVR",   "TRENT":  "TRENT",       "TUBINV": "CHOLAHLDNG",
    "UJJFIN": "UJJIVANFIN",   "UJJSMA": "UJJIVANSFB",  "UNISPI": "UNITDSPR",
    "USHMA":  "USHAMARTIN",   "VARBEV": "VBL",          "VATWAB": "WABAG",
    "VISRET": "V2RETAIL",     "VSTTIL": "VSTTILLERS",  "WELEN":  "WELENT",
    "WELINV": "WELSPUNLIV",   "WINBIO": "WINDLAS",     "ZINLOG": "BLACKBUCK",
    "ZOMLIM": "ZOMATO",       "NIVBUP": "NIVABUPA",    "ICIA30": "ICIALPHAETF", "ICIAUT": "ICICIAUTO",
    "ICIGOL": "ICICIGOLD",    "NIFBEE": "NIFTYBEES",   "INFBEE": "INFRAETF",
    "AXITEC": "AXISNIFTYIT",  "CPSETF": "CPSEETF",
}

# ── ETF / untracked classification ───────────────────────────────────────────
# Broker codes that are ETFs — no stage/fundamental analysis possible
_ETF_BROKERS: frozenset[str] = frozenset({
    "BHA22", "ICIA30", "ICIAUT", "ICIGOL", "INFBEE", "PSUBAN",
    "NIFBEE", "BANBEE", "AXITEC", "CPSETF", "SBIGOL", "TATNID",
})

# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_num(s: str) -> float:
    if not s or not s.strip():
        return 0.0
    s = s.strip()
    neg = "(" in s
    s = s.replace(",", "").replace("(", "").replace(")", "").strip()
    try:
        v = float(s)
    except ValueError:
        return 0.0
    return -v if neg else v


def _parse_pct(s: str) -> float:
    if not s or not s.strip():
        return 0.0
    s = s.strip()
    neg = "(" in s or s.startswith("-")
    s = s.replace(",", "").replace("%", "").replace("+", "").replace("-", "")
    s = s.replace("(", "").replace(")", "").strip()
    try:
        v = float(s)
    except ValueError:
        return 0.0
    return -v if neg else v


def _normalize_name(name: str) -> str:
    name = name.upper()
    for word in [
        "LIMITED", "LTD", "LTD.", "PRIVATE", "PVT", "INDIA", "INDUSTRIES",
        "CORPORATION", "ENTERPRISES", "HOLDINGS", "SERVICES", "SOLUTIONS",
        "TECHNOLOGIES", "TECHNOLOGY", "AND", "&", "OF", "THE", "CO.", "CO",
    ]:
        name = re.sub(r"\b" + word + r"\b", "", name)
    return " ".join(re.sub(r"[^A-Z0-9 ]", "", name).split())


def _is_market_hours() -> bool:
    """True during NSE trading hours (09:15–15:30 IST Mon–Fri)."""
    try:
        ist_now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(hours=5, minutes=30)
        if ist_now.weekday() >= 5:
            return False
        t = ist_now.time()
        return datetime.time(9, 15) <= t <= datetime.time(15, 30)
    except Exception:
        return False


# ── Portfolio loader ──────────────────────────────────────────────────────────

def _load_portfolio(csv_path: Path = PORTFOLIO_CSV) -> list[dict]:
    rows = []
    with open(csv_path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            bs = (row.get("Stock Symbol") or row.get("symbol") or "").strip().upper()
            if not bs:
                continue

            if "symbol" in row and "Stock Symbol" not in row:
                qty = _parse_num(row.get("qty", ""))
                avg_cost = _parse_num(row.get("avg_cost", ""))
                value_cost = qty * avg_cost
                rows.append({
                    "broker":     bs,
                    "company":    (row.get("company") or row.get("name") or bs).strip(),
                    "qty":        qty,
                    "avg_cost":   avg_cost,
                    "cmp":        _parse_num(row.get("cmp", "") or row.get("current_price", "")),
                    "value_cost": value_cost,
                    "value_mkt":  _parse_num(row.get("value_mkt", "") or row.get("market_value", "")),
                    "upnl":       _parse_num(row.get("upnl", "") or row.get("unrealized_pnl", "")),
                    "upnl_pct":   _parse_num(row.get("upnl_pct", "") or row.get("unrealized_pnl_pct", "")),
                    "rpnl":       _parse_num(row.get("rpnl", "") or row.get("realized_pnl", "")),
                    "day_chg_pct": _parse_pct(row.get("day_chg_pct", "") or row.get("change_1d_pct", "")),
                    "buy_date":   (row.get("buy_date") or "").strip(),
                })
                continue

            pct_raw = (row.get("Unrealized Profit/Loss %") or "").strip().strip(",")
            neg_pct = "(" in pct_raw
            try:
                pct = float(pct_raw.strip("()")) * (-1 if neg_pct else 1)
            except ValueError:
                pct = 0.0
            rows.append({
                "broker":     bs,
                "company":    (row.get("Company Name") or "").strip(),
                "qty":        _parse_num(row.get("Qty", "")),
                "avg_cost":   _parse_num(row.get("Average Cost Price", "")),
                "cmp":        _parse_num(row.get("Current Market Price", "")),
                "value_cost": _parse_num(row.get("Value At Cost", "")),
                "value_mkt":  _parse_num(row.get("Value At Market Price", "")),
                "upnl":       _parse_num(row.get("Unrealized Profit/Loss", "")),
                "upnl_pct":   pct,
                "rpnl":       _parse_num(row.get("Realized Profit / Loss", "")),
                "day_chg_pct": _parse_pct(row.get("% Change over prev close", "")),
                })
    return rows


def _load_transactions(csv_path: Path = TRANSACTIONS_CSV, *, limit: int | None = None) -> list[dict]:
    """Load optional closed-transaction ledger rows.

    The current broker holdings export carries realized P&L by symbol but not
    every fill. When a closed-P&L export is available, surface it as the
    transaction ledger in the first-class portfolio report.
    """
    if not csv_path or not Path(csv_path).exists():
        return []
    rows: list[dict] = []
    with open(csv_path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            symbol = (row.get("symbol") or row.get("Stock Symbol") or row.get("broker") or "").strip().upper()
            if not symbol:
                continue
            purchase_value = _parse_num(row.get("purchase_value", "") or row.get("buy_value", ""))
            sale_value = _parse_num(row.get("sale_value", "") or row.get("sell_value", ""))
            pnl = _parse_num(row.get("pnl", "") or row.get("realized_pnl", "") or row.get("Realized Profit / Loss", ""))
            rows.append({
                "symbol": symbol,
                "isin": (row.get("isin") or row.get("ISIN Code") or "").strip(),
                "qty": _parse_num(row.get("qty", "") or row.get("Qty", "")),
                "purchase_date": (row.get("purchase_date") or row.get("buy_date") or "").strip(),
                "purchase_rate": _parse_num(row.get("purchase_rate", "") or row.get("buy_price", "")),
                "purchase_value": purchase_value,
                "sale_date": (row.get("sale_date") or row.get("sell_date") or "").strip(),
                "sale_rate": _parse_num(row.get("sale_rate", "") or row.get("sell_price", "")),
                "sale_value": sale_value,
                "pnl": pnl,
                "pnl_pct": (pnl / purchase_value * 100) if purchase_value else 0.0,
                "tenure_bucket": (row.get("tenure_bucket") or row.get("holding_period") or "").strip(),
            })
    rows.sort(key=lambda r: (r.get("sale_date") or "", r.get("symbol") or ""), reverse=True)
    return rows[:limit] if limit else rows


def _portfolio_broker_metrics(rows: list[dict], *, value_key: str = "value_mkt") -> dict:
    """Broker-screen compatible totals and day movers.

    Broker exports provide current value and % change over previous close.
    The day gain shown on the broker screen is therefore:
      current value - current value / (1 + day_change_pct / 100)
    not day_change_pct applied to original cost.
    """
    enriched: list[dict] = []
    total_cost = 0.0
    current_value = 0.0
    total_day_gain = 0.0
    for row in rows:
        cost = float(row.get("value_cost") or 0.0)
        value = float(row.get(value_key) or row.get("value_mkt") or 0.0)
        pct = row.get("day_chg_pct")
        try:
            pct_f = float(pct if pct is not None else 0.0)
        except (TypeError, ValueError):
            pct_f = 0.0
        denominator = 1.0 + pct_f / 100.0
        prev_value = value / denominator if denominator > 0 else value
        day_gain = value - prev_value
        total_cost += cost
        current_value += value
        total_day_gain += day_gain
        enriched.append({
            **row,
            "broker_day_gain": day_gain,
            "broker_prev_value": prev_value,
        })
    absolute_return_pct = (current_value / total_cost - 1.0) * 100.0 if total_cost else 0.0
    max_gainer = max(enriched, key=lambda r: r["broker_day_gain"], default=None)
    max_loser = min(enriched, key=lambda r: r["broker_day_gain"], default=None)
    return {
        "total_cost": total_cost,
        "current_value": current_value,
        "day_gain": total_day_gain,
        "day_gain_pct": (total_day_gain / (current_value - total_day_gain) * 100.0)
        if current_value != total_day_gain else 0.0,
        "absolute_return_pct": absolute_return_pct,
        "max_gainer": max_gainer,
        "max_loser": max_loser,
    }


# ── DB snapshot loader ────────────────────────────────────────────────────────

def _load_db_snapshot(db_path: Optional[Path] = None) -> tuple[dict[str, dict], str]:
    """Load latest stage_snapshots from PostgreSQL, then optional SQLite fallback."""

    cols = [
        "symbol", "company_name", "stage", "stage_score", "price", "live_price",
        "tech_score", "rsi", "trade_sig", "trend_sig", "rel_str",
        "chg1d", "chg1w", "chg1m", "mktcap", "sector",
        "fund_score", "efund_score", "earn_qual", "sales_gr",
        "fin_str", "inst_back", "canslim", "minervini", "inv_score",
        "fund_det", "narrative", "stance", "supertrend", "st_val",
    ]

    conn = None
    try:
        conn = pg_connect()
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(snapshot_date)::text FROM scores.stage_snapshots")
            row = cur.fetchone()
            if not row or not row[0]:
                return {}, "N/A"
            snap_date = row[0]
            cur.execute(
                """
                SELECT symbol, company_name, stage, stage_score, price, live_price,
                       technical_score, rsi, trading_signal, trend_signal, relative_strength,
                       change_1d_pct, change_1w_pct, change_1m_pct, market_cap_cat, sector,
                       fundamental_score, enhanced_fund_score, earnings_quality, sales_growth,
                       financial_strength, institutional_backing, can_slim_score, minervini_score,
                       investment_score, fund_details::text, narrative, stance, supertrend_state,
                       supertrend_value
                FROM scores.stage_snapshots
                WHERE snapshot_date = %s
                """,
                (snap_date,),
            )
            records: dict[str, dict] = {}
            for result in cur.fetchall():
                data = dict(zip(cols, result))
                records[data["symbol"]] = data
            return records, snap_date
    except Exception:
        pass
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    if not db_path or not Path(db_path).exists():
        return {}, "N/A"

    sql_conn = None
    try:
        sql_conn = sqlite3.connect(str(db_path))
        sql_conn.row_factory = sqlite3.Row
        snap_row = sql_conn.execute(
            "SELECT MAX(snapshot_date) AS snapshot_date FROM stage_snapshots"
        ).fetchone()
        snap_date = snap_row["snapshot_date"] if snap_row else None
        if not snap_date:
            return {}, "N/A"
        query = """
            SELECT symbol, company_name, stage, stage_score, price, live_price,
                   technical_score AS tech_score, rsi, trading_signal AS trade_sig,
                   trend_signal AS trend_sig, relative_strength AS rel_str,
                   change_1d_pct AS chg1d, change_1w_pct AS chg1w,
                   change_1m_pct AS chg1m, market_cap_cat AS mktcap, sector,
                   fundamental_score AS fund_score,
                   enhanced_fund_score AS efund_score,
                   earnings_quality AS earn_qual, sales_growth AS sales_gr,
                   financial_strength AS fin_str,
                   institutional_backing AS inst_back,
                   can_slim_score AS canslim, minervini_score AS minervini,
                   investment_score AS inv_score, fund_details AS fund_det,
                   narrative, stance, supertrend_state AS supertrend,
                   supertrend_value AS st_val
            FROM stage_snapshots
            WHERE snapshot_date = ?
        """
        records = {}
        for row in sql_conn.execute(query, (snap_date,)).fetchall():
            data = {column: row[column] for column in cols}
            records[data["symbol"]] = data
        return records, str(snap_date)
    except Exception:
        return {}, "N/A"
    finally:
        if sql_conn is not None:
            try:
                sql_conn.close()
            except Exception:
                pass


def _load_latest_fundamentals_lookup() -> dict[str, dict]:
    """Load latest Screener-derived fundamental detail summaries from PostgreSQL."""
    conn = None
    try:
        conn = pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT symbol, pnl_summary, quarterly_summary, balance_sheet_summary,
                       cash_flow_summary, investor_summary, ratios_summary
                FROM scores.v_latest_fundamentals
                """
            )
            lookup: dict[str, dict] = {}
            for row in cur.fetchall():
                symbol = str(row[0] or "").strip().upper()
                if not symbol:
                    continue
                details = {
                    "pnl_summary": row[1],
                    "quarterly_summary": row[2],
                    "balance_sheet_summary": row[3],
                    "cash_flow_summary": row[4],
                    "investor_summary": row[5],
                    "ratios_summary": row[6],
                }
                details = {k: v for k, v in details.items() if v}
                if details:
                    lookup[symbol] = details
            return lookup
    except Exception:
        return {}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ── Symbol matching ───────────────────────────────────────────────────────────

def _build_db_norm(records: dict[str, dict]) -> dict[str, str]:
    return {sym: _normalize_name(r["company_name"] or "") for sym, r in records.items()}


def _find_match(broker: str, company: str, records: dict, db_norm: dict) -> Optional[dict]:
    nse = _BROKER_TO_NSE.get(broker)
    if nse and nse in records:
        return records[nse]
    if broker in records:
        return records[broker]
    nc = _normalize_name(company)
    best, bsym = 0.0, None
    for sym, nd in db_norm.items():
        if nd:
            s = SequenceMatcher(None, nc, nd).ratio()
            if s > best:
                best, bsym = s, sym
    if best > 0.55 and bsym:
        return records[bsym]
    return None


# ── Strategy evaluators ───────────────────────────────────────────────────────

def _strat_momentum(d: Optional[dict]) -> tuple[Optional[str], str]:
    if not d:
        return None, "No data"
    stage = d.get("stage") or ""
    trend = d.get("trend_sig") or ""
    sup   = d.get("supertrend") or ""
    tech  = float(d.get("tech_score") or 0)
    rsi   = float(d.get("rsi") or 50)
    if stage in ("STAGE_2", "STAGE_1") and trend in ("STRONG_BULLISH", "BULLISH") and sup == "BULLISH" and tech >= 60:
        return "BUY", f"Stage {stage[-1]}, {trend}, Supertrend BULLISH, Tech {tech:.0f}"
    if stage == "STAGE_4" or trend in ("STRONG_BEARISH", "BEARISH") or sup == "BEARISH":
        return "SELL", f"{stage or '?'}, {trend}, ST={sup}"
    if stage == "STAGE_3" or rsi > 75:
        return "HOLD", f"Stage {stage[-1] if stage else '?'}, RSI {rsi:.0f} (caution)"
    return "HOLD", f"Stage {stage[-1] if stage else '?'}, {trend}"


def _strat_canslim(d: Optional[dict]) -> tuple[Optional[str], str]:
    if not d:
        return None, "No data"
    score = float(d.get("canslim") or 0)
    if score >= 18:
        return "BUY",  f"CANSLIM {score:.0f}/30 — Strong"
    if score >= 14:
        return "BUY",  f"CANSLIM {score:.0f}/30 — Moderate"
    if score >= 10:
        return "HOLD", f"CANSLIM {score:.0f}/30 — Neutral"
    if score > 0:
        return "SELL", f"CANSLIM {score:.0f}/30 — Weak"
    return None, "CANSLIM N/A"


def _strat_minervini(d: Optional[dict]) -> tuple[Optional[str], str]:
    if not d:
        return None, "No data"
    score = float(d.get("minervini") or 0)
    stage = d.get("stage") or ""
    sup   = d.get("supertrend") or ""
    if score >= 18 and stage == "STAGE_2" and sup == "BULLISH":
        return "BUY",  f"Minervini {score:.0f}/30, Stage 2 + Bullish ST"
    if score >= 14:
        return "BUY",  f"Minervini {score:.0f}/30 — setup forming"
    if score >= 10:
        return "HOLD", f"Minervini {score:.0f}/30 — watch"
    if score > 0:
        return "SELL", f"Minervini {score:.0f}/30 — avoid"
    return None, "Minervini N/A"


def _parse_fund_details(fd_raw) -> dict:
    """Parse fund_details JSON into a flat dict. Returns {} on failure."""
    if not fd_raw:
        return {}
    try:
        return json.loads(fd_raw) if isinstance(fd_raw, str) else fd_raw
    except (json.JSONDecodeError, TypeError):
        return {}


def _extract_pct(text: str, keyword: str) -> Optional[float]:
    """Extract a YoY percentage from text like 'NetProfit: 57,936 Cr (YoY +6.2%)'."""
    pattern = keyword + r"[^(]*\(YoY\s*([+-]?\d+(?:\.\d+)?)\s*%\)"
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


def _extract_ratio(text: str, keyword: str) -> Optional[float]:
    """Extract a ratio value from text like 'ROCE: 14.6; ROE: 15.9'."""
    pattern = keyword + r"[:\s]+([+-]?\d+(?:\.\d+)?)\s*%?"
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


def _derive_fund_score_from_details(fd: dict) -> dict:
    """
    Derive fundamental quality scores from the fund_details JSON when
    enhanced_fund_score is NULL in the DB.

    Returns dict with keys: efund, earnq, salesgr, roce, roe, rev_growth,
    np_growth, pe, fii_pct, notes — all used by _strat_fundamental_derived.
    """
    pnl     = fd.get("pnl_summary", "") or ""
    ratios  = fd.get("ratios_summary", "") or ""
    inv_sum = fd.get("investor_summary", "") or ""

    rev_growth = _extract_pct(pnl, "Sales")
    np_growth  = _extract_pct(pnl, "NetProfit")
    roce       = _extract_ratio(ratios, "ROCE")
    roe        = _extract_ratio(ratios, "ROE")
    pe         = _extract_ratio(ratios, r"P/E")
    npm        = _extract_ratio(ratios, "NPM")

    # FII institutional backing from investor_summary
    fii_m = re.search(r"FII\s+([\d.]+)%", inv_sum)
    dii_m = re.search(r"DII\s+([\d.]+)%", inv_sum)
    fii_pct = float(fii_m.group(1)) if fii_m else None
    dii_pct = float(dii_m.group(1)) if dii_m else None
    inst_total = (fii_pct or 0) + (dii_pct or 0)

    def _score_growth(g):
        if g is None: return 50.0
        if g >= 25:   return 90.0
        if g >= 15:   return 78.0
        if g >= 8:    return 65.0
        if g >= 0:    return 50.0
        if g >= -15:  return 35.0
        return 15.0

    def _score_roce(r):
        if r is None: return 50.0
        if r >= 30:   return 90.0
        if r >= 20:   return 78.0
        if r >= 12:   return 62.0
        if r >= 6:    return 48.0
        return 30.0

    def _score_roe(r):
        if r is None: return 50.0
        if r >= 20:   return 88.0
        if r >= 15:   return 72.0
        if r >= 10:   return 58.0
        if r >= 5:    return 42.0
        return 25.0

    def _score_inst(i):
        if i >= 60:   return 85.0
        if i >= 40:   return 70.0
        if i >= 20:   return 55.0
        return 35.0

    salesgr = _score_growth(rev_growth)
    earnq   = _score_growth(np_growth)
    fin_str = (_score_roce(roce) * 0.6 + _score_roe(roe) * 0.4)
    inst    = _score_inst(inst_total) if inst_total > 0 else 50.0

    # Composite efund: weighted blend
    efund = salesgr * 0.25 + earnq * 0.30 + fin_str * 0.30 + inst * 0.15

    notes_parts = []
    if rev_growth is not None:  notes_parts.append(f"RevGr {rev_growth:+.1f}%")
    if np_growth  is not None:  notes_parts.append(f"ProfGr {np_growth:+.1f}%")
    if roce       is not None:  notes_parts.append(f"ROCE {roce:.1f}%")
    if roe        is not None:  notes_parts.append(f"ROE {roe:.1f}%")
    if pe         is not None:  notes_parts.append(f"P/E {pe:.1f}x")

    return {
        "efund":      round(efund, 1),
        "earnq":      round(earnq, 1),
        "salesgr":    round(salesgr, 1),
        "fin_str":    round(fin_str, 1),
        "inst":       round(inst, 1),
        "rev_growth": rev_growth,
        "np_growth":  np_growth,
        "roce":       roce,
        "roe":        roe,
        "pe":         pe,
        "notes":      " · ".join(notes_parts),
        "derived":    True,
    }


def _strat_fundamental(d: Optional[dict]) -> tuple[Optional[str], str]:
    if not d:
        return None, "No data"

    ef = float(d.get("efund_score") or 0)
    eq = float(d.get("earn_qual")   or 0)
    sg = float(d.get("sales_gr")    or 0)

    # If the DB scores are populated, use them directly
    if ef > 0 and eq > 0:
        if ef >= 70 and eq >= 70 and sg >= 60:
            return "BUY",  f"eFund {ef:.0f}, EarnQ {eq:.0f}, SalesGr {sg:.0f}"
        if ef >= 55 and eq >= 55:
            return "HOLD", f"eFund {ef:.0f}, EarnQ {eq:.0f} — decent"
        if ef < 40 or eq < 40:
            return "SELL", f"eFund {ef:.0f}, EarnQ {eq:.0f} — weak"
        return "HOLD", f"eFund {ef:.0f} — average"

    # Fallback: derive from fund_details JSON (covers large caps with NULL scores)
    fd_raw = d.get("fund_det")
    fd = _parse_fund_details(fd_raw) if fd_raw else {}
    if not fd:
        return None, "No fundamental data"

    derived = _derive_fund_score_from_details(fd)
    ef2 = derived["efund"]
    eq2 = derived["earnq"]
    sg2 = derived["salesgr"]
    notes = derived["notes"]

    if ef2 >= 70 and eq2 >= 70 and sg2 >= 60:
        return "BUY",  f"[derived] {notes}"
    if ef2 >= 55 and eq2 >= 55:
        return "HOLD", f"[derived] {notes} — decent"
    if ef2 < 40 or eq2 < 40:
        return "SELL", f"[derived] {notes} — weak"
    return "HOLD", f"[derived] {notes}"


def _strat_value(stock: dict, _d: Optional[dict]) -> tuple[Optional[str], str]:
    pct = stock["upnl_pct"]
    if pct <= -30:
        return "SELL", f"Deep loss {pct:.1f}% — cut"
    if pct <= -20:
        return "SELL", f"Loss {pct:.1f}% — exit"
    if pct >= 100:
        return "HOLD", f"100%+ gain {pct:.1f}% — trail stop"
    if pct >= 50:
        return "HOLD", f"Gain {pct:.1f}% — trail stop"
    if 0 <= pct < 10:
        return "HOLD", f"Small gain {pct:.1f}%"
    if pct < 0:
        return "HOLD", f"Mild loss {pct:.1f}%"
    return "HOLD", f"Gain {pct:.1f}%"


def _strat_vcp(d: Optional[dict]) -> tuple[Optional[str], str]:
    if not d:
        return None, "No data"
    stage = d.get("stage") or ""
    trend = d.get("trend_sig") or ""
    sup = d.get("supertrend") or ""
    tech = float(d.get("tech_score") or 0)
    minervini = float(d.get("minervini") or 0)
    bullish = trend in ("BULLISH", "STRONG_BULLISH")
    if stage == "STAGE_4" or trend in ("BEARISH", "STRONG_BEARISH") or sup == "BEARISH":
        return "SELL", f"VCP broken: {stage or '?'}, {trend or 'N/A'}, ST={sup or 'N/A'}"
    if stage in ("STAGE_2", "STAGE_1") and bullish and sup == "BULLISH" and minervini >= 14 and tech >= 55:
        return "BUY", f"VCP setup: Stage {stage[-1]}, {trend}, ST BULLISH, Minervini {minervini:.0f}, Tech {tech:.0f}"
    if stage in ("STAGE_2", "STAGE_1") and bullish and sup == "BULLISH" and (minervini >= 10 or tech >= 50):
        return "HOLD", f"VCP forming: Stage {stage[-1]}, {trend}, Minervini {minervini:.0f}, Tech {tech:.0f}"
    return "HOLD", f"No clean VCP: Stage {stage[-1] if stage else '?'}, {trend or 'N/A'}, ST={sup or 'N/A'}"


def _strat_rs_nifty500(d: Optional[dict]) -> tuple[Optional[str], str]:
    if not d:
        return None, "No data"
    rs = float(d.get("rel_str") or 0)
    if rs >= 20:
        return "BUY", f"RS vs NIFTY 500 {rs:+.1f}: outperforming"
    if rs < -10:
        return "SELL", f"RS vs NIFTY 500 {rs:+.1f}: underperforming"
    return "HOLD", f"RS vs NIFTY 500 {rs:+.1f}: neutral"


def _strat_rsi(d: Optional[dict]) -> tuple[Optional[str], str]:
    if not d:
        return None, "No data"
    rsi   = float(d.get("rsi") or 50)
    trend = d.get("trend_sig") or ""
    if rsi <= 30 and trend in ("BULLISH", "STRONG_BULLISH"):
        return "BUY",  f"RSI {rsi:.0f} oversold in uptrend"
    if rsi >= 80:
        return "SELL", f"RSI {rsi:.0f} overbought — trim"
    if rsi <= 35:
        return "BUY",  f"RSI {rsi:.0f} oversold"
    return None, f"RSI {rsi:.0f}"


def _composite_signal(signals: dict) -> tuple[str, int, int, int]:
    buy = sell = hold = 0
    for sig, _ in signals.values():
        if sig == "BUY":
            buy += 1
        elif sig == "SELL":
            sell += 1
        elif sig == "HOLD":
            hold += 1
    if sell >= 2 and sell > buy:
        return "SELL",       buy, sell, hold
    if buy >= 3 and buy > sell + 1:
        return "STRONG BUY", buy, sell, hold
    if buy >= 2 and buy > sell:
        return "BUY",        buy, sell, hold
    if sell >= 1 and buy == 0:
        return "SELL",       buy, sell, hold
    return "HOLD",           buy, sell, hold


# ── Full analysis builder ─────────────────────────────────────────────────────

def _analyse_portfolio(
    portfolio: list[dict],
    records: dict[str, dict],
    db_norm: dict[str, str],
    live_prices: Optional[dict[str, float]] = None,
    fund_lookup: Optional[dict[str, dict]] = None,
) -> list[dict]:
    results = []
    if fund_lookup is None:
        fund_lookup = _load_latest_fundamentals_lookup()
    for s in portfolio:
        d = _find_match(s["broker"], s["company"], records, db_norm)

        # Overlay live intraday price if available
        live_cmp = s["cmp"]
        if (not live_cmp or live_cmp <= 0) and d:
            live_cmp = float(d.get("live_price") or d.get("price") or 0)
        day_chg_pct: Optional[float] = s.get("day_chg_pct")
        if live_prices:
            nse_sym = _BROKER_TO_NSE.get(s["broker"])
            live_p = live_prices.get(nse_sym) or live_prices.get(s["broker"])
            if live_p and live_p > 0:
                if d and d.get("price") and float(d["price"]) > 0:
                    prev_close = float(d["price"])
                    day_chg_pct = (live_p / prev_close - 1) * 100
                live_cmp = live_p

        sigs = {
            "Momentum":    _strat_momentum(d),
            "CANSLIM":     _strat_canslim(d),
            "Minervini":   _strat_minervini(d),
            "Fundamental": _strat_fundamental(d),
            "Value/PnL":   _strat_value(s, d),
            "VCP":         _strat_vcp(d),
            "RS Strategy": _strat_rs_nifty500(d),
        }
        comp, nb, ns, nh = _composite_signal(sigs)

        fd: dict = _parse_fund_details(d.get("fund_det")) if d else {}
        if d and not fd:
            fd = fund_lookup.get(str(d.get("symbol") or "").upper(), {}) or {}

        # Derive or pull fundamental scores for display
        ef_db = float(d.get("efund_score") or 0) if d else 0
        eq_db = float(d.get("earn_qual")   or 0) if d else 0
        if ef_db > 0 and eq_db > 0:
            derived_fund = None  # use DB scores as-is
        else:
            derived_fund = _derive_fund_score_from_details(fd) if fd else None

        # Resolved fundamental display values
        ef_disp = ef_db if ef_db > 0 else (derived_fund["efund"]  if derived_fund else None)
        eq_disp = eq_db if eq_db > 0 else (derived_fund["earnq"]  if derived_fund else None)
        sg_disp = float(d.get("sales_gr") or 0) if d else 0
        sg_disp = sg_disp if sg_disp > 0 else (derived_fund["salesgr"] if derived_fund else None)

        # Live P&L computed from live price
        live_value = live_cmp * s["qty"] if live_cmp else s["value_mkt"]
        live_upnl  = live_value - s["value_cost"]
        live_upnl_pct = (live_value / s["value_cost"] - 1) * 100 if s["value_cost"] > 0 else 0
        pct_for_day = float(day_chg_pct or 0.0)
        day_denominator = 1.0 + pct_for_day / 100.0
        live_prev_value = live_value / day_denominator if day_denominator > 0 else live_value
        broker_prev_value = s["value_mkt"] / day_denominator if day_denominator > 0 else s["value_mkt"]
        live_day_gain = live_value - live_prev_value
        broker_day_gain = s["value_mkt"] - broker_prev_value

        results.append({
            **s,
            "db":           d,
            "live_cmp":     live_cmp,
            "live_value":   live_value,
            "live_upnl":    live_upnl,
            "live_upnl_pct":live_upnl_pct,
            "day_chg_pct":  day_chg_pct,
            "live_day_gain": live_day_gain,
            "broker_day_gain": broker_day_gain,
            "broker_prev_value": broker_prev_value,
            "signals":      sigs,
            "composite":    comp,
            "buy_count":    nb,
            "sell_count":   ns,
            "hold_count":   nh,
            "stage":        d["stage"]      if d else "N/A",
            "tech_score":   d["tech_score"] if d else None,
            "rsi_val":      d["rsi"]        if d else None,
            "rs_nifty500":   d["rel_str"]    if d else None,
            "inv_score":    d["inv_score"]  if d else None,
            "sector":       d["sector"]     if d else "N/A",
            "canslim_sc":   d["canslim"]    if d else None,
            "minervini_sc": d["minervini"]  if d else None,
            "efund_sc":     ef_disp,
            "earnq_sc":     eq_disp,
            "salesgr_sc":   sg_disp,
            "derived_fund": derived_fund,
            "narrative":    d["narrative"]  if d else "",
            "supertrend":   d["supertrend"] if d else "",
            "trend_sig":    d["trend_sig"]  if d else "",
            "fund_det":     fd,
            # coverage label used by heat map and display
            "coverage":     (
                "etf"       if s["broker"] in _ETF_BROKERS else
                "full"      if d is not None else
                "untracked"
            ),
        })
    return results


# ── Live price fetch (yfinance, lightweight) ──────────────────────────────────

# ── yfinance ticker overrides ─────────────────────────────────────────────────
# NSE symbol → yfinance ticker (when they differ).
# Reasons: renamed companies, hyphenated yfinance tickers, merged entities.
_YF_TICKER_OVERRIDES: dict[str, str] = {
    # Corporate actions / renames
    "ZOMATO":          "ETERNAL",      # Zomato renamed to Eternal Limited
    "TATACOFFEE":      "TATACONSUM",   # Tata Coffee merged into Tata Consumer
    # yfinance uses different NSE ticker casing/format
    "BAJAJAUTO":       "BAJAJ-AUTO",   # hyphenated
    "BLUESTAR":        "BLUESTARCO",   # suffix added
    "ARVINDFA":        "ARVINDFASN",   # suffix added
    "DATAPATTERNSIND": "DATAPATTNS",   # truncated
    "JUBILANTPHARMA":  "JUBLPHARMA",   # truncated
    # Shorter NSE symbol on yfinance
    "BHARATDYNAM":     "BDL",          # Bharat Dynamics Ltd
    "CANARABANK":      "CANBK",        # Canara Bank
    "IDBIBANK":        "IDBI",         # IDBI Bank
    "CITYUNIONBANK":   "CUB",          # City Union Bank
    "TIMEXIND":        "TIMEX",        # Timex Group India
    "SHAILYENG":       "SHAILY",       # Shaily Engineering
    "MAITHANALLOYS":   "MAITHANALL",   # Maithan Alloys
    "PREMIEREXP":      "PREMIER",      # Premier Explosives (note: low liquidity)
    "SUNFLAGIRON":     "SUNFLAG",      # Sunflag Iron & Steel
    "KECIN":           "KERNEX",       # Kernex Microsystems
    "INDGLY":          "INDIAGLYCO",   # India Glycols
    "SAGARCEM":        "SAGCEM",       # Sagar Cements
    "GREATSHIP":       "GESHIP",       # Great Eastern Shipping
    # Stocks not available on yfinance — will fall back to DB snapshot change_1d_pct
    # "TATAMTRDVR"  — DVR shares not on yfinance
    # "PONDYOX"     — Pondy Oxides not available
    # "INDMED"      — Indraprastha Medical not available
    # "UJJIVANFIN"  — Ujjivan Financial not available
    # "HBLPOWER"    — HBL Engineering not available
    # "USHAMARTIN"  — Usha Martin not available
    # "APOLLOMICRO" — Apollo Micro Systems not available
    # "DHAMPURBIO"  — Dhampur Bio not available
    # "ROSSELTECHSYS"— Rossell Tech not available
    # "GUJAMBEXPORTS"— Gujarat Ambuja not available
    # "GYFTR"       — GYFTR Limited not available
}

_YF_SKIP: frozenset[str] = frozenset({
    # ETFs / index funds — not individual stocks, skip yfinance
    "LIQUID", "CASHIETF", "CPSEETF", "COMMOIETF", "GROWWLIQID",
    "LIQUIDPLUS", "LIQUIDADD", "LIQUIDCASE", "LIQUIDBETF",
    "LIQUID1", "LIQUIDBEES", "BANKBEES", "NIFTYBEES", "INFRAETF",
    "BHARAT22ETF", "AXISNIFTYIT", "ICICIGOLD", "SBIETFGOLD",
    "ICICIAUTO", "ICIALPHAETF", "TATANIFTYDIGITAL", "PSUBNKBEES",
    "ICICIB22",
    # Stocks confirmed not available on yfinance (use DB snapshot fallback)
    "TATAMTRDVR", "PONDYOX", "INDMED", "UJJIVANFIN", "HBLPOWER",
    "USHAMARTIN", "APOLLOMICRO", "DHAMPURBIO", "ROSSELTECHSYS",
    "GUJAMBEXPORTS", "GYFTR",
})


def _fetch_live_prices_yf(nse_symbols: list[str]) -> dict[str, float]:
    """Fetch latest prices from Yahoo Finance (.NS suffix). Best-effort.

    Applies _YF_TICKER_OVERRIDES for stocks whose yfinance ticker differs
    from the NSE symbol, and skips ETFs and stocks known to be unavailable.
    Returns a dict keyed by the ORIGINAL NSE symbol (not the yfinance ticker).
    """
    try:
        import yfinance as yf, math, warnings

        # Map NSE symbol → yfinance ticker; skip ETFs and unavailable stocks
        fetch_map: dict[str, str] = {}  # yf_ticker → nse_symbol (for result remapping)
        for nse_sym in nse_symbols:
            if nse_sym in _YF_SKIP:
                continue
            yf_ticker = _YF_TICKER_OVERRIDES.get(nse_sym, nse_sym)
            fetch_map[f"{yf_ticker}.NS"] = nse_sym

        prices: dict[str, float] = {}
        yf_tickers = list(fetch_map.keys())

        for i in range(0, len(yf_tickers), 60):
            chunk = yf_tickers[i : i + 60]
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    data = yf.download(chunk, period="2d", progress=False, auto_adjust=True)
                close = data.get("Close", None)
                if close is not None and not close.empty:
                    last = close.iloc[-1]
                    for yf_t in chunk:
                        nse_sym = fetch_map.get(yf_t)
                        if not nse_sym:
                            continue
                        val = last.get(yf_t)
                        if val is not None:
                            try:
                                fv = float(val)
                                if not math.isnan(fv):
                                    prices[nse_sym] = round(fv, 2)
                            except (TypeError, ValueError):
                                pass
            except Exception:
                pass
        return prices
    except ImportError:
        return {}


# ── Intraday markdown view (for terminal) ─────────────────────────────────────

def run_intraday_view(
    filter_signal: Optional[str] = None,
    live: bool = True,
    csv_path: Path = PORTFOLIO_CSV,
    db_path: Optional[Path] = None,
) -> str:
    """
    Return a Rich markdown string of the live portfolio dashboard.
    Also writes INTRADAY_REPORT HTML.

    filter_signal: None (all), 'BUY', 'SELL', 'HOLD', 'STRONG BUY'
    live: if True fetch intraday prices via yfinance
    """
    portfolio = _load_portfolio(csv_path)
    records, snap_date = _load_db_snapshot(db_path)
    db_norm = _build_db_norm(records)

    live_prices: dict[str, float] = {}
    if live and _is_market_hours():
        nse_syms = list({_BROKER_TO_NSE.get(s["broker"], s["broker"]) for s in portfolio})
        live_prices = _fetch_live_prices_yf(nse_syms)

    all_results = _analyse_portfolio(portfolio, records, db_norm, live_prices or None)
    results = list(all_results)

    if filter_signal:
        fs = filter_signal.upper()
        results = [r for r in results if r["composite"].upper() == fs]

    # Sort: STRONG BUY/BUY by inv_score desc, SELL by loss pct
    def _sort_key(r):
        order = {"STRONG BUY": 0, "BUY": 1, "HOLD": 2, "SELL": 3}
        return (order.get(r["composite"], 9), -(r["inv_score"] or 0))
    results.sort(key=_sort_key)

    metrics = _portfolio_broker_metrics(results, value_key="live_value")
    html_metrics = _portfolio_broker_metrics(all_results, value_key="live_value")
    total_cost  = metrics["total_cost"]
    total_live  = metrics["current_value"]
    total_upnl  = total_live - total_cost
    day_gain    = metrics["day_gain"]
    html_total_cost = html_metrics["total_cost"]
    html_total_live = html_metrics["current_value"]
    html_total_upnl = html_total_live - html_total_cost
    html_day_gain = html_metrics["day_gain"]

    now_ist = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(hours=5, minutes=30)
    mkt_status = "MARKET OPEN" if _is_market_hours() else "MARKET CLOSED"

    lines = [
        f"## 💼 My Portfolio — {mkt_status}",
        f"*{now_ist.strftime('%d %b %Y %H:%M')} IST  ·  Snapshot: {snap_date}  ·  {len(results)} holdings*",
        "",
        f"| KPI | Value |",
        f"|-----|-------|",
        f"| Amount Invested | ₹{total_cost:,.2f} |",
        f"| Current Value | ₹{total_live:,.2f} |",
        f"| Day's Gain | {'+'if day_gain>=0 else ''}₹{day_gain:,.2f} ({metrics['day_gain_pct']:+.2f}%) |",
        f"| Absolute Returns | {metrics['absolute_return_pct']:+.2f}% |",
        "",
    ]

    # Signal summary
    cats = {"STRONG BUY": 0, "BUY": 0, "HOLD": 0, "SELL": 0}
    for r in results:
        cats[r["composite"]] = cats.get(r["composite"], 0) + 1
    lines.append(
        f"**Signals:** 🟢 Strong Buy: {cats['STRONG BUY']} · "
        f"🟢 Buy: {cats['BUY']} · 🟡 Hold: {cats['HOLD']} · "
        f"🔴 Sell: {cats['SELL']}"
    )
    lines.append("")

    # Table
    lines.append("| Symbol | Company | CMP | Day% | P&L% | Signal | Stage | RS vs N500 | Sector |")
    lines.append("|--------|---------|-----|------|------|--------|-------|------------|--------|")
    for r in results[:60]:  # cap at 60 rows in terminal
        day_s   = f"{r['day_chg_pct']:+.1f}%" if r["day_chg_pct"] is not None else "-"
        pct_s   = f"{r['live_upnl_pct']:+.1f}%"
        stage_s = (r["stage"] or "N/A").replace("STAGE_", "S")
        rs_s    = _fmt_rs_nifty500(r.get("rs_nifty500"))
        sect_s  = (r["sector"] or "N/A")[:18]
        lines.append(
            f"| **{r['broker']}** | {r['company'][:22]} | ₹{r['live_cmp']:,.0f} "
            f"| {day_s} | {pct_s} | {r['composite']} | {stage_s} | {rs_s} | {sect_s} |"
        )

    if len(results) > 60:
        lines.append(f"*… and {len(results)-60} more — open HTML report for full view*")

    lines.extend([
        "",
        "---",
        f"*Open full report: `reports/latest/portfolio_intraday.html`*",
    ])

    # Write HTML
    _write_intraday_html(
        all_results,
        snap_date,
        html_total_cost,
        html_total_live,
        html_total_upnl,
        html_day_gain,
    )

    return "\n".join(lines)


# ── EOD comprehensive report ──────────────────────────────────────────────────

def run_eod_report(
    csv_path: Path = PORTFOLIO_CSV,
    db_path: Optional[Path] = None,
) -> dict:
    """Build full EOD analysis and write portfolio_analysis.html."""
    try:
        portfolio = _load_portfolio(csv_path)
        result = _load_db_snapshot(db_path)
        if isinstance(result, tuple):
            records, snap_date = result
        else:
            records, snap_date = {}, "N/A"
        if not records or snap_date == "N/A":
            return {
                "path": None,
                "success": False,
                "note": "PostgreSQL stage snapshot unavailable for portfolio monitor.",
            }
        db_norm = _build_db_norm(records)
        results = _analyse_portfolio(portfolio, records, db_norm, live_prices=None)
        transactions = _load_transactions()
        _write_eod_html(results, snap_date, transactions=transactions)
        return {"path": str(EOD_REPORT), "success": True, "note": f"Snapshot: {snap_date}"}
    except Exception as exc:
        return {"path": None, "success": False, "note": str(exc)}


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _sig_badge(sig: Optional[str]) -> str:
    colors = {
        "BUY":        "#22c55e",
        "STRONG BUY": "#16a34a",
        "SELL":       "#ef4444",
        "HOLD":       "#f59e0b",
    }
    c = colors.get(sig or "", "#6b7280")
    label = sig or "–"
    return (
        f'<span style="background:{c};color:white;padding:2px 7px;'
        f'border-radius:4px;font-size:11px;font-weight:700">{label}</span>'
    )


def _stage_badge(stage: Optional[str]) -> str:
    s = stage or "N/A"
    colors = {
        "STAGE_1": "#3b82f6", "STAGE_2": "#22c55e",
        "STAGE_3": "#f59e0b", "STAGE_4": "#ef4444", "N/A": "#9ca3af",
    }
    c = colors.get(s, "#9ca3af")
    label = s.replace("STAGE_", "S")
    return (
        f'<span style="background:{c};color:white;padding:1px 6px;'
        f'border-radius:3px;font-size:11px">{label}</span>'
    )


def _pct_color(pct: float) -> str:
    if pct >= 20:   return "#16a34a"
    if pct >= 0:    return "#15803d"
    if pct >= -15:  return "#ca8a04"
    return "#dc2626"


def _esc(value) -> str:
    return html.escape("" if value is None else str(value))


def _money(value: float, *, scale: float = 1.0, suffix: str = "") -> str:
    try:
        v = float(value or 0.0) / scale
    except (TypeError, ValueError):
        v = 0.0
    sign = "+" if v > 0 else ""
    return f"{sign}₹{v:,.2f}{suffix}"


def _plain_money(value: float, *, scale: float = 1.0, suffix: str = "") -> str:
    try:
        v = float(value or 0.0) / scale
    except (TypeError, ValueError):
        v = 0.0
    return f"₹{v:,.2f}{suffix}"


def _fmt_rs_nifty500(value: object) -> str:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{parsed:+.1f}"


def _tooltip_attrs(items: dict[str, object]) -> str:
    attrs = []
    for key, value in items.items():
        if value is None or value == "":
            continue
        safe_key = "".join(ch for ch in str(key).lower() if ch.isalnum() or ch == "-")
        attrs.append(f' data-tooltip-{safe_key}="{_esc(value)}"')
    return "".join(attrs)


_HTML_HEAD = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{refresh_meta}
<title>{title}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
      background:#f3f4f6;color:#1f2937}}
.container{{max-width:1800px;margin:0 auto;padding:20px}}
.header{{background:linear-gradient(135deg,#1e3a5f,#1a56db);color:white;
          padding:20px 28px;border-radius:12px;margin-bottom:20px}}
.header h1{{font-size:24px;font-weight:800}}
.header p{{opacity:.8;font-size:13px;margin-top:4px}}
.kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
           gap:10px;margin-bottom:20px}}
.kpi{{background:white;border-radius:10px;padding:14px 18px;
       box-shadow:0 1px 3px rgba(0,0,0,.1)}}
.kpi .lbl{{font-size:11px;text-transform:uppercase;color:#6b7280;font-weight:600}}
.kpi .val{{font-size:20px;font-weight:800;margin-top:3px}}
.kpi .sub{{font-size:11px;color:#9ca3af;margin-top:2px}}
#alertZone.alert-zone{{background:#111827;color:white;border-radius:10px;padding:16px 18px;
             margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,.14)}}
#alertZone h2{{font-size:16px;margin-bottom:4px}}
#alertZone .hint{{font-size:12px;color:#cbd5e1;margin-bottom:12px}}
#alertZone .alert-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}}
#alertZone .alert-card{{background:#1f2937;border:1px solid #374151;border-radius:8px;padding:10px}}
#alertZone .alert-card h3{{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#f8fafc;margin-bottom:8px}}
#alertZone .alert-list{{display:flex;flex-direction:column;gap:6px}}
#alertZone .alert-item{{display:grid;grid-template-columns:72px minmax(0,1fr) auto;gap:8px;align-items:center;
             width:100%;border:1px solid #374151;border-radius:6px;background:#0f172a;
             color:white;padding:7px 8px;text-align:left;cursor:pointer}}
#alertZone .alert-item:hover{{border-color:#93c5fd;background:#172554}}
#alertZone .alert-symbol{{font-weight:900;font-size:12px;color:#f8fafc}}
#alertZone .alert-detail{{font-size:11px;color:#dbeafe;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
#alertZone .alert-metric{{font-weight:900;font-size:12px;color:#f8fafc}}
#alertZone .alert-empty{{font-size:12px;color:#cbd5e1;padding:8px;border:1px dashed #475569;border-radius:6px}}
.section{{margin-bottom:28px}}
.sec-hdr{{padding:10px 18px;border-radius:8px 8px 0 0;
           display:flex;justify-content:space-between;align-items:center;gap:14px;cursor:pointer}}
.sec-hdr .title{{font-size:16px;font-weight:700;color:white}}
.sec-hdr .meta{{font-size:12px;color:rgba(255,255,255,.8)}}
.sec-hdr .title::before{{content:"▾";display:inline-block;margin-right:8px;font-size:13px}}
.section.collapsed .sec-hdr{{border-radius:8px}}
.section.collapsed .sec-hdr .title::before{{content:"▸"}}
.section.collapsed > :not(.sec-hdr){{display:none!important}}
.tbl-wrap{{overflow-x:auto;background:white;border:1px solid #e5e7eb;
            border-radius:0 0 8px 8px}}
.table-tools{{display:flex;align-items:center;justify-content:space-between;gap:10px;
              flex-wrap:wrap;background:#f8fafc;border:1px solid #e5e7eb;
              border-bottom:0;border-radius:8px 8px 0 0;padding:8px 10px}}
.table-search{{min-width:220px;max-width:420px;flex:1;border:1px solid #cbd5e1;
               border-radius:6px;padding:7px 9px;font-size:12px;background:white;color:#0f172a}}
.table-count{{font-size:11px;color:#64748b;font-weight:700;white-space:nowrap}}
.tbl-wrap.has-tools{{border-radius:0 0 8px 8px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
thead tr{{background:#f9fafb}}
th{{padding:6px 8px;text-align:left;font-size:11px;color:#6b7280;
    font-weight:600;text-transform:uppercase;border-bottom:1px solid #e5e7eb}}
th[data-sortable="1"]{{cursor:pointer;user-select:none;white-space:nowrap}}
th[data-sortable="1"]::after{{content:"↕";font-size:9px;margin-left:4px;color:#94a3b8}}
th.sort-asc::after{{content:"↑";color:#1e3a5f}}
th.sort-desc::after{{content:"↓";color:#1e3a5f}}
td{{padding:5px 8px;border-bottom:1px solid #f3f4f6;vertical-align:middle}}
tr:hover td{{background:#f0f9ff}}
.note{{background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;
        padding:12px 16px;margin-bottom:16px;font-size:12px;color:#1e40af}}
.narr{{font-size:11px;color:#6b7280;padding:2px 8px 6px 16px;
        background:#fafafa;border-bottom:1px solid #f3f4f6}}
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}}
.card{{background:white;border-radius:10px;padding:18px;
        box-shadow:0 1px 3px rgba(0,0,0,.1)}}
.card h3{{font-size:13px;font-weight:700;color:#374151;margin-bottom:10px}}
.card table td,.card table th{{padding:5px 8px}}
.control-bar{{display:grid;grid-template-columns:minmax(220px,2fr) repeat(3,minmax(130px,1fr)) auto;
              gap:10px;align-items:end;background:white;border:1px solid #e5e7eb;
              border-radius:8px;padding:12px;margin-bottom:12px}}
.control{{display:flex;flex-direction:column;gap:4px}}
.control label{{font-size:10px;text-transform:uppercase;color:#64748b;font-weight:700}}
.control input,.control select{{width:100%;border:1px solid #cbd5e1;border-radius:6px;
                                padding:7px 9px;font-size:12px;background:white;color:#0f172a}}
.control button{{border:1px solid #cbd5e1;border-radius:6px;padding:7px 11px;
                 background:#f8fafc;color:#0f172a;font-weight:700;cursor:pointer}}
.table-meta{{font-size:12px;color:#64748b;margin:0 0 10px 2px}}
.sortable{{cursor:pointer;user-select:none;white-space:nowrap}}
.sortable::after{{content:"↕";font-size:9px;margin-left:4px;color:#94a3b8}}
.sortable.sort-asc::after{{content:"↑";color:#1e3a5f}}
.sortable.sort-desc::after{{content:"↓";color:#1e3a5f}}
.visual-grid{{display:grid;grid-template-columns:1.2fr .8fr;gap:16px;margin-bottom:20px}}
.chart-card{{background:white;border-radius:10px;padding:16px;border:1px solid #e5e7eb;
             box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.chart-card h3{{font-size:13px;font-weight:800;color:#334155;margin-bottom:4px}}
.chart-card p{{font-size:11px;color:#64748b;margin-bottom:10px}}
.bubble-point{{transition:opacity .15s ease, transform .15s ease;cursor:crosshair;outline:none}}
.bubble-point:hover,.bubble-point:focus{{stroke:#0f172a;stroke-width:1.6px;filter:drop-shadow(0 3px 5px rgba(15,23,42,.24))}}
.bubble-point.hidden{{opacity:.08}}
.bubble-tooltip{{position:fixed;z-index:9999;display:none;pointer-events:none;
                 min-width:230px;max-width:330px;background:#111827;color:#f8fafc;
                 border:1px solid #334155;border-radius:8px;padding:10px 12px;
                 box-shadow:0 12px 30px rgba(15,23,42,.28);font-size:12px;line-height:1.45}}
.bubble-tooltip .bt-title{{font-weight:900;font-size:13px;margin-bottom:2px}}
.bubble-tooltip .bt-meta{{color:#cbd5e1;font-size:11px;margin-bottom:8px}}
.bubble-tooltip .bt-grid{{display:grid;grid-template-columns:1fr auto;gap:4px 12px;align-items:center}}
.bubble-tooltip .bt-label{{color:#94a3b8}}
.bubble-tooltip .bt-value{{font-weight:800;text-align:right;color:#fff}}
.heatmap{{display:grid;grid-template-columns:90px repeat(5,1fr);gap:4px;font-size:11px}}
.heatmap .head,.heatmap .row-lbl{{font-weight:800;color:#475569;padding:5px 4px}}
.heat-cell{{min-height:34px;border-radius:5px;padding:5px;text-align:center;
            color:#0f172a;background:#f1f5f9;border:1px solid #e2e8f0}}
.heat-cell .count{{display:block;font-weight:900;font-size:13px}}
.heat-cell .avg{{display:block;font-size:10px;color:#475569}}
.alert-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}
.alert-card{{background:white;border:1px solid #e5e7eb;border-radius:8px;padding:12px}}
.alert-card h3{{font-size:12px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px}}
.alert-list{{display:flex;flex-direction:column;gap:6px}}
.alert-item{{display:flex;justify-content:space-between;gap:8px;border-top:1px solid #f1f5f9;padding-top:6px;font-size:12px}}
.alert-item:first-child{{border-top:0;padding-top:0}}
.alert-item b{{color:#111827}}
.alert-item span{{color:#64748b;text-align:right}}
.portfolio-position-row{{cursor:pointer}}
.portfolio-position-row:hover td{{background:#eef6ff!important}}
.stock-detail-row{{display:none;background:#f8fafc}}
.stock-detail-row.open{{display:table-row}}
.stock-detail-cell{{padding:14px 18px!important;background:#f8fafc!important;border-bottom:1px solid #dbeafe!important}}
.detail-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}
.detail-card{{background:white;border:1px solid #e5e7eb;border-radius:8px;padding:12px}}
.detail-card h4{{font-size:12px;color:#334155;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px}}
.detail-card table td,.detail-card table th{{font-size:11px;padding:4px 5px}}
.detail-note{{font-size:11px;color:#475569;line-height:1.6;margin-top:8px}}
@media (max-width:900px){{
  .control-bar{{grid-template-columns:1fr 1fr}}
  .visual-grid{{grid-template-columns:1fr}}
}}
.footer{{text-align:center;color:#9ca3af;font-size:11px;
          margin-top:20px;padding:12px}}
</style>
</head>
<body><div class="container">
"""

_HTML_FOOT = """\
<div class="footer">{ts} &nbsp;|&nbsp; For informational purposes only. Not financial advice.</div>
<script>
(function(){{
  function norm(s){{ return (s || "").toString().toLowerCase().replace(/[,₹%]/g,"").trim(); }}
  function cellValue(row, idx){{
    const cell = row.children[idx];
    if (!cell) return "";
    const text = cell.innerText || cell.textContent || "";
    const numeric = Number(norm(text).replace(/[^0-9.+-]/g,""));
    return Number.isFinite(numeric) && /[0-9]/.test(text) ? numeric : text.toLowerCase();
  }}
  function dataRows(table){{
    const body = table.tBodies[0];
    if (!body) return [];
    const rows = Array.from(body.rows);
    const groups = [];
    for (let i = 0; i < rows.length; i++) {{
      const row = rows[i];
      if (row.classList.contains("narr") || row.classList.contains("stock-detail-row")) continue;
      const group = [row];
      let next = rows[i + 1];
      while (next && (next.classList.contains("narr") || next.classList.contains("stock-detail-row"))) {{
        group.push(next);
        i++;
        next = rows[i + 1];
      }}
      groups.push(group);
    }}
    return groups;
  }}
  function refreshCount(wrap, table){{
    const count = wrap.parentElement.querySelector(".table-count");
    if (!count) return;
    const groups = dataRows(table);
    const shown = groups.filter(g => g[0].style.display !== "none").length;
    count.textContent = shown + " / " + groups.length + " rows";
  }}
  function wireTable(table, index){{
    if (table.dataset.noEnhance === "1") return;
    if (table.dataset.enhanced === "1" || !table.tHead || !table.tBodies.length) return;
    table.dataset.enhanced = "1";
    const wrap = table.closest(".tbl-wrap");
    if (!wrap) return;
    wrap.classList.add("has-tools");
    const tools = document.createElement("div");
    tools.className = "table-tools";
    tools.innerHTML = '<input class="table-search" type="search" placeholder="Search this table" aria-label="Search table">' +
      '<span class="table-count"></span>';
    wrap.parentElement.insertBefore(tools, wrap);
    const search = tools.querySelector(".table-search");
    search.addEventListener("input", function(){{
      const q = norm(search.value);
      dataRows(table).forEach(function(group){{
        const text = norm(group.map(r => r.innerText).join(" "));
        const show = !q || text.includes(q);
        group.forEach(r => r.style.display = show ? "" : "none");
      }});
      refreshCount(wrap, table);
    }});
    Array.from(table.tHead.rows[0].cells).forEach(function(th, colIdx){{
      th.dataset.sortable = "1";
      th.addEventListener("click", function(){{
        const current = th.classList.contains("sort-asc") ? "asc" : th.classList.contains("sort-desc") ? "desc" : "";
        const next = current === "asc" ? "desc" : "asc";
        Array.from(table.tHead.querySelectorAll("th")).forEach(h => h.classList.remove("sort-asc","sort-desc"));
        th.classList.add(next === "asc" ? "sort-asc" : "sort-desc");
        const groups = dataRows(table);
        groups.sort(function(a,b){{
          const av = cellValue(a[0], colIdx);
          const bv = cellValue(b[0], colIdx);
          if (typeof av === "number" && typeof bv === "number") return next === "asc" ? av - bv : bv - av;
          return next === "asc" ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
        }});
        const body = table.tBodies[0];
        groups.forEach(g => g.forEach(r => body.appendChild(r)));
        refreshCount(wrap, table);
      }});
    }});
    refreshCount(wrap, table);
  }}
  function wireSections(){{
    document.querySelectorAll(".section > .sec-hdr").forEach(function(hdr){{
      if (hdr.dataset.collapseWired === "1") return;
      hdr.dataset.collapseWired = "1";
      hdr.setAttribute("title", "Click to collapse or expand");
      hdr.addEventListener("click", function(evt){{
        if (evt.target.closest("a,button,input,select")) return;
        hdr.parentElement.classList.toggle("collapsed");
      }});
    }});
  }}
  function wireStockDetails(){{
    document.querySelectorAll(".portfolio-position-row").forEach(function(row){{
      if (row.dataset.detailWired === "1") return;
      row.dataset.detailWired = "1";
      row.setAttribute("title", "Click for portfolio, technical, and fundamental details");
      row.addEventListener("click", function(evt){{
        if (evt.target.closest("a,button,input,select")) return;
        const detail = document.querySelector('.stock-detail-row[data-detail-for="' + row.dataset.detailId + '"]');
        if (!detail) return;
        detail.classList.toggle("open");
      }});
    }});
  }}
  function escHtml(value){{
    return (value || "").toString().replace(/[&<>"']/g, function(ch){{
      return ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}})[ch];
    }});
  }}
  function wireBubbleTooltips(){{
    const points = document.querySelectorAll(".bubble-point[data-tooltip-title]");
    if (!points.length) return;
    let tip = document.querySelector(".bubble-tooltip");
    if (!tip) {{
      tip = document.createElement("div");
      tip.className = "bubble-tooltip";
      tip.setAttribute("role", "tooltip");
      document.body.appendChild(tip);
    }}
    function htmlFor(point){{
      const d = point.dataset;
      const rows = [
        ["Signal", d.tooltipSignal],
        ["Stage", d.tooltipStage],
        ["Sector", d.tooltipSector],
        ["Technical Score", d.tooltipTech],
        ["Fundamental Score", d.tooltipFund],
        ["Investment Score", d.tooltipInvestment],
        ["RS vs NIFTY 500", d.tooltipRsNifty500],
        ["P&amp;L", d.tooltipPnl],
        ["Value", d.tooltipValue]
      ].filter(function(item){{ return item[1] !== undefined && item[1] !== null && item[1] !== ""; }});
      return '<div class="bt-title">' + escHtml(d.tooltipTitle) + '</div>' +
        '<div class="bt-meta">' + escHtml(d.tooltipCompany || "") + '</div>' +
        '<div class="bt-grid">' + rows.map(function(item){{
          return '<span class="bt-label">' + item[0] + '</span>' +
            '<span class="bt-value">' + escHtml(item[1]) + '</span>';
        }}).join("") + '</div>';
    }}
    function move(evt){{
      const pad = 14;
      const gap = 12;
      tip.style.display = "block";
      const rect = tip.getBoundingClientRect();
      let x = evt.clientX + gap;
      let y = evt.clientY + gap;
      if (x + rect.width + pad > window.innerWidth) x = evt.clientX - rect.width - gap;
      if (y + rect.height + pad > window.innerHeight) y = evt.clientY - rect.height - gap;
      tip.style.left = Math.max(pad, x) + "px";
      tip.style.top = Math.max(pad, y) + "px";
    }}
    function show(evt){{
      const point = evt.currentTarget;
      tip.innerHTML = htmlFor(point);
      tip.style.display = "block";
      move(evt);
    }}
    points.forEach(function(point){{
      if (point.dataset.tooltipWired === "1") return;
      point.dataset.tooltipWired = "1";
      point.addEventListener("mouseenter", show);
      point.addEventListener("mousemove", move);
      point.addEventListener("mouseleave", function(){{ tip.style.display = "none"; }});
      point.addEventListener("focus", function(evt){{
        const rect = point.getBoundingClientRect();
        show({{currentTarget: point, clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2}});
      }});
      point.addEventListener("blur", function(){{ tip.style.display = "none"; }});
    }});
  }}
  function init(){{
    document.querySelectorAll(".tbl-wrap table").forEach(wireTable);
    wireSections();
    wireStockDetails();
    wireBubbleTooltips();
  }}
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
}})();
</script>
</div></body></html>
"""


# ── Intraday HTML ─────────────────────────────────────────────────────────────

def _write_intraday_html(
    results: list[dict],
    snap_date: str,
    total_cost: float,
    total_live: float,
    total_upnl: float,
    day_gain: float,
) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    now_ist = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(hours=5, minutes=30)
    mkt_open = _is_market_hours()
    refresh_meta = '<meta http-equiv="refresh" content="60">' if mkt_open else ""

    cats = {"STRONG BUY": [], "BUY": [], "HOLD": [], "SELL": []}
    for r in results:
        cats.setdefault(r["composite"], cats["HOLD"]).append(r)

    # Portfolio-level P&L
    overall_pct = (total_live / total_cost - 1) * 100 if total_cost else 0
    broker_metrics = _portfolio_broker_metrics(results, value_key="live_value")
    max_gainer = broker_metrics.get("max_gainer")
    max_loser = broker_metrics.get("max_loser")

    def _mover_kpi(row: Optional[dict]) -> tuple[str, str]:
        if not row:
            return ("N/A", "")
        gain = float(row.get("broker_day_gain") or row.get("live_day_gain") or 0.0)
        pct = float(row.get("day_chg_pct") or 0.0)
        return (
            f"{_esc(row.get('broker'))} ₹{float(row.get('live_cmp') or row.get('cmp') or 0):,.2f}",
            f"{gain:+,.2f} ({pct:+.2f}%)",
        )

    max_gain_val, max_gain_sub = _mover_kpi(max_gainer)
    max_loss_val, max_loss_sub = _mover_kpi(max_loser)

    # KPIs
    kpi_html = ""
    kpi_data = [
        ("Amount Invested", f"₹{total_cost:,.2f}",       f"{len(results)} holdings"),
        ("Current Value",   f"₹{total_live:,.2f}",       snap_date),
        ("Day's Gain",      f"{'+'if day_gain>=0 else ''}₹{day_gain:,.2f}",
                             f"{broker_metrics['day_gain_pct']:+.2f}%"),
        ("Absolute Returns", f"{overall_pct:+.2f}%",     "broker-screen formula"),
        ("Max Gainer",      max_gain_val,                max_gain_sub),
        ("Max Loser",       max_loss_val,                max_loss_sub),
        ("Strong Buy",   str(len(cats["STRONG BUY"])), "stocks"),
        ("Buy",          str(len(cats["BUY"])),         "stocks"),
        ("Hold",         str(len(cats["HOLD"])),        "stocks"),
        ("Sell",         str(len(cats["SELL"])),        "stocks"),
    ]
    bg_map = {"Strong Buy": "#dcfce7", "Buy": "#f0fdf4", "Hold": "#fffbeb", "Sell": "#fef2f2"}
    vc_map = {"Total P&L": "#16a34a" if total_upnl >= 0 else "#dc2626",
              "Day's Gain": "#16a34a" if day_gain >= 0 else "#dc2626",
              "Absolute Returns": "#16a34a" if overall_pct >= 0 else "#dc2626",
              "Max Gainer": "#16a34a",
              "Max Loser": "#dc2626"}
    for lbl, val, sub in kpi_data:
        bg = bg_map.get(lbl, "white")
        vc = vc_map.get(lbl, "#111827")
        kpi_html += (
            f'<div class="kpi" style="background:{bg}">'
            f'<div class="lbl">{lbl}</div>'
            f'<div class="val" style="color:{vc}">{val}</div>'
            f'<div class="sub">{sub}</div></div>'
        )

    def _alert_item(r: dict, detail: str, metric: str) -> str:
        return (
            f'<button type="button" class="alert-item" data-alert-symbol="{_esc(r["broker"])}" '
            f'onclick="focusHolding(\'{_esc(r["broker"])}\')">'
            f'<span class="alert-symbol">{_esc(r["broker"])}</span>'
            f'<span class="alert-detail">{_esc(detail)}</span>'
            f'<span class="alert-metric">{_esc(metric)}</span>'
            "</button>"
        )

    def _alert_card(title: str, rows: list[tuple[dict, str, str]]) -> str:
        if rows:
            items = "".join(_alert_item(r, detail, metric) for r, detail, metric in rows[:5])
        else:
            items = '<div class="alert-empty">No current alerts</div>'
        return f'<div class="alert-card"><h3>{_esc(title)}</h3><div class="alert-list">{items}</div></div>'

    sharp_rows = sorted(
        [r for r in results if abs(float(r.get("day_chg_pct") or 0)) >= 3.0],
        key=lambda r: abs(float(r.get("day_chg_pct") or 0)),
        reverse=True,
    )
    risk_rows = sorted(
        [
            r for r in results
            if r["composite"] == "SELL" or r["stage"] == "STAGE_4" or float(r.get("live_upnl_pct") or 0) <= -15.0
        ],
        key=lambda r: (r["composite"] != "SELL", float(r.get("live_upnl_pct") or 0)),
    )
    watch_rows = sorted(
        [
            r for r in results
            if float(r.get("rs_nifty500") or 0) < -10
            or float(r.get("tech_score") or 100) < 40
        ],
        key=lambda r: float(r.get("rs_nifty500") or 0),
    )
    high_value_rows = sorted(
        [
            r for r in results
            if float(r.get("live_value") or 0) >= 100000
            and abs(float(r.get("day_chg_pct") or 0)) >= 2.0
        ],
        key=lambda r: abs(float(r.get("day_chg_pct") or 0)) * float(r.get("live_value") or 0),
        reverse=True,
    )

    alert_html = f"""
    <div id="alertZone" class="alert-zone">
      <h2>Alert Zone</h2>
      <div class="hint">Click a symbol to filter the holdings table. Thresholds: day move ±3%, loss ≤ -15%, RS vs NIFTY 500 &lt; -10, high-value ≥ ₹1L with ±2% move.</div>
      <div class="alert-grid">
        {_alert_card("Sharp Movers", [(r, r["company"][:28], f'{float(r.get("day_chg_pct") or 0):+.1f}%') for r in sharp_rows])}
        {_alert_card("Risk Alerts", [(r, f'{r["composite"]} · {r["stage"]}', f'{float(r.get("live_upnl_pct") or 0):+.1f}%') for r in risk_rows])}
        {_alert_card("Watch Alerts", [(r, f'RS vs N500 {_fmt_rs_nifty500(r.get("rs_nifty500"))} · Tech {float(r.get("tech_score") or 0):.0f}', r["stage"]) for r in watch_rows])}
        {_alert_card("High-Value Moves", [(r, f'₹{float(r.get("live_value") or 0)/100000:.2f}L position', f'{float(r.get("day_chg_pct") or 0):+.1f}%') for r in high_value_rows])}
      </div>
    </div>
    """

    # Intraday movers table — all stocks sorted by day% then signal
    def _day_sort(r):
        order = {"STRONG BUY": 0, "BUY": 1, "HOLD": 2, "SELL": 3}
        return (order.get(r["composite"], 9), -(r["day_chg_pct"] or 0))
    sorted_results = sorted(results, key=_day_sort)

    rows_html = ""
    for idx, r in enumerate(sorted_results):
        day_s   = f"{r['day_chg_pct']:+.1f}%" if r["day_chg_pct"] is not None else "—"
        day_c   = _pct_color(r["day_chg_pct"] or 0)
        pct_c   = _pct_color(r["live_upnl_pct"])
        stage_s = _stage_badge(r["stage"])
        rs_s    = _fmt_rs_nifty500(r.get("rs_nifty500"))
        inv_s   = f"{float(r['inv_score']):.0f}" if r["inv_score"] else "—"
        sector_s = (r["sector"] or "N/A")[:20]
        narr    = (r.get("narrative") or "")[:100]
        stage_raw = r["stage"] or "N/A"
        search_text = " ".join(
            str(v or "")
            for v in (r["broker"], r["company"], r.get("sector"), r["composite"], stage_raw)
        ).lower()

        fd = r.get("fund_det") or {}
        ratios = fd.get("ratios_summary", "")

        rows_html += f"""<tr class="holding-row" data-row-id="{idx}"
          data-search="{_esc(search_text)}"
          data-signal="{_esc(r['composite'])}"
          data-stage="{_esc(stage_raw)}"
          data-sector="{_esc(r['sector'] or 'N/A')}"
          data-broker="{_esc(r['broker'])}"
          data-company="{_esc(r['company'])}"
          data-cmp="{float(r['live_cmp'] or 0):.4f}"
          data-day="{float(r['day_chg_pct'] or 0):.4f}"
          data-pnl="{float(r['live_upnl_pct'] or 0):.4f}"
          data-value="{float(r['live_value'] or 0):.4f}"
          data-rs-nifty500="{float(r['rs_nifty500'] or 0):.4f}"
          data-inv="{float(r['inv_score'] or 0):.4f}">
          <td><strong>{r['broker']}</strong></td>
          <td style="font-size:12px">{r['company'][:30]}</td>
          <td style="text-align:right">₹{r['live_cmp']:,.1f}</td>
          <td style="text-align:right;color:{day_c};font-weight:600">{day_s}</td>
          <td style="text-align:right;color:{pct_c};font-weight:600">
            {r['live_upnl_pct']:+.1f}%</td>
          <td style="text-align:right">₹{r['live_value']/1000:,.0f}K</td>
          <td>{_sig_badge(r['composite'])}</td>
          <td>{stage_s}</td>
          <td style="text-align:center">{rs_s}</td>
          <td style="text-align:center;font-weight:600">{inv_s}</td>
          <td style="font-size:11px">{sector_s}</td>
        </tr>
        <tr class="narr holding-narr" data-row-id="{idx}"><td colspan="11">{narr}
          {f'<span style="color:#555"> · {ratios}</span>' if ratios else ''}</td></tr>"""

    # Top movers today
    top_gainers = sorted(
        [r for r in results if r["day_chg_pct"] is not None],
        key=lambda x: -(x["day_chg_pct"] or 0),
    )[:5]
    top_losers = sorted(
        [r for r in results if r["day_chg_pct"] is not None],
        key=lambda x: (x["day_chg_pct"] or 0),
    )[:5]

    def _mover_rows(lst, positive):
        html = ""
        for r in lst:
            c = "#16a34a" if positive else "#dc2626"
            html += (
                f"<tr><td><strong>{r['broker']}</strong></td>"
                f"<td>{r['company'][:28]}</td>"
                f"<td style='text-align:right'>₹{r['live_cmp']:,.1f}</td>"
                f"<td style='text-align:right;color:{c};font-weight:600'>"
                f"{r['day_chg_pct']:+.1f}%</td>"
                f"<td>{_sig_badge(r['composite'])}</td></tr>"
            )
        return html or "<tr><td colspan='5' style='color:#9ca3af'>No data yet</td></tr>"

    signals = ["STRONG BUY", "BUY", "HOLD", "SELL"]
    stages = sorted({str(r.get("stage") or "N/A") for r in results})
    sectors = sorted({str(r.get("sector") or "N/A") for r in results})
    signal_options = "".join(f'<option value="{_esc(s)}">{_esc(s)}</option>' for s in signals)
    stage_options = "".join(f'<option value="{_esc(s)}">{_esc(s.replace("STAGE_", "S"))}</option>' for s in stages)
    sector_options = "".join(f'<option value="{_esc(s)}">{_esc(s)}</option>' for s in sectors)

    def _bubble_svg(rows: list[dict]) -> str:
        if not rows:
            return "<svg id='portfolioBubbleChart' viewBox='0 0 640 260'></svg>"
        pnl_values = [float(r.get("live_upnl_pct") or 0) for r in rows]
        min_pnl = min(-30.0, min(pnl_values))
        max_pnl = max(80.0, max(pnl_values))
        if max_pnl == min_pnl:
            max_pnl = min_pnl + 1
        max_value = max(float(r.get("live_value") or 0) for r in rows) or 1
        color_map = {
            "STRONG BUY": "#16a34a",
            "BUY": "#22c55e",
            "HOLD": "#f59e0b",
            "SELL": "#ef4444",
        }
        parts = [
            '<svg id="portfolioBubbleChart" viewBox="0 0 640 260" role="img" aria-label="Portfolio bubble chart">',
            '<line x1="54" y1="210" x2="610" y2="210" stroke="#cbd5e1"/>',
            '<line x1="54" y1="24" x2="54" y2="210" stroke="#cbd5e1"/>',
            '<text x="300" y="248" text-anchor="middle" font-size="11" fill="#64748b">Investment Score</text>',
            '<text x="16" y="126" text-anchor="middle" font-size="11" fill="#64748b" transform="rotate(-90 16 126)">P&L %</text>',
        ]
        for idx, r in enumerate(rows):
            inv = max(0.0, min(100.0, float(r.get("inv_score") or 0)))
            pnl = float(r.get("live_upnl_pct") or 0)
            x = 54 + (inv / 100.0) * 556
            y = 210 - ((pnl - min_pnl) / (max_pnl - min_pnl)) * 186
            radius = 5 + min(18, (float(r.get("live_value") or 0) / max_value) * 18)
            color = color_map.get(str(r.get("composite") or ""), "#64748b")
            label = f"{r['broker']} {pnl:+.1f}% Inv {inv:.0f}"
            tooltip = _tooltip_attrs({
                "title": r.get("broker"),
                "company": r.get("company"),
                "signal": r.get("composite"),
                "stage": str(r.get("stage") or "N/A").replace("STAGE_", "S"),
                "sector": r.get("sector") or "N/A",
                "tech": f"{float(r.get('tech_score') or 0):.0f}",
                "fund": f"{float((r.get('efund_sc') or r.get('fund_score') or r.get('inv_score') or 0)):.0f}",
                "investment": f"{inv:.0f}",
                "rs-nifty500": _fmt_rs_nifty500(r.get("rs_nifty500")),
                "pnl": f"{pnl:+.1f}%",
                "value": _plain_money(float(r.get("live_value") or 0)),
            })
            parts.append(
                f'<circle class="bubble-point" data-row-id="{idx}" tabindex="0" '
                f'aria-label="{_esc(label)}"{tooltip} cx="{x:.1f}" cy="{y:.1f}" '
                f'r="{radius:.1f}" fill="{color}" opacity="0.72"><title>{_esc(label)}</title></circle>'
            )
        parts.append("</svg>")
        return "".join(parts)

    heatmap_stages = ["STAGE_1", "STAGE_2", "STAGE_3", "STAGE_4", "N/A"]
    heatmap_html = '<div id="portfolioHeatmap" class="heatmap" aria-label="Signal by stage heatmap">'
    heatmap_html += '<div class="head">Signal</div>' + "".join(
        f'<div class="head">{_esc(s.replace("STAGE_", "S"))}</div>' for s in heatmap_stages
    )
    for sig in signals:
        heatmap_html += f'<div class="row-lbl">{_esc(sig)}</div>'
        for stage in heatmap_stages:
            heatmap_html += (
                f'<div class="heat-cell" data-signal="{_esc(sig)}" data-stage="{_esc(stage)}">'
                '<span class="count">0</span><span class="avg">Inv --</span></div>'
            )
    heatmap_html += "</div>"

    controls_html = f"""
    <div class="control-bar" aria-label="Holdings table controls">
      <div class="control">
        <label for="holdingsSearch">Search</label>
        <input id="holdingsSearch" type="search" placeholder="Symbol, company, sector, signal">
      </div>
      <div class="control">
        <label for="signalFilter">Signal</label>
        <select id="signalFilter"><option value="">All signals</option>{signal_options}</select>
      </div>
      <div class="control">
        <label for="stageFilter">Stage</label>
        <select id="stageFilter"><option value="">All stages</option>{stage_options}</select>
      </div>
      <div class="control">
        <label for="sectorFilter">Sector</label>
        <select id="sectorFilter"><option value="">All sectors</option>{sector_options}</select>
      </div>
      <div class="control">
        <label>&nbsp;</label>
        <button type="button" id="resetPortfolioFilters">Reset</button>
      </div>
    </div>
    <div id="visibleHoldingsCount" class="table-meta">{len(results)} of {len(results)} holdings visible</div>
    """

    visuals_html = f"""
    <div class="visual-grid">
      <div class="chart-card">
        <h3>Bubble Chart</h3>
        <p>X-axis is investment score, Y-axis is P&amp;L %, and bubble size is market value.</p>
        {_bubble_svg(sorted_results)}
      </div>
      <div class="chart-card">
        <h3>Signal Heatmap</h3>
        <p>Visible holdings grouped by composite signal and Weinstein stage.</p>
        {heatmap_html}
      </div>
    </div>
    """

    body = f"""
    <div class="header">
      <h1>💼 My Portfolio — Live Dashboard</h1>
      <p>{now_ist.strftime('%d %b %Y %H:%M')} IST &nbsp;|&nbsp;
         {mkt_open and 'MARKET OPEN ● Auto-refresh 60s' or 'MARKET CLOSED'} &nbsp;|&nbsp;
         Snapshot: {snap_date} &nbsp;|&nbsp; {len(results)} holdings</p>
    </div>

    <div class="kpi-grid">{kpi_html}</div>

    {alert_html}

    {visuals_html}

    <div class="two-col">
      <div class="card">
        <h3>📈 Top Gainers Today</h3>
        <table class="sortable-table" data-no-enhance="1"><thead><tr><th class="sortable" data-sort-key="broker">Symbol</th><th class="sortable" data-sort-key="company">Company</th><th class="sortable" data-sort-key="cmp">CMP</th>
          <th class="sortable" data-sort-key="day">Day%</th><th class="sortable" data-sort-key="signal">Signal</th></tr></thead>
        <tbody>{_mover_rows(top_gainers, True)}</tbody></table>
      </div>
      <div class="card">
        <h3>📉 Top Losers Today</h3>
        <table class="sortable-table" data-no-enhance="1"><thead><tr><th class="sortable" data-sort-key="broker">Symbol</th><th class="sortable" data-sort-key="company">Company</th><th class="sortable" data-sort-key="cmp">CMP</th>
          <th class="sortable" data-sort-key="day">Day%</th><th class="sortable" data-sort-key="signal">Signal</th></tr></thead>
        <tbody>{_mover_rows(top_losers, False)}</tbody></table>
      </div>
    </div>

    <div class="note">
      <strong>Signal logic:</strong> Each stock evaluated on 7 strategies (Momentum ·
      CANSLIM · Minervini · Fundamental · Value/PnL · VCP · RS Strategy). Composite: ≥3 BUY → STRONG BUY ·
      ≥2 BUY &gt; SELL → BUY · ≥2 SELL &gt; BUY → SELL · else HOLD.
      Prices are 15-min delayed via Yahoo Finance during market hours.
    </div>

    <div class="section">
      <div class="sec-hdr" style="background:#1e3a5f">
        <span class="title">All Holdings — Intraday View</span>
        <span class="meta">{len(results)} stocks sorted by signal then day gain</span>
      </div>
      <div class="tbl-wrap">
        {controls_html}
        <table id="holdingsTable" data-no-enhance="1">
          <thead><tr>
            <th class="sortable" data-sort-key="broker">Symbol</th><th class="sortable" data-sort-key="company">Company</th><th class="sortable" data-sort-key="cmp">CMP</th>
            <th class="sortable" data-sort-key="day">Day%</th><th class="sortable" data-sort-key="pnl">P&amp;L%</th><th class="sortable" data-sort-key="value">Value</th>
            <th class="sortable" data-sort-key="signal">Signal</th><th class="sortable" data-sort-key="stage">Stage</th><th class="sortable" data-sort-key="rs_nifty500">RS vs NIFTY 500</th><th class="sortable" data-sort-key="inv">InvSc</th><th class="sortable" data-sort-key="sector">Sector</th>
          </tr></thead>
          <tbody id="holdingsRows">{rows_html}</tbody>
        </table>
      </div>
    </div>
    """

    script = """
<script>
(function () {
  const search = document.getElementById("holdingsSearch");
  const signal = document.getElementById("signalFilter");
  const stage = document.getElementById("stageFilter");
  const sector = document.getElementById("sectorFilter");
  const reset = document.getElementById("resetPortfolioFilters");
  const count = document.getElementById("visibleHoldingsCount");
  const tbody = document.getElementById("holdingsRows");
  const totalRows = () => Array.from(document.querySelectorAll("tr.holding-row"));

  function pairFor(row) {
    return document.querySelector('tr.holding-narr[data-row-id="' + row.dataset.rowId + '"]');
  }

  function matches(row) {
    const q = (search && search.value || "").trim().toLowerCase();
    const signalValue = signal && signal.value || "";
    const stageValue = stage && stage.value || "";
    const sectorValue = sector && sector.value || "";
    if (q && !(row.dataset.search || "").includes(q)) return false;
    if (signalValue && row.dataset.signal !== signalValue) return false;
    if (stageValue && row.dataset.stage !== stageValue) return false;
    if (sectorValue && row.dataset.sector !== sectorValue) return false;
    return true;
  }

  function updateHeatmap(visibleRows) {
    const cells = Array.from(document.querySelectorAll(".heat-cell"));
    const buckets = {};
    cells.forEach(cell => {
      const key = cell.dataset.signal + "|" + cell.dataset.stage;
      buckets[key] = {count: 0, invTotal: 0};
    });
    visibleRows.forEach(row => {
      const stageValue = ["STAGE_1", "STAGE_2", "STAGE_3", "STAGE_4"].includes(row.dataset.stage)
        ? row.dataset.stage
        : "N/A";
      const key = row.dataset.signal + "|" + stageValue;
      if (!buckets[key]) buckets[key] = {count: 0, invTotal: 0};
      buckets[key].count += 1;
      buckets[key].invTotal += Number(row.dataset.inv || 0);
    });
    cells.forEach(cell => {
      const key = cell.dataset.signal + "|" + cell.dataset.stage;
      const data = buckets[key] || {count: 0, invTotal: 0};
      const avg = data.count ? data.invTotal / data.count : 0;
      cell.querySelector(".count").textContent = String(data.count);
      cell.querySelector(".avg").textContent = data.count ? "Inv " + avg.toFixed(0) : "Inv --";
      const alpha = Math.min(0.92, 0.10 + data.count / Math.max(1, visibleRows.length) * 3.2);
      const colors = {"STRONG BUY": "22,101,52", "BUY": "34,197,94", "HOLD": "245,158,11", "SELL": "239,68,68"};
      cell.style.background = data.count ? "rgba(" + (colors[cell.dataset.signal] || "100,116,139") + "," + alpha + ")" : "#f8fafc";
      cell.style.color = alpha > 0.42 ? "white" : "#0f172a";
    });
  }

  function applyPortfolioFilters() {
    const rows = totalRows();
    const visible = [];
    rows.forEach(row => {
      const show = matches(row);
      const narr = pairFor(row);
      row.style.display = show ? "" : "none";
      if (narr) narr.style.display = show ? "" : "none";
      if (show) visible.push(row);
    });
    document.querySelectorAll(".bubble-point").forEach(point => {
      const row = document.querySelector('tr.holding-row[data-row-id="' + point.dataset.rowId + '"]');
      point.classList.toggle("hidden", !row || row.style.display === "none");
    });
    if (count) count.textContent = visible.length + " of " + rows.length + " holdings visible";
    updateHeatmap(visible);
  }

  window.focusHolding = function focusHolding(symbol) {
    if (search) search.value = symbol || "";
    if (signal) signal.value = "";
    if (stage) stage.value = "";
    if (sector) sector.value = "";
    applyPortfolioFilters();
    const table = document.getElementById("holdingsTable");
    if (table) table.scrollIntoView({behavior: "smooth", block: "start"});
  };

  function valueFor(row, key) {
    const attrKey = key.replace(/_/g, "-");
    const raw = row.dataset[key] ?? row.getAttribute("data-" + attrKey) ?? "";
    if (["cmp", "day", "pnl", "value", "rs_nifty500", "inv"].includes(key)) {
      return Number(raw || 0);
    }
    return String(raw || "").toLowerCase();
  }

  function sortHoldings(key, dir) {
    const pairs = totalRows().map(row => ({row, narr: pairFor(row)}));
    pairs.sort((a, b) => {
      const av = valueFor(a.row, key);
      const bv = valueFor(b.row, key);
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
    pairs.forEach(pair => {
      tbody.appendChild(pair.row);
      if (pair.narr) tbody.appendChild(pair.narr);
    });
  }

  document.querySelectorAll("#holdingsTable th.sortable").forEach(th => {
    th.addEventListener("click", () => {
      const desc = !th.classList.contains("sort-desc");
      document.querySelectorAll("#holdingsTable th.sortable").forEach(other => other.classList.remove("sort-asc", "sort-desc"));
      th.classList.add(desc ? "sort-desc" : "sort-asc");
      sortHoldings(th.dataset.sortKey, desc ? -1 : 1);
      applyPortfolioFilters();
    });
  });

  document.querySelectorAll("table.sortable-table th.sortable").forEach(th => {
    th.addEventListener("click", () => {
      const table = th.closest("table");
      const tbody = table && table.querySelector("tbody");
      if (!tbody) return;
      const idx = Array.from(th.parentElement.children).indexOf(th);
      const desc = !th.classList.contains("sort-desc");
      table.querySelectorAll("th.sortable").forEach(other => other.classList.remove("sort-asc", "sort-desc"));
      th.classList.add(desc ? "sort-desc" : "sort-asc");
      const rows = Array.from(tbody.querySelectorAll("tr"));
      rows.sort((a, b) => {
        const av = (a.children[idx] && a.children[idx].textContent || "").trim();
        const bv = (b.children[idx] && b.children[idx].textContent || "").trim();
        const an = Number(av.replace(/[^0-9.-]/g, ""));
        const bn = Number(bv.replace(/[^0-9.-]/g, ""));
        if (!Number.isNaN(an) && !Number.isNaN(bn)) return (an - bn) * (desc ? -1 : 1);
        return av.localeCompare(bv) * (desc ? -1 : 1);
      });
      rows.forEach(row => tbody.appendChild(row));
    });
  });

  [search, signal, stage, sector].forEach(el => {
    if (el) el.addEventListener("input", applyPortfolioFilters);
    if (el) el.addEventListener("change", applyPortfolioFilters);
  });
  if (reset) {
    reset.addEventListener("click", () => {
      if (search) search.value = "";
      if (signal) signal.value = "";
      if (stage) stage.value = "";
      if (sector) sector.value = "";
      applyPortfolioFilters();
    });
  }
  applyPortfolioFilters();
})();
</script>
"""

    ts = now_ist.strftime("%Y-%m-%d %H:%M IST")
    html = (
        _HTML_HEAD.format(
            title="Portfolio Live Dashboard",
            refresh_meta=refresh_meta,
        )
        + body
        + script
        + _HTML_FOOT.format(ts=ts)
    )
    INTRADAY_REPORT.write_text(html, encoding="utf-8")


# ── EOD HTML ──────────────────────────────────────────────────────────────────

def _fund_color(score: Optional[float]) -> str:
    """Map a 0-100 fundamental/investment score to a CSS background colour."""
    if score is None:
        return "#e5e7eb"
    s = float(score)
    if s >= 75:  return "#16a34a"
    if s >= 65:  return "#22c55e"
    if s >= 55:  return "#86efac"
    if s >= 45:  return "#fde68a"
    if s >= 35:  return "#fb923c"
    return "#ef4444"


def _fund_text_color(score: Optional[float]) -> str:
    if score is None:
        return "#6b7280"
    s = float(score)
    return "white" if s >= 65 or s < 45 else "#1f2937"


def _build_heatmap_section(results: list[dict]) -> str:
    """
    Build complementary heat-map visualisations:

    1. Signal × Stage grid   – avg fund score + count per cell, coloured heat.
    2. Bubble scatter         – Tech Score (X) × Fund Score (Y), bubble size =
                                portfolio value, colour = signal.  Pure SVG.
    """
    import math as _math

    SIGS   = ["STRONG BUY", "BUY", "HOLD", "SELL"]
    STAGES = ["STAGE_1", "STAGE_2", "STAGE_4", "Untracked"]
    STAGE_LABELS = {
        "STAGE_1": "Stage 1", "STAGE_2": "Stage 2",
        "STAGE_4": "Stage 4", "Untracked": "ETF / Untracked",
    }
    SIG_COLORS = {
        "STRONG BUY": "#166534", "BUY": "#22c55e",
        "HOLD": "#d97706", "SELL": "#dc2626",
    }

    # ── 1. Build cell data for Signal × Stage grid ──────────────────────────
    from collections import defaultdict
    cell: dict = defaultdict(list)        # (sig, stage) → [fund_scores]
    cell_stocks: dict = defaultdict(list) # (sig, stage) → [broker names]

    # Only include equity stocks with full data in the signal grid
    # ETFs and untracked go into the "Untracked" bucket
    for r in results:
        sig      = r["composite"]
        coverage = r.get("coverage", "full")
        stage    = r["stage"] or "N/A"
        if coverage in ("etf", "untracked") or stage not in ("STAGE_1","STAGE_2","STAGE_3","STAGE_4"):
            stage = "Untracked"
        elif stage == "STAGE_3":
            stage = "STAGE_4"   # very few Stage 3; fold into Stage 4 bucket
        fs = r.get("efund_sc") or r.get("inv_score")
        # Don't include synthetic 50.0 fallbacks for untracked stocks
        if coverage == "full" and fs:
            cell[(sig, stage)].append(float(fs))
        elif coverage == "full":
            cell[(sig, stage)].append(50.0)
        else:
            cell[(sig, "Untracked")].append(None)
        cell_stocks[(sig, stage)].append(r["broker"])

    def _cell_html(sig, stage):
        scores  = cell.get((sig, stage), [])
        brokers = cell_stocks.get((sig, stage), [])
        cnt = len(brokers)   # use broker count (includes Nones for untracked)
        if cnt == 0:
            return '<td style="background:#f9fafb;color:#d1d5db;text-align:center;padding:10px 8px;border:1px solid #e5e7eb">—</td>'

        tip = ", ".join(brokers[:12]) + ("…" if len(brokers) > 12 else "")

        # Untracked column: no fundamental scoring, grey style
        if stage == "Untracked":
            return (
                f'<td title="ETF / not in tracked universe: {tip}" '
                f'style="background:#f3f4f6;color:#6b7280;text-align:center;'
                f'padding:10px 8px;border:1px solid #e5e7eb;cursor:default;min-width:90px">'
                f'<div style="font-size:18px;font-weight:800">{cnt}</div>'
                f'<div style="font-size:11px">ETF/Untracked</div>'
                f'</td>'
            )

        real_scores = [s for s in scores if s is not None]
        if not real_scores:
            return '<td style="background:#f9fafb;color:#d1d5db;text-align:center;padding:10px 8px;border:1px solid #e5e7eb">—</td>'
        avg = sum(real_scores) / len(real_scores)
        bg  = _fund_color(avg)
        tc  = _fund_text_color(avg)
        return (
            f'<td title="{tip}" style="background:{bg};color:{tc};text-align:center;'
            f'padding:10px 8px;border:1px solid #e5e7eb;cursor:default;min-width:90px">'
            f'<div style="font-size:18px;font-weight:800">{cnt}</div>'
            f'<div style="font-size:11px;opacity:.85">FS avg {avg:.0f}</div>'
            f'</td>'
        )

    grid_rows = ""
    for sig in SIGS:
        sc = SIG_COLORS[sig]
        row_total = sum(len(cell[(sig, stg)]) for stg in STAGES)
        grid_rows += (
            f'<tr><td style="background:{sc};color:white;font-weight:700;'
            f'padding:10px 12px;white-space:nowrap">{sig}'
            f'<span style="opacity:.65;font-size:11px;margin-left:6px">({row_total})</span></td>'
        )
        for stg in STAGES:
            grid_rows += _cell_html(sig, stg)
        grid_rows += "</tr>"

    stage_header = "".join(
        f'<th style="background:#1e3a5f;color:white;padding:8px 12px;text-align:center">'
        f'{STAGE_LABELS[s]}</th>'
        for s in STAGES
    )
    grid_html = f"""
    <table style="border-collapse:collapse;width:100%">
      <thead><tr>
        <th style="background:#1e3a5f;color:white;padding:8px 12px;text-align:left">Signal</th>
        {stage_header}
      </tr></thead>
      <tbody>{grid_rows}</tbody>
    </table>
    <p style="font-size:11px;color:#6b7280;margin-top:6px">
      Cell = stock count · FS = avg Fundamental Score · colour: 🔴 weak → 🟡 avg → 🟢 strong · hover for tickers
    </p>"""

    # ── 2. Bubble scatter SVG (full width) ─────────────────────────────────
    W, H     = 900, 440
    PAD      = 56
    plot_w   = W - PAD * 2
    plot_h   = H - PAD * 2

    def _to_x(tech):
        return PAD + (float(tech or 50) / 100.0) * plot_w

    def _to_y(fund):
        return PAD + plot_h - (float(fund or 50) / 100.0) * plot_h

    sig_fill = {
        "STRONG BUY": "#16a34a", "BUY": "#22c55e",
        "HOLD": "#f59e0b", "SELL": "#ef4444",
    }

    # Grid lines — separate X and Y loops to avoid label confusion
    grid_lines = ""
    for v in range(0, 101, 20):
        gx = _to_x(v)
        # Vertical grid line + X-axis label (bottom)
        grid_lines += (
            f'<line x1="{gx:.1f}" y1="{PAD}" x2="{gx:.1f}" y2="{PAD+plot_h}" '
            f'stroke="#e5e7eb" stroke-width="1"/>'
            f'<text x="{gx:.1f}" y="{PAD+plot_h+13}" text-anchor="middle" '
            f'font-size="10" fill="#9ca3af">{v}</text>'
        )
    for v in range(0, 101, 20):
        gy = _to_y(v)
        # Horizontal grid line + Y-axis label (left)
        grid_lines += (
            f'<line x1="{PAD}" y1="{gy:.1f}" x2="{PAD+plot_w}" y2="{gy:.1f}" '
            f'stroke="#e5e7eb" stroke-width="1"/>'
            f'<text x="{PAD-6}" y="{gy+4:.1f}" text-anchor="end" '
            f'font-size="10" fill="#9ca3af">{v}</text>'
        )

    # Diagonal guide (equal tech+fund): bottom-left (0,0) → top-right (100,100)
    grid_lines += (
        f'<line x1="{_to_x(0):.1f}" y1="{_to_y(0):.1f}" '
        f'x2="{_to_x(100):.1f}" y2="{_to_y(100):.1f}" '
        f'stroke="#d1d5db" stroke-width="1" stroke-dasharray="4 4"/>'
    )

    # Bubbles — only equity stocks with real data; ETF/untracked plotted separately
    bubble_items = []
    untracked_items = []
    for r in results:
        coverage = r.get("coverage", "full")
        tech = r.get("tech_score")
        fund = r.get("efund_sc") or r.get("inv_score")
        val  = r["value_mkt"]
        r_px = max(5.0, min(22.0, _math.sqrt(val / 5000)))

        if coverage in ("etf", "untracked") or not tech or not fund:
            untracked_items.append((r_px, r["broker"], val, coverage))
            continue

        tech = float(tech)
        fund = float(fund)
        cx   = _to_x(tech)
        cy   = _to_y(fund)
        fill = sig_fill.get(r["composite"], "#9ca3af")
        tip  = (f"{r['broker']} | {r['company'][:28]} | "
                f"Tech:{tech:.0f} Fund:{fund:.0f} | "
                f"{r['composite']} | P&L:{r['upnl_pct']:+.1f}%")
        tooltip = _tooltip_attrs({
            "title": r.get("broker"),
            "company": r.get("company"),
            "signal": r.get("composite"),
            "stage": str(r.get("stage") or "N/A").replace("STAGE_", "S"),
            "sector": r.get("sector") or "N/A",
            "tech": f"{tech:.0f}",
            "fund": f"{fund:.0f}",
            "investment": f"{float(r.get('inv_score') or 0):.0f}",
            "rs-nifty500": _fmt_rs_nifty500(r.get("rs_nifty500")),
            "pnl": f"{float(r.get('upnl_pct') or 0):+.1f}%",
            "value": _plain_money(float(val or 0)),
        })
        bubble_items.append((r_px, cx, cy, fill, tip, r["broker"], tooltip))

    bubble_items.sort(key=lambda x: -x[0])  # largest first (render behind)
    bubbles_svg = ""
    labels_svg  = ""
    for r_px, cx, cy, fill, tip, broker, tooltip in bubble_items:
        bubbles_svg += (
            f'<circle class="bubble-point" tabindex="0" aria-label="{_esc(tip)}"{tooltip} '
            f'cx="{cx:.1f}" cy="{cy:.1f}" r="{r_px:.1f}" '
            f'fill="{fill}" fill-opacity="0.75" stroke="white" stroke-width="0.8">'
            f'<title>{_esc(tip)}</title></circle>'
        )
        if r_px >= 10:
            labels_svg += (
                f'<text x="{cx:.1f}" y="{cy+3.5:.1f}" text-anchor="middle" '
                f'font-size="8" fill="white" font-weight="600" '
                f'style="pointer-events:none">{broker[:6]}</text>'
            )

    # Untracked / ETF stocks listed as a small note, not plotted
    untracked_note = ""
    if untracked_items:
        names = ", ".join(b for _, b, _, _ in sorted(untracked_items, key=lambda x: -x[2]))
        etf_cnt      = sum(1 for _, _, _, c in untracked_items if c == "etf")
        untrk_cnt    = sum(1 for _, _, _, c in untracked_items if c != "etf")
        untracked_note = (
            f'<p style="font-size:11px;color:#6b7280;margin-top:2px">'
            f'Not plotted ({etf_cnt} ETF, {untrk_cnt} not in tracked universe): {names}</p>'
        )

    # Axis labels
    axis_labels = (
        f'<text x="{PAD + plot_w/2:.0f}" y="{H-4}" text-anchor="middle" '
        f'font-size="12" fill="#374151" font-weight="600">Technical Score →</text>'
        f'<text x="14" y="{PAD + plot_h/2:.0f}" text-anchor="middle" '
        f'font-size="12" fill="#374151" font-weight="600" '
        f'transform="rotate(-90,14,{PAD + plot_h/2:.0f})">Fundamental Score →</text>'
    )

    # Legend
    legend_x = PAD + plot_w - 110
    legend_y  = PAD + 10
    legend_svg = f'<rect x="{legend_x}" y="{legend_y}" width="108" height="82" fill="white" fill-opacity=".9" rx="4" stroke="#e5e7eb"/>'
    for i, (lsig, lclr) in enumerate(sig_fill.items()):
        ly = legend_y + 14 + i * 17
        legend_svg += (
            f'<circle cx="{legend_x+12}" cy="{ly}" r="6" fill="{lclr}" fill-opacity=".8"/>'
            f'<text x="{legend_x+22}" y="{ly+4}" font-size="10" fill="#374151">{lsig}</text>'
        )

    scatter_block = f"""
    <div>
      <h3 style="font-size:13px;font-weight:700;color:#374151;margin:16px 0 8px">
        Bubble Map — Technical Score (X) vs Fundamental Score (Y)
        <span style="font-size:11px;font-weight:400;color:#6b7280;margin-left:8px">
          bubble size = portfolio value · hover for ticker detail · dashed = equal scores
        </span>
      </h3>
      <svg width="{W}" height="{H}" viewBox="0 0 {W} {H}"
           style="font-family:-apple-system,sans-serif;width:100%;display:block">
        {grid_lines}
        {bubbles_svg}
        {labels_svg}
        {axis_labels}
        {legend_svg}
      </svg>
      {untracked_note}
    </div>"""

    # ── 3. Per-stock heat strip ──────────────────────────────────────────────
    # Sort: signal order then inv_score desc
    sig_order = {"STRONG BUY": 0, "BUY": 1, "HOLD": 2, "SELL": 3}
    strip_data = sorted(
        results,
        key=lambda r: (sig_order.get(r["composite"], 9), -(float(r["inv_score"] or 0)))
    )

    def _heat_cell(val, lo=0, hi=100, fmt=None, reverse=False):
        """A mini coloured cell. reverse=True means low value = green."""
        if val is None:
            return '<td style="background:#f3f4f6;width:42px;text-align:center;font-size:10px;color:#9ca3af">—</td>'
        fv = float(val)
        norm = max(0.0, min(1.0, (fv - lo) / (hi - lo))) if hi > lo else 0.5
        if reverse:
            norm = 1.0 - norm
        # Interpolate red→yellow→green
        if norm < 0.5:
            r2 = 220
            g2 = int(norm * 2 * 159 + 60)
            b2 = 34 if norm < 0.25 else 34
            col = f"rgb({r2},{g2},{b2})"
            tc  = "white" if norm < 0.3 else "#1f2937"
        else:
            r2 = int((1 - norm) * 2 * 220)
            g2 = 163
            b2 = 74
            col = f"rgb({max(0,r2)},{g2},{b2})"
            tc  = "white" if norm > 0.7 else "#1f2937"
        label = fmt.format(fv) if fmt else f"{fv:.0f}"
        return (
            f'<td style="background:{col};color:{tc};width:42px;text-align:center;'
            f'font-size:10px;padding:2px 1px;white-space:nowrap">{label}</td>'
        )

    def _stage_cell(stage):
        colors = {"STAGE_1":"#3b82f6","STAGE_2":"#22c55e","STAGE_4":"#ef4444","N/A":"#9ca3af"}
        c = colors.get(stage or "N/A", "#9ca3af")
        label = (stage or "N/A").replace("STAGE_","S")
        return f'<td style="background:{c};color:white;width:36px;text-align:center;font-size:10px;padding:2px 3px">{label}</td>'

    def _sig_cell_strip(sig):
        c = {"STRONG BUY":"#166534","BUY":"#16a34a","HOLD":"#d97706","SELL":"#dc2626"}.get(sig,"#6b7280")
        short = {"STRONG BUY":"SBY","BUY":"BUY","HOLD":"HLD","SELL":"SEL"}.get(sig,"?")
        return f'<td style="background:{c};color:white;width:36px;text-align:center;font-size:10px;padding:2px 3px;font-weight:700">{short}</td>'

    _GREY_CELL = '<td style="background:#f3f4f6;color:#9ca3af;text-align:center;font-size:9px;padding:2px 3px">N/A</td>'

    strip_rows = ""
    for r in strip_data:
        pct      = r["upnl_pct"]
        coverage = r.get("coverage", "full")
        pct_c    = _fund_color(50 + pct * 0.6)
        pct_tc   = _fund_text_color(50 + pct * 0.6)

        co_short  = r["company"][:26]
        co_full   = r["company"]
        sym_td    = f'<td style="font-size:10px;padding:3px 5px;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{r["broker"]}</td>'
        co_td     = f'<td style="font-size:10px;padding:3px 5px;color:#6b7280;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{co_full}">{co_short}</td>'

        if coverage == "etf":
            strip_rows += (
                f'<tr style="background:#f0f9ff;opacity:.8">'
                f'<td style="font-size:10px;padding:3px 5px;font-weight:700;color:#0284c7">{r["broker"]}</td>'
                f'<td style="font-size:10px;padding:3px 5px;color:#6b7280;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{co_short}</td>'
                f'<td style="background:#e0f2fe;color:#0284c7;text-align:center;font-size:9px;padding:2px;font-weight:700">ETF</td>'
                f'<td style="background:#f3f4f6;color:#9ca3af;text-align:center;font-size:9px;padding:2px">—</td>'
                + _GREY_CELL * 6
                + f'<td style="background:{pct_c};color:{pct_tc};text-align:right;'
                f'font-size:10px;padding:2px 4px;font-weight:600">{pct:+.1f}%</td>'
                f'</tr>'
            )
        elif coverage == "untracked":
            strip_rows += (
                f'<tr style="opacity:.55">'
                f'<td style="font-size:10px;padding:3px 5px;font-weight:700;color:#9ca3af">{r["broker"]}</td>'
                f'<td style="font-size:10px;padding:3px 5px;color:#9ca3af;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{co_short}</td>'
                f'<td style="background:#fef3c7;color:#92400e;text-align:center;font-size:9px;padding:2px;font-weight:700">?</td>'
                f'<td style="background:#f3f4f6;color:#9ca3af;text-align:center;font-size:9px;padding:2px">—</td>'
                + _GREY_CELL * 6
                + f'<td style="background:{pct_c};color:{pct_tc};text-align:right;'
                f'font-size:10px;padding:2px 4px;font-weight:600">{pct:+.1f}%</td>'
                f'</tr>'
            )
        else:
            strip_rows += (
                f'<tr>'
                f'{sym_td}{co_td}'
                f'{_sig_cell_strip(r["composite"])}'
                f'{_stage_cell(r["stage"])}'
                f'{_heat_cell(r.get("efund_sc") or r.get("inv_score"), 10, 90)}'
                f'{_heat_cell(r.get("tech_score"), 10, 85)}'
                f'{_heat_cell(r.get("rs_nifty500"), -25, 25, fmt="{:+.1f}")}'
                f'{_heat_cell(r.get("canslim_sc"), 0, 30)}'
                f'{_heat_cell(r.get("minervini_sc"), 0, 30)}'
                f'{_heat_cell(r.get("inv_score"), 15, 70)}'
                f'<td style="background:{pct_c};color:{pct_tc};text-align:right;'
                f'font-size:10px;padding:2px 4px;font-weight:600">{pct:+.1f}%</td>'
                f'</tr>'
            )

    # Column widths (px): sym=80, company=180, sig=44, stg=40, fund=48, tech=48, rs=62, cans=44, minv=44, invsc=48, pnl=58 = 700px total
    strip_html = f"""
    <div style="overflow-x:auto;max-height:500px;overflow-y:auto;
                border:1px solid #e5e7eb;border-radius:6px">
      <table style="border-collapse:collapse;table-layout:fixed;width:700px;
                    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',monospace">
        <colgroup>
          <col style="width:80px">
          <col style="width:180px">
          <col style="width:44px"><col style="width:40px">
          <col style="width:48px"><col style="width:48px">
          <col style="width:62px"><col style="width:44px">
          <col style="width:44px"><col style="width:48px">
          <col style="width:58px">
        </colgroup>
        <thead style="position:sticky;top:0;z-index:1">
          <tr style="background:#1e3a5f;color:white;font-size:10px;text-transform:uppercase;letter-spacing:.3px">
            <th style="padding:5px 6px;text-align:left">Symbol</th>
            <th style="padding:5px 6px;text-align:left">Company</th>
            <th style="padding:5px 2px;text-align:center" title="Composite Signal">Sig</th>
            <th style="padding:5px 2px;text-align:center" title="Weinstein Stage">Stg</th>
            <th style="padding:5px 2px;text-align:center" title="Fundamental Score 0–100">Fund</th>
            <th style="padding:5px 2px;text-align:center" title="Technical Score 0–100">Tech</th>
            <th style="padding:5px 2px;text-align:center" title="Relative Strength vs NIFTY 500">RS vs N500</th>
            <th style="padding:5px 2px;text-align:center" title="CANSLIM /30">CANS</th>
            <th style="padding:5px 2px;text-align:center" title="Minervini /30">Minv</th>
            <th style="padding:5px 2px;text-align:center" title="Composite Investment Score">InvSc</th>
            <th style="padding:5px 4px;text-align:center" title="Unrealised P&L%">P&amp;L%</th>
          </tr>
        </thead>
        <tbody>{strip_rows}</tbody>
      </table>
    </div>
    <p style="font-size:11px;color:#6b7280;margin-top:6px">
      {len(results)} holdings · sorted by signal → investment score ·
      colour: 🔴 weak → 🟡 avg → 🟢 strong ·
      <span style="background:#e0f2fe;color:#0284c7;padding:1px 5px;border-radius:3px;font-size:10px">ETF</span> = ETF ·
      <span style="background:#fef3c7;color:#92400e;padding:1px 5px;border-radius:3px;font-size:10px">?</span> = not in tracked universe
    </p>"""

    # ── Assemble ─────────────────────────────────────────────────────────────
    return f"""
    <div style="background:white;border-radius:12px;padding:20px;
                box-shadow:0 1px 3px rgba(0,0,0,.1);margin-bottom:20px">
      <h2 style="font-size:16px;font-weight:700;color:#111827;margin-bottom:16px">
        📊 Portfolio Heat Maps
      </h2>

      <h3 style="font-size:13px;font-weight:700;color:#374151;margin-bottom:10px">
        Signal × Stage — avg Fundamental Score
        <span style="font-size:11px;font-weight:400;color:#6b7280;margin-left:8px">
          cell = stock count · FS = avg fundamental score · hover for tickers
        </span>
      </h3>
      {grid_html}

      {scatter_block}
    </div>"""


def _write_eod_html(results: list[dict], snap_date: str, *, transactions: list[dict] | None = None) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    transactions = transactions or []

    total_cost = sum(r["value_cost"] for r in results)
    total_mkt  = sum(r["value_mkt"]  for r in results)
    total_upnl = sum(r["upnl"]       for r in results)
    total_rpnl = sum(r["rpnl"]       for r in results)
    total_pnl = total_upnl + total_rpnl
    overall_pct = (total_mkt / total_cost - 1) * 100 if total_cost else 0
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0
    broker_metrics = _portfolio_broker_metrics(results)
    day_gain = broker_metrics["day_gain"]
    winners = sum(1 for r in results if r["upnl"] >= 0)
    losers = sum(1 for r in results if r["upnl"] < 0)
    cash_status = "Fully invested view"
    biggest_position = max(results, key=lambda r: r["value_mkt"], default=None)
    biggest_weight = (biggest_position["value_mkt"] / total_mkt * 100) if biggest_position and total_mkt else 0.0
    max_gainer = broker_metrics.get("max_gainer")
    max_loser = broker_metrics.get("max_loser")

    cats: dict[str, list] = {"STRONG BUY": [], "BUY": [], "HOLD": [], "SELL": []}
    for r in results:
        cats.setdefault(r["composite"], cats["HOLD"]).append(r)
    for k in ("STRONG BUY", "BUY"):
        cats[k].sort(key=lambda x: -(x["inv_score"] or 0))
    cats["SELL"].sort(key=lambda x: (x["upnl_pct"] or 0))
    cats["HOLD"].sort(key=lambda x: -(x["inv_score"] or 0))

    # KPIs
    def _mover_kpi(row: Optional[dict]) -> tuple[str, str]:
        if not row:
            return ("N/A", "")
        gain = float(row.get("broker_day_gain") or 0.0)
        pct = float(row.get("day_chg_pct") or 0.0)
        return (
            f"{_esc(row.get('broker'))} ₹{float(row.get('cmp') or 0):,.2f}",
            f"{gain:+,.2f} ({pct:+.2f}%)",
        )

    max_gain_val, max_gain_sub = _mover_kpi(max_gainer)
    max_loss_val, max_loss_sub = _mover_kpi(max_loser)
    kpi_items = [
        ("Amount Invested", f"₹{total_cost:,.2f}",         f"{len(results)} holdings"),
        ("Current Value",   f"₹{total_mkt:,.2f}",          snap_date),
        ("Day's Gain",      f"{'+' if day_gain >= 0 else ''}₹{day_gain:,.2f}",
                            f"{broker_metrics['day_gain_pct']:+.2f}%"),
        ("Absolute Returns", f"{overall_pct:+.2f}%",       "broker-screen formula"),
        ("Unrealised P&L", f"{'+'if total_upnl>=0 else ''}₹{total_upnl/100000:.2f}L",
                           f"{overall_pct:+.1f}%"),
        ("Realised P&L",   f"₹{total_rpnl/100000:.2f}L",   "booked"),
        ("Total P&L",      f"{'+'if total_pnl>=0 else ''}₹{total_pnl/100000:.2f}L",
                           f"{total_pnl_pct:+.1f}% on cost"),
        ("Max Gainer",      max_gain_val,                  max_gain_sub),
        ("Max Loser",       max_loss_val,                  max_loss_sub),
        ("Strong Buy",     str(len(cats["STRONG BUY"])),    "stocks"),
        ("Buy",            str(len(cats["BUY"])),           "stocks"),
        ("Hold",           str(len(cats["HOLD"])),          "stocks"),
        ("Sell",           str(len(cats["SELL"])),          "stocks"),
    ]
    bg_map2 = {
        "Strong Buy": "#dcfce7", "Buy": "#f0fdf4",
        "Hold": "#fffbeb", "Sell": "#fef2f2",
        "Unrealised P&L": "#f0fdf4" if total_upnl >= 0 else "#fef2f2",
        "Total P&L": "#f0fdf4" if total_pnl >= 0 else "#fef2f2",
        "Day's Gain": "#f0fdf4" if day_gain >= 0 else "#fef2f2",
        "Absolute Returns": "#f0fdf4" if overall_pct >= 0 else "#fef2f2",
    }
    vc_map2 = {
        "Unrealised P&L": "#16a34a" if total_upnl >= 0 else "#dc2626",
        "Total P&L": "#16a34a" if total_pnl >= 0 else "#dc2626",
        "Day's Gain": "#16a34a" if day_gain >= 0 else "#dc2626",
        "Absolute Returns": "#16a34a" if overall_pct >= 0 else "#dc2626",
        "Max Gainer": "#16a34a",
        "Max Loser": "#dc2626",
    }
    kpi_html = ""
    for lbl, val, sub in kpi_items:
        bg = bg_map2.get(lbl, "white")
        vc = vc_map2.get(lbl, "#111827")
        kpi_html += (
            f'<div class="kpi" style="background:{bg}">'
            f'<div class="lbl">{lbl}</div>'
            f'<div class="val" style="color:{vc}">{val}</div>'
            f'<div class="sub">{sub}</div></div>'
        )

    def _num(v, default: float = 0.0) -> float:
        try:
            return float(v if v is not None else default)
        except (TypeError, ValueError):
            return default

    def _alert_tags(r: dict) -> list[tuple[str, str]]:
        tags: list[tuple[str, str]] = []
        stage = r.get("stage") or "N/A"
        supertrend = r.get("supertrend") or ""
        tech = _num(r.get("tech_score"))
        inv = _num(r.get("inv_score"))
        rs_n500 = _num(r.get("rs_nifty500"))
        pnl_pct = _num(r.get("upnl_pct"))
        composite = r.get("composite") or "HOLD"
        coverage = r.get("coverage") or "full"
        if composite == "SELL" or stage == "STAGE_4" or supertrend == "BEARISH" or pnl_pct <= -20 or tech < 35:
            reason = []
            if composite == "SELL": reason.append("SELL signal")
            if stage == "STAGE_4": reason.append("Stage 4")
            if supertrend == "BEARISH": reason.append("bearish ST")
            if pnl_pct <= -20: reason.append(f"{pnl_pct:.1f}% loss")
            if tech < 35: reason.append(f"Tech {tech:.0f}")
            tags.append(("Exit / Reduce", ", ".join(reason[:3]) or "risk elevated"))
        if (stage == "STAGE_3" or rs_n500 < -10 or pnl_pct >= 50 or (r.get("buy_count", 0) and r.get("sell_count", 0))):
            reason = []
            if stage == "STAGE_3": reason.append("Stage 3")
            if rs_n500 < -10: reason.append(f"RS vs N500 {rs_n500:+.1f}")
            if pnl_pct >= 50: reason.append(f"{pnl_pct:.1f}% gain")
            if r.get("buy_count", 0) and r.get("sell_count", 0): reason.append("mixed votes")
            tags.append(("Hold / Watch", ", ".join(reason[:3]) or "monitor"))
        if composite in {"STRONG BUY", "BUY"} and stage == "STAGE_2" and (supertrend == "BULLISH" or inv >= 55):
            tags.append(("Add / Accumulate", f"Stage 2, {composite}, Inv {inv:.0f}"))
        if coverage != "full" or not r.get("db") or not r.get("fund_det"):
            reason = "ETF/untracked" if coverage != "full" else "missing fund_details"
            tags.append(("Data Gaps", reason))
        return tags or [("Hold / Watch", "no urgent alert")]

    def _primary_alert(r: dict) -> tuple[str, str]:
        priority = {"Exit / Reduce": 0, "Add / Accumulate": 1, "Hold / Watch": 2, "Data Gaps": 3}
        return sorted(_alert_tags(r), key=lambda item: priority.get(item[0], 9))[0]

    def _alert_badge(label: str) -> str:
        colors = {
            "Exit / Reduce": ("#fee2e2", "#991b1b"),
            "Hold / Watch": ("#fef3c7", "#92400e"),
            "Add / Accumulate": ("#dcfce7", "#166534"),
            "Data Gaps": ("#e0f2fe", "#0369a1"),
        }
        bg, fg = colors.get(label, ("#f1f5f9", "#334155"))
        return f'<span style="background:{bg};color:{fg};padding:2px 7px;border-radius:4px;font-size:11px;font-weight:800">{_esc(label)}</span>'

    def _alert_zone_html() -> str:
        buckets = {"Exit / Reduce": [], "Hold / Watch": [], "Add / Accumulate": [], "Data Gaps": []}
        for r in results:
            for label, reason in _alert_tags(r):
                buckets.setdefault(label, []).append((r, reason))
        configs = {
            "Exit / Reduce": ("#991b1b", "Highest priority risk/action names"),
            "Hold / Watch": ("#92400e", "Monitor, trail, or wait for confirmation"),
            "Add / Accumulate": ("#166534", "Best current add candidates in the book"),
            "Data Gaps": ("#0369a1", "Needs mapping or fundamentals coverage"),
        }
        cards = []
        for label, (color, subtitle) in configs.items():
            rows = sorted(
                buckets.get(label, []),
                key=lambda item: (
                    _num(item[0].get("upnl_pct")) if label == "Exit / Reduce" else -_num(item[0].get("inv_score"))
                ),
            )[:8]
            if rows:
                items = "".join(
                    f'<div class="alert-item"><b>{_esc(r["broker"])}</b><span>{_esc(reason)}</span></div>'
                    for r, reason in rows
                )
            else:
                items = '<div class="alert-item"><b>None</b><span>No names currently flagged</span></div>'
            cards.append(
                f'<div class="alert-card">'
                f'<h3 style="color:{color}">{_esc(label)} <span style="color:#94a3b8;font-weight:700">({len(buckets.get(label, []))})</span></h3>'
                f'<div style="font-size:11px;color:#64748b;margin-bottom:8px">{_esc(subtitle)}</div>'
                f'<div class="alert-list">{items}</div></div>'
            )
        return f"""
    <div class="section">
      <div class="sec-hdr" style="background:#7f1d1d">
        <span class="title">Portfolio Alert Zone</span>
        <span class="meta">Action buckets from portfolio, technical, and fundamental signals</span>
      </div>
      <div style="background:#fff;border:1px solid #e5e7eb;border-top:0;border-radius:0 0 8px 8px;padding:14px">
        <div class="alert-grid">{''.join(cards)}</div>
      </div>
    </div>
    """

    def _kv_rows(rows: list[tuple[str, object]]) -> str:
        return "".join(f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in rows)

    def _strategy_vote_rows(r: dict) -> str:
        rows = []
        for name, (sig, reason) in (r.get("signals") or {}).items():
            rows.append(f"<tr><th>{_esc(name)}</th><td>{_sig_badge(sig)} <span style='color:#64748b'>{_esc(reason)}</span></td></tr>")
        return "".join(rows)

    def _stock_detail_row(r: dict, detail_id: str, colspan: int = 16) -> str:
        alert, alert_reason = _primary_alert(r)
        fd = r.get("fund_det") or {}
        derived = r.get("derived_fund") or {}
        portfolio_rows = [
            ("Alert", f"{alert}: {alert_reason}"),
            ("Quantity", f"{r['qty']:,.0f}"),
            ("Average cost", f"₹{r['avg_cost']:,.2f}"),
            ("CMP", f"₹{r['cmp']:,.2f}"),
            ("Market value", f"₹{r['value_mkt']:,.0f}"),
            ("Realized P&L", _money(r["rpnl"])),
            ("Unrealized P&L", f"{_money(r['upnl'])} ({r['upnl_pct']:+.2f}%)"),
            ("Composite signal", r.get("composite") or "N/A"),
        ]
        technical_rows = [
            ("Stage", (r.get("stage") or "N/A").replace("STAGE_", "Stage ")),
            ("Trend", r.get("trend_sig") or "N/A"),
            ("Supertrend", r.get("supertrend") or "N/A"),
            ("Technical score", f"{_num(r.get('tech_score')):.0f}"),
            ("RS vs NIFTY 500", _fmt_rs_nifty500(r.get("rs_nifty500"))),
            ("CANSLIM", f"{_num(r.get('canslim_sc')):.0f}"),
            ("Minervini", f"{_num(r.get('minervini_sc')):.0f}"),
            ("Investment score", f"{_num(r.get('inv_score')):.0f}"),
        ]
        fundamental_rows = [
            ("eFund", f"{_num(r.get('efund_sc')):.0f}" if r.get("efund_sc") is not None else "N/A"),
            ("Earnings quality", f"{_num(r.get('earnq_sc')):.0f}" if r.get("earnq_sc") is not None else "N/A"),
            ("Sales growth", f"{_num(r.get('salesgr_sc')):.0f}" if r.get("salesgr_sc") is not None else "N/A"),
            ("Financial strength", f"{_num((r.get('db') or {}).get('fin_str')):.0f}" if r.get("db") else "N/A"),
            ("Institutional backing", f"{_num((r.get('db') or {}).get('inst_back')):.0f}" if r.get("db") else "N/A"),
            ("Derived notes", derived.get("notes") or "N/A"),
        ]
        fund_notes = " · ".join(
            str(fd.get(k) or "")
            for k in ("pnl_summary", "quarterly_summary", "ratios_summary", "investor_summary")
            if fd.get(k)
        )
        narrative = r.get("narrative") or ""

        # ── Volume Profile + Chart Patterns ────────────────────────────────
        nse_sym = (r.get("db") or {}).get("symbol") or r["broker"]
        vp_html = ""
        pat_html = ""
        try:
            from terminal.volume_profile import (
                compute_volume_profile, detect_patterns,
                render_volume_profile_svg, render_patterns_html,
            )
            vp = compute_volume_profile(nse_sym, lookback=60)
            if vp:
                vp_svg = render_volume_profile_svg(vp, width=190, height=140)
                va_label = "Inside Value Area ✓" if vp.price_in_value_area else "Outside Value Area"
                vp_html = f"""
                <div class="detail-card" style="min-width:200px">
                  <h4>Volume Profile (60 sessions)</h4>
                  {vp_svg}
                  <table style="margin-top:6px;font-size:11px;width:100%">
                    <tr><td style="color:#6b7280">POC</td><td style="text-align:right;font-weight:700;color:#dc2626">₹{vp.poc:,.1f}</td></tr>
                    <tr><td style="color:#6b7280">VAH</td><td style="text-align:right;color:#3b82f6">₹{vp.vah:,.1f}</td></tr>
                    <tr><td style="color:#6b7280">VAL</td><td style="text-align:right;color:#3b82f6">₹{vp.val:,.1f}</td></tr>
                    <tr><td style="color:#6b7280">vs POC</td><td style="text-align:right;color:{'#16a34a' if vp.price_vs_poc>=0 else '#dc2626'}">{vp.price_vs_poc:+.1f}%</td></tr>
                    <tr><td colspan="2" style="color:#64748b;font-size:10px">{va_label}</td></tr>
                  </table>
                </div>"""

            patterns = detect_patterns(nse_sym, lookback=120)
            pat_html = f"""
                <div class="detail-card" style="min-width:220px;max-width:320px">
                  <h4>Chart Patterns</h4>
                  {render_patterns_html(patterns)}
                </div>"""
        except Exception:
            pass

        return f"""
          <tr class="stock-detail-row" data-detail-for="{_esc(detail_id)}">
            <td colspan="{colspan}" class="stock-detail-cell">
              <div class="detail-grid">
                <div class="detail-card"><h4>Portfolio Details</h4><table>{_kv_rows(portfolio_rows)}</table></div>
                <div class="detail-card"><h4>Technical Details</h4><table>{_kv_rows(technical_rows)}</table></div>
                <div class="detail-card"><h4>Fundamental Details</h4><table>{_kv_rows(fundamental_rows)}</table></div>
                <div class="detail-card"><h4>Strategy Votes</h4><table>{_strategy_vote_rows(r)}</table></div>
                {vp_html}
                {pat_html}
              </div>
              {f'<div class="detail-note"><strong>Narrative:</strong> {_esc(narrative)}</div>' if narrative else ''}
              {f'<div class="detail-note"><strong>Fund details:</strong> {_esc(fund_notes)}</div>' if fund_notes else ''}
            </td>
          </tr>
        """

    def _ledger_rows() -> str:
        sorted_positions = sorted(results, key=lambda r: -r["value_mkt"])
        rows = []
        for idx, r in enumerate(sorted_positions):
            weight = (r["value_mkt"] / total_mkt * 100) if total_mkt else 0.0
            upnl_c = "#16a34a" if r["upnl"] >= 0 else "#dc2626"
            rpnl_c = "#16a34a" if r["rpnl"] >= 0 else "#dc2626"
            tpnl = r["upnl"] + r["rpnl"]
            tpnl_c = "#16a34a" if tpnl >= 0 else "#dc2626"
            alert, alert_reason = _primary_alert(r)
            detail_id = f"pos-{idx}-{re.sub(r'[^A-Za-z0-9_-]+', '', str(r['broker']))}"
            rows.append(f"""
              <tr class="portfolio-position-row" data-detail-id="{_esc(detail_id)}">
                <td><strong>{_esc(r['broker'])}</strong><span style="color:#64748b;font-size:10px;margin-left:5px">details</span></td>
                <td>{_esc((r.get('company') or '')[:34])}</td>
                <td style="text-align:right">{r['qty']:,.0f}</td>
                <td style="text-align:right">₹{r['avg_cost']:,.2f}</td>
                <td style="text-align:right">₹{r['cmp']:,.2f}</td>
                <td style="text-align:right">₹{r['value_cost']:,.0f}</td>
                <td style="text-align:right">₹{r['value_mkt']:,.0f}</td>
                <td style="text-align:right;color:{upnl_c};font-weight:700">{_money(r['upnl'])}</td>
                <td style="text-align:right;color:{upnl_c};font-weight:700">{r['upnl_pct']:+.2f}%</td>
                <td style="text-align:right;color:{rpnl_c}">{_money(r['rpnl'])}</td>
                <td style="text-align:right;color:{tpnl_c};font-weight:700">{_money(tpnl)}</td>
                <td style="text-align:right">{weight:.1f}%</td>
                <td title="{_esc(alert_reason)}">{_alert_badge(alert)}</td>
                <td style="text-align:right">{_fmt_rs_nifty500(r.get('rs_nifty500'))}</td>
                <td>{_sig_badge(r['composite'])}</td>
                <td>{_stage_badge(r['stage'])}</td>
                <td>{_esc((r.get('sector') or 'N/A')[:24])}</td>
              </tr>
              {_stock_detail_row(r, detail_id, colspan=17)}
            """)
        return "".join(rows) or "<tr><td colspan='16' style='color:#9ca3af'>No open positions found</td></tr>"

    def _realized_rows() -> str:
        realized = sorted([r for r in results if abs(r["rpnl"]) > 0.001], key=lambda r: r["rpnl"])
        rows = []
        for r in realized:
            c = "#16a34a" if r["rpnl"] >= 0 else "#dc2626"
            rows.append(f"""
              <tr>
                <td><strong>{_esc(r['broker'])}</strong></td>
                <td>{_esc((r.get('company') or '')[:34])}</td>
                <td style="text-align:right">{r['qty']:,.0f}</td>
                <td style="text-align:right">₹{r['value_cost']:,.0f}</td>
                <td style="text-align:right">₹{r['value_mkt']:,.0f}</td>
                <td style="text-align:right;color:{c};font-weight:700">{_money(r['rpnl'])}</td>
                <td style="text-align:right;color:{'#16a34a' if r['upnl'] >= 0 else '#dc2626'}">{_money(r['upnl'])}</td>
                <td>{_esc((r.get('sector') or 'N/A')[:24])}</td>
              </tr>
            """)
        return "".join(rows) or "<tr><td colspan='8' style='color:#9ca3af'>No realized P&L rows in holdings export</td></tr>"

    def _transaction_rows() -> str:
        if not transactions:
            return "<tr><td colspan='10' style='color:#9ca3af'>No detailed transaction ledger configured. Set AGENT_ADDA_TRANSACTIONS_CSV or generate portfolio-analyzer/output/closed_pnl.csv.</td></tr>"
        rows = []
        for t in transactions[:80]:
            c = "#16a34a" if t["pnl"] >= 0 else "#dc2626"
            rows.append(f"""
              <tr>
                <td><strong>{_esc(t['symbol'])}</strong></td>
                <td>{_esc(t.get('purchase_date'))}</td>
                <td>{_esc(t.get('sale_date'))}</td>
                <td style="text-align:right">{t['qty']:,.0f}</td>
                <td style="text-align:right">₹{t['purchase_rate']:,.2f}</td>
                <td style="text-align:right">₹{t['sale_rate']:,.2f}</td>
                <td style="text-align:right">₹{t['purchase_value']:,.0f}</td>
                <td style="text-align:right">₹{t['sale_value']:,.0f}</td>
                <td style="text-align:right;color:{c};font-weight:700">{_money(t['pnl'])}</td>
                <td>{_esc(t.get('tenure_bucket') or '—')}</td>
              </tr>
            """)
        return "".join(rows)

    portfolio_status_html = f"""
    <div class="section">
      <div class="sec-hdr" style="background:#111827">
        <span class="title">Portfolio Status</span>
        <span class="meta">{cash_status} · Winners {winners} · Losers {losers}</span>
      </div>
      <div class="tbl-wrap">
        <table>
          <tbody>
            <tr><th>Total cost</th><td>{_plain_money(total_cost)}</td><th>Market value</th><td>{_plain_money(total_mkt)}</td></tr>
            <tr><th>Day's Gain</th><td style="color:{'#16a34a' if day_gain >= 0 else '#dc2626'}">{_money(day_gain)}</td><th>Absolute Returns</th><td>{overall_pct:+.2f}%</td></tr>
            <tr><th>Max Gainer</th><td>{max_gain_val} <span style="color:#16a34a">{max_gain_sub}</span></td><th>Max Loser</th><td>{max_loss_val} <span style="color:#dc2626">{max_loss_sub}</span></td></tr>
            <tr><th>Unrealized P&amp;L</th><td style="color:{'#16a34a' if total_upnl >= 0 else '#dc2626'}">{_money(total_upnl)}</td><th>Unrealized return</th><td>{overall_pct:+.2f}%</td></tr>
            <tr><th>Realized P&amp;L</th><td style="color:{'#16a34a' if total_rpnl >= 0 else '#dc2626'}">{_money(total_rpnl)}</td><th>Total P&amp;L</th><td style="color:{'#16a34a' if total_pnl >= 0 else '#dc2626'}">{_money(total_pnl)} ({total_pnl_pct:+.2f}%)</td></tr>
            <tr><th>Open positions</th><td>{len(results)}</td><th>Largest position</th><td>{_esc(biggest_position['broker'] if biggest_position else 'N/A')} ({biggest_weight:.1f}%)</td></tr>
            <tr><th>Holdings source</th><td colspan="3"><code>{_esc(PORTFOLIO_CSV)}</code></td></tr>
            <tr><th>Transaction source</th><td colspan="3"><code>{_esc(TRANSACTIONS_CSV if transactions else 'not configured / not found')}</code></td></tr>
          </tbody>
        </table>
      </div>
    </div>
    """

    positions_html = f"""
    <div class="section">
      <div class="sec-hdr" style="background:#1e3a5f">
        <span class="title">Open Positions &amp; Unrealized P&amp;L</span>
        <span class="meta">Sorted by market value</span>
      </div>
      <div class="tbl-wrap">
        <table>
          <thead><tr>
            <th>Symbol</th><th>Company</th><th>Qty</th><th>Avg Cost</th><th>CMP</th>
            <th>Cost</th><th>Market Value</th><th>Unrealized ₹</th><th>Unrealized %</th>
            <th>Realized ₹</th><th>Total P&amp;L</th><th>Weight</th><th>Alert</th><th>RS vs N500</th><th>Signal</th><th>Stage</th><th>Sector</th>
          </tr></thead>
          <tbody>{_ledger_rows()}</tbody>
        </table>
      </div>
    </div>
    """

    realized_html = f"""
    <div class="section">
      <div class="sec-hdr" style="background:#334155">
        <span class="title">Realized P&amp;L by Current Holding</span>
        <span class="meta">From broker holdings export</span>
      </div>
      <div class="tbl-wrap">
        <table>
          <thead><tr>
            <th>Symbol</th><th>Company</th><th>Open Qty</th><th>Open Cost</th>
            <th>Market Value</th><th>Realized P&amp;L</th><th>Unrealized P&amp;L</th><th>Sector</th>
          </tr></thead>
          <tbody>{_realized_rows()}</tbody>
        </table>
      </div>
    </div>
    """

    transactions_html = f"""
    <div class="section">
      <div class="sec-hdr" style="background:#475569">
        <span class="title">Closed Transactions Ledger</span>
        <span class="meta">{len(transactions)} rows loaded · latest 80 shown</span>
      </div>
      <div class="tbl-wrap">
        <table>
          <thead><tr>
            <th>Symbol</th><th>Buy Date</th><th>Sell Date</th><th>Qty</th><th>Buy Price</th>
            <th>Sell Price</th><th>Buy Value</th><th>Sell Value</th><th>Realized P&amp;L</th><th>Bucket</th>
          </tr></thead>
          <tbody>{_transaction_rows()}</tbody>
        </table>
      </div>
    </div>
    """

    # Section configs
    section_cfgs = {
        "STRONG BUY": ("#166534", "#dcfce7"),
        "BUY":        ("#15803d", "#f0fdf4"),
        "HOLD":       ("#92400e", "#fffbeb"),
        "SELL":       ("#991b1b", "#fef2f2"),
    }

    def _sig_cell(sv, sreason):
        return f'<td title="{sreason}">{_sig_badge(sv)}</td>'

    sections_html = ""
    for cat, (hcolor, bgcolor) in section_cfgs.items():
        rlist = cats[cat]
        if not rlist:
            continue
        cnt = len(rlist)
        val = sum(r["value_mkt"] for r in rlist)
        avg = sum(r["upnl_pct"] for r in rlist) / cnt

        rows = ""
        for r in rlist:
            pct_c  = _pct_color(r["upnl_pct"])
            tech_s = f"{float(r['tech_score']):.0f}" if r["tech_score"] else "—"
            rs_s   = _fmt_rs_nifty500(r.get("rs_nifty500"))
            inv_s  = f"{float(r['inv_score']):.0f}"  if r["inv_score"]  else "—"
            cs_s   = f"{float(r['canslim_sc']):.0f}" if r["canslim_sc"] else "—"
            mn_s   = f"{float(r['minervini_sc']):.0f}" if r["minervini_sc"] else "—"
            ef_s   = f"{float(r['efund_sc']):.0f}"   if r["efund_sc"]   else "—"
            eq_s   = f"{float(r['earnq_sc']):.0f}"   if r.get("earnq_sc")  else "—"
            sg_s   = f"{float(r['salesgr_sc']):.0f}" if r.get("salesgr_sc") else "—"
            sect_s  = (r["sector"] or "N/A")[:20]
            trend_s = (r["trend_sig"] or "—").replace("STRONG_", "")
            narr    = (r.get("narrative") or "")[:180]

            fd     = r.get("fund_det") or {}
            pnl_s  = fd.get("pnl_summary", "")
            rat_s  = fd.get("ratios_summary", "")
            qtr_s  = fd.get("quarterly_summary", "")
            inv_sum = fd.get("investor_summary", "")

            # Mark derived fundamentals with a ★ to distinguish from DB scores
            df     = r.get("derived_fund")
            ef_tag = " ★" if df else ""

            sig_cells = "".join(
                _sig_cell(sv, sreason)
                for sname, (sv, sreason) in r["signals"].items()
            )

            fund_badge = ""
            if df:
                # Build mini fundamental pills from derived data
                parts = []
                if df.get("rev_growth") is not None:
                    c = "#16a34a" if df["rev_growth"] >= 8 else ("#ca8a04" if df["rev_growth"] >= 0 else "#dc2626")
                    parts.append(f'<span style="color:{c}">Rev {df["rev_growth"]:+.1f}%</span>')
                if df.get("np_growth") is not None:
                    c = "#16a34a" if df["np_growth"] >= 8 else ("#ca8a04" if df["np_growth"] >= 0 else "#dc2626")
                    parts.append(f'<span style="color:{c}">Prf {df["np_growth"]:+.1f}%</span>')
                if df.get("roce") is not None:
                    parts.append(f'ROCE {df["roce"]:.0f}%')
                if df.get("roe") is not None:
                    parts.append(f'ROE {df["roe"]:.0f}%')
                if df.get("pe") is not None:
                    parts.append(f'P/E {df["pe"]:.1f}x')
                fund_badge = " &nbsp;|&nbsp; " + " · ".join(parts) if parts else ""

            rows += f"""<tr>
              <td><strong>{r['broker']}</strong></td>
              <td style="font-size:12px">{r['company'][:30]}</td>
              <td style="text-align:right">₹{r['cmp']:,.1f}</td>
              <td style="text-align:right">₹{r['avg_cost']:,.1f}</td>
              <td style="text-align:right;color:{pct_c};font-weight:600">{r['upnl_pct']:+.1f}%</td>
              <td style="text-align:right">₹{r['value_mkt']/1000:,.0f}K</td>
              <td>{_stage_badge(r["stage"])}</td>
              <td style="text-align:center">{tech_s}</td>
              <td style="text-align:center">{rs_s}</td>
              <td style="text-align:center;font-weight:600">{inv_s}</td>
              <td style="font-size:11px" title="CANSLIM/Minervini/eFund{ef_tag}">{cs_s}/{mn_s}/{ef_s}{ef_tag}</td>
              <td style="font-size:11px">{eq_s}/{sg_s}</td>
              <td style="font-size:11px">{trend_s}</td>
              {sig_cells}
              <td>{_sig_badge(r['composite'])}</td>
              <td style="font-size:11px">{sect_s}</td>
            </tr>
            <tr class="narr">
              <td colspan="22" style="font-size:11px;line-height:1.7">
                {narr}{fund_badge}
                {f'<br><span style="color:#1e40af">{pnl_s}</span>' if pnl_s else ''}
                {f'<br>{qtr_s}' if qtr_s else ''}
                {f'<br><span style="color:#374151">{rat_s}</span>' if rat_s else ''}
                {f'<br><span style="color:#6b7280">{inv_sum}</span>' if inv_sum else ''}
              </td>
            </tr>"""

        sections_html += f"""
        <div class="section">
          <div class="sec-hdr" style="background:{hcolor}">
            <span class="title">{cat} &nbsp;
              <span style="opacity:.65;font-size:13px">({cnt} stocks)</span></span>
            <span class="meta">
              Mkt Value ₹{val/100000:.1f}L &nbsp;·&nbsp; Avg P&L {avg:+.1f}%
            </span>
          </div>
          <div class="tbl-wrap" style="background:{bgcolor}">
            <table>
              <thead><tr>
                <th>Symbol</th><th>Company</th><th>CMP</th><th>AvgCost</th>
                <th>P&amp;L%</th><th>Value</th><th>Stage</th>
                <th title="Tech Score">Tech</th>
                <th title="Relative Strength vs NIFTY 500">RS vs N500</th>
                <th title="Investment Score">InvSc</th>
                <th title="CANSLIM/Minervini/eFund (★=derived from fund_details)">C/M/F</th>
                <th title="EarnQuality/SalesGrowth">EQ/SG</th>
                <th>Trend</th>
                <th title="Momentum">Mom.</th>
                <th title="CANSLIM">CANS.</th>
                <th title="Minervini">Miner.</th>
                <th title="Fundamental">Fund.</th>
                <th title="Value/PnL">Val.</th>
                <th title="Volatility Contraction Pattern">VCP</th>
                <th title="Relative Strength vs NIFTY 500 Strategy">RS Strat.</th>
                <th>Signal</th><th>Sector</th>
              </tr></thead>
              <tbody>{rows}</tbody>
            </table>
          </div>
        </div>"""

    # ── Sector breakdown with per-sector stock drill-down ────────────────────
    sector_stats: dict[str, dict] = {}
    sector_stocks: dict[str, list] = {}
    for r in results:
        s = r["sector"] or "N/A"
        if s not in sector_stats:
            sector_stats[s] = {"cost": 0.0, "mkt": 0.0, "cnt": 0}
            sector_stocks[s] = []
        sector_stats[s]["cost"] += r["value_cost"]
        sector_stats[s]["mkt"]  += r["value_mkt"]
        sector_stats[s]["cnt"]  += 1
        sector_stocks[s].append(r)

    top_sectors = sorted(sector_stats.items(), key=lambda x: -x[1]["mkt"])[:15]

    # Build compact sect_rows for the summary card (unchanged format)
    sect_rows = "".join(
        f"<tr><td>{s}</td><td>{v['cnt']}</td>"
        f"<td style='text-align:right'>₹{v['mkt']/100000:.2f}L</td>"
        f"<td style='text-align:right;color:"
        f"{'#16a34a' if v['mkt']>=v['cost'] else '#dc2626'}'>"
        f"{(v['mkt']/v['cost']-1)*100:+.1f}%</td></tr>"
        for s, v in top_sectors
    )

    # Build the interactive drill-down sector table
    def _sector_drill_rows() -> str:
        rows = ""
        for i, (sect, v) in enumerate(top_sectors):
            ret_pct = (v["mkt"] / v["cost"] - 1) * 100 if v["cost"] else 0
            ret_c   = "#16a34a" if ret_pct >= 0 else "#dc2626"
            drill_id = f"sector-drill-{i}"
            wt_pct  = v["mkt"] / sum(x["mkt"] for _, x in top_sectors) * 100 if top_sectors else 0

            # Signal breakdown for this sector
            sig_counts = {}
            for r in sector_stocks[sect]:
                sig_counts[r["composite"]] = sig_counts.get(r["composite"], 0) + 1
            sig_pills = "".join(
                f'<span style="background:{"#16a34a" if s in ("STRONG BUY","BUY") else "#f59e0b" if s=="HOLD" else "#dc2626"};'
                f'color:white;padding:1px 5px;border-radius:3px;font-size:10px;margin-left:3px">'
                f'{s.replace("STRONG BUY","SBY").replace("BUY","BUY").replace("HOLD","HLD").replace("SELL","SEL")} {c}</span>'
                for s, c in sorted(sig_counts.items(), key=lambda x: ["STRONG BUY","BUY","HOLD","SELL"].index(x[0]) if x[0] in ["STRONG BUY","BUY","HOLD","SELL"] else 9)
            )

            # Clickable sector row
            rows += f"""
            <tr class="sector-row" onclick="toggleSectorDrill('{drill_id}')" style="cursor:pointer"
                title="Click to expand {v['cnt']} holdings in {sect}">
              <td style="font-weight:600">{sect}
                <span style="color:#94a3b8;font-size:10px;margin-left:4px">▾</span></td>
              <td style="text-align:center">{v['cnt']}</td>
              <td style="text-align:right;font-weight:600">₹{v['mkt']/100000:.2f}L</td>
              <td style="text-align:center;color:#6b7280">{wt_pct:.1f}%</td>
              <td style="text-align:right;color:{ret_c};font-weight:600">{ret_pct:+.1f}%</td>
              <td>{sig_pills}</td>
            </tr>
            <tr class="sector-drill-row" id="{drill_id}" style="display:none">
              <td colspan="6" style="padding:0;background:#f8fafc;border-bottom:2px solid #0f766e">
                {_sector_holdings_table(sect, sector_stocks[sect])}
              </td>
            </tr>"""
        return rows

    def _sector_holdings_table(sect: str, stocks: list) -> str:
        """Build the expanded holdings table for a sector drill-down."""
        sorted_stocks = sorted(stocks, key=lambda r: -(r["value_mkt"] or 0))
        rows = ""
        for r in sorted_stocks:
            pct_c   = _pct_color(r["upnl_pct"])
            inv_s   = f"{float(r['inv_score']):.0f}" if r.get("inv_score") else "—"
            tech_s  = f"{float(r['tech_score']):.0f}" if r.get("tech_score") else "—"
            rsi_s   = f"{float(r['rsi_val']):.0f}" if r.get("rsi_val") else "—"
            stage_s = _stage_badge(r["stage"])
            sig     = _sig_badge(r["composite"])
            day_s   = f"{r['_day_chg']:+.1f}%{'ᵈ' if r.get('day_chg_pct') is None else ''}" \
                      if r.get("_day_chg") is not None else "—"
            day_c   = _pct_color(r.get("_day_chg") or 0) if r.get("_day_chg") is not None else "#6b7280"
            wt_s    = f"{r['value_mkt']/sum(x['value_mkt'] for x in stocks)*100:.1f}%" \
                      if stocks else "—"

            rows += f"""<tr style="border-bottom:1px solid #e5e7eb">
              <td style="padding:5px 10px;font-weight:600;font-size:12px">{r['broker']}</td>
              <td style="padding:5px 8px;font-size:11px;color:#374151">{r['company'][:28]}</td>
              <td style="padding:5px 8px;text-align:right;font-size:12px">₹{r['cmp']:,.0f}</td>
              <td style="padding:5px 8px;text-align:right;font-size:12px;color:{day_c};font-weight:600">{day_s}</td>
              <td style="padding:5px 8px;text-align:right;color:{pct_c};font-weight:600;font-size:12px">{r['upnl_pct']:+.1f}%</td>
              <td style="padding:5px 8px;text-align:right;font-size:12px">₹{r['value_mkt']/1000:,.0f}K</td>
              <td style="padding:5px 8px;text-align:center;font-size:11px;color:#6b7280">{wt_s}</td>
              <td style="padding:5px 8px">{sig}</td>
              <td style="padding:5px 8px">{stage_s}</td>
              <td style="padding:5px 8px;text-align:center;font-size:11px">{tech_s}</td>
              <td style="padding:5px 8px;text-align:center;font-size:11px">{rsi_s}</td>
              <td style="padding:5px 8px;text-align:center;font-size:11px;font-weight:600">{inv_s}</td>
            </tr>"""

        header = """<table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead><tr style="background:#f0fdf4;font-size:10px;text-transform:uppercase;color:#0f766e">
            <th style="padding:5px 10px;text-align:left">Symbol</th>
            <th style="padding:5px 8px;text-align:left">Company</th>
            <th style="padding:5px 8px;text-align:right">CMP</th>
            <th style="padding:5px 8px;text-align:right">Day%</th>
            <th style="padding:5px 8px;text-align:right">P&amp;L%</th>
            <th style="padding:5px 8px;text-align:right">Value</th>
            <th style="padding:5px 8px;text-align:center">Wt%</th>
            <th style="padding:5px 8px;text-align:center">Signal</th>
            <th style="padding:5px 8px;text-align:center">Stage</th>
            <th style="padding:5px 8px;text-align:center">Tech</th>
            <th style="padding:5px 8px;text-align:center">RSI</th>
            <th style="padding:5px 8px;text-align:center">InvSc</th>
          </tr></thead>
          <tbody>{rows}</tbody>
        </table>"""
        return header.format(rows=rows)

    # JavaScript for sector drill-down toggle
    sector_js = """
<script>
function toggleSectorDrill(id) {
  var el = document.getElementById(id);
  if (!el) return;
  var showing = el.style.display !== 'none';
  el.style.display = showing ? 'none' : 'table-row';
  // Flip the arrow on the parent row
  var parentRow = el.previousElementSibling;
  if (parentRow) {
    var arrow = parentRow.querySelector('span[title]') || parentRow.querySelector('td:first-child span:last-child');
    if (arrow) arrow.textContent = showing ? '▾' : '▴';
  }
}
function expandAllSectors() {
  document.querySelectorAll('.sector-drill-row').forEach(function(el) {
    el.style.display = 'table-row';
  });
}
function collapseAllSectors() {
  document.querySelectorAll('.sector-drill-row').forEach(function(el) {
    el.style.display = 'none';
  });
}
</script>"""

    sector_exposure_html = f"""
    {sector_js}
    <div class="section" id="sector-exposure-section" style="scroll-margin-top:56px">
      <div class="sec-hdr" style="background:#0f766e;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
        <span class="title">Sector Exposure
          <span style="opacity:.65;font-size:13px">(top 15 by value)</span></span>
        <span class="meta" style="display:flex;gap:8px">
          <button onclick="expandAllSectors()"
            style="background:rgba(255,255,255,.2);border:none;color:white;cursor:pointer;
                   padding:3px 10px;border-radius:4px;font-size:11px">Expand all</button>
          <button onclick="collapseAllSectors()"
            style="background:rgba(255,255,255,.2);border:none;color:white;cursor:pointer;
                   padding:3px 10px;border-radius:4px;font-size:11px">Collapse all</button>
          <span style="opacity:.7;font-size:12px">Click sector row to drill down</span>
        </span>
      </div>
      <div class="tbl-wrap">
        <table id="sector-exposure-tbl" style="width:100%;border-collapse:collapse">
          <thead><tr style="background:#f9fafb">
            <th style="padding:7px 12px;text-align:left;font-size:11px;color:#0f766e;text-transform:uppercase">Sector</th>
            <th style="padding:7px 8px;text-align:center;font-size:11px;color:#6b7280"># Holdings</th>
            <th style="padding:7px 8px;text-align:right;font-size:11px;color:#6b7280">Market Value</th>
            <th style="padding:7px 8px;text-align:center;font-size:11px;color:#6b7280">Portfolio Wt%</th>
            <th style="padding:7px 8px;text-align:right;font-size:11px;color:#6b7280">Return</th>
            <th style="padding:7px 8px;text-align:left;font-size:11px;color:#6b7280">Signals</th>
          </tr></thead>
          <tbody>{_sector_drill_rows()}</tbody>
        </table>
      </div>
    </div>
    """

    # Top-5 buys / top-5 sells
    buys  = sorted(cats["STRONG BUY"] + cats["BUY"], key=lambda x: -(x["inv_score"] or 0))[:5]
    sells = sorted(cats["SELL"], key=lambda x: (x["upnl_pct"] or 0))[:5]

    def _top_row(r, mode):
        c = "#16a34a" if r["upnl_pct"] >= 0 else "#dc2626"
        if mode == "buy":
            return (
                f"<tr><td><strong>{r['broker']}</strong></td>"
                f"<td>{r['company'][:30]}</td>"
                f"<td style='text-align:right'>₹{r['cmp']:,.1f}</td>"
                f"<td style='text-align:right;color:{c}'>{r['upnl_pct']:+.1f}%</td>"
                f"<td style='text-align:center'>{(lambda v: f'{float(v):.0f}' if v else '—')(r['inv_score'])}</td>"
                f"<td>{_stage_badge(r['stage'])}</td>"
                f"<td style='font-size:11px'>{(r['sector'] or '')[:20]}</td></tr>"
            )
        else:
            return (
                f"<tr><td><strong>{r['broker']}</strong></td>"
                f"<td>{r['company'][:30]}</td>"
                f"<td style='text-align:right;color:#dc2626'>{r['upnl_pct']:+.1f}%</td>"
                f"<td style='text-align:right;color:#dc2626'>"
                f"₹{abs(r['upnl'])/1000:.0f}K</td>"
                f"<td>{_stage_badge(r['stage'])}</td>"
                f"<td style='font-size:11px'>{(r['sector'] or '')[:20]}</td></tr>"
            )

    two_col = f"""
    <div class="two-col">
      <div class="card">
        <h3>🟢 Top 5 Buy Opportunities</h3>
        <table><thead><tr>
          <th>Symbol</th><th>Company</th><th>CMP</th>
          <th>P&amp;L%</th><th>InvSc</th><th>Stage</th><th>Sector</th>
        </tr></thead>
        <tbody>{''.join(_top_row(r,'buy') for r in buys) or
                '<tr><td colspan=7 style=color:#9ca3af>None</td></tr>'}
        </tbody></table>
      </div>
      <div class="card">
        <h3>🔴 Top 5 Sell Candidates</h3>
        <table><thead><tr>
          <th>Symbol</th><th>Company</th><th>Loss%</th>
          <th>Loss₹</th><th>Stage</th><th>Sector</th>
        </tr></thead>
        <tbody>{''.join(_top_row(r,'sell') for r in sells) or
                '<tr><td colspan=6 style=color:#9ca3af>None</td></tr>'}
        </tbody></table>
      </div>
    </div>
    <div class="two-col">
      <div class="card">
        <h3>Sector Breakdown (top 15)</h3>
        <table><thead><tr>
          <th>Sector</th><th>#</th><th>Value</th><th>Return</th>
        </tr></thead><tbody>{sect_rows}</tbody></table>
      </div>
      <div class="card">
        <h3>Signal Summary</h3>
        <table>
          <thead><tr><th>Signal</th><th>Count</th><th>Value</th><th>Avg P&L%</th></tr></thead>
          <tbody>
            {''.join(
              f"<tr><td>{_sig_badge(cat)}</td>"
              f"<td>{len(cats[cat])}</td>"
              f"<td>₹{sum(r['value_mkt'] for r in cats[cat])/100000:.1f}L</td>"
              f"<td style='color:{'#16a34a' if sum(r['upnl_pct'] for r in cats[cat])/max(1,len(cats[cat]))>=0 else '#dc2626'}'>"
              f"{sum(r['upnl_pct'] for r in cats[cat])/max(1,len(cats[cat])):+.1f}%</td></tr>"
              for cat in ('STRONG BUY','BUY','HOLD','SELL')
            )}
          </tbody>
        </table>
        <div style="margin-top:12px;font-size:12px;color:#6b7280">
          <ul style="margin-left:16px;line-height:1.9">
            <li>{sum(1 for r in results if (r['stage'] or '') == 'STAGE_4')} stocks in Stage 4 — consider exiting</li>
            <li>{sum(1 for r in results if float(r.get('rs_nifty500') or 0) > 10)} stocks outperforming NIFTY 500 by &gt;10 RS points</li>
            <li>{sum(1 for r in results if float(r.get('rs_nifty500') or 0) < -10)} stocks underperforming NIFTY 500 by &gt;10 RS points</li>
            <li>{sum(1 for r in results if r['upnl_pct'] <= -20)} stocks with &gt;20% loss — review exit</li>
            <li>{sum(1 for r in results if r['upnl_pct'] >= 50)} stocks with &gt;50% gain — trail stop</li>
          </ul>
        </div>
      </div>
    </div>"""

    note = """
    <div class="note">
      <strong>Strategies:</strong>
      <strong>Momentum</strong> (Stage + Supertrend + Trend) ·
      <strong>CANSLIM</strong> (composite /30) ·
      <strong>Minervini</strong> (/30 setup score) ·
      <strong>Fundamental</strong> (eFund + EarnQuality + SalesGrowth; ★ = derived from fund_details) ·
      <strong>Value/PnL</strong> (loss-cut &lt;-30%, trail &gt;100%) ·
      <strong>VCP</strong> (Stage + bullish trend + supertrend + Minervini/Tech setup) ·
      <strong>RS Strategy</strong> (RS vs NIFTY 500: BUY ≥ +20, SELL &lt; -10).
      Composite: ≥3 BUY → STRONG BUY · ≥2 BUY &gt; SELL → BUY ·
      ≥2 SELL &gt; BUY → SELL · else HOLD.
    </div>"""

    heatmap_html = _build_heatmap_section(results)

    now_ist = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(hours=5, minutes=30)
    body = f"""
    <div class="header">
      <h1>💼 My Portfolio — Daily Portfolio Ledger</h1>
      <p>{now_ist.strftime('%d %b %Y %H:%M')} IST &nbsp;|&nbsp;
         Snapshot: {snap_date} &nbsp;|&nbsp; {len(results)} holdings &nbsp;|&nbsp;
         Positions · Transactions · Realized/Unrealized P&amp;L · Strategy diagnostics</p>
    </div>
    <div class="kpi-grid">{kpi_html}</div>
    {_alert_zone_html()}
    {portfolio_status_html}
    {positions_html}
    {realized_html}
    {transactions_html}
    {note}
    {heatmap_html}
    {sector_exposure_html}
    """

    ts = now_ist.strftime("%Y-%m-%d %H:%M IST")
    html = (
        _HTML_HEAD.format(title="Daily Portfolio Ledger", refresh_meta="")
        + body
        + _HTML_FOOT.format(ts=ts)
    )
    EOD_REPORT.write_text(html, encoding="utf-8")
