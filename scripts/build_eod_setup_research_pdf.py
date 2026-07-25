"""Build an editorial PDF for the EOD setup-effectiveness research.

The report is intentionally different from the raw signal_effectiveness HTML:
it is a compact research note modeled after the ORB/VWAP PDF style, with a
thesis, evidence tables, stability/regime read-through, and limitations.
"""

from __future__ import annotations

import argparse
import html
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
SIGNAL_DIR = ROOT / "reports" / "signal_effectiveness"
RESEARCH_DIR = ROOT / "reports" / "research"
LATEST_DIR = ROOT / "reports" / "latest"


def _stamp_from_path(path: Path) -> str:
    match = re.search(r"signal_events_(\d{8}_\d{6})\.csv$", path.name)
    if not match:
        raise ValueError(f"Cannot infer stamp from {path}")
    return match.group(1)


def _latest_stamp() -> str:
    files = sorted(SIGNAL_DIR.glob("signal_events_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise SystemExit("No signal_events_*.csv file found under reports/signal_effectiveness")
    return _stamp_from_path(files[0])


def _read_csv(path: Path, **kwargs: Any) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"Missing required artifact: {path}")
    return pd.read_csv(path, **kwargs)


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _fmt(value: Any, digits: int = 2, suffix: str = "") -> str:
    try:
        val = float(value)
    except Exception:
        return "-"
    if not math.isfinite(val):
        return "-"
    return f"{val:,.{digits}f}{suffix}"


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(float(value)):,}"
    except Exception:
        return "-"


def _fmt_r(value: Any, digits: int = 3) -> str:
    try:
        val = float(value)
    except Exception:
        return "-"
    if not math.isfinite(val):
        return "-"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.{digits}f}R"


def _fmt_pct(value: Any, digits: int = 1) -> str:
    return _fmt(value, digits, "%")


def _short_setup(value: Any) -> str:
    mapping = {
        "ema20_pullback_reclaim": "EMA20 reclaim",
        "combo_rs_volume_sector": "RS+vol+sector",
        "combo_momentum_quality": "Momentum quality",
        "relative_strength_breakout": "RS breakout",
        "breakout_50_volume": "50d breakout",
        "breakout_20_volume": "20d breakout",
        "combo_risk_filtered_breakout": "Risk-filtered",
        "vcp_breakout_proxy": "VCP proxy",
        "darvas_box_breakout": "Darvas",
        "combo_vcp_volume_sector": "VCP+vol+sector",
        "combo_ema_reclaim_regime": "EMA reclaim+regime",
        "combo_fno_confirmed_breakout": "F&O breakout",
    }
    text = str(value)
    return mapping.get(text, text)


def _html_cell(value: Any) -> str:
    if pd.isna(value):
        return "-"
    return html.escape(str(value))


def _table(headers: list[str], rows: list[list[Any]], *, cls: str = "") -> str:
    thead = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = []
    for row in rows:
        body.append("<tr>" + "".join(f"<td>{_html_cell(v)}</td>" for v in row) + "</tr>")
    return f"<table class='{cls}'><thead><tr>{thead}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _metric_cards(cards: list[tuple[str, str, str]]) -> str:
    out = []
    for label, value, sub in cards:
        out.append(
            "<div class='metric'>"
            f"<div class='metric-label'>{html.escape(label)}</div>"
            f"<div class='metric-value'>{html.escape(value)}</div>"
            f"<div class='metric-sub'>{html.escape(sub)}</div>"
            "</div>"
        )
    return "<div class='metrics'>" + "".join(out) + "</div>"


def _agg(frame: pd.DataFrame) -> pd.Series:
    r = _num(frame["r_multiple"]).dropna()
    hits = _num(frame.get("target_hit", pd.Series(index=frame.index, dtype=float))).reindex(frame.index).fillna(0)
    hits = hits.loc[r.index]
    wins = r[r > 0]
    losses = r[r < 0]
    gross_win = float(wins.sum()) if len(wins) else 0.0
    gross_loss = abs(float(losses.sum())) if len(losses) else 0.0
    profit_factor = gross_win / gross_loss if gross_loss > 0 else (math.inf if gross_win > 0 else math.nan)
    curve = r.cumsum()
    max_drawdown = float((curve - curve.cummax()).min()) if len(curve) else math.nan
    return pd.Series(
        {
            "trades": int(len(r)),
            "target_hit_rate_pct": float((hits == 1).mean() * 100.0) if len(r) else math.nan,
            "positive_r_rate_pct": float((r > 0).mean() * 100.0) if len(r) else math.nan,
            "expectancy_r": float(r.mean()) if len(r) else math.nan,
            "profit_factor": profit_factor,
            "max_drawdown_r": max_drawdown,
        }
    )


def _rolling_stability(events: pd.DataFrame) -> pd.DataFrame:
    dates = np.array(sorted(events["date"].dropna().unique()))
    rows: list[pd.DataFrame] = []
    window = 63
    step = 21
    for start_idx in range(0, max(len(dates) - window + 1, 0), step):
        start = pd.Timestamp(dates[start_idx])
        end = pd.Timestamp(dates[start_idx + window - 1])
        chunk = events[(events["date"] >= start) & (events["date"] <= end)]
        if chunk.empty:
            continue
        grouped = chunk.groupby("setup", dropna=False).apply(_agg, include_groups=False).reset_index()
        grouped["window_start"] = start
        grouped["window_end"] = end
        rows.append(grouped)
    if not rows:
        return pd.DataFrame()
    rolling = pd.concat(rows, ignore_index=True)
    usable = rolling[rolling["trades"] >= 50].copy()
    if usable.empty:
        return pd.DataFrame()
    return (
        usable.groupby("setup")
        .agg(
            windows=("expectancy_r", "count"),
            total_window_trades=("trades", "sum"),
            positive_window_rate_pct=("expectancy_r", lambda s: float((s > 0).mean() * 100.0)),
            avg_window_expectancy_r=("expectancy_r", "mean"),
            worst_window_expectancy_r=("expectancy_r", "min"),
            best_window_expectancy_r=("expectancy_r", "max"),
            avg_profit_factor=("profit_factor", "mean"),
            worst_drawdown_r=("max_drawdown_r", "min"),
        )
        .reset_index()
        .sort_values(["positive_window_rate_pct", "avg_window_expectancy_r"], ascending=[False, False])
    )


def _load_eod(symbols: list[str], dsn: str | None) -> pd.DataFrame:
    if not dsn:
        return pd.DataFrame()
    try:
        import psycopg2
    except Exception:
        return pd.DataFrame()
    try:
        with psycopg2.connect(dsn) as conn:
            return pd.read_sql_query(
                """
                SELECT trade_date AS date, upper(symbol) AS symbol, open, high, low, close, volume
                FROM market.equity_eod
                WHERE series='EQ'
                  AND trade_date >= %s
                  AND trade_date <= %s
                  AND upper(symbol) = ANY(%s)
                  AND open > 0 AND high > 0 AND low > 0 AND close > 0 AND volume > 0
                ORDER BY symbol, trade_date
                """,
                conn,
                params=["2022-06-01", "2026-06-19", symbols],
            )
    except Exception as exc:
        print(f"warning: could not load EOD diagnostics from PostgreSQL: {exc}", file=sys.stderr)
        return pd.DataFrame()


def _add_vol_regimes(events: pd.DataFrame, eod: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if eod.empty:
        events = events.copy()
        events["vol_regime"] = "unknown"
        return events, pd.DataFrame()
    eod = eod.copy()
    eod["date"] = pd.to_datetime(eod["date"])
    for column in ("open", "high", "low", "close", "volume"):
        eod[column] = _num(eod[column])
    eod = eod.dropna(subset=["date", "symbol", "close"]).sort_values(["symbol", "date"])
    grouped = eod.groupby("symbol", group_keys=False)
    eod["ret_pct"] = grouped["close"].pct_change().mul(100)
    eod["ewma_vol_pct"] = grouped["ret_pct"].transform(
        lambda s: np.sqrt((s.pow(2)).ewm(span=20, adjust=False, min_periods=10).mean())
    )
    q = eod.groupby("symbol")["ewma_vol_pct"].quantile([0.33, 0.67]).unstack()
    q.columns = ["vol_q33", "vol_q67"]
    eod = eod.merge(q, on="symbol", how="left")
    eod["vol_regime"] = np.select(
        [eod["ewma_vol_pct"] <= eod["vol_q33"], eod["ewma_vol_pct"] >= eod["vol_q67"]],
        ["low_vol", "high_vol"],
        default="normal_vol",
    )
    merged = events.merge(eod[["date", "symbol", "ewma_vol_pct", "vol_regime"]], on=["date", "symbol"], how="left")
    return merged, eod


def _pcr_regime(row: pd.Series) -> str:
    fno_available = pd.to_numeric(row.get("fno_available"), errors="coerce")
    pcr = pd.to_numeric(row.get("fno_pcr"), errors="coerce")
    if fno_available != 1 or pd.isna(pcr):
        return "no_fno"
    if pcr >= 1.15:
        return "put_heavy"
    if pcr < 0.80:
        return "call_heavy"
    return "balanced"


def _symbol_diagnostics(eod: pd.DataFrame, best: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if eod.empty:
        return pd.DataFrame(), pd.DataFrame()
    frame = eod[eod["date"] >= pd.Timestamp("2023-06-19")].copy()

    def diag(group: pd.DataFrame) -> pd.Series:
        r = group["ret_pct"].dropna()
        if len(r) < 80:
            return pd.Series(
                {
                    "bars": len(group),
                    "drift_pct_per_day": np.nan,
                    "vol_pct": np.nan,
                    "autocorr_1d": np.nan,
                    "vol_clustering_1d": np.nan,
                    "trend_persistence": np.nan,
                }
            )
        return pd.Series(
            {
                "bars": len(group),
                "drift_pct_per_day": float(r.mean()),
                "vol_pct": float(r.std()),
                "autocorr_1d": float(r.autocorr(1)),
                "vol_clustering_1d": float(r.abs().autocorr(1)),
                "trend_persistence": float((np.sign(r) == np.sign(r.shift(1))).mean()),
            }
        )

    out = frame.groupby("symbol").apply(diag, include_groups=False).reset_index()
    best = best.copy()
    for column in ("trades", "expectancy_r", "win_rate_pct"):
        if column in best:
            best[column] = _num(best[column])
    joined = out.merge(best[["symbol", "setup", "trades", "expectancy_r", "win_rate_pct"]], on="symbol", how="left")
    breakout = joined[
        (joined["bars"] >= 500)
        & (joined["drift_pct_per_day"] > 0)
        & (joined["autocorr_1d"] >= 0.03)
        & (joined["trades"] >= 10)
    ].sort_values(["expectancy_r", "drift_pct_per_day"], ascending=[False, False])
    meanrev = joined[(joined["bars"] >= 500) & (joined["autocorr_1d"] <= -0.03)].sort_values(
        ["autocorr_1d", "expectancy_r"], ascending=[True, False]
    )
    return breakout, meanrev


def _chart_bars(frame: pd.DataFrame, *, label_col: str, value_col: str, limit: int = 8) -> str:
    data = frame.head(limit).copy()
    values = _num(data[value_col])
    max_abs = max(float(values.abs().max()), 0.001)
    rows = []
    for _, row in data.iterrows():
        value = float(row[value_col])
        width = max(4, min(100, abs(value) / max_abs * 100))
        cls = "positive" if value >= 0 else "negative"
        rows.append(
            "<div class='bar-row'>"
            f"<div class='bar-label'>{html.escape(str(row[label_col]))}</div>"
            "<div class='bar-track'>"
            f"<div class='bar {cls}' style='width:{width:.1f}%'></div>"
            "</div>"
            f"<div class='bar-value'>{html.escape(_fmt_r(value, 3))}</div>"
            "</div>"
        )
    return "<div class='bar-chart'>" + "".join(rows) + "</div>"


def _build_html(data: dict[str, Any]) -> str:
    setup = data["setup"]
    stability = data["stability"]
    variant = data["variant"]
    vol_setup = data["vol_setup"]
    fno_cross = data["fno_cross"]
    breakout = data["breakout_symbols"]
    meanrev = data["meanrev_symbols"]
    queue = data["queue"]
    stamp = data["stamp"]

    top = setup.iloc[0]
    eod_rows = data.get("eod_rows", 0)
    issue_rows = [
        ["SETUP FAMILY", "TIMEFRAME", "UNIVERSE", "BASIS", "GENERATED", "MODE"],
        [
            "EOD SETUP EFFECTIVENESS",
            "Daily",
            "500 liquid NSE symbols",
            f"{_fmt_int(data['event_count'])} labelled events",
            data["generated"],
            "Research only",
        ],
    ]
    setup_rows = []
    for _, row in setup.head(10).iterrows():
        setup_rows.append(
            [
                row["setup"],
                _fmt_int(row["trades"]),
                _fmt_pct(row["win_rate_pct"], 2),
                _fmt_r(row["expectancy_r"]),
                _fmt_r(row["median_r"]),
                _fmt_r(row["max_drawdown_r"]),
            ]
        )
    stability_rows = []
    for _, row in stability.head(10).iterrows():
        stability_rows.append(
            [
                row["setup"],
                _fmt_int(row["windows"]),
                _fmt_pct(row["positive_window_rate_pct"], 1),
                _fmt_r(row["avg_window_expectancy_r"]),
                _fmt_r(row["worst_window_expectancy_r"]),
                _fmt(row["avg_profit_factor"], 2),
            ]
        )
    variant_rows = []
    for _, row in variant.head(12).iterrows():
        variant_rows.append(
            [
                row["setup"],
                row["entry_variant"],
                _fmt_int(row["trades"]),
                _fmt_pct(row["win_rate_pct"], 2),
                _fmt_r(row["expectancy_r"]),
                _fmt_r(row["max_drawdown_r"]),
            ]
        )
    vol_rows = []
    for _, row in vol_setup.head(12).iterrows():
        vol_rows.append(
            [
                row["setup"],
                row["vol_regime"],
                _fmt_int(row["trades"]),
                _fmt_pct(row["target_hit_rate_pct"], 1),
                _fmt_pct(row["positive_r_rate_pct"], 1),
                _fmt_r(row["expectancy_r"]),
                _fmt(row["profit_factor"], 2),
            ]
        )
    fno_rows = []
    for _, row in fno_cross.head(12).iterrows():
        fno_rows.append(
            [
                row["setup"],
                row["vol_regime"],
                row["pcr_regime"],
                _fmt_int(row["trades"]),
                _fmt_pct(row["target_hit_rate_pct"], 1),
                _fmt_r(row["expectancy_r"]),
                _fmt(row["profit_factor"], 2),
            ]
        )
    breakout_rows = []
    for _, row in breakout.head(10).iterrows():
        breakout_rows.append(
            [
                row["symbol"],
                _short_setup(row["setup"]),
                _fmt_int(row["trades"]),
                _fmt_r(row["expectancy_r"]),
                _fmt_pct(row["win_rate_pct"], 1),
                _fmt(row["drift_pct_per_day"], 3),
                _fmt(row["autocorr_1d"], 3),
            ]
        )
    meanrev_rows = []
    for _, row in meanrev.head(8).iterrows():
        meanrev_rows.append(
            [
                row["symbol"],
                _short_setup(row["setup"]),
                _fmt_int(row["trades"]),
                _fmt_r(row["expectancy_r"]),
                _fmt(row["drift_pct_per_day"], 3),
                _fmt(row["autocorr_1d"], 3),
            ]
        )
    best_queue = queue[queue["action"].astype(str).eq("BEST CANDIDATE")].head(8)
    queue_rows = []
    for _, row in best_queue.iterrows():
        queue_rows.append(
            [
                row["symbol"],
                row.get("sector", "-"),
                _short_setup(row["setup"]),
                _fmt_r(row.get("setup_expectancy_r")),
                _fmt_r(row.get("stock_best_expectancy_r")),
                _fmt(row.get("decision_score"), 1),
            ]
        )

    cards = _metric_cards(
        [
            ("Evidence set", _fmt_int(data["event_count"]), f"{data['symbol_count']} symbols · {data['setup_count']} setups"),
            ("Signal window", f"{data['start_date']} → {data['end_date']}", "10-session outcome horizon"),
            ("Best headline setup", str(top["setup"]), f"{_fmt_r(top['expectancy_r'])} · {_fmt_pct(top['win_rate_pct'], 2)} hit rate"),
            ("EOD rows loaded", _fmt_int(eod_rows), "Used for EWMA volatility and diagnostics"),
        ]
    )

    css = """
@page {
  size: Letter;
  margin: 0.62in 0.56in 0.64in 0.56in;
  @top-left { content: "AGENT ADDA"; color: #263238; font-size: 8.5pt; font-weight: 700; letter-spacing: 0.9pt; }
  @top-right { content: "Quantitative Research · Talk2Stocks"; color: #54626f; font-size: 8pt; }
  @bottom-left { content: "Research only — not investment advice"; color: #54626f; font-size: 8pt; }
  @bottom-right { content: "Page " counter(page); color: #54626f; font-size: 8pt; }
}
html, body { margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
  color: #172027;
  font-size: 9.5pt;
  line-height: 1.42;
}
.cover { page-break-after: always; padding-top: 0.18in; }
.mast { font-size: 11pt; font-weight: 800; letter-spacing: 1.8pt; margin-bottom: 0.38in; }
.mast span { color: #7b8790; font-weight: 600; letter-spacing: 1.2pt; }
h1 {
  font-size: 30pt;
  line-height: 1.02;
  letter-spacing: 0;
  margin: 0 0 0.14in;
  max-width: 6.2in;
}
.subtitle { font-size: 12.2pt; color: #3c4b55; margin: 0 0 0.18in; max-width: 6.65in; }
.lede { font-size: 10.6pt; color: #263238; max-width: 6.75in; margin-bottom: 0.34in; }
h2 {
  font-size: 14pt;
  letter-spacing: 0.4pt;
  margin: 0.16in 0 0.10in;
  text-transform: uppercase;
}
h3 {
  font-size: 11.5pt;
  margin: 0.13in 0 0.06in;
}
.section-num { color: #7b8790; font-weight: 800; letter-spacing: 1pt; }
.pull {
  border-left: 5px solid #172027;
  padding: 0.08in 0 0.08in 0.16in;
  font-size: 15pt;
  line-height: 1.16;
  font-weight: 700;
  margin: 0.18in 0 0.20in;
}
.note { color: #52616b; font-size: 8.8pt; }
.smallcaps { font-size: 8pt; letter-spacing: 1.2pt; font-weight: 800; color: #52616b; text-transform: uppercase; }
table { width: 100%; border-collapse: collapse; margin: 0.08in 0 0.18in; font-size: 8pt; }
th { text-align: left; color: #263238; border-bottom: 1.2px solid #172027; padding: 5px 6px; font-weight: 800; }
td { padding: 5px 6px; border-bottom: 0.55px solid #d8dde2; vertical-align: top; }
tr:nth-child(even) td { background: #f5f7f8; }
.issue th { font-size: 7.2pt; color: #52616b; letter-spacing: 0.7pt; text-transform: uppercase; }
.issue td { font-size: 8.4pt; font-weight: 700; }
.metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.08in; margin: 0.16in 0 0.20in; }
.metric { border-top: 2px solid #172027; padding-top: 0.06in; }
.metric-label { font-size: 7.2pt; color: #69777f; text-transform: uppercase; font-weight: 800; letter-spacing: 0.7pt; }
.metric-value { font-size: 14pt; line-height: 1.2; font-weight: 800; margin-top: 0.03in; }
.metric-sub { font-size: 7.8pt; color: #52616b; }
.bar-chart { margin: 0.12in 0 0.20in; }
.bar-row { display: grid; grid-template-columns: 1.95in 1fr 0.65in; gap: 0.08in; align-items: center; margin-bottom: 0.055in; }
.bar-label { font-size: 8pt; font-weight: 600; }
.bar-track { height: 0.12in; background: #eef1f3; }
.bar { height: 100%; }
.bar.positive { background: #1f6f5b; }
.bar.negative { background: #9d2f2f; }
.bar-value { font-size: 8pt; text-align: right; font-weight: 700; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0.20in; }
.grid2 table { font-size: 7.1pt; table-layout: fixed; }
.grid2 th, .grid2 td { padding: 4px 4px; overflow-wrap: anywhere; }
.pagebreak { page-break-before: always; }
.conclusion { font-size: 12pt; line-height: 1.35; font-weight: 600; }
"""

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>EOD Setup Effectiveness Research</title>
<style>{css}</style>
</head>
<body>
<section class="cover">
  <div class="mast">AGENT ADDA <span>· QUANTITATIVE RESEARCH</span></div>
  <h1>A real edge, but not a broad permission slip.</h1>
  <p class="subtitle">Three-year EOD setup-effectiveness research across the liquid NSE universe.</p>
  <p class="lede">The expanded EOD study confirms positive gross expectancy across several breakout and continuation families, but the result is narrower than the short-window read. The edge concentrates in momentum-quality, relative-strength, and EMA reclaim structures; it weakens in generic VCP/Darvas variants and turns negative when F&amp;O confirmation is treated as a bullish shortcut.</p>
  <div class="smallcaps">Issue basis</div>
  {_table(issue_rows[0], [issue_rows[1]], cls="issue")}
  {cards}
  <p class="note">Source stamp: {html.escape(stamp)}. Costs and slippage are not deducted. This is research evidence, not investment advice.</p>
</section>

<section>
  <h2><span class="section-num">00 ·</span> Charter · Objective &amp; Scope</h2>
  <h3>Why this study exists.</h3>
  <p>The lazy version of the question is whether EOD breakouts work. The disciplined version is narrower: which EOD setup families keep positive expectancy over a three-year signal window, which regimes carry them, and where does the headline number fall apart?</p>
  <p>The study uses deterministic daily OHLCV-derived signals on a fixed liquid universe, then labels each signal against a 10-session target/stop/timeout outcome. The output is not a market call. It is a research map: setups to promote, setups to gate, and contexts to avoid.</p>
  <h3>What we are researching.</h3>
  <p>Signals include 20/50-day breakouts, Darvas-box and VCP proxies, EMA20 pullback reclaim, relative-strength breakout, and explicit combination stacks. The 2R target, ATR-based stop, volume confirmation, ADR filter, and 10-session horizon are held constant so setup comparisons remain interpretable.</p>
  <p>The older backfill provides OHLCV history; NSE turnover and F&amp;O/PCR fields are only fully populated in the newer local windows. That is why the universe is selected from current liquid names and the F&amp;O/PCR layer is treated as an overlay rather than a three-year conclusion.</p>
</section>

<section>
  <h2>The whole report in one chart</h2>
  <div class="pull">Expectancy is positive, but the safest thesis is not “buy every breakout.” It is “promote RS/momentum-quality setups, gate generic breakouts, and do not treat F&amp;O confirmation as bullish evidence yet.”</div>
  {_chart_bars(setup, label_col="setup", value_col="expectancy_r", limit=10)}
  <p class="note">Bars show gross setup expectancy in R. The best rows are small positive edges over large samples, not high-hit-rate systems.</p>
</section>

<section class="pagebreak">
  <h2><span class="section-num">01 ·</span> Headline setup leaderboard</h2>
  {_table(["Setup", "Trades", "Target hit", "Expectancy", "Median", "Max DD"], setup_rows)}
  <p>The headline leader is EMA20 pullback reclaim at +0.152R across 3,862 trades. The more durable research thesis, however, comes from the cluster: combo RS/volume/sector, combo momentum-quality, and relative-strength breakout all sit near the top with larger or complementary samples.</p>
  <p>The negative outlier remains F&amp;O-confirmed breakout. Its -0.270R expectancy argues that the current F&amp;O confirmation logic is not an edge amplifier; it is, at least in this evidence set, a bad bullish filter.</p>
</section>

<section>
  <h2><span class="section-num">02 ·</span> Rolling-window stability</h2>
  {_table(["Setup", "Windows", "Positive windows", "Avg exp.", "Worst exp.", "Avg PF"], stability_rows)}
  <p>Rolling stability changes the read. EMA20 reclaim has the best full-period expectancy but only 65.6% positive windows. Momentum-quality, RS/volume/sector, and relative-strength breakout have lower headline expectancy but stronger positive-window rates.</p>
  <p class="note">Method: 63 trading-day windows stepped by 21 trading days; setup/window buckets require at least 50 trades.</p>
</section>

<section class="pagebreak">
  <h2><span class="section-num">03 ·</span> Execution variants</h2>
  {_table(["Setup", "Entry variant", "Trades", "Target hit", "Expectancy", "Max DD"], variant_rows)}
  <p>Close-entry remains the strongest raw expectancy for the leading setups. Retest-hold entries often reduce drawdown and can preserve expectancy for relative-strength and 50-day breakouts, but next-day confirmation generally sacrifices too much edge.</p>
  <p>The practical rule is not to replace the close trigger blindly. Use retest-hold as a risk-control variant for names with wider gaps or poor liquidity, while keeping close-entry as the primary research benchmark.</p>
</section>

<section>
  <h2><span class="section-num">04 ·</span> Volatility regime read-through</h2>
  {_table(["Setup", "Vol regime", "Trades", "Target hit", "Positive R", "Expectancy", "PF"], vol_rows)}
  <p>Low-vol momentum-quality and RS/volume/sector buckets show the highest expectancy, but with smaller samples. Normal-vol EMA reclaim, normal-vol relative-strength breakout, and high-vol RS/volume/sector are more usable as scalable thesis buckets.</p>
  <p>The useful interpretation: volatility does not kill the edge by itself. The problem is generic breakout exposure without quality filters, especially when F&amp;O/PCR context is adverse.</p>
</section>

<section>
  <h2><span class="section-num">05 ·</span> F&amp;O / PCR cross-walk</h2>
  {_table(["Setup", "Vol regime", "PCR regime", "Trades", "Target hit", "Expectancy", "PF"], fno_rows)}
  <p>The F&amp;O sample is short, but the direction is clear enough to avoid a bad rule. Call-heavy and balanced F&amp;O contexts are negative for several breakout families, including the explicit F&amp;O-confirmed breakout stack.</p>
  <p class="note">This table is not a three-year F&amp;O test. Local F&amp;O EOD coverage begins on 2026-04-21; treat it as an overlay and a warning label.</p>
</section>

<section class="pagebreak">
  <h2><span class="section-num">06 ·</span> Symbol attribution</h2>
  <h3>Breakout-friendly names</h3>
  {_table(["Symbol", "Best setup", "Trades", "Exp.", "Hit", "Drift", "AR(1)"], breakout_rows)}
  <h3>Mean-reversion candidates</h3>
  {_table(["Symbol", "Best setup", "Trades", "Exp.", "Drift", "AR(1)"], meanrev_rows)}
  <p>Breakout-friendly names combine positive drift and positive one-day autocorrelation. Mean-reversion candidates show negative autocorrelation and should not be forced into the same breakout playbook without separate rules.</p>
</section>

<section class="pagebreak">
  <h2><span class="section-num">07 ·</span> Current EOD decision queue</h2>
  {_table(["Symbol", "Sector", "Setup", "Setup exp.", "Stock best exp.", "Score"], queue_rows)}
  <p>The latest queue contains {_fmt_int(len(queue))} rows across {queue["symbol"].nunique()} symbols: {_fmt_int((queue["action"] == "BEST CANDIDATE").sum())} best-candidate rows, {_fmt_int((queue["action"] == "WAIT FOR TRIGGER/RETEST").sum())} wait/retest rows, {_fmt_int((queue["action"] == "WATCH ONLY").sum())} watch-only rows, and {_fmt_int((queue["action"] == "NO TRADE").sum())} no-trade row.</p>
  <p>Historyless current setups such as stage2/supertrend variants are not promoted as best candidates in this run. They should be explicitly demoted or assigned their own historical leaderboard before they become actionable.</p>
</section>

<section>
  <h2><span class="section-num">08 ·</span> Monitoring playbook</h2>
  <p><strong>Promote:</strong> EMA20 reclaim when the name has trend support; momentum-quality and RS/volume/sector when volume and sector participation confirm; relative-strength breakout for scalable breakout exposure.</p>
  <p><strong>Gate:</strong> Plain 20-day/50-day breakouts should require name-level history, regime support, or retest confirmation. VCP and Darvas proxies need stricter confirmation before promotion.</p>
  <p><strong>Reject or redesign:</strong> F&amp;O-confirmed breakout as currently defined. The F&amp;O overlay should become a risk filter first, not a bullish accelerator.</p>
</section>

<section>
  <h2><span class="section-num">09 ·</span> Limits · What this study does not claim</h2>
  <p>This report does not claim executable P&amp;L. Costs, slippage, gap fills, position sizing, portfolio heat, and allocation are not deducted. Newer IPOs naturally contribute shorter histories.</p>
  <p>The backfill supplies older OHLCV but not full historical NSE turnover/delivery. F&amp;O/PCR coverage is materially shorter than the EOD price-history coverage.</p>
  <h2>Research-grade conclusion</h2>
  <p class="conclusion">The three-year EOD evidence supports a controlled long-breakout/reclaim playbook, not a broad breakout mandate. The best thesis is to rank EMA20 reclaim, momentum-quality, and relative-strength setups first; use rolling stability and volatility regime as gates; and treat current F&amp;O confirmation as a negative or unproven overlay until it is rebuilt and retested.</p>
</section>
</body>
</html>
"""


def build_report(stamp: str, *, dsn: str | None, html_path: Path, pdf_path: Path) -> None:
    events = _read_csv(SIGNAL_DIR / f"signal_events_{stamp}.csv", low_memory=False, parse_dates=["date", "exit_date"])
    setup = _read_csv(SIGNAL_DIR / f"setup_leaderboard_{stamp}.csv")
    variant = _read_csv(SIGNAL_DIR / f"execution_variant_leaderboard_{stamp}.csv")
    best = _read_csv(SIGNAL_DIR / f"stock_best_setups_{stamp}.csv")
    queue = _read_csv(SIGNAL_DIR / f"current_decision_queue_{stamp}.csv")

    for frame in (events, setup, variant, best, queue):
        for column in frame.columns:
            if column.endswith("_r") or column.endswith("_pct") or column in {
                "trades",
                "target_hits",
                "target_hit",
                "decision_score",
                "setup_expectancy_r",
                "stock_best_expectancy_r",
                "win_rate_pct",
            }:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")

    symbols = sorted(events["symbol"].dropna().astype(str).str.upper().unique().tolist())
    eod = _load_eod(symbols, dsn)
    events_v, eod_diag = _add_vol_regimes(events, eod)
    stability = _rolling_stability(events)
    vol_setup = (
        events_v.dropna(subset=["vol_regime"])
        .groupby(["setup", "vol_regime"], dropna=False)
        .apply(_agg, include_groups=False)
        .reset_index()
    )
    vol_setup = vol_setup[vol_setup["trades"] >= 100].sort_values(["expectancy_r", "trades"], ascending=[False, False])
    events_v["pcr_regime"] = events_v.apply(_pcr_regime, axis=1)
    fno_cross = (
        events_v[events_v["pcr_regime"] != "no_fno"]
        .groupby(["setup", "vol_regime", "pcr_regime"], dropna=False)
        .apply(_agg, include_groups=False)
        .reset_index()
    )
    fno_cross = fno_cross[fno_cross["trades"] >= 20].sort_values(["expectancy_r", "trades"], ascending=[False, False])
    breakout, meanrev = _symbol_diagnostics(eod_diag, best)

    generated = pd.Timestamp.now().strftime("%Y-%m-%d")
    data = {
        "stamp": stamp,
        "generated": generated,
        "events": events,
        "setup": setup,
        "variant": variant,
        "best": best,
        "queue": queue,
        "stability": stability,
        "vol_setup": vol_setup,
        "fno_cross": fno_cross,
        "breakout_symbols": breakout,
        "meanrev_symbols": meanrev,
        "event_count": len(events),
        "symbol_count": int(events["symbol"].nunique()),
        "setup_count": int(events["setup"].nunique()),
        "start_date": str(pd.to_datetime(events["date"]).min().date()),
        "end_date": str(pd.to_datetime(events["date"]).max().date()),
        "eod_rows": len(eod_diag),
    }
    html_text = _build_html(data)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html_text, encoding="utf-8")
    weasy = shutil.which("weasyprint")
    if not weasy:
        raise SystemExit("weasyprint not found; HTML report was written but PDF cannot be generated")
    subprocess.run([weasy, str(html_path), str(pdf_path)], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build EOD setup-effectiveness editorial research PDF.")
    parser.add_argument("--stamp", default=None, help="Artifact stamp, e.g. 20260621_133904. Defaults to latest events file.")
    parser.add_argument("--dsn", default=os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN"))
    parser.add_argument("--html", default=str(RESEARCH_DIR / "EOD_Setup_Effectiveness_Research_Report.html"))
    parser.add_argument("--pdf", default=str(RESEARCH_DIR / "EOD_Setup_Effectiveness_Research_Report.pdf"))
    args = parser.parse_args()
    stamp = args.stamp or _latest_stamp()
    build_report(stamp, dsn=args.dsn, html_path=Path(args.html), pdf_path=Path(args.pdf))
    latest_pdf = LATEST_DIR / "eod_setup_effectiveness_research.pdf"
    latest_html = LATEST_DIR / "eod_setup_effectiveness_research.html"
    shutil.copy2(args.pdf, latest_pdf)
    shutil.copy2(args.html, latest_html)
    print(f"EOD research PDF complete: {args.pdf}")
    print(f"EOD research HTML complete: {args.html}")
    print(f"Latest PDF: {latest_pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
