"""Tests for the lenient LLM clarification-questions parser.

Verifies that ``_parse_questions`` skips malformed entries silently,
picks up the new ``preview`` field, and routes shape through the
``terminal.clarify`` builder dataclasses (single source of truth with
the static-builder callsites in situation_assessment).
"""

from __future__ import annotations

from terminal.assessment_llm import _parse_questions
from terminal.situation_assessment import ClarificationQuestion


def _ok_option(label: str, text: str, **extra) -> dict:
    return {
        "label": label,
        "text": text,
        "bound_action": {"decision": "run_tool_plan", "tool_plan": [["x", {}]]},
        **extra,
    }


def test_parse_questions_picks_up_preview_field():
    raw = [{
        "prompt": "Which view?",
        "options": [
            _ok_option("A", "intraday", preview="15m chart"),
            _ok_option("B", "daily"),
        ],
        "default_label": "A",
    }]
    result = _parse_questions(raw)
    assert len(result) == 1
    q = result[0]
    assert isinstance(q, ClarificationQuestion)
    assert q.prompt == "Which view?"
    assert q.default_label == "A"
    assert q.options[0].preview == "15m chart"
    assert q.options[1].preview == ""
    assert q.options[0].bound_action["decision"] == "run_tool_plan"


def test_parse_questions_skips_non_dict_entries():
    raw = ["not-a-dict", 42, None, {
        "prompt": "ok?",
        "options": [_ok_option("A", "yes"), _ok_option("B", "no")],
    }]
    result = _parse_questions(raw)
    assert len(result) == 1
    assert result[0].prompt == "ok?"


def test_parse_questions_skips_questions_with_no_options():
    raw = [
        {"prompt": "empty", "options": []},
        {"prompt": "missing"},
        {"prompt": "junk options", "options": ["x", 1, None]},
        {"prompt": "valid", "options": [_ok_option("A", "yes")]},
    ]
    result = _parse_questions(raw)
    assert [q.prompt for q in result] == ["valid"]


def test_parse_questions_skips_non_dict_options_within_question():
    raw = [{
        "prompt": "mix",
        "options": [
            "garbage",
            _ok_option("A", "real"),
            42,
            _ok_option("B", "another"),
        ],
    }]
    result = _parse_questions(raw)
    assert len(result) == 1
    assert [o.label for o in result[0].options] == ["A", "B"]


def test_parse_questions_coerces_missing_strings_to_empty():
    raw = [{
        "options": [{"bound_action": {}}],
    }]
    result = _parse_questions(raw)
    assert len(result) == 1
    q = result[0]
    assert q.prompt == ""
    assert q.options[0].label == ""
    assert q.options[0].text == ""
    assert q.options[0].bound_action == {}


def test_parse_questions_empty_input_returns_empty_tuple():
    assert _parse_questions([]) == ()


def test_parse_questions_returns_tuple_not_list():
    raw = [{"prompt": "p", "options": [_ok_option("A", "y")]}]
    assert isinstance(_parse_questions(raw), tuple)
