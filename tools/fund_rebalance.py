#!/usr/bin/env python3
"""
fund_rebalance.py — Agent Adda Monthly Rebalance Engine
========================================================
Answers: "If we rebalanced today, what would change?"

Strategy definitions (exact fund rules):
  SC S2 : Stage 2  +  RS > 70th-pct of ALL SC stocks  +  fund_score ≥ 65
          → rank by TechScore  →  keep top 9

  MC S1 : Stage 2  +  fund_score ≥ 65
          → rank by TechScore  →  keep top 15

  Fundamental gate active from Aug 2026. Hard gate: failing either
  technical or fundamental makes the stock ineligible for selection.

Per-fund output:
  HOLD  — current holding that stays in the new top-N
  DROP  — current holding that would be exited at rebalance:
          [TECH] exited Stage 2
          [RS]   Stage 2 intact but RS ≤ p70  (SC only)
          [FUND] fund_score < 65
          [RANK] passes all gates but displaced by higher-TechScore stock
  ADD   — new entry: in new top-N, not currently held
  WATCH — ranks N+1 to N+5 after both gates (buffer, good alternatives)

Usage:
  python tools/fund_rebalance.py            # terminal output
  python tools/fund_rebalance.py --html     # save HTML to reports/latest/
  python tools/fund_rebalance.py --sc       # SC funds only
  python tools/fund_rebalance.py --mc       # MC funds only


Universe definitions (aligned with backtest_fund_strategies.py):
  SC universe : market_cap_cat = 'SMALL_CAP'  (~268 stocks)
  MC universe : Nifty Midcap 150 membership  (data/index_stock_mapping.csv)

Note on existing holdings: stocks that have graduated from smallcap
to midcap/largecap are correctly shown as GRAD drops — they've outgrown
the universe, not broken Stage 2.
"""

import argparse
import json
import pathlib
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras

ROOT = pathlib.Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.fund_capital_policy import load_capital_policy  # noqa: E402

_POLICY = load_capital_policy()
SC_N           = _POLICY.slots_sc
MC_N           = _POLICY.slots_mc
FUND_SCORE_MIN = _POLICY.fund_score_min
WATCH_N        = _POLICY.watch_n

NIFTY_MC150    = "NIFTY MIDCAP 150"    # MC universe index name


# ── PORTFOLIO DEFINITIONS ─────────────────────────────────────────────────────

AUG_SC = {
    "SYRMA", "CPPLUS", "KARURVYSYA", "SKYGOLD", "RUBICON",
    "GLAND", "RRKABEL", "RAINBOW", "SANSERA",
}

AUG_MC = {
    "OFSS", "COFORGE", "NYKAA", "LLOYDSME", "KALYANKJIL",
    "GODREJPROP", "SONACOMS", "PRESTIGE", "AUROPHARMA", "OBEROIRLTY",
    "TATATECH", "BHARATFORG", "FEDERALBNK", "POLYCAB", "HEROMOTOCO",
}


def load_shadow() -> tuple[set, set]:
    wl = ROOT / "data" / "fund_watchlist.json"
    if not wl.exists():
        return set(), set()
    with open(wl) as f:
        data = json.load(f)
    return set(data.get("smallcap", {}).keys()), set(data.get("midcap", {}).keys())


# ── HELPERS ──────────────────────────────────────────────────────────────────

def fund_grade(score) -> str:
    if score is None: return "?"
    s = float(score)
    if s >= 80: return "A"
    if s >= 65: return "B"
    if s >= 50: return "C"
    return "F"


def fmt(v, dec=1, plus=False, pre="", suf="") -> str:
    if v is None: return "—"
    s = f"{float(v):.{dec}f}"
    if plus and float(v) > 0: s = "+" + s
    return pre + s + suf


# ── DATA ─────────────────────────────────────────────────────────────────────

def compute_rs_p70(conn, cap: str) -> float:
    cur = conn.cursor()
    cur.execute("""
        SELECT COALESCE(CAST(relative_strength AS float), 0)
        FROM scores.stage_snapshots
        WHERE market_cap_cat = %s
          AND snapshot_date = (SELECT MAX(snapshot_date) FROM scores.stage_snapshots)
          AND relative_strength IS NOT NULL
    """, (cap,))
    vals = [r[0] for r in cur.fetchall()]
    return float(np.percentile(vals, 70)) if vals else 0.0


def load_nifty_mc150() -> set:
    """Load Nifty Midcap 150 symbols from index_stock_mapping.csv."""
    mapping = ROOT / "data" / "index_stock_mapping.csv"
    if not mapping.exists():
        return set()
    df = pd.read_csv(mapping)
    return set(df[df["INDEX_NAME"] == NIFTY_MC150]["STOCK_SYMBOL"].tolist())


def fetch_full_universe(conn, cap: str, rs_p70: float,
                        mc150_syms: set | None = None) -> tuple[list[dict], str]:
    """
    Fetch all Stage 2 stocks for the universe, join with fundamentals.
    Returns (universe_rows, snap_date).

    Universe definition:
      SC : market_cap_cat = 'SMALL_CAP'          (per backtest design)
      MC : Nifty Midcap 150 symbol membership    (NSE index, ~150 stocks)

    Each row has: symbol, price, stage, rsi, rs, tech_score,
                  fund_score, fund_grade, eq, sg, fs, ib,
                  rs_pass, fund_pass, both_pass.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Snapshot date
    cur.execute("""
        SELECT MAX(snapshot_date)::text AS dt FROM scores.stage_snapshots
    """)
    snap_date = (cur.fetchone() or {}).get("dt", "unknown")

    # Build the WHERE clause based on universe type
    if cap == "SMALL_CAP":
        # SC: filter by market_cap_cat
        where_cap = "s.market_cap_cat = 'SMALL_CAP'"
        where_params: tuple = ()
    else:
        # MC: filter by Nifty Midcap 150 membership
        if mc150_syms:
            sym_list = "','".join(sorted(mc150_syms))
            where_cap = f"s.symbol IN ('{sym_list}')"
        else:
            where_cap = "s.market_cap_cat = 'MID_CAP'"  # fallback
        where_params = ()

    # All Stage 2 stocks in universe
    cur.execute(f"""
        SELECT
            s.symbol,
            s.market_cap_cat,
            ROUND(s.price::numeric, 2)                                         AS price,
            s.stage,
            ROUND(s.rsi::numeric, 1)                                           AS rsi,
            ROUND(COALESCE(CAST(s.relative_strength AS float), 0)::numeric, 1) AS rs,
            ROUND(s.technical_score::numeric, 1)                               AS tech_score
        FROM scores.stage_snapshots s
        WHERE {where_cap}
          AND s.snapshot_date = (SELECT MAX(snapshot_date) FROM scores.stage_snapshots)
          AND s.stage = 'STAGE_2'
          AND s.technical_score IS NOT NULL
        ORDER BY s.technical_score DESC NULLS LAST
    """)
    s2_rows = {r["symbol"]: dict(r) for r in cur.fetchall()}

    # Fundamental scores for all Stage 2 stocks
    fund_data: dict = {}
    if s2_rows:
        sym_list = "','".join(s2_rows.keys())
        cur.execute(f"""
            SELECT DISTINCT ON (symbol)
                symbol,
                ROUND(enhanced_fund_score, 1)    AS fund_score,
                ROUND(earnings_quality, 1)        AS eq,
                ROUND(sales_growth, 1)            AS sg,
                ROUND(financial_strength, 1)      AS fs,
                ROUND(institutional_backing, 1)   AS ib,
                score_date::text                  AS fund_date
            FROM scores.fundamental_scores
            WHERE symbol IN ('{sym_list}')
            ORDER BY symbol, score_date DESC
        """)
        fund_data = {r["symbol"]: dict(r) for r in cur.fetchall()}

    # Merge
    universe = []
    for sym, snap in s2_rows.items():
        fd = fund_data.get(sym, {})
        fs = float(fd.get("fund_score") or 0)
        rs = float(snap.get("rs") or 0)

        rs_pass   = (rs > rs_p70) if cap == "SMALL_CAP" else True
        fund_pass = fs >= FUND_SCORE_MIN

        universe.append({
            **snap,
            "fund_score":  fs,
            "fund_grade":  fund_grade(fs),
            "eq":          fd.get("eq"),
            "sg":          fd.get("sg"),
            "fs_sub":      fd.get("fs"),
            "ib":          fd.get("ib"),
            "fund_date":   fd.get("fund_date"),
            "rs_pass":     rs_pass,
            "fund_pass":   fund_pass,
            "both_pass":   rs_pass and fund_pass,
        })

    # Sorted by TechScore desc (already ordered from DB, but re-sort for safety)
    universe.sort(key=lambda r: float(r.get("tech_score") or 0), reverse=True)
    return universe, snap_date


def fetch_non_s2_info(conn, symbols: set) -> dict:
    """For holdings not in universe, get their current stage + cap classification."""
    if not symbols:
        return {}
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    sym_list = "','".join(symbols)
    cur.execute(f"""
        SELECT symbol, stage, market_cap_cat,
               ROUND(COALESCE(CAST(relative_strength AS float), 0)::numeric, 1) AS rs,
               ROUND(technical_score::numeric, 1) AS tech_score
        FROM scores.stage_snapshots
        WHERE symbol IN ('{sym_list}')
          AND snapshot_date = (SELECT MAX(snapshot_date) FROM scores.stage_snapshots)
    """)
    return {r["symbol"]: dict(r) for r in cur.fetchall()}


# ── REBALANCE LOGIC ───────────────────────────────────────────────────────────

def classify(holdings: set, universe: list[dict], n: int,
             conn, cap: str, rs_p70: float) -> dict:
    """
    Classify current holdings vs new ideal top-N.
    Returns a dict with holds / drops / adds / watch / top_n / passing.
    """
    u_map     = {r["symbol"]: r for r in universe}
    passing   = [r for r in universe if r["both_pass"]]
    top_n     = passing[:n]
    watch     = passing[n : n + WATCH_N]
    top_n_set = {r["symbol"] for r in top_n}
    u_set     = set(u_map.keys())         # all Stage 2 symbols

    # Holdings not in Stage 2 universe at all
    not_in_s2 = holdings - u_set
    dropped_info = fetch_non_s2_info(conn, not_in_s2) if not_in_s2 else {}

    holds, drops = [], []

    for sym in sorted(holdings):
        if sym not in u_set:
            info     = dropped_info.get(sym, {})
            stage    = info.get("stage", "NOT_IN_DB")
            cur_cap  = info.get("market_cap_cat", "?")
            # Distinguish: still Stage 2 (graduated cap) vs Stage 2 broken vs not in DB
            if stage == "STAGE_2":
                reason = "GRAD"
                detail = f"Stage 2 ✓ but now {cur_cap} — graduated out of {cap.replace('_',' ')} universe"
            elif stage in ("STAGE_1","STAGE_3","STAGE_4"):
                reason = "TECH"
                detail = f"{stage} — exited Stage 2"
            else:
                reason = "TECH"
                detail = "Not in latest snapshot"
            drops.append({
                "symbol":      sym,
                "drop_reason": reason,
                "stage":       stage,
                "detail":      detail,
                "tech_score":  info.get("tech_score"),
                "rs":          info.get("rs"),
                "fund_score":  None,
                "fund_grade":  "?",
                "both_pass":   False,
            })
            continue

        snap = u_map[sym]

        if not snap["rs_pass"]:                        # SC RS gate
            drops.append({
                **snap,
                "drop_reason": "RS",
                "detail":      f"RS {snap['rs']:+.1f} ≤ p70 {rs_p70:.1f}",
            })
        elif not snap["fund_pass"]:                    # fundamental gate
            drops.append({
                **snap,
                "drop_reason": "FUND",
                "detail":      f"Fund {snap['fund_score']:.1f} < {FUND_SCORE_MIN}",
            })
        elif sym in top_n_set:                         # in top-N → HOLD
            holds.append({**snap, "action": "HOLD"})
        else:                                          # passes gates, ranked out
            drops.append({
                **snap,
                "drop_reason": "RANK",
                "detail":      f"TechScore {snap['tech_score']} — displaced by higher-ranked stock",
            })

    # New entries = top-N symbols not currently held
    adds = [r for r in top_n if r["symbol"] not in holdings]

    return {
        "holds":        sorted(holds, key=lambda r: float(r.get("tech_score") or 0), reverse=True),
        "drops":        drops,
        "adds":         adds,
        "watch":        watch,
        "top_n":        top_n,
        "passing":      passing,
        "n_changes":    len(adds),      # drops == adds in count at a full rebalance
    }


# ── TERMINAL OUTPUT ───────────────────────────────────────────────────────────

DROP_LABEL = {
    "TECH": "🔴 TECH",
    "GRAD": "🟣 GRAD",   # graduated to larger cap
    "RS":   "🟠 RS  ",
    "FUND": "🟡 FUND",
    "RANK": "🔵 RANK",
}

def print_fund(name: str, result: dict, rs_p70: float, cap: str) -> None:
    n      = len(result["top_n"])
    W      = 130
    sep    = "─" * W
    print(f"\n{'═'*W}")
    print(f"  {name.upper()}  ·  universe: {len(result['passing'])} passing / strategy selects top {n}")
    print(f"  Filter: {'Stage 2 + RS > ' + str(round(rs_p70,1)) + ' (p70) + fund ≥ ' + str(FUND_SCORE_MIN) if cap == 'SMALL_CAP' else 'Stage 2 + fund ≥ ' + str(FUND_SCORE_MIN)}  ·  Rank by TechScore")
    print(f"{'═'*W}")
    print(f"  {'Symbol':<14} {'Status':<14} {'Stage':<8} {'TechSc':>7} {'RS':>7} {'Fund':>6} {'Gr':>2} {'EQ':>5} {'SG':>5} {'FS':>5}  Detail")
    print(f"  {sep}")

    print(f"\n  ── 🟢 HOLD ({len(result['holds'])}) ──")
    for r in result["holds"]:
        print(f"  {r['symbol']:<14} {'HOLD':<14} {'S2':<8} "
              f"{fmt(r.get('tech_score')):>7} {fmt(r.get('rs'), plus=True):>7} "
              f"{fmt(r.get('fund_score')):>6} {r.get('fund_grade','?'):>2} "
              f"{fmt(r.get('eq')):>5} {fmt(r.get('sg')):>5} {fmt(r.get('fs_sub')):>5}")

    print(f"\n  ── 🔵 ADD ({len(result['adds'])}) — new entries ──")
    for r in result["adds"]:
        rank = result["top_n"].index(r) + 1
        print(f"  {r['symbol']:<14} {'ADD #'+str(rank):<14} {'S2':<8} "
              f"{fmt(r.get('tech_score')):>7} {fmt(r.get('rs'), plus=True):>7} "
              f"{fmt(r.get('fund_score')):>6} {r.get('fund_grade','?'):>2} "
              f"{fmt(r.get('eq')):>5} {fmt(r.get('sg')):>5} {fmt(r.get('fs_sub')):>5}")

    print(f"\n  ── 🔻 DROP ({len(result['drops'])}) ──")
    for r in result["drops"]:
        label = DROP_LABEL.get(r["drop_reason"], r["drop_reason"])
        print(f"  {r['symbol']:<14} {label:<14} {(r.get('stage') or '?'):<8} "
              f"{fmt(r.get('tech_score')):>7} {fmt(r.get('rs'), plus=True):>7} "
              f"{fmt(r.get('fund_score')):>6} {r.get('fund_grade','?'):>2} "
              f"{fmt(r.get('eq')):>5} {fmt(r.get('sg')):>5} {fmt(r.get('fs_sub')):>5}  {r.get('detail','')}")

    if result["watch"]:
        print(f"\n  ── 👁 WATCH — next {WATCH_N} after top-{n} ──")
        for i, r in enumerate(result["watch"], start=n+1):
            print(f"  {r['symbol']:<14} {'#'+str(i):<14} {'S2':<8} "
                  f"{fmt(r.get('tech_score')):>7} {fmt(r.get('rs'), plus=True):>7} "
                  f"{fmt(r.get('fund_score')):>6} {r.get('fund_grade','?'):>2} "
                  f"{fmt(r.get('eq')):>5} {fmt(r.get('sg')):>5} {fmt(r.get('fs_sub')):>5}")

    print(f"\n  {sep}")
    print(f"  Changes at rebalance: {len(result['adds'])} in / {len(result['drops'])} out  "
          f"| Holds: {len(result['holds'])} / {n}")


# ── HTML OUTPUT ───────────────────────────────────────────────────────────────

def _grade_cls(g: str) -> str:
    return {"A":"ga","B":"gb","C":"gc","F":"gf"}.get(g, "gna")

def _drop_cls(reason: str) -> str:
    return {"TECH":"dt","RS":"dr","FUND":"df","RANK":"dk"}.get(reason, "")


def build_fund_html(name: str, result: dict, rs_p70: float, cap: str, n: int) -> str:
    def row_hold(r):
        ts = fmt(r.get("tech_score"))
        rs = fmt(r.get("rs"), plus=True)
        fs = fmt(r.get("fund_score"))
        grade = r.get("fund_grade", "?")
        return f"""<tr class="r-hold">
  <td class="sym">{r['symbol']}</td>
  <td><span class="badge b-hold">HOLD</span></td>
  <td><span class="s2">S2</span></td>
  <td class="n">{ts}</td><td class="n">{rs}</td>
  <td class="n"><span class="{_grade_cls(grade)}">{fs}</span></td>
  <td class="n">{fmt(r.get('eq'))}</td><td class="n">{fmt(r.get('sg'))}</td>
  <td class="n">{fmt(r.get('fs_sub'))}</td>
  <td class="detail"></td>
</tr>"""

    def row_add(r, rank):
        ts = fmt(r.get("tech_score"))
        rs = fmt(r.get("rs"), plus=True)
        fs = fmt(r.get("fund_score"))
        grade = r.get("fund_grade", "?")
        return f"""<tr class="r-add">
  <td class="sym">{r['symbol']}</td>
  <td><span class="badge b-add">ADD #{rank}</span></td>
  <td><span class="s2">S2</span></td>
  <td class="n">{ts}</td><td class="n">{rs}</td>
  <td class="n"><span class="{_grade_cls(grade)}">{fs}</span></td>
  <td class="n">{fmt(r.get('eq'))}</td><td class="n">{fmt(r.get('sg'))}</td>
  <td class="n">{fmt(r.get('fs_sub'))}</td>
  <td class="detail">→ New position</td>
</tr>"""

    def row_drop(r):
        reason = r.get("drop_reason", "")
        label_map  = {"TECH":"🔴 TECH","GRAD":"🟣 GRAD","RS":"🟠 RS","FUND":"🟡 FUND","RANK":"🔵 RANK"}
        badge_map  = {"TECH":"b-tech","GRAD":"b-grad","RS":"b-rs","FUND":"b-fund","RANK":"b-rank"}
        label = label_map.get(reason, reason)
        bcls  = badge_map.get(reason, "")
        stage = (r.get("stage") or "—").replace("STAGE_", "S")
        ts = fmt(r.get("tech_score"))
        rs = fmt(r.get("rs"), plus=True)
        fs = fmt(r.get("fund_score"))
        grade = r.get("fund_grade", "?")
        return f"""<tr class="r-drop">
  <td class="sym">{r['symbol']}</td>
  <td><span class="badge {bcls}">{label}</span></td>
  <td><span class="stage-{stage.lower().replace(' ','')}">{stage}</span></td>
  <td class="n">{ts}</td><td class="n">{rs}</td>
  <td class="n"><span class="{_grade_cls(grade)}">{fs}</span></td>
  <td class="n">{fmt(r.get('eq'))}</td><td class="n">{fmt(r.get('sg'))}</td>
  <td class="n">{fmt(r.get('fs_sub'))}</td>
  <td class="detail muted">{r.get('detail','')}</td>
</tr>"""

    def row_watch(r, rank):
        ts = fmt(r.get("tech_score"))
        rs = fmt(r.get("rs"), plus=True)
        fs = fmt(r.get("fund_score"))
        grade = r.get("fund_grade", "?")
        return f"""<tr class="r-watch">
  <td class="sym">{r['symbol']}</td>
  <td><span class="badge b-watch">WATCH #{rank}</span></td>
  <td><span class="s2">S2</span></td>
  <td class="n">{ts}</td><td class="n">{rs}</td>
  <td class="n"><span class="{_grade_cls(grade)}">{fs}</span></td>
  <td class="n">{fmt(r.get('eq'))}</td><td class="n">{fmt(r.get('sg'))}</td>
  <td class="n">{fmt(r.get('fs_sub'))}</td>
  <td class="detail muted">Buffer — available if needed</td>
</tr>"""

    # Build rows: HOLD → ADD → DROP (with sep) → WATCH
    body = ""
    if result["holds"]:
        body += f'<tr class="grp-sep sep-hold"><td colspan="10">🟢 Hold ({len(result["holds"])}) — stays in portfolio</td></tr>'
        for r in result["holds"]:
            body += row_hold(r)

    if result["adds"]:
        body += f'<tr class="grp-sep sep-add"><td colspan="10">🔵 Add ({len(result["adds"])}) — new positions at rebalance</td></tr>'
        for r in result["adds"]:
            body += row_add(r, result["top_n"].index(r) + 1)

    if result["drops"]:
        # Group by reason
        for reason, label in [
            ("TECH", "🔴 Tech exit — Stage 2 broken"),
            ("GRAD", "🟣 Graduated — outgrown this cap universe (positive!)"),
            ("RS",   "🟠 RS exit — below p70 threshold"),
            ("FUND", "🟡 Fund exit — score below 65"),
            ("RANK", "🔵 Ranked out — displaced by higher-TechScore stock"),
        ]:
            sub = [r for r in result["drops"] if r.get("drop_reason") == reason]
            if sub:
                body += f'<tr class="grp-sep sep-drop"><td colspan="10">DROP [{reason}]: {label} ({len(sub)})</td></tr>'
                for r in sub:
                    body += row_drop(r)

    if result["watch"]:
        body += f'<tr class="grp-sep sep-watch"><td colspan="10">👁 Watch — next {WATCH_N} after top-{n} (both gates pass)</td></tr>'
        for i, r in enumerate(result["watch"], start=n+1):
            body += row_watch(r, i)

    filter_str = (f"Stage 2 + RS &gt; {rs_p70:.1f} (p70) + fund ≥ {FUND_SCORE_MIN}"
                  if cap == "SMALL_CAP"
                  else f"Stage 2 + fund ≥ {FUND_SCORE_MIN}")
    changes = len(result["adds"])

    return f"""<section class="fund-section">
<div class="fund-header">
  <h2>{name}</h2>
  <div class="fund-meta">
    <span class="fm-tag">{filter_str}</span>
    <span class="fm-tag">Top {n} by TechScore</span>
    <span class="fm-tag">{len(result['passing'])} stocks pass both gates</span>
  </div>
</div>
<div class="change-summary {'cs-changes' if changes else 'cs-clean'}">
  {'⚠ ' + str(changes) + ' change' + ('s' if changes != 1 else '') + ' at next rebalance — ' + str(len(result["holds"])) + ' holds + ' + str(len(result["adds"])) + ' new in / ' + str(len(result["drops"])) + ' out'
   if changes else
   '✓ No changes — current holdings match new top-' + str(n)}
</div>
<div class="tbl-wrap"><table>
  <thead><tr>
    <th>Symbol</th><th>Action</th><th>Stage</th>
    <th class="n">TechSc</th><th class="n">RS</th>
    <th class="n">FScore</th>
    <th class="n" title="Earnings Quality">EQ</th>
    <th class="n" title="Sales Growth">SG</th>
    <th class="n" title="Financial Strength">FS</th>
    <th>Reason</th>
  </tr></thead>
  <tbody>{body}</tbody>
</table></div>
</section>"""


def build_html(results: list[dict], run_date: str, snap_date: str,
               rs_p70_sc: float) -> str:

    total_changes = sum(r["result"]["n_changes"] for r in results)
    sections_html = "\n".join(
        build_fund_html(r["name"], r["result"], r["rs_p70"], r["cap"], r["n"])
        for r in results
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fund Rebalance — {run_date}</title>
<style>
:root{{
  --bg:#f5f7fa; --surface:#fff; --surface2:#eef1f5;
  --border:#d0d7de; --text:#1a2233; --text2:#57606a; --text3:#8b949e;
  --hold:#1a7f37; --add:#0969da; --drop:#cf222e; --rank:#6366f1;
  --fund:#d97706; --watch:#6b7280;
  --shadow:0 1px 3px rgba(0,0,0,.06);
}}
@media(prefers-color-scheme:dark){{:root:not([data-theme="light"]){{
  --bg:#0d1117; --surface:#161b22; --surface2:#1c2128;
  --border:#30363d; --text:#e6edf3; --text2:#8b949e; --text3:#6e7681;
  --hold:#3fb950; --add:#58a6ff; --drop:#f85149; --rank:#a5b4fc;
  --fund:#fbbf24; --watch:#9ca3af;
}}}}
:root[data-theme="dark"]{{
  --bg:#0d1117; --surface:#161b22; --surface2:#1c2128;
  --border:#30363d; --text:#e6edf3; --text2:#8b949e; --text3:#6e7681;
  --hold:#3fb950; --add:#58a6ff; --drop:#f85149; --rank:#a5b4fc;
  --fund:#fbbf24; --watch:#9ca3af;
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
  font-size:13px;background:var(--bg);color:var(--text);padding:20px 24px;max-width:1280px;margin:0 auto}}

h1{{font-size:18px;font-weight:700;margin-bottom:4px}}
.page-sub{{font-size:11px;color:var(--text2);margin-bottom:16px}}

.summary-bar{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}}
.sb{{background:var(--surface);border:1px solid var(--border);border-radius:8px;
  padding:10px 16px;box-shadow:var(--shadow)}}
.sb-label{{font-size:10px;text-transform:uppercase;letter-spacing:.4px;color:var(--text2)}}
.sb-val{{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.2}}

.fund-section{{background:var(--surface);border:1px solid var(--border);
  border-radius:10px;box-shadow:var(--shadow);margin-bottom:20px;overflow:hidden}}
.fund-header{{padding:12px 16px 8px;border-bottom:1px solid var(--border)}}
.fund-header h2{{font-size:14px;font-weight:700}}
.fund-meta{{display:flex;gap:8px;flex-wrap:wrap;margin-top:5px}}
.fm-tag{{font-size:10px;color:var(--text2);background:var(--surface2);
  border:1px solid var(--border);border-radius:4px;padding:2px 7px}}
.change-summary{{padding:8px 16px;font-size:12px;font-weight:600}}
.cs-changes{{background:rgba(207,34,46,.06);color:var(--drop);border-bottom:1px solid rgba(207,34,46,.2)}}
.cs-clean{{background:rgba(26,127,55,.06);color:var(--hold);border-bottom:1px solid rgba(26,127,55,.2)}}

.tbl-wrap{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}}
thead th{{background:var(--surface2);color:var(--text2);font-size:10px;font-weight:700;
  text-transform:uppercase;letter-spacing:.4px;padding:7px 10px;
  border-bottom:1px solid var(--border);white-space:nowrap;text-align:left}}
thead th.n{{text-align:right}}
tbody td{{padding:6px 10px;border-bottom:1px solid var(--border);font-size:12px;vertical-align:middle;white-space:nowrap}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}}
td.detail{{min-width:200px;white-space:normal;font-size:11px}}
td.muted{{color:var(--text2)}}
.sym{{font-weight:600}}
tbody tr:hover td{{background:var(--surface2)}}

.grp-sep td{{padding:6px 10px;font-size:11px;font-weight:600;
  border-top:2px solid var(--border);border-bottom:1px solid var(--border)}}
.sep-hold td{{color:var(--hold);background:rgba(26,127,55,.05)}}
.sep-add td{{color:var(--add);background:rgba(9,105,218,.05)}}
.sep-drop td{{color:var(--drop);background:rgba(207,34,46,.05)}}
.sep-watch td{{color:var(--watch);background:var(--surface2)}}

.r-hold td{{background:rgba(26,127,55,.02)}}
.r-add td{{background:rgba(9,105,218,.04)}}
.r-drop td{{background:rgba(207,34,46,.03)}}
.r-watch td{{opacity:.75}}

/* badges */
.badge{{display:inline-block;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:700}}
.b-hold{{background:rgba(26,127,55,.12);color:var(--hold)}}
.b-add{{background:rgba(9,105,218,.12);color:var(--add)}}
.b-tech{{background:rgba(207,34,46,.15);color:var(--drop)}}
.b-grad{{background:rgba(139,92,246,.15);color:#7c3aed}}
.b-rs{{background:rgba(217,119,6,.15);color:#b35c00}}
.b-fund{{background:rgba(234,179,8,.15);color:#92400e}}
.b-rank{{background:rgba(99,102,241,.15);color:var(--rank)}}
.b-watch{{background:var(--surface2);color:var(--watch);border:1px solid var(--border)}}

/* stages */
.s2{{display:inline-block;padding:1px 5px;border-radius:3px;font-size:10px;font-weight:600;
  color:var(--hold);background:rgba(26,127,55,.1)}}
.stage-s1{{display:inline-block;padding:1px 5px;border-radius:3px;font-size:10px;font-weight:600;
  color:var(--add);background:rgba(9,105,218,.1)}}
.stage-s3,.stage-s4{{display:inline-block;padding:1px 5px;border-radius:3px;font-size:10px;font-weight:600;
  color:var(--drop);background:rgba(207,34,46,.1)}}
.stage-not_in_db{{display:inline-block;padding:1px 5px;border-radius:3px;font-size:10px;
  color:var(--text3);background:var(--surface2)}}

/* fund grade colours */
.ga{{color:var(--hold);font-weight:700}}
.gb{{color:var(--add);font-weight:600}}
.gc{{color:#b35c00;font-weight:600}}
.gf{{color:var(--drop);font-weight:700}}
.gna{{color:var(--text3)}}

.footer{{font-size:11px;color:var(--text3);margin-top:12px;text-align:right}}
</style></head><body>

<h1>Monthly Rebalance View</h1>
<div class="page-sub">
  Run date: {run_date}  ·  Snapshot: {snap_date}  ·
  SC p70 RS threshold: {rs_p70_sc:.1f}  ·  Fundamental gate: fund_score ≥ {FUND_SCORE_MIN}  ·
  Rank metric: TechScore
</div>

<div class="summary-bar">
  <div class="sb"><div class="sb-label">Total changes</div>
    <div class="sb-val" style="color:{'var(--drop)' if total_changes else 'var(--hold)'}">{total_changes}</div></div>
  {''.join(f"""<div class="sb"><div class="sb-label">{r['name']}</div>
    <div class="sb-val">{r['result']['n_changes']} swap{'s' if r['result']['n_changes']!=1 else ''}</div></div>"""
    for r in results)}
</div>

{sections_html}

<div class="footer">Agent Adda · scores.stage_snapshots + scores.fundamental_scores · {run_date}</div>
</body></html>"""


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fund Rebalance Engine")
    parser.add_argument("--html",  action="store_true", help="Save HTML to reports/latest/")
    parser.add_argument("--sc",    action="store_true", help="SC funds only")
    parser.add_argument("--mc",    action="store_true", help="MC funds only")
    args = parser.parse_args()

    run_date   = str(date.today())
    shadow_sc, shadow_mc = load_shadow()
    mc150_syms = load_nifty_mc150()
    print(f"Nifty Midcap 150 loaded: {len(mc150_syms)} symbols", file=sys.stderr)

    conn = psycopg2.connect(dbname="nse_market", user="pgorai", host="localhost")

    rs_p70_sc = compute_rs_p70(conn, "SMALL_CAP")
    print(f"SC RS p70 = {rs_p70_sc:.1f}", file=sys.stderr)

    # ── Fetch universes ──
    sc_universe, snap_date = fetch_full_universe(conn, "SMALL_CAP", rs_p70_sc)
    mc_universe, _         = fetch_full_universe(conn, "MID_CAP",   0.0, mc150_syms=mc150_syms)

    runs = []

    if not args.mc:
        aug_sc_result  = classify(AUG_SC,    sc_universe, SC_N, conn, "SMALL_CAP", rs_p70_sc)
        shadow_sc_result = classify(shadow_sc, sc_universe, SC_N, conn, "SMALL_CAP", rs_p70_sc) if shadow_sc else None
        runs.append({"name":"Aug SC  (S2 strategy)",  "result": aug_sc_result,    "cap":"SMALL_CAP","n":SC_N,"rs_p70":rs_p70_sc})
        if shadow_sc_result:
            runs.append({"name":"Shadow SC (S2 strategy)", "result": shadow_sc_result, "cap":"SMALL_CAP","n":SC_N,"rs_p70":rs_p70_sc})

    if not args.sc:
        aug_mc_result    = classify(AUG_MC,    mc_universe, MC_N, conn, "MID_CAP", 0.0)
        shadow_mc_result = classify(shadow_mc, mc_universe, MC_N, conn, "MID_CAP", 0.0) if shadow_mc else None
        runs.append({"name":"Aug MC  (S1 strategy)",  "result": aug_mc_result,    "cap":"MID_CAP","n":MC_N,"rs_p70":0.0})
        if shadow_mc_result:
            runs.append({"name":"Shadow MC (S1 strategy)", "result": shadow_mc_result, "cap":"MID_CAP","n":MC_N,"rs_p70":0.0})

    conn.close()

    if args.html:
        html = build_html(runs, run_date, snap_date, rs_p70_sc)
        out  = ROOT / "reports" / "latest" / f"fund_rebalance_{run_date.replace('-','')}.html"
        out.write_text(html)
        print(f"Saved: {out}", file=sys.stderr)

    for r in runs:
        print_fund(r["name"], r["result"], r["rs_p70"], r["cap"])

    # Rebalance summary
    total = sum(r["result"]["n_changes"] for r in runs)
    print(f"\n{'═'*60}")
    print(f"  REBALANCE SUMMARY  ·  {run_date}")
    for r in runs:
        nc = r["result"]["n_changes"]
        sym_in  = ", ".join(a["symbol"] for a in r["result"]["adds"])  or "—"
        sym_out = ", ".join(d["symbol"] for d in r["result"]["drops"]) or "—"
        print(f"  {r['name']:<28}  {nc} change{'s' if nc!=1 else ''}")
        if nc:
            print(f"    IN : {sym_in}")
            print(f"    OUT: {sym_out}")
    print(f"  Total changes: {total}")
    print(f"{'═'*60}")


if __name__ == "__main__":
    main()
