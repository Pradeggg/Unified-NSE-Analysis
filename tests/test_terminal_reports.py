import sqlite3
import tempfile
import unittest
from pathlib import Path

from terminal import reports


def test_report_recommendation_is_recognized_as_preset_type():
    import nse_agent

    assert "recommendation" in nse_agent._REPORT_PRESET_TYPES_FOR_TEST


class TerminalReportsTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
