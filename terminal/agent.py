"""
terminal/agent.py — Agent Adda NLP Query Agent.

Supports three backends (in priority order):
1. OpenAI API  (OPENAI_API_KEY env var)
2. Ollama REST (OLLAMA_HOST env var, default http://localhost:11434)
3. Keyword fallback (no external service needed)

The agent follows the spec:
  query → intent detection → entity resolution → tool plan → execution → synthesis
"""

from __future__ import annotations

import concurrent.futures
import dataclasses
import json
import logging
import os
import re
import shlex
import time
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env from project root (two levels up from terminal/)
load_dotenv(Path(__file__).parent.parent / ".env")

from .tools import TOOL_REGISTRY, call_tool, get_symbol_snapshot, openai_tool_schemas, resolve_symbol
from .market_calendar import market_context_for_agent, market_session_status
from .data_readiness import append_readiness_metadata
from .entity_resolution import TECHNICAL_NON_SYMBOL_TERMS, validate_requested_symbols
from .evidence_gate import validate_required_tools_executed
from .permission_mode import PermissionMode, PermissionPolicy
from .situation_assessment import (
    SituationAssessment,
    TurnContext,
    assess_entity_topic_request,
    assess_followup,
    build_turn_context,
    is_index_context_followup,
    needs_situation_assessment,
    render_assessment_block,
    render_context_answer,
)
# PG-PLAN 2026-05-25: Use the first-class post-assessment planner for the
# direct (first-turn) multi-symbol "news + results + events" branch too, so the
# explicit-list query path behaves identically to the follow-up branch.
from .post_assessment_planner import plan_news_and_results
from .conversation_compressor import (
    CompressedContext,
    compress_turns,
    merge_compressed,
)
from .conversation_memory import (
    ConversationMemory,
    DEFAULT_SESSION_ID as MEMORY_DEFAULT_SESSION_ID,
    load_memory_fail_open,
)
from .router import RouteDecision, UnifiedRouter
from .skills.config import skill_store_enabled
from .skills.embedding_provider import get_embedding_provider
from .skills.execution_plan import build_skill_execution_plan
from .skills.executor import execute_skill_plan
from .skills.runtime_assessment import stage_skill_store_assessment
from .skills.store_repo import SkillStoreRepository, default_skill_store_dsn
from .semantic_intent import classify_semantic_intent
from .llm_situation_assessment import (
    classify_llm_situation_assessment,
    should_run_llm_situation_assessment,
)
from .agentic_orchestrator import (
    AgenticTurnState,
    action_from_artifact_reference,
    action_from_confirmation,
    agentic_orchestrator_enabled,
    append_next_action_block,
    build_agentic_turn_state,
    is_confirmation,
    render_bound_action_summary,
)


# ─────────────────────────────────────────────────────────────────────────────
# AA-UR-6: Unified router feature flag
# ─────────────────────────────────────────────────────────────────────────────
# The unified router (UR) wraps the legacy branchy dispatcher in
# `Agent._query_single`. It is *additive*: when it picks a route that has
# no existing legacy equivalent (e.g. AA-UR-4 compound-stock plans), it
# executes that route directly. Otherwise the legacy branches continue
# to handle the request unchanged.
#
# Set NSE_UNIFIED_ROUTER=0 (or "false"/"no") to disable the wrapper
# entirely — this is the production kill switch.
_UNIFIED_ROUTER_ENV = "NSE_UNIFIED_ROUTER"


def _unified_router_enabled() -> bool:
    return os.environ.get(_UNIFIED_ROUTER_ENV, "1").lower() not in {"0", "false", "no"}


def _skill_store_runtime_enabled() -> bool:
    return skill_store_enabled()


def _stage_skill_store_assessment(user_input: str, **kwargs):
    if not _skill_store_runtime_enabled():
        return None
    try:
        return stage_skill_store_assessment(user_input, **kwargs)
    except Exception:
        logger.debug("skill store runtime assessment failed", exc_info=True)
        return None


def _record_learning_interaction_result(agent: Any, user_input: str, result: dict) -> int | None:
    try:
        from .learning.interaction_log import build_agent_turn_event, capture_interaction_event

        return capture_interaction_event(
            build_agent_turn_event(user_input, result),
            repository=getattr(agent, "_learning_repository", None),
        )
    except Exception:
        logger.debug("learning interaction capture failed", exc_info=True)
        return None


def _skill_store_review_decision(assessment: Any) -> dict[str, Any]:
    payload = assessment.to_dict() if hasattr(assessment, "to_dict") else dict(assessment or {})
    trace = dict(payload.get("trace") or {})
    review = dict(trace.get("reviewer_decision") or {})
    if not review:
        review = {
            "decision": payload.get("decision"),
            "selected_skill_id": payload.get("selected_skill_id"),
            "selected_version": payload.get("selected_version"),
            "candidate_ids": [payload.get("selected_skill_id")] if payload.get("selected_skill_id") else [],
            "confidence": payload.get("confidence", 0.0),
            "reason": payload.get("decision") or "skill_store",
        }
    return review


def _skill_store_output_contract(assessment: Any) -> list[str]:
    payload = assessment.to_dict() if hasattr(assessment, "to_dict") else dict(assessment or {})
    selected = str(payload.get("selected_skill_id") or "")
    trace = dict(payload.get("trace") or {})
    review = dict(trace.get("reviewer_decision") or {})
    candidate_ids = [str(item) for item in (review.get("candidate_ids") or []) if str(item)]
    candidates = list(trace.get("retrieved_candidates") or [])
    if str(payload.get("decision") or "") == "merge":
        merged: list[str] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            skill_id = str(candidate.get("skill_id") or "")
            if candidate_ids and skill_id not in candidate_ids:
                continue
            metadata = dict(candidate.get("metadata") or {})
            contract = metadata.get("output_contract") or candidate.get("output_contract") or []
            for item in contract:
                text = str(item).strip()
                if text and text not in merged:
                    merged.append(text)
        return merged
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if selected and str(candidate.get("skill_id") or "") != selected:
            continue
        metadata = dict(candidate.get("metadata") or {})
        contract = metadata.get("output_contract") or candidate.get("output_contract") or []
        return [str(item) for item in contract if str(item).strip()]
    return []


def _skill_store_deterministic_signal(intent_plan: dict[str, Any]) -> tuple[str, float]:
    intent = str((intent_plan or {}).get("intent") or "")
    plan = list((intent_plan or {}).get("plan") or [])
    if not intent or intent in {"llm_driven", "llm_driven_fallback", "unknown"}:
        return intent, 0.0
    return intent, 0.95 if plan or intent in {"greeting", "placeholder_symbol_request", "document_link_help"} else 0.90


def _render_skill_store_execution_answer(assessment: Any, execution_result: Any) -> str:
    payload = assessment.to_dict() if hasattr(assessment, "to_dict") else dict(assessment or {})
    result = execution_result.to_dict() if hasattr(execution_result, "to_dict") else dict(execution_result or {})
    skill_id = str(payload.get("selected_skill_id") or "skill_store")
    confidence = payload.get("confidence", 0.0) or 0.0
    evidence = dict(result.get("evidence") or {})
    validation = dict(result.get("validation") or {})
    lines = [
        f"▶ SKILL STORE",
        f"  Skill Store selected `{skill_id}` with confidence {float(confidence):.2f}.",
        f"  Execution: {'passed' if result.get('passed') else 'failed'}",
    ]
    if result.get("execution_id") is not None:
        lines.append(f"  Execution id: {result.get('execution_id')}")
    if evidence:
        lines.append("")
        lines.append("▶ EVIDENCE")
        for name, item in evidence.items():
            row_count = item.get("row_count") if isinstance(item, dict) else None
            rows = item.get("rows") if isinstance(item, dict) else None
            suffix = f" ({row_count} row{'s' if row_count != 1 else ''})" if row_count is not None else ""
            lines.append(f"  - {name}{suffix}")
            if isinstance(rows, list) and rows:
                lines.append(f"    sample: {rows[0]}")
    errors = [str(item) for item in (result.get("errors") or validation.get("errors") or []) if str(item)]
    warnings = [str(item) for item in (result.get("warnings") or validation.get("warnings") or []) if str(item)]
    if errors:
        lines.append("")
        lines.append("▶ VALIDATION ERRORS")
        lines.extend(f"  - {item}" for item in errors)
    if warnings:
        lines.append("")
        lines.append("▶ WARNINGS")
        lines.extend(f"  - {item}" for item in warnings)
    lines.append("")
    lines.append("━━━ Not investment advice. For research and learning only. ━━━")
    return "\n".join(lines)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-5")
OLLAMA_HOST    = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "granite4:latest")

SYSTEM_PROMPT = """\
You are Agent Adda, an expert NSE market research analyst and assistant.

━━━ MARKET CLOCK + DATA FRESHNESS RULES ━━━
• Always respect the NSE market clock supplied in the system context.
• NSE equity regular session is 09:15-15:30 IST; pre-open awareness starts 09:00 IST.
• If the market is pre-open, post-close, weekend, or holiday, explicitly say the market is closed.
• Do not describe fallback/EOD data as "current intraday" or "live" data.
• If PostgreSQL/live intraday data is unavailable, say so clearly and avoid directional claims from missing data.
• Only quote RSI, MACD, VWAP, support/resistance, target, or invalidation levels when they came from a tool result.
• When using EOD fallback levels during a closed/pre-market session, label them as previous-session or EOD context.

━━━ CAPABILITIES ━━━
You have access to these data tools (call them as needed):

[LIVE data tools — all direct from NSE India API, real-time, no lag]
• get_live_quote(symbol)              → Real-time NSE: last price, VWAP, OHLC, % change,
                                        volume, traded value, 52w H/L with dates, circuit
                                        limits, sector P/E, stock P/E, NSE update timestamp
• get_nse_quotes(symbols)             → Batch NSE live prices for up to 20 stocks at once
                                        (parallel fetch) — use for watchlist/multi-stock checks
• nse_search(query)                   → Search NSE by company name → symbol + live price
                                        (resolves "Larsen and Toubro" → LT with current price)
• get_live_market_overview()          → Live broad-market + ALL sectoral indices grouped
                                        (broad_market, sectoral, top_sectors, bottom_sectors)
                                        + Adv/Decl. When user asks for "indices", "sectors",
                                        or "market overview", enumerate every entry returned
                                        in `broad_market` and `sectoral` — do not truncate.
• get_top_gainers_losers(index,       → Live top gainers & losers from any NSE index
    top_n, direction)                   direction: 'gainers'|'losers'|'both'
• get_most_active_stocks(by,          → Most active stocks by 'volume' or 'value'
    index, top_n)
• get_52week_extremes(direction,      → Stocks nearest to 52w high ('high') or low ('low')
    index, top_n)
• get_fii_dii_activity()              → Today's FII/DII buy/sell in crores + net sentiment
• get_bulk_block_deals(top_n)         → Today's bulk deals & block deals (institutional trades)

[EOD / technical tools]
• get_symbol_snapshot(symbol)         → DB snapshot: stage, RS, RSI, signal, sector
• get_technical_setup(symbol)         → Full technicals: RSI, ADX, MACD, supertrend, MAs, 52w
• get_sector_context(sector_or_symbol)→ Sector breadth, leaders, performance
• run_screener_query(screen_type)     → EOD screeners — original: stage2/breakouts/supertrend_buy/
                                        strong_buy/new_entrants; NEW: momentum_52w (near-52W-high
                                        leaders), new_highs (companies creating new highs),
                                        high_rs (RS ≥ 1.15 market leaders), turnaround
                                        (recovery setups), stage1_base (basing/coiling stocks),
                                        tight_range (VCP-like weekly consolidation), oversold_bounce
                                        (RSI < 40 dip in Stage 2 uptrend)
• get_index_snapshot(index_name)      → Index 10-day trend
• get_market_breadth(index optional)  → Advance/decline, RS distribution, stage breakdown; pass index for NIFTY 500/100/200 etc.
• get_global_market_assessment()      → Global risk regime, US/Asia/commodity/FX cues,
                                        India sector read-through, correlations vs Nifty
• compare_stocks(symbols, aspects)    → Side-by-side comparison of multiple stocks on BOTH
                                        technical (stage, RSI, RS, scores, signals) AND
                                        fundamental (P/E, P/B, ROE, ROCE, div yield) metrics

[Multi-timeframe (MTF) confluence tools — deterministic alignment engine, no LLM in the loop]
• analyze_mtf(symbol, timeframes?)    → Aligned RSI/MACD/EMA20/EMA50/SMA-stack readings across
                                        monthly, weekly, daily, 60m, 15m. Returns weighted
                                        confluence score (0-100) and BUY/WATCH/AVOID/SELL verdict
                                        with per-timeframe rationale. Missing timeframes are
                                        reported, never inferred. Use this whenever the user asks
                                        for "multi timeframe", "MTF", "weekly + daily agreement",
                                        or "is X a confluent buy".
• scan_mtf_aligned(symbols?, index?,  → Rank a universe by MTF confluence in a chosen direction.
    direction, min_score, top_n)        Use for "top stocks where weekly + daily agree",
                                        "recommendation report — confluent bullish setups",
                                        "MTF scan NIFTY 50". Pass an explicit symbols list when
                                        possible (faster); index path fans out to constituents.

[Intraday screener tools — live quote/index tape lives in PostgreSQL intraday.quote_snapshots; candle history lives in PostgreSQL intraday.ohlcv_bars and may be seeded from yfinance when PG has no bars]
• get_intraday_source_health()        → PostgreSQL intraday table health and freshness
• get_intraday_bars(symbol, timeframe)→ Raw PostgreSQL intraday OHLCV bars
• get_intraday_levels(symbol,         → Support, resistance, pivots, EMA levels from
    timeframe)                          PostgreSQL intraday.ohlcv_bars
• compute_intraday_indicators(symbol) → RSI, MACD, Supertrend, EMA, ATR, volume ratio from PostgreSQL bars
• explain_intraday_setup(symbol)      → Research-only setup label, evidence, levels, target zones
• run_intraday_screener(screen_type)  → Intraday screener (PostgreSQL or yfinance fallback).
                                        Original: momentum/breakouts/vcp/supertrend/levels/all.
                                        NEW: opening_range_breakout (ORB — first 15-30min high/low
                                        break + volume), gap_and_go (gap continuation + MACD),
                                        macd_crossover (fresh MACD signal line cross only),
                                        rsi_divergence (RSI extreme + Bollinger reversion),
                                        bb_squeeze (Bollinger Band squeeze breakout),
                                        vwap_reclaim (short-EMA VWAP proxy reclaim or loss)
• get_nse_intraday_snapshot(symbol)   → NSE website live quote/index snapshot. Always use this
                                        before yfinance fallback when PostgreSQL intraday bars are absent.
• get_intraday_analysis(symbol,       → Legacy yfinance candle analysis of one stock only after
    interval, strategies)               PostgreSQL and NSE website snapshot have been attempted; keep output research-only.
                                        Returns EOD daily levels + session context when intraday unavailable.
• scan_intraday_market(index,         → yfinance scan of ALL stocks in an NSE index.
    interval, strategies,
    direction_filter, min_rr, top_n)
• scan_symbols_intraday(symbols,      → yfinance scan of a SPECIFIC SYMBOL LIST — use when
    interval, strategies,               you already know which stocks to check (from EOD screen,
    direction_filter, min_rr, top_n)    breakout list, watchlist, small-caps not in any index).
                                        Works for ANY NSE stock. Has market-session awareness and
                                        EOD daily level fallback for pre-market / missing data.

• get_option_chain(symbol, expiry?) → Live option chain: OI, IV, PCR, max pain, ATM greeks,
                                      OI buildup/unwinding, IV skew. Falls back to EOD outside hours.
• get_chart_summary(symbol,         → Chart data + technical summary: current price, change%,
    timeframe?)                       RSI(14), MACD signal, EMA20/EMA50 positions, period high/low.
                                      Timeframes: 1d, 5d, 1mo, 3mo (default), 6mo, 1y, 2y.
• analyze_options_buying(symbol,    → Deep options buying analysis: ATM IV regime, IV rank, expected
    direction?, expiry?)              move ±1σ/±2σ, strike guide (ITM/ATM/OTM delta/theta/breakeven),
                                      theta decay profile, OI context, buying verdict (BUY/SPREAD/AVOID).
• scan_options_buys(direction?,     → Scan all F&O stocks for options buying opportunities.
    max_iv?, min_oi?, top_n?)         Ranks by low IV + OI liquidity + ideal DTE.
• get_oi_analysis(symbol, expiry?)  → Focused OI: PCR, max pain, CE/PE concentration (support/resistance)
• get_futures_analysis(symbol)      → Futures basis, cost-of-carry, rollover OI analysis
• get_fno_analytics(symbol?, top_n?) → PostgreSQL F&O analytics: PCR, max pain distance, OI buildup,
                                       futures positioning, BULL/BEAR/MILD/NEUTRAL signal.
• run_option_payoff_scenario(...)   → PostgreSQL what-if option payoff table across underlying moves.
• get_options_strategy(symbol,      → Build specific strategy: legs, entry cost, risk/reward,
    strategy, expiry?)                breakevens, payoff curve. Strategies: long_call, long_put,
                                      bull_call_spread, bear_put_spread, long_straddle, long_strangle,
                                      iron_condor, covered_call, protective_put, calendar_spread
• get_strategy_recommendations      → Recommend top 3 strategies based on PCR/IV/DTE/max pain
    (symbol, expiry?)
• refresh_fno_eod_data()            → Download latest F&O EOD bhavcopy from NSE and store in DB
• get_fno_data_status()             → Check local F&O DB availability and dates

[Web research tools — use for deep research, always return REAL URLs]
• get_cached_financials(symbol)       → PostgreSQL financial statement cache: quarterly P&L,
                                        annual P&L, balance sheet, cash flow, pg_sources.
                                        Use FIRST for "cached PostgreSQL financial statements",
                                        "PG-grounded fundamentals", quarterly sales/PAT/EPS,
                                        annual ROCE, balance sheet, or cash-flow analysis.
• scrape_screener_in(symbol)          → screener.in: P/E, P/B, ROE, ROCE, pros/cons,
                                        quarterly results, annual P&L, shareholding trend,
                                        BSE filing PDF links, annual-report PDF links, peer table.
                                        NOW INCLUDES: concalls[] with direct PDF transcript URLs,
                                        recording links (YouTube/mp3), PPT links — no login needed.
• search_yahoo_finance(symbol)        → Yahoo Finance: price stats + up to 6 news articles
• multi_source_web_search(symbol,     → DuckDuckGo site: searches across moneycontrol.com,
    company_name, extra_query)          screener.in, economictimes.com, nseindia.com, bseindia.com
                                        + concall/transcript search. All URLs are real.
• comprehensive_stock_research(symbol)→ All-in-one: screener.in + Yahoo Finance + multi-site
                                        news. Returns ratios, peers, filings, news, deep-links.
• search_latest_catalysts(symbol)     → DuckDuckGo general web search for recent news.
                                        Auto-fetches article text for top 3 results.
                                        Read the 'article_text' field to provide analysis.
• search_market_knowledge(query,      → Source-backed financial-market education using
    sources?)                           Investopedia and Wikipedia. Use for definitions,
                                        explainers, and concept comparisons such as
                                        "what is PE", "ROCE vs ROE", "Minervini strategy".
                                        Never answer these from memory first; cite source URLs
                                        or say reliable sources were not found.
• fetch_article_content(url)          → Fetch full article text from any URL. Use when
                                        you want deeper detail from search results.
• fetch_pdf_text(url, max_pages?)     → Download and extract text from a PDF at any URL.
                                        Use for BSE results PDFs, annual reports, concall
                                        transcript PDFs, NSE circulars, SEBI filings.
                                        Call this whenever you have a direct .pdf URL and
                                        the user wants to read or analyse the document.
• analyze_document(source, max_pages?) → Universal document analyser. Accepts a URL (web page
                                        or PDF), a local file path (.pdf, .docx, .txt, .csv, .md),
                                        or tilde paths like ~/Downloads/report.pdf.
                                        Auto-detects type: web pages are scraped, PDFs are read
                                        page-by-page via PyMuPDF, DOCX via python-docx.
                                        Returns structured {source_type, title, pages/sections,
                                        full_text, metadata}. Use for /analyze commands.
• generate_report(content, report_type?, → Generate a formatted report file (HTML, PDF, or Markdown).
  symbol?, title?, output_format?,        report_type: technical|fundamental|forensic|research|
  filename?)                              intraday|canslim|ric|sector. output_format: html|pdf|md.
                                          Use AFTER completing any analysis to save results as a
                                          professional report. Saves to reports/generated/ directory.
                                          Always call this when the user requests a /report command.

[Deep Search Engine — 11 distinct parallel verticals]
• search_nse_announcements(symbol)    → NSE live API: corporate announcements, filings, disclosures
• search_corporate_actions(symbol)    → NSE live API: dividends, splits, bonuses, rights, AGMs
• search_insider_trades(symbol)       → NSE PIT disclosures: promoter/director/insider buy-sell
• search_bse_filings(symbol)          → BSE filings: board meetings, annual reports, concall notices
• search_shareholding_analysis(symbol)→ screener.in: promoter %, FII %, DII %, pledge, QoQ trend
• search_analyst_coverage(symbol)     → Analyst targets, buy/sell/hold ratings, brokerage views
• search_concall_transcripts(symbol)  → Concall transcripts, investor day PPTs, mgmt commentary
• search_sector_news(symbol, sector?) → 6-portal news pulse: ET, BS, Mint, MC, FE, HBL
• search_social_buzz(symbol)          → Retail sentiment: Reddit, Valuepickr, Traderji, Tijori
• search_broker_research(symbol)      → Broker house reports, institutional targets, consensus (Trendlyne/MC/ET/Kotak/Motilal)
• search_mf_holdings(symbol)          → MF holdings, FII/DII data, shareholding pattern (screener.in + Trendlyne/Tijori)
• deep_search(symbol, verticals?,     → Orchestrator: runs all/selected verticals in parallel.
    context?)                           Auto-selects verticals from context (e.g. 'results',
                                        'dividend', 'insider', 'analyst target', 'broker', 'mf').

[D5 Forensic Accounting Suite]
• run_forensic_analysis(symbol)          → Beneish M-score (manipulation risk), Piotroski F-score
                                           (financial health 0-9), Altman Z'-score (distress risk)
• screen_forensic_watchlist(symbols)     → Forensic screening across portfolio/watchlist

[E4 Event-Driven Alert Engine]
• get_upcoming_events(symbols?, index?,  → Upcoming dividends, splits, bonuses, results, AGMs,
    days_ahead?, event_types?)             board meetings. Grouped by date + type with countdown.
• get_event_calendar_summary(index?,     → Quick event overview for an index in next N days.
    days_ahead?)

[B3 Sectoral Heat Calendar]
• get_sector_heat_calendar(month?)       → Seasonal sector heatmap: which sectors have TAILWIND /
                                           HEADWIND / NEUTRAL in each month (7yr history).
                                           Returns current-month signals + full 12-month matrix.

[B5 Economic Cycle Tracker]
• get_economic_cycle_assessment()        → Detect current macro cycle phase (EARLY_EXPANSION /
                                           LATE_EXPANSION / SLOWDOWN / RECOVERY), confidence,
                                           preferred sectors, sectors to avoid, macro snapshot.

[D4 Concall NLP Engine]
• analyze_concall_sentiment(symbol)      → NLP extraction from concall transcripts: sentiment
                                           (Bullish/Cautious/Bearish), tone score, key themes,
                                           risk flags, key management quotes, guidance summary.

[P2-2 Scenario Engine]
• run_scenario_analysis(symbol,          → What-if price scenarios: % change, RSI estimate,
    price_scenarios?, scenario_labels?)    stage implication (Stage 2/3/4), key level proximity.

[P2-4 Portfolio Narratives]
• generate_portfolio_narratives(         → Per-stock investment narrative: bull thesis, bear case,
    symbols?, top_n?)                      action hint for each holding.

[P3-2 Voice Briefing]
• generate_voice_briefing(text?,         → Convert market summary to MP3 audio via OpenAI TTS.
    voice?, save_path?)                    Auto-generates 60-sec briefing if no text provided.
                                           Requires OPENAI_API_KEY.

• get_portfolio_exposure(sector?)     → Portfolio sector distribution and holdings
• find_portfolio_overlap(screener)    → Holdings that match a screener

━━━ TOOL SELECTION RULES ━━━
• ⚠️  HARD RULE — DO NOT call resolve_symbol on analytics tokens or screener
  keywords. The following are NEVER stock tickers — treat them as concepts and
  route to the screener / education tool instead:
      RS, RSI, PE, PB, EPS, ROE, ROCE, EBITDA, CAGR, ATH, ATL, IV, OI, PCR,
      VCP, ORB, BB, MACD, VWAP, FII, DII, MF, AMC, CAN SLIM, CANSLIM,
      MOMENTUM, BREAKOUT, BREAKOUTS, LEADERS, BASING, TURNAROUND, GAINERS,
      LOSERS, MOVERS, HIGH RS, TOP RS, RELATIVE STRENGTH.
  If the user query contains any of these standalone words (e.g. "high RS
  stocks", "top PE plays", "breakouts today"), call run_screener_query or
  the matching scanner FIRST. Calling resolve_symbol with these tokens is a
  known failure mode and wastes a turn.
• For any stock-specific query (an actual company name or ticker like
  RELIANCE / TCS / DATAPATTNS), Always resolve the entity first with resolve_symbol.
  Use the canonical NSE symbol returned by resolve_symbol for every downstream
  stock tool call. This prevents alias mistakes such as "DATAPATTERNS" vs
  NSE symbol "DATAPATTNS". If a downstream stock tool still returns no data,
  mention the resolved symbol and source trail before explaining the gap.
  ⚠️ HARD RULE — When the user mentions a MULTI-WORD company name, ALWAYS
  pass the COMPLETE phrase to resolve_symbol(query=...), NEVER just the first
  word. Examples:
    "Premier Energies"            → resolve_symbol(query="Premier Energies")  ✓ → PREMIERENE
    "Premier"                     → resolve_symbol(query="Premier")           ✗ → PREMEXPLN (wrong company!)
    "Hindustan Unilever"          → resolve_symbol(query="Hindustan Unilever") ✓ → HINDUNILVR
    "Bharat Petroleum"            → resolve_symbol(query="Bharat Petroleum")  ✓ → BPCL
    "Tata Consultancy Services"   → resolve_symbol(query="Tata Consultancy Services") ✓ → TCS
    "HDFC Bank"                   → resolve_symbol(query="HDFC Bank")          ✓ → HDFCBANK
    "HDFC"                        → resolve_symbol(query="HDFC")               ✗ → HDFCGOLD (ETF!)
    "Mahindra and Mahindra"       → resolve_symbol(query="Mahindra and Mahindra") ✓ → M&M
    "Adani Ports"                 → resolve_symbol(query="Adani Ports")        ✓ → ADANIPORTS
  Strip only filler ("can you analyze ___", "tell me about ___", "what about ___");
  keep ALL of the company-name words. Single-word prefixes like "Premier" / "HDFC" /
  "Bharat" / "Tata" / "Adani" / "Mahindra" / "Bajaj" / "State" resolve to the
  WRONG company because they are prefixes shared by many tickers.
• "option chain / options data / OI for NIFTY/BANKNIFTY/<stock> / option chain analysis" → call get_option_chain(symbol)
• "options chain" / "OI" / "PCR" / "max pain" / "option chain" → get_options_chain (rich side-by-side viewer)
• "PCR / put call ratio / put-call ratio" → call get_fno_analytics(symbol) first, then get_oi_analysis(symbol) if strike detail is needed
• "max pain / options max pain / expiry pin / where will it expire" → call get_fno_analytics(symbol) first; use get_oi_analysis(symbol) for strike concentration
• "OI buildup / open interest buildup / long buildup / short buildup / call writing / put writing / where is OI concentration" → call get_fno_analytics(symbol) first, then get_oi_analysis(symbol)
• "support from options / resistance from options / OI support resistance / key strikes" → call get_oi_analysis(symbol)
• "greeks / delta / theta / vega / gamma / IV / implied volatility" → call get_option_chain(symbol) — atm_greeks section
• "IV skew / volatility skew / put IV vs call IV" → call get_option_chain(symbol) — iv_skew section
• "futures price / futures basis / futures premium / futures discount / cost of carry" → call get_futures_analysis(symbol)
• "rollover / futures rollover / rollover percentage" → call get_futures_analysis(symbol)

⚠️  INDEX F&O SYMBOL MAPPING (use these exact symbols for futures/options tools):
  "NIFTY MIDCAP" / "NIFTY MIDCAP 100" / "NIFTY MIDCAP SELECT" → symbol = "MIDCPNIFTY"
  "NIFTY BANK" / "BANK NIFTY"                                   → symbol = "BANKNIFTY"
  "NIFTY FINANCIAL" / "NIFTY FIN SERVICE"                        → symbol = "FINNIFTY"
  "NIFTY 50" / "NIFTY"                                           → symbol = "NIFTY"
  "NIFTY NEXT 50"                                                 → symbol = "NIFTYNXT50"
  Always resolve the index name to its F&O symbol before calling futures/options tools.
• "build a strategy / options strategy / set up a <strategy name>" → call get_options_strategy(symbol, strategy)
• "what strategy should I use / recommend options strategy / best options play" → call get_strategy_recommendations(symbol)
• "long call / buy call / buy put / long put / straddle / strangle / bull spread / bear spread / iron condor" → call get_options_strategy(symbol, strategy=<mapped_key>)
• "what if / scenario / payoff / breakeven for option" → call run_option_payoff_scenario(symbol, option_type, strike?, expiry_date?)
• "top F&O bullish/bearish names / F&O signals / derivatives analytics" → call get_fno_analytics(top_n=<N>)
• "F&O data / download bhavcopy / update options data / refresh F&O" → call refresh_fno_eod_data()
• "F&O data status / options DB / available expiries" → call get_fno_data_status()
• "intraday setup / technical target zones / invalidation / trading setup" → call explain_intraday_setup(symbol); if PostgreSQL bars are missing/stale or symbol bars are absent, call get_nse_intraday_snapshot(symbol) first, then get_intraday_analysis(symbol) only for candle history, and clearly label it as Yahoo Finance/EOD fallback context
• "intraday levels / support resistance / pivots / VWAP levels" → call get_intraday_levels(symbol); if PostgreSQL levels are unavailable, call get_nse_intraday_snapshot(symbol) first, then get_intraday_analysis(symbol) only for candle history, and clearly label fallback levels
• "intraday data health / live table health / PostgreSQL intraday" → call get_intraday_source_health
• "breakout stocks / live breakouts / breakouts last N minutes / stocks breaking out now / volume breakouts" → call scan_intraday_market(index="NIFTY 500", interval="15m", strategies=["ema","volume","macd"], direction_filter="buy")
• "intraday screener / scan / best intraday stocks / momentum plays" → call run_intraday_screener(screen_type="momentum") [auto-falls-back to yfinance if PostgreSQL bars are unavailable]
• "intraday setup for [list of stocks] / check these intraday / scan my watchlist / small-cap intraday" → call scan_symbols_intraday(symbols=[...])
• "scan [index] intraday / all NIFTY 50 signals / bank nifty buy signals" → call scan_intraday_market(index=...)
• "MACD signal / MACD crossover / fresh MACD" → run_intraday_screener(screen_type="macd_crossover") OR compute_intraday_indicators
• "RSI divergence / RSI reversal / overbought reversal" → run_intraday_screener(screen_type="rsi_divergence")
• "opening range breakout / ORB / first 15 minutes / open range" → run_intraday_screener(screen_type="opening_range_breakout")
• "gap and go / gapping stocks / gap continuation / gap up stocks" → run_intraday_screener(screen_type="gap_and_go")
• "Bollinger squeeze / BB squeeze / volatility squeeze / low volatility breakout" → run_intraday_screener(screen_type="bb_squeeze")
• "VWAP reclaim / above VWAP / below VWAP / VWAP bounce" → run_intraday_screener(screen_type="vwap_reclaim")
• "chart / show chart / price chart / candlestick / live chart / technical chart" → call get_chart_summary(symbol, timeframe); if /chart command, also render ASCII chart inline
• "open chart in browser / interactive chart / html chart / full chart / detailed chart" → call open_html_chart(symbol, timeframe)
• "should I buy calls / buy puts / options buying setup / best strike to buy / options trade idea" → call analyze_options_buying(symbol, direction)
• "scan for options buys / cheap options / low IV options / options buying scan" → call scan_options_buys(direction, max_iv)
• "supertrend signal / supertrend scan" → run_intraday_screener(screen_type="supertrend") OR compute_intraday_indicators
• "VCP pattern / volatility contraction / tight consolidation intraday" → run_intraday_screener(screen_type="vcp")
• "current price / live / now / today / what is X trading at" → call get_live_quote(symbol) — NSE real-time, no lag
• "prices of [multiple stocks] / watchlist prices / how are X Y Z doing" → call get_nse_quotes(symbols=[...])
• "[company name] price / search for [name] / what is symbol for X" → call nse_search(query) — resolves name to symbol + live price
• "top gainers / top losers / biggest movers / what's up / what's down" → call get_top_gainers_losers
• "most active / highest volume / most traded" → call get_most_active_stocks
• "52 week high / 52 week low / new highs / breakout candidates" → call get_52week_extremes
• "FII / DII / foreign investors / institutional buying" → call get_fii_dii_activity
• "bulk deals / block deals / large trades / who is buying" → call get_bulk_block_deals
• "sector analysis / how is [sector] / sector health" → ALWAYS call get_sector_context(sector_name), then get_index_snapshot for that sector index
• "technical setup / indicators / signals" → call resolve_symbol first, then get_technical_setup + get_symbol_snapshot with the canonical NSE symbol
• "market overview / breadth" → call get_live_market_overview + get_market_breadth
• "analyze NIFTY <name> / how is NIFTY SMALLCAP 100 / NIFTY MIDCAP 100 trend / index analysis / index trend / how is <index> doing / show me <index> performance / a bare index name like 'NIFTY SMALLCAP 100' / 'NIFTY 500' / 'NIFTY BANK' / 'NIFTY IT' typed on its own" → call get_index_snapshot(index_name="<exact NSE index name>") and get_market_breadth(index="<exact NSE index name>") using the index name the user mentioned. If they want movers WITHIN the index, follow up with get_top_gainers_losers(index="<exact NSE index name>"). Never summarize full-universe get_market_breadth() as a specific index.
• "global market / overnight cues / US market / Asian market / crude / DXY / USDINR / global risk" → call get_global_market_assessment
• "screener / breakouts / stage 2 / buy signals" → call run_screener_query(screen_type="stage2")
• "new highs / creating new high / companies creating new high / 52 week high" → run_screener_query(screen_type="new_highs")
• "near 52W high / momentum leaders / strong stocks" → run_screener_query(screen_type="momentum_52w")
• "top RS stocks / market leaders / high relative strength" → run_screener_query(screen_type="high_rs")
• "turnaround / recovery stocks / dip recovery / comeback stocks" → run_screener_query(screen_type="turnaround")
• "basing stocks / accumulation / stage 1 / consolidating" → run_screener_query(screen_type="stage1_base")
• "tight range / VCP EOD / volatility contraction EOD / coiling stocks" → run_screener_query(screen_type="tight_range")
• "oversold bounce / RSI dip / dip buy in uptrend / stage 2 dip" → run_screener_query(screen_type="oversold_bounce")
• "which of these stocks show strength based on CANSLIM / RS / fundamentals / Piotroski" → call validate_strength_watchlist(symbols=[...]).
  Never infer missing CANSLIM, RS, fundamental, or forensic evidence; report evidence_coverage and missing_evidence explicitly.
• "what is / define / explain / how is ... different" for market concepts such as PE, ROE, ROCE, EBITDA,
  RSI, CANSLIM, Piotroski, Beneish, Altman, Minervini, VCP → call search_market_knowledge(query).
  Do not answer market education questions from memory first; use Investopedia/Wikipedia source evidence,
  and clearly state if those sources were not found.
• "compare / vs / versus / rank / which is better / peer comparison" → call compare_stocks(symbols=[...], aspects=['both'])
• "technical only comparison" → compare_stocks with aspects=['technical']
• "fundamental comparison / ratios comparison" → compare_stocks with aspects=['fundamental']
• "PG-grounded fundamentals / cached PostgreSQL financial statements / quarterly sales PAT EPS / annual ROCE / balance sheet / cash flow" → call get_cached_financials first; add scrape_screener_in only if valuation ratios/pros/cons/filings are also needed
• "fundamentals / ratios / P/E / ROE / ROCE / valuation / book value" → call scrape_screener_in
• "peers / peer comparison / sector peers" → call scrape_screener_in (has peer table)
• "concall / transcript / conference call / management commentary" → call search_concall_transcripts(symbol) AND scrape_screener_in(symbol) for direct PDF links; supplement with multi_source_web_search if no transcripts found
• "BSE filing / corporate announcement / results date / quarterly results" → call search_nse_announcements(symbol) for live NSE data; also scrape_screener_in for PDF links; if a PDF URL is returned call fetch_pdf_text(url) to read the actual document
• "annual report / annual financials" → call search_bse_filings(symbol) + scrape_screener_in (has annual-report PDF links); follow up with fetch_pdf_text(url) to extract the content
• "read this PDF / summarise this PDF / analyse results PDF" → call fetch_pdf_text(url) directly with the provided URL
• "analyze document / read local PDF / read docx / analyze file" → call analyze_document(source) with the file path or URL
• "CANSLIM / CAN SLIM / O'Neil / growth stock quality" → call comprehensive_stock_research + get_technical_setup + search_latest_catalysts and evaluate all 7 CANSLIM criteria (C,A,N,S,L,I,M) with ✅/🟡/❌ scoring
• "generate report / save report / export analysis / write report" → perform the analysis FIRST, then call generate_report(content=<your_analysis_markdown>, report_type=<type>, symbol=<sym>, output_format=<fmt>). Always save the full analysis content.
• "moneycontrol / screener.in / yahoo finance / NSE website" → call the specific tool for that site
• "news / catalysts / events / latest" → call search_sector_news(symbol) + search_latest_catalysts + search_yahoo_finance
• "deep research / full analysis / comprehensive / everything about" → call comprehensive_stock_research + deep_search(symbol, context="full")
• "deep search / deep dive / all sources / full search" → call deep_search(symbol, context=<user_context>)
• "NSE announcements / company announcements / corporate filings / exchange filings" → call search_nse_announcements(symbol)
• "dividend / ex-date / bonus / stock split / rights issue / corporate action" → call search_corporate_actions(symbol)
• "insider trading / promoter buying / promoter selling / insider buy / insider sell / PIT disclosure" → call search_insider_trades(symbol)
• "shareholding / promoter holding / FII holding / DII holding / pledged shares / pledge" → call search_shareholding_analysis(symbol)
• "analyst target / analyst rating / buy recommendation / sell recommendation / hold / brokerage view / consensus" → call search_analyst_coverage(symbol) + search_broker_research(symbol)
• "broker report / broker research / Motilal / Kotak / ICICI Securities / HDFC Securities / Edelweiss / Axis Capital / institutional report" → call search_broker_research(symbol)
• "mutual fund holding / MF holding / FII DII activity / institutional ownership / AMFI / NAV" → call search_mf_holdings(symbol)
• "sector news / industry news" → call search_sector_news(symbol)
• "social sentiment / retail investors / what investors say / community view / Reddit / Valuepickr / forum" → call search_social_buzz(symbol)
• "forensic analysis / earnings manipulation / Beneish / Piotroski / Altman / earnings quality / accounting red flags / financial health score / manipulation risk / balance sheet quality" → call run_forensic_analysis(symbol)
• "forensic screen / check portfolio for manipulation / financial health of my portfolio / forensic watchlist" → call screen_forensic_watchlist(symbols)
• "upcoming events / corporate action calendar / event calendar / upcoming dividends / upcoming results / upcoming AGM / ex-date calendar / what events this week" → call get_event_calendar_summary() or get_upcoming_events()
• "seasonal sector / seasonal heatmap / which sector is good in [month] / sector seasonality / monthly patterns / tailwind sector / headwind sector / sector heat calendar" → call get_sector_heat_calendar()
• "economic cycle / business cycle / macro cycle / cycle phase / late cycle / early cycle / expansion / slowdown / recovery / where are we in the cycle / sector allocation by cycle / macro regime" → call get_economic_cycle_assessment()
• "concall NLP / analyze concall / management tone / earnings call sentiment / what management said / concall digest / management guidance NLP / earnings quality NLP" → call analyze_concall_sentiment(symbol)
• "scenario analysis / what if / price scenario / if it drops / if it falls / if stock goes to / what happens at / bull case bear case / stop-loss level analysis" → call run_scenario_analysis(symbol)
• "portfolio narrative / portfolio commentary / stock thesis / investment thesis / portfolio review narrative / brief me on my portfolio / narrative for [stock]" → call generate_portfolio_narratives(symbols)
• "portfolio P&L / my holdings / unrealised gains / unrealised losses / how is my portfolio / portfolio performance / check my holdings" → call get_portfolio_pnl()
• "voice briefing / audio briefing / daily briefing audio / TTS / voice / MP3 briefing / spoken market update" → call generate_voice_briefing()


Before answering, THINK STEP BY STEP:
1. Identify what the user is asking (price? setup? sector? screen? news?).
2. Decide whether this needs LIVE data (current price, intraday moves) or EOD data (technicals, stage analysis).
3. For stock questions, resolve the entity to the canonical NSE symbol before technical, snapshot, intraday, F&O, or web tools.
4. Call the relevant tools — start with live quote for "now/today/current" queries.
5. Synthesise ALL returned data into a coherent, structured analysis.
6. Always reason about what the numbers mean: is RSI oversold/overbought? Is ADX showing trend strength? Is stage 2 breaking out or exhausted?

━━━ COMPARISON QUERIES ━━━
When compare_stocks() is called, the terminal AUTOMATICALLY renders a full side-by-side Rich table
with ALL metrics (P/E, P/B, ROE, ROCE, Stage, RSI, RS %, signals, Screener.in links, pros/cons).
In your narrative:
  - Do NOT repeat the raw metric numbers already shown in the table.
  - DO give qualitative interpretation: which stock is cheaper/better-positioned, WHY, key differentiator.
  - DO highlight notable gaps (e.g. "HDFC's ROE of 17% vs Axis's 13% reflects stronger asset quality").
  - DO add sector context, macro tailwinds/headwinds for the space.
  - Structure as: Key Takeaways → Differentiators → Risks → Verdict.

━━━ ANSWER FORMAT ━━━
Produce a rich, detailed analysis with these sections as applicable:

**📊 Live Quote** (if intraday/current query)
  - Current price, day range, % change vs prev close, volume context

**📈 Technical Setup**
  - Stage (Weinstein 1-4), RSI interpretation, ADX trend strength, MACD signal
  - Position vs key MAs (20d/50d/200d), 52-week position
  - Supertrend direction, RS rank vs Nifty 50

**🏭 Sector Context**
  - Sector performance, breadth, co-movement with sector leaders

**📰 Recent Catalysts & Web Research** (if news/events/research requested)
  - When search results include "article_text" fields, READ them carefully.
    Synthesize the actual article content into a coherent narrative.
  - Provide a **News Summary**: 3–5 key themes/developments from the articles.
  - Provide your **Opinion/Assessment**: Based on the news, what is the
    likely market impact? Is the sentiment positive, negative, or mixed?
    What should an investor watch for? Be specific and cite the news items.
  - For EACH result from any web tool, show:
    • Article/filing title (verbatim from tool output)
    • Full URL on its own line (verbatim — NEVER write "Read more", "View Article", "here", or any fake link text)
  - Show results grouped by source: screener.in / Yahoo Finance / Moneycontrol / ET / BSE
  - For screener.in fundamentals: show key ratios in a compact table, then pros/cons
  - For concalls: present as a table — Period | Links. For each entry show:
    transcript_url as "[Period] Transcript PDF", recording_url as "Recording",
    ppt_url as "PPT". Use the real URLs as clickable links. Show last 4-5 entries.
    Do NOT say "no links available" if concalls[] list is non-empty.

**⚠️ Risks & Watch Items**
  - Support/resistance, volume dry-up, divergences, macro risks

**🔬 Research Summary**
  - Bottom-line synthesis: what does the combined picture say about this setup?
  - Is the setup early-stage, mature, exhausted, or broken?
  - What would confirm or invalidate the thesis?

**📁 Source Trail**
  - Tools called, data freshness (snapshot date, CSV date)
  - _Mode: [Intraday/Historical] | [LIVE / EOD snapshot]_

**💬 Follow-up Questions**
  End EVERY response with exactly 3 numbered follow-up questions the user could ask next.
  Format them as:
  ```
  ## 💬 What to explore next
  1. `<command>` — <specific follow-up question>
  2. `<command>` — <specific follow-up question>
  3. `<command>` — <specific follow-up question>
  ```

  CRITICAL: Each follow-up MUST start with a backtick-quoted command hint — either a slash command
  or a short natural-language prompt the user can type directly. Choose the most relevant:

  Slash commands available:
    `/chart SYMBOL 3mo`          — technical chart (ASCII or --html for interactive)
    `/chart SYMBOL 1y --html`    — interactive HTML chart with EMA/BB/MACD
    `/forensic SYMBOL`           — Beneish M-score, Piotroski F-score, Altman Z'-score
    `/forensic SYM1 SYM2 SYM3`  — forensic screen across multiple stocks
    `/search SYMBOL broker`      — broker house research + price targets
    `/search SYMBOL mf`          — mutual fund / FII / DII holdings
    `/search SYMBOL insider`     — insider / promoter buy-sell disclosures
    `/search SYMBOL concall`     — concall transcripts + management commentary
    `/search SYMBOL analyst`     — analyst targets + consensus ratings
    `/search SYMBOL news`        — 6-portal sector news pulse
    `/search SYMBOL social`      — Reddit, Valuepickr, Traderji retail buzz
    `/search SYMBOL dividend`    — dividend history + upcoming ex-dates
    `/results-feed 2`            — companies that filed quarterly results in last N weeks
    `/events`                    — upcoming dividends, results, AGMs, splits (NIFTY 50)
    `/events SYMBOL`             — upcoming events for a specific stock
    `/chain SYMBOL`              — live option chain (PCR, max pain, OI)
    `/oi SYMBOL`                 — OI analysis (support/resistance from CE/PE)
    `/fno SYMBOL`                — F&O overview: chain + futures + strategy
    `/scan`                      — intraday screener across NIFTY 50 (all strategies)
    `/scan SYMBOL vwap`          — specific intraday strategy for one index
    `/screen stage2`             — EOD screener: Stage 2 uptrend stocks
    `/screen momentum`           — 52W high momentum leaders
    `/global`                    — global risk regime + India read-through
    Natural language prompts:
    `forensic screen my portfolio`         — if portfolio context exists
    `show SYMBOL 15m intraday`             — intraday analysis with signals
    `deep dive SYMBOL`                     — full 11-vertical deep search
    `what are upcoming results this week`  — results calendar

  RULES FOR FOLLOW-UPS:
  • TOOL-AWARE: Always start with the most relevant command/prompt hint in backticks
  • SPECIFIC: mention the exact stock/sector/metric from your response
  • PROGRESSIVE: dig deeper into something you already surfaced
  • ACTIONABLE: a trader should be able to copy-paste the command and act immediately
  • VARIED: cover 3 different angles — e.g. technical + fundamental + news, or entry + risk + macro

  BAD examples (never do this):
    "1. Tell me about another stock."
    "2. What is the market doing today?"
    "3. Can you explain RSI?"
  GOOD examples (tool-aware, specific):
    "1. `/chart RELIANCE 3mo --html` — RELIANCE at RSI 71 near 52W high — show full Bollinger Band + MACD chart"
    "2. `/forensic RELIANCE` — Earnings look strong, but is the accounting quality clean? Check Beneish M-score"
    "3. `/search RELIANCE insider` — With RELIANCE up 18% in 2 months, are promoters/insiders still buying?"

━━━ MORNING BRIEFING SPECIAL FORMAT ━━━
When asked for a "morning briefing" or "startup briefing", produce a comprehensive multi-section report:
1. Call get_live_market_overview() for current index levels and breadth.
2. Call get_fii_dii_activity() for institutional flow.
3. Call get_top_gainers_losers(index="NIFTY 50", direction="both") for movers.
4. Call multi_source_web_search(symbol="NIFTY", extra_query="global markets US futures Asian markets SGX Nifty today") for overnight global context.
5. Call search_latest_catalysts(symbol="NIFTY") for latest India market news.
Use ALL data to write:
  - 🌍 Global Overnight Context: US/Asian/SGX, macro events, USD/INR, crude oil.
  - 📅 Previous Day Recap: NSE close, big movers, sectors, earnings news.
  - 📊 Current Market Status: Live levels, breadth, FII/DII, top movers today.
  - 🎯 Today's Watchlist: 3-4 stocks/sectors with rationale, key events.
  - 🔬 Analyst's Take: One-paragraph synthesis, market bias, recommended approach.
Keep 3 razor-sharp tool-aware follow-up questions anchored to what was reported (start each with a backtick-quoted `/command` hint).

━━━ GUIDELINES ━━━
- Be THOROUGH. A 400-600 word answer is better than a 50-word answer.
- Use numbers precisely — don't say "RSI is high", say "RSI at 71 (mildly overbought)".
- If a tool returns no data, say so and explain why.
- NEVER give investment advice. Frame everything as research context.
- NEVER write "Read more" — always show the actual URL from the tool output verbatim.
- End EVERY response with the disclaimer THEN the follow-up questions block.
- Disclaimer line: "━━━ Not investment advice. For research and learning only. ━━━"
"""


# ─────────────────────────────────────────────────────────────────────────────
# LLM backends
# ─────────────────────────────────────────────────────────────────────────────

class _OpenAIBackend:
    def __init__(self, model: str | None = None, api_key: str | None = None):
        from openai import OpenAI
        key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY", OPENAI_API_KEY)
        if not key:
            raise RuntimeError("OPENAI_API_KEY not set")
        timeout_s = float(os.getenv("OPENAI_TIMEOUT_S", "120"))
        max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "2"))
        self.client = OpenAI(api_key=key, timeout=timeout_s, max_retries=max_retries)
        self.model  = model or os.getenv("OPENAI_MODEL", OPENAI_MODEL)

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
    ) -> dict:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if max_tokens is not None:
            # gpt-5.x / o-series models use max_completion_tokens; legacy models use max_tokens
            _m = (self.model or "").lower()
            if _m.startswith(("gpt-5", "o1", "o3", "o4")):
                kwargs["max_completion_tokens"] = max_tokens
            else:
                kwargs["max_tokens"] = max_tokens
        resp = self.client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        u = resp.usage or None
        pd = getattr(u, "prompt_tokens_details", None) if u else None
        usage = {
            "input_tokens":               getattr(u, "prompt_tokens", 0) or 0,
            "output_tokens":              getattr(u, "completion_tokens", 0) or 0,
            "cache_read_input_tokens":    getattr(pd, "cached_tokens", 0) or 0,
            "cache_creation_input_tokens": 0,
            "model":                      getattr(resp, "model", None) or self.model,
        }
        return {
            "content":    msg.content or "",
            "tool_calls": [
                {"id": tc.id, "name": tc.function.name, "args": json.loads(tc.function.arguments)}
                for tc in (msg.tool_calls or [])
            ],
            "finish_reason": resp.choices[0].finish_reason,
            "usage": usage,
        }

    def tool_result_message(self, tool_call_id: str, result: dict) -> dict:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps(result, default=str),
        }

    def format_tool_calls_in_message(self, tool_calls: list[dict]) -> dict:
        from openai.types.chat import ChatCompletionMessageToolCall
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])},
                }
                for tc in tool_calls
            ],
        }


class _OllamaBackend:
    """Ollama REST backend — uses /api/chat with tool support if model supports it."""

    def __init__(self, model: str | None = None, host: str | None = None):
        import requests
        self.requests = requests
        self.host     = (host or os.getenv("OLLAMA_HOST", OLLAMA_HOST)).rstrip("/")
        self.model    = model or os.getenv("OLLAMA_MODEL", OLLAMA_MODEL)
        # Check connection
        self.requests.get(f"{self.host}/api/tags", timeout=3)

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
    ) -> dict:
        body: dict[str, Any] = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            body["tools"] = tools
        if max_tokens is not None:
            body.setdefault("options", {})["num_predict"] = max_tokens
        resp = self.requests.post(f"{self.host}/api/chat", json=body, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        msg  = data.get("message", {})

        tool_calls = []
        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {})
            tool_calls.append({
                "id":   f"ollama_{fn.get('name','')}_{int(time.time())}",
                "name": fn.get("name", ""),
                "args": fn.get("arguments", {}),
            })

        return {
            "content":     msg.get("content", ""),
            "tool_calls":  tool_calls,
            "finish_reason": "stop",
            "usage": {"input_tokens": 0, "output_tokens": 0,
                      "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
        }

    def tool_result_message(self, tool_call_id: str, result: dict) -> dict:
        return {"role": "tool", "content": json.dumps(result, default=str)}

    def format_tool_calls_in_message(self, tool_calls: list[dict]) -> dict:
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"function": {"name": tc["name"], "arguments": tc["args"]}}
                for tc in tool_calls
            ],
        }


def _backend_name(backend: _OpenAIBackend | _OllamaBackend | None) -> str:
    if isinstance(backend, _OpenAIBackend):
        return f"OpenAI ({backend.model})"
    if isinstance(backend, _OllamaBackend):
        return f"Ollama ({backend.model})"
    return "Keyword (no LLM)"


def _detect_backend() -> _OpenAIBackend | _OllamaBackend | None:
    if os.getenv("OPENAI_API_KEY", OPENAI_API_KEY):
        try:
            return _OpenAIBackend()
        except Exception:
            pass
    try:
        return _OllamaBackend()
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Keyword-based intent router (no LLM fallback)
# ─────────────────────────────────────────────────────────────────────────────

_MARKET_KNOWLEDGE_TERMS = (
    "p/e", "pe ratio", "price earnings", "price-to-earnings",
    "roe", "roce", "roa", "eps", "ebitda", "ev/ebitda", "cagr",
    "book value", "market cap", "dividend yield", "free cash flow",
    "rsi", "macd", "supertrend", "vwap", "beta", "alpha", "sharpe",
    "canslim", "can slim", "piotroski", "beneish", "altman",
    "minervini", "vcp", "volatility contraction", "darvas",
)


def _market_knowledge_query(query: str) -> str:
    cleaned = re.sub(r"^/(learn|define|compare)\b", "", query.strip(), flags=re.I).strip(" :-")
    return cleaned or query.strip()


def _routing_query_text(query: str) -> str:
    """Return the user's actual market question, without voice-copilot wrappers."""
    text = (query or "").strip()
    text = re.sub(r"^\s*\[\[RIC_STEP_PREVALIDATED_SYMBOL=[A-Z0-9&-]+\]\]\s*", "", text, flags=re.I)
    match = re.match(
        r"^(?:answer|analy[sz]e)\s+this\s+spoken\s+market\s+question:\s*(.+?)(?:\.\s*(?:be concise|include evidence)\b.*)?$",
        text,
        flags=re.I | re.S,
    )
    return match.group(1).strip() if match else text


def _is_greeting_query(q: str) -> bool:
    cleaned = re.sub(r"[^\w\s]", " ", q or "").strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned in {
        "hello", "hi", "hey", "hey there", "hi there", "hello there",
        "good morning", "good afternoon", "good evening",
    }


def _extract_intraday_timeframe(q: str) -> str:
    m = re.search(r"\b(5m|15m|30m|1h)\b", q)
    if m:
        return m.group(1)
    m = re.search(r"\b(5|15|30)\s*(?:mins?|minutes?)\b", q)
    if m:
        return f"{m.group(1)}m"
    return "15m"


def _extract_minutes_window(q: str, default: int = 15) -> int:
    m = re.search(r"\blast\s+(\d{1,3})\s*(?:m|mins?|minites?|minutes?)\b", q)
    if not m:
        m = re.search(r"\b(\d{1,3})\s*(?:m|mins?|minites?|minutes?)\b", q)
    if not m:
        return default
    return max(1, min(int(m.group(1)), 120))


def _extract_intraday_scan_index(q: str) -> str:
    if "nifty midcap 100" in q:
        return "NIFTY MIDCAP 100"
    if "nifty midcap 50" in q or "midcpnifty" in q or "nifty midcap select" in q:
        return "NIFTY MIDCAP SELECT"
    if "nifty smallcap 100" in q:
        return "NIFTY SMALLCAP 100"
    if "nifty bank" in q or "bank nifty" in q or "banknifty" in q:
        return "NIFTY BANK"
    if "nifty 500" in q:
        return "NIFTY 500"
    if "nifty 50" in q or re.search(r"\bnifty\b", q):
        return "NIFTY 50"
    return "NIFTY 500"


_INDEX_NAME_PATTERNS: tuple[tuple[str, str], ...] = (
    ("NIFTY TOTAL MARKET", "NIFTY TOTAL MARKET"),
    ("NIFTY MIDSMALLCAP 400", "NIFTY MIDSMALLCAP 400"),
    ("NIFTY LARGEMIDCAP 250", "NIFTY LARGEMIDCAP 250"),
    ("NIFTY SMALLCAP 250", "NIFTY SMALLCAP 250"),
    ("NIFTY SMALLCAP 100", "NIFTY SMALLCAP 100"),
    ("NIFTY SMALLCAP 50", "NIFTY SMALLCAP 50"),
    ("NIFTY MIDCAP 150", "NIFTY MIDCAP 150"),
    ("NIFTY MIDCAP 100", "NIFTY MIDCAP 100"),
    ("NIFTY MIDCAP 50", "NIFTY MIDCAP 50"),
    ("NIFTY MIDCAP SELECT", "NIFTY MIDCAP SELECT"),
    ("NIFTY MIDCAP", "NIFTY MIDCAP SELECT"),
    ("MIDCAP NIFTY", "NIFTY MIDCAP SELECT"),
    ("MIDCPNIFTY", "NIFTY MIDCAP SELECT"),
    ("NIFTY NEXT 50", "NIFTY NEXT 50"),
    ("NIFTY MICROCAP 250", "NIFTY MICROCAP 250"),
    ("NIFTY FINANCIAL SERVICES EX-BANK", "NIFTY FINSEREXBNK"),
    ("NIFTY FINANCIAL SERVICES EX BANK", "NIFTY FINSEREXBNK"),
    ("NIFTY FINSEREXBNK", "NIFTY FINSEREXBNK"),
    ("FINSEREXBNK", "NIFTY FINSEREXBNK"),
    ("NIFTY FINANCIAL SERVICES 25 50", "NIFTY FINSRV25 50"),
    ("NIFTY FINANCIAL SERVICES", "NIFTY FIN SERVICE"),
    ("NIFTY 500", "NIFTY 500"),
    ("NIFTY500", "NIFTY 500"),
    ("NIFTY 200", "NIFTY 200"),
    ("NIFTY200", "NIFTY 200"),
    ("NIFTY 100", "NIFTY 100"),
    ("NIFTY100", "NIFTY 100"),
    ("NIFTY 50", "NIFTY 50"),
    ("NIFTY50", "NIFTY 50"),
    ("NIFTY BANK", "NIFTY BANK"),
    ("BANK NIFTY", "NIFTY BANK"),
    ("BANKNIFTY", "NIFTY BANK"),
    ("NIFTY IT", "NIFTY IT"),
    ("NIFTY AUTO", "NIFTY AUTO"),
    ("NIFTY FMCG", "NIFTY FMCG"),
    ("NIFTY PHARMA", "NIFTY PHARMA"),
    ("NIFTY METAL", "NIFTY METAL"),
    ("NIFTY REALTY", "NIFTY REALTY"),
)


def _extract_named_index(q: str, default: str = "NIFTY 50") -> str:
    normalized = re.sub(r"\s+", " ", (q or "").strip().upper())
    squashed = normalized.replace(" ", "")
    for needle, index_name in _INDEX_NAME_PATTERNS:
        if needle in normalized or needle.replace(" ", "") in squashed:
            return index_name
    if re.search(r"\bNIFTY\b", normalized):
        return default
    return default


def _extract_intraday_scan_strategies(q: str) -> list[str] | None:
    strategies: list[str] = []
    mapping = [
        ("supertrend", "supertrend"),
        ("super trend", "supertrend"),
        ("vcp", "vcp"),
        ("volatility contraction", "vcp"),
        ("macd", "macd"),
        ("rsi", "rsi"),
        ("bollinger", "bollinger"),
        ("bb squeeze", "bollinger"),
        ("ema", "ema"),
        ("volume", "volume"),
    ]
    for phrase, strategy in mapping:
        if phrase in q and strategy not in strategies:
            strategies.append(strategy)
    return strategies or None


def _intraday_scan_direction(q: str) -> str:
    if any(w in q for w in (" buy", " long", " bullish", "breakout", "breakouts", "ready")):
        return "buy"
    if any(w in q for w in (" sell", " short", " bearish")):
        return "sell"
    return "all"


def _looks_like_intraday_query(q: str) -> bool:
    words = set(re.split(r"\W+", q.lower()))
    if words & _INTRADAY_KEYWORDS:
        return True
    if re.search(r"\b(?:5m|15m|30m|1h|5\s*min|15\s*min|30\s*min)\b", q.lower()):
        return True
    return "scan" in q.lower() and any(
        term in q.lower()
        for term in ("setup", "setups", "invalidation", "target zone", "supertrend", "vcp", "breakout")
    )


def _is_market_knowledge_query(query: str) -> bool:
    q = _routing_query_text(query).lower().strip()
    if (
        "technical setup for" in q
        or re.search(r"\b(full|detailed|complete)\s+technical\b.*\bfor\b", q)
        or ("position vs" in q and re.search(r"\b(ma|sma|ema)\b|20/50/200", q))
    ):
        return False
    # Stock/company research prompts often contain educational metric words
    # such as P/B, ROE, ROCE, or "vs peers". Those should stay on stock_brief
    # evidence paths, not become generic market-knowledge explanations.
    if any(term in q for term in (
        "valuation deep dive",
        "complete analysis",
        "full fundamental analysis",
        "complete fundamental",
        "fundamental analysis of",
        "screener.in fundamentals",
        "technical stage",
        "fii holding",
        "key catalysts",
        "npa trend",
    )):
        return False
    if q.startswith(("/learn", "/define")):
        return True
    if q.startswith("/compare"):
        return any(term in q for term in _MARKET_KNOWLEDGE_TERMS)

    education_prefix = q.startswith((
        "what is ", "what are ", "define ", "explain ", "how is ", "how are ",
        "teach me ", "help me understand ",
    ))
    comparison_phrase = any(phrase in q for phrase in (" different from ", " difference between ", " vs ", " versus "))
    has_market_term = any(term in q for term in _MARKET_KNOWLEDGE_TERMS) or bool(re.search(r"\bpe\b", q))
    return has_market_term and (education_prefix or comparison_phrase)


def _is_document_link_followup(q: str) -> bool:
    return (
        any(term in q for term in ("document link", "pdf link", "alternative link", "updated url", "updated link"))
        and any(term in q for term in ("document", "pdf", "link", "url"))
        and not re.search(r"https?://", q)
    )


def _is_trusted_symbol_resolution(resolved: dict | None) -> bool:
    if not isinstance(resolved, dict) or not resolved.get("symbol"):
        return False
    band = str(resolved.get("confidence_band") or "").lower()
    if band in {"exact", "high"}:
        return True
    try:
        if float(resolved.get("score") or 0.0) >= 0.85:
            return True
    except Exception:
        pass
    return resolved.get("confidence") in {"exact", "near-match"}


def _trusted_symbol_from_phrase_tokens(phrase: str) -> str:
    for token in re.findall(r"\b[A-Z][A-Z0-9&-]{1,12}\b", phrase or ""):
        try:
            resolved = resolve_symbol(token)
        except Exception:
            continue
        if _is_trusted_symbol_resolution(resolved):
            return str(resolved.get("symbol") or token).upper()
    return ""


def _primary_symbol_query(candidates: list[str], symbol_candidates: list[str], raw_query: str = "") -> str:
    """Choose the most explicit stock entity from a routed user query.

    Uppercase NSE-like ticker tokens are stronger evidence than prose labels
    such as "Earnings", "Teach", or "End-to-end". This keeps deterministic
    routes from handing common task words to resolve_symbol().

    Added: when two or more adjacent uppercase tokens appear in the raw
    query (e.g. "TATA MOTORS", "BAJAJ FINANCE", "BANK NIFTY"), join them
    with a space and prefer that phrase. resolve_symbol's local matcher can
    then map the multi-word company name to the canonical NSE ticker
    (TATAMOTORS / BAJFINANCE / BANKNIFTY) instead of being handed just the
    first word ("TATA" → fuzzy-matched to TATATECH).
    """
    if raw_query:
        # Prefer the leading multi-word company phrase ("State Bank of India",
        # "Bharat Petroleum") BEFORE the preposition extractor, otherwise
        # "of India" matches first and the resolver returns INDIA. The leading-
        # phrase helper already strips prose filler ("can you analyze ___").
        phrase = _leading_company_phrase(raw_query)
        if phrase:
            try:
                resolved = resolve_symbol(phrase)
                canonical = resolved.get("symbol") if isinstance(resolved, dict) else None
                if canonical and _is_trusted_symbol_resolution(resolved):
                    return canonical
            except Exception:
                pass
        phrase = _symbol_phrase_after_preposition(raw_query)
        if phrase:
            try:
                resolved = resolve_symbol(phrase)
                canonical = resolved.get("symbol") if isinstance(resolved, dict) else None
                if canonical and _is_trusted_symbol_resolution(resolved):
                    return canonical
            except Exception:
                pass
            token_symbol = _trusted_symbol_from_phrase_tokens(phrase)
            if token_symbol:
                return token_symbol
            # Only fall back to the raw phrase when the caller has no better
            # explicit candidate. Otherwise we end up shipping prose like
            # "intraday signals" downstream as if it were a ticker.
            if not symbol_candidates:
                return phrase
        phrase = _leading_company_phrase(raw_query)
        if phrase:
            try:
                resolved = resolve_symbol(phrase)
                canonical = resolved.get("symbol") if isinstance(resolved, dict) else None
                if canonical and _is_trusted_symbol_resolution(resolved):
                    return canonical
            except Exception:
                pass

    if raw_query and symbol_candidates:
        # Find adjacent uppercase runs of length ≥ 2 in the raw query.
        runs = re.findall(
            r"\b(?:[A-Z][A-Z0-9&-]{1,11}\s+){1,3}[A-Z][A-Z0-9&-]{1,11}\b",
            raw_query,
        )
        if runs:
            phrase = max(runs, key=len).strip()
            # Only prefer the phrase if it contains a known symbol candidate.
            if any(sc in phrase.split() for sc in symbol_candidates):
                # Resolve the phrase to the canonical NSE symbol so downstream
                # tools (get_symbol_snapshot, get_technical_setup, …) receive
                # "TATAMOTORS" not "TATA MOTORS". If resolution fails, fall
                # back to the spaced phrase (resolve_symbol will retry on it).
                try:
                    resolved = resolve_symbol(phrase)
                    canonical = resolved.get("symbol") if isinstance(resolved, dict) else None
                    if canonical and _is_trusted_symbol_resolution(resolved):
                        return canonical
                except Exception:
                    pass
                return phrase
    if symbol_candidates:
        return symbol_candidates[0]
    return candidates[0] if candidates else ""


def _leading_company_phrase(raw_query: str) -> str:
    """Extract a leading multi-word company phrase before task words."""
    stop_words = {
        # Prose filler — must be stripped so the 4-word window doesn't fill
        # with "can you analyze ..." before the real company name. Without
        # these, "can you analyze Premier Energies" yielded "can you analyze
        # Premier" and resolved to PREMEXPLN instead of PREMIERENE.
        "can", "could", "would", "should", "shall", "may", "might",
        "you", "u", "we", "i", "me", "us", "they",
        "please", "kindly", "tell", "show", "give", "explain", "describe",
        "analyze", "analyse", "analysis",
        "let", "lets", "let's", "want", "wanna", "wish",
        "about", "around", "regarding", "concerning",
        "for", "of",
        "how", "what", "where", "when", "why",
        "do", "does", "doing", "done",
        "is", "are", "was", "were", "be", "been", "being",
        "a", "an", "the", "this", "that", "these", "those",
        "to", "into", "onto", "upon",
        # Existing task words
        "intraday", "setup", "technical", "technicals", "fundamental", "fundamentals",
        "analysis", "deep", "dive", "research", "forensic", "risk", "levels",
        "support", "resistance", "target", "targets", "today", "now", "live",
        "current", "price", "prices", "quote", "quotes",
        "scan", "f&o", "fno", "fo",
        "superperformance", "minervini", "sepa", "vcp", "canslim",
    }
    words: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9&.-]*", raw_query):
        if token.lower() in stop_words:
            if words:
                break
            continue
        words.append(token)
        if len(words) >= 6:
            break
    return " ".join(words).strip() if len(words) >= 2 else ""


def _stock_research_symbol_from_query(raw_query: str) -> str:
    """Resolve the primary company in stock research prose.

    This guards prompts like "HDFC Bank valuation deep dive" and
    "SBI complete analysis" before generic comparison logic sees metric
    fragments such as P/B, NIM, NPA, or "vs peers" and treats them as symbols.
    """
    phrase = _leading_company_phrase(raw_query or "")
    tokens = phrase.split()
    for size in range(min(len(tokens), 5), 0, -1):
        candidate = " ".join(tokens[:size]).strip()
        if not candidate:
            continue
        try:
            resolved = resolve_symbol(candidate)
            if _is_trusted_symbol_resolution(resolved):
                return str(resolved["symbol"]).upper()
        except Exception:
            continue
    # Fallback to explicit uppercase runs in the original query.
    for token in re.findall(r"\b[A-Z][A-Z0-9&-]{1,12}\b", raw_query or ""):
        raw = token.upper()
        if raw in _SYMBOL_VALIDATION_SKIP or raw in TECHNICAL_NON_SYMBOL_TERMS:
            continue
        try:
            resolved = resolve_symbol(raw)
            if _is_trusted_symbol_resolution(resolved):
                return str(resolved["symbol"]).upper()
        except Exception:
            continue
    return ""


def _looks_like_stock_research_prompt(q: str) -> bool:
    return any(term in (q or "") for term in (
        "complete analysis",
        "deep dive",
        "full analysis",
        "full fundamental analysis",
        "fundamental analysis of",
        "valuation deep dive",
        "screener.in fundamentals",
        "technical stage",
        "fii holding",
        "holding changes",
        "key catalysts",
        "npa trend",
        "concall transcript",
        "management commentary",
    ))


def _symbol_phrase_after_preposition(raw_query: str) -> str:
    """Extract a company-name phrase after stock-query prepositions."""
    stop_words = {
        "with", "including", "include", "after", "before", "using", "use",
        "on", "in", "at",
        "technical", "technicals", "fundamental", "fundamentals", "analysis",
        "setup", "risk", "valuation", "news", "catalyst", "catalysts",
        "forensic", "red", "flags", "flag", "and", "or", "stage", "rsi",
        "adx", "macd", "supertrend", "recent", "announcements", "results",
        "management", "commentary", "analyst", "views", "current", "price",
        "support", "supports", "resistance", "resistances", "pivot", "pivots",
        "level", "levels", "short", "breakdown", "breakdowns", "long", "buy",
        "sell", "setups", "strategy", "strategies", "entry", "target", "stoploss",
    }
    for match in re.finditer(r"\b(?:for|of|about|on|into)\s+(.+)$", raw_query, flags=re.IGNORECASE):
        subject = re.split(r"\s+[—–-]\s+|[,;:?]", match.group(1), maxsplit=1)[0]
        if re.match(r"\s*\d+\s*(?:m|min|mins?|minutes?|h|hour|hours?)\b", subject, flags=re.IGNORECASE):
            continue
        connective_company = re.match(
            r"\s*([A-Za-z][A-Za-z0-9&.-]*(?:\s+[A-Za-z][A-Za-z0-9&.-]*){0,2}\s+(?:and|&)\s+[A-Za-z][A-Za-z0-9&.-]*(?:\s+[A-Za-z][A-Za-z0-9&.-]*){0,2})\b",
            subject,
            flags=re.IGNORECASE,
        )
        if connective_company:
            phrase = connective_company.group(1).strip()
            try:
                resolved = resolve_symbol(phrase)
                if _is_trusted_symbol_resolution(resolved):
                    return phrase
            except Exception:
                pass
        words: list[str] = []
        for token in re.findall(r"[A-Za-z][A-Za-z0-9&.-]*", subject):
            if token.lower() in stop_words:
                break
            words.append(token)
            if len(words) >= 4:
                break
        phrase = " ".join(words).strip()
        if phrase and phrase.lower() not in {"it", "this", "that", "stock", "company"}:
            return phrase
    return ""


_PLACEHOLDER_SYMBOLS: frozenset[str] = frozenset(
    {"SYMBOL", "TICKER", "STOCK", "NAME", "COMPANY", "NSE_SYMBOL"}
)


def _contains_placeholder_symbol(query: str) -> bool:
    text = query or ""
    if re.search(r"[<{\\[]\s*(?:symbol|ticker|stock|name|company|nse_symbol)\s*[>}\\]]", text, flags=re.I):
        return True

    tokens = re.findall(r"\b[A-Za-z_][A-Za-z0-9_&-]*\b", text)
    uppercase_placeholders = {
        token.upper()
        for token in tokens
        if token == token.upper() or "_" in token
    }
    if uppercase_placeholders & _PLACEHOLDER_SYMBOLS:
        return True

    return bool(
        text.strip().startswith("/")
        and any(token.lower() in {"symbol", "ticker", "stock", "name", "company", "nse_symbol"} for token in tokens[1:])
    )


_SYMBOL_VALIDATION_SKIP: frozenset[str] = frozenset(
    {
        "NSE", "BSE", "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY",
        "RS", "RSI", "ADX", "ATR", "MA", "SMA", "EMA", "DMA", "PE", "PB",
        "EPS", "ROE", "ROCE", "MACD", "VWAP", "VCP", "ORB", "BB", "OBV",
        "FII", "DII", "FNO", "OI", "PCR", "CEO", "CFO", "FY", "QOQ", "YOY",
        "PDF", "URL", "HTML", "EOD", "DB", "PG", "API", "LLM", "AI",
        "BUY", "SELL", "HOLD", "LONG", "SHORT", "OPEN", "HIGH", "LOW",
    }
) | TECHNICAL_NON_SYMBOL_TERMS

# Intents that handle grounded scan/screener data (gainers, RS, breadth, screeners).
# The LLM must NOT fabricate responses for these — if no deterministic handler claimed
# the intent, the hallucination guard fires and refuses cleanly.
#
# IMPORTANT: This is NOT the same as the keyword-path gate set (agent.py ~line 6796).
# Keyword-gate answers: "does this intent have a keyword handler?"
# _GROUNDED_SCAN_INTENTS answers: "would an LLM fabricating a response for this intent
#   produce a plausible-but-false scan/screener list?"
# A new intent that handles grounded scan data must be added here. An intent that is
# only conversational (greeting, youtube_*, stock_brief) must NOT be added here even
# if it has a keyword handler.
_GROUNDED_SCAN_INTENTS: frozenset[str] = frozenset({
    "market_overview",
    "market_situation_assessment",
    "market_swing_candidates",
    "market_dashboard",
    "screener_run",
    "stage2_screener",
    "intraday_scan",
    "intraday_symbol_scan",
    "gainers_losers",
    "top_movers",
    "high_rs",
    "breakout_scan",
    "entity_topic_command",
    "report_lookup",
    "contextual_tool_plan",
})

# Static source-label overrides for intents whose sources are known before tool
# execution.  Maps intent → source_label.  mode_suffix is built at runtime
# using the label plus the live market_status fields.
# NOTE: intents whose source_label depends on tool_results (intraday keyword
# path at ~line 6854) or on transcription sub-type (youtube) are intentionally
# absent — those are handled by runtime logic below.
_INTENT_SOURCE_LABEL_OVERRIDES: dict[str, str] = {
    "index_status":              "EOD index snapshots + scoped DB index breadth",
    "market_overview":            "NSE live API + DB breadth",
    "market_situation_assessment": "situation planner + NSE live API + DB breadth",
    "market_swing_candidates":     "EOD index snapshots + DB breadth + quality breakout screener",
    "market_dashboard":           "dashboard planner + NSE live API + DB breadth + FII/DII + global context",
    "intraday_market_recap":      "NSE live API + PG intraday.quote_snapshots + DB breadth",
    "intraday_options_trade_plan": "PG intraday levels + NSE live snapshot + NSE options/F&O evidence",
    "fno_overview":               "NSE options/futures API + F&O EOD fallback",
    "long_term_growth_research":  "NSE live index constituents + DB growth scores + screener.in",
}

# Mode label overrides: intents that should display a mode other than the
# detected data_mode (e.g. market_dashboard always says "Intraday", research
# intents say "Research" regardless of session mode).
_INTENT_MODE_LABEL_OVERRIDES: dict[str, str] = {
    "market_dashboard":          "Intraday",
    "intraday_market_recap":     "Intraday",
    "intraday_options_trade_plan": "Intraday",
    "fno_overview":              "Intraday",
    "long_term_growth_research": "Research",
}


_REQUIRED_TOOLS_BY_INTENT: dict[str, tuple[str, ...]] = {
    "market_swing_candidates": ("get_index_snapshot", "get_market_breadth", "run_quality_breakout_screener"),
    "screener": ("run_screener_query",),
    "quality_breakouts": ("run_quality_breakout_screener",),
    "intraday_screener": ("run_intraday_screener",),
    "intraday_index_scan": ("scan_intraday_market",),
    "intraday_symbol_scan": ("scan_symbols_intraday",),
    "intraday_setup": ("explain_intraday_setup", "get_nse_intraday_snapshot"),
    "intraday_levels": ("get_intraday_levels", "get_nse_intraday_snapshot"),
    "intraday_options_trade_plan": ("get_intraday_levels", "get_options_chain", "get_nse_intraday_snapshot"),
    "fno_overview": ("get_fno_overview",),
    "visual_scan": ("run_visual_scan",),
    "stock_comparison": ("compare_stocks",),
    "strength_validation": ("validate_strength_watchlist",),
    "symbol_quick_analysis": ("resolve_symbol", "get_symbol_quick_analysis"),
    "stock_brief": ("resolve_symbol", "get_symbol_snapshot"),
    "stock_results": (
        "resolve_symbol",
        "get_latest_results",
    ),
    "results_feed": ("get_latest_results_feed",),
    "forthcoming_results": ("get_forthcoming_results",),
    # PG-PLAN 2026-05-25: Follow-up plans that fetch latest results for a
    # set of symbols already resolved in the previous turn. resolve_symbol
    # is intentionally NOT required — the symbols are bound by the
    # situation-assessment planner, not re-resolved from reply text.
    "collective_news_results": ("get_latest_results",),
}


# PG-SYNTH-INTENT 2026-05-25: When a situation-assessment / clarification /
# compound-provider branch runs a tool plan, the post-execution synthesis
# step needs an intent label so the universal claim-gate can pick the right
# required-tool contract. Historically this was hardcoded to
# "intraday_symbol_scan" for every non-report plan, which caused the
# guardrail to demand `scan_symbols_intraday` even for plans that ran
# only compare_stocks / get_latest_results / get_fno_overview / etc.
# Result: user-visible "Missing required tool: scan_symbols_intraday" on
# follow-ups like "any news or results for these top gainers" even though
# the executed plan was valid for its actual tools. Map first-tool ->
# synthesis_intent so the gate matches the tools that actually ran.
_PLAN_TOOL_TO_SYNTHESIS_INTENT: dict[str, str] = {
    "compare_stocks": "stock_comparison",
    "validate_strength_watchlist": "strength_validation",
    "scan_symbols_intraday": "intraday_symbol_scan",
    "scan_intraday_market": "intraday_index_scan",
    "run_intraday_screener": "intraday_screener",
    "run_screener_query": "screener",
    "run_quality_breakout_screener": "quality_breakouts",
    "explain_intraday_setup": "intraday_setup",
    "get_nse_intraday_snapshot": "intraday_setup",
    "get_intraday_levels": "intraday_levels",
    "get_fno_overview": "fno_overview",
    "run_visual_scan": "visual_scan",
    "get_latest_results": "stock_results",
    "get_latest_results_feed": "results_feed",
    "get_forthcoming_results": "forthcoming_results",
    "get_symbol_quick_analysis": "symbol_quick_analysis",
    "screen_forensic_watchlist": "portfolio_forensic_review",
    "screen_portfolio_forensic_watchlist": "portfolio_forensic_review",
    "get_symbol_snapshot": "stock_brief",
    # AA-UR-6 Phase 2: MarketSituationProvider market-overview tools
    "get_live_market_overview": "market_situation_assessment",
    "get_market_breadth": "market_situation_assessment",
    "get_top_gainers_losers": "market_situation_assessment",
    "get_eod_top_movers": "market_situation_assessment",
    # AA-UR-6 Phase 2: DirectIntentProvider single-stock tools
    "get_technical_setup": "stock_brief",
    "analyze_mtf": "intraday_setup",
    "get_live_quote": "intraday_setup",
    "search_yahoo_finance": "stock_brief",
}

_REPORT_LOOKUP_TOOLS: frozenset[str] = frozenset({
    "open_report",
    "read_report",
    "summarize_report",
    "get_last_report",
    "list_generated_reports",
})


def _synthesis_intent_from_plan(
    tool_plan: list[tuple[str, dict]] | tuple,
    default: str = "intraday_symbol_scan",
    query: str = "",
) -> str:
    """PG-SYNTH-INTENT: derive a synthesis_intent from the executed plan.

    Picks the first plan tool that has a known intent mapping so the
    universal claim-gate's required-tool check is consistent with the
    tools that actually ran. Report-tool plans short-circuit to
    `report_lookup`. Falls back to ``default`` only when no plan tool
    is recognized (preserves prior behaviour for unknown plans).
    """
    if not tool_plan:
        return default
    names = [name for name, _ in tool_plan]
    q = (query or "").lower()
    wants_results_analysis = (
        "get_latest_results" in names
        and any(
            term in q
            for term in (
                "analyze",
                "analysis",
                "deep dive",
                "deep analysis",
                "quarterly result",
                "quarterly results",
                "latest results",
                "results analysis",
                "earnings analysis",
                "financial results",
            )
        )
    )
    if wants_results_analysis:
        return "stock_results"
    if any(n in _REPORT_LOOKUP_TOOLS for n in names):
        return "report_lookup"
    for name in names:
        mapped = _PLAN_TOOL_TO_SYNTHESIS_INTENT.get(name)
        if mapped:
            return mapped
    return default


_DYNAMIC_EVIDENCE_REQUIRED_INTENTS: frozenset[str] = frozenset(
    {
        "stock_brief",
        "stock_results",
        "stock_comparison",
        "strength_validation",
        "portfolio_review",
        "entity_topic_command",
        "llm_driven",
        "llm_driven_fallback",
    }
)


# AA-UR-6: routing providers whose RouteDecision carries an executable
# tool plan that ``Agent._execute_route`` should run directly without
# falling through to subsequent pipeline stages.  Kept module-level so
# we don't rebuild it on every router invocation.
_ROUTER_DIRECT_PLAN_PROVIDERS: frozenset[str] = frozenset({
    "CompoundStockProvider",
    "PendingOptionProvider",
    "VisualScanProvider",      # "chart RELIANCE", "visual scan INFY"
    "MarketSituationProvider", # "market situation", "intraday scan"
    "TopMoversProvider",       # "top gainers", "top losers"
})


def _explicit_requested_symbols(query: str) -> list[str]:
    """Return explicit ticker-looking symbols from user text without fuzzy substitution."""
    requested = validate_requested_symbols(query or "").get("requested_symbols", [])
    # Multi-word company-phrase guard (priority path): when the user typed a
    # phrase like "HDFC Bank" / "Sun Pharma", the upstream validator picks the
    # first ticker-shaped token ("HDFC" → an ETF; "SUN" → a defunct ticker)
    # which then trips the validation gate against evidence using the real
    # company symbol (HDFCBANK / SUNPHARMA). If the leading-company-phrase
    # helper resolves the full phrase exactly via the alias/universe map, that
    # canonical symbol wins over any single-token extraction.
    try:
        # Strip known index phrases (NIFTY MIDCAP 100, NIFTY BANK, NIFTY
        # FINANCIAL SERVICES, ...) before attempting company-phrase resolution.
        # Otherwise "NIFTY MIDCAP" resolves to the MIDCPNIFTY derivative and
        # mis-fires the validation gate against breadth/scan tools that use
        # the actual index name.
        from .entity_resolution import _strip_index_phrases as _strip_idx_phr
        scrubbed_for_phrase = _strip_idx_phr(query or "")
        phrase = _leading_company_phrase(scrubbed_for_phrase)
        if phrase and " " in phrase.strip():
            phrase_resolution = resolve_symbol(phrase)
            if _is_trusted_symbol_resolution(phrase_resolution):
                return [str(phrase_resolution["symbol"]).upper()]
    except Exception:
        pass
    # The universe-backed validator deliberately filters non-listed tokens to
    # avoid instruction words becoming symbols in generated prompts. For final
    # evidence validation, retain explicit all-caps user tokens in stock-shaped
    # queries so a bad resolver cannot silently substitute another company.
    if not requested and re.search(
        r"\b(technical|setup|stock|analy[sz]e|result|results|earnings|screener|breakout)\b",
        query or "",
        re.I,
    ):
        # Strip well-known multi-word NSE index names ("NIFTY SMALLCAP 100",
        # "NIFTY FINANCIAL SERVICES", ...) before re-extracting candidate
        # tokens. Without this, "lets analyze NIFTY SMALLCAP 100" trips the
        # symbol-validation gate on SMALLCAP/MIDCAP/PRIVATE/etc. even though
        # the upstream universe-backed validator correctly stripped them.
        from .entity_resolution import _strip_index_phrases as _strip_idx
        scrubbed = _strip_idx(query or "")
        requested = [
            token
            for token in re.findall(r"\b[A-Z][A-Z0-9&-]{1,12}\b", scrubbed)
            if token.upper() not in _SYMBOL_VALIDATION_SKIP
            and token.upper() not in TECHNICAL_NON_SYMBOL_TERMS
        ]
        # Multi-word company-phrase guard: when the user typed a phrase like
        # "HDFC Bank" / "Premier Energies", the single-token extractor only
        # picks up the first all-caps run ("HDFC") which resolves to HDFCGOLD
        # (an ETF). If the leading-phrase helper resolves the whole company
        # name exactly via _COMMON_STOCK_ALIASES, prefer that canonical symbol
        # so the validation gate matches the actual evidence (HDFCBANK).
        try:
            phrase = _leading_company_phrase(query or "")
            if phrase:
                phrase_resolution = resolve_symbol(phrase)
                if _is_trusted_symbol_resolution(phrase_resolution):
                    requested = [str(phrase_resolution["symbol"]).upper()]
        except Exception:
            pass
    symbols: list[str] = []
    for token in requested:
        clean = token.strip().upper()
        if clean in _SYMBOL_VALIDATION_SKIP:
            continue
        if clean.endswith("-"):
            continue
        if re.fullmatch(r"[A-Z0-9&-]{2,12}", clean):
            canonical = clean
            try:
                resolved = resolve_symbol(clean)
                if _is_trusted_symbol_resolution(resolved):
                    canonical = str(resolved["symbol"]).upper()
            except Exception:
                canonical = clean
            symbols.append(canonical)
    return list(dict.fromkeys(symbols))


def _tool_symbols(tool_results: list[dict]) -> set[str]:
    symbols: set[str] = set()
    for tr in tool_results or []:
        args = tr.get("args") if isinstance(tr.get("args"), dict) else {}
        result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
        for key in ("symbol", "resolved_symbol"):
            val = result.get(key) or args.get(key)
            if isinstance(val, str) and re.fullmatch(r"[A-Z0-9&-]{2,12}", val.upper()):
                symbols.add(val.upper())
        for key in ("symbols", "input_symbols", "unresolved_symbols"):
            vals = result.get(key) or args.get(key)
            if isinstance(vals, list):
                for val in vals:
                    if isinstance(val, str) and re.fullmatch(r"[A-Z0-9&-]{2,12}", val.upper()):
                        symbols.add(val.upper())
    return symbols


def _source_trail_lines(tool_results: list[dict]) -> list[str]:
    lines: list[str] = []
    for tr in tool_results or []:
        result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
        err = result.get("error")
        status = f"ERROR: {err}" if err else "ok"
        lines.append(f"  {tr.get('tool')}: {status}")
        if err and tr.get("tool") == "resolve_symbol":
            candidates = result.get("candidates") or []
            if candidates:
                lines.append(f"    Suggestions: {', '.join(str(c) for c in candidates[:5])}")
    return lines


_SEARCH_TOOLS = frozenset({
    "search_latest_catalysts", "search_broker_research", "search_concall_transcripts",
    "search_yahoo_finance", "multi_source_web_search", "comprehensive_stock_research",
    "search_market_knowledge", "web_search",
})


def _tool_stats_from_results(tool_results: list[dict]) -> dict:
    read_count = search_count = 0
    for tr in tool_results or []:
        name = tr.get("tool") or ""
        if name in _SEARCH_TOOLS:
            search_count += 1
        else:
            read_count += 1
    return {"readCount": read_count, "searchCount": search_count}


# USD per 1M tokens. Keys are matched as case-insensitive prefixes against
# the model identifier so variants like "gpt-4o-2024-08-06" hit the gpt-4o
# row. Update when OpenAI publishes new pricing.
_LLM_PRICING_USD_PER_M: dict[str, dict[str, float]] = {
    "gpt-5-mini":   {"in": 0.25, "cached_in": 0.025, "out": 2.00},
    "gpt-5":        {"in": 1.25, "cached_in": 0.125, "out": 10.00},
    "gpt-4o-mini":  {"in": 0.15, "cached_in": 0.075, "out": 0.60},
    "gpt-4o":       {"in": 2.50, "cached_in": 1.25,  "out": 10.00},
    "gpt-4.1-mini": {"in": 0.40, "cached_in": 0.10,  "out": 1.60},
    "gpt-4.1":      {"in": 2.00, "cached_in": 0.50,  "out": 8.00},
    "o3-mini":      {"in": 1.10, "cached_in": 0.55,  "out": 4.40},
    "o3":           {"in": 2.00, "cached_in": 0.50,  "out": 8.00},
}


def _usd_cost_for_usage(usage: dict) -> float | None:
    """Return USD cost for a usage dict, or None if the model is unpriced."""
    model = (usage.get("model") or "").strip().lower()
    if not model:
        return None
    # Longest-prefix match so "gpt-4o-mini" wins over "gpt-4o".
    price = None
    matched_len = -1
    for key, row in _LLM_PRICING_USD_PER_M.items():
        if model.startswith(key) and len(key) > matched_len:
            price = row
            matched_len = len(key)
    if price is None:
        return None
    cached = usage.get("cache_read_input_tokens", 0) or 0
    fresh_in = max(0, (usage.get("input_tokens", 0) or 0) - cached)
    out = usage.get("output_tokens", 0) or 0
    return (
        fresh_in * price["in"]
        + cached * price["cached_in"]
        + out * price["out"]
    ) / 1_000_000.0


def _cost_trail_block(usage: dict, tool_results: list[dict]) -> str:
    """Render a compact ▶ COST line summarising token spend and tool stats."""
    if not usage or not any(usage.get(k, 0) for k in (
        "input_tokens", "output_tokens",
        "cache_read_input_tokens", "cache_creation_input_tokens",
    )):
        return ""
    ts = _tool_stats_from_results(tool_results)
    parts = [
        f"in={usage.get('input_tokens', 0)}",
        f"out={usage.get('output_tokens', 0)}",
    ]
    if usage.get("cache_read_input_tokens"):
        parts.append(f"cache_read={usage['cache_read_input_tokens']}")
    if usage.get("cache_creation_input_tokens"):
        parts.append(f"cache_create={usage['cache_creation_input_tokens']}")
    usd = _usd_cost_for_usage(usage)
    if usd is not None:
        parts.append(f"cost=${usd:.4f}")
    parts.append(f"tools: read={ts['readCount']} search={ts['searchCount']}")
    return "\n▶ COST  " + "  ".join(parts)


def _accumulate_usage(acc: dict, new: dict) -> dict:
    """Merge two usage dicts by summing every key. Carries the model id from
    the newest non-empty value so cost pricing has something to match against."""
    for k in ("input_tokens", "output_tokens",
               "cache_read_input_tokens", "cache_creation_input_tokens"):
        acc[k] = acc.get(k, 0) + (new.get(k, 0) or 0)
    if new.get("model"):
        acc["model"] = new["model"]
    return acc


# Tools that write to shared state (caches, DBs) and must run sequentially.
# All other tools are assumed pure-read and are safe to dispatch concurrently.
_SERIAL_TOOLS: frozenset[str] = frozenset({
    "run_screener_query",           # writes screener result cache
    "run_quality_breakout_screener", # writes screener result cache through source screens
    "scan_symbols_intraday",        # writes intraday scan cache
    "refresh_market_data",          # mutates local data files
    "cache_symbol_snapshot",        # explicit cache writer
    "write_report",                 # filesystem writer
})

_PARALLEL_WORKERS = 6


def _parallel_tool_dispatch(
    tool_calls: list[dict],
    call_tool_fn: Callable,
) -> list[tuple[str, dict, Any, str]]:
    """Execute tool calls concurrently when all are parallel-safe.

    Returns a list of (name, args, result, call_id) in the original call order.
    Falls back to sequential dispatch if any tool is in _SERIAL_TOOLS.
    """
    if len(tool_calls) <= 1 or any(tc["name"] in _SERIAL_TOOLS for tc in tool_calls):
        return [
            (tc["name"], tc.get("args", {}),
             call_tool_fn(tc["name"], tc.get("args", {})), tc["id"])
            for tc in tool_calls
        ]

    # All parallel-safe: submit concurrently, collect in original order.
    with concurrent.futures.ThreadPoolExecutor(max_workers=_PARALLEL_WORKERS) as pool:
        futures = {
            idx: pool.submit(call_tool_fn, tc["name"], tc.get("args", {}))
            for idx, tc in enumerate(tool_calls)
        }
    results = []
    for idx, tc in enumerate(tool_calls):
        try:
            result = futures[idx].result()
        except Exception as exc:
            result = {"error": f"tool dispatch error: {exc}"}
        results.append((tc["name"], tc.get("args", {}), result, tc["id"]))
    return results


def _required_tools_for_query(intent: str, query: str) -> tuple[str, ...]:
    required = list(_REQUIRED_TOOLS_BY_INTENT.get(intent) or ())
    if intent not in _DYNAMIC_EVIDENCE_REQUIRED_INTENTS:
        return tuple(dict.fromkeys(required))

    q = (query or "").lower()
    wants_fundamental_chain = _stock_fundamental_chain_requested(q)
    if any(term in q for term in ("news", "catalyst", "catalysts", "recent announcement")):
        required.append("search_latest_catalysts")
    if any(term in q for term in ("broker", "analyst target", "target price", "rating", "brokerage")):
        required.append("search_broker_research")
    if any(term in q for term in ("concall", "earnings call", "management commentary", "guidance")):
        required.append("search_concall_transcripts")
    if any(term in q for term in ("forensic", "red flag", "red flags", "manipulation", "earnings quality")):
        required.append("run_forensic_analysis")
    if any(term in q for term in (
        "latest results", "quarterly results", "quarterly result",
        "q1 results", "q2 results", "q3 results", "q4 results",
        "annual results", "yearly results",
        "earnings results", "earnings report",
        "p&l statement", "profit and loss",
        "balance sheet", "cash flow statement", "financial statements",
        "fundamental analysis", "quarterly numbers", "quarterly financials",
    )):
        required.append("get_latest_results")
    if wants_fundamental_chain:
        required.extend(["get_cached_financials", "scrape_screener_in", "get_latest_results"])
    return tuple(dict.fromkeys(required))


def _ric_prevalidated_symbol(query: str) -> str:
    match = re.match(
        r"^\s*\[\[RIC_STEP_PREVALIDATED_SYMBOL=([A-Z0-9&-]+)\]\]",
        query or "",
        flags=re.I,
    )
    return match.group(1).upper() if match else ""


def _is_contextual_synthesis_query(query: str) -> bool:
    """True when the user is asking for a synthesis/recommendation on already-gathered evidence.

    These queries don't name a new stock — they refer back to the current context
    ("based on the analysis", "what is your recommendation", "should I buy/sell",
    "summarise", "compare all", "give me a summary", "which would you pick", etc.).
    The symbol is already known from prior turns; demanding a fresh resolve_symbol
    call is a false negative.
    """
    q = _routing_query_text(query).lower()
    synthesis_signals = (
        "based on",
        "your recommendation",
        "what is your",
        "what do you think",
        "should i buy",
        "should i sell",
        "should i hold",
        "buy or sell",
        "is it a buy",
        "is it a sell",
        "give me a verdict",
        "give me a view",
        "give me a summary",
        "give me an overview",
        "what is the verdict",
        "summarize",
        "summarise",
        "sum up",
        "overall view",
        "overall verdict",
        "overall recommendation",
        "investment recommendation",
        "trading recommendation",
        "trade recommendation",
        "final recommendation",
        "what do you recommend",
        "your view",
        "your take",
        "your opinion",
        # cross-stock synthesis / comparison
        "which would you pick",
        "which one would you",
        "which has the best",
        "which is the best",
        "compare all",
        "compare the stocks",
        "compare these stocks",
        "rank them",
        "rank these",
        "which of these",
        "all the stocks we",
        "everything we covered",
        "everything we analysed",
        "everything we analyzed",
        "all the above",
        "all of the above",
        "from the above",
        "from all the",
        "across all",
        "best pick",
        "top pick",
        # contextual follow-up signals (referencing prior context)
        "deep dive",
        "dive into",
        "more on this",
        "more about this",
        "tell me more",
        "latest results",
        "the results",
        "its results",
        "their results",
        "can we look",
        "can you look",
        "let's look",
        "on this",
        "into this",
        "about this",
        "for this",
    )
    return any(signal in q for signal in synthesis_signals)


def _context_symbol_resolved(tool_results: list[dict]) -> bool:
    """True when a downstream tool that requires a valid symbol ran successfully.

    get_symbol_snapshot / get_technical_setup / explain_intraday_setup etc. can
    only run on a known NSE symbol. If any of them returned a non-error result,
    the symbol was effectively resolved from context — resolve_symbol is satisfied.
    """
    context_evidence_tools = {
        "get_symbol_snapshot",
        "get_symbol_quick_analysis",
        "get_technical_setup",
        "explain_intraday_setup",
        "get_intraday_analysis",
        "get_intraday_levels",
        "get_nse_intraday_snapshot",
        "get_cached_financials",
        "scrape_screener_in",
        "get_latest_results",
        "search_nse_announcements",
    }
    for tr in tool_results or []:
        if tr.get("tool") not in context_evidence_tools:
            continue
        result = tr.get("result") or {}
        if isinstance(result, dict) and not result.get("error"):
            return True
    return False


def _ric_step_evidence_satisfied(query: str, intent: str, executed: set[str]) -> bool:
    """RIC recipes resolve the symbol once before the step sequence.

    Each step is intentionally partial, so stock_brief's full-response
    mandatory tool contract would be a false positive for step-local evidence.
    """
    if not _ric_prevalidated_symbol(query):
        return False
    q = _routing_query_text(query).lower()
    if intent == "stock_brief":
        if any(term in q for term in ("fundamental", "fundamentals", "screener.in", "p/e", "roe", "roce")):
            return bool(executed & {"get_cached_financials", "scrape_screener_in", "get_symbol_snapshot"})
        if any(term in q for term in ("news", "catalyst", "catalysts", "announcement", "announcements", "management commentary")):
            return bool(executed & {
                "search_latest_catalysts",
                "search_nse_announcements",
                "search_bse_filings",
                "get_latest_results",
                "search_concall_transcripts",
            })
        if any(term in q for term in ("technical", "rsi", "adx", "macd", "supertrend", "weinstein")):
            return bool(executed & {"get_technical_setup", "explain_intraday_setup", "get_intraday_analysis"})
        if any(term in q for term in ("live price", "quote", "current price")):
            return bool(executed & {"get_live_quote", "get_symbol_snapshot", "get_nse_intraday_snapshot"})
    if intent in {"intraday_setup", "intraday_levels"}:
        return bool(executed & {
            "explain_intraday_setup",
            "get_intraday_levels",
            "get_nse_intraday_snapshot",
            "get_intraday_analysis",
        })
    return False


def _validate_required_tools(query: str, intent: str, tool_results: list[dict]) -> str | None:
    required = _required_tools_for_query(intent, query)
    if not required:
        return None
    executed = {str(tr.get("tool")) for tr in tool_results or []}
    if _ric_step_evidence_satisfied(query, intent, executed):
        return None
    if (
        intent == "stock_brief"
        and {"explain_intraday_setup", "get_intraday_levels"} & executed
        and "setup" in (query or "").lower()
    ):
        return None

    # ── Contextual follow-up: symbol resolved from prior turn context ─────
    # If the user is asking a synthesis/recommendation question (e.g. "based
    # on the analysis what is your recommendation") and substantive evidence
    # tools ran successfully, resolve_symbol is satisfied implicitly — the
    # symbol was bound from the previous turn and the LLM called downstream
    # tools directly (get_symbol_snapshot, get_technical_setup, etc.).
    # Guard: only applies when the query is a pure synthesis/meta question
    # with no new ticker to resolve. Fresh "tell me about RELIANCE" queries
    # still require resolve_symbol even if snapshot data was gathered.
    if (
        "resolve_symbol" in required
        and (_is_contextual_synthesis_query(query) or intent == "contextual_tool_plan")
        and _context_symbol_resolved(tool_results)
    ):
        return None
    # If the user invoked /analyze on a document URL/file, the expanded prompt template
    # references "concall transcript / management commentary / guidance" as generic
    # interpretation hints. Those words must not coerce search_concall_transcripts /
    # search_broker_research / search_latest_catalysts requirements — the user is
    # analyzing a fixed document, not researching a stock.
    if "analyze_document" in executed:
        document_safe_skip = {
            "search_concall_transcripts",
            "search_broker_research",
            "search_latest_catalysts",
            "run_forensic_analysis",
            "scrape_screener_in",
            "get_cached_financials",
            "get_latest_results",
        }
        required = tuple(t for t in required if t not in document_safe_skip)
        if not required:
            return None
    validation = validate_required_tools_executed(list(required), tool_results or [])
    missing = validation.get("missing_tools") or [tool for tool in required if tool not in executed]
    if not missing:
        return None
    suggestions: list[str] = []
    for tr in tool_results or []:
        if tr.get("tool") != "resolve_symbol" or not isinstance(tr.get("result"), dict):
            continue
        if tr["result"].get("symbol") and not tr["result"].get("error"):
            continue
        candidates = tr["result"].get("candidates") or []
        if candidates:
            bad_query = tr["result"].get("query") or tr.get("args", {}).get("query") or "requested symbol"
            suggestions.append(f"  Symbol not found: {bad_query}. Did you mean: {', '.join(str(c) for c in candidates[:5])}?")
    lines = [
        "▶ REQUIRED TOOL VALIDATION FAILED",
        f"  Intent: {intent}",
        f"  Missing required tool(s): {', '.join(missing)}",
        *suggestions,
        "  No market conclusion was rendered because the mandatory evidence plan did not run.",
        "",
        "▶ SOURCE TRAIL",
        *_source_trail_lines(tool_results),
        "",
        "━━━ Not investment advice. For research and learning only. ━━━",
    ]
    return "\n".join(lines)


def _validate_symbol_grounding(
    query: str,
    intent: str,
    tool_results: list[dict],
    compressed_symbols: list[str] | None = None,
) -> str | None:
    # ── Synthesis query over compressed context ───────────────────────────────
    # When the query is a synthesis question (compare, rank, which is best) and
    # compressed_symbols were provided OR the query contains an injected
    # [CONTEXT: prior stocks analysed = ...] suffix, those symbols are already
    # in the LLM system prompt — the LLM synthesises from that data without
    # needing fresh tool calls. Skip the symbol grounding check entirely.
    has_injected_context = "[CONTEXT: prior stocks analysed" in query
    if (compressed_symbols or has_injected_context) and _is_contextual_synthesis_query(query):
        return None
    stock_360_symbol = _stock_360_prompt_symbol(query)
    requested = [stock_360_symbol] if stock_360_symbol else _explicit_requested_symbols(query)
    if not requested:
        return None
    if intent not in {
        "stock_brief", "stock_comparison", "strength_validation", "portfolio_review",
        "intraday_setup", "intraday_levels", "intraday_symbol_scan",
        "llm_driven", "llm_driven_fallback",
    }:
        return None
    # Document-analysis runs may contain many uppercase tokens in the prompt
    # (POT, TOT, EBITDA, PBT, KPI, ...) that are not stock tickers — they are
    # report-format hints. Skip symbol grounding when analyze_document executed.
    if any(str(tr.get("tool")) == "analyze_document" for tr in tool_results or []):
        return None

    tool_syms = _tool_symbols(tool_results)
    missing = [sym for sym in requested if sym not in tool_syms]
    substitutions: list[str] = []
    for tr in tool_results or []:
        if tr.get("tool") != "resolve_symbol":
            continue
        args = tr.get("args") if isinstance(tr.get("args"), dict) else {}
        result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
        raw = str(args.get("query") or "").strip().upper()
        resolved = str(result.get("symbol") or "").strip().upper()
        if raw in requested and resolved and raw != resolved:
            substitutions.append(f"{raw}->{resolved}")

    unrequested = sorted(
        sym
        for sym in tool_syms
        if sym not in requested and sym not in _SYMBOL_VALIDATION_SKIP
    )
    if not missing and not substitutions and not unrequested:
        return None

    lines = [
        "▶ SYMBOL VALIDATION FAILED",
        f"  Requested symbol(s): {', '.join(requested)}",
    ]
    if missing:
        lines.append(f"  Missing from executed evidence: {', '.join(missing)}")
    if substitutions:
        lines.append(f"  Blocked substitution(s): {', '.join(substitutions)}")
    if unrequested:
        lines.append(f"  Unrequested symbol(s) in tool evidence: {', '.join(unrequested)}")
    lines.extend([
        "  No technical, fundamental, catalyst, or sector conclusion was inferred from mismatched symbol evidence.",
        "",
        "▶ SOURCE TRAIL",
        *_source_trail_lines(tool_results),
        "",
        "━━━ Not investment advice. For research and learning only. ━━━",
    ])
    return "\n".join(lines)


def _missing_evidence_summary(tool_results: list[dict]) -> list[str]:
    missing: list[str] = []
    for tr in tool_results or []:
        result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
        tool = str(tr.get("tool") or "tool")
        values = result.get("missing_evidence") or []
        if isinstance(values, list):
            missing.extend(f"{tool}.{item}" for item in values if item)
        rows = result.get("results") or result.get("stock_details") or []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                row_symbol = row.get("symbol") or row.get("input_symbol") or "row"
                for item in row.get("missing_evidence") or []:
                    missing.append(f"{tool}.{row_symbol}.{item}")
    return list(dict.fromkeys(missing))


def _append_missing_evidence_guard(answer: str, tool_results: list[dict]) -> str:
    if "▶ MISSING EVIDENCE" in (answer or "").upper():
        return answer
    missing = _missing_evidence_summary(tool_results)
    if not missing:
        return answer
    block = [
        "▶ MISSING EVIDENCE",
        f"  Missing evidence: {', '.join(missing[:12])}",
        "  No unsupported technical, fundamental, catalyst, forensic, broker, or sector conclusion was inferred from missing data.",
    ]
    text = (answer or "").rstrip()
    marker = "━━━ Not investment advice. For research and learning only. ━━━"
    if marker in text:
        before, after = text.rsplit(marker, 1)
        return before.rstrip() + "\n\n" + "\n".join(block) + "\n\n" + marker + after
    return text + "\n\n" + "\n".join(block)


def _apply_response_guardrails(
    query: str,
    intent: str,
    tool_results: list[dict],
    answer: str,
    compressed_symbols: list[str] | None = None,
) -> str:
    required_failure = _validate_required_tools(query, intent, tool_results)
    if required_failure:
        return required_failure
    symbol_failure = _validate_symbol_grounding(query, intent, tool_results, compressed_symbols)
    if symbol_failure:
        return symbol_failure
    return _append_missing_evidence_guard(answer, tool_results)


def _planner_task(
    task_id: str,
    question: str,
    *,
    tool: str | None = None,
    args: dict | None = None,
    derived_from: str | None = None,
    fallback: str = "",
    recovery_plan: str = "",
) -> dict:
    return {
        "id": task_id,
        "question": question,
        "tool": tool,
        "args": args or {},
        "derived_from": derived_from,
        "fallback": fallback,
        "recovery_plan": recovery_plan,
    }


def _planner_execution_plan(tasks: list[dict]) -> list[tuple[str, dict]]:
    plan: list[tuple[str, dict]] = []
    seen: set[tuple[str, str]] = set()
    for task in tasks:
        tool = task.get("tool")
        if not tool:
            continue
        args = dict(task.get("args") or {})
        key = (tool, json.dumps(args, sort_keys=True))
        if key in seen:
            continue
        seen.add(key)
        plan.append((tool, args))
    return plan


def _entity_topic_execution_plan(assessment) -> list[tuple[str, dict]]:
    """Translate direct entity/topic command assessment into deterministic tools."""
    symbol = assessment.canonical_symbol
    topic = assessment.topic or ""
    command = assessment.command
    if not symbol:
        return []
    if command == "/search":
        return [("deep_search", {"symbol": symbol, "context": topic or "full overview"})]
    if command == "/results":
        return [
            ("resolve_symbol", {"query": symbol}),
            ("get_latest_results", {"symbol": symbol}),
        ]
    if command in {"/fno", "/chain", "/oi", "/options"}:
        if command == "/fno":
            return [("get_fno_overview", {"symbol": symbol, "expiry_index": 0})]
        plan = [
            ("get_options_chain", {"symbol": symbol, "expiry_index": 0}),
        ]
        return plan
    if command == "/report":
        report_type = (topic.split() or ["research"])[0]
        return [
            ("resolve_symbol", {"query": symbol}),
            ("get_symbol_snapshot", {"symbol": symbol}),
            ("get_technical_setup", {"symbol": symbol}),
            ("get_sector_context", {"sector_or_symbol": symbol}),
        ] + (
            [("search_latest_catalysts", {"symbol": symbol})]
            if report_type in {"research", "forensic", "fundamental"}
            else []
        )
    if command == "/forensic":
        return [
            ("resolve_symbol", {"query": symbol}),
            ("get_symbol_snapshot", {"symbol": symbol}),
            ("run_forensic_analysis", {"symbol": symbol}),
        ]
    if command in {"/analyze", "/canslim", "/concall", "/chart", "/company-xray", "/company-index", "/strategy-council"}:
        # ── Fix 2026-05-19: /analyze SYMBOL used to return only a thin 4-tool
        # plan (resolve/snapshot/technical/sector), producing a 2-line summary
        # with no fundamentals, no news/catalysts, no forensic, no concall, no
        # deep-search (shareholding/insider/analyst). The full 360° plan was
        # only firing for the agent-generated "comprehensive 360° analysis of
        # X" phrasing, not for user-typed /analyze. Route /analyze to the rich
        # plan; keep the other slash commands on their existing thin plan to
        # avoid behavioural drift in unrelated features.
        if command == "/analyze":
            return _stock_360_prompt_plan(symbol, topic or "")
        return [
            ("resolve_symbol", {"query": symbol}),
            ("get_symbol_snapshot", {"symbol": symbol}),
            ("get_technical_setup", {"symbol": symbol}),
            ("get_sector_context", {"sector_or_symbol": symbol}),
        ]
    if command == "/strategy":
        return [
            ("get_options_chain", {"symbol": symbol, "expiry_index": 0}),
            ("get_strategy_recommendations", {"symbol": symbol}),
        ]
    return []


def _build_market_situation_assessment_plan(query: str, data_mode: str = "historical") -> dict | None:
    q = _routing_query_text(query).lower()

    # ── Fix 2026-05-19: bail out for sector-specific deep dives. Previously
    # prompts like "Analyse the IT sector — breadth, ..." matched on "breadth"
    # + "nifty" and short-circuited the sector router. Defer to the keyword
    # planner's SECTOR_INDEX_MAP route which yields the proper plan.
    #
    # 2026-05-22: Skip the bailout when the user explicitly asks for MTF /
    # confluence / recommendation. Those intents need the universe scan
    # (mtf-universe-scan) regardless of which sector words appear.
    _mtf_intent_hint = (
        "mtf" in q
        or "multi" in q
        or "muti" in q  # tolerate the common 'multi' typo
        or "confluence" in q
        or "timeframe" in q
        or "time frame" in q
        or "recommendation" in q
        or "recommendataion" in q  # tolerate
    )
    if "sector" in q and not _mtf_intent_hint:
        _sector_tokens = (
            "it sector", "sector it", "banking sector", "bank sector",
            "pharma sector", "auto sector", "fmcg sector", "metal sector",
            "metals sector", "realty sector", "real estate sector",
            "energy sector", "oil & gas sector", "oil and gas sector",
            "media sector", "consumer durables sector", "infrastructure sector",
            "defence sector", "defense sector", "chemicals sector",
            "financial services sector", "capital markets sector",
            "healthcare sector", "psu bank sector", "private bank sector",
        )
        if any(tok in q for tok in _sector_tokens):
            return None

    # A named index with breadth/analysis terms is an index-scoped ask, not a
    # broad market-situation ask. Let the deterministic index route attach
    # get_market_breadth(index=...) so NIFTY 500/200/100 do not use global
    # 963-stock universe breadth.
    if _extract_named_index(q, default=""):
        return None

    market_terms = ("market", "nifty", "indices", "index", "breadth", "advance", "decline")
    status_terms = ("current", "status", "today", "now", "live", "pulse", "how is")
    mover_terms = ("top gainer", "top gainers", "gainers", "losers", "movers", "top stocks", "top indices")
    flow_terms = ("fii", "dii", "institutional", "flows", "foreign investors")
    news_terms = ("news", "catalyst", "event", "headline")

    wants_market = any(term in q for term in market_terms)
    wants_status = any(term in q for term in status_terms)
    wants_movers = any(term in q for term in mover_terms)
    wants_breadth = "breadth" in q or "advance" in q or "decline" in q
    wants_flows = any(term in q for term in flow_terms)
    wants_news = any(term in q for term in news_terms)
    # MTF + recommendation intent (PG 2026-05-22): trigger when the user asks
    # for multi-timeframe analysis or a "recommendation report" style ask.
    # These imply a fan-out across a universe + per-symbol confluence scoring
    # that the LLM rarely orchestrates unaided.
    mtf_terms = (
        "multi time frame", "multi-time-frame", "multi timeframe",
        "multi-timeframe", "multitimeframe", " mtf ", "mtf:",
        "mtf scan", "mtf alignment", "mtf confluence",
        "muti time frame", "muti-time", "muti timeframe", "muti-timeframe",
        "multi tf", "multi-tf",
        "across timeframes", "across time frames",
        "weekly and daily", "monthly weekly daily", "weekly + daily",
        "higher timeframe", "higher time frame", "timeframe alignment",
        "timeframe confluence", "tf confluence",
    )
    rec_terms = (
        "recommendation report", "recommendation list", "buy list",
        "top picks", "top buys", "what to buy", "best stocks to buy",
        "confluent setups", "confluence",
    )
    wants_mtf = any(term in q for term in mtf_terms) or (
        f" {q} ".find(" mtf ") != -1
    )
    # Tolerant match: catches typo variants like "recommendataion report".
    wants_recommendation = (
        any(term in q for term in rec_terms)
        or bool(re.search(r"recommend\w*\s+(report|list|view|note)", q))
    )
    wants_plan = any(
        term in q
        for term in (
            "show plan", "show the plan", "include plan", "show steps",
            "step by step", "break it down", "break down", "execution plan",
            "tool plan", "which tools",
        )
    )

    # MTF / recommendation prompts qualify as market-situation requests even
    # without an explicit status word — the user clearly wants market-wide
    # decomposition. Treat the recommendation/MTF flags as primary triggers
    # alongside the original (status|breadth|movers|flows) set. They also
    # bypass the wants_market gate when present, since "find bearish MTF
    # aligned stocks" or "pharma sector MTF confluence" clearly implies a
    # market-wide fan-out even without an explicit market/nifty/index word.
    if not (wants_mtf or wants_recommendation):
        if not wants_market or not (
            wants_status or wants_breadth or wants_movers or wants_flows
        ):
            return None

    tasks = [
        _planner_task(
            "current-index-status",
            "Fetch current Indian index levels and live session breadth.",
            tool="get_live_market_overview",
            fallback="NSE live API broad-market index endpoints + live-analysis-variations for breadth; if unavailable, label data stale and use latest EOD index snapshot.",
            recovery_plan="If the tool is missing, implement a wrapper over nseindia.com index APIs and normalize last, pct_change, advances, declines, and as_of.",
        ),
        _planner_task(
            "db-universe-breadth",
            "Fetch database-backed market breadth and stage distribution.",
            tool="get_market_breadth",
            fallback="Query PostgreSQL scores.stage_snapshots or scores.mv_latest_daily for advances, declines, stage distribution, and average RS.",
            recovery_plan="If no tool exists, add a PostgreSQL query helper that aggregates latest score_date/snapshot_date from scores.*.",
        ),
    ]

    if wants_movers:
        tasks.append(
            _planner_task(
                "top-stock-movers",
                "Fetch top gaining and losing stocks from the broad NSE universe.",
                tool="get_top_gainers_losers",
                args={"index": "NIFTY 500", "top_n": 5, "direction": "both"},
                fallback="Use NSE live-analysis-variations for the gainers/losers buckets; if live source fails, derive movers from market.equity_eod latest daily percent change.",
                recovery_plan="If no tool exists, implement an NSE live-analysis-variations client with PostgreSQL EOD fallback.",
            )
        )
        tasks.append(
            _planner_task(
                "top-index-movers",
                "Derive top gaining and losing indices from the live market overview result.",
                derived_from="get_live_market_overview",
                fallback="If overview lacks full index list, query NSE allIndices or cached global/index snapshots.",
                recovery_plan="If derivation is insufficient, add get_top_index_movers to fetch and rank all NSE index rows directly.",
            )
        )

    if wants_flows:
        tasks.append(
            _planner_task(
                "institutional-flows",
                "Fetch latest FII/DII institutional activity.",
                tool="get_fii_dii_activity",
                fallback="Use cached fetch_fii_dii_flows output or PostgreSQL market.fii_dii_flows if live NSE endpoint is unavailable.",
                recovery_plan="If no tool exists, add a PostgreSQL-first flow reader with NSE refresh fallback.",
            )
        )

    if wants_news:
        tasks.append(
            _planner_task(
                "latest-market-catalysts",
                "Search current market catalysts and news affecting Indian indices.",
                tool="search_latest_catalysts",
                args={"symbol": "NIFTY India market news today"},
                fallback="Search NSE, Moneycontrol, Economic Times, and cached report notes.",
                recovery_plan="If no search tool exists, implement a source-specific news search adapter and store results with URLs.",
            )
        )

    if wants_mtf or wants_recommendation:
        # Universe-wide MTF confluence scan. NIFTY 50 keeps the fan-out
        # bounded (~50 symbols * 5 timeframes); callers can override.
        mtf_direction = "bearish" if any(t in q for t in ("short", "sell", "bearish")) else "bullish"
        tasks.append(
            _planner_task(
                "mtf-universe-scan",
                "Rank an NSE universe by multi-timeframe confluence in the requested direction.",
                tool="scan_mtf_aligned",
                args={
                    "index": "NIFTY 50",
                    "direction": mtf_direction,
                    "min_score": 60,
                    "top_n": 10,
                },
                fallback="If live NSE constituents fetch fails, derive a 50-symbol universe from PostgreSQL scores.mv_latest_daily top-RS rows and pass via 'symbols'.",
                recovery_plan="If scan_mtf_aligned is missing, fall back to calling analyze_mtf per stock from a 20-symbol candidate list derived from run_screener_query('high_rs').",
            )
        )
        tasks.append(
            _planner_task(
                "mtf-top-symbols",
                "For the top scan matches, surface the full per-timeframe MTF stack (direction, score, aligned/dissonant TFs) so the report cites every aligned/dissonant timeframe.",
                derived_from="mtf-universe-scan",
                fallback="Iterate symbols from mtf-universe-scan.top and call analyze_mtf(symbol) for each (cap to 5 to keep runtime bounded).",
                recovery_plan="If analyze_mtf is missing, build the per-stock MTF stack inline using terminal.mtf.compute_mtf.",
            )
        )
        if wants_recommendation:
            tasks.append(
                _planner_task(
                    "recommendation-fundamentals",
                    "Augment the top MTF-aligned symbols with fundamental context (P/E, ROCE, growth) so the recommendation is grounded on both technical and fundamental data.",
                    derived_from="mtf-universe-scan",
                    fallback="If screener.in is unreachable, use compare_stocks(symbols, aspects=['fundamentals']) which reads PG fundamentals.",
                    recovery_plan="If both fail, mark fundamentals as missing in the report rather than inferring.",
                )
            )

    # Attach a confidence score to the plan so downstream renderers can
    # surface a clarification panel for low-confidence routes.
    try:
        from terminal.confidence import score_plan as _score_plan

        triggers = [
            ("status", wants_status),
            ("breadth", wants_breadth),
            ("movers", wants_movers),
            ("flows", wants_flows),
            ("news", wants_news),
            ("mtf", wants_mtf),
            ("recommendation", wants_recommendation),
        ]
        trigger_count = sum(1 for _, present in triggers if present)
        # Detect typo-tolerant route: any of the fuzzy-only mtf aliases.
        typo_route = any(
            term in q for term in ("muti-time", "muti timeframe", "muti-timeframe", "muti time frame")
        ) or bool(re.search(r"recommend\w*\s+(report|list|view|note)", q) and "recommendation" not in q)
        plan_conf = _score_plan(
            decision="situation_assessment_plan",
            trigger_count=trigger_count,
            has_mtf_or_recommendation=bool(wants_mtf or wants_recommendation),
            has_market_word=bool(wants_market),
            typo_route=typo_route,
            extra_signals={
                "triggers": {name: present for name, present in triggers},
                "wants_market": wants_market,
                "wants_plan": wants_plan,
            },
        )
    except Exception:
        plan_conf = None

    return {
        "kind": "market_situation_assessment",
        "tasks": tasks,
        "execution_order": [task["id"] for task in tasks],
        "mode": data_mode,
        "show_plan": wants_plan,
        "confidence": plan_conf.to_dict() if plan_conf is not None else None,
    }


def _extract_fno_symbol(query: str, fallback_symbol: str = "") -> str:
    """Extract an index/stock symbol for F&O tools without treating F&O terms as symbols.

    Resolution order:
      1. Known multi-word index aliases (banknifty / finnifty / etc).
      2. The first token that is present in the NSE symbol universe
         AND is NOT a known F&O option-type abbreviation (CE, PE, ATM, ITM, OTM).
      3. The first token not in the F&O-jargon skip list (back-compat fallback),
         again excluding option-type abbreviations.
      4. fallback_symbol (passed by caller from compound-query context).
      5. Default to NIFTY.
    """
    # ── Option-type tokens that must NEVER be used as underlying symbols ──────
    # CE = Call European (also NSE-listed Crompton Greaves), PE = Put European,
    # ATM/ITM/OTM = moneyness labels. These appear in F&O questions but are NOT
    # underlying index/stock symbols.
    _OPTION_ABBREVS = {
        "CE", "PE", "ATM", "ITM", "OTM",
        "CALL", "PUT", "CALLS", "PUTS",
        "EXPIRY", "STRIKE", "STRIKES",
        "STRADDLE", "STRANGLE", "SPREAD", "CONDOR", "BUTTERFLY",
        "DELTA", "GAMMA", "THETA", "VEGA", "IV",
        "LONGSTRADDLE", "SHORTSTRADDLE",
    }

    text = query or ""
    # Strip "CE/PE" and "CE & PE" compound forms so they don't pollute tokenisation
    text = re.sub(r"\bCE\s*/\s*PE\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bPE\s*/\s*CE\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bCE\s+&\s+PE\b",  "", text, flags=re.IGNORECASE)

    q = text.lower()
    if "banknifty" in q or "bank nifty" in q or "nifty bank" in q:
        return "BANKNIFTY"
    if "finnifty" in q or "fin nifty" in q:
        return "FINNIFTY"
    if "midcpnifty" in q or "midcap nifty" in q:
        return "MIDCPNIFTY"
    if "nifty" in q:
        return "NIFTY"

    bank_phrase_match = re.search(r"\b([A-Za-z][A-Za-z0-9&-]{2,20})\s+BANK\b", text, flags=re.IGNORECASE)
    if bank_phrase_match:
        phrase = bank_phrase_match.group(0).strip()
        try:
            resolved = resolve_symbol(phrase)
            symbol = str(resolved.get("symbol") or "").strip().upper() if isinstance(resolved, dict) else ""
        except Exception:
            symbol = ""
        if symbol:
            return symbol

    phrases = [
        phrase
        for phrase in (_symbol_phrase_after_preposition(text), _leading_company_phrase(text))
        if phrase
    ]
    phrases = sorted(dict.fromkeys(phrases), key=lambda item: len(item.split()), reverse=True)
    for phrase in phrases:
        try:
            resolved = resolve_symbol(phrase)
            symbol = str(resolved.get("symbol") or "").strip().upper() if isinstance(resolved, dict) else ""
        except Exception:
            symbol = ""
        if symbol:
            return symbol

    skip = {
        "F", "O", "FO", "FNO", "F&O",
        "AND", "FOR", "THE", "WITH", "GIVE", "COMPREHENSIVE",
        "OVERVIEW", "OPTION", "OPTIONS", "CHAIN", "PCR", "MAX", "PAIN", "TOP", "OI",
        "STRIKES", "FUTURES", "BASIS", "COST", "CARRY", "ROLL", "ROLLOVER", "RECOMMEND",
        "BEST", "STRATEGY", "CURRENT", "DATA", "OPEN", "INTEREST",
        # OI-context keywords that look like tickers
        "SHOW", "KEY", "WHERE", "SUPPORT", "RESISTANCE", "LEVELS", "BUILDING",
        "UNWINDING", "TODAY", "INTRADAY", "SWING", "WHICH", "THAT", "WHAT",
        "ANALYSE", "ANALYZE", "CHECK", "RUN", "GET", "FIND",
    } | _OPTION_ABBREVS  # CE, PE, ATM, ITM, OTM etc. always excluded
    tokens = [t.upper() for t in re.findall(r"\b[A-Z][A-Z0-9&-]{1,12}\b", text)]
    candidates = [t for t in tokens if t not in skip]

    # Prefer tokens that exist in the NSE symbol universe — this stops jargon
    # like "F&O" being treated as a ticker when a real symbol (HINDUNILVR,
    # RELIANCE, etc.) appears later in the prompt.
    try:
        from terminal.entity_resolution import _load_symbol_universe
        universe = _load_symbol_universe()
    except Exception:
        universe = frozenset()
    for token in candidates:
        # Extra guard: skip tokens that are option-type abbreviations even if they
        # happen to appear in the NSE universe (e.g. CE = Crompton Greaves).
        if token in _OPTION_ABBREVS:
            continue
        if universe and token in universe:
            return token
    for token in candidates:
        if token in _OPTION_ABBREVS:
            continue
        return token
    # Use caller-supplied context symbol (e.g. from compound-query Part N-1)
    if fallback_symbol:
        return fallback_symbol
    return "NIFTY"


def _intraday_options_trade_plan(symbol: str, timeframe: str = "15m") -> list[tuple[str, dict]]:
    """Evidence plan for intraday options trade setup synthesis."""
    return [
        ("resolve_symbol", {"query": symbol}),
        ("get_nse_intraday_snapshot", {"symbol": symbol}),
        ("get_intraday_levels", {"symbol": symbol, "timeframe": timeframe}),
        ("get_fno_overview", {"symbol": symbol, "expiry_index": 0}),
        ("get_options_chain", {"symbol": symbol, "expiry_index": 0}),
        ("explain_intraday_setup", {"symbol": symbol, "timeframe": timeframe}),
        ("get_intraday_analysis", {"symbol": symbol, "interval": timeframe}),
    ]


# --- Compound-query splitter ------------------------------------------------
# Splits a multi-question prompt into independent sub-queries. Conservative
# by design: only splits on strong sentence/clause separators when each
# resulting fragment looks substantive (>=3 words). Leaves single-question
# prompts unchanged.
_COMPOUND_SPLIT_RE = re.compile(
    r"(?<=[?!.])\s+(?=[A-Za-z/])"          # sentence boundary followed by start-of-clause
    r"|\s+(?:and also|also|then|next)\s+"    # explicit chaining adverbs
    r"|\s*;\s*",                                # semicolons
    flags=re.IGNORECASE,
)


def _split_compound_query(text: str) -> list[str]:
    """Return cleaned list of sub-queries; single-element list when no split.

    Heuristics:
      * never split slash-commands (e.g. "/scan NIFTY 50 vwap")
      * never split short prompts (<10 words) — likely a single question
      * never split if any fragment is too short (<3 words) — false positive
      * strip trailing whitespace / punctuation on each part
    """
    raw = (text or "").strip()
    if not raw or raw.startswith("/"):
        return [raw] if raw else []
    if re.search(r"\brun\s+a\s+comprehensive\s+deep\s+search\s+for\s+[A-Z][A-Z0-9&-]{1,20}\b", raw, flags=re.IGNORECASE):
        return [raw]
    if "deep_search" in raw:
        return [raw]
    if re.search(r"\.\s+keep\s+the\s+answer\b", raw, flags=re.IGNORECASE):
        return [raw]
    # Skip internal/programmatic prompts: multi-line text (the morning
    # briefing prompt, RIC recipes, etc.) and very long inputs are not
    # natural conversational compound questions — they're templates.
    # Changed: added newline + length guard to stop the morning briefing
    # being shredded into 5 fake "parts".
    if "\n" in raw or len(raw) > 400 or len(raw.split()) > 40:
        return [raw]
    if any(
        term in raw.lower()
        for term in (
            "run_forensic_analysis",
            "forensic analysis",
            "beneish",
            "piotroski",
            "altman",
            "earnings manipulation",
            "my portfolio",
            "portfolio sector distribution",
            "companies are announcing quarterly results",
            "quarterly results this week",
            "global markets overnight",
            "asian, and european markets overnight",
        )
    ):
        return [raw]
    # Cheap pre-filter: if there are no plausible separators, return early
    # without paying for the regex split.
    if not re.search(r"[?!.;]|\b(?:and also|also then|then|next)\b", raw, flags=re.IGNORECASE):
        return [raw]
    if len(raw.split()) < 6:
        return [raw]
    parts = [p.strip(" \t,.;") for p in _COMPOUND_SPLIT_RE.split(raw) if p and p.strip()]
    if len(parts) <= 1:
        return [raw]
    # Reject the split if any fragment is too short — likely a false positive
    # (e.g. "Mr. Smith said hi" should not become ["Mr", "Smith said hi"]).
    # Threshold is intentionally tight (≥2 words) so single-word fragments
    # like "Mr" / "Inc" don't pass, while legitimate 2-word commands like
    # "show breakouts" / "top gainers" / "high RS" still allow the split.
    if any(len(p.split()) < 2 for p in parts):
        return [raw]
    return parts


def _extract_youtube_url(text: str) -> str:
    match = re.search(r"https?://(?:www\.|m\.)?(?:youtube\.com|youtu\.be)/\S+", text or "", re.I)
    return match.group(0).rstrip(".,);]") if match else ""


def _extract_youtube_selection(text: str) -> str:
    return re.sub(r"^/youtube\b", "", text or "", flags=re.I).strip()


def _extract_youtube_transcribe_args(text: str) -> tuple[str, str]:
    selection = re.sub(r"^/youtube\s+transcribe\b", "", text or "", flags=re.I).strip()
    backend = "local"
    match = re.search(r"(?:^|\s)--backend(?:=|\s+)(local|auto)\b", selection, flags=re.I)
    if match:
        backend = match.group(1).lower()
        selection = (selection[:match.start()] + " " + selection[match.end():]).strip()
    return selection, backend


def _stock_fundamental_chain_requested(q: str) -> bool:
    q = (q or "").lower()
    return any(term in q for term in (
        "deep analysis", "deep dive", "detailed analysis", "full analysis",
        "fundamental", "fundamentals", "valuation", "ratios", "p/e", "pe ratio",
        "p/b", "pb ratio", "roe", "roce", "debt/equity", "debt to equity",
        "quarterly numbers", "quarterly financials", "financial statements",
        "balance sheet", "cash flow", "p&l", "profit and loss",
        "earnings", "latest results", "quarterly results", "annual results",
    ))


def _ensure_fundamental_source_chain(plan: list[tuple[str, dict]], sym: str) -> None:
    """Ensure PG cache, Screener, then latest-results evidence run in that order."""
    source_tools = {"get_cached_financials", "scrape_screener_in", "get_latest_results"}
    first_source_idx = next(
        (idx for idx, (name, _args) in enumerate(plan) if name in source_tools),
        len(plan),
    )
    plan[:] = [(name, args) for name, args in plan if name not in source_tools]
    chain = [
        ("get_cached_financials", {"symbol": sym}),
        ("scrape_screener_in", {"symbol": sym}),
        ("get_latest_results", {"symbol": sym}),
    ]
    for offset, item in enumerate(chain):
        plan.insert(first_source_idx + offset, item)


def _first_valid_tool_symbol(tool_results: list[dict]) -> str:
    """Return the first trusted symbol produced by executed evidence tools."""
    for tr in tool_results or []:
        result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
        if tr.get("tool") == "resolve_symbol" and result.get("symbol") and not result.get("error"):
            return str(result["symbol"]).upper()
    symbols = sorted(_tool_symbols(tool_results or []))
    return symbols[0] if symbols else ""


def _missing_fundamental_chain_plan(tool_results: list[dict], query: str) -> list[tuple[str, dict]]:
    """Plan missing PG/Screener/latest-results tools for stock fundamentals."""
    if not _stock_fundamental_chain_requested(query):
        return []
    sym = _first_valid_tool_symbol(tool_results)
    if not sym:
        return []
    full_plan: list[tuple[str, dict]] = []
    _ensure_fundamental_source_chain(full_plan, sym)
    executed = {str(tr.get("tool")) for tr in tool_results or []}
    return [(name, args) for name, args in full_plan if name not in executed]


def _with_dynamic_stock_evidence(plan: list[tuple[str, dict]], q: str, symbol: str) -> list[tuple[str, dict]]:
    """Keep stock_brief plans aligned with dynamic evidence validation."""
    sym = (symbol or "").upper()
    if not sym:
        return plan
    existing = {name for name, _ in plan}

    def add_once(name: str, args: dict) -> None:
        if name not in existing:
            plan.append((name, args))
            existing.add(name)

    if any(term in q for term in ("news", "catalyst", "catalysts", "recent announcement")):
        add_once("search_latest_catalysts", {"symbol": sym})
    if any(term in q for term in ("broker", "analyst target", "target price", "rating", "brokerage", "analyst views")):
        add_once("search_broker_research", {"symbol": sym})
    if any(term in q for term in ("concall", "earnings call", "management commentary", "guidance")):
        add_once("search_concall_transcripts", {"symbol": sym})
    if any(term in q for term in ("forensic", "red flag", "red flags", "manipulation", "earnings quality")):
        add_once("run_forensic_analysis", {"symbol": sym})
    if _stock_fundamental_chain_requested(q):
        _ensure_fundamental_source_chain(plan, sym)
        existing = {name for name, _ in plan}
    if any(term in q for term in (
        "latest results", "quarterly results", "quarterly result",
        "q1 results", "q2 results", "q3 results", "q4 results",
        "annual results", "yearly results",
        "earnings results", "earnings report",
        "p&l statement", "profit and loss",
        "balance sheet", "cash flow statement", "financial statements",
        "fundamental analysis", "quarterly numbers", "quarterly financials",
    )):
        add_once("get_latest_results", {"symbol": sym})
    return plan


def _stock_360_prompt_symbol(query: str) -> str:
    """Extract the symbol from Agent-generated 360 stock-analysis/report prompts."""
    text = re.sub(r"[*_`]+", "", query or "")
    patterns = (
        r"\bcomprehensive\s+360(?:°|\s*degree)?\s+analysis\s+(?:of|for)\s+([A-Z][A-Z0-9&-]{1,20})\b",
        r"\bcomprehensive(?:\s+institutional-grade)?\s+360(?:°|\s*degree)?\s+research\s+report\s+on\s+([A-Z][A-Z0-9&-]{1,20})\b",
    )
    symbol = ""
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            symbol = match.group(1).upper()
            break
    return symbol if re.fullmatch(r"[A-Z0-9&-]{2,20}", symbol) else ""


def _stock_360_prompt_plan(symbol: str, query: str) -> list[tuple[str, dict]]:
    sym = symbol.upper()
    plan: list[tuple[str, dict]] = [
        ("resolve_symbol", {"query": sym}),
        ("get_symbol_snapshot", {"symbol": sym}),
        ("scrape_screener_in", {"symbol": sym}),
        ("get_technical_setup", {"symbol": sym}),
        ("comprehensive_stock_research", {"symbol": sym}),
        ("run_forensic_analysis", {"symbol": sym}),
        ("search_shareholding_analysis", {"symbol": sym}),
        ("search_concall_transcripts", {"symbol": sym}),
        ("analyze_concall_sentiment", {"symbol": sym}),
        ("search_latest_catalysts", {"symbol": sym}),
        ("get_sector_context", {"sector_or_symbol": sym}),
        ("search_broker_research", {"symbol": sym}),
        (
            "deep_search",
            {
                "symbol": sym,
                "verticals": ["shareholding", "insider_trades", "analyst_coverage"],
                "context": "shareholding, insider trades, analyst targets",
            },
        ),
    ]
    return _with_dynamic_stock_evidence(plan, (query or "").lower(), sym)


def _analyze_command_symbols(query: str) -> list[str]:
    if not re.match(r"^\s*/analy[sz]e\b", query or "", flags=re.IGNORECASE):
        return []
    text = re.sub(r"^/analy[sz]e\b", "", query or "", flags=re.IGNORECASE).strip()
    if not re.search(r"[,;/]", text):
        return []
    if not text or text.lower().startswith(("http://", "https://")) or any(
        text.lower().endswith(ext) for ext in (".pdf", ".docx", ".doc", ".txt", ".csv", ".md", ".xlsx")
    ):
        return []
    symbols = [
        token.upper()
        for token in re.split(r"[\s,;/]+", text)
        if re.fullmatch(r"[A-Z0-9&-]{2,12}", token.upper())
        and token.lower() not in {"html", "pdf", "md"}
    ]
    return list(dict.fromkeys(symbols))


def _generated_deep_search_prompt(query: str) -> dict | None:
    """Parse Agent-generated `/search SYMBOL ...` prompts without treating verbs as tickers."""
    text = query or ""
    match = re.search(
        r"\brun\s+a\s+comprehensive\s+deep\s+search\s+for\s+([A-Z][A-Z0-9&-]{1,20})\b",
        text,
        flags=re.IGNORECASE,
    )
    if not match or "deep_search" not in text.lower():
        return None
    symbol = match.group(1).upper()
    if not re.fullmatch(r"[A-Z0-9&-]{2,20}", symbol):
        return None
    context = "full overview"
    ctx_match = re.search(r"\bContext:\s*['\"]?([^'\".]+)", text, flags=re.IGNORECASE)
    if ctx_match:
        context = ctx_match.group(1).strip() or context
    return {
        "intent": "entity_topic_command",
        "plan": [("deep_search", {"symbol": symbol, "context": context})],
    }


def _word_number(value: str) -> int | None:
    mapping = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "ten": 10,
        "fourteen": 14,
    }
    value = (value or "").strip().lower()
    if value.isdigit():
        return int(value)
    return mapping.get(value)


def _results_feed_window_days(q: str) -> int | None:
    """Detect symbol-less/latest-results feed requests and return a bounded day window."""
    text = (q or "").lower()
    if not any(term in text for term in ("result", "results", "earnings")):
        return None
    if (
        "event" in text
        or "corporate action" in text
        or "corporate actions" in text
        or "dividend" in text
        or "agm" in text
        or "ex-date" in text
        or "ex date" in text
    ):
        return None

    if "today" in text or "yesterday" in text:
        return 2
    if "fortnight" in text:
        return 14
    if "this month" in text or "last month" in text or "past month" in text or "previous month" in text:
        return 30
    if "this week" in text:
        return 7

    match = re.search(
        r"\b(?:in|for|over|during|within)?\s*(?:the\s+)?(?:last|past|previous)\s+"
        r"(?:(\d+|one|two|three|four|five|six|seven|ten|fourteen)\s+)?"
        r"(days?|weeks?|months?)\b",
        text,
    )
    if match:
        amount = _word_number(match.group(1) or "1") or 1
        unit = match.group(2)
        multiplier = 30 if unit.startswith("month") else 7 if unit.startswith("week") else 1
        return min(90, max(1, amount * multiplier))

    feed_terms = (
        "latest results", "latest result",
        "who reported", "who has reported", "who all reported",
        "results announced", "results posted", "results filed",
        "results released", "results submitted",
        "companies reported", "companies that reported",
        "companies announced results", "companies posted results", "companies filed results",
        "companies submitted results", "companies that announced", "announced results",
        "announced their results", "earnings posted", "results feed",
        "recent results", "recently reported", "result announcements", "results announcements",
    )
    if any(term in text for term in feed_terms):
        return 7
    return None


def _results_feed_slash_days(query: str) -> int | None:
    """Parse `/results-feed [weeks]` style commands into a bounded day window."""
    text = (query or "").strip()
    if not re.match(r"^/(?:results-feed|resultsfeed|latest-results)\b", text, flags=re.IGNORECASE):
        return None
    try:
        parts = shlex.split(text)
    except ValueError:
        parts = text.split()
    if not parts:
        return None
    command = parts[0].lower()
    if command not in {"/results-feed", "/resultsfeed", "/latest-results"}:
        return None
    weeks = 2
    args = parts[1:]
    for i, token in enumerate(args):
        lower = token.lower()
        value = None
        if lower in {"--weeks", "-w", "weeks"} and i + 1 < len(args):
            value = args[i + 1]
        elif lower.startswith("--weeks="):
            value = lower.split("=", 1)[1]
        else:
            compact = re.fullmatch(r"(\d+)(?:w|wk|wks|week|weeks)?", lower)
            if compact:
                value = compact.group(1)
        if value is None:
            continue
        try:
            weeks = int(value)
            break
        except ValueError:
            continue
    return min(90, max(1, weeks * 7))


def _keyword_intent(query: str, data_mode: str = "historical", context_symbol: str = "") -> dict:
    """Detect intent and build a tool plan from keywords alone."""
    routing_text = _routing_query_text(query)
    q = routing_text.lower()

    # Agent-generated tool-execution prompts (e.g. /analyze expansion) must go to the
    # LLM path so the model can actually call analyze_document with the supplied source,
    # rather than being mis-classified as a stock_brief or market_situation_assessment.
    if "analyze_document tool with source=" in q or "use the analyze_document tool" in q:
        return {"intent": "llm_driven", "plan": []}

    if _is_greeting_query(q):
        return {"intent": "greeting", "plan": []}

    if _contains_placeholder_symbol(routing_text):
        return {"intent": "placeholder_symbol_request", "plan": []}

    ric_match = re.match(r"^\s*/ric\s+([a-z0-9-]+)(?:\s+(.+))?\s*$", routing_text, flags=re.IGNORECASE)
    if ric_match:
        ric_key = ric_match.group(1).lower()
        ric_arg = (ric_match.group(2) or "").strip()
        if ric_key == "index-pulse":
            index_name = ric_arg or "NIFTY 50"
            return {
                "intent": "index_status",
                "plan": [
                    ("get_index_snapshot", {"index_name": index_name}),
                    ("get_market_breadth", {"index": index_name}),
                ],
            }
        if ric_key == "sector-xray":
            return {
                "intent": "sector_deep_dive",
                "plan": [("get_sector_context", {"sector_or_symbol": ric_arg or "IT"})],
            }
        if ric_key == "breakout-hunter":
            return {
                "intent": "screener",
                "plan": [("run_screener_query", {"screen_type": "breakouts"})],
            }
        symbol_arg = (re.split(r"[\s,]+", ric_arg.strip())[0] if ric_arg else "RELIANCE").upper()
        if not re.fullmatch(r"[A-Z0-9&-]{2,20}", symbol_arg):
            symbol_arg = "RELIANCE"
        return {
            "intent": "stock_brief",
            "plan": _with_dynamic_stock_evidence([
                ("resolve_symbol", {"query": symbol_arg}),
                ("get_symbol_snapshot", {"symbol": symbol_arg}),
                ("get_technical_setup", {"symbol": symbol_arg}),
                ("get_sector_context", {"sector_or_symbol": symbol_arg}),
            ], q, symbol_arg),
        }

    stock_360_symbol = _stock_360_prompt_symbol(routing_text)
    if stock_360_symbol:
        return {
            "intent": "stock_brief",
            "plan": _stock_360_prompt_plan(stock_360_symbol, routing_text),
        }

    if _is_document_link_followup(q):
        return {"intent": "document_link_help", "plan": []}

    generated_deep_search = _generated_deep_search_prompt(routing_text)
    if generated_deep_search:
        return generated_deep_search

    results_feed_slash_days = _results_feed_slash_days(routing_text)
    if results_feed_slash_days is not None:
        return {"intent": "results_feed", "plan": [
            ("get_latest_results_feed", {"days_back": results_feed_slash_days, "limit": 50}),
        ]}

    visual_scan_match = re.search(
        r"^(?:/visual-scan|/visual_scan|visual scan(?:\s+of)?|perform a visual scan of|deep visual qa of)\s+(.+)$",
        routing_text.strip(),
        flags=re.IGNORECASE,
    )
    if visual_scan_match:
        raw_symbol = visual_scan_match.group(1).strip(" .,:;")
        raw_symbol = re.sub(r"\bchart\b", "", raw_symbol, flags=re.IGNORECASE).strip()
        sym_q = _primary_symbol_query([raw_symbol], [], raw_symbol)
        return {"intent": "visual_scan", "plan": [("run_visual_scan", {"symbol": sym_q.upper()})]}

    analyze_symbols = _analyze_command_symbols(routing_text)
    if len(analyze_symbols) >= 2:
        return {
            "intent": "stock_comparison",
            "plan": [("compare_stocks", {"symbols": analyze_symbols[:5], "aspects": ["both"]})],
        }

    if q.startswith("/youtube") or "youtube.com/watch" in q or "youtu.be/" in q:
        if q.startswith("/youtube transcribe"):
            selection, backend = _extract_youtube_transcribe_args(query)
            youtube_url = _extract_youtube_url(selection)
            if youtube_url:
                return {"intent": "youtube_video_transcription", "plan": [
                    ("analyze_youtube_video", {"source": youtube_url, "persist": True, "transcribe": True, "transcription_backend": backend}),
                    ("list_youtube_channels", {}),
                ]}
            if not selection or selection.lower() in {"channels", "channel", "list", "show", "show channels"}:
                return {"intent": "youtube_channels", "plan": [("list_youtube_channels", {})]}
            return {"intent": "youtube_channel_transcription", "plan": [
                ("analyze_youtube_channel_latest", {"selection": selection, "persist": True, "transcribe": True, "transcription_backend": backend}),
                ("list_youtube_channels", {}),
            ]}
        selection = _extract_youtube_selection(query)
        if (not selection or selection.lower() in {"channels", "channel", "list", "show", "show channels"}) and not _extract_youtube_url(query):
            return {"intent": "youtube_channels", "plan": [("list_youtube_channels", {})]}
        youtube_url = _extract_youtube_url(query)
        if youtube_url:
            return {"intent": "youtube_video_analysis", "plan": [
                ("analyze_youtube_video", {"source": youtube_url, "persist": True}),
                ("list_youtube_channels", {}),
            ]}
        return {"intent": "youtube_channel_latest", "plan": [
            ("analyze_youtube_channel_latest", {"selection": selection, "persist": True}),
            ("list_youtube_channels", {}),
        ]}

    if _is_morning_briefing_query(q):
        return {
            "intent": "startup_morning_briefing",
            "plan": [
                ("get_global_market_assessment", {}),
                ("get_index_snapshot", {"index_name": "NIFTY 50"}),
                ("get_index_snapshot", {"index_name": "NIFTY BANK"}),
                ("get_live_market_overview", {}),
                ("get_market_breadth", {}),
                ("get_top_gainers_losers", {"index": "NIFTY 50", "top_n": 3, "direction": "both"}),
                ("get_fii_dii_activity", {}),
            ],
        }

    if data_mode == "intraday" and "intraday" in q and not any(w in q for w in ("scan", "screener")) and re.search(r"\bnifty\s*50\b|\bnifty50\b|\bnifty\b", q):
        symbol = "BANKNIFTY" if ("bank nifty" in q or "nifty bank" in q or "banknifty" in q) else "NIFTY50"
        return {"intent": "intraday_setup", "plan": [
            ("resolve_symbol", {"query": symbol}),
            ("explain_intraday_setup", {"symbol": symbol}),
            ("get_nse_intraday_snapshot", {"symbol": symbol}),
            ("get_intraday_analysis", {"symbol": symbol}),
        ]}

    # Removed 2026-05-19: legacy thin IT-only route returned just
    # get_sector_context, causing prompt p21 to skip index snapshot + breadth.
    # Generic SECTOR_INDEX_MAP route below now handles IT with full plan.

    if "dashboard" in q and any(term in q for term in ("market", "nifty", "india", "current", "narrative")):
        return {
            "intent": "market_dashboard",
            "plan": [
                ("get_live_market_overview", {}),
                ("get_market_breadth", {}),
                ("get_top_gainers_losers", {"index": "NIFTY 500", "top_n": 5, "direction": "both"}),
                ("get_fii_dii_activity", {}),
                ("get_global_market_assessment", {}),
                ("search_latest_catalysts", {"symbol": "NIFTY India market today"}),
            ],
        }

    fno_terms = (
        "f&o", "fno", "option chain", "options chain", "option data", "options data",
        "pcr", "put call", "put-call", "max pain", "open interest", " oi ",
        "top oi", "futures basis", "cost of carry", "rollover", "futures premium",
        "futures discount", "options strategy", "option strategy", "long straddle",
        "option trading", "options trading", "option trade", "options trade",
        "ce setup", "pe setup", "call setup", "put setup",
        "short straddle", "straddle", "strangle", "iron condor", "butterfly",
    )
    q_padded = f" {q} "
    explicit_options_trade_terms = (
        "option trading", "options trading", "option trade", "options trade",
        "ce setup", "pe setup", "call setup", "put setup",
    )
    has_option_token = any(term in q_padded for term in (" option ", " options ", " ce ", " pe ", " call ", " put "))
    has_options_trade_context = has_option_token and any(
        term in q
        for term in (
            "good for options", "support", "resistance", "target", "targets",
            " stop ", "stop loss", "stop-loss", "buildup", "build-up",
        )
    )
    explicit_options_trade_request = (
        any(term in q for term in explicit_options_trade_terms)
        or has_options_trade_context
    )
    if (
        data_mode == "intraday"
        and not explicit_options_trade_request
        and any(term in q_padded for term in (" f&o ", " fno ", " derivatives "))
        and any(term in q for term in ("intraday", "trade setup", "tradesetup", "trading setup"))
    ):
        symbol = _extract_fno_symbol(routing_text, fallback_symbol=context_symbol)
        timeframe = _extract_intraday_timeframe(q)
        return {"intent": "intraday_setup", "plan": [
            ("resolve_symbol", {"query": symbol}),
            ("get_nse_intraday_snapshot", {"symbol": symbol}),
            ("get_fno_overview", {"symbol": symbol, "expiry_index": 0}),
            ("explain_intraday_setup", {"symbol": symbol, "timeframe": timeframe}),
            ("get_intraday_analysis", {"symbol": symbol, "interval": timeframe}),
        ]}
    if any(term in q_padded for term in fno_terms) or explicit_options_trade_request:
        symbol = _extract_fno_symbol(routing_text, fallback_symbol=context_symbol)
        try:
            resolved = resolve_symbol(symbol)
            if isinstance(resolved, dict) and resolved.get("symbol") and _is_trusted_symbol_resolution(resolved):
                symbol = str(resolved["symbol"]).upper()
        except Exception:
            pass
        if data_mode == "intraday" and explicit_options_trade_request and any(
            term in q
            for term in (
                "intraday", "trade setup", "tradesetup", "trading setup",
                "live price", "live prices", "live pricies", "price", "prices", "pricies",
                "support", "resistance", "target", "stop loss", "stop-loss",
            )
        ) and symbol not in {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"}:
            timeframe = _extract_intraday_timeframe(q)
            return {
                "intent": "intraday_options_trade_plan",
                "plan": _intraday_options_trade_plan(symbol, timeframe),
            }
        plan = [("get_fno_overview", {"symbol": symbol, "expiry_index": 0})]
        return {"intent": "fno_overview", "plan": plan}

    company_identity_match = re.search(
        r"^\s*resolve\s+([A-Z][A-Z0-9&-]{1,12})\s+to\s+its\s+company\s+identity\b",
        routing_text,
        flags=re.IGNORECASE,
    )
    if company_identity_match:
        sym_q = company_identity_match.group(1).strip().upper()
        return {
            "intent": "company_identity",
            "plan": [
                ("resolve_symbol", {"query": sym_q}),
                ("get_symbol_snapshot", {"symbol": sym_q}),
                ("get_sector_context", {"sector_or_symbol": sym_q}),
            ],
        }

    sector_analysis_match = re.search(r"\bsector\s+analysis\s+for\s+([a-z][a-z\s&-]{1,40})(?:[:?.]|$)", q)
    if sector_analysis_match:
        sector_name = sector_analysis_match.group(1).strip()
        sector_aliases = {
            "it": "IT",
            "information technology": "IT",
            "bank": "Bank",
            "banking": "Bank",
            "pharma": "Pharma",
            "auto": "Auto",
            "metal": "Metals",
            "metals": "Metals",
            "fmcg": "FMCG",
            "real estate": "Real Estate",
            "realty": "Real Estate",
            "energy": "Energy",
        }
        return {"intent": "sector_scan", "plan": [("get_sector_context", {"sector_or_symbol": sector_aliases.get(sector_name, sector_name.upper())})]}

    stock_360_symbol = _stock_360_prompt_symbol(routing_text)
    if stock_360_symbol:
        return {
            "intent": "stock_brief",
            "plan": _stock_360_prompt_plan(stock_360_symbol, routing_text),
        }

    assessment_plan = _build_market_situation_assessment_plan(query, data_mode=data_mode)
    if assessment_plan:
        return {
            "intent": "market_situation_assessment",
            "plan": _planner_execution_plan(assessment_plan["tasks"]),
            "assessment_plan": assessment_plan,
        }

    if _is_market_knowledge_query(query):
        return {
            "intent": "market_knowledge",
            "plan": [("search_market_knowledge", {"query": _market_knowledge_query(query)})],
        }

    # Global market assessment
    if _is_global_query(q):
        return {
            "intent": "global_market_assessment",
            "plan": [("get_global_market_assessment", {})],
        }

    # Breadth / market overview. Keep this before stock extraction so
    # "Market overview" is not interpreted as an OVERVIEW ticker.
    breadth_words = [
        "market overview", "overview of market", "breadth", "advance decline",
        "a/d", "market today", "market outlook", "nifty direction",
        "overall market", "how is market", "market status", "market pulse",
        "pulse on the market", "pulse of the market",
    ]
    mover_words = [
        "top gainer", "top gainers", "gainers", "losers", "movers",
        "top stocks", "top indices", "indices", "index movers",
    ]

    # ── Fix 2026-05-19: route sector-deep-dive prompts BEFORE breadth check ──
    # Bug: prompts like "Analyse the IT sector — breadth, stage distribution, RS
    # vs Nifty, leaders and laggards, and key themes" (prompt-library p21)
    # used to hit `breadth_words` first and return the generic market overview,
    # never invoking get_sector_context. We pre-route any query that names a
    # specific sector (token "<sector> sector" or "sector ... <name>") to
    # get_sector_context + get_index_snapshot for that sector's NIFTY index.
    SECTOR_INDEX_MAP = {
        "it":          ("IT",          "NIFTY IT"),
        "banking":     ("Banking",     "NIFTY BANK"),
        "bank":        ("Banking",     "NIFTY BANK"),
        "psu bank":    ("PSU Banking", "NIFTY PSU BANK"),
        "private bank":("Private Banking", "NIFTY PRIVATE BANK"),
        "pharma":      ("Pharma",      "NIFTY PHARMA"),
        "healthcare":  ("Healthcare",  "NIFTY HEALTHCARE INDEX"),
        "auto":        ("Auto",        "NIFTY AUTO"),
        "fmcg":        ("FMCG",        "NIFTY FMCG"),
        "metal":       ("Metals",      "NIFTY METAL"),
        "metals":      ("Metals",      "NIFTY METAL"),
        "realty":      ("Realty",      "NIFTY REALTY"),
        "real estate": ("Realty",      "NIFTY REALTY"),
        "energy":      ("Energy",      "NIFTY ENERGY"),
        "oil & gas":   ("Oil & Gas",   "NIFTY OIL & GAS"),
        "oil and gas": ("Oil & Gas",   "NIFTY OIL & GAS"),
        "media":       ("Media",       "NIFTY MEDIA"),
        "consumer durables": ("Consumer Durables", "NIFTY CONSUMER DURABLES"),
        "infrastructure":    ("Infrastructure",    "NIFTY INFRASTRUCTURE"),
        "defence":     ("Defence",     "NIFTY INDIA DEFENCE"),
        "defense":     ("Defence",     "NIFTY INDIA DEFENCE"),
        "chemicals":   ("Chemicals",   "NIFTY CHEMICALS"),
        "financial services": ("Financial Services", "NIFTY FINANCIAL SERVICES"),
        "capital markets":    ("Capital Markets",    "NIFTY CAPITAL MARKETS"),
    }
    if "sector" in q:
        # Match "<name> sector" or "sector ... <name>" (longest names first so
        # "real estate" beats "estate" and "private bank" beats "bank").
        sector_hit = None
        for name in sorted(SECTOR_INDEX_MAP.keys(), key=len, reverse=True):
            if f"{name} sector" in q or f"sector {name}" in q or (
                "sector" in q and re.search(rf"\b{re.escape(name)}\b", q)
            ):
                sector_hit = name
                break
        if sector_hit:
            canonical, idx_name = SECTOR_INDEX_MAP[sector_hit]
            return {
                "intent": "sector_deep_dive",
                "plan": [
                    ("get_sector_context",   {"sector_or_symbol": canonical}),
                    ("get_index_snapshot",   {"index_name": idx_name}),
                    ("get_top_gainers_losers", {"index": idx_name, "top_n": 5, "direction": "both"}),
                    ("get_market_breadth",   {}),
                ],
            }

    wants_swing_candidates = (
        any(
            term in q
            for term in (
                "swing candidate", "swing candidates",
                "swing setup", "swing setups",
                "swing trade", "swing trades",
                "swing trading", "swing opportunity", "swing opportunities",
            )
        )
        or (
            "swing" in q
            and any(term in q for term in (
                "candidate", "candidates", "stocks", "setups", "ideas",
                "trade", "trades", "trading", "opportunity", "opportunities",
            ))
        )
    )
    wants_market_analysis = (
        "market analysis" in q
        or "market view" in q
        or "market assessment" in q
        or ("market" in q and any(term in q for term in ("last", "month", "months", "3 month", "three month")))
    )
    if wants_swing_candidates and (
        wants_market_analysis
        or any(term in q for term in ("opportunity", "opportunities", "trade", "trades", "trading"))
    ):
        return {
            "intent": "market_swing_candidates",
            "plan": [
                ("get_index_snapshot", {"index_name": "NIFTY 50"}),
                ("get_index_snapshot", {"index_name": "NIFTY MIDCAP 100"}),
                ("get_market_breadth", {}),
                ("run_quality_breakout_screener", {"top_n": 15, "mode": "balanced"}),
            ],
        }

    recent_market_words = [
        "what happened", "what changed", "last 15", "last 30", "last 5",
        "last few minutes", "last minutes", "recent move", "just now",
    ]
    if any(w in q for w in recent_market_words) and any(w in q for w in ["minute", "minutes", "min", "market", "nifty", "happened", "changed"]):
        return {"intent": "intraday_market_recap", "plan": [
            ("get_intraday_market_recap", {"minutes": _extract_minutes_window(q, 15)}),
            ("get_market_breadth", {}),
        ]}

    # Added: "ROE/PE/EPS/ROCE/EBITDA for|of <SYMBOL>" → fundamentals lookup
    # for the named symbol, not for the metric. Example: "ROE for HDFCBANK"
    # used to extract ROE as the ticker (HDFCBANK was getting skipped).
    _METRIC_RE = re.compile(
        r"\b(ROE|ROCE|ROA|PE|P/E|PB|P/B|EPS|EBITDA|MARGIN|MARGINS|DEBT|DIVIDEND|DPS|BVPS|BOOK\s+VALUE|FUNDAMENTALS|RATIOS)\b",
        re.IGNORECASE,
    )
    if _METRIC_RE.search(q) and (" for " in q or " of " in q):
        # Extract the symbol after for/of
        m = re.search(r"\b(?:for|of)\s+([A-Z][A-Z0-9&-]{1,11}(?:\s+[A-Z][A-Z0-9&-]{1,11}){0,2})\b", routing_text)
        if m:
            sym_q = m.group(1).strip()
            plan = [
                ("resolve_symbol",      {"query": sym_q}),
                ("scrape_screener_in",  {"symbol": sym_q.upper().replace(" ", "")}),
                ("get_symbol_snapshot", {"symbol": sym_q.upper().replace(" ", "")}),
            ]
            return {"intent": "stock_brief", "plan": _with_dynamic_stock_evidence(plan, q, sym_q.upper().replace(" ", ""))}

    growth_research_terms = (
        "long term growth", "long-term growth", "growth potential", "compounder",
        "compounders", "quality growth", "deep research", "deep dive research",
    )
    index_universe_pick_terms = (
        any(term in q for term in ("best", "top", "pick", "picks", "shortlist", "select", "candidate", "candidates"))
        and any(term in q for term in ("technical", "fundamental", "fundamentals", "quality", "score", "scores"))
        and any(term in q for term in ("stock", "stocks", "names", "companies"))
        and any(term in q for term in ("index", "indices", "nifty", "midcap", "smallcap"))
    )
    if (
        any(term in q for term in growth_research_terms)
        and any(term in q for term in ("stock", "stocks", "index", "indices", "midcap", "smallcap"))
    ) or index_universe_pick_terms:
        if "smallcap" in q or "small cap" in q:
            index_scope = "SMALLCAP"
            breadth_index = "NIFTY SMALLCAP 250"
        elif "nifty 500" in q or "nifty500" in q:
            index_scope = "NIFTY 500"
            breadth_index = "NIFTY 500"
        elif "nifty 50" in q or "nifty50" in q:
            index_scope = "NIFTY 50"
            breadth_index = "NIFTY 50"
        else:
            index_scope = "MIDCAP"
            breadth_index = "NIFTY MIDCAP 150"
        return {"intent": "long_term_growth_research", "plan": [
            ("get_long_term_growth_candidates", {"index_scope": index_scope, "top_n": 12, "include_research": True}),
            ("get_market_breadth", {"index": breadth_index}),
        ]}

    # Specific index query must be handled before generic market/breadth words;
    # otherwise "NIFTY 500 analysis" or "NIFTY 200 breadth" gets rendered with
    # full-universe breadth.
    idx = _extract_named_index(q, default="")
    bare_idx = bool(idx) and q.strip().upper().replace(" ", "") == idx.replace(" ", "")
    index_status_terms = (
        "analysis", "analyze", "analyse", "breadth", "trend", "performance",
        "status", "how is", "how does", "look like", "looks like", "doing",
    )
    scan_terms = ("scan", "screener", "intraday", "setup", "setups", "breakout", "vcp")
    if (
        idx
        and not _explicit_requested_symbols(routing_text)
        and not any(term in q for term in scan_terms)
        and (bare_idx or any(term in q for term in index_status_terms))
    ):
        plan = [
            ("get_index_snapshot", {"index_name": idx}),
            ("get_market_breadth", {"index": idx}),
        ]
        if any(term in q for term in ("analysis", "analyze", "analyse", "movers", "gainers", "losers", "breadth")):
            plan.append(("get_top_gainers_losers", {"index": idx, "top_n": 10, "direction": "both"}))
        return {"intent": "index_status", "plan": plan}

    if any(w in q for w in breadth_words) or q.strip() in {"overview", "market"}:
        plan = [
            ("get_live_market_overview", {}),
            ("get_market_breadth", {}),
        ]
        if any(w in q for w in mover_words):
            plan.append(("get_top_gainers_losers", {"index": "NIFTY 500", "top_n": 5, "direction": "both"}))
        return {"intent": "market_overview", "plan": plan}

    # Sector leadership questions should use live NSE sector indices, not the
    # stock-level high-RS screener.
    if (
        "sector" in q
        and any(term in q for term in ("strength", "strong", "leading", "leaders", "showing strength", "outperforming"))
        and not any(term in q for term in ("stock", "stocks", "names"))
        and not any(term in q for term in ("compare", " vs ", " versus ", "which is better", "better", "between"))
    ):
        return {"intent": "market_overview", "plan": [
            ("get_live_market_overview", {}),
            ("get_market_breadth", {}),
        ]}

    # Standalone movers query (e.g. "top gainers", "top losers", "biggest movers").
    # Without this branch, "top gainers" used to fall through to the
    # symbol-extractor and get parsed as ticker "TOP".
    if any(w in q for w in mover_words):
        direction = (
            "gainers" if any(g in q for g in ["gainer", "gainers", "advancing"])
            else "losers" if any(l in q for l in ["loser", "losers", "declining"])
            else "both"
        )
        return {"intent": "market_overview", "plan": [
            ("get_top_gainers_losers", {"index": "NIFTY 500", "top_n": 10, "direction": direction}),
            ("get_market_breadth", {}),
        ]}

    eod_screener_aliases = {
        "stage2": "stage2",
        "stage_2": "stage2",
        "breakouts": "breakouts",
        "breakout": "breakouts",
        "supertrend": "supertrend_buy",
        "supertrend_buy": "supertrend_buy",
        "strong": "strong_buy",
        "strong_buy": "strong_buy",
        "new": "new_entrants",
        "new_entrants": "new_entrants",
        "newhigh": "new_highs",
        "newhighs": "new_highs",
        "new_high": "new_highs",
        "new_highs": "new_highs",
        "52w": "new_highs",
        "momentum": "momentum_52w",
        "momentum_52w": "momentum_52w",
        "highrs": "high_rs",
        "high_rs": "high_rs",
        "turnaround": "turnaround",
        "base": "stage1_base",
        "stage1_base": "stage1_base",
        "tight": "tight_range",
        "tight_range": "tight_range",
        "dip": "oversold_bounce",
        "oversold_bounce": "oversold_bounce",
    }
    if "screener" in q:
        tail = q.split("screener", 1)[1].strip()
        tail_tokens = re.findall(r"[a-z0-9_]+", tail)
        if tail_tokens:
            key = tail_tokens[0]
            if key in eod_screener_aliases:
                return {
                    "intent": "screener",
                    "plan": [("run_screener_query", {"screen_type": eod_screener_aliases[key]})],
                }

    if any(term in q for term in ("superperformance", "minervini", "sepa")) and any(
        term in q for term in ("stock", "stocks", "screener", "screen", "find", "show", "scan")
    ):
        screen_type = "tight_range" if any(term in q for term in ("vcp", "contraction", "tight", "coiling")) else "high_rs"
        return {"intent": "screener", "plan": [("run_screener_query", {"screen_type": screen_type})]}

    words = re.findall(r"[A-Za-z][A-Za-z0-9\-&\.]+", routing_text)
    skip  = {        "show","me","the","latest","on","for","in","by","during","over","what","is","how","tell",
              "about","give","setup","stock","stocks","sector","nse","india","market","today","brief","full",
              "overview","intraday","levels","level","support","resistance","screener","scan",
              "deep","dive","analysis","technical","trade","trading","of",
              "and","or","candidate","candidates","swing","trades","opportunity","opportunities",
              "answer","analyze","analyse","this","spoken","question","your","read","view",
              "after","before","results","result","submitted","submit","concise","evidence","aware","risk","first",
              "research","only","include","context","watch","next","hello","hi","hey",
              "happened","changed","change","last","minute","minutes","min","few",
              "compare","vs","versus","from","perspective","into","including","combine",
              "fundamental","fundamentals","forensic","red","flags","flag",
              "own","portfolio","holding","holdings","monitor","should",
              "detailed","detail","complete","comprehensive",
              # Calendar / event / time tokens — never a ticker.
              "due","tomorrow","yesterday","tonight","upcoming","forthcoming",
              "recent","recently","reporting","reported","announced","announce",
              "filed","filing","filings","posted","posting","calendar",
              "earnings","dividend","dividends","agm","split","bonus","rights",
              "monday","tuesday","wednesday","thursday","friday","saturday","sunday",
              "week","weeks","weekly","month","months","monthly","year","years","yearly","quarter","quarterly",
              "day","days","past","previous","various","company","companies","bse",
              "who","has","have","had","whose","whom"}
    candidates = [w for w in words if w.lower() not in skip and len(w) >= 2]

    symbol_candidates = [
        w.upper()
        for w in candidates
        if re.fullmatch(r"[A-Z0-9&-]{2,12}", w.upper())
        and w.upper() not in _SYMBOL_VALIDATION_SKIP
        and w.upper() not in TECHNICAL_NON_SYMBOL_TERMS
        and (
            w == w.upper()
            or any(ch.isdigit() for ch in w)
            or ("&" in w and w == w.upper())
            or ("-" in w and w == w.upper())
        )
    ]

    portfolio_subject_terms = ("i own", "my portfolio", "my porfolio", "portfolio", "porfolio", "holdings", "holding")
    portfolio_symbol_subject_terms = (
        "i own", "i hold", "we own", "we hold",
        "my portfolio", "my porfolio", "portfolio", "porfolio",
        "my holdings", "our holdings", "holdings summary",
    )
    portfolio_forensic_terms = (
        "forensic", "beneish", "piotroski", "petroski", "altman",
        "manipulation", "earnings quality", "financial health",
        "accounting risk", "red flag", "red flags",
    )
    if any(term in q for term in portfolio_subject_terms) and any(term in q for term in portfolio_forensic_terms):
        return {
            "intent": "portfolio_forensic_review",
            "plan": [("screen_portfolio_forensic_watchlist", {})],
        }

    is_single_stock_technical_setup = (
        "technical setup for" in q
        or re.search(r"\b(full|detailed|complete)\s+technical\b.*\bfor\b", q)
    )
    is_strength_validation_query = (
        sum(1 for term in ("canslim", "can slim", "rs", "relative strength", "fundamental", "piotroski", "petroski") if term in q) >= 2
        and any(w in q for w in ("strength", "strong", "which", "rank", "out of"))
    )
    if _looks_like_stock_research_prompt(q):
        research_symbol = _stock_research_symbol_from_query(routing_text)
        if research_symbol:
            plan = [
                ("resolve_symbol", {"query": research_symbol}),
                ("get_symbol_snapshot", {"symbol": research_symbol}),
                ("get_technical_setup", {"symbol": research_symbol}),
                ("get_sector_context", {"sector_or_symbol": research_symbol}),
            ]
            plan = _with_dynamic_stock_evidence(plan, q, research_symbol)
            return {"intent": "stock_brief", "plan": plan}

    if (
        not is_single_stock_technical_setup
        and not is_strength_validation_query
        and any(term in q for term in ("compare", " vs ", " versus ", "which is better", "better", "rank", "between"))
        and len(symbol_candidates) >= 2
    ):
        aspects = ["both"]
        if "technical" in q and not any(term in q for term in ("fundamental", "ratio", "valuation")):
            aspects = ["technical"]
        elif any(term in q for term in ("fundamental", "ratio", "valuation")) and "technical" not in q:
            aspects = ["fundamental"]
        return {
            "intent": "stock_comparison",
            "plan": [("compare_stocks", {"symbols": symbol_candidates[:5], "aspects": aspects})],
        }

    if any(term in q for term in portfolio_symbol_subject_terms) and symbol_candidates:
        return {
            "intent": "portfolio_review",
            "plan": [("generate_portfolio_narratives", {"symbols": symbol_candidates[:10], "top_n": min(len(symbol_candidates), 10)})],
        }

    # Added: standalone "portfolio review / my portfolio / holdings overview"
    # without explicit tickers — call get_portfolio_exposure to summarize the
    # portfolio CSV. Was misrouting to "REVIEW (REVIEW) — Market Brief".
    if any(term in q for term in ("portfolio review", "review my portfolio", "review my porfolio", "my portfolio", "my porfolio", "portfolio summary", "porfolio summary", "holdings summary", "portfolio overview")):
        return {
            "intent": "portfolio_review",
            "plan": [("get_portfolio_exposure", {})],
        }

    strength_terms = ("canslim", "can slim", "rs", "relative strength", "fundamental", "piotroski", "petroski")
    if is_strength_validation_query:
        strength_skip = skip | {
            "out", "of", "which", "show", "shows", "strength", "strong", "based", "basis",
            "can", "slim", "canslim", "rs", "relative", "fundamental", "fundamentals",
            "analysis", "piotroski", "petroski", "score", "scores", "fscore", "f-score",
        }
        symbols = []
        for token in words:
            raw = token.upper().strip()
            if raw.lower() in strength_skip:
                continue
            looks_like_symbol = (
                token == token.upper()
                or any(ch.isdigit() for ch in raw)
                or "&" in raw
                or "-" in raw
            )
            if looks_like_symbol and re.fullmatch(r"[A-Z0-9&-]{2,12}", raw) and raw not in {"CANSLIM", "RS"}:
                symbols.append(raw)
        if symbols:
            return {"intent": "strength_validation", "plan": [("validate_strength_watchlist", {"symbols": symbols})]}

    if any(w in q for w in [
        "source health", "live table", "postgre", "postgres", "postgresql",
        "intraday data", "intra day data", "intraday table", "ohlcv table",
    ]):
        return {"intent": "intraday_health", "plan": [("get_intraday_source_health", {})]}

    if any(w in q for w in ["bulk deal", "bulk deals", "block deal", "block deals", "large trades"]):
        return {"intent": "market_overview", "plan": [("get_bulk_block_deals", {})]}
    if any(w in q for w in ["most active", "highest volume", "most traded", "volume leaders"]):
        return {"intent": "market_overview", "plan": [("get_most_active_stocks", {})]}

    technical_stock_terms = (
        "technical setup", "indicators", "rsi", "adx", "macd", "supertrend",
        "moving average", "sma", "weinstein stage", "rs rank", "relative strength",
        "technical analysis",
    )
    fundamental_stock_terms = (
        "fundamental", "fundamentals", "fundamental analysis", "ratio", "ratios",
        "valuation", "p/e", "pe", "roe", "roce", "book value",
    )
    forensic_stock_terms = (
        "run_forensic_analysis", "forensic", "beneish", "piotroski", "altman",
        "earnings manipulation", "manipulation risk", "financial health",
        "red flag", "red flags", "earnings quality", "accounting risk",
        "balance sheet quality",
    )
    # Queries that ask for actual reported numbers (P&L / Balance Sheet /
    # Quarterly results / fundamentals) must pull screener.in data and the
    # latest BSE/NSE filing — a snapshot-only response is incomplete.
    # Keep keywords specific so we don't steal generic "news / results" intents.
    results_stock_terms = (
        "latest results", "quarterly results", "quarterly result",
        "q1 results", "q2 results", "q3 results", "q4 results",
        "annual results", "yearly results", "fy results",
        "earnings results", "earnings report", "result update",
        "profit and loss", "p&l statement", "p & l",
        "balance sheet", "cash flow statement", "financial statements",
        "fundamental analysis", "quarterly numbers", "quarterly financials",
        "annual financials", "revenue and profit", "revenue & profit",
    )
    # Treat conversational mentions ("after results", "before earnings",
    # "post results") as commentary, not data fetches.
    conversational_results = (
        "after results", "after the results", "before results", "before the results",
        "post results", "post the results", "after earnings", "before earnings",
        "post earnings", "after the earnings", "before the earnings",
        "read on", "view on", "thoughts on", "opinion on",
    )
    # Match free-form "<symbol> results" / "latest <symbol> results" patterns
    # where the user is clearly asking for the actual results data.
    _results_freeform = (
        re.search(r"\b(?:latest|recent|new|fresh|published)\b[^.?!]{0,60}\bresults?\b", q)
        or re.search(r"\bresults?\b[^.?!]{0,40}\b(?:for|of)\b\s+[A-Z]", routing_text)
        or re.search(r"\bshow\s+(?:me\s+)?[^.?!]{0,40}\bresults?\b", q)
    ) and not any(c in q for c in conversational_results)
    # If user is primarily asking for news/catalysts, defer to that branch.
    news_priority_terms = ("news", "catalyst", "catalysts", "announcement", "announcements")
    explicit_stock_subject = bool(symbol_candidates or _symbol_phrase_after_preposition(routing_text))
    bare_symbol_query = (
        len(words) == 1
        and len(candidates) == 1
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9&.-]{1,19}", routing_text.strip())
        and candidates[0].upper() not in _SYMBOL_VALIDATION_SKIP
        and candidates[0].upper() not in TECHNICAL_NON_SYMBOL_TERMS
        and q not in {"nifty", "nifty50", "banknifty", "sensex"}
    )
    if bare_symbol_query:
        sym_q = candidates[0]
        return {"intent": "symbol_quick_analysis", "plan": [
            ("resolve_symbol", {"query": sym_q}),
            ("get_symbol_quick_analysis", {"symbol": sym_q}),
        ]}
    result_entity_match = re.search(
        r"\bresults?\b\s+(?:of|for)\s+([A-Za-z][A-Za-z0-9&.\-]*(?:\s+[A-Za-z][A-Za-z0-9&.\-]*){0,4})",
        routing_text,
        flags=re.IGNORECASE,
    ) or re.search(
        r"\b(?:of|for)\s+([A-Za-z][A-Za-z0-9&.\-]*(?:\s+[A-Za-z][A-Za-z0-9&.\-]*){0,4})\s+results?\b",
        routing_text,
        flags=re.IGNORECASE,
    )
    if result_entity_match and (any(term in q for term in results_stock_terms) or _results_freeform):
        raw_entity = result_entity_match.group(1).strip(" ?.,")
        raw_entity = re.sub(r"\b(?:latest|recent|quarterly|annual|fy|q[1-4])\b", "", raw_entity, flags=re.IGNORECASE).strip()
        if raw_entity and raw_entity.lower() not in {"companies", "stocks", "market"}:
            try:
                resolved = resolve_symbol(raw_entity)
                resolved_symbol = str(resolved.get("symbol") or "").strip().upper() if isinstance(resolved, dict) else ""
            except Exception:
                resolved_symbol = ""
            if resolved_symbol:
                plan = [
                    ("resolve_symbol", {"query": raw_entity}),
                    ("get_latest_results", {"symbol": resolved_symbol}),
                ]
                _ensure_fundamental_source_chain(plan, resolved_symbol)
                return {"intent": "stock_results", "plan": plan}

    # Market-wide latest results feed — no specific symbol in the query.
    # Catches "latest results", "who reported today", "results this week",
    # "companies that announced", "recently reported", etc. Must come BEFORE
    # the per-symbol stock_results block so symbol-less queries are caught.
    results_feed_days = _results_feed_window_days(q)
    if (
        not symbol_candidates
        and results_feed_days is not None
    ):
        return {"intent": "results_feed", "plan": [
            ("get_latest_results_feed", {"days_back": results_feed_days, "limit": 50}),
        ]}

    # PG-PLAN 2026-05-25: Direct multi-symbol "news / results / events" branch.
    # When the user spells out two or more tickers AND asks about news,
    # results, earnings, corporate events, announcements, filings, or
    # upcoming catalysts, hand off to plan_news_and_results so we run
    # get_latest_results per symbol PLUS get_event_calendar_summary —
    # instead of falling through to the single-symbol stock_results branch
    # that only handles the first ticker.
    _collective_news_terms = (
        "news", "headlines", "announcement", "announcements",
        "corporate event", "corporate events", "corporate action",
        "corporate actions", "filings", "disclosure", "disclosures",
        "catalyst", "catalysts", "events", "upcoming",
        "calendar",
    )
    _results_pair_terms = ("results", "earnings", "quarterly")
    _has_collective_news = any(term in q for term in _collective_news_terms)
    _has_results_term = any(term in q for term in _results_pair_terms)
    if (
        len(symbol_candidates) >= 2
        and (_has_collective_news or _has_results_term)
    ):
        planned = plan_news_and_results(symbol_candidates)
        if planned is not None:
            return {"intent": "collective_news_results", "plan": list(planned.tool_plan)}

    if (
        candidates and explicit_stock_subject
        and (any(term in q for term in results_stock_terms) or _results_freeform)
        and not any(term in q for term in news_priority_terms)
    ):
        sym_q = _primary_symbol_query(candidates, symbol_candidates, routing_text)
        sym = sym_q.upper()
        plan = [
            ("resolve_symbol",     {"query": sym}),
            ("get_latest_results", {"symbol": sym}),
        ]
        _ensure_fundamental_source_chain(plan, sym)
        return {"intent": "stock_results", "plan": plan}

    if candidates and explicit_stock_subject and any(term in q for term in forensic_stock_terms):
        sym_q = _primary_symbol_query(candidates, symbol_candidates, routing_text)
        plan = [
            ("resolve_symbol",       {"query": sym_q}),
            ("get_symbol_snapshot",  {"symbol": sym_q.upper()}),
            ("get_technical_setup",  {"symbol": sym_q.upper()}),
            ("get_sector_context",   {"sector_or_symbol": sym_q.upper()}),
            ("run_forensic_analysis", {"symbol": sym_q.upper()}),
        ]
        return {"intent": "stock_brief", "plan": _with_dynamic_stock_evidence(plan, q, sym_q)}

    # Intraday routing: PostgreSQL bars first, NSE website live snapshot second,
    # yfinance candle analysis only as fallback for OHLCV history.
    if data_mode == "intraday":
        if any(w in q for w in ["rsi divergence", "rsi reversal"]):
            return {"intent": "intraday_screener", "plan": [("run_intraday_screener", {"screen_type": "rsi_divergence"})]}
        if candidates and explicit_stock_subject and any(w in q for w in ["news", "catalyst", "catalysts", "recent"]):
            sym_q = _primary_symbol_query(candidates, symbol_candidates, routing_text)
            plan = [
                ("resolve_symbol",       {"query": sym_q}),
                ("get_symbol_snapshot",  {"symbol": sym_q.upper()}),
                ("get_technical_setup",  {"symbol": sym_q.upper()}),
                ("get_sector_context",   {"sector_or_symbol": sym_q.upper()}),
                ("search_latest_catalysts", {"symbol": sym_q.upper()}),
            ]
            return {"intent": "stock_brief", "plan": _with_dynamic_stock_evidence(plan, q, sym_q)}
        if (
            candidates
            and explicit_stock_subject
            and "scan" not in q
            and "screener" not in q
            and any(term in q for term in technical_stock_terms)
        ):
            sym_q = _primary_symbol_query(candidates, symbol_candidates, routing_text)
            return {"intent": "intraday_setup", "plan": [
                ("resolve_symbol", {"query": sym_q}),
                ("explain_intraday_setup", {"symbol": sym_q}),
                ("get_nse_intraday_snapshot", {"symbol": sym_q}),
                ("get_intraday_analysis", {"symbol": sym_q}),
            ]}
        # PG 2026-05-22: "intraday scan for TRENT" / "scan SBIN intraday" — when
        # the user pairs the word "scan" with an explicit single-symbol subject
        # (no index keyword), route to scan_symbols_intraday so we actually
        # analyze that stock instead of falling through to the generic momentum
        # screener.
        if (
            candidates
            and explicit_stock_subject
            and ("scan" in q or "screener" in q)
            and not any(
                kw in q
                for kw in ("nifty", "bank nifty", "banknifty", "midcap", "smallcap",
                            "sensex", "finnifty", "index", "universe")
            )
        ):
            sym_q = _primary_symbol_query(candidates, symbol_candidates, routing_text)
            sym_upper = sym_q.upper()
            return {"intent": "intraday_symbol_scan", "plan": [
                ("resolve_symbol", {"query": sym_q}),
                ("scan_symbols_intraday", {
                    "symbols": [sym_upper],
                    "interval": _extract_intraday_timeframe(q),
                    "strategies": _extract_intraday_scan_strategies(q),
                    "direction_filter": _intraday_scan_direction(q),
                    "min_rr": 1.3,
                    "top_n": 10,
                }),
                ("explain_intraday_setup", {"symbol": sym_q}),
                ("get_nse_intraday_snapshot", {"symbol": sym_q}),
            ]}
        if "scan" in q and (
            "nifty" in q
            or "bank nifty" in q
            or "banknifty" in q
            or "midcap" in q
            or "smallcap" in q
        ):
            return {"intent": "intraday_index_scan", "plan": [("scan_intraday_market", {
                "index": _extract_intraday_scan_index(q),
                "interval": _extract_intraday_timeframe(q),
                "strategies": _extract_intraday_scan_strategies(q),
                "direction_filter": _intraday_scan_direction(q),
                "min_rr": 1.3,
                "top_n": 10,
            })]}
        if any(w in q for w in ["gap up", "gap and go", "gap continuation", "gapping stocks"]):
            return {"intent": "intraday_screener", "plan": [("run_intraday_screener", {"screen_type": "gap_and_go"})]}
        if any(w in q for w in ["macd crossover", "macd signal", "fresh macd"]):
            return {"intent": "intraday_screener", "plan": [("run_intraday_screener", {"screen_type": "macd_crossover"})]}
        if any(w in q for w in ["vwap reclaim", "above vwap", "vwap bounce"]):
            return {"intent": "intraday_screener", "plan": [("run_intraday_screener", {"screen_type": "vwap_reclaim"})]}
        if any(w in q for w in ["bollinger squeeze", "bb squeeze", "volatility squeeze"]):
            return {"intent": "intraday_screener", "plan": [("run_intraday_screener", {"screen_type": "bb_squeeze"})]}
        if any(w in q for w in ["rsi divergence", "rsi reversal"]):
            return {"intent": "intraday_screener", "plan": [("run_intraday_screener", {"screen_type": "rsi_divergence"})]}
        if any(w in q for w in ["opening range breakout", "orb breakout", "orb breakouts", "first 15 minutes"]):
            return {"intent": "intraday_screener", "plan": [("run_intraday_screener", {"screen_type": "opening_range_breakout"})]}
        if any(w in q for w in ["data health", "source health", "live table", "sqlite", "stale", "fresh"]):
            return {"intent": "intraday_health", "plan": [("get_intraday_source_health", {})]}
        if any(w in q for w in ["breakout", "breakouts"]):
            return {"intent": "intraday_screener", "plan": [("run_intraday_screener", {"screen_type": "breakouts"})]}
        if any(w in q for w in ["vcp", "contraction"]):
            return {"intent": "intraday_screener", "plan": [("run_intraday_screener", {"screen_type": "vcp"})]}
        if any(w in q for w in ["supertrend", "super trend"]):
            return {"intent": "intraday_screener", "plan": [("run_intraday_screener", {"screen_type": "supertrend"})]}
        if any(w in q for w in ["momentum", "movers", "leaders", "scan", "screener"]):
            return {"intent": "intraday_screener", "plan": [("run_intraday_screener", {"screen_type": "momentum"})]}
        if any(w in q for w in ["level", "levels", "support", "resistance", "pivot"]):
            sym_q = _primary_symbol_query(candidates, symbol_candidates, routing_text)
            return {"intent": "intraday_levels", "plan": [
                ("resolve_symbol", {"query": sym_q}),
                ("get_intraday_levels", {"symbol": sym_q}),
                ("get_nse_intraday_snapshot", {"symbol": sym_q}),
                ("get_intraday_analysis", {"symbol": sym_q}),
            ]}
        if candidates:
            sym_q = _primary_symbol_query(candidates, symbol_candidates, routing_text)
            return {"intent": "intraday_setup", "plan": [
                ("resolve_symbol", {"query": sym_q}),
                ("explain_intraday_setup", {"symbol": sym_q}),
                ("get_nse_intraday_snapshot", {"symbol": sym_q}),
                ("get_intraday_analysis", {"symbol": sym_q}),
            ]}
    if (
        candidates
        and any(term in q for term in technical_stock_terms)
        and any(term in q for term in fundamental_stock_terms)
    ):
        sym_q = _primary_symbol_query(candidates, symbol_candidates, routing_text)
        plan = [
            ("resolve_symbol",       {"query": sym_q}),
            ("scrape_screener_in",   {"symbol": sym_q.upper()}),
            ("get_symbol_snapshot",  {"symbol": sym_q.upper()}),
            ("get_technical_setup",  {"symbol": sym_q.upper()}),
            ("get_sector_context",   {"sector_or_symbol": sym_q.upper()}),
        ]
        return {"intent": "stock_brief", "plan": _with_dynamic_stock_evidence(plan, q, sym_q)}

    if candidates and any(term in q for term in technical_stock_terms) and (" for " in f" {q} " or "setup" in q):
        sym_q = _primary_symbol_query(candidates, symbol_candidates, routing_text)
        plan = [
            ("resolve_symbol",       {"query": sym_q}),
            ("get_symbol_snapshot",  {"symbol": sym_q.upper()}),
            ("get_technical_setup",  {"symbol": sym_q.upper()}),
            ("get_sector_context",   {"sector_or_symbol": sym_q.upper()}),
        ]
        return {"intent": "stock_brief", "plan": _with_dynamic_stock_evidence(plan, q, sym_q)}

    # Screener queries
    quality_breakout_terms = (
        ("new high" in q or "new highs" in q or "52 week" in q or "52w" in q)
        and ("vcp" in q or "tight" in q or "contraction" in q)
        and ("breakout" in q or "breakouts" in q)
        and ("fundamental" in q or "quality" in q)
    ) or any(
        term in q
        for term in (
            "quality breakout candidates",
            "quality breakouts",
            "breakouts with good fundamentals",
            "new highs with good fundamentals",
            "vcp stocks with good fundamentals",
            "breakouts with fundamental quality",
        )
    )
    if quality_breakout_terms:
        return {
            "intent": "quality_breakouts",
            "plan": [("run_quality_breakout_screener", {"top_n": 15, "mode": "balanced"})],
        }

    if any(w in q for w in ["strong buy", "top buy", "buy signals", "best stocks"]):
        return {"intent": "screener", "plan": [("run_screener_query", {"screen_type": "strong_buy"})]}
    if (
        any(term in q for term in [
            "showing strength", "still strong", "strong stocks",
            "market leaders", "relative strength",
            # Added the "high rs" / "high relative strength" variants and
            # standalone "rs stocks" — these used to fall through to
            # stock_brief which then misrouted resolve_symbol("RS").
            "top rs", "high rs", "highest rs", "best rs", "rs leaders",
            "rs leadership", "rs ranked", "top relative strength",
            "high relative strength",
        ])
        and any(term in q for term in ["stock", "stocks", "which", "leaders", "names"])
    ):
        return {"intent": "screener", "plan": [("run_screener_query", {"screen_type": "high_rs"})]}
    if any(w in q for w in ["stage 2", "stage2", "weinstein", "advancing stocks"]):
        return {"intent": "screener", "plan": [("run_screener_query", {"screen_type": "stage2"})]}
    if any(w in q for w in ["companies creating new high", "creating new highs", "creating new high", "new highs", "new high", "52w high", "52 week high"]):
        return {"intent": "screener", "plan": [("run_screener_query", {"screen_type": "new_highs"})]}
    if any(w in q for w in ["breakout", "breakouts", "20d high"]):
        return {"intent": "screener", "plan": [("run_screener_query", {"screen_type": "breakouts"})]}
    if any(w in q for w in ["new entrant", "new stage 2", "recently upgraded"]):
        return {"intent": "screener", "plan": [("run_screener_query", {"screen_type": "new_entrants"})]}
    # Added: turnaround / recovery / dip-recovery / comeback (matches the
    # screener prompt mapping at the top of this file).
    if any(w in q for w in ["turnaround", "turn around", "recovery stock", "comeback stock", "dip recovery"]):
        return {"intent": "screener", "plan": [("run_screener_query", {"screen_type": "turnaround"})]}
    if any(w in q for w in ["supertrend", "super trend"]):
        return {"intent": "screener", "plan": [("run_screener_query", {"screen_type": "supertrend_buy"})]}
    # Added: oversold-bounce / tight-range / basing  EOD screeners that used
    # to fall through to the symbol extractor and become OVERSOLD / TIGHT /
    # BASING "Market Briefs".
    if any(w in q for w in ["oversold bounce", "oversold dip", "rsi dip", "dip buy", "stage 2 dip"]):
        return {"intent": "screener", "plan": [("run_screener_query", {"screen_type": "oversold_bounce"})]}
    if any(w in q for w in ["tight range", "vcp eod", "volatility contraction", "coiling stocks", "tight consolidation"]):
        return {"intent": "screener", "plan": [("run_screener_query", {"screen_type": "tight_range"})]}
    if any(w in q for w in ["basing stock", "basing stocks", "accumulation stock", "stage 1 base", "consolidating stock"]):
        return {"intent": "screener", "plan": [("run_screener_query", {"screen_type": "stage1_base"})]}

    # Added: live-tape utilities  bulk/block deals + most-active.
    if any(w in q for w in ["bulk deal", "bulk deals", "block deal", "block deals", "large trades"]):
        return {"intent": "market_overview", "plan": [("get_bulk_block_deals", {})]}
    if any(w in q for w in ["most active", "highest volume", "most traded", "volume leaders"]):
        return {"intent": "market_overview", "plan": [("get_most_active_stocks", {})]}

    # Added: intraday screeners  gap-and-go / MACD / VWAP / Bollinger
    # squeeze. Must come BEFORE the generic symbol extractor so they don't
    # become GAP / MACD / VWAP / BOLLINGER "Market Briefs".
    if any(w in q for w in ["gap up", "gap and go", "gap continuation", "gapping stocks"]):
        return {"intent": "intraday_screener", "plan": [("run_intraday_screener", {"screen_type": "gap_and_go"})]}
    if any(w in q for w in ["macd crossover", "macd signal", "fresh macd"]):
        return {"intent": "intraday_screener", "plan": [("run_intraday_screener", {"screen_type": "macd_crossover"})]}
    if any(w in q for w in ["vwap reclaim", "above vwap", "vwap bounce"]):
        return {"intent": "intraday_screener", "plan": [("run_intraday_screener", {"screen_type": "vwap_reclaim"})]}
    if any(w in q for w in ["bollinger squeeze", "bb squeeze", "volatility squeeze"]):
        return {"intent": "intraday_screener", "plan": [("run_intraday_screener", {"screen_type": "bb_squeeze"})]}
    if any(w in q for w in ["rsi divergence", "rsi reversal"]):
        return {"intent": "intraday_screener", "plan": [("run_intraday_screener", {"screen_type": "rsi_divergence"})]}
    if any(w in q for w in ["opening range breakout", "orb breakout", "orb breakouts", "first 15 minutes"]):
        return {"intent": "intraday_screener", "plan": [("run_intraday_screener", {"screen_type": "opening_range_breakout"})]}

    # Intraday / PostgreSQL data health — works in any mode
    if any(w in q for w in [
        "source health", "live table", "postgre", "postgres", "postgresql",
        "intraday data", "intra day data", "intraday table", "ohlcv table",
    ]):
        return {"intent": "intraday_health", "plan": [("get_intraday_source_health", {})]}

    # Data health
    if any(w in q for w in ["data health", "data fresh", "stale", "last update", "when was"]):
        return {"intent": "data_health", "plan": [("get_data_health", {})]}

    # Forthcoming results / earnings calendar — companies with scheduled board
    # meetings to declare quarterly results. Routes to a dedicated tool that
    # surfaces a results-only event table (not generic corporate-actions prose).
    forthcoming_results_terms = (
        "results due", "earnings due",
        "results next week", "earnings next week",
        "results tomorrow", "earnings tomorrow",
        "reporting tomorrow", "reporting this week", "reporting next week",
        "who has results", "who's reporting", "whos reporting", "who is reporting",
        "who is reporting results", "who's reporting results",
        "results scheduled", "earnings scheduled",
        "forthcoming results", "forthcoming earnings",
        "upcoming results", "upcoming earnings",
        "results calendar this week", "results calendar next week",
        "earnings calendar this week", "earnings calendar next week",
        "results expected", "earnings expected",
    )
    if not symbol_candidates and any(term in q for term in forthcoming_results_terms):
        days = 14
        if "tomorrow" in q:
            days = 2
        elif "this week" in q:
            days = 7
        elif "next week" in q:
            days = 14
        elif "this month" in q or "next month" in q:
            days = 30
        return {
            "intent": "forthcoming_results",
            "plan": [("get_forthcoming_results", {"days_ahead": days, "limit": 50})],
        }

    if any(
        phrase in q
        for phrase in [
            "upcoming events", "event calendar", "events this week", "corporate action",
            "corporate actions", "upcoming results", "results this week", "board meeting",
            "dividend", "agm", "ex-date", "ex date",
            # Forthcoming results / earnings calendar phrasings
            "results due", "earnings due", "results next week", "earnings next week",
            "results tomorrow", "earnings tomorrow", "reporting tomorrow",
            "reporting this week", "reporting next week",
            "who has results", "who's reporting", "whos reporting", "who is reporting",
            "results scheduled", "earnings scheduled", "forthcoming results",
        ]
    ) or ("events" in q and any(term in q for term in ("results", "corporate", "actions", "week", "watch"))):
        return {
            "intent": "event_calendar",
            "plan": [("get_event_calendar_summary", {"index": "NIFTY 50", "days_ahead": 14})],
        }

    # Reports
    if any(w in q for w in ["report", "html", "generated", "latest report"]):
        return {"intent": "report_lookup", "plan": [("find_latest_report", {})]}

    if "sector context" in q and candidates:
        sym_q = _primary_symbol_query(candidates, symbol_candidates, routing_text)
        return {"intent": "sector_scan", "plan": [("get_sector_context", {"sector_or_symbol": sym_q.upper()})]}

    # Sector queries
    sector_words = ["sector", "pharma", "it sector", "auto sector", "bank sector",
                    "metals", "fmcg", "real estate", "energy"]
    for sw in sector_words:
        if sw in q:
            sector = sw.replace(" sector", "").title()
            return {"intent": "sector_scan", "plan": [("get_sector_context", {"sector_or_symbol": sector})]}

    # Stock-specific query — extract likely symbol
    if candidates:
        sym_q = _primary_symbol_query(candidates, symbol_candidates, routing_text)
        plan = [
            ("resolve_symbol",       {"query": sym_q}),
            ("get_symbol_snapshot",  {"symbol": sym_q.upper()}),
            ("get_technical_setup",  {"symbol": sym_q.upper()}),
            ("get_sector_context",   {"sector_or_symbol": sym_q.upper()}),
            ("scrape_screener_in",   {"symbol": sym_q.upper()}),
            ("search_nse_announcements", {"symbol": sym_q.upper()}),
        ]
        return {"intent": "stock_brief", "plan": _with_dynamic_stock_evidence(plan, q, sym_q)}

    return {"intent": "unknown", "plan": [("get_market_breadth", {})]}


# ─────────────────────────────────────────────────────────────────────────────
# Tool execution
# ─────────────────────────────────────────────────────────────────────────────

def _execute_plan(plan: list[tuple[str, dict]]) -> list[dict]:
    """Execute a list of (tool_name, args) tuples, resolving symbols first."""
    results: list[dict] = []
    resolved_sym: str | None = None

    for tool_name, args in plan:
        # Auto-substitute resolved symbol
        if resolved_sym and "symbol" in args and not args["symbol"]:
            args["symbol"] = resolved_sym

        result = call_tool(tool_name, args)

        # Capture resolved symbol for downstream tools
        if tool_name == "resolve_symbol" and result.get("symbol"):
            resolved_sym = result["symbol"]
            original_query = str(args.get("query") or "")
            # Patch subsequent args that reference the original fuzzy query
            for _, a in plan:
                for k, v in a.items():
                    if isinstance(v, str) and original_query and v.upper() == original_query.upper():
                        a[k] = resolved_sym

        results.append({"tool": tool_name, "args": args, "result": result})

    return results


def _execute_plan_layered(
    specs: "tuple",
    max_workers: int = 4,
) -> list[dict]:
    """Execute a tuple of ``ToolCallSpec`` honouring declared deps.

    Uses ``terminal.router.task_graph.dependency_layers`` to group the
    plan into layers of mutually-independent calls; each layer is then
    dispatched in parallel via a ``ThreadPoolExecutor``. Between
    layers, a freshly resolved symbol is patched into any downstream
    args that referenced the original fuzzy query (mirrors the
    sequential ``_execute_plan`` behaviour).

    The returned ``results`` list preserves layered, deterministic
    order (within a layer, original input order is kept).
    """
    from concurrent.futures import ThreadPoolExecutor

    from terminal.router.task_graph import _ensure_ids, dependency_layers

    if not specs:
        return []

    specs = _ensure_ids(specs)
    layers = dependency_layers(specs)
    pending_args: dict[str, dict] = {s.task_id: dict(s.args) for s in specs}
    results: list[dict] = []
    resolved_sym: str | None = None
    resolve_query: str | None = None

    def _apply_resolved(sym: str, query: str | None) -> None:
        for spec in specs:
            args = pending_args[spec.task_id]
            if "symbol" in args and not args["symbol"]:
                args["symbol"] = sym
            if query:
                for k, v in list(args.items()):
                    if isinstance(v, str) and v.upper() == query.upper():
                        args[k] = sym

    for layer in layers:
        if len(layer) == 1:
            spec = layer[0]
            args = pending_args[spec.task_id]
            result = call_tool(spec.tool, args)
            results.append({"tool": spec.tool, "args": args, "result": result})
            if spec.tool == "resolve_symbol" and isinstance(result, dict) and result.get("symbol"):
                resolved_sym = result["symbol"]
                resolve_query = args.get("query")
                _apply_resolved(resolved_sym, resolve_query)
            continue

        workers = min(max_workers, len(layer))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [
                (spec, ex.submit(call_tool, spec.tool, pending_args[spec.task_id]))
                for spec in layer
            ]
            for spec, fut in futures:
                result = fut.result()
                args = pending_args[spec.task_id]
                results.append({"tool": spec.tool, "args": args, "result": result})
                if spec.tool == "resolve_symbol" and isinstance(result, dict) and result.get("symbol"):
                    resolved_sym = result["symbol"]
                    resolve_query = args.get("query")
        if resolved_sym:
            _apply_resolved(resolved_sym, resolve_query)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Response synthesis
# ─────────────────────────────────────────────────────────────────────────────

def _synthesize_no_llm(intent: str, tool_results: list[dict], assessment_plan: dict | None = None) -> str:
    """Route to the appropriate per-intent renderer in terminal.renderers."""
    from terminal.renderers import render as _render
    return _render(intent, tool_results, assessment_plan)


def _indent_answer_block(text: str) -> str:
    return "\n".join(f"  {line}" if line else "" for line in (text or "").splitlines())


def _structured_output_is_diagnostics_only(structured: str) -> bool:
    """Return true when the deterministic render adds no evidence beyond errors.

    Final synthesis already explains missing evidence in user-facing language.
    If the render only contains a title, missing-evidence block, source trail,
    and footer, appending it creates a noisy duplicate response.
    """
    text = structured or ""
    if "▶ MISSING EVIDENCE" not in text:
        return False

    substantive_markers = (
        "▶ SNAPSHOT",
        "▶ CURRENT OVERVIEW",
        "▶ TECHNICAL SETUP",
        "▶ TECHNICAL AND SECTOR CONTEXT",
        "▶ FUNDAMENTAL",
        "▶ QUARTERLY RESULTS",
        "▶ ANNUAL P&L",
        "▶ SALES & EPS GROWTH",
        "▶ SECTOR CONTEXT",
        "▶ MARKET OVERVIEW",
        "▶ MARKET BREADTH",
        "▶ TOP MOVERS",
        "▶ TOP STOCK",
        "▶ KEY MOVERS",
        "▶ INDEX TAPE",
        "▶ OPTION CHAIN",
        "▶ FUTURES",
        "▶ STRATEGY",
    )
    return not any(marker in text for marker in substantive_markers)


def _synthesize_and_narrate(
    intent: str,
    query: str,
    tool_results: list[dict],
    backend,
    assessment_plan: dict | None = None,
) -> str:
    """Synthesize + optionally append an LLM narrative paragraph.

    Uses the deterministic renderer first (always fast, always present),
    then appends a short interpretation if the intent is in NARRATION_INTENTS
    and a backend is available.
    """
    from terminal.renderers import render as _render, build_narrative, attach_narrative
    from terminal.renderers.narrator import build_final_answer
    structured = _render(intent, tool_results, assessment_plan)
    final_answer = build_final_answer(
        intent,
        query,
        tool_results,
        structured,
        backend,
        assessment_plan,
    )
    if final_answer:
        if _structured_output_is_diagnostics_only(structured):
            from terminal.renderers._base import FOOTER
            return f"▶ ANSWER\n{_indent_answer_block(final_answer)}\n{FOOTER}"
        return f"▶ ANSWER\n{_indent_answer_block(final_answer)}\n\n{structured}"
    narrative = build_narrative(intent, query, tool_results, structured, backend)
    return attach_narrative(structured, narrative)
# ─────────────────────────────────────────────────────────────────────────────
# Main Agent class
# ─────────────────────────────────────────────────────────────────────────────

_INTRADAY_KEYWORDS: frozenset[str] = frozenset(
    {"live", "current", "today", "now", "intraday", "real-time", "realtime"}
)

_GLOBAL_QUERY_PHRASES: tuple[str, ...] = (
    "global", "overnight", "us market", "asian market", "asia market",
    "europe market", "crude", "oil", "gold", "copper", "dxy", "usd/inr",
    "usdinr", "dollar index", "risk on", "risk off", "global cues",
)


def _is_morning_briefing_query(q: str) -> bool:
    q = (q or "").lower()
    return (
        "morning briefing" in q
        or "startup briefing" in q
        or "market intelligence briefing" in q
        or ("starting a new trading session" in q and "global overnight context" in q)
    )


def _is_global_query(q: str) -> bool:
    return any(phrase in q for phrase in _GLOBAL_QUERY_PHRASES)


def _is_implicit_results_followup(q: str) -> bool:
    text = (q or "").lower().strip()
    if not any(
        term in text
        for term in (
            "latest results",
            "quarterly results",
            "quarterly result",
            "results analysis",
            "earnings analysis",
            "financial results",
        )
    ):
        return False
    return re.search(r"\b(?:for|of)\s+[a-z][a-z0-9&.-]{1,20}\b", text) is None


def _has_tool_error(tool_results: list[dict], tool_name: str, needle: str = "") -> bool:
    for trace in tool_results:
        if trace.get("tool") != tool_name:
            continue
        result = trace.get("result") or {}
        error = str(result.get("error") or "")
        if error and (not needle or needle.lower() in error.lower()):
            return True
    return False


def _has_successful_tool(tool_results: list[dict], tool_name: str) -> bool:
    for trace in tool_results:
        if trace.get("tool") != tool_name:
            continue
        result = trace.get("result") or {}
        if isinstance(result, dict) and not result.get("error"):
            return True
    return False


def _intraday_source_label(intent: str, tool_results: list[dict], default_label: str) -> str:
    if intent not in {"intraday_setup", "intraday_levels"}:
        return default_label
    bars_missing = (
        _has_tool_error(tool_results, "explain_intraday_setup", "intraday.ohlcv_bars")
        or _has_tool_error(tool_results, "get_intraday_levels", "intraday.ohlcv_bars")
    )
    fallback_ok = _has_successful_tool(tool_results, "get_intraday_analysis")
    nse_snapshot_ok = _has_successful_tool(tool_results, "get_nse_intraday_snapshot")
    if bars_missing and fallback_ok and nse_snapshot_ok:
        return "NSE live API snapshot + Yahoo Finance fallback candles"
    if bars_missing and nse_snapshot_ok:
        return "NSE live API snapshot; PostgreSQL intraday OHLCV unavailable"
    return default_label


@dataclasses.dataclass
class _PipelineCtx:
    """AA-AR-2: Per-turn pipeline state shared across _query_single stages.

    Mutable fields (``source_label``, ``mode_suffix``, ``trace``) are
    updated in-place by stages that refine the source attribution or
    accumulate tool/step audit entries.  The ``raw_input`` field carries
    the original pre-stripped user_input so quality-check helpers that
    compare input length see the real query, not a pronoun-expanded form.
    """
    raw_input: str        # original user_input before prefix stripping
    clean_input: str      # prefix-stripped + pronoun-contextualized
    mode: str             # "intraday" | "historical" | "global"
    source_label: str     # mutable — overridden by keyword/intent stage
    mode_suffix: str      # mutable — footer appended to every answer
    mode_context: str     # system hint for LLM prompt
    mode_sources: dict    # {"intraday": ..., "historical": ..., "global": ...}
    market_status: object  # MarketSessionStatus (compact_label, clock_label)
    show_trace: bool
    trace: list = dataclasses.field(default_factory=list)


class Agent:
    """Agent Adda NLP Query Agent."""

    # Approx token budget for rolling history (chars ÷ 4 ≈ tokens).
    # At ~4 chars/token, 40_000 chars ≈ 10k tokens — safe headroom for most models.
    _HISTORY_CHAR_BUDGET = 40_000
    # Hard cap: never keep more than 20 turns (40 messages) regardless of size
    _HISTORY_MAX_TURNS   = 20
    # After this many turns in _history, compress the oldest half into a
    # CompressedContext block that is injected into every subsequent LLM prompt.
    _COMPRESSION_TRIGGER_TURNS = 10
    _OPENAI_TOOL_SCHEMA_LIMIT = 128
    _FALLBACK_TOOL_PRIORITY = (
        "resolve_symbol",
        "get_symbol_snapshot",
        "get_technical_setup",
        "get_sector_context",
        "scrape_screener_in",
        "search_latest_catalysts",
        "search_nse_announcements",
        "search_bse_filings",
        "search_concall_transcripts",
        "search_broker_research",
        "run_forensic_analysis",
        "get_latest_results",
        "analyze_document",
        "fetch_pdf_text",
        "generate_report",
    )
    _TOOL_SEARCH_STOPWORDS = {
        "the", "and", "for", "with", "from", "this", "that", "what", "when",
        "where", "which", "would", "should", "could", "please", "using",
        "about", "into", "then", "than", "your", "tool", "tools", "call",
        "latest", "best", "show", "give", "tell", "need", "want", "based",
    }

    def __init__(self):
        self.backend      = _detect_backend()
        self.tool_schemas = openai_tool_schemas()
        self.backend_name = _backend_name(self.backend)
        # Rolling conversation history: list of {"role": ..., "content": ...}
        # Only user + assistant turns (no system, no tool messages).
        self._history: list[dict] = []
        self._last_symbols: list[str] = []
        self._last_turn_context: TurnContext | None = None
        # Parallel list of per-turn tool results (same length as _history // 2).
        # Used by the compression pass to extract structured data without
        # re-parsing the assistant text.
        self._turn_tool_data: list[list[dict]] = []
        # Cumulative compressed context produced when _history exceeds
        # _COMPRESSION_TRIGGER_TURNS.  Injected into every LLM prompt.
        self._compressed_context: CompressedContext | None = None
        # Absolute turn counter (never resets within a session — used for
        # CompressedContext.turn_range tracking).
        self._total_turns: int = 0
        self._memory_session_id = os.environ.get("AGENT_ADDA_MEMORY_SESSION_ID", MEMORY_DEFAULT_SESSION_ID)
        self._memory_pg_enabled = os.environ.get("AGENT_ADDA_MEMORY_PG", "1").lower() not in {"0", "false", "no"}
        self._memory = (
            load_memory_fail_open(self._memory_session_id)
            if self._memory_pg_enabled
            else ConversationMemory(session_id=self._memory_session_id)
        )
        self._agentic_turn_state: AgenticTurnState | None = (
            AgenticTurnState.from_dict(self._memory.agentic_state)
            if getattr(self._memory, "agentic_state", None)
            else None
        )
        # AA-CC-2: permission policy controls clarification asking,
        # tool execution (plan mode), and future approval gates.
        # Defaults from AGENT_ADDA_PERMISSION_MODE env var.
        self._permission_policy: PermissionPolicy = PermissionPolicy.from_env()
        # Most recent assistant clarification (set when we render an
        # ask_clarification turn). The next user input is matched against
        # its options; the bound_action is executed verbatim without
        # re-running symbol/entity resolution. Cleared after one turn.
        self._pending_clarification: SituationAssessment | None = None
        self._pending_skill_store_assessment = None
        self._skill_store_repository = (
            SkillStoreRepository(dsn=default_skill_store_dsn())
            if _skill_store_runtime_enabled()
            else None
        )
        self._skill_store_embedding_provider = None

    def set_permission_mode(self, mode: str | PermissionMode | None) -> PermissionMode:
        """Update the permission policy at runtime; returns the resolved mode."""
        self._permission_policy = PermissionPolicy.of(mode)
        return self._permission_policy.mode

    @property
    def permission_mode(self) -> PermissionMode:
        return self._permission_policy.mode

    def _handle_mode_command(self, user_input: str) -> dict | None:
        """Handle the ``/mode`` slash command.

        Forms:
          * ``/mode``         → show the current mode
          * ``/mode help``    → list available modes
          * ``/mode <name>``  → switch to that mode

        Returns a ``query()``-shaped dict when the input is a ``/mode``
        command; ``None`` otherwise so the normal pipeline runs.
        """
        raw = (user_input or "").strip()
        if not raw or not raw.startswith("/mode"):
            return None
        rest = raw[len("/mode"):]
        # Only treat as /mode when followed by whitespace or end-of-string
        # so "/modest" / "/modern" fall through to the normal pipeline.
        if rest and not rest[0].isspace():
            return None
        rest = rest.strip()
        valid = [m.value for m in PermissionMode]
        if not rest:
            answer = (
                f"▶ PERMISSION MODE\n"
                f"  Current: {self._permission_policy.mode.value}\n"
                f"  Valid:   {', '.join(valid)}\n"
                f"  Usage:   /mode <name>"
            )
            return {
                "answer": answer,
                "trace": [{"step": "mode_command", "action": "show",
                           "mode": self._permission_policy.mode.value}],
                "backend": self.backend_name,
                "intent": "mode_command",
                "usage": {"input_tokens": 0, "output_tokens": 0,
                          "cache_read_input_tokens": 0,
                          "cache_creation_input_tokens": 0},
            }
        if rest.lower() in {"help", "?", "list"}:
            answer = (
                "▶ PERMISSION MODE — available modes\n"
                "  default            Ask clarifications, execute plans (historical default).\n"
                "  auto               Reserved; currently equivalent to default.\n"
                "  dontAsk            Never block on clarifications; auto-pick the default option.\n"
                "  plan               Emit the tool plan summary; do not execute.\n"
                "  bypassPermissions  Equivalent to dontAsk; reserved for future approval gates.\n"
                f"\nCurrent: {self._permission_policy.mode.value}"
            )
            return {
                "answer": answer,
                "trace": [{"step": "mode_command", "action": "help"}],
                "backend": self.backend_name,
                "intent": "mode_command",
                "usage": {"input_tokens": 0, "output_tokens": 0,
                          "cache_read_input_tokens": 0,
                          "cache_creation_input_tokens": 0},
            }
        try:
            new_mode = self.set_permission_mode(rest)
        except ValueError as exc:
            answer = (
                f"▶ PERMISSION MODE — error\n"
                f"  {exc}\n"
                f"  Current: {self._permission_policy.mode.value}"
            )
            return {
                "answer": answer,
                "trace": [{"step": "mode_command", "action": "error",
                           "input": rest, "error": str(exc)}],
                "backend": self.backend_name,
                "intent": "mode_command",
                "usage": {"input_tokens": 0, "output_tokens": 0,
                          "cache_read_input_tokens": 0,
                          "cache_creation_input_tokens": 0},
            }
        answer = (
            f"▶ PERMISSION MODE\n"
            f"  Switched to: {new_mode.value}\n"
            f"  (was applied via /mode; run /mode help for a description)"
        )
        return {
            "answer": answer,
            "trace": [{"step": "mode_command", "action": "set",
                       "mode": new_mode.value}],
            "backend": self.backend_name,
            "intent": "mode_command",
            "usage": {"input_tokens": 0, "output_tokens": 0,
                      "cache_read_input_tokens": 0,
                      "cache_creation_input_tokens": 0},
        }

    def _handle_brainstorm_command(self, user_input: str) -> dict | None:
        """Handle the ``/brainstorm <topic>`` slash command.

        Calls the LLM with a market-context-aware system prompt so it generates
        real ideas rather than a static scaffold.  Returns ``None`` if the input
        is not a /brainstorm command.
        """
        raw = (user_input or "").strip()
        if not raw.startswith("/brainstorm"):
            return None
        rest = raw[len("/brainstorm"):]
        if rest and not rest[0].isspace():
            return None  # e.g. "/brainstorming" — not our command
        topic = rest.strip() or "general trading ideas"

        ctx_symbols = list(self._last_symbols) if self._last_symbols else []
        symbol_line = (
            f"Current session symbols: {', '.join(ctx_symbols)}." if ctx_symbols
            else "No specific symbol in context — answer for the broader NSE market."
        )

        system_prompt = (
            "You are Agent Adda, an NSE market intelligence assistant. "
            "The user has invoked /brainstorm to explore ideas before committing to any action. "
            "Your job: generate a structured, insightful brainstorm — real ideas with market reasoning, "
            "not generic advice. Use your knowledge of NSE instruments, F&O dynamics, intraday/swing "
            "setups, and risk management. Be specific and actionable but make clear nothing is executed "
            "until the user approves.\n\n"
            f"{symbol_line}\n\n"
            "Format your response with these sections:\n"
            "## 💡 Ideas & Approaches\n"
            "## ⚠️ Risks & Assumptions\n"
            "## ✅ Recommendation\n"
            "## 🚦 Approval Gate\n"
            "End with: 'Reply `approved` to proceed or describe changes.'"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Brainstorm: {topic}"},
        ]
        try:
            resp = self.backend.chat(messages)
            answer = (resp.get("content") or "").strip()
            if not answer:
                answer = f"## 💡 Brainstorm: {topic}\n\n*(LLM returned empty response — try again)*"
            usage = resp.get("usage") or {}
        except Exception as exc:
            log.warning("brainstorm LLM call failed: %s", exc)
            answer = f"## 💡 Brainstorm: {topic}\n\n⚠️ LLM error: {exc}\n\nTry again or check your API key."
            usage = {}
        return {
            "answer": answer,
            "trace": [{"step": "brainstorm_command", "topic": topic,
                       "context_symbols": ctx_symbols}],
            "backend": self.backend_name,
            "intent": "brainstorm_command",
            "usage": {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
                "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
            },
        }

    @staticmethod
    def _tool_schema_name(schema: dict) -> str:
        function = schema.get("function") if isinstance(schema, dict) else {}
        return str((function or {}).get("name") or "")

    @classmethod
    def _tool_query_terms(cls, text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9]{3,}", (text or "").lower())
            if token not in cls._TOOL_SEARCH_STOPWORDS
        }

    @classmethod
    def _tool_schema_search_text(cls, schema: dict) -> str:
        function = schema.get("function") if isinstance(schema, dict) else {}
        name = str((function or {}).get("name") or "")
        description = str((function or {}).get("description") or "")
        params = ((function or {}).get("parameters") or {}).get("properties") or {}
        param_names = " ".join(str(key) for key in params.keys()) if isinstance(params, dict) else ""
        return f"{name} {name.replace('_', ' ')} {description} {param_names}".lower()

    @classmethod
    def _tool_schema_score(cls, schema: dict, query: str, query_terms: set[str]) -> int:
        name = cls._tool_schema_name(schema).lower()
        if not name:
            return 0
        search_text = cls._tool_schema_search_text(schema)
        schema_terms = cls._tool_query_terms(search_text)
        name_terms = cls._tool_query_terms(name.replace("_", " "))
        overlap = query_terms & schema_terms
        score = len(overlap)
        score += 3 * len(query_terms & name_terms)
        if name in query:
            score += 20
        if name.replace("_", " ") in query:
            score += 12
        if name_terms and name_terms.issubset(query_terms):
            score += 8
        return score

    def _tool_selection_text(self, user_input: str) -> str:
        parts = [user_input or ""]
        context = self._last_turn_context
        if context is not None:
            parts.extend([
                str(context.intent or ""),
                str(context.result_summary or ""),
                " ".join(str(symbol) for symbol in (context.symbols or [])),
                " ".join(str(tool) for tool in (context.tools or [])),
            ])
        if getattr(self, "_memory", None) is not None:
            parts.append(self._memory.compressed_summary())
        return "\n".join(part for part in parts if part)

    def _tool_schemas_for_query(self, user_input: str) -> list[dict]:
        """Return a bounded, query-relevant tool schema list for LLM calls."""
        schemas = list(self.tool_schemas or [])
        if len(schemas) <= self._OPENAI_TOOL_SCHEMA_LIMIT:
            return schemas

        query = (user_input or "").lower()
        mentioned = [
            schema for schema in schemas
            if self._tool_schema_name(schema)
            and re.search(rf"(?<![A-Za-z0-9_]){re.escape(self._tool_schema_name(schema).lower())}(?![A-Za-z0-9_])", query)
        ]
        if mentioned:
            return mentioned[: self._OPENAI_TOOL_SCHEMA_LIMIT]

        query_terms = self._tool_query_terms(query)
        scored = [
            (self._tool_schema_score(schema, query, query_terms), idx, schema)
            for idx, schema in enumerate(schemas)
        ]
        searched = [
            schema
            for score, _idx, schema in sorted(scored, key=lambda item: (-item[0], item[1]))
            if score > 0
        ]
        if searched:
            return searched[: self._OPENAI_TOOL_SCHEMA_LIMIT]

        by_name = {self._tool_schema_name(schema): schema for schema in schemas}
        selected: list[dict] = []
        seen: set[str] = set()
        for name in self._FALLBACK_TOOL_PRIORITY:
            schema = by_name.get(name)
            if schema:
                selected.append(schema)
                seen.add(name)
        for schema in schemas:
            name = self._tool_schema_name(schema)
            if name and name not in seen:
                selected.append(schema)
                seen.add(name)
            if len(selected) >= self._OPENAI_TOOL_SCHEMA_LIMIT:
                break
        return selected

    def model_status(self) -> dict:
        """Return the active main chat backend status. Voice STT/TTS models are separate."""
        provider = (
            "openai" if isinstance(self.backend, _OpenAIBackend) else
            "ollama" if isinstance(self.backend, _OllamaBackend) else
            "keyword"
        )
        model = getattr(self.backend, "model", None)
        return {"provider": provider, "model": model, "backend": self.backend_name}

    def set_model_backend(self, provider: str, model: str | None = None) -> dict:
        """Switch the main chat backend at runtime.

        This only affects the main Agent Adda reasoning backend. Voice
        transcription and TTS keep using their own OPENAI_TRANSCRIBE_MODEL and
        OPENAI_TTS_MODEL settings.
        """
        clean_provider = (provider or "").strip().lower()
        # Accept any explicit OpenAI model name as the provider arg too
        # (e.g. `/model gpt-4o-mini` → provider="gpt-4o-mini").  This avoids
        # requiring users to type `/model gpt-4o gpt-4o-mini`.
        # Changed: route any "gpt-*" / "o1*" / "o3*" / "o4*" string to OpenAI.
        is_openai_alias = (
            clean_provider in {"gpt-4o", "gpt4o", "got-40", "got-4o", "openai"}
            or clean_provider.startswith(("gpt-", "gpt4", "o1", "o3", "o4"))
        )
        if is_openai_alias:
            if clean_provider in {"openai"}:
                clean_model = model
            elif clean_provider in {"gpt-4o", "gpt4o", "got-40", "got-4o"}:
                clean_model = model or "gpt-4o"
            else:
                # provider arg is itself a model name (e.g. "gpt-4o-mini")
                clean_model = model or clean_provider
            try:
                self.backend = _OpenAIBackend(model=clean_model)
            except Exception as exc:
                return {
                    "status": "error",
                    "error": f"OpenAI backend unavailable: {exc}",
                    "provider": "openai",
                    "model": clean_model or os.getenv("OPENAI_MODEL", OPENAI_MODEL),
                }
        elif clean_provider in {"ollama", "local"}:
            try:
                self.backend = _OllamaBackend(model=model)
            except Exception as exc:
                return {
                    "status": "error",
                    "error": f"Ollama backend unavailable: {exc}",
                    "provider": "ollama",
                    "model": model or os.getenv("OLLAMA_MODEL", OLLAMA_MODEL),
                }
        elif clean_provider in {"keyword", "none", "off"}:
            self.backend = None
        else:
            return {
                "status": "error",
                "error": "Usage: /model status | /model gpt-4o | /model gpt-4o-mini | /model ollama [model-name] | /model keyword",
            }

        self.backend_name = _backend_name(self.backend)
        return {"status": "ok", **self.model_status()}

    @property
    def turn_count(self) -> int:
        """Number of completed user→assistant turns in current session."""
        return sum(1 for m in self._history if m["role"] == "user")

    def reset_history(self) -> None:
        """Clear conversation history — start a fresh session."""
        self._history = []
        self._last_symbols = []
        self._last_turn_context = None
        self._agentic_turn_state = None
        self._turn_tool_data = []
        self._compressed_context = None
        self._total_turns = 0
        self._memory = ConversationMemory(session_id=self._memory_session_id)

    def _maybe_compress(self) -> None:
        """Compress the oldest turns when the active window hits the trigger.

        After _COMPRESSION_TRIGGER_TURNS (10) turns in _history the first 10
        turn-pairs are extracted, passed to compress_turns() and merged into
        _compressed_context.  The compressed pairs are then removed from
        _history and _turn_tool_data so the active window stays lean.

        Compression is transparent to all callers — the summary is injected
        into _llm_query automatically.
        """
        n_turns = len(self._history) // 2          # current number of full pairs
        if n_turns < self._COMPRESSION_TRIGGER_TURNS:
            return

        trigger = self._COMPRESSION_TRIGGER_TURNS  # 10
        # Slice the oldest `trigger` pairs out of _history
        pairs_msgs   = self._history[:trigger * 2]      # 20 messages
        remain_msgs  = self._history[trigger * 2:]

        # Build (user, assistant) tuples for the compressor
        history_pairs: list[tuple[str, str]] = []
        for i in range(0, len(pairs_msgs) - 1, 2):
            u = str(pairs_msgs[i].get("content") or "")
            a = str(pairs_msgs[i + 1].get("content") or "")
            history_pairs.append((u, a))

        # Matching tool data rows
        tool_data = self._turn_tool_data[:trigger]
        remain_tools = self._turn_tool_data[trigger:]

        # Turn offset for accurate range tracking
        turn_offset = self._total_turns - n_turns

        logger.debug(
            "Context compression: compressing turns %d–%d (%d pairs)",
            turn_offset, turn_offset + trigger - 1, trigger,
        )

        try:
            new_ctx = compress_turns(
                history_pairs,
                tool_data,
                backend=self.backend,
                turn_offset=turn_offset,
            )
            self._compressed_context = merge_compressed(self._compressed_context, new_ctx)
            logger.debug(
                "Compression complete — symbols=%s topics=%s",
                self._compressed_context.symbols_analyzed,
                self._compressed_context.topics_covered,
            )
        except Exception:
            logger.warning("Context compression failed — history kept intact", exc_info=True)
            return  # don't trim history if compression failed

        # Trim active window
        self._history = remain_msgs
        self._turn_tool_data = remain_tools

    def _contextualize_pronouns(self, user_input: str) -> str:
        """Replace stock pronouns with the last resolved symbol for routing."""
        if not self._last_symbols:
            return user_input
        if not re.search(r"\b(it|that stock|this stock)\b", user_input or "", flags=re.I):
            return user_input
        symbol = self._last_symbols[0]
        text = re.sub(r"\bthat stock\b", symbol, user_input, flags=re.I)
        text = re.sub(r"\bthis stock\b", symbol, text, flags=re.I)
        text = re.sub(r"\bit\b", symbol, text, flags=re.I)
        return text

    def _remember_interaction(
        self,
        user_input: str,
        answer: str,
        tool_results: list[dict],
        turn_context: TurnContext | None = None,
        include_in_history: bool = True,
    ) -> None:
        """Persist compact chat state plus the latest resolved symbols.

        include_in_history=False skips appending to self._history (used for
        hallucination-guard refusals and no-match clarification clears so those
        turns do not pollute the rolling LLM context).  PostgreSQL persistence
        still fires regardless so the audit trail remains complete.
        """
        symbols: list[str] = []
        for tr in tool_results:
            args = tr.get("args") if isinstance(tr.get("args"), dict) else {}
            result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
            if tr.get("tool") == "compare_stocks" and isinstance(args.get("symbols"), list):
                symbols.extend(str(s).upper() for s in args["symbols"] if s)
            if result.get("symbol"):
                symbols.append(str(result["symbol"]).upper())
            if args.get("symbol"):
                symbols.append(str(args["symbol"]).upper())
        clean_symbols = [
            s for s in dict.fromkeys(symbols)
            if re.fullmatch(r"[A-Z0-9&-]{2,12}", s)
        ]
        if clean_symbols:
            self._last_symbols = clean_symbols[:5]
        if turn_context is not None:
            self._last_turn_context = turn_context

        if agentic_orchestrator_enabled() and (tool_results or turn_context is not None):
            self._refresh_agentic_turn_state(
                user_input=user_input,
                intent=turn_context.intent if turn_context is not None else "llm_driven",
                tool_results=tool_results,
                answer=answer,
            )

        if include_in_history:
            if not hasattr(self, "_turn_tool_data"):
                self._turn_tool_data = []
            if not hasattr(self, "_total_turns"):
                self._total_turns = 0
            if not hasattr(self, "_compressed_context"):
                self._compressed_context = None
            self._history.append({"role": "user", "content": user_input})
            self._history.append({"role": "assistant", "content": answer})
            # Track tool results in parallel with history for compression
            self._turn_tool_data.append(list(tool_results or []))
            self._total_turns += 1
            # Compress when the active window exceeds the trigger threshold
            self._maybe_compress()
        memory_context = turn_context or self._last_turn_context
        if getattr(self, "_memory", None) is not None:
            try:
                self._memory.record_turn(user_input, answer, tool_results, memory_context)
                if self._memory_pg_enabled:
                    self._memory.save_to_postgres()
            except Exception:
                # Memory persistence must never break the research answer path.
                logger.debug("Memory persistence failed — answer unaffected", exc_info=True)

    def _refresh_agentic_turn_state(
        self,
        *,
        user_input: str,
        intent: str,
        tool_results: list[dict],
        answer: str,
    ) -> AgenticTurnState | None:
        """Refresh compact agentic state from grounded tool evidence."""
        if not agentic_orchestrator_enabled():
            return None
        try:
            state = build_agentic_turn_state(
                user_input=user_input,
                intent=intent,
                tool_results=tool_results,
                answer=answer,
                previous_state=self._agentic_turn_state,
            )
        except Exception:
            logger.debug("Agentic state refresh failed", exc_info=True)
            return None
        if state is None:
            return None
        self._agentic_turn_state = state
        if getattr(self, "_memory", None) is not None:
            self._memory.agentic_state = state.to_dict()
        return state

    def _apply_agentic_next_action_block(
        self,
        answer: str,
        user_input: str,
        intent: str,
        tool_results: list[dict],
    ) -> str:
        """Append a grounded next-action block for tool-backed turns."""
        state = self._refresh_agentic_turn_state(
            user_input=user_input,
            intent=intent,
            tool_results=tool_results,
            answer=answer,
        )
        return append_next_action_block(answer, state)

    # ─── AA-UR-6: Unified router scaffolding ────────────────────────────────
    @property
    def _unified_router(self) -> UnifiedRouter:
        """Lazily-constructed shared :class:`UnifiedRouter` instance."""
        router = getattr(self, "_unified_router_instance", None)
        if router is None:
            router = UnifiedRouter()
            self._unified_router_instance = router
        return router

    def _build_context_pack(self):
        """Snapshot the current :class:`ConversationMemory` into a ContextPack.

        Returns ``None`` if memory is unavailable or snapshotting fails —
        the router invocation is always best-effort and never breaks the
        legacy dispatcher path.
        """
        memory = getattr(self, "_memory", None)
        if memory is None:
            return None
        try:
            return memory.build_context_pack(depth=5)
        except Exception:
            logger.debug("_build_context_pack failed — router will be skipped", exc_info=True)
            return None

    def _execute_route(
        self,
        decision: RouteDecision,
        clean_input: str,
        mode: str,
        source_label: str,
        mode_suffix: str,
        trace: list[dict],
    ) -> dict | None:
        """Execute a :class:`RouteDecision` if the unified router owns its path.

        Returns the agent response dict when the router fully handles the
        request, or ``None`` to fall through to subsequent stages of
        :meth:`_query_single` (entity topic → situation assessment →
        keyword + LLM).

        Owned route types: ``compound_plan`` and ``direct_tool_plan``
        emitted by providers in :data:`_ROUTER_DIRECT_PLAN_PROVIDERS`.

        Fall through (return ``None``):
          * ``blocked_ungrounded`` — validation rewrote the plan to a
            refusal.  Subsequent stages may still serve the prompt
            (e.g. the LLM path can answer a generic question that the
            router considered ungrounded).
          * ``contextual_answer`` — ContextualFollowupProvider and
            ReportProvider carry no executable plan; the
            situation-assessment stage handles them with
            context-synthesis logic.
          * Validation failure or empty tool plan — defensive guard.
          * Selected provider not in the direct-plan set.
        """
        selected = decision.reasoning_summary.selected_branch
        route_type = decision.route_type

        if route_type == "blocked_ungrounded":
            trace.append({"step": "router_fallthrough", "reason": "blocked_ungrounded"})
            return None

        if not decision.validation.ok or not decision.tool_plan:
            trace.append({
                "step": "router_fallthrough",
                "reason": "no_executable_plan",
                "route_type": route_type,
            })
            return None

        if selected not in _ROUTER_DIRECT_PLAN_PROVIDERS:
            return None
        if route_type not in {"compound_plan", "direct_tool_plan"}:
            return None

        tool_plan = decision.tool_plan_tuples()
        if self._permission_policy.is_plan:
            return self._render_plan_preview(
                tool_plan,
                intent=decision.intent,
                clean_input=clean_input,
                mode_suffix=mode_suffix,
                trace=trace,
            )
        has_deps = any(getattr(s, "blocked_by", ()) for s in decision.tool_plan)
        if has_deps:
            from terminal.router.task_graph import dependency_layers
            layers = dependency_layers(decision.tool_plan)
            tool_results = _execute_plan_layered(decision.tool_plan)
            trace.append({"step": "layered_execution", "layers": len(layers)})
        else:
            tool_results = _execute_plan(tool_plan)
        trace.extend(tool_results)

        # Derive the synthesis intent from the executed plan tools so the
        # synthesiser and claim-gate both see a consistent intent label.
        # CompoundStockProvider keeps "intraday_setup" to match the legacy
        # multi-stock setup guardrail contract.  All other providers resolve
        # via the tool-to-intent map.
        if selected == "CompoundStockProvider":
            synthesis_intent = "intraday_setup"
        else:
            # Derive from the tools that actually ran so that synthesis intent
            # stays consistent with tool_results (matters when _execute_plan is
            # mocked in tests and the result set diverges from the planned tools).
            _ran = [(tr["tool"], {}) for tr in tool_results] or tool_plan
            synthesis_intent = _synthesis_intent_from_plan(_ran, query=clean_input)

        answer_body = _synthesize_and_narrate(
            synthesis_intent, clean_input, tool_results, self.backend,
        )
        answer_body = _apply_response_guardrails(
            clean_input, synthesis_intent, tool_results, answer_body,
        )
        answer_body = self._apply_agentic_next_action_block(
            answer_body, clean_input, synthesis_intent, tool_results,
        )
        answer = answer_body + mode_suffix
        turn_context = build_turn_context(
            user_input=clean_input,
            intent=decision.intent,
            mode=mode,
            source_label=source_label,
            tool_results=tool_results,
            answer=answer,
        )
        self._remember_interaction(
            clean_input, answer, tool_results, turn_context=turn_context,
        )

        # Best-effort consume the matched pending option so it can't fire twice.
        if selected == "PendingOptionProvider":
            try:
                label_token = clean_input.strip().split()[0]
                label_token = label_token.rstrip(".)").strip()
                if label_token:
                    self._memory.consume_pending_option(label_token)
            except Exception:
                pass

        return {
            "answer": answer,
            "trace": trace,
            "backend": self.backend_name,
            "intent": decision.intent,
            "has_source_trail": True,  # mode_suffix always appended above
        }

    def _conversation_fallback_context(self, *, mode: str, source_label: str) -> TurnContext | None:
        """Build minimal context from rolling history when structured context is absent."""
        if getattr(self, "_memory", None) is not None:
            memory_context = self._memory.context_for_query(
                "previous analysis",
                mode=mode,
                source_label=source_label,
            )
            if memory_context is not None:
                return memory_context
        if not self._history:
            return None
        recent = "\n".join(str(m.get("content") or "") for m in self._history[-6:])
        symbols = list(dict.fromkeys(re.findall(r"\b[A-Z][A-Z0-9&-]{1,12}\b", recent)))
        if not recent.strip() and not symbols:
            return None
        summary = "Previous conversation is available."
        if "Report:" in recent or "Opening report:" in recent:
            summary = "Previous conversation referenced a generated report."
        elif symbols:
            summary = f"Previous conversation referenced symbols: {', '.join(symbols[:5])}."
        return TurnContext(
            user_input="previous conversation",
            intent="conversation_history",
            mode=mode,
            tools=[],
            source_label=source_label,
            result_type="conversation_history",
            result_summary=summary,
            symbols=symbols[:10],
            result_items=symbols[:20],
        )

    def _trim_history(self) -> list[dict]:
        """Return a trimmed copy of history that fits within the char budget."""
        history = list(self._history)
        # Enforce turn cap (pairs of user+assistant = 2 messages per turn)
        max_msgs = self._HISTORY_MAX_TURNS * 2
        if len(history) > max_msgs:
            history = history[-max_msgs:]
        # Enforce char budget — drop oldest pairs until under budget
        while history:
            total = sum(len(m.get("content") or "") for m in history)
            if total <= self._HISTORY_CHAR_BUDGET:
                break
            # Drop the oldest user+assistant pair (2 messages)
            history = history[2:]
        return history

    # PG-self-check: post-processor that detects degraded responses (failed
    # tools, unhandled slash commands, suspiciously thin answers) and
    # prepends a clear acknowledgement + actionable suggestions instead of
    # silently returning a weak result.
    def _quality_check(
        self,
        original_query: str,
        intent: str,
        tool_results: list[dict],
        answer: str,
        mode_suffix: str = "",
    ) -> str:
        """Return possibly-augmented answer with a heads-up block prepended
        when the response looks degraded. Conservative — never modifies a
        clearly-good answer."""
        try:
            q = (original_query or "").strip()
            if not q:
                return answer

            # Strip mode suffix + disclaimer to measure substantive content.
            body = answer or ""
            if mode_suffix and body.endswith(mode_suffix):
                body = body[: -len(mode_suffix)]
            for marker in (
                "━━━ Not investment advice. For research and learning only. ━━━",
                "Not investment advice. For research and learning only.",
            ):
                body = body.replace(marker, "")
            body = body.strip()

            # ── Heuristic A: tool error rate ──────────────────────────────
            errs = sum(
                1 for tr in (tool_results or [])
                if isinstance(tr.get("result"), dict) and tr["result"].get("error")
            )
            n_tools = sum(1 for tr in (tool_results or []) if tr.get("tool"))
            tool_error_ratio = (errs / n_tools) if n_tools else 0.0

            # ── Heuristic B: unhandled slash command ──────────────────────
            # User typed something starting with `/` but only one token, AND
            # the planner routed it to stock_brief (i.e. the symbol resolver
            # treated the slash command as a ticker — same class of bug as
            # the original /recap → AVONMORE issue).
            words = q.split()
            unhandled_slash = (
                q.startswith("/")
                and len(words) == 1
                and intent in {"stock_brief", "intraday_setup"}
            )

            # ── Heuristic C: suspiciously thin body ───────────────────────
            thin_body = len(body) < 180

            # ── Heuristic D: every tool returned empty payload ────────────
            empty_payload = (
                n_tools >= 1
                and all(
                    (not isinstance(tr.get("result"), dict))
                    or (not tr["result"]) or tr["result"].get("error")
                    for tr in (tool_results or [])
                )
            )

            triggers: list[str] = []
            if unhandled_slash:
                triggers.append(f"`{q}` is not a registered slash command")
            if tool_error_ratio >= 0.5 and n_tools >= 2:
                triggers.append(
                    f"{errs} of {n_tools} tools failed "
                    f"({int(tool_error_ratio * 100)}% error rate)"
                )
            if thin_body and intent != "greeting":
                triggers.append("the response came back unusually thin")
            if empty_payload and not unhandled_slash:
                triggers.append("no usable data was returned by any tool")

            if not triggers:
                return answer

            # Build a context-aware suggestion list.
            qlow = q.lower()
            suggestions: list[str] = []
            if unhandled_slash:
                suggestions.append(
                    "Type `/help` to browse all slash commands, or `/commands "
                    "<keyword>` to search them."
                )
            if any(w in qlow for w in ("market", "nifty", "breadth", "today", "now")):
                suggestions.append("`/live` — live NSE indices + breadth.")
                suggestions.append("`/recap` — what moved in the last 15 minutes.")
                suggestions.append("`/heat` — sector seasonal heatmap.")
            if any(w in qlow for w in ("sector", "rotation")):
                suggestions.append("`/heat` — sector seasonal tail/headwinds.")
                suggestions.append("`/cycle` — economic-cycle phase + preferred sectors.")
            if any(w in qlow for w in ("global", "us", "fed", "dxy", "crude")):
                suggestions.append("`/global` — global risk regime + India read-through.")
            if any(w in qlow for w in ("option", "strike", "oi", "fno", "f&o")):
                suggestions.append("`/oi <SYMBOL>` — open-interest heatmap.")
                suggestions.append("`/chain <SYMBOL>` — option chain.")
            if any(w in qlow for w in ("scan", "screen", "vcp", "breakout", "momentum")):
                suggestions.append("`/scan <INDEX> <type>` — intraday screener.")
                suggestions.append("`/screen <name>` — EOD screeners.")
            if any(w in qlow for w in ("portfolio", "pnl", "holdings")):
                suggestions.append("`/pnl` — portfolio P&L review.")
            if not suggestions:
                # Universal fallback list.
                suggestions = [
                    "`/live` — live market snapshot.",
                    "`/global` — global cues + India read-through.",
                    "`/heat` — sector seasonal heatmap.",
                    "Or rephrase with a specific NSE symbol, e.g. `RELIANCE setup`.",
                ]
            # Dedupe while preserving order.
            seen = set()
            suggestions = [
                s for s in suggestions
                if not (s in seen or seen.add(s))
            ][:5]

            ack_lines = ["▶ HEADS-UP — response may be incomplete"]
            for t in triggers:
                ack_lines.append(f"  • {t}")
            ack_lines.append("")
            ack_lines.append("▶ TRY ONE OF THESE")
            for s in suggestions:
                ack_lines.append(f"  • {s}")
            clarify = (
                "Or rephrase with more context — e.g. mention a specific NSE "
                "symbol, sector, or time window (intraday / EOD / 1-month)."
            )
            ack_lines.append("")
            ack_lines.append(f"  {clarify}")
            ack_lines.append("")

            return "\n".join(ack_lines) + "\n" + (answer or "")
        except Exception:
            # Self-check must never break the response — fail open.
            return answer

    def query(
        self,
        user_input: str,
        show_trace: bool = False,
        entity_assessment=None,
    ) -> dict:
        """Process a user query. Returns {"answer": str, "trace": list, "backend": str}.

        Compound query support: if the user packs multiple distinct questions
        into one prompt (separated by ". ", " and also ", " ; ", "?" boundaries,
        etc.), split them and run each through `_query_single`, then merge the
        answers. Single-question queries are dispatched unchanged.

        entity_assessment: optional pre-computed EntityTopicAssessment from the
        caller (nse_agent REPL loop). When provided, _query_single skips the
        second assess_entity_topic_request call that would otherwise repeat
        symbol resolution.
        """
        # /mode slash command — runtime permission-mode control (AA-CC-2).
        mode_result = self._handle_mode_command(user_input)
        if mode_result is not None:
            return mode_result

        # /brainstorm slash command — market-context-aware design discussion.
        brainstorm_result = self._handle_brainstorm_command(user_input)
        if brainstorm_result is not None:
            return brainstorm_result

        parts = _split_compound_query(user_input)
        if len(parts) <= 1:
            result = self._query_single(
                user_input, show_trace=show_trace, entity_assessment=entity_assessment
            )
            _record_learning_interaction_result(self, user_input, result)
            return result

        # Multi-part compound query: dispatch each part sequentially.
        # Snapshot pre-compound state so each sub-query sees the same
        # starting context and pronoun scope, preventing sub-query N from
        # inheriting symbols/context written by sub-query N-1.
        _pre_symbols = list(self._last_symbols)
        _pre_context = self._last_turn_context
        merged_answers: list[str] = []
        merged_trace: list[dict] = []
        last_backend = self.backend_name
        compound_usage: dict = {
            "input_tokens": 0, "output_tokens": 0,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
        }
        compound_tool_results: list[dict] = []
        for idx, part in enumerate(parts, start=1):
            self._last_symbols = list(_pre_symbols)
            self._last_turn_context = _pre_context
            res = self._query_single(part, show_trace=show_trace)
            merged_answers.append(
                f"━━━ Part {idx} of {len(parts)}: {part} ━━━\n\n"
                + (res.get("answer") or "")
            )
            merged_trace.append({"step": f"compound_part_{idx}", "query": part,
                                 "intent": res.get("intent"),
                                 "trace": res.get("trace", [])})
            last_backend = res.get("backend") or last_backend
            _accumulate_usage(compound_usage, res.get("usage") or {})
            compound_tool_results.extend(
                tr for tr in (res.get("trace") or [])
                if isinstance(tr, dict) and tr.get("tool")
            )
        answer = "\n\n".join(merged_answers)
        answer += _cost_trail_block(compound_usage, compound_tool_results)
        result = {
            "answer": answer,
            "trace": merged_trace,
            "backend": last_backend,
            "intent": "compound",
            "usage": compound_usage,
        }
        _record_learning_interaction_result(self, user_input, result)
        return result

    # ── AA-AR-2: Pipeline stage helpers ──────────────────────────────────────
    # _query_single is decomposed into named stages so the dispatch logic reads
    # as a linear pipeline rather than a 500-line nested if-chain.  Each stage
    # returns a result dict when it fully handles the turn, or None to fall
    # through to the next stage.  _stage_keyword_and_llm always returns a dict.

    def _build_pipeline_ctx(self, user_input: str, show_trace: bool) -> _PipelineCtx:
        """Parse the mode prefix, build mode context and source labels."""
        clean_input = user_input
        mode = "historical"
        if user_input.startswith("/historical "):
            mode        = "historical"
            clean_input = user_input[len("/historical "):].strip()
        elif user_input.startswith("/intraday "):
            mode        = "intraday"
            clean_input = user_input[len("/intraday "):].strip()
        else:
            if _is_global_query(user_input.lower()):
                mode = "global"
            elif _looks_like_intraday_query(user_input):
                mode = "intraday"

        clean_input = self._contextualize_pronouns(clean_input)

        # ── Compressed-context symbol injection ──────────────────────────────
        # When the query is a cross-stock synthesis ("which has the best RSI",
        # "compare all the stocks we covered") and compressed context holds
        # symbols from prior turns, append them as an explicit hint so the LLM
        # can map them directly without calling resolve_symbol on vague phrases.
        if (
            self._compressed_context is not None
            and self._compressed_context.symbols_analyzed
            and _is_contextual_synthesis_query(clean_input)
        ):
            syms = ", ".join(self._compressed_context.symbols_analyzed)
            clean_input = (
                f"{clean_input} "
                f"[CONTEXT: prior stocks analysed = {syms}]"
            )
        market_context = market_context_for_agent()
        mode_context = (
            f"Data mode: {mode}. "
            + (
                "Use get_global_market_assessment for global indices, commodities, FX, "
                "correlation context, and India read-through."
                if mode == "global"
                else (
               "Use get_intraday_source_health first for calculations, then PostgreSQL-backed "
               "get_intraday_bars, compute_intraday_indicators, get_intraday_levels, "
               "explain_intraday_setup, and run_intraday_screener. If PostgreSQL intraday "
               "tables are missing or stale for a single-stock/index deep dive, call "
               "get_nse_intraday_snapshot first from the NSE website, then call "
               "get_intraday_analysis only when OHLCV candle history is required. Label "
               "yfinance/EOD fallback clearly, and do not present fallback levels as "
               "PostgreSQL/NSE live-table data."
                    if mode == "intraday"
                    else "Use EOD CSV and DB snapshot tools for historical/technical analysis."
                )
            )
            + f"\n\n{market_context}"
        )
        mode_sources = {
            "global": "cached global indices + correlations",
            "intraday": "PG intraday.quote_snapshots + PG intraday.ohlcv_bars",
            "historical": "EOD CSV + DB snapshot",
        }
        source_label = mode_sources.get(mode, "EOD CSV + DB snapshot")
        market_status = market_session_status()
        mode_suffix = (
            f"\n\n_Mode: {mode.title()} | Sources: "
            f"{source_label} | "
            f"Market: {market_status.compact_label} | "
            f"Clock: {market_status.clock_label}_"
        )
        return _PipelineCtx(
            raw_input=user_input,
            clean_input=clean_input,
            mode=mode,
            source_label=source_label,
            mode_suffix=mode_suffix,
            mode_context=mode_context,
            mode_sources=mode_sources,
            market_status=market_status,
            show_trace=show_trace,
        )

    def _with_readiness_metadata(self, answer: str, mode: str) -> str:
        """Append data-readiness metadata block for historical-mode answers."""
        if mode != "historical":
            return answer
        try:
            return append_readiness_metadata(
                answer,
                project_root=Path(__file__).resolve().parent.parent,
            )
        except Exception:
            logger.debug("append_readiness_metadata failed", exc_info=True)
            return answer

    def _stage_clarification_binding(self, ctx: _PipelineCtx) -> dict | None:
        """If a structured clarification is pending, match this reply and execute the bound action."""
        pending_clarification = self._pending_clarification
        if pending_clarification is None:
            pending_skill = self._pending_skill_store_assessment
            if pending_skill:
                original = str((pending_skill or {}).get("original_input") or "").strip()
                self._pending_skill_store_assessment = None
                if original and ctx.clean_input.strip():
                    ctx.clean_input = f"{original} {ctx.clean_input.strip()}".strip()
                    ctx.trace.append({"step": "skill_store_clarification_binding", "original_input": original})
                    return self._stage_skill_store(ctx)
            return None

        from .situation_assessment import (
            assessment_from_bound_action,
            match_clarification_reply,
        )

        def _finalize(
            answer: str,
            tool_results_: list,
            turn_context_: "TurnContext | None" = None,
            include_in_history: bool = True,
        ) -> dict:
            self._remember_interaction(
                ctx.clean_input, answer, tool_results_,
                turn_context=turn_context_,
                include_in_history=include_in_history,
            )
            return {
                "answer":  answer,
                "trace":   ctx.trace,
                "backend": self.backend_name,
                "intent":  "clarification_reply_binding",
            }

        matched_option = match_clarification_reply(ctx.clean_input, pending_clarification)
        if matched_option is not None:
            ctx.trace.append({
                "step": "clarification_reply_binding",
                "matched_label": matched_option.label,
                "matched_text": matched_option.text,
            })
            bound = assessment_from_bound_action(
                matched_option.bound_action,
                previous_context=self._last_turn_context,
            )
            self._pending_clarification = None
            previous_context = self._last_turn_context or self._conversation_fallback_context(
                mode=ctx.mode, source_label=ctx.source_label,
            )
            _fallback_ctx = previous_context or TurnContext(
                user_input="", intent="unknown", mode=ctx.mode,
                tools=[], source_label=ctx.source_label,
            )
            if bound.decision == "ask_clarification":
                answer = render_context_answer(ctx.clean_input, bound, _fallback_ctx)
                self._pending_clarification = bound
                return _finalize(answer, [])
            if bound.decision == "answer_from_context":
                answer = render_context_answer(ctx.clean_input, bound, _fallback_ctx)
                return _finalize(answer, [])
            if bound.decision == "run_tool_plan" and bound.tool_plan:
                if self._permission_policy.is_plan:
                    return self._render_plan_preview(
                        bound.tool_plan,
                        intent="clarification_reply_binding",
                        clean_input=ctx.clean_input,
                        mode_suffix=ctx.mode_suffix,
                        trace=ctx.trace,
                    )
                tool_results = _execute_plan(bound.tool_plan)
                ctx.trace.extend(tool_results)
                synthesis_intent = (
                    getattr(bound, "synthesis_intent", "")
                    or _synthesis_intent_from_plan(bound.tool_plan, query=ctx.clean_input)
                )
                answer_body = (
                    render_assessment_block(bound)
                    + "\n\n"
                    + _synthesize_and_narrate(
                        synthesis_intent, ctx.clean_input, tool_results, self.backend,
                    )
                )
                answer_body = _apply_response_guardrails(
                    ctx.clean_input, synthesis_intent, tool_results, answer_body,
                )
                answer_body = self._apply_agentic_next_action_block(
                    answer_body, ctx.clean_input, synthesis_intent, tool_results,
                )
                answer = answer_body + ctx.mode_suffix
                turn_ctx = build_turn_context(
                    user_input=ctx.clean_input,
                    intent="clarification_reply_binding",
                    mode=ctx.mode,
                    source_label=ctx.source_label,
                    tool_results=tool_results,
                    answer=answer,
                )
                return _finalize(answer, tool_results, turn_ctx)
        else:
            # Short typo-like reply that doesn't match any option: re-prompt once.
            _is_typo_like = (
                len(ctx.clean_input.strip()) <= 3
                and " " not in ctx.clean_input.strip()
            )
            if _is_typo_like:
                try:
                    reprompt = render_assessment_block(pending_clarification)
                except Exception:
                    reprompt = None
                if reprompt:
                    ctx.trace.append({
                        "step": "clarification_reprompt",
                        "original_input": ctx.clean_input,
                    })
                    return _finalize(reprompt, [], include_in_history=False)
            # User typed something that is clearly not an option reply — clear state.
            self._pending_clarification = None
        return None

    def _stage_agentic_bound_action(self, ctx: _PipelineCtx) -> dict | None:
        """Execute a previously bound agentic follow-up before generic routing."""
        if not agentic_orchestrator_enabled():
            return None
        action = (
            action_from_confirmation(ctx.clean_input, self._agentic_turn_state)
            or action_from_artifact_reference(ctx.clean_input, self._agentic_turn_state)
        )
        if action is None or not action.tool_plan:
            if is_confirmation(ctx.clean_input):
                answer = (
                    "▶ FOLLOW-UP\n"
                    "  I do not have a bound next action from the previous turn.\n"
                    "  Ask the specific action directly, for example `deep dive these stocks`, "
                    "`open the latest report`, or `email the report`."
                    f"{ctx.mode_suffix}"
                )
                self._remember_interaction(
                    ctx.clean_input,
                    answer,
                    [],
                    include_in_history=False,
                )
                return {
                    "answer": answer,
                    "trace": ctx.trace + [{"step": "agentic_confirmation_without_bound_action"}],
                    "backend": self.backend_name,
                    "intent": "agentic_unbound_confirmation",
                }
            return None
        ctx.trace.append({
            "step": "agentic_bound_action",
            "action": action.to_dict(),
        })
        if self._permission_policy.is_plan:
            return self._render_plan_preview(
                action.tool_plan,
                intent="agentic_bound_action",
                clean_input=ctx.clean_input,
                mode_suffix=ctx.mode_suffix,
                trace=ctx.trace,
                extra_lines=[f"Bound action: {action.label}"],
            )
        tool_results = _execute_plan(action.tool_plan)
        ctx.trace.extend(tool_results)
        synthesis_intent = _synthesis_intent_from_plan(
            action.tool_plan,
            default="report_lookup" if action.artifact_targets else "stock_brief",
            query=ctx.clean_input,
        )
        answer_body = render_bound_action_summary(action, tool_results)
        if not answer_body:
            answer_body = _synthesize_and_narrate(
                synthesis_intent,
                ctx.clean_input,
                tool_results,
                self.backend,
            )
        answer_body = _apply_response_guardrails(
            ctx.clean_input,
            synthesis_intent,
            tool_results,
            answer_body,
        )
        answer_body = self._apply_agentic_next_action_block(
            answer_body, ctx.clean_input, synthesis_intent, tool_results,
        )
        answer = self._with_readiness_metadata(answer_body + ctx.mode_suffix, ctx.mode)
        turn_context = build_turn_context(
            user_input=ctx.clean_input,
            intent="agentic_bound_action",
            mode=ctx.mode,
            source_label=ctx.source_label,
            tool_results=tool_results,
            answer=answer,
        )
        self._remember_interaction(
            ctx.clean_input,
            answer,
            tool_results,
            turn_context=turn_context,
        )
        return {
            "answer": answer,
            "trace": ctx.trace,
            "backend": self.backend_name,
            "intent": "agentic_bound_action",
        }

    def _stage_unified_router(self, ctx: _PipelineCtx) -> dict | None:
        """Run UnifiedRouter and execute the route when the router owns it."""
        if not (_unified_router_enabled() and not _is_morning_briefing_query(ctx.clean_input)):
            return None
        # Agent-generated 360 stock-analysis/report prompts intentionally
        # contain words like "chart", "technical", and "visual" as section
        # requirements. Let the keyword planner bind the full stock dossier
        # instead of letting VisualScanProvider preempt the report.
        if _stock_360_prompt_symbol(ctx.clean_input):
            return None
        if (
            self._last_turn_context is not None
            and is_index_context_followup(ctx.clean_input, self._last_turn_context)
        ):
            return None
        if any(term in ctx.clean_input.lower() for term in (
            "my portfolio",
            "my porfolio",
            "portfolio sector",
            "portfolio exposure",
            "portfolio distribution",
            "portfolio concentration",
            "portfolio holdings",
        )):
            return None
        qlow = ctx.clean_input.lower()
        try:
            direct_plan = _keyword_intent(ctx.clean_input, data_mode="intraday")
        except Exception:
            direct_plan = {}
        if direct_plan.get("intent") == "intraday_options_trade_plan":
            return None
        if _looks_like_stock_research_prompt(qlow) and _stock_research_symbol_from_query(ctx.clean_input):
            return None
        if "sector" in qlow and re.search(
            r"\b(?:it|pharma|auto|fmcg|banking|bank|metal|metals|realty|real estate|energy|oil\s+(?:&|and)\s+gas|consumer discretionary|consumer durables)\b",
            qlow,
        ):
            return None
        pack = self._build_context_pack()
        if pack is None:
            return None
        try:
            decision = self._unified_router.route(ctx.clean_input, pack)
        except Exception as exc:  # noqa: BLE001
            ctx.trace.append({"step": "unified_router_error", "error": repr(exc)})
            decision = None
        if decision is not None:
            ctx.trace.append({
                "step": "unified_router",
                "decision": decision.to_debug_trace(),
            })
            executed = self._execute_route(
                decision, ctx.clean_input, ctx.mode,
                ctx.source_label, ctx.mode_suffix, ctx.trace,
            )
            if executed is not None:
                return executed
        return None

    def _stage_entity_topic(
        self, ctx: _PipelineCtx, entity_assessment=None
    ) -> dict | None:
        """Resolve entity-topic queries (e.g. 'RELIANCE technicals') deterministically."""
        # Contextual follow-ups such as "open it" or "what about its EPS
        # growth" must bind to the active turn context before entity-topic
        # tries to resolve fragments like "open" or "its EPS growth" as
        # stock symbols.
        if needs_situation_assessment(ctx.clean_input) or (
            self._last_turn_context is not None
            and _is_implicit_results_followup(ctx.clean_input)
        ) or (
            self._last_turn_context is not None
            and is_index_context_followup(ctx.clean_input, self._last_turn_context)
        ) or should_run_llm_situation_assessment(ctx.clean_input, self._last_turn_context):
            return None
        if entity_assessment is None:
            entity_assessment = assess_entity_topic_request(ctx.clean_input)
        if not (entity_assessment.applies and entity_assessment.decision == "route_with_entity_topic"):
            return None
        return self._execute_entity_topic_assessment(ctx, entity_assessment)

    def _execute_entity_topic_assessment(self, ctx: _PipelineCtx, entity_assessment) -> dict | None:
        """Execute an entity/topic assessment as a situation-owned sub-route."""
        ctx.trace.append({"step": "entity_topic_assessment", "result": entity_assessment.__dict__})
        entity_plan = _entity_topic_execution_plan(entity_assessment)
        if not entity_plan:
            return None
        if self._permission_policy.is_plan:
            return self._render_plan_preview(
                entity_plan,
                intent="entity_topic_command",
                clean_input=ctx.clean_input,
                mode_suffix=ctx.mode_suffix,
                trace=ctx.trace,
            )
        tool_results = _execute_plan(entity_plan)
        ctx.trace.extend(tool_results)
        answer_body = _synthesize_and_narrate(
            "entity_topic_command", ctx.clean_input, tool_results, self.backend,
        )
        answer_body = _apply_response_guardrails(
            ctx.clean_input, "entity_topic_command", tool_results, answer_body,
        )
        answer_body = self._apply_agentic_next_action_block(
            answer_body, ctx.clean_input, "entity_topic_command", tool_results,
        )
        answer = self._with_readiness_metadata(answer_body + ctx.mode_suffix, ctx.mode)
        turn_context = build_turn_context(
            user_input=ctx.clean_input,
            intent="entity_topic_command",
            mode=ctx.mode,
            source_label=ctx.source_label,
            tool_results=tool_results,
            answer=answer,
        )
        self._remember_interaction(ctx.clean_input, answer, tool_results, turn_context=turn_context)
        return {
            "answer": answer,
            "trace": ctx.trace,
            "backend": self.backend_name,
            "intent": "entity_topic_command",
        }

    def _render_plan_preview(
        self,
        tool_plan,
        *,
        intent: str,
        clean_input: str,
        mode_suffix: str,
        trace: list[dict],
        extra_lines: list[str] | None = None,
    ) -> dict:
        """AA-CC-2 plan mode: produce a non-executing preview of a tool plan.

        Callers guard with ``self._permission_policy.is_plan`` and skip
        :func:`_execute_plan` when this returns a response dict.
        """
        plan_list = list(tool_plan or [])
        steps = len(plan_list)
        lines = [
            "▶ PLAN MODE — no tools executed",
            f"  Intent: {intent}",
            f"  Mode: {self._permission_policy.mode.value}",
            "",
            f"▶ TOOL PLAN ({steps} step{'s' if steps != 1 else ''})",
        ]
        for idx, item in enumerate(plan_list, start=1):
            try:
                tool, args = item
            except (TypeError, ValueError):
                lines.append(f"  {idx}. {item!r}")
                continue
            try:
                args_repr = ", ".join(f"{k}={v!r}" for k, v in (args or {}).items())
            except Exception:
                args_repr = "<args>"
            lines.append(f"  {idx}. {tool}({args_repr})")
        if extra_lines:
            lines.append("")
            lines.extend(extra_lines)
        lines.append("")
        lines.append(
            "Switch to `default` mode (or unset AGENT_ADDA_PERMISSION_MODE) "
            "and re-issue the same query to execute this plan."
        )
        answer = "\n".join(lines) + (mode_suffix or "")
        trace.append({
            "step": "plan_mode_preview",
            "intent": intent,
            "tool_count": steps,
        })
        try:
            self._remember_interaction(clean_input, answer, [], include_in_history=False)
        except TypeError:
            self._remember_interaction(clean_input, answer, [])
        return {
            "answer": answer,
            "trace": trace,
            "backend": self.backend_name,
            "intent": f"plan_preview:{intent}",
        }

    def _auto_dispatch_default_clarification(
        self,
        assessment: "SituationAssessment",
        ctx: "_PipelineCtx",
        previous_context: "TurnContext",
    ) -> dict | None:
        """AA-CC-2: pick the default-labelled option and execute its bound_action.

        Used when the permission policy says "don't ask" — instead of
        surfacing the clarification, the default option's bound_action
        is dispatched as if the user had typed that label. Returns the
        same response shape as the regular pipeline stages, or ``None``
        if no usable default can be found.
        """
        from .situation_assessment import assessment_from_bound_action

        default_option = None
        for q in assessment.clarification_questions or ():
            label = (q.default_label or "").strip()
            if not label:
                continue
            for opt in q.options:
                if opt.label == label:
                    default_option = opt
                    break
            if default_option is not None:
                break
        if default_option is None:
            ctx.trace.append({
                "step": "permission_mode_auto_dispatch_skipped",
                "mode": self._permission_policy.mode.value,
                "reason": "no_default_option",
            })
            return None

        ctx.trace.append({
            "step": "permission_mode_auto_dispatch",
            "mode": self._permission_policy.mode.value,
            "label": default_option.label,
            "text": default_option.text,
        })

        bound = assessment_from_bound_action(
            default_option.bound_action,
            previous_context=previous_context,
        )
        if bound.decision == "answer_from_context":
            answer = render_context_answer(ctx.clean_input, bound, previous_context)
            self._remember_interaction(ctx.clean_input, answer, [])
            return {
                "answer": answer,
                "trace": ctx.trace,
                "backend": self.backend_name,
                "intent": "permission_mode_auto_dispatch",
            }
        if bound.decision == "run_tool_plan" and bound.tool_plan:
            if self._permission_policy.is_plan:
                return self._render_plan_preview(
                    bound.tool_plan,
                    intent="permission_mode_auto_dispatch",
                    clean_input=ctx.clean_input,
                    mode_suffix=ctx.mode_suffix,
                    trace=ctx.trace,
                )
            tool_results = _execute_plan(bound.tool_plan)
            ctx.trace.extend(tool_results)
            synthesis_intent = (
                getattr(bound, "synthesis_intent", "")
                or _synthesis_intent_from_plan(bound.tool_plan, query=ctx.clean_input)
            )
            answer_body = (
                render_assessment_block(bound)
                + "\n\n"
                + _synthesize_and_narrate(
                    synthesis_intent, ctx.clean_input, tool_results, self.backend,
                )
            )
            answer_body = _apply_response_guardrails(
                ctx.clean_input, synthesis_intent, tool_results, answer_body,
            )
            answer_body = self._apply_agentic_next_action_block(
                answer_body, ctx.clean_input, synthesis_intent, tool_results,
            )
            answer = answer_body + ctx.mode_suffix
            turn_ctx = build_turn_context(
                user_input=ctx.clean_input,
                intent="permission_mode_auto_dispatch",
                mode=ctx.mode,
                source_label=ctx.source_label,
                tool_results=tool_results,
                answer=answer,
            )
            self._remember_interaction(
                ctx.clean_input, answer, tool_results, turn_context=turn_ctx,
            )
            return {
                "answer": answer,
                "trace": ctx.trace,
                "backend": self.backend_name,
                "intent": "permission_mode_auto_dispatch",
            }
        return None

    def _stage_situation_assessment(self, ctx: _PipelineCtx) -> dict | None:
        """Handle contextual follow-ups via situation assessment."""
        if _stock_360_prompt_symbol(ctx.clean_input):
            return None
        entity_assessment = assess_entity_topic_request(ctx.clean_input)
        needs_context = needs_situation_assessment(ctx.clean_input)
        if not needs_context and entity_assessment.applies:
            needs_context = True
        if (
            not needs_context
            and self._last_turn_context is not None
            and _is_implicit_results_followup(ctx.clean_input)
        ):
            needs_context = True
        if (
            not needs_context
            and self._last_turn_context is not None
            and is_index_context_followup(ctx.clean_input, self._last_turn_context)
        ):
            needs_context = True
        if (
            not needs_context
            and should_run_llm_situation_assessment(ctx.clean_input, self._last_turn_context)
        ):
            needs_context = True
        if not needs_context:
            return None
        previous_context = self._last_turn_context or self._conversation_fallback_context(
            mode=ctx.mode, source_label=ctx.source_label,
        )

        direct_plan = _keyword_intent(ctx.clean_input, data_mode="intraday")
        if direct_plan.get("intent") == "intraday_options_trade_plan" and direct_plan.get("plan"):
            plan_list = list(direct_plan["plan"])
            symbol = ""
            for tool_name, args in plan_list:
                if tool_name == "resolve_symbol":
                    symbol = str((args or {}).get("query") or "").upper()
                    break
            assessment = SituationAssessment(
                applies=True,
                decision="run_tool_plan",
                confidence="high",
                user_is_asking="Intraday options trade-plan request with stock, levels, and derivatives context.",
                context_found="Direct intraday options intent detected; bypassing contextual LLM routing.",
                resolved_entities=[symbol] if symbol else [],
                evidence_plan=[tool for tool, _ in plan_list],
                tool_plan=plan_list,
                plan=[
                    "Resolve the stock to its canonical NSE symbol.",
                    "Fetch live/intraday levels and setup evidence.",
                    "Fetch options/F&O evidence for PCR, max pain, and positioning where available.",
                    "Synthesize conditional CE/PE setups with triggers, stops, targets, no-trade zone, and missing evidence.",
                ],
                synthesis_intent="intraday_options_trade_plan",
            )
            ctx.trace.append({"step": "situation_assessment", "result": assessment.__dict__})
            if self._permission_policy.is_plan:
                return self._render_plan_preview(
                    assessment.tool_plan,
                    intent="situation_assessment",
                    clean_input=ctx.clean_input,
                    mode_suffix=ctx.mode_suffix,
                    trace=ctx.trace,
                )
            tool_results = _execute_plan(assessment.tool_plan)
            ctx.trace.extend(tool_results)
            answer_body = (
                render_assessment_block(assessment)
                + "\n\n"
                + _synthesize_and_narrate(
                    "intraday_options_trade_plan", ctx.clean_input, tool_results, self.backend,
                )
            )
            answer_body = _apply_response_guardrails(
                ctx.clean_input, "intraday_options_trade_plan", tool_results, answer_body,
            )
            answer_body = self._apply_agentic_next_action_block(
                answer_body, ctx.clean_input, "intraday_options_trade_plan", tool_results,
            )
            answer = answer_body + ctx.mode_suffix
            turn_ctx = build_turn_context(
                user_input=ctx.clean_input,
                intent="intraday_options_trade_plan",
                mode=ctx.mode,
                source_label=ctx.source_label,
                tool_results=tool_results,
                answer=answer,
            )
            self._remember_interaction(
                ctx.clean_input, answer, tool_results, turn_context=turn_ctx,
            )
            return {
                "answer": answer,
                "trace": ctx.trace,
                "backend": self.backend_name,
                "intent": "intraday_options_trade_plan",
            }

        if (
            entity_assessment.applies
            and entity_assessment.decision == "route_with_entity_topic"
        ):
            ctx.trace.append({
                "step": "situation_assessment",
                "result": {
                    "applies": True,
                    "decision": "route_with_entity_topic",
                    "confidence": entity_assessment.confidence,
                    "user_is_asking": entity_assessment.user_is_asking,
                    "context_found": "Direct entity/topic command delegated by situation assessment.",
                    "resolved_entities": [entity_assessment.canonical_symbol],
                },
            })
            return self._execute_entity_topic_assessment(ctx, entity_assessment)
        if (
            entity_assessment.applies
            and entity_assessment.decision == "ask_clarification"
        ):
            assessment = SituationAssessment(
                applies=True,
                decision="ask_clarification",
                confidence=entity_assessment.confidence,
                user_is_asking=entity_assessment.user_is_asking,
                context_found="Direct entity/topic command is missing a stock or company.",
                clarification_question="Which NSE symbol or company should I use?",
                plan=entity_assessment.plan,
            )
            ctx.trace.append({"step": "situation_assessment", "result": assessment.__dict__})
            fallback_context = previous_context or TurnContext(
                user_input="", intent="unknown", mode=ctx.mode,
                tools=[], source_label=ctx.source_label,
            )
            answer = render_context_answer(ctx.clean_input, assessment, fallback_context)
            self._pending_clarification = assessment
            self._remember_interaction(ctx.clean_input, answer, [])
            return {
                "answer": answer,
                "trace": ctx.trace,
                "backend": self.backend_name,
                "intent": "situation_assessment",
            }

        llm_assessment = None
        if should_run_llm_situation_assessment(ctx.clean_input, previous_context):
            llm_assessment = classify_llm_situation_assessment(
                ctx.clean_input,
                previous_context,
                self.backend,
                data_mode=ctx.mode,
                market_status={
                    "status": getattr(ctx.market_status, "compact_label", ""),
                    "clock": getattr(ctx.market_status, "clock_label", ""),
                },
            )
            ctx.trace.append({
                "step": "llm_situation_assessment",
                "result": {
                    "used": llm_assessment is not None,
                    "decision": getattr(llm_assessment, "decision", ""),
                    "confidence": getattr(llm_assessment, "confidence", ""),
                },
            })
        assessment = llm_assessment or assess_followup(ctx.clean_input, previous_context)
        ctx.trace.append({"step": "situation_assessment", "result": assessment.__dict__})

        if assessment.applies and assessment.decision in {"answer_from_context", "ask_clarification"}:
            previous_context = previous_context or TurnContext(
                user_input="", intent="unknown", mode=ctx.mode,
                tools=[], source_label=ctx.source_label,
            )
            # AA-CC-2: in dontAsk / bypassPermissions modes, auto-dispatch
            # the default-labelled option's bound_action instead of asking.
            if (
                assessment.decision == "ask_clarification"
                and assessment.clarification_questions
                and not self._permission_policy.should_ask_clarification()
            ):
                auto = self._auto_dispatch_default_clarification(
                    assessment, ctx, previous_context,
                )
                if auto is not None:
                    return auto
            answer = render_context_answer(ctx.clean_input, assessment, previous_context)
            if assessment.decision == "ask_clarification" and assessment.clarification_questions:
                self._pending_clarification = assessment
            self._remember_interaction(ctx.clean_input, answer, [])
            return {
                "answer": answer,
                "trace": ctx.trace,
                "backend": self.backend_name,
                "intent": "situation_assessment",
            }

        if assessment.applies and assessment.decision == "run_tool_plan":
            if self._permission_policy.is_plan:
                return self._render_plan_preview(
                    assessment.tool_plan,
                    intent="situation_assessment",
                    clean_input=ctx.clean_input,
                    mode_suffix=ctx.mode_suffix,
                    trace=ctx.trace,
                )
            tool_results = _execute_plan(assessment.tool_plan)
            ctx.trace.extend(tool_results)
            # PG-SYNTH-INTENT 2026-06-17: Derive synthesis_intent from the
            # actual tool plan first (authoritative), then fall back to LLM's
            # assessment. This prevents validation failures when the LLM returns
            # a default/example intent like "stock_brief" but the plan actually
            # ran different tools (e.g. get_latest_results -> stock_results).
            synthesis_intent = (
                _synthesis_intent_from_plan(assessment.tool_plan, query=ctx.clean_input)
                or getattr(assessment, "synthesis_intent", "")
                or "contextual_tool_plan"
            )
            answer_body = (
                render_assessment_block(assessment)
                + "\n\n"
                + _synthesize_and_narrate(synthesis_intent, ctx.clean_input, tool_results, self.backend)
            )
            # Pass "contextual_tool_plan" so _validate_required_tools waives
            # resolve_symbol — the symbol was already bound from prior-turn context.
            answer_body = _apply_response_guardrails(
                ctx.clean_input, "contextual_tool_plan", tool_results, answer_body,
            )
            answer_body = self._apply_agentic_next_action_block(
                answer_body, ctx.clean_input, synthesis_intent, tool_results,
            )
            answer = answer_body + ctx.mode_suffix
            turn_context = build_turn_context(
                user_input=ctx.clean_input,
                intent="contextual_tool_plan",
                mode=ctx.mode,
                source_label=ctx.source_label,
                tool_results=tool_results,
                answer=answer,
            )
            self._remember_interaction(ctx.clean_input, answer, tool_results, turn_context=turn_context)
            return {
                "answer": answer,
                "trace": ctx.trace,
                "backend": self.backend_name,
                "intent": "contextual_tool_plan",
            }
        return None

    def _stage_skill_store(self, ctx: _PipelineCtx) -> dict | None:
        """Run validated Skill Store workflows after deterministic stages decline."""
        try:
            if not _skill_store_runtime_enabled():
                return None
            deterministic_plan = _keyword_intent(ctx.clean_input, data_mode=ctx.mode)
            deterministic_intent, deterministic_confidence = _skill_store_deterministic_signal(deterministic_plan)
            if self._skill_store_embedding_provider is None:
                try:
                    self._skill_store_embedding_provider = get_embedding_provider()
                except Exception as exc:
                    ctx.trace.append({"step": "skill_store_embedding_provider", "error": str(exc)})
                    self._skill_store_embedding_provider = None

            assessment = _stage_skill_store_assessment(
                ctx.clean_input,
                repo=self._skill_store_repository,
                embedding_provider=self._skill_store_embedding_provider,
                deterministic_intent=deterministic_intent,
                deterministic_confidence=deterministic_confidence,
                plan_mode=self._permission_policy.is_plan,
            )
            if assessment is None:
                return None
            ctx.trace.append({"step": "skill_store_assessment", "result": assessment.to_dict()})

            if assessment.decision == "ask_clarification":
                answer = (
                    "▶ SKILL STORE NEEDS INPUT\n"
                    f"  {assessment.clarification_question}"
                    f"{ctx.mode_suffix}"
                )
                self._pending_skill_store_assessment = {
                    "assessment": assessment,
                    "original_input": ctx.clean_input,
                }
                self._remember_interaction(ctx.clean_input, answer, [])
                return {
                    "answer": answer,
                    "trace": ctx.trace,
                    "backend": self.backend_name,
                    "intent": "skill_store_clarification",
                }
            if assessment.decision not in {"select", "merge"}:
                return None
            if self._permission_policy.is_plan:
                answer = (
                    "▶ SKILL STORE PLAN\n"
                    + "\n".join(f"  {idx}. {item}" for idx, item in enumerate(assessment.plan_preview or (), start=1))
                    + ctx.mode_suffix
                )
                self._remember_interaction(ctx.clean_input, answer, [])
                return {
                    "answer": answer,
                    "trace": ctx.trace,
                    "backend": self.backend_name,
                    "intent": "skill_store_plan",
                }

            execution_plan = build_skill_execution_plan(
                _skill_store_review_decision(assessment),
                repository=self._skill_store_repository,
                params={},
                available_tools={name.lower() for name in TOOL_REGISTRY.keys()},
            )
            execution = execute_skill_plan(
                execution_plan,
                repository=self._skill_store_repository,
                call_tool_fn=call_tool,
                available_tools={name.lower() for name in TOOL_REGISTRY.keys()},
                output_contract=_skill_store_output_contract(assessment),
                retrieval_id=(assessment.trace or {}).get("retrieval_id"),
            )
            execution_trace = {
                "tool": "skill_store.execute",
                "args": {"skill_ids": list(execution_plan.skill_ids)},
                "result": execution.to_dict(),
            }
            ctx.trace.append(execution_trace)
            if not execution.passed:
                ctx.trace.append({
                    "step": "skill_store_failed_open",
                    "reason": "execution_failed",
                    "errors": list(execution.errors),
                })
                return None
            answer_body = _render_skill_store_execution_answer(assessment, execution)
            try:
                from terminal.renderers import build_narrative, attach_narrative

                narrative = build_narrative(
                    "skill_store",
                    ctx.clean_input,
                    [execution_trace],
                    answer_body,
                    self.backend,
                )
                answer_body = attach_narrative(answer_body, narrative)
            except Exception:
                logger.debug("skill store final narration failed — structured answer preserved", exc_info=True)
            answer_body = self._apply_agentic_next_action_block(
                answer_body, ctx.clean_input, "skill_store", [execution_trace],
            )
            answer = answer_body + ctx.mode_suffix
            turn_context = build_turn_context(
                user_input=ctx.clean_input,
                intent="skill_store",
                mode=ctx.mode,
                source_label=ctx.source_label,
                tool_results=[execution_trace],
                answer=answer,
            )
            self._remember_interaction(ctx.clean_input, answer, [execution_trace], turn_context=turn_context)
            return {
                "answer": answer,
                "trace": ctx.trace,
                "backend": self.backend_name,
                "intent": "skill_store",
            }
        except Exception as exc:
            ctx.trace.append({"step": "skill_store_assessment", "error": str(exc)})
            logger.debug("skill store workflow failed open", exc_info=True)
            return None

    def _stage_semantic_intent(self, ctx: _PipelineCtx) -> dict | None:
        """Use the LLM as a constrained intent classifier for open-ended asks."""
        if any(item.get("step") == "skill_store_failed_open" for item in ctx.trace if isinstance(item, dict)):
            return None
        decision = classify_semantic_intent(
            ctx.clean_input,
            self.backend,
            data_mode=ctx.mode,
        )
        if decision is None:
            return None
        intent_plan = {
            "intent": decision.intent,
            "plan": [(tool, args) for tool, args in decision.plan],
        }
        ctx.trace.append({"step": "semantic_intent", "result": decision.to_trace()})

        if decision.intent in _INTENT_SOURCE_LABEL_OVERRIDES:
            ctx.source_label = _INTENT_SOURCE_LABEL_OVERRIDES[decision.intent]
            ctx.mode_suffix = (
                f"\n\n_Mode: {ctx.mode.title()} | Sources: {ctx.source_label} | "
                f"Market: {ctx.market_status.compact_label} | "
                f"Clock: {ctx.market_status.clock_label}_"
            )

        if self._permission_policy.is_plan:
            return self._render_plan_preview(
                intent_plan["plan"],
                intent=decision.intent,
                clean_input=ctx.clean_input,
                mode_suffix=ctx.mode_suffix,
                trace=ctx.trace,
            )

        tool_results = _execute_plan(intent_plan["plan"])
        ctx.trace.extend(tool_results)
        answer_body = _synthesize_and_narrate(
            decision.intent,
            ctx.clean_input,
            tool_results,
            self.backend,
        )
        answer_body = _apply_response_guardrails(
            ctx.clean_input,
            decision.intent,
            tool_results,
            answer_body,
        )
        answer_body = self._apply_agentic_next_action_block(
            answer_body, ctx.clean_input, decision.intent, tool_results,
        )
        answer = self._with_readiness_metadata(answer_body + ctx.mode_suffix, ctx.mode)
        turn_context = build_turn_context(
            user_input=ctx.clean_input,
            intent=decision.intent,
            mode=ctx.mode,
            source_label=ctx.source_label,
            tool_results=tool_results,
            answer=answer,
        )
        self._remember_interaction(ctx.clean_input, answer, tool_results, turn_context=turn_context)
        return {
            "answer": answer,
            "trace": ctx.trace,
            "backend": self.backend_name,
            "intent": decision.intent,
        }

    def _stage_keyword_and_llm(self, ctx: _PipelineCtx) -> dict:
        """Keyword intent dispatch, LLM path with hallucination guard, and keyword fallback."""
        intent_plan = _keyword_intent(ctx.clean_input, data_mode=ctx.mode)
        _intent = intent_plan.get("intent") or ""

        # Apply static source-label overrides whose sources are known before tool execution.
        if _intent in _INTENT_SOURCE_LABEL_OVERRIDES:
            ctx.source_label = _INTENT_SOURCE_LABEL_OVERRIDES[_intent]
            _mode_label = _INTENT_MODE_LABEL_OVERRIDES.get(_intent, ctx.mode.title())
            ctx.mode_suffix = (
                f"\n\n_Mode: {_mode_label} | Sources: {ctx.source_label} | "
                f"Market: {ctx.market_status.compact_label} | "
                f"Clock: {ctx.market_status.clock_label}_"
            )
        elif _intent in {
            "youtube_video_analysis", "youtube_channel_latest",
            "youtube_video_transcription", "youtube_channel_transcription",
            "youtube_channels",
        }:
            ctx.source_label = "YouTube watch metadata + available captions + preset channel registry"
            if _intent in {"youtube_video_transcription", "youtube_channel_transcription"}:
                ctx.source_label += " + explicit audio speech-to-text when captions are unavailable"
            ctx.mode_suffix = (
                f"\n\n_Mode: Research | Sources: {ctx.source_label} | "
                f"Market: {ctx.market_status.compact_label} | "
                f"Clock: {ctx.market_status.clock_label}_"
            )

        if _intent in {
            "greeting", "startup_morning_briefing", "global_market_assessment",
            "market_situation_assessment", "placeholder_symbol_request",
            "document_link_help",
            "index_status",
            "strength_validation", "market_knowledge", "entity_topic_command", "company_identity",
            "symbol_quick_analysis", "stock_brief",
            "stock_results",
            "results_feed", "forthcoming_results",
            "stock_comparison", "portfolio_review", "portfolio_forensic_review",
            "event_calendar",
            "fno_overview", "market_dashboard", "screener",
            "market_swing_candidates",
            "visual_scan",
            "long_term_growth_research",
            "market_overview", "intraday_index_scan", "intraday_screener",
            "intraday_market_recap", "intraday_setup", "intraday_levels",
            "intraday_options_trade_plan",
            "data_health", "intraday_health",
            "youtube_video_analysis", "youtube_channel_latest",
            "youtube_video_transcription", "youtube_channel_transcription",
            "youtube_channels",
        }:
            ctx.trace.append({"step": "intent", "result": intent_plan})
            if self._permission_policy.is_plan:
                return self._render_plan_preview(
                    intent_plan["plan"],
                    intent=intent_plan.get("intent") or _intent or "intent_plan",
                    clean_input=ctx.clean_input,
                    mode_suffix=ctx.mode_suffix,
                    trace=ctx.trace,
                )
            tool_results = _execute_plan(intent_plan["plan"])
            ctx.trace.extend(tool_results)
            if ctx.mode == "intraday":
                ctx.source_label = _intraday_source_label(
                    _intent, tool_results, ctx.mode_sources["intraday"],
                )
                ctx.mode_suffix = (
                    f"\n\n_Mode: Intraday | Sources: {ctx.source_label} | "
                    f"Market: {ctx.market_status.compact_label} | "
                    f"Clock: {ctx.market_status.clock_label}_"
                )
            answer_body = _synthesize_and_narrate(
                _intent, ctx.clean_input, tool_results, self.backend,
                intent_plan.get("assessment_plan"),
            )
            answer_body = _apply_response_guardrails(ctx.clean_input, _intent, tool_results, answer_body)
            answer_body = self._apply_agentic_next_action_block(
                answer_body, ctx.clean_input, _intent, tool_results,
            )
            answer = self._with_readiness_metadata(answer_body + ctx.mode_suffix, ctx.mode)
            turn_context = build_turn_context(
                user_input=ctx.clean_input,
                intent=_intent,
                mode=ctx.mode,
                source_label=ctx.source_label,
                tool_results=tool_results,
                answer=answer,
            )
            self._remember_interaction(ctx.clean_input, answer, tool_results, turn_context=turn_context)
            # Extract compare_stocks result for the Rich comparison table renderer
            _comp = next(
                (t["result"] for t in tool_results
                 if t["tool"] == "compare_stocks" and isinstance(t.get("result"), dict)
                 and t["result"].get("stock_details")),
                None,
            )
            return {"answer": answer, "trace": ctx.trace, "backend": self.backend_name,
                    "intent": _intent, "comparison": _comp}

        # ── LLM path ──────────────────────────────────────────────────────
        if self.backend is not None:
            try:
                from .situation_assessment import classify_grounded_intent as _cgi
                _grounded_tag = _cgi(ctx.clean_input)
            except Exception:
                logger.debug(
                    "classify_grounded_intent failed — hallucination guard disabled for this turn",
                    exc_info=True,
                )
                _grounded_tag = ""
            _claimed = (intent_plan.get("intent") or "") in _GROUNDED_SCAN_INTENTS
            if _grounded_tag and not _claimed:
                ctx.trace.append({
                    "step": "hallucination_guard_pre_llm",
                    "reason": "grounded ask with no deterministic handler",
                    "grounded_intent": _grounded_tag,
                    "intent_plan": intent_plan.get("intent"),
                })
                answer = (
                    f"_No grounded results available for `{_grounded_tag}` request._\n\n"
                    "This needs a real scan against live/DB data — I won't "
                    "fabricate a list. Please specify the universe "
                    "(e.g. `NIFTY 50`, `NIFTY 500`, `F&O`) or run a deterministic "
                    "command like `/screen highrs` or `/scan NIFTY 500`.\n\n"
                    "━━━ Not investment advice. For research and learning only. ━━━"
                ) + ctx.mode_suffix
                self._remember_interaction(ctx.clean_input, answer, [], include_in_history=False)
                return {
                    "answer": answer,
                    "trace": ctx.trace,
                    "backend": self.backend_name,
                    "intent": "hallucination_guard",
                }

            result = self._llm_query(ctx.clean_input, ctx.show_trace, ctx.mode_context)
            if not result.get("has_source_trail", False):
                result["answer"] = result.get("answer", "") + ctx.mode_suffix
            result["answer"] += _cost_trail_block(
                result.get("usage") or {}, result.get("trace") or []
            )
            result["answer"] = self._with_readiness_metadata(result.get("answer", ""), ctx.mode)
            return result

        # ── Keyword fallback (no LLM backend) ─────────────────────────────
        ctx.trace.append({"step": "intent", "result": intent_plan})
        if self._permission_policy.is_plan:
            return self._render_plan_preview(
                intent_plan["plan"],
                intent=intent_plan.get("intent") or "keyword_fallback",
                clean_input=ctx.clean_input,
                mode_suffix=ctx.mode_suffix,
                trace=ctx.trace,
            )
        tool_results = _execute_plan(intent_plan["plan"])
        ctx.trace.extend(tool_results)
        if ctx.mode == "intraday":
            ctx.source_label = _intraday_source_label(
                intent_plan["intent"], tool_results, ctx.mode_sources["intraday"],
            )
            ctx.mode_suffix = (
                f"\n\n_Mode: Intraday | Sources: {ctx.source_label} | "
                f"Market: {ctx.market_status.compact_label} | "
                f"Clock: {ctx.market_status.clock_label}_"
            )
        answer_body = _synthesize_and_narrate(
            intent_plan["intent"], ctx.clean_input, tool_results, self.backend,
            intent_plan.get("assessment_plan"),
        )
        answer_body = _apply_response_guardrails(
            ctx.clean_input, intent_plan["intent"], tool_results, answer_body,
        )
        answer_body = self._apply_agentic_next_action_block(
            answer_body, ctx.clean_input, intent_plan["intent"], tool_results,
        )
        answer = answer_body + ctx.mode_suffix
        answer = self._quality_check(
            ctx.raw_input, intent_plan["intent"], tool_results, answer, ctx.mode_suffix,
        )
        answer = self._with_readiness_metadata(answer, ctx.mode)
        turn_context = build_turn_context(
            user_input=ctx.clean_input,
            intent=intent_plan["intent"],
            mode=ctx.mode,
            source_label=ctx.source_label,
            tool_results=tool_results,
            answer=answer,
        )
        self._remember_interaction(ctx.clean_input, answer, tool_results, turn_context=turn_context)
        return {
            "answer": answer,
            "trace": ctx.trace,
            "backend": self.backend_name,
            "intent": intent_plan["intent"],
        }

    def _query_single(
        self, user_input: str, show_trace: bool = False, entity_assessment=None
    ) -> dict:
        """Process a single user query through the named pipeline stages.

        Supports optional prefixes:
          /historical <query>  — force EOD / CSV mode
          /intraday <query>    — force live API mode
        Auto-detects intraday intent from keywords if no prefix given.

        Pipeline (AA-AR-2):
          1. _stage_clarification_binding — match reply to pending structured clarification
          2. _stage_unified_router        — UnifiedRouter owns compound/entity/market routes
          3. _stage_entity_topic          — legacy fallback for deterministic entity-topic resolution
          4. _stage_situation_assessment  — contextual follow-up + entity-topic orchestration
          5. _stage_skill_store           — validated skill retrieval/execution for open-ended asks
          6. _stage_semantic_intent       — LLM intent classification with fixed grounded plans
          7. _stage_keyword_and_llm       — keyword intent dispatch → LLM path → fallback
        Each stage returns a result dict or None to fall through to the next stage.
        """
        ctx = self._build_pipeline_ctx(user_input, show_trace)
        return (
            self._stage_clarification_binding(ctx)
            or self._stage_compressed_context_synthesis(ctx)
            or self._stage_agentic_bound_action(ctx)
            or self._stage_unified_router(ctx)
            or self._stage_entity_topic(ctx, entity_assessment)
            or self._stage_situation_assessment(ctx)
            or self._stage_skill_store(ctx)
            or self._stage_semantic_intent(ctx)
            or self._stage_keyword_and_llm(ctx)
        )

    def _stage_compressed_context_synthesis(self, ctx: _PipelineCtx) -> dict | None:
        """Handle synthesis queries over compressed context with NO tool calls.

        When the user asks a synthesis question ("which has the best RSI",
        "compare all stocks", "rank them") AND we have compressed context with
        key_findings, route directly to an LLM call with tools=None. This
        forces the LLM to answer from the compressed data rather than calling
        tools that would only fetch partial fresh data.
        """
        if self._compressed_context is None:
            return None
        if not self._compressed_context.key_findings:
            return None
        if not _is_contextual_synthesis_query(ctx.clean_input):
            return None

        ctx.trace.append({
            "step": "compressed_context_synthesis",
            "symbols": self._compressed_context.symbols_analyzed,
            "findings_count": len(self._compressed_context.key_findings),
        })

        # Build system prompt with compressed context
        system_content = (
            f"{ctx.mode_context}\n\n{SYSTEM_PROMPT}\n\n"
            + self._compressed_context.as_system_block()
        )

        # Strip the [CONTEXT: ...] suffix from clean_input for cleaner prompt
        user_msg = ctx.clean_input
        if "[CONTEXT: prior stocks analysed" in user_msg:
            user_msg = user_msg.split("[CONTEXT:")[0].strip()

        messages = [
            {"role": "system", "content": system_content},
            *self._trim_history(),
            {"role": "user", "content": user_msg},
        ]

        # Call LLM with NO tools — force synthesis from context
        resp = self.backend.chat(messages, tools=None)
        answer = resp.get("content") or ""

        if "research and learning only" not in answer[-400:]:
            answer += "\n\n━━━ Not investment advice. For research and learning only. ━━━"

        answer = self._with_readiness_metadata(answer + ctx.mode_suffix, ctx.mode)

        turn_context = build_turn_context(
            user_input=ctx.clean_input,
            intent="compressed_context_synthesis",
            mode=ctx.mode,
            source_label=ctx.source_label,
            tool_results=[],
            answer=answer,
        )
        self._remember_interaction(ctx.clean_input, answer, [], turn_context=turn_context)

        return {
            "answer": answer,
            "trace": ctx.trace,
            "backend": self.backend_name,
            "intent": "compressed_context_synthesis",
            "usage": resp.get("usage") or {},
        }

    def _llm_query(self, user_input: str, show_trace: bool,
                   mode_context: str = "") -> dict:
        """Full LLM-powered agentic query loop with rolling conversation history."""
        system_content = (f"{mode_context}\n\n{SYSTEM_PROMPT}" if mode_context
                          else SYSTEM_PROMPT)

        # Inject compressed prior-context block when available so the LLM
        # knows about symbols, findings and verdicts from earlier turns even
        # after those turns have been compressed out of the active window.
        compressed_context = getattr(self, "_compressed_context", None)
        if compressed_context is not None:
            system_content = (
                system_content
                + "\n\n"
                + compressed_context.as_system_block()
            )

        # Build messages: system + trimmed history + current user turn
        prior = self._trim_history()
        messages: list[dict] = [
            {"role": "system", "content": system_content},
            *prior,
            {"role": "user",   "content": user_input},
        ]
        tool_results: list[dict] = []
        max_rounds = 10
        _usage: dict = {
            "input_tokens": 0, "output_tokens": 0,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
        }

        _first_round = True
        for round_n in range(max_rounds):
            resp = self.backend.chat(messages, tools=self._tool_schemas_for_query(self._tool_selection_text(user_input)))
            _accumulate_usage(_usage, resp.get("usage") or {})

            if resp["tool_calls"]:
                # ── Show LLM planning on first round ─────────────────────────
                if _first_round and resp["tool_calls"]:
                    _first_round = False
                    try:
                        import logging as _log
                        _log.getLogger(__name__).debug(
                            "LLM first-round tools: %s",
                            [tc.get("function", {}).get("name") for tc in resp["tool_calls"]],
                        )
                        # Emit planning line visible in the terminal
                        # (uses the same import pattern as the rest of the file)
                        _tool_names = [
                            tc.get("function", {}).get("name", "?")
                            for tc in resp["tool_calls"]
                        ]
                        _plan_line = "  → [dim]LLM plan:[/dim] " + " → ".join(
                            f"[cyan]{n}[/cyan]" for n in _tool_names
                        )
                        # Emit to stderr so it appears before the spinner without
                        # disrupting Rich's console state in the main thread.
                        import sys as _sys
                        print(_plan_line.replace("[dim]","").replace("[/dim]","")
                              .replace("[cyan]","").replace("[/cyan]",""),
                              file=_sys.stderr, flush=True)
                    except Exception:
                        pass

                # Execute tool calls — concurrently when all are pure-read, sequentially otherwise.
                asst_msg = self.backend.format_tool_calls_in_message(resp["tool_calls"])
                messages.append(asst_msg)

                dispatched = _parallel_tool_dispatch(resp["tool_calls"], call_tool)
                for name, args, result, call_id in dispatched:
                    tool_results.append({"tool": name, "args": args, "result": result})
                    messages.append(self.backend.tool_result_message(call_id, result))
            else:
                # Final text response
                answer = resp["content"]
                supplemental_plan = _missing_fundamental_chain_plan(tool_results, user_input)
                if supplemental_plan:
                    supplemental_results = _execute_plan(supplemental_plan)
                    tool_results.extend(supplemental_results)
                    answer = _synthesize_and_narrate("stock_brief", user_input, tool_results, self.backend)
                # Only append disclaimer if LLM didn't include it (check last 400 chars)
                if "research and learning only" not in answer[-400:]:
                    answer += "\n\n━━━ Not investment advice. For research and learning only. ━━━"
                compressed_context = getattr(self, "_compressed_context", None)
                compressed_syms = (
                    compressed_context.symbols_analyzed
                    if compressed_context is not None
                    else None
                )
                answer = _apply_response_guardrails(user_input, "llm_driven", tool_results, answer, compressed_syms)

                # ── Persist compact conversation and resolved entity state ──
                self._remember_interaction(user_input, answer, tool_results)

                # Extract news/catalyst results so they can be rendered with real URLs
                # Priority: comprehensive_stock_research → search_latest_catalysts → search_yahoo_finance
                _web_tools = ("comprehensive_stock_research", "search_latest_catalysts",
                              "search_yahoo_finance", "multi_source_web_search")
                catalysts = None
                for _wt in _web_tools:
                    _hit = next(
                        (t["result"] for t in tool_results
                         if t["tool"] == _wt and isinstance(t.get("result"), dict)),
                        None,
                    )
                    if _hit:
                        # Normalise into {"results": [...]} shape
                        items = (_hit.get("results") or _hit.get("items") or
                                 _hit.get("news_articles") or [])
                        if items:
                            catalysts = {"results": items}
                            break
                # Extract compare_stocks result for dedicated Rich table rendering
                comparison = next(
                    (t["result"] for t in tool_results
                     if t["tool"] == "compare_stocks" and isinstance(t.get("result"), dict)
                     and t["result"].get("stock_details")),
                    None,
                )
                # Signal whether the LLM already included a source-trail footer so
                # _query_single can skip appending mode_suffix without fragile text search.
                _has_trail = "_Mode:" in answer or "Mode: " in answer[-300:]
                return {
                    "answer":          answer,
                    "trace":           tool_results,
                    "backend":         self.backend_name,
                    "intent":          "llm_driven",
                    "catalysts":       catalysts,
                    "comparison":      comparison,
                    "turn":            self.turn_count,
                    "has_source_trail": _has_trail,
                    "usage":           _usage,
                }

        # If we exhausted rounds without a text response, synthesize from tool results
        answer = _synthesize_and_narrate("stock_brief", user_input, tool_results, self.backend)
        compressed_context = getattr(self, "_compressed_context", None)
        compressed_syms = (
            compressed_context.symbols_analyzed
            if compressed_context is not None
            else None
        )
        answer = _apply_response_guardrails(user_input, "llm_driven_fallback", tool_results, answer, compressed_syms)
        # Still save the turn so context is preserved
        self._remember_interaction(user_input, answer, tool_results)
        _has_trail = "_Mode:" in answer or "Mode: " in answer[-300:]
        return {"answer": answer, "trace": tool_results, "backend": self.backend_name,
                "intent": "llm_driven_fallback", "turn": self.turn_count,
                "has_source_trail": _has_trail, "usage": _usage}
