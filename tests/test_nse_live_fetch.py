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
        with (
            patch("terminal.tools._get_live_session", return_value=session),
            patch("terminal.tools._fetch_nse_index_constituents", return_value=[]),
        ):
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


class NSEOnlyQuoteModeTests(unittest.TestCase):
    def test_get_live_quote_uses_quote_equity_without_yfinance_when_nse_only(self):
        payload = {
            "info": {"companyName": "Infosys Limited"},
            "metadata": {"symbol": "INFY", "series": "EQ", "lastUpdateTime": "22-Jun-2026 10:30:00"},
            "priceInfo": {
                "lastPrice": 1062.5,
                "open": 1070.0,
                "previousClose": 1055.0,
                "change": 7.5,
                "pChange": 0.71,
                "vwap": 1065.2,
                "intraDayHighLow": {"max": 1072.0, "min": 1058.0},
                "weekHighLow": {"max": 1800.0, "min": 1000.0},
            },
        }

        with (
            patch.dict("os.environ", {"AGENT_ADDA_QUOTE_SOURCE": "nse_only"}),
            patch.object(nse_tools, "_nse_get_json", return_value=payload) as nse_fetch,
            patch("yfinance.Ticker", side_effect=AssertionError("yfinance must not run in NSE-only mode")),
        ):
            result = nse_tools.get_live_quote("INFY")

        nse_fetch.assert_called_once()
        self.assertEqual(result["symbol"], "INFY")
        self.assertEqual(result["source"], "NSE quote-equity live API")
        self.assertEqual(result["last_price"], 1062.5)
        self.assertEqual(result["pct_change"], 0.71)
        self.assertNotIn("error", result)

    def test_get_live_quote_fails_closed_when_nse_only_quote_equity_is_blocked(self):
        with (
            patch.dict("os.environ", {"AGENT_ADDA_NSE_ONLY_QUOTES": "1"}),
            patch.object(nse_tools, "_nse_get_json", side_effect=RuntimeError("NSE returned HTTP 403")),
            patch("yfinance.Ticker", side_effect=AssertionError("yfinance must not run in NSE-only mode")),
        ):
            result = nse_tools.get_live_quote("INFY")

        self.assertEqual(result["symbol"], "INFY")
        self.assertEqual(result["source"], "NSE quote-equity live API")
        self.assertTrue(result["fallback_disabled"])
        self.assertIn("NSE quote-equity unavailable", result["error"])
        self.assertIn("HTTP 403", result["error"])

    def test_get_nse_quotes_uses_sequential_nse_quotes_when_nse_only(self):
        def fake_live_quote(symbol):
            return {
                "symbol": symbol,
                "last_price": 100.0,
                "pct_change": 1.0,
                "source": "NSE quote-equity live API",
            }

        with (
            patch.dict("os.environ", {"AGENT_ADDA_QUOTE_SOURCE": "NSE_ONLY"}),
            patch.object(nse_tools, "get_live_quote", side_effect=fake_live_quote) as live_quote,
            patch("yfinance.download", side_effect=AssertionError("yfinance batch must not run in NSE-only mode")),
        ):
            result = nse_tools.get_nse_quotes(["INFY", "BHEL"])

        self.assertEqual(result["source"], "NSE quote-equity live API batch")
        self.assertTrue(result["fallback_disabled"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(set(result["quotes"]), {"INFY", "BHEL"})
        self.assertEqual(live_quote.call_count, 2)


class BSEQuoteModeTests(unittest.TestCase):
    def test_get_live_quote_uses_bse_header_data_without_yfinance_when_bse_mode(self):
        header_payload = {
            "CurrRate": {"LTP": "1063.65", "Chg": "+11.80", "PcChg": "+1.12"},
            "Cmpname": {"FullN": "Infosys Ltd", "ShortN": "infy", "EquityScrips": "500209"},
            "Header": {
                "PrevClose": "1051.85",
                "Open": "1055.00",
                "High": "1071.35",
                "Low": "1055.00",
                "Ason": "22 Jun 26 | 10:49",
            },
        }

        with (
            patch.dict("os.environ", {"AGENT_ADDA_QUOTE_SOURCE": "bse"}),
            patch.object(nse_tools, "_resolve_bse_scrip_code", return_value="500209") as resolver,
            patch.object(nse_tools, "_bse_get_json", return_value=header_payload) as bse_fetch,
            patch("yfinance.Ticker", side_effect=AssertionError("yfinance must not run in BSE mode")),
        ):
            result = nse_tools.get_live_quote("INFY")

        resolver.assert_called_once_with("INFY")
        bse_fetch.assert_called_once()
        self.assertEqual(result["symbol"], "INFY")
        self.assertEqual(result["source"], "BSE live API")
        self.assertEqual(result["exchange"], "BSE")
        self.assertEqual(result["bse_scrip_code"], "500209")
        self.assertEqual(result["last_price"], 1063.65)
        self.assertEqual(result["open"], 1055.0)
        self.assertEqual(result["day_high"], 1071.35)
        self.assertEqual(result["day_low"], 1055.0)
        self.assertEqual(result["prev_close"], 1051.85)
        self.assertEqual(result["pct_change"], 1.12)
        self.assertEqual(result["as_of"], "22 Jun 26 | 10:49")
        self.assertNotIn("error", result)

    def test_get_live_quote_fails_closed_when_bse_mode_cannot_resolve_symbol(self):
        with (
            patch.dict("os.environ", {"AGENT_ADDA_QUOTE_SOURCE": "bse_only"}),
            patch.object(nse_tools, "_resolve_bse_scrip_code", return_value=None),
            patch("yfinance.Ticker", side_effect=AssertionError("yfinance must not run in BSE mode")),
        ):
            result = nse_tools.get_live_quote("UNKNOWN")

        self.assertEqual(result["symbol"], "UNKNOWN")
        self.assertEqual(result["source"], "BSE live API")
        self.assertTrue(result["fallback_disabled"])
        self.assertIn("BSE scrip code unavailable", result["error"])

    def test_get_nse_quotes_uses_sequential_bse_quotes_when_bse_mode(self):
        def fake_live_quote(symbol):
            return {
                "symbol": symbol,
                "last_price": 100.0,
                "source": "BSE live API",
            }

        with (
            patch.dict("os.environ", {"AGENT_ADDA_QUOTE_SOURCE": "exchange_public"}),
            patch.object(nse_tools, "get_live_quote", side_effect=fake_live_quote) as live_quote,
            patch("yfinance.download", side_effect=AssertionError("yfinance batch must not run in BSE mode")),
        ):
            result = nse_tools.get_nse_quotes(["INFY", "BHEL"])

        self.assertEqual(result["source"], "BSE live API batch")
        self.assertTrue(result["fallback_disabled"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(set(result["quotes"]), {"INFY", "BHEL"})
        self.assertEqual(live_quote.call_count, 2)

    def test_resolve_bse_scrip_code_parses_peer_smart_search_html(self):
        html_payload = (
            "<li class='quotemenu quotemenuselect' "
            "onclick=\"liclick('500209','Infosys Ltd')\">"
            "<a>INFOSYS LTD<br /><span><strong>INFY</strong>&nbsp;&nbsp;&nbsp;"
            "INE009A01021&nbsp;&nbsp;&nbsp;500209</span></a></li>"
        )
        with patch.object(nse_tools, "_bse_get_text", return_value=html_payload):
            result = nse_tools._resolve_bse_scrip_code("INFY")

        self.assertEqual(result, "500209")


if __name__ == "__main__":
    unittest.main()
