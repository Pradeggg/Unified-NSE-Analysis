"""PG-cache backed fundamentals enrichment for Strategy Council evidence packs.

This module turns the structured rows we cache in ``scores.quarterly_results``
/ ``scores.annual_results`` / ``scores.balance_sheet`` / ``scores.cash_flow``
into deterministic derived facts that the Council's LLM strategists and
critics can quote without re-doing arithmetic in natural language.

All metrics are computed with **strict point-in-time semantics**: rows
whose ``period_end`` is after ``as_of`` are dropped before computation,
which is the same look-ahead guard the historic-prices loader applies. This
is what eliminates the "data leakage" warning the Council surfaced in the
GESHIP report — the cache always returns the latest scrape, but evidence
construction filters by the run's as_of date.

Coverage status: a symbol that has no rows in PG is recorded on
``pack.missing`` as ``"fundamentals"``, mirroring how regime / factor
exposure announce their absence.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable

from backtesting.strategy_council.types import EvidencePack
from terminal.financials_cache import read_financials


__all__ = [
    "compute_fundamentals",
    "enrich_with_fundamentals",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _point_in_time(rows: list[dict[str, Any]], as_of: date | None) -> list[dict[str, Any]]:
    """Drop rows whose ``period_end`` is strictly after ``as_of``.

    Rows with ``period_end IS NULL`` (e.g. TTM / FY labels with no fixed
    month-end) are kept conservatively — the cache writer only stores TTM
    when it appears on the same page as historical rows, and dropping it
    would lose the most recent data point for non-quarterly-reporting
    companies.
    """
    if as_of is None:
        return list(rows)
    out: list[dict[str, Any]] = []
    for r in rows:
        pe = _as_date(r.get("period_end"))
        if pe is None or pe <= as_of:
            out.append(r)
    return out


def _newest_first(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        list(rows),
        key=lambda r: (_as_date(r.get("period_end")) or date.min, r.get("fetched_at") or datetime.min),
        reverse=True,
    )


def _pct_change(curr: float | None, prev: float | None) -> float | None:
    if curr is None or prev is None:
        return None
    if abs(prev) < 1e-9:
        return None
    return round(((curr - prev) / abs(prev)) * 100.0, 2)


def _cagr(latest: float | None, base: float | None, years: float) -> float | None:
    if latest is None or base is None or years <= 0:
        return None
    if base <= 0 or latest <= 0:
        return None
    return round(((latest / base) ** (1.0 / years) - 1.0) * 100.0, 2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_fundamentals(
    symbol: str,
    *,
    as_of: date | None = None,
    dsn: str | None = None,
) -> dict[str, Any]:
    """Read PG cache, drop look-ahead rows, derive headline + trend metrics.

    Returns a dict shaped for ``EvidencePack.fundamental``. When the cache
    is empty the dict has ``available=False`` and a ``reason`` field so the
    council still surfaces the gap explicitly.
    """
    fin = read_financials(symbol, dsn=dsn)

    quarters_all = _newest_first(fin.get("quarterly") or [])
    annual_all = _newest_first(fin.get("annual") or [])
    bs_all = _newest_first(fin.get("balance_sheet") or [])
    cf_all = _newest_first(fin.get("cash_flow") or [])

    quarters = _point_in_time(quarters_all, as_of)
    annual = _point_in_time(annual_all, as_of)
    bs = _point_in_time(bs_all, as_of)
    cf = _point_in_time(cf_all, as_of)

    if not (quarters or annual or bs or cf):
        return {
            "available": False,
            "reason": "no rows in scores.* cache for this symbol",
            "as_of": as_of.isoformat() if as_of else None,
        }

    out: dict[str, Any] = {
        "available": True,
        "source": "pg_cache (scores.*)",
        "as_of": as_of.isoformat() if as_of else None,
        "rows_used": {
            "quarterly": len(quarters),
            "annual": len(annual),
            "balance_sheet": len(bs),
            "cash_flow": len(cf),
        },
    }

    # --- Latest quarter headline ------------------------------------------
    if quarters:
        q0 = quarters[0]
        out["latest_quarter"] = {
            "period_label": q0.get("period_label"),
            "period_end": _as_date(q0.get("period_end")).isoformat() if _as_date(q0.get("period_end")) else None,
            "revenue": _as_float(q0.get("revenue")),
            "pat": _as_float(q0.get("pat")),
            "eps": _as_float(q0.get("eps")),
            "operating_profit": _as_float(q0.get("operating_profit")),
            "opm_pct": _as_float(q0.get("opm_pct")),
        }

        # YoY: same-quarter-last-year is index 4 if we have ≥5 rows
        if len(quarters) >= 5:
            q_yoy = quarters[4]
            out["yoy_growth"] = {
                "vs_period": q_yoy.get("period_label"),
                "revenue_pct": _pct_change(_as_float(q0.get("revenue")), _as_float(q_yoy.get("revenue"))),
                "pat_pct": _pct_change(_as_float(q0.get("pat")), _as_float(q_yoy.get("pat"))),
                "eps_pct": _pct_change(_as_float(q0.get("eps")), _as_float(q_yoy.get("eps"))),
                "opm_delta_pp": (
                    round(_as_float(q0.get("opm_pct")) - _as_float(q_yoy.get("opm_pct")), 2)
                    if _as_float(q0.get("opm_pct")) is not None and _as_float(q_yoy.get("opm_pct")) is not None
                    else None
                ),
            }

        # QoQ: previous quarter is index 1
        if len(quarters) >= 2:
            q_qoq = quarters[1]
            out["qoq_growth"] = {
                "vs_period": q_qoq.get("period_label"),
                "revenue_pct": _pct_change(_as_float(q0.get("revenue")), _as_float(q_qoq.get("revenue"))),
                "pat_pct": _pct_change(_as_float(q0.get("pat")), _as_float(q_qoq.get("pat"))),
            }

    # --- Annual: 3y CAGR + latest annual snapshot --------------------------
    if annual:
        a0 = annual[0]
        out["latest_annual"] = {
            "period_label": a0.get("period_label"),
            "revenue": _as_float(a0.get("revenue")),
            "pat": _as_float(a0.get("pat")),
            "eps": _as_float(a0.get("eps")),
            "opm_pct": _as_float(a0.get("opm_pct")),
        }
        if len(annual) >= 4:
            a_base = annual[3]
            out["cagr_3y"] = {
                "from_period": a_base.get("period_label"),
                "to_period": a0.get("period_label"),
                "revenue_pct": _cagr(_as_float(a0.get("revenue")), _as_float(a_base.get("revenue")), 3),
                "pat_pct": _cagr(_as_float(a0.get("pat")), _as_float(a_base.get("pat")), 3),
            }

    # --- Balance sheet: leverage + leverage trajectory ---------------------
    if bs:
        b0 = bs[0]
        out["balance_sheet_latest"] = {
            "period_label": b0.get("period_label"),
            "borrowings": _as_float(b0.get("borrowings")),
            "investments": _as_float(b0.get("investments")),
            "net_debt": _as_float(b0.get("net_debt")),
            "total_assets": _as_float(b0.get("total_assets")),
            "reserves": _as_float(b0.get("reserves")),
        }
        if len(bs) >= 2:
            b_prev = bs[1]
            out["leverage_trend"] = {
                "vs_period": b_prev.get("period_label"),
                "borrowings_change_pct": _pct_change(_as_float(b0.get("borrowings")), _as_float(b_prev.get("borrowings"))),
                "net_debt_change_pct": _pct_change(_as_float(b0.get("net_debt")), _as_float(b_prev.get("net_debt"))),
            }

    # --- Cash flow: cash conversion + FCF proxy ----------------------------
    if cf:
        c0 = cf[0]
        ocf = _as_float(c0.get("operating_cf"))
        icf = _as_float(c0.get("investing_cf"))
        out["cash_flow_latest"] = {
            "period_label": c0.get("period_label"),
            "operating_cf": ocf,
            "investing_cf": icf,
            "financing_cf": _as_float(c0.get("financing_cf")),
            "net_cf": _as_float(c0.get("net_cf")),
        }
        # FCF proxy: OCF - |investing_cf| (investing is typically negative).
        # We only quote it if OCF is positive and investing is negative
        # (the usual case for a non-IPO-year company).
        if ocf is not None and icf is not None and icf < 0:
            out["cash_flow_latest"]["fcf_proxy"] = round(ocf + icf, 2)

        # Cash conversion: OCF / PAT for the matching annual period
        if annual and out.get("latest_annual"):
            pat_annual = out["latest_annual"].get("pat")
            if ocf is not None and pat_annual:
                out["cash_flow_latest"]["ocf_to_pat"] = round(ocf / pat_annual, 2)

    return out


def enrich_with_fundamentals(
    pack: EvidencePack,
    *,
    as_of: date | str | None = None,
    dsn: str | None = None,
) -> EvidencePack:
    """Attach cached fundamentals + derived metrics to an evidence pack."""

    if isinstance(as_of, str):
        try:
            as_of = date.fromisoformat(as_of[:10])
        except ValueError:
            as_of = None
    elif as_of is None and pack.as_of:
        try:
            as_of = date.fromisoformat(str(pack.as_of)[:10])
        except ValueError:
            as_of = None

    try:
        fund = compute_fundamentals(pack.symbol, as_of=as_of, dsn=dsn)
    except Exception as exc:  # pragma: no cover - defensive
        pack.missing.append("fundamentals")
        pack.source_trail.append(f"fundamentals: ERROR: {exc}")
        return pack

    pack.fundamental["pg_cache"] = fund
    if fund.get("available"):
        pack.freshness["fundamentals"] = fund.get("latest_quarter", {}).get("period_label", "available")
        bits = []
        lq = fund.get("latest_quarter") or {}
        if lq.get("period_label"):
            bits.append(f"q={lq['period_label']}")
        yoy = fund.get("yoy_growth") or {}
        if yoy.get("revenue_pct") is not None:
            bits.append(f"yoy_rev={yoy['revenue_pct']}%")
        if yoy.get("pat_pct") is not None:
            bits.append(f"yoy_pat={yoy['pat_pct']}%")
        bsl = fund.get("balance_sheet_latest") or {}
        if bsl.get("net_debt") is not None:
            bits.append(f"net_debt={bsl['net_debt']}")
        pack.source_trail.append("fundamentals: " + ", ".join(bits) if bits else "fundamentals: available")
    else:
        pack.missing.append("fundamentals")
        pack.source_trail.append(f"fundamentals: unavailable ({fund.get('reason')})")

    return pack
