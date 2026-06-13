from terminal.copilot_workflows.brainstorm import handle_brainstorm_command, render_brainstorm


def test_brainstorm_scaffolds_discussion_without_implementation():
    text = handle_brainstorm_command("/brainstorm add a new alert feature")

    assert "add a new alert feature" in text
    assert "Approaches" in text
    assert "Approval Gate" in text
    assert "approved" in text


def test_brainstorm_market_topic_shows_trading_approaches():
    text = render_brainstorm("intraday strategy for BANKNIFTY")

    assert "intraday strategy for BANKNIFTY" in text
    assert "Intraday" in text
    assert "Swing" in text
    assert "Options play" in text
    assert "F&O" in text
    assert "Approval Gate" in text


def test_brainstorm_context_symbols_injected():
    text = render_brainstorm("breakout setup", context_symbols=["NIFTY", "BANKNIFTY"])

    assert "NIFTY" in text
    assert "BANKNIFTY" in text
    assert "Market Context" in text


def test_brainstorm_no_symbols_generic_mode():
    text = render_brainstorm("refactor the logging module")

    # Should use software-engineering template, not trading template
    assert "Minimal" in text
    assert "Structured" in text
    assert "Approval Gate" in text


def test_brainstorm_empty_topic_fallback():
    text = render_brainstorm("")
    assert "unspecified topic" in text
    assert "Approval Gate" in text
