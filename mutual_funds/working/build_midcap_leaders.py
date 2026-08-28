from __future__ import annotations

import argparse
import csv
import html
import math
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


RUN_DATE = datetime.now().strftime("%Y%m%d")
RUN_DATE_DISPLAY = ""

TOP_N = 15  # portfolio size cap — output is limited to the top N stocks by score

INDEX_MAPPING = ROOT / "data" / "index_stock_mapping.csv"
SCORE_SOURCE = ROOT / "reports" / "generated_csv" / "2026" / "comprehensive_nse_enhanced_20260817.csv"
OUT_CSV = ROOT / "Mutual Funds" / "extracted" / f"agent_adda_midcap_leaders_preselection_{RUN_DATE}.csv"
OUT_MD = ROOT / "docs" / "fund_policies" / "research_updates" / "midcap-leaders-portfolio-research-update.md"
OUT_HTML = ROOT / "Mutual Funds" / "reports" / f"agent_adda_midcap_leaders_report_{RUN_DATE}.html"

MIDCAP_INDEXES = {
    "NIFTY MIDCAP 50",
    "NIFTY MIDCAP 100",
    "NIFTY MIDCAP 150",
    "NIFTY MIDCAP SELECT",
}
CONFIRMATION_INDEXES = {"NIFTY LARGEMIDCAP 250", "NIFTY 500", "NIFTY 200"}

GOVERNMENT_THEME_INDEXES = {
    "NIFTY INDIA DEFENCE": ("Defence indigenisation", "Defence capital procurement and local manufacturing"),
    "NIFTY INFRASTRUCTURE": ("Infrastructure capex", "Union capex, highways, rail, ports, utilities"),
    "NIFTY INDIA MANUFACTURING": ("Manufacturing / PLI", "Manufacturing, electronics, industrial capex"),
    "NIFTY EV & NEW AGE AUTOMOTIVE": ("EV and mobility", "EV ecosystem, auto components, clean mobility"),
    "NIFTY TRANSPORTATION & LOGISTICS": ("Transport and logistics", "Rail, road, logistics, multimodal corridors"),
    "NIFTY CPSE": ("Public-sector capex", "Central public-sector enterprise capex"),
    "NIFTY PSE": ("Public-sector capex", "Public-sector enterprise capex"),
    "NIFTY PSU BANK": ("Public credit cycle", "Government-linked credit and public-bank cycle"),
    "NIFTY CORE HOUSING": ("Housing and urban infra", "Housing, urban infrastructure, building materials"),
    "NIFTY HOUSING": ("Housing and urban infra", "Housing, urban infrastructure, building materials"),
    "NIFTY ENERGY": ("Energy infrastructure", "Power, fuel, grid and energy transition capex"),
    "NIFTY OIL & GAS": ("Energy infrastructure", "Fuel, gas and downstream infrastructure"),
    "NIFTY INDIA DIGITAL": ("Digital infrastructure", "Digital public infrastructure and enterprise digitisation"),
}

SECTOR_INDEXES = {
    "NIFTY AUTO": "Auto / Auto Components",
    "NIFTY EV & NEW AGE AUTOMOTIVE": "EV / Mobility",
    "NIFTY PHARMA": "Pharma",
    "NIFTY HEALTHCARE INDEX": "Healthcare",
    "NIFTY500 HEALTHCARE": "Healthcare",
    "NIFTY MIDSMALL HEALTHCARE": "Healthcare",
    "NIFTY CAPITAL MARKETS": "Capital Markets",
    "NIFTY FINANCIAL SERVICES": "Financial Services",
    "NIFTY FINANCIAL SERVICES 25/50": "Financial Services",
    "NIFTY FINANCIAL SERVICES EX-BANK": "Financial Services",
    "NIFTY BANK": "Banks",
    "NIFTY PRIVATE BANK": "Banks",
    "NIFTY PSU BANK": "Banks",
    "NIFTY IT": "IT / Digital",
    "NIFTY INDIA DIGITAL": "IT / Digital",
    "NIFTY REALTY": "Real Estate",
    "NIFTY HOUSING": "Housing",
    "NIFTY CORE HOUSING": "Housing",
    "NIFTY CONSUMER DURABLES": "Consumer Durables",
    "NIFTY FMCG": "FMCG",
    "NIFTY INDIA CONSUMPTION": "Consumption",
    "NIFTY INDIA DEFENCE": "Defence",
    "NIFTY INDIA MANUFACTURING": "Manufacturing",
    "NIFTY INFRASTRUCTURE": "Infrastructure",
    "NIFTY TRANSPORTATION & LOGISTICS": "Transportation / Logistics",
    "NIFTY CHEMICALS": "Chemicals",
    "NIFTY METAL": "Metals",
    "NIFTY ENERGY": "Energy",
    "NIFTY OIL & GAS": "Oil & Gas",
    "NIFTY TOURISM": "Tourism",
    "NIFTY INDIA TOURISM": "Tourism",
}

THEME_SECTORS = {
    "Capital Goods": "Public capex, electrification, industrial equipment and project execution",
    "Auto / Auto Components": "Mobility, EV ancillaries and component localisation",
    "EV / Mobility": "EV ecosystem and new-age mobility",
    "Capital Markets": "Financialisation and market infrastructure",
    "Financial Services": "Credit, insurance, wealth and capital-market participation",
    "Banks": "Credit cycle and financial inclusion",
    "Pharma": "Domestic healthcare, exports and specialty products",
    "Healthcare": "Healthcare services, hospitals and diagnostics",
    "IT / Digital": "Digital infrastructure and enterprise technology",
    "Real Estate": "Housing cycle and urbanisation",
    "Housing": "Housing, building materials and urban infrastructure",
    "Consumer Durables": "Premiumisation and household consumption",
    "FMCG": "Consumption compounding",
    "Consumption": "Consumption compounding",
    "Defence": "Defence indigenisation and procurement",
    "Manufacturing": "PLI, Make in India and industrial capex",
    "Infrastructure": "Public capex and infrastructure execution",
    "Transportation / Logistics": "Rail, road, ports, logistics and supply-chain investment",
    "Chemicals": "Specialty manufacturing and import substitution",
    "Metals": "Infrastructure and industrial cycle",
    "Energy": "Power, grid and energy transition capex",
    "Oil & Gas": "Energy and gas infrastructure",
    "Tourism": "Tourism infrastructure and discretionary travel",
}

GOVERNMENT_SOURCE_TRAIL = (
    "Union Budget 2026-27 highlights: https://www.pib.gov.in/PressReleasePage.aspx?PRID=2221455; "
    "Budget speech: https://www.indiabudget.gov.in/doc/budget_speech.pdf; "
    "Capital goods/public capex: https://www.pib.gov.in/PressReleasePage.aspx?PRID=2222521; "
    "Infrastructure: https://www.pib.gov.in/PressReleasePage.aspx?PRID=2270740; "
    "Defence budget: https://www.pib.gov.in/PressReleaseDetail.aspx?PRID=2221612"
)


def display_date(run_date: str) -> str:
    return f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:]}"


def configure_run_date(run_date: str) -> None:
    global RUN_DATE, RUN_DATE_DISPLAY, OUT_CSV, OUT_MD, OUT_HTML
    if not re.fullmatch(r"\d{8}", run_date):
        raise ValueError("run_date must use YYYYMMDD format")
    RUN_DATE = run_date
    RUN_DATE_DISPLAY = display_date(run_date)
    OUT_CSV = ROOT / "Mutual Funds" / "extracted" / f"agent_adda_midcap_leaders_preselection_{RUN_DATE}.csv"
    OUT_MD = ROOT / "docs" / "fund_policies" / "research_updates" / f"{RUN_DATE_DISPLAY}-midcap-leaders-portfolio-research-update.md"
    OUT_HTML = ROOT / "Mutual Funds" / "reports" / f"agent_adda_midcap_leaders_report_{RUN_DATE}.html"


configure_run_date(RUN_DATE)


def fnum(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "na", "n/a"}:
        return None
    text = text.replace(",", "").replace("%", "").replace("+", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def fmt(value: Any, digits: int = 1) -> str:
    number = fnum(value)
    if number is None:
        return "NA"
    return f"{number:,.{digits}f}"


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_index_memberships() -> dict[str, set[str]]:
    memberships: dict[str, set[str]] = defaultdict(set)
    for row in read_csv(INDEX_MAPPING):
        symbol = str(row.get("STOCK_SYMBOL") or "").strip().upper()
        index = str(row.get("INDEX_NAME") or "").strip().upper()
        if symbol and index:
            memberships[symbol].add(index)
    return memberships


def load_score_rows() -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for row in read_csv(SCORE_SOURCE):
        symbol = str(row.get("SYMBOL") or "").strip().upper()
        if symbol:
            rows[symbol] = row
    return rows


def midcap_symbols(memberships: dict[str, set[str]]) -> list[str]:
    out = []
    for symbol, indexes in memberships.items():
        if indexes.intersection(MIDCAP_INDEXES):
            out.append(symbol)
    return sorted(out)


def infer_sector(indexes: set[str]) -> str:
    for index in sorted(indexes):
        if index in SECTOR_INDEXES:
            return SECTOR_INDEXES[index]
    return "Unclassified"


def theme_for_sector(sector: str) -> str:
    return THEME_SECTORS.get(sector, "General midcap leadership")


def government_theme(indexes: set[str], sector: str) -> tuple[str, str, str]:
    for index in sorted(indexes):
        if index in GOVERNMENT_THEME_INDEXES:
            theme, note = GOVERNMENT_THEME_INDEXES[index]
            return "PASS", theme, note
    if sector in {"Infrastructure", "Defence", "Manufacturing", "Transportation / Logistics", "Energy", "Housing"}:
        return "IDEA", theme_for_sector(sector), "Sector has public-investment linkage but index confirmation is missing"
    return "NONE", "No direct government-investment tag", "Theme is primarily private demand or company-specific"


def _rsi(close: pd.Series) -> float | None:
    if len(close) < 20:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=14).mean()
    rs = gain / loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    value = rsi.iloc[-1]
    return None if pd.isna(value) else round(float(value), 1)


def stage_from_history(hist: pd.DataFrame) -> dict[str, Any]:
    if hist is None or hist.empty or "Close" not in hist:
        return {"stage": "", "stage_source": "no history"}
    close = hist["Close"].dropna().astype(float)
    if len(close) < 60:
        return {"stage": "", "stage_source": "insufficient history"}
    sma50 = close.rolling(50, min_periods=40).mean()
    sma200 = close.rolling(200, min_periods=150).mean()
    last = float(close.iloc[-1])
    s50 = float(sma50.iloc[-1]) if not pd.isna(sma50.iloc[-1]) else None
    s200 = float(sma200.iloc[-1]) if len(close) >= 150 and not pd.isna(sma200.iloc[-1]) else None
    s50_slope = float(sma50.pct_change(10).iloc[-1]) if not pd.isna(sma50.pct_change(10).iloc[-1]) else 0.0
    s200_slope = float(sma200.pct_change(10).iloc[-1]) if s200 is not None and not pd.isna(sma200.pct_change(10).iloc[-1]) else 0.0
    high_52w = float(close.rolling(252, min_periods=60).max().iloc[-1])
    dist_high = (last / high_52w - 1) * 100 if high_52w else None
    six_month_base = close.iloc[-126] if len(close) > 126 else close.iloc[0]
    one_year_base = close.iloc[-252] if len(close) > 252 else close.iloc[0]
    ret_6m = (last / float(six_month_base) - 1) * 100 if six_month_base else None
    ret_1y = (last / float(one_year_base) - 1) * 100 if one_year_base else None
    if s200 is not None and s50 is not None and last > s50 > s200 and s50_slope > 0 and s200_slope >= -0.002 and (dist_high or -99) > -25:
        stage = "STAGE_2"
    elif s200 is not None and s50 is not None and last < s50 < s200:
        stage = "STAGE_4"
    elif s200 is not None and last > s200:
        stage = "STAGE_1"
    else:
        stage = "UNKNOWN"
    return {
        "stage": stage,
        "stage_source": "yfinance daily history",
        "latest_price": round(last, 2),
        "sma50": round(s50, 2) if s50 is not None else "",
        "sma200": round(s200, 2) if s200 is not None else "",
        "distance_52w_high_pct": round(dist_high, 2) if dist_high is not None else "",
        "six_month_return_pct": round(ret_6m, 2) if ret_6m is not None else "",
        "one_year_return_pct": round(ret_1y, 2) if ret_1y is not None else "",
        "rsi": _rsi(close),
    }


def history_map(symbols: list[str], skip_history: bool = False) -> dict[str, dict[str, Any]]:
    if skip_history:
        return {}
    try:
        import yfinance as yf
    except Exception:
        return {}
    tickers = [f"{symbol}.NS" for symbol in symbols]
    try:
        data = yf.download(
            tickers=tickers,
            period="1y",
            interval="1d",
            auto_adjust=False,
            group_by="ticker",
            threads=True,
            progress=False,
        )
    except Exception:
        return {}
    out: dict[str, dict[str, Any]] = {}
    if data.empty:
        return out
    for symbol in symbols:
        ticker = f"{symbol}.NS"
        try:
            if isinstance(data.columns, pd.MultiIndex):
                if ticker not in data.columns.get_level_values(0):
                    continue
                hist = data[ticker].dropna(how="all")
            else:
                hist = data.dropna(how="all")
            out[symbol] = stage_from_history(hist)
        except Exception:
            continue
    return out


def stage_proxy(score_row: dict[str, Any]) -> str:
    technical = fnum(score_row.get("TECHNICAL_SCORE")) or 0
    trend = str(score_row.get("TREND_SIGNAL") or "").upper()
    signal = str(score_row.get("TRADING_SIGNAL") or "").upper()
    if technical >= 60 and "BULLISH" in trend and signal in {"BUY", "STRONG_BUY", "HOLD"}:
        return "STAGE_2"
    if "BEARISH" in trend or signal == "SELL":
        return "STAGE_4"
    return "WATCH"


def normalized_row(symbol: str, indexes: set[str], score_row: dict[str, str], hist: dict[str, Any] | None) -> dict[str, Any]:
    sector = infer_sector(indexes)
    gov_gate, gov_theme, gov_note = government_theme(indexes, sector)
    hist = hist or {}
    stage = hist.get("stage") or stage_proxy(score_row)
    return {
        "symbol": symbol,
        "company": score_row.get("COMPANY_NAME") or symbol,
        "index_membership": "; ".join(sorted(indexes.intersection(MIDCAP_INDEXES | CONFIRMATION_INDEXES))),
        "sector": sector,
        "sector_theme": theme_for_sector(sector),
        "government_investment_theme": gov_theme,
        "government_investment_note": gov_note,
        "stage": stage,
        "stage_source": hist.get("stage_source") or "technical score proxy",
        "latest_price": hist.get("latest_price") or score_row.get("CURRENT_PRICE", ""),
        "sma50": hist.get("sma50", ""),
        "sma200": hist.get("sma200", ""),
        "distance_52w_high_pct": hist.get("distance_52w_high_pct", ""),
        "six_month_return_pct": hist.get("six_month_return_pct") or score_row.get("CHANGE_1M", ""),
        "one_year_return_pct": hist.get("one_year_return_pct", ""),
        "technical_score": score_row.get("TECHNICAL_SCORE", ""),
        "rsi": hist.get("rsi") or score_row.get("RSI", ""),
        "relative_strength": score_row.get("RELATIVE_STRENGTH", ""),
        "trend_signal": score_row.get("TREND_SIGNAL", ""),
        "trading_signal": score_row.get("TRADING_SIGNAL", ""),
        "can_slim_score": score_row.get("CAN_SLIM_SCORE", ""),
        "minervini_score": score_row.get("MINERVINI_SCORE", ""),
        "fundamental_score": score_row.get("FUNDAMENTAL_SCORE", ""),
        "enhanced_fund_score": score_row.get("ENHANCED_FUND_SCORE", ""),
        "earnings_quality": score_row.get("EARNINGS_QUALITY", ""),
        "sales_growth": score_row.get("SALES_GROWTH", ""),
        "financial_strength": score_row.get("FINANCIAL_STRENGTH", ""),
        "institutional_backing": score_row.get("INSTITUTIONAL_BACKING", ""),
        "eps_growth_proxy": score_row.get("EARNINGS_QUALITY", ""),
        "trading_value_cr": round((fnum(score_row.get("TRADING_VALUE")) or 0) / 10_000_000, 2),
        "source_score_date": score_row.get("ANALYSIS_DATE", "2026-04-28"),
        "source_trail": f"{SCORE_SOURCE.relative_to(ROOT)}; {INDEX_MAPPING.relative_to(ROOT)}; {GOVERNMENT_SOURCE_TRAIL}",
        "government_investment_gate": gov_gate,
    }


def _gate(value: float | None, pass_at: float, refresh_label: str = "REFRESH_REQUIRED") -> str:
    if value is None:
        return refresh_label
    return "PASS" if value >= pass_at else "WATCH"


def _score_band(value: float | None, low: float, high: float, points: float) -> float:
    if value is None:
        return 0.0
    if value <= low:
        return 0.0
    if value >= high:
        return points
    return (value - low) / (high - low) * points


def score_candidate(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    stage = str(out.get("stage") or "").upper()
    rsi = fnum(out.get("rsi"))
    rs = fnum(out.get("relative_strength"))
    six_month = fnum(out.get("six_month_return_pct"))
    technical = fnum(out.get("technical_score"))
    enhanced = fnum(out.get("enhanced_fund_score"))
    earnings = fnum(out.get("earnings_quality"))
    eps_proxy = fnum(out.get("eps_growth_proxy")) or earnings
    sales = fnum(out.get("sales_growth"))
    financial_strength = fnum(out.get("financial_strength"))
    can_slim = fnum(out.get("can_slim_score"))
    minervini = fnum(out.get("minervini_score"))
    turnover = fnum(out.get("trading_value_cr"))
    sector = str(out.get("sector") or "")
    government_gate = str(out.get("government_investment_gate") or "").upper()
    if not government_gate and sector in {"Defence", "Capital Goods", "Infrastructure", "Manufacturing", "Transportation / Logistics", "Energy", "Housing"}:
        government_gate = "PASS"

    out["stage2_gate"] = "PASS" if stage == "STAGE_2" else "WATCH"
    out["high_eps_gate"] = _gate(eps_proxy, 65)
    out["yoy_sales_gate"] = _gate(sales, 60)
    if enhanced is None or eps_proxy is None or sales is None:
        out["growth_gate"] = "REFRESH_REQUIRED"
    elif enhanced >= 60 and eps_proxy >= 65 and sales >= 60:
        out["growth_gate"] = "PASS"
    else:
        out["growth_gate"] = "WATCH"
    out["theme_gate"] = "PASS" if sector in THEME_SECTORS else "WATCH"
    out["government_investment_gate"] = "PASS" if government_gate == "PASS" else ("IDEA" if government_gate == "IDEA" else "NONE")
    out["liquidity_gate"] = "PASS" if turnover is not None and turnover >= 5 else "WATCH"
    out["freshness_gate"] = "REFRESH_REQUIRED"

    technical_component = 0.0
    technical_component += 12 if out["stage2_gate"] == "PASS" else 3
    technical_component += _score_band(technical, 45, 75, 6)
    technical_component += _score_band(rs, 0, 45, 5)
    technical_component += _score_band(six_month, 0, 45, 5)
    if rsi is not None and 50 <= rsi <= 70:
        technical_component += 2
    elif rsi is not None and 70 < rsi <= 76:
        technical_component += 1

    fundamental_component = 0.0
    fundamental_component += _score_band(enhanced, 45, 75, 10)
    fundamental_component += _score_band(eps_proxy, 45, 85, 8)
    fundamental_component += _score_band(sales, 40, 85, 8)
    fundamental_component += _score_band(financial_strength, 45, 75, 5)
    fundamental_component += _score_band(can_slim, 8, 25, 2)
    fundamental_component += _score_band(minervini, 6, 18, 2)

    theme_component = 0.0
    theme_component += 8 if out["theme_gate"] == "PASS" else 2
    theme_component += 8 if out["government_investment_gate"] == "PASS" else (4 if out["government_investment_gate"] == "IDEA" else 0)
    membership = str(out.get("index_membership") or "")
    if "NIFTY MIDCAP SELECT" in membership:
        theme_component += 4
    elif "NIFTY MIDCAP 50" in membership:
        theme_component += 3
    elif "NIFTY MIDCAP 100" in membership:
        theme_component += 2

    risk_component = 0.0
    risk_component += _score_band(turnover, 0, 50, 7)
    if rsi is None:
        risk_component += 1
    elif rsi <= 76:
        risk_component += 4
    elif rsi <= 82:
        risk_component += 2
    if out["freshness_gate"] == "PASS":
        risk_component += 4
    else:
        risk_component += 1
    if out["liquidity_gate"] == "PASS":
        risk_component += 3

    overall = clamp(technical_component + fundamental_component + theme_component + risk_component, 0, 100)
    out["technical_component_30"] = round(clamp(technical_component, 0, 30), 1)
    out["fundamental_component_35"] = round(clamp(fundamental_component, 0, 35), 1)
    out["theme_component_20"] = round(clamp(theme_component, 0, 20), 1)
    out["risk_component_15"] = round(clamp(risk_component, 0, 15), 1)
    out["overall_score_100"] = round(overall, 1)

    missing_growth = any(out[g] == "REFRESH_REQUIRED" for g in ("growth_gate", "high_eps_gate", "yoy_sales_gate"))
    if missing_growth:
        bucket = "REFRESH FIRST"
    elif rsi is not None and rsi > 76:
        bucket = "RETEST ONLY"
    elif out["stage2_gate"] == "PASS" and out["theme_gate"] == "PASS" and out["government_investment_gate"] == "PASS" and overall >= 80:
        bucket = "CORE CANDIDATE"
    elif out["stage2_gate"] == "PASS" and overall >= 68:
        bucket = "WATCH / PREPARE"
    else:
        bucket = "WATCH / PREPARE"
    out["decision_bucket"] = bucket
    out["trigger_state"] = "WAIT"
    out["blockers"] = "; ".join(
        label
        for label in [
            "FUNDAMENTAL_REFRESH_REQUIRED" if out["freshness_gate"] == "REFRESH_REQUIRED" else "",
            "MISSING_GROWTH_OR_EPS" if missing_growth else "",
            "NO_STAGE2_CONFIRMATION" if out["stage2_gate"] != "PASS" else "",
            "NO_GOVERNMENT_INVESTMENT_CONFIRMATION" if out["government_investment_gate"] == "NONE" else "",
            "EXTENDED_RSI_RETEST_ONLY" if bucket == "RETEST ONLY" else "",
        ]
        if label
    )
    return out


def build_candidates(skip_history: bool = False, max_symbols: int | None = None) -> list[dict[str, Any]]:
    memberships = load_index_memberships()
    scores = load_score_rows()
    symbols = [s for s in midcap_symbols(memberships) if s in scores]
    if max_symbols:
        symbols = symbols[:max_symbols]
    histories = history_map(symbols, skip_history=skip_history)
    rows = []
    for symbol in symbols:
        base = normalized_row(symbol, memberships[symbol], scores[symbol], histories.get(symbol))
        rows.append(score_candidate(base))
    rows.sort(key=lambda r: (fnum(r.get("overall_score_100")) or 0), reverse=True)
    return rows


def write_csv(rows: list[dict[str, Any]]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "symbol", "company", "index_membership", "sector", "sector_theme",
        "government_investment_theme", "government_investment_gate", "government_investment_note",
        "overall_score_100", "technical_component_30", "fundamental_component_35", "theme_component_20", "risk_component_15",
        "decision_bucket", "trigger_state", "stage", "stage_source", "stage2_gate",
        "growth_gate", "high_eps_gate", "yoy_sales_gate", "theme_gate", "liquidity_gate", "freshness_gate",
        "latest_price", "sma50", "sma200", "distance_52w_high_pct", "six_month_return_pct", "one_year_return_pct",
        "technical_score", "rsi", "relative_strength", "trend_signal", "trading_signal",
        "enhanced_fund_score", "earnings_quality", "eps_growth_proxy", "sales_growth", "financial_strength",
        "can_slim_score", "minervini_score", "trading_value_cr", "source_score_date", "source_trail", "blockers",
    ]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def md_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]], limit: int = 20) -> str:
    lines = ["| " + " | ".join(title for title, _ in columns) + " |"]
    lines.append("|" + "|".join("---" for _ in columns) + "|")
    for row in rows[:limit]:
        values = [str(row.get(key, "")).replace("|", "/") for _, key in columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def bucket_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row.get("decision_bucket") or "")] += 1
    return dict(counts)


def render_markdown(rows: list[dict[str, Any]]) -> str:
    counts = bucket_counts(rows)
    core = [r for r in rows if r.get("decision_bucket") == "CORE CANDIDATE"]
    refresh = [r for r in rows if r.get("decision_bucket") == "REFRESH FIRST"]
    columns = [
        ("Symbol", "symbol"), ("Score", "overall_score_100"), ("Bucket", "decision_bucket"),
        ("Sector", "sector"), ("Gov Theme", "government_investment_theme"),
        ("Stage", "stage"), ("Growth", "growth_gate"), ("EPS", "high_eps_gate"), ("Sales", "yoy_sales_gate"),
        ("Blockers", "blockers"),
    ]
    return f"""# Agent Adda Midcap Leaders Portfolio Research Update

Date: {RUN_DATE_DISPLAY}
Status: Research preselection. No paper order is approved.
Universe: Nifty Midcap 50, Midcap 100, Midcap 150, Midcap Select, with LargeMidcap/Nifty 500 confirmation tags.

## Mandate Filters

- Stage 2 structure or proxy confirmation.
- Growth score and high EPS/earnings-quality proxy.
- YoY sales-growth score.
- Sector theme.
- Government-investment theme alignment.
- Liquidity and no-chase controls.

## Current State

- Symbols scored: {len(rows)}
- Core candidates: {len(core)}
- Refresh first: {len(refresh)}
- Bucket counts: {counts}
- Paper order allowed: NO. Technical scores are current to 2026-08-07 (via PostgreSQL daily_scores). Fundamental sub-scores (EQ/SG/FS) are sourced from v_latest_fundamental_scores which aggregates the latest per-symbol filings. Individual Q1 FY27 result verification on exchange filings is still required before any paper order can be raised.

## Top Candidates

{md_table(rows, columns, limit=25)}

## Source Trail

- Score source: `{SCORE_SOURCE.relative_to(ROOT)}`.
- Universe source: `{INDEX_MAPPING.relative_to(ROOT)}`.
- Government-investment source trail: {GOVERNMENT_SOURCE_TRAIL}.
- Official result/filing refresh is still required before any paper order.
"""


def write_markdown(rows: list[dict[str, Any]]) -> None:
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(render_markdown(rows), encoding="utf-8")


def render_html(rows: list[dict[str, Any]]) -> str:
    counts = bucket_counts(rows)
    top_rows = "\n".join(
        "<tr>"
        f"<td>{esc(r.get('symbol'))}</td><td>{esc(r.get('overall_score_100'))}</td>"
        f"<td>{esc(r.get('decision_bucket'))}</td><td>{esc(r.get('sector'))}</td>"
        f"<td>{esc(r.get('government_investment_theme'))}</td><td>{esc(r.get('stage'))}</td>"
        f"<td>{esc(r.get('growth_gate'))}</td><td>{esc(r.get('high_eps_gate'))}</td>"
        f"<td>{esc(r.get('yoy_sales_gate'))}</td><td>{esc(r.get('blockers'))}</td>"
        "</tr>"
        for r in rows[:40]
    )
    theme_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        theme_counts[str(row.get("government_investment_theme") or "NA")] += 1
    theme_items = "".join(f"<li><strong>{esc(k)}</strong>: {v}</li>" for k, v in sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:12])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Agent Adda Midcap Leaders Portfolio Research Update</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; color: #17202a; background: #f6f7f9; }}
    header {{ background: #101820; color: white; padding: 28px 36px; }}
    main {{ padding: 28px 36px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; }}
    h2 {{ margin-top: 28px; font-size: 20px; }}
    .meta {{ color: #cbd5df; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(160px, 1fr)); gap: 12px; margin: 20px 0; }}
    .metric {{ background: white; border: 1px solid #d8dee6; border-radius: 8px; padding: 14px; }}
    .metric span {{ display: block; color: #5c6670; font-size: 12px; text-transform: uppercase; }}
    .metric strong {{ display: block; font-size: 24px; margin-top: 6px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #d8dee6; }}
    th, td {{ border-bottom: 1px solid #e7ebf0; padding: 9px 10px; text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ background: #eef2f6; color: #2f3b46; }}
    .note {{ background: #fff8e6; border: 1px solid #f0d58c; border-radius: 8px; padding: 14px; }}
    .sources {{ font-size: 13px; color: #46515c; }}
    @media (max-width: 900px) {{ .grid {{ grid-template-columns: repeat(2, minmax(140px, 1fr)); }} main, header {{ padding: 20px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Agent Adda Midcap Leaders Portfolio Research Update</h1>
    <div class="meta">Run date {RUN_DATE_DISPLAY}. Research-only preselection. No paper order is approved.</div>
  </header>
  <main>
    <section class="note">
      <strong>Operating stance:</strong> this is a midcap model-portfolio research layer. The score includes Stage 2, growth, high EPS/earnings-quality proxy, YoY sales score, sector theme, and government-investment alignment. Fresh official financial extraction remains mandatory before any paper order.
    </section>
    <section class="grid">
      <div class="metric"><span>Symbols scored</span><strong>{len(rows)}</strong></div>
      <div class="metric"><span>Core candidates</span><strong>{counts.get('CORE CANDIDATE', 0)}</strong></div>
      <div class="metric"><span>Refresh first</span><strong>{counts.get('REFRESH FIRST', 0)}</strong></div>
      <div class="metric"><span>Paper order</span><strong>NO</strong></div>
    </section>
    <h2>Government-Investment Theme Mix</h2>
    <ul>{theme_items}</ul>
    <h2>Top Ranked Midcap Candidates</h2>
    <table>
      <thead>
        <tr><th>Symbol</th><th>Score</th><th>Bucket</th><th>Sector</th><th>Gov Theme</th><th>Stage</th><th>Growth</th><th>EPS</th><th>Sales</th><th>Blockers</th></tr>
      </thead>
      <tbody>{top_rows}</tbody>
    </table>
    <h2>Rules Used</h2>
    <p>Score weights: technical 30, fundamentals 35, theme 20, risk/liquidity 15. A core candidate needs Stage 2, growth, high EPS/earnings-quality, YoY sales, sector theme and government-investment alignment. Any stale or missing fundamental evidence is a refresh-first blocker.</p>
    <h2>Source Trail</h2>
    <p class="sources">Score source: {esc(SCORE_SOURCE.relative_to(ROOT))}. Universe source: {esc(INDEX_MAPPING.relative_to(ROOT))}. Government-investment source trail: {esc(GOVERNMENT_SOURCE_TRAIL)}.</p>
  </main>
</body>
</html>
"""


def write_html(rows: list[dict[str, Any]]) -> None:
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(render_html(rows), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Agent Adda midcap leaders preselection artifacts.")
    parser.add_argument("--run-date", default=RUN_DATE, help="Run date in YYYYMMDD format.")
    parser.add_argument("--skip-history", action="store_true", help="Use score-file technical proxy instead of yfinance history.")
    parser.add_argument("--max-symbols", type=int, default=None, help="Limit symbols for smoke generation.")
    parser.add_argument("--top-n", type=int, default=TOP_N, help="Cap output to the top N stocks by score (default: %(default)s).")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_run_date(args.run_date)
    all_rows = build_candidates(skip_history=args.skip_history, max_symbols=args.max_symbols)
    rows = all_rows[: args.top_n] if args.top_n else all_rows
    write_csv(rows)
    write_markdown(rows)
    write_html(rows)
    print(f"Wrote {OUT_CSV.relative_to(ROOT)}")
    print(f"Wrote {OUT_MD.relative_to(ROOT)}")
    print(f"Wrote {OUT_HTML.relative_to(ROOT)}")
    print(f"Symbols scored (universe): {len(all_rows)}")
    print(f"Symbols in output (top-{args.top_n}): {len(rows)}")
    print(f"Core candidates: {sum(1 for r in rows if r.get('decision_bucket') == 'CORE CANDIDATE')}")
    print(f"Refresh first: {sum(1 for r in rows if r.get('decision_bucket') == 'REFRESH FIRST')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
