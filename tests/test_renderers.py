"""Unit tests for terminal.renderers package.

Each renderer module is exercised in isolation using lightweight fixture dicts —
no agent, no network, no database.
"""
import unittest

from terminal.renderers import render
from terminal.renderers._base import _get, _source_trail_lines, FOOTER, trail_and_footer
from terminal.renderers.narrator import (
    NARRATION_INTENTS,
    attach_narrative,
    build_final_answer,
    build_narrative,
)
from terminal.renderers import results_feed as _rf
from terminal.agent import _synthesize_and_narrate


# ── helpers ───────────────────────────────────────────────────────────────────

def _tr(tool: str, **result_kw) -> dict:
    """Build a minimal tool-result dict."""
    return {"tool": tool, "result": result_kw}


def _ok(out: str) -> None:
    """Assert output is non-empty and contains the footer sentinel."""
    assert out.strip(), "render returned empty string"
    assert "Not investment advice" in out or "━━━" in out, "footer missing"


# ── _base ─────────────────────────────────────────────────────────────────────

class TestBase(unittest.TestCase):

    def test_get_returns_matching_result(self):
        trs = [_tr("tool_a", val=1), _tr("tool_b", val=2)]
        self.assertEqual(_get(trs, "tool_b"), {"val": 2})

    def test_get_returns_none_for_missing(self):
        self.assertIsNone(_get([_tr("tool_a", x=1)], "tool_z"))

    def test_get_returns_none_for_non_dict_result(self):
        trs = [{"tool": "tool_a", "result": "plain string"}]
        self.assertIsNone(_get(trs, "tool_a"))

    def test_source_trail_ok(self):
        trs = [_tr("my_tool", data=42)]
        lines = _source_trail_lines(trs)
        self.assertTrue(any("my_tool" in l for l in lines))
        self.assertTrue(any("ok" in l for l in lines))

    def test_source_trail_error(self):
        trs = [{"tool": "bad_tool", "result": {"error": "timeout"}}]
        lines = _source_trail_lines(trs)
        self.assertTrue(any("ERROR" in l for l in lines))

    def test_trail_and_footer(self):
        out = trail_and_footer([_tr("t", x=1)])
        self.assertIn("SOURCE TRAIL", out)
        self.assertIn("Not investment advice", out)


# ── narrator ──────────────────────────────────────────────────────────────────

class TestNarrator(unittest.TestCase):

    def test_attach_narrative_inserts_before_source_trail(self):
        body = "TABLES\n▶ SOURCE TRAIL\n  tool: ok\n━━━ Not investment advice"
        result = attach_narrative(body, "Market is bullish.")
        self.assertIn("INTERPRETATION", result)
        idx_interp = result.index("INTERPRETATION")
        idx_trail  = result.index("SOURCE TRAIL")
        self.assertLess(idx_interp, idx_trail)

    def test_attach_narrative_appends_when_no_trail(self):
        body = "TABLES ONLY"
        result = attach_narrative(body, "Commentary here.")
        self.assertIn("Commentary here.", result)

    def test_attach_narrative_noop_on_empty(self):
        body = "TABLES\n▶ SOURCE TRAIL"
        self.assertEqual(attach_narrative(body, ""), body)

    def test_build_narrative_skips_unlisted_intents(self):
        assert "greeting" not in NARRATION_INTENTS
        result = build_narrative("greeting", "hi", [], "structured output", backend=None)
        self.assertEqual(result, "")

    def test_build_narrative_skips_when_backend_none(self):
        result = build_narrative("stock_brief", "RELIANCE", [], "output", backend=None)
        self.assertEqual(result, "")

    def test_build_narrative_generates_for_skill_store(self):
        class Backend:
            def chat(self, messages, tools=None, max_tokens=None):
                assert max_tokens == 160
                return {"content": "The selected workflow produced usable evidence."}

        result = build_narrative(
            "skill_store",
            "find market swing candidates",
            [{"tool": "skill_store.execute", "result": {"passed": True, "evidence": {"scan": {"row_count": 3}}}}],
            "▶ SKILL STORE\n  Execution: passed",
            backend=Backend(),
        )

        self.assertEqual(result, "The selected workflow produced usable evidence.")

    def test_build_final_answer_uses_query_and_structured_evidence(self):
        seen = {}

        class Backend:
            def chat(self, messages, tools=None, max_tokens=None):
                seen["messages"] = messages
                seen["max_tokens"] = max_tokens
                return {"content": "BAJAJCON sales and EPS growth are accelerating from the rendered evidence."}

        result = build_final_answer(
            "stock_brief",
            "analyze the sales and EPS growth of BAJAJCON",
            [{"tool": "scrape_screener_in", "result": {"symbol": "BAJAJCON"}}],
            "▶ SALES & EPS GROWTH\n  Quarterly Sales YoY: +30.8%\n  Quarterly EPS YoY: +115.5%",
            backend=Backend(),
        )

        self.assertIn("BAJAJCON sales and EPS growth", result)
        self.assertEqual(seen["max_tokens"], 700)
        prompt_text = "\n".join(m["content"] for m in seen["messages"])
        self.assertIn("analyze the sales and EPS growth of BAJAJCON", prompt_text)
        self.assertIn("Quarterly Sales YoY: +30.8%", prompt_text)

    def test_build_final_answer_prompt_requires_structured_answer_sections(self):
        seen = {}

        class Backend:
            def chat(self, messages, tools=None, max_tokens=None):
                seen["system"] = messages[0]["content"]
                return {"content": "Direct answer."}

        build_final_answer(
            "stock_brief",
            "analyze BAJAJCON growth",
            [],
            "▶ SNAPSHOT\n  Price: ₹582.20",
            backend=Backend(),
        )

        system_prompt = seen["system"]
        self.assertIn("Start with a terminal title line", system_prompt)
        self.assertIn("━━━", system_prompt)
        self.assertIn("▶ CURRENT OVERVIEW", system_prompt)
        self.assertIn("▶ FINANCIAL PERFORMANCE", system_prompt)
        self.assertIn("▶ TECHNICAL AND SECTOR CONTEXT", system_prompt)
        self.assertIn("▶ KEY CONSIDERATIONS", system_prompt)
        self.assertIn("▶ BOTTOM LINE", system_prompt)
        self.assertIn("Avoid markdown heading syntax", system_prompt)
        self.assertIn("Use one bullet level", system_prompt)
        self.assertIn("Always include all five section headers", system_prompt)

    def test_build_final_answer_strips_footer_and_source_trail_from_llm_text(self):
        class Backend:
            def chat(self, messages, tools=None, max_tokens=None):
                return {
                    "content": (
                        "Direct answer.\n\n"
                        "▶ SOURCE TRAIL\n  scrape_screener_in: ok\n\n"
                        "━━━ Not investment advice. For research and learning only. ━━━"
                    )
                }

        result = build_final_answer("stock_brief", "query", [], "structured", backend=Backend())

        self.assertEqual(result, "Direct answer.")

    def test_build_final_answer_normalizes_markdown_headings_to_terminal_sections(self):
        class Backend:
            def chat(self, messages, tools=None, max_tokens=None):
                return {
                    "content": (
                        "### BAJAJCON — Growth Story\n\n"
                        "#### Current Overview\n"
                        "- Price: ₹582.20\n\n"
                        "#### Financial Performance\n"
                        "- Sales YoY: +30.8%\n\n"
                        "#### Key Considerations\n"
                        "- Valuation is high.\n"
                    )
                }

        result = build_final_answer("stock_brief", "query", [], "structured", backend=Backend())

        self.assertIn("━━━ BAJAJCON — Growth Story ━━━", result)
        self.assertIn("▶ CURRENT OVERVIEW", result)
        self.assertIn("▶ FINANCIAL PERFORMANCE", result)
        self.assertIn("▶ KEY CONSIDERATIONS", result)
        self.assertNotIn("###", result)
        self.assertNotIn("####", result)

    def test_build_final_answer_indents_bullet_continuation_lines(self):
        class Backend:
            def chat(self, messages, tools=None, max_tokens=None):
                return {
                    "content": (
                        "━━━ BAJAJCON — Direct Answer ━━━\n\n"
                        "▶ BOTTOM LINE\n"
                        "  - Strong recent sales and EPS growth\n"
                        "both quarterly and annually."
                    )
                }

        result = build_final_answer("stock_brief", "query", [], "structured", backend=Backend())

        self.assertIn("  - Strong recent sales and EPS growth\n    both quarterly", result)
        self.assertNotIn("\nboth quarterly", result)

    def test_build_final_answer_indents_section_paragraph_lines(self):
        class Backend:
            def chat(self, messages, tools=None, max_tokens=None):
                return {
                    "content": (
                        "━━━ BAJAJCON — Direct Answer ━━━\n\n"
                        "▶ BOTTOM LINE\n"
                        "BAJAJCON shows strong short-term growth with constructive momentum in the market although valuation needs attention\n"
                        "although long-term sales growth is weak."
                    )
                }

        result = build_final_answer("stock_brief", "query", [], "structured", backend=Backend())

        self.assertIn("▶ BOTTOM LINE\n  BAJAJCON shows strong short-term growth", result)
        self.assertIn("\n  the market although valuation needs attention", result)
        self.assertIn("\n  although long-term", result)
        self.assertNotIn("\nBAJAJCON shows", result)
        self.assertNotIn("\nalthough long-term", result)

    def test_build_narrative_drops_unsupported_rs_percentile_claim(self):
        class Backend:
            def chat(self, messages, tools=None, max_tokens=None):
                return {"content": "Relative strength is averaging at a low percentile, so risk is elevated."}

        result = build_narrative(
            "market_overview",
            "show current market breadth and RS percentile distribution",
            [{"tool": "get_market_breadth", "result": {"avg_rs_pct": 12.0}}],
            "▶ DB UNIVERSE CONTEXT\n  Universe avg RS: +12.0%",
            backend=Backend(),
        )

        self.assertEqual(result, "")

    def test_narration_intents_are_frozenset(self):
        self.assertIsInstance(NARRATION_INTENTS, frozenset)
        self.assertIn("stock_brief", NARRATION_INTENTS)
        self.assertIn("market_dashboard", NARRATION_INTENTS)
        self.assertIn("skill_store", NARRATION_INTENTS)

    def test_market_intelligence_intents_are_narrated(self):
        expected = {
            "market_swing_candidates",
            "quality_breakouts",
            "symbol_quick_analysis",
            "stock_comparison",
            "portfolio_review",
            "market_knowledge",
            "entity_topic_command",
        }

        self.assertTrue(expected.issubset(NARRATION_INTENTS))


# ── results_feed helpers ──────────────────────────────────────────────────────

class TestResultsFeedHelpers(unittest.TestCase):

    def test_qtr_labels(self):
        cases = [
            ("First Quarter", "Q1"),
            ("Second Quarter", "Q2"),
            ("Third Quarter", "Q3"),
            ("Fourth Quarter", "Q4"),
            ("Annual Results", "Q4"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(_rf._qtr(raw), expected)

    def test_fy_dash_format(self):
        self.assertEqual(_rf._fy("2024-25"), "FY25")
        self.assertEqual(_rf._fy("2023-24"), "FY24")

    def test_fy_indian_date_post_april(self):
        # April is month 4 → FY starts in April → fy_yr = yr + 1
        self.assertEqual(_rf._fy("01-Apr-2024"), "FY25")
        self.assertEqual(_rf._fy("15-Sep-2024"), "FY25")

    def test_fy_indian_date_pre_april(self):
        # January–March is before the FY start → fy_yr = yr
        self.assertEqual(_rf._fy("31-Mar-2025"), "FY25")

    def test_aud_labels(self):
        self.assertEqual(_rf._aud("Audited"), "A")
        self.assertEqual(_rf._aud("Un-Audited"), "UA")
        self.assertEqual(_rf._aud("UnAudited"), "UA")

    def test_cons_labels(self):
        self.assertEqual(_rf._cons("Consolidated"), "C")
        self.assertEqual(_rf._cons("Non-Consolidated"), "NC")
        self.assertEqual(_rf._cons("NonConsolidated"), "NC")


# ── results_feed renderer ─────────────────────────────────────────────────────

_FEED_ROW = {
    "symbol": "RELIANCE",
    "company": "Reliance Industries Ltd",
    "period": "Third Quarter",
    "financial_year": "2024-25",
    "filing_date": "2025-01-16",
    "audited": "Un-Audited",
    "consolidated": "Consolidated",
}

_FEED_RESULT = {
    "results": [_FEED_ROW],
    "days_back": 7,
    "source": "NSE",
    "total_available": 42,
    "total_in_window": 1,
}

_FORTHCOMING_ROW = {
    "date": "2025-04-20",
    "symbol": "TCS",
    "company": "Tata Consultancy Services Ltd",
    "description": "Board meeting for Q4 FY25",
}

_FORTHCOMING_RESULT = {
    "results": [_FORTHCOMING_ROW],
    "days_ahead": 14,
    "source": "NSE",
    "total_available": 30,
    "total_in_window": 1,
}


class TestResultsFeedRenderer(unittest.TestCase):

    def setUp(self):
        self.trs_feed = [{"tool": "get_latest_results_feed", "result": _FEED_RESULT}]
        self.trs_forthcoming = [{"tool": "get_forthcoming_results", "result": _FORTHCOMING_RESULT}]

    def test_feed_contains_symbol(self):
        out = _rf.render_results_feed(self.trs_feed)
        self.assertIn("RELIANCE", out)

    def test_feed_abbreviates_qtr(self):
        out = _rf.render_results_feed(self.trs_feed)
        self.assertIn("Q3", out)
        self.assertNotIn("Third Quarter", out)

    def test_feed_abbreviates_fy(self):
        out = _rf.render_results_feed(self.trs_feed)
        self.assertIn("FY25", out)

    def test_feed_abbreviates_audited(self):
        out = _rf.render_results_feed(self.trs_feed)
        self.assertIn("UA", out)

    def test_feed_abbreviates_consolidated(self):
        out = _rf.render_results_feed(self.trs_feed)
        self.assertIn("C", out)

    def test_feed_has_footer(self):
        out = _rf.render_results_feed(self.trs_feed)
        _ok(out)

    def test_feed_empty_rows(self):
        trs = [{"tool": "get_latest_results_feed", "result": {"results": [], "days_back": 7}}]
        out = _rf.render_results_feed(trs)
        self.assertIn("No results filings found", out)

    def test_forthcoming_contains_symbol(self):
        out = _rf.render_forthcoming(self.trs_forthcoming)
        self.assertIn("TCS", out)

    def test_forthcoming_has_date(self):
        out = _rf.render_forthcoming(self.trs_forthcoming)
        self.assertIn("2025-04-20", out)

    def test_forthcoming_has_footer(self):
        out = _rf.render_forthcoming(self.trs_forthcoming)
        _ok(out)

    def test_forthcoming_empty_rows(self):
        trs = [{"tool": "get_forthcoming_results", "result": {"results": [], "days_ahead": 14}}]
        out = _rf.render_forthcoming(trs)
        self.assertIn("No forthcoming results", out)


# ── misc renderers ────────────────────────────────────────────────────────────

class TestMiscRenderer(unittest.TestCase):

    def test_greeting(self):
        out = render("greeting", [])
        self.assertIn("Agent Adda", out)

    def test_greeting_has_footer(self):
        _ok(render("greeting", []))

    def test_placeholder_symbol_request(self):
        out = render("placeholder_symbol_request", [_tr("resolve_symbol", error="no match")])
        self.assertIn("NSE SYMBOL", out)
        _ok(out)

    def test_document_link_help(self):
        out = render("document_link_help", [])
        self.assertIn("DOCUMENT LINK", out)
        _ok(out)

    def test_visual_scan(self):
        trs = [_tr("run_visual_scan", symbol="NIFTY 50", summary="Bullish pattern.")]
        out = render("visual_scan", trs)
        self.assertIn("NIFTY 50", out)
        _ok(out)


# ── report renderer ───────────────────────────────────────────────────────────

class TestReportRenderer(unittest.TestCase):

    def test_report_lookup_basic(self):
        trs = [_tr("get_latest_report", title="Sector Rotation", path="/reports/latest/sector_rotation.md")]
        out = render("report_lookup", trs)
        _ok(out)


# ── fno renderer ──────────────────────────────────────────────────────────────

_FNO_OVERVIEW = {
    "symbol": "NIFTY",
    "pcr": 1.12,
    "max_pain": 22500,
    "future_price": 22550.5,
    "spot_price": 22530.0,
    "basis": 20.5,
    "strategy_recommendation": "Sell calls above 22800",
    "ce_top_oi": [{"strike": 22800, "oi": 500000, "chg_oi": 12000}],
    "pe_top_oi": [{"strike": 22200, "oi": 450000, "chg_oi": -5000}],
}


class TestFnoRenderer(unittest.TestCase):

    def test_fno_overview_symbol(self):
        trs = [_tr("get_fno_overview", **_FNO_OVERVIEW)]
        out = render("fno_overview", trs)
        self.assertIn("NIFTY", out)

    def test_fno_overview_pcr(self):
        trs = [_tr("get_fno_overview", **_FNO_OVERVIEW)]
        out = render("fno_overview", trs)
        self.assertIn("1.12", out)

    def test_fno_overview_footer(self):
        trs = [_tr("get_fno_overview", **_FNO_OVERVIEW)]
        _ok(render("fno_overview", trs))

    def test_fno_overview_no_data_fallback(self):
        out = render("fno_overview", [])
        _ok(out)


# ── market dashboard ──────────────────────────────────────────────────────────

_MARKET_SNAP = {
    "indices": [
        {"symbol": "NIFTY 50", "last": 22530.0, "change_pct": -0.45},
        {"symbol": "NIFTY BANK", "last": 48200.0, "change_pct": 0.12},
    ],
    "breadth": {"advances": 900, "declines": 600, "unchanged": 50},
}


class TestMarketRenderer(unittest.TestCase):

    def test_market_dashboard_indices(self):
        trs = [_tr("get_market_snapshot", **_MARKET_SNAP)]
        out = render("market_dashboard", trs)
        _ok(out)

    def test_morning_briefing_no_crash(self):
        trs = [_tr("get_morning_briefing", summary="Global cues negative.", key_themes=[])]
        out = render("startup_morning_briefing", trs)
        _ok(out)


# ── dispatcher fallback ───────────────────────────────────────────────────────

class TestDispatcher(unittest.TestCase):

    def test_unknown_intent_falls_through_to_stock_brief(self):
        # stock_brief.render() should not raise for an unknown intent
        trs = [_tr("resolve_symbol", symbol="RELIANCE", name="Reliance Industries")]
        out = render("unknown_intent_xyz", trs)
        self.assertIsInstance(out, str)

    def test_stock_brief_does_not_suggest_symbol_when_resolution_succeeded(self):
        trs = [
            _tr("resolve_symbol", symbol="CHENNPETRO", query="CHENNPETRO", candidates=["CHENNPETRO"]),
            _tr("scrape_screener_in", error="network unavailable"),
        ]
        out = render("stock_brief", trs)

        self.assertIn("MISSING EVIDENCE", out)
        self.assertNotIn("Symbol not found", out)
        self.assertNotIn("Did you mean", out)

    def test_stock_brief_renders_pg_and_latest_results_fundamental_evidence(self):
        trs = [
            _tr("resolve_symbol", symbol="DMART"),
            _tr("get_symbol_snapshot", symbol="DMART", price=4000, stage="STAGE_2"),
            _tr(
                "get_cached_financials",
                symbol="DMART",
                section_counts={"quarterly": 1, "annual": 1, "balance_sheet": 0, "cash_flow": 0},
                quarterly=[{"period": "Mar 2026", "revenue": 14000, "pat": 800, "eps": 12.3}],
                annual=[{"period": "FY26", "sales": 52000, "net_profit": 3000}],
            ),
            _tr("scrape_screener_in", error="network unavailable"),
            _tr(
                "get_latest_results",
                symbol="DMART",
                status="ok",
                facts={
                    "revenue": {"value": "14,000", "period": "Mar 2026", "source": "nse_filing"},
                    "pat": {"value": "800", "period": "Mar 2026", "source": "nse_filing"},
                },
                source_trail={"discover_financial_filings": "ok", "search_nse_announcements": "ok"},
                summary="Latest result confirms revenue and PAT.",
            ),
        ]
        out = render("stock_brief", trs)

        self.assertIn("FUNDAMENTAL EVIDENCE", out)
        self.assertIn("PG financial cache", out)
        self.assertIn("Mar 2026", out)
        self.assertIn("LATEST RESULTS", out)
        self.assertIn("Revenue", out)
        self.assertIn("PAT", out)

    def test_stock_brief_computes_sales_and_eps_growth_from_screener_tables(self):
        trs = [
            _tr("resolve_symbol", symbol="BAJAJCON"),
            _tr(
                "scrape_screener_in",
                symbol="BAJAJCON",
                quarterly={
                    "_headers": ["Dec 2024", "Mar 2025", "Jun 2025", "Sep 2025", "Dec 2025", "Mar 2026"],
                    "Sales+": ["234", "250", "267", "265", "306", "327"],
                    "EPS in Rs": ["1.85", "2.26", "2.77", "3.24", "3.55", "4.87"],
                },
                annual_pl={
                    "_headers": ["Mar 2022", "Mar 2023", "Mar 2024", "Mar 2025", "Mar 2026"],
                    "Sales+": ["880", "961", "984", "965", "1,165"],
                    "EPS in Rs": ["11.50", "9.63", "10.88", "9.14", "14.56"],
                },
            ),
        ]

        out = render("stock_brief", trs)

        self.assertIn("SALES & EPS GROWTH", out)
        self.assertIn("Quarterly Sales YoY: +30.8%", out)
        self.assertIn("Quarterly EPS YoY: +115.5%", out)
        self.assertIn("Quarterly Sales QoQ: +6.9%", out)
        self.assertIn("Quarterly EPS QoQ: +37.2%", out)
        self.assertIn("Annual Sales YoY: +20.7%", out)
        self.assertIn("Annual EPS YoY: +59.3%", out)

    def test_synthesize_prefers_llm_final_answer_before_evidence(self):
        class Backend:
            def chat(self, messages, tools=None, max_tokens=None):
                return {
                    "content": (
                        "━━━ BAJAJCON — Direct Answer ━━━\n\n"
                        "▶ CURRENT OVERVIEW\n"
                        "  - BAJAJCON direct growth answer from the final synthesizer."
                    )
                }

        trs = [
            _tr("resolve_symbol", symbol="BAJAJCON"),
            _tr(
                "scrape_screener_in",
                symbol="BAJAJCON",
                quarterly={
                    "_headers": ["Dec 2024", "Mar 2025", "Jun 2025", "Sep 2025", "Dec 2025", "Mar 2026"],
                    "Sales+": ["234", "250", "267", "265", "306", "327"],
                    "EPS in Rs": ["1.85", "2.26", "2.77", "3.24", "3.55", "4.87"],
                },
            ),
        ]

        out = _synthesize_and_narrate(
            "stock_brief",
            "analyze the sales and EPS growth of BAJAJCON",
            trs,
            Backend(),
        )

        self.assertIn("▶ ANSWER", out)
        self.assertLess(out.index("BAJAJCON direct growth answer"), out.index("▶ QUARTERLY RESULTS"))
        self.assertIn("\n  ━━━ BAJAJCON — Direct Answer ━━━", out)
        self.assertIn("\n  ▶ CURRENT OVERVIEW", out)
        self.assertNotIn("\n▶ CURRENT OVERVIEW", out)
        self.assertIn("▶ SALES & EPS GROWTH", out)

    def test_render_always_returns_str(self):
        # All registered intents must return a string
        intents = [
            "greeting", "visual_scan", "placeholder_symbol_request",
            "document_link_help", "results_feed", "forthcoming_results",
            "fno_overview", "market_dashboard", "startup_morning_briefing",
        ]
        for intent in intents:
            with self.subTest(intent=intent):
                out = render(intent, [])
                self.assertIsInstance(out, str)


if __name__ == "__main__":
    unittest.main()
