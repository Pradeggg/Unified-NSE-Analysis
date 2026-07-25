#!/usr/bin/env python3
"""Build the Agent Adda comprehensive intraday F&O strategy report.

The report is intentionally evidence-first. It reads the latest intraday F&O
research markdown, enriches the promoted/watch names with PostgreSQL F&O
analytics, and writes stable latest artifacts for email distribution.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal.tools import get_fno_analytics
from terminal.intraday_indicator_study import _connect_pg


LATEST_DIR = ROOT / "reports" / "latest"
RESEARCH_DIR = ROOT / "reports" / "research"
IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True)
class StrategyRow:
    symbol: str
    status: str
    setup: str
    timeframe: str
    direction: str
    trades: int
    win_rate: str
    expectancy_r: float
    profit_factor: str
    fno: dict[str, Any]
    fno_view: str


def _first_table(markdown: str, section: str) -> list[dict[str, str]]:
    marker = f"## {section}"
    start = markdown.find(marker)
    if start < 0:
        return []
    block = markdown[start + len(marker):]
    next_heading = block.find("\n## ")
    if next_heading >= 0:
        block = block[:next_heading]

    rows = [line.strip() for line in block.splitlines() if line.strip().startswith("|")]
    if len(rows) < 3:
        return []
    headers = [c.strip() for c in rows[0].strip("|").split("|")]
    out: list[dict[str, str]] = []
    for line in rows[2:]:
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(headers):
            continue
        out.append(dict(zip(headers, cells)))
    return out


def _bullet_value(markdown: str, label: str) -> str:
    pattern = rf"^- {re.escape(label)}:\s*(.+)$"
    for line in markdown.splitlines():
        match = re.match(pattern, line.strip())
        if match:
            return match.group(1).strip()
    return "-"


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, "-", ""):
            return default
        return float(str(value).replace("%", ""))
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return default


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None or value == "":
        return "-"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _money(value: Any) -> str:
    if value is None or value == "":
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number) >= 1000:
        return f"{number:,.0f}"
    if abs(number) >= 100:
        return f"{number:,.1f}"
    return f"{number:,.2f}"


def _fno_view(direction: str, analytics: dict[str, Any]) -> str:
    signal = str(analytics.get("fno_signal") or "")
    buildup = str(analytics.get("buildup") or "")
    pcr = analytics.get("pcr_oi")
    fut_chg = _float(analytics.get("futures_price_change_pct"))
    fut_oi = _float(analytics.get("futures_oi_change_pct"))
    direction = direction.upper()

    if direction == "LONG":
        if signal in {"BULL", "MILD_BULL"}:
            return "supports_long"
        if signal in {"BEAR", "MILD_BEAR"} or buildup == "SHORT_BUILDUP":
            return "against_long"
        if pcr is not None and _float(pcr) >= 1.0:
            return "mild_support"
        if pcr is not None and _float(pcr) < 0.70:
            return "call_heavy_caution"
        if fut_chg > 0 and fut_oi > 0:
            return "neutral_constructive"
        return "neutral"

    if direction == "SHORT":
        if signal in {"BEAR", "MILD_BEAR"}:
            return "supports_short"
        if pcr is not None and _float(pcr) < 0.80:
            return "mild_support"
        if signal in {"BULL", "MILD_BULL"}:
            return "against_short"
        return "neutral"
    return "neutral"


def _load_strategy_rows(markdown: str, limit: int = 44) -> list[StrategyRow]:
    table = _first_table(markdown, "Symbol Strategy Map")
    rows: list[StrategyRow] = []
    for item in table:
        status = item.get("status", "")
        if status not in {"promoted", "watch_candidate"}:
            continue
        symbol = item.get("symbol", "").upper()
        result = get_fno_analytics(symbol)
        analytics = {}
        if result.get("status") == "ok" and result.get("rows"):
            analytics = dict(result["rows"][0])
        rows.append(
            StrategyRow(
                symbol=symbol,
                status=status,
                setup=item.get("setup", ""),
                timeframe=item.get("timeframe", ""),
                direction=item.get("direction", ""),
                trades=_int(item.get("trades")),
                win_rate=item.get("win_rate", "-"),
                expectancy_r=_float(item.get("expectancy_r")),
                profit_factor=item.get("profit_factor", "-"),
                fno=analytics,
                fno_view=_fno_view(item.get("direction", ""), analytics) if analytics else "no_fno_data",
            )
        )
        if len(rows) >= limit:
            break
    return rows


def _latest_fno_date() -> str:
    try:
        with _connect_pg() as conn, conn.cursor() as cur:
            cur.execute("SELECT max(trade_date) FROM derivatives.fno_eod")
            row = cur.fetchone()
            return str(row[0]) if row and row[0] else "-"
    except Exception:
        return "-"


def _last_week_history(symbols: list[str]) -> dict[str, dict[str, Any]]:
    if not symbols:
        return {}
    sql = """
        WITH latest AS (
            SELECT max(timestamp)::date AS max_date
            FROM intraday.ohlcv_bars
            WHERE timeframe = '15m'
        ),
        bars AS (
            SELECT symbol, timestamp, open, high, low, close, volume
            FROM intraday.ohlcv_bars, latest
            WHERE timeframe = '15m'
              AND symbol = ANY(%s)
              AND timestamp::date BETWEEN latest.max_date - interval '6 days' AND latest.max_date
        )
        SELECT symbol,
               min(timestamp)::text AS first_ts,
               max(timestamp)::text AS last_ts,
               (array_agg(open ORDER BY timestamp))[1] AS first_open,
               (array_agg(close ORDER BY timestamp DESC))[1] AS last_close,
               max(high) AS week_high,
               min(low) AS week_low,
               sum(volume) AS week_volume,
               count(*) AS bars
        FROM bars
        GROUP BY symbol
    """
    out: dict[str, dict[str, Any]] = {}
    try:
        with _connect_pg() as conn, conn.cursor() as cur:
            cur.execute(sql, (symbols,))
            for row in cur.fetchall():
                first_open = _float(row[3])
                last_close = _float(row[4])
                change = ((last_close / first_open) - 1) * 100 if first_open else None
                out[str(row[0]).upper()] = {
                    "first_ts": row[1],
                    "last_ts": row[2],
                    "first_open": row[3],
                    "last_close": row[4],
                    "week_high": row[5],
                    "week_low": row[6],
                    "week_volume": row[7],
                    "bars": row[8],
                    "week_change_pct": change,
                }
    except Exception:
        return {}
    return out


def _tier_rows(rows: list[StrategyRow]) -> dict[str, list[StrategyRow]]:
    confirmed: list[StrategyRow] = []
    tactical: list[StrategyRow] = []
    cautious: list[StrategyRow] = []
    avoid: list[StrategyRow] = []
    for row in rows:
        if row.fno_view in {"against_long", "against_short"}:
            avoid.append(row)
        elif row.status == "promoted" and row.fno_view in {"supports_long", "supports_short", "mild_support", "neutral_constructive", "neutral"}:
            confirmed.append(row)
        elif row.fno_view in {"call_heavy_caution"}:
            cautious.append(row)
        else:
            tactical.append(row)
    return {"confirmed": confirmed, "tactical": tactical, "cautious": cautious, "avoid": avoid}


def _md_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(lines)


def build_markdown(source: Path, output_date: datetime | None = None) -> str:
    generated_at = output_date or datetime.now(IST)
    markdown = source.read_text(encoding="utf-8")
    rows = _load_strategy_rows(markdown)
    tiers = _tier_rows(rows)
    history = _last_week_history([r.symbol for r in rows])

    leaderboard = _first_table(markdown, "Indicator Leaderboard")[:5]
    walk_forward = _first_table(markdown, "Walk-Forward Validation")[:4]
    core_carriers = _first_table(markdown, "Confirmed Setup Symbol Drilldown")
    fno_date = _latest_fno_date()

    best_setup = leaderboard[0] if leaderboard else {}
    confirmed = tiers["confirmed"]
    primary_symbols = {"MIDCPNIFTY", "360ONE", "HAL", "POLYCAB", "BAJFINANCE", "KEI"}
    primary = [
        r
        for r in rows
        if r.symbol in primary_symbols
        and r.direction.upper() == "LONG"
        and r.fno_view not in {"against_long", "call_heavy_caution"}
    ]
    if not primary:
        primary = confirmed[:5]

    lines: list[str] = [
        "# Agent Adda Intraday F&O Strategy Report",
        "",
        f"- Generated: {generated_at.strftime('%Y-%m-%d %H:%M:%S IST')}",
        f"- Research source: `{source.relative_to(ROOT)}`",
        f"- F&O snapshot: {fno_date}",
        f"- Data mode: historical intraday bars + EOD F&O analytics; not live quotes",
        "",
        "## Executive Read",
        "",
        "The current research favors a selective long-breakout playbook, not broad market chasing. "
        "The confirmed aggregate edge is the 15-minute ORB + VWAP long setup, but the F&O layer narrows the tradable list materially.",
        "",
        _md_table(
            ["Metric", "Value"],
            [
                ["Bars loaded", _bullet_value(markdown, "Bars loaded")],
                ["Symbols with bars", _bullet_value(markdown, "Symbols with bars")],
                ["Trade candidates tested", _bullet_value(markdown, "Trade candidates tested")],
                ["Daily F&O context rows", _bullet_value(markdown, "Daily F&O context rows")],
                [
                    "Best tested setup",
                    f"{best_setup.get('setup', '-')} {best_setup.get('direction', '-')} on {best_setup.get('timeframe', '-')}",
                ],
                ["Best setup expectancy", f"{best_setup.get('expectancy_r', '-')}R"],
                ["Best setup profit factor", best_setup.get("profit_factor", "-")],
            ],
        ),
        "",
        "## Monday Playbook",
        "",
        "- Do not enter at the open. Let the 15-minute opening range form.",
        "- Primary trigger: price clears opening-range high and holds above VWAP on a 15-minute close.",
        "- Preferred structure: defined-risk long call or futures/spot with a hard invalidation below VWAP/opening-range support.",
        "- Avoid gap-up chase. Prefer breakout-retest or continuation after VWAP reclaim.",
        "- Max 2-3 trades for the session; stop trading after two failed breakouts.",
        "- Same-day exit only unless a separate swing thesis is built from fresh EOD data.",
        "",
        "## Primary Candidates",
        "",
    ]

    primary_rows = []
    for row in primary[:6]:
        f = row.fno
        h = history.get(row.symbol, {})
        primary_rows.append(
            [
                row.symbol,
                row.setup,
                row.direction,
                row.trades,
                row.win_rate,
                f"{row.expectancy_r:.2f}",
                row.fno_view,
                _fmt(f.get("pcr_oi")),
                _money(f.get("max_call_oi_strike")),
                _money(f.get("max_put_oi_strike")),
                _fmt(h.get("week_change_pct")),
            ]
        )
    lines.append(
        _md_table(
            [
                "Symbol",
                "Setup",
                "Side",
                "Trades",
                "Win",
                "Exp R",
                "F&O view",
                "PCR",
                "CE wall",
                "PE floor",
                "Last-week %",
            ],
            primary_rows,
        )
    )

    lines += [
        "",
        "## F&O Confirmation Matrix",
        "",
        "This table includes the promoted and watch-candidate universe from the strategy map. "
        "`against_long` and `call_heavy_caution` are gates, not automatic shorts.",
        "",
    ]
    matrix_rows = []
    for row in rows:
        f = row.fno
        h = history.get(row.symbol, {})
        matrix_rows.append(
            [
                row.symbol,
                row.status,
                row.setup,
                row.direction,
                row.trades,
                row.win_rate,
                f"{row.expectancy_r:.2f}",
                f.get("fno_signal", "-"),
                f.get("buildup", "-"),
                _fmt(f.get("futures_price_change_pct")),
                _fmt(f.get("futures_oi_change_pct")),
                _fmt(f.get("pcr_oi")),
                _money(f.get("max_pain")),
                _money(f.get("max_call_oi_strike")),
                _money(f.get("max_put_oi_strike")),
                _fmt(h.get("week_change_pct")),
                row.fno_view,
            ]
        )
    lines.append(
        _md_table(
            [
                "Symbol",
                "Map",
                "Setup",
                "Side",
                "Trades",
                "Win",
                "Exp R",
                "F&O signal",
                "Buildup",
                "Fut %",
                "OI %",
                "PCR",
                "Max pain",
                "CE wall",
                "PE floor",
                "Week %",
                "Gate",
            ],
            matrix_rows,
        )
    )

    lines += [
        "",
        "## Confirmed Research Evidence",
        "",
        _md_table(
            list(leaderboard[0].keys()) if leaderboard else ["Evidence"],
            [list(r.values()) for r in leaderboard] if leaderboard else [["Missing indicator leaderboard"]],
        ),
        "",
        "## Walk-Forward Validation",
        "",
        _md_table(
            list(walk_forward[0].keys()) if walk_forward else ["Evidence"],
            [list(r.values()) for r in walk_forward] if walk_forward else [["Missing walk-forward validation"]],
        ),
        "",
        "## Core Carriers And Diluters",
        "",
        _md_table(
            list(core_carriers[0].keys()) if core_carriers else ["Evidence"],
            [list(r.values()) for r in core_carriers] if core_carriers else [["Missing symbol drilldown"]],
        ),
        "",
        "## Action List",
        "",
        "- Active watch: MIDCPNIFTY and 360ONE first; HAL only if it clears its pin zone with volume.",
        "- Secondary watch: POLYCAB, BAJFINANCE, KEI, FEDERALBNK, ABCAPITAL, TITAN, LT, ETERNAL, EICHERMOT, INDIGO.",
        "- Downgrade: DIXON long because F&O shows mild-bearish short buildup.",
        "- Avoid long: INFY while F&O remains BEAR/SHORT_BUILDUP.",
        "- Market filters: use NIFTY and BANKNIFTY for tape confirmation, not as first-choice ORB+VWAP longs.",
        "",
        "## Risk And No-Trade Conditions",
        "",
        "- No trade if opening range is too wide to define a practical stop.",
        "- No trade if VWAP is flat and price whipsaws across it repeatedly.",
        "- No option trade if bid-ask spread or volume is poor near the selected strike.",
        "- Reduce size near max-pain or heavy OI pin zones.",
        "- Treat OI walls as context, not guaranteed support or resistance.",
        "",
        "## Source Trail",
        "",
        "- `reports/latest/intraday_fno_indicator_study.md`",
        "- PostgreSQL `intraday.ohlcv_bars` 15-minute bars",
        "- PostgreSQL `derivatives.mv_fno_symbol_analytics`",
        "- PostgreSQL `derivatives.fno_eod` nearest-expiry option context",
        "",
        "## Disclaimer",
        "",
        "Research and learning only. This is not investment advice or a recommendation to buy or sell securities or derivatives. "
        "Validate live price, liquidity, spreads, and risk before any trade.",
    ]
    return "\n".join(lines)


def markdown_to_html(markdown: str) -> str:
    parts: list[str] = []
    in_table = False
    in_list = False
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("| ") and line.endswith(" |"):
            cells = [html.escape(c.strip()) for c in line.strip("|").split("|")]
            if all(c == "---" for c in cells):
                continue
            if in_list:
                parts.append("</ul>")
                in_list = False
            if not in_table:
                parts.append("<div class='table-wrap'><table class='data-table'>")
                in_table = True
                parts.append("<thead><tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr></thead><tbody>")
            else:
                parts.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            parts.append("</tbody></table></div>")
            in_table = False
        if line.startswith("- "):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{html.escape(line[2:])}</li>")
            continue
        if in_list:
            parts.append("</ul>")
            in_list = False
        if line.startswith("# "):
            parts.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            parts.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line:
            parts.append(f"<p>{html.escape(line)}</p>")
    if in_table:
        parts.append("</tbody></table></div>")
    if in_list:
        parts.append("</ul>")

    css = """
    :root{--ink:#102326;--muted:#5a6b72;--line:#d8e3e7;--brand:#0f5b55;--accent:#d97706;--ok:#0f766e;--warn:#b45309;--bad:#b91c1c;--bg:#f3f7f8}
    *{box-sizing:border-box}
    body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Arial,Helvetica,sans-serif;line-height:1.5}
    .shell{max-width:1320px;margin:0 auto;padding:28px}
    .hero{background:#0f2f33;color:#fff;border-radius:8px;padding:26px 28px;margin-bottom:18px;border:1px solid rgba(255,255,255,.12)}
    .brand{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#9ee3dc;font-weight:700}
    h1{font-size:30px;line-height:1.15;margin:8px 0 4px;color:#fff}
    .subtitle{color:#d5e7e9;margin:0;font-size:15px}
    .content{background:#fff;border:1px solid var(--line);border-radius:8px;padding:26px}
    h2{font-size:21px;margin:30px 0 12px;color:#123e42;border-top:1px solid var(--line);padding-top:22px}
    .content h2:first-child{border-top:0;padding-top:0;margin-top:0}
    p{margin:10px 0;color:#263d43}
    ul{margin:8px 0 18px;padding-left:20px}
    li{margin:5px 0;color:#263d43}
    .table-wrap{overflow:auto;border:1px solid var(--line);border-radius:8px;margin:12px 0 22px}
    table{border-collapse:collapse;width:100%;min-width:900px;font-size:12.5px}
    th{background:#123e42;color:#fff;text-align:left;padding:9px 10px;white-space:nowrap;position:sticky;top:0}
    td{padding:8px 10px;border-top:1px solid #e7eef1;vertical-align:top;white-space:nowrap}
    tr:nth-child(even) td{background:#f8fbfc}
    code{background:#eef5f6;padding:2px 5px;border-radius:4px}
    .footer{color:var(--muted);font-size:12px;margin-top:14px}
    @media(max-width:760px){.shell{padding:12px}.hero,.content{padding:18px}h1{font-size:24px}table{font-size:12px}}
    """
    body = "\n".join(parts)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Adda Intraday F&O Strategy Report</title>
  <style>{css}</style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="brand">Agent Adda Research</div>
      <h1>Intraday F&O Strategy Report</h1>
      <p class="subtitle">Opening-range, VWAP, F&O positioning, and Monday execution plan.</p>
    </section>
    <section class="content">{body}</section>
    <p class="footer">Generated locally from Agent Adda research artifacts and PostgreSQL evidence.</p>
  </main>
</body>
</html>
"""


def write_report(markdown: str, output_dir: Path = LATEST_DIR) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    dated_dir = ROOT / "reports" / "research"
    dated_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
    latest_md = output_dir / "agent_adda_intraday_fno_strategy_report.md"
    latest_html = output_dir / "agent_adda_intraday_fno_strategy_report.html"
    dated_md = dated_dir / f"agent_adda_intraday_fno_strategy_report_{stamp}.md"
    dated_html = dated_dir / f"agent_adda_intraday_fno_strategy_report_{stamp}.html"
    html_doc = markdown_to_html(markdown)
    latest_md.write_text(markdown, encoding="utf-8")
    latest_html.write_text(html_doc, encoding="utf-8")
    dated_md.write_text(markdown, encoding="utf-8")
    dated_html.write_text(html_doc, encoding="utf-8")
    return {"markdown": latest_md, "html": latest_html, "dated_markdown": dated_md, "dated_html": dated_html}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build comprehensive Agent Adda intraday F&O report.")
    parser.add_argument(
        "--source",
        default=str(LATEST_DIR / "intraday_fno_indicator_study.md"),
        help="Source intraday F&O study markdown.",
    )
    args = parser.parse_args(argv)
    source = Path(args.source)
    if not source.is_absolute():
        source = (ROOT / source).resolve()
    if not source.exists():
        raise SystemExit(f"source report not found: {source}")
    markdown = build_markdown(source)
    paths = write_report(markdown)
    print(f"Markdown: {paths['markdown']}")
    print(f"HTML: {paths['html']}")
    print(f"Dated HTML: {paths['dated_html']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
