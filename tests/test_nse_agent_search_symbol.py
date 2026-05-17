import nse_agent


def test_canonical_search_symbol_uses_symbol_resolver_for_aliases():
    assert nse_agent._canonical_search_symbol("USL") == "UNITDSPR"


def test_search_command_assessment_splits_entity_from_topic():
    symbol, context, output_format = nse_agent._assess_search_command("/search USL growth strategy")

    assert symbol == "UNITDSPR"
    assert context == "growth strategy"
    assert output_format == ""


def test_search_command_assessment_preserves_format():
    symbol, context, output_format = nse_agent._assess_search_command("/search United Spirits concall pdf")

    assert symbol == "UNITDSPR"
    assert context == "concall"
    assert output_format == "pdf"


def test_interactive_input_expands_numbered_slash_followup_before_dispatch():
    followups = ["`/search USL growth strategy` — Look into USL's growth initiatives."]

    expanded, note = nse_agent._normalise_interactive_input("1", followups)

    assert expanded == "/search USL growth strategy"
    assert note == "/search USL growth strategy  —  Look into USL's growth initiatives."


def test_interactive_input_expands_prompt_shortcut_before_dispatch():
    expanded, note = nse_agent._normalise_interactive_input("p1", [])

    assert expanded == nse_agent._PROMPT_INDEX[1][2]
    assert nse_agent._PROMPT_INDEX[1][1] in note


def test_direct_terminal_interaction_is_remembered_for_followups():
    class DummyAgent:
        def __init__(self):
            self.calls = []

        def _remember_interaction(self, user_input, answer, tool_results, turn_context=None):
            self.calls.append((user_input, answer, tool_results, turn_context))

    agent = DummyAgent()

    nse_agent._remember_terminal_interaction(
        agent,
        "/strategy-council KIRLOSENG llm",
        "Strategy Council — KIRLOSENG Recommendation: NO_TRADE Report: /tmp/report.md",
        intent="strategy_council",
        source_label="Strategy Council report",
        result_type="report",
    )

    assert agent.calls
    ctx = agent.calls[0][3]
    assert ctx.result_type == "report"
    assert ctx.source_label == "Strategy Council report"
    assert "KIRLOSENG" in ctx.symbols
