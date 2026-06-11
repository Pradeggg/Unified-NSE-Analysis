from terminal.copilot_workflows.brainstorm import handle_brainstorm_command


def test_brainstorm_scaffolds_discussion_without_implementation():
    text = handle_brainstorm_command("/brainstorm portfolio strategy lab")

    assert "portfolio strategy lab" in text
    assert "Approaches" in text
    assert "Approval Gate" in text
    assert "implementation starts" in text
