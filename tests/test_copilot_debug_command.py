from terminal.copilot_workflows.debug import handle_debug_command


def test_debug_outputs_investigation_plan_without_fix_claim():
    text = handle_debug_command("/debug results_analysis links not working")

    assert "Debug Plan" in text
    assert "Reproduce" in text
    assert "reports/latest" in text
    assert "No files will be modified" in text
    assert "Fixed:" not in text
    assert "complete" not in text.lower()


def test_debug_apply_flag_is_guarded():
    text = handle_debug_command("/debug broken report --apply")

    assert "--apply" in text
    assert "only produces an investigation plan" in text
