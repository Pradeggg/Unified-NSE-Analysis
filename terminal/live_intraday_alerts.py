"""Running intraday F&O commentary with trigger-based email alerts."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
import argparse
import html
import json
import os
from pathlib import Path
import re
import time
from typing import Any

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from terminal.email_dispatcher import _email_provider, _load_recipients, send_via_outlook
from terminal.edge_knowledge import fetch_edge_memory_rows
from terminal.market_calendar import MarketSessionStatus, market_session_status
from terminal.live_dashboard import (
    LiveDashboardConfig,
    LiveDashboardState,
    TrackedSymbolState,
    apply_trade_decisions,
    enrich_tracked_symbols_with_fno_context,
    enrich_tracked_symbols_with_mtf_levels,
    fetch_live_dashboard_cycle,
    generate_live_commentary,
    _to_float,
    update_live_dashboard_state,
)
from terminal.options_strategy_selector import select_options_strategy


DEFAULT_FNO_INTRADAY_UNIVERSE = [
    "NIFTY",
    "BANKNIFTY",
    "FINNIFTY",
    "MIDCPNIFTY",
    "BEL",
    "TRENT",
    "DIXON",
    "SCHNEIDER",
    "INDUSINDBK",
    "NESTLEIND",
    "ICICIBANK",
    "MCX",
    "RELIANCE",
    "HDFCBANK",
    "SBIN",
    "ADANIENT",
    "TCS",
    "AXISBANK",
    "KOTAKBANK",
    "LT",
    "BHARTIARTL",
    "TATASTEEL",
    "HINDALCO",
    "BAJFINANCE",
    "INFY",
]
INDEX_UNDERLYINGS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}

ROOT = Path(__file__).resolve().parent.parent
FNO_CACHE_DIR = ROOT / "data" / "_fno_cache"
LOG_DIR = ROOT / "logs"
INTRADAY_ALERT_STATE_SCHEMA_VERSION = 1
DEFAULT_BREAKOUT_STRATEGIES = [
    "supertrend_breakout",
    "near_breakout_volume",
    "vcp",
    "volume",
    "darvas",
    "orb_vwap",
]
OPENING_DRIVE_STRATEGIES = {"orb_vwap"}


def default_intraday_alert_state_path() -> Path:
    raw_path = os.environ.get("AGENT_ADDA_INTRADAY_ALERT_STATE_PATH")
    if raw_path:
        return Path(raw_path).expanduser()
    return Path.home() / ".agent_adda" / "intraday_alerts_state.json"


def load_intraday_alert_symbols(path: Path | str | None = None) -> list[str]:
    state_path = Path(path).expanduser() if path else default_intraday_alert_state_path()
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    symbols = payload.get("symbols", [])
    if not isinstance(symbols, list):
        return []
    return list(dict.fromkeys(
        str(symbol).strip().upper()
        for symbol in symbols
        if str(symbol).strip()
    ))


def save_intraday_alert_symbols(symbols: list[str], path: Path | str | None = None) -> Path:
    state_path = Path(path).expanduser() if path else default_intraday_alert_state_path()
    clean_symbols = list(dict.fromkeys(
        str(symbol).strip().upper()
        for symbol in symbols
        if str(symbol).strip()
    ))
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schema_version": INTRADAY_ALERT_STATE_SCHEMA_VERSION,
                "symbols": clean_symbols,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return state_path


def clear_intraday_alert_symbols(path: Path | str | None = None) -> None:
    state_path = Path(path).expanduser() if path else default_intraday_alert_state_path()
    try:
        state_path.unlink()
    except FileNotFoundError:
        return


def _equity_alert_symbols(symbols: list[str]) -> list[str]:
    return [
        symbol
        for symbol in symbols
        if str(symbol).strip().upper() not in INDEX_UNDERLYINGS
    ]


def load_fno_intraday_universe() -> list[str]:
    """Load the latest local F&O underlying universe.

    Falls back to the curated list when the cache is absent or malformed. The
    cache path is intentionally local because this monitor must start quickly
    during market hours and should not depend on a slow network lookup.
    """
    try:
        files = sorted(
            path for path in FNO_CACHE_DIR.glob("fo_bhav_*.csv")
            if re.fullmatch(r"fo_bhav_\d{8}\.csv", path.name)
        )
        if not files:
            return list(DEFAULT_FNO_INTRADAY_UNIVERSE)
        latest = files[-1]
        import pandas as pd

        df = pd.read_csv(latest, usecols=lambda col: str(col).upper() in {"SYMBOL", "INSTRUMENT"})
        if "SYMBOL" not in df.columns:
            return list(DEFAULT_FNO_INTRADAY_UNIVERSE)
        if "INSTRUMENT" in df.columns:
            df = df[df["INSTRUMENT"].astype(str).str.upper().isin({"STF", "STO", "FUTSTK", "OPTSTK", "FUTIDX", "OPTIDX"})]
        symbols = [
            str(symbol).strip().upper()
            for symbol in df["SYMBOL"].dropna().unique().tolist()
            if str(symbol).strip()
        ]
        merged = list(dict.fromkeys([*DEFAULT_FNO_INTRADAY_UNIVERSE, *symbols]))
        return merged or list(DEFAULT_FNO_INTRADAY_UNIVERSE)
    except Exception:
        return list(DEFAULT_FNO_INTRADAY_UNIVERSE)


@dataclass
class IntradayAlertConfig:
    symbols: list[str] = field(default_factory=load_fno_intraday_universe)
    interval_secs: int = 60
    cycles: int | None = None
    candle_interval: str = "15m"
    min_rr: float = 2.0
    trigger: str = "active_or_near"
    report_key: str = "intraday_alerts"
    send: bool = False
    dry_run: bool = False
    use_llm: bool = True
    email_every_mins: int = 0
    rescan_every_mins: int = 0
    max_tracked_symbols: int = 15
    strategies: list[str] = field(default_factory=lambda: list(DEFAULT_BREAKOUT_STRATEGIES))
    require_volume: bool = True
    min_volume_ratio: float = 1.2
    include_fno: bool = True
    remember_symbols: bool = True
    state_path: Path | None = None
    write_cycle_log: bool = True
    log_path: Path | None = None
    latest_snapshot_path: Path | None = None
    include_edge_memory: bool = True


@dataclass(frozen=True)
class AlertCandidate:
    symbol: str
    side: str
    status: str
    last_price: float | None
    pct_change: float | None
    trigger: float | None
    stop: float | None
    target: float | None
    rr: float | None
    strategy: str
    note: str
    decision: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.symbol, self.side, self.status)


def _fmt(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except Exception:
        return str(value)
    if abs(number) >= 1000:
        return f"{number:,.0f}"
    return f"{number:,.{decimals}f}"


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):+.1f}%"
    except Exception:
        return str(value)


def _fmt_compact(value: Any, decimals: int = 2) -> str:
    text = _fmt(value, decimals)
    return text.replace(",", "")


def _option_direction(row: TrackedSymbolState) -> str | None:
    if row.direction == "LONG":
        return "bullish"
    if row.direction == "SHORT":
        return "bearish"
    return None


def _option_type_for_direction(direction: str | None) -> str:
    return "PE" if direction == "bearish" else "CE"


def _no_options_trade(row: TrackedSymbolState, status: str, reasons: list[str] | tuple[str, ...]) -> dict[str, Any]:
    result = {
        "status": status,
        "verdict": "NO OPTIONS TRADE",
        "option_type": _option_type_for_direction(_option_direction(row)),
        "strike": None,
        "premium": None,
        "breakeven": None,
        "expiry": None,
        "dte": None,
        "iv_pct": None,
        "delta": None,
        "gamma": None,
        "theta_per_day": None,
        "vega": None,
        "expected_move": None,
        "oi_wall": "n/a",
        "premium_stop": None,
        "premium_target": None,
        "underlying_target": row.target1,
        "reasons": [str(item) for item in reasons if str(item)],
    }
    result["strategy"] = select_options_strategy(symbol=row.symbol, direction=row.direction, execution=result)
    return result


def _first_strike_profile(analysis: dict[str, Any]) -> dict[str, Any]:
    recommended = analysis.get("recommended_strikes") or []
    if recommended:
        return dict(recommended[0])
    profiles = ((analysis.get("strike_guide") or {}).get("strike_profiles") or [])
    for profile in profiles:
        if profile.get("is_recommended"):
            return dict(profile)
    for profile in profiles:
        if str(profile.get("label") or "").upper() == "ATM":
            return dict(profile)
    return dict(profiles[0]) if profiles else {}


def _option_wall_text(analysis: dict[str, Any], option_type: str) -> str:
    oi_context = analysis.get("oi_context") or {}
    if option_type == "PE":
        walls = oi_context.get("support_walls") or []
        if walls:
            return "PE wall " + ", ".join(_fmt_compact(item.get("strike"), 0) for item in walls[:2])
    walls = oi_context.get("resistance_walls") or []
    if walls:
        return "CE wall " + ", ".join(_fmt_compact(item.get("strike"), 0) for item in walls[:2])
    note = str(oi_context.get("note") or "").strip()
    return note[:80] if note else "n/a"


def _normalise_options_execution(
    row: TrackedSymbolState,
    analysis: dict[str, Any],
    *,
    direction: str,
) -> dict[str, Any]:
    if analysis.get("error"):
        return _no_options_trade(row, "missing_evidence", [analysis.get("error")])

    verdict = analysis.get("verdict") or {}
    verdict_label = str(verdict.get("label") or "").upper()
    strike_guide = analysis.get("strike_guide") or {}
    profile = _first_strike_profile(analysis)
    option_type = str(profile.get("option_type") or strike_guide.get("option_type") or _option_type_for_direction(direction)).upper()

    if "STRONG BUY" in verdict_label or "GOOD BUYING" in verdict_label:
        normalized_verdict = f"BUY {option_type}"
    elif "USE SPREAD" in verdict_label:
        normalized_verdict = "USE SPREAD"
    elif "SELECTIVE" in verdict_label:
        normalized_verdict = "USE SPREAD"
    else:
        normalized_verdict = "NO OPTIONS TRADE"

    premium = profile.get("ltp")
    try:
        premium_number = float(premium) if premium is not None else None
    except (TypeError, ValueError):
        premium_number = None
    premium_stop = round(premium_number * 0.5, 2) if premium_number is not None else None
    premium_target = (
        f"{_fmt_compact(premium_number * 1.5, 2)}-{_fmt_compact(premium_number * 1.8, 2)}"
        if premium_number is not None
        else None
    )

    expected = strike_guide.get("expected_move") or analysis.get("expected_move") or {}
    reasons = [str(item) for item in (verdict.get("reasons") or [])[:4]]
    if profile.get("recommendation"):
        reasons.append(str(profile.get("recommendation")))

    result = {
        "status": "ok" if normalized_verdict != "NO OPTIONS TRADE" else "no_trade",
        "verdict": normalized_verdict,
        "raw_verdict": verdict.get("label"),
        "option_type": option_type,
        "moneyness": profile.get("label"),
        "strike": profile.get("strike"),
        "premium": premium,
        "breakeven": profile.get("breakeven"),
        "expiry": analysis.get("expiry"),
        "dte": analysis.get("dte"),
        "iv_pct": strike_guide.get("atm_iv") or (analysis.get("iv_summary") or {}).get("atm_iv"),
        "delta": profile.get("delta"),
        "gamma": profile.get("gamma"),
        "theta_per_day": profile.get("theta_per_day"),
        "vega": profile.get("vega"),
        "expected_move": expected.get("expected_move_1sd"),
        "expected_upper": expected.get("upper_1sd"),
        "expected_lower": expected.get("lower_1sd"),
        "oi_wall": _option_wall_text(analysis, option_type),
        "premium_stop": premium_stop,
        "premium_target": premium_target,
        "underlying_target": row.target1,
        "reasons": reasons,
        "source": analysis.get("source"),
    }
    result["strategy"] = select_options_strategy(symbol=row.symbol, direction=row.direction, execution=result)
    return result


def apply_options_execution_to_tracked_symbols(
    rows: list[TrackedSymbolState],
    *,
    analyzer=None,
) -> list[TrackedSymbolState]:
    """Attach a compact options-execution verdict to each tracked row.

    This is deliberately separate from the directional alert decision. It
    answers whether an options instrument is tradeable, not whether the
    underlying setup exists.
    """
    if analyzer is None:
        from terminal.tools import analyze_options_buying as analyzer

    for row in rows:
        decision = dict(row.decision_context or {})
        direction = _option_direction(row)
        if direction is None:
            decision["options_execution"] = _no_options_trade(row, "not_directional", ["row is not LONG or SHORT"])
            row.decision_context = decision
            continue

        final_action = str(decision.get("final_action") or "").upper()
        if final_action in {"AVOID", "NO TRADE", "INVALIDATED"}:
            decision["options_execution"] = _no_options_trade(row, "decision_blocked", [f"decision gate is {final_action}"])
            row.decision_context = decision
            continue

        fno = row.fno_context or {}
        missing = [str(item) for item in (fno.get("missing_evidence") or []) if str(item)]
        if fno.get("status") != "ok" or missing:
            reasons = missing or [f"F&O status {fno.get('status', 'missing')}"]
            decision["options_execution"] = _no_options_trade(row, "missing_evidence", reasons)
            row.decision_context = decision
            continue

        try:
            analysis = analyzer(row.symbol, direction)
        except Exception as exc:
            decision["options_execution"] = _no_options_trade(row, "analysis_error", [str(exc)])
            row.decision_context = decision
            continue

        decision["options_execution"] = _normalise_options_execution(row, analysis or {}, direction=direction)
        row.decision_context = decision
    return rows


def _options_execution(row: TrackedSymbolState) -> dict[str, Any]:
    execution = (row.decision_context or {}).get("options_execution")
    if isinstance(execution, dict) and execution:
        return execution
    return _no_options_trade(row, "not_assessed", ["options analysis not run"])


def _md_cell(value: Any) -> str:
    if value is None:
        return "n/a"
    text = str(value).strip()
    return (text or "n/a").replace("|", "/")


def _options_expiry_text(execution: dict[str, Any]) -> str:
    expiry = execution.get("expiry") or "n/a"
    dte = execution.get("dte")
    if dte is None:
        return str(expiry)
    return f"{expiry} / {dte}D"


def _options_greek_text(execution: dict[str, Any]) -> str:
    delta = _fmt(execution.get("delta"), 2)
    theta = _fmt(execution.get("theta_per_day"), 2)
    return f"{delta} / {theta}"


def _options_notes(execution: dict[str, Any], *, limit: int = 2) -> str:
    reasons = [str(item) for item in (execution.get("reasons") or []) if str(item)]
    if not reasons and execution.get("raw_verdict"):
        reasons = [str(execution["raw_verdict"])]
    return "; ".join(reasons[:limit]) or "n/a"


def _options_strategy_text(execution: dict[str, Any]) -> str:
    strategy = execution.get("strategy") or {}
    if not isinstance(strategy, dict):
        return "n/a"
    structure = str(strategy.get("structure") or "n/a").strip()
    verdict = str(strategy.get("verdict") or "").strip()
    return f"{structure} ({verdict})" if verdict and structure != "n/a" else structure


def _terminal_clean_text(value: Any) -> str:
    text = str(value or "")
    replacements = {
        "\u26a0\ufe0f": "Warn:",
        "\u26a0": "Warn:",
        "\u2705": "OK:",
        "\u274c": "Avoid:",
        "\ufe0f": "",
        "\u2014": "-",
        "\u2013": "-",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text).strip()


def _options_execution_terminal_table(rows: list[TrackedSymbolState], *, limit: int = 10) -> Table:
    table = Table(
        expand=True,
        box=box.SIMPLE_HEAVY,
        header_style="bold magenta",
        padding=(0, 0),
    )
    table.add_column("Symbol", style="bold cyan", no_wrap=True)
    table.add_column("Verdict / Strategy", overflow="fold", min_width=24, ratio=3)
    table.add_column("Contract", no_wrap=True)
    table.add_column("Strike\nPrem", justify="right", no_wrap=True)
    table.add_column("BE / DTE", justify="right", no_wrap=True)
    table.add_column("IV", justify="right", no_wrap=True)
    table.add_column("D/Theta", justify="right", no_wrap=True)
    table.add_column("OI Wall", overflow="fold", ratio=1)

    for row in rows[:limit]:
        execution = _options_execution(row)
        verdict = str(execution.get("verdict") or "NO OPTIONS TRADE")
        verdict_style = "bold green" if verdict.startswith("BUY") else "bold yellow" if verdict == "USE SPREAD" else "bold red"
        strategy_text = _terminal_clean_text(_options_strategy_text(execution))
        verdict_cell = Text(verdict, style=verdict_style)
        if strategy_text and strategy_text != "n/a":
            verdict_cell.append("\n")
            verdict_cell.append(strategy_text)
        contract = " ".join(
            part
            for part in (
                str(execution.get("option_type") or _option_type_for_direction(_option_direction(row))),
                str(execution.get("moneyness") or "").strip(),
            )
            if part
        )
        be_dte = f"{_fmt(execution.get('breakeven'))}\n{_options_expiry_text(execution)}"
        greeks = f"{_fmt(execution.get('delta'), 2)}\n{_fmt(execution.get('theta_per_day'), 2)}"
        strike_premium = f"{_fmt(execution.get('strike'))}\n{_fmt(execution.get('premium'))}"
        table.add_row(
            row.symbol,
            verdict_cell,
            contract or "n/a",
            strike_premium,
            be_dte,
            _fmt(execution.get("iv_pct"), 1),
            greeks,
            _terminal_clean_text(execution.get("oi_wall") or "n/a"),
        )

    if not rows:
        table.add_row("n/a", "NO OPTIONS TRADE\nNo options structure", "n/a", "n/a", "n/a", "n/a", "n/a", "No alert-qualified option rows.")
    return table


def build_options_execution_section(rows: list[TrackedSymbolState], *, limit: int = 30) -> str:
    """Markdown section for the separate options-execution overlay."""
    lines = [
        "## Options Execution",
        "",
        "| Symbol | Verdict | Strategy | Option | Strike | Premium | Breakeven | Exp/DTE | IV | Delta/Theta | Expected Move | OI Wall | Notes |",
        "|---|---|---|---|---:|---:|---:|---|---:|---|---:|---|---|",
    ]
    for row in rows[:limit]:
        execution = _options_execution(row)
        option_parts = [
            str(execution.get("option_type") or _option_type_for_direction(_option_direction(row))),
            str(execution.get("moneyness") or "").strip(),
        ]
        option_text = " ".join(part for part in option_parts if part)
        lines.append(
            f"| {row.symbol} | {_md_cell(execution.get('verdict'))} | {_md_cell(_options_strategy_text(execution))} | {_md_cell(option_text)} | "
            f"{_fmt(execution.get('strike'))} | {_fmt(execution.get('premium'))} | "
            f"{_fmt(execution.get('breakeven'))} | {_md_cell(_options_expiry_text(execution))} | "
            f"{_fmt(execution.get('iv_pct'), 1)} | {_md_cell(_options_greek_text(execution))} | "
            f"{_fmt(execution.get('expected_move'))} | {_md_cell(execution.get('oi_wall'))} | "
            f"{_md_cell(_options_notes(execution))} |"
        )
    if not rows:
        lines.append("| n/a | NO OPTIONS TRADE | No options structure | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | no tracked symbols |")
    return "\n".join(lines)


SHARP_MOVE_PCT = 2.0


def _sharp_move_reference(row: TrackedSymbolState, move: str) -> tuple[float | None, str]:
    levels = row.mtf_levels or {}
    last_price = _to_float(row.last_price)
    if move == "Sharp Rise":
        resistance = _to_float(levels.get("breakout") or row.trigger)
        if resistance is None:
            return None, "no resistance context"
        state = "breaking resistance" if last_price is not None and last_price >= resistance else "approaching resistance"
        return resistance, state
    support = _to_float(levels.get("support") or row.trigger or row.invalidation)
    if support is None:
        return None, "no support context"
    state = "breaking support" if last_price is not None and last_price <= support else "approaching support"
    return support, state


def collect_sharp_movers(
    rows: list[TrackedSymbolState],
    *,
    threshold_pct: float = SHARP_MOVE_PCT,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Return large intraday movers as a watch/read-through section.

    This is intentionally separate from alert qualification. A sharp mover can
    be important context even when timing, R:R, or options gates say no trade.
    """
    movers: list[dict[str, Any]] = []
    threshold = abs(float(threshold_pct or SHARP_MOVE_PCT))
    for row in rows:
        pct = _to_float(row.pct_change)
        if pct is None or abs(pct) < threshold:
            continue
        move = "Sharp Rise" if pct > 0 else "Sharp Fall"
        reference_level, level_state = _sharp_move_reference(row, move)
        movers.append(
            {
                "symbol": row.symbol,
                "move": move,
                "pct_change": pct,
                "last_price": row.last_price,
                "direction": row.direction,
                "status": row.status,
                "reference_level": reference_level,
                "level_state": level_state,
                "target1": row.target1,
                "decision": (row.decision_context or {}).get("final_action", "n/a"),
                "options": (row.decision_context or {}).get("options_suitability", "n/a"),
            }
        )
    movers.sort(key=lambda item: abs(float(item.get("pct_change") or 0.0)), reverse=True)
    return movers[: max(1, int(limit))]


def build_sharp_movers_section(rows: list[TrackedSymbolState], *, limit: int = 8) -> str:
    movers = collect_sharp_movers(rows, limit=limit)
    lines = [
        "## Sharp Movers",
        "",
        "| Symbol | Move | Chg | LTP | Level State | Ref Level | Read | Decision |",
        "|---|---|---:|---:|---|---:|---|---|",
    ]
    if not movers:
        lines.append("| n/a | none | n/a | n/a | n/a | n/a | No tracked name has crossed the sharp-move threshold. | n/a |")
        return "\n".join(lines)
    for item in movers:
        lines.append(
            f"| {item['symbol']} | {item['move']} | {_fmt_pct(item.get('pct_change'))} | "
            f"{_fmt(item.get('last_price'))} | {item.get('level_state', 'n/a')} | "
            f"{_fmt(item.get('reference_level'))} | {item.get('direction', 'n/a')} {item.get('status', 'n/a')} | "
            f"{item.get('decision', 'n/a')} / {item.get('options', 'n/a')} |"
        )
    return "\n".join(lines)


def default_cycle_log_path(now: datetime | None = None) -> Path:
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return LOG_DIR / f"intraday_alerts_{stamp}.jsonl"


def default_latest_snapshot_path() -> Path:
    return LOG_DIR / "intraday_alerts_latest.md"


def _tracked_to_payload(row: TrackedSymbolState) -> dict[str, Any]:
    return {
        "symbol": row.symbol,
        "last_price": row.last_price,
        "pct_change": row.pct_change,
        "direction": row.direction,
        "status": row.status,
        "trigger": row.trigger,
        "invalidation": row.invalidation,
        "target1": row.target1,
        "target2": row.target2,
        "rr": row.rr,
        "strategy": row.strategy,
        "note": row.note,
        "freshness": row.freshness,
        "source": row.source,
        "mtf_levels": row.mtf_levels,
        "fno_context": row.fno_context,
        "decision_context": row.decision_context,
        "locked_setup": row.locked_setup,
        "locked_at": row.locked_at,
    }


def _candidate_to_payload(item: AlertCandidate) -> dict[str, Any]:
    return {
        "symbol": item.symbol,
        "side": item.side,
        "status": item.status,
        "last_price": item.last_price,
        "pct_change": item.pct_change,
        "trigger": item.trigger,
        "stop": item.stop,
        "target": item.target,
        "rr": item.rr,
        "strategy": item.strategy,
        "note": item.note,
        "decision": item.decision,
    }


def extract_trade_timing_rows(state: LiveDashboardState) -> list[dict[str, Any]]:
    timestamp = (state.last_updated_at or datetime.now()).isoformat(timespec="seconds")
    rows: list[dict[str, Any]] = []
    for row in state.tracked_symbols:
        decision = row.decision_context or {}
        timing = decision.get("trade_timing") or {}
        if not timing:
            continue
        edge = decision.get("edge_memory") or {}
        rows.append(
            {
                "timestamp": timestamp,
                "cycle": state.cycle,
                "symbol": row.symbol,
                "direction": row.direction,
                "status": row.status,
                "last_price": row.last_price,
                "trigger": row.trigger,
                "invalidation": row.invalidation,
                "target1": row.target1,
                "rr": row.rr,
                "final_action": decision.get("final_action"),
                "decision_score": decision.get("decision_score"),
                "timing_window": timing.get("window"),
                "timing_score": timing.get("score"),
                "time_bucket": timing.get("time_bucket"),
                "timing_reasons": list(timing.get("reasons") or []),
                "edge_status": edge.get("status"),
                "edge_role": edge.get("edge_role"),
                "edge_setup": edge.get("setup"),
                "edge_confidence": edge.get("confidence"),
            }
        )
    return rows


def _timing_price(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _directional_return_pct(direction: str, entry: float, future: float) -> float | None:
    if entry <= 0:
        return None
    if direction == "LONG":
        return round((future - entry) / entry * 100.0, 4)
    if direction == "SHORT":
        return round((entry - future) / entry * 100.0, 4)
    return None


def evaluate_trade_timing_outcomes(
    records: list[dict[str, Any]],
    *,
    horizon_cycles: int = 3,
) -> list[dict[str, Any]]:
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        for row in record.get("trade_timing_scores") or []:
            symbol = str(row.get("symbol") or "").upper()
            if not symbol:
                continue
            by_symbol.setdefault(symbol, []).append(row)
    for rows in by_symbol.values():
        rows.sort(key=lambda item: int(item.get("cycle") or 0))

    outcomes: list[dict[str, Any]] = []
    for symbol, rows in by_symbol.items():
        for idx, row in enumerate(rows):
            cycle = int(row.get("cycle") or 0)
            entry = _timing_price(row.get("last_price"))
            direction = str(row.get("direction") or "").upper()
            if entry is None or direction not in {"LONG", "SHORT"}:
                continue
            future_rows = [
                future
                for future in rows[idx + 1 :]
                if 0 < int(future.get("cycle") or 0) - cycle <= max(1, int(horizon_cycles))
                and _timing_price(future.get("last_price")) is not None
            ]
            if not future_rows:
                continue
            future = future_rows[-1]
            future_price = _timing_price(future.get("last_price"))
            if future_price is None:
                continue
            future_prices = [_timing_price(item.get("last_price")) for item in future_rows]
            clean_prices = [price for price in future_prices if price is not None]
            if direction == "LONG":
                mfe = max(clean_prices) if clean_prices else future_price
                mae = min(clean_prices) if clean_prices else future_price
            else:
                mfe = min(clean_prices) if clean_prices else future_price
                mae = max(clean_prices) if clean_prices else future_price
            directional_return = _directional_return_pct(direction, entry, future_price)
            outcomes.append(
                {
                    **row,
                    "symbol": symbol,
                    "entry_cycle": cycle,
                    "future_cycle": int(future.get("cycle") or 0),
                    "entry_price": entry,
                    "future_price": future_price,
                    "directional_return_pct": directional_return,
                    "mfe_pct": _directional_return_pct(direction, entry, mfe),
                    "mae_pct": _directional_return_pct(direction, entry, mae),
                    "outcome_label": "positive" if (directional_return or 0.0) > 0 else "negative",
                }
            )
    return outcomes


def _avg(values: list[float]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def summarize_trade_timing_outcomes(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in outcomes:
        grouped.setdefault(str(row.get("timing_window") or "unknown"), []).append(row)
    summary: list[dict[str, Any]] = []
    for window, rows in grouped.items():
        returns = [row.get("directional_return_pct") for row in rows if row.get("directional_return_pct") is not None]
        positive = sum(1 for row in rows if row.get("outcome_label") == "positive")
        summary.append(
            {
                "timing_window": window,
                "samples": len(rows),
                "positive_rate": positive / len(rows) * 100.0 if rows else 0.0,
                "avg_directional_return_pct": _avg(returns),
                "avg_timing_score": _avg([row.get("timing_score") for row in rows if row.get("timing_score") is not None]),
            }
        )
    return sorted(summary, key=lambda row: (-(row.get("positive_rate") or 0.0), -(row.get("samples") or 0)))


def write_trade_timing_audit_report(
    records: list[dict[str, Any]],
    *,
    output_dir: str | Path = "reports/latest",
    horizon_cycles: int = 3,
) -> dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    outcomes = evaluate_trade_timing_outcomes(records, horizon_cycles=horizon_cycles)
    summary = summarize_trade_timing_outcomes(outcomes)

    lines = [
        "# Agent Adda Trade Timing Outcome Audit",
        "",
        f"- Records: {len(records)}",
        f"- Outcomes: {len(outcomes)}",
        f"- Horizon cycles: {horizon_cycles}",
        "",
        "## Timing Window Summary",
        "",
        "| Window | Samples | Positive Rate | Avg Return % | Avg Timing Score |",
        "|---|---:|---:|---:|---:|",
    ]
    if summary:
        for row in summary:
            lines.append(
                f"| {row.get('timing_window')} | {row.get('samples', 0)} | "
                f"{_fmt(row.get('positive_rate'), 1)}% | {_fmt(row.get('avg_directional_return_pct'), 2)} | "
                f"{_fmt(row.get('avg_timing_score'), 0)} |"
            )
    else:
        lines.append("| n/a | 0 | n/a | n/a | n/a |")
    lines.extend(
        [
            "",
            "## Outcome Rows",
            "",
            "| Symbol | Window | Bucket | Direction | Entry | Future | Return % | Label |",
            "|---|---|---|---|---:|---:|---:|---|",
        ]
    )
    if outcomes:
        for row in outcomes[:100]:
            lines.append(
                f"| {row.get('symbol')} | {row.get('timing_window')} | {row.get('time_bucket')} | "
                f"{row.get('direction')} | {_fmt(row.get('entry_price'), 2)} | {_fmt(row.get('future_price'), 2)} | "
                f"{_fmt(row.get('directional_return_pct'), 2)} | {row.get('outcome_label')} |"
            )
    else:
        lines.append("| n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |")
    lines.extend(["", "Research only. Not investment advice.", ""])

    markdown_path = output / "trade_timing_audit.md"
    json_path = output / "trade_timing_audit.json"
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "records": len(records),
                "horizon_cycles": horizon_cycles,
                "summary": summary,
                "outcomes": outcomes,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    return {"markdown": str(markdown_path), "json": str(json_path)}


def _edge_memory_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("symbol") or "").strip().upper(),
        str(row.get("direction") or "").strip().upper(),
        str(row.get("timeframe") or "").strip().lower(),
    )


def _best_edge_memory_rows(edge_rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    status_rank = {"retired": 0, "promoted": 1, "candidate": 2, "monitoring": 3, "decaying": 4}
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in edge_rows or []:
        key = _edge_memory_key(edge)
        if not all(key):
            continue
        current = out.get(key)
        if current is None:
            out[key] = edge
            continue
        current_rank = status_rank.get(str(current.get("status") or ""), 9)
        edge_rank = status_rank.get(str(edge.get("status") or ""), 9)
        current_conf = float(current.get("confidence") or 0.0)
        edge_conf = float(edge.get("confidence") or 0.0)
        if (edge_rank, -edge_conf) < (current_rank, -current_conf):
            out[key] = edge
    return out


def _best_retired_edge_by_symbol(edge_rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for edge in edge_rows or []:
        status = str(edge.get("status") or "").strip().lower()
        role = str(edge.get("edge_role") or "").strip().lower()
        if status != "retired" and role != "edge_diluter":
            continue
        key = (
            str(edge.get("symbol") or "").strip().upper(),
            str(edge.get("timeframe") or "").strip().lower(),
        )
        if not all(key):
            continue
        current = out.get(key)
        if current is None or float(edge.get("confidence") or 0.0) > float(current.get("confidence") or 0.0):
            out[key] = edge
    return out


def load_edge_memory_rows() -> list[dict[str, Any]]:
    try:
        from terminal.intraday_indicator_study import _connect_pg

        with _connect_pg() as conn:
            return fetch_edge_memory_rows(conn)
    except Exception:
        return []


def apply_edge_memory_to_tracked_symbols(
    rows: list[TrackedSymbolState],
    edge_rows: list[dict[str, Any]],
    *,
    timeframe: str,
) -> list[TrackedSymbolState]:
    lookup = _best_edge_memory_rows(edge_rows)
    retired_by_symbol = _best_retired_edge_by_symbol(edge_rows)
    tf = str(timeframe or "").strip().lower()
    for row in rows:
        key = (row.symbol.strip().upper(), row.direction.strip().upper(), tf)
        edge = lookup.get(key)
        if not edge and row.direction not in {"LONG", "SHORT"}:
            edge = retired_by_symbol.get((row.symbol.strip().upper(), tf))
        if not edge:
            continue
        status = str(edge.get("status") or "").strip().lower()
        role = str(edge.get("edge_role") or "").strip().lower()
        confidence = float(edge.get("confidence") or 0.0)
        decision = dict(row.decision_context or {})
        reasons = list(decision.get("reasons") or [])
        decision["edge_memory"] = {
            "status": status,
            "edge_role": role,
            "setup": edge.get("setup"),
            "direction": edge.get("direction"),
            "confidence": confidence,
            "persistence_count": edge.get("persistence_count", 0),
        }
        if status == "retired" or role == "edge_diluter":
            decision["final_action"] = "AVOID"
            decision["options_suitability"] = "No Trade"
            decision["decision_score"] = min(float(decision.get("decision_score") or 0.0), 25)
            edge_direction = str(edge.get("direction") or row.direction or "").strip().upper()
            reasons.insert(0, f"retired edge memory: {edge.get('setup')} {edge_direction} is {role or status}")
        elif status == "promoted":
            base_score = float(decision.get("decision_score") or 0.0)
            boosted = min(100, base_score + 10)
            decision["decision_score"] = boosted
            row_status = (row.status or "").lower()
            if "active" in row_status and boosted >= 65 and decision.get("final_action") not in {"AVOID", "NO TRADE", "INVALIDATED"}:
                decision["final_action"] = "TRADE NOW"
            elif "near trigger" in row_status and boosted >= 45 and decision.get("final_action") not in {"AVOID", "NO TRADE", "INVALIDATED"}:
                decision["final_action"] = "WAIT FOR RETEST"
            reasons.insert(0, f"promoted edge memory: {edge.get('setup')} confidence {confidence:.2f}")
        elif status in {"candidate", "monitoring"}:
            base_score = float(decision.get("decision_score") or 0.0)
            decision["decision_score"] = min(100, base_score + 5)
            reasons.insert(0, f"{status} edge memory: {edge.get('setup')} confidence {confidence:.2f}")
        elif status == "decaying":
            base_score = float(decision.get("decision_score") or 0.0)
            decision["decision_score"] = max(0, base_score - 10)
            reasons.insert(0, f"decaying edge memory: {edge.get('setup')} needs reconfirmation")
        decision["reasons"] = reasons[:8]
        row.decision_context = decision
    return rows


def _live_time_bucket(value: datetime | None) -> str:
    ts = value or datetime.now()
    minute = int(ts.hour) * 60 + int(ts.minute)
    if minute < 10 * 60 + 15:
        return "opening_drive"
    if minute < 12 * 60:
        return "late_morning"
    if minute < 14 * 60:
        return "mid_session"
    return "closing_drive"


def _active_intraday_strategies(strategies: list[str], *, as_of: datetime | None = None) -> list[str]:
    active = list(dict.fromkeys(strategies))
    if _live_time_bucket(as_of) == "opening_drive":
        return active
    filtered = [strategy for strategy in active if strategy not in OPENING_DRIVE_STRATEGIES]
    return filtered or active


def _float_or_zero(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _trade_timing_window(score: int, final_action: str, status: str) -> str:
    action = str(final_action or "").upper()
    lower_status = str(status or "").lower()
    if action in {"AVOID", "NO TRADE", "INVALIDATED"} or score <= 25:
        return "NO_TRADE_WINDOW"
    if "active" in lower_status and score >= 70:
        return "TRADE_WINDOW"
    if "near trigger" in lower_status and score >= 50:
        return "RETEST_WINDOW"
    if score >= 40:
        return "WATCH_WINDOW"
    return "NO_TRADE_WINDOW"


def apply_trade_timing_score(
    rows: list[TrackedSymbolState],
    *,
    as_of: datetime | None = None,
) -> list[TrackedSymbolState]:
    bucket = _live_time_bucket(as_of)
    for row in rows:
        decision = dict(row.decision_context or {})
        edge = decision.get("edge_memory") or {}
        status = str(row.status or "").lower()
        final_action = str(decision.get("final_action") or "")
        reasons: list[str] = []
        score = 0

        edge_status = str(edge.get("status") or "").lower()
        edge_role = str(edge.get("edge_role") or "").lower()
        if edge_status == "promoted":
            score += 30
            reasons.append("promoted edge")
        elif edge_status in {"candidate", "monitoring"}:
            score += 18
            reasons.append(f"{edge_status} edge")
        elif edge_status == "decaying":
            score -= 10
            reasons.append("decaying edge")
        elif edge_status == "retired" or edge_role == "edge_diluter":
            score -= 60
            reasons.append("retired edge")
        else:
            reasons.append("no persisted edge")

        if bucket == "opening_drive":
            score += 15
            reasons.append("opening-drive timing")
        elif bucket == "late_morning":
            score += 6
            reasons.append("late-morning timing")
        elif bucket == "mid_session":
            score -= 4
            reasons.append("mid-session lower urgency")
        else:
            score -= 2
            reasons.append("closing-drive timing")

        if "active" in status or "t1 hit" in status:
            score += 20
            reasons.append("trigger active")
        elif "near trigger" in status:
            score += 10
            reasons.append("near trigger")
        elif "invalid" in status or "breakdown" in status:
            score -= 35
            reasons.append("invalidated structure")
        else:
            score -= 5
            reasons.append("watch-only structure")

        rr = _float_or_zero(row.rr)
        if rr >= 2.0:
            score += 10
            reasons.append("R:R >= 2")
        elif rr >= 1.3:
            score += 5
            reasons.append("R:R acceptable")
        else:
            score -= 10
            reasons.append("R:R weak")

        fno_bias = str((row.fno_context or {}).get("bias") or "").lower()
        if row.direction == "LONG" and fno_bias == "bullish":
            score += 10
            reasons.append("F&O aligned bullish")
        elif row.direction == "SHORT" and fno_bias == "bearish":
            score += 10
            reasons.append("F&O aligned bearish")
        elif row.direction in {"LONG", "SHORT"} and fno_bias in {"bullish", "bearish"}:
            score -= 15
            reasons.append("F&O conflicts")
        elif fno_bias == "sideways":
            reasons.append("F&O sideways")

        if str(final_action).upper() in {"AVOID", "NO TRADE", "INVALIDATED"}:
            score = min(score, 25)
        score = int(max(0, min(100, round(score))))
        decision["trade_timing"] = {
            "score": score,
            "window": _trade_timing_window(score, final_action, row.status),
            "time_bucket": bucket,
            "reasons": reasons[:8],
        }
        row.decision_context = decision
    return rows


def _state_market_closed(state: LiveDashboardState) -> bool:
    return any(str(item).startswith("market_session closed") for item in state.source_health)


def _market_closed_commentary(status: MarketSessionStatus) -> str:
    return (
        f"{status.status_label}\n"
        "Intraday alert analysis skipped because the NSE regular session is closed. "
        "No alert email or draft was created."
    )


def _market_closed_email_result(status: MarketSessionStatus) -> dict[str, Any]:
    return {
        "ok": None,
        "message": f"market closed; no alert sent ({status.reason})",
        "subject": "n/a",
    }


def _build_market_closed_cycle_state(
    state: LiveDashboardState,
    status: MarketSessionStatus,
) -> LiveDashboardState:
    closed_state = update_live_dashboard_state(
        state,
        market_context=status.status_label,
        tracked_symbols=[],
        source_health=[
            f"market_session closed: {status.phase}; {status.reason}",
            f"market_clock: {status.clock_label}",
            f"next_open: {status.next_open_at:%Y-%m-%d %H:%M:%S IST}",
            "intraday_analysis skipped",
            "alert_dispatch skipped",
        ],
    )
    closed_state.last_commentary = _market_closed_commentary(status)
    return closed_state


def build_trading_stance(
    *,
    state: LiveDashboardState,
    candidates: list[AlertCandidate],
    fresh_candidates: list[AlertCandidate],
    config: IntradayAlertConfig | None = None,
) -> dict[str, Any]:
    """Summarize whether the current cycle is tradeable or should wait."""
    del config
    reasons: list[str] = [
        f"Fresh alerts: {len(fresh_candidates)}",
        f"Alert candidates: {len(candidates)}",
    ]
    market_closed_reasons = [
        str(item)
        for item in state.source_health
        if str(item).startswith(("market_session closed", "next_open"))
    ]
    if market_closed_reasons:
        return {
            "label": "NO_TRADE",
            "headline": "Market closed; no intraday trade alerts.",
            "action": "Stand aside until NSE regular session is open.",
            "symbols": [],
            "reasons": [*reasons, *market_closed_reasons],
        }

    trade_now_candidates: list[str] = []
    wait_candidates: list[str] = []
    no_trade_windows: list[str] = []
    volume_missing = False

    for item in candidates:
        decision = item.decision or {}
        timing = decision.get("trade_timing") or {}
        final_action = str(decision.get("final_action") or "").upper()
        timing_window = str(timing.get("window") or "")
        if final_action == "TRADE NOW" or timing_window == "TRADE_WINDOW":
            trade_now_candidates.append(item.symbol)
        else:
            wait_candidates.append(item.symbol)

    for row in state.tracked_symbols:
        decision = row.decision_context or {}
        timing = decision.get("trade_timing") or {}
        if timing.get("window") == "NO_TRADE_WINDOW":
            bucket = str(timing.get("time_bucket") or "n/a")
            no_trade_windows.append(f"{bucket} / NO_TRADE_WINDOW")
        decision_reasons = [str(item).lower() for item in (decision.get("reasons") or [])]
        timing_reasons = [str(item).lower() for item in (timing.get("reasons") or [])]
        if any("volume not confirmed" in reason for reason in decision_reasons + timing_reasons):
            volume_missing = True

    if no_trade_windows:
        reasons.append(no_trade_windows[0])
    if volume_missing:
        reasons.append("volume confirmation missing")

    if trade_now_candidates:
        return {
            "label": "TRADE",
            "headline": "Trade only qualified setup(s); avoid chasing.",
            "action": "Use only the named trade-window candidates and respect invalidation.",
            "symbols": trade_now_candidates[:5],
            "reasons": reasons,
        }
    if candidates or wait_candidates:
        return {
            "label": "WAIT",
            "headline": "Wait for retest/confirmation; no trade-now signal.",
            "action": "Monitor qualified watches, but wait for trigger hold and cleaner timing.",
            "symbols": wait_candidates[:5],
            "reasons": reasons,
        }
    if state.tracked_symbols:
        return {
            "label": "WAIT",
            "headline": "Wait; do not force trades right now.",
            "action": "Stand aside until fresh alerts, volume confirmation, and timing improve.",
            "symbols": [],
            "reasons": reasons,
        }
    return {
        "label": "NO_TRADE",
        "headline": "No trade; scanner has no usable setup evidence.",
        "action": "Stand aside until the scanner has valid tracked symbols and source health.",
        "symbols": [],
        "reasons": reasons,
    }


def build_intraday_cycle_log_record(
    *,
    state: LiveDashboardState,
    candidates: list[AlertCandidate],
    fresh_candidates: list[AlertCandidate],
    email_result: dict[str, Any] | None,
    config: IntradayAlertConfig,
) -> dict[str, Any]:
    return {
        "event": "intraday_alert_cycle",
        "timestamp": (state.last_updated_at or datetime.now()).isoformat(timespec="seconds"),
        "cycle": state.cycle,
        "market_context": state.market_context,
        "source_health": list(state.source_health),
        "config": {
            "symbols_count": len(config.symbols),
            "candle_interval": config.candle_interval,
            "min_rr": config.min_rr,
            "trigger": config.trigger,
            "report_key": config.report_key,
            "send": config.send,
            "dry_run": config.dry_run,
            "use_llm": config.use_llm,
            "email_every_mins": config.email_every_mins,
            "rescan_every_mins": config.rescan_every_mins,
            "max_tracked_symbols": config.max_tracked_symbols,
            "strategies": list(config.strategies),
            "require_volume": config.require_volume,
            "min_volume_ratio": config.min_volume_ratio,
            "include_fno": config.include_fno,
            "include_edge_memory": config.include_edge_memory,
        },
        "cycle_changes": state.cycle_changes,
        "trading_stance": build_trading_stance(
            state=state,
            candidates=candidates,
            fresh_candidates=fresh_candidates,
            config=config,
        ),
        "sharp_movers": collect_sharp_movers(state.tracked_symbols),
        "tracked_symbols": [_tracked_to_payload(row) for row in state.tracked_symbols],
        "trade_timing_scores": extract_trade_timing_rows(state),
        "blocked_trade_rows": [
            {
                "symbol": row.symbol,
                "direction": row.direction,
                "status": row.status,
                "last_price": row.last_price,
                "trigger": row.trigger,
                "invalidation": row.invalidation,
                "target1": row.target1,
                "rr": row.rr,
                "final_action": (row.decision_context or {}).get("final_action"),
                "options_suitability": (row.decision_context or {}).get("options_suitability"),
                "decision_score": (row.decision_context or {}).get("decision_score"),
                "blockers": _blocked_trade_reasons(row, config),
            }
            for row in collect_blocked_trade_rows(state.tracked_symbols, candidates, config, limit=5)
        ],
        "alert_candidates": [_candidate_to_payload(item) for item in candidates],
        "fresh_alerts": [_candidate_to_payload(item) for item in fresh_candidates],
        "email_result": email_result or {"ok": None, "message": "no fresh alert"},
        "commentary": state.last_commentary,
    }


def write_intraday_cycle_log(record: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    return path


def write_intraday_latest_snapshot(
    *,
    state: LiveDashboardState,
    candidates: list[AlertCandidate],
    fresh_candidates: list[AlertCandidate],
    email_result: dict[str, Any] | None,
    path: Path,
    config: IntradayAlertConfig | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    effective_config = config or IntradayAlertConfig(symbols=[])
    stance = build_trading_stance(
        state=state,
        candidates=candidates,
        fresh_candidates=fresh_candidates,
        config=effective_config,
    )
    lines = [
        "# Agent Adda Intraday Alerts - Latest Cycle",
        "",
        f"- Time: {(state.last_updated_at or datetime.now()).strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Cycle: {state.cycle}",
        f"- Market: {state.market_context or 'n/a'}",
        f"- Source health: {' | '.join(state.source_health) if state.source_health else 'n/a'}",
        f"- Fresh alerts: {len(fresh_candidates)}",
        f"- Total candidates: {len(candidates)}",
        "",
    ]
    lines.extend([
        "## Trading Stance",
        "",
        f"- Stance: {stance.get('label', 'n/a')}",
        f"- Headline: {stance.get('headline', 'n/a')}",
        f"- Action: {stance.get('action', 'n/a')}",
        f"- Reasons: {'; '.join(str(item) for item in (stance.get('reasons') or [])) or 'n/a'}",
        "",
    ])
    lines.extend(["", build_sharp_movers_section(state.tracked_symbols), ""])
    changes = state.cycle_changes or {}
    lines.extend(["## Cycle Changes", ""])
    for label, key in (
        ("New added", "new_added"),
        ("Removed", "removed"),
        ("Forming", "forming"),
        ("Confirmed", "confirmed"),
        ("Active", "active"),
    ):
        names = ", ".join(item.get("symbol", "") for item in (changes.get(key) or []) if item.get("symbol"))
        lines.append(f"- {label}: {names or 'none'}")
    if changes.get("status_changes"):
        lines.append(
            "- Status changes: "
            + "; ".join(
                f"{item.get('symbol')} {item.get('from')} -> {item.get('to')}"
                for item in changes["status_changes"]
            )
        )
    lines.extend(["", "## Fresh Alerts", ""])
    if fresh_candidates:
        lines.extend(["| Symbol | Side | Status | Decision | Options | Entry | Stop | T1 | RR |", "|---|---:|---|---|---|---:|---:|---:|---:|"])
        for item in fresh_candidates:
            decision = item.decision or {}
            lines.append(
                f"| {item.symbol} | {item.side} | {item.status} | {decision.get('final_action', 'n/a')} | "
                f"{decision.get('options_suitability', 'n/a')} | {_fmt(item.trigger)} | "
                f"{_fmt(item.stop)} | {_fmt(item.target)} | {_fmt(item.rr, 1)} |"
            )
    else:
        lines.append("No fresh alerts this cycle.")
    lines.extend(["", "## Tracker", ""])
    lines.extend(["| Symbol | Read | Decision | Options | Score | F&O | LTP | Chg | Entry | Stop | T1/RR |", "|---|---|---|---|---:|---|---:|---:|---:|---:|---:|"])
    for row in state.tracked_symbols[:30]:
        target = _fmt(row.target1)
        if row.rr is not None:
            target = f"{target}/{_fmt(row.rr, 1)}R"
        fno = row.fno_context or {}
        decision = row.decision_context or {}
        fno_text = f"{fno.get('bias', 'n/a')} PCR {_fmt(fno.get('pcr'), 2)} basis {_fmt(fno.get('basis'), 2)} MP {_fmt(fno.get('max_pain'), 0)}"
        lines.append(
            f"| {row.symbol} | {row.direction} {row.status} | {decision.get('final_action', 'n/a')} | "
            f"{decision.get('options_suitability', 'n/a')} | {_fmt(decision.get('decision_score'), 0)} | "
            f"{fno_text} | {_fmt(row.last_price)} | "
            f"{_fmt_pct(row.pct_change)} | {_fmt(row.trigger)} | {_fmt(row.invalidation)} | {target} |"
        )
    blocked_rows = collect_blocked_trade_rows(state.tracked_symbols, candidates, effective_config, limit=5)
    lines.extend(["", "## Why No Trade - Top 5 Blocked", ""])
    if blocked_rows:
        lines.extend([
            "| Symbol | Side | State | Decision | LTP | Trigger | Stop | T1 | RR | Why blocked |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---|",
        ])
        for row in blocked_rows:
            decision = row.decision_context or {}
            gate = " / ".join(
                str(part)
                for part in [
                    decision.get("final_action") or "n/a",
                    decision.get("options_suitability") or "",
                    f"score {_fmt(decision.get('decision_score'), 0)}" if decision.get("decision_score") is not None else "",
                ]
                if part
            )
            lines.append(
                f"| {row.symbol} | {row.direction} | {row.status} | {gate} | "
                f"{_fmt(row.last_price)} | {_fmt(row.trigger)} | {_fmt(row.invalidation)} | {_fmt(row.target1)} | "
                f"{_fmt(row.rr, 1)} | {'; '.join(_blocked_trade_reasons(row, effective_config))} |"
            )
    else:
        lines.append("No blocked tracker rows available.")
    lines.extend(["", "## Trade Decisions", ""])
    lines.extend(["| Symbol | Action | Options | Score | Market Regime | Reasons |", "|---|---|---|---:|---|---|"])
    for row in state.tracked_symbols[:30]:
        decision = row.decision_context or {}
        regime = decision.get("market_regime") or {}
        reasons = "; ".join(str(item) for item in (decision.get("reasons") or [])[:5])
        lines.append(
            f"| {row.symbol} | {decision.get('final_action', 'n/a')} | {decision.get('options_suitability', 'n/a')} | "
            f"{_fmt(decision.get('decision_score'), 0)} | {regime.get('label', 'n/a')} | {reasons} |"
        )
    lines.extend(["", "## Trade Timing", ""])
    lines.extend(["| Symbol | Window | Timing Score | Time Bucket | Reasons |", "|---|---|---:|---|---|"])
    for row in state.tracked_symbols[:30]:
        timing = (row.decision_context or {}).get("trade_timing") or {}
        if not timing:
            continue
        timing_reasons = "; ".join(str(item) for item in (timing.get("reasons") or [])[:5])
        lines.append(
            f"| {row.symbol} | {timing.get('window', 'n/a')} | {_fmt(timing.get('score'), 0)} | "
            f"{timing.get('time_bucket', 'n/a')} | {timing_reasons} |"
        )
    if not any((row.decision_context or {}).get("trade_timing") for row in state.tracked_symbols[:30]):
        lines.append("| n/a | n/a | n/a | n/a | n/a |")
    lines.extend(["", build_options_execution_section(state.tracked_symbols[:30]), ""])
    lines.extend(["", "## Edge Memory", ""])
    lines.extend(["| Symbol | Status | Role | Setup | Confidence | Persistence |", "|---|---|---|---|---:|---:|"])
    edge_rows = []
    for row in state.tracked_symbols[:30]:
        edge = (row.decision_context or {}).get("edge_memory") or {}
        if not edge:
            continue
        edge_rows.append(row)
        lines.append(
            f"| {row.symbol} | {edge.get('status', 'n/a')} | {edge.get('edge_role', 'n/a')} | "
            f"{edge.get('setup', 'n/a')} | {_fmt(edge.get('confidence'), 2)} | {_fmt(edge.get('persistence_count'), 0)} |"
        )
    if not edge_rows:
        lines.append("| n/a | n/a | n/a | n/a | n/a | n/a |")
    lines.extend(["", "## F&O Context", ""])
    lines.extend(["| Symbol | Bias | PCR | Basis | Max Pain | Note |", "|---|---|---:|---:|---:|---|"])
    for row in state.tracked_symbols[:30]:
        fno = row.fno_context or {}
        lines.append(
            f"| {row.symbol} | {fno.get('bias', 'n/a')} | {_fmt(fno.get('pcr'), 2)} | "
            f"{_fmt(fno.get('basis'), 2)} | {_fmt(fno.get('max_pain'), 0)} | {str(fno.get('reason') or '')[:140]} |"
        )
    lines.extend(["", "## Commentary", "", state.last_commentary or "n/a", ""])
    if email_result:
        lines.extend(["## Email", "", f"- Status: {email_result.get('message')}", f"- Subject: {email_result.get('subject', 'n/a')}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _is_triggered(row: TrackedSymbolState, config: IntradayAlertConfig) -> bool:
    status = (row.status or "").lower()
    decision = row.decision_context or {}
    final_action = str(decision.get("final_action") or "").upper()
    if final_action in {"AVOID", "NO TRADE", "INVALIDATED"}:
        return False
    if row.rr is not None and row.rr < config.min_rr:
        return False
    if config.trigger == "active":
        return "active" in status or "t1 hit" in status
    if config.trigger == "near":
        return "near trigger" in status
    return "active" in status or "near trigger" in status or "t1 hit" in status


def collect_alert_candidates(
    tracked: list[TrackedSymbolState],
    config: IntradayAlertConfig,
) -> list[AlertCandidate]:
    candidates: list[AlertCandidate] = []
    for row in tracked:
        if not _is_triggered(row, config):
            continue
        side = "LONG" if row.direction == "LONG" else "SHORT" if row.direction == "SHORT" else "WATCH"
        if side == "WATCH":
            continue
        candidates.append(
            AlertCandidate(
                symbol=row.symbol,
                side=side,
                status=row.status,
                last_price=row.last_price,
                pct_change=row.pct_change,
                trigger=row.trigger,
                stop=row.invalidation,
                target=row.target1,
                rr=row.rr,
                strategy=row.strategy,
                note=row.note,
                decision=row.decision_context,
            )
        )
    return sorted(candidates, key=lambda item: (item.status.startswith("near"), -(item.rr or 0.0)))


def _candidate_is_active(item: AlertCandidate) -> bool:
    status = (item.status or "").lower()
    return "active" in status or "t1 hit" in status


def _candidate_row_style(item: AlertCandidate) -> str:
    if item.side == "LONG":
        return "green"
    if item.side == "SHORT":
        return "red"
    return "yellow"


def _sharp_movers_terminal_table(rows: list[TrackedSymbolState], *, limit: int = 8) -> Table:
    table = Table(
        expand=True,
        box=box.SIMPLE_HEAVY,
        header_style="bold yellow",
        padding=(0, 1),
    )
    table.add_column("Symbol", style="bold cyan", no_wrap=True)
    table.add_column("Move", no_wrap=True)
    table.add_column("Chg", justify="right", no_wrap=True)
    table.add_column("LTP", justify="right", no_wrap=True)
    table.add_column("Level", overflow="fold")
    table.add_column("Read", overflow="fold")
    movers = collect_sharp_movers(rows, limit=limit)
    if not movers:
        table.add_row("n/a", "none", "n/a", "n/a", "No tracked name crossed the sharp-move threshold.", "Watch current alert candidates.")
        return table
    for item in movers:
        move = str(item.get("move") or "n/a")
        style = "bold green" if move == "Sharp Rise" else "bold red"
        table.add_row(
            str(item.get("symbol") or "n/a"),
            Text(move, style=style),
            _fmt_pct(item.get("pct_change")),
            _fmt(item.get("last_price")),
            f"{item.get('level_state', 'n/a')} @ {_fmt(item.get('reference_level'))}",
            f"{item.get('direction', 'n/a')} {item.get('status', 'n/a')} | {item.get('decision', 'n/a')}",
        )
    return table


def _blocked_trades_terminal_table(
    rows: list[TrackedSymbolState],
    *,
    config: IntradayAlertConfig,
) -> Table:
    table = Table(
        expand=True,
        box=box.SIMPLE_HEAVY,
        header_style="bold yellow",
        padding=(0, 1),
    )
    table.add_column("Symbol", style="bold cyan", no_wrap=True)
    table.add_column("Side", justify="center", no_wrap=True)
    table.add_column("State", overflow="fold")
    table.add_column("LTP", justify="right", no_wrap=True)
    table.add_column("Trigger/Stop/T1", overflow="fold")
    table.add_column("R:R", justify="right", no_wrap=True)
    table.add_column("Gate", overflow="fold")
    table.add_column("Why blocked", overflow="fold")

    if not rows:
        table.add_row("n/a", "-", "No tracked non-candidate rows.", "n/a", "n/a", "n/a", "n/a", "n/a")
        return table

    for row in rows:
        decision = row.decision_context or {}
        gate = " / ".join(
            str(part)
            for part in [
                decision.get("final_action") or "n/a",
                decision.get("options_suitability") or "",
                f"score {_fmt(decision.get('decision_score'), 0)}" if decision.get("decision_score") is not None else "",
            ]
            if part
        )
        reasons = "; ".join(_blocked_trade_reasons(row, config))
        side_style = "green" if row.direction == "LONG" else "red" if row.direction == "SHORT" else "yellow"
        table.add_row(
            row.symbol,
            Text(row.direction or "WATCH", style=f"bold {side_style}"),
            row.status or "watch",
            _fmt(row.last_price),
            f"{_fmt(row.trigger)} / {_fmt(row.invalidation)} / {_fmt(row.target1)}",
            _fmt(row.rr, 1),
            gate,
            reasons,
        )
    return table


def render_intraday_alert_dashboard(
    state: LiveDashboardState,
    candidates: list[AlertCandidate],
    fresh_candidates: list[AlertCandidate],
    config: IntradayAlertConfig,
) -> Group:
    """Render the terminal alert view.

    This intentionally renders alert-qualified candidates only. The broader
    tracker remains available in cycle logs and latest snapshots, but showing
    it in the terminal alert view made watchlist rows look like alerts.
    """
    as_of = state.last_updated_at or datetime.now()
    active = [item for item in candidates if _candidate_is_active(item)]
    watch = [item for item in candidates if item not in active]
    stance = build_trading_stance(
        state=state,
        candidates=candidates,
        fresh_candidates=fresh_candidates,
        config=config,
    )

    summary = Text()
    summary.append(f"Cycle {state.cycle}", style="bold bright_blue")
    summary.append(f" | {as_of:%Y-%m-%d %H:%M:%S}", style="dim")
    summary.append(f" | {state.market_context or 'market context unavailable'}", style="white")
    summary.append(
        f"\nFilter: trigger={config.trigger}, min R:R={_fmt(config.min_rr, 1)}, interval={config.candle_interval}",
        style="dim",
    )
    summary.append(
        f"\nAlert candidates: {len(candidates)} | fresh: {len(fresh_candidates)} | tracked context: {len(state.tracked_symbols)}",
        style="bold",
    )
    stance_text = Text()
    stance_label = str(stance.get("label") or "n/a")
    stance_style = {
        "TRADE": "bold green",
        "WAIT": "bold yellow",
        "NO_TRADE": "bold red",
    }.get(stance_label, "bold white")
    stance_text.append(stance_label, style=stance_style)
    stance_text.append(f" - {stance.get('headline', 'n/a')}\n", style="white")
    stance_text.append(str(stance.get("action") or "n/a"), style="cyan")
    reasons = [str(item) for item in (stance.get("reasons") or [])]
    if reasons:
        stance_text.append("\nReasons: ", style="dim")
        stance_text.append("; ".join(reasons), style="dim")

    table = Table(
        title="Alert-qualified setups",
        expand=True,
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("Symbol", style="bold cyan", no_wrap=True)
    table.add_column("Side", justify="center", no_wrap=True)
    table.add_column("State", no_wrap=True)
    table.add_column("LTP", justify="right", no_wrap=True)
    table.add_column("Chg", justify="right", no_wrap=True)
    table.add_column("Trigger", justify="right", no_wrap=True)
    table.add_column("Stop", justify="right", no_wrap=True)
    table.add_column("T1", justify="right", no_wrap=True)
    table.add_column("R:R", justify="right", no_wrap=True)
    table.add_column("Setup", overflow="fold")
    if candidates:
        for item in candidates:
            style = _candidate_row_style(item)
            decision = item.decision or {}
            decision_note = ""
            if decision:
                decision_note = (
                    f"\nDecision: {decision.get('final_action', 'n/a')} / "
                    f"{decision.get('options_suitability', 'n/a')} "
                    f"score {_fmt(decision.get('decision_score'), 0)}"
                )
            table.add_row(
                item.symbol,
                Text(item.side, style=f"bold {style}"),
                item.status,
                _fmt(item.last_price),
                _fmt_pct(item.pct_change),
                Text(_fmt(item.trigger), style="cyan"),
                Text(_fmt(item.stop), style="red"),
                Text(_fmt(item.target), style="green"),
                Text(_fmt(item.rr, 1), style="bold white"),
                f"{item.strategy}\n{item.note}{decision_note}".strip(),
            )
    else:
        table.add_row(
            "No candidates",
            "-",
            f"No {config.trigger} setup passed min R:R {_fmt(config.min_rr, 1)}",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "Wait for next scan.",
        )

    fresh_text = Text()
    if fresh_candidates:
        for item in fresh_candidates[:8]:
            fresh_text.append(fresh_text.plain and "\n" or "")
            fresh_text.append(_candidate_action_line(item), style=_candidate_row_style(item))
    else:
        fresh_text.append("No fresh alert this cycle.", style="dim")

    commentary = (
        state.last_commentary
        if _state_market_closed(state)
        else build_email_commentary(
            candidates,
            market_context=state.market_context,
            commentary="commentary",
        )
    )
    candidate_symbols = {item.symbol for item in candidates}
    options_rows = [row for row in state.tracked_symbols if row.symbol in candidate_symbols]
    options_table = _options_execution_terminal_table(options_rows[:10])
    blocked_rows = collect_blocked_trade_rows(state.tracked_symbols, candidates, config, limit=5)
    source = " | ".join(state.source_health) if state.source_health else "source health unavailable"

    return Group(
        Panel(summary, title="Agent Adda Intraday Alert Dashboard", border_style="bright_blue"),
        Panel(stance_text, title="Trading Stance", border_style="yellow" if stance_label == "WAIT" else "green" if stance_label == "TRADE" else "red"),
        Panel(_sharp_movers_terminal_table(state.tracked_symbols), title="Sharp Movers", border_style="yellow"),
        table,
        Panel(_blocked_trades_terminal_table(blocked_rows, config=config), title="Why No Trade - Top 5 Blocked", border_style="red" if not candidates else "yellow"),
        Panel(fresh_text, title="Fresh Alert Candidates", border_style="green" if fresh_candidates else "yellow"),
        Panel(options_table, title="Options Execution", border_style="magenta"),
        Panel(commentary, title="Alert Commentary", border_style="cyan"),
        Panel(source, title="Source Health", border_style="dim"),
    )


def _is_placeholder_commentary(commentary: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(commentary or "")).strip().lower()
    return normalized in {"", "commentary", "n/a", "na", "none", "null"}


def _candidate_action_line(item: AlertCandidate) -> str:
    status = (item.status or "").lower()
    is_near = "near trigger" in status
    is_t1 = "t1 hit" in status
    if is_t1:
        confirm = "T1 already hit; trail only above trigger" if item.side == "LONG" else "T1 already hit; trail only below trigger"
    elif is_near and item.side == "LONG":
        confirm = "watch only; wait for break and 5m hold above trigger"
    elif is_near and item.side == "SHORT":
        confirm = "watch only; wait for break and 5m hold below trigger"
    elif item.side == "LONG":
        confirm = "active only while holding above trigger"
    elif item.side == "SHORT":
        confirm = "active only while holding below trigger"
    else:
        confirm = "confirm trigger"
    decision = item.decision or {}
    decision_text = ""
    if decision:
        timing = decision.get("trade_timing") or {}
        timing_text = ""
        if timing:
            timing_text = (
                f" Timing {timing.get('window', 'n/a')} "
                f"{_fmt(timing.get('score'), 0)}/{timing.get('time_bucket', 'n/a')}."
            )
        decision_text = (
            f" Decision {decision.get('final_action', 'n/a')} / "
            f"{decision.get('options_suitability', 'n/a')} "
            f"(score {_fmt(decision.get('decision_score'), 0)})."
            f"{timing_text}"
        )
    return (
        f"{item.symbol}: {item.side} {item.status}; {confirm} {_fmt(item.trigger)}, "
        f"invalidation {_fmt(item.stop)}, T1 {_fmt(item.target)}, R:R {_fmt(item.rr, 1)}."
        f"{decision_text}"
    )


def _candidate_subject_label(item: AlertCandidate) -> str:
    status = (item.status or "").lower()
    if "near trigger" in status:
        state = "WATCH"
    elif "t1 hit" in status:
        state = "T1"
    elif "active" in status:
        state = "ACTIVE"
    else:
        state = "SETUP"
    return f"{item.symbol} {item.side} {state}"


def build_email_commentary(
    candidates: list[AlertCandidate],
    *,
    market_context: str,
    commentary: str,
) -> str:
    """Return email-ready tracker commentary, replacing placeholders with evidence."""
    if not _is_placeholder_commentary(commentary):
        return commentary.strip()

    ranked = sorted(
        candidates,
        key=lambda item: (
            "active" not in (item.status or "").lower() and "t1 hit" not in (item.status or "").lower(),
            -(item.rr or 0.0),
        ),
    )
    active = [
        item for item in ranked
        if "active" in (item.status or "").lower() or "t1 hit" in (item.status or "").lower()
    ]
    watch = [item for item in ranked if item not in active]

    lines = ["Current read from the tracker:", ""]
    if active:
        lines.append("Active triggers:")
        lines.extend(f"- {_candidate_action_line(item)}" for item in active[:5])
    else:
        lines.append("- No active trigger is currently passing the alert filter.")

    lines.extend(["", "Near trigger / watch:"])
    if watch:
        lines.extend(f"- {_candidate_action_line(item)}" for item in watch[:5])
    else:
        lines.append("- No near-trigger watches passed the alert filter.")

    lines.extend(["", "What to do next:"])
    if ranked:
        top = ranked[0]
        lines.append(
            f"- Priority is {top.symbol} {top.side}: wait for trigger hold, then respect invalidation at {_fmt(top.stop)}."
        )
        lines.append("- Skip if spread, liquidity, option premium, or candle quality makes execution poor.")
    else:
        lines.append("- No actionable candidate; wait for the next scan.")
    lines.append(f"- Market context: {market_context or 'unavailable'}")
    return "\n".join(lines)


def _fno_alignment_rank(row: TrackedSymbolState) -> int:
    """Sort helper: aligned F&O first, neutral next, conflicting last."""
    direction = row.direction
    bias = str((row.fno_context or {}).get("bias") or "").lower()
    if direction not in {"LONG", "SHORT"} or bias in {"", "unknown"}:
        return 1
    if bias == "sideways":
        return 1
    if direction == "LONG" and bias == "bullish":
        return 0
    if direction == "SHORT" and bias == "bearish":
        return 0
    return 2


def _tracking_rank(row: TrackedSymbolState, config: IntradayAlertConfig) -> tuple[int, int, int, float, float, str]:
    status = (row.status or "").lower()
    rr = row.rr or 0.0
    abs_change = abs(row.pct_change or 0.0)
    fno_alignment = _fno_alignment_rank(row) if config.include_fno else 1
    actionable_rr = rr >= config.min_rr
    final_action = str((row.decision_context or {}).get("final_action") or "").upper()
    action_rank = {
        "TRADE NOW": 0,
        "WAIT FOR RETEST": 1,
        "WATCH ONLY": 2,
        "AVOID": 4,
        "NO TRADE": 5,
        "INVALIDATED": 6,
    }.get(final_action, 3)
    if actionable_rr and ("active" in status or "t1 hit" in status):
        bucket = 0
    elif actionable_rr and "near trigger" in status:
        bucket = 1
    elif row.direction in {"LONG", "SHORT"}:
        bucket = 2
    elif "invalid" in status or "breakdown" in status:
        bucket = 4
    else:
        bucket = 3
    return (action_rank, bucket, fno_alignment, -rr, -abs_change, row.symbol)


def select_tracking_rows(
    tracked: list[TrackedSymbolState],
    config: IntradayAlertConfig,
) -> list[TrackedSymbolState]:
    limit = max(1, int(config.max_tracked_symbols or 15))
    return sorted(tracked, key=lambda row: _tracking_rank(row, config))[:limit]


def _short_reason(text: Any, *, limit: int = 68) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 1)].rstrip() + "..."


def _append_unique(items: list[str], value: Any) -> None:
    text = _short_reason(value)
    if text and text not in items:
        items.append(text)


def _blocked_trade_reasons(row: TrackedSymbolState, config: IntradayAlertConfig) -> list[str]:
    decision = row.decision_context or {}
    timing = decision.get("trade_timing") or {}
    reasons: list[str] = []

    final_action = str(decision.get("final_action") or "").strip()
    if final_action:
        _append_unique(reasons, f"gate {final_action}")

    status = (row.status or "").lower()
    if "invalid" in status:
        _append_unique(reasons, "setup invalidated")
    elif "near trigger" in status:
        _append_unique(reasons, "needs break/hold confirmation")
    elif row.direction not in {"LONG", "SHORT"}:
        _append_unique(reasons, "watch-only / no directional trigger")

    if row.rr is None:
        _append_unique(reasons, "no R:R / target structure")
    elif row.rr < config.min_rr:
        _append_unique(reasons, f"R:R {_fmt(row.rr, 1)} < min {_fmt(config.min_rr, 1)}")

    timing_window = str(timing.get("window") or "").strip()
    if timing_window:
        bucket = str(timing.get("time_bucket") or "n/a").strip()
        _append_unique(reasons, f"{bucket} / {timing_window}")

    for reason in list(decision.get("reasons") or [])[:4]:
        _append_unique(reasons, reason)
    for reason in list(timing.get("reasons") or [])[:3]:
        _append_unique(reasons, reason)

    mtf = row.mtf_levels or {}
    if mtf.get("status") == "missing":
        _append_unique(reasons, mtf.get("reason") or "MTF levels missing")

    execution = decision.get("options_execution") or {}
    if execution.get("verdict") == "NO OPTIONS TRADE":
        exec_reasons = execution.get("reasons") or []
        _append_unique(reasons, exec_reasons[0] if exec_reasons else "options blocked")

    return reasons[:6] or ["not alert-qualified"]


def collect_blocked_trade_rows(
    tracked: list[TrackedSymbolState],
    candidates: list[AlertCandidate],
    config: IntradayAlertConfig,
    *,
    limit: int = 5,
) -> list[TrackedSymbolState]:
    candidate_symbols = {item.symbol for item in candidates}
    blocked = [row for row in tracked if row.symbol not in candidate_symbols]
    return sorted(blocked, key=lambda row: _tracking_rank(row, config))[:limit]


def _rescan_interval_mins(config: IntradayAlertConfig) -> int:
    return max(0, int(config.rescan_every_mins or config.email_every_mins or 0))


def _dashboard_read(row: TrackedSymbolState) -> str:
    prefix = {"LONG": "L", "SHORT": "S"}.get(row.direction, "W")
    status = (row.status or "watch").lower()
    if "invalid" in status or "breakdown" in status:
        label = "INV"
    elif "active" in status:
        label = "ACTIVE"
    elif "near trigger" in status:
        label = "WATCH"
    elif "t1 hit" in status:
        label = "T1"
    else:
        label = "WATCH"
    return f"{prefix}-{label}"


def _tracker_target_text(row: TrackedSymbolState) -> str:
    target = _fmt(row.target1)
    if row.rr is not None:
        target = f"{target}/{_fmt(row.rr, 1)}R"
    return target


EMAIL_TABLE_WIDTH = 760
EMAIL_NOWRAP = "white-space:nowrap"
EMAIL_WRAP = "word-break:break-word;overflow-wrap:anywhere"


def _html_section_title(title: str) -> str:
    return (
        f"<tr><td style='padding:0 18px 6px;font-family:Arial,Helvetica,sans-serif;"
        f"font-size:16px;font-weight:bold;color:#0f172a'>{html.escape(title)}</td></tr>"
    )


def _html_empty_row(text: str) -> str:
    return (
        "<table width='100%' cellpadding='0' cellspacing='0' role='presentation' style='border-collapse:collapse'>"
        f"<tr><td style='padding:10px 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#64748b'>{html.escape(text)}</td></tr>"
        "</table>"
    )


def _sharp_movers_html(rows: list[TrackedSymbolState], *, limit: int = 8) -> str:
    movers = collect_sharp_movers(rows, limit=limit)
    if not movers:
        return _html_empty_row("No tracked name crossed the sharp-move threshold this cycle.")
    body = []
    for item in movers:
        move = str(item.get("move") or "n/a")
        move_color = "#16a34a" if move == "Sharp Rise" else "#dc2626"
        body.append(
            "<tr>"
            f"<td style='width:110px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'><b>{html.escape(str(item.get('symbol') or 'n/a'))}</b></td>"
            f"<td style='width:100px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:{move_color};font-weight:bold;{EMAIL_NOWRAP}'>{html.escape(move)}</td>"
            f"<td align='right' style='width:70px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'>{_fmt_pct(item.get('pct_change'))}</td>"
            f"<td align='right' style='width:90px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'>{_fmt(item.get('last_price'))}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px'>{html.escape(str(item.get('level_state') or 'n/a'))} @ {_fmt(item.get('reference_level'))}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px'>{html.escape(str(item.get('direction') or 'n/a'))} {html.escape(str(item.get('status') or 'n/a'))}<br><span style='color:#64748b'>{html.escape(str(item.get('decision') or 'n/a'))} / {html.escape(str(item.get('options') or 'n/a'))}</span></td>"
            "</tr>"
        )
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse;border:1px solid #dbe3ef">
      <thead>
        <tr bgcolor="#fff7ed">
          <th align="left" style="width:110px;padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#7c2d12;{EMAIL_NOWRAP}">Symbol</th>
          <th align="left" style="width:100px;padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#7c2d12;{EMAIL_NOWRAP}">Move</th>
          <th align="right" style="width:70px;padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#7c2d12;{EMAIL_NOWRAP}">Chg</th>
          <th align="right" style="width:90px;padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#7c2d12;{EMAIL_NOWRAP}">LTP</th>
          <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#7c2d12">Level State</th>
          <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#7c2d12">Read</th>
        </tr>
      </thead>
      <tbody>{''.join(body)}</tbody>
    </table>
    """


def _dashboard_tracker_table(state: LiveDashboardState, *, limit: int = 15) -> str:
    rows = []
    for row in state.tracked_symbols[:limit]:
        rows.append(
            "<tr>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px'><b>{html.escape(row.symbol)}</b></td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px'>{html.escape(_dashboard_read(row))}</td>"
            f"<td align='right' style='padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px'>{_fmt(row.last_price)}</td>"
            f"<td align='right' style='padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px'>{_fmt_pct(row.pct_change)}</td>"
            f"<td align='right' style='padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px'>{_fmt(row.trigger)}</td>"
            f"<td align='right' style='padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#dc2626'>{_fmt(row.invalidation)}</td>"
            f"<td align='right' style='padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#16a34a'>{html.escape(_tracker_target_text(row))}</td>"
            "</tr>"
        )
    if not rows:
        rows.append(
            "<tr><td colspan='7' style='padding:10px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#64748b'>"
            "No tracker rows available for this cycle.</td></tr>"
        )
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse;border:1px solid #dbe3ef">
      <tr bgcolor="#0f172a">
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff">Symbol</th>
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff">Read</th>
        <th align="right" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff">LTP</th>
        <th align="right" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff">Chg</th>
        <th align="right" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff">Trigger</th>
        <th align="right" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff">Stop</th>
        <th align="right" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff">T1/RR</th>
      </tr>
      {''.join(rows)}
    </table>
    """


def _options_execution_html(rows: list[TrackedSymbolState], *, limit: int = 15) -> str:
    body = []
    for row in rows[:limit]:
        execution = _options_execution(row)
        verdict = str(execution.get("verdict") or "NO OPTIONS TRADE")
        verdict_color = "#166534" if verdict.startswith("BUY") else "#92400e" if verdict == "USE SPREAD" else "#991b1b"
        option_parts = [
            str(execution.get("option_type") or _option_type_for_direction(_option_direction(row))),
            str(execution.get("moneyness") or "").strip(),
        ]
        option_text = " ".join(part for part in option_parts if part)
        strategy_text = _options_strategy_text(execution)
        notes = _options_notes(execution)
        body.append(
            "<tr>"
            f"<td style='width:92px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'><b>{html.escape(row.symbol)}</b></td>"
            f"<td style='width:128px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:bold;color:{verdict_color};{EMAIL_NOWRAP}'>{html.escape(verdict)}</td>"
            f"<td style='width:168px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#334155'>{html.escape(strategy_text)}</td>"
            f"<td style='width:82px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'>{html.escape(option_text or 'n/a')}</td>"
            f"<td align='right' style='width:82px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'>{_fmt(execution.get('strike'))}</td>"
            f"<td align='right' style='width:82px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'>{_fmt(execution.get('premium'))}</td>"
            f"<td align='right' style='width:92px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'>{_fmt(execution.get('breakeven'))}</td>"
            f"<td style='width:128px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'>{html.escape(_options_expiry_text(execution))}</td>"
            f"<td align='right' style='width:60px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'>{_fmt(execution.get('iv_pct'), 1)}</td>"
            f"<td style='width:104px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'>{html.escape(_options_greek_text(execution))}</td>"
            f"<td align='right' style='width:86px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'>{_fmt(execution.get('expected_move'))}</td>"
            f"<td style='width:132px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px'>{html.escape(str(execution.get('oi_wall') or 'n/a'))}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#475569'>{html.escape(notes)}</td>"
            "</tr>"
        )
    if not body:
        body.append(
            "<tr><td colspan='13' style='padding:10px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#64748b'>"
            "No tracked symbols available for options execution.</td></tr>"
        )
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse;border:1px solid #dbe3ef">
      <tr bgcolor="#312e81">
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff;{EMAIL_NOWRAP}">Symbol</th>
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff;{EMAIL_NOWRAP}">Verdict</th>
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff">Strategy</th>
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff;{EMAIL_NOWRAP}">Option</th>
        <th align="right" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff;{EMAIL_NOWRAP}">Strike</th>
        <th align="right" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff;{EMAIL_NOWRAP}">Premium</th>
        <th align="right" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff;{EMAIL_NOWRAP}">Breakeven</th>
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff;{EMAIL_NOWRAP}">Exp/DTE</th>
        <th align="right" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff;{EMAIL_NOWRAP}">IV</th>
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff;{EMAIL_NOWRAP}">Delta/Theta</th>
        <th align="right" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff;{EMAIL_NOWRAP}">1SD Move</th>
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff">OI Wall</th>
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff">Notes</th>
      </tr>
      {''.join(body)}
    </table>
    """


def _cycle_change_names(changes: dict[str, Any], key: str) -> str:
    return ", ".join(item.get("symbol", "") for item in (changes.get(key) or []) if item.get("symbol")) or "none"


def _cycle_changes_table(state: LiveDashboardState) -> str:
    changes = state.cycle_changes or {}
    status_changes = "; ".join(
        f"{item.get('symbol')} {item.get('from')} -> {item.get('to')}"
        for item in (changes.get("status_changes") or [])
    ) or "none"
    rows = [
        ("New", _cycle_change_names(changes, "new_added")),
        ("Removed", _cycle_change_names(changes, "removed")),
        ("Forming", _cycle_change_names(changes, "forming")),
        ("Confirmed", _cycle_change_names(changes, "confirmed")),
        ("Active", _cycle_change_names(changes, "active")),
        ("Changed", status_changes),
    ]
    body = "".join(
        "<tr>"
        f"<td valign='top' style='width:95px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:bold;color:#334155'>{html.escape(label)}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#111827'>{html.escape(value)}</td>"
        "</tr>"
        for label, value in rows
    )
    return (
        "<table width='100%' cellpadding='0' cellspacing='0' role='presentation' style='border-collapse:collapse;border:1px solid #dbe3ef'>"
        f"{body}</table>"
    )


def _inline_commentary_html(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(
        r"`(.+?)`",
        r"<code style='font-family:Menlo,Consolas,monospace;font-size:12px'>\1</code>",
        escaped,
    )
    return escaped


def _clean_commentary_line(line: str) -> str:
    cleaned = line.strip()
    cleaned = re.sub(r"^#{1,6}\s*", "", cleaned)
    cleaned = re.sub(r"^\*\*(.*?)\*\*$", r"\1", cleaned)
    cleaned = re.sub(r"^\*(.*?)\*$", r"\1", cleaned)
    cleaned = re.sub(r"^\s*[-*]\s+", "", cleaned)
    return cleaned.strip()


def _is_commentary_heading(raw_line: str, cleaned: str) -> bool:
    normalized = cleaned.rstrip(":").lower()
    if raw_line.lstrip().startswith("#"):
        return True
    return normalized in {
        "current read from the tracker",
        "cycle changes",
        "new added",
        "removed",
        "forming",
        "confirmed",
        "active",
        "status changes this cycle",
        "meaningful change",
        "best actionable names",
        "closest micro-level watches",
        "higher rr watch names",
        "watch next",
        "source health",
        "key live states",
        "locked near-trigger setups still on screen",
    }


def _commentary_html(commentary: str) -> str:
    lines = [line.rstrip() for line in (commentary or "").splitlines()]
    blocks = []
    previous_blank = False
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if not previous_blank:
                blocks.append("<tr><td style='height:6px;line-height:6px;font-size:6px'>&nbsp;</td></tr>")
            previous_blank = True
            continue
        previous_blank = False
        if re.fullmatch(r"[-_]{5,}", line):
            blocks.append(
                "<tr><td style='padding:8px 0'>"
                "<table width='100%' cellpadding='0' cellspacing='0' role='presentation' style='border-collapse:collapse'>"
                "<tr><td style='border-top:1px solid #e5e7eb;font-size:1px;line-height:1px'>&nbsp;</td></tr>"
                "</table></td></tr>"
            )
            continue
        bullet_match = re.match(r"^(?:[•●▪]|[-*])\s+(.*)$", line)
        if bullet_match:
            bullet = _clean_commentary_line(bullet_match.group(1))
            if not bullet:
                continue
            blocks.append(
                "<tr><td style='padding:3px 0'>"
                "<table width='100%' cellpadding='0' cellspacing='0' role='presentation' style='border-collapse:collapse'>"
                "<tr>"
                "<td valign='top' style='width:16px;padding:0 4px 0 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#0f766e'>&bull;</td>"
                f"<td style='font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#334155;line-height:18px'>{_inline_commentary_html(bullet)}</td>"
                "</tr>"
                "</table>"
                "</td></tr>"
            )
            continue
        cleaned = _clean_commentary_line(line)
        if not cleaned:
            continue
        is_heading = _is_commentary_heading(line, cleaned)
        style = (
            "font-size:14px;font-weight:bold;color:#0f172a;padding:9px 0 4px;line-height:18px"
            if is_heading
            else "font-size:13px;color:#334155;padding:2px 0;line-height:18px"
        )
        blocks.append(
            f"<tr><td style='font-family:Arial,Helvetica,sans-serif;{style}'>{_inline_commentary_html(cleaned)}</td></tr>"
        )
    if not blocks:
        blocks.append(
            "<tr><td style='font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#64748b'>No commentary generated for this cycle.</td></tr>"
        )
    return "<table width='100%' cellpadding='0' cellspacing='0' role='presentation' style='border-collapse:collapse'>" + "".join(blocks) + "</table>"


def _source_health_html(state: LiveDashboardState) -> str:
    source = " | ".join(state.source_health) if state.source_health else "n/a"
    return (
        "<table width='100%' cellpadding='0' cellspacing='0' role='presentation' style='border-collapse:collapse;background:#f8fafc;border:1px solid #dbe3ef'>"
        f"<tr><td style='padding:10px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#475569;{EMAIL_NOWRAP}'>{html.escape(source)}</td></tr>"
        "</table>"
    )


def _email_short_text(value: Any, *, limit: int = 130) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def _email_candidate_gate(item: AlertCandidate) -> str:
    decision = item.decision or {}
    action = str(decision.get("final_action") or "").strip()
    suitability = str(decision.get("options_suitability") or "").strip()
    score = decision.get("decision_score")
    parts = [part for part in [action, suitability] if part]
    if score is not None:
        parts.append(f"score {score}")
    return " / ".join(parts) or "watch gate"


def _compact_candidate_table(items: list[AlertCandidate], empty_text: str, *, limit: int = 7) -> str:
    rows = []
    for item in items[:limit]:
        side_color = "#047857" if item.side == "LONG" else "#b91c1c" if item.side == "SHORT" else "#475569"
        gate = _email_candidate_gate(item)
        levels = (
            f"Trig {_fmt(item.trigger)} | Stop {_fmt(item.stop)} | T1 {_fmt(item.target)} | RR {_fmt(item.rr, 1)}"
        )
        read = " - ".join(
            part
            for part in [
                _email_short_text(item.status, limit=48),
                _email_short_text(item.strategy, limit=60),
                _email_short_text(item.note, limit=110),
            ]
            if part
        )
        rows.append(
            "<tr>"
            f"<td valign='top' style='width:112px;padding:9px 8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'><b>{html.escape(item.symbol)}</b><br><span style='color:{side_color};font-weight:bold'>{html.escape(item.side)}</span></td>"
            f"<td valign='top' style='width:120px;padding:9px 8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'>{_fmt(item.last_price)}<br><span style='color:#64748b'>{_fmt_pct(item.pct_change)}</span></td>"
            f"<td valign='top' style='width:220px;padding:9px 8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#334155;line-height:18px'>{html.escape(levels)}</td>"
            f"<td valign='top' style='padding:9px 8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#111827;line-height:18px;{EMAIL_WRAP}'><b>{html.escape(gate)}</b><br><span style='color:#475569'>{html.escape(read)}</span></td>"
            "</tr>"
        )
    if not rows:
        rows.append(
            "<tr><td colspan='4' style='padding:11px 8px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#64748b'>"
            f"{html.escape(empty_text)}</td></tr>"
        )
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse;border:1px solid #dbe3ef;background:#ffffff">
      <tr bgcolor="#f1f5f9">
        <th align="left" style="width:112px;padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#334155;{EMAIL_NOWRAP}">Symbol</th>
        <th align="left" style="width:120px;padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#334155;{EMAIL_NOWRAP}">LTP</th>
        <th align="left" style="width:220px;padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#334155">Levels</th>
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#334155">Gate / Read</th>
      </tr>
      {''.join(rows)}
    </table>
    """


def _compact_sharp_movers_html(rows: list[TrackedSymbolState], *, limit: int = 6) -> str:
    movers = collect_sharp_movers(rows, limit=limit)
    if not movers:
        return _html_empty_row("No tracked name crossed the sharp-move threshold.")
    body = []
    for item in movers:
        move = str(item.get("move") or "n/a")
        color = "#047857" if "Rise" in move else "#b91c1c"
        read = " | ".join(
            part
            for part in [
                _email_short_text(item.get("level_state"), limit=44),
                _email_short_text(item.get("read"), limit=80),
            ]
            if part
        )
        body.append(
            "<tr>"
            f"<td style='width:108px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'><b>{html.escape(str(item.get('symbol') or 'n/a'))}</b></td>"
            f"<td style='width:112px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:{color};font-weight:bold;{EMAIL_NOWRAP}'>{html.escape(move)}</td>"
            f"<td style='width:120px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'>{_fmt_pct(item.get('pct_change'))} / {_fmt(item.get('last_price'))}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#334155;line-height:18px;{EMAIL_WRAP}'>{html.escape(read)}</td>"
            "</tr>"
        )
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse;border:1px solid #dbe3ef;background:#ffffff">
      <tr bgcolor="#fff7ed">
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#7c2d12">Symbol</th>
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#7c2d12">Move</th>
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#7c2d12">Chg / LTP</th>
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#7c2d12">Read</th>
      </tr>
      {''.join(body)}
    </table>
    """


def _compact_tracker_html(state: LiveDashboardState | None, *, limit: int = 7) -> str:
    if not state or not state.tracked_symbols:
        return _html_empty_row("No tracker rows available for this cycle.")
    rows = []
    for row in state.tracked_symbols[:limit]:
        decision = row.decision_context or {}
        action = str(decision.get("final_action") or "WATCH").strip()
        suitability = str(decision.get("options_suitability") or "").strip()
        gate = " / ".join(part for part in [action, suitability] if part)
        levels = f"Trig {_fmt(row.trigger)} | Stop {_fmt(row.invalidation)} | T1 {_tracker_target_text(row)}"
        read = " - ".join(
            part
            for part in [
                _dashboard_read(row),
                levels,
                _email_short_text(row.strategy, limit=60),
            ]
            if part
        )
        rows.append(
            "<tr>"
            f"<td style='width:110px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'><b>{html.escape(row.symbol)}</b><br><span style='color:#64748b'>{_fmt(row.last_price)} / {_fmt_pct(row.pct_change)}</span></td>"
            f"<td style='width:155px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:bold;color:#334155;{EMAIL_WRAP}'>{html.escape(gate or 'watch')}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#334155;line-height:18px;{EMAIL_WRAP}'>{html.escape(_email_short_text(read, limit=180))}</td>"
            "</tr>"
        )
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse;border:1px solid #dbe3ef;background:#ffffff">
      <tr bgcolor="#f1f5f9">
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#334155">Symbol</th>
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#334155">Gate</th>
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#334155">Read</th>
      </tr>
      {''.join(rows)}
    </table>
    """


def _compact_options_execution_html(rows: list[TrackedSymbolState], *, limit: int = 6) -> str:
    selected = list(rows[:limit])
    if not selected:
        return _html_empty_row("No alert-qualified option rows.")
    body = []
    for row in selected:
        execution = _options_execution(row)
        verdict = str(execution.get("verdict") or "NO OPTIONS TRADE")
        color = "#047857" if verdict.startswith("BUY") else "#92400e" if verdict == "USE SPREAD" else "#991b1b"
        contract = " ".join(
            part
            for part in [
                str(execution.get("option_type") or _option_type_for_direction(_option_direction(row))),
                str(execution.get("moneyness") or "").strip(),
                _fmt(execution.get("strike")),
            ]
            if part and part != "n/a"
        ) or "n/a"
        metrics = (
            f"Prem {_fmt(execution.get('premium'))} | BE {_fmt(execution.get('breakeven'))} | "
            f"{html.escape(_options_expiry_text(execution))} | IV {_fmt(execution.get('iv_pct'), 1)}"
        )
        notes = _email_short_text(_options_notes(execution), limit=150)
        body.append(
            "<tr>"
            f"<td style='width:108px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'><b>{html.escape(row.symbol)}</b></td>"
            f"<td style='width:145px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:bold;color:{color};{EMAIL_WRAP}'>{html.escape(verdict)}<br><span style='font-weight:normal;color:#475569'>{html.escape(_options_strategy_text(execution))}</span></td>"
            f"<td style='width:210px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#334155;line-height:18px;{EMAIL_WRAP}'>{html.escape(contract)}<br>{metrics}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#475569;line-height:18px;{EMAIL_WRAP}'>{html.escape(notes)}</td>"
            "</tr>"
        )
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse;border:1px solid #dbe3ef;background:#ffffff">
      <tr bgcolor="#eef2ff">
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#3730a3">Symbol</th>
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#3730a3">Verdict</th>
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#3730a3">Contract</th>
        <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#3730a3">Risk Notes</th>
      </tr>
      {''.join(body)}
    </table>
    """


def _compact_cycle_changes_html(state: LiveDashboardState | None) -> str:
    if not state:
        return _html_empty_row("No cycle-change state available.")
    changes = state.cycle_changes or {}
    summary = [
        ("New", _cycle_change_names(changes, "new_added")),
        ("Active", _cycle_change_names(changes, "active")),
        ("Changed", "; ".join(
            f"{item.get('symbol')} {item.get('from')} -> {item.get('to')}"
            for item in (changes.get("status_changes") or [])
        ) or "none"),
    ]
    rows = "".join(
        "<tr>"
        f"<td style='width:90px;padding:7px 8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:bold;color:#334155'>{html.escape(label)}</td>"
        f"<td style='padding:7px 8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#475569;{EMAIL_WRAP}'>{html.escape(_email_short_text(value, limit=220))}</td>"
        "</tr>"
        for label, value in summary
    )
    return (
        "<table width='100%' cellpadding='0' cellspacing='0' role='presentation' style='border-collapse:collapse;border:1px solid #dbe3ef;background:#ffffff'>"
        f"{rows}</table>"
    )


def _compact_commentary_html(commentary: str, *, max_lines: int = 14, max_chars: int = 1800) -> str:
    kept: list[str] = []
    total = 0
    for line in (commentary or "").splitlines():
        cleaned = line.rstrip()
        if not cleaned.strip() and (not kept or not kept[-1].strip()):
            continue
        next_total = total + len(cleaned)
        if len(kept) >= max_lines or next_total > max_chars:
            kept.append("... commentary truncated for email readability; see the cycle log for full detail.")
            break
        kept.append(cleaned)
        total = next_total
    return _commentary_html("\n".join(kept))


def build_alert_email_body(
    candidates: list[AlertCandidate],
    *,
    market_context: str,
    commentary: str,
    as_of: datetime,
    email_every_mins: int = 0,
    state: LiveDashboardState | None = None,
    fresh_candidates: list[AlertCandidate] | None = None,
) -> str:
    def _sort_key(item: AlertCandidate) -> tuple[int, float]:
        status = (item.status or "").lower()
        bucket = 0 if "active" in status or "t1 hit" in status else 1
        return (bucket, -(item.rr or 0.0))

    ranked = sorted(candidates, key=_sort_key)
    stance_fresh_candidates = list(fresh_candidates) if fresh_candidates is not None else ranked
    active = [item for item in ranked if "active" in (item.status or "").lower() or "t1 hit" in (item.status or "").lower()]
    watch = [item for item in ranked if item not in active]
    top_names = ", ".join(item.symbol for item in ranked[:5]) or "No active candidates"
    cadence = f"{email_every_mins}-minute scheduled update" if email_every_mins > 0 else "trigger update"
    use_candidate_commentary = not commentary or commentary.strip().lower() == "commentary"
    dashboard_commentary = build_email_commentary(
        ranked,
        market_context=market_context,
        commentary=commentary,
    ) if use_candidate_commentary else commentary
    cycle_number = state.cycle if state else "n/a"
    tracker_rows_count = len(state.tracked_symbols) if state else 0
    changed_count = len((state.cycle_changes or {}).get("status_changes") or []) if state else 0
    stance = build_trading_stance(
        state=state or LiveDashboardState(),
        candidates=ranked,
        fresh_candidates=stance_fresh_candidates,
        config=None,
    )
    stance_color = {
        "TRADE": "#166534",
        "WAIT": "#92400e",
        "NO_TRADE": "#991b1b",
    }.get(str(stance.get("label") or ""), "#334155")
    stance_bg = {
        "TRADE": "#ecfdf5",
        "WAIT": "#fffbeb",
        "NO_TRADE": "#fef2f2",
    }.get(str(stance.get("label") or ""), "#f8fafc")
    stance_reasons = "; ".join(str(item) for item in (stance.get("reasons") or [])) or "n/a"
    stance_html = f"""
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse;background:{stance_bg};border:1px solid #dbe3ef">
      <tr>
        <td style="width:150px;padding:11px 12px;font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:bold;color:#64748b;text-transform:uppercase;{EMAIL_NOWRAP}">Trading Stance</td>
        <td style="padding:11px 12px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#334155">
          <b style="color:{stance_color};font-size:15px">{html.escape(str(stance.get('label') or 'n/a'))}</b>
          <span style="color:#111827"> - {html.escape(str(stance.get('headline') or 'n/a'))}</span><br>
          <span style="color:#475569">{html.escape(str(stance.get('action') or 'n/a'))}</span><br>
          <span style="color:#64748b;font-size:12px">Reasons: {html.escape(stance_reasons)}</span>
        </td>
      </tr>
    </table>
    """

    stats_html = "".join(
        "<td width='25%' valign='top' style='padding:9px;border:1px solid #dbe3ef;background:#f8fafc'>"
        f"<div style='font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#64748b;text-transform:uppercase'>{html.escape(label)}</div>"
        f"<div style='font-family:Arial,Helvetica,sans-serif;font-size:16px;font-weight:bold;color:#111827;margin-top:3px'>{html.escape(value)}</div>"
        "</td>"
        for label, value in (
            ("Cycle", str(cycle_number)),
            ("Tracked", str(tracker_rows_count)),
            ("Candidates", str(len(candidates))),
            ("Changed", str(changed_count)),
        )
    )
    priority_table = _compact_candidate_table(ranked, "No qualifying candidates at this cycle.")
    active_table = _compact_candidate_table(active, "No active trades passed the alert filter.", limit=5)
    watch_table = _compact_candidate_table(watch, "No near-trigger watches passed the alert filter.", limit=5)
    tracker_table = _compact_tracker_html(state)
    sharp_movers = _compact_sharp_movers_html(state.tracked_symbols) if state else _html_empty_row("Sharp mover context unavailable.")
    options_source_rows = state.tracked_symbols if state else []
    options_execution = _compact_options_execution_html(options_source_rows)
    cycle_changes = _compact_cycle_changes_html(state)
    narrative = _compact_commentary_html(dashboard_commentary)
    source_health = _source_health_html(state) if state else _html_empty_row("Source health unavailable.")
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation" bgcolor="#f4f7fb" style="border-collapse:collapse;background:#f4f7fb">
      <tr>
        <td align="center" style="padding:18px 10px">
          <table width="{EMAIL_TABLE_WIDTH}" cellpadding="0" cellspacing="0" role="presentation" style="width:100%;max-width:{EMAIL_TABLE_WIDTH}px;border-collapse:collapse;background:#ffffff;border:1px solid #dbe3ef">
            <tr>
              <td bgcolor="#0f172a" style="padding:16px 18px;background:#0f172a">
                <div style="font-family:Arial,Helvetica,sans-serif;font-size:20px;font-weight:bold;color:#ffffff">Agent Adda Intraday Live Commentary</div>
                <div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#cbd5e1;margin-top:5px">
                  {as_of:%Y-%m-%d %H:%M:%S} IST | {html.escape(cadence)}
                </div>
              </td>
            </tr>
            <tr>
              <td style="padding:12px 18px 0">
                <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse;background:#f8fafc;border:1px solid #dbe3ef">
                  <tr><td style="padding:10px 12px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#334155;line-height:18px;{EMAIL_WRAP}"><b>Market:</b> {html.escape(market_context)}</td></tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:14px 18px 6px">
                <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse"><tr>{stats_html}</tr></table>
              </td>
            </tr>
            {_html_section_title("Trading Stance")}
            <tr><td style="padding:0 18px 16px">{stance_html}</td></tr>
            {_html_section_title("Sharp Movers")}
            <tr><td style="padding:0 18px 16px">{sharp_movers}</td></tr>
            {_html_section_title("Current Read From The Tracker")}
            <tr><td style="padding:0 18px 16px">{tracker_table}</td></tr>
            {_html_section_title("Options Execution")}
            <tr><td style="padding:0 18px 16px">{options_execution}</td></tr>
            {_html_section_title("Cycle Changes")}
            <tr><td style="padding:0 18px 16px">{cycle_changes}</td></tr>
            {_html_section_title("Narrative / Commentary")}
            <tr>
              <td style="padding:0 18px 16px">
                <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse;background:#ffffff;border:1px solid #dbe3ef">
                  <tr><td style="padding:10px 14px 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:bold;color:#64748b">State-Machine Commentary</td></tr>
                  <tr><td style="padding:12px 14px">{narrative}</td></tr>
                </table>
              </td>
            </tr>
            {_html_section_title("Source Health")}
            <tr><td style="padding:0 18px 16px">{source_health}</td></tr>
            {_html_section_title("Alert Candidates")}
            <tr>
              <td style="padding:8px 18px 14px">
                <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse;background:#ecfdf5;border-left:4px solid #0f766e">
                  <tr>
                    <td style="padding:11px 12px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#064e3b">
                      <b>Priority:</b> {html.escape(top_names)}. Confirm trigger hold and invalidation before acting.
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            {_html_section_title("Priority Queue")}
            <tr><td style="padding:0 18px 16px">{priority_table}</td></tr>
            {_html_section_title("Active Trades")}
            <tr><td style="padding:0 18px 16px">{active_table}</td></tr>
            {_html_section_title("Near Trigger / Watch")}
            <tr><td style="padding:0 18px 16px">{watch_table}</td></tr>
            {_html_section_title("Risk Rules")}
            <tr>
              <td style="padding:0 18px 18px">
                <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse">
                  <tr><td style="padding:3px 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#475569;line-height:18px">- Active means the state machine sees the trigger already engaged; near-trigger means wait for confirmation.</td></tr>
                  <tr><td style="padding:3px 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#475569;line-height:18px">- Stops are invalidation references, not guaranteed execution prices.</td></tr>
                  <tr><td style="padding:3px 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#475569;line-height:18px">- Skip names where spread, liquidity, option premium, or volatility makes execution poor.</td></tr>
                </table>
              </td>
            </tr>
            <tr>
              <td bgcolor="#f8fafc" style="padding:12px 18px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#64748b;background:#f8fafc;border-top:1px solid #dbe3ef;line-height:18px">
                Research only. Not investment advice. Validate liquidity, spread, option premium, and execution risk before acting.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
    """


def build_alert_email_plain_body(
    candidates: list[AlertCandidate],
    *,
    market_context: str,
    commentary: str,
    as_of: datetime,
    email_every_mins: int = 0,
    state: LiveDashboardState | None = None,
    fresh_candidates: list[AlertCandidate] | None = None,
) -> str:
    """Plain-text alert body for Apple Mail, whose AppleScript API does not send HTML reliably."""
    def _sort_key(item: AlertCandidate) -> tuple[int, float]:
        status = (item.status or "").lower()
        bucket = 0 if "active" in status or "t1 hit" in status else 1
        return (bucket, -(item.rr or 0.0))

    ranked = sorted(candidates, key=_sort_key)
    stance_fresh_candidates = list(fresh_candidates) if fresh_candidates is not None else ranked
    stance = build_trading_stance(
        state=state or LiveDashboardState(),
        candidates=ranked,
        fresh_candidates=stance_fresh_candidates,
        config=None,
    )
    cadence = f"{email_every_mins}-minute scheduled update" if email_every_mins > 0 else "trigger update"
    lines = [
        "AGENT ADDA INTRADAY LIVE COMMENTARY",
        f"As of: {as_of:%Y-%m-%d %H:%M:%S} IST | {cadence}",
        f"Market: {market_context}",
        "",
        f"Trading stance: {stance.get('label') or 'n/a'} - {stance.get('headline') or 'n/a'}",
        f"Action: {stance.get('action') or 'n/a'}",
        "Reasons: " + ("; ".join(str(item) for item in (stance.get("reasons") or [])) or "n/a"),
    ]

    if state:
        lines.extend([
            "",
            f"Cycle: {state.cycle} | Tracked: {len(state.tracked_symbols)} | Candidates: {len(candidates)}",
        ])

    movers = collect_sharp_movers(state.tracked_symbols if state else [], limit=6)
    lines.extend(["", "Sharp movers:"])
    if movers:
        for item in movers:
            lines.append(
                "- {symbol}: {move}, {chg} at {ltp}; {read}".format(
                    symbol=item.get("symbol") or "n/a",
                    move=item.get("move") or "n/a",
                    chg=_fmt_pct(item.get("pct_change")),
                    ltp=_fmt(item.get("last_price")),
                    read=_email_short_text(
                        " | ".join(
                            part
                            for part in [item.get("level_state"), item.get("read")]
                            if part
                        ),
                        limit=130,
                    ),
                )
            )
    else:
        lines.append("- None crossed the sharp-move threshold.")

    lines.extend(["", "Alert candidates:"])
    if ranked:
        for item in ranked[:7]:
            lines.append(
                "- {symbol} {side} {status}: LTP {ltp} ({chg}); trigger {trig}, stop {stop}, T1 {target}, RR {rr}. Gate: {gate}. {read}".format(
                    symbol=item.symbol,
                    side=item.side,
                    status=item.status,
                    ltp=_fmt(item.last_price),
                    chg=_fmt_pct(item.pct_change),
                    trig=_fmt(item.trigger),
                    stop=_fmt(item.stop),
                    target=_fmt(item.target),
                    rr=_fmt(item.rr, 1),
                    gate=_email_candidate_gate(item),
                    read=_email_short_text(" - ".join(part for part in [item.strategy, item.note] if part), limit=140),
                )
            )
    else:
        lines.append("- No active candidate passed the trade gate.")

    tracked = state.tracked_symbols if state else []
    lines.extend(["", "Tracker read:"])
    if tracked:
        for row in tracked[:7]:
            decision = row.decision_context or {}
            gate = " / ".join(
                str(part)
                for part in [
                    decision.get("final_action") or "WATCH",
                    decision.get("options_suitability") or "",
                ]
                if part
            )
            lines.append(
                "- {symbol}: {gate}; LTP {ltp} ({chg}); trigger {trig}, stop {stop}, T1 {t1}. {read}".format(
                    symbol=row.symbol,
                    gate=gate,
                    ltp=_fmt(row.last_price),
                    chg=_fmt_pct(row.pct_change),
                    trig=_fmt(row.trigger),
                    stop=_fmt(row.invalidation),
                    t1=_tracker_target_text(row),
                    read=_email_short_text(_dashboard_read(row), limit=130),
                )
            )
    else:
        lines.append("- No tracker rows available.")

    lines.extend(["", "Options execution:"])
    option_rows = tracked[:6]
    if option_rows:
        for row in option_rows:
            execution = _options_execution(row)
            lines.append(
                "- {symbol}: {verdict}; {strategy}; {typ} {strike}; premium {premium}, BE {be}, {expiry}, IV {iv}. {notes}".format(
                    symbol=row.symbol,
                    verdict=execution.get("verdict") or "NO OPTIONS TRADE",
                    strategy=_email_short_text(_options_strategy_text(execution), limit=80),
                    typ=execution.get("option_type") or _option_type_for_direction(_option_direction(row)),
                    strike=_fmt(execution.get("strike")),
                    premium=_fmt(execution.get("premium")),
                    be=_fmt(execution.get("breakeven")),
                    expiry=_options_expiry_text(execution),
                    iv=_fmt(execution.get("iv_pct"), 1),
                    notes=_email_short_text(_options_notes(execution), limit=130),
                )
            )
    else:
        lines.append("- No alert-qualified option rows.")

    if commentary and commentary.strip().lower() != "commentary":
        cleaned_commentary = []
        for line in commentary.splitlines():
            line = _clean_commentary_line(line)
            if line:
                cleaned_commentary.append(line)
            if len(cleaned_commentary) >= 6:
                break
        if cleaned_commentary:
            lines.extend(["", "Commentary:"])
            lines.extend(f"- {_email_short_text(line, limit=180)}" for line in cleaned_commentary)

    lines.extend([
        "",
        "Risk rules:",
        "- Active means the state machine sees the trigger already engaged; near-trigger means wait for confirmation.",
        "- Stops are invalidation references, not guaranteed execution prices.",
        "- Skip if spread, liquidity, option premium, volatility, or candle quality is poor.",
        "",
        "Research only. Not investment advice.",
    ])
    return "\n".join(lines).strip()


def dispatch_alert_email(
    candidates: list[AlertCandidate],
    *,
    state: LiveDashboardState,
    config: IntradayAlertConfig,
) -> dict[str, Any]:
    recipients = _load_recipients(config.report_key)
    to_addrs = recipients.get("to") or []
    bcc_addrs = recipients.get("bcc") or []
    if not to_addrs and not bcc_addrs:
        return {"ok": False, "message": f"no recipients configured for {config.report_key}"}

    subject = (
        f"Agent Adda Intraday F&O Alert: "
        f"{', '.join(_candidate_subject_label(item) for item in candidates[:5])}"
    )[:160]
    body_kwargs = dict(
        market_context=state.market_context,
        commentary=state.last_commentary,
        as_of=state.last_updated_at or datetime.now(),
        email_every_mins=config.email_every_mins,
        state=state,
        fresh_candidates=candidates,
    )
    if _email_provider() in {"applemail", "mail", "apple_mail"}:
        plain_body = build_alert_email_plain_body(candidates, **body_kwargs)
        body = (
            "<pre style='font-family:Menlo,Consolas,monospace;font-size:13px;"
            "line-height:1.45;white-space:pre-wrap;color:#111827'>"
            f"{html.escape(plain_body)}"
            "</pre>"
        )
    else:
        body = build_alert_email_body(candidates, **body_kwargs)
    if config.dry_run:
        from terminal.email_dispatcher import LOG_DIR

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = LOG_DIR / f"_intraday_alert_preview_{datetime.now():%Y%m%d_%H%M%S}.html"
        path.write_text(body, encoding="utf-8")
        return {"ok": True, "message": f"dry-run preview written to {path}", "subject": subject}

    try:
        status = send_via_outlook(
            subject=subject,
            html_body=body,
            to_addrs=to_addrs,
            bcc_addrs=bcc_addrs,
            attachments=[],
            send_immediately=config.send,
        )
    except Exception as exc:
        return {"ok": False, "message": f"email dispatch failed: {exc}", "subject": subject}
    return {"ok": True, "message": status, "subject": subject}


def _email_delivery_confirmation(email_result: dict[str, Any], config: IntradayAlertConfig) -> str:
    """Human-readable terminal confirmation for real email sends."""
    if not email_result.get("ok") or config.dry_run or not config.send:
        return ""
    subject = str(email_result.get("subject") or "").strip()
    return f"Email sent successfully: {subject}" if subject else "Email sent successfully."


def _is_email_cadence_due(last_email_at: datetime | None, *, now: datetime, every_mins: int) -> bool:
    if every_mins <= 0:
        return False
    if last_email_at is None:
        return True
    return (now - last_email_at).total_seconds() >= every_mins * 60


def run_intraday_alert_commentary(config: IntradayAlertConfig, *, backend=None, console: Console | None = None) -> LiveDashboardState:
    con = console or Console(highlight=False, force_terminal=True)
    state = LiveDashboardState()
    seen: set[tuple[str, str, str]] = set()
    last_email_at: datetime | None = None
    last_full_rescan_at: datetime | None = None
    tracking_symbols: list[str] = []
    cycles_done = 0
    log_path = config.log_path or default_cycle_log_path()
    latest_snapshot_path = config.latest_snapshot_path or default_latest_snapshot_path()
    edge_memory_rows: list[dict[str, Any]] | None = None

    while True:
        now = datetime.now()
        session_status = market_session_status(now)
        if not session_status.is_open:
            state = _build_market_closed_cycle_state(state, session_status)
            candidates: list[AlertCandidate] = []
            fresh: list[AlertCandidate] = []
            email_result = _market_closed_email_result(session_status)
            con.print(render_intraday_alert_dashboard(state, candidates, fresh, config))
            con.print(f"[yellow]{session_status.status_label}[/yellow]")
            con.print("[dim]Intraday alert analysis skipped. No alert email or draft was created.[/dim]")

            if config.write_cycle_log:
                record = build_intraday_cycle_log_record(
                    state=state,
                    candidates=candidates,
                    fresh_candidates=fresh,
                    email_result=email_result,
                    config=config,
                )
                write_intraday_cycle_log(record, log_path)
                write_intraday_latest_snapshot(
                    state=state,
                    candidates=candidates,
                    fresh_candidates=fresh,
                    email_result=email_result,
                    path=latest_snapshot_path,
                    config=config,
                )
                con.print(f"[dim]Cycle log: {log_path}[/dim]")
                con.print(f"[dim]Latest snapshot: {latest_snapshot_path}[/dim]")

            cycles_done += 1
            if config.cycles is not None and cycles_done >= config.cycles:
                return state
            time.sleep(max(1, config.interval_secs))
            continue

        rescan_mins = _rescan_interval_mins(config)
        full_rescan_due = not tracking_symbols or _is_email_cadence_due(
            last_full_rescan_at,
            now=now,
            every_mins=rescan_mins,
        )
        scan_symbols = config.symbols if full_rescan_due else tracking_symbols
        active_strategies = _active_intraday_strategies(config.strategies, as_of=now)
        cycle = fetch_live_dashboard_cycle(
            LiveDashboardConfig(
                symbols=scan_symbols,
                refresh_secs=config.interval_secs,
                max_cycles=1,
                use_llm=config.use_llm,
                interval=config.candle_interval,
                top_n=len(scan_symbols),
                strategies=active_strategies,
                require_volume=config.require_volume,
                min_volume_ratio=config.min_volume_ratio,
                include_fno=config.include_fno,
            )
        )
        if active_strategies != config.strategies:
            cycle["source_health"].append(
                "strategy_time_gate ok: "
                + ",".join(active_strategies)
            )
        tracked_symbols = cycle["tracked_symbols"]
        if full_rescan_due:
            preselect_limit = min(
                len(tracked_symbols),
                max(config.max_tracked_symbols, config.max_tracked_symbols * 3),
            )
            tracked_symbols = select_tracking_rows(
                tracked_symbols,
                replace(config, max_tracked_symbols=preselect_limit),
            )
        tracked_symbols = enrich_tracked_symbols_with_mtf_levels(
            tracked_symbols,
            interval=config.candle_interval,
        )
        if config.include_fno:
            tracked_symbols = enrich_tracked_symbols_with_fno_context(tracked_symbols)
            cycle["source_health"].append("fno_context ok")
        tracked_symbols = apply_trade_decisions(tracked_symbols, cycle["market_context"])
        if config.include_edge_memory:
            if edge_memory_rows is None:
                edge_memory_rows = load_edge_memory_rows()
            tracked_symbols = apply_edge_memory_to_tracked_symbols(
                tracked_symbols,
                edge_memory_rows,
                timeframe=config.candle_interval,
            )
            cycle["source_health"].append(f"edge_memory ok: {len(edge_memory_rows)}")
        tracked_symbols = apply_trade_timing_score(tracked_symbols, as_of=now)
        if full_rescan_due:
            tracked_symbols = select_tracking_rows(tracked_symbols, config)
            tracking_symbols = [row.symbol for row in tracked_symbols]
            last_full_rescan_at = now
            cycle["source_health"].append(
                f"full universe rescan ok: scanned {len(scan_symbols)}, tracking {len(tracking_symbols)}"
            )
        if config.include_fno:
            tracked_symbols = apply_options_execution_to_tracked_symbols(tracked_symbols)
            cycle["source_health"].append("options_execution ok")
        state = update_live_dashboard_state(
            state,
            market_context=cycle["market_context"],
            tracked_symbols=tracked_symbols,
            source_health=cycle["source_health"],
        )
        state.last_commentary = generate_live_commentary(state, backend, use_llm=config.use_llm)
        candidates = collect_alert_candidates(state.tracked_symbols, config)
        fresh = [item for item in candidates if item.key not in seen]
        con.print(render_intraday_alert_dashboard(state, candidates, fresh, config))

        email_result: dict[str, Any] | None = None
        now = state.last_updated_at or datetime.now()
        cadence_due = _is_email_cadence_due(last_email_at, now=now, every_mins=config.email_every_mins)
        if config.email_every_mins > 0:
            email_candidates = candidates if cadence_due else []
        else:
            email_candidates = fresh
        if email_candidates:
            for item in fresh:
                seen.add(item.key)
            email_result = dispatch_alert_email(email_candidates, state=state, config=config)
            last_email_at = now
            color = "green" if email_result.get("ok") else "yellow"
            con.print(f"[{color}]Email alert: {email_result.get('message')}[/{color}]")
            if email_result.get("subject"):
                con.print(f"[dim]Subject: {email_result.get('subject')}[/dim]")
            delivery_confirmation = _email_delivery_confirmation(email_result, config)
            if delivery_confirmation:
                con.print(f"[bold green]{delivery_confirmation}[/bold green]")
            if config.email_every_mins > 0:
                con.print(f"[dim]Email cadence: every {config.email_every_mins} min; sent {len(email_candidates)} current candidates.[/dim]")
        else:
            for item in fresh:
                seen.add(item.key)
            if config.email_every_mins > 0 and candidates:
                con.print(f"[dim]Email cadence not due; {len(candidates)} current candidates tracked.[/dim]")
            else:
                con.print("[dim]No new trigger alert this cycle.[/dim]")

        if config.write_cycle_log:
            record = build_intraday_cycle_log_record(
                state=state,
                candidates=candidates,
                fresh_candidates=fresh,
                email_result=email_result,
                config=config,
            )
            write_intraday_cycle_log(record, log_path)
            write_intraday_latest_snapshot(
                state=state,
                candidates=candidates,
                fresh_candidates=fresh,
                email_result=email_result,
                path=latest_snapshot_path,
                config=config,
            )
            con.print(f"[dim]Cycle log: {log_path}[/dim]")
            con.print(f"[dim]Latest snapshot: {latest_snapshot_path}[/dim]")

        cycles_done += 1
        if config.cycles is not None and cycles_done >= config.cycles:
            return state
        time.sleep(max(1, config.interval_secs))


def _split_symbols(value: str) -> list[str]:
    return [part.strip().upper() for part in value.replace(";", ",").split(",") if part.strip()]


def _split_strategies(value: str) -> list[str]:
    return [part.strip().lower() for part in value.replace(";", ",").split(",") if part.strip()]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run intraday F&O commentary with trigger email alerts.")
    parser.add_argument("--symbols", default="", help="Comma-separated F&O/index symbols. Saved as the default basket unless --no-remember-symbols is used.")
    parser.add_argument("--interval", type=int, default=60, help="Loop interval in seconds.")
    parser.add_argument("--cycles", type=int, default=1, help="Number of cycles. Use 0 for continuous.")
    parser.add_argument("--candle-interval", default="15m", help="Scanner candle interval, e.g. 5m, 15m, 30m.")
    parser.add_argument("--min-rr", type=float, default=2.0, help="Minimum R:R for email alert.")
    parser.add_argument("--trigger", choices=["active", "near", "active_or_near"], default="active_or_near")
    parser.add_argument("--report-key", default="intraday_alerts", help="Recipient key in config/report_recipients.yml.")
    parser.add_argument("--send", action="store_true", help="Send immediately. Default opens Outlook draft.")
    parser.add_argument("--dry-run", action="store_true", help="Write alert HTML preview only.")
    parser.add_argument("--no-llm", action="store_true", help="Use deterministic commentary.")
    parser.add_argument("--email-every-mins", type=int, default=15, help="Email/draft all current candidates at this cadence; default 15. Use 0 for fresh-trigger-only behavior.")
    parser.add_argument("--rescan-every-mins", type=int, default=0, help="Rescan the full remembered basket at this cadence; 0 follows --email-every-mins.")
    parser.add_argument("--max-tracked-symbols", type=int, default=15, help="Number of best names to actively track after each full rescan.")
    parser.add_argument(
        "--strategies",
        default=",".join(DEFAULT_BREAKOUT_STRATEGIES),
        help="Comma-separated intraday strategy keys. Default: Supertrend breakout, near-breakout volume, VCP, volume, Darvas.",
    )
    parser.add_argument("--min-volume-ratio", type=float, default=1.2, help="Minimum current candle volume ratio for live alert candidates.")
    parser.add_argument("--allow-no-volume", action="store_true", help="Allow signals without volume confirmation.")
    parser.add_argument("--no-fno", action="store_true", help="Disable option-chain/futures context enrichment.")
    parser.add_argument("--no-edge-memory", action="store_true", help="Disable persisted Edge Knowledge Node gating.")
    parser.add_argument("--no-remember-symbols", action="store_true", help="Do not save a provided --symbols basket as the future default.")
    parser.add_argument("--reset-symbols", action="store_true", help="Clear the remembered symbol basket before resolving this run.")
    parser.add_argument("--state-path", default="", help="Override the remembered symbol state file path.")
    parser.add_argument("--no-cycle-log", action="store_true", help="Disable JSONL cycle logging and latest markdown snapshot.")
    parser.add_argument("--log-path", default="", help="Append JSONL cycle records to this path.")
    parser.add_argument("--latest-snapshot-path", default="", help="Write the latest readable markdown snapshot to this path.")
    return parser


def config_from_args(args: argparse.Namespace) -> IntradayAlertConfig:
    state_path = Path(args.state_path).expanduser() if args.state_path else None
    remember_symbols = not args.no_remember_symbols
    if args.reset_symbols:
        clear_intraday_alert_symbols(state_path)

    if args.symbols:
        symbols = _split_symbols(args.symbols)
        if remember_symbols and symbols:
            save_intraday_alert_symbols(symbols, state_path)
    else:
        symbols = _equity_alert_symbols(load_intraday_alert_symbols(state_path))
        if not symbols:
            symbols = _equity_alert_symbols(load_fno_intraday_universe())

    return IntradayAlertConfig(
        symbols=symbols,
        interval_secs=max(1, args.interval),
        cycles=None if args.cycles == 0 else max(1, args.cycles),
        candle_interval=args.candle_interval,
        min_rr=args.min_rr,
        trigger=args.trigger,
        report_key=args.report_key,
        send=args.send,
        dry_run=args.dry_run,
        use_llm=not args.no_llm,
        email_every_mins=max(0, args.email_every_mins),
        rescan_every_mins=max(0, args.rescan_every_mins),
        max_tracked_symbols=max(1, args.max_tracked_symbols),
        strategies=_split_strategies(args.strategies) or list(DEFAULT_BREAKOUT_STRATEGIES),
        require_volume=not args.allow_no_volume,
        min_volume_ratio=max(0.0, args.min_volume_ratio),
        include_fno=not args.no_fno,
        include_edge_memory=not args.no_edge_memory,
        remember_symbols=remember_symbols,
        state_path=state_path,
        write_cycle_log=not args.no_cycle_log,
        log_path=Path(args.log_path).expanduser() if args.log_path else None,
        latest_snapshot_path=Path(args.latest_snapshot_path).expanduser() if args.latest_snapshot_path else None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    backend = None
    if not args.no_llm:
        try:
            from terminal.agent import _detect_backend

            backend = _detect_backend()
        except Exception:
            backend = None
    config = config_from_args(args)
    run_intraday_alert_commentary(config, backend=backend)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
