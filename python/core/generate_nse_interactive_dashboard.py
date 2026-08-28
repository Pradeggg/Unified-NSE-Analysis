#!/usr/bin/env python3
"""
Generate an HTML interactive-style dashboard from the Python NSE analysis outputs.

This is a Python analogue of the R-based dashboard writer in
`organized/core_scripts/fixed_nse_universe_analysis.R`.

Input:
- Latest `reports/comprehensive_nse_enhanced_*.csv` (stocks universe results)
- `nse_analysis.db` (authoritative **as of** date = max analysis_date across tables;
  index rows from `index_analysis`)
- `data/fundamental_scores_database.csv` (scores + pillars; after R refresh may include `PROFIT_YOY_PCT`, `PE_TTM`, etc.)
- Optional `data/fundamental_quarterly_ratios.csv` (extra or override columns for the fundamentals tab)

Output:
- `reports/NSE_Interactive_Dashboard_<YYYYMMDD>.html` (one file per as-of date; re-run overwrites)
- Embeds rows from SQLite `llm_narratives` for that as-of date (market + any stock narratives present).
  Set `NARRATIVE_API_BASE` if the narrative API is not on `http://127.0.0.1:8765`.
"""

from __future__ import annotations

import html
import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional, Tuple

import pandas as pd


# Project root is two levels up from this file (../..)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = PROJECT_ROOT / "nse_analysis.db"

# Optional quarterly ratios file — copy from example and fill from your data vendor / exports
FUND_RATIOS_CSV = DATA_DIR / "fundamental_quarterly_ratios.csv"


@dataclass
class DashboardData:
    """as_of_date = latest snapshot in SQLite (preferred); csv_snapshot_date = TIMESTAMP in universe CSV."""

    as_of_date: date
    csv_snapshot_date: date
    stocks: pd.DataFrame
    indexes: pd.DataFrame
    avg_fund_score: Optional[float] = None
    high_fund_count: Optional[int] = None
    total_with_fund: Optional[int] = None
    # From llm_narratives (SQLite) at as_of_date — embedded into HTML for offline viewing
    market_narrative_embed: Optional[dict[str, Any]] = None
    stock_narratives_embed: dict[str, dict[str, Any]] = field(default_factory=dict)


def _find_latest_stocks_csv() -> Path:
    """
    Find the most recent `comprehensive_nse_enhanced_*.csv` in reports/.
    """
    candidates = sorted(
        REPORTS_DIR.glob("comprehensive_nse_enhanced_*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError("No comprehensive_nse_enhanced_*.csv found in reports/")
    return candidates[0]


def _load_stocks_and_latest_date(csv_path: Path) -> Tuple[pd.DataFrame, date]:
    df = pd.read_csv(csv_path, low_memory=False)
    if "SYMBOL" not in df.columns or "TECHNICAL_SCORE" not in df.columns:
        raise ValueError(f"{csv_path} does not look like the expected analysis CSV")

    # Try to infer latest_date from TIMESTAMP if present; else fallback to today
    latest_date: date
    if "TIMESTAMP" in df.columns:
        ts = pd.to_datetime(df["TIMESTAMP"], errors="coerce").dt.date
        df["TIMESTAMP"] = ts
        if ts.notna().any():
            latest_date = ts.max()
        else:
            latest_date = date.today()
    else:
        latest_date = date.today()

    # Basic ordering by technical score descending
    df = df.sort_values("TECHNICAL_SCORE", ascending=False)
    return df, latest_date


def _load_index_summary(latest_date: date) -> pd.DataFrame:
    """
    Load index analysis for the given date from the SQLite DB.
    Falls back to the most recent date if exact match is unavailable.
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} not found; cannot load index analysis.")

    conn = sqlite3.connect(DB_PATH)
    try:
        idx = pd.read_sql_query("SELECT * FROM index_analysis", conn)
    finally:
        conn.close()

    if idx.empty:
        raise ValueError("index_analysis table is empty.")

    idx["analysis_date"] = pd.to_datetime(idx["analysis_date"]).dt.date
    # Try exact date first
    same_day = idx[idx["analysis_date"] == latest_date]
    if same_day.empty:
        latest_available = idx["analysis_date"].max()
        same_day = idx[idx["analysis_date"] == latest_available]

    # Order indices by TECHNICAL_SCORE descending
    same_day = same_day.sort_values("technical_score", ascending=False)
    return same_day


def _load_db_as_of_date() -> Optional[date]:
    """
    Latest analysis_date across SQLite tables (stocks, indices, breadth).
    Used as the dashboard's authoritative 'as of' date when the DB exists.
    """
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    dates: list[date] = []
    try:
        for table in ("stocks_analysis", "index_analysis", "market_breadth"):
            try:
                cur = conn.execute(f"SELECT MAX(analysis_date) FROM {table}")
                row = cur.fetchone()
                if row and row[0] is not None:
                    dates.append(pd.to_datetime(row[0], errors="coerce").date())
            except sqlite3.Error:
                continue
    finally:
        conn.close()
    return max(dates) if dates else None


def _load_llm_narratives_for_date(as_of: date) -> tuple[Optional[dict[str, Any]], dict[str, dict[str, Any]]]:
    """
    Load Ollama narratives from llm_narratives for this analysis_date.
    Returns (market_row_dict_or_none, {SYMBOL_UPPER: {content, ollama_model, updated_at}}).
    """
    if not DB_PATH.exists():
        return None, {}
    ad = as_of.isoformat()[:10]
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    market: Optional[dict[str, Any]] = None
    stocks_map: dict[str, dict[str, Any]] = {}
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='llm_narratives'"
        )
        if cur.fetchone() is None:
            return None, {}
        row = conn.execute(
            """
            SELECT content, ollama_model, updated_at
            FROM llm_narratives
            WHERE narrative_type = 'market' AND analysis_date = ? AND IFNULL(symbol, '') = ''
            LIMIT 1
            """,
            (ad,),
        ).fetchone()
        if row and row["content"]:
            market = {
                "content": str(row["content"]),
                "ollama_model": str(row["ollama_model"] or ""),
                "updated_at": str(row["updated_at"] or ""),
            }
        for r in conn.execute(
            """
            SELECT symbol, content, ollama_model, updated_at
            FROM llm_narratives
            WHERE narrative_type = 'stock' AND analysis_date = ?
            """,
            (ad,),
        ):
            if not r["content"]:
                continue
            sym = str(r["symbol"] or "").strip().upper()
            if not sym:
                continue
            stocks_map[sym] = {
                "content": str(r["content"]),
                "ollama_model": str(r["ollama_model"] or ""),
                "updated_at": str(r["updated_at"] or ""),
            }
    except sqlite3.Error:
        return None, {}
    finally:
        conn.close()
    return market, stocks_map


def _first_existing_column(df: pd.DataFrame, candidates: tuple[str, ...]) -> Optional[str]:
    """Return the first column name in df that matches candidates (case-insensitive)."""
    if df is None or df.empty:
        return None
    cmap = {c.upper(): c for c in df.columns}
    for name in candidates:
        u = name.upper()
        if u in cmap:
            return cmap[u]
    return None


def _normalize_processed_date_for_display(val: object) -> Optional[str]:
    """
    R sometimes wrote processed_date as numeric days since 1970-01-01 (e.g. 20538 → 2026-03-26).
    Prefer ISO strings; map legacy numbers to YYYY-MM-DD for the Fund data column.
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip().strip('"')
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    try:
        n = float(s)
        if 12000 < n < 50000:
            from datetime import date, timedelta

            d = date(1970, 1, 1) + timedelta(days=int(round(n)))
            return d.isoformat()
    except (TypeError, ValueError, OverflowError):
        pass
    return s[:10] if s else None


def _normalize_fund_symbol_column(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    if df is None or df.empty:
        return None
    out = df.copy()
    sym_col = _first_existing_column(out, ("symbol", "SYMBOL", "Symbol"))
    if sym_col is None:
        return None
    if sym_col != "symbol":
        out = out.rename(columns={sym_col: "symbol"})
    out["symbol"] = out["symbol"].astype(str).str.strip().str.upper()
    return out


def _build_fundamentals_json_rows(stocks_df: pd.DataFrame) -> tuple[str, bool, str]:
    """
    Merge universe symbols with fundamental_scores_database.csv and optional
    fundamental_quarterly_ratios.csv. Returns (json_array_string, ratios_file_used, note_for_ui).
    """
    if stocks_df is None or stocks_df.empty or "SYMBOL" not in stocks_df.columns:
        return "[]", False, "No universe symbols."

    def _of(v: object) -> Optional[float]:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        try:
            f = float(v)
            if pd.isna(f):
                return None
            return f
        except (TypeError, ValueError):
            return None

    def _sanitize_yoy_pct(v: object, limit: float = 300.0) -> Optional[float]:
        """Hide absurd YoY% from tiny denominators (R caps CFO/debt at ±200; allow slight headroom)."""
        x = _of(v)
        if x is None:
            return None
        if abs(x) > limit:
            return None
        return x

    base_cols = ["SYMBOL", "COMPANY_NAME"] if "COMPANY_NAME" in stocks_df.columns else ["SYMBOL"]
    base = stocks_df[base_cols].copy()
    if "COMPANY_NAME" not in base.columns:
        base["COMPANY_NAME"] = base["SYMBOL"].astype(str)
    base["_u"] = base["SYMBOL"].astype(str).str.strip().str.upper()

    fund_path = DATA_DIR / "fundamental_scores_database.csv"
    fund_norm: Optional[pd.DataFrame] = None
    if fund_path.exists():
        try:
            raw = pd.read_csv(fund_path, low_memory=False)
            fund_norm = _normalize_fund_symbol_column(raw)
        except Exception:
            fund_norm = None

    ratios_used = False
    ratios_norm: Optional[pd.DataFrame] = None
    if FUND_RATIOS_CSV.exists():
        try:
            raw_r = pd.read_csv(FUND_RATIOS_CSV, low_memory=False)
            ratios_norm = _normalize_fund_symbol_column(raw_r)
            if ratios_norm is not None:
                ratios_used = True
        except Exception:
            ratios_norm = None

    merged = base.copy()
    if fund_norm is not None:
        fx = fund_norm.rename(columns={"symbol": "_u"}).drop_duplicates(subset=["_u"])
        merged = merged.merge(fx, how="left", on="_u")
    if ratios_norm is not None:
        rx = ratios_norm.rename(columns={"symbol": "_u"}).drop_duplicates(subset=["_u"])
        merged = merged.merge(rx, how="left", on="_u", suffixes=("", "_rq"))

    # Resolve optional ratio column names (flexible headers).
    # R pipeline (fn_screener_public_ratios) writes: PROFIT_YOY_PCT, SALES_REPORTED_YOY_PCT, MARGIN_PP_CHANGE,
    # PE_TTM, CFO_YOY_PCT, DEBT_YOY_PCT, RATIOS_PERIOD into fundamental_scores_database.csv when scores are refreshed.
    col_profit_yoy = _first_existing_column(
        merged,
        (
            "PROFIT_YOY_PCT",
            "EPS_GROWTH_YOY",
            "EPS_GROWTH_QOQ",
            "EPS_GROWTH",
            "eps_growth_yoy",
        ),
    )
    col_sales_yoy_rep = _first_existing_column(
        merged,
        ("SALES_REPORTED_YOY_PCT", "SALES_YOY_REPORTED", "REPORTED_SALES_YOY_PCT"),
    )
    col_margin_pp = _first_existing_column(
        merged,
        (
            "MARGIN_PP_CHANGE",
            "NET_MARGIN_PP_CHANGE",
            "PROFIT_MARGIN_GROWTH_YOY",
            "PROFIT_MARGIN_GROWTH",
            "NET_MARGIN_GROWTH_YOY",
            "profit_margin_growth_yoy",
        ),
    )
    col_pe = _first_existing_column(merged, ("PE_TTM", "PE", "P_E", "pe_ttm", "trailing_pe"))
    col_cfo = _first_existing_column(
        merged,
        (
            "CFO_YOY_PCT",
            "CFO_CHANGE_YOY",
            "OCF_CHANGE_YOY",
            "CASHFLOW_CHANGE_YOY",
            "OPERATING_CASHFLOW_CHANGE_YOY",
            "cfo_change_yoy",
        ),
    )
    col_debt = _first_existing_column(
        merged,
        (
            "DEBT_YOY_PCT",
            "DEBT_CHANGE_YOY",
            "NET_DEBT_CHANGE_YOY",
            "TOTAL_DEBT_CHANGE_YOY",
            "debt_change_yoy",
        ),
    )
    col_period = _first_existing_column(merged, ("RATIOS_PERIOD", "RATIO_AS_OF", "QUARTER_END", "FUNDAMENTAL_PERIOD", "period"))

    rows_out: list[dict] = []
    for _, row in merged.iterrows():
        sym = str(row.get("SYMBOL") or "").strip()
        co = str(row.get("COMPANY_NAME") or sym).strip()
        # Fund-data date: prefer ratio scrape period, then fix legacy numeric processed_date
        pdate_s = None
        if col_period and row.get(col_period) is not None and not pd.isna(row.get(col_period)):
            rp = str(row.get(col_period)).strip()
            if re.match(r"^\d{4}-\d{2}-\d{2}", rp):
                pdate_s = rp[:10]
        if pdate_s is None:
            pdate_s = _normalize_processed_date_for_display(row.get("processed_date"))

        rows_out.append(
            {
                "symbol": sym,
                "companyName": co,
                "fundScore": _of(row.get("ENHANCED_FUND_SCORE")),
                "earningsQuality": _of(row.get("EARNINGS_QUALITY")),
                "salesGrowth": _of(row.get("SALES_GROWTH")),
                "financialStrength": _of(row.get("FINANCIAL_STRENGTH")),
                "institutionalBacking": _of(row.get("INSTITUTIONAL_BACKING")),
                "fundDataDate": pdate_s,
                # Reported YoY / ratio fields (main CSV after R refresh, or optional quarterly ratios file)
                "profitYoyPct": _of(row.get(col_profit_yoy)) if col_profit_yoy else None,
                "salesReportedYoyPct": _of(row.get(col_sales_yoy_rep)) if col_sales_yoy_rep else None,
                "marginPpChange": _of(row.get(col_margin_pp)) if col_margin_pp else None,
                "peTtm": _of(row.get(col_pe)) if col_pe else None,
                "cfoChangeYoy": _sanitize_yoy_pct(row.get(col_cfo)) if col_cfo else None,
                "debtChangeYoy": _sanitize_yoy_pct(row.get(col_debt)) if col_debt else None,
                "ratiosPeriod": (
                    str(row.get(col_period))[:32]
                    if col_period and row.get(col_period) is not None and not pd.isna(row.get(col_period))
                    else None
                ),
            }
        )

    note = ""
    if not ratios_used:
        note = (
            "<strong class=\"text-info\">Ratio columns</strong> fill from "
            "<code>data/fundamental_scores_database.csv</code> after re-running the R fundamental job "
            "(columns <code>PROFIT_YOY_PCT</code>, <code>PE_TTM</code>, etc.), "
            "or add optional <code>data/fundamental_quarterly_ratios.csv</code> "
            "(see <code>data/fundamental_quarterly_ratios.example.csv</code>)."
        )
    return json.dumps(rows_out, ensure_ascii=False), ratios_used, note


def _escape(s: str) -> str:
    return html.escape(str(s)) if s is not None else ""


def _render_html(data: DashboardData) -> str:
    """
    Render a simple but informative HTML dashboard using Bootstrap styling.
    """
    as_of_str = data.as_of_date.strftime("%Y-%m-%d")
    csv_snap_str = data.csv_snapshot_date.strftime("%Y-%m-%d")
    csv_differs = data.csv_snapshot_date != data.as_of_date
    generated_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fundamentals_json, fund_ratios_file_loaded, fund_panel_note = _build_fundamentals_json_rows(data.stocks)

    # LLM narratives (embedded from SQLite at dashboard build time); live refresh uses narrative API
    narrative_api_base = os.environ.get("NARRATIVE_API_BASE", "http://127.0.0.1:8765").rstrip("/")
    narrative_api_base_js = json.dumps(narrative_api_base)
    market_narrative_json = json.dumps(data.market_narrative_embed, ensure_ascii=False)
    stock_narratives_json = json.dumps(data.stock_narratives_embed, ensure_ascii=False)
    stock_narrative_count = len(data.stock_narratives_embed)

    # Fundamental score aggregates (if available)
    fund_series = data.stocks.get("ENHANCED_FUND_SCORE")
    avg_fund = (
        float(fund_series.dropna().mean()) if fund_series is not None and fund_series.notna().any() else None
    )
    high_fund = (
        int((fund_series >= 70).sum()) if fund_series is not None and fund_series.notna().any() else None
    )
    total_with_fund = int(fund_series.notna().sum()) if fund_series is not None else 0

    # Trading signal distribution
    signal_counts = data.stocks["TRADING_SIGNAL"].value_counts(dropna=False)
    total = len(data.stocks)

    signal_rows = []
    for sig, cnt in signal_counts.items():
        pct = 0 if total == 0 else round(cnt / total * 100, 1)
        signal_rows.append(
            f"<tr><td>{_escape(sig)}</td><td class='text-end'>{cnt}</td><td class='text-end'>{pct}%</td></tr>"
        )

    # Chart inputs (signals + market cap)
    signal_chart_labels = [str(k) for k in signal_counts.index.tolist()]
    signal_chart_values = [int(v) for v in signal_counts.values.tolist()]

    market_cap_counts = {}
    if "MARKET_CAP_CATEGORY" in data.stocks.columns and not data.stocks.empty:
        market_cap_counts = (
            data.stocks["MARKET_CAP_CATEGORY"]
            .fillna("UNKNOWN")
            .astype(str)
            .value_counts()
            .head(8)
            .to_dict()
        )
    cap_chart_labels = list(market_cap_counts.keys())
    cap_chart_values = [int(v) for v in market_cap_counts.values()]

    # Helper: required numeric fields default to 0 only where appropriate
    def _to_float(val: object, default: float = 0.0) -> float:
        try:
            f = float(val)
            if pd.isna(f):
                return default
            return f
        except Exception:
            return default

    # Optional metrics: missing CSV → JSON null (not 0), so UI shows "—" not fake zeros
    def _optional_float(val: object) -> Optional[float]:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        try:
            f = float(val)
            if pd.isna(f):
                return None
            return f
        except (TypeError, ValueError):
            return None

    # All stocks (for JS-driven table, heatmap, filters)
    top_n = data.stocks.copy() if not data.stocks.empty else data.stocks.copy()
    stocks_js_objects = []
    for _, row in top_n.iterrows():
        symbol = str(row.get("SYMBOL") or "")
        company_name = str(
            row.get("COMPANY_NAME")
            or row.get("LONG_NAME")
            or row.get("SEC_NAME")
            or symbol
        )
        market_cap = str(row.get("MARKET_CAP_CATEGORY") or "")
        stocks_js_objects.append(
            {
                "symbol": symbol,
                "companyName": company_name,
                "marketCap": market_cap,
                "currentPrice": _to_float(row.get("CURRENT_PRICE")),
                "change1D": _to_float(row.get("CHANGE_1D")),
                "change1W": _to_float(row.get("CHANGE_1W")),
                "change1M": _to_float(row.get("CHANGE_1M")),
                "technicalScore": _to_float(row.get("TECHNICAL_SCORE")),
                "rsi": _to_float(row.get("RSI")),
                "relativeStrength": _optional_float(row.get("RELATIVE_STRENGTH")),
                "canSlim": int(row.get("CAN_SLIM_SCORE"))
                if not pd.isna(row.get("CAN_SLIM_SCORE"))
                else 0,
                "minervini": int(row.get("MINERVINI_SCORE"))
                if not pd.isna(row.get("MINERVINI_SCORE"))
                else 0,
                "fundamental": _optional_float(row.get("ENHANCED_FUND_SCORE")),
                "trendSignal": str(row.get("TREND_SIGNAL") or ""),
                "tradingSignal": str(row.get("TRADING_SIGNAL") or ""),
            }
        )

    stocks_js_data = json.dumps(stocks_js_objects, ensure_ascii=False)

    def _index_tech_tier_class(tech: float) -> str:
        """Score pill color tiers (aligned with heat map bands)."""
        if tech >= 65:
            return "index-score-tier-excellent"
        if tech >= 50:
            return "index-score-tier-good"
        if tech >= 40:
            return "index-score-tier-moderate"
        return "index-score-tier-low"

    def _fmt_idx_pct(v: object) -> tuple[str, str]:
        """Return (display string, pos/neg class) for momentum / RS % columns."""
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "—", "index-mini-neutral"
        try:
            x = float(v)
        except (TypeError, ValueError):
            return "—", "index-mini-neutral"
        s = ("+" if x >= 0 else "") + f"{x:.2f}%"
        cls = "index-mini-pos" if x >= 0 else "index-mini-neg"
        return s, cls

    # Index cards (grid layout — matches NSE indices card dashboard style)
    index_cards: list[str] = []
    for _, row in data.indexes.iterrows():
        idx_name = _escape(str(row.get("index_name", "") or ""))

        def _sf(v: object) -> float:
            try:
                f = float(v)
                return 0.0 if pd.isna(f) else f
            except Exception:
                return 0.0

        level_f = _sf(row.get("current_level", 0))
        tech_f = _sf(row.get("technical_score", 0))
        rsi_raw = row.get("rsi")
        if rsi_raw is None or (isinstance(rsi_raw, float) and pd.isna(rsi_raw)):
            rsi_html = "—"
        else:
            rsi_html = f"{float(rsi_raw):.1f}"

        mom_str, mom_cls = _fmt_idx_pct(row.get("momentum_50d"))
        rs_str, rs_cls = _fmt_idx_pct(row.get("relative_strength"))
        tier_cls = _index_tech_tier_class(tech_f)
        trend_raw = str(row.get("trend_signal", "") or "")
        sig_raw = str(row.get("trading_signal", "") or "")
        trend_slug = trend_raw.lower().replace("_", "-")
        sig_slug = sig_raw.lower().replace("_", "-")
        price_display = f"₹{level_f:,.2f}"
        index_cards.append(
            f'<div class="col-6 col-md-4 col-xl-3">'
            f'<div class="index-metric-card h-100">'
            f'<div class="index-metric-card-header d-flex justify-content-between align-items-start gap-2">'
            f'<span class="index-metric-name">{idx_name}</span>'
            f'<span class="index-metric-score-pill {tier_cls}">{tech_f:.0f}</span>'
            f"</div>"
            f'<div class="index-metric-price">{price_display}</div>'
            f'<div class="index-metric-strip d-flex gap-2 justify-content-between mt-2">'
            f'<div class="index-mini-metric"><span class="index-mini-label">RSI</span><span class="index-mini-val">{rsi_html}</span></div>'
            f'<div class="index-mini-metric"><span class="index-mini-label">50D</span><span class="index-mini-val {mom_cls}">{mom_str}</span></div>'
            f'<div class="index-mini-metric"><span class="index-mini-label">RS</span><span class="index-mini-val {rs_cls}">{rs_str}</span></div>'
            f"</div>"
            f'<div class="index-metric-badges d-flex flex-wrap gap-2 align-items-center mt-3">'
            f'<span class="signal-pill signal-{sig_slug}">{_escape(sig_raw.replace("_", " "))}</span>'
            f'<span class="trend-pill trend-{trend_slug}">{_escape(trend_raw.replace("_", " "))}</span>'
            f"</div>"
            f"</div>"
            f"</div>"
        )

    # Universe summary strip (same metrics as reference card dashboard)
    if not data.stocks.empty and "TRADING_SIGNAL" in data.stocks.columns:
        sig_s = data.stocks["TRADING_SIGNAL"].astype(str).str.upper()
        summary_total = len(data.stocks)
        summary_strong_buy = int((sig_s == "STRONG_BUY").sum())
        summary_buy = int((sig_s == "BUY").sum())
        summary_avg_tech = (
            float(data.stocks["TECHNICAL_SCORE"].mean()) if "TECHNICAL_SCORE" in data.stocks.columns else 0.0
        )
    else:
        summary_total = summary_strong_buy = summary_buy = 0
        summary_avg_tech = 0.0

    # Breadth summary counts from trading signals (match R logic)
    bullish_count = neutral_count = bearish_count = 0
    ts = data.stocks.get("TRADING_SIGNAL")
    if ts is not None:
        sig_series = ts.astype(str).str.upper()
        bullish_count = int(sig_series.isin(["BUY", "STRONG_BUY"]).sum())
        neutral_count = int(sig_series.eq("HOLD").sum())
        bearish_count = int(sig_series.isin(["WEAK_HOLD", "SELL", "STRONG_SELL"]).sum())

    # Chart data (embed as JSON literals)
    signal_chart_labels_json = json.dumps(signal_chart_labels)
    signal_chart_values_json = json.dumps(signal_chart_values)
    cap_chart_labels_json = json.dumps(cap_chart_labels)
    cap_chart_values_json = json.dumps(cap_chart_values)

    html_content = f"""<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
  <meta charset="utf-8" />
  <title>NSE Dashboard — as of {as_of_str}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="stylesheet"
        href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
        integrity="sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH"
        crossorigin="anonymous" />
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {{
      --bg-body: #020617;
      --bg-card: rgba(15, 23, 42, 0.92);
      --border-subtle: #1e293b;
      --text-primary: #e5e7eb;
      --text-muted: #9ca3af;
      --accent: #38bdf8;
    }}
    html, body {{
      background: radial-gradient(circle at top left, #1d2b64 0%, #020617 45%, #090909 100%) fixed;
      min-height: 100vh;
      color: var(--text-primary);
    }}
    .card {{
      background: radial-gradient(circle at top left, rgba(56,189,248,.07), #020617) !important;
      border-color: var(--border-subtle) !important;
    }}
    .card-header {{
      background: transparent !important;
      border-bottom-color: var(--border-subtle) !important;
    }}
    .card-title {{
      font-size: .78rem;
      font-weight: 600;
      letter-spacing: .1em;
      text-transform: uppercase;
      color: var(--accent);
      margin-bottom: 0;
    }}
    /* Tables */
    .table {{
      --bs-table-bg: transparent;
      --bs-table-hover-bg: rgba(56,189,248,.06);
      color: var(--text-primary);
    }}
    .table th {{
      color: var(--accent);
      font-size: .69rem;
      letter-spacing: .09em;
      text-transform: uppercase;
      border-bottom-color: var(--border-subtle) !important;
      cursor: pointer;
      user-select: none;
      white-space: nowrap;
      padding: .45rem .5rem;
    }}
    .table td {{
      font-size: .8rem;
      border-bottom-color: var(--border-subtle) !important;
      vertical-align: middle;
      padding: .35rem .5rem;
    }}
    .sort-asc::after  {{ content: " ▲"; color: var(--accent); font-size: .6rem; }}
    .sort-desc::after {{ content: " ▼"; color: var(--accent); font-size: .6rem; }}
    /* Scrollable table: vertical + horizontal so right columns (e.g. Fund) stay reachable on narrow screens */
    .scroll-section {{
      max-height: 540px;
      overflow-x: auto;
      overflow-y: auto;
      scrollbar-width: thin;
      scrollbar-color: #38bdf8 transparent;
    }}
    .scroll-section::-webkit-scrollbar {{ width: 6px; height: 6px; }}
    .scroll-section::-webkit-scrollbar-thumb {{
      background: linear-gradient(180deg, #38bdf8, #6366f1); border-radius: 999px;
    }}
    /* Keep first column visible while scrolling horizontally */
    #stocksTable th:first-child,
    #stocksTable td:first-child,
    #fundamentalsTable th:first-child,
    #fundamentalsTable td:first-child {{
      position: sticky;
      left: 0;
      z-index: 2;
      background: rgba(15, 23, 42, 0.98);
      box-shadow: 4px 0 10px rgba(0, 0, 0, 0.35);
    }}
    #stocksTable thead th:first-child,
    #fundamentalsTable thead th:first-child {{ z-index: 3; }}
    /* Pills */
    .trend-pill, .signal-pill {{
      display: inline-flex; align-items: center; padding: .07rem .5rem;
      border-radius: 999px; font-size: .62rem; font-weight: 500;
      letter-spacing: .06em; text-transform: uppercase;
      border: 1px solid rgba(148,163,184,.26); background: rgba(15,23,42,.85);
      white-space: nowrap;
    }}
    .trend-strong-bullish {{ border-color:rgba(34,197,94,.4); background:radial-gradient(circle at top,rgba(34,197,94,.18),rgba(15,23,42,.9)); color:#bbf7d0; }}
    .trend-bullish        {{ border-color:rgba(52,211,153,.45); background:radial-gradient(circle at top,rgba(52,211,153,.12),rgba(15,23,42,.92)); color:#a7f3d0; }}
    .trend-bearish        {{ border-color:rgba(248,113,113,.45); background:radial-gradient(circle at top,rgba(248,113,113,.16),rgba(15,23,42,.9)); color:#fecaca; }}
    .trend-strong-bearish {{ border-color:rgba(248,113,113,.6); background:radial-gradient(circle at top,rgba(248,113,113,.22),rgba(15,23,42,.9)); color:#fecaca; }}
    .trend-neutral        {{ border-color:rgba(148,163,184,.5); background:radial-gradient(circle at top,rgba(148,163,184,.12),rgba(15,23,42,.9)); color:#e5e7eb; }}
    .signal-strong-buy  {{ border-color:rgba(22,163,74,.7);  background:radial-gradient(circle at top,rgba(22,163,74,.24),rgba(15,23,42,.9));  color:#bbf7d0; }}
    .signal-buy         {{ border-color:rgba(74,222,128,.5); background:radial-gradient(circle at top,rgba(74,222,128,.18),rgba(15,23,42,.9)); color:#dcfce7; }}
    .signal-hold        {{ border-color:rgba(234,179,8,.55); background:radial-gradient(circle at top,rgba(234,179,8,.18),rgba(15,23,42,.9));  color:#fef3c7; }}
    .signal-weak-hold   {{ border-color:rgba(234,179,8,.45); background:radial-gradient(circle at top,rgba(234,179,8,.14),rgba(15,23,42,.9));  color:#fef3c7; }}
    .signal-sell        {{ border-color:rgba(220,38,38,.6);  background:radial-gradient(circle at top,rgba(239,68,68,.2),rgba(15,23,42,.9));   color:#fee2e2; }}
    .signal-strong-sell {{ border-color:rgba(185,28,28,.7);  background:radial-gradient(circle at top,rgba(239,68,68,.28),rgba(15,23,42,.9));  color:#fecaca; }}
    /* Cap tags */
    .tag-cap {{
      border-radius: 999px; padding: .06rem .48rem; font-size: .6rem; font-weight: 500;
      letter-spacing: .08em; text-transform: uppercase; white-space: nowrap;
      border: 1px solid rgba(148,163,184,.36); color: #cbd5f5; background: rgba(15,23,42,.88);
    }}
    .tag-cap-large {{ border-color:rgba(56,189,248,.5);  color:#bae6fd; }}
    .tag-cap-mid   {{ border-color:rgba(167,243,208,.4); color:#a7f3d0; }}
    .tag-cap-small {{ border-color:rgba(251,191,36,.4);  color:#fde68a; }}
    .tag-cap-micro {{ border-color:rgba(249,115,22,.4);  color:#fed7aa; }}
    /* Numbers */
    .number-pos {{ color: #4ade80; }}
    .number-neg {{ color: #f97373; }}
    /* Filter / search */
    .filter-btn {{
      padding: .28rem .8rem; border: 1px solid var(--border-subtle); background: rgba(15,23,42,.7);
      color: var(--text-muted); border-radius: 999px; font-size: .7rem; cursor: pointer;
      transition: all .18s; white-space: nowrap;
    }}
    .filter-btn:hover, .filter-btn.active {{
      background: rgba(56,189,248,.16); border-color: rgba(56,189,248,.6); color: #bae6fd;
    }}
    .search-box {{
      background: rgba(15,23,42,.7); border: 1px solid var(--border-subtle);
      color: var(--text-primary); border-radius: 999px;
      padding: .32rem 1rem; font-size: .8rem; outline: none; width: 100%;
    }}
    .search-box:focus {{ border-color: rgba(56,189,248,.6); box-shadow: 0 0 0 3px rgba(56,189,248,.1); }}
    .search-box::placeholder {{ color: var(--text-muted); }}
    /* KPI cards */
    .kpi-card {{ text-align: center; padding: 1rem .75rem; }}
    .kpi-label {{ font-size: .6rem; letter-spacing: .14em; text-transform: uppercase; color: var(--text-muted); }}
    .kpi-value {{ font-size: 1.75rem; font-weight: 700; color: var(--text-primary); line-height: 1.15; }}
    .kpi-sub   {{ font-size: .65rem; color: var(--text-muted); margin-top: .1rem; }}
    #rowCount  {{ font-size: .7rem; color: var(--text-muted); }}
    /* Heatmap */
    .heatmap-container {{
      background: radial-gradient(circle at top left, rgba(15,23,42,.98), rgba(9,9,9,.97));
      padding: 1.5rem; border-radius: 1rem; border: 1px solid rgba(148,163,184,.35);
    }}
    .heatmap-title {{
      font-size: .82rem; font-weight: 600; letter-spacing: .16em; text-transform: uppercase;
      color: #e0f2fe; text-align: center; margin-bottom: .9rem;
    }}
    /* LLM narratives (market panel + stock modal) */
    .narrative-body {{
      white-space: pre-wrap; word-break: break-word; font-size: .84rem; line-height: 1.55;
      color: var(--text-primary); max-height: 420px; overflow-y: auto;
      padding: .75rem 1rem; border-radius: .5rem; background: rgba(15,23,42,.65);
      border: 1px solid var(--border-subtle);
    }}
    .narrative-body.narrative-body--structured {{ white-space: normal; }}
    .narrative-render-json {{ font-size: .84rem; line-height: 1.55; }}
    .narrative-json-header {{
      display: flex; flex-wrap: wrap; align-items: center; gap: .5rem;
      margin-bottom: 1rem; padding-bottom: .75rem; border-bottom: 1px solid rgba(148,163,184,.2);
    }}
    .nr-section {{ margin-bottom: 1rem; }}
    .nr-section:last-child {{ margin-bottom: 0; }}
    .nr-title {{
      font-size: .68rem; font-weight: 600; letter-spacing: .12em; text-transform: uppercase;
      color: #7dd3fc; margin-bottom: .4rem;
    }}
    .nr-text {{ color: #e5e7eb; margin: 0; }}
    .nr-text.nr-summary {{ font-size: .88rem; line-height: 1.6; color: #f1f5f9; }}
    .nr-kv {{ margin: 0; padding: 0; }}
    .nr-kv dt {{
      font-size: .62rem; letter-spacing: .08em; text-transform: uppercase;
      color: #94a3b8; margin-top: .45rem; margin-bottom: .1rem;
    }}
    .nr-kv dd {{ margin: 0 0 .2rem 0; color: #e5e7eb; font-variant-numeric: tabular-nums; }}
    .nr-kv dd:first-of-type {{ margin-top: 0; }}
    .nr-quarterly-wrap {{ overflow-x: auto; margin: 0; }}
    .nr-quarterly {{
      width: 100%; font-size: .78rem; border-collapse: collapse;
      color: #e5e7eb; margin: 0;
    }}
    .nr-quarterly th, .nr-quarterly td {{
      border: 1px solid rgba(148,163,184,.22); padding: .35rem .5rem; text-align: left;
    }}
    .nr-quarterly th {{ background: rgba(30,41,59,.9); color: #7dd3fc; font-weight: 600; font-size: .65rem; text-transform: uppercase; letter-spacing: .06em; }}
    .nr-quarterly td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .narrative-fallback {{ white-space: pre-wrap; word-break: break-word; margin: 0; font-size: .82rem; color: #e5e7eb; }}
    .modal-content.narrative-modal-dark {{
      background: #0f172a; color: #e5e7eb; border: 1px solid rgba(148,163,184,.35);
    }}
    .btn-narrative {{ font-size: .65rem; padding: .12rem .45rem; }}
    .heatmap-grid {{
      display: grid;
      grid-template-columns: repeat(10, minmax(28px, 1fr));
      gap: 5px; margin-bottom: .9rem; max-width: 720px; margin-left: auto; margin-right: auto;
    }}
    @media (max-width: 767px) {{ .heatmap-grid {{ grid-template-columns: repeat(5, minmax(24px, 1fr)); }} }}
    .heatmap-cell {{
      aspect-ratio: 1; width: 100%; max-width: 64px; display: flex; flex-direction: column; align-items: center; justify-content: center;
      gap: 1px; font-size: .58rem; font-weight: 600; color: white; border-radius: 6px; cursor: pointer;
      transition: transform .15s; min-width: 24px; min-height: 24px;
      user-select: none;
      -webkit-user-select: none;
      text-align: center; line-height: 1.05; padding: 2px;
    }}
    .heatmap-cell .hm-line1 {{ font-size: .56rem; font-weight: 700; }}
    .heatmap-cell .hm-line2 {{ font-size: .48rem; font-weight: 600; opacity: 0.95; }}
    /* Subtle hover so heat map cells do not overlap neighbors */
    .heatmap-cell:hover {{ transform: scale(1.08); z-index: 5; }}
    .heatmap-cell.excellent {{ background: linear-gradient(135deg, #16a34a, #4ade80); }}
    .heatmap-cell.good      {{ background: linear-gradient(135deg, #22c55e, #86efac); }}
    .heatmap-cell.moderate  {{ background: linear-gradient(135deg, #eab308, #fbbf24); color:#020617; }}
    .heatmap-cell.poor      {{ background: linear-gradient(135deg, #f97316, #fdba74); }}
    .heatmap-cell.very-poor {{ background: linear-gradient(135deg, #ef4444, #f97373); }}
    .heatmap-legend {{
      display: flex; justify-content: center; gap: .8rem; flex-wrap: wrap;
      font-size: .7rem; color: var(--text-muted); margin-bottom: .6rem;
    }}
    .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 3px; vertical-align: middle; }}
    /* Breadth cards */
    .breadth-summary {{ display: flex; flex-wrap: wrap; justify-content: center; gap: .75rem; margin-top: .75rem; }}
    .breadth-card {{
      min-width: 110px; padding: .6rem .85rem; border-radius: .85rem;
      background: rgba(15,23,42,.9); border: 1px solid var(--border-subtle);
      text-align: center; font-size: .7rem; color: var(--text-muted);
    }}
    .breadth-card .bval {{ font-size: 1.3rem; font-weight: 700; color: var(--text-primary); }}
    .breadth-card.bullish {{ border-color: rgba(34,197,94,.55); }}
    .breadth-card.neutral {{ border-color: rgba(234,179,8,.55); }}
    .breadth-card.bearish {{ border-color: rgba(239,68,68,.65); }}
    /* Tabs (dark) */
    .nav-tabs {{ border-bottom-color: var(--border-subtle); }}
    .nav-tabs .nav-link {{
      color: var(--text-muted); border: none; border-bottom: 2px solid transparent;
      padding: .5rem 1rem; font-size: .85rem;
    }}
    .nav-tabs .nav-link:hover {{ color: var(--accent); border-color: transparent; }}
    .nav-tabs .nav-link.active {{
      color: var(--accent); background: transparent; border-color: transparent transparent var(--accent) transparent;
    }}
    tr.row-highlight {{ background: rgba(56,189,248,.22) !important; outline: 1px solid rgba(56,189,248,.5); }}
    .heatmap-cell.is-selected {{ outline: 3px solid #fff; box-shadow: 0 0 12px rgba(56,189,248,.8); }}
    /* Chart panels: explicit canvas box avoids legend/doughnut overlap with short fixed heights */
    .chart-card {{
      display: flex;
      flex-direction: column;
      min-height: 0;
    }}
    .chart-card .chart-body {{
      flex: 1 1 auto;
      display: flex;
      flex-direction: column;
      padding: 0.75rem 1rem 1rem;
      min-height: 0;
    }}
    .chart-canvas-wrap {{
      position: relative;
      width: 100%;
      height: 240px;
      min-height: 220px;
      max-height: 320px;
    }}
    @media (min-width: 1400px) {{
      .chart-canvas-wrap {{ height: 260px; }}
    }}
    /* Signal mix beside counts table: a bit more vertical room */
    .chart-canvas-wrap--signal {{
      height: 260px;
      min-height: 240px;
    }}
    .section-label {{
      font-size: .65rem;
      letter-spacing: .18em;
      text-transform: uppercase;
      color: var(--text-muted);
      margin-bottom: .65rem;
      padding-left: .15rem;
    }}
    /* Universe tab: grouped controls so filter rows do not run together */
    .filter-toolbar {{
      border: 1px solid var(--border-subtle);
      border-radius: .65rem;
      padding: .85rem 1rem;
      background: rgba(15, 23, 42, 0.55);
      margin-bottom: 1rem;
    }}
    .filter-toolbar .toolbar-row {{
      margin-bottom: .65rem;
    }}
    .filter-toolbar .toolbar-row:last-child {{ margin-bottom: 0; }}
    .filter-toolbar .toolbar-label {{
      font-size: .62rem;
      letter-spacing: .12em;
      text-transform: uppercase;
      color: var(--accent);
      margin-bottom: .4rem;
      display: block;
    }}
    details.methodology-details {{
      border: 1px solid var(--border-subtle);
      border-radius: .65rem;
      background: rgba(15, 23, 42, 0.45);
      margin-bottom: 1rem;
    }}
    details.methodology-details > summary {{
      cursor: pointer;
      padding: .65rem 1rem;
      font-size: .75rem;
      font-weight: 600;
      color: var(--accent);
      list-style-position: outside;
    }}
    details.methodology-details .details-body {{
      padding: 0 1rem 1rem;
      border-top: 1px solid var(--border-subtle);
    }}
    .nav-tabs {{ flex-wrap: wrap; gap: .25rem; }}
    /* NSE index cards (grid) — levels, tech score pill, RSI / 50D / RS strip, signal + trend */
    .index-metric-card {{
      background: linear-gradient(165deg, rgba(30,41,59,.95) 0%, rgba(15,23,42,.98) 100%);
      border: 1px solid var(--border-subtle);
      border-radius: .85rem;
      padding: 1rem 1rem 1.1rem;
      box-shadow: 0 8px 24px rgba(0,0,0,.25);
      transition: transform .15s ease, border-color .15s ease;
    }}
    .index-metric-card:hover {{
      transform: translateY(-2px);
      border-color: rgba(56,189,248,.35);
    }}
    .index-metric-name {{
      font-size: .82rem;
      font-weight: 700;
      color: var(--text-primary);
      letter-spacing: .02em;
      line-height: 1.25;
      max-width: 62%;
    }}
    .index-metric-score-pill {{
      min-width: 2.5rem;
      text-align: center;
      font-size: 1.15rem;
      font-weight: 800;
      padding: .2rem .55rem;
      border-radius: .45rem;
      line-height: 1.1;
    }}
    .index-score-tier-excellent {{ background: rgba(22,163,74,.22); color: #4ade80; border: 1px solid rgba(34,197,94,.45); }}
    .index-score-tier-good      {{ background: rgba(74,222,128,.14); color: #86efac; border: 1px solid rgba(74,222,128,.35); }}
    .index-score-tier-moderate  {{ background: rgba(234,179,8,.16); color: #fde047; border: 1px solid rgba(234,179,8,.4); }}
    .index-score-tier-low       {{ background: rgba(249,115,22,.18); color: #fdba74; border: 1px solid rgba(249,115,22,.45); }}
    .index-metric-price {{
      font-size: 1.35rem;
      font-weight: 700;
      color: #7dd3fc;
      letter-spacing: .02em;
      margin-top: .15rem;
    }}
    .index-mini-metric {{
      flex: 1 1 0;
      text-align: center;
      font-size: .58rem;
      text-transform: uppercase;
      letter-spacing: .06em;
      color: var(--text-muted);
      border: 1px solid rgba(148,163,184,.28);
      border-radius: .4rem;
      padding: .35rem .2rem .4rem;
      background: rgba(15,23,42,.65);
    }}
    .index-mini-label {{ display: block; margin-bottom: .15rem; opacity: .9; }}
    .index-mini-val {{ font-size: .72rem; font-weight: 700; letter-spacing: 0; text-transform: none; }}
    .index-mini-pos {{ color: #4ade80; }}
    .index-mini-neg {{ color: #f97373; }}
    .index-mini-neutral {{ color: var(--text-muted); }}
    .index-summary-footer-card {{
      text-align: center;
      padding: 1rem .75rem;
      border-radius: .85rem;
      border: 1px solid var(--border-subtle);
      background: radial-gradient(circle at top, rgba(56,189,248,.08), rgba(15,23,42,.92));
    }}
    .index-summary-footer-card .isfc-val {{
      font-size: 1.65rem;
      font-weight: 800;
      color: var(--text-primary);
      line-height: 1.1;
    }}
    .index-summary-footer-card .isfc-lbl {{
      font-size: .58rem;
      letter-spacing: .14em;
      text-transform: uppercase;
      color: var(--text-muted);
      margin-top: .35rem;
    }}
  </style>
</head>
<body>
<!-- Dashboard HTML generated {generated_str} -->
<div class="container-fluid px-3 px-md-4 py-4" style="max-width:1600px;margin:0 auto;">

  <!-- Header: single primary date from DB; optional CSV snapshot if different -->
  <div class="text-center mb-4">
    <h1 class="fw-light mb-1" style="font-size:1.9rem;color:var(--text-primary);letter-spacing:-.4px;">
      NSE Market Analysis Dashboard
    </h1>
    <p class="mb-0" style="font-size:1.25rem;color:var(--text-primary);">
      <strong style="color:var(--accent);">As of {as_of_str}</strong>
    </p>
    {(
      f'<p class="small mb-0 mt-2" style="color:var(--text-warning);">Universe CSV date is {csv_snap_str} (differs from DB as-of). Re-run the universe analysis / full pipeline to align.</p>'
      if csv_differs
      else ""
    )}
  </div>

  <!-- KPI Row -->
  <div class="row g-3 mb-4">
    <div class="col-6 col-md-4 col-lg-2">
      <div class="card kpi-card h-100">
        <div class="kpi-label">Stocks Analyzed</div>
        <div class="kpi-value">{len(data.stocks):,}</div>
        <div class="kpi-sub">Price&gt;₹100 · Vol&gt;1L</div>
      </div>
    </div>
    <div class="col-6 col-md-4 col-lg-2">
      <div class="card kpi-card h-100">
        <div class="kpi-label">Unique Symbols</div>
        <div class="kpi-value">{data.stocks['SYMBOL'].nunique():,}</div>
        <div class="kpi-sub">All series</div>
      </div>
    </div>
    <div class="col-6 col-md-4 col-lg-2">
      <div class="card kpi-card h-100">
        <div class="kpi-label">Indices Tracked</div>
        <div class="kpi-value">{len(data.indexes):,}</div>
        <div class="kpi-sub">NSE indices</div>
      </div>
    </div>
    <div class="col-6 col-md-4 col-lg-2">
      <div class="card kpi-card h-100">
        <div class="kpi-label">Avg Fund Score</div>
        <div class="kpi-value">{ (f"{avg_fund:.1f}" if avg_fund is not None else "N/A") }</div>
        <div class="kpi-sub">{ (f"{high_fund} ≥ 70 / {total_with_fund}" if avg_fund is not None else "Enhanced") }</div>
      </div>
    </div>
    <div class="col-6 col-md-4 col-lg-2">
      <div class="card kpi-card h-100" style="border-color:rgba(34,197,94,.35)!important;">
        <div class="kpi-label">Bullish Signals</div>
        <div class="kpi-value" style="color:#4ade80;">{bullish_count:,}</div>
        <div class="kpi-sub">BUY / STRONG BUY</div>
      </div>
    </div>
    <div class="col-6 col-md-4 col-lg-2">
      <div class="card kpi-card h-100" style="border-color:rgba(239,68,68,.35)!important;">
        <div class="kpi-label">Bearish Signals</div>
        <div class="kpi-value" style="color:#f97373;">{bearish_count:,}</div>
        <div class="kpi-sub">SELL / WEAK HOLD</div>
      </div>
    </div>
  </div>

  <!-- NSE indices — card grid (levels, tech score, RSI / 50D / RS, signal + trend) -->
  <div class="section-label mb-2">NSE indices analysis</div>
  <div class="card index-strip-card mb-3">
    <div class="card-header py-2 px-3 d-flex justify-content-between align-items-center flex-wrap gap-2">
      <span class="card-title mb-0">Index cards</span>
      <span class="small" style="color:var(--text-muted);">{len(data.indexes):,} indices</span>
    </div>
    <div class="card-body p-3">
      <div class="row g-3">
        {''.join(index_cards)}
      </div>
      <div class="row g-3 mt-1">
        <div class="col-6 col-md-3">
          <div class="index-summary-footer-card h-100">
            <div class="isfc-val">{summary_total:,}</div>
            <div class="isfc-lbl">Total stocks analyzed</div>
          </div>
        </div>
        <div class="col-6 col-md-3">
          <div class="index-summary-footer-card h-100">
            <div class="isfc-val" style="color:#4ade80;">{summary_strong_buy:,}</div>
            <div class="isfc-lbl">Strong buy signals</div>
          </div>
        </div>
        <div class="col-6 col-md-3">
          <div class="index-summary-footer-card h-100">
            <div class="isfc-val" style="color:#86efac;">{summary_buy:,}</div>
            <div class="isfc-lbl">Buy signals</div>
          </div>
        </div>
        <div class="col-6 col-md-3">
          <div class="index-summary-footer-card h-100">
            <div class="isfc-val">{summary_avg_tech:.1f}</div>
            <div class="isfc-lbl">Average technical score</div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <ul class="nav nav-tabs px-1" id="dashTabNav" role="tablist">
    <li class="nav-item" role="presentation">
      <button class="nav-link active" id="tab-overview-btn" data-bs-toggle="tab" data-bs-target="#tabOverview" type="button" role="tab" aria-controls="tabOverview" aria-selected="true">Overview &amp; charts</button>
    </li>
    <li class="nav-item" role="presentation">
      <button class="nav-link" id="tab-universe-btn" data-bs-toggle="tab" data-bs-target="#tabUniverse" type="button" role="tab" aria-controls="tabUniverse" aria-selected="false">Universe, filters &amp; heat map</button>
    </li>
    <li class="nav-item" role="presentation">
      <button class="nav-link" id="tab-fundamentals-btn" data-bs-toggle="tab" data-bs-target="#tabFundamentals" type="button" role="tab" aria-controls="tabFundamentals" aria-selected="false">Fundamentals &amp; ratios</button>
    </li>
  </ul>

  <div class="tab-content pt-2" id="dashTabContent">
    <!-- Tab 1: signals, indices, charts, breadth summary, data notes -->
    <div class="tab-pane fade show active" id="tabOverview" role="tabpanel" aria-labelledby="tab-overview-btn">
      <div class="section-label">AI market narrative (SQLite + optional live API)</div>
      <div class="card mb-4 border-info border-opacity-25">
        <div class="card-header py-2 px-3 d-flex flex-wrap justify-content-between align-items-center gap-2">
          <span class="card-title mb-0">Local LLM summary — breadth &amp; indices</span>
          <div class="d-flex flex-wrap align-items-center gap-2">
            <span class="small" style="color:var(--text-muted);">as of {_escape(as_of_str)} · {stock_narrative_count} stock narrative(s) embedded</span>
            <button type="button" class="btn btn-sm btn-outline-info" id="btnRefreshMarketNarrative" title="Calls narrative API; saves to DB (re-run dashboard to re-embed)">
              Refresh via API
            </button>
          </div>
        </div>
        <div class="card-body">
          <p id="marketNarrativeMeta" class="small mb-2" style="color:var(--text-muted);"></p>
          <div id="marketNarrativeBody" class="narrative-body d-none"></div>
          <p id="marketNarrativeEmpty" class="small mb-0" style="color:var(--text-muted);">
            No market narrative in <code class="text-info">llm_narratives</code> for this date. Run
            <code class="text-info">python python/core/narrative_llm_server.py</code> and open
            <code class="text-info">/api/market-narrative?refresh=1</code>, then regenerate this dashboard.
          </p>
        </div>
      </div>
      <!-- Signal mix sits with the counts table (not with cap chart) -->
      <div class="section-label">Signal counts &amp; mix</div>
      <div class="row g-3 mb-4">
        <div class="col-12 col-lg-5 col-xl-4">
          <div class="card h-100 mb-0">
            <div class="card-header py-2 px-3">
              <span class="card-title">Signal distribution</span>
            </div>
            <div class="card-body p-0">
              <div class="table-responsive">
                <table class="table table-sm mb-0">
                  <thead><tr>
                    <th>Signal</th>
                    <th class="text-end">Count</th>
                    <th class="text-end">%</th>
                  </tr></thead>
                  <tbody>{''.join(signal_rows)}</tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
        <div class="col-12 col-lg-7 col-xl-8">
          <div class="card chart-card h-100 mb-0">
            <div class="card-header py-2 px-3">
              <span class="card-title">Signal mix</span>
            </div>
            <div class="card-body chart-body">
              <div class="chart-canvas-wrap chart-canvas-wrap--signal">
                <canvas id="signalsChart" aria-label="Trading signal mix chart"></canvas>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="section-label">Market cap &amp; breadth</div>
      <div class="row g-3 mb-3">
        <div class="col-12 col-lg-8">
          <div class="card chart-card h-100 mb-0">
            <div class="card-header py-2 px-3">
              <span class="card-title">Market cap mix</span>
            </div>
            <div class="card-body chart-body">
              <div class="chart-canvas-wrap">
                <canvas id="capChart" aria-label="Market cap distribution chart"></canvas>
              </div>
            </div>
          </div>
        </div>
        <div class="col-12 col-lg-4">
          <div class="heatmap-container h-100 mb-0" style="min-height: 100%;">
            <div class="heatmap-title">Signal breadth (counts)</div>
            <div class="breadth-summary" style="margin-top:0;">
              <div class="breadth-card bullish"><div class="bval">{bullish_count}</div><div>Bullish</div></div>
              <div class="breadth-card neutral"><div class="bval">{neutral_count}</div><div>Neutral / Hold</div></div>
              <div class="breadth-card bearish"><div class="bval">{bearish_count}</div><div>Bearish</div></div>
            </div>
          </div>
        </div>
      </div>
      <details class="methodology-details mb-0">
        <summary>RS %, fund scores &amp; data notes (click to expand)</summary>
        <div class="details-body pt-3">
          <p class="small mb-2" style="color:var(--text-muted);line-height:1.55;">
            <strong class="text-light">Relative strength (RS %):</strong>
            50-day total return of the stock minus the same for a broad benchmark.
            The analysis picks the first usable series in <code class="text-info">data/nse_index_data.csv</code>
            (order: Nifty 500, Nifty 50, Nifty 100/200, then other broad indices with <span title="at least 50 daily rows">&ge;50</span> rows).
            Matching is case-insensitive (&quot;Nifty 500&quot; and &quot;NIFTY 500&quot; both work).
            If RS is blank in the CSV, the benchmark had no overlapping history or too few rows
            &mdash; add or fix that index in the file and re-run the <strong class="text-light">universe analysis</strong>
            (not only this dashboard).
          </p>
          <p class="small mb-0" style="color:var(--text-muted);line-height:1.55;">
            <strong class="text-light">Fund score:</strong>
            From <code class="text-info">data/fundamental_scores_database.csv</code> when that file exists and the symbol has a row
            (column <code>symbol</code> or <code>SYMBOL</code>). Only symbols present in that file get a number after you re-run
            <strong class="text-light">universe analysis</strong>; others stay blank in the CSV and show &quot;&mdash;&quot; in the table
            (not zero). In this run: <strong class="text-light">{total_with_fund:,}</strong> of <strong class="text-light">{len(data.stocks):,}</strong> stocks have a fund score.
            If you do not see the Fund column, scroll the universe table <em>horizontally</em> (wide layout).
          </p>
        </div>
      </details>
    </div>

    <!-- Tab 2: filters, full table, heatmap (click cell → focus row) -->
    <div class="tab-pane fade" id="tabUniverse" role="tabpanel" aria-labelledby="tab-universe-btn">
      <div class="card mb-3">
        <div class="card-header py-2 px-3 d-flex justify-content-between align-items-center flex-wrap gap-2">
          <span class="card-title">All stocks — filter, sort &amp; inspect</span>
          <span id="rowCount"></span>
        </div>
        <div class="card-body">
          <div class="filter-toolbar">
            <div class="toolbar-row">
              <span class="toolbar-label">Trading signal</span>
              <div class="d-flex flex-wrap gap-2" id="signalFilters">
                <button class="filter-btn active" data-signal="ALL" type="button">All</button>
                <button class="filter-btn" data-signal="STRONG_BUY" type="button">Strong Buy</button>
                <button class="filter-btn" data-signal="BUY" type="button">Buy</button>
                <button class="filter-btn" data-signal="HOLD" type="button">Hold</button>
                <button class="filter-btn" data-signal="WEAK_HOLD" type="button">Weak Hold</button>
                <button class="filter-btn" data-signal="SELL" type="button">Sell</button>
                <button class="filter-btn" data-signal="STRONG_SELL" type="button">Strong Sell</button>
              </div>
            </div>
            <div class="toolbar-row">
              <span class="toolbar-label">Market cap</span>
              <div class="d-flex flex-wrap gap-2" id="capFilters">
                <button class="filter-btn active" data-cap="ALL" type="button">All Caps</button>
                <button class="filter-btn" data-cap="LARGE_CAP" type="button">Large</button>
                <button class="filter-btn" data-cap="MID_CAP" type="button">Mid</button>
                <button class="filter-btn" data-cap="SMALL_CAP" type="button">Small</button>
                <button class="filter-btn" data-cap="MICRO_CAP" type="button">Micro</button>
              </div>
            </div>
            <div class="toolbar-row">
              <span class="toolbar-label">Search</span>
              <input id="searchBox" class="search-box mb-0" placeholder="Symbol or company name…" autocomplete="off" />
            </div>
          </div>
          <p class="small mb-2" style="color:var(--text-muted);">
            Fund scores: <strong class="text-light">{total_with_fund:,}</strong> / {len(data.stocks):,} symbols &mdash;
            scroll <strong class="text-light">right</strong> inside the table if the Fund column is off-screen.
          </p>
          <div class="scroll-section">
            <table class="table table-sm" id="stocksTable">
              <thead>
                <tr>
                  <th data-col="symbol">Symbol</th>
                  <th data-col="companyName">Company</th>
                  <th data-col="marketCap">Cap</th>
                  <th data-col="currentPrice" class="text-end">Price</th>
                  <th data-col="change1D" class="text-end">1D%</th>
                  <th data-col="change1W" class="text-end">1W%</th>
                  <th data-col="change1M" class="text-end">1M%</th>
                  <th data-col="technicalScore" class="text-end sort-desc">Tech</th>
                  <th data-col="rsi" class="text-end">RSI</th>
                  <th data-col="relativeStrength" class="text-end">RS %</th>
                  <th data-col="fundamental" class="text-end">Fund</th>
                  <th data-col="canSlim" class="text-end">CAN-SLIM</th>
                  <th data-col="minervini" class="text-end">Minervini</th>
                  <th data-col="trendSignal">Trend</th>
                  <th data-col="tradingSignal">Signal</th>
                  <th class="text-center">AI</th>
                </tr>
              </thead>
              <tbody id="stocksTableBody"></tbody>
            </table>
          </div>
        </div>
      </div>
      <div class="heatmap-container mt-2">
        <div class="heatmap-title">Heat map — top 50 by technical score (click = AI narrative popup; double-click = clear search &amp; filters)</div>
        <div class="heatmap-legend">
          <span><span class="legend-dot" style="background:#16a34a;"></span>Excellent (80+)</span>
          <span><span class="legend-dot" style="background:#22c55e;"></span>Good (65–79)</span>
          <span><span class="legend-dot" style="background:#eab308;"></span>Moderate (50–64)</span>
          <span><span class="legend-dot" style="background:#f97316;"></span>Poor (35–49)</span>
          <span><span class="legend-dot" style="background:#ef4444;"></span>Very Poor (&lt;35)</span>
        </div>
        <div id="breadthHeatmap" class="heatmap-grid"></div>
        <p class="text-center small mt-2 mb-0" style="color:var(--text-muted);">Universe: {len(data.stocks):,} stocks · Cells show ticker (truncated)</p>
      </div>
    </div>

    <!-- Tab 3: fundamental scores + optional quarterly ratios (merged in Python) -->
    <div class="tab-pane fade" id="tabFundamentals" role="tabpanel" aria-labelledby="tab-fundamentals-btn">
      <div class="card mb-3">
        <div class="card-header py-2 px-3 d-flex justify-content-between align-items-center flex-wrap gap-2">
          <span class="card-title">Fundamental scores &amp; latest-quarter style ratios</span>
          <span class="small" style="color:var(--text-muted);">
            {("Ratios file: loaded" if fund_ratios_file_loaded else "Ratios file: not found (optional)")}
          </span>
        </div>
        <div class="card-body">
          <p class="small mb-2" style="color:var(--text-muted);line-height:1.5;">
            {f'<span class="d-block mb-2">{fund_panel_note}</span>' if fund_panel_note else ''}
            Scores and pillars come from <code class="text-info">data/fundamental_scores_database.csv</code>.
            Reported profit/sales YoY, margin change (pp), PE, CFO/debt YoY are written there when you refresh fundamentals via R
            (<code>fn_screener_public_ratios</code>), or supply <code class="text-info">data/fundamental_quarterly_ratios.csv</code>.
          </p>
          <input id="fundSearchBox" class="search-box mb-2" placeholder="Search company name…" autocomplete="off" />
          <span id="fundRowCount" class="small d-block mb-2" style="color:var(--text-muted);"></span>
          <div class="scroll-section">
            <table class="table table-sm" id="fundamentalsTable">
              <thead>
                <tr>
                  <th data-fcol="companyName">Company</th>
                  <th data-fcol="fundScore" class="text-end sort-desc">Fund</th>
                  <th data-fcol="earningsQuality" class="text-end">Earn Q</th>
                  <th data-fcol="salesGrowth" class="text-end">Sales score</th>
                  <th data-fcol="financialStrength" class="text-end">Fin. str.</th>
                  <th data-fcol="institutionalBacking" class="text-end">Inst.</th>
                  <th data-fcol="fundDataDate">Fund data</th>
                  <th data-fcol="profitYoyPct" class="text-end">Profit YoY %</th>
                  <th data-fcol="salesReportedYoyPct" class="text-end">Sales YoY %</th>
                  <th data-fcol="marginPpChange" class="text-end">Margin Δ (pp)</th>
                  <th data-fcol="peTtm" class="text-end">PE (TTM)</th>
                  <th data-fcol="cfoChangeYoy" class="text-end">CFO Δ%</th>
                  <th data-fcol="debtChangeYoy" class="text-end">Debt Δ%</th>
                  <th data-fcol="ratiosPeriod">Ratio period</th>
                </tr>
              </thead>
              <tbody id="fundamentalsTableBody"></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Stock narrative: heat map + universe table → same modal -->
  <div class="modal fade" id="stockNarrativeModal" tabindex="-1" aria-labelledby="stockNarrativeModalLabel" aria-hidden="true">
    <div class="modal-dialog modal-lg modal-dialog-scrollable">
      <div class="modal-content narrative-modal-dark">
        <div class="modal-header border-secondary">
          <h5 class="modal-title" id="stockNarrativeModalLabel">Stock narrative</h5>
          <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
        </div>
        <div class="modal-body">
          <div id="stockNarrativeMetrics" class="small mb-3" style="color:var(--text-muted);"></div>
          <div id="stockNarrativeBody" class="narrative-body" style="max-height:55vh;"></div>
          <p id="stockNarrativeEmbedMeta" class="small text-muted mt-2 mb-0"></p>
          <p id="stockNarrativeStatus" class="small mt-2 mb-0 text-warning d-none"></p>
        </div>
        <div class="modal-footer border-secondary">
          <button type="button" class="btn btn-sm btn-outline-light" id="btnStockNarrativeFind">Find in table</button>
          <button type="button" class="btn btn-sm btn-outline-info" id="btnStockNarrativeFetch">Regenerate via API</button>
          <button type="button" class="btn btn-sm btn-secondary" data-bs-dismiss="modal">Close</button>
        </div>
      </div>
    </div>
  </div>

</div><!-- /container-fluid -->

<script>
  const stocksData = {stocks_js_data};
  const fundamentalsData = {fundamentals_json};
  const NARRATIVE_API_BASE = {narrative_api_base_js};
  const narrativeAnalysisDate = {json.dumps(as_of_str)};
  const embeddedMarketNarrative = {market_narrative_json};
  const embeddedStockNarratives = {stock_narratives_json};
  Chart.defaults.color = "#9ca3af";

  /** Escape text for safe use in HTML attribute or text node */
  function escHtml(s) {{
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }}

  /**
   * Strip ```json ... ``` fences (LLM output) and return inner text for JSON.parse.
   */
  function extractFencedJsonOrRaw(raw) {{
    const t = String(raw ?? "").trim();
    if (t.startsWith("```")) {{
      const nl = t.indexOf(String.fromCharCode(10));
      const lastFence = t.lastIndexOf("```");
      if (nl >= 0 && lastFence > nl) {{
        return t.slice(nl + 1, lastFence).trim();
      }}
    }}
    return t;
  }}

  /** Badge colour for sentiment strings */
  function narrativeSentimentBadgeClass(sent) {{
    const u = String(sent || "").toUpperCase();
    if (u.includes("BEAR")) return "bg-danger";
    if (u.includes("BULL")) return "bg-success";
    if (u.includes("NEUTRAL") || u.includes("MIXED")) return "bg-warning text-dark";
    return "bg-secondary";
  }}

  function formatKeyLabel(key) {{
    return String(key).replace(/_/g, " ").replace(/\\b\\w/g, c => c.toUpperCase());
  }}

  /** Build HTML for a JSON object narrative (market + per-stock pipeline JSON) */
  function buildNarrativeObjectHtml(obj) {{
    const order = [
      "analysis_date", "symbol", "overall_sentiment", "headline_view",
      "breadth_analysis", "index_tone", "technical_summary", "fundamental_summary",
      "quarterly_trends", "yahoo_context", "summary"
    ];
    const labels = {{
      analysis_date: "As of",
      symbol: "Symbol",
      overall_sentiment: "Overall sentiment",
      headline_view: "Headline view",
      breadth_analysis: "Breadth analysis",
      index_tone: "Index tone",
      technical_summary: "Technical summary",
      fundamental_summary: "Fundamental summary",
      quarterly_trends: "Quarterly trends (last quarters)",
      yahoo_context: "Yahoo / news context",
      summary: "Summary"
    }};
    const seen = new Set();
    let html = '<div class="narrative-render-json">';
    const headerParts = [];
    if (obj.analysis_date != null && obj.analysis_date !== "") {{
      seen.add("analysis_date");
      headerParts.push('<span class="text-muted small">As of <strong class="text-light">' + escHtml(String(obj.analysis_date)) + "</strong></span>");
    }}
    if (obj.symbol != null && obj.symbol !== "") {{
      seen.add("symbol");
      headerParts.push('<span class="badge bg-info text-dark">' + escHtml(String(obj.symbol)) + "</span>");
    }}
    if (obj.overall_sentiment != null && obj.overall_sentiment !== "") {{
      seen.add("overall_sentiment");
      const cls = narrativeSentimentBadgeClass(obj.overall_sentiment);
      headerParts.push('<span class="badge ' + cls + '">' + escHtml(String(obj.overall_sentiment)) + "</span>");
    }}
    if (headerParts.length) {{
      html += '<div class="narrative-json-header">' + headerParts.join("") + "</div>";
    }}
    for (const k of order) {{
      if (seen.has(k)) continue;
      if (!(k in obj) || obj[k] === null || obj[k] === undefined) continue;
      seen.add(k);
      const v = obj[k];
      if (typeof v === "object") continue;
      const title = labels[k] || formatKeyLabel(k);
      const isSummary = k === "summary" || k === "quarterly_trends";
      html += '<div class="nr-section">' +
        '<div class="nr-title">' + escHtml(title) + '</div>' +
        '<p class="nr-text' + (isSummary ? " nr-summary" : "") + '">' + escHtml(String(v)) + "</p></div>";
    }}
    for (const k of Object.keys(obj).sort()) {{
      if (seen.has(k)) continue;
      const v = obj[k];
      if (typeof v === "object" && v !== null) continue;
      html += '<div class="nr-section">' +
        '<div class="nr-title">' + escHtml(formatKeyLabel(k)) + '</div>' +
        '<p class="nr-text">' + escHtml(String(v)) + "</p></div>";
    }}
    html += "</div>";
    return html;
  }}

  /**
   * Render narrative into a container: structured HTML for JSON objects, else escaped pre text.
   */
  function renderNarrativeIntoElement(el, rawString) {{
    if (!el) return;
    el.classList.remove("narrative-body--structured");
    if (rawString == null || rawString === "") {{
      el.innerHTML = "";
      return;
    }}
    const candidate = extractFencedJsonOrRaw(rawString);
    let obj = null;
    try {{
      obj = JSON.parse(candidate);
    }} catch (e1) {{
      try {{
        obj = JSON.parse(String(rawString).trim());
      }} catch (e2) {{
        obj = null;
      }}
    }}
    if (obj !== null && typeof obj === "object" && !Array.isArray(obj)) {{
      el.innerHTML = buildNarrativeObjectHtml(obj);
      el.classList.add("narrative-body--structured");
      return;
    }}
    el.innerHTML = '<pre class="narrative-fallback">' + escHtml(String(rawString)) + "</pre>";
  }}

  let activeSignal = "ALL";
  let activeCap    = "ALL";
  let currentSortColumn    = "technicalScore";
  let currentSortDirection = "desc";

  /* ——— Fundamentals tab (scores + optional quarterly ratios) ——— */
  let fundSortColumn = "fundScore";
  let fundSortDirection = "desc";

  function fmtFundNum(v, decimals = 1) {{
    if (v === null || v === undefined || (typeof v === "number" && !Number.isFinite(v))) return "—";
    return Number(v).toFixed(decimals);
  }}

  function fmtFundPct(v) {{
    if (v === null || v === undefined || (typeof v === "number" && !Number.isFinite(v))) return "—";
    const n = Number(v);
    return (n >= 0 ? "+" : "") + n.toFixed(2) + "%";
  }}

  /** Margin change in percentage points (not %) */
  function fmtFundPp(v) {{
    if (v === null || v === undefined || (typeof v === "number" && !Number.isFinite(v))) return "—";
    const n = Number(v);
    return (n >= 0 ? "+" : "") + n.toFixed(2) + " pp";
  }}

  const FUND_NUM_COLS = new Set([
    "fundScore", "earningsQuality", "salesGrowth", "financialStrength", "institutionalBacking",
    "profitYoyPct", "salesReportedYoyPct", "marginPpChange", "peTtm", "cfoChangeYoy", "debtChangeYoy",
  ]);

  /** Symbol for open stock narrative modal (Find in table / API refresh) */
  let narrativeModalSymbol = "";

  function openStockNarrativeModal(symbol) {{
    narrativeModalSymbol = (symbol || "").trim();
    const symU = narrativeModalSymbol.toUpperCase();
    const s = stocksData.find(x => (x.symbol || "").toUpperCase() === symU);
    const f = (fundamentalsData || []).find(x => (x.symbol || "").toUpperCase() === symU);
    const emb = embeddedStockNarratives[symU] || embeddedStockNarratives[narrativeModalSymbol] || null;
    const titleEl = document.getElementById("stockNarrativeModalLabel");
    const metricsEl = document.getElementById("stockNarrativeMetrics");
    const bodyEl = document.getElementById("stockNarrativeBody");
    const statusEl = document.getElementById("stockNarrativeStatus");
    const embedMetaEl = document.getElementById("stockNarrativeEmbedMeta");
    if (titleEl) titleEl.textContent = (s ? (s.companyName + " (" + s.symbol + ")") : narrativeModalSymbol) + " — AI narrative";
    let metHtml = "";
    if (s) {{
      metHtml =
        "<div class='row g-2 small'>" +
        "<div class='col-6 col-md-4'><strong>Tech</strong> " + s.technicalScore.toFixed(1) + "</div>" +
        "<div class='col-6 col-md-4'><strong>RSI</strong> " + s.rsi.toFixed(1) + "</div>" +
        "<div class='col-6 col-md-4'><strong>Signal</strong> " + escHtml(s.tradingSignal) + "</div>" +
        "<div class='col-6 col-md-4'><strong>Trend</strong> " + escHtml(s.trendSignal) + "</div>" +
        "<div class='col-6 col-md-4'><strong>Fund</strong> " +
        (s.fundamental !== null && s.fundamental !== undefined && typeof s.fundamental === "number" && Number.isFinite(s.fundamental)
          ? s.fundamental.toFixed(1) : "—") +
        "</div></div>";
    }}
    if (f) {{
      metHtml +=
        "<div class='mt-2 pt-2 border-top border-secondary small'><strong class='text-info'>Fundamentals (merged)</strong> — " +
        "Earn Q " + fmtFundNum(f.earningsQuality) + " · Sales score " + fmtFundNum(f.salesGrowth) +
        " · Profit YoY " + fmtFundPct(f.profitYoyPct) + " · Sales YoY " + fmtFundPct(f.salesReportedYoyPct) +
        " · PE " + (f.peTtm !== null && f.peTtm !== undefined && Number.isFinite(Number(f.peTtm)) ? Number(f.peTtm).toFixed(2) : "—") +
        "</div>";
    }}
    if (metricsEl) metricsEl.innerHTML = metHtml;
    if (statusEl) {{ statusEl.classList.add("d-none"); statusEl.textContent = ""; }}
    if (emb && emb.content) {{
      if (bodyEl) renderNarrativeIntoElement(bodyEl, emb.content);
      if (embedMetaEl) embedMetaEl.textContent =
        "Embedded from SQLite: model " + (emb.ollama_model || "?") + " · " + (emb.updated_at || "?") + " (re-generate dashboard to refresh embed)";
    }} else {{
      if (bodyEl) {{
        bodyEl.classList.remove("narrative-body--structured");
        bodyEl.innerHTML = "<p class=\\"text-muted small mb-0\\">" + escHtml(
          "No embedded narrative for this symbol for as-of " + narrativeAnalysisDate +
          ". Use Regenerate via API (" + NARRATIVE_API_BASE + "), then run the dashboard generator again to embed."
        ) + "</p>";
      }}
      if (embedMetaEl) embedMetaEl.textContent = "";
    }}
    const modalEl = document.getElementById("stockNarrativeModal");
    if (modalEl && window.bootstrap && bootstrap.Modal) {{
      bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }}
  }}

  function initMarketNarrativePanel() {{
    const body = document.getElementById("marketNarrativeBody");
    const empty = document.getElementById("marketNarrativeEmpty");
    const meta = document.getElementById("marketNarrativeMeta");
    if (!body || !empty) return;
    if (embeddedMarketNarrative && embeddedMarketNarrative.content) {{
      renderNarrativeIntoElement(body, embeddedMarketNarrative.content);
      body.classList.remove("d-none");
      empty.classList.add("d-none");
      if (meta) meta.textContent =
        "Model: " + (embeddedMarketNarrative.ollama_model || "?") + " · SQLite " + (embeddedMarketNarrative.updated_at || "?") +
        " (embedded when this HTML was generated)";
    }} else {{
      body.classList.add("d-none");
      empty.classList.remove("d-none");
      if (meta) meta.textContent = "";
    }}
    document.getElementById("btnRefreshMarketNarrative")?.addEventListener("click", async () => {{
      const btn = document.getElementById("btnRefreshMarketNarrative");
      if (btn) btn.disabled = true;
      try {{
        const u = new URL(NARRATIVE_API_BASE + "/api/market-narrative");
        u.searchParams.set("refresh", "1");
        u.searchParams.set("analysis_date", narrativeAnalysisDate);
        const r = await fetch(u.toString());
        if (!r.ok) throw new Error(await r.text());
        const j = await r.json();
        if (j.content) {{
          renderNarrativeIntoElement(body, j.content);
          body.classList.remove("d-none");
          empty.classList.add("d-none");
          if (meta) meta.textContent =
            "Model: " + (j.ollama_model || "?") + " — " + (j.cached ? "from cache" : "just generated") +
            ". Re-run dashboard generator to embed in this file.";
        }}
      }} catch (e) {{
        alert("Narrative API error (start narrative_llm_server on " + NARRATIVE_API_BASE + "): " + e);
      }}
      if (btn) btn.disabled = false;
    }});
  }}

  function setupStockNarrativeModalActions() {{
    document.getElementById("btnStockNarrativeFind")?.addEventListener("click", () => {{
      if (narrativeModalSymbol) focusStockFromHeatmap(narrativeModalSymbol);
      const el = document.getElementById("stockNarrativeModal");
      if (el && window.bootstrap && bootstrap.Modal) bootstrap.Modal.getInstance(el)?.hide();
    }});
    document.getElementById("btnStockNarrativeFetch")?.addEventListener("click", async () => {{
      if (!narrativeModalSymbol) return;
      const btn = document.getElementById("btnStockNarrativeFetch");
      const statusEl = document.getElementById("stockNarrativeStatus");
      const bodyEl = document.getElementById("stockNarrativeBody");
      const embedMetaEl = document.getElementById("stockNarrativeEmbedMeta");
      if (btn) btn.disabled = true;
      if (statusEl) {{ statusEl.classList.remove("d-none"); statusEl.textContent = "Calling Ollama…"; }}
      try {{
        const u = new URL(NARRATIVE_API_BASE + "/api/stock-narrative");
        u.searchParams.set("symbol", narrativeModalSymbol);
        u.searchParams.set("analysis_date", narrativeAnalysisDate);
        u.searchParams.set("refresh", "1");
        const r = await fetch(u.toString());
        if (!r.ok) throw new Error(await r.text());
        const j = await r.json();
        if (j.content && bodyEl) renderNarrativeIntoElement(bodyEl, j.content);
        if (embedMetaEl) embedMetaEl.textContent =
          "Saved to SQLite — re-run dashboard generator to embed. Model: " + (j.ollama_model || "?");
        if (statusEl) statusEl.textContent = j.cached ? "Returned cached after refresh." : "Generated and stored in llm_narratives.";
      }} catch (e) {{
        if (statusEl) statusEl.textContent = "Error: " + e;
      }}
      if (btn) btn.disabled = false;
    }});
  }}

  function renderFundamentalsTable(data) {{
    const tbody = document.getElementById("fundamentalsTableBody");
    if (!tbody) return;
    const frag = document.createDocumentFragment();
    data.forEach(r => {{
      const tr = document.createElement("tr");
      tr.dataset.symbol = r.symbol || "";
      const co = escHtml(r.companyName);
      const peStr = (r.peTtm !== null && r.peTtm !== undefined && Number.isFinite(Number(r.peTtm)))
        ? Number(r.peTtm).toFixed(2) : "—";
      tr.innerHTML =
        `<td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${{escHtml(r.companyName || r.symbol || "")}}"><strong>${{co}}</strong></td>` +
        `<td class="text-end">${{fmtFundNum(r.fundScore)}}</td>` +
        `<td class="text-end">${{fmtFundNum(r.earningsQuality)}}</td>` +
        `<td class="text-end">${{fmtFundNum(r.salesGrowth)}}</td>` +
        `<td class="text-end">${{fmtFundNum(r.financialStrength)}}</td>` +
        `<td class="text-end">${{fmtFundNum(r.institutionalBacking)}}</td>` +
        `<td class="small">${{r.fundDataDate ? escHtml(r.fundDataDate) : "—"}}</td>` +
        `<td class="text-end">${{fmtFundPct(r.profitYoyPct)}}</td>` +
        `<td class="text-end">${{fmtFundPct(r.salesReportedYoyPct)}}</td>` +
        `<td class="text-end">${{fmtFundPp(r.marginPpChange)}}</td>` +
        `<td class="text-end">${{peStr}}</td>` +
        `<td class="text-end">${{fmtFundPct(r.cfoChangeYoy)}}</td>` +
        `<td class="text-end">${{fmtFundPct(r.debtChangeYoy)}}</td>` +
        `<td class="small">${{r.ratiosPeriod ? escHtml(r.ratiosPeriod) : "—"}}</td>`;
      frag.appendChild(tr);
    }});
    tbody.innerHTML = "";
    tbody.appendChild(frag);
  }}

  function updateFundSortIndicators() {{
    document.querySelectorAll("#fundamentalsTable thead th[data-fcol]").forEach(th => {{
      th.classList.remove("sort-asc", "sort-desc");
      if (th.dataset.fcol === fundSortColumn) {{
        th.classList.add(fundSortDirection === "asc" ? "sort-asc" : "sort-desc");
      }}
    }});
  }}

  function applyFundamentalsFilterSort() {{
    const q = (document.getElementById("fundSearchBox")?.value || "").trim().toUpperCase();
    let rows = [...fundamentalsData];
    if (q) {{
      rows = rows.filter(r =>
        (r.symbol || "").toUpperCase().includes(q) ||
        (r.companyName || "").toUpperCase().includes(q)
      );
    }}
    const col = fundSortColumn;
    rows.sort((a, b) => {{
      let av = a[col];
      let bv = b[col];
      if (FUND_NUM_COLS.has(col)) {{
        const na = av === null || av === undefined || (typeof av === "number" && !Number.isFinite(av));
        const nb = bv === null || bv === undefined || (typeof bv === "number" && !Number.isFinite(bv));
        if (na && nb) return 0;
        if (na) return 1;
        if (nb) return -1;
        av = Number(av);
        bv = Number(bv);
      }} else {{
        av = String(av ?? "").toUpperCase();
        bv = String(bv ?? "").toUpperCase();
      }}
      if (av < bv) return fundSortDirection === "asc" ? -1 : 1;
      if (av > bv) return fundSortDirection === "asc" ? 1 : -1;
      return 0;
    }});
    renderFundamentalsTable(rows);
    const fc = document.getElementById("fundRowCount");
    if (fc) fc.textContent = rows.length.toLocaleString() + " of " + fundamentalsData.length.toLocaleString() + " rows";
  }}

  function setupFundamentalsSorting() {{
    document.querySelectorAll("#fundamentalsTable thead th[data-fcol]").forEach(th => {{
      th.addEventListener("click", () => {{
        const col = th.dataset.fcol;
        if (fundSortColumn === col) {{
          fundSortDirection = fundSortDirection === "asc" ? "desc" : "asc";
        }} else {{
          fundSortColumn = col;
          fundSortDirection = FUND_NUM_COLS.has(col) ? "desc" : "asc";
        }}
        updateFundSortIndicators();
        applyFundamentalsFilterSort();
      }});
    }});
  }}

  function capSlug(cap) {{
    return (cap || "").toUpperCase().replace(/\\s+/g, "_");
  }}

  function capClass(cap) {{
    const c = capSlug(cap);
    if (c.includes("LARGE")) return "tag-cap tag-cap-large";
    if (c.includes("MID"))   return "tag-cap tag-cap-mid";
    if (c.includes("SMALL")) return "tag-cap tag-cap-small";
    if (c.includes("MICRO")) return "tag-cap tag-cap-micro";
    return "tag-cap";
  }}

  function applyFiltersAndSort() {{
    const query = (document.getElementById("searchBox").value || "").trim().toUpperCase();
    let rows = [...stocksData];

    if (activeSignal !== "ALL") {{
      rows = rows.filter(s => (s.tradingSignal || "").toUpperCase() === activeSignal);
    }}
    if (activeCap !== "ALL") {{
      rows = rows.filter(s => capSlug(s.marketCap) === activeCap);
    }}
    if (query) {{
      rows = rows.filter(s =>
        (s.symbol || "").toUpperCase().includes(query) ||
        (s.companyName || "").toUpperCase().includes(query)
      );
    }}

    const NUM_COLS = new Set([
      "currentPrice", "change1D", "change1W", "change1M", "technicalScore", "rsi",
      "relativeStrength", "fundamental", "canSlim", "minervini",
    ]);
    rows.sort((a, b) => {{
      const col = currentSortColumn;
      let av = a[col];
      let bv = b[col];
      if (NUM_COLS.has(col)) {{
        const na = (av === null || av === undefined || (typeof av === "number" && Number.isNaN(av)));
        const nb = (bv === null || bv === undefined || (typeof bv === "number" && Number.isNaN(bv)));
        if (na && nb) return 0;
        if (na) return 1;
        if (nb) return -1;
        av = Number(av);
        bv = Number(bv);
      }} else {{
        av = String(av ?? "").toUpperCase();
        bv = String(bv ?? "").toUpperCase();
      }}
      if (av < bv) return currentSortDirection === "asc" ? -1 : 1;
      if (av > bv) return currentSortDirection === "asc" ? 1 : -1;
      return 0;
    }});

    renderTable(rows);
    const rc = document.getElementById("rowCount");
    if (rc) rc.textContent = rows.length.toLocaleString() + " of " + stocksData.length.toLocaleString() + " stocks";
  }}

  function renderTable(data) {{
    const tbody = document.getElementById("stocksTableBody");
    if (!tbody) return;
    const frag = document.createDocumentFragment();
    data.forEach(s => {{
      const tr = document.createElement("tr");
      tr.dataset.symbol = s.symbol || "";
      const c1d = s.change1D >= 0 ? "number-pos" : "number-neg";
      const c1w = s.change1W >= 0 ? "number-pos" : "number-neg";
      const c1m = s.change1M >= 0 ? "number-pos" : "number-neg";
      const hasRs = s.relativeStrength !== null && s.relativeStrength !== undefined;
      const crs = hasRs ? (s.relativeStrength >= 0 ? "number-pos" : "number-neg") : "";
      const rsCell = hasRs
        ? ((s.relativeStrength >= 0 ? "+" : "") + s.relativeStrength.toFixed(2) + "%")
        : "—";
      /* Treat null, undefined, and NaN as missing (invalid JSON can theoretically yield NaN in edge cases) */
      const hasFund =
        s.fundamental !== null &&
        s.fundamental !== undefined &&
        typeof s.fundamental === "number" &&
        Number.isFinite(s.fundamental);
      const fundCell = hasFund ? s.fundamental.toFixed(1) : "—";
      const trendSlug = (s.trendSignal || "").toLowerCase().replace(/_/g, "-");
      const sigSlug   = (s.tradingSignal || "").toLowerCase().replace(/_/g, "-");
      const trendDisp = escHtml((s.trendSignal || "").replace(/_/g, " "));
      const sigDisp   = escHtml((s.tradingSignal || "").replace(/_/g, " "));
      const capDisp   = escHtml((s.marketCap || "").replace(/_/g, " "));
      const symEsc    = escHtml(s.symbol);
      const coEsc     = escHtml(s.companyName);
      const sg1d = s.change1D >= 0 ? "+" : "";
      const sg1w = s.change1W >= 0 ? "+" : "";
      const sg1m = s.change1M >= 0 ? "+" : "";
      const priceStr = Number.isFinite(s.currentPrice)
        ? s.currentPrice.toLocaleString(undefined, {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }})
        : "—";
      tr.innerHTML =
        `<td><strong>${{symEsc}}</strong></td>` +
        `<td style="max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${{coEsc}}">${{coEsc}}</td>` +
        `<td><span class="${{capClass(s.marketCap)}}">${{capDisp}}</span></td>` +
        `<td class="text-end">₹${{priceStr}}</td>` +
        `<td class="text-end ${{c1d}}">${{sg1d}}${{s.change1D.toFixed(2)}}%</td>` +
        `<td class="text-end ${{c1w}}">${{sg1w}}${{s.change1W.toFixed(2)}}%</td>` +
        `<td class="text-end ${{c1m}}">${{sg1m}}${{s.change1M.toFixed(2)}}%</td>` +
        `<td class="text-end"><strong>${{s.technicalScore.toFixed(1)}}</strong></td>` +
        `<td class="text-end">${{s.rsi.toFixed(1)}}</td>` +
        `<td class="text-end ${{crs}}">${{rsCell}}</td>` +
        `<td class="text-end">${{fundCell}}</td>` +
        `<td class="text-end">${{s.canSlim}}</td>` +
        `<td class="text-end">${{s.minervini}}</td>` +
        `<td><span class="trend-pill trend-${{trendSlug}}">${{trendDisp}}</span></td>` +
        `<td><span class="signal-pill signal-${{sigSlug}}">${{sigDisp}}</span></td>` +
        `<td class="text-center"><button type="button" class="btn btn-sm btn-outline-info btn-narrative" data-symbol="${{symEsc}}" title="LLM narrative">AI</button></td>`;
      frag.appendChild(tr);
    }});
    tbody.innerHTML = "";
    tbody.appendChild(frag);
  }}

  function updateSortIndicators() {{
    document.querySelectorAll("#stocksTable thead th").forEach(th => {{
      th.classList.remove("sort-asc", "sort-desc");
      if (th.dataset.col === currentSortColumn) {{
        th.classList.add(currentSortDirection === "asc" ? "sort-asc" : "sort-desc");
      }}
    }});
  }}

  function setupSorting() {{
    document.querySelectorAll("#stocksTable thead th[data-col]").forEach(th => {{
      th.addEventListener("click", () => {{
        const col = th.dataset.col;
        if (currentSortColumn === col) {{
          currentSortDirection = currentSortDirection === "asc" ? "desc" : "asc";
        }} else {{
          currentSortColumn = col;
          const numCols = new Set([
            "currentPrice", "change1D", "change1W", "change1M", "technicalScore", "rsi",
            "relativeStrength", "fundamental", "canSlim", "minervini",
          ]);
          currentSortDirection = numCols.has(col) ? "desc" : "asc";
        }}
        updateSortIndicators();
        applyFiltersAndSort();
      }});
    }});
  }}

  function setupFilters() {{
    document.getElementById("signalFilters")?.querySelectorAll(".filter-btn").forEach(btn => {{
      btn.addEventListener("click", () => {{
        document.getElementById("signalFilters").querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        activeSignal = (btn.dataset.signal || "ALL").toUpperCase();
        applyFiltersAndSort();
      }});
    }});
    document.getElementById("capFilters")?.querySelectorAll(".filter-btn").forEach(btn => {{
      btn.addEventListener("click", () => {{
        document.getElementById("capFilters").querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        activeCap = (btn.dataset.cap || "ALL").toUpperCase();
        applyFiltersAndSort();
      }});
    }});
    document.getElementById("searchBox")?.addEventListener("input", applyFiltersAndSort);
  }}

  function getHeatmapScoreClass(score) {{
    if (score >= 80) return "excellent";
    if (score >= 65) return "good";
    if (score >= 50) return "moderate";
    if (score >= 35) return "poor";
    return "very-poor";
  }}

  function focusStockFromHeatmap(symbol) {{
    if (!symbol) return;
    const tabBtn = document.getElementById("tab-universe-btn");
    if (tabBtn) {{
      if (window.bootstrap && bootstrap.Tab) {{
        try {{ new bootstrap.Tab(tabBtn).show(); }} catch (e) {{ tabBtn.click(); }}
      }} else {{
        tabBtn.click();
      }}
    }}
    document.querySelectorAll("#breadthHeatmap .heatmap-cell").forEach(c => c.classList.remove("is-selected"));
    const match = document.querySelector(`#breadthHeatmap .heatmap-cell[data-symbol="${{CSS.escape(symbol)}}"]`);
    if (match) match.classList.add("is-selected");
    activeSignal = "ALL";
    activeCap = "ALL";
    document.getElementById("signalFilters")?.querySelectorAll(".filter-btn").forEach(b => {{
      b.classList.toggle("active", (b.dataset.signal || "ALL") === "ALL");
    }});
    document.getElementById("capFilters")?.querySelectorAll(".filter-btn").forEach(b => {{
      b.classList.toggle("active", (b.dataset.cap || "ALL") === "ALL");
    }});
    const sb = document.getElementById("searchBox");
    if (sb) sb.value = symbol;
    applyFiltersAndSort();
    setTimeout(() => {{
      const row = document.querySelector(`#stocksTableBody tr[data-symbol="${{CSS.escape(symbol)}}"]`);
      if (row) {{
        row.scrollIntoView({{ block: "center", behavior: "smooth" }});
        document.querySelectorAll("#stocksTableBody tr.row-highlight").forEach(r => r.classList.remove("row-highlight"));
        row.classList.add("row-highlight");
        setTimeout(() => row.classList.remove("row-highlight"), 2800);
      }}
    }}, 200);
  }}

  /** Double-click heat map: clear symbol search, reset signal/cap filters, remove cell highlight */
  function clearHeatmapFocusAndFilters() {{
    activeSignal = "ALL";
    activeCap = "ALL";
    document.getElementById("signalFilters")?.querySelectorAll(".filter-btn").forEach(b => {{
      b.classList.toggle("active", (b.dataset.signal || "ALL") === "ALL");
    }});
    document.getElementById("capFilters")?.querySelectorAll(".filter-btn").forEach(b => {{
      b.classList.toggle("active", (b.dataset.cap || "ALL") === "ALL");
    }});
    const sb = document.getElementById("searchBox");
    if (sb) sb.value = "";
    document.querySelectorAll("#breadthHeatmap .heatmap-cell").forEach(c => c.classList.remove("is-selected"));
    applyFiltersAndSort();
  }}

  /** R-style heatmap: up to 50 cells, 10 columns — top names by technical score */
  function generateHeatmap() {{
    const container = document.getElementById("breadthHeatmap");
    if (!container || !stocksData || !stocksData.length) return;
    container.innerHTML = "";
    const sorted = [...stocksData].sort((a, b) => b.technicalScore - a.technicalScore);
    const frag = document.createDocumentFragment();
    const maxCells = Math.min(50, sorted.length);
    for (let index = 0; index < maxCells; index++) {{
      const s = sorted[index];
      const sc = s.technicalScore;
      const cell = document.createElement("div");
      const sym = (s.symbol || "").trim();
      cell.className = "heatmap-cell " + getHeatmapScoreClass(sc);
      cell.dataset.symbol = sym;
      const shortSym = sym.length > 4 ? sym.substring(0, 4) : sym;
      const fund = s.fundamental;
      const hasFund = fund !== null && fund !== undefined && typeof fund === "number" && Number.isFinite(fund);
      cell.innerHTML =
        "<span class=\\"hm-line1\\">" + escHtml(shortSym) + "</span>" +
        (hasFund ? "<span class=\\"hm-line2\\">F " + fund.toFixed(0) + "</span>" : "");
      cell.title =
        "Click to find " + sym + " in the table\\n" +
        String(s.companyName || sym) + "\\n" +
        "Technical: " + sc.toFixed(1) +
        (hasFund ? "\\nFundamental: " + fund.toFixed(1) : "") +
        "\\nSignal: " + String(s.tradingSignal || "") + "\\nRank: " + (index + 1) +
        "\\nDouble-click to clear search & filters";
      cell.addEventListener("click", () => openStockNarrativeModal(sym));
      frag.appendChild(cell);
    }}
    container.appendChild(frag);
    /* Delegated dblclick: clear filters (bind once — container persists across rebuilds) */
    if (!container.dataset.dblClearBound) {{
      container.dataset.dblClearBound = "1";
      container.addEventListener("dblclick", (e) => {{
        const cell = e.target && e.target.closest && e.target.closest(".heatmap-cell");
        if (!cell) return;
        e.preventDefault();
        clearHeatmapFocusAndFilters();
      }});
    }}
  }}

  function initCharts() {{
    try {{
      const sigLabels = {signal_chart_labels_json};
      const sigValues = {signal_chart_values_json};
      const elSig = document.getElementById("signalsChart");
      if (elSig && sigLabels.length && sigValues.length && typeof Chart !== "undefined") {{
        const sigColors = sigLabels.map(l => {{
          const u = String(l).toUpperCase();
          if (u === "STRONG_BUY")  return "#16a34a";
          if (u === "BUY")         return "#4ade80";
          if (u === "HOLD")        return "#eab308";
          if (u === "WEAK_HOLD")   return "#f97316";
          if (u === "SELL")        return "#ef4444";
          if (u === "STRONG_SELL") return "#b91c1c";
          return "#6366f1";
        }});
        new Chart(elSig, {{
          type: "doughnut",
          data: {{ labels: sigLabels, datasets: [{{ data: sigValues, backgroundColor: sigColors, borderWidth: 0 }}] }},
          options: {{
            responsive: true,
            maintainAspectRatio: false,
            layout: {{ padding: {{ top: 6, bottom: 6, left: 4, right: 4 }} }},
            plugins: {{
              legend: {{
                position: "bottom",
                align: "center",
                labels: {{
                  boxWidth: 12,
                  boxHeight: 12,
                  padding: 10,
                  font: {{ size: 10 }},
                  usePointStyle: true,
                }},
              }},
            }},
          }},
        }});
      }}

      const capLabels = {cap_chart_labels_json};
      const capValues = {cap_chart_values_json};
      const elCap = document.getElementById("capChart");
      if (elCap && capLabels.length && capValues.length && typeof Chart !== "undefined") {{
        new Chart(elCap, {{
          type: "bar",
          data: {{ labels: capLabels, datasets: [{{ data: capValues, backgroundColor: "rgba(56,189,248,.62)", borderRadius: 4, borderSkipped: false }}] }},
          options: {{
            responsive: true,
            maintainAspectRatio: false,
            layout: {{ padding: {{ top: 8, bottom: 4, left: 4, right: 8 }} }},
            plugins: {{ legend: {{ display: false }} }},
            scales: {{
              x: {{ ticks: {{ font: {{ size: 10 }}, maxRotation: 35, minRotation: 0 }}, grid: {{ color: "rgba(148,163,184,.1)" }} }},
              y: {{ beginAtZero: true, ticks: {{ font: {{ size: 10 }} }}, grid: {{ color: "rgba(148,163,184,.1)" }} }},
            }},
          }},
        }});
      }}
    }} catch (e) {{
      console.warn("Chart init skipped:", e);
    }}
  }}

  /** Re-fit Chart.js when Overview tab becomes visible (hidden tabs have zero width on first paint). */
  function resizeOverviewCharts() {{
    if (typeof Chart === "undefined") return;
    ["signalsChart", "capChart"].forEach((id) => {{
      const el = document.getElementById(id);
      if (!el) return;
      const ch = Chart.getChart(el);
      if (ch) ch.resize();
    }});
  }}

  document.addEventListener("DOMContentLoaded", () => {{
    try {{
      updateSortIndicators();
      applyFiltersAndSort();
      setupSorting();
      setupFilters();
      generateHeatmap();
      initCharts();
      initMarketNarrativePanel();
      setupStockNarrativeModalActions();
      document.getElementById("stocksTableBody")?.addEventListener("click", (e) => {{
        const b = e.target.closest(".btn-narrative");
        if (b && b.dataset.symbol) openStockNarrativeModal(b.dataset.symbol);
      }});
      updateFundSortIndicators();
      applyFundamentalsFilterSort();
      setupFundamentalsSorting();
      document.getElementById("fundSearchBox")?.addEventListener("input", applyFundamentalsFilterSort);
      document.querySelectorAll("#dashTabNav button[data-bs-toggle='tab']").forEach((btn) => {{
        btn.addEventListener("shown.bs.tab", () => {{
          const target = btn.getAttribute("data-bs-target") || "";
          if (target === "#tabOverview") {{
            requestAnimationFrame(() => resizeOverviewCharts());
          }}
        }});
      }});
      window.addEventListener("resize", () => {{
        if (document.getElementById("tabOverview")?.classList.contains("active")) {{
          resizeOverviewCharts();
        }}
      }});
    }} catch (e) {{
      console.error("Dashboard init error:", e);
    }}
  }});
</script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"
        integrity="sha384-YvpcrYf0tY3lHB60NNkmXc5s9fDVZLESaAA55NDzOxhy9GkcIdslK1eN7N6jIeHz"
        crossorigin="anonymous"></script>
</body>
</html>
"""
    return html_content


def generate_dashboard() -> Path:
    """
    High-level entry: load latest data and write the HTML dashboard file.
    """
    csv_path = _find_latest_stocks_csv()
    stocks, csv_snapshot_date = _load_stocks_and_latest_date(csv_path)
    db_as_of = _load_db_as_of_date()
    as_of_date = db_as_of if db_as_of is not None else csv_snapshot_date
    indexes = _load_index_summary(as_of_date)
    market_narr, stock_narr_map = _load_llm_narratives_for_date(as_of_date)
    dash_data = DashboardData(
        as_of_date=as_of_date,
        csv_snapshot_date=csv_snapshot_date,
        stocks=stocks,
        indexes=indexes,
        market_narrative_embed=market_narr,
        stock_narratives_embed=stock_narr_map,
    )

    html_content = _render_html(dash_data)
    filename = REPORTS_DIR / f"NSE_Interactive_Dashboard_{as_of_date.strftime('%Y%m%d')}.html"
    filename.write_text(html_content, encoding="utf-8")
    print(f"HTML dashboard saved to: {filename}")
    return filename


if __name__ == "__main__":
    generate_dashboard()

