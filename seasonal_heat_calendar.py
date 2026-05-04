"""
seasonal_heat_calendar.py  —  B3: Sectoral Heat Calendar
=========================================================
Builds a 12 × N_sectors matrix of average monthly returns from NSE index history.
Provides TAILWIND / HEADWIND / NEUTRAL signals for the current month.
Renders a standalone HTML heatmap table embeddable in the sector rotation report.
"""
from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
_DATA_DIR = Path(__file__).parent / "data"
_INDEX_CSV = _DATA_DIR / "nse_index_data.csv"
_CACHE_CSV = _DATA_DIR / "seasonal_monthly_returns.csv"
_CACHE_TTL_DAYS = 7  # refresh once a week

_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Thresholds per backlog spec
_TAILWIND_PCT = 2.0   # avg monthly return > +2% → TAILWIND
_HEADWIND_PCT = -1.0  # avg monthly return < -1% → HEADWIND
_MIN_OBS = 5          # minimum observations required for a signal


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _load_index_data() -> pd.DataFrame:
    df = pd.read_csv(_INDEX_CSV, parse_dates=["TIMESTAMP"])
    return df


def _build_monthly_returns(index_symbols: list[str]) -> pd.DataFrame:
    """Return a long-form DataFrame: [symbol, period, month_num, return_pct]."""
    df = _load_index_data()
    df = df[df["SYMBOL"].isin(index_symbols)].copy()

    # Last trading day close per calendar month per symbol
    df["period"] = df["TIMESTAMP"].dt.to_period("M")
    monthly = (
        df.sort_values("TIMESTAMP")
        .groupby(["SYMBOL", "period"])
        .last()
        .reset_index()[["SYMBOL", "period", "CLOSE"]]
    )

    monthly["return_pct"] = (
        monthly.groupby("SYMBOL")["CLOSE"].pct_change() * 100
    )
    monthly["month_num"] = monthly["period"].dt.month
    monthly = monthly.dropna(subset=["return_pct"])
    return monthly


# ---------------------------------------------------------------------------
# Core: build heat matrix
# ---------------------------------------------------------------------------

def build_seasonal_heat_calendar(
    index_to_sector: dict[str, str],
    lookback_years: int = 7,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns (matrix, heat) where:
    - matrix  : 12-row (months) × N-sector columns of avg return %
    - heat    : long-form with [sector, month_num, avg, std, n]
    """
    cutoff = pd.Timestamp.now() - pd.DateOffset(years=lookback_years)

    # Check cache
    if _CACHE_CSV.exists():
        age_days = (datetime.now() - datetime.fromtimestamp(_CACHE_CSV.stat().st_mtime)).days
        if age_days < _CACHE_TTL_DAYS:
            cached = pd.read_csv(_CACHE_CSV)
            if set(index_to_sector.keys()).issubset(set(cached["symbol"].unique())):
                monthly_long = cached
                _apply_sector_names(monthly_long, index_to_sector)
                return _pivot_heat(monthly_long)

    symbols = list(index_to_sector.keys())
    monthly_long = _build_monthly_returns(symbols)
    monthly_long = monthly_long[monthly_long["period"].dt.to_timestamp() >= cutoff]
    monthly_long = monthly_long.rename(columns={"SYMBOL": "symbol"})
    monthly_long.to_csv(_CACHE_CSV, index=False)

    _apply_sector_names(monthly_long, index_to_sector)
    return _pivot_heat(monthly_long)


def _apply_sector_names(df: pd.DataFrame, index_to_sector: dict[str, str]) -> None:
    df["sector"] = df["symbol"].map(index_to_sector).fillna(df["symbol"])


def _pivot_heat(monthly_long: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    heat = (
        monthly_long.groupby(["sector", "month_num"])["return_pct"]
        .agg(avg="mean", std="std", n="count")
        .reset_index()
    )

    matrix = heat.pivot_table(index="month_num", columns="sector", values="avg")
    matrix.index = [_MONTH_NAMES[i - 1] for i in matrix.index]
    return matrix, heat


# ---------------------------------------------------------------------------
# Signal extraction
# ---------------------------------------------------------------------------

def get_seasonal_signal(sector: str, month: int, heat: pd.DataFrame) -> str:
    """Return TAILWIND / HEADWIND / NEUTRAL for a sector in a given month."""
    row = heat[(heat["sector"] == sector) & (heat["month_num"] == month)]
    if row.empty or int(row.iloc[0]["n"]) < _MIN_OBS:
        return "NEUTRAL"
    avg = float(row.iloc[0]["avg"])
    if avg > _TAILWIND_PCT:
        return "TAILWIND"
    if avg < _HEADWIND_PCT:
        return "HEADWIND"
    return "NEUTRAL"


def get_all_seasonal_signals(heat: pd.DataFrame, month: Optional[int] = None) -> dict[str, str]:
    """Return {sector: signal} for the given month (defaults to current month)."""
    if month is None:
        month = datetime.now().month
    sectors = heat["sector"].unique()
    return {s: get_seasonal_signal(s, month, heat) for s in sectors}


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------

_CELL_COLORS = [
    (-10, "#b91c1c"),   # deep red
    (-5,  "#dc2626"),
    (-2,  "#f87171"),
    (-1,  "#fca5a5"),
    (0,   "#fde68a"),   # yellow neutral
    (1,   "#bbf7d0"),
    (2,   "#4ade80"),
    (5,   "#16a34a"),
    (10,  "#14532d"),   # deep green
]


def _cell_color(val: float) -> tuple[str, str]:
    """Return (background, text) CSS color for a return value."""
    if math.isnan(val):
        return "#f1f5f9", "#94a3b8"
    bg = _CELL_COLORS[0][1]
    for threshold, color in _CELL_COLORS:
        if val >= threshold:
            bg = color
    # Choose text color based on darkness
    dark_bgs = {"#b91c1c", "#dc2626", "#14532d", "#16a34a"}
    text = "#ffffff" if bg in dark_bgs else "#1e293b"
    return bg, text


def _arrow(val: float) -> str:
    if math.isnan(val):
        return "—"
    if val > 1.0:
        return "↑"
    if val < -0.5:
        return "↓"
    return "→"


def render_heat_calendar_html(
    matrix: pd.DataFrame,
    current_month: Optional[int] = None,
) -> str:
    """
    Returns a self-contained HTML <div> containing the 12×N_sectors heatmap.
    Current month column is outlined in blue.
    """
    if current_month is None:
        current_month = datetime.now().month
    cur_month_name = _MONTH_NAMES[current_month - 1]

    sectors = list(matrix.columns)

    # Shorten long sector names for display
    _short = {
        "Defence & Aerospace": "Defence",
        "EV & Auto Ancillaries": "EV/Auto",
        "Energy - Power": "Power",
        "Energy - Oil & Gas": "Oil & Gas",
        "Pharma & Healthcare": "Pharma",
        "FMCG & Consumer Goods": "FMCG",
        "Metals & Mining": "Metals",
    }
    short_names = [_short.get(s, s) for s in sectors]

    # Header row
    header_cells = '<th style="min-width:48px;text-align:left;padding:5px 8px;border-bottom:2px solid #e2e8f0">Month</th>'
    for i, s in enumerate(sectors):
        is_cur_col = False  # columns not linked to months; skip col highlight
        style = "min-width:68px;text-align:center;padding:5px 6px;font-size:10px;border-bottom:2px solid #e2e8f0"
        header_cells += f'<th style="{style}">{short_names[i]}</th>'

    # Data rows
    data_rows = ""
    for month_name in _MONTH_NAMES:
        is_cur_row = (month_name == cur_month_name)
        row_style = (
            "background:#eff6ff;font-weight:700;outline:2px solid #3b82f6;outline-offset:-1px"
            if is_cur_row else ""
        )
        row_html = (
            f'<td style="padding:4px 8px;font-size:11px;font-weight:{"700" if is_cur_row else "500"};'
            f'white-space:nowrap;{"color:#1d4ed8;" if is_cur_row else "color:#475569;"}">'
            f'{month_name}{"  ◀" if is_cur_row else ""}</td>'
        )
        for s in sectors:
            try:
                val = float(matrix.loc[month_name, s])
            except (KeyError, TypeError, ValueError):
                val = float("nan")
            bg, fg = _cell_color(val)
            arrow = _arrow(val)
            val_str = f"{val:+.1f}%" if not math.isnan(val) else "n/a"
            row_html += (
                f'<td style="text-align:center;padding:4px 6px;background:{bg};color:{fg};'
                f'font-size:10.5px;font-weight:600;border-radius:3px;cursor:default" '
                f'title="{s}: {val_str}">'
                f'{arrow} {val_str}</td>'
            )
        data_rows += f'<tr style="{row_style}">{row_html}</tr>'

    legend_html = (
        '<div style="display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap">'
        '<span style="font-size:10px;color:#64748b">Return avg:</span>'
        '<span style="background:#b91c1c;color:#fff;padding:2px 6px;border-radius:3px;font-size:9px">&lt; -5%</span>'
        '<span style="background:#f87171;color:#1e293b;padding:2px 6px;border-radius:3px;font-size:9px">-2% to -5%</span>'
        '<span style="background:#fde68a;color:#1e293b;padding:2px 6px;border-radius:3px;font-size:9px">-1% to +1%</span>'
        '<span style="background:#4ade80;color:#1e293b;padding:2px 6px;border-radius:3px;font-size:9px">+2% to +5%</span>'
        '<span style="background:#16a34a;color:#fff;padding:2px 6px;border-radius:3px;font-size:9px">&gt; +5%</span>'
        '<span style="background:#eff6ff;outline:2px solid #3b82f6;outline-offset:-1px;padding:2px 6px;font-size:9px;border-radius:3px">Current month</span>'
        '</div>'
    )

    html = (
        f'<div class="heat-calendar-wrap" style="overflow-x:auto;margin:0 0 16px">'
        f'<div style="font-size:12px;font-weight:600;color:var(--primary,#1e40af);margin-bottom:6px">'
        f'Sectoral Seasonality (7-year avg monthly returns)</div>'
        f'<table style="border-collapse:separate;border-spacing:2px;width:100%">'
        f'<thead><tr>{header_cells}</tr></thead>'
        f'<tbody>{data_rows}</tbody>'
        f'</table>'
        f'{legend_html}'
        f'</div>'
    )
    return html


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def load_seasonal_calendar(
    index_to_sector: dict[str, str],
    force: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, str, dict[str, str]]:
    """
    Returns (matrix, heat, calendar_html, signals_dict).
    signals_dict: {sector_name: TAILWIND|HEADWIND|NEUTRAL} for current month.
    """
    if force and _CACHE_CSV.exists():
        _CACHE_CSV.unlink()

    matrix, heat = build_seasonal_heat_calendar(index_to_sector)
    calendar_html = render_heat_calendar_html(matrix)
    signals = get_all_seasonal_signals(heat)
    return matrix, heat, calendar_html, signals


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="B3 Sectoral Heat Calendar")
    ap.add_argument("--force", action="store_true", help="Bypass cache")
    ap.add_argument("--out", default="reports/latest/seasonal_calendar.html",
                    help="Output HTML path")
    args = ap.parse_args()

    # Import ROTATING_INDEXES from the report module
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from sector_rotation_report import ROTATING_INDEXES
        idx_map = ROTATING_INDEXES
    except ImportError:
        idx_map = {
            "Nifty Auto": "EV & Auto Ancillaries",
            "Nifty Bank": "Banking",
            "Nifty FMCG": "FMCG & Consumer Goods",
            "NIFTY HEALTHCARE": "Pharma & Healthcare",
            "Nifty IT": "IT & Technology",
            "Nifty Metal": "Metals & Mining",
            "Nifty Pharma": "Pharma & Healthcare",
            "Nifty Realty": "Realty",
            "NIFTY OIL AND GAS": "Energy - Oil & Gas",
            "Nifty Energy": "Energy - Power",
        }

    matrix, heat, cal_html, signals = load_seasonal_calendar(idx_map, force=args.force)

    print("\nSeasonal signals for current month:")
    for sec, sig in sorted(signals.items()):
        print(f"  {sec:35s}  {sig}")

    print(f"\nMonthly return matrix ({len(matrix.columns)} sectors):")
    print(matrix.round(1).to_string())

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    full_html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>Sectoral Heat Calendar</title>"
        "<style>body{font-family:system-ui,sans-serif;padding:24px;background:#f8fafc}</style>"
        "</head><body>"
        + cal_html
        + "</body></html>"
    )
    out.write_text(full_html, encoding="utf-8")
    print(f"\nCalendar written to {out}")
