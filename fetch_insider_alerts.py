#!/usr/bin/env python3
"""Promoter/Insider activity alert generator (P1-4).

Downloads NSE bulk deals, block deals, and insider trading disclosures,
classifies alerts, and exposes an enrichment function for sector_rotation_report.py.

Alert types:
  PROMOTER_BUYING   — promoter/promoter group bought shares (open market/preferential)
  PROMOTER_SELLING  — promoter sold shares
  PROMOTER_PLEDGE   — promoter pledged/revoked pledge on shares
  INSIDER_BUY       — director/KMP bought shares
  INSIDER_SELL      — director/KMP sold shares
  BULK_DEAL_BUY     — large investor bought > 0.5% in single session
  BULK_DEAL_SELL    — large investor sold > 0.5% in single session

Data sources (NSE, free):
  - Bulk deals:  https://archives.nseindia.com/content/equities/bulk.csv
  - Block deals: https://archives.nseindia.com/content/equities/block.csv
  - Insider PIT: https://www.nseindia.com/api/corporates-pit?index=equities&from_date=...&to_date=...

Cache: data/_insider_cache/ directory; output: data/insider_alerts.csv
TTL: 18 hours (re-fetch if stale)

Usage:
  python fetch_insider_alerts.py                    # fetch & compute
  python fetch_insider_alerts.py --lookback 30      # last 30 days
  python fetch_insider_alerts.py --force             # ignore cache

  # As module
  from fetch_insider_alerts import enrich_with_insider_alerts
  candidates = enrich_with_insider_alerts(candidates)
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# ── Paths ──
ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "data" / "_insider_cache"
ALERTS_CSV = ROOT / "data" / "insider_alerts.csv"
CACHE_TTL_HOURS = 18

# ── NSE access config ──
_NSE_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
_COOKIE_JAR = ROOT / "data" / "_fno_cache" / "_nse_cookies.txt"
_SLEEP = 2  # seconds between NSE calls


# ─────────────────────────────────────────────
# SECTION 1: DATA FETCHING
# ─────────────────────────────────────────────

def _ensure_nse_cookies() -> bool:
    """Shared NSE cookie jar setup (reuses fetch_fno_data pattern)."""
    _COOKIE_JAR.parent.mkdir(parents=True, exist_ok=True)
    if _COOKIE_JAR.exists():
        age_min = (time.time() - _COOKIE_JAR.stat().st_mtime) / 60
        if age_min < 10:
            return True
    cmd = [
        "curl", "-sS", "-L", "--http1.1",
        "-c", str(_COOKIE_JAR), "-o", "/dev/null", "--max-time", "30",
        "-H", f"User-Agent: {_NSE_UA}",
        "-H", "Accept: text/html,application/xhtml+xml",
        "https://www.nseindia.com",
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        return _COOKIE_JAR.exists() and _COOKIE_JAR.stat().st_size > 0
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"  Cookie setup failed: {exc}")
        return False


def _curl_get(url: str, out_path: Path, timeout: int = 30, use_cookies: bool = False) -> bool:
    """Download a URL via curl subprocess. Returns True on HTTP 200 with content."""
    if use_cookies:
        _ensure_nse_cookies()
    cmd = [
        "curl", "-sS", "-L", "--http1.1",
        "-o", str(out_path),
        "-w", "%{http_code}",
        "--max-time", str(timeout),
        "-H", f"User-Agent: {_NSE_UA}",
        "-H", "Accept: */*",
    ]
    if use_cookies:
        cmd += ["-b", str(_COOKIE_JAR)]
    cmd.append(url)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
        code = result.stdout.strip()
        if code == "200" and out_path.exists() and out_path.stat().st_size > 50:
            return True
        if out_path.exists():
            out_path.unlink()
        return False
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"  curl failed for {url}: {exc}")
        if out_path.exists():
            out_path.unlink()
        return False


def fetch_bulk_deals() -> pd.DataFrame:
    """Fetch NSE bulk deals CSV (today's data)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    cache_file = CACHE_DIR / f"bulk_{today_str}.csv"

    if cache_file.exists() and cache_file.stat().st_size > 50:
        try:
            return pd.read_csv(cache_file)
        except Exception:
            pass

    tmp = CACHE_DIR / "_bulk_tmp.csv"
    url = "https://archives.nseindia.com/content/equities/bulk.csv"
    print(f"  Fetching bulk deals: {url}")
    if not _curl_get(url, tmp):
        print("  Bulk deals not available.")
        return pd.DataFrame()

    try:
        df = pd.read_csv(tmp)
        df.columns = [c.strip() for c in df.columns]
        # Standardise column names
        col_map = {
            "Symbol": "SYMBOL", "Date": "DATE",
            "Client Name": "ENTITY", "Buy/Sell": "SIDE",
            "Quantity Traded": "QTY",
            "Trade Price / Wght. Avg. Price": "PRICE",
        }
        df = df.rename(columns=col_map)
        df["SOURCE"] = "BULK_DEAL"
        df.to_csv(cache_file, index=False)
        return df
    except Exception as exc:
        print(f"  Failed to parse bulk deals: {exc}")
        return pd.DataFrame()
    finally:
        if tmp.exists():
            tmp.unlink()


def fetch_block_deals() -> pd.DataFrame:
    """Fetch NSE block deals CSV (today's data)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    cache_file = CACHE_DIR / f"block_{today_str}.csv"

    if cache_file.exists() and cache_file.stat().st_size > 50:
        try:
            return pd.read_csv(cache_file)
        except Exception:
            pass

    tmp = CACHE_DIR / "_block_tmp.csv"
    url = "https://archives.nseindia.com/content/equities/block.csv"
    print(f"  Fetching block deals: {url}")
    if not _curl_get(url, tmp):
        print("  Block deals not available.")
        return pd.DataFrame()

    try:
        df = pd.read_csv(tmp)
        df.columns = [c.strip() for c in df.columns]
        # Check for "NO RECORDS" sentinel
        if df.empty or (len(df) == 1 and "NO RECORDS" in str(df.iloc[0].values)):
            return pd.DataFrame()
        col_map = {
            "Symbol": "SYMBOL", "Date": "DATE",
            "Client Name": "ENTITY", "Buy/Sell": "SIDE",
            "Quantity Traded": "QTY",
            "Trade Price / Wght. Avg. Price": "PRICE",
        }
        df = df.rename(columns=col_map)
        df["SOURCE"] = "BLOCK_DEAL"
        df.to_csv(cache_file, index=False)
        return df
    except Exception as exc:
        print(f"  Failed to parse block deals: {exc}")
        return pd.DataFrame()
    finally:
        if tmp.exists():
            tmp.unlink()


def fetch_insider_pit(lookback_days: int = 30) -> pd.DataFrame:
    """Fetch NSE insider trading (PIT) disclosures via API.

    PG: This is the richest source — covers promoter buys/sells, pledges,
    director transactions, ESOPs, etc. The API accepts a date range.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    cache_file = CACHE_DIR / f"pit_{today_str}.json"

    if cache_file.exists() and cache_file.stat().st_size > 50:
        try:
            with open(cache_file) as f:
                records = json.load(f)
            if records:
                return pd.DataFrame(records)
        except Exception:
            pass

    _ensure_nse_cookies()
    from_date = (today - timedelta(days=lookback_days)).strftime("%d-%m-%Y")
    to_date = today.strftime("%d-%m-%Y")
    url = (
        f"https://www.nseindia.com/api/corporates-pit"
        f"?index=equities&from_date={from_date}&to_date={to_date}"
    )

    tmp = CACHE_DIR / "_pit_tmp.json"
    print(f"  Fetching insider PIT disclosures: {from_date} → {to_date}")
    if not _curl_get(url, tmp, use_cookies=True):
        print("  Insider PIT data not available.")
        return pd.DataFrame()

    try:
        with open(tmp) as f:
            raw = json.load(f)
        records = raw.get("data", []) if isinstance(raw, dict) else raw
        if not records:
            print("  No insider PIT records in response.")
            return pd.DataFrame()

        # Cache the parsed records
        with open(cache_file, "w") as f:
            json.dump(records, f)

        df = pd.DataFrame(records)
        print(f"  Insider PIT: {len(df)} disclosures loaded.")
        return df
    except Exception as exc:
        print(f"  Failed to parse PIT data: {exc}")
        return pd.DataFrame()
    finally:
        if tmp.exists():
            tmp.unlink()


# ─────────────────────────────────────────────
# SECTION 2: ALERT CLASSIFICATION
# ─────────────────────────────────────────────

def _classify_pit_alerts(pit_df: pd.DataFrame) -> pd.DataFrame:
    """Classify insider PIT disclosures into alert types.

    PG: personCategory tells us who (Promoter/Director/KMP/Other);
    tdpTransactionType tells us what (Buy/Sell/Pledge/Revoke).
    """
    if pit_df.empty:
        return pd.DataFrame(columns=[
            "DATE", "SYMBOL", "ALERT_TYPE", "ENTITY", "QTY", "VALUE_CR",
            "CATEGORY", "DETAIL", "SOURCE",
        ])

    alerts = []
    for _, r in pit_df.iterrows():
        sym = str(r.get("symbol", "")).strip()
        if not sym:
            continue

        person_cat = str(r.get("personCategory", "")).strip().lower()
        txn_type = str(r.get("tdpTransactionType", "")).strip().lower()
        acq_mode = str(r.get("acqMode", "")).strip()
        entity = str(r.get("acqName", "")).strip()
        sec_val = r.get("secVal", 0)
        sec_acq = r.get("secAcq", 0)

        # Parse value in crores
        try:
            val_cr = float(sec_val) / 1e7 if sec_val else 0
        except (ValueError, TypeError):
            val_cr = 0
        try:
            qty = int(float(sec_acq)) if sec_acq else 0
        except (ValueError, TypeError):
            qty = 0

        # Classify based on person category + transaction type
        is_promoter = "promoter" in person_cat
        is_director = "director" in person_cat or "kmp" in person_cat.lower()

        if "pledge" in txn_type or "pledge" in acq_mode.lower():
            alert_type = "PROMOTER_PLEDGE"
        elif "buy" in txn_type or "acquisition" in txn_type:
            if is_promoter:
                alert_type = "PROMOTER_BUYING"
            elif is_director:
                alert_type = "INSIDER_BUY"
            else:
                continue  # skip ESOPs and other non-significant buys
        elif "sell" in txn_type or "disposal" in txn_type:
            if is_promoter:
                alert_type = "PROMOTER_SELLING"
            elif is_director:
                alert_type = "INSIDER_SELL"
            else:
                continue
        else:
            continue  # skip unclear transaction types

        # Parse date
        date_str = str(r.get("acqfromDt", r.get("date", ""))).strip()
        try:
            dt = pd.to_datetime(date_str, dayfirst=True)
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            date_str = ""

        detail = f"{acq_mode}" if acq_mode and acq_mode != "-" else ""

        alerts.append({
            "DATE": date_str,
            "SYMBOL": sym,
            "ALERT_TYPE": alert_type,
            "ENTITY": entity[:60],
            "QTY": qty,
            "VALUE_CR": round(val_cr, 2),
            "CATEGORY": r.get("personCategory", ""),
            "DETAIL": detail,
            "SOURCE": "PIT",
        })

    return pd.DataFrame(alerts) if alerts else pd.DataFrame(columns=[
        "DATE", "SYMBOL", "ALERT_TYPE", "ENTITY", "QTY", "VALUE_CR",
        "CATEGORY", "DETAIL", "SOURCE",
    ])


def _classify_bulk_block_alerts(deals_df: pd.DataFrame) -> pd.DataFrame:
    """Classify bulk/block deals into alert types."""
    if deals_df.empty:
        return pd.DataFrame(columns=[
            "DATE", "SYMBOL", "ALERT_TYPE", "ENTITY", "QTY", "VALUE_CR",
            "CATEGORY", "DETAIL", "SOURCE",
        ])

    alerts = []
    for _, r in deals_df.iterrows():
        sym = str(r.get("SYMBOL", "")).strip()
        if not sym:
            continue

        side = str(r.get("SIDE", "")).strip().upper()
        entity = str(r.get("ENTITY", "")).strip()
        source = str(r.get("SOURCE", "BULK_DEAL"))

        try:
            qty = int(float(r.get("QTY", 0)))
        except (ValueError, TypeError):
            qty = 0
        try:
            price = float(r.get("PRICE", 0))
        except (ValueError, TypeError):
            price = 0

        val_cr = round((qty * price) / 1e7, 2) if qty and price else 0

        if "BUY" in side:
            alert_type = "BULK_DEAL_BUY"
        elif "SELL" in side:
            alert_type = "BULK_DEAL_SELL"
        else:
            continue

        date_str = str(r.get("DATE", "")).strip()
        try:
            dt = pd.to_datetime(date_str, dayfirst=True)
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            pass

        alerts.append({
            "DATE": date_str,
            "SYMBOL": sym,
            "ALERT_TYPE": alert_type,
            "ENTITY": entity[:60],
            "QTY": qty,
            "VALUE_CR": val_cr,
            "CATEGORY": source.replace("_", " ").title(),
            "DETAIL": f"@ ₹{price:.2f}" if price else "",
            "SOURCE": source,
        })

    return pd.DataFrame(alerts) if alerts else pd.DataFrame(columns=[
        "DATE", "SYMBOL", "ALERT_TYPE", "ENTITY", "QTY", "VALUE_CR",
        "CATEGORY", "DETAIL", "SOURCE",
    ])


# ─────────────────────────────────────────────
# SECTION 3: SIGNAL AGGREGATION
# ─────────────────────────────────────────────

# PG: alert severity/sentiment score for ranking
_ALERT_SENTIMENT = {
    "PROMOTER_BUYING":   +2,
    "INSIDER_BUY":       +1,
    "BULK_DEAL_BUY":     +1,
    "PROMOTER_SELLING":  -2,
    "INSIDER_SELL":      -1,
    "BULK_DEAL_SELL":    -1,
    "PROMOTER_PLEDGE":   -1,
}


def aggregate_alerts(alerts_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-symbol alerts into a summary for enrichment.

    Returns DataFrame: SYMBOL, INSIDER_ALERT (most significant alert type),
    INSIDER_SCORE (net sentiment), INSIDER_DETAIL (text summary for LLM).
    """
    if alerts_df.empty:
        return pd.DataFrame(columns=["SYMBOL", "INSIDER_ALERT", "INSIDER_SCORE", "INSIDER_DETAIL"])

    results = []
    for sym, group in alerts_df.groupby("SYMBOL"):
        # Net sentiment score
        score = sum(_ALERT_SENTIMENT.get(at, 0) for at in group["ALERT_TYPE"])

        # Most significant alert (highest absolute sentiment)
        best_alert = max(group["ALERT_TYPE"], key=lambda a: abs(_ALERT_SENTIMENT.get(a, 0)))

        # Build detail string for LLM narrative
        details = []
        for _, r in group.iterrows():
            at = r["ALERT_TYPE"]
            ent = r.get("ENTITY", "")[:30]
            val = r.get("VALUE_CR", 0)
            val_str = f"₹{val:.1f}Cr" if val > 0.1 else ""
            details.append(f"{at.replace('_', ' ').title()}: {ent} {val_str}".strip())

        detail_str = "; ".join(details[:3])  # limit to 3 alerts for prompt brevity
        if len(details) > 3:
            detail_str += f" (+{len(details)-3} more)"

        results.append({
            "SYMBOL": sym,
            "INSIDER_ALERT": best_alert,
            "INSIDER_SCORE": score,
            "INSIDER_DETAIL": detail_str,
        })

    return pd.DataFrame(results)


def generate_insider_alerts(lookback_days: int = 30) -> pd.DataFrame:
    """Full pipeline: fetch all sources → classify → aggregate → save.

    Returns aggregated alerts DataFrame.
    """
    print(f"\n{'='*60}")
    print(f"Insider/Promoter Alert Generation (last {lookback_days} days)")
    print(f"{'='*60}")

    all_alerts = []

    # 1. Bulk deals
    bulk = fetch_bulk_deals()
    if not bulk.empty:
        bulk_alerts = _classify_bulk_block_alerts(bulk)
        if not bulk_alerts.empty:
            all_alerts.append(bulk_alerts)
            print(f"  Bulk deals: {len(bulk_alerts)} alerts")
    time.sleep(_SLEEP)

    # 2. Block deals
    block = fetch_block_deals()
    if not block.empty:
        block_alerts = _classify_bulk_block_alerts(block)
        if not block_alerts.empty:
            all_alerts.append(block_alerts)
            print(f"  Block deals: {len(block_alerts)} alerts")
    time.sleep(_SLEEP)

    # 3. Insider PIT disclosures
    pit = fetch_insider_pit(lookback_days=lookback_days)
    if not pit.empty:
        pit_alerts = _classify_pit_alerts(pit)
        if not pit_alerts.empty:
            all_alerts.append(pit_alerts)
            print(f"  Insider PIT: {len(pit_alerts)} alerts")

    if not all_alerts:
        print("  No insider alerts found.")
        return pd.DataFrame(columns=["SYMBOL", "INSIDER_ALERT", "INSIDER_SCORE", "INSIDER_DETAIL"])

    combined = pd.concat(all_alerts, ignore_index=True)
    print(f"  Total raw alerts: {len(combined)}")
    print(f"  Alert breakdown: {combined['ALERT_TYPE'].value_counts().to_dict()}")

    # Save raw alerts
    ALERTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(ALERTS_CSV, index=False)

    # Aggregate per symbol
    aggregated = aggregate_alerts(combined)
    print(f"  Aggregated: {len(aggregated)} symbols with alerts")

    # Save aggregated
    agg_csv = ROOT / "data" / "insider_alerts_agg.csv"
    aggregated.to_csv(agg_csv, index=False)
    print(f"  Saved → {ALERTS_CSV} (raw), {agg_csv.name} (aggregated)")

    return aggregated


# ─────────────────────────────────────────────
# SECTION 4: INTEGRATION API (for sector_rotation_report.py)
# ─────────────────────────────────────────────

def _cache_is_fresh() -> bool:
    agg_csv = ROOT / "data" / "insider_alerts_agg.csv"
    if not agg_csv.exists():
        return False
    age_hours = (time.time() - agg_csv.stat().st_mtime) / 3600
    return age_hours < CACHE_TTL_HOURS


def load_insider_alerts() -> pd.DataFrame:
    """Load aggregated insider alerts — from cache if fresh, otherwise regenerate."""
    agg_csv = ROOT / "data" / "insider_alerts_agg.csv"
    if _cache_is_fresh():
        try:
            df = pd.read_csv(agg_csv)
            if not df.empty:
                print(f"  Insider alerts: loaded {len(df)} symbols from cache.")
                return df
        except Exception:
            pass
    return generate_insider_alerts()


def enrich_with_insider_alerts(candidates: pd.DataFrame) -> pd.DataFrame:
    """Merge insider alerts into the candidates DataFrame.

    Adds columns: INSIDER_ALERT, INSIDER_SCORE, INSIDER_DETAIL.
    Non-alert stocks get None values (graceful degradation).

    Called from sector_rotation_report.py → generate_report().
    """
    if candidates.empty or "SYMBOL" not in candidates.columns:
        return candidates

    try:
        alerts = load_insider_alerts()
    except Exception as exc:
        print(f"  Insider alert enrichment skipped ({exc}). Filling with None.")
        alerts = pd.DataFrame()

    alert_cols = ["INSIDER_ALERT", "INSIDER_SCORE", "INSIDER_DETAIL"]

    if alerts.empty:
        for col in alert_cols:
            candidates[col] = None
        return candidates

    merge_cols = ["SYMBOL"] + [c for c in alert_cols if c in alerts.columns]
    result = candidates.merge(alerts[merge_cols], on="SYMBOL", how="left")

    for col in alert_cols:
        if col not in result.columns:
            result[col] = None

    n_enriched = result["INSIDER_ALERT"].notna().sum()
    print(f"  Insider enrichment: {n_enriched}/{len(result)} candidates have alerts.")

    return result


# ─────────────────────────────────────────────
# SECTION 5: HTML BADGE (for render_html_interactive)
# ─────────────────────────────────────────────

def insider_badge_html(alert_type: str, score: float | None = None,
                       detail: str = "") -> str:
    """Return an HTML badge for the insider alert."""
    at = str(alert_type or "").strip().upper()
    if not at or at in ("", "NAN", "NONE"):
        return '<span class="ins ins-na">—</span>'

    label_map = {
        "PROMOTER_BUYING":   ("🟢 Promoter Buy", "ins-bull"),
        "INSIDER_BUY":       ("🟢 Insider Buy",  "ins-bull"),
        "BULK_DEAL_BUY":     ("🔵 Bulk Buy",     "ins-info"),
        "PROMOTER_SELLING":  ("🔴 Promoter Sell", "ins-bear"),
        "INSIDER_SELL":      ("🟠 Insider Sell",  "ins-warn"),
        "BULK_DEAL_SELL":    ("🟠 Bulk Sell",     "ins-warn"),
        "PROMOTER_PLEDGE":   ("⚠️ Pledge",        "ins-warn"),
    }
    label, css_class = label_map.get(at, (at.replace("_", " ").title(), "ins-neutral"))

    detail_html = ""
    if detail and str(detail) not in ("", "nan", "None"):
        # Truncate for display
        short = str(detail)[:80]
        detail_html = f'<div class="ins-detail">{short}</div>'

    return f'<span class="ins {css_class}">{label}</span>{detail_html}'


# CSS rules for injection into sector_rotation_report.py
INSIDER_CSS = """
/* ---- INSIDER/PROMOTER ALERT BADGES (P1-4) ---- */
.ins{display:inline-block;padding:2px 7px;border-radius:10px;font-size:9.5px;font-weight:700;white-space:nowrap}
.ins-bull{background:#dcfce7;color:#15803d;border:1px solid #86efac}
.ins-info{background:#dbeafe;color:#1e40af;border:1px solid #93c5fd}
.ins-bear{background:#fee2e2;color:#991b1b;border:1px solid #fca5a5}
.ins-warn{background:#ffedd5;color:#c2410c;border:1px solid #fdba74}
.ins-neutral{background:#f1f5f9;color:#64748b}
.ins-na{color:#cbd5e1;font-size:9px}
.ins-detail{font-size:9px;color:#64748b;margin-top:2px;line-height:1.3;max-width:180px;overflow:hidden;text-overflow:ellipsis}
"""


# ─────────────────────────────────────────────
# SECTION 6: CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch NSE insider/promoter alerts.")
    parser.add_argument("--lookback", type=int, default=30, help="Days to look back (default: 30).")
    parser.add_argument("--force", action="store_true", help="Ignore cache and re-fetch.")
    args = parser.parse_args()

    if args.force:
        for f in [ALERTS_CSV, ROOT / "data" / "insider_alerts_agg.csv"]:
            if f.exists():
                f.unlink()

    alerts = generate_insider_alerts(lookback_days=args.lookback)

    if alerts.empty:
        print("\nNo insider alerts generated.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"Insider Alert Summary ({len(alerts)} symbols)")
    print(f"{'='*60}")
    if "INSIDER_ALERT" in alerts.columns:
        print(alerts["INSIDER_ALERT"].value_counts().to_string())
    print()
    # Show top positive and negative alerts
    if "INSIDER_SCORE" in alerts.columns:
        pos = alerts[alerts["INSIDER_SCORE"] > 0].nlargest(5, "INSIDER_SCORE")
        neg = alerts[alerts["INSIDER_SCORE"] < 0].nsmallest(5, "INSIDER_SCORE")
        if not pos.empty:
            print("Top POSITIVE alerts:")
            for _, r in pos.iterrows():
                print(f"  {r['SYMBOL']:12s} score={r['INSIDER_SCORE']:+d}  {r['INSIDER_ALERT']}")
        if not neg.empty:
            print("Top NEGATIVE alerts:")
            for _, r in neg.iterrows():
                print(f"  {r['SYMBOL']:12s} score={r['INSIDER_SCORE']:+d}  {r['INSIDER_ALERT']}")


if __name__ == "__main__":
    main()
