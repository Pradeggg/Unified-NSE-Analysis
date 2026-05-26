"""AA-CC-1: tests for the AskUserQuestion builder API."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from terminal.clarify import AskUserQuestion, Option, Question
from terminal.situation_assessment import (
    _render_structured_clarifications,
    match_clarification_reply,
)


def _basic_ask() -> AskUserQuestion:
    return AskUserQuestion(
        user_is_asking="User wants RELIANCE but didn't specify timeframe.",
        context_found="No prior RELIANCE context.",
        source_assessment="Need to choose fetch.",
        questions=[
            Question(
                prompt="What timeframe for RELIANCE?",
                options=[
                    Option.run_tool_plan(
                        label="A", text="EOD daily setup",
                        tools=[("get_technical_setup", {"symbol": "RELIANCE"})],
                        preview="Daily candles, EMA stack",
                    ),
                    Option.run_tool_plan(
                        label="B", text="15m intraday setup",
                        tools=[("scan_symbols_intraday", {"symbols": ["RELIANCE"]})],
                    ),
                    Option.answer_from_context(
                        label="C", text="Summarize from memory",
                    ),
                ],
                default_label="A",
            ),
        ],
    )


class TestOptionFactories(unittest.TestCase):
    def test_run_tool_plan_shape(self):
        opt = Option.run_tool_plan(
            label="A", text="Do X",
            tools=[("foo", {"x": 1})], resolved_entities=["FOO"], preview="hint",
        )
        self.assertEqual(opt.label, "A")
        self.assertEqual(opt.preview, "hint")
        self.assertEqual(opt.bound_action["decision"], "run_tool_plan")
        self.assertEqual(opt.bound_action["tool_plan"], [("foo", {"x": 1})])
        self.assertEqual(opt.bound_action["resolved_entities"], ["FOO"])

    def test_answer_from_context_shape(self):
        opt = Option.answer_from_context(label="C", text="From memory")
        self.assertEqual(opt.bound_action, {"decision": "answer_from_context"})


class TestAskUserQuestionValidation(unittest.TestCase):
    def test_basic_valid_ask_builds(self):
        ask = _basic_ask()
        self.assertEqual(len(ask.questions), 1)

    def test_empty_questions_rejected(self):
        with self.assertRaises(ValueError):
            AskUserQuestion(questions=[])

    def test_more_than_4_questions_rejected(self):
        q = Question(
            prompt="Pick?",
            options=[
                Option.answer_from_context(label="A", text="a"),
                Option.answer_from_context(label="B", text="b"),
            ],
        )
        with self.assertRaises(ValueError):
            AskUserQuestion(questions=[q, q, q, q, q])

    def test_fewer_than_2_options_rejected(self):
        with self.assertRaises(ValueError):
            AskUserQuestion(questions=[
                Question(prompt="?", options=[
                    Option.answer_from_context(label="A", text="only"),
                ]),
            ])

    def test_more_than_4_options_rejected(self):
        opts = [Option.answer_from_context(label=L, text=L) for L in "ABCDE"]
        with self.assertRaises(ValueError):
            AskUserQuestion(questions=[Question(prompt="?", options=opts)])

    def test_non_sequential_labels_rejected(self):
        with self.assertRaises(ValueError):
            AskUserQuestion(questions=[
                Question(prompt="?", options=[
                    Option.answer_from_context(label="A", text="a"),
                    Option.answer_from_context(label="C", text="c"),  # skipped B
                ]),
            ])

    def test_lowercase_labels_rejected(self):
        with self.assertRaises(ValueError):
            AskUserQuestion(questions=[
                Question(prompt="?", options=[
                    Option.answer_from_context(label="a", text="x"),
                    Option.answer_from_context(label="b", text="y"),
                ]),
            ])

    def test_default_label_outside_options_rejected(self):
        with self.assertRaises(ValueError):
            AskUserQuestion(questions=[
                Question(prompt="?", default_label="Z", options=[
                    Option.answer_from_context(label="A", text="a"),
                    Option.answer_from_context(label="B", text="b"),
                ]),
            ])

    def test_empty_prompt_rejected(self):
        with self.assertRaises(ValueError):
            AskUserQuestion(questions=[
                Question(prompt="   ", options=[
                    Option.answer_from_context(label="A", text="a"),
                    Option.answer_from_context(label="B", text="b"),
                ]),
            ])

    def test_run_tool_plan_with_empty_plan_rejected(self):
        bad = Option(label="A", text="x", bound_action={"decision": "run_tool_plan", "tool_plan": []})
        ok = Option.answer_from_context(label="B", text="y")
        with self.assertRaises(ValueError):
            AskUserQuestion(questions=[Question(prompt="?", options=[bad, ok])])

    def test_invalid_decision_rejected(self):
        bad = Option(label="A", text="x", bound_action={"decision": "mystery"})
        ok = Option.answer_from_context(label="B", text="y")
        with self.assertRaises(ValueError):
            AskUserQuestion(questions=[Question(prompt="?", options=[bad, ok])])


class TestToAssessment(unittest.TestCase):
    def test_to_assessment_produces_ask_clarification(self):
        ask = _basic_ask()
        sa = ask.to_assessment()
        self.assertTrue(sa.applies)
        self.assertEqual(sa.decision, "ask_clarification")
        self.assertEqual(len(sa.clarification_questions), 1)
        self.assertEqual(len(sa.clarification_questions[0].options), 3)

    def test_preview_carried_into_clarification_option(self):
        ask = _basic_ask()
        sa = ask.to_assessment()
        opt_a = sa.clarification_questions[0].options[0]
        self.assertEqual(opt_a.preview, "Daily candles, EMA stack")

    def test_assessment_plays_with_match_clarification_reply(self):
        ask = _basic_ask()
        sa = ask.to_assessment()
        matched = match_clarification_reply("B", sa)
        self.assertIsNotNone(matched)
        self.assertEqual(matched.label, "B")
        self.assertEqual(matched.bound_action["decision"], "run_tool_plan")

    def test_no_match_returns_none(self):
        ask = _basic_ask()
        sa = ask.to_assessment()
        self.assertIsNone(match_clarification_reply("nonsense-blah", sa))


class TestPreviewRendering(unittest.TestCase):
    def test_preview_appears_in_next_options(self):
        ask = _basic_ask()
        sa = ask.to_assessment()
        rendered = _render_structured_clarifications(
            sa.clarification_questions, sa.clarification_question,
        )
        self.assertIn("[A]", rendered)
        self.assertIn("Daily candles, EMA stack", rendered)
        # Option B has no preview - no ↪ line should follow it
        self.assertIn("EOD daily setup", rendered)

    def test_options_without_preview_render_unchanged(self):
        ask = AskUserQuestion(questions=[
            Question(prompt="?", options=[
                Option.answer_from_context(label="A", text="alpha"),
                Option.answer_from_context(label="B", text="beta"),
            ]),
        ])
        sa = ask.to_assessment()
        rendered = _render_structured_clarifications(
            sa.clarification_questions, sa.clarification_question,
        )
        self.assertNotIn("↪", rendered)


class TestMultiSelectWarning(unittest.TestCase):
    def test_multi_select_logs_warning_and_does_not_raise(self):
        with self.assertLogs("terminal.clarify", level="WARNING") as logs:
            AskUserQuestion(questions=[
                Question(prompt="?", multi_select=True, options=[
                    Option.answer_from_context(label="A", text="a"),
                    Option.answer_from_context(label="B", text="b"),
                ]),
            ])
        self.assertTrue(any("multi_select" in r.message for r in logs.records))


if __name__ == "__main__":
    unittest.main()
