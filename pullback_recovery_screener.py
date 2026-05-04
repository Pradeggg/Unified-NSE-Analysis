#!/usr/bin/env python3
"""
Apex Resilience Screener — NIFTY Midcap Select, NIFTY 500, India Defence, CPSE, Microcap 250.

Step 1 — Data analysis: coverage, date range, universe size (printed + written to report).
Step 2 — Screen: RS in pullback window, depth vs 52w peak (≤30%), recovery vs trough,
        volume confirmation, above 50-DMA, “slow” pullback (muted daily damage), fundamentals.

Outputs (date-stamped by analysis day, no clock time): Apex_Resilience_Screener_YYYYMMDD.html, CSV, notes.
Optional Ollama thesis narratives (shown on demand in HTML).

Usage (from project root):
  python3 pullback_recovery_screener.py
  OLLAMA_MODEL=granite4:latest python3 pullback_recovery_screener.py --llm-top 25
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
ORG_DATA = PROJECT_ROOT / "organized" / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"
MAPPING_CSV = DATA_DIR / "index_stock_mapping.csv"
STOCK_CSV = DATA_DIR / "nse_sec_full_data.csv"
INDEX_CSV = DATA_DIR / "nse_index_data.csv"
FUNDAMENTAL_CSV = ORG_DATA / "fundamental_scores_database.csv"

TARGET_INDICES = (
    "NIFTY MIDCAP SELECT",
    "NIFTY 500",
    "NIFTY INDIA DEFENCE",
    "NIFTY CPSE",
    "NIFTY MICROCAP 250",
)

# Product name (HTML title & headers)
SCREENER_DISPLAY_NAME = "Apex Resilience Screener"
SCREENER_TAGLINE = (
    "Pullback-tough leaders — relative strength vs Nifty 500, shallow peak drawdowns, recovery & volume, "
    "above 50-DMA, fundamental quality proxy."
)
SCREENER_SLUG = "Apex_Resilience"

_INDEX_ABBREV = {
    "NIFTY MIDCAP SELECT": "MSC",
    "NIFTY 500": "500",
    "NIFTY INDIA DEFENCE": "DEF",
    "NIFTY CPSE": "CPSE",
    "NIFTY MICROCAP 250": "µ250",
}


def abbrev_index_tags(tags: str) -> str:
    parts = [p.strip() for p in str(tags).split(",") if p.strip()]
    out = [_INDEX_ABBREV.get(p, p.replace("NIFTY ", "")[:4]) for p in sorted(parts)]
    return "·".join(out)


def _fmt_num(v, nd: int = 2, empty: str = "—") -> str:
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return empty
    return f"{float(v):.{nd}f}"


def build_llm_map(rows: pd.DataFrame, model: str) -> dict[str, str]:
    """Symbol -> thesis HTML body (escaped lines with <br/>)."""
    out: dict[str, str] = {}
    for _, r in rows.iterrows():
        sym = str(r["SYMBOL"])
        prompt = (
            "You are an equity analyst for Indian markets. In 4-6 bullet points, explain why this stock "
            "could fit a pullback-recovery quality basket: relative resilience vs Nifty 500, proximity to "
            "52-week highs (limited damage), recovery from recent trough, volume behaviour, and fundamental "
            "score as a proxy for earnings/sales quality. Be factual; cite only numbers given; no price targets.\n\n"
            f"Symbol: {r['SYMBOL']}\n"
            f"Indices: {r['INDEX_TAGS']}\n"
            f"Close: {r['CLOSE']}\n"
            f"Drawdown vs rolling 52w peak (%): {r['DD_VS_PEAK_PCT']}\n"
            f"Above 50-DMA cushion (%): {r['ABOVE_SMA50']}\n"
            f"RS vs Nifty500 over ~60 sessions (percentage pts): {r['RS_PULLBACK_60D_BPS']}\n"
            f"Recovery from ~60d trough (%): {r['RECOVERY_FROM_TROUGH_PCT']}\n"
            f"Recovery velocity (recovery%/bars): {r['RECOVERY_VELOCITY']}\n"
            f"Volume ratio (10d / prior ~50d): {r['VOL_RATIO_10_50']}\n"
            f"Slow-pullback score (RS on down-market days): {r['SLOW_PULLBACK_SCORE']}\n"
            f"Worst single-day drop in window (%): {r['MAX_1D_DROP_60D_PCT']}\n"
            f"Enhanced fundamental score (database proxy): {r['ENHANCED_FUND_SCORE']}\n"
            f"Sales growth score: {r['SALES_GROWTH']}\n"
            f"Earnings quality score: {r['EARNINGS_QUALITY']}\n"
        )
        raw = call_ollama(prompt, model)
        body_html = "<br/>".join(html_lib.escape(line) for line in raw.splitlines())
        out[sym] = body_html
    return out

ROLL_52 = 252
ROLL_60 = 60
ROLL_45 = 45
MIN_HISTORY = ROLL_52 + 55  # cushion for SMA50 + trough window


@dataclass
class ScreenerParams:
    max_dd_vs_52w_peak_pct: float = 30.0  # keep if drop from peak ≤ 30%
    min_above_sma_pct: float = 0.0       # close > SMA50 strictly
    min_fund_score: float = 52.0          # composite fundamental floor (proxy; not live 3QY)
    pullback_days: int = ROLL_60
    trough_lookback: int = ROLL_60


def load_universe_symbols() -> tuple[pd.DataFrame, list[str]]:
    df = pd.read_csv(MAPPING_CSV)
    df["INDEX_NAME"] = df["INDEX_NAME"].astype(str).str.upper().str.strip()
    df["STOCK_SYMBOL"] = df["STOCK_SYMBOL"].astype(str).str.strip()
    mask = df["INDEX_NAME"].isin(TARGET_INDICES)
    sub = df.loc[mask, ["INDEX_NAME", "STOCK_SYMBOL"]].drop_duplicates()
    symbols = sorted(sub["STOCK_SYMBOL"].unique().tolist())
    return sub, symbols


def load_stock_panel(symbols: list[str]) -> pd.DataFrame:
    usecols = ["SYMBOL", "TIMESTAMP", "OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY"]
    chunks: list[pd.DataFrame] = []
    sym_set = set(symbols)
    for chunk in pd.read_csv(STOCK_CSV, usecols=usecols, chunksize=500_000, low_memory=False):
        chunk = chunk[chunk["SYMBOL"].isin(sym_set)]
        if len(chunk):
            chunks.append(chunk)
    if not chunks:
        raise RuntimeError("No stock rows after filter — check universe vs nse_sec_full_data.csv.")
    df = pd.concat(chunks, ignore_index=True)
    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"]).dt.normalize()
    for c in ["OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["SYMBOL", "TIMESTAMP", "CLOSE", "HIGH"])
    df = df.sort_values(["SYMBOL", "TIMESTAMP"]).drop_duplicates(["SYMBOL", "TIMESTAMP"], keep="last")
    return df


def load_benchmark() -> pd.Series:
    ix = pd.read_csv(INDEX_CSV, low_memory=False)
    ix["TIMESTAMP"] = pd.to_datetime(ix["TIMESTAMP"]).dt.normalize()
    ix["CLOSE"] = pd.to_numeric(ix["CLOSE"], errors="coerce")
    nifty = ix[ix["SYMBOL"].astype(str).str.strip() == "Nifty 500"].sort_values("TIMESTAMP")
    nifty = nifty.drop_duplicates("TIMESTAMP", keep="last")
    s = nifty.set_index("TIMESTAMP")["CLOSE"].sort_index()
    s.index = pd.to_datetime(s.index).normalize()
    return s


def per_symbol_metrics(
    g: pd.DataFrame,
    bench: pd.Series,
    params: ScreenerParams,
) -> dict | None:
    """Compute last-row metrics for one symbol time series."""
    g = g.sort_values("TIMESTAMP").reset_index(drop=True)
    if len(g) < MIN_HISTORY:
        return None

    close = g["CLOSE"].astype(float)
    high = g["HIGH"].astype(float)
    low = g["LOW"].astype(float)
    vol = g["TOTTRDQTY"].astype(float).clip(lower=0)
    dt = g["TIMESTAMP"]

    # Trailing 52-week (252 sessions) highest high through today
    rolling_peak = float(high.iloc[-ROLL_52:].max())
    last_close = close.iloc[-1]
    if pd.isna(rolling_peak) or rolling_peak <= 0:
        return None

    dd_vs_peak_pct = (last_close / rolling_peak - 1.0) * 100.0
    if dd_vs_peak_pct < -params.max_dd_vs_52w_peak_pct:
        return None

    sma50 = close.rolling(50, min_periods=45).mean()
    last_sma = sma50.iloc[-1]
    if pd.isna(last_sma) or last_close <= last_sma + params.min_above_sma_pct:
        return None

    dts = pd.DatetimeIndex(pd.to_datetime(dt).dt.normalize())
    b_series = bench.reindex(dts).ffill().bfill()
    if b_series.isna().all():
        return None

    win = params.pullback_days
    if len(close) < win + 5:
        return None

    c_tail = close.iloc[-win:]
    bench_tail = b_series.iloc[-win:]
    stock_ret_win = (c_tail.iloc[-1] / c_tail.iloc[0]) - 1.0 if c_tail.iloc[0] > 0 else np.nan
    bt0 = float(bench_tail.iloc[0])
    bt1 = float(bench_tail.iloc[-1])
    bench_ret_win = (bt1 / bt0 - 1.0) if bt0 > 0 else np.nan
    if pd.isna(stock_ret_win) or pd.isna(bench_ret_win):
        rs_pullback_window = np.nan
    else:
        rs_pullback_window = (stock_ret_win - bench_ret_win) * 100.0

    trough_lb = params.trough_lookback
    sub_close = close.iloc[-trough_lb:]
    trough_rel = int(np.argmin(sub_close.values))
    trough_price = float(sub_close.iloc[trough_rel])
    recovery_pct = (last_close / trough_price - 1.0) * 100.0 if trough_price > 0 else np.nan
    bars_from_trough = max(trough_lb - 1 - trough_rel, 1)
    recovery_velocity = recovery_pct / bars_from_trough

    day_ret_stock = close.pct_change()
    day_ret_bench = b_series.pct_change()
    both = pd.DataFrame({"s": day_ret_stock.values, "b": day_ret_bench.values}).iloc[-win:].dropna()
    slow_score = np.nan
    max_1d_hit = np.nan
    if len(both) > 15:
        neg_mkt = both["b"] < -0.0005
        if neg_mkt.sum() > 5:
            rs_on_down_days = both.loc[neg_mkt, "s"].mean() - both.loc[neg_mkt, "b"].mean()
            slow_score = rs_on_down_days * 10000
        max_1d_hit = float(day_ret_stock.min()) * 100.0

    vol_short = vol.iloc[-10:].mean()
    vol_long = vol.iloc[-win:-10].mean() if vol.iloc[-win:-10].mean() > 0 else vol.iloc[-win].mean()
    vol_ratio = vol_short / vol_long if vol_long > 0 else np.nan

    hi_52_now = float(high.iloc[-ROLL_52:].max())
    pct_of_hi = (last_close / hi_52_now * 100.0) if hi_52_now > 0 else np.nan

    return {
        "LAST_DATE": dt.iloc[-1],
        "CLOSE": round(float(last_close), 2),
        "PEAK_52_ROLL": round(float(rolling_peak), 4),
        "DD_VS_PEAK_PCT": round(float(dd_vs_peak_pct), 2),
        "PCT_OF_52W_RANGE": round(float(pct_of_hi), 2),
        "ABOVE_SMA50": round(float((last_close / last_sma - 1.0) * 100), 2),
        "RS_PULLBACK_60D_BPS": round(float(rs_pullback_window), 4),
        "RECOVERY_FROM_TROUGH_PCT": round(float(recovery_pct), 2),
        "RECOVERY_VELOCITY": round(float(recovery_velocity), 6),
        "VOL_RATIO_10_50": round(float(vol_ratio), 4) if pd.notna(vol_ratio) else np.nan,
        "SLOW_PULLBACK_SCORE": round(float(slow_score), 4) if pd.notna(slow_score) else np.nan,
        "MAX_1D_DROP_60D_PCT": round(float(max_1d_hit), 2) if pd.notna(max_1d_hit) else np.nan,
    }


def load_fundamentals() -> pd.DataFrame:
    if not FUNDAMENTAL_CSV.exists():
        return pd.DataFrame()
    f = pd.read_csv(FUNDAMENTAL_CSV)
    f["SYMBOL"] = f["symbol"].astype(str).str.upper().str.strip()
    return f


def composite_rank(df: pd.DataFrame, z_suffix_cols: list[str] | None = None) -> pd.Series:
    """Higher is better for selected *_Z columns (default: all *_Z)."""
    if z_suffix_cols is None:
        zcols = [c for c in df.columns if c.endswith("_Z")]
    else:
        zcols = [c for c in z_suffix_cols if c in df.columns]
    if not zcols:
        return pd.Series(0.0, index=df.index)
    sub = df[zcols].astype(float).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return sub.mean(axis=1)


def build_screened_dataframe(
    params: ScreenerParams | None = None,
    *,
    require_proxy_fundamentals: bool = True,
    use_fund_z_in_composite: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, tuple, tuple]:
    """
    Run Apex-style filters over the mapped universe.

    When require_proxy_fundamentals=False, symbols are not dropped for missing rows in
    fundamental_scores_database.csv (used when fundamentals come from Screener.in instead).
    When use_fund_z_in_composite=False, composite omits FUND_Z (technical + recovery only).
    """
    params = params or ScreenerParams()
    mapping_df, symbols = load_universe_symbols()
    stock = load_stock_panel(symbols)
    bench = load_benchmark()
    stock_dates = (stock["TIMESTAMP"].min(), stock["TIMESTAMP"].max())
    bench_range = (bench.index.min(), bench.index.max())
    fund = load_fundamentals()

    rows_out: list[dict] = []
    tag_map = (
        mapping_df.groupby("STOCK_SYMBOL")["INDEX_NAME"]
        .agg(lambda x: ",".join(sorted(set(x))))
        .to_dict()
    )

    for sym, grp in stock.groupby("SYMBOL"):
        m = per_symbol_metrics(grp, bench, params)
        if m is None:
            continue
        row: dict = {"SYMBOL": sym, "INDEX_TAGS": tag_map.get(sym, "")}
        row.update(m)
        fs = fund[fund["SYMBOL"] == sym]
        if fs.empty:
            if require_proxy_fundamentals:
                continue
            row["ENHANCED_FUND_SCORE"] = np.nan
            row["SALES_GROWTH"] = np.nan
            row["EARNINGS_QUALITY"] = np.nan
        else:
            fs = fs.sort_values("processed_date").iloc[-1]
            ef = float(fs["ENHANCED_FUND_SCORE"])
            if require_proxy_fundamentals and ef < params.min_fund_score:
                continue
            row["ENHANCED_FUND_SCORE"] = round(ef, 2)
            row["SALES_GROWTH"] = round(float(fs["SALES_GROWTH"]), 2)
            row["EARNINGS_QUALITY"] = round(float(fs["EARNINGS_QUALITY"]), 2)
        rows_out.append(row)

    if not rows_out:
        raise RuntimeError("No stocks passed filters — check universe, params, or data.")

    res = pd.DataFrame(rows_out)

    def z(col: str) -> pd.Series:
        x = res[col].astype(float)
        sd = x.std()
        if sd is None or sd < 1e-12:
            return pd.Series(0.0, index=x.index)
        return (x - x.mean()) / sd

    res["RS_Z"] = z("RS_PULLBACK_60D_BPS")
    res["REC_Z"] = z("RECOVERY_VELOCITY")
    res["VOL_Z"] = z("VOL_RATIO_10_50").fillna(0)
    res["SLOW_Z"] = z("SLOW_PULLBACK_SCORE").fillna(0)
    if use_fund_z_in_composite and "ENHANCED_FUND_SCORE" in res.columns:
        ef = res["ENHANCED_FUND_SCORE"]
        res["FUND_Z"] = z("ENHANCED_FUND_SCORE").fillna(0) if ef.notna().sum() >= 2 else pd.Series(0.0, index=res.index)
    res["PEAK_Z"] = z("DD_VS_PEAK_PCT")

    z_for_composite = (
        ["RS_Z", "REC_Z", "VOL_Z", "SLOW_Z", "FUND_Z", "PEAK_Z"]
        if use_fund_z_in_composite and "FUND_Z" in res.columns
        else ["RS_Z", "REC_Z", "VOL_Z", "SLOW_Z", "PEAK_Z"]
    )
    res["COMPOSITE"] = composite_rank(res, z_suffix_cols=z_for_composite)
    res = res.sort_values("COMPOSITE", ascending=False).reset_index(drop=True)
    return res, mapping_df, stock_dates, bench_range


def call_ollama(prompt: str, model: str) -> str:
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    payload = json.dumps(
        {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.35}}
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{host.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return (data.get("response") or "").strip()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        return f"(LLM unavailable: {e})"


def write_data_analysis_md(
    path: Path,
    mapping_df: pd.DataFrame,
    universe_count: int,
    stock_dates: tuple,
    bench_range: tuple,
    passed_n: int,
) -> None:
    lines = [
        "# Apex Resilience Screener — data analysis (step 1)",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Universe (index constituents)",
        "",
        "| Index | Symbols |",
        "|-------|---------|",
    ]
    for idx in TARGET_INDICES:
        n = mapping_df.loc[mapping_df["INDEX_NAME"] == idx, "STOCK_SYMBOL"].nunique()
        lines.append(f"| {idx} | {n} |")
    lines.extend(
        [
            "",
            f"**Union (unique symbols):** {universe_count}",
            "",
            "## Price data coverage",
            "",
            f"- **Stock file:** `{STOCK_CSV}`",
            f"- **Date range (filtered universe):** `{stock_dates[0]}` → `{stock_dates[1]}`",
            f"- **Benchmark:** Nifty 500 close from `{INDEX_CSV}`",
            f"- **Benchmark range:** `{bench_range[0]}` → `{bench_range[1]}`",
            "",
            "## Interpretation",
            "",
            "- **52w peak** = rolling max of *HIGH* over ~252 sessions (full-year window).",
            "- **Drawdown filter** keeps names within **≤30%** of that rolling peak (your “not below 25–30%” band).",
            "- **RS (pullback window)** = stock total return minus Nifty 500 total return over ~60 sessions.",
            "- **Recovery** = rebound from the minimum *close* inside the same ~60-session window.",
            "- **Slow pullback** = average excess return vs index on days Nifty 500 was down (higher = more resilient).",
            "- **Fundamentals** use `organized/data/fundamental_scores_database.csv` as a **composite proxy**; live last-3-quarter audited metrics are **not** in this file — refresh from filings/Screener for diligence.",
            "",
            f"## Screen output",
            "",
            f"- Rows passing all hard filters: **{passed_n}**",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _td_sort(text: str, sort_val: float | str | None) -> str:
    if sort_val is None or (isinstance(sort_val, float) and (np.isnan(sort_val) or np.isinf(sort_val))):
        sk = ""
    else:
        sk = float(sort_val) if isinstance(sort_val, (int, float, np.floating)) else str(sort_val)
    return f'<td data-sort="{html_lib.escape(str(sk))}">{text}</td>'


def _detail_panel_html(r: pd.Series) -> str:
    esc = html_lib.escape
    tech = [
        ("52W peak (₹)", _fmt_num(r.get("PEAK_52_ROLL"), 2)),
        ("Close (₹)", _fmt_num(r.get("CLOSE"), 2)),
        ("Drawdown vs 52W peak", f"{_fmt_num(r.get('DD_VS_PEAK_PCT'), 1)}%"),
        ("% of 52W high", f"{_fmt_num(r.get('PCT_OF_52W_RANGE'), 1)}%"),
        ("Cushion vs 50-DMA", f"+{_fmt_num(r.get('ABOVE_SMA50'), 1)}%"),
        ("RS vs Nifty (≈60d)", f"{_fmt_num(r.get('RS_PULLBACK_60D_BPS'), 1)} pp"),
        ("Recovery from trough", f"+{_fmt_num(r.get('RECOVERY_FROM_TROUGH_PCT'), 1)}%"),
        ("Recovery velocity", _fmt_num(r.get("RECOVERY_VELOCITY"), 4)),
        ("Vol ratio 10d/50d", f"{_fmt_num(r.get('VOL_RATIO_10_50'), 2)}×"),
        ("Slow-pullback score", _fmt_num(r.get("SLOW_PULLBACK_SCORE"), 2)),
        ("Worst 1-day drop (60d)", f"{_fmt_num(r.get('MAX_1D_DROP_60D_PCT'), 1)}%"),
    ]
    fund = [
        ("Enhanced fund score", _fmt_num(r.get("ENHANCED_FUND_SCORE"), 1)),
        ("Sales growth score", _fmt_num(r.get("SALES_GROWTH"), 1)),
        ("Earnings quality", _fmt_num(r.get("EARNINGS_QUALITY"), 1)),
    ]
    ranks = [
        ("Z: RS", _fmt_num(r.get("RS_Z"), 3)),
        ("Z: Recovery", _fmt_num(r.get("REC_Z"), 3)),
        ("Z: Volume", _fmt_num(r.get("VOL_Z"), 3)),
        ("Z: Slow PB", _fmt_num(r.get("SLOW_Z"), 3)),
        ("Z: Fund", _fmt_num(r.get("FUND_Z"), 3)),
        ("Z: Peak", _fmt_num(r.get("PEAK_Z"), 3)),
        ("Composite", _fmt_num(r.get("COMPOSITE"), 3)),
    ]

    def dl(items: list[tuple[str, str]], title: str) -> str:
        rows_inner = "".join(f"<div><dt>{esc(l)}</dt><dd>{esc(v)}</dd></div>" for l, v in items)
        return f'<div class="dl-block"><h4>{esc(title)}</h4><dl>{rows_inner}</dl></div>'

    sym = esc(str(r["SYMBOL"]))
    tags = esc(str(r.get("INDEX_TAGS", "")))
    return (
        f'<div class="detail-inner">'
        f'<p class="detail-tags"><strong>{sym}</strong> · <span class="muted">{tags}</span></p>'
        f'<div class="detail-grid">{dl(tech, "Technical")}{dl(fund, "Fundamental (proxy)")}'
        f'{dl(ranks, "Model ranks")}</div></div>'
    )


_UI_JS = r"""
(function () {
  const tbody = document.querySelector("#screenTable tbody");
  if (!tbody) return;

  document.querySelectorAll(".btn-details").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const id = btn.getAttribute("data-target");
      const row = document.getElementById(id);
      if (!row) return;
      const open = row.classList.toggle("open");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      btn.textContent = open ? "Hide" : "Details";
    });
  });

  document.querySelectorAll(".btn-thesis").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const sym = btn.getAttribute("data-symbol");
      const raw = (window.THESIS_JSON && window.THESIS_JSON[sym]) || "";
      document.getElementById("modalTitle").textContent = sym + " — investment thesis";
      document.getElementById("modalBody").innerHTML = raw || "<p class='muted'>No thesis for this row. Regenerate with --llm-top and OLLAMA_MODEL.</p>";
      document.getElementById("thesisModal").showModal();
    });
  });

  document.getElementById("closeModal").addEventListener("click", () => {
    document.getElementById("thesisModal").close();
  });

  document.querySelectorAll("#screenTable thead th.sortable").forEach((th, idx) => {
    th.addEventListener("click", () => {
      const asc = !th.dataset.asc || th.dataset.asc === "desc";
      th.dataset.asc = asc ? "asc" : "desc";
      const pairs = [];
      tbody.querySelectorAll("tr.row-head").forEach((head) => {
        const det = head.nextElementSibling;
        pairs.push({ head, detail: det && det.classList.contains("row-detail") ? det : null });
      });
      pairs.sort((a, b) => {
        const ca = a.head.cells[idx];
        const cb = b.head.cells[idx];
        const sa = ca.getAttribute("data-sort");
        const sb = cb.getAttribute("data-sort");
        const na = parseFloat(sa);
        const nb = parseFloat(sb);
        let cmp = 0;
        if (sa !== null && sb !== null && sa !== "" && sb !== ""
            && !Number.isNaN(na) && !Number.isNaN(nb)) cmp = na - nb;
        else cmp = (ca.textContent || "").localeCompare(cb.textContent || "");
        return asc ? cmp : -cmp;
      });
      pairs.forEach(({ head, detail }) => {
        tbody.appendChild(head);
        if (detail) tbody.appendChild(detail);
      });
    });
  });
})();
"""


def build_html_report(
    display_title: str,
    analysis_day_label: str,
    as_of_date: str,
    full_df: pd.DataFrame,
    thesis_map: dict[str, str],
    out_path: Path,
) -> None:
    esc = html_lib.escape
    rows_html: list[str] = []
    for i, (_, r) in enumerate(full_df.iterrows(), start=1):
        sym = str(r["SYMBOL"])
        basket = abbrev_index_tags(str(r.get("INDEX_TAGS", "")))
        price = f"₹{_fmt_num(r['CLOSE'], 1)}"
        dd = f"{_fmt_num(r['DD_VS_PEAK_PCT'], 1)}%"
        dma = f"+{_fmt_num(r['ABOVE_SMA50'], 1)}%"
        rs = f"{_fmt_num(r['RS_PULLBACK_60D_BPS'], 1)} pp"
        rec = f"+{_fmt_num(r['RECOVERY_FROM_TROUGH_PCT'], 1)}%"
        vol = f"{_fmt_num(r['VOL_RATIO_10_50'], 2)}×"
        fund = str(int(round(float(r["ENHANCED_FUND_SCORE"]))))
        apex = _fmt_num(r["COMPOSITE"], 2)
        has_thesis = sym in thesis_map and bool(thesis_map[sym])
        tid = "detail-" + re.sub(r"[^A-Za-z0-9_-]+", "_", sym).strip("_")
        thesis_btn = (
            f'<button type="button" class="btn-thesis btn-sm" data-symbol="{esc(sym)}">Thesis</button>'
            if has_thesis
            else '<span class="muted">—</span>'
        )

        row_cells = "".join(
            [
                _td_sort(str(i), i),
                _td_sort(f'<span class="sym">{esc(sym)}</span>', None),
                _td_sort(esc(basket), None),
                _td_sort(price, float(r["CLOSE"])),
                _td_sort(dd, float(r["DD_VS_PEAK_PCT"])),
                _td_sort(dma, float(r["ABOVE_SMA50"])),
                _td_sort(rs, float(r["RS_PULLBACK_60D_BPS"])),
                _td_sort(rec, float(r["RECOVERY_FROM_TROUGH_PCT"])),
                _td_sort(vol, float(r["VOL_RATIO_10_50"]) if pd.notna(r["VOL_RATIO_10_50"]) else None),
                _td_sort(fund, float(r["ENHANCED_FUND_SCORE"])),
                _td_sort(apex, float(r["COMPOSITE"])),
                f'<td class="actions" data-sort="0"><button type="button" class="btn-details btn-sm" data-target="{tid}" aria-expanded="false">Details</button> {thesis_btn}</td>',
            ]
        )
        rows_html.append(f'<tr class="row-head">{row_cells}</tr>')
        detail = _detail_panel_html(r)
        rows_html.append(
            f'<tr class="row-detail" id="{tid}"><td colspan="12"><div class="detail-shell">{detail}</div></td></tr>'
        )

    thesis_json = json.dumps(thesis_map, ensure_ascii=False)
    thesis_json_esc = thesis_json.replace("</", "<\\/")

    html_main = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{esc(display_title)} · {esc(as_of_date)}</title>
<style>
:root {{
  --bg: #0b1220;
  --panel: #131d2e;
  --panel2: #0f172a;
  --border: #2d3f5c;
  --text: #e8eef7;
  --muted: #8b9cb8;
  --accent: #38bdf8;
  --accent2: #a78bfa;
  --ok: #34d399;
  font-family: "Inter", system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: radial-gradient(1200px 600px at 10% -10%, #1e3a5f22, transparent),
    radial-gradient(800px 400px at 90% 0%, #4c1d9522, transparent), var(--bg);
  color: var(--text);
  min-height: 100vh;
  padding: 28px 20px 48px;
}}
.wrap {{ max-width: 1280px; margin: 0 auto; }}
.brand {{
  display: flex; flex-wrap: wrap; align-items: baseline; gap: 12px 20px;
  margin-bottom: 8px;
}}
.brand h1 {{
  font-size: 1.65rem; font-weight: 700; letter-spacing: -0.02em; margin: 0;
  background: linear-gradient(120deg, #e8eef7, var(--accent));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}}
.badge {{
  font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.12em;
  color: var(--accent); border: 1px solid var(--border); padding: 4px 10px; border-radius: 999px;
}}
.sub {{ color: var(--muted); font-size: 0.95rem; max-width: 720px; line-height: 1.5; margin: 0 0 20px; }}
.meta-bar {{
  display: flex; flex-wrap: wrap; gap: 16px; font-size: 0.88rem; color: var(--muted);
  margin-bottom: 22px;
}}
.meta-bar strong {{ color: var(--text); }}
.card {{
  background: linear-gradient(165deg, #152238f0, #0f172acc);
  border: 1px solid var(--border); border-radius: 16px;
  padding: 18px 20px 20px;
  box-shadow: 0 24px 60px rgba(0,0,0,.35);
}}
.card h2 {{ font-size: 1rem; margin: 0 0 10px; font-weight: 600; }}
.legend {{ font-size: 0.8rem; color: var(--muted); margin-bottom: 12px; line-height: 1.45; }}
.scroll {{ overflow: auto; max-height: min(72vh, 900px); border-radius: 10px; border: 1px solid var(--border); }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.81rem; }}
thead th {{
  position: sticky; top: 0; z-index: 2;
  background: #1a2740; color: #cbd5e1; font-weight: 600;
  padding: 10px 8px; text-align: left; border-bottom: 2px solid var(--border);
}}
thead th.sortable {{ cursor: pointer; user-select: none; }}
thead th.sortable:hover {{ color: var(--accent); }}
tbody td {{
  padding: 9px 8px;
  border-bottom: 1px solid #243047;
  vertical-align: middle;
}}
tbody tr.row-head {{ border-left: 3px solid transparent; }}
tbody tr.row-head:hover {{ background: #1e293b66; border-left-color: var(--accent); }}
.sym {{ font-weight: 600; color: #f1f5f9; }}
.muted {{ color: var(--muted); }}
.btn-sm {{
  font-size: 0.76rem; padding: 6px 10px; border-radius: 8px;
  border: 1px solid var(--border); background: #1e293b; color: var(--text);
  cursor: pointer;
}}
.btn-sm:hover {{ border-color: var(--accent); color: var(--accent); }}
.actions {{ white-space: nowrap; }}
.row-detail {{ display: none; background: #0c1524; }}
.row-detail.open {{ display: table-row; }}
.detail-shell {{ padding: 16px 16px 18px; }}
.detail-inner {{ max-width: 100%; }}
.detail-tags {{ margin: 0 0 12px; font-size: 0.88rem; }}
.detail-grid {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px;
}}
.dl-block h4 {{
  margin: 0 0 8px; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted);
}}
.dl-block dl {{ margin: 0; font-size: 0.82rem; }}
.dl-block dl > div {{
  display: flex; justify-content: space-between; gap: 12px;
  padding: 5px 0; border-bottom: 1px dashed #243047;
}}
.dl-block dt {{ color: var(--muted); }}
.dl-block dd {{ margin: 0; font-variant-numeric: tabular-nums; }}
dialog {{
  border: 1px solid var(--border); border-radius: 14px; padding: 0;
  background: var(--panel); color: var(--text); max-width: 560px; width: calc(100% - 32px);
}}
dialog::backdrop {{ background: rgba(0,0,0,.55); }}
.modal-hd {{
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 18px; border-bottom: 1px solid var(--border);
}}
.modal-hd h3 {{ margin: 0; font-size: 1rem; }}
.modal-bd {{ padding: 16px 18px 20px; font-size: 0.9rem; line-height: 1.55; max-height: min(65vh, 520px); overflow-y: auto; }}
.disclaimer {{ font-size: 0.75rem; color: var(--muted); margin-top: 18px; }}
</style>
</head>
<body>
<div class="wrap">
  <header class="brand">
    <h1>{esc(display_title)}</h1>
    <span class="badge">Recover faster · Hold structure</span>
  </header>
  <p class="sub">{esc(SCREENER_TAGLINE)} Not investment advice — verify fundamentals from filings.</p>
  <div class="meta-bar">
    <span><strong>As of</strong> {esc(analysis_day_label)}</span>
    <span><strong>Universe</strong> Mid Select · Nifty 500 · India Defence · CPSE · Microcap 250</span>
    <span><strong>Names shown</strong> {len(full_df)}</span>
  </div>
  <section class="card">
    <h2>Lead table</h2>
    <p class="legend">
      <strong>vs 52W</strong> = drawdown vs trailing 252-session high ·
      <strong>RS·60d</strong> = excess return vs Nifty 500 (percentage points) ·
      <strong>Vol×</strong> = recent 10d avg volume vs prior ~50 sessions ·
      <strong>Apex</strong> = composite model score. Click column headers to sort.
    </p>
    <div class="scroll">
      <table id="screenTable">
        <thead>
          <tr>
            <th class="sortable">#</th>
            <th class="sortable">Symbol</th>
            <th class="sortable">Basket</th>
            <th class="sortable">Price</th>
            <th class="sortable">vs 52W</th>
            <th class="sortable">vs 50d</th>
            <th class="sortable">RS·60d</th>
            <th class="sortable">Recover</th>
            <th class="sortable">Vol×</th>
            <th class="sortable">Fund</th>
            <th class="sortable">Apex</th>
            <th class="nosort" aria-label="Actions"></th>
          </tr>
        </thead>
        <tbody>
          {chr(10).join(rows_html)}
        </tbody>
      </table>
    </div>
    <p class="disclaimer">Fundamental columns use the project&apos;s scores database as a proxy, not audited quarterly statements.</p>
  </section>
</div>

<dialog id="thesisModal">
  <div class="modal-hd">
    <h3 id="modalTitle">Thesis</h3>
    <button type="button" class="btn-sm" id="closeModal">Close</button>
  </div>
  <div class="modal-bd" id="modalBody"></div>
</dialog>

"""
    doc = html_main + (
        f'<script type="application/json" id="thesis-data">{thesis_json_esc}</script>\n'
        "<script>\n"
        "window.THESIS_JSON = {};\n"
        "try {\n"
        "  const el = document.getElementById('thesis-data');\n"
        "  if (el && el.textContent) window.THESIS_JSON = JSON.parse(el.textContent);\n"
        "} catch (e) { console.warn(e); }\n"
        "</script>\n"
        "<script>\n"
        + _UI_JS
        + "\n</script>\n</body>\n</html>\n"
    )

    out_path.write_text(doc, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm-top", type=int, default=0, help="Top N rows for Ollama narratives (0=skip)")
    parser.add_argument("--max-rows", type=int, default=80, help="Max rows in HTML/CSV output")
    args = parser.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    params_used = ScreenerParams()
    try:
        res, mapping_df, stock_dates, bench_range = build_screened_dataframe(
            params_used,
            require_proxy_fundamentals=True,
            use_fund_z_in_composite=True,
        )
    except RuntimeError as e:
        print(e)
        sys.exit(1)

    passed_n = len(res)
    top = res.head(args.max_rows).copy()

    analysis_dt = pd.to_datetime(top["LAST_DATE"].iloc[0])
    day_key = analysis_dt.strftime("%Y%m%d")
    day_label = analysis_dt.strftime("%d %b %Y")
    as_of_iso = analysis_dt.strftime("%Y-%m-%d")

    slug = SCREENER_SLUG.lower()
    notes_path = REPORTS_DIR / f"{slug}_data_notes_{day_key}.md"
    write_data_analysis_md(
        notes_path,
        mapping_df,
        mapping_df["STOCK_SYMBOL"].nunique(),
        stock_dates,
        bench_range,
        passed_n,
    )

    csv_path = REPORTS_DIR / f"{slug}_screen_{day_key}.csv"
    top.to_csv(csv_path, index=False)

    thesis_map: dict[str, str] = {}
    model = os.environ.get("OLLAMA_MODEL", "").strip()
    if args.llm_top > 0 and model:
        thesis_map = build_llm_map(top.head(args.llm_top), model=model)

    html_path = REPORTS_DIR / f"{SCREENER_SLUG}_Screener_{day_key}.html"
    build_html_report(
        SCREENER_DISPLAY_NAME,
        day_label,
        as_of_iso,
        top,
        thesis_map,
        html_path,
    )

    print("Step 1 — Data notes:", notes_path)
    print("Step 2 — CSV:", csv_path)
    print("Step 2 — HTML:", html_path)
    print("Rows (after filters):", passed_n, "| exported:", len(top))


if __name__ == "__main__":
    main()
