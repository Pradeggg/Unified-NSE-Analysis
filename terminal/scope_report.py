"""Generic grounded sector/index report generation."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import math
import os
import re
import shutil
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
MISSING = "-"


def _load_project_env() -> None:
    """Load project .env for standalone script runs."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(env_path, override=False)
        return
    except Exception:
        pass
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        return


_load_project_env()

DEFAULT_PG_DSN = (
    os.environ.get("AGENT_ADDA_PG_DSN")
    or os.environ.get("PG_DSN")
    or "dbname=nse_market user=nse_admin host=/tmp"
)


@dataclass
class ScopeReportOptions:
    scope: str
    name: str
    output_format: str = "html"
    output_dir: Path | None = None
    top_n: int = 20
    with_charts: bool = True
    with_web: bool = False
    with_llm: bool = False
    open_report: bool = False
    pg_dsn: str = DEFAULT_PG_DSN


@dataclass
class ScopeInputData:
    snapshots: pd.DataFrame = field(default_factory=pd.DataFrame)
    index_history: pd.DataFrame = field(default_factory=pd.DataFrame)
    quarterly_results: pd.DataFrame = field(default_factory=pd.DataFrame)
    fundamentals: pd.DataFrame = field(default_factory=pd.DataFrame)
    snapshot_date: str = ""
    eod_date: str = ""


WebSearchFn = Callable[[str, str], dict[str, list[dict[str, Any]]]]
LLMNarrativeFn = Callable[[str], str]


def parse_scope_report_args(args: list[str] | None = None) -> ScopeReportOptions:
    parser = argparse.ArgumentParser(description="Generate a grounded sector/index research report.")
    parser.add_argument("--scope", choices=("sector", "index"), required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--format", dest="output_format", choices=("html", "md", "markdown"), default="html")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--top", dest="top_n", type=int, default=20)
    parser.add_argument("--with-charts", action="store_true", default=False)
    parser.add_argument("--no-charts", action="store_true", default=False)
    parser.add_argument("--with-web", action="store_true", default=False)
    parser.add_argument("--llm", dest="with_llm", action="store_true", default=False)
    parser.add_argument("--open", dest="open_report", action="store_true", default=False)
    ns = parser.parse_args(args)
    output_format = "md" if ns.output_format == "markdown" else ns.output_format
    return ScopeReportOptions(
        scope=ns.scope,
        name=ns.name,
        output_format=output_format,
        output_dir=ns.output_dir,
        top_n=max(1, int(ns.top_n)),
        with_charts=bool(ns.with_charts or not ns.no_charts),
        with_web=bool(ns.with_web),
        with_llm=bool(ns.with_llm),
        open_report=bool(ns.open_report),
    )


def _num(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        out = float(value)
        return None if math.isnan(out) else out
    except Exception:
        return None


def _fmt(value: Any, digits: int = 1, suffix: str = "") -> str:
    number = _num(value)
    if number is None:
        return MISSING
    sign = "+" if suffix == "%" and number > 0 else ""
    return f"{sign}{number:.{digits}f}{suffix}"


def _inr(value: Any) -> str:
    number = _num(value)
    return MISSING if number is None else f"INR {number:,.2f}"


def _median(values: list[Any] | pd.Series) -> float | None:
    vals = sorted(v for v in (_num(v) for v in values) if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell).replace("\n", " ") for cell in row) + " |")
    return "\n".join(lines)


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def _report_subject(options: ScopeReportOptions) -> str:
    label = options.name.strip()
    return f"{label} {'Sector' if options.scope == 'sector' else 'Index'} Research Report"


def _classify(row: dict[str, Any]) -> str:
    stage = str(row.get("stage") or "")
    signal = str(row.get("trading_signal") or "").upper()
    tech = _num(row.get("technical_score")) or 0
    rsi = _num(row.get("rsi"))
    rs = _num(row.get("relative_strength"))
    one_m = _num(row.get("change_1m_pct"))
    fund = _num(row.get("enhanced_fund_score")) or _num(row.get("fundamental_score"))
    if stage == "STAGE_2" and signal == "BUY" and tech >= 60 and (rsi is None or rsi < 82):
        return "Actionable watchlist"
    if stage == "STAGE_2" and tech >= 50 and (rs is None or rs > 0):
        return "Constructive but wait for entry"
    if (rsi is not None and rsi >= 85) or (one_m is not None and one_m >= 20):
        return "Extended; do not chase"
    if signal == "SELL" or tech < 40 or (rs is not None and rs < -10):
        return "Avoid / weak"
    if fund is not None and fund >= 70 and tech >= 45:
        return "Fundamental watchlist"
    return "Neutral"


def _bar_svg(title: str, items: list[tuple[str, float]], *, width: int = 520, height: int = 170) -> str:
    clean = [(str(k), float(v)) for k, v in items if v is not None]
    if not clean:
        return "<div class='empty-chart'>No chart data available.</div>"
    max_val = max(abs(v) for _, v in clean) or 1.0
    pad_l, pad_t, pad_b = 130, 34, 28
    row_h = max(22, int((height - pad_t - pad_b) / max(1, len(clean))))
    svg_h = pad_t + pad_b + row_h * len(clean)
    bars = [
        f"<text x='18' y='22' font-size='13' font-weight='700' fill='#0f172a'>{html.escape(title)}</text>"
    ]
    axis_x = pad_l
    bars.append(f"<line x1='{axis_x}' y1='{pad_t - 8}' x2='{axis_x}' y2='{svg_h - pad_b + 6}' stroke='#cbd5e1'/>")
    for i, (label, value) in enumerate(clean):
        y = pad_t + i * row_h
        bar_w = max(2, int((abs(value) / max_val) * (width - pad_l - 76)))
        color = "#059669" if value >= 0 else "#dc2626"
        bars.append(f"<text x='18' y='{y + 15}' font-size='10' fill='#334155'>{html.escape(label[:20])}</text>")
        bars.append(f"<rect x='{axis_x}' y='{y + 3}' width='{bar_w}' height='14' rx='3' fill='{color}' opacity='.86'/>")
        bars.append(f"<text x='{axis_x + bar_w + 8}' y='{y + 15}' font-size='10' fill='#0f172a'>{value:.1f}</text>")
    return (
        f"<svg class='scope-chart' viewBox='0 0 {width} {svg_h}' role='img' "
        f"aria-label='{html.escape(title)}'>"
        f"<rect width='{width}' height='{svg_h}' rx='8' fill='#ffffff'/>"
        + "".join(bars)
        + "</svg>"
    )


def _donut_svg(title: str, counts: Counter, *, width: int = 520) -> str:
    total = sum(counts.values())
    items = [(k, float(v)) for k, v in counts.items()]
    if total == 0:
        return "<div class='empty-chart'>No chart data available.</div>"
    colors = ["#059669", "#2563eb", "#ca8a04", "#dc2626", "#64748b", "#7c3aed"]
    rows = [f"<text x='18' y='22' font-size='13' font-weight='700' fill='#0f172a'>{html.escape(title)}</text>"]
    x = 20
    for i, (label, count) in enumerate(items):
        pct = count / total * 100
        y = 52 + i * 25
        rows.append(f"<rect x='{x}' y='{y - 12}' width='14' height='14' rx='3' fill='{colors[i % len(colors)]}'/>")
        rows.append(f"<text x='{x + 22}' y='{y}' font-size='10' fill='#0f172a'>{html.escape(str(label))}: {int(count)} ({pct:.1f}%)</text>")
    height = max(105, 55 + 25 * len(items))
    return (
        f"<svg class='scope-chart' viewBox='0 0 {width} {height}' role='img' "
        f"aria-label='{html.escape(title)}'>"
        f"<rect width='{width}' height='{height}' rx='8' fill='#ffffff'/>"
        + "".join(rows)
        + "</svg>"
    )


def _ema(values: list[float], period: int) -> list[float | None]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    out: list[float | None] = []
    ema: float | None = None
    for idx, value in enumerate(values):
        ema = value if ema is None else (value * alpha + ema * (1 - alpha))
        out.append(ema if idx + 1 >= period else None)
    return out


def _line_svg(title: str, rows: list[dict[str, Any]], *, width: int = 520, height: int = 170) -> str:
    points: list[tuple[str, float]] = []
    for row in rows:
        close = _num(row.get("close"))
        if close is not None:
            points.append((str(row.get("trade_date") or ""), close))
    points = points[-60:]
    if len(points) < 2:
        return "<div class='empty-chart'>No index chart data available.</div>"

    values = [value for _, value in points]
    min_v, max_v = min(values), max(values)
    span = max(max_v - min_v, 1.0)
    pad_l, pad_r, pad_t, pad_b = 52, 22, 38, 28
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    coords: list[tuple[float, float]] = []
    for idx, (_, value) in enumerate(points):
        x = pad_l + (idx / (len(points) - 1)) * plot_w
        y = pad_t + (1 - ((value - min_v) / span)) * plot_h
        coords.append((x, y))

    first, last = values[0], values[-1]
    change = ((last / first) - 1) * 100 if first else 0
    color = "#059669" if change >= 0 else "#dc2626"
    path_d = " ".join(("M" if i == 0 else "L") + f"{x:.1f},{y:.1f}" for i, (x, y) in enumerate(coords))
    labels = [
        f"<text x='18' y='22' font-size='13' font-weight='700' fill='#0f172a'>{html.escape(title)}</text>",
        f"<text x='{width - 118}' y='22' font-size='10' fill='{color}'>Return {change:+.1f}%</text>",
        f"<line x1='{pad_l}' y1='{pad_t}' x2='{pad_l}' y2='{pad_t + plot_h}' stroke='#cbd5e1'/>",
        f"<line x1='{pad_l}' y1='{pad_t + plot_h}' x2='{pad_l + plot_w}' y2='{pad_t + plot_h}' stroke='#cbd5e1'/>",
        f"<text x='12' y='{pad_t + 4}' font-size='9' fill='#64748b'>{max_v:.0f}</text>",
        f"<text x='12' y='{pad_t + plot_h}' font-size='9' fill='#64748b'>{min_v:.0f}</text>",
        f"<text x='{pad_l}' y='{height - 10}' font-size='9' fill='#64748b'>{html.escape(points[0][0][-10:])}</text>",
        f"<text x='{width - 92}' y='{height - 10}' font-size='9' fill='#64748b'>{html.escape(points[-1][0][-10:])}</text>",
    ]
    return (
        f"<svg class='scope-chart' viewBox='0 0 {width} {height}' role='img' "
        f"aria-label='{html.escape(title)}'>"
        f"<rect width='{width}' height='{height}' rx='8' fill='#ffffff'/>"
        + "".join(labels)
        + f"<path d='{path_d}' fill='none' stroke='{color}' stroke-width='3'/>"
        + f"<circle cx='{coords[-1][0]:.1f}' cy='{coords[-1][1]:.1f}' r='4' fill='{color}'/>"
        + "</svg>"
    )


def _candlestick_ema_svg(title: str, rows: list[dict[str, Any]], *, width: int = 720, height: int = 260) -> str:
    data = [row for row in rows[-80:] if _num(row.get("close")) is not None]
    if len(data) < 5:
        return "<div class='empty-chart'>No index candlestick data available.</div>"
    closes = [_num(row.get("close")) or 0 for row in data]
    highs = [_num(row.get("high")) or max(_num(row.get("open")) or closes[i], closes[i]) for i, row in enumerate(data)]
    lows = [_num(row.get("low")) or min(_num(row.get("open")) or closes[i], closes[i]) for i, row in enumerate(data)]
    opens: list[float] = []
    for i, row in enumerate(data):
        open_v = _num(row.get("open"))
        opens.append(open_v if open_v is not None else (closes[i - 1] if i else closes[i]))
    min_v, max_v = min(lows), max(highs)
    span = max(max_v - min_v, 1.0)
    pad_l, pad_r, pad_t, pad_b = 58, 18, 38, 28
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    def y(value: float) -> float:
        return pad_t + (1 - ((value - min_v) / span)) * plot_h

    step = plot_w / max(1, len(data) - 1)
    body_w = max(2.0, min(7.0, step * 0.55))
    bits = [
        f"<text x='18' y='22' font-size='13' font-weight='700' fill='#0f172a'>{html.escape(title)}</text>",
        f"<line x1='{pad_l}' y1='{pad_t}' x2='{pad_l}' y2='{pad_t + plot_h}' stroke='#cbd5e1'/>",
        f"<line x1='{pad_l}' y1='{pad_t + plot_h}' x2='{pad_l + plot_w}' y2='{pad_t + plot_h}' stroke='#cbd5e1'/>",
        f"<text x='12' y='{pad_t + 4}' font-size='9' fill='#64748b'>{max_v:.0f}</text>",
        f"<text x='12' y='{pad_t + plot_h}' font-size='9' fill='#64748b'>{min_v:.0f}</text>",
    ]
    for i, close in enumerate(closes):
        x = pad_l + i * step
        color = "#059669" if close >= opens[i] else "#dc2626"
        bits.append(f"<line x1='{x:.1f}' y1='{y(highs[i]):.1f}' x2='{x:.1f}' y2='{y(lows[i]):.1f}' stroke='{color}' stroke-width='1.2'/>")
        top = min(y(opens[i]), y(close))
        body_h = max(1.5, abs(y(opens[i]) - y(close)))
        bits.append(f"<rect x='{x - body_w/2:.1f}' y='{top:.1f}' width='{body_w:.1f}' height='{body_h:.1f}' fill='{color}' rx='1'/>")
    for period, color in ((20, "#2563eb"), (50, "#ca8a04"), (200, "#64748b")):
        ema = _ema(closes, period)
        coords = [(pad_l + i * step, y(value)) for i, value in enumerate(ema) if value is not None]
        if len(coords) >= 2:
            d = " ".join(("M" if i == 0 else "L") + f"{x:.1f},{yy:.1f}" for i, (x, yy) in enumerate(coords))
            bits.append(f"<path d='{d}' fill='none' stroke='{color}' stroke-width='2' opacity='.9'/>")
            bits.append(f"<text x='{width - 82}' y='{22 + (period in (50,))*12 + (period == 200)*24}' font-size='9' fill='{color}'>EMA{period}</text>")
    return (
        f"<svg class='scope-chart scope-chart-wide' viewBox='0 0 {width} {height}' role='img' aria-label='{html.escape(title)}'>"
        f"<rect width='{width}' height='{height}' rx='8' fill='#ffffff'/>"
        + "".join(bits)
        + "</svg>"
    )


def _volume_svg(title: str, rows: list[dict[str, Any]], *, width: int = 520, height: int = 160) -> str:
    vals = [(_num(row.get("volume")) or 0) for row in rows[-60:]]
    if not vals or max(vals) <= 0:
        return f"<div class='empty-chart empty-chart-wide'><strong>{html.escape(title)}</strong><br>Volume distribution unavailable for this index.</div>"
    max_v = max(vals)
    pad_l, pad_t, pad_b = 34, 34, 24
    plot_w = width - pad_l - 16
    plot_h = height - pad_t - pad_b
    step = plot_w / len(vals)
    bits = [f"<text x='18' y='22' font-size='13' font-weight='700' fill='#0f172a'>{html.escape(title)}</text>"]
    for i, value in enumerate(vals):
        h = max(1, value / max_v * plot_h)
        x = pad_l + i * step
        bits.append(f"<rect x='{x:.1f}' y='{pad_t + plot_h - h:.1f}' width='{max(1, step * .7):.1f}' height='{h:.1f}' fill='#2563eb' opacity='.72'/>")
    return f"<svg class='scope-chart' viewBox='0 0 {width} {height}' role='img' aria-label='{html.escape(title)}'><rect width='{width}' height='{height}' rx='8' fill='#ffffff'/>" + "".join(bits) + "</svg>"


def _rsi_distribution_svg(rows: list[dict[str, Any]]) -> str:
    bins = Counter()
    for row in rows:
        rsi = _num(row.get("rsi"))
        if rsi is None:
            continue
        label = "<45 weak" if rsi < 45 else "45-60 neutral" if rsi < 60 else "60-75 strong" if rsi < 75 else ">=75 hot"
        bins[label] += 1
    return _donut_svg("RSI Distribution", bins)


def _sector_index_alias(name: str) -> str | None:
    normalized = _normalize_name(name)
    aliases = {
        "pharma healthcare": "NIFTY PHARMA",
        "healthcare": "NIFTY HEALTHCARE INDEX",
        "it technology": "NIFTY IT",
        "information technology": "NIFTY IT",
        "auto": "NIFTY AUTO",
        "automobile": "NIFTY AUTO",
        "fmcg": "NIFTY FMCG",
        "financial services": "NIFTY FINANCIAL SERVICES",
        "banking financial services": "NIFTY FINANCIAL SERVICES",
        "metals mining": "NIFTY METAL",
        "real estate": "NIFTY REALTY",
        "oil gas": "NIFTY OIL & GAS",
        "energy": "NIFTY ENERGY",
        "consumer durables": "NIFTY CONSUMER DURABLES",
        "capital goods industrials": "NIFTY INDIA MANUFACTURING",
        "chemicals specialty": "NIFTY COMMODITIES",
    }
    for key, value in aliases.items():
        if key in normalized or normalized in key:
            return value
    return None


def _index_sector_filters(name: str) -> list[str]:
    normalized = _normalize_name(name)
    mappings = {
        "nifty it": ["IT & Technology"],
        "nifty bank": ["Banking - Private", "Banking - PSU"],
        "nifty pvt bank": ["Banking - Private"],
        "nifty psu bank": ["Banking - PSU"],
        "nifty auto": ["EV & Auto Ancillaries"],
        "nifty pharma": ["Pharma & Healthcare"],
        "nifty healthcare": ["Pharma & Healthcare"],
        "nifty fmcg": ["FMCG & Consumer Goods"],
        "nifty metal": ["Metals & Mining"],
        "nifty metals": ["Metals & Mining"],
        "nifty realty": ["Realty"],
        "nifty energy": ["Energy - Oil & Gas", "Energy - Power"],
        "nifty oil and gas": ["Energy - Oil & Gas"],
        "nifty capital mkt": ["Capital Markets"],
        "nifty chemicals": ["Chemicals & Specialty"],
        "nifty infra": ["Infrastructure"],
        "nifty ind defence": ["Defence & Aerospace"],
        "nifty railwayspsu": ["Railways & PSU Infra"],
    }
    for key, sectors in mappings.items():
        if key == normalized or key in normalized:
            return sectors
    return []


def _build_web_research(subject: str, scope: str) -> dict[str, list[dict[str, Any]]]:
    try:
        from terminal.web_research import _ddg_search
    except Exception:
        return {"broker_research": [], "credit_ratings": [], "news": []}
    base = f"{subject} {scope} India"
    queries = {
        "broker_research": [
            f"{base} broker research report Motilal Oswal ICICI Securities HDFC Securities Kotak Nuvama",
            f"{base} sector report brokerage target outlook pdf",
        ],
        "credit_ratings": [
            f"{base} credit rating outlook CRISIL ICRA CARE India Ratings",
            f"{base} debt credit outlook rating report",
        ],
        "news": [
            f"{base} latest news outlook earnings catalysts",
        ],
    }
    out: dict[str, list[dict[str, Any]]] = {key: [] for key in queries}
    seen: set[str] = set()
    for bucket, bucket_queries in queries.items():
        for query in bucket_queries:
            for hit in _ddg_search(query, max_results=5):
                url = hit.get("url") or ""
                if not url or url in seen:
                    continue
                seen.add(url)
                out[bucket].append(
                    {
                        "source": _domain(url),
                        "title": hit.get("title") or url,
                        "url": url,
                        "take": hit.get("snippet") or "Source found; open link for full context.",
                    }
                )
    return out


def _domain(url: str) -> str:
    m = re.search(r"https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1) if m else "source"


def _build_llm_narrative(prompt: str) -> str:
    _load_project_env()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "LLM narrative unavailable: OPENAI_API_KEY is not set. Deterministic analysis is shown in the report."
    try:
        from openai import OpenAI

        model = os.environ.get("SCOPE_REPORT_LLM_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4o"
        client = OpenAI(api_key=api_key, timeout=90.0)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an institutional Indian equity research analyst. "
                        "Use only the supplied evidence. Flag missing evidence. "
                        "Do not make investment advice or unsupported broker/credit claims."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        return f"LLM narrative unavailable: {type(exc).__name__}: {exc}"


def _scope_rows(options: ScopeReportOptions, data: ScopeInputData) -> pd.DataFrame:
    df = data.snapshots.copy()
    if df.empty or "sector" not in df.columns:
        return df
    if options.scope == "index":
        sectors = _index_sector_filters(options.name)
        if not sectors:
            return df.iloc[0:0].copy()
        wanted_sectors = {_normalize_name(sector) for sector in sectors}
        return df.loc[df["sector"].astype(str).map(_normalize_name).isin(wanted_sectors)].copy()
    if options.scope != "sector":
        return df.iloc[0:0].copy()
    wanted = _normalize_name(options.name)
    sector_names = df["sector"].astype(str)
    mask = sector_names.map(_normalize_name).eq(wanted)
    if not mask.any():
        mask = sector_names.str.contains(re.escape(options.name), case=False, na=False)
    return df.loc[mask].copy()


def _index_rows(options: ScopeReportOptions, data: ScopeInputData) -> pd.DataFrame:
    df = data.index_history.copy()
    if df.empty or "index_symbol" not in df.columns:
        return df
    subject = _sector_index_alias(options.name) if options.scope == "sector" else None
    wanted = _normalize_name(subject or options.name)
    mask = df["index_symbol"].astype(str).map(_normalize_name).eq(wanted)
    if not mask.any():
        mask = df["index_symbol"].astype(str).str.contains(re.escape(subject or options.name), case=False, na=False)
    return df.loc[mask].copy()


def build_scope_report_markdown(
    options: ScopeReportOptions,
    input_data: ScopeInputData,
    *,
    web_search_fn: WebSearchFn | None = None,
    llm_narrative_fn: LLMNarrativeFn | None = None,
) -> str:
    rows_df = _scope_rows(options, input_data)
    idx_df = _index_rows(options, input_data)
    rows = rows_df.to_dict("records")
    for row in rows:
        row["bucket"] = _classify(row)

    n = len(rows)
    stages = Counter(str(row.get("stage") or "UNKNOWN") for row in rows)
    signals = Counter(str(row.get("trading_signal") or "UNKNOWN").upper() for row in rows)
    stage2 = stages.get("STAGE_2", 0)
    buys = signals.get("BUY", 0)
    pos_rs = sum(1 for row in rows if (_num(row.get("relative_strength")) or -999) > 0)
    overheated = [row for row in rows if (_num(row.get("rsi")) or 0) >= 75]
    med_1w = _median([row.get("change_1w_pct") for row in rows])
    med_1m = _median([row.get("change_1m_pct") for row in rows])
    breadth_score = stage2 / n * 100 if n else 0
    signal_score = buys / n * 100 if n else 0
    rs_score = pos_rs / n * 100 if n else 0
    rotation_score = max(0, min(100, 50 + (med_1m or 0) * 3))
    setup_score = breadth_score * 0.30 + signal_score * 0.25 + rs_score * 0.20 + rotation_score * 0.25
    setup_score -= (len(overheated) / n * 100 * 0.35) if n else 0
    stance = (
        "Constructive / selective watchlist"
        if setup_score >= 55
        else "Neutral / watchlist only"
        if setup_score >= 40
        else "Cautious / avoid broad exposure"
    )

    web = web_search_fn(options.name, options.scope) if options.with_web and web_search_fn else {}
    if options.with_web and web_search_fn is None:
        web = _build_web_research(options.name, options.scope)
    web = {"broker_research": [], "credit_ratings": [], "news": [], **(web or {})}

    llm_narrative = ""
    if options.with_llm:
        llm_prompt = _llm_prompt(options, rows, input_data, stance, setup_score, web)
        llm_narrative = (llm_narrative_fn or _build_llm_narrative)(llm_prompt)

    top = max(1, int(options.top_n))
    leaders = sorted(rows, key=lambda r: (_num(r.get("technical_score")) or 0, _num(r.get("investment_score")) or 0), reverse=True)[:top]
    rs_leaders = sorted(rows, key=lambda r: _num(r.get("relative_strength")) or -999, reverse=True)[:top]
    action = [row for row in rows if row["bucket"] == "Actionable watchlist"][:top]
    weak = [row for row in rows if row["bucket"] == "Avoid / weak"][:top]
    latest_q = _latest_by_symbol(input_data.quarterly_results, "period_label")
    fundamentals = _latest_by_symbol(input_data.fundamentals, "symbol")

    idx_chart_rows = idx_df.sort_values("trade_date").to_dict("records") if not idx_df.empty else []
    idx_rows = list(reversed(idx_chart_rows[-10:]))
    index_name = (
        idx_chart_rows[-1].get("index_symbol")
        if idx_chart_rows
        else _sector_index_alias(options.name) or options.name
    )
    idx_values = [_num(row.get("close")) for row in idx_chart_rows[-60:]]
    idx_values = [value for value in idx_values if value is not None]
    index_return = ((idx_values[-1] / idx_values[0]) - 1) * 100 if len(idx_values) >= 2 and idx_values[0] else None
    executive_summary = (
        llm_narrative
        if llm_narrative
        else (
            f"{options.name} is currently a {stance.lower()} based on the latest cached snapshot. "
            f"The setup score is {setup_score:.1f}/100, with {stage2}/{n} names in Stage 2, "
            f"{buys}/{n} BUY signals, {pos_rs}/{n} stocks showing positive relative strength, "
            f"and {len(overheated)} RSI-stretched names."
        )
    )
    summary_cards = [
        ("Stance", stance, "Evidence-gated view from breadth, signal, RS and rotation."),
        ("Setup Score", f"{setup_score:.1f}/100", "Composite of trend breadth, BUY breadth, RS and 1M rotation."),
        ("Stage 2 Breadth", f"{stage2}/{n}", "Number of matched stocks in Stage 2 trend structure."),
        ("BUY Breadth", f"{buys}/{n}", "Trading-signal breadth from the score snapshot."),
        ("Positive RS", f"{pos_rs}/{n}", "Stocks with relative strength above zero."),
        ("RSI Stretched", str(len(overheated)), "Names with RSI at or above 75; chase-risk bucket."),
        ("Index 60D", _fmt(index_return, 1, "%"), f"Benchmark: {index_name or MISSING}."),
        ("Actionable", str(len(action)), "Names passing the stricter actionability filter."),
    ]
    title = f"# {_report_subject(options)}"
    parts = [
        title,
        "",
        "## Executive Summary",
        executive_summary,
        "",
        "## Summary Cards",
        _summary_cards_html(summary_cards),
        "",
        "## Executive Verdict",
        f"**Stance: {stance}.** Setup score: **{setup_score:.1f}/100**.",
        (
            f"Stage 2 breadth: **{stage2}/{n}**; BUY signal breadth: **{buys}/{n}**; "
            f"positive RS breadth: **{pos_rs}/{n}**; median 1W/1M moves: "
            f"**{_fmt(med_1w, 1, '%')} / {_fmt(med_1m, 1, '%')}**."
        ),
        "",
    ]

    if options.with_charts:
        index_title = f"Index Trend - {index_name}" if idx_chart_rows else ""
        supertrend = Counter(str(row.get("supertrend_state") or row.get("supertrend") or "UNKNOWN") for row in rows)
        parts.extend(
            [
                "## Technical Dashboard",
                "### Benchmark Trend",
                _candlestick_ema_svg(f"Index Candlestick + EMA - {index_name}", idx_chart_rows)
                if idx_chart_rows
                else "_No index candlestick data available._",
                _line_svg(index_title, idx_chart_rows) if idx_chart_rows else "_No index trend chart data available._",
                _volume_svg("Volume Distribution", idx_chart_rows),
                "### Breadth And Participation",
                _donut_svg("Stage Distribution", stages),
                _donut_svg("Trading Signal Breadth", signals),
                _donut_svg("Supertrend Breadth", supertrend),
                _rsi_distribution_svg(rows),
                "### Leadership And Rotation",
                _bar_svg(
                    "Top Relative Strength Leaders",
                    [(row.get("symbol", ""), _num(row.get("relative_strength")) or 0) for row in rs_leaders[:10]],
                ),
                _bar_svg(
                    "One-Month Return Leaders",
                    [(row.get("symbol", ""), _num(row.get("change_1m_pct")) or 0) for row in leaders[:10]],
                ),
                "",
            ]
        )

    parts.extend(
        [
            "## Grounded Scorecard",
            _table(
                ["Metric", "Value", "Read"],
                [
                    ["Universe", n, "Rows matched from score snapshot"],
                    ["Setup score", f"{setup_score:.1f}/100", "Breadth, signal, RS, rotation and overheat penalty"],
                    ["Stage 2 breadth", f"{stage2}/{n}", "Trend breadth"],
                    ["BUY signal breadth", f"{buys}/{n}", "Signal breadth"],
                    ["Positive RS breadth", f"{pos_rs}/{n}", "Relative-strength breadth"],
                    ["Overheated RSI >=75", len(overheated), "Chase-risk count"],
                ],
            ),
            "",
            "## Index / Benchmark Context",
            _table(
                ["Date", "Index", "Close", "1D %", "Tech", "RSI", "Signal"],
                [
                    [
                        row.get("trade_date") or MISSING,
                        row.get("index_symbol") or MISSING,
                        _fmt(row.get("close"), 2),
                        _fmt(row.get("change_pct"), 2, "%"),
                        _fmt(row.get("technical_score"), 1),
                        _fmt(row.get("rsi"), 1),
                        row.get("trading_signal") or "No signal",
                    ]
                    for row in idx_rows
                ],
            ),
            "",
            "## Actionable Watchlist",
            _stock_table(action),
            "",
            "## Technical Leaders",
            _stock_table(leaders),
            "",
            "## Relative Strength Leaders",
            _stock_table(rs_leaders),
            "",
            "## Avoid / Weak Setup",
            _stock_table(weak),
            "",
            "## Fundamental And Quality Lens",
            _fundamental_table(leaders, latest_q, fundamentals),
            "",
            "## Credit And Balance Sheet Risk Lens",
            _credit_table(leaders, fundamentals, web.get("credit_ratings") or []),
            "",
            "## Broker And Research Report Scan",
            _source_table(web.get("broker_research") or []),
            "",
            "## Broader News And Website Research",
            _source_table(web.get("news") or []),
            "",
            "## Action Checklist",
            "- Validate live price and liquidity before any trade.",
            "- Prefer candidates where Stage 2, BUY signal, relative strength and fundamentals agree.",
            "- Avoid chasing RSI-stretched names without a clean retest or consolidation.",
            "- Recheck broker and credit sources before using them in a formal investment memo.",
            "",
            "## Evidence Gaps",
            _evidence_gap_text(options, n, idx_rows, web),
            "",
            "## Source Trail",
            _table(
                ["Source", "Freshness", "Coverage", "Used For"],
                [
                    ["scores.stage_snapshots", input_data.snapshot_date or MISSING, f"{n} matched stocks", "Universe, stages, signals, RS"],
                    ["market.index_eod", input_data.eod_date or MISSING, f"{len(idx_rows)} index rows shown", "Benchmark/index trend context"],
                    ["scores.quarterly_results", "latest cached", f"{len(latest_q)} matched symbols", "Revenue, margins, PAT, EPS"],
                    ["scores.fundamentals", "latest cached", f"{len(fundamentals)} matched symbols", "Credit/quality risk lens"],
                    ["web research", "runtime search" if options.with_web else "disabled", _web_count(web), "Broker, credit and news context"],
                    ["LLM narrative", "runtime synthesis" if options.with_llm else "disabled", "grounded prompt only", "Interpretive narrative"],
                ],
            ),
            "",
            "## Disclaimer",
            "This report is for research and learning only. It is not investment advice or a buy/sell recommendation.",
        ]
    )
    return "\n".join(parts)


def _latest_by_symbol(frame: pd.DataFrame, marker_col: str) -> dict[str, dict[str, Any]]:
    if frame is None or frame.empty or "symbol" not in frame.columns:
        return {}
    result: dict[str, dict[str, Any]] = {}
    for row in frame.to_dict("records"):
        result.setdefault(str(row.get("symbol")), row)
    return result


def _stock_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "_No matched rows for this section._"
    return _table(
        ["Symbol", "Price", "1W", "1M", "Stage", "Signal", "Tech", "RS", "RSI", "Read"],
        [
            [
                row.get("symbol") or MISSING,
                _inr(row.get("price")),
                _fmt(row.get("change_1w_pct"), 1, "%"),
                _fmt(row.get("change_1m_pct"), 1, "%"),
                row.get("stage") or "No stage",
                row.get("trading_signal") or "No signal",
                _fmt(row.get("technical_score"), 1),
                _fmt(row.get("relative_strength"), 1),
                _fmt(row.get("rsi"), 1),
                row.get("bucket") or _classify(row),
            ]
            for row in rows
        ],
    )


def _fundamental_table(
    rows: list[dict[str, Any]],
    latest_q: dict[str, dict[str, Any]],
    fundamentals: dict[str, dict[str, Any]],
) -> str:
    if not rows:
        return "_No stock rows available for fundamental lens._"
    return _table(
        ["Symbol", "Fund Score", "Latest Qtr", "Revenue", "OPM %", "PAT", "EPS", "Forensic"],
        [
            [
                row.get("symbol") or MISSING,
                _fmt(row.get("enhanced_fund_score") or row.get("fundamental_score"), 1),
                (latest_q.get(row.get("symbol")) or {}).get("period_label", "Not captured"),
                _fmt((latest_q.get(row.get("symbol")) or {}).get("revenue"), 1),
                _fmt((latest_q.get(row.get("symbol")) or {}).get("opm_pct"), 1, "%"),
                _fmt((latest_q.get(row.get("symbol")) or {}).get("pat"), 1),
                _fmt((latest_q.get(row.get("symbol")) or {}).get("eps"), 2),
                (fundamentals.get(row.get("symbol")) or {}).get("forensic_risk", "Not captured"),
            ]
            for row in rows
        ],
    )


def _credit_table(
    rows: list[dict[str, Any]],
    fundamentals: dict[str, dict[str, Any]],
    credit_sources: list[dict[str, Any]],
) -> str:
    table = _table(
        ["Symbol", "Forensic", "ROE", "ROCE", "Debt/Equity", "Altman Z", "Beneish M", "Piotroski"],
        [
            [
                row.get("symbol") or MISSING,
                (fundamentals.get(row.get("symbol")) or {}).get("forensic_risk", "Not captured"),
                _fmt((fundamentals.get(row.get("symbol")) or {}).get("roe"), 1, "%"),
                _fmt((fundamentals.get(row.get("symbol")) or {}).get("roce"), 1, "%"),
                _fmt((fundamentals.get(row.get("symbol")) or {}).get("debt_to_equity"), 2),
                _fmt((fundamentals.get(row.get("symbol")) or {}).get("altman_z_score"), 2),
                _fmt((fundamentals.get(row.get("symbol")) or {}).get("beneish_m_score"), 2),
                _fmt((fundamentals.get(row.get("symbol")) or {}).get("piotroski_score"), 0),
            ]
            for row in rows[:12]
        ],
    )
    if credit_sources:
        table += "\n\n### External Credit / Rating Source Trail\n" + _source_table(credit_sources)
    return table


def _source_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "_No accessible sources found or web research disabled._"
    return _table(
        ["Source", "Title", "Take", "URL"],
        [
            [
                row.get("source") or _domain(row.get("url", "")),
                row.get("title") or "Untitled",
                row.get("take") or row.get("snippet") or "Open source for details.",
                row.get("url") or "",
            ]
            for row in rows[:12]
        ],
    )


def _summary_cards_html(cards: list[tuple[str, str, str]]) -> str:
    bits = ["<section class='scope-card-grid'>"]
    for label, value, note in cards:
        bits.append(
            "<article class='scope-card'>"
            f"<div class='scope-card-label'>{html.escape(label)}</div>"
            f"<div class='scope-card-value'>{html.escape(value)}</div>"
            f"<div class='scope-card-note'>{html.escape(note)}</div>"
            "</article>"
        )
    bits.append("</section>")
    return "".join(bits)


def _web_count(web: dict[str, list[dict[str, Any]]]) -> str:
    return f"{sum(len(v or []) for v in web.values())} links"


def _evidence_gap_text(options: ScopeReportOptions, n: int, idx_rows: list[dict[str, Any]], web: dict[str, Any]) -> str:
    gaps = []
    if options.scope == "index" and n == 0:
        gaps.append("Index constituent mapping is not available in this report run, so stock-level buckets are omitted.")
    if not idx_rows:
        gaps.append("Index EOD history was unavailable for the requested subject.")
    if options.with_web and _web_count(web) == "0 links":
        gaps.append("Web research did not return accessible broker, credit or news sources.")
    if not options.with_web:
        gaps.append("Web research was disabled for this run.")
    if not options.with_llm:
        gaps.append("LLM narrative was disabled for this run.")
    return "\n".join(f"- {gap}" for gap in gaps) if gaps else "- No critical evidence gaps detected in the configured scope."


def _llm_prompt(
    options: ScopeReportOptions,
    rows: list[dict[str, Any]],
    data: ScopeInputData,
    stance: str,
    setup_score: float,
    web: dict[str, list[dict[str, Any]]],
) -> str:
    leaders = rows[:12]
    payload = {
        "scope": options.scope,
        "name": options.name,
        "snapshot_date": data.snapshot_date,
        "eod_date": data.eod_date,
        "stance": stance,
        "setup_score": round(setup_score, 1),
        "leaders": leaders,
        "web_sources": web,
    }
    return (
        "Write a concise institutional-style narrative with sections: sector/index take, "
        "bull case, bear case, credit/risk take, and what would change the view. "
        "Use only this evidence and name missing evidence explicitly:\n"
        f"{payload}"
    )


def load_scope_input_data(options: ScopeReportOptions) -> ScopeInputData:
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except Exception:
        return ScopeInputData()
    try:
        conn = psycopg2.connect(options.pg_dsn)
    except Exception:
        return ScopeInputData()
    try:
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT MAX(snapshot_date)::text AS d FROM scores.stage_snapshots")
            snapshot_date = (cur.fetchone() or {}).get("d") or ""
            cur.execute("SELECT MAX(trade_date)::text AS d FROM market.equity_eod")
            eod_date = (cur.fetchone() or {}).get("d") or ""
            cur.execute(
                """
                SELECT *
                FROM scores.stage_snapshots
                WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM scores.stage_snapshots)
                """
            )
            snapshots = pd.DataFrame(cur.fetchall())
            cur.execute(
                """
                SELECT *
                FROM market.index_eod
                WHERE trade_date >= (
                    SELECT MAX(trade_date) FROM market.index_eod
                ) - INTERVAL '120 days'
                ORDER BY index_symbol, trade_date
                """
            )
            index_history = pd.DataFrame(cur.fetchall())
            symbols = snapshots.get("symbol", pd.Series(dtype=str)).dropna().astype(str).unique().tolist()
            quarterly = pd.DataFrame()
            fundamentals = pd.DataFrame()
            if symbols:
                cur.execute(
                    """
                    SELECT symbol, period_label, period_end::text, revenue, opm_pct, pat, eps
                    FROM scores.quarterly_results
                    WHERE symbol = ANY(%s)
                    ORDER BY symbol, period_end DESC
                    """,
                    (symbols,),
                )
                quarterly = pd.DataFrame(cur.fetchall())
                cur.execute("SELECT * FROM scores.fundamentals WHERE symbol = ANY(%s)", (symbols,))
                fundamentals = pd.DataFrame(cur.fetchall())
        return ScopeInputData(
            snapshots=snapshots,
            index_history=index_history,
            quarterly_results=quarterly,
            fundamentals=fundamentals,
            snapshot_date=snapshot_date,
            eod_date=eod_date,
        )
    finally:
        conn.close()


def generate_scope_report(
    *,
    options: ScopeReportOptions,
    input_data: ScopeInputData | None = None,
    web_search_fn: WebSearchFn | None = None,
    llm_narrative_fn: LLMNarrativeFn | None = None,
) -> dict[str, Any]:
    from terminal import reports as report_module

    data = input_data or load_scope_input_data(options)
    markdown = build_scope_report_markdown(
        options,
        data,
        web_search_fn=web_search_fn,
        llm_narrative_fn=llm_narrative_fn,
    )
    digest = hashlib.sha1(markdown.encode("utf-8")).hexdigest()[:8]
    safe_name = re.sub(r"[^A-Za-z0-9_]+", "_", options.name).strip("_").lower() or "scope"
    filename = f"{safe_name}_{options.scope}_research_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}_{digest}"
    title = _report_subject(options)

    original_dir = report_module.REPORTS_DIR
    if options.output_dir:
        report_module.REPORTS_DIR = Path(options.output_dir)
    try:
        result = report_module.generate_report(
            content=markdown,
            report_type="sector",
            symbol=options.name,
            output_format=options.output_format,
            title=title,
            filename=filename,
        )
    finally:
        report_module.REPORTS_DIR = original_dir

    if result.get("format") == "html":
        _restore_inline_svgs(Path(result["path"]))

    result["markdown"] = markdown
    result["scope"] = options.scope
    result["subject"] = options.name
    if options.open_report:
        _open_path(Path(result["path"]))
    return result


def _restore_inline_svgs(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return

    def repl(match: re.Match) -> str:
        svg = html.unescape(match.group(1))
        svg = re.sub(
            r"\s+xmlns='<a href=\"http://www\.w3\.org/2000/svg\"><rect\"[^>]*>"
            r"http://www\.w3\.org/2000/svg'><rect</a>",
            "><rect",
            svg,
        )
        svg = re.sub(r'<span class="sig-[^"]+">([^<]+)</span>', r"\1", svg)
        return svg

    text = re.sub(r"<p>(&lt;svg\b.*?&lt;/svg&gt;)</p>", repl, text, flags=re.S)
    text = re.sub(
        r"<p>(&lt;section\b.*?scope-card-grid.*?&lt;/section&gt;)</p>",
        lambda match: re.sub(r'<span class="sig-[^"]+">([^<]+)</span>', r"\1", html.unescape(match.group(1))),
        text,
        flags=re.S,
    )
    text = re.sub(
        r"<p>(&lt;div class=&#x27;empty-chart[^&]*&#x27;&gt;.*?&lt;/div&gt;)</p>",
        lambda match: html.unescape(match.group(1)),
        text,
        flags=re.S,
    )
    text = text.replace(
        "</style>",
        "\n.scope-card-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:12px 0 18px;}\n"
        ".scope-card{border:1px solid #e2e8f0;border-radius:8px;background:#fff;padding:12px 14px;box-shadow:0 1px 2px rgba(15,23,42,.04);}\n"
        ".scope-card-label{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#64748b;font-weight:700;}\n"
        ".scope-card-value{font-size:18px;color:#059669;font-weight:800;line-height:1.25;margin-top:4px;}\n"
        ".scope-card-note{font-size:11px;color:#64748b;margin-top:4px;line-height:1.35;}\n"
        ".scope-chart{width:calc(50% - 12px);max-width:none;height:auto;border:1px solid #e2e8f0;border-radius:8px;margin:8px 10px 8px 0;background:#fff;display:inline-block;vertical-align:top;}\n"
        ".scope-chart-wide{width:calc(50% - 12px);max-width:none;}\n"
        ".empty-chart{display:inline-block;vertical-align:top;width:calc(50% - 12px);box-sizing:border-box;margin:8px 10px 8px 0;padding:12px 14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;color:#64748b;}\n"
        ".empty-chart-wide{width:calc(100% - 12px);}\n"
        "@media(max-width:760px){.scope-chart,.scope-chart-wide,.empty-chart,.empty-chart-wide{width:100%;margin-right:0;}}\n"
        "</style>",
    )
    path.write_text(text, encoding="utf-8")


def _open_path(path: Path) -> None:
    try:
        if shutil.which("open"):
            os.system(f"open {path!s}")
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    options = parse_scope_report_args(argv)
    result = generate_scope_report(options=options)
    print(result["path"])
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
