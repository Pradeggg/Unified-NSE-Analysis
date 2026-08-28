"""NSE Market Intelligence MCP Server.

Exposes the local PostgreSQL NSE database as conversational tools
that Claude can call when answering questions about the Indian market.

Run:
    source .venv/bin/activate
    python mcp_server.py

Add to Claude Code settings.json:
    {
      "mcpServers": {
        "nse": {
          "command": "/path/to/.venv/bin/python",
          "args": ["/path/to/mcp_server.py"]
        }
      }
    }
"""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path

import psycopg2
import psycopg2.extras

from mcp.server.mcpserver import MCPServer
from mcp.server.stdio import stdio_server

# ── Config ────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent
DSN = (
    os.environ.get("AGENT_ADDA_PG_DSN")
    or os.environ.get("PG_DSN")
    or "dbname=nse_market user=nse_admin host=/tmp"
)
STRATEGY_LAB_DIR = ROOT / "portfolio" / "data" / "nse_pg_strategy_lab" / "nifty500"

server = MCPServer("nse-intelligence")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _conn():
    return psycopg2.connect(DSN, cursor_factory=psycopg2.extras.RealDictCursor)


def _fmt_table(rows: list[dict], cols: list[str] | None = None) -> str:
    """Format a list of dicts as a markdown table."""
    if not rows:
        return "_No data._"
    cols = cols or list(rows[0].keys())
    header = " | ".join(cols)
    sep = " | ".join("---" for _ in cols)
    lines = [header, sep]
    for r in rows:
        lines.append(" | ".join(str(r.get(c, "")) for c in cols))
    return "\n".join(lines)


def _latest_snapshot_date(cur) -> str:
    cur.execute("SELECT max(snapshot_date)::text AS d FROM scores.stage_snapshots")
    return cur.fetchone()["d"]


# ── Tool 1: Market Overview ───────────────────────────────────────────────────

@server.tool(description=(
    "Current market overview: NIFTY breadth (advance/decline), 52-week highs/lows, "
    "FII/DII activity, global indices, and the latest index closes. "
    "Use this for general 'how is the market today?' questions."
))
def get_market_overview() -> str:
    with _conn() as conn:
        cur = conn.cursor()

        # Latest breadth
        cur.execute("""
            SELECT date::text, advances, declines, unchanged,
                   new_highs_52w, new_lows_52w,
                   advance_decline_ratio,
                   pct_above_sma50, pct_above_sma200
            FROM breadth.market_daily
            ORDER BY date DESC LIMIT 1
        """)
        breadth = cur.fetchone()

        # Key index closes
        cur.execute("""
            SELECT index_symbol, close, change_pct
            FROM market.index_eod
            WHERE trade_date = (SELECT max(trade_date) FROM market.index_eod)
              AND index_symbol IN ('Nifty 50','Nifty 500','NIFTY BANK',
                                   'NIFTY MIDCAP 100','NIFTY SMALLCAP 100',
                                   'India VIX')
            ORDER BY index_symbol
        """)
        indices = cur.fetchall()

        # Global indices
        cur.execute("""
            SELECT symbol, close, date::text
            FROM market.global_index_levels
            WHERE date = (SELECT max(date) FROM market.global_index_levels)
            ORDER BY symbol
        """)
        global_idx = cur.fetchall()

        # FII/DII latest
        cur.execute("""
            SELECT date::text, fii_net_cr, dii_net_cr
            FROM signals.fii_dii_flows
            ORDER BY date DESC LIMIT 3
        """)
        fii = cur.fetchall()

    parts = []

    if breadth:
        ad = breadth.get("advances", 0) or 0
        dc = breadth.get("declines", 0) or 0
        parts.append(f"## Market Breadth — {breadth['date']}")
        parts.append(
            f"Advances **{ad}** · Declines **{dc}** · "
            f"A/D ratio **{breadth.get('advance_decline_ratio') or 'N/A'}**\n"
            f"52-week Highs **{breadth.get('new_highs_52w') or 'N/A'}** · "
            f"Lows **{breadth.get('new_lows_52w') or 'N/A'}**\n"
            f"% above SMA50: **{breadth.get('pct_above_sma50') or 'N/A'}%** · "
            f"SMA200: **{breadth.get('pct_above_sma200') or 'N/A'}%**"
        )

    if indices:
        parts.append("\n## NSE Index Closes")
        for r in indices:
            chg = r.get("change_pct")
            chg_str = f"{chg:+.2f}%" if chg is not None else ""
            parts.append(f"- **{r['index_symbol']}**: {r['close']:,.2f}  {chg_str}")

    if global_idx:
        parts.append("\n## Global Indices")
        for r in global_idx:
            parts.append(f"- {r['symbol']}: {r['close']:.2f}  ({r['date']})")

    if fii:
        parts.append("\n## FII / DII Flows (₹ Cr)")
        parts.append(_fmt_table(list(fii), ["date", "fii_net_cr", "dii_net_cr"]))

    return "\n".join(parts) if parts else "No market data available."


# ── Tool 2: Stage 2 Picks ─────────────────────────────────────────────────────

@server.tool(description=(
    "Stocks currently in Minervini Stage 2 (uptrend) from a given NSE index. "
    "Returns symbol, price, RSI, relative strength, technical score, and sector. "
    "Use for 'what Stage 2 stocks should I watch?' questions. "
    "index options: 'NIFTY 500', 'NIFTY 100', 'NIFTY 50', 'NIFTY MIDCAP 100', 'NIFTY SMALLCAP 100'."
))
def get_stage2_picks(
    index: str = "NIFTY 500",
    sector: str | None = None,
    min_rs: float = 0,
    limit: int = 25,
) -> str:
    with _conn() as conn:
        cur = conn.cursor()
        snap_date = _latest_snapshot_date(cur)

        sector_clause = "AND i.sector ILIKE %(sector)s" if sector else ""
        cur.execute(f"""
            SELECT ss.symbol,
                   ss.price,
                   ss.change_1d_pct,
                   ss.rsi,
                   ss.relative_strength,
                   ss.technical_score,
                   ss.stage_score,
                   i.sector,
                   i.market_cap_cat
            FROM scores.stage_snapshots ss
            LEFT JOIN ref.instruments i ON i.symbol = ss.symbol
            JOIN ref.index_compositions ic
              ON ic.symbol = ss.symbol AND ic.index_symbol = %(index)s
            WHERE ss.snapshot_date = %(snap)s
              AND ss.stage = 'STAGE_2'
              AND ss.relative_strength >= %(min_rs)s
              {sector_clause}
            ORDER BY ss.relative_strength DESC NULLS LAST
            LIMIT %(limit)s
        """, {"snap": snap_date, "index": index, "min_rs": min_rs,
              "sector": f"%{sector}%", "limit": limit})
        rows = cur.fetchall()

    if not rows:
        return f"No Stage 2 stocks found in {index}{' / ' + sector if sector else ''}."

    lines = [f"## Stage 2 Stocks — {index} — {snap_date}",
             f"_{len(rows)} stocks in Stage 2_\n"]
    lines.append("| Symbol | Price | Chg% | RSI | RS | TS | Sector | Cap |")
    lines.append("|--------|------:|-----:|----:|---:|---:|--------|-----|")
    for r in rows:
        chg = f"{r['change_1d_pct']:+.1f}" if r.get("change_1d_pct") is not None else ""
        lines.append(
            f"| {r['symbol']} | {r['price']:.2f} | {chg} "
            f"| {r['rsi']:.0f} | {r['relative_strength']:.0f} "
            f"| {r['technical_score'] or 0:.0f} "
            f"| {r.get('sector') or ''} | {r.get('market_cap_cat') or ''} |"
        )
    return "\n".join(lines)


# ── Tool 3: Stock Profile ─────────────────────────────────────────────────────

@server.tool(description=(
    "Full profile for any NSE-listed stock: current stage, price, RSI, "
    "relative strength, fundamental scores, recent quarterly results, "
    "and 30-day stage history. Use for single-stock deep dives."
))
def get_stock_profile(symbol: str) -> str:
    symbol = symbol.upper().strip()
    with _conn() as conn:
        cur = conn.cursor()

        # Latest snapshot
        cur.execute("""
            SELECT ss.*, i.sector, i.isin, i.market_cap_cat
            FROM scores.stage_snapshots ss
            LEFT JOIN ref.instruments i ON i.symbol = ss.symbol
            WHERE ss.symbol = %s
            ORDER BY ss.snapshot_date DESC LIMIT 1
        """, (symbol,))
        snap = cur.fetchone()

        # 30-day stage history
        cur.execute("""
            SELECT snapshot_date::text, stage, price, rsi, relative_strength
            FROM scores.stage_snapshots
            WHERE symbol = %s
            ORDER BY snapshot_date DESC LIMIT 30
        """, (symbol,))
        history = cur.fetchall()

        # Fundamentals
        cur.execute("""
            SELECT revenue_growth_3y, pat_growth_3y, roe, roce, debt_to_equity,
                   pe_ratio, pb_ratio, market_cap_cr
            FROM scores.fundamentals
            WHERE symbol = %s LIMIT 1
        """, (symbol,))
        fund = cur.fetchone()

        # Quarterly results (last 4)
        cur.execute("""
            SELECT period_label, revenue, pat, eps, opm_pct
            FROM scores.quarterly_results
            WHERE symbol = %s
            ORDER BY period_end DESC LIMIT 4
        """, (symbol,))
        qtrs = cur.fetchall()

        # Latest EOD
        cur.execute("""
            SELECT trade_date::text, open, high, low, close, volume, turnover_cr
            FROM market.equity_eod
            WHERE symbol = %s AND series = 'EQ'
            ORDER BY trade_date DESC LIMIT 1
        """, (symbol,))
        eod = cur.fetchone()

    if not snap:
        return f"No data found for **{symbol}**. Check the symbol spelling."

    parts = [f"## {symbol} — {snap.get('sector', '')} · {snap.get('market_cap_cat', '')}"]

    # Stage badge
    stage = snap.get("stage", "UNKNOWN")
    stage_emoji = {"STAGE_2": "🟢", "STAGE_1": "🟡", "STAGE_3": "🔴", "STAGE_4": "🔴"}.get(stage, "⚪")
    parts.append(f"{stage_emoji} **{stage}** as of {snap['snapshot_date']}")

    if eod:
        parts.append(
            f"\n**Price**: ₹{eod['close']:.2f}  "
            f"(O:{eod['open']:.2f} H:{eod['high']:.2f} L:{eod['low']:.2f})  "
            f"Vol: {eod['volume']:,}  Turnover: ₹{eod['turnover_cr']:.1f} Cr"
            f"  _{eod['trade_date']}_"
        )

    parts.append(
        f"\n**RSI**: {snap.get('rsi') or 'N/A':.1f}  "
        f"**Relative Strength**: {snap.get('relative_strength') or 0:.0f}/100  "
        f"**Technical Score**: {snap.get('technical_score') or 0:.0f}/100"
    )

    if fund:
        parts.append("\n### Fundamentals")
        parts.append(
            f"Revenue Growth (3Y): **{fund.get('revenue_growth_3y') or 'N/A'}%** · "
            f"PAT Growth (3Y): **{fund.get('pat_growth_3y') or 'N/A'}%**\n"
            f"ROE: **{fund.get('roe') or 'N/A'}%** · "
            f"ROCE: **{fund.get('roce') or 'N/A'}%** · "
            f"D/E: **{fund.get('debt_to_equity') or 'N/A'}**\n"
            f"PE: **{fund.get('pe_ratio') or 'N/A'}** · "
            f"PB: **{fund.get('pb_ratio') or 'N/A'}** · "
            f"Mcap: ₹**{fund.get('market_cap_cr') or 'N/A'}** Cr"
        )

    if qtrs:
        parts.append("\n### Quarterly Results")
        parts.append(_fmt_table(list(qtrs),
                                ["period_label", "revenue", "pat", "eps", "opm_pct"]))

    if history:
        parts.append("\n### 30-Day Stage History")
        stage_history = " → ".join(
            f"{r['snapshot_date'][-5:]}:{r['stage'].replace('STAGE_','S')}"
            for r in reversed(history)
        )
        parts.append(stage_history)

    return "\n".join(parts)


# ── Tool 4: Swing Candidates ──────────────────────────────────────────────────

@server.tool(description=(
    "Top liquid NSE stocks in Stage 2 suitable for swing trading. "
    "Filters for high turnover (liquid), RSI not overbought, "
    "and strong relative strength. Returns entry context and key levels."
))
def get_swing_candidates(limit: int = 15) -> str:
    with _conn() as conn:
        cur = conn.cursor()
        snap_date = _latest_snapshot_date(cur)

        cur.execute("""
            SELECT ss.symbol, ss.price, ss.change_1d_pct, ss.rsi,
                   ss.relative_strength, ss.technical_score,
                   CASE
                     WHEN e.turnover_cr > 1e9 THEN round((e.turnover_cr / 1e7)::numeric, 1)
                     ELSE round(e.turnover_cr::numeric, 1)
                   END AS turnover_cr,
                   i.sector
            FROM scores.stage_snapshots ss
            JOIN market.equity_eod e
              ON e.symbol = ss.symbol
             AND e.trade_date = (SELECT max(trade_date) FROM market.equity_eod WHERE series='EQ')
             AND e.series = 'EQ'
            LEFT JOIN ref.instruments i ON i.symbol = ss.symbol
            WHERE ss.snapshot_date = %s
              AND ss.stage = 'STAGE_2'
              AND ss.rsi BETWEEN 40 AND 70
              AND ss.relative_strength >= 55
              AND e.turnover_cr IS NOT NULL
              AND e.turnover_cr > 0
            ORDER BY e.turnover_cr DESC NULLS LAST
            LIMIT %s
        """, (snap_date, limit))
        rows = cur.fetchall()

    if not rows:
        return "No swing candidates found for today."

    lines = [f"## Swing Candidates — {snap_date}", ""]
    lines.append("| Symbol | Price | Chg% | RSI | RS | Turnover Cr | Sector |")
    lines.append("|--------|------:|-----:|----:|---:|------------:|--------|")
    for r in rows:
        chg = f"{r['change_1d_pct']:+.1f}" if r.get("change_1d_pct") is not None else ""
        tc = r.get("turnover_cr") or 0
        lines.append(
            f"| {r['symbol']} | {r['price']:.2f} | {chg} "
            f"| {r['rsi']:.0f} | {r['relative_strength']:.0f} "
            f"| {tc:.1f} | {r.get('sector') or ''} |"
        )
    return "\n".join(lines)


# ── Tool 5: Sector Rotation ───────────────────────────────────────────────────

@server.tool(description=(
    "Sector-level stage distribution and relative strength from NIFTY 500. "
    "Shows which sectors have the most Stage 2 stocks and best average RS. "
    "Use for 'which sectors are leading?' questions."
))
def get_sector_rotation() -> str:
    with _conn() as conn:
        cur = conn.cursor()
        snap_date = _latest_snapshot_date(cur)

        cur.execute("""
            SELECT i.sector,
                   count(*) AS total,
                   count(*) FILTER (WHERE ss.stage = 'STAGE_2') AS stage2,
                   count(*) FILTER (WHERE ss.stage = 'STAGE_1') AS stage1,
                   count(*) FILTER (WHERE ss.stage = 'STAGE_3') AS stage3,
                   count(*) FILTER (WHERE ss.stage = 'STAGE_4') AS stage4,
                   round(avg(ss.relative_strength)::numeric, 1) AS avg_rs,
                   round(avg(ss.technical_score)::numeric, 1)   AS avg_ts
            FROM scores.stage_snapshots ss
            JOIN ref.instruments i ON i.symbol = ss.symbol
            JOIN ref.index_compositions ic
              ON ic.symbol = ss.symbol AND ic.index_symbol = 'NIFTY 500'
            WHERE ss.snapshot_date = %s
              AND i.sector IS NOT NULL AND i.sector != ''
            GROUP BY i.sector
            ORDER BY stage2 DESC, avg_rs DESC
        """, (snap_date,))
        rows = cur.fetchall()

    if not rows:
        return "No sector data available."

    lines = [f"## Sector Rotation — NIFTY 500 — {snap_date}", ""]
    lines.append("| Sector | S2 | S1 | S3 | S4 | Total | Avg RS | Avg TS |")
    lines.append("|--------|---:|---:|---:|---:|------:|-------:|-------:|")
    for r in rows:
        lines.append(
            f"| {r['sector']} | **{r['stage2']}** | {r['stage1']} "
            f"| {r['stage3']} | {r['stage4']} | {r['total']} "
            f"| {r['avg_rs']} | {r['avg_ts']} |"
        )
    return "\n".join(lines)


# ── Tool 6: Strategy Lab Results ─────────────────────────────────────────────

@server.tool(description=(
    "Portfolio strategy lab backtest results on NIFTY 500 universe "
    "(Jan 2025 – Aug 2026). Returns leaderboard with returns, alpha vs benchmark, "
    "win rate, max drawdown, and trade counts. "
    "Also returns the trade log for a specific strategy if requested. "
    "strategy options: 'stage2_continuation_v1', 'darvas_box_breakout_v1', "
    "'vcp_breakout_v1', 'donchian_turtle_breakout_v1', "
    "'momentum_rotation_v1', 'moving_average_trend_v1', "
    "'mean_reversion_uptrend_v1', 'minervini_trend_template_v1'."
))
def get_strategy_lab(strategy_id: str | None = None) -> str:
    summary_path = STRATEGY_LAB_DIR / "reports" / "strategy_comparison_summary.json"
    if not summary_path.exists():
        return "Strategy lab data not found. Run the strategy lab first."

    summary = json.loads(summary_path.read_text())
    lb = summary.get("leaderboard", [])
    bench = lb[0].get("benchmark_return_pct", 0) if lb else 0

    parts = [
        f"## Strategy Lab — NIFTY 500 Universe",
        f"Period: **{summary.get('start_date')} → {summary.get('end_date')}** · "
        f"Universe: **{summary.get('symbol_count')} stocks** · "
        f"Benchmark (NIFTY 500): **+{bench:.2f}%**\n"
    ]

    # Leaderboard table
    verdict_icon = {"PASS": "✅", "WARN": "⚠️", "BLOCK": "🚫"}
    parts.append("| # | Strategy | Fills | Return | Alpha | Max DD | Win Rate | Verdict |")
    parts.append("|---|----------|------:|-------:|------:|-------:|---------:|---------|")
    for r in lb:
        icon = verdict_icon.get(r.get("critic_verdict", ""), "")
        parts.append(
            f"| {r['rank']} | {r['name']} | {r['fills']} "
            f"| {r['total_return_pct']:+.2f}% | {r['excess_return_pct']:+.2f}% "
            f"| {r['max_drawdown_pct']:.1f}% | {r['win_rate_pct']:.0f}% "
            f"| {icon} {r.get('critic_verdict','')} |"
        )

    # Trade log for a specific strategy
    if strategy_id:
        state_path = STRATEGY_LAB_DIR / "runs" / strategy_id / "state" / "replay_state.json"
        if not state_path.exists():
            parts.append(f"\n_Trade log not found for `{strategy_id}`._")
        else:
            state = json.loads(state_path.read_text())
            fills = state.get("fills", [])
            open_pos = {}
            trades = []
            for f in fills:
                sym = f["symbol"]
                if f["side"] == "BUY":
                    open_pos[sym] = f
                elif f["side"] == "SELL" and sym in open_pos:
                    buy = open_pos.pop(sym)
                    qty = min(buy["quantity"], f["quantity"])
                    pnl = (f["fill_price"] - buy["fill_price"]) * qty \
                          - buy.get("fees", 0) - f.get("fees", 0)
                    pct = (f["fill_price"] - buy["fill_price"]) / buy["fill_price"] * 100
                    trades.append({
                        "symbol": sym,
                        "entry": buy["fill_date"],
                        "exit": f["fill_date"],
                        "entry_px": round(buy["fill_price"], 2),
                        "exit_px": round(f["fill_price"], 2),
                        "qty": qty,
                        "pnl": round(pnl, 0),
                        "pct": round(pct, 2),
                    })

            name = next((r["name"] for r in lb if r["strategy_id"] == strategy_id), strategy_id)
            parts.append(f"\n### Trade Log — {name} ({len(trades)} completed trades)")
            parts.append("| Symbol | Entry | Exit | Entry ₹ | Exit ₹ | Qty | P&L ₹ | % |")
            parts.append("|--------|-------|------|--------:|-------:|----:|------:|---|")
            for t in sorted(trades, key=lambda x: x["exit"]):
                sign = "🟢" if t["pnl"] >= 0 else "🔴"
                parts.append(
                    f"| {sign} {t['symbol']} | {t['entry']} | {t['exit']} "
                    f"| {t['entry_px']:,.2f} | {t['exit_px']:,.2f} "
                    f"| {t['qty']} | {t['pnl']:+,.0f} | {t['pct']:+.2f}% |"
                )

    return "\n".join(parts)


# ── Tool 7: F&O Signals ───────────────────────────────────────────────────────

@server.tool(description=(
    "F&O (Futures & Options) signals for NSE stocks and indices. "
    "Returns PCR (Put-Call Ratio), OI buildup, max pain levels, and "
    "open interest changes. PCR > 1.2 = bullish, < 0.8 = bearish."
))
def get_fno_signals(symbol: str | None = None, limit: int = 20) -> str:
    with _conn() as conn:
        cur = conn.cursor()

        where = "WHERE symbol = %s" if symbol else ""
        params = (symbol.upper(),) if symbol else ()
        cur.execute(f"""
            SELECT symbol, signal_date::text, signal_type, pcr, max_pain,
                   oi_change_pct, buildup_type, signal_strength
            FROM derivatives.fno_signals
            {where}
            ORDER BY signal_date DESC, signal_strength DESC NULLS LAST
            LIMIT %s
        """, params + (limit,))
        rows = cur.fetchall()

    if not rows:
        return "No F&O signals available" + (f" for {symbol.upper()}" if symbol else "") + "."

    title = f"## F&O Signals{' — ' + symbol.upper() if symbol else ''}"
    return title + "\n\n" + _fmt_table(
        list(rows),
        ["symbol", "signal_date", "signal_type", "pcr", "max_pain",
         "oi_change_pct", "buildup_type", "signal_strength"]
    )


# ── Tool 8: Bulk & Block Deals ────────────────────────────────────────────────

@server.tool(description=(
    "Recent bulk deals and block deals on NSE. "
    "These are large institutional trades — significant buying/selling by "
    "mutual funds, FIIs, or promoters. Use for 'who is buying/selling?' questions."
))
def get_bulk_block_deals(symbol: str | None = None, limit: int = 20) -> str:
    with _conn() as conn:
        cur = conn.cursor()
        where = "WHERE symbol = %s" if symbol else ""
        params = (symbol.upper(),) if symbol else ()
        cur.execute(f"""
            SELECT deal_date::text, symbol, client_name, deal_type,
                   quantity, price, value_cr
            FROM signals.bulk_block_deals
            {where}
            ORDER BY deal_date DESC, value_cr DESC NULLS LAST
            LIMIT %s
        """, params + (limit,))
        rows = cur.fetchall()

    if not rows:
        return "No bulk/block deal data available" + (f" for {symbol.upper()}" if symbol else "") + "."

    title = f"## Bulk & Block Deals{' — ' + symbol.upper() if symbol else ''}"
    return title + "\n\n" + _fmt_table(
        list(rows),
        ["deal_date", "symbol", "client_name", "deal_type", "quantity", "price", "value_cr"]
    )


# ── Tool 9: Corporate Events ──────────────────────────────────────────────────

@server.tool(description=(
    "Upcoming and recent corporate events: dividends, bonus issues, "
    "rights offerings, AGMs, stock splits, and result dates. "
    "Use for 'what events does RELIANCE have?' or 'upcoming dividends?'"
))
def get_corporate_events(symbol: str | None = None, days_ahead: int = 30) -> str:
    with _conn() as conn:
        cur = conn.cursor()
        if symbol:
            cur.execute("""
                SELECT ex_date::text, symbol, event_type, details, record_date::text
                FROM signals.corporate_events
                WHERE symbol = %s
                ORDER BY ex_date DESC LIMIT 20
            """, (symbol.upper(),))
        else:
            cur.execute("""
                SELECT ex_date::text, symbol, event_type, details
                FROM signals.corporate_events
                WHERE ex_date BETWEEN current_date AND current_date + %s
                ORDER BY ex_date ASC LIMIT 30
            """, (days_ahead,))
        rows = cur.fetchall()

    if not rows:
        return "No corporate events found."

    title = f"## Corporate Events{' — ' + symbol.upper() if symbol else ' (Next ' + str(days_ahead) + ' days)'}"
    cols = ["ex_date", "symbol", "event_type", "details"] + (["record_date"] if symbol else [])
    return title + "\n\n" + _fmt_table(list(rows), cols)


# ── KB Tools Query — coding-assistant fast-path ───────────────────────────────
# PG 2026-08-25: Exposes the BM25 skills/commands/workflows index so that
# coding assistants (Claude Code, Copilot, Cursor) can query it via MCP
# BEFORE searching source code — dramatically reducing token usage.

@server.tool(description=(
    "Query the Agent Adda Knowledge Base for skills, commands, tools, and workflows. "
    "Call this FIRST when you need to know HOW to do something in Agent Adda "
    "(run the pipeline, build a chart, screen for stocks, etc.) — it returns "
    "the exact CLI command, trigger phrases, ordering rules, and Ollama guidance "
    "without requiring any source-code search. "
    "Returns a markdown context block with ranked results and token-savings metadata."
))
async def query_kb_tools(
    query: str,
    top_k: int = 5,
    fmt: str = "context",
    web: bool = False,
    hybrid: bool = False,
    max_tokens: int = 2000,
) -> str:
    """BM25 search over 160+ skills/commands/tools/workflows.

    Parameters
    ----------
    query : str
        Natural-language question (e.g. 'how to run daily pipeline', 'chart RELIANCE').
    top_k : int
        Number of results to return (default 5, max 10).
    fmt : str
        'context' (default) for prompt-ready markdown, 'json' for machine-readable,
        'context-compact' for a tighter token budget.
    web : bool
        If true, append live web-search hits (Layer 3) for recency.
    hybrid : bool
        If true, augment BM25 with vector search (Layer 2) when available.
    max_tokens : int
        Soft token budget for context output (default 2000).
    """
    try:
        from knowledge_base.kb_tools_query import query_tools  # noqa: WPS433
        k = max(1, min(int(top_k), 10))
        result = query_tools(
            query,
            k=k,
            fmt=fmt,
            hybrid=bool(hybrid),
            web=bool(web),
            max_tokens=int(max_tokens),
            caller="mcp",
        )
        block = result["context_block"]
        # Append lightweight token accounting for the MCP caller
        web_n = len(result.get("web_hits", []) or [])
        block += (
            f"\n\n<!-- KB token accounting: "
            f"in={result['tokens_in']} out={result['tokens_out']} "
            f"saved≈{result['token_savings']} | "
            f"method={result['search_method']} web={web_n} "
            f"latency={result['latency_ms']:.1f}ms -->"
        )
        return block
    except Exception as exc:
        return f"KB query failed: {exc}\nFallback: run `python -m knowledge_base query \"{query}\"`"


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
