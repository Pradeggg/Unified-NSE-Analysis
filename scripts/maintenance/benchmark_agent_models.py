#!/usr/bin/env python3
"""Benchmark Agent Adda main chat backends across OpenAI and Ollama.

This script intentionally exercises the application layer, not a bare LLM API:
symbol routing, tool calls, no-assumption handling, report generation, and
multi-turn context are all measured from `terminal.agent.Agent`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

from terminal.agent import Agent
from terminal.reports import generate_preset_report


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    category: str
    query: str
    mode: str = "single"
    notes: str = ""
    expected_symbols: tuple[str, ...] = ()
    required_tools: tuple[str, ...] = ()
    required_terms: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ()
    model_dependent: bool = True


CORE_CASES: list[BenchmarkCase] = [
    BenchmarkCase(
        "market_overview",
        "market_overview",
        "Give me a current NSE market overview with NIFTY, BANKNIFTY, breadth, FII/DII flow, and top risks. Be explicit about data freshness.",
        required_tools=("get_live_market_overview",),
        required_terms=("breadth", "NIFTY"),
    ),
    BenchmarkCase(
        "stock_technical_dmart",
        "stock_technical",
        "Give a full technical setup for DMART: Weinstein stage, RSI, ADX, MACD, supertrend, moving averages, RS rank, support/resistance, and source trail.",
        expected_symbols=("DMART",),
        required_tools=("resolve_symbol", "get_symbol_snapshot", "get_technical_setup"),
        required_terms=("RSI", "ADX", "supertrend"),
    ),
    BenchmarkCase(
        "education_roce_roe",
        "market_education",
        "Explain how ROCE is different from ROE for an Indian equity investor, with a simple example and common traps.",
        required_terms=("ROCE", "ROE"),
    ),
    BenchmarkCase(
        "compare_stocks",
        "comparative_research",
        "Compare DMART, TRENT, and VBL on technical strength, fundamentals, valuation, and risks. Do not assume missing values.",
        expected_symbols=("DMART", "TRENT", "VBL"),
        forbidden_terms=("TALBROAUTO",),
    ),
    BenchmarkCase(
        "strength_validation",
        "validated_strength",
        "Out of MANINDS, THERMAX, and BAJAJCON, which show strength based on CANSLIM, RS, fundamental analysis, and Piotroski? Validate data and flag missing evidence.",
        expected_symbols=("MANINDS", "THERMAX", "BAJAJCON"),
        required_tools=("validate_strength_watchlist",),
        required_terms=("Piotroski", "missing"),
    ),
    BenchmarkCase(
        "intraday_nifty",
        "intraday_situation",
        "Intraday technical analysis of NIFTY50 right now. Use NSE website snapshot first, then yfinance only as fallback, and label stale data.",
        expected_symbols=("NIFTY",),
        required_tools=("get_nse_intraday_snapshot",),
        required_terms=("NIFTY",),
    ),
    BenchmarkCase(
        "tool_heavy_research",
        "tool_calls",
        "Research WELCORP with technical setup, sector context, latest catalysts, and forensic red flags. Show what tools were used.",
        expected_symbols=("WELCORP",),
        required_tools=("resolve_symbol", "get_technical_setup", "get_sector_context"),
        required_terms=("WELCORP",),
    ),
]

MULTI_TURN_CASES: list[BenchmarkCase] = [
    BenchmarkCase(
        "multi_turn_1",
        "multi_turn_context",
        "Analyze WELCORP as a company and stock. Focus on what is known from the database and what still needs fresh evidence.",
        mode="multi",
        expected_symbols=("WELCORP",),
        required_terms=("WELCORP",),
    ),
    BenchmarkCase(
        "multi_turn_2",
        "multi_turn_context",
        "Now compare it with NAVABUPA and tell me which one has better evidence quality. Do not treat the word 'it' as a ticker.",
        mode="multi",
        expected_symbols=("WELCORP", "NAVABUPA"),
        forbidden_terms=("NIFTY 50", "proprietary", "GitHub", "peer-reviewed", "econometric"),
    ),
]

PROMPT_CATEGORY_CASES: list[BenchmarkCase] = [
    BenchmarkCase("prompt_market", "prompt_library", "Market overview — current trend, breadth, FII/DII and watchlist.", required_terms=("market",)),
    BenchmarkCase("prompt_intraday", "prompt_library", "Analyze RELIANCE intraday setup with clear target, stop loss, invalidation, and data freshness.", expected_symbols=("RELIANCE",), required_terms=("intraday",)),
    BenchmarkCase("prompt_technical", "prompt_library", "Technical setup for RELIANCE with stage, RSI, ADX, MACD, moving averages, and source trail.", expected_symbols=("RELIANCE",), required_tools=("get_technical_setup",)),
    BenchmarkCase("prompt_sector", "prompt_library", "Sector analysis for IT: breadth, leaders, laggards, rotation, and risks.", required_terms=("sector",)),
    BenchmarkCase("prompt_screener", "prompt_library", "Run Stage 2 breakout screen and explain top candidates without assuming missing evidence.", required_tools=("run_screener_query",)),
    BenchmarkCase("prompt_fundamentals", "prompt_library", "Fundamental quality review of TCS: ROE, ROCE, debt, valuation, growth and missing fields.", expected_symbols=("TCS",)),
    BenchmarkCase("prompt_stock", "prompt_library", "Full stock research brief for HDFCBANK with technicals, fundamentals, news and risks.", expected_symbols=("HDFCBANK",)),
    BenchmarkCase("prompt_news", "prompt_library", "Latest catalysts for INFY and what evidence is fresh versus stale.", expected_symbols=("INFY",)),
    BenchmarkCase("prompt_portfolio", "prompt_library", "Compare portfolio risk across RELIANCE, TCS, and HDFCBANK using evidence only.", expected_symbols=("RELIANCE", "TCS", "HDFCBANK")),
    BenchmarkCase("prompt_global", "prompt_library", "Global market read-through for India: US, Asia, crude, USD/INR, and NSE sector implications.", required_terms=("global",)),
]

SCAN_CASES: list[BenchmarkCase] = [
    BenchmarkCase("scan_default", "slash_scan", "/scan", mode="command", required_tools=("scan_symbols_intraday",)),
    BenchmarkCase("scan_nifty_bank", "slash_scan", "/scan NIFTY BANK", mode="command"),
    BenchmarkCase("scan_nifty_midcap", "slash_scan", "/scan NIFTY MIDCAP 100", mode="command"),
    BenchmarkCase("scan_orb", "slash_scan", "/scan orb", mode="command"),
    BenchmarkCase("scan_gap", "slash_scan", "/scan gap", mode="command"),
    BenchmarkCase("scan_macd", "slash_scan", "/scan macd", mode="command"),
    BenchmarkCase("scan_rsi", "slash_scan", "/scan rsi", mode="command"),
    BenchmarkCase("scan_bb", "slash_scan", "/scan bb", mode="command"),
    BenchmarkCase("scan_vwap", "slash_scan", "/scan vwap", mode="command"),
    BenchmarkCase("scan_vcp", "slash_scan", "/scan vcp", mode="command"),
    BenchmarkCase("scan_momentum", "slash_scan", "/scan momentum", mode="command"),
]

SCREEN_CASES: list[BenchmarkCase] = [
    BenchmarkCase("screen_stage2", "slash_screen", "/screen stage2", mode="command", required_tools=("run_screener_query",)),
    BenchmarkCase("screen_momentum", "slash_screen", "/screen momentum", mode="command", required_tools=("run_screener_query",)),
    BenchmarkCase("screen_highrs", "slash_screen", "/screen highrs", mode="command", required_tools=("run_screener_query",)),
    BenchmarkCase("screen_turnaround", "slash_screen", "/screen turnaround", mode="command", required_tools=("run_screener_query",)),
    BenchmarkCase("screen_base", "slash_screen", "/screen base", mode="command", required_tools=("run_screener_query",)),
    BenchmarkCase("screen_tight", "slash_screen", "/screen tight", mode="command", required_tools=("run_screener_query",)),
    BenchmarkCase("screen_dip", "slash_screen", "/screen dip", mode="command", required_tools=("run_screener_query",)),
]

COMMAND_CASES: list[BenchmarkCase] = [
    BenchmarkCase("cmd_model_status", "slash_command", "/model", mode="command", model_dependent=False),
    BenchmarkCase("cmd_prompts_catalog", "slash_command", "/prompts", mode="command", model_dependent=False),
    BenchmarkCase("cmd_backtest_list", "slash_command", "/backtest list", mode="command", model_dependent=False, required_terms=("stage2", "vcp")),
    BenchmarkCase("cmd_backtest_validate", "slash_command", "/strategy-lab validate", mode="command", model_dependent=False, required_terms=("Strategy Lab",)),
    BenchmarkCase("cmd_strength", "slash_command", "/strength MANINDS THERMAX BAJAJCON", mode="command", model_dependent=False, expected_symbols=("MANINDS", "THERMAX", "BAJAJCON")),
    BenchmarkCase("cmd_report_stage2_md", "slash_command", "/report stage2 md", mode="command", model_dependent=False, required_terms=("path", "stage2")),
    BenchmarkCase("cmd_report_sector_rotation_md", "slash_command", "/report sector-rotation md", mode="command", model_dependent=False, required_terms=("path", "sector")),
]

EDUCATION_AND_ANALYSIS_CASES: list[BenchmarkCase] = [
    BenchmarkCase("learn_pe_ratio", "market_education", "What is a PE ratio? Explain with Indian equity examples and source-backed caveats.", required_terms=("PE",)),
    BenchmarkCase("learn_minervini", "market_education", "Explain Minervini's trading strategy and how VCP differs from a normal breakout.", required_terms=("Minervini", "VCP")),
    BenchmarkCase("stock_brief_welcorp", "stock_brief", "What about WELCORP? Validate latest database data before answering.", expected_symbols=("WELCORP",)),
    BenchmarkCase("stock_brief_navabupa", "stock_brief", "What about NAVABUPA? If data is not available, say exactly what is missing.", expected_symbols=("NAVABUPA",), required_terms=("missing",)),
    BenchmarkCase("stock_brief_ushamart", "stock_brief", "Full technical setup for USHAMART with scores and historical details, loading missing data if available.", expected_symbols=("USHAMART",)),
    BenchmarkCase("market_clock", "market_clock", "Is NSE open right now? Give current IST time, market status, and whether intraday data should be considered live or fallback.", required_terms=("NSE", "IST")),
    BenchmarkCase("fno_options", "fno", "Give NIFTY option chain context, PCR, max pain, and whether options buying is attractive. Label source freshness.", expected_symbols=("NIFTY",)),
    BenchmarkCase("global_readthrough", "global", "Global market assessment and India sector read-through for today. Use global cues and state data freshness.", required_terms=("global", "India")),
]


def _all_cases() -> list[BenchmarkCase]:
    return (
        CORE_CASES
        + PROMPT_CATEGORY_CASES
        + SCAN_CASES
        + SCREEN_CASES
        + COMMAND_CASES
        + EDUCATION_AND_ANALYSIS_CASES
        + MULTI_TURN_CASES
    )


COMPLEX_WORKFLOW_CASES: list[BenchmarkCase] = [
    BenchmarkCase(
        "complex_stock_sherlock_reliance",
        "complex_ric_stock",
        "RIC-style Stock Sherlock for RELIANCE: resolve identity, get live or latest quote, full technical setup, sector context, latest catalysts, forensic red flags, then produce a research-only thesis with evidence gaps.",
        expected_symbols=("RELIANCE",),
        required_tools=("resolve_symbol", "get_technical_setup", "get_sector_context"),
        required_terms=("RELIANCE", "evidence"),
    ),
    BenchmarkCase(
        "complex_peer_battle_retail",
        "complex_peer_battle",
        "Peer battle: compare DMART, TRENT, and VBL across technical strength, valuation, business quality, catalysts, and missing evidence. Return a table and do not substitute any other symbol.",
        expected_symbols=("DMART", "TRENT", "VBL"),
        forbidden_terms=("TALBROAUTO", "QGOLDHALF"),
    ),
    BenchmarkCase(
        "complex_breakout_hunter",
        "complex_screener_to_scan",
        "Breakout hunter workflow: use Stage 2 screener, high RS logic, VCP/supertrend scan evidence, then shortlist 3 candidates with entry trigger, invalidation, and missing data.",
        required_tools=("run_screener_query",),
        required_terms=("Stage", "missing"),
    ),
    BenchmarkCase(
        "complex_sector_xray_it",
        "complex_sector",
        "Sector X-Ray for IT: breadth, leaders, laggards, RS vs Nifty, top 5 stocks, risks, and whether the sector is rotating in or out. Do not give a generic market overview.",
        required_terms=("IT", "sector"),
    ),
    BenchmarkCase(
        "complex_index_pulse_banknifty",
        "complex_index",
        "Index Pulse for NIFTY BANK: technical setup, breadth, top gainers/losers, intraday levels, FII/DII context, and market-clock freshness labels.",
        expected_symbols=("NIFTY",),
        required_terms=("BANK", "freshness"),
    ),
    BenchmarkCase(
        "complex_earnings_playbook_tcs",
        "complex_earnings",
        "Earnings playbook for TCS: latest results, financial ratios, peer comparison, management/concall commentary, post-earnings technical setup, and evidence gaps.",
        expected_symbols=("TCS",),
        forbidden_terms=("QGOLDHALF",),
    ),
    BenchmarkCase(
        "complex_risk_radar",
        "complex_macro_risk",
        "Risk Radar: combine global cues, FII/DII flow, market breadth extremes, Stage 4 or weak RS names, and vulnerable sectors. Separate data from inference.",
        required_terms=("risk", "breadth"),
    ),
    BenchmarkCase(
        "complex_morning_intel",
        "complex_morning",
        "Morning Intel: global overnight, previous NSE recap, current breadth, FII/DII activity, 5-stock watchlist, and what to verify after market open.",
        required_terms=("global", "breadth"),
    ),
    BenchmarkCase(
        "complex_company_xray_dmart",
        "complex_company_xray",
        "Company + Sector X-Ray for DMART: business model, customer base, operating model, competitive advantage, sector structure, policy sensitivity, bull/base/bear cases, and indexed-evidence gaps.",
        expected_symbols=("DMART",),
        required_terms=("business model", "evidence"),
    ),
    BenchmarkCase(
        "complex_kb_policy_impact_banks",
        "complex_kb_policy",
        "Use market knowledge style reasoning to explain how RBI monetary policy and Union Budget changes affect HDFCBANK and SBIN differently. Identify what data must be fetched before making a conclusion.",
        expected_symbols=("HDFCBANK", "SBIN"),
        required_terms=("RBI", "Budget"),
    ),
    BenchmarkCase(
        "complex_concall_management_infy",
        "complex_concall",
        "Find management commentary/concall evidence for INFY, summarize sentiment, key growth themes, risk flags, and clearly state if transcripts or source URLs are unavailable.",
        expected_symbols=("INFY",),
        required_terms=("concall", "source"),
    ),
    BenchmarkCase(
        "complex_deep_search_welcorp",
        "complex_deep_search",
        "Deep-search WELCORP across announcements, broker research, analyst coverage, concalls, and news. Return real URLs where available and no unsupported claims.",
        expected_symbols=("WELCORP",),
        required_terms=("WELCORP", "URL"),
    ),
    BenchmarkCase(
        "complex_forensic_strength_pack",
        "complex_forensic",
        "For MANINDS, THERMAX, BAJAJCON, and DEEDEV, validate CANSLIM, RS, fundamentals, Piotroski, Beneish, and Altman. Rank only where evidence exists.",
        expected_symbols=("MANINDS", "THERMAX", "BAJAJCON", "DEEDEV"),
        required_tools=("validate_strength_watchlist",),
        required_terms=("Piotroski", "evidence"),
    ),
    BenchmarkCase(
        "complex_intraday_supertrend_midcap",
        "complex_intraday_scan",
        "Scan NIFTY MIDCAP 100 for active 15m Supertrend research setups with targets, invalidation, source priority NSE first then yfinance fallback, and stale-data warnings.",
        required_terms=("Supertrend", "invalidation"),
    ),
    BenchmarkCase(
        "complex_options_strategy_nifty",
        "complex_options",
        "Build a NIFTY options strategy decision: option chain, PCR, max pain, IV context, directional bias, strategy recommendation, payoff risk, and freshness labels.",
        expected_symbols=("NIFTY",),
        required_terms=("PCR", "max pain"),
    ),
    BenchmarkCase(
        "complex_backtest_strategy_design",
        "complex_backtest_design",
        "Design an EOD backtest for Stage 2 + VCP + Supertrend confirmation: universe, entry rules, exit rules, risk model, metrics, PostgreSQL persistence, and test plan.",
        required_terms=("backtest", "PostgreSQL"),
    ),
    BenchmarkCase(
        "complex_report_generation_request",
        "complex_report_generation",
        "Generate a research-report plan for HDFCBANK: sections, data sources, tool calls, report format, source trail, and what should be saved as HTML/Markdown.",
        expected_symbols=("HDFCBANK",),
        required_terms=("report", "source"),
    ),
    BenchmarkCase(
        "complex_code_assimilation_reports_py",
        "complex_code_assimilation",
        "Inspect the reporting workflow conceptually: explain how terminal/reports.py should transform analysis content into Markdown/HTML/PDF, where hallucination risks enter, and how to test it.",
        required_terms=("reports.py", "test"),
    ),
    BenchmarkCase(
        "complex_code_assimilation_enhanced_report",
        "complex_code_assimilation",
        "Using the enhanced comprehensive analysis module as context, describe how DB-backed report generation should assimilate scores, indices, filtered stocks, and source metadata into a final report.",
        required_terms=("DB", "report"),
    ),
    BenchmarkCase(
        "complex_market_education_to_stock",
        "complex_education_application",
        "Teach PE, ROE, ROCE, and free cash flow, then apply them to compare TCS and INFY with missing-data handling and no valuation assumptions.",
        expected_symbols=("TCS", "INFY"),
        required_terms=("ROCE", "missing"),
    ),
    BenchmarkCase(
        "complex_portfolio_risk_assessment",
        "complex_portfolio",
        "Assess portfolio risk for RELIANCE, TCS, HDFCBANK, DMART, and WELCORP: sector concentration, technical stage, RS, drawdown risk, evidence gaps, and action checklist.",
        expected_symbols=("RELIANCE", "TCS", "HDFCBANK", "DMART", "WELCORP"),
    ),
    BenchmarkCase(
        "complex_global_to_sector_rotation",
        "complex_global_sector",
        "Map US market, crude, USD/INR, and Asia cues into Indian sector rotation. Name sectors that benefit or suffer and explain confidence level.",
        required_terms=("sector", "confidence"),
    ),
    BenchmarkCase(
        "complex_navabupa_symbol_guardrail",
        "complex_symbol_guardrail",
        "Analyze NAVABUPA. If the exact NSE symbol or database row is unavailable, do not substitute NIFTY, NAVA, NIVABUPA, or another company. Explain the symbol-resolution result.",
        expected_symbols=("NAVABUPA",),
        forbidden_terms=("NIFTY 50", "NAVA ", "NIVABUPA"),
    ),
    BenchmarkCase(
        "complex_multiturn_setup_1",
        "complex_multi_turn",
        "Start a multi-step investigation on WELCORP: establish identity, latest technical state, sector context, and open evidence gaps.",
        expected_symbols=("WELCORP",),
        required_terms=("WELCORP",),
    ),
    BenchmarkCase(
        "complex_multiturn_followup_2",
        "complex_multi_turn",
        "Now use that company as the base and compare it with JINDALSAW on business quality, technical strength, and evidence quality. Do not lose the prior company.",
        expected_symbols=("WELCORP", "JINDALSAW"),
        forbidden_terms=("TALBROAUTO",),
    ),
    BenchmarkCase(
        "complex_multi_tool_failure_handling",
        "complex_failure_handling",
        "Try to answer: latest broker target, latest concall, latest NSE announcement, current intraday setup, and forensic scores for APOLLOPIPE. If any source fails, produce a missing-evidence matrix.",
        expected_symbols=("APOLLOPIPE",),
        required_terms=("missing", "evidence"),
    ),
    BenchmarkCase(
        "complex_screen_to_report",
        "complex_screen_to_report",
        "Run a Stage 2 screen, select the strongest 5 by RS and technical evidence, then outline a Markdown report with source trails and risk notes.",
        required_tools=("run_screener_query",),
        required_terms=("Markdown", "risk"),
    ),
    BenchmarkCase(
        "complex_scan_to_watchlist",
        "complex_scan_to_watchlist",
        "From intraday scan logic, produce a watchlist for RELIANCE, TCS, INFY, HDFCBANK, and SBIN with setup label, target, invalidation, and stale-data warning.",
        expected_symbols=("RELIANCE", "TCS", "INFY", "HDFCBANK", "SBIN"),
        required_terms=("invalidation",),
    ),
    BenchmarkCase(
        "complex_agent_quality_audit",
        "complex_meta_audit",
        "Audit your own answer quality requirements for market research: tool calls, source trail, factual checks, missing data, market clock, no investment advice, and how to fail safely.",
        required_terms=("source", "missing", "market"),
    ),
    BenchmarkCase(
        "complex_end_to_end_trade_research",
        "complex_end_to_end",
        "End-to-end research for THERMAX: technical setup, fundamentals, sector context, latest catalysts, forensic quality, backtest idea, position risk, and final research-only decision tree.",
        expected_symbols=("THERMAX",),
        required_terms=("THERMAX", "risk"),
    ),
]


def _complex_cases() -> list[BenchmarkCase]:
    return COMPLEX_WORKFLOW_CASES


def _summarize_trace(trace: list[dict[str, Any]]) -> dict[str, Any]:
    tools: list[str] = []
    errors: list[str] = []
    intents: list[str] = []
    for item in trace or []:
        if item.get("step") == "intent":
            intent = ((item.get("result") or {}).get("intent") or "").strip()
            if intent:
                intents.append(intent)
            continue
        tool = item.get("tool")
        if tool:
            tools.append(str(tool))
        result = item.get("result")
        if isinstance(result, dict) and result.get("error"):
            errors.append(f"{tool}: {result.get('error')}")
    return {
        "tool_count": len(tools),
        "tools": tools,
        "unique_tools": sorted(set(tools)),
        "errors": errors,
        "intents": intents,
    }


def _answer_metrics(answer: str) -> dict[str, Any]:
    lower = answer.lower()
    return {
        "chars": len(answer),
        "words": len(answer.split()),
        "has_disclaimer": "not investment advice" in lower or "research and learning only" in lower,
        "mentions_mode": "mode:" in lower,
        "mentions_source_trail": "source trail" in lower,
        "mentions_missing_data": any(x in lower for x in ("missing", "unavailable", "not found", "no data")),
        "mentions_market_clock": "market:" in lower or "clock:" in lower or "pre-market" in lower or "closed" in lower,
    }


_SCREEN_ALIASES = {
    "stage2":     ("stage2",          "Stage 2 Uptrend"),
    "breakouts":  ("breakouts",       "Stage 2 Breakouts"),
    "supertrend": ("supertrend_buy",  "Supertrend BUY"),
    "strong":     ("strong_buy",      "Strong Buy"),
    "new":        ("new_entrants",    "New Stage 2 Entrants"),
    "momentum":   ("momentum_52w",    "52W High Momentum Leaders"),
    "highrs":     ("high_rs",         "High RS Leaders"),
    "turnaround": ("turnaround",      "Turnaround Recovery"),
    "base":       ("stage1_base",     "Stage 1 Basing"),
    "tight":      ("tight_range",     "Tight Range VCP"),
    "dip":        ("oversold_bounce", "Oversold Bounce"),
}


def _prompt_catalog_answer() -> str:
    import nse_agent

    categories = []
    total = 0
    for category in nse_agent.PROMPT_LIBRARY:
        prompts = category.get("prompts") or []
        total += len(prompts)
        categories.append(f"- {category.get('cat')}: {len(prompts)} prompts")
    return "Prompt catalog validated.\n" + "\n".join(categories) + f"\nTotal prompts: {total}"


def _run_command_case(agent: Agent, case: BenchmarkCase) -> dict[str, Any]:
    text = case.query.strip()
    lower = text.lower()
    if lower == "/model" or lower.startswith("/model "):
        return {"answer": json.dumps(agent.model_status(), indent=2), "trace": [], "intent": "model_status"}
    if lower.startswith("/prompts"):
        return {"answer": _prompt_catalog_answer(), "trace": [], "intent": "prompt_catalog"}
    if lower.startswith("/backtest") or lower.startswith("/strategy-lab"):
        from terminal.backtest import handle_backtest_command

        return {"answer": handle_backtest_command(text), "trace": [], "intent": "backtest_command"}
    if lower.startswith("/strength"):
        from terminal.tools import validate_strength_watchlist

        symbols = [re.sub(r"[^A-Za-z0-9&-]", "", p).upper() for p in text.split()[1:]]
        result = validate_strength_watchlist([s for s in symbols if s])
        return {"answer": json.dumps(result, indent=2, default=str), "trace": [], "intent": "strength_command"}
    if lower.startswith("/report"):
        parts = text.split()
        report_type = parts[1].lower() if len(parts) > 1 else "stage2"
        output_format = parts[2].lower() if len(parts) > 2 else "md"
        if report_type in {"stage2", "sector-rotation"}:
            result = generate_preset_report(report_type, output_format)
            return {"answer": json.dumps(result, indent=2, default=str), "trace": [], "intent": "report_command"}
        return {"answer": "Only preset report commands are run inside this benchmark.", "trace": [], "intent": "report_command"}
    if lower.startswith("/scan"):
        import nse_agent
        from terminal.tools import scan_symbols_intraday

        rewritten, _label = nse_agent._rewrite_scan_command(text)
        screen_match = re.search(r"screener\s+([a-z_]+)", rewritten, flags=re.I)
        screen_type = screen_match.group(1) if screen_match else "momentum"
        strategy_map = {
            "opening_range_breakout": ["ema", "volume"],
            "gap_and_go": ["volume", "macd"],
            "macd_crossover": ["macd"],
            "rsi_divergence": ["rsi", "bollinger"],
            "bb_squeeze": ["bollinger", "volume"],
            "vwap_reclaim": ["ema", "rsi"],
            "momentum": ["macd", "rsi", "supertrend"],
            "vcp": ["vcp", "volume"],
            "supertrend": ["supertrend"],
            "breakouts": ["ema", "volume", "macd"],
        }
        result = scan_symbols_intraday(
            symbols=["RELIANCE"],
            interval="15m",
            strategies=strategy_map.get(screen_type),
            direction_filter="all",
            min_rr=1.0,
            top_n=1,
        )
        answer = json.dumps(result, indent=2, default=str)[:12000]
        return {
            "answer": answer,
            "trace": [{"tool": "scan_symbols_intraday", "args": {"screen_type": screen_type, "symbols": ["RELIANCE"]}, "result": result}],
            "intent": "scan_command",
        }
    if lower.startswith("/screen"):
        from terminal.tools import run_screener_query

        parts = text.split(maxsplit=1)
        arg = parts[1].strip().lower() if len(parts) > 1 else "stage2"
        screen_type, _label = _SCREEN_ALIASES.get(arg, (arg, arg))
        result = run_screener_query(screen_type, top_n=10)
        answer = json.dumps(result, indent=2, default=str)[:12000]
        return {
            "answer": answer,
            "trace": [{"tool": "run_screener_query", "args": {"screen_type": screen_type, "top_n": 10}, "result": result}],
            "intent": "screen_command",
        }
    return agent.query(text, show_trace=True)


def _factual_checks(case: BenchmarkCase, answer: str, trace_summary: dict[str, Any], status: str) -> dict[str, Any]:
    upper_answer = answer.upper()
    lower_answer = answer.lower()
    tools = set(trace_summary.get("unique_tools") or [])
    missing_symbols = [s for s in case.expected_symbols if s.upper() not in upper_answer]
    missing_tools = [t for t in case.required_tools if t not in tools]
    missing_terms = [t for t in case.required_terms if t.lower() not in lower_answer]
    forbidden_hits = [t for t in case.forbidden_terms if t.lower() in lower_answer]
    data_freshness_issue = (
        any(word in case.query.lower() for word in ("current", "live", "intraday", "right now", "latest"))
        and not any(word in lower_answer for word in ("mode:", "clock:", "market:", "fresh", "stale", "snapshot", "unavailable", "fallback"))
    )
    passed = status == "ok" and not (missing_symbols or missing_tools or missing_terms or forbidden_hits or data_freshness_issue)
    return {
        "passed": passed,
        "missing_symbols": missing_symbols,
        "missing_required_tools": missing_tools,
        "missing_required_terms": missing_terms,
        "forbidden_term_hits": forbidden_hits,
        "data_freshness_issue": data_freshness_issue,
    }


def _run_agent_cases(provider: str, model: str, cases: list[BenchmarkCase]) -> dict[str, Any]:
    agent = Agent()
    switch = agent.set_model_backend(provider, model)
    backend_status = agent.model_status()
    backend_status["switch"] = switch

    outputs: list[dict[str, Any]] = []
    total = len(cases)
    for idx, case in enumerate(cases, start=1):
        print(f"[{provider}:{model}] {idx}/{total} {case.case_id} ({case.category})", flush=True)
        start = time.perf_counter()
        try:
            result = _run_command_case(agent, case) if case.mode == "command" else agent.query(case.query, show_trace=True)
            elapsed = time.perf_counter() - start
            answer = result.get("answer", "") or ""
            trace = result.get("trace") or []
            trace_summary = _summarize_trace(trace)
            status = "ok"
            outputs.append(
                {
                    "case_id": case.case_id,
                    "category": case.category,
                    "query": case.query,
                    "notes": case.notes,
                    "mode": case.mode,
                    "model_dependent": case.model_dependent,
                    "status": status,
                    "elapsed_seconds": round(elapsed, 3),
                    "backend": result.get("backend") or backend_status.get("backend"),
                    "intent": result.get("intent"),
                    "answer": answer,
                    "answer_excerpt": answer[:1600],
                    "trace_summary": trace_summary,
                    "answer_metrics": _answer_metrics(answer),
                    "factual_checks": _factual_checks(case, answer, trace_summary, status),
                }
            )
        except Exception as exc:
            elapsed = time.perf_counter() - start
            status = "error"
            outputs.append(
                {
                    "case_id": case.case_id,
                    "category": case.category,
                    "query": case.query,
                    "mode": case.mode,
                    "model_dependent": case.model_dependent,
                    "status": status,
                    "elapsed_seconds": round(elapsed, 3),
                    "backend": backend_status.get("backend"),
                    "error": f"{type(exc).__name__}: {exc}",
                    "factual_checks": _factual_checks(case, "", {}, status),
                }
            )
    return {"provider": provider, "model": model, "backend_status": backend_status, "cases": outputs}


def _run_report_generation() -> dict[str, Any]:
    start = time.perf_counter()
    try:
        result = generate_preset_report("stage2", "md")
        path = result.get("path") or result.get("file") or ""
        content_len = 0
        if path and Path(path).exists():
            content_len = len(Path(path).read_text(encoding="utf-8", errors="ignore"))
        return {
            "status": "ok",
            "elapsed_seconds": round(time.perf_counter() - start, 3),
            "report_type": "stage2",
            "format": "md",
            "path": path,
            "content_chars": content_len,
            "result": result,
        }
    except Exception as exc:
        return {
            "status": "error",
            "elapsed_seconds": round(time.perf_counter() - start, 3),
            "report_type": "stage2",
            "format": "md",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _run_code_assimilation_checks() -> dict[str, Any]:
    targets = [
        ROOT / "terminal" / "reports.py",
        ROOT / "reports" / "enhanced_comprehensive_analysis.py",
        ROOT / "company_intelligence_search.py",
    ]
    files: list[dict[str, Any]] = []
    for path in targets:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            files.append(
                {
                    "path": str(path),
                    "exists": True,
                    "chars": len(text),
                    "functions": len(re.findall(r"^def\s+", text, flags=re.M)),
                    "classes": len(re.findall(r"^class\s+", text, flags=re.M)),
                    "mentions_openai": "openai" in text.lower(),
                    "mentions_report": "report" in text.lower(),
                }
            )
        except FileNotFoundError:
            files.append({"path": str(path), "exists": False})
    return {"status": "ok", "files": files}


def _compact_case_for_eval(case: dict[str, Any]) -> dict[str, Any]:
    answer = case.get("answer", "")
    return {
        "case_id": case.get("case_id"),
        "category": case.get("category"),
        "query": case.get("query"),
        "status": case.get("status"),
        "elapsed_seconds": case.get("elapsed_seconds"),
        "backend": case.get("backend"),
        "intent": case.get("intent"),
        "trace_summary": case.get("trace_summary"),
        "answer_metrics": case.get("answer_metrics"),
        "factual_checks": case.get("factual_checks"),
        "answer_excerpt": answer[:900],
        "error": case.get("error"),
    }


def _evaluate_with_gpt55(payload: dict[str, Any], evaluator_model: str) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("SHUNYAAI_OPENAI_API_KEY")
    if not api_key:
        return {"status": "skipped", "reason": "OPENAI_API_KEY not set"}
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        eval_payload = {
            "openai": [_compact_case_for_eval(c) for c in payload["runs"]["openai"]["cases"]],
            "ollama": [_compact_case_for_eval(c) for c in payload["runs"]["ollama"]["cases"]],
            "report_generation": payload.get("report_generation"),
        }
        prompt = (
            "You are evaluating Agent Adda model-backend benchmark results. "
            "Compare OpenAI gpt-4o and Ollama granite4:latest on application behavior: "
            "tool discipline, evidence transparency, instruction following, market reasoning, "
            "risk handling, context management, factual data checks, report generation, and output usability. "
            "Return strict JSON with keys: overall_winner, executive_summary, case_scores, "
            "strengths, weaknesses, tool_call_findings, context_findings, report_generation_findings, "
            "factual_accuracy_findings, command_coverage_findings, recommended_backend_policy, remediation_backlog. "
            "Do not return an empty JSON object. If a section has limited evidence, still fill it with concise findings. "
            "Scores must be 1-5. Penalize fabricated data, missing source trails, tool failures, "
            "missing factual checks, wrong symbols, treating common words as symbols, and weak code/report assimilation."
        )
        completion_args = {
            "model": evaluator_model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(eval_payload, ensure_ascii=False)},
            ],
        }
        if evaluator_model.startswith("gpt-5"):
            completion_args["max_completion_tokens"] = 8000
        else:
            completion_args["max_tokens"] = 3500
            completion_args["temperature"] = 0
        response = client.chat.completions.create(**completion_args)
        text = response.choices[0].message.content or "{}"
        evaluation = json.loads(text)
        if not evaluation:
            return {"status": "error", "model": evaluator_model, "error": "Evaluator returned empty JSON object"}
        return {"status": "ok", "model": evaluator_model, "evaluation": evaluation}
    except Exception as exc:
        return {"status": "error", "model": evaluator_model, "error": f"{type(exc).__name__}: {exc}"}


def _heuristic_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for name, run in payload["runs"].items():
        cases = run.get("cases", [])
        ok = [c for c in cases if c.get("status") == "ok"]
        tool_counts = [c.get("trace_summary", {}).get("tool_count", 0) for c in ok]
        words = [c.get("answer_metrics", {}).get("words", 0) for c in ok]
        errors = [c for c in cases if c.get("status") != "ok"]
        summary[name] = {
            "ok_cases": len(ok),
            "error_cases": len(errors),
            "avg_elapsed_seconds": round(sum(c.get("elapsed_seconds", 0) for c in cases) / max(len(cases), 1), 3),
            "avg_tool_calls": round(sum(tool_counts) / max(len(tool_counts), 1), 2),
            "avg_words": round(sum(words) / max(len(words), 1), 1),
            "cases_with_source_trail": sum(1 for c in ok if c.get("answer_metrics", {}).get("mentions_source_trail")),
            "cases_with_missing_data_flag": sum(1 for c in ok if c.get("answer_metrics", {}).get("mentions_missing_data")),
            "factual_check_passes": sum(1 for c in ok if c.get("factual_checks", {}).get("passed")),
            "factual_check_failures": sum(1 for c in ok if not c.get("factual_checks", {}).get("passed")),
            "errors": [c.get("error", "") for c in errors],
        }
    return summary


def _render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []

    def append_value(value: Any) -> None:
        if isinstance(value, str):
            lines.append(value or "n/a")
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, (dict, list)):
                    lines.append("- `" + json.dumps(item, ensure_ascii=False) + "`")
                else:
                    lines.append(f"- {item}")
        elif isinstance(value, dict):
            lines.append("```json")
            lines.append(json.dumps(value, indent=2, ensure_ascii=False))
            lines.append("```")
        elif value is None:
            lines.append("n/a")
        else:
            lines.append(str(value))

    lines.append("# Agent Adda Model Benchmark Report")
    lines.append("")
    lines.append(f"Generated: `{payload['generated_at']}`")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append(
        "This benchmark compares the main Agent Adda chat backend between OpenAI `gpt-4o` "
        "and Ollama `granite4:latest`. Voice STT/TTS models are excluded."
    )
    lines.append("")
    lines.append("## Backend Status")
    lines.append("")
    lines.append("| Backend | Status | Model | Switch Result |")
    lines.append("|---|---|---|---|")
    for name, run in payload["runs"].items():
        status = run.get("backend_status", {})
        switch = status.get("switch", {})
        lines.append(
            f"| {name} | {status.get('backend', 'n/a')} | {status.get('model', 'n/a')} | {switch.get('status', 'n/a')} |"
        )
    lines.append("")
    lines.append("## Heuristic Metrics")
    lines.append("")
    lines.append("| Backend | OK Cases | Error Cases | Avg Time | Avg Tool Calls | Avg Words | Source Trail Cases | Missing Data Flags | Factual Pass | Factual Fail |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for name, metrics in payload["heuristic_summary"].items():
        lines.append(
            f"| {name} | {metrics['ok_cases']} | {metrics['error_cases']} | "
            f"{metrics['avg_elapsed_seconds']}s | {metrics['avg_tool_calls']} | "
            f"{metrics['avg_words']} | {metrics['cases_with_source_trail']} | "
            f"{metrics['cases_with_missing_data_flag']} | {metrics['factual_check_passes']} | "
            f"{metrics['factual_check_failures']} |"
        )
    lines.append("")
    lines.append("## Case Results")
    lines.append("")
    lines.append("| Case | Category | OpenAI Status / Tools / Factual / Time | Ollama Status / Tools / Factual / Time |")
    lines.append("|---|---|---|---|")
    openai_cases = {c["case_id"]: c for c in payload["runs"]["openai"]["cases"]}
    ollama_cases = {c["case_id"]: c for c in payload["runs"]["ollama"]["cases"]}
    for case_id, oc in openai_cases.items():
        lc = ollama_cases.get(case_id, {})
        ot = oc.get("trace_summary", {}).get("tool_count", 0)
        lt = lc.get("trace_summary", {}).get("tool_count", 0)
        of = "pass" if oc.get("factual_checks", {}).get("passed") else "fail"
        lf = "pass" if lc.get("factual_checks", {}).get("passed") else "fail"
        lines.append(
            f"| `{case_id}` | {oc.get('category')} | {oc.get('status')} / {ot} / {of} / {oc.get('elapsed_seconds')}s | "
            f"{lc.get('status')} / {lt} / {lf} / {lc.get('elapsed_seconds')}s |"
        )
    lines.append("")
    lines.append("## Factual Check Failures")
    lines.append("")
    for backend_name, cases_by_id in (("openai", openai_cases), ("ollama", ollama_cases)):
        failures = [c for c in cases_by_id.values() if not c.get("factual_checks", {}).get("passed")]
        lines.append(f"### {backend_name}")
        lines.append("")
        if not failures:
            lines.append("- No factual check failures.")
        for case in failures[:25]:
            checks = case.get("factual_checks", {})
            detail = {
                "missing_symbols": checks.get("missing_symbols"),
                "missing_required_tools": checks.get("missing_required_tools"),
                "missing_required_terms": checks.get("missing_required_terms"),
                "forbidden_term_hits": checks.get("forbidden_term_hits"),
                "data_freshness_issue": checks.get("data_freshness_issue"),
                "error": case.get("error"),
            }
            lines.append(f"- `{case.get('case_id')}`: `{json.dumps(detail, ensure_ascii=False)}`")
        lines.append("")
    lines.append("## Report Generation")
    lines.append("")
    report = payload.get("report_generation", {})
    if report.get("status") == "ok":
        lines.append(
            f"- Stage 2 Markdown report generated in `{report.get('elapsed_seconds')}s` at `{report.get('path')}` "
            f"with `{report.get('content_chars')}` characters."
        )
    else:
        lines.append(f"- Report generation failed: `{report.get('error')}`")
    lines.append("")
    code_checks = payload.get("code_assimilation_checks", {})
    if code_checks:
        lines.append("## Code Assimilation Checks")
        lines.append("")
        lines.append("| File | Exists | Chars | Functions | Classes | Mentions Report | Mentions OpenAI |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for item in code_checks.get("files", []):
            lines.append(
                f"| `{item.get('path')}` | {item.get('exists')} | {item.get('chars', 0)} | "
                f"{item.get('functions', 0)} | {item.get('classes', 0)} | "
                f"{item.get('mentions_report', False)} | {item.get('mentions_openai', False)} |"
            )
        lines.append("")
    lines.append("## GPT-5.5 Evaluation")
    lines.append("")
    evaluator = payload.get("gpt55_evaluation", {})
    if evaluator.get("status") == "ok":
        evaluation = evaluator.get("evaluation", {})
        lines.append(f"- Evaluator model: `{evaluator.get('model')}`")
        lines.append(f"- Overall winner: `{evaluation.get('overall_winner', 'n/a')}`")
        lines.append("")
        lines.append("### Executive Summary")
        lines.append("")
        append_value(evaluation.get("executive_summary", "n/a"))
        lines.append("")
        for section in (
            "strengths",
            "weaknesses",
            "tool_call_findings",
            "context_findings",
            "report_generation_findings",
            "factual_accuracy_findings",
            "command_coverage_findings",
            "recommended_backend_policy",
            "remediation_backlog",
        ):
            value = evaluation.get(section)
            lines.append(f"### {section.replace('_', ' ').title()}")
            lines.append("")
            append_value(value)
            lines.append("")
        lines.append("### Case Scores")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(evaluation.get("case_scores", {}), indent=2, ensure_ascii=False))
        lines.append("```")
    else:
        lines.append(f"- GPT-5.5 evaluation status: `{evaluator.get('status')}`")
        if evaluator.get("error"):
            lines.append(f"- Error: `{evaluator.get('error')}`")
        if evaluator.get("reason"):
            lines.append(f"- Reason: `{evaluator.get('reason')}`")
    lines.append("")
    lines.append("## Raw Output Location")
    lines.append("")
    lines.append(f"- JSON: `{payload.get('json_path', 'written next to this report')}`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Agent Adda model backends.")
    parser.add_argument("--openai-model", default="gpt-4o")
    parser.add_argument("--ollama-model", default="granite4:latest")
    parser.add_argument("--evaluator-model", default="gpt-5.5")
    parser.add_argument("--skip-evaluator", action="store_true")
    parser.add_argument("--input-json", default="", help="Reuse an existing benchmark JSON and rerun report/evaluator only.")
    parser.add_argument("--output-dir", default=str(ROOT / "reports" / "model_benchmarks"))
    parser.add_argument("--suite", choices=("standard", "complex", "all"), default="standard")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.input_json:
        payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
        payload["rerendered_at"] = datetime.now().isoformat(timespec="seconds")
    else:
        if args.suite == "complex":
            all_cases = _complex_cases()
        elif args.suite == "all":
            all_cases = _all_cases() + _complex_cases()
        else:
            all_cases = _all_cases()
        payload: dict[str, Any] = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "benchmark_design": "docs/superpowers/specs/2026-05-12-agent-model-benchmark-design.md",
            "suite": args.suite,
            "scenario_count": len(all_cases),
            "runs": {
                "openai": _run_agent_cases("openai", args.openai_model, all_cases),
                "ollama": _run_agent_cases("ollama", args.ollama_model, all_cases),
            },
            "report_generation": _run_report_generation(),
            "code_assimilation_checks": _run_code_assimilation_checks(),
        }
        payload["heuristic_summary"] = _heuristic_summary(payload)
    if args.skip_evaluator:
        payload["gpt55_evaluation"] = {"status": "skipped", "reason": "--skip-evaluator"}
    else:
        payload["gpt55_evaluation"] = _evaluate_with_gpt55(payload, args.evaluator_model)

    json_path = out_dir / f"agent_model_benchmark_{timestamp}.json"
    md_path = out_dir / f"agent_model_benchmark_{timestamp}.md"
    payload["json_path"] = str(json_path)
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md_path.write_text(_render_markdown(payload), encoding="utf-8")

    print(f"JSON: {json_path}")
    print(f"Report: {md_path}")
    print(json.dumps(payload["heuristic_summary"], indent=2, ensure_ascii=False))
    evaluator = payload.get("gpt55_evaluation", {})
    print(f"GPT-5.5 evaluator: {evaluator.get('status')}")
    if evaluator.get("error"):
        print(f"GPT-5.5 evaluator error: {evaluator['error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
