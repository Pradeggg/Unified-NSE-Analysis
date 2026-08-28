"""Read-through cache for structured financials (P&L / BS / CF).

The scraper in :mod:`terminal.web_research.scrape_screener_in` returns
screener.in's quarterly / annual_pl / balance_sheet / cash_flow tables as
``dict[label, list[str]]`` plus a ``"_headers"`` list of period labels. The
helpers in this module:

1. Normalise those scraped tables into structured rows ready for PG upsert.
2. Provide :func:`upsert_screener_payload` — one call writes all four PG
   tables (``scores.quarterly_results``, ``scores.annual_results``,
   ``scores.balance_sheet``, ``scores.cash_flow``).
3. Provide :func:`read_financials` — pulls the latest cached rows from PG
   for a symbol, returning ``None`` on miss so callers (e.g.
   ``reconcile_filing_facts``) can fall back to a live scrape.

The cache stores raw, lightly normalised values: numeric where parseable,
``NULL`` otherwise. The raw period_label is preserved so users can join
back to the original screener column heading without ambiguity. The full
scraped tables for each section are also stored as JSONB in ``raw_json``
for analyst inspection.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Iterable

import psycopg2
import psycopg2.extras


__all__ = [
    "DEFAULT_DSN",
    "connect",
    "parse_period_end",
    "to_number",
    "build_pnl_rows",
    "build_balance_sheet_rows",
    "build_cash_flow_rows",
    "upsert_screener_payload",
    "read_financials",
    "screener_payload_from_cache",
    "read_quarterly",
    "read_annual",
    "read_balance_sheet",
    "read_cash_flow",
    "log_refresh_run",
]


DEFAULT_DSN = os.environ.get(
    "AGENT_ADDA_PG_DSN", "dbname=nse_market user=nse_admin host=/tmp"
)


@contextmanager
def connect(dsn: str | None = None):
    """Context manager for a short-lived Postgres connection."""
    conn = psycopg2.connect(dsn or DEFAULT_DSN)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Period + value normalisation
# ---------------------------------------------------------------------------


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_period_end(label: str) -> date | None:
    """Best-effort parse of screener period headers like ``'Mar 2026'``.

    Returns the month-end date for that month, or ``None`` for labels we
    cannot resolve (``'TTM'``, ``'FY26'``, empty strings).
    """
    if not label:
        return None
    s = str(label).strip().lower()
    m = re.match(r"^([a-z]{3})[a-z]*\s+(\d{4})$", s)
    if not m:
        return None
    month_idx = _MONTHS.get(m.group(1))
    if not month_idx:
        return None
    year = int(m.group(2))
    if month_idx == 12:
        return date(year, 12, 31)
    next_month_first = date(year, month_idx + 1, 1)
    from datetime import timedelta
    return next_month_first - timedelta(days=1)


def to_number(value: Any) -> float | None:
    """Parse screener-style numbers — commas, %, parens for negatives — into floats."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value != value:  # NaN
            return None
        return float(value)
    s = str(value).strip()
    if not s or s in {"-", "—", "n/a", "NA", "NaN", "None"}:
        return None
    s = s.replace(",", "").replace("\u20b9", "").strip()
    s = s.rstrip("%").strip()
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]
    try:
        f = float(s)
        return -f if negative else f
    except (ValueError, TypeError):
        return None


def _label_norm(label: str) -> str:
    """Strip trailing ``+`` markers and lowercase for matching."""
    return re.sub(r"\s+", " ", str(label or "").rstrip("+").strip().lower())


def _pick(table: dict[str, Any], aliases: Iterable[str]) -> list[str]:
    """Find the first row whose label (normalised) matches any alias."""
    if not isinstance(table, dict):
        return []
    norm = {_label_norm(k): v for k, v in table.items() if k != "_headers"}
    for alias in aliases:
        a = _label_norm(alias)
        if a in norm and isinstance(norm[a], list):
            return [str(x) for x in norm[a]]
    return []


# ---------------------------------------------------------------------------
# Table -> structured rows
# ---------------------------------------------------------------------------


def _zip_columns(values: list[str], headers: list[str]) -> list[tuple[str, str]]:
    """Pair values with headers, trimming the longer side from the front
    (screener tables sometimes carry an extra leading column).
    """
    if not headers:
        return []
    if len(values) > len(headers):
        values = values[-len(headers):]
    elif len(values) < len(headers):
        headers = headers[-len(values):]
    return list(zip(headers, values))


def _build_pl_like_rows(
    symbol: str,
    table: dict[str, Any],
    *,
    period_type: str,
    source: str,
    source_url: str | None,
) -> list[dict[str, Any]]:
    """Shared builder for quarterly + annual P&L rows (same column shape)."""
    if not isinstance(table, dict):
        return []
    headers = table.get("_headers") or []
    if not headers:
        return []
    rows: list[dict[str, Any]] = []
    field_map = {
        "revenue":           ("sales", "revenue", "revenue from operations"),
        "expenses":          ("expenses",),
        "operating_profit":  ("operating profit",),
        "opm_pct":           ("opm %", "opm"),
        "other_income":      ("other income",),
        "interest":          ("interest",),
        "depreciation":      ("depreciation",),
        "pbt":               ("profit before tax", "pbt"),
        "tax_pct":           ("tax %", "tax"),
        "pat":               ("net profit", "pat", "profit after tax"),
        "eps":               ("eps in rs", "eps"),
    }
    extra: dict[str, tuple[str, ...]] = {}
    if period_type == "annual":
        extra = {"dividend_payout_pct": ("dividend payout %", "dividend payout")}

    parsed: dict[str, list[float | None]] = {}
    for col, aliases in {**field_map, **extra}.items():
        values = _pick(table, aliases)
        if not values:
            continue
        for idx, (_hdr, raw) in enumerate(_zip_columns(values, headers)):
            parsed.setdefault(col, [None] * len(headers))
            if idx < len(parsed[col]):
                parsed[col][idx] = to_number(raw)

    for i, header in enumerate(headers):
        row: dict[str, Any] = {
            "symbol": symbol,
            "period_label": header,
            "period_end": parse_period_end(header),
            "period_type": period_type,
            "source": source,
            "source_url": source_url,
            "fetched_at": datetime.now(),
        }
        any_value = False
        for col in {**field_map, **extra}.keys():
            v = (parsed.get(col) or [None] * len(headers))[i]
            row[col] = v
            if v is not None:
                any_value = True
        if not any_value:
            continue
        row["raw_json"] = json.dumps({"headers": headers, "table_keys": list(table.keys())})
        rows.append(row)
    return rows


def build_pnl_rows(
    symbol: str,
    payload: dict[str, Any],
    *,
    source: str = "screener",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return ``(quarterly_rows, annual_rows)`` from a ``scrape_screener_in`` payload."""
    source_url = payload.get("source_url") if isinstance(payload, dict) else None
    q = _build_pl_like_rows(
        symbol, payload.get("quarterly") or {},
        period_type="quarter", source=source, source_url=source_url,
    )
    a = _build_pl_like_rows(
        symbol, payload.get("annual_pl") or {},
        period_type="annual", source=source, source_url=source_url,
    )
    return q, a


def build_balance_sheet_rows(
    symbol: str,
    payload: dict[str, Any],
    *,
    source: str = "screener",
) -> list[dict[str, Any]]:
    """Build ``scores.balance_sheet`` rows from a payload."""
    table = (payload or {}).get("balance_sheet") if isinstance(payload, dict) else None
    if not isinstance(table, dict):
        return []
    headers = table.get("_headers") or []
    if not headers:
        return []
    source_url = payload.get("source_url") if isinstance(payload, dict) else None
    field_map = {
        "equity_capital":   ("equity capital",),
        "reserves":         ("reserves",),
        "borrowings":       ("borrowings",),
        "other_liabilities": ("other liabilities",),
        "total_liabilities": ("total liabilities",),
        "fixed_assets":     ("fixed assets",),
        "cwip":             ("cwip", "capital work in progress"),
        "investments":      ("investments",),
        "other_assets":     ("other assets",),
        "total_assets":     ("total assets",),
    }
    parsed: dict[str, list[float | None]] = {}
    for col, aliases in field_map.items():
        values = _pick(table, aliases)
        if not values:
            continue
        for idx, (_hdr, raw) in enumerate(_zip_columns(values, headers)):
            parsed.setdefault(col, [None] * len(headers))
            if idx < len(parsed[col]):
                parsed[col][idx] = to_number(raw)

    rows: list[dict[str, Any]] = []
    for i, header in enumerate(headers):
        row: dict[str, Any] = {
            "symbol": symbol,
            "period_label": header,
            "period_end": parse_period_end(header),
            "period_type": "annual",
            "source": source,
            "source_url": source_url,
            "fetched_at": datetime.now(),
        }
        any_value = False
        for col in field_map:
            v = (parsed.get(col) or [None] * len(headers))[i]
            row[col] = v
            if v is not None:
                any_value = True
        # Derived: net_debt = borrowings - investments (best-effort proxy when
        # cash is not reported separately on screener's BS table).
        borrowings = row.get("borrowings")
        investments = row.get("investments")
        if borrowings is not None and investments is not None:
            row["net_debt"] = borrowings - investments
            any_value = True
        else:
            row["net_debt"] = None
        if not any_value:
            continue
        row["raw_json"] = json.dumps({"headers": headers, "table_keys": list(table.keys())})
        rows.append(row)
    return rows


def build_cash_flow_rows(
    symbol: str,
    payload: dict[str, Any],
    *,
    source: str = "screener",
) -> list[dict[str, Any]]:
    """Build ``scores.cash_flow`` rows from a payload."""
    table = (payload or {}).get("cash_flow") if isinstance(payload, dict) else None
    if not isinstance(table, dict):
        return []
    headers = table.get("_headers") or []
    if not headers:
        return []
    source_url = payload.get("source_url") if isinstance(payload, dict) else None
    field_map = {
        "operating_cf": ("cash from operating activity",),
        "investing_cf": ("cash from investing activity",),
        "financing_cf": ("cash from financing activity",),
        "net_cf":       ("net cash flow",),
        "free_cash_flow": ("free cash flow", "fcf"),
    }
    parsed: dict[str, list[float | None]] = {}
    for col, aliases in field_map.items():
        values = _pick(table, aliases)
        if not values:
            continue
        for idx, (_hdr, raw) in enumerate(_zip_columns(values, headers)):
            parsed.setdefault(col, [None] * len(headers))
            if idx < len(parsed[col]):
                parsed[col][idx] = to_number(raw)

    rows: list[dict[str, Any]] = []
    for i, header in enumerate(headers):
        row: dict[str, Any] = {
            "symbol": symbol,
            "period_label": header,
            "period_end": parse_period_end(header),
            "period_type": "annual",
            "source": source,
            "source_url": source_url,
            "fetched_at": datetime.now(),
        }
        any_value = False
        for col in field_map:
            v = (parsed.get(col) or [None] * len(headers))[i]
            row[col] = v
            if v is not None:
                any_value = True
        if not any_value:
            continue
        row["raw_json"] = json.dumps({"headers": headers, "table_keys": list(table.keys())})
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Upsert + read API
# ---------------------------------------------------------------------------


def _upsert(cur, table: str, rows: list[dict[str, Any]], conflict_cols: list[str]) -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    update_cols = [c for c in cols if c not in conflict_cols]
    values = [[r.get(c) for c in cols] for r in rows]
    placeholders = ", ".join(["%s"] * len(cols))
    conflict = ", ".join(conflict_cols)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
    sql = (
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
    )
    cur.executemany(sql, values)
    return len(values)


def upsert_screener_payload(
    symbol: str,
    payload: dict[str, Any],
    *,
    source: str = "screener",
    conn=None,
    dsn: str | None = None,
) -> dict[str, int]:
    """Persist all four sections from a ``scrape_screener_in`` payload to PG.

    Returns ``{"quarterly": n, "annual": n, "balance_sheet": n, "cash_flow": n}``.
    Pass an open ``conn`` to share a transaction with a caller (the function
    will not commit/close it); otherwise a short-lived connection is opened
    and committed at the end.
    """
    sym = str(symbol or "").strip().upper()
    if not sym:
        return {"quarterly": 0, "annual": 0, "balance_sheet": 0, "cash_flow": 0}

    quarterly_rows, annual_rows = build_pnl_rows(sym, payload, source=source)
    bs_rows = build_balance_sheet_rows(sym, payload, source=source)
    cf_rows = build_cash_flow_rows(sym, payload, source=source)

    counts = {
        "quarterly": 0,
        "annual": 0,
        "balance_sheet": 0,
        "cash_flow": 0,
    }
    own_conn = conn is None
    if own_conn:
        conn = psycopg2.connect(dsn or DEFAULT_DSN)
    try:
        with conn.cursor() as cur:
            counts["quarterly"] = _upsert(cur, "scores.quarterly_results", quarterly_rows, ["symbol", "period_label"])
            counts["annual"] = _upsert(cur, "scores.annual_results", annual_rows, ["symbol", "period_label"])
            counts["balance_sheet"] = _upsert(cur, "scores.balance_sheet", bs_rows, ["symbol", "period_label"])
            counts["cash_flow"] = _upsert(cur, "scores.cash_flow", cf_rows, ["symbol", "period_label"])
        if own_conn:
            conn.commit()
    except Exception:
        if own_conn:
            conn.rollback()
        raise
    finally:
        if own_conn:
            conn.close()
    return counts


def _read_table(
    table: str,
    symbol: str,
    *,
    limit: int = 6,
    dsn: str | None = None,
) -> list[dict[str, Any]]:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return []
    conn = psycopg2.connect(dsn or DEFAULT_DSN)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"SELECT * FROM {table} WHERE symbol = %s "
                f"ORDER BY period_end DESC NULLS LAST, fetched_at DESC LIMIT %s",
                (sym, limit),
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def read_quarterly(symbol: str, *, limit: int = 6, dsn: str | None = None) -> list[dict[str, Any]]:
    return _read_table("scores.quarterly_results", symbol, limit=limit, dsn=dsn)


def read_annual(symbol: str, *, limit: int = 5, dsn: str | None = None) -> list[dict[str, Any]]:
    return _read_table("scores.annual_results", symbol, limit=limit, dsn=dsn)


def read_balance_sheet(symbol: str, *, limit: int = 5, dsn: str | None = None) -> list[dict[str, Any]]:
    return _read_table("scores.balance_sheet", symbol, limit=limit, dsn=dsn)


def read_cash_flow(symbol: str, *, limit: int = 5, dsn: str | None = None) -> list[dict[str, Any]]:
    return _read_table("scores.cash_flow", symbol, limit=limit, dsn=dsn)


def read_financials(symbol: str, *, dsn: str | None = None) -> dict[str, Any]:
    """Bulk read all four sections for a symbol.

    Returns a dict with keys ``quarterly``, ``annual``, ``balance_sheet``,
    ``cash_flow``, each a list of rows. If a section has no rows, that list
    is empty (no ``None``).
    """
    return {
        "quarterly": read_quarterly(symbol, dsn=dsn),
        "annual": read_annual(symbol, dsn=dsn),
        "balance_sheet": read_balance_sheet(symbol, dsn=dsn),
        "cash_flow": read_cash_flow(symbol, dsn=dsn),
    }


# ---------------------------------------------------------------------------
# Screener-shape reconstruction for read-through cache
# ---------------------------------------------------------------------------


_QUARTERLY_COL_LABELS = [
    ("Sales+", "revenue"),
    ("Expenses+", "expenses"),
    ("Operating Profit", "operating_profit"),
    ("OPM %", "opm_pct"),
    ("Other Income+", "other_income"),
    ("Interest", "interest"),
    ("Depreciation", "depreciation"),
    ("Profit before tax", "pbt"),
    ("Tax %", "tax_pct"),
    ("Net Profit+", "pat"),
    ("EPS in Rs", "eps"),
]
_ANNUAL_COL_LABELS = _QUARTERLY_COL_LABELS + [("Dividend Payout %", "dividend_payout_pct")]
_BS_COL_LABELS = [
    ("Equity Capital", "equity_capital"),
    ("Reserves", "reserves"),
    ("Borrowings+", "borrowings"),
    ("Other Liabilities+", "other_liabilities"),
    ("Total Liabilities", "total_liabilities"),
    ("Fixed Assets+", "fixed_assets"),
    ("CWIP", "cwip"),
    ("Investments", "investments"),
    ("Other Assets+", "other_assets"),
    ("Total Assets", "total_assets"),
]
_CF_COL_LABELS = [
    ("Cash from Operating Activity+", "operating_cf"),
    ("Cash from Investing Activity+", "investing_cf"),
    ("Cash from Financing Activity+", "financing_cf"),
    ("Net Cash Flow", "net_cf"),
    ("Free Cash Flow", "free_cash_flow"),
]


def _format_cache_value(v: Any) -> str:
    if v is None:
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f == int(f):
        return f"{int(f):,}"
    return f"{f:,.2f}"


def _section_from_cache_rows(
    rows: list[dict[str, Any]],
    col_map: list[tuple[str, str]],
) -> dict[str, Any]:
    if not rows:
        return {}
    # PG rows come back newest→oldest; screener_data convention is
    # oldest→newest across columns.
    rows_asc = list(reversed(rows))
    headers = [r["period_label"] for r in rows_asc]
    out: dict[str, Any] = {"_headers": headers}
    for label, col in col_map:
        values = [_format_cache_value(r.get(col)) for r in rows_asc]
        if any(v for v in values):
            out[label] = values
    return out


def screener_payload_from_cache(
    symbol: str,
    *,
    max_age_hours: float | None = 24.0,
    dsn: str | None = None,
) -> dict[str, Any] | None:
    """Reconstruct a screener-shaped payload from cached PG rows.

    Returns ``None`` when the cache is empty or staler than
    ``max_age_hours`` (set ``max_age_hours=None`` to ignore freshness — used
    by the live-scrape failure fallback path).
    """
    sym = str(symbol or "").strip().upper()
    if not sym:
        return None
    fin = read_financials(sym, dsn=dsn)
    all_rows = (
        (fin.get("quarterly") or [])
        + (fin.get("annual") or [])
        + (fin.get("balance_sheet") or [])
        + (fin.get("cash_flow") or [])
    )
    if not all_rows:
        return None

    newest = None
    for r in all_rows:
        ts = r.get("fetched_at")
        if ts and (newest is None or ts > newest):
            newest = ts
    age_hours: float | None = None
    if newest is not None:
        age_hours = (datetime.now(newest.tzinfo) - newest).total_seconds() / 3600.0
        if max_age_hours is not None and age_hours > max_age_hours:
            return None

    source_url = None
    for r in all_rows:
        if r.get("source_url"):
            source_url = r["source_url"]
            break

    payload: dict[str, Any] = {
        "symbol": sym,
        "source_url": source_url,
        "_source": "pg_cache",
        "_cache_age_hours": round(age_hours, 2) if age_hours is not None else None,
        "quarterly": _section_from_cache_rows(fin.get("quarterly") or [], _QUARTERLY_COL_LABELS),
        "annual_pl": _section_from_cache_rows(fin.get("annual") or [], _ANNUAL_COL_LABELS),
        "balance_sheet": _section_from_cache_rows(fin.get("balance_sheet") or [], _BS_COL_LABELS),
        "cash_flow": _section_from_cache_rows(fin.get("cash_flow") or [], _CF_COL_LABELS),
        "ratios": {},
        "shareholding": {},
        "announcements": [],
    }
    return payload


# ---------------------------------------------------------------------------
# Refresh-job audit log
# ---------------------------------------------------------------------------


def log_refresh_run(
    job_name: str,
    *,
    symbols_attempted: int,
    symbols_loaded: int,
    rows_upserted: int,
    errors: int,
    notes: str | None = None,
    run_id: str | None = None,
    dsn: str | None = None,
) -> str:
    """Write a row to ``scores.financials_refresh_log`` and return the run id."""
    rid = run_id or f"{job_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    conn = psycopg2.connect(dsn or DEFAULT_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO scores.financials_refresh_log
                    (run_id, job_name, finished_at,
                     symbols_attempted, symbols_loaded, rows_upserted, errors, notes)
                VALUES (%s, %s, now(), %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET
                    finished_at = EXCLUDED.finished_at,
                    symbols_attempted = EXCLUDED.symbols_attempted,
                    symbols_loaded = EXCLUDED.symbols_loaded,
                    rows_upserted = EXCLUDED.rows_upserted,
                    errors = EXCLUDED.errors,
                    notes = EXCLUDED.notes
                """,
                (rid, job_name, symbols_attempted, symbols_loaded, rows_upserted, errors, notes),
            )
        conn.commit()
    finally:
        conn.close()
    return rid
