import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import terminal

from terminal.strategy_council import (
    handle_strategy_council_command,
    parse_strategy_council_command,
    resolve_strategy_council_agents,
)


class NSEAgentStrategyCouncilTests(unittest.TestCase):
    def test_parse_strategy_council_command_defaults(self):
        cfg = parse_strategy_council_command("/strategy-council DMART")

        self.assertEqual(cfg.symbol, "DMART")
        self.assertEqual(cfg.horizons, (5, 10, 20))
        self.assertEqual(cfg.iterations, 3)

    def test_strategy_council_intraday_mode_uses_live_snapshot_and_setup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "data").mkdir()
            pd.DataFrame(
                {
                    "SYMBOL": ["DMART"] * 520,
                    "TIMESTAMP": pd.date_range("2024-01-01", periods=520, freq="D"),
                    "OPEN": [100 + i * 0.2 for i in range(520)],
                    "HIGH": [101 + i * 0.2 for i in range(520)],
                    "LOW": [99 + i * 0.2 for i in range(520)],
                    "CLOSE": [100.5 + i * 0.2 for i in range(520)],
                    "TOTTRDQTY": [1000] * 520,
                }
            ).to_csv(root / "data" / "nse_sec_full_data.csv", index=False)

            fake_tools = SimpleNamespace()
            fake_tools.get_nse_intraday_snapshot = Mock(
                return_value={
                    "symbol": "DMART",
                    "source": "NSE live API snapshot",
                    "last_price": 4200.0,
                    "pct_change": 1.2,
                    "as_of": "15-May-2026 10:13:00",
                }
            )
            fake_tools.explain_intraday_setup = Mock(
                return_value={
                    "symbol": "DMART",
                    "source": "PostgreSQL intraday.ohlcv_bars seeded from Yahoo Finance (yfinance)",
                    "setup_label": "LONG_SETUP",
                    "score": 72.5,
                    "latest_timestamp": "2026-05-15 10:00:00",
                    "latest_close": 4195.0,
                }
            )
            fake_tools.get_intraday_analysis = Mock()

            with patch.object(terminal, "tools", fake_tools, create=True):

                output = handle_strategy_council_command(
                    "/strategy-council DMART --iterations 1 --intraday --no-llm",
                    project_root=root,
                )

        fake_tools.get_nse_intraday_snapshot.assert_called_once_with("DMART")
        fake_tools.explain_intraday_setup.assert_called_once_with("DMART", timeframe="15m")
        fake_tools.get_intraday_analysis.assert_not_called()
        self.assertIn("Mode: Intraday Strategy Council", output)
        self.assertIn("NSE live API snapshot", output)
        self.assertIn("Yahoo Finance", output)
        self.assertIn("LONG_SETUP", output)

    def test_strategy_council_intraday_mode_falls_back_to_yfinance_analysis(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "data").mkdir()
            pd.DataFrame(
                {
                    "SYMBOL": ["DMART"] * 520,
                    "TIMESTAMP": pd.date_range("2024-01-01", periods=520, freq="D"),
                    "OPEN": [100 + i * 0.2 for i in range(520)],
                    "HIGH": [101 + i * 0.2 for i in range(520)],
                    "LOW": [99 + i * 0.2 for i in range(520)],
                    "CLOSE": [100.5 + i * 0.2 for i in range(520)],
                    "TOTTRDQTY": [1000] * 520,
                }
            ).to_csv(root / "data" / "nse_sec_full_data.csv", index=False)

            fake_tools = SimpleNamespace()
            fake_tools.get_nse_intraday_snapshot = Mock(
                return_value={"symbol": "DMART", "source": "NSE live API snapshot", "last_price": 4200.0}
            )
            fake_tools.explain_intraday_setup = Mock(
                return_value={
                    "symbol": "DMART",
                    "source": "PostgreSQL intraday.ohlcv_bars",
                    "error": "No PostgreSQL intraday.ohlcv_bars for DMART at 15m",
                }
            )
            fake_tools.get_intraday_analysis = Mock(
                return_value={
                    "symbol": "DMART",
                    "source": "Yahoo Finance (yfinance)",
                    "bias": "BULLISH",
                    "close": 4198.0,
                    "candles": 35,
                }
            )

            with patch.object(terminal, "tools", fake_tools, create=True):

                output = handle_strategy_council_command(
                    "/strategy-council DMART --iterations 1 --mode intraday --no-llm",
                    project_root=root,
                )

        fake_tools.get_intraday_analysis.assert_called_once_with("DMART", interval="15m")
        self.assertIn("Mode: Intraday Strategy Council", output)
        self.assertIn("Yahoo Finance", output)
        self.assertIn("BULLISH", output)

    def test_parse_strategy_council_rejects_invalid_horizon(self):
        with self.assertRaisesRegex(ValueError, "Invalid horizon"):
            parse_strategy_council_command("/strategy-council DMART --horizon nonsense")

    def test_parse_strategy_council_rejects_unknown_strategy(self):
        with self.assertRaisesRegex(ValueError, "Unknown strategy"):
            parse_strategy_council_command("/strategy-council DMART --strategies eval")

    def test_parse_strategy_council_rejects_non_positive_iterations(self):
        with self.assertRaisesRegex(ValueError, "positive integer"):
            parse_strategy_council_command("/strategy-council DMART --iterations 0")

    def test_strategy_council_defaults_to_llm_when_api_key_exists(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=True):
            _strategist, _critics, mode = resolve_strategy_council_agents(["/strategy-council", "DMART"])

        self.assertIn("LLM strategist", mode)

    def test_strategy_council_no_llm_forces_deterministic_fallback(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=True):
            _strategist, _critics, mode = resolve_strategy_council_agents(["/strategy-council", "DMART", "--no-llm"])

        self.assertIn("deterministic fallback", mode)

    def test_handle_strategy_council_command_runs_and_writes_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "data").mkdir()
            pd.DataFrame(
                {
                    "SYMBOL": ["DMART"] * 520,
                    "TIMESTAMP": pd.date_range("2024-01-01", periods=520, freq="D"),
                    "OPEN": [100 + i * 0.2 for i in range(520)],
                    "HIGH": [101 + i * 0.2 for i in range(520)],
                    "LOW": [99 + i * 0.2 for i in range(520)],
                    "CLOSE": [100.5 + i * 0.2 for i in range(520)],
                    "TOTTRDQTY": [1000] * 520,
                }
            ).to_csv(root / "data" / "nse_sec_full_data.csv", index=False)

            output = handle_strategy_council_command("/strategy-council DMART --iterations 1 --no-llm", project_root=root)

        self.assertIn("Strategy Council", output)
        self.assertIn("DMART", output)
        self.assertIn("Recommendation", output)
        self.assertIn("Report:", output)
        self.assertIn("deterministic fallback", output)

    @patch("terminal.strategy_council.persist_council_result")
    def test_handle_strategy_council_command_persists_when_requested(self, mock_persist):
        mock_persist.return_value = {
            "ok": True,
            "run_id": "6d9c47aa-63a9-4c1a-a691-f0f22138ce45",
            "split_results_inserted": 0,
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "data").mkdir()
            pd.DataFrame(
                {
                    "SYMBOL": ["DMART"] * 520,
                    "TIMESTAMP": pd.date_range("2024-01-01", periods=520, freq="D"),
                    "OPEN": [100 + i * 0.2 for i in range(520)],
                    "HIGH": [101 + i * 0.2 for i in range(520)],
                    "LOW": [99 + i * 0.2 for i in range(520)],
                    "CLOSE": [100.5 + i * 0.2 for i in range(520)],
                    "TOTTRDQTY": [1000] * 520,
                }
            ).to_csv(root / "data" / "nse_sec_full_data.csv", index=False)

            output = handle_strategy_council_command(
                "/strategy-council DMART --iterations 1 --no-llm --persist",
                project_root=root,
            )

        mock_persist.assert_called_once()
        self.assertIn("PostgreSQL council run:", output)
        self.assertIn("6d9c47aa", output)
