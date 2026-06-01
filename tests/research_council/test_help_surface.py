from __future__ import annotations


def test_curated_help_includes_research_council_commands():
    from terminal.help import SECTIONS

    entries = SECTIONS["strategy_lab"]["entries"]
    commands = [command for command, _description in entries]

    assert "/council today --horizon swing --risk moderate" in commands
    assert "/council today --evidence-only --horizon swing" in commands
    assert "/council sector NIFTY AUTO --horizon swing" in commands
    assert "/council stock MODISONLTD --horizon swing" in commands
    assert "/council report --run latest --format html" in commands
