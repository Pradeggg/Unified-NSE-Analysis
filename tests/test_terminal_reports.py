import sqlite3
import tempfile
import unittest
import json
from pathlib import Path

from terminal import reports


def test_report_recommendation_is_recognized_as_preset_type():
    import nse_agent

    assert "recommendation" in nse_agent._REPORT_PRESET_TYPES_FOR_TEST
    assert "strategy-lab" in nse_agent._REPORT_PRESET_TYPES_FOR_TEST


def test_recommendation_report_command_forwards_args_and_options(monkeypatch):
    import nse_agent
    import terminal.recommendation_report as recommendation_report

    calls = {}
    printed = []
    parsed_options = object()

    class FakeConsole:
        def print(self, value="", *args, **kwargs):
            printed.append(value)

    def fake_parse(args):
        calls["parse_args"] = list(args)
        return parsed_options

    def fake_generate(*, options):
        calls["options"] = options
        return {
            "success": True,
            "path": "/tmp/recommendation.html",
            "evidence_path": "/tmp/evidence.json",
            "recommendation_count": 2,
            "run_id": "run-1",
            "warnings": ["partial data"],
            "markdown": "# Grounded EOD Recommendation Report\n\n## Stock Opportunity Map\n\n| Subject | Label |\n| --- | --- |\n| AAA | WATCHLIST |",
        }

    monkeypatch.setattr(recommendation_report, "parse_recommendation_report_args", fake_parse)
    monkeypatch.setattr(recommendation_report, "generate_recommendation_report", fake_generate)
    monkeypatch.setattr(nse_agent, "_open_report_path", lambda path, console=None: calls.setdefault("opened", path))

    handled = nse_agent._handle_recommendation_report_command(
        ["/report", "recommendation", "--watchlist", "RELIANCE,TCS", "--format", "md"],
        FakeConsole(),
    )

    assert handled is True
    assert calls["parse_args"] == ["recommendation", "--watchlist", "RELIANCE,TCS", "--format", "md"]
    assert calls["options"] is parsed_options
    assert calls["opened"] == "/tmp/recommendation.html"
    assert any(isinstance(item, nse_agent.Markdown) for item in printed)


def test_recommendation_report_command_forwards_scope_filters(monkeypatch):
    import nse_agent
    import terminal.recommendation_report as recommendation_report

    calls = {}

    class FakeConsole:
        def print(self, value="", *args, **kwargs):
            pass

    def fake_parse(args):
        calls["parse_args"] = list(args)
        return object()

    def fake_generate(*, options):
        calls["options"] = options
        return {
            "success": True,
            "path": "/tmp/recommendation.html",
            "evidence_path": "/tmp/evidence.json",
            "recommendation_count": 1,
            "run_id": "run-2",
            "warnings": [],
            "markdown": "",
        }

    monkeypatch.setattr(recommendation_report, "parse_recommendation_report_args", fake_parse)
    monkeypatch.setattr(recommendation_report, "generate_recommendation_report", fake_generate)
    monkeypatch.setattr(nse_agent, "_open_report_path", lambda path, console=None: True)

    handled = nse_agent._handle_recommendation_report_command(
        ["/report", "recommendation", "--symbol", "DIXON", "--index", "NIFTY BANK", "--sector", "Capital Goods"],
        FakeConsole(),
    )

    assert handled is True
    assert calls["parse_args"] == [
        "recommendation",
        "--symbol",
        "DIXON",
        "--index",
        "NIFTY BANK",
        "--sector",
        "Capital Goods",
    ]


def test_recommendation_report_command_handles_parser_system_exit(monkeypatch):
    import nse_agent
    import terminal.recommendation_report as recommendation_report

    def fake_parse(args):
        raise SystemExit(2)

    monkeypatch.setattr(recommendation_report, "parse_recommendation_report_args", fake_parse)

    handled = nse_agent._handle_recommendation_report_command(
        ["/report", "recommendation", "--bad-flag"],
        nse_agent.console,
    )

    assert handled is True


def test_open_report_path_swallows_viewer_failures(monkeypatch):
    import nse_agent

    def fake_popen(args):
        raise OSError("viewer missing")

    monkeypatch.setattr(nse_agent.subprocess, "Popen", fake_popen)

    assert nse_agent._open_report_path("/tmp/report.html", nse_agent.console) is False


class TerminalReportsTests(unittest.TestCase):
    def test_generated_html_uses_agent_adda_standard_theme(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_reports_dir = reports.REPORTS_DIR
            try:
                reports.REPORTS_DIR = Path(tmp)
                result = reports.generate_report(
                    "# Market Recommendation\n\n| Symbol | View |\n|---|---|\n| ABC | Watch |",
                    report_type="research",
                    symbol="MARKET",
                    output_format="html",
                    title="Theme Contract Report",
                    filename="theme_contract",
                )
            finally:
                reports.REPORTS_DIR = original_reports_dir

            html = Path(result["path"]).read_text(encoding="utf-8")

        self.assertIn('data-agent-theme="sector-rotation-standard"', html)
        self.assertIn("app-bar", html)
        self.assertIn("summary-grid", html)
        self.assertIn("sum-card", html)
        self.assertIn("sec-hdr", html)
        self.assertIn("site-hdr", html)
        self.assertIn("metrics-row", html)
        self.assertIn("metric-card", html)
        self.assertIn("summary-card", html)
        self.assertIn("tbl-wrap", html)
        self.assertIn("data-table", html)
        self.assertIn("Theme Contract Report", html)

    def test_markdown_converter_handles_loose_tables_indented_bullets_and_angle_links(self):
        html = reports._md_to_html_basic(
            "\n".join(
                [
                    "Field| Value  ",
                    "---|---  ",
                    "Company| Tata Steel Limited  ",
                    "Symbol| TATASTEEL  ",
                    "",
                    "  * First indented bullet",
                    "  * [neutral-tata-steel-target-of-rs-180-motilal-oswal-13569217.html\" target=\"_blank\">Motilal Oswal's perspective](<https://www.moneycontrol.com/news/business/stocks/neutral-tata-steel-target-of-rs-180-motilal-oswal-13569217.html>)",
                ]
            )
        )

        self.assertIn('<table class="data-table"', html)
        self.assertIn("<th>Field</th><th>Value</th>", html)
        self.assertIn("<td>Company</td><td>Tata Steel Limited</td>", html)
        self.assertIn("<li>First indented bullet</li>", html)
        self.assertIn('href="https://www.moneycontrol.com/news/business/stocks/neutral-tata-steel-target-of-rs-180-motilal-oswal-13569217.html"', html)
        self.assertIn(">Motilal Oswal&#x27;s perspective</a>", html)
        self.assertNotIn("&lt;https://www.moneycontrol.com", html)
        self.assertNotIn('target=&quot;_blank&quot;&gt;', html)

    def test_sector_rotation_report_derives_avg_rs_when_explicit_rs_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            conn = sqlite3.connect(data_dir / "sector_rotation_tracker.db")
            conn.executescript(
                """
                CREATE TABLE stage_snapshots (
                    snapshot_date TEXT, symbol TEXT, company_name TEXT, stage TEXT,
                    price REAL, rsi REAL, investment_score REAL, trading_signal TEXT,
                    change_1m_pct REAL, change_1w_pct REAL, sector TEXT,
                    relative_strength REAL
                );
                CREATE TABLE stage_changes (
                    change_date TEXT, compare_date TEXT, symbol TEXT, company_name TEXT,
                    stage_now TEXT, stage_prev TEXT, stage_changed INTEGER,
                    price_now REAL, price_prev REAL, price_chg_pct REAL,
                    live_price REAL, live_vs_prev_pct REAL,
                    stage_score_now REAL, stage_score_prev REAL,
                    trading_signal TEXT, change_type TEXT
                );
                """
            )
            conn.executemany(
                "INSERT INTO stage_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    ("2026-05-12", "A", "Alpha", "STAGE_2", 100, 55, 60, "HOLD", 20.0, 2.0, "Leaders", None),
                    ("2026-05-12", "B", "Beta", "STAGE_2", 100, 52, 58, "HOLD", 10.0, 1.0, "Leaders", None),
                    ("2026-05-12", "C", "Gamma", "STAGE_1", 100, 48, 40, "HOLD", 0.0, -1.0, "Laggards", None),
                ],
            )
            conn.commit()
            conn.close()

            original_root = reports.ROOT
            try:
                reports.ROOT = root
                content = reports._build_sector_rotation_content()
            finally:
                reports.ROOT = original_root

        self.assertIn("| Rank | Sector | Total | Stage 2 | S2 % | Avg RS | Avg 1M | BUY Signals | Signal |", content)
        self.assertIn("| 1 | Leaders | 2 | **2** | 100% | 5.0 | +15.0% | 0 |", content)
        self.assertNotIn("| 1 | Leaders | 2 | **2** | 100% | — |", content)

    def test_stage2_report_deduplicates_stage_change_rows_by_symbol(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            conn = sqlite3.connect(data_dir / "sector_rotation_tracker.db")
            conn.executescript(
                """
                CREATE TABLE stage_snapshots (
                    snapshot_date TEXT, symbol TEXT, company_name TEXT, stage TEXT,
                    price REAL, rsi REAL, investment_score REAL, trading_signal TEXT,
                    change_1m_pct REAL, supertrend_state TEXT, change_1w_pct REAL,
                    sector TEXT, minervini_score REAL, can_slim_score REAL
                );
                CREATE TABLE stage_changes (
                    change_date TEXT, compare_date TEXT, symbol TEXT, company_name TEXT,
                    stage_now TEXT, stage_prev TEXT, stage_changed INTEGER,
                    price_now REAL, price_prev REAL, price_chg_pct REAL,
                    live_price REAL, live_vs_prev_pct REAL,
                    stage_score_now REAL, stage_score_prev REAL,
                    trading_signal TEXT, change_type TEXT
                );
                """
            )
            conn.executemany(
                """
                INSERT INTO stage_snapshots VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                [
                    ("2026-05-11", "AVL", "Aditya Vision", "STAGE_2", 543.75, 62.2, 60.6, "BUY", 14.3, "BULLISH", 0.3, "Other", 10, 18),
                    ("2026-05-11", "CARRARO", "Carraro India", "STAGE_2", 589.3, 55.4, 56.4, "HOLD", 22.6, "BULLISH", 1.2, "Other", 8, 16),
                    ("2026-05-11", "ABB", "ABB India", "STAGE_1", 5000.0, 48.0, 42.0, "HOLD", -2.0, "BEARISH", -1.5, "Capital Goods", 6, 12),
                ],
            )
            conn.executemany(
                """
                INSERT INTO stage_changes VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                [
                    ("2026-05-08", "2026-05-07", "AVL", "Aditya Vision", "STAGE_2", "UNKNOWN", 1, 543.75, 520.0, 4.6, None, None, None, None, "BUY", "ENTER_STAGE2"),
                    ("2026-05-11", "2026-05-08", "AVL", "Aditya Vision", "STAGE_2", "UNKNOWN", 1, 543.75, 530.0, 2.6, None, None, None, None, "BUY", "ENTER_STAGE2"),
                    ("2026-05-08", "2026-05-07", "CARRARO", "Carraro India", "STAGE_2", "STAGE_1", 1, 589.3, 570.0, 3.4, None, None, None, None, "HOLD", "ENTER_STAGE2"),
                    ("2026-05-08", "2026-05-07", "ABB", "ABB India", "STAGE_1", "STAGE_2", 1, 5000.0, 5050.0, -1.0, None, None, None, None, "HOLD", "EXIT_STAGE2"),
                    ("2026-05-11", "2026-05-08", "ABB", "ABB India", "STAGE_1", "STAGE_2", 1, 5000.0, 5040.0, -0.8, None, None, None, None, "HOLD", "EXIT_STAGE2"),
                ],
            )
            conn.commit()
            conn.close()

            original_root = reports.ROOT
            try:
                reports.ROOT = root
                content = reports._build_stage2_content()
            finally:
                reports.ROOT = original_root

        self.assertIn("New Stage 2 Entrants — Last 14 Days (2 stocks)", content)
        self.assertIn("Stage 2 Exits — Last 7 Days (1 stocks)", content)
        self.assertIn("| **AVL** | Aditya Vision | Other | ₹543.75 | 62.2 | +14.3% | 60.6 | BUY | ✅ | 2026-05-11 |", content)
        self.assertNotIn("| **AVL** | Aditya Vision | Other | ₹543.75 | 62.2 | +14.3% | 60.6 | BUY | ✅ | 2026-05-08 |", content)
        self.assertIn("| **ABB** | ABB India | STAGE_1 | ₹5000.0 | -0.8% | 2026-05-11 |", content)
        self.assertNotIn("| **ABB** | ABB India | STAGE_1 | ₹5000.0 | -1.0% | 2026-05-08 |", content)

    def test_strategy_lab_report_builds_from_portfolio_summary_and_copies_latest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_dir = root / "portfolio" / "data" / "nse_pg_strategy_lab" / "latest" / "reports"
            summary_dir.mkdir(parents=True)
            (summary_dir / "strategy_comparison_summary.json").write_text(
                json.dumps(
                    {
                        "run_id": "TEST-LAB",
                        "source": "PostgreSQL market.equity_eod + scores.stage_snapshots",
                        "latest_eod_date": "2026-05-29",
                        "row_count": 100,
                        "symbol_count": 10,
                        "start_date": "2025-01-01",
                        "end_date": "2026-05-29",
                        "initial_capital": 1000000,
                        "slippage_bps": 5,
                        "brokerage_bps": 3,
                        "benchmark_id": "Nifty 500",
                        "stage_counts": {"STAGE_2": 20, "STAGE_3": 80},
                        "data_path": "features.csv",
                        "benchmark_path": "benchmark.csv",
                        "output_dir": "portfolio/data/nse_pg_strategy_lab/latest",
                        "leaderboard": [
                            {
                                "rank": 1,
                                "strategy_id": "vcp_breakout_v1",
                                "total_return_pct": 40.4247,
                                "max_drawdown_pct": 19.6632,
                                "excess_return_pct": 39.6454,
                                "profit_factor": 1.322151,
                                "expectancy": 742.38,
                                "turnover_pct": 3834.0,
                                "cost_drag_pct": 3.067,
                                "fills": 474,
                                "win_rate_pct": 23.9362,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            original_root = reports.ROOT
            original_reports_dir = reports.REPORTS_DIR
            try:
                reports.ROOT = root
                reports.REPORTS_DIR = root / "reports" / "generated"
                result = reports.generate_preset_report("strategy-lab", "html")
            finally:
                reports.ROOT = original_root
                reports.REPORTS_DIR = original_reports_dir

            html = Path(result["path"]).read_text(encoding="utf-8")

        self.assertTrue(result["success"])
        self.assertEqual(result["report_type"], "strategy-lab")
        self.assertIn("portfolio_strategy_lab.html", result["latest_path"])
        self.assertIn("Portfolio Strategy Lab", html)
        self.assertIn("vcp_breakout_v1", html)
        self.assertIn("Cost and Turnover Diagnostics", html)


if __name__ == "__main__":
    unittest.main()
