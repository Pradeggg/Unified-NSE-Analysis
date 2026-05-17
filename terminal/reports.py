"""
First-class report generation engine for Agent Adda.
PG: Enables /report command — generates PDF, HTML, or Markdown reports
from any analysis output. Supports prebuilt report types:
  intraday, fundamental, technical, forensic, research, ric, canslim, sector
"""
from __future__ import annotations

import os
import re
import base64
import datetime
import html as _html
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports" / "generated"
PG_DSN = "dbname=nse_market user=nse_admin host=/tmp"

# ── Embed logo as base64 (self-contained HTML, works offline) ────────────────
def _load_logo_b64() -> str:
    logo_path = ROOT / "docs" / "Agent-adda-logo.jpg"
    if logo_path.exists():
        with open(logo_path, "rb") as _f:
            return "data:image/jpeg;base64," + base64.b64encode(_f.read()).decode()
    return ""  # graceful fallback — header renders without image

_LOGO_DATA_URI = _load_logo_b64()

# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _strip_ansi(text: str) -> str:
    return re.sub(r'\x1b\[[0-9;]*[mK]', '', text)


def _strip_rich_markup(text: str) -> str:
    """Remove Rich console markup tags for plain text output."""
    return re.sub(r'\[/?[a-zA-Z0-9_ #;:.]+\]', '', text)


# ── Signal word coloriser ─────────────────────────────────────────────────────
_SIGNAL_CLASSES = {
    "BUY":     "sig-buy",   "STRONG BUY": "sig-buy",
    "SELL":    "sig-sell",  "STRONG SELL": "sig-sell",
    "HOLD":    "sig-hold",  "NEUTRAL": "sig-hold",
    "AVOID":   "sig-avoid", "BEARISH": "sig-avoid",
    "BULLISH": "sig-bull",  "CAUTION": "sig-warn",
    "WATCH":   "sig-warn",  "ALERT":   "sig-warn",
    "PASS":    "sig-avoid", "FAIL":    "sig-avoid",
    "FLAG":    "sig-warn",
}

def _colorise_signals(text: str) -> str:
    """Wrap known signal words in colored spans.

    Only colorises text segments that are OUTSIDE existing HTML tags, anchors,
    and already-coloured spans. Without this guard the regex re-matches words
    like "buy" / "hold" / "neutral" inside hrefs and existing sig-* spans,
    producing broken nested markup such as
    ``<span class="sig-<span class="sig-hold">hold</span>">neutral</span>``.
    """
    # Tokenise on HTML tags so we never substitute inside one.
    parts = re.split(r'(<[^>]+>)', text)
    depth_a = 0
    depth_sig = 0
    for idx, seg in enumerate(parts):
        if seg.startswith('<'):
            low = seg.lower()
            if low.startswith('<a '):
                depth_a += 1
            elif low.startswith('</a>'):
                depth_a = max(0, depth_a - 1)
            elif re.match(r'<span\s+class="sig-', low):
                depth_sig += 1
            elif low.startswith('</span>') and depth_sig:
                depth_sig -= 1
            continue
        if depth_a or depth_sig:
            continue
        for word, cls in sorted(_SIGNAL_CLASSES.items(), key=lambda x: -len(x[0])):
            seg = re.sub(
                rf'(?<![\w-])({re.escape(word)})(?![\w-])',
                rf'<span class="{cls}">\1</span>',
                seg, flags=re.IGNORECASE
            )
        parts[idx] = seg
    return ''.join(parts)


# Linkify bare URLs, including those wrapped in parentheses like (https://...)
_URL_RE = re.compile(r'(?<!["\'>=])(https?://[^\s<>)\]]+)')

def _linkify_urls(text: str) -> str:
    """Convert bare ``https://...`` occurrences into clickable links.

    Skips URLs already inside an ``href`` attribute. Strips trailing punctuation
    so a trailing period or closing paren doesn't get absorbed into the link.
    """
    def _sub(match: re.Match) -> str:
        url = match.group(1)
        trail = ''
        while url and url[-1] in '.,;:)':
            trail = url[-1] + trail
            url = url[:-1]
        if not url:
            return match.group(0)
        return f'<a href="{url}" target="_blank" rel="noopener">{url}</a>{trail}'
    # Process segment-by-segment to avoid touching href attributes.
    parts = re.split(r'(<a [^>]*>.*?</a>)', text, flags=re.IGNORECASE | re.DOTALL)
    for i, seg in enumerate(parts):
        if seg.lower().startswith('<a '):
            continue
        parts[i] = _URL_RE.sub(_sub, seg)
    return ''.join(parts)


def _fmt_num(v, digits: int = 2, suffix: str = "") -> str:
    try:
        if v is None:
            return "N/A"
        fv = float(v)
        return f"{fv:,.{digits}f}{suffix}"
    except Exception:
        return "N/A"


def _fmt_text(v) -> str:
    s = "" if v is None else str(v).strip()
    return s if s and s.lower() not in {"nan", "none", "null"} else "N/A"


def _build_postgres_research_context(symbol: str) -> str:
    """Build a data-backed research context from PostgreSQL for /report research."""
    if not symbol:
        return ""
    sym = symbol.upper().strip()
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(PG_DSN)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    WITH px AS (
                        SELECT * FROM market.equity_eod
                        WHERE symbol = %s
                    ),
                    latest AS (
                        SELECT * FROM px ORDER BY trade_date DESC LIMIT 1
                    ),
                    metrics AS (
                        SELECT
                            (SELECT close FROM latest) AS latest_close,
                            (SELECT trade_date FROM latest) AS latest_date,
                            (SELECT volume FROM latest) AS latest_volume,
                            (SELECT turnover_cr FROM latest) AS latest_turnover,
                            (SELECT close FROM px WHERE trade_date <= (SELECT trade_date FROM latest) - INTERVAL '7 days' ORDER BY trade_date DESC LIMIT 1) AS close_1w,
                            (SELECT close FROM px WHERE trade_date <= (SELECT trade_date FROM latest) - INTERVAL '1 month' ORDER BY trade_date DESC LIMIT 1) AS close_1m,
                            (SELECT close FROM px WHERE trade_date <= (SELECT trade_date FROM latest) - INTERVAL '3 months' ORDER BY trade_date DESC LIMIT 1) AS close_3m,
                            (SELECT close FROM px WHERE trade_date <= (SELECT trade_date FROM latest) - INTERVAL '6 months' ORDER BY trade_date DESC LIMIT 1) AS close_6m,
                            (SELECT close FROM market.index_eod WHERE index_symbol IN ('Nifty 50', 'NIFTY 50') AND trade_date <= (SELECT trade_date FROM latest) ORDER BY trade_date DESC LIMIT 1) AS nifty_close,
                            (SELECT close FROM market.index_eod WHERE index_symbol IN ('Nifty 50', 'NIFTY 50') AND trade_date <= (SELECT trade_date FROM latest) - INTERVAL '1 month' ORDER BY trade_date DESC LIMIT 1) AS nifty_close_1m,
                            (SELECT min(close) FROM px) AS all_time_low,
                            (SELECT max(close) FROM px) AS all_time_high,
                            (SELECT avg(volume) FROM (SELECT volume FROM px ORDER BY trade_date DESC LIMIT 20) v) AS avg_volume_20d,
                            (SELECT avg(turnover_cr) FROM (SELECT turnover_cr FROM px ORDER BY trade_date DESC LIMIT 20) t) AS avg_turnover_20d,
                            (SELECT count(*) FROM px) AS price_rows,
                            (SELECT min(trade_date) FROM px) AS first_price_date
                    )
                    SELECT
                        i.symbol,
                        i.company_name,
                        i.sector,
                        i.industry,
                        i.market_cap_cat,
                        i.face_value,
                        i.issue_size,
                        i.is_fno,
                        i.is_nifty500,
                        i.status,
                        s.stage,
                        s.stage_score,
                        s.technical_score,
                        s.rsi,
                        s.trading_signal,
                        s.trend_signal,
                        s.relative_strength,
                        s.can_slim_score,
                        s.minervini_score,
                        s.fundamental_score,
                        s.enhanced_fund_score,
                        s.investment_score,
                        sc.screens_passed_total,
                        sc.conviction_tier,
                        sc.passed_screens,
                        m.*
                    FROM ref.instruments i
                    CROSS JOIN metrics m
                    LEFT JOIN scores.mv_latest_snapshot s ON s.symbol = i.symbol
                    LEFT JOIN screener.mv_latest_summary sc ON sc.symbol = i.symbol
                    WHERE i.symbol = %s
                    """,
                    (sym, sym),
                )
                row = cur.fetchone()
        finally:
            conn.close()
    except Exception:
        return ""

    if not row:
        return ""

    close = row.get("latest_close")
    def ret(prev):
        try:
            return (float(close) / float(prev) - 1) * 100 if close and prev else None
        except Exception:
            return None

    ret_1w = ret(row.get("close_1w"))
    ret_1m = ret(row.get("close_1m"))
    ret_3m = ret(row.get("close_3m"))
    ret_6m = ret(row.get("close_6m"))
    nifty_ret_1m = None
    try:
        nifty_ret_1m = (float(row.get("nifty_close")) / float(row.get("nifty_close_1m")) - 1) * 100
    except Exception:
        pass
    rs_value = row.get("relative_strength")
    rs_source = "score snapshot"
    if rs_value is None and ret_1m is not None and nifty_ret_1m is not None:
        rs_value = ret_1m - nifty_ret_1m
        rs_source = "derived: stock 1M return minus NIFTY 50 1M return"
    high = row.get("all_time_high")
    low = row.get("all_time_low")
    dd_high = None
    try:
        dd_high = (float(close) / float(high) - 1) * 100 if close and high else None
    except Exception:
        pass

    overview_bits = [
        f"{_fmt_text(row.get('company_name'))} is classified under {_fmt_text(row.get('sector'))}",
        f"latest close ₹{_fmt_num(close)} as of {_fmt_text(row.get('latest_date'))}",
        f"1M return {_fmt_num(ret_1m, 2, '%')}",
        f"stage {_fmt_text(row.get('stage'))}",
        f"RS {_fmt_num(rs_value, 2, '%')}",
        f"drawdown from DB high {_fmt_num(dd_high, 2, '%')}",
    ]

    lines = [
        "## Agent Adda Overview",
        "",
        "> " + "; ".join(overview_bits) + ". Use this as the quick data-backed setup before reading the full research narrative.",
        "",
        "## Market Intelligence Snapshot",
        "",
        "> This section was auto-populated from the local market data store before rendering the report.",
        "",
        "| Field | Value |",
        "|---|---:|",
        f"| Company | {_fmt_text(row.get('company_name'))} |",
        f"| Symbol | {sym} |",
        f"| Sector / Industry | {_fmt_text(row.get('sector'))} / {_fmt_text(row.get('industry'))} |",
        f"| Market-cap category | {_fmt_text(row.get('market_cap_cat'))} |",
        f"| Latest close | ₹{_fmt_num(close)} |",
        f"| Latest price date | {_fmt_text(row.get('latest_date'))} |",
        f"| 1W / 1M / 3M / 6M return | {_fmt_num(ret_1w, 2, '%')} / {_fmt_num(ret_1m, 2, '%')} / {_fmt_num(ret_3m, 2, '%')} / {_fmt_num(ret_6m, 2, '%')} |",
        f"| Listed price history | {_fmt_text(row.get('first_price_date'))} onward · {int(row.get('price_rows') or 0):,} rows |",
        f"| Price range in DB | ₹{_fmt_num(low)} – ₹{_fmt_num(high)} |",
        f"| Drawdown from DB high | {_fmt_num(dd_high, 2, '%')} |",
        f"| Latest volume / 20D avg volume | {_fmt_num(row.get('latest_volume'), 0)} / {_fmt_num(row.get('avg_volume_20d'), 0)} |",
        f"| Latest turnover / 20D avg turnover | ₹{_fmt_num(row.get('latest_turnover'), 2)} / ₹{_fmt_num(row.get('avg_turnover_20d'), 2)} |",
        f"| F&O stock | {'Yes' if row.get('is_fno') else 'No'} |",
        "",
        "## Pre-computed Score Availability",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Weinstein stage | {_fmt_text(row.get('stage'))} |",
        f"| Stage score | {_fmt_num(row.get('stage_score'))} |",
        f"| Technical score | {_fmt_num(row.get('technical_score'))} |",
        f"| RSI | {_fmt_num(row.get('rsi'))} |",
        f"| Trading signal | {_fmt_text(row.get('trading_signal'))} |",
        f"| Trend signal | {_fmt_text(row.get('trend_signal'))} |",
        f"| Relative strength vs NIFTY 50 (1M) | {_fmt_num(rs_value, 2, '%')} |",
        f"| Relative strength source | {_fmt_text(rs_source)} |",
        f"| CANSLIM score | {_fmt_num(row.get('can_slim_score'))} |",
        f"| Minervini score | {_fmt_num(row.get('minervini_score'))} |",
        f"| Fundamental score | {_fmt_num(row.get('fundamental_score'))} |",
        f"| Enhanced fund score | {_fmt_num(row.get('enhanced_fund_score'))} |",
        f"| Investment score | {_fmt_num(row.get('investment_score'))} |",
        f"| Screener conviction | {_fmt_text(row.get('conviction_tier'))} |",
        f"| Screens passed | {_fmt_num(row.get('screens_passed_total'), 0)} |",
        "",
    ]
    screens = row.get("passed_screens")
    if screens:
        if isinstance(screens, (list, tuple)):
            screen_text = ", ".join(str(s) for s in screens[:12])
        else:
            screen_text = str(screens)
        lines.extend(["**Passed screens:** " + screen_text, ""])

    if not row.get("stage") and not row.get("technical_score"):
        lines.extend([
            "### Data gap note",
            "",
            f"{sym} has EOD price history and reference/master data, but it is not present in the latest pre-computed score snapshot or screener summary. The report should therefore treat stage, CANSLIM, Minervini, and investment-score fields as unavailable rather than as weak signals.",
            "",
        ])

    return "\n".join(lines)


def _inline_md(text: str) -> str:
    """Convert inline Markdown (bold, italic, code, links) inside a line."""
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', text)
    text = re.sub(r'\*\*(.+?)\*\*',     r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*',         r'<em>\1</em>', text)
    # Underscore italics (_text_) — only when both underscores are at word boundaries.
    text = re.sub(r'(?<![\w_])_([^_\n]+?)_(?![\w_])', r'<em>\1</em>', text)
    text = re.sub(r'`(.+?)`',           r'<code>\1</code>', text)

    def _md_link(match: re.Match) -> str:
        label = _html.unescape(match.group(1)).strip()
        href = _html.unescape(match.group(2)).strip()
        if href.startswith("<") and href.endswith(">"):
            href = href[1:-1].strip()
        href = href.strip("\"'")
        if ">" in label and "target=" in label.lower():
            label = label.rsplit(">", 1)[-1].strip()
        return (
            f'<a href="{_html.escape(href, quote=True)}" target="_blank">'
            f'{_html.escape(label)}</a>'
        )

    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', _md_link, text)
    text = _linkify_urls(text)
    text = _colorise_signals(text)
    return text


def _md_to_html_basic(md_text: str) -> str:
    """
    Convert Markdown to rich HTML.
    Handles: headers, bold/italic/code, links, ordered + unordered lists,
    Markdown pipe tables, blockquotes, horizontal rules, code blocks.
    """
    lines = md_text.split('\n')
    out: list[str] = []
    in_code   = False
    in_ul     = False
    in_ol     = False
    in_bq     = False
    in_table  = False
    table_rows: list[str] = []

    def _flush_list():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append('</ul>')
            in_ul = False
        if in_ol:
            out.append('</ol>')
            in_ol = False

    def _emit_plain_rows(rows: list[str]) -> None:
        for row in rows:
            if row.strip():
                out.append(f'<p>{_inline_md(_html.escape(row))}</p>')

    def _table_cells(line: str) -> list[str]:
        stripped = line.strip()
        if "|" not in stripped:
            return []
        if stripped.startswith("|"):
            stripped = stripped[1:]
        if stripped.endswith("|"):
            stripped = stripped[:-1]
        cells = [cell.strip() for cell in stripped.split("|")]
        return cells if len(cells) >= 2 else []

    def _flush_table():
        nonlocal in_table, table_rows
        if not table_rows:
            return
        in_table = False
        rows = table_rows[:]
        table_rows.clear()
        if len(rows) < 2 or not _is_separator(rows[1]):
            _emit_plain_rows(rows)
            return
        header = rows[0]
        # rows[1] is the separator line — skip it
        body_rows = rows[2:] if len(rows) > 2 else []

        cells = _table_cells(header)
        th_html = ''.join(f'<th>{_inline_md(_html.escape(c))}</th>' for c in cells)
        out.append(
            '<div class="tbl-wrap">'
            '<table class="data-table" data-sortable="true">'
            f'<thead><tr>{th_html}</tr></thead><tbody>'
        )
        for row in body_rows:
            tds = _table_cells(row)
            td_html = ''.join(f'<td>{_inline_md(_html.escape(c))}</td>' for c in tds)
            out.append(f'<tr>{td_html}</tr>')
        out.append('</tbody></table></div>')

    def _flush_blockquote():
        nonlocal in_bq
        if in_bq:
            out.append('</blockquote>')
            in_bq = False

    def _is_table_row(line: str) -> bool:
        return bool(_table_cells(line))

    def _is_separator(line: str) -> bool:
        cells = _table_cells(line)
        return bool(cells) and all(re.fullmatch(r':?-{3,}:?', cell) for cell in cells)

    ol_counter = 0
    in_kv = False  # whether we're inside an indented "Key: Value" definition list

    def _flush_kv():
        nonlocal in_kv
        if in_kv:
            out.append('</dl>')
            in_kv = False

    for line in lines:
        raw = line

        # ── Code block toggle ─────────────────────────────────────────────
        if raw.strip().startswith('```'):
            if in_code:
                out.append('</code></pre>')
                in_code = False
            else:
                _flush_list(); _flush_table(); _flush_blockquote(); _flush_kv()
                lang = raw.strip()[3:].strip()
                out.append(f'<pre><code class="lang-{lang}">')
                in_code = True
            continue
        if in_code:
            out.append(_html.escape(raw))
            continue

        # ── Table rows ────────────────────────────────────────────────────
        if _is_table_row(raw):
            _flush_list(); _flush_blockquote(); _flush_kv()
            if _is_separator(raw) and table_rows:
                table_rows.append(raw)  # keep separator to detect header boundary
            else:
                in_table = True
                table_rows.append(raw)
            continue
        else:
            if in_table:
                _flush_table()

        # ── ━━━ Part-style divider ━━━ ────────────────────────────────────
        part_m = re.match(r'^\s*━{2,}\s*(.+?)\s*━{2,}\s*$', raw)
        if part_m:
            _flush_list(); _flush_blockquote(); _flush_kv()
            label = _inline_md(_html.escape(part_m.group(1)))
            out.append(f'<div class="part-divider"><span>{label}</span></div>')
            continue

        # ── ▶ Section header (e.g. "▶ SNAPSHOT") ──────────────────────────
        arrow_m = re.match(r'^\s*▶\s+(.+?)\s*$', raw)
        if arrow_m:
            _flush_list(); _flush_blockquote(); _flush_kv()
            label = _inline_md(_html.escape(arrow_m.group(1)))
            out.append(f'<div class="arrow-header">{label}</div>')
            continue

        # ── Indented "Key: Value" lines → definition list (compact) ───────
        kv_m = re.match(r'^( {2,}|\t+)([A-Za-z0-9 _/&()%+\-.\']{2,40}?):\s+(.*\S.*)$', raw)
        if kv_m and not raw.lstrip().startswith(('-', '*', '•', '#', '|', '>')):
            if not in_kv:
                _flush_list(); _flush_blockquote()
                out.append('<dl class="kv-list">')
                in_kv = True
            k = _inline_md(_html.escape(kv_m.group(2).strip()))
            v = _inline_md(_html.escape(kv_m.group(3).strip()))
            out.append(f'<dt>{k}</dt><dd>{v}</dd>')
            continue
        else:
            if in_kv and raw.strip() != '':
                _flush_kv()

        # ── Blank line ────────────────────────────────────────────────────
        if raw.strip() == '':
            _flush_list()
            _flush_blockquote()
            _flush_kv()
            out.append('<div class="gap"></div>')
            continue

        # ── Horizontal rule ───────────────────────────────────────────────
        if re.match(r'^[-*_]{3,}\s*$', raw.strip()):
            _flush_list(); _flush_blockquote(); _flush_kv()
            out.append('<hr>')
            continue

        # ── Blockquote ────────────────────────────────────────────────────
        bq_m = re.match(r'^>\s?(.*)', raw)
        if bq_m:
            _flush_list(); _flush_kv()
            if not in_bq:
                out.append('<blockquote>')
                in_bq = True
            out.append(f'<p>{_inline_md(_html.escape(bq_m.group(1)))}</p>')
            continue
        else:
            _flush_blockquote()

        # ── Headers ───────────────────────────────────────────────────────
        h_m = re.match(r'^(#{1,6})\s+(.*)', raw)
        if h_m:
            _flush_list(); _flush_kv()
            level = len(h_m.group(1))
            text  = _inline_md(_html.escape(h_m.group(2)))
            slug  = re.sub(r'[^a-z0-9]+', '-', h_m.group(2).lower()).strip('-')
            out.append(f'<h{level} id="{slug}">{text}</h{level}>')
            continue

        # ── Ordered list ──────────────────────────────────────────────────
        ol_m = re.match(r'^\s*(\d+)\.\s+(.*)', raw)
        if ol_m:
            _flush_blockquote(); _flush_kv()
            if not in_ol:
                _flush_list()
                out.append('<ol>')
                in_ol = True
                ol_counter = int(ol_m.group(1))
            out.append(f'<li>{_inline_md(_html.escape(ol_m.group(2)))}</li>')
            continue

        # ── Unordered list ────────────────────────────────────────────────
        ul_m = re.match(r'^\s*[-•*]\s+(.*)', raw)
        if ul_m:
            _flush_blockquote(); _flush_kv()
            if not in_ul:
                _flush_list()
                out.append('<ul>')
                in_ul = True
            out.append(f'<li>{_inline_md(_html.escape(ul_m.group(1)))}</li>')
            continue

        # ── Regular paragraph ─────────────────────────────────────────────
        _flush_list(); _flush_kv()
        out.append(f'<p>{_inline_md(_html.escape(raw))}</p>')

    # Flush any open structures
    _flush_list()
    _flush_table()
    _flush_blockquote()
    _flush_kv()
    if in_code:
        out.append('</code></pre>')

    return '\n'.join(out)


# ─────────────────────────────────────────────────────────────────────────────
# HTML Report Template
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# HTML Report Template — Premium design with logo, interactive tables, TOC
# ─────────────────────────────────────────────────────────────────────────────

REPORT_HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Agent Adda</title>
<style>
/* ── Reset & variables ─────────────────────────────────────────────── */
:root {{
  --bg:       #07070f;
  --surface:  #0f0f1a;
  --card:     #14142a;
  --border:   #252545;
  --border2:  #1e1e38;
  --text:     #e2e2f0;
  --dim:      #6868a0;
  --accent:   #7c6fff;
  --accent2:  #22d3ee;
  --green:    #4ade80;
  --red:      #f87171;
  --yellow:   #fbbf24;
  --orange:   #fb923c;
  --purple:   #c084fc;
  --radius:   10px;
  --shadow:   0 4px 24px rgba(0,0,0,.45);
}}
*,*::before,*::after {{ box-sizing:border-box; margin:0; padding:0; }}
html {{ scroll-behavior:smooth; }}
body {{
  background: var(--bg);
  color: var(--text);
  font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
  font-size: 14px;
  line-height: 1.75;
  min-height: 100vh;
}}
a {{ color: var(--accent2); text-decoration:none; }}
a:hover {{ text-decoration:underline; }}

/* ── Top nav bar ───────────────────────────────────────────────────── */
.topbar {{
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 0 32px;
  height: 52px;
  display:flex; align-items:center; justify-content:space-between;
  position: sticky; top:0; z-index:99;
}}
.topbar-brand {{ display:flex; align-items:center; gap:12px; }}
.topbar-brand img {{
  height:32px; width:auto; border-radius:6px;
  object-fit:contain; background:#fff; padding:2px 4px;
}}
.topbar-brand .brand-name {{
  font-size:15px; font-weight:800; letter-spacing:.02em;
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent2) 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
}}
.topbar-actions {{ display:flex; align-items:center; gap:12px; }}
.btn {{
  padding: 6px 14px; border-radius:6px; font-size:12px; font-weight:600;
  cursor:pointer; border:none; transition: all .15s;
}}
.btn-outline {{
  background:transparent; border:1px solid var(--border);
  color:var(--dim);
}}
.btn-outline:hover {{ border-color:var(--accent); color:var(--accent); }}
.btn-primary {{
  background: var(--accent); color:#fff;
}}
.btn-primary:hover {{ opacity:.88; }}

/* ── Topbar search ─────────────────────────────────────────────────── */
.search-wrap {{
  position:relative; display:none; align-items:center;
}}
.search-wrap.active {{
  display:flex;
}}
.topbar-search {{
  background:var(--card); border:1px solid var(--border);
  color:var(--text); border-radius:6px;
  padding:5px 28px 5px 10px; font-size:12px; width:200px;
  outline:none; transition:.2s;
}}
.topbar-search:focus {{
  border-color:var(--accent); width:260px;
  box-shadow:0 0 0 2px rgba(124,111,255,.15);
}}
.topbar-search::placeholder {{ color:var(--dim); }}
.srch-clear {{
  position:absolute; right:6px;
  background:none; border:none; color:var(--dim);
  font-size:12px; cursor:pointer; padding:0; line-height:1;
  display:none;
}}
.srch-clear.visible {{ display:block; }}
mark.srch-hl {{
  background:rgba(251,191,36,.35); color:inherit;
  border-radius:2px; padding:0 1px;
}}

/* ── Report header ─────────────────────────────────────────────────── */
.report-header {{
  background: linear-gradient(160deg, #0e0e20 0%, #12122a 60%, #0a0a1a 100%);
  border-bottom: 1px solid var(--border);
  padding: 36px 40px 28px;
}}
.report-header-inner {{
  max-width:1100px; margin:0 auto;
  display:flex; align-items:flex-start; justify-content:space-between; gap:24px;
  flex-wrap:wrap;
}}
.report-header-left {{ flex:1; min-width:0; }}
.report-title {{
  font-size: 26px; font-weight:800; line-height:1.3;
  background: linear-gradient(135deg, #fff 0%, var(--accent2) 100%);
  -webkit-background-clip:text; -webkit-text-fill-color:transparent;
  background-clip:text;
  margin-bottom:12px;
}}
.report-meta {{
  display:flex; flex-wrap:wrap; gap:14px; font-size:13px; color:var(--dim);
  align-items:center;
}}
.meta-pill {{
  display:inline-flex; align-items:center; gap:5px;
  background:var(--card); border:1px solid var(--border);
  border-radius:20px; padding:4px 12px; font-size:12px;
}}
.report-badge {{
  display:inline-flex; align-items:center;
  padding: 4px 12px; border-radius:5px;
  font-size:11px; font-weight:700; letter-spacing:.08em;
  text-transform:uppercase;
}}
.badge-technical  {{ background:#0e2040; color:#93c5fd; border:1px solid #1e3a6f; }}
.badge-fundamental{{ background:#0a2018; color:var(--green); border:1px solid #1a4028; }}
.badge-forensic   {{ background:#200808; color:var(--red);   border:1px solid #4a1010; }}
.badge-research   {{ background:#16083a; color:var(--purple);border:1px solid #2d1469; }}
.badge-intraday   {{ background:#0f1520; color:var(--yellow);border:1px solid #2a2500; }}
.badge-canslim    {{ background:#0a1a0a; color:#86efac;      border:1px solid #1a4020; }}
.badge-ric        {{ background:#160a2a; color:#c4b5fd;      border:1px solid #2a1450; }}
.badge-sector     {{ background:#071826; color:#7dd3fc;      border:1px solid #0e2a40; }}
.badge-sector-rotation {{ background:#061a30; color:#38bdf8; border:1px solid #0e3a60; }}
.badge-stage2     {{ background:#081a06; color:#a3e635;      border:1px solid #1a4a08; }}
.report-logo-block {{
  flex-shrink:0; display:flex; flex-direction:column; align-items:center;
  gap:8px; opacity:.9;
}}
.report-logo-block img {{
  height:80px; width:auto; border-radius:10px;
  object-fit:contain; background:#fff;
  padding:4px 8px; box-shadow: var(--shadow);
}}
.report-logo-block .logo-sub {{
  font-size:10px; color:var(--dim); text-align:center; letter-spacing:.05em;
}}

/* ── Layout ────────────────────────────────────────────────────────── */
.page-layout {{
  max-width:1440px; margin:0 auto; padding:28px 32px;
}}

/* ── TOC — collapsible right-side drawer ───────────────────────────── */
.toc-overlay {{
  display:none; position:fixed; inset:0; z-index:198;
  background:rgba(0,0,0,.45); backdrop-filter:blur(2px);
}}
.toc-overlay.open {{ display:block; }}
.toc-drawer {{
  position:fixed; top:52px; right:0; bottom:0; z-index:199;
  width:300px; background:var(--surface);
  border-left:1px solid var(--border);
  display:flex; flex-direction:column;
  transform:translateX(100%); transition:transform .28s cubic-bezier(.4,0,.2,1);
  box-shadow:-8px 0 32px rgba(0,0,0,.5);
}}
.toc-drawer.open {{ transform:translateX(0); }}
.toc-drawer-header {{
  padding:14px 18px 10px;
  border-bottom:1px solid var(--border);
  display:flex; align-items:center; justify-content:space-between;
}}
.toc-drawer-header h4 {{
  color:var(--accent2); font-size:12px; font-weight:700;
  text-transform:uppercase; letter-spacing:.1em; margin:0;
}}
.toc-close {{
  background:none; border:none; color:var(--dim);
  font-size:18px; cursor:pointer; padding:0 4px;
  line-height:1;
}}
.toc-close:hover {{ color:var(--text); }}
.toc-body {{
  flex:1; overflow-y:auto; padding:10px 0 20px;
}}
.toc-body a {{
  display:block; color:var(--dim); padding:5px 18px;
  border-left:2px solid transparent;
  font-size:12.5px; transition:.15s; text-decoration:none;
}}
.toc-body a:hover {{ color:var(--accent2); border-left-color:var(--accent2); background:rgba(34,211,238,.04); }}
.toc-body a.active {{ color:var(--accent2); border-left-color:var(--accent2); font-weight:600; }}
.toc-body a.toc-h3 {{ padding-left:30px; font-size:11.5px; }}
.toc-body a.toc-h4 {{ padding-left:40px; font-size:11px; color:#555580; }}
.toc-section-num {{
  display:inline-block; width:20px; color:var(--accent);
  font-weight:700; font-size:11px; flex-shrink:0;
}}

/* ── Summary strip ─────────────────────────────────────────────────── */
.summary-strip {{
  max-width:1440px; margin:0 auto;
  padding:0 32px 0;
}}
.summary-inner {{
  background: linear-gradient(135deg,#0d0d22 0%,#11112a 100%);
  border:1px solid var(--border); border-radius:12px;
  padding:20px 24px 18px; margin-bottom:20px;
}}
.summary-label {{
  font-size:10.5px; text-transform:uppercase; letter-spacing:.12em;
  color:var(--dim); margin-bottom:12px; display:flex; align-items:center; gap:6px;
}}
.summary-label::after {{
  content:''; flex:1; height:1px; background:var(--border);
}}
.summary-pills {{
  display:flex; flex-wrap:wrap; gap:8px; margin-bottom:14px;
}}
.summary-pill {{
  background:var(--card); border:1px solid var(--border);
  border-radius:20px; padding:4px 14px;
  font-size:12px; color:var(--dim); cursor:pointer;
  transition:.15s; text-decoration:none; white-space:nowrap;
  display:inline-flex; align-items:center; gap:5px;
}}
.summary-pill:hover {{
  border-color:var(--accent2); color:var(--accent2);
  background:rgba(34,211,238,.06); text-decoration:none;
}}
.summary-pill .pill-num {{
  background:var(--accent); color:#fff;
  border-radius:50%; width:16px; height:16px;
  display:inline-flex; align-items:center; justify-content:center;
  font-size:9px; font-weight:700; flex-shrink:0;
}}
.summary-teaser {{
  font-size:13px; color:#9090b8; line-height:1.75;
  padding-top:12px; border-top:1px solid var(--border2);
}}
.summary-stats {{
  display:flex; gap:20px; flex-wrap:wrap; margin-bottom:12px;
}}
.stat-chip {{
  display:flex; flex-direction:column; align-items:flex-start;
}}
.stat-chip .stat-val {{
  font-size:18px; font-weight:800;
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent2) 100%);
  -webkit-background-clip:text; -webkit-text-fill-color:transparent;
  background-clip:text; line-height:1.2;
}}
.stat-chip .stat-lbl {{ font-size:10px; color:var(--dim); text-transform:uppercase; letter-spacing:.08em; }}

/* ── Content area ──────────────────────────────────────────────────── */
.content-area {{ min-width:0; }}

/* ── Section cards ─────────────────────────────────────────────────── */
.section {{
  background:var(--card); border:1px solid var(--border);
  border-radius:var(--radius); margin-bottom:16px; overflow:hidden;
  box-shadow: 0 2px 12px rgba(0,0,0,.3);
  transition: border-color .2s;
}}
.section:hover {{ border-color: var(--border2); }}
.section-header {{
  padding:13px 20px; background:var(--surface);
  border-bottom:1px solid var(--border);
  font-weight:700; font-size:13.5px; color:var(--accent2);
  display:flex; justify-content:space-between; align-items:center;
  cursor:pointer; user-select:none;
}}
.section-header:hover {{ background:rgba(34,211,238,.04); }}
.section-toggle {{ font-size:16px; transition:transform .2s; color:var(--dim); }}
.section.collapsed .section-toggle {{ transform:rotate(-90deg); }}
.section-body {{
  padding:18px 22px; font-size:13.5px; line-height:1.85;
  overflow:hidden; transition:all .25s ease;
}}
.section.collapsed .section-body {{ display:none; }}

/* ── Content typography ────────────────────────────────────────────── */
.section-body h1 {{ font-size:19px; color:var(--accent);  margin:18px 0 8px; }}
.section-body h2 {{ font-size:16px; color:var(--accent2); margin:16px 0 6px; }}
.section-body h3 {{ font-size:14.5px;color:var(--purple); margin:12px 0 5px; }}
.section-body h4 {{ font-size:13px; color:var(--dim);     margin:10px 0 4px; font-weight:600; }}
.section-body p  {{ margin-bottom:8px; }}
.section-body ul {{ margin:6px 0 10px 20px; }}
.section-body ol {{ margin:6px 0 10px 22px; }}
.section-body li {{ margin-bottom:4px; }}
.section-body hr {{ border:none; border-top:1px solid var(--border); margin:16px 0; }}
.section-body strong {{ color:var(--accent2); font-weight:600; }}
.section-body em    {{ color:#c0c0e0; font-style:italic; }}
.section-body code {{
  background:var(--surface); padding:2px 7px; border-radius:4px;
  font-family:'JetBrains Mono','Fira Code','Courier New',monospace;
  font-size:12px; color:var(--yellow);
}}
.section-body pre {{
  background:var(--surface); border:1px solid var(--border);
  border-radius:6px; padding:14px 16px; overflow-x:auto;
  font-size:12px; font-family:'JetBrains Mono','Fira Code','Courier New',monospace;
  margin:10px 0; line-height:1.6;
}}
.section-body blockquote {{
  border-left:3px solid var(--accent); margin:10px 0;
  padding:8px 14px; background:rgba(124,111,255,.06);
  border-radius:0 6px 6px 0; color:#a0a0c0;
}}
.gap {{ height:6px; }}
.gap + .gap, .gap + .part-divider, .part-divider + .gap {{ display:none; }}

/* ── ━━━ Part-of-N dividers ─────────────────────────────────────────── */
.part-divider {{
  display:flex; align-items:center; gap:14px;
  margin:22px 0 14px;
  color: var(--accent2);
  font-size:11px; font-weight:700; letter-spacing:.14em; text-transform:uppercase;
}}
.part-divider::before, .part-divider::after {{
  content:""; flex:1; height:1px;
  background: linear-gradient(90deg, transparent, var(--border) 30%, var(--border) 70%, transparent);
}}
.part-divider span {{ white-space:nowrap; }}

/* ── ▶ Section sub-header (e.g. ▶ SNAPSHOT) ─────────────────────────── */
.arrow-header {{
  margin: 14px 0 4px;
  padding: 6px 12px;
  background: linear-gradient(90deg, rgba(124,111,255,.12), rgba(124,111,255,0));
  border-left: 3px solid var(--accent);
  color: var(--accent2);
  font-size: 12px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase;
  border-radius: 4px;
}}
.arrow-header::before {{ content: "▶ "; opacity:.7; }}

/* ── Indented key:value blocks (rendered as <dl>) ───────────────────── */
.kv-list {{
  display: grid;
  grid-template-columns: max-content 1fr;
  column-gap: 18px; row-gap: 2px;
  margin: 6px 0 10px;
  padding: 10px 14px;
  background: var(--surface);
  border: 1px solid var(--border2);
  border-radius: 7px;
  font-size: 13px;
  font-family: 'JetBrains Mono', 'SF Mono', 'Menlo', 'Consolas', monospace;
}}
.kv-list dt {{ color: var(--dim); font-weight: 600; white-space: nowrap; }}
.kv-list dd {{ color: var(--text); margin: 0; }}

/* ── Signal colors ─────────────────────────────────────────────────── */
.sig-buy  {{ color:var(--green);  font-weight:700; }}
.sig-sell {{ color:var(--red);    font-weight:700; }}
.sig-hold {{ color:var(--yellow); font-weight:700; }}
.sig-avoid{{ color:var(--orange); font-weight:700; }}
.sig-bull {{ color:var(--green);  font-weight:700; }}
.sig-warn {{ color:var(--orange); font-weight:700; }}

/* ── Tables ────────────────────────────────────────────────────────── */
.tbl-wrap {{
  overflow-x:auto; margin:14px 0; border-radius:7px;
  border:1px solid var(--border);
  width:100%;
}}
.data-table {{
  width:max-content; min-width:100%;
  border-collapse:collapse; font-size:13px;
}}
.data-table thead tr {{ background:var(--surface); }}
.data-table th {{
  padding:9px 16px; text-align:left; font-weight:700;
  color:var(--accent2); font-size:12px; letter-spacing:.04em;
  white-space:nowrap; cursor:pointer; user-select:none;
  transition:.15s;
}}
.data-table th:hover {{ color:#fff; background:rgba(34,211,238,.08); }}
.data-table th.sort-asc::after  {{ content:" ▲"; font-size:10px; }}
.data-table th.sort-desc::after {{ content:" ▼"; font-size:10px; }}
.data-table td {{
  padding:8px 16px; border-bottom:1px solid var(--border2);
  vertical-align:top; white-space:nowrap;
}}
.data-table td.wrap {{ white-space:normal; }}
.data-table tbody tr:hover td {{ background:rgba(124,111,255,.06); }}
.data-table tbody tr:last-child td {{ border-bottom:none; }}

/* ── Disclaimer box ────────────────────────────────────────────────── */
.disclaimer-box {{
  background: linear-gradient(135deg, #150800 0%, #1a0e00 100%);
  border:1px solid var(--orange); border-radius:var(--radius);
  padding:18px 22px; margin:24px 0; font-size:12.5px; color:#c0a060;
  line-height:1.8;
}}
.disclaimer-box h4 {{
  color:var(--orange); font-size:13px; margin-bottom:8px;
  display:flex; align-items:center; gap:6px;
}}
.disclaimer-box p {{ margin:0; }}

/* ── Footer ────────────────────────────────────────────────────────── */
.report-footer {{
  max-width:1100px; margin:0 auto;
  padding:20px 24px 32px;
  border-top:1px solid var(--border);
  display:flex; align-items:center; justify-content:space-between;
  gap:16px; flex-wrap:wrap;
}}
.footer-brand {{ display:flex; align-items:center; gap:10px; }}
.footer-brand img {{ height:24px; border-radius:4px; background:#fff; padding:1px 3px; }}
.footer-text {{ font-size:11.5px; color:var(--dim); }}
.footer-right {{ font-size:11px; color:#444460; text-align:right; }}

/* ── Print styles ──────────────────────────────────────────────────── */
@media print {{
  @page {{ size:A4; margin:12mm 15mm; }}

  /* Force colour output for all backgrounds */
  * {{ -webkit-print-color-adjust:exact !important; print-color-adjust:exact !important; }}

  :root {{
    --bg:#ffffff; --surface:#f4f4fb; --card:#f8f8fc;
    --border:#c8c8e0; --border2:#dcdcf0;
    --text:#1a1a2e; --dim:#555570;
    --accent:#5856d6; --accent2:#0060df;
    --green:#16a34a; --red:#dc2626;
    --yellow:#d97706; --purple:#7c3aed;
    --orange:#c2610c;
  }}

  /* Hide interactive / nav elements */
  .topbar,.toc-drawer,.toc-overlay,.summary-pills,
  .btn,.section-toggle,.search-wrap,.topbar-search,.srch-clear {{ display:none !important; }}

  /* Body — kill the min-height that pushes content to page 2 */
  body {{ min-height:0 !important; font-size:11px; background:#fff !important; }}

  /* Layout */
  .page-layout {{ padding:0 !important; max-width:100% !important; }}

  /* Report header */
  .report-header {{
    background: linear-gradient(160deg,#eeeef8 0%,#f0f0fc 60%,#ebebf5 100%) !important;
    padding:16px 20px !important; border-bottom:2px solid #c0c0e0 !important;
  }}
  .report-header-inner {{ max-width:100% !important; }}
  .report-title {{
    font-size:20px !important;
    background:none !important;
    -webkit-background-clip:unset !important; background-clip:unset !important;
    -webkit-text-fill-color:#1a1a2e !important; color:#1a1a2e !important;
  }}
  .brand-name {{
    background:none !important;
    -webkit-text-fill-color:#5856d6 !important; color:#5856d6 !important;
  }}
  .meta-pill {{ background:#ebebf8 !important; border-color:#c8c8e0 !important; }}
  .report-badge {{ border:1px solid currentColor !important; }}

  /* Summary strip */
  .summary-strip {{ padding:0 !important; max-width:100% !important; margin:0 0 10px !important; }}
  .summary-inner {{
    background:#ebebf8 !important; border-color:#c0c0e0 !important;
    padding:14px 18px !important; margin-bottom:10px !important;
  }}
  .summary-label {{ color:#555580 !important; }}
  .summary-label::after {{ background:#c8c8e0 !important; }}
  .summary-teaser {{ color:#1a1a3a !important; border-top-color:#d0d0e8 !important; }}
  .stat-chip .stat-val {{
    background:none !important;
    -webkit-text-fill-color:#5856d6 !important; color:#5856d6 !important;
  }}
  .stat-chip .stat-lbl {{ color:#555580 !important; }}

  /* Section cards */
  .section {{
    break-inside: auto !important; overflow: visible !important;
    box-shadow: none !important;
    background: #f8f8fc !important; border-color: #d0d0e8 !important;
    margin-bottom: 10px !important;
  }}
  .section-header {{
    break-after: avoid !important;
    background: #ebebf8 !important; color: #0060df !important;
    cursor: default !important;
  }}
  .section.collapsed .section-body {{ display:block !important; }}
  .section-body {{
    font-size:11px !important; padding:12px 16px !important;
    color:#1a1a2e !important; overflow: visible !important;
  }}
  .section-body h2 {{ color:#5856d6 !important; break-after: avoid !important; }}
  .section-body h3 {{ color:#7c3aed !important; break-after: avoid !important; }}
  .section-body strong {{ color:#0060df !important; }}

  /* Tables */
  .tbl-wrap {{ overflow:visible !important; border:none !important; }}
  .data-table {{
    width:100% !important; font-size:10px !important;
    table-layout:auto !important;
  }}
  .data-table td {{ white-space:normal !important; }}
  .data-table thead tr {{ background:#e8e8f8 !important; }}
  .data-table th {{ color:#5856d6 !important; font-size:10px !important; white-space:normal !important; }}

  /* Disclaimer & footer */
  .disclaimer-box {{
    background:#fff8ef !important; border-color:#c2610c !important;
    break-inside:avoid;
  }}
  .disclaimer-box h4 {{ color:#c2610c !important; }}
  .disclaimer-box p {{ color:#7a4010 !important; }}
  .report-footer {{
    border-top:1px solid #d0d0e0 !important;
    max-width:100% !important;
  }}
  .footer-text {{ color:#555570 !important; }}
  .footer-right {{ color:#777790 !important; }}

  /* Ensure signal colours stay visible */
  .sig-buy  {{ color:#16a34a !important; }}
  .sig-sell {{ color:#dc2626 !important; }}
  .sig-hold {{ color:#d97706 !important; }}

  /* Light-mode versions of the new block styles */
  .part-divider {{ color:#5856d6 !important; }}
  .part-divider::before, .part-divider::after {{
    background: linear-gradient(90deg, transparent, #c8c8e0 30%, #c8c8e0 70%, transparent) !important;
  }}
  .arrow-header {{
    background: linear-gradient(90deg, rgba(88,86,214,.10), rgba(88,86,214,0)) !important;
    border-left-color:#5856d6 !important; color:#5856d6 !important;
  }}
  .kv-list {{
    background:#f4f4fb !important; border-color:#dcdcf0 !important;
  }}
  .kv-list dt {{ color:#555570 !important; }}
  .kv-list dd {{ color:#1a1a2e !important; }}
}}
</style>
</head>
<body>

<!-- ── Right-side TOC drawer ──────────────────────────────────────────────── -->
<div class="toc-overlay" id="toc-overlay" onclick="closeTOC()"></div>
<div class="toc-drawer" id="toc-drawer">
  <div class="toc-drawer-header">
    <h4>📑 Contents</h4>
    <button class="toc-close" onclick="closeTOC()">✕</button>
  </div>
  <div class="toc-body" id="toc-links"></div>
</div>

<!-- ── Top navigation bar ─────────────────────────────────────────────────── -->
<div class="topbar">
  <div class="topbar-brand">
    {logo_img_nav}
    <span class="brand-name">Agent Adda</span>
    <span style="color:var(--dim);font-size:12px;">NSE Market Intelligence Terminal</span>
  </div>
  <div class="topbar-actions">
    <div class="search-wrap">
      <input class="topbar-search" id="srch" type="search" placeholder="🔍 Search report…"
             oninput="filterContent(this.value)" onkeydown="if(event.key==='Escape'){{clearSearch();}}" autocomplete="off">
      <button class="srch-clear" id="srch-clear" onclick="clearSearch()" title="Clear search">✕</button>
    </div>
    <button class="btn btn-outline" onclick="toggleAll()">Collapse All</button>
    <button class="btn btn-outline" onclick="toggleTOC()" title="Table of Contents">📑 Contents</button>
    <button class="btn btn-primary" onclick="window.print()">🖨 Print / PDF</button>
  </div>
</div>

<!-- ── Report header ───────────────────────────────────────────────────────── -->
<div class="report-header">
  <div class="report-header-inner">
    <div class="report-header-left">
      <div class="report-title">{title}</div>
      <div class="report-meta">
        <span class="report-badge {badge_class}">{badge_label}</span>
        {symbol_meta}
        <span class="meta-pill">📅 {date}</span>
        <span class="meta-pill">⏱ {time} IST</span>
        <span class="meta-pill">🤖 Agent Adda</span>
      </div>
    </div>
    <div class="report-logo-block">
      {logo_img_header}
      <span class="logo-sub">NSE MARKET INTELLIGENCE</span>
    </div>
  </div>
</div>

<!-- ── Summary strip ───────────────────────────────────────────────────────── -->
<div class="summary-strip">
  <div class="summary-inner" id="summary-inner">
    <div class="summary-label">Quick Navigation</div>
    <div class="summary-stats" id="summary-stats"></div>
    <div class="summary-pills" id="summary-pills">
      <span style="color:var(--dim);font-size:12px;">Loading sections…</span>
    </div>
    <div class="summary-teaser" id="summary-teaser"></div>
  </div>
</div>

<!-- ── Main layout ─────────────────────────────────────────────────────────── -->
<div class="page-layout">
  <div class="content-area">

    <!-- Report body -->
    <div class="section" id="main-section">
      <div class="section-header" onclick="toggleSection(this.parentElement)">
        <span>📑 Analysis</span>
        <span class="section-toggle">▾</span>
      </div>
      <div class="section-body" id="report-body">
{content_html}
      </div>
    </div>

    <!-- Disclaimer box -->
    <div class="disclaimer-box">
      <h4>⚠️ Important Disclaimer</h4>
      <p>
        This report has been generated by <strong>Agent Adda</strong>, an AI-powered NSE market research terminal,
        using publicly available market data, news, and analytical models.
        <strong>This is NOT investment advice.</strong>
        The information contained herein is provided solely for educational and informational purposes.
        Agent Adda, its creators, and contributors are <strong>not registered investment advisors</strong>
        and make no representation as to the accuracy, completeness, or timeliness of this information.
        Equity investments are subject to market risk. You may lose some or all of your invested capital.
        <strong>Always consult a SEBI-registered research analyst or investment advisor</strong> before
        making any investment decisions. Past performance of any stock is not a guarantee of future returns.
        NSE/BSE data is sourced from public feeds and may have delays.
      </p>
    </div>

  </div><!-- end content-area -->
</div><!-- end page-layout -->

<!-- ── Footer ─────────────────────────────────────────────────────────────── -->
<div class="report-footer">
  <div class="footer-brand">
    {logo_img_footer}
    <span class="footer-text">
      <strong>Agent Adda</strong> · NSE Market Intelligence Terminal<br>
      Generated {date} · {time} IST
    </span>
  </div>
  <div class="footer-right">
    For research &amp; educational use only.<br>
    Not investment advice · Subject to market risk.
  </div>
</div>

<script>
/* ── Live search ─────────────────────────────────────────────────── */
(function() {{
  var _rx = null;

  /* Walk DOM tree, skip SCRIPT/STYLE/MARK, wrap text matches in <mark> */
  function _walk(node, rx) {{
    if (node.nodeType === 3) {{                       // TEXT_NODE
      var t = node.nodeValue;
      if (!rx.test(t)) return;
      rx.lastIndex = 0;
      var frag = document.createDocumentFragment();
      var last = 0, m;
      while ((m = rx.exec(t)) !== null) {{
        if (m.index > last) frag.appendChild(document.createTextNode(t.slice(last, m.index)));
        var mk = document.createElement('mark');
        mk.className = 'srch-hl';
        mk.appendChild(document.createTextNode(m[0]));
        frag.appendChild(mk);
        last = rx.lastIndex;
        if (m[0].length === 0) {{ rx.lastIndex++; break; }}
      }}
      if (last < t.length) frag.appendChild(document.createTextNode(t.slice(last)));
      node.parentNode.replaceChild(frag, node);
      return;
    }}
    if (node.nodeType !== 1) return;
    var tag = node.tagName;
    if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'MARK') return;
    /* clone children list before walking — replaceChild changes live list */
    var kids = Array.from(node.childNodes);
    for (var i = 0; i < kids.length; i++) _walk(kids[i], rx);
  }}

  function _clearHL(root) {{
    root.querySelectorAll('mark.srch-hl').forEach(function(mk) {{
      var parent = mk.parentNode;
      while (mk.firstChild) parent.insertBefore(mk.firstChild, mk);
      parent.removeChild(mk);
      parent.normalize();
    }});
  }}

  window.filterContent = function(q) {{
    var body = document.getElementById('report-body');
    var btn  = document.getElementById('srch-clear');
    if (!body) return;
    _clearHL(body);
    if (!q || !q.trim()) {{
      _rx = null;
      if (btn) btn.classList.remove('visible');
      /* restore collapsed state */
      document.querySelectorAll('.section.srch-expanded').forEach(function(s) {{
        s.classList.remove('srch-expanded'); s.classList.add('collapsed');
      }});
      return;
    }}
    if (btn) btn.classList.add('visible');
    var escaped = q.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&');
    _rx = new RegExp(escaped, 'gi');
    _walk(body, _rx);
    /* expand sections that contain highlights */
    document.querySelectorAll('.section').forEach(function(sec) {{
      if (sec.querySelector('mark.srch-hl')) {{
        if (sec.classList.contains('collapsed')) {{
          sec.classList.remove('collapsed');
          sec.classList.add('srch-expanded');
        }}
      }}
    }});
    /* scroll to first match */
    var first = body.querySelector('mark.srch-hl');
    if (first) first.scrollIntoView({{behavior:'smooth', block:'center'}});
  }};

  window.clearSearch = function() {{
    var inp = document.getElementById('srch');
    if (inp) {{ inp.value = ''; inp.dispatchEvent(new Event('input')); inp.focus(); }}
  }};
}})();

/* ── TOC drawer ──────────────────────────────────────────────────── */
function openTOC()  {{ document.getElementById('toc-drawer').classList.add('open'); document.getElementById('toc-overlay').classList.add('open'); }}
function closeTOC() {{ document.getElementById('toc-drawer').classList.remove('open'); document.getElementById('toc-overlay').classList.remove('open'); }}
function toggleTOC(){{ document.getElementById('toc-drawer').classList.contains('open') ? closeTOC() : openTOC(); }}

(function buildTOC() {{
  const toc  = document.getElementById('toc-links');
  const body = document.getElementById('report-body');
  if (!toc || !body) return;
  const hdrs = body.querySelectorAll('h1,h2,h3,h4');
  if (!hdrs.length) return;
  hdrs.forEach(h => {{
    const a = document.createElement('a');
    a.href = '#' + (h.id || '');
    a.className = 'toc-' + h.tagName.toLowerCase();
    const num = h.tagName === 'H2' ? (h.textContent.match(/^(\\d+)\\./) || ['',''])[1] : '';
    if (num) {{
      const ns = document.createElement('span');
      ns.className = 'toc-section-num'; ns.textContent = num + '.';
      a.appendChild(ns);
    }}
    a.appendChild(document.createTextNode(
      num ? h.textContent.replace(/^\\d+\\.\\s*/, '') : h.textContent
    ));
    toc.appendChild(a);
  }});
  // Scroll spy
  const obs = new IntersectionObserver(entries => {{
    entries.forEach(e => {{
      if (e.isIntersecting) {{
        toc.querySelectorAll('a').forEach(a => a.classList.remove('active'));
        const active = toc.querySelector('a[href="#' + e.target.id + '"]');
        if (active) {{ active.classList.add('active'); active.scrollIntoView({{block:'nearest'}}); }}
      }}
    }});
  }}, {{ rootMargin:'-15% 0px -65% 0px' }});
  hdrs.forEach(h => {{ if (h.id) obs.observe(h); }});
}})();

/* ── Summary strip builder ───────────────────────────────────────── */
(function buildSummary() {{
  const body    = document.getElementById('report-body');
  const pills   = document.getElementById('summary-pills');
  const teaser  = document.getElementById('summary-teaser');
  const stats   = document.getElementById('summary-stats');
  if (!body || !pills) return;

  const h2s   = Array.from(body.querySelectorAll('h2'));
  const tables = body.querySelectorAll('table');
  const paras  = body.querySelectorAll('p');

  // Stats chips
  if (h2s.length) {{
    stats.innerHTML =
      '<div class="stat-chip"><span class="stat-val">' + h2s.length + '</span><span class="stat-lbl">Sections</span></div>' +
      '<div class="stat-chip"><span class="stat-val">' + tables.length + '</span><span class="stat-lbl">Data Tables</span></div>' +
      '<div class="stat-chip"><span class="stat-val">' + paras.length + '</span><span class="stat-lbl">Insights</span></div>';
  }}

  // Section pills
  pills.innerHTML = '';
  h2s.forEach((h, i) => {{
    const a = document.createElement('a');
    a.className = 'summary-pill';
    a.href = '#' + (h.id || '');
    const numMatch = h.textContent.match(/^(\\d+)\\.\\s*(.*)/);
    const num  = numMatch ? numMatch[1] : String(i+1);
    const text = numMatch ? numMatch[2].trim() : h.textContent.trim();
    a.innerHTML = '<span class="pill-num">' + num + '</span>' + text;
    pills.appendChild(a);
  }});
  if (!h2s.length) pills.innerHTML = '';

  // Teaser: first real paragraph from report-body
  for (var p of paras) {{
    var txt = p.textContent.trim();
    if (txt.length > 60) {{
      teaser.textContent = txt.length > 280 ? txt.slice(0, 280) + '…' : txt;
      break;
    }}
  }}
}})();

/* ── Section collapse ────────────────────────────────────────────── */
function toggleSection(el) {{ el.classList.toggle('collapsed'); }}
function toggleAll() {{
  const sections = document.querySelectorAll('.section');
  const anyOpen  = [...sections].some(s => !s.classList.contains('collapsed'));
  sections.forEach(s => anyOpen ? s.classList.add('collapsed') : s.classList.remove('collapsed'));
  document.querySelectorAll('.btn-outline')[0].textContent = anyOpen ? 'Expand All' : 'Collapse All';
}}

/* ── Table sort ──────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {{
  document.querySelectorAll('.data-table[data-sortable]').forEach(tbl => {{
    tbl.querySelectorAll('th').forEach((th, ci) => {{
      th.addEventListener('click', () => {{
        const asc = !th.classList.contains('sort-asc');
        tbl.querySelectorAll('th').forEach(t => t.classList.remove('sort-asc','sort-desc'));
        th.classList.toggle('sort-asc', asc);
        th.classList.toggle('sort-desc', !asc);
        const tbody = tbl.querySelector('tbody');
        const rows  = [...tbody.querySelectorAll('tr')];
        rows.sort((a,b) => {{
          const av = a.cells[ci]?.textContent.trim() || '';
          const bv = b.cells[ci]?.textContent.trim() || '';
          const an = parseFloat(av.replace(/[^\\d.-]/g,''));
          const bn = parseFloat(bv.replace(/[^\\d.-]/g,''));
          if (!isNaN(an) && !isNaN(bn)) return asc ? an-bn : bn-an;
          return asc ? av.localeCompare(bv) : bv.localeCompare(av);
        }});
        rows.forEach(r => tbody.appendChild(r));
      }});
    }});
  }});

  /* Show search bar only for multi-stock / tabular reports:
     reveal if report-body contains ≥2 tables OR ≥5 sections */
  const body = document.getElementById('report-body');
  if (body) {{
    const tables   = body.querySelectorAll('table').length;
    const sections = body.querySelectorAll('.section').length;
    if (tables >= 2 || sections >= 5) {{
      const wrap = document.querySelector('.search-wrap');
      if (wrap) wrap.classList.add('active');
    }}
  }}
}});
</script>
</body>
</html>'''


# ─────────────────────────────────────────────────────────────────────────────
# Core report generation
# ─────────────────────────────────────────────────────────────────────────────

# Prebuilt report type definitions — maps type to (title_template, badge_class, sections)
REPORT_TYPES = {
    "technical": {
        "title": "{symbol} — Technical Analysis Report",
        "badge": "badge-technical",
        "badge_label": "TECHNICAL",
        "sections": [
            "Price Action & Trend", "Key Levels (Support/Resistance)",
            "Momentum Indicators (RSI, MACD, Stochastic)",
            "Volume Analysis", "Chart Patterns", "Stage Analysis",
            "Trading Setup & Levels",
        ],
    },
    "fundamental": {
        "title": "{symbol} — Fundamental Analysis Report",
        "badge": "badge-fundamental",
        "badge_label": "FUNDAMENTAL",
        "sections": [
            "Company Overview", "Revenue & Profitability",
            "Balance Sheet Strength", "Cash Flow Analysis",
            "Valuation Metrics", "Peer Comparison",
            "Management Quality", "Investment Thesis",
        ],
    },
    "forensic": {
        "title": "{symbol} — Forensic Accounting Report",
        "badge": "badge-forensic",
        "badge_label": "FORENSIC",
        "sections": [
            "Beneish M-Score (Earnings Manipulation)",
            "Piotroski F-Score (Financial Strength)",
            "Altman Z-Score (Bankruptcy Risk)",
            "Cash Flow vs Earnings Quality",
            "Red Flags & Anomalies", "Governance & Audit",
            "Verdict & Risk Rating",
        ],
    },
    "research": {
        "title": "{symbol} — Comprehensive Research Report",
        "badge": "badge-research",
        "badge_label": "RESEARCH",
        "sections": [
            "Executive Summary & Master Scorecard",
            "Company Overview",
            "Stage Analysis & Technical Position",
            "CANSLIM Analysis (Full 7-Criteria)",
            "Minervini Trend Template Score",
            "P&L Analysis — Quarterly & YoY",
            "Balance Sheet — Quarterly & YoY",
            "Profitability & Efficiency (ROCE, ROE, Margins)",
            "Promoter & Institutional Holding",
            "Forensic Health (Beneish, Piotroski, Altman — Full Scores)",
            "Concall Highlights & Management Commentary",
            "Credit Ratings & Analyst Targets",
            "Investor Sentiment & News Catalysts",
            "Sector Context & Relative Strength",
            "Risk Factors",
            "Investment Verdict",
        ],
    },
    "intraday": {
        "title": "{symbol} — Intraday Analysis Report",
        "badge": "badge-intraday",
        "badge_label": "INTRADAY",
        "sections": [
            "Intraday Price Action", "Volume Profile",
            "VWAP & Levels", "Momentum (5m/15m timeframes)",
            "Options Activity (if F&O)", "Sector Context",
            "Trade Setup & Risk",
        ],
    },
    "canslim": {
        "title": "{symbol} — CANSLIM Quality Report",
        "badge": "badge-canslim",
        "badge_label": "CANSLIM",
        "sections": [
            "C — Current Quarterly Earnings",
            "A — Annual Earnings Growth",
            "N — New Products/Management/Price Highs",
            "S — Supply & Demand (Volume/Float)",
            "L — Leader or Laggard (RS Rating)",
            "I — Institutional Sponsorship",
            "M — Market Direction",
            "Final CANSLIM Score & Verdict",
        ],
    },
    "ric": {
        "title": "{symbol} — RIC Investigation Report",
        "badge": "badge-ric",
        "badge_label": "RIC",
        "sections": [
            "Investigation Context", "Evidence Gathering",
            "Key Findings", "Risk Assessment",
            "Conclusions & Recommendations",
        ],
    },
    "sector": {
        "title": "{sector} — Sector Analysis Report",
        "badge": "badge-sector",
        "badge_label": "SECTOR",
        "sections": [
            "Sector Overview & Macro Context",
            "Rotation Status & Relative Strength",
            "Top Performers & Laggards",
            "Technical Breadth",
            "Key Stocks & Catalysts",
            "Outlook & Positioning",
        ],
    },
    "sector-rotation": {
        "title": "NSE Sector Rotation Tracker — {date}",
        "badge": "badge-sector-rotation",
        "badge_label": "SECTOR ROTATION",
        "sections": [
            "Market Overview", "Sector Rankings (by Stage 2 breadth)",
            "Rotation Leaders vs Laggards",
            "Stage 2 Breadth by Sector",
            "Sector RS & Momentum", "Strategy & Positioning",
        ],
    },
    "stage2": {
        "title": "Stage 2 Tracker — NSE Universe — {date}",
        "badge": "badge-stage2",
        "badge_label": "STAGE 2 TRACKER",
        "sections": [
            "Market Breadth Snapshot",
            "New Stage 2 Entrants (last 14 days)",
            "Stage 2 Exits (last 7 days)",
            "Top Stage 2 Leaders by Investment Score",
            "Stage 2 by Sector", "Watchlist Candidates",
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Data-direct report builders — pull from DB, no LLM required
# ─────────────────────────────────────────────────────────────────────────────

def _db_conn_reports():
    """Open sector rotation DB connection."""
    import sqlite3
    db = ROOT / "data" / "sector_rotation_tracker.db"
    if not db.exists():
        raise FileNotFoundError(f"DB not found: {db}")
    return sqlite3.connect(db), str(db)


def _latest_snap(conn) -> str:
    row = conn.execute("SELECT MAX(snapshot_date) FROM stage_snapshots").fetchone()
    return row[0] if row and row[0] else "N/A"


def _fmt_pct(v, decimals=1) -> str:
    try:
        f = float(v)
        sign = "+" if f > 0 else ""
        return f"{sign}{f:.{decimals}f}%"
    except (TypeError, ValueError):
        return "—"


def _build_sector_rotation_content() -> str:
    """Build Sector Rotation report content directly from DB."""
    import sqlite3
    conn, _ = _db_conn_reports()
    snap = _latest_snap(conn)
    now  = datetime.datetime.now()

    # ── Sector summary ──────────────────────────────────────────────────────
    sector_rows = conn.execute("""
        WITH market AS (
            SELECT AVG(CAST(change_1m_pct AS FLOAT)) AS avg_1m
            FROM stage_snapshots
            WHERE snapshot_date=?
        )
        SELECT COALESCE(NULLIF(TRIM(sector), ''), 'Other')              AS sector,
               COUNT(*)                                                AS total,
               SUM(CASE WHEN stage='STAGE_2' THEN 1 ELSE 0 END)       AS s2,
               SUM(CASE WHEN stage='STAGE_1' THEN 1 ELSE 0 END)       AS s1,
               SUM(CASE WHEN stage='STAGE_3' OR stage='STAGE_4'
                           THEN 1 ELSE 0 END)                           AS s34,
                ROUND(AVG(
                    CASE
                        WHEN relative_strength IS NOT NULL
                             THEN CAST(relative_strength AS FLOAT) * 100
                        WHEN change_1m_pct IS NOT NULL
                             THEN CAST(change_1m_pct AS FLOAT) - market.avg_1m
                    END
                ),1)                                                     AS avg_rs,
                ROUND(AVG(CAST(change_1m_pct AS FLOAT)),1)             AS avg_1m,
                ROUND(AVG(CAST(change_1w_pct AS FLOAT)),1)             AS avg_1w,
                SUM(CASE WHEN trading_signal IN ('STRONG_BUY','BUY')
                           THEN 1 ELSE 0 END)                           AS buys
        FROM stage_snapshots, market
        WHERE snapshot_date=?
        GROUP BY COALESCE(NULLIF(TRIM(sector), ''), 'Other')
        ORDER BY s2 DESC, avg_rs DESC
    """, (snap, snap)).fetchall()

    # ── Market-wide breadth ─────────────────────────────────────────────────
    breadth = conn.execute("""
        SELECT
            COUNT(*)                                                    AS total,
            SUM(CASE WHEN stage='STAGE_2' THEN 1 ELSE 0 END)          AS s2,
            SUM(CASE WHEN stage='STAGE_1' THEN 1 ELSE 0 END)          AS s1,
            SUM(CASE WHEN stage IN ('STAGE_3','STAGE_4') THEN 1 ELSE 0 END) AS s34,
            ROUND(AVG(CAST(change_1m_pct AS FLOAT)),1)                AS avg_1m,
            SUM(CASE WHEN trading_signal IN ('STRONG_BUY','BUY')
                       THEN 1 ELSE 0 END)                              AS buys
        FROM stage_snapshots WHERE snapshot_date=?
    """, (snap,)).fetchone()

    total, s2_all, s1_all, s34_all, mkt_1m, buys_all = breadth
    s2_pct = round(s2_all / total * 100, 1) if total else 0
    bull_pct = round((s2_all + s1_all) / total * 100, 1) if total else 0

    # ── Recent stage changes ────────────────────────────────────────────────
    changes = conn.execute("""
        SELECT change_type, COUNT(*) FROM stage_changes
        WHERE change_date >= date(?, '-7 days')
        GROUP BY change_type
    """, (snap,)).fetchall()
    chg = dict(changes)

    # ── New Stage 2 entrants ────────────────────────────────────────────────
    new_s2 = conn.execute("""
        WITH ranked_changes AS (
            SELECT c.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY c.symbol
                       ORDER BY c.change_date DESC, c.rowid DESC
                   ) AS rn
            FROM stage_changes c
            WHERE c.stage_now='STAGE_2' AND c.stage_prev != 'STAGE_2'
              AND c.change_date >= date(?, '-14 days')
        )
        SELECT c.symbol, c.company_name, c.price_now, c.live_price,
               s.sector, s.rsi, s.investment_score, c.change_date
        FROM ranked_changes c
        JOIN stage_snapshots s ON c.symbol=s.symbol AND s.snapshot_date=?
        WHERE c.rn=1
        ORDER BY c.change_date DESC, s.investment_score DESC
    """, (snap, snap)).fetchall()

    # ── Top 15 Stage 2 leaders ──────────────────────────────────────────────
    leaders = conn.execute("""
        SELECT symbol, company_name, sector, price, rsi,
               relative_strength, change_1m_pct, investment_score, trading_signal
        FROM stage_snapshots
        WHERE snapshot_date=? AND stage='STAGE_2'
        ORDER BY investment_score DESC
        LIMIT 15
    """, (snap,)).fetchall()

    conn.close()

    # ── Build Markdown ──────────────────────────────────────────────────────
    md = []
    md.append(f"# NSE Sector Rotation Tracker")
    md.append(f"**Data Snapshot:** {snap} · **Report Generated:** {now.strftime('%d %b %Y, %H:%M IST')}")
    md.append("")

    # Market breadth
    market_signal = "BULLISH" if s2_pct >= 40 else ("NEUTRAL" if s2_pct >= 25 else "BEARISH")
    md.append("## Market Overview")
    md.append(f"> **Market Regime: {market_signal}** — {s2_pct}% of NSE universe in Stage 2 uptrend")
    md.append("")
    md.append("| Metric | Value |")
    md.append("|---|---|")
    md.append(f"| Total Stocks in Universe | {total:,} |")
    md.append(f"| Stage 2 (Uptrend) | **{s2_all}** ({s2_pct}%) |")
    md.append(f"| Stage 1 (Basing) | {s1_all} ({round(s1_all/total*100,1) if total else 0}%) |")
    md.append(f"| Stage 3/4 (Decline) | {s34_all} ({round(s34_all/total*100,1) if total else 0}%) |")
    md.append(f"| Bullish Breadth (S1+S2) | {bull_pct}% |")
    md.append(f"| Avg 1M Market Return | {_fmt_pct(mkt_1m)} |")
    md.append(f"| BUY Signals Active | {buys_all} stocks |")
    md.append(f"| New Stage 2 Entrants (14d) | {len(new_s2)} |")
    md.append(f"| Stage 2 Exits (7d) | {chg.get('EXIT_STAGE2', 0)} |")
    md.append(f"| Stage Upgrades (7d) | {chg.get('STAGE_UP', 0)} |")
    md.append(f"| Stage Downgrades (7d) | {chg.get('STAGE_DOWN', 0)} |")
    md.append("")

    # Sector rankings
    md.append("## Sector Rankings — Stage 2 Breadth")
    md.append("")
    md.append("| Rank | Sector | Total | Stage 2 | S2 % | Avg RS | Avg 1M | BUY Signals | Signal |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for i, (sector, total_s, s2, s1, s34, avg_rs, avg_1m, avg_1w, buys) in enumerate(sector_rows, 1):
        s2_pct_s = round(s2 / total_s * 100, 0) if total_s else 0
        sig = "🟢 LEADING" if s2 >= 5 and avg_1m and avg_1m > 15 else (
              "🔵 NEUTRAL" if s2 >= 3 else "🔴 LAGGING")
        md.append(
            f"| {i} | {sector or 'Other'} | {total_s} | **{s2}** | {s2_pct_s:.0f}% | "
            f"{avg_rs or '—'} | {_fmt_pct(avg_1m)} | {buys} | {sig} |"
        )
    md.append("")

    # Leaders
    md.append("## Top Stage 2 Leaders (by Investment Score)")
    md.append("")
    md.append("| Symbol | Company | Sector | Price | RSI | 1M Chg | Inv. Score | Signal |")
    md.append("|---|---|---|---|---|---|---|---|")
    for sym, cname, sector, price, rsi, rs, chg1m, inv_score, sig in leaders:
        md.append(
            f"| **{sym}** | {(cname or '')[:28]} | {(sector or 'Other')[:22]} | "
            f"₹{price or '—'} | {rsi or '—'} | {_fmt_pct(chg1m)} | "
            f"{inv_score or '—'} | {sig or '—'} |"
        )
    md.append("")

    # New entrants
    if new_s2:
        md.append("## New Stage 2 Entrants (Last 14 Days)")
        md.append("*Stocks that recently crossed into Stage 2 — early opportunity zone*")
        md.append("")
        md.append("| Symbol | Company | Sector | Price | RSI | Inv. Score | Date Entered |")
        md.append("|---|---|---|---|---|---|---|")
        for sym, cname, price_now, live_px, sector, rsi, inv_score, chg_date in new_s2[:20]:
            md.append(
                f"| **{sym}** | {(cname or '')[:28]} | {(sector or 'Other')[:22]} | "
                f"₹{live_px or price_now or '—'} | {rsi or '—'} | {inv_score or '—'} | {chg_date} |"
            )
        md.append("")

    # Strategy
    md.append("## Strategy & Positioning")
    md.append("")
    if s2_pct >= 40:
        md.append("**Market is BULLISH.** Broad Stage 2 participation — favour long positions in leaders.")
        md.append("- Focus on sectors with highest S2 breadth and positive RS")
        md.append("- Buy new Stage 2 entrants on first pullback to 21/50 EMA")
        md.append("- Tighten stops on Stage 3 stocks — rotate into leaders")
    elif s2_pct >= 25:
        md.append("**Market is NEUTRAL.** Mixed breadth — be selective, buy only the best setups.")
        md.append("- Focus on sector leaders only; avoid lagging sectors")
        md.append("- Reduce position sizes; keep more cash")
        md.append("- Watch for breadth expansion for confirmation")
    else:
        md.append("**Market is BEARISH.** Broad Stage 2 weakness — defensive posture.")
        md.append("- Reduce equity exposure significantly")
        md.append("- Only consider highest-conviction Stage 2 leaders")
        md.append("- Wait for breadth recovery before adding new positions")
    md.append("")
    md.append("---")
    md.append("*Sector Rotation data sourced from NSE EOD DB snapshot. Stage analysis uses Weinstein Stage methodology.*")

    return "\n".join(md)


def _build_stage2_content() -> str:
    """Build Stage 2 Tracker report content directly from DB."""
    conn, _ = _db_conn_reports()
    snap = _latest_snap(conn)
    now  = datetime.datetime.now()

    # ── Breadth snapshot ────────────────────────────────────────────────────
    breadth = conn.execute("""
        SELECT
            COUNT(*)                                                    AS total,
            SUM(CASE WHEN stage='STAGE_2' THEN 1 ELSE 0 END)          AS s2,
            SUM(CASE WHEN stage='STAGE_1' THEN 1 ELSE 0 END)          AS s1,
            SUM(CASE WHEN stage='STAGE_2' AND supertrend_state='BULLISH'
                       THEN 1 ELSE 0 END)                              AS s2_bull,
            SUM(CASE WHEN stage='STAGE_2' AND rsi BETWEEN 50 AND 70
                       THEN 1 ELSE 0 END)                              AS s2_healthy_rsi,
            SUM(CASE WHEN stage='STAGE_2' AND trading_signal IN ('STRONG_BUY','BUY')
                       THEN 1 ELSE 0 END)                              AS s2_buys,
            ROUND(AVG(CASE WHEN stage='STAGE_2'
                           THEN CAST(change_1m_pct AS FLOAT) END),1)  AS s2_avg_1m
        FROM stage_snapshots WHERE snapshot_date=?
    """, (snap,)).fetchone()

    total, s2_all, s1_all, s2_bull, s2_healthy, s2_buys, s2_avg1m = breadth

    # ── Stage 2 by sector ───────────────────────────────────────────────────
    by_sector = conn.execute("""
        SELECT COALESCE(NULLIF(TRIM(sector), ''), 'Other')              AS sector,
               COUNT(*)                                                 AS s2_count,
               ROUND(AVG(CAST(investment_score AS FLOAT)),1)           AS avg_inv,
               ROUND(AVG(CAST(change_1m_pct AS FLOAT)),1)              AS avg_1m,
               ROUND(AVG(CAST(rsi AS FLOAT)),1)                        AS avg_rsi
        FROM stage_snapshots
        WHERE snapshot_date=? AND stage='STAGE_2'
        GROUP BY COALESCE(NULLIF(TRIM(sector), ''), 'Other')
        ORDER BY s2_count DESC, avg_inv DESC
    """, (snap,)).fetchall()

    # ── New entrants (last 14d) ─────────────────────────────────────────────
    new_s2 = conn.execute("""
        WITH ranked_changes AS (
            SELECT c.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY c.symbol
                       ORDER BY c.change_date DESC, c.rowid DESC
                   ) AS rn
            FROM stage_changes c
            WHERE c.stage_now='STAGE_2' AND c.stage_prev != 'STAGE_2'
              AND c.change_date >= date(?, '-14 days')
        )
        SELECT c.symbol, c.company_name, s.sector, s.price, s.rsi,
               s.investment_score, s.trading_signal, s.change_1m_pct,
               s.supertrend_state, c.change_date
        FROM ranked_changes c
        JOIN stage_snapshots s ON c.symbol=s.symbol AND s.snapshot_date=?
        WHERE c.rn=1
        ORDER BY s.investment_score DESC
    """, (snap, snap)).fetchall()

    # ── Stage 2 exits (last 7d) ─────────────────────────────────────────────
    exits = conn.execute("""
        WITH ranked_changes AS (
            SELECT c.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY c.symbol
                       ORDER BY c.change_date DESC, c.rowid DESC
                   ) AS rn
            FROM stage_changes c
            WHERE c.stage_prev='STAGE_2' AND c.stage_now != 'STAGE_2'
              AND c.change_date >= date(?, '-7 days')
        )
        SELECT c.symbol, c.company_name, c.price_now, c.price_prev,
               c.price_chg_pct, c.stage_now, c.change_date
        FROM ranked_changes c
        WHERE c.rn=1
        ORDER BY c.change_date DESC
    """, (snap,)).fetchall()

    # ── Top 30 Stage 2 leaders ──────────────────────────────────────────────
    leaders = conn.execute("""
        SELECT symbol, company_name, sector, price, rsi,
               change_1w_pct, change_1m_pct, investment_score,
               trading_signal, supertrend_state, minervini_score, can_slim_score
        FROM stage_snapshots
        WHERE snapshot_date=? AND stage='STAGE_2'
        ORDER BY investment_score DESC
        LIMIT 30
    """, (snap,)).fetchall()

    # ── VCP/Tight setups ───────────────────────────────────────────────────
    vcp_setups = conn.execute("""
        SELECT symbol, company_name, sector, price, rsi, change_1w_pct, investment_score
        FROM stage_snapshots
        WHERE snapshot_date=? AND stage='STAGE_2'
          AND supertrend_state='BULLISH'
          AND ABS(COALESCE(change_1w_pct, 0)) < 2.0
          AND COALESCE(rsi, 0) BETWEEN 45 AND 65
        ORDER BY investment_score DESC
        LIMIT 20
    """, (snap,)).fetchall()

    conn.close()

    # ── Build Markdown ──────────────────────────────────────────────────────
    s2_pct = round(s2_all / total * 100, 1) if total else 0
    market_signal = "BULLISH" if s2_pct >= 40 else ("NEUTRAL" if s2_pct >= 25 else "BEARISH")

    md = []
    md.append("# Stage 2 Universe Tracker — NSE")
    md.append(f"**Data Snapshot:** {snap} · **Generated:** {now.strftime('%d %b %Y, %H:%M IST')}")
    md.append("")

    # Breadth
    md.append("## Market Breadth Snapshot")
    md.append(f"> **Market Regime: {market_signal}** — {s2_all} stocks ({s2_pct}%) in confirmed Stage 2 uptrend")
    md.append("")
    md.append("| Metric | Count | % of Universe |")
    md.append("|---|---|---|")
    md.append(f"| Total Universe | {total:,} | 100% |")
    md.append(f"| **Stage 2 (Uptrend)** | **{s2_all}** | **{s2_pct}%** |")
    md.append(f"| Stage 1 (Basing) | {s1_all} | {round(s1_all/total*100,1) if total else 0}% |")
    md.append(f"| S2 + Supertrend BULLISH | {s2_bull} | {round(s2_bull/s2_all*100,1) if s2_all else 0}% of S2 |")
    md.append(f"| S2 with Healthy RSI (50–70) | {s2_healthy} | {round(s2_healthy/s2_all*100,1) if s2_all else 0}% of S2 |")
    md.append(f"| S2 BUY Signals | {s2_buys} | {round(s2_buys/s2_all*100,1) if s2_all else 0}% of S2 |")
    md.append(f"| S2 Avg 1M Return | {_fmt_pct(s2_avg1m)} | — |")
    md.append(f"| New Entrants (14d) | {len(new_s2)} | — |")
    md.append(f"| Stage 2 Exits (7d) | {len(exits)} | — |")
    md.append("")

    # New entrants
    if new_s2:
        md.append(f"## New Stage 2 Entrants — Last 14 Days ({len(new_s2)} stocks)")
        md.append("*Freshly entered Stage 2 — highest opportunity zone for early positioning*")
        md.append("")
        md.append("| Symbol | Company | Sector | Price | RSI | 1M Chg | Inv. Score | Signal | ST | Entered |")
        md.append("|---|---|---|---|---|---|---|---|---|---|")
        for row in new_s2:
            sym, cname, sector, price, rsi, inv, sig, chg1m, st, date = row
            md.append(
                f"| **{sym}** | {(cname or '')[:26]} | {(sector or 'Other')[:20]} | "
                f"₹{price or '—'} | {rsi or '—'} | {_fmt_pct(chg1m)} | "
                f"{inv or '—'} | {sig or '—'} | {'✅' if st=='BULLISH' else '⚠️'} | {date} |"
            )
        md.append("")

    # Exits
    if exits:
        md.append(f"## Stage 2 Exits — Last 7 Days ({len(exits)} stocks)")
        md.append("*These stocks have left Stage 2 — review any holdings*")
        md.append("")
        md.append("| Symbol | Company | Now In | Price | Chg % | Date |")
        md.append("|---|---|---|---|---|---|")
        for sym, cname, price, prev_price, pct_chg, stage_now, date in exits:
            md.append(
                f"| **{sym}** | {(cname or '')[:28]} | {stage_now} | "
                f"₹{price or '—'} | {_fmt_pct(pct_chg)} | {date} |"
            )
        md.append("")

    # Top leaders
    md.append("## Top 30 Stage 2 Leaders — Ranked by Investment Score")
    md.append("")
    md.append("| # | Symbol | Company | Sector | Price | RSI | 1W | 1M | Score | Signal | ST | Minervini | CANSLIM |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, row in enumerate(leaders, 1):
        sym, cname, sector, price, rsi, chg1w, chg1m, inv, sig, st, min_s, can_s = row
        md.append(
            f"| {i} | **{sym}** | {(cname or '')[:22]} | {(sector or 'Other')[:18]} | "
            f"₹{price or '—'} | {rsi or '—'} | {_fmt_pct(chg1w)} | {_fmt_pct(chg1m)} | "
            f"**{inv or '—'}** | {sig or '—'} | {'✅' if st=='BULLISH' else '⚠️'} | "
            f"{min_s or '—'} | {can_s or '—'} |"
        )
    md.append("")

    # Stage 2 by sector
    md.append("## Stage 2 Stocks by Sector")
    md.append("")
    md.append("| Sector | S2 Count | Avg Inv. Score | Avg 1M Return | Avg RSI |")
    md.append("|---|---|---|---|---|")
    for sector, s2_cnt, avg_inv, avg_1m, avg_rsi in by_sector:
        md.append(
            f"| {sector or 'Other'} | **{s2_cnt}** | {avg_inv or '—'} | "
            f"{_fmt_pct(avg_1m)} | {avg_rsi or '—'} |"
        )
    md.append("")

    # VCP/tight setups
    if vcp_setups:
        md.append(f"## Watchlist Candidates — VCP / Tight Range Setups ({len(vcp_setups)})")
        md.append("*Stage 2 + Supertrend BULLISH + Weekly range < 2% + RSI 45–65 → coiled spring*")
        md.append("")
        md.append("| Symbol | Company | Sector | Price | RSI | 1W Range | Inv. Score |")
        md.append("|---|---|---|---|---|---|---|")
        for sym, cname, sector, price, rsi, chg1w, inv in vcp_setups:
            md.append(
                f"| **{sym}** | {(cname or '')[:26]} | {(sector or 'Other')[:20]} | "
                f"₹{price or '—'} | {rsi or '—'} | {_fmt_pct(chg1w)} | {inv or '—'} |"
            )
        md.append("")

    md.append("---")
    md.append(
        "*Stage 2 analysis uses William O'Neil / Stan Weinstein methodology. "
        "Investment scores are composite (technical + fundamental + CANSLIM + Minervini). "
        "Data from NSE EOD DB snapshot.*"
    )
    return "\n".join(md)


def generate_preset_report(
    report_type: str,
    output_format: str = "html",
) -> dict:
    """
    Generate a data-direct preset report (sector-rotation or stage2)
    without requiring LLM content. Pulls data straight from the DB.

    Args:
        report_type: 'sector-rotation' or 'stage2'
        output_format: 'html', 'pdf', or 'md'

    Returns:
        dict with keys: path, format, title, report_type, success, note
    """
    rt = report_type.lower().strip()
    if rt not in ("sector-rotation", "stage2"):
        raise ValueError(f"generate_preset_report only supports sector-rotation and stage2, got '{rt}'")

    try:
        if rt == "sector-rotation":
            content = _build_sector_rotation_content()
            sym     = "NSE"
        else:
            content = _build_stage2_content()
            sym     = "NSE"
    except FileNotFoundError as e:
        return {
            "path": None, "format": output_format, "title": rt,
            "report_type": rt, "symbol": "NSE", "success": False,
            "note": str(e),
        }

    type_config = REPORT_TYPES[rt]
    now   = datetime.datetime.now()
    title = type_config["title"].format(date=now.strftime("%d %b %Y"))

    ts       = now.strftime("%Y%m%d_%H%M%S")
    filename = f"NSE_{rt.replace('-','_')}_{ts}"

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if output_format == "md":
        result = _generate_md_report(content, title, rt, sym, filename, type_config)
    elif output_format == "pdf":
        result = _generate_pdf_report(content, title, rt, sym, filename, type_config)
    else:
        result = _generate_html_report(content, title, rt, sym, filename, type_config)

    result["note"] = "Generated directly from DB snapshot — no LLM required."
    return result


def generate_report(
    content: str,
    report_type: str = "research",
    symbol: str = "",
    output_format: str = "html",
    title: Optional[str] = None,
    filename: Optional[str] = None,
) -> dict:
    """
    Generate a report file from analysis content.

    Args:
        content: The analysis content (Markdown text from LLM output).
        report_type: One of: technical, fundamental, forensic, research,
                     intraday, canslim, ric, sector.
        symbol: Stock symbol or sector name for the report.
        output_format: 'html', 'pdf', or 'md'. Default 'html'.
        title: Custom title (overrides report_type template).
        filename: Custom filename (without extension). Auto-generated if omitted.

    Returns:
        dict with keys: path, format, title, report_type, symbol, success
    """
    # PG: Universal report generator — takes any content and wraps in styled output

    # Safety guard: if title was accidentally passed where output_format is expected
    _fmt_vals = {"html", "pdf", "md", "markdown"}
    if title and title.lower().strip() in _fmt_vals and output_format == "html":
        output_format, title = title, None

    output_format = output_format.lower().strip()
    if output_format not in ("html", "pdf", "md", "markdown"):
        output_format = "html"
    if output_format == "markdown":
        output_format = "md"

    report_type = report_type.lower().strip()
    type_config = REPORT_TYPES.get(report_type, REPORT_TYPES["research"])

    # Resolve title
    if not title:
        title = type_config["title"].format(
            symbol=symbol.upper() if symbol else "Market",
            sector=symbol if symbol else "Market",
        )

    # Generate filename
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if not filename:
        safe_sym = re.sub(r'[^a-zA-Z0-9_]', '', symbol) if symbol else "report"
        filename = f"{safe_sym}_{report_type}_{ts}"

    # Ensure output directory exists
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Clean content
    content = _strip_ansi(content)
    content = _strip_rich_markup(content)

    if report_type == "research" and symbol and "Market Intelligence Snapshot" not in content:
        pg_context = _build_postgres_research_context(symbol)
        if pg_context:
            content = f"{pg_context}\n\n---\n\n{content}"

    if output_format == "md":
        return _generate_md_report(content, title, report_type, symbol, filename, type_config)
    elif output_format == "pdf":
        return _generate_pdf_report(content, title, report_type, symbol, filename, type_config)
    else:
        return _generate_html_report(content, title, report_type, symbol, filename, type_config)


def _generate_md_report(
    content: str, title: str, report_type: str, symbol: str,
    filename: str, type_config: dict,
) -> dict:
    """Generate a Markdown report file."""
    now = datetime.datetime.now()
    dt  = now.strftime("%d %b %Y, %H:%M IST")
    header = (
        f"# {title}\n\n"
        f"> **⚠️ DISCLAIMER:** This report is for informational and research purposes only."
        f" It does **NOT** constitute investment advice, solicitation, or a recommendation to"
        f" buy/sell any security. Markets are subject to risk. Past performance is not"
        f" indicative of future results. Consult a SEBI-registered financial advisor before investing.\n\n"
        f"---\n\n"
        f"| Field | Value |\n"
        f"|---|---|\n"
        f"| **Report Type** | {type_config['badge_label']} |\n"
        f"| **Symbol** | {symbol.upper() if symbol else 'N/A'} |\n"
        f"| **Generated** | {dt} |\n"
        f"| **Engine** | Agent Adda — NSE Market Intelligence Terminal |\n\n"
        f"---\n\n"
    )
    footer = (
        f"\n\n---\n\n"
        f"## Disclaimer\n\n"
        f"This report was generated by **Agent Adda**, an AI-powered NSE market research terminal,"
        f" using publicly available market data, news, and analytical models."
        f" **This is NOT investment advice.** The information contained herein is provided solely"
        f" for educational and informational purposes. Agent Adda, its creators, and contributors"
        f" are **not registered investment advisors** and make no representation as to the accuracy,"
        f" completeness, or timeliness of this information. Equity investments are subject to market"
        f" risk. You may lose some or all of your invested capital. **Always consult a SEBI-registered"
        f" research analyst or investment advisor** before making any investment decisions.\n\n"
        f"*Generated {dt} · Agent Adda · NSE Market Intelligence Terminal*\n"
    )

    full_content = header + content + footer
    fpath = REPORTS_DIR / f"{filename}.md"

    with open(fpath, "w", encoding="utf-8") as f:
        f.write(full_content)

    return {
        "path": str(fpath),
        "format": "md",
        "title": title,
        "report_type": report_type,
        "symbol": symbol,
        "success": True,
    }


def _generate_html_report(
    content: str, title: str, report_type: str, symbol: str,
    filename: str, type_config: dict,
) -> dict:
    """Generate a styled HTML report file."""
    now = datetime.datetime.now()

    badge_class = type_config["badge"]
    badge_label = type_config["badge_label"]
    symbol_meta = f'<span class="meta-pill">📊 {symbol.upper()}</span>' if symbol else ''

    # Build logo img tags (inline base64 — fully self-contained)
    if _LOGO_DATA_URI:
        logo_img_nav    = f'<img src="{_LOGO_DATA_URI}" alt="Agent Adda">'
        logo_img_header = f'<img src="{_LOGO_DATA_URI}" alt="Agent Adda">'
        logo_img_footer = f'<img src="{_LOGO_DATA_URI}" alt="Agent Adda">'
    else:
        logo_img_nav = logo_img_header = logo_img_footer = ""

    # Convert markdown content to HTML
    content_html = _md_to_html_basic(content)

    html = REPORT_HTML_TEMPLATE.format(
        title           = _html.escape(title),
        badge_class     = badge_class,
        badge_label     = badge_label,
        date            = now.strftime("%d %b %Y"),
        time            = now.strftime("%H:%M"),
        symbol_meta     = symbol_meta,
        content_html    = content_html,
        logo_img_nav    = logo_img_nav,
        logo_img_header = logo_img_header,
        logo_img_footer = logo_img_footer,
    )

    fpath = REPORTS_DIR / f"{filename}.html"
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(html)

    return {
        "path": str(fpath),
        "format": "html",
        "title": title,
        "report_type": report_type,
        "symbol": symbol,
        "success": True,
    }


def _generate_pdf_report(
    content: str, title: str, report_type: str, symbol: str,
    filename: str, type_config: dict,
) -> dict:
    """Generate PDF report (via HTML → PDF conversion)."""
    # First generate HTML version
    result = _generate_html_report(content, title, report_type, symbol, filename, type_config)
    html_path = result["path"]
    pdf_path = html_path.replace(".html", ".pdf")

    # Try Chrome/Chromium headless (most reliable on macOS)
    import subprocess, shutil
    _chrome_candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "google-chrome",
        "chromium",
        "chromium-browser",
    ]
    for _chrome in _chrome_candidates:
        _exe = _chrome if os.path.exists(_chrome) else shutil.which(_chrome)
        if _exe:
            try:
                subprocess.run(
                    [
                        _exe,
                        "--headless",
                        "--disable-gpu",
                        "--no-sandbox",
                        "--run-all-compositor-stages-before-draw",
                        "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf_path}",
                        f"file://{html_path}",
                    ],
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
                if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 1000:
                    return {
                        "path": pdf_path,
                        "format": "pdf",
                        "title": title,
                        "report_type": report_type,
                        "symbol": symbol,
                        "success": True,
                        "note": "PDF generated via Chrome headless",
                    }
            except Exception:
                pass

    # Try weasyprint
    try:
        import weasyprint
        weasyprint.HTML(filename=html_path).write_pdf(pdf_path)
        return {
            "path": pdf_path,
            "format": "pdf",
            "title": title,
            "report_type": report_type,
            "symbol": symbol,
            "success": True,
            "note": "PDF generated via WeasyPrint",
        }
    except Exception:
        pass

    # Try pdfkit (requires wkhtmltopdf)
    try:
        import pdfkit
        pdfkit.from_file(html_path, pdf_path)
        return {
            "path": pdf_path,
            "format": "pdf",
            "title": title,
            "report_type": report_type,
            "symbol": symbol,
            "success": True,
            "note": "PDF generated via pdfkit",
        }
    except Exception:
        pass

    # Fallback: return HTML with note
    return {
        "path": html_path,
        "format": "html",
        "title": title,
        "report_type": report_type,
        "symbol": symbol,
        "success": True,
        "note": "PDF conversion unavailable — HTML report generated instead. Install weasyprint for PDF support.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Prebuilt report prompts — returns the LLM instruction for each report type
# ─────────────────────────────────────────────────────────────────────────────

def get_report_prompt(report_type: str, symbol: str, output_format: str = "html") -> str:
    """
    Returns the full LLM prompt that will generate a structured report and
    save it via generate_report tool.

    This is called by the /report dispatch handler in nse_agent.py.
    """
    sym = symbol.upper()
    fmt = output_format.lower()

    prompts = {
        "technical": (
            f"Perform a comprehensive technical analysis of {sym}. "
            f"Call get_technical_setup for {sym}. Then write a detailed technical analysis report covering:\n"
            f"1. **Price Action & Trend** — current trend direction, ADX, trend duration\n"
            f"2. **Key Levels** — support/resistance zones, pivot points, Fibonacci levels\n"
            f"3. **Momentum Indicators** — RSI, MACD signal, Stochastic, rate of change\n"
            f"4. **Volume Analysis** — volume trend, accumulation/distribution, OBV\n"
            f"5. **Chart Patterns** — any recognizable patterns (cup & handle, VCP, flag, etc.)\n"
            f"6. **Stage Analysis** — Weinstein stage (1-4), duration in current stage\n"
            f"7. **Trading Setup** — entry zone, stop-loss, targets (1:2 and 1:3 RR), timeframe\n\n"
            f"After your analysis, call generate_report with:\n"
            f"  content=<your full analysis as markdown>, report_type='technical', "
            f"  symbol='{sym}', output_format='{fmt}'\n"
            f"Then tell the user where the report was saved."
        ),
        "fundamental": (
            f"Perform a fundamental analysis of {sym}. "
            f"Call comprehensive_stock_research for {sym}. Then write a detailed fundamental report covering:\n"
            f"1. **Company Overview** — business model, sector, market cap, promoter holding\n"
            f"2. **Revenue & Profitability** — 5Y revenue/PAT CAGR, margins (OPM, NPM), QoQ/YoY growth\n"
            f"3. **Balance Sheet** — debt/equity, current ratio, interest coverage, working capital\n"
            f"4. **Cash Flow** — operating CF, free cash flow, CFO/PAT ratio, capex trends\n"
            f"5. **Valuation Metrics** — P/E, P/B, EV/EBITDA, PEG ratio vs sector median\n"
            f"6. **Peer Comparison** — how does it rank vs top 3-5 peers on key metrics\n"
            f"7. **Management Quality** — promoter track record, capital allocation, ROE/ROCE consistency\n"
            f"8. **Investment Thesis** — bull case, bear case, fair value estimate, margin of safety\n\n"
            f"After your analysis, call generate_report with:\n"
            f"  content=<your full analysis as markdown>, report_type='fundamental', "
            f"  symbol='{sym}', output_format='{fmt}'\n"
            f"Then tell the user where the report was saved."
        ),
        "forensic": (
            f"Perform a forensic accounting analysis of {sym}. "
            f"Call run_forensic_analysis for {sym} AND comprehensive_stock_research for {sym}. "
            f"Then write a detailed forensic report covering:\n"
            f"1. **Beneish M-Score** — each component (DSRI, GMI, AQI, SGI, DEPI, SGAI, LVGI, TATA), "
            f"individual flags, composite score, manipulation probability\n"
            f"2. **Piotroski F-Score** — all 9 criteria scored (profitability, leverage, efficiency), "
            f"total score /9, financial strength interpretation\n"
            f"3. **Altman Z-Score** — all 5 ratios, composite score, distress/grey/safe zone\n"
            f"4. **Cash Flow Quality** — CFO vs PAT, accrual ratio, Sloan ratio, cash conversion\n"
            f"5. **Red Flags & Anomalies** — unusual items, related party transactions, auditor changes, "
            f"contingent liabilities, off-balance sheet items\n"
            f"6. **Governance & Audit** — auditor opinion, board independence, pledged shares\n"
            f"7. **Verdict** — GREEN (clean) / AMBER (monitor) / RED (avoid) with confidence level\n\n"
            f"After your analysis, call generate_report with:\n"
            f"  content=<your full analysis as markdown>, report_type='forensic', "
            f"  symbol='{sym}', output_format='{fmt}'\n"
            f"Then tell the user where the report was saved."
        ),
        "research": (
            f"Perform a **comprehensive institutional-grade 360° research report** on {sym}. "
            f"Execute ALL of the following tools IN ORDER — do not skip any:\n\n"
            f"1.  get_symbol_snapshot('{sym}')                        — DB pre-computed scores: Weinstein stage, CANSLIM score, Minervini score, technical/fundamental/investment scores, RSI, trading signal\n"
            f"2.  scrape_screener_in('{sym}')                         — P&L YoY/quarterly, balance sheet, ROCE, ROE, ratios, peers, concall PDF links\n"
            f"3.  get_technical_setup('{sym}')                        — price action, MAs, RSI, MACD, ADX, supertrend, support/resistance from price history\n"
            f"4.  comprehensive_stock_research('{sym}')               — broad fundamental + Yahoo Finance + Moneycontrol\n"
            f"5.  run_forensic_analysis('{sym}')                      — Beneish M-Score (all 8 variables), Piotroski F-Score (all 9 signals), Altman Z'-Score, accrual/Sloan ratio\n"
            f"6.  search_shareholding_analysis('{sym}')               — promoter %, FII %, DII %, pledge %, QoQ trend\n"
            f"7.  search_concall_transcripts('{sym}')                 — latest 2-3 concall transcripts / earnings call PDFs\n"
            f"8.  analyze_concall_sentiment('{sym}')                  — NLP: mgmt tone, guidance, red flags, sentiment score\n"
            f"9.  search_latest_catalysts('{sym}')                    — recent news, events, triggers\n"
            f"10. get_sector_context('{sym}')                         — sector rotation, relative strength vs Nifty\n"
            f"11. deep_search('{sym}', verticals=['analyst_targets','broker_reports','credit_ratings','insider_trades'])\n\n"
            f"Now synthesise ALL data into a **comprehensive research report**. Start with a top section named "
            f"**Agent Adda Overview**: a detailed LLM-written overview of the stock in 2-3 short paragraphs, "
            f"covering business quality, current technical position, fundamental picture, relative strength, "
            f"key risks, and what would change the view. Then include ALL of these 16 sections:\n\n"
            f"---\n\n"
            f"## 1. Executive Summary\n"
            f"- 3-line verdict: BUY / HOLD / AVOID with conviction level (HIGH / MEDIUM / LOW)\n"
            f"- One-paragraph thesis: why this company stands out (or doesn't)\n"
            f"- **Master Scorecard table** (use DB values from get_symbol_snapshot + your analysis):\n"
            f"  | Dimension | Score | Max | Rating |\n"
            f"  |---|---|---|---|\n"
            f"  | Technical Score | (from DB) | 100 | |\n"
            f"  | Fundamental Score | (from DB) | 100 | |\n"
            f"  | CANSLIM Score | (from DB) | 100 | |\n"
            f"  | Minervini Score | (from DB) | 10 | |\n"
            f"  | Investment Score (Composite) | (from DB) | 100 | |\n"
            f"  | Forensic Health | (Piotroski F) | 9 | |\n"
            f"  | Mgmt Sentiment | (from NLP) | 10 | |\n\n"
            f"## 2. Company Overview\n"
            f"- Full business description: what it does, key segments, revenue mix\n"
            f"- Market cap, listing exchange, sector, industry classification\n"
            f"- Promoter group background, management pedigree\n"
            f"- Key competitive moats and differentiators\n"
            f"- Recent corporate events (mergers, splits, bonus, rights, buybacks)\n\n"
            f"## 3. Stage Analysis & Technical Position\n"
            f"- **Weinstein Stage**: State stage (1/2/3/4) with label and plain-English meaning:\n"
            f"  Stage 1 = Basing/Accumulation | Stage 2 = Advancing/Uptrend | Stage 3 = Topping/Distribution | Stage 4 = Declining\n"
            f"- Stage score from DB; trading signal (e.g. STRONG_BUY / WEAK_HOLD); trend signal (BULLISH/BEARISH)\n"
            f"- Supertrend: state and value vs current price\n"
            f"- **Technical Indicator table**:\n"
            f"  | Indicator | Value | Signal |\n"
            f"  |---|---|---|\n"
            f"  | Weinstein Stage | | |\n"
            f"  | Stage Score (DB) | | |\n"
            f"  | RSI (14) | | |\n"
            f"  | MACD | | |\n"
            f"  | ADX | | |\n"
            f"  | 50 DMA | | |\n"
            f"  | 150 DMA | | |\n"
            f"  | 200 DMA | | |\n"
            f"  | Supertrend | | |\n"
            f"  | Relative Strength % | | |\n"
            f"  | Trading Signal | | |\n"
            f"- Key support and resistance zones (table: Level | Type | Significance)\n"
            f"- Price performance: 1D / 1W / 1M changes\n"
            f"- Chart pattern if any (VCP, cup & handle, flag, base breakout)\n"
            f"- **Trading Setup**: Entry Zone | Stop-Loss | Target-1 | Target-2 | R:R | Timeframe\n\n"
            f"## 4. CANSLIM Analysis (Full 7-Criteria)\n"
            f"- DB pre-computed CANSLIM score: X/100 — state prominently\n"
            f"- **Full 7-criteria evaluation table** with ✅ PASS / 🟡 PARTIAL / ❌ FAIL:\n"
            f"  | Criterion | Metric | Value | Threshold | Signal | Notes |\n"
            f"  |---|---|---|---|---|---|\n"
            f"  | C — Current Quarterly Earnings | QoQ EPS growth | | ≥25% | | |\n"
            f"  | A — Annual Earnings Growth | 5Y EPS CAGR | | ≥25% | | |\n"
            f"  | N — New Products/Highs | 52W high proximity | | Within 15% | | |\n"
            f"  | S — Supply & Demand | Vol up-days vs down-days | | Up > Down | | |\n"
            f"  | L — Leader or Laggard | RS Rating % | | ≥80 | | |\n"
            f"  | I — Institutional Sponsorship | FII/MF trend | | Rising | | |\n"
            f"  | M — Market Direction | Nifty stage/trend | | Stage 2 / Uptrend | | |\n"
            f"- Final score X/7 and overall CANSLIM verdict\n\n"
            f"## 5. Minervini Trend Template Score\n"
            f"- DB pre-computed Minervini score: X/10 — state prominently\n"
            f"- **Minervini Trend Template checklist** (evaluate each criterion with ✅/❌):\n"
            f"  | # | Criterion | Status | Current Value |\n"
            f"  |---|---|---|---|\n"
            f"  | 1 | Price > 150 DMA AND 200 DMA | | |\n"
            f"  | 2 | 150 DMA > 200 DMA | | |\n"
            f"  | 3 | 200 DMA trending up ≥1 month | | |\n"
            f"  | 4 | 50 DMA > 150 DMA AND 200 DMA | | |\n"
            f"  | 5 | Price > 50 DMA | | |\n"
            f"  | 6 | Price within 25% of 52W high | | |\n"
            f"  | 7 | Price ≥ 30% above 52W low | | |\n"
            f"  | 8 | RS Rating ≥ 70 | | |\n"
            f"- Template compliance: X/8 criteria met; verdict: STAGE 2 LEADER / WATCH / NOT READY\n\n"
            f"## 6. P&L Analysis — Quarterly & YoY\n"
            f"- **Quarterly P&L table** (last 6 quarters): Quarter | Revenue (Cr) | EBITDA (Cr) | OPM% | PAT (Cr) | NPM% | EPS | QoQ Gr% | YoY Gr%\n"
            f"- **Annual P&L table** (last 5 years): FY | Revenue | Revenue Gr% | EBITDA | OPM% | PAT | PAT Gr% | EPS\n"
            f"- Revenue and PAT 3Y and 5Y CAGR\n"
            f"- Margin trend: expanding or compressing, and why\n"
            f"- One-time items, exceptional gains/losses to flag\n\n"
            f"## 7. Balance Sheet — Quarterly & YoY\n"
            f"- **Annual Balance Sheet** (last 5 years): FY | Equity | Total Debt | Net Debt | D/E | Cash | Total Assets\n"
            f"- **Quarterly Balance Sheet** (last 4 quarters): Q | Borrowings | Cash | Net Debt | Current Ratio | Working Capital\n"
            f"- Interest coverage ratio trend; asset quality; off-balance-sheet obligations\n\n"
            f"## 8. Profitability & Efficiency (ROCE, ROE, Margins)\n"
            f"- **Key Ratios table**: Metric | FY-2 | FY-1 | TTM | Sector Median\n"
            f"  Rows: ROCE (%) | ROE (%) | OPM (%) | NPM (%) | Asset Turnover | Inventory Days | Debtor Days | FCF Yield\n"
            f"- Free Cash Flow (OCF - Capex) for last 5 years; CFO/PAT ratio\n"
            f"- Capital allocation: dividends, buybacks, reinvestment rate\n\n"
            f"## 9. Promoter & Institutional Holding\n"
            f"- **Shareholding table** (last 6 quarters): Quarter | Promoter% | FII% | DII% | MF% | Public%\n"
            f"- Pledge % and trend — flag if >10%\n"
            f"- Recent insider/promoter buy-sell disclosures\n"
            f"- Top institutional holders: which MFs/FIIs hold, trend (adding/reducing)\n\n"
            f"## 10. Forensic Health (Full Scores)\n"
            f"- **Forensic Master Scorecard**:\n"
            f"  | Score | Value | Safe Threshold | Zone | Interpretation |\n"
            f"  |---|---|---|---|---|\n"
            f"  | Beneish M-Score | | < -1.78 | | |\n"
            f"  | Piotroski F-Score | | ≥ 7 strong | | |\n"
            f"  | Altman Z'-Score | | > 2.6 safe | | |\n"
            f"  | Accrual Ratio (Sloan) | | < 5% clean | | |\n"
            f"  | CFO/PAT Ratio | | > 0.8 clean | | |\n"
            f"- **Beneish M-Score — all 8 variables**: Variable | Value | Flag? | What it measures\n"
            f"  (DSRI, GMI, AQI, SGI, DEPI, SGAI, LVGI, TATA)\n"
            f"- **Piotroski F-Score — all 9 signals**: Signal | Score (0/1) | Interpretation\n"
            f"  (F1 ROA, F2 ΔCash ROA, F3 Accrual quality, F4 ΔLEV, F5 ΔLIQ, F6 No dilution, F7 ΔMARGIN, F8 ΔTURN, Total)\n"
            f"- Top 3 red flags (if any); governance: auditor quality, RPTs, contingent liabilities\n"
            f"- Overall forensic verdict: ✅ CLEAN / ⚠️ WATCH / ❌ CAUTION\n\n"
            f"## 11. Concall Highlights & Management Commentary\n"
            f"- Latest 2-3 concall PDFs — link table: Period | Date | Link\n"
            f"- Management tone: Bullish / Neutral / Cautious (NLP confidence score)\n"
            f"- Key guidance: revenue growth, margin outlook, capex plans\n"
            f"- Key risks acknowledged; forward-looking: product launches, expansion, order book\n\n"
            f"## 12. Credit Ratings & Analyst Targets\n"
            f"- Credit ratings (CRISIL/ICRA/CARE): Instrument | Rating | Outlook | Date\n"
            f"- **Analyst consensus**: Broker | Rating | Target | Upside% | Date\n"
            f"- Consensus summary: Buy/Hold/Sell count, average target, implied upside\n\n"
            f"## 13. Investor Sentiment & News Catalysts\n"
            f"- Recent news (last 30 days): Date | Headline | Impact (Positive/Negative/Neutral)\n"
            f"- Upcoming events: results, AGM, dividend, product launches, regulatory\n\n"
            f"## 14. Sector Context & Relative Strength\n"
            f"- Sector rotation phase; RS vs sector and Nifty 50\n"
            f"- Sector PE vs stock PE; macro tailwinds/headwinds\n\n"
            f"## 15. Risk Factors\n"
            f"- Table: Risk | Severity (H/M/L) | Probability (H/M/L) | Mitigation\n"
            f"- Cover: regulatory, competition, promoter, debt, macro/FX, valuation risks\n\n"
            f"## 16. Investment Verdict\n"
            f"- **Final Recommendation**: BUY / ACCUMULATE / HOLD / REDUCE / AVOID\n"
            f"- **Action Table**: Entry Zone | Stop-Loss | Target-1 (6M) | Target-2 (12M) | Position Size\n"
            f"- Bull case scenario (price + conditions) | Bear case scenario (price + conditions)\n"
            f"- Fair value estimate if feasible\n\n"
            f"---\n\n"
            f"**Formatting rules:**\n"
            f"- Use markdown tables for all comparative/tabular data — never bullet lists for table data\n"
            f"- Use ✅ for positive signals, ⚠️ for caution, ❌ for red flags\n"
            f"- Bold key metrics and signal words (BUY, SELL, BULLISH, BEARISH, HIGH, LOW)\n"
            f"- Every section must contain real data from the tools — do not write 'data not available'\n\n"
            f"After writing ALL 16 sections, call generate_report with:\n"
            f"  content=<your full analysis as markdown>, report_type='research', "
            f"  symbol='{sym}', output_format='{fmt}'\n"
            f"Then tell the user the file path and 3 key highlights."
        ),
        "intraday": (
            f"Perform an intraday analysis of {sym}. "
            f"Call get_technical_setup for {sym}. Also call search_latest_catalysts for {sym} "
            f"to check for any breaking news. Then write an intraday report covering:\n"
            f"1. **Intraday Price Action** — gap up/down, opening drive, range, trend today\n"
            f"2. **Volume Profile** — volume vs 20-day avg, buyer/seller dominance\n"
            f"3. **VWAP & Levels** — VWAP status, PDH/PDL, today's pivot, key intraday levels\n"
            f"4. **Momentum (5m/15m)** — short-term RSI, MACD crossover, momentum direction\n"
            f"5. **Options Activity** — if F&O stock: PCR, max pain, OI buildup, unusual activity\n"
            f"6. **Sector Context** — is the sector helping or hurting? sector index direction\n"
            f"7. **Trade Setup** — intraday entry, target, stop-loss, position sizing note\n\n"
            f"After your analysis, call generate_report with:\n"
            f"  content=<your full analysis as markdown>, report_type='intraday', "
            f"  symbol='{sym}', output_format='{fmt}'\n"
            f"Then tell the user where the report was saved."
        ),
        "canslim": (
            f"Perform a full CANSLIM evaluation of {sym}. Execute:\n"
            f"1. comprehensive_stock_research for {sym}\n"
            f"2. get_technical_setup for {sym}\n"
            f"3. search_latest_catalysts for {sym}\n"
            f"4. deep_search for {sym} with verticals=['shareholding','mutual_funds']\n\n"
            f"Evaluate ALL 7 CANSLIM criteria:\n"
            f"- **C — Current Quarterly Earnings**: QoQ EPS growth ≥25%? Revenue acceleration?\n"
            f"- **A — Annual Earnings Growth**: 5Y EPS CAGR ≥25%? Consistent growth?\n"
            f"- **N — New**: New products/management/price highs? 52W high proximity?\n"
            f"- **S — Supply & Demand**: Low float? Volume on up-days vs down-days?\n"
            f"- **L — Leader or Laggard**: RS rating vs market ≥80? Sector leader?\n"
            f"- **I — Institutional Sponsorship**: FII/MF increasing? Quality institutions?\n"
            f"- **M — Market Direction**: Is the market in confirmed uptrend?\n\n"
            f"Score each criterion: ✅ PASS / 🟡 PARTIAL / ❌ FAIL\n"
            f"Give a final score X/7 and overall verdict.\n\n"
            f"After your analysis, call generate_report with:\n"
            f"  content=<your full analysis as markdown>, report_type='canslim', "
            f"  symbol='{sym}', output_format='{fmt}'\n"
            f"Then tell the user where the report was saved."
        ),
        "ric": (
            f"Perform a RIC (Research Investigation Committee) deep-dive on {sym}. Execute:\n"
            f"1. comprehensive_stock_research for {sym}\n"
            f"2. run_forensic_analysis for {sym}\n"
            f"3. search_latest_catalysts for {sym}\n"
            f"4. deep_search for {sym} with verticals=['insider_trades','shareholding','analyst_targets','broker_reports']\n"
            f"5. get_sector_context for {sym}\n\n"
            f"Write a RIC investigation report:\n"
            f"1. **Investigation Context** — why is this stock interesting? catalyst/trigger\n"
            f"2. **Evidence Gathering** — key data points from all tools\n"
            f"3. **Bull Case** — strongest arguments for buying, with data support\n"
            f"4. **Bear Case** — strongest arguments against, red flags, risks\n"
            f"5. **Key Findings** — surprising/non-obvious insights from the data\n"
            f"6. **Risk Assessment** — probability-weighted risk analysis\n"
            f"7. **Conclusions & Recommendations** — verdict, sizing, timeframe, conditions\n\n"
            f"After your analysis, call generate_report with:\n"
            f"  content=<your full analysis as markdown>, report_type='ric', "
            f"  symbol='{sym}', output_format='{fmt}'\n"
            f"Then tell the user where the report was saved."
        ),
        "sector": (
            f"Perform a sector analysis for '{symbol}'. Execute:\n"
            f"1. get_sector_context for a representative stock or '{symbol}'\n"
            f"2. search_latest_catalysts for '{symbol} sector India'\n"
            f"3. deep_search for '{symbol}' with context='sector rotation analysis India'\n\n"
            f"Write a sector report covering:\n"
            f"1. **Sector Overview** — what the sector does, key drivers, macro linkage\n"
            f"2. **Rotation Status** — Mansfield RS, is money flowing in/out? which quadrant?\n"
            f"3. **Top Performers & Laggards** — best and worst stocks, why\n"
            f"4. **Technical Breadth** — % stocks above 50/200 DMA, new highs vs lows\n"
            f"5. **Key Stocks & Catalysts** — which names to watch, upcoming triggers\n"
            f"6. **Outlook & Positioning** — next 1-3 months view, overweight/underweight\n\n"
            f"After your analysis, call generate_report with:\n"
            f"  content=<your full analysis as markdown>, report_type='sector', "
            f"  symbol='{symbol}', output_format='{fmt}'\n"
            f"Then tell the user where the report was saved."
        ),
    }

    return prompts.get(report_type, prompts["research"])
