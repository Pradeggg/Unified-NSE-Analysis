#!/usr/bin/env python3
"""Build a portfolio-level RIC Sherlock HTML report.

This is a batch, evidence-first companion to `/ric sherlock SYMBOL`.
It uses the same Sherlock evidence categories programmatically:

1. Quote / EOD snapshot
2. Technical setup
3. Screener fundamentals
4. Recent announcements / catalysts
5. Intraday trade setup and levels

Each symbol is cached independently so the report can be resumed without
rerunning slow web evidence for completed symbols.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal.tools import (  # noqa: E402
    _load_price_history,
    explain_intraday_setup,
    get_cached_financials,
    get_symbol_snapshot,
    get_technical_setup,
    scrape_screener_in,
)
from top_picks_report import TV_CROSSHAIR_JS, _svg_candlestick  # noqa: E402


REPORT_DIR = ROOT / "reports" / "portfolio"
CACHE_DIR = REPORT_DIR / "ric_sherlock_cache"
DEFAULT_PORTFOLIO_CSV = REPORT_DIR / "portfolio_analysis_20260610.csv"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    try:
        import numpy as np

        if isinstance(value, np.generic):
            return _jsonable(value.item())
    except Exception:
        pass
    return str(value)


def _f(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text or text in {"—", "-", "nan", "None"}:
        return None
    try:
        out = float(text)
    except Exception:
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def _fmt(value: Any, digits: int = 1, suffix: str = "") -> str:
    val = _f(value)
    if val is None:
        return "—"
    return f"{val:.{digits}f}{suffix}"


def _money(value: Any) -> str:
    val = _f(value)
    if val is None:
        return "—"
    if abs(val) >= 1000:
        return f"₹{val:,.0f}"
    return f"₹{val:,.2f}"


def _pct_change(old: Any, new: Any) -> float | None:
    old_f = _f(old)
    new_f = _f(new)
    if old_f is None or new_f is None or old_f == 0:
        return None
    return (new_f / old_f - 1.0) * 100.0


def _table_last_growth(table: dict[str, Any], metric: str) -> float | None:
    vals = table.get(metric) if isinstance(table, dict) else None
    if not isinstance(vals, list) or len(vals) < 2:
        return None
    return _pct_change(vals[-2], vals[-1])


def _cached_growth(rows: Any, field: str) -> float | None:
    if not isinstance(rows, list) or len(rows) < 2:
        return None
    clean = [r for r in rows if isinstance(r, dict) and _f(r.get(field)) is not None]
    if len(clean) < 2:
        return None
    clean.sort(key=lambda r: str(r.get("period_end") or r.get("period_label") or ""))
    return _pct_change(clean[-2].get(field), clean[-1].get(field))


def _portfolio_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        sym = str(row.get("symbol") or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(row)
    return out


def _signal_class(signal: str | None) -> str:
    sig = (signal or "").upper()
    if "BUY" in sig:
        return "buy"
    if "SELL" in sig:
        return "sell"
    return "hold"


def _rating_class(rating: str | None) -> str:
    r = (rating or "").upper()
    if "ACCUMULATE" in r:
        return "core"
    if "AVOID" in r or "EXIT" in r:
        return "avoid"
    return "watch"


def _sherlock_verdict(snapshot: dict[str, Any], technical: dict[str, Any], portfolio_row: dict[str, Any]) -> str:
    stage = str(snapshot.get("stage") or portfolio_row.get("stage") or "").upper()
    signal = str(snapshot.get("trading_signal") or portfolio_row.get("signal") or "").upper()
    tech_score = _f(snapshot.get("technical_score") or portfolio_row.get("technical_score")) or 0
    rs = _f(snapshot.get("relative_strength") or portfolio_row.get("relative_strength")) or 0
    if stage == "STAGE_2" and signal in {"BUY", "STRONG_BUY", "HOLD"} and tech_score >= 55 and rs >= 10:
        return "Constructive Sherlock"
    if stage == "STAGE_2":
        return "Stage 2, needs confirmation"
    if stage == "STAGE_4" or signal == "SELL" or tech_score < 25:
        return "Cautious / Review"
    return "Neutral Watch"


def _chart_history(symbol: str, days: int = 260, limit: int = 130) -> dict[str, Any]:
    try:
        df = _load_price_history(symbol, days=days)
    except Exception as exc:
        return {"symbol": symbol, "error": str(exc), "bars": []}
    if df is None or df.empty:
        return {"symbol": symbol, "error": "no EOD price history available", "bars": []}
    source = str(df.attrs.get("data_source") or "")
    if "PostgreSQL" not in source:
        return {
            "symbol": symbol,
            "error": f"PostgreSQL EOD history unavailable; refused non-PG fallback source: {source or 'unknown'}",
            "bars": [],
            "source": source or "unknown",
        }
    frame = df.copy()
    for col in ["OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY"]:
        if col in frame.columns:
            frame[col] = frame[col].apply(_f)
    frame = frame.dropna(subset=["TIMESTAMP", "CLOSE"]).sort_values("TIMESTAMP")
    frame["SMA20"] = frame["CLOSE"].rolling(20).mean()
    frame["SMA50"] = frame["CLOSE"].rolling(50).mean()
    frame["SMA200"] = frame["CLOSE"].rolling(200).mean()
    frame["EMA20"] = frame["CLOSE"].ewm(span=20, adjust=False).mean()
    frame["EMA50"] = frame["CLOSE"].ewm(span=50, adjust=False).mean()
    frame["EMA200"] = frame["CLOSE"].ewm(span=200, adjust=False).mean()
    delta = frame["CLOSE"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, math.nan)
    frame["RSI14"] = 100 - (100 / (1 + rs))
    ema12 = frame["CLOSE"].ewm(span=12, adjust=False).mean()
    ema26 = frame["CLOSE"].ewm(span=26, adjust=False).mean()
    frame["MACD"] = ema12 - ema26
    frame["MACD_SIGNAL"] = frame["MACD"].ewm(span=9, adjust=False).mean()
    frame["MACD_HIST"] = frame["MACD"] - frame["MACD_SIGNAL"]
    frame = frame.tail(limit)
    bars: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        ts = row.get("TIMESTAMP")
        date_text = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
        bars.append(
            {
                "d": date_text,
                "o": _f(row.get("OPEN")),
                "h": _f(row.get("HIGH")),
                "l": _f(row.get("LOW")),
                "c": _f(row.get("CLOSE")),
                "v": _f(row.get("TOTTRDQTY")),
                "s20": _f(row.get("SMA20")),
                "s50": _f(row.get("SMA50")),
                "s200": _f(row.get("SMA200")),
                "e20": _f(row.get("EMA20")),
                "e50": _f(row.get("EMA50")),
                "e200": _f(row.get("EMA200")),
                "rsi": _f(row.get("RSI14")),
                "macd": _f(row.get("MACD")),
                "macds": _f(row.get("MACD_SIGNAL")),
                "macdh": _f(row.get("MACD_HIST")),
            }
        )
    return {
        "symbol": symbol,
        "source": frame.attrs.get("data_source", "PostgreSQL market.equity_eod"),
        "bars": bars,
    }


def _ensure_chart_history(symbol: str, result: dict[str, Any]) -> dict[str, Any]:
    chart = result.get("chart_history")
    bars = chart.get("bars") if isinstance(chart, dict) else []
    latest_bar = bars[-1] if isinstance(bars, list) and bars else {}
    if (
        isinstance(chart, dict)
        and bars
        and isinstance(latest_bar, dict)
        and "rsi" in latest_bar
        and "macd" in latest_bar
        and "e20" in latest_bar
        and len(bars) <= 140
        and "PostgreSQL" in str(chart.get("source") or "")
    ):
        return result
    result["chart_history"] = _jsonable(_chart_history(symbol))
    if not result["chart_history"].get("error"):
        result.setdefault("source_trail", []).append("_load_price_history")
    return result


def collect_symbol(symbol: str, portfolio_row: dict[str, Any], refresh: bool = False) -> dict[str, Any]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{symbol}.json"
    if cache_path.exists() and not refresh:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            had_cached_financials = bool(cached.get("cached_financials"))
            chart_bars = (cached.get("chart_history") or {}).get("bars") or []
            had_chart_history = bool(chart_bars)
            had_indicator_history = (
                bool(chart_bars)
                and isinstance(chart_bars[-1], dict)
                and "rsi" in chart_bars[-1]
                and "macd" in chart_bars[-1]
                and "e20" in chart_bars[-1]
            )
            had_pg_chart_history = "PostgreSQL" in str((cached.get("chart_history") or {}).get("source") or "")
            upgraded = _ensure_cached_financials(symbol, cached)
            upgraded = _ensure_chart_history(symbol, upgraded)
            if (
                (bool(upgraded.get("cached_financials")) and not had_cached_financials)
                or (bool((upgraded.get("chart_history") or {}).get("bars")) and not had_chart_history)
                or (
                    bool((upgraded.get("chart_history") or {}).get("bars"))
                    and not had_indicator_history
                )
                or (
                    bool((upgraded.get("chart_history") or {}).get("bars"))
                    and not had_pg_chart_history
                )
            ):
                cache_path.write_text(json.dumps(upgraded, indent=2, ensure_ascii=False), encoding="utf-8")
            return upgraded
        except Exception:
            pass

    result: dict[str, Any] = {
        "symbol": symbol,
        "portfolio": portfolio_row,
        "collected_at": datetime.now().isoformat(timespec="seconds"),
        "source_trail": [],
        "errors": [],
    }

    try:
        result["snapshot"] = _jsonable(get_symbol_snapshot(symbol))
        result["source_trail"].append("get_symbol_snapshot")
    except Exception as exc:
        result["snapshot"] = {"symbol": symbol, "error": str(exc)}
        result["errors"].append(f"snapshot: {exc}")

    try:
        result["technical"] = _jsonable(get_technical_setup(symbol))
        result["source_trail"].append("get_technical_setup")
    except Exception as exc:
        result["technical"] = {"symbol": symbol, "error": str(exc)}
        result["errors"].append(f"technical: {exc}")

    try:
        result["fundamentals"] = _jsonable(scrape_screener_in(symbol))
        result["source_trail"].append("scrape_screener_in")
    except Exception as exc:
        result["fundamentals"] = {"symbol": symbol, "error": str(exc)}
        result["errors"].append(f"fundamentals: {exc}")
    result = _ensure_cached_financials(symbol, result)

    try:
        result["trade_setup"] = _jsonable(explain_intraday_setup(symbol, timeframe="15m"))
        result["source_trail"].append("explain_intraday_setup")
    except Exception as exc:
        result["trade_setup"] = {"symbol": symbol, "error": str(exc)}
        result["errors"].append(f"trade_setup: {exc}")

    result["verdict"] = _sherlock_verdict(
        result.get("snapshot") or {},
        result.get("technical") or {},
        portfolio_row,
    )
    result = _ensure_chart_history(symbol, result)
    cache_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def _ensure_cached_financials(symbol: str, result: dict[str, Any]) -> dict[str, Any]:
    fund = result.get("fundamentals") if isinstance(result.get("fundamentals"), dict) else {}
    already_ok = bool(fund) and not fund.get("error")
    if already_ok or result.get("cached_financials"):
        return result
    try:
        cached = _jsonable(get_cached_financials(symbol))
    except Exception as exc:
        cached = {"symbol": symbol, "error": str(exc), "missing_evidence": ["cached_financials"]}
    if not isinstance(cached, dict):
        cached = {"symbol": symbol, "error": "cached financials returned non-dict"}
    result["cached_financials"] = cached
    if not cached.get("error"):
        result.setdefault("source_trail", []).append("get_cached_financials")
    return result


def _first_items(items: Any, n: int = 3) -> list[Any]:
    if isinstance(items, list):
        return items[:n]
    return []


def _announcements(fund: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    anns = fund.get("announcements") if isinstance(fund, dict) else None
    if not isinstance(anns, list):
        return []
    return [a for a in anns[:limit] if isinstance(a, dict)]


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("%", "").replace("₹", "")
    if not text or text in {"—", "-", "None", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _verdict_key(verdict: Any) -> str:
    text = str(verdict or "").lower()
    if "constructive" in text:
        return "constructive"
    if "stage 2" in text:
        return "stage2"
    if "cautious" in text or "review" in text:
        return "review"
    return "watch"


def _heat_class(value: Any, mode: str = "score") -> str:
    num = _as_float(value)
    if num is None:
        return "heat-na"
    if mode == "distance":
        rank = 3 if num >= -8 else 2 if num >= -20 else 1 if num >= -40 else 0
    elif mode == "return":
        rank = 3 if num >= 8 else 2 if num >= 2 else 1 if num >= -5 else 0
    elif mode == "rs":
        rank = 3 if num >= 65 else 2 if num >= 50 else 1 if num >= 30 else 0
    else:
        rank = 3 if num >= 75 else 2 if num >= 55 else 1 if num >= 35 else 0
    return f"heat-{rank}"


def _metric_cell(value: Any, mode: str = "score", suffix: str = "") -> str:
    decimals = 1 if suffix else 0
    return f'<td class="num metric {_heat_class(value, mode)}">{_fmt(value, decimals, suffix)}</td>'


def _fund_source(item: dict[str, Any]) -> str:
    fund = item.get("fundamentals") or {}
    cached = item.get("cached_financials") or {}
    if fund and not fund.get("error"):
        return "Screener"
    if cached and not cached.get("error"):
        return "PG fallback"
    return "Missing"


def _parse_report_date(value: Any) -> Any:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("T", " ")[:19]
    for candidate, fmt in (
        (text[:19], "%Y-%m-%d %H:%M:%S"),
        (text[:16], "%Y-%m-%d %H:%M"),
        (text[:10], "%Y-%m-%d"),
    ):
        try:
            return datetime.strptime(candidate, fmt).date()
        except Exception:
            continue
    try:
        return datetime.fromisoformat(text).date()
    except Exception:
        return None


def _trade_setup_freshness(item: dict[str, Any], max_age_days: int = 1) -> tuple[bool, str]:
    trade = item.get("trade_setup") if isinstance(item.get("trade_setup"), dict) else {}
    levels = trade.get("levels") if isinstance(trade.get("levels"), dict) else {}
    technical = item.get("technical") if isinstance(item.get("technical"), dict) else {}
    snapshot = item.get("snapshot") if isinstance(item.get("snapshot"), dict) else {}
    eod_date = _parse_report_date(
        technical.get("as_of")
        or snapshot.get("snapshot_date")
        or technical.get("snapshot_date")
        or snapshot.get("as_of")
    )
    trade_date = _parse_report_date(trade.get("latest_timestamp") or levels.get("latest_timestamp"))
    if not eod_date or not trade_date:
        return False, "15m trade levels hidden on the chart because freshness could not be verified."
    age_days = (eod_date - trade_date).days
    if age_days < 0 or age_days <= max_age_days:
        return True, f"15m trade levels fresh vs EOD snapshot ({trade_date} vs {eod_date})."
    return (
        False,
        f"15m trade levels are stale ({trade_date} vs EOD {eod_date}); hidden from the daily chart.",
    )


def _daily_pivots_from_bars(bars: list[dict[str, Any]]) -> dict[str, float]:
    if not bars:
        return {}
    latest = bars[-1]
    high = _as_float(latest.get("h"))
    low = _as_float(latest.get("l"))
    close = _as_float(latest.get("c"))
    if high is None or low is None or close is None:
        return {}
    pp = (high + low + close) / 3.0
    return {"PP": pp, "R1": (2 * pp) - low, "S1": (2 * pp) - high}


def _local_technical_chart(
    item: dict[str, Any],
    supports: list[Any],
    resistances: list[Any],
    invalidation: Any,
) -> str:
    chart = item.get("chart_history") if isinstance(item.get("chart_history"), dict) else {}
    bars = chart.get("bars") if isinstance(chart.get("bars"), list) else []
    bars = [b for b in bars if isinstance(b, dict) and _as_float(b.get("c")) is not None][-130:]
    if len(bars) < 5:
        return '<div class="local-chart-empty">Local EOD chart unavailable for this symbol.</div>'

    first_date = html.escape(str(bars[0].get("d") or ""))
    last_date = html.escape(str(bars[-1].get("d") or ""))
    latest_close = _money(bars[-1].get("c"))
    source = html.escape(str(chart.get("source") or "local EOD history"))
    fresh_levels, freshness_note = _trade_setup_freshness(item)
    chart_payload = {
        "bars": [
            {
                "date": str(b.get("d") or ""),
                "open": _as_float(b.get("o")) or _as_float(b.get("c")) or 0,
                "high": _as_float(b.get("h")) or _as_float(b.get("c")) or 0,
                "low": _as_float(b.get("l")) or _as_float(b.get("c")) or 0,
                "close": _as_float(b.get("c")) or 0,
                "volume": _as_float(b.get("v")) or 0,
            }
            for b in bars
        ],
        "ema20_series": [_as_float(b.get("e20") if b.get("e20") is not None else b.get("s20")) for b in bars],
        "ema50_series": [_as_float(b.get("e50") if b.get("e50") is not None else b.get("s50")) for b in bars],
        "ema200_series": [_as_float(b.get("e200") if b.get("e200") is not None else b.get("s200")) for b in bars],
        "rsi_series": [_as_float(b.get("rsi")) for b in bars],
        "wk52_high": _as_float((item.get("technical") or {}).get("52w_high")),
        "wk52_low": _as_float((item.get("technical") or {}).get("52w_low")),
        "pivots": _daily_pivots_from_bars(bars),
        "support_levels": [_as_float(x) for x in supports[:3] if _as_float(x) is not None] if fresh_levels else [],
        "resistance_levels": [_as_float(x) for x in resistances[:3] if _as_float(x) is not None] if fresh_levels else [],
    }
    setup_side = str((item.get("trade_setup") or {}).get("setup_side") or (item.get("trade_setup") or {}).get("setup_label") or "").upper()
    targets = resistances[:3] if "SHORT" not in setup_side else supports[:3]
    candle_svg = _svg_candlestick(
        chart_payload,
        symbol=str(item.get("symbol") or ""),
        stop=invalidation if fresh_levels else None,
        t1=targets[0] if fresh_levels and len(targets) > 0 else None,
        t2=targets[1] if fresh_levels and len(targets) > 1 else None,
        t3=targets[2] if fresh_levels and len(targets) > 2 else None,
        width=1100,
        price_h=380,
        vol_h=80,
        rsi_h=70,
    )
    return f"""
<div class="local-chart-card">
  <div class="local-chart-title">
    <div><b>{html.escape(item['symbol'])}</b> · 6-Month Daily Technical Chart</div>
    <span>{first_date} → {last_date} · Latest {latest_close}</span>
  </div>
  <div class="tp-chart-wrap">
    <div class="tp-chart-toolbar" aria-label="Chart controls">
      <div class="tp-chart-group" aria-label="Time range">
        <button type="button" class="tp-chart-btn" data-range="22" title="Show latest 1 month">1M</button>
        <button type="button" class="tp-chart-btn" data-range="65" title="Show latest 3 months">3M</button>
        <button type="button" class="tp-chart-btn active" data-range="130" title="Show latest 6 months">6M</button>
        <button type="button" class="tp-chart-btn" data-range="all" title="Show all loaded bars">All</button>
      </div>
      <div class="tp-chart-group" aria-label="Zoom and overlays">
        <button type="button" class="tp-chart-btn" data-zoom="in" title="Zoom in">+</button>
        <button type="button" class="tp-chart-btn" data-zoom="out" title="Zoom out">-</button>
        <button type="button" class="tp-chart-btn" data-zoom="reset" title="Reset view">Reset</button>
        <button type="button" class="tp-chart-btn" data-toggle-ann="1" title="Show or hide chart annotations">Annotations</button>
      </div>
    </div>
    {candle_svg}
  </div>
  <div class="local-chart-foot">Source: {source}. Daily candles use local EOD OHLC with EMA20/50/200, volume, RSI, pivots and 52-week levels. {html.escape(freshness_note)}</div>
</div>"""


def _heat_tile(item: dict[str, Any]) -> str:
    row = item.get("portfolio") or {}
    snap = item.get("snapshot") or {}
    tech = item.get("technical") or {}
    sym = item["symbol"]
    verdict_key = _verdict_key(item.get("verdict"))
    signal = str(snap.get("trading_signal") or row.get("signal") or "—")
    stage = str(snap.get("stage") or row.get("stage") or "—")
    tech_score = snap.get("technical_score") or row.get("technical_score")
    fund_score = row.get("enhanced_fund_score")
    rs = snap.get("relative_strength") or row.get("relative_strength")
    month = snap.get("change_1m_pct") or row.get("chg_1m")
    dist = tech.get("pct_from_52h")
    return f"""
<button class="heat-tile verdict-{verdict_key}" data-symbol="{html.escape(sym)}" data-verdict="{verdict_key}" onclick="focusStock('{html.escape(sym)}')" type="button">
  <span class="tile-head"><b>{html.escape(sym)}</b><span>{html.escape(stage.replace('STAGE_', 'S'))}</span></span>
  <span class="tile-signal pill {_signal_class(signal)}">{html.escape(signal)}</span>
  <span class="tile-metrics">
    <span class="{_heat_class(tech_score)}">Tech {_fmt(tech_score)}</span>
    <span class="{_heat_class(fund_score)}">Fund {_fmt(fund_score)}</span>
    <span class="{_heat_class(rs, 'rs')}">RS {_fmt(rs, 0, '%')}</span>
    <span class="{_heat_class(month, 'return')}">1M {_fmt(month, 1, '%')}</span>
    <span class="{_heat_class(dist, 'distance')}">52W {_fmt(dist, 1, '%')}</span>
  </span>
</button>"""


def _heatmap_grid(rows: list[dict[str, Any]]) -> str:
    tiles = "\n".join(_heat_tile(item) for item in rows)
    return f"""
<div class="legend">
  <span><i class="swatch constructive"></i>Constructive</span>
  <span><i class="swatch stage2"></i>Stage 2 confirmation</span>
  <span><i class="swatch watch"></i>Neutral watch</span>
  <span><i class="swatch review"></i>Cautious / review</span>
</div>
<div class="heat-grid">{tiles}</div>"""


def _matrix_table(rows: list[dict[str, Any]]) -> str:
    body = []
    for item in rows:
        row = item.get("portfolio") or {}
        snap = item.get("snapshot") or {}
        tech = item.get("technical") or {}
        trade = item.get("trade_setup") or {}
        sym = item["symbol"]
        verdict_key = _verdict_key(item.get("verdict"))
        signal = str(snap.get("trading_signal") or row.get("signal") or "—")
        setup = str(trade.get("setup_label") or "—")
        body.append(
            f'<tr data-symbol="{html.escape(sym)}" data-verdict="{verdict_key}">'
            f"<td><b>{html.escape(sym)}</b></td>"
            f"<td>{html.escape(str(snap.get('stage') or row.get('stage') or '—'))}</td>"
            f"<td><span class=\"pill {_signal_class(signal)}\">{html.escape(signal)}</span></td>"
            f"{_metric_cell(row.get('portfolio_score'))}"
            f"{_metric_cell(snap.get('technical_score') or row.get('technical_score'))}"
            f"{_metric_cell(row.get('enhanced_fund_score'))}"
            f"{_metric_cell(snap.get('relative_strength') or row.get('relative_strength'), 'rs', '%')}"
            f"{_metric_cell(snap.get('change_1m_pct') or row.get('chg_1m'), 'return', '%')}"
            f"{_metric_cell(tech.get('pct_from_52h'), 'distance', '%')}"
            f"<td><span class=\"pill {_signal_class(setup)}\">{html.escape(setup)}</span></td>"
            f"<td>{html.escape(_fund_source(item))}</td>"
            "</tr>"
        )
    return "\n".join(body)


def _ric_detail_html(item: dict[str, Any]) -> str:
    sym = item["symbol"]
    row = item.get("portfolio") or {}
    snap = item.get("snapshot") or {}
    tech = item.get("technical") or {}
    fund = item.get("fundamentals") or {}
    cached_fund = item.get("cached_financials") or {}
    trade = item.get("trade_setup") or {}
    ratios = fund.get("ratios") if isinstance(fund.get("ratios"), dict) else {}
    q = fund.get("quarterly") if isinstance(fund.get("quarterly"), dict) else {}
    annual = fund.get("annual_pl") if isinstance(fund.get("annual_pl"), dict) else {}
    sales_yoy = _table_last_growth(annual, "Sales+")
    eps_yoy = _table_last_growth(annual, "EPS in Rs")
    q_sales_qoq = _table_last_growth(q, "Sales+")
    q_eps_qoq = _table_last_growth(q, "EPS in Rs")
    if sales_yoy is None:
        sales_yoy = _cached_growth(cached_fund.get("annual"), "revenue")
    if eps_yoy is None:
        eps_yoy = _cached_growth(cached_fund.get("annual"), "eps")
    if q_sales_qoq is None:
        q_sales_qoq = _cached_growth(cached_fund.get("quarterly"), "revenue")
    if q_eps_qoq is None:
        q_eps_qoq = _cached_growth(cached_fund.get("quarterly"), "eps")
    fund_source = "Screener"
    if fund.get("error") and cached_fund and not cached_fund.get("error"):
        fund_source = "PostgreSQL cached financials"
    elif fund.get("error"):
        fund_source = "Missing / rate-limited"
    setup_label = trade.get("setup_label") or "—"
    levels = trade.get("levels") if isinstance(trade.get("levels"), dict) else {}
    supports = levels.get("supports") if isinstance(levels.get("supports"), list) else []
    resistances = levels.get("resistances") if isinstance(levels.get("resistances"), list) else []
    fresh_levels, freshness_note = _trade_setup_freshness(item)
    pros = _first_items(fund.get("pros"), 3)
    cons = _first_items(fund.get("cons"), 3)
    anns = _announcements(fund)
    local_chart = _local_technical_chart(item, supports, resistances, trade.get("invalidation_level"))

    def pill(label: str, klass: str) -> str:
        return f'<span class="pill {klass}">{html.escape(label)}</span>'

    above = []
    for label, key in [("20DMA", "above_sma20"), ("50DMA", "above_sma50"), ("200DMA", "above_sma200")]:
        val = tech.get(key)
        if val is True:
            above.append(pill(f"Above {label}", "buy"))
        elif val is False:
            above.append(pill(f"Below {label}", "sell"))

    ann_html = ""
    if anns:
        ann_html = "<ul>" + "".join(
            f'<li>{html.escape(str(a.get("title") or a.get("text") or "Announcement")[:140])}</li>'
            for a in anns
        ) + "</ul>"
    else:
        ann_html = '<p class="muted">No announcement list captured from Screener/BSE evidence.</p>'

    verdict_key = _verdict_key(item.get("verdict"))

    return f"""
<details class="stock-detail" id="stock-{html.escape(sym)}" data-symbol="{html.escape(sym)}" data-verdict="{verdict_key}">
  <summary>
    <span class="sym">{html.escape(sym)}</span>
    <span class="muted">{html.escape(str(row.get('inputs') or row.get('company_name') or ''))}</span>
    <span class="pill {_rating_class(row.get('rating'))}">{html.escape(item.get('verdict') or 'Sherlock')}</span>
  </summary>
  <section class="chart-panel">
    <div class="chart-head">
      <div>
        <h3>Daily Candlestick Chart · 6-Month Local EOD</h3>
        <p class="muted">Top-picks style local SVG chart with daily candles, EMA20/50/200, volume, RSI, pivots, 52-week context, and fresh Sherlock 15m levels only.</p>
      </div>
    </div>
    <div class="chart-layout">
      {local_chart}
      <aside class="annotation-panel">
        <h3>Local Annotations</h3>
        <div class="anno-grid">
          <div><span class="label">Setup</span><b>{html.escape(str(setup_label))}</b></div>
          <div><span class="label">Invalidation</span><b>{_money(trade.get('invalidation_level'))}</b></div>
          <div><span class="label">52W High</span><b>{_money(tech.get('52w_high'))}</b></div>
          <div><span class="label">52W Dist</span><b>{_fmt(tech.get('pct_from_52h'), 1, '%')}</b></div>
        </div>
        <p><b>Supports:</b> {html.escape(', '.join(_money(x) for x in supports[:4]) or '—')}</p>
        <p><b>Resistances:</b> {html.escape(', '.join(_money(x) for x in resistances[:4]) or '—')}</p>
        <p class="freshness {'ok' if fresh_levels else 'warn'}"><b>Level freshness:</b> {html.escape(freshness_note)}</p>
        <p><b>Indicators to confirm:</b> Stage {html.escape(str(snap.get('stage') or row.get('stage') or '—'))}, RSI {_fmt(tech.get('rsi') or snap.get('rsi'))}, ADX {_fmt(tech.get('adx'))}, MACD {html.escape(str(tech.get('macd') or '—'))}, price vs 20/50/200DMA.</p>
      </aside>
    </div>
  </section>
  <div class="detail-grid">
    <section>
      <h3>Step 1 · Quote Snapshot</h3>
      <p><b>Price:</b> {_money(snap.get('price') or tech.get('price') or row.get('price'))}
      · <b>1D:</b> {_fmt(snap.get('change_1d_pct') or row.get('chg_1d'), 1, '%')}
      · <b>1W:</b> {_fmt(snap.get('change_1w_pct') or row.get('chg_1w'), 1, '%')}
      · <b>1M:</b> {_fmt(snap.get('change_1m_pct') or row.get('chg_1m'), 1, '%')}</p>
      <p><b>Sector:</b> {html.escape(str(snap.get('sector') or row.get('sector') or '—'))}
      · <b>MCap:</b> {html.escape(str(snap.get('market_cap_cat') or row.get('mcap') or '—'))}</p>
    </section>
    <section>
      <h3>Step 2 · Technical Setup</h3>
      <p><b>Stage:</b> {html.escape(str(snap.get('stage') or row.get('stage') or '—'))}
      · <b>Signal:</b> {pill(str(snap.get('trading_signal') or row.get('signal') or '—'), _signal_class(str(snap.get('trading_signal') or row.get('signal'))))}
      · <b>Trend:</b> {html.escape(str(snap.get('trend_signal') or row.get('trend') or '—'))}</p>
      <p><b>Tech Score:</b> {_fmt(snap.get('technical_score') or row.get('technical_score'))}
      · <b>RS:</b> {_fmt(snap.get('relative_strength') or row.get('relative_strength'), 1, '%')}
      · <b>RSI:</b> {_fmt(tech.get('rsi') or snap.get('rsi'))}
      · <b>ADX:</b> {_fmt(tech.get('adx'))}
      · <b>MACD:</b> {html.escape(str(tech.get('macd') or '—'))}</p>
      <p>{''.join(above) or '<span class="muted">MA evidence unavailable</span>'}</p>
      <p><b>52W:</b> {_money(tech.get('52w_low'))} – {_money(tech.get('52w_high'))}
      · <b>Dist. from high:</b> {_fmt(tech.get('pct_from_52h'), 1, '%')}</p>
    </section>
    <section>
      <h3>Step 3 · Fundamentals</h3>
      <p><b>P/E:</b> {html.escape(str(ratios.get('Stock P/E') or '—'))}
      · <b>Book:</b> {html.escape(str(ratios.get('Book Value') or '—'))}
      · <b>ROCE:</b> {html.escape(str(ratios.get('ROCE') or '—'))}
      · <b>ROE:</b> {html.escape(str(ratios.get('ROE') or '—'))}
      · <b>Fund Score:</b> {_fmt(row.get('enhanced_fund_score'))}
      · <b>Source:</b> {html.escape(fund_source)}</p>
      <p><b>Annual Sales YoY:</b> {_fmt(sales_yoy, 1, '%')}
      · <b>Annual EPS YoY:</b> {_fmt(eps_yoy, 1, '%')}
      · <b>Quarter Sales QoQ:</b> {_fmt(q_sales_qoq, 1, '%')}
      · <b>Quarter EPS QoQ:</b> {_fmt(q_eps_qoq, 1, '%')}</p>
      <div class="cols"><div><b>Pros</b><ul>{''.join(f'<li>{html.escape(str(x))}</li>' for x in pros) or '<li>—</li>'}</ul></div>
      <div><b>Cons</b><ul>{''.join(f'<li>{html.escape(str(x))}</li>' for x in cons) or '<li>—</li>'}</ul></div></div>
    </section>
    <section>
      <h3>Step 4 · News & Catalysts</h3>
      {ann_html}
    </section>
    <section>
      <h3>Step 5 · Trade Setup</h3>
      <p><b>15m setup:</b> {pill(str(setup_label), _signal_class(str(trade.get('setup_side') or setup_label)))}
      · <b>Score:</b> {_fmt(trade.get('score'))}
      · <b>Latest intraday close:</b> {_money(trade.get('latest_close'))}</p>
      <p><b>Supports:</b> {html.escape(', '.join(_money(x) for x in supports[:4]) or '—')}</p>
      <p><b>Resistances:</b> {html.escape(', '.join(_money(x) for x in resistances[:4]) or '—')}</p>
      <p><b>Invalidation:</b> {_money(trade.get('invalidation_level'))}</p>
    </section>
  </div>
</details>
"""


def _summary_table(rows: list[dict[str, Any]]) -> str:
    body = []
    for item in rows:
        row = item.get("portfolio") or {}
        snap = item.get("snapshot") or {}
        tech = item.get("technical") or {}
        sig = str(snap.get("trading_signal") or row.get("signal") or "—")
        verdict_key = _verdict_key(item.get("verdict"))
        body.append(
            f'<tr data-symbol="{html.escape(item["symbol"])}" data-verdict="{verdict_key}">'
            f"<td><b>{html.escape(item['symbol'])}</b></td>"
            f"<td>{html.escape(str(row.get('inputs') or ''))}</td>"
            f"<td>{html.escape(str(snap.get('sector') or row.get('sector') or '—'))}</td>"
            f"<td>{html.escape(str(snap.get('stage') or row.get('stage') or '—'))}</td>"
            f"<td><span class=\"pill {_signal_class(sig)}\">{html.escape(sig)}</span></td>"
            f"{_metric_cell(row.get('portfolio_score'))}"
            f"{_metric_cell(snap.get('technical_score') or row.get('technical_score'))}"
            f"{_metric_cell(row.get('enhanced_fund_score'))}"
            f"{_metric_cell(snap.get('relative_strength') or row.get('relative_strength'), 'rs', '%')}"
            f"{_metric_cell(tech.get('pct_from_52h'), 'distance', '%')}"
            f"<td>{html.escape(item.get('verdict') or '—')}</td>"
            "</tr>"
        )
    return "\n".join(body)


def render_html(rows: list[dict[str, Any]], generated_at: str) -> str:
    total = len(rows)
    stage_counts: dict[str, int] = {}
    signal_counts: dict[str, int] = {}
    verdict_counts: dict[str, int] = {}
    for item in rows:
        row = item.get("portfolio") or {}
        snap = item.get("snapshot") or {}
        stage = str(snap.get("stage") or row.get("stage") or "—")
        signal = str(snap.get("trading_signal") or row.get("signal") or "—")
        verdict = str(item.get("verdict") or "—")
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        signal_counts[signal] = signal_counts.get(signal, 0) + 1
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

    screener_count = sum(1 for r in rows if _fund_source(r) == "Screener")
    pg_fallback_count = sum(1 for r in rows if _fund_source(r) == "PG fallback")
    missing_fund_count = sum(1 for r in rows if _fund_source(r) == "Missing")

    detail_html = "\n".join(_ric_detail_html(r) for r in rows)
    summary_rows = _summary_table(rows)
    heatmap_html = _heatmap_grid(rows)
    matrix_rows = _matrix_table(rows)
    stage_bits = "".join(f"<span class=\"chip\">{html.escape(k)}: <b>{v}</b></span>" for k, v in sorted(stage_counts.items()))
    signal_bits = "".join(f"<span class=\"chip\">{html.escape(k)}: <b>{v}</b></span>" for k, v in sorted(signal_counts.items()))
    verdict_bits = "".join(f"<span class=\"chip\">{html.escape(k)}: <b>{v}</b></span>" for k, v in sorted(verdict_counts.items()))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Portfolio RIC Sherlock Report</title>
<style>
:root{{--primary:#0f766e;--primary-dark:#134e4a;--bg:#eef5f4;--surface:#fff;--text:#102927;--muted:#667a77;--line:rgba(15,76,71,.16);--radius:8px;--shadow:0 1px 3px rgba(15,23,42,.08)}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;font-size:14px;line-height:1.55}}
.appbar{{background:#0f3f3b;color:white;padding:18px 24px;box-shadow:0 3px 10px rgba(0,0,0,.16)}}
.appbar h1{{margin:0;font-size:22px;font-weight:750}} .appbar .meta{{font-size:12px;opacity:.9;margin-top:4px}}
.content{{max-width:1480px;margin:0 auto;padding:22px}}
.disc{{background:#fff7ed;color:#92400e;border-left:4px solid #d97706;padding:10px 14px;border-radius:var(--radius);margin-bottom:16px;font-size:12px}}
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:16px}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:14px 16px;box-shadow:var(--shadow)}}
.label{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:750}} .value{{font-size:26px;font-weight:850;color:var(--primary-dark);margin-top:2px}}
.chips{{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 16px}} .chip{{display:inline-block;background:white;border:1px solid var(--line);padding:5px 9px;border-radius:16px;color:#244b47;font-size:12px}}
h2{{font-size:16px;color:var(--primary-dark);margin:22px 0 10px}} h3{{font-size:13px;color:var(--primary-dark);margin:0 0 8px}}
.sticky-tools{{position:sticky;top:0;z-index:20;background:rgba(238,245,244,.96);backdrop-filter:blur(8px);border:1px solid var(--line);border-radius:var(--radius);padding:10px;margin:10px 0 16px;box-shadow:var(--shadow)}}
.toolbar{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}} input{{padding:8px 10px;border:1px solid var(--line);border-radius:6px;min-width:280px;background:#fff}} button.filter-btn{{border:1px solid var(--line);background:#fff;border-radius:6px;padding:7px 10px;color:#23413e;cursor:pointer}} button.filter-btn.active{{background:#0f766e;color:#fff;border-color:#0f766e}}
.legend{{display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin:4px 0 10px;color:var(--muted);font-size:12px}} .swatch{{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-2px}} .swatch.constructive{{background:#16a34a}} .swatch.stage2{{background:#0ea5a4}} .swatch.watch{{background:#64748b}} .swatch.review{{background:#dc2626}}
.heat-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(156px,1fr));gap:8px;margin-bottom:18px}}
.heat-tile{{border:1px solid var(--line);border-radius:8px;background:#fff;padding:9px;text-align:left;min-height:126px;cursor:pointer;box-shadow:var(--shadow);display:flex;flex-direction:column;gap:7px;color:var(--text)}}
.heat-tile:hover{{outline:2px solid rgba(15,118,110,.25)}} .verdict-constructive{{border-left:5px solid #16a34a}} .verdict-stage2{{border-left:5px solid #0ea5a4}} .verdict-watch{{border-left:5px solid #64748b}} .verdict-review{{border-left:5px solid #dc2626}}
.tile-head{{display:flex;justify-content:space-between;gap:8px;align-items:center}} .tile-head b{{font-size:14px;color:#102927}} .tile-head span{{font-size:11px;color:var(--muted);font-weight:750}} .tile-signal{{align-self:flex-start}}
.tile-metrics{{display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:auto}} .tile-metrics span,.metric{{border-radius:5px;padding:3px 5px;font-size:11px;font-variant-numeric:tabular-nums}}
.heat-3{{background:#dcfce7;color:#14532d}} .heat-2{{background:#e0f2fe;color:#075985}} .heat-1{{background:#fef3c7;color:#92400e}} .heat-0{{background:#fee2e2;color:#991b1b}} .heat-na{{background:#f1f5f9;color:#64748b}}
.tbl-wrap{{overflow-x:auto;background:#fff;border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}}
table{{border-collapse:collapse;width:100%;font-size:12px}} th{{background:var(--primary);color:#fff;text-align:left;padding:9px 10px;white-space:nowrap}} td{{padding:8px 10px;border-bottom:1px solid #edf2f2;vertical-align:top}} tbody tr:nth-child(even){{background:rgba(15,118,110,.035)}} .num{{text-align:right;font-variant-numeric:tabular-nums}}
.pill{{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:750;white-space:nowrap}} .buy,.core{{background:#dcfce7;color:#166534}} .sell,.avoid{{background:#fee2e2;color:#991b1b}} .hold,.watch{{background:#f1f5f9;color:#475569}}
.stock-detail{{background:#fff;border:1px solid var(--line);border-radius:var(--radius);margin:8px 0;box-shadow:var(--shadow)}} .stock-detail summary{{cursor:pointer;padding:12px 14px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.stock-detail[open]{{outline:2px solid rgba(15,118,110,.12)}} .sym{{font-weight:800;font-size:15px;color:#0f766e}} .muted{{color:var(--muted);font-size:12px}}
.chart-panel{{border-top:1px solid #edf2f2;margin:0 14px 12px;padding:12px 0 0}} .chart-head{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px}} .chart-head p{{margin:2px 0 0}}
.chart-layout{{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:12px;align-items:stretch}}
.local-chart-card{{background:#fff;border:1px solid var(--line);border-radius:8px;padding:10px;box-shadow:var(--shadow);min-width:0}} .local-chart-title{{display:flex;justify-content:space-between;gap:10px;align-items:center;color:#102927;font-size:13px;margin-bottom:6px}} .local-chart-title span{{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}}
.local-chart-foot{{margin-top:6px;color:var(--muted);font-size:11px}} .local-chart-empty{{height:420px;display:flex;align-items:center;justify-content:center;border:1px solid var(--line);border-radius:8px;color:var(--muted);background:#fbfdfd}}
.tp-chart-wrap{{position:relative;background:#0f1218;border:1px solid #1e222d;border-radius:8px;padding:8px;overflow:hidden}} .tp-chart-toolbar{{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;margin:0 0 8px 0}} .tp-chart-group{{display:flex;align-items:center;gap:5px;flex-wrap:wrap}}
.tp-chart-btn{{height:26px;min-width:30px;padding:0 9px;border:1px solid #2a2e39;border-radius:4px;background:#1e222d;color:#d1d4dc;font-size:11px;font-weight:800;line-height:24px;cursor:pointer;font-family:inherit}} .tp-chart-btn:hover,.tp-chart-btn.active{{background:#2563eb;border-color:#3b82f6;color:#fff}}
.tp-tv-chart{{touch-action:none;user-select:none;min-height:530px}} .tp-tv-chart.is-panning,.tp-tv-chart.is-panning .cx-area{{cursor:grabbing!important}} .tp-ann{{display:none}} .tp-chart-wrap.show-ann .tp-ann{{display:inline}} .tp-chart-wrap.show-ann .tp-pat{{display:inline}} .tp-chart-wrap.show-ann.zoomed-tight .tp-pat{{display:none}}
.annotation-panel{{background:#fbfdfd;border:1px solid var(--line);border-radius:8px;padding:12px;min-height:100%}}
.anno-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:8px 0 10px}} .anno-grid div{{background:#fff;border:1px solid #edf2f2;border-radius:6px;padding:8px}} .anno-grid b{{display:block;margin-top:2px;color:#102927}} .freshness{{border-radius:6px;padding:8px 10px;font-size:12px}} .freshness.ok{{background:#ecfdf5;color:#166534;border:1px solid #bbf7d0}} .freshness.warn{{background:#fff7ed;color:#9a3412;border:1px solid #fed7aa}}
.detail-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px;padding:0 14px 14px}} section{{border-top:1px solid #edf2f2;padding-top:12px}} p{{margin:4px 0 8px}} ul{{margin:6px 0 0 18px;padding:0}} li{{margin:2px 0}} .cols{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
@media (max-width:980px){{.chart-layout{{grid-template-columns:1fr}}}}
@media (max-width:720px){{.content{{padding:14px}} input{{min-width:100%;width:100%}} .heat-grid{{grid-template-columns:repeat(auto-fill,minmax(138px,1fr))}} .cols{{grid-template-columns:1fr}} .chart-head{{display:block}} .anno-grid{{grid-template-columns:1fr}}}}
@media print{{.sticky-tools,.toolbar,.disc{{display:none}} details{{break-inside:avoid}} details:not([open])>summary::after{{content:' (details collapsed)';color:#777}}}}
</style>
</head>
<body>
<div class="appbar"><h1>Portfolio RIC Sherlock Report</h1><div class="meta">Generated {html.escape(generated_at)} · {total} resolved stocks · quote → technicals → fundamentals → catalysts → trade setup</div></div>
<div class="content">
<div class="disc">Research and learning only. This is not investment advice or a trade recommendation. Intraday levels can be stale outside market hours; validate liquidity, spreads, corporate actions, and latest prices independently.</div>
<div class="metrics">
  <div class="card"><div class="label">Stocks Analyzed</div><div class="value">{total}</div></div>
  <div class="card"><div class="label">Stage 2</div><div class="value">{stage_counts.get('STAGE_2',0)}</div></div>
  <div class="card"><div class="label">SELL Signals</div><div class="value">{signal_counts.get('SELL',0)}</div></div>
  <div class="card"><div class="label">Cautious / Review</div><div class="value">{verdict_counts.get('Cautious / Review',0)}</div></div>
  <div class="card"><div class="label">Screener Evidence</div><div class="value">{screener_count}</div></div>
  <div class="card"><div class="label">PG Fallback</div><div class="value">{pg_fallback_count}</div></div>
  <div class="card"><div class="label">Missing Fundamentals</div><div class="value">{missing_fund_count}</div></div>
</div>
<div class="sticky-tools">
  <div class="toolbar">
    <input id="q" placeholder="Filter symbol, sector, verdict, setup..." oninput="applyFilters()">
    <button class="filter-btn active" data-filter="all" onclick="setVerdictFilter('all', this)" type="button">All</button>
    <button class="filter-btn" data-filter="constructive" onclick="setVerdictFilter('constructive', this)" type="button">Constructive</button>
    <button class="filter-btn" data-filter="stage2" onclick="setVerdictFilter('stage2', this)" type="button">Stage 2</button>
    <button class="filter-btn" data-filter="watch" onclick="setVerdictFilter('watch', this)" type="button">Watch</button>
    <button class="filter-btn" data-filter="review" onclick="setVerdictFilter('review', this)" type="button">Review</button>
    <button class="filter-btn" onclick="toggleDetails(true)" type="button">Open all</button>
    <button class="filter-btn" onclick="toggleDetails(false)" type="button">Close all</button>
  </div>
</div>
<h2>Stage Distribution</h2><div class="chips">{stage_bits}</div>
<h2>Signal Distribution</h2><div class="chips">{signal_bits}</div>
<h2>Sherlock Verdicts</h2><div class="chips">{verdict_bits}</div>
<h2>Sherlock Heat Map</h2>
{heatmap_html}
<h2>Heat Map Matrix</h2>
<div class="tbl-wrap"><table id="matrix"><thead><tr><th>Symbol</th><th>Stage</th><th>Signal</th><th class="num">Portfolio</th><th class="num">Tech</th><th class="num">Fund</th><th class="num">RS</th><th class="num">1M</th><th class="num">52W Dist</th><th>Trade Setup</th><th>Fund Source</th></tr></thead><tbody>{matrix_rows}</tbody></table></div>
<h2>Portfolio Summary Table</h2>
<div class="tbl-wrap"><table id="summary"><thead><tr><th>Symbol</th><th>Input</th><th>Sector</th><th>Stage</th><th>Signal</th><th class="num">Portfolio</th><th class="num">Tech</th><th class="num">Fund</th><th class="num">RS</th><th class="num">52W Dist</th><th>Verdict</th></tr></thead><tbody>{summary_rows}</tbody></table></div>
<h2>RIC Sherlock Detail By Stock</h2>
{detail_html}
</div>
{TV_CROSSHAIR_JS}
<script>
let verdictFilter = 'all';
function matches(el, q){{
  const text = (el.innerText || el.textContent || '').toLowerCase();
  const verdict = el.dataset.verdict || '';
  return (!q || text.includes(q) || (el.dataset.symbol || '').toLowerCase().includes(q)) &&
    (verdictFilter === 'all' || verdict === verdictFilter);
}}
function applyFilters(){{
  const q = (document.getElementById('q').value || '').toLowerCase();
  document.querySelectorAll('#summary tbody tr,#matrix tbody tr,.heat-tile,.stock-detail').forEach(function(el){{
    el.style.display = matches(el, q) ? '' : 'none';
  }});
}}
function setVerdictFilter(filter, btn){{
  verdictFilter = filter;
  document.querySelectorAll('.filter-btn[data-filter]').forEach(function(b){{ b.classList.remove('active'); }});
  if (btn) btn.classList.add('active');
  applyFilters();
}}
function toggleDetails(open){{
  document.querySelectorAll('.stock-detail').forEach(function(d){{
    if (d.style.display !== 'none') {{
      d.open = open;
    }}
  }});
}}
function focusStock(symbol){{
  const detail = document.getElementById('stock-' + symbol);
  if (!detail) return;
  detail.open = true;
  detail.scrollIntoView({{behavior:'smooth', block:'start'}});
}}
document.addEventListener('DOMContentLoaded', function(){{
  applyFilters();
}});
</script>
</body>
</html>"""


def build_report(portfolio_csv: Path, limit: int | None, refresh: bool) -> dict[str, str | int]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    rows = _portfolio_rows(portfolio_csv)
    if limit:
        rows = rows[:limit]
    evidence: list[dict[str, Any]] = []
    total = len(rows)
    for idx, row in enumerate(rows, 1):
        sym = str(row.get("symbol") or "").strip().upper()
        if not sym:
            continue
        print(f"[{idx:02d}/{total:02d}] RIC Sherlock evidence: {sym}", flush=True)
        evidence.append(collect_symbol(sym, row, refresh=refresh))

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M IST")
    html_doc = render_html(evidence, generated_at)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = REPORT_DIR / f"portfolio_ric_sherlock_{stamp}.html"
    json_path = REPORT_DIR / f"portfolio_ric_sherlock_{stamp}.json"
    latest_html = REPORT_DIR / "latest_portfolio_ric_sherlock.html"
    latest_json = REPORT_DIR / "latest_portfolio_ric_sherlock.json"
    html_path.write_text(html_doc, encoding="utf-8")
    json_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    latest_html.write_text(html_doc, encoding="utf-8")
    latest_json.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "symbols": len(evidence),
        "html": str(html_path),
        "json": str(json_path),
        "latest_html": str(latest_html),
        "latest_json": str(latest_json),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build portfolio RIC Sherlock HTML report")
    parser.add_argument("--portfolio-csv", type=Path, default=DEFAULT_PORTFOLIO_CSV)
    parser.add_argument("--limit", type=int, default=None, help="Optional symbol cap for testing")
    parser.add_argument("--refresh", action="store_true", help="Ignore per-symbol evidence cache")
    args = parser.parse_args()
    result = build_report(args.portfolio_csv, args.limit, args.refresh)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
