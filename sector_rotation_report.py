#!/usr/bin/env python3
"""Generate an NSE sector rotation report from existing local analysis outputs."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
import hashlib
from pathlib import Path
import html as html_mod
import json
import math
import re
import socket
import struct
import subprocess
import tempfile
import time

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"
INDEX_DATA_CSV = ROOT / "data" / "nse_index_data.csv"
STOCK_CACHE_RDATA = ROOT / "data" / "nse_stock_cache.RData"
AGENT_LOGO_PATH = ROOT / "docs" / "Agent-adda-logo.jpg"
AGENT_BRAND = "Agent Adda - Market Intelligence Agent"
REPORT_DISCLAIMER = (
    "This report is not investment advice. It is a learning journey demonstrating how AI "
    "and rules-based agents can be applied to financial markets. Validate all data, prices, "
    "liquidity, corporate events, and risk independently before making any financial decision."
)
PRINT_FOOTER_DISCLAIMER = (
    "Disclaimer: Not investment advice or a trading recommendation. Educational AI/rules-based market "
    "intelligence only. Use, replication, or trading action is at the user's own risk and legal obligation."
)
FULL_LEGAL_DISCLAIMER = (
    "This report is provided strictly for educational, research, and learning purposes as part of a journey "
    "to understand how AI agents and rules-based agents can be applied to financial-market data. It is not "
    "investment advice, trading advice, portfolio advice, a research recommendation, or a solicitation to buy, "
    "sell, hold, short, or otherwise transact in any security, derivative, index, fund, or financial instrument. "
    "The information, scores, signals, narratives, charts, model outputs, and examples in this report must not "
    "be replicated, redistributed, automated, or used with any intent of trading, recommending trades, advising "
    "others, managing money, or making financial decisions. Anyone choosing to use, interpret, adapt, copy, "
    "replicate, distribute, or act on this information does so entirely at their own risk, responsibility, and "
    "legal and regulatory obligation. Agent Adda is not a SEBI-registered investment adviser, research analyst, "
    "portfolio manager, broker, or any other SEBI-registered market intermediary. Agent Adda, its creators, "
    "contributors, systems, agents, and associated persons accept no responsibility or liability for losses, "
    "damages, legal consequences, regulatory consequences, tax consequences, opportunity costs, or any other "
    "implications arising directly or indirectly from the use of this information by any person or organization. "
    "All market data can be delayed, incomplete, inaccurate, stale, or affected by corporate actions, liquidity, "
    "data-provider issues, model limitations, prompt limitations, or rule-design limitations. Users must consult "
    "qualified SEBI-registered professionals and independently verify all facts before making any financial or "
    "legal decision."
)
FUNDAMENTAL_FALLBACK_CSVS = [
    ROOT / "data" / "fundamental_scores_database.csv",
    ROOT / "organized" / "data" / "fundamental_scores_database.csv",
]

ROTATING_INDEXES = {
    "Nifty Ind Defence": "Defence & Aerospace",
    "Nifty Realty": "Realty",
    "Nifty Metal": "Metals & Mining",
    "Nifty Energy": "Energy - Power",
    "NIFTY OIL AND GAS": "Energy - Oil & Gas",
    "Nifty EV": "EV & Auto Ancillaries",
    "Nifty Auto": "EV & Auto Ancillaries",
    "Nifty FMCG": "FMCG & Consumer Goods",
    "NIFTY HEALTHCARE": "Pharma & Healthcare",
    "Nifty Pharma": "Pharma & Healthcare",
}

INDEX_CATEGORIES: dict[str, str] = {
    # Broad Market
    "Nifty 50": "Broad Market", "Nifty 100": "Broad Market",
    "Nifty 200": "Broad Market", "Nifty 500": "Broad Market",
    "Nifty Next 50": "Broad Market", "NIFTY TOTAL MKT": "Broad Market",
    "NIFTY LARGEMID250": "Broad Market", "NIFTY MIDSML 400": "Broad Market",
    "NIFTY500 MULTICAP": "Broad Market", "NIFTY500 Flexicap": "Broad Market",
    "Nifty 500 EW": "Broad Market", "NIFTY500 EW": "Broad Market",
    "NIFTY500 LMS Eql": "Broad Market",
    # Sector
    "Nifty Auto": "Sector", "Nifty Bank": "Sector", "Nifty FMCG": "Sector",
    "Nifty IT": "Sector", "Nifty Metal": "Sector", "Nifty Pharma": "Sector",
    "Nifty Realty": "Sector", "NIFTY HEALTHCARE": "Sector",
    "NIFTY OIL AND GAS": "Sector", "Nifty Energy": "Sector",
    "Nifty Infra": "Sector", "Nifty Media": "Sector",
    "Nifty Serv Sector": "Sector", "Nifty PSU Bank": "Sector",
    "Nifty Pvt Bank": "Sector", "Nifty Capital Mkt": "Sector",
    "Nifty Commodities": "Sector", "Nifty Fin Service": "Sector",
    "Nifty FinSerExBnk": "Sector", "Nifty Chemicals": "Sector",
    "NIFTY CONSR DURBL": "Sector", "NIFTY IND DIGITAL": "Sector",
    "NIFTY INDIA MFG": "Sector", "Nifty MS IT Telcm": "Sector",
    "Nifty MS Fin Serv": "Sector", "Nifty MS Ind Cons": "Sector",
    "India VIX": "Sector",
    # Thematic
    "Nifty EV": "Thematic", "Nifty Ind Defence": "Thematic",
    "Nifty Housing": "Thematic", "Nifty IPO": "Thematic",
    "Nifty Internet": "Thematic", "Nifty Rural": "Thematic",
    "Nifty CoreHousing": "Thematic", "Nifty Trans Logis": "Thematic",
    "Nifty RailwaysPSU": "Thematic", "Nifty MNC": "Thematic",
    "Nifty CPSE": "Thematic", "Nifty PSE": "Thematic",
    "Nifty InfraLog": "Thematic", "Nifty Multi Infra": "Thematic",
    "Nifty Multi Mfg": "Thematic", "Nifty Mobility": "Thematic",
    "Nifty Ind Tourism": "Thematic", "Nifty Consumption": "Thematic",
    "Nifty New Consump": "Thematic", "Nifty NonCyc Cons": "Thematic",
    "NiftyConglomerate": "Thematic", "Nifty FPI 150": "Thematic",
    "Nifty GrowSect 15": "Thematic", "Nifty Corp MAATR": "Thematic",
    "Nifty Waves": "Thematic", "Nifty Tata 25 Cap": "Thematic",
    "Nifty SME Emerge": "Thematic", "Nifty CONSR DURBL": "Thematic",
    # Strategy / Factor
    "NIFTY Alpha 50": "Strategy / Factor", "NIFTY AlphaLowVol": "Strategy / Factor",
    "NIFTY100 EQL Wgt": "Strategy / Factor", "NIFTY100 LowVol30": "Strategy / Factor",
    "NIFTY100 Qualty30": "Strategy / Factor", "NIFTY200 QUALTY30": "Strategy / Factor",
    "Nifty HighBeta 50": "Strategy / Factor", "Nifty Low Vol 50": "Strategy / Factor",
    "Nifty100 Alpha 30": "Strategy / Factor", "Nifty200 Alpha 30": "Strategy / Factor",
    "Nifty200 Value 30": "Strategy / Factor", "Nifty200Momentm30": "Strategy / Factor",
    "Nifty500 Qlty50": "Strategy / Factor", "Nifty500 Value 50": "Strategy / Factor",
    "Nifty500Momentm50": "Strategy / Factor", "Nifty500 LowVol50": "Strategy / Factor",
    "Nifty50 Value 20": "Strategy / Factor", "Nifty AQL 30": "Strategy / Factor",
    "Nifty AQLV 30": "Strategy / Factor", "Nifty Qlty LV 30": "Strategy / Factor",
    "Nifty Multi MQ 50": "Strategy / Factor", "Nifty TMMQ 50": "Strategy / Factor",
    "Nifty Div Opps 50": "Strategy / Factor", "Nifty Shariah 25": "Strategy / Factor",
    "NIFTY100 ESG": "Strategy / Factor", "NIFTY100 Enh ESG": "Strategy / Factor",
    "NIFTY100ESGSecLdr": "Strategy / Factor", "NIFTY100 Liq 15": "Strategy / Factor",
    "NIFTY50 EQL Wgt": "Strategy / Factor", "Nifty50 Div Point": "Strategy / Factor",
    "Nifty50 Shariah": "Strategy / Factor", "Nifty50 USD": "Strategy / Factor",
    "Nifty50 PR 1x Inv": "Strategy / Factor", "Nifty50 TR 1x Inv": "Strategy / Factor",
    "Nifty50 PR 2x Lev": "Strategy / Factor", "Nifty50 TR 2x Lev": "Strategy / Factor",
    "Nifty Top 10 EW": "Strategy / Factor", "Nifty Top 15 EW": "Strategy / Factor",
    "Nifty Top 20 EW": "Strategy / Factor", "Nifty500 Shariah": "Strategy / Factor",
    "Nifty500 MQVLv50": "Strategy / Factor", "Nifty500 Health": "Strategy / Factor",
    "NIFTY500 Qlty50": "Strategy / Factor",
    # Size
    "NIFTY MIDCAP 100": "Size", "NIFTY MIDCAP 150": "Size",
    "NIFTY SMLCAP 100": "Size", "NIFTY SMLCAP 250": "Size",
    "NIFTY SMLCAP 50": "Size", "NIFTY MID SELECT": "Size",
    "NIFTY MICROCAP250": "Size", "Nifty Midcap 50": "Size",
    "Nifty Mid Liq 15": "Size", "NiftyM150Momntm50": "Size",
    "NIFTY M150 QLTY50": "Size", "Nifty MidSml Hlth": "Size",
    "Nifty Sml250 Q50": "Size", "NiftySml250MQ 100": "Size",
    "NiftyMS400 MQ 100": "Size", "Nifty FinSrv25 50": "Size",
    "NIFTY Alpha 50": "Size",
    # Fixed Income
    "BHARATBOND-APR25": "Fixed Income", "BHARATBOND-APR30": "Fixed Income",
    "BHARATBOND-APR31": "Fixed Income", "BHARATBOND-APR32": "Fixed Income",
    "BHARATBOND-APR33": "Fixed Income",
    "Nifty GS 10Yr": "Fixed Income", "Nifty GS 10Yr Cln": "Fixed Income",
    "Nifty GS 11 15Yr": "Fixed Income", "Nifty GS 15YrPlus": "Fixed Income",
    "Nifty GS 4 8Yr": "Fixed Income", "Nifty GS 8 13Yr": "Fixed Income",
    "Nifty GS Compsite": "Fixed Income",
}

SECTOR_KEYWORDS = {
    "Defence & Aerospace": [
        "HAL", "BEL", "BEML", "MIDHANI", "MAZDOCK", "COCHINSHIP", "GRSE",
        "DATAPATTNS", "DCXINDIA", "ASTRAMICRO", "MTARTECH", "AZAD", "BELRISE",
        "AEROFLEX", "PARAS", "RRKABEL", "WEBELSOLAR",
    ],
    "Realty": [
        "DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE", "BRIGADE", "SOBHA",
        "SUNTECK", "LODHA", "MACROTECH", "PURVA", "KOLTEPATIL", "ANANTRAJ",
    ],
    "Metals & Mining": [
        "TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "COALINDIA", "HINDCOPPER",
        "NATIONALUM", "SAIL", "WELCORP", "JINDALSTEL", "JSL", "NALCO", "MOIL",
        "RATNAMANI", "SUNFLAG", "IMFA",
    ],
    "Energy - Power": [
        "NTPC", "POWERGRID", "ADANIPOWER", "TORNTPOWER", "TATAPOWER", "NHPC",
        "SJVN", "ADANIGREEN", "JSWENERGY", "NLCINDIA", "NTPCGREEN", "CESC",
    ],
    "Energy - Oil & Gas": [
        "RELIANCE", "ONGC", "IOC", "BPCL", "HPCL", "GAIL", "OIL", "PETRONET",
        "MRPL", "ATGL", "IGL", "MGL", "CHENNPETRO", "CASTROLIND", "KIRLOSENG",
    ],
    "EV & Auto Ancillaries": [
        "BHARATFORG", "MOTHERSON", "BOSCHLTD", "UNOMINDA", "SONACOMS", "TIINDIA",
        "EXIDEIND", "AMARAJABAT", "APOLLOTYRE", "MRF", "SANSERA", "AUTOAXLES",
        "LUMAX", "PRICOLLTD", "GNA", "CRAFTSMAN", "ENDURANCE", "FIEMIND",
    ],
    "FMCG & Consumer Goods": [
        "HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "DABUR", "MARICO",
        "COLPAL", "GODREJCP", "UBL", "VBL", "TATACONSUM", "EMAMILTD",
        "RADICO", "BALRAMCHIN", "DALMIASUG",
    ],
    "Pharma & Healthcare": [
        "SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "APOLLOHOSP", "BIOCON",
        "TORNTPHARM", "ALKEM", "LUPIN", "AUROPHARMA", "GLENMARK", "ZYDUSLIFE",
        "ASTERDM", "BLISSGVS",
    ],
}


@dataclass(frozen=True)
class ReportPaths:
    markdown: Path
    html: Path
    pdf: Path
    latest_markdown: Path
    latest_html: Path
    latest_pdf: Path


def _latest_file(pattern: str, directory: Path = REPORTS_DIR) -> Path:
    files = sorted(directory.rglob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No files matched {directory / pattern}")
    return files[0]


def report_output_paths(generated_at: datetime | pd.Timestamp) -> ReportPaths:
    ts = pd.Timestamp(generated_at).to_pydatetime()
    suffix = ts.strftime("%Y%m%d")
    year = ts.strftime("%Y")
    output_dir = REPORTS_DIR / "sector_rotation" / year
    return ReportPaths(
        markdown=output_dir / f"Sector_Rotation_Report_{suffix}.md",
        html=output_dir / f"Sector_Rotation_Report_{suffix}.html",
        pdf=output_dir / f"Sector_Rotation_Report_{suffix}.pdf",
        latest_markdown=REPORTS_DIR / "latest" / "sector_rotation.md",
        latest_html=REPORTS_DIR / "latest" / "sector_rotation.html",
        latest_pdf=REPORTS_DIR / "latest" / "sector_rotation.pdf",
    )


def _pct_return(series: pd.Series, days: int, dates: pd.Series) -> float:
    if series.empty:
        return math.nan
    last_close = float(series.iloc[-1])
    last_date = pd.to_datetime(dates.iloc[-1])
    prior = series[pd.to_datetime(dates) <= last_date - pd.Timedelta(days=days)]
    if prior.empty or float(prior.iloc[-1]) == 0:
        return math.nan
    return (last_close / float(prior.iloc[-1]) - 1.0) * 100.0


def build_index_metrics(index_data: pd.DataFrame, symbols: list[str]) -> pd.DataFrame:
    df = index_data.copy()
    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"])
    rows = []
    for symbol in symbols:
        hist = df[df["SYMBOL"] == symbol].sort_values("TIMESTAMP")
        if hist.empty:
            continue
        rows.append(
            {
                "SYMBOL": symbol,
                "DATE": hist["TIMESTAMP"].iloc[-1].date().isoformat(),
                "CLOSE": float(hist["CLOSE"].iloc[-1]),
                "RET_5D": _pct_return(hist["CLOSE"], 7, hist["TIMESTAMP"]),
                "RET_1M": _pct_return(hist["CLOSE"], 30, hist["TIMESTAMP"]),
                "RET_3M": _pct_return(hist["CLOSE"], 91, hist["TIMESTAMP"]),
                "RET_6M": _pct_return(hist["CLOSE"], 182, hist["TIMESTAMP"]),
            }
        )
    return pd.DataFrame(rows)


def rank_rotating_sectors(index_metrics: pd.DataFrame, benchmark_symbol: str = "Nifty 500") -> pd.DataFrame:
    df = index_metrics.copy()
    benchmark = df[df["SYMBOL"] == benchmark_symbol]
    if benchmark.empty:
        raise ValueError(f"Benchmark symbol not found: {benchmark_symbol}")

    bench = benchmark.iloc[0]
    for col in ["RET_5D", "RET_1M", "RET_3M", "RET_6M"]:
        rs_col = "RS_" + col.removeprefix("RET_")
        df[rs_col] = df[col] - bench[col]

    df["ROTATION_SCORE"] = (
        0.35 * df["RS_1M"].fillna(0)
        + 0.25 * df["RET_1M"].fillna(0)
        + 0.20 * df["RS_5D"].fillna(0)
        + 0.10 * df["RS_3M"].fillna(0)
        + 0.10 * df["RS_6M"].fillna(0)
    )
    df = df[df["SYMBOL"] != benchmark_symbol].sort_values("ROTATION_SCORE", ascending=False)
    return df.reset_index(drop=True)


def compute_supertrend(price_data: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    df = price_data.copy().reset_index(drop=True)
    high = df["HIGH"].astype(float)
    low = df["LOW"].astype(float)
    close = df["CLOSE"].astype(float)

    prev_close = close.shift(1)
    true_range = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(period, min_periods=1).mean()

    hl2 = (high + low) / 2.0
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr
    final_upper = basic_upper.copy()
    final_lower = basic_lower.copy()
    direction = pd.Series(1, index=df.index, dtype="int64")

    for i in range(1, len(df)):
        if basic_upper.iloc[i] < final_upper.iloc[i - 1] or close.iloc[i - 1] > final_upper.iloc[i - 1]:
            final_upper.iloc[i] = basic_upper.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i - 1]

        if basic_lower.iloc[i] > final_lower.iloc[i - 1] or close.iloc[i - 1] < final_lower.iloc[i - 1]:
            final_lower.iloc[i] = basic_lower.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i - 1]

        if close.iloc[i] > final_upper.iloc[i - 1]:
            direction.iloc[i] = 1
        elif close.iloc[i] < final_lower.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]

    df["SUPERTREND"] = np.where(direction.eq(1), final_lower, final_upper)
    df["SUPERTREND_DIRECTION"] = direction
    df["SUPERTREND_STATE"] = np.where(direction.eq(1), "BULLISH", "BEARISH")
    return df


def classify_consolidation_breakout(
    history: pd.DataFrame,
    lookback: int = 20,
    width_threshold: float = 0.12,
    volume_multiplier: float = 1.4,
) -> dict[str, object]:
    if len(history) < max(lookback + 1, 5):
        return {
            "PATTERN": "INSUFFICIENT_HISTORY",
            "IS_CONSOLIDATION_BREAKOUT": False,
            "CONSOLIDATION_WIDTH": math.nan,
            "VOLUME_RATIO": math.nan,
            "RESISTANCE": math.nan,
            "SUPPORT": math.nan,
        }

    hist = history.copy().sort_values("TIMESTAMP") if "TIMESTAMP" in history.columns else history.copy()
    base = hist.iloc[-lookback - 1 : -1]
    latest = hist.iloc[-1]
    resistance = float(base["HIGH"].max())
    support = float(base["LOW"].min())
    midpoint = (resistance + support) / 2.0 if resistance and support else math.nan
    width = (resistance - support) / midpoint if midpoint else math.nan
    avg_volume = float(base["TOTTRDQTY"].replace(0, np.nan).mean()) if "TOTTRDQTY" in base else math.nan
    latest_volume = float(latest.get("TOTTRDQTY", math.nan))
    volume_ratio = latest_volume / avg_volume if avg_volume and not math.isnan(avg_volume) else math.nan
    breakout = (
        bool(width <= width_threshold)
        and float(latest["CLOSE"]) > resistance
        and (math.isnan(volume_ratio) or volume_ratio >= volume_multiplier)
    )

    if breakout:
        pattern = "CONSOLIDATION_BREAKOUT"
    elif bool(width <= width_threshold):
        pattern = "BASE_BUILDING"
    elif float(latest["CLOSE"]) >= resistance * 0.98:
        pattern = "NEAR_RESISTANCE"
    else:
        pattern = "TRENDING_OR_CHOPPY"

    return {
        "PATTERN": pattern,
        "IS_CONSOLIDATION_BREAKOUT": breakout,
        "CONSOLIDATION_WIDTH": width,
        "VOLUME_RATIO": volume_ratio,
        "RESISTANCE": resistance,
        "SUPPORT": support,
    }


def calculate_peak_resilience(history: pd.DataFrame, lookback: int = 252, near_high_threshold: float = 5.0) -> dict[str, object]:
    """Measure drawdown from 52-week high and recovery from 52-week low."""
    if history.empty:
        return {
            "FIFTY_TWO_WEEK_HIGH": math.nan,
            "FIFTY_TWO_WEEK_LOW": math.nan,
            "DRAWDOWN_FROM_52W_HIGH_PCT": math.nan,
            "RECOVERY_FROM_52W_LOW_PCT": math.nan,
            "DAYS_SINCE_52W_LOW": math.nan,
            "RECOVERY_SPEED_SCORE": math.nan,
            "WITHIN_20PCT_OF_HIGH": False,
            "NEAR_OR_ABOVE_52W_HIGH": False,
        }

    hist = history.copy()
    if "TIMESTAMP" in hist.columns:
        hist["TIMESTAMP"] = pd.to_datetime(hist["TIMESTAMP"])
        hist = hist.sort_values("TIMESTAMP")
    hist = hist.tail(lookback)
    latest = hist.iloc[-1]
    close = float(latest["CLOSE"])
    high_52w = float(hist["HIGH"].max())
    low_52w = float(hist["LOW"].min())
    low_idx = hist["LOW"].astype(float).idxmin()
    low_date = pd.to_datetime(hist.loc[low_idx, "TIMESTAMP"]) if "TIMESTAMP" in hist.columns else None
    latest_date = pd.to_datetime(latest["TIMESTAMP"]) if "TIMESTAMP" in hist.columns else None
    days_since_low = max((latest_date - low_date).days, 1) if low_date is not None and latest_date is not None else max(len(hist) - 1, 1)
    drawdown = (close / high_52w - 1.0) * 100.0 if high_52w else math.nan
    recovery_from_low = (close / low_52w - 1.0) * 100.0 if low_52w else math.nan
    recovery_speed = recovery_from_low / days_since_low if days_since_low else math.nan

    return {
        "FIFTY_TWO_WEEK_HIGH": high_52w,
        "FIFTY_TWO_WEEK_LOW": low_52w,
        "DRAWDOWN_FROM_52W_HIGH_PCT": drawdown,
        "RECOVERY_FROM_52W_LOW_PCT": recovery_from_low,
        "DAYS_SINCE_52W_LOW": days_since_low,
        "RECOVERY_SPEED_SCORE": recovery_speed,
        "WITHIN_20PCT_OF_HIGH": bool(drawdown >= -20.0),
        "NEAR_OR_ABOVE_52W_HIGH": bool(drawdown >= -near_high_threshold),
    }


def _series_0_100(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if values.dropna().empty:
        return pd.Series(50.0, index=series.index)
    low = values.quantile(0.05)
    high = values.quantile(0.95)
    if high == low:
        return pd.Series(50.0, index=series.index)
    return ((values.clip(low, high) - low) / (high - low) * 100.0).fillna(50)


def _column_or_default(df: pd.DataFrame, column: str, default: object) -> pd.Series:
    if column in df.columns:
        return df[column]
    return pd.Series(default, index=df.index)


def _classify_setup(df: pd.DataFrame) -> pd.Series:
    """Classify each candidate into an A+ setup class based on technical conditions."""
    pat = _column_or_default(df, "PATTERN", "").astype(str)
    vol = pd.to_numeric(_column_or_default(df, "VOLUME_RATIO", math.nan), errors="coerce").fillna(1.0)
    rsi = pd.to_numeric(_column_or_default(df, "RSI", 50), errors="coerce").fillna(50)
    st = _column_or_default(df, "SUPERTREND_STATE", "").astype(str)
    ret5d = pd.to_numeric(_column_or_default(df, "RET_5D", 0), errors="coerce").fillna(0)
    ret1m = pd.to_numeric(_column_or_default(df, "RET_1M", 0), errors="coerce").fillna(0)
    dd = pd.to_numeric(_column_or_default(df, "DRAWDOWN_FROM_52W_HIGH_PCT", -100), errors="coerce").fillna(-100)
    sig = _column_or_default(df, "TRADING_SIGNAL", "").astype(str)

    leader_breakout = (
        pat.eq("CONSOLIDATION_BREAKOUT") & vol.gt(1.5) & rsi.between(55, 72) & st.eq("BULLISH")
    )
    fast_recovery = (
        ret5d.gt(3) & ret1m.gt(8) & dd.lt(-5) & st.eq("BULLISH")
    )
    base_near_high = (
        dd.between(-5, 0) & rsi.between(50, 65) & vol.lt(1.2) & st.eq("BULLISH")
    )
    pullback_in_uptrend = (
        st.eq("BULLISH") & rsi.between(38, 52) & ret5d.lt(-2)
    )
    momentum_extended = rsi.gt(72) & ret1m.gt(15)
    weak_trend = st.eq("BEARISH") | sig.isin(["SELL", "WEAK_SELL"]) | ret1m.lt(-5)

    conditions = [
        leader_breakout,
        fast_recovery,
        base_near_high,
        pullback_in_uptrend,
        momentum_extended,
        weak_trend,
    ]
    labels = [
        "LEADER_BREAKOUT",
        "FAST_RECOVERY",
        "BASE_NEAR_HIGH",
        "PULLBACK_IN_UPTREND",
        "MOMENTUM_EXTENDED",
        "WEAK_TREND",
    ]
    result = pd.Series("NEUTRAL", index=df.index)
    for cond, label in zip(reversed(conditions), reversed(labels)):
        result = result.where(~cond, label)
    return result


def _compute_entry_levels(df: pd.DataFrame) -> pd.DataFrame:
    """Add ENTRY_LOW, ENTRY_HIGH, STOP_LOSS, TARGET_1, TARGET_2 columns."""
    price = pd.to_numeric(_column_or_default(df, "CURRENT_PRICE", math.nan), errors="coerce")
    res = pd.to_numeric(_column_or_default(df, "RESISTANCE", math.nan), errors="coerce")
    sup = pd.to_numeric(_column_or_default(df, "SUPPORT", math.nan), errors="coerce")
    st_val = pd.to_numeric(_column_or_default(df, "SUPERTREND_VALUE", math.nan), errors="coerce")

    entry_low = (price * 0.99).round(2)
    entry_high = pd.concat([res * 0.995, price * 1.02], axis=1).min(axis=1).round(2)
    risk = entry_low - pd.concat([st_val, sup * 0.98, entry_low * 0.94], axis=1).max(axis=1)
    stop_loss = (entry_low - risk).round(2)
    target_1 = res.round(2)
    target_2 = (entry_low + risk * 2.5).round(2)

    df = df.copy()
    df["ENTRY_LOW"] = entry_low
    df["ENTRY_HIGH"] = entry_high
    df["STOP_LOSS"] = stop_loss
    df["TARGET_1"] = target_1
    df["TARGET_2"] = target_2
    return df


def assign_action_buckets(df: pd.DataFrame) -> pd.DataFrame:
    """Add ACTION_BUCKET and ACTION_REASON using setup quality and risk state."""
    out = df.copy()
    setup = _column_or_default(out, "SETUP_CLASS", "NEUTRAL").astype(str)
    signal = _column_or_default(out, "TRADING_SIGNAL", "").astype(str)
    st = _column_or_default(out, "SUPERTREND_STATE", "").astype(str)
    pattern = _column_or_default(out, "PATTERN", "").astype(str)
    rsi = pd.to_numeric(_column_or_default(out, "RSI", 50), errors="coerce").fillna(50)
    tech = pd.to_numeric(_column_or_default(out, "TECHNICAL_SCORE", 50), errors="coerce").fillna(50)
    dd = pd.to_numeric(_column_or_default(out, "DRAWDOWN_FROM_52W_HIGH_PCT", -100), errors="coerce").fillna(-100)

    bucket = pd.Series("WATCHLIST", index=out.index)
    reason = pd.Series("Mixed setup; wait for cleaner confirmation.", index=out.index)

    avoid = setup.eq("WEAK_TREND") | st.eq("BEARISH") | signal.isin(["SELL", "WEAK_SELL"])
    extended = setup.eq("MOMENTUM_EXTENDED") | (rsi.gt(72) & dd.ge(-8))
    buy_watch = (
        setup.eq("LEADER_BREAKOUT")
        & st.eq("BULLISH")
        & signal.isin(["STRONG_BUY", "BUY", "HOLD"])
        & tech.ge(65)
    )
    breakout_watch = setup.eq("BASE_NEAR_HIGH") | pattern.eq("NEAR_RESISTANCE")
    hold_trail = setup.isin(["FAST_RECOVERY", "PULLBACK_IN_UPTREND"]) & st.eq("BULLISH")

    bucket = bucket.where(~breakout_watch, "BREAKOUT_WATCH")
    reason = reason.where(~breakout_watch, "Near high/base setup; wait for price and volume breakout confirmation.")
    bucket = bucket.where(~hold_trail, "HOLD_TRAIL")
    reason = reason.where(~hold_trail, "Constructive trend; use defined stop and trail winners.")
    bucket = bucket.where(~buy_watch, "BUY_WATCH")
    reason = reason.where(~buy_watch, "High-quality breakout with bullish trend and acceptable momentum.")
    bucket = bucket.where(~extended, "WAIT_FOR_PULLBACK")
    reason = reason.where(~extended, "Momentum is extended; prefer a pullback or fresh base before entry.")
    bucket = bucket.where(~avoid, "AVOID")
    reason = reason.where(~avoid, "Weak trend or sell signal; avoid fresh exposure until repaired.")

    out["ACTION_BUCKET"] = bucket
    out["ACTION_REASON"] = reason
    return out


def rank_stock_candidates(stocks: pd.DataFrame) -> pd.DataFrame:
    df = stocks.copy()
    tech = pd.to_numeric(df["TECHNICAL_SCORE"], errors="coerce").clip(0, 100).fillna(50)
    rs = _series_0_100(df["RELATIVE_STRENGTH"])
    fund = pd.to_numeric(_column_or_default(df, "ENHANCED_FUND_SCORE", 50), errors="coerce").clip(0, 100).fillna(50)
    pattern_bonus = _column_or_default(df, "PATTERN", "").map(
        {
            "CONSOLIDATION_BREAKOUT": 12,
            "BASE_BUILDING": 5,
            "NEAR_RESISTANCE": 3,
            "TRENDING_OR_CHOPPY": 0,
            "INSUFFICIENT_HISTORY": -3,
        }
    ).fillna(0)
    supertrend_bonus = _column_or_default(df, "SUPERTREND_STATE", "").map({"BULLISH": 6, "BEARISH": -4}).fillna(0)
    signal_bonus = _column_or_default(df, "TRADING_SIGNAL", "").map({"STRONG_BUY": 8, "BUY": 5, "HOLD": 1, "WEAK_HOLD": -2, "SELL": -8}).fillna(0)
    stage_bonus = _column_or_default(df, "STAGE", "UNKNOWN").map({"STAGE_2": 4, "STAGE_1": 0, "STAGE_3": -5, "STAGE_4": -8, "UNKNOWN": 0}).fillna(0)

    df["RS_RANK_SCORE"] = rs.round(2)
    df["INVESTMENT_SCORE"] = (0.38 * tech + 0.27 * rs + 0.25 * fund + pattern_bonus + supertrend_bonus + signal_bonus + stage_bonus).round(2)
    df["SETUP_CLASS"] = _classify_setup(df)
    df = _compute_entry_levels(df)
    df = assign_action_buckets(df)
    return df.sort_values(["INVESTMENT_SCORE", "TECHNICAL_SCORE", "RELATIVE_STRENGTH"], ascending=False).reset_index(drop=True)


def rank_peak_resilience_stocks(stocks: pd.DataFrame, max_drawdown_pct: float = 20.0) -> pd.DataFrame:
    df = stocks.copy()
    drawdown = pd.to_numeric(df["DRAWDOWN_FROM_52W_HIGH_PCT"], errors="coerce")
    eligible = df[
        drawdown.ge(-max_drawdown_pct)
        & _column_or_default(df, "WITHIN_20PCT_OF_HIGH", False).astype(bool)
        & _column_or_default(df, "NEAR_OR_ABOVE_52W_HIGH", False).astype(bool)
    ].copy()
    if eligible.empty:
        return eligible

    tech = pd.to_numeric(eligible["TECHNICAL_SCORE"], errors="coerce").clip(0, 100).fillna(50)
    rs = _series_0_100(eligible["RELATIVE_STRENGTH"])
    fund = pd.to_numeric(_column_or_default(eligible, "ENHANCED_FUND_SCORE", 50), errors="coerce").clip(0, 100).fillna(50)
    recovery_speed = _series_0_100(eligible["RECOVERY_SPEED_SCORE"])
    high_proximity = (100.0 + pd.to_numeric(eligible["DRAWDOWN_FROM_52W_HIGH_PCT"], errors="coerce")).clip(0, 100).fillna(0)

    eligible["PEAK_RESILIENCE_SCORE"] = (
        0.25 * tech
        + 0.20 * rs
        + 0.20 * recovery_speed
        + 0.20 * high_proximity
        + 0.15 * fund
    ).round(2)
    return eligible.sort_values(
        ["PEAK_RESILIENCE_SCORE", "DRAWDOWN_FROM_52W_HIGH_PCT", "RECOVERY_SPEED_SCORE"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def assign_sector(symbol: str, company_name: str = "") -> str | None:
    symbol_u = str(symbol).upper()
    company_u = str(company_name).upper()
    for sector, keywords in SECTOR_KEYWORDS.items():
        for keyword in keywords:
            kw = keyword.upper()
            if kw in symbol_u or kw in company_u:
                return sector
    return None


def load_comprehensive_analysis() -> tuple[pd.DataFrame, Path]:
    path = _latest_file("comprehensive_nse_enhanced_*.csv")
    df = pd.read_csv(path)
    fallback = load_fundamental_fallback()
    if fallback is not None:
        df = merge_fundamental_scores(df, fallback)
    return df, path


def load_fundamental_fallback() -> pd.DataFrame | None:
    for path in FUNDAMENTAL_FALLBACK_CSVS:
        if path.exists():
            return pd.read_csv(path)
    return None


def merge_fundamental_scores(analysis: pd.DataFrame, fallback: pd.DataFrame) -> pd.DataFrame:
    """Fill missing fundamental score columns from an external symbol-keyed database."""
    if fallback.empty:
        return analysis.copy()

    symbol_col = "symbol" if "symbol" in fallback.columns else "SYMBOL" if "SYMBOL" in fallback.columns else None
    if symbol_col is None:
        return analysis.copy()

    score_cols = [
        "ENHANCED_FUND_SCORE",
        "EARNINGS_QUALITY",
        "SALES_GROWTH",
        "FINANCIAL_STRENGTH",
        "INSTITUTIONAL_BACKING",
    ]
    available_cols = [col for col in score_cols if col in fallback.columns]
    if not available_cols:
        return analysis.copy()

    df = analysis.copy()
    fund = fallback[[symbol_col, *available_cols]].copy()
    fund["_SYMBOL_KEY"] = fund[symbol_col].astype(str).str.strip().str.upper()
    fund = fund.drop_duplicates("_SYMBOL_KEY", keep="last").set_index("_SYMBOL_KEY")
    keys = df["SYMBOL"].astype(str).str.strip().str.upper()

    for col in available_cols:
        if col not in df.columns:
            df[col] = np.nan
        existing = pd.to_numeric(df[col], errors="coerce")
        fallback_values = keys.map(pd.to_numeric(fund[col], errors="coerce"))
        df[col] = existing.where(existing.notna(), fallback_values)

    if "FUNDAMENTAL_SCORE" in df.columns:
        enhanced = pd.to_numeric(df["ENHANCED_FUND_SCORE"], errors="coerce")
        current = pd.to_numeric(df["FUNDAMENTAL_SCORE"], errors="coerce").fillna(0)
        derived = pd.cut(
            enhanced,
            bins=[-np.inf, 30, 40, 50, 60, 70, np.inf],
            labels=[0, 5, 10, 15, 20, 25],
        )
        derived = pd.to_numeric(derived, errors="coerce")
        df["FUNDAMENTAL_SCORE"] = current.where(current.gt(0), derived).fillna(current)
    return df


def load_index_rotation() -> pd.DataFrame:
    index_data = pd.read_csv(INDEX_DATA_CSV, usecols=["SYMBOL", "CLOSE", "TIMESTAMP"])
    symbols = ["Nifty 500", *ROTATING_INDEXES.keys()]
    metrics = build_index_metrics(index_data, symbols)
    ranked = rank_rotating_sectors(metrics, benchmark_symbol="Nifty 500")
    ranked["SECTOR_NAME"] = ranked["SYMBOL"].map(ROTATING_INDEXES)
    return ranked.dropna(subset=["SECTOR_NAME"])


def load_all_index_metrics() -> pd.DataFrame:
    """Load performance metrics + 52W range for all available NSE indices."""
    index_data = pd.read_csv(
        INDEX_DATA_CSV,
        usecols=["SYMBOL", "CLOSE", "TIMESTAMP", "HI_52_WK", "LO_52_WK"],
    )
    all_syms = index_data["SYMBOL"].unique().tolist()
    metrics = build_index_metrics(index_data, ["Nifty 500", *all_syms])

    bench = metrics[metrics["SYMBOL"] == "Nifty 500"]
    if not bench.empty:
        b = bench.iloc[0]
        for col in ["RET_5D", "RET_1M", "RET_3M", "RET_6M"]:
            metrics[f"RS_{col[4:]}"] = metrics[col] - b[col]
        metrics["ROTATION_SCORE"] = (
            0.35 * metrics["RS_1M"].fillna(0)
            + 0.25 * metrics["RET_1M"].fillna(0)
            + 0.20 * metrics["RS_5D"].fillna(0)
            + 0.10 * metrics["RS_3M"].fillna(0)
            + 0.10 * metrics["RS_6M"].fillna(0)
        )

    latest_52w = (
        index_data.sort_values("TIMESTAMP")
        .groupby("SYMBOL")
        .last()[["HI_52_WK", "LO_52_WK", "CLOSE"]]
        .reset_index()
    )
    latest_52w["DD_FROM_52W_HIGH"] = (
        (latest_52w["CLOSE"] - latest_52w["HI_52_WK"]) / latest_52w["HI_52_WK"] * 100
    )
    metrics = metrics.merge(
        latest_52w[["SYMBOL", "HI_52_WK", "LO_52_WK", "DD_FROM_52W_HIGH"]],
        on="SYMBOL",
        how="left",
    )
    metrics["CATEGORY"] = metrics["SYMBOL"].map(INDEX_CATEGORIES).fillna("Other")
    return metrics.sort_values("RET_1M", ascending=False).reset_index(drop=True)


def export_stock_cache(symbols: list[str], output_csv: Path) -> bool:
    if not STOCK_CACHE_RDATA.exists():
        return False
    symbol_expr = ",".join(f'"{s}"' for s in sorted(set(symbols)))
    r_script = f"""
load({str(STOCK_CACHE_RDATA)!r})
symbols <- c({symbol_expr})
stock_data <- stock_data[stock_data$SYMBOL %in% symbols, c("SYMBOL","TIMESTAMP","OPEN","HIGH","LOW","CLOSE","TOTTRDQTY")]
write.csv(stock_data, {str(output_csv)!r}, row.names = FALSE)
"""
    result = subprocess.run(["Rscript", "-e", r_script], cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        print("Warning: RData export failed; continuing without OHLC enrichment.")
        print(result.stderr.strip())
        return False
    return output_csv.exists()


def enrich_with_patterns(stocks: pd.DataFrame, stock_history: pd.DataFrame | None) -> pd.DataFrame:
    df = stocks.copy()
    defaults = {
        "PATTERN": "INSUFFICIENT_HISTORY",
        "IS_CONSOLIDATION_BREAKOUT": False,
        "CONSOLIDATION_WIDTH": math.nan,
        "VOLUME_RATIO": math.nan,
        "RESISTANCE": math.nan,
        "SUPPORT": math.nan,
        "SUPERTREND_STATE": "UNKNOWN",
        "SUPERTREND_VALUE": math.nan,
    }
    for col, value in defaults.items():
        df[col] = value

    if stock_history is None or stock_history.empty:
        return df

    hist = stock_history.copy()
    hist["TIMESTAMP"] = pd.to_datetime(hist["TIMESTAMP"])
    for idx, row in df.iterrows():
        symbol = row["SYMBOL"]
        symbol_hist = hist[hist["SYMBOL"] == symbol].sort_values("TIMESTAMP").tail(90)
        if symbol_hist.empty:
            continue
        pattern = classify_consolidation_breakout(symbol_hist, lookback=20, width_threshold=0.12, volume_multiplier=1.4)
        for key, value in pattern.items():
            df.at[idx, key] = value
        st = compute_supertrend(symbol_hist, period=10, multiplier=3.0)
        df.at[idx, "SUPERTREND_STATE"] = st["SUPERTREND_STATE"].iloc[-1]
        df.at[idx, "SUPERTREND_VALUE"] = float(st["SUPERTREND"].iloc[-1])
    return df


def enrich_with_peak_resilience(stocks: pd.DataFrame, stock_history: pd.DataFrame | None) -> pd.DataFrame:
    df = stocks.copy()
    defaults = {
        "FIFTY_TWO_WEEK_HIGH": math.nan,
        "FIFTY_TWO_WEEK_LOW": math.nan,
        "DRAWDOWN_FROM_52W_HIGH_PCT": math.nan,
        "RECOVERY_FROM_52W_LOW_PCT": math.nan,
        "DAYS_SINCE_52W_LOW": math.nan,
        "RECOVERY_SPEED_SCORE": math.nan,
        "WITHIN_20PCT_OF_HIGH": False,
        "NEAR_OR_ABOVE_52W_HIGH": False,
    }
    for col, value in defaults.items():
        df[col] = value

    if stock_history is None or stock_history.empty:
        return df

    hist = stock_history.copy()
    hist["TIMESTAMP"] = pd.to_datetime(hist["TIMESTAMP"])
    for idx, row in df.iterrows():
        symbol_hist = hist[hist["SYMBOL"] == row["SYMBOL"]].sort_values("TIMESTAMP").tail(252)
        if symbol_hist.empty:
            continue
        metrics = calculate_peak_resilience(symbol_hist, lookback=252, near_high_threshold=5.0)
        for key, value in metrics.items():
            df.at[idx, key] = value
    return df


def build_rotating_sector_universe(analysis: pd.DataFrame, rotating_sectors: list[str]) -> pd.DataFrame:
    df = analysis.copy()
    df["SECTOR_NAME"] = [
        assign_sector(symbol, company)
        for symbol, company in zip(df["SYMBOL"], df.get("COMPANY_NAME", pd.Series("", index=df.index)))
    ]
    return df[df["SECTOR_NAME"].isin(rotating_sectors)].copy()


def build_sector_stock_table(analysis: pd.DataFrame, rotating_sectors: list[str], top_n_per_sector: int = 8) -> pd.DataFrame:
    df = build_rotating_sector_universe(analysis, rotating_sectors)
    ranked_parts = []
    for sector, part in df.groupby("SECTOR_NAME", sort=False):
        ranked_parts.append(rank_stock_candidates(part).head(top_n_per_sector))
    if not ranked_parts:
        return pd.DataFrame()
    return pd.concat(ranked_parts, ignore_index=True)


def _fmt(value: object, suffix: str = "", digits: int = 1) -> str:
    try:
        if pd.isna(value):
            return "N/A"
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


# ===== MARKDOWN RENDERING =====

def _asset_data_uri(path: Path) -> str:
    """Embed a local image asset for standalone report portability."""
    try:
        if not path.exists():
            return ""
        mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    except Exception:
        return ""


def render_markdown(
    sector_rank: pd.DataFrame,
    candidates: pd.DataFrame,
    peak_resilience: pd.DataFrame,
    source_file: Path,
    generated_at: datetime,
    narratives: dict | None = None,
) -> str:
    analysis_date = candidates["ANALYSIS_DATE"].dropna().iloc[0] if "ANALYSIS_DATE" in candidates and candidates["ANALYSIS_DATE"].notna().any() else "N/A"
    lines = [
        "# Sector Rotation Investment Report",
        "",
        f"**{AGENT_BRAND}**",
        "",
        f"**Generated:** {generated_at.strftime('%Y-%m-%d')}  ",
        f"**Data as of:** {analysis_date}  ",
        f"**Source analysis:** `{source_file}`",
        "",
        f"> **Disclaimer:** {REPORT_DISCLAIMER}",
        f"> **Use Restriction:** This material must not be replicated or used with any intent of trading or recommendation. "
        f"Anyone doing so acts at their own risk and legal obligations. Agent Adda is not SEBI registered.",
        "",
    ]
    market_brief = (narratives or {}).get("market_brief", {})
    if market_brief:
        lines += [
            "## Market Brief",
            "",
            f"**Market Read:** {market_brief.get('market_read', '')}",
            "",
            f"**Risk Posture:** {market_brief.get('risk_posture', '')}",
            "",
            f"**Where to Focus:** {market_brief.get('where_to_focus', '')}",
            "",
            f"**What Would Change the View:** {market_brief.get('what_would_change_the_view', '')}",
            "",
        ]

    lines += [
        "## 1. Sector Rotation",
        "",
        "Current rotation is ranked using 1M return, 5D/1M/3M/6M relative strength versus Nifty 500, and short-term participation.",
        "",
        "| Rank | Index | Sector Lens | Close | 5D | 1M | 3M | 6M | RS 1M | Rotation Score |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, (_, row) in enumerate(sector_rank.iterrows(), start=1):
        lines.append(
            f"| {rank} | {row['SYMBOL']} | {row['SECTOR_NAME']} | {_fmt(row['CLOSE'], digits=2)} | "
            f"{_fmt(row['RET_5D'], '%')} | {_fmt(row['RET_1M'], '%')} | {_fmt(row['RET_3M'], '%')} | "
            f"{_fmt(row['RET_6M'], '%')} | {_fmt(row['RS_1M'], '%')} | {_fmt(row['ROTATION_SCORE'])} |"
        )

    lines += [
        "",
        "## 2. Investment Candidates",
        "",
        "Candidates are ranked within rotating sectors by technical score, relative strength, fundamental score, Supertrend state, trading signal, and consolidation breakout status.",
        "",
    ]
    for sector in sector_rank["SECTOR_NAME"].drop_duplicates():
        part = candidates[candidates["SECTOR_NAME"] == sector].head(5)
        if part.empty:
            continue
        lines += [
            f"### {sector}",
            "",
            "| Symbol | Company | Price | Signal | Setup | Action | Score | Tech | RS | Fund | RSI | Supertrend | Pattern | Volume Ratio |",
            "|---|---|---:|---|---|---|---:|---:|---:|---:|---:|---|---|---:|",
        ]
        for _, row in part.iterrows():
            lines.append(
                f"| {row['SYMBOL']} | {row.get('COMPANY_NAME', '')} | {_fmt(row.get('CURRENT_PRICE'), digits=2)} | "
                f"{row.get('TRADING_SIGNAL', '')} | {row.get('SETUP_CLASS', 'NEUTRAL')} | {row.get('ACTION_BUCKET', 'WATCHLIST')} | "
                f"{_fmt(row.get('INVESTMENT_SCORE'))} | {_fmt(row.get('TECHNICAL_SCORE'))} | "
                f"{_fmt(row.get('RELATIVE_STRENGTH'), '%')} | {_fmt(row.get('ENHANCED_FUND_SCORE'))} | {_fmt(row.get('RSI'))} | "
                f"{row.get('SUPERTREND_STATE', '')} | {row.get('PATTERN', '')} | {_fmt(row.get('VOLUME_RATIO'), 'x', 2)} |"
            )
        lines.append("")

    lines += [
        "## 3. Deep Technical Notes",
        "",
    ]
    top_candidates = candidates.head(18)
    for _, row in top_candidates.iterrows():
        breakout_text = "breakout confirmation present" if row.get("IS_CONSOLIDATION_BREAKOUT") else "no confirmed consolidation breakout"
        lines += [
            f"### {row['SYMBOL']} - {row.get('COMPANY_NAME', '')}",
            "",
            f"- **Sector:** {row.get('SECTOR_NAME')} | **Setup:** {row.get('SETUP_CLASS', 'NEUTRAL')} | **Action:** {row.get('ACTION_BUCKET', 'WATCHLIST')}",
            f"- **Action reason:** {row.get('ACTION_REASON', 'Mixed setup; wait for cleaner confirmation.')}",
            f"- **Relative strength:** {_fmt(row.get('RELATIVE_STRENGTH'), '%')} vs Nifty 500; RS rank score {_fmt(row.get('RS_RANK_SCORE'))}.",
            f"- **Technical pattern:** {row.get('PATTERN')} with {breakout_text}; resistance {_fmt(row.get('RESISTANCE'), digits=2)}, support {_fmt(row.get('SUPPORT'), digits=2)}.",
            f"- **Supertrend:** {row.get('SUPERTREND_STATE')} around {_fmt(row.get('SUPERTREND_VALUE'), digits=2)}.",
            f"- **Technofunda:** technical {_fmt(row.get('TECHNICAL_SCORE'))}, Minervini {_fmt(row.get('MINERVINI_SCORE'), digits=0)}, CAN SLIM {_fmt(row.get('CAN_SLIM_SCORE'), digits=0)}, enhanced fundamental {_fmt(row.get('ENHANCED_FUND_SCORE'))}.",
            "",
        ]

    lines += [
        "## 4. Peak Resilience & Fast Recovery",
        "",
        "This screen adds stocks in rotating sectors that remain within 20% of their 52-week high, are within 5% of the 52-week high or above it, and rank well on recovery velocity from the 52-week low.",
        "",
    ]
    if peak_resilience.empty:
        lines += ["No stocks passed the peak-resilience filter in the current rotating-sector universe.", ""]
    else:
        lines += [
            "| Rank | Symbol | Sector | Price | 52W High | 52W Low | Drawdown From High | Recovery From Low | Days Since Low | Recovery Speed | Peak Score |",
            "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for rank, (_, row) in enumerate(peak_resilience.head(25).iterrows(), start=1):
            lines.append(
                f"| {rank} | {row['SYMBOL']} | {row.get('SECTOR_NAME', '')} | {_fmt(row.get('CURRENT_PRICE'), digits=2)} | "
                f"{_fmt(row.get('FIFTY_TWO_WEEK_HIGH'), digits=2)} | {_fmt(row.get('FIFTY_TWO_WEEK_LOW'), digits=2)} | "
                f"{_fmt(row.get('DRAWDOWN_FROM_52W_HIGH_PCT'), '%')} | {_fmt(row.get('RECOVERY_FROM_52W_LOW_PCT'), '%')} | "
                f"{_fmt(row.get('DAYS_SINCE_52W_LOW'), digits=0)} | {_fmt(row.get('RECOVERY_SPEED_SCORE'), '%/day', 2)} | "
                f"{_fmt(row.get('PEAK_RESILIENCE_SCORE'))} |"
            )
        lines.append("")

    lines += [
        "## 5. Methodology",
        "",
        "- **Sector rotation:** 0.35 x RS 1M + 0.25 x 1M return + 0.20 x RS 5D + 0.10 x RS 3M + 0.10 x RS 6M.",
        "- **Investment score:** 0.38 x technical + 0.27 x RS rank + 0.25 x enhanced fundamental + pattern, Supertrend, and signal bonuses.",
        "- **Supertrend:** ATR-based calculation using local NSE OHLC cache with period 10 and multiplier 3.",
        "- **Consolidation breakout:** latest close above prior 20-session resistance after a base width of 12% or less, with volume ratio threshold of 1.4x where volume is available.",
        "- **Peak resilience:** filters for stocks no worse than 20% below 52-week high and within 5% of the 52-week high, then ranks by technical strength, RS, recovery speed from 52-week low, high proximity, and fundamentals.",
        "",
        "## 6. Full Disclaimer",
        "",
        FULL_LEGAL_DISCLAIMER,
        "",
    ]
    return "\n".join(lines)


# ===== FUNDAMENTAL DATA LOADING =====

def _load_fundamental_details(symbols: list[str]) -> dict:
    """Load P&L/quarterly/ratios data from persistent cache; fetch missing via R script and merge back."""
    fund_cols = ["SYMBOL", "pnl_summary", "quarterly_summary", "balance_sheet_summary", "ratios_summary"]
    CACHE = ROOT / "data" / "_sector_rotation_fund_cache.csv"

    def _read_src(path):
        try:
            df = pd.read_csv(path)
            if "symbol" in df.columns and "SYMBOL" not in df.columns:
                df = df.rename(columns={"symbol": "SYMBOL"})
            if "SYMBOL" in df.columns and "pnl_summary" in df.columns:
                return df[[c for c in fund_cols if c in df.columns]]
        except Exception:
            pass
        return None

    # Build working dataframe: use persistent cache only (P0-4: consolidated)
    # PG: legacy sources removed — all data now lives in the single cache file.
    # Legacy sources were: reports/Apex_Resilience_screener_fundamentals_*.csv,
    #   working-sector/output/fundamental_details.csv
    frames = []
    if CACHE.exists():
        f = _read_src(CACHE)
        if f is not None:
            frames.append(f)

    existing = pd.concat(frames).drop_duplicates("SYMBOL", keep="first") if frames else pd.DataFrame(columns=fund_cols)
    have = set(existing["SYMBOL"].tolist())
    missing = [s for s in symbols if s not in have]

    if missing:
        print(f"  Fetching fundamentals for {len(missing)} symbols: {missing[:8]}{'...' if len(missing)>8 else ''}")
        import tempfile, subprocess as sp
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tf:
            tf.write("\n".join(missing))
            syms_path = tf.name
        out_csv = ROOT / "data" / "_sector_rotation_fund_tmp.csv"
        rscript = ROOT / "working-sector" / "fetch_screener_fundamental_details.R"
        if rscript.exists():
            try:
                sp.run(
                    ["Rscript", str(rscript), syms_path, str(out_csv)],
                    capture_output=True, text=True, timeout=300, cwd=str(ROOT),
                )
                if out_csv.exists():
                    fetched = _read_src(out_csv)
                    if fetched is not None and len(fetched):
                        existing = pd.concat([existing, fetched]).drop_duplicates("SYMBOL", keep="first")
                        # Merge new rows into persistent cache (append-only, never overwrite)
                        cache_df = _read_src(CACHE) if CACHE.exists() else pd.DataFrame(columns=fund_cols)
                        if cache_df is None:
                            cache_df = pd.DataFrame(columns=fund_cols)
                        merged = pd.concat([cache_df, fetched]).drop_duplicates("SYMBOL", keep="first")
                        merged.to_csv(CACHE, index=False)
                        print(f"  Fetched {len(fetched)} symbols; cache now has {len(merged)} rows.")
                        # P0-4: clean up tmp file after successful merge into cache
                        if out_csv.exists():
                            out_csv.unlink()
            except Exception as exc:
                print(f"  Fundamental fetch failed ({exc}); using available data only.")
        try:
            import os; os.unlink(syms_path)
        except OSError:
            pass

    result: dict = {}
    for _, row in existing.iterrows():
        sym = str(row.get("SYMBOL", "")).strip()
        if sym:
            result[sym] = {
                "pnl": str(row.get("pnl_summary", "") or ""),
                "quarterly": str(row.get("quarterly_summary", "") or ""),
                "balance_sheet": str(row.get("balance_sheet_summary", "") or ""),
                "ratios": str(row.get("ratios_summary", "") or ""),
            }
    return result


# ===== SIGNAL LOGGER (P0-1) =====

_SIGNAL_LOG = ROOT / "data" / "signal_log.csv"
_SIGNAL_LOG_COLS = [
    "date_issued", "symbol", "sector", "company", "signal", "setup_class", "action_bucket", "action_reason",
    "investment_score", "technical_score", "rsi", "supertrend_state",
    "price_at_issue", "entry_low", "entry_high", "stop_loss", "target_1", "target_2",
    "regime_at_issue",
    "fno_pcr", "fno_oi_change_5d", "fno_buildup", "fno_signal",
    "fii_flow_signal",
    "insider_alert", "insider_score", "insider_detail",
    "date_resolved", "price_at_resolution", "return_pct", "hit_target", "hit_stop",
]


def _log_signals(candidates: pd.DataFrame, date: datetime, regime: str = "UNKNOWN") -> None:
    """Append today's candidates to the signal log without duplicating existing entries."""
    today_str = date.strftime("%Y-%m-%d")

    existing = pd.DataFrame(columns=_SIGNAL_LOG_COLS)
    if _SIGNAL_LOG.exists():
        try:
            existing = pd.read_csv(_SIGNAL_LOG)
        except Exception:
            pass

    already_logged = set()
    if not existing.empty and "date_issued" in existing.columns and "symbol" in existing.columns:
        already_logged = set(
            existing[existing["date_issued"] == today_str]["symbol"].tolist()
        )

    new_rows = []
    for _, r in candidates.iterrows():
        sym = str(r.get("SYMBOL", ""))
        if not sym or sym in already_logged:
            continue
        price = r.get("CURRENT_PRICE", math.nan)
        new_rows.append({
            "date_issued": today_str,
            "symbol": sym,
            "sector": r.get("SECTOR_NAME", ""),
            "company": r.get("COMPANY_NAME", ""),
            "signal": r.get("TRADING_SIGNAL", ""),
            "setup_class": r.get("SETUP_CLASS", "NEUTRAL"),
            "action_bucket": r.get("ACTION_BUCKET", "WATCHLIST"),
            "action_reason": r.get("ACTION_REASON", ""),
            "investment_score": r.get("INVESTMENT_SCORE", math.nan),
            "technical_score": r.get("TECHNICAL_SCORE", math.nan),
            "rsi": r.get("RSI", math.nan),
            "supertrend_state": r.get("SUPERTREND_STATE", ""),
            "price_at_issue": price,
            "entry_low": r.get("ENTRY_LOW", math.nan),
            "entry_high": r.get("ENTRY_HIGH", math.nan),
            "stop_loss": r.get("STOP_LOSS", math.nan),
            "target_1": r.get("TARGET_1", math.nan),
            "target_2": r.get("TARGET_2", math.nan),
            "regime_at_issue": regime,
            "fno_pcr": r.get("FNO_PCR", math.nan),
            "fno_oi_change_5d": r.get("FNO_OI_CHANGE_5D", math.nan),
            "fno_buildup": r.get("FNO_BUILDUP", ""),
            "fno_signal": r.get("FNO_SIGNAL", ""),
            "fii_flow_signal": r.get("_FII_FLOW_SIGNAL", ""),
            "insider_alert": r.get("INSIDER_ALERT", ""),
            "insider_score": r.get("INSIDER_SCORE", math.nan),
            "insider_detail": r.get("INSIDER_DETAIL", ""),
            "date_resolved": "",
            "price_at_resolution": math.nan,
            "return_pct": math.nan,
            "hit_target": "",
            "hit_stop": "",
        })

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        appended = new_df if existing.empty else pd.concat([existing, new_df], ignore_index=True)
        appended.to_csv(_SIGNAL_LOG, index=False)
        print(f"  Signal log: appended {len(new_rows)} new entries → {len(appended)} total rows.")
    else:
        print(f"  Signal log: no new entries (already logged for {today_str}).")


# ===== NARRATIVE GENERATION =====

def _build_narrative_prompt(sector_rank: pd.DataFrame, candidates: pd.DataFrame,
                             fund_details: dict | None = None) -> str:
    """Construct the full data prompt for LLM narrative generation."""
    data_date = (
        candidates["ANALYSIS_DATE"].dropna().iloc[0]
        if "ANALYSIS_DATE" in candidates.columns and candidates["ANALYSIS_DATE"].notna().any()
        else "recent"
    )
    lines = [
        f"NSE India Sector Rotation Analysis — Data as of {data_date}",
        "",
        "SECTOR ROTATION RANKINGS (vs Nifty 500 benchmark):",
    ]
    for rank, (_, row) in enumerate(sector_rank.iterrows(), start=1):
        ret5d = float(row.get("RET_5D", 0) or 0)
        ret1m = float(row.get("RET_1M", 0) or 0)
        ret3m = float(row.get("RET_3M", 0) or 0)
        ret6m = float(row.get("RET_6M", 0) or 0)
        rs1m = float(row.get("RS_1M", 0) or 0)
        score = float(row.get("ROTATION_SCORE", 0) or 0)
        close = float(row.get("CLOSE", 0) or 0)
        lines.append(
            f"  Rank #{rank}: {row['SECTOR_NAME']} ({row['SYMBOL']}) | "
            f"Index Close: {close:.2f} | 5D: {ret5d:+.1f}% | 1M: {ret1m:+.1f}% | "
            f"3M: {ret3m:+.1f}% | 6M: {ret6m:+.1f}% | RS vs Nifty500 1M: {rs1m:+.1f}% | "
            f"Rotation Score: {score:.1f} | Seasonal: {row.get('SEASONAL_SIGNAL', 'NEUTRAL')} | "
            f"Breadth(50DMA): {row.get('BREADTH_PCT50', float('nan')):.0f}% {row.get('BREADTH_SIGNAL', 'NO_DATA')}"
            + (f" ⚠ {row.get('BREADTH_DIVERGENCE')}" if str(row.get('BREADTH_DIVERGENCE', 'NONE')) != 'NONE' else "")
        )

    # PG: inject FII/DII flow context into LLM prompt (P1-3)
    try:
        from fetch_fii_dii_flows import load_flow_signals
        _flow = load_flow_signals()
        fii_5d = _flow.get("fii_net_5d", 0)
        dii_5d = _flow.get("dii_net_5d", 0)
        fsig = _flow.get("flow_signal", "NO_DATA")
        lines += [
            "",
            "INSTITUTIONAL FLOW CONTEXT:",
            f"  FII net (5-day rolling): ₹{fii_5d:+,.0f} Cr — Signal: {fsig}",
            f"  DII net (5-day rolling): ₹{dii_5d:+,.0f} Cr",
            f"  FII trend: {_flow.get('fii_trend', '?')} · DII trend: {_flow.get('dii_trend', '?')}",
        ]
    except Exception:
        pass  # graceful: flow data is optional context for LLM

    # PG: inject macro-economic backdrop into LLM prompt (P1-6)
    try:
        from fetch_macro_proxies import macro_context_for_llm, load_sector_tailwinds
        _macro_ctx = macro_context_for_llm()
        if _macro_ctx:
            lines += ["", "MACRO-ECONOMIC BACKDROP:", f"  {_macro_ctx}"]
            # Add sector-level tailwinds
            _tw_df = load_sector_tailwinds()
            if not _tw_df.empty:
                lines.append("  Sector macro tailwinds (positive = tailwind, negative = headwind):")
                for _, _twr in _tw_df.iterrows():
                    lines.append(f"    {_twr['SECTOR_NAME']}: {_twr['MACRO_TAILWIND']:+.2f} ({_twr.get('MACRO_DETAIL', '')})")
    except Exception:
        pass  # graceful: macro data is optional context for LLM

    lines += ["", "INVESTMENT CANDIDATES (all sectors):"]
    for _, row in candidates.iterrows():
        sym = row.get("SYMBOL", "")
        co = row.get("COMPANY_NAME", sym)
        sec = row.get("SECTOR_NAME", "")
        sig = row.get("TRADING_SIGNAL", "HOLD")
        score = float(row.get("INVESTMENT_SCORE", 50) or 50)
        tech = float(row.get("TECHNICAL_SCORE", 50) or 50)
        rs = float(row.get("RELATIVE_STRENGTH", 0) or 0)
        rsi = float(row.get("RSI", 50) or 50)
        st = row.get("SUPERTREND_STATE", "UNKNOWN")
        pat = row.get("PATTERN", "")
        vol = row.get("VOLUME_RATIO", math.nan)
        fund = float(row.get("ENHANCED_FUND_SCORE", 50) or 50)
        res = row.get("RESISTANCE", math.nan)
        sup = row.get("SUPPORT", math.nan)
        st_val = row.get("SUPERTREND_VALUE", math.nan)
        minv = row.get("MINERVINI_SCORE", "")
        canslim = row.get("CAN_SLIM_SCORE", "")
        price = row.get("CURRENT_PRICE", math.nan)

        res_str = f"₹{float(res):.2f}" if res and not (isinstance(res, float) and math.isnan(res)) else "N/A"
        sup_str = f"₹{float(sup):.2f}" if sup and not (isinstance(sup, float) and math.isnan(sup)) else "N/A"
        st_str = f"₹{float(st_val):.2f}" if st_val and not (isinstance(st_val, float) and math.isnan(st_val)) else "N/A"
        vol_str = f"{float(vol):.2f}x" if vol and not (isinstance(vol, float) and math.isnan(vol)) else "N/A"
        price_str = f"₹{float(price):.2f}" if price and not (isinstance(price, float) and math.isnan(price)) else "N/A"

        setup = row.get("SETUP_CLASS", "NEUTRAL")
        action = row.get("ACTION_BUCKET", "WATCHLIST")
        entry_low = row.get("ENTRY_LOW", math.nan)
        stop_loss = row.get("STOP_LOSS", math.nan)
        target_1 = row.get("TARGET_1", math.nan)
        target_2 = row.get("TARGET_2", math.nan)
        el_str = f"₹{float(entry_low):.2f}" if entry_low and not (isinstance(entry_low, float) and math.isnan(entry_low)) else "N/A"
        sl_str = f"₹{float(stop_loss):.2f}" if stop_loss and not (isinstance(stop_loss, float) and math.isnan(stop_loss)) else "N/A"
        t1_str = f"₹{float(target_1):.2f}" if target_1 and not (isinstance(target_1, float) and math.isnan(target_1)) else "N/A"
        t2_str = f"₹{float(target_2):.2f}" if target_2 and not (isinstance(target_2, float) and math.isnan(target_2)) else "N/A"

        stock_line = (
            f"  {sym} ({co}) | {sec} | Price: {price_str} | Signal: {sig} | Setup: {setup} | Action: {action} | "
            f"Score: {score:.1f} | Tech: {tech:.1f} | RS: {rs:+.1f}% | RSI: {rsi:.1f} | "
            f"Supertrend: {st} @ {st_str} | Pattern: {pat} | Vol: {vol_str} | "
            f"Fund: {fund:.1f} | Resistance: {res_str} | Support: {sup_str} | "
            f"Entry: {el_str} | Stop: {sl_str} | T1: {t1_str} | T2: {t2_str} | "
            f"Minervini: {minv} | CAN-SLIM: {canslim}"
        )
        # F&O derivative signals (P1-2)
        fno_signal = row.get("FNO_SIGNAL", "")
        fno_pcr_v = row.get("FNO_PCR", math.nan)
        fno_oi_chg = row.get("FNO_OI_CHANGE_5D", math.nan)
        fno_buildup = row.get("FNO_BUILDUP", "")
        fno_pcr_str = f"{float(fno_pcr_v):.2f}" if fno_pcr_v and not (isinstance(fno_pcr_v, float) and math.isnan(fno_pcr_v)) else "N/A"
        fno_oi_str = f"{float(fno_oi_chg):+.1f}%" if fno_oi_chg and not (isinstance(fno_oi_chg, float) and math.isnan(fno_oi_chg)) else "N/A"
        if fno_signal and str(fno_signal) not in ("", "nan", "None"):
            stock_line += f"\n    F&O: Signal={fno_signal} | PCR={fno_pcr_str} | OI Change 5D={fno_oi_str} | Buildup={fno_buildup}"
        # Insider/promoter alerts (P1-4)
        _ins_alert = row.get("INSIDER_ALERT", "")
        _ins_detail = row.get("INSIDER_DETAIL", "")
        if _ins_alert and str(_ins_alert) not in ("", "nan", "None"):
            stock_line += f"\n    Insider: {_ins_alert} — {_ins_detail}"
        # Corporate events (E4)
        _next_event = row.get("NEXT_EVENT", "")
        _next_event_days = row.get("NEXT_EVENT_DAYS", "")
        _event_detail = row.get("EVENT_DETAIL", "")
        if _next_event and str(_next_event) not in ("", "nan", "None"):
            _days_str = f" in {int(float(_next_event_days))}d" if _next_event_days not in ("", None) else ""
            stock_line += f"\n    Event: {_next_event}{_days_str} — {_event_detail}"
        fd = (fund_details or {}).get(str(sym), {})
        if fd.get("pnl"):
            stock_line += f"\n    P&L: {fd['pnl']}"
        if fd.get("quarterly"):
            stock_line += f"\n    Quarterly: {fd['quarterly']}"
        if fd.get("balance_sheet"):
            stock_line += f"\n    Balance Sheet: {fd['balance_sheet']}"
        if fd.get("ratios"):
            stock_line += f"\n    Ratios: {fd['ratios']}"
        lines.append(stock_line)

    lines += [
        "",
        "INSTRUCTIONS:",
        "Generate comprehensive, detailed investment narratives grounded strictly in the above data.",
        "Return only valid JSON with no markdown fences, no preamble, no trailing text.",
        "",
        "Required JSON structure (use \\n\\n to separate paragraphs within string values):",
        '{',
        '  "market_summary": "<3-4 sentences: dominant rotation theme, breadth, and tactical market context citing specific index levels, RS%, and scores>",',
        '  "sectors": {',
        '    "<sector_name>": {',
        '      "narrative": "<Para 1 — Rotation Dynamics: momentum metrics, score, multi-timeframe returns vs Nifty 500, breadth signals>\\n\\n<Para 2 — Fundamental Drivers: sector catalysts, policy tailwinds/headwinds, valuation context, earnings cycle>\\n\\n<Para 3 — Risk & Tactical View: key watchpoints, stop levels, entry triggers, position sizing guidance>",',
        '      "conviction": "<HIGH|MEDIUM|LOW>",',
        '      "key_themes": ["<theme 1 with a number>", "<theme 2 with a number>", "<theme 3 with a number>"]',
        '    }',
        '  },',
        '  "stocks": {',
        '    "<symbol>": {',
        '      "narrative": "<Para 1 — Technical Setup: price action, RSI, Supertrend level, pattern, volume ratio, resistance and support levels, trend phase>\\n\\n<Para 2 — Fundamental Quality & RS: fund score interpretation, relative strength vs benchmark, earnings quality, valuation context>\\n\\n<Para 3 — Risk/Reward & Actionable Guidance: specific entry zone, stop-loss level, price target, position sizing, catalyst to watch>",',
        '      "stance": "<CONSTRUCTIVE|NEUTRAL|CAUTIOUS>"',
        '    }',
        '  }',
        '}',
        "",
        "Strict rules — every violation will invalidate the output:",
        "- EVERY sentence must cite at least one specific number (price, %, score, ratio) from the data.",
        "- RSI > 75: flag as overbought, recommend against new full-size entries.",
        "- RSI < 45: flag momentum deterioration, tighten stops or avoid.",
        "- CONSOLIDATION_BREAKOUT + volume > 1.4x: label as high-conviction breakout with entry rationale.",
        "- NEAR_RESISTANCE: specify the resistance level and advise waiting for confirmed break.",
        "- Fund score > 65: explicitly state fundamental backing. Fund score < 50: label as momentum/speculative.",
        "- Where P&L, quarterly, balance sheet, and ratios data is provided for a stock, you MUST use it:",
        "  * Cite Sales figure and YoY growth % in the fundamental paragraph.",
        "  * Cite Net Profit and YoY growth % in the fundamental paragraph.",
        "  * Cite EPS and NPM (Net Profit Margin) % in the fundamental paragraph.",
        "  * Cite ROCE % in the fundamental paragraph.",
        "  * Comment on quarterly revenue and profit trend (improving/declining/lumpy).",
        "  * If debt is significant, mention it and assess leverage.",
        "- Where fundamental data is NOT provided, rely on fund score, Minervini, and CAN-SLIM scores.",
        "- Supertrend: always state the exact ₹ level as dynamic stop-loss support.",
        "- BUY: provide specific entry range. HOLD: state stop-loss and profit-booking trigger. SELL/WEAK: state exit level.",
        "- Sector conviction: HIGH if score > 10, MEDIUM if 5-10, LOW if < 5.",
        "- Do NOT use generic phrases like 'investors should consider' or 'it may be wise'. Be direct and specific.",
    ]
    return "\n".join(lines)


def _load_env_key(key: str) -> str | None:
    """Read a key from the project .env file (last non-empty, non-placeholder occurrence)."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return None
    result = None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == key:
            val = v.strip().strip('"').strip("'")
            if val and "your-" not in val.lower() and val.lower() != key.lower():
                result = val
    return result


def _llm_call(api_key: str, model: str, system_msg: str, user_msg: str,
              max_tokens: int = 16384, timeout: int = 250) -> dict:
    """Make a single OpenAI chat completion call via curl; return parsed JSON dict."""
    import subprocess
    import tempfile
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "max_completion_tokens": max_tokens,
    })
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tf:
        tf.write(payload)
        payload_path = tf.name
    try:
        result = subprocess.run(
            [
                "curl", "-s", "--max-time", str(timeout - 10),
                "https://api.openai.com/v1/chat/completions",
                "-H", f"Authorization: Bearer {api_key}",
                "-H", "Content-Type: application/json",
                "-d", f"@{payload_path}",
            ],
            capture_output=True, text=True, timeout=timeout,
        )
    finally:
        try:
            import os; os.unlink(payload_path)
        except OSError:
            pass
    if result.returncode != 0:
        raise RuntimeError(f"curl failed (rc={result.returncode}): {result.stderr[:200]}")
    data = json.loads(result.stdout)
    if "error" in data:
        raise RuntimeError(f"OpenAI API error: {data['error'].get('message', data['error'])}")
    choice = data["choices"][0]
    finish_reason = choice.get("finish_reason", "unknown")
    text = choice["message"]["content"].strip()
    if finish_reason == "length":
        raise ValueError("LLM response truncated — max_completion_tokens exceeded")
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:] if lines[0].startswith("```") else lines)
        if text.endswith("```"):
            text = text[:-3].strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= start:
        raise ValueError(f"No JSON object in LLM response. First 200: {text[:200]!r}")
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSONDecodeError: {exc}. Head: {text[start:start+300]!r}") from exc


def _build_stock_followup_prompt(missing_syms: list[str], candidates: pd.DataFrame,
                                  fund_details: dict | None = None) -> str:
    """Build a targeted follow-up prompt for stocks that the primary LLM call omitted."""
    sub = candidates[candidates["SYMBOL"].isin(missing_syms)]
    lines = [
        "Generate stock investment narratives for the following NSE India candidates.",
        "Return ONLY a JSON object with a 'stocks' key — no other keys, no markdown.",
        "",
        "STOCK DATA:",
    ]
    for _, row in sub.iterrows():
        sym = row.get("SYMBOL", "")
        co = row.get("COMPANY_NAME", sym)
        sec = row.get("SECTOR_NAME", "")
        sig = row.get("TRADING_SIGNAL", "HOLD")
        score = float(row.get("INVESTMENT_SCORE", 50) or 50)
        tech = float(row.get("TECHNICAL_SCORE", 50) or 50)
        rs = float(row.get("RELATIVE_STRENGTH", 0) or 0)
        rsi = float(row.get("RSI", 50) or 50)
        st = row.get("SUPERTREND_STATE", "UNKNOWN")
        fund = float(row.get("ENHANCED_FUND_SCORE", 50) or 50)
        res = row.get("RESISTANCE", math.nan)
        sup = row.get("SUPPORT", math.nan)
        st_val = row.get("SUPERTREND_VALUE", math.nan)
        price = row.get("CURRENT_PRICE", math.nan)
        vol = row.get("VOLUME_RATIO", math.nan)
        pat = row.get("PATTERN", "")
        res_str = f"₹{float(res):.2f}" if res and not (isinstance(res, float) and math.isnan(res)) else "N/A"
        sup_str = f"₹{float(sup):.2f}" if sup and not (isinstance(sup, float) and math.isnan(sup)) else "N/A"
        st_str = f"₹{float(st_val):.2f}" if st_val and not (isinstance(st_val, float) and math.isnan(st_val)) else "N/A"
        price_str = f"₹{float(price):.2f}" if price and not (isinstance(price, float) and math.isnan(price)) else "N/A"
        vol_str = f"{float(vol):.2f}x" if vol and not (isinstance(vol, float) and math.isnan(vol)) else "N/A"
        stock_line = (
            f"  {sym} ({co}) | {sec} | Price: {price_str} | Signal: {sig} | "
            f"Score: {score:.1f} | Tech: {tech:.1f} | RS: {rs:+.1f}% | RSI: {rsi:.1f} | "
            f"Supertrend: {st} @ {st_str} | Pattern: {pat} | Vol: {vol_str} | "
            f"Fund: {fund:.1f} | Resistance: {res_str} | Support: {sup_str}"
        )
        fd = (fund_details or {}).get(str(sym), {})
        if fd.get("pnl"):
            stock_line += f"\n    P&L: {fd['pnl']}"
        if fd.get("quarterly"):
            stock_line += f"\n    Quarterly: {fd['quarterly']}"
        if fd.get("ratios"):
            stock_line += f"\n    Ratios: {fd['ratios']}"
        lines.append(stock_line)
    lines += [
        "",
        "Required JSON format:",
        '{"stocks": {"<symbol>": {"narrative": "<Para 1 — Technical Setup>\\n\\n<Para 2 — Fundamental Quality & RS>\\n\\n<Para 3 — Risk/Reward & Actionable Guidance>", "stance": "<CONSTRUCTIVE|NEUTRAL|CAUTIOUS>"}}}',
        "",
        "Rules: cite specific numbers in every sentence; use fund data where provided; flag RSI > 75 as overbought.",
    ]
    return "\n".join(lines)


def _generate_llm_narratives(sector_rank: pd.DataFrame, candidates: pd.DataFrame,
                              fund_details: dict | None = None) -> dict:
    """Call OpenAI API (gpt-5.5) to generate structured narratives; follow up for any missed stocks."""
    import os

    api_key = (
        os.environ.get("OPENAI_API_KEY")
        or _load_env_key("OPENAI_API_KEY")
        or _load_env_key("AGENTIC_HARNESS_API_KEY")
    )
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set in environment or .env file")

    model = (
        os.environ.get("SHUNYAAI_ASSISTANT_MODEL")
        or _load_env_key("SHUNYAAI_ASSISTANT_MODEL")
        or "gpt-5.5"
    )

    system_msg = (
        "You are an expert quantitative equity analyst specialising in NSE India sector rotation "
        "and momentum investing. Generate precise, data-grounded investment narratives that cite "
        "specific numbers from the provided data. "
        "Output valid JSON only — no markdown fences, no preamble, no trailing commentary."
    )

    # Phase 1: full prompt
    prompt = _build_narrative_prompt(sector_rank, candidates, fund_details=fund_details)
    print(f"  Generating narratives via OpenAI {model}...")
    narratives = _llm_call(api_key, model, system_msg, prompt, max_tokens=16384, timeout=250)

    # Phase 2: follow-up for any stocks the LLM omitted
    all_syms = candidates["SYMBOL"].dropna().tolist()
    covered = set(narratives.get("stocks", {}).keys())
    missing_syms = [s for s in all_syms if s not in covered]
    if missing_syms:
        print(f"  Follow-up call for {len(missing_syms)} uncovered stocks: {missing_syms[:8]}{'...' if len(missing_syms) > 8 else ''}")
        followup_prompt = _build_stock_followup_prompt(missing_syms, candidates, fund_details=fund_details)
        try:
            followup = _llm_call(api_key, model, system_msg, followup_prompt, max_tokens=12288, timeout=200)
            extra_stocks = followup.get("stocks", {})
            if extra_stocks:
                narratives.setdefault("stocks", {}).update(extra_stocks)
                print(f"  Follow-up added narratives for {len(extra_stocks)} stocks.")
        except Exception as exc:
            print(f"  Follow-up call failed ({exc}); skipping.")

    return narratives


def _generate_rule_based_narratives(sector_rank: pd.DataFrame, candidates: pd.DataFrame) -> dict:
    """Generate data-driven narratives without API dependency."""
    narratives: dict = {"market_summary": "", "sectors": {}, "stocks": {}}

    # Market summary
    if not sector_rank.empty:
        top = sector_rank.iloc[0]
        second = sector_rank.iloc[1] if len(sector_rank) > 1 else None
        top_names = ", ".join(sector_rank.head(3)["SECTOR_NAME"].tolist())
        narratives["market_summary"] = (
            f"NSE rotation is led by {top['SECTOR_NAME']} (score {float(top.get('ROTATION_SCORE', 0)):.1f}, "
            f"+{float(top.get('RET_1M', 0)):.1f}% 1M) with broad cyclical participation across {top_names}. "
            f"The multi-sector rotation pattern signals risk-on positioning with institutional momentum in "
            f"{'defensive-growth' if 'Defence' in top['SECTOR_NAME'] else 'cyclical'} segments."
        )

    # Sector narratives
    for rank, (_, row) in enumerate(sector_rank.iterrows(), start=1):
        sector = str(row["SECTOR_NAME"])
        ret1m = float(row.get("RET_1M", 0) or 0)
        ret3m = float(row.get("RET_3M", 0) or 0)
        ret6m = float(row.get("RET_6M", 0) or 0)
        ret5d = float(row.get("RET_5D", 0) or 0)
        rs1m = float(row.get("RS_1M", 0) or 0)
        score = float(row.get("ROTATION_SCORE", 0) or 0)
        close = float(row.get("CLOSE", 0) or 0)

        accel = ret1m > (ret3m / 3.0) if ret3m != 0 else True
        momentum_desc = "accelerating" if accel else "decelerating"
        rs_desc = "strong outperformance" if rs1m > 8 else "moderate outperformance" if rs1m > 3 else "near-benchmark performance"

        para1 = (
            f"{sector} ranks #{rank} in the current NSE rotation screen with a composite score of {score:.1f}, "
            f"driven by a {ret1m:+.1f}% 1-month return and {rs1m:+.1f}% relative strength above Nifty 500 — {rs_desc}. "
            f"The 5-day return of {ret5d:+.1f}% suggests {'continued near-term momentum' if ret5d > 0 else 'brief consolidation within the broader uptrend'}. "
            f"Momentum is {momentum_desc}: the 1M gain of {ret1m:.1f}% "
            f"{'exceeds' if accel else 'lags'} the 3M annualized run-rate ({ret3m/3:.1f}% per month), "
            f"{'implying a fresh acceleration' if accel else 'suggesting momentum may be normalizing'}."
        )

        if ret6m > 15:
            para2 = (
                f"The {ret6m:.1f}% 6-month return establishes {sector} as a sustained outperformer, not a tactical bounce. "
                f"Multi-timeframe strength — 1M {ret1m:+.1f}%, 3M {ret3m:+.1f}%, 6M {ret6m:+.1f}% — confirms "
                f"deep institutional participation and structural sector tailwinds beyond short-term noise."
            )
        elif ret6m < 0:
            para2 = (
                f"The 6-month return of {ret6m:.1f}% reveals that the recent {ret1m:.1f}% 1M surge is a recovery rally "
                f"rather than a trend continuation. Positioning should remain tactical: the 1M relative strength of "
                f"{rs1m:+.1f}% vs Nifty 500 warrants attention but the negative 6M base demands caution on sizing."
            )
        else:
            para2 = (
                f"The balanced timeframe profile — 1M {ret1m:+.1f}%, 3M {ret3m:+.1f}%, 6M {ret6m:+.1f}% — "
                f"indicates a sector building momentum progressively. The rotation score of {score:.1f} and "
                f"1M relative strength of {rs1m:+.1f}% place this sector in the tactical opportunity zone."
            )

        para3 = (
            f"Key watchpoints: sustaining RS above {rs1m * 0.6:.1f}% (40% pullback threshold) on consolidation "
            f"would confirm the rotation is durable. "
            f"{'Risk: rotation score of ' + str(round(score, 1)) + ' is below 5, suggesting weak conviction — monitor for a drop out of the top 6.' if score < 5 else 'Conviction: HIGH — rotation score above 10 with RS in double digits supports active positioning.'}"
        )

        conviction = "HIGH" if score > 10 else "MEDIUM" if score > 5 else "LOW"
        key_themes = [
            f"{ret1m:+.1f}% 1M momentum",
            f"RS {rs1m:+.1f}% vs Nifty 500",
            f"Score {score:.1f} — #{rank} rotation",
        ]
        narratives["sectors"][sector] = {
            "narrative": f"{para1}\n\n{para2}\n\n{para3}",
            "conviction": conviction,
            "key_themes": key_themes,
        }

    # Stock narratives
    for _, row in candidates.iterrows():
        sym = str(row.get("SYMBOL", ""))
        co = str(row.get("COMPANY_NAME", sym))
        sector = str(row.get("SECTOR_NAME", ""))
        sig = str(row.get("TRADING_SIGNAL", "HOLD"))
        tech = float(row.get("TECHNICAL_SCORE", 50) or 50)
        rs = float(row.get("RELATIVE_STRENGTH", 0) or 0)
        rsi = float(row.get("RSI", 50) or 50)
        st_state = str(row.get("SUPERTREND_STATE", "UNKNOWN"))
        pattern = str(row.get("PATTERN", ""))
        vol = row.get("VOLUME_RATIO", math.nan)
        vol_f = float(vol) if vol and not (isinstance(vol, float) and math.isnan(vol)) else None
        fund = float(row.get("ENHANCED_FUND_SCORE", 50) or 50)
        res = row.get("RESISTANCE", math.nan)
        sup = row.get("SUPPORT", math.nan)
        st_val = row.get("SUPERTREND_VALUE", math.nan)
        inv_score = float(row.get("INVESTMENT_SCORE", 50) or 50)
        minv = row.get("MINERVINI_SCORE", "")
        canslim = row.get("CAN_SLIM_SCORE", "")
        price = row.get("CURRENT_PRICE", math.nan)

        res_str = f"₹{float(res):.2f}" if res and not (isinstance(res, float) and math.isnan(res)) else "resistance"
        sup_str = f"₹{float(sup):.2f}" if sup and not (isinstance(sup, float) and math.isnan(sup)) else "support"
        st_str = f"₹{float(st_val):.2f}" if st_val and not (isinstance(st_val, float) and math.isnan(st_val)) else "the dynamic level"
        price_str = f"₹{float(price):.2f}" if price and not (isinstance(price, float) and math.isnan(price)) else "current price"

        rsi_desc = (
            "deep overbought territory (RSI >75) — momentum is extended and pullback risk is elevated"
            if rsi > 75 else
            "overbought-approaching levels (RSI 65-75) — trend is strong but upside may be limited near-term"
            if rsi > 65 else
            "healthy trending momentum (RSI 50-65) — room for further upside without overextension"
            if rsi > 50 else
            "neutral-to-weak momentum (RSI <50) — watch for confirmation before adding"
        )

        vol_desc = (
            f"Volume at {vol_f:.2f}x average confirms institutional participation"
            if vol_f and vol_f >= 1.4 else
            f"volume at {vol_f:.2f}x average is below the 1.4x breakout threshold"
            if vol_f else
            "volume data unavailable"
        )

        if pattern == "CONSOLIDATION_BREAKOUT":
            tech_para = (
                f"{co} ({sym}) at {price_str} has delivered a high-conviction consolidation breakout above prior "
                f"20-session resistance at {res_str}, with {vol_desc}. "
                f"RSI at {rsi:.1f} reflects {rsi_desc}. "
                f"Supertrend is {st_state.lower()} at {st_str}, providing a rising dynamic floor. "
                f"Technical score of {tech:.1f}/100 ranks this as a top-tier setup in {sector}."
            )
        elif pattern == "NEAR_RESISTANCE":
            tech_para = (
                f"{co} ({sym}) at {price_str} is testing key resistance at {res_str}, "
                f"with immediate support at {sup_str}. "
                f"RSI at {rsi:.1f} is in {rsi_desc}. "
                f"Supertrend is {st_state.lower()} at {st_str}; a decisive close above resistance with volume "
                f"would upgrade this to a breakout setup. Technical score: {tech:.1f}/100."
            )
        else:
            tech_para = (
                f"{co} ({sym}) at {price_str} is in a {pattern.replace('_', ' ').lower()} phase. "
                f"RSI at {rsi:.1f} reflects {rsi_desc}. "
                f"Supertrend is {st_state.lower()} at {st_str}, with {vol_desc}. "
                f"Key levels: resistance {res_str}, support {sup_str}. Technical score: {tech:.1f}/100."
            )

        fund_tier = "strong fundamental backing (score {:.1f}/100)".format(fund) if fund > 65 else \
                    "moderate fundamentals (score {:.1f}/100)".format(fund) if fund > 50 else \
                    "below-average fundamental quality (score {:.1f}/100) — primarily a momentum/technical play".format(fund)
        minv_str = f"Minervini score {minv}" if minv else ""
        canslim_str = f"CAN SLIM {canslim}" if canslim else ""
        scores_str = ", ".join(x for x in [minv_str, canslim_str] if x)

        stance = "CONSTRUCTIVE" if sig in ("BUY", "STRONG_BUY") else "CAUTIOUS" if sig == "SELL" else "NEUTRAL"
        stance_desc = (
            "Active entry — breakout or strong momentum warrants a position"
            if stance == "CONSTRUCTIVE" else
            "Exit or avoid — technical or fundamental signals are deteriorating"
            if stance == "CAUTIOUS" else
            "Hold existing positions — monitor for a catalyst to upgrade or downgrade"
        )

        fund_para = (
            f"Fundamentals: {fund_tier}. "
            f"Relative strength of {rs:+.1f}% vs Nifty 500 places {sym} "
            f"{'well above' if rs > 20 else 'above' if rs > 10 else 'in line with'} market. "
            + (f"Institutional quality metrics: {scores_str}. " if scores_str else "") +
            f"Investment score: {inv_score:.1f}/100. Stance: {stance} — {stance_desc}."
        )

        narratives["stocks"][sym] = {
            "narrative": f"{tech_para}\n\n{fund_para}",
            "stance": stance,
        }

    return narratives


def generate_narratives(sector_rank: pd.DataFrame, candidates: pd.DataFrame,
                        fund_details: dict | None = None) -> dict:
    """Generate investment narratives. Uses OpenAI API if available, falls back to rule-based."""
    try:
        return _generate_llm_narratives(sector_rank, candidates, fund_details=fund_details)
    except Exception as exc:
        print(f"  LLM narrative generation skipped ({type(exc).__name__}), using rule-based narratives.")
        return _generate_rule_based_narratives(sector_rank, candidates)


def _latest_breadth_row(breadth_history: pd.DataFrame | None) -> dict:
    if breadth_history is None or breadth_history.empty:
        return {}
    return breadth_history.iloc[-1].to_dict()


def _build_market_brief_prompt(
    sector_rank: pd.DataFrame,
    candidates: pd.DataFrame,
    regime_info: dict | None = None,
    cycle_info: dict | None = None,
    flow_info: dict | None = None,
    macro_context: str = "",
    breadth_history: pd.DataFrame | None = None,
) -> str:
    """Build a compact prompt for the dashboard market brief."""
    top_sectors = []
    for rank, (_, row) in enumerate(sector_rank.head(6).iterrows(), start=1):
        top_sectors.append(
            f"#{rank} {row.get('SECTOR_NAME', '')}: score {float(row.get('ROTATION_SCORE', 0) or 0):.1f}, "
            f"1M {float(row.get('RET_1M', 0) or 0):+.1f}%, RS 1M {float(row.get('RS_1M', 0) or 0):+.1f}%"
        )

    signal_counts = candidates.get("TRADING_SIGNAL", pd.Series(dtype=str)).value_counts().to_dict() if not candidates.empty else {}
    breadth = _latest_breadth_row(breadth_history)
    return "\n".join(
        [
            "Create a concise NSE dashboard market brief from these signals.",
            "Return only valid JSON with keys: market_read, risk_posture, where_to_focus, what_would_change_the_view.",
            "Each value must be 2-4 sentences, direct and actionable, with specific numbers.",
            "",
            f"Regime: {regime_info or {}}",
            f"Economic cycle: {cycle_info or {}}",
            f"FII/DII flow: {flow_info or {}}",
            f"Breadth latest: {breadth}",
            f"Macro backdrop: {macro_context}",
            f"Signal counts: {signal_counts}",
            "Top sectors:",
            *top_sectors,
            "",
            "Interpret mixed evidence explicitly. If bear trend and weak breadth conflict with bullish divergence or TRIN strength, call it defensive but alert for reversal.",
        ]
    )


def _generate_rule_based_market_brief(
    sector_rank: pd.DataFrame,
    candidates: pd.DataFrame,
    regime_info: dict | None = None,
    cycle_info: dict | None = None,
    flow_info: dict | None = None,
    macro_context: str = "",
    breadth_history: pd.DataFrame | None = None,
) -> dict:
    """Generate a deterministic market brief when the LLM is unavailable."""
    regime = str((regime_info or {}).get("current_regime", "UNKNOWN"))
    regime_conf = float((regime_info or {}).get("confidence", 0) or 0)
    cycle = str((cycle_info or {}).get("cycle_phase", "UNKNOWN"))
    cycle_conf = float((cycle_info or {}).get("confidence", 0) or 0)
    preferred = ", ".join((cycle_info or {}).get("preferred_sectors", [])[:4]) or "sector leaders"
    avoid = ", ".join((cycle_info or {}).get("avoid_sectors", [])[:4]) or "extended laggards"
    flow_signal = str((flow_info or {}).get("flow_signal", "NO_DATA"))
    fii_5d = float((flow_info or {}).get("fii_net_5d", 0) or 0)
    dii_5d = float((flow_info or {}).get("dii_net_5d", 0) or 0)
    breadth = _latest_breadth_row(breadth_history)
    osc = float(breadth.get("oscillator", 0) or 0)
    trin = float(breadth.get("trin", 0) or 0)
    breadth_signal = str(breadth.get("signal", "NO_DATA"))
    trin_signal = str(breadth.get("trin_signal", "NO_DATA"))
    divergence = str(breadth.get("divergence", "NONE"))
    top = sector_rank.iloc[0] if not sector_rank.empty else pd.Series(dtype=object)
    top_sector = str(top.get("SECTOR_NAME", "N/A"))
    top_score = float(top.get("ROTATION_SCORE", 0) or 0)
    top_1m = float(top.get("RET_1M", 0) or 0)
    buy_count = int(candidates.get("TRADING_SIGNAL", pd.Series(dtype=str)).isin(["BUY", "STRONG_BUY"]).sum()) if not candidates.empty else 0

    defensive = regime in {"BEAR_TREND", "CHOP"} or cycle == "SLOWDOWN"
    posture = "Defensive but alert for reversal" if defensive and divergence != "NONE" else "Defensive" if defensive else "Constructive"

    return {
        "market_read": (
            f"Regime is {regime.replace('_', ' ')} with {regime_conf:.0%} confidence while the economic cycle is {cycle.replace('_', ' ')} "
            f"with {cycle_conf:.0%} confidence. Breadth is mixed: McClellan is {breadth_signal} at {osc:+.1f}, TRIN is {trin:.2f} "
            f"({trin_signal}), and divergence is {divergence}, so the tape is weak on trend but showing internal reversal pressure."
        ),
        "risk_posture": (
            f"{posture}: keep position sizing controlled because FII 5D flow is ₹{fii_5d:+,.0f} Cr while DII 5D flow is ₹{dii_5d:+,.0f} Cr "
            f"({flow_signal}). New exposure should wait for breadth confirmation unless the setup has a defined stop and the score justifies risk; current BUY count is {buy_count}."
        ),
        "where_to_focus": (
            f"Focus first on {preferred}, which aligns with the {cycle.replace('_', ' ')} cycle map. Current rotation is led by {top_sector} "
            f"with score {top_score:.1f} and {top_1m:+.1f}% 1M return; avoid or downsize {avoid} until regime and breadth improve."
        ),
        "what_would_change_the_view": (
            f"Turn more constructive if the regime exits {regime.replace('_', ' ')}, McClellan holds above 0 without a failed divergence, and Nifty breadth recovers above 50% of stocks over the 200DMA. "
            f"Turn more defensive if TRIN rises above 1.40, McClellan rolls below 0, or the macro backdrop worsens from the current read: {macro_context[:180]}."
        ),
    }


def generate_market_brief(
    sector_rank: pd.DataFrame,
    candidates: pd.DataFrame,
    regime_info: dict | None = None,
    cycle_info: dict | None = None,
    flow_info: dict | None = None,
    macro_context: str = "",
    breadth_history: pd.DataFrame | None = None,
) -> dict:
    """Generate LLM market brief with deterministic fallback."""
    import os

    fallback = _generate_rule_based_market_brief(
        sector_rank,
        candidates,
        regime_info=regime_info,
        cycle_info=cycle_info,
        flow_info=flow_info,
        macro_context=macro_context,
        breadth_history=breadth_history,
    )
    api_key = (
        os.environ.get("OPENAI_API_KEY")
        or _load_env_key("OPENAI_API_KEY")
        or _load_env_key("AGENTIC_HARNESS_API_KEY")
    )
    if not api_key:
        return fallback

    model = (
        os.environ.get("SHUNYAAI_ASSISTANT_MODEL")
        or _load_env_key("SHUNYAAI_ASSISTANT_MODEL")
        or "gpt-5.5"
    )
    try:
        prompt = _build_market_brief_prompt(
            sector_rank,
            candidates,
            regime_info=regime_info,
            cycle_info=cycle_info,
            flow_info=flow_info,
            macro_context=macro_context,
            breadth_history=breadth_history,
        )
        print(f"  Generating LLM market brief via OpenAI {model}...")
        brief = _llm_call(
            api_key,
            model,
            "You are an NSE India market strategist. Return valid JSON only.",
            prompt,
            max_tokens=4096,
            timeout=120,
        )
        required = ["market_read", "risk_posture", "where_to_focus", "what_would_change_the_view"]
        if all(str(brief.get(key, "")).strip() for key in required):
            return {key: str(brief[key]).strip() for key in required}
    except Exception as exc:
        print(f"  LLM market brief skipped ({type(exc).__name__}); using rule-based brief.")
    return fallback


# ===== HTML HELPERS =====

def _h(val: object) -> str:
    """HTML-escape a value, returning em-dash for None/NaN."""
    if val is None:
        return "—"
    if isinstance(val, float) and math.isnan(val):
        return "—"
    return html_mod.escape(str(val))


def _fmth(value: object, suffix: str = "", digits: int = 1) -> str:
    """Format a numeric value for HTML display."""
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return "—"
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return html_mod.escape(str(value)) if value else "—"


def _signal_badge(signal: str) -> str:
    sig = str(signal).upper().replace(" ", "_")
    css_map = {
        "STRONG_BUY": "sig-sb", "BUY": "sig-buy",
        "HOLD": "sig-hold", "WEAK_HOLD": "sig-wh", "SELL": "sig-sell",
    }
    label_map = {
        "STRONG_BUY": "Strong Buy", "BUY": "Buy",
        "HOLD": "Hold", "WEAK_HOLD": "Weak Hold", "SELL": "Sell",
    }
    css = css_map.get(sig, "sig-hold")
    label = label_map.get(sig, html_mod.escape(signal))
    return f'<span class="sig {css}">{label}</span>'


def _st_badge(state: str) -> str:
    css = "st-bull" if state == "BULLISH" else "st-bear" if state == "BEARISH" else "st-uk"
    label = {"BULLISH": "Bullish ↑", "BEARISH": "Bearish ↓", "UNKNOWN": "—"}.get(state, html_mod.escape(state))
    return f'<span class="stb {css}">{label}</span>'


def _pattern_badge(pattern: str) -> str:
    label_map = {
        "CONSOLIDATION_BREAKOUT": "Breakout ★",
        "NEAR_RESISTANCE": "Near Res.",
        "BASE_BUILDING": "Base Build",
        "TRENDING_OR_CHOPPY": "Trending",
        "INSUFFICIENT_HISTORY": "Low Data",
    }
    css_map = {
        "CONSOLIDATION_BREAKOUT": "pat-cb",
        "NEAR_RESISTANCE": "pat-nr",
        "BASE_BUILDING": "pat-bb",
        "TRENDING_OR_CHOPPY": "pat-tc",
        "INSUFFICIENT_HISTORY": "pat-ih",
    }
    label = label_map.get(pattern, html_mod.escape(pattern))
    css = css_map.get(pattern, "pat-tc")
    return f'<span class="pat {css}">{label}</span>'


def _score_bar(score: object, cls: str = "invest") -> str:
    try:
        s = float(score) if score is not None else 0.0
        if math.isnan(s):
            s = 0.0
    except (TypeError, ValueError):
        s = 0.0
    w = max(0.0, min(100.0, s))
    return (
        f'<div class="sbar">'
        f'<span class="sv">{s:.1f}</span>'
        f'<div class="st2"><div class="sf sf-{cls}" style="width:{w:.0f}%"></div></div>'
        f'</div>'
    )


def _rsi_cell(rsi: object) -> str:
    try:
        r = float(rsi) if rsi is not None else math.nan
        if math.isnan(r):
            return "—"
    except (TypeError, ValueError):
        return "—"
    css = "rsi-h" if r > 75 else "rsi-w" if r > 65 else "rsi-n" if r > 50 else "rsi-c"
    return f'<span class="{css}">{r:.1f}</span>'


def _ret_cell(ret: object, pct: bool = True) -> str:
    try:
        v = float(ret) if ret is not None else math.nan
        if math.isnan(v):
            return "—"
    except (TypeError, ValueError):
        return "—"
    css = "rp" if v > 0 else "rn" if v < 0 else "rz"
    sign = "+" if v > 0 else ""
    suf = "%" if pct else ""
    return f'<span class="{css}">{sign}{v:.1f}{suf}</span>'


def _vol_cell(vol: object) -> str:
    try:
        v = float(vol) if vol is not None else math.nan
        if math.isnan(v):
            return "—"
    except (TypeError, ValueError):
        return "—"
    css = "vh" if v >= 1.5 else "vm" if v >= 1.0 else "vl"
    return f'<span class="{css}">{v:.2f}×</span>'


def _setup_badge(setup_class: str) -> str:
    label_map = {
        "LEADER_BREAKOUT":     "⭐ Leader Breakout",
        "FAST_RECOVERY":       "🚀 Fast Recovery",
        "BASE_NEAR_HIGH":      "🏔 Base Near High",
        "PULLBACK_IN_UPTREND": "🔄 Pullback Buy",
        "MOMENTUM_EXTENDED":   "⚠️ Extended",
        "WEAK_TREND":          "🔻 Weak Trend",
        "NEUTRAL":             "Neutral",
    }
    css_map = {
        "LEADER_BREAKOUT":     "setup-lb",
        "FAST_RECOVERY":       "setup-fr",
        "BASE_NEAR_HIGH":      "setup-bnh",
        "PULLBACK_IN_UPTREND": "setup-pu",
        "MOMENTUM_EXTENDED":   "setup-me",
        "WEAK_TREND":          "setup-wt",
        "NEUTRAL":             "setup-n",
    }
    label = label_map.get(setup_class, html_mod.escape(setup_class))
    css = css_map.get(setup_class, "setup-n")
    return f'<span class="setup {css}">{label}</span>'


def _action_badge(action_bucket: str) -> str:
    label_map = {
        "BUY_WATCH": "Buy Watch",
        "BREAKOUT_WATCH": "Breakout Watch",
        "HOLD_TRAIL": "Hold/Trail",
        "WAIT_FOR_PULLBACK": "Wait Pullback",
        "AVOID": "Avoid",
        "WATCHLIST": "Watchlist",
    }
    css_map = {
        "BUY_WATCH": "act-buy",
        "BREAKOUT_WATCH": "act-brk",
        "HOLD_TRAIL": "act-hold",
        "WAIT_FOR_PULLBACK": "act-wait",
        "AVOID": "act-avoid",
        "WATCHLIST": "act-watch",
    }
    label = label_map.get(action_bucket, html_mod.escape(action_bucket))
    css = css_map.get(action_bucket, "act-watch")
    return f'<span class="action {css}">{label}</span>'


def _cycle_tag_badge(tag: object, adjustment: object = 0) -> str:
    tag_s = str(tag or "")
    if tag_s in ("", "nan", "None"):
        return ""
    try:
        adj = int(float(adjustment or 0))
    except (TypeError, ValueError):
        adj = 0
    color_map = {
        "CYCLE_FAVOURED": ("#ecfdf5", "#047857"),
        "CYCLE_UNFAVOURED": ("#fef2f2", "#b91c1c"),
        "CYCLE_NEUTRAL": ("#f8fafc", "#64748b"),
    }
    bg, fg = color_map.get(tag_s, ("#f8fafc", "#64748b"))
    label = tag_s.replace("_", " ")
    return (
        f'<span style="display:inline-block;margin-top:3px;padding:2px 6px;'
        f'border-radius:999px;background:{bg};color:{fg};border:1px solid rgba(0,0,0,.08);'
        f'font-size:9px;font-weight:700">{html_mod.escape(label)} · Cycle {adj:+d}</span>'
    )


def _price_fmt(v: object) -> str:
    try:
        f = float(v)
        if math.isnan(f):
            return "—"
        return f"₹{f:.2f}"
    except (TypeError, ValueError):
        return "—"


def _dd_cell(dd: object) -> str:
    try:
        v = float(dd) if dd is not None else math.nan
        if math.isnan(v):
            return "—"
    except (TypeError, ValueError):
        return "—"
    css = "dds" if v >= -3 else "ddm" if v >= -10 else "ddl"
    return f'<span class="{css}">{v:.1f}%</span>'


_PARA_LABELS = [
    ("Technical Setup", "🔍"),
    ("Fundamental Quality & RS", "📊"),
    ("Risk/Reward & Action", "🎯"),
]
_SECTOR_PARA_LABELS = [
    ("Rotation Dynamics", "📈"),
    ("Fundamental Drivers", "🏭"),
    ("Risk & Tactical View", "⚠️"),
]

def _narrative_html(text: str, is_sector: bool = False) -> str:
    """Convert narrative text (\\n\\n separated) to labelled HTML paragraphs."""
    if not text:
        return "<p><em>Narrative not available.</em></p>"
    paras = [p.strip() for p in text.replace("\\n\\n", "\n\n").split("\n\n") if p.strip()]
    if not paras:
        paras = [p.strip() for p in text.split("\n") if p.strip()]
    if not paras:
        paras = [text.strip()]
    labels = _SECTOR_PARA_LABELS if is_sector else _PARA_LABELS
    html_parts = []
    for i, para in enumerate(paras):
        if i < len(labels):
            label, icon = labels[i]
            html_parts.append(
                f'<div class="narr-section">'
                f'<div class="narr-label">{icon} {html_mod.escape(label)}</div>'
                f'<p>{html_mod.escape(para)}</p>'
                f'</div>'
            )
        else:
            html_parts.append(f"<p>{html_mod.escape(para)}</p>")
    return "\n".join(html_parts)


# ===== INTERACTIVE HTML RENDERING =====

_CSS = """
:root {
  --bg: #f0f4f8;
  --card: #ffffff;
  --text: #1a2332;
  --muted: #64748b;
  --border: #e2e8f0;
  --primary: #1e3a5f;
  --primary-alt: #2563eb;
  --hdr-h: 56px;
  --nav-h: 44px;
  --radius: 8px;
  --shadow: 0 1px 3px rgba(0,0,0,0.08);
  --shadow-md: 0 4px 8px rgba(0,0,0,0.1);
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Inter",sans-serif;background:var(--bg);color:var(--text);line-height:1.6;font-size:14px}
a{color:var(--primary-alt);text-decoration:none}

/* ---- HEADER ---- */
.site-hdr{background:var(--primary);color:#fff;position:sticky;top:0;z-index:200;box-shadow:var(--shadow-md);height:var(--hdr-h)}
.hdr-inner{max-width:1400px;margin:0 auto;padding:0 20px;height:100%;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.hdr-brand{display:flex;align-items:center;gap:10px;min-width:0}
.brand-logo{width:38px;height:38px;border-radius:8px;object-fit:cover;background:#fff;border:1px solid rgba(255,255,255,.4);flex-shrink:0}
.hdr-copy{min-width:0}
.hdr-kicker{font-size:10px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:rgba(255,255,255,.78);line-height:1.2;white-space:nowrap}
.hdr-title{font-size:1.05rem;font-weight:700;letter-spacing:-0.02em;white-space:nowrap}
.hdr-meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.mbadge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600;white-space:nowrap}
.mbadge-date{background:rgba(255,255,255,0.18);color:#fff}
.mbadge-data{background:rgba(255,255,255,0.1);color:rgba(255,255,255,0.85)}

/* ---- DISCLAIMER ---- */
.disc{background:#fff8e1;border-bottom:1px solid #ffe082;color:#5d4037;padding:7px 20px;font-size:11px;text-align:center;line-height:1.45}
.disc strong{font-weight:800}
.print-page-header,.print-page-footer{display:none}

/* ---- NAV ---- */
.main-nav{background:var(--card);border-bottom:2px solid var(--border);position:sticky;top:var(--hdr-h);z-index:190}
.nav-inner{max-width:1400px;margin:0 auto;padding:0 16px;display:flex;overflow-x:auto;gap:0}
.nav-btn{background:none;border:none;padding:10px 18px;font-size:13px;font-weight:500;color:var(--muted);cursor:pointer;border-bottom:2.5px solid transparent;margin-bottom:-2px;transition:all .15s;white-space:nowrap}
.nav-btn:hover{color:var(--primary-alt)}
.nav-btn.active{color:var(--primary);border-bottom-color:var(--primary);font-weight:700}

/* ---- CONTENT ---- */
.content{max-width:1400px;margin:0 auto;padding:20px}
.tab-pane{display:none}
.tab-pane.active{display:block}

/* ---- CARDS ---- */
.card{background:var(--card);border-radius:var(--radius);border:1px solid var(--border);box-shadow:var(--shadow);padding:18px;margin-bottom:16px}
.card-title{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:10px}

/* ---- SUMMARY METRICS ---- */
.metrics-row{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}
.metric-card{flex:1;min-width:160px;background:var(--card);border-radius:var(--radius);border:1px solid var(--border);padding:14px 16px;box-shadow:var(--shadow)}
.metric-label{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:5px}
.metric-value{font-size:1.6rem;font-weight:800;color:var(--primary);line-height:1}
.metric-sub{font-size:11px;color:var(--muted);margin-top:3px}

/* ---- OVERVIEW GRID ---- */
.overview-grid{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-bottom:20px}
@media(max-width:900px){.overview-grid{grid-template-columns:1fr}}
.summary-card{background:var(--card);border-radius:var(--radius);border:1px solid var(--border);box-shadow:var(--shadow);padding:18px;min-width:0;max-width:100%;overflow-wrap:anywhere}
.summary-card h3{font-size:13px;font-weight:700;color:var(--primary);margin-bottom:10px}
.summary-card p{font-size:13px;line-height:1.65;color:var(--text)}
.brief-card{background:#fff;border:1px solid var(--border);border-radius:8px;box-shadow:var(--shadow);padding:16px 18px;margin:10px 0 12px}
.brief-title{font-size:13px;font-weight:800;color:var(--primary);text-transform:uppercase;letter-spacing:.04em;margin-bottom:10px}
.brief-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.brief-block{border-left:3px solid #3b82f6;background:#f8fafc;padding:10px 11px;border-radius:6px;min-width:0}
.brief-label{font-size:10px;font-weight:800;color:#475569;text-transform:uppercase;margin-bottom:5px}
.brief-text{font-size:12px;line-height:1.55;color:var(--text);overflow-wrap:anywhere}
@media(max-width:900px){.brief-grid{grid-template-columns:1fr}}
.buy-list{list-style:none;padding:0}
.buy-list li{padding:5px 0;border-bottom:1px solid var(--border);font-size:13px;display:flex;align-items:center;gap:8px}
.buy-list li:last-child{border-bottom:none}

/* ---- CHART ---- */
.chart-wrap{background:var(--card);border-radius:var(--radius);border:1px solid var(--border);padding:20px;margin-bottom:20px;position:relative;height:280px}
.chart-title{font-size:12px;font-weight:700;color:var(--primary);margin-bottom:12px;text-transform:uppercase;letter-spacing:.06em}

/* ---- TABLES ---- */
.tbl-wrap{display:block;width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch;border-radius:var(--radius);border:1px solid var(--border);background:var(--card);margin-bottom:16px;box-shadow:var(--shadow)}
table{width:100%;border-collapse:collapse;font-size:13px}
#tab-candidates table{min-width:1360px;table-layout:fixed}
#tab-candidates table colgroup col:nth-child(1){width:90px}
#tab-candidates table colgroup col:nth-child(2){width:135px}
#tab-candidates table colgroup col:nth-child(3){width:82px}
#tab-candidates table colgroup col:nth-child(4){width:140px}
#tab-candidates table colgroup col:nth-child(5){width:70px}
#tab-candidates table colgroup col:nth-child(6){width:70px}
#tab-candidates table colgroup col:nth-child(7){width:70px}
#tab-candidates table colgroup col:nth-child(8){width:60px}
#tab-candidates table colgroup col:nth-child(9){width:54px}
#tab-candidates table colgroup col:nth-child(10){width:90px}
#tab-candidates table colgroup col:nth-child(11){width:82px}
#tab-candidates table colgroup col:nth-child(12){width:58px}
#tab-candidates table colgroup col:nth-child(13){width:80px}
#tab-candidates table colgroup col:nth-child(14){width:90px}
#tab-candidates table colgroup col:nth-child(15){width:175px}
thead tr{background:var(--primary)}
th{padding:10px 10px;text-align:left;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#fff;white-space:nowrap;cursor:pointer;user-select:none;overflow:hidden;text-overflow:ellipsis}
th:hover{background:#2d5480}
th.sort-asc::after{content:" ↑";opacity:.7}
th.sort-desc::after{content:" ↓";opacity:.7}
td{padding:9px 12px;border-bottom:1px solid var(--border);vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:#f0f7ff}
.num{text-align:right;font-variant-numeric:tabular-nums}

/* ---- SIGNAL BADGES ---- */
.sig{display:inline-block;padding:2px 9px;border-radius:12px;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.04em;white-space:nowrap}
.sig-sb{background:#bbf7d0;color:#14532d}
.sig-buy{background:#dcfce7;color:#15803d}
.sig-hold{background:#fef3c7;color:#92400e}
.sig-wh{background:#ffedd5;color:#c2410c}
.sig-sell{background:#fee2e2;color:#991b1b}

/* ---- SUPERTREND BADGES ---- */
.stb{display:inline-block;padding:2px 8px;border-radius:12px;font-size:10px;font-weight:700;white-space:nowrap}
.st-bull{background:#dcfce7;color:#15803d}
.st-bear{background:#fee2e2;color:#991b1b}
.st-uk{background:#f1f5f9;color:#64748b}

/* ---- PATTERN BADGES ---- */
.pat{display:inline-block;padding:2px 8px;border-radius:12px;font-size:10px;font-weight:600;white-space:nowrap}
.pat-cb{background:#bbf7d0;color:#14532d;font-weight:800}
.pat-nr{background:#fef3c7;color:#92400e}
.pat-bb{background:#dbeafe;color:#1e40af}
.pat-tc{background:#f1f5f9;color:#475569}
.pat-ih{background:#f9fafb;color:#9ca3af}

/* ---- SCORE BARS ---- */
.sbar{display:flex;align-items:center;gap:6px;min-width:0}
.sv{font-weight:700;min-width:34px;text-align:right;font-size:12px}
.st2{flex:1;height:5px;background:#e2e8f0;border-radius:3px;overflow:hidden;min-width:40px}
.sf{height:100%;border-radius:3px}
.sf-invest{background:linear-gradient(90deg,#0f766e,#2dd4bf)}
.sf-tech{background:linear-gradient(90deg,#2563eb,#93c5fd)}
.sf-fund{background:linear-gradient(90deg,#7c3aed,#c4b5fd)}
.sf-rot{background:linear-gradient(90deg,#1e3a5f,#60a5fa)}

/* ---- RETURN COLORS ---- */
.rp{color:#15803d;font-weight:600}
.rn{color:#dc2626;font-weight:600}
.rz{color:var(--muted)}

/* ---- RSI COLORS ---- */
.rsi-h{color:#dc2626;font-weight:700}
.rsi-w{color:#ea580c;font-weight:600}
.rsi-n{color:#16a34a}
.rsi-c{color:#2563eb}

/* ---- VOLUME COLORS ---- */
.vh{color:#7c3aed;font-weight:700}
.vm{color:#2563eb;font-weight:600}
.vl{color:var(--muted)}

/* ---- DRAWDOWN COLORS ---- */
.dds{color:#15803d;font-weight:700}
.ddm{color:#d97706;font-weight:600}
.ddl{color:#dc2626;font-weight:600}

/* ---- ROTATION SCORE BAR (inline) ---- */
.rot-wrap{display:flex;align-items:center;gap:8px}
.rot-track{width:70px;height:6px;background:#e2e8f0;border-radius:3px;overflow:hidden;flex-shrink:0}
.rot-fill{height:100%;border-radius:3px;background:linear-gradient(90deg,#1e3a5f,#3b82f6)}
/* PG: macro tailwind badges (P1-6) */
.mtw-badge{display:inline-block;padding:2px 7px;border-radius:10px;font-size:11px;font-weight:600}
.mtw-pos{background:#dcfce7;color:#166534}.mtw-neg{background:#fee2e2;color:#991b1b}.mtw-neu{background:#f1f5f9;color:#64748b}
/* B3: seasonal signal badges */
.ssig{display:inline-block;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:600}
.ssig-tail{background:#dcfce7;color:#166534;border:1px solid #86efac}
.ssig-head{background:#fee2e2;color:#991b1b;border:1px solid #fca5a5}
.ssig-neu{background:#f1f5f9;color:#64748b}
/* C3: sector breadth badges */
.brd-badge{display:inline-block;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:600}
.brd-strong{background:#dcfce7;color:#166534;border:1px solid #86efac}
.brd-healthy{background:#d1fae5;color:#065f46;border:1px solid #6ee7b7}
.brd-neu{background:#f1f5f9;color:#475569}
.brd-weak{background:#fef9c3;color:#854d0e;border:1px solid #fde047}
.brd-bear{background:#fee2e2;color:#991b1b;border:1px solid #fca5a5}
.brd-nd{background:#f8fafc;color:#94a3b8}
.bdiv{display:inline-block;padding:1px 5px;border-radius:8px;font-size:9px;font-weight:700;margin-left:3px}
.bdiv-bull{background:#bbf7d0;color:#14532d}
.bdiv-bear{background:#fecaca;color:#7f1d1d}
.bdiv-int{background:#fef3c7;color:#78350f}

/* ---- ALL INDICES TAB (B3+) ---- */
.idx-filter-bar{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;align-items:center}
.idx-chip{padding:4px 12px;border-radius:14px;border:1px solid #e2e8f0;background:#f8fafc;font-size:11px;cursor:pointer;transition:background .15s,color .15s;white-space:nowrap}
.idx-chip:hover{background:#dbeafe;border-color:#93c5fd}
.idx-chip.active{background:#1e40af;color:#fff;border-color:#1e40af}
.idx-search{padding:6px 12px;border:1px solid #e2e8f0;border-radius:16px;font-size:12px;min-width:200px;outline:none;background:var(--card)}
.idx-search:focus{border-color:#3b82f6;box-shadow:0 0 0 3px rgba(59,130,246,.15)}

/* ---- SIGNALS POPUP (F&O + Insider + Events) ---- */
.signals-wrap{position:relative;display:inline-block}
.signals-btn{display:flex;align-items:center;gap:3px;cursor:pointer;padding:3px 8px;border-radius:12px;border:1px solid #e2e8f0;background:#f8fafc;font-size:10px;font-weight:600;white-space:nowrap;transition:background .15s}
.signals-btn:hover{background:#dbeafe;border-color:#93c5fd}
.signals-popup{display:none;position:absolute;top:calc(100% + 4px);left:0;z-index:200;background:#fff;border:1px solid #e2e8f0;border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,.12);padding:10px 12px;min-width:260px;max-width:320px}
.signals-wrap.sp-open .signals-popup{display:block}
.sdot{display:inline-block;width:7px;height:7px;border-radius:50%}
.sdot-bull{background:#16a34a}.sdot-bear{background:#dc2626}.sdot-neu{background:#94a3b8}.sdot-evt{background:#2563eb}.sdot-none{background:#e2e8f0}
.sbtn-lbl{font-size:10px;color:#475569;margin-left:2px}
.sp-row{display:flex;align-items:flex-start;gap:8px;padding:4px 0}
.sp-sep{border-top:1px solid #f1f5f9;margin-top:4px;padding-top:6px}
.sp-label{font-size:10px;font-weight:700;color:#64748b;min-width:52px;padding-top:2px}
.sp-val{font-size:11px;flex:1}
.sp-detail{font-size:9px;color:#64748b;margin-top:2px}
.sp-none{font-size:10px;color:#94a3b8;font-style:italic}

/* ---- SECTOR HEADINGS ---- */
.sec-hdr{display:flex;align-items:center;gap:12px;padding:14px 0 10px;border-bottom:2px solid var(--primary);margin-bottom:12px;margin-top:28px}
.sec-hdr:first-child{margin-top:0}
.sec-rank{width:28px;height:28px;border-radius:50%;background:var(--primary);color:#fff;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:800;flex-shrink:0}
.sec-name{font-size:16px;font-weight:800;color:var(--primary)}
.sec-meta{font-size:12px;color:var(--muted);margin-left:auto;display:flex;gap:10px;align-items:center;flex-wrap:wrap}

/* ---- NARRATIVE ---- */
details.narr{margin:8px 0}
details.narr summary{cursor:pointer;padding:7px 12px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;color:var(--primary);font-size:12px;font-weight:600;list-style:none;display:flex;align-items:center;gap:6px;transition:background .15s;white-space:normal;flex-wrap:wrap;max-width:100%;box-sizing:border-box}
details.narr summary:hover{background:#dbeafe}
details.narr summary::before{content:"▶";font-size:9px;transition:transform .2s;color:#2563eb}
details.narr[open] summary{border-bottom-left-radius:0;border-bottom-right-radius:0}
details.narr[open] summary::before{transform:rotate(90deg)}
.narr-body{padding:14px 16px;background:#f8faff;border:1px solid #bfdbfe;border-top:none;border-radius:0 0 6px 6px}
.narr-body p{font-size:13px;line-height:1.7;color:var(--text);margin-bottom:0}
.narr-section{margin-bottom:12px;padding-bottom:12px;border-bottom:1px solid #dbeafe}
.narr-section:last-child{margin-bottom:0;padding-bottom:0;border-bottom:none}
.narr-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#1e40af;margin-bottom:5px}
.click-detail summary{cursor:pointer;list-style:none;display:inline-block}
.click-detail summary::-webkit-details-marker{display:none}
.click-detail summary::after{content:"";display:inline-block;margin-left:4px;border-left:3px solid transparent;border-right:3px solid transparent;border-top:4px solid currentColor;opacity:.55;vertical-align:middle}
.click-detail[open] summary::after{transform:rotate(180deg)}
.click-detail-body{margin-top:4px;font-size:9px;color:#64748b;line-height:1.35;max-width:180px;white-space:normal;overflow-wrap:anywhere}

/* ---- SECTOR NARRATIVE CARD ---- */
.sec-narr-card{background:#f0fdf9;border:1px solid #99f6e4;border-radius:var(--radius);padding:16px;margin-bottom:16px}
.sec-narr-hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;flex-wrap:wrap;gap:8px}
.sec-narr-title{font-size:13px;font-weight:700;color:#0f766e}
.conviction{padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700}
.conv-HIGH{background:#bbf7d0;color:#14532d}
.conv-MEDIUM{background:#fef3c7;color:#92400e}
.conv-LOW{background:#fee2e2;color:#991b1b}
.themes{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.theme-chip{display:inline-block;background:#eff6ff;color:#1e40af;border:1px solid #bfdbfe;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:500}
.sec-narr-card p{font-size:13px;line-height:1.7;color:var(--text);margin-bottom:8px}
.sec-narr-card p:last-child{margin-bottom:0}

/* ---- SECTOR PILLS (horizontal slide-track) ---- */
.pills-nav{position:relative;display:flex;align-items:center;gap:0;margin-bottom:16px;background:var(--card);border:1px solid var(--border);border-radius:24px;padding:4px;box-shadow:var(--shadow)}
.pills-arrow{flex-shrink:0;background:none;border:none;cursor:pointer;color:var(--muted);padding:4px 8px;font-size:16px;line-height:1;border-radius:20px;transition:all .15s;display:flex;align-items:center}
.pills-arrow:hover{background:var(--border);color:var(--text)}
.pills-arrow:disabled{opacity:0.25;cursor:default}
.sec-pills{display:flex;gap:6px;flex-wrap:nowrap;overflow-x:auto;scroll-behavior:smooth;-webkit-overflow-scrolling:touch;padding:2px 4px;flex:1;scrollbar-width:none;-ms-overflow-style:none}
.sec-pills::-webkit-scrollbar{display:none}
.sec-pill{flex-shrink:0;background:transparent;border:1.5px solid transparent;color:var(--muted);padding:4px 14px;border-radius:20px;font-size:12px;font-weight:600;cursor:pointer;transition:all .18s;white-space:nowrap}
.sec-pill:hover{background:var(--bg);border-color:var(--border);color:var(--text)}
.sec-pill.active{background:var(--primary);border-color:var(--primary);color:#fff;box-shadow:0 2px 6px rgba(30,58,95,.3)}
/* ---- SECTOR BLOCK SLIDE ANIMATION ---- */
.sblock-area{overflow:visible}
[data-sblock]{animation:none;transition:opacity .22s,transform .22s}
[data-sblock].sblock-enter{animation:sblock-in .25s ease both}
@keyframes sblock-in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}

/* ---- SETUP CLASS BADGES ---- */
.setup{display:inline-block;padding:2px 7px;border-radius:10px;font-size:9.5px;font-weight:700;white-space:nowrap;margin-top:3px}
.setup-lb{background:#fef08a;color:#713f12;border:1px solid #fde047}
.setup-fr{background:#bbf7d0;color:#14532d}
.setup-bnh{background:#dbeafe;color:#1e40af}
.setup-pu{background:#e0e7ff;color:#3730a3}
.setup-me{background:#ffedd5;color:#c2410c}
.setup-wt{background:#fee2e2;color:#991b1b}
.setup-n{background:#f1f5f9;color:#64748b}
.action{display:inline-block;padding:2px 7px;border-radius:10px;font-size:9.5px;font-weight:800;white-space:nowrap;margin-top:3px;text-transform:uppercase;letter-spacing:0}
.act-buy{background:#dcfce7;color:#166534;border:1px solid #86efac}
.act-brk{background:#e0f2fe;color:#075985;border:1px solid #7dd3fc}
.act-hold{background:#ecfdf5;color:#047857}
.act-wait{background:#fef3c7;color:#92400e}
.act-avoid{background:#fee2e2;color:#991b1b;border:1px solid #fca5a5}
.act-watch{background:#f1f5f9;color:#475569}

/* ---- KEY LEVELS ---- */
.levels{font-size:11px;line-height:1.8;display:flex;flex-wrap:wrap;gap:4px 8px}
.levels-sub{font-size:10px;color:#64748b;line-height:1.6}
.lev-entry{font-weight:700;color:#1e40af}
.lev-stop{font-weight:700;color:#dc2626}
.lev-tgt{font-weight:700;color:#15803d}
.lev-tgt2{font-weight:600;color:#059669}
.lev-r{color:#dc2626}
.lev-s{color:#15803d}

/* ---- F&O SIGNAL BADGES (P1-2) ---- */
.fno{display:inline-block;padding:2px 7px;border-radius:10px;font-size:9.5px;font-weight:700;white-space:nowrap}
.fno-bull{background:#dcfce7;color:#15803d;border:1px solid #86efac}
.fno-mbull{background:#fef9c3;color:#854d0e}
.fno-neutral{background:#f1f5f9;color:#64748b}
.fno-mbear{background:#ffedd5;color:#c2410c}
.fno-bear{background:#fee2e2;color:#991b1b;border:1px solid #fca5a5}
.fno-na{color:#cbd5e1;font-size:9px}
.fno-detail{font-size:9px;color:#64748b;margin-top:2px;line-height:1.3}

/* ---- FII/DII FLOW BANNER (P1-3) ---- */
.flow-banner{display:flex;align-items:center;gap:12px;padding:8px 14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:10px;flex-wrap:wrap}
.flow-badge{display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;white-space:nowrap}
.flow-bull{background:#dcfce7;color:#15803d;border:1px solid #86efac}
.flow-caution{background:#fef9c3;color:#854d0e;border:1px solid #fde047}
.flow-bear{background:#fee2e2;color:#991b1b;border:1px solid #fca5a5}
.flow-neutral{background:#f1f5f9;color:#64748b}
.flow-na{background:#f1f5f9;color:#94a3b8}
.flow-detail{font-size:11px;color:#475569}
.flow-today{font-size:10px;color:#94a3b8;margin-left:auto}
.breadth-strip{display:flex;align-items:center;gap:10px;padding:8px 14px;background:#eef6ff;border:1px solid #bfdbfe;border-radius:8px;margin-bottom:10px;flex-wrap:wrap;font-size:11px;color:#334155}
.breadth-kicker{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.06em;color:#1e40af}
.breadth-context{font-weight:800;color:#1e3a5f}

/* ---- INSIDER/PROMOTER ALERT BADGES (P1-4) ---- */
.ins{display:inline-block;padding:2px 7px;border-radius:10px;font-size:9.5px;font-weight:700;white-space:nowrap}
.ins-bull{background:#dcfce7;color:#15803d;border:1px solid #86efac}
.ins-info{background:#dbeafe;color:#1e40af;border:1px solid #93c5fd}
.ins-bear{background:#fee2e2;color:#991b1b;border:1px solid #fca5a5}
.ins-warn{background:#ffedd5;color:#c2410c;border:1px solid #fdba74}
.ins-neutral{background:#f1f5f9;color:#64748b}
.ins-na{color:#cbd5e1;font-size:9px}
.ins-detail{font-size:9px;color:#64748b;margin-top:2px;line-height:1.3;max-width:180px;overflow:hidden;text-overflow:ellipsis}

/* ---- CORPORATE EVENT BADGES (E4) ---- */
.evt{display:inline-block;padding:2px 7px;border-radius:10px;font-size:9.5px;font-weight:700;white-space:nowrap}
.evt-result-urgent{background:#fee2e2;color:#991b1b;border:1px solid #fca5a5;animation:pulse-red 1.2s infinite}
.evt-result-soon{background:#ffedd5;color:#c2410c;border:1px solid #fdba74}
.evt-result{background:#dbeafe;color:#1e40af;border:1px solid #93c5fd}
.evt-buyback{background:#dcfce7;color:#15803d;border:1px solid #86efac}
.evt-bonus{background:#fef9c3;color:#854d0e;border:1px solid #fde047}
.evt-split{background:#f3e8ff;color:#6b21a8;border:1px solid #d8b4fe}
.evt-dividend{background:#e0f2fe;color:#0369a1;border:1px solid #7dd3fc}
.evt-other{background:#f1f5f9;color:#475569;border:1px solid #cbd5e1}
.evt-na{color:#cbd5e1;font-size:9px}
.evt-detail{font-size:9px;color:#64748b;margin-top:2px;line-height:1.3;max-width:180px;overflow:hidden;text-overflow:ellipsis}
@keyframes pulse-red{0%,100%{opacity:1}50%{opacity:.55}}

/* ---- A1 STAGE ANALYSIS BADGES ---- */
.stage-badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;white-space:nowrap}
.s2-badge{background:#dcfce7;color:#166534;border:1px solid #86efac}
.s1-badge{background:#fef9c3;color:#854d0e;border:1px solid #fde047}
.s3-badge{background:#ffedd5;color:#c2410c;border:1px solid #fdba74}
.s4-badge{background:#fee2e2;color:#991b1b;border:1px solid #fca5a5}
.su-badge{background:#f1f5f9;color:#94a3b8}
.stage-summary{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.stage-card{padding:12px 16px;border-radius:8px;min-width:110px;text-align:center}
.stage-card .sc-count{font-size:24px;font-weight:800}
.stage-card .sc-label{font-size:11px;font-weight:600;margin-top:2px}
.stage-card.s2{background:#dcfce7;color:#166534}.stage-card.s1{background:#fef9c3;color:#854d0e}
.stage-card.s3{background:#ffedd5;color:#c2410c}.stage-card.s4{background:#fee2e2;color:#991b1b}
.stage-card.su{background:#f1f5f9;color:#64748b}

/* ---- DASHBOARD TOOLBAR (P1-5) ---- */
.dash-toolbar{display:flex;align-items:center;gap:8px;padding:8px 0;margin-bottom:8px;flex-wrap:wrap}
.dash-search{flex:1;min-width:180px;max-width:320px;padding:7px 12px 7px 32px;border:1px solid var(--border);border-radius:20px;font-size:12px;color:var(--text);background:var(--card) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' fill='%2394a3b8' viewBox='0 0 24 24'%3E%3Cpath d='M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z'/%3E%3C/svg%3E") no-repeat 10px center;transition:border-color .15s,box-shadow .15s}
.dash-search:focus{outline:none;border-color:#3b82f6;box-shadow:0 0 0 3px rgba(59,130,246,.15)}
.dash-search::placeholder{color:#94a3b8}
.dash-btn{padding:6px 14px;border:1px solid var(--border);border-radius:20px;font-size:11px;font-weight:600;cursor:pointer;background:var(--card);color:var(--text);transition:all .15s;white-space:nowrap}
.dash-btn:hover{background:var(--primary);color:#fff;border-color:var(--primary)}
.dash-btn.active{background:var(--primary);color:#fff;border-color:var(--primary)}
.dash-count{font-size:11px;color:var(--muted);margin-left:auto}

/* ---- HEATMAP VIEW (P1-5) ---- */
.hm-grid{display:grid;grid-template-columns:repeat(10,1fr);gap:4px;padding:8px}
.hm-cell{padding:8px 4px;border-radius:6px;text-align:center;font-size:10px;font-weight:700;color:#fff;cursor:default;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;transition:transform .12s;line-height:1.3}
.hm-cell:hover{transform:scale(1.08);z-index:2;box-shadow:0 3px 12px rgba(0,0,0,.25)}
.hm-score{display:block;font-size:8px;font-weight:400;opacity:.85;margin-top:1px}
.hm-wrap{display:none;background:var(--card);border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow);margin-bottom:16px;padding:4px}
.hm-wrap.hm-active{display:block}
.sblock-area.hm-hidden>*{display:none}

/* ---- RESILIENCE GAUGE ---- */
.dd-bar-wrap{display:flex;align-items:center;gap:6px}
.dd-bar-outer{width:60px;height:6px;background:#e2e8f0;border-radius:3px;overflow:hidden}
.dd-bar-inner{height:100%;border-radius:3px}

/* ---- METHODOLOGY CARDS ---- */
.meth-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}
.meth-card{background:var(--card);border-radius:var(--radius);border:1px solid var(--border);padding:18px;box-shadow:var(--shadow)}
.meth-card-title{font-size:13px;font-weight:700;color:var(--primary);margin-bottom:8px;display:flex;align-items:center;gap:8px}
.meth-icon{width:28px;height:28px;border-radius:6px;background:var(--primary);color:#fff;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;flex-shrink:0}
.meth-card p{font-size:13px;line-height:1.6;color:var(--muted)}
.meth-section-hdr{font-size:14px;font-weight:800;color:var(--primary);letter-spacing:.04em;text-transform:uppercase;margin:28px 0 12px;padding-bottom:6px;border-bottom:2px solid var(--primary);grid-column:1/-1}
.meth-heat-legend{display:flex;gap:4px;flex-wrap:wrap;align-items:center;margin-top:10px}
.meth-heat-swatch{display:inline-flex;align-items:center;gap:4px;font-size:10px;font-weight:600;padding:2px 7px;border-radius:4px}
.meth-signal-row{display:flex;align-items:center;gap:6px;font-size:12px;margin:4px 0;color:var(--muted)}
.meth-dot{display:inline-block;width:9px;height:9px;border-radius:50%;flex-shrink:0}
.formula{background:#f8fafc;border:1px solid var(--border);border-radius:6px;padding:10px 14px;font-size:12px;font-family:monospace;margin-top:10px;color:var(--primary)}
.legal-disclaimer{background:#fff;border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow);padding:22px;margin-top:16px}
.legal-disclaimer h2{font-size:18px;color:var(--primary);margin-bottom:10px}
.legal-disclaimer p{font-size:13px;line-height:1.75;color:var(--text);margin-bottom:10px}
.legal-disclaimer .legal-alert{font-weight:800;color:#991b1b;background:#fef2f2;border:1px solid #fecaca;border-radius:6px;padding:10px 12px}

/* ---- RANK BADGE ---- */
.rank-num{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;background:var(--primary);color:#fff;border-radius:50%;font-size:11px;font-weight:700}

/* ---- SECTION TITLE ---- */
.sec-title{font-size:15px;font-weight:800;color:var(--primary);margin-bottom:4px}
.sec-sub{font-size:12px;color:var(--muted);margin-bottom:16px}

/* ---- PRINT (P1-5 enhanced) ---- */
@media print{
  .main-nav,.pills-nav,.dash-toolbar,.disc,.hm-wrap,.pills-arrow{display:none!important}
  .print-page-header{display:flex!important;position:fixed;top:0;left:0;right:0;height:11mm;align-items:center;justify-content:space-between;border-bottom:1px solid #cbd5e1;background:#fff;color:#1e3a5f;font-size:9px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;padding:0 7mm;z-index:9999;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .print-page-footer{display:block!important;position:fixed;bottom:0;left:0;right:0;min-height:12mm;border-top:1px solid #cbd5e1;background:#fff;color:#475569;font-size:7.5px;line-height:1.25;padding:2mm 7mm;z-index:9999;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .tab-pane{display:block!important;opacity:1!important}
  .site-hdr{position:static!important;height:auto!important;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .hdr-inner{height:auto!important;display:block!important;padding:8px 12px!important}
  .hdr-brand{display:flex!important}
  .brand-logo{width:30px!important;height:30px!important}
  .hdr-kicker{white-space:normal!important}
  .hdr-title{white-space:normal!important;margin-bottom:4px}
  .hdr-meta{display:block!important}
  .chart-wrap{display:none!important}
  @page{margin:18mm 7mm 20mm}
  .content{max-width:none!important;padding:8px 0!important}
  body{background:#fff;font-size:10px;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .tbl-wrap{box-shadow:none;border:1px solid #ccc;overflow:visible}
  table{font-size:9px;table-layout:auto!important}
  thead tr{background:#1e3a5f!important;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  th{white-space:normal!important;overflow:visible!important;text-overflow:clip!important;padding:6px 5px!important;font-size:8px!important;line-height:1.2}
  td{padding:5px 5px!important;line-height:1.25}
  #tab-candidates table{min-width:0!important;width:100%!important}
  #tab-candidates table colgroup{display:none}
  .card,.sec-narr-card{break-inside:avoid}
  .narr-body{break-inside:avoid}
  [data-sblock]{page-break-inside:avoid}
  .legal-disclaimer{break-before:page;page-break-before:always;box-shadow:none;border:1px solid #cbd5e1}
}
@media(max-width:768px){
  .content{padding:12px}
  .metrics-row{gap:8px}
  .metric-card{min-width:140px}
  .hdr-title{font-size:.9rem}
}
@media(max-width:900px){
  #tab-candidates table{min-width:800px}
  #tab-candidates table colgroup col:nth-child(1){width:105px}
  #tab-candidates table colgroup col:nth-child(3){width:84px}
  #tab-candidates table colgroup col:nth-child(4){width:140px}
  #tab-candidates table colgroup col:nth-child(8){width:65px}
  #tab-candidates table colgroup col:nth-child(9){width:58px}
  #tab-candidates table colgroup col:nth-child(10){width:92px}
  #tab-candidates table colgroup col:nth-child(14){width:80px}
  #tab-candidates table colgroup col:nth-child(15){width:175px}
  #tab-candidates table colgroup col:nth-child(2),
  #tab-candidates table colgroup col:nth-child(5),
  #tab-candidates table colgroup col:nth-child(6),
  #tab-candidates table colgroup col:nth-child(7),
  #tab-candidates table colgroup col:nth-child(11),
  #tab-candidates table colgroup col:nth-child(12),
  #tab-candidates table colgroup col:nth-child(13),
  #tab-candidates th:nth-child(2),
  #tab-candidates th:nth-child(5),
  #tab-candidates th:nth-child(6),
  #tab-candidates th:nth-child(7),
  #tab-candidates th:nth-child(11),
  #tab-candidates th:nth-child(12),
  #tab-candidates th:nth-child(13),
  #tab-candidates td:nth-child(2),
  #tab-candidates td:nth-child(5),
  #tab-candidates td:nth-child(6),
  #tab-candidates td:nth-child(7),
  #tab-candidates td:nth-child(11),
  #tab-candidates td:nth-child(12),
  #tab-candidates td:nth-child(13){display:none}
  #tab-candidates th,#tab-candidates td{padding:8px 10px}
  #tab-candidates .sig,
  #tab-candidates .setup,
  #tab-candidates .action{font-size:9px;padding:2px 7px}
  #tab-candidates .levels{display:block;line-height:1.55}
  #tab-candidates .levels span{display:block;margin-bottom:2px}
  #tab-candidates .levels-sub{display:none}
}
"""

_JS = r"""
(function(){
  var _ls=function(k,v){try{if(v===undefined)return localStorage.getItem(k);localStorage.setItem(k,v);}catch(e){return null;}};

  // Tab switching (P1-5: persists active tab via localStorage)
  function showTab(id){
    document.querySelectorAll('.tab-pane').forEach(p=>p.classList.toggle('active',p.id==='tab-'+id));
    document.querySelectorAll('.nav-btn').forEach(b=>b.classList.toggle('active',b.dataset.tab===id));
    history.replaceState(null,'','#'+id);
    _ls('nse_tab',id);
  }
  document.querySelectorAll('.nav-btn').forEach(b=>b.addEventListener('click',()=>showTab(b.dataset.tab)));

  // Table sorting (P1-5: paired-row aware for candidates tab, persists sort state)
  document.querySelectorAll('table').forEach(function(table){
    var ths=table.querySelectorAll('th');
    var isCand=!!table.closest('#tab-candidates');
    ths.forEach(function(th,idx){
      th.addEventListener('click',function(){
        var tbody=table.querySelector('tbody');
        if(!tbody)return;
        var allRows=Array.from(tbody.querySelectorAll('tr'));
        var asc=th.dataset.sort!=='asc';
        if(isCand){
          var pairs=[];
          for(var i=0;i<allRows.length;i+=2) pairs.push([allRows[i],allRows[i+1]]);
          pairs.sort(function(a,b){
            var av=(a[0].cells[idx]&&(a[0].cells[idx].dataset.val||a[0].cells[idx].textContent.trim()))||'';
            var bv=(b[0].cells[idx]&&(b[0].cells[idx].dataset.val||b[0].cells[idx].textContent.trim()))||'';
            var an=parseFloat(av.replace(/[^0-9.\-]/g,'')),bn=parseFloat(bv.replace(/[^0-9.\-]/g,''));
            if(!isNaN(an)&&!isNaN(bn))return asc?an-bn:bn-an;
            return asc?av.localeCompare(bv):bv.localeCompare(av);
          });
          pairs.forEach(function(p){p.forEach(function(r){if(r)tbody.appendChild(r);});});
        } else {
          allRows.sort(function(a,b){
            var av=(a.cells[idx]&&(a.cells[idx].dataset.val||a.cells[idx].textContent.trim()))||'';
            var bv=(b.cells[idx]&&(b.cells[idx].dataset.val||b.cells[idx].textContent.trim()))||'';
            var an=parseFloat(av.replace(/[^0-9.\-]/g,'')),bn=parseFloat(bv.replace(/[^0-9.\-]/g,''));
            if(!isNaN(an)&&!isNaN(bn))return asc?an-bn:bn-an;
            return asc?av.localeCompare(bv):bv.localeCompare(av);
          });
          allRows.forEach(r=>tbody.appendChild(r));
        }
        ths.forEach(t=>{delete t.dataset.sort;t.classList.remove('sort-asc','sort-desc');});
        th.dataset.sort=asc?'asc':'desc';
        th.classList.add(asc?'sort-asc':'sort-desc');
      });
    });
  });

  // Sector filter pills — slide-track with arrow nav (P1-5: persists selected sector)
  var pillsTrack=document.querySelector('.sec-pills');
  var arrowL=document.querySelector('.pills-arrow-l');
  var arrowR=document.querySelector('.pills-arrow-r');
  function updateArrows(){
    if(!pillsTrack||!arrowL||!arrowR)return;
    arrowL.disabled=pillsTrack.scrollLeft<=2;
    arrowR.disabled=pillsTrack.scrollLeft>=pillsTrack.scrollWidth-pillsTrack.clientWidth-2;
  }
  if(pillsTrack){pillsTrack.addEventListener('scroll',updateArrows);updateArrows();}
  if(arrowL){arrowL.addEventListener('click',function(){pillsTrack.scrollBy({left:-200,behavior:'smooth'});});}
  if(arrowR){arrowR.addEventListener('click',function(){pillsTrack.scrollBy({left:200,behavior:'smooth'});});}

  function selectSector(sec,activePill){
    document.querySelectorAll('[data-spill]').forEach(p=>p.classList.toggle('active',p===activePill));
    document.querySelectorAll('[data-sblock]').forEach(function(block){
      var show=(!sec||block.dataset.sblock===sec);
      if(show){
        block.style.display='';
        block.classList.remove('sblock-enter');
        void block.offsetWidth;
        block.classList.add('sblock-enter');
      } else {
        block.style.display='none';
      }
    });
    document.querySelectorAll('.hm-cell').forEach(function(cell){
      cell.style.display=(!sec||cell.dataset.sector===sec)?'':'none';
    });
    if(activePill) activePill.scrollIntoView({behavior:'smooth',block:'nearest',inline:'center'});
    updateArrows();
    _ls('nse_sector',sec);
  }
  document.querySelectorAll('[data-spill]').forEach(function(pill){
    pill.addEventListener('click',function(){selectSector(pill.dataset.spill,pill);});
  });

  // Narrative search filter (P1-5)
  var searchInput=document.getElementById('narrSearch');
  var matchCount=document.getElementById('matchCount');
  if(searchInput){
    var _debounce;
    searchInput.addEventListener('input',function(){
      clearTimeout(_debounce);
      _debounce=setTimeout(function(){
        var q=searchInput.value.trim().toLowerCase();
        _ls('nse_search',q);
        var shown=0,total=0;
        document.querySelectorAll('#tab-candidates [data-sblock] tbody').forEach(function(tbody){
          var rows=Array.from(tbody.querySelectorAll('tr'));
          for(var i=0;i<rows.length;i+=2){
            total++;
            var dr=rows[i],nr=rows[i+1];
            if(!q){dr.style.display='';if(nr)nr.style.display='';shown++;continue;}
            var txt=(dr.textContent+' '+(nr?nr.textContent:'')).toLowerCase();
            var match=txt.indexOf(q)>=0;
            dr.style.display=match?'':'none';
            if(nr)nr.style.display=match?'':'none';
            if(match)shown++;
          }
        });
        if(matchCount) matchCount.textContent=q?(shown+' / '+total+' stocks'):(total+' stocks');
      },200);
    });
  }

  // Heatmap toggle (P1-5)
  var hmBtn=document.getElementById('hmToggle');
  if(hmBtn){
    hmBtn.addEventListener('click',function(){
      var sba=document.querySelector('.sblock-area');
      var hmw=document.querySelector('.hm-wrap');
      if(!sba||!hmw)return;
      var active=hmw.classList.toggle('hm-active');
      sba.classList.toggle('hm-hidden',active);
      hmBtn.classList.toggle('active',active);
      hmBtn.textContent=active?'Table View':'Heatmap';
      _ls('nse_heatmap',active?'1':'0');
    });
  }

  // Print button (P1-5)
  var printBtn=document.getElementById('printReport');
  if(printBtn){printBtn.addEventListener('click',function(){window.print();});}

  // Rotation chart
  if(typeof Chart!=='undefined'&&document.getElementById('rotChart')){
    var ctx=document.getElementById('rotChart').getContext('2d');
    var scores=window._rotScores||[];
    var colors=scores.map(function(s){return s>10?'#1e3a5f':s>5?'#2563eb':'#93c5fd';});
    new Chart(ctx,{
      type:'bar',
      data:{
        labels:window._rotLabels||[],
        datasets:[{
          label:'Rotation Score',
          data:scores,
          backgroundColor:colors,
          borderRadius:4,
          borderSkipped:false
        }]
      },
      options:{
        indexAxis:'y',
        responsive:true,
        maintainAspectRatio:false,
        plugins:{
          legend:{display:false},
          tooltip:{callbacks:{label:function(c){return' Score: '+c.parsed.x.toFixed(1);}}}
        },
        scales:{
          x:{grid:{color:'#e2e8f0'},title:{display:true,text:'Rotation Score',color:'#64748b',font:{size:11}}},
          y:{grid:{display:false},ticks:{color:'#1a2332',font:{size:12,weight:'600'}}}
        }
      }
    });
  }

  // Restore persisted state on load (P1-5)
  var savedTab=_ls('nse_tab')||location.hash.slice(1)||'overview';
  showTab(savedTab);
  var savedSec=_ls('nse_sector');
  if(savedSec){var pill=document.querySelector('[data-spill="'+savedSec+'"]');if(pill)selectSector(savedSec,pill);}
  var savedSearch=_ls('nse_search');
  if(savedSearch&&searchInput){searchInput.value=savedSearch;searchInput.dispatchEvent(new Event('input'));}
  var savedHm=_ls('nse_heatmap');
  if(savedHm==='1'&&hmBtn){hmBtn.click();}
  // Signals popup open/close
  window.toggleSignals=function(btn,ev){
    if(ev)ev.stopPropagation();
    var wrap=btn.closest('.signals-wrap');
    var wasOpen=wrap.classList.contains('sp-open');
    document.querySelectorAll('.signals-wrap.sp-open').forEach(function(w){w.classList.remove('sp-open');});
    if(!wasOpen)wrap.classList.add('sp-open');
  };
  document.addEventListener('click',function(){
    document.querySelectorAll('.signals-wrap.sp-open').forEach(function(w){w.classList.remove('sp-open');});
  });
})();
"""


_CAT_COLORS: dict[str, tuple[str, str]] = {
    "Sector":           ("#dbeafe", "#1e40af"),
    "Broad Market":     ("#dcfce7", "#166534"),
    "Thematic":         ("#f3e8ff", "#6b21a8"),
    "Strategy / Factor":("#fef9c3", "#854d0e"),
    "Size":             ("#ffedd5", "#c2410c"),
    "Fixed Income":     ("#e0f2fe", "#0369a1"),
    "Other":            ("#f1f5f9", "#475569"),
}


def build_indices_tab_html(all_metrics: pd.DataFrame | None) -> str:
    if all_metrics is None or all_metrics.empty:
        return '<div class="card"><p>Index data not available.</p></div>'

    categories = ["All"] + sorted(all_metrics["CATEGORY"].unique().tolist())
    chip_html = ""
    for cat in categories:
        active = ' class="idx-chip active"' if cat == "All" else ' class="idx-chip"'
        chip_html += f'<button{active} data-idxcat="{html_mod.escape(cat)}">{html_mod.escape(cat)}</button>'

    rows_html = ""
    for _, row in all_metrics.iterrows():
        sym = str(row.get("SYMBOL", ""))
        cat = str(row.get("CATEGORY", "Other"))
        cat_bg, cat_fg = _CAT_COLORS.get(cat, ("#f1f5f9", "#475569"))
        cat_badge = (
            f'<span style="display:inline-block;padding:2px 7px;border-radius:10px;'
            f'font-size:9px;font-weight:600;background:{cat_bg};color:{cat_fg}">'
            f'{html_mod.escape(cat)}</span>'
        )
        close_v = _fmth(row.get("CLOSE"), digits=2)
        r5d = _ret_cell(row.get("RET_5D"))
        r1m = _ret_cell(row.get("RET_1M"))
        r3m = _ret_cell(row.get("RET_3M"))
        r6m = _ret_cell(row.get("RET_6M"))
        rs1m = _ret_cell(row.get("RS_1M"))
        score_raw = float(row.get("ROTATION_SCORE", 0) or 0)
        score_cls = "ret-pos" if score_raw > 0 else ("ret-neg" if score_raw < 0 else "ret-neu")
        score_html = f'<span class="{score_cls}">{score_raw:+.1f}</span>'
        h52 = _fmth(row.get("HI_52_WK"), digits=2)
        l52 = _fmth(row.get("LO_52_WK"), digits=2)
        dd = row.get("DD_FROM_52W_HIGH")
        dd_html = _dd_cell(dd)
        rows_html += (
            f'<tr data-idxcat="{html_mod.escape(cat)}" data-idxsym="{html_mod.escape(sym.lower())}">'
            f'<td><strong>{html_mod.escape(sym)}</strong></td>'
            f'<td>{cat_badge}</td>'
            f'<td class="num" data-val="{_fmth(row.get("CLOSE"), digits=2)}">{close_v}</td>'
            f'<td class="num" data-val="{_fmth(row.get("RET_5D"))}">{r5d}</td>'
            f'<td class="num" data-val="{_fmth(row.get("RET_1M"))}">{r1m}</td>'
            f'<td class="num" data-val="{_fmth(row.get("RET_3M"))}">{r3m}</td>'
            f'<td class="num" data-val="{_fmth(row.get("RET_6M"))}">{r6m}</td>'
            f'<td class="num" data-val="{_fmth(row.get("RS_1M"))}">{rs1m}</td>'
            f'<td class="num" data-val="{score_raw:.2f}">{score_html}</td>'
            f'<td class="num" data-val="{_fmth(row.get("HI_52_WK"), digits=2)}">{h52}</td>'
            f'<td class="num" data-val="{_fmth(row.get("LO_52_WK"), digits=2)}">{l52}</td>'
            f'<td class="num" data-val="{_fmth(dd)}">{dd_html}</td>'
            f'</tr>'
        )

    idx_js = """
<script>
(function(){
  var chips=document.querySelectorAll('.idx-chip');
  var idxSearch=document.getElementById('idxSearch');
  function filterIdx(){
    var activeCat='';
    chips.forEach(function(c){if(c.classList.contains('active'))activeCat=c.dataset.idxcat;});
    var q=(idxSearch?idxSearch.value.toLowerCase().trim():'');
    document.querySelectorAll('#idxTbody tr').forEach(function(r){
      var catMatch=(activeCat==='All'||r.dataset.idxcat===activeCat);
      var symMatch=(!q||r.dataset.idxsym.indexOf(q)>=0);
      r.style.display=(catMatch&&symMatch)?'':'none';
    });
    var vis=document.querySelectorAll('#idxTbody tr:not([style*="none"])').length;
    var el=document.getElementById('idxCount');
    if(el)el.textContent=vis+' indices';
  }
  chips.forEach(function(c){
    c.addEventListener('click',function(){
      chips.forEach(function(x){x.classList.remove('active');});
      c.classList.add('active');
      filterIdx();
    });
  });
  if(idxSearch)idxSearch.addEventListener('input',filterIdx);
})();
</script>"""

    table_html = (
        f'<div class="tbl-wrap"><table>'
        f'<thead><tr>'
        f'<th>Index</th><th>Category</th><th class="num">Close</th>'
        f'<th class="num">5D</th><th class="num">1M</th><th class="num">3M</th><th class="num">6M</th>'
        f'<th class="num">RS 1M</th><th class="num">Score</th>'
        f'<th class="num">52W High</th><th class="num">52W Low</th><th class="num">DD%</th>'
        f'</tr></thead>'
        f'<tbody id="idxTbody">{rows_html}</tbody>'
        f'</table></div>'
    )

    n_total = len(all_metrics)
    return (
        f'<div class="sec-title">All NSE Indices</div>'
        f'<div class="sec-sub">Performance and range data for all {n_total} tracked indices. '
        f'RS 1M and Score are relative to Nifty 500 benchmark.</div>'
        f'<div class="idx-filter-bar">'
        f'{chip_html}'
        f'<input type="text" id="idxSearch" class="idx-search" placeholder="Search index name…" autocomplete="off">'
        f'<span id="idxCount" style="font-size:11px;color:#64748b;margin-left:4px">{n_total} indices</span>'
        f'</div>'
        + table_html
        + idx_js
    )


def render_html_interactive(
    sector_rank: pd.DataFrame,
    candidates: pd.DataFrame,
    peak_resilience: pd.DataFrame,
    source_file: Path,
    generated_at: datetime,
    narratives: dict,
    regime_info: dict | None = None,
    flow_info: dict | None = None,
    cycle_info: dict | None = None,
    macro_context: str = "",
    seasonal_calendar_html: str = "",
    all_index_metrics: pd.DataFrame | None = None,
) -> str:
    gen_date = generated_at.strftime("%Y-%m-%d")
    data_date = (
        candidates["ANALYSIS_DATE"].dropna().iloc[0]
        if "ANALYSIS_DATE" in candidates.columns and candidates["ANALYSIS_DATE"].notna().any()
        else gen_date
    )
    # Build regime banner HTML
    _regime_banner = ""
    if regime_info:
        try:
            from regime_detector import regime_badge_html as _rbh
            _regime_banner = _rbh(regime_info)
        except Exception:
            pass
    _cycle_banner = ""
    if cycle_info:
        try:
            from economic_cycle import cycle_badge_html as _cbh
            _cycle_banner = _cbh(cycle_info)
        except Exception:
            pass

    # Build FII/DII flow banner HTML (P1-3)
    _flow_banner = ""
    if flow_info and flow_info.get("flow_signal") not in (None, "NO_DATA"):
        try:
            from fetch_fii_dii_flows import flow_badge_html as _fbh
            _flow_banner = _fbh(flow_info)
        except Exception:
            pass

    # Build cross-index breadth context strip (B1)
    _breadth_strip = ""
    try:
        breadth_csv = ROOT / "reports" / "latest" / "index_intelligence.csv"
        if breadth_csv.exists():
            from index_intelligence import breadth_context_html
            _breadth_strip = breadth_context_html(pd.read_csv(breadth_csv))
    except Exception:
        pass

    # Build McClellan breadth context strip (C1)
    _mcclellan_strip = ""
    try:
        from market_breadth import load_breadth_history, mcclellan_context_html
        _mcclellan_strip = mcclellan_context_html(load_breadth_history())
    except Exception:
        pass

    sec_narratives = narratives.get("sectors", {})
    stk_narratives = narratives.get("stocks", {})
    market_summary = narratives.get("market_summary", "")
    market_brief = narratives.get("market_brief", {})
    logo_uri = _asset_data_uri(AGENT_LOGO_PATH)
    logo_html = (
        f'<img class="brand-logo" src="{logo_uri}" alt="Agent adda logo">'
        if logo_uri else ""
    )

    brief_html = ""
    if isinstance(market_brief, dict) and market_brief:
        brief_items = [
            ("Market Read", market_brief.get("market_read", "")),
            ("Risk Posture", market_brief.get("risk_posture", "")),
            ("Where to Focus", market_brief.get("where_to_focus", "")),
            ("What Would Change", market_brief.get("what_would_change_the_view", "")),
        ]
        brief_blocks = "".join(
            f'<div class="brief-block"><div class="brief-label">{html_mod.escape(label)}</div>'
            f'<div class="brief-text">{html_mod.escape(str(text))}</div></div>'
            for label, text in brief_items if str(text).strip()
        )
        if brief_blocks:
            brief_html = (
                '<div class="content" style="padding-top:0;padding-bottom:0">'
                '<div class="brief-card"><div class="brief-title">Market Brief</div>'
                f'<div class="brief-grid">{brief_blocks}</div></div></div>'
            )

    # ---- BUILD OVERVIEW TAB ----
    buy_stocks = candidates[candidates.get("TRADING_SIGNAL", pd.Series([], dtype=str)).isin(["BUY", "STRONG_BUY"])] \
        if "TRADING_SIGNAL" in candidates.columns else pd.DataFrame()
    n_buy = len(buy_stocks)
    n_candidates = len(candidates)
    top_sector = sector_rank.iloc[0]["SECTOR_NAME"] if not sector_rank.empty else "—"
    top_sector_score = _fmth(sector_rank.iloc[0].get("ROTATION_SCORE") if not sector_rank.empty else None)
    top_sector_1m = _ret_cell(sector_rank.iloc[0].get("RET_1M") if not sector_rank.empty else None)

    buy_list_html = ""
    if not buy_stocks.empty:
        for _, r in buy_stocks.head(8).iterrows():
            sym = _h(r.get("SYMBOL", ""))
            co = _h(r.get("COMPANY_NAME", sym))
            sec = _h(r.get("SECTOR_NAME", ""))
            sc = _fmth(r.get("INVESTMENT_SCORE"))
            buy_list_html += (
                f'<li>{_signal_badge("BUY")} <strong>{sym}</strong> — {co} '
                f'<span class="muted">({sec})</span> <span class="sv" style="margin-left:auto">Score {sc}</span></li>'
            )
    else:
        buy_list_html = '<li><em>No BUY signals in current rotation.</em></li>'

    metrics_html = (
        f'<div class="metrics-row">'
        f'<div class="metric-card"><div class="metric-label">BUY Signals</div>'
        f'<div class="metric-value">{n_buy}</div><div class="metric-sub">out of {n_candidates} candidates</div></div>'
        f'<div class="metric-card"><div class="metric-label">Leading Sector</div>'
        f'<div class="metric-value" style="font-size:1rem">{html_mod.escape(top_sector)}</div>'
        f'<div class="metric-sub">Score {top_sector_score} · 1M {top_sector_1m}</div></div>'
        f'<div class="metric-card"><div class="metric-label">Sectors Rotating</div>'
        f'<div class="metric-value">{len(sector_rank)}</div><div class="metric-sub">above Nifty 500 baseline</div></div>'
        f'<div class="metric-card"><div class="metric-label">Data As Of</div>'
        f'<div class="metric-value" style="font-size:1rem">{html_mod.escape(str(data_date))}</div>'
        f'<div class="metric-sub">Report: {gen_date}</div></div>'
        f'</div>'
    )

    summary_card = (
        f'<div class="summary-card"><h3>Market Rotation Context</h3>'
        f'<p>{html_mod.escape(market_summary) if market_summary else "<em>Analysing rotation across " + str(len(sector_rank)) + " sectors vs Nifty 500 benchmark.</em>"}</p>'
        f'</div>'
    )
    buy_card = (
        f'<div class="summary-card"><h3>Active BUY Signals ({n_buy})</h3>'
        f'<ul class="buy-list">{buy_list_html}</ul></div>'
    )

    # Chart data
    rot_labels = [str(row.get("SECTOR_NAME", "")) for _, row in sector_rank.iterrows()]
    rot_scores = [round(float(row.get("ROTATION_SCORE", 0) or 0), 2) for _, row in sector_rank.iterrows()]

    chart_html = (
        f'<div class="chart-wrap">'
        f'<div class="chart-title">Sector Rotation Score vs Nifty 500</div>'
        f'<canvas id="rotChart" style="height:240px"></canvas>'
        f'</div>'
    )

    overview_html = (
        metrics_html
        + f'<div class="overview-grid">{summary_card}{buy_card}</div>'
        + chart_html
    )

    # ---- BUILD ROTATION TAB ----
    rot_rows = ""
    for rank, (_, row) in enumerate(sector_rank.iterrows(), start=1):
        sym = _h(row.get("SYMBOL", ""))
        sname = _h(row.get("SECTOR_NAME", ""))
        close_v = _fmth(row.get("CLOSE"), digits=2)
        r5d = _ret_cell(row.get("RET_5D"))
        r1m = _ret_cell(row.get("RET_1M"))
        r3m = _ret_cell(row.get("RET_3M"))
        r6m = _ret_cell(row.get("RET_6M"))
        rs1m = _ret_cell(row.get("RS_1M"))
        rscore_raw = float(row.get("ROTATION_SCORE", 0) or 0)
        max_score = max(rot_scores) if rot_scores else 1
        bar_w = int(rscore_raw / max_score * 100) if max_score > 0 else 0
        rscore_html = (
            f'<div class="rot-wrap">'
            f'<span style="font-weight:700;min-width:32px;text-align:right">{rscore_raw:.1f}</span>'
            f'<div class="rot-track"><div class="rot-fill" style="width:{bar_w}%"></div></div>'
            f'</div>'
        )
        # PG: macro tailwind badge (P1-6)
        _mtw_val = float(row.get("MACRO_TAILWIND", 0) or 0)
        _mtw_cls = "mtw-pos" if _mtw_val > 0.5 else ("mtw-neg" if _mtw_val < -0.5 else "mtw-neu")
        _mtw_html = f'<span class="mtw-badge {_mtw_cls}">{_mtw_val:+.1f}</span>'
        # B3: seasonal signal badge
        _ssig = str(row.get("SEASONAL_SIGNAL", "NEUTRAL") or "NEUTRAL")
        _ssig_map = {"TAILWIND": ("🌱 Tailwind", "ssig-tail"), "HEADWIND": ("🌧 Headwind", "ssig-head"), "NEUTRAL": ("→ Neutral", "ssig-neu")}
        _ssig_lbl, _ssig_cls = _ssig_map.get(_ssig, ("→ Neutral", "ssig-neu"))
        _ssig_html = f'<span class="ssig {_ssig_cls}">{_ssig_lbl}</span>'
        # C3: sector breadth badge
        _bsig = str(row.get("BREADTH_SIGNAL", "NO_DATA") or "NO_DATA")
        _bdiv = str(row.get("BREADTH_DIVERGENCE", "NONE") or "NONE")
        _bpct = row.get("BREADTH_PCT50")
        _bpct_str = f"{float(_bpct):.0f}%" if _bpct is not None and str(_bpct) not in ("nan", "") else "–"
        _bsig_cls_map = {"STRONG": "brd-strong", "HEALTHY": "brd-healthy", "NEUTRAL": "brd-neu", "WEAK": "brd-weak", "BEARISH": "brd-bear"}
        _bsig_cls = _bsig_cls_map.get(_bsig, "brd-nd")
        _bdiv_cls_map = {"BULLISH_DIV": "bdiv-bull", "BEARISH_DIV": "bdiv-bear", "INT_WEAKNESS": "bdiv-int"}
        _bdiv_html = (
            f'<span class="bdiv {_bdiv_cls_map.get(_bdiv, "")}">{_bdiv.replace("_", " ")}</span>'
            if _bdiv != "NONE" else ""
        )
        _breadth_html = f'<span class="brd-badge {_bsig_cls}">{_bpct_str} {_bsig}</span>{_bdiv_html}'
        rot_rows += (
            f'<tr>'
            f'<td class="num" data-val="{rank}"><span class="rank-num">{rank}</span></td>'
            f'<td>{sym}</td>'
            f'<td><strong>{sname}</strong></td>'
            f'<td class="num" data-val="{_fmth(row.get("CLOSE"), digits=2)}">{close_v}</td>'
            f'<td class="num" data-val="{_fmth(row.get("RET_5D"))}">{r5d}</td>'
            f'<td class="num" data-val="{_fmth(row.get("RET_1M"))}">{r1m}</td>'
            f'<td class="num" data-val="{_fmth(row.get("RET_3M"))}">{r3m}</td>'
            f'<td class="num" data-val="{_fmth(row.get("RET_6M"))}">{r6m}</td>'
            f'<td class="num" data-val="{_fmth(row.get("RS_1M"))}">{rs1m}</td>'
            f'<td data-val="{rscore_raw:.2f}">{rscore_html}</td>'
            f'<td class="num" data-val="{_mtw_val:.2f}">{_mtw_html}</td>'
            f'<td>{_ssig_html}</td>'
            f'<td>{_breadth_html}</td>'
            f'</tr>'
        )

    rotation_table = (
        f'<div class="tbl-wrap"><table><thead><tr>'
        f'<th>#</th><th>Index</th><th>Sector</th><th class="num">Close</th>'
        f'<th class="num">5D</th><th class="num">1M</th><th class="num">3M</th><th class="num">6M</th>'
        f'<th class="num">RS 1M</th><th>Score</th><th class="num">Macro</th><th>Season</th><th>Breadth</th>'
        f'</tr></thead><tbody>{rot_rows}</tbody></table></div>'
    )

    # Sector narratives below table
    sec_narr_html = '<h3 style="margin:20px 0 12px;font-size:14px;color:var(--primary)">Sector Analysis Narratives</h3>'
    for _, row in sector_rank.iterrows():
        sname = str(row.get("SECTOR_NAME", ""))
        narr = sec_narratives.get(sname, {})
        narr_text = narr.get("narrative", "") if isinstance(narr, dict) else ""
        conviction = narr.get("conviction", "MEDIUM") if isinstance(narr, dict) else "MEDIUM"
        key_themes = narr.get("key_themes", []) if isinstance(narr, dict) else []

        themes_html = "".join(f'<span class="theme-chip">{html_mod.escape(str(t))}</span>' for t in key_themes)
        conv_cls = f"conviction conv-{conviction}"

        sec_narr_html += (
            f'<div class="sec-narr-card">'
            f'<div class="sec-narr-hdr">'
            f'<div class="sec-narr-title">{html_mod.escape(sname)}</div>'
            f'<span class="{conv_cls}">{conviction} Conviction</span>'
            f'</div>'
            + (_narrative_html(narr_text, is_sector=True) if narr_text else "<p><em>Narrative pending.</em></p>")
            + (f'<div class="themes">{themes_html}</div>' if themes_html else "")
            + f'</div>'
        )

    rotation_html = (
        f'<div class="sec-title">Sector Rotation Rankings</div>'
        f'<div class="sec-sub">Ranked by composite rotation score vs Nifty 500. Click column headers to sort.</div>'
        + rotation_table
        + (f'<div class="card" style="margin:12px 0">{seasonal_calendar_html}</div>' if seasonal_calendar_html else "")
        + sec_narr_html
    )

    # ---- BUILD CANDIDATES TAB ----
    # Sector filter pills
    sector_order = list(sector_rank["SECTOR_NAME"].drop_duplicates())
    pills_inner = '<button class="sec-pill active" data-spill="">All Sectors</button>'
    for sname in sector_order:
        pills_inner += f'<button class="sec-pill" data-spill="{html_mod.escape(sname)}">{html_mod.escape(sname)}</button>'
    pills_html = (
        '<div class="pills-nav">'
        '<button class="pills-arrow pills-arrow-l" aria-label="scroll left">&#8249;</button>'
        f'<div class="sec-pills">{pills_inner}</div>'
        '<button class="pills-arrow pills-arrow-r" aria-label="scroll right">&#8250;</button>'
        '</div>'
    )

    def _has_insider_alert(row: pd.Series) -> bool:
        alert = str(row.get("INSIDER_ALERT", "") or "").strip().lower()
        return alert not in ("", "nan", "none")

    def _display_candidates_for_sector(sector_candidates: pd.DataFrame) -> pd.DataFrame:
        top_rows = sector_candidates.head(5)
        if "INSIDER_ALERT" not in sector_candidates.columns:
            return top_rows
        alert_rows = sector_candidates[sector_candidates.apply(_has_insider_alert, axis=1)]
        if alert_rows.empty:
            return top_rows
        return pd.concat([top_rows, alert_rows]).drop_duplicates("SYMBOL", keep="first")

    sector_blocks_html = ""
    for rank_idx, sname in enumerate(sector_order, start=1):
        part = _display_candidates_for_sector(candidates[candidates["SECTOR_NAME"] == sname])
        if part.empty:
            continue
        sec_row = sector_rank[sector_rank["SECTOR_NAME"] == sname]
        rot_score_str = _fmth(sec_row.iloc[0].get("ROTATION_SCORE") if not sec_row.empty else None)
        ret1m_str = _ret_cell(sec_row.iloc[0].get("RET_1M") if not sec_row.empty else None)
        rs1m_str = _ret_cell(sec_row.iloc[0].get("RS_1M") if not sec_row.empty else None)

        # Stock rows
        stock_rows_html = ""
        for _, r in part.iterrows():
            sym = str(r.get("SYMBOL", ""))
            co = _h(r.get("COMPANY_NAME", sym))
            price = _fmth(r.get("CURRENT_PRICE"), digits=2)
            sig_html = _signal_badge(str(r.get("TRADING_SIGNAL", "HOLD")))
            setup_html = _setup_badge(str(r.get("SETUP_CLASS", "NEUTRAL")))
            action_html = _action_badge(str(r.get("ACTION_BUCKET", "WATCHLIST")))
            # A1: stage badge
            try:
                from screeners import stage_badge_html as _sbh
                _stage_html = _sbh(str(r.get("STAGE", "UNKNOWN") or "UNKNOWN"))
            except Exception:
                _stage_html = ""
            inv_bar = _score_bar(r.get("INVESTMENT_SCORE"), "invest")
            tech_bar = _score_bar(r.get("TECHNICAL_SCORE"), "tech")
            fund_bar = _score_bar(r.get("ENHANCED_FUND_SCORE"), "fund")
            rs_html = _ret_cell(r.get("RELATIVE_STRENGTH"))
            rsi_html = _rsi_cell(r.get("RSI"))
            st_html = _st_badge(str(r.get("SUPERTREND_STATE", "UNKNOWN")))
            pat_html = _pattern_badge(str(r.get("PATTERN", "")))
            vol_html = _vol_cell(r.get("VOLUME_RATIO"))

            # F&O signal badge (P1-2)
            _fno_sig = str(r.get("FNO_SIGNAL", "") or "")
            _fno_buildup = str(r.get("FNO_BUILDUP", "") or "")
            _fno_pcr_val = r.get("FNO_PCR")
            if _fno_sig and _fno_sig not in ("", "nan", "None"):
                _fno_label_map = {"BULL": "🟢 Bull", "MILD_BULL": "🟡 Mild Bull", "NEUTRAL": "⚪ Neutral", "MILD_BEAR": "🟠 Mild Bear", "BEAR": "🔴 Bear"}
                _fno_css_map = {"BULL": "fno-bull", "MILD_BULL": "fno-mbull", "NEUTRAL": "fno-neutral", "MILD_BEAR": "fno-mbear", "BEAR": "fno-bear"}
                _fno_lbl = _fno_label_map.get(_fno_sig.upper(), _fno_sig)
                _fno_cls = _fno_css_map.get(_fno_sig.upper(), "fno-neutral")
                _bu_lbl = {"LONG_BUILDUP": "Long Buildup", "SHORT_BUILDUP": "Short Buildup", "SHORT_COVERING": "Short Cover", "LONG_UNWINDING": "Long Unwind"}.get(_fno_buildup.upper(), "")
                _pcr_s = f"PCR: {float(_fno_pcr_val):.2f}" if _fno_pcr_val and not (isinstance(_fno_pcr_val, float) and math.isnan(_fno_pcr_val)) else ""
                _det_parts = [p for p in [_bu_lbl, _pcr_s] if p]
                _fno_det = f'<div class="fno-detail">{" · ".join(_det_parts)}</div>' if _det_parts else ""
                fno_html = f'<span class="fno {_fno_cls}">{_fno_lbl}</span>{_fno_det}'
            else:
                fno_html = '<span class="fno fno-na">—</span>'

            # Insider/promoter alert badge (P1-4)
            _ins_at = str(r.get("INSIDER_ALERT", "") or "")
            _ins_sc = r.get("INSIDER_SCORE")
            _ins_det = str(r.get("INSIDER_DETAIL", "") or "")
            if _ins_at and _ins_at not in ("", "nan", "None"):
                _ins_lmap = {"PROMOTER_BUYING": ("🟢 Promo Buy", "ins-bull"), "INSIDER_BUY": ("🟢 Insider Buy", "ins-bull"), "BULK_DEAL_BUY": ("🔵 Bulk Buy", "ins-info"), "PROMOTER_SELLING": ("🔴 Promo Sell", "ins-bear"), "INSIDER_SELL": ("🟠 Insider Sell", "ins-warn"), "BULK_DEAL_SELL": ("🟠 Bulk Sell", "ins-warn"), "PROMOTER_PLEDGE": ("⚠️ Pledge", "ins-warn")}
                _ins_lbl, _ins_cls = _ins_lmap.get(_ins_at.upper(), (_ins_at.replace("_", " ").title(), "ins-neutral"))
                _ins_det_html = html_mod.escape(_ins_det[:120]) if _ins_det and _ins_det not in ("nan", "None") else ""
                if _ins_det_html:
                    ins_html = (
                        f'<details class="click-detail">'
                        f'<summary><span class="ins {_ins_cls}">{_ins_lbl}</span></summary>'
                        f'<div class="click-detail-body">{_ins_det_html}</div>'
                        f'</details>'
                    )
                else:
                    ins_html = f'<span class="ins {_ins_cls}">{_ins_lbl}</span>'
            else:
                ins_html = '<span class="ins ins-na">—</span>'

            # Corporate event badge (E4)
            _evt_type = str(r.get("NEXT_EVENT", "") or "")
            _evt_days_raw = r.get("NEXT_EVENT_DAYS", "")
            _evt_det = str(r.get("EVENT_DETAIL", "") or "")
            if _evt_type and _evt_type not in ("", "nan", "None"):
                try:
                    from fetch_corporate_events import event_badge_html as _evtbadge
                    _evt_days_int = int(float(_evt_days_raw)) if _evt_days_raw not in ("", None) else -1
                    _evt_badge_html = _evtbadge(_evt_type, _evt_days_int, _evt_det)
                    if '<div class="evt-detail">' in _evt_badge_html:
                        _evt_badge_html = _evt_badge_html.split('<div class="evt-detail">', 1)[0]
                    _evt_det_html = html_mod.escape(_evt_det[:120]) if _evt_det and _evt_det not in ("nan", "None") else ""
                    if _evt_det_html:
                        evt_html = (
                            f'<details class="click-detail">'
                            f'<summary>{_evt_badge_html}</summary>'
                            f'<div class="click-detail-body">{_evt_det_html}</div>'
                            f'</details>'
                        )
                    else:
                        evt_html = _evt_badge_html
                except Exception:
                    _evt_badge_html = f'<span class="evt evt-other">{html_mod.escape(_evt_type.replace("_", " ").title())}</span>'
                    _evt_det_html = html_mod.escape(_evt_det[:120]) if _evt_det and _evt_det not in ("nan", "None") else ""
                    if _evt_det_html:
                        evt_html = (
                            f'<details class="click-detail">'
                            f'<summary>{_evt_badge_html}</summary>'
                            f'<div class="click-detail-body">{_evt_det_html}</div>'
                            f'</details>'
                        )
                    else:
                        evt_html = _evt_badge_html
            else:
                evt_html = '<span class="evt evt-na">—</span>'

            # ---- Build signals popup (F&O + Insider + Events) ----
            # Indicator dots on the button
            _fno_dot_cls = (
                "sdot-bull" if _fno_sig.upper() in ("BULL", "MILD_BULL")
                else "sdot-bear" if _fno_sig.upper() in ("BEAR", "MILD_BEAR")
                else "sdot-neu"
            ) if _fno_sig and _fno_sig not in ("", "nan", "None") else "sdot-none"
            _ins_dot_cls = (
                "sdot-bull" if _ins_at.upper() in ("PROMOTER_BUYING", "INSIDER_BUY", "BULK_DEAL_BUY")
                else "sdot-bear" if _ins_at.upper() in ("PROMOTER_SELLING", "INSIDER_SELL", "BULK_DEAL_SELL", "PROMOTER_PLEDGE")
                else "sdot-neu"
            ) if _ins_at and _ins_at not in ("", "nan", "None") else "sdot-none"
            _evt_dot_cls = "sdot-evt" if _evt_type and _evt_type not in ("", "nan", "None") else "sdot-none"

            # Full F&O popup row content (richer than inline badge)
            if _fno_sig and _fno_sig not in ("", "nan", "None"):
                _fno_oi_chg = r.get("FNO_OI_CHANGE_5D")
                _fno_mp = r.get("FNO_MAX_PAIN")
                _fno_oi_str = f"{float(_fno_oi_chg):+.1f}%" if _fno_oi_chg and not (isinstance(_fno_oi_chg, float) and math.isnan(float(_fno_oi_chg))) else ""
                _fno_mp_str = f"Max Pain: ₹{float(_fno_mp):,.0f}" if _fno_mp and not (isinstance(_fno_mp, float) and math.isnan(float(_fno_mp))) else ""
                _fno_popup_parts = [p for p in [_bu_lbl, _pcr_s, _fno_oi_str, _fno_mp_str] if p]
                _fno_popup_content = fno_html + (f'<div class="sp-detail">{" · ".join(_fno_popup_parts)}</div>' if _fno_popup_parts else "")
            else:
                _fno_popup_content = '<span class="sp-none">No F&amp;O data</span>'

            if _ins_at and _ins_at not in ("", "nan", "None"):
                _ins_sc_str = f"Score: {int(float(_ins_sc)):+d}" if _ins_sc not in (None, "") else ""
                _ins_popup_content = ins_html + (f'<div class="sp-detail">{html_mod.escape(_ins_det[:120])} {_ins_sc_str}</div>' if _ins_det and _ins_det not in ("nan", "None") else "")
            else:
                _ins_popup_content = '<span class="sp-none">No insider alerts</span>'

            if _evt_type and _evt_type not in ("", "nan", "None"):
                _evt_popup_content = evt_html
            else:
                _evt_popup_content = '<span class="sp-none">No upcoming events</span>'

            _popup_id = f"sp-{html_mod.escape(sym)}"
            signals_html = (
                f'<div class="signals-wrap">'
                f'<button class="signals-btn" onclick="toggleSignals(this,event)" aria-label="Signals for {html_mod.escape(sym)}">'
                f'<span class="sdot {_fno_dot_cls}"></span>'
                f'<span class="sdot {_ins_dot_cls}"></span>'
                f'<span class="sdot {_evt_dot_cls}"></span>'
                f'<span class="sbtn-lbl">Signals</span>'
                f'</button>'
                f'<div class="signals-popup">'
                f'<div class="sp-row"><div class="sp-label">F&amp;O</div><div class="sp-val">{_fno_popup_content}</div></div>'
                f'<div class="sp-row sp-sep"><div class="sp-label">Insider</div><div class="sp-val">{_ins_popup_content}</div></div>'
                f'<div class="sp-row sp-sep"><div class="sp-label">Events</div><div class="sp-val">{_evt_popup_content}</div></div>'
                f'</div>'
                f'</div>'
            )
            entry_low_str  = _price_fmt(r.get("ENTRY_LOW"))
            entry_high_str = _price_fmt(r.get("ENTRY_HIGH"))
            stop_str       = _price_fmt(r.get("STOP_LOSS"))
            tgt1_str       = _price_fmt(r.get("TARGET_1"))
            tgt2_str       = _price_fmt(r.get("TARGET_2"))
            res_str        = _price_fmt(r.get("RESISTANCE"))
            sup_str        = _price_fmt(r.get("SUPPORT"))
            st_str         = _price_fmt(r.get("SUPERTREND_VALUE"))

            levels_html = (
                f'<div class="levels">'
                f'<span class="lev-entry">Entry: {html_mod.escape(entry_low_str)}–{html_mod.escape(entry_high_str)}</span>'
                f'<span class="lev-stop">Stop: {html_mod.escape(stop_str)}</span>'
                f'<span class="lev-tgt">T1: {html_mod.escape(tgt1_str)}</span>'
                f'<span class="lev-tgt2">T2: {html_mod.escape(tgt2_str)}</span>'
                f'</div>'
                f'<div class="levels-sub">'
                f'<span class="lev-r">R: {html_mod.escape(res_str)}</span>'
                f' · <span class="lev-s">S: {html_mod.escape(sup_str)}</span>'
                f' · <span style="color:#7c3aed">ST: {html_mod.escape(st_str)}</span>'
                f'</div>'
            )

            # Stock narrative
            stk_narr = stk_narratives.get(sym, {})
            stk_narr_text = stk_narr.get("narrative", "") if isinstance(stk_narr, dict) else ""
            stance = stk_narr.get("stance", "") if isinstance(stk_narr, dict) else ""
            stance_badge = ""
            if stance:
                stance_css = {"CONSTRUCTIVE": "sig-buy", "CAUTIOUS": "sig-sell", "NEUTRAL": "sig-hold"}.get(stance, "sig-hold")
                stance_badge = f' &nbsp;<span class="sig {stance_css}" style="font-size:9px">{stance}</span>'

            narr_details = (
                f'<details class="narr">'
                f'<summary>Investment Narrative — {html_mod.escape(sym)}{stance_badge}</summary>'
                f'<div class="narr-body">{_narrative_html(stk_narr_text)}</div>'
                f'</details>'
            )

            stock_rows_html += (
                f'<tr>'
                f'<td><strong>{html_mod.escape(sym)}</strong></td>'
                f'<td>{co}</td>'
                f'<td class="num" data-val="{price}">₹{price}</td>'
                f'<td>{sig_html}<br>{setup_html}<br>{action_html}<br>{_cycle_tag_badge(r.get("CYCLE_TAG"), r.get("CYCLE_ADJUSTMENT"))}<br>{_stage_html}</td>'
                f'<td data-val="{_fmth(r.get("INVESTMENT_SCORE"))}">{inv_bar}</td>'
                f'<td data-val="{_fmth(r.get("TECHNICAL_SCORE"))}">{tech_bar}</td>'
                f'<td data-val="{_fmth(r.get("ENHANCED_FUND_SCORE"))}">{fund_bar}</td>'
                f'<td class="num" data-val="{_fmth(r.get("RELATIVE_STRENGTH"))}">{rs_html}</td>'
                f'<td class="num" data-val="{_fmth(r.get("RSI"))}">{rsi_html}</td>'
                f'<td>{st_html}</td>'
                f'<td>{pat_html}</td>'
                f'<td>{vol_html}</td>'
                f'<td style="position:relative">{signals_html}</td>'
                f'<td>{levels_html}</td>'
                f'</tr>'
                f'<tr><td colspan="14" style="padding:4px 12px 10px;background:#fafbff">{narr_details}</td></tr>'
            )

        sec_table = (
            f'<div class="tbl-wrap"><table>'
            f'<colgroup>'
            f'<col><col><col><col><col><col><col><col><col><col><col><col><col><col>'
            f'</colgroup>'
            f'<thead><tr>'
            f'<th>Symbol</th><th>Company</th><th class="num">Price</th>'
            f'<th>Signal / Action</th><th>Score</th><th>Tech</th><th>Fund</th>'
            f'<th class="num">RS%</th><th class="num">RSI</th>'
            f'<th>Supertrend</th><th>Pattern</th><th>Vol</th><th>Signals</th><th>Entry · Stop · Targets</th>'
            f'</tr></thead>'
            f'<tbody>{stock_rows_html}</tbody>'
            f'</table></div>'
        )

        sector_blocks_html += (
            f'<div data-sblock="{html_mod.escape(sname)}">'
            f'<div class="sec-hdr">'
            f'<div class="sec-rank">{rank_idx}</div>'
            f'<div class="sec-name">{html_mod.escape(sname)}</div>'
            f'<div class="sec-meta">'
            f'<span>Rotation: {rot_score_str}</span>'
            f'<span>1M: {ret1m_str}</span>'
            f'<span>RS: {rs1m_str}</span>'
            f'</div>'
            f'</div>'
            + sec_table
            + f'</div>'
        )

    # Build heatmap grid for quick visual scan (P1-5)
    _hm_cells = ""
    _total_cands = 0
    for sname in sector_order:
        part = _display_candidates_for_sector(candidates[candidates["SECTOR_NAME"] == sname])
        for _, r in part.iterrows():
            _total_cands += 1
            _hm_sym = _h(r.get("SYMBOL", ""))
            _hm_score = r.get("INVESTMENT_SCORE")
            _hm_score_f = float(_hm_score) if _hm_score and not (isinstance(_hm_score, float) and math.isnan(_hm_score)) else 0
            _hm_sig = str(r.get("SIGNAL", ""))
            # Score → color mapping
            if _hm_score_f >= 70: _hm_bg = "#15803d"
            elif _hm_score_f >= 55: _hm_bg = "#22c55e"
            elif _hm_score_f >= 40: _hm_bg = "#d97706"
            elif _hm_score_f >= 25: _hm_bg = "#ea580c"
            else: _hm_bg = "#dc2626"
            _hm_cells += (
                f'<div class="hm-cell" data-sector="{html_mod.escape(sname)}" style="background:{_hm_bg}" '
                f'title="{html_mod.escape(_hm_sym)} — Score: {_fmth(_hm_score)} | {html_mod.escape(_hm_sig)}">'
                f'{html_mod.escape(_hm_sym)}<span class="hm-score">{_fmth(_hm_score)}</span></div>'
            )
    heatmap_html = f'<div class="hm-wrap"><div class="hm-grid">{_hm_cells}</div></div>'

    # Dashboard toolbar: search, heatmap toggle, print (P1-5)
    toolbar_html = (
        '<div class="dash-toolbar">'
        '<input type="text" id="narrSearch" class="dash-search" placeholder="Search stocks or narratives…" autocomplete="off">'
        '<button id="hmToggle" class="dash-btn" title="Switch between table and heatmap view">Heatmap</button>'
        '<button id="printReport" class="dash-btn" title="Print / export as PDF">🖨 Print</button>'
        f'<span id="matchCount" class="dash-count">{_total_cands} stocks</span>'
        '</div>'
    )

    candidates_html = (
        f'<div class="sec-title">Investment Candidates by Sector</div>'
        f'<div class="sec-sub">Ranked within each sector by composite investment score. '
        f'Click any row\'s narrative arrow to expand the analysis.</div>'
        + toolbar_html
        + pills_html
        + heatmap_html
        + f'<div class="sblock-area">{sector_blocks_html}</div>'
    )

    # ---- BUILD RESILIENCE TAB ----
    if peak_resilience.empty:
        resilience_html = '<div class="card"><p>No stocks passed the peak-resilience filter in the current universe.</p></div>'
    else:
        res_rows = ""
        for rank, (_, row) in enumerate(peak_resilience.head(25).iterrows(), start=1):
            sym = _h(row.get("SYMBOL", ""))
            sec = _h(row.get("SECTOR_NAME", ""))
            price = _fmth(row.get("CURRENT_PRICE"), digits=2)
            h52 = _fmth(row.get("FIFTY_TWO_WEEK_HIGH"), digits=2)
            l52 = _fmth(row.get("FIFTY_TWO_WEEK_LOW"), digits=2)
            dd = row.get("DRAWDOWN_FROM_52W_HIGH_PCT")
            dd_html = _dd_cell(dd)
            rec = _ret_cell(row.get("RECOVERY_FROM_52W_LOW_PCT"))
            days = _fmth(row.get("DAYS_SINCE_52W_LOW"), digits=0)
            speed = _fmth(row.get("RECOVERY_SPEED_SCORE"), suffix="%/d", digits=2)
            peak = _fmth(row.get("PEAK_RESILIENCE_SCORE"))

            # Proximity bar (how close to 52W high)
            dd_f = float(dd) if dd and not (isinstance(dd, float) and math.isnan(dd)) else -20
            proximity_pct = max(0, min(100, 100 + dd_f))
            bar_color = "#15803d" if proximity_pct > 97 else "#d97706" if proximity_pct > 90 else "#dc2626"
            proximity_html = (
                f'<div class="dd-bar-wrap">'
                f'{dd_html}'
                f'<div class="dd-bar-outer"><div class="dd-bar-inner" style="width:{proximity_pct:.0f}%;background:{bar_color}"></div></div>'
                f'</div>'
            )

            res_rows += (
                f'<tr>'
                f'<td class="num" data-val="{rank}"><span class="rank-num">{rank}</span></td>'
                f'<td><strong>{sym}</strong></td>'
                f'<td>{sec}</td>'
                f'<td class="num" data-val="{price}">₹{price}</td>'
                f'<td class="num" data-val="{h52}">₹{h52}</td>'
                f'<td class="num" data-val="{l52}">₹{l52}</td>'
                f'<td data-val="{_fmth(dd)}">{proximity_html}</td>'
                f'<td class="num" data-val="{_fmth(row.get("RECOVERY_FROM_52W_LOW_PCT"))}">{rec}</td>'
                f'<td class="num" data-val="{_fmth(row.get("DAYS_SINCE_52W_LOW"), digits=0)}">{days}d</td>'
                f'<td class="num" data-val="{_fmth(row.get("RECOVERY_SPEED_SCORE"), digits=4)}">{speed}</td>'
                f'<td data-val="{_fmth(row.get("PEAK_RESILIENCE_SCORE"))}">{_score_bar(row.get("PEAK_RESILIENCE_SCORE"), "invest")}</td>'
                f'</tr>'
            )

        resilience_table = (
            f'<div class="tbl-wrap"><table><thead><tr>'
            f'<th>#</th><th>Symbol</th><th>Sector</th><th class="num">Price</th>'
            f'<th class="num">52W High</th><th class="num">52W Low</th>'
            f'<th>Drawdown</th><th class="num">Recovery</th>'
            f'<th class="num">Days</th><th class="num">Speed</th><th>Peak Score</th>'
            f'</tr></thead><tbody>{res_rows}</tbody></table></div>'
        )
        resilience_html = (
            f'<div class="sec-title">Peak Resilience & Fast Recovery</div>'
            f'<div class="sec-sub">Stocks within 5% of their 52-week high, ranked by composite peak resilience score. '
            f'Green drawdown = very close to 52W high.</div>'
            + resilience_table
        )

    # ---- BUILD STAGE SCREENER TAB (A1 + A3) ----
    def _build_screener_tab(cands: pd.DataFrame) -> str:
        try:
            from screeners import (
                run_stage_screener,
                build_stage_screener_tab_html,
                momentum_52w_high_screener,
                build_momentum_screener_tab_html,
            )
            screener_df = run_stage_screener(cands)
            stage_html = build_stage_screener_tab_html(screener_df)
            momentum_df = momentum_52w_high_screener(screener_df)
            momentum_html = build_momentum_screener_tab_html(momentum_df)
            return stage_html + momentum_html
        except Exception as exc:
            return f'<div class="card"><p>Screener unavailable: {html_mod.escape(str(exc))}</p></div>'

    # ---- BUILD METHODOLOGY TAB ----
    methodology_html = (
        '<div class="sec-title">Methodology</div>'
        '<div class="sec-sub">How each score and screen is calculated.</div>'
        # ── Section 1: Scoring ──────────────────────────────────────────────
        '<div class="meth-grid">'
        '<div class="meth-section-hdr">1 · Scoring Frameworks</div>'

        '<div class="meth-card">'
        '<div class="meth-card-title"><div class="meth-icon">R</div>Sector Rotation Score</div>'
        '<p>Ranks sectors by short-term momentum and relative strength versus the Nifty 500 benchmark. '
        'Positive values mean the sector is outperforming the broad market. '
        'The five sub-components capture momentum across multiple timeframes, with the heaviest weight on 1-month RS.</p>'
        '<div class="formula">0.35 × RS_1M + 0.25 × RET_1M<br>+ 0.20 × RS_5D + 0.10 × RS_3M + 0.10 × RS_6M<br>'
        '<span style="font-size:9px">RS_xM = sector return minus Nifty 500 return over the same period</span></div>'
        '</div>'

        '<div class="meth-card">'
        '<div class="meth-card-title"><div class="meth-icon">S</div>Investment Score</div>'
        '<p>Per-stock composite score (0–100+) that blends price momentum, relative strength, fundamentals, and qualitative bonuses. '
        'Use it to rank candidates within a sector, not across sectors. '
        '<strong>Stage 2</strong> stocks receive +4; Stage 3 = −5; Stage 4 = −8.</p>'
        '<div class="formula">0.38 × Tech + 0.27 × RS_rank + 0.25 × Fund<br>'
        '+ Pattern bonus (+3) + Supertrend bonus (+2)<br>'
        '+ Signal bonus (F&amp;O/Insider) + Stage bonus (±4/−5/−8)</div>'
        '</div>'

        '<div class="meth-card">'
        '<div class="meth-card-title"><div class="meth-icon">T</div>Technical Score</div>'
        '<p>Aggregates price-based momentum signals: RSI (14), distance from 52W high, '
        'SMA50/SMA200 position, short-term rate-of-change, and volume trend. '
        'Scored 0–100; values above 60 indicate strong uptrend conditions.</p>'
        '<div class="formula">RSI, SMA50/200 crossover, 52W high proximity,<br>'
        '5-day & 20-day ROC, volume ratio vs 20D avg</div>'
        '</div>'

        '<div class="meth-card">'
        '<div class="meth-card-title"><div class="meth-icon">F</div>Fundamental Score</div>'
        '<p>Enhanced composite score sourced from the Screener.in pipeline, covering earnings quality, '
        'revenue growth, balance sheet strength, and institutional interest. '
        'Refreshed weekly.</p>'
        '<div class="formula">Score: 0–100 · Source: fundamental_scores_database.csv<br>'
        '≥65: Strong · 50–65: Moderate · &lt;50: Speculative</div>'
        '</div>'

        '<div class="meth-card">'
        '<div class="meth-card-title"><div class="meth-icon">P</div>Peak Resilience Score</div>'
        '<p>Identifies stocks trading within 20% of their 52-week high — the hallmark of institutional accumulation. '
        'Scores favour stocks near their peak with strong technicals, fast drawdown recovery, and solid fundamentals.</p>'
        '<div class="formula">0.25 × Tech + 0.20 × RS + 0.20 × RecoverySpeed<br>'
        '+ 0.20 × HighProximity + 0.15 × Fund</div>'
        '</div>'

        '</div>'  # end meth-grid section 1

        # ── Section 2: Trend & Pattern Indicators ──────────────────────────
        '<div class="meth-grid" style="margin-top:8px">'
        '<div class="meth-section-hdr">2 · Trend &amp; Pattern Indicators</div>'

        '<div class="meth-card">'
        '<div class="meth-card-title"><div class="meth-icon">ST</div>Supertrend</div>'
        '<p>ATR-based dynamic support/resistance line. When price closes above the band the signal turns <strong>Bullish</strong>; '
        'below it turns <strong>Bearish</strong>. A flip from Bear→Bull adds +2 to the Investment Score. '
        'Works best on daily timeframe with a 1–2 week holding horizon.</p>'
        '<div class="formula">Period: 10 · Multiplier: 3.0 · Source: NSE OHLC cache<br>'
        'Score bonus: +2 (Bull), −1 (Bear)</div>'
        '</div>'

        '<div class="meth-card">'
        '<div class="meth-card-title"><div class="meth-icon">B</div>Consolidation Breakout</div>'
        '<p>Flags stocks that have just broken above a tight multi-week base. '
        'Requires the latest close to exceed the prior 20-session high, the base to be narrow (≤12% range), '
        'and volume to spike to at least 1.4× the 20-day average — confirming institutional demand.</p>'
        '<div class="formula">Lookback: 20 sessions · Base width ≤ 12%<br>'
        'Volume threshold: 1.4× 20D avg · Score bonus: +3</div>'
        '</div>'

        '<div class="meth-card">'
        '<div class="meth-card-title"><div class="meth-icon">A1</div>Stage Analysis (O\'Neil / Weinstein)</div>'
        '<p>Classifies every stock into one of four price-cycle stages using the SMA 50/200 structure and their slopes. '
        '<strong>Only buy Stage 2.</strong> Avoid Stage 3 (distribution) and never hold Stage 4 (decline).</p>'
        '<ul style="font-size:12px;color:var(--muted);margin:6px 0 0 16px;line-height:1.8">'
        '<li><strong>Stage 2 — Markup ✅</strong>: Price &gt; SMA50 &gt; SMA200, both slopes rising, '
        'within 20% of 52W high. Score +4.</li>'
        '<li><strong>Stage 1 — Base</strong>: Price near 200 DMA, MAs flat. Accumulation phase. Score 0.</li>'
        '<li><strong>Stage 3 — Distribution ⚠</strong>: Near highs but SMA50 flattening, ATR expanding. Score −5.</li>'
        '<li><strong>Stage 4 — Decline ❌</strong>: Price &lt; SMA50 &lt; SMA200, both MAs falling. Score −8.</li>'
        '</ul>'
        '<div class="formula">SMA50/200 · 10-day slope · 52W high dist · Vol ratio · ATR expansion</div>'
        '</div>'

        '</div>'  # end meth-grid section 2

        # ── Section 3: Signals (F&O · Insider · Events) ───────────────────
        '<div class="meth-grid" style="margin-top:8px">'
        '<div class="meth-section-hdr">3 · Signals Column (F&amp;O · Insider · Events)</div>'

        '<div class="meth-card">'
        '<div class="meth-card-title"><div class="meth-icon">SG</div>Reading the Signals Button</div>'
        '<p>Each stock row has a compact <strong>Signals</strong> button showing three coloured dots. '
        'Click to expand a popup with the full detail for each signal type. Click anywhere else to close.</p>'
        '<div style="margin-top:10px">'
        '<div class="meth-signal-row"><span class="meth-dot" style="background:#16a34a"></span><strong style="color:#16a34a">Green</strong> — Bullish signal (F&amp;O bull, insider buy, bullish event)</div>'
        '<div class="meth-signal-row"><span class="meth-dot" style="background:#dc2626"></span><strong style="color:#dc2626">Red</strong> — Bearish signal (F&amp;O bear, insider sell/pledge)</div>'
        '<div class="meth-signal-row"><span class="meth-dot" style="background:#94a3b8"></span><strong style="color:#64748b">Grey</strong> — Neutral / mixed signal</div>'
        '<div class="meth-signal-row"><span class="meth-dot" style="background:#2563eb"></span><strong style="color:#2563eb">Blue</strong> — Upcoming corporate event</div>'
        '<div class="meth-signal-row"><span class="meth-dot" style="background:#e2e8f0"></span><strong style="color:#94a3b8">Light</strong> — No data for this signal type</div>'
        '</div>'
        '</div>'

        '<div class="meth-card">'
        '<div class="meth-card-title"><div class="meth-icon">F&O</div>F&amp;O Signals</div>'
        '<p>Derived from NSE Futures &amp; Options data. '
        'The Put/Call Ratio (PCR) and Open Interest (OI) trend identify smart-money positioning. '
        'An expanding OI with rising price confirms a strong trend; falling OI on a rally is a warning.</p>'
        '<ul style="font-size:12px;color:var(--muted);margin:6px 0 0 16px;line-height:1.8">'
        '<li><strong>BULL</strong>: PCR &gt; 1.2 or OI trending up with price rise</li>'
        '<li><strong>MILD_BULL / MILD_BEAR</strong>: Mixed OI signals</li>'
        '<li><strong>BEAR</strong>: PCR &lt; 0.7 or OI building on price decline</li>'
        '</ul>'
        '<div class="formula">Score bonus: +2 (BULL), +1 (MILD_BULL), −1 (MILD_BEAR), −3 (BEAR)</div>'
        '</div>'

        '<div class="meth-card">'
        '<div class="meth-card-title"><div class="meth-icon">IN</div>Insider Alerts</div>'
        '<p>Monitors SEBI bulk/block deal disclosures and promoter shareholding changes. '
        'Promoter buying at market price is one of the strongest fundamental signals; '
        'promoter pledging or large block selling flags elevated risk.</p>'
        '<ul style="font-size:12px;color:var(--muted);margin:6px 0 0 16px;line-height:1.8">'
        '<li><strong>PROMOTER_BUYING</strong>: +6 score · <strong>INSIDER_BUY</strong>: +4</li>'
        '<li><strong>BULK_DEAL_BUY</strong>: +3 · <strong>BULK_DEAL_SELL</strong>: −3</li>'
        '<li><strong>PROMOTER_SELLING</strong>: −4 · <strong>PROMOTER_PLEDGE</strong>: −5</li>'
        '</ul>'
        '<div class="formula">Lookback: 90 days · Source: SEBI disclosures via NSE API</div>'
        '</div>'

        '<div class="meth-card">'
        '<div class="meth-card-title"><div class="meth-icon">EV</div>Corporate Events</div>'
        '<p>Surfaces the next material event (earnings, dividend, board meeting, AGM, split, bonus) '
        'from the NSE corporate actions calendar. Urgency is colour-coded by days remaining.</p>'
        '<ul style="font-size:12px;color:var(--muted);margin:6px 0 0 16px;line-height:1.8">'
        '<li>🔴 <strong>≤ 3 days</strong>: Imminent — animated pulse badge</li>'
        '<li>🟡 <strong>4–7 days</strong>: This week — amber badge</li>'
        '<li>🔵 <strong>8–30 days</strong>: Upcoming — blue badge</li>'
        '<li>⚪ <strong>&gt; 30 days</strong>: Far out — grey badge</li>'
        '</ul>'
        '<div class="formula">Score bonus: +3 (results ≤7d), +1 (dividend), −1 (AGM/EGM)</div>'
        '</div>'

        '</div>'  # end meth-grid section 3

        # ── Section 4: Seasonal Analysis ──────────────────────────────────
        '<div class="meth-grid" style="margin-top:8px">'
        '<div class="meth-section-hdr">4 · Sectoral Seasonality — How to Read the Heat Calendar</div>'

        '<div class="meth-card" style="grid-column:1/-1">'
        '<div class="meth-card-title"><div class="meth-icon">B3</div>Sectoral Heat Calendar (7-Year Monthly Returns)</div>'
        '<p>The heat calendar shows the <strong>average return</strong> for each NSE sector index in every calendar month, '
        'computed over the last 7 years of NSE index data. '
        'It answers: <em>"Historically, has this sector tended to go up or down in this month?"</em></p>'

        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:12px">'

        '<div>'
        '<div style="font-size:12px;font-weight:700;color:var(--primary);margin-bottom:6px">Reading the Colours</div>'
        '<div class="meth-heat-legend">'
        '<div class="meth-heat-swatch" style="background:#14532d;color:#fff">&gt; +5%</div>'
        '<div class="meth-heat-swatch" style="background:#16a34a;color:#fff">+2% → +5%</div>'
        '<div class="meth-heat-swatch" style="background:#4ade80;color:#1e293b">+1% → +2%</div>'
        '<div class="meth-heat-swatch" style="background:#bbf7d0;color:#1e293b">0% → +1%</div>'
        '<div class="meth-heat-swatch" style="background:#fde68a;color:#1e293b">−1% → 0%</div>'
        '<div class="meth-heat-swatch" style="background:#fca5a5;color:#1e293b">−1% → −2%</div>'
        '<div class="meth-heat-swatch" style="background:#f87171;color:#1e293b">−2% → −5%</div>'
        '<div class="meth-heat-swatch" style="background:#dc2626;color:#fff">−5% → −10%</div>'
        '<div class="meth-heat-swatch" style="background:#b91c1c;color:#fff">&lt; −10%</div>'
        '</div>'
        '<p style="font-size:11px;color:var(--muted);margin-top:6px">'
        'Arrows inside each cell: ↑ avg &gt; +1% · → flat (−0.5% to +1%) · ↓ avg &lt; −0.5%.<br>'
        'The <strong>current month row</strong> is highlighted in blue with a ◀ marker.'
        '</p>'
        '</div>'

        '<div>'
        '<div style="font-size:12px;font-weight:700;color:var(--primary);margin-bottom:6px">Signals Derived</div>'
        '<p style="font-size:12px;color:var(--muted);line-height:1.7">'
        'Each sector is tagged <strong>TAILWIND</strong>, <strong>HEADWIND</strong>, or <strong>NEUTRAL</strong> '
        'for the current month based on its historical average return:</p>'
        '<ul style="font-size:12px;color:var(--muted);margin:4px 0 0 16px;line-height:1.8">'
        '<li><strong style="color:#16a34a">TAILWIND</strong>: avg monthly return &gt; +2% over ≥5 years of data</li>'
        '<li><strong style="color:#dc2626">HEADWIND</strong>: avg monthly return &lt; −1%</li>'
        '<li><strong style="color:#64748b">NEUTRAL</strong>: between −1% and +2%, or fewer than 5 observations</li>'
        '</ul>'
        '<p style="font-size:11px;color:var(--muted);margin-top:8px">'
        'These signals appear as coloured tags on sector headers in the Sector Rotation tab '
        'and as a summary in the Overview.</p>'
        '</div>'

        '</div>'  # end 2-col grid

        '<div style="margin-top:14px;padding:10px 14px;background:#fef9c3;border-radius:6px;border-left:3px solid #ca8a04">'
        '<div style="font-size:12px;font-weight:700;color:#854d0e;margin-bottom:4px">⚠ Interpretation Guidance</div>'
        '<p style="font-size:12px;color:#92400e;line-height:1.6;margin:0">'
        'Seasonal patterns are <strong>probabilistic, not deterministic</strong>. '
        'A TAILWIND month improves the base rate; it does not guarantee a positive return. '
        'Always cross-reference with the Rotation Score and the current market regime (displayed in the top banner). '
        'A HEADWIND season in a strong uptrend sector is less of a deterrent than in a weakening one. '
        'Use seasonality as a tie-breaker, not the primary filter.'
        '</p>'
        '</div>'

        '</div>'  # end full-width meth-card

        '</div>'  # end meth-grid section 4

        # ── Section 5: All Indices Tab ─────────────────────────────────────
        '<div class="meth-grid" style="margin-top:8px">'
        '<div class="meth-section-hdr">5 · All Indices Tab</div>'

        '<div class="meth-card">'
        '<div class="meth-card-title"><div class="meth-icon">IX</div>136 NSE Indices — Coverage &amp; Layout</div>'
        '<p>Covers all NSE index series with performance metrics computed from the same index data feed. '
        'Use the category filter chips to narrow focus, and the search box to jump to a specific index.</p>'
        '<ul style="font-size:12px;color:var(--muted);margin:6px 0 0 16px;line-height:1.8">'
        '<li><strong>Broad Market</strong>: Nifty 50, 100, 200, 500 and multi-cap composites</li>'
        '<li><strong>Sector</strong>: 25 NSE sector sub-indices (Auto, Bank, IT, Metal…)</li>'
        '<li><strong>Thematic</strong>: EV, Defence, Housing, Railways, Tourism…</li>'
        '<li><strong>Strategy / Factor</strong>: Alpha, Low Vol, Momentum, Quality, Value…</li>'
        '<li><strong>Size</strong>: Mid, Small, Micro-cap series and derivatives</li>'
        '<li><strong>Fixed Income</strong>: Bharat Bond ETF indices and G-Sec series</li>'
        '</ul>'
        '<div class="formula">Columns: 5D · 1M · 3M · 6M return · RS vs Nifty 500 (1M)<br>'
        'Rotation Score · 52W High · 52W Low · Drawdown from 52W High<br>'
        'All columns sortable — click any header to rank</div>'
        '</div>'

        '<div class="meth-card">'
        '<div class="meth-card-title"><div class="meth-icon">DD</div>Drawdown from 52W High</div>'
        '<p>The <strong>DD%</strong> column shows how far the index is currently trading below its 52-week high. '
        'This is the most direct measure of whether an index has corrected or is still near peak levels.</p>'
        '<ul style="font-size:12px;color:var(--muted);margin:6px 0 0 16px;line-height:1.8">'
        '<li><strong>0% to −5%</strong>: Near all-time / 52W high — strong trend</li>'
        '<li><strong>−5% to −15%</strong>: Healthy pullback — possible buy zone</li>'
        '<li><strong>−15% to −30%</strong>: Correction — wait for base or reversal signal</li>'
        '<li><strong>&gt; −30%</strong>: Deep decline — avoid unless very strong catalyst</li>'
        '</ul>'
        '</div>'

        '</div>'  # end meth-grid section 5

        f'<div class="card" style="margin-top:20px">'
        f'<div class="card-title">Disclaimer</div>'
        f'<p style="font-size:13px;color:var(--muted);line-height:1.7">'
        f'{html_mod.escape(REPORT_DISCLAIMER)} '
        f'This material must not be replicated or used with any intent of trading or recommendation. '
        f'Narratives are AI-assisted analyses grounded in the displayed data and are subject to all limitations thereof.'
        f'</p></div>'
    )

    legal_disclaimer_html = (
        '<div class="legal-disclaimer">'
        '<h2>Full Disclaimer &amp; Use Restrictions</h2>'
        f'<p class="legal-alert">{html_mod.escape(PRINT_FOOTER_DISCLAIMER)}</p>'
        f'<p>{html_mod.escape(FULL_LEGAL_DISCLAIMER)}</p>'
        '<p><strong>Do not replicate, redistribute, automate, or use this report for trading, recommendations, advisory, '
        'portfolio management, or any financial decision-making workflow.</strong></p>'
        '</div>'
    )

    # ---- ASSEMBLE FULL HTML ----
    chart_data_script = (
        f'<script>'
        f'window._rotLabels={json.dumps(rot_labels)};'
        f'window._rotScores={json.dumps(rot_scores)};'
        f'</script>'
    )

    html_parts = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>NSE Sector Rotation Report — {gen_date}</title>',
        '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>',
        f'<style>{_CSS}</style>',
        '</head>',
        '<body>',
        f'<div class="print-page-header"><span>{html_mod.escape(AGENT_BRAND)}</span><span>NSE Sector Rotation Report</span></div>',
        f'<div class="print-page-footer">{html_mod.escape(PRINT_FOOTER_DISCLAIMER)}</div>',
        # Header
        '<header class="site-hdr">',
        '<div class="hdr-inner">',
        '<div class="hdr-brand">',
        logo_html,
        '<div class="hdr-copy">',
        f'<div class="hdr-kicker">{html_mod.escape(AGENT_BRAND)}</div>',
        '<div class="hdr-title">NSE Sector Rotation Report</div>',
        '</div>',
        '</div>',
        '<div class="hdr-meta">',
        f'<span class="mbadge mbadge-date">Report Date: {gen_date}</span>',
        f'<span class="mbadge mbadge-data">Data as of: {html_mod.escape(str(data_date))}</span>',
        '</div></div>',
        '</header>',
        f'<div class="disc"><strong>Disclaimer:</strong> {html_mod.escape(REPORT_DISCLAIMER)}</div>',
        f'<div class="content" style="padding-top:12px;padding-bottom:0">{_regime_banner}{_cycle_banner}{_flow_banner}{_breadth_strip}{_mcclellan_strip}</div>' if (_regime_banner or _cycle_banner or _flow_banner or _breadth_strip or _mcclellan_strip) else '',
        # PG: macro context banner (P1-6)
        f'<div class="content" style="padding:6px 20px;font-size:11px;color:#6c6f85;background:#f8f9fa;border-bottom:1px solid #e9ecef">🌐 {html_mod.escape(macro_context)}</div>' if macro_context else '',
        brief_html,
        # Nav
        '<nav class="main-nav"><div class="nav-inner">',
        '<button class="nav-btn" data-tab="overview">Overview</button>',
        '<button class="nav-btn" data-tab="rotation">Sector Rotation</button>',
        '<button class="nav-btn" data-tab="candidates">Investment Candidates</button>',
        '<button class="nav-btn" data-tab="screeners">Screeners</button>',
        '<button class="nav-btn" data-tab="resilience">Peak Resilience</button>',
        '<button class="nav-btn" data-tab="indices">All Indices</button>',
        '<button class="nav-btn" data-tab="methodology">Methodology</button>',
        '<button class="nav-btn" data-tab="disclaimer">Disclaimer</button>',
        '</div></nav>',
        # Content
        '<main class="content">',
        f'<section id="tab-overview" class="tab-pane">{overview_html}</section>',
        f'<section id="tab-rotation" class="tab-pane">{rotation_html}</section>',
        f'<section id="tab-candidates" class="tab-pane">{candidates_html}</section>',
        f'<section id="tab-screeners" class="tab-pane">{_build_screener_tab(candidates)}</section>',
        f'<section id="tab-resilience" class="tab-pane">{resilience_html}</section>',
        f'<section id="tab-indices" class="tab-pane">{build_indices_tab_html(all_index_metrics)}</section>',
        f'<section id="tab-methodology" class="tab-pane">{methodology_html}</section>',
        f'<section id="tab-disclaimer" class="tab-pane">{legal_disclaimer_html}</section>',
        '</main>',
        chart_data_script,
        f'<script>{_JS}</script>',
        '</body>',
        '</html>',
    ]
    return "\n".join(html_parts)


def export_pdf_from_html(html_path: Path, pdf_path: Path) -> bool:
    """Export the interactive HTML report to PDF with Playwright or local Chrome."""
    def _write_pdf_html_copy(src: Path, tmp_dir: Path) -> Path:
        text = src.read_text(encoding="utf-8")
        text = re.sub(r"<script\b[^>]*>.*?</script>", "", text, flags=re.IGNORECASE | re.DOTALL)
        out = tmp_dir / src.name
        out.write_text(text, encoding="utf-8")
        return out

    def _pdf_header_footer_templates() -> tuple[str, str]:
        header_template = (
            '<div style="font-family:Arial,sans-serif;font-size:8px;width:100%;'
            'padding:0 8mm;color:#1e3a5f;font-weight:700;text-transform:uppercase;'
            'display:flex;justify-content:space-between;border-bottom:1px solid #cbd5e1;">'
            f'<span>{html_mod.escape(AGENT_BRAND)}</span>'
            '<span>NSE Sector Rotation Report</span></div>'
        )
        footer_template = (
            '<div style="font-family:Arial,sans-serif;font-size:6.5px;width:100%;'
            'padding:0 8mm;color:#475569;line-height:1.25;display:flex;gap:8px;'
            'border-top:1px solid #cbd5e1;">'
            f'<span style="flex:1;">{html_mod.escape(PRINT_FOOTER_DISCLAIMER)}</span>'
            '<span><span class="pageNumber"></span>/<span class="totalPages"></span></span></div>'
        )
        return header_template, footer_template

    playwright_error = ""
    with tempfile.TemporaryDirectory() as tmp_pdf_dir:
        pdf_html_path = _write_pdf_html_copy(html_path, Path(tmp_pdf_dir))
        try:
            from playwright.sync_api import sync_playwright
            header_template, footer_template = _pdf_header_footer_templates()
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width": 1440, "height": 1200})
                page.goto(pdf_html_path.resolve().as_uri(), wait_until="domcontentloaded")
                page.emulate_media(media="print")
                page.pdf(
                    path=str(pdf_path),
                    format="A4",
                    display_header_footer=True,
                    header_template=header_template,
                    footer_template=footer_template,
                    print_background=True,
                    prefer_css_page_size=True,
                    margin={"top": "12mm", "right": "7mm", "bottom": "14mm", "left": "7mm"},
                )
                browser.close()
            return True
        except Exception as exc:
            playwright_error = f"{type(exc).__name__}: {exc}"

        chrome_candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        ]
        chrome = next((p for p in chrome_candidates if p.exists()), None)
        if chrome:
            try:
                pdf_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_profile = Path(tmp_pdf_dir) / "chrome-profile"
                proc = subprocess.Popen(
                    [
                        str(chrome),
                        "--headless",
                        "--disable-gpu",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--disable-extensions",
                        "--disable-background-networking",
                        "--allow-file-access-from-files",
                        f"--user-data-dir={tmp_profile}",
                        "--no-pdf-header-footer",
                        "--print-to-pdf-no-header",
                        f"--print-to-pdf={pdf_path}",
                        pdf_html_path.resolve().as_uri(),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                stable_count = 0
                last_size = -1
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    if proc.poll() is not None:
                        break
                    if pdf_path.exists():
                        size = pdf_path.stat().st_size
                        if size > 0 and size == last_size:
                            stable_count += 1
                            if stable_count >= 3:
                                proc.terminate()
                                try:
                                    proc.wait(timeout=5)
                                except subprocess.TimeoutExpired:
                                    proc.kill()
                                return True
                        else:
                            stable_count = 0
                            last_size = size
                    time.sleep(1)
                stdout, stderr = proc.communicate(timeout=5) if proc.poll() is not None else ("", "")
                if pdf_path.exists() and pdf_path.stat().st_size > 0:
                    if proc.poll() is None:
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                    return True
                if proc.poll() is None:
                    proc.kill()
                chrome_error = (stderr or stdout or "").strip()
                print(f"PDF export skipped: Chrome headless failed. {chrome_error}")
                return False
            except Exception as exc:
                print(f"PDF export skipped ({type(exc).__name__}: {exc}).")
                return False

    print(
        "PDF export skipped: no PDF renderer is available. "
        f"Playwright status: {playwright_error or 'not installed'}. "
        "Install with `python3 -m pip install playwright` and `python3 -m playwright install chromium`, "
        "or install Google Chrome."
    )
    return False


# ===== REPORT GENERATION =====

def generate_report(top_n_sectors: int = 6, top_n_per_sector: int = 8) -> ReportPaths:
    analysis, source_file = load_comprehensive_analysis()
    sector_rank = load_index_rotation()
    all_index_metrics = load_all_index_metrics()
    _macro_sig = pd.DataFrame()

    # Enrich sector rankings with macro tailwind scores (P1-6)
    try:
        from fetch_macro_proxies import generate_macro_signals, enrich_sector_rank_with_tailwinds, macro_context_for_llm
        _macro_sig, _macro_tw = generate_macro_signals()
        sector_rank = enrich_sector_rank_with_tailwinds(sector_rank)
        _macro_ctx = macro_context_for_llm(_macro_sig)
        print(f"  Macro: {len(_macro_sig)} indicators, {len(_macro_tw)} sector tailwinds computed.")
    except Exception as exc:
        print(f"  Macro proxy signals skipped ({exc}).")
        sector_rank["MACRO_TAILWIND"] = 0.0
        sector_rank["MACRO_DETAIL"] = ""
        _macro_ctx = ""

    # Detect market regime (P1-1) before sector selection so B5 can cross-check it.
    regime_info: dict = {}
    regime_name = "ROTATION"
    try:
        from regime_detector import detect_regime
        regime_info = detect_regime()
        regime_name = regime_info.get("current_regime", "ROTATION")
        print(f"  Regime: {regime_name} (confidence {regime_info.get('confidence', 0):.0%}, {regime_info.get('regime_duration_days', 1)}d)")
    except Exception as exc:
        print(f"  Regime detection skipped ({exc}); using ROTATION default.")

    # Economic cycle positioning (B5/D3): adjust sector ranking before taking top N.
    cycle_info: dict = {}
    try:
        from economic_cycle import apply_cycle_to_sectors, detect_economic_cycle_phase
        cycle_info = detect_economic_cycle_phase(_macro_sig, market_regime=regime_name)
        sector_rank = apply_cycle_to_sectors(sector_rank, cycle_info)
        print(
            "  Economic cycle: "
            f"{cycle_info.get('cycle_phase', 'UNKNOWN')} "
            f"({cycle_info.get('confidence', 0):.0%}, {cycle_info.get('regime_cycle_alignment', 'MIXED')})"
        )
    except Exception as exc:
        print(f"  Economic cycle detection skipped ({exc}).")
        sector_rank["CYCLE_PHASE"] = "UNKNOWN"
        sector_rank["CYCLE_TAG"] = "CYCLE_NEUTRAL"
        sector_rank["CYCLE_ADJUSTMENT"] = 0

    # Market breadth oscillator (C1): refresh local McClellan history for the HTML strip.
    try:
        from market_breadth import generate_breadth_history
        _breadth_history = generate_breadth_history()
        if not _breadth_history.empty:
            _latest_breadth = _breadth_history.iloc[-1]
            print(
                "  McClellan: "
                f"{float(_latest_breadth.get('oscillator', 0)):+.1f} "
                f"{_latest_breadth.get('signal', 'NEUTRAL')} "
                f"({_latest_breadth.get('divergence', 'NONE')})"
            )
    except Exception as exc:
        print(f"  McClellan breadth skipped ({exc}).")

    # Sectoral seasonality (B3): tag each sector with its seasonal signal.
    _seasonal_calendar_html = ""
    try:
        from seasonal_heat_calendar import load_seasonal_calendar
        _, _sheat, _seasonal_calendar_html, _seasonal_signals = load_seasonal_calendar(ROTATING_INDEXES)
        sector_rank["SEASONAL_SIGNAL"] = sector_rank["SECTOR_NAME"].map(_seasonal_signals).fillna("NEUTRAL")
        print(
            "  Seasonal signals: "
            + ", ".join(f"{s}={v}" for s, v in sorted(_seasonal_signals.items()) if v != "NEUTRAL")
        )
    except Exception as exc:
        print(f"  Seasonal calendar skipped ({exc}).")
        sector_rank["SEASONAL_SIGNAL"] = "NEUTRAL"
        _seasonal_calendar_html = ""

    # Sector breadth divergence (C3): add pct_above_50dma and divergence alerts per sector.
    try:
        from market_breadth import generate_sector_breadth
        _sb = generate_sector_breadth()
        if not _sb.empty:
            _sb_lookup = _sb.set_index("index_name")[["pct_above_50dma", "change_5d", "breadth_signal", "divergence_alert"]]
            _sb_lookup.index = _sb_lookup.index.str.upper()
            sector_rank = sector_rank.merge(
                _sb_lookup.rename(columns={
                    "pct_above_50dma": "BREADTH_PCT50",
                    "change_5d": "BREADTH_CHANGE_5D",
                    "breadth_signal": "BREADTH_SIGNAL",
                    "divergence_alert": "BREADTH_DIVERGENCE",
                }),
                left_on=sector_rank["SYMBOL"].str.upper(),
                right_index=True,
                how="left",
            ).drop(columns="key_0", errors="ignore")
            sector_rank["BREADTH_SIGNAL"] = sector_rank["BREADTH_SIGNAL"].fillna("NO_DATA")
            sector_rank["BREADTH_DIVERGENCE"] = sector_rank["BREADTH_DIVERGENCE"].fillna("NONE")
            divs = sector_rank[sector_rank["BREADTH_DIVERGENCE"] != "NONE"]
            print(
                f"  Sector breadth: {len(_sb)} sectors loaded, "
                + (f"{len(divs)} divergence alert(s): " + ", ".join(f"{r['SECTOR_NAME']}={r['BREADTH_DIVERGENCE']}" for _, r in divs.iterrows()) if not divs.empty else "no divergences")
            )
        else:
            sector_rank["BREADTH_SIGNAL"] = "NO_DATA"
            sector_rank["BREADTH_DIVERGENCE"] = "NONE"
    except Exception as exc:
        print(f"  Sector breadth skipped ({exc}).")
        sector_rank["BREADTH_SIGNAL"] = "NO_DATA"
        sector_rank["BREADTH_DIVERGENCE"] = "NONE"

    sector_rank = sector_rank.head(top_n_sectors)
    rotating_sectors = list(sector_rank["SECTOR_NAME"].drop_duplicates())
    rotating_universe = build_rotating_sector_universe(analysis, rotating_sectors)
    candidates = build_sector_stock_table(analysis, rotating_sectors, top_n_per_sector=top_n_per_sector)

    with tempfile.TemporaryDirectory() as tmp:
        stock_csv = Path(tmp) / "stock_history.csv"
        history = None
        export_symbols = sorted(set(candidates["SYMBOL"].tolist()) | set(rotating_universe["SYMBOL"].tolist()))
        if export_symbols and export_stock_cache(export_symbols, stock_csv):
            history = pd.read_csv(stock_csv)
        candidates = enrich_with_patterns(candidates, history)
        # A1: Stage analysis enrichment (must run before rank_stock_candidates)
        try:
            from screeners import enrich_with_stage
            candidates = enrich_with_stage(candidates, history)
            _stage_counts = candidates["STAGE"].value_counts().to_dict()
            print(f"  Stage analysis: S2={_stage_counts.get('STAGE_2',0)} S1={_stage_counts.get('STAGE_1',0)} S3={_stage_counts.get('STAGE_3',0)} S4={_stage_counts.get('STAGE_4',0)}")
        except Exception as exc:
            print(f"  Stage analysis skipped ({exc}).")
            candidates["STAGE"] = "UNKNOWN"
            for _sc in ["SMA_50", "SMA_200", "SMA_50_SLOPE", "SMA_200_SLOPE", "DIST_FROM_52W_HIGH_PCT", "VOL_RATIO"]:
                candidates[_sc] = None
        candidates = rank_stock_candidates(candidates)
        peak_resilience = enrich_with_peak_resilience(rotating_universe, history)
        peak_resilience = rank_peak_resilience_stocks(peak_resilience)

    # Enrich with F&O derivative signals (P1-2)
    try:
        from fetch_fno_data import enrich_with_fno_signals
        candidates = enrich_with_fno_signals(candidates)
    except Exception as exc:
        print(f"  F&O signal enrichment skipped ({exc}). Filling with None.")
        for _fc in ["FNO_PCR", "FNO_OI_CHANGE_5D", "FNO_BUILDUP", "FNO_MAX_PAIN", "FNO_SIGNAL"]:
            candidates[_fc] = None

    # Enrich with insider/promoter alerts (P1-4)
    try:
        from fetch_insider_alerts import enrich_with_insider_alerts
        candidates = enrich_with_insider_alerts(candidates)
    except Exception as exc:
        print(f"  Insider alert enrichment skipped ({exc}). Filling with None.")
        for _ic in ["INSIDER_ALERT", "INSIDER_SCORE", "INSIDER_DETAIL"]:
            candidates[_ic] = None

    # Enrich with corporate event alerts (E4)
    try:
        from fetch_corporate_events import enrich_with_events
        candidates = enrich_with_events(candidates)
    except Exception as exc:
        print(f"  Event enrichment skipped ({exc}).")
        for _ec in ["NEXT_EVENT", "NEXT_EVENT_DATE", "NEXT_EVENT_DAYS", "EVENT_DETAIL", "EVENT_SCORE_DELTA"]:
            candidates[_ec] = ""

    # Apply stock-level cycle positioning (D3) after all candidate enrichment.
    if cycle_info:
        try:
            from economic_cycle import apply_cycle_to_candidates
            candidates = apply_cycle_to_candidates(candidates, cycle_info)
        except Exception as exc:
            print(f"  Stock cycle positioning skipped ({exc}).")

    generated_at = datetime.now()
    paths = report_output_paths(generated_at)

    # Fetch FII/DII flow signals (P1-3)
    flow_info: dict = {}
    try:
        from fetch_fii_dii_flows import load_flow_signals
        flow_info = load_flow_signals()
        _fsig = flow_info.get("flow_signal", "NO_DATA")
        print(f"  FII/DII flow: {_fsig} (FII 5D: ₹{flow_info.get('fii_net_5d', 0):+,.0f} Cr)")
        # Tag each candidate row with the market-wide flow signal for signal log
        candidates["_FII_FLOW_SIGNAL"] = _fsig
    except Exception as exc:
        print(f"  FII/DII flow signals skipped ({exc}).")
        candidates["_FII_FLOW_SIGNAL"] = ""

    # Log signals for outcome tracking (P0-1)
    _log_signals(candidates, generated_at, regime=regime_name)

    # Load rich fundamental data (P&L, quarterly, ratios) for all candidates
    candidate_symbols = candidates["SYMBOL"].dropna().tolist() if "SYMBOL" in candidates.columns else []
    fund_details = _load_fundamental_details(candidate_symbols)

    # Generate narratives (LLM or rule-based fallback)
    narratives = generate_narratives(sector_rank, candidates, fund_details=fund_details)
    try:
        from market_breadth import load_breadth_history
        _brief_breadth = load_breadth_history()
    except Exception:
        _brief_breadth = pd.DataFrame()
    narratives["market_brief"] = generate_market_brief(
        sector_rank,
        candidates,
        regime_info=regime_info,
        cycle_info=cycle_info,
        flow_info=flow_info,
        macro_context=_macro_ctx,
        breadth_history=_brief_breadth,
    )

    md = render_markdown(sector_rank, candidates, peak_resilience, source_file, generated_at, narratives=narratives)
    html_text = render_html_interactive(sector_rank, candidates, peak_resilience, source_file, generated_at, narratives, regime_info=regime_info, flow_info=flow_info, cycle_info=cycle_info, macro_context=_macro_ctx, seasonal_calendar_html=_seasonal_calendar_html, all_index_metrics=all_index_metrics)
    for path, text in [
        (paths.markdown, md),
        (paths.html, html_text),
        (paths.latest_markdown, md),
        (paths.latest_html, html_text),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(f"Wrote {paths.markdown}")
    print(f"Wrote {paths.html}")
    print(f"Wrote {paths.latest_markdown}")
    print(f"Wrote {paths.latest_html}")
    if export_pdf_from_html(paths.html, paths.pdf):
        paths.latest_pdf.parent.mkdir(parents=True, exist_ok=True)
        paths.latest_pdf.write_bytes(paths.pdf.read_bytes())
        print(f"Wrote {paths.pdf}")
        print(f"Wrote {paths.latest_pdf}")
    return paths


def main() -> None:
    generate_report()


if __name__ == "__main__":
    main()
