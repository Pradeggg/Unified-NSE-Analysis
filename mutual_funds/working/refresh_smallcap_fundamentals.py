from __future__ import annotations

import argparse
import csv
import html
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg2


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal.financials_cache import DEFAULT_DSN, log_refresh_run, read_financials, to_number, upsert_screener_payload
from terminal.web_research import scrape_screener_in


INPUT = ROOT / "Mutual Funds" / "extracted" / "agent_adda_smallcap_policy_gate_20260806.csv"
OUT_CSV = ROOT / "Mutual Funds" / "extracted" / "smallcap_fundamental_refresh_audit_20260806.csv"
OUT_JSON = ROOT / "Mutual Funds" / "extracted" / "smallcap_fundamental_refresh_audit_20260806.json"
OUT_HTML = ROOT / "Mutual Funds" / "reports" / "smallcap_fundamental_refresh_audit_20260806.html"


ALIAS_OVERRIDES: dict[str, list[str]] = {
    "AVL": ["AVL", "ADITYAVISION"],
    "PRICOLLTD": ["PRICOLLTD", "PRICOL"],
}


def fnum(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            return to_number(str(value))
        except Exception:
            return None


def normalize_yfinance_fallback(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Map Yahoo-style fallback labels into the local Screener-like schema.

    The project cache writer understands rows such as ``Sales+`` and
    ``Net Profit+``. Some symbols return fallback tables with labels like
    ``Total Revenue`` and ``Net Income``. This keeps those rows loadable while
    still marking the source as fallback-normalized.
    """
    changed = False
    out = dict(payload)
    for section in ("quarterly", "annual_pl"):
        table = dict(out.get(section) or {})
        if not table:
            continue
        for key, values in list(table.items()):
            if key == "_headers" or not isinstance(values, list):
                continue
            cleaned = [_clean_fallback_value(v) for v in values]
            if cleaned != values:
                table[key] = cleaned
                changed = True
        if "Sales+" not in table and "Total Revenue" in table:
            table["Sales+"] = table["Total Revenue"]
            changed = True
        if "Operating Profit" not in table:
            if "Operating Income" in table:
                table["Operating Profit"] = table["Operating Income"]
                changed = True
            elif "Gross Profit" in table:
                table["Operating Profit"] = table["Gross Profit"]
                changed = True
        if "Net Profit+" not in table and "Net Income" in table:
            table["Net Profit+"] = table["Net Income"]
            changed = True
        if "OPM %" not in table and "Sales+" in table and "Operating Profit" in table:
            opm_values: list[str] = []
            for revenue_raw, op_raw in zip(table.get("Sales+") or [], table.get("Operating Profit") or []):
                revenue = to_number(str(revenue_raw))
                operating = to_number(str(op_raw))
                if revenue not in (None, 0) and operating is not None:
                    opm_values.append(f"{operating / revenue * 100:.2f}%")
                else:
                    opm_values.append("")
            if opm_values:
                table["OPM %"] = opm_values
                changed = True
        out[section] = table
    return out, changed


def _clean_fallback_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for token in ("₹", "Rs.", "Rs", "INR"):
        text = text.replace(token, "")
    text = text.replace(" Cr", "").replace("Cr", "").replace(" crores", "").replace("crores", "")
    text = text.replace(",", "").strip()
    return text


def latest_state(symbol: str) -> dict[str, Any]:
    fin = read_financials(symbol)
    quarters = sorted(fin.get("quarterly") or [], key=lambda r: str(r.get("period_end") or ""), reverse=True)
    annual = sorted(fin.get("annual") or [], key=lambda r: str(r.get("period_end") or ""), reverse=True)
    balance = sorted(fin.get("balance_sheet") or [], key=lambda r: str(r.get("period_end") or ""), reverse=True)
    cash = sorted(fin.get("cash_flow") or [], key=lambda r: str(r.get("period_end") or ""), reverse=True)
    latest_q = quarters[0] if quarters else {}
    latest_a = annual[0] if annual else {}
    fetched_at = None
    for section in (quarters, annual, balance, cash):
        for row in section:
            if row.get("fetched_at") and (fetched_at is None or row["fetched_at"] > fetched_at):
                fetched_at = row["fetched_at"]

    if latest_q.get("period_label") == "Jun 2026":
        status = "FRESH_JUN_2026"
    elif latest_q.get("period_label"):
        status = f"STALE_LATEST_{latest_q.get('period_label')}"
    elif latest_a.get("period_label"):
        status = f"PARTIAL_ANNUAL_ONLY_{latest_a.get('period_label')}"
    else:
        status = "NO_STRUCTURED_ROWS"

    return {
        "financial_status_after": status,
        "quarterly_rows_after": len(quarters),
        "annual_rows_after": len(annual),
        "balance_sheet_rows_after": len(balance),
        "cash_flow_rows_after": len(cash),
        "latest_quarter_after": latest_q.get("period_label", ""),
        "latest_annual_after": latest_a.get("period_label", ""),
        "latest_quarter_revenue_cr_after": fnum(latest_q.get("revenue")),
        "latest_quarter_pat_cr_after": fnum(latest_q.get("pat")),
        "latest_quarter_eps_after": fnum(latest_q.get("eps")),
        "latest_annual_revenue_cr_after": fnum(latest_a.get("revenue")),
        "latest_annual_pat_cr_after": fnum(latest_a.get("pat")),
        "latest_source_url_after": latest_q.get("source_url") or latest_a.get("source_url") or "",
        "latest_fetched_at_after": fetched_at.isoformat() if hasattr(fetched_at, "isoformat") else "",
    }


def candidate_symbols(mode: str) -> list[dict[str, str]]:
    df = pd.read_csv(INPUT)
    if mode == "all":
        part = df
    elif mode == "missing":
        part = df[df["financial_gate"].eq("FAIL_NO_CACHE")]
    else:
        part = df[~df["financial_gate"].eq("PASS")]
    return [
        {
            "symbol": str(row["symbol"]).strip().upper(),
            "company": str(row.get("company") or ""),
            "financial_gate_before": str(row.get("financial_gate") or ""),
            "latest_quarter_before": str(row.get("latest_quarter") or ""),
            "policy_rating_before": str(row.get("policy_rating") or ""),
        }
        for _, row in part.iterrows()
    ]


def scrape_with_aliases(symbol: str) -> tuple[str, dict[str, Any]]:
    aliases = ALIAS_OVERRIDES.get(symbol, [symbol])
    last_payload: dict[str, Any] = {}
    for alias in aliases:
        payload = scrape_screener_in(alias)
        last_payload = payload
        if not payload.get("error"):
            return alias, payload
    return aliases[-1], last_payload


def refresh_symbol(item: dict[str, str], conn: Any) -> dict[str, Any]:
    symbol = item["symbol"]
    before = latest_state(symbol)
    scraped_alias, payload = scrape_with_aliases(symbol)
    row: dict[str, Any] = {
        **item,
        "scraped_alias": scraped_alias,
        "scrape_source_url": payload.get("source_url", ""),
        "scrape_error": payload.get("error", ""),
        "normalized_yfinance_fallback": False,
        "rows_upserted": 0,
        "quarterly_rows_upserted": 0,
        "annual_rows_upserted": 0,
        "balance_sheet_rows_upserted": 0,
        "cash_flow_rows_upserted": 0,
        **{f"{k}_before": v for k, v in before.items()},
    }
    if payload.get("error"):
        row.update(latest_state(symbol))
        row["refresh_outcome"] = "SCRAPE_ERROR"
        return row

    normalized, normalized_flag = normalize_yfinance_fallback(payload)
    row["normalized_yfinance_fallback"] = normalized_flag
    source = "screener_yfinance_fallback_normalized" if normalized_flag else "screener"
    counts = upsert_screener_payload(symbol, normalized, source=source, conn=conn)
    row["quarterly_rows_upserted"] = counts.get("quarterly", 0)
    row["annual_rows_upserted"] = counts.get("annual", 0)
    row["balance_sheet_rows_upserted"] = counts.get("balance_sheet", 0)
    row["cash_flow_rows_upserted"] = counts.get("cash_flow", 0)
    row["rows_upserted"] = sum(counts.values())
    conn.commit()
    row.update(latest_state(symbol))

    status = row.get("financial_status_after", "")
    if status == "FRESH_JUN_2026":
        row["refresh_outcome"] = "LOADED_FRESH_JUN_2026"
    elif row["rows_upserted"]:
        row["refresh_outcome"] = "LOADED_BUT_STILL_STALE_OR_PARTIAL"
    else:
        row["refresh_outcome"] = "NO_STRUCTURED_ROWS"
    return row


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def write_outputs(rows: list[dict[str, Any]], *, mode: str) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    OUT_JSON.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    counts = pd.Series([r["refresh_outcome"] for r in rows]).value_counts().to_dict() if rows else {}
    generated = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    table = "\n".join(
        f"""
        <tr>
          <td><b>{esc(r['symbol'])}</b><span>{esc(r['company'])}</span></td>
          <td>{esc(r['refresh_outcome'])}<br><small>{esc(r['financial_status_after'])}</small></td>
          <td>{esc(r['financial_gate_before'])}<br><small>{esc(r['latest_quarter_before'])}</small></td>
          <td>{esc(r['latest_quarter_after'])}<br><small>Rev {esc(r['latest_quarter_revenue_cr_after'])} cr / PAT {esc(r['latest_quarter_pat_cr_after'])} cr</small></td>
          <td>{esc(r['rows_upserted'])}<br><small>Q {esc(r['quarterly_rows_upserted'])} / A {esc(r['annual_rows_upserted'])} / BS {esc(r['balance_sheet_rows_upserted'])} / CF {esc(r['cash_flow_rows_upserted'])}</small></td>
          <td>{esc(r['scraped_alias'])}<br><small>{esc(r['normalized_yfinance_fallback'])}</small></td>
          <td>{esc(r['scrape_error'])}</td>
          <td>{esc(r['latest_source_url_after'])}</td>
        </tr>
        """
        for r in rows
    )
    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Smallcap Fundamental Refresh Audit</title>
  <style>
    body {{ margin:0; font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif; color:#172129; background:#fbfcfc; }}
    header, main, footer {{ padding:24px 32px; }}
    header, footer {{ background:#fff; border-bottom:1px solid #d8e0e5; }}
    footer {{ border-top:1px solid #d8e0e5; border-bottom:0; color:#60707c; }}
    h1 {{ margin:0 0 8px; font-size:27px; letter-spacing:0; }}
    p {{ margin:0; color:#60707c; }}
    .summary {{ display:flex; flex-wrap:wrap; gap:10px; margin:16px 0; }}
    .metric {{ border:1px solid #d8e0e5; background:#f5f8f9; border-radius:8px; padding:10px 12px; }}
    .metric b {{ display:block; font-size:22px; color:#172129; }}
    .table-wrap {{ overflow:auto; border:1px solid #d8e0e5; border-radius:8px; background:#fff; }}
    table {{ border-collapse:collapse; width:100%; min-width:1250px; }}
    th, td {{ border-bottom:1px solid #d8e0e5; padding:9px 8px; text-align:left; vertical-align:top; }}
    th {{ background:#eef3f5; position:sticky; top:0; z-index:1; font-size:12px; }}
    td span, small {{ display:block; color:#60707c; }}
  </style>
</head>
<body>
  <header>
    <h1>Smallcap Fundamental Refresh Audit</h1>
    <p>Scoped refresh of Agent Adda Smallcap policy-gate symbols using the local Screener/Yahoo fallback scraper and PostgreSQL financial cache.</p>
    <div class="summary">
      <div class="metric"><b>{len(rows)}</b><span>Symbols attempted</span></div>
      <div class="metric"><b>{counts.get('LOADED_FRESH_JUN_2026', 0)}</b><span>Fresh Jun 2026 loaded</span></div>
      <div class="metric"><b>{counts.get('LOADED_BUT_STILL_STALE_OR_PARTIAL', 0)}</b><span>Loaded stale/partial</span></div>
      <div class="metric"><b>{counts.get('NO_STRUCTURED_ROWS', 0)}</b><span>No structured rows</span></div>
      <div class="metric"><b>{counts.get('SCRAPE_ERROR', 0)}</b><span>Scrape errors</span></div>
    </div>
    <p>Generated: {esc(generated)} | Mode: {esc(mode)}</p>
  </header>
  <main>
    <section class="table-wrap">
      <table>
        <thead>
          <tr><th>Stock</th><th>Outcome</th><th>Before</th><th>After Latest Quarter</th><th>Rows Upserted</th><th>Alias / Fallback</th><th>Error</th><th>Source URL</th></tr>
        </thead>
        <tbody>{table}</tbody>
      </table>
    </section>
  </main>
  <footer>
    This is structured-cache evidence only. Policy-grade selection still requires official filing, governance, valuation, liquidity, and entry-trigger checks.
  </footer>
</body>
</html>
"""
    OUT_HTML.write_text(html_text, encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    items = candidate_symbols(args.mode)
    if args.symbols:
        wanted = {s.strip().upper() for s in args.symbols.split(",") if s.strip()}
        existing = {item["symbol"] for item in items}
        for sym in wanted - existing:
            items.append(
                {
                    "symbol": sym,
                    "company": "",
                    "financial_gate_before": "MANUAL",
                    "latest_quarter_before": "",
                    "policy_rating_before": "",
                }
            )
        items = [item for item in items if item["symbol"] in wanted]

    rows: list[dict[str, Any]] = []
    attempted = loaded = total_rows = errors = 0
    conn = psycopg2.connect(args.dsn)
    conn.autocommit = False
    try:
        for idx, item in enumerate(items, 1):
            attempted += 1
            symbol = item["symbol"]
            try:
                row = refresh_symbol(item, conn)
                conn.commit()
                if row.get("rows_upserted", 0):
                    loaded += 1
                    total_rows += int(row["rows_upserted"])
                if row.get("scrape_error"):
                    errors += 1
                rows.append(row)
                print(
                    f"[{idx}/{len(items)}] {symbol:<12} {row['refresh_outcome']:<34} "
                    f"latest={row.get('latest_quarter_after') or '-':<8} rows={row.get('rows_upserted', 0)}"
                )
            except Exception as exc:
                conn.rollback()
                errors += 1
                row = {**item, "refresh_outcome": "ERROR", "scrape_error": f"{type(exc).__name__}: {exc}"}
                rows.append(row)
                print(f"[{idx}/{len(items)}] {symbol:<12} ERROR {exc}")
            if idx < len(items) and args.delay > 0:
                time.sleep(args.delay)
    finally:
        conn.close()

    write_outputs(rows, mode=args.mode)
    try:
        run_id = log_refresh_run(
            "smallcap_fundamental_refresh",
            symbols_attempted=attempted,
            symbols_loaded=loaded,
            rows_upserted=total_rows,
            errors=errors,
            notes=f"mode={args.mode}; outputs={OUT_CSV.name},{OUT_HTML.name}",
            dsn=args.dsn,
        )
    except Exception as exc:
        run_id = f"log_failed:{type(exc).__name__}:{exc}"
    print(f"\nWrote {OUT_CSV}")
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_HTML}")
    print(f"attempted={attempted} loaded={loaded} rows_upserted={total_rows} errors={errors} run_id={run_id}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["stale_or_missing", "missing", "all"], default="stale_or_missing")
    parser.add_argument("--symbols", default="", help="Optional comma-separated symbols override")
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    args = parser.parse_args()
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
