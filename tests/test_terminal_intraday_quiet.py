import io
import sys
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout

import pandas as pd

from terminal.intraday import get_intraday_candles


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


if __name__ == "__main__":
    unittest.main()
