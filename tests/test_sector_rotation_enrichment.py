"""Tests for tracker JIT screener-enrichment of missing fundamentals."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import sector_rotation_tracker as srt  # noqa: E402
from scripts.backfill_screener_fundamentals import load_symbols_for_index  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# load_symbols_for_index multi-index support
# ─────────────────────────────────────────────────────────────────────────────

def test_load_symbols_single_index():
    syms = load_symbols_for_index("NIFTY 500")
    assert len(syms) > 400  # ~501


def test_load_symbols_comma_separated_union_dedupes():
    a = set(load_symbols_for_index("NIFTY 500"))
    b = set(load_symbols_for_index("NIFTY MICROCAP 250"))
    union = load_symbols_for_index("NIFTY 500,NIFTY MICROCAP 250")
    assert set(union) == a | b
    assert len(union) == len(set(union))  # deduped


def test_load_symbols_dedupes_within_single_call():
    union = load_symbols_for_index("NIFTY 500,NIFTY MICROCAP 250")
    assert len(union) == len(set(union))


def test_load_symbols_handles_whitespace():
    a = load_symbols_for_index("NIFTY 500,NIFTY MICROCAP 250")
    b = load_symbols_for_index(" NIFTY 500 , NIFTY MICROCAP 250 ")
    assert a == b


# ─────────────────────────────────────────────────────────────────────────────
# _enrich_missing_fundamentals
# ─────────────────────────────────────────────────────────────────────────────

_FAKE_PAYLOAD = {
    "symbol": "FOOCO",
    "pnl_data": {"years": ["Mar 2024"], "metrics": {"Sales": ["100"]}},
    "ratios": {"P/E": "20", "ROE": "15%"},
}


@pytest.fixture
def fund_cache():
    return {}


def _patch_helpers(
    scrape_result=None,
    yf_result=None,
    pg_raises=False,
):
    """Patch all the helper modules `_enrich_missing_fundamentals` imports."""
    fake_pg = type("FakePG", (), {})()
    fake_pg.autocommit = False
    fake_pg.committed = 0
    fake_pg.rolled_back = 0
    fake_pg.closed = False

    class _CtxCur:
        def __init__(self):
            self.upserts = []
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    fake_cur = _CtxCur()
    fake_pg.cursor = lambda: fake_cur
    fake_pg.commit = lambda: setattr(fake_pg, "committed", fake_pg.committed + 1)
    fake_pg.rollback = lambda: setattr(fake_pg, "rolled_back", fake_pg.rolled_back + 1)
    fake_pg.close = lambda: setattr(fake_pg, "closed", True)
    fake_pg.cur = fake_cur

    def _scrape(sym):
        if isinstance(scrape_result, Exception):
            raise scrape_result
        if callable(scrape_result):
            return scrape_result(sym)
        return scrape_result

    def _yf(sym):
        if isinstance(yf_result, Exception):
            raise yf_result
        if callable(yf_result):
            return yf_result(sym)
        return yf_result

    def _pg():
        if pg_raises:
            raise RuntimeError("pg unavailable")
        return fake_pg

    upsert_calls = []
    def _upsert(cur, sym, payload, source_tag):
        upsert_calls.append((sym, source_tag))

    patches = [
        patch("terminal.web_research.scrape_screener_in", side_effect=_scrape),
        patch("terminal.web_research._get_yfinance_ratios", side_effect=_yf),
        patch("scripts.backfill_screener_fundamentals.upsert_symbol", side_effect=_upsert),
        patch("scripts.backfill_screener_fundamentals.build_pnl_summary",
              return_value="PNL summary"),
        patch("scripts.backfill_screener_fundamentals.build_quarterly_summary",
              return_value="Quarterly summary"),
        patch("scripts.backfill_screener_fundamentals.build_balance_sheet_summary",
              return_value=None),
        patch("scripts.backfill_screener_fundamentals.build_ratios_summary",
              return_value="Ratios summary"),
        patch("postgres.loader.pg", side_effect=_pg),
        # No-op sleep to keep tests fast
        patch("time.sleep", return_value=None),
    ]
    return patches, fake_pg, upsert_calls


def _run_with(patches, *args, **kwargs):
    for p in patches:
        p.start()
    try:
        return srt._enrich_missing_fundamentals(*args, **kwargs)
    finally:
        for p in patches:
            p.stop()


def test_enrich_screener_success_updates_cache_and_pg(fund_cache):
    patches, fake_pg, upserts = _patch_helpers(scrape_result=_FAKE_PAYLOAD)
    counts = _run_with(
        patches,
        ["FOOCO"], fund_cache,
        cap=5, delay=0, jitter=0, yfinance_fallback=False,
    )
    assert counts["screener_ok"] == 1
    assert counts["screener_err"] == 0
    assert "FOOCO" in fund_cache
    assert fund_cache["FOOCO"]["pnl_summary"] == "PNL summary"
    assert fund_cache["FOOCO"]["ratios_summary"] == "Ratios summary"
    assert ("FOOCO", "tracker_enrich") in upserts
    assert fake_pg.committed == 1


def test_enrich_screener_error_with_yfinance_fallback(fund_cache):
    patches, _pg, _ = _patch_helpers(
        scrape_result={"error": "HTTP 404"},
        yf_result={"Stock P/E": "18", "ROE": "20%", "Market Cap": "N/A"},
    )
    counts = _run_with(
        patches,
        ["BARCO"], fund_cache,
        cap=5, delay=0, jitter=0, yfinance_fallback=True,
    )
    assert counts["screener_err"] == 1
    assert counts["yfinance_ok"] == 1
    assert "BARCO" in fund_cache
    assert fund_cache["BARCO"]["ratios_summary"].endswith("[yfinance]")
    assert "P/E: 18" in fund_cache["BARCO"]["ratios_summary"]
    # N/A values dropped
    assert "Mkt Cap" not in fund_cache["BARCO"]["ratios_summary"]


def test_enrich_both_fail_leaves_cache_unchanged(fund_cache):
    fund_cache["EXISTING"] = {"SYMBOL": "EXISTING"}
    patches, _pg, _ = _patch_helpers(
        scrape_result={"error": "boom"},
        yf_result={},
    )
    counts = _run_with(
        patches,
        ["NEWSYM"], fund_cache,
        cap=5, delay=0, jitter=0, yfinance_fallback=True,
    )
    assert counts["screener_err"] == 1
    assert counts["yfinance_ok"] == 0
    assert "NEWSYM" not in fund_cache
    assert "EXISTING" in fund_cache


def test_enrich_cap_honored(fund_cache):
    called = []
    def _scrape(sym):
        called.append(sym)
        return _FAKE_PAYLOAD

    patches, _pg, upserts = _patch_helpers(scrape_result=_scrape)
    syms = [f"S{i}" for i in range(100)]
    counts = _run_with(
        patches, syms, fund_cache,
        cap=5, delay=0, jitter=0, yfinance_fallback=False,
    )
    assert len(called) == 5
    assert counts["screener_ok"] == 5


def test_enrich_pg_unavailable_still_updates_memory(fund_cache):
    patches, _pg, upserts = _patch_helpers(
        scrape_result=_FAKE_PAYLOAD,
        pg_raises=True,
    )
    counts = _run_with(
        patches, ["MEMONLY"], fund_cache,
        cap=5, delay=0, jitter=0, yfinance_fallback=False,
    )
    assert counts["screener_ok"] == 1
    assert "MEMONLY" in fund_cache
    assert upserts == []  # never called because pg() raised


def test_enrich_zero_cap_short_circuits(fund_cache):
    # Should not even import helpers when cap=0
    counts = srt._enrich_missing_fundamentals(
        ["A", "B"], fund_cache, cap=0, delay=0, jitter=0, yfinance_fallback=False
    )
    assert counts == {"screener_ok": 0, "screener_err": 0, "yfinance_ok": 0, "skipped": 0}
    assert fund_cache == {}


def test_enrich_empty_list_short_circuits(fund_cache):
    counts = srt._enrich_missing_fundamentals(
        [], fund_cache, cap=10, delay=0, jitter=0, yfinance_fallback=False
    )
    assert counts == {"screener_ok": 0, "screener_err": 0, "yfinance_ok": 0, "skipped": 0}


def test_enrich_summary_all_none_marks_skipped(fund_cache):
    # Screener succeeds but every section builder returns falsy → skipped
    patches, _pg, _ = _patch_helpers(scrape_result=_FAKE_PAYLOAD)
    # Override summary builders to all return None
    extra = [
        patch("scripts.backfill_screener_fundamentals.build_pnl_summary", return_value=None),
        patch("scripts.backfill_screener_fundamentals.build_quarterly_summary", return_value=None),
        patch("scripts.backfill_screener_fundamentals.build_balance_sheet_summary", return_value=None),
        patch("scripts.backfill_screener_fundamentals.build_ratios_summary", return_value=None),
    ]
    counts = _run_with(
        patches + extra,
        ["BLANKCO"], fund_cache,
        cap=5, delay=0, jitter=0, yfinance_fallback=False,
    )
    assert counts["skipped"] == 1
    assert counts["screener_ok"] == 0
    assert "BLANKCO" not in fund_cache
