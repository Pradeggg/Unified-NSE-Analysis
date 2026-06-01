"""Data freshness and integrity gate for Research Council runs."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from terminal.research_council.mode_profiles import ModeProfile, load_mode_profile
from terminal.research_council.schemas import CouncilState, StewardVerdict

DEFAULT_DSN = os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"
LIQUIDITY_FILTERS = ["close > 100", "volume > 100000", "at least 50 bars"]


def run(state: CouncilState) -> CouncilState:
    if state.flags.get("dry_run"):
        return state
    verdict = run_check(mode=state.mode)
    data = state.to_dict()
    data["steward_verdict"] = verdict.to_dict()
    if verdict.data_status == "blocked":
        data["stage"] = "abort_stale_data"
    return CouncilState.from_dict(data)


def run_check(
    *,
    mode: str = "market_council",
    as_of: date | None = None,
    now: datetime | None = None,
    snapshot_loader: Callable[[], dict[str, Any]] | None = None,
    dsn: str | None = None,
) -> StewardVerdict:
    profile = load_mode_profile(mode)
    snapshot = snapshot_loader() if snapshot_loader else collect_pg_snapshot(dsn=dsn)
    # Default as_of to the last business day so weekend runs don't spuriously
    # flag weekday-fresh data as stale (e.g. Sunday run with Friday EOD data).
    if as_of is None:
        as_of = _last_business_day(now.date() if now else date.today())
    return compute_verdict(snapshot=snapshot, profile=profile, as_of=as_of, now=now)


def _last_business_day(d: date) -> date:
    from datetime import timedelta
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d -= timedelta(days=1)
    return d


def compute_verdict(
    *,
    snapshot: dict[str, Any],
    profile: ModeProfile,
    as_of: date | None = None,
    now: datetime | None = None,
) -> StewardVerdict:
    now = now or datetime.now()
    as_of = as_of or now.date()
    checks: list[dict[str, Any]] = []
    blocking: list[str] = []
    warnings: list[str] = []

    eod_latest = _as_date(snapshot.get("eod_latest"))
    eod_lag = _day_lag(as_of, eod_latest)
    eod_max_lag = _int_freshness(profile, "eod_max_lag_days", default=1)
    checks.append(_check("eod_freshness", eod_latest, eod_max_lag, eod_lag))
    if eod_latest is None or eod_lag > eod_max_lag:
        blocking.append("eod_stale")

    stage_latest = _as_date(snapshot.get("stage_latest"))
    stage_lag = _day_lag(as_of, stage_latest)
    checks.append(_check("stage_snapshot_freshness", stage_latest, eod_max_lag, stage_lag))
    if stage_latest is None or stage_lag > eod_max_lag:
        warnings.append("stage_snapshot_stale")

    if "fno_max_lag_days" in profile.required_freshness:
        fno_latest = _as_date(snapshot.get("fno_latest"))
        fno_max_lag = _int_freshness(profile, "fno_max_lag_days", default=1)
        fno_lag = _day_lag(as_of, fno_latest)
        checks.append(_check("fno_freshness", fno_latest, fno_max_lag, fno_lag))
        if fno_latest is None or fno_lag > fno_max_lag:
            warnings.append("fno_stale")

    if "fundamentals_max_age_days" in profile.required_freshness:
        financials_latest = _as_date(snapshot.get("financials_latest"))
        fundamentals_max_age = _int_freshness(profile, "fundamentals_max_age_days", default=21)
        fundamentals_lag = _day_lag(as_of, financials_latest)
        checks.append(_check("fundamentals_freshness", financials_latest, fundamentals_max_age, fundamentals_lag))
        if financials_latest is None or fundamentals_lag > fundamentals_max_age:
            warnings.append("fundamentals_stale")

    if "intraday_max_age_minutes" in profile.required_freshness:
        intraday_latest = _as_datetime(snapshot.get("intraday_latest"))
        intraday_max_age = _int_freshness(profile, "intraday_max_age_minutes", default=5)
        intraday_age = _minute_lag(now, intraday_latest)
        checks.append(_check("intraday_freshness", intraday_latest, intraday_max_age, intraday_age))
        if intraday_latest is None or intraday_age > intraday_max_age:
            blocking.append("intraday_stale")

    universe = {
        "total_symbols": int(snapshot.get("total_symbols") or 0),
        "liquid_symbols": int(snapshot.get("liquid_symbols") or 0),
        "analyzed_symbols": int(snapshot.get("analyzed_symbols") or 0),
        "filters": list(snapshot.get("filters") or LIQUIDITY_FILTERS),
    }
    if universe["total_symbols"] <= 0:
        blocking.append("universe_empty")

    data_status = "blocked" if blocking else "degraded" if warnings else "usable"
    remediation = _remediation(blocking)
    return StewardVerdict(
        as_of=as_of,
        data_status=data_status,
        blocking_gaps=blocking,
        non_blocking_gaps=warnings,
        universe=universe,
        checks=checks,
        remediation=remediation,
    )


def collect_pg_snapshot(*, dsn: str | None = None) -> dict[str, Any]:
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except Exception as exc:
        return _blocked_snapshot(f"psycopg2 unavailable: {exc}")

    try:
        with psycopg2.connect(dsn or DEFAULT_DSN) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                snapshot: dict[str, Any] = {}
                cur.execute(
                    """
                    WITH latest AS (SELECT max(trade_date) AS d FROM market.equity_eod),
                    liquid AS (
                        SELECT e.symbol
                        FROM market.equity_eod e
                        JOIN latest l ON e.trade_date = l.d
                        WHERE e.close > 100 AND COALESCE(e.volume, 0) > 100000
                    ),
                    analyzed AS (
                        SELECT l.symbol
                        FROM liquid l
                        JOIN market.equity_eod e ON e.symbol = l.symbol
                        GROUP BY l.symbol
                        HAVING count(*) >= 50
                    )
                    SELECT
                        (SELECT d FROM latest) AS eod_latest,
                        (SELECT count(DISTINCT symbol) FROM market.equity_eod e JOIN latest l ON e.trade_date = l.d) AS total_symbols,
                        (SELECT count(*) FROM liquid) AS liquid_symbols,
                        (SELECT count(*) FROM analyzed) AS analyzed_symbols
                    """
                )
                snapshot.update(dict(cur.fetchone() or {}))

                snapshot["stage_latest"] = _fetch_scalar(cur, "SELECT max(snapshot_date) FROM scores.stage_snapshots")
                snapshot["fno_latest"] = _fetch_scalar(cur, "SELECT max(trade_date) FROM derivatives.fno_eod")
                snapshot["financials_latest"] = _fetch_scalar(
                    cur,
                    "SELECT max(COALESCE(finished_at, started_at))::date FROM scores.financials_refresh_log",
                )
                snapshot["intraday_latest"] = _fetch_intraday_latest(cur)
                snapshot["filters"] = LIQUIDITY_FILTERS
                return snapshot
    except Exception as exc:
        return _blocked_snapshot(f"PostgreSQL unavailable: {exc}")


def _fetch_scalar(cur: Any, sql: str) -> Any:
    cur.execute(sql)
    row = cur.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return next(iter(row.values()), None)
    return row[0]


def _fetch_intraday_latest(cur: Any) -> Any:
    for sql in (
        "SELECT max(captured_at) FROM intraday.quote_snapshots",
        "SELECT max(snapshot_time) FROM market.intraday_snapshots",
        "SELECT max(captured_at) FROM market.intraday_snapshots",
    ):
        try:
            return _fetch_scalar(cur, sql)
        except Exception:
            continue
    return None


def _blocked_snapshot(reason: str) -> dict[str, Any]:
    return {
        "eod_latest": None,
        "stage_latest": None,
        "fno_latest": None,
        "financials_latest": None,
        "intraday_latest": None,
        "total_symbols": 0,
        "liquid_symbols": 0,
        "analyzed_symbols": 0,
        "filters": LIQUIDITY_FILTERS,
        "error": reason,
    }


def _check(name: str, value: Any, expected: int, actual: int) -> dict[str, Any]:
    return {"check": name, "value": str(value) if value is not None else None, "expected": expected, "actual": actual}


def _remediation(blocking: list[str]) -> str | None:
    if "eod_stale" in blocking or "universe_empty" in blocking:
        return "Run the daily refresh and PostgreSQL loader, then rerun /council steward."
    if "intraday_stale" in blocking:
        return "Start or refresh intraday capture, then rerun the intraday council."
    return None


def _int_freshness(profile: ModeProfile, key: str, *, default: int) -> int:
    value = profile.required_freshness.get(key, default)
    return int(value)


def _day_lag(as_of: date, value: date | None) -> int:
    if value is None:
        return 999_999
    return max(0, (as_of - value).days)


def _minute_lag(now: datetime, value: datetime | None) -> int:
    if value is None:
        return 999_999
    return max(0, int((now - value).total_seconds() // 60))


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    return datetime.fromisoformat(str(value))
