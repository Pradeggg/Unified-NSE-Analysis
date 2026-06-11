"""
terminal/renderer.py — Financial-grade Rich terminal rendering for Agent Adda.

Provides structured, colour-coded output for:
  • Gainers / losers tables       (green / red gradient by % move)
  • Market breadth panel          (ASCII bar charts: A/D, Stage distribution)
  • FII / DII flow panel          (directional bars)
  • Sector performance table      (heat-coded by relative performance)
  • Screener / Stage-2 results    (coloured by score / signal)
  • Index snapshot panel          (compact multi-index overview)
  • Mini ASCII sparkline          (7-bar price trend for inline use)
  • Pre-render LLM planner        (fast gpt-4o-mini call to decide layout)

Usage (from nse_agent.py):
    from terminal.renderer import render_trace_tables, pre_render_plan, apply_render_plan
    plan = pre_render_plan(answer, trace)       # ~200ms fast LLM call
    apply_render_plan(plan)                     # summary strip + header colour
    render_trace_tables(trace, plan=plan)       # structured tables, guided by plan
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from typing import Any

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

# Shared console — caller may override via set_console()
_console: Console = Console(highlight=False, force_terminal=True)

# PG 2026-05-20: cache of the most recently completed REPL turn's rich console
# output, so capabilities like /screenshot can attach the terminal context that
# preceded their invocation. Populated by nse_agent's REPL loop between turns.
_last_turn_html: str = ""
_last_turn_text: str = ""


def set_console(con: Console) -> None:
    global _console
    _console = con


def get_console() -> Console:
    return _console


def get_last_turn_capture() -> tuple[str, str]:
    """Return (html, text) snapshot of the prior REPL turn's console output."""
    return _last_turn_html, _last_turn_text


def set_last_turn_capture(html: str, text: str) -> None:
    global _last_turn_html, _last_turn_text
    _last_turn_html, _last_turn_text = html or "", text or ""


# ─────────────────────────────────────────────────────────────────────────────
# Colour helpers
# ─────────────────────────────────────────────────────────────────────────────

def _pct_style(pct: float | None) -> str:
    if pct is None:
        return "dim"
    if pct >= 4.0:
        return "bold bright_green"
    if pct >= 2.0:
        return "green"
    if pct >= 0.5:
        return "bright_green"
    if pct >= -0.5:
        return "yellow"
    if pct >= -2.0:
        return "red"
    if pct >= -4.0:
        return "bright_red"
    return "bold bright_red"


def _signal_style(sig: str | None) -> str:
    if not sig:
        return "dim"
    s = sig.upper()
    if "STRONG_BUY" in s:
        return "bold bright_green"
    if "BUY" in s:
        return "green"
    if "STRONG_SELL" in s:
        return "bold bright_red"
    if "SELL" in s:
        return "red"
    if "HOLD" in s:
        return "yellow"
    return "dim"


def _stage_style(stage: str | None) -> str:
    if not stage:
        return "dim"
    s = str(stage).upper()
    if "2" in s:
        return "bold green"
    if "1" in s:
        return "cyan"
    if "3" in s:
        return "yellow"
    if "4" in s:
        return "red"
    return "dim"


def _score_style(score: float | None) -> str:
    if score is None:
        return "dim"
    if score >= 80:
        return "bold bright_green"
    if score >= 60:
        return "green"
    if score >= 40:
        return "yellow"
    return "red"


def _fmt_pct(v: float | None, na: str = "—") -> str:
    if v is None:
        return na
    sign = "▲" if v >= 0 else "▼"
    return f"{sign} {abs(v):.2f}%"


def _fmt_price(v: float | None, na: str = "—") -> str:
    if v is None:
        return na
    return f"₹{v:,.2f}"


def _ascii_bar(value: float, max_val: float, width: int = 12, fill: str = "█", empty: str = "░") -> str:
    """Render a horizontal ASCII bar proportional to value/max_val."""
    if max_val <= 0:
        return empty * width
    ratio = min(abs(value) / max_val, 1.0)
    filled = round(ratio * width)
    return fill * filled + empty * (width - filled)


def _sparkline(values: list[float], width: int = 7) -> str:
    """7-block ASCII sparkline from a list of prices."""
    _bars = "▁▂▃▄▅▆▇█"
    if not values or len(values) < 2:
        return "─" * width
    # Downsample to `width` points
    step = max(1, len(values) // width)
    pts = [values[i] for i in range(0, len(values), step)][:width]
    mn, mx = min(pts), max(pts)
    if mx == mn:
        return "▄" * len(pts)
    return "".join(_bars[round((v - mn) / (mx - mn) * 7)] for v in pts)


# ─────────────────────────────────────────────────────────────────────────────
# Gainers / Losers
# ─────────────────────────────────────────────────────────────────────────────

def render_gainers_losers(data: dict) -> None:
    """Render top gainers and losers as a colour-coded Rich table."""
    gainers = data.get("gainers", [])
    losers  = data.get("losers",  [])
    index   = data.get("index", "NSE")
    as_of   = data.get("as_of", "")

    if not gainers and not losers:
        return

    def _make_table(stocks: list[dict], direction: str) -> Table:
        colour = "green" if direction == "gainers" else "red"
        icon   = "▲" if direction == "gainers" else "▼"
        tbl = Table(
            box=box.SIMPLE_HEAD,
            header_style=f"bold {colour}",
            show_header=True,
            expand=True,
            padding=(0, 1),
        )
        tbl.add_column(f"{icon} {'GAINERS' if direction == 'gainers' else 'LOSERS'}", style="bold white", min_width=12)
        tbl.add_column("Price", justify="right", min_width=10)
        tbl.add_column("% Chg", justify="right", min_width=8)
        tbl.add_column("Chg ₹", justify="right", min_width=8)
        tbl.add_column("Vol (Cr)", justify="right", min_width=9)
        tbl.add_column("52w H/L", justify="right", min_width=14)

        for i, s in enumerate(stocks):
            pct = s.get("pct_change")
            chg = s.get("change")
            sym = s.get("symbol", "—")
            price = s.get("last_price")
            vol   = s.get("volume")
            yh    = s.get("year_high")
            yl    = s.get("year_low")

            st = _pct_style(pct)
            # Bold top 3
            sym_text = Text(sym, style="bold white" if i < 3 else "white")

            pct_text = Text(_fmt_pct(pct), style=st)
            chg_text = Text(f"{'+'if (chg or 0)>=0 else ''}{chg:.2f}" if chg is not None else "—", style=st)

            vol_str = f"{vol/1e7:.2f}" if vol else "—"

            hl_str = "—"
            if yh and yl:
                hl_str = f"{_fmt_price(yh)} / {_fmt_price(yl)}"
            elif yh:
                hl_str = f"H {_fmt_price(yh)}"

            tbl.add_row(
                sym_text,
                _fmt_price(price),
                pct_text,
                chg_text,
                vol_str,
                hl_str,
            )
        return tbl

    _console.print()
    _console.print(Rule(
        f"[bold cyan] 📈  Top Movers — {index}"
        + (f"  ·  {as_of}" if as_of else "") + " [/bold cyan]",
        style="dim cyan",
    ))

    panels = []
    if gainers:
        panels.append(Panel(_make_table(gainers, "gainers"), border_style="green", padding=(0, 1)))
    if losers:
        panels.append(Panel(_make_table(losers, "losers"),   border_style="red",   padding=(0, 1)))

    if len(panels) == 2:
        _console.print(Columns(panels, equal=True, expand=True))
    elif panels:
        _console.print(panels[0])


# ─────────────────────────────────────────────────────────────────────────────
# Market Breadth
# ─────────────────────────────────────────────────────────────────────────────

def render_market_breadth(data: dict) -> None:
    """Render A/D ratio, stage distribution, and index levels as a panel."""
    if data.get("error"):
        return

    def _stage_count(stages: dict, *keys: str) -> int:
        for key in keys:
            if key in stages:
                return int(stages.get(key) or 0)
        return 0

    tbl = Table(box=box.SIMPLE, header_style="bold dim", expand=True, padding=(0, 1))
    tbl.add_column("Metric", style="bold white", min_width=24, no_wrap=True)
    tbl.add_column("Value", min_width=12)
    tbl.add_column("Bar / Context", min_width=30)

    # ── Advance / Decline ────────────────────────────────────────────────────
    ad = data.get("advance_decline") or {
        "advances": data.get("advances"),
        "declines": data.get("declines"),
        "unchanged": data.get("unchanged"),
    }
    advances  = ad.get("advances",  0) or 0
    declines  = ad.get("declines",  0) or 0
    unchanged = ad.get("unchanged", 0) or 0
    total_ad  = advances + declines
    if total_ad > 0:
        ad_ratio = advances / total_ad
        bar_a    = _ascii_bar(advances,  total_ad, 20, "█", "░")
        bar_d    = _ascii_bar(declines,  total_ad, 20, "█", "░")
        ad_style = "green" if ad_ratio > 0.55 else "red" if ad_ratio < 0.45 else "yellow"
        tbl.add_row(
            "Advance / Decline",
            Text(f"{advances} / {declines}", style=ad_style),
            Text.from_markup(
                f"[green]{bar_a[:round(ad_ratio*20)]}[/green][red]{'█'*round((1-ad_ratio)*20)}[/red]"
                + f"  {ad_ratio*100:.0f}% adv"
            ),
        )
        if unchanged:
            tbl.add_row("Unchanged", str(unchanged), "")

    # ── Stage distribution ───────────────────────────────────────────────────
    stages = data.get("stage_distribution", {})
    if stages:
        tbl.add_section()
        tbl.add_row(Text("── Stage Distribution ──", style="bold dim"), "", "")
        stage_rows = [
            (_stage_count(stages, "stage_1", "STAGE_1", "Stage 1"), "Stage 1  (base)", "cyan"),
            (_stage_count(stages, "stage_2", "STAGE_2", "Stage 2"), "Stage 2  (uptrend)", "bold green"),
            (_stage_count(stages, "stage_3", "STAGE_3", "Stage 3"), "Stage 3  (top)", "yellow"),
            (_stage_count(stages, "stage_4", "STAGE_4", "Stage 4"), "Stage 4  (downtrend)", "red"),
        ]
        total_s = sum(n for n, _, _ in stage_rows) or 1
        for n, label, colour in stage_rows:
            pct = n / total_s * 100
            bar = _ascii_bar(n, total_s, 18)
            tbl.add_row(
                label,
                Text(f"{n}  ({pct:.0f}%)", style=colour),
                Text(bar, style=colour),
            )

    # ── Relative strength distribution ───────────────────────────────────────
    percentiles = data.get("rs_percentiles") or {}
    distribution = data.get("rs_distribution") or {}
    if percentiles or distribution:
        tbl.add_section()
        tbl.add_row(Text("── RS Distribution ──", style="bold dim"), "", "")
        if percentiles:
            pct_bits = []
            for key in ("p10", "p25", "p50", "p75", "p90"):
                value = percentiles.get(key)
                if isinstance(value, (int, float)):
                    pct_bits.append(f"{key} {value:.1f}%")
            if pct_bits:
                tbl.add_row("RS percentiles", " | ".join(pct_bits), "")
        for key in ("negative", "neutral_0_25", "positive_25_50", "strong_50_plus"):
            row = distribution.get(key) if isinstance(distribution, dict) else None
            if not isinstance(row, dict):
                continue
            label = str(row.get("label") or key)
            count = row.get("count")
            pct = row.get("pct")
            pct_txt = f"{pct:.1f}%" if isinstance(pct, (int, float)) else ""
            tbl.add_row(label, str(count), pct_txt)

    # ── % above MAs ─────────────────────────────────────────────────────────
    ma_data = data.get("above_ma", {})
    if ma_data:
        tbl.add_section()
        tbl.add_row(Text("── % Above Moving Averages ──", style="bold dim"), "", "")
        for key, label in [("above_200ma", "Above 200 MA"), ("above_50ma", "Above 50 MA"), ("above_20ma", "Above 20 MA")]:
            pct = ma_data.get(key)
            if pct is not None:
                st = "green" if pct > 60 else "yellow" if pct > 40 else "red"
                bar = _ascii_bar(pct, 100, 18)
                tbl.add_row(label, Text(f"{pct:.0f}%", style=st), Text(bar, style=st))

    if tbl.row_count:
        _console.print()
        _console.print(Panel(tbl, title="[bold cyan]📊  Market Breadth[/bold cyan]", border_style="dim cyan", padding=(0, 1)))


# ─────────────────────────────────────────────────────────────────────────────
# FII / DII Flow
# ─────────────────────────────────────────────────────────────────────────────

def render_fii_dii(data: dict) -> None:
    """Render FII/DII flow with directional ASCII bars."""
    if data.get("error") or not data:
        return

    fii_net = data.get("fii_net") or data.get("fii", {}).get("net")
    dii_net = data.get("dii_net") or data.get("dii", {}).get("net")
    as_of   = data.get("date") or data.get("as_of", "")

    if fii_net is None and dii_net is None:
        return

    tbl = Table(box=box.SIMPLE, header_style="bold dim", expand=False, padding=(0, 1))
    tbl.add_column("Institution", style="bold white", min_width=12)
    tbl.add_column("Net (Cr)", justify="right", min_width=12)
    tbl.add_column("Direction", min_width=32)
    tbl.add_column("Sentiment", min_width=12)

    max_abs = max(abs(fii_net or 0), abs(dii_net or 0), 1)

    for label, net in [("FII / FPI", fii_net), ("DII", dii_net)]:
        if net is None:
            continue
        sign    = "+" if net >= 0 else ""
        colour  = "green" if net >= 0 else "red"
        bar_w   = round(abs(net) / max_abs * 24)
        bar     = ("█" * bar_w).ljust(24, "░") if net >= 0 else ("█" * bar_w).ljust(24, "░")
        arrow   = "▲ BUYER" if net >= 0 else "▼ SELLER"
        tbl.add_row(
            label,
            Text(f"{sign}{net:,.0f}", style=f"bold {colour}"),
            Text(bar[:24], style=colour),
            Text(arrow, style=colour),
        )

    _console.print()
    _console.print(Panel(
        tbl,
        title=f"[bold cyan]💹  FII / DII Flow{('  ·  ' + as_of) if as_of else ''}[/bold cyan]",
        border_style="dim cyan", padding=(0, 1),
    ))


# ─────────────────────────────────────────────────────────────────────────────
# Index Snapshot / Market Overview
# ─────────────────────────────────────────────────────────────────────────────

def render_market_overview(data: dict) -> None:
    """Compact multi-index levels panel."""
    indices = data.get("indices", {}) or {}
    if not indices:
        # try flat structure
        _KEYS = ["nifty_50", "nifty_bank", "nifty_it", "nifty_midcap", "nifty_smallcap",
                 "nifty50", "banknifty", "niftyit"]
        flat = {k: data[k] for k in _KEYS if k in data}
        if flat:
            indices = flat

    if not indices:
        return

    tbl = Table(box=box.SIMPLE_HEAD, header_style="bold dim", expand=True, padding=(0, 1))
    tbl.add_column("Index", style="bold white", min_width=18)
    tbl.add_column("Last", justify="right", min_width=10)
    tbl.add_column("Chg %", justify="right", min_width=8)
    tbl.add_column("High", justify="right", min_width=10)
    tbl.add_column("Low", justify="right", min_width=10)

    _LABELS = {
        "nifty_50": "NIFTY 50", "nifty50": "NIFTY 50",
        "nifty_bank": "NIFTY BANK", "banknifty": "NIFTY BANK",
        "nifty_it": "NIFTY IT", "niftyit": "NIFTY IT",
        "nifty_midcap": "NIFTY MIDCAP", "nifty_midcap_100": "NIFTY MIDCAP 100",
        "nifty_smallcap": "NIFTY SMALLCAP", "nifty_next_50": "NIFTY NEXT 50",
        "nifty_500": "NIFTY 500",
    }

    for key, val in indices.items():
        if not isinstance(val, dict):
            continue
        label  = _LABELS.get(key.lower(), key.upper())
        last   = val.get("last") or val.get("last_price") or val.get("value")
        pct    = val.get("pct_change") or val.get("change_pct")
        high   = val.get("day_high")
        low    = val.get("day_low")
        st     = _pct_style(pct)

        tbl.add_row(
            label,
            _fmt_price(last),
            Text(_fmt_pct(pct), style=st),
            _fmt_price(high),
            _fmt_price(low),
        )

    if tbl.row_count:
        as_of = data.get("as_of", "")
        _console.print()
        _console.print(Panel(
            tbl,
            title=f"[bold cyan]🏦  Market Overview{('  ·  ' + as_of) if as_of else ''}[/bold cyan]",
            border_style="dim cyan", padding=(0, 1),
        ))


# ─────────────────────────────────────────────────────────────────────────────
# Screener / Stage-2 results
# ─────────────────────────────────────────────────────────────────────────────

def render_screener_results(data: dict | list, title: str = "Screener Results") -> None:
    """Render screener / stage-2 / watchlist results as a coloured Rich table."""
    rows: list[dict] = []
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = (data.get("results") or data.get("stocks") or
                data.get("stage2_stocks") or data.get("watchlist") or
                data.get("screener_results") or [])

    if not rows:
        return

    tbl = Table(box=box.SIMPLE_HEAD, header_style="bold cyan", expand=True, padding=(0, 1))
    tbl.add_column("#", width=3, style="dim")
    tbl.add_column("Symbol", style="bold white", min_width=12)
    tbl.add_column("Stage", min_width=8, justify="center")
    tbl.add_column("Signal", min_width=14)
    tbl.add_column("Score", justify="right", min_width=7)
    tbl.add_column("RS", justify="right", min_width=6)
    tbl.add_column("RSI", justify="right", min_width=6)
    tbl.add_column("Sector", min_width=16)

    for i, r in enumerate(rows[:30], 1):
        sym    = r.get("symbol") or r.get("ticker", "—")
        stage  = str(r.get("stage") or r.get("stage_analysis") or "—")
        signal = str(r.get("trading_signal") or r.get("signal") or "—")
        score  = r.get("investment_score") or r.get("technical_score") or r.get("score")
        rs     = r.get("rs_pct") if r.get("rs_pct") is not None else (r.get("relative_strength") if r.get("relative_strength") is not None else r.get("rs"))
        rsi    = r.get("rsi")
        sector = (r.get("sector") or "")[:16]

        stage_t  = Text(stage,  style=_stage_style(stage))
        signal_t = Text(signal, style=_signal_style(signal))
        score_t  = Text(f"{score:.0f}" if score is not None else "—", style=_score_style(score))
        rs_t     = Text(f"{rs:+.1f}%" if rs is not None else "—",
                        style="green" if (rs or 0) > 0 else "red" if (rs or 0) < 0 else "yellow")
        rsi_t    = Text(f"{rsi:.0f}" if rsi is not None else "—",
                        style="green" if 50 < (rsi or 0) < 70 else "red" if (rsi or 0) < 30 else "yellow")

        tbl.add_row(str(i), sym, stage_t, signal_t, score_t, rs_t, rsi_t, sector)

    count = len(rows)
    _console.print()
    _console.print(Panel(
        tbl,
        title=f"[bold cyan]🔍  {title}  ·  {count} stock{'s' if count != 1 else ''}[/bold cyan]",
        border_style="dim cyan", padding=(0, 1),
    ))


# ─────────────────────────────────────────────────────────────────────────────
# Sector context
# ─────────────────────────────────────────────────────────────────────────────

def render_sector_context(data: dict) -> None:
    """Render sector breadth, leaders, and laggards."""
    if data.get("error"):
        return

    sector  = data.get("sector", "")
    leaders = data.get("top_leaders") or data.get("leaders") or []
    laggards = data.get("laggards") or []
    breadth  = data.get("breadth", {}) or {}

    if not leaders and not breadth:
        return

    tbl = Table(box=box.SIMPLE_HEAD, header_style="bold dim", expand=True, padding=(0, 1))
    tbl.add_column("Symbol", style="bold white", min_width=12)
    tbl.add_column("Stage", min_width=8, justify="center")
    tbl.add_column("Signal", min_width=14)
    tbl.add_column("Score", justify="right", min_width=7)
    tbl.add_column("RS", justify="right", min_width=6)
    tbl.add_column("Role", min_width=10)

    for s in leaders[:6]:
        sym   = s.get("symbol", "—")
        stage = str(s.get("stage") or "—")
        sig   = str(s.get("trading_signal") or s.get("signal") or "—")
        score = s.get("investment_score") or s.get("score")
        rs    = s.get("relative_strength") or s.get("rs")
        tbl.add_row(
            sym,
            Text(stage,  style=_stage_style(stage)),
            Text(sig,    style=_signal_style(sig)),
            Text(f"{score:.0f}" if score is not None else "—", style=_score_style(score)),
            Text(f"{rs:.2f}" if rs is not None else "—",
                 style="green" if (rs or 0) > 1 else "yellow"),
            Text("Leader", style="bold green"),
        )
    for s in laggards[:3]:
        sym   = s.get("symbol", "—")
        stage = str(s.get("stage") or "—")
        sig   = str(s.get("trading_signal") or s.get("signal") or "—")
        score = s.get("investment_score") or s.get("score")
        rs    = s.get("relative_strength") or s.get("rs")
        tbl.add_row(
            sym,
            Text(stage,  style=_stage_style(stage)),
            Text(sig,    style=_signal_style(sig)),
            Text(f"{score:.0f}" if score is not None else "—", style=_score_style(score)),
            Text(f"{rs:.2f}" if rs is not None else "—",
                 style="red" if (rs or 0) < 0.8 else "yellow"),
            Text("Laggard", style="red"),
        )

    if tbl.row_count:
        _console.print()
        _console.print(Panel(
            tbl,
            title=f"[bold cyan]🏭  {sector or 'Sector'} — Leaders & Laggards[/bold cyan]",
            border_style="dim cyan", padding=(0, 1),
        ))


# ─────────────────────────────────────────────────────────────────────────────
# 52-week extremes
# ─────────────────────────────────────────────────────────────────────────────

def render_52week_extremes(data: dict) -> None:
    """Render stocks near 52w highs or lows."""
    direction = data.get("direction", "high")
    stocks    = data.get("stocks") or data.get("results") or []
    if not stocks:
        return

    colour = "green" if direction == "high" else "red"
    icon   = "🚀" if direction == "high" else "📉"

    tbl = Table(box=box.SIMPLE_HEAD, header_style=f"bold {colour}", expand=True, padding=(0, 1))
    tbl.add_column("Symbol", style="bold white", min_width=12)
    tbl.add_column("Price", justify="right", min_width=10)
    tbl.add_column("52w Extreme", justify="right", min_width=12)
    tbl.add_column("% from Extreme", justify="right", min_width=14)
    tbl.add_column("Stage", min_width=8)

    for s in stocks[:15]:
        sym    = s.get("symbol", "—")
        price  = s.get("last_price")
        ex     = s.get("year_high") if direction == "high" else s.get("year_low")
        stage  = str(s.get("stage") or "—")
        pct_from = s.get("pct_from_high") or s.get("pct_from_low")

        pct_t = "—"
        pct_style = colour
        if pct_from is not None:
            pct_t = f"{pct_from:+.1f}%"
            pct_style = "green" if pct_from > -5 else "yellow" if pct_from > -15 else "red"

        tbl.add_row(
            sym,
            _fmt_price(price),
            _fmt_price(ex),
            Text(pct_t, style=pct_style),
            Text(stage, style=_stage_style(stage)),
        )

    _console.print()
    _console.print(Panel(
        tbl,
        title=f"[bold {colour}]{icon}  52-Week {'Highs' if direction == 'high' else 'Lows'}[/bold {colour}]",
        border_style=f"dim {colour}", padding=(0, 1),
    ))


# ─────────────────────────────────────────────────────────────────────────────
# Most active stocks
# ─────────────────────────────────────────────────────────────────────────────

def render_most_active(data: dict) -> None:
    """Render most active stocks by volume or value."""
    stocks = data.get("stocks") or data.get("results") or []
    if not stocks:
        return

    by  = data.get("by", "value")
    max_v = max((s.get("volume") or s.get("traded_value") or 0 for s in stocks), default=1) or 1

    tbl = Table(box=box.SIMPLE_HEAD, header_style="bold cyan", expand=True, padding=(0, 1))
    tbl.add_column("#", width=3, style="dim")
    tbl.add_column("Symbol", style="bold white", min_width=12)
    tbl.add_column("Price", justify="right", min_width=10)
    tbl.add_column("Chg %", justify="right", min_width=8)
    tbl.add_column(f"{'Value (Cr)' if by == 'value' else 'Volume'}", justify="right", min_width=12)
    tbl.add_column("Activity", min_width=20)

    for i, s in enumerate(stocks[:15], 1):
        sym   = s.get("symbol", "—")
        price = s.get("last_price")
        pct   = s.get("pct_change")
        v     = s.get("traded_value") if by == "value" else s.get("volume")
        v_str = f"{v/1e7:.1f}" if (v and by == "value") else (f"{v/1e5:.1f}L" if v else "—")
        bar   = _ascii_bar(v or 0, max_v, 18)

        tbl.add_row(
            str(i), sym,
            _fmt_price(price),
            Text(_fmt_pct(pct), style=_pct_style(pct)),
            v_str,
            Text(bar, style="cyan"),
        )

    _console.print()
    _console.print(Panel(
        tbl,
        title=f"[bold cyan]⚡  Most Active — by {'Value' if by == 'value' else 'Volume'}[/bold cyan]",
        border_style="dim cyan", padding=(0, 1),
    ))


# ─────────────────────────────────────────────────────────────────────────────
# Bulk / Block deals
# ─────────────────────────────────────────────────────────────────────────────

def render_bulk_deals(data: dict) -> None:
    """Render bulk/block deals table."""
    deals = data.get("deals") or data.get("bulk_deals") or data.get("block_deals") or []
    if not deals:
        return

    tbl = Table(box=box.SIMPLE_HEAD, header_style="bold magenta", expand=True, padding=(0, 1))
    tbl.add_column("Symbol", style="bold white", min_width=12)
    tbl.add_column("Client", min_width=22)
    tbl.add_column("B/S", min_width=5, justify="center")
    tbl.add_column("Qty", justify="right", min_width=10)
    tbl.add_column("Price ₹", justify="right", min_width=10)
    tbl.add_column("Value (Cr)", justify="right", min_width=10)

    for d in deals[:20]:
        sym    = d.get("symbol") or d.get("Symbol", "—")
        client = (d.get("client") or d.get("clientName") or "—")[:22]
        bs     = str(d.get("buySell") or d.get("trade_type") or "—").upper()
        qty    = d.get("quantity") or d.get("qty")
        price  = d.get("price") or d.get("tradePrice")
        val    = d.get("value_cr") or ((qty or 0) * (price or 0) / 1e7)

        bs_style = "green" if "B" in bs else "red" if "S" in bs else "yellow"
        qty_str  = f"{qty:,.0f}" if qty else "—"
        val_str  = f"{val:.1f}" if val else "—"

        tbl.add_row(
            sym, client,
            Text(bs, style=bs_style),
            qty_str,
            _fmt_price(price),
            val_str,
        )

    _console.print()
    _console.print(Panel(
        tbl,
        title="[bold magenta]🏛  Bulk / Block Deals[/bold magenta]",
        border_style="dim magenta", padding=(0, 1),
    ))


# ─────────────────────────────────────────────────────────────────────────────
# Trace dispatcher — called from _print_response()
# ─────────────────────────────────────────────────────────────────────────────

# Map tool_name → renderer function
_TOOL_RENDERERS: dict[str, Any] = {
    "get_top_gainers_losers":    render_gainers_losers,
    "get_eod_top_movers":        render_gainers_losers,
    "get_market_breadth":        render_market_breadth,
    "get_fii_dii_activity":      render_fii_dii,
    "get_live_market_overview":  render_market_overview,
    "get_52week_extremes":       render_52week_extremes,
    "get_most_active_stocks":    render_most_active,
    "get_bulk_block_deals":      render_bulk_deals,
    "run_screener_query":        lambda d: render_screener_results(d, "Screener Results"),
    "get_sector_context":        render_sector_context,
    "analyze_mtf":               lambda d: render_mtf_panel(d),
    "scan_mtf_aligned":          lambda d: render_mtf_scan(d),
}

# Tool names that we want to render as structured tables
_RENDER_TOOLS = set(_TOOL_RENDERERS.keys())


def render_trace_tables(trace: list[dict], plan: dict | None = None) -> None:
    """
    Scan a response trace for tool results and render each as a structured
    Rich table.  Called BEFORE the LLM narrative so tables appear at top.

    If a render plan is provided, only renders tools listed in plan["render_tools"]
    (when present); otherwise renders all recognised tools.

    Only renders tools whose output has structured data (not errors).
    Skips rendering if the tool result is just a string or has an 'error' key.
    """
    if not trace:
        return

    # If plan specifies which tools to render, respect it; otherwise render all
    allowed_tools = None
    if plan and plan.get("render_tools") is not None:
        allowed_tools = set(plan["render_tools"])

    rendered = set()
    for entry in trace:
        tool = entry.get("tool", "")
        if tool not in _RENDER_TOOLS:
            continue
        if allowed_tools is not None and tool not in allowed_tools:
            continue
        if tool in rendered:
            continue  # deduplicate — some tools called twice

        result = entry.get("result", {})
        if not isinstance(result, dict):
            continue
        if result.get("error"):
            continue

        fn = _TOOL_RENDERERS[tool]
        try:
            fn(result)
            rendered.add(tool)
        except Exception:
            logger.debug("render_trace_tables: renderer for %s raised", tool, exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Pre-render LLM planner
# ─────────────────────────────────────────────────────────────────────────────

# Simple in-process cache: content hash → plan dict (avoids redundant calls)
_plan_cache: dict[str, dict] = {}

_PLANNER_SYSTEM = """\
You are a financial terminal render planner for Agent Adda, an NSE market research terminal.
Given a short summary of an agent response and its data tools, return a JSON render plan that
tells the terminal exactly HOW to display the output.

Return ONLY valid JSON with these fields:

{
  "content_type": "<one of: stock_analysis | market_overview | gainers_losers | sector | screener | breadth | fii_dii | news | comparison | briefing | generic>",
  "sentiment": "<bullish | bearish | neutral | mixed>",
  "alert_level": "<none | info | warning | critical>",
  "summary_line": "<one crisp sentence ≤ 100 chars summarising the key takeaway>",
  "bold_symbols": ["<up to 5 NSE tickers that should be visually emphasised>"],
  "key_metrics": [
    {"label": "<metric name>", "value": "<display value>", "style": "<green | red | yellow | bold | dim>"}
  ],
  "render_tools": ["<tool names whose structured tables should be shown — subset of available tools>"],
  "render_mode": "<tables_first | narrative_first | tables_only | narrative_only>",
  "show_summary_strip": <true | false>,
  "narrative_first_for_types": ["<content_types where narrative should come before tables>"]
}

Rules:
- summary_line must be factual and specific (include ticker/index names and numbers when available).
- bold_symbols: only tickers mentioned in the response that are worth spotlighting.
- key_metrics: pick at most 4 of the most important numbers (price, % change, RSI, score, etc.).
- render_tools: only include tools whose structured output genuinely adds value.
  For a simple price quote, omit screener/breadth tables.
  For market overview queries, include get_live_market_overview and get_market_breadth.
  For gainers/losers, include get_top_gainers_losers.
- render_mode: use tables_first for data-heavy responses; narrative_first for analysis/opinion.
- show_summary_strip: true when there is a clear actionable insight worth highlighting at the top.
- alert_level: critical for breakouts/stops hit; warning for high-risk/regime-change; info otherwise.
"""

_SENTINEL_PLAN: dict = {
    "content_type":   "generic",
    "sentiment":      "neutral",
    "alert_level":    "none",
    "summary_line":   "",
    "bold_symbols":   [],
    "key_metrics":    [],
    "render_tools":   None,   # None = render all recognised tools
    "render_mode":    "tables_first",
    "show_summary_strip": False,
}


def _has_intraday_data_gap(answer: str, trace: list[dict]) -> bool:
    """Detect responses where current intraday data is absent or fallback-only."""
    text = (answer or "").lower()
    gap_markers = (
        "intraday data",
        "postgresql intraday",
        "intraday source unavailable",
        "intraday unavailable",
        "pre-market",
        "pre market",
        "market is closed",
        "fallback",
    )
    has_text_gap = (
        ("intraday" in text)
        and any(marker in text for marker in gap_markers)
        and any(marker in text for marker in ("unavailable", "not available", "pre-market", "pre market", "closed", "fallback"))
    )
    if has_text_gap:
        return True

    for entry in trace or []:
        result = entry.get("result")
        if not isinstance(result, dict):
            continue
        source = str(result.get("source") or result.get("data_source") or "").lower()
        error = str(result.get("error") or result.get("fallback_note") or result.get("reason") or "").lower()
        session = str(result.get("session") or "").lower()
        if "intraday" in source and ("unavailable" in error or "not available" in error):
            return True
        if "eod daily candles" in source and "intraday unavailable" in source:
            return True
        if session in {"pre-market", "holiday", "weekend"} and ("intraday" in error or "fallback" in source):
            return True
    return False


def _is_placeholder_metric(metric: dict) -> bool:
    value = str((metric or {}).get("value") or "").strip()
    if not value:
        return True
    compact = re.sub(r"[\s,._-]+", "", value).upper()
    return bool(re.fullmatch(r"(?:₹|RS\.?|INR|\$)?[WXYZABC]", compact))


def _has_placeholder_text(text: str) -> bool:
    compact = re.sub(r"[\s,._-]+", "", text or "").upper()
    return bool(re.search(r"(?:₹|RS\.?|INR|\$)?[WXYZABC](?:CRORES?|CR|BN|M|LAKH|L)?\b", compact))


def sanitize_render_plan(plan: dict, answer: str, trace: list[dict]) -> dict:
    """Apply deterministic safety guards after the optional LLM render planner."""
    guarded = dict(_SENTINEL_PLAN) | dict(plan or {})
    guarded["key_metrics"] = [
        metric
        for metric in (guarded.get("key_metrics") or [])
        if isinstance(metric, dict) and not _is_placeholder_metric(metric)
    ]
    if _has_placeholder_text(guarded.get("summary_line") or ""):
        guarded["summary_line"] = ""
    if guarded.get("show_summary_strip") and not guarded.get("summary_line") and not guarded.get("key_metrics"):
        guarded["show_summary_strip"] = False

    if _has_intraday_data_gap(answer, trace):
        guarded["show_summary_strip"] = False
        guarded["summary_line"] = ""
        guarded["key_metrics"] = []
        guarded["sentiment"] = "neutral"
        guarded["alert_level"] = "none"
    return guarded


def _build_planner_context(answer: str, trace: list[dict]) -> str:
    """Build a compact context string for the planner LLM."""
    parts: list[str] = []

    # Truncated answer preview
    parts.append(f"RESPONSE (first 600 chars):\n{answer[:600]}")

    # Compact tool result summaries
    tool_lines: list[str] = []
    for entry in trace:
        tool   = entry.get("tool", "")
        result = entry.get("result")
        if not isinstance(result, dict) or result.get("error"):
            continue

        if tool == "get_top_gainers_losers":
            g = [x.get("symbol") for x in result.get("gainers", [])[:3]]
            lo = [x.get("symbol") for x in result.get("losers",  [])[:3]]
            tool_lines.append(f"{tool}: gainers={g}, losers={lo}")

        elif tool == "get_live_market_overview":
            idxs = result.get("indices", {})
            if idxs:
                top = list(idxs.items())[:3]
                tool_lines.append(f"{tool}: {top}")

        elif tool == "get_market_breadth":
            ad = result.get("advance_decline", {})
            tool_lines.append(f"{tool}: adv={ad.get('advances')} dec={ad.get('declines')}")

        elif tool == "get_fii_dii_activity":
            tool_lines.append(f"{tool}: fii_net={result.get('fii_net')} dii_net={result.get('dii_net')}")

        elif tool == "run_screener_query":
            n = len(result.get("results") or result.get("stocks") or [])
            tool_lines.append(f"{tool}: {n} results")

        elif tool == "get_sector_context":
            tool_lines.append(f"{tool}: sector={result.get('sector')}")

        elif tool in ("get_symbol_snapshot", "get_live_quote"):
            sym   = result.get("symbol", "")
            price = result.get("last_price") or result.get("price")
            pct   = result.get("pct_change")
            stage = result.get("stage")
            tool_lines.append(f"{tool}: {sym} price={price} pct={pct} stage={stage}")

        else:
            # Generic — just note the tool ran
            tool_lines.append(tool)

    if tool_lines:
        parts.append("TOOLS CALLED:\n" + "\n".join(tool_lines))

    return "\n\n".join(parts)


def pre_render_plan(answer: str, trace: list[dict]) -> dict:
    """
    Make a fast gpt-4o-mini call to understand the content and produce a
    structured render plan.  Returns _SENTINEL_PLAN on any failure so the
    caller always gets a valid dict.

    Results are cached by content hash — repeated calls with the same answer
    are free.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return dict(_SENTINEL_PLAN)

    context = _build_planner_context(answer, trace)
    cache_key = hashlib.md5(context.encode()).hexdigest()
    if cache_key in _plan_cache:
        return sanitize_render_plan(_plan_cache[cache_key], answer, trace)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _PLANNER_SYSTEM},
                {"role": "user",   "content": context},
            ],
            max_tokens=400,
            temperature=0,
            timeout=8,          # hard cap — never block the terminal
        )
        raw = resp.choices[0].message.content or "{}"
        plan = json.loads(raw)
        # Ensure all expected keys exist (merge with sentinel)
        merged = sanitize_render_plan(plan, answer, trace)
        _plan_cache[cache_key] = merged
        return merged
    except Exception:
        return sanitize_render_plan(_SENTINEL_PLAN, answer, trace)


# ─────────────────────────────────────────────────────────────────────────────
# Apply render plan — summary strip + styled header colour
# ─────────────────────────────────────────────────────────────────────────────

_SENTIMENT_ICON = {
    "bullish": "🟢",
    "bearish": "🔴",
    "neutral": "⚪",
    "mixed":   "🟡",
}
_SENTIMENT_COLOUR = {
    "bullish": "bold green",
    "bearish": "bold red",
    "neutral": "white",
    "mixed":   "yellow",
}
_ALERT_COLOUR = {
    "none":     "dim cyan",
    "info":     "cyan",
    "warning":  "bold yellow",
    "critical": "bold red",
}


def apply_render_plan(plan: dict) -> str:
    """
    Render the plan's summary strip and return the recommended header rule
    colour string for use in the Agent Adda rule.

    Returns the rule style string (e.g. "bold green", "bold red") so the
    caller can colour the ── Agent Adda ── rule accordingly.
    """
    sentiment = plan.get("sentiment", "neutral")
    alert     = plan.get("alert_level", "none")
    show_strip = plan.get("show_summary_strip", False)
    summary   = plan.get("summary_line", "")
    metrics   = plan.get("key_metrics") or []
    bold_syms = plan.get("bold_symbols") or []

    # ── Summary strip ────────────────────────────────────────────────────────
    if show_strip and (summary or metrics):
        icon   = _SENTIMENT_ICON.get(sentiment, "⚪")
        colour = _SENTIMENT_COLOUR.get(sentiment, "white")
        alert_c = _ALERT_COLOUR.get(alert, "dim cyan")

        from rich.table import Table as _T
        strip = _T(box=None, padding=(0, 2), expand=True, show_header=False)
        strip.add_column("icon",    width=3)
        strip.add_column("summary", style=colour, ratio=2)
        strip.add_column("metrics", ratio=3)

        # Build metrics string
        metric_parts = []
        for m in metrics[:4]:
            label = m.get("label", "")
            val   = m.get("value", "")
            style = m.get("style", "white")
            metric_parts.append(f"[{style}]{label}: {val}[/{style}]")
        metric_str = "  ·  ".join(metric_parts)

        # Bold symbols in summary
        sum_display = summary
        for sym in bold_syms:
            sum_display = re.sub(
                rf"\b{re.escape(sym)}\b",
                f"[bold white]{sym}[/bold white]",
                sum_display,
            )

        strip.add_row(icon, sum_display, metric_str)

        _console.print(Panel(
            strip,
            border_style=alert_c,
            padding=(0, 1),
            expand=True,
        ))

    # Return header rule colour
    if alert in ("critical", "warning"):
        return _ALERT_COLOUR[alert]
    return _SENTIMENT_COLOUR.get(sentiment, "green dim")


def get_bold_symbols(plan: dict) -> list[str]:
    """Return the list of symbols the plan wants emphasised."""
    return plan.get("bold_symbols") or []


# ─────────────────────────────────────────────────────────────────────────────
# Multi-Timeframe (MTF) confluence
# ─────────────────────────────────────────────────────────────────────────────

_MTF_VERDICT_STYLE = {
    "BUY":   "bold green",
    "WATCH": "bold yellow",
    "AVOID": "bold magenta",
    "SELL":  "bold red",
}

_MTF_DIR_STYLE = {
    "bullish": "green",
    "bearish": "red",
    "neutral": "yellow",
}


def _mtf_dir_glyph(direction: str | None) -> Text:
    if direction == "bullish":
        return Text("▲ bullish", style="green")
    if direction == "bearish":
        return Text("▼ bearish", style="red")
    if direction == "neutral":
        return Text("• neutral", style="yellow")
    return Text("? n/a", style="dim")


def render_mtf_panel(data: dict) -> None:
    """Render a single-symbol /mtf analyze_mtf result as a rich panel."""
    if not data or data.get("error"):
        if data and data.get("error"):
            _console.print(f"[red]  ✗ /mtf failed:[/red] {data['error']}")
        return

    symbol  = data.get("symbol", "—")
    direction = data.get("direction", "—")
    score   = data.get("confluence_score", 0)
    verdict = data.get("verdict", "—")
    aligned = data.get("aligned_tfs") or []
    dissonant = data.get("dissonant_tfs") or []
    missing = data.get("missing_tfs") or []

    summary = Table(box=box.SIMPLE, expand=True, padding=(0, 1), show_header=False)
    summary.add_column("Field", style="bold cyan", no_wrap=True, width=14)
    summary.add_column("Value", overflow="fold")
    summary.add_row("Symbol", Text(symbol, style="bold white"))
    summary.add_row("Direction", _mtf_dir_glyph(direction))
    summary.add_row("Confluence", Text(f"{int(score)} / 100", style=_score_style(score)))
    summary.add_row("Verdict", Text(verdict, style=_MTF_VERDICT_STYLE.get(verdict, "bold")))
    if aligned:
        summary.add_row("Aligned TFs", Text(", ".join(aligned), style="green"))
    if dissonant:
        summary.add_row("Dissonant TFs", Text(", ".join(dissonant), style="yellow"))
    if missing:
        summary.add_row("Missing TFs", Text(", ".join(missing), style="dim"))

    detail = Table(box=box.SIMPLE_HEAD, header_style="bold dim", expand=True, padding=(0, 1))
    detail.add_column("TF", style="bold white", no_wrap=True, width=8)
    detail.add_column("Dir", no_wrap=True, width=10)
    detail.add_column("Close", justify="right")
    detail.add_column("RSI(14)", justify="right")
    detail.add_column("MACD", no_wrap=True, width=8)
    detail.add_column("EMA20", justify="right")
    detail.add_column("EMA50", justify="right")
    detail.add_column("SMA stack", no_wrap=True, width=12)

    for tf in data.get("timeframes") or []:
        reading = (data.get("readings") or {}).get(tf, {}) or {}
        if reading.get("status") != "ok":
            detail.add_row(tf, Text(reading.get("status", "?"), style="dim"), "—", "—", "—", "—", "—", "—")
            continue
        rsi = reading.get("rsi")
        rsi_style = "green" if (rsi or 0) > 55 else "red" if (rsi or 0) < 45 else "yellow"
        macd = reading.get("macd", "—")
        macd_style = _MTF_DIR_STYLE.get(macd, "white")
        if reading.get("sma_stack_bullish"):
            stack, stack_style = "bullish", "green"
        elif reading.get("sma_stack_bearish"):
            stack, stack_style = "bearish", "red"
        else:
            stack, stack_style = "mixed", "yellow"
        detail.add_row(
            tf,
            _mtf_dir_glyph(reading.get("direction")),
            f"{reading.get('close', 0):.2f}" if reading.get("close") is not None else "—",
            Text(f"{rsi:.1f}" if isinstance(rsi, (int, float)) else "—", style=rsi_style),
            Text(str(macd), style=macd_style),
            f"{reading.get('ema20', 0):.2f}" if reading.get("ema20") is not None else "—",
            f"{reading.get('ema50', 0):.2f}" if reading.get("ema50") is not None else "—",
            Text(stack, style=stack_style),
        )

    rationale = data.get("rationale") or ""
    if isinstance(rationale, list):
        rationale = "  ·  ".join(str(r) for r in rationale)
    body_renderables: list[Any] = [summary, detail]
    if rationale:
        body_renderables.append(Text(str(rationale), style="dim italic"))

    _console.print()
    _console.print(Panel(
        Columns(body_renderables, expand=True, equal=False) if False else _stack(body_renderables),
        title=f"[bold cyan]🧭  Multi-Timeframe Confluence — {symbol}[/bold cyan]",
        border_style=_MTF_VERDICT_STYLE.get(verdict, "dim cyan"),
        padding=(0, 1),
    ))


def _stack(items: list[Any]):
    """Vertically stack rich renderables inside a single Panel."""
    from rich.console import Group
    return Group(*items)


def render_mtf_scan(data: dict) -> None:
    """Render the universe scan_mtf_aligned result as a ranked panel."""
    if not data or data.get("error"):
        if data and data.get("error"):
            _console.print(f"[red]  ✗ /mtf scan failed:[/red] {data['error']}")
        return

    direction = data.get("direction", "—")
    min_score = data.get("min_score", "—")
    timeframes = data.get("timeframes") or []
    universe_size = data.get("universe_size", 0)
    matches_total = data.get("matches_total", 0)
    top = data.get("top") or []

    header = Table(box=box.SIMPLE, expand=True, padding=(0, 1), show_header=False)
    header.add_column("Field", style="bold cyan", no_wrap=True, width=14)
    header.add_column("Value", overflow="fold")
    header.add_row("Direction", _mtf_dir_glyph(direction))
    header.add_row("Min score", Text(str(min_score), style="bold white"))
    header.add_row("Timeframes", Text(", ".join(timeframes), style="white"))
    header.add_row("Universe", Text(f"{universe_size} symbols", style="white"))
    header.add_row("Matches", Text(f"{matches_total} ≥ {min_score}", style="bold yellow"))

    tbl = Table(box=box.SIMPLE_HEAD, header_style="bold dim", expand=True, padding=(0, 1))
    tbl.add_column("#", width=3, style="dim", justify="right")
    tbl.add_column("Symbol", style="bold white", no_wrap=True, min_width=12)
    tbl.add_column("Score", justify="right", width=7)
    tbl.add_column("Verdict", no_wrap=True, width=8)
    tbl.add_column("Aligned TFs", overflow="fold")
    tbl.add_column("Dissonant", overflow="fold")
    tbl.add_column("Missing", overflow="fold")

    if not top:
        tbl.add_row("—", Text("(no symbols met threshold)", style="dim"), "—", "—", "—", "—", "—")
    for i, row in enumerate(top, start=1):
        verdict = row.get("verdict", "—")
        score = row.get("confluence_score", 0)
        aligned_tfs = row.get("aligned_tfs") or []
        dissonant_tfs = row.get("dissonant_tfs") or []
        missing_tfs = row.get("missing_tfs") or []
        tbl.add_row(
            str(i),
            row.get("symbol", "—"),
            Text(str(int(score)), style=_score_style(score)),
            Text(verdict, style=_MTF_VERDICT_STYLE.get(verdict, "white")),
            Text(", ".join(aligned_tfs), style="green") if aligned_tfs else Text("—", style="dim"),
            Text(", ".join(dissonant_tfs), style="yellow") if dissonant_tfs else Text("—", style="dim"),
            Text(", ".join(missing_tfs), style="dim") if missing_tfs else Text("—", style="dim"),
        )

    _console.print()
    _console.print(Panel(
        _stack([header, tbl]),
        title=f"[bold cyan]🧭  MTF Scan — {direction.upper()} confluence[/bold cyan]",
        border_style="dim cyan",
        padding=(0, 1),
    ))


def write_mtf_report(data: dict, out_dir: str = "reports/mtf") -> str:
    """Persist an MTF result as a markdown report and return the absolute path.

    Accepts either a single-symbol analyze_mtf result or a scan_mtf_aligned result.
    """
    import os
    from datetime import datetime as _dt
    os.makedirs(out_dir, exist_ok=True)
    ts = _dt.now().strftime("%Y%m%d_%H%M%S")

    lines: list[str] = []
    if "top" in data and "direction" in data and "universe_size" in data:
        slug = f"mtf_scan_{data.get('direction','x')}_{ts}"
        lines.append(f"# MTF Scan — {data.get('direction','—').upper()} confluence")
        lines.append("")
        lines.append(f"- Generated: {_dt.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"- Direction: **{data.get('direction','—')}**  ·  Min score: **{data.get('min_score','—')}**")
        lines.append(f"- Timeframes: `{', '.join(data.get('timeframes') or [])}`")
        lines.append(f"- Universe: {data.get('universe_size',0)} symbols  ·  Matches ≥ threshold: {data.get('matches_total',0)}")
        lines.append("")
        lines.append("| # | Symbol | Score | Verdict | Aligned TFs | Dissonant | Missing |")
        lines.append("|---|--------|------:|---------|-------------|-----------|---------|")
        for i, row in enumerate(data.get("top") or [], start=1):
            lines.append(
                f"| {i} | **{row.get('symbol','—')}** | {int(row.get('confluence_score',0))} | "
                f"{row.get('verdict','—')} | {', '.join(row.get('aligned_tfs') or []) or '—'} | "
                f"{', '.join(row.get('dissonant_tfs') or []) or '—'} | "
                f"{', '.join(row.get('missing_tfs') or []) or '—'} |"
            )
    else:
        symbol = data.get("symbol", "SYMBOL")
        slug = f"mtf_{symbol}_{ts}"
        lines.append(f"# Multi-Timeframe Confluence — {symbol}")
        lines.append("")
        lines.append(f"- Generated: {_dt.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"- Direction: **{data.get('direction','—')}**")
        lines.append(f"- Confluence score: **{int(data.get('confluence_score',0))} / 100**")
        lines.append(f"- Verdict: **{data.get('verdict','—')}**")
        if data.get("aligned_tfs"):
            lines.append(f"- Aligned timeframes: {', '.join(data['aligned_tfs'])}")
        if data.get("dissonant_tfs"):
            lines.append(f"- Dissonant timeframes: {', '.join(data['dissonant_tfs'])}")
        if data.get("missing_tfs"):
            lines.append(f"- Missing timeframes: {', '.join(data['missing_tfs'])}")
        lines.append("")
        lines.append("| TF | Direction | Close | RSI(14) | MACD | EMA20 | EMA50 | SMA stack |")
        lines.append("|----|-----------|------:|--------:|------|------:|------:|-----------|")
        for tf in data.get("timeframes") or []:
            r = (data.get("readings") or {}).get(tf, {}) or {}
            if r.get("status") != "ok":
                lines.append(f"| {tf} | _{r.get('status','?')}_ | — | — | — | — | — | — |")
                continue
            lines.append(
                f"| {tf} | {r.get('direction','—')} | "
                f"{r.get('close','—')} | {r.get('rsi','—')} | {r.get('macd','—')} | "
                f"{r.get('ema20','—')} | {r.get('ema50','—')} | {r.get('sma_stack','—')} |"
            )
        if data.get("rationale"):
            lines.append("")
            _rat = data["rationale"]
            if isinstance(_rat, list):
                _rat = "  ·  ".join(str(r) for r in _rat)
            lines.append(f"> {_rat}")

    out_path = os.path.abspath(os.path.join(out_dir, f"{slug}.md"))
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return out_path
