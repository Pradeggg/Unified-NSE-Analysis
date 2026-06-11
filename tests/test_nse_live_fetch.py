"""Regression tests for NSE live-fetch resilience.

These cover the case where the cached NSE session returns a non-JSON
body (typically an HTML splash page after cookies expire) — historically
this surfaced as a useless ``Expecting value: line 1 column 1`` error in
the rendered SOURCE TRAIL for tools like ``get_top_gainers_losers``.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from terminal import tools as nse_tools


class _Resp:
    def __init__(self, *, status_code: int = 200, text: str = "", payload=None):
        self.status_code = status_code
        if payload is not None and not text:
            text = json.dumps(payload)
        self.text = text
        self._payload = payload

    def json(self):
        if self._payload is not None:
            return self._payload
        return json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class NseGetJsonRetryTests(unittest.TestCase):
    def setUp(self):
        nse_tools._force_refresh_live_session()

    def tearDown(self):
        nse_tools._force_refresh_live_session()

    def test_nse_get_json_returns_payload_on_first_success(self):
        session = MagicMock()
        session.get.return_value = _Resp(payload={"data": [{"symbol": "AAA"}]})
        with patch("terminal.tools._get_live_session", return_value=session):
            payload = nse_tools._nse_get_json("https://example.com/x")
        self.assertEqual(payload, {"data": [{"symbol": "AAA"}]})
        session.get.assert_called_once()

    def test_nse_get_json_retries_after_html_body_and_recovers(self):
        first_session = MagicMock()
        first_session.get.return_value = _Resp(
            status_code=200,
            text="<!DOCTYPE html><html><head><title>NSE</title>",
        )
        second_session = MagicMock()
        second_session.get.return_value = _Resp(payload={"data": [{"symbol": "AAA"}]})

        sessions = iter([first_session, second_session])
        with patch("terminal.tools._get_live_session", side_effect=lambda: next(sessions)):
            payload = nse_tools._nse_get_json("https://example.com/x")

        self.assertEqual(payload, {"data": [{"symbol": "AAA"}]})
        first_session.get.assert_called_once()
        second_session.get.assert_called_once()

    def test_nse_get_json_raises_descriptive_runtime_error_on_persistent_failure(self):
        session = MagicMock()
        session.get.return_value = _Resp(status_code=200, text="")
        with patch("terminal.tools._get_live_session", return_value=session):
            with self.assertRaises(RuntimeError) as ctx:
                nse_tools._nse_get_json("https://example.com/x")
        # The message must surface the URL + the empty-body diagnosis so
        # the SOURCE TRAIL no longer reads as the opaque
        # ``Expecting value: line 1 column 1`` JSONDecodeError.
        message = str(ctx.exception)
        self.assertIn("https://example.com/x", message)
        self.assertIn("empty body", message.lower())

    def test_get_top_gainers_losers_surfaces_clean_error_on_html_body(self):
        session = MagicMock()
        session.get.return_value = _Resp(
            status_code=200,
            text="<!DOCTYPE html><html>NSE marketing splash",
        )
        with patch("terminal.tools._get_live_session", return_value=session):
            result = nse_tools.get_top_gainers_losers(index="NIFTY 500", top_n=5)

        self.assertIn("error", result)
        self.assertNotIn("Expecting value", result["error"])
        # Should reference the upstream cause + URL so the SOURCE TRAIL is useful.
        self.assertIn("NSE", result["error"])
        self.assertIn("live-analysis-variations", result["error"])

    def test_get_top_gainers_losers_returns_parsed_payload_on_success(self):
        gainers_payload = {
            "allSec": {
                "data": [
                    {"symbol": "AAA", "ltp": 100, "perChange": 5.5, "net_price": 5.0,
                     "trade_quantity": 100, "turnover": 10.0,
                     "high_price": 105, "low_price": 95,
                     "open_price": 96, "prev_price": 94.8},
                    {"symbol": "BBB", "ltp": 50, "perChange": 2.0, "net_price": 1.0,
                     "trade_quantity": 50, "turnover": 5.0,
                     "high_price": 52, "low_price": 48,
                     "open_price": 49, "prev_price": 49.0},
                ],
                "timestamp": "x",
            }
        }
        losers_payload = {
            "allSec": {
                "data": [
                    {"symbol": "ZZZ", "ltp": 50, "perChange": -4.2, "net_price": -2.2,
                     "trade_quantity": 50, "turnover": 5.0,
                     "high_price": 52, "low_price": 48,
                     "open_price": 51, "prev_price": 52.2},
                ],
                "timestamp": "x",
            }
        }

        def _route(url, timeout=10):
            if "index=gainers" in url:
                return _Resp(payload=gainers_payload)
            if "index=loosers" in url:
                return _Resp(payload=losers_payload)
            return _Resp(status_code=404, text="not found")

        session = MagicMock()
        session.get.side_effect = _route
        with patch("terminal.tools._get_live_session", return_value=session):
            result = nse_tools.get_top_gainers_losers(index="NIFTY 500", top_n=5)

        self.assertNotIn("error", result)
        self.assertEqual(result["bucket"], "allSec")
        self.assertEqual(result["gainers"][0]["symbol"], "AAA")
        self.assertEqual(result["gainers"][0]["pct_change"], 5.5)
        self.assertEqual(result["losers"][0]["symbol"], "ZZZ")

    def test_get_live_market_overview_uses_all_indices_breadth_not_gainers_only(self):
        payload = {
            "data": [
                {
                    "index": "NIFTY 50",
                    "last": 23232.45,
                    "previousClose": 23483.55,
                    "variation": -251.10,
                    "percentChange": -1.07,
                    "dayHigh": 23447.65,
                    "dayLow": 23212.10,
                    "advances": "8",
                    "declines": "42",
                    "unchanged": "0",
                },
                {
                    "index": "NIFTY TOTAL MARKET",
                    "last": 12400.0,
                    "previousClose": 12500.0,
                    "variation": -100.0,
                    "percentChange": -0.8,
                    "advances": "163",
                    "declines": "585",
                    "unchanged": "7",
                },
            ]
        }
        session = MagicMock()
        session.get.return_value = _Resp(payload=payload)

        with patch("terminal.tools._get_live_session", return_value=session):
            result = nse_tools.get_live_market_overview()

        self.assertEqual(result["adv_dec"], {"advances": 163, "declines": 585, "unchanged": 7})
        session.get.assert_called_once_with("https://www.nseindia.com/api/allIndices", timeout=10)


if __name__ == "__main__":
    unittest.main()
