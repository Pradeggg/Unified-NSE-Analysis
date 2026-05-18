from terminal.tools import TOOL_REGISTRY, openai_tool_schemas


def test_tool_registry_entries_are_well_formed():
    assert TOOL_REGISTRY

    for name, entry in TOOL_REGISTRY.items():
        assert isinstance(name, str)
        assert name
        assert isinstance(entry, tuple)
        assert len(entry) == 3

        func, description, params = entry
        assert callable(func), f"{name} does not map to a callable"
        assert isinstance(description, str), f"{name} description must be text"
        assert description.strip(), f"{name} description is empty"
        assert isinstance(params, dict), f"{name} params must be a JSON schema dict"
        assert params.get("type") == "object", f"{name} params must be an object schema"
        assert isinstance(params.get("properties", {}), dict), f"{name} properties must be a dict"
        assert isinstance(params.get("required", []), list), f"{name} required must be a list"


def test_openai_tool_schemas_match_registry():
    schemas = openai_tool_schemas()

    assert len(schemas) == len(TOOL_REGISTRY)
    schema_names = {schema["function"]["name"] for schema in schemas}
    assert schema_names == set(TOOL_REGISTRY)

    for schema in schemas:
        assert schema["type"] == "function"
        function = schema["function"]
        assert function["description"].strip()
        assert function["parameters"]["type"] == "object"


def test_call_tool_drops_unknown_kwargs_from_llm_plans(monkeypatch):
    """Regression: an LLM-generated tool plan that passes a hallucinated
    kwarg (e.g. ``get_live_market_overview(timeframe='30m')``) must not
    crash the executor with a TypeError. ``call_tool`` should filter
    kwargs to the target function's signature when the function does not
    accept ``**kwargs``.
    """
    from terminal import tools as tools_mod

    calls: list[dict] = []

    def fake_overview():
        calls.append({})
        return {"ok": True, "indices": []}

    original = tools_mod.TOOL_REGISTRY["get_live_market_overview"]
    monkeypatch.setitem(
        tools_mod.TOOL_REGISTRY,
        "get_live_market_overview",
        (fake_overview, original[1], original[2]),
    )

    result = tools_mod.call_tool(
        "get_live_market_overview",
        {"timeframe": "30m", "minutes": 30},
    )

    assert result == {"ok": True, "indices": []}
    assert calls == [{}], "unknown kwargs must be dropped before invocation"


def test_call_tool_preserves_known_kwargs():
    """Sanity: known kwargs still flow through unchanged."""
    from terminal.tools import call_tool

    result = call_tool("get_intraday_market_recap", {"minutes": 30})
    # The real tool may return data or an error dict depending on environment,
    # but it must NOT be a TypeError about an unexpected keyword argument.
    assert isinstance(result, dict)
    err = result.get("error", "")
    assert "unexpected keyword argument" not in err
