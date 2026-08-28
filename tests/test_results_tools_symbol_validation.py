from __future__ import annotations

from terminal.results_tools import get_latest_results


def test_get_latest_results_rejects_unresolved_symbol_placeholder():
    result = get_latest_results("<RESOLVED_NSE_SYMBOL>", ingest=False)

    assert result["status"] == "error"
    assert result["symbol"] == "<RESOLVED_NSE_SYMBOL>"
    assert "unresolved symbol placeholder" in result["error"].lower()
    assert result["source_trail"]["symbol_validation"].startswith("ERROR")

