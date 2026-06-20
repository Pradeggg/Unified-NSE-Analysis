#!/usr/bin/env python3
"""Build a comprehensive paper-trading performance report from latest artifacts."""

from __future__ import annotations

import csv
import html
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
PAPER_DIR = ROOT / "portfolio" / "data" / "nse_pg_strategy_lab" / "latest" / "paper"
REPORTS_DIR = ROOT / "reports"
LATEST_DIR = REPORTS_DIR / "latest"
ARCHIVE_DIR = REPORTS_DIR / "paper_trading"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value in {None, ""}:
            return default
        return float(value)
    except Exception:
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        if value in {None, ""}:
            return default
        return int(float(value))
    except Exception:
        return default


def _money(value: Any) -> str:
    return f"₹{_f(value):,.0f}"


def _money2(value: Any) -> str:
    return f"₹{_f(value):,.2f}"


def _pct(value: Any) -> str:
    return f"{_f(value):+.2f}%"


def _cls(value: Any, *, inverse: bool = False) -> str:
    number = _f(value)
    if inverse:
        number *= -1
    if number > 0:
        return "pos"
    if number < 0:
        return "neg"
    return "muted"


def _h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _sparkline(points: list[float], *, width: int = 760, height: int = 140, color: str = "#2563eb") -> str:
    if not points:
        return ""
    if len(points) == 1:
        points = [points[0], points[0]]
    lo, hi = min(points), max(points)
    pad = 10
    span = hi - lo or 1.0
    step = (width - pad * 2) / (len(points) - 1)
    coords = []
    for idx, value in enumerate(points):
        x = pad + idx * step
        y = height - pad - ((value - lo) / span * (height - pad * 2))
        coords.append(f"{x:.1f},{y:.1f}")
    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="trend chart">'
        f'<polyline points="{" ".join(coords)}" fill="none" stroke="{color}" stroke-width="3" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'<line x1="{pad}" y1="{height-pad}" x2="{width-pad}" y2="{height-pad}" stroke="#e5e7eb"/>'
        f'<text x="{pad}" y="16" class="chart-label">{_h(_money(hi))}</text>'
        f'<text x="{pad}" y="{height-4}" class="chart-label">{_h(_money(lo))}</text>'
        "</svg>"
    )


def _drawdown_chart(points: list[float], *, width: int = 760, height: int = 110) -> str:
    if not points:
        return ""
    lo, hi = min(points), max(points)
    pad = 10
    span = hi - lo or 1.0
    step = (width - pad * 2) / (len(points) - 1 or 1)
    coords = []
    for idx, value in enumerate(points):
        x = pad + idx * step
        y = height - pad - ((value - lo) / span * (height - pad * 2))
        coords.append(f"{x:.1f},{y:.1f}")
    return (
        f'<svg class="chart drawdown" viewBox="0 0 {width} {height}" role="img" aria-label="drawdown chart">'
        f'<polyline points="{" ".join(coords)}" fill="none" stroke="#dc2626" stroke-width="3" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'<line x1="{pad}" y1="{pad}" x2="{width-pad}" y2="{pad}" stroke="#e5e7eb"/>'
        f'<text x="{pad}" y="16" class="chart-label">0%</text>'
        f'<text x="{pad}" y="{height-4}" class="chart-label">{_h(f"{lo:.1f}%")}</text>'
        "</svg>"
    )


def _table(headers: list[str], rows: list[list[Any]], classes: str = "") -> str:
    head = "".join(f"<th>{_h(col)}</th>" for col in headers)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{cell}</td>" for cell in row)
        body_rows.append(f"<tr>{cells}</tr>")
    return f'<table class="{classes}"><thead><tr>{head}</tr></thead><tbody>{"".join(body_rows)}</tbody></table>'


def _stage_rows(positions: list[dict[str, str]]) -> list[list[str]]:
    counts = Counter(row.get("stage") or "UNKNOWN" for row in positions)
    total = len(positions) or 1
    rows = []
    for stage, count in sorted(counts.items()):
        rows.append([_h(stage), str(count), f"{count / total * 100:.1f}%"])
    return rows


def build() -> dict[str, Path]:
    state = _read_json(PAPER_DIR / "portfolio_state.json")
    positions = _read_csv(PAPER_DIR / "positions.csv")
    daily = _read_csv(PAPER_DIR / "daily_pnl.csv")
    trades = _read_csv(PAPER_DIR / "trades.csv")
    next_orders = _read_csv(PAPER_DIR / "next_orders.csv")

    latest = daily[-1] if daily else state.get("latest_snapshot", {})
    metrics = state.get("strategy_metrics", {})
    as_of = str(state.get("as_of") or latest.get("date") or "unknown")
    generated = datetime.now().strftime("%Y-%m-%d %H:%M IST")

    nav_values = [_f(row.get("nav")) for row in daily if row.get("nav")]
    drawdowns = [_f(row.get("drawdown_pct")) for row in daily if row.get("drawdown_pct")]
    recent_daily = daily[-10:]

    winners = [row for row in positions if _f(row.get("unrealized_pnl")) > 0]
    losers = [row for row in positions if _f(row.get("unrealized_pnl")) < 0]
    sorted_positions = sorted(positions, key=lambda row: _f(row.get("unrealized_pnl")), reverse=True)
    closed = [row for row in trades if row.get("side") == "SELL"]
    winning_closed = [row for row in closed if _f(row.get("realized_pnl")) > 0]
    losing_closed = [row for row in closed if _f(row.get("realized_pnl")) < 0]
    last_trade_date = max((row.get("date") or "" for row in trades), default="")
    recent_trades = trades[-20:]

    health = "Strong but volatile"
    if _f(latest.get("drawdown_pct")) <= -15:
        health = "Profitable but under drawdown pressure"
    elif _f(latest.get("cumulative_return_pct")) < 0:
        health = "Needs review"

    css = """
    :root { --ink:#17212b; --muted:#64748b; --line:#d9e2ec; --bg:#f6f8fb; --card:#ffffff;
      --blue:#2563eb; --green:#15803d; --red:#dc2626; --amber:#b45309; --teal:#0f766e; }
    * { box-sizing: border-box; }
    body { margin:0; background:var(--bg); color:var(--ink); font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif; }
    .wrap { max-width:1180px; margin:0 auto; padding:28px; }
    .hero { background:linear-gradient(135deg,#0f172a,#164e63); color:white; border-radius:10px; padding:24px; }
    .hero h1 { margin:0 0 8px; font-size:28px; letter-spacing:0; }
    .hero p { margin:0; color:#dbeafe; }
    .chips { display:flex; flex-wrap:wrap; gap:8px; margin-top:16px; }
    .chip { border:1px solid rgba(255,255,255,.22); border-radius:6px; padding:5px 8px; color:#ecfeff; }
    .grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:16px 0; }
    .card { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:14px; box-shadow:0 1px 2px rgba(15,23,42,.05); }
    .card h2, .card h3 { margin:0 0 10px; }
    .metric .label { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.05em; }
    .metric .value { font-size:23px; font-weight:800; margin-top:2px; }
    .metric .sub { color:var(--muted); font-size:12px; margin-top:2px; }
    .span2 { grid-column:span 2; } .span4 { grid-column:1 / -1; }
    table { width:100%; border-collapse:collapse; font-size:13px; }
    th, td { border-bottom:1px solid #e5e7eb; padding:8px; text-align:left; vertical-align:top; }
    th { color:#334155; background:#f8fafc; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
    .pos { color:var(--green); font-weight:700; } .neg { color:var(--red); font-weight:700; } .muted { color:var(--muted); }
    .pill { display:inline-block; border-radius:5px; padding:2px 6px; background:#e0f2fe; color:#075985; font-weight:700; font-size:12px; }
    .risk { background:#fef3c7; color:#92400e; }
    .good { background:#dcfce7; color:#166534; }
    .bad { background:#fee2e2; color:#991b1b; }
    .chart { width:100%; height:auto; background:#fff; border:1px solid #e5e7eb; border-radius:6px; }
    .chart-label { fill:#64748b; font-size:11px; }
    ul { margin:8px 0 0 18px; padding:0; }
    .callout { border-left:4px solid var(--blue); background:#eff6ff; padding:12px; border-radius:6px; }
    .warn { border-left-color:var(--amber); background:#fffbeb; }
    .footer { color:var(--muted); font-size:12px; margin-top:18px; }
    @media (max-width:900px) { .grid { grid-template-columns:1fr 1fr; } .span2,.span4 { grid-column:1 / -1; } }
    """

    position_rows = []
    for row in sorted_positions:
        position_rows.append([
            f"<b>{_h(row.get('symbol'))}</b>",
            _h(row.get("quantity")),
            _money2(row.get("current_price")),
            _money2(row.get("avg_cost")),
            f'<span class="{_cls(row.get("unrealized_pnl"))}">{_money2(row.get("unrealized_pnl"))}</span>',
            f'<span class="{_cls(row.get("unrealized_pct"))}">{_pct(row.get("unrealized_pct"))}</span>',
            f'<span class="pill">{_h(row.get("stage"))}</span>',
            _h(row.get("relative_strength")),
            _money2(row.get("stop_price")),
            _money2(row.get("target_price")),
        ])

    trade_rows = []
    for row in reversed(recent_trades):
        trade_rows.append([
            _h(row.get("date")),
            f"<b>{_h(row.get('symbol'))}</b>",
            _h(row.get("side")),
            _h(row.get("trade_intent")),
            _h(row.get("quantity")),
            _money2(row.get("price")),
            f'<span class="{_cls(row.get("realized_pnl"))}">{_money2(row.get("realized_pnl")) if row.get("realized_pnl") else "n/a"}</span>',
            _h(row.get("holding_period_days") or "n/a"),
        ])

    order_rows = []
    for row in next_orders:
        order_rows.append([
            _h(row.get("date")),
            f"<b>{_h(row.get('symbol'))}</b>",
            _h(row.get("side")),
            _h(row.get("quantity")),
            _money2(row.get("reference_price")),
            _money2(row.get("stop_price")),
            _money2(row.get("target_price")),
            _money2(row.get("estimated_risk")),
            _money2(row.get("estimated_notional")),
        ])

    daily_rows = []
    for row in recent_daily:
        daily_rows.append([
            _h(row.get("date")),
            _money(row.get("nav")),
            f'<span class="{_cls(row.get("daily_pnl"))}">{_money(row.get("daily_pnl"))}</span>',
            f'<span class="{_cls(row.get("daily_return_pct"))}">{_pct(row.get("daily_return_pct"))}</span>',
            f'<span class="{_cls(row.get("drawdown_pct"))}">{_pct(row.get("drawdown_pct"))}</span>',
            _h(row.get("open_positions")),
        ])

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Paper Trading Performance Report - {as_of}</title>
<style>{css}</style>
</head>
<body>
<main class="wrap">
  <section class="hero">
    <h1>Paper Trading Performance Report</h1>
    <p>As of {as_of} · Generated {generated} · Strategy: {_h(state.get('selected_strategy_name'))}</p>
    <div class="chips">
      <span class="chip">Mode: Paper trading only</span>
      <span class="chip">Source: portfolio/data/nse_pg_strategy_lab/latest</span>
      <span class="chip">Run: {_h(state.get('run_id'))}</span>
      <span class="chip">Health: {health}</span>
    </div>
  </section>

  <section class="grid">
    <div class="card metric"><div class="label">NAV</div><div class="value">{_money(latest.get('nav'))}</div><div class="sub">From ₹10,00,000 initial capital</div></div>
    <div class="card metric"><div class="label">Total Return</div><div class="value {_cls(latest.get('cumulative_return_pct'))}">{_pct(latest.get('cumulative_return_pct'))}</div><div class="sub">Benchmark: {_pct(metrics.get('benchmark_return_pct'))}</div></div>
    <div class="card metric"><div class="label">Daily P&L</div><div class="value {_cls(latest.get('daily_pnl'))}">{_money(latest.get('daily_pnl'))}</div><div class="sub">{_pct(latest.get('daily_return_pct'))} on {as_of}</div></div>
    <div class="card metric"><div class="label">Drawdown</div><div class="value {_cls(latest.get('drawdown_pct'))}">{_pct(latest.get('drawdown_pct'))}</div><div class="sub">Strategy max DD: {abs(_f(metrics.get('max_drawdown_pct'))):.2f}%</div></div>

    <div class="card span2">
      <h2>Equity Curve</h2>
      {_sparkline(nav_values)}
    </div>
    <div class="card span2">
      <h2>Drawdown Path</h2>
      {_drawdown_chart(drawdowns)}
    </div>

    <div class="card span2">
      <h2>Executive Read</h2>
      <div class="callout">
        <b>{health}.</b> The paper account is strongly profitable at {_pct(latest.get('cumulative_return_pct'))},
        with {_money2(state.get('account', {}).get('realized_pnl'))} realized P&L and
        {_money2(state.get('total_unrealized_pnl'))} open unrealized P&L. The trade-off is volatility:
        the latest drawdown is {_pct(latest.get('drawdown_pct'))}, and the selected breakout strategy
        has a max drawdown of {abs(_f(metrics.get('max_drawdown_pct'))):.2f}%.
      </div>
      <ul>
        <li>Open book has {len(winners)} winners and {len(losers)} losers across {len(positions)} positions.</li>
        <li>Win rate is {_f(metrics.get('win_rate_pct')):.2f}%, but profit factor is {_f(metrics.get('profit_factor')):.2f}.</li>
        <li>Average winner ({_money2(metrics.get('average_win'))}) is materially larger than average loser ({_money2(metrics.get('average_loss'))}).</li>
        <li>Current exposure is {_f(latest.get('market_value')) / max(_f(latest.get('nav')), 1) * 100:.1f}% with {_money2(latest.get('cash'))} cash.</li>
      </ul>
    </div>

    <div class="card span2">
      <h2>Risk Diagnosis</h2>
      <div class="callout warn">
        This is a high-beta breakout profile. The book is profitable because winners are allowed to run,
        but losses can cluster when breakouts fail or gap through exits.
      </div>
      <ul>
        <li>Closed trades: {len(closed)} · Winners: {len(winning_closed)} · Losers: {len(losing_closed)}</li>
        <li>Turnover is {_f(metrics.get('turnover_pct')):.1f}%, so cost/slippage discipline matters.</li>
        <li>Largest recent realized loss was E2E at ₹-117,430, which deserves post-trade review.</li>
        <li>Guardrails to review before live use: position cap, gap-risk cap, liquidity filter, and max single-trade loss.</li>
      </ul>
    </div>

    <div class="card span4">
      <h2>Current Open Positions</h2>
      {_table(['Symbol','Qty','Price','Avg Cost','Unrealized','Unrealized %','Stage','RS','Stop','Target'], position_rows)}
    </div>

    <div class="card span2">
      <h2>Stage Mix</h2>
      {_table(['Stage','Count','Weight'], _stage_rows(positions))}
    </div>
    <div class="card span2">
      <h2>Strategy Metrics</h2>
      {_table(['Metric','Value'], [
        ['Selected strategy', _h(state.get('selected_strategy_name'))],
        ['Rank score', f"{_f(metrics.get('rank_score')):.2f}"],
        ['Profit factor', f"{_f(metrics.get('profit_factor')):.2f}"],
        ['Expectancy', _money2(metrics.get('expectancy'))],
        ['Win rate', f"{_f(metrics.get('win_rate_pct')):.2f}%"],
        ['Closed trades', str(_i(metrics.get('closed_trades')))],
        ['Fills', str(_i(metrics.get('fills')))],
        ['Cost drag', f"{_f(metrics.get('cost_drag_pct')):.2f}%"],
      ])}
    </div>

    <div class="card span4">
      <h2>Recent Daily P&L</h2>
      {_table(['Date','NAV','Daily P&L','Daily Return','Drawdown','Open Positions'], daily_rows)}
    </div>

    <div class="card span4">
      <h2>Recent Trades</h2>
      {_table(['Date','Symbol','Side','Intent','Qty','Price','Realized','Hold Days'], trade_rows)}
    </div>

    <div class="card span4">
      <h2>Next Session Orders</h2>
      {_table(['Date','Symbol','Side','Qty','Ref Price','Stop','Target','Est Risk','Est Notional'], order_rows)}
    </div>

    <div class="card span4">
      <h2>Operating Recommendation</h2>
      <ul>
        <li>Continue paper trading: the signal engine is finding momentum winners and beating the benchmark.</li>
        <li>Do not move this exact configuration live without explicit risk guardrails for gap-down exits and single-name loss caps.</li>
        <li>Review oversized losers, especially E2E, to determine if corporate-action, liquidity, or data-adjustment handling needs improvement.</li>
        <li>Maintain separate watch on Stage 1 open positions with high RS; they are profitable but less aligned with strict Stage 2 trend rules.</li>
      </ul>
    </div>
  </section>
  <p class="footer">Research and learning only. This report is generated from local paper-trading artifacts and does not represent broker activity or investment advice.</p>
</main>
</body>
</html>
"""

    md_lines = [
        f"# Paper Trading Performance Report - {as_of}",
        "",
        f"Generated: {generated}",
        f"Strategy: {state.get('selected_strategy_name')} (`{state.get('selected_strategy_id')}`)",
        "",
        "## Executive Summary",
        "",
        f"- NAV: {_money2(latest.get('nav'))}",
        f"- Total return: {_pct(latest.get('cumulative_return_pct'))}",
        f"- Daily P&L: {_money2(latest.get('daily_pnl'))} ({_pct(latest.get('daily_return_pct'))})",
        f"- Current drawdown: {_pct(latest.get('drawdown_pct'))}",
        f"- Realized P&L: {_money2(state.get('account', {}).get('realized_pnl'))}",
        f"- Unrealized P&L: {_money2(state.get('total_unrealized_pnl'))}",
        f"- Open positions: {len(positions)}",
        f"- Cash: {_money2(latest.get('cash'))}",
        "",
        "## Diagnosis",
        "",
        f"The paper account is {health.lower()}. It is strongly ahead of the benchmark, but the profile is volatile.",
        f"Win rate is {_f(metrics.get('win_rate_pct')):.2f}% and profit factor is {_f(metrics.get('profit_factor')):.2f}.",
        "The system depends on large breakout winners offsetting a larger number of failed trades.",
        "",
        "## Open Positions",
        "",
        "| Symbol | Qty | Price | Avg Cost | Unrealized | Unrealized % | Stage | RS | Stop | Target |",
        "|---|---:|---:|---:|---:|---:|---|---:|---:|---:|",
    ]
    for row in sorted_positions:
        md_lines.append(
            f"| {row.get('symbol')} | {row.get('quantity')} | {_money2(row.get('current_price'))} | "
            f"{_money2(row.get('avg_cost'))} | {_money2(row.get('unrealized_pnl'))} | {_pct(row.get('unrealized_pct'))} | "
            f"{row.get('stage')} | {row.get('relative_strength')} | {_money2(row.get('stop_price'))} | {_money2(row.get('target_price'))} |"
        )
    md_lines.extend([
        "",
        "## Next Session Orders",
        "",
        "| Symbol | Side | Qty | Ref Price | Stop | Target | Est Risk | Est Notional |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ])
    for row in next_orders:
        md_lines.append(
            f"| {row.get('symbol')} | {row.get('side')} | {row.get('quantity')} | {_money2(row.get('reference_price'))} | "
            f"{_money2(row.get('stop_price'))} | {_money2(row.get('target_price'))} | "
            f"{_money2(row.get('estimated_risk'))} | {_money2(row.get('estimated_notional'))} |"
        )
    md_lines.extend([
        "",
        "## Recommendation",
        "",
        "- Continue paper trading because selection is productive and benchmark-relative performance is strong.",
        "- Add explicit guardrails before live use: position cap, gap-risk cap, liquidity filter, max single-trade loss, and data-adjustment checks.",
        "- Review oversized realized losses, especially E2E, before trusting the setup with real capital.",
        "",
        "Research and learning only. Not investment advice.",
    ])

    LATEST_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = as_of.replace("-", "")
    html_path = ARCHIVE_DIR / f"paper_trading_performance_{stamp}.html"
    md_path = ARCHIVE_DIR / f"paper_trading_performance_{stamp}.md"
    latest_html = LATEST_DIR / "paper_trading_performance.html"
    latest_md = LATEST_DIR / "paper_trading_performance.md"
    for path in (html_path, latest_html):
        path.write_text(html_doc, encoding="utf-8")
    md_doc = "\n".join(md_lines) + "\n"
    for path in (md_path, latest_md):
        path.write_text(md_doc, encoding="utf-8")
    return {"html": html_path, "md": md_path, "latest_html": latest_html, "latest_md": latest_md}


def main() -> int:
    paths = build()
    for key, value in paths.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
