"""Enhanced Comprehensive NSE Analysis — Postgres-native, branded, full-feature.

PG-report-v2: Faithful port of the legacy R script
``archive/legacy_nse_enhanced_comprehensive_analysis.R``.

Scoring (0..100) — composite of three sub-scores:
    • TECHNICAL  60 pts : Trend(50d-mom) + 50DMA + 200DMA + RSI14 +
                          MACD + 52-week position + Volume vs VEMA20
    • FUNDAMENTAL 25 pts: scaled scores.v_latest_fundamental_scores.enhanced_fund_score
    • RELATIVE-STR 15 pts: 50d return vs Nifty 500's 50d return

Recommendation buckets (legacy 6-tier):
    ≥85 STRONG BUY · ≥70 BUY · ≥55 MOD BUY · ≥45 HOLD · ≥30 WEAK HOLD · <30 SELL

Pipeline: SQL CTE → INSERT … RETURNING → render branded HTML.

CLI:
  python -m reports.enhanced_comprehensive_analysis run | html | both
"""
from __future__ import annotations

import argparse
import html as _h
import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras

from reports import _branding as B

ROOT         = Path(__file__).resolve().parent.parent
REPORTS_DIR  = ROOT / "reports"
SCHEMA_SQL   = ROOT / "postgres" / "report_schema.sql"
PG_DSN       = os.environ.get("AGENT_ADDA_PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"
REPORT_TITLE = "NSE Enhanced Comprehensive Analysis"

MAJOR_INDICES = [
    "NIFTY 50", "NIFTY BANK", "NIFTY AUTO", "NIFTY IT", "NIFTY PHARMA",
    "NIFTY FMCG", "NIFTY METAL", "NIFTY ENERGY", "NIFTY REALTY", "NIFTY MEDIA",
]


def pg():
    return psycopg2.connect(PG_DSN)


# ─────────────────────────────────────────────────────────────────────────────
# 1. ANALYSIS — pure SQL (one transaction)
# ─────────────────────────────────────────────────────────────────────────────
# PG-report-v2: Big CTE chain.
#   per_symbol → window aggregates (SMA/EMA/momentum/MACD-12-26-9 proxy)
#   gains_losses → for Cutler RSI-14
#   nifty500    → benchmark 50-day return
#   scored      → 7 technical components (each capped) + sub-scores + buckets
_STOCK_SQL = """
WITH base AS (
    SELECT  e.symbol, e.trade_date, e.close, e.open, e.high, e.low,
            e.volume, e.change_pct,
            AVG(e.close)  OVER w20  AS sma20,
            AVG(e.close)  OVER w50  AS sma50,
            AVG(e.close)  OVER w200 AS sma200,
            AVG(e.close)  OVER w12  AS ema12_proxy,
            AVG(e.close)  OVER w26  AS ema26_proxy,
            AVG(e.volume) OVER w20  AS vol_avg20,
            MAX(e.high)   OVER w252 AS hi_52w,
            MIN(e.low)    OVER w252 AS lo_52w,
            -- momentum windows
            100.0*(e.close-LAG(e.close,50) OVER pord)
                / NULLIF(LAG(e.close,50) OVER pord,0) AS mom50,
            100.0*(e.close-LAG(e.close,5)  OVER pord)
                / NULLIF(LAG(e.close,5)  OVER pord,0) AS mom5,
            -- gains / losses for Cutler RSI-14
            GREATEST(e.close - LAG(e.close,1) OVER pord, 0) AS gain1,
            GREATEST(LAG(e.close,1) OVER pord - e.close, 0) AS loss1,
            ROW_NUMBER() OVER (PARTITION BY e.symbol ORDER BY e.trade_date DESC) AS rn
    FROM market.equity_eod e
    WHERE e.trade_date >= (SELECT MAX(trade_date) FROM market.equity_eod) - INTERVAL '300 days'
    WINDOW pord AS (PARTITION BY e.symbol ORDER BY e.trade_date),
           w20  AS (PARTITION BY e.symbol ORDER BY e.trade_date ROWS BETWEEN  19 PRECEDING AND CURRENT ROW),
           w50  AS (PARTITION BY e.symbol ORDER BY e.trade_date ROWS BETWEEN  49 PRECEDING AND CURRENT ROW),
           w200 AS (PARTITION BY e.symbol ORDER BY e.trade_date ROWS BETWEEN 199 PRECEDING AND CURRENT ROW),
           w12  AS (PARTITION BY e.symbol ORDER BY e.trade_date ROWS BETWEEN  11 PRECEDING AND CURRENT ROW),
           w26  AS (PARTITION BY e.symbol ORDER BY e.trade_date ROWS BETWEEN  25 PRECEDING AND CURRENT ROW),
           w252 AS (PARTITION BY e.symbol ORDER BY e.trade_date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW)
),
rsi_calc AS (
    SELECT  symbol, trade_date,
            AVG(gain1) OVER (PARTITION BY symbol ORDER BY trade_date
                             ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS avg_gain14,
            AVG(loss1) OVER (PARTITION BY symbol ORDER BY trade_date
                             ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS avg_loss14
    FROM base
),
macd_calc AS (
    SELECT  symbol, trade_date, (ema12_proxy - ema26_proxy) AS macd_line
    FROM base
),
macd_sig AS (
    SELECT  symbol, trade_date, macd_line,
            AVG(macd_line) OVER (PARTITION BY symbol ORDER BY trade_date
                                 ROWS BETWEEN 8 PRECEDING AND CURRENT ROW) AS macd_signal_line
    FROM macd_calc
),
joined AS (
    SELECT  b.*, r.avg_gain14, r.avg_loss14,
            m.macd_line, m.macd_signal_line
    FROM base b
    JOIN rsi_calc  r USING (symbol, trade_date)
    JOIN macd_sig  m USING (symbol, trade_date)
),
latest AS (SELECT * FROM joined WHERE rn = 1),
nifty500 AS (
    SELECT close AS now_close,
           LAG(close,50) OVER (ORDER BY trade_date) AS px_50d_ago
    FROM   market.index_eod
    WHERE  UPPER(index_symbol) = 'NIFTY 500'
       AND trade_date >= (SELECT MAX(trade_date) FROM market.index_eod) - INTERVAL '120 days'
    ORDER  BY trade_date DESC LIMIT 1
),
scored AS (
    SELECT  l.*,
            -- ─── 7 technical components (each capped to its weight) ─────────
            -- (a) Trend / 50d momentum         max 10
            LEAST(10, GREATEST(0, COALESCE(l.mom50,0)*0.25 + 5))                       AS sc_trend,
            -- (b) 50-DMA distance              max 10
            LEAST(10, GREATEST(0, 5 + COALESCE((l.close-l.sma50) /NULLIF(l.sma50,0),0) *100*0.30)) AS sc_50dma,
            -- (c) 200-DMA distance             max 10
            LEAST(10, GREATEST(0, 5 + COALESCE((l.close-l.sma200)/NULLIF(l.sma200,0),0)*100*0.20)) AS sc_200dma,
            -- (d) Cutler RSI-14                max 10
            -- centre on 60 (target overbought-but-trending), 0 at RSI<=30, 10 at RSI>=70
            LEAST(10, GREATEST(0, (
                CASE WHEN l.avg_loss14 = 0 THEN 100
                     ELSE 100 - 100/(1 + l.avg_gain14/NULLIF(l.avg_loss14,0)) END
                - 30) / 4.0)) AS sc_rsi,
            -- (e) MACD                         max 5  (signal line below macd line = bullish)
            CASE WHEN l.macd_line > l.macd_signal_line THEN 5 ELSE 0 END                AS sc_macd,
            -- (f) 52-week position             max 10  (nearer to 52w high → higher)
            LEAST(10, GREATEST(0, 10.0 *
                COALESCE((l.close-l.lo_52w)/NULLIF(l.hi_52w-l.lo_52w,0), 0.5))) AS sc_52w,
            -- (g) Volume vs 20d avg            max 5  (linear up to 2x)
            LEAST(5, GREATEST(0, 5.0 * COALESCE(l.volume::numeric/NULLIF(l.vol_avg20,0)/2.0, 0.5))) AS sc_volume,
            -- raw RSI for display
            CASE WHEN l.avg_loss14 = 0 THEN 100
                 ELSE 100 - 100/(1 + l.avg_gain14/NULLIF(l.avg_loss14,0)) END           AS rsi14,
            CASE WHEN l.macd_line > l.macd_signal_line THEN 'BULLISH'
                 WHEN l.macd_line < l.macd_signal_line THEN 'BEARISH'
                 ELSE 'NEUTRAL' END                                                     AS macd_text,
            -- 50-day return for RS (vs nifty500 below)
            l.mom50                                                                     AS stock_50d_ret
    FROM latest l
),
final AS (
    SELECT  s.*,
            -- ─── sub-scores ─────────────────────────────────────────────────
            ROUND((s.sc_trend + s.sc_50dma + s.sc_200dma + s.sc_rsi + s.sc_macd + s.sc_52w + s.sc_volume)::numeric, 2) AS tech_score,
            -- fundamental score: scale 0-100 → 0-25
            ROUND((COALESCE(f.enhanced_fund_score, 50.0) * 0.25)::numeric, 2)           AS fund_score,
            -- relative strength vs Nifty 500: outperformance over 50d
            -- 0 pts at -10pp, 7.5 pts at 0pp, 15 pts at +10pp
            ROUND(LEAST(15, GREATEST(0,
                7.5 + (COALESCE(s.stock_50d_ret,0) -
                       100.0*((SELECT now_close FROM nifty500)/NULLIF((SELECT px_50d_ago FROM nifty500),0) - 1)
                      ) * 0.75
            ))::numeric, 2)                                                             AS rs_score,
            -- absolute outperformance % for the RS-bucket
            (COALESCE(s.stock_50d_ret,0) -
             100.0*((SELECT now_close FROM nifty500)/NULLIF((SELECT px_50d_ago FROM nifty500),0) - 1))
                                                                                        AS rs_outperf_pct,
            -- volume ratio for display
            ROUND((s.volume::numeric/NULLIF(s.vol_avg20,0))::numeric, 2)                AS volume_ratio
    FROM scored s
    LEFT JOIN scores.v_latest_fundamental_scores f USING (symbol)
)
SELECT  symbol, close AS current_price, open AS open_price, high AS high_price,
        low AS low_price, volume,
        ROUND(((volume*close)/1e7)::numeric, 2)                              AS trading_value_cr,
        ROUND((tech_score + fund_score + rs_score)::numeric, 2)              AS score,
        ROUND(change_pct::numeric, 2)                                        AS day_change_pct,
        (close > sma50)                                                      AS above_50dma,
        (close > sma200)                                                     AS above_200dma,
        CASE WHEN close > sma20 AND sma20 > sma50  THEN 'BULLISH'
             WHEN close < sma20 AND sma20 < sma50  THEN 'BEARISH'
             ELSE 'NEUTRAL' END                                              AS daily_signal,
        CASE WHEN close > sma50 AND sma50 > sma200 THEN 'BULLISH'
             WHEN close < sma50 AND sma50 < sma200 THEN 'BEARISH'
             ELSE 'NEUTRAL' END                                              AS weekly_signal,
        ROUND(rsi14::numeric, 1)                                             AS rsi,
        tech_score, fund_score, rs_score, macd_text                          AS macd_signal,
        ROUND((100.0*COALESCE((close-lo_52w)/NULLIF(hi_52w-lo_52w,0), 0.5))::numeric, 2) AS week52_position,
        volume_ratio,
        CASE WHEN rs_outperf_pct >  3 THEN 'OUTPERFORMING'
             WHEN rs_outperf_pct < -3 THEN 'UNDERPERFORMING'
             ELSE 'IN_LINE' END                                              AS rs_vs_nifty500
FROM final
WHERE volume > 100000 AND close > 100
ORDER BY score DESC NULLS LAST
LIMIT 200;
"""

# Index scoring keeps the v1 SQL — indices don't need the fundamental/RS join
_INDEX_SQL = """
WITH per_idx AS (
    SELECT  index_symbol, trade_date, close, change_pct,
            AVG(close) OVER w50  AS sma50,
            AVG(close) OVER w200 AS sma200,
            AVG(close) OVER w20  AS sma20,
            100.0*(close-LAG(close,50) OVER (PARTITION BY index_symbol ORDER BY trade_date))
                / NULLIF(LAG(close,50) OVER (PARTITION BY index_symbol ORDER BY trade_date),0) AS mom50,
            100.0*(close-LAG(close,5)  OVER (PARTITION BY index_symbol ORDER BY trade_date))
                / NULLIF(LAG(close,5)  OVER (PARTITION BY index_symbol ORDER BY trade_date),0) AS mom5,
            100.0*(close-LAG(close,14) OVER (PARTITION BY index_symbol ORDER BY trade_date))
                / NULLIF(LAG(close,14) OVER (PARTITION BY index_symbol ORDER BY trade_date),0) AS mom14,
            ROW_NUMBER() OVER (PARTITION BY index_symbol ORDER BY trade_date DESC) AS rn
    FROM market.index_eod
    WHERE UPPER(index_symbol) = ANY(%s)
      AND trade_date >= (SELECT MAX(trade_date) FROM market.index_eod) - INTERVAL '300 days'
    WINDOW w50  AS (PARTITION BY index_symbol ORDER BY trade_date ROWS BETWEEN  49 PRECEDING AND CURRENT ROW),
           w200 AS (PARTITION BY index_symbol ORDER BY trade_date ROWS BETWEEN 199 PRECEDING AND CURRENT ROW),
           w20  AS (PARTITION BY index_symbol ORDER BY trade_date ROWS BETWEEN  19 PRECEDING AND CURRENT ROW)
),
latest AS (SELECT * FROM per_idx WHERE rn=1)
SELECT  index_symbol, close, change_pct,
        ROUND((
            LEAST(25, GREATEST(0, COALESCE(mom50,0)*0.6 + 12.5)) +
            CASE WHEN sma50  IS NULL THEN 12 ELSE
                 LEAST(25, GREATEST(0, 12.5 + (close-sma50) /NULLIF(sma50,0) *100*0.4)) END +
            CASE WHEN sma200 IS NULL THEN 12 ELSE
                 LEAST(25, GREATEST(0, 12.5 + (close-sma200)/NULLIF(sma200,0)*100*0.3)) END +
            LEAST(25, GREATEST(0, 12.5 + COALESCE(mom5,0)*1.5))
        )::numeric, 2)                                                AS score,
        ROUND(GREATEST(0, LEAST(100, 50 + COALESCE(mom14,0)*1.5))::numeric, 1) AS rsi,
        ROUND(COALESCE(mom50,0)::numeric, 2)                          AS momentum_50d,
        ROUND(COALESCE(mom14,0)::numeric, 2)                          AS relative_strength,
        CASE WHEN close > sma20 AND sma20 > sma50  THEN 'BULLISH'
             WHEN close < sma20 AND sma20 < sma50  THEN 'BEARISH'
             ELSE 'NEUTRAL' END                                       AS trend_signal,
        CASE WHEN close > sma50 AND sma50 > sma200 THEN 'BULLISH'
             WHEN close < sma50 AND sma50 < sma200 THEN 'BEARISH'
             ELSE 'NEUTRAL' END                                       AS trading_signal
FROM latest
ORDER BY score DESC NULLS LAST
"""


def compute_and_persist_run() -> int:
    """Compute scores, persist run, return new run_id."""
    with pg() as conn, conn.cursor() as cur:
        # Idempotent migration in case schema needs new columns
        cur.execute(SCHEMA_SQL.read_text())

        cur.execute("SELECT MAX(trade_date) FROM market.equity_eod")
        analysis_date = cur.fetchone()[0]
        if analysis_date is None:
            raise SystemExit("No data in market.equity_eod")
        print(f"[run] analysis_date = {analysis_date}")

        cur.execute(_STOCK_SQL)
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]
        print(f"[run] filtered stocks: {len(rows)}")

        cur.execute("SELECT COUNT(*) FROM market.equity_eod WHERE trade_date=%s", (analysis_date,))
        universe_size = cur.fetchone()[0]

        cur.execute(_INDEX_SQL, ([i.upper() for i in MAJOR_INDICES],))
        idx_rows = cur.fetchall()
        print(f"[run] indices: {len(idx_rows)}")

        # PG-report-v2: composite uses the scored stocks + indices
        avg_stock = sum(float(r[7]  or 0) for r in rows)     / max(len(rows), 1)
        avg_idx   = sum(float(r[3]  or 0) for r in idx_rows) / max(len(idx_rows), 1)
        composite = round((avg_stock + avg_idx) / 2, 2)
        sentiment = ("BULLISH" if composite >= 60 else
                     "NEUTRAL" if composite >= 40 else "BEARISH")
        print(f"[run] composite={composite} sentiment={sentiment}")

        cur.execute("""
            INSERT INTO report.enhanced_runs
              (analysis_date, universe_size, stocks_analyzed, stocks_filtered,
               indices_analyzed, market_composite_score, market_sentiment, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING run_id
        """, (analysis_date, universe_size, universe_size, len(rows),
              len(idx_rows), composite, sentiment,
              "v2 — full technical+fundamental+RS"))
        run_id = cur.fetchone()[0]

        # Map columns by name for clarity
        idx_of = {c: i for i, c in enumerate(cols)}
        def g(row, name): return row[idx_of[name]]

        psycopg2.extras.execute_values(cur, """
            INSERT INTO report.enhanced_filtered_stocks
              (run_id, rank, symbol, score, recommendation, current_price,
               open_price, high_price, low_price, volume, trading_value_cr,
               weekly_signal, daily_signal, day_change_pct, rsi,
               above_50dma, above_200dma,
               tech_score, fund_score, rs_score, macd_signal,
               week52_position, volume_ratio, rs_vs_nifty500)
            VALUES %s
        """, [
            (run_id, i+1, g(r,'symbol'), g(r,'score'), _bucket(g(r,'score')),
             g(r,'current_price'), g(r,'open_price'), g(r,'high_price'),
             g(r,'low_price'), g(r,'volume'), g(r,'trading_value_cr'),
             g(r,'weekly_signal'), g(r,'daily_signal'), g(r,'day_change_pct'),
             g(r,'rsi'), g(r,'above_50dma'), g(r,'above_200dma'),
             g(r,'tech_score'), g(r,'fund_score'), g(r,'rs_score'),
             g(r,'macd_signal'), g(r,'week52_position'), g(r,'volume_ratio'),
             g(r,'rs_vs_nifty500'))
            for i, r in enumerate(rows)
        ])

        psycopg2.extras.execute_values(cur, """
            INSERT INTO report.enhanced_indices
              (run_id, index_name, score, recommendation, current_value,
               weekly_signal, daily_signal, day_change_pct, rsi, momentum_50d,
               relative_strength, trend_signal, trading_signal)
            VALUES %s
        """, [
            (run_id, r[0], r[3], _bucket(r[3]), r[1],
             r[8], r[7], r[2], r[4], r[5], r[6], r[7], r[8])
            for r in idx_rows
        ])
        conn.commit()
        print(f"[run] run_id = {run_id}")
        return run_id


# PG-report-v2: legacy 6-tier buckets
def _bucket(score):
    if score is None: return None
    s = float(score)
    if s >= 85: return "STRONG BUY"
    if s >= 70: return "BUY"
    if s >= 55: return "MOD BUY"
    if s >= 45: return "HOLD"
    if s >= 30: return "WEAK HOLD"
    return "SELL"


# ─────────────────────────────────────────────────────────────────────────────
# 2. HTML rendering — pure SELECT, branded
# ─────────────────────────────────────────────────────────────────────────────
def render_html(run_id: int | None = None) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    with pg() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if run_id is None:
            cur.execute("SELECT * FROM report.v_latest_run")
        else:
            cur.execute("SELECT * FROM report.enhanced_runs WHERE run_id=%s", (run_id,))
        run = cur.fetchone()
        if not run:
            raise SystemExit(f"No run found for run_id={run_id}")
        run_id = run["run_id"]

        cur.execute("""SELECT * FROM report.enhanced_indices
                       WHERE run_id=%s ORDER BY score DESC NULLS LAST""", (run_id,))
        indices = cur.fetchall()
        cur.execute("""SELECT * FROM report.enhanced_filtered_stocks
                       WHERE run_id=%s ORDER BY score DESC NULLS LAST""", (run_id,))
        stocks = cur.fetchall()

    html = _build_html(run, indices, stocks)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    out  = REPORTS_DIR / f"Enhanced_Comprehensive_Analysis_{ts}.html"
    out.write_text(html, encoding="utf-8")
    print(f"[html] wrote {out}")
    return out


def _badge(text):
    if text in (None, ""): return '<span class="muted">—</span>'
    cls = str(text).replace(" ", "")
    return f'<span class="badge b-{cls}">{_h.escape(str(text))}</span>'

def _pct(v):
    if v is None: return '<span class="muted">—</span>'
    f = float(v)
    cls = "pos" if f > 0 else "neg" if f < 0 else ""
    return f'<span class="num {cls}" data-v="{f:.4f}">{f:+.2f}%</span>'

def _num(v, fmt="{:,.2f}"):
    if v is None: return '<span class="muted">—</span>'
    f = float(v)
    return f'<span class="num" data-v="{f:.6f}">{fmt.format(f)}</span>'

def _check(v):
    return '<span class="dot ok">✓</span>' if v else '<span class="dot no">✗</span>'


def _build_html(run, indices, stocks) -> str:
    sentiment = run["market_sentiment"] or "NEUTRAL"
    composite = float(run["market_composite_score"] or 0)

    kpis = (
        '<div class="metrics-row">'
        f'<div class="metric-card"><div class="metric-label">Universe</div>'
        f'<div class="metric-value">{run["universe_size"]:,}</div>'
        f'<div class="metric-sub">stocks on {run["analysis_date"]}</div></div>'
        f'<div class="metric-card"><div class="metric-label">Filtered</div>'
        f'<div class="metric-value">{run["stocks_filtered"]:,}</div>'
        f'<div class="metric-sub">Vol &gt; 100k · Px &gt; ₹100</div></div>'
        f'<div class="metric-card"><div class="metric-label">Indices</div>'
        f'<div class="metric-value">{run["indices_analyzed"]}</div>'
        f'<div class="metric-sub">major NIFTY baskets</div></div>'
        f'<div class="metric-card"><div class="metric-label">Composite</div>'
        f'<div class="metric-value">{composite:.1f}</div>'
        f'<div class="metric-sub">avg(stocks · indices)</div></div>'
        f'<div class="metric-card"><div class="metric-label">Sentiment</div>'
        f'<div class="metric-value" style="font-size:1.05rem">{_badge(sentiment)}</div>'
        f'<div class="metric-sub">composite-band</div></div>'
        '</div>'
    )

    idx_rows = "".join(
        f'<tr><td><b>{_h.escape(r["index_name"])}</b></td>'
        f'<td>{_num(r["score"], "{:.1f}")}</td>'
        f'<td>{_badge(r["recommendation"])}</td>'
        f'<td>{_num(r["current_value"], "{:,.2f}")}</td>'
        f'<td>{_pct(r["day_change_pct"])}</td>'
        f'<td>{_num(r["rsi"], "{:.1f}")}</td>'
        f'<td>{_pct(r["momentum_50d"])}</td>'
        f'<td>{_pct(r["relative_strength"])}</td>'
        f'<td>{_badge(r["trend_signal"])}</td>'
        f'<td>{_badge(r["trading_signal"])}</td></tr>'
        for r in indices
    ) or '<tr><td colspan="10" class="muted">No indices.</td></tr>'

    idx_table = (
        '<div class="tbl-wrap"><table class="sortable"><thead><tr>'
        '<th data-sort="str">Index</th><th data-sort="num">Score</th>'
        '<th data-sort="str">Reco</th><th data-sort="num">Last</th>'
        '<th data-sort="num">Day %</th><th data-sort="num">RSI(14)</th>'
        '<th data-sort="num">Mom 50d</th><th data-sort="num">Mom 14d</th>'
        '<th data-sort="str">Trend</th><th data-sort="str">Signal</th>'
        f'</tr></thead><tbody>{idx_rows}</tbody></table></div>'
    )

    # PG-report-v2: stocks table now exposes all sub-scores
    stk_rows = "".join(
        f'<tr><td>{r["rank"]}</td><td><b>{_h.escape(r["symbol"])}</b></td>'
        f'<td><b>{_num(r["score"], "{:.1f}")}</b></td>'
        f'<td>{_badge(r["recommendation"])}</td>'
        f'<td>{_num(r["tech_score"], "{:.1f}")}</td>'
        f'<td>{_num(r["fund_score"], "{:.1f}")}</td>'
        f'<td>{_num(r["rs_score"], "{:.1f}")}</td>'
        f'<td>{_num(r["current_price"], "₹{:,.2f}")}</td>'
        f'<td>{_pct(r["day_change_pct"])}</td>'
        f'<td>{_num((r["volume"] or 0)/1e5, "{:,.1f}")}</td>'
        f'<td>{_num(r["trading_value_cr"], "{:,.2f}")}</td>'
        f'<td>{_num(r["rsi"], "{:.1f}")}</td>'
        f'<td>{_badge(r["macd_signal"])}</td>'
        f'<td>{_num(r["week52_position"], "{:.0f}%")}</td>'
        f'<td>{_num(r["volume_ratio"], "{:.2f}×")}</td>'
        f'<td>{_badge(r["rs_vs_nifty500"])}</td>'
        f'<td>{_badge(r["daily_signal"])}</td>'
        f'<td>{_badge(r["weekly_signal"])}</td>'
        f'<td>{_check(r["above_50dma"])}</td>'
        f'<td>{_check(r["above_200dma"])}</td></tr>'
        for r in stocks
    ) or '<tr><td colspan="20" class="muted">No stocks.</td></tr>'

    stk_table = (
        '<div class="tbl-wrap"><table class="sortable"><thead><tr>'
        '<th data-sort="num">#</th><th data-sort="str">Symbol</th>'
        '<th data-sort="num">Score</th><th data-sort="str">Reco</th>'
        '<th data-sort="num">Tech /60</th><th data-sort="num">Fund /25</th>'
        '<th data-sort="num">RS /15</th>'
        '<th data-sort="num">Price</th><th data-sort="num">Day %</th>'
        '<th data-sort="num">Vol (L)</th><th data-sort="num">Val (Cr)</th>'
        '<th data-sort="num">RSI</th><th data-sort="str">MACD</th>'
        '<th data-sort="num">52W Pos</th><th data-sort="num">Vol×</th>'
        '<th data-sort="str">RS vs N500</th>'
        '<th data-sort="str">Daily</th><th data-sort="str">Weekly</th>'
        '<th data-sort="str">50D</th><th data-sort="str">200D</th>'
        f'</tr></thead><tbody>{stk_rows}</tbody></table></div>'
    )

    meth = (
        '<div class="card"><h2>Methodology — full composite</h2>'
        '<p style="font-size:13px;color:var(--muted);line-height:1.7;margin-bottom:10px">'
        'Each instrument is scored 0–100 by combining three sub-scores:</p>'
        '<table style="width:100%;font-size:13px"><thead><tr>'
        '<th style="text-align:left">Sub-score</th><th style="text-align:right">Max</th>'
        '<th style="text-align:left">Components</th></tr></thead><tbody>'
        '<tr><td><b>Technical</b></td><td class="num">60</td>'
        '<td>Trend (50d mom, 10) + 50-DMA dist (10) + 200-DMA dist (10) + RSI-14 (10) '
        '+ MACD (5) + 52-week position (10) + Volume vs VEMA20 (5)</td></tr>'
        '<tr><td><b>Fundamental</b></td><td class="num">25</td>'
        '<td>Scaled <code>scores.v_latest_fundamental_scores.enhanced_fund_score</code> '
        '(earnings quality, sales growth, financial strength, institutional backing)</td></tr>'
        '<tr><td><b>Relative Strength</b></td><td class="num">15</td>'
        '<td>50-day return relative to <code>NIFTY 500</code>; +0.75 pt per pp of outperformance, '
        'centred at 7.5 pts</td></tr></tbody></table>'
        '<p style="font-size:13px;color:var(--muted);line-height:1.7;margin-top:14px">'
        'Recommendation buckets (legacy R thresholds): '
        '<b>≥85 STRONG BUY · ≥70 BUY · ≥55 MOD BUY · ≥45 HOLD · ≥30 WEAK HOLD · &lt;30 SELL</b>. '
        'Universe filter applied <i>before</i> ranking: volume &gt; 100,000 AND price &gt; ₹100. '
        'RSI uses Cutler smoothing (SMA-14 of gains/losses); MACD is a 12/26/9 SMA proxy. '
        'All numbers come from PostgreSQL '
        '<code>market.equity_eod</code>, <code>market.index_eod</code>, '
        '<code>scores.v_latest_fundamental_scores</code>; results persist in '
        '<code>report.enhanced_runs / enhanced_filtered_stocks / enhanced_indices</code>.</p>'
        '</div>'
    )

    meta = [
        f"Analysis · {run['analysis_date']}",
        f"Run #{run['run_id']}",
        f"Generated · {run['run_ts'].strftime('%Y-%m-%d %H:%M')}",
    ]
    nav = (
        '<nav class="main-nav"><div class="nav-inner">'
        '<button class="nav-btn active" data-tab="overview">Overview</button>'
        '<button class="nav-btn" data-tab="indices">Indices</button>'
        '<button class="nav-btn" data-tab="stocks">Top Stocks</button>'
        '<button class="nav-btn" data-tab="methodology">Methodology</button>'
        '<button class="nav-btn" data-tab="disclaimer">Disclaimer</button>'
        '</div></nav>'
    )

    panes = (
        f'<section id="tab-overview" class="tab-pane active">{kpis}'
        f'<div class="card"><h2>Major indices snapshot</h2>{idx_table}</div></section>'
        f'<section id="tab-indices" class="tab-pane"><div class="card">'
        f'<h2>Major indices — full</h2>{idx_table}</div></section>'
        f'<section id="tab-stocks" class="tab-pane"><div class="card">'
        f'<h2>Top {len(stocks)} ranked stocks</h2>{stk_table}</div></section>'
        f'<section id="tab-methodology" class="tab-pane">{meth}</section>'
        f'{B.full_legal_pane()}'
    )

    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{REPORT_TITLE} — {run["analysis_date"]}</title>'
        f'<style>{B.base_css()}</style></head><body>'
        f'{B.header_html(REPORT_TITLE, meta)}'
        f'{B.disclaimer_strip()}'
        f'{B.print_only_header_footer(REPORT_TITLE)}'
        f'{nav}'
        f'<main class="content">{panes}</main>'
        f'{B.tab_nav_script()}'
        '</body></html>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="enhanced_comprehensive_analysis")
    p.add_argument("action", nargs="?", default="both", choices=["run", "html", "both"])
    p.add_argument("--run-id", type=int, default=None,
                   help="Render HTML for a specific run (default: latest)")
    args = p.parse_args(argv)

    run_id = args.run_id
    if args.action in ("run", "both"):
        run_id = compute_and_persist_run()
    if args.action in ("html", "both"):
        render_html(run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
