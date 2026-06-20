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

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from terminal.email_dispatcher import _load_recipients, send_via_outlook
from terminal.live_dashboard import (
    LiveDashboardConfig,
    LiveDashboardState,
    TrackedSymbolState,
    apply_trade_decisions,
    enrich_tracked_symbols_with_fno_context,
    enrich_tracked_symbols_with_mtf_levels,
    fetch_live_dashboard_cycle,
    generate_live_commentary,
    update_live_dashboard_state,
)


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
]


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
        },
        "cycle_changes": state.cycle_changes,
        "tracked_symbols": [_tracked_to_payload(row) for row in state.tracked_symbols],
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
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
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

    commentary = build_email_commentary(
        candidates,
        market_context=state.market_context,
        commentary="commentary",
    )
    source = " | ".join(state.source_health) if state.source_health else "source health unavailable"

    return Group(
        Panel(summary, title="Agent Adda Intraday Alert Dashboard", border_style="bright_blue"),
        table,
        Panel(fresh_text, title="Fresh Alert Candidates", border_style="green" if fresh_candidates else "yellow"),
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
        decision_text = (
            f" Decision {decision.get('final_action', 'n/a')} / "
            f"{decision.get('options_suitability', 'n/a')} "
            f"(score {_fmt(decision.get('decision_score'), 0)})."
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


EMAIL_TABLE_WIDTH = 1280
EMAIL_NOWRAP = "white-space:nowrap"


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


def build_alert_email_body(
    candidates: list[AlertCandidate],
    *,
    market_context: str,
    commentary: str,
    as_of: datetime,
    email_every_mins: int = 0,
    state: LiveDashboardState | None = None,
) -> str:
    def _sort_key(item: AlertCandidate) -> tuple[int, float]:
        status = (item.status or "").lower()
        bucket = 0 if "active" in status or "t1 hit" in status else 1
        return (bucket, -(item.rr or 0.0))

    ranked = sorted(candidates, key=_sort_key)
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

    def _rows(items: list[AlertCandidate]) -> str:
        rows = []
        for item in items:
            side_color = "#16a34a" if item.side == "LONG" else "#dc2626"
            status_color = "#166534" if "active" in (item.status or "").lower() else "#92400e"
            rows.append(
                "<tr>"
                f"<td style='width:86px;padding:9px 8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'><b>{html.escape(item.symbol)}</b></td>"
                f"<td style='width:62px;padding:9px 8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:{side_color};font-weight:bold;{EMAIL_NOWRAP}'>{html.escape(item.side)}</td>"
                f"<td style='width:138px;padding:9px 8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:{status_color};{EMAIL_NOWRAP}'>{html.escape(item.status)}</td>"
                f"<td align='right' style='width:84px;padding:9px 8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'>{_fmt(item.last_price)}</td>"
                f"<td align='right' style='width:64px;padding:9px 8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'>{_fmt_pct(item.pct_change)}</td>"
                f"<td align='right' style='width:92px;padding:9px 8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'>{_fmt(item.trigger)}</td>"
                f"<td align='right' style='width:102px;padding:9px 8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#dc2626;{EMAIL_NOWRAP}'>{_fmt(item.stop)}</td>"
                f"<td align='right' style='width:84px;padding:9px 8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#16a34a;{EMAIL_NOWRAP}'>{_fmt(item.target)}</td>"
                f"<td align='right' style='width:54px;padding:9px 8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'>{_fmt(item.rr, 1)}</td>"
                f"<td style='padding:9px 8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px'>{html.escape(item.strategy or '')}<br><span style='color:#64748b'>{html.escape(item.note or '')}</span></td>"
                "</tr>"
            )
        return "".join(rows)

    def _table(items: list[AlertCandidate], empty_text: str) -> str:
        if not items:
            return (
                "<table width='100%' cellpadding='0' cellspacing='0' role='presentation' style='border-collapse:collapse'>"
                f"<tr><td style='padding:10px 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#64748b'>{html.escape(empty_text)}</td></tr>"
                "</table>"
            )
        return f"""
        <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse;border:1px solid #dbe3ef">
          <thead>
            <tr bgcolor="#0f172a">
              <th align="left" style="width:86px;padding:9px 8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff;{EMAIL_NOWRAP}">Symbol</th>
              <th align="left" style="width:62px;padding:9px 8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff;{EMAIL_NOWRAP}">Side</th>
              <th align="left" style="width:138px;padding:9px 8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff;{EMAIL_NOWRAP}">State</th>
              <th align="right" style="width:84px;padding:9px 8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff;{EMAIL_NOWRAP}">LTP</th>
              <th align="right" style="width:64px;padding:9px 8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff;{EMAIL_NOWRAP}">Chg</th>
              <th align="right" style="width:92px;padding:9px 8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff;{EMAIL_NOWRAP}">Trigger</th>
              <th align="right" style="width:102px;padding:9px 8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff;{EMAIL_NOWRAP}">Invalidation</th>
              <th align="right" style="width:84px;padding:9px 8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff;{EMAIL_NOWRAP}">T1</th>
              <th align="right" style="width:54px;padding:9px 8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff;{EMAIL_NOWRAP}">R:R</th>
              <th align="left" style="padding:9px 8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#ffffff">Setup Read</th>
            </tr>
          </thead>
          <tbody>{_rows(items)}</tbody>
        </table>
        """

    stats_html = "".join(
        "<td width='25%' valign='top' style='padding:10px;border:1px solid #dbe3ef;background:#f8fafc'>"
        f"<div style='font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#64748b;text-transform:uppercase'>{html.escape(label)}</div>"
        f"<div style='font-family:Arial,Helvetica,sans-serif;font-size:18px;font-weight:bold;color:#111827;margin-top:3px'>{html.escape(value)}</div>"
        "</td>"
        for label, value in (
            ("Cycle", str(cycle_number)),
            ("Tracked", str(tracker_rows_count)),
            ("Candidates", str(len(candidates))),
            ("Changed", str(changed_count)),
        )
    )
    ranked_rows = "".join(
        "<tr>"
        f"<td style='width:36px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'><b>{idx}</b></td>"
        f"<td style='width:110px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'><b>{html.escape(item.symbol)}</b></td>"
        f"<td style='width:70px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'>{html.escape(item.side)}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'>{html.escape(item.status)}</td>"
        f"<td align='right' style='width:95px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'>{_fmt(item.trigger)}</td>"
        f"<td align='right' style='width:95px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#dc2626;{EMAIL_NOWRAP}'>{_fmt(item.stop)}</td>"
        f"<td align='right' style='width:95px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#16a34a;{EMAIL_NOWRAP}'>{_fmt(item.target)}</td>"
        f"<td align='right' style='width:56px;padding:8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;{EMAIL_NOWRAP}'>{_fmt(item.rr, 1)}</td>"
        "</tr>"
        for idx, item in enumerate(ranked[:6], 1)
    ) or (
        "<tr><td colspan='8' style='padding:10px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#64748b'>"
        "No qualifying candidates at this cycle.</td></tr>"
    )
    tracker_table = _dashboard_tracker_table(state) if state else _html_empty_row("No tracker rows available for this cycle.")
    cycle_changes = _cycle_changes_table(state) if state else _html_empty_row("No cycle-change state available.")
    narrative = _commentary_html(dashboard_commentary)
    source_health = _source_health_html(state) if state else _html_empty_row("Source health unavailable.")
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation" bgcolor="#f4f7fb" style="border-collapse:collapse;background:#f4f7fb">
      <tr>
        <td align="center" style="padding:18px 10px">
          <table width="{EMAIL_TABLE_WIDTH}" cellpadding="0" cellspacing="0" role="presentation" style="width:{EMAIL_TABLE_WIDTH}px;min-width:{EMAIL_TABLE_WIDTH}px;max-width:{EMAIL_TABLE_WIDTH}px;border-collapse:collapse;background:#ffffff;border:1px solid #dbe3ef">
            <tr>
              <td bgcolor="#0f172a" style="padding:16px 18px;background:#0f172a">
                <div style="font-family:Arial,Helvetica,sans-serif;font-size:20px;font-weight:bold;color:#ffffff">Agent Adda Intraday Live Commentary Dashboard</div>
                <div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#cbd5e1;margin-top:5px">
                  As of {as_of:%Y-%m-%d %H:%M:%S} IST | {html.escape(cadence)} | {html.escape(market_context)}
                </div>
              </td>
            </tr>
            <tr>
              <td style="padding:14px 18px 6px">
                <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse"><tr>{stats_html}</tr></table>
              </td>
            </tr>
            {_html_section_title("Current Read From The Tracker")}
            <tr><td style="padding:0 18px 16px">{tracker_table}</td></tr>
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
            <tr>
              <td style="padding:0 18px 16px">
                <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse;border:1px solid #dbe3ef">
                  <tr bgcolor="#f1f5f9">
                    <th align="left" style="width:36px;padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#334155;{EMAIL_NOWRAP}">#</th>
                    <th align="left" style="width:110px;padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#334155;{EMAIL_NOWRAP}">Symbol</th>
                    <th align="left" style="width:70px;padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#334155;{EMAIL_NOWRAP}">Side</th>
                    <th align="left" style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#334155;{EMAIL_NOWRAP}">State</th>
                    <th align="right" style="width:95px;padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#334155;{EMAIL_NOWRAP}">Trigger</th>
                    <th align="right" style="width:95px;padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#334155;{EMAIL_NOWRAP}">Stop</th>
                    <th align="right" style="width:95px;padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#334155;{EMAIL_NOWRAP}">T1</th>
                    <th align="right" style="width:56px;padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#334155;{EMAIL_NOWRAP}">RR</th>
                  </tr>
                  {ranked_rows}
                </table>
              </td>
            </tr>
            {_html_section_title("Active Trades")}
            <tr><td style="padding:0 18px 16px">{_table(active, "No active trades passed the alert filter.")}</td></tr>
            {_html_section_title("Near Trigger / Watch")}
            <tr><td style="padding:0 18px 16px">{_table(watch, "No near-trigger watches passed the alert filter.")}</td></tr>
            {_html_section_title("Risk Rules")}
            <tr>
              <td style="padding:0 18px 18px">
                <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse">
                  <tr><td style="padding:3px 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#475569;{EMAIL_NOWRAP}">- Active means the state machine sees the trigger already engaged; near-trigger means wait for confirmation.</td></tr>
                  <tr><td style="padding:3px 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#475569;{EMAIL_NOWRAP}">- Stops are invalidation references, not guaranteed execution prices.</td></tr>
                  <tr><td style="padding:3px 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#475569;{EMAIL_NOWRAP}">- Skip names where spread, liquidity, option premium, or volatility makes execution poor.</td></tr>
                </table>
              </td>
            </tr>
            <tr>
              <td bgcolor="#f8fafc" style="padding:12px 18px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#64748b;background:#f8fafc;border-top:1px solid #dbe3ef;{EMAIL_NOWRAP}">
                Research only. Not investment advice. Validate liquidity, spread, option premium, and execution risk before acting.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
    """


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
    body = build_alert_email_body(
        candidates,
        market_context=state.market_context,
        commentary=state.last_commentary,
        as_of=state.last_updated_at or datetime.now(),
        email_every_mins=config.email_every_mins,
        state=state,
    )
    if config.dry_run:
        from terminal.email_dispatcher import LOG_DIR

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = LOG_DIR / f"_intraday_alert_preview_{datetime.now():%Y%m%d_%H%M%S}.html"
        path.write_text(body, encoding="utf-8")
        return {"ok": True, "message": f"dry-run preview written to {path}", "subject": subject}

    status = send_via_outlook(
        subject=subject,
        html_body=body,
        to_addrs=to_addrs,
        bcc_addrs=bcc_addrs,
        attachments=[],
        send_immediately=config.send,
    )
    return {"ok": True, "message": status, "subject": subject}


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

    while True:
        now = datetime.now()
        rescan_mins = _rescan_interval_mins(config)
        full_rescan_due = not tracking_symbols or _is_email_cadence_due(
            last_full_rescan_at,
            now=now,
            every_mins=rescan_mins,
        )
        scan_symbols = config.symbols if full_rescan_due else tracking_symbols
        cycle = fetch_live_dashboard_cycle(
            LiveDashboardConfig(
                symbols=scan_symbols,
                refresh_secs=config.interval_secs,
                max_cycles=1,
                use_llm=config.use_llm,
                interval=config.candle_interval,
                top_n=len(scan_symbols),
                strategies=config.strategies,
                require_volume=config.require_volume,
                min_volume_ratio=config.min_volume_ratio,
                include_fno=config.include_fno,
            )
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
        if full_rescan_due:
            tracked_symbols = select_tracking_rows(tracked_symbols, config)
            tracking_symbols = [row.symbol for row in tracked_symbols]
            last_full_rescan_at = now
            cycle["source_health"].append(
                f"full universe rescan ok: scanned {len(scan_symbols)}, tracking {len(tracking_symbols)}"
            )
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
    parser.add_argument("--email-every-mins", type=int, default=0, help="Email/draft all current candidates at this cadence; 0 keeps fresh-trigger-only behavior.")
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
        symbols = load_intraday_alert_symbols(state_path) or load_fno_intraday_universe()

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
