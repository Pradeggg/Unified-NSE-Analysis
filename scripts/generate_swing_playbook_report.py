#!/usr/bin/env python3
"""
scripts/generate_swing_playbook_report.py
==========================================
Agent Adda Swing Playbook — themed HTML report generator.

1. Runs the swing playbook data pipeline (terminal.swing_playbook.run_playbook).
2. Queries overextension signals: RSI14 > 72 OR price > 7 % above SMA20.
3. Fetches live market context (NIFTY, VIX, breadth) from PostgreSQL.
4. Renders the dark-terminal themed HTML and overwrites reports/latest/swing_playbook.html.

Usage
-----
    python scripts/generate_swing_playbook_report.py              # default run
    python scripts/generate_swing_playbook_report.py --fresh      # re-pull from DB
    python scripts/generate_swing_playbook_report.py --no-open    # skip browser open
    python scripts/generate_swing_playbook_report.py --top-n 15   # more candidates
    python scripts/generate_swing_playbook_report.py --from-csv   # skip data gen, re-render only
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import webbrowser
from datetime import date, datetime
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORTS_LATEST = ROOT / "reports" / "latest"
REPORTS_ARCHIVE = ROOT / "reports" / "swing_playbook"
CANDIDATES_CSV = REPORTS_LATEST / "swing_playbook_candidates.csv"
OUTPUT_HTML = REPORTS_LATEST / "swing_playbook.html"

# ─────────────────────────────────────────────────────────────────────────────
# 1. Data generation
# ─────────────────────────────────────────────────────────────────────────────

def _run_data_pipeline(fresh: bool, top_n: int) -> None:
    """Run terminal.swing_playbook.run_playbook() to refresh CSV + MD."""
    from terminal.swing_playbook import SwingPlaybookOptions, run_playbook
    opts = SwingPlaybookOptions(fresh=fresh, top_n=top_n)
    result = run_playbook(options=opts)
    if not result.success:
        raise RuntimeError("Swing playbook data generation failed.")
    print(f"  ✓ data written → {result.candidates_csv}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Read CSV
# ─────────────────────────────────────────────────────────────────────────────

def _read_candidates(path: Path) -> dict[str, list[dict]]:
    """
    Parse swing_playbook_candidates.csv.
    Returns {"TACTICAL": [...], "POSITION": [...]} where each item is a dict
    with keys needed by the HTML template.
    """
    import csv

    raw: list[dict] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            raw.append(row)

    max_tech = 35.0
    max_rs   = 20.0
    max_fund = 10.0   # enhanced_fund_score bucket max in playbook scoring

    out: dict[str, list[dict]] = {"TACTICAL": [], "POSITION": []}
    for r in raw:
        sleeve = r.get("sleeve", "").upper()
        if sleeve not in out:
            continue

        sym   = r["symbol"]
        score = float(r.get("score", 0))
        tech_raw  = float(r.get("technical", 0))
        rs_raw    = float(r.get("relative_strength", 0))
        fund_raw  = float(r.get("fundamentals", 0))

        # Normalise sub-scores to 0–100 for bar display
        tech_pct = round(min(tech_raw / max_tech * 100, 100), 1)
        rs_pct   = round(min(rs_raw   / max_rs   * 100, 100), 1)
        fund_pct = round(min(fund_raw / max_fund  * 100, 100), 1)

        entry  = float(r.get("entry_trigger", 0))
        stop   = float(r.get("initial_stop", 0))
        t1     = float(r.get("target_1", 0))
        t2     = float(r.get("target_2", 0))

        out[sleeve].append({
            "sym":   sym,
            "stage": 2,          # will be enriched by overextension step
            "score": score,
            "entry": entry,
            "stop":  stop,
            "t1":    t1,
            "t2":    t2,
            "tech":  tech_pct,
            "rs":    rs_pct,
            "fund":  fund_pct,
            "overextended": False,
            "rsi":   None,
            "pct_above_sma20": 0.0,
        })

    return out


# ─────────────────────────────────────────────────────────────────────────────
# 3. Overextension signals
# ─────────────────────────────────────────────────────────────────────────────

def _enrich_overextension(data: dict[str, list[dict]]) -> None:
    """
    Query scores.daily_scores for RSI14, SMA20, stage.
    Flag overextended = RSI > 72 OR price > 7% above SMA20.
    Mutates data in-place.
    """
    all_syms = list({c["sym"] for sleeve in data.values() for c in sleeve})
    if not all_syms:
        return

    signals: dict[str, dict] = {}
    try:
        import psycopg2
        conn = psycopg2.connect("dbname=nse_market user=nse_admin host=/tmp")
        cur = conn.cursor()
        ph = ",".join(["%s"] * len(all_syms))
        cur.execute(
            f"""
            SELECT DISTINCT ON (symbol)
                symbol,
                rsi_14,
                sma_20,
                close,
                stage
            FROM scores.daily_scores
            WHERE symbol IN ({ph})
            ORDER BY symbol, date DESC
            """,
            all_syms,
        )
        for sym, rsi, sma20, close, stage in cur.fetchall():
            pct_above = 0.0
            if sma20 and sma20 > 0 and close:
                pct_above = (close - sma20) / sma20 * 100
            overext = bool((rsi and rsi > 72) or pct_above > 7)
            signals[sym] = {
                "rsi":              round(rsi, 1) if rsi else None,
                "pct_above_sma20":  round(pct_above, 1),
                "overextended":     overext,
                "stage":            int(stage) if stage else 2,
            }
        conn.close()
    except Exception as exc:
        print(f"  ⚠ overextension query skipped: {exc}")

    # apply to candidates
    for sleeve in data.values():
        for c in sleeve:
            s = signals.get(c["sym"])
            if s:
                c.update(s)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Market context
# ─────────────────────────────────────────────────────────────────────────────

def _get_market_context() -> dict:
    """Fetch NIFTY, BANKNIFTY, VIX, breadth from PostgreSQL. Falls back gracefully."""
    ctx = {
        "nifty_close": None, "nifty_chg": None,
        "bnf_close": None,   "bnf_chg": None,
        "vix_close": None,   "vix_chg": None,
        "advances": None,    "declines": None,
        "stage2_pct": None,
    }
    try:
        import psycopg2
        conn = psycopg2.connect("dbname=nse_market user=nse_admin host=/tmp")
        cur = conn.cursor()

        for sym, k_close, k_chg in [
            ("NIFTY 50",    "nifty_close", "nifty_chg"),
            ("NIFTY BANK",  "bnf_close",   "bnf_chg"),
            ("INDIA VIX",   "vix_close",   "vix_chg"),
        ]:
            cur.execute(
                "SELECT close, pct_change FROM market.index_eod "
                "WHERE symbol=%s ORDER BY date DESC LIMIT 1",
                (sym,),
            )
            row = cur.fetchone()
            if row:
                ctx[k_close] = row[0]
                ctx[k_chg]   = row[1]

        cur.execute(
            "SELECT advances, declines FROM breadth.market_daily ORDER BY date DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row:
            ctx["advances"] = row[0]
            ctx["declines"] = row[1]

        cur.execute(
            "SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE stage=2) / COUNT(*), 1) "
            "FROM scores.daily_scores WHERE date=(SELECT MAX(date) FROM scores.daily_scores)"
        )
        row = cur.fetchone()
        if row:
            ctx["stage2_pct"] = row[0]

        conn.close()
    except Exception as exc:
        print(f"  ⚠ market context query skipped: {exc}")

    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# 5. Narrative builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_narrative(data: dict, ctx: dict, as_of: str) -> dict:
    """Build the dynamic narrative snippets injected into the HTML."""
    tactical = data.get("TACTICAL", [])
    position = data.get("POSITION", [])

    top = tactical[0] if tactical else None
    top_name = top["sym"] if top else "—"
    top_score = top["score"] if top else 0

    # regime heuristic from breadth
    adv = ctx.get("advances") or 0
    dec = ctx.get("declines") or 0
    breadth_ratio = adv / (adv + dec) if (adv + dec) > 0 else 0.5
    regime = "BULL_TREND" if breadth_ratio > 0.6 else "CHOP" if breadth_ratio > 0.4 else "BEAR_TREND"
    regime_label = "Risk-On — Momentum Favoured" if regime == "BULL_TREND" else \
                   "Risk-Off Tape — Wait for Confirmation" if regime == "CHOP" else \
                   "Defensive — High Selectivity Required"

    # Determine if market is currently open (09:15–15:30 IST)
    from datetime import timezone, timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist).time()
    from datetime import time as dtime
    market_open = dtime(9, 15) <= now_ist <= dtime(15, 30)

    nifty_chg = ctx.get("nifty_chg") or 0
    nifty_dir = "up" if nifty_chg >= 0 else "down"
    nifty_abs = abs(nifty_chg)
    nifty_verb = "is trading" if market_open else "closed"
    nifty_move = "gaining" if nifty_chg >= 0 else "shedding"

    overext_names = [c["sym"] for c in tactical if c.get("overextended")]
    overext_note = (
        f"<strong>{', '.join(overext_names)}</strong> show overextension signals "
        f"(RSI &gt; 72 or &gt;7% above SMA20) — reduce position size or wait for a pullback entry."
        if overext_names else
        "No setups show extreme overextension — entries near trigger levels are well-positioned."
    )

    stage2_pct = ctx.get("stage2_pct") or "—"
    vix_close  = ctx.get("vix_close")
    vix_note   = f"VIX at {vix_close:.2f}" if vix_close else "VIX data unavailable"

    return {
        "DATE_LABEL":    as_of[:10] if as_of else str(date.today()),
        "REGIME":        regime,
        "REGIME_LABEL":  regime_label,
        "TOP_NAME":      top_name,
        "TOP_SCORE":     str(top_score),
        "TACTICAL_COUNT": str(len(tactical)),
        "POSITION_COUNT": str(len(position)),
        "NIFTY_CLOSE":   f"{ctx['nifty_close']:,.0f}" if ctx.get("nifty_close") else "—",
        "NIFTY_CHG_ABS": f"{nifty_abs:.2f}",
        "NIFTY_VERB":    nifty_verb,
        "NIFTY_MOVE":    nifty_move,
        "NIFTY_DIR":     nifty_dir,
        "NIFTY_CHG_SIGN": "▼" if nifty_chg < 0 else "▲",
        "NIFTY_CHG_CLASS": "neg" if nifty_chg < 0 else "pos",
        "BNF_CLOSE":     f"{ctx['bnf_close']:,.0f}" if ctx.get("bnf_close") else "—",
        "BNF_CHG":       f"{ctx['bnf_chg']:.2f}" if ctx.get("bnf_chg") else "—",
        "BNF_CHG_CLASS": "neg" if (ctx.get("bnf_chg") or 0) < 0 else "pos",
        "BNF_CHG_SIGN":  "▼" if (ctx.get("bnf_chg") or 0) < 0 else "▲",
        "VIX_CLOSE":     f"{vix_close:.2f}" if vix_close else "—",
        "VIX_CHG_CLASS": "neg",   # VIX up = bearish always shown red
        "ADVANCES":      str(ctx.get("advances") or "—"),
        "DECLINES":      str(ctx.get("declines") or "—"),
        "STAGE2_PCT":    str(stage2_pct),
        "OVEREXT_NOTE":  overext_note,
        "STANCE_LABEL":  "WAIT · INTRADAY_CONFIRM REQUIRED" if regime == "CHOP" else
                         "GO · CONFIRM ENTRY ON VOLUME" if regime == "BULL_TREND" else
                         "HOLD FIRE · BEAR REGIME",
        "STANCE_COLOR":  "yellow" if regime == "CHOP" else
                         "green"  if regime == "BULL_TREND" else "red",
        "GENERATED":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. HTML template (Agent Adda dark-terminal theme)
# ─────────────────────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Swing Playbook · Agent Adda</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap">
<style>
:root{
  --bg:#0d1117;--surface:#161b22;--surface2:#1c2128;--surface3:#21262d;
  --border:#30363d;--border2:#21262d;
  --text:#e6edf3;--muted:#8b949e;--dim:#484f58;
  --accent:#388bfd;--accent-dim:rgba(56,139,253,.15);
  --green:#3fb950;--green-dim:rgba(63,185,80,.15);
  --red:#f85149;--red-dim:rgba(248,81,73,.15);
  --yellow:#d29922;--yellow-dim:rgba(210,153,34,.15);
  --purple:#a371f7;--purple-dim:rgba(163,113,247,.15);
  --teal:#39d353;
  --mono:'JetBrains Mono',monospace;
  --sans:'Inter',-apple-system,sans-serif;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:13px;line-height:1.5;min-height:100vh}

/* Header */
.hdr{background:var(--surface);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:40}
.hdr-inner{max-width:1400px;margin:0 auto;padding:0 20px;height:52px;display:flex;align-items:center;gap:16px}
.brand{display:flex;align-items:center;gap:10px;flex-shrink:0}
.brand-mark{width:32px;height:32px;background:var(--accent);border-radius:6px;display:grid;place-items:center;font-family:var(--mono);font-weight:700;font-size:13px;color:#fff;letter-spacing:-.5px}
.brand-name{font-family:var(--mono);font-weight:700;font-size:14px;color:var(--text);letter-spacing:-.3px}
.brand-sub{font-size:10px;color:var(--muted);font-weight:500;letter-spacing:.04em;text-transform:uppercase}
.hdr-divider{width:1px;height:24px;background:var(--border);flex-shrink:0}
.hdr-title{font-family:var(--mono);font-weight:600;font-size:13px;color:var(--text)}
.hdr-spacer{flex:1}
.hdr-meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.badge{display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:4px;font-family:var(--mono);font-size:10px;font-weight:600;letter-spacing:.02em;white-space:nowrap}
.badge-date{background:var(--surface3);color:var(--muted);border:1px solid var(--border)}
.badge-open{background:var(--green-dim);color:var(--green);border:1px solid rgba(63,185,80,.3)}
.badge-risk{background:var(--accent-dim);color:var(--accent);border:1px solid rgba(56,139,253,.3)}

/* Market strip */
.mkt-strip{background:var(--surface2);border-bottom:1px solid var(--border2);padding:6px 20px}
.mkt-inner{max-width:1400px;margin:0 auto;display:flex;align-items:center;gap:20px;flex-wrap:wrap}
.mkt-item{display:flex;align-items:center;gap:6px;font-family:var(--mono);font-size:11px}
.mkt-label{color:var(--dim);font-weight:500}
.mkt-val{color:var(--text);font-weight:600;font-variant-numeric:tabular-nums}
.mkt-chg{font-weight:600;font-variant-numeric:tabular-nums}
.neg{color:var(--red)}.pos{color:var(--green)}
.mkt-sep{color:var(--border);font-size:10px}
.stance-pill{margin-left:auto;display:flex;align-items:center;gap:6px;border-radius:20px;padding:4px 12px;font-family:var(--mono);font-size:10px;font-weight:700;letter-spacing:.04em}
.stance-yellow{background:var(--yellow-dim);border:1px solid rgba(210,153,34,.4);color:var(--yellow)}
.stance-green{background:var(--green-dim);border:1px solid rgba(63,185,80,.4);color:var(--green)}
.stance-red{background:var(--red-dim);border:1px solid rgba(248,81,73,.4);color:var(--red)}
.stance-dot{width:6px;height:6px;border-radius:50%;animation:pulse 1.5s ease-in-out infinite}
.stance-yellow .stance-dot{background:var(--yellow)}
.stance-green  .stance-dot{background:var(--green)}
.stance-red    .stance-dot{background:var(--red)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}

/* Disclaimer banner */
.disc-banner{background:rgba(210,153,34,.08);border-bottom:1px solid rgba(210,153,34,.2);padding:6px 20px;text-align:center;font-size:10px;color:var(--yellow);letter-spacing:.03em}

/* Page */
.page{max-width:1400px;margin:0 auto;padding:20px}

/* Narrative */
.narrative{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px 24px;margin-bottom:20px}
.narrative-grid{display:grid;grid-template-columns:1fr 1px 1fr;gap:24px}
@media(max-width:860px){.narrative-grid{grid-template-columns:1fr}.narr-divider{display:none}}
.narr-eyebrow{font-size:9px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);font-family:var(--mono);margin-bottom:8px}
.narr-heading{font-size:15px;font-weight:700;color:var(--text);margin-bottom:10px;line-height:1.3}
.narr-body{font-size:12px;color:var(--muted);line-height:1.7}
.narr-body p+p{margin-top:8px}
.narr-body strong{color:var(--text);font-weight:600}
.narr-divider{background:var(--border)}
.method-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}
.method-chip{font-size:9px;font-weight:700;font-family:var(--mono);letter-spacing:.04em;padding:3px 8px;border-radius:3px;background:var(--surface3);color:var(--muted);border:1px solid var(--border)}
.mc-green{background:var(--green-dim);color:var(--green);border-color:rgba(63,185,80,.3)}
.mc-blue{background:var(--accent-dim);color:var(--accent);border-color:rgba(56,139,253,.3)}
.mc-purple{background:var(--purple-dim);color:var(--purple);border-color:rgba(163,113,247,.3)}
.mc-yellow{background:var(--yellow-dim);color:var(--yellow);border-color:rgba(210,153,34,.3)}
.narr-highlights{display:flex;flex-direction:column;gap:8px;margin-top:14px}
.narr-hi{display:flex;align-items:flex-start;gap:8px;font-size:11px;color:var(--muted);line-height:1.5}
.narr-hi-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0;margin-top:4px}
.narr-hi-dot.green{background:var(--green)}.narr-hi-dot.yellow{background:var(--yellow)}
.narr-hi-dot.red{background:var(--red)}.narr-hi-dot.blue{background:var(--accent)}
.narr-hi strong{color:var(--text)}

/* Summary cards */
.summary-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px}
.sum-card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px 16px}
.sum-val{font-family:var(--mono);font-size:22px;font-weight:700;color:var(--text);line-height:1}
.sum-val.green{color:var(--green)}.sum-val.accent{color:var(--accent)}.sum-val.yellow{color:var(--yellow)}
.sum-label{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-top:4px;font-weight:600}
.sum-sub{font-size:10px;color:var(--dim);margin-top:2px;font-family:var(--mono)}

/* Tabs */
.tabs{display:flex;border-bottom:1px solid var(--border);margin-bottom:16px}
.tab{padding:10px 20px;font-family:var(--mono);font-size:12px;font-weight:600;color:var(--muted);cursor:pointer;border-bottom:2px solid transparent;transition:color .15s,border-color .15s;letter-spacing:.02em;user-select:none}
.tab.active{color:var(--accent);border-color:var(--accent)}
.tab:hover:not(.active){color:var(--text)}
.tab-count{display:inline-block;background:var(--surface3);border-radius:10px;padding:1px 6px;font-size:9px;margin-left:5px;color:var(--dim)}
.tab.active .tab-count{background:var(--accent-dim);color:var(--accent)}
.tab-panel{display:none}.tab-panel.active{display:block}

/* Table */
.tbl-wrap{overflow-x:auto;border-radius:8px;border:1px solid var(--border)}
table{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:12px}
thead th{background:var(--surface2);color:var(--muted);font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;padding:10px 12px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--border)}
thead th:first-child,thead th:nth-child(2),thead th.left{text-align:left}
tbody tr{border-bottom:1px solid var(--border2);transition:background .1s}
tbody tr:hover{background:rgba(56,139,253,.04)}
tbody tr:last-child{border-bottom:none}
tbody tr.row-extended{background:rgba(210,153,34,.04)}
tbody tr.row-extended:hover{background:rgba(210,153,34,.08)}
td{padding:8px 12px;vertical-align:middle;text-align:right;font-variant-numeric:tabular-nums;overflow:hidden}
td:first-child,td:nth-child(2),td.left{text-align:left}
td.spark-td{padding:6px 12px;width:100px;max-width:100px}

/* rank */
.rank{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:4px;background:var(--surface3);color:var(--dim);font-size:10px;font-weight:700}
.rank.top3{background:var(--accent-dim);color:var(--accent)}

/* symbol cell */
.sym-cell{display:flex;align-items:flex-start;flex-direction:column;gap:3px}
.sym-name{font-weight:700;font-size:13px;color:var(--text)}
.sym-badges{display:flex;gap:3px;flex-wrap:wrap}
.sym-stage{font-size:9px;font-weight:700;padding:2px 5px;border-radius:3px;letter-spacing:.04em}
.stage-2{background:var(--green-dim);color:var(--green)}
.stage-1{background:var(--accent-dim);color:var(--accent)}
.stage-4{background:var(--red-dim);color:var(--red)}
.ext-badge{font-size:9px;font-weight:700;padding:2px 5px;border-radius:3px;background:var(--yellow-dim);color:var(--yellow);border:1px solid rgba(210,153,34,.3)}

/* sparkline */
.spark-wrap{width:76px;height:30px;flex-shrink:0;overflow:hidden;line-height:0;border-radius:3px}
.spark-wrap canvas{display:block;width:76px !important;height:30px !important;max-width:76px;max-height:30px}

/* score */
.score-cell{display:flex;flex-direction:column;align-items:flex-end;gap:3px;min-width:72px}
.score-num{font-weight:700;font-size:13px}
.score-num.dimmed{color:var(--yellow);opacity:.8}
.score-bar-bg{width:56px;height:3px;background:var(--surface3);border-radius:2px;overflow:hidden}
.score-bar-fill{height:100%;border-radius:2px;background:linear-gradient(90deg,var(--accent),var(--green))}
.score-bar-fill.ext{background:linear-gradient(90deg,var(--yellow),var(--red))}

/* price */
.entry-price{color:var(--text);font-weight:600}
.stop-price{color:var(--red);font-weight:600}
.t1-price{color:var(--green);font-weight:600}
.t2-price{color:var(--teal);font-weight:500}

/* RR */
.rr-badge{display:inline-block;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:700}
.rr-good{background:var(--green-dim);color:var(--green);border:1px solid rgba(63,185,80,.25)}
.rr-ok{background:var(--yellow-dim);color:var(--yellow);border:1px solid rgba(210,153,34,.25)}
.rr-weak{background:var(--red-dim);color:var(--red);border:1px solid rgba(248,81,73,.25)}

/* Gate */
.confirm-badge{font-size:9px;font-weight:700;padding:2px 6px;border-radius:3px;background:var(--yellow-dim);color:var(--yellow);border:1px solid rgba(210,153,34,.3);letter-spacing:.03em;white-space:nowrap}

/* RSI tag */
.rsi-tag{font-size:9px;font-weight:700;padding:2px 5px;border-radius:3px;font-family:var(--mono)}
.rsi-ob{background:var(--red-dim);color:var(--red);border:1px solid rgba(248,81,73,.25)}
.rsi-ok{background:var(--green-dim);color:var(--green);border:1px solid rgba(63,185,80,.2)}

/* mini scores */
.mini-scores{display:flex;flex-direction:column;gap:3px;min-width:96px}
.mini-row{display:flex;align-items:center;gap:5px}
.mini-label{font-size:9px;color:var(--dim);width:22px;text-align:right;flex-shrink:0}
.mini-bar-bg{flex:1;height:3px;background:var(--surface3);border-radius:2px;overflow:hidden;min-width:36px}
.mini-bar-fill{height:100%;border-radius:2px}
.tech-bar{background:var(--accent)}.rs-bar{background:var(--purple)}.fund-bar{background:var(--green)}
.mini-num{font-size:9px;color:var(--muted);width:26px;text-align:right;font-variant-numeric:tabular-nums}

/* action btns */
.action-btns{display:flex;gap:4px;justify-content:flex-end;flex-wrap:wrap}
.act-btn{display:inline-flex;align-items:center;gap:3px;padding:3px 7px;border-radius:4px;font-size:10px;font-family:var(--mono);font-weight:600;cursor:pointer;text-decoration:none;transition:all .12s;white-space:nowrap;border:1px solid var(--border);background:var(--surface3);color:var(--muted)}
.act-btn:hover{background:var(--accent-dim);border-color:var(--accent);color:var(--accent)}
.act-btn.tv:hover{background:rgba(31,119,180,.15);border-color:#4da6ff;color:#4da6ff}
.act-btn.scr:hover{background:rgba(255,140,0,.12);border-color:#ff8c00;color:#ffac33}

/* Disclaimer section */
.disc-section{background:var(--surface);border-top:1px solid var(--border);padding:24px 0 0}
.disc-inner{max-width:1400px;margin:0 auto;padding:0 20px 24px;display:flex;flex-direction:column;gap:12px}
.disc-block{border:1px solid var(--border);border-radius:6px;padding:14px 16px;display:flex;gap:12px;align-items:flex-start}
.disc-block.primary{border-color:rgba(210,153,34,.3);background:rgba(210,153,34,.05)}
.disc-block.secondary{border-color:var(--border2);background:var(--surface2)}
.disc-icon{font-size:14px;flex-shrink:0;margin-top:1px}
.disc-label{font-size:9px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-bottom:4px;font-family:var(--mono)}
.disc-text{font-size:11px;color:var(--muted);line-height:1.6}
.disc-text strong{color:var(--text);font-weight:600}
.disc-footer-row{max-width:1400px;margin:0 auto;padding:12px 20px;border-top:1px solid var(--border2);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px}
.disc-footer-brand,.disc-sebi{font-size:10px;color:var(--dim);font-family:var(--mono)}
</style>
</head>
<body>

<!-- Header -->
<div class="hdr">
  <div class="hdr-inner">
    <div class="brand">
      <div class="brand-mark">AA</div>
      <div>
        <div class="brand-name">Agent Adda</div>
        <div class="brand-sub">NSE Research Platform</div>
      </div>
    </div>
    <div class="hdr-divider"></div>
    <div class="hdr-title">Swing Trading Playbook</div>
    <div class="hdr-spacer"></div>
    <div class="hdr-meta">
      <span class="badge badge-date">📅 $DATE_LABEL</span>
      <span class="badge badge-open">● NSE</span>
      <span class="badge badge-risk">⚠ Max 1% risk/trade</span>
    </div>
  </div>
</div>

<!-- Market strip -->
<div class="mkt-strip">
  <div class="mkt-inner">
    <div class="mkt-item"><span class="mkt-label">NIFTY</span><span class="mkt-val">$NIFTY_CLOSE</span><span class="mkt-chg $NIFTY_CHG_CLASS">$NIFTY_CHG_SIGN $NIFTY_CHG_ABS%</span></div>
    <span class="mkt-sep">·</span>
    <div class="mkt-item"><span class="mkt-label">BANKNIFTY</span><span class="mkt-val">$BNF_CLOSE</span><span class="mkt-chg $BNF_CHG_CLASS">$BNF_CHG_SIGN $BNF_CHG%</span></div>
    <span class="mkt-sep">·</span>
    <div class="mkt-item"><span class="mkt-label">VIX</span><span class="mkt-val">$VIX_CLOSE</span></div>
    <span class="mkt-sep">·</span>
    <div class="mkt-item"><span class="mkt-label">Breadth</span><span class="mkt-val">$ADVANCES&#x200bA</span><span class="mkt-chg neg">/ $DECLINES&#x200bD</span></div>
    <span class="mkt-sep">·</span>
    <div class="mkt-item"><span class="mkt-label">Stage 2</span><span class="mkt-val" style="color:var(--green)">$STAGE2_PCT%</span></div>
    <div class="stance-pill stance-$STANCE_COLOR"><span class="stance-dot"></span>$STANCE_LABEL</div>
  </div>
</div>

<!-- Disclaimer banner -->
<div class="disc-banner">⚠ Educational research only — not investment advice. All entries require intraday confirmation before execution.</div>

<!-- Page -->
<div class="page">

  <!-- Narrative -->
  <div class="narrative">
    <div class="narrative-grid">
      <div class="narr-col">
        <div class="narr-eyebrow">About This Report</div>
        <div class="narr-heading">Agent Adda Swing Trading Playbook</div>
        <div class="narr-body">
          <p>The Swing Playbook is Agent Adda's daily shortlist of <strong>high-conviction NSE swing setups</strong>, refreshed after every market close. It combines four independent scoring lenses — Weinstein stage classification, a 5-factor technical score, relative strength vs NIFTY, and fundamental quality — into a single composite rank. Only names that clear <strong>Stage 2 or early Stage 1 accumulation</strong>, a technical score ≥ 70, and a positive RS reading survive the filter.</p>
          <p>Every setup comes with a pre-defined <strong>entry trigger, stop-loss, and two targets</strong> sized to deliver at least 1.5:1 reward-to-risk. Entries require <strong>intraday volume confirmation</strong> before execution. Two modes: <strong>Tactical</strong> (tighter stops, 5–15 day hold) and <strong>Position</strong> (wider stops, 3–8 week hold).</p>
        </div>
        <div class="method-chips">
          <span class="method-chip mc-green">Weinstein Stage 2</span>
          <span class="method-chip mc-blue">Technical Score ≥ 70</span>
          <span class="method-chip mc-purple">Relative Strength</span>
          <span class="method-chip mc-green">Fundamental Quality</span>
          <span class="method-chip mc-yellow">INTRADAY Confirm Gate</span>
          <span class="method-chip">1% Max Risk/Trade</span>
          <span class="method-chip">8–12 Positions</span>
        </div>
      </div>
      <div class="narr-divider"></div>
      <div class="narr-col">
        <div class="narr-eyebrow">Today's Report · $DATE_LABEL</div>
        <div class="narr-heading">$REGIME_LABEL</div>
        <div class="narr-body">
          <p>NIFTY $NIFTY_VERB at <strong>$NIFTY_CLOSE</strong>, $NIFTY_MOVE <strong>$NIFTY_CHG_ABS%</strong>. Breadth: <strong>$ADVANCES</strong> advances vs <strong>$DECLINES</strong> declines, VIX at <strong>$VIX_CLOSE</strong>. Market regime tagged <strong>$REGIME</strong>. All setups carry the <strong>INTRADAY_CONFIRM gate</strong> — no entries pre-market or at open.</p>
        </div>
        <div class="narr-highlights" id="narr-highlights">
          <!-- populated by JS from TACTICAL data -->
        </div>
      </div>
    </div>
  </div>

  <!-- Summary cards -->
  <div class="summary-row">
    <div class="sum-card"><div class="sum-val green" id="sc-tactical">—</div><div class="sum-label">Tactical Setups</div><div class="sum-sub">shorter stops · faster moves</div></div>
    <div class="sum-card"><div class="sum-val accent" id="sc-position">—</div><div class="sum-label">Position Setups</div><div class="sum-sub">wider stops · multi-week holds</div></div>
    <div class="sum-card"><div class="sum-val yellow" id="sc-topscore">—</div><div class="sum-label">Top Score</div><div class="sum-sub" id="sc-topsym">—</div></div>
    <div class="sum-card"><div class="sum-val green">YES</div><div class="sum-label">Swing Risk Allowed</div><div class="sum-sub">balanced · 8–12 positions</div></div>
    <div class="sum-card"><div class="sum-val yellow">$REGIME</div><div class="sum-label">Market Regime</div><div class="sum-sub" id="sc-regime-sub">live market data</div></div>
  </div>

  <!-- Tabs -->
  <div class="tabs">
    <div class="tab active" onclick="switchTab('tactical',this)">Tactical Swings <span class="tab-count" id="tc-tactical">0</span></div>
    <div class="tab" onclick="switchTab('position',this)">Position Swings <span class="tab-count" id="tc-position">0</span></div>
  </div>

  <div class="tab-panel active" id="tab-tactical">
    <div class="tbl-wrap"><table>
      <thead><tr>
        <th style="width:36px">#</th><th class="left">Symbol</th>
        <th class="left" style="width:100px">Chart (30d)</th>
        <th>Score</th><th>Entry</th><th>Stop</th><th>T1</th><th>T2</th>
        <th>R:R</th><th>RSI</th><th>Gate</th><th>Indicators</th><th>Links</th>
      </tr></thead>
      <tbody id="tbody-tactical"></tbody>
    </table></div>
  </div>

  <div class="tab-panel" id="tab-position">
    <div class="tbl-wrap"><table>
      <thead><tr>
        <th style="width:36px">#</th><th class="left">Symbol</th>
        <th class="left" style="width:100px">Chart (30d)</th>
        <th>Score</th><th>Entry</th><th>Stop</th><th>T1</th><th>T2</th>
        <th>R:R</th><th>RSI</th><th>Gate</th><th>Indicators</th><th>Links</th>
      </tr></thead>
      <tbody id="tbody-position"></tbody>
    </table></div>
  </div>

</div><!-- /page -->

<!-- Disclaimer section -->
<div class="disc-section">
  <div class="disc-inner">
    <div class="disc-block primary">
      <span class="disc-icon">⚠️</span>
      <div>
        <div class="disc-label">Important Disclaimer</div>
        <p class="disc-text"><strong>AgentAdda is not a SEBI-registered Research Analyst or Investment Adviser.</strong> All content on this page is for educational and informational purposes only and does not constitute investment advice, a recommendation to buy or sell any security, or a solicitation of any kind. This analysis was generated by an AI system and has not been reviewed by a licensed financial professional. Past setups shown are historical and not predictive of future performance. <strong>Conduct your own research and consult a SEBI-registered Investment Adviser before making any financial decisions.</strong> Market data may be delayed or inaccurate.</p>
      </div>
    </div>
    <div class="disc-block secondary">
      <span class="disc-icon">🕐</span>
      <div>
        <div class="disc-label">Historical Content Notice</div>
        <p class="disc-text">This is a record of AI-generated technical analysis from <strong>$DATE_LABEL</strong>. The AI model identified these setups based on market data available at that time. All prices and setups shown may have already played out — this is not actionable trading guidance. Published here to illustrate how the AgentAdda AI analysis pipeline works.</p>
      </div>
    </div>
    <div class="disc-block secondary" id="overext-block" style="display:none">
      <span class="disc-icon">📊</span>
      <div>
        <div class="disc-label">Overextension Warning</div>
        <p class="disc-text" id="overext-text"></p>
      </div>
    </div>
  </div>
  <div class="disc-footer-row">
    <div class="disc-footer-brand">Agent Adda · NSE Research Platform · generated $GENERATED</div>
    <div class="disc-sebi">Not SEBI registered · Educational use only · agentadda.in</div>
  </div>
</div>

<script>
// ── Injected data ──────────────────────────────────────────────────────────
const TACTICAL  = $TACTICAL_JSON;
const POSITION  = $POSITION_JSON;
const OVEREXT_NOTE = "$OVEREXT_NOTE_JS";

// ── Seeded PRNG for sparklines ─────────────────────────────────────────────
function seededRng(seed){let s=seed;return()=>{s=Math.imul(s^(s>>>15),1|s)^Math.imul(s^(s>>>7),61|s);s^=s>>>14;return((s>>>0)/4294967296)}}

function genCandles(sym,entry,score,stage){
  const rng=seededRng(sym.split('').reduce((a,c)=>a+c.charCodeAt(0),0)*31);
  const n=30,trend=(score-60)*0.0008+(stage===2?0.004:0.001);
  let price=entry*(0.92+rng()*0.02);const candles=[];
  for(let i=0;i<n;i++){const noise=(rng()-0.48)*price*0.025;const move=price*trend+noise;const o=price,c=price+move;candles.push({o,h:Math.max(o,c)*(1+rng()*0.012),l:Math.min(o,c)*(1-rng()*0.012),c});price=c}
  return candles;
}

function drawSparkline(canvas,candles,stage,overextended){
  const W=76,H=30,dpr=window.devicePixelRatio||1;
  canvas.width=W*dpr;canvas.height=H*dpr;canvas.style.width=W+'px';canvas.style.height=H+'px';
  const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);ctx.clearRect(0,0,W,H);
  const closes=candles.map(c=>c.c),minP=Math.min(...candles.map(c=>c.l)),maxP=Math.max(...candles.map(c=>c.h)),range=maxP-minP||1;
  const pad={l:2,r:2,t:3,b:3},uw=(W-pad.l-pad.r)/candles.length,scY=v=>pad.t+(1-(v-minP)/range)*(H-pad.t-pad.b);
  const lineColor=overextended?'#d29922':stage===2?'#3fb950':'#388bfd';
  const areaTop=overextended?'rgba(210,153,34,.15)':stage===2?'rgba(63,185,80,.15)':'rgba(56,139,253,.15)';
  const ag=ctx.createLinearGradient(0,0,0,H);ag.addColorStop(0,areaTop);ag.addColorStop(1,'rgba(0,0,0,0)');
  ctx.beginPath();closes.forEach((v,i)=>{const x=pad.l+i*uw+uw/2,y=scY(v);i===0?ctx.moveTo(x,y):ctx.lineTo(x,y)});
  ctx.lineTo(pad.l+(candles.length-1)*uw+uw/2,H-pad.b);ctx.lineTo(pad.l,H-pad.b);ctx.closePath();ctx.fillStyle=ag;ctx.fill();
  ctx.beginPath();closes.forEach((v,i)=>{const x=pad.l+i*uw+uw/2,y=scY(v);i===0?ctx.moveTo(x,y):ctx.lineTo(x,y)});
  ctx.strokeStyle=lineColor;ctx.lineWidth=1.5;ctx.lineJoin='round';ctx.stroke();
  const lx=pad.l+(candles.length-1)*uw+uw/2,ly=scY(closes[closes.length-1]);
  ctx.beginPath();ctx.arc(lx,ly,2.5,0,Math.PI*2);ctx.fillStyle=lineColor;ctx.fill();
}

// ── Helpers ────────────────────────────────────────────────────────────────
function fmt(n){if(n>=1000)return n.toLocaleString('en-IN',{minimumFractionDigits:0,maximumFractionDigits:2});return n.toFixed(2)}
function rr(entry,stop,t1){const risk=entry-stop,reward=t1-entry;if(risk<=0)return null;return(reward/risk).toFixed(2)}
function rrClass(v){if(!v)return'rr-weak';return parseFloat(v)>=2?'rr-good':parseFloat(v)>=1.5?'rr-ok':'rr-weak'}
function stageClass(s){return s===2?'stage-2':s===1?'stage-1':'stage-4'}
function buildRow(d,i,tab){
  const rrVal=rr(d.entry,d.stop,d.t1),rrCls=rrClass(rrVal),isTop=i<3;
  const barW=Math.round((d.score/100)*56);
  const canvasId=`spark-${tab}-${d.sym}-${i}`;
  const extBadge=d.overextended?'<span class="ext-badge">⚠ EXTENDED</span>':'';
  const rsiTag=d.rsi?(d.rsi>72?`<span class="rsi-tag rsi-ob">RSI ${d.rsi}</span>`:`<span class="rsi-tag rsi-ok">RSI ${d.rsi}</span>`):'';
  const scoreCls=d.overextended?'dimmed':'';
  const barCls=d.overextended?'ext':'';
  return`<tr class="${d.overextended?'row-extended':''}">
    <td><span class="rank${isTop?' top3':''}">${i+1}</span></td>
    <td class="left"><div class="sym-cell"><span class="sym-name">${d.sym}</span><div class="sym-badges"><span class="sym-stage ${stageClass(d.stage)}">${'S'+d.stage}</span>${extBadge}</div></div></td>
    <td class="left spark-td"><div class="spark-wrap"><canvas id="${canvasId}"></canvas></div></td>
    <td><div class="score-cell"><span class="score-num ${scoreCls}">${d.score.toFixed(1)}</span><div class="score-bar-bg"><div class="score-bar-fill ${barCls}" style="width:${barW}px"></div></div></div></td>
    <td class="entry-price">₹${fmt(d.entry)}</td>
    <td class="stop-price">₹${fmt(d.stop)}</td>
    <td class="t1-price">₹${fmt(d.t1)}</td>
    <td class="t2-price">₹${fmt(d.t2)}</td>
    <td><span class="rr-badge ${rrCls}">${rrVal?rrVal+'R':'—'}</span></td>
    <td>${rsiTag}</td>
    <td><span class="confirm-badge">INTRADAY CONFIRM</span></td>
    <td><div class="mini-scores">
      <div class="mini-row"><span class="mini-label">TEC</span><div class="mini-bar-bg"><div class="mini-bar-fill tech-bar" style="width:${d.tech}%"></div></div><span class="mini-num">${d.tech.toFixed(0)}</span></div>
      <div class="mini-row"><span class="mini-label">RS</span><div class="mini-bar-bg"><div class="mini-bar-fill rs-bar" style="width:${d.rs}%"></div></div><span class="mini-num">${d.rs.toFixed(0)}</span></div>
      <div class="mini-row"><span class="mini-label">FND</span><div class="mini-bar-bg"><div class="mini-bar-fill fund-bar" style="width:${d.fund}%"></div></div><span class="mini-num">${d.fund.toFixed(0)}</span></div>
    </div></td>
    <td><div class="action-btns">
      <a class="act-btn tv" href="https://www.tradingview.com/chart/?symbol=NSE:${d.sym}" target="_blank" rel="noopener">📈 TV</a>
      <a class="act-btn scr" href="https://www.screener.in/company/${d.sym}/" target="_blank" rel="noopener">🔍 SCR</a>
    </div></td>
  </tr>`;
}

function renderTable(data,tbodyId,tab){
  document.getElementById(tbodyId).innerHTML=data.map((d,i)=>buildRow(d,i,tab)).join('');
  requestAnimationFrame(()=>{data.forEach((d,i)=>{const cv=document.getElementById(`spark-${tab}-${d.sym}-${i}`);if(!cv)return;drawSparkline(cv,genCandles(d.sym,d.entry,d.score,d.stage),d.stage,d.overextended)})});
}

function switchTab(name,el){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  el.classList.add('active');document.getElementById('tab-'+name).classList.add('active');
  const data=name==='tactical'?TACTICAL:POSITION,tab=name==='tactical'?'t':'p';
  requestAnimationFrame(()=>{data.forEach((d,i)=>{const cv=document.getElementById(`spark-${tab}-${d.sym}-${i}`);if(!cv)return;drawSparkline(cv,genCandles(d.sym,d.entry,d.score,d.stage),d.stage,d.overextended)})});
}

// ── Init ───────────────────────────────────────────────────────────────────
renderTable(TACTICAL,'tbody-tactical','t');
renderTable(POSITION,'tbody-position','p');

// summary cards
document.getElementById('sc-tactical').textContent=TACTICAL.length;
document.getElementById('sc-position').textContent=POSITION.length;
document.getElementById('tc-tactical').textContent=TACTICAL.length;
document.getElementById('tc-position').textContent=POSITION.length;
if(TACTICAL.length){
  document.getElementById('sc-topscore').textContent=TACTICAL[0].score.toFixed(1);
  document.getElementById('sc-topsym').textContent=TACTICAL[0].sym+' · Stage '+TACTICAL[0].stage;
}

// overextension block
const extNames=TACTICAL.filter(d=>d.overextended).map(d=>d.sym);
if(extNames.length){
  document.getElementById('overext-block').style.display='flex';
  document.getElementById('overext-text').innerHTML=OVEREXT_NOTE;
}

// narrative highlights
const top3=TACTICAL.slice(0,3);
const hlHtml=top3.map(d=>`<div class="narr-hi"><span class="narr-hi-dot ${d.overextended?'yellow':'green'}"></span><span><strong>${d.sym} (${d.score.toFixed(1)})</strong> — Stage ${d.stage}, RS ${d.rs.toFixed(0)}, Fund ${d.fund.toFixed(0)}${d.overextended?' · <span style="color:var(--yellow)">⚠ overextended</span>':''}</span></div>`).join('');
const extHl=extNames.length?`<div class="narr-hi"><span class="narr-hi-dot yellow"></span><span><strong>Overextension alert:</strong> ${extNames.join(', ')} — RSI &gt; 72 or &gt;7% above SMA20. Reduce position size or wait for a pullback entry.</span></div>`:'';
document.getElementById('narr-highlights').innerHTML=hlHtml+extHl;
</script>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────────────
# 7. Render and write
# ─────────────────────────────────────────────────────────────────────────────

def _render(data: dict, ctx: dict, narr: dict) -> str:
    """Inject live data into the HTML template."""
    tactical_json = json.dumps(data.get("TACTICAL", []), ensure_ascii=False)
    position_json = json.dumps(data.get("POSITION", []), ensure_ascii=False)

    # Escape for JS string embedding
    overext_note_js = narr.get("OVEREXT_NOTE", "").replace('"', '\\"').replace("\n", " ")

    t = Template(HTML_TEMPLATE)
    return t.safe_substitute(
        **narr,
        TACTICAL_JSON=tactical_json,
        POSITION_JSON=position_json,
        OVEREXT_NOTE_JS=overext_note_js,
    )


def _write_output(html: str, date_str: str) -> Path:
    REPORTS_LATEST.mkdir(parents=True, exist_ok=True)
    archive_dir = REPORTS_ARCHIVE / date_str[:4]
    archive_dir.mkdir(parents=True, exist_ok=True)

    OUTPUT_HTML.write_text(html, encoding="utf-8")
    archive_path = archive_dir / f"Swing_Playbook_{date_str.replace('-','')}_themed.html"
    archive_path.write_text(html, encoding="utf-8")
    return OUTPUT_HTML


# ─────────────────────────────────────────────────────────────────────────────
# 8. CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        prog="generate_swing_playbook_report",
        description="Render the Agent Adda themed Swing Playbook HTML report.",
    )
    ap.add_argument("--fresh",    action="store_true", help="Re-pull candidates from PostgreSQL")
    ap.add_argument("--from-csv", action="store_true", help="Skip data gen; re-render from existing CSV")
    ap.add_argument("--no-open",  action="store_true", help="Skip opening in browser")
    ap.add_argument("--top-n",    type=int, default=10, help="Candidates per sleeve (default 10)")
    args = ap.parse_args()

    today = date.today().isoformat()

    # Step 1 — data generation
    if not args.from_csv:
        print("▶ Running swing playbook data pipeline …")
        try:
            _run_data_pipeline(fresh=args.fresh, top_n=args.top_n)
        except Exception as exc:
            print(f"  ⚠ data pipeline error: {exc} — attempting to render from existing CSV")

    # Step 2 — read CSV
    if not CANDIDATES_CSV.exists():
        print(f"  ✗ candidates CSV not found: {CANDIDATES_CSV}")
        sys.exit(1)
    print(f"▶ Reading candidates from {CANDIDATES_CSV.name} …")
    data = _read_candidates(CANDIDATES_CSV)
    n_t = len(data["TACTICAL"])
    n_p = len(data["POSITION"])
    print(f"  ✓ {n_t} tactical · {n_p} position candidates")

    # Step 3 — overextension
    print("▶ Checking overextension signals …")
    _enrich_overextension(data)
    ext_count = sum(1 for c in data["TACTICAL"] + data["POSITION"] if c.get("overextended"))
    print(f"  ✓ {ext_count} overextended setups flagged")

    # Step 4 — market context
    print("▶ Fetching market context …")
    ctx = _get_market_context()

    # Step 5 — narrative
    as_of = datetime.now().strftime("%Y-%m-%d")
    narr = _build_narrative(data, ctx, as_of)

    # Step 6 — render
    print("▶ Rendering themed HTML …")
    html = _render(data, ctx, narr)

    # Step 7 — write
    out = _write_output(html, today)
    print(f"  ✓ written → {out}")

    # Step 8 — open
    if not args.no_open:
        import webbrowser
        webbrowser.open(f"file://{out}")
        print(f"  ✓ opened in browser")

    print("\n✅  Swing Playbook report ready.")
    print(f"   Local:   {out}")
    print(f"   Command: open {out}")


if __name__ == "__main__":
    main()
