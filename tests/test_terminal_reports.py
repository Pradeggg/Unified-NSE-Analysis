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
    assert "swing-playbook" in nse_agent._REPORT_PRESET_TYPES_FOR_TEST
    assert "diagnosis" in nse_agent._REPORT_PRESET_TYPES_FOR_TEST


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


def test_swing_playbook_report_preset_delegates_to_generator(monkeypatch, tmp_path):
    calls = []

    def fake_generate_swing_playbook(*, options=None, candidates=None):
        calls.append({"options": options, "candidates": candidates})
        html_path = tmp_path / "swing_playbook.html"
        md_path = tmp_path / "swing_playbook.md"
        candidates_path = tmp_path / "candidates.csv"
        portfolio_path = tmp_path / "portfolio.csv"
        html_path.write_text("<html>Swing</html>", encoding="utf-8")
        md_path.write_text("# Swing", encoding="utf-8")
        candidates_path.write_text("symbol\nAAA\n", encoding="utf-8")
        portfolio_path.write_text("symbol\nAAA\n", encoding="utf-8")
        from terminal.swing_playbook import SwingPlaybookResult

        return SwingPlaybookResult(
            success=True,
            markdown="# Swing",
            html_path=str(html_path),
            markdown_path=str(md_path),
            candidates_csv=str(candidates_path),
            portfolio_csv=str(portfolio_path),
        )

    import terminal.swing_playbook as swing_playbook

    monkeypatch.setattr(swing_playbook, "generate_swing_playbook", fake_generate_swing_playbook)

    result = reports.generate_preset_report("swing-playbook", "html")

    assert result["path"].endswith("swing_playbook.html")
    assert result["latest_path"].endswith("swing_playbook.html")
    assert result["format"] == "html"
    assert result["title"] == "Swing Trading Playbook"
    assert result["report_type"] == "swing-playbook"
    assert result["symbol"] == "MARKET"
    assert result["note"]
    assert result["markdown"] == "# Swing"
    assert result["warnings"] == []
    assert calls[-1]["options"] is not None

    for output_format in ("md", "markdown"):
        result = reports.generate_preset_report("swing-playbook", output_format)

        assert result["path"].endswith("swing_playbook.md")
        assert result["latest_path"].endswith("swing_playbook.md")
        assert result["format"] == "md"


def test_diagnosis_report_preset_writes_latest_markdown_and_html(monkeypatch, tmp_path):
    import terminal.reports as reports_module
    from terminal.skills.fundamental_driver import FundamentalDriverResult

    monkeypatch.setattr(reports_module, "ROOT", tmp_path)
    monkeypatch.setattr(reports_module, "REPORTS_DIR", tmp_path / "reports" / "generated")

    def fake_diagnose(symbol, metric, **kwargs):
        return FundamentalDriverResult(
            success=True,
            symbol=symbol,
            metric=metric,
            short_answer=f"{symbol} {metric} explanation",
            metric_bridge={"eps_change_pct": -12.3},
            evidence=("P&L periods compared: Mar 2026 vs Mar 2025",),
            interpretation="operating_margin_pressure",
            what_to_watch=("Margin recovery",),
            warnings=("Cache stale",),
        )

    monkeypatch.setattr("terminal.skills.fundamental_driver.diagnose_fundamental_driver", fake_diagnose)

    html = reports.generate_preset_report("diagnosis", "html", args=["DMART", "eps"])
    md = reports.generate_preset_report("diagnosis", "md", args=["DMART", "eps"])

    assert html["success"] is True
    assert html["report_type"] == "diagnosis"
    assert html["symbol"] == "DMART"
    assert html["format"] == "html"
    assert html["latest_path"].endswith("fundamental_driver_diagnosis.html")
    assert Path(html["path"]).exists()
    assert Path(html["latest_path"]).exists()
    assert "DMART eps explanation" in html["markdown"]
    assert html["warnings"] == ["Cache stale"]
    assert md["format"] == "md"
    assert md["latest_path"].endswith("fundamental_driver_diagnosis.md")
    assert "## Fundamental Driver Diagnosis" in Path(md["latest_path"]).read_text(encoding="utf-8")


def test_research_report_generation_appends_llm_assessment(monkeypatch, tmp_path):
    import terminal.reports as reports_module

    monkeypatch.setattr(reports_module, "REPORTS_DIR", tmp_path / "reports" / "generated")
    monkeypatch.setattr(reports_module, "_build_postgres_research_context", lambda symbol: "")

    calls = {}

    def fake_assessment(content, *, symbol, report_type, title, allow_fallback=False):
        calls["symbol"] = symbol
        calls["content"] = content
        return "## LLM Report Assessment\n\nAssessment body.", {"status": "ok", "source": "LLM"}

    monkeypatch.setattr(reports_module, "build_llm_report_assessment", fake_assessment)

    result = reports_module.generate_report(
        "## Latest Catalysts And Filings\n\nThe latest-catalyst search returned no usable web results.\n",
        report_type="research",
        symbol="AEROENTER",
        output_format="md",
        title="AEROENTER Research",
        filename="aeroenter_test",
    )

    assert result["success"] is True
    assert result["llm_assessment"] == {"status": "ok", "source": "LLM"}
    assert calls["symbol"] == "AEROENTER"
    rendered = Path(result["path"]).read_text(encoding="utf-8")
    assert "## LLM Report Assessment" in rendered
    assert "Assessment body." in rendered


def test_build_llm_report_assessment_uses_report_text_only(monkeypatch):
    import terminal.reports as reports_module
    import terminal.research_council.llm_client as llm_client

    captured = {}

    def fake_call_llm_json(*, system, user, schema, **kwargs):
        captured["system"] = system
        captured["user"] = user
        return {
            "verdict": "HOLD / WATCH",
            "conviction": "medium",
            "thesis": "Quarterly detail is limited, so the report needs filing review.",
            "catalyst_and_filings_assessment": "SAST Reg. 29(2) disclosures are ownership disclosures, not automatic operating catalysts.",
            "quarterly_results_assessment": "The report lacks enough quarterly numbers for a hard trend call.",
            "evidence_quality": "Evidence is mixed because web catalysts are absent but BSE filings are linked.",
            "positive_signals": ["BSE source links are present."],
            "risks": ["Catalyst interpretation could be overstated."],
            "follow_up_checks": ["Open the SAST PDFs and extract acquirer/seller/holding changes."],
        }

    monkeypatch.setattr(llm_client, "call_llm_json", fake_call_llm_json)

    md, meta = reports_module.build_llm_report_assessment(
        "## Latest Catalysts And Filings\n\nDisclosures under Reg. 29(2) of SEBI (SAST) Regulations.",
        symbol="AEROENTER",
        title="AEROENTER report",
    )

    assert meta["status"] == "ok"
    assert "## LLM Report Assessment" in md
    assert "SAST Reg. 29(2)" in md
    assert "report_text" in captured["user"]


def test_assess_existing_research_report_writes_sidecar_and_first_class_report(monkeypatch, tmp_path):
    import terminal.reports as reports_module

    monkeypatch.setattr(reports_module, "REPORTS_DIR", tmp_path / "reports" / "generated")
    source = tmp_path / "AEROENTER_research.html"
    source.write_text(
        """
        <html><body><main>
        <div class="summary-card section" id="main-section">
        <div class="section-body" id="report-body">
          <h2>Latest Catalysts And Filings</h2>
          <p>The latest-catalyst search returned no usable web results.</p>
          <div class="part-divider"><span>Quarterly Results Review</span></div>
          <p>Revenue and PAT need manual validation from filings.</p>
          <div class="tbl-wrap"><table class="data-table"><thead><tr><th>Metric</th><th>Mar 2026</th></tr></thead><tbody><tr><td>Sales</td><td>200</td></tr></tbody></table></div>
        </div>
        </div>
        </main></body></html>
        """,
        encoding="utf-8",
    )

    def fake_assessment(content, *, symbol, report_type, title, allow_fallback=False):
        assert "Latest Catalysts And Filings" in content
        assert symbol == "AEROENTER"
        assert allow_fallback is True
        return "## LLM Report Assessment\n\nExisting report assessment.", {"status": "ok"}

    def fake_section_assessment(section, *, symbol, report_title, allow_fallback=True):
        assert symbol == "AEROENTER"
        return f"Section narrative for {section['title']}.", {"status": "ok"}

    def fake_inline_summary(*, title, section_text, symbol, report_title="", allow_fallback=True):
        assert symbol == "AEROENTER"
        return f"{title} translated for investors.", {"status": "ok"}

    monkeypatch.setattr(reports_module, "build_llm_report_assessment", fake_assessment)
    monkeypatch.setattr(reports_module, "build_llm_section_assessment", fake_section_assessment)
    monkeypatch.setattr(reports_module, "build_inline_section_summary", fake_inline_summary)

    result = reports_module.assess_existing_research_report(source.as_uri())

    assert result["success"] is True
    assert result["symbol"] == "AEROENTER"
    assert len(result["section_assessments"]) == 2
    assert Path(result["assessment_path"]).exists()
    assert Path(result["report_path"]).exists()
    assert result["report_format"] == "html"
    sidecar = Path(result["assessment_path"]).read_text(encoding="utf-8")
    assert "Existing report assessment." in sidecar
    assert "Section narrative for Quarterly Results Review." in sidecar
    assert "Original Research Report" in sidecar
    assert '<table class="data-table"' in sidecar
    assert "Latest Catalysts And Filings translated for investors." in sidecar
    report_html = Path(result["report_path"]).read_text(encoding="utf-8")
    assert "ASSESSED RESEARCH" in report_html
    assert "Existing report assessment." in report_html
    assert "Source Report Section Assessments" in report_html
    assert "Assessment Narrative" in report_html
    assert "Original Research Report" in report_html
    assert "The latest-catalyst search returned no usable web results." in report_html
    assert "Section narrative for Latest Catalysts And Filings." in report_html
    assert "What this means" in report_html
    assert "Latest Catalysts And Filings translated for investors." in report_html
    assert "LLM Section Narrative" not in report_html
    assert "<table" in report_html


def test_extract_research_report_sections_preserves_original_report_blocks(tmp_path):
    import terminal.reports as reports_module

    source = tmp_path / "source.html"
    source.write_text(
        """
        <html><body>
        <h1>Ignored Page Title</h1>
        <div class="section-body" id="report-body">
          <div class="part-divider"><span>AEROENTER — FORENSIC ACCOUNTING ANALYSIS</span></div>
          <div class="arrow-header">Beneish M-score</div>
          <p>Overall forensic risk: LOW.</p>
          <h2>Latest Catalysts And Filings</h2>
          <p>Disclosures under Reg. 29(2) of SEBI SAST Regulations.</p>
        </div>
        </body></html>
        """,
        encoding="utf-8",
    )

    sections = reports_module.extract_research_report_sections(source)

    assert [s["title"] for s in sections] == [
        "AEROENTER — FORENSIC ACCOUNTING ANALYSIS",
        "Latest Catalysts And Filings",
    ]
    assert "### Beneish M-score" in sections[0]["text"]
    assert "Overall forensic risk: LOW." in sections[0]["text"]
    assert "SEBI SAST" in sections[1]["text"]


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
                    "![TATASTEEL 6-month chart](data:image/svg+xml;utf8,%3Csvg%3E%3C/svg%3E)",
                    "",
                    "  * First indented bullet",
                    "  * [neutral-tata-steel-target-of-rs-180-motilal-oswal-13569217.html\" target=\"_blank\">Motilal Oswal's perspective](<https://www.moneycontrol.com/news/business/stocks/neutral-tata-steel-target-of-rs-180-motilal-oswal-13569217.html>)",
                ]
            )
        )

        self.assertIn('<table class="data-table"', html)
        self.assertIn("<th>Field</th><th>Value</th>", html)
        self.assertIn("<td>Company</td><td>Tata Steel Limited</td>", html)
        self.assertIn('<img src="data:image/svg+xml;utf8,%3Csvg%3E%3C/svg%3E"', html)
        self.assertIn('alt="TATASTEEL 6-month chart"', html)
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
                        "paper_portfolio": {
                            "selected_strategy_id": "vcp_breakout_v1",
                            "selected_strategy_name": "VCP Breakout",
                            "as_of": "2026-05-29",
                            "open_positions": 2,
                            "today_pnl": 1234.56,
                            "today_return_pct": 0.12,
                            "total_unrealized_pnl": 4321.0,
                            "artifacts": {
                                "state": "paper/portfolio_state.json",
                                "positions": "paper/positions.csv",
                                "daily_pnl": "paper/daily_pnl.csv",
                                "trades": "paper/trades.csv",
                                "next_orders": "paper/next_orders.csv",
                                "agent_actions": "paper/agent_actions.jsonl",
                                "report": "reports/paper_portfolio_report.md",
                            },
                        },
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
            paper_dir = root / "portfolio" / "data" / "nse_pg_strategy_lab" / "latest" / "paper"
            paper_dir.mkdir(parents=True)
            (paper_dir / "daily_pnl.csv").write_text(
                "date,cash,market_value,nav,daily_pnl,daily_return_pct,cumulative_return_pct,drawdown_pct,open_positions\n"
                "2026-05-27,100000,900000,1000000,0,0,0,0,1\n"
                "2026-05-28,90000,920000,1010000,10000,1,1,0,1\n"
                "2026-05-29,80000,940000,1020000,10000,0.99,2,0,2\n",
                encoding="utf-8",
            )
            (paper_dir / "positions.csv").write_text(
                "symbol,quantity,current_price,market_value,unrealized_pnl,unrealized_pct,stage,rsi_14,relative_strength,stop_price,target_price,reward_risk\n"
                "AAA,10,100,1000,50,5,STAGE_2,62,80,90,120,2\n"
                "BBB,5,200,1000,-25,-2.5,STAGE_2,55,70,180,240,2\n",
                encoding="utf-8",
            )
            (paper_dir / "trades.csv").write_text(
                "date,strategy_id,symbol,side,trade_intent,signal_date,signal_reason,order_type,entry_date,quantity,price,entry_price,stop_price,target_price,risk_amount,realized_pnl,r_multiple,holding_period_days,notional,fees,slippage,cash_effect,order_id,fill_id\n"
                "2026-05-29,vcp_breakout_v1,AAA,BUY,ENTRY,2026-05-28,stage2 breakout with volume confirmation,MARKET_NEXT_OPEN,2026-05-29,10,100,100,90,120,100,, , ,1000,1,0.5,-1001,ord1,fill1\n"
                "2026-05-29,vcp_breakout_v1,BBB,SELL,EXIT,2026-05-28,exit rule matched,MARKET_NEXT_OPEN,2026-05-28,5,200,190,175,220,75,49,0.67,1,1000,1,0.5,999,ord2,fill2\n",
                encoding="utf-8",
            )
            (paper_dir / "next_orders.csv").write_text(
                "date,order_id,strategy_id,symbol,side,trade_intent,quantity,order_type,signal_reason,reference_price,stop_price,target_price,risk_per_share,estimated_risk,estimated_notional\n"
                "2026-05-29,ord-next-buy,vcp_breakout_v1,CCC,BUY,ENTRY,10,MARKET_NEXT_OPEN,entry rule matched,100,90,120,10,100,1000\n"
                "2026-05-29,ord-next-sell,vcp_breakout_v1,AAA,SELL,EXIT,5,MARKET_NEXT_OPEN,exit rule matched,100,,,,,500\n",
                encoding="utf-8",
            )
            state_dir = root / "portfolio" / "data" / "nse_pg_strategy_lab" / "latest" / "runs" / "vcp_breakout_v1" / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "replay_state.json").write_text(
                json.dumps(
                    {
                        "nav_history": [
                            {"timestamp": "2026-05-27", "nav": 1000000, "cash": 100000, "market_value": 900000, "open_positions": 1},
                            {"timestamp": "2026-05-28", "nav": 1010000, "cash": 90000, "market_value": 920000, "open_positions": 1},
                            {"timestamp": "2026-05-29", "nav": 1005000, "cash": 80000, "market_value": 925000, "open_positions": 2},
                        ],
                        "fills": [
                            {"fill_date": "2026-05-28", "symbol": "AAA", "side": "BUY", "quantity": 10, "price": 100},
                            {"fill_date": "2026-05-29", "symbol": "BBB", "side": "SELL", "quantity": 5, "price": 200},
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
        self.assertIn("Daily Paper Portfolio", html)
        self.assertIn("Current Paper Book", html)
        self.assertIn("Today Trade Blotter", html)
        self.assertIn("Next Session Orders", html)
        self.assertIn("ord-next-buy", html)
        self.assertIn("ord-next-sell", html)
        self.assertIn("stage2 breakout with volume confirmation", html)
        self.assertIn("exit rule matched", html)
        self.assertIn("Realized", html)
        self.assertIn("LLM Narrative", html)
        self.assertIn("Strategy Return Chart", html)
        self.assertIn("Portfolio NAV Chart", html)
        self.assertIn("aa-strategy-row", html)
        self.assertIn("aa-position-row", html)
        self.assertIn("toggleStrategyLabDetail", html)
        self.assertIn("Strategy Details", html)
        self.assertIn("Position Details", html)
        self.assertIn("Fundamental Details", html)
        self.assertIn('<div class="aa-strategy-lab-assets">', html)
        self.assertNotIn("&lt;div class=&quot;aa-strategy-lab-assets&quot;", html)
        self.assertIn("aa-lab-tabbar", html)
        self.assertIn("aa-lab-tab-panel", html)
        self.assertIn("aa-window-header", html)
        self.assertIn("buildStrategyLabTabs", html)
        self.assertIn("Paper Trading", html)
        self.assertIn("Strategy Verdict", html)
        self.assertIn("Turnover Decomposition", html)
        self.assertIn("total filled notional divided by starting capital", html)
        self.assertIn("Stage 2 Feature Rows", html)
        self.assertIn("20.0% of feature rows", html)
        self.assertIn("Executive Summary", html)
        self.assertIn("Primary Strategy", html)
        self.assertIn("Portfolio P&amp;L", html)
        self.assertIn("Detailed Analysis", html)
        self.assertIn("Strategy Playbook", html)
        self.assertIn("aa-strategy-playbook", html)
        self.assertIn("Entry Criteria", html)
        self.assertIn("Add / Pyramid Criteria", html)
        self.assertIn("Exit Criteria", html)
        self.assertIn("Stop Loss", html)
        self.assertIn("Targets / Profit Taking", html)
        self.assertIn("Position Sizing", html)
        self.assertIn('playbook:"Strategy Playbook"', html)
        self.assertIn('"overview","strategy","playbook","paper"', html)
        self.assertIn("What it is", html)
        self.assertIn("VCP Breakout", html)
        self.assertIn("Council Deliberations", html)
        self.assertIn("Quant Agent", html)
        self.assertIn("Risk Agent", html)
        self.assertIn("Portfolio Manager", html)
        self.assertIn("Data Steward", html)
        self.assertIn("Council Chair Recommendation", html)
        self.assertIn("Strategy Daily Calendar Heatmap", html)
        self.assertIn("data-heatmap-day", html)
        self.assertIn("data-tooltip", html)
        self.assertIn("aa-heatmap-day:hover::after", html)
        self.assertIn("BUY: AAA", html)
        self.assertIn("SELL: BBB", html)
        self.assertIn("Daily P&amp;L: ₹10,000.00", html)
        self.assertIn("Daily P&amp;L: ₹-5,000.00", html)

    def test_strategy_lab_report_includes_managed_portfolio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_dir = root / "portfolio" / "data" / "nse_pg_strategy_lab" / "latest" / "reports"
            summary_dir.mkdir(parents=True)
            (summary_dir / "strategy_comparison_summary.json").write_text(
                json.dumps(
                    {
                        "run_id": "TEST-MANAGED-LAB",
                        "latest_eod_date": "2025-01-02",
                        "row_count": 1,
                        "symbol_count": 1,
                        "start_date": "2025-01-01",
                        "end_date": "2025-01-02",
                        "initial_capital": 1000000,
                        "slippage_bps": 5,
                        "brokerage_bps": 3,
                        "benchmark_id": "Nifty 500",
                        "stage_counts": {"STAGE_2": 1},
                        "output_dir": "portfolio/data/nse_pg_strategy_lab/latest",
                        "managed_portfolio": {
                            "state": {
                                "policy_checksum": "policy-test",
                                "nav": 1010000,
                                "cash": 500000,
                                "positions": {
                                    "AAA": {
                                        "symbol": "AAA",
                                        "quantity": 25,
                                        "avg_cost": 100,
                                        "open_risk": 250,
                                        "lots": [
                                            {
                                                "entry_date": "2025-01-02",
                                                "quantity": 25,
                                                "entry_price": 100,
                                                "stop_price": 90,
                                                "target_price": 130,
                                            }
                                        ],
                                        "sector": "Capital Goods",
                                    }
                                },
                            },
                            "decisions": [
                                {
                                    "date": "2025-01-02",
                                    "symbol": "AAA",
                                    "action": "ENTER",
                                    "quantity": 25,
                                    "reason_codes": ["POLICY_OK", "RISK|OK"],
                                }
                            ],
                            "orders": [
                                {
                                    "date": "2025-01-02",
                                    "symbol": "AAA",
                                    "action": "ENTER",
                                    "quantity": 25,
                                }
                            ],
                        },
                        "leaderboard": [
                            {
                                "rank": 1,
                                "strategy_id": "vcp_breakout_v1",
                                "total_return_pct": 1,
                                "max_drawdown_pct": 1,
                                "excess_return_pct": 1,
                                "profit_factor": 1.1,
                                "expectancy": 100,
                                "turnover_pct": 10,
                                "cost_drag_pct": 0.1,
                                "fills": 1,
                                "win_rate_pct": 50,
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
        self.assertIn("Managed Portfolio", html)
        self.assertIn("Managed Positions", html)
        self.assertIn("Recent Managed Decisions", html)
        self.assertIn("Open Risk", html)
        self.assertIn("AAA", html)
        self.assertIn("POLICY_OK", html)
        self.assertIn("RISK / OK", html)
        self.assertIn("policy-test", html)


if __name__ == "__main__":
    unittest.main()
