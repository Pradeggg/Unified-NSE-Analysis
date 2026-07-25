"""Stateful terminal live-commentary dashboard for Agent Adda."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import os
import queue
import re
import threading
import time
from typing import Any

import pandas as pd
from rich.console import Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from terminal.tools import (
    get_index_snapshot,
    get_live_market_overview,
    get_nse_quotes,
    get_top_gainers_losers,
    scan_symbols_intraday,
)
from terminal.intraday import get_intraday_candles
from terminal.fno_composite import get_fno_overview


DEFAULT_TRACKER_SYMBOLS = [
    "TRENT",
    "DIXON",
    "SCHNEIDER",
    "INDUSINDBK",
    "NESTLEIND",
    "ICICIBANK",
    "MCX",
    "MANINDS",
    "BAJAJCON",
    "KIMS",
]


def _configured_source_mode(*keys: str) -> str:
    raw = ""
    for key in keys:
        raw = os.getenv(key, "").strip()
        if raw:
            break
    mode = raw.lower().replace("-", "_")
    if mode in {"bse", "bse_only", "bse_live", "bse_public", "exchange_public"}:
        return "bse"
    if mode in {"nse", "nse_only", "nse_quote_equity"}:
        return "nse_only"
    return "auto"


@dataclass
class LiveDashboardConfig:
    symbols: list[str] = field(default_factory=list)
    refresh_secs: int = 60
    max_cycles: int | None = None
    use_llm: bool = True
    interval: str = "15m"
    top_n: int = 10
    strategies: list[str] | None = None
    require_volume: bool = True
    min_volume_ratio: float = 1.2
    include_fno: bool = True


@dataclass
class TrackedSymbolState:
    symbol: str
    last_price: float | None
    pct_change: float | None
    direction: str
    status: str
    trigger: float | None = None
    invalidation: float | None = None
    target1: float | None = None
    target2: float | None = None
    rr: float | None = None
    strategy: str = ""
    note: str = ""
    freshness: str = ""
    source: str = ""
    mtf_levels: dict[str, Any] = field(default_factory=dict)
    fno_context: dict[str, Any] = field(default_factory=dict)
    decision_context: dict[str, Any] = field(default_factory=dict)
    locked_setup: bool = False
    locked_at: str = ""


@dataclass
class LiveDashboardEvent:
    symbol: str
    message: str
    timestamp: str
    severity: str = "info"


@dataclass
class LiveDashboardState:
    started_at: datetime = field(default_factory=datetime.now)
    cycle: int = 0
    last_updated_at: datetime | None = None
    symbols: list[str] = field(default_factory=list)
    previous_zone_by_symbol: dict[str, str] = field(default_factory=dict)
    previous_snapshot_by_symbol: dict[str, dict[str, Any]] = field(default_factory=dict)
    locked_setups_by_symbol: dict[str, dict[str, Any]] = field(default_factory=dict)
    tracked_symbols: list[TrackedSymbolState] = field(default_factory=list)
    cycle_changes: dict[str, Any] = field(default_factory=dict)
    events: list[LiveDashboardEvent] = field(default_factory=list)
    last_commentary: str = ""
    market_context: str = ""
    source_health: list[str] = field(default_factory=list)


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def _fmt_num(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.{decimals}f}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.2f}%"


def _fmt_pct_compact(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.1f}%"


def _fmt_level(value: float | None) -> str:
    if value is None:
        return "n/a"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:,.2f}"


def _round_level(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except Exception:
        return None
    if number != number:
        return None
    return round(number, 2)


def _pct_style(value: float | None) -> str:
    if value is None:
        return "dim"
    if value > 0:
        return "bold green"
    if value < 0:
        return "bold red"
    return "yellow"


def _window_levels(frame, label: str) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {"label": label, "support": None, "resistance": None, "range_pct": None}
    high = _round_level(frame["High"].max())
    low = _round_level(frame["Low"].min())
    close = _round_level(frame["Close"].iloc[-1])
    range_pct = None
    if high is not None and low is not None and close:
        range_pct = round((high - low) / close * 100, 2)
    return {"label": label, "support": low, "resistance": high, "range_pct": range_pct}


def _latest_session_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep only the latest trading session from an intraday frame.

    `get_intraday_candles(..., period="1d")` can fall back to a longer
    interval/period early in the session when yfinance returns too few candles.
    MTF current-day levels must not treat that longer fallback as "start of day".
    """
    if frame is None or frame.empty:
        return frame
    out = frame.copy().sort_index()
    idx = pd.to_datetime(out.index)
    if not isinstance(idx, pd.DatetimeIndex) or idx.empty:
        return out
    if idx.tz is not None:
        idx = idx.tz_convert("Asia/Kolkata").tz_localize(None)
    out.index = idx
    latest_date = idx.max().date()
    return out[idx.date == latest_date]


def _nearest_level(levels: list[float], price: float | None, *, above: bool) -> float | None:
    clean = sorted({float(level) for level in levels if level is not None})
    if price is None:
        return _round_level(clean[0] if clean else None)
    if above:
        candidates = [level for level in clean if level >= price]
        return _round_level(candidates[0] if candidates else (clean[-1] if clean else None))
    candidates = [level for level in clean if level <= price]
    return _round_level(candidates[-1] if candidates else (clean[0] if clean else None))


def build_mtf_level_context(symbol: str, last_price: float | None, interval: str = "5m") -> dict[str, Any]:
    """Build support/resistance context across weekly, daily, and intraday windows."""
    daily = get_intraday_candles(symbol, "1d", period="3mo")
    intraday = _latest_session_frame(get_intraday_candles(symbol, interval, period="1d"))
    derived_last_price = _round_level(last_price)
    intraday_pct_change = None
    if not intraday.empty and "Close" in intraday:
        closes = pd.to_numeric(intraday["Close"], errors="coerce").dropna()
        if not closes.empty:
            derived_last_price = derived_last_price if derived_last_price is not None else _round_level(closes.iloc[-1])
            first_close = _to_float(closes.iloc[0])
            last_close = _to_float(closes.iloc[-1])
            if first_close and last_close is not None:
                intraday_pct_change = _round_level((last_close / first_close - 1) * 100)

    completed_daily = daily.iloc[:-1] if len(daily) > 1 else daily
    previous_week = completed_daily.tail(5)
    previous_3_days = completed_daily.tail(3)
    previous_day = completed_daily.tail(1)

    start_of_day = intraday
    last_30_mins = intraday
    if not intraday.empty:
        latest = intraday.index.max()
        cutoff = latest - pd.Timedelta(minutes=30)
        last_30_mins = intraday[intraday.index >= cutoff]
        if last_30_mins.empty:
            last_30_mins = intraday.tail(6)

    windows = {
        "previous_week": _window_levels(previous_week, "Previous week"),
        "previous_3_days": _window_levels(previous_3_days, "Previous 3 days"),
        "previous_day": _window_levels(previous_day, "Previous day"),
        "start_of_day": _window_levels(start_of_day, "Start of day"),
        "last_30_mins": _window_levels(last_30_mins, "Last 30 mins"),
    }
    supports = [value["support"] for value in windows.values() if value.get("support") is not None]
    resistances = [value["resistance"] for value in windows.values() if value.get("resistance") is not None]
    support = _nearest_level(supports, derived_last_price, above=False)
    breakout = _nearest_level(resistances, derived_last_price, above=True)
    lower_supports = sorted({float(level) for level in supports if support is None or float(level) < support}, reverse=True)
    breakdown_target = _round_level(lower_supports[0] if lower_supports else None)
    higher_resistances = sorted({float(level) for level in resistances if breakout is None or float(level) > breakout})
    target = _round_level(higher_resistances[0] if higher_resistances else None)
    if target is None and breakout is not None and support is not None:
        target = _round_level(breakout + max(breakout - support, 0.0) * 0.75)
    if breakdown_target is None and breakout is not None and support is not None:
        breakdown_target = _round_level(support - max(breakout - support, 0.0) * 0.75)

    range_values = [value.get("range_pct") for value in windows.values() if value.get("range_pct") is not None]
    return {
        "windows": windows,
        "support": support,
        "breakout": breakout,
        "target": target,
        "breakdown_target": breakdown_target,
        "last_price": derived_last_price,
        "intraday_pct_change": intraday_pct_change,
        "range_pressure_pct": _round_level(max(range_values) if range_values else None),
    }


def _missing_mtf_context(symbol: str, exc: Exception | str) -> dict[str, Any]:
    reason = str(exc) or f"MTF levels unavailable for {symbol}"
    return {
        "status": "missing",
        "reason": reason,
        "missing_evidence": ["mtf_levels"],
        "windows": {},
        "support": None,
        "breakout": None,
        "target": None,
        "breakdown_target": None,
        "last_price": None,
        "intraday_pct_change": None,
    }


def _enrichment_timeout_secs(env_key: str, default: float) -> float:
    raw = os.getenv(env_key, "").strip()
    if not raw:
        return default
    try:
        return max(0.1, float(raw))
    except ValueError:
        return default


def _run_daemon_batch_with_timeout(
    rows: list[TrackedSymbolState],
    worker,
    *,
    timeout_secs: float | None,
) -> dict[int, tuple[Any | None, Exception | None]]:
    out: queue.Queue[tuple[int, Any | None, Exception | None]] = queue.Queue()
    timeout = 6.0 if timeout_secs is None else max(0.1, float(timeout_secs))

    def target(index: int, row: TrackedSymbolState) -> None:
        try:
            out.put((index, worker(row), None))
        except Exception as exc:
            out.put((index, None, exc))

    threads = [
        threading.Thread(target=target, args=(idx, row), daemon=True, name=f"live-enrich-{row.symbol}")
        for idx, row in enumerate(rows)
    ]
    for thread in threads:
        thread.start()

    deadline = time.monotonic() + timeout
    for thread in threads:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        thread.join(remaining)

    results: dict[int, tuple[Any | None, Exception | None]] = {}
    while True:
        try:
            idx, value, exc = out.get_nowait()
        except queue.Empty:
            break
        results[idx] = (value, exc)
    return results


def _mtf_note(mtf_levels: dict[str, Any]) -> str:
    if not mtf_levels:
        return ""
    windows = mtf_levels.get("windows") or {}
    parts = []
    for key in ("previous_week", "previous_3_days", "previous_day", "start_of_day", "last_30_mins"):
        row = windows.get(key) or {}
        label = row.get("label") or key
        support = _fmt_level(row.get("support"))
        resistance = _fmt_level(row.get("resistance"))
        parts.append(f"{label} S/R {support}/{resistance}")
    return "; ".join(parts)


def style_direction(direction: str) -> Text:
    normalized = str(direction or "WATCH").upper()
    if normalized == "LONG":
        return Text("LONG", style="bold green")
    if normalized == "SHORT":
        return Text("SHORT", style="bold red")
    return Text("WATCH", style="bold yellow")


def style_status(status: str) -> Text:
    label = str(status or "watch")
    lower = label.lower()
    compact = label.upper()
    if compact.startswith("L-"):
        return Text(label, style="bold green")
    if compact.startswith("S-"):
        return Text(label, style="bold red")
    if compact.startswith("W-"):
        return Text(label, style="bold yellow")
    if "invalid" in lower or "breakdown" in lower:
        return Text(label, style="bold red")
    if "t1 hit" in lower or "trail" in lower:
        return Text(label, style="bold bright_green")
    if "long active" in lower:
        return Text(label, style="bold green")
    if "short active" in lower:
        return Text(label, style="bold red")
    if "near trigger" in lower:
        return Text(label, style="bold yellow")
    if "watch" in lower:
        return Text(label, style="yellow")
    return Text(label, style="white")


def _compact_read(row: TrackedSymbolState) -> Text:
    status = row.status.lower()
    if "invalid" in status or "breakdown" in status:
        label = "INV"
    elif "t1 hit" in status or "trail" in status:
        label = "TRAIL"
    elif "active" in status:
        label = "ACT"
    elif "trigger" in status or "watch" in status:
        label = "WATCH"
    else:
        label = (status[:5] or "WATCH").upper()
    direction = {"LONG": "L", "SHORT": "S"}.get(row.direction, "W")
    return style_status(f"{direction}-{label}")


def _normalise_symbols(symbols: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    for item in symbols or []:
        for part in str(item).replace(",", " ").split():
            sym = "".join(ch for ch in part.upper() if ch.isalnum() or ch in {"&", "-"})
            if sym and sym not in cleaned:
                cleaned.append(sym)
    return cleaned


def _market_context(overview: dict) -> str:
    indices = overview.get("indices") or {}
    n50 = indices.get("NIFTY 50") or {}
    bank = indices.get("NIFTY BANK") or {}
    vix = indices.get("INDIA VIX") or {}
    adv_dec = overview.get("adv_dec") or {}
    breadth = ""
    if adv_dec:
        breadth = f", breadth {adv_dec.get('advances', 'n/a')}A/{adv_dec.get('declines', 'n/a')}D"
    return (
        f"NIFTY {_fmt_num(_to_float(n50.get('last')), 0)} {_fmt_pct(_to_float(n50.get('pct_change')))}, "
        f"BANKNIFTY {_fmt_num(_to_float(bank.get('last')), 0)} {_fmt_pct(_to_float(bank.get('pct_change')))}, "
        f"VIX {_fmt_num(_to_float(vix.get('last')), 2)} {_fmt_pct(_to_float(vix.get('pct_change')))}"
        f"{breadth}"
    )


def _market_context_is_complete(context: str) -> bool:
    text = str(context or "")
    return bool(text and "n/a" not in text.lower())


def _index_row_is_complete(row: dict[str, Any] | None) -> bool:
    if not isinstance(row, dict):
        return False
    return _to_float(row.get("last")) is not None and _to_float(row.get("pct_change")) is not None


def _overview_has_core_indices(overview: dict) -> bool:
    indices = overview.get("indices") or {}
    return all(
        _index_row_is_complete(indices.get(name))
        for name in ("NIFTY 50", "NIFTY BANK", "INDIA VIX")
    )


def _snapshot_to_live_index_row(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "last": snapshot.get("close"),
        "change": None,
        "pct_change": snapshot.get("chg_pct"),
        "day_high": snapshot.get("high"),
        "day_low": snapshot.get("low"),
    }


def _fill_market_overview_from_index_snapshots(overview: dict) -> tuple[dict, list[str]]:
    repaired = dict(overview or {})
    indices = dict(repaired.get("indices") or {})
    notes: list[str] = []
    for name in ("NIFTY 50", "NIFTY BANK", "INDIA VIX"):
        if _index_row_is_complete(indices.get(name)):
            continue
        try:
            snapshot = get_index_snapshot(name)
        except Exception as exc:
            notes.append(f"{name} snapshot error: {exc}")
            continue
        if not snapshot or snapshot.get("error"):
            notes.append(f"{name} snapshot unavailable")
            continue
        indices[name] = _snapshot_to_live_index_row(snapshot)
        as_of = snapshot.get("as_of")
        suffix = f" {as_of}" if as_of else ""
        notes.append(f"{name} snapshot fallback{suffix}")
    repaired["indices"] = indices
    if notes:
        repaired["market_context_degraded"] = True
    return repaired, notes


def _styled_market_context(context: str) -> Text:
    text = Text()
    tokens = str(context or "market context unavailable").split(" ")
    for token in tokens:
        style = "white"
        stripped = token.strip(",")
        if stripped.startswith("+"):
            style = "bold green"
        elif stripped.startswith("-"):
            style = "bold red"
        elif "A/" in stripped and stripped.endswith("D"):
            style = "bold cyan"
        elif stripped in {"NIFTY", "BANKNIFTY", "VIX"}:
            style = "bold white"
        text.append(token + " ", style=style)
    return text


def _styled_commentary(commentary: str) -> Text | Markdown:
    if any(marker in commentary for marker in ("###", "**", "|", "1.", "- ")):
        return Markdown(commentary)

    text = Text()
    for line in commentary.splitlines():
        stripped = line.strip()
        style = "white"
        lower = stripped.lower()
        if not stripped:
            text.append("\n")
            continue
        if stripped.endswith(":"):
            style = "bold cyan"
        elif "long active" in lower or "target hit" in lower or "t1 hit" in lower:
            style = "green"
        elif "short active" in lower or "invalid" in lower or "breakdown" in lower:
            style = "red"
        elif "watch" in lower or "near trigger" in lower:
            style = "yellow"
        elif "source health" in lower:
            style = "dim"
        text.append(line + "\n", style=style)
    return text


def _cycle_changes_text(changes: dict[str, Any]) -> Text:
    text = Text()
    for label, key, style in (
        ("New", "new_added", "bold cyan"),
        ("Removed", "removed", "bold red"),
        ("Forming", "forming", "yellow"),
        ("Confirmed", "confirmed", "bold green"),
        ("Active", "active", "bold bright_green"),
    ):
        names = ", ".join(item.get("symbol", "") for item in (changes.get(key) or [])[:10] if item.get("symbol"))
        text.append(f"{label}: ", style="bold white")
        text.append(names or "none", style=style if names else "dim")
        text.append("\n")
    if changes.get("status_changes"):
        text.append("Changed: ", style="bold white")
        text.append(
            "; ".join(
                f"{item.get('symbol')} {item.get('from')} -> {item.get('to')}"
                for item in changes["status_changes"][:8]
            ),
            style="bold magenta",
        )
    return text


def _fno_compact(row: TrackedSymbolState) -> Text:
    fno = row.fno_context or {}
    bias = str(fno.get("bias") or "n/a")
    pcr = _to_float(fno.get("pcr"))
    basis = _to_float(fno.get("basis"))
    label = f"{bias.upper()}"
    if pcr is not None:
        label += f" P{pcr:.2f}"
    if basis is not None:
        label += f" B{basis:g}"
    style = "dim"
    if bias == "bullish":
        style = "bold green"
    elif bias == "bearish":
        style = "bold red"
    elif bias == "sideways":
        style = "yellow"
    return Text(label, style=style)


def _symbols_from_movers(movers: dict) -> list[str]:
    symbols: list[str] = []
    for bucket in ("gainers", "losers"):
        for row in movers.get(bucket) or []:
            sym = str(row.get("symbol") or "").strip().upper()
            if sym and sym not in symbols:
                symbols.append(sym)
    return symbols


def _signal_volume_confirmed(signal: dict, min_volume_ratio: float) -> bool:
    indicator = signal.get("indicator") if isinstance(signal.get("indicator"), dict) else {}
    if indicator.get("volume_confirmed") is True:
        return True
    try:
        return float(indicator.get("vol_ratio") or 0.0) >= min_volume_ratio
    except Exception:
        return False


def _best_signal_for_symbol(symbol: str, scan: dict, config: LiveDashboardConfig | None = None) -> dict:
    candidates: list[dict] = []
    for row in (scan.get("top_buy") or []) + (scan.get("buy_signals") or []):
        if str(row.get("symbol") or "").upper() == symbol:
            candidates.append(row)
    for row in (scan.get("top_sell") or []) + (scan.get("sell_signals") or []):
        if str(row.get("symbol") or "").upper() == symbol:
            candidates.append(row)
    if config and config.require_volume:
        candidates = [
            row for row in candidates
            if _signal_volume_confirmed(row, config.min_volume_ratio)
        ]
    if not candidates:
        return {}
    return sorted(
        candidates,
        key=lambda row: (
            _signal_volume_confirmed(row, config.min_volume_ratio if config else 1.2),
            _to_float((row.get("indicator") or {}).get("range_pct")) or 0.0,
            _to_float(row.get("rr")) or 0.0,
        ),
        reverse=True,
    )[0]


def build_tracked_symbol(
    symbol: str,
    quote: dict,
    signal: dict,
    freshness: str = "",
    mtf_levels: dict[str, Any] | None = None,
) -> TrackedSymbolState:
    last_price = _to_float(quote.get("last_price") or quote.get("price") or quote.get("ltp"))
    pct_change = _to_float(quote.get("pct_change") or quote.get("change_pct"))
    direction_raw = str(signal.get("direction") or "").upper()
    direction = "LONG" if direction_raw == "BUY" else ("SHORT" if direction_raw == "SELL" else "WATCH")
    entry = _to_float(signal.get("entry")) or last_price
    if last_price is None and signal:
        last_price = entry
    stop = _to_float(signal.get("stoploss") or signal.get("stop"))
    target = _to_float(signal.get("target"))
    rr = _to_float(signal.get("rr"))
    mtf_levels = mtf_levels or {}
    strength = str(signal.get("strength") or "")
    same_tick_entry = (
        last_price is not None
        and entry is not None
        and abs(float(last_price) - float(entry)) < 0.000001
    )
    needs_trigger_confirmation = same_tick_entry and strength.lower().startswith("moderate")

    if not signal and mtf_levels:
        breakout = _to_float(mtf_levels.get("breakout"))
        support = _to_float(mtf_levels.get("support"))
        mtf_target = _to_float(mtf_levels.get("target"))
        if breakout is not None:
            entry = breakout
        if support is not None:
            stop = support
        if mtf_target is not None:
            target = mtf_target
        if entry is not None and stop is not None and target is not None and entry > stop:
            rr = round((target - entry) / (entry - stop), 2) if target > entry else None

    status = "watch"
    if direction == "LONG":
        if last_price is not None and target is not None and last_price >= target:
            status = "T1 hit / trail"
        elif last_price is not None and stop is not None and last_price < stop:
            status = "breakdown / long invalid"
        elif last_price is not None and entry is not None and last_price >= entry and not needs_trigger_confirmation:
            status = "long active"
        else:
            status = "near trigger / watch"
    elif direction == "SHORT":
        if last_price is not None and target is not None and last_price <= target:
            status = "T1 hit / trail"
        elif last_price is not None and stop is not None and last_price > stop:
            status = "short invalid"
        elif last_price is not None and entry is not None and last_price <= entry and not needs_trigger_confirmation:
            status = "short active"
        else:
            status = "near trigger / watch"
    note = str(signal.get("note") or _mtf_note(mtf_levels))
    if needs_trigger_confirmation and note:
        side_word = "above" if direction == "LONG" else "below" if direction == "SHORT" else "through"
        note = f"{note}; needs next candle hold {side_word} trigger"

    return TrackedSymbolState(
        symbol=symbol,
        last_price=last_price,
        pct_change=pct_change,
        direction=direction,
        status=status,
        trigger=entry,
        invalidation=stop,
        target1=target,
        target2=None,
        rr=rr,
        strategy=str(signal.get("strategy") or ("MTF breakout levels" if mtf_levels else "")),
        note=note,
        freshness=freshness,
        source="scan_symbols_intraday" if signal else ("mtf_levels" if mtf_levels else "get_nse_quotes"),
        mtf_levels=mtf_levels,
    )


def enrich_tracked_symbols_with_mtf_levels(
    rows: list[TrackedSymbolState],
    *,
    interval: str = "5m",
    timeout_secs: float | None = None,
) -> list[TrackedSymbolState]:
    timeout = timeout_secs
    if timeout is None:
        timeout = _enrichment_timeout_secs("AGENT_ADDA_MTF_ENRICH_TIMEOUT", 6.0)
    results = _run_daemon_batch_with_timeout(
        rows,
        lambda row: build_mtf_level_context(row.symbol, row.last_price, interval=interval),
        timeout_secs=timeout,
    )
    timeout_reason = f"MTF level provider timed out after {timeout:g}s"
    for idx, row in enumerate(rows):
        value, exc = results.get(idx, (None, TimeoutError(timeout_reason)))
        levels = _missing_mtf_context(row.symbol, exc) if exc or value is None else value
        row.mtf_levels = levels
        if row.last_price is None:
            row.last_price = _to_float(levels.get("last_price"))
        if row.pct_change is None:
            row.pct_change = _to_float(levels.get("intraday_pct_change"))
        breakout = _to_float(levels.get("breakout"))
        support = _to_float(levels.get("support"))
        breakdown_target = _to_float(levels.get("breakdown_target"))
        long_target = _to_float(levels.get("target"))
        weak_intraday = row.pct_change is not None and row.pct_change <= -0.5
        strong_intraday = row.pct_change is not None and row.pct_change >= 0.5
        if row.direction == "WATCH" and breakout is not None and support is not None:
            if weak_intraday and breakdown_target is not None and breakdown_target < support < breakout:
                row.direction = "SHORT"
                row.trigger = support
                row.invalidation = breakout
                row.target1 = breakdown_target
                row.status = "short active" if row.last_price is not None and row.last_price <= support else "near trigger / watch"
                row.strategy = "MTF breakdown levels"
            elif strong_intraday or row.pct_change is None:
                row.trigger = breakout
                row.invalidation = support
                row.target1 = long_target
                row.direction = "LONG"
                row.status = "near trigger / watch" if row.last_price is None or row.last_price < breakout else "long active"
                row.strategy = "MTF breakout levels"
            else:
                row.trigger = None
                row.invalidation = support
                row.target1 = None
                row.status = "watch"
        else:
            if not row.invalidation:
                row.invalidation = support
            if not row.target1:
                row.target1 = long_target
            if not row.trigger or row.trigger == row.last_price:
                row.trigger = breakout or row.trigger
        if row.rr is None and row.trigger is not None and row.invalidation is not None and row.target1 is not None:
            if row.trigger > row.invalidation and row.target1 > row.trigger:
                row.rr = round((row.target1 - row.trigger) / (row.trigger - row.invalidation), 2)
            elif row.trigger < row.invalidation and row.target1 < row.trigger:
                row.rr = round((row.trigger - row.target1) / (row.invalidation - row.trigger), 2)
        if not row.strategy or row.source == "get_nse_quotes":
            row.strategy = "MTF breakdown levels" if row.direction == "SHORT" else "MTF breakout levels"
        mtf_note = _mtf_note(levels)
        if mtf_note and not row.note:
            row.note = mtf_note
        if row.source == "get_nse_quotes":
            row.source = "mtf_levels"
    return rows


def _first_oi_strike(rows: list[dict]) -> float | None:
    if not rows:
        return None
    return _to_float(rows[0].get("strike"))


def _fno_bias_from_overview(row: TrackedSymbolState, overview: dict[str, Any]) -> tuple[str, str]:
    pcr = _to_float(overview.get("pcr"))
    basis = _to_float(overview.get("basis"))
    max_pain = _to_float(overview.get("max_pain"))
    top = overview.get("top_oi_strikes") or {}
    call_wall = _first_oi_strike(top.get("calls") or [])
    put_wall = _first_oi_strike(top.get("puts") or [])
    price = row.last_price

    score = 0
    reasons: list[str] = []
    if pcr is not None:
        if pcr >= 1.1:
            score += 1
            reasons.append(f"PCR {pcr:.2f} put-heavy")
        elif pcr < 0.8:
            score -= 1
            reasons.append(f"PCR {pcr:.2f} call-heavy")
        else:
            reasons.append(f"PCR {pcr:.2f} balanced")
    if basis is not None:
        if basis > 0:
            score += 1
            reasons.append(f"fut basis +{basis:g}")
        elif basis < 0:
            score -= 1
            reasons.append(f"fut basis {basis:g}")
    if max_pain is not None and price is not None:
        if price > max_pain:
            score += 1
            reasons.append(f"spot above max pain {max_pain:g}")
        elif price < max_pain:
            score -= 1
            reasons.append(f"spot below max pain {max_pain:g}")
    if put_wall is not None:
        reasons.append(f"PE wall {put_wall:g}")
    if call_wall is not None:
        reasons.append(f"CE wall {call_wall:g}")

    if score >= 2:
        return "bullish", "; ".join(reasons)
    if score <= -2:
        return "bearish", "; ".join(reasons)
    return "sideways", "; ".join(reasons)


def build_fno_context(row: TrackedSymbolState) -> dict[str, Any]:
    try:
        overview = get_fno_overview(row.symbol)
    except Exception as exc:
        return {"status": "missing", "bias": "unknown", "reason": str(exc)}
    if overview.get("status") not in {"ok", "missing_evidence"}:
        return {
            "status": overview.get("status") or "missing",
            "bias": "unknown",
            "reason": overview.get("error") or "F&O overview unavailable",
        }
    bias, reason = _fno_bias_from_overview(row, overview)
    top = overview.get("top_oi_strikes") or {}
    return {
        "status": overview.get("status"),
        "bias": bias,
        "reason": reason,
        "pcr": overview.get("pcr"),
        "max_pain": overview.get("max_pain"),
        "basis": overview.get("basis"),
        "cost_of_carry": overview.get("cost_of_carry"),
        "top_call_oi": (top.get("calls") or [])[:3],
        "top_put_oi": (top.get("puts") or [])[:3],
        "source_trail": overview.get("source_trail"),
        "missing_evidence": overview.get("missing_evidence") or [],
    }


def enrich_tracked_symbols_with_fno_context(
    rows: list[TrackedSymbolState],
    *,
    timeout_secs: float | None = None,
) -> list[TrackedSymbolState]:
    timeout = timeout_secs
    if timeout is None:
        timeout = _enrichment_timeout_secs("AGENT_ADDA_FNO_ENRICH_TIMEOUT", 8.0)
    results = _run_daemon_batch_with_timeout(rows, build_fno_context, timeout_secs=timeout)
    timeout_reason = f"F&O provider timed out after {timeout:g}s"
    for idx, row in enumerate(rows):
        value, exc = results.get(idx, (None, TimeoutError(timeout_reason)))
        if exc or value is None:
            row.fno_context = {
                "status": "missing",
                "bias": "unknown",
                "reason": str(exc) or "F&O context unavailable",
                "missing_evidence": ["fno_context"],
            }
        else:
            row.fno_context = value
    return rows


def _extract_context_pct(market_context: str, label: str) -> float | None:
    match = re.search(rf"\b{re.escape(label)}\s+[\d,]+(?:\.\d+)?\s+([+-]\d+(?:\.\d+)?)%", str(market_context or ""))
    return _to_float(match.group(1)) if match else None


def _extract_breadth(market_context: str) -> tuple[int | None, int | None]:
    match = re.search(r"breadth\s+(\d+)A/(\d+)D", str(market_context or ""), flags=re.IGNORECASE)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def market_regime_from_context(market_context: str) -> dict[str, Any]:
    nifty = _extract_context_pct(market_context, "NIFTY")
    bank = _extract_context_pct(market_context, "BANKNIFTY")
    vix = _extract_context_pct(market_context, "VIX")
    adv, dec = _extract_breadth(market_context)
    breadth_negative = adv is not None and dec is not None and adv < dec
    breadth_positive = adv is not None and dec is not None and adv > dec
    weak_index = (nifty is not None and nifty < 0) or (bank is not None and bank < 0)
    strong_index = (nifty is not None and nifty > 0) and (bank is not None and bank > 0)
    high_vix = vix is not None and vix >= 4.0

    if high_vix and weak_index and breadth_negative:
        label = "risk_off"
        stance = "Prefer shorts/retests; suppress marginal long option buys."
    elif high_vix:
        label = "high_vol_chop"
        stance = "Use confirmation; avoid late naked option entries."
    elif strong_index and breadth_positive and (vix is None or vix <= 0):
        label = "risk_on"
        stance = "Long breakouts can be considered after confirmation."
    elif weak_index and breadth_negative:
        label = "weak_tape"
        stance = "Prefer selective shorts; longs need stronger confirmation."
    else:
        label = "neutral"
        stance = "Trade only clean trigger/retest setups."

    return {
        "label": label,
        "nifty_pct": nifty,
        "banknifty_pct": bank,
        "vix_pct": vix,
        "advances": adv,
        "declines": dec,
        "stance": stance,
    }


def _direction_aligned_with_tape(row: TrackedSymbolState) -> int:
    pct = _to_float(row.pct_change)
    if pct is None or row.direction not in {"LONG", "SHORT"}:
        return 0
    if row.direction == "LONG":
        if pct >= 0.5:
            return 15
        if pct <= -0.5:
            return -25
    if row.direction == "SHORT":
        if pct <= -0.5:
            return 15
        if pct >= 0.5:
            return -25
    return 0


def _technical_decision_score(row: TrackedSymbolState, regime: dict[str, Any]) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 0
    status = (row.status or "").lower()
    rr = _to_float(row.rr) or 0.0
    if "invalid" in status or "breakdown" in status:
        return -100, ["setup invalidated"]
    if "active" in status:
        score += 25
        reasons.append("trigger active")
    elif "near trigger" in status:
        score += 10
        reasons.append("near trigger only")
    if rr >= 2.0:
        score += 20
        reasons.append(f"RR {rr:.1f} strong")
    elif rr >= 1.3:
        score += 10
        reasons.append(f"RR {rr:.1f} acceptable")
    elif rr > 0:
        score -= 10
        reasons.append(f"RR {rr:.1f} weak")
    tape_score = _direction_aligned_with_tape(row)
    score += tape_score
    if tape_score > 0:
        reasons.append("price momentum aligned")
    elif tape_score < 0:
        reasons.append("price momentum conflicts")
    if row.source == "scan_symbols_intraday":
        score += 10
        reasons.append("scanner-confirmed")
    elif row.source == "mtf_levels":
        score += 3
        reasons.append("MTF level-derived")
    if row.locked_setup:
        score += 5
        reasons.append("locked setup")
    if regime.get("label") == "risk_off" and row.direction == "LONG":
        score -= 25
        reasons.append("risk-off tape suppresses longs")
    if regime.get("label") == "risk_off" and row.direction == "SHORT":
        score += 10
        reasons.append("short aligned with risk-off tape")
    return score, reasons


def _fno_decision_score(row: TrackedSymbolState) -> tuple[int, list[str]]:
    fno = row.fno_context or {}
    bias = str(fno.get("bias") or "unknown").lower()
    score = 0
    reasons: list[str] = []
    if bias == "bullish":
        score += 18 if row.direction == "LONG" else -20 if row.direction == "SHORT" else 0
        reasons.append("F&O bullish")
    elif bias == "bearish":
        score += 18 if row.direction == "SHORT" else -20 if row.direction == "LONG" else 0
        reasons.append("F&O bearish")
    elif bias == "sideways":
        reasons.append("F&O sideways")
    else:
        reasons.append("F&O unavailable")
    pcr = _to_float(fno.get("pcr"))
    basis = _to_float(fno.get("basis"))
    max_pain = _to_float(fno.get("max_pain"))
    price = _to_float(row.last_price)
    if pcr is not None:
        if row.direction == "LONG" and pcr >= 1.0:
            score += 5
        elif row.direction == "LONG" and pcr < 0.75:
            score -= 5
        elif row.direction == "SHORT" and pcr < 0.8:
            score += 5
    if basis is not None:
        if row.direction == "LONG" and basis > 0:
            score += 4
        elif row.direction == "SHORT" and basis < 0:
            score += 4
        elif row.direction in {"LONG", "SHORT"}:
            score -= 2
    if price is not None and max_pain is not None:
        if row.direction == "LONG" and price > max_pain:
            score += 4
        elif row.direction == "SHORT" and price < max_pain:
            score += 4
        elif row.direction in {"LONG", "SHORT"}:
            score -= 4
    return score, reasons


def _volume_decision_score(row: TrackedSymbolState) -> tuple[int, list[str]]:
    text = f"{row.strategy} {row.note}".lower()
    if "volume" in text or "vol_ratio" in text:
        return 12, ["volume-aware setup"]
    if row.source == "scan_symbols_intraday":
        return 5, ["scanner signal"]
    return 0, ["volume not confirmed"]


def _options_suitability(row: TrackedSymbolState, regime: dict[str, Any], total_score: int, fno_score: int) -> str:
    if row.direction not in {"LONG", "SHORT"} or total_score < 25:
        return "No Trade"
    high_vix = (_to_float(regime.get("vix_pct")) or 0.0) >= 4.0
    if high_vix and total_score < 55:
        return "Avoid Options"
    if high_vix:
        return "Prefer Spread"
    if fno_score < 0:
        return "Prefer Futures"
    return "Option Buy OK"


def _final_action(row: TrackedSymbolState, regime: dict[str, Any], total_score: int, option_suitability: str) -> str:
    status = (row.status or "").lower()
    if "invalid" in status or "breakdown" in status:
        return "INVALIDATED"
    if option_suitability in {"No Trade", "Avoid Options"} and total_score < 45:
        return "AVOID"
    if "active" in status and total_score >= 65:
        return "TRADE NOW"
    if "near trigger" in status and total_score >= 45:
        return "WAIT FOR RETEST"
    if total_score >= 35:
        return "WATCH ONLY"
    return "NO TRADE"


def apply_trade_decisions(rows: list[TrackedSymbolState], market_context: str) -> list[TrackedSymbolState]:
    regime = market_regime_from_context(market_context)
    for row in rows:
        technical_score, technical_reasons = _technical_decision_score(row, regime)
        fno_score, fno_reasons = _fno_decision_score(row)
        volume_score, volume_reasons = _volume_decision_score(row)
        total_score = max(0, min(100, technical_score + fno_score + volume_score))
        suitability = _options_suitability(row, regime, total_score, fno_score)
        action = _final_action(row, regime, total_score, suitability)
        row.decision_context = {
            "market_regime": regime,
            "technical_score": technical_score,
            "fno_score": fno_score,
            "volume_score": volume_score,
            "decision_score": total_score,
            "options_suitability": suitability,
            "final_action": action,
            "reasons": [*technical_reasons, *fno_reasons, *volume_reasons][:8],
        }
    return rows


def _row_payload(row: TrackedSymbolState) -> dict[str, Any]:
    return {
        "symbol": row.symbol,
        "status": row.status,
        "direction": row.direction,
        "last_price": row.last_price,
        "trigger": row.trigger,
        "invalidation": row.invalidation,
        "target1": row.target1,
        "rr": row.rr,
        "strategy": row.strategy,
        "fno_bias": (row.fno_context or {}).get("bias"),
        "fno_pcr": (row.fno_context or {}).get("pcr"),
        "fno_basis": (row.fno_context or {}).get("basis"),
        "fno_max_pain": (row.fno_context or {}).get("max_pain"),
        "decision": row.decision_context,
        "locked_setup": row.locked_setup,
        "locked_at": row.locked_at,
    }


def _cycle_bucket(row: TrackedSymbolState) -> str:
    status = (row.status or "").lower()
    if "active" in status or "t1 hit" in status:
        return "active"
    if "near trigger" in status or (row.direction in {"LONG", "SHORT"} and row.source == "scan_symbols_intraday"):
        return "confirmed"
    if row.trigger is not None or row.invalidation is not None or row.target1 is not None:
        return "forming"
    return "forming"


def _is_invalid_status(status: str) -> bool:
    lower = (status or "").lower()
    return "invalid" in lower or "breakdown" in lower


def _is_lock_eligible(row: TrackedSymbolState) -> bool:
    if _is_invalid_status(row.status):
        return False
    if row.direction not in {"LONG", "SHORT"}:
        return False
    if row.trigger is None or row.invalidation is None or row.target1 is None:
        return False
    return _cycle_bucket(row) in {"confirmed", "active"}


def _recompute_status_from_locked_levels(row: TrackedSymbolState) -> None:
    if row.last_price is None:
        return
    if row.direction == "LONG":
        if row.target1 is not None and row.last_price >= row.target1:
            row.status = "T1 hit / trail"
        elif row.invalidation is not None and row.last_price < row.invalidation:
            row.status = "breakdown / long invalid"
        elif row.trigger is not None and row.last_price >= row.trigger:
            row.status = "long active"
        else:
            row.status = "near trigger / watch"
    elif row.direction == "SHORT":
        if row.target1 is not None and row.last_price <= row.target1:
            row.status = "T1 hit / trail"
        elif row.invalidation is not None and row.last_price > row.invalidation:
            row.status = "short invalid"
        elif row.trigger is not None and row.last_price <= row.trigger:
            row.status = "short active"
        else:
            row.status = "near trigger / watch"


def _lock_payload(row: TrackedSymbolState, locked_at: str) -> dict[str, Any]:
    return {
        "symbol": row.symbol,
        "direction": row.direction,
        "trigger": row.trigger,
        "invalidation": row.invalidation,
        "target1": row.target1,
        "target2": row.target2,
        "rr": row.rr,
        "strategy": row.strategy,
        "note": row.note,
        "source": row.source,
        "locked_at": locked_at,
    }


def apply_locked_setups(
    state: LiveDashboardState,
    rows: list[TrackedSymbolState],
    *,
    now: datetime,
) -> list[TrackedSymbolState]:
    current_symbols = {row.symbol for row in rows}
    for symbol in list(state.locked_setups_by_symbol):
        if symbol not in current_symbols:
            state.locked_setups_by_symbol.pop(symbol, None)

    locked_at = now.strftime("%H:%M:%S")
    for row in rows:
        if _is_invalid_status(row.status):
            state.locked_setups_by_symbol.pop(row.symbol, None)
            continue

        locked = state.locked_setups_by_symbol.get(row.symbol)
        if locked:
            row.direction = locked.get("direction") or row.direction
            row.trigger = _to_float(locked.get("trigger"))
            row.invalidation = _to_float(locked.get("invalidation"))
            row.target1 = _to_float(locked.get("target1"))
            row.target2 = _to_float(locked.get("target2"))
            row.rr = _to_float(locked.get("rr"))
            row.strategy = str(locked.get("strategy") or row.strategy)
            row.note = str(locked.get("note") or row.note)
            row.locked_setup = True
            row.locked_at = str(locked.get("locked_at") or "")
            _recompute_status_from_locked_levels(row)
            if _is_invalid_status(row.status):
                state.locked_setups_by_symbol.pop(row.symbol, None)
                row.locked_setup = False
                row.locked_at = ""
            continue

        if _is_lock_eligible(row):
            row.locked_setup = True
            row.locked_at = locked_at
            state.locked_setups_by_symbol[row.symbol] = _lock_payload(row, locked_at)
    return rows


def build_cycle_change_summary(
    tracked_symbols: list[TrackedSymbolState],
    *,
    previous_snapshot: dict[str, dict[str, Any]],
    status_changes: list[dict[str, Any]],
) -> dict[str, Any]:
    previous_symbols = set(previous_snapshot)
    current_symbols = {row.symbol for row in tracked_symbols}
    payload_by_symbol = {row.symbol: _row_payload(row) for row in tracked_symbols}
    buckets = {"forming": [], "confirmed": [], "active": []}
    for row in tracked_symbols:
        buckets[_cycle_bucket(row)].append(_row_payload(row))
    return {
        "new_added": [payload_by_symbol[symbol] for symbol in sorted(current_symbols - previous_symbols)],
        "removed": [
            {"symbol": symbol, **previous_snapshot.get(symbol, {})}
            for symbol in sorted(previous_symbols - current_symbols)
        ],
        "status_changes": status_changes,
        "forming": buckets["forming"],
        "confirmed": buckets["confirmed"],
        "active": buckets["active"],
    }


def update_live_dashboard_state(
    state: LiveDashboardState,
    *,
    market_context: str,
    tracked_symbols: list[TrackedSymbolState],
    source_health: list[str],
) -> LiveDashboardState:
    now = datetime.now()
    tracked_symbols = apply_locked_setups(state, tracked_symbols, now=now)
    previous_snapshot = dict(state.previous_snapshot_by_symbol)
    previous_symbols = set(previous_snapshot)
    current_symbols = {row.symbol for row in tracked_symbols}
    status_changes: list[dict[str, Any]] = []
    state.cycle += 1
    state.last_updated_at = now
    if _market_context_is_complete(market_context):
        state.market_context = market_context
    elif _market_context_is_complete(state.market_context):
        source_health = [
            *source_health,
            "market_context retained from previous good cycle",
        ]
    else:
        state.market_context = market_context
    state.tracked_symbols = tracked_symbols
    state.symbols = [row.symbol for row in tracked_symbols]
    state.source_health = source_health

    for row in tracked_symbols:
        previous = state.previous_zone_by_symbol.get(row.symbol)
        if previous is None:
            message = f"{row.symbol} initialized as {row.status}"
            state.events.append(LiveDashboardEvent(row.symbol, message, now.strftime("%H:%M:%S")))
        elif previous != row.status:
            message = f"{row.symbol} changed from {previous} to {row.status}"
            state.events.append(LiveDashboardEvent(row.symbol, message, now.strftime("%H:%M:%S"), "change"))
            status_changes.append({"symbol": row.symbol, "from": previous, "to": row.status})
        state.previous_zone_by_symbol[row.symbol] = row.status

    for removed in sorted(previous_symbols - current_symbols):
        previous_status = previous_snapshot.get(removed, {}).get("status", "unknown")
        state.events.append(
            LiveDashboardEvent(
                removed,
                f"{removed} removed from tracker after {previous_status}",
                now.strftime("%H:%M:%S"),
                "removed",
            )
        )

    state.cycle_changes = build_cycle_change_summary(
        tracked_symbols,
        previous_snapshot=previous_snapshot,
        status_changes=status_changes,
    )
    state.previous_snapshot_by_symbol = {
        row.symbol: {
            "status": row.status,
            "direction": row.direction,
            "last_price": row.last_price,
            "trigger": row.trigger,
            "invalidation": row.invalidation,
            "target1": row.target1,
            "rr": row.rr,
            "strategy": row.strategy,
            "locked_setup": row.locked_setup,
            "locked_at": row.locked_at,
        }
        for row in tracked_symbols
    }

    state.events = state.events[-30:]
    return state


def _key_level(row: TrackedSymbolState) -> str:
    prefix = "Locked setup: " if row.locked_setup else ""
    if row.direction == "SHORT":
        return (
            f"{prefix}Below {_fmt_num(row.trigger)} stays weak; "
            f"above {_fmt_num(row.invalidation)} invalidates; "
            f"T1 {_fmt_num(row.target1)}"
        )
    if row.direction == "LONG":
        return (
            f"{prefix}Above {_fmt_num(row.trigger)}; "
            f"T1 {_fmt_num(row.target1)}, stop {_fmt_num(row.invalidation)}"
        )
    if row.trigger is not None or row.invalidation is not None or row.target1 is not None:
        return (
            f"{prefix}Breakout above {_fmt_num(row.trigger)}; "
            f"support {_fmt_num(row.invalidation)}; "
            f"T1 {_fmt_num(row.target1)}"
        )
    return f"Watch price {_fmt_num(row.last_price)}; no active setup"


def deterministic_commentary(state: LiveDashboardState) -> str:
    lines = ["Current read from the tracker:", ""]
    for row in state.tracked_symbols[:10]:
        fno = row.fno_context or {}
        decision = row.decision_context or {}
        fno_text = ""
        if fno:
            fno_text = (
                f"; F&O {fno.get('bias', 'unknown')} "
                f"(PCR {_fmt_num(_to_float(fno.get('pcr')))}, "
                f"basis {_fmt_num(_to_float(fno.get('basis')))}, "
                f"max pain {_fmt_num(_to_float(fno.get('max_pain')))})"
            )
        decision_text = ""
        if decision:
            decision_text = (
                f"; Decision {decision.get('final_action', 'n/a')} "
                f"({decision.get('options_suitability', 'n/a')}, "
                f"score {_fmt_num(_to_float(decision.get('decision_score')), 0)})"
            )
        lines.append(f"- {row.symbol}: {row.status}; {_key_level(row)}{fno_text}{decision_text}")

    changes = state.cycle_changes or {}
    lines.extend(["", "Cycle changes:"])
    for label, key in (
        ("New added", "new_added"),
        ("Removed", "removed"),
        ("Forming", "forming"),
        ("Confirmed", "confirmed"),
        ("Active", "active"),
    ):
        names = ", ".join(item.get("symbol", "") for item in (changes.get(key) or [])[:8] if item.get("symbol"))
        lines.append(f"- {label}: {names or 'none'}")
    if changes.get("status_changes"):
        detail = "; ".join(
            f"{item.get('symbol')} {item.get('from')} -> {item.get('to')}"
            for item in changes["status_changes"][:6]
        )
        lines.append(f"- Status changes: {detail}")

    recent_changes = [e for e in state.events[-8:] if e.severity == "change"]
    if recent_changes:
        lines.extend(["", "Meaningful change:"])
        lines.extend(f"- {event.message}" for event in recent_changes[-5:])

    action_order = {
        "TRADE NOW": 0,
        "WAIT FOR RETEST": 1,
        "WATCH ONLY": 2,
        "AVOID": 4,
        "NO TRADE": 5,
        "INVALIDATED": 6,
    }
    ranked = sorted(
        state.tracked_symbols,
        key=lambda row: (
            action_order.get(str((row.decision_context or {}).get("final_action") or ""), 3),
            row.status not in {"long active", "short active", "T1 hit / trail"},
            -(_to_float((row.decision_context or {}).get("decision_score")) or 0),
            -(row.rr or 0),
        ),
    )
    lines.extend(["", "Best actionable names:"])
    if ranked:
        for idx, row in enumerate(ranked[:5], 1):
            qualifier = "valid but needs follow-through"
            decision = row.decision_context or {}
            action = str(decision.get("final_action") or "")
            if "invalid" in row.status or "breakdown" in row.status:
                qualifier = "avoid until it reclaims trigger"
            elif action in {"AVOID", "NO TRADE"}:
                qualifier = "avoid; decision gate not satisfied"
            elif action == "WAIT FOR RETEST":
                qualifier = "wait for retest / confirmation"
            elif action == "TRADE NOW":
                qualifier = "tradeable only while trigger holds"
            elif row.status == "watch":
                qualifier = "not actionable yet; wait for trigger"
            elif row.status == "T1 hit / trail":
                qualifier = "target hit once; manage trailing risk"
            lines.append(f"{idx}. {row.symbol} {row.status}, {qualifier}.")
    else:
        lines.append("1. No active tracker names yet.")

    lines.extend(["", "Watch next:"])
    lines.append(f"- Market context: {state.market_context or 'unavailable'}")
    if state.source_health:
        lines.append(f"- Source health: {' | '.join(state.source_health[:4])}")
    return "\n".join(lines)


def build_live_commentary_prompt(state: LiveDashboardState) -> list[dict[str, str]]:
    payload = {
        "market_context": state.market_context,
        "tracked_symbols": [
            {
                "symbol": row.symbol,
                "status": row.status,
                "last_price": row.last_price,
                "pct_change": row.pct_change,
                "direction": row.direction,
                "trigger": row.trigger,
                "invalidation": row.invalidation,
                "targets": [value for value in (row.target1, row.target2) if value is not None],
                "rr": row.rr,
                "strategy": row.strategy,
                "note": row.note,
                "freshness": row.freshness,
                "mtf_levels": row.mtf_levels,
                "fno_context": row.fno_context,
                "decision_context": row.decision_context,
                "locked_setup": row.locked_setup,
                "locked_at": row.locked_at,
            }
            for row in state.tracked_symbols[:12]
        ],
        "events_since_last_cycle": [event.message for event in state.events[-8:]],
        "cycle_changes": state.cycle_changes,
        "source_health": state.source_health,
        "style": "tracker commentary, concise, level-specific, no investment advice",
    }
    system = (
        "You are Agent Adda's terminal live dashboard narrator. Write tracker commentary "
        "in the user's attached style. Use only supplied evidence. Be level-specific. "
        "Separate: Current read from the tracker, Cycle changes, Meaningful change, Best actionable names, Watch next. "
        "Include the decision_context final_action and options_suitability when available; explain conflicts between market regime, F&O, volume, and trigger state. "
        "In Cycle changes explicitly cover new added, removed, forming, confirmed, and active. "
        "Do not provide investment advice."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
    ]


def generate_live_commentary(state: LiveDashboardState, backend, use_llm: bool = True) -> str:
    if not use_llm or backend is None:
        return deterministic_commentary(state)
    try:
        response = backend.chat(build_live_commentary_prompt(state), tools=None)
        content = str((response or {}).get("content") or "").strip()
        return content or deterministic_commentary(state)
    except Exception:
        return deterministic_commentary(state)


def fetch_live_dashboard_cycle(config: LiveDashboardConfig) -> dict[str, Any]:
    source_health: list[str] = []
    quote_source_mode = _configured_source_mode("AGENT_ADDA_QUOTE_SOURCE", "AGENT_ADDA_INTRADAY_QUOTE_SOURCE")
    ohlcv_source_mode = _configured_source_mode(
        "AGENT_ADDA_INTRADAY_OHLCV_SOURCE",
        "AGENT_ADDA_INTRADAY_QUOTE_SOURCE",
        "AGENT_ADDA_QUOTE_SOURCE",
    )
    if quote_source_mode != "auto":
        source_health.append(f"quote_source={quote_source_mode}")
    if ohlcv_source_mode != "auto":
        source_health.append(f"ohlcv_source={ohlcv_source_mode}")

    try:
        overview = get_live_market_overview()
        if _overview_has_core_indices(overview):
            source_health.append("get_live_market_overview ok")
        else:
            source_health.append("get_live_market_overview incomplete")
            try:
                retry_overview = get_live_market_overview()
                if _overview_has_core_indices(retry_overview):
                    overview = retry_overview
                    source_health.append("get_live_market_overview retry ok")
                else:
                    overview, fallback_notes = _fill_market_overview_from_index_snapshots(overview)
                    if fallback_notes:
                        source_health.append("market_context fallback: " + "; ".join(fallback_notes))
            except Exception as retry_exc:
                overview, fallback_notes = _fill_market_overview_from_index_snapshots(overview)
                source_health.append(f"get_live_market_overview retry error: {retry_exc}")
                if fallback_notes:
                    source_health.append("market_context fallback: " + "; ".join(fallback_notes))
    except Exception as exc:
        overview = {}
        source_health.append(f"get_live_market_overview error: {exc}")
        overview, fallback_notes = _fill_market_overview_from_index_snapshots(overview)
        if fallback_notes:
            source_health.append("market_context fallback: " + "; ".join(fallback_notes))

    try:
        movers = get_top_gainers_losers(index="NIFTY 500", top_n=8, direction="both")
        source_health.append("get_top_gainers_losers ok")
    except Exception as exc:
        movers = {}
        source_health.append(f"get_top_gainers_losers error: {exc}")

    symbols = _normalise_symbols(config.symbols)
    if not symbols:
        symbols = _normalise_symbols(_symbols_from_movers(movers)[:6] + DEFAULT_TRACKER_SYMBOLS)
    symbols = symbols[: max(1, config.top_n)]

    try:
        quotes = get_nse_quotes(symbols)
        quote_map = quotes.get("quotes") or {}
        quote_freshness = str(quotes.get("as_of") or "")
        quote_source = str(quotes.get("source") or "").strip()
        source_health.append(f"get_nse_quotes ok: {quote_source}" if quote_source else "get_nse_quotes ok")
    except Exception as exc:
        quote_map = {}
        quote_freshness = ""
        source_health.append(f"get_nse_quotes error: {exc}")

    try:
        scan = scan_symbols_intraday(
            symbols=symbols,
            interval=config.interval,
            strategies=config.strategies,
            top_n=max(config.top_n, len(symbols)),
        )
        source_health.append("scan_symbols_intraday ok")
    except Exception as exc:
        scan = {}
        source_health.append(f"scan_symbols_intraday error: {exc}")

    tracked = [
        build_tracked_symbol(symbol, quote_map.get(symbol, {}), _best_signal_for_symbol(symbol, scan, config), quote_freshness)
        for symbol in symbols
    ]
    return {
        "market_context": _market_context(overview),
        "tracked_symbols": tracked,
        "source_health": source_health,
        "overview": overview,
        "movers": movers,
    }


def render_live_dashboard(state: LiveDashboardState):
    table = Table(
        title="Current read from the tracker",
        box=box.SIMPLE_HEAD,
        expand=True,
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("Symbol", style="bold cyan", no_wrap=True)
    table.add_column("Read", justify="center", no_wrap=True)
    table.add_column("LTP", justify="right", no_wrap=True)
    table.add_column("Chg", justify="right", no_wrap=True)
    table.add_column("F&O", justify="left", no_wrap=True)
    table.add_column("Trigger", justify="right", no_wrap=True)
    table.add_column("Stop", justify="right", no_wrap=True)
    table.add_column("T1/RR", justify="right", no_wrap=True)
    for row in state.tracked_symbols[:12]:
        target = _fmt_level(row.target1)
        if row.rr is not None:
            target = f"{target}/{_fmt_num(row.rr, 1)}R"
        table.add_row(
            row.symbol,
            _compact_read(row),
            Text(_fmt_level(row.last_price), style="bold white"),
            Text(_fmt_pct_compact(row.pct_change), style=_pct_style(row.pct_change)),
            _fno_compact(row),
            Text(_fmt_level(row.trigger), style="cyan"),
            Text(_fmt_level(row.invalidation), style="red" if row.invalidation is not None else "dim"),
            Text(target, style="green" if row.target1 is not None else "dim"),
        )

    header = Text()
    header.append(f"Cycle {state.cycle}", style="bold bright_blue")
    header.append(" | ", style="dim")
    header.append((state.last_updated_at or state.started_at).strftime("%Y-%m-%d %H:%M:%S"), style="bold white")
    header.append(" | ", style="dim")
    header.append_text(_styled_market_context(state.market_context))
    source = " | ".join(state.source_health[:5]) or "sources pending"
    commentary = state.last_commentary or deterministic_commentary(state)
    return Group(
        Panel(header, title="Agent Adda Live Commentary Dashboard", border_style="bright_blue"),
        table,
        Panel(_cycle_changes_text(state.cycle_changes or {}), title="Cycle Changes", border_style="yellow"),
        Panel(_styled_commentary(commentary), title="Narrative / Commentary", border_style="bright_green"),
        Panel(Text(source, style="dim green" if "error" not in source.lower() else "bold red"), title="Source Health", border_style="dim"),
    )


def run_live_commentary_dashboard(config: LiveDashboardConfig, *, backend=None, console=None) -> LiveDashboardState:
    from rich.console import Console

    con = console or Console(highlight=False, force_terminal=True)
    state = LiveDashboardState()

    def tick() -> None:
        nonlocal state
        cycle = fetch_live_dashboard_cycle(config)
        state = update_live_dashboard_state(
            state,
            market_context=cycle["market_context"],
            tracked_symbols=cycle["tracked_symbols"],
            source_health=cycle["source_health"],
        )
        state.last_commentary = generate_live_commentary(state, backend, use_llm=config.use_llm)

    tick()
    if config.max_cycles == 1:
        con.print(render_live_dashboard(state))
        return state

    cycles_done = 1
    with Live(render_live_dashboard(state), console=con, screen=True, auto_refresh=False, transient=False) as live:
        while True:
            if config.max_cycles is not None and cycles_done >= config.max_cycles:
                return state
            try:
                time.sleep(max(1, config.refresh_secs))
                tick()
                cycles_done += 1
                live.update(render_live_dashboard(state), refresh=True)
            except KeyboardInterrupt:
                return state


__all__ = [
    "LiveDashboardConfig",
    "LiveDashboardEvent",
    "LiveDashboardState",
    "TrackedSymbolState",
    "build_cycle_change_summary",
    "build_mtf_level_context",
    "build_live_commentary_prompt",
    "deterministic_commentary",
    "enrich_tracked_symbols_with_mtf_levels",
    "fetch_live_dashboard_cycle",
    "generate_live_commentary",
    "render_live_dashboard",
    "run_live_commentary_dashboard",
    "style_direction",
    "style_status",
    "update_live_dashboard_state",
]
