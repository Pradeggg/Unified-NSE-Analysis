import tempfile
import unittest
from pathlib import Path

from backtesting.strategy_council.report import render_council_markdown, write_council_report
from backtesting.strategy_council.types import CouncilConfig, CouncilResult, EvidencePack, StrategySpec


class StrategyCouncilReportTests(unittest.TestCase):
    def test_render_council_markdown_includes_guardrails_and_recommendation(self):
        result = CouncilResult(
            config=CouncilConfig(symbol="DMART"),
            evidence=EvidencePack(symbol="DMART", as_of="2026-05-14", missing=["news"]),
            iterations=(),
            locked_strategy=StrategySpec("stage2", 10, ("entry",), ("exit",), ("risk",), "thesis", origin="llm"),
            test_results=(),
            recommendation="WAIT",
            rationale="Research-only.",
        )

        md = render_council_markdown(result)

        self.assertIn("Strategy Council", md)
        self.assertIn("DMART", md)
        self.assertIn("WAIT", md)
        self.assertIn("Missing Data", md)
        self.assertIn("Strategy Origin", md)
        self.assertIn("llm", md)
        self.assertIn("not investment advice", md.lower())

    def test_render_council_markdown_includes_source_trail(self):
        evidence = EvidencePack(
            symbol="DMART",
            as_of="2026-05-14",
            source_trail=["PostgreSQL market.equity_eod: ok (819 rows)"],
        )
        result = CouncilResult(
            config=CouncilConfig(symbol="DMART"),
            evidence=evidence,
            iterations=(),
            locked_strategy=None,
            test_results=(),
            recommendation="WAIT",
            rationale="Research-only.",
        )

        md = render_council_markdown(result)

        self.assertIn("Source Trail", md)
        self.assertIn("PostgreSQL market.equity_eod", md)

    def test_render_council_markdown_includes_enriched_evidence(self):
        evidence = EvidencePack(
            symbol="DMART",
            as_of="2026-05-15",
            technical={"close": 100, "bars": 300},
            fundamental={
                "snapshot": {"fundamental_score": 72},
                "latest_results": {"status": "ok", "facts": {"revenue": {"value": "14000"}}},
                "readiness": {"score": 85, "status": "usable"},
            },
            market={"breadth": {"advances": 500, "declines": 420}},
            news=[{"title": "DMART update"}],
        )
        result = CouncilResult(
            config=CouncilConfig(symbol="DMART"),
            evidence=evidence,
            iterations=(),
            locked_strategy=None,
            test_results=(),
            recommendation="WAIT",
            rationale="Research-only.",
        )

        md = render_council_markdown(result)

        self.assertIn("Enriched Evidence", md)
        self.assertIn("fundamental_score", md)
        self.assertIn("latest_results", md)
        self.assertIn("DMART update", md)
        self.assertIn("Readiness", md)

    def test_write_council_report_creates_markdown_file(self):
        result = CouncilResult(
            config=CouncilConfig(symbol="DMART"),
            evidence=EvidencePack(symbol="DMART", as_of="2026-05-14"),
            iterations=(),
            locked_strategy=None,
            test_results=(),
            recommendation="NO_TRADE",
            rationale="No valid strategy.",
        )
        with tempfile.TemporaryDirectory() as td:
            path = write_council_report(result, output_dir=Path(td))
            self.assertTrue(path.exists())
            self.assertIn("DMART", path.read_text())

    def test_render_council_markdown_includes_intraday_evidence_section(self):
        evidence = EvidencePack(symbol="DMART", as_of="2026-05-15")
        evidence.market["intraday_snapshot"] = {
            "source": "NSE live API snapshot",
            "last_price": 4200.0,
            "pct_change": 1.2,
            "as_of": "15-May-2026 10:13:00",
        }
        evidence.technical["intraday_setup"] = {
            "source": "PostgreSQL intraday.ohlcv_bars seeded from Yahoo Finance (yfinance)",
            "setup_label": "LONG_SETUP",
            "score": 72.5,
        }
        result = CouncilResult(
            config=CouncilConfig(symbol="DMART"),
            evidence=evidence,
            iterations=(),
            locked_strategy=None,
            test_results=(),
            recommendation="WAIT",
            rationale="Research-only.",
        )

        md = render_council_markdown(result)

        self.assertIn("Intraday Evidence", md)
        self.assertIn("NSE live API snapshot", md)
        self.assertIn("Yahoo Finance", md)
        self.assertIn("LONG_SETUP", md)
