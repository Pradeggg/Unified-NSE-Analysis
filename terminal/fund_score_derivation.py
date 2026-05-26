"""Derive enhanced fundamental sub-scores from a screener.in payload.

This Python derivation approximates the R `fn_get_enhanced_fund_score`
formula in ``core/screenerdata.R``: the final ENHANCED_FUND_SCORE is a
Minervini-style weighted average of four sub-scores ::

    enhanced = 0.40 * earnings_quality
             + 0.25 * sales_growth
             + 0.20 * financial_strength
             + 0.15 * institutional_backing

The R version uses dozens of micro-component scores from
``superperformance()``; we use a smaller, robust set of metrics that
``terminal.web_research.scrape_screener_in`` reliably populates
(annual_pl, quarterly, balance_sheet, ratios, shareholding, cash_flow).

Each sub-score is bounded [0, 100]. Missing data falls back to a
slightly-above-neutral default (55) so we never punish a stock just
because screener didn't expose a section. Callers receive a dict with
``enhanced_fund_score``, the four sub-scores, and an ``inputs`` block
documenting the raw metrics used (helpful for debugging / UI tooltips).
"""
from __future__ import annotations

from typing import Any, Mapping

# ─── default neutral fallback (matches R code's behavior) ─────────────────────
_DEFAULT = 55.0


# ─────────────────────────────────────────────────────────────────────────────
# Number parsing helpers
# ─────────────────────────────────────────────────────────────────────────────

def _to_float(v: Any) -> float | None:
    """Parse a screener cell ('1,23,456', '27%', '-12.5') into a float."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s or s.lower() in ("n/a", "na", "--", "-"):
        return None
    s = s.replace(",", "").replace("%", "").replace("₹", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _last_n(values: list, n: int) -> list[float]:
    out: list[float] = []
    for v in values[-n:]:
        f = _to_float(v)
        if f is not None:
            out.append(f)
    return out


def _yoy_growth(values: list) -> float | None:
    """Latest YoY growth % between last two parseable values."""
    parsed = _last_n(values, 8)
    if len(parsed) < 2 or parsed[-2] == 0:
        return None
    return (parsed[-1] - parsed[-2]) / abs(parsed[-2]) * 100.0


def _cagr(values: list, years: int) -> float | None:
    parsed = _last_n(values, years + 1)
    if len(parsed) < 2 or parsed[0] <= 0 or parsed[-1] <= 0:
        return None
    span = len(parsed) - 1
    try:
        return ((parsed[-1] / parsed[0]) ** (1.0 / span) - 1.0) * 100.0
    except (ValueError, ZeroDivisionError):
        return None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


# ─────────────────────────────────────────────────────────────────────────────
# Banded scoring (mirrors the R bandings)
# ─────────────────────────────────────────────────────────────────────────────

def _band_growth(g: float | None) -> float | None:
    """Score for a growth rate (Sales/PAT YoY %)."""
    if g is None:
        return None
    if g >= 30:
        return 95.0
    if g >= 20:
        return 90.0
    if g >= 15:
        return 85.0
    if g >= 10:
        return 75.0
    if g >= 5:
        return 65.0
    if g >= 0:
        return 55.0
    if g >= -10:
        return 40.0
    return 25.0


def _band_roce(roce: float | None) -> float | None:
    if roce is None:
        return None
    if roce >= 30:
        return 95.0
    if roce >= 20:
        return 88.0
    if roce >= 15:
        return 78.0
    if roce >= 10:
        return 65.0
    if roce >= 5:
        return 50.0
    return 35.0


def _band_roe(roe: float | None) -> float | None:
    if roe is None:
        return None
    if roe >= 25:
        return 92.0
    if roe >= 17:
        return 82.0
    if roe >= 12:
        return 70.0
    if roe >= 8:
        return 60.0
    return 45.0


def _band_opm(opm: float | None) -> float | None:
    if opm is None:
        return None
    if opm >= 30:
        return 90.0
    if opm >= 20:
        return 80.0
    if opm >= 12:
        return 68.0
    if opm >= 6:
        return 55.0
    return 40.0


def _band_debt_equity(de: float | None) -> float | None:
    """Lower is better."""
    if de is None:
        return None
    if de <= 0.1:
        return 92.0
    if de <= 0.3:
        return 82.0
    if de <= 0.6:
        return 70.0
    if de <= 1.0:
        return 58.0
    if de <= 2.0:
        return 45.0
    return 30.0


def _band_cfo_op(pct: float | None) -> float | None:
    """Cash from Operating / Operating Profit. ≥80% is healthy."""
    if pct is None:
        return None
    if pct >= 90:
        return 90.0
    if pct >= 75:
        return 78.0
    if pct >= 60:
        return 65.0
    if pct >= 40:
        return 50.0
    return 35.0


def _band_promoter(p: float | None) -> float | None:
    if p is None:
        return None
    if p >= 60:
        return 85.0
    if p >= 50:
        return 78.0
    if p >= 40:
        return 70.0
    if p >= 25:
        return 60.0
    return 50.0


def _band_institutional(fii_plus_dii: float | None) -> float | None:
    if fii_plus_dii is None:
        return None
    if fii_plus_dii >= 40:
        return 92.0
    if fii_plus_dii >= 25:
        return 82.0
    if fii_plus_dii >= 15:
        return 72.0
    if fii_plus_dii >= 8:
        return 62.0
    if fii_plus_dii >= 3:
        return 52.0
    return 42.0


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def _avg(parts: list[float | None], default: float = _DEFAULT) -> float:
    real = [p for p in parts if p is not None]
    return _clamp(sum(real) / len(real)) if real else default


# ─────────────────────────────────────────────────────────────────────────────
# Main derivation
# ─────────────────────────────────────────────────────────────────────────────

def derive_fund_scores(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Compute enhanced fundamental scores from a screener payload.

    Returns a dict with five score keys (always present, default 55 when
    data is missing) plus an ``inputs`` block documenting raw metrics.
    """
    annual = payload.get("annual_pl") or {}
    quarterly = payload.get("quarterly") or {}
    balance = payload.get("balance_sheet") or {}
    cash = payload.get("cash_flow") or {}
    ratios = payload.get("ratios") or {}
    shareholding = payload.get("shareholding") or {}

    # ── Sales growth ────────────────────────────────────────────────────────
    sales_series = annual.get("Sales+") or annual.get("Sales") or []
    sales_yoy = _yoy_growth(sales_series)
    sales_cagr3 = _cagr(sales_series, 3)
    qtr_sales = quarterly.get("Sales+") or quarterly.get("Sales") or []
    qoq_sales = _yoy_growth(qtr_sales)
    sales_score = _avg([
        _band_growth(sales_yoy),
        _band_growth(sales_cagr3),
        _band_growth(qoq_sales),
    ])

    # ── Earnings quality ────────────────────────────────────────────────────
    pat_series = annual.get("Net Profit+") or annual.get("Net Profit") or []
    pat_yoy = _yoy_growth(pat_series)
    pat_cagr3 = _cagr(pat_series, 3)
    eps_series = annual.get("EPS in Rs") or []
    eps_yoy = _yoy_growth(eps_series)
    qtr_pat = quarterly.get("Net Profit+") or quarterly.get("Net Profit") or []
    qoq_pat = _yoy_growth(qtr_pat)
    opm_series = quarterly.get("OPM %") or annual.get("OPM %") or []
    opm_last = _last_n(opm_series, 1)
    earnings_score = _avg([
        _band_growth(pat_yoy),
        _band_growth(pat_cagr3),
        _band_growth(eps_yoy),
        _band_growth(qoq_pat),
        _band_opm(opm_last[0] if opm_last else None),
    ])

    # ── Financial strength ──────────────────────────────────────────────────
    roce = _to_float(ratios.get("ROCE"))
    roe = _to_float(ratios.get("ROE"))
    # Debt / (Equity + Reserves) from balance sheet
    debt_series = balance.get("Borrowings+") or balance.get("Borrowings") or []
    equity_series = balance.get("Equity Capital") or []
    reserves_series = balance.get("Reserves") or []
    de = None
    debt = _last_n(debt_series, 1)
    eq = _last_n(equity_series, 1)
    rs = _last_n(reserves_series, 1)
    if debt and (eq or rs):
        denom = (eq[0] if eq else 0) + (rs[0] if rs else 0)
        if denom > 0:
            de = debt[0] / denom
    # CFO/OP %
    cfo_op_series = cash.get("CFO/OP") or []
    cfo_op = _last_n(cfo_op_series, 1)
    financial_score = _avg([
        _band_roce(roce),
        _band_roe(roe),
        _band_debt_equity(de),
        _band_cfo_op(cfo_op[0] if cfo_op else None),
    ])

    # ── Institutional backing ───────────────────────────────────────────────
    promoters = _to_float(shareholding.get("Promoters"))
    fiis = _to_float(shareholding.get("FIIs"))
    diis = _to_float(shareholding.get("DIIs"))
    institutional_score = _avg([
        _band_promoter(promoters),
        _band_institutional(
            (fiis if fiis is not None else 0.0) + (diis if diis is not None else 0.0)
            if (fiis is not None or diis is not None) else None
        ),
    ])

    enhanced = _clamp(
        0.40 * earnings_score
        + 0.25 * sales_score
        + 0.20 * financial_score
        + 0.15 * institutional_score
    )

    return {
        "enhanced_fund_score": round(enhanced, 2),
        "earnings_quality": round(earnings_score, 2),
        "sales_growth": round(sales_score, 2),
        "financial_strength": round(financial_score, 2),
        "institutional_backing": round(institutional_score, 2),
        "inputs": {
            "sales_yoy_pct": sales_yoy,
            "sales_cagr3_pct": sales_cagr3,
            "qoq_sales_pct": qoq_sales,
            "pat_yoy_pct": pat_yoy,
            "pat_cagr3_pct": pat_cagr3,
            "eps_yoy_pct": eps_yoy,
            "qoq_pat_pct": qoq_pat,
            "opm_latest_pct": opm_last[0] if opm_last else None,
            "roce": roce,
            "roe": roe,
            "debt_equity": de,
            "cfo_op_pct": cfo_op[0] if cfo_op else None,
            "promoter_pct": promoters,
            "fii_pct": fiis,
            "dii_pct": diis,
        },
    }
