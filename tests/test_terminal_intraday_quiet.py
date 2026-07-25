import io
import sys
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

import pandas as pd

from terminal import intraday
from terminal.intraday import _suppress_fds, get_intraday_candles


class TerminalIntradayQuietTests(unittest.TestCase):
    def test_failed_yfinance_download_output_is_suppressed(self):
        original = sys.modules.get("yfinance")

        def noisy_download(*args, **kwargs):
            print("$NAVINFLUOR.NS: possibly delisted; no price data found", file=sys.stderr)
            print("1 Failed download:", file=sys.stderr)
            print("['NAVINFLUOR.NS']", file=sys.stdout)
            return pd.DataFrame()

        sys.modules["yfinance"] = types.SimpleNamespace(download=noisy_download)
        try:
            out = io.StringIO()
            err = io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                df = get_intraday_candles("NAVINFLUOR", interval="15m")
        finally:
            if original is None:
                sys.modules.pop("yfinance", None)
            else:
                sys.modules["yfinance"] = original

        self.assertTrue(df.empty)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")

    def test_midcpnifty_uses_yahoo_midcap_select_index_ticker(self):
        original = sys.modules.get("yfinance")
        calls = []
        expected = pd.DataFrame(
            {
                "Open": [100 + i for i in range(12)],
                "High": [101 + i for i in range(12)],
                "Low": [99 + i for i in range(12)],
                "Close": [100.5 + i for i in range(12)],
                "Volume": [1000 + i for i in range(12)],
            },
            index=pd.date_range("2026-05-15 09:15:00", periods=12, freq="15min"),
        )

        def fake_download(ticker, *args, **kwargs):
            calls.append(ticker)
            return expected if ticker == "NIFTY_MID_SELECT.NS" else pd.DataFrame()

        sys.modules["yfinance"] = types.SimpleNamespace(download=fake_download)
        try:
            df = get_intraday_candles("MIDCPNIFTY", interval="15m")
        finally:
            if original is None:
                sys.modules.pop("yfinance", None)
            else:
                sys.modules["yfinance"] = original

        self.assertFalse(df.empty)
        self.assertEqual(calls, ["NIFTY_MID_SELECT.NS"])

    def test_prompt_toolkit_stdout_proxy_is_not_replaced_or_closed(self):
        class FakeStdoutProxy:
            encoding = "utf-8"

            class Buffer:
                closed = False

                def write(self, data):
                    if self.closed:
                        raise ValueError("write to closed file")
                    return len(data)

            def __init__(self):
                self.buffer = self.Buffer()

            def write(self, data):
                if self.buffer.closed:
                    raise ValueError("write to closed file")
                return len(data)

            def flush(self):
                if self.buffer.closed:
                    raise ValueError("write to closed file")

        FakeStdoutProxy.__module__ = "prompt_toolkit.patch_stdout"
        proxy = FakeStdoutProxy()

        with patch.object(sys, "stdout", proxy):
            with _suppress_fds():
                self.assertIs(sys.stdout, proxy)

        proxy.buffer.write(b"ok")
        proxy.flush()

    def test_bse_stock_reach_graph_payload_normalizes_to_ohlcv_candles(self):
        payload = {
            "Scripname": "INFY",
            "Data": (
                '[{"dttm":"Mon Jun 22 2026 09:15:59","vale1":"1063.00","vole":"34047"},'
                '{"dttm":"Mon Jun 22 2026 09:16:59","vale1":"1065.50","vole":"41278"},'
                '{"dttm":"Mon Jun 22 2026 09:17:59","vale1":"1070.00","vole":"33578"}]'
            ),
        }

        df = intraday._bse_stock_reach_graph_to_candles(payload)

        self.assertEqual(list(df.columns), ["Open", "High", "Low", "Close", "Volume"])
        self.assertEqual(len(df), 3)
        self.assertEqual(df.iloc[0]["Open"], 1063.0)
        self.assertEqual(df.iloc[1]["High"], 1065.5)
        self.assertEqual(df.iloc[-1]["Close"], 1070.0)
        self.assertEqual(df.iloc[0]["Volume"], 34047)
        self.assertEqual(df.index[0], pd.Timestamp("2026-06-22 09:15:59"))

    def test_get_intraday_candles_uses_bse_graph_when_bse_source_mode_enabled(self):
        payload = {
            "Scripname": "INFY",
            "Data": (
                '[{"dttm":"Mon Jun 22 2026 09:15:59","vale1":"1063.00","vole":"34047"},'
                '{"dttm":"Mon Jun 22 2026 09:16:59","vale1":"1065.50","vole":"41278"}]'
            ),
        }

        with (
            patch.dict("os.environ", {"AGENT_ADDA_INTRADAY_QUOTE_SOURCE": "bse"}),
            patch.object(intraday, "_resolve_bse_scrip_code_for_intraday", return_value="500209") as resolver,
            patch.object(intraday, "_bse_stock_reach_graph_payload", return_value=payload) as bse_fetch,
            patch.object(intraday, "_quiet_yf_download", side_effect=AssertionError("yfinance must not run in BSE mode")),
        ):
            df = get_intraday_candles("INFY", interval="15m")

        resolver.assert_called_once_with("INFY")
        bse_fetch.assert_called_once_with("500209")
        self.assertFalse(df.empty)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[-1]["Close"], 1065.5)
        self.assertEqual(df.iloc[-1]["Volume"], 75325)


if __name__ == "__main__":
    unittest.main()
