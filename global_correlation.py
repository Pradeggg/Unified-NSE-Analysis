#!/usr/bin/env python3
"""B2: Global Correlation Monitor — rolling correlation of Nifty500 vs global assets.

Fetches global indices/commodities via yfinance, computes 30d and 60d rolling
correlation with the Nifty 500 index, and flags decoupling events when the
two windows diverge by more than 20 percentage points.

PG: B2 backlog item — global context for the sector rotation report.
"""
from __future__ import annotations

import html as html_mod
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_CSV = DATA_DIR / "global_indices.csv"
CORR_CSV = DATA_DIR / "global_correlations.csv"
NIFTY_INDEX_CSV = DATA_DIR / "nse_index_data.csv"
CACHE_TTL_HOURS = 24  # re-fetch once a day

# Global tickers — per B2 backlog spec
GLOBAL_TICKERS: dict[str, str] = {
    "S&P 500":    "^GSPC",
    "Nasdaq":     "^IXIC",
    "Hang Seng":  "^HSI",
    "Nikkei 225": "^N225",
    "Gold":       "GC=F",
    "Crude Oil":  "CL=F",
    "Copper":     "HG=F",
    "DXY":        "DX-Y.NYB",
    "USDINR":     "USDINR=X",
}

CORR_WINDOW_SHORT = 30  # days
CORR_WINDOW_LONG = 60   # days
DECOUPLE_THRESHOLD = 0.20  # |corr_30d − corr_60d| > 0.20 → DECOUPLING


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def _cache_is_fresh() -> bool:
    """Check if the global indices cache is fresh (< CACHE_TTL_HOURS old)."""
    if not CACHE_CSV.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(CACHE_CSV.stat().st_mtime)
    return age < timedelta(hours=CACHE_TTL_HOURS)


def fetch_global_indices(
    tickers: dict[str, str] | None = None,
    lookback_days: int = 120,
    force: bool = False,
) -> pd.DataFrame:
    """Fetch daily close prices for global assets via yfinance.

    Returns a DataFrame indexed by Date with one column per asset name.
    Results are cached to ``data/global_indices.csv`` with a 24-hour TTL.
    """
    if not force and _cache_is_fresh():
        cached = pd.read_csv(CACHE_CSV, index_col=0, parse_dates=True)
        if not cached.empty:
            return cached

    tickers = tickers or GLOBAL_TICKERS
    try:
        import yfinance as yf
    except ImportError:
        print("  yfinance not installed — global correlation skipped.")
        return pd.DataFrame()

    period = f"{lookback_days}d"
    data: dict[str, pd.Series] = {}
    for name, ticker in tickers.items():
        try:
            hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
            if hist is not None and not hist.empty and "Close" in hist.columns:
                series = hist["Close"].dropna()
                series.index = series.index.tz_localize(None)  # strip timezone
                data[name] = series
        except Exception:
            pass  # PG: missing global index is non-fatal per spec

    if not data:
        return pd.DataFrame()

    result = pd.DataFrame(data).sort_index()
    result.index.name = "Date"
    # PG: persist cache
    CACHE_CSV.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(CACHE_CSV)
    return result


# ---------------------------------------------------------------------------
# Nifty 500 close series from local NSE data
# ---------------------------------------------------------------------------

def _load_nifty500_close(index_csv: Path = NIFTY_INDEX_CSV) -> pd.Series:
    """Load Nifty 500 daily close from local NSE index data."""
    if not index_csv.exists():
        return pd.Series(dtype=float, name="Nifty 500")
    df = pd.read_csv(index_csv, usecols=["SYMBOL", "TIMESTAMP", "CLOSE"])
    df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip()
    mask = df["SYMBOL"].str.upper().isin(["NIFTY 500", "NIFTY500"])
    df = df[mask].copy()
    df["Date"] = pd.to_datetime(df["TIMESTAMP"], errors="coerce")
    df["CLOSE"] = pd.to_numeric(df["CLOSE"], errors="coerce")
    df = df.dropna(subset=["Date", "CLOSE"]).sort_values("Date")
    return df.set_index("Date")["CLOSE"].rename("Nifty 500")


# ---------------------------------------------------------------------------
# Correlation computation
# ---------------------------------------------------------------------------

def compute_correlations(
    nifty_series: pd.Series,
    global_df: pd.DataFrame,
    short_window: int = CORR_WINDOW_SHORT,
    long_window: int = CORR_WINDOW_LONG,
) -> pd.DataFrame:
    """Compute rolling correlations of Nifty500 vs each global asset.

    Returns a DataFrame with columns:
        asset, price, corr_30d, corr_60d, change, alert
    Where alert is DECOUPLING if |corr_30d − corr_60d| > threshold.
    """
    if nifty_series.empty or global_df.empty:
        return pd.DataFrame(columns=["asset", "price", "corr_30d", "corr_60d", "change", "alert"])

    # PG: align dates — forward-fill to handle different holiday calendars
    # between NSE and global markets, but truncate to Nifty's real range
    # to avoid stale ffill values producing 0% returns
    combined = global_df.copy()
    nifty_aligned = nifty_series.reindex(combined.index, method="ffill")
    combined["Nifty 500"] = nifty_aligned
    combined = combined.dropna(subset=["Nifty 500"])
    # PG: only keep dates within Nifty's actual data range
    nifty_end = nifty_series.index.max()
    combined = combined[combined.index <= nifty_end]

    if len(combined) < long_window:
        return pd.DataFrame(columns=["asset", "price", "corr_30d", "corr_60d", "change", "alert"])

    # PG: per-column returns — don't drop rows globally because
    # different assets have different trading calendars
    returns = combined.pct_change().iloc[1:]  # drop first NaN row only

    rows: list[dict[str, Any]] = []
    for asset in global_df.columns:
        if asset == "Nifty 500":
            continue
        if asset not in returns.columns:
            continue
        asset_ret = returns[asset].dropna()
        nifty_ret = returns["Nifty 500"].reindex(asset_ret.index).dropna()
        common = asset_ret.index.intersection(nifty_ret.index)
        if len(common) < short_window:
            continue
        asset_ret = asset_ret.loc[common]
        nifty_ret = nifty_ret.loc[common]

        corr_short = float(asset_ret.tail(short_window).corr(nifty_ret.tail(short_window)))
        corr_long = float(asset_ret.tail(long_window).corr(nifty_ret.tail(long_window)))
        change = corr_short - corr_long
        decoupling = abs(change) > DECOUPLE_THRESHOLD

        # PG: latest price from the raw global_df (not truncated) for display
        latest_price = float(global_df[asset].dropna().iloc[-1]) if asset in global_df.columns and not global_df[asset].dropna().empty else math.nan
        rows.append({
            "asset": asset,
            "price": round(latest_price, 2) if not math.isnan(latest_price) else math.nan,
            "corr_30d": round(corr_short, 3) if not math.isnan(corr_short) else math.nan,
            "corr_60d": round(corr_long, 3) if not math.isnan(corr_long) else math.nan,
            "change": round(change, 3) if not math.isnan(change) else math.nan,
            "alert": "DECOUPLING" if decoupling else "STABLE",
        })

    return pd.DataFrame(rows).sort_values("asset").reset_index(drop=True)


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def _corr_color(val: float) -> tuple[str, str]:
    """Return (background, text) CSS colors for a correlation value."""
    if math.isnan(val):
        return "#f1f5f9", "#94a3b8"
    if val > 0.6:
        return "#dcfce7", "#166534"
    if val > 0.3:
        return "#ecfdf5", "#047857"
    if val > -0.3:
        return "#f8fafc", "#475569"
    if val > -0.6:
        return "#fef2f2", "#b91c1c"
    return "#fee2e2", "#991b1b"


def correlation_context_html(corr_df: pd.DataFrame) -> str:
    """Compact context strip for the sector rotation report header.

    Shows key correlations and any decoupling alerts inline.
    """
    if corr_df is None or corr_df.empty:
        return ""

    # PG: pick most relevant assets for the compact strip
    key_assets = ["S&P 500", "Gold", "Crude Oil", "DXY", "USDINR"]
    parts: list[str] = []
    decouples: list[str] = []

    for _, row in corr_df.iterrows():
        asset = str(row.get("asset", ""))
        if asset not in key_assets:
            continue
        c30 = row.get("corr_30d", math.nan)
        alert = str(row.get("alert", ""))
        c_str = f"{c30:+.2f}" if not math.isnan(c30) else "n/a"
        parts.append(f"{asset} {c_str}")
        if alert == "DECOUPLING":
            decouples.append(asset)

    if not parts:
        return ""

    # PG: choose tone based on decoupling count
    if decouples:
        bg, fg = "#fef9c3", "#854d0e"  # amber — decoupling detected
        label = f"⚠ Decoupling: {', '.join(decouples)}"
    else:
        bg, fg = "#f0f9ff", "#0c4a6e"  # cool blue — stable
        label = "Stable"

    metric_spans = " · ".join(parts)
    return (
        f'<div class="breadth-strip" style="background:{bg};color:{fg};border-color:rgba(0,0,0,.08)">'
        f'<span class="breadth-kicker" style="color:{fg}">Global Corr</span>'
        f'<span class="breadth-context" style="color:{fg}">{html_mod.escape(label)}</span>'
        f'<span>{html_mod.escape(metric_spans)}</span>'
        f'</div>'
    )


def render_correlation_table_html(corr_df: pd.DataFrame) -> str:
    """Full correlation table HTML for embedding as a card in the report."""
    if corr_df is None or corr_df.empty:
        return ""

    header = (
        '<tr>'
        '<th style="text-align:left;padding:6px 10px;border-bottom:2px solid #e2e8f0">Asset</th>'
        '<th style="text-align:right;padding:6px 8px;border-bottom:2px solid #e2e8f0">Price</th>'
        '<th style="text-align:center;padding:6px 8px;border-bottom:2px solid #e2e8f0">30d Corr</th>'
        '<th style="text-align:center;padding:6px 8px;border-bottom:2px solid #e2e8f0">60d Corr</th>'
        '<th style="text-align:center;padding:6px 8px;border-bottom:2px solid #e2e8f0">Δ</th>'
        '<th style="text-align:center;padding:6px 8px;border-bottom:2px solid #e2e8f0">Alert</th>'
        '</tr>'
    )

    rows = ""
    for _, row in corr_df.iterrows():
        asset = html_mod.escape(str(row.get("asset", "")))
        price = row.get("price", math.nan)
        c30 = row.get("corr_30d", math.nan)
        c60 = row.get("corr_60d", math.nan)
        change = row.get("change", math.nan)
        alert = str(row.get("alert", "STABLE"))

        bg30, fg30 = _corr_color(c30)
        bg60, fg60 = _corr_color(c60)

        # PG: format price — use commas for large numbers
        if math.isnan(price):
            price_s = "n/a"
        elif price >= 1000:
            price_s = f"{price:,.0f}"
        else:
            price_s = f"{price:,.2f}"
        c30_s = f"{c30:+.3f}" if not math.isnan(c30) else "n/a"
        c60_s = f"{c60:+.3f}" if not math.isnan(c60) else "n/a"
        chg_s = f"{change:+.3f}" if not math.isnan(change) else "n/a"

        alert_bg, alert_fg = ("#fef9c3", "#854d0e") if alert == "DECOUPLING" else ("#f1f5f9", "#64748b")
        alert_label = "⚠ Decoupling" if alert == "DECOUPLING" else "Stable"

        rows += (
            f'<tr>'
            f'<td style="padding:5px 10px;font-weight:600;font-size:12px">{asset}</td>'
            f'<td style="text-align:right;padding:5px 8px;font-size:12px;font-weight:600;color:#334155">{price_s}</td>'
            f'<td style="text-align:center;padding:5px 8px;background:{bg30};color:{fg30};'
            f'font-size:12px;font-weight:600;border-radius:3px">{c30_s}</td>'
            f'<td style="text-align:center;padding:5px 8px;background:{bg60};color:{fg60};'
            f'font-size:12px;font-weight:600;border-radius:3px">{c60_s}</td>'
            f'<td style="text-align:center;padding:5px 8px;font-size:12px;font-weight:600">{chg_s}</td>'
            f'<td style="text-align:center;padding:5px 8px">'
            f'<span style="background:{alert_bg};color:{alert_fg};padding:2px 8px;border-radius:10px;'
            f'font-size:10px;font-weight:700">{alert_label}</span></td>'
            f'</tr>'
        )

    return (
        f'<div style="overflow-x:auto;margin:0 0 16px">'
        f'<div style="font-size:12px;font-weight:600;color:var(--primary,#1e40af);margin-bottom:6px">'
        f'Global Correlation Monitor (30d/60d rolling vs Nifty 500)</div>'
        f'<table style="border-collapse:separate;border-spacing:2px;width:100%">'
        f'<thead>{header}</thead>'
        f'<tbody>{rows}</tbody>'
        f'</table>'
        f'<div style="font-size:10px;color:#94a3b8;margin-top:6px">'
        f'Decoupling alert fires when |30d − 60d correlation| &gt; {DECOUPLE_THRESHOLD:.0%}. '
        f'Positive correlation = moves together; negative = moves inversely.'
        f'</div></div>'
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def generate_global_correlations(
    force: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Main pipeline: fetch global data, compute correlations, persist, return.

    Returns (global_prices_df, correlations_df).
    """
    global_df = fetch_global_indices(force=force)
    if global_df.empty:
        return global_df, pd.DataFrame()

    nifty = _load_nifty500_close()
    if nifty.empty:
        return global_df, pd.DataFrame()

    corr = compute_correlations(nifty, global_df)

    # PG: persist correlations
    if not corr.empty:
        CORR_CSV.parent.mkdir(parents=True, exist_ok=True)
        corr.to_csv(CORR_CSV, index=False)

    return global_df, corr


def load_global_correlations(path: Path = CORR_CSV) -> pd.DataFrame:
    """Load cached correlations from CSV."""
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="B2: Global Correlation Monitor")
    ap.add_argument("--force", action="store_true", help="Force re-fetch of global data")
    args = ap.parse_args()

    print("Fetching global indices...")
    prices, corr = generate_global_correlations(force=args.force)

    if prices.empty:
        print("No global data fetched.")
    else:
        print(f"Global prices: {len(prices)} days × {len(prices.columns)} assets")
        print(f"Date range: {prices.index[0].date()} to {prices.index[-1].date()}")

    if corr.empty:
        print("No correlations computed.")
    else:
        print(f"\nCorrelations (vs Nifty 500):")
        for _, row in corr.iterrows():
            alert = "⚠ DECOUPLING" if row["alert"] == "DECOUPLING" else "  Stable"
            price = row.get("price", math.nan)
            price_s = f"{price:>10,.2f}" if not math.isnan(price) else "       n/a"
            print(
                f"  {row['asset']:15s} {price_s}  30d={row['corr_30d']:+.3f}  "
                f"60d={row['corr_60d']:+.3f}  Δ={row['change']:+.3f}  {alert}"
            )

    # Generate HTML strip preview
    strip = correlation_context_html(corr)
    if strip:
        print(f"\nContext strip: {strip[:200]}...")
