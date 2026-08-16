#!/usr/bin/env python3
"""Build the Agent Adda small/micro-cap super performers HTML report."""

from __future__ import annotations

import html
import json
import math
import re
import shutil
import statistics
import urllib.request
import http.cookiejar
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCREEN_CSV = Path("/tmp/agent_adda_smallcap/smallcap_super_screen_ranked.csv")
INDEX_CSV = ROOT / "data" / "nse_index_data.csv"
DATA_SUMMARY = ROOT / "data" / "data_summary.json"
INTRADAY_MD = ROOT / "logs" / "intraday_alerts_fno_latest_20260806_111746.md"
OUT_DIR = ROOT / "reports" / "generated"
LATEST_DIR = ROOT / "reports" / "latest"
REPORT_STEM = "agent_adda_smallcap_super_performers_20260806_1652"
REPORT_TITLE = "Agent Adda Market Intelligence: Small & Micro Cap Super Performers"


INDEX_WATCHLIST = [
    "NIFTY 50",
    "NIFTY 500",
    "NIFTY SMALLCAP 50",
    "NIFTY SMALLCAP 100",
    "NIFTY SMALLCAP 250",
    "NIFTY SMALLCAP 500",
    "NIFTY MICROCAP 250",
    "NIFTY MIDSMALLCAP 400",
    "INDIA VIX",
]


SELECTED_SYMBOLS = [
    "MARKSANS",
    "SKIPPER",
    "ASTRAMICRO",
    "HONASA",
    "RATEGAIN",
    "MINDACORP",
    "SYRMA",
    "GRANULES",
    "EMCURE",
    "GLAND",
    "SANSERA",
]


COMPANY_SOURCES: dict[str, list[tuple[str, str]]] = {
    "ASTRAMICRO": [
        ("Astra Microwave investor results page", "https://astramwp.com/financial-results-2/"),
        ("Business Standard - HAL order", "https://www.business-standard.com/markets/capital-market-news/astra-microwave-products-jumps-after-securing-rs-2-205-crore-hal-order-126073100334_1.html"),
        ("Economic Times - Q4 result", "https://m.economictimes.com/markets/stocks/earnings/astra-microwave-q4-results-cons-pat-jumps-44-to-rs-106-crore-co-announces-rs-2-4/share-dividend/articleshow/131323738.cms"),
    ],
    "RATEGAIN": [
        ("RateGain Q4 FY26 press release", "https://rategain.com/press-release/rategain-q4fy26-results-travel-intent-data-company/"),
        ("Angel One Q4 FY26 summary", "https://www.angelone.in/news/stocks/rategain-q4-fy26-results-reported-revenue-of-rs-716-crore-becomes-world-s-largest-travel-intent-data-company"),
    ],
    "MARKSANS": [
        ("Marksans investor presentation", "https://www.marksanspharma.com/pdf/investor-presentation-may-2026.pdf"),
        ("Business Standard - Q4 PAT jump", "https://www.business-standard.com/markets/capital-market-news/marksans-pharma-soars-after-q4-pat-jumps-64-yoy-126052600911_1.html"),
    ],
    "SKIPPER": [
        ("NSE Skipper Q4 FY26 transcript", "https://nsearchives.nseindia.com/corporate/skipper_05052026133011_Transcriptintimation.pdf"),
        ("ICICI Direct rapid result", "https://www.icicidirect.com/research/equity/rapid-results/skipper-ltd"),
    ],
    "SYRMA": [
        ("Syrma investor relations", "https://www.syrmasgs.com/investor-relations/"),
        ("Economic Times - Syrma Q4", "https://m.economictimes.com/industry/cons-products/electronics/syrma-sgs-q4-results-net-profit-surges-67-to-119-crore-driven-by-strong-revenue-growth/articleshow/131022614.cms"),
        ("Times of India - export plan", "https://timesofindia.indiatimes.com/city/chennai/syrma-sgs-eyes-rs-1500-cr-exports-in-fy27-on-global-supply-chain-shift/articleshow/132813076.cms"),
    ],
    "HONASA": [
        ("Honasa investor relations", "https://honasa.in/pages/investor"),
        ("Mint - Honasa Q4", "https://www.livemint.com/market/stock-market-news/mamaearth-parent-honasa-consumer-share-price-soars-10-5-to-its-52-week-high-on-robust-q4-results-maiden-dividend-11779425098517.html"),
        ("Business Standard - Honasa Q4", "https://www.business-standard.com/markets/capital-market-news/honasa-consumer-jumps-after-q4-pat-surges-178-126052200376_1.html"),
    ],
    "MINDACORP": [
        ("Business Standard - Minda Corp Q4", "https://www.business-standard.com/companies/quarterly-results/minda-corp-q4-result-profit-up-7-3-at-124-cr-revenue-grows-to-1-704-cr-126052201150_1.html"),
        ("ET Auto - Minda Corp Q4", "https://auto.economictimes.indiatimes.com/news/industry/minda-corp-q4-fy26-net-profit-surges-139-revenue-grows-29/131263940"),
    ],
    "GRANULES": [
        ("Granules quarterly results", "https://granulesindia.com/investors/financial-reports/quarterly-results/"),
        ("ET Pharma - Granules Q1 FY27", "https://pharma.economictimes.indiatimes.com/news/financial-performance/granules-india-q1-fy27-net-profit-soars-60-to-180-cr-on-complex-generics-gain/132533688"),
    ],
    "GLAND": [
        ("Gland Pharma Q4 FY26 press release", "https://glandpharma.com/images/Press_Release_Q4_FY26.pdf"),
        ("ET Pharma - Gland Q4", "https://pharma.economictimes.indiatimes.com/news/financial-performance/gland-pharma-reports-22-revenue-surge-to-1742-crore-in-q4-fy26-net-profit-doubles/131174278"),
        ("Times of India - Neuland CDMO partnership", "https://timesofindia.indiatimes.com/city/hyderabad/gland-pharma-neuland-enter-into-long-term-sterile-api-cdmo-partnership/articleshow/132935788.cms"),
    ],
    "SANSERA": [
        ("Sansera Q4 FY26 earnings release", "https://nsearchives.nseindia.com/corporate/SANSERA_21052026062942_earnings.pdf"),
        ("Yahoo Finance - Sansera Q4", "https://finance.yahoo.com/markets/stocks/articles/sansera-engineering-ltd-bom-543358-010209906.html"),
    ],
    "EMCURE": [
        ("Emcure Q4 FY26 press release", "https://www.emcure.com/wp-content/uploads/2026/05/Press_Release_Emcure_Q4FY26.pdf"),
        ("ET Pharma - Emcure Q4", "https://pharma.economictimes.indiatimes.com/news/financial-performance/emcure-posts-2470-crore-in-q4-fy26-net-profit-soars-24/130842665"),
    ],
}


SOURCE_SNIPPETS = {
    "ASTRAMICRO": "HAL order of about INR 2,205 crore is a material defence-electronics catalyst; Q4 PAT in the local data is INR 106 crore with operating margin above 30%.",
    "RATEGAIN": "Record Q4 revenue base is acquisition-assisted; organic durability and integration delivery remain the watch items.",
    "MARKSANS": "Pharma earnings are cleaner than the price tape: strong Q4 PAT growth, cash conversion above 1x PAT, low debt proxy.",
    "SKIPPER": "Power T&D/capital-goods cycle remains the sector support; debt intensity and working-capital discipline need continued tracking.",
    "SYRMA": "EMS demand and export optionality are strong, but margin and raw-material/logistics pressure need monitoring.",
    "HONASA": "Growth is back after a weak phase, but the stock still needs proof of repeatable brand scale and margin durability.",
    "MINDACORP": "Result feeds conflict on headline profit growth basis; treat it as a watchlist name until the filing basis is reconciled.",
    "GRANULES": "Q1 FY27 is the freshest result in this pack, with complex generics supporting margin expansion.",
    "GLAND": "Q4 rebound is strong and the CDMO partnership is strategically relevant; annual PAT CAGR remains the main historical weak spot.",
    "SANSERA": "Aerospace/defence and industrial mix is improving, but the stock is technically extended with RSI above 75.",
    "EMCURE": "Steady pharma growth with FY26 scale, but leverage and execution after bolt-on deals remain watch items.",
}


def esc(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return html.escape(str(value), quote=True)


def fmt_num(value: object, digits: int = 1, suffix: str = "") -> str:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return "n/a"
        x = float(value)
    except Exception:
        return "n/a"
    if abs(x) >= 1000:
        return f"{x:,.{digits}f}{suffix}"
    return f"{x:.{digits}f}{suffix}"


def fmt_pct(value: object, digits: int = 1) -> str:
    return fmt_num(value, digits, "%")


def signed_pct(value: object, digits: int = 1) -> str:
    try:
        x = float(value)
    except Exception:
        return "n/a"
    return f"{x:+.{digits}f}%"


def css_class_for_pct(value: object) -> str:
    try:
        x = float(value)
    except Exception:
        return "neutral"
    if x >= 0.01:
        return "pos"
    if x <= -0.01:
        return "neg"
    return "neutral"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def bar(value: object, min_v: float, max_v: float, label: str = "", cls: str = "") -> str:
    try:
        x = float(value)
    except Exception:
        x = min_v
    pct = 100.0 * (clamp(x, min_v, max_v) - min_v) / (max_v - min_v)
    label_html = f"<span>{esc(label or fmt_num(x, 1))}</span>"
    return (
        f"<div class='mini-bar {esc(cls)}' aria-label='{esc(label or x)}'>"
        f"<i style='width:{pct:.1f}%'></i>{label_html}</div>"
    )


def read_data_summary() -> dict[str, str]:
    if not DATA_SUMMARY.exists():
        return {}
    try:
        data = json.loads(DATA_SUMMARY.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(value, list) and value:
            out[key] = " to ".join(str(item) for item in value)
        else:
            out[key] = str(value)
    return out


def fetch_nse_index_snapshot() -> tuple[str, list[dict[str, object]], str]:
    """Fetch NSE allIndices; fallback to the latest captured values for this report."""
    fallback_time = "2026-08-06 16:52:22 IST"
    fallback_rows = [
        {"index": "NIFTY 50", "last": 24636.0, "variation": 11.35, "percentChange": 0.05, "advances": "15", "declines": "34", "unchanged": "1", "yearHigh": 26373.2, "yearLow": 22182.55},
        {"index": "NIFTY 500", "last": 23729.45, "variation": -6.1, "percentChange": -0.03, "advances": "202", "declines": "293", "unchanged": "5", "yearHigh": 24144.2, "yearLow": 20385.65},
        {"index": "NIFTY SMALLCAP 100", "last": 19878.25, "variation": 94.55, "percentChange": 0.48, "advances": "53", "declines": "47", "unchanged": "0", "yearHigh": 19936.55, "yearLow": 14986.0},
        {"index": "INDIA VIX", "last": 12.11, "variation": 0.05, "percentChange": 0.39, "advances": None, "declines": None, "unchanged": None, "yearHigh": 28.91, "yearLow": 8.72},
        {"index": "NIFTY SMALLCAP 50", "last": 9945.05, "variation": 101.9, "percentChange": 1.04, "advances": "30", "declines": "20", "unchanged": "0", "yearHigh": 9968.0, "yearLow": 7338.35},
        {"index": "NIFTY SMALLCAP 250", "last": 18358.65, "variation": 36.7, "percentChange": 0.2, "advances": "120", "declines": "130", "unchanged": "0", "yearHigh": 18407.75, "yearLow": 14143.45},
        {"index": "NIFTY MIDSMALLCAP 400", "last": 21515.3, "variation": -41.45, "percentChange": -0.19, "advances": "168", "declines": "229", "unchanged": "3", "yearHigh": 21620.15, "yearLow": 17390.85},
        {"index": "NIFTY MICROCAP 250", "last": 26048.35, "variation": 91.65, "percentChange": 0.35, "advances": "113", "declines": "136", "unchanged": "3", "yearHigh": 26188.85, "yearLow": 18858.5},
        {"index": "NIFTY SMALLCAP 500", "last": 20894.05, "variation": 54.5, "percentChange": 0.26, "advances": "232", "declines": "267", "unchanged": "3", "yearHigh": 20959.7, "yearLow": 15960.2},
    ]
    try:
        ua = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        )
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        for url in ("https://www.nseindia.com/", "https://www.nseindia.com/market-data/live-equity-market"):
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": ua,
                        "Accept": "text/html,*/*",
                        "Accept-Language": "en-US,en;q=0.9",
                    },
                )
                opener.open(req, timeout=10).read(128)
            except Exception:
                pass
        req = urllib.request.Request(
            "https://www.nseindia.com/api/allIndices",
            headers={
                "User-Agent": ua,
                "Accept": "application/json,text/plain,*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.nseindia.com/market-data/live-equity-market",
            },
        )
        raw = opener.open(req, timeout=15).read()
        data = json.loads(raw)
        rows = []
        wanted = set(INDEX_WATCHLIST)
        for row in data.get("data", []):
            name = row.get("index") or row.get("indexSymbol")
            if name in wanted:
                rows.append(
                    {
                        "index": name,
                        "last": row.get("last"),
                        "variation": row.get("variation"),
                        "percentChange": row.get("percentChange"),
                        "advances": row.get("advances"),
                        "declines": row.get("declines"),
                        "unchanged": row.get("unchanged"),
                        "yearHigh": row.get("yearHigh"),
                        "yearLow": row.get("yearLow"),
                    }
                )
        if rows:
            fetched_at = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S IST")
            return fetched_at, rows, "NSE allIndices live API"
    except Exception:
        pass
    return fallback_time, fallback_rows, "NSE allIndices live API fallback captured at 16:52 IST"


def index_history_metrics() -> dict[str, dict[str, object]]:
    if not INDEX_CSV.exists():
        return {}
    df = pd.read_csv(INDEX_CSV)
    if df.empty:
        return {}
    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"])
    name_map = {
        "Nifty 50": "NIFTY 50",
        "Nifty 500": "NIFTY 500",
        "Nifty Smallcap 500": "NIFTY SMALLCAP 500",
        "NIFTY MICROCAP250": "NIFTY MICROCAP 250",
        "Nifty MidSmall 50 50": "NIFTY MIDSMALL 50:50",
        "India VIX": "INDIA VIX",
    }
    out: dict[str, dict[str, object]] = {}
    for raw_name, label in name_map.items():
        sub = df.loc[df["SYMBOL"].eq(raw_name)].sort_values("TIMESTAMP")
        if sub.empty:
            continue
        close = sub["CLOSE"].astype(float)
        last = close.iloc[-1]
        metric: dict[str, object] = {"last_eod": last, "as_of": sub["TIMESTAMP"].iloc[-1].date().isoformat()}
        for days, key in [(20, "ret20"), (60, "ret60"), (120, "ret120")]:
            if len(close) > days and close.iloc[-days - 1] != 0:
                metric[key] = (last / close.iloc[-days - 1] - 1.0) * 100.0
        for window, key in [(50, "ma50"), (200, "ma200")]:
            if len(close) >= window:
                ma = close.rolling(window).mean().iloc[-1]
                metric[key] = ma
                metric[f"vs{window}"] = (last / ma - 1.0) * 100.0 if ma else None
        delta = close.diff()
        up = delta.clip(lower=0).rolling(14).mean()
        down = (-delta.clip(upper=0)).rolling(14).mean()
        rs = up / down.replace(0, float("nan"))
        rsi = 100.0 - (100.0 / (1.0 + rs))
        if not math.isnan(float(rsi.iloc[-1])):
            metric["rsi"] = float(rsi.iloc[-1])
        out[label] = metric
    return out


def parse_intraday() -> dict[str, str]:
    if not INTRADAY_MD.exists():
        return {"time": "n/a", "stance": "WAIT", "headline": "No current intraday report found."}
    text = INTRADAY_MD.read_text(encoding="utf-8", errors="ignore")
    def grab(pattern: str, default: str = "n/a") -> str:
        m = re.search(pattern, text, flags=re.MULTILINE)
        return m.group(1).strip() if m else default
    return {
        "time": grab(r"^- Time:\s*(.+)$"),
        "market": grab(r"^- Market:\s*(.+)$"),
        "stance": grab(r"^- Stance:\s*(.+)$", "WAIT"),
        "headline": grab(r"^- Headline:\s*(.+)$", "Wait; do not force trades right now."),
        "action": grab(r"^- Action:\s*(.+)$", "Stand aside until fresh alerts confirm."),
        "fresh_alerts": grab(r"^- Fresh alerts:\s*(.+)$", "0"),
        "total_candidates": grab(r"^- Total candidates:\s*(.+)$", "0"),
    }


def load_screen() -> pd.DataFrame:
    if not SCREEN_CSV.exists():
        raise FileNotFoundError(f"Missing screen file: {SCREEN_CSV}")
    df = pd.read_csv(SCREEN_CSV)
    df = df.sort_values("overall", ascending=False).reset_index(drop=True)
    return df


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        x = float(value)
        if math.isnan(x):
            return default
        return x
    except Exception:
        return default


def action_label(row: pd.Series) -> tuple[str, str]:
    symbol = str(row.get("Symbol", ""))
    rsi = safe_float(row.get("rsi_calc"))
    from52 = safe_float(row.get("from52"))
    ret60 = safe_float(row.get("ret60"))
    ocf = safe_float(row.get("ocf_pat_proxy"), default=0.0)
    debt = safe_float(row.get("bs_debt_to_equity_proxy"), default=0.0)
    signal = str(row.get("stg_trading_signal", "")).upper()
    q_date = str(row.get("q_period_label", ""))
    if symbol == "MINDACORP":
        return "WATCH - VERIFY", "Headline result-growth basis conflicts across feeds."
    if rsi >= 72 or from52 > -1.0:
        return "WATCH - EXTENDED", "Trend is strong but entry risk is elevated near highs."
    if signal == "BUY" and ret60 > 25 and ocf >= 1.0 and debt <= 0.7:
        return "CORE WATCH", "Momentum, balance-sheet, and cash-flow checks align."
    if ret60 > 30 and safe_float(row.get("q_rev_yoy_calc")) > 20 and safe_float(row.get("q_pat_yoy_calc")) > 20:
        return "GROWTH WATCH", "Earnings acceleration and relative strength align."
    if q_date.startswith("Jun 2026"):
        return "FRESH RESULT WATCH", "Latest quarter is fresher than most of the pack."
    return "WATCH ONLY", "Needs cleaner entry, fresher filing, or stronger confirmation."


def company_read(row: pd.Series) -> dict[str, str]:
    symbol = str(row.get("Symbol"))
    label, reason = action_label(row)
    industry = str(row.get("industry", ""))
    tech = []
    if safe_float(row.get("ret60")) >= 50:
        tech.append("very strong 3M trend")
    elif safe_float(row.get("ret60")) >= 25:
        tech.append("strong 3M trend")
    elif safe_float(row.get("ret60")) >= 15:
        tech.append("constructive 3M trend")
    else:
        tech.append("moderate trend")
    if safe_float(row.get("vs50")) >= 10:
        tech.append("price well above 50-DMA")
    elif safe_float(row.get("vs50")) >= 3:
        tech.append("price above 50-DMA")
    else:
        tech.append("near 50-DMA")
    rsi = safe_float(row.get("rsi_calc"))
    if rsi >= 72:
        tech.append("RSI is extended")
    elif rsi >= 60:
        tech.append("RSI is constructive")
    elif rsi >= 50:
        tech.append("RSI is neutral-positive")
    else:
        tech.append("RSI is soft")
    financial = []
    if safe_float(row.get("q_rev_yoy_calc")) > 25:
        financial.append("revenue growth is strong")
    elif safe_float(row.get("q_rev_yoy_calc")) > 10:
        financial.append("revenue growth is healthy")
    else:
        financial.append("revenue growth is modest")
    if safe_float(row.get("q_pat_yoy_calc")) > 50:
        financial.append("PAT growth is high")
    elif safe_float(row.get("q_pat_yoy_calc")) > 15:
        financial.append("PAT growth is positive")
    else:
        financial.append("PAT growth needs verification")
    if safe_float(row.get("ocf_pat_proxy"), 0) >= 1.0:
        financial.append("cash conversion is supportive")
    else:
        financial.append("cash conversion is the watch item")
    debt = safe_float(row.get("bs_debt_to_equity_proxy"), 0.0)
    if debt <= 0.2:
        leverage = "low leverage proxy"
    elif debt <= 0.7:
        leverage = "manageable leverage proxy"
    else:
        leverage = "leverage needs caution"
    sector = {
        "Capital Goods": "sector tailwind from defence, EMS, power T&D, industrial capex, or precision manufacturing is visible in the screen.",
        "Healthcare": "healthcare/pharma leadership is quality-led, but US/regulatory/product concentration risk must stay visible.",
        "Information Technology": "IT/SaaS leadership is narrower and depends on growth durability rather than broad IT beta.",
        "Automobile and Auto Components": "auto-ancillary momentum is tied to premiumisation, exports, and EV content.",
        "Fast Moving Consumer Goods": "FMCG names need brand-led growth and margin repeatability after rerating.",
    }.get(industry, "sector read is stock-specific; avoid extrapolating one strong chart to the whole industry.")
    return {
        "label": label,
        "reason": reason,
        "technical": "; ".join(tech) + ".",
        "financial": "; ".join(financial) + f"; {leverage}.",
        "sector": sector,
        "source_note": SOURCE_SNIPPETS.get(symbol, "External source verification is partial; rely on local screen plus company filings."),
    }


def table(rows: list[list[str]], headers: list[str], cls: str = "") -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "\n".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<div class='table-wrap {esc(cls)}'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def source_links(symbol: str) -> str:
    items = COMPANY_SOURCES.get(symbol, [])
    if not items:
        return "<span class='muted'>Local evidence only</span>"
    links = []
    for name, url in items:
        links.append(f"<a href='{esc(url)}' target='_blank' rel='noopener'>{esc(name)}</a>")
    return "<br>".join(links)


def index_snapshot_html(rows: list[dict[str, object]], history: dict[str, dict[str, object]]) -> str:
    rank = {name: i for i, name in enumerate(INDEX_WATCHLIST)}
    rows = sorted(rows, key=lambda r: rank.get(str(r.get("index")), 999))
    rendered = []
    for row in rows:
        name = str(row.get("index"))
        adv = safe_float(row.get("advances"), float("nan"))
        dec = safe_float(row.get("declines"), float("nan"))
        breadth = "n/a"
        breadth_bar = ""
        if not math.isnan(adv) and not math.isnan(dec) and (adv + dec) > 0:
            breadth = f"{int(adv)}A / {int(dec)}D"
            breadth_bar = bar(adv / (adv + dec) * 100, 0, 100, f"{adv / (adv + dec) * 100:.0f}% adv", "green")
        hist = history.get(name) or history.get(name.replace("CAP ", "CAP"))
        hist_bits = []
        if hist:
            for key, label in (("ret20", "1M"), ("ret60", "3M"), ("vs50", "vs50D"), ("rsi", "RSI")):
                if key in hist:
                    suffix = "%" if key != "rsi" else ""
                    hist_bits.append(f"{label} {fmt_num(hist[key], 1, suffix)}")
        else:
            hist_bits.append("live-only read")
        rendered.append(
            [
                f"<b>{esc(name)}</b>",
                fmt_num(row.get("last"), 2),
                f"<span class='{css_class_for_pct(row.get('percentChange'))}'>{signed_pct(row.get('percentChange'))}</span>",
                esc(breadth) + breadth_bar,
                esc("; ".join(hist_bits)),
            ]
        )
    return table(rendered, ["Index", "Live level", "Day move", "Breadth", "Local EOD technical context"])


def sector_summary_html(df: pd.DataFrame) -> str:
    grouped = []
    for industry, sub in df.groupby("industry", dropna=False):
        grouped.append(
            {
                "industry": str(industry),
                "count": len(sub),
                "avg_overall": safe_float(sub["overall"].mean()),
                "avg_ret60": safe_float(sub["ret60"].mean()),
                "buy_count": int((sub["stg_trading_signal"].astype(str).str.upper() == "BUY").sum()),
            }
        )
    grouped = sorted(grouped, key=lambda x: (x["count"], x["avg_overall"]), reverse=True)[:12]
    rows = []
    max_count = max([g["count"] for g in grouped] or [1])
    for g in grouped:
        rows.append(
            [
                f"<b>{esc(g['industry'])}</b>",
                f"{g['count']}",
                bar(g["count"], 0, max_count, str(g["count"]), "blue"),
                fmt_pct(g["avg_ret60"]),
                fmt_num(g["avg_overall"], 1),
                str(g["buy_count"]),
            ]
        )
    return table(rows, ["Sector bucket", "Stage 2 names", "Weight", "Avg 3M return", "Avg screen score", "BUY flags"])


def top_screen_table(df: pd.DataFrame, limit: int = 30) -> str:
    rows = []
    for _, row in df.head(limit).iterrows():
        label, reason = action_label(row)
        rows.append(
            [
                f"<b>{esc(row.get('Symbol'))}</b><br><span class='muted'>{esc(row.get('company'))}</span>",
                esc(row.get("industry")),
                esc(row.get("buckets")),
                fmt_num(row.get("price"), 2),
                f"<span class='{css_class_for_pct(row.get('ret60'))}'>{signed_pct(row.get('ret60'))}</span>",
                f"<span class='{css_class_for_pct(row.get('ret120'))}'>{signed_pct(row.get('ret120'))}</span>",
                f"<span class='{css_class_for_pct(row.get('vs50'))}'>{signed_pct(row.get('vs50'))}</span>",
                fmt_num(row.get("rsi_calc"), 1),
                esc(row.get("stg_trading_signal")),
                fmt_num(row.get("stg_enhanced_fund_score"), 1),
                fmt_num(row.get("overall"), 1),
                f"<span class='pill'>{esc(label)}</span><br><span class='muted'>{esc(reason)}</span>",
            ]
        )
    return table(
        rows,
        [
            "Name",
            "Sector",
            "Index bucket",
            "Price",
            "3M",
            "6M",
            "vs 50-DMA",
            "RSI",
            "Signal",
            "Fund score",
            "Overall",
            "Desk label",
        ],
        "dense",
    )


def selected_cards(df: pd.DataFrame) -> str:
    by_symbol = {str(row["Symbol"]): row for _, row in df.iterrows()}
    cards = []
    for symbol in SELECTED_SYMBOLS:
        if symbol not in by_symbol:
            continue
        row = by_symbol[symbol]
        read = company_read(row)
        cards.append(
            f"""
            <article class="company-card" id="{esc(symbol)}">
              <div class="company-head">
                <div>
                  <h3>{esc(symbol)} <span>{esc(row.get('company'))}</span></h3>
                  <p>{esc(row.get('industry'))} | {esc(row.get('buckets'))}</p>
                </div>
                <div class="label-stack">
                  <span class="pill hot">{esc(read['label'])}</span>
                  <span class="score">Overall {fmt_num(row.get('overall'), 1)}</span>
                </div>
              </div>
              <div class="metric-grid">
                <div><b>{fmt_num(row.get('price'), 2)}</b><span>Price</span></div>
                <div><b class="{css_class_for_pct(row.get('ret60'))}">{signed_pct(row.get('ret60'))}</b><span>3M return</span></div>
                <div><b class="{css_class_for_pct(row.get('ret120'))}">{signed_pct(row.get('ret120'))}</b><span>6M return</span></div>
                <div><b>{fmt_num(row.get('rsi_calc'), 1)}</b><span>RSI</span></div>
                <div><b>{fmt_num(row.get('stg_enhanced_fund_score'), 1)}</b><span>Fund score</span></div>
                <div><b>{fmt_num(row.get('ocf_pat_proxy'), 2)}x</b><span>OCF/PAT</span></div>
              </div>
              <div class="bar-stack">
                <div><span>3M return</span>{bar(row.get('ret60'), -10, 110, signed_pct(row.get('ret60')), 'green')}</div>
                <div><span>vs 50-DMA</span>{bar(row.get('vs50'), -10, 35, signed_pct(row.get('vs50')), 'blue')}</div>
                <div><span>RSI</span>{bar(row.get('rsi_calc'), 30, 90, fmt_num(row.get('rsi_calc'), 1), 'amber')}</div>
              </div>
              <div class="read-grid">
                <section><h4>Technical View</h4><p>{esc(read['technical'])}</p></section>
                <section><h4>Financial/Fundamental View</h4><p>{esc(read['financial'])}</p></section>
                <section><h4>Sector View</h4><p>{esc(read['sector'])}</p></section>
                <section><h4>Desk Risk</h4><p>{esc(read['reason'])} {esc(read['source_note'])}</p></section>
              </div>
              <div class="result-strip">
                <span>Quarter: <b>{esc(row.get('q_period_label'))}</b></span>
                <span>Revenue: <b>INR {fmt_num(row.get('q_revenue'), 0)} cr</b> ({signed_pct(row.get('q_rev_yoy_calc'))} YoY)</span>
                <span>PAT: <b>INR {fmt_num(row.get('q_pat'), 0)} cr</b> ({signed_pct(row.get('q_pat_yoy_calc'))} YoY)</span>
                <span>OPM: <b>{fmt_pct(row.get('q_opm_pct'))}</b></span>
                <span>Debt/equity proxy: <b>{fmt_num(row.get('bs_debt_to_equity_proxy'), 2)}x</b></span>
              </div>
              <details>
                <summary>Source links and local evidence</summary>
                <div class="sources-inline">
                  <p>Local evidence: Agent Adda small/micro-cap screen, EOD price history through {esc(row.get('trade_date'))}, latest result row {esc(row.get('q_period_label'))} from the local financial evidence set.</p>
                  <p>{source_links(symbol)}</p>
                </div>
              </details>
            </article>
            """
        )
    return "\n".join(cards)


def full_appendix(df: pd.DataFrame) -> str:
    rows = []
    for _, row in df.iterrows():
        label, _ = action_label(row)
        rows.append(
            [
                esc(row.get("Symbol")),
                esc(row.get("company")),
                esc(row.get("industry")),
                esc(row.get("buckets")),
                fmt_num(row.get("price"), 2),
                signed_pct(row.get("ret20")),
                signed_pct(row.get("ret60")),
                signed_pct(row.get("ret120")),
                signed_pct(row.get("vs50")),
                signed_pct(row.get("vs200")),
                fmt_num(row.get("rsi_calc"), 1),
                esc(row.get("stg_trading_signal")),
                fmt_num(row.get("stg_technical_score"), 1),
                fmt_num(row.get("stg_enhanced_fund_score"), 1),
                fmt_num(row.get("stg_investment_score"), 1),
                fmt_num(row.get("overall"), 1),
                esc(label),
            ]
        )
    return table(
        rows,
        [
            "Symbol",
            "Company",
            "Sector",
            "Index bucket",
            "Price",
            "1M",
            "3M",
            "6M",
            "vs50D",
            "vs200D",
            "RSI",
            "Signal",
            "Tech",
            "Fund",
            "Invest",
            "Overall",
            "Desk label",
        ],
        "dense appendix-table",
    )


def stats_cards(df: pd.DataFrame, index_rows: list[dict[str, object]]) -> str:
    buy_count = int((df["stg_trading_signal"].astype(str).str.upper() == "BUY").sum())
    selected = df[df["Symbol"].isin(SELECTED_SYMBOLS)]
    avg3m = selected["ret60"].dropna().mean() if not selected.empty else 0
    median_rsi = selected["rsi_calc"].dropna().median() if not selected.empty else 0
    smallcap500 = next((r for r in index_rows if r.get("index") == "NIFTY SMALLCAP 500"), {})
    microcap = next((r for r in index_rows if r.get("index") == "NIFTY MICROCAP 250"), {})
    cards = [
        ("Universe screened", "502", "Smallcap 50/100/250 plus Microcap 250 unique names."),
        ("Stage 2 candidates", str(len(df)), f"{buy_count} BUY flags; the rest remain HOLD/monitor candidates."),
        ("Shortlist avg 3M", signed_pct(avg3m), "Selected company-card group, not a portfolio return."),
        ("Shortlist median RSI", fmt_num(median_rsi, 1), "Momentum is positive; several names are no longer low-risk entries."),
        ("Smallcap 500 today", signed_pct(smallcap500.get("percentChange")), f"Level {fmt_num(smallcap500.get('last'), 2)}."),
        ("Microcap 250 today", signed_pct(microcap.get("percentChange")), f"Level {fmt_num(microcap.get('last'), 2)}."),
    ]
    return "".join(
        f"<div class='stat-card'><span>{esc(title)}</span><b>{esc(value)}</b><p>{esc(note)}</p></div>"
        for title, value, note in cards
    )


def source_trail() -> str:
    items = [
        ("Agent Adda local market database", "EOD stock/index history through data_summary date, stage snapshots, technical scores, and local result evidence."),
        ("NSE allIndices live API", "6 Aug 2026 live index levels and A/D breadth for small-cap and microcap index family."),
        ("NSE constituent files", "Nifty Smallcap 50/100/250 and Nifty Microcap 250 universe definitions downloaded into /tmp/agent_adda_smallcap."),
        ("Intraday alert monitor", "11:19 IST F&O alert cycle: WAIT stance, no fresh executable trade, no forced-trade bias."),
        ("Company and exchange sources", "Company investor pages, NSE/BSE filings, and credible financial media listed inside each company card."),
    ]
    return "\n".join(f"<li><b>{esc(k)}:</b> {esc(v)}</li>" for k, v in items)


def render_report() -> str:
    generated_at = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S IST")
    df = load_screen()
    data_summary = read_data_summary()
    fetched_at, index_rows, index_source = fetch_nse_index_snapshot()
    history = index_history_metrics()
    intraday = parse_intraday()
    industry_counts = Counter(str(x) for x in df["industry"].fillna("Unknown"))
    top_industries = ", ".join(f"{k} ({v})" for k, v in industry_counts.most_common(5))

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(REPORT_TITLE)}</title>
  <style>
    :root {{
      --bg:#0f1318; --panel:#171d24; --panel2:#1f2730; --line:#2f3a45;
      --text:#e9edf2; --muted:#9aa8b6; --green:#2fbf71; --blue:#4da3ff;
      --amber:#f0a202; --red:#ff6b6b; --ink:#0d1117;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font:14px/1.55 Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; }}
    a {{ color:#91c6ff; text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    .masthead {{ padding:34px 24px 28px; border-bottom:1px solid var(--line); background:#111820; }}
    .wrap {{ max-width:1180px; margin:0 auto; }}
    .eyebrow {{ color:var(--amber); text-transform:uppercase; letter-spacing:.08em; font-size:12px; font-weight:700; }}
    h1 {{ margin:8px 0 10px; font-size:34px; line-height:1.1; letter-spacing:0; }}
    h2 {{ margin:34px 0 12px; font-size:22px; letter-spacing:0; }}
    h3 {{ margin:0; font-size:18px; letter-spacing:0; }}
    h3 span {{ display:block; color:var(--muted); font-size:13px; font-weight:500; margin-top:2px; }}
    h4 {{ margin:0 0 6px; font-size:13px; color:#d7e4f0; text-transform:uppercase; letter-spacing:.06em; }}
    p {{ margin:0 0 10px; }}
    .lead {{ max-width:940px; color:#c9d3de; font-size:16px; }}
    .meta {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:18px; }}
    .meta span, .pill {{ display:inline-flex; align-items:center; gap:6px; border:1px solid var(--line); background:#1a222b; color:#d7e4f0; border-radius:999px; padding:5px 9px; font-size:12px; font-weight:700; }}
    .pill.hot {{ background:rgba(47,191,113,.14); border-color:rgba(47,191,113,.5); color:#bff2d2; }}
    .notice-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; margin:18px 0 4px; }}
    .notice {{ border:1px solid var(--line); background:var(--panel); border-radius:8px; padding:14px; }}
    .notice strong {{ color:#fff; }}
    main {{ padding:26px 24px 42px; }}
    .stat-grid {{ display:grid; grid-template-columns:repeat(6,1fr); gap:10px; margin:22px 0; }}
    .stat-card {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; min-height:126px; }}
    .stat-card span {{ color:var(--muted); display:block; font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.05em; }}
    .stat-card b {{ display:block; font-size:24px; margin:6px 0 4px; }}
    .stat-card p {{ color:#aeb9c5; font-size:12px; margin:0; }}
    .section-note {{ color:#c6d0da; max-width:940px; margin-bottom:14px; }}
    .callout {{ border-left:4px solid var(--amber); background:#1a2028; padding:13px 14px; border-radius:6px; margin:12px 0; }}
    .callout.green {{ border-left-color:var(--green); }}
    .callout.red {{ border-left-color:var(--red); }}
    .table-wrap {{ width:100%; overflow-x:auto; border:1px solid var(--line); border-radius:8px; background:var(--panel); }}
    table {{ width:100%; border-collapse:collapse; min-width:840px; }}
    th, td {{ padding:10px 11px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ position:sticky; top:0; background:#202934; color:#dce7f2; font-size:12px; text-transform:uppercase; letter-spacing:.05em; }}
    td {{ color:#d9e1ea; }}
    .dense th, .dense td {{ padding:8px 9px; font-size:12px; }}
    .muted {{ color:var(--muted); }}
    .pos {{ color:#7ee3a1; }} .neg {{ color:#ff8b8b; }} .neutral {{ color:#d8dde3; }}
    .mini-bar {{ position:relative; height:18px; background:#111820; border:1px solid #303a45; border-radius:999px; overflow:hidden; margin-top:5px; min-width:96px; }}
    .mini-bar i {{ display:block; height:100%; background:#728197; opacity:.85; }}
    .mini-bar.green i {{ background:var(--green); }} .mini-bar.blue i {{ background:var(--blue); }} .mini-bar.amber i {{ background:var(--amber); }}
    .mini-bar span {{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center; color:#eef5fb; font-size:11px; font-weight:800; text-shadow:0 1px 2px #000; }}
    .company-grid {{ display:grid; grid-template-columns:1fr; gap:16px; }}
    .company-card {{ border:1px solid var(--line); background:var(--panel); border-radius:8px; padding:16px; }}
    .company-head {{ display:flex; justify-content:space-between; gap:14px; align-items:flex-start; border-bottom:1px solid var(--line); padding-bottom:12px; margin-bottom:12px; }}
    .company-head p {{ color:var(--muted); margin:4px 0 0; }}
    .label-stack {{ text-align:right; min-width:150px; }}
    .score {{ display:block; color:#aeb9c5; margin-top:6px; font-size:12px; }}
    .metric-grid {{ display:grid; grid-template-columns:repeat(6,1fr); gap:8px; margin:10px 0 12px; }}
    .metric-grid div {{ background:var(--panel2); border:1px solid var(--line); border-radius:8px; padding:10px; }}
    .metric-grid b {{ display:block; font-size:18px; }}
    .metric-grid span {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.04em; }}
    .bar-stack {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:12px; }}
    .bar-stack > div > span {{ color:var(--muted); font-size:12px; }}
    .read-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }}
    .read-grid section {{ background:#141a21; border:1px solid var(--line); border-radius:8px; padding:12px; }}
    .read-grid p {{ color:#c7d1dc; margin:0; }}
    .result-strip {{ display:flex; flex-wrap:wrap; gap:8px; margin:12px 0; }}
    .result-strip span {{ border:1px solid var(--line); background:#141a21; border-radius:999px; padding:5px 8px; font-size:12px; color:#cfd8e2; }}
    details {{ margin-top:10px; border-top:1px solid var(--line); padding-top:10px; }}
    summary {{ cursor:pointer; color:#cfe2ff; font-weight:700; }}
    .sources-inline {{ color:#bcc8d4; padding-top:8px; }}
    .two-col {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
    ul.source-list {{ margin:8px 0 0; padding-left:20px; color:#cbd5df; }}
    .footer {{ border-top:1px solid var(--line); margin-top:34px; padding-top:18px; color:#aeb9c5; }}
    @media (max-width: 980px) {{
      h1 {{ font-size:28px; }}
      .notice-grid, .two-col, .read-grid {{ grid-template-columns:1fr; }}
      .stat-grid {{ grid-template-columns:repeat(2,1fr); }}
      .metric-grid {{ grid-template-columns:repeat(2,1fr); }}
      .bar-stack {{ grid-template-columns:1fr; }}
      .company-head {{ flex-direction:column; }}
      .label-stack {{ text-align:left; }}
    }}
  </style>
</head>
<body>
  <header class="masthead">
    <div class="wrap">
      <div class="eyebrow">Agent Adda Market Intelligence</div>
      <h1>{esc(REPORT_TITLE)}</h1>
      <p class="lead">Small-cap indices showed positive but selective participation on 6 Aug 2026. This report converts the intraday index read and the 502-name small/micro-cap constituent screen into a practical watchlist, with technical, financial, fundamental, and sectoral context kept separate.</p>
      <div class="meta">
        <span>Generated: {esc(generated_at)}</span>
        <span>Index snapshot: {esc(fetched_at)}</span>
        <span>EOD data through: {esc(data_summary.get('stock_date_range', 'n/a'))}</span>
        <span>Screen basis: 502 names / {len(df)} Stage 2 candidates</span>
        <span>Mode: Research only, not investment advice</span>
      </div>
      <div class="notice-grid">
        <div class="notice">
          <strong>AI and data-grounding note:</strong>
          AI assistants helped draft and organize this report. Tables, levels, breadth, technical metrics, and result evidence are grounded in Agent Adda local evidence and the source trail below. AI synthesis does not replace independent verification or suitability assessment.
        </div>
        <div class="notice">
          <strong>Disclaimer / SEBI-aligned investor caution:</strong>
          This is for education and general market research only. It is not personalised advice, not a SEBI-registered research report, and not a recommendation or solicitation to buy, sell, hold, trade, or subscribe. Markets carry risk, including capital loss. No assured, fixed, or guaranteed returns are expressed or implied. Verify independently and consult a SEBI-registered investment adviser / qualified professional before acting.
        </div>
      </div>
    </div>
  </header>

  <main>
    <div class="wrap">
      <section>
        <h2>Desk View</h2>
        <div class="callout green">
          <b>Trade stance from intraday monitor: {esc(intraday.get('stance'))}.</b>
          {esc(intraday.get('headline'))} {esc(intraday.get('action'))}
          Monitor timestamp: {esc(intraday.get('time'))}; fresh alerts: {esc(intraday.get('fresh_alerts'))}; total candidates: {esc(intraday.get('total_candidates'))}.
        </div>
        <p class="section-note">The investment/research view is constructive but selective. Smallcap 50 led the family, but broader Smallcap 250/500 and Microcap 250 breadth was closer to mixed. The correct posture is watchlist preparation and retest discipline, not broad chasing.</p>
        <div class="stat-grid">{stats_cards(df, index_rows)}</div>
      </section>

      <section>
        <h2>Small-Cap Index Complex</h2>
        <p class="section-note">Live index/breadth source: {esc(index_source)}. Local technical history is included only where the local index history carries that index. Live-only rows should not be read as audited EOD technical signals.</p>
        {index_snapshot_html(index_rows, history)}
      </section>

      <section>
        <h2>Screen Construction</h2>
        <div class="two-col">
          <div class="callout">
            <b>What passed:</b> {len(df)} names are in Stage 2 from a 502-name unique small/micro-cap universe. Ranking blends performance, trend, local financial evidence, and sector context. Top sector buckets by count: {esc(top_industries)}.
          </div>
          <div class="callout">
            <b>What did not pass:</b> Stage 1/3/4 names, stale or weak financial evidence, negative cash conversion, heavy leverage, and very extended charts are not promoted as executable entries. They may still appear in the appendix only as watchlist context.
          </div>
        </div>
        <h2>Sector Concentration</h2>
        {sector_summary_html(df)}
      </section>

      <section>
        <h2>Ranked Shortlist</h2>
        <p class="section-note">These are research candidates, not direct calls. The desk label tells how to treat each name today: core watch, growth watch, extended watch, verify, or watch only.</p>
        {top_screen_table(df, 30)}
      </section>

      <section>
        <h2>Individual Stock Views</h2>
        <p class="section-note">The cards below combine price action, result quality, balance-sheet/cash-flow checks, and sector lens. Observed data is in the metric strip; the view blocks are interpretation.</p>
        <div class="company-grid">
          {selected_cards(df)}
        </div>
      </section>

      <section>
        <h2>Downgrades And Guardrails</h2>
        <div class="callout red">
          <b>No forced BUY list:</b> intraday alerts were WAIT/no executable trade. Strong daily/weekly charts are not enough for immediate action without entry, stop, volume confirmation, and risk/reward.
        </div>
        <div class="callout">
          <b>Extended charts:</b> SANSERA, SHAILY, ASKAUTOLTD, CUPID, PRICOLLTD, and similar high-RSI names need retest discipline. They may continue to trend, but the entry asymmetry is no longer clean.
        </div>
        <div class="callout">
          <b>Evidence conflicts:</b> MINDACORP has conflicting public headline bases for PAT growth. Treat the stock as watch-and-verify until the exact filing basis is reconciled.
        </div>
      </section>

      <section>
        <h2>Full Stage 2 Appendix</h2>
        <details open>
          <summary>Show all {len(df)} Stage 2 candidates ranked by overall screen score</summary>
          {full_appendix(df)}
        </details>
      </section>

      <section>
        <h2>Source Trail</h2>
        <ul class="source-list">
          {source_trail()}
        </ul>
        <p class="footer">
          Research only, not investment advice. No assured or guaranteed returns. Please consult a SEBI-registered investment adviser / qualified financial professional before acting.
          <br><br><b>Hold. Think. Then act.</b>
        </p>
      </section>
    </div>
  </main>
</body>
</html>
"""
    return html_doc


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_DIR.mkdir(parents=True, exist_ok=True)
    html_doc = render_report()
    dated = OUT_DIR / f"{REPORT_STEM}.html"
    latest = LATEST_DIR / "agent_adda_smallcap_super_performers.html"
    dated.write_text(html_doc, encoding="utf-8")
    shutil.copyfile(dated, latest)
    print(dated)
    print(latest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
