from datetime import date

import pytest

from terminal.copilot_workflows.plan import handle_plan_command


def test_plan_outputs_implementation_ready_tasks_without_writing(tmp_path):
    text = handle_plan_command("/plan add copilot task memory", plans_dir=tmp_path)

    assert "Implementation Plan" in text
    assert "Files To Inspect" in text
    assert "Tests To Add" in text
    assert "Verification Commands" in text
    assert not list(tmp_path.iterdir())


def test_plan_write_saves_deterministic_markdown(tmp_path):
    text = handle_plan_command(
        "/plan add copilot task memory --write",
        plans_dir=tmp_path,
        today=date(2026, 6, 4),
    )

    path = tmp_path / "2026-06-04-add-copilot-task-memory.md"
    assert path.exists()
    assert "Saved Plan" in text
    assert "add copilot task memory" in path.read_text(encoding="utf-8")


def test_plan_write_refuses_to_overwrite(tmp_path):
    handle_plan_command(
        "/plan add copilot task memory --write",
        plans_dir=tmp_path,
        today=date(2026, 6, 4),
    )

    with pytest.raises(FileExistsError):
        handle_plan_command(
            "/plan add copilot task memory --write",
            plans_dir=tmp_path,
            today=date(2026, 6, 4),
        )
