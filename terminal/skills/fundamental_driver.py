from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any

from terminal.financials_cache import read_financials


@dataclass(frozen=True)
class FundamentalDriverResult:
    success: bool
    symbol: str
    metric: str
    short_answer: str
    metric_bridge: dict[str, Any] = field(default_factory=dict)
    evidence: tuple[str, ...] = ()
    interpretation: str = "insufficient_evidence"
    what_to_watch: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _num(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct_change(now: float | None, then: float | None) -> float | None:
    if now is None or then in (None, 0):
        return None
    return round(((now - then) / abs(then)) * 100.0, 2)


def _delta(now: float | None, then: float | None) -> float | None:
    if now is None or then is None:
        return None
    return round(now - then, 2)


def _sorted_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows or [],
        key=lambda row: (row.get("period_end") is not None, row.get("period_end") or row.get("period_label") or ""),
        reverse=True,
    )


def _insufficient(symbol: str, metric: str, reason: str) -> FundamentalDriverResult:
    return FundamentalDriverResult(
        success=False,
        symbol=symbol.upper(),
        metric=metric,
        short_answer=f"Insufficient financial evidence for {symbol.upper()}: {reason}.",
        interpretation="insufficient_evidence",
        warnings=(reason,),
    )


def _latest_and_prior_yoy(rows: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    ordered = _sorted_rows(rows)
    if not ordered:
        return None, None
    latest = ordered[0]
    latest_end = latest.get("period_end")
    if latest_end is not None:
        for row in ordered[1:]:
            end = row.get("period_end")
            if end is not None and end.month == latest_end.month and end.year == latest_end.year - 1:
                return latest, row
    return latest, ordered[1] if len(ordered) > 1 else None


def _diagnose_eps(symbol: str, financials: dict[str, Any]) -> FundamentalDriverResult:
    latest, prior = _latest_and_prior_yoy(financials.get("quarterly") or financials.get("annual") or [])
    if not latest or not prior:
        return _insufficient(symbol, "eps", "need at least two comparable P&L periods")

    eps_change = _pct_change(_num(latest, "eps"), _num(prior, "eps"))
    revenue_change = _pct_change(_num(latest, "revenue"), _num(prior, "revenue"))
    operating_profit_change = _pct_change(_num(latest, "operating_profit"), _num(prior, "operating_profit"))
    pat_change = _pct_change(_num(latest, "pat"), _num(prior, "pat"))
    opm_delta = _delta(_num(latest, "opm_pct"), _num(prior, "opm_pct"))
    other_income_change = _pct_change(_num(latest, "other_income"), _num(prior, "other_income"))
    interest_change = _pct_change(_num(latest, "interest"), _num(prior, "interest"))
    depreciation_change = _pct_change(_num(latest, "depreciation"), _num(prior, "depreciation"))
    pbt_change = _pct_change(_num(latest, "pbt"), _num(prior, "pbt"))
    tax_delta = _delta(_num(latest, "tax_pct"), _num(prior, "tax_pct"))

    bridge = {
        "latest_period": latest.get("period_label"),
        "comparison_period": prior.get("period_label"),
        "eps_change_pct": eps_change,
        "revenue_change_pct": revenue_change,
        "operating_profit_change_pct": operating_profit_change,
        "pat_change_pct": pat_change,
        "opm_delta_pp": opm_delta,
        "other_income_change_pct": other_income_change,
        "interest_change_pct": interest_change,
        "depreciation_change_pct": depreciation_change,
        "pbt_change_pct": pbt_change,
        "tax_delta_pp": tax_delta,
    }

    eps_down = eps_change is not None and eps_change < 0
    operating_healthy = (
        (revenue_change is not None and revenue_change >= 0)
        and (opm_delta is None or opm_delta >= -1)
        and (operating_profit_change is None or operating_profit_change >= 0)
    )
    below_ebit_pressure = (
        (interest_change is not None and interest_change >= 25)
        or (depreciation_change is not None and depreciation_change >= 25)
        or (tax_delta is not None and tax_delta >= 5)
    )
    other_income_normalized = other_income_change is not None and other_income_change <= -50

    if eps_down and operating_healthy and other_income_normalized and not below_ebit_pressure:
        short = (
            f"{symbol.upper()} EPS is down mainly because other income normalized despite stable operating performance."
        )
        interpretation = "other_income_normalization"
    elif eps_down and operating_healthy and below_ebit_pressure:
        short = (
            f"{symbol.upper()} EPS is down mainly because interest, depreciation, and tax pressure offset operating growth."
        )
        interpretation = "below_ebit_pressure"
    elif eps_down and opm_delta is not None and opm_delta < -1:
        short = (
            f"{symbol.upper()} EPS is down mainly because margin compression offset revenue growth."
        )
        interpretation = "operating_margin_pressure"
    elif eps_down and revenue_change is not None and revenue_change < 0:
        short = f"{symbol.upper()} EPS is down mainly because revenue declined."
        interpretation = "revenue_pressure"
    elif eps_down and pat_change is not None and pat_change < 0:
        short = f"{symbol.upper()} EPS is down because PAT declined versus the comparison period."
        interpretation = "profit_pressure"
    else:
        short = f"{symbol.upper()} EPS movement is not clearly negative from the available periods."
        interpretation = "mixed_or_stable"

    return FundamentalDriverResult(
        success=True,
        symbol=symbol.upper(),
        metric="eps",
        short_answer=short,
        metric_bridge=bridge,
        evidence=(
            f"P&L periods compared: {bridge['latest_period']} vs {bridge['comparison_period']}",
            f"EPS change: {eps_change}%",
            f"Revenue change: {revenue_change}%",
            f"Operating profit change: {operating_profit_change}%",
            f"OPM delta: {opm_delta} pp",
            f"Other income change: {other_income_change}%",
            f"Interest change: {interest_change}%",
            f"Depreciation change: {depreciation_change}%",
            f"Tax rate delta: {tax_delta} pp",
        ),
        interpretation=interpretation,
        what_to_watch=(
            "Margin recovery in the next reported quarter",
            "Interest cost and debt-funded capex trend",
            "Depreciation step-up after capacity expansion",
            "Tax-rate normalization versus prior periods",
            "Revenue growth versus the same quarter last year",
            "One-off expense, tax, or depreciation commentary",
        ),
    )


def _capital_employed(row: dict[str, Any]) -> float | None:
    total_assets = _num(row, "total_assets")
    investments = _num(row, "investments") or 0.0
    if total_assets is None:
        return None
    return total_assets - investments


def _diagnose_roce(symbol: str, financials: dict[str, Any]) -> FundamentalDriverResult:
    annual = _sorted_rows(financials.get("annual") or [])
    balance = _sorted_rows(financials.get("balance_sheet") or [])
    if len(annual) < 2 or len(balance) < 2:
        return _insufficient(symbol, "roce", "need annual P&L and balance-sheet history")

    latest_pl, prior_pl = annual[0], annual[1]
    latest_bs, prior_bs = balance[0], balance[1]
    ebit_now = _num(latest_pl, "operating_profit")
    ebit_then = _num(prior_pl, "operating_profit")
    ce_now = _capital_employed(latest_bs)
    ce_then = _capital_employed(prior_bs)
    ebit_change = _pct_change(ebit_now, ebit_then)
    ce_change = _pct_change(ce_now, ce_then)
    roce_now = round((ebit_now / ce_now) * 100, 2) if ebit_now is not None and ce_now else None
    roce_then = round((ebit_then / ce_then) * 100, 2) if ebit_then is not None and ce_then else None

    bridge = {
        "latest_period": latest_pl.get("period_label"),
        "comparison_period": prior_pl.get("period_label"),
        "latest_roce_pct": roce_now,
        "comparison_roce_pct": roce_then,
        "ebit_change_pct": ebit_change,
        "capital_employed_change_pct": ce_change,
    }

    if ebit_change is not None and ce_change is not None and ebit_change > ce_change:
        short = f"{symbol.upper()} ROCE is high because EBIT grew faster than capital employed."
        interpretation = "higher_operating_return_on_capital"
    elif ce_change is not None and ce_change < 0:
        short = f"{symbol.upper()} ROCE is high partly because capital employed shrank."
        interpretation = "lower_capital_base"
    else:
        short = f"{symbol.upper()} ROCE needs more context; EBIT and capital employed moved together."
        interpretation = "mixed_or_stable"

    return FundamentalDriverResult(
        success=True,
        symbol=symbol.upper(),
        metric="roce",
        short_answer=short,
        metric_bridge=bridge,
        evidence=(
            f"Annual periods compared: {bridge['latest_period']} vs {bridge['comparison_period']}",
            f"EBIT change: {ebit_change}%",
            f"Capital employed change: {ce_change}%",
            f"ROCE: {roce_now}% vs {roce_then}%",
        ),
        interpretation=interpretation,
        what_to_watch=(
            "Whether new capex increases capital employed",
            "Operating profit growth versus asset growth",
            "Working-capital reversal or margin normalization",
        ),
        warnings=(
            "ROCE uses a capital employed proxy of total assets minus investments because current liabilities are unavailable.",
        ),
    )


def _diagnose_simple(symbol: str, metric: str, financials: dict[str, Any]) -> FundamentalDriverResult:
    rows = financials.get("quarterly") or financials.get("annual") or []
    latest, prior = _latest_and_prior_yoy(rows)
    if not latest or not prior:
        return _insufficient(symbol, metric, "need at least two comparable financial periods")

    if metric == "margin":
        bridge = {
            "latest_period": latest.get("period_label"),
            "comparison_period": prior.get("period_label"),
            "opm_delta_pp": _delta(_num(latest, "opm_pct"), _num(prior, "opm_pct")),
            "revenue_change_pct": _pct_change(_num(latest, "revenue"), _num(prior, "revenue")),
        }
        short = f"{symbol.upper()} margin movement is explained by the OPM bridge in available P&L periods."
        watch = ("Gross/operating margin trend", "Input cost and pricing commentary")
    elif metric == "debt":
        balance = _sorted_rows(financials.get("balance_sheet") or [])
        if len(balance) < 2:
            return _insufficient(symbol, metric, "need balance-sheet history")
        bridge = {
            "latest_period": balance[0].get("period_label"),
            "comparison_period": balance[1].get("period_label"),
            "borrowings_change_pct": _pct_change(_num(balance[0], "borrowings"), _num(balance[1], "borrowings")),
            "net_debt_change_pct": _pct_change(_num(balance[0], "net_debt"), _num(balance[1], "net_debt")),
        }
        short = f"{symbol.upper()} debt movement is explained by borrowings and net-debt changes."
        watch = ("Capex funding", "Interest cost", "Cash and investments")
    else:
        cash = _sorted_rows(financials.get("cash_flow") or [])
        if len(cash) < 1:
            return _insufficient(symbol, metric, "need cash-flow history")
        latest_cash = cash[0]
        bridge = {
            "latest_period": latest_cash.get("period_label"),
            "operating_cf": _num(latest_cash, "operating_cf"),
            "investing_cf": _num(latest_cash, "investing_cf"),
            "net_cf": _num(latest_cash, "net_cf"),
        }
        short = f"{symbol.upper()} cash-flow quality depends on operating cash flow versus investing and financing flows."
        watch = ("Operating cash conversion", "Receivables and inventory", "Capex intensity")

    return FundamentalDriverResult(
        success=True,
        symbol=symbol.upper(),
        metric=metric,
        short_answer=short,
        metric_bridge=bridge,
        evidence=(f"Metric bridge built for {metric}",),
        interpretation=f"{metric}_bridge",
        what_to_watch=tuple(watch),
    )


def diagnose_fundamental_driver(
    symbol: str,
    metric: str,
    *,
    financials: dict[str, Any] | None = None,
    dsn: str | None = None,
    max_age_days: int = 90,
) -> FundamentalDriverResult:
    sym = symbol.strip().upper()
    normalized_metric = metric.strip().lower().replace("_", "").replace("-", "")
    if normalized_metric == "cashflow":
        normalized_metric = "cashflow"
    if financials is None:
        financials = read_financials(sym, dsn=dsn)

    if not any(financials.get(section) for section in ("quarterly", "annual", "balance_sheet", "cash_flow")):
        return _insufficient(sym, normalized_metric, "no financial statement rows are available")

    warnings = _financial_warnings(financials, max_age_days=max_age_days)

    if normalized_metric == "eps":
        result = _diagnose_eps(sym, financials)
    elif normalized_metric == "roce":
        result = _diagnose_roce(sym, financials)
    elif normalized_metric in {"margin", "debt", "cashflow"}:
        result = _diagnose_simple(sym, normalized_metric, financials)
    else:
        result = _insufficient(sym, normalized_metric, f"unsupported metric '{metric}'")
    if warnings:
        return replace(result, warnings=tuple(dict.fromkeys((*result.warnings, *warnings))))
    return result


def _financial_warnings(financials: dict[str, Any], *, max_age_days: int) -> tuple[str, ...]:
    fetched_values = []
    for section in ("quarterly", "annual", "balance_sheet", "cash_flow"):
        for row in financials.get(section) or []:
            fetched_at = row.get("fetched_at")
            if isinstance(fetched_at, datetime):
                fetched_values.append(fetched_at)
    if not fetched_values or max_age_days <= 0:
        return ()
    latest_fetch = max(fetched_values)
    if latest_fetch.tzinfo is None:
        latest_fetch = latest_fetch.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - latest_fetch).days
    if age_days > max_age_days:
        return (f"Financial statement cache is stale: latest fetch is {age_days} days old.",)
    return ()
