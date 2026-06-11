#!/usr/bin/env python3
"""
Email Daily NSE Reports — PostgreSQL-backed
============================================
Sends the daily NSE sector-rotation + Stage 2 tracker HTML reports as a
formatted HTML email via Microsoft Outlook on macOS (AppleScript).

All dynamic content (Stage 2 counts, new/exit symbols, top BUY signals,
FII/DII flows, macro indicators, sector tailwinds) is sourced directly
from PostgreSQL — no SQLite, no CSV dependencies.

Usage:
  python email_daily_reports.py                # open draft for review
  python email_daily_reports.py --send         # auto-send via Outlook
  python email_daily_reports.py --dry-run      # render body to stdout only
  python email_daily_reports.py --date 2026-05-18   # explicit snapshot date

Recipients are configured in TO_RECIPIENTS / BCC_RECIPIENTS below.
"""
from __future__ import annotations

# ── Changed: PostgreSQL-only data sources (replaces SQLite + CSV reads) ──
import argparse
import os
import subprocess
import sys
import textwrap
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.extras

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent
PG_DSN = os.environ.get("AGENT_ADDA_PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"

# Recipients per current distribution
TO_RECIPIENTS = [
    ("pgorai",            "pgorai@deloitte.com"),
]
# Changed 2026-05-19: BCC distribution re-enabled per user — full team list.
BCC_RECIPIENTS: list[tuple[str, str]] = [
    ("Khan, Hina Tabassum",    "hikhan@deloitte.com"),
    ("Binjola, Maheshanand",   "mbinjola@deloitte.com"),
    ("Bhatia, Hitesh",         "hibhatia@deloitte.com"),
    ("Chouhan, Kapil",         "kchouhan@deloitte.com"),
    ("Tangirala, Viswa Phani", "vitangirala@deloitte.com"),
    ("Sen, Avirup",            "avsen@deloitte.com"),
    ("Mahale, Ashish",         "amahale@deloitte.com"),
    ("Gorai, Sandeep",         "sgorai@deloitte.com"),
]

REPORTS_DIR        = ROOT / "reports"
SECTOR_LATEST_HTML = REPORTS_DIR / "latest" / "sector_rotation.html"
STAGE2_DIR         = REPORTS_DIR / "sector_rotation"


# ─────────────────────────────────────────────────────────────────────────────
# PostgreSQL fetchers
# ─────────────────────────────────────────────────────────────────────────────

def _conn():
    return psycopg2.connect(PG_DSN)


def fetch_latest_date(forced: Optional[str] = None) -> date:
    """Resolve the snapshot date — explicit override or latest in PG."""
    if forced:
        return datetime.strptime(forced, "%Y-%m-%d").date()
    with _conn() as c, c.cursor() as cur:
        cur.execute("SELECT MAX(snapshot_date) FROM scores.stage_snapshots")
        row = cur.fetchone()
        if not row or not row[0]:
            raise RuntimeError("scores.stage_snapshots is empty — run daily_refresh.py first")
        return row[0]


def fetch_stage2_summary(d: date) -> dict:
    """Stage 2 universe size + previous comparison date."""
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM scores.stage_snapshots "
            "WHERE snapshot_date=%s AND stage='STAGE_2'",
            (d,),
        )
        s2_count = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM scores.stage_snapshots WHERE snapshot_date=%s",
            (d,),
        )
        total = cur.fetchone()[0]

        # Most recent change_date is the day vs prior session
        cur.execute(
            "SELECT compare_date FROM scores.stage_changes "
            "WHERE change_date=%s ORDER BY compare_date DESC LIMIT 1",
            (d,),
        )
        row = cur.fetchone()
        compare_date = row[0] if row else None

        # Changed 2026-05-19: stage_changed boolean is unreliable in current loader output.
        # Count actual change_type events (NEW/EXIT/UPGRADE/DOWNGRADE) instead.
        cur.execute(
            "SELECT COUNT(*) FROM scores.stage_changes "
            "WHERE change_date=%s AND compare_date=%s "
            "AND change_type IS NOT NULL AND change_type <> 'UNCHANGED'",
            (d, compare_date),
        )
        total_changes = cur.fetchone()[0] if compare_date else 0

    return {
        "snapshot_date": d,
        "compare_date":  compare_date,
        "stage2_count":  s2_count,
        "total":         total,
        "total_changes": total_changes,
    }


def fetch_new_exit_stage2(d: date, compare_date: Optional[date]) -> tuple[list, list]:
    """Return (new_entrants, exits) as lists of (symbol, stage_now)."""
    if not compare_date:
        return [], []
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT symbol, stage_now FROM scores.stage_changes "
            "WHERE change_date=%s AND compare_date=%s "
            "AND change_type IN ('NEW_STAGE2','ENTRY') ORDER BY symbol",
            (d, compare_date),
        )
        new_entrants = [(r[0], r[1]) for r in cur.fetchall()]

        cur.execute(
            "SELECT symbol, stage_now FROM scores.stage_changes "
            "WHERE change_date=%s AND compare_date=%s "
            "AND change_type IN ('EXIT_STAGE2','EXIT') ORDER BY symbol",
            (d, compare_date),
        )
        exits = [(r[0], r[1]) for r in cur.fetchall()]
    return new_entrants, exits


def fetch_top_buy_signals(d: date, limit: int = 8) -> list[dict]:
    """Top technical BUY signals from scores.daily_scores for the snapshot date."""
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT symbol, current_price, change_1d_pct, change_1w_pct,
                       change_1m_pct, rsi, technical_score
                  FROM scores.daily_scores
                 WHERE score_date=%s AND trading_signal='BUY'
                 ORDER BY technical_score DESC NULLS LAST
                 LIMIT %s
                """,
                (d, limit),
            )
            return [dict(r) for r in cur.fetchall()]


# ── Added 2026-05-19: top gainers/losers from scores.daily_scores ──
def fetch_top_movers(d: date, limit: int = 8) -> tuple[list[dict], list[dict]]:
    """Return (gainers, losers) ranked by 1-day price change for the snapshot date."""
    base_sql = """
        SELECT symbol, current_price, change_1d_pct, change_1w_pct, change_1m_pct,
               rsi, technical_score, trading_signal
          FROM scores.daily_scores
         WHERE score_date=%s
           AND current_price IS NOT NULL
           AND change_1d_pct IS NOT NULL
         ORDER BY change_1d_pct {dir} NULLS LAST
         LIMIT %s
    """
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(base_sql.format(dir="DESC"), (d, limit))
            gainers = [dict(r) for r in cur.fetchall()]
            cur.execute(base_sql.format(dir="ASC"), (d, limit))
            losers = [dict(r) for r in cur.fetchall()]
    return gainers, losers


# ── Added 2026-05-19: parse Market Brief narrative from generated md report ──
def fetch_market_brief() -> dict:
    """Parse the 4 brief sections from reports/latest/sector_rotation.md.

    Returns dict with keys: market_read, risk_posture, where_to_focus, view_change.
    Empty strings if the file is missing or a section is absent.
    """
    import re
    md_path = REPORTS_DIR / "latest" / "sector_rotation.md"
    out = {"market_read": "", "risk_posture": "", "where_to_focus": "", "view_change": ""}
    if not md_path.exists():
        return out
    text = md_path.read_text(encoding="utf-8")
    # Each brief section is **Label:** <prose paragraph> on a single line.
    patterns = {
        "market_read":    r"\*\*Market Read:\*\*\s*(.+)",
        "risk_posture":   r"\*\*Risk Posture:\*\*\s*(.+)",
        "where_to_focus": r"\*\*Where to Focus:\*\*\s*(.+)",
        "view_change":    r"\*\*What Would Change(?: the View)?:\*\*\s*(.+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text)
        if m:
            out[key] = m.group(1).strip()
    return out


def fetch_signal_mix(d: date) -> dict:
    """Count of trading signals for the snapshot date."""
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT trading_signal, COUNT(*) FROM scores.daily_scores "
            "WHERE score_date=%s GROUP BY trading_signal",
            (d,),
        )
        return {k: v for k, v in cur.fetchall() if k}


def fetch_fii_dii(d: date) -> Optional[dict]:
    """Latest FII/DII flow row at or before the snapshot date."""
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM signals.fii_dii_flows "
                "WHERE trade_date<=%s ORDER BY trade_date DESC LIMIT 1",
                (d,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def fetch_macro_indicators(d: date) -> dict:
    """Key macro indicators for the snapshot date (or latest available)."""
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (indicator)
                       indicator, latest_value, trend, momentum_1m_pct, signal_score
                  FROM macro.indicators
                 WHERE snapshot_date<=%s
                 ORDER BY indicator, snapshot_date DESC
                """,
                (d,),
            )
            return {r["indicator"]: dict(r) for r in cur.fetchall()}


def fetch_sector_tailwinds(d: date, top_n: int = 5) -> tuple[list, list]:
    """Top and bottom sector tailwinds. Returns (top, bottom) lists of dicts."""
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT sector_name, macro_tailwind, macro_detail
                  FROM macro.sector_tailwinds
                 WHERE snapshot_date=(
                       SELECT MAX(snapshot_date) FROM macro.sector_tailwinds
                       WHERE snapshot_date<=%s)
                """,
                (d,),
            )
            rows = [dict(r) for r in cur.fetchall()]
    # macro_tailwind is TEXT in schema but holds numeric — cast safely
    def _f(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return 0.0
    rows = [{**r, "_val": _f(r["macro_tailwind"])} for r in rows]
    top    = sorted(rows, key=lambda r: r["_val"], reverse=True)[:top_n]
    bottom = sorted(rows, key=lambda r: r["_val"])[:3]
    return top, bottom


def fetch_regime(d: date) -> Optional[dict]:
    """Latest regime entry at or before snapshot date."""
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM signals.regime_history "
                "WHERE trade_date<=%s ORDER BY trade_date DESC LIMIT 1",
                (d,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


# ─────────────────────────────────────────────────────────────────────────────
# Attachment discovery
# ─────────────────────────────────────────────────────────────────────────────

def locate_attachments(d: date) -> tuple[Path, Path, Path]:
    """Find today's sector rotation HTML, Stage 2 tracker HTML, and TradingView watchlist."""
    sector = SECTOR_LATEST_HTML
    if not sector.exists():
        # Fallback to dated file
        sector = REPORTS_DIR / "sector_rotation" / f"{d.year}" / f"Sector_Rotation_Report_{d.strftime('%Y%m%d')}.html"

    stage2 = STAGE2_DIR / f"stage2_tracker_{d.isoformat()}.html"
    if not stage2.exists():
        # Use the newest available stage2 tracker file
        candidates = sorted(STAGE2_DIR.glob("stage2_tracker_*.html"), reverse=True)
        if candidates:
            stage2 = candidates[0]
    tradingview = REPORTS_DIR / "latest" / "stage2_buy_tradingview.txt"
    if not tradingview.exists():
        candidates = sorted(STAGE2_DIR.glob("stage2_buy_tradingview_*.txt"), reverse=True)
        if candidates:
            tradingview = candidates[0]
    return sector, stage2, tradingview


# ─────────────────────────────────────────────────────────────────────────────
# HTML body rendering
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_inr(x) -> str:
    if x is None:
        return "—"
    try:
        v = float(x)
        sign = "+" if v >= 0 else "−"
        return f"{sign}₹{abs(v):,.0f} Cr"
    except (TypeError, ValueError):
        return "—"


# ── Changed 2026-05-19: rewrite render_body for Outlook-friendly layout ──
# Key fixes vs prior version:
#   1. All structural elements are <table> (Outlook for Mac strips <div> styles).
#   2. Every cell carries inline styles (font, padding, color) — no class/CSS reliance.
#   3. Sections with no PG data are hidden gracefully instead of showing 0.00 placeholders.
#   4. Section headers are full-width table rows with solid background.
#   5. Consistent typography (Segoe UI / Helvetica fallback), 14px body, 12px small.

FONT_STACK = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
COLOR_PRIMARY = "#0b5394"
COLOR_GREEN   = "#15803d"
COLOR_RED     = "#c0392b"
COLOR_MUTED   = "#666666"
COLOR_BORDER  = "#dddddd"
COLOR_HEADER_BG = "#f3f4f6"


def _section_header(title: str) -> str:
    """Render a full-width blue section header that survives Outlook rendering."""
    return (
        f'<tr><td style="background:{COLOR_PRIMARY}; color:#ffffff; '
        f'padding:8px 12px; font-family:{FONT_STACK}; font-size:14px; '
        f'font-weight:bold; border-radius:4px;">{title}</td></tr>'
        f'<tr><td style="height:8px; line-height:8px; font-size:0;">&nbsp;</td></tr>'
    )


def _row(label: str, value: str) -> str:
    """Two-column key-value row for the Market Context table."""
    return (
        f'<tr>'
        f'<td style="padding:5px 14px 5px 0; font-family:{FONT_STACK}; '
        f'font-size:13px; color:#222;"><b>{label}</b></td>'
        f'<td style="padding:5px 0; font-family:{FONT_STACK}; font-size:13px; color:#222;">{value}</td>'
        f'</tr>'
    )


def render_body(data: dict) -> str:
    d            = data["snapshot_date"]
    cmp_d        = data["compare_date"]
    s2           = data["stage2_count"]
    total_chg    = data["total_changes"]
    new_ent      = data["new_entrants"]
    exits        = data["exits"]
    top_buy      = data["top_buy"]
    sig_mix      = data["signal_mix"]
    fii_dii      = data["fii_dii"] or {}
    macro        = data["macro"]
    tw_top       = data["tailwinds_top"]
    tw_bot       = data["tailwinds_bottom"]
    regime       = data["regime"] or {}
    # Added 2026-05-19: Market Brief + top movers
    brief        = data.get("market_brief") or {}
    gainers      = data.get("gainers") or []
    losers       = data.get("losers") or []

    nice_date    = d.strftime("%-d %b %Y") if hasattr(d, "strftime") else str(d)
    weekday      = d.strftime("%A") if hasattr(d, "strftime") else ""
    cmp_str      = cmp_d.strftime("%-d %b") if cmp_d else "previous session"

    nifty   = macro.get("Nifty 50",  {})
    vix     = macro.get("India VIX", {})
    usd_inr = macro.get("USD/INR",   {})

    # ── Market Context rows (hide rows with no PG data) ───────────────────
    ctx_rows = []
    def _macro_row(name, m, suffix=""):
        v = m.get("latest_value")
        if v in (None, 0, 0.0):
            return  # skip empty
        mom = m.get("momentum_1m_pct")
        trend = m.get("trend") or ""
        mom_str = f" ({float(mom):+.2f}% 1M{', trend ' + trend if trend else ''})" if mom is not None else ""
        ctx_rows.append(_row(name, f"{float(v):,.2f}{suffix}<span style='color:{COLOR_MUTED};'>{mom_str}</span>"))

    _macro_row("Nifty 50",  nifty)
    _macro_row("India VIX", vix)
    _macro_row("USD/INR",   usd_inr)

    if fii_dii.get("fii_net_today") is not None:
        ctx_rows.append(_row("FII flow",
            f"{_fmt_inr(fii_dii.get('fii_net_today'))} today &nbsp;|&nbsp; "
            f"5-day net {_fmt_inr(fii_dii.get('fii_net_5d'))}"))
    if fii_dii.get("dii_net_today") is not None:
        ctx_rows.append(_row("DII flow",
            f"{_fmt_inr(fii_dii.get('dii_net_today'))} today &nbsp;|&nbsp; "
            f"5-day net {_fmt_inr(fii_dii.get('dii_net_5d'))}"))
    if fii_dii.get("flow_signal"):
        ctx_rows.append(_row("Flow signal", str(fii_dii["flow_signal"])))

    regime_label = regime.get("regime")
    if regime_label:
        regime_conf = regime.get("confidence")
        conf_str = (f" <span style='color:{COLOR_MUTED};'>(confidence {float(regime_conf):.0f}%)</span>"
                    if regime_conf is not None else "")
        ctx_rows.append(_row("Market regime", f"<b>{regime_label}</b>{conf_str}"))

    market_ctx_html = ""
    if ctx_rows:
        market_ctx_html = (
            _section_header(f"📊 Market Context — {nice_date}")
            + '<tr><td style="padding:0 0 12px 0;">'
            + '<table cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;">'
            + "\n".join(ctx_rows)
            + '</table></td></tr>'
        )

    # ── Tailwinds / Headwinds (hide if no data) ───────────────────────────
    tw_html = ""
    if tw_top or tw_bot:
        def _bullets(items, color="#222"):
            return "\n".join(
                f'<li style="padding:2px 0; font-family:{FONT_STACK}; font-size:13px;">'
                f'{r["sector_name"]} &nbsp; <b style="color:{color};">{r["_val"]:+.2f}</b></li>'
                for r in items
            )
        tw_html = (
            f'<tr><td style="padding:6px 0 4px; font-family:{FONT_STACK}; '
            f'font-size:14px; font-weight:bold;">Sector Tailwinds (top {len(tw_top)})</td></tr>'
            f'<tr><td><ul style="margin:0 0 8px 22px; padding:0;">{_bullets(tw_top, COLOR_GREEN)}</ul></td></tr>'
            f'<tr><td style="padding:6px 0 4px; font-family:{FONT_STACK}; '
            f'font-size:14px; font-weight:bold;">Sector Headwinds</td></tr>'
            f'<tr><td><ul style="margin:0 0 12px 22px; padding:0;">{_bullets(tw_bot, COLOR_RED)}</ul></td></tr>'
        )

    # ── Stage 2 lists ─────────────────────────────────────────────────────
    new_list = ", ".join(s for s, _ in new_ent) if new_ent else "—"
    exits_s1  = [s for s, st in exits if st == "STAGE_1"]
    exits_unk = [s for s, st in exits if (st or "").upper() in ("UNKNOWN", "")]
    exits_s1_str  = ", ".join(exits_s1)  if exits_s1  else "—"
    exits_unk_str = ", ".join(exits_unk) if exits_unk else "—"

    # ── Signal mix ────────────────────────────────────────────────────────
    total = sum(sig_mix.values()) or 1
    sig_mix_str = " &nbsp;|&nbsp; ".join(
        f"<b>{k}</b> {v} <span style='color:{COLOR_MUTED};'>({v/total*100:.1f}%)</span>"
        for k, v in sorted(sig_mix.items(), key=lambda kv: -kv[1])
    )

    # ── Top BUY table (proper cell-level inline styles) ───────────────────
    def _td(content, align="left", bold=False, color="#222"):
        weight = "bold" if bold else "normal"
        return (
            f'<td align="{align}" style="padding:6px 10px; border-bottom:1px solid {COLOR_BORDER}; '
            f'font-family:{FONT_STACK}; font-size:13px; font-weight:{weight}; color:{color};">{content}</td>'
        )

    def _chg_color(v):
        try:
            return COLOR_GREEN if float(v) >= 0 else COLOR_RED
        except (TypeError, ValueError):
            return COLOR_MUTED

    buy_rows_html = "\n".join(
        "<tr>"
        + _td(r['symbol'], bold=True)
        + _td(f"{float(r['current_price'] or 0):,.2f}", align="right")
        + _td(f"{float(r['change_1d_pct'] or 0):+.2f}%", align="right", color=_chg_color(r['change_1d_pct']))
        + _td(f"{float(r['change_1m_pct'] or 0):+.2f}%", align="right", color=_chg_color(r['change_1m_pct']))
        + _td(f"{float(r['rsi'] or 0):.1f}", align="right")
        + _td(f"{float(r['technical_score'] or 0):.1f}", align="right", bold=True)
        + "</tr>"
        for r in top_buy
    ) or f'<tr><td colspan="6" style="padding:8px; font-family:{FONT_STACK}; font-size:13px; color:{COLOR_MUTED};">No BUY signals available</td></tr>'

    def _th(label, align="left"):
        return (
            f'<th align="{align}" style="background:{COLOR_HEADER_BG}; padding:8px 10px; '
            f'border-bottom:2px solid {COLOR_BORDER}; font-family:{FONT_STACK}; '
            f'font-size:12px; font-weight:bold; color:#333; text-transform:uppercase; '
            f'letter-spacing:0.4px;">{label}</th>'
        )

    # ── Added 2026-05-19: Market Brief block (4 narrative sub-sections) ───
    brief_html = ""
    brief_items = [
        ("Market Read",      brief.get("market_read"),    "#1d4ed8"),
        ("Risk Posture",     brief.get("risk_posture"),   "#b45309"),
        ("Where to Focus",   brief.get("where_to_focus"), COLOR_GREEN),
        ("What Would Change the View", brief.get("view_change"), COLOR_RED),
    ]
    brief_cards = "\n".join(
        f'<tr><td style="padding:8px 0;">'
        f'<table cellspacing="0" cellpadding="0" border="0" width="100%" style="border-collapse:collapse;">'
        f'<tr><td style="background:{COLOR_HEADER_BG}; border-left:4px solid {col}; '
        f'padding:10px 14px; font-family:{FONT_STACK}; font-size:13px; line-height:1.6; color:#222;">'
        f'<div style="font-weight:bold; color:{col}; font-size:13px; margin-bottom:4px; '
        f'text-transform:uppercase; letter-spacing:0.4px;">{label}</div>{text}</td></tr>'
        f'</table></td></tr>'
        for (label, text, col) in brief_items if text
    )
    if brief_cards:
        brief_html = _section_header("📰 Market Brief") + brief_cards

    # ── Added 2026-05-19: Top Gainers / Losers tables ─────────────────────
    def _movers_rows(rows):
        if not rows:
            return (f'<tr><td colspan="5" style="padding:8px; font-family:{FONT_STACK}; '
                    f'font-size:13px; color:{COLOR_MUTED};">No data</td></tr>')
        return "\n".join(
            "<tr>"
            + _td(r['symbol'], bold=True)
            + _td(f"{float(r['current_price'] or 0):,.2f}", align="right")
            + _td(f"{float(r['change_1d_pct'] or 0):+.2f}%", align="right",
                  color=_chg_color(r['change_1d_pct']), bold=True)
            + _td(f"{float(r['change_1m_pct'] or 0):+.2f}%", align="right",
                  color=_chg_color(r['change_1m_pct']))
            + _td(r.get('trading_signal') or '—', align="right")
            + "</tr>"
            for r in rows
        )

    gainers_html = _movers_rows(gainers)
    losers_html  = _movers_rows(losers)

    movers_block = f"""
{_section_header("🚀 Top Gainers & Losers (1-day)")}
<tr><td style="padding:0 0 14px;">
<table cellspacing="0" cellpadding="0" border="0" width="100%" style="border-collapse:collapse;">
<tr>
<td valign="top" width="50%" style="padding-right:8px;">
<div style="font-family:{FONT_STACK}; font-size:13px; font-weight:bold; color:{COLOR_GREEN}; padding:4px 0;">▲ Top {len(gainers)} Gainers</div>
<table cellspacing="0" cellpadding="0" border="0" width="100%" style="border-collapse:collapse; border:1px solid {COLOR_BORDER};">
<tr>{_th("Symbol")}{_th("Price (₹)", "right")}{_th("1D", "right")}{_th("1M", "right")}{_th("Signal", "right")}</tr>
{gainers_html}
</table>
</td>
<td valign="top" width="50%" style="padding-left:8px;">
<div style="font-family:{FONT_STACK}; font-size:13px; font-weight:bold; color:{COLOR_RED}; padding:4px 0;">▼ Top {len(losers)} Losers</div>
<table cellspacing="0" cellpadding="0" border="0" width="100%" style="border-collapse:collapse; border:1px solid {COLOR_BORDER};">
<tr>{_th("Symbol")}{_th("Price (₹)", "right")}{_th("1D", "right")}{_th("1M", "right")}{_th("Signal", "right")}</tr>
{losers_html}
</table>
</td>
</tr>
</table>
</td></tr>
"""

    # ── Final assembly — outer table for Outlook compatibility ────────────
    return f"""<table cellspacing="0" cellpadding="0" border="0" width="100%" style="background:#ffffff;">
<tr><td style="padding:18px 24px; font-family:{FONT_STACK}; color:#222;">

<table cellspacing="0" cellpadding="0" border="0" width="100%" style="max-width:760px; border-collapse:collapse;">

<tr><td style="padding:0 0 12px; font-family:{FONT_STACK}; font-size:14px; line-height:1.55;">
Hello,
</td></tr>

<tr><td style="padding:0 0 16px; font-family:{FONT_STACK}; font-size:14px; line-height:1.6;">
Please find attached the daily NSE market analysis reports for the trading session ending
<b>{nice_date} ({weekday})</b>. These are generated end-to-end by the
<b>Agent Adda daily refresh pipeline</b> — NSE bhavcopy download → comprehensive universe
analysis (PostgreSQL-backed) → sector rotation engine → Stage 2 (Weinstein) tracker.
</td></tr>

<tr><td>
<table cellspacing="0" cellpadding="0" border="0" width="100%" style="border-collapse:collapse; margin:8px 0 12px;">
<tr><td style="background:{COLOR_HEADER_BG}; border-left:4px solid {COLOR_PRIMARY}; padding:10px 14px; font-family:{FONT_STACK}; font-size:13px;">
<b>Headlines</b> &nbsp;·&nbsp;
Stage 2 universe: <b>{s2}</b> stocks &nbsp;·&nbsp;
<span style="color:{COLOR_GREEN};">▲ {len(new_ent)} new</span> &nbsp;·&nbsp;
<span style="color:{COLOR_RED};">▼ {len(exits)} exits</span> &nbsp;·&nbsp;
{total_chg} total stage changes vs {cmp_str}
</td></tr>
</table>
</td></tr>

{brief_html}

{market_ctx_html}

{tw_html}

{_section_header("📎 Attachment 1 — Sector Rotation Report")}
<tr><td style="padding:0 0 14px; font-family:{FONT_STACK}; font-size:13px; line-height:1.55;">
<code style="background:{COLOR_HEADER_BG}; padding:2px 6px; border-radius:3px;">sector_rotation.html</code>
— end-to-end sector rotation analysis covering all sectors with stage breakdown, Darvas boxes,
F&amp;O enrichment, LLM-generated narratives, and short-term technical view.
</td></tr>

{_section_header("📎 Attachment 2 — Stage 2 Tracker")}
<tr><td style="padding:0 0 8px; font-family:{FONT_STACK}; font-size:13px; line-height:1.55;">
<code style="background:{COLOR_HEADER_BG}; padding:2px 6px; border-radius:3px;">stage2_tracker_{d}.html</code>
— Weinstein Stage 2 universe snapshot, <b>{data['total']} stocks scored</b>.
</td></tr>

<tr><td style="padding:0 0 14px; font-family:{FONT_STACK}; font-size:13px; line-height:1.55;">
Current Stage 2 universe: <b>{s2} stocks</b><br>
vs prior session ({cmp_str}): <b>{total_chg} stage changes</b> · {len(new_ent)} new / {len(exits)} exits
</td></tr>

<tr><td style="padding:4px 0; font-family:{FONT_STACK}; font-size:14px; font-weight:bold; color:{COLOR_GREEN};">
▲ New Stage 2 Entrants ({len(new_ent)})
</td></tr>
<tr><td style="padding:0 0 14px; font-family:{FONT_STACK}; font-size:13px; line-height:1.55;">
{new_list}
</td></tr>

<tr><td style="padding:4px 0; font-family:{FONT_STACK}; font-size:14px; font-weight:bold; color:{COLOR_RED};">
▼ Stage 2 Exits ({len(exits)})
</td></tr>
<tr><td style="padding:0 0 14px; font-family:{FONT_STACK}; font-size:13px; line-height:1.6;">
<b>→ Stage 1:</b> {exits_s1_str}<br>
<b>→ Unknown / out of coverage:</b> {exits_unk_str}
</td></tr>

<tr><td style="padding:4px 0; font-family:{FONT_STACK}; font-size:14px; font-weight:bold;">
Top Technical BUY Signals
</td></tr>
<tr><td style="padding:0 0 14px;">
<table cellspacing="0" cellpadding="0" border="0" width="100%" style="border-collapse:collapse; border:1px solid {COLOR_BORDER};">
<tr>
  {_th("Symbol")}{_th("Price (₹)", "right")}{_th("1D", "right")}{_th("1M", "right")}{_th("RSI", "right")}{_th("Tech Score", "right")}
</tr>
{buy_rows_html}
</table>
</td></tr>

{movers_block}

<tr><td style="padding:4px 0; font-family:{FONT_STACK}; font-size:14px; font-weight:bold;">
Signal Mix (full universe — {sum(sig_mix.values())} stocks)
</td></tr>
<tr><td style="padding:0 0 14px; font-family:{FONT_STACK}; font-size:13px; line-height:1.6;">
{sig_mix_str}
</td></tr>

{_section_header("🧭 How to Use")}
<tr><td style="padding:0 0 14px;">
<ol style="margin:0 0 0 22px; padding:0; font-family:{FONT_STACK}; font-size:13px; line-height:1.6;">
<li style="padding:2px 0;">Open each HTML attachment in your browser (Chrome / Safari / Edge).</li>
<li style="padding:2px 0;"><b>Sector Rotation Report</b> → start with the regime banner and ranked sector table; drill into per-stock cards for narratives, F&amp;O context, and price targets.</li>
<li style="padding:2px 0;"><b>Stage 2 Tracker</b> → review <i>New</i> entrants for fresh ideas and <i>Exits</i> for risk management; existing holdings should ideally remain in Stage 2.</li>
</ol>
</td></tr>

<tr><td style="padding:14px 0 6px; border-top:1px solid {COLOR_BORDER}; font-family:{FONT_STACK}; font-size:11px; color:{COLOR_MUTED}; line-height:1.5;">
<i>Disclaimer: Descriptive analytics on historical and live market data; not investment advice. Verify independently before trading.</i>
</td></tr>

<tr><td style="padding:14px 0 0; font-family:{FONT_STACK}; font-size:13px; line-height:1.6;">
Regards,<br>
<b style="color:{COLOR_PRIMARY}; font-size:14px;">Agent Adda</b><br>
<span style="color:{COLOR_MUTED}; font-size:11px;">ShunyaAI Core &nbsp;|&nbsp; Daily NSE Intelligence</span>
</td></tr>

</table>

</td></tr>
</table>"""


# ─────────────────────────────────────────────────────────────────────────────
# Outlook (AppleScript) integration
# ─────────────────────────────────────────────────────────────────────────────

def _applescript_recipients(label: str, recipients: list[tuple[str, str]]) -> str:
    """Build AppleScript snippet creating recipients of given type."""
    type_map = {"to": "to recipient", "cc": "cc recipient", "bcc": "bcc recipient"}
    rec_type = type_map[label]
    lines = []
    for name, addr in recipients:
        # Escape AppleScript double quotes
        name_e = name.replace('"', '\\"')
        addr_e = addr.replace('"', '\\"')
        lines.append(
            f'    make new {rec_type} at newMsg with properties {{email address:'
            f'{{name:"{name_e}", address:"{addr_e}"}}}}'
        )
    return "\n".join(lines)


def compose_via_outlook(
    subject: str,
    html_body: str,
    sector_attachment: Path,
    stage2_attachment: Path,
    tradingview_attachment: Path | None,
    to_recipients: list[tuple[str, str]],
    bcc_recipients: list[tuple[str, str]],
    send_immediately: bool = False,
) -> None:
    """Compose (and optionally send) the email via Microsoft Outlook on macOS."""
    # Write HTML body to a temp file — safer than embedding multi-line strings
    body_path = ROOT / "logs" / f"_email_body_{datetime.now():%Y%m%d_%H%M%S}.html"
    body_path.parent.mkdir(parents=True, exist_ok=True)
    body_path.write_text(html_body, encoding="utf-8")

    final_action = "send newMsg" if send_immediately else "open newMsg"
    to_block  = _applescript_recipients("to",  to_recipients)
    bcc_block = _applescript_recipients("bcc", bcc_recipients)

    subj_e = subject.replace('"', '\\"')
    body_path_str = str(body_path).replace('"', '\\"')
    sector_str    = str(sector_attachment).replace('"', '\\"')
    stage2_str    = str(stage2_attachment).replace('"', '\\"')
    tradingview_block = ""
    if tradingview_attachment and tradingview_attachment.exists():
        tv_str = str(tradingview_attachment).replace('"', '\\"')
        tradingview_block = (
            f'set tradingviewPath to POSIX file "{tv_str}"\n'
            '    make new attachment at newMsg with properties {file:tradingviewPath}'
        )

    script = f'''
set htmlBody to (do shell script "cat " & quoted form of "{body_path_str}")
set sectorPath to POSIX file "{sector_str}"
set stage2Path to POSIX file "{stage2_str}"
tell application "Microsoft Outlook"
    activate
    set newMsg to make new outgoing message with properties {{subject:"{subj_e}"}}
    set content of newMsg to htmlBody
{to_block}
{bcc_block}
    make new attachment at newMsg with properties {{file:sectorPath}}
    make new attachment at newMsg with properties {{file:stage2Path}}
    {tradingview_block}
    {final_action}
end tell
'''
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Outlook AppleScript failed:\n{result.stderr}")
    print(f"   AppleScript: {'sent' if send_immediately else 'draft opened'}")
    if result.stdout.strip():
        print(f"   stdout: {result.stdout.strip()}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description="Email daily NSE reports (PG-backed, Agent Adda)")
    p.add_argument("--date", help="Snapshot date YYYY-MM-DD (default: latest in PG)")
    p.add_argument("--send", action="store_true", help="Send immediately via Outlook (no draft review)")
    p.add_argument("--dry-run", action="store_true", help="Render body to stdout; do NOT touch Outlook")
    p.add_argument("--to", action="append", help="Override TO recipient (repeatable)")
    p.add_argument("--bcc", action="append", help="Override BCC recipient (repeatable)")
    args = p.parse_args()

    snap_date = fetch_latest_date(args.date)
    print(f"▶  Snapshot date: {snap_date}")

    # Gather PG-sourced metrics
    summary    = fetch_stage2_summary(snap_date)
    new_ent, exits = fetch_new_exit_stage2(snap_date, summary["compare_date"])
    top_buy    = fetch_top_buy_signals(snap_date, limit=8)
    sig_mix    = fetch_signal_mix(snap_date)
    fii_dii    = fetch_fii_dii(snap_date)
    macro      = fetch_macro_indicators(snap_date)
    tw_top, tw_bot = fetch_sector_tailwinds(snap_date)
    regime     = fetch_regime(snap_date)
    # Added 2026-05-19: pull Market Brief narrative + top gainers/losers
    market_brief = fetch_market_brief()
    gainers, losers = fetch_top_movers(snap_date, limit=8)

    print(f"   Stage 2: {summary['stage2_count']} stocks  |  changes vs {summary['compare_date']}: "
          f"{summary['total_changes']}  |  new={len(new_ent)} exits={len(exits)}")
    print(f"   Top BUY: {len(top_buy)} rows  |  Signal mix: {sum(sig_mix.values())} stocks")
    print(f"   Macro: {len(macro)} indicators  |  Tailwinds: {len(tw_top)}+{len(tw_bot)}")

    data = {
        "snapshot_date":    summary["snapshot_date"],
        "compare_date":     summary["compare_date"],
        "stage2_count":     summary["stage2_count"],
        "total":            summary["total"],
        "total_changes":    summary["total_changes"],
        "new_entrants":     new_ent,
        "exits":            exits,
        "top_buy":          top_buy,
        "signal_mix":       sig_mix,
        "fii_dii":          fii_dii,
        "macro":            macro,
        "tailwinds_top":    tw_top,
        "tailwinds_bottom": tw_bot,
        "regime":           regime,
        # Added 2026-05-19
        "market_brief":     market_brief,
        "gainers":          gainers,
        "losers":           losers,
    }

    html_body = render_body(data)

    # Build subject
    regime_label = (regime or {}).get("regime") or "ROTATION"
    nice_date = snap_date.strftime("%-d %b %Y")
    subject = (
        f"NSE Analysis Reports – {nice_date} | Regime: {regime_label} | "
        f"{len(new_ent)} New Stage 2 Entrants"
    )

    if args.dry_run:
        print("\n" + "═" * 60)
        print("DRY RUN — rendered HTML body follows")
        print("═" * 60)
        print(html_body)
        return 0

    sector_path, stage2_path, tradingview_path = locate_attachments(snap_date)
    if not sector_path.exists():
        print(f"❌ Sector rotation HTML not found: {sector_path}", file=sys.stderr)
        return 2
    if not stage2_path.exists():
        print(f"❌ Stage 2 tracker HTML not found: {stage2_path}", file=sys.stderr)
        return 2

    print(f"   Attaching: {sector_path.name} ({sector_path.stat().st_size//1024} KB)")
    print(f"   Attaching: {stage2_path.name} ({stage2_path.stat().st_size//1024} KB)")
    if tradingview_path.exists():
        print(f"   Attaching: {tradingview_path.name} ({tradingview_path.stat().st_size//1024} KB)")
    else:
        print(f"   TradingView watchlist not found, skipping attachment: {tradingview_path}")

    to_list  = [(addr.split('@')[0], addr) for addr in args.to]  if args.to  else TO_RECIPIENTS
    bcc_list = [(addr.split('@')[0], addr) for addr in args.bcc] if args.bcc else BCC_RECIPIENTS

    print(f"   To  ({len(to_list)}):  " + ", ".join(a for _, a in to_list))
    print(f"   Bcc ({len(bcc_list)}): " + ", ".join(a for _, a in bcc_list))
    print(f"   Subject: {subject}")
    print(f"   Mode: {'SEND' if args.send else 'OPEN DRAFT'}")

    compose_via_outlook(
        subject=subject,
        html_body=html_body,
        sector_attachment=sector_path,
        stage2_attachment=stage2_path,
        tradingview_attachment=tradingview_path if tradingview_path.exists() else None,
        to_recipients=to_list,
        bcc_recipients=bcc_list,
        send_immediately=args.send,
    )
    print("✅ Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
