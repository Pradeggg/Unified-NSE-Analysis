from terminal.tools import resolve_symbol
import nse_agent


def test_resolve_symbol_supports_common_usl_alias():
    resolved = resolve_symbol("USL")

    assert resolved["symbol"] == "UNITDSPR"
    assert resolved["confidence"] == "exact"


def test_resolve_symbol_united_spirits_prefers_unitdspr_not_globus():
    resolved = resolve_symbol("United Spirits")

    assert resolved["symbol"] == "UNITDSPR"
    assert "GLOBUSSPR" not in resolved.get("candidates", [])


def test_search_command_canonicalizes_symbol_before_context():
    assert nse_agent._resolve_search_symbol("USL") == "UNITDSPR"
    assert nse_agent._resolve_search_symbol("USL growth strategy") == "UNITDSPR"
