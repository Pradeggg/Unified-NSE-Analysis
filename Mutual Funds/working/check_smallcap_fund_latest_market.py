from __future__ import annotations

import csv
import html
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal.tools import get_index_snapshot, get_live_quote


RUN_DATE = "20260807"
NAV = 500_000.0
PHASE1_EXPOSURE_CAP = NAV * 0.40
OPEN_RISK_CAP = NAV * 0.06
INPUT = ROOT / "Mutual Funds" / "extracted" / "agent_adda_smallcap_phase1_evidence_packs_20260806.csv"
OUT_CSV = ROOT / "Mutual Funds" / "extracted" / f"agent_adda_smallcap_fund_latest_market_check_{RUN_DATE}.csv"
OUT_JSON = ROOT / "Mutual Funds" / "extracted" / f"agent_adda_smallcap_fund_latest_market_check_{RUN_DATE}.json"
OUT_HTML = ROOT / "Mutual Funds" / "reports" / f"agent_adda_smallcap_fund_latest_market_check_{RUN_DATE}.html"


EXTERNAL_MARKET_CONTEXT = [
    {
        "source": "Economic Times",
        "as_of": "2026-08-07 09:40 IST",
        "note": (
            "Indian market opened lower as oil rose on Strait of Hormuz concerns; Nifty 50 traded near "
            "24,600, broader Midcap 100 and Smallcap 100 were marginally red, while NSE breadth was "
            "slightly positive at 1,297 advances versus 1,042 declines."
        ),
        "url": "https://economictimes.indiatimes.com/markets/stocks/news/sensex-drops-over-200-points-nifty-tests-23600-as-strait-of-hormuz-tensions-rattle-oil-markets/articleshow/133020628.cms",
    },
    {
        "source": "Investing.com UK",
        "as_of": "2026-08-07 crawl",
        "note": (
            "Nifty Smallcap 250 was quoted around 18,360, with an intraday range shown near "
            "18,301.70-18,404.45 and 52-week range near 14,143.45-18,407.40."
        ),
        "url": "https://uk.investing.com/indices/nifty-smallcap-250",
    },
    {
        "source": "Economic Times",
        "as_of": "2026-08-05 13:21 IST",
        "note": (
            "Smallcap leadership had already strengthened earlier in the week, with Nifty Smallcap 250 "
            "near a fresh 52-week high and earnings/valuation reset cited as support."
        ),
        "url": "https://economictimes.indiatimes.com/markets/stocks/news/nifty-smallcap-250-hits-52-week-high-as-ola-electric-other-stocks-rally-up-to-7-what-lies-ahead/articleshow/132903983.cms",
    },
]


def fnum(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "na", "n/a"}:
        return None
    text = text.replace(",", "").replace("%", "").replace("Rs.", "").replace("₹", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def fmt_num(value: Any, digits: int = 2) -> str:
    number = fnum(value)
    if number is None:
        return "NA"
    return f"{number:,.{digits}f}"


def fmt_pct(value: Any, digits: int = 2) -> str:
    number = fnum(value)
    if number is None:
        return "NA"
    return f"{number:,.{digits}f}%"


def fmt_money(value: Any) -> str:
    number = fnum(value)
    if number is None:
        return "NA"
    return f"Rs. {number:,.0f}"


def read_rows() -> list[dict[str, Any]]:
    with INPUT.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_levels(trigger: str) -> tuple[float | None, float | None]:
    breakout = None
    retest = None
    m = re.search(r"Break above\s+([0-9,.]+)", trigger or "", flags=re.I)
    if m:
        breakout = fnum(m.group(1))
    m = re.search(r"retest-hold near\s+([0-9,.]+)", trigger or "", flags=re.I)
    if m:
        retest = fnum(m.group(1))
    return breakout, retest


def latest_quote(symbol: str) -> dict[str, Any]:
    try:
        out = get_live_quote(symbol) or {}
        if out.get("error"):
            return {"symbol": symbol, "error": out.get("error")}
        return out
    except Exception as exc:
        return {"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"}


def yfinance_index_snapshot(ticker: str, label: str) -> dict[str, Any]:
    try:
        import yfinance as yf

        hist = yf.Ticker(ticker).history(period="5d", interval="1d", auto_adjust=False)
        if hist.empty:
            return {"label": label, "ticker": ticker, "error": "no yfinance rows"}
        latest = hist.tail(1).iloc[0]
        previous_rows = hist.tail(2)
        prev_close = previous_rows.iloc[0]["Close"] if len(previous_rows) >= 2 else None
        close = float(latest["Close"])
        pct = ((close / float(prev_close) - 1) * 100) if prev_close not in (None, 0) else None
        return {
            "label": label,
            "ticker": ticker,
            "as_of": str(hist.tail(1).index[0]),
            "open": round(float(latest["Open"]), 2),
            "high": round(float(latest["High"]), 2),
            "low": round(float(latest["Low"]), 2),
            "close": round(close, 2),
            "prev_close": round(float(prev_close), 2) if prev_close is not None else None,
            "pct_change": round(pct, 2) if pct is not None else None,
            "source": "yfinance delayed daily row",
        }
    except Exception as exc:
        return {"label": label, "ticker": ticker, "error": f"{type(exc).__name__}: {exc}"}


def local_index_snapshot(index_name: str) -> dict[str, Any]:
    try:
        out = get_index_snapshot(index_name) or {}
        return {
            "label": index_name,
            "as_of": out.get("as_of"),
            "open": out.get("open"),
            "high": out.get("high"),
            "low": out.get("low"),
            "close": out.get("close"),
            "pct_change": out.get("chg_pct"),
            "source": "Agent Adda local index snapshot",
            "trend_10d": out.get("trend_10d"),
            "error": out.get("error"),
        }
    except Exception as exc:
        return {"label": index_name, "error": f"{type(exc).__name__}: {exc}"}


def trigger_state(row: dict[str, Any], quote: dict[str, Any]) -> tuple[str, str]:
    breakout, retest = parse_levels(row.get("entry_trigger", ""))
    last = fnum(quote.get("last_price"))
    high = fnum(quote.get("day_high"))
    low = fnum(quote.get("day_low"))
    stop = fnum(row.get("initial_stop_price"))
    bucket = row.get("bucket", "")

    if last is None:
        return "NO_QUOTE", "Quote unavailable; keep as watch-only."
    if stop is not None and low is not None and low <= stop:
        return "STOP_ZONE_HIT", "Latest day low breached or touched the mapped stop; candidate must be reviewed."
    if breakout is not None and high is not None and high >= breakout and last >= breakout:
        if bucket == "Retest trigger map":
            return "BREAKOUT_TOUCHED_BUT_RETEST_ONLY", "Breakout zone touched, but policy bucket remains retest-only/no-chase."
        return "BREAKOUT_TRIGGER_ACTIVE", "Breakout level has been cleared; needs volume/governance confirmation before order."
    if breakout is not None and high is not None and high >= breakout:
        return "BREAKOUT_TOUCHED_NOT_CONFIRMED", "Breakout level touched intraday but latest price is below trigger."
    if retest is not None and low is not None and low <= retest <= last:
        if bucket == "Retest trigger map":
            return "RETEST_HOLD_WATCH", "Retest zone held so far; still retest-only and needs close/next-session confirmation."
        return "RETEST_TRIGGER_WATCH", "Retest zone held so far; needs close/volume confirmation before order."
    if retest is not None and low is not None and low <= retest and last < retest:
        return "RETEST_UNDER_PRESSURE", "Retest zone was lost intraday; no order."
    if breakout is not None and last is not None:
        distance = (breakout / last - 1) * 100
        if 0 <= distance <= 3:
            if bucket == "Retest trigger map":
                return "NEAR_BREAKOUT_RETEST_ONLY", "Near breakout, but policy says retest-only/no-chase."
            return "NEAR_BREAKOUT", "Within 3% of breakout; prepare trigger but no order yet."
    return "NO_TRIGGER_WAIT", "No mapped breakout/retest trigger has confirmed."


def build_symbol_row(row: dict[str, Any]) -> dict[str, Any]:
    quote = latest_quote(row["symbol"])
    ref = fnum(row.get("current_price"))
    last = fnum(quote.get("last_price"))
    qty = int(fnum(row.get("paper_quantity_by_policy")) or 0)
    stop = fnum(row.get("initial_stop_price"))
    breakout, retest = parse_levels(row.get("entry_trigger", ""))
    shadow_pnl = (last - ref) * qty if last is not None and ref is not None else None
    ref_change = (last / ref - 1) * 100 if last is not None and ref not in (None, 0) else None
    stop_gap = (last / stop - 1) * 100 if last is not None and stop not in (None, 0) else None
    breakout_gap = (breakout / last - 1) * 100 if breakout not in (None, 0) and last not in (None, 0) else None
    retest_gap = (last / retest - 1) * 100 if retest not in (None, 0) and last not in (None, 0) else None
    state, note = trigger_state(row, quote)
    return {
        "symbol": row["symbol"],
        "company": row.get("company", ""),
        "bucket": row.get("bucket", ""),
        "policy_score_100": row.get("policy_score_100", ""),
        "policy_rating": row.get("policy_rating", ""),
        "theme_lens": row.get("theme_lens", ""),
        "reference_price": ref,
        "latest_price": last,
        "latest_pct_change": quote.get("pct_change"),
        "move_vs_reference_pct": ref_change,
        "day_high": quote.get("day_high"),
        "day_low": quote.get("day_low"),
        "volume_shares": quote.get("volume_shares"),
        "quote_as_of": quote.get("as_of"),
        "quote_source": quote.get("source") or quote.get("error") or "",
        "breakout_level": breakout,
        "retest_level": retest,
        "stop_price": stop,
        "target_2r_price": fnum(row.get("target_2r_price")),
        "distance_to_breakout_pct": breakout_gap,
        "distance_above_retest_pct": retest_gap,
        "distance_above_stop_pct": stop_gap,
        "paper_quantity_by_policy": qty,
        "paper_position_value_reference": fnum(row.get("paper_position_value")),
        "paper_position_value_latest": qty * last if last is not None else None,
        "shadow_pnl": shadow_pnl,
        "shadow_pnl_pct_nav": (shadow_pnl / NAV * 100) if shadow_pnl is not None else None,
        "paper_risk_to_stop": fnum(row.get("paper_risk_to_stop")),
        "trigger_state": state,
        "trigger_note": note,
        "evidence_blockers": row.get("evidence_blockers", ""),
        "next_action": row.get("next_action", ""),
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    clean = [r for r in rows if r["bucket"] == "Clean trigger map"]
    retest = [r for r in rows if r["bucket"] == "Retest trigger map"]

    def sums(subset: list[dict[str, Any]]) -> dict[str, Any]:
        exposure_ref = sum(fnum(r.get("paper_position_value_reference")) or 0 for r in subset)
        exposure_latest = sum(fnum(r.get("paper_position_value_latest")) or 0 for r in subset)
        risk = sum(fnum(r.get("paper_risk_to_stop")) or 0 for r in subset)
        pnl = sum(fnum(r.get("shadow_pnl")) or 0 for r in subset)
        winners = sum(1 for r in subset if (fnum(r.get("shadow_pnl")) or 0) > 0)
        losers = sum(1 for r in subset if (fnum(r.get("shadow_pnl")) or 0) < 0)
        triggers = sum(1 for r in subset if "TRIGGER_ACTIVE" in r.get("trigger_state", ""))
        return {
            "count": len(subset),
            "exposure_reference": exposure_ref,
            "exposure_latest": exposure_latest,
            "risk_to_stop": risk,
            "shadow_pnl": pnl,
            "shadow_return_on_reference_pct": (pnl / exposure_ref * 100) if exposure_ref else 0,
            "shadow_return_on_nav_pct": pnl / NAV * 100,
            "winners": winners,
            "losers": losers,
            "active_triggers": triggers,
        }

    return {
        "actual_fund": {
            "nav": NAV,
            "paper_orders": 0,
            "gross_exposure": 0,
            "open_risk": 0,
            "pnl": 0,
            "status": "No portfolio-specific paper orders have been created; this remains a trigger-map watchlist.",
        },
        "clean_trigger_map": sums(clean),
        "retest_trigger_map": sums(retest),
        "all_trigger_map": sums(rows),
    }


def index_context() -> dict[str, Any]:
    return {
        "live_delayed": [
            yfinance_index_snapshot("^NSEI", "Nifty 50"),
            yfinance_index_snapshot("^NSEBANK", "Nifty Bank"),
            yfinance_index_snapshot("^CNXSC", "Nifty Smallcap 100"),
        ],
        "local_eod": [
            local_index_snapshot("NIFTY 50"),
            local_index_snapshot("NIFTY BANK"),
            local_index_snapshot("NIFTY 500"),
            local_index_snapshot("NIFTY SMALLCAP 250"),
            local_index_snapshot("NIFTY SMALLCAP 100"),
            local_index_snapshot("NIFTY MIDCAP 100"),
        ],
        "external_notes": EXTERNAL_MARKET_CONTEXT,
    }


def write_csv(rows: list[dict[str, Any]]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(rows: list[dict[str, Any]], agg: dict[str, Any], indices: dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_date": RUN_DATE,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "nav": NAV,
        "phase1_exposure_cap": PHASE1_EXPOSURE_CAP,
        "open_risk_cap": OPEN_RISK_CAP,
        "input": str(INPUT.relative_to(ROOT)),
        "aggregation": agg,
        "index_context": indices,
        "rows": rows,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def status_class(state: str) -> str:
    low = state.lower()
    if "active" in low:
        return "ok"
    if "near" in low or "watch" in low:
        return "watch"
    if "pressure" in low or "stop" in low:
        return "bad"
    return "wait"


def metric(label: str, value: Any, detail: str = "") -> str:
    return f"""
      <div class="metric">
        <span>{esc(label)}</span>
        <b>{esc(value)}</b>
        <small>{esc(detail)}</small>
      </div>
    """


def index_cards(indices: dict[str, Any]) -> str:
    cards = []
    for item in indices["live_delayed"]:
        if item.get("error"):
            cards.append(metric(item["label"], "NA", item["error"]))
        else:
            cards.append(metric(item["label"], fmt_num(item.get("close")), f"{fmt_pct(item.get('pct_change'))} / {item.get('as_of', '')[:10]}"))
    for item in indices["local_eod"]:
        cards.append(metric(f"{item['label']} EOD", fmt_num(item.get("close")), f"{fmt_pct(item.get('pct_change'))} / {item.get('as_of')}"))
    return "\n".join(cards)


def context_notes(indices: dict[str, Any]) -> str:
    notes = []
    for item in indices["external_notes"]:
        notes.append(
            f"""
            <article class="note-card">
              <h3>{esc(item['source'])}</h3>
              <p>{esc(item['note'])}</p>
              <a href="{esc(item['url'])}">{esc(item['as_of'])}</a>
            </article>
            """
        )
    return "\n".join(notes)


def row_html(row: dict[str, Any]) -> str:
    return f"""
      <tr>
        <td><b>{esc(row['symbol'])}</b><span>{esc(row['company'])}</span></td>
        <td>{esc(row['bucket'])}<span>{esc(row['theme_lens'])}</span></td>
        <td>{fmt_num(row['latest_price'])}<span>{fmt_pct(row['latest_pct_change'])} today</span></td>
        <td>{fmt_num(row['reference_price'])}<span>{fmt_pct(row['move_vs_reference_pct'])} vs reference</span></td>
        <td>{fmt_num(row['day_high'])} / {fmt_num(row['day_low'])}<span>{esc(row['quote_as_of'])}</span></td>
        <td>{fmt_num(row['breakout_level'])}<span>{fmt_pct(row['distance_to_breakout_pct'])} away</span></td>
        <td>{fmt_num(row['retest_level'])}<span>{fmt_pct(row['distance_above_retest_pct'])} above</span></td>
        <td>{fmt_num(row['stop_price'])}<span>{fmt_pct(row['distance_above_stop_pct'])} cushion</span></td>
        <td>{fmt_money(row['paper_position_value_latest'])}<span>qty {esc(row['paper_quantity_by_policy'])}</span></td>
        <td class="{status_class(row['trigger_state'])}">{esc(row['trigger_state'])}<span>{esc(row['trigger_note'])}</span></td>
        <td>{fmt_money(row['shadow_pnl'])}<span>{fmt_pct(row['shadow_pnl_pct_nav'])} NAV</span></td>
      </tr>
    """


def write_html(rows: list[dict[str, Any]], agg: dict[str, Any], indices: dict[str, Any]) -> None:
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    clean = agg["clean_trigger_map"]
    retest = agg["retest_trigger_map"]
    all_map = agg["all_trigger_map"]
    table = "\n".join(row_html(row) for row in rows)
    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Adda Smallcap Portfolio - Latest Market Check</title>
  <style>
    :root {{
      --ink:#17222b; --muted:#63717c; --line:#dbe3e8; --paper:#fff; --soft:#f5f8fa;
      --green:#0e6b52; --amber:#9a6a00; --red:#9a332b; --blue:#1f5d8f;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:#fbfcfd; color:var(--ink); font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif; }}
    header, main, footer {{ padding:24px 32px; }}
    header, footer {{ background:var(--paper); border-bottom:1px solid var(--line); }}
    footer {{ border-top:1px solid var(--line); border-bottom:0; color:var(--muted); }}
    h1 {{ margin:0 0 6px; font-size:28px; letter-spacing:0; }}
    h2 {{ margin:26px 0 12px; font-size:20px; letter-spacing:0; }}
    h3 {{ margin:0 0 7px; font-size:16px; letter-spacing:0; }}
    p {{ margin:0 0 10px; }}
    a {{ color:var(--blue); text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    .meta, .summary, .index-grid, .notes {{ display:grid; gap:10px; }}
    .meta {{ display:flex; flex-wrap:wrap; margin-top:12px; color:var(--muted); }}
    .pill {{ border:1px solid var(--line); border-radius:8px; padding:7px 9px; background:var(--soft); }}
    .summary {{ grid-template-columns:repeat(6,minmax(130px,1fr)); }}
    .index-grid {{ grid-template-columns:repeat(3,minmax(150px,1fr)); }}
    .notes {{ grid-template-columns:repeat(3,minmax(0,1fr)); }}
    .metric, .note-card, .decision {{ background:var(--paper); border:1px solid var(--line); border-radius:8px; padding:12px; }}
    .metric span, td span, small {{ display:block; color:var(--muted); }}
    .metric b {{ display:block; margin-top:3px; font-size:21px; }}
    .decision {{ border-left:5px solid var(--green); background:#eef7f2; margin:14px 0; }}
    .warning {{ border-left:5px solid var(--amber); background:#fff8e8; }}
    .table-wrap {{ overflow:auto; border:1px solid var(--line); border-radius:8px; background:var(--paper); }}
    table {{ width:100%; min-width:1500px; border-collapse:collapse; }}
    th, td {{ border-bottom:1px solid var(--line); padding:9px 8px; text-align:left; vertical-align:top; }}
    th {{ background:#eef3f5; color:#31434f; font-size:12px; }}
    .ok {{ color:var(--green); font-weight:700; }}
    .watch {{ color:var(--amber); font-weight:700; }}
    .bad {{ color:var(--red); font-weight:700; }}
    .wait {{ color:#52606a; font-weight:700; }}
    @media (max-width:1100px) {{
      .summary, .index-grid, .notes {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
    }}
    @media (max-width:720px) {{
      header, main, footer {{ padding:16px; }}
      h1 {{ font-size:23px; }}
      .summary, .index-grid, .notes {{ grid-template-columns:1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Agent Adda Smallcap Portfolio - Latest Market Check</h1>
    <p>Portfolio state, shadow trigger-map P&L, trigger status, and market context for the Phase 1 smallcap paper-portfolio candidates.</p>
    <div class="meta">
      <span class="pill">Generated: {esc(generated)}</span>
      <span class="pill">Input: {esc(str(INPUT.relative_to(ROOT)))}</span>
      <span class="pill">Quote source: yfinance via Agent Adda live quote</span>
      <span class="pill">Research only</span>
    </div>
  </header>
  <main>
    <section class="summary">
      {metric("Actual portfolio NAV", fmt_money(NAV), "no portfolio-specific paper orders")}
      {metric("Actual portfolio P&L", fmt_money(0), "watchlist only")}
      {metric("Clean shadow P&L", fmt_money(clean["shadow_pnl"]), f"{fmt_pct(clean['shadow_return_on_reference_pct'])} on model exposure")}
      {metric("Retest shadow P&L", fmt_money(retest["shadow_pnl"]), f"{fmt_pct(retest['shadow_return_on_reference_pct'])} on model exposure")}
      {metric("All shadow P&L", fmt_money(all_map["shadow_pnl"]), f"{fmt_pct(all_map['shadow_return_on_nav_pct'])} of NAV")}
      {metric("Active triggers", all_map["active_triggers"], "deterministic trigger count")}
    </section>

    <section class="decision">
      <h2>Decision</h2>
      <p><b>Portfolio status: WAIT / no paper order.</b> The official smallcap paper portfolio still has zero exposure, zero open risk, and zero P&L because the evidence packs created a trigger map, not executed trades.</p>
      <p>The clean watchlist is slightly negative on a shadow mark-to-market basis, while the retest reserve is positive. That is useful information, but it does not override the no-chase and governance gates.</p>
    </section>

    <section class="decision warning">
      <h2>Market Read</h2>
      <p>Smallcaps remain near leadership territory, but the Aug 7 tape is not a clean risk-on confirmation: benchmarks opened weak, oil/geopolitical risk is active, and the local Aug 6 EOD smallcap indexes were already close to 52-week highs. This supports watchlist discipline rather than forced deployment.</p>
    </section>

    <h2>Index Context</h2>
    <section class="index-grid">{index_cards(indices)}</section>

    <h2>External Market Notes</h2>
    <section class="notes">{context_notes(indices)}</section>

    <h2>Candidate Trigger And Shadow P&L</h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Stock</th><th>Bucket / Theme</th><th>Latest</th><th>Reference</th><th>Day H/L</th><th>Breakout</th><th>Retest</th><th>Stop</th><th>Model Slot</th><th>Trigger State</th><th>Shadow P&L</th>
          </tr>
        </thead>
        <tbody>{table}</tbody>
      </table>
    </div>
  </main>
  <footer>
    Actual portfolio P&L is zero because no portfolio-specific paper order has been created. Shadow P&L assumes the model quantities from the 2026-08-06 evidence pack were hypothetically entered at their reference prices; it is diagnostic only, not a trade record.
  </footer>
</body>
</html>
"""
    OUT_HTML.write_text(html_text, encoding="utf-8")


def main() -> None:
    source_rows = read_rows()
    rows = [build_symbol_row(row) for row in source_rows]
    agg = aggregate(rows)
    indices = index_context()
    write_csv(rows)
    write_json(rows, agg, indices)
    write_html(rows, agg, indices)
    print(f"Wrote {OUT_HTML}")
    print(f"Wrote {OUT_CSV}")
    print(f"Wrote {OUT_JSON}")
    print("Actual portfolio P&L: 0; no portfolio-specific paper orders.")
    print("Clean shadow P&L:", round(agg["clean_trigger_map"]["shadow_pnl"], 2))
    print("Retest shadow P&L:", round(agg["retest_trigger_map"]["shadow_pnl"], 2))
    print("All shadow P&L:", round(agg["all_trigger_map"]["shadow_pnl"], 2))
    print("Active triggers:", agg["all_trigger_map"]["active_triggers"])
    for row in rows:
        print(row["symbol"], row["latest_price"], row["trigger_state"], round(fnum(row["shadow_pnl"]) or 0, 2))


if __name__ == "__main__":
    main()
