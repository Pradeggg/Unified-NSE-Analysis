#!/usr/bin/env python3
"""
Apex Resilience — full report: Screener.in fundamentals (last 3Q + BS + P&L summaries),
CAN SLIM / Minervini / technical signal from comprehensive analysis CSV, recovery composite,
deterministic guidance, and factual index-relative performance narratives.

Outputs (same calendar date as last price row, YYYYMMDD):
  reports/Apex_Resilience_Full_YYYYMMDD.md
  reports/Apex_Resilience_Full_YYYYMMDD.html
  reports/Apex_Resilience_Full_YYYYMMDD.csv

Usage (project root):
  python3 apex_resilience_full_report.py
  python3 apex_resilience_full_report.py --max-rows 40 --skip-screener
  python3 apex_resilience_full_report.py --reuse-screener-csv
  python3 apex_resilience_full_report.py --comprehensive reports/comprehensive_nse_enhanced_20260422.csv
  OLLAMA_MODEL=llama3.2:latest python3 apex_resilience_full_report.py --llm-top 25

By default the prior Screener output CSV for that run date is deleted and fundamentals are re-fetched live
(R uses HTTP GET + Cache-Control: no-cache). Use --reuse-screener-csv only to intentionally keep an existing file.
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pullback_recovery_screener import (
    PROJECT_ROOT,
    REPORTS_DIR,
    SCREENER_DISPLAY_NAME,
    SCREENER_SLUG,
    SCREENER_TAGLINE,
    STOCK_CSV,
    INDEX_CSV,
    TARGET_INDICES,
    abbrev_index_tags,
    build_screened_dataframe,
    call_ollama,
)


# Mapping from index_stock_mapping.csv labels to SYMBOL column in nse_index_data.csv (when absent, fallback below).
INDEX_TO_BENCHMARK_SYMBOL: dict[str, str] = {
    "NIFTY MIDCAP SELECT": "NIFTY MID SELECT",
    "NIFTY 500": "Nifty 500",
    "NIFTY INDIA DEFENCE": "Nifty 500",
    "NIFTY CPSE": "Nifty CPSE",
    "NIFTY MICROCAP 250": "NIFTY MICROCAP250",
}

BENCHMARK_FALLBACK_NOTE: dict[str, str] = {
    "NIFTY INDIA DEFENCE": "NIFTY INDIA DEFENCE series not found in data/nse_index_data.csv; using Nifty 500 as liquid broad benchmark for excess return.",
}

_SIGNAL_RANK = {"STRONG_BUY": 4, "BUY": 3, "HOLD": 2, "WEAK_HOLD": 1, "SELL": 0}
_RANK_TO_SIGNAL = {v: k for k, v in _SIGNAL_RANK.items()}


def normalize_trading_signal(raw) -> str | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip().upper().replace(" ", "_")
    if s in _SIGNAL_RANK:
        return s
    return None


def downgrade_signal(sig: str | None) -> str:
    if not sig or sig not in _SIGNAL_RANK:
        return "REVIEW"
    r = _SIGNAL_RANK[sig]
    return _RANK_TO_SIGNAL[max(0, r - 1)]


def load_index_close_map() -> dict[str, pd.Series]:
    ix = pd.read_csv(INDEX_CSV, usecols=["SYMBOL", "TIMESTAMP", "CLOSE"], low_memory=False)
    ix["TIMESTAMP"] = pd.to_datetime(ix["TIMESTAMP"]).dt.normalize()
    ix["CLOSE"] = pd.to_numeric(ix["CLOSE"], errors="coerce")
    ix["SYMBOL"] = ix["SYMBOL"].astype(str).str.strip()
    out: dict[str, pd.Series] = {}
    for sym, g in ix.groupby("SYMBOL"):
        s = g.sort_values("TIMESTAMP").drop_duplicates("TIMESTAMP").set_index("TIMESTAMP")["CLOSE"].sort_index()
        out[str(sym)] = s
    return out


def total_return_pct(series: pd.Series, days: int = 60) -> float | None:
    series = series.dropna()
    if len(series) < days + 1:
        return None
    a = float(series.iloc[-1])
    b = float(series.iloc[-(days + 1)])
    if b <= 0 or a <= 0:
        return None
    return round((a / b - 1.0) * 100.0, 4)


def load_stock_subset(symbols: list[str]) -> pd.DataFrame:
    usecols = ["SYMBOL", "TIMESTAMP", "CLOSE"]
    sym_set = set(symbols)
    chunks: list[pd.DataFrame] = []
    for chunk in pd.read_csv(STOCK_CSV, usecols=usecols, chunksize=500_000, low_memory=False):
        chunk = chunk[chunk["SYMBOL"].isin(sym_set)]
        if len(chunk):
            chunks.append(chunk)
    if not chunks:
        return pd.DataFrame(columns=usecols)
    df = pd.concat(chunks, ignore_index=True)
    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"]).dt.normalize()
    df["CLOSE"] = pd.to_numeric(df["CLOSE"], errors="coerce")
    return df.sort_values(["SYMBOL", "TIMESTAMP"]).drop_duplicates(["SYMBOL", "TIMESTAMP"], keep="last")


def benchmark_for_index_tag(tag: str) -> tuple[str, str | None]:
    """Returns (benchmark_symbol, optional note when fallback)."""
    tag = tag.strip().upper()
    bench = INDEX_TO_BENCHMARK_SYMBOL.get(tag)
    if bench is None:
        return "Nifty 500", f"Unknown index tag {tag}; using Nifty 500."
    note = BENCHMARK_FALLBACK_NOTE.get(tag)
    return bench, note


def build_index_narrative(
    symbol: str,
    index_tags: str,
    stock_ret_60d: float | None,
    index_map: dict[str, pd.Series],
) -> str:
    """Single factual sentence per mapped index tag (no causal claims)."""
    parts: list[str] = []
    tags = [t.strip() for t in str(index_tags).split(",") if t.strip()]
    seen_bench: set[str] = set()
    for tag in sorted(tags):
        bench_sym, note = benchmark_for_index_tag(tag)
        if bench_sym in seen_bench:
            continue
        seen_bench.add(bench_sym)
        ix_s = index_map.get(bench_sym)
        ix_ret = total_return_pct(ix_s, 60) if ix_s is not None else None
        if stock_ret_60d is None:
            parts.append(f"{symbol} vs {bench_sym}: stock 60-session return unavailable (history).")
        elif ix_ret is None:
            parts.append(
                f"{symbol} vs {bench_sym}: stock 60-session return {stock_ret_60d:.2f}%; "
                f"benchmark series missing or too short in {INDEX_CSV.name}."
            )
        else:
            exc = stock_ret_60d - ix_ret
            parts.append(
                f"{symbol} vs {bench_sym}: stock 60-session return {stock_ret_60d:.2f}% vs "
                f"index {ix_ret:.2f}% ({exc:+.2f} percentage points excess). Index membership tag: {tag}."
            )
        if note:
            parts[-1] += " " + note
    if not parts:
        parts.append(f"{symbol}: no index tags for benchmark comparison.")
    return " ".join(parts)


def screener_row_complete(row: pd.Series) -> bool:
    q = str(row.get("quarterly_summary", "")).strip()
    bs = str(row.get("balance_sheet_summary", "")).strip()
    pnl = str(row.get("pnl_summary", "")).strip()
    return len(q) > 15 and (len(bs) > 15 or len(pnl) > 15)


def latest_comprehensive_csv(reports_dir: Path, explicit: Path | None) -> Path | None:
    if explicit is not None and explicit.is_file():
        return explicit
    cands = [p for p in reports_dir.glob("comprehensive_nse_enhanced_*.csv") if p.is_file()]
    if not cands:
        return None
    return max(cands, key=lambda p: p.stat().st_mtime)


def merge_comprehensive(comp_path: Path, symbols: set[str]) -> pd.DataFrame:
    df = pd.read_csv(comp_path)
    df["SYMBOL"] = df["SYMBOL"].astype(str).str.upper().str.strip()
    df = df[df["SYMBOL"].isin(symbols)].copy()
    if df.empty:
        return df
    if "TECHNICAL_SCORE" in df.columns:
        df = df.sort_values("TECHNICAL_SCORE", ascending=False)
    df = df.drop_duplicates("SYMBOL", keep="first")
    return df


def _chunked(symbols: list[str], batch_size: int) -> list[list[str]]:
    if batch_size <= 0:
        return [symbols]
    return [symbols[i : i + batch_size] for i in range(0, len(symbols), batch_size)]


def run_screener_fetch(
    symbols: list[str],
    out_csv: Path,
    project_root: Path,
    *,
    symbols_list_path: Path | None = None,
) -> tuple[bool, str]:
    """Run R fetch (live screener.in HTML); returns (ok, stderr+stdout tail)."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = symbols_list_path or (REPORTS_DIR / "_apex_screener_symbols.txt")
    tmp.write_text("\n".join(symbols), encoding="utf-8")
    cmd = [
        "Rscript",
        str(project_root / "working-sector" / "fetch_screener_fundamental_details.R"),
        str(tmp),
        str(out_csv),
    ]
    env = {**os.environ}
    env.setdefault("SCREENER_HTTP_REFRESH", "1")
    try:
        r = subprocess.run(cmd, cwd=str(project_root), capture_output=True, text=True, timeout=7200, env=env)
    except subprocess.TimeoutExpired:
        return False, "Rscript timeout"
    tail = (r.stdout or "")[-4000:] + "\n" + (r.stderr or "")[-4000:]
    return r.returncode == 0, tail


def consolidate_screener_parts(
    part_paths: list[Path],
    expected_symbols: list[str],
) -> pd.DataFrame:
    """Merge batch CSVs; ensure one row per expected symbol (empty summaries if missing)."""
    cols = ("pnl_summary", "quarterly_summary", "balance_sheet_summary", "ratios_summary")
    frames: list[pd.DataFrame] = []
    for p in part_paths:
        if not p.is_file() or p.stat().st_size == 0:
            continue
        try:
            frames.append(pd.read_csv(p))
        except Exception:
            continue
    if not frames:
        out = pd.DataFrame({"SYMBOL": [s.upper() for s in expected_symbols]})
        for c in cols:
            out[c] = ""
        return out

    df = pd.concat(frames, ignore_index=True)
    if "symbol" in df.columns:
        df["SYMBOL"] = df["symbol"].astype(str).str.upper().str.strip()
    elif "SYMBOL" in df.columns:
        df["SYMBOL"] = df["SYMBOL"].astype(str).str.upper().str.strip()
    else:
        df["SYMBOL"] = ""
    df = df.drop_duplicates(subset=["SYMBOL"], keep="last")
    df = df.drop(columns=["symbol"], errors="ignore")

    exp_upper = [s.upper() for s in expected_symbols]
    have = set(df["SYMBOL"].tolist())
    for sym in exp_upper:
        if sym not in have:
            df = pd.concat(
                [df, pd.DataFrame([{"SYMBOL": sym, **{c: "" for c in cols}}])],
                ignore_index=True,
            )
    df = df[df["SYMBOL"].isin(exp_upper)].copy()
    df["_order"] = df["SYMBOL"].map({s: i for i, s in enumerate(exp_upper)})
    df = df.sort_values("_order").drop(columns=["_order"], errors="ignore")
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df


def run_screener_fetch_batched(
    symbols: list[str],
    consolidated_out: Path,
    project_root: Path,
    day_key: str,
    batch_size: int,
    max_workers: int,
) -> tuple[pd.DataFrame, bool, str]:
    """
    Run one R process per batch; batches in parallel (ThreadPool) when max_workers > 1.
    Writes merged fundamentals to consolidated_out. Returns (df, all_ok, log tail).
    """
    batches = _chunked(symbols, batch_size)
    n_b = len(batches)
    part_paths: list[Path] = []
    results: list[tuple[int, bool, str, Path]] = []

    def one_batch(idx: int, chunk: list[str]) -> tuple[int, bool, str, Path]:
        sym_path = REPORTS_DIR / f"_apex_sym_{day_key}_{idx:03d}.txt"
        out_part = REPORTS_DIR / f"_apex_part_{day_key}_{idx:03d}.csv"
        ok, tail = run_screener_fetch(
            chunk, out_part, project_root, symbols_list_path=sym_path
        )
        return idx, ok, tail, out_part

    if max_workers <= 1:
        for i, ch in enumerate(batches):
            results.append(one_batch(i, ch))
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futs = {pool.submit(one_batch, i, ch): i for i, ch in enumerate(batches)}
            for fut in as_completed(futs):
                results.append(fut.result())
    results.sort(key=lambda x: x[0])
    all_ok = all(r[1] for r in results)
    part_paths = [r[3] for r in results]
    bad_tails = [f"--- batch {r[0]} ---\n{r[2][-2000:]}" for r in results if not r[1]]
    log = "\n".join(bad_tails)

    merged_df = consolidate_screener_parts(part_paths, symbols)
    consolidated_out.parent.mkdir(parents=True, exist_ok=True)
    merged_df.to_csv(consolidated_out, index=False)
    print(
        f"Screener batches: {n_b} jobs (≤{batch_size} symbols each), workers={max_workers}; "
        f"consolidated {len(merged_df)} rows → {consolidated_out}",
        file=sys.stderr,
    )
    return merged_df, all_ok, log


def compute_apex_guidance(row: pd.Series, composite_median: float) -> str:
    ok = bool(row.get("SCREENER_DATA_COMPLETE"))
    if not ok:
        return "REVIEW_DATA"
    ts = normalize_trading_signal(row.get("TRADING_SIGNAL"))
    if ts is None:
        return "REVIEW_NO_TECH"
    comp = float(row["COMPOSITE"])
    if comp >= composite_median:
        return ts
    return downgrade_signal(ts)


def _fmt(v, nd=2, empty="—"):
    if v is None or (isinstance(v, float) and (pd.isna(v) or np.isinf(v))):
        return empty
    return f"{float(v):.{nd}f}"


def _td_sort(text: str, sort_val: float | str | None) -> str:
    if sort_val is None or (isinstance(sort_val, float) and (np.isnan(sort_val) or np.isinf(sort_val))):
        sk = ""
    else:
        sk = float(sort_val) if isinstance(sort_val, (int, float, np.floating)) else str(sort_val)
    return f'<td data-sort="{html_lib.escape(str(sk))}">{text}</td>'


def _apex_guidance_sort_key(guidance: str) -> float:
    g = str(guidance).strip().upper().replace(" ", "_")
    order = {"STRONG_BUY": 5.0, "BUY": 4.0, "HOLD": 3.0, "WEAK_HOLD": 2.0, "SELL": 1.0}
    if g.startswith("REVIEW"):
        return 0.5
    return float(order.get(g, 2.5))


def _apex_signal_row_class(guidance: str) -> str:
    g = str(guidance).strip().upper().replace(" ", "_")
    if g.startswith("REVIEW"):
        return "sig-review"
    return {
        "STRONG_BUY": "sig-strong-buy",
        "BUY": "sig-buy",
        "HOLD": "sig-hold",
        "WEAK_HOLD": "sig-weak-hold",
        "SELL": "sig-sell",
    }.get(g, "sig-neutral")


def _detail_panel_full(r: pd.Series) -> str:
    esc = html_lib.escape

    def dl(items: list[tuple[str, str]], title: str) -> str:
        rows_inner = "".join(f"<div><dt>{esc(l)}</dt><dd>{esc(v)}</dd></div>" for l, v in items)
        return f'<div class="dl-block"><h4>{esc(title)}</h4><dl>{rows_inner}</dl></div>'

    tech = [
        ("Close (₹)", esc(_fmt(r.get("CLOSE"), 2))),
        ("52W peak (₹)", esc(_fmt(r.get("PEAK_52_ROLL"), 4))),
        ("Drawdown vs 52W peak", f"{esc(_fmt(r.get('DD_VS_PEAK_PCT'), 2))}%"),
        ("% of 52W high", f"{esc(_fmt(r.get('PCT_OF_52W_RANGE'), 2))}%"),
        ("Cushion vs 50-DMA", f"+{esc(_fmt(r.get('ABOVE_SMA50'), 2))}%"),
        ("RS vs Nifty500 (~60d)", f"{esc(_fmt(r.get('RS_PULLBACK_60D_BPS'), 2))} pp"),
        ("Recovery from trough", f"+{esc(_fmt(r.get('RECOVERY_FROM_TROUGH_PCT'), 2))}%"),
        ("Recovery velocity", esc(_fmt(r.get("RECOVERY_VELOCITY"), 6))),
        ("Vol ratio 10d/50d", f"{esc(_fmt(r.get('VOL_RATIO_10_50'), 3))}×"),
        ("Slow-pullback score", esc(_fmt(r.get("SLOW_PULLBACK_SCORE"), 3))),
        ("Worst 1-day drop (60d)", f"{esc(_fmt(r.get('MAX_1D_DROP_60D_PCT'), 2))}%"),
        ("APEX_GUIDANCE", esc(str(r.get("APEX_GUIDANCE", "")))),
        ("COMPOSITE", esc(_fmt(r.get("COMPOSITE"), 4))),
    ]
    ranks = [
        ("Z RS", esc(_fmt(r.get("RS_Z"), 4))),
        ("Z Recovery", esc(_fmt(r.get("REC_Z"), 4))),
        ("Z Volume", esc(_fmt(r.get("VOL_Z"), 4))),
        ("Z Slow PB", esc(_fmt(r.get("SLOW_Z"), 4))),
        ("Z Peak", esc(_fmt(r.get("PEAK_Z"), 4))),
    ]
    tech_comp = [
        ("TECHNICAL_SCORE", esc(str(r.get("TECHNICAL_SCORE", "—")))),
        ("TRADING_SIGNAL", esc(str(r.get("TRADING_SIGNAL", "—")))),
        ("CAN SLIM", esc(str(r.get("CAN_SLIM_SCORE", "—")))),
        ("Minervini", esc(str(r.get("MINERVINI_SCORE", "—")))),
        ("TREND_SIGNAL", esc(str(r.get("TREND_SIGNAL", "—")))),
        ("RELATIVE_STRENGTH", esc(str(r.get("RELATIVE_STRENGTH", "—")))),
        ("ANALYSIS_DATE", esc(str(r.get("ANALYSIS_DATE", "—")))),
    ]
    fund_txt = ""
    for label, key in (
        ("P&L summary (Screener)", "pnl_summary"),
        ("Quarterly (last 3Q)", "quarterly_summary"),
        ("Balance sheet", "balance_sheet_summary"),
        ("Ratios", "ratios_summary"),
    ):
        txt = str(r.get(key, "") or "").strip()
        fund_txt += f'<div class="fund-block"><h5>{esc(label)}</h5><pre class="fund-pre">{esc(txt) or "—"}</pre></div>'
    meta = dl(
        [
            ("SCREENER_DATA_COMPLETE", "Y" if r.get("SCREENER_DATA_COMPLETE") else "N"),
            ("SCREENER_FETCH_AT", esc(str(r.get("SCREENER_FETCH_AT", "")))),
        ],
        "Fundamental metadata",
    )
    idx_bl = f'<div class="fund-block"><h5>Factual benchmark narrative</h5><p class="idx-text">{esc(str(r.get("INDEX_NARRATIVE", "") or ""))}</p></div>'
    sym = esc(str(r["SYMBOL"]))
    tags = esc(str(r.get("INDEX_TAGS", "")))
    return (
        f'<div class="detail-inner">'
        f'<p class="detail-tags"><strong>{sym}</strong> · <span class="muted">{tags}</span></p>'
        f'<div class="detail-grid">{dl(tech, "Technical screen")}{dl(ranks, "Model Z-scores")}'
        f'{dl(tech_comp, "Comprehensive file")}</div>'
        f'{meta}{idx_bl}<div class="fund-grid">{fund_txt}</div></div>'
    )


def build_enhanced_narrative_map(df: pd.DataFrame, model: str) -> dict[str, str]:
    """Symbol -> escaped HTML lines (br-separated) for the narrative modal."""
    out: dict[str, str] = {}
    for _, r in df.iterrows():
        sym = str(r["SYMBOL"])
        block = f"""SYMBOL: {sym}
INDEX_TAGS: {r.get('INDEX_TAGS', '')}
APEX_GUIDANCE: {r.get('APEX_GUIDANCE', '')}
TRADING_SIGNAL: {r.get('TRADING_SIGNAL', '')}
TECHNICAL_SCORE: {r.get('TECHNICAL_SCORE', '')}
CAN_SLIM_SCORE: {r.get('CAN_SLIM_SCORE', '')}
MINERVINI_SCORE: {r.get('MINERVINI_SCORE', '')}
TREND_SIGNAL: {r.get('TREND_SIGNAL', '')}
RELATIVE_STRENGTH: {r.get('RELATIVE_STRENGTH', '')}
COMPOSITE (recovery rank): {_fmt(r.get('COMPOSITE'), 4)}
CLOSE: {r.get('CLOSE', '')} | DD_VS_PEAK_PCT: {r.get('DD_VS_PEAK_PCT', '')} | RS_PULLBACK_60D_BPS: {r.get('RS_PULLBACK_60D_BPS', '')}
RECOVERY_FROM_TROUGH_PCT: {r.get('RECOVERY_FROM_TROUGH_PCT', '')} | VOL_RATIO_10_50: {r.get('VOL_RATIO_10_50', '')}
SCREENER_DATA_COMPLETE: {r.get('SCREENER_DATA_COMPLETE', '')}
SCREENER_FETCH_AT: {r.get('SCREENER_FETCH_AT', '')}
P&L summary: {r.get('pnl_summary', '')}
Quarterly summary: {r.get('quarterly_summary', '')}
Balance sheet summary: {r.get('balance_sheet_summary', '')}
Ratios summary: {r.get('ratios_summary', '')}
INDEX_NARRATIVE (factual): {r.get('INDEX_NARRATIVE', '')}
"""
        prompt = (
            "You are an equity research analyst covering Indian equities (NSE). Produce an **enhanced narrative** "
            "for an internal Apex Resilience quality screen.\n\n"
            "Hard rules (must follow):\n"
            "- Use ONLY facts that appear in the INPUT block. Do not invent revenue, EPS, dates, news, or price targets.\n"
            "- If a field is empty or missing, write \"not provided in inputs\" for that item — never guess.\n"
            "- Do not contradict APEX_GUIDANCE or TRADING_SIGNAL; you may explain how the numbers relate to those labels.\n"
            "- Output 6–10 bullet points, each starting with \"• \", plain English, no markdown headings.\n\n"
            "Cover, in order:\n"
            "1) Basket / index membership and benchmark context.\n"
            "2) Pullback-recovery mechanics: distance from 52W peak, RS vs Nifty 500 over the window, trough recovery, volume.\n"
            "3) CAN SLIM / Minervini / technical trend as given.\n"
            "4) Screener fundamentals: tie narrative to verbatim P&L, quarterly, balance sheet, ratios text only.\n"
            "5) Versus-index facts from INDEX_NARRATIVE.\n"
            "6) Data gaps: flag incomplete Screener lines or REVIEW_* guidance explicitly.\n\n"
            "INPUT:\n"
            + block
        )
        raw = call_ollama(prompt, model)
        body_html = "<br/>".join(html_lib.escape(line) for line in raw.splitlines())
        out[sym] = body_html
    return out


_APEX_HTML_UI_JS = r"""
(function () {
  const tbody = document.querySelector("#apexFullTable tbody");
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

  document.querySelectorAll(".btn-narrative").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const sym = btn.getAttribute("data-symbol");
      const raw = (window.APEX_NARRATIVE_JSON && window.APEX_NARRATIVE_JSON[sym]) || "";
      document.getElementById("narrModalTitle").textContent = sym + " — enhanced narrative";
      document.getElementById("narrModalBody").innerHTML = raw || "<p class='muted'>No narrative generated. Run with --llm-top &gt; 0 and set OLLAMA_MODEL.</p>";
      document.getElementById("narrativeModal").showModal();
    });
  });

  document.getElementById("narrCloseModal").addEventListener("click", () => {
    document.getElementById("narrativeModal").close();
  });

  document.querySelectorAll("#apexFullTable thead th.sortable").forEach((th, idx) => {
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


def build_html_full(
    title: str,
    day_label: str,
    as_of: str,
    df: pd.DataFrame,
    methodology_lines: list[str],
    comp_path: str | None,
    screener_path: str | None,
    out_path: Path,
    narrative_map: dict[str, str] | None = None,
) -> None:
    esc = html_lib.escape
    narrative_map = narrative_map or {}
    rows_html: list[str] = []
    ncol = 10
    for i, (_, r) in enumerate(df.iterrows(), start=1):
        sym = str(r["SYMBOL"])
        basket = abbrev_index_tags(str(r.get("INDEX_TAGS", "")))
        guidance_raw = str(r.get("APEX_GUIDANCE", ""))
        guidance = esc(guidance_raw)
        can_m = esc(str(r.get("CAN_SLIM_SCORE", "—")))
        mn = esc(str(r.get("MINERVINI_SCORE", "—")))
        comp_v = r.get("COMPOSITE")
        comp_f = float(comp_v) if pd.notna(comp_v) else None
        comp = esc(_fmt(comp_v, 3))
        ts = esc(str(r.get("TRADING_SIGNAL", "—")))
        sc_ok = "yes" if r.get("SCREENER_DATA_COMPLETE") else "no"
        sig_cls = _apex_signal_row_class(guidance_raw)
        tid = "detail-" + re.sub(r"[^A-Za-z0-9_-]+", "_", sym).strip("_")
        has_narr = sym in narrative_map and bool(narrative_map[sym])
        narr_btn = (
            f'<button type="button" class="btn-narrative btn-sm" data-symbol="{esc(sym)}">Narrative</button>'
            if has_narr
            else '<span class="muted">—</span>'
        )
        guide_sort = _apex_guidance_sort_key(guidance_raw)
        _ts = pd.to_numeric(r.get("TECHNICAL_SCORE"), errors="coerce")
        tech_sort = float(_ts) if pd.notna(_ts) else None

        row_cells = "".join(
            [
                _td_sort(str(i), i),
                _td_sort(f'<span class="sym">{esc(sym)}</span>', None),
                _td_sort(esc(basket), None),
                _td_sort(f'<span class="pill pill-{sig_cls.replace("sig-", "")}">{guidance}</span>', guide_sort),
                _td_sort(ts, tech_sort),
                _td_sort(comp, comp_f),
                _td_sort(
                    can_m,
                    float(pd.to_numeric(r.get("CAN_SLIM_SCORE"), errors="coerce"))
                    if pd.notna(pd.to_numeric(r.get("CAN_SLIM_SCORE"), errors="coerce"))
                    else None,
                ),
                _td_sort(
                    mn,
                    float(pd.to_numeric(r.get("MINERVINI_SCORE"), errors="coerce"))
                    if pd.notna(pd.to_numeric(r.get("MINERVINI_SCORE"), errors="coerce"))
                    else None,
                ),
                _td_sort(sc_ok, 1.0 if r.get("SCREENER_DATA_COMPLETE") else 0.0),
                f'<td class="actions" data-sort="0">'
                f'<button type="button" class="btn-details btn-sm" data-target="{tid}" aria-expanded="false">Details</button> '
                f"{narr_btn}</td>",
            ]
        )
        rows_html.append(f'<tr class="row-head {sig_cls}">{row_cells}</tr>')
        detail = _detail_panel_full(r)
        rows_html.append(
            f'<tr class="row-detail" id="{tid}"><td colspan="{ncol}"><div class="detail-shell">{detail}</div></td></tr>'
        )

    meth = "".join(f"<li>{esc(x)}</li>" for x in methodology_lines)
    meta_comp = esc(comp_path or "(none)")
    meta_scr = esc(screener_path or "(none)")
    narr_json = json.dumps(narrative_map, ensure_ascii=False)
    narr_json_esc = narr_json.replace("</", "<\\/")

    legend = (
        "Click column headers to sort. "
        "<strong>Details</strong> expands technical metrics, Z-scores, comprehensive fields, Screener summaries, and benchmark narrative. "
        "<strong>Narrative</strong> opens the LLM-enhanced view (generated with <code>--llm-top</code> + <code>OLLAMA_MODEL</code>)."
    )

    html_main = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{esc(title)} · {esc(as_of)}</title>
<style>
:root {{
  --bg:#0b1220; --panel:#131d2e; --border:#2d3f5c; --text:#e8eef7; --muted:#8b9cb8; --accent:#38bdf8;
  font-family:"Inter",system-ui,sans-serif;
}}
body {{ margin:0; background:radial-gradient(1200px 600px at 10% -10%, #1e3a5f22, transparent), var(--bg);
  color:var(--text); padding:28px 20px 48px; }}
.wrap {{ max-width:1320px; margin:0 auto; }}
h1 {{ font-size:1.55rem; margin:0 0 8px; font-weight:700; }}
.sub {{ color:var(--muted); font-size:.95rem; margin:0 0 16px; max-width:780px; line-height:1.5; }}
.meta {{ font-size:.85rem; color:var(--muted); margin-bottom:18px; }}
.card {{ background:linear-gradient(165deg,#152238f0,#0f172acc); border:1px solid var(--border); border-radius:14px;
  padding:18px 20px 20px; box-shadow:0 20px 50px rgba(0,0,0,.35); }}
.card h2 {{ font-size:1rem; margin:0 0 8px; font-weight:600; }}
.legend {{ font-size:.78rem; color:var(--muted); margin-bottom:12px; line-height:1.45; }}
.scroll {{ overflow:auto; max-height:min(78vh,920px); border-radius:10px; border:1px solid var(--border); }}
table {{ width:100%; border-collapse:collapse; font-size:.81rem; }}
thead th {{ position:sticky; top:0; z-index:2; background:#1a2740; color:#cbd5e1; font-weight:600;
  padding:10px 8px; text-align:left; border-bottom:2px solid var(--border); }}
thead th.sortable {{ cursor:pointer; user-select:none; }}
thead th.sortable:hover {{ color:var(--accent); }}
tbody td {{ padding:9px 8px; border-bottom:1px solid #243047; vertical-align:middle; }}
tbody tr.row-head {{ border-left:4px solid transparent; }}
tbody tr.row-head:hover {{ background:#1e293b55; }}
tbody tr.row-head.sig-strong-buy {{ border-left-color:#22c55e; background:linear-gradient(90deg,#14532d18,transparent); }}
tbody tr.row-head.sig-buy {{ border-left-color:#14b8a6; background:linear-gradient(90deg,#134e4a18,transparent); }}
tbody tr.row-head.sig-hold {{ border-left-color:#eab308; background:linear-gradient(90deg,#713f1218,transparent); }}
tbody tr.row-head.sig-weak-hold {{ border-left-color:#f97316; background:linear-gradient(90deg,#7c2d1218,transparent); }}
tbody tr.row-head.sig-sell {{ border-left-color:#ef4444; background:linear-gradient(90deg,#7f1d1d22,transparent); }}
tbody tr.row-head.sig-review {{ border-left-color:#a78bfa; background:linear-gradient(90deg,#4c1d9520,transparent); }}
tbody tr.row-head.sig-neutral {{ border-left-color:#64748b; }}
.pill {{ display:inline-block; padding:2px 8px; border-radius:6px; font-size:.76rem; font-weight:600; }}
.pill-strong-buy {{ background:#14532d; color:#bbf7d0; }}
.pill-buy {{ background:#134e4a; color:#99f6e4; }}
.pill-hold {{ background:#713f12; color:#fef08a; }}
.pill-weak-hold {{ background:#7c2d12; color:#fed7aa; }}
.pill-sell {{ background:#7f1d1d; color:#fecaca; }}
.pill-review {{ background:#4c1d95; color:#e9d5ff; }}
.pill-neutral {{ background:#334155; color:#e2e8f0; }}
.sym {{ font-weight:600; color:#f8fafc; }}
.muted {{ color:var(--muted); }}
.btn-sm {{ font-size:.74rem; padding:6px 10px; border-radius:8px; border:1px solid var(--border);
  background:#1e293b; color:var(--text); cursor:pointer; margin-right:6px; }}
.btn-sm:hover {{ border-color:var(--accent); color:var(--accent); }}
.actions {{ white-space:nowrap; }}
.row-detail {{ display:none; background:#0c1524; }}
.row-detail.open {{ display:table-row; }}
.detail-shell {{ padding:16px 18px 20px; }}
.detail-inner {{ max-width:100%; }}
.detail-tags {{ margin:0 0 12px; font-size:.88rem; }}
.detail-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:16px; }}
.dl-block h4 {{ margin:0 0 8px; font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); }}
.dl-block dl {{ margin:0; font-size:.82rem; }}
.dl-block dl > div {{ display:flex; justify-content:space-between; gap:12px; padding:5px 0; border-bottom:1px dashed #243047; }}
.dl-block dt {{ color:var(--muted); }}
.dl-block dd {{ margin:0; font-variant-numeric:tabular-nums; text-align:right; max-width:65%; }}
.fund-grid {{ margin-top:14px; display:flex; flex-direction:column; gap:12px; }}
.fund-block h5 {{ margin:0 0 6px; font-size:.72rem; color:var(--accent); text-transform:uppercase; letter-spacing:.04em; }}
.fund-pre {{ margin:0; white-space:pre-wrap; word-break:break-word; font-size:.78rem; line-height:1.45;
  background:#0f172a; border:1px solid #243047; border-radius:8px; padding:10px 12px; color:#cbd5e1; }}
.idx-text {{ font-size:.82rem; line-height:1.5; color:#94a3b8; margin:0; }}
ul.method {{ font-size:.88rem; color:var(--muted); line-height:1.5; }}
dialog {{ border:1px solid var(--border); border-radius:14px; padding:0; background:var(--panel); color:var(--text);
  max-width:640px; width:calc(100% - 32px); }}
dialog::backdrop {{ background:rgba(0,0,0,.55); }}
.modal-hd {{ display:flex; justify-content:space-between; align-items:center; padding:14px 18px; border-bottom:1px solid var(--border); }}
.modal-hd h3 {{ margin:0; font-size:1rem; }}
.modal-bd {{ padding:16px 18px 22px; font-size:.9rem; line-height:1.55; max-height:min(68vh,560px); overflow-y:auto; }}
</style></head><body><div class="wrap">
<h1>{esc(title)} — full fundamentals</h1>
<p class="sub">{esc(SCREENER_TAGLINE.replace("fundamental quality proxy.", "Screener.in summaries + comprehensive technical file."))}</p>
<div class="meta"><strong>As of</strong> {esc(day_label)} · <strong>Comprehensive CSV</strong> {meta_comp} · <strong>Screener CSV</strong> {meta_scr}</div>
<section class="card"><h2 style="margin-top:0;">Methodology</h2><ul class="method">{meth}</ul></section>
<section class="card" style="margin-top:14px;"><h2 style="margin-top:0;">Lead table</h2>
<p class="legend">{legend}</p>
<div class="scroll"><table id="apexFullTable">
<thead><tr>
<th class="sortable">#</th>
<th class="sortable">Symbol</th>
<th class="sortable">Basket</th>
<th class="sortable">APEX guidance</th>
<th class="sortable">Tech signal</th>
<th class="sortable">Recovery composite</th>
<th class="sortable">CAN SLIM</th>
<th class="sortable">Minervini</th>
<th class="sortable">Screener OK</th>
<th class="nosort">Actions</th>
</tr></thead><tbody>
{chr(10).join(rows_html)}
</tbody></table></div>
<p style="font-size:.75rem;color:var(--muted);margin-top:14px;">Not investment advice. VERIFY all figures on screener.in and exchange filings.</p>
</section>

<dialog id="narrativeModal">
  <div class="modal-hd">
    <h3 id="narrModalTitle">Enhanced narrative</h3>
    <button type="button" class="btn-sm" id="narrCloseModal">Close</button>
  </div>
  <div class="modal-bd" id="narrModalBody"></div>
</dialog>

"""
    doc = (
        html_main
        + f'<script type="application/json" id="narrative-data">{narr_json_esc}</script>\n'
        + "<script>\n"
        + "window.APEX_NARRATIVE_JSON = {};\n"
        + "try {\n"
        + "  const el = document.getElementById('narrative-data');\n"
        + "  if (el && el.textContent) window.APEX_NARRATIVE_JSON = JSON.parse(el.textContent);\n"
        + "} catch (e) { console.warn(e); }\n"
        + "</script>\n"
        + "<script>\n"
        + _APEX_HTML_UI_JS
        + "\n</script>\n</body>\n</html>\n"
    )
    out_path.write_text(doc, encoding="utf-8")


def build_markdown_report(
    day_key: str,
    df: pd.DataFrame,
    methodology: list[str],
    comp_file: str | None,
    screener_file: str | None,
    out_path: Path,
) -> None:
    lines = [
        f"# {SCREENER_DISPLAY_NAME} — full report ({day_key})",
        "",
        f"Generated (run time): {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Methodology",
        "",
        *[f"- {m}" for m in methodology],
        "",
        "## Inputs",
        "",
        f"- **Comprehensive analysis CSV:** `{comp_file or 'not used'}`",
        f"- **Screener.in extract CSV:** `{screener_file or 'not used'}`",
        "",
        "## Holdings table",
        "",
        "| SYMBOL | INDEX_TAGS | APEX_GUIDANCE | TRADING_SIGNAL | COMPOSITE | CAN_SLIM | MINERVINI | SCREENER_OK |",
        "|--------|--------------|---------------|----------------|-----------|----------|-----------|-------------|",
    ]
    for _, r in df.iterrows():
        lines.append(
            f"| {r['SYMBOL']} | {r.get('INDEX_TAGS','')} | {r.get('APEX_GUIDANCE')} | "
            f"{r.get('TRADING_SIGNAL','')} | {_fmt(r.get('COMPOSITE'), 3)} | "
            f"{r.get('CAN_SLIM_SCORE','')} | {r.get('MINERVINI_SCORE','')} | "
            f"{'Y' if r.get('SCREENER_DATA_COMPLETE') else 'N'} |"
        )
    lines.extend(["", "## Screener summaries (verbatim columns)", ""])
    for _, r in df.iterrows():
        lines.append(f"### {r['SYMBOL']}")
        for col in ("pnl_summary", "quarterly_summary", "balance_sheet_summary", "ratios_summary"):
            val = str(r.get(col, "")).strip()
            lines.append(f"- **{col}:** {val or '—'}")
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-rows", type=int, default=80)
    parser.add_argument("--skip-screener", action="store_true", help="Skip R fetch; fundamentals columns empty.")
    parser.add_argument(
        "--reuse-screener-csv",
        action="store_true",
        help="Use existing reports/Apex_Resilience_screener_fundamentals_<date>.csv if present (skip live refresh).",
    )
    parser.add_argument("--comprehensive", type=Path, default=None, help="Path to comprehensive_nse_enhanced_*.csv")
    parser.add_argument(
        "--llm-top",
        type=int,
        default=0,
        help="Call Ollama for enhanced narrative on first N rows (requires OLLAMA_MODEL env). 0=skip.",
    )
    parser.add_argument(
        "--screener-batch-size",
        type=int,
        default=40,
        metavar="N",
        help="Symbols per R subprocess when fetching Screener.in (split into batches).",
    )
    parser.add_argument(
        "--screener-workers",
        type=int,
        default=3,
        metavar="W",
        help="Parallel R jobs for Screener fetch (1 = sequential batches). Reduce if rate-limited.",
    )
    args = parser.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        res, mapping_df, stock_dates, bench_range = build_screened_dataframe(
            require_proxy_fundamentals=False,
            use_fund_z_in_composite=False,
        )
    except RuntimeError as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    top = res.head(args.max_rows).copy()
    symbols = top["SYMBOL"].tolist()
    sym_set = set(symbols)

    analysis_dt = pd.to_datetime(top["LAST_DATE"].iloc[0])
    day_key = analysis_dt.strftime("%Y%m%d")
    day_label = analysis_dt.strftime("%d %b %Y")

    stock_panel = load_stock_subset(symbols)
    index_map = load_index_close_map()

    stock_rets: dict[str, float | None] = {}
    for sym in symbols:
        g = stock_panel[stock_panel["SYMBOL"] == sym]
        if g.empty:
            stock_rets[sym] = None
            continue
        ser = g.set_index("TIMESTAMP")["CLOSE"].sort_index()
        stock_rets[sym] = total_return_pct(ser, 60)

    narratives: dict[str, str] = {}
    for sym in symbols:
        row = top.loc[top["SYMBOL"] == sym].iloc[0]
        narratives[sym] = build_index_narrative(sym, str(row.get("INDEX_TAGS", "")), stock_rets.get(sym), index_map)

    comp_path = latest_comprehensive_csv(REPORTS_DIR, args.comprehensive)
    comp_df = merge_comprehensive(comp_path, sym_set) if comp_path else pd.DataFrame()
    comp_cols = [
        c
        for c in (
            "SYMBOL",
            "TECHNICAL_SCORE",
            "TRADING_SIGNAL",
            "CAN_SLIM_SCORE",
            "MINERVINI_SCORE",
            "TREND_SIGNAL",
            "RELATIVE_STRENGTH",
            "ANALYSIS_DATE",
        )
        if c in comp_df.columns
    ]
    comp_small = comp_df[comp_cols] if len(comp_df) and comp_cols else pd.DataFrame()

    merged = top.merge(comp_small, on="SYMBOL", how="left")

    screener_csv = REPORTS_DIR / f"{SCREENER_SLUG}_screener_fundamentals_{day_key}.csv"
    screener_ok_run = False
    fetch_at_iso = ""
    if args.skip_screener:
        scr = pd.DataFrame({"SYMBOL": [s.upper() for s in symbols]})
        for c in ("pnl_summary", "quarterly_summary", "balance_sheet_summary", "ratios_summary"):
            scr[c] = ""
        fetch_at_iso = "skipped"
    elif args.reuse_screener_csv and screener_csv.is_file():
        scr = pd.read_csv(screener_csv)
        screener_ok_run = True
        fetch_at_iso = datetime.fromtimestamp(screener_csv.stat().st_mtime, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        print(f"Using existing Screener CSV (--reuse-screener-csv), mtime={fetch_at_iso}: {screener_csv}", file=sys.stderr)
    else:
        screener_csv.unlink(missing_ok=True)
        for p in REPORTS_DIR.glob(f"_apex_part_{day_key}_*.csv"):
            p.unlink(missing_ok=True)
        for p in REPORTS_DIR.glob(f"_apex_sym_{day_key}_*.txt"):
            p.unlink(missing_ok=True)
        scr, screener_ok_run, r_log = run_screener_fetch_batched(
            symbols,
            screener_csv,
            PROJECT_ROOT,
            day_key,
            batch_size=max(1, args.screener_batch_size),
            max_workers=max(1, args.screener_workers),
        )
        fetch_at_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not screener_ok_run:
            fetch_at_iso += " (partial: some Screener batches failed)"
            print(
                "Warning: one or more Screener batch jobs failed. Partial data consolidated. Tail:\n",
                r_log[-4000:],
                file=sys.stderr,
            )
    if "symbol" in scr.columns and "SYMBOL" not in scr.columns:
        scr["SYMBOL"] = scr["symbol"].astype(str).str.upper().str.strip()
    scr = scr.drop(columns=["symbol"], errors="ignore")
    merged = merged.merge(scr, on="SYMBOL", how="left")

    for col in ("pnl_summary", "quarterly_summary", "balance_sheet_summary", "ratios_summary"):
        if col not in merged.columns:
            merged[col] = ""

    merged["SCREENER_DATA_COMPLETE"] = merged.apply(screener_row_complete, axis=1)
    merged["SCREENER_FETCH_AT"] = fetch_at_iso
    merged["INDEX_NARRATIVE"] = merged["SYMBOL"].map(narratives)

    med = float(merged["COMPOSITE"].median())
    merged["APEX_GUIDANCE"] = merged.apply(lambda r: compute_apex_guidance(r, med), axis=1)

    methodology = [
        "Universe: index_stock_mapping constituents for "
        + ", ".join(TARGET_INDICES)
        + ".",
        f"Price screen: same as Apex Resilience (≤30% from rolling 52-week high of HIGH, "
        f"close > SMA50, recovery/volume metrics; composite excludes proxy fund Z). "
        f"Stock data date range (filtered): {stock_dates[0]} → {stock_dates[1]}; "
        f"benchmark range: {bench_range[0]} → {bench_range[1]}.",
        "Fundamentals: refreshed from live www.screener.in on each run (HTTP GET with Cache-Control: no-cache via R/httr); "
        "prior Apex_Resilience_screener_fundamentals_<date>.csv is removed before re-fetch unless --reuse-screener-csv. "
        f"Batched fetch: --screener-batch-size {args.screener_batch_size}, --screener-workers {args.screener_workers} "
        "(parallel R jobs per batch; consolidated into one CSV). "
        "working-sector/fetch_screener_fundamental_details.R formats P&L, last 3 quarters, balance sheet, ratios. "
        "Column SCREENER_FETCH_AT records UTC time of this pull (or file mtime when reusing CSV). "
        "No substitution from fundamental_scores_database.csv.",
        "CAN SLIM / Minervini / TRADING_SIGNAL: merged from the selected comprehensive_nse_enhanced CSV (TECHNICAL_SCORE-based rules in fixed_nse_universe_analysis.determine_trading_signal).",
        f"APEX_GUIDANCE: if Screener data incomplete → REVIEW_DATA; else if TRADING_SIGNAL missing → REVIEW_NO_TECH; "
        f"else if COMPOSITE ≥ batch median ({med:.4f}) keep TRADING_SIGNAL; else one-step downgrade.",
        "Index narrative: 60-session total return of stock vs benchmark index series in nse_index_data.csv; "
        "tags from INDEX_TAGS map to benchmarks via INDEX_TO_BENCHMARK_SYMBOL (documented fallbacks).",
    ]

    scr_meta = None
    if args.skip_screener:
        scr_meta = None
    elif screener_ok_run:
        scr_meta = str(screener_csv)
    else:
        scr_meta = f"{screener_csv} (fetch failed)"

    out_csv = REPORTS_DIR / f"{SCREENER_SLUG}_Full_{day_key}.csv"
    merged.to_csv(out_csv, index=False)

    out_md = REPORTS_DIR / f"{SCREENER_SLUG}_Full_{day_key}.md"
    build_markdown_report(
        day_key,
        merged,
        methodology,
        str(comp_path) if comp_path else None,
        scr_meta,
        out_md,
    )

    narrative_map: dict[str, str] = {}
    ollama_model = os.environ.get("OLLAMA_MODEL", "").strip()
    if args.llm_top > 0 and ollama_model:
        sub = merged.head(args.llm_top)
        print(f"Generating enhanced narratives for {len(sub)} symbols via Ollama ({ollama_model})...", file=sys.stderr)
        narrative_map = build_enhanced_narrative_map(sub, ollama_model)
    elif args.llm_top > 0 and not ollama_model:
        print("Warning: --llm-top set but OLLAMA_MODEL is empty; skipping LLM narratives.", file=sys.stderr)

    out_html = REPORTS_DIR / f"{SCREENER_SLUG}_Full_{day_key}.html"
    build_html_full(
        SCREENER_DISPLAY_NAME,
        day_label,
        analysis_dt.strftime("%Y-%m-%d"),
        merged,
        methodology,
        str(comp_path) if comp_path else None,
        scr_meta,
        out_html,
        narrative_map=narrative_map,
    )

    print("CSV:", out_csv)
    print("Markdown:", out_md)
    print("HTML:", out_html)
    print("Rows:", len(merged), "| Comprehensive:", comp_path)


if __name__ == "__main__":
    main()
