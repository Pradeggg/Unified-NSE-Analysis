"""Live agent scenario runner.

Drives the real Agent() against a categorised list of scenarios with the
configured OpenAI backend + PostgreSQL + NSE network. Grades each scenario
on objective invariants only (no LLM-as-judge):

    * trail_contains:     tool X must appear in the source trail
    * trail_not_contains: tool X must NOT appear in the source trail
    * answer_contains:    substring must appear in rendered answer
    * answer_not_contains substring must NOT appear in rendered answer
    * no_exception:       Agent.query() must not raise

Output: a Markdown report at reports/scenarios/live_scenarios_<ts>.md
(PASS/FAIL counts, per-bucket summary, full failure list with reasons).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Make sure the repo root is on sys.path when invoked as a script.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Force assessment LLM tier OFF for these runs — we're testing the main
# router. Subsequent toggling is per-scenario if needed.
os.environ.setdefault("ASSESSMENT_LLM_ENABLED", "1")


@dataclass
class Scenario:
    id: str
    bucket: str
    query: str
    setup_queries: list[str] = field(default_factory=list)
    asserts: list[tuple] = field(default_factory=list)
    description: str = ""


@dataclass
class Result:
    scenario: Scenario
    passed: bool
    failures: list[str]
    duration_s: float
    answer_excerpt: str
    tool_trail: list[str]
    exception: str | None = None


# ---------------------------------------------------------------------------
# Scenario definitions — 200 cases across 9 buckets
# ---------------------------------------------------------------------------


def _bucket_a_index_routing() -> list[Scenario]:
    """30 cases: NIFTY index analysis must route to get_index_snapshot,
    must NOT raise SYMBOL VALIDATION FAILED on the index component
    words (SMALLCAP, MIDCAP, BANK, IT, …)."""
    indices = [
        "NIFTY SMALLCAP 100", "NIFTY SMALLCAP 250", "NIFTY MIDCAP 100",
        "NIFTY MIDCAP 150", "NIFTY MIDCAP 50", "NIFTY 500", "NIFTY 200",
        "NIFTY 100", "NIFTY NEXT 50", "NIFTY BANK", "NIFTY IT",
        "NIFTY PHARMA", "NIFTY FMCG", "NIFTY AUTO", "NIFTY METAL",
        "NIFTY REALTY", "NIFTY ENERGY", "NIFTY INFRA", "NIFTY OIL & GAS",
        "NIFTY FINANCIAL SERVICES", "NIFTY HEALTHCARE INDEX",
        "NIFTY PSU BANK", "NIFTY PRIVATE BANK",
        "NIFTY MEDIA", "NIFTY CONSUMER DURABLES",
    ]
    phrasings = [
        ("bare-{i}",     lambda idx: idx),
        ("analyze-{i}",  lambda idx: f"lets analyze {idx}"),
        ("how-{i}",      lambda idx: f"how is {idx} doing"),
        ("trend-{i}",    lambda idx: f"show me {idx} trend"),
        ("perf-{i}",     lambda idx: f"{idx} performance this week"),
    ]
    scenarios: list[Scenario] = []
    # Build first 30: cycle through indices × phrasings
    flat: list[tuple[str, str]] = []
    for pfx, fn in phrasings:
        for idx_name in indices:
            flat.append((pfx, fn(idx_name)))
            if len(flat) >= 30:
                break
        if len(flat) >= 30:
            break
    for i, (pfx, q) in enumerate(flat[:30], start=1):
        scenarios.append(Scenario(
            id=f"A{i:02d}",
            bucket="A_index_routing",
            query=q,
            asserts=[
                ("answer_not_contains", "SYMBOL VALIDATION FAILED"),
                ("no_exception",),
            ],
            description="Index analysis should not trip symbol validation.",
        ))
    return scenarios


def _bucket_b_resolver_traps() -> list[Scenario]:
    """20 cases: company-name queries that previously caused alias
    collisions (Premier Energies → AIIL was the canonical example)."""
    cases = [
        ("Premier Energies",                "PREMIERENE"),
        ("Hindustan Lever",                 "HINDUNILVR"),
        ("Hindustan Unilever",              "HINDUNILVR"),
        ("Bharat Forge",                    "BHARATFORG"),
        ("Bharat Petroleum",                "BPCL"),
        ("Larsen and Toubro",               "LT"),
        ("Tata Investment Corporation",     "TATAINVEST"),
        ("Tata Consultancy Services",       "TCS"),
        ("Adani Enterprises",               "ADANIENT"),
        ("Adani Ports",                     "ADANIPORTS"),
        ("Power Grid",                      "POWERGRID"),
        ("HDFC Bank",                       "HDFCBANK"),
        ("ICICI Bank",                      "ICICIBANK"),
        ("Mahindra and Mahindra",           "M&M"),
        ("Reliance Industries",             "RELIANCE"),
        ("State Bank of India",             "SBIN"),
        ("Asian Paints",                    "ASIANPAINT"),
        ("Bajaj Finance",                   "BAJFINANCE"),
        ("Sun Pharma",                      "SUNPHARMA"),
        ("Maruti Suzuki",                   "MARUTI"),
    ]
    return [
        Scenario(
            id=f"B{i:02d}",
            bucket="B_resolver_traps",
            query=f"can you analyze {name}",
            asserts=[
                ("answer_contains", expected_ticker),
                ("answer_not_contains", "SYMBOL VALIDATION FAILED"),
                ("no_exception",),
            ],
            description=f"{name} must resolve to {expected_ticker}, not an alias collision.",
        )
        for i, (name, expected_ticker) in enumerate(cases, start=1)
    ]


def _bucket_c_stock_briefs() -> list[Scenario]:
    """40 cases: vanilla stock-brief queries across large-/mid-/small-caps."""
    symbols = [
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC",
        "HINDUNILVR", "LT", "BAJFINANCE", "AXISBANK", "KOTAKBANK",
        "BHARTIARTL", "MARUTI", "M&M", "TITAN", "ULTRACEMCO", "NESTLEIND",
        "ASIANPAINT", "WIPRO", "TECHM", "HCLTECH", "ADANIENT", "ADANIPORTS",
        "POWERGRID", "NTPC", "ONGC", "COALINDIA", "BPCL", "IOC",
        "TATAMOTORS", "TATASTEEL", "JSWSTEEL", "HINDALCO", "SUNPHARMA",
        "DRREDDY", "CIPLA", "DIVISLAB", "GRASIM", "BRITANNIA",
    ]
    queries = [
        "analyze {s}", "{s} technical setup", "should I buy {s}",
        "what is the current setup of {s}", "{s} fundamentals",
    ]
    scenarios: list[Scenario] = []
    for i, sym in enumerate(symbols, start=1):
        q = queries[i % len(queries)].format(s=sym)
        scenarios.append(Scenario(
            id=f"C{i:02d}",
            bucket="C_stock_briefs",
            query=q,
            asserts=[
                ("trail_contains", "resolve_symbol"),
                ("answer_contains", sym),
                ("no_exception",),
            ],
        ))
    return scenarios


def _bucket_d_review_round_trips() -> list[Scenario]:
    """20 cases: scan → review the long/short setups round-trip. Tests
    the result_groups context wiring shipped in commit 3d9f5d3."""
    setup_q = (
        "Scan NIFTY MIDCAP 100 for stocks with active Supertrend research "
        "setups on 15m with clear invalidation levels."
    )
    followups = [
        "Review all the long setups",     "Review the longs",
        "Review long setups",             "Review longs",
        "Review all the longsetups",     "Details on the long setups",
        "deep dive on the long setups",  "review all setups",
        "Review the shorts",             "Review short setups",
    ]
    indices_to_try = ["NIFTY MIDCAP 100", "NIFTY 100", "NIFTY 500", "NIFTY BANK"]
    scenarios: list[Scenario] = []
    for i, fu in enumerate(followups, start=1):
        idx = indices_to_try[i % len(indices_to_try)]
        scan = setup_q.replace("NIFTY MIDCAP 100", idx)
        scenarios.append(Scenario(
            id=f"D{i:02d}",
            bucket="D_review_round_trip",
            query=fu,
            setup_queries=[scan],
            asserts=[
                ("trail_contains", "compare_stocks"),
                ("answer_not_contains", "LATENTVIEW"),
                ("no_exception",),
            ],
        ))
    # Plus 10 alternate scan setups
    extra_scans = [
        ("Scan NIFTY 100 for EMA + volume breakout buys on 15m",
         "Review the long setups"),
        ("Scan NIFTY 500 intraday for MACD crossovers",
         "Deep dive these setups"),
        ("Scan NIFTY BANK intraday with supertrend strategy",
         "Review the shorts"),
        ("Scan NIFTY IT for Supertrend setups on 15m",
         "Review all setups"),
        ("Scan NIFTY AUTO for momentum signals 15m",
         "details on the long setups"),
        ("Scan NIFTY METAL intraday Supertrend",
         "Review the longs"),
        ("Scan NIFTY PHARMA 15m breakouts",
         "review longs"),
        ("Scan NIFTY FMCG 15m signals",
         "review shorts"),
        ("Scan NIFTY SMALLCAP 100 for 15m supertrend",
         "review setups"),
        ("Scan NIFTY MIDCAP 150 intraday",
         "Review the long setups"),
    ]
    for j, (scan, fu) in enumerate(extra_scans, start=len(scenarios) + 1):
        scenarios.append(Scenario(
            id=f"D{j:02d}",
            bucket="D_review_round_trip",
            query=fu,
            setup_queries=[scan],
            asserts=[
                ("trail_contains", "compare_stocks"),
                ("no_exception",),
            ],
        ))
    return scenarios[:20]


def _bucket_e_sector_movers() -> list[Scenario]:
    """20 cases: sector / movers queries."""
    cases = [
        ("top gainers in NIFTY 50",           "get_top_gainers_losers"),
        ("top losers today",                  "get_top_gainers_losers"),
        ("biggest movers in NIFTY BANK",      "get_top_gainers_losers"),
        ("most active stocks by volume",      "get_most_active_stocks"),
        ("52 week high stocks",               "get_52week_extremes"),
        ("how is the IT sector doing",        "get_sector_context"),
        ("auto sector performance",           "get_sector_context"),
        ("pharma sector context",             "get_sector_context"),
        ("market breadth today",              "get_market_breadth"),
        ("market overview live",              "get_live_market_overview"),
        ("FII DII activity today",            "get_fii_dii_activity"),
        ("bulk deals today",                  "get_bulk_block_deals"),
        ("how is banking sector",             "get_sector_context"),
        ("metal sector view",                 "get_sector_context"),
        ("global market cues",                "get_global_market_assessment"),
        ("how did US market close",           "get_global_market_assessment"),
        ("crude oil and dollar context",      "get_global_market_assessment"),
        ("show top gainers in NIFTY IT",      "get_top_gainers_losers"),
        ("realty sector how is it",           "get_sector_context"),
        ("what is the advance decline today", "get_market_breadth"),
    ]
    return [
        Scenario(
            id=f"E{i:02d}",
            bucket="E_sector_movers",
            query=q,
            asserts=[
                ("trail_contains", expected_tool),
                ("no_exception",),
            ],
        )
        for i, (q, expected_tool) in enumerate(cases, start=1)
    ]


def _bucket_f_report_followups() -> list[Scenario]:
    """20 cases: /analyze <sym> followed by report follow-up phrasings."""
    symbols = [
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "SBIN",
        "TATAMOTORS", "ITC", "BHARTIARTL", "ASIANPAINT", "LT",
        "AXISBANK", "MARUTI", "M&M", "WIPRO", "TITAN",
        "SUNPHARMA", "NTPC", "POWERGRID", "ULTRACEMCO", "ADANIENT",
    ]
    followups = [
        "summarize its recommendation",  "what does the report say",
        "summarise the report",          "give me a recap",
        "tldr",                          "summary please",
        "tl;dr",                         "its recommendation",
        "what is the conclusion",        "show me the report",
        "open the report",               "summarize the report",
        "what does it say",              "the recommendation",
        "give me the conclusion",        "summary",
        "recap please",                  "summarise",
        "summary of report",             "summarise it",
    ]
    scenarios: list[Scenario] = []
    for i, (sym, fu) in enumerate(zip(symbols, followups), start=1):
        scenarios.append(Scenario(
            id=f"F{i:02d}",
            bucket="F_report_followups",
            query=fu,
            setup_queries=[f"/analyze {sym}"],
            asserts=[
                ("answer_contains", sym),
                ("answer_not_contains", "SYMBOL VALIDATION FAILED"),
                ("no_exception",),
            ],
            description=f"After /analyze {sym}, follow-up '{fu}' must stay on {sym}.",
        ))
    return scenarios


def _bucket_g_clarification_replies() -> list[Scenario]:
    """15 cases: ambiguous setup → letter / option-text reply binding."""
    # Trigger an ask_clarification via /recap with no window, or generic
    # 'what about these' style follow-up that asks for clarification.
    cases = [
        ([f"/analyze RELIANCE"], "summary"),
        ([f"/analyze TCS"], "B"),
        ([f"/analyze INFY"], "summarize it"),
        ([f"/recap"], "last 30 minutes"),
        ([f"/recap"], "A"),
        ([f"/analyze SBIN"], "open it"),
        ([f"/analyze HDFCBANK"], "the conclusion"),
        ([f"/analyze ITC"], "tldr"),
        ([f"/analyze BHARTIARTL"], "what does it say"),
        ([f"/analyze LT"], "C"),
        ([f"/analyze TITAN"], "summarise the recommendation"),
        ([f"/analyze WIPRO"], "show me the report"),
        ([f"/analyze NTPC"], "tl;dr"),
        ([f"/analyze MARUTI"], "summary please"),
        ([f"/analyze ASIANPAINT"], "summarize it for me"),
    ]
    return [
        Scenario(
            id=f"G{i:02d}",
            bucket="G_clarification_reply",
            query=q,
            setup_queries=list(setups),
            asserts=[
                ("answer_not_contains", "SYMBOL VALIDATION FAILED"),
                ("no_exception",),
            ],
        )
        for i, (setups, q) in enumerate(cases, start=1)
    ]


def _bucket_h_concept_screener() -> list[Scenario]:
    """20 cases: concept words / screener queries — must NOT resolve_symbol
    on tokens like RSI, PE, ROE, MOMENTUM, etc."""
    cases = [
        ("show me stage 2 stocks",        "run_screener_query"),
        ("top RS stocks",                  "run_screener_query"),
        ("new highs today",                "run_screener_query"),
        ("breakouts today",                "run_screener_query"),
        ("momentum leaders",                "run_screener_query"),
        ("turnaround setups",               "run_screener_query"),
        ("tight range stocks",              "run_screener_query"),
        ("oversold bounces",                "run_screener_query"),
        ("basing stocks",                   "run_screener_query"),
        ("strong buy signals",              "run_screener_query"),
        ("what is RSI",                     "search_market_knowledge"),
        ("explain ROCE",                    "search_market_knowledge"),
        ("what is CANSLIM",                 "search_market_knowledge"),
        ("define Piotroski score",          "search_market_knowledge"),
        ("what is VCP pattern",             "search_market_knowledge"),
        ("Minervini strategy explanation",  "search_market_knowledge"),
        ("ROE vs ROCE difference",          "search_market_knowledge"),
        ("what is supertrend indicator",    "search_market_knowledge"),
        ("opening range breakout intraday", "run_intraday_screener"),
        ("MACD crossover scan today",       "run_intraday_screener"),
    ]
    return [
        Scenario(
            id=f"H{i:02d}",
            bucket="H_concept_screener",
            query=q,
            asserts=[
                ("trail_contains", expected_tool),
                ("answer_not_contains", "SYMBOL VALIDATION FAILED"),
                ("no_exception",),
            ],
        )
        for i, (q, expected_tool) in enumerate(cases, start=1)
    ]


def _bucket_i_adversarial() -> list[Scenario]:
    """15 cases: edge cases — typos, lowercase, compare, multi-stock, etc."""
    cases = [
        # Lowercase tickers
        ("reliance technical setup",                "RELIANCE"),
        ("tcs fundamentals",                        "TCS"),
        ("infy chart",                              "INFY"),
        # Common typos
        ("analyse RELIENCE technical",              "RELIANCE"),
        ("DATAPATTERNS setup",                      "DATAPATTNS"),
        # Compare
        ("compare TCS and INFY",                    "compare_stocks"),
        ("rank RELIANCE vs ONGC vs IOC",            "compare_stocks"),
        ("how is HDFCBANK vs ICICIBANK",            "compare_stocks"),
        # F&O
        ("NIFTY option chain",                      "get_option_chain"),
        ("BANKNIFTY PCR analysis",                  "get_fno_analytics"),
        # Intraday
        ("breakout stocks live last 30 minutes",    "scan_intraday_market"),
        # Concept
        ("what is the difference between PE and PB",  "search_market_knowledge"),
        # Mixed-case ticker
        ("Hindustan Zinc analysis",                 "HINDZINC"),
        # Multi-word ticker
        ("Bajaj Auto fundamentals",                 "BAJAJ-AUTO"),
        # Plural / setup phrase
        ("show me trading setups for ICICIBANK",    "ICICIBANK"),
    ]
    scenarios: list[Scenario] = []
    for i, (q, expected) in enumerate(cases, start=1):
        # If expected starts with lowercase, it's a tool name; otherwise a symbol
        if expected.islower() or "_" in expected:
            asserts = [("trail_contains", expected), ("no_exception",)]
        else:
            asserts = [
                ("answer_contains", expected),
                ("answer_not_contains", "SYMBOL VALIDATION FAILED"),
                ("no_exception",),
            ]
        scenarios.append(Scenario(
            id=f"I{i:02d}",
            bucket="I_adversarial",
            query=q,
            asserts=asserts,
        ))
    return scenarios


def build_scenarios() -> list[Scenario]:
    return (
        _bucket_a_index_routing()
        + _bucket_b_resolver_traps()
        + _bucket_c_stock_briefs()
        + _bucket_d_review_round_trips()
        + _bucket_e_sector_movers()
        + _bucket_f_report_followups()
        + _bucket_g_clarification_replies()
        + _bucket_h_concept_screener()
        + _bucket_i_adversarial()
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _trail_from_trace(trace: list[dict] | None) -> list[str]:
    """Pull tool names from an Agent trace into a flat list."""
    if not trace:
        return []
    names: list[str] = []
    for entry in trace:
        if not isinstance(entry, dict):
            continue
        tool = entry.get("tool")
        if tool:
            names.append(str(tool))
        # Some traces nest tool calls under 'plan' / 'tools'
        for key in ("tools", "plan"):
            inner = entry.get(key)
            if isinstance(inner, list):
                for ent in inner:
                    if isinstance(ent, dict) and ent.get("tool"):
                        names.append(str(ent["tool"]))
                    elif isinstance(ent, (tuple, list)) and len(ent) >= 1:
                        names.append(str(ent[0]))
                    elif isinstance(ent, str):
                        names.append(ent)
    return names


def evaluate(scenario: Scenario, answer: str, trace: list[dict] | None,
             exc: str | None) -> tuple[bool, list[str]]:
    failures: list[str] = []
    trail = _trail_from_trace(trace)
    trail_joined = " ".join(trail)
    answer_low = (answer or "").lower()
    for check in scenario.asserts:
        kind = check[0]
        if kind == "no_exception":
            if exc is not None:
                failures.append(f"raised exception: {exc.splitlines()[-1][:120]}")
        elif kind == "trail_contains":
            tool = check[1]
            if tool not in trail_joined:
                failures.append(f"missing tool {tool!r} in trail ({trail})")
        elif kind == "trail_not_contains":
            tool = check[1]
            if tool in trail_joined:
                failures.append(f"forbidden tool {tool!r} in trail")
        elif kind == "answer_contains":
            needle = check[1]
            if needle.lower() not in answer_low:
                failures.append(f"answer missing {needle!r}")
        elif kind == "answer_not_contains":
            needle = check[1]
            if needle.lower() in answer_low:
                failures.append(f"answer contained forbidden {needle!r}")
        else:
            failures.append(f"unknown check kind {kind!r}")
    return (not failures), failures


def run_one(agent, scenario: Scenario) -> Result:
    started = time.time()
    answer = ""
    trace: list[dict] = []
    exc: str | None = None
    try:
        # Reset history between scenarios (each scenario is independent).
        agent._history = []
        agent._last_symbols = []
        agent._last_turn_context = None
        agent._pending_clarification = None
        # Run any setup queries first (for follow-up contexts).
        for setup in scenario.setup_queries:
            try:
                agent.query(setup)
            except Exception as e:
                # Setup failure is not a scenario failure unless asserted.
                exc = (
                    f"setup query failed: {setup!r}: "
                    + "".join(traceback.format_exception_only(type(e), e))
                )
        res = agent.query(scenario.query)
        answer = res.get("answer", "") or ""
        trace = res.get("trace") or []
    except Exception as e:
        exc = "".join(traceback.format_exception(type(e), e, e.__traceback__))
    duration = time.time() - started
    passed, failures = evaluate(scenario, answer, trace, exc)
    return Result(
        scenario=scenario,
        passed=passed,
        failures=failures,
        duration_s=duration,
        answer_excerpt=(answer or "")[:300].replace("\n", " "),
        tool_trail=_trail_from_trace(trace),
        exception=exc,
    )


def write_report(results: list[Result], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    # Per-bucket aggregates
    by_bucket: dict[str, list[Result]] = {}
    for r in results:
        by_bucket.setdefault(r.scenario.bucket, []).append(r)
    lines: list[str] = []
    lines.append(f"# Live Scenario Run — {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append(f"**Total:** {total}  ·  **Passed:** {passed} ({passed/total:.0%})  ·  **Failed:** {failed}")
    lines.append("")
    lines.append("## By bucket")
    lines.append("")
    lines.append("| Bucket | Cases | Pass | Fail | Pass % |")
    lines.append("|---|---:|---:|---:|---:|")
    for bucket in sorted(by_bucket):
        items = by_bucket[bucket]
        b_p = sum(1 for r in items if r.passed)
        b_f = len(items) - b_p
        lines.append(f"| {bucket} | {len(items)} | {b_p} | {b_f} | {b_p/len(items):.0%} |")
    lines.append("")
    if failed:
        lines.append("## Failures")
        lines.append("")
        for r in results:
            if r.passed:
                continue
            lines.append(f"### {r.scenario.id} — {r.scenario.bucket}")
            lines.append(f"- **Query:** `{r.scenario.query}`")
            if r.scenario.setup_queries:
                lines.append(f"- **Setup:** {'; '.join(repr(s) for s in r.scenario.setup_queries)}")
            lines.append(f"- **Failures:** {'; '.join(r.failures)}")
            lines.append(f"- **Trail:** {r.tool_trail}")
            lines.append(f"- **Answer excerpt:** {r.answer_excerpt}")
            if r.exception:
                lines.append(f"- **Exception:** {r.exception.splitlines()[-1][:200]}")
            lines.append("")
    out_path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Run only the first N scenarios (smoke testing).")
    parser.add_argument("--bucket", action="append", default=None,
                        help="Filter to one or more buckets (repeatable).")
    parser.add_argument("--out", type=str, default=None,
                        help="Override output path for the report.")
    parser.add_argument("--progress-every", type=int, default=5,
                        help="Print progress every N scenarios.")
    args = parser.parse_args()

    # Import here so cwd / .env are set up first.
    from terminal.agent import Agent  # noqa: WPS433

    scenarios = build_scenarios()
    if args.bucket:
        keep = set(args.bucket)
        scenarios = [s for s in scenarios if s.bucket in keep]
    if args.limit:
        scenarios = scenarios[: args.limit]

    print(f"[runner] Running {len(scenarios)} scenarios with backend agent…",
          flush=True)
    agent = Agent()
    print(f"[runner] Backend ready: {agent.backend_name}", flush=True)

    results: list[Result] = []
    started_at = time.time()
    for i, scen in enumerate(scenarios, start=1):
        r = run_one(agent, scen)
        results.append(r)
        if i % args.progress_every == 0 or i == len(scenarios):
            elapsed = time.time() - started_at
            passed = sum(1 for x in results if x.passed)
            print(
                f"[{i:3d}/{len(scenarios)}] {scen.id:6s} {scen.bucket:24s} "
                f"{'PASS' if r.passed else 'FAIL':5s} "
                f"{r.duration_s:5.1f}s  cum {passed}/{i} pass  "
                f"elapsed {elapsed/60:5.1f}m",
                flush=True,
            )
            if not r.passed:
                print(f"          → {r.failures}", flush=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(args.out) if args.out else Path("reports/scenarios") / f"live_scenarios_{ts}.md"
    write_report(results, out_path)
    json_path = out_path.with_suffix(".json")
    json_path.write_text(json.dumps([
        {
            "id": r.scenario.id, "bucket": r.scenario.bucket,
            "query": r.scenario.query, "setup": r.scenario.setup_queries,
            "passed": r.passed, "failures": r.failures,
            "duration_s": r.duration_s,
            "trail": r.tool_trail,
            "answer_excerpt": r.answer_excerpt,
        }
        for r in results
    ], indent=2))

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    print(f"\n[runner] DONE — {passed}/{total} passed "
          f"({passed/total:.0%}) in {(time.time()-started_at)/60:.1f}m", flush=True)
    print(f"[runner] Report: {out_path}", flush=True)
    print(f"[runner] JSON:   {json_path}", flush=True)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
