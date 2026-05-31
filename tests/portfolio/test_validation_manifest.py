from __future__ import annotations

import json

import pandas as pd

from portfolio.engine.run_manifest import build_run_manifest, checksum_payload
from portfolio.engine.validation import Severity, validate_ohlcv
from tests.portfolio.fixtures import sample_ohlcv, valid_strategy_spec


def test_validate_ohlcv_accepts_fixture_without_errors():
    report = validate_ohlcv(sample_ohlcv())

    assert report.error_count == 0
    assert report.row_count == 6
    assert report.symbol_count == 1
    assert report.is_usable
    assert report.as_dict()["issues"] == []


def test_validate_ohlcv_flags_malformed_bars_deterministically():
    frame = sample_ohlcv()
    frame.loc[1, "high"] = 99.0
    frame.loc[2, "volume"] = 0
    frame = pd.concat([frame, frame.iloc[[2]]], ignore_index=True)

    report = validate_ohlcv(frame)

    codes = [issue.code for issue in report.issues]
    assert "invalid_ohlc_range" in codes
    assert "zero_volume" in codes
    assert "duplicate_bar" in codes
    assert report.error_count == 1
    assert report.warning_count == 2


def test_validate_ohlcv_rejects_missing_required_columns():
    frame = sample_ohlcv().drop(columns=["close"])

    report = validate_ohlcv(frame)

    assert not report.is_usable
    assert report.error_count == 1
    assert report.issues[0].code == "missing_column"
    assert report.issues[0].severity == Severity.ERROR


def test_build_run_manifest_is_json_safe_and_checksum_stable(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"ok": true}', encoding="utf-8")

    manifest = build_run_manifest(
        run_id="PT-1",
        config={"initial_capital": 1000000.0},
        strategy_specs=[valid_strategy_spec()],
        data=sample_ohlcv(),
        artifacts={"state": state_path},
    )

    payload = manifest.as_dict()
    json.dumps(payload)
    assert payload["run_id"] == "PT-1"
    assert payload["strategy_count"] == 1
    assert payload["data"]["row_count"] == 6
    assert payload["checksums"]["strategies"] == checksum_payload([valid_strategy_spec()])
    assert payload["artifacts"]["state"].endswith("state.json")
