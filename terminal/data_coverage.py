"""Terminal handler for /data-coverage — audit & backfill EOD history.

Usage examples:

    /data-coverage NIFTY500                       # audit only
    /data-coverage NIFTY500 --backfill            # audit + fill gaps
    /data-coverage NIFTY50 --min-years 5
    /data-coverage NIFTY500 --backfill --period 5y --sleep 0.15
    /data-coverage NIFTY500 --symbols DMART,RELIANCE --backfill
    /data-coverage NIFTY500 --details             # list undercovered symbols

Designed for the Agent Adda terminal: returns a Markdown summary that
renders cleanly with ``console.print(Markdown(...))``.
"""

from __future__ import annotations

import shlex
import time
from contextlib import closing
from pathlib import Path

import pandas as pd

from data_pipeline.equity_eod_backfill import (
    SymbolCoverage,
    coverage_for_symbols,
    fetch_history,
    pg_dsn,
    upsert_rows,
)


TRADING_DAYS_PER_YEAR = 240  # NSE averages ~248 sessions; 240 gives margin
DEFAULT_MIN_YEARS = 5
DEFAULT_PERIOD = "5y"
DEFAULT_INDEX_MAPPING_CSV = "data/index_stock_mapping.csv"

# Common short-hand → CSV-canonical index name
INDEX_ALIASES = {
    "NIFTY50": "NIFTY 50",
    "NIFTY100": "NIFTY 100",
    "NIFTY200": "NIFTY 200",
    "NIFTY500": "NIFTY 500",
    "NIFTYNEXT50": "NIFTY NEXT 50",
    "NIFTYMIDCAP50": "NIFTY MIDCAP 50",
    "NIFTYMIDCAP100": "NIFTY MIDCAP 100",
    "NIFTYMIDCAP150": "NIFTY MIDCAP 150",
    "NIFTYSMALLCAP250": "NIFTY SMALLCAP 250",
    "NIFTYMICROCAP250": "NIFTY MICROCAP 250",
    "NIFTYLARGEMIDCAP250": "NIFTY LARGEMIDCAP 250",
}


def _canonical_index(name: str) -> str:
    token = name.strip().upper().replace("-", "").replace("_", "").replace(" ", "")
    return INDEX_ALIASES.get(token, name.strip().upper())


def _arg(parts: list[str], name: str, default: str | None = None) -> str | None:
    if name in parts:
        idx = parts.index(name)
        if idx + 1 >= len(parts):
            raise ValueError(f"Missing value for {name}")
        return parts[idx + 1]
    return default


def _flag(parts: list[str], *names: str) -> bool:
    return any(n in parts for n in names)


def _positive_float(raw: str | None, *, name: str, default: float) -> float:
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _symbols_for(df: pd.DataFrame, canonical: str) -> list[str]:
    matched = df[df["INDEX_NAME"].astype(str).str.upper() == canonical.upper()]
    return (
        matched["STOCK_SYMBOL"].dropna().astype(str).str.strip().str.upper().tolist()
    )


def _load_index_symbols(index_name: str, project_root: Path) -> list[str]:
    canonical = _canonical_index(index_name)
    csv_path = project_root / DEFAULT_INDEX_MAPPING_CSV
    if not csv_path.exists():
        raise FileNotFoundError(f"Index mapping not found: {csv_path}")
    df = pd.read_csv(csv_path)
    if "INDEX_NAME" not in df.columns or "STOCK_SYMBOL" not in df.columns:
        raise ValueError(f"Unexpected schema in {csv_path}: {list(df.columns)}")

    # NIFTY SMALLCAP 250 isn't published in the index_stock_mapping CSV;
    # derive it as the official methodology does: NIFTY 500 minus the
    # NIFTY LARGEMIDCAP 250 (which is NIFTY 100 + NIFTY MIDCAP 150).
    if canonical.upper() == "NIFTY SMALLCAP 250":
        n500 = set(_symbols_for(df, "NIFTY 500"))
        nlm250 = set(_symbols_for(df, "NIFTY LARGEMIDCAP 250"))
        derived = sorted(n500 - nlm250)
        if not derived:
            raise ValueError(
                "Cannot derive NIFTY SMALLCAP 250: NIFTY 500 / LARGEMIDCAP 250 "
                "missing in mapping CSV."
            )
        return derived

    matched = df[df["INDEX_NAME"].astype(str).str.upper() == canonical.upper()]
    if matched.empty:
        available = (
            df["INDEX_NAME"].dropna().astype(str).str.upper().unique().tolist()
        )
        available = sorted(a for a in available if "NIFTY" in a)[:15]
        raise ValueError(
            f"Index '{index_name}' (resolved to '{canonical}') not found. "
            f"Try one of: {', '.join(available)}"
        )
    symbols = (
        matched["STOCK_SYMBOL"].dropna().astype(str).str.strip().str.upper().tolist()
    )
    return sorted(set(symbols))


def _classify(coverage: list[SymbolCoverage], min_bars: int) -> dict:
    ok = [c for c in coverage if c.bar_count >= min_bars]
    short = [c for c in coverage if 0 < c.bar_count < min_bars]
    missing = [c for c in coverage if c.bar_count == 0]
    return {"ok": ok, "short": short, "missing": missing}


def _format_summary(
    index_name: str,
    min_years: float,
    min_bars: int,
    coverage: list[SymbolCoverage],
    backfill_stats: dict | None,
    details: bool,
) -> str:
    classes = _classify(coverage, min_bars)
    total = len(coverage)
    ok = len(classes["ok"])
    short = len(classes["short"])
    missing = len(classes["missing"])
    pct = (ok / total * 100.0) if total else 0.0

    lines = [
        f"### Data Coverage — {index_name}",
        "",
        f"- **Universe:** {total} symbols",
        f"- **Threshold:** {min_years:g} years (~{min_bars} trading bars)",
        f"- **Fully covered:** {ok} ({pct:.1f}%)",
        f"- **Undercovered:** {short}",
        f"- **Missing entirely:** {missing}",
    ]
    if backfill_stats is not None:
        lines.extend(
            [
                "",
                "**Backfill run**",
                f"- Symbols attempted: {backfill_stats['attempted']}",
                f"- Rows inserted: {backfill_stats['inserted']}",
                f"- Empty (no yfinance data): {backfill_stats['empty']}",
                f"- Errors: {backfill_stats['errors']}",
                f"- Duration: {backfill_stats['duration_s']:.1f}s",
            ]
        )
    if details and (classes["short"] or classes["missing"]):
        lines.append("")
        lines.append("**Undercovered symbols (top 25)**")
        worst = sorted(
            classes["short"] + classes["missing"], key=lambda c: c.bar_count
        )[:25]
        for cov in worst:
            first = cov.first_date.isoformat() if cov.first_date else "—"
            last = cov.last_date.isoformat() if cov.last_date else "—"
            lines.append(
                f"- `{cov.symbol}` bars={cov.bar_count} first={first} last={last}"
            )
    lines.append("")
    lines.append("_Source: PostgreSQL `market.equity_eod`; backfill via yfinance._")
    return "\n".join(lines)


def _run_backfill(
    conn,
    targets: list[str],
    *,
    period: str,
    sleep_s: float,
) -> dict:
    attempted = 0
    inserted = 0
    empty = 0
    errors = 0
    t0 = time.time()
    for sym in targets:
        attempted += 1
        try:
            df = fetch_history(sym, period=period)
            if df.empty:
                empty += 1
            else:
                n = upsert_rows(conn, df)
                conn.commit()
                inserted += n
        except Exception:
            conn.rollback()
            errors += 1
        if sleep_s > 0:
            time.sleep(sleep_s)
    return {
        "attempted": attempted,
        "inserted": inserted,
        "empty": empty,
        "errors": errors,
        "duration_s": time.time() - t0,
    }


def handle_data_coverage_command(
    text: str,
    *,
    project_root: Path | None = None,
) -> str:
    root = Path(project_root or Path.cwd())
    try:
        parts = shlex.split(text)
        if len(parts) < 2:
            raise ValueError(
                "Usage: /data-coverage INDEX [--min-years 5] [--backfill] "
                "[--symbols SYM1,SYM2] [--period 5y] [--sleep 0.15] [--details]"
            )
        index_name = parts[1]
        min_years = _positive_float(
            _arg(parts, "--min-years"), name="--min-years", default=DEFAULT_MIN_YEARS
        )
        min_bars = int(min_years * TRADING_DAYS_PER_YEAR)
        period = _arg(parts, "--period") or DEFAULT_PERIOD
        sleep_s = _positive_float(_arg(parts, "--sleep"), name="--sleep", default=0.15)
        do_backfill = _flag(parts, "--backfill")
        details = _flag(parts, "--details")
        symbols_override = _arg(parts, "--symbols")

        if symbols_override:
            symbols = sorted(
                {s.strip().upper() for s in symbols_override.split(",") if s.strip()}
            )
        else:
            symbols = _load_index_symbols(index_name, root)
    except Exception as exc:
        return f"Data Coverage failed: {exc}"

    try:
        import psycopg2
    except Exception as exc:
        return f"Data Coverage failed: psycopg2 unavailable ({exc})"

    try:
        with closing(psycopg2.connect(pg_dsn())) as conn:
            coverage = coverage_for_symbols(conn, symbols)
            backfill_stats = None
            if do_backfill:
                targets = [c.symbol for c in coverage if c.bar_count < min_bars]
                if targets:
                    backfill_stats = _run_backfill(
                        conn, targets, period=period, sleep_s=sleep_s
                    )
                    coverage = coverage_for_symbols(conn, symbols)
                else:
                    backfill_stats = {
                        "attempted": 0,
                        "inserted": 0,
                        "empty": 0,
                        "errors": 0,
                        "duration_s": 0.0,
                    }
    except Exception as exc:
        return f"Data Coverage failed: {type(exc).__name__}: {exc}"

    return _format_summary(
        index_name=index_name,
        min_years=min_years,
        min_bars=min_bars,
        coverage=coverage,
        backfill_stats=backfill_stats,
        details=details,
    )
