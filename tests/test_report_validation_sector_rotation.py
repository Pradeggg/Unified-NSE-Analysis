import pandas as pd

from report_validation import ValidationResult


def test_sector_rotation_candidate_validation_flags_snapshot_mismatch(tmp_path, monkeypatch):
    report = tmp_path / "sector_rotation.md"
    report.write_text(
        "\n".join(
            [
                "### Metals & Mining",
                "",
                "| Symbol | Company | Price | Signal | Setup | Action | Score | Tech | RS | Fund | RSI | Supertrend | Pattern | Volume Ratio |",
                "|---|---|---:|---|---|---|---:|---:|---:|---:|---:|---|---|---:|",
                "| WELCORP | Welspun Corp | 1389.40 | BUY | NEUTRAL | WATCHLIST | 95.4 | 98.4 | 98.8% | 49.4 | 57.8 | BULLISH | TRENDING_OR_CHOPPY | 0.49x |",
            ]
        ),
        encoding="utf-8",
    )

    import report_validation as rv

    monkeypatch.setattr(rv, "LATEST_DIR", tmp_path)
    monkeypatch.setattr(
        rv,
        "_load_latest_stage_snapshot_for_validation",
        lambda symbols: pd.DataFrame(
            [
                {
                    "SYMBOL": "WELCORP",
                    "SNAPSHOT_DATE": "2026-06-11",
                    "INVESTMENT_SCORE": 59.9,
                    "TECHNICAL_SCORE": 58.0,
                    "RELATIVE_STRENGTH": 67.03,
                }
            ]
        ),
    )
    result = ValidationResult(checkpoint="sector_rotation", generated_at="2026-06-11 20:30 IST", mode="rules")

    rv._validate_sector_rotation_report(result)

    assert any(f.severity == "high" and "candidate metrics do not match" in f.issue.lower() for f in result.findings)


def test_sector_rotation_candidate_validation_passes_matching_snapshot(tmp_path, monkeypatch):
    report = tmp_path / "sector_rotation.md"
    report.write_text(
        "\n".join(
            [
                "### Metals & Mining",
                "",
                "| Symbol | Company | Price | Signal | Setup | Action | Score | Tech | RS | Fund | RSI | Supertrend | Pattern | Volume Ratio |",
                "|---|---|---:|---|---|---|---:|---:|---:|---:|---:|---|---|---:|",
                "| WELCORP | Welspun Corp | 1389.40 | BUY | NEUTRAL | WATCHLIST | 59.9 | 58.0 | 67.0% | 49.4 | 57.8 | BULLISH | TRENDING_OR_CHOPPY | 0.49x |",
            ]
        ),
        encoding="utf-8",
    )

    import report_validation as rv

    monkeypatch.setattr(rv, "LATEST_DIR", tmp_path)
    monkeypatch.setattr(
        rv,
        "_load_latest_stage_snapshot_for_validation",
        lambda symbols: pd.DataFrame(
            [
                {
                    "SYMBOL": "WELCORP",
                    "SNAPSHOT_DATE": "2026-06-11",
                    "INVESTMENT_SCORE": 59.9,
                    "TECHNICAL_SCORE": 58.0,
                    "RELATIVE_STRENGTH": 67.03,
                }
            ]
        ),
    )
    result = ValidationResult(checkpoint="sector_rotation", generated_at="2026-06-11 20:30 IST", mode="rules")

    rv._validate_sector_rotation_report(result)

    assert result.findings == []
