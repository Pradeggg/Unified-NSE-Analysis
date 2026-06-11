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
import csv
import datetime
import html as _html
import json
import shutil
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports" / "generated"
PG_DSN = (
    os.environ.get("AGENT_ADDA_PG_DSN")
    or os.environ.get("PG_DSN")
    or "dbname=nse_market user=nse_admin host=/tmp"
)

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


def _research_price_chart_markdown(symbol: str, rows: list[dict]) -> str:
    """Return an embedded SVG price chart as Markdown image syntax."""
    clean_rows: list[dict] = []
    for row in rows or []:
        try:
            close = float(row.get("close"))
        except Exception:
            continue
        clean_rows.append(
            {
                "date": str(row.get("trade_date") or ""),
                "close": close,
                "volume": float(row.get("volume") or 0),
            }
        )
    if len(clean_rows) < 5:
        return ""

    import urllib.parse

    width, height = 920, 330
    pad_l, pad_r, pad_t, pad_b = 54, 20, 24, 46
    chart_h = 210
    vol_h = 44
    closes = [r["close"] for r in clean_rows]
    volumes = [r["volume"] for r in clean_rows]
    cmin, cmax = min(closes), max(closes)
    if cmax == cmin:
        cmax = cmin + 1
    vmax = max(volumes) or 1
    plot_w = width - pad_l - pad_r

    def x_for(i: int) -> float:
        if len(clean_rows) == 1:
            return pad_l + plot_w / 2
        return pad_l + (i / (len(clean_rows) - 1)) * plot_w

    def y_for(value: float) -> float:
        return pad_t + chart_h - ((value - cmin) / (cmax - cmin)) * chart_h

    points = " ".join(
        f"{x_for(i):.1f},{y_for(row['close']):.1f}"
        for i, row in enumerate(clean_rows)
    )
    vol_y = pad_t + chart_h + 22
    bar_w = max(1.0, plot_w / len(clean_rows) * 0.62)
    vol_bars = []
    for i, row in enumerate(clean_rows):
        h = max(1.0, (row["volume"] / vmax) * vol_h)
        x = x_for(i) - bar_w / 2
        y = vol_y + vol_h - h
        color = "#16a34a" if i == 0 or row["close"] >= clean_rows[i - 1]["close"] else "#dc2626"
        vol_bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{color}" opacity="0.45"/>')

    first = clean_rows[0]
    last = clean_rows[-1]
    ret = ((last["close"] / first["close"]) - 1) * 100 if first["close"] else 0
    trend_color = "#16a34a" if ret >= 0 else "#dc2626"
    grid = []
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = pad_t + chart_h * frac
        value = cmax - (cmax - cmin) * frac
        grid.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" stroke="#e2e8f0" stroke-width="1"/>')
        grid.append(f'<text x="8" y="{y+4:.1f}" font-size="11" fill="#64748b">{value:,.0f}</text>')

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        '<rect width="100%" height="100%" rx="12" fill="#f8fafc"/>'
        f'<text x="{pad_l}" y="18" font-size="14" font-weight="700" fill="#0f172a">{_html.escape(symbol.upper())} 6-month price and volume</text>'
        f'<text x="{width-pad_r-170}" y="18" font-size="12" fill="{trend_color}">{ret:+.1f}% over chart</text>'
        + "".join(grid)
        + "".join(vol_bars)
        + f'<polyline points="{points}" fill="none" stroke="{trend_color}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>'
        + f'<circle cx="{x_for(len(clean_rows)-1):.1f}" cy="{y_for(last["close"]):.1f}" r="4" fill="{trend_color}"/>'
        + f'<text x="{pad_l}" y="{height-16}" font-size="11" fill="#64748b">{_html.escape(first["date"])}</text>'
        + f'<text x="{width-pad_r-96}" y="{height-16}" font-size="11" fill="#64748b">{_html.escape(last["date"])}</text>'
        + f'<text x="{width-pad_r-114}" y="{y_for(last["close"])-8:.1f}" font-size="12" font-weight="700" fill="{trend_color}">Close {last["close"]:,.2f}</text>'
        + '</svg>'
    )
    data_uri = "data:image/svg+xml;utf8," + urllib.parse.quote(svg, safe="")
    return "\n".join(
        [
            "## Price Chart & Technical Narrative",
            "",
            f"![{symbol.upper()} 6-month price and volume chart]({data_uri})",
            "",
            (
                f"> The embedded chart uses {len(clean_rows)} local EOD sessions from "
                f"{first['date']} to {last['date']}. Close moved from "
                f"₹{first['close']:,.2f} to ₹{last['close']:,.2f} ({ret:+.1f}%). "
                "Use this visual together with the technical-score and stage tables below."
            ),
            "",
        ]
    )


def _build_postgres_research_context(symbol: str) -> str:
    """Build a data-backed research context from PostgreSQL for /report research."""
    if not symbol:
        return ""
    sym = symbol.upper().strip()
    chart_rows: list[dict] = []
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
                cur.execute(
                    """
                    SELECT trade_date, close, volume
                    FROM market.equity_eod
                    WHERE symbol = %s
                    ORDER BY trade_date DESC
                    LIMIT 126
                    """,
                    (sym,),
                )
                chart_rows = list(reversed(cur.fetchall()))
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
        _research_price_chart_markdown(sym, chart_rows),
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

    def _md_image(match: re.Match) -> str:
        alt = _html.unescape(match.group(1)).strip()
        src = _html.unescape(match.group(2)).strip()
        if src.startswith("<") and src.endswith(">"):
            src = src[1:-1].strip()
        src = src.strip("\"'")
        return (
            f'<img src="{_html.escape(src, quote=True)}" '
            f'alt="{_html.escape(alt, quote=True)}" '
            f'style="max-width:100%;height:auto;border-radius:8px;" />'
        )

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

    text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', _md_image, text)
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

        # ── Trusted raw report widgets emitted by internal builders ───────
        # Keep this before table detection so JavaScript/CSS containing pipes
        # such as "||" is not mistaken for a Markdown table.
        if raw.lstrip().startswith(('<div class="aa-', '<section class="aa-')):
            _flush_list(); _flush_table(); _flush_blockquote(); _flush_kv()
            out.append(raw)
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

AGENT_ADDA_REPORT_THEME_ID = "sector-rotation-standard"
AGENT_ADDA_REPORT_ENGINE = "Agent Adda Report Shell"


REPORT_HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Agent Adda</title>
<style>
/* ── Reset & variables ─────────────────────────────────────────────── */
:root {{
  --bg:       #f0f4f8;
  --surface:  #f8fafc;
  --card:     #ffffff;
  --border:   #e2e8f0;
  --border2:  #dbe3ef;
  --text:     #1a2332;
  --dim:      #64748b;
  --primary:  #1e3a5f;
  --primary-alt:#2563eb;
  --accent:   #1e3a5f;
  --accent2:  #2563eb;
  --green:    #4ade80;
  --red:      #f87171;
  --yellow:   #fbbf24;
  --orange:   #fb923c;
  --purple:   #c084fc;
  --radius:   10px;
  --shadow:   0 1px 3px rgba(0,0,0,.08);
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
  background: var(--primary);
  border-bottom: 1px solid var(--border);
  padding: 0 32px;
  height: 52px;
  display:flex; align-items:center; justify-content:space-between;
  position: sticky; top:0; z-index:99;
}}
.site-hdr {{
  color:#fff; box-shadow:0 4px 8px rgba(0,0,0,.10);
}}
.hdr-inner {{
  width:100%; display:flex; align-items:center; justify-content:space-between; gap:12px;
}}
.hdr-brand {{
  display:flex; align-items:center; gap:10px; min-width:0;
}}
.hdr-title {{
  font-size:1.05rem; font-weight:700; letter-spacing:0; white-space:nowrap; color:#fff;
}}
.hdr-meta {{
  display:flex; gap:8px; align-items:center; flex-wrap:wrap;
}}
.mbadge {{
  display:inline-block; padding:3px 10px; border-radius:20px;
  font-size:11px; font-weight:600; white-space:nowrap;
  background:rgba(255,255,255,.14); color:#fff;
}}
.topbar-brand {{ display:flex; align-items:center; gap:12px; }}
.topbar-brand img {{
  height:32px; width:auto; border-radius:6px;
  object-fit:contain; background:#fff; padding:2px 4px;
}}
.topbar-brand .brand-name {{
  font-size:15px; font-weight:800; letter-spacing:.02em;
  color:#fff;
}}
.topbar-actions {{ display:flex; align-items:center; gap:12px; }}
.btn {{
  padding: 6px 14px; border-radius:6px; font-size:12px; font-weight:600;
  cursor:pointer; border:none; transition: all .15s;
}}
.btn-outline {{
  background:transparent; border:1px solid rgba(255,255,255,.32);
  color:rgba(255,255,255,.82);
}}
.btn-outline:hover {{ border-color:#fff; color:#fff; }}
.btn-primary {{
  background: var(--primary-alt); color:#fff;
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
.content {{
  max-width:1440px; margin:0 auto; padding:20px 32px;
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

/* ── Sector-rotation-standard summary cards ───────────────────────── */
.metrics-row {{
  display:flex; gap:12px; flex-wrap:wrap; margin-bottom:20px;
}}
.metric-card {{
  flex:1; min-width:160px; background:var(--card); border-radius:8px;
  border:1px solid var(--border); padding:14px 16px; box-shadow:var(--shadow);
}}
.metric-label {{
  font-size:10px; text-transform:uppercase; letter-spacing:.08em;
  color:var(--dim); margin-bottom:5px; font-weight:700;
}}
.metric-value {{
  font-size:1.25rem; font-weight:800; color:var(--primary); line-height:1.15;
}}
.metric-sub {{
  font-size:11px; color:var(--dim); margin-top:3px;
}}
.summary-card {{
  background:var(--card); border-radius:8px; border:1px solid var(--border);
  box-shadow:var(--shadow); padding:0; min-width:0; max-width:100%;
  overflow-wrap:anywhere;
}}

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

/* ── Stage 2 tracker visual standard overrides ────────────────────── */
body {{
  background:#f1f5f9;
  color:#0f172a;
  font-family:'Segoe UI', system-ui, sans-serif;
  line-height:1.6;
}}
.topbar.app-bar {{
  background:linear-gradient(135deg,#065f46,#059669);
  color:#fff;
  padding:18px 24px;
  height:auto;
  min-height:86px;
  position:static;
  border:0;
  box-shadow:none;
  align-items:flex-start;
}}
.topbar.app-bar .hdr-inner {{
  max-width:1600px;
  margin:0 auto;
  align-items:flex-start;
}}
.topbar.app-bar .topbar-brand img {{ display:none; }}
.topbar.app-bar .hdr-brand {{
  flex-direction:column;
  align-items:flex-start;
  gap:4px;
}}
.topbar.app-bar .hdr-title {{
  font-size:1.4rem;
  font-weight:700;
  line-height:1.15;
}}
.hdr-subtitle {{
  font-size:.82rem;
  opacity:.86;
  color:#ecfdf5;
  font-weight:600;
}}
.topbar.app-bar .topbar-actions {{
  gap:8px;
  flex-wrap:wrap;
  justify-content:flex-end;
  padding-top:1px;
}}
.topbar.app-bar .btn {{
  padding:5px 12px;
  border-radius:6px;
  font-size:12px;
  font-weight:600;
}}
.topbar.app-bar .btn-outline {{
  background:rgba(255,255,255,.08);
  border-color:rgba(255,255,255,.28);
  color:#fff;
}}
.topbar.app-bar .btn-outline:hover {{
  background:rgba(255,255,255,.16);
  border-color:rgba(255,255,255,.55);
}}
.topbar.app-bar .btn-primary {{
  background:#fff;
  color:#047857;
}}
.topbar.app-bar .search-wrap.active {{ display:flex; }}
.topbar.app-bar .topbar-search {{
  border-color:rgba(255,255,255,.65);
  width:200px;
}}
.topbar.app-bar .topbar-search:focus {{
  border-color:#fff;
  width:240px;
  box-shadow:0 0 0 2px rgba(255,255,255,.18);
}}
.report-header,
.summary-strip {{
  display:none;
}}
.page-layout,
.content {{
  max-width:1600px;
  padding:20px 16px;
}}
.metrics-row.summary-grid {{
  display:flex;
  flex-wrap:wrap;
  gap:12px;
  margin-bottom:20px;
}}
.metric-card.sum-card {{
  background:#fff;
  border-radius:8px;
  padding:14px 20px;
  box-shadow:0 1px 3px rgba(0,0,0,.08);
  min-width:140px;
  border:1px solid #e2e8f0;
  border-top:3px solid transparent;
  flex:1;
}}
.standard-report-kpis .sum-card:nth-child(1) {{ border-top-color:#059669; }}
.standard-report-kpis .sum-card:nth-child(2) {{ border-top-color:#2563eb; }}
.standard-report-kpis .sum-card:nth-child(3) {{ border-top-color:#ca8a04; }}
.standard-report-kpis .sum-card:nth-child(4) {{ border-top-color:#64748b; }}
.metric-label {{
  font-size:.75rem;
  color:#64748b;
  margin-top:4px;
  text-transform:uppercase;
  letter-spacing:.04em;
  font-weight:500;
}}
.metric-value {{
  font-size:1.55rem;
  font-weight:700;
  line-height:1;
  color:#059669;
}}
.metric-sub {{
  font-size:.72rem;
  color:#94a3b8;
  margin-top:5px;
}}
.section,
.summary-card {{
  background:#fff;
  border-radius:8px;
  border:0;
  box-shadow:0 1px 3px rgba(0,0,0,.08);
  margin-bottom:20px;
  overflow:hidden;
}}
.section:hover {{ border-color:transparent; }}
.section-header.sec-hdr {{
  padding:14px 18px;
  border-bottom:1px solid #e2e8f0;
  background:#fff;
  display:flex;
  align-items:center;
  gap:10px;
  color:#0f172a;
  font-size:1rem;
  font-weight:600;
}}
.section-header.sec-hdr:hover {{
  background:#f8fafc;
}}
.section-toggle {{
  margin-left:auto;
  color:#64748b;
  font-size:.9rem;
}}
.section-body {{
  padding:16px 22px;
  font-size:13.5px;
  line-height:1.65;
}}
.section-body h1 {{
  font-size:1.05rem;
  color:#0f172a;
  margin:18px 0 10px;
}}
.section-body h2 {{
  font-size:.95rem;
  color:#059669;
  margin:18px 0 8px;
}}
.section-body h3 {{
  font-size:.9rem;
  color:#0f172a;
  margin:14px 0 6px;
}}
.section-body strong {{
  color:#0f172a;
}}
.section-body blockquote {{
  border-left:3px solid #059669;
  background:#f8fafc;
  color:#334155;
}}
.arrow-header {{
  background:#f8fafc;
  border-left-color:#059669;
  color:#059669;
}}
.part-divider {{
  color:#64748b;
}}
.kv-list {{
  background:#f8fafc;
  border-color:#e2e8f0;
  font-size:12.5px;
}}
.tbl-wrap {{
  overflow-x:auto;
  margin:14px 0;
  border:0;
  border-radius:0;
}}
.data-table {{
  width:100%;
  min-width:100%;
  border-collapse:collapse;
  font-size:13px;
}}
.data-table thead tr {{
  background:#f8fafc;
}}
.data-table th {{
  background:#f8fafc;
  padding:8px 12px;
  color:#64748b;
  font-size:.72rem;
  font-weight:600;
  text-transform:uppercase;
  letter-spacing:.04em;
  border-bottom:2px solid #e2e8f0;
}}
.data-table th:hover {{
  background:#eef2ff;
  color:#3730a3;
}}
.data-table th.sort-asc::after,
.data-table th.sort-desc::after {{
  color:#059669;
}}
.data-table td {{
  padding:7px 12px;
  border-bottom:1px solid #f1f5f9;
  color:#0f172a;
}}
.data-table tbody tr:hover td {{
  background:rgba(5,150,105,.04);
}}
.disclaimer-box {{
  background:#fff8e1;
  border:1px solid #ffe082;
  color:#5d4037;
  border-radius:8px;
  padding:14px 18px;
}}
.disclaimer-box h4 {{
  color:#92400e;
}}
.report-footer {{
  max-width:1600px;
  padding:16px 24px 28px;
  border-top:1px solid #e2e8f0;
}}

@media(max-width:720px) {{
  html,
  body {{
    max-width:100%;
    overflow-x:hidden;
  }}
  .topbar.app-bar {{
    padding:18px 16px;
  }}
  .topbar.app-bar .hdr-inner {{
    flex-direction:column;
    gap:12px;
    min-width:0;
    width:calc(100vw - 32px);
    max-width:100%;
  }}
  .topbar.app-bar .hdr-brand,
  .topbar.app-bar .topbar-actions {{
    min-width:0;
    width:100%;
    max-width:100%;
  }}
  .topbar.app-bar .hdr-title {{
    white-space:normal;
    overflow-wrap:anywhere;
    word-break:break-word;
    max-width:100%;
    font-size:1.15rem;
  }}
  .hdr-subtitle {{
    line-height:1.45;
    overflow-wrap:anywhere;
  }}
  .topbar.app-bar .topbar-actions {{
    width:100%;
    justify-content:flex-start;
  }}
  .topbar.app-bar .btn {{
    max-width:100%;
    white-space:normal;
  }}
  .topbar.app-bar .search-wrap,
  .topbar.app-bar .search-wrap.active,
  .topbar.app-bar .topbar-search {{
    width:100%;
  }}
  .page-layout,
  .content {{
    padding:20px 16px;
    width:100%;
    max-width:100%;
    overflow:hidden;
  }}
  .content-area {{
    width:100%;
    max-width:100%;
    min-width:0;
  }}
  .content *,
  .page-layout * {{
    min-width:0;
  }}
  .metrics-row.summary-grid {{
    display:grid;
    grid-template-columns:minmax(0, 1fr);
    gap:12px;
  }}
  .metric-card.sum-card {{
    min-width:0;
    width:100%;
    max-width:100%;
    flex-basis:auto;
  }}
  .section,
  .summary-card {{
    width:100%;
    max-width:100%;
    min-width:0;
  }}
  .section-body {{
    padding:14px 18px;
    width:100%;
    max-width:100%;
    overflow:hidden;
    overflow-wrap:anywhere;
  }}
  .section-body > *:not(.tbl-wrap) {{
    max-width:100%;
  }}
  .section-body p,
  .section-body li,
  .section-body h1,
  .section-body h2,
  .section-body h3,
  .section-body h4 {{
    width:100%;
    max-width:100%;
    overflow-wrap:anywhere;
    word-break:break-word;
  }}
  .section-body code {{
    white-space:normal;
    overflow-wrap:anywhere;
  }}
  .tbl-wrap {{
    max-width:100%;
    overflow-x:auto;
  }}
  .data-table {{
    width:100%;
    min-width:100%;
  }}
  .data-table th,
  .data-table td {{
    white-space:normal;
    overflow-wrap:anywhere;
  }}
}}

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
<body data-agent-theme="{theme_id}">

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
<header class="app-bar site-hdr topbar">
  <div class="hdr-inner">
  <div class="hdr-brand topbar-brand">
    {logo_img_nav}
    <span class="brand-name hdr-title">{title}</span>
    <span class="hdr-subtitle">{badge_label} · {report_subject} · Generated: {date} {time} IST · Agent Adda</span>
  </div>
  <div class="hdr-meta topbar-actions">
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
</header>

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
<main class="content page-layout">
  <section class="summary-grid metrics-row standard-report-kpis" aria-label="Report details">
    <div class="sum-card metric-card">
      <div class="metric-label">Report Type</div>
      <div class="metric-value">{badge_label}</div>
      <div class="metric-sub">Standard Agent Adda theme</div>
    </div>
    <div class="sum-card metric-card">
      <div class="metric-label">Subject</div>
      <div class="metric-value">{report_subject}</div>
      <div class="metric-sub">Symbol or market scope</div>
    </div>
    <div class="sum-card metric-card">
      <div class="metric-label">Generated</div>
      <div class="metric-value">{date}</div>
      <div class="metric-sub">{time} IST</div>
    </div>
    <div class="sum-card metric-card">
      <div class="metric-label">Engine</div>
      <div class="metric-value">Agent Adda</div>
      <div class="metric-sub">{engine}</div>
    </div>
  </section>
  <div class="content-area">

    <!-- Report body -->
    <div class="summary-card section" id="main-section">
      <div class="sec-hdr section-header" onclick="toggleSection(this.parentElement)">
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
</main><!-- end page-layout -->

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
    "strategy-lab": {
        "title": "Portfolio Strategy Lab — NSE Paper Trading — {date}",
        "badge": "badge-stage2",
        "badge_label": "PORTFOLIO STRATEGY LAB",
        "sections": [
            "Strategy Leaderboard",
            "Risk-Adjusted Readout",
            "Cost and Turnover Diagnostics",
            "Recommended Paper Trading Focus",
            "Run Artifacts and Methodology",
        ],
    },
    "portfolio-monitor": {
        "title": "My Portfolio — EOD Analysis — {date}",
        "badge": "badge-research",
        "badge_label": "PORTFOLIO MONITOR",
        "sections": [
            "Portfolio Summary & KPIs",
            "Strong Buy Opportunities",
            "Buy Signals",
            "Hold — Monitor",
            "Sell — Exit Candidates",
            "Sector Breakdown",
            "Signal Distribution",
        ],
    },
    "diagnosis": {
        "title": "{symbol} — Fundamental Driver Diagnosis",
        "badge": "badge-fundamental",
        "badge_label": "FUNDAMENTAL DIAGNOSIS",
        "sections": [
            "Short Answer",
            "Metric Bridge",
            "Evidence",
            "Interpretation",
            "What to Watch",
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


def _fmt_pct_plain(v, decimals=1) -> str:
    try:
        return f"{float(v):.{decimals}f}%"
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


def _strategy_lab_artifact_path(summary: dict, summary_path: Path, artifact: str | None) -> Path | None:
    if not artifact:
        return None
    raw = Path(str(artifact))
    if raw.is_absolute():
        return raw
    output_dir = summary.get("output_dir")
    candidates = []
    if output_dir:
        candidates.append(ROOT / str(output_dir) / raw)
    candidates.append(ROOT / raw)
    candidates.append(summary_path.parent.parent / raw)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else None


def _strategy_lab_output_dir(summary: dict, summary_path: Path) -> Path:
    output_dir = Path(str(summary.get("output_dir") or summary_path.parent.parent))
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    return output_dir


def _strategy_lab_replay_state_path(summary: dict, summary_path: Path, strategy_id: str) -> Path:
    return _strategy_lab_output_dir(summary, summary_path) / "runs" / strategy_id / "state" / "replay_state.json"


def _read_csv_rows(path: Path | None, limit: int | None = None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError:
        return []
    return rows[:limit] if limit is not None else rows


def _float_or_none(value) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in {float("inf"), float("-inf")}:
        return None
    return parsed


def _strategy_lab_narrative(summary: dict, rows: list[dict], paper: dict, positions: list[dict]) -> dict[str, object]:
    """Return a comprehensive LLM narrative, with deterministic fallback."""

    fallback = _strategy_lab_deterministic_narrative(summary, rows, paper, positions)
    use_llm = _strategy_lab_llm_enabled()
    if not use_llm:
        return {**fallback, "source": "deterministic fallback"}

    schema = {
        "type": "object",
        "required": [
            "headline",
            "narrative",
            "portfolio_readout",
            "strategy_readout",
            "turnover_readout",
            "action_plan",
            "focus",
            "risks",
        ],
        "properties": {
            "headline": {"type": "string"},
            "narrative": {"type": "string"},
            "portfolio_readout": {"type": "string"},
            "strategy_readout": {"type": "string"},
            "turnover_readout": {"type": "string"},
            "action_plan": {"type": "array", "items": {"type": "string"}},
            "focus": {"type": "array", "items": {"type": "string"}},
            "risks": {"type": "array", "items": {"type": "string"}},
        },
    }
    payload = {
        "run": {
            "window": f"{summary.get('start_date')} to {summary.get('end_date')}",
            "latest_eod_date": summary.get("latest_eod_date"),
            "costs": f"{summary.get('slippage_bps')} bps slippage + {summary.get('brokerage_bps')} bps brokerage",
        },
        "leaderboard": rows[:5],
        "paper_portfolio": paper,
        "fundamental_coverage": summary.get("fundamental_coverage") or {},
        "top_positions": positions[:8],
    }
    try:
        from terminal.research_council.llm_client import call_llm_json

        result = call_llm_json(
            system=(
                "You are a paper-trading portfolio analyst writing an executive-ready strategy-lab "
                "brief for an Indian NSE paper portfolio. Interpret only the supplied strategy-lab and "
                "paper portfolio data. Do not add external facts. Use INR/₹ for all money values, never "
                "USD or $. Be comprehensive but grounded: explain the portfolio state, strategy leadership, "
                "cost/turnover implications, risk controls, and the next monitoring actions. Keep the main "
                "narrative around 250-350 words."
            ),
            user=json.dumps(payload, default=str),
            schema=schema,
        )
        return {
            "headline": _strategy_lab_clean_llm_text(result.get("headline") or fallback["headline"]),
            "narrative": _strategy_lab_clean_llm_text(result.get("narrative") or fallback["narrative"]),
            "portfolio_readout": _strategy_lab_clean_llm_text(result.get("portfolio_readout") or fallback["portfolio_readout"]),
            "strategy_readout": _strategy_lab_clean_llm_text(result.get("strategy_readout") or fallback["strategy_readout"]),
            "turnover_readout": _strategy_lab_clean_llm_text(result.get("turnover_readout") or fallback["turnover_readout"]),
            "action_plan": _strategy_lab_clean_llm_list(result.get("action_plan"), fallback["action_plan"], 5),
            "focus": _strategy_lab_clean_llm_list(result.get("focus"), fallback["focus"], 4),
            "risks": _strategy_lab_clean_llm_list(result.get("risks"), fallback["risks"], 4),
            "source": "LLM",
        }
    except Exception as exc:
        return {**fallback, "source": f"deterministic fallback; LLM unavailable: {type(exc).__name__}"}


def _strategy_lab_deterministic_narrative(summary: dict, rows: list[dict], paper: dict, positions: list[dict]) -> dict[str, object]:
    top = rows[0] if rows else {}
    selected = paper.get("selected_strategy_id") or top.get("strategy_id") or "n/a"
    total_return = _float_or_none(top.get("total_return_pct"))
    max_dd = _float_or_none(top.get("max_drawdown_pct"))
    profit_factor = _float_or_none(top.get("profit_factor"))
    today_pnl = _float_or_none(paper.get("today_pnl"))
    open_positions = int(_float_or_none(paper.get("open_positions")) or len(positions or []))
    headline = f"{selected} is the current paper strategy leader."
    narrative = (
        f"The selected strategy is carrying {open_positions} open paper positions"
        f" with latest daily P&L of ₹{_fmt_num(today_pnl, 2)}. "
        f"Its backtest profile shows {_fmt_pct(total_return, 2)} return, "
        f"{_fmt_pct_plain(max_dd, 2)} max drawdown, and {_fmt_num(profit_factor, 2)} profit factor after configured costs."
    )
    portfolio_readout = (
        f"The paper book is using `{selected}` with {open_positions} open positions as of "
        f"{_fmt_text(paper.get('as_of'))}. Latest daily P&L is ₹{_fmt_num(today_pnl, 2)}, "
        f"today return is {_fmt_pct(paper.get('today_return_pct'), 2)}, and total unrealized P&L is "
        f"₹{_fmt_num(paper.get('total_unrealized_pnl'), 2)}."
    )
    strategy_readout = (
        f"The current leader's replay profile is {_fmt_pct(total_return, 2)} total return, "
        f"{_fmt_pct_plain(max_dd, 2)} max drawdown, {_fmt_num(profit_factor, 2)} profit factor, "
        f"and ₹{_fmt_num(top.get('expectancy'), 0)} expectancy across {top.get('fills', 0)} fills."
    )
    turnover_readout = (
        f"Turnover for the leader is {_fmt_pct_plain(top.get('turnover_pct'), 1)} with "
        f"{_fmt_pct_plain(top.get('cost_drag_pct'), 2)} modeled cost drag. This means the strategy is "
        "profitable in the replay but must stay under turnover caps before it is trusted for larger paper sizing."
    )
    action_plan = [
        "Keep the primary strategy live in paper mode while it remains leader after costs and drawdown checks.",
        "Review current stops, targets, and concentration before allowing add orders.",
        "Compare the next daily P&L report against turnover, fills, and cost drag rather than return alone.",
        "Quarantine strategies whose churn rises without a matching improvement in profit factor or expectancy.",
    ]
    focus = [
        "Keep the selected strategy under observation while it remains rank 1 after cost and drawdown checks.",
        "Review open positions against stop levels before adding fresh exposure.",
        "Compare daily P&L against drawdown and turnover rather than raw return alone.",
    ]
    risks = [
        "Backtest leadership may be unstable when turnover or cost drag rises.",
        "Open positions remain exposed to gap risk because fills are modeled on EOD/next-open data.",
    ]
    if positions:
        largest = max(positions, key=lambda row: _float_or_none(row.get("market_value")) or 0.0)
        risks.append(f"Largest current paper exposure is {largest.get('symbol', 'n/a')}; check concentration before adding.")
    return {
        "headline": headline,
        "narrative": narrative,
        "portfolio_readout": portfolio_readout,
        "strategy_readout": strategy_readout,
        "turnover_readout": turnover_readout,
        "action_plan": action_plan,
        "focus": focus,
        "risks": risks,
    }


def _md_cell(value) -> str:
    return _fmt_text(value).replace("|", "\\|").replace("\n", " ")


def _strategy_lab_clean_llm_text(value) -> str:
    return _fmt_text(value).replace("$", "₹")


def _strategy_lab_clean_llm_list(values, fallback_values, limit: int) -> list[str]:
    raw_values = values or fallback_values or []
    return [_strategy_lab_clean_llm_text(item) for item in raw_values][:limit]


def _strategy_lab_llm_enabled() -> bool:
    if os.environ.get("OPENAI_API_KEY") or os.environ.get("AGENT_ADDA_STRATEGY_LAB_LLM") == "1":
        return True
    env_path = ROOT / ".env"
    if not env_path.exists():
        return False
    try:
        return any(
            line.strip().startswith("OPENAI_API_KEY=") and line.split("=", 1)[1].strip().strip('"').strip("'")
            for line in env_path.read_text(encoding="utf-8").splitlines()
        )
    except OSError:
        return False


def _strategy_lab_strategy_catalog() -> dict[str, dict[str, str]]:
    return {
        "stage2_continuation_v1": {
            "what": "A Weinstein Stage 2 continuation model that stays with established uptrends after trend and fundamental confirmation.",
            "entry": "Stage 2, close above SMA50, SMA50 above SMA200, RSI in a constructive band, volume confirmation, and non-negative sales/PAT growth.",
            "risk": "ATR stop, pullback adds above SMA20, and exits on Stage 3/4, close below SMA50, or trailing stop.",
            "regime": "Best when broad market breadth supports sustained uptrends.",
            "caveat": "Can lag fast breakouts because it waits for established trend quality.",
        },
        "donchian_turtle_breakout_v1": {
            "what": "A trend-following breakout proxy inspired by Donchian/Turtle systems.",
            "entry": "Price above longer moving averages, SMA50 above SMA200, high relative strength, and volume expansion.",
            "risk": "ATR stop, breakout adds above SMA20, and exits below SMA50 or trailing stop.",
            "regime": "Best when breakouts continue and leaders trend cleanly after the signal.",
            "caveat": "Whipsaws when breakouts fail quickly or breadth is narrow.",
        },
        "moving_average_trend_v1": {
            "what": "A simple moving-average stack trend follower.",
            "entry": "Close above SMA20, SMA20 above SMA50, and SMA50 above SMA200.",
            "risk": "ATR stop with no adds; exits when price loses SMA50 or SMA20 breaks below SMA50.",
            "regime": "Best in broad, orderly advances with persistent trend alignment.",
            "caveat": "Low selectivity can create many trades and moderate cost drag.",
        },
        "momentum_rotation_v1": {
            "what": "A relative-strength rotation strategy that favors the strongest stocks with fresh fundamental support.",
            "entry": "High relative strength, RSI in an actionable zone, close above SMA50, volume confirmation, and non-negative sales/PAT growth.",
            "risk": "ATR stop with no adds; exits when relative strength weakens or close falls below SMA50.",
            "regime": "Best when leadership rotates into new high-RS groups without broad market breakdown.",
            "caveat": "Can chase extended names if the rotation is late-cycle.",
        },
        "vcp_breakout_v1": {
            "what": "A deterministic VCP Breakout model that looks for Stage 2 names emerging from contraction with volume expansion.",
            "entry": "Stage 2, close above SMA20, SMA20 above SMA50, strong volume ratio, constructive RSI, and fresh positive fundamentals.",
            "risk": "Tighter ATR stop, adds only when volume expansion confirms, and exits below SMA20 or RSI breakdown.",
            "regime": "Best when high-quality bases resolve upward with institutional volume.",
            "caveat": "High turnover is possible because VCP entries and tight exits recycle capital quickly.",
        },
        "persisted_vcp_picks_v1": {
            "what": "A persisted VCP Picks strategy that trades the stored Stage 2/VCP picks table instead of recomputing the signal only inside the replay.",
            "entry": "Requires `scores.stage2_vcp_picks`, Stage 2, VCP score threshold, close above SMA20, and RSI confirmation.",
            "risk": "Tighter ATR stop, adds only for very high VCP score, and exits on stage deterioration, close below SMA20, or RSI breakdown.",
            "regime": "Best for auditability because the exact daily VCP candidates are stored before the backtest consumes them.",
            "caveat": "Performance depends on quality and completeness of the daily persisted VCP pick table.",
        },
        "darvas_box_breakout_v1": {
            "what": "A Darvas-style breakout model focused on Stage 2 stocks with strength and volume confirmation.",
            "entry": "Stage 2, close above SMA50, relative strength above threshold, and volume expansion.",
            "risk": "ATR stop with exits below SMA50, RS weakness, or trailing stop.",
            "regime": "Best when consolidation breakouts are followed by sustained price discovery.",
            "caveat": "Can underperform if breakouts repeatedly fail after the initial volume burst.",
        },
        "mean_reversion_uptrend_v1": {
            "what": "A pullback strategy that buys short-term weakness inside a longer-term uptrend.",
            "entry": "Close above SMA200, SMA50 above SMA200, close below SMA20, and RSI in a pullback zone.",
            "risk": "Tighter ATR stop with exits on rebound above SMA20 or failure below SMA50.",
            "regime": "Best in rising but choppy markets where pullbacks mean-revert quickly.",
            "caveat": "Can produce very high churn and weak expectancy when pullbacks become trend breaks.",
        },
        "minervini_trend_template_v1": {
            "what": "A stricter Minervini-style trend template combining Stage 2, moving-average hierarchy, relative strength, and growth fundamentals.",
            "entry": "Stage 2, price above key moving averages, high RS, EPS/sales/PAT growth, OPM improvement, and volume confirmation.",
            "risk": "ATR stop, trend adds above SMA20, and exits on SMA50/RS/stage deterioration.",
            "regime": "Best when true growth leaders are available with clean trend and earnings confirmation.",
            "caveat": "Strict filters can produce no trades in windows where fundamentals or trend quality are sparse.",
        },
    }


def _strategy_lab_strategy_specs_by_id() -> dict[str, dict]:
    try:
        from portfolio.engine.strategy_library import built_in_strategy_specs

        return {str(spec.get("strategy_id")): spec for spec in built_in_strategy_specs()}
    except Exception:
        return {}


def _strategy_lab_strategy_name(strategy_id: str, specs: dict[str, dict], catalog: dict[str, dict[str, str]]) -> str:
    spec = specs.get(strategy_id) or {}
    name = spec.get("name")
    if name:
        return str(name)
    return strategy_id.replace("_", " ").replace(" v1", "").title()


def _strategy_lab_rule_text(rule: dict) -> str:
    indicator = str(rule.get("indicator") or "").replace("_", " ").upper()
    operator = str(rule.get("operator") or "").replace("_", " ")
    value = rule.get("value")
    if isinstance(value, list):
        value_text = " and ".join(_fmt_text(item) for item in value)
    else:
        value_text = _fmt_text(value).replace("_", " ").upper()
    return f"{indicator} {operator} {value_text}".strip()


def _strategy_lab_rule_group_text(group: dict | None, *, joiner: str = " AND ") -> str:
    if not isinstance(group, dict):
        return "Not specified in the executable strategy spec."
    rules = group.get("all") or group.get("any") or []
    if not rules:
        return "Not specified in the executable strategy spec."
    return joiner.join(_strategy_lab_rule_text(rule) for rule in rules if isinstance(rule, dict))


def _strategy_lab_add_rules_text(spec: dict) -> str:
    add_rules = [rule for rule in spec.get("add_rules") or [] if isinstance(rule, dict)]
    if not add_rules:
        return "No pyramiding configured; additions are disabled after initial entry."
    parts = []
    for rule in add_rules:
        condition = _strategy_lab_rule_text(rule)
        size = _fmt_pct_plain(rule.get("size_pct"), 1)
        risk = _fmt_pct_plain(rule.get("risk_per_trade_pct"), 2) if rule.get("risk_per_trade_pct") is not None else "strategy risk budget"
        kind = str(rule.get("kind") or "add").replace("_", " ")
        parts.append(f"{kind}: add {size} when {condition}; incremental risk {risk}.")
    return " ".join(parts)


def _strategy_lab_stop_loss_text(spec: dict, fallback: dict[str, str]) -> str:
    risk = spec.get("risk") if isinstance(spec.get("risk"), dict) else {}
    initial_stop = risk.get("initial_stop") if isinstance(risk.get("initial_stop"), dict) else {}
    if initial_stop.get("type") == "atr":
        multiple = _fmt_num(initial_stop.get("multiple"), 2)
        indicator = str(initial_stop.get("indicator") or "atr_14").replace("_", " ").upper()
        return f"Initial protective stop is {multiple}x {indicator} from entry; risk per trade is {_fmt_pct_plain(risk.get('risk_per_trade_pct'), 2)}."
    return fallback.get("risk") or "Uses the configured protective stop from the strategy spec."


def _strategy_lab_target_text(spec: dict) -> str:
    exit_text = _strategy_lab_rule_group_text(spec.get("exit"), joiner=" OR ")
    return (
        "No fixed price target is configured. Profits are managed by trend continuation, adds where configured, "
        f"and rule exits: {exit_text}"
    )


def _strategy_lab_position_sizing_text(spec: dict) -> str:
    risk = spec.get("risk") if isinstance(spec.get("risk"), dict) else {}
    risk_pct = _fmt_pct_plain(risk.get("risk_per_trade_pct"), 2) if risk else "strategy risk budget"
    max_position = _fmt_pct_plain(risk.get("max_position_pct"), 1) if risk else "strategy cap"
    return f"Size each entry from stop distance and risk budget: {risk_pct} portfolio risk per trade, capped at {max_position} of portfolio value."


def _strategy_lab_strategy_playbook(rows: list[dict]) -> str:
    catalog = _strategy_lab_strategy_catalog()
    specs = _strategy_lab_strategy_specs_by_id()
    ordered_ids: list[str] = []
    for row in rows:
        sid = str(row.get("strategy_id") or "")
        if sid and sid not in ordered_ids:
            ordered_ids.append(sid)
    for sid in specs:
        if sid not in ordered_ids:
            ordered_ids.append(sid)
    for sid in catalog:
        if sid not in ordered_ids:
            ordered_ids.append(sid)

    cards = []
    for sid in ordered_ids:
        spec = specs.get(sid) or {}
        details = catalog.get(sid) or {
            "what": "Built-in paper strategy.",
            "entry": "Uses the configured strategy specification.",
            "risk": "Uses configured ATR risk, add rules, and exit rules.",
            "regime": "Depends on the signal family.",
            "caveat": "Review the strategy specification before sizing.",
        }
        name = _strategy_lab_strategy_name(sid, specs, catalog)
        entry_text = _strategy_lab_rule_group_text(spec.get("entry")) if spec else details.get("entry")
        exit_text = _strategy_lab_rule_group_text(spec.get("exit"), joiner=" OR ") if spec else details.get("risk")
        risk = spec.get("risk") if isinstance(spec.get("risk"), dict) else {}
        cards.append(
            '<div class="aa-playbook-card">'
            f'<button type="button" class="aa-playbook-header" onclick="toggleStrategyLabWindow(this)">'
            f'<span><strong>{_html.escape(name)}</strong><em>{_html.escape(sid)}</em></span>'
            f'<span class="aa-window-caret">▾</span></button>'
            '<div class="aa-playbook-body">'
            f'<p><strong>What it is:</strong> {_html.escape(_fmt_text(details.get("what")))}</p>'
            '<div class="aa-playbook-grid">'
            f'<div><h4>Entry Criteria</h4><p>{_html.escape(_fmt_text(entry_text))}</p></div>'
            f'<div><h4>Add / Pyramid Criteria</h4><p>{_html.escape(_strategy_lab_add_rules_text(spec))}</p></div>'
            f'<div><h4>Exit Criteria</h4><p>{_html.escape(_fmt_text(exit_text))}</p></div>'
            f'<div><h4>Stop Loss</h4><p>{_html.escape(_strategy_lab_stop_loss_text(spec, details))}</p></div>'
            f'<div><h4>Targets / Profit Taking</h4><p>{_html.escape(_strategy_lab_target_text(spec))}</p></div>'
            f'<div><h4>Position Sizing</h4><p>{_html.escape(_strategy_lab_position_sizing_text(spec))}</p></div>'
            f'<div><h4>Best Regime</h4><p>{_html.escape(_fmt_text(details.get("regime")))}</p></div>'
            f'<div><h4>Caveat</h4><p>{_html.escape(_fmt_text(details.get("caveat")))}</p></div>'
            '</div>'
            '<table class="aa-playbook-mini">'
            f'<tr><td>Risk Per Trade</td><td>{_html.escape(_fmt_pct_plain(risk.get("risk_per_trade_pct"), 2) if risk else "n/a")}</td></tr>'
            f'<tr><td>Max Position</td><td>{_html.escape(_fmt_pct_plain(risk.get("max_position_pct"), 1) if risk else "n/a")}</td></tr>'
            f'<tr><td>Universe</td><td>{_html.escape(json.dumps(spec.get("universe") or {}, sort_keys=True) if spec else "n/a")}</td></tr>'
            '</table>'
            '</div></div>'
        )
    return "\n".join(
        [
            "## Strategy Playbook",
            "",
            (
                '<div class="aa-lab-section aa-strategy-playbook">'
                '<div class="aa-lab-hdr"><strong>Strategy Playbook</strong>'
                '<span>Executable rules, risk sizing, add logic, exits, and target handling</span></div>'
                '<div class="aa-playbook-intro">Each card maps the strategy narrative back to the current built-in strategy specification used by the paper-trading replay.</div>'
                f'{"".join(cards)}'
                '</div>'
            ),
        ]
    )


def _strategy_lab_council_fallback(
    summary: dict,
    rows: list[dict],
    paper: dict,
    positions: list[dict],
    turnover_rows: list[dict[str, object]],
    *,
    source: str = "deterministic fallback",
) -> dict[str, object]:
    top = rows[0] if rows else {}
    second = rows[1] if len(rows) > 1 else {}
    selected = paper.get("selected_strategy_id") or top.get("strategy_id") or "n/a"
    high_turnover = max(rows, key=lambda row: _float_or_none(row.get("turnover_pct")) or 0.0) if rows else {}
    weak_pf = [
        row for row in rows
        if (_float_or_none(row.get("profit_factor")) or 0.0) < 1.0 and int(_float_or_none(row.get("fills")) or 0) > 0
    ]
    persisted = next((row for row in rows if row.get("strategy_id") == "persisted_vcp_picks_v1"), None)
    open_positions = int(_float_or_none(paper.get("open_positions")) or len(positions or []))
    filled_turnover = ""
    if turnover_rows and selected:
        selected_turnover = next((row for row in turnover_rows if row.get("strategy_id") == selected), turnover_rows[0])
        filled_turnover = f" Total filled notional was ₹{_fmt_num(selected_turnover.get('total_notional'), 0)}."

    quant = (
        f"{top.get('strategy_id', 'n/a')} leads the replay with {_fmt_pct(top.get('total_return_pct'), 2)} return, "
        f"{_fmt_pct_plain(top.get('max_drawdown_pct'), 2)} max drawdown, {_fmt_num(top.get('profit_factor'), 2)} profit factor, "
        f"and ₹{_fmt_num(top.get('expectancy'), 0)} expectancy across {top.get('fills', 0)} fills."
    )
    if second:
        quant += (
            f" The nearest challenger is {second.get('strategy_id')} at {_fmt_pct(second.get('total_return_pct'), 2)} "
            f"with {_fmt_num(second.get('profit_factor'), 2)} profit factor."
        )
    if persisted:
        quant += (
            f" Persisted VCP Picks ranks {persisted.get('rank')} with {_fmt_pct(persisted.get('total_return_pct'), 2)} return, "
            "which validates that the stored VCP pick table is usable for replay."
        )

    risk = (
        f"Turnover remains the main constraint. {high_turnover.get('strategy_id', 'n/a')} shows "
        f"{_fmt_pct_plain(high_turnover.get('turnover_pct'), 1)} turnover and {_fmt_pct_plain(high_turnover.get('cost_drag_pct'), 2)} cost drag."
        f"{filled_turnover} Strategies should be capped by positions, sector exposure, and maximum daily churn before paper size is increased."
    )
    portfolio_manager = (
        f"Keep {selected} as the active paper book only while it remains top-ranked after costs and drawdown checks. "
        f"The book has {open_positions} open positions as of {_fmt_text(paper.get('as_of'))}; new adds should be allowed only when stop distance and concentration remain acceptable."
    )
    data_steward = (
        "The replay uses EOD bars, next-open fill assumptions, point-in-time stage snapshots, quarterly-result features, "
        "and persisted VCP picks where the strategy requires `scores.stage2_vcp_picks`. The output should stay paper-only and auditable."
    )
    quarantine = ", ".join(str(row.get("strategy_id")) for row in weak_pf[:4]) or "none"
    chair = (
        f"Council recommendation: continue with {selected} as the primary paper strategy, monitor "
        f"{second.get('strategy_id', 'the runner-up') if second else 'the runner-up'} as a constrained challenger, "
        f"and quarantine weak profit-factor strategies ({quarantine}) until they improve after costs."
    )
    return {
        "source": source,
        "quant_agent": quant,
        "risk_agent": risk,
        "portfolio_manager": portfolio_manager,
        "data_steward": data_steward,
        "chair_recommendation": chair,
        "recommendations": [
            "Use the top strategy as the paper baseline, not as live-trading instruction.",
            "Promote a challenger only after it beats the leader on return, drawdown, cost drag, and turnover.",
            "Set explicit guardrails for max open positions, sector concentration, daily turnover, and drawdown pause.",
            "Review persisted VCP Picks separately because it is the cleanest audit trail from daily signals to backtest trades.",
        ],
    }


def _strategy_lab_council_deliberation(
    summary: dict,
    rows: list[dict],
    paper: dict,
    positions: list[dict],
    turnover_rows: list[dict[str, object]],
) -> dict[str, object]:
    fallback = _strategy_lab_council_fallback(summary, rows, paper, positions, turnover_rows)
    use_llm = _strategy_lab_llm_enabled()
    if not use_llm:
        return fallback

    schema = {
        "type": "object",
        "required": [
            "quant_agent",
            "risk_agent",
            "portfolio_manager",
            "data_steward",
            "chair_recommendation",
            "recommendations",
        ],
        "properties": {
            "quant_agent": {"type": "string"},
            "risk_agent": {"type": "string"},
            "portfolio_manager": {"type": "string"},
            "data_steward": {"type": "string"},
            "chair_recommendation": {"type": "string"},
            "recommendations": {"type": "array", "items": {"type": "string"}},
        },
    }
    payload = {
        "run": {
            "window": f"{summary.get('start_date')} to {summary.get('end_date')}",
            "latest_eod_date": summary.get("latest_eod_date"),
            "slippage_bps": summary.get("slippage_bps"),
            "brokerage_bps": summary.get("brokerage_bps"),
            "fundamental_coverage": summary.get("fundamental_coverage") or {},
        },
        "leaderboard": rows,
        "paper_portfolio": paper,
        "top_positions": positions[:10],
        "turnover": turnover_rows,
        "strategy_playbook": _strategy_lab_strategy_catalog(),
    }
    try:
        from terminal.research_council.llm_client import call_llm_json

        result = call_llm_json(
            system=(
                "You are a buy-side paper-trading strategy council for an Indian NSE paper portfolio. "
                "Deliberate using four seats: Quant Agent, Risk Agent, Portfolio Manager, and Data Steward. "
                "Use only the supplied strategy-lab artifacts. Use INR/₹ for all money values, never USD or $. "
                "Compare strategies, explain rationale, identify weaknesses, and make paper-trading "
                "recommendations. Do not give live investment advice."
            ),
            user=json.dumps(payload, default=str),
            schema=schema,
        )
        return {
            "source": "LLM",
            "quant_agent": _strategy_lab_clean_llm_text(result.get("quant_agent") or fallback["quant_agent"]),
            "risk_agent": _strategy_lab_clean_llm_text(result.get("risk_agent") or fallback["risk_agent"]),
            "portfolio_manager": _strategy_lab_clean_llm_text(result.get("portfolio_manager") or fallback["portfolio_manager"]),
            "data_steward": _strategy_lab_clean_llm_text(result.get("data_steward") or fallback["data_steward"]),
            "chair_recommendation": _strategy_lab_clean_llm_text(result.get("chair_recommendation") or fallback["chair_recommendation"]),
            "recommendations": _strategy_lab_clean_llm_list(result.get("recommendations"), fallback["recommendations"], 6),
        }
    except Exception as exc:
        return _strategy_lab_council_fallback(
            summary,
            rows,
            paper,
            positions,
            turnover_rows,
            source=f"deterministic fallback; LLM unavailable: {type(exc).__name__}",
        )


def _strategy_lab_council_markdown(council: dict[str, object]) -> str:
    md = [
        "## Council Deliberations",
        "",
        f"*Council source: {_fmt_text(council.get('source'))}.*",
        "",
        "| Council Seat | Deliberation |",
        "|---|---|",
        f"| **Quant Agent** | {_md_cell(council.get('quant_agent'))} |",
        f"| **Risk Agent** | {_md_cell(council.get('risk_agent'))} |",
        f"| **Portfolio Manager** | {_md_cell(council.get('portfolio_manager'))} |",
        f"| **Data Steward** | {_md_cell(council.get('data_steward'))} |",
        "",
        "### Council Chair Recommendation",
        "",
        str(council.get("chair_recommendation") or "No recommendation available."),
        "",
    ]
    recommendations = list(council.get("recommendations") or [])
    if recommendations:
        md.extend(["### Recommendations", ""])
        for item in recommendations:
            md.append(f"- {item}")
        md.append("")
    return "\n".join(md).strip()


def _strategy_lab_verdict(row: dict, rank: int | None = None) -> tuple[str, str]:
    strategy_id = str(row.get("strategy_id") or "")
    fills = int(_float_or_none(row.get("fills")) or 0)
    total_return = _float_or_none(row.get("total_return_pct")) or 0.0
    max_dd = _float_or_none(row.get("max_drawdown_pct")) or 0.0
    profit_factor = _float_or_none(row.get("profit_factor")) or 0.0
    turnover = _float_or_none(row.get("turnover_pct")) or 0.0
    if fills <= 0:
        return "Inactive", "No qualifying entries fired in this backtest window."
    if turnover >= 10000 or (total_return < 0 and turnover >= 3000):
        return "Quarantine", "Turnover and cost drag are too high for the return profile."
    if rank == 1:
        return "Primary", "Best current risk-adjusted paper strategy after drawdown and activity checks."
    if total_return >= 35 and max_dd >= 30:
        return "High Return / High Drawdown", "Strong raw return but drawdown is too large for primary allocation."
    if profit_factor < 1.0:
        return "Watchlist - Weak PF", "Profit factor is below 1.0 after modeled costs."
    if total_return > 0:
        return "Monitor", "Positive result, but lower risk-adjusted score than the leader."
    return "Avoid", "Negative return or weak cost-adjusted profile."


def _strategy_lab_turnover_rows(summary: dict, summary_path: Path, rows: list[dict]) -> list[dict[str, object]]:
    initial_capital = _float_or_none(summary.get("initial_capital")) or 0.0
    out: list[dict[str, object]] = []
    for row in rows:
        strategy_id = str(row.get("strategy_id") or "")
        state_path = _strategy_lab_replay_state_path(summary, summary_path, strategy_id)
        fills = []
        try:
            fills = json.loads(state_path.read_text(encoding="utf-8")).get("fills", [])
        except (OSError, json.JSONDecodeError):
            fills = []
        buy_notional = 0.0
        sell_notional = 0.0
        symbols: set[str] = set()
        for fill in fills:
            qty = _float_or_none(fill.get("quantity")) or 0.0
            price = _float_or_none(fill.get("price")) or 0.0
            notional = qty * price
            symbols.add(str(fill.get("symbol") or ""))
            if str(fill.get("side") or "").upper() == "SELL":
                sell_notional += notional
            else:
                buy_notional += notional
        total_notional = buy_notional + sell_notional
        turnover_pct = (total_notional / initial_capital * 100.0) if initial_capital else (_float_or_none(row.get("turnover_pct")) or 0.0)
        out.append(
            {
                "strategy_id": strategy_id,
                "buy_notional": buy_notional,
                "sell_notional": sell_notional,
                "total_notional": total_notional,
                "turnover_pct": turnover_pct,
                "fills": len(fills) or int(_float_or_none(row.get("fills")) or 0),
                "symbols": len([symbol for symbol in symbols if symbol]),
            }
        )
    return out


def _strategy_lab_widget(title: str, body: str) -> str:
    return (
        '<div class="aa-chart" style="margin:14px 0;padding:14px 16px;border:1px solid #e2e8f0;'
        'border-radius:8px;background:#ffffff;box-shadow:0 1px 3px rgba(15,23,42,.08);">'
        f'<div style="font-size:13px;font-weight:800;color:#1e3a5f;margin-bottom:8px;">{_html.escape(title)}</div>'
        f'{body}</div>'
    )


def _strategy_lab_detail_assets() -> str:
    return (
        '<div class="aa-strategy-lab-assets">'
        '<style>'
        '.aa-lab-section{margin:18px 0;border:1px solid #dbe3ef;border-radius:10px;background:#fff;box-shadow:0 1px 3px rgba(15,23,42,.08);overflow:hidden}'
        '.aa-lab-hdr{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:13px 16px;background:#1e3a5f;color:#fff}'
        '.aa-lab-hdr strong{font-size:14px}.aa-lab-hdr span{font-size:12px;opacity:.78}'
        '.aa-lab-table{width:100%;border-collapse:collapse;font-size:12px}.aa-lab-table th{background:#f8fafc;color:#475569;text-transform:uppercase;font-size:10px;letter-spacing:.04em;padding:8px 10px;text-align:left;border-bottom:1px solid #e2e8f0}'
        '.aa-lab-table td{padding:8px 10px;border-bottom:1px solid #eef2f7;vertical-align:top}.aa-lab-table td.num,.aa-lab-table th.num{text-align:right}'
        '.aa-strategy-row,.aa-position-row{cursor:pointer}.aa-strategy-row:hover,.aa-position-row:hover{background:#f8fafc}'
        '.aa-detail-row{display:none;background:#f8fafc}.aa-detail-row.open{display:table-row}.aa-detail-cell{padding:14px!important;background:#f8fafc!important}'
        '.aa-detail-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.aa-detail-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:12px}'
        '.aa-detail-card h4{margin:0 0 8px;font-size:11px;color:#334155;text-transform:uppercase;letter-spacing:.06em}.aa-detail-card table{width:100%;border-collapse:collapse}.aa-detail-card td{padding:4px 0;border:0;font-size:11px}.aa-detail-card td:first-child{color:#64748b;padding-right:10px}.aa-detail-card td:last-child{text-align:right;color:#0f172a;font-weight:650}'
        '.aa-pill{display:inline-block;padding:2px 7px;border-radius:999px;font-size:10px;font-weight:800}.aa-pill-primary{background:#dbeafe;color:#1d4ed8}.aa-pill-good{background:#dcfce7;color:#15803d}.aa-pill-warn{background:#fef3c7;color:#92400e}.aa-pill-bad{background:#fee2e2;color:#b91c1c}.aa-row-hint{color:#64748b;font-size:10px;margin-left:6px}'
        '.aa-lab-tabs{margin:18px 0 24px}.aa-lab-tabbar{position:sticky;top:56px;z-index:30;display:flex;gap:8px;flex-wrap:wrap;padding:10px;background:#eef4fb;border:1px solid #dbe3ef;border-radius:10px;margin-bottom:14px}'
        '.aa-lab-tab{border:1px solid #cbd5e1;background:#fff;color:#334155;border-radius:8px;padding:8px 12px;font-size:12px;font-weight:800;cursor:pointer}.aa-lab-tab.active{background:#1e3a5f;color:#fff;border-color:#1e3a5f}.aa-lab-tab-panel{display:none}.aa-lab-tab-panel.active{display:block}'
        '.aa-window{border:1px solid #dbe3ef;border-radius:10px;background:#fff;box-shadow:0 1px 3px rgba(15,23,42,.08);margin:12px 0;overflow:hidden}.aa-window-header{width:100%;border:0;background:#f8fafc;color:#0f172a;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;cursor:pointer;text-align:left}.aa-window-title{font-size:13px;font-weight:850}.aa-window-meta{font-size:11px;color:#64748b;font-weight:650}.aa-window-body{padding:14px}.aa-window.collapsed>.aa-window-body{display:none}.aa-window-caret{font-size:13px;color:#64748b}.aa-window.collapsed .aa-window-caret{transform:rotate(-90deg)}'
        '.aa-subwindow{border:1px solid #e2e8f0;border-radius:8px;background:#fff;margin:10px 0;overflow:hidden}.aa-subwindow-header{width:100%;border:0;background:#f8fafc;color:#334155;display:flex;justify-content:space-between;gap:10px;padding:10px 12px;font-size:12px;font-weight:800;cursor:pointer;text-align:left}.aa-subwindow-body{padding:12px}.aa-subwindow.collapsed>.aa-subwindow-body{display:none}'
        '.aa-strategy-playbook{border-radius:10px}.aa-playbook-intro{padding:12px 16px;color:#475569;font-size:12px;border-bottom:1px solid #e2e8f0;background:#f8fafc}.aa-playbook-card{border-bottom:1px solid #e2e8f0;background:#fff}.aa-playbook-card:last-child{border-bottom:0}.aa-playbook-header{width:100%;border:0;background:#fff;color:#0f172a;display:flex;justify-content:space-between;align-items:center;gap:12px;padding:13px 16px;cursor:pointer;text-align:left}.aa-playbook-header strong{display:block;font-size:13px}.aa-playbook-header em{display:block;font-style:normal;font-size:10px;color:#64748b;margin-top:2px}.aa-playbook-body{padding:0 16px 16px}.aa-playbook-card.collapsed>.aa-playbook-body{display:none}.aa-playbook-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px;margin-top:10px}.aa-playbook-grid>div{border:1px solid #e2e8f0;border-radius:8px;padding:10px;background:#f8fafc}.aa-playbook-grid h4{margin:0 0 6px;font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:#475569}.aa-playbook-grid p,.aa-playbook-body p{font-size:12px;color:#1f2937;margin:0}.aa-playbook-mini{width:100%;border-collapse:collapse;margin-top:12px;font-size:11px}.aa-playbook-mini td{padding:6px 8px;border-top:1px solid #e2e8f0}.aa-playbook-mini td:first-child{color:#64748b}.aa-playbook-mini td:last-child{text-align:right;font-weight:700;color:#0f172a}'
        '</style>'
        '<script>'
        'function toggleStrategyLabDetail(id){var el=document.getElementById(id);if(!el)return;el.classList.toggle("open");}'
        'function toggleStrategyLabWindow(btn){var w=btn&&btn.closest?btn.closest(".aa-window,.aa-subwindow,.aa-playbook-card"):null;if(w)w.classList.toggle("collapsed");}'
        'function switchStrategyLabTab(tab){document.querySelectorAll(".aa-lab-tab").forEach(function(b){b.classList.toggle("active",b.dataset.tab===tab);});document.querySelectorAll(".aa-lab-tab-panel").forEach(function(p){p.classList.toggle("active",p.dataset.tab===tab);});}'
        'function buildStrategyLabTabs(){var body=document.getElementById("report-body");if(!body||body.querySelector(".aa-lab-tabbar"))return;var h2s=Array.from(body.children).filter(function(el){return el.tagName==="H2";});if(!h2s.length)return;'
        'function tabFor(title){var t=(title||"").toLowerCase();if(t.indexOf("daily paper portfolio")>=0)return"paper";if(t.indexOf("risk-adjusted")>=0||t.indexOf("cost and turnover")>=0||t.indexOf("recommended paper")>=0)return"risk";if(t.indexOf("run artifacts")>=0)return"artifacts";if(t.indexOf("strategy playbook")>=0)return"playbook";if(t.indexOf("strategy leaderboard")>=0||t.indexOf("strategy verdict")>=0||t.indexOf("detailed analysis")>=0||t.indexOf("market and run")>=0||t.indexOf("fundamental and quarterly")>=0||t.indexOf("charts and visual")>=0)return"strategy";return"overview";}'
        'var labels={overview:"Overview",strategy:"Strategy Lab",playbook:"Strategy Playbook",paper:"Paper Trading",risk:"Risk & Turnover",artifacts:"Artifacts"};var shell=document.createElement("div");shell.className="aa-lab-tabs";shell.innerHTML=\'<div class="aa-lab-tabbar" role="tablist"></div><div class="aa-lab-tab-panels"></div>\';body.insertBefore(shell,h2s[0]);var bar=shell.querySelector(".aa-lab-tabbar");var panels=shell.querySelector(".aa-lab-tab-panels");var panelByKey={};["overview","strategy","playbook","paper","risk","artifacts"].forEach(function(key){var b=document.createElement("button");b.type="button";b.className="aa-lab-tab"+(key==="overview"?" active":"");b.dataset.tab=key;b.textContent=labels[key];b.onclick=function(){switchStrategyLabTab(key);};bar.appendChild(b);var p=document.createElement("div");p.className="aa-lab-tab-panel"+(key==="overview"?" active":"");p.dataset.tab=key;panels.appendChild(p);panelByKey[key]=p;});'
        'function wrapH3Sections(parent){var h3s=Array.from(parent.children).filter(function(el){return el.tagName==="H3";});if(!h3s.length)return;var first=h3s[0];var nodes=Array.from(parent.children);var moving=[];var started=false;nodes.forEach(function(n){if(n===first)started=true;if(started)moving.push(n);});moving.forEach(function(n){if(n.parentNode===parent)parent.removeChild(n);});var current=null;var currentBody=null;moving.forEach(function(n){if(n.tagName==="H3"){current=document.createElement("div");current.className="aa-subwindow collapsed";var title=n.textContent.trim();current.innerHTML=\'<button type="button" class="aa-subwindow-header" onclick="toggleStrategyLabWindow(this)"><span></span><span>▾</span></button><div class="aa-subwindow-body"></div>\';current.querySelector("span").textContent=title;currentBody=current.querySelector(".aa-subwindow-body");parent.appendChild(current);}else if(currentBody){currentBody.appendChild(n);}else{parent.appendChild(n);}});var firstSub=parent.querySelector(".aa-subwindow");if(firstSub)firstSub.classList.remove("collapsed");}'
        'var nodes=Array.from(body.children);var moving=[];var started=false;nodes.forEach(function(n){if(n===shell)return;if(n.tagName==="H2")started=true;if(started)moving.push(n);});moving.forEach(function(n){if(n.parentNode===body)body.removeChild(n);});var currentWin=null;var currentBody=null;var openSeen={};moving.forEach(function(n){if(n.tagName==="H2"){var title=n.textContent.trim();var key=tabFor(title);currentWin=document.createElement("div");currentWin.className="aa-window";currentWin.id=n.id||"";var collapsed=(key!=="overview"&&!openSeen[key]);if(collapsed)currentWin.classList.add("collapsed");openSeen[key]=true;currentWin.innerHTML=\'<button type="button" class="aa-window-header" onclick="toggleStrategyLabWindow(this)"><span class="aa-window-title"></span><span class="aa-window-meta"></span><span class="aa-window-caret">▾</span></button><div class="aa-window-body"></div>\';currentWin.querySelector(".aa-window-title").textContent=title;currentWin.querySelector(".aa-window-meta").textContent=key==="paper"?"Paper book isolated in this tab":"Click header to collapse or expand";currentBody=currentWin.querySelector(".aa-window-body");panelByKey[key].appendChild(currentWin);}else if(currentBody){currentBody.appendChild(n);}else{panelByKey.overview.appendChild(n);}});document.querySelectorAll(".aa-window-body").forEach(wrapH3Sections);if(location.hash&&document.querySelector(location.hash)){var target=document.querySelector(location.hash);var panel=target.closest(".aa-lab-tab-panel");if(panel)switchStrategyLabTab(panel.dataset.tab);}}'
        'document.addEventListener("DOMContentLoaded",buildStrategyLabTabs);'
        '</script>'
        '</div>'
    )


def _strategy_lab_html_table(rows: list[tuple[str, object]]) -> str:
    body = []
    for label, value in rows:
        body.append(
            f'<tr><td>{_html.escape(str(label))}</td><td>{_html.escape(_fmt_text(value))}</td></tr>'
        )
    return '<table>' + ''.join(body) + '</table>'


def _strategy_lab_load_symbol_fundamentals(symbols: list[str]) -> dict[str, dict[str, object]]:
    clean = sorted({str(symbol or "").strip().upper() for symbol in symbols if str(symbol or "").strip()})
    if not clean:
        return {}
    try:
        import psycopg2

        conn = psycopg2.connect(PG_DSN)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT symbol,
                           company_name,
                           sector,
                           stage,
                           technical_score,
                           rsi,
                           trading_signal,
                           trend_signal,
                           relative_strength,
                           fundamental_score,
                           enhanced_fund_score,
                           earnings_quality,
                           sales_growth,
                           financial_strength,
                           institutional_backing,
                           can_slim_score,
                           minervini_score,
                           investment_score,
                           fund_details::text,
                           narrative
                    FROM scores.stage_snapshots
                    WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM scores.stage_snapshots)
                      AND symbol = ANY(%s)
                    """,
                    (clean,),
                )
                cols = [desc[0] for desc in cur.description]
                return {str(row[0]).upper(): dict(zip(cols, row)) for row in cur.fetchall()}
        finally:
            conn.close()
    except Exception:
        return {}


def _strategy_lab_parse_fund_details(raw: object) -> dict[str, object]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _strategy_lab_fund_summary(fund: dict[str, object]) -> str:
    details = _strategy_lab_parse_fund_details(fund.get("fund_details"))
    parts = []
    for key in ("pnl_summary", "quarterly_summary", "ratios_summary", "investor_summary"):
        value = details.get(key) or fund.get(key)
        if value:
            parts.append(str(value))
    narrative = fund.get("narrative")
    if narrative:
        parts.append(str(narrative))
    return " ".join(parts[:3])


def _strategy_lab_interactive_leaderboard(
    summary: dict,
    rows: list[dict],
    turnover_rows: list[dict[str, object]],
) -> str:
    if not rows:
        return ""
    catalog = _strategy_lab_strategy_catalog()
    specs = _strategy_lab_strategy_specs_by_id()
    turnover_by_id = {str(row.get("strategy_id") or ""): row for row in turnover_rows}
    body = []
    for idx, row in enumerate(rows):
        rank = int(_float_or_none(row.get("rank")) or idx + 1)
        sid = str(row.get("strategy_id") or "n/a")
        detail_id = f"aa-strategy-detail-{idx}"
        verdict, reason = _strategy_lab_verdict(row, rank)
        details = catalog.get(sid) or {}
        spec = specs.get(sid) or {}
        turns = turnover_by_id.get(sid) or {}
        verdict_class = "aa-pill-good" if verdict == "Primary" else "aa-pill-warn" if "Watch" in verdict or "Monitor" in verdict else "aa-pill-bad" if verdict in {"Avoid", "Quarantine"} else "aa-pill-primary"
        body.append(
            f'<tr class="aa-strategy-row" onclick="toggleStrategyLabDetail(\'{detail_id}\')" title="Click for strategy diagnostics">'
            f'<td>#{rank}<span class="aa-row-hint">details</span></td>'
            f'<td><strong>{_html.escape(_strategy_lab_strategy_name(sid, specs, catalog))}</strong><br><span style="color:#64748b;font-size:10px">{_html.escape(sid)}</span></td>'
            f'<td><span class="aa-pill {verdict_class}">{_html.escape(verdict)}</span></td>'
            f'<td class="num">{_fmt_pct(row.get("total_return_pct"), 2)}</td>'
            f'<td class="num">{_fmt_pct_plain(row.get("max_drawdown_pct"), 2)}</td>'
            f'<td class="num">{_fmt_num(row.get("profit_factor"), 2)}</td>'
            f'<td class="num">₹{_fmt_num(row.get("expectancy"), 0)}</td>'
            f'<td class="num">{_fmt_pct_plain(row.get("turnover_pct"), 1)}</td>'
            f'<td class="num">{row.get("fills", 0)}</td>'
            f'<td class="num">{_fmt_pct_plain(row.get("win_rate_pct"), 1)}</td>'
            '</tr>'
        )
        body.append(
            f'<tr class="aa-detail-row" id="{detail_id}"><td colspan="10" class="aa-detail-cell">'
            '<div class="aa-detail-grid">'
            '<div class="aa-detail-card"><h4>Strategy Details</h4>'
            + _strategy_lab_html_table([
                ("What", details.get("what") or spec.get("description") or "Built-in paper strategy"),
                ("Entry", details.get("entry") or "Uses configured strategy entry rules"),
                ("Exit / Risk", details.get("risk") or "Uses configured exit and risk rules"),
                ("Best Regime", details.get("regime") or "Depends on signal family"),
                ("Verdict Reason", reason),
            ])
            + '</div>'
            '<div class="aa-detail-card"><h4>Performance Diagnostics</h4>'
            + _strategy_lab_html_table([
                ("Total Return", _fmt_pct(row.get("total_return_pct"), 2)),
                ("Excess Return", _fmt_pct(row.get("excess_return_pct"), 2)),
                ("Max Drawdown", _fmt_pct_plain(row.get("max_drawdown_pct"), 2)),
                ("Profit Factor", _fmt_num(row.get("profit_factor"), 2)),
                ("Cost Drag", _fmt_pct_plain(row.get("cost_drag_pct"), 2)),
            ])
            + '</div>'
            '<div class="aa-detail-card"><h4>Turnover / Audit</h4>'
            + _strategy_lab_html_table([
                ("Buy Notional", f"₹{_fmt_num(turns.get('buy_notional'), 0)}"),
                ("Sell Notional", f"₹{_fmt_num(turns.get('sell_notional'), 0)}"),
                ("Filled Notional", f"₹{_fmt_num(turns.get('total_notional'), 0)}"),
                ("Capital Turns", f"{_fmt_num((_float_or_none(turns.get('turnover_pct')) or 0.0) / 100.0, 2)}x"),
                ("Symbols Touched", turns.get("symbols", "n/a")),
            ])
            + '</div>'
            '</div></td></tr>'
        )
    return (
        '<div class="aa-lab-section"><div class="aa-lab-hdr"><strong>Interactive Strategy Leaderboard</strong>'
        '<span>Click a strategy row for rules, diagnostics, and turnover decomposition</span></div>'
        '<div style="overflow:auto"><table class="aa-lab-table"><thead><tr>'
        '<th>Rank</th><th>Strategy</th><th>Verdict</th><th class="num">Return</th><th class="num">Max DD</th>'
        '<th class="num">PF</th><th class="num">Expectancy</th><th class="num">Turnover</th><th class="num">Fills</th><th class="num">Win %</th>'
        '</tr></thead><tbody>'
        + ''.join(body)
        + '</tbody></table></div></div>'
    )


def _strategy_lab_interactive_positions(positions: list[dict], fund_lookup: dict[str, dict[str, object]]) -> str:
    if not positions:
        return ""
    body = []
    for idx, row in enumerate(positions[:40]):
        symbol = str(row.get("symbol") or "").upper()
        detail_id = f"aa-position-detail-{idx}-{re.sub(r'[^A-Za-z0-9_-]+', '', symbol)}"
        fund = fund_lookup.get(symbol, {})
        upnl = _float_or_none(row.get("unrealized_pnl")) or 0.0
        upct = _float_or_none(row.get("unrealized_pct")) or 0.0
        color = "#15803d" if upnl >= 0 else "#dc2626"
        body.append(
            f'<tr class="aa-position-row" onclick="toggleStrategyLabDetail(\'{detail_id}\')" title="Click for position, technical, and fundamental details">'
            f'<td><strong>{_html.escape(symbol)}</strong><span class="aa-row-hint">details</span></td>'
            f'<td>{_html.escape(_fmt_text(fund.get("company_name") or symbol))}</td>'
            f'<td class="num">{row.get("quantity", "0")}</td>'
            f'<td class="num">₹{_fmt_num(row.get("current_price"), 2)}</td>'
            f'<td class="num">₹{_fmt_num(row.get("market_value"), 0)}</td>'
            f'<td class="num" style="color:{color};font-weight:750">₹{_fmt_num(upnl, 0)} ({upct:+.1f}%)</td>'
            f'<td>{_html.escape(_fmt_text(row.get("stage") or fund.get("stage") or "n/a"))}</td>'
            f'<td class="num">{_fmt_num(row.get("relative_strength"), 1)}</td>'
            f'<td class="num">₹{_fmt_num(row.get("stop_price"), 2)}</td>'
            f'<td class="num">₹{_fmt_num(row.get("target_price"), 2)}</td>'
            '</tr>'
        )
        fund_summary = _strategy_lab_fund_summary(fund)
        body.append(
            f'<tr class="aa-detail-row" id="{detail_id}"><td colspan="10" class="aa-detail-cell">'
            '<div class="aa-detail-grid">'
            '<div class="aa-detail-card"><h4>Position Details</h4>'
            + _strategy_lab_html_table([
                ("Quantity", row.get("quantity", "0")),
                ("Current Price", f"₹{_fmt_num(row.get('current_price'), 2)}"),
                ("Market Value", f"₹{_fmt_num(row.get('market_value'), 2)}"),
                ("Unrealized P&L", f"₹{_fmt_num(row.get('unrealized_pnl'), 2)}"),
                ("Reward / Risk", _fmt_num(row.get("reward_risk"), 2)),
            ])
            + '</div>'
            '<div class="aa-detail-card"><h4>Technical Details</h4>'
            + _strategy_lab_html_table([
                ("Stage", row.get("stage") or fund.get("stage") or "n/a"),
                ("RSI", row.get("rsi_14") or fund.get("rsi") or "n/a"),
                ("Relative Strength", row.get("relative_strength") or fund.get("relative_strength") or "n/a"),
                ("Trading Signal", fund.get("trading_signal") or "n/a"),
                ("Trend", fund.get("trend_signal") or "n/a"),
                ("Technical Score", _fmt_num(fund.get("technical_score"), 0)),
            ])
            + '</div>'
            '<div class="aa-detail-card"><h4>Fundamental Details</h4>'
            + _strategy_lab_html_table([
                ("Fund Score", _fmt_num(fund.get("fundamental_score"), 0)),
                ("Enhanced Fund", _fmt_num(fund.get("enhanced_fund_score"), 0)),
                ("Earnings Quality", _fmt_num(fund.get("earnings_quality"), 0)),
                ("Sales Growth", _fmt_num(fund.get("sales_growth"), 0)),
                ("CANSLIM", _fmt_num(fund.get("can_slim_score"), 0)),
                ("Minervini", _fmt_num(fund.get("minervini_score"), 0)),
                ("Investment Score", _fmt_num(fund.get("investment_score"), 0)),
            ])
            + (f'<div style="margin-top:8px;font-size:11px;line-height:1.55;color:#475569;text-align:left">{_html.escape(fund_summary)}</div>' if fund_summary else '<div style="margin-top:8px;font-size:11px;color:#94a3b8;text-align:left">No detailed fundamentals found for this symbol in the latest snapshot.</div>')
            + '</div>'
            '</div></td></tr>'
        )
    return (
        '<div class="aa-lab-section"><div class="aa-lab-hdr"><strong>Clickable Paper Positions</strong>'
        '<span>Click a paper holding for position, technical, and fundamental details</span></div>'
        '<div style="overflow:auto"><table class="aa-lab-table"><thead><tr>'
        '<th>Symbol</th><th>Company</th><th class="num">Qty</th><th class="num">Price</th><th class="num">Value</th>'
        '<th class="num">Unrealized</th><th>Stage</th><th class="num">RS</th><th class="num">Stop</th><th class="num">Target</th>'
        '</tr></thead><tbody>'
        + ''.join(body)
        + '</tbody></table></div></div>'
    )


def _strategy_lab_exec_cards(
    summary: dict,
    rows: list[dict],
    paper: dict,
    positions: list[dict],
    turnover_rows: list[dict[str, object]],
) -> str:
    top = rows[0] if rows else {}
    selected = paper.get("selected_strategy_id") or top.get("strategy_id") or "n/a"
    latest_eod = summary.get("latest_eod_date") or paper.get("as_of") or "n/a"
    open_positions = int(_float_or_none(paper.get("open_positions")) or len(positions or []))
    leader_turnover = _float_or_none(top.get("turnover_pct"))
    leader_cost_drag = _float_or_none(top.get("cost_drag_pct"))
    total_filled = None
    if turnover_rows:
        by_strategy = {str(row.get("strategy_id") or ""): row for row in turnover_rows}
        selected_turnover = by_strategy.get(str(selected)) or turnover_rows[0]
        total_filled = _float_or_none(selected_turnover.get("total_notional"))

    cards = [
        (
            "Primary Strategy",
            str(selected),
            f"{_fmt_pct(top.get('total_return_pct'), 2)} return / {_fmt_pct_plain(top.get('max_drawdown_pct'), 2)} max DD",
        ),
        (
            "Portfolio P&L",
            f"₹{_fmt_num(paper.get('today_pnl'), 2)}",
            f"{_fmt_pct(paper.get('today_return_pct'), 2)} today return",
        ),
        (
            "Open Positions",
            str(open_positions),
            f"₹{_fmt_num(paper.get('total_unrealized_pnl'), 2)} unrealized P&L",
        ),
        (
            "Turnover",
            _fmt_pct_plain(leader_turnover, 1),
            f"₹{_fmt_num(total_filled, 0)} filled notional",
        ),
        (
            "Cost Drag",
            _fmt_pct_plain(leader_cost_drag, 2),
            f"{summary.get('slippage_bps')} bps slippage + {summary.get('brokerage_bps')} bps brokerage",
        ),
        (
            "Latest EOD",
            str(latest_eod),
            f"{summary.get('symbol_count', 0)} symbols / {summary.get('row_count', 0):,} rows",
        ),
    ]
    body = []
    for label, value, note in cards:
        body.append(
            '<div class="aa-exec-card" style="min-height:104px;padding:14px;border:1px solid #dbe3ef;'
            'border-radius:8px;background:#ffffff;box-shadow:0 1px 3px rgba(15,23,42,.08);">'
            f'<div style="font-size:11px;font-weight:800;letter-spacing:.04em;text-transform:uppercase;color:#64748b;">{_html.escape(label)}</div>'
            f'<div style="margin-top:8px;font-size:22px;line-height:1.15;font-weight:850;color:#0f172a;overflow-wrap:anywhere;">{_html.escape(value)}</div>'
            f'<div style="margin-top:8px;font-size:12px;line-height:1.35;color:#475569;">{_html.escape(note)}</div>'
            '</div>'
        )
    return (
        '<div class="aa-exec-cards" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(185px,1fr));'
        'gap:12px;margin:14px 0 18px;">'
        + "".join(body)
        + "</div>"
    )


def _strategy_lab_bar_chart(title: str, rows: list[dict], value_key: str, label_key: str, *, suffix: str = "%") -> str:
    clean = [
        (str(row.get(label_key) or "n/a"), _float_or_none(row.get(value_key)) or 0.0)
        for row in rows
    ][:8]
    if not clean:
        return ""
    max_abs = max(abs(value) for _, value in clean) or 1.0
    bar_rows = []
    is_drawdown_chart = "drawdown" in title.lower()
    for label, value in clean:
        width = max(3.0, abs(value) / max_abs * 100.0)
        color = "#dc2626" if is_drawdown_chart or value < 0 else "#16a34a"
        bar_rows.append(
            '<div style="display:grid;grid-template-columns:150px 1fr 70px;gap:10px;align-items:center;margin:7px 0;">'
            f'<div style="font-size:12px;color:#334155;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{_html.escape(label)}</div>'
            '<div style="height:11px;background:#e2e8f0;border-radius:999px;overflow:hidden;">'
            f'<div style="height:100%;width:{width:.1f}%;background:{color};border-radius:999px;"></div></div>'
            f'<div style="font-size:12px;text-align:right;color:#0f172a;">{value:.2f}{_html.escape(suffix)}</div>'
            '</div>'
        )
    return _strategy_lab_widget(title, "".join(bar_rows))


def _strategy_lab_line_chart(title: str, rows: list[dict], value_key: str, label_key: str = "date") -> str:
    points = []
    for row in rows[-90:]:
        value = _float_or_none(row.get(value_key))
        if value is not None:
            points.append((str(row.get(label_key) or ""), value))
    if len(points) < 2:
        return ""
    width, height = 720, 220
    pad_l, pad_r, pad_t, pad_b = 54, 18, 18, 34
    vals = [value for _, value in points]
    min_v, max_v = min(vals), max(vals)
    span = max(max_v - min_v, 1.0)
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    def x_at(idx: int) -> float:
        return pad_l + (idx / max(1, len(points) - 1)) * plot_w

    def y_at(value: float) -> float:
        return pad_t + (1 - ((value - min_v) / span)) * plot_h

    path = " ".join(("M" if idx == 0 else "L") + f"{x_at(idx):.1f},{y_at(value):.1f}" for idx, (_, value) in enumerate(points))
    zero_line = ""
    if min_v < 0 < max_v:
        y0 = y_at(0.0)
        zero_line = f'<line x1="{pad_l}" y1="{y0:.1f}" x2="{width-pad_r}" y2="{y0:.1f}" stroke="#cbd5e1" stroke-dasharray="4 4"/>'
    body = (
        f'<svg viewBox="0 0 {width} {height}" style="width:100%;max-width:920px;height:auto;" role="img" aria-label="{_html.escape(title)}">'
        f'<rect width="{width}" height="{height}" rx="8" fill="#f8fafc"/>'
        f'<line x1="{pad_l}" y1="{height-pad_b}" x2="{width-pad_r}" y2="{height-pad_b}" stroke="#cbd5e1"/>'
        f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{height-pad_b}" stroke="#cbd5e1"/>'
        f'{zero_line}'
        f'<path d="{path}" fill="none" stroke="#2563eb" stroke-width="3"/>'
        f'<text x="8" y="{pad_t+8}" font-size="11" fill="#64748b">{max_v:,.0f}</text>'
        f'<text x="8" y="{height-pad_b}" font-size="11" fill="#64748b">{min_v:,.0f}</text>'
        f'<text x="{pad_l}" y="{height-10}" font-size="11" fill="#64748b">{_html.escape(points[0][0])}</text>'
        f'<text x="{width-pad_r-80}" y="{height-10}" font-size="11" fill="#64748b">{_html.escape(points[-1][0])}</text>'
        f'<circle cx="{x_at(len(points)-1):.1f}" cy="{y_at(points[-1][1]):.1f}" r="4" fill="#1d4ed8"/>'
        '</svg>'
    )
    return _strategy_lab_widget(title, body)


def _strategy_lab_calendar_heatmap(summary: dict, summary_path: Path, rows: list[dict]) -> str:
    strategy_blocks = []
    for row in rows[:10]:
        strategy_id = str(row.get("strategy_id") or "")
        if not strategy_id:
            continue
        state_path = _strategy_lab_replay_state_path(summary, summary_path, strategy_id)
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        daily_rows = _strategy_lab_daily_heatmap_rows(state)
        if not daily_rows:
            continue
        strategy_blocks.append(_strategy_lab_calendar_strategy_block(strategy_id, row, daily_rows))

    if not strategy_blocks:
        return ""
    style = (
        '<style>'
        '.aa-heatmap-day{position:relative;display:inline-block;}'
        '.aa-heatmap-day:hover::after,.aa-heatmap-day:focus::after{content:attr(data-tooltip);position:absolute;left:22px;top:-8px;z-index:9999;'
        'min-width:280px;max-width:460px;padding:10px 12px;border-radius:8px;background:#0f172a;color:#fff;'
        'box-shadow:0 10px 24px rgba(15,23,42,.28);font-size:12px;line-height:1.45;white-space:normal;text-align:left;}'
        '.aa-heatmap-day:hover::before,.aa-heatmap-day:focus::before{content:"";position:absolute;left:17px;top:2px;z-index:9998;'
        'border-width:6px 6px 6px 0;border-style:solid;border-color:transparent #0f172a transparent transparent;}'
        '</style>'
    )
    legend = (
        '<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:8px 0 14px;'
        'font-size:12px;color:#64748b;">'
        '<span>Daily P&amp;L intensity:</span>'
        '<span style="display:inline-flex;align-items:center;gap:4px;"><i style="display:inline-block;width:12px;height:12px;background:#dc2626;border-radius:3px;"></i>Loss</span>'
        '<span style="display:inline-flex;align-items:center;gap:4px;"><i style="display:inline-block;width:12px;height:12px;background:#e2e8f0;border-radius:3px;"></i>Flat</span>'
        '<span style="display:inline-flex;align-items:center;gap:4px;"><i style="display:inline-block;width:12px;height:12px;background:#16a34a;border-radius:3px;"></i>Gain</span>'
        '<span>Hover a day for BUY/SELL symbols and P&amp;L.</span>'
        '</div>'
    )
    body = style + legend + "".join(strategy_blocks)
    return _strategy_lab_widget("Strategy Daily Calendar Heatmap", body)


def _strategy_lab_daily_heatmap_rows(state: dict) -> list[dict[str, object]]:
    nav_history = list(state.get("nav_history") or [])
    fills_by_date: dict[str, dict[str, list[str]]] = {}
    for fill in state.get("fills") or []:
        date = str(fill.get("fill_date") or fill.get("timestamp") or "")[:10]
        if not date:
            continue
        side = str(fill.get("side") or "").upper()
        symbol = str(fill.get("symbol") or "").upper()
        if not symbol or side not in {"BUY", "SELL"}:
            continue
        fills_by_date.setdefault(date, {"BUY": [], "SELL": []})[side].append(symbol)

    rows: list[dict[str, object]] = []
    previous_nav: float | None = None
    for entry in nav_history:
        date = str(entry.get("timestamp") or entry.get("date") or "")[:10]
        nav = _float_or_none(entry.get("nav"))
        if not date or nav is None:
            continue
        daily_pnl = 0.0 if previous_nav is None else nav - previous_nav
        daily_return = 0.0 if previous_nav in {None, 0.0} else daily_pnl / previous_nav * 100.0
        previous_nav = nav
        rows.append(
            {
                "date": date,
                "nav": nav,
                "daily_pnl": daily_pnl,
                "daily_return_pct": daily_return,
                "buys": sorted(set(fills_by_date.get(date, {}).get("BUY", []))),
                "sells": sorted(set(fills_by_date.get(date, {}).get("SELL", []))),
            }
        )
    return rows


def _strategy_lab_calendar_strategy_block(strategy_id: str, leaderboard_row: dict, daily_rows: list[dict[str, object]]) -> str:
    max_abs_pnl = max(abs(_float_or_none(row.get("daily_pnl")) or 0.0) for row in daily_rows) or 1.0
    by_month: dict[str, list[dict[str, object]]] = {}
    for row in daily_rows:
        month = str(row.get("date"))[:7]
        by_month.setdefault(month, []).append(row)

    months = []
    for month in sorted(by_month):
        days = sorted(by_month[month], key=lambda row: str(row.get("date")))
        cells = []
        try:
            first_date = datetime.date.fromisoformat(str(days[0].get("date")))
            first_weekday = first_date.weekday()
        except (ValueError, TypeError):
            first_weekday = 0
        for _ in range(first_weekday):
            cells.append('<span style="width:18px;height:18px;"></span>')
        for row in days:
            cells.append(_strategy_lab_calendar_day_cell(strategy_id, row, max_abs_pnl))
        month_label = datetime.datetime.strptime(month, "%Y-%m").strftime("%b %Y")
        months.append(
            '<div style="min-width:170px;margin:0 12px 14px 0;">'
            f'<div style="font-size:11px;font-weight:800;color:#334155;margin-bottom:5px;">{_html.escape(month_label)}</div>'
            '<div style="display:grid;grid-template-columns:repeat(7,18px);gap:3px;align-items:center;">'
            + "".join(cells)
            + '</div></div>'
        )
    header = (
        '<div style="display:flex;justify-content:space-between;gap:12px;align-items:baseline;'
        'border-top:1px solid #e2e8f0;padding-top:12px;margin-top:12px;">'
        f'<div style="font-size:13px;font-weight:850;color:#0f172a;">{_html.escape(strategy_id)}</div>'
        f'<div style="font-size:12px;color:#64748b;">Return {_fmt_pct(leaderboard_row.get("total_return_pct"), 2)} '
        f'/ Max DD {_fmt_pct_plain(leaderboard_row.get("max_drawdown_pct"), 2)} '
        f'/ Fills {leaderboard_row.get("fills", 0)}</div></div>'
    )
    return header + '<div style="display:flex;flex-wrap:wrap;margin-top:10px;">' + "".join(months) + "</div>"


def _strategy_lab_calendar_day_cell(strategy_id: str, row: dict[str, object], max_abs_pnl: float) -> str:
    date = str(row.get("date"))
    pnl = _float_or_none(row.get("daily_pnl")) or 0.0
    nav = _float_or_none(row.get("nav")) or 0.0
    daily_return = _float_or_none(row.get("daily_return_pct")) or 0.0
    buys = list(row.get("buys") or [])
    sells = list(row.get("sells") or [])
    intensity = min(1.0, abs(pnl) / max_abs_pnl)
    if pnl > 0:
        color = _strategy_lab_heat_color((22, 163, 74), intensity)
    elif pnl < 0:
        color = _strategy_lab_heat_color((220, 38, 38), intensity)
    else:
        color = "#e2e8f0"
    tooltip = (
        f"{date} - {strategy_id} - "
        f"Daily P&L: ₹{_fmt_num(pnl, 2)} - "
        f"Daily return: {_fmt_pct(daily_return, 2)} - "
        f"NAV: ₹{_fmt_num(nav, 2)} - "
        f"BUY: {', '.join(buys) if buys else '-'} - "
        f"SELL: {', '.join(sells) if sells else '-'}"
    )
    border = "#0f172a" if buys or sells else "rgba(15,23,42,.14)"
    return (
        f'<span class="aa-heatmap-day" data-heatmap-day="{_html.escape(date)}" '
        f'data-tooltip="{_html.escape(tooltip, quote=True)}" title="{_html.escape(tooltip, quote=True)}" tabindex="0" '
        f'style="width:18px;height:18px;border-radius:4px;background:{color};border:1px solid {border};'
        'display:inline-block;cursor:help;"></span>'
    )


def _strategy_lab_heat_color(rgb: tuple[int, int, int], intensity: float) -> str:
    base = (248, 250, 252)
    blend = max(0.2, min(1.0, intensity))
    values = [round(base[idx] + (rgb[idx] - base[idx]) * blend) for idx in range(3)]
    return f"rgb({values[0]},{values[1]},{values[2]})"


def _strategy_lab_managed_portfolio_markdown(summary: dict[str, object]) -> str:
    managed = summary.get("managed_portfolio") or {}
    if not isinstance(managed, dict) or not managed:
        return ""

    state = managed.get("state") or {}
    if not isinstance(state, dict):
        state = {}
    raw_positions = state.get("positions") or {}
    if isinstance(raw_positions, dict):
        positions = list(raw_positions.values())
    elif isinstance(raw_positions, list):
        positions = raw_positions
    else:
        positions = []
    positions = [row for row in positions if isinstance(row, dict)]
    decisions = [row for row in list(managed.get("decisions") or []) if isinstance(row, dict)]
    orders = [row for row in list(managed.get("orders") or []) if isinstance(row, dict)]

    def table_text(value: object) -> str:
        return _fmt_text(value).replace("\n", " ").replace("|", " / ")

    policy_checksum = state.get("policy_checksum") or managed.get("policy_checksum")

    md: list[str] = []
    md.append("## Managed Portfolio")
    md.append("")
    md.append("| Metric | Value |")
    md.append("|---|---:|")
    md.append(f"| NAV | ₹{_fmt_num(state.get('nav'), 2)} |")
    md.append(f"| Cash | ₹{_fmt_num(state.get('cash'), 2)} |")
    md.append(f"| Open Positions | {len(positions)} |")
    md.append(f"| Orders | {len(orders)} |")
    md.append(f"| Decisions | {len(decisions)} |")
    if policy_checksum:
        md.append(f"| Policy Checksum | `{table_text(policy_checksum)}` |")
    md.append("")

    md.append("### Managed Positions")
    md.append("")
    md.append("| Symbol | Qty | Avg Cost | Open Risk | Lots | Sector |")
    md.append("|---|---:|---:|---:|---:|---|")
    if positions:
        for row in positions[:30]:
            md.append(
                f"| **{table_text(row.get('symbol'))}** | {row.get('quantity', '0')} | "
                f"₹{_fmt_num(row.get('avg_cost'), 2)} | ₹{_fmt_num(row.get('open_risk'), 2)} | "
                f"{len(row.get('lots') or [])} | {table_text(row.get('sector'))} |"
            )
    else:
        md.append("| n/a | 0 | n/a | n/a | 0 | n/a |")
    md.append("")

    md.append("### Recent Managed Decisions")
    md.append("")
    md.append("| Date | Symbol | Action | Qty | Reason |")
    md.append("|---|---|---|---:|---|")
    if decisions:
        for row in decisions[-20:]:
            reason_codes = row.get("reason_codes")
            if isinstance(reason_codes, list):
                reason_text = ", ".join(str(value) for value in reason_codes)
            else:
                reason_text = _fmt_text(reason_codes)
            md.append(
                f"| {table_text(row.get('date'))} | **{table_text(row.get('symbol'))}** | "
                f"{table_text(row.get('action'))} | {row.get('quantity', '0')} | {table_text(reason_text)} |"
            )
    else:
        md.append("| n/a | n/a | HOLD | 0 | no managed decisions recorded |")
    md.append("")

    return "\n".join(md)


def _build_strategy_lab_content() -> str:
    """Build the Portfolio Strategy Lab report from native portfolio artifacts."""
    summary_path = ROOT / "portfolio" / "data" / "nse_pg_strategy_lab" / "latest" / "reports" / "strategy_comparison_summary.json"
    if not summary_path.exists():
        fallback = ROOT / "portfolio" / "data" / "nse_pg_strategy_lab" / "native_20260601" / "reports" / "strategy_comparison_summary.json"
        summary_path = fallback if fallback.exists() else summary_path
    if not summary_path.exists():
        raise FileNotFoundError(
            "Portfolio strategy-lab summary not found. Run "
            "`python -m portfolio.cli strategy-lab --output-dir portfolio/data/nse_pg_strategy_lab/latest` first."
        )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rows = list(summary.get("leaderboard") or [])
    now = datetime.datetime.now()
    top = rows[0] if rows else {}
    stage_counts = summary.get("stage_counts") or {}
    paper = summary.get("paper_portfolio") or {}
    database = paper.get("database") or {}
    paper_artifacts = paper.get("artifacts") or {}
    fundamental_coverage = summary.get("fundamental_coverage") or {}
    positions = _read_csv_rows(_strategy_lab_artifact_path(summary, summary_path, paper_artifacts.get("positions")))
    daily_pnl = _read_csv_rows(_strategy_lab_artifact_path(summary, summary_path, paper_artifacts.get("daily_pnl")))
    trades = _read_csv_rows(_strategy_lab_artifact_path(summary, summary_path, paper_artifacts.get("trades")), limit=5000)
    next_orders = _read_csv_rows(_strategy_lab_artifact_path(summary, summary_path, paper_artifacts.get("next_orders")), limit=1000)
    turnover_rows = _strategy_lab_turnover_rows(summary, summary_path, rows)
    fund_lookup = _strategy_lab_load_symbol_fundamentals([str(row.get("symbol") or "") for row in positions])
    narrative = _strategy_lab_narrative(summary, rows, paper, positions)
    council = _strategy_lab_council_deliberation(summary, rows, paper, positions, turnover_rows)
    stage2_count = stage_counts.get("STAGE_2", 0)
    symbol_count = summary.get("symbol_count") or 0
    row_count = summary.get("row_count") or 0
    stage2_pct = (float(stage2_count) / float(row_count) * 100.0) if row_count else 0.0

    md: list[str] = []
    md.append("# Portfolio Strategy Lab — NSE Paper Trading")
    md.append(f"**Generated:** {now.strftime('%d %b %Y, %H:%M IST')} · **Source:** `scores.stage_snapshots` + `market.equity_eod` + `scores.quarterly_results`")
    md.append("")
    md.append(_strategy_lab_detail_assets())
    md.append("")
    md.append("## Executive Summary")
    md.append("")
    md.append(_strategy_lab_exec_cards(summary, rows, paper, positions, turnover_rows))
    md.append("")

    md.append("## Comprehensive LLM Narrative")
    md.append("")
    md.append(f"**{_fmt_text(narrative.get('headline'))}**")
    md.append("")
    md.append(str(narrative.get("narrative") or "No narrative available."))
    md.append("")
    md.append(f"**Portfolio readout:** {str(narrative.get('portfolio_readout') or 'N/A')}")
    md.append("")
    md.append(f"**Strategy readout:** {str(narrative.get('strategy_readout') or 'N/A')}")
    md.append("")
    md.append(f"**Turnover readout:** {str(narrative.get('turnover_readout') or 'N/A')}")
    md.append("")
    md.append(f"*Narrative source: {_fmt_text(narrative.get('source'))}.*")
    md.append("")
    md.append("| Focus | Risk Watch |")
    md.append("|---|---|")
    focus_items = list(narrative.get("focus") or [])
    risk_items = list(narrative.get("risks") or [])
    for idx in range(max(len(focus_items), len(risk_items), 1)):
        md.append(
            f"| {_fmt_text(focus_items[idx] if idx < len(focus_items) else '')} | "
            f"{_fmt_text(risk_items[idx] if idx < len(risk_items) else '')} |"
        )
    md.append("")
    action_items = list(narrative.get("action_plan") or [])
    if action_items:
        md.append("### Agent Action Plan")
        md.append("")
        for item in action_items:
            md.append(f"- {item}")
        md.append("")

    md.append(_strategy_lab_council_markdown(council))
    md.append("")
    md.append(_strategy_lab_strategy_playbook(rows))
    md.append("")

    md.append("## Detailed Analysis")
    md.append("")
    md.append("## Market and Run Snapshot")
    md.append("")
    md.append("| Metric | Value |")
    md.append("|---|---|")
    md.append(f"| Run ID | `{summary.get('run_id', 'n/a')}` |")
    md.append(f"| Window | {summary.get('start_date')} → {summary.get('end_date')} |")
    md.append(f"| Latest EOD Date | {summary.get('latest_eod_date', 'n/a')} |")
    md.append(f"| Universe | {symbol_count} liquid NSE symbols |")
    md.append(f"| Feature Rows | {row_count:,} |")
    md.append(f"| Stage 2 Feature Rows | {stage2_count:,} ({stage2_pct:.1f}% of feature rows) |")
    md.append(f"| Latest Result Coverage | {fundamental_coverage.get('symbols_with_latest_result', 0)} symbols / {fundamental_coverage.get('rows_with_latest_result', 0):,} rows |")
    md.append(f"| Median Result Age | {_fmt_num(fundamental_coverage.get('median_result_age_days'), 0)} days |")
    md.append(f"| Benchmark | {summary.get('benchmark_id', 'Nifty 500')} |")
    md.append(f"| Costs | {summary.get('slippage_bps')} bps slippage + {summary.get('brokerage_bps')} bps brokerage |")
    if top:
        md.append(f"| Current Leader | **{top.get('strategy_id')}** ({_fmt_pct(top.get('total_return_pct'), 2)} return, {_fmt_pct_plain(top.get('max_drawdown_pct'), 2)} max DD) |")
    md.append("")

    md.append("## Fundamental and Quarterly Result Coverage")
    md.append("")
    md.append("Quarterly result features are merged point-in-time using a conservative availability lag after period end. The active fundamental filters use latest-result freshness, revenue/PAT/EPS growth, and OPM trend where available.")
    md.append("")
    md.append("| Metric | Value |")
    md.append("|---|---:|")
    md.append(f"| Rows with latest quarterly result | {fundamental_coverage.get('rows_with_latest_result', 0):,} |")
    md.append(f"| Symbols with latest quarterly result | {fundamental_coverage.get('symbols_with_latest_result', 0):,} |")
    md.append(f"| Median result age | {_fmt_num(fundamental_coverage.get('median_result_age_days'), 0)} days |")
    md.append(f"| Rows with revenue YoY signal | {fundamental_coverage.get('rows_with_sales_yoy', 0):,} |")
    md.append(f"| Rows with PAT YoY signal | {fundamental_coverage.get('rows_with_pat_yoy', 0):,} |")
    md.append(f"| Rows with EPS YoY signal | {fundamental_coverage.get('rows_with_eps_yoy', 0):,} |")
    md.append("")

    md.append("## Charts and Visual Readout")
    md.append("")
    md.append(_strategy_lab_bar_chart("Strategy Return Chart", rows, "total_return_pct", "strategy_id"))
    md.append("")
    md.append(_strategy_lab_bar_chart("Strategy Drawdown Chart", rows, "max_drawdown_pct", "strategy_id"))
    md.append("")
    md.append(_strategy_lab_line_chart("Portfolio NAV Chart", daily_pnl, "nav"))
    md.append("")
    md.append(_strategy_lab_line_chart("Daily P&L Chart", daily_pnl, "daily_pnl"))
    md.append("")
    md.append(_strategy_lab_calendar_heatmap(summary, summary_path, rows))
    md.append("")
    if positions:
        md.append(_strategy_lab_bar_chart("Open Position Unrealized P&L", positions, "unrealized_pnl", "symbol", suffix=""))
        md.append("")

    if paper:
        md.append("## Daily Paper Portfolio")
        md.append("")
        latest_trade_date = max((str(row.get("date")) for row in trades), default="")
        blotter_trades = [row for row in trades if str(row.get("date")) == str(paper.get("as_of"))]
        if not blotter_trades and latest_trade_date:
            blotter_trades = [row for row in trades if str(row.get("date")) == latest_trade_date]
        buy_count = sum(1 for row in blotter_trades if str(row.get("side")).upper() == "BUY")
        sell_count = sum(1 for row in blotter_trades if str(row.get("side")).upper() == "SELL")
        latest_nav = daily_pnl[-1] if daily_pnl else {}
        nav_value = _float_or_none(latest_nav.get("nav")) or 0.0
        market_value = _float_or_none(latest_nav.get("market_value")) or 0.0
        exposure_pct = (market_value / nav_value * 100.0) if nav_value else 0.0

        md.append("### Current Paper Book")
        md.append("")
        md.append("| Metric | Value |")
        md.append("|---|---:|")
        md.append(f"| Selected Strategy | `{paper.get('selected_strategy_id', 'n/a')}` |")
        md.append(f"| As Of | {paper.get('as_of', 'n/a')} |")
        md.append(f"| Open Positions | {paper.get('open_positions', 0)} |")
        md.append(f"| Today P&L | ₹{_fmt_num(paper.get('today_pnl'), 2)} |")
        md.append(f"| Today Return | {_fmt_pct(paper.get('today_return_pct'), 2)} |")
        md.append(f"| Unrealized P&L | ₹{_fmt_num(paper.get('total_unrealized_pnl'), 2)} |")
        md.append(f"| Market Exposure | {_fmt_pct_plain(exposure_pct, 1)} |")
        md.append(f"| Latest Trade Date | {latest_trade_date or 'n/a'} |")
        md.append(f"| Buys / Sells In Blotter | {buy_count} / {sell_count} |")
        md.append("")
        md.append("| Artifact | Path |")
        md.append("|---|---|")
        md.append(f"| Portfolio State | `{paper_artifacts.get('state', 'n/a')}` |")
        md.append(f"| Positions | `{paper_artifacts.get('positions', 'n/a')}` |")
        md.append(f"| Daily P&L | `{paper_artifacts.get('daily_pnl', 'n/a')}` |")
        md.append(f"| Trades | `{paper_artifacts.get('trades', 'n/a')}` |")
        md.append(f"| Next Session Orders | `{paper_artifacts.get('next_orders', 'n/a')}` |")
        md.append(f"| Agent Actions | `{paper_artifacts.get('agent_actions', 'n/a')}` |")
        md.append(f"| Paper Report | `{paper_artifacts.get('report', 'n/a')}` |")
        md.append("")

        md.append("### Database Persistence")
        md.append("")
        md.append("| Metric | Value |")
        md.append("|---|---:|")
        md.append(f"| Database write status | {'Success' if database.get('success') else 'Not written'} |")
        md.append(f"| Schema | `{database.get('schema', 'portfolio')}` |")
        md.append(f"| Positions stored | {database.get('positions', 0)} |")
        md.append(f"| Daily P&L rows stored | {database.get('daily_pnl', 0)} |")
        md.append(f"| Transactions stored | {database.get('transactions', 0)} |")
        md.append(f"| Next orders stored | {database.get('next_orders', 0)} |")
        md.append(f"| Agent actions stored | {database.get('agent_actions', 0)} |")
        if database.get("tables"):
            md.append(f"| Tables | {', '.join(f'`{table}`' for table in database.get('tables') or [])} |")
        if database.get("error"):
            md.append(f"| Error | {_fmt_text(database.get('error'))} |")
        md.append("")

        if positions:
            md.append("### Current Holdings and Risk Levels")
            md.append("")
            md.append(_strategy_lab_interactive_positions(positions, fund_lookup))
            md.append("")

        md.append("### Next Session Orders")
        md.append("")
        md.append("| Date | Order | Symbol | Action | Qty | Type | Signal Reason | Ref Price | Stop | Target | Est Risk | Est Notional |")
        md.append("|---|---|---|---|---:|---|---|---:|---:|---:|---:|---:|")
        if next_orders:
            for row in next_orders[:30]:
                md.append(
                    f"| {_fmt_text(row.get('date'))} | `{_fmt_text(row.get('order_id'))}` | "
                    f"**{_fmt_text(row.get('symbol'))}** | {_fmt_text(row.get('trade_intent') or row.get('side'))} | "
                    f"{row.get('quantity', '0')} | {_fmt_text(row.get('order_type'))} | "
                    f"{_fmt_text(row.get('signal_reason') or 'n/a')} | ₹{_fmt_num(row.get('reference_price'), 2)} | "
                    f"₹{_fmt_num(row.get('stop_price'), 2)} | ₹{_fmt_num(row.get('target_price'), 2)} | "
                    f"₹{_fmt_num(row.get('estimated_risk'), 2)} | ₹{_fmt_num(row.get('estimated_notional'), 2)} |"
                )
        else:
            md.append("| n/a | n/a | n/a | HOLD | 0 | n/a | no next-open paper orders | n/a | n/a | n/a | n/a | n/a |")
        md.append("")

        if trades:
            md.append("### Today Trade Blotter")
            md.append("")
            md.append("| Date | Symbol | Action | Qty | Price | Signal Reason | Entry | Stop | Target | Realized | R | Hold Days |")
            md.append("|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|")
            for row in blotter_trades:
                md.append(
                    f"| {_fmt_text(row.get('date'))} | **{_fmt_text(row.get('symbol'))}** | "
                    f"{_fmt_text(row.get('trade_intent') or row.get('side'))} | {row.get('quantity', '0')} | "
                    f"₹{_fmt_num(row.get('price'), 2)} | {_fmt_text(row.get('signal_reason') or 'n/a')} | "
                    f"₹{_fmt_num(row.get('entry_price'), 2)} | ₹{_fmt_num(row.get('stop_price'), 2)} | "
                    f"₹{_fmt_num(row.get('target_price'), 2)} | ₹{_fmt_num(row.get('realized_pnl'), 2)} | "
                    f"{_fmt_num(row.get('r_multiple'), 2)} | {_fmt_num(row.get('holding_period_days'), 0)} |"
                )
            md.append("")

            md.append("### Latest Paper Trades")
            md.append("")
            md.append("| Date | Symbol | Side | Intent | Qty | Price | Signal Reason | Realized | Hold Days |")
            md.append("|---|---|---|---|---:|---:|---|---:|---:|")
            for row in trades[-15:]:
                md.append(
                    f"| {_fmt_text(row.get('date'))} | **{_fmt_text(row.get('symbol'))}** | "
                    f"{_fmt_text(row.get('side'))} | {_fmt_text(row.get('trade_intent') or 'n/a')} | "
                    f"{row.get('quantity', '0')} | ₹{_fmt_num(row.get('price'), 2)} | "
                    f"{_fmt_text(row.get('signal_reason') or 'n/a')} | ₹{_fmt_num(row.get('realized_pnl'), 2)} | "
                    f"{_fmt_num(row.get('holding_period_days'), 0)} |"
                )
            md.append("")

    managed_section = _strategy_lab_managed_portfolio_markdown(summary)
    if managed_section:
        md.append(managed_section)
        md.append("")

    md.append("## Strategy Leaderboard")
    md.append("")
    md.append(_strategy_lab_interactive_leaderboard(summary, rows, turnover_rows))
    md.append("")
    md.append("| Rank | Strategy | Strategy Verdict | Return | Max DD | Excess | Profit Factor | Expectancy | Turnover | Cost Drag | Fills | Win Rate |")
    md.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in rows:
        verdict, _reason = _strategy_lab_verdict(row, int(row.get("rank") or 0))
        md.append(
            f"| {row.get('rank')} | **{row.get('strategy_id')}** | "
            f"{verdict} | "
            f"{_fmt_pct(row.get('total_return_pct'), 2)} | {_fmt_pct_plain(row.get('max_drawdown_pct'), 2)} | "
            f"{_fmt_pct(row.get('excess_return_pct'), 2)} | {_fmt_num(row.get('profit_factor'), 2)} | "
            f"₹{_fmt_num(row.get('expectancy'), 0)} | {_fmt_pct_plain(row.get('turnover_pct'), 1)} | "
            f"{_fmt_pct_plain(row.get('cost_drag_pct'), 2)} | {row.get('fills', 0)} | "
            f"{_fmt_pct_plain(row.get('win_rate_pct'), 1)} |"
        )
    md.append("")

    md.append("## Strategy Verdict")
    md.append("")
    md.append("The ranking is deliberately not sorted by raw return alone. It rewards active strategies that preserve return after drawdown, turnover, cost drag, and trade quality checks.")
    md.append("")
    md.append("| Strategy | Verdict | Why |")
    md.append("|---|---|---|")
    for row in rows:
        verdict, reason = _strategy_lab_verdict(row, int(row.get("rank") or 0))
        md.append(f"| **{row.get('strategy_id')}** | {verdict} | {reason} |")
    md.append("")

    md.append("## Risk-Adjusted Readout")
    md.append("")
    if rows:
        best = rows[0]
        high_return = max(rows, key=lambda row: float(row.get("total_return_pct") or 0))
        worst_turnover = max(rows, key=lambda row: float(row.get("turnover_pct") or 0))
        md.append(f"- **Best current candidate:** `{best.get('strategy_id')}` leads the ranking after return, drawdown, and activity checks.")
        md.append(f"- **Highest raw return:** `{high_return.get('strategy_id')}` returned {_fmt_pct(high_return.get('total_return_pct'), 2)} but carried {_fmt_pct_plain(high_return.get('max_drawdown_pct'), 2)} max drawdown.")
        md.append(f"- **Turnover warning:** `{worst_turnover.get('strategy_id')}` generated {_fmt_pct_plain(worst_turnover.get('turnover_pct'), 1)} turnover and {_fmt_pct_plain(worst_turnover.get('cost_drag_pct'), 2)} cost drag.")
        weak = [row for row in rows if float(row.get("profit_factor") or 0) < 1 and int(row.get("fills") or 0) > 0]
        if weak:
            md.append("- **Quarantine candidates:** " + ", ".join(f"`{row.get('strategy_id')}`" for row in weak[:4]) + " have profit factor below 1.0 after costs.")
    else:
        md.append("- No strategy rows were found in the latest strategy-lab artifact.")
    md.append("")

    md.append("## Cost and Turnover Diagnostics")
    md.append("")
    if rows:
        leader_turnover = _float_or_none(rows[0].get("turnover_pct")) or 0.0
        leader_turns = leader_turnover / 100.0
        md.append(
            "Turnover is **total filled notional divided by starting capital**. "
            f"For the current leader `{rows[0].get('strategy_id')}`, turnover of {_fmt_pct_plain(leader_turnover, 1)} means "
            f"the replay filled about {_fmt_num(leader_turns, 2)}x starting capital over the full test window. "
            "This becomes high when rules enter/exit frequently, when add rules pyramid positions, or when exits are tight enough to recycle cash repeatedly."
        )
    else:
        md.append(
            "Turnover is **total filled notional divided by starting capital**. "
            "This becomes high when rules enter/exit frequently, when add rules pyramid positions, or when exits are tight enough to recycle cash repeatedly."
        )
    md.append("")
    md.append("| Strategy | Turnover | Cost Drag | Profit Factor | Expectancy | Fills |")
    md.append("|---|---:|---:|---:|---:|---:|")
    for row in rows:
        md.append(
            f"| **{row.get('strategy_id')}** | "
            f"{_fmt_pct_plain(row.get('turnover_pct'), 1)} | "
            f"{_fmt_pct_plain(row.get('cost_drag_pct'), 2)} | "
            f"{_fmt_num(row.get('profit_factor'), 2)} | "
            f"₹{_fmt_num(row.get('expectancy'), 0)} | "
            f"{row.get('fills', 0)} |"
        )
    if not rows:
        md.append("| No strategy rows | N/A | N/A | N/A | N/A | 0 |")
    md.append("")

    if turnover_rows:
        md.append("### Turnover Decomposition")
        md.append("")
        md.append("| Strategy | Buy Notional | Sell Notional | Total Filled Notional | Starting Capital Turns | Fills | Symbols |")
        md.append("|---|---:|---:|---:|---:|---:|---:|")
        for row in turnover_rows:
            turns = (_float_or_none(row.get("turnover_pct")) or 0.0) / 100.0
            md.append(
                f"| **{row.get('strategy_id')}** | ₹{_fmt_num(row.get('buy_notional'), 0)} | "
                f"₹{_fmt_num(row.get('sell_notional'), 0)} | ₹{_fmt_num(row.get('total_notional'), 0)} | "
                f"{_fmt_num(turns, 2)}x | {row.get('fills', 0)} | {row.get('symbols', 0)} |"
            )
        md.append("")

    md.append("## Recommended Paper Trading Focus")
    md.append("")
    md.append("| Action | Strategy | Reason |")
    md.append("|---|---|---|")
    if rows:
        md.append(f"| Primary paper strategy | `{rows[0].get('strategy_id')}` | Best active risk-adjusted score in the latest run |")
    if len(rows) > 1:
        md.append(f"| Watch but constrain | `{rows[1].get('strategy_id')}` | Strong return profile but needs drawdown and exposure caps |")
    md.append("| Avoid for now | `mean_reversion_uptrend_v1` | High churn and weak cost-adjusted result in recent runs |")
    md.append("| Required guardrail | Portfolio controls | Add max positions, sector caps, turnover caps, and drawdown stop before daily paper allocation |")
    md.append("")

    md.append("## Run Artifacts and Methodology")
    md.append("")
    md.append("| Artifact | Path |")
    md.append("|---|---|")
    md.append(f"| Summary JSON | `{summary_path}` |")
    md.append(f"| Feature CSV | `{summary.get('data_path', 'n/a')}` |")
    md.append(f"| Benchmark CSV | `{summary.get('benchmark_path', 'n/a')}` |")
    md.append(f"| Output Directory | `{summary.get('output_dir', 'n/a')}` |")
    md.append("")
    md.append("Methodology: each built-in strategy is replayed independently from zero positions using EOD bars, next-open fills, historical `scores.stage_snapshots`, persisted `scores.stage2_vcp_picks` where a strategy uses them, point-in-time quarterly-result features, and the configured slippage/brokerage assumptions. Ranking sorts active strategies first and then uses the strategy-lab `rank_score`.")
    md.append("")
    md.append("---")
    md.append("*Paper trading only. This report is for strategy research and auditability, not investment advice or live trading instruction.*")
    return "\n".join(md)


def _generate_diagnosis_preset_report(args: list[str], output_format: str) -> dict:
    if len(args) < 2:
        return {
            "path": None,
            "latest_path": None,
            "format": output_format,
            "title": "Fundamental Driver Diagnosis",
            "report_type": "diagnosis",
            "symbol": "",
            "success": False,
            "warnings": ["Usage: /report diagnosis SYMBOL eps|roce|margin|debt|cashflow"],
            "note": "Usage: /report diagnosis SYMBOL eps|roce|margin|debt|cashflow",
        }

    from terminal.skills.commands import render_fundamental_driver_result
    from terminal.skills.fundamental_driver import diagnose_fundamental_driver

    symbol = str(args[0]).strip().upper()
    metric = str(args[1]).strip().lower()
    normalized_format = "md" if output_format.lower().strip() in {"md", "markdown"} else "html"
    result = diagnose_fundamental_driver(symbol, metric)
    markdown = render_fundamental_driver_result(result)
    filename = f"{symbol}_fundamental_driver_{metric}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    title = f"{symbol} — {metric.upper()} Fundamental Driver Diagnosis"

    archive = generate_report(
        markdown,
        report_type="diagnosis",
        symbol=symbol,
        output_format=normalized_format,
        title=title,
        filename=filename,
    )
    latest_dir = ROOT / "reports" / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)
    latest_path = latest_dir / f"fundamental_driver_diagnosis.{archive.get('format', normalized_format)}"
    if archive.get("success") and archive.get("path"):
        shutil.copy2(Path(archive["path"]), latest_path)
        archive["latest_path"] = str(latest_path)

    archive.update(
        {
            "title": title,
            "report_type": "diagnosis",
            "symbol": symbol,
            "markdown": markdown,
            "warnings": list(result.warnings),
            "note": f"Generated deterministic fundamental driver diagnosis for {symbol} {metric.upper()}.",
        }
    )
    return archive


def generate_preset_report(
    report_type: str,
    output_format: str = "html",
    args: list[str] | tuple[str, ...] | None = None,
) -> dict:
    """
    Generate a data-direct preset report without requiring LLM content.

    Supported report_type values:
        'sector-rotation', 'stage2', 'strategy-lab', 'portfolio-monitor',
        'swing-playbook', 'diagnosis'

    Returns:
        dict with keys: path, format, title, report_type, success, note
    """
    rt = report_type.lower().strip()
    preset_args = list(args or [])

    # portfolio-monitor is self-contained — delegate directly
    if rt == "portfolio-monitor":
        from terminal.portfolio_monitor import run_eod_report
        result = run_eod_report()
        return {
            "path":        result.get("path"),
            "format":      "html",
            "title":       REPORT_TYPES["portfolio-monitor"]["title"].format(
                               date=datetime.datetime.now().strftime("%d %b %Y")),
            "report_type": "portfolio-monitor",
            "symbol":      "PORTFOLIO",
            "success":     result.get("success", False),
            "note":        result.get("note", ""),
        }

    if rt in {"swing-playbook", "swing_playbook"}:
        from terminal.swing_playbook import SwingPlaybookOptions, generate_swing_playbook

        normalized_format = "md" if output_format.lower().strip() in {"md", "markdown"} else "html"
        result = generate_swing_playbook(options=SwingPlaybookOptions(project_root=ROOT))
        selected_path = (
            result.markdown_path
            if normalized_format == "md"
            else result.html_path
        )
        return {
            "success": result.success,
            "path": selected_path,
            "latest_path": selected_path,
            "format": normalized_format,
            "title": "Swing Trading Playbook",
            "report_type": "swing-playbook",
            "symbol": "MARKET",
            "markdown": result.markdown,
            "warnings": list(result.warnings),
            "note": "Generated swing trading playbook report from current project data.",
        }

    if rt in {"diagnosis", "fundamental-driver", "fundamental_driver"}:
        return _generate_diagnosis_preset_report(preset_args, output_format)

    if rt not in ("sector-rotation", "stage2", "strategy-lab"):
        raise ValueError(
            f"generate_preset_report supports sector-rotation, stage2, strategy-lab, "
            f"portfolio-monitor, swing-playbook, diagnosis; got '{rt}'"
        )

    try:
        if rt == "sector-rotation":
            content = _build_sector_rotation_content()
            sym     = "NSE"
        elif rt == "stage2":
            content = _build_stage2_content()
            sym     = "NSE"
        else:
            content = _build_strategy_lab_content()
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

    if result.get("success") and rt == "strategy-lab":
        latest_dir = ROOT / "reports" / "latest"
        latest_dir.mkdir(parents=True, exist_ok=True)
        source = Path(result["path"])
        latest_path = latest_dir / f"portfolio_strategy_lab.{result.get('format', output_format)}"
        try:
            shutil.copy2(source, latest_path)
            result["latest_path"] = str(latest_path)
        except Exception:
            pass
    result["note"] = (
        "Generated from DB/artifacts with optional LLM narrative overlay."
        if rt == "strategy-lab"
        else "Generated directly from DB snapshot — no LLM required."
    )
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
        theme_id        = AGENT_ADDA_REPORT_THEME_ID,
        engine          = AGENT_ADDA_REPORT_ENGINE,
        badge_class     = badge_class,
        badge_label     = badge_label,
        report_subject  = _html.escape(symbol.upper() if symbol else "Market"),
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
