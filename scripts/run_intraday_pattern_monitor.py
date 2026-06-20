#!/usr/bin/env python3
"""Poll intraday VCP, breakout, and retest setups for a symbol basket."""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from terminal.tools import run_intraday_screener  # noqa: E402


DEFAULT_SYMBOLS = [
    "BANKBARODA",
    "CGPOWER",
    "RBLBANK",
    "IDFCFIRSTB",
    "DELHIVERY",
    "RECLTD",
    "TATAPOWER",
    "TRENT",
    "SIEMENS",
    "DIXON",
    "BEL",
    "INDUSINDBK",
]

LOG_DIR = PROJECT_ROOT / "logs"
LATEST_PATH = LOG_DIR / "intraday_pattern_monitor_latest.md"
PID_PATH = LOG_DIR / "intraday_pattern_monitor.pid"


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _fmt(value: Any, digits: int = 2) -> str:
    number = _float(value)
    if number is None:
        return "n/a"
    if abs(number) >= 1000:
        return f"{number:,.0f}"
    return f"{number:,.{digits}f}"


def _scan(screen_type: str, timeframe: str, symbols: list[str], min_score: float) -> dict:
    return run_intraday_screener(
        screen_type=screen_type,
        timeframe=timeframe,
        symbols=symbols,
        min_score=min_score,
        top_n=max(len(symbols), 20),
    )


def _row_key(row: dict, timeframe: str, kind: str) -> tuple[str, str, str]:
    return (str(row.get("symbol", "")).upper(), timeframe, kind)


def _event_from_row(row: dict, timeframe: str, kind: str, note: str) -> dict:
    return {
        "symbol": str(row.get("symbol", "")).upper(),
        "timeframe": timeframe,
        "kind": kind,
        "price": _float(row.get("price")),
        "score": row.get("score"),
        "setup": row.get("setup_label"),
        "side": row.get("setup_side"),
        "rsi": row.get("rsi"),
        "support": _float(row.get("support")),
        "resistance": _float(row.get("resistance")),
        "invalidation": _float(row.get("invalidation_level")),
        "targets": row.get("technical_target_zones"),
        "freshness": row.get("freshness"),
        "note": note,
    }


def _parse_freshness(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def _is_fresh_row(row: dict, max_age_min: int) -> bool:
    if max_age_min <= 0:
        return True
    fresh_at = _parse_freshness(row.get("freshness"))
    if fresh_at is None:
        return True
    age_secs = (datetime.now() - fresh_at).total_seconds()
    return age_secs <= max_age_min * 60


def _retest_events(rows: list[dict], timeframe: str, tolerance_pct: float) -> list[dict]:
    events: list[dict] = []
    for row in rows:
        price = _float(row.get("price"))
        support = _float(row.get("support"))
        resistance = _float(row.get("resistance"))
        if price is None or price <= 0:
            continue

        side = str(row.get("setup_side") or row.get("setup_label") or "").upper()
        if support is not None:
            distance = (price - support) / price
            if 0 <= distance <= tolerance_pct and ("LONG" in side or "WATCH" in side):
                events.append(
                    _event_from_row(
                        row,
                        timeframe,
                        "support_retest",
                        f"Holding near support; distance {distance * 100:.2f}%",
                    )
                )

        if resistance is not None:
            distance = (price - resistance) / price
            if 0 <= distance <= tolerance_pct:
                events.append(
                    _event_from_row(
                        row,
                        timeframe,
                        "breakout_retest",
                        f"Holding above breakout/resistance; distance {distance * 100:.2f}%",
                    )
                )
            elif -tolerance_pct <= distance < 0 and ("LONG" in side or "WATCH" in side):
                events.append(
                    _event_from_row(
                        row,
                        timeframe,
                        "pre_breakout_retest",
                        f"Testing resistance from below; distance {abs(distance) * 100:.2f}%",
                    )
                )
    return events


def collect_cycle(
    symbols: list[str],
    timeframes: list[str],
    min_score: float,
    tolerance_pct: float,
    max_age_min: int,
) -> dict:
    cycle = {
        "as_of": _now_text(),
        "symbols": symbols,
        "timeframes": timeframes,
        "events": [],
        "sources": [],
        "errors": [],
    }

    for timeframe in timeframes:
        for screen_type in ("vcp", "breakouts", "levels"):
            result = _scan(screen_type, timeframe, symbols, min_score)
            cycle["sources"].append(
                {
                    "screen_type": screen_type,
                    "timeframe": timeframe,
                    "source": result.get("source") or result.get("data_source"),
                    "data_mode": result.get("data_mode"),
                    "scanned": result.get("scanned"),
                    "count": result.get("count"),
                }
            )
            if result.get("error"):
                cycle["errors"].append({"screen_type": screen_type, "timeframe": timeframe, "error": result["error"]})
                continue
            rows = result.get("results") or []
            if not isinstance(rows, list):
                continue
            rows = [row for row in rows if _is_fresh_row(row, max_age_min)]

            if screen_type == "vcp":
                for row in rows:
                    cycle["events"].append(_event_from_row(row, timeframe, "vcp", "VCP/tight-range candidate"))
            elif screen_type == "breakouts":
                for row in rows:
                    cycle["events"].append(_event_from_row(row, timeframe, "breakout", "Breakout candidate"))
            elif screen_type == "levels":
                cycle["events"].extend(_retest_events(rows, timeframe, tolerance_pct))

    cycle["events"] = sorted(
        cycle["events"],
        key=lambda item: (
            item.get("symbol") or "",
            item.get("timeframe") or "",
            item.get("kind") or "",
        ),
    )
    return cycle


def _is_changed(event: dict, previous: dict | None, price_move_pct: float) -> bool:
    if previous is None:
        return True
    if event.get("setup") != previous.get("setup") or event.get("side") != previous.get("side"):
        return True
    price = _float(event.get("price"))
    prev_price = _float(previous.get("price"))
    if price is None or prev_price is None or prev_price == 0:
        return False
    return abs(price - prev_price) / prev_price >= price_move_pct


def render_markdown(cycle: dict, changed: list[dict]) -> str:
    lines = [
        f"# Intraday Pattern Monitor",
        "",
        f"As of: {cycle['as_of']} IST",
        f"Symbols: {', '.join(cycle['symbols'])}",
        f"Timeframes: {', '.join(cycle['timeframes'])}",
        "",
        "## New Or Changed Alerts",
    ]
    if not changed:
        lines.append("No new or materially changed alerts this cycle.")
    else:
        lines.append("| Symbol | TF | Pattern | Price | Score | RSI | Support | Resistance | Note |")
        lines.append("|---|---:|---|---:|---:|---:|---:|---:|---|")
        for item in changed:
            lines.append(
                "| {symbol} | {timeframe} | {kind} | {price} | {score} | {rsi} | {support} | {resistance} | {note} |".format(
                    symbol=item.get("symbol", ""),
                    timeframe=item.get("timeframe", ""),
                    kind=item.get("kind", ""),
                    price=_fmt(item.get("price")),
                    score=_fmt(item.get("score"), 0),
                    rsi=_fmt(item.get("rsi"), 1),
                    support=_fmt(item.get("support")),
                    resistance=_fmt(item.get("resistance")),
                    note=str(item.get("note") or ""),
                )
            )

    lines.extend(["", "## Full Current State"])
    if not cycle["events"]:
        lines.append("No active VCP, breakout, or retest rows in the current scan.")
    else:
        lines.append("| Symbol | TF | Pattern | Price | Score | RSI | Support | Resistance | Freshness |")
        lines.append("|---|---:|---|---:|---:|---:|---:|---:|---|")
        for item in cycle["events"]:
            lines.append(
                "| {symbol} | {timeframe} | {kind} | {price} | {score} | {rsi} | {support} | {resistance} | {freshness} |".format(
                    symbol=item.get("symbol", ""),
                    timeframe=item.get("timeframe", ""),
                    kind=item.get("kind", ""),
                    price=_fmt(item.get("price")),
                    score=_fmt(item.get("score"), 0),
                    rsi=_fmt(item.get("rsi"), 1),
                    support=_fmt(item.get("support")),
                    resistance=_fmt(item.get("resistance")),
                    freshness=str(item.get("freshness") or ""),
                )
            )

    if cycle.get("errors"):
        lines.extend(["", "## Errors"])
        for error in cycle["errors"]:
            lines.append(f"- {error}")

    lines.extend(["", "Research only. Not investment advice."])
    return "\n".join(lines) + "\n"


def _install_pid_file() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if PID_PATH.exists():
        old_pid_text = PID_PATH.read_text(encoding="utf-8").strip()
        try:
            old_pid = int(old_pid_text)
            os.kill(old_pid, 0)
        except (ValueError, ProcessLookupError, PermissionError):
            pass
        else:
            raise SystemExit(f"monitor already appears to be running with pid {old_pid}")
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")


def _remove_pid_file() -> None:
    try:
        if PID_PATH.read_text(encoding="utf-8").strip() == str(os.getpid()):
            PID_PATH.unlink()
    except FileNotFoundError:
        pass


def run(args: argparse.Namespace) -> int:
    symbols = [item.strip().upper() for item in args.symbols.split(",") if item.strip()]
    timeframes = [item.strip() for item in args.timeframes.split(",") if item.strip()]
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    jsonl_path = LOG_DIR / f"intraday_pattern_monitor_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    _install_pid_file()

    stop = {"value": False}

    def _handle_stop(_signum: int, _frame: Any) -> None:
        stop["value"] = True

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    previous: dict[tuple[str, str, str], dict] = {}
    cycles_done = 0
    print(f"[{_now_text()}] monitor started pid={os.getpid()} log={jsonl_path}", flush=True)
    try:
        while not stop["value"]:
            cycle = collect_cycle(
                symbols,
                timeframes,
                args.min_score,
                args.retest_tolerance_pct / 100.0,
                args.max_age_min,
            )
            changed = []
            current: dict[tuple[str, str, str], dict] = {}
            for event in cycle["events"]:
                key = _row_key(event, event["timeframe"], event["kind"])
                current[key] = event
                if _is_changed(event, previous.get(key), args.price_change_pct / 100.0):
                    changed.append(event)
            previous = current

            record = {"cycle": cycle, "changed": changed}
            with jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, default=str, separators=(",", ":")) + "\n")
            LATEST_PATH.write_text(render_markdown(cycle, changed), encoding="utf-8")
            print(
                f"[{cycle['as_of']}] scanned={len(symbols)} events={len(cycle['events'])} changed={len(changed)}",
                flush=True,
            )

            cycles_done += 1
            if args.cycles and cycles_done >= args.cycles:
                break
            for _ in range(args.interval_secs):
                if stop["value"]:
                    break
                time.sleep(1)
    finally:
        _remove_pid_file()
        print(f"[{_now_text()}] monitor stopped", flush=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--timeframes", default="5m,15m")
    parser.add_argument("--interval-secs", type=int, default=180)
    parser.add_argument("--cycles", type=int, default=0, help="0 means run until stopped")
    parser.add_argument("--min-score", type=float, default=55)
    parser.add_argument("--retest-tolerance-pct", type=float, default=0.35)
    parser.add_argument("--price-change-pct", type=float, default=0.15)
    parser.add_argument("--max-age-min", type=int, default=90, help="Ignore rows with stale freshness; 0 disables")
    args = parser.parse_args()
    if args.cycles <= 0:
        args.cycles = 0
    return args


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
