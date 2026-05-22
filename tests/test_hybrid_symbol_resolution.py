from terminal.symbol_search import (
    ResolveCandidate,
    ResolveResult,
    project_legacy_result,
)


def test_resolve_result_projects_exact_legacy_shape():
    result = ResolveResult(
        symbol="TRENT",
        legacy_confidence="exact",
        confidence_band="exact",
        score=1.0,
        raw_score=1.0,
        query="TRENT",
        candidates=(
            ResolveCandidate(
                symbol="TRENT",
                score=1.0,
                raw_score=1.0,
                methods=("dict",),
                matched="TRENT",
            ),
        ),
        method="dict",
        matched="TRENT",
    )

    assert result.needs_clarification is False
    assert result.to_dict() == {
        "symbol": "TRENT",
        "legacy_confidence": "exact",
        "confidence_band": "exact",
        "score": 1.0,
        "raw_score": 1.0,
        "query": "TRENT",
        "candidates": [
            {
                "symbol": "TRENT",
                "score": 1.0,
                "raw_score": 1.0,
                "methods": ["dict"],
                "matched": "TRENT",
            }
        ],
        "method": "dict",
        "matched": "TRENT",
        "needs_clarification": False,
    }
    assert project_legacy_result(result) == {
        "symbol": "TRENT",
        "confidence": "exact",
        "score": 1.0,
        "confidence_band": "exact",
        "query": "TRENT",
        "candidates": ["TRENT"],
        "method": "dict",
        "matched": "TRENT",
    }


def test_medium_result_keeps_legacy_fuzzy_and_sets_clarification_flag():
    result = ResolveResult(
        symbol="TRENT",
        legacy_confidence="fuzzy",
        confidence_band="medium",
        score=0.72,
        raw_score=0.031,
        query="trent ltd",
        candidates=(
            ResolveCandidate(
                symbol="TRENT",
                score=0.72,
                raw_score=0.031,
                methods=("trigram",),
                matched="Trent Limited",
            ),
        ),
        method="trigram",
        matched="Trent Limited",
    )

    assert result.needs_clarification is True
    assert project_legacy_result(result)["confidence"] == "fuzzy"
    assert project_legacy_result(result)["confidence_band"] == "medium"


def test_low_result_projects_none_symbol_and_candidate_list():
    result = ResolveResult(
        symbol=None,
        legacy_confidence="none",
        confidence_band="low",
        score=0.42,
        raw_score=0.018,
        query="market action",
        candidates=(
            ResolveCandidate(
                symbol="FMNL",
                score=0.42,
                raw_score=0.018,
                methods=("trigram",),
                matched="Future Market Networks Limited",
            ),
        ),
        method="trigram",
        matched="",
    )

    projected = project_legacy_result(result)

    assert result.needs_clarification is True
    assert projected["symbol"] is None
    assert projected["confidence"] == "none"
    assert projected["candidates"] == ["FMNL"]


def test_result_validates_confidence_values_and_score_bounds():
    try:
        ResolveResult(
            symbol="TRENT",
            legacy_confidence="high",
            confidence_band="high",
            score=1.2,
            raw_score=0.05,
            query="TRENT",
            candidates=(),
            method="dict",
        )
    except ValueError as exc:
        assert "legacy_confidence" in str(exc)
    else:
        raise AssertionError("ResolveResult accepted invalid confidence/score values")


# ---------------------------------------------------------------------------
# AA-HSR-2 — alias source + seed flow
# ---------------------------------------------------------------------------

import importlib
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from terminal.symbol_search import alias_source as _alias_source
from terminal.symbol_search.alias_source import (
    AliasRecord,
    KIND_WEIGHTS,
    VALID_KINDS,
    alias_summary,
    build_alias_map,
    classify_alias,
    iter_aliases,
)


def test_alias_source_does_not_import_terminal_tools():
    """The neutral module must not pull in terminal.tools (cycle hazard)."""
    sys.modules.pop("terminal.tools", None)
    sys.modules.pop("terminal.symbol_search.alias_source", None)
    importlib.import_module("terminal.symbol_search.alias_source")
    assert "terminal.tools" not in sys.modules, (
        "terminal.symbol_search.alias_source must not import terminal.tools"
    )


def test_kind_weights_match_backlog():
    """Locked by AA-HSR-2 acceptance criteria."""
    assert KIND_WEIGHTS["official"] == 1.0
    assert KIND_WEIGHTS["symbol"] == 0.9
    assert KIND_WEIGHTS["short"] == 0.7
    assert KIND_WEIGHTS["alias"] == 0.6
    assert KIND_WEIGHTS["sector_hint"] == 0.5


def test_classify_alias_distinguishes_kinds():
    assert classify_alias("RELIANCE", "RELIANCE") == "symbol"
    assert classify_alias("Reliance Industries Limited", "RELIANCE") == "official"
    assert classify_alias("HDFC Bank", "HDFCBANK") == "symbol"  # normalises equal → symbol kind
    assert classify_alias("Asian Paints", "ASIANPAINT") == "short"
    assert classify_alias("HUL", "HINDUNILVR") == "alias"


def test_alias_record_validates_kind_and_weight():
    with pytest.raises(ValueError):
        AliasRecord(symbol="X", name="X Co", kind="bogus",
                    weight=0.5, source="manual")
    with pytest.raises(ValueError):
        AliasRecord(symbol="X", name="X Co", kind="manual",
                    weight=2.0, source="manual")
    with pytest.raises(ValueError):
        AliasRecord(symbol="", name="X Co", kind="manual",
                    weight=0.9, source="manual")


def test_iter_aliases_without_pg_emits_manual_and_index_rows():
    """Without Postgres the module still emits manual + index + sector aliases."""
    records = list(iter_aliases(include_pg=False))
    assert records, "iter_aliases should yield manual and index aliases even with no PG"

    by_source = {r.source for r in records}
    assert "manual" in by_source
    assert "fo_index" in by_source
    assert "sector_hint" in by_source
    assert "ref_instruments" not in by_source

    # Spot-check a few known manual aliases — these are bug-regression anchors.
    pairs = {(r.name, r.symbol) for r in records}
    assert ("HDFC BANK", "HDFCBANK") in pairs
    assert ("STATE BANK OF INDIA", "SBIN") in pairs
    assert ("PREMIER ENERGIES", "PREMIERENE") in pairs


def test_iter_aliases_dedup_on_symbol_name_kind():
    records = list(iter_aliases(include_pg=False))
    keys = [(r.symbol, r.name, r.kind) for r in records]
    assert len(keys) == len(set(keys)), "iter_aliases must dedupe on (symbol, name, kind)"


def test_iter_aliases_rejects_generic_single_tokens():
    """A single-token alias like 'INVEST' must never sneak in."""
    records = list(iter_aliases(include_pg=False))
    for r in records:
        if r.kind in {"alias", "short"}:
            assert r.name.upper() not in {"INVEST", "ENERGY", "BANK", "POWER", "AUTO"}


def test_build_alias_map_returns_normalized_keys():
    mapping = build_alias_map(include_pg=False)
    # 'HDFC Bank' should normalize to 'HDFCBANK' lookup key
    assert mapping.get("HDFCBANK") == "HDFCBANK"
    assert mapping.get("STATEBANKOFINDIA") == "SBIN"


def test_alias_summary_groups_by_kind_and_source():
    summary = alias_summary(iter_aliases(include_pg=False))
    assert summary["total"] > 0
    assert set(summary["by_kind"]).issubset(VALID_KINDS)
    assert "manual" in summary["by_source"]
    assert sum(summary["by_kind"].values()) == summary["total"]
    assert sum(summary["by_source"].values()) == summary["total"]


def test_seed_script_dry_run_does_not_touch_db(monkeypatch, capsys):
    """`--dry-run --skip-pg` must complete with exit 0 and zero DB calls."""
    from scripts import seed_symbol_aliases

    called = {"connect": 0}

    def _explode():
        called["connect"] += 1
        raise AssertionError("dry-run must not connect to Postgres")

    monkeypatch.setattr(seed_symbol_aliases, "_connect", _explode)
    rc = seed_symbol_aliases.main(["--dry-run", "--skip-pg"])

    out = capsys.readouterr().out
    assert rc == 0
    assert called["connect"] == 0
    assert "Prepared" in out
    assert "dry-run" in out


def test_seed_script_reports_empty_source(monkeypatch, capsys):
    from scripts import seed_symbol_aliases

    monkeypatch.setattr(seed_symbol_aliases, "iter_aliases", lambda **_: iter(()))
    monkeypatch.setattr(seed_symbol_aliases, "alias_summary",
                        lambda *_: {"total": 0, "by_kind": {}, "by_source": {}})
    rc = seed_symbol_aliases.main(["--dry-run", "--skip-pg"])
    assert rc == 3


def test_seed_script_reports_missing_table(monkeypatch):
    """If market.symbol_aliases is missing, exit code 2 + clear log message."""
    from scripts import seed_symbol_aliases

    fake_conn = mock.MagicMock()
    fake_cur = fake_conn.cursor.return_value.__enter__.return_value
    fake_cur.execute.return_value = None
    fake_cur.fetchone.return_value = (False,)

    monkeypatch.setattr(seed_symbol_aliases, "_connect", lambda: fake_conn)

    rc = seed_symbol_aliases.main(["--skip-pg"])
    assert rc == 2
    fake_conn.close.assert_called()


def test_seed_script_upserts_when_table_exists(monkeypatch):
    """Happy path: connection succeeds, table exists, upsert runs, exit 0."""
    from scripts import seed_symbol_aliases

    fake_conn = mock.MagicMock()
    fake_cur = fake_conn.cursor.return_value.__enter__.return_value
    fake_cur.execute.return_value = None
    fake_cur.fetchone.return_value = (True,)

    monkeypatch.setattr(seed_symbol_aliases, "_connect", lambda: fake_conn)

    rc = seed_symbol_aliases.main(["--skip-pg"])
    assert rc == 0
    fake_conn.commit.assert_called_once()
    # executemany call exists for the UPSERT
    assert any(
        call.args and "INSERT INTO market.symbol_aliases" in str(call.args[0])
        for call in fake_cur.executemany.call_args_list
    )


def test_seed_script_idempotent_executes_upsert_with_conflict_clause():
    """Static check: the UPSERT SQL uses ON CONFLICT, so reruns don't inflate rows."""
    from scripts.seed_symbol_aliases import UPSERT_SQL

    assert "ON CONFLICT (symbol, name, kind)" in UPSERT_SQL
    assert "DO UPDATE" in UPSERT_SQL
