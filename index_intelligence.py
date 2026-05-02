#!/usr/bin/env python3
"""Cross-index breadth dashboard built from local NSE data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import html
import math
import shutil

import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
STOCK_DATA_CSV = DATA_DIR / "nse_sec_full_data.csv"
INDEX_MAPPING_CSV = DATA_DIR / "index_stock_mapping.csv"
INDEX_CATALOG_CSV = DATA_DIR / "nse_indices_catalog.csv"

TARGET_INDICES = [
    "NIFTY 50",
    "NIFTY NEXT 50",
    "NIFTY 500",
    "NIFTY MIDCAP 150",
    "NIFTY SMALLCAP 250",
    "NIFTY BANK",
    "NIFTY IT",
    "NIFTY PHARMA",
    "NIFTY AUTO",
    "NIFTY FMCG",
    "NIFTY METAL",
]

INDEX_ALIASES = {
    "NIFTY SMALLCAP 250": ["NIFTY SMALLCAP 250", "NIFTY SMLCAP 250"],
}

SMALLCAP_EXCLUSION_INDICES = [
    "NIFTY 50",
    "NIFTY NEXT 50",
    "NIFTY 100",
    "NIFTY MIDCAP 50",
    "NIFTY MIDCAP 100",
    "NIFTY MIDCAP 150",
    "NIFTY 200",
    "NIFTY LARGEMIDCAP 250",
]


@dataclass(frozen=True)
class IndexReportPaths:
    html: Path
    csv: Path
    latest_html: Path
    latest_csv: Path
    latest_coverage_csv: Path
    latest_top5_csv: Path


def report_output_paths(generated_at: datetime | pd.Timestamp, root: Path = ROOT) -> IndexReportPaths:
    ts = pd.Timestamp(generated_at).to_pydatetime()
    suffix = ts.strftime("%Y%m%d")
    year = ts.strftime("%Y")
    reports = root / "reports"
    out_dir = reports / "index_intelligence" / year
    return IndexReportPaths(
        html=out_dir / f"Index_Intelligence_{suffix}.html",
        csv=out_dir / f"Index_Intelligence_{suffix}.csv",
        latest_html=reports / "latest" / "index_intelligence.html",
        latest_csv=reports / "latest" / "index_intelligence.csv",
        latest_coverage_csv=reports / "latest" / "index_coverage.csv",
        latest_top5_csv=reports / "latest" / "index_top5_stocks.csv",
    )


def _pct_true(mask: pd.Series) -> float:
    valid = mask.dropna()
    if valid.empty:
        return math.nan
    return float(valid.mean() * 100.0)


def classify_breadth_signal(pct_above_200: float, pct_near_52wl: float, ad_ratio: float) -> str:
    if pd.notna(pct_near_52wl) and pct_near_52wl > 15:
        return "BEARISH"
    if pd.isna(pct_above_200):
        return "NO_DATA"
    if pct_above_200 < 30:
        return "BEARISH"
    if pct_above_200 > 70 and pd.notna(ad_ratio) and ad_ratio > 1.8:
        return "STRONG"
    if 60 <= pct_above_200 <= 70:
        return "HEALTHY"
    if 45 <= pct_above_200 < 60:
        return "NEUTRAL"
    if 30 <= pct_above_200 < 45:
        return "WEAK"
    return "NEUTRAL"


def cross_index_breadth(index_constituent_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Compute breadth metrics for each index constituent DataFrame."""
    rows: list[dict] = []
    for index_name, raw_df in index_constituent_data.items():
        df = raw_df.copy()
        if df.empty:
            rows.append({
                "INDEX_NAME": index_name,
                "constituents": 0,
                "pct_above_200dma": math.nan,
                "pct_above_50dma": math.nan,
                "pct_near_52wh": math.nan,
                "pct_near_52wl": math.nan,
                "ad_ratio": math.nan,
                "advances": 0,
                "declines": 0,
                "breadth_signal": "NO_DATA",
            })
            continue

        for col in ["CLOSE", "SMA_50", "SMA_200", "HIGH_52W", "LOW_52W", "RET_1D"]:
            if col not in df.columns:
                df[col] = math.nan
            df[col] = pd.to_numeric(df[col], errors="coerce")

        advances = int((df["RET_1D"] > 0).sum())
        declines = int((df["RET_1D"] < 0).sum())
        pct_above_200 = _pct_true(df["CLOSE"] > df["SMA_200"])
        pct_above_50 = _pct_true(df["CLOSE"] > df["SMA_50"])
        pct_near_52wh = _pct_true((df["HIGH_52W"] > 0) & ((df["CLOSE"] / df["HIGH_52W"]) > 0.95))
        pct_near_52wl = _pct_true((df["LOW_52W"] > 0) & ((df["CLOSE"] / df["LOW_52W"]) < 1.05))
        ad_ratio = advances / max(declines, 1)

        rows.append({
            "INDEX_NAME": index_name,
            "constituents": int(len(df)),
            "pct_above_200dma": round(pct_above_200, 2) if pd.notna(pct_above_200) else math.nan,
            "pct_above_50dma": round(pct_above_50, 2) if pd.notna(pct_above_50) else math.nan,
            "pct_near_52wh": round(pct_near_52wh, 2) if pd.notna(pct_near_52wh) else math.nan,
            "pct_near_52wl": round(pct_near_52wl, 2) if pd.notna(pct_near_52wl) else math.nan,
            "ad_ratio": round(ad_ratio, 2),
            "advances": advances,
            "declines": declines,
            "breadth_signal": classify_breadth_signal(pct_above_200, pct_near_52wl, ad_ratio),
        })

    result = pd.DataFrame(rows)
    if result.empty:
        return result
    signal_rank = {"STRONG": 5, "HEALTHY": 4, "NEUTRAL": 3, "WEAK": 2, "BEARISH": 1, "NO_DATA": 0}
    result["_signal_rank"] = result["breadth_signal"].map(signal_rank).fillna(0)
    return result.sort_values(["_signal_rank", "pct_above_200dma"], ascending=[False, False]).drop(columns="_signal_rank").reset_index(drop=True)


def build_stock_metric_frame(stock_history: pd.DataFrame, min_days: int = 50) -> pd.DataFrame:
    """Build latest per-symbol breadth inputs from stock OHLC history."""
    if stock_history.empty:
        return pd.DataFrame(columns=["SYMBOL", "CLOSE", "SMA_50", "SMA_200", "HIGH_52W", "LOW_52W", "RET_1D", "TOTTRDQTY", "DATA_DATE"])

    df = stock_history.copy()
    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"])
    for col in ["CLOSE", "HIGH", "LOW"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "TOTTRDQTY" in df.columns:
        df["TOTTRDQTY"] = pd.to_numeric(df["TOTTRDQTY"], errors="coerce")
    df = df.dropna(subset=["SYMBOL", "TIMESTAMP", "CLOSE"]).sort_values(["SYMBOL", "TIMESTAMP"])

    rows: list[dict] = []
    for symbol, hist in df.groupby("SYMBOL", sort=False):
        hist = hist.sort_values("TIMESTAMP")
        if len(hist) < min_days:
            continue
        close = hist["CLOSE"].astype(float)
        high = hist["HIGH"].astype(float) if "HIGH" in hist.columns else close
        low = hist["LOW"].astype(float) if "LOW" in hist.columns else close
        latest_close = float(close.iloc[-1])
        prev_close = float(close.iloc[-2]) if len(close) > 1 else math.nan
        ret_1d = (latest_close / prev_close - 1.0) * 100.0 if prev_close and not math.isnan(prev_close) else math.nan
        latest_volume = float(hist["TOTTRDQTY"].iloc[-1]) if "TOTTRDQTY" in hist.columns and pd.notna(hist["TOTTRDQTY"].iloc[-1]) else math.nan
        rows.append({
            "SYMBOL": str(symbol).strip().upper(),
            "CLOSE": latest_close,
            "SMA_50": float(close.rolling(50, min_periods=50).mean().iloc[-1]) if len(close) >= 50 else math.nan,
            "SMA_200": float(close.rolling(200, min_periods=200).mean().iloc[-1]) if len(close) >= 200 else math.nan,
            "HIGH_52W": float(high.tail(252).max()),
            "LOW_52W": float(low.tail(252).min()),
            "RET_1D": ret_1d,
            "TOTTRDQTY": latest_volume,
            "DATA_DATE": hist["TIMESTAMP"].iloc[-1].date().isoformat(),
        })
    return pd.DataFrame(rows)


def load_index_constituents(mapping_csv: Path = INDEX_MAPPING_CSV) -> dict[str, list[str]]:
    mapping = pd.read_csv(mapping_csv)
    mapping["INDEX_NAME"] = mapping["INDEX_NAME"].astype(str).str.strip().str.upper()
    mapping["STOCK_SYMBOL"] = mapping["STOCK_SYMBOL"].astype(str).str.strip().str.upper()

    constituents: dict[str, list[str]] = {}
    for index_name, group in mapping.groupby("INDEX_NAME"):
        symbols = sorted(set(s for s in group["STOCK_SYMBOL"].tolist() if s and s != "NAN"))
        if symbols:
            constituents[index_name] = symbols
    return constituents


def load_index_catalog(catalog_csv: Path = INDEX_CATALOG_CSV) -> pd.DataFrame:
    catalog = pd.read_csv(catalog_csv)
    rename_map = {
        "index_display_name": "INDEX_NAME",
        "category_label": "CATEGORY",
        "api_index_symbol": "API_SYMBOL",
    }
    catalog = catalog.rename(columns={k: v for k, v in rename_map.items() if k in catalog.columns})
    for col in ["INDEX_NAME", "CATEGORY", "API_SYMBOL"]:
        if col not in catalog.columns:
            catalog[col] = ""
        catalog[col] = catalog[col].astype(str).str.strip()
    catalog["INDEX_NAME"] = catalog["INDEX_NAME"].str.upper()
    catalog["API_SYMBOL"] = catalog["API_SYMBOL"].str.upper()
    return catalog.drop_duplicates("INDEX_NAME", keep="first").reset_index(drop=True)


def _normalise_constituents(constituents: dict[str, list[str]]) -> dict[str, list[str]]:
    return {
        str(index_name).strip().upper(): [
            str(symbol).strip().upper()
            for symbol in symbols
            if str(symbol).strip() and str(symbol).strip().upper() != "NAN"
        ]
        for index_name, symbols in constituents.items()
    }


def _symbols_for_index(constituents: dict[str, list[str]], index_name: str) -> list[str]:
    for alias in INDEX_ALIASES.get(index_name.upper(), [index_name.upper()]):
        symbols = constituents.get(alias.upper(), [])
        if symbols:
            return symbols
    return []


def infer_smallcap_250_constituents(
    stock_metrics: pd.DataFrame,
    constituents: dict[str, list[str]],
    count: int = 250,
) -> list[str]:
    """Infer a smallcap breadth basket when the local NSE mapping lacks constituents."""
    if stock_metrics.empty or "SYMBOL" not in stock_metrics.columns:
        return []

    metrics = stock_metrics.copy()
    metrics["SYMBOL"] = metrics["SYMBOL"].astype(str).str.strip().str.upper()
    metrics = metrics.drop_duplicates("SYMBOL", keep="last")
    normalised_constituents = _normalise_constituents(constituents)

    nifty_500 = set(normalised_constituents.get("NIFTY 500", []))
    universe = nifty_500 if nifty_500 else set(metrics["SYMBOL"])
    excluded: set[str] = set()
    for index_name in SMALLCAP_EXCLUSION_INDICES:
        excluded.update(normalised_constituents.get(index_name, []))

    candidates = metrics[metrics["SYMBOL"].isin(universe - excluded)].copy()
    if candidates.empty:
        candidates = metrics[~metrics["SYMBOL"].isin(excluded)].copy()
    if candidates.empty:
        return []

    if "TOTTRDQTY" in candidates.columns:
        candidates["TOTTRDQTY"] = pd.to_numeric(candidates["TOTTRDQTY"], errors="coerce").fillna(0)
        candidates = candidates.sort_values(["TOTTRDQTY", "SYMBOL"], ascending=[False, True])
    else:
        candidates = candidates.sort_values("SYMBOL")

    return candidates["SYMBOL"].head(count).tolist()


def build_index_coverage(
    index_catalog: pd.DataFrame,
    constituents: dict[str, list[str]],
    index_data: dict[str, pd.DataFrame] | None = None,
    target_indices: list[str] | None = None,
) -> pd.DataFrame:
    catalog = index_catalog.copy()
    if catalog.empty:
        return pd.DataFrame(columns=["INDEX_NAME", "CATEGORY", "API_SYMBOL", "constituent_count", "mapping_status", "included_in_dashboard"])
    for col in ["INDEX_NAME", "CATEGORY", "API_SYMBOL"]:
        if col not in catalog.columns:
            catalog[col] = ""
        catalog[col] = catalog[col].astype(str).str.strip()
    catalog["INDEX_NAME"] = catalog["INDEX_NAME"].str.upper()
    normalised_constituents = _normalise_constituents(constituents)
    index_data = index_data or {}
    selected = {str(i).strip().upper() for i in (target_indices or TARGET_INDICES)}

    rows: list[dict] = []
    for _, row in catalog.iterrows():
        index_name = str(row.get("INDEX_NAME", "")).strip().upper()
        mapped_symbols = _symbols_for_index(normalised_constituents, index_name)
        data_count = int(len(index_data.get(index_name, pd.DataFrame())))
        if mapped_symbols:
            status = "Available"
            count = len(set(mapped_symbols))
        elif data_count > 0:
            status = "Inferred"
            count = data_count
        else:
            status = "Missing"
            count = 0
        rows.append({
            "INDEX_NAME": index_name,
            "CATEGORY": str(row.get("CATEGORY", "")).strip(),
            "API_SYMBOL": str(row.get("API_SYMBOL", "")).strip().upper(),
            "constituent_count": int(count),
            "mapping_status": status,
            "included_in_dashboard": index_name in selected,
        })
    return pd.DataFrame(rows).sort_values(["CATEGORY", "INDEX_NAME"]).reset_index(drop=True)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    if pd.isna(value):
        return low
    return max(low, min(high, float(value)))


def _score_index_stock(row: pd.Series, liquidity_rank: float) -> float:
    close = float(row.get("CLOSE", math.nan))
    sma_50 = float(row.get("SMA_50", math.nan))
    sma_200 = float(row.get("SMA_200", math.nan))
    high_52w = float(row.get("HIGH_52W", math.nan))
    low_52w = float(row.get("LOW_52W", math.nan))
    ret_1d = float(row.get("RET_1D", math.nan))

    dma_score = (35.0 if pd.notna(sma_200) and close > sma_200 else 0.0) + (20.0 if pd.notna(sma_50) and close > sma_50 else 0.0)
    high_score = _clamp((close / high_52w) * 100.0 if high_52w > 0 else 0.0) * 0.20
    recovery_score = _clamp((close / low_52w - 1.0) * 100.0 if low_52w > 0 else 0.0) * 0.10
    short_term_score = _clamp((ret_1d + 5.0) * 10.0 if pd.notna(ret_1d) else 0.0, 0.0, 100.0) * 0.05
    liquidity_score = _clamp(liquidity_rank * 100.0) * 0.10
    return round(dma_score + high_score + recovery_score + short_term_score + liquidity_score, 2)


def build_top5_index_stocks(
    index_catalog: pd.DataFrame,
    index_constituent_data: dict[str, pd.DataFrame],
    top_n: int = 5,
) -> pd.DataFrame:
    if index_catalog.empty or not index_constituent_data:
        return pd.DataFrame(columns=[
            "INDEX_NAME", "CATEGORY", "rank", "SYMBOL", "CLOSE", "investment_score",
            "above_50dma", "above_200dma", "dist_from_52w_high_pct",
            "recovery_from_52w_low_pct", "RET_1D", "TOTTRDQTY",
        ])

    catalog = index_catalog.copy()
    catalog["INDEX_NAME"] = catalog["INDEX_NAME"].astype(str).str.strip().str.upper()
    catalog["CATEGORY"] = catalog["CATEGORY"].astype(str).str.strip()
    category_by_index = catalog.set_index("INDEX_NAME")["CATEGORY"].to_dict()

    rows: list[dict] = []
    for index_name, raw_df in index_constituent_data.items():
        key = str(index_name).strip().upper()
        category = str(category_by_index.get(key, "")).strip()
        if category.lower() not in {"sectoral", "thematic"} or raw_df.empty:
            continue
        df = raw_df.copy()
        for col in ["CLOSE", "SMA_50", "SMA_200", "HIGH_52W", "LOW_52W", "RET_1D", "TOTTRDQTY"]:
            if col not in df.columns:
                df[col] = math.nan
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip().str.upper()
        if df.empty:
            continue
        volume_rank = df["TOTTRDQTY"].rank(pct=True, method="average").fillna(0)
        df["investment_score"] = [
            _score_index_stock(row, float(volume_rank.loc[idx]))
            for idx, row in df.iterrows()
        ]
        df["above_50dma"] = df["CLOSE"] > df["SMA_50"]
        df["above_200dma"] = df["CLOSE"] > df["SMA_200"]
        df["dist_from_52w_high_pct"] = ((df["CLOSE"] / df["HIGH_52W"] - 1.0) * 100.0).round(2)
        df["recovery_from_52w_low_pct"] = ((df["CLOSE"] / df["LOW_52W"] - 1.0) * 100.0).round(2)
        top = df.sort_values(["investment_score", "TOTTRDQTY", "SYMBOL"], ascending=[False, False, True]).head(top_n)
        for rank, (_, row) in enumerate(top.iterrows(), start=1):
            rows.append({
                "INDEX_NAME": key,
                "CATEGORY": category,
                "rank": rank,
                "SYMBOL": row["SYMBOL"],
                "CLOSE": round(float(row["CLOSE"]), 2) if pd.notna(row["CLOSE"]) else math.nan,
                "investment_score": round(float(row["investment_score"]), 2),
                "above_50dma": bool(row["above_50dma"]),
                "above_200dma": bool(row["above_200dma"]),
                "dist_from_52w_high_pct": row["dist_from_52w_high_pct"],
                "recovery_from_52w_low_pct": row["recovery_from_52w_low_pct"],
                "RET_1D": round(float(row["RET_1D"]), 2) if pd.notna(row["RET_1D"]) else math.nan,
                "TOTTRDQTY": round(float(row["TOTTRDQTY"]), 0) if pd.notna(row["TOTTRDQTY"]) else math.nan,
            })
    return pd.DataFrame(rows).reset_index(drop=True)


def build_index_constituent_data(
    stock_metrics: pd.DataFrame,
    constituents: dict[str, list[str]],
    target_indices: list[str] | None = None,
) -> dict[str, pd.DataFrame]:
    metrics = stock_metrics.copy()
    metrics["SYMBOL"] = metrics["SYMBOL"].astype(str).str.strip().str.upper()
    metrics = metrics.drop_duplicates("SYMBOL", keep="last").set_index("SYMBOL")
    selected = target_indices or TARGET_INDICES
    normalised_constituents = _normalise_constituents(constituents)

    result: dict[str, pd.DataFrame] = {}
    for index_name in selected:
        key = index_name.upper()
        symbols = _symbols_for_index(normalised_constituents, key)
        if not symbols and key == "NIFTY SMALLCAP 250":
            symbols = infer_smallcap_250_constituents(stock_metrics, normalised_constituents)
        if not symbols:
            result[key] = pd.DataFrame(columns=metrics.reset_index().columns)
            continue
        available = [sym for sym in symbols if sym in metrics.index]
        if not available:
            result[key] = pd.DataFrame(columns=metrics.reset_index().columns)
            continue
        result[key] = metrics.loc[available].reset_index()
    return result


def _fmt_pct(value: object) -> str:
    if pd.isna(value):
        return "NA"
    return f"{float(value):.1f}%"


def _fmt_num(value: object, digits: int = 2) -> str:
    if pd.isna(value):
        return "NA"
    return f"{float(value):.{digits}f}"


def _signal_badge(signal: str) -> str:
    sig = html.escape(str(signal or "NO_DATA"))
    cls = {
        "STRONG": "sig-strong",
        "HEALTHY": "sig-healthy",
        "NEUTRAL": "sig-neutral",
        "WEAK": "sig-weak",
        "BEARISH": "sig-bearish",
    }.get(sig, "sig-nodata")
    return f'<span class="signal {cls}">{sig}</span>'


def breadth_context_html(breadth: pd.DataFrame) -> str:
    """Compact breadth strip for embedding in the sector rotation report."""
    if breadth.empty:
        return ""

    by_index = {
        str(row.get("INDEX_NAME", "")).upper(): row
        for _, row in breadth.iterrows()
    }
    nifty = by_index.get("NIFTY 50")
    smallcap = by_index.get("NIFTY SMALLCAP 250")
    if smallcap is None:
        smallcap = by_index.get("NIFTY MICROCAP 250")
    nifty_signal = str(nifty.get("breadth_signal", "NO_DATA")) if nifty is not None else "NO_DATA"
    small_signal = str(smallcap.get("breadth_signal", "NO_DATA")) if smallcap is not None else "NO_DATA"

    context = "Broad participation"
    if nifty_signal in ("STRONG", "HEALTHY") and small_signal in ("WEAK", "BEARISH"):
        context = "Selective rotation"
    elif nifty_signal in ("WEAK", "BEARISH") and small_signal in ("WEAK", "BEARISH", "NO_DATA"):
        context = "Weak breadth"
    elif nifty_signal in ("STRONG", "HEALTHY") and small_signal in ("STRONG", "HEALTHY"):
        context = "Broad participation"

    def _metric(row: pd.Series | None, name: str) -> str:
        if row is None:
            return f"{name}: NO_DATA"
        signal = str(row.get("breadth_signal", "NO_DATA"))
        pct = row.get("pct_above_200dma", math.nan)
        pct_text = "NA" if pd.isna(pct) else f"{float(pct):.0f}% >200DMA"
        return f"{name}: {signal} ({pct_text})"

    return (
        '<div class="breadth-strip">'
        '<span class="breadth-kicker">Breadth</span>'
        f'<span class="breadth-context">{html.escape(context)}</span>'
        f'<span>{html.escape(_metric(nifty, "NIFTY 50"))}</span>'
        f'<span>{html.escape(_metric(smallcap, "Smallcap"))}</span>'
        '</div>'
    )


def _render_coverage_rows(coverage: pd.DataFrame | None) -> str:
    if coverage is None or coverage.empty:
        return '<tr><td colspan="6">No index coverage data available.</td></tr>'
    rows = ""
    for _, row in coverage.iterrows():
        status = str(row.get("mapping_status", "Missing"))
        status_cls = {
            "Available": "sig-strong",
            "Inferred": "sig-healthy",
            "Missing": "sig-nodata",
        }.get(status, "sig-nodata")
        included = "Yes" if bool(row.get("included_in_dashboard", False)) else "No"
        rows += (
            "<tr>"
            f"<td><strong>{html.escape(str(row.get('INDEX_NAME', '')))}</strong></td>"
            f"<td>{html.escape(str(row.get('CATEGORY', '')))}</td>"
            f"<td>{html.escape(str(row.get('API_SYMBOL', '')))}</td>"
            f"<td class=\"num\">{int(row.get('constituent_count', 0) or 0)}</td>"
            f"<td><span class=\"signal {status_cls}\">{html.escape(status)}</span></td>"
            f"<td>{included}</td>"
            "</tr>"
        )
    return rows


def _render_top5_rows(top5: pd.DataFrame | None) -> str:
    if top5 is None or top5.empty:
        return '<tr><td colspan="10">No sectoral or thematic top-five data available.</td></tr>'
    rows = ""
    for _, row in top5.iterrows():
        rows += (
            "<tr>"
            f"<td><strong>{html.escape(str(row.get('INDEX_NAME', '')))}</strong></td>"
            f"<td>{html.escape(str(row.get('CATEGORY', '')))}</td>"
            f"<td class=\"num\">{int(row.get('rank', 0) or 0)}</td>"
            f"<td><strong>{html.escape(str(row.get('SYMBOL', '')))}</strong></td>"
            f"<td class=\"num\">{_fmt_num(row.get('CLOSE'), 2)}</td>"
            f"<td class=\"num\">{_fmt_num(row.get('investment_score'), 1)}</td>"
            f"<td>{'Yes' if bool(row.get('above_200dma', False)) else 'No'}</td>"
            f"<td class=\"num\">{_fmt_pct(row.get('dist_from_52w_high_pct'))}</td>"
            f"<td class=\"num\">{_fmt_pct(row.get('recovery_from_52w_low_pct'))}</td>"
            f"<td class=\"num\">{_fmt_num(row.get('TOTTRDQTY'), 0)}</td>"
            "</tr>"
        )
    return rows


def render_breadth_html(
    breadth: pd.DataFrame,
    generated_at: datetime | pd.Timestamp,
    coverage: pd.DataFrame | None = None,
    top5_stocks: pd.DataFrame | None = None,
) -> str:
    gen_date = pd.Timestamp(generated_at).strftime("%Y-%m-%d")
    if breadth.empty:
        rows = '<tr><td colspan="8">No breadth data available.</td></tr>'
        summary = "No breadth data available"
    else:
        counts = breadth["breadth_signal"].value_counts().to_dict()
        summary = " · ".join(f"{k}: {v}" for k, v in counts.items())
        rows = ""
        for _, row in breadth.iterrows():
            rows += (
                "<tr>"
                f"<td><strong>{html.escape(str(row.get('INDEX_NAME', '')))}</strong></td>"
                f"<td class=\"num\">{int(row.get('constituents', 0) or 0)}</td>"
                f"<td>{_signal_badge(str(row.get('breadth_signal', 'NO_DATA')))}</td>"
                f"<td class=\"num\">{_fmt_pct(row.get('pct_above_200dma'))}</td>"
                f"<td class=\"num\">{_fmt_pct(row.get('pct_above_50dma'))}</td>"
                f"<td class=\"num\">{_fmt_pct(row.get('pct_near_52wh'))}</td>"
                f"<td class=\"num\">{_fmt_pct(row.get('pct_near_52wl'))}</td>"
                f"<td class=\"num\">{_fmt_num(row.get('ad_ratio'), 2)}</td>"
                "</tr>"
            )

    coverage_rows = _render_coverage_rows(coverage)
    top5_rows = _render_top5_rows(top5_stocks)
    coverage_summary = ""
    if coverage is not None and not coverage.empty:
        status_counts = coverage["mapping_status"].value_counts().to_dict()
        coverage_summary = " · ".join(f"{k}: {v}" for k, v in status_counts.items())
    top5_summary = ""
    if top5_stocks is not None and not top5_stocks.empty:
        top5_summary = f"{top5_stocks['INDEX_NAME'].nunique()} sectoral/thematic indices · {len(top5_stocks)} stock rows"

    css = """
    :root{--bg:#f4f7fb;--card:#fff;--text:#172033;--muted:#64748b;--line:#e2e8f0;--primary:#183a5a}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    header{background:var(--primary);color:white;padding:18px 24px}h1{font-size:20px;margin:0 0 4px}.sub{font-size:12px;opacity:.82}
    main{max-width:1180px;margin:0 auto;padding:20px}.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:16px;margin-bottom:16px}
    .summary{font-size:13px;color:var(--muted)}.tbl-wrap{overflow-x:auto;background:white;border:1px solid var(--line);border-radius:8px}
    .section-title{font-size:15px;font-weight:800;color:var(--primary);margin:22px 0 6px}.section-sub{font-size:12px;color:var(--muted);margin:0 0 10px}
    table{width:100%;min-width:860px;border-collapse:collapse;font-size:13px}th{background:#183a5a;color:#fff;text-align:left;padding:10px;font-size:11px;text-transform:uppercase;letter-spacing:.04em}
    td{padding:10px;border-bottom:1px solid var(--line)}tr:last-child td{border-bottom:0}.num{text-align:right;font-variant-numeric:tabular-nums}
    .signal{display:inline-block;border-radius:999px;padding:3px 9px;font-size:10px;font-weight:800}
    .sig-strong{background:#dcfce7;color:#166534}.sig-healthy{background:#dbeafe;color:#1d4ed8}.sig-neutral{background:#f1f5f9;color:#475569}
    .sig-weak{background:#fef3c7;color:#92400e}.sig-bearish{background:#fee2e2;color:#991b1b}.sig-nodata{background:#f8fafc;color:#94a3b8}
    """
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>Cross-Index Breadth Dashboard - {gen_date}</title><style>{css}</style></head><body>"
        f"<header><h1>Cross-Index Breadth Dashboard</h1><div class=\"sub\">Generated {gen_date}</div></header>"
        f"<main><section class=\"card\"><div class=\"summary\">{html.escape(summary)}</div></section>"
        "<section class=\"tbl-wrap\"><table><thead><tr>"
        "<th>Index</th><th class=\"num\">Stocks</th><th>Signal</th><th class=\"num\">Above 200DMA</th>"
        "<th class=\"num\">Above 50DMA</th><th class=\"num\">Near 52W High</th>"
        "<th class=\"num\">Near 52W Low</th><th class=\"num\">A/D Ratio</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></section>"
        "<section>"
        "<div class=\"section-title\">Index Coverage</div>"
        f"<div class=\"section-sub\">{html.escape(coverage_summary or 'Coverage by cached NSE index catalog')}</div>"
        "<div class=\"tbl-wrap\"><table><thead><tr>"
        "<th>Index</th><th>Category</th><th>API Symbol</th><th class=\"num\">Stocks</th><th>Status</th><th>Dashboard</th>"
        f"</tr></thead><tbody>{coverage_rows}</tbody></table></div>"
        "</section>"
        "<section>"
        "<div class=\"section-title\">Top 5 Investment Stocks By Sector/Thematic Index</div>"
        f"<div class=\"section-sub\">{html.escape(top5_summary or 'Ranked using local technical, 52-week, recovery, and liquidity metrics')}</div>"
        "<div class=\"tbl-wrap\"><table><thead><tr>"
        "<th>Index</th><th>Category</th><th class=\"num\">Rank</th><th>Symbol</th><th class=\"num\">Close</th>"
        "<th class=\"num\">Score</th><th>Above 200DMA</th><th class=\"num\">From 52W High</th>"
        "<th class=\"num\">Recovery From 52W Low</th><th class=\"num\">Volume</th>"
        f"</tr></thead><tbody>{top5_rows}</tbody></table></div>"
        "</section></main></body></html>"
    )


def generate_index_intelligence_report(root: Path = ROOT) -> IndexReportPaths:
    generated_at = datetime.now()
    paths = report_output_paths(generated_at, root=root)

    stock_history = pd.read_csv(root / STOCK_DATA_CSV.relative_to(ROOT))
    metrics = build_stock_metric_frame(stock_history, min_days=50)
    constituents = load_index_constituents(root / INDEX_MAPPING_CSV.relative_to(ROOT))
    catalog = load_index_catalog(root / INDEX_CATALOG_CSV.relative_to(ROOT))
    index_data = build_index_constituent_data(metrics, constituents)
    investment_indices = catalog[catalog["CATEGORY"].str.lower().isin(["sectoral", "thematic"])]["INDEX_NAME"].tolist()
    investment_index_data = build_index_constituent_data(metrics, constituents, target_indices=investment_indices)
    combined_index_data = {**investment_index_data, **index_data}
    breadth = cross_index_breadth(index_data)
    coverage = build_index_coverage(catalog, constituents, combined_index_data)
    top5_stocks = build_top5_index_stocks(catalog, investment_index_data, top_n=5)

    paths.html.parent.mkdir(parents=True, exist_ok=True)
    paths.latest_html.parent.mkdir(parents=True, exist_ok=True)
    breadth.to_csv(paths.csv, index=False)
    coverage.to_csv(paths.latest_coverage_csv, index=False)
    top5_stocks.to_csv(paths.latest_top5_csv, index=False)
    paths.html.write_text(render_breadth_html(breadth, generated_at, coverage, top5_stocks), encoding="utf-8")
    shutil.copy2(paths.csv, paths.latest_csv)
    shutil.copy2(paths.html, paths.latest_html)
    return paths


def main() -> None:
    paths = generate_index_intelligence_report()
    print(f"Wrote {paths.csv}")
    print(f"Wrote {paths.html}")
    print(f"Wrote {paths.latest_csv}")
    print(f"Wrote {paths.latest_html}")
    print(f"Wrote {paths.latest_coverage_csv}")
    print(f"Wrote {paths.latest_top5_csv}")


if __name__ == "__main__":
    main()
