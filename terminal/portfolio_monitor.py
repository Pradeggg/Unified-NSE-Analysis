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
import json
import os
import re
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

# ── Symbol mapping: broker short-code → NSE ticker ────────────────────────────
_BROKER_TO_NSE: dict[str, str] = {
    "ACTCON": "ACTIONCONS",   "ADAENT": "ADANIENT",    "ADAPOR": "ADANIPORTS",
    "ADAPOW": "ADANIPOWER",   "ADOWEL": "ADORWELD",    "AFFIND": "AFFLE",
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
    "HINREC": "HINDRECT",     "ICIBAN": "ICICIBANK",   "ICILOM": "ICICIGI",
    "ICIPRU": "ICICIPRULI",   "IDBI":   "IDBIBANK",    "IDFC":   "IDFC",
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
    "RAYMON": "RAYMOND",      "RELNIP": "NIPPONLIFE",  "ROSTEC": "ROSSELTECHSYS",
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
    "ZOMLIM": "ZOMATO",       "ICIA30": "ICIALPHAETF", "ICIAUT": "ICICIAUTO",
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
            })
    return rows


# ── DB snapshot loader ────────────────────────────────────────────────────────

def _load_db_snapshot() -> tuple[dict[str, dict], str]:
    """Load latest stage_snapshots from PostgreSQL.

    Returns (records_dict, snap_date_str). On failure returns ({}, 'N/A').
    """
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
            cols = [
                "symbol", "company_name", "stage", "stage_score", "price", "live_price",
                "tech_score", "rsi", "trade_sig", "trend_sig", "rel_str",
                "chg1d", "chg1w", "chg1m", "mktcap", "sector",
                "fund_score", "efund_score", "earn_qual", "sales_gr",
                "fin_str", "inst_back", "canslim", "minervini", "inv_score",
                "fund_det", "narrative", "stance", "supertrend", "st_val",
            ]
            records: dict[str, dict] = {}
            for result in cur.fetchall():
                data = dict(zip(cols, result))
                records[data["symbol"]] = data
            return records, snap_date
    except Exception:
        return {}, "N/A"
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
) -> list[dict]:
    results = []
    for s in portfolio:
        d = _find_match(s["broker"], s["company"], records, db_norm)

        # Overlay live intraday price if available
        live_cmp = s["cmp"]
        if (not live_cmp or live_cmp <= 0) and d:
            live_cmp = float(d.get("live_price") or d.get("price") or 0)
        day_chg_pct: Optional[float] = None
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
            "RSI":         _strat_rsi(d),
        }
        comp, nb, ns, nh = _composite_signal(sigs)

        fd: dict = _parse_fund_details(d.get("fund_det")) if d else {}

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

        results.append({
            **s,
            "db":           d,
            "live_cmp":     live_cmp,
            "live_value":   live_value,
            "live_upnl":    live_upnl,
            "live_upnl_pct":live_upnl_pct,
            "day_chg_pct":  day_chg_pct,
            "signals":      sigs,
            "composite":    comp,
            "buy_count":    nb,
            "sell_count":   ns,
            "hold_count":   nh,
            "stage":        d["stage"]      if d else "N/A",
            "tech_score":   d["tech_score"] if d else None,
            "rsi_val":      d["rsi"]        if d else None,
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

def _fetch_live_prices_yf(nse_symbols: list[str]) -> dict[str, float]:
    """Fetch latest prices from Yahoo Finance (.NS suffix). Best-effort."""
    try:
        import yfinance as yf
        skip = {
            "LIQUID", "CASHIETF", "CPSEETF", "COMMOIETF", "GROWWLIQID",
            "LIQUIDPLUS", "LIQUIDADD", "LIQUIDCASE", "LIQUIDBETF",
            "LIQUID1", "LIQUIDBEES", "BANKBEES", "NIFTYBEES", "INFRAETF",
            "BHARAT22ETF", "AXISNIFTYIT", "ICICIGOLD", "SBIETFGOLD",
            "ICICIAUTO", "ICIALPHAETF", "TATANIFTYDIGITAL", "PSUBNKBEES",
        }
        syms_to_fetch = [s for s in nse_symbols if s not in skip]
        prices: dict[str, float] = {}
        for i in range(0, len(syms_to_fetch), 60):
            chunk = syms_to_fetch[i : i + 60]
            tickers = [f"{s}.NS" for s in chunk]
            try:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    data = yf.download(
                        tickers, period="2d", progress=False, auto_adjust=True
                    )
                close = data.get("Close", None)
                if close is not None and not close.empty:
                    last = close.iloc[-1]
                    for t in tickers:
                        sym = t.replace(".NS", "")
                        val = last.get(t)
                        if val is not None:
                            try:
                                import math
                                if not math.isnan(float(val)):
                                    prices[sym] = round(float(val), 2)
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
    records, snap_date = _load_db_snapshot()
    db_norm = _build_db_norm(records)

    live_prices: dict[str, float] = {}
    if live and _is_market_hours():
        nse_syms = list({_BROKER_TO_NSE.get(s["broker"], s["broker"]) for s in portfolio})
        live_prices = _fetch_live_prices_yf(nse_syms)

    results = _analyse_portfolio(portfolio, records, db_norm, live_prices or None)

    if filter_signal:
        fs = filter_signal.upper()
        results = [r for r in results if r["composite"].upper() == fs]

    # Sort: STRONG BUY/BUY by inv_score desc, SELL by loss pct
    def _sort_key(r):
        order = {"STRONG BUY": 0, "BUY": 1, "HOLD": 2, "SELL": 3}
        return (order.get(r["composite"], 9), -(r["inv_score"] or 0))
    results.sort(key=_sort_key)

    total_cost  = sum(r["value_cost"]  for r in results)
    total_live  = sum(r["live_value"]  for r in results)
    total_upnl  = sum(r["live_upnl"]   for r in results)
    day_gain    = sum(
        (r["day_chg_pct"] or 0) / 100 * r["value_cost"]
        for r in results if r["day_chg_pct"] is not None
    )

    now_ist = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(hours=5, minutes=30)
    mkt_status = "MARKET OPEN" if _is_market_hours() else "MARKET CLOSED"

    lines = [
        f"## 💼 My Portfolio — {mkt_status}",
        f"*{now_ist.strftime('%d %b %Y %H:%M')} IST  ·  Snapshot: {snap_date}  ·  {len(results)} holdings*",
        "",
        f"| KPI | Value |",
        f"|-----|-------|",
        f"| Invested | ₹{total_cost/100000:.2f}L |",
        f"| Live Value | ₹{total_live/100000:.2f}L |",
        f"| Total P&L | {'+'if total_upnl>=0 else ''}₹{total_upnl/100000:.2f}L ({(total_live/total_cost-1)*100 if total_cost else 0:+.1f}%) |",
        f"| Today's Move | {'+'if day_gain>=0 else ''}₹{day_gain/1000:.1f}K |",
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
    lines.append("| Symbol | Company | CMP | Day% | P&L% | Signal | Stage | RSI | Sector |")
    lines.append("|--------|---------|-----|------|------|--------|-------|-----|--------|")
    for r in results[:60]:  # cap at 60 rows in terminal
        day_s   = f"{r['day_chg_pct']:+.1f}%" if r["day_chg_pct"] is not None else "-"
        pct_s   = f"{r['live_upnl_pct']:+.1f}%"
        stage_s = (r["stage"] or "N/A").replace("STAGE_", "S")
        rsi_s   = f"{float(r['rsi_val']):.0f}" if r["rsi_val"] else "-"
        sect_s  = (r["sector"] or "N/A")[:18]
        lines.append(
            f"| **{r['broker']}** | {r['company'][:22]} | ₹{r['live_cmp']:,.0f} "
            f"| {day_s} | {pct_s} | {r['composite']} | {stage_s} | {rsi_s} | {sect_s} |"
        )

    if len(results) > 60:
        lines.append(f"*… and {len(results)-60} more — open HTML report for full view*")

    lines.extend([
        "",
        "---",
        f"*Open full report: `reports/latest/portfolio_intraday.html`*",
    ])

    # Write HTML
    _write_intraday_html(results, snap_date, total_cost, total_live, total_upnl, day_gain)

    return "\n".join(lines)


# ── EOD comprehensive report ──────────────────────────────────────────────────

def run_eod_report(
    csv_path: Path = PORTFOLIO_CSV,
    db_path: Optional[Path] = None,
) -> dict:
    """Build full EOD analysis and write portfolio_analysis.html."""
    try:
        portfolio = _load_portfolio(csv_path)
        result = _load_db_snapshot()
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
        _write_eod_html(results, snap_date)
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
.section{{margin-bottom:28px}}
.sec-hdr{{padding:10px 18px;border-radius:8px 8px 0 0;
           display:flex;justify-content:space-between;align-items:center}}
.sec-hdr .title{{font-size:16px;font-weight:700;color:white}}
.sec-hdr .meta{{font-size:12px;color:rgba(255,255,255,.8)}}
.tbl-wrap{{overflow-x:auto;background:white;border:1px solid #e5e7eb;
            border-radius:0 0 8px 8px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
thead tr{{background:#f9fafb}}
th{{padding:6px 8px;text-align:left;font-size:11px;color:#6b7280;
    font-weight:600;text-transform:uppercase;border-bottom:1px solid #e5e7eb}}
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
.footer{{text-align:center;color:#9ca3af;font-size:11px;
          margin-top:20px;padding:12px}}
</style>
</head>
<body><div class="container">
"""

_HTML_FOOT = """\
<div class="footer">{ts} &nbsp;|&nbsp; For informational purposes only. Not financial advice.</div>
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

    # KPIs
    kpi_html = ""
    kpi_data = [
        ("Invested",     f"₹{total_cost/100000:.2f}L",       f"{len(results)} holdings"),
        ("Live Value",   f"₹{total_live/100000:.2f}L",        snap_date),
        ("Total P&L",    f"{'+'if total_upnl>=0 else ''}₹{total_upnl/100000:.2f}L",
                         f"{overall_pct:+.1f}%",),
        ("Today",        f"{'+'if day_gain>=0 else ''}₹{day_gain/1000:.1f}K",
                         "intraday move"),
        ("Strong Buy",   str(len(cats["STRONG BUY"])), "stocks"),
        ("Buy",          str(len(cats["BUY"])),         "stocks"),
        ("Hold",         str(len(cats["HOLD"])),        "stocks"),
        ("Sell",         str(len(cats["SELL"])),        "stocks"),
    ]
    bg_map = {"Strong Buy": "#dcfce7", "Buy": "#f0fdf4", "Hold": "#fffbeb", "Sell": "#fef2f2"}
    vc_map = {"Total P&L": "#16a34a" if total_upnl >= 0 else "#dc2626",
              "Today":     "#16a34a" if day_gain >= 0 else "#dc2626"}
    for lbl, val, sub in kpi_data:
        bg = bg_map.get(lbl, "white")
        vc = vc_map.get(lbl, "#111827")
        kpi_html += (
            f'<div class="kpi" style="background:{bg}">'
            f'<div class="lbl">{lbl}</div>'
            f'<div class="val" style="color:{vc}">{val}</div>'
            f'<div class="sub">{sub}</div></div>'
        )

    # Intraday movers table — all stocks sorted by day% then signal
    def _day_sort(r):
        order = {"STRONG BUY": 0, "BUY": 1, "HOLD": 2, "SELL": 3}
        return (order.get(r["composite"], 9), -(r["day_chg_pct"] or 0))
    sorted_results = sorted(results, key=_day_sort)

    rows_html = ""
    for r in sorted_results:
        day_s   = f"{r['day_chg_pct']:+.1f}%" if r["day_chg_pct"] is not None else "—"
        day_c   = _pct_color(r["day_chg_pct"] or 0)
        pct_c   = _pct_color(r["live_upnl_pct"])
        stage_s = _stage_badge(r["stage"])
        rsi_s   = f"{float(r['rsi_val']):.0f}" if r["rsi_val"] else "—"
        inv_s   = f"{float(r['inv_score']):.0f}" if r["inv_score"] else "—"
        sector_s = (r["sector"] or "N/A")[:20]
        narr    = (r.get("narrative") or "")[:100]

        fd = r.get("fund_det") or {}
        ratios = fd.get("ratios_summary", "")

        rows_html += f"""<tr>
          <td><strong>{r['broker']}</strong></td>
          <td style="font-size:12px">{r['company'][:30]}</td>
          <td style="text-align:right">₹{r['live_cmp']:,.1f}</td>
          <td style="text-align:right;color:{day_c};font-weight:600">{day_s}</td>
          <td style="text-align:right;color:{pct_c};font-weight:600">
            {r['live_upnl_pct']:+.1f}%</td>
          <td style="text-align:right">₹{r['live_value']/1000:,.0f}K</td>
          <td>{_sig_badge(r['composite'])}</td>
          <td>{stage_s}</td>
          <td style="text-align:center">{rsi_s}</td>
          <td style="text-align:center;font-weight:600">{inv_s}</td>
          <td style="font-size:11px">{sector_s}</td>
        </tr>
        <tr class="narr"><td colspan="11">{narr}
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

    body = f"""
    <div class="header">
      <h1>💼 My Portfolio — Live Dashboard</h1>
      <p>{now_ist.strftime('%d %b %Y %H:%M')} IST &nbsp;|&nbsp;
         {mkt_open and 'MARKET OPEN ● Auto-refresh 60s' or 'MARKET CLOSED'} &nbsp;|&nbsp;
         Snapshot: {snap_date} &nbsp;|&nbsp; {len(results)} holdings</p>
    </div>

    <div class="kpi-grid">{kpi_html}</div>

    <div class="two-col">
      <div class="card">
        <h3>📈 Top Gainers Today</h3>
        <table><thead><tr><th>Symbol</th><th>Company</th><th>CMP</th>
          <th>Day%</th><th>Signal</th></tr></thead>
        <tbody>{_mover_rows(top_gainers, True)}</tbody></table>
      </div>
      <div class="card">
        <h3>📉 Top Losers Today</h3>
        <table><thead><tr><th>Symbol</th><th>Company</th><th>CMP</th>
          <th>Day%</th><th>Signal</th></tr></thead>
        <tbody>{_mover_rows(top_losers, False)}</tbody></table>
      </div>
    </div>

    <div class="note">
      <strong>Signal logic:</strong> Each stock evaluated on 6 strategies (Momentum ·
      CANSLIM · Minervini · Fundamental · Value/PnL · RSI). Composite: ≥3 BUY → STRONG BUY ·
      ≥2 BUY &gt; SELL → BUY · ≥2 SELL &gt; BUY → SELL · else HOLD.
      Prices are 15-min delayed via Yahoo Finance during market hours.
    </div>

    <div class="section">
      <div class="sec-hdr" style="background:#1e3a5f">
        <span class="title">All Holdings — Intraday View</span>
        <span class="meta">{len(results)} stocks sorted by signal then day gain</span>
      </div>
      <div class="tbl-wrap">
        <table>
          <thead><tr>
            <th>Symbol</th><th>Company</th><th>CMP</th>
            <th>Day%</th><th>P&amp;L%</th><th>Value</th>
            <th>Signal</th><th>Stage</th><th>RSI</th><th>InvSc</th><th>Sector</th>
          </tr></thead>
          <tbody>{rows_html}</tbody>
        </table>
      </div>
    </div>
    """

    ts = now_ist.strftime("%Y-%m-%d %H:%M IST")
    html = (
        _HTML_HEAD.format(
            title="Portfolio Live Dashboard",
            refresh_meta=refresh_meta,
        )
        + body
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
    Build three complementary heat-map visualisations:

    1. Signal × Stage grid   – avg fund score + count per cell, coloured heat.
    2. Bubble scatter         – Tech Score (X) × Fund Score (Y), bubble size =
                                portfolio value, colour = signal.  Pure SVG.
    3. Per-stock heat strip   – every stock as one row with coloured cells for
                                Stage / Signal / Fund / Tech / CANSLIM /
                                Minervini / InvScore / P&L%.
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
        bubble_items.append((r_px, cx, cy, fill, tip, r["broker"]))

    bubble_items.sort(key=lambda x: -x[0])  # largest first (render behind)
    bubbles_svg = ""
    labels_svg  = ""
    for r_px, cx, cy, fill, tip, broker in bubble_items:
        bubbles_svg += (
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r_px:.1f}" '
            f'fill="{fill}" fill-opacity="0.75" stroke="white" stroke-width="0.8">'
            f'<title>{tip}</title></circle>'
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
                f'{_heat_cell(r.get("rsi_val"), 20, 85, fmt="{:.0f}")}'
                f'{_heat_cell(r.get("canslim_sc"), 0, 30)}'
                f'{_heat_cell(r.get("minervini_sc"), 0, 30)}'
                f'{_heat_cell(r.get("inv_score"), 15, 70)}'
                f'<td style="background:{pct_c};color:{pct_tc};text-align:right;'
                f'font-size:10px;padding:2px 4px;font-weight:600">{pct:+.1f}%</td>'
                f'</tr>'
            )

    # Column widths (px): sym=80, company=180, sig=44, stg=40, fund=48, tech=48, rsi=44, cans=44, minv=44, invsc=48, pnl=58 = 682px total
    strip_html = f"""
    <div style="overflow-x:auto;max-height:500px;overflow-y:auto;
                border:1px solid #e5e7eb;border-radius:6px">
      <table style="border-collapse:collapse;table-layout:fixed;width:682px;
                    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',monospace">
        <colgroup>
          <col style="width:80px">
          <col style="width:180px">
          <col style="width:44px"><col style="width:40px">
          <col style="width:48px"><col style="width:48px">
          <col style="width:44px"><col style="width:44px">
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
            <th style="padding:5px 2px;text-align:center" title="Relative Strength Index">RSI</th>
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

      <h3 style="font-size:13px;font-weight:700;color:#374151;margin:16px 0 8px">
        All-Stock Heat Strip
        <span style="font-size:11px;font-weight:400;color:#6b7280;margin-left:8px">
          Signal · Stage · Fund · Tech · RSI · CANSLIM · Minervini · InvScore · P&amp;L%
        </span>
      </h3>
      {strip_html}
    </div>"""


def _write_eod_html(results: list[dict], snap_date: str) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    total_cost = sum(r["value_cost"] for r in results)
    total_mkt  = sum(r["value_mkt"]  for r in results)
    total_upnl = sum(r["upnl"]       for r in results)
    total_rpnl = sum(r["rpnl"]       for r in results)
    overall_pct = (total_mkt / total_cost - 1) * 100 if total_cost else 0

    cats: dict[str, list] = {"STRONG BUY": [], "BUY": [], "HOLD": [], "SELL": []}
    for r in results:
        cats.setdefault(r["composite"], cats["HOLD"]).append(r)
    for k in ("STRONG BUY", "BUY"):
        cats[k].sort(key=lambda x: -(x["inv_score"] or 0))
    cats["SELL"].sort(key=lambda x: (x["upnl_pct"] or 0))
    cats["HOLD"].sort(key=lambda x: -(x["inv_score"] or 0))

    # KPIs
    kpi_items = [
        ("Invested",       f"₹{total_cost/100000:.2f}L",   f"{len(results)} holdings"),
        ("Market Value",   f"₹{total_mkt/100000:.2f}L",    snap_date),
        ("Unrealised P&L", f"{'+'if total_upnl>=0 else ''}₹{total_upnl/100000:.2f}L",
                           f"{overall_pct:+.1f}%"),
        ("Realised P&L",   f"₹{total_rpnl/100000:.2f}L",   "booked"),
        ("Strong Buy",     str(len(cats["STRONG BUY"])),    "stocks"),
        ("Buy",            str(len(cats["BUY"])),           "stocks"),
        ("Hold",           str(len(cats["HOLD"])),          "stocks"),
        ("Sell",           str(len(cats["SELL"])),          "stocks"),
    ]
    bg_map2 = {
        "Strong Buy": "#dcfce7", "Buy": "#f0fdf4",
        "Hold": "#fffbeb", "Sell": "#fef2f2",
        "Unrealised P&L": "#f0fdf4" if total_upnl >= 0 else "#fef2f2",
    }
    vc_map2 = {"Unrealised P&L": "#16a34a" if total_upnl >= 0 else "#dc2626"}
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
            rsi_s  = f"{float(r['rsi_val']):.0f}"    if r["rsi_val"]    else "—"
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
              <td style="text-align:center">{rsi_s}</td>
              <td style="text-align:center;font-weight:600">{inv_s}</td>
              <td style="font-size:11px" title="CANSLIM/Minervini/eFund{ef_tag}">{cs_s}/{mn_s}/{ef_s}{ef_tag}</td>
              <td style="font-size:11px">{eq_s}/{sg_s}</td>
              <td style="font-size:11px">{trend_s}</td>
              {sig_cells}
              <td>{_sig_badge(r['composite'])}</td>
              <td style="font-size:11px">{sect_s}</td>
            </tr>
            <tr class="narr">
              <td colspan="16" style="font-size:11px;line-height:1.7">
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
                <th title="RSI">RSI</th>
                <th title="Investment Score">InvSc</th>
                <th title="CANSLIM/Minervini/eFund (★=derived from fund_details)">C/M/F</th>
                <th title="EarnQuality/SalesGrowth">EQ/SG</th>
                <th>Trend</th>
                <th title="Momentum">Mom.</th>
                <th title="CANSLIM">CANS.</th>
                <th title="Minervini">Miner.</th>
                <th title="Fundamental">Fund.</th>
                <th title="Value/PnL">Val.</th>
                <th title="RSI Strategy">RSI</th>
                <th>Signal</th><th>Sector</th>
              </tr></thead>
              <tbody>{rows}</tbody>
            </table>
          </div>
        </div>"""

    # Sector breakdown
    sector_stats: dict[str, dict] = {}
    for r in results:
        s = r["sector"] or "N/A"
        if s not in sector_stats:
            sector_stats[s] = {"cost": 0.0, "mkt": 0.0, "cnt": 0}
        sector_stats[s]["cost"] += r["value_cost"]
        sector_stats[s]["mkt"]  += r["value_mkt"]
        sector_stats[s]["cnt"]  += 1
    top_sectors = sorted(sector_stats.items(), key=lambda x: -x[1]["mkt"])[:15]
    sect_rows = "".join(
        f"<tr><td>{s}</td><td>{v['cnt']}</td>"
        f"<td style='text-align:right'>₹{v['mkt']/100000:.2f}L</td>"
        f"<td style='text-align:right;color:"
        f"{'#16a34a' if v['mkt']>=v['cost'] else '#dc2626'}'>"
        f"{(v['mkt']/v['cost']-1)*100:+.1f}%</td></tr>"
        for s, v in top_sectors
    )

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
            <li>{sum(1 for r in results if float(r['rsi_val'] or 50) >= 80)} stocks RSI &gt;80 (overbought) — trim</li>
            <li>{sum(1 for r in results if float(r['rsi_val'] or 50) <= 35)} stocks RSI &lt;35 (oversold) — watch bounce</li>
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
      <strong>Minervini VCP</strong> (/30 + Stage 2) ·
      <strong>Fundamental</strong> (eFund + EarnQuality + SalesGrowth; ★ = derived from fund_details) ·
      <strong>Value/PnL</strong> (loss-cut &lt;-30%, trail &gt;100%) ·
      <strong>RSI</strong> (oversold &lt;35, overbought &gt;80).
      Composite: ≥3 BUY → STRONG BUY · ≥2 BUY &gt; SELL → BUY ·
      ≥2 SELL &gt; BUY → SELL · else HOLD.
    </div>"""

    heatmap_html = _build_heatmap_section(results)

    now_ist = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(hours=5, minutes=30)
    body = f"""
    <div class="header">
      <h1>💼 My Portfolio — EOD Comprehensive Analysis</h1>
      <p>{now_ist.strftime('%d %b %Y %H:%M')} IST &nbsp;|&nbsp;
         Snapshot: {snap_date} &nbsp;|&nbsp; {len(results)} holdings &nbsp;|&nbsp;
         Strategies: Momentum · CANSLIM · Minervini · Fundamental · Value/PnL · RSI</p>
    </div>
    <div class="kpi-grid">{kpi_html}</div>
    {note}
    {heatmap_html}
    {two_col}
    {sections_html}
    """

    ts = now_ist.strftime("%Y-%m-%d %H:%M IST")
    html = (
        _HTML_HEAD.format(title="Portfolio EOD Analysis", refresh_meta="")
        + body
        + _HTML_FOOT.format(ts=ts)
    )
    EOD_REPORT.write_text(html, encoding="utf-8")
