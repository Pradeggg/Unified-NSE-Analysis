#!/usr/bin/env python3
"""
fund_recent_filings.py — NSE filings for Agent Adda fund holdings
===============================================================

Reads  : data/fund_holdings.json (symbols in smallcap + midcap books)
Fetches: NSE corporate announcements via https://www.nseindia.com/api/corporate-announcements
Writes : reports/latest/fund_filings_last_{days}d.json + .csv

Note: This script requires outbound network access to nseindia.com.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from curl_cffi import requests as cffi_requests  # type: ignore
except Exception:  # pragma: no cover
    cffi_requests = None

import requests


ROOT = Path(__file__).resolve().parent.parent
HOLDINGS_FILE = ROOT / "data" / "fund_holdings.json"
OUT_DIR = ROOT / "reports" / "latest"

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def _load_fund_symbols() -> list[str]:
    payload = json.loads(HOLDINGS_FILE.read_text(encoding="utf-8"))
    symbols: set[str] = set()
    for book in ("smallcap", "midcap"):
        for sym in (payload.get(book) or {}).keys():
            if sym.startswith("_"):
                continue
            symbols.add(sym.strip().upper())
    return sorted(symbols)


def _parse_nse_dt(s: str) -> datetime | None:
    if not s:
        return None
    s = " ".join(str(s).split())
    # Common NSE formats observed in corp-info/corporate-announcements payloads.
    for fmt in (
        "%d-%b-%Y %H:%M:%S",
        "%d-%b-%Y %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except Exception:
            continue
    return None


def _attachment_url(att: str) -> str:
    if not att:
        return ""
    if att.startswith("http://") or att.startswith("https://"):
        return att
    return f"https://nsearchives.nseindia.com/corporate/{att.lstrip('/')}"


@dataclass(frozen=True)
class FilingRow:
    symbol: str
    broadcast_dt: str
    subject: str
    details: str
    attachment_url: str
    source: str


def _new_session():
    if cffi_requests is not None:
        sess: Any = cffi_requests.Session(impersonate="chrome120")
    else:
        sess = requests.Session()
    sess.headers.update(NSE_HEADERS)
    return sess


def _warmup(sess) -> None:
    # NSE often requires cookies set by visiting the main site first.
    try:
        sess.get("https://www.nseindia.com/", timeout=10)
        sess.get("https://www.nseindia.com/market-data/live-equity-market?symbol=NIFTY+50", timeout=10)
    except Exception:
        pass


def fetch_corporate_announcements(sess, symbol: str) -> list[dict[str, Any]]:
    url = f"https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={symbol}"
    r = sess.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):
        items = data.get("data", data.get("items", []))
        if isinstance(items, list):
            return items
    if isinstance(data, list):
        return data
    return []


def normalize_items(symbol: str, items: list[dict[str, Any]]) -> list[FilingRow]:
    rows: list[FilingRow] = []
    for it in items:
        subject = (it.get("subject") or it.get("sm_name") or it.get("desc") or "").strip()
        details = (it.get("desc") or it.get("details") or it.get("attchmntText") or "").strip()
        broadcast = (it.get("an_dt") or it.get("dt") or it.get("exchdisstime") or it.get("sort_date") or "").strip()
        att = (it.get("attchmntFile") or it.get("attachment") or it.get("file") or "").strip()
        rows.append(
            FilingRow(
                symbol=symbol,
                broadcast_dt=broadcast,
                subject=subject[:200],
                details=details[:600],
                attachment_url=_attachment_url(att),
                source="nseindia.com/api/corporate-announcements",
            )
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=14, help="Lookback window (default 14)")
    ap.add_argument("--sleep", type=float, default=0.2, help="Sleep between NSE calls (default 0.2s)")
    ap.add_argument("--no-fetch", action="store_true", help="Only print symbols; do not fetch")
    args = ap.parse_args(argv)

    symbols = _load_fund_symbols()
    if args.no_fetch:
        print(f"fund_symbols={len(symbols)}")
        print(",".join(symbols))
        return 0

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=int(args.days))

    sess = _new_session()
    _warmup(sess)

    all_rows: list[FilingRow] = []
    errors: dict[str, str] = {}
    for i, sym in enumerate(symbols, 1):
        try:
            items = fetch_corporate_announcements(sess, sym)
            rows = normalize_items(sym, items)
            # Filter to lookback window where we can parse a date
            for r in rows:
                dt = _parse_nse_dt(r.broadcast_dt)
                if dt is None:
                    continue
                if dt >= cutoff:
                    all_rows.append(r)
        except Exception as exc:
            errors[sym] = f"{type(exc).__name__}: {exc}"
        if args.sleep:
            time.sleep(float(args.sleep))
        print(f"[{i}/{len(symbols)}] {sym}: ok" if sym not in errors else f"[{i}/{len(symbols)}] {sym}: error")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / f"fund_filings_last_{int(args.days)}d.json"
    out_csv = OUT_DIR / f"fund_filings_last_{int(args.days)}d.csv"

    payload = {
        "as_of_utc": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "days": int(args.days),
        "symbols": symbols,
        "count": len(all_rows),
        "errors": errors,
        "rows": [r.__dict__ for r in sorted(all_rows, key=lambda x: (x.symbol, x.broadcast_dt), reverse=True)],
    }
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["symbol", "broadcast_dt", "subject", "details", "attachment_url", "source"],
        )
        w.writeheader()
        for r in payload["rows"]:
            w.writerow(r)

    print(f"\nWrote: {out_json}")
    print(f"Wrote: {out_csv}")
    if errors:
        print(f"Errors: {len(errors)} symbols (see JSON)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

