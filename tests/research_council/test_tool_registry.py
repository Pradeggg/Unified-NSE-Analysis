import sys

from terminal.research_council.tool_registry import (
    DEFAULT_REGISTRY,
    ToolNotRegistered,
    build_default_registry,
)


def test_default_registry_import_is_lazy():
    sys.modules.pop("terminal.tools", None)

    registry = build_default_registry()

    assert "terminal.tools" not in sys.modules
    assert registry.resolve("screen.stage2")
    assert "terminal.tools" not in sys.modules


def test_mvp_registry_tools_resolve_to_callables():
    expected = {
        "regime.detect",
        "breadth.summarize",
        "flows.fii_dii_5d",
        "macro.proxy_signals",
        "sector.rs_ranking",
        "sector.breadth_health",
        "sector.top_stocks",
        "screen.stage2",
        "screen.high_rs",
        "screen.momentum_52w",
        "fund.results_trend",
        "fund.balance_sheet_health",
        "events.upcoming",
        "fno.buildup",
        "strategy.build",
    }

    assert set(DEFAULT_REGISTRY.names()) == expected
    for name in expected:
        assert callable(DEFAULT_REGISTRY.resolve(name))


def test_missing_tool_returns_structured_error():
    try:
        DEFAULT_REGISTRY.resolve("missing.tool")
    except ToolNotRegistered as exc:
        payload = exc.to_result()
    else:
        raise AssertionError("expected ToolNotRegistered")

    assert payload == {
        "ok": False,
        "error": "tool_not_registered",
        "tool_name": "missing.tool",
    }


def test_stage2_adapter_calls_lazy_terminal_tool(monkeypatch):
    calls = {}

    def fake_run_screener_query(screen_type="stage2", top_n=10):
        calls["screen_type"] = screen_type
        calls["top_n"] = top_n
        return {"ok": True, "screen_type": screen_type, "top_n": top_n}

    import terminal.research_council.tool_adapters as adapters

    monkeypatch.setattr(adapters, "_terminal_tool", lambda name: fake_run_screener_query)

    result = DEFAULT_REGISTRY.resolve("screen.stage2")(top_n=7)

    assert result["screen_type"] == "stage2"
    assert calls == {"screen_type": "stage2", "top_n": 7}


def test_adapter_normalizes_successful_payload_without_ok(monkeypatch):
    def fake_run_screener_query(screen_type="stage2", top_n=10):
        return {"count": 1, "results": [{"symbol": "AAA"}]}

    import terminal.research_council.tool_adapters as adapters

    monkeypatch.setattr(adapters, "_terminal_tool", lambda name: fake_run_screener_query)

    result = DEFAULT_REGISTRY.resolve("screen.stage2")(top_n=1)

    assert result == {"ok": True, "count": 1, "results": [{"symbol": "AAA"}]}
