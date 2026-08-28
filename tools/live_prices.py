#!/usr/bin/env python3
"""
live_prices.py — Fetch live NSE prices via yfinance (5-min candles)
and write a self-contained HTML dashboard to reports/latest/live_prices.html.

Usage:
    python tools/live_prices.py              # generate + open
    python tools/live_prices.py --no-open    # generate only
    python tools/live_prices.py --symbols RELIANCE,INFY,TCS
    python tools/live_prices.py --watchlist portfolio   # portfolio holdings

Source: yfinance (~15-min delayed during market hours; EOD after close)
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT   = Path(__file__).parent.parent
LATEST = ROOT / "reports" / "latest"
OUT    = LATEST / "live_prices.html"

# ── default watchlists ─────────────────────────────────────────────────────────

WATCHLISTS: dict[str, list[tuple[str, str]]] = {
    "nifty50": [
        ("RELIANCE",   "Reliance"),
        ("HDFCBANK",   "HDFC Bank"),
        ("TCS",        "TCS"),
        ("INFY",       "Infosys"),
        ("ICICIBANK",  "ICICI Bank"),
        ("BHARTIARTL", "Airtel"),
        ("SBIN",       "SBI"),
        ("LT",         "L&T"),
        ("KOTAKBANK",  "Kotak Bank"),
        ("AXISBANK",   "Axis Bank"),
        ("WIPRO",      "Wipro"),
        ("HCLTECH",    "HCL Tech"),
        ("BAJAJ-AUTO", "Bajaj Auto"),
        ("MARUTI",     "Maruti"),
        ("SUNPHARMA",  "Sun Pharma"),
        ("ONGC",       "ONGC"),
        ("NTPC",       "NTPC"),
        ("POWERGRID",  "Power Grid"),
        ("BAJFINANCE",  "Bajaj Finance"),
        ("ULTRACEMCO", "UltraTech"),
    ],
    "it": [
        ("TCS",        "TCS"),
        ("INFY",       "Infosys"),
        ("WIPRO",      "Wipro"),
        ("HCLTECH",    "HCL Tech"),
        ("LTIM",       "LTI Mindtree"),
        ("TECHM",      "Tech Mahindra"),
        ("MPHASIS",    "Mphasis"),
        ("COFORGE",    "Coforge"),
        ("PERSISTENT", "Persistent"),
        ("KPIT",       "KPIT"),
    ],
    "banks": [
        ("HDFCBANK",  "HDFC Bank"),
        ("ICICIBANK", "ICICI Bank"),
        ("SBIN",      "SBI"),
        ("KOTAKBANK", "Kotak"),
        ("AXISBANK",  "Axis"),
        ("INDUSINDBK","IndusInd"),
        ("BANKBARODA","BoB"),
        ("PNB",       "PNB"),
        ("FEDERALBNK","Federal"),
        ("IDFCFIRSTB","IDFC First"),
    ],
}


def _portfolio_watchlist() -> list[tuple[str, str]]:
    """Load the active Agent Adda fund holdings as a bounded watchlist."""
    try:
        with (ROOT / "data" / "fund_holdings.json").open(encoding="utf-8") as f:
            h = json.load(f)
        symbols = list(h.get("smallcap", {})) + list(h.get("midcap", {}))
        return [(s, s) for s in symbols]
    except Exception:
        return []


WATCHLISTS["portfolio"] = _portfolio_watchlist()


# ── data fetching ──────────────────────────────────────────────────────────────

def _fetch_one(sym_name: tuple[str, str]) -> tuple[str, dict | None]:
    sym, name = sym_name
    try:
        import warnings
        warnings.filterwarnings("ignore")
        import yfinance as yf

        ticker   = yf.Ticker(f"{sym}.NS")
        df5      = ticker.history(period="1d",   interval="5m")
        dfd      = ticker.history(period="5d",   interval="1d")

        if df5 is None or df5.empty or dfd is None or len(dfd) < 2:
            return sym, None

        last  = df5.iloc[-1]
        prev  = float(dfd.iloc[-2]["Close"])
        ltp   = float(last["Close"])
        hi    = float(df5["High"].max())
        lo    = float(df5["Low"].min())
        vol   = int(df5["Volume"].sum())
        op    = float(df5.iloc[0]["Open"])
        ts    = str(last.name)[11:16]

        # intraday position: 0 (at lo) → 1 (at hi)
        rng  = hi - lo
        ipos = (ltp - lo) / rng if rng > 0 else 0.5

        return sym, {
            "name":  name,
            "ltp":   round(ltp, 2),
            "prev":  round(prev, 2),
            "open":  round(op,  2),
            "hi":    round(hi,  2),
            "lo":    round(lo,  2),
            "vol":   vol,
            "chg":   round((ltp - prev) / prev * 100, 2),
            "chg_o": round((ltp - op)   / op   * 100, 2),
            "ipos":  round(ipos, 3),
            "ts":    ts,
        }
    except Exception:
        return sym, None


def fetch_all(pairs: list[tuple[str, str]], workers: int = 10) -> dict[str, dict]:
    results: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for sym, data in ex.map(_fetch_one, pairs):
            if data:
                results[sym] = data
    return results


# ── HTML builder ───────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Live Prices</title>
<style>
:root {
  --page:    #f2f2ef; --surface: #fafaf9; --surface-2: #ededea;
  --border:  #e0dfdb;
  --ink-1:   #0f1117; --ink-2: #52514e; --ink-3: #969690;
  --g:       #006300; --r: #c0392b;
  --g-bar:   #0ca30c; --r-bar: #d03b3b;
  --g-wash:  rgba(12,163,12,.07); --r-wash: rgba(208,59,59,.07);
}
@media (prefers-color-scheme:dark) { :root:not([data-theme="light"]) {
  --page:#111420; --surface:#191d29; --surface-2:#1f2437;
  --border:#262d42; --ink-1:#e6e8ee; --ink-2:#9499a8; --ink-3:#515870;
  --g:#0ca30c; --r:#e66767; --g-bar:#0ca30c; --r-bar:#d03b3b;
  --g-wash:rgba(12,163,12,.09); --r-wash:rgba(208,59,59,.09);
}}
:root[data-theme="dark"] {
  --page:#111420; --surface:#191d29; --surface-2:#1f2437;
  --border:#262d42; --ink-1:#e6e8ee; --ink-2:#9499a8; --ink-3:#515870;
  --g:#0ca30c; --r:#e66767; --g-bar:#0ca30c; --r-bar:#d03b3b;
  --g-wash:rgba(12,163,12,.09); --r-wash:rgba(208,59,59,.09);
}
*,*::before,*::after { box-sizing:border-box; margin:0; padding:0; }
body { background:var(--page); color:var(--ink-1); font-family:system-ui,-apple-system,"Segoe UI",sans-serif; font-size:13px; line-height:1.5; padding:24px 18px 48px; }
.wrap { max-width:980px; margin:0 auto; }

/* header */
.hd { display:flex; align-items:flex-end; justify-content:space-between; margin-bottom:20px; flex-wrap:wrap; gap:10px; }
.hd-l .eyebrow { font-size:10px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; color:var(--ink-3); margin-bottom:4px; }
.hd-l h1 { font-size:20px; font-weight:700; letter-spacing:-.4px; }
.hd-r { text-align:right; }
.badge { display:inline-block; background:var(--surface-2); border:1px solid var(--border); border-radius:4px; padding:3px 9px; font-size:11px; color:var(--ink-3); font-variant-numeric:tabular-nums; }
.badge .ts { color:var(--ink-2); font-weight:600; }
.note { font-size:10.5px; color:var(--ink-3); margin-top:3px; }

/* table */
.tbl-wrap { overflow-x:auto; -webkit-overflow-scrolling:touch; }
table { width:100%; border-collapse:collapse; background:var(--surface); border:1px solid var(--border); border-radius:6px; overflow:hidden; font-variant-numeric:tabular-nums; }
thead { background:var(--surface-2); }
th { font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.08em; color:var(--ink-3); padding:9px 12px; text-align:right; border-bottom:1px solid var(--border); white-space:nowrap; }
th:first-child { text-align:left; }
td { padding:8px 12px; text-align:right; border-bottom:1px solid var(--border); color:var(--ink-2); }
td:first-child { text-align:left; font-weight:600; color:var(--ink-1); letter-spacing:-.01em; }
tr:last-child td { border-bottom:none; }
tr:hover td { background:var(--surface-2); }
.up   { color:var(--g); font-weight:700; }
.down { color:var(--r); font-weight:700; }
.muted { color:var(--ink-3); }

/* intraday position bar */
.ibar-track { width:80px; height:8px; background:var(--surface-2); border-radius:4px; display:inline-block; vertical-align:middle; position:relative; border:1px solid var(--border); }
.ibar-fill  { position:absolute; left:0; top:0; height:100%; border-radius:4px; }
.ibar-dot   { position:absolute; top:50%; width:8px; height:8px; border-radius:50%; transform:translate(-50%,-50%); border:2px solid var(--surface); }

/* section label */
.section-hd { font-size:10px; font-weight:700; letter-spacing:.1em; text-transform:uppercase; color:var(--ink-3); margin:22px 0 8px; }
.section-hd:first-child { margin-top:0; }

/* summary strip */
.summary { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:16px; }
.pill { background:var(--surface); border:1px solid var(--border); border-radius:5px; padding:8px 14px; }
.pill-label { font-size:10px; color:var(--ink-3); letter-spacing:.05em; text-transform:uppercase; margin-bottom:2px; }
.pill-val { font-size:16px; font-weight:700; letter-spacing:-.3px; }
.pill-val.up   { color:var(--g); }
.pill-val.down { color:var(--r); }
.pill-val.neu  { color:var(--ink-2); }
</style>
</head><body>
<div class="wrap">

<div class="hd">
  <div class="hd-l">
    <div class="eyebrow">NSE Live Prices</div>
    <h1>Market Snapshot</h1>
  </div>
  <div class="hd-r">
    <div class="badge">Last refreshed <span class="ts">REFRESH_TS</span></div>
  <div class="note">SOURCE_NOTE · Re-run script to refresh</div>
  </div>
</div>

SUMMARY_STRIP

SECTIONS_HTML

</div>
</body></html>
"""

ROW_TEMPLATE = """<tr>
  <td title="{sym}">{name}</td>
  <td>₹{ltp:,.2f}</td>
  <td class="{chg_cls}">{chg_sign}{chg:.2f}%</td>
  <td class="{chg_o_cls}">{chg_o_sign}{chg_o:.2f}%</td>
  <td>₹{hi:,.2f}</td>
  <td>₹{lo:,.2f}</td>
  <td class="muted">{vol_fmt}</td>
  <td>
    <span class="ibar-track">
      <span class="ibar-fill" style="width:{ipos_pct:.0f}%;background:{ibar_color}"></span>
      <span class="ibar-dot" style="left:{ipos_pct:.0f}%;background:{ibar_color}"></span>
    </span>
  </td>
  <td class="muted">{ts}</td>
</tr>"""

TABLE_HEADER = """<div class="tbl-wrap"><table>
<thead><tr>
  <th>Symbol</th>
  <th>LTP</th>
  <th>Chg (prev)</th>
  <th>Chg (open)</th>
  <th>Day Hi</th>
  <th>Day Lo</th>
  <th>Volume</th>
  <th style="min-width:96px">Day Range</th>
  <th>As of</th>
</tr></thead><tbody>"""

TABLE_FOOTER = "</tbody></table></div>"


def _fvol(v: int) -> str:
    if v >= 10_000_000: return f"{v/10_000_000:.1f} Cr"
    if v >= 100_000:    return f"{v/100_000:.1f} L"
    return f"{v:,}"


def _row(sym: str, d: dict) -> str:
    chg_cls   = "up" if d["chg"] >= 0 else "down"
    chg_sign  = "+" if d["chg"] >= 0 else ""
    chg_o_cls = "up" if d["chg_o"] >= 0 else "down"
    chg_o_sign= "+" if d["chg_o"] >= 0 else ""
    ipos_pct  = d["ipos"] * 100
    # color: green when in upper half, red when lower, orange middle
    if d["ipos"] >= 0.6:   ibar_color = "#0ca30c"
    elif d["ipos"] <= 0.4: ibar_color = "#d03b3b"
    else:                  ibar_color = "#e8932d"

    return ROW_TEMPLATE.format(
        sym=sym, name=d["name"],
        ltp=d["ltp"], prev=d["prev"],
        chg=abs(d["chg"]), chg_cls=chg_cls, chg_sign=chg_sign,
        chg_o=abs(d["chg_o"]), chg_o_cls=chg_o_cls, chg_o_sign=chg_o_sign,
        hi=d["hi"], lo=d["lo"],
        vol_fmt=_fvol(d["vol"]),
        ipos_pct=ipos_pct, ibar_color=ibar_color,
        ts=d["ts"],
    )


def _summary_strip(data: dict[str, dict]) -> str:
    vals = list(data.values())
    n_up   = sum(1 for d in vals if d["chg"] >= 0)
    n_down = len(vals) - n_up
    avg_chg = sum(d["chg"] for d in vals) / len(vals) if vals else 0
    best   = max(vals, key=lambda d: d["chg"])
    worst  = min(vals, key=lambda d: d["chg"])

    def pill(label, val_str, cls):
        return f'<div class="pill"><div class="pill-label">{label}</div><div class="pill-val {cls}">{val_str}</div></div>'

    avg_cls = "up" if avg_chg >= 0 else "down"
    return (
        '<div class="summary">'
        + pill("Advancing", str(n_up), "up")
        + pill("Declining", str(n_down), "down")
        + pill("Avg Change", f"{'+'if avg_chg>=0 else ''}{avg_chg:.2f}%", avg_cls)
        + pill("Best", f"{best['name']} +{best['chg']:.2f}%", "up")
        + pill("Worst", f"{worst['name']} {worst['chg']:.2f}%", "down")
        + "</div>"
    )


def _cached_data(pairs: list[tuple[str, str]]) -> tuple[dict[str, dict], str]:
    """Return a visible, clearly labelled fallback when live quotes fail."""
    cache_file = ROOT / "data" / "fund_prices_cache.json"
    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
        prices = cache.get("prices", {})
        cache_date = cache.get("date", "unknown date")
    except Exception:
        return {}, "Source: no quote data available"

    data = {}
    for sym, name in pairs:
        if sym not in prices:
            continue
        p = round(float(prices[sym]), 2)
        data[sym] = {
            "name": name, "ltp": p, "prev": p, "open": p,
            "hi": p, "lo": p, "vol": 0, "chg": 0.0, "chg_o": 0.0,
            "ipos": 0.5, "ts": str(cache_date),
        }
    if data:
        return data, f"Source: Agent Adda EOD cache ({cache_date}) · live provider unavailable"
    return {}, "Source: no quote data available"


def build_html(
    sections: list[tuple[str, list[tuple[str, str]]]],
    data: dict[str, dict],
    ts: str,
    source_note: str = "Source: yfinance · ~15-min delay",
) -> str:
    all_data = {sym: data[sym] for _, pairs in sections for sym, _ in pairs if sym in data}

    summary = _summary_strip(all_data) if all_data else ""

    sections_html = []
    for title, pairs in sections:
        rows = [_row(sym, data[sym]) for sym, _ in pairs if sym in data]
        if not rows:
            continue
        sections_html.append(
            f'<div class="section-hd">{title}</div>'
            + TABLE_HEADER
            + "\n".join(rows)
            + TABLE_FOOTER
        )

    html = HTML_TEMPLATE.replace("REFRESH_TS", ts)
    html = html.replace("SOURCE_NOTE", source_note)
    html = html.replace("SUMMARY_STRIP", summary)
    html = html.replace("SECTIONS_HTML", "\n".join(sections_html))
    return html


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Generate live NSE price dashboard")
    ap.add_argument("--no-open",   action="store_true",  help="Don't open the browser")
    ap.add_argument("--watchlist", default="portfolio",
                    choices=list(WATCHLISTS.keys()),
                    help="Built-in watchlist (default: nifty50)")
    ap.add_argument("--symbols",   default="",
                    help="Comma-separated symbols to add/override, e.g. RELIANCE,TCS")
    args = ap.parse_args()

    # build pairs list
    base_pairs = WATCHLISTS.get(args.watchlist, WATCHLISTS["nifty50"])
    extra_syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    extra_pairs = [(s, s) for s in extra_syms]

    # sections
    sections: list[tuple[str, list[tuple[str, str]]]] = []
    if extra_pairs:
        sections.append(("Custom symbols", extra_pairs))
    sections.append((f"Watchlist — {args.watchlist.upper()}", base_pairs))

    all_pairs = list({sym: name for sym, name in extra_pairs + base_pairs}.items())

    print(f"Fetching live prices for {len(all_pairs)} symbols…")
    data = fetch_all(all_pairs)
    source_note = "Source: yfinance · ~15-min delay"
    cached_data, cached_note = _cached_data(all_pairs)
    missing = [sym for sym, _ in all_pairs if sym not in data]
    if missing:
        # Fill provider gaps from the latest Agent Adda cache so a holding is
        # never silently omitted. The row timestamp and source note make the
        # stale/mixed nature explicit to the reader.
        data.update({sym: cached_data[sym] for sym in missing if sym in cached_data})
        cached_filled = [sym for sym in missing if sym in cached_data]
        if cached_filled and data:
            source_note = "Source: mixed yfinance + Agent Adda EOD cache · live provider gaps marked by row date"
            print(f"  Filled {len(cached_filled)} provider gap(s) from cached EOD prices: {', '.join(cached_filled)}")
        elif not data:
            data, source_note = cached_data, cached_note
            if data:
                print("  Live provider returned no quotes; using cached EOD prices")

    ts  = datetime.now().strftime("%d %b %Y  %H:%M IST")
    html = build_html(sections, data, ts, source_note)

    LATEST.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")

    fetched = len(data)
    failed  = len(all_pairs) - fetched
    print(f"✓  live_prices.html  ({len(html):,} bytes)")
    print(f"   {fetched} fetched, {failed} failed")
    print(f"   As of {ts}")
    print(f"   {OUT}")

    if not args.no_open:
        subprocess.run(["open", str(OUT)])


if __name__ == "__main__":
    main()
