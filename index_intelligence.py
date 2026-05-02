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


@dataclass(frozen=True)
class IndexReportPaths:
    html: Path
    csv: Path
    latest_html: Path
    latest_csv: Path


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
        return pd.DataFrame(columns=["SYMBOL", "CLOSE", "SMA_50", "SMA_200", "HIGH_52W", "LOW_52W", "RET_1D", "DATA_DATE"])

    df = stock_history.copy()
    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"])
    for col in ["CLOSE", "HIGH", "LOW"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
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
        rows.append({
            "SYMBOL": str(symbol).strip().upper(),
            "CLOSE": latest_close,
            "SMA_50": float(close.rolling(50, min_periods=50).mean().iloc[-1]) if len(close) >= 50 else math.nan,
            "SMA_200": float(close.rolling(200, min_periods=200).mean().iloc[-1]) if len(close) >= 200 else math.nan,
            "HIGH_52W": float(high.tail(252).max()),
            "LOW_52W": float(low.tail(252).min()),
            "RET_1D": ret_1d,
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


def build_index_constituent_data(
    stock_metrics: pd.DataFrame,
    constituents: dict[str, list[str]],
    target_indices: list[str] | None = None,
) -> dict[str, pd.DataFrame]:
    metrics = stock_metrics.copy()
    metrics["SYMBOL"] = metrics["SYMBOL"].astype(str).str.strip().str.upper()
    metrics = metrics.drop_duplicates("SYMBOL", keep="last").set_index("SYMBOL")
    selected = target_indices or TARGET_INDICES

    result: dict[str, pd.DataFrame] = {}
    for index_name in selected:
        key = index_name.upper()
        symbols = constituents.get(key, [])
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


def render_breadth_html(breadth: pd.DataFrame, generated_at: datetime | pd.Timestamp) -> str:
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

    css = """
    :root{--bg:#f4f7fb;--card:#fff;--text:#172033;--muted:#64748b;--line:#e2e8f0;--primary:#183a5a}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    header{background:var(--primary);color:white;padding:18px 24px}h1{font-size:20px;margin:0 0 4px}.sub{font-size:12px;opacity:.82}
    main{max-width:1180px;margin:0 auto;padding:20px}.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:16px;margin-bottom:16px}
    .summary{font-size:13px;color:var(--muted)}.tbl-wrap{overflow-x:auto;background:white;border:1px solid var(--line);border-radius:8px}
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
        f"</tr></thead><tbody>{rows}</tbody></table></section></main></body></html>"
    )


def generate_index_intelligence_report(root: Path = ROOT) -> IndexReportPaths:
    generated_at = datetime.now()
    paths = report_output_paths(generated_at, root=root)

    stock_history = pd.read_csv(root / STOCK_DATA_CSV.relative_to(ROOT))
    metrics = build_stock_metric_frame(stock_history, min_days=50)
    constituents = load_index_constituents(root / INDEX_MAPPING_CSV.relative_to(ROOT))
    index_data = build_index_constituent_data(metrics, constituents)
    breadth = cross_index_breadth(index_data)

    paths.html.parent.mkdir(parents=True, exist_ok=True)
    paths.latest_html.parent.mkdir(parents=True, exist_ok=True)
    breadth.to_csv(paths.csv, index=False)
    paths.html.write_text(render_breadth_html(breadth, generated_at), encoding="utf-8")
    shutil.copy2(paths.csv, paths.latest_csv)
    shutil.copy2(paths.html, paths.latest_html)
    return paths


def main() -> None:
    paths = generate_index_intelligence_report()
    print(f"Wrote {paths.csv}")
    print(f"Wrote {paths.html}")
    print(f"Wrote {paths.latest_csv}")
    print(f"Wrote {paths.latest_html}")


if __name__ == "__main__":
    main()
