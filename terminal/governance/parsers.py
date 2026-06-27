from __future__ import annotations

import calendar
import math
import re
from datetime import date, datetime
from typing import Any

from terminal.governance.models import (
    CapitalAllocationSignal,
    ComplaintSignal,
    DealEvent,
    GovernanceAnnouncement,
    InsiderDisclosure,
    ShareholdingSnapshot,
)


_MISSING_VALUES = {"", "-", "na", "n/a", "none", "null", "nan"}
_DEAL_TYPE_VALUES = {"BULK_DEAL", "BLOCK_DEAL", "BULK", "BLOCK"}


def _first(row: dict[str, Any], *keys: str) -> Any:
    if not isinstance(row, dict):
        return None
    for key in keys:
        if key in row and not _is_missing(row[key]):
            return row[key]
    return None


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in _MISSING_VALUES
    return False


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip()
    if text.lower() in _MISSING_VALUES:
        return None
    text = text.replace(",", "").replace("%", "").replace("₹", "").strip()
    text = re.sub(r"^(rs\.?|inr)\s*", "", text, flags=re.IGNORECASE)
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def to_int(value: Any) -> int:
    number = to_float(value)
    return int(number) if number is not None else 0


def parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if text.lower() in _MISSING_VALUES:
        return None
    if len(text) >= 10:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d %b %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_quarter_end(label: str) -> date | None:
    text = str(label or "").strip()
    if not text:
        return None
    for fmt in ("%b %Y", "%B %Y"):
        try:
            parsed = datetime.strptime(text, fmt)
            last_day = calendar.monthrange(parsed.year, parsed.month)[1]
            return date(parsed.year, parsed.month, last_day)
        except ValueError:
            continue
    return None


def normalize_transaction_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "revoke" in text or "revocation" in text:
        return "REVOKE_PLEDGE"
    if "pledge" in text:
        return "PLEDGE"
    if "buy" in text or "acquisition" in text:
        return "BUY"
    if "sell" in text or "sale" in text or "disposal" in text:
        return "SELL"
    return "OTHER"


def _rows(raw: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    data = raw.get("data") or []
    return data if isinstance(data, list) else []


def _normalize_label(value: Any, *, default: str = "") -> str:
    text = str(value or default).strip()
    return re.sub(r"[\s-]+", "_", text).upper()


def _normalize_deal_type(row: dict[str, Any]) -> str:
    explicit = _normalize_label(_first(row, "deal_type", "DEAL_TYPE", "DEAL", "type"), default="")
    if explicit:
        return explicit
    source_label = _normalize_label(_first(row, "SOURCE", "source"), default="")
    return source_label if source_label in _DEAL_TYPE_VALUES else "DEAL"


def parse_nse_shareholding(raw: dict[str, Any]) -> list[ShareholdingSnapshot]:
    snapshots: list[ShareholdingSnapshot] = []
    for row in _rows(raw):
        quarter = str(_first(row, "quarter", "QUARTER") or "")
        snapshots.append(
            ShareholdingSnapshot(
                quarter=quarter,
                quarter_end=parse_quarter_end(quarter),
                promoter_pct=to_float(_first(row, "promoterAndPromoterGroupShareHolding", "promoter_pct")),
                pledge_pct=to_float(_first(row, "pledgedSharesPercent", "pledge_pct")),
                pledge_of_total_pct=to_float(
                    _first(row, "pledgedSharesPercentOfTotalShareCapital", "pledge_of_total_pct")
                ),
                fii_pct=to_float(_first(row, "fii", "FII")),
                dii_pct=to_float(_first(row, "dii", "DII")),
                public_pct=to_float(_first(row, "public", "PUBLIC")),
                source="NSE",
            )
        )
    return sorted(snapshots, key=lambda item: item.quarter_end or date.min, reverse=True)


def parse_nse_insider_disclosures(raw: dict[str, Any], *, symbol: str) -> list[InsiderDisclosure]:
    target = symbol.upper()
    disclosures: list[InsiderDisclosure] = []
    for row in _rows(raw):
        row_symbol = str(_first(row, "symbol", "SYMBOL") or symbol).upper()
        if row_symbol != target:
            continue
        value = to_float(_first(row, "sellValue", "buyValue", "secVal", "tdpVal")) or 0.0
        disclosures.append(
            InsiderDisclosure(
                trade_date=parse_date(_first(row, "date", "tdpAcqDisposalDate", "acqfromDt")),
                symbol=row_symbol,
                name=str(_first(row, "acqName", "name") or ""),
                category=str(_first(row, "personCategory", "category") or ""),
                transaction_type=normalize_transaction_type(_first(row, "tdpTransactionType", "transaction_type")),
                shares=to_int(_first(row, "secAcq", "noSecAcq")),
                value_cr=round(value / 1e7, 2),
                source="NSE_PIT",
            )
        )
    return disclosures


def parse_deal_rows(rows: list[dict[str, Any]], *, symbol: str) -> list[DealEvent]:
    target = symbol.upper()
    deals: list[DealEvent] = []
    row_list = rows if isinstance(rows, list) else []
    for row in row_list:
        row_symbol = str(_first(row, "SYMBOL", "symbol") or symbol).upper()
        if row_symbol != target:
            continue
        qty = to_int(_first(row, "QTY", "qty", "quantity"))
        price = to_float(_first(row, "PRICE", "price"))
        source = str(_first(row, "SOURCE", "source") or "cache")
        deal_type = _normalize_deal_type(row)
        deals.append(
            DealEvent(
                deal_date=parse_date(_first(row, "DATE", "date", "deal_date")),
                symbol=row_symbol,
                entity=str(_first(row, "ENTITY", "entity", "clientName") or ""),
                side=str(_first(row, "SIDE", "side") or "").upper(),
                qty=qty,
                price=price,
                value_cr=round(qty * (price or 0.0) / 1e7, 2),
                deal_type=deal_type,
                source=source,
            )
        )
    return sorted(deals, key=lambda item: item.deal_date or date.min, reverse=True)


def parse_governance_announcements(rows: list[dict[str, Any]], *, symbol: str) -> list[GovernanceAnnouncement]:
    target = symbol.upper()
    announcements: list[GovernanceAnnouncement] = []
    row_list = rows if isinstance(rows, list) else []
    for row in row_list:
        row_symbol = str(_first(row, "SYMBOL", "symbol") or symbol).upper()
        if row_symbol != target:
            continue
        subject = str(_first(row, "SUBJECT", "subject", "desc", "announcement") or "")
        text = subject.lower()
        if any(term in text for term in ("resignation", "auditor", "fine", "penalty")):
            severity = "red"
            category = "governance_risk"
        elif any(term in text for term in ("board", "agm", "analyst")):
            severity = "amber"
            category = "governance_event"
        else:
            severity = "green"
            category = "general"
        announcements.append(
            GovernanceAnnouncement(
                announcement_date=parse_date(_first(row, "date", "EVENT_DATE", "announcement_date")),
                symbol=row_symbol,
                subject=subject,
                category=category,
                severity=severity,
                source=str(_first(row, "SOURCE", "source") or ""),
                url=_first(row, "url", "URL", "attachment"),
            )
        )
    return announcements


def parse_complaint_signal(raw: dict[str, Any] | None) -> ComplaintSignal:
    total = 0
    pending = 0
    for row in _rows(raw):
        total += to_int(_first(row, "totalComplaints", "total"))
        pending += to_int(_first(row, "pendingComplaints", "pending"))
    rate = 100.0 if total == 0 else round((total - pending) / total * 100, 1)
    return ComplaintSignal(total, pending, rate, "NSE_COMPLAINTS")


def _numeric_series(table: dict[str, Any], *keys: str) -> list[float]:
    values = _series_values(table, *keys)
    return [number for value in values if (number := to_float(value)) is not None]


def _series_values(table: dict[str, Any], *keys: str) -> list[Any]:
    values = None
    if isinstance(table, dict):
        for key in keys:
            if key in table:
                values = table.get(key)
                break
    values = values if values is not None else []
    if not isinstance(values, list):
        values = [values]
    return values


def _series_by_period(table: dict[str, Any], *keys: str) -> dict[str, Any]:
    headers = _series_values(table, "_headers")
    values = _series_values(table, *keys)
    if not headers:
        return {str(idx): value for idx, value in enumerate(values)}
    return {str(header): value for header, value in zip(headers, values, strict=False)}


def parse_screener_capital_allocation(payload: dict[str, Any] | None) -> CapitalAllocationSignal | None:
    if not payload:
        return None
    annual_pl = payload.get("annual_pl") or payload.get("annual") or {}
    cash_flow = payload.get("cash_flow") or {}
    ratios = payload.get("ratios") if isinstance(payload.get("ratios"), dict) else {}

    dividends = _numeric_series(annual_pl, "Dividend Payout %", "Dividend Payout%")
    if not dividends:
        consistency = "Unknown"
    else:
        positive_ratio = sum(1 for value in dividends if value > 0) / len(dividends)
        if positive_ratio >= 0.8:
            consistency = "High"
        elif positive_ratio >= 0.5:
            consistency = "Medium"
        elif positive_ratio > 0:
            consistency = "Low"
        else:
            consistency = "None"

    profits_by_period = _series_by_period(annual_pl, "Net Profit", "Net Profit+")
    cash_flows_by_period = _series_by_period(
        cash_flow, "Cash from Operating Activity", "Cash from Operating Activity+"
    )
    common_periods = [
        period
        for period in profits_by_period
        if period in cash_flows_by_period and period.strip().lower() != "ttm"
    ][-3:]
    paired = []
    for period in common_periods:
        cfo = to_float(cash_flows_by_period[period])
        profit = to_float(profits_by_period[period])
        if cfo is not None and profit not in (None, 0):
            paired.append((cfo, profit))
    fcf_ratio = None
    if paired:
        denominator = sum(profit for _, profit in paired)
        if denominator:
            fcf_ratio = round(sum(cfo for cfo, _ in paired) / denominator, 1)

    return CapitalAllocationSignal(
        dividend_payout_consistency=consistency,
        dividend_yield_5y_avg=to_float(ratios.get("Dividend Yield")),
        buyback_count_5y=0,
        fcf_to_net_income_ratio_3y=fcf_ratio,
        esop_dilution_pct_annual=None,
        acquisitions_goodwill_impairment=False,
        source="screener",
    )
