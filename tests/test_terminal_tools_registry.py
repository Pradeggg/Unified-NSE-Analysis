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
