#!/usr/bin/env python3
"""Run scenario-quality checks against Agent Adda final responses.

The harness intentionally calls terminal.agent.Agent directly instead of the
terminal wrapper so the test exercises routing, tool execution, guardrails,
renderers, and final answer text without printing the startup UI 300 times.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))

os.environ.setdefault("AGENT_ADDA_MEMORY_PG", "0")

from terminal.agent import (  # noqa: E402
    Agent,
    _apply_response_guardrails,
    _execute_plan,
    _keyword_intent,
    _synthesize_and_narrate,
)


SYMBOLS = [
    ("CHENNPETRO", "chennai petroleum"),
    ("TATASTEEL", "tata steel"),
    ("RELIANCE", "reliance"),
    ("HDFCBANK", "hdfc bank"),
    ("INFY", "infosys"),
    ("SBIN", "sbi"),
    ("ICICIBANK", "icici bank"),
    ("LT", "larsen and toubro"),
    ("ITC", "itc"),
    ("MARUTI", "maruti"),
    ("SUNPHARMA", "sun pharma"),
    ("BHARTIARTL", "bharti airtel"),
]

TEMPLATES = [
    "perform a deep analysis of {name}",
    "deep dive into {name} fundamentals and technicals",
    "detailed fundamental and technical analysis of {name}",
    "latest quarterly results for {name}",
    "latest results of {name}",
    "explain {name} latest results with revenue pat eps and source trail",
    "analyze {name} valuation, roe, roce, debt and recent quarterly numbers",
    "is {name} technically strong and are fundamentals supporting it",
    "give a precise risk reward view on {name} using technicals, sector context and fundamentals",
    "what changed in {name} earnings and does the chart confirm strength",
    "summarize {name} from pg financial cache, screener ratios and nse filings",
    "find missing evidence in {name} analysis before giving a conclusion",
    "compare latest results evidence and screener fundamentals for {name}",
    "deep analysis of {name}: price action, sector, financials, risks, and watch levels",
    "what are the key positives and negatives in {name} with numbers",
    "should I track {name} now based on stage, rs, latest results and valuation",
    "review {name} for articulation: clear thesis, evidence, risks, and source trail",
    "does {name} have earnings momentum and technical confirmation",
    "give an investor-friendly but precise explanation of {name}",
    "give a trader-friendly but evidence grounded setup for {name}",
    "show {name} technical setup plus quarterly results evidence",
    "what is the fundamental evidence chain for {name}",
    "explain {name} in simple terms but include exact numbers and caveats",
    "produce a comprehensive grounded view on {name} without unsupported claims",
    "what is the final answer for {name} after checking pg, screener and nse",
]


@dataclass
class ScenarioResult:
    idx: int
    symbol: str
    query: str
    intent: str
    ok: bool
    elapsed_sec: float
    score: int
    scores: dict[str, int]
    issues: list[str]
    tools: list[str]
    answer_chars: int
    answer_excerpt: str


def build_scenarios(limit: int) -> list[tuple[str, str]]:
    scenarios: list[tuple[str, str]] = []
    for template in TEMPLATES:
        for symbol, name in SYMBOLS:
            scenarios.append((symbol, template.format(name=name)))
    return scenarios[:limit]


def tool_names(trace: list[dict]) -> list[str]:
    out: list[str] = []
    for item in trace or []:
        if isinstance(item, dict) and item.get("tool"):
            out.append(str(item["tool"]))
        for nested in item.get("trace") or [] if isinstance(item, dict) else []:
            if isinstance(nested, dict) and nested.get("tool"):
                out.append(str(nested["tool"]))
    return out


def score_answer(query: str, symbol: str, answer: str, tools: list[str]) -> tuple[int, dict[str, int], list[str]]:
    text = answer or ""
    upper = text.upper()
    query_l = query.lower()
    issues: list[str] = []

    hard_fail_patterns = [
        "REQUIRED TOOL VALIDATION FAILED",
        "SYMBOL VALIDATION FAILED",
        "TRACEBACK",
        "NO MARKET CONCLUSION WAS RENDERED",
    ]
    for pattern in hard_fail_patterns:
        if pattern in upper:
            issues.append(pattern)
    if "ERROR:" in text:
        issues.append("source_errors")
    if "▶ MISSING EVIDENCE" in upper or "MISSING EVIDENCE:" in upper:
        issues.append("missing_evidence")

    grounding = 0
    if "SOURCE TRAIL" in upper:
        grounding += 2
    if any(t in tools for t in ("get_cached_financials", "scrape_screener_in", "get_latest_results")):
        grounding += 2
    if "PG financial cache" in text or "pg_cache" in text or "scrape_screener_in" in text:
        grounding += 2
    if re.search(r"\b(?:Revenue|PAT|EPS|ROE|ROCE|RSI|ADX|Stage|Price)\b", text):
        grounding += 2
    if re.search(r"\b(?:Mar|Jun|Sep|Dec)\s+20\d{2}\b|20\d{2}-\d{2}-\d{2}", text):
        grounding += 1
    if "Not investment advice" in text:
        grounding += 1

    specificity = 0
    if symbol in upper:
        specificity += 2
    if len(re.findall(r"[-+]?\d[\d,.]*%?", text)) >= 6:
        specificity += 3
    if any(term in upper for term in ("REVENUE", "PAT", "EPS", "ROCE", "ROE", "RSI", "ADX")):
        specificity += 2
    if any(term in upper for term in ("LATEST", "QUARTERLY", "ANNUAL", "TECHNICAL", "FUNDAMENTAL")):
        specificity += 2
    if len(text) >= 900:
        specificity += 1

    clarity = 0
    if text.count("▶") >= 2 or text.count("\n#") >= 1:
        clarity += 3
    if len(text) >= 400:
        clarity += 2
    if len(text) <= 9000:
        clarity += 2
    if not re.search(r"\b(?:maybe|probably|I think|might be)\b", text, flags=re.I):
        clarity += 1
    if "\n  " in text or "\n-" in text:
        clarity += 2

    completeness = 0
    expected_terms = []
    if any(term in query_l for term in ("deep", "detailed", "comprehensive")):
        expected_terms += ["SNAPSHOT", "TECHNICAL", "FUNDAMENTAL", "RISK"]
    if any(term in query_l for term in ("latest", "quarterly", "earnings", "results")):
        expected_terms += ["LATEST", "REVENUE", "PAT"]
    if any(term in query_l for term in ("technical", "chart", "trader", "setup")):
        expected_terms += ["TECHNICAL", "RSI"]
    if any(term in query_l for term in ("valuation", "roe", "roce", "debt", "fundamental")):
        expected_terms += ["FUNDAMENTAL", "ROE", "ROCE"]
    if not expected_terms:
        expected_terms = ["SOURCE", symbol]
    hit = sum(1 for term in dict.fromkeys(expected_terms) if term in upper)
    completeness += min(10, int(10 * hit / max(1, len(dict.fromkeys(expected_terms)))))

    scores = {
        "grounding": min(10, grounding),
        "specificity": min(10, specificity),
        "clarity": min(10, clarity),
        "completeness": min(10, completeness),
    }
    total = sum(scores.values())

    for key, value in scores.items():
        if value < 7:
            issues.append(f"low_{key}:{value}")
    if len(text.strip()) < 250:
        issues.append("too_short")
    if not tools:
        issues.append("no_tools")

    return total, scores, issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--out-dir", default="reports/agent_adda_eval")
    parser.add_argument("--stop-on-fail", action="store_true")
    parser.add_argument(
        "--prefetch-symbol-evidence",
        action="store_true",
        help="Fetch each symbol's real evidence once, then synthesize every scenario from the cached evidence pack.",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y%m%d_%H%M%S")
    jsonl_path = out_dir / f"scenario_eval_{stamp}.jsonl"
    summary_path = out_dir / f"scenario_eval_{stamp}.md"

    scenarios = build_scenarios(args.limit)
    agent = Agent()
    results: list[ScenarioResult] = []
    evidence_by_symbol: dict[str, list[dict]] = {}

    if args.prefetch_symbol_evidence:
        symbols_needed = list(dict.fromkeys(symbol for symbol, _query in scenarios))
        for sym in symbols_needed:
            plan = [
                ("resolve_symbol", {"query": sym}),
                ("get_symbol_snapshot", {"symbol": sym}),
                ("get_technical_setup", {"symbol": sym}),
                ("get_sector_context", {"sector_or_symbol": sym}),
                ("get_cached_financials", {"symbol": sym}),
                ("scrape_screener_in", {"symbol": sym}),
                ("get_latest_results", {"symbol": sym}),
                ("search_nse_announcements", {"symbol": sym}),
            ]
            started = time.perf_counter()
            evidence_by_symbol[sym] = _execute_plan(plan)
            print(f"PREFETCH {sym} tools={len(evidence_by_symbol[sym])} time={time.perf_counter() - started:.1f}s", flush=True)

    with jsonl_path.open("w", encoding="utf-8") as fh:
        for idx, (symbol, query) in enumerate(scenarios, start=1):
            started = time.perf_counter()
            try:
                if args.prefetch_symbol_evidence:
                    routed = _keyword_intent(query)
                    routed_intent = str((routed or {}).get("intent") or "")
                    intent = routed_intent if routed_intent in {"stock_results", "stock_brief"} else "stock_brief"
                    trace = evidence_by_symbol[symbol]
                    answer = _synthesize_and_narrate(intent, query, trace, agent.backend)
                    answer = _apply_response_guardrails(query, intent, trace, answer)
                    tools = tool_names(trace)
                else:
                    res = agent.query(query, show_trace=True)
                    answer = str(res.get("answer") or "")
                    intent = str(res.get("intent") or "")
                    tools = tool_names(res.get("trace") or [])
                elapsed = time.perf_counter() - started
                total, scores, issues = score_answer(query, symbol, answer, tools)
                ok = not any(
                    issue.startswith(("REQUIRED", "SYMBOL", "TRACEBACK", "NO MARKET"))
                    or issue in {"source_errors", "missing_evidence"}
                    for issue in issues
                ) and total >= 28
            except Exception as exc:
                answer = ""
                intent = "exception"
                tools = []
                elapsed = time.perf_counter() - started
                total = 0
                scores = {"grounding": 0, "specificity": 0, "clarity": 0, "completeness": 0}
                issues = [f"exception:{type(exc).__name__}:{str(exc).splitlines()[0]}"]
                ok = False

            row = ScenarioResult(
                idx=idx,
                symbol=symbol,
                query=query,
                intent=intent,
                ok=ok,
                elapsed_sec=round(elapsed, 2),
                score=total,
                scores=scores,
                issues=issues,
                tools=tools,
                answer_chars=len(answer),
                answer_excerpt=answer[:1200],
            )
            results.append(row)
            fh.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
            fh.flush()
            print(
                f"{idx:03d}/{len(scenarios)} "
                f"{'OK' if ok else 'FAIL'} score={total:02d} "
                f"intent={intent} symbol={symbol} time={elapsed:.1f}s "
                f"issues={','.join(issues[:3]) or '-'}"
            )
            if args.stop_on_fail and not ok:
                break

    failures = [r for r in results if not r.ok]
    avg = sum(r.score for r in results) / max(1, len(results))
    lines = [
        f"# Agent Adda Scenario Evaluation - {stamp}",
        "",
        f"- Scenarios run: {len(results)}",
        f"- Passed: {len(results) - len(failures)}",
        f"- Failed / low quality: {len(failures)}",
        f"- Average score: {avg:.1f} / 40",
        f"- JSONL: `{jsonl_path}`",
        "",
        "## Failure Summary",
    ]
    if failures:
        for r in failures[:50]:
            lines.extend([
                "",
                f"### {r.idx}. {r.symbol} - score {r.score}/40",
                f"- Query: `{r.query}`",
                f"- Intent: `{r.intent}`",
                f"- Issues: {', '.join(r.issues) or '-'}",
                f"- Tools: {', '.join(r.tools) or '-'}",
                "",
                "```text",
                r.answer_excerpt.strip(),
                "```",
            ])
    else:
        lines.append("No failures under the harness thresholds.")
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"SUMMARY {summary_path}")
    print(f"JSONL {jsonl_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
