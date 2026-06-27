from datetime import date

from terminal.governance.parsers import (
    normalize_transaction_type,
    parse_complaint_signal,
    parse_deal_rows,
    parse_nse_insider_disclosures,
    parse_nse_shareholding,
    parse_screener_capital_allocation,
)


def test_parse_nse_shareholding_orders_latest_quarter_first():
    raw = {
        "data": [
            {
                "quarter": "Mar 2026",
                "promoterAndPromoterGroupShareHolding": "52.0",
                "pledgedSharesPercent": "3.0",
                "pledgedSharesPercentOfTotalShareCapital": "1.56",
                "fii": "11.0",
                "dii": "12.0",
                "public": "25.0",
            },
            {
                "quarter": "Jun 2026",
                "promoterAndPromoterGroupShareHolding": "51.0",
                "pledgedSharesPercent": "12.5",
                "pledgedSharesPercentOfTotalShareCapital": "6.38",
                "fii": "10.5",
                "dii": "12.5",
                "public": "26.0",
            },
        ]
    }

    snapshots = parse_nse_shareholding(raw)

    assert [s.quarter for s in snapshots] == ["Jun 2026", "Mar 2026"]
    assert snapshots[0].quarter_end == date(2026, 6, 30)
    assert snapshots[0].pledge_pct == 12.5


def test_parse_nse_shareholding_preserves_row_source_when_present():
    raw = {
        "data": [
            {
                "quarter": "Mar 2026",
                "promoter_pct": "14.5",
                "fii": "32",
                "dii": "39",
                "public": "14",
                "source": "screener",
            }
        ]
    }

    snapshots = parse_nse_shareholding(raw)

    assert snapshots[0].source == "screener"


def test_parse_nse_insider_disclosures_uses_real_dates_and_values():
    raw = {
        "data": [
            {
                "symbol": "AAA",
                "acqName": "Promoter One",
                "personCategory": "Promoter",
                "tdpTransactionType": "Disposal",
                "secAcq": "100000",
                "sellValue": "45000000",
                "date": "15-Feb-2026",
            },
            {
                "symbol": "AAA",
                "acqName": "Director Two",
                "personCategory": "Director",
                "tdpTransactionType": "Acquisition",
                "noSecAcq": "20000",
                "tdpVal": "12000000",
                "tdpAcqDisposalDate": "20-03-2026",
            },
        ]
    }

    disclosures = parse_nse_insider_disclosures(raw, symbol="AAA")

    assert disclosures[0].trade_date == date(2026, 2, 15)
    assert disclosures[0].transaction_type == "SELL"
    assert disclosures[0].value_cr == 4.5
    assert disclosures[1].trade_date == date(2026, 3, 20)
    assert disclosures[1].transaction_type == "BUY"
    assert disclosures[1].shares == 20000


def test_parse_nse_insider_disclosures_skips_blank_primary_fallback_fields():
    raw = {
        "data": [
            {
                "symbol": "AAA",
                "acqName": "Director Two",
                "personCategory": "Director",
                "tdpTransactionType": "Acquisition",
                "secAcq": "",
                "noSecAcq": "20000",
                "sellValue": "-",
                "buyValue": "12000000",
                "date": "",
                "tdpAcqDisposalDate": "20-03-2026",
            }
        ]
    }

    disclosures = parse_nse_insider_disclosures(raw, symbol="AAA")

    assert disclosures[0].trade_date == date(2026, 3, 20)
    assert disclosures[0].shares == 20000
    assert disclosures[0].value_cr == 1.2


def test_normalize_transaction_type_classifies_pledge_and_revoke():
    assert normalize_transaction_type("Acquisition") == "BUY"
    assert normalize_transaction_type("Disposal") == "SELL"
    assert normalize_transaction_type("Pledge Creation") == "PLEDGE"
    assert normalize_transaction_type("Revocation of Pledge") == "REVOKE_PLEDGE"
    assert normalize_transaction_type("Sale") == "SELL"
    assert normalize_transaction_type("ESOP Exercise") == "OTHER"


def test_parse_deal_rows_normalizes_bulk_and_block_values():
    rows = [
        {
            "DATE": "25-Jun-2026",
            "SYMBOL": "AAA",
            "ENTITY": "Fund A",
            "SIDE": "BUY",
            "QTY": "500000",
            "PRICE": "120.50",
            "SOURCE": "BULK_DEAL",
        }
    ]

    deals = parse_deal_rows(rows, symbol="AAA")

    assert deals[0].deal_date == date(2026, 6, 25)
    assert deals[0].value_cr == 6.03
    assert deals[0].deal_type == "BULK_DEAL"


def test_parse_deal_rows_keeps_source_separate_from_deal_type():
    rows = [
        {
            "DATE": "25-Jun-2026",
            "SYMBOL": "AAA",
            "ENTITY": "Fund A",
            "SIDE": "BUY",
            "QTY": "500000",
            "PRICE": "120.50",
            "SOURCE": "NSE_CACHE",
            "deal_type": "bulk deal",
        }
    ]

    deals = parse_deal_rows(rows, symbol="AAA")

    assert deals[0].source == "NSE_CACHE"
    assert deals[0].deal_type == "BULK_DEAL"


def test_parse_deal_rows_defaults_unknown_source_to_generic_deal_type():
    rows = [
        {
            "DATE": "25-Jun-2026",
            "SYMBOL": "AAA",
            "ENTITY": "Fund A",
            "SIDE": "BUY",
            "QTY": "500000",
            "PRICE": "120.50",
            "SOURCE": "NSE_CACHE",
        }
    ]

    deals = parse_deal_rows(rows, symbol="AAA")

    assert deals[0].source == "NSE_CACHE"
    assert deals[0].deal_type == "DEAL"


def test_parse_complaint_signal_sums_rows():
    signal = parse_complaint_signal(
        {"data": [{"totalComplaints": "10", "pendingComplaints": "1"}, {"totalComplaints": "5", "pendingComplaints": "0"}]}
    )

    assert signal.total_complaints_fy == 15
    assert signal.pending_complaints == 1
    assert signal.resolution_rate_pct == 93.3


def test_parse_complaint_signal_handles_missing_payload():
    signal = parse_complaint_signal(None)

    assert signal.total_complaints_fy == 0
    assert signal.pending_complaints == 0
    assert signal.resolution_rate_pct == 100.0


def test_parse_screener_capital_allocation_is_conservative_on_missing_values():
    payload = {
        "annual_pl": {
            "_headers": ["Mar 2024", "Mar 2025", "Mar 2026"],
            "Net Profit": ["100", "120", "150"],
            "Dividend Payout %": ["20", "25", "30"],
        },
        "cash_flow": {
            "_headers": ["Mar 2024", "Mar 2025", "Mar 2026"],
            "Cash from Operating Activity": ["90", "130", "170"],
        },
        "ratios": {"Dividend Yield": "1.2"},
    }

    signal = parse_screener_capital_allocation(payload)

    assert signal.dividend_payout_consistency == "High"
    assert signal.fcf_to_net_income_ratio_3y == 1.1
    assert signal.source == "screener"


def test_parse_screener_capital_allocation_preserves_period_alignment():
    payload = {
        "annual_pl": {
            "_headers": ["Mar 2024", "Mar 2025", "Mar 2026"],
            "Net Profit": ["100", "-", "300"],
            "Dividend Payout %": ["20", "0", "30"],
        },
        "cash_flow": {
            "_headers": ["Mar 2024", "Mar 2025", "Mar 2026"],
            "Cash from Operating Activity": ["90", "999", "150"],
        },
    }

    signal = parse_screener_capital_allocation(payload)

    assert signal.fcf_to_net_income_ratio_3y == 0.6


def test_parse_screener_capital_allocation_aligns_by_headers_and_aliases():
    payload = {
        "annual_pl": {
            "_headers": ["Mar 2024", "Mar 2025", "TTM"],
            "Net Profit+": ["100", "200", "999"],
            "Dividend Payout %": ["20", "30", "0"],
        },
        "cash_flow": {
            "_headers": ["Mar 2024", "Mar 2026", "Mar 2025"],
            "Cash from Operating Activity+": ["90", "999", "110"],
        },
    }

    signal = parse_screener_capital_allocation(payload)

    assert signal.fcf_to_net_income_ratio_3y == 0.7


def test_parse_screener_capital_allocation_handles_zero_denominator_and_bad_ratios():
    payload = {
        "annual_pl": {
            "_headers": ["Mar 2025", "Mar 2026"],
            "Net Profit": ["100", "-100"],
            "Dividend Payout %": ["0", "0"],
        },
        "cash_flow": {
            "_headers": ["Mar 2025", "Mar 2026"],
            "Cash from Operating Activity": ["90", "110"],
        },
        "ratios": "bad",
    }

    signal = parse_screener_capital_allocation(payload)

    assert signal.fcf_to_net_income_ratio_3y is None
    assert signal.dividend_yield_5y_avg is None
