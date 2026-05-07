import csv
import tempfile
import unittest
from pathlib import Path

from agent_adda.cli import build_parser, main


class AgentAddaCliTests(unittest.TestCase):
    def test_parser_accepts_core_commands(self):
        parser = build_parser()
        self.assertEqual(parser.parse_args(["setup", "--non-interactive"]).command, "setup")
        self.assertEqual(parser.parse_args(["doctor"]).command, "doctor")
        args = parser.parse_args(["data", "bootstrap", "--historical"])
        self.assertEqual(args.command, "data")
        self.assertEqual(args.data_command, "bootstrap")
        self.assertTrue(args.historical)

    def test_setup_non_interactive_writes_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            exit_code = main(["setup", "--non-interactive", "--home", tmp])
            self.assertEqual(exit_code, 0)
            self.assertTrue((Path(tmp) / "config.toml").exists())

    def test_data_bootstrap_historical_creates_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            with (source / "sample.csv").open("w", newline="") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=["SYMBOL", "DATE", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "SYMBOL": "RELIANCE",
                        "DATE": "2026-05-04",
                        "OPEN": "1400",
                        "HIGH": "1420",
                        "LOW": "1390",
                        "CLOSE": "1410",
                        "VOLUME": "12345",
                    }
                )

            exit_code = main(
                [
                    "data",
                    "bootstrap",
                    "--historical",
                    "--home",
                    str(root),
                    "--source",
                    str(source),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "data" / "market_data.sqlite").exists())


if __name__ == "__main__":
    unittest.main()
