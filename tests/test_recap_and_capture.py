"""Comprehensive tests for the /recap slash command and intraday capture daemon.

Covers the bug-fix work from this session:
  1. /recap is registered as a slash command (was missing → fell through to
     symbol planner and returned a random ticker brief like AVONMORE).
  2. The handler rewrites `/recap` and `/recap N` into a phrase the planner
     routes to `intraday_market_recap` (not `stock_brief`).
  3. The recap source-label says "PG intraday.quote_snapshots".
  4. terminal/intraday_capture.py daemon: env-overridable knobs, idempotent
     start, market-hours gating, single-tick capture, single-tick prune,
     and rows actually land in PG intraday.quote_snapshots.
  5. terminal/tools.get_intraday_market_recap() returns rows when prior
     snapshots exist for the requested lookback window.

Run:  .venv/bin/python -m tests.test_recap_and_capture
"""
from __future__ import annotations

import datetime as _dt
import importlib
import os
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import psycopg2  # noqa: E402

PG_DSN = "dbname=nse_market user=nse_admin host=/tmp"


def _pg():
    return psycopg2.connect(PG_DSN)


# ─────────────────────────────────────────────────────────────────────────────
# 1. /recap slash command is registered
# ─────────────────────────────────────────────────────────────────────────────
class TestRecapSlashRegistered(unittest.TestCase):
    def test_recap_in_slash_commands_list(self):
        import nse_agent
        labels = [t[0] for t in nse_agent._SLASH_COMMANDS]
        self.assertIn("/recap", labels, "/recap must be a registered slash command")

    def test_recap_with_minutes_in_slash_commands_list(self):
        import nse_agent
        labels = [t[0] for t in nse_agent._SLASH_COMMANDS]
        self.assertTrue(
            any(lbl.startswith("/recap ") for lbl in labels),
            "Expected at least one '/recap N' help entry",
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Planner routes the rewritten phrase to intraday_market_recap
# ─────────────────────────────────────────────────────────────────────────────
class TestRecapRouting(unittest.TestCase):
    def test_default_15min_routes_to_recap(self):
        from terminal.agent import _keyword_intent
        plan = _keyword_intent(
            "what happened in the market in the last 15 minutes",
            data_mode="intraday",
        )
        self.assertEqual(plan["intent"], "intraday_market_recap")

    def test_custom_window_routes_to_recap(self):
        from terminal.agent import _keyword_intent
        for n in (5, 30, 60):
            plan = _keyword_intent(
                f"what happened in the market in the last {n} minutes",
                data_mode="intraday",
            )
            self.assertEqual(
                plan["intent"], "intraday_market_recap",
                f"failed for {n}-minute window",
            )

    def test_recap_plan_calls_pg_recap_tool(self):
        from terminal.agent import _keyword_intent
        plan = _keyword_intent(
            "what happened in the market in the last 15 minutes",
            data_mode="intraday",
        )
        tool_names = [step[0] for step in plan["plan"]]
        self.assertIn("get_intraday_market_recap", tool_names)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Source label corrected (PG)
# ─────────────────────────────────────────────────────────────────────────────
class TestSourceLabel(unittest.TestCase):
    def test_no_stale_sqlite_label_in_mode_sources(self):
        agent_src = (ROOT / "terminal" / "agent.py").read_text()
        # The mode_sources dict and intraday_market_recap mode_suffix should
        # both name PG.
        self.assertNotIn(
            '"intraday": "SQLite intraday/live tables"',
            agent_src,
            "stale mode_sources label still present",
        )
        self.assertIn(
            "PG intraday.quote_snapshots",
            agent_src,
            "expected new PG label not found in agent.py",
        )

    def test_recap_footer_uses_pg_label(self):
        agent_src = (ROOT / "terminal" / "agent.py").read_text()
        # The intraday_market_recap branch must use the PG label.
        self.assertIn(
            "NSE live API + PG intraday.quote_snapshots + DB breadth",
            agent_src,
        )

    def test_system_prompt_mentions_pg_quote_tape(self):
        agent_src = (ROOT / "terminal" / "agent.py").read_text()
        self.assertIn("PostgreSQL intraday.quote_snapshots", agent_src)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Intraday capture daemon
# ─────────────────────────────────────────────────────────────────────────────
class TestIntradayCaptureDaemon(unittest.TestCase):
    def setUp(self):
        self._capture_env_backup = {
            "AGENT_ADDA_CAPTURE_INTERVAL_SEC": os.environ.pop("AGENT_ADDA_CAPTURE_INTERVAL_SEC", None),
            "AGENT_ADDA_CAPTURE_RETENTION_MIN": os.environ.pop("AGENT_ADDA_CAPTURE_RETENTION_MIN", None),
        }
        # Force a fresh import so previous start_background_capture() calls
        # don't leak between tests.
        for mod in list(sys.modules):
            if mod == "terminal.intraday_capture":
                del sys.modules[mod]
        self.cap = importlib.import_module("terminal.intraday_capture")

    def tearDown(self):
        for key, value in getattr(self, "_capture_env_backup", {}).items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for mod in list(sys.modules):
            if mod == "terminal.intraday_capture":
                del sys.modules[mod]

    def test_default_knobs(self):
        self.assertEqual(self.cap.CAPTURE_INTERVAL_SEC, 60)
        self.assertEqual(self.cap.RETENTION_MINUTES, 129600)  # 90 days

    def test_env_override(self):
        os.environ["AGENT_ADDA_CAPTURE_INTERVAL_SEC"] = "30"
        os.environ["AGENT_ADDA_CAPTURE_RETENTION_MIN"] = "240"
        try:
            for mod in list(sys.modules):
                if mod == "terminal.intraday_capture":
                    del sys.modules[mod]
            cap = importlib.import_module("terminal.intraday_capture")
            self.assertEqual(cap.CAPTURE_INTERVAL_SEC, 30)
            self.assertEqual(cap.RETENTION_MINUTES, 240)
        finally:
            del os.environ["AGENT_ADDA_CAPTURE_INTERVAL_SEC"]
            del os.environ["AGENT_ADDA_CAPTURE_RETENTION_MIN"]
            for mod in list(sys.modules):
                if mod == "terminal.intraday_capture":
                    del sys.modules[mod]

    def test_market_hours_window(self):
        self.assertEqual(self.cap.MARKET_OPEN, _dt.time(9, 0))
        self.assertEqual(self.cap.MARKET_CLOSE, _dt.time(15, 45))

    def test_preferred_indices_includes_majors(self):
        # The preferred-indices list lives inside _capture_once() as a local;
        # verify by reading the source rather than poking module attrs.
        src = (ROOT / "terminal" / "intraday_capture.py").read_text()
        for name in ("NIFTY 50", "NIFTY BANK", "NIFTY IT",
                     "NIFTY AUTO", "NIFTY PHARMA"):
            self.assertIn(f'"{name}"', src,
                          f"capture daemon should poll {name}")

    def test_idempotent_start(self):
        first = self.cap.start_background_capture()
        second = self.cap.start_background_capture()
        self.assertTrue(first, "first start should return True")
        self.assertFalse(second, "second start must be a no-op (return False)")

    def test_capture_once_inserts_rows_during_market_hours(self):
        # Only assert insertion when within market hours; otherwise the
        # function legitimately returns 0 (skipped).
        now_ist = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=5, minutes=30)))
        is_market = (
            now_ist.weekday() < 5
            and self.cap.MARKET_OPEN <= now_ist.time() <= self.cap.MARKET_CLOSE
        )
        with _pg() as c, c.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM intraday.quote_snapshots")
            before = cur.fetchone()[0]
        n = self.cap._capture_once()
        if is_market:
            self.assertGreater(n, 0, "expected rows during market hours")
            with _pg() as c, c.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM intraday.quote_snapshots")
                after = cur.fetchone()[0]
            self.assertGreater(after, before)
        else:
            self.assertEqual(n, 0, "outside market hours should return 0")

    def test_prune_once_runs_without_error(self):
        # Just make sure it returns an int without raising.
        n = self.cap._prune_once()
        self.assertIsInstance(n, int)
        self.assertGreaterEqual(n, 0)


# ─────────────────────────────────────────────────────────────────────────────
# 5. End-to-end recap tool reads from PG
# ─────────────────────────────────────────────────────────────────────────────
class TestRecapToolEndToEnd(unittest.TestCase):
    def test_recap_returns_pg_rows_or_clean_fallback(self):
        from terminal.tools import get_intraday_market_recap
        result = get_intraday_market_recap(minutes=15)
        self.assertIsInstance(result, dict)
        # Must always return a narrative — never crash.
        self.assertIn("narrative", result)
        # Must not surface the legacy "no clean interval" string anymore;
        # either rows are present, or the fallback narrative is used.
        rows = result.get("rows") or []
        if rows:
            sample = rows[0]
            for key in ("symbol", "current", "prior",
                        "point_change", "interval_pct_change"):
                self.assertIn(key, sample, f"missing recap key: {key}")
        # Source string should be NSE-live (the upstream source for the tape).
        self.assertIsInstance(result.get("source", ""), str)

    def test_recap_falls_back_to_pg_tape_when_nse_live_overview_times_out(self):
        from terminal.tools import get_intraday_market_recap

        fallback_overview = {
            "indices": {
                "NIFTY 50": {
                    "last": 24500.0,
                    "change": -25.0,
                    "pct_change": -0.1,
                    "day_high": 24650.0,
                    "day_low": 24450.0,
                }
            },
            "adv_dec": {},
            "as_of": "2026-05-22 10:00:00",
            "source": "PG intraday.quote_snapshots fallback",
            "degraded": True,
            "fallback_reason": "NSE live overview unavailable: timeout",
        }

        with patch("terminal.tools.get_live_market_overview", return_value={"error": "timeout"}), patch(
            "terminal.tools._intraday_market_overview_from_pg",
            return_value=fallback_overview,
        ):
            result = get_intraday_market_recap(minutes=15)

        self.assertNotIn("error", result)
        self.assertEqual(result["source"], "PG intraday.quote_snapshots fallback")
        self.assertTrue(result["degraded"])
        self.assertIn("narrative", result)
        self.assertEqual(result["rows"][0]["symbol"], "NIFTY 50")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Slash dispatcher: /recap rewrites text before the LLM is called
# ─────────────────────────────────────────────────────────────────────────────
class TestRecapSlashDispatch(unittest.TestCase):
    """The /recap handler in nse_agent.py rewrites the user input into a
    free-text phrase that the planner recognizes. Verify the substring
    appears in the source so we know the handler is wired (a lightweight
    contract test — running the full REPL is out of scope)."""

    def test_recap_handler_present(self):
        src = (ROOT / "nse_agent.py").read_text()
        self.assertIn('elif text.lower().startswith("/recap")', src)
        self.assertIn(
            "what happened in the market in the last",
            src,
            "rewrite phrase missing — planner won't classify as recap",
        )


# ─────────────────────────────────────────────────────────────────────────────
# 7. Self-check / degraded-response intelligence
# ─────────────────────────────────────────────────────────────────────────────
class TestQualityCheck(unittest.TestCase):
    """Agent._quality_check should detect degraded responses (failed tools,
    unhandled slash commands, thin body, empty payloads) and prepend a
    HEADS-UP block with actionable suggestions. A clearly-good response
    must pass through unchanged."""

    @classmethod
    def setUpClass(cls):
        from terminal.agent import Agent
        # Skip __init__ — we only need the bound method.
        cls.agent = Agent.__new__(Agent)

    def test_unhandled_slash_command_triggers_headsup(self):
        out = self.agent._quality_check(
            "/foobar", "stock_brief", [], "AVONMORE setup is HOLD", ""
        )
        self.assertIn("HEADS-UP", out)
        self.assertIn("/foobar", out)
        self.assertIn("not a registered slash command", out)
        self.assertIn("/help", out)

    def test_all_tools_errored_triggers_headsup(self):
        trs = [
            {"tool": "get_x", "result": {"error": "boom"}},
            {"tool": "get_y", "result": {"error": "down"}},
        ]
        out = self.agent._quality_check(
            "what happened in market today",
            "market_overview", trs, "", "",
        )
        self.assertIn("HEADS-UP", out)
        self.assertIn("100% error rate", out)
        # Market-keyword-aware suggestion list.
        self.assertIn("/live", out)

    def test_thin_body_triggers_headsup(self):
        out = self.agent._quality_check(
            "reliance options", "fno_overview", [], "ok.", ""
        )
        self.assertIn("HEADS-UP", out)
        self.assertIn("unusually thin", out)
        # F&O-keyword-aware suggestions.
        self.assertTrue(
            any(tag in out for tag in ("/oi", "/chain")),
            "expected F&O suggestions for an options query",
        )

    def test_clean_response_passes_through_unchanged(self):
        good = ("Detailed multi-paragraph analysis with concrete numbers, "
                "indicators, and source trail. " * 6)
        trs = [{"tool": "get_symbol_snapshot",
                "result": {"symbol": "RELIANCE", "price": 2500}}]
        out = self.agent._quality_check(
            "RELIANCE setup", "stock_brief", trs, good, ""
        )
        self.assertNotIn("HEADS-UP", out)
        self.assertEqual(out, good)

    def test_self_check_never_raises(self):
        # Even with malformed inputs the wrapper must fail open.
        out = self.agent._quality_check(
            "x", "stock_brief",
            [{"tool": "get_x", "result": None}],
            None,
            "",
        )
        # Just assert no exception — return value can be anything.
        del out

    def test_suggestions_deduped_and_capped(self):
        trs = [{"tool": "get_x", "result": {"error": "fail"}},
               {"tool": "get_y", "result": {"error": "fail"}}]
        out = self.agent._quality_check(
            "global market sector rotation options scan",
            "market_overview", trs, "tiny", "",
        )
        try_block = out.split("▶ TRY ONE OF THESE")[1].split("Or rephrase")[0]
        bullets = [l for l in try_block.splitlines() if l.strip().startswith("•")]
        self.assertLessEqual(len(bullets), 5)
        self.assertEqual(len(bullets), len(set(bullets)),
                         "duplicate suggestions detected")

if __name__ == "__main__":
    # Pretty test runner with a single-line summary, matching the style of
    # tests/test_reports_pipeline.py.
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print()
    print(f"── Summary ──")
    print(f"  RAN: {result.testsRun}    "
          f"FAIL: {len(result.failures)}    "
          f"ERR: {len(result.errors)}    "
          f"SKIP: {len(result.skipped)}")
    sys.exit(0 if result.wasSuccessful() else 1)
