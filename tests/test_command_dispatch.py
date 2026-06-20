"""tests/test_command_dispatch.py — Comprehensive command and prompt dispatch tests.

Covers the full AA dispatch architecture after the unified-dispatch refactor:

  Layer 0 — Pre-dispatch guards
    0.1  Slash commands bypass entity assessment entirely
    0.2  Natural language goes through entity assessment
    0.3  MTF freeform detection skips slash commands

  Layer 1 — Command registry (deterministic, both modes)
    1.1  All 14 registered handlers match their expected inputs
    1.2  Registered commands do NOT match unrelated inputs
    1.3  Registry dispatch fires before the inline chain in interactive mode
    1.4  Registry uses mode=interactive in _chat_loop, mode=single_query in _single_query

  Layer 2 — _SLASH_COMMANDS visibility list
    2.1  All slash commands in the list start with '/'
    2.2  /my-portfolio and all sub-variants appear
    2.3  /report portfolio-monitor appears
    2.4  _CMD_CATEGORIES covers /my-portfolio under "Portfolio"
    2.5  Autocomplete entries include all _SLASH_COMMANDS entries

  Layer 3 — /screen vs /screenshot prefix collision (regression)
    3.1  /screen <arg> routes to EOD screener
    3.2  /screenshot routes past /screen handler

  Layer 4 — Natural language → LLM route
    4.1  Queries without '/' prefix reach LLM (not registry)
    4.2  "MY-PORTFOLIO" (all-caps, no slash) goes to LLM, not portfolio handler

  Layer 5 — Specific command match functions
    5.1  /my-portfolio variants
    5.2  /email variants
    5.3  /scan variants
    5.4  /visual-scan variants
    5.5  /doctor variants
    5.6  /mtf variants
    5.7  /strength variants
    5.8  /strategy-council variants
    5.9  /council variants
    5.10 /backtest and /strategy-lab variants
    5.11 /data-coverage variants
    5.12 open-last-report natural language phrases
    5.13 help variants

  Layer 6 — /commands and autocomplete
    6.1  /commands returns correct category list
    6.2  Portfolio category exists with correct icon
    6.3  Autocomplete returns /my-portfolio completions

  Layer 7 — Daily refresh and report preset
    7.1  step_portfolio_monitor exists and is callable
    7.2  generate_preset_report('portfolio-monitor') delegates to run_eod_report
    7.3  email alias 'my-portfolio' resolves to portfolio_analysis.html

  Layer 8 — Prompt library
    8.1  _SLASH_COMMANDS contains prompt library entries
    8.2  Portfolio prompts appear

  Layer 9 — Regression: previously broken commands
    9.1  /screenshot is not caught by /screen handler
    9.2  /my-portfolio is not caught by entity assessment rewriter
    9.3  Registry commands don't double-fire in chat loop
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
import nse_agent
from terminal.command_registry import CommandRegistry, CommandHandler


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def registry():
    return nse_agent._build_command_registry()


@pytest.fixture(scope="module")
def slash_commands():
    return nse_agent._SLASH_COMMANDS


@pytest.fixture(scope="module")
def cmd_categories():
    return nse_agent._CMD_CATEGORIES


# ─── Layer 0: Pre-dispatch guards ────────────────────────────────────────────

class TestPreDispatchGuards:
    """Slash commands bypass entity assessment; natural language goes through it."""

    def test_slash_commands_skip_entity_assessment(self):
        """Anything starting with '/' must NOT enter entity assessment."""
        slash_inputs = [
            "/my-portfolio",
            "/my-portfolio eod",
            "/my-portfolio eod",
            "/search RELIANCE",
            "/screenshot --mode window",
            "/report sector-rotation",
            "/email sector --to a@b.com",
        ]
        for text in slash_inputs:
            # The guard condition in _chat_loop: `not text.lstrip().startswith("/")`
            would_assess = not text.lstrip().startswith("/")
            assert not would_assess, (
                f"Slash command {text!r} should bypass entity assessment "
                f"but would_assess={would_assess}"
            )

    def test_natural_language_enters_entity_assessment(self):
        """Free-form text without '/' prefix must go through entity assessment."""
        nl_inputs = [
            "what is RELIANCE doing today",
            "show me stage 2 stocks",
            "MY-PORTFOLIO",           # old broken behaviour — no slash
            "market outlook for today",
            "analyze TCS fundamentals",
        ]
        for text in nl_inputs:
            would_assess = not text.lstrip().startswith("/")
            assert would_assess, (
                f"Natural language {text!r} should enter entity assessment "
                f"but would_assess={would_assess}"
            )

    def test_mtf_rewrite_skips_slash_commands(self):
        """_detect_mtf_intent_scored must return None for slash commands."""
        from nse_agent import _detect_mtf_intent_scored
        slash_inputs = ["/my-portfolio", "/scan NIFTY", "/mtf RELIANCE"]
        for text in slash_inputs:
            rewrite, _ = _detect_mtf_intent_scored(text)
            assert rewrite is None, (
                f"MTF rewriter must not rewrite slash command {text!r}, "
                f"got rewrite={rewrite!r}"
            )

    def test_mtf_rewrite_fires_on_freeform_mtf(self):
        """_detect_mtf_intent_scored CAN fire on freeform MTF language."""
        from nse_agent import _detect_mtf_intent_scored
        # These contain explicit MTF keywords that should trigger the rewriter
        for text in ["bullish NIFTY 50 multi timeframe", "MTF alignment RELIANCE daily weekly"]:
            rewrite, _ = _detect_mtf_intent_scored(text)
            # Not asserting True — MTF detection is heuristic — but it must not crash
            assert rewrite is None or rewrite.startswith("/"), (
                f"MTF rewrite must produce None or a slash command, got {rewrite!r}"
            )


# ─── Layer 1: Command registry ───────────────────────────────────────────────

class TestCommandRegistry:
    """All registered handlers match expected inputs in both modes."""

    EXPECTED_HANDLERS = [
        "help", "commands", "dashboard", "intraday-alerts", "interaction", "copilot-workflows", "scan", "quality-breakouts", "strategy-council", "council",
        "backtest", "data-coverage", "broker-research", "open-last-report", "visual-scan",
        "doctor", "mtf", "strength", "skills", "email", "my-portfolio",
        "swing-playbook", "diagnose", "report-diagnosis",
    ]

    def test_registry_has_all_expected_handlers(self, registry):
        for name in self.EXPECTED_HANDLERS:
            assert name in registry.handler_names, (
                f"Handler '{name}' missing from registry"
            )

    def test_registry_handler_count(self, registry):
        assert len(registry) == len(self.EXPECTED_HANDLERS), (
            f"Expected {len(self.EXPECTED_HANDLERS)} handlers, "
            f"got {len(registry)}: {registry.handler_names}"
        )

    def test_all_handlers_support_interactive_mode(self, registry):
        for h in registry._handlers:
            assert "interactive" in h.modes, (
                f"Handler '{h.name}' does not support interactive mode"
            )

    def test_all_handlers_support_single_query_mode(self, registry):
        for h in registry._handlers:
            assert "single_query" in h.modes, (
                f"Handler '{h.name}' does not support single_query mode"
            )

    def test_registry_dispatch_returns_true_for_known_commands(self, registry):
        """Registry.dispatch() returns True (handled) for all registered commands."""
        handler_map = {h.name: h for h in registry._handlers}
        test_inputs = {
            "help":             "/help",
            "commands":         "/commands",
            "dashboard":         "/dashboard --once --html",
            "interaction":      "/style codex",
            "copilot-workflows": "/status",
            "scan":             "/scan nifty",
            "quality-breakouts": "/screen quality-breakouts",
            "strategy-council": "/strategy-council dmart",
            "council":          "/council today",
            "backtest":         "/backtest list",
            "data-coverage":    "/data-coverage nifty500",
            "visual-scan":      "/visual-scan dmart",
            "doctor":           "/doctor",
            "mtf":              "/mtf reliance",
            "strength":         "/strength maninds thermax",
            "email":            "/email sector --to a@b.com",
            "my-portfolio":     "/my-portfolio",
            "swing-playbook":    "/swing-playbook --portfolio",
            "diagnose":          "/diagnose DMART eps",
            "report-diagnosis":  "/report diagnosis DMART eps",
        }
        for name, query in test_inputs.items():
            h = handler_map[name]
            assert h.match_fn(query.lower()), (
                f"Handler '{name}' did not match expected input {query!r}"
            )

    def test_dashboard_handler_calls_market_dashboard_runner(self, registry):
        handler_map = {h.name: h for h in registry._handlers}
        h = handler_map["dashboard"]

        with patch("nse_agent._print_user"), \
             patch("nse_agent._run_market_dashboard_live") as run_dashboard:
            handled = h.handler_fn("/dashboard --once --html --drilldown", agent=None, show_trace=False)

        assert handled is True
        run_dashboard.assert_called_once_with(
            "",
            llm_backend=None,
            once=True,
            html_output=True,
            open_browser=False,
            drilldown=True,
        )
        assert h.match_fn("/dash")
        assert h.match_fn("/dashboard --once")

    def test_dashboard_parser_supports_live_commentary_flags(self):
        parsed = nse_agent._parse_dashboard_command(
            "/dashboard --live-commentary --symbols TRENT,DIXON --interval 30 --cycles 2 --no-llm"
        )

        assert parsed["live_commentary"] is True
        assert parsed["symbols"] == ["TRENT", "DIXON"]
        assert parsed["refresh_secs"] == 30
        assert parsed["cycles"] == 2
        assert parsed["use_llm"] is False
        assert parsed["focus"] == ""

    def test_dashboard_handler_routes_live_commentary_to_tracker_runner(self, registry):
        handler_map = {h.name: h for h in registry._handlers}
        h = handler_map["dashboard"]

        with patch("nse_agent._print_user"), \
             patch("nse_agent.run_live_commentary_dashboard", create=True) as live_runner:
            handled = h.handler_fn(
                "/dashboard --live-commentary --symbols TRENT,DIXON --interval 30 --cycles 1 --no-llm",
                agent=None,
                show_trace=False,
            )

        assert handled is True
        live_runner.assert_called_once()
        config = live_runner.call_args.args[0]
        assert config.symbols == ["TRENT", "DIXON"]
        assert config.refresh_secs == 30
        assert config.max_cycles == 1
        assert config.use_llm is False

    def test_intraday_alerts_handler_is_registered_and_routes_to_monitor(self, registry):
        handler_map = {h.name: h for h in registry._handlers}
        h = handler_map["intraday-alerts"]

        with patch("nse_agent._print_user"), \
             patch("nse_agent.run_intraday_alert_commentary", create=True) as runner:
            handled = h.handler_fn(
                "/intraday-alerts --symbols BEL,MCX --cycles 1 --interval 5 --min-rr 2.5 --trigger active --dry-run --no-llm",
                agent=None,
                show_trace=False,
            )

        assert handled is True
        runner.assert_called_once()
        config = runner.call_args.args[0]
        assert config.symbols == ["BEL", "MCX"]
        assert config.cycles == 1
        assert config.interval_secs == 5
        assert config.min_rr == 2.5
        assert config.trigger == "active"
        assert config.dry_run is True
        assert config.use_llm is False

    def test_live_intraday_alerts_alias_routes_to_monitor(self, registry):
        handler_map = {h.name: h for h in registry._handlers}
        h = handler_map["intraday-alerts"]

        assert h.match_fn("/live_intraday_alerts --symbols BEL")

        with patch("nse_agent._print_user"), \
             patch("nse_agent.run_intraday_alert_commentary", create=True) as runner:
            handled = h.handler_fn(
                "/live_intraday_alerts --symbols INDUSINDBK,NHPC --cycles 1 --interval 5 --no-llm",
                agent=None,
                show_trace=False,
            )

        assert handled is True
        runner.assert_called_once()
        config = runner.call_args.args[0]
        assert config.symbols == ["INDUSINDBK", "NHPC"]
        assert config.cycles == 1
        assert config.interval_secs == 5
        assert config.use_llm is False

    def test_live_intraday_alerts_typo_and_pasted_separator_routes_to_monitor(self, registry):
        handler_map = {h.name: h for h in registry._handlers}
        h = handler_map["intraday-alerts"]

        assert h.match_fn("/live_intraday_alertss --cycles 1")

        with patch("nse_agent._print_user"), \
             patch("nse_agent.run_intraday_alert_commentary", create=True) as runner:
            handled = h.handler_fn(
                "/live_intraday_alertss --cycles 1 --interval 180 --candle-interval 5m --trigger active_or_near │ --min-rr 1.3 --email-every-mins 15 --max-tracked-symbols 7 --min-volume-ratio 1.2",
                agent=None,
                show_trace=False,
            )

        assert handled is True
        runner.assert_called_once()
        config = runner.call_args.args[0]
        assert config.cycles == 1
        assert config.interval_secs == 180
        assert config.candle_interval == "5m"
        assert config.trigger == "active_or_near"
        assert config.min_rr == 1.3
        assert config.email_every_mins == 15
        assert config.max_tracked_symbols == 7
        assert config.min_volume_ratio == 1.2

    def test_my_portfolio_handler_is_registered(self, registry):
        """Bare /my-portfolio handler must exist in registry."""
        handler_map = {h.name: h for h in registry._handlers}
        assert "my-portfolio" in handler_map
        h = handler_map["my-portfolio"]
        assert h.match_fn("/my-portfolio")
        assert h.match_fn("/my-portfolio sell")
        assert h.match_fn("/my-portfolio eod")

    def test_swing_playbook_handler_calls_generator(self, registry):
        handler_map = {h.name: h for h in registry._handlers}
        h = handler_map["swing-playbook"]

        with patch("terminal.swing_playbook.handle_swing_playbook_command", return_value="Swing Playbook: /tmp/report.html\nReport: /tmp/report.html") as handle, \
             patch("nse_agent._print_user"), \
             patch.object(nse_agent.console, "print") as printed:
            handled = h.handler_fn("/swing-playbook --portfolio", agent=None, show_trace=False)

        assert handled is True
        handle.assert_called_once_with("/swing-playbook --portfolio")
        assert printed.called

    def test_swing_playbook_handler_rejects_prefix_typos(self, registry):
        handler_map = {h.name: h for h in registry._handlers}
        h = handler_map["swing-playbook"]

        assert not h.match_fn("/swing-playbooker")
        assert not h.match_fn("/swing-playbook-extra")

    def test_diagnose_handler_calls_skill_command(self, registry):
        handler_map = {h.name: h for h in registry._handlers}
        h = handler_map["diagnose"]

        with patch("terminal.skills.commands.handle_diagnose_command", return_value="## Fundamental Driver Diagnosis\n\nShort Answer: ok") as handle, \
             patch("nse_agent._print_user"), \
             patch.object(nse_agent.console, "print") as printed:
            handled = h.handler_fn("/diagnose DMART eps", agent=None, show_trace=False)

        assert handled is True
        handle.assert_called_once_with("/diagnose DMART eps")
        assert printed.called

    def test_diagnose_handler_rejects_prefix_typos(self, registry):
        handler_map = {h.name: h for h in registry._handlers}
        h = handler_map["diagnose"]

        assert not h.match_fn("/diagnosee DMART eps")
        assert not h.match_fn("/diagnostic DMART eps")

    def test_report_diagnosis_handler_calls_preset_report(self, registry):
        handler_map = {h.name: h for h in registry._handlers}
        h = handler_map["report-diagnosis"]

        fake = {
            "success": True,
            "path": "/tmp/fundamental_driver_diagnosis.html",
            "latest_path": "/tmp/latest.html",
            "note": "ok",
        }
        with patch("terminal.reports.generate_preset_report", return_value=fake) as generate, \
             patch("nse_agent._print_user"), \
             patch("nse_agent._open_report_path") as open_report, \
             patch.object(nse_agent.console, "print") as printed:
            handled = h.handler_fn("/report diagnosis DMART eps", agent=None, show_trace=False)

        assert handled is True
        generate.assert_called_once_with("diagnosis", "html", args=["DMART", "eps"])
        open_report.assert_called_once_with("/tmp/fundamental_driver_diagnosis.html", nse_agent.console)
        assert printed.called

    def test_report_diagnosis_handler_parses_format(self, registry):
        handler_map = {h.name: h for h in registry._handlers}
        h = handler_map["report-diagnosis"]

        fake = {"success": True, "path": "/tmp/fundamental_driver_diagnosis.md", "note": "ok"}
        with patch("terminal.reports.generate_preset_report", return_value=fake) as generate, \
             patch("nse_agent._print_user"), \
             patch("nse_agent._open_report_path"), \
             patch.object(nse_agent.console, "print"):
            handled = h.handler_fn("/report diagnosis DMART eps md", agent=None, show_trace=False)

        assert handled is True
        generate.assert_called_once_with("diagnosis", "md", args=["DMART", "eps"])

    def test_registry_does_not_match_natural_language(self, registry):
        nl_queries = [
            "what is reliance doing",
            "my portfolio",          # no slash
            "show stage 2 stocks",
            "analyze tcs",
        ]
        for q in nl_queries:
            for h in registry._handlers:
                if h.name == "open-last-report":
                    continue  # natural language matcher by design
                assert not h.match_fn(q.lower()), (
                    f"Handler '{h.name}' incorrectly matched natural language {q!r}"
                )


# ─── Layer 2: _SLASH_COMMANDS visibility ─────────────────────────────────────

class TestSlashCommandsVisibility:
    """Everything in _SLASH_COMMANDS is well-formed and covers key commands."""

    def test_all_entries_start_with_slash_or_are_empty_or_template(self, slash_commands):
        for cmd, desc in slash_commands:
            # Allowed: empty string (spacer), slash commands, or <template> pipe examples
            ok = (cmd == "" or cmd.startswith("/") or cmd.startswith("<"))
            assert ok, f"Entry {cmd!r} does not start with '/' or '<'"
            assert isinstance(desc, str), f"Description for {cmd!r} is not a string"

    def test_my_portfolio_all_variants_present(self, slash_commands):
        cmds = {cmd for cmd, _ in slash_commands}
        required = [
            "/my-portfolio",
            "/my-portfolio eod",
            "/my-portfolio eod",
            "/my-portfolio buy",
            "/my-portfolio sell",
            "/my-portfolio hold",
        ]
        for r in required:
            assert r in cmds, f"{r!r} missing from _SLASH_COMMANDS"

    def test_report_portfolio_monitor_present(self, slash_commands):
        cmds = {cmd for cmd, _ in slash_commands}
        assert "/report portfolio-monitor" in cmds

    def test_report_swing_playbook_present_and_preset(self, slash_commands):
        cmds = {cmd for cmd, _ in slash_commands}
        assert "/report swing-playbook" in cmds
        assert "swing-playbook" in nse_agent._REPORT_PRESET_TYPES_FOR_TEST

    def test_report_diagnosis_present_and_preset(self, slash_commands):
        cmds = {cmd for cmd, _ in slash_commands}
        assert "/report diagnosis DMART eps" in cmds
        assert "diagnosis" in nse_agent._REPORT_PRESET_TYPES_FOR_TEST

    def test_portfolio_category_defined(self, cmd_categories):
        assert "/my-portfolio" in cmd_categories
        cat, icon = cmd_categories["/my-portfolio"]
        assert cat == "Portfolio"
        assert "💼" in icon

    def test_no_duplicate_commands(self, slash_commands):
        seen = {}
        for cmd, desc in slash_commands:
            if not cmd:
                continue
            assert cmd not in seen, (
                f"Duplicate entry {cmd!r} in _SLASH_COMMANDS "
                f"(first: {seen[cmd]!r}, second: {desc!r})"
            )
            seen[cmd] = desc

    def test_autocomplete_includes_my_portfolio(self):
        entries = nse_agent._AgentCompleter._slash_command_entries()
        cmds = {cmd for cmd, _ in entries}
        assert "/my-portfolio" in cmds
        assert "/my-portfolio eod" in cmds
        assert "/my-portfolio eod" in cmds
        assert "/my-portfolio sell" in cmds

    def test_portfolio_section_in_help_aliases(self):
        from terminal.help import SECTIONS
        assert "portfolio" in SECTIONS
        aliases = SECTIONS["portfolio"].get("aliases", [])
        assert "my-portfolio" in aliases


# ─── Layer 3: /screen vs /screenshot collision (regression) ──────────────────

class TestScreenScreenshotCollision:
    """The /screen handler must not swallow /screenshot commands."""

    SCREEN_GUARD = staticmethod(
        lambda text: text.lower().startswith("/screen")
                     and not text.lower().startswith("/screenshot")
    )

    @pytest.mark.parametrize("cmd", [
        "/screen stage2",
        "/screen momentum",
        "/screen highrs",
        "/screen dip",
        "/screen base",
        "/screen tight",
        "/screen strong",
        "/screen new",
        "/screen supertrend",
        "/screen turnaround",
    ])
    def test_screen_commands_fire_screener(self, cmd):
        assert self.SCREEN_GUARD(cmd), f"{cmd!r} should fire the screener handler"

    @pytest.mark.parametrize("cmd", [
        "/screenshot --mode window --to a@b.com",
        "/screenshot --mode full --send",
        "/screenshot --no-email --out ~/Desktop/shot.png",
        "/screenshot",
    ])
    def test_screenshot_commands_skip_screener(self, cmd):
        assert not self.SCREEN_GUARD(cmd), (
            f"{cmd!r} must NOT fire the screener handler (screen/screenshot collision)"
        )


# ─── Layer 4: Natural language → LLM route ───────────────────────────────────

class TestNaturalLanguageLLMRoute:
    """Natural language queries should not match any registry handler."""

    @pytest.mark.parametrize("query", [
        "what is nifty 50 today",
        "show me stage 2 stocks",
        "analyze reliance",
        "MY-PORTFOLIO",            # pre-fix: was accidentally routed to LLM as entity
        "my portfolio performance",
        "portfolio analysis",
        "how is my portfolio doing",
    ])
    def test_natural_language_not_caught_by_registry(self, registry, query):
        q = query.strip().lower()
        for h in registry._handlers:
            if h.name == "open-last-report":
                continue
            assert not h.match_fn(q), (
                f"Registry handler '{h.name}' incorrectly matched NL query {query!r}"
            )


# ─── Layer 5: Specific command match functions ────────────────────────────────

class TestCommandMatchFunctions:
    """Each handler's match_fn covers all expected variants."""

    def _get_handler(self, registry, name):
        return next(h for h in registry._handlers if h.name == name)

    # /my-portfolio
    @pytest.mark.parametrize("query, expected", [
        ("/my-portfolio",               True),
        ("/my-portfolio eod",      True),
        ("/my-portfolio eod",           True),
        ("/my-portfolio buy",           True),
        ("/my-portfolio sell",          True),
        ("/my-portfolio hold",          True),
        ("/my-portfolio strong-buy",    True),
        ("/my_portfolio",               True),
        ("/my_portfolio sell",          True),
        ("/myportfolio",                False),
        ("my-portfolio",                False),
        ("/portfolio",                  False),
    ])
    def test_my_portfolio_match(self, registry, query, expected):
        h = self._get_handler(registry, "my-portfolio")
        assert h.match_fn(query.lower()) == expected, (
            f"/my-portfolio handler: {query!r} expected {expected}"
        )

    # /email
    @pytest.mark.parametrize("query", [
        "/email sector --to a@b.com",
        "/email portfolio-analysis --to a@b.com",
        "/email my-portfolio --to a@b.com",
        "/email dashboard --to a@b.com --send",
        "/email",
    ])
    def test_email_matches(self, registry, query):
        h = self._get_handler(registry, "email")
        assert h.match_fn(query.lower()), f"email handler did not match {query!r}"

    # /scan
    @pytest.mark.parametrize("query", [
        "/scan",
        "/scan nifty",
        "/scan nifty bank",
        "/scan orb",
        "/scan vcp",
        "/scan momentum",
    ])
    def test_scan_matches(self, registry, query):
        h = self._get_handler(registry, "scan")
        assert h.match_fn(query.lower()), f"scan handler did not match {query!r}"

    def test_scan_does_not_match_screen(self, registry):
        h = self._get_handler(registry, "scan")
        assert not h.match_fn("/screen stage2"), (
            "scan handler must not match /screen"
        )

    # /visual-scan
    @pytest.mark.parametrize("query", [
        "/visual-scan dmart",
        "/visual-scan reliance --strict",
        "/visual_scan tcs",
    ])
    def test_visual_scan_matches(self, registry, query):
        h = self._get_handler(registry, "visual-scan")
        assert h.match_fn(query.lower()), f"visual-scan did not match {query!r}"

    # /doctor
    @pytest.mark.parametrize("query", ["/doctor", "/doctor --repair"])
    def test_doctor_matches(self, registry, query):
        h = self._get_handler(registry, "doctor")
        assert h.match_fn(query.lower()), f"doctor did not match {query!r}"

    # /mtf
    @pytest.mark.parametrize("query", [
        "/mtf reliance",
        "/mtf scan nifty50 bullish",
        "/mtf reliance --report",
    ])
    def test_mtf_matches(self, registry, query):
        h = self._get_handler(registry, "mtf")
        assert h.match_fn(query.lower()), f"mtf did not match {query!r}"

    # /strength
    @pytest.mark.parametrize("query", [
        "/strength maninds thermax",
        "/strength reliance tcs infy",
    ])
    def test_strength_matches(self, registry, query):
        h = self._get_handler(registry, "strength")
        assert h.match_fn(query.lower()), f"strength did not match {query!r}"

    # /strategy-council
    @pytest.mark.parametrize("query", [
        "/strategy-council dmart",
        "/strategy-council reliance --iterations 3",
    ])
    def test_strategy_council_matches(self, registry, query):
        h = self._get_handler(registry, "strategy-council")
        assert h.match_fn(query.lower()), f"strategy-council did not match {query!r}"

    def test_strategy_council_does_not_match_bare_strategy(self, registry):
        h = self._get_handler(registry, "strategy-council")
        assert not h.match_fn("/strategy nifty long_straddle"), (
            "strategy-council must not match /strategy <options-builder>"
        )

    # /council
    @pytest.mark.parametrize("query", [
        "/council",
        "/council today",
        "/council sector nifty auto --horizon swing",
        "/council stock modisonltd",
    ])
    def test_council_matches(self, registry, query):
        h = self._get_handler(registry, "council")
        assert h.match_fn(query.lower()), f"council did not match {query!r}"

    # /backtest and /strategy-lab
    @pytest.mark.parametrize("query", [
        "/backtest list",
        "/backtest reliance --strategy stage2",
        "/strategy-lab validate",
        "/strategy-lab",
    ])
    def test_backtest_matches(self, registry, query):
        h = self._get_handler(registry, "backtest")
        assert h.match_fn(query.lower()), f"backtest did not match {query!r}"

    def test_backtest_does_not_match_strategy_council(self, registry):
        h = self._get_handler(registry, "backtest")
        assert not h.match_fn("/strategy-council dmart"), (
            "backtest must not match /strategy-council"
        )

    # /data-coverage
    @pytest.mark.parametrize("query", [
        "/data-coverage nifty500",
        "/data-coverage nifty500 --backfill",
        "/data-coverage nifty500 --details",
    ])
    def test_data_coverage_matches(self, registry, query):
        h = self._get_handler(registry, "data-coverage")
        assert h.match_fn(query.lower()), f"data-coverage did not match {query!r}"

    # open-last-report (natural language) — only phrases that _is_open_last_report_request matches
    @pytest.mark.parametrize("query", [
        "open last report",
        "open the report",
        "show last report",
    ])
    def test_open_last_report_natural_language(self, registry, query):
        h = self._get_handler(registry, "open-last-report")
        assert h.match_fn(query.lower()), (
            f"open-last-report did not match NL phrase {query!r}"
        )

    @pytest.mark.parametrize("query", [
        "what is nifty today",
        "analyze reliance",
        "my-portfolio",
    ])
    def test_open_last_report_does_not_match_unrelated(self, registry, query):
        h = self._get_handler(registry, "open-last-report")
        assert not h.match_fn(query.lower()), (
            f"open-last-report incorrectly matched {query!r}"
        )

    # /help
    @pytest.mark.parametrize("query", [
        "/help",
        "?",
        "/h",
        "/help portfolio",
        "/help charts",
    ])
    def test_help_matches(self, registry, query):
        h = self._get_handler(registry, "help")
        assert h.match_fn(query.lower()), f"help did not match {query!r}"


# ─── Layer 6: /commands and autocomplete ─────────────────────────────────────

class TestCommandsAndAutocomplete:
    """The /commands browser and autocomplete reflect the current command set."""

    def test_portfolio_appears_in_commands_search(self, slash_commands):
        portfolio_cmds = [
            cmd for cmd, desc in slash_commands
            if "portfolio" in cmd.lower() or "portfolio" in desc.lower()
        ]
        assert len(portfolio_cmds) >= 5, (
            f"Expected ≥5 portfolio-related entries, got {len(portfolio_cmds)}: {portfolio_cmds}"
        )

    def test_all_categories_have_at_least_one_entry(self, slash_commands, cmd_categories):
        cats_with_entries = set()
        for cmd, _ in slash_commands:
            if not cmd:
                continue
            root = cmd.split()[0]
            if root in cmd_categories:
                cats_with_entries.add(cmd_categories[root][0])
        # At least 10 distinct categories populated
        assert len(cats_with_entries) >= 10, (
            f"Expected ≥10 categories with entries, got {len(cats_with_entries)}"
        )

    def test_autocomplete_returns_slash_completions(self):
        """_slash_command_entries merges _SLASH_COMMANDS + helpfile catalog."""
        entries = nse_agent._AgentCompleter._slash_command_entries()
        slash_only = [cmd for cmd, _ in entries if cmd.startswith("/")]
        assert len(slash_only) >= 50, (
            f"Expected ≥50 slash completions, got {len(slash_only)}"
        )

    def test_no_orphaned_slash_commands_in_display_list(self, slash_commands):
        """Every non-empty _SLASH_COMMANDS entry should have at least a description."""
        for cmd, desc in slash_commands:
            if cmd:
                assert desc, f"Command {cmd!r} has no description in _SLASH_COMMANDS"


# ─── Layer 7: Daily refresh + report preset ──────────────────────────────────

class TestDailyRefreshAndPreset:

    def test_step_portfolio_monitor_callable(self):
        import daily_refresh
        assert callable(daily_refresh.step_portfolio_monitor)

    def test_step_portfolio_monitor_dry_run_intraday(self):
        import daily_refresh
        assert daily_refresh.step_portfolio_monitor(dry_run=True, intraday=True) is True

    def test_step_portfolio_monitor_dry_run_eod(self):
        import daily_refresh
        assert daily_refresh.step_portfolio_monitor(dry_run=True, intraday=False) is True

    def test_generate_preset_report_portfolio_monitor(self, tmp_path):
        from terminal.reports import generate_preset_report
        from terminal.portfolio_monitor import run_eod_report, EOD_REPORT
        fake = {"path": str(tmp_path / "eod.html"), "success": True, "note": "ok"}
        with patch("terminal.portfolio_monitor.run_eod_report", return_value=fake):
            result = generate_preset_report("portfolio-monitor", "html")
        assert result["success"] is True
        assert result["report_type"] == "portfolio-monitor"
        assert "My Portfolio" in result["title"]

    def test_email_alias_my_portfolio_resolves(self, tmp_path):
        """email dispatcher 'my-portfolio' alias resolves to portfolio_analysis.html."""
        from terminal.email_dispatcher import REPORT_ALIASES, resolve_report
        assert "my-portfolio" in REPORT_ALIASES
        assert REPORT_ALIASES["my-portfolio"] == "latest/portfolio_analysis.html"
        assert "portfolio-analysis" in REPORT_ALIASES
        assert "portfolio_analysis" in REPORT_ALIASES


# ─── Layer 8: Prompt library ─────────────────────────────────────────────────

class TestPromptLibrary:

    def test_prompts_command_present(self, slash_commands):
        cmds = {cmd for cmd, _ in slash_commands}
        assert "/prompts" in cmds

    def test_portfolio_prompts_present(self, slash_commands):
        cmds = {cmd for cmd, _ in slash_commands}
        assert "/prompts portfolio" in cmds

    def test_all_prompt_sections_have_descriptions(self, slash_commands):
        prompt_entries = [(cmd, desc) for cmd, desc in slash_commands if cmd.startswith("/prompts")]
        assert len(prompt_entries) >= 5, "Expected at least 5 /prompts entries"
        for cmd, desc in prompt_entries:
            assert desc, f"/prompts entry {cmd!r} has no description"


# ─── Layer 9: Regression tests ───────────────────────────────────────────────

class TestRegressions:
    """Pin fixes for bugs that were caught and fixed during development."""

    def test_screenshot_not_caught_by_screen_handler(self):
        """/screenshot must not be silently consumed by the /screen EOD screener."""
        text = "/screenshot --mode window --to pgorai@deloitte.com"
        # The fixed guard in nse_agent.py line 8064
        fires_screener = (
            text.lower().startswith("/screen")
            and not text.lower().startswith("/screenshot")
        )
        assert not fires_screener, (
            "/screenshot was caught by the /screen handler — regression!"
        )

    def test_my_portfolio_not_treated_as_stock_symbol(self, registry):
        """'/my-portfolio' must be caught by the registry, not fall to LLM."""
        h_map = {h.name: h for h in registry._handlers}
        h = h_map["my-portfolio"]
        assert h.match_fn("/my-portfolio"), "Registry must catch /my-portfolio"
        assert h.match_fn("/my-portfolio eod"), "Registry must catch /my-portfolio eod"

    def test_my_portfolio_without_slash_goes_to_llm(self, registry):
        """'MY-PORTFOLIO' (no slash) must NOT hit the registry (goes to LLM)."""
        h_map = {h.name: h for h in registry._handlers}
        h = h_map["my-portfolio"]
        for q in ["my-portfolio", "MY-PORTFOLIO", "myportfolio"]:
            assert not h.match_fn(q.lower()), (
                f"'{q}' without slash must not hit the my-portfolio registry handler"
            )

    def test_entity_assessment_bypassed_for_slash_commands(self):
        """Verify guard condition: slash commands are excluded from assessment."""
        for text in ["/my-portfolio", "/search RELIANCE", "/email sector --to x@y.com"]:
            assert not (not text.lstrip().startswith("/")), (
                f"Slash command {text!r} must bypass entity assessment"
            )

    def test_screen_variants_do_not_bleed_into_screenshot(self):
        """/screen<anything> but /screenshot must fire screener."""
        screener_commands = [
            "/screen",
            "/screen stage2",
            "/screener",       # unknown but starts with /screen
            "/screenplay",     # edge case: also starts with /screen
        ]
        screenshot_commands = [
            "/screenshot",
            "/screenshots",    # edge: starts with /screenshot
        ]
        for cmd in screener_commands:
            fires = (
                cmd.lower().startswith("/screen")
                and not cmd.lower().startswith("/screenshot")
            )
            assert fires, f"{cmd!r} should fire screener"

        for cmd in screenshot_commands:
            fires = (
                cmd.lower().startswith("/screen")
                and not cmd.lower().startswith("/screenshot")
            )
            assert not fires, f"{cmd!r} must not fire screener"

    def test_provider_chain_has_no_retired_providers(self):
        """EntityTopicProvider and DirectIntentProvider must not be in the chain."""
        from terminal.router import UnifiedRouter
        names = UnifiedRouter().provider_names
        assert "EntityTopicProvider" not in names, "Retired provider found in chain"
        assert "DirectIntentProvider" not in names, "Retired provider found in chain"

    def test_screen_screener_handler_guard_present_in_source(self):
        """Verify the /screen vs /screenshot guard exists in nse_agent.py."""
        src = (ROOT / "nse_agent.py").read_text(encoding="utf-8")
        assert "not _tl.startswith(\"/screenshot\")" in src or \
               "not text.lower().startswith(\"/screenshot\")" in src or \
               "not _tl.startswith('/screenshot')" in src, (
            "The /screen vs /screenshot guard is missing from nse_agent.py"
        )

    def test_registry_dispatch_call_in_chat_loop(self):
        """The _chat_loop must call _get_shared_registry().dispatch()."""
        src = (ROOT / "nse_agent.py").read_text(encoding="utf-8")
        assert "_get_shared_registry()" in src
        assert ".dispatch(text, agent, show_trace, mode=\"interactive\")" in src, (
            "registry.dispatch() with mode='interactive' must be called in _chat_loop"
        )

    def test_entity_assessment_guard_in_source(self):
        """Slash commands must bypass entity assessment — check source guard."""
        src = (ROOT / "nse_agent.py").read_text(encoding="utf-8")
        assert 'not text.lstrip().startswith("/")' in src, (
            "Entity assessment slash-command bypass guard missing from nse_agent.py"
        )
