"""Tests for live stock-futures bulk fetcher in terminal/fno_data.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from terminal import fno_data


@pytest.fixture(autouse=True)
def _clear_bulk_cache():
    fno_data._STOCK_FUT_BULK_CACHE["ts"] = 0.0
    fno_data._STOCK_FUT_BULK_CACHE["rows"] = None
    yield
    fno_data._STOCK_FUT_BULK_CACHE["ts"] = 0.0
    fno_data._STOCK_FUT_BULK_CACHE["rows"] = None


def _sample_payload() -> dict:
    return {
        "data": [
            {
                "underlying": "RELIANCE",
                "instrument": "Stock Futures",
                "instrumentType": "FUTSTK",
                "expiryDate": "26-May-2026",
                "lastPrice": 1355.2,
                "pChange": -0.83,
                "openInterest": 213685,
                "volume": 12335500,
                "underlyingValue": 1357.0,
            },
            {
                "underlying": "RELIANCE",
                "instrument": "Stock Futures",
                "instrumentType": "FUTSTK",
                "expiryDate": "30-Jun-2026",
                "lastPrice": 1366.3,
                "pChange": -0.61,
                "openInterest": 50000,
                "volume": 14932500,
                "underlyingValue": 1357.0,
            },
            {
                "underlying": "HDFCBANK",
                "instrument": "Stock Futures",
                "instrumentType": "FUTSTK",
                "expiryDate": "26-May-2026",
                "lastPrice": 1700.0,
                "pChange": 0.5,
                "openInterest": 100000,
                "volume": 50000,
                "underlyingValue": 1695.0,
            },
        ],
        "timestamp": "irrelevant",
    }


def _mock_session(payload, status_code=200):
    sess = MagicMock()
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = "x" if payload is not None else ""
    resp.json.return_value = payload if payload is not None else {}
    sess.get.return_value = resp
    return sess


def test_fetch_live_stock_futures_filters_by_symbol():
    sess = _mock_session(_sample_payload())
    with patch("terminal.tools._get_live_session", return_value=sess):
        result = fno_data._fetch_live_stock_futures("RELIANCE")

    assert result is not None
    assert result["symbol"] == "RELIANCE"
    assert result["source"] == "live-nse-api"
    assert result["underlying"] == 1357.0
    assert len(result["futures"]) == 2
    assert result["futures"][0]["expiry"] == "26-May-2026"
    assert result["futures"][0]["last_price"] == 1355.2
    assert result["futures"][0]["oi_change"] is None


def test_fetch_live_stock_futures_missing_symbol_returns_none():
    sess = _mock_session(_sample_payload())
    with patch("terminal.tools._get_live_session", return_value=sess):
        assert fno_data._fetch_live_stock_futures("INFY") is None


def test_fetch_live_stock_futures_empty_payload_returns_none():
    sess = _mock_session({"data": []})
    with patch("terminal.tools._get_live_session", return_value=sess):
        assert fno_data._fetch_live_stock_futures("RELIANCE") is None


def test_fetch_live_stock_futures_http_error_returns_none():
    sess = _mock_session(None, status_code=403)
    with patch("terminal.tools._get_live_session", return_value=sess):
        assert fno_data._fetch_live_stock_futures("RELIANCE") is None


def test_bulk_payload_is_cached_within_ttl():
    sess = _mock_session(_sample_payload())
    with patch("terminal.tools._get_live_session", return_value=sess):
        fno_data._fetch_live_stock_futures("RELIANCE")
        fno_data._fetch_live_stock_futures("HDFCBANK")
        fno_data._fetch_live_stock_futures("RELIANCE")
    assert sess.get.call_count == 1


def test_fetch_live_futures_routes_stock_through_bulk():
    sess = _mock_session(_sample_payload())
    with patch("terminal.tools._get_live_session", return_value=sess):
        result = fno_data.fetch_live_futures("RELIANCE")
    assert result.get("source") == "live-nse-api"
    assert result["symbol"] == "RELIANCE"
    assert len(result["futures"]) == 2


def test_fetch_live_futures_falls_back_to_eod_when_not_in_bulk():
    sess = _mock_session(_sample_payload())
    eod_dummy = {"symbol": "INFY", "source": "eod-fallback", "futures": []}
    with patch("terminal.tools._get_live_session", return_value=sess), \
         patch("terminal.fno_data._futures_from_eod", return_value=eod_dummy) as eod_mock:
        result = fno_data.fetch_live_futures("INFY")
    eod_mock.assert_called_once_with("INFY")
    assert result == eod_dummy
