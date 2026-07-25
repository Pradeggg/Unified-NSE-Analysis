"""Persistent Edge Knowledge Nodes for Agent Adda research.

This module converts validated intraday study evidence into typed, deterministic
knowledge nodes. It intentionally does not run a backtest; it consumes the
already-built research tables and persists their claims with lineage.
"""

from __future__ import annotations

import hashlib
import html as html_lib
import json
import math
import subprocess
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class EdgeRefreshRun:
    refresh_id: str
    evidence_set_id: str
    generated_at: datetime
    source_report: str
    bar_count: int
    symbol_count: int
    trade_count: int
    code_version: str


@dataclass(frozen=True)
class EdgeKnowledgeNode:
    claim_id: str
    setup: str
    direction: str
    timeframe: str
    symbol: str
    session_bucket: str
    vol_regime: str
    pcr_regime: str
    expectancy_r: float | None
    profit_factor: float | None
    win_rate: float | None
    trades_n: int
    wf_status: str
    wf_folds: int
    wf_positive_rate: float | None
    wf_worst_r: float | None
    edge_role: str
    confidence: float
    lineage: dict[str, Any]
    first_seen: datetime
    last_confirmed: datetime | None
    persistence_count: int
    status: str

    def to_record(self) -> dict[str, Any]:
        out = asdict(self)
        out["lineage"] = json.dumps(self.lineage, sort_keys=True, default=str)
        return out


def _norm(value: Any, default: str = "-") -> str:
    text = str(value if value is not None else default).strip()
    if not text or text.lower() in {"nan", "none"}:
        return default
    return text


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", "").strip()
            if value in {"", "-", "nan", "None"}:
                return None
        out = float(value)
        return None if math.isnan(out) else out
    except (TypeError, ValueError):
        return None


def _int(value: Any, default: int = 0) -> int:
    number = _num(value)
    return default if number is None else int(number)


def make_condition_key(
    *,
    symbol: str,
    setup: str,
    timeframe: str,
    direction: str,
    session_bucket: str,
    vol_regime: str,
    pcr_regime: str,
) -> str:
    return "|".join(
        [
            _norm(symbol).upper(),
            _norm(setup),
            _norm(timeframe).lower(),
            _norm(direction).upper(),
            _norm(session_bucket).lower(),
            _norm(vol_regime).lower(),
            _norm(pcr_regime).lower(),
        ]
    )


def make_claim_id(
    *,
    setup: str,
    direction: str,
    timeframe: str,
    symbol: str,
    session_bucket: str,
    vol_regime: str,
    pcr_regime: str,
) -> str:
    condition = make_condition_key(
        symbol=symbol,
        setup=setup,
        timeframe=timeframe,
        direction=direction,
        session_bucket=session_bucket,
        vol_regime=vol_regime,
        pcr_regime=pcr_regime,
    )
    digest = hashlib.sha1(condition.encode("utf-8")).hexdigest()[:16]
    return f"edge_{digest}"


def score_edge_confidence(
    *,
    trades_n: int,
    expectancy_r: float | None,
    profit_factor: float | None,
    wf_status: str,
    wf_positive_rate: float | None,
    wf_worst_r: float | None,
    persistence_count: int,
) -> float:
    sample_score = min(max(trades_n, 0) / 30.0, 1.0) * 0.25
    expectancy = max(min(expectancy_r or 0.0, 0.4), -0.4)
    expectancy_score = max((expectancy + 0.1) / 0.5, 0.0) * 0.18
    pf = profit_factor or 0.0
    pf_score = max(min((pf - 1.0) / 1.0, 1.0), 0.0) * 0.17
    wf_base = 0.22 if wf_status == "confirmed" else 0.08 if wf_status == "unconfirmed" else 0.0
    wf_rate_score = max(min((wf_positive_rate or 0.0) / 100.0, 1.0), 0.0) * 0.10
    worst = wf_worst_r if wf_worst_r is not None else -1.0
    worst_score = max(min((worst + 0.75) / 0.75, 1.0), 0.0) * 0.04
    persistence_score = min(max(persistence_count, 0), 6) / 6.0 * 0.04
    return round(min(sample_score + expectancy_score + pf_score + wf_base + wf_rate_score + worst_score + persistence_score, 1.0), 4)


def classify_edge_status(*, confidence: float, wf_status: str, edge_role: str, persistence_count: int) -> str:
    if edge_role == "edge_diluter" or confidence < 0.25:
        return "retired"
    if wf_status not in {"confirmed", "unconfirmed"}:
        return "decaying" if persistence_count > 0 else "retired"
    if wf_status == "confirmed" and confidence >= 0.80 and persistence_count >= 1:
        return "promoted"
    if wf_status == "confirmed" and confidence >= 0.55:
        return "candidate"
    return "monitoring" if persistence_count > 0 else "candidate"


def _wf_lookup(walk_forward: pd.DataFrame) -> dict[tuple[str, str, str], dict[str, Any]]:
    if walk_forward is None or walk_forward.empty:
        return {}
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in walk_forward.to_dict("records"):
        key = (_norm(row.get("setup")), _norm(row.get("timeframe")).lower(), _norm(row.get("direction")).upper())
        out[key] = row
    return out


def build_edge_nodes(
    *,
    confirmed_symbol_drilldown: pd.DataFrame,
    walk_forward: pd.DataFrame,
    evidence_set_id: str,
    bar_count: int,
    code_version: str,
    generated_at: datetime | None = None,
    persistence_counts: dict[str, int] | None = None,
    session_bucket: str = "opening_drive",
) -> list[EdgeKnowledgeNode]:
    generated_at = generated_at or datetime.now(timezone.utc)
    persistence_counts = persistence_counts or {}
    wf_by_setup = _wf_lookup(walk_forward)
    if confirmed_symbol_drilldown is None or confirmed_symbol_drilldown.empty:
        return []

    nodes: list[EdgeKnowledgeNode] = []
    for row in confirmed_symbol_drilldown.to_dict("records"):
        setup = _norm(row.get("setup"))
        timeframe = _norm(row.get("timeframe")).lower()
        direction = _norm(row.get("direction")).upper()
        symbol = _norm(row.get("symbol")).upper()
        vol_regime = _norm(row.get("best_volatility_regime")).lower()
        pcr_regime = _norm(row.get("best_pcr_regime")).lower()
        edge_role = _norm(row.get("symbol_edge_status"), "neutral").lower()
        wf = wf_by_setup.get((setup, timeframe, direction), {})
        condition_key = make_condition_key(
            symbol=symbol,
            setup=setup,
            timeframe=timeframe,
            direction=direction,
            session_bucket=session_bucket,
            vol_regime=vol_regime,
            pcr_regime=pcr_regime,
        )
        persistence_count = int(persistence_counts.get(condition_key, 0))
        trades_n = _int(row.get("trades"))
        expectancy_r = _num(row.get("expectancy_r"))
        profit_factor = _num(row.get("profit_factor"))
        win_rate = _num(row.get("win_rate"))
        wf_status = _norm(wf.get("walk_forward_status"), "unconfirmed")
        wf_folds = _int(wf.get("folds_tested"))
        wf_positive_rate = _num(wf.get("validation_positive_fold_rate"))
        wf_worst_r = _num(wf.get("worst_validation_r"))
        confidence = score_edge_confidence(
            trades_n=trades_n,
            expectancy_r=expectancy_r,
            profit_factor=profit_factor,
            wf_status=wf_status,
            wf_positive_rate=wf_positive_rate,
            wf_worst_r=wf_worst_r,
            persistence_count=persistence_count,
        )
        status = classify_edge_status(
            confidence=confidence,
            wf_status=wf_status,
            edge_role=edge_role,
            persistence_count=persistence_count,
        )
        nodes.append(
            EdgeKnowledgeNode(
                claim_id=make_claim_id(
                    setup=setup,
                    direction=direction,
                    timeframe=timeframe,
                    symbol=symbol,
                    session_bucket=session_bucket,
                    vol_regime=vol_regime,
                    pcr_regime=pcr_regime,
                ),
                setup=setup,
                direction=direction,
                timeframe=timeframe,
                symbol=symbol,
                session_bucket=session_bucket,
                vol_regime=vol_regime,
                pcr_regime=pcr_regime,
                expectancy_r=expectancy_r,
                profit_factor=profit_factor,
                win_rate=win_rate,
                trades_n=trades_n,
                wf_status=wf_status,
                wf_folds=wf_folds,
                wf_positive_rate=wf_positive_rate,
                wf_worst_r=wf_worst_r,
                edge_role=edge_role,
                confidence=confidence,
                lineage={
                    "evidence_set_id": evidence_set_id,
                    "bar_count": bar_count,
                    "code_version": code_version,
                    "generated_at": generated_at.isoformat(),
                },
                first_seen=generated_at,
                last_confirmed=generated_at if wf_status == "confirmed" and edge_role != "edge_diluter" else None,
                persistence_count=persistence_count + 1,
                status=status,
            )
        )
    return nodes


def get_code_version(project_root: Path | None = None) -> str:
    root = Path(project_root or Path.cwd())
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def make_refresh_run(
    *,
    evidence_set_id: str,
    source_report: str,
    bar_count: int,
    symbol_count: int,
    trade_count: int,
    code_version: str,
    generated_at: datetime | None = None,
) -> EdgeRefreshRun:
    generated_at = generated_at or datetime.now(timezone.utc)
    stamp = generated_at.strftime("%Y%m%d_%H%M%S")
    return EdgeRefreshRun(
        refresh_id=f"refresh_{stamp}",
        evidence_set_id=evidence_set_id,
        generated_at=generated_at,
        source_report=source_report,
        bar_count=bar_count,
        symbol_count=symbol_count,
        trade_count=trade_count,
        code_version=code_version,
    )


def fetch_persistence_counts(conn: Any) -> dict[str, int]:
    sql = """
        SELECT symbol, setup, timeframe, direction, session_bucket, vol_regime, pcr_regime, persistence_count
        FROM research.edge_knowledge_nodes
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return {}
    out: dict[str, int] = {}
    for row in rows:
        key = make_condition_key(
            symbol=row[0],
            setup=row[1],
            timeframe=row[2],
            direction=row[3],
            session_bucket=row[4],
            vol_regime=row[5],
            pcr_regime=row[6],
        )
        out[key] = _int(row[7])
    return out


def fetch_edge_memory_rows(conn: Any) -> list[dict[str, Any]]:
    _create_schema(conn)
    sql = """
        SELECT
            claim_id, setup, direction, timeframe, symbol, session_bucket, vol_regime, pcr_regime,
            expectancy_r, profit_factor, win_rate, trades_n, wf_status, wf_folds, wf_positive_rate,
            wf_worst_r, edge_role, confidence, first_seen, last_confirmed, persistence_count, status, updated_at
        FROM research.edge_knowledge_nodes
        ORDER BY
            CASE status
                WHEN 'promoted' THEN 1
                WHEN 'candidate' THEN 2
                WHEN 'monitoring' THEN 3
                WHEN 'decaying' THEN 4
                WHEN 'retired' THEN 5
                ELSE 6
            END,
            confidence DESC,
            symbol
    """
    cols = [
        "claim_id",
        "setup",
        "direction",
        "timeframe",
        "symbol",
        "session_bucket",
        "vol_regime",
        "pcr_regime",
        "expectancy_r",
        "profit_factor",
        "win_rate",
        "trades_n",
        "wf_status",
        "wf_folds",
        "wf_positive_rate",
        "wf_worst_r",
        "edge_role",
        "confidence",
        "first_seen",
        "last_confirmed",
        "persistence_count",
        "status",
        "updated_at",
    ]
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    return [dict(zip(cols, row, strict=True)) for row in rows]


def summarize_edge_memory(rows: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    role_counts: dict[str, int] = {}
    for row in rows:
        status = _norm(row.get("status"), "unknown")
        role = _norm(row.get("edge_role"), "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        role_counts[role] = role_counts.get(role, 0) + 1
    avg_confidence = None
    if rows:
        avg_confidence = round(sum(_num(row.get("confidence")) or 0.0 for row in rows) / len(rows), 4)
    return {
        "total_edges": len(rows),
        "status_counts": status_counts,
        "role_counts": role_counts,
        "avg_confidence": avg_confidence,
        "active_edges": sum(status_counts.get(s, 0) for s in ("promoted", "candidate", "monitoring")),
        "retired_edges": status_counts.get("retired", 0),
        "latest_update": max((row.get("updated_at") for row in rows if row.get("updated_at")), default=None),
    }


def _fmt_num(value: Any, digits: int = 2) -> str:
    number = _num(value)
    if number is None:
        return "-"
    return f"{number:.{digits}f}"


def _fmt_pct(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "-"
    return f"{number:.1f}%"


def _fmt_dt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def render_edge_memory_markdown(
    rows: list[dict[str, Any]],
    *,
    summary: dict[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> str:
    generated_at = generated_at or datetime.now(timezone.utc)
    summary = summary or summarize_edge_memory(rows)
    status_counts = summary.get("status_counts") or {}
    lines = [
        "# Agent Adda Edge Memory Dashboard",
        "",
        f"Generated: {_fmt_dt(generated_at)}",
        "",
        "## Memory Summary",
        "",
        f"- Total edges: {summary.get('total_edges', 0)}",
        f"- Active edges: {summary.get('active_edges', 0)}",
        f"- Retired/no-trade edges: {summary.get('retired_edges', 0)}",
        f"- Average confidence: {_fmt_num(summary.get('avg_confidence'), 4)}",
        f"- Status mix: "
        + ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items()))
        if status_counts
        else "- Status mix: none",
        "",
        "## Active Edge Memory",
        "",
        "| Symbol | Setup | Dir | TF | Status | Role | Confidence | Trades | Exp R | PF | Win | Persistence | Last Confirmed |",
        "|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    active = [row for row in rows if row.get("status") in {"promoted", "candidate", "monitoring"}]
    if active:
        for row in active:
            lines.append(
                f"| {row.get('symbol')} | {row.get('setup')} | {row.get('direction')} | {row.get('timeframe')} | "
                f"{row.get('status')} | {row.get('edge_role')} | {_fmt_num(row.get('confidence'), 4)} | "
                f"{row.get('trades_n', 0)} | {_fmt_num(row.get('expectancy_r'), 4)} | "
                f"{_fmt_num(row.get('profit_factor'), 2)} | {_fmt_pct(row.get('win_rate'))} | "
                f"{row.get('persistence_count', 0)} | {_fmt_dt(row.get('last_confirmed'))} |"
            )
    else:
        lines.append("| - | - | - | - | - | - | - | - | - | - | - | - | - |")
    lines.extend(
        [
            "",
            "## No-Trade / Retired Edges",
            "",
            "| Symbol | Setup | Dir | TF | Role | Confidence | Trades | Exp R | Reason |",
            "|---|---|---|---|---|---:|---:|---:|---|",
        ]
    )
    retired = [row for row in rows if row.get("status") == "retired"]
    if retired:
        for row in retired:
            reason = "historical edge diluter" if row.get("edge_role") == "edge_diluter" else "low/failed confidence"
            lines.append(
                f"| {row.get('symbol')} | {row.get('setup')} | {row.get('direction')} | {row.get('timeframe')} | "
                f"{row.get('edge_role')} | {_fmt_num(row.get('confidence'), 4)} | {row.get('trades_n', 0)} | "
                f"{_fmt_num(row.get('expectancy_r'), 4)} | {reason} |"
            )
    else:
        lines.append("| - | - | - | - | - | - | - | - | - |")
    lines.extend(
        [
            "",
            "## Operating Rule",
            "",
            "Use active/candidate edges only when live intraday conditions match the stored setup, direction, timeframe, and regime. Retired edges are explicit no-trade memory until a later refresh earns them back.",
            "",
            "Research only. Not investment advice.",
        ]
    )
    return "\n".join(lines)


def render_edge_memory_html(
    rows: list[dict[str, Any]],
    *,
    summary: dict[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> str:
    generated_at = generated_at or datetime.now(timezone.utc)
    summary = summary or summarize_edge_memory(rows)
    status_counts = summary.get("status_counts") or {}

    def esc(value: Any) -> str:
        return html_lib.escape(str(value if value is not None else "-"))

    def badge(text: Any) -> str:
        raw = str(text or "unknown")
        key = raw.replace("_", "-")
        return f"<span class='badge {esc(key)}'>{esc(raw)}</span>"

    def table_body(items: list[dict[str, Any]], retired: bool = False) -> str:
        if not items:
            return "<tr><td colspan='13' class='empty'>No rows</td></tr>"
        cells = []
        for row in items:
            reason = "historical edge diluter" if row.get("edge_role") == "edge_diluter" else "low/failed confidence"
            if retired:
                cells.append(
                    "<tr>"
                    f"<td class='symbol'>{esc(row.get('symbol'))}</td><td>{esc(row.get('setup'))}</td>"
                    f"<td>{esc(row.get('direction'))}</td><td>{esc(row.get('timeframe'))}</td>"
                    f"<td>{badge(row.get('edge_role'))}</td><td class='num'>{_fmt_num(row.get('confidence'), 4)}</td>"
                    f"<td class='num'>{esc(row.get('trades_n', 0))}</td><td class='num'>{_fmt_num(row.get('expectancy_r'), 4)}</td>"
                    f"<td>{esc(reason)}</td></tr>"
                )
            else:
                cells.append(
                    "<tr>"
                    f"<td class='symbol'>{esc(row.get('symbol'))}</td><td>{esc(row.get('setup'))}</td>"
                    f"<td>{esc(row.get('direction'))}</td><td>{esc(row.get('timeframe'))}</td>"
                    f"<td>{badge(row.get('status'))}</td><td>{badge(row.get('edge_role'))}</td>"
                    f"<td class='num'>{_fmt_num(row.get('confidence'), 4)}</td><td class='num'>{esc(row.get('trades_n', 0))}</td>"
                    f"<td class='num'>{_fmt_num(row.get('expectancy_r'), 4)}</td><td class='num'>{_fmt_num(row.get('profit_factor'), 2)}</td>"
                    f"<td class='num'>{_fmt_pct(row.get('win_rate'))}</td><td class='num'>{esc(row.get('persistence_count', 0))}</td>"
                    f"<td>{esc(_fmt_dt(row.get('last_confirmed')))}</td></tr>"
                )
        return "".join(cells)

    active = [row for row in rows if row.get("status") in {"promoted", "candidate", "monitoring"}]
    retired_rows = [row for row in rows if row.get("status") == "retired"]
    status_text = ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items())) or "none"
    css = """
    :root { color-scheme: light; --ink:#172033; --muted:#647083; --line:#d8dee8; --panel:#f7f9fc; --good:#0f766e; --warn:#9a5b00; --bad:#b42318; --blue:#1d4ed8; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:#ffffff; }
    .wrap { max-width:1220px; margin:0 auto; padding:28px 24px 44px; }
    header { border-bottom:1px solid var(--line); padding-bottom:18px; margin-bottom:20px; }
    h1 { margin:0 0 8px; font-size:30px; letter-spacing:0; }
    h2 { margin:26px 0 12px; font-size:18px; letter-spacing:0; }
    .sub { color:var(--muted); margin:0; }
    .kpis { display:grid; grid-template-columns:repeat(5,minmax(140px,1fr)); gap:10px; margin:18px 0 8px; }
    .kpi { border:1px solid var(--line); background:var(--panel); border-radius:8px; padding:12px; }
    .kpi .label { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
    .kpi .value { font-size:22px; font-weight:700; margin-top:4px; }
    .note { border-left:4px solid var(--blue); background:#f3f7ff; padding:12px 14px; color:#263653; margin-top:18px; }
    table { width:100%; border-collapse:collapse; border:1px solid var(--line); font-size:13px; }
    th, td { border-bottom:1px solid var(--line); padding:9px 10px; text-align:left; vertical-align:middle; }
    th { background:#eef2f7; color:#334155; font-weight:700; }
    tr:nth-child(even) td { background:#fbfcfe; }
    .num { text-align:right; font-variant-numeric:tabular-nums; }
    .symbol { font-weight:700; }
    .badge { display:inline-block; border-radius:999px; padding:3px 8px; font-size:12px; border:1px solid var(--line); background:#fff; white-space:nowrap; }
    .promoted, .candidate, .monitoring, .core-carrier { color:var(--good); border-color:#99d5cd; background:#eefbf8; }
    .decaying { color:var(--warn); border-color:#f2c979; background:#fff7e6; }
    .retired, .edge-diluter { color:var(--bad); border-color:#f2aaa5; background:#fff1f0; }
    .empty { color:var(--muted); text-align:center; }
    @media (max-width:900px) { .kpis { grid-template-columns:repeat(2,minmax(140px,1fr)); } .table-scroll { overflow-x:auto; } h1 { font-size:24px; } }
    """
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Adda Edge Memory Dashboard</title>
  <style>{css}</style>
</head>
<body>
  <main class="wrap">
    <header>
      <h1>Agent Adda Edge Memory Dashboard</h1>
      <p class="sub">Generated {_fmt_dt(generated_at)} · Status mix: {esc(status_text)}</p>
      <section class="kpis">
        <div class="kpi"><div class="label">Total Edges</div><div class="value">{esc(summary.get('total_edges', 0))}</div></div>
        <div class="kpi"><div class="label">Active</div><div class="value">{esc(summary.get('active_edges', 0))}</div></div>
        <div class="kpi"><div class="label">Retired</div><div class="value">{esc(summary.get('retired_edges', 0))}</div></div>
        <div class="kpi"><div class="label">Avg Confidence</div><div class="value">{_fmt_num(summary.get('avg_confidence'), 4)}</div></div>
        <div class="kpi"><div class="label">Latest Update</div><div class="value">{esc(_fmt_dt(summary.get('latest_update')))}</div></div>
      </section>
    </header>
    <section>
      <h2>Active Edge Memory</h2>
      <div class="table-scroll"><table>
        <thead><tr><th>Symbol</th><th>Setup</th><th>Dir</th><th>TF</th><th>Status</th><th>Role</th><th>Confidence</th><th>Trades</th><th>Exp R</th><th>PF</th><th>Win</th><th>Persist</th><th>Last Confirmed</th></tr></thead>
        <tbody>{table_body(active)}</tbody>
      </table></div>
    </section>
    <section>
      <h2>No-Trade / Retired Edges</h2>
      <div class="table-scroll"><table>
        <thead><tr><th>Symbol</th><th>Setup</th><th>Dir</th><th>TF</th><th>Role</th><th>Confidence</th><th>Trades</th><th>Exp R</th><th>Reason</th></tr></thead>
        <tbody>{table_body(retired_rows, retired=True)}</tbody>
      </table></div>
    </section>
    <p class="note">Use active/candidate edges only when live intraday conditions match the stored setup, direction, timeframe, and regime. Retired edges are explicit no-trade memory until a later refresh earns them back. Research only. Not investment advice.</p>
  </main>
</body>
</html>"""


def write_edge_memory_report(
    rows: list[dict[str, Any]],
    *,
    output_dir: str | Path = "reports/latest",
    generated_at: datetime | None = None,
) -> dict[str, str]:
    generated_at = generated_at or datetime.now(timezone.utc)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize_edge_memory(rows)
    markdown = render_edge_memory_markdown(rows, summary=summary, generated_at=generated_at)
    html = render_edge_memory_html(rows, summary=summary, generated_at=generated_at)
    payload = {"generated_at": generated_at.isoformat(), "summary": summary, "edges": rows}

    md_path = out_dir / "edge_knowledge_report.md"
    html_path = out_dir / "edge_knowledge_report.html"
    json_path = out_dir / "edge_knowledge_report.json"
    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")

    if out_dir.name == "latest":
        research_dir = out_dir.parent / "research"
        try:
            research_dir.mkdir(parents=True, exist_ok=True)
            stamp = generated_at.strftime("%Y%m%d_%H%M%S")
            shutil.copyfile(html_path, research_dir / f"edge_knowledge_report_{stamp}.html")
            shutil.copyfile(md_path, research_dir / f"edge_knowledge_report_{stamp}.md")
            shutil.copyfile(json_path, research_dir / f"edge_knowledge_report_{stamp}.json")
        except Exception:
            pass
    return {"markdown": str(md_path), "html": str(html_path), "json": str(json_path)}


def generate_edge_memory_report(
    *,
    dsn: str | None = None,
    output_dir: str | Path = "reports/latest",
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    from terminal.intraday_indicator_study import _connect_pg

    generated_at = generated_at or datetime.now(timezone.utc)
    with _connect_pg(dsn) as conn:
        rows = fetch_edge_memory_rows(conn)
    summary = summarize_edge_memory(rows)
    paths = write_edge_memory_report(rows, output_dir=output_dir, generated_at=generated_at)
    return {"summary": summary, "paths": paths, "edges": rows}


def _create_schema(conn: Any) -> None:
    statements = [
        "CREATE SCHEMA IF NOT EXISTS research",
        """
        CREATE TABLE IF NOT EXISTS research.edge_refresh_runs (
            refresh_id TEXT PRIMARY KEY,
            evidence_set_id TEXT NOT NULL,
            generated_at TIMESTAMPTZ NOT NULL,
            source_report TEXT,
            bar_count INTEGER NOT NULL DEFAULT 0,
            symbol_count INTEGER NOT NULL DEFAULT 0,
            trade_count INTEGER NOT NULL DEFAULT 0,
            code_version TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS research.edge_knowledge_nodes (
            claim_id TEXT PRIMARY KEY,
            setup TEXT NOT NULL,
            direction TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            symbol TEXT NOT NULL,
            session_bucket TEXT NOT NULL,
            vol_regime TEXT NOT NULL,
            pcr_regime TEXT NOT NULL,
            expectancy_r DOUBLE PRECISION,
            profit_factor DOUBLE PRECISION,
            win_rate DOUBLE PRECISION,
            trades_n INTEGER NOT NULL DEFAULT 0,
            wf_status TEXT NOT NULL,
            wf_folds INTEGER NOT NULL DEFAULT 0,
            wf_positive_rate DOUBLE PRECISION,
            wf_worst_r DOUBLE PRECISION,
            edge_role TEXT NOT NULL,
            confidence DOUBLE PRECISION NOT NULL,
            lineage JSONB NOT NULL,
            first_seen TIMESTAMPTZ NOT NULL,
            last_confirmed TIMESTAMPTZ,
            persistence_count INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS research.edge_refresh_history (
            refresh_id TEXT NOT NULL REFERENCES research.edge_refresh_runs(refresh_id) ON DELETE CASCADE,
            claim_id TEXT NOT NULL,
            snapshot JSONB NOT NULL,
            confidence DOUBLE PRECISION NOT NULL,
            status TEXT NOT NULL,
            edge_role TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (refresh_id, claim_id)
        )
        """,
    ]
    with conn.cursor() as cur:
        for sql in statements:
            cur.execute(sql)


def persist_edge_nodes(conn: Any, refresh: EdgeRefreshRun, nodes: list[EdgeKnowledgeNode]) -> dict[str, Any]:
    _create_schema(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO research.edge_refresh_runs (
                refresh_id, evidence_set_id, generated_at, source_report, bar_count, symbol_count, trade_count, code_version
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (refresh_id) DO UPDATE SET
                evidence_set_id = EXCLUDED.evidence_set_id,
                generated_at = EXCLUDED.generated_at,
                source_report = EXCLUDED.source_report,
                bar_count = EXCLUDED.bar_count,
                symbol_count = EXCLUDED.symbol_count,
                trade_count = EXCLUDED.trade_count,
                code_version = EXCLUDED.code_version
            """,
            (
                refresh.refresh_id,
                refresh.evidence_set_id,
                refresh.generated_at,
                refresh.source_report,
                refresh.bar_count,
                refresh.symbol_count,
                refresh.trade_count,
                refresh.code_version,
            ),
        )
        for node in nodes:
            record = node.to_record()
            cur.execute(
                """
                INSERT INTO research.edge_knowledge_nodes (
                    claim_id, setup, direction, timeframe, symbol, session_bucket, vol_regime, pcr_regime,
                    expectancy_r, profit_factor, win_rate, trades_n, wf_status, wf_folds, wf_positive_rate,
                    wf_worst_r, edge_role, confidence, lineage, first_seen, last_confirmed, persistence_count, status
                ) VALUES (
                    %(claim_id)s, %(setup)s, %(direction)s, %(timeframe)s, %(symbol)s, %(session_bucket)s,
                    %(vol_regime)s, %(pcr_regime)s, %(expectancy_r)s, %(profit_factor)s, %(win_rate)s,
                    %(trades_n)s, %(wf_status)s, %(wf_folds)s, %(wf_positive_rate)s, %(wf_worst_r)s,
                    %(edge_role)s, %(confidence)s, %(lineage)s::jsonb, %(first_seen)s, %(last_confirmed)s,
                    %(persistence_count)s, %(status)s
                )
                ON CONFLICT (claim_id) DO UPDATE SET
                    expectancy_r = EXCLUDED.expectancy_r,
                    profit_factor = EXCLUDED.profit_factor,
                    win_rate = EXCLUDED.win_rate,
                    trades_n = EXCLUDED.trades_n,
                    wf_status = EXCLUDED.wf_status,
                    wf_folds = EXCLUDED.wf_folds,
                    wf_positive_rate = EXCLUDED.wf_positive_rate,
                    wf_worst_r = EXCLUDED.wf_worst_r,
                    edge_role = EXCLUDED.edge_role,
                    confidence = EXCLUDED.confidence,
                    lineage = EXCLUDED.lineage,
                    last_confirmed = COALESCE(EXCLUDED.last_confirmed, research.edge_knowledge_nodes.last_confirmed),
                    persistence_count = EXCLUDED.persistence_count,
                    status = EXCLUDED.status,
                    updated_at = now()
                """,
                record,
            )
            cur.execute(
                """
                INSERT INTO research.edge_refresh_history (
                    refresh_id, claim_id, snapshot, confidence, status, edge_role
                ) VALUES (%s,%s,%s::jsonb,%s,%s,%s)
                ON CONFLICT (refresh_id, claim_id) DO UPDATE SET
                    snapshot = EXCLUDED.snapshot,
                    confidence = EXCLUDED.confidence,
                    status = EXCLUDED.status,
                    edge_role = EXCLUDED.edge_role
                """,
                (
                    refresh.refresh_id,
                    node.claim_id,
                    json.dumps(record, sort_keys=True, default=str),
                    node.confidence,
                    node.status,
                    node.edge_role,
                ),
            )
    conn.commit()
    return {"refresh_id": refresh.refresh_id, "nodes": len(nodes)}
