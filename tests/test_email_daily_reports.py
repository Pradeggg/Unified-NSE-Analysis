from datetime import date
from pathlib import Path

import email_daily_reports


def test_locate_attachments_includes_stage2_tradingview_watchlist(tmp_path):
    reports_dir = tmp_path / "reports"
    latest_dir = reports_dir / "latest"
    stage2_dir = reports_dir / "sector_rotation"
    latest_dir.mkdir(parents=True)
    stage2_dir.mkdir(parents=True)

    sector = latest_dir / "sector_rotation.html"
    stage2 = stage2_dir / "stage2_tracker_2026-05-29.html"
    tv = latest_dir / "stage2_buy_tradingview.txt"
    sector.write_text("<html>sector</html>", encoding="utf-8")
    stage2.write_text("<html>stage2</html>", encoding="utf-8")
    tv.write_text("NSE:RELIANCE\n", encoding="utf-8")

    old_sector = email_daily_reports.SECTOR_LATEST_HTML
    old_stage2 = email_daily_reports.STAGE2_DIR
    old_reports = email_daily_reports.REPORTS_DIR
    try:
        email_daily_reports.SECTOR_LATEST_HTML = sector
        email_daily_reports.STAGE2_DIR = stage2_dir
        email_daily_reports.REPORTS_DIR = reports_dir

        resolved = email_daily_reports.locate_attachments(date(2026, 5, 29))
    finally:
        email_daily_reports.SECTOR_LATEST_HTML = old_sector
        email_daily_reports.STAGE2_DIR = old_stage2
        email_daily_reports.REPORTS_DIR = old_reports

    assert resolved == (sector, stage2, tv)
