#!/usr/bin/env python3
"""Corporate event alert engine (E4).

Fetches upcoming corporate events from NSE for all candidates:
  RESULT_ANNOUNCEMENT  — quarterly/annual result date
  EX_DIVIDEND          — dividend ex-date (price drop expected)
  BONUS                — bonus share ex-date
  SPLIT                — stock split ex-date
  RIGHTS               — rights issue open/close
  BUYBACK              — buyback open/close
  AGM                  — Annual General Meeting

Trading implications injected:
  +3  INVESTMENT_SCORE bonus : buyback announced above current price (floor)
  +2                         : result in 5-14 days + earnings acceleration
  -1                         : result in next 3 days (short-term uncertainty)

Data source: NSE corporate actions API (free, requires browser cookies)
  https://www.nseindia.com/api/corporates-corporateActions?index=equities
  https://www.nseindia.com/api/event-calendar

Cache: data/corporate_events.csv  (TTL: 24h)
Output columns added to candidates:
  NEXT_EVENT        — event type string (e.g. 'RESULT_ANNOUNCEMENT')
  NEXT_EVENT_DATE   — date string YYYY-MM-DD
  NEXT_EVENT_DAYS   — integer days until event
  EVENT_DETAIL      — human-readable string for HTML/LLM

Usage:
  python fetch_corporate_events.py                  # fetch and print
  python fetch_corporate_events.py --force          # ignore cache
  python fetch_corporate_events.py --symbol HDFC    # single symbol

  # As module
  from fetch_corporate_events import enrich_with_events
  candidates = enrich_with_events(candidates)
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
EVENTS_CSV = ROOT / "data" / "corporate_events.csv"
CACHE_DIR = ROOT / "data" / "_insider_cache"   # reuse existing cache dir
CACHE_TTL_HOURS = 24

_NSE_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_COOKIE_JAR = ROOT / "data" / "_fno_cache" / "_nse_cookies.txt"
_SLEEP = 2


# ─────────────────────────────────────────────
# SECTION 1: NSE ACCESS HELPERS
# ─────────────────────────────────────────────

def _ensure_nse_cookies() -> bool:
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
    except (subprocess.TimeoutExpired, OSError):
        return False


def _curl_json(url: str, timeout: int = 30) -> dict | list | None:
    """Fetch JSON from NSE API via curl subprocess. Returns None on failure."""
    _ensure_nse_cookies()
    tmp = CACHE_DIR / "_evt_tmp.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "curl", "-sS", "-L", "--http1.1",
        "-o", str(tmp),
        "-w", "%{http_code}",
        "--max-time", str(timeout),
        "-H", f"User-Agent: {_NSE_UA}",
        "-H", "Accept: application/json, text/plain, */*",
        "-H", "Referer: https://www.nseindia.com/",
        "-b", str(_COOKIE_JAR),
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
        code = result.stdout.strip()
        if code != "200" or not tmp.exists() or tmp.stat().st_size < 10:
            if tmp.exists():
                tmp.unlink()
            return None
        with open(tmp) as f:
            data = json.load(f)
        return data
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
        return None
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


# ─────────────────────────────────────────────
# SECTION 2: DATA FETCHING
# ─────────────────────────────────────────────

# Map NSE purpose strings to normalised event types
_PURPOSE_MAP = {
    "dividend":            "EX_DIVIDEND",
    "interim dividend":    "EX_DIVIDEND",
    "final dividend":      "EX_DIVIDEND",
    "special dividend":    "EX_DIVIDEND",
    "bonus":               "BONUS",
    "bonus shares":        "BONUS",
    "sub-division":        "SPLIT",
    "stock split":         "SPLIT",
    "rights":              "RIGHTS",
    "buyback":             "BUYBACK",
    "buy-back":            "BUYBACK",
    "agm":                 "AGM",
    "annual general meeting": "AGM",
    "egm":                 "EGM",
    "extraordinary general meeting": "EGM",
    "scheme":              "CORPORATE_ACTION",
    "amalgamation":        "CORPORATE_ACTION",
    "demerger":            "CORPORATE_ACTION",
}


def _normalise_purpose(raw: str) -> str:
    r = raw.strip().lower()
    for key, val in _PURPOSE_MAP.items():
        if key in r:
            return val
    return "CORPORATE_ACTION"


def _parse_nse_date(date_str: str) -> str | None:
    """Parse NSE date formats (DD-MMM-YYYY, DD-MM-YYYY, YYYY-MM-DD) → YYYY-MM-DD."""
    if not date_str or str(date_str).strip() in ("", "-", "nan", "None"):
        return None
    s = str(date_str).strip()
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%b %d, %Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    try:
        return pd.to_datetime(s, dayfirst=True).strftime("%Y-%m-%d")
    except Exception:
        return None


def fetch_nse_corporate_actions() -> pd.DataFrame:
    """Fetch NSE corporate actions (dividends, bonuses, splits, buybacks, AGM)."""
    print("  Fetching NSE corporate actions...")
    url = "https://www.nseindia.com/api/corporates-corporateActions?index=equities"
    raw = _curl_json(url, timeout=30)
    time.sleep(_SLEEP)
    if not raw:
        print("  Corporate actions: not available (NSE API).")
        return pd.DataFrame()

    records = raw if isinstance(raw, list) else raw.get("data", [])
    if not records:
        print("  Corporate actions: no records in response.")
        return pd.DataFrame()

    rows = []
    for item in records:
        sym = str(item.get("symbol", "")).strip()
        if not sym:
            continue
        purpose_raw = str(item.get("purpose", "")).strip()
        event_type = _normalise_purpose(purpose_raw)
        # Prefer exDate, then recordDate
        ex_date = _parse_nse_date(item.get("exDate", "") or item.get("recordDate", ""))
        if not ex_date:
            continue
        detail_parts = [purpose_raw]
        # For dividends: include amount if available
        if event_type == "EX_DIVIDEND":
            amt = str(item.get("faceVal", "") or item.get("dividend", "")).strip()
            if amt and amt not in ("-", ""):
                detail_parts.append(f"₹{amt}")
        # For buyback: include price if available
        if event_type == "BUYBACK":
            price = str(item.get("buyBackPrice", "") or "").strip()
            if price and price not in ("-", ""):
                detail_parts.append(f"@ ₹{price}")
        rows.append({
            "SYMBOL": sym,
            "EVENT_TYPE": event_type,
            "EVENT_DATE": ex_date,
            "PURPOSE_RAW": purpose_raw,
            "DETAIL": " — ".join(detail_parts),
            "SOURCE": "NSE_CORP_ACTION",
        })

    df = pd.DataFrame(rows)
    print(f"  Corporate actions: {len(df)} events for {df['SYMBOL'].nunique()} symbols.")
    return df


def fetch_nse_event_calendar() -> pd.DataFrame:
    """Fetch NSE event calendar (result announcements, board meetings)."""
    print("  Fetching NSE event calendar...")
    url = "https://www.nseindia.com/api/event-calendar"
    raw = _curl_json(url, timeout=30)
    time.sleep(_SLEEP)
    if not raw:
        print("  Event calendar: not available.")
        return pd.DataFrame()

    records = raw if isinstance(raw, list) else raw.get("data", [])
    if not records:
        print("  Event calendar: no records.")
        return pd.DataFrame()

    rows = []
    for item in records:
        sym = str(item.get("symbol", "")).strip()
        if not sym:
            continue
        event_date = _parse_nse_date(item.get("date", "") or item.get("meetingDate", ""))
        if not event_date:
            continue
        purpose_raw = str(item.get("purpose", "")).strip()
        # Classify: board meetings with results = RESULT_ANNOUNCEMENT
        purpose_lower = purpose_raw.lower()
        if any(k in purpose_lower for k in ("quarterly result", "annual result", "financial result",
                                             "q1", "q2", "q3", "q4", "fy", "board meeting")):
            event_type = "RESULT_ANNOUNCEMENT"
        elif "agm" in purpose_lower or "annual general" in purpose_lower:
            event_type = "AGM"
        elif "dividend" in purpose_lower:
            event_type = "EX_DIVIDEND"
        elif "buyback" in purpose_lower or "buy-back" in purpose_lower:
            event_type = "BUYBACK"
        else:
            event_type = "BOARD_MEETING"
        rows.append({
            "SYMBOL": sym,
            "EVENT_TYPE": event_type,
            "EVENT_DATE": event_date,
            "PURPOSE_RAW": purpose_raw,
            "DETAIL": purpose_raw,
            "SOURCE": "NSE_EVENT_CALENDAR",
        })

    df = pd.DataFrame(rows)
    print(f"  Event calendar: {len(df)} events for {df['SYMBOL'].nunique()} symbols.")
    return df


# ─────────────────────────────────────────────
# SECTION 3: PIPELINE
# ─────────────────────────────────────────────

def fetch_all_events(force: bool = False) -> pd.DataFrame:
    """Fetch all corporate events, merge, cache, return DataFrame."""
    if not force and EVENTS_CSV.exists():
        age_h = (time.time() - EVENTS_CSV.stat().st_mtime) / 3600
        if age_h < CACHE_TTL_HOURS:
            try:
                df = pd.read_csv(EVENTS_CSV)
                if not df.empty:
                    print(f"  Corporate events: loaded {len(df)} rows from cache.")
                    return df
            except Exception:
                pass

    parts = []

    corp_actions = fetch_nse_corporate_actions()
    if not corp_actions.empty:
        parts.append(corp_actions)

    event_cal = fetch_nse_event_calendar()
    if not event_cal.empty:
        parts.append(event_cal)

    if not parts:
        print("  No corporate events fetched from any source.")
        return pd.DataFrame(columns=["SYMBOL", "EVENT_TYPE", "EVENT_DATE", "PURPOSE_RAW", "DETAIL", "SOURCE"])

    combined = pd.concat(parts, ignore_index=True)
    combined["EVENT_DATE"] = pd.to_datetime(combined["EVENT_DATE"], errors="coerce")
    combined = combined.dropna(subset=["EVENT_DATE"])

    # Keep only future events (within next 90 days) and recent past (last 3 days for context)
    today = pd.Timestamp.now().normalize()
    combined = combined[
        (combined["EVENT_DATE"] >= today - pd.Timedelta(days=3)) &
        (combined["EVENT_DATE"] <= today + pd.Timedelta(days=90))
    ].copy()

    # Deduplicate: keep earliest event per symbol+event_type
    combined = combined.sort_values("EVENT_DATE")
    combined = combined.drop_duplicates(subset=["SYMBOL", "EVENT_TYPE"], keep="first")

    combined["EVENT_DATE"] = combined["EVENT_DATE"].dt.strftime("%Y-%m-%d")
    EVENTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(EVENTS_CSV, index=False)
    print(f"  Corporate events: saved {len(combined)} rows → {EVENTS_CSV.name}")
    return combined


# ─────────────────────────────────────────────
# SECTION 4: ENRICHMENT
# ─────────────────────────────────────────────

# Score adjustments per event type
_EVENT_SCORE_DELTA: dict[str, int] = {
    "RESULT_ANNOUNCEMENT": 0,   # neutral by default; adjusted by timing below
    "EX_DIVIDEND":         +1,  # mild positive (income + dip entry opportunity)
    "BONUS":               +1,  # psychological positive
    "SPLIT":               +1,  # psychological positive
    "BUYBACK":             +3,  # strong positive (company buying = floor signal)
    "RIGHTS":               0,
    "AGM":                  0,
    "BOARD_MEETING":        0,
    "EGM":                  0,
    "CORPORATE_ACTION":     0,
}


def _next_event_for_symbol(events_df: pd.DataFrame, symbol: str) -> dict | None:
    """Return the soonest upcoming event for a symbol."""
    sym_events = events_df[events_df["SYMBOL"] == symbol].copy()
    if sym_events.empty:
        return None
    sym_events["EVENT_DATE_DT"] = pd.to_datetime(sym_events["EVENT_DATE"], errors="coerce")
    today = pd.Timestamp.now().normalize()
    future = sym_events[sym_events["EVENT_DATE_DT"] >= today - pd.Timedelta(days=1)]
    if future.empty:
        return None
    row = future.sort_values("EVENT_DATE_DT").iloc[0]
    days_until = max(0, (row["EVENT_DATE_DT"] - today).days)
    return {
        "event_type": row["EVENT_TYPE"],
        "event_date": row["EVENT_DATE"],
        "days_until": days_until,
        "detail": str(row.get("DETAIL", "")),
    }


def _event_score_delta(event_type: str, days_until: int, detail: str = "") -> int:
    """Return INVESTMENT_SCORE adjustment for this event."""
    base = _EVENT_SCORE_DELTA.get(event_type, 0)
    if event_type == "RESULT_ANNOUNCEMENT":
        if days_until <= 3:
            base = -1  # very close result = uncertainty, reduce
        elif days_until <= 14:
            base = +1  # coming up soon = potential catalyst
    if event_type == "BUYBACK" and "₹" in detail:
        # If buyback price mentioned and > current price (can't check here), give max bonus
        base = +3
    return base


def _event_detail_text(event_type: str, days_until: int, detail: str, event_date: str) -> str:
    """Return a concise human-readable event string for HTML and LLM."""
    type_labels = {
        "RESULT_ANNOUNCEMENT": "Results",
        "EX_DIVIDEND":         "Ex-Div",
        "BONUS":               "Bonus",
        "SPLIT":               "Split",
        "RIGHTS":              "Rights",
        "BUYBACK":             "Buyback",
        "AGM":                 "AGM",
        "BOARD_MEETING":       "Board Mtg",
        "EGM":                 "EGM",
        "CORPORATE_ACTION":    "Corp Action",
    }
    label = type_labels.get(event_type, event_type.replace("_", " ").title())
    when = f"in {days_until}d" if days_until > 0 else "today"
    suffix = ""
    if detail and detail != event_type and len(detail) < 60:
        # Add relevant detail (dividend amount, buyback price)
        parts = detail.split("—")
        if len(parts) > 1:
            suffix = f" ({parts[-1].strip()})"
        elif "₹" in detail:
            suffix = f" ({detail})"
    return f"{label} {when} ({event_date}){suffix}"


def generate_event_alerts(candidates: pd.DataFrame, events_df: pd.DataFrame) -> pd.DataFrame:
    """Merge upcoming event data into candidates DataFrame.

    Adds/updates columns:
      NEXT_EVENT        — event type or empty string
      NEXT_EVENT_DATE   — YYYY-MM-DD or empty
      NEXT_EVENT_DAYS   — integer (0 = today, -1 = past)
      EVENT_DETAIL      — display string
      EVENT_SCORE_DELTA — score adjustment (may add to INVESTMENT_SCORE)
    """
    out = candidates.copy()
    for col in ["NEXT_EVENT", "NEXT_EVENT_DATE", "EVENT_DETAIL"]:
        out[col] = pd.Series([""] * len(out), index=out.index, dtype=object)
    out["NEXT_EVENT_DAYS"] = pd.Series([-1] * len(out), index=out.index, dtype="Int64")
    out["EVENT_SCORE_DELTA"] = pd.Series([0] * len(out), index=out.index, dtype="Int64")

    for idx, row in out.iterrows():
        sym = str(row.get("SYMBOL", "")).strip()
        if not sym:
            continue
        evt = _next_event_for_symbol(events_df, sym)
        if not evt:
            continue
        delta = _event_score_delta(evt["event_type"], evt["days_until"], evt["detail"])
        detail_text = _event_detail_text(evt["event_type"], evt["days_until"], evt["detail"], evt["event_date"])
        out.at[idx, "NEXT_EVENT"]        = evt["event_type"]
        out.at[idx, "NEXT_EVENT_DATE"]   = evt["event_date"]
        out.at[idx, "NEXT_EVENT_DAYS"]   = evt["days_until"]
        out.at[idx, "EVENT_DETAIL"]      = detail_text
        out.at[idx, "EVENT_SCORE_DELTA"] = delta

    # Apply score adjustments
    if "INVESTMENT_SCORE" in out.columns:
        deltas = pd.to_numeric(out["EVENT_SCORE_DELTA"], errors="coerce").fillna(0)
        mask = deltas.ne(0)
        out.loc[mask, "INVESTMENT_SCORE"] = (
            pd.to_numeric(out.loc[mask, "INVESTMENT_SCORE"], errors="coerce").fillna(50) +
            deltas.loc[mask]
        )

    n_events = (out["NEXT_EVENT"] != "").sum()
    print(f"  Event enrichment: {n_events}/{len(out)} candidates have upcoming events.")
    return out


def enrich_with_events(candidates: pd.DataFrame, force: bool = False) -> pd.DataFrame:
    """Full pipeline: fetch events → merge into candidates. Called from sector_rotation_report.py."""
    if candidates.empty or "SYMBOL" not in candidates.columns:
        return candidates
    try:
        events_df = fetch_all_events(force=force)
    except Exception as exc:
        print(f"  Event enrichment skipped ({exc}).")
        for col in ["NEXT_EVENT", "NEXT_EVENT_DATE", "NEXT_EVENT_DAYS", "EVENT_DETAIL", "EVENT_SCORE_DELTA"]:
            candidates[col] = ""
        return candidates
    if events_df.empty:
        for col in ["NEXT_EVENT", "NEXT_EVENT_DATE", "NEXT_EVENT_DAYS", "EVENT_DETAIL", "EVENT_SCORE_DELTA"]:
            candidates[col] = ""
        return candidates
    return generate_event_alerts(candidates, events_df)


# ─────────────────────────────────────────────
# SECTION 5: HTML BADGE
# ─────────────────────────────────────────────

_EVENT_BADGE_STYLE: dict[str, tuple[str, str]] = {
    "RESULT_ANNOUNCEMENT": ("📊 Results",  "evt-result"),
    "EX_DIVIDEND":         ("💰 Ex-Div",   "evt-div"),
    "BONUS":               ("🎁 Bonus",    "evt-bonus"),
    "SPLIT":               ("✂️ Split",    "evt-split"),
    "RIGHTS":              ("📝 Rights",   "evt-rights"),
    "BUYBACK":             ("🔵 Buyback",  "evt-buyback"),
    "AGM":                 ("🏛️ AGM",     "evt-agm"),
    "BOARD_MEETING":       ("📋 Board",    "evt-board"),
    "EGM":                 ("📋 EGM",      "evt-board"),
    "CORPORATE_ACTION":    ("⚙️ Action",   "evt-action"),
}

_RESULT_URGENCY_CSS = {
    (0, 3):   "evt-result evt-urgent",     # red: result very soon
    (4, 7):   "evt-result evt-soon",       # amber: within week
    (8, 999): "evt-result",               # default
}


def event_badge_html(event_type: str, days_until: int = -1, detail: str = "") -> str:
    """Return HTML badge string for an event."""
    et = str(event_type or "").strip().upper()
    if not et or et in ("", "NAN", "NONE"):
        return '<span class="evt evt-na">—</span>'

    if et == "RESULT_ANNOUNCEMENT":
        if days_until <= 3:
            css = "evt evt-result evt-urgent"
            label = f"📊 Results in {days_until}d"
        elif days_until <= 7:
            css = "evt evt-result evt-soon"
            label = f"📊 Results in {days_until}d"
        else:
            css = "evt evt-result"
            label = f"📊 Results in {days_until}d" if days_until >= 0 else "📊 Results"
    else:
        label_base, css_base = _EVENT_BADGE_STYLE.get(et, (et.replace("_", " ").title(), "evt-action"))
        label = f"{label_base} in {days_until}d" if days_until >= 0 else label_base
        css = f"evt {css_base}"

    detail_html = ""
    if detail and str(detail) not in ("", "nan", "None"):
        # Show concise detail (strip the "in Xd (date)" part for the tooltip)
        short = str(detail)[:70]
        detail_html = f'<div class="evt-detail">{short}</div>'

    return f'<span class="{css}">{label}</span>{detail_html}'


EVENT_CSS = """
/* ---- CORPORATE EVENT BADGES (E4) ---- */
.evt{display:inline-block;padding:2px 7px;border-radius:10px;font-size:9.5px;font-weight:700;white-space:nowrap}
.evt-result{background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe}
.evt-result.evt-urgent{background:#fee2e2;color:#991b1b;border:1px solid #fca5a5;animation:pulse-red 1.5s infinite}
.evt-result.evt-soon{background:#ffedd5;color:#c2410c;border:1px solid #fdba74}
.evt-div{background:#f0fdf4;color:#15803d;border:1px solid #86efac}
.evt-bonus{background:#fdf4ff;color:#7e22ce;border:1px solid #e9d5ff}
.evt-split{background:#fdf4ff;color:#7e22ce;border:1px solid #e9d5ff}
.evt-buyback{background:#dbeafe;color:#1e40af;border:1px solid #93c5fd;font-weight:800}
.evt-agm{background:#f1f5f9;color:#475569;border:1px solid #cbd5e1}
.evt-board{background:#f8fafc;color:#64748b;border:1px solid #e2e8f0}
.evt-action{background:#fefce8;color:#a16207;border:1px solid #fde68a}
.evt-rights{background:#fff7ed;color:#c2410c;border:1px solid #fed7aa}
.evt-na{color:#cbd5e1;font-size:9px}
.evt-detail{font-size:9px;color:#64748b;margin-top:2px;line-height:1.3;max-width:180px;overflow:hidden;text-overflow:ellipsis}
@keyframes pulse-red{0%,100%{opacity:1}50%{opacity:.6}}
"""


# ─────────────────────────────────────────────
# SECTION 6: CLI
# ─────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch NSE corporate event alerts (E4).")
    parser.add_argument("--force", action="store_true", help="Ignore cache, re-fetch from NSE.")
    parser.add_argument("--symbol", type=str, default=None, help="Show events for a specific symbol.")
    parser.add_argument("--days", type=int, default=30, help="Look-forward window in days (default: 30).")
    args = parser.parse_args()

    events = fetch_all_events(force=args.force)
    if events.empty:
        print("\nNo corporate events available.")
        sys.exit(0)

    events["EVENT_DATE_DT"] = pd.to_datetime(events["EVENT_DATE"], errors="coerce")
    today = pd.Timestamp.now().normalize()
    upcoming = events[
        (events["EVENT_DATE_DT"] >= today) &
        (events["EVENT_DATE_DT"] <= today + pd.Timedelta(days=args.days))
    ].sort_values("EVENT_DATE_DT")

    if args.symbol:
        upcoming = upcoming[upcoming["SYMBOL"].str.upper() == args.symbol.upper()]

    print(f"\n{'='*70}")
    print(f"Upcoming Corporate Events (next {args.days} days) — {len(upcoming)} events")
    print(f"{'='*70}")
    print(f"{'Symbol':<14} {'Event':<22} {'Date':<14} {'Days':>5}  Detail")
    print("-" * 70)
    for _, r in upcoming.head(50).iterrows():
        days = max(0, (r["EVENT_DATE_DT"] - today).days)
        detail = str(r.get("DETAIL", ""))[:35]
        print(f"{r['SYMBOL']:<14} {r['EVENT_TYPE']:<22} {r['EVENT_DATE']:<14} {days:>5}d  {detail}")

    # Summary
    print(f"\nEvent breakdown:")
    print(upcoming["EVENT_TYPE"].value_counts().to_string())


if __name__ == "__main__":
    main()
