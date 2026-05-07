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

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load .env from project root (two levels up from terminal/)
load_dotenv(Path(__file__).parent.parent / ".env")

from .tools import call_tool, get_symbol_snapshot, openai_tool_schemas, resolve_symbol

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o")
OLLAMA_HOST    = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "granite4:latest")

SYSTEM_PROMPT = """\
You are Agent Adda, an expert NSE market research analyst and assistant.

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
• get_live_market_overview()          → Live index levels (Nifty 50/Bank/IT/Mid/Small) + A/D
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
                                        leaders), high_rs (RS ≥ 1.15 market leaders), turnaround
                                        (recovery setups), stage1_base (basing/coiling stocks),
                                        tight_range (VCP-like weekly consolidation), oversold_bounce
                                        (RSI < 40 dip in Stage 2 uptrend)
• get_index_snapshot(index_name)      → Index 10-day trend
• get_market_breadth()                → Advance/decline, RS distribution, stage breakdown
• get_global_market_assessment()      → Global risk regime, US/Asia/commodity/FX cues,
                                        India sector read-through, correlations vs Nifty
• compare_stocks(symbols, aspects)    → Side-by-side comparison of multiple stocks on BOTH
                                        technical (stage, RSI, RS, scores, signals) AND
                                        fundamental (P/E, P/B, ROE, ROCE, div yield) metrics

[Intraday screener tools — primary path uses SQLite intraday/live tables; legacy yfinance tools remain available]
• get_intraday_source_health()        → SQLite intraday table health and freshness
• get_intraday_bars(symbol, timeframe)→ Raw SQLite intraday OHLCV bars
• get_intraday_levels(symbol,         → Support, resistance, pivots, EMA levels from
    timeframe)                          SQLite intraday_ohlcv; no EOD/yfinance fallback
• compute_intraday_indicators(symbol) → RSI, MACD, Supertrend, EMA, ATR, volume ratio from SQLite bars
• explain_intraday_setup(symbol)      → Research-only setup label, evidence, levels, target zones
• run_intraday_screener(screen_type)  → Intraday screener (SQLite or yfinance fallback).
                                        Original: momentum/breakouts/vcp/supertrend/levels/all.
                                        NEW: opening_range_breakout (ORB — first 15-30min high/low
                                        break + volume), gap_and_go (gap continuation + MACD),
                                        macd_crossover (fresh MACD signal line cross only),
                                        rsi_divergence (RSI extreme + Bollinger reversion),
                                        bb_squeeze (Bollinger Band squeeze breakout),
                                        vwap_reclaim (short-EMA VWAP proxy reclaim or loss)
• get_intraday_analysis(symbol,       → Legacy yfinance analysis of one stock when SQLite tables are absent
    interval, strategies)               or explicitly requested; keep output research-only.
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
• get_options_strategy(symbol,      → Build specific strategy: legs, entry cost, risk/reward,
    strategy, expiry?)                breakevens, payoff curve. Strategies: long_call, long_put,
                                      bull_call_spread, bear_put_spread, long_straddle, long_strangle,
                                      iron_condor, covered_call, protective_put, calendar_spread
• get_strategy_recommendations      → Recommend top 3 strategies based on PCR/IV/DTE/max pain
    (symbol, expiry?)
• refresh_fno_eod_data()            → Download latest F&O EOD bhavcopy from NSE and store in DB
• get_fno_data_status()             → Check local F&O DB availability and dates

[Web research tools — use for deep research, always return REAL URLs]
• scrape_screener_in(symbol)          → screener.in: P/E, P/B, ROE, ROCE, pros/cons,
                                        quarterly results, annual P&L, shareholding trend,
                                        BSE filing PDF links, annual-report links, peer table.
                                        NOW INCLUDES: concalls[] list with direct PDF transcript
                                        URLs, recording links (YouTube/mp3), PPT links — all
                                        accessible without login. Always use for concalls first.
• search_yahoo_finance(symbol)        → Yahoo Finance: price stats + up to 6 news articles
• multi_source_web_search(symbol,     → DuckDuckGo site: searches across moneycontrol.com,
    company_name, extra_query)          screener.in, economictimes.com, nseindia.com, bseindia.com
                                        + concall/transcript search. All URLs are real.
• comprehensive_stock_research(symbol)→ All-in-one: screener.in + Yahoo Finance + multi-site
                                        news. Returns ratios, peers, filings, news, deep-links.
• search_latest_catalysts(symbol)     → DuckDuckGo general web search for recent news
• get_portfolio_exposure(sector?)     → Portfolio sector distribution and holdings
• find_portfolio_overlap(screener)    → Holdings that match a screener

━━━ TOOL SELECTION RULES ━━━
• "option chain / options data / OI for NIFTY/BANKNIFTY/<stock> / option chain analysis" → call get_option_chain(symbol)
• "PCR / put call ratio / put-call ratio" → call get_oi_analysis(symbol) — focus on pcr and signal
• "max pain / options max pain / expiry pin / where will it expire" → call get_oi_analysis(symbol) — focus on max_pain
• "OI buildup / open interest buildup / call writing / put writing / where is OI concentration" → call get_oi_analysis(symbol)
• "support from options / resistance from options / OI support resistance / key strikes" → call get_oi_analysis(symbol)
• "greeks / delta / theta / vega / gamma / IV / implied volatility" → call get_option_chain(symbol) — atm_greeks section
• "IV skew / volatility skew / put IV vs call IV" → call get_option_chain(symbol) — iv_skew section
• "futures price / futures basis / futures premium / futures discount / cost of carry" → call get_futures_analysis(symbol)
• "rollover / futures rollover / rollover percentage" → call get_futures_analysis(symbol)
• "build a strategy / options strategy / set up a <strategy name>" → call get_options_strategy(symbol, strategy)
• "what strategy should I use / recommend options strategy / best options play" → call get_strategy_recommendations(symbol)
• "long call / buy call / buy put / long put / straddle / strangle / bull spread / bear spread / iron condor" → call get_options_strategy(symbol, strategy=<mapped_key>)
• "F&O data / download bhavcopy / update options data / refresh F&O" → call refresh_fno_eod_data()
• "F&O data status / options DB / available expiries" → call get_fno_data_status()
• "intraday setup / technical target zones / invalidation / trading setup" → call explain_intraday_setup(symbol); if SQLite tables are missing/stale or symbol bars are absent, call get_intraday_analysis(symbol) and clearly label it as Yahoo Finance/EOD fallback context
• "intraday levels / support resistance / pivots / VWAP levels" → call get_intraday_levels(symbol); if SQLite levels are unavailable, call get_intraday_analysis(symbol) and clearly label fallback levels
• "intraday data health / live table health / SQLite intraday" → call get_intraday_source_health
• "breakout stocks / live breakouts / breakouts last N minutes / stocks breaking out now / volume breakouts" → call scan_intraday_market(index="NIFTY 500", interval="15m", strategies=["ema","volume","macd"], direction_filter="buy")
• "intraday screener / scan / best intraday stocks / momentum plays" → call run_intraday_screener(screen_type="momentum") [auto-falls-back to yfinance if SQLite unavailable]
• "intraday setup for [list of stocks] / check these intraday / scan my watchlist / small-cap intraday" → call scan_symbols_intraday(symbols=[...])
• "scan [index] intraday / all NIFTY 50 signals / bank nifty buy signals" → call scan_intraday_market(index=...)
• "MACD signal / MACD crossover / fresh MACD" → run_intraday_screener(screen_type="macd_crossover") OR compute_intraday_indicators
• "RSI divergence / RSI reversal / overbought reversal" → run_intraday_screener(screen_type="rsi_divergence")
• "opening range breakout / ORB / first 15 minutes / open range" → run_intraday_screener(screen_type="opening_range_breakout")
• "gap and go / gapping stocks / gap continuation / gap up stocks" → run_intraday_screener(screen_type="gap_and_go")
• "Bollinger squeeze / BB squeeze / volatility squeeze / low volatility breakout" → run_intraday_screener(screen_type="bb_squeeze")
• "VWAP reclaim / above VWAP / below VWAP / VWAP bounce" → run_intraday_screener(screen_type="vwap_reclaim")
• "chart / show chart / price chart / candlestick / live chart / technical chart" → call get_chart_summary(symbol, timeframe); if /chart command, also render ASCII chart inline
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
• "technical setup / indicators / signals" → call get_technical_setup + get_symbol_snapshot
• "market overview / breadth" → call get_live_market_overview + get_market_breadth
• "global market / overnight cues / US market / Asian market / crude / DXY / USDINR / global risk" → call get_global_market_assessment
• "screener / breakouts / stage 2 / buy signals" → call run_screener_query(screen_type="stage2")
• "near 52W high / momentum leaders / strong stocks" → run_screener_query(screen_type="momentum_52w")
• "top RS stocks / market leaders / high relative strength" → run_screener_query(screen_type="high_rs")
• "turnaround / recovery stocks / dip recovery / comeback stocks" → run_screener_query(screen_type="turnaround")
• "basing stocks / accumulation / stage 1 / consolidating" → run_screener_query(screen_type="stage1_base")
• "tight range / VCP EOD / volatility contraction EOD / coiling stocks" → run_screener_query(screen_type="tight_range")
• "oversold bounce / RSI dip / dip buy in uptrend / stage 2 dip" → run_screener_query(screen_type="oversold_bounce")
• "compare / vs / versus / rank / which is better / peer comparison" → call compare_stocks(symbols=[...], aspects=['both'])
• "technical only comparison" → compare_stocks with aspects=['technical']
• "fundamental comparison / ratios comparison" → compare_stocks with aspects=['fundamental']
• "fundamentals / ratios / P/E / ROE / ROCE / valuation / book value" → call scrape_screener_in
• "peers / peer comparison / sector peers" → call scrape_screener_in (has peer table)
• "concall / transcript / conference call / management commentary" → call scrape_screener_in first (has direct PDF transcript URLs, recording links); supplement with multi_source_web_search if no transcripts found
• "BSE filing / corporate announcement / results date / quarterly results" → call scrape_screener_in (has BSE PDF links)
• "annual report / annual financials" → call scrape_screener_in (has annual-report PDF links)
• "moneycontrol / screener.in / yahoo finance / NSE website" → call the specific tool for that site
• "news / catalysts / events / latest" → call search_latest_catalysts AND search_yahoo_finance
• "deep research / full analysis / comprehensive / everything about" → call comprehensive_stock_research


Before answering, THINK STEP BY STEP:
1. Identify what the user is asking (price? setup? sector? screen? news?).
2. Decide whether this needs LIVE data (current price, intraday moves) or EOD data (technicals, stage analysis).
3. Call the relevant tools — start with live quote for "now/today/current" queries.
4. Synthesise ALL returned data into a coherent, structured analysis.
5. Always reason about what the numbers mean: is RSI oversold/overbought? Is ADX showing trend strength? Is stage 2 breaking out or exhausted?

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
  1. <specific follow-up question>
  2. <specific follow-up question>
  3. <specific follow-up question>
  ```
  RULES FOR FOLLOW-UPS — they must be:
  • SPECIFIC: mention the exact stock/sector/number from your response (e.g. "RELIANCE RSI at 71 — is it still a buy?" NOT "What is the RSI?")
  • PROGRESSIVE: each question should dig deeper into something you already surfaced (e.g. if you mentioned INDUSINDBK had a Supertrend BUY, ask about its entry/target)
  • ACTIONABLE: a trader should be able to act on the answer (entry/exit decisions, risk management, sector rotation)
  • VARIED: cover 3 different angles — e.g. technical + fundamental + news, or stock + sector + macro
  • NATURAL: phrase them as a curious analyst would — not as a checklist

  BAD examples (too generic — never do this):
    "Tell me about another stock."
    "What is the market doing today?"
    "Can you explain RSI?"
  GOOD examples (specific to data returned):
    "RELIANCE is at RSI 71 near 52W high — what does the Supertrend say on 15m?"
    "HDFC Bank shows lower RS than ICICI — is there a rotation trade here?"
    "FII sold ₹3,621 Cr today — which sectors saw the biggest outflows?"

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
Keep 3 razor-sharp follow-up questions anchored to what was reported.

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
    def __init__(self):
        from openai import OpenAI
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model  = OPENAI_MODEL

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        resp = self.client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        return {
            "content":    msg.content or "",
            "tool_calls": [
                {"id": tc.id, "name": tc.function.name, "args": json.loads(tc.function.arguments)}
                for tc in (msg.tool_calls or [])
            ],
            "finish_reason": resp.choices[0].finish_reason,
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

    def __init__(self):
        import requests
        self.requests = requests
        self.host     = OLLAMA_HOST.rstrip("/")
        self.model    = OLLAMA_MODEL
        # Check connection
        self.requests.get(f"{self.host}/api/tags", timeout=3)

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        body: dict[str, Any] = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            body["tools"] = tools
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


def _detect_backend() -> _OpenAIBackend | _OllamaBackend | None:
    if OPENAI_API_KEY:
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

def _keyword_intent(query: str, data_mode: str = "historical") -> dict:
    """Detect intent and build a tool plan from keywords alone."""
    q = query.lower()

    # Global market assessment
    if _is_global_query(q):
        return {
            "intent": "global_market_assessment",
            "plan": [("get_global_market_assessment", {})],
        }

    words = re.findall(r"[A-Za-z][A-Za-z0-9\-&\.]+", query)
    skip  = {"show","me","the","latest","on","for","what","is","how","tell",
              "about","give","setup","stock","nse","india","market","today","brief",
              "intraday","levels","level","support","resistance","screener","scan",
              "deep","dive","analysis","technical","trade","trading"}
    candidates = [w for w in words if w.lower() not in skip and len(w) >= 2]

    # SQLite-backed intraday routing. No EOD/yfinance fallback in this path.
    if data_mode == "intraday":
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
            sym_q = candidates[0] if candidates else ""
            return {"intent": "intraday_levels", "plan": [
                ("resolve_symbol", {"query": sym_q}),
                ("get_intraday_levels", {"symbol": sym_q}),
                ("get_intraday_analysis", {"symbol": sym_q}),
            ]}
        if candidates:
            sym_q = candidates[0]
            return {"intent": "intraday_setup", "plan": [
                ("resolve_symbol", {"query": sym_q}),
                ("explain_intraday_setup", {"symbol": sym_q}),
                ("get_intraday_analysis", {"symbol": sym_q}),
            ]}

    # Index query
    index_words = ["nifty", "sensex", "bank nifty", "nifty it", "nifty 50"]
    if any(w in q for w in index_words):
        idx = "NIFTY BANK" if "bank" in q else ("NIFTY IT" if " it" in q else "NIFTY 50")
        return {"intent": "index_status", "plan": [("get_index_snapshot", {"index_name": idx})]}

    # Breadth / market overview
    breadth_words = ["breadth", "advance decline", "a/d", "market today", "market outlook",
                     "nifty direction", "overall market", "how is market", "market status"]
    if any(w in q for w in breadth_words):
        return {"intent": "market_overview", "plan": [
            ("get_market_breadth", {}),
            ("get_index_snapshot", {"index_name": "NIFTY 50"}),
        ]}

    # Screener queries
    if any(w in q for w in ["strong buy", "top buy", "buy signals", "best stocks"]):
        return {"intent": "screener", "plan": [("run_screener_query", {"screen_type": "strong_buy"})]}
    if any(w in q for w in ["stage 2", "stage2", "weinstein", "advancing stocks"]):
        return {"intent": "screener", "plan": [("run_screener_query", {"screen_type": "stage2"})]}
    if any(w in q for w in ["breakout", "breakouts", "52w high", "52 week high", "20d high"]):
        return {"intent": "screener", "plan": [("run_screener_query", {"screen_type": "breakouts"})]}
    if any(w in q for w in ["new entrant", "new stage 2", "recently upgraded"]):
        return {"intent": "screener", "plan": [("run_screener_query", {"screen_type": "new_entrants"})]}
    if any(w in q for w in ["supertrend", "super trend"]):
        return {"intent": "screener", "plan": [("run_screener_query", {"screen_type": "supertrend_buy"})]}

    # Data health
    if any(w in q for w in ["data health", "data fresh", "stale", "last update", "when was"]):
        return {"intent": "data_health", "plan": [("get_data_health", {})]}

    # Reports
    if any(w in q for w in ["report", "html", "generated", "latest report"]):
        return {"intent": "report_lookup", "plan": [("find_latest_report", {})]}

    # Sector queries
    sector_words = ["sector", "pharma", "it sector", "auto sector", "bank sector",
                    "metals", "fmcg", "real estate", "energy"]
    for sw in sector_words:
        if sw in q:
            sector = sw.replace(" sector", "").title()
            return {"intent": "sector_scan", "plan": [("get_sector_context", {"sector_or_symbol": sector})]}

    # Stock-specific query — extract likely symbol
    if candidates:
        sym_q = candidates[0]
        plan = [
            ("resolve_symbol",       {"query": sym_q}),
            ("get_symbol_snapshot",  {"symbol": sym_q.upper()}),
            ("get_technical_setup",  {"symbol": sym_q.upper()}),
            ("get_sector_context",   {"sector_or_symbol": sym_q.upper()}),
        ]
        if any(w in q for w in ["news", "catalyst", "recent", "latest news"]):
            plan.append(("search_latest_catalysts", {"symbol": sym_q.upper()}))
        return {"intent": "stock_brief", "plan": plan}

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
            # Patch subsequent args that reference the original fuzzy query
            for _, a in plan:
                for k, v in a.items():
                    if isinstance(v, str) and v.upper() == args["query"].upper():
                        a[k] = resolved_sym

        results.append({"tool": tool_name, "args": args, "result": result})

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Response synthesis (no-LLM path)
# ─────────────────────────────────────────────────────────────────────────────

def _synthesize_no_llm(intent: str, tool_results: list[dict]) -> str:
    """Build a structured text response from tool results without an LLM."""
    lines: list[str] = []

    def _get(name: str) -> dict | None:
        for tr in tool_results:
            if tr["tool"] == name:
                return tr["result"]
        return None

    snap = _get("get_symbol_snapshot")
    tech = _get("get_technical_setup")
    sec  = _get("get_sector_context")
    idx  = _get("get_index_snapshot")
    brd  = _get("get_market_breadth")
    scr  = _get("run_screener_query")
    cat  = _get("search_latest_catalysts")
    res  = _get("resolve_symbol")
    glob = _get("get_global_market_assessment")
    intra_setup = _get("explain_intraday_setup")
    intra_screen = _get("run_intraday_screener")
    intra_levels = _get("get_intraday_levels")
    intra_ind = _get("compute_intraday_indicators")
    intra_legacy = _get("get_intraday_analysis")

    sym = (snap or {}).get("symbol") or (tech or {}).get("symbol") or ""
    cname = (snap or {}).get("company_name") or sym

    if sym:
        lines.append(f"━━━ {cname} ({sym}) — Market Brief ━━━")
        snap_date = (snap or {}).get("snapshot_date", "N/A")
        lines.append(f"Data: EOD snapshot {snap_date}\n")

    # 1. Snapshot
    if snap and not snap.get("error"):
        lines.append("▶ SNAPSHOT")
        price = snap.get("price") or (tech or {}).get("price")
        chg1d = snap.get("change_1d_pct")
        if price:
            chg_str = f"  ({chg1d:+.2f}%)" if chg1d else ""
            lines.append(f"  Price:  ₹{price:,.2f}{chg_str}")
        lines.append(f"  Stage:  {snap.get('stage','—')}  (score: {snap.get('stage_score','—')})")
        lines.append(f"  Signal: {snap.get('trading_signal','—')}")
        rs = snap.get("rs_pct")
        lines.append(f"  RS:     {rs:+.0f}%" if rs is not None else "  RS:     —")
        lines.append(f"  Sector: {snap.get('sector','—')}")
        lines.append(f"  MCap:   {snap.get('market_cap_cat','—')}")
        if snap.get("narrative"):
            lines.append(f"  Note:   {snap['narrative'][:120]}")

    # 2. Technical Setup
    if tech and not tech.get("error"):
        lines.append("\n▶ TECHNICAL SETUP")
        lines.append(f"  RSI:        {tech.get('rsi','—')}")
        lines.append(f"  ADX:        {tech.get('adx','—')}  (>25 = trending)")
        lines.append(f"  MACD:       {tech.get('macd','—')}")
        lines.append(f"  Supertrend: {tech.get('supertrend','—')}")
        ma_flags = []
        if tech.get("above_sma20"):   ma_flags.append("▲ SMA20")
        if tech.get("above_sma50"):   ma_flags.append("▲ SMA50")
        if tech.get("above_sma200"):  ma_flags.append("▲ SMA200")
        lines.append(f"  MAs:        {' | '.join(ma_flags) or '— below key MAs'}")
        h52, l52, pct = tech.get("52w_high"), tech.get("52w_low"), tech.get("pct_from_52h")
        if h52:
            lines.append(f"  52W Range:  ₹{l52:,.0f} – ₹{h52:,.0f}  ({pct:+.1f}% from high)" if pct else "")
        vr = tech.get("vol_ratio")
        lines.append(f"  Volume:     {vr:.1f}x avg" if vr else "")

    # 3. Sector Context
    if sec and not sec.get("error"):
        lines.append("\n▶ SECTOR CONTEXT")
        lines.append(f"  Sector:         {sec.get('sector','—')}")
        lines.append(f"  Stocks in DB:   {sec.get('total_stocks','—')}")
        lines.append(f"  Stage 2 count:  {sec.get('stage2_count','—')}")
        lines.append(f"  Buy signals:    {sec.get('buy_signals','—')}")
        lines.append(f"  Avg RS:         {sec.get('avg_rs_pct','—'):+.1f}%" if sec.get('avg_rs_pct') is not None else "")
        lines.append(f"  Avg 1M chg:     {sec.get('avg_1m_pct','—'):+.2f}%" if sec.get('avg_1m_pct') is not None else "")
        top5 = sec.get("top5_by_score", [])
        if top5:
            lines.append("  Top peers:      " + ", ".join(s["symbol"] for s in top5[:5]))

    # 4. Index / breadth
    if idx and not idx.get("error"):
        lines.append("\n▶ INDEX")
        lines.append(f"  {idx.get('index')}: {idx.get('close'):,.2f}  ({idx.get('chg_pct'):+.2f}%)")
        t = idx.get("trend_10d", {})
        lines.append(f"  10d trend: {t.get('chg_pct',0):+.2f}%  ({t.get('up_days',0)}/{len(t.get('closes',[]))-1} up-days)")

    if brd and not brd.get("error"):
        lines.append("\n▶ MARKET BREADTH")
        lines.append(f"  Advances: {brd.get('advances')}  Declines: {brd.get('declines')}  "
                     f"A/D ratio: {brd.get('ad_ratio')}")
        lines.append(f"  Universe avg RS: {brd.get('avg_rs_pct',0):+.1f}%")
        sd = brd.get("stage_distribution", {})
        if sd:
            lines.append("  Stage dist: " + " | ".join(f"{k}: {v}" for k, v in sd.items()))

    # 4b. Global market assessment
    if glob and not glob.get("error"):
        lines.append("\n▶ GLOBAL MARKET ASSESSMENT")
        lines.append(f"  Risk regime: {glob.get('risk_regime', '—')}")
        lines.append(f"  As of:        {glob.get('as_of', '—')}")
        regions = glob.get("regions") or {}
        if regions:
            region_bits = []
            for name, data in regions.items():
                avg = data.get("avg_pct_change")
                avg_s = f"{avg:+.2f}%" if isinstance(avg, (int, float)) else "n/a"
                region_bits.append(f"{name}: {data.get('bias', '—')} ({avg_s})")
            lines.append("  Regions:      " + " | ".join(region_bits))
        moves = glob.get("moves") or {}
        if moves:
            key_moves = []
            for asset in ["S&P 500", "Nasdaq", "Hang Seng", "Nikkei 225", "Crude Oil", "DXY", "USDINR"]:
                if asset in moves:
                    m = moves[asset]
                    key_moves.append(f"{asset} {m.get('pct_change', 0):+.2f}%")
            if key_moves:
                lines.append("  Key moves:    " + " | ".join(key_moves))
        readthrough = glob.get("india_readthrough") or []
        if readthrough:
            lines.append("  India read-through:")
            for item in readthrough[:5]:
                lines.append(f"    - {item}")
        watch = glob.get("watch_items") or []
        if watch:
            lines.append("  Watch:")
            for item in watch[:4]:
                lines.append(f"    - {item}")
        corrs = glob.get("correlations") or []
        if corrs:
            lines.append("  Correlation context:")
            for c in corrs[:5]:
                lines.append(
                    f"    - {c.get('asset')}: 30d {c.get('corr_30d')} | "
                    f"60d {c.get('corr_60d')} | {c.get('alert', '—')}"
                )

    # 5. Screener results
    if scr:
        lines.append(f"\n▶ SCREENER: {scr.get('screen_type','').upper()}  ({scr.get('count',0)} results)")
        for s in (scr.get("results") or [])[:8]:
            rs_str = f"RS:{s['rs_pct']:+.0f}%" if s.get("rs_pct") is not None else ""
            lines.append(f"  {s['symbol']:<12}  ₹{s.get('price',0):>8,.0f}  "
                         f"{rs_str:<8}  {s.get('trading_signal','—')}")

    # 5b. SQLite intraday setup and screeners
    if intra_setup and not intra_setup.get("error"):
        lines.append("\n▶ INTRADAY SETUP")
        lines.append(f"  Symbol:      {intra_setup.get('symbol', '—')}")
        lines.append(f"  Timeframe:   {intra_setup.get('timeframe', '—')}")
        lines.append(f"  Setup label: {intra_setup.get('setup_label', '—')}")
        lines.append(f"  Score:       {intra_setup.get('score', '—')}")
        lines.append(f"  Price:       ₹{intra_setup.get('latest_close', '—')}")
        lines.append(f"  Freshness:   {intra_setup.get('latest_timestamp', '—')}")
        ind = intra_setup.get("indicators") or {}
        lines.append(
            f"  Indicators:  RSI {ind.get('rsi', '—')} | MACD hist {ind.get('macd_hist', '—')} | "
            f"Supertrend dir {ind.get('supertrend_dir', '—')}"
        )
        levels = intra_setup.get("levels") or {}
        lines.append(
            f"  Levels:      Support {(levels.get('supports') or ['—'])[0]} | "
            f"Resistance {(levels.get('resistances') or ['—'])[0]}"
        )
        lines.append(f"  Invalidation level: {intra_setup.get('invalidation_level', '—')}")
        lines.append(f"  Technical target zones: {intra_setup.get('technical_target_zones') or '—'}")
        lines.append("  Framing:     Research setup only; not a buy/sell recommendation.")

    if intra_levels and not intra_levels.get("error"):
        lines.append("\n▶ INTRADAY LEVELS")
        lines.append(f"  Symbol:      {intra_levels.get('symbol', '—')}")
        lines.append(f"  Timeframe:   {intra_levels.get('timeframe', '—')}")
        lines.append(f"  Price:       ₹{intra_levels.get('latest_close', '—')}")
        lines.append(f"  Supports:    {intra_levels.get('supports') or '—'}")
        lines.append(f"  Resistances: {intra_levels.get('resistances') or '—'}")
        lines.append(f"  Pivot:       {intra_levels.get('pivot', '—')}")

    if intra_ind and not intra_ind.get("error"):
        lines.append("\n▶ INTRADAY INDICATORS")
        ind = intra_ind.get("indicators") or {}
        lines.append(f"  Symbol:      {intra_ind.get('symbol', '—')}")
        lines.append(f"  Timeframe:   {intra_ind.get('timeframe', '—')}")
        lines.append(f"  Score:       {intra_ind.get('score', '—')}")
        lines.append(f"  RSI:         {ind.get('rsi', '—')}")
        lines.append(f"  MACD hist:   {ind.get('macd_hist', '—')}")
        lines.append(f"  Supertrend:  {ind.get('supertrend_dir', '—')}")

    if (
        intra_legacy
        and not intra_legacy.get("error")
        and (
            (intra_setup and intra_setup.get("error"))
            or (intra_levels and intra_levels.get("error"))
            or not (intra_setup or intra_levels or intra_ind)
        )
    ):
        sqlite_error = (
            (intra_setup or {}).get("error")
            or (intra_levels or {}).get("error")
            or "SQLite intraday source unavailable"
        )
        lines.append("\n▶ INTRADAY FALLBACK ANALYSIS")
        lines.append(f"  SQLite intraday source unavailable: {sqlite_error}")
        lines.append(
            f"  Fallback source: {intra_legacy.get('source') or intra_legacy.get('data_source') or 'legacy intraday engine'}"
        )
        lines.append(f"  Symbol:      {intra_legacy.get('symbol', '—')}")
        lines.append(f"  Interval:    {intra_legacy.get('interval', '—')}")
        lines.append(f"  Session:     {intra_legacy.get('session', '—')}")
        lines.append(f"  Price:       ₹{intra_legacy.get('close', '—')}")
        lines.append(f"  Bias:        {intra_legacy.get('bias', '—')}")
        if intra_legacy.get("candles") is not None:
            lines.append(f"  Candles:     {intra_legacy.get('candles')}")
        reason = intra_legacy.get("reason") or intra_legacy.get("note")
        if reason:
            lines.append(f"  Note:        {reason}")
        key_levels = intra_legacy.get("key_levels") or intra_legacy.get("approx_levels") or {}
        if key_levels:
            supports = key_levels.get("supports") or [key_levels.get("support_20d_low"), key_levels.get("prev_day_low")]
            resistances = key_levels.get("resistances") or [key_levels.get("resistance_20d_high"), key_levels.get("prev_day_high")]
            supports = [v for v in supports if v is not None]
            resistances = [v for v in resistances if v is not None]
            lines.append(f"  Supports:    {supports or '—'}")
            lines.append(f"  Resistances: {resistances or '—'}")
            lines.append(f"  Pivot:       {key_levels.get('pivot') or key_levels.get('prev_day_close') or '—'}")
        ind = intra_legacy.get("indicators") or {}
        if ind:
            lines.append(
                f"  Indicators:  RSI {ind.get('rsi', '—')} | MACD hist {ind.get('macd_hist', '—')} | "
                f"Supertrend dir {ind.get('supertrend_dir', '—')}"
            )
        buy_sigs = intra_legacy.get("buy_signals") or []
        sell_sigs = intra_legacy.get("sell_signals") or []
        watch = intra_legacy.get("watch_alerts") or []
        if buy_sigs or sell_sigs or watch:
            lines.append(
                f"  Signals:     {len(buy_sigs)} long research setups | "
                f"{len(sell_sigs)} short research setups | {len(watch)} watch alerts"
            )
            for sig in (buy_sigs + sell_sigs + watch)[:5]:
                bits = [str(sig.get("strategy", "setup"))]
                if sig.get("entry") is not None:
                    bits.append(f"entry {sig.get('entry')}")
                if sig.get("target") is not None:
                    bits.append(f"target {sig.get('target')}")
                if sig.get("stoploss") is not None:
                    bits.append(f"invalidation {sig.get('stoploss')}")
                lines.append("    - " + " | ".join(bits))
        lines.append("  Framing:     Research-only fallback analysis; not a buy/sell recommendation.")

    if intra_screen and not intra_screen.get("error"):
        lines.append(
            f"\n▶ INTRADAY SCREENER: {intra_screen.get('screen_type', '').upper()} "
            f"({intra_screen.get('count', 0)} results)"
        )
        for row in (intra_screen.get("results") or [])[:10]:
            lines.append(
                f"  {row.get('symbol','—'):<12} {row.get('setup_label','—'):<12} "
                f"score {row.get('score','—')} price ₹{row.get('price','—')} "
                f"S {row.get('support','—')} R {row.get('resistance','—')}"
            )
        lines.append("  Framing: Research-only setup labels; not buy/sell recommendations.")

    # 6. Catalysts
    if cat and cat.get("results"):
        lines.append("\n▶ LATEST CATALYSTS (web search results — use EXACT URLs below, never write 'Read more')")
        for r in cat["results"][:5]:
            title   = r.get("title", "")[:100]
            url     = r.get("url", "")
            snippet = r.get("snippet", "")[:120]
            lines.append(f"  TITLE:   {title}")
            if url:
                lines.append(f"  URL:     {url}")
            if snippet:
                lines.append(f"  SNIPPET: {snippet}")
            lines.append("")

    # 7. Risks / Watch
    risks: list[str] = []
    if tech:
        if tech.get("rsi", 50) > 75:  risks.append("RSI overbought (>75)")
        if not tech.get("above_sma50"): risks.append("Price below SMA50")
        if tech.get("adx", 0) < 20:  risks.append("ADX < 20 — weak trend")
    if snap:
        if snap.get("stage") not in ("STAGE_2", None) and snap.get("stage"):
            risks.append(f"Not in Stage 2 ({snap.get('stage')})")
    if risks:
        lines.append("\n▶ RISKS / WATCH")
        for r in risks:
            lines.append(f"  ⚠ {r}")

    # Source trail
    lines.append("\n▶ SOURCE TRAIL")
    for tr in tool_results:
        err = tr["result"].get("error", "")
        status = f"ERROR: {err}" if err else "ok"
        lines.append(f"  {tr['tool']}: {status}")

    lines.append("\n━━━ Not investment advice. For research and learning only. ━━━")
    return "\n".join(l for l in lines if l.strip() != "")


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


def _is_global_query(q: str) -> bool:
    return any(phrase in q for phrase in _GLOBAL_QUERY_PHRASES)


class Agent:
    """Agent Adda NLP Query Agent."""

    # Approx token budget for rolling history (chars ÷ 4 ≈ tokens).
    # At ~4 chars/token, 40_000 chars ≈ 10k tokens — safe headroom for most models.
    _HISTORY_CHAR_BUDGET = 40_000
    # Hard cap: never keep more than 20 turns (40 messages) regardless of size
    _HISTORY_MAX_TURNS   = 20

    def __init__(self):
        self.backend      = _detect_backend()
        self.tool_schemas = openai_tool_schemas()
        self.backend_name = (
            "OpenAI" if isinstance(self.backend, _OpenAIBackend) else
            "Ollama" if isinstance(self.backend, _OllamaBackend) else
            "Keyword (no LLM)"
        )
        # Rolling conversation history: list of {"role": ..., "content": ...}
        # Only user + assistant turns (no system, no tool messages).
        self._history: list[dict] = []

    @property
    def turn_count(self) -> int:
        """Number of completed user→assistant turns in current session."""
        return sum(1 for m in self._history if m["role"] == "user")

    def reset_history(self) -> None:
        """Clear conversation history — start a fresh session."""
        self._history = []

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

    def query(self, user_input: str, show_trace: bool = False) -> dict:
        """Process a user query. Returns {"answer": str, "trace": list, "backend": str}.

        Supports optional prefixes:
          /historical <query>  — force EOD / CSV mode
          /intraday <query>    — force live API mode
        Auto-detects intraday intent from keywords if no prefix given.
        """
        # ── Determine data mode ───────────────────────────────────────────────
        clean_input = user_input
        mode = "historical"
        if user_input.startswith("/historical "):
            mode        = "historical"
            clean_input = user_input[len("/historical "):].strip()
        elif user_input.startswith("/intraday "):
            mode        = "intraday"
            clean_input = user_input[len("/intraday "):].strip()
        else:
            words = set(re.split(r"\W+", user_input.lower()))
            if _is_global_query(user_input.lower()):
                mode = "global"
            elif words & _INTRADAY_KEYWORDS:
                mode = "intraday"

        mode_context = (
            f"Data mode: {mode}. "
            + (
                "Use get_global_market_assessment for global indices, commodities, FX, "
                "correlation context, and India read-through."
                if mode == "global"
                else (
               "Use get_intraday_source_health first for calculations, then SQLite-backed "
               "get_intraday_bars, compute_intraday_indicators, get_intraday_levels, "
               "explain_intraday_setup, and run_intraday_screener. If SQLite intraday "
               "tables are missing or stale for a single-stock deep dive, call "
               "get_intraday_analysis as an explicit Yahoo Finance/EOD fallback, label "
               "it clearly, and do not present fallback levels as SQLite/live-table data."
                    if mode == "intraday"
                    else "Use EOD CSV and DB snapshot tools for historical/technical analysis."
                )
            )
        )
        mode_sources = {
            "global": "cached global indices + correlations",
            "intraday": "SQLite intraday/live tables",
            "historical": "EOD CSV + DB snapshot",
        }
        mode_suffix = (
            f"\n\n_Mode: {mode.title()} | Sources: "
            f"{mode_sources.get(mode, 'EOD CSV + DB snapshot')}_"
        )

        trace: list[dict] = []

        # ── LLM path ──────────────────────────────────────────────────────────
        if self.backend is not None:
            result = self._llm_query(clean_input, show_trace, mode_context)
            # Only append mode suffix if the LLM didn't include a Source Trail
            if "Mode:" not in result.get("answer", "")[-600:]:
                result["answer"] = result.get("answer", "") + mode_suffix
            return result

        # ── Keyword fallback path ──────────────────────────────────────────────
        intent_plan = _keyword_intent(clean_input, data_mode=mode)
        trace.append({"step": "intent", "result": intent_plan})

        tool_results = _execute_plan(intent_plan["plan"])
        trace.extend(tool_results)

        answer = _synthesize_no_llm(intent_plan["intent"], tool_results) + mode_suffix
        return {"answer": answer, "trace": trace, "backend": self.backend_name,
                "intent": intent_plan["intent"]}

    def _llm_query(self, user_input: str, show_trace: bool,
                   mode_context: str = "") -> dict:
        """Full LLM-powered agentic query loop with rolling conversation history."""
        system_content = (f"{mode_context}\n\n{SYSTEM_PROMPT}" if mode_context
                          else SYSTEM_PROMPT)

        # Build messages: system + trimmed history + current user turn
        prior = self._trim_history()
        messages: list[dict] = [
            {"role": "system", "content": system_content},
            *prior,
            {"role": "user",   "content": user_input},
        ]
        tool_results: list[dict] = []
        max_rounds = 10

        for round_n in range(max_rounds):
            resp = self.backend.chat(messages, tools=self.tool_schemas)

            if resp["tool_calls"]:
                # Execute each tool call
                asst_msg = self.backend.format_tool_calls_in_message(resp["tool_calls"])
                messages.append(asst_msg)

                for tc in resp["tool_calls"]:
                    result = call_tool(tc["name"], tc["args"])
                    tool_results.append({"tool": tc["name"], "args": tc["args"], "result": result})
                    tool_msg = self.backend.tool_result_message(tc["id"], result)
                    messages.append(tool_msg)
            else:
                # Final text response
                answer = resp["content"]
                # Only append disclaimer if LLM didn't include it (check last 400 chars)
                if "research and learning only" not in answer[-400:]:
                    answer += "\n\n━━━ Not investment advice. For research and learning only. ━━━"

                # ── Persist this turn to conversation history ──────────────
                # Store only user + final assistant text (no tool messages — keeps history compact)
                self._history.append({"role": "user",      "content": user_input})
                self._history.append({"role": "assistant", "content": answer})

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
                return {
                    "answer":     answer,
                    "trace":      tool_results,
                    "backend":    self.backend_name,
                    "intent":     "llm_driven",
                    "catalysts":  catalysts,
                    "comparison": comparison,
                    "turn":       self.turn_count,
                }

        # If we exhausted rounds without a text response, synthesize from tool results
        answer = _synthesize_no_llm("stock_brief", tool_results)
        # Still save the turn so context is preserved
        self._history.append({"role": "user",      "content": user_input})
        self._history.append({"role": "assistant", "content": answer})
        return {"answer": answer, "trace": tool_results, "backend": self.backend_name,
                "intent": "llm_driven_fallback", "turn": self.turn_count}
