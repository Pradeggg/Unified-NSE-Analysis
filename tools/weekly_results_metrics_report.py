from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from terminal.financials_cache import to_number, screener_payload_from_cache, upsert_screener_payload
from terminal.web_research import scrape_screener_in


ROOT = Path(__file__).resolve().parent.parent

try:
    from terminal.research_council.reports.markdown_renderer import DISCLAIMER as AGENT_ADDA_DISCLAIMER
except Exception:
    AGENT_ADDA_DISCLAIMER = "Not investment advice. For research and learning only."


@dataclass(frozen=True)
class Series:
    headers: list[str]
    values: list[float | None]


def _series(section: dict[str, Any], label: str) -> Series | None:
    if not isinstance(section, dict):
        return None
    headers = section.get("_headers")
    raw = section.get(label)
    if not isinstance(headers, list) or not isinstance(raw, list):
        return None
    values = [to_number(v) for v in raw]
    if not headers or not values or len(headers) != len(values):
        return None
    return Series(headers=[str(h) for h in headers], values=values)


def _latest(series: Series) -> tuple[str, float | None] | None:
    if not series.headers:
        return None
    return series.headers[-1], series.values[-1]


def _prev(series: Series, n: int = 1) -> tuple[str, float | None] | None:
    if len(series.headers) <= n:
        return None
    return series.headers[-1 - n], series.values[-1 - n]


def _pct_change(cur: float | None, prev: float | None) -> float | None:
    if cur is None or prev is None:
        return None
    if prev == 0:
        return None
    return (cur - prev) / abs(prev) * 100.0


def _ratio(numer: float | None, denom: float | None) -> float | None:
    if numer is None or denom is None:
        return None
    if denom == 0:
        return None
    return numer / denom


def _fmt(v: float | None, *, suffix: str = "", digits: int = 2) -> str:
    if v is None:
        return ""
    return f"{v:.{digits}f}{suffix}"


def _fmt_int(v: float | None) -> str:
    if v is None:
        return ""
    return f"{int(round(v)):,}"


def _ensure_screener_payload(symbol: str, *, ttl_hours: float | None) -> tuple[dict[str, Any] | None, str]:
    pg_ok = True
    try:
        cached = screener_payload_from_cache(symbol, max_age_hours=ttl_hours)
    except Exception:
        cached = None
        pg_ok = False
    if cached:
        return cached, "pg_cache" if pg_ok else "pg_cache_unavailable"
    try:
        live = scrape_screener_in(symbol)
        if isinstance(live, dict) and (live.get("quarterly") or live.get("annual_pl")):
            try:
                if pg_ok:
                    upsert_screener_payload(symbol, live)
            except Exception:
                # Cache writes are best-effort; still return live.
                pass
            return live, "live_screener"
    except Exception:
        pass
    if pg_ok:
        try:
            stale = screener_payload_from_cache(symbol, max_age_hours=None)
        except Exception:
            stale = None
        if stale:
            return stale, "pg_cache_stale"
    return None, "missing"


def _to_cr_from_lakhs(lakhs: float | None) -> float | None:
    if lakhs is None:
        return None
    return lakhs / 100.0


def _build_rows(symbols: list[str], *, ttl_hours: float | None) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    notes: list[str] = []

    for sym in symbols:
        payload, source = _ensure_screener_payload(sym, ttl_hours=ttl_hours)
        if not payload:
            rows.append({"symbol": sym, "status": "missing", "source": source})
            continue

        q = payload.get("quarterly") if isinstance(payload, dict) else {}
        bs = payload.get("balance_sheet") if isinstance(payload, dict) else {}
        cf = payload.get("cash_flow") if isinstance(payload, dict) else {}

        sales_s = _series(q, "Sales") or _series(q, "Revenue") or _series(q, "Revenue from Operations")
        pat_s = _series(q, "Net Profit") or _series(q, "PAT")
        opm_s = _series(q, "OPM %") or _series(q, "OPM")
        op_s = _series(q, "Operating Profit")
        interest_s = _series(q, "Interest")

        if not (sales_s and pat_s):
            rows.append({"symbol": sym, "status": "partial", "source": source})
            continue

        latest_period, sales = _latest(sales_s) or ("", None)
        _p, pat = _latest(pat_s) or ("", None)

        sales_prev = _prev(sales_s, 1)
        sales_yoy = _prev(sales_s, 4)
        pat_prev = _prev(pat_s, 1)
        pat_yoy = _prev(pat_s, 4)

        sales_qoq = _pct_change(sales, sales_prev[1] if sales_prev else None)
        sales_yoy_pct = _pct_change(sales, sales_yoy[1] if sales_yoy else None)
        pat_qoq = _pct_change(pat, pat_prev[1] if pat_prev else None)
        pat_yoy_pct = _pct_change(pat, pat_yoy[1] if pat_yoy else None)

        opm_latest = (_latest(opm_s)[1] if opm_s and _latest(opm_s) else None)
        npm_latest = _ratio(pat, sales)
        npm_latest = (npm_latest * 100.0) if npm_latest is not None else None

        op_latest = (_latest(op_s)[1] if op_s and _latest(op_s) else None)
        interest_latest = (_latest(interest_s)[1] if interest_s and _latest(interest_s) else None)
        interest_coverage = _ratio(op_latest, interest_latest)

        equity_cap_s = _series(bs, "Equity Capital")
        reserves_s = _series(bs, "Reserves")
        borrowings_s = _series(bs, "Borrowings+")

        equity_latest = None
        if equity_cap_s and reserves_s:
            ec = _latest(equity_cap_s)[1] if _latest(equity_cap_s) else None
            rs = _latest(reserves_s)[1] if _latest(reserves_s) else None
            if ec is not None and rs is not None:
                equity_latest = ec + rs
        borrowings_latest = _latest(borrowings_s)[1] if borrowings_s and _latest(borrowings_s) else None
        debt_to_equity = _ratio(borrowings_latest, equity_latest)

        ocf_s = _series(cf, "Cash from Operating Activity+")
        ocf_latest = _latest(ocf_s)[1] if ocf_s and _latest(ocf_s) else None

        rows.append(
            {
                "symbol": sym,
                "status": "ok",
                "source": source,
                "latest_period": latest_period,
                "sales_cr": _to_cr_from_lakhs(sales),
                "sales_qoq_pct": sales_qoq,
                "sales_yoy_pct": sales_yoy_pct,
                "pat_cr": _to_cr_from_lakhs(pat),
                "pat_qoq_pct": pat_qoq,
                "pat_yoy_pct": pat_yoy_pct,
                "opm_pct": opm_latest,
                "npm_pct": npm_latest,
                "interest_cov_x": interest_coverage,
                "debt_to_equity_x": debt_to_equity,
                "ocf_cr": _to_cr_from_lakhs(ocf_latest),
            }
        )

        cache_age = payload.get("_cache_age_hours")
        if cache_age is not None:
            notes.append(f"{sym}: cache_age_hours={cache_age} (source={source})")

    return rows, notes


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    cols = [
        "symbol",
        "status",
        "source",
        "latest_period",
        "sales_cr",
        "sales_qoq_pct",
        "sales_yoy_pct",
        "pat_cr",
        "pat_qoq_pct",
        "pat_yoy_pct",
        "opm_pct",
        "npm_pct",
        "interest_cov_x",
        "debt_to_equity_x",
        "ocf_cr",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})


def _write_html(path: Path, rows: list[dict[str, Any]], *, generated_on: str, notes: list[str]) -> None:
    from terminal.ui.html_theme import agent_adda_dark_css

    narrative = _build_narrative(rows)

    def td(txt: str, *, cls: str = "") -> str:
        class_attr = f' class="{cls}"' if cls else ""
        return f"<td{class_attr}>{txt}</td>"

    def th(txt: str, *, cls: str = "") -> str:
        class_attr = f' class="{cls}"' if cls else ""
        return f"<th{class_attr}>{txt}</th>"

    def row_class(r: dict[str, Any]) -> str:
        if r.get("status") != "ok":
            return "neutral"
        d2e = r.get("debt_to_equity_x")
        if isinstance(d2e, (int, float)) and d2e >= 1.5:
            return "warning"
        return ""

    table_rows = []
    for r in rows:
        rc = row_class(r)
        table_rows.append(
            "<tr>"
            + td(str(r.get("symbol", "")), cls="nowrap")
            + td(str(r.get("latest_period", "")), cls="nowrap")
            + td(str(r.get("status", "")), cls=f"nowrap {rc}".strip())
            + td(str(r.get("source", "")), cls="nowrap")
            + td(_fmt(r.get("sales_cr")), cls="num")
            + td(_fmt(r.get("sales_qoq_pct"), suffix="%", digits=1), cls="num")
            + td(_fmt(r.get("sales_yoy_pct"), suffix="%", digits=1), cls="num")
            + td(_fmt(r.get("pat_cr")), cls="num")
            + td(_fmt(r.get("pat_qoq_pct"), suffix="%", digits=1), cls="num")
            + td(_fmt(r.get("pat_yoy_pct"), suffix="%", digits=1), cls="num")
            + td(_fmt(r.get("opm_pct"), suffix="%", digits=1), cls="num")
            + td(_fmt(r.get("npm_pct"), suffix="%", digits=1), cls="num")
            + td(_fmt(r.get("interest_cov_x"), digits=2), cls="num")
            + td(_fmt(r.get("debt_to_equity_x"), digits=2), cls="num")
            + td(_fmt(r.get("ocf_cr")), cls="num")
            + "</tr>"
        )

    notes_html = "".join(f"<li><code>{n}</code></li>" for n in notes[:50]) if notes else "<li><em>none</em></li>"

    extra_css = """
.table-scroll { overflow-x:auto; -webkit-overflow-scrolling:touch; }
table { font-variant-numeric: tabular-nums; }
thead th { position: sticky; top: 0; background: var(--panel); }
tbody tr:hover td { background: rgba(255,255,255,.04); }
code { white-space: nowrap; }
"""

    doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Weekly Results — Growth & Ratios</title>
  <style>
{agent_adda_dark_css()}
{extra_css}
  </style>
</head>
<body>
  <header>
    <h1>Weekly Results — Growth & Ratios</h1>
    <div class="sub">Generated {generated_on} · Source: PG Screener cache first (fallback to live scrape)</div>
  </header>
  <main class="grid">
    <section class="panel summary-panel wide">
      <h2>Executive Summary</h2>
      {narrative}
    </section>
    <section class="panel wide">
      <h2>Snapshot</h2>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              {th("Symbol")}
              {th("Latest period")}
              {th("Status")}
              {th("Data source")}
              {th("Sales (₹cr)", cls="num")}
              {th("Sales QoQ", cls="num")}
              {th("Sales YoY", cls="num")}
              {th("PAT (₹cr)", cls="num")}
              {th("PAT QoQ", cls="num")}
              {th("PAT YoY", cls="num")}
              {th("OPM%", cls="num")}
              {th("NPM%", cls="num")}
              {th("Int cov (x)", cls="num")}
              {th("D/E (x)", cls="num")}
              {th("OCF (₹cr)", cls="num")}
            </tr>
          </thead>
          <tbody>
            {''.join(table_rows)}
          </tbody>
        </table>
      </div>
    </section>
    <section class="panel wide">
      <h2>Notes</h2>
      <ul>{notes_html}</ul>
    </section>
  </main>
  <footer>{AGENT_ADDA_DISCLAIMER}</footer>
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate a weekly results growth/ratios report from cached financials.")
    p.add_argument(
        "--symbols",
        nargs="*",
        default=["MANIPALHOS", "LCL", "XTRANET", "FLEXITUFF", "INNOVACAP"],
        help="NSE symbols to include (default: last-week set)",
    )
    p.add_argument(
        "--ttl-hours",
        type=float,
        default=24.0,
        help="Max cache age hours for PG-first read (default 24). Use -1 to ignore freshness.",
    )
    p.add_argument(
        "--llm",
        action="store_true",
        help="Generate a narrative summary via OpenAI (requires OPENAI_API_KEY).",
    )
    p.add_argument(
        "--llm-model",
        default="gpt-4o-mini",
        help="OpenAI model id for narrative (default gpt-4o-mini).",
    )
    p.add_argument("--out", default="reports/latest/weekly_results_growth_ratios.html", help="Output HTML path.")
    args = p.parse_args(argv)

    ttl = None if args.ttl_hours < 0 else float(args.ttl_hours)
    rows, notes = _build_rows([s.strip().upper() for s in args.symbols if s.strip()], ttl_hours=ttl)
    out_html = ROOT / args.out
    out_csv = out_html.with_suffix(".csv")

    from datetime import datetime

    generated_on = datetime.now().isoformat(timespec="seconds")
    _write_csv(out_csv, rows)
    global _LLM_ENABLED, _LLM_MODEL
    _LLM_ENABLED = bool(args.llm)
    _LLM_MODEL = str(args.llm_model or "gpt-4o-mini")
    _write_html(out_html, rows, generated_on=generated_on, notes=notes)

    print(str(out_html))
    print(str(out_csv))
    return 0


_LLM_ENABLED = False
_LLM_MODEL = "gpt-4o-mini"


def _build_narrative(rows: list[dict[str, Any]]) -> str:
    """Return HTML for the narrative section; tries LLM, falls back deterministic."""
    llm_html = _llm_narrative_html(rows) if _LLM_ENABLED else None
    if llm_html:
        return llm_html
    return _fallback_narrative_html(rows)


def _fallback_narrative_html(rows: list[dict[str, Any]]) -> str:
    ok_rows = [r for r in rows if r.get("status") == "ok"]
    if not ok_rows:
        return "<p class='neutral'>No structured financial rows available to summarise.</p>"

    def pick_best(key: str, *, higher_is_better: bool = True) -> str:
        best = None
        for r in ok_rows:
            v = r.get(key)
            if not isinstance(v, (int, float)):
                continue
            if best is None:
                best = (v, r)
                continue
            if higher_is_better and v > best[0]:
                best = (v, r)
            if not higher_is_better and v < best[0]:
                best = (v, r)
        if not best:
            return "n/a"
        return f"{best[1].get('symbol')} ({best[0]:.1f}%)" if "pct" in key else f"{best[1].get('symbol')} ({best[0]:.2f}x)"

    growth = pick_best("sales_yoy_pct")
    margin = pick_best("npm_pct")
    leverage = pick_best("debt_to_equity_x")

    parts = [
        "<p class='lede'>This snapshot ranks sales growth, profitability and balance-sheet risk from the latest available tabular financials.</p>",
        "<div class='summary-columns'>",
        f"<div><h3>Leaders</h3><ul><li><span>Sales YoY:</span> <b>{growth}</b></li><li><span>NPM:</span> <b>{margin}</b></li></ul></div>",
        f"<div><h3>Risk</h3><ul><li><span>Highest D/E:</span> <b>{leverage}</b></li></ul></div>",
        "<div><h3>Interpretation</h3><ul>"
        "<li><span>QoQ can be noisy:</span> compare with YoY + margin stability.</li>"
        "<li><span>Working capital matters:</span> high debtor/inventory days often precede cash stress.</li>"
        "</ul></div>",
        "</div>",
        "<small>Summary is generated from the table above.</small>",
    ]
    return "".join(parts)


def _llm_narrative_html(rows: list[dict[str, Any]]) -> str | None:
    api_key = __import__("os").environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    ok_rows = [r for r in rows if r.get("status") == "ok"]
    if not ok_rows:
        return None

    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None

    payload_rows = []
    for r in ok_rows:
        payload_rows.append(
            {
                "symbol": r.get("symbol"),
                "latest_period": r.get("latest_period"),
                "sales_cr": r.get("sales_cr"),
                "sales_qoq_pct": r.get("sales_qoq_pct"),
                "sales_yoy_pct": r.get("sales_yoy_pct"),
                "pat_cr": r.get("pat_cr"),
                "pat_qoq_pct": r.get("pat_qoq_pct"),
                "pat_yoy_pct": r.get("pat_yoy_pct"),
                "opm_pct": r.get("opm_pct"),
                "npm_pct": r.get("npm_pct"),
                "interest_cov_x": r.get("interest_cov_x"),
                "debt_to_equity_x": r.get("debt_to_equity_x"),
                "ocf_cr": r.get("ocf_cr"),
            }
        )

    system = (
        "Write a concise, finance-operator executive summary for a weekly results dashboard. "
        "Be factual and tie every claim to the provided numbers. "
        "Output STRICT JSON with keys: headline (string), key_takeaways (array of 4 strings), "
        "risk_flags (array of 3 strings), what_to_watch (array of 3 strings)."
    )
    user = {"as_of": "latest available", "rows": payload_rows}
    try:
        client = OpenAI(api_key=api_key, timeout=25.0)
        resp = client.chat.completions.create(
            model=_LLM_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": __import__("json").dumps(user, default=str)},
            ],
            temperature=0.2,
        )
        content = (resp.choices[0].message.content or "").strip()
        data = __import__("json").loads(content)
    except Exception:
        return None

    def li(items: list[str]) -> str:
        return "<ul>" + "".join(f"<li>{__import__('html').escape(str(x))}</li>" for x in items) + "</ul>"

    headline = __import__("html").escape(str(data.get("headline", "")))
    takeaways = data.get("key_takeaways") or []
    risks = data.get("risk_flags") or []
    watch = data.get("what_to_watch") or []

    return (
        f"<p class='lede'>{headline}</p>"
        "<div class='summary-columns'>"
        f"<div><h3>Takeaways</h3>{li(list(takeaways)[:6])}</div>"
        f"<div><h3>Risks</h3>{li(list(risks)[:6])}</div>"
        f"<div><h3>Watch Next</h3>{li(list(watch)[:6])}</div>"
        "</div>"
        "<small>Summary generated from the table above.</small>"
    )


if __name__ == "__main__":
    raise SystemExit(main())
