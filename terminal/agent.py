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
import shlex
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load .env from project root (two levels up from terminal/)
load_dotenv(Path(__file__).parent.parent / ".env")

from .tools import call_tool, get_symbol_snapshot, openai_tool_schemas, resolve_symbol
from .market_calendar import market_context_for_agent, market_session_status
from .data_readiness import append_readiness_metadata
from .entity_resolution import TECHNICAL_NON_SYMBOL_TERMS, validate_requested_symbols
from .evidence_gate import validate_required_tools_executed
from .situation_assessment import (
    TurnContext,
    assess_entity_topic_request,
    assess_followup,
    build_turn_context,
    needs_situation_assessment,
    render_assessment_block,
    render_context_answer,
)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o")
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
• get_market_breadth()                → Advance/decline, RS distribution, stage breakdown
• get_global_market_assessment()      → Global risk regime, US/Asia/commodity/FX cues,
                                        India sector read-through, correlations vs Nifty
• compare_stocks(symbols, aspects)    → Side-by-side comparison of multiple stocks on BOTH
                                        technical (stage, RSI, RS, scores, signals) AND
                                        fundamental (P/E, P/B, ROE, ROCE, div yield) metrics

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
        self.client = OpenAI(api_key=key, timeout=120.0)
        self.model  = model or os.getenv("OPENAI_MODEL", OPENAI_MODEL)

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

    def __init__(self, model: str | None = None, host: str | None = None):
        import requests
        self.requests = requests
        self.host     = (host or os.getenv("OLLAMA_HOST", OLLAMA_HOST)).rstrip("/")
        self.model    = model or os.getenv("OLLAMA_MODEL", OLLAMA_MODEL)
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
    m = re.search(r"\b(5|15|30)\s*(?:min|minute|minutes)\b", q)
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
        phrase = _symbol_phrase_after_preposition(raw_query)
        if phrase:
            try:
                resolved = resolve_symbol(phrase)
                canonical = resolved.get("symbol") if isinstance(resolved, dict) else None
                if canonical:
                    return canonical
            except Exception:
                pass
            return phrase
        phrase = _leading_company_phrase(raw_query)
        if phrase:
            try:
                resolved = resolve_symbol(phrase)
                canonical = resolved.get("symbol") if isinstance(resolved, dict) else None
                if canonical:
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
                    if canonical:
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
        "intraday", "setup", "technical", "technicals", "fundamental", "fundamentals",
        "analysis", "deep", "dive", "research", "forensic", "risk", "levels",
        "support", "resistance", "target", "targets", "today", "now", "live",
        "scan", "show", "tell", "give", "what", "is", "the", "of", "for",
    }
    words: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9&.-]*", raw_query):
        if token.lower() in stop_words:
            if words:
                break
            continue
        words.append(token)
        if len(words) >= 4:
            break
    return " ".join(words).strip() if len(words) >= 2 else ""


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


_REQUIRED_TOOLS_BY_INTENT: dict[str, tuple[str, ...]] = {
    "screener": ("run_screener_query",),
    "intraday_screener": ("run_intraday_screener",),
    "intraday_index_scan": ("scan_intraday_market",),
    "intraday_setup": ("explain_intraday_setup", "get_nse_intraday_snapshot"),
    "intraday_levels": ("get_intraday_levels", "get_nse_intraday_snapshot"),
    "fno_overview": ("get_fno_overview",),
    "stock_comparison": ("compare_stocks",),
    "strength_validation": ("validate_strength_watchlist",),
    "stock_brief": ("resolve_symbol", "get_symbol_snapshot"),
    "stock_results": (
        "resolve_symbol",
        "get_latest_results",
    ),
    "results_feed": ("get_latest_results_feed",),
    "forthcoming_results": ("get_forthcoming_results",),
}


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


def _explicit_requested_symbols(query: str) -> list[str]:
    """Return explicit ticker-looking symbols from user text without fuzzy substitution."""
    requested = validate_requested_symbols(query or "").get("requested_symbols", [])
    # The universe-backed validator deliberately filters non-listed tokens to
    # avoid instruction words becoming symbols in generated prompts. For final
    # evidence validation, retain explicit all-caps user tokens in stock-shaped
    # queries so a bad resolver cannot silently substitute another company.
    if not requested and re.search(
        r"\b(technical|setup|stock|analy[sz]e|result|results|earnings|screener|breakout)\b",
        query or "",
        re.I,
    ):
        requested = [
            token
            for token in re.findall(r"\b[A-Z][A-Z0-9&-]{1,12}\b", query or "")
            if token.upper() not in _SYMBOL_VALIDATION_SKIP
            and token.upper() not in TECHNICAL_NON_SYMBOL_TERMS
        ]
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
                if isinstance(resolved, dict) and resolved.get("symbol") and resolved.get("confidence") in {"exact", "near-match"}:
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
    return lines


def _required_tools_for_query(intent: str, query: str) -> tuple[str, ...]:
    required = list(_REQUIRED_TOOLS_BY_INTENT.get(intent) or ())
    if intent not in _DYNAMIC_EVIDENCE_REQUIRED_INTENTS:
        return tuple(dict.fromkeys(required))

    q = (query or "").lower()
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
    return tuple(dict.fromkeys(required))


def _validate_required_tools(query: str, intent: str, tool_results: list[dict]) -> str | None:
    required = _required_tools_for_query(intent, query)
    if not required:
        return None
    executed = {str(tr.get("tool")) for tr in tool_results or []}
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
            "get_latest_results",
        }
        required = tuple(t for t in required if t not in document_safe_skip)
        if not required:
            return None
    validation = validate_required_tools_executed(list(required), tool_results or [])
    missing = validation.get("missing_tools") or [tool for tool in required if tool not in executed]
    if not missing:
        return None
    lines = [
        "▶ REQUIRED TOOL VALIDATION FAILED",
        f"  Intent: {intent}",
        f"  Missing required tool(s): {', '.join(missing)}",
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
) -> str | None:
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
) -> str:
    required_failure = _validate_required_tools(query, intent, tool_results)
    if required_failure:
        return required_failure
    symbol_failure = _validate_symbol_grounding(query, intent, tool_results)
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
    market_terms = ("market", "nifty", "indices", "index", "breadth", "advance", "decline")
    status_terms = ("current", "status", "today", "now", "live", "how is")
    mover_terms = ("top gainer", "top gainers", "gainers", "losers", "movers", "top stocks", "top indices")
    flow_terms = ("fii", "dii", "institutional", "flows", "foreign investors")
    news_terms = ("news", "catalyst", "event", "headline")

    wants_market = any(term in q for term in market_terms)
    wants_status = any(term in q for term in status_terms)
    wants_movers = any(term in q for term in mover_terms)
    wants_breadth = "breadth" in q or "advance" in q or "decline" in q
    wants_flows = any(term in q for term in flow_terms)
    wants_news = any(term in q for term in news_terms)
    wants_plan = any(
        term in q
        for term in (
            "show plan", "show the plan", "include plan", "show steps",
            "step by step", "break it down", "break down", "execution plan",
            "tool plan", "which tools",
        )
    )

    if not wants_market or not (wants_status or wants_breadth or wants_movers or wants_flows):
        return None

    tasks = [
        _planner_task(
            "current-index-status",
            "Fetch current Indian index levels and live session breadth.",
            tool="get_live_market_overview",
            fallback="NSE live API equity-stockIndices endpoints; if unavailable, label data stale and use latest EOD index snapshot.",
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
                fallback="Use NSE equity-stockIndices for NIFTY 500; if live source fails, derive movers from market.equity_eod latest daily percent change.",
                recovery_plan="If no tool exists, implement an NSE variations/equity-stockIndices client with PostgreSQL EOD fallback.",
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

    return {
        "kind": "market_situation_assessment",
        "tasks": tasks,
        "execution_order": [task["id"] for task in tasks],
        "mode": data_mode,
        "show_plan": wants_plan,
    }


def _extract_fno_symbol(query: str) -> str:
    """Extract an index/stock symbol for F&O tools without treating F&O terms as symbols."""
    text = query or ""
    q = text.lower()
    if "banknifty" in q or "bank nifty" in q or "nifty bank" in q:
        return "BANKNIFTY"
    if "finnifty" in q or "fin nifty" in q:
        return "FINNIFTY"
    if "midcpnifty" in q or "midcap nifty" in q:
        return "MIDCPNIFTY"
    if "nifty" in q:
        return "NIFTY"

    skip = {
        "F", "O", "FO", "FNO", "AND", "FOR", "THE", "WITH", "GIVE", "COMPREHENSIVE",
        "OVERVIEW", "OPTION", "OPTIONS", "CHAIN", "PCR", "MAX", "PAIN", "TOP", "OI",
        "STRIKES", "FUTURES", "BASIS", "COST", "CARRY", "ROLL", "ROLLOVER", "RECOMMEND",
        "BEST", "STRATEGY", "CURRENT", "DATA", "OPEN", "INTEREST",
    }
    for token in re.findall(r"\b[A-Z][A-Z0-9&-]{1,12}\b", text):
        clean = token.upper()
        if clean not in skip:
            return clean
    return "NIFTY"


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
    """Extract the symbol from Agent-generated /analyze <symbol> 360 prompts."""
    match = re.search(
        r"\bcomprehensive\s+360(?:°|\s*degree)?\s+analysis\s+(?:of|for)\s+([A-Z][A-Z0-9&-]{1,20})\b",
        query or "",
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    symbol = match.group(1).upper()
    return symbol if re.fullmatch(r"[A-Z0-9&-]{2,20}", symbol) else ""


def _stock_360_prompt_plan(symbol: str, query: str) -> list[tuple[str, dict]]:
    sym = symbol.upper()
    plan: list[tuple[str, dict]] = [
        ("resolve_symbol", {"query": sym}),
        ("get_symbol_snapshot", {"symbol": sym}),
        ("get_technical_setup", {"symbol": sym}),
        ("comprehensive_stock_research", {"symbol": sym}),
        ("run_forensic_analysis", {"symbol": sym}),
        ("search_latest_catalysts", {"symbol": sym}),
        ("get_sector_context", {"sector_or_symbol": sym}),
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


def _keyword_intent(query: str, data_mode: str = "historical") -> dict:
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

    if "sector" in q and re.search(r"\bit\b|information technology", q):
        return {"intent": "sector_scan", "plan": [("get_sector_context", {"sector_or_symbol": "IT"})]}

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
        "short straddle", "straddle", "strangle", "iron condor", "butterfly",
    )
    if any(term in f" {q} " for term in fno_terms):
        symbol = _extract_fno_symbol(routing_text)
        plan = [("get_fno_overview", {"symbol": symbol, "expiry_index": 0})]
        return {"intent": "fno_overview", "plan": plan}

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
        "overall market", "how is market", "market status",
    ]
    mover_words = [
        "top gainer", "top gainers", "gainers", "losers", "movers",
        "top stocks", "top indices", "indices", "index movers",
    ]
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

    words = re.findall(r"[A-Za-z][A-Za-z0-9\-&\.]+", routing_text)
    skip  = {        "show","me","the","latest","on","for","in","by","during","over","what","is","how","tell",
              "about","give","setup","stock","stocks","sector","nse","india","market","today","brief","full",
              "overview","intraday","levels","level","support","resistance","screener","scan",
              "deep","dive","analysis","technical","trade","trading","of",
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
        and (
            w == w.upper()
            or any(ch.isdigit() for ch in w)
            or ("&" in w and w == w.upper())
            or ("-" in w and w == w.upper())
        )
    ]

    is_single_stock_technical_setup = (
        "technical setup for" in q
        or re.search(r"\b(full|detailed|complete)\s+technical\b.*\bfor\b", q)
    )
    is_strength_validation_query = (
        sum(1 for term in ("canslim", "can slim", "rs", "relative strength", "fundamental", "piotroski", "petroski") if term in q) >= 2
        and any(w in q for w in ("strength", "strong", "which", "rank", "out of"))
    )
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

    if any(term in q for term in ("i own", "my portfolio", "portfolio", "holdings", "holding")) and symbol_candidates:
        return {
            "intent": "portfolio_review",
            "plan": [("generate_portfolio_narratives", {"symbols": symbol_candidates[:10], "top_n": min(len(symbol_candidates), 10)})],
        }

    # Added: standalone "portfolio review / my portfolio / holdings overview"
    # without explicit tickers — call get_portfolio_exposure to summarize the
    # portfolio CSV. Was misrouting to "REVIEW (REVIEW) — Market Brief".
    if any(term in q for term in ("portfolio review", "review my portfolio", "my portfolio", "portfolio summary", "holdings summary", "portfolio overview")):
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
                return {"intent": "stock_results", "plan": [
                    ("resolve_symbol", {"query": raw_entity}),
                    ("get_latest_results", {"symbol": resolved_symbol}),
                ]}

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

    if (
        candidates and explicit_stock_subject
        and (any(term in q for term in results_stock_terms) or _results_freeform)
        and not any(term in q for term in news_priority_terms)
    ):
        sym_q = _primary_symbol_query(candidates, symbol_candidates, routing_text)
        return {"intent": "stock_results", "plan": [
            ("resolve_symbol",           {"query": sym_q}),
            ("get_latest_results",       {"symbol": sym_q.upper()}),
        ]}

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

    # Index query
    index_words = ["nifty", "sensex", "bank nifty", "nifty it", "nifty 50"]
    if any(w in q for w in index_words):
        idx = "NIFTY BANK" if "bank" in q else ("NIFTY IT" if " it" in q else "NIFTY 50")
        return {"intent": "index_status", "plan": [("get_index_snapshot", {"index_name": idx})]}

    # Screener queries
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

def _synthesize_no_llm(intent: str, tool_results: list[dict], assessment_plan: dict | None = None) -> str:
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
    live = _get("get_live_market_overview")
    brd  = _get("get_market_breadth")
    scr  = _get("run_screener_query")
    strength = _get("validate_strength_watchlist")
    knowledge = _get("search_market_knowledge")
    cat  = _get("search_latest_catalysts")
    res  = _get("resolve_symbol")
    glob = _get("get_global_market_assessment")
    movers = _get("get_top_gainers_losers")
    comparison = _get("compare_stocks")
    portfolio_narratives = _get("generate_portfolio_narratives")
    event_calendar = _get("get_event_calendar_summary")
    market_recap = _get("get_intraday_market_recap")
    fno_chain = _get("get_options_chain") or _get("get_option_chain")
    fno_futures = _get("get_futures_analysis")
    fno_strategy = _get("get_strategy_recommendations")
    fno_overview = _get("get_fno_overview")
    forensic = _get("run_forensic_analysis")
    deep = _get("deep_search")
    intra_setup = _get("explain_intraday_setup")
    intra_screen = _get("run_intraday_screener")
    intra_index_scan = _get("scan_intraday_market")
    intra_symbol_scan = _get("scan_symbols_intraday")
    intra_levels = _get("get_intraday_levels")
    intra_ind = _get("compute_intraday_indicators")
    nse_intraday = _get("get_nse_intraday_snapshot")
    intra_legacy = _get("get_intraday_analysis")
    scr_fund = _get("scrape_screener_in")
    research = _get("comprehensive_stock_research") or {}
    # /analyze pipes through comprehensive_stock_research, which wraps
    # scrape_screener_in under result["screener"]. Backfill scr_fund so the
    # downstream FUNDAMENTAL ANALYSIS block has the data it needs.
    if not scr_fund and isinstance(research, dict):
        emb = research.get("screener")
        if isinstance(emb, dict):
            scr_fund = emb
    nse_ann  = _get("search_nse_announcements")
    bse_filings = _get("search_bse_filings")
    concalls = _get("search_concall_transcripts")
    latest_results = _get("get_latest_results")
    latest_report = _get("find_latest_report")
    listed_reports = _get("list_generated_reports")
    opened_report = _get("open_report")
    read_report_result = _get("read_report")
    report_summary = _get("summarize_report")
    last_report = _get("get_last_report")
    youtube = _get("analyze_youtube_video") or _get("analyze_youtube_channel_latest")
    youtube_channels = _get("list_youtube_channels")

    sym = (snap or {}).get("symbol") or (tech or {}).get("symbol") or ""
    if not sym and forensic:
        sym = forensic.get("symbol") or ""
    cname = (snap or {}).get("company_name") or sym

    def _render_assessment_plan(plan: dict | None) -> None:
        if not plan:
            return
        tool_status: dict[str, str] = {}
        for tr in tool_results:
            result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
            tool_status[tr["tool"]] = f"ERROR: {result.get('error')}" if result.get("error") else "ok"

        lines.append("▶ SITUATION ASSESSMENT PLAN")
        for i, task in enumerate(plan.get("tasks") or [], start=1):
            tool = task.get("tool")
            derived_from = task.get("derived_from")
            if tool:
                status = tool_status.get(tool, "not executed")
                source = f"tool={tool}"
            elif derived_from:
                status = "derived" if tool_status.get(derived_from) == "ok" else f"blocked by {derived_from}"
                source = f"derived_from={derived_from}"
            else:
                status = "missing tool"
                source = "tool=missing"
            lines.append(f"  {i}. {task.get('question')} [{source}; status={status}]")
            if status != "ok" and status != "derived" and task.get("fallback"):
                lines.append(f"     fallback: {task.get('fallback')}")
            if (not tool or status.startswith("ERROR") or status == "not executed") and task.get("recovery_plan"):
                lines.append(f"     recovery/code plan: {task.get('recovery_plan')}")
        lines.append("")

    def _first_nonempty_row(table: dict, labels: tuple[str, ...]) -> tuple[str, list] | None:
        # Match each label loosely: ignores trailing "+" / "%" and is case-insensitive
        def _norm(s: str) -> str:
            return (s or "").replace("+", "").replace("%", "").strip().lower()
        wanted = {_norm(label) for label in labels}
        for key, values in (table or {}).items():
            if key.startswith("_"):
                continue
            if _norm(key) in wanted and isinstance(values, list) and any(str(v).strip() for v in values):
                return key, values
        return None

    def _render_stock_results(symbol: str) -> None:
        q = (scr_fund or {}).get("quarterly") or {}
        q_headers = q.get("_headers") if isinstance(q, dict) else []
        annual = (scr_fund or {}).get("annual_pl") or {}
        annual_headers = annual.get("_headers") if isinstance(annual, dict) else []
        ratios = (scr_fund or {}).get("ratios") or {}

        def _is_junk_url(url: str) -> bool:
            if not url:
                return False
            u = url.lower()
            return any(j in u for j in (
                "duckduckgo.com/y.js",
                "bing.com/aclick",
                "investilo.ai",
                "msclkid=",
                "/y.js?ad_domain=",
            ))

        def _clean_title(t: str) -> str:
            t = (t or "").strip()
            for noise in (
                "| BSE", "|BSE", " - BSE", " | NSE", "LIVE Stock/Share Market",
                "Today's Stock Market News", "AI-Powered Stock Analysis",
            ):
                if noise in t:
                    t = t.replace(noise, "").strip()
            # Strip screener.in relative-time badge glued to title (e.g. "Acquisition1d", "Dividend23h")
            t = re.sub(r"([A-Za-z\)])(\d+[dhm])(?=\s|-|$)", r"\1", t)
            # Insert missing space between digits and lowercase word (e.g. "2025from bse")
            t = re.sub(r"(\d)([a-z])", r"\1 \2", t)
            return re.sub(r"\s{2,}", " ", t).rstrip(" |").strip()

        lines.append(f"━━━ {symbol or (scr_fund or {}).get('symbol', 'Stock')} — Latest Results Evidence ━━━")
        lines.append("")

        # LATEST PERIOD SUMMARY — reconcile period from available sources
        period_sources: list[str] = []
        period_label = ""
        if q_headers:
            last_q = str(q_headers[-1])
            period_label = f"Quarter ending {last_q}"
            period_sources.append(f"screener {last_q}")
        annual_hdrs_local = annual_headers or []
        if annual_hdrs_local:
            period_sources.append(f"annual {annual_hdrs_local[-1]}")
        for item in (nse_ann or {}).get("bse_filings") or (nse_ann or {}).get("nse_filings") or []:
            if not isinstance(item, dict):
                continue
            t_low = (item.get("title") or item.get("subject") or "").lower()
            if any(k in t_low for k in (
                "financial results", "outcome of board meeting",
                "audited results", "unaudited results", "outcomeofbm",
            )):
                d = item.get("date") or item.get("published")
                if d:
                    period_sources.append(f"BSE filing {d}")
                break
        if period_label or period_sources:
            lines.append("▶ LATEST PERIOD SUMMARY")
            if period_label:
                lines.append(f"  Period: {period_label}")
            if period_sources:
                lines.append(f"  Reconciled from: {' · '.join(period_sources[:4])}")
            lines.append("")

        lines.append("▶ FINANCIAL SNAPSHOT")
        if ratios:
            snap_keys = (
                ("Market Cap", "₹ Cr"),
                ("Current Price", "₹"),
                ("Stock P/E", ""),
                ("ROE", "%"),
                ("ROCE", "%"),
                ("Book Value", "₹"),
                ("Dividend Yield", "%"),
                ("Debt to equity", ""),
                ("EPS", "₹"),
                ("Promoter holding", "%"),
            )
            snap_rows: list[tuple[str, str]] = []
            for k, unit in snap_keys:
                v = ratios.get(k)
                if v:
                    snap_rows.append((k, f"{v}" + (f" {unit}" if unit and unit not in str(v) else "")))
            if snap_rows:
                lines.append("")
                lines.append("  | Metric             | Value                |")
                lines.append("  |--------------------|----------------------|")
                for k, v in snap_rows:
                    lines.append(f"  | {k[:18]:<18} | {str(v)[:20]:<20} |")
                lines.append("")

        # Quarterly P&L as a real markdown table
        if q_headers:
            quarterly_metrics = []
            for labels in (
                ("Sales", "Revenue", "Operating Revenue"),
                ("Expenses",),
                ("Operating Profit",),
                ("OPM %",),
                ("Net Profit", "Profit after tax", "PAT"),
                ("EPS in Rs", "EPS"),
            ):
                row = _first_nonempty_row(q, labels)
                if row:
                    quarterly_metrics.append(row)
            if quarterly_metrics:
                lines.append("▶ QUARTERLY P&L (₹ Cr — last 6 quarters)")
                lines.append("")
                hdr_cells = [str(h) for h in q_headers[:6]]
                lines.append("  | Metric              | " + " | ".join(f"{h:>10}" for h in hdr_cells) + " |")
                lines.append("  |---------------------|" + ("------------|" * len(hdr_cells)))
                for label, values in quarterly_metrics:
                    padded = (values[:6] + [""] * (len(hdr_cells) - len(values[:6])))
                    cells = " | ".join(f"{str(v or '—'):>10}" for v in padded)
                    lines.append(f"  | {_clean_title(label)[:19]:<19} | {cells} |")
                lines.append("")
            elif scr_fund and scr_fund.get("error"):
                lines.append(f"  Screener unavailable: {scr_fund.get('error')}")
                lines.append("")

        # Annual P&L as a real markdown table
        if annual_headers and isinstance(annual, dict):
            annual_metrics = []
            for labels in (
                ("Sales", "Revenue"),
                ("Expenses",),
                ("Operating Profit",),
                ("OPM %",),
                ("Net Profit", "Profit after tax", "PAT"),
                ("EPS in Rs", "EPS"),
                ("Dividend Payout %",),
            ):
                row = _first_nonempty_row(annual, labels)
                if row:
                    annual_metrics.append(row)
            if annual_metrics:
                lines.append("▶ ANNUAL P&L (₹ Cr — last 5 years)")
                lines.append("")
                hdr_cells = [str(h) for h in annual_headers[:5]]
                lines.append("  | Metric              | " + " | ".join(f"{h:>10}" for h in hdr_cells) + " |")
                lines.append("  |---------------------|" + ("------------|" * len(hdr_cells)))
                for label, values in annual_metrics:
                    padded = (values[:5] + [""] * (len(hdr_cells) - len(values[:5])))
                    cells = " | ".join(f"{str(v or '—'):>10}" for v in padded)
                    lines.append(f"  | {_clean_title(label)[:19]:<19} | {cells} |")
                lines.append("")

        # Pros / Cons from screener
        pros = (scr_fund or {}).get("pros") or []
        cons = (scr_fund or {}).get("cons") or []
        if pros or cons:
            lines.append("▶ SCREENER ANALYSIS")
            if pros:
                lines.append("  Pros:")
                for p in pros[:4]:
                    lines.append(f"    • {p}")
            if cons:
                lines.append("  Cons:")
                for c in cons[:4]:
                    lines.append(f"    • {c}")
            lines.append("")

        # Consolidated filings: dedupe across NSE/screener announcements / BSE filings
        lines.append("▶ RESULT FILINGS & ANNOUNCEMENTS")
        seen_urls: set[str] = set()
        rendered_count = 0
        max_filings = 8

        def _emit_filing(title: str, url: str, date: str = "", category: str = "") -> bool:
            nonlocal rendered_count
            if rendered_count >= max_filings or _is_junk_url(url):
                return False
            key = (url or title).split("?")[0].rstrip("/")
            if key in seen_urls:
                return False
            seen_urls.add(key)
            t = _clean_title(title)[:100] or "Filing"
            cat = f"[{category}] " if category else ""
            dt = f"{date} — " if date else ""
            url_part = f"\n      {url}" if url else ""
            lines.append(f"  • {cat}{dt}{t}{url_part}")
            rendered_count += 1
            return True

        # 1. NSE/BSE corporate announcements (highest signal — actual filings)
        nse_payload = nse_ann or {}
        if not nse_payload.get("error"):
            for item in (nse_payload.get("results") or nse_payload.get("announcements") or
                         nse_payload.get("bse_filings") or nse_payload.get("nse_filings") or []):
                if not isinstance(item, dict):
                    continue
                _emit_filing(
                    item.get("title") or item.get("subject") or item.get("desc") or "",
                    item.get("url") or item.get("link") or item.get("pdf_url") or item.get("att_url") or "",
                    item.get("date") or item.get("published") or "",
                )
        # 2. Screener.in announcements (often duplicates the above — dedupe handles it)
        for item in (scr_fund or {}).get("announcements") or []:
            if isinstance(item, dict):
                _emit_filing(item.get("title", ""), item.get("url", ""))
        # 3. BSE filings from DDG search (lower signal — only fill remaining slots,
        # and only with deep filings/results URLs not generic company-quote pages)
        bse_payload = bse_filings or {}
        if not bse_payload.get("error"):
            bse_results = bse_payload.get("results") or {}
            if isinstance(bse_results, dict):
                for cat_key, group in bse_results.items():
                    if not isinstance(group, list):
                        continue
                    for entry in group:
                        if not isinstance(entry, dict):
                            continue
                        url = entry.get("url") or ""
                        # Only accept BSE filings/results/board-meeting pages
                        if not any(s in url for s in (
                            "/financials-results/", "/board-meetings/",
                            "/financials-annual-reports/", "comp_results.aspx",
                            "AttachLive", "AttachHis",
                        )):
                            continue
                        _emit_filing(entry.get("title", ""), url, category=cat_key)
        if rendered_count == 0:
            lines.append("  No recent result filing links were returned.")
        lines.append("")

        # Concall transcripts — dedupe and prefer transcript > ppt > recording
        lines.append("▶ CONCALL / MANAGEMENT COMMENTARY")
        screener_concalls = (scr_fund or {}).get("concalls") or []
        rendered_concalls = 0
        for item in screener_concalls[:5]:
            if not isinstance(item, dict):
                continue
            period = item.get("period") or "Period"
            link_parts: list[str] = []
            for key, label in (("transcript_url", "Transcript"), ("ppt_url", "PPT"), ("recording_url", "Recording")):
                u = item.get(key)
                if u and not _is_junk_url(u):
                    link_parts.append(f"{label}: {u}")
            if link_parts:
                lines.append(f"  • {period}")
                for lp in link_parts:
                    lines.append(f"      {lp}")
                rendered_concalls += 1
        if rendered_concalls == 0:
            concall_items = (concalls or {}).get("results") or (concalls or {}).get("items") or []
            for item in concall_items[:3]:
                if isinstance(item, dict):
                    url = item.get("url") or item.get("link") or ""
                    if _is_junk_url(url):
                        continue
                    title = _clean_title(item.get("title") or item.get("headline") or "")
                    if title:
                        lines.append(f"  • {title}" + (f"\n      {url}" if url else ""))
                        rendered_concalls += 1
        if rendered_concalls == 0:
            lines.append("  No concall transcript or presentation link was returned.")
        lines.append("")

        # Latest catalysts — filter junk URLs
        lines.append("▶ LATEST CATALYSTS")
        catalyst_items = (cat or {}).get("results") or (cat or {}).get("items") or [] if isinstance(cat, dict) else []
        rendered_catalysts = 0
        for item in catalyst_items[:6]:
            if not isinstance(item, dict):
                continue
            url = item.get("url") or item.get("link") or ""
            if _is_junk_url(url):
                continue
            title = _clean_title(item.get("title") or item.get("headline") or "")
            if not title:
                continue
            lines.append(f"  • {title}" + (f"\n      {url}" if url else ""))
            rendered_catalysts += 1
            if rendered_catalysts >= 5:
                break
        if rendered_catalysts == 0:
            if isinstance(cat, dict) and cat.get("error"):
                lines.append(f"  ERROR: {cat.get('error')}")
            else:
                lines.append("  No latest catalyst items were returned.")
        lines.append("")

        # ── DEEP-DIVE INSIGHTS: recursively /analyze top 2 PDFs for the latest period ──
        def _classify_filing(title: str, url: str) -> tuple[str, int]:
            t = (title or "").lower()
            u = (url or "").lower()
            if any(k in t for k in ("investor presentation", "investor update",
                                    "earnings presentation", "results presentation")):
                return ("investor_pres", 1)
            if any(k in t for k in (
                "outcome of board meeting", "outcomeofbm", "outcome of bm",
                "financial results", "audited financial", "unaudited financial",
                "quarterly results", "quarterly result", "earnings release",
                "results - sebi", "results-sebi",
            )):
                return ("earnings_outcome", 2)
            if any(k in t for k in ("transcript", "concall transcript", "earnings call")):
                return ("transcript", 3)
            if "annual report" in t or "annualreport" in u or "bseplus/annualreport" in u:
                return ("annual_report", 4)
            return ("other", 9)

        def _is_analyzable_pdf(url: str) -> bool:
            if not url:
                return False
            u = url.lower()
            if u.endswith(".pdf"):
                return True
            return any(k in u for k in (
                "annpdfopen", "attachlive", "attachhis",
                "bseplus/annualreport", "/corpfiling/",
            ))

        deep_candidates: list[dict] = []

        # Primary: screener concalls list (clean, period-grouped, latest-first)
        for entry in ((scr_fund or {}).get("concalls") or [])[:3]:
            if not isinstance(entry, dict):
                continue
            period = entry.get("period") or ""
            # Prefer PPT (= investor presentation), then transcript
            if entry.get("ppt_url") and not _is_junk_url(entry["ppt_url"]):
                deep_candidates.append({
                    "title": f"{period} Investor Presentation",
                    "url": entry["ppt_url"], "rank": 1, "kind": "investor_pres",
                })
            if entry.get("transcript_url") and not _is_junk_url(entry["transcript_url"]):
                deep_candidates.append({
                    "title": f"{period} Earnings Call Transcript",
                    "url": entry["transcript_url"], "rank": 2, "kind": "earnings_outcome",
                })

        nse_payload = nse_ann or {}
        if not nse_payload.get("error"):
            for item in (nse_payload.get("results") or nse_payload.get("announcements")
                         or nse_payload.get("bse_filings") or nse_payload.get("nse_filings") or []):
                if not isinstance(item, dict):
                    continue
                title = item.get("title") or item.get("subject") or ""
                url = (item.get("url") or item.get("link")
                       or item.get("pdf_url") or item.get("att_url") or "")
                if not _is_analyzable_pdf(url) or _is_junk_url(url):
                    continue
                kind, rank = _classify_filing(title, url)
                if kind in ("investor_pres", "earnings_outcome"):
                    deep_candidates.append({"title": title, "url": url,
                                            "rank": rank, "kind": kind})
        for item in (scr_fund or {}).get("announcements") or []:
            if not isinstance(item, dict):
                continue
            title = item.get("title", "")
            url = item.get("url", "")
            if not _is_analyzable_pdf(url) or _is_junk_url(url):
                continue
            kind, rank = _classify_filing(title, url)
            if kind in ("investor_pres", "earnings_outcome"):
                deep_candidates.append({"title": title, "url": url,
                                        "rank": rank, "kind": kind})

        # Dedupe by URL stem, sort by rank, take top 2
        _seen_urls: set[str] = set()
        _uniq: list[dict] = []
        for c in deep_candidates:
            key = c["url"].split("?")[0].rstrip("/")
            if key in _seen_urls:
                continue
            _seen_urls.add(key)
            _uniq.append(c)
        _uniq.sort(key=lambda x: x["rank"])
        picks = _uniq[:2]

        if picks:
            lines.append("▶ DEEP-DIVE INSIGHTS (recursive /analyze on top filings)")
            deadline = time.time() + 120
            for pick in picks:
                if time.time() > deadline:
                    lines.append(f"  • Skipped remaining picks: 120s time budget exceeded")
                    break
                kind_label = pick["kind"].replace("_", " ").title()
                lines.append("")
                lines.append(f"  ◆ {kind_label}: {_clean_title(pick['title'])[:110]}")
                lines.append(f"    Source: {pick['url']}")
                try:
                    analysis = call_tool("analyze_document", {
                        "source": pick["url"], "max_pages": 40,
                        "vision_fallback": True,
                    })
                except Exception as exc:
                    lines.append(f"    Analysis error: {exc}")
                    continue
                # Append to tool_results so SOURCE TRAIL reflects recursive call
                tool_results.append({
                    "tool": "analyze_document",
                    "args": {"source": pick["url"]},
                    "result": analysis if isinstance(analysis, dict) else {"text": str(analysis)},
                })
                if not isinstance(analysis, dict):
                    lines.append("    (no parsed content)")
                    continue
                if analysis.get("error"):
                    lines.append(f"    Analysis error: {analysis.get('error')}")
                    continue
                # fetch_pdf_text returns {text, pages: [{page,text,...}], total_pages, ...}
                # fetch_article_content returns {content, ...}
                page_list = analysis.get("pages") or analysis.get("page_texts") or []
                if not isinstance(page_list, list):
                    page_list = []
                page_count = analysis.get("total_pages") or analysis.get("page_count") or len(page_list)
                text = (analysis.get("text") or analysis.get("content") or "").strip()
                if not text and page_list:
                    text = "\n\n".join(
                        (pt.get("text") or "").strip()
                        for pt in page_list if isinstance(pt, dict)
                    ).strip()
                if isinstance(page_count, int) and page_count > 0:
                    lines.append(f"    Pages parsed: {page_count}")
                if text:
                    preview = text[:1500].strip()
                    shown_lines = 0
                    for raw in preview.splitlines():
                        ln = raw.strip()
                        if not ln:
                            continue
                        lines.append(f"    {ln[:140]}")
                        shown_lines += 1
                        if shown_lines >= 25:
                            break
                    if len(text) > 1500:
                        lines.append(f"    … (preview truncated — full {len(text):,} chars in MD report)")
                else:
                    lines.append("    (no extractable text)")
            lines.append("")

    if intent == "greeting":
        lines.append("Hello — Agent Adda is ready.")
        lines.append("Try `/live` for current market status, `/global` for global cues, `/heat` for breadth/sector heat, or ask about a specific NSE symbol.")
        lines.append("\n━━━ Not investment advice. For research and learning only. ━━━")
        return "\n".join(lines)

    if intent == "placeholder_symbol_request":
        lines.append("▶ NEED A REAL NSE SYMBOL")
        lines.append("  Replace the placeholder with an actual NSE symbol or company name.")
        lines.append("")
        lines.append("▶ EXAMPLES")
        lines.append("  /assess RELIANCE")
        lines.append("  /assess TCS")
        lines.append("  RELIANCE technical setup")
        lines.append("")
        lines.append("▶ WHY")
        lines.append(
            "  `SYMBOL`, `TICKER`, and similar placeholders are templates, not tradable NSE symbols. "
            "No market, technical, sector, or catalyst conclusion was inferred from placeholder input."
        )
        lines.append("\n━━━ Not investment advice. For research and learning only. ━━━")
        return "\n".join(lines)

    if intent == "document_link_help":
        lines.append("▶ DOCUMENT LINK FOLLOW-UP")
        lines.append("  This looks like a document/PDF follow-up, not a stock-symbol query.")
        lines.append("")
        lines.append("▶ WHAT TO DO")
        lines.append("  Re-run `/analyze <URL>` with the document URL. Wrapped/pasted URLs are normalized before PDF extraction.")
        lines.append("  If the URL still fails, paste the source page URL or use a company/results search prompt with the company name and period.")
        lines.append("")
        lines.append("▶ EXAMPLES")
        lines.append("  /analyze https://www.diageoindia.com/pdf-viewer.aspx?...src=...pdf")
        lines.append("  find United Spirits FY26 audited results PDF")
        lines.append("")
        lines.append("▶ SOURCE TRAIL")
        lines.append("  No equity symbol was resolved; no market conclusion was inferred.")
        lines.append("\n━━━ Not investment advice. For research and learning only. ━━━")
        return "\n".join(lines)

    if intent in {
        "youtube_video_analysis", "youtube_channel_latest",
        "youtube_video_transcription", "youtube_channel_transcription",
        "youtube_channels",
    }:
        if youtube and youtube.get("error"):
            lines.append("▶ YOUTUBE ANALYSIS")
            lines.append(f"  Error: {youtube.get('error')}")
            lines.append("")
        elif youtube:
            lines.append("▶ YOUTUBE MARKET INTELLIGENCE")
            selected = youtube.get("selected_channel") or {}
            latest = youtube.get("latest_video") or {}
            if selected:
                lines.append(f"  Selected channel: {selected.get('name') or selected.get('id')}")
            if latest:
                lines.append(f"  Latest video:     {latest.get('title') or latest.get('video_id')}")
            lines.append(f"  Title:   {youtube.get('title') or '—'}")
            lines.append(f"  Channel: {youtube.get('channel') or '—'}")
            lines.append(f"  Date:    {youtube.get('published_at') or '—'}")
            lines.append(f"  URL:     {youtube.get('url')}")
            transcript = youtube.get("transcript") or {}
            lines.append(f"  Transcript: {'available' if transcript.get('available') else 'unavailable'} ({transcript.get('segment_count', 0)} segments)")
            if not transcript.get("available") and transcript.get("reason"):
                lines.append(f"  Transcript note: {transcript.get('reason')}")
            transcription = youtube.get("transcription") or {}
            if transcription.get("requested"):
                detail = f"  Transcription: {transcription.get('status') or 'unknown'} via {transcription.get('backend') or '—'}"
                if transcription.get("model"):
                    detail += f" ({transcription.get('model')})"
                lines.append(detail)
                if transcription.get("reason"):
                    lines.append(f"  Transcription note: {transcription.get('reason')}")
                if transcription.get("temporary_audio_deleted"):
                    lines.append("  Audio handling: temporary audio deleted after transcription")
            elif not transcript.get("available"):
                lines.append("  To run speech-to-text explicitly: /youtube transcribe <channel|url> [--backend local|auto]")
            lines.append(f"  Market relevance: {youtube.get('market_relevance')}")
            if youtube.get("artifact_path"):
                lines.append(f"  Artifact: {youtube.get('artifact_path')}")
            lines.append("")
            topics = youtube.get("market_topic_counts") or {}
            if topics:
                lines.append("▶ TOPIC SIGNALS")
                for topic, count in sorted(topics.items(), key=lambda kv: kv[1], reverse=True):
                    lines.append(f"  {topic}: {count}")
                lines.append("")
            insights = youtube.get("market_insights") or []
            if insights:
                lines.append("▶ MARKET INSIGHTS")
                for insight in insights[:6]:
                    lines.append(f"  • {insight}")
                lines.append("")
            segments = youtube.get("market_segments") or []
            lines.append("▶ TIMESTAMPED MARKET EXTRACTS")
            if segments:
                for segment in segments[:10]:
                    lines.append(f"  {segment.get('timestamp', '—')}: {segment.get('excerpt', '')}")
            else:
                lines.append("  No market-specific transcript segments were detected.")
            lines.append("")
            followups = youtube.get("suggested_followups") or []
            if followups:
                lines.append("▶ FOLLOW-UP QUESTIONS")
                for idx, followup in enumerate(followups[:6], start=1):
                    suffix = f" — {followup.get('why')}" if followup.get("why") else ""
                    lines.append(f"  {idx}. {followup.get('prompt')}{suffix}")
                lines.append("")
            lines.append("▶ SOURCE POLICY")
            lines.append(f"  {youtube.get('source_policy')}")
            lines.append("")
        channels = (youtube_channels or {}).get("channels") or []
        lines.append("▶ PRESET YOUTUBE CHANNELS")
        if channels:
            for channel in channels:
                state = "enabled" if channel.get("enabled", True) else "disabled"
                feed = "latest-feed" if channel.get("has_latest_feed") else "manual-url"
                lines.append(f"  {channel.get('index', '—')}. {channel.get('name')} [{state}; {feed}] — {channel.get('category', 'market')}")
        else:
            lines.append("  No preset channels configured yet.")
        lines.append("")
        lines.append("▶ USAGE")
        lines.append("  /youtube")
        lines.append("  /youtube 1")
        lines.append("  /youtube <channel name>")
        lines.append("  /youtube <youtube-url>")
        lines.append("  /youtube transcribe 1 [--backend local|auto]")
        lines.append("  /youtube transcribe <youtube-url> [--backend local|auto]")
        lines.append("  /youtube channels")
        lines.append("\n━━━ Not investment advice. For research and learning only. ━━━")
        return "\n".join(lines)

    if intent == "report_lookup":
        report_payload = opened_report or report_summary or read_report_result or last_report or listed_reports or latest_report or {}
        status = report_payload.get("status") or ("ok" if report_payload else "unknown")
        lines.append("▶ REPORT CONTEXT")
        if opened_report:
            lines.append(f"  Status: {status}")
            lines.append(f"  Path:   {opened_report.get('path') or 'N/A'}")
            if opened_report.get("message"):
                lines.append(f"  Note:   {opened_report.get('message')}")
        elif report_summary:
            lines.append(f"  Status:         {status}")
            lines.append(f"  Path:           {report_summary.get('path') or 'N/A'}")
            if report_summary.get("symbol"):
                lines.append(f"  Symbol:         {report_summary.get('symbol')}")
            if report_summary.get("recommendation"):
                lines.append(f"  Recommendation: {report_summary.get('recommendation')}")
            if report_summary.get("summary"):
                lines.append("")
                lines.append("▶ SUMMARY")
                for line in str(report_summary.get("summary")).splitlines()[:12]:
                    lines.append(f"  {line}")
        elif read_report_result:
            lines.append(f"  Status: {status}")
            lines.append(f"  Path:   {read_report_result.get('path') or 'N/A'}")
            content = str(read_report_result.get("content") or "").strip()
            if content:
                lines.append("")
                lines.append("▶ PREVIEW")
                for line in content.splitlines()[:12]:
                    if line.strip():
                        lines.append(f"  {line[:140]}")
        elif last_report and last_report.get("report"):
            report = last_report.get("report") or {}
            lines.append(f"  Status: {status}")
            lines.append(f"  Path:   {report.get('path') or report.get('absolute_path') or 'N/A'}")
            lines.append(f"  Type:   {report.get('report_type') or 'report'}")
        elif listed_reports:
            reports = listed_reports.get("reports") or []
            lines.append(f"  Status: {status}")
            lines.append(f"  Count:  {listed_reports.get('count', len(reports))}")
            for row in reports[:10]:
                lines.append(f"  - {row.get('name')} | {row.get('report_type')} | {row.get('path')}")
        elif latest_report:
            files = latest_report.get("files") or []
            lines.append(f"  Count: {latest_report.get('count', len(files))}")
            for row in files[:10]:
                lines.append(f"  - {row.get('name')} | {row.get('path')}")
        else:
            lines.append("  No report context was available.")
        lines.append("")
        lines.append("▶ SOURCE TRAIL")
        lines.extend(_source_trail_lines(tool_results))
        lines.append("\n━━━ Not investment advice. For research and learning only. ━━━")
        return "\n".join(lines)

    if intent == "stock_results":
        if latest_results:
            lines.append(f"━━━ {latest_results.get('symbol', 'SYMBOL')} — Latest Results Evidence ━━━")
            lines.append("")
            lines.append("▶ LATEST RESULTS PACK")
            lines.append(f"  Status: {latest_results.get('status', 'unknown')}")
            lines.append(f"  Period: {latest_results.get('period', 'latest')}")
            selected = latest_results.get("selected_filing") or {}
            if selected:
                lines.append(f"  Selected filing: {selected.get('title') or selected.get('url') or 'N/A'}")
                if selected.get("source"):
                    lines.append(f"  Filing source:   {selected.get('source')}")
            warning = latest_results.get("warning") or {}
            if warning.get("message"):
                lines.append(f"  ⚠ {warning.get('message')}")
            facts = latest_results.get("facts") or {}
            if facts:
                lines.append("")
                lines.append("▶ RECONCILED FACTS")
                for label, key in (("Revenue", "revenue"), ("PAT", "pat"), ("EPS", "eps")):
                    item = facts.get(key)
                    if item:
                        lines.append(
                            f"  {label}: {item.get('value')} "
                            f"({item.get('period', 'latest')} · {item.get('source', 'source unavailable')})"
                        )
            missing = latest_results.get("missing_facts") or []
            if missing:
                lines.append("")
                lines.append("▶ MISSING FACTS")
                lines.append("  " + ", ".join(missing))
            if latest_results.get("summary"):
                lines.append("")
                lines.append("▶ SUMMARY")
                for line in str(latest_results.get("summary")).splitlines():
                    lines.append(f"  {line}")
        else:
            _render_stock_results(sym or (scr_fund or {}).get("symbol", ""))
        lines.append("▶ SOURCE TRAIL")
        if latest_results and isinstance(latest_results.get("source_trail"), dict):
            for tool, status in latest_results["source_trail"].items():
                lines.append(f"  {tool}: {status}")
        else:
            for trail_line in _source_trail_lines(tool_results):
                lines.append(trail_line)
        lines.append("\n━━━ Not investment advice. For research and learning only. ━━━")
        body = "\n".join(lines)
        # Save Markdown deep-dive report alongside the terminal output
        try:
            import os as _os
            import datetime as _dt
            symbol_out = (sym or (scr_fund or {}).get("symbol") or "RESULTS").upper()
            ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = _os.path.join(_os.getcwd(), "reports", "generated")
            _os.makedirs(out_dir, exist_ok=True)
            md_path = _os.path.join(out_dir, f"{symbol_out}_results_{ts}.md")
            md_chunks = [f"# {symbol_out} — Latest Results Deep-Dive", "", body, ""]
            doc_dumps = [tr for tr in tool_results if tr.get("tool") == "analyze_document"]
            if doc_dumps:
                md_chunks.append("\n---\n\n## Appendix: Full Document Text (recursive /analyze)\n")
                for tr in doc_dumps:
                    src = (tr.get("args") or {}).get("source", "")
                    res = tr.get("result") if isinstance(tr.get("result"), dict) else {}
                    md_chunks.append(f"### Source: {src}\n")
                    if res.get("error"):
                        md_chunks.append(f"_Error: {res.get('error')}_\n")
                    else:
                        full_text = res.get("text") or res.get("content") or ""
                        if not full_text:
                            pts = res.get("pages") or res.get("page_texts") or []
                            if isinstance(pts, list) and pts:
                                full_text = "\n\n".join(
                                    f"### Page {pt.get('page', i+1)}\n\n{(pt.get('text') or '').strip()}"
                                    for i, pt in enumerate(pts) if isinstance(pt, dict)
                                )
                        if full_text:
                            if len(full_text) > 50000:
                                md_chunks.append(full_text[:50000])
                                md_chunks.append(
                                    f"\n_(truncated at 50000 chars — original {len(full_text):,} chars)_"
                                )
                            else:
                                md_chunks.append(full_text)
                        else:
                            md_chunks.append("_(no text extracted)_")
                    md_chunks.append("")
            with open(md_path, "w", encoding="utf-8") as _f:
                _f.write("\n".join(md_chunks))
            body += f"\n\n📄 Deep-dive report saved: {md_path}"
        except Exception as _save_exc:
            body += f"\n\n⚠ MD save failed: {_save_exc}"
        return body

    if intent == "results_feed":
        feed = {}
        for tr in tool_results:
            if tr.get("tool") == "get_latest_results_feed":
                feed = tr.get("result") if isinstance(tr.get("result"), dict) else {}
                break
        rows = feed.get("results") or []
        days_back = feed.get("days_back", 7)
        lines.append(f"━━━ Latest Quarterly Results Feed — last {days_back} day(s) ━━━")
        note = feed.get("window_note") or ""
        if note:
            lines.append(f"  {note}")
        src = feed.get("source") or "n/a"
        total_avail = feed.get("total_available", "?")
        total_in_win = feed.get("total_in_window", 0)
        lines.append(f"  Source: {src}  ·  in-window: {total_in_win}  ·  available: {total_avail}")
        if feed.get("nse_error"):
            lines.append(f"  ⚠ NSE error: {feed.get('nse_error')}")
        if not rows:
            lines.append("\n  No results filings found.")
        else:
            lines.append("")
            lines.append("| # | Symbol | Company | Period | FY | Filed | Audited | Cons | Industry |")
            lines.append("|---|--------|---------|--------|----|-------|---------|------|----------|")
            for i, r in enumerate(rows[:50], 1):
                sym_c   = (r.get("symbol") or "")[:12]
                co      = (r.get("company") or "")[:32]
                period  = (r.get("period")  or "")[:18]
                fy      = (r.get("financial_year") or "")[:7]
                filed   = (r.get("filing_date") or "")[:17]
                aud     = (r.get("audited") or "")[:10]
                cons    = (r.get("consolidated") or "")[:6]
                ind     = (r.get("industry") or "")[:22]
                lines.append(f"| {i} | {sym_c} | {co} | {period} | {fy} | {filed} | {aud} | {cons} | {ind} |")
            xbrl_links = [(r.get("symbol",""), r.get("xbrl_url","")) for r in rows[:8] if r.get("xbrl_url")]
            if xbrl_links:
                lines.append("")
                lines.append("▶ XBRL FILINGS (top 8)")
                for s_, u_ in xbrl_links:
                    lines.append(f"  • {s_}: {u_}")
        lines.append("")
        lines.append("▶ SOURCE TRAIL")
        for trail_line in _source_trail_lines(tool_results):
            lines.append(trail_line)
        lines.append("\n━━━ Not investment advice. For research and learning only. ━━━")
        return "\n".join(lines)

    if intent == "forthcoming_results":
        feed = {}
        for tr in tool_results:
            if tr.get("tool") == "get_forthcoming_results":
                feed = tr.get("result") if isinstance(tr.get("result"), dict) else {}
                break
        rows = feed.get("results") or []
        days_ahead = feed.get("days_ahead", 14)
        lines.append(f"━━━ Forthcoming Results — next {days_ahead} day(s) ━━━")
        note = feed.get("window_note") or ""
        if note:
            lines.append(f"  {note}")
        src = feed.get("source") or "n/a"
        total_avail = feed.get("total_available", "?")
        total_in_win = feed.get("total_in_window", 0)
        lines.append(f"  Source: {src}  ·  in-window: {total_in_win}  ·  upcoming-total: {total_avail}")
        if feed.get("error"):
            lines.append(f"  ⚠ {feed.get('error')}")
        if not rows:
            lines.append("\n  No forthcoming results events found.")
        else:
            lines.append("")
            lines.append("| # | Date | Symbol | Company | Purpose |")
            lines.append("|---|------|--------|---------|---------|")
            for i, r in enumerate(rows[:50], 1):
                dt_     = (r.get("date") or "")[:12]
                sym_c   = (r.get("symbol") or "")[:14]
                co      = (r.get("company") or "")[:34]
                purpose = (r.get("purpose") or "")[:40]
                lines.append(f"| {i} | {dt_} | {sym_c} | {co} | {purpose} |")
        lines.append("")
        lines.append("▶ SOURCE TRAIL")
        for trail_line in _source_trail_lines(tool_results):
            lines.append(trail_line)
        lines.append("\n━━━ Not investment advice. For research and learning only. ━━━")
        return "\n".join(lines)

    if intent == "entity_topic_command":
        symbol = ""
        for tr in tool_results:
            result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
            args = tr.get("args") if isinstance(tr.get("args"), dict) else {}
            symbol = str(result.get("symbol") or args.get("symbol") or symbol or "").upper()
        lines.append(f"━━━ {symbol or 'Entity'} — Command Assessment Result ━━━")
        if deep is not None:
            lines.append("")
            lines.append("▶ DEEP SEARCH")
            if deep.get("error"):
                lines.append(f"  Error: {deep.get('error')}")
            else:
                count = len(deep.get("results") or deep.get("items") or [])
                lines.append(f"  Symbol: {symbol}")
                lines.append(f"  Results: {count}")
                lines.append("  Framing: Entity and topic were resolved before routing.")
        if fno_chain is not None:
            lines.append("")
            lines.append("▶ OPTIONS")
            if fno_chain.get("error"):
                lines.append(f"  Error: {fno_chain.get('error')}")
            else:
                lines.append(f"  Symbol: {fno_chain.get('symbol', symbol)}")
                lines.append(f"  PCR: {fno_chain.get('pcr', 'n/a')}")
                lines.append(f"  Max pain: {fno_chain.get('max_pain', 'n/a')}")
        if latest_results is not None:
            lines.append("")
            lines.append("▶ Latest Results Evidence")
            lines.append(f"  Status: {latest_results.get('status', 'unknown')}")
            lines.append(f"  Period: {latest_results.get('period', 'latest')}")
            selected = latest_results.get("selected_filing") or {}
            if selected:
                lines.append(f"  Selected filing: {selected.get('title') or selected.get('url') or 'N/A'}")
            facts = latest_results.get("facts") or {}
            for label, key in (("Revenue", "revenue"), ("PAT", "pat"), ("EPS", "eps")):
                item = facts.get(key)
                if item:
                    lines.append(f"  {label}: {item.get('value')} ({item.get('period', 'latest')})")
            missing = latest_results.get("missing_facts") or []
            if missing:
                lines.append(f"  Missing facts: {', '.join(missing)}")
            if latest_results.get("summary"):
                lines.append("  Summary:")
                for line in str(latest_results.get("summary")).splitlines()[:6]:
                    lines.append(f"    {line}")
        if scr_fund is not None and (nse_ann is not None or bse_filings is not None or concalls is not None):
            lines.append("")
            _render_stock_results(symbol)
        lines.append("")
        lines.append("▶ SOURCE TRAIL")
        for tr in tool_results:
            result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
            status = f"ERROR: {result.get('error')}" if result.get("error") else "ok"
            lines.append(f"  {tr.get('tool')}: {status}")
            if tr.get("tool") == "get_latest_results" and isinstance(result.get("source_trail"), dict):
                for sub_tool, sub_status in result["source_trail"].items():
                    lines.append(f"  {sub_tool}: {sub_status}")
        lines.append("\n━━━ Not investment advice. For research and learning only. ━━━")
        return "\n".join(lines)

    if intent == "market_dashboard":
        def _fmt_pct(value) -> str:
            return f"{value:+.2f}%" if isinstance(value, (int, float)) else "n/a"

        def _fmt_num(value) -> str:
            return f"{value:,.2f}" if isinstance(value, (int, float)) else "n/a"

        indices = (live or {}).get("indices") or {}
        n50 = indices.get("NIFTY 50") or {}
        bank = indices.get("NIFTY BANK") or {}
        vix = indices.get("INDIA VIX") or {}
        mid = (
            indices.get("NIFTY MIDCAP SELECT")
            or indices.get("NIFTY MIDCAP 50")
            or indices.get("NIFTY MIDCAP 100")
            or {}
        )
        small = indices.get("NIFTY SMALLCAP 100") or indices.get("NIFTY SMALLCAP 250") or {}
        live_adv_dec = (live or {}).get("adv_dec") or {}

        index_rows = []
        for name, row in indices.items():
            if name.upper() == "INDIA VIX":
                continue
            pct = row.get("pct_change", row.get("chg_pct"))
            last = row.get("last", row.get("close"))
            if isinstance(pct, (int, float)):
                index_rows.append((name, pct, last))
        leaders = sorted(index_rows, key=lambda x: x[1], reverse=True)[:5]
        laggards = sorted(index_rows, key=lambda x: x[1])[:5]

        n50_pct = n50.get("pct_change", n50.get("chg_pct"))
        adv = live_adv_dec.get("advances")
        dec = live_adv_dec.get("declines")
        breadth_bias = "mixed"
        if isinstance(adv, (int, float)) and isinstance(dec, (int, float)):
            breadth_bias = "positive" if adv > dec else ("negative" if dec > adv else "flat")
        price_bias = "bullish" if isinstance(n50_pct, (int, float)) and n50_pct > 0.25 else (
            "bearish" if isinstance(n50_pct, (int, float)) and n50_pct < -0.25 else "range-bound"
        )
        global_regime = (glob or {}).get("risk_regime", "mixed")
        narrative_bias = (
            "constructive but selective"
            if price_bias == "bullish" and breadth_bias != "negative"
            else "defensive / risk-off"
            if price_bias == "bearish" and breadth_bias == "negative"
            else "mixed and breadth-sensitive"
        )

        lines.append("## Current Market Dashboard")
        if live and not live.get("error"):
            lines.append(f"Source: {live.get('source', 'NSE live API')} | As of: {live.get('as_of', '—')}")
        lines.append("")

        lines.append("### 1. Market Tape")
        for label, row in (
            ("NIFTY 50", n50),
            ("NIFTY BANK", bank),
            ("MIDCAP", mid),
            ("SMALLCAP", small),
            ("INDIA VIX", vix),
        ):
            last = row.get("last", row.get("close"))
            pct = row.get("pct_change", row.get("chg_pct"))
            if isinstance(last, (int, float)):
                lines.append(f"- {label}: {_fmt_num(last)} ({_fmt_pct(pct)})")
        if live_adv_dec:
            lines.append(f"- Live breadth: {live_adv_dec.get('advances', '—')} advances / {live_adv_dec.get('declines', '—')} declines ({breadth_bias}).")

        if leaders or laggards:
            lines.append("\n### 2. Index Leadership")
            if leaders:
                lines.append("- Leaders: " + " | ".join(f"{name} {_fmt_pct(pct)}" for name, pct, _ in leaders))
            if laggards:
                lines.append("- Laggards: " + " | ".join(f"{name} {_fmt_pct(pct)}" for name, pct, _ in laggards))

        if brd and not brd.get("error"):
            lines.append("\n### 3. Breadth & Internal Health")
            lines.append(
                f"- DB universe: {brd.get('advances', '—')} advances / {brd.get('declines', '—')} declines; "
                f"A/D ratio {brd.get('ad_ratio', '—')}."
            )
            if brd.get("avg_rs_pct") is not None:
                lines.append(f"- Average RS: {brd.get('avg_rs_pct'):+.1f}%.")
            sd = brd.get("stage_distribution") or {}
            if sd:
                stage_bits = []
                for key, label in (("STAGE_1", "Stage 1"), ("STAGE_2", "Stage 2"), ("STAGE_3", "Stage 3"), ("STAGE_4", "Stage 4")):
                    value = sd.get(key, sd.get(key.lower()))
                    if value is not None:
                        stage_bits.append(f"{label}: {int(value or 0)}")
                if stage_bits:
                    lines.append("- Stage mix: " + " | ".join(stage_bits))

        if movers and not movers.get("error"):
            gainers = movers.get("gainers") or []
            losers = movers.get("losers") or []
            lines.append("\n### 4. Stock Movers")
            if gainers:
                lines.append("- Top gainers: " + " | ".join(f"{r.get('symbol', '—')} {_fmt_pct(r.get('pct_change'))}" for r in gainers[:5]))
            if losers:
                lines.append("- Top losers: " + " | ".join(f"{r.get('symbol', '—')} {_fmt_pct(r.get('pct_change'))}" for r in losers[:5]))

        fii = _get("get_fii_dii_activity") or {}
        if fii and not fii.get("error"):
            lines.append("\n### 5. Flows")
            flow_parts = []
            for row in (fii.get("data") or [])[:4]:
                net = row.get("net_crore")
                net_txt = f"{net:+,.0f} Cr" if isinstance(net, (int, float)) else "n/a"
                flow_parts.append(f"{row.get('category', 'Flow')} {net_txt} ({row.get('sentiment', '—')})")
            if flow_parts:
                lines.append("- " + " | ".join(flow_parts))

        if glob and not glob.get("error"):
            lines.append("\n### 6. Global Read-through")
            lines.append(f"- Global risk regime: {global_regime}; as of {glob.get('as_of', '—')}.")
            readthrough = glob.get("india_readthrough") or []
            for item in readthrough[:4]:
                lines.append(f"- {item}")
            watch = glob.get("watch_items") or []
            if watch:
                lines.append("- Watch: " + " | ".join(watch[:3]))

        if cat and cat.get("results"):
            lines.append("\n### 7. Catalyst Tape")
            for r in cat.get("results", [])[:3]:
                title = (r.get("title") or "")[:110]
                url = r.get("url") or ""
                lines.append(f"- {title}" + (f" — {url}" if url else ""))

        lines.append("\n### 8. Narrative")
        lines.append(
            f"- Dashboard bias: {narrative_bias}. NIFTY tape is {price_bias}, breadth is {breadth_bias}, "
            f"and global regime is {global_regime}. Treat this as a situational map, not a trade signal."
        )
        if leaders:
            lines.append(f"- Leadership clue: strongest index bucket is {leaders[0][0]} ({_fmt_pct(leaders[0][1])}).")
        if laggards:
            lines.append(f"- Risk clue: weakest index bucket is {laggards[0][0]} ({_fmt_pct(laggards[0][1])}).")
        lines.append("- Operating plan: confirm with breadth expansion, sector leadership, and invalidation levels before acting.")

        lines.append("\n▶ SOURCE TRAIL")
        for tr in tool_results:
            result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
            status = f"ERROR: {result.get('error')}" if result.get("error") else "ok"
            lines.append(f"  {tr['tool']}: {status}")
        lines.append("\n━━━ Not investment advice. For research and learning only. ━━━")
        return "\n".join(l for l in lines if str(l).strip() != "")

    if intent == "market_situation_assessment":
        if (assessment_plan or {}).get("show_plan"):
            _render_assessment_plan(assessment_plan)

    if intent == "startup_morning_briefing":
        def _fmt_pct(value) -> str:
            return f"{value:+.2f}%" if isinstance(value, (int, float)) else "n/a"

        def _fmt_index_from_live(name: str) -> str:
            row = (live or {}).get("indices", {}).get(name) or {}
            last = row.get("last", row.get("close"))
            pct = row.get("pct_change", row.get("chg_pct"))
            if isinstance(last, (int, float)):
                return f"{name}: {last:,.2f} ({_fmt_pct(pct)})"
            return f"{name}: live level unavailable"

        index_snaps = [
            tr["result"] for tr in tool_results
            if tr["tool"] == "get_index_snapshot" and isinstance(tr.get("result"), dict)
        ]
        movers = _get("get_top_gainers_losers") or {}
        fii = _get("get_fii_dii_activity") or {}

        lines.append("## Good Morning — Market Intelligence Briefing")

        lines.append("\n### 🌍 Global Overnight Context")
        if glob and not glob.get("error"):
            lines.append(f"- Risk regime: {glob.get('risk_regime', '—')} as of {glob.get('as_of', '—')}.")
            regions = glob.get("regions") or {}
            if regions:
                lines.append(
                    "- Regional bias: "
                    + " | ".join(
                        f"{name} {data.get('bias', '—')} ({_fmt_pct(data.get('avg_pct_change'))})"
                        for name, data in regions.items()
                    )
                )
            moves = glob.get("moves") or {}
            key_assets = ["S&P 500", "Nasdaq", "Dow Jones", "Hang Seng", "Nikkei 225", "Shanghai Composite", "Crude Oil", "DXY", "USDINR"]
            key_moves = [
                f"{asset} {_fmt_pct(moves[asset].get('pct_change'))}"
                for asset in key_assets
                if asset in moves
            ]
            if key_moves:
                lines.append("- Key global moves: " + " | ".join(key_moves))
            for item in (glob.get("india_readthrough") or [])[:4]:
                lines.append(f"- India read-through: {item}")
        else:
            lines.append("- Global cached assessment unavailable; no unsupported inference added.")

        lines.append("\n### 📅 Previous Trading Day Recap (NSE)")
        if index_snaps:
            for row in index_snaps:
                if row.get("error"):
                    continue
                close = row.get("close")
                chg = row.get("chg_pct")
                if isinstance(close, (int, float)):
                    lines.append(f"- {row.get('index', 'Index')}: closed at {close:,.2f} ({_fmt_pct(chg)}).")
        if brd and not brd.get("error"):
            lines.append(
                f"- EOD universe breadth: {brd.get('advances', '—')} advances / "
                f"{brd.get('declines', '—')} declines; A/D ratio {brd.get('ad_ratio', '—')}."
            )

        lines.append("\n### 📊 Current Market Status")
        if live and not live.get("error"):
            lines.append(f"- {_fmt_index_from_live('NIFTY 50')}")
            lines.append(f"- {_fmt_index_from_live('NIFTY BANK')}")
            adv_dec = live.get("adv_dec") or {}
            if adv_dec:
                lines.append(f"- Live breadth: {adv_dec.get('advances', '—')} advances / {adv_dec.get('declines', '—')} declines.")
            lines.append(f"- Source: {live.get('source', 'NSE live API')} | As of: {live.get('as_of', '—')}.")
        else:
            lines.append("- Live NSE overview unavailable; using cached/EOD context only.")
        if fii and not fii.get("error"):
            flow_parts = []
            for row in fii.get("data", [])[:4]:
                net = row.get("net_crore")
                net_txt = f"{net:+,.2f} Cr" if isinstance(net, (int, float)) else "n/a"
                flow_parts.append(f"{row.get('category', 'Flow')} {net_txt} ({row.get('sentiment', '—')})")
            if flow_parts:
                lines.append("- FII/DII: " + " | ".join(flow_parts))

        if movers and not movers.get("error"):
            gainers = movers.get("gainers") or []
            losers = movers.get("losers") or []
            if gainers:
                lines.append("- Top NIFTY 50 gainers: " + ", ".join(f"{r.get('symbol')} {_fmt_pct(r.get('pct_change'))}" for r in gainers[:3]))
            if losers:
                lines.append("- Top NIFTY 50 losers: " + ", ".join(f"{r.get('symbol')} {_fmt_pct(r.get('pct_change'))}" for r in losers[:3]))

        lines.append("\n### 🎯 Today's Watchlist & Themes")
        watch_items = (glob or {}).get("watch_items") or []
        if watch_items:
            for item in watch_items[:4]:
                lines.append(f"- {item}")
        elif movers and not movers.get("error") and (movers.get("gainers") or movers.get("losers")):
            symbols = [r.get("symbol") for r in (movers.get("gainers") or [])[:2] + (movers.get("losers") or [])[:2] if r.get("symbol")]
            lines.append("- Monitor live movers for continuation/fade research: " + ", ".join(symbols))
        else:
            lines.append("- Monitor index breadth, FII/DII flows, USD/INR, crude, and high-volume NIFTY 50 movers.")

        if cat and cat.get("results"):
            lines.append("\n### 📰 Latest Source Trail")
            for r in cat["results"][:3]:
                title = (r.get("title") or "")[:110]
                url = r.get("url") or ""
                lines.append(f"- {title} — {url}" if url else f"- {title}")

        lines.append("\n### 🔬 Analyst's Take")
        regime = (glob or {}).get("risk_regime", "mixed")
        live_breadth = (live or {}).get("adv_dec") or {}
        breadth_text = (
            f"live breadth at {live_breadth.get('advances', '—')} advances vs {live_breadth.get('declines', '—')} declines"
            if live_breadth else "live breadth unavailable"
        )
        lines.append(
            f"- Bias is {regime}: combine the global cue with {breadth_text}, institutional flow, "
            "and NIFTY/BANKNIFTY levels before forming any intraday view. Keep position sizing and invalidation discipline explicit."
        )

        lines.append("\n### Follow-up questions")
        lines.append("1. `/global` — refresh the full global risk regime and India read-through.")
        lines.append("2. `/heat` — inspect live sector and breadth heatmap for leadership confirmation.")
        lines.append("3. `/scan NIFTY 50 vwap` — find intraday research setups with clear invalidation.")

        lines.append("\n▶ SOURCE TRAIL")
        for tr in tool_results:
            err = tr["result"].get("error", "") if isinstance(tr.get("result"), dict) else ""
            status = f"ERROR: {err}" if err else "ok"
            lines.append(f"  {tr['tool']}: {status}")
        lines.append("\n━━━ Not investment advice. For research and learning only. ━━━")
        return "\n".join(l for l in lines if str(l).strip() != "")

    if intent == "fno_overview":
        if fno_overview:
            def _fmt_oi_rows(rows: list[dict] | None) -> str:
                parts: list[str] = []
                for row in (rows or [])[:5]:
                    strike = row.get("strike", "—")
                    oi = next((row.get(k) for k in ("oi", "ce_oi", "pe_oi", "open_interest") if row.get(k) is not None), None)
                    chg = next((row.get(k) for k in ("chg_oi", "ce_oi_chg", "pe_oi_chg", "oi_change") if row.get(k) is not None), None)
                    oi_text = f"{int(oi):,}" if isinstance(oi, (int, float)) else str(oi or "—")
                    chg_text = ""
                    if isinstance(chg, (int, float)):
                        chg_text = f", chg {int(chg):+,}"
                    parts.append(f"{strike} (OI {oi_text}{chg_text})")
                return "; ".join(parts) if parts else "—"

            symbol = fno_overview.get("symbol") or "NIFTY"
            lines.append(f"━━━ {symbol} — F&O Overview ━━━")
            lines.append("\n▶ OPTION CHAIN")
            chain = fno_overview.get("option_chain") or {}
            if chain.get("status") == "missing" or chain.get("error"):
                lines.append(f"  ERROR: {chain.get('error') or 'option-chain evidence missing'}")
            else:
                lines.append(f"  PCR: {fno_overview.get('pcr', '—')} | Max pain: {fno_overview.get('max_pain', '—')}")
                top_oi = fno_overview.get("top_oi_strikes") or {}
                lines.append(f"  Top call OI: {_fmt_oi_rows(top_oi.get('calls'))}")
                lines.append(f"  Top put OI: {_fmt_oi_rows(top_oi.get('puts'))}")
            lines.append("\n▶ FUTURES BASIS & CARRY")
            futures = fno_overview.get("futures") or {}
            if futures.get("status") == "missing" or futures.get("error"):
                lines.append(f"  ERROR: {futures.get('error') or 'futures evidence missing'}")
            else:
                lines.append(f"  Basis: {fno_overview.get('basis', '—')} | Cost of carry: {fno_overview.get('cost_of_carry', '—')}")
            rec = fno_overview.get("recommendation") or {}
            lines.append("\n▶ STRATEGY CONTEXT")
            if rec.get("status") == "blocked":
                lines.append(f"  Blocked: {rec.get('reason')}")
            else:
                lines.append(f"  Strategy: {rec.get('strategy', '—')}")
                if rec.get("conditions"):
                    lines.append("  Conditions: " + " | ".join(map(str, rec.get("conditions") or [])))
                if rec.get("invalidation"):
                    lines.append(f"  Invalidation: {rec.get('invalidation')}")
                if rec.get("max_loss"):
                    lines.append(f"  Max loss: {rec.get('max_loss')}")
                if rec.get("max_profit"):
                    lines.append(f"  Max profit: {rec.get('max_profit')}")
            missing = fno_overview.get("missing_evidence") or []
            if missing:
                lines.append("\n▶ MISSING EVIDENCE")
                lines.append("  " + ", ".join(missing))
            lines.append("\n▶ SOURCE TRAIL")
            for tool, status in (fno_overview.get("source_trail") or {}).items():
                lines.append(f"  {tool}: {status}")
            lines.append("\n━━━ Not investment advice. For research and learning only. ━━━")
            return "\n".join(l for l in lines if str(l).strip() != "")

        def _fmt_num(value, decimals: int = 2) -> str:
            if isinstance(value, (int, float)):
                return f"{value:,.{decimals}f}"
            return "—"

        def _fmt_int(value) -> str:
            if isinstance(value, (int, float)):
                return f"{int(value):,}"
            return "—"

        def _fmt_oi_rows(rows: list[dict], side: str) -> str:
            if not rows:
                return "—"
            oi_key = "oi" if "oi" in rows[0] else ("ce_oi" if side == "CE" else "pe_oi")
            chg_key = "chg_oi" if "chg_oi" in rows[0] else ("ce_oi_chg" if side == "CE" else "pe_oi_chg")
            top = sorted(rows, key=lambda row: row.get(oi_key) or 0, reverse=True)[:5]
            parts = []
            for row in top:
                strike = row.get("strike", "—")
                oi = _fmt_int(row.get(oi_key))
                chg = row.get(chg_key)
                chg_txt = f", chg {int(chg):+,}" if isinstance(chg, (int, float)) else ""
                parts.append(f"{strike}: OI {oi}{chg_txt}")
            return " | ".join(parts)

        symbol = (
            (fno_chain or {}).get("symbol")
            or (fno_futures or {}).get("symbol")
            or (fno_strategy or {}).get("symbol")
            or "NIFTY"
        )
        lines.append(f"━━━ {symbol} — F&O Overview ━━━")

        if fno_chain and not fno_chain.get("error"):
            pcr = fno_chain.get("pcr")
            if isinstance(pcr, dict):
                pcr_text = f"OI {pcr.get('oi', '—')} | Volume {pcr.get('volume', '—')} | {pcr.get('signal', '—')}"
            else:
                pcr_text = str(pcr if pcr is not None else "—")
            lines.append("\n▶ OPTION CHAIN")
            lines.append(
                f"  Expiry: {fno_chain.get('expiry', '—')} | "
                f"Spot/underlying: {_fmt_num(fno_chain.get('underlying'))} | "
                f"ATM: {fno_chain.get('atm', '—')} | Source: {fno_chain.get('source', 'NSE live/API fallback')} | "
                f"As of: {fno_chain.get('as_of', '—')}"
            )
            lines.append(f"  PCR: {pcr_text} | Max pain: {fno_chain.get('max_pain', '—')}")
            if fno_chain.get("total_call_oi") is not None or fno_chain.get("total_put_oi") is not None:
                lines.append(
                    f"  Total OI: Calls {_fmt_int(fno_chain.get('total_call_oi'))} | "
                    f"Puts {_fmt_int(fno_chain.get('total_put_oi'))}"
                )
            calls = fno_chain.get("calls") or fno_chain.get("top_ce_oi_strikes") or []
            puts = fno_chain.get("puts") or fno_chain.get("top_pe_oi_strikes") or []
            lines.append(f"  Top CE OI / resistance zones: {_fmt_oi_rows(calls, 'CE')}")
            lines.append(f"  Top PE OI / support zones: {_fmt_oi_rows(puts, 'PE')}")
            if fno_chain.get("max_pain_vs_spot") is not None:
                lines.append(f"  Max pain vs spot: {_fmt_num(fno_chain.get('max_pain_vs_spot'))}")
        elif fno_chain:
            lines.append(f"\n▶ OPTION CHAIN\n  ERROR: {fno_chain.get('error')}")

        if fno_futures and not fno_futures.get("error"):
            lines.append("\n▶ FUTURES BASIS & CARRY")
            lines.append(
                f"  Spot: {_fmt_num(fno_futures.get('spot'))} | "
                f"Lot size: {fno_futures.get('lot_size', '—')} | "
                f"Source: {fno_futures.get('source', '—')} | As of: {fno_futures.get('as_of', '—')}"
            )
            for fut in (fno_futures.get("futures") or [])[:3]:
                lines.append(
                    f"  - Expiry {fut.get('expiry', '—')}: future {_fmt_num(fut.get('last_price') or fut.get('settle_price'))} | "
                    f"basis {_fmt_num(fut.get('basis'))} ({_fmt_num(fut.get('basis_pct'), 3)}%) | "
                    f"CoC {_fmt_num(fut.get('cost_of_carry_annualised_pct'))}% | "
                    f"OI {_fmt_int(fut.get('oi'))} | OI chg {_fmt_int(fut.get('oi_change'))}"
                )
            rollover = fno_futures.get("rollover") or {}
            if rollover:
                lines.append(
                    f"  Rollover: {rollover.get('rollover_pct', '—')}% | "
                    f"{rollover.get('interpretation', '—')}"
                )
        elif fno_futures:
            lines.append(f"\n▶ FUTURES BASIS & CARRY\n  ERROR: {fno_futures.get('error')}")

        if fno_strategy and not fno_strategy.get("error"):
            lines.append("\n▶ STRATEGY CONTEXT")
            lines.append(
                f"  IV regime: {fno_strategy.get('iv_regime', '—')} | "
                f"DTE: {fno_strategy.get('dte', '—')} | "
                f"PCR OI: {fno_strategy.get('pcr_oi', '—')} | "
                f"Max pain: {fno_strategy.get('max_pain', '—')}"
            )
            for rec in (fno_strategy.get("recommendations") or [])[:3]:
                name = rec.get("strategy") or rec.get("name") or rec.get("title") or "strategy"
                reason = rec.get("rationale") or rec.get("reason") or rec.get("why") or ""
                lines.append(f"  - {name}: {reason}".rstrip())
        elif fno_strategy:
            lines.append(f"\n▶ STRATEGY CONTEXT\n  ERROR: {fno_strategy.get('error')}")

        lines.append("\n▶ SOURCE TRAIL")
        for tr in tool_results:
            result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
            status = f"ERROR: {result.get('error')}" if result.get("error") else "ok"
            lines.append(f"  {tr['tool']}: {status}")
        lines.append("\n━━━ Not investment advice. For research and learning only. ━━━")
        return "\n".join(l for l in lines if str(l).strip() != "")

    if forensic:
        fsym = forensic.get("symbol") or sym or "SYMBOL"
        lines.append(f"━━━ {fsym} — FORENSIC ACCOUNTING ANALYSIS ━━━")
        if forensic.get("error"):
            lines.append(f"\n▶ ERROR\n  {forensic.get('error')}")
        else:
            beneish = forensic.get("beneish") or {}
            piotroski = forensic.get("piotroski") or {}
            altman = forensic.get("altman") or {}
            lines.append(f"Overall forensic risk: {str(forensic.get('overall_risk', 'unknown')).upper()}")
            if forensic.get("source_url"):
                lines.append(f"Source: {forensic.get('source_url')}")

            lines.append("\n▶ Beneish M-score")
            lines.append(
                f"  Score: {beneish.get('score', '—')} | "
                f"Interpretation: {beneish.get('interpretation', '—')}"
            )
            risk_flags = beneish.get("risk_flags") or []
            lines.append("  Flagged variables: " + (", ".join(map(str, risk_flags)) if risk_flags else "None reported"))
            variables = beneish.get("variables") or beneish.get("components") or {}
            for name, value in list(variables.items())[:10]:
                lines.append(f"    - {name}: {value}")

            lines.append("\n▶ Piotroski F-score")
            max_possible = piotroski.get("max_possible", 9)
            lines.append(
                f"  Score: {piotroski.get('score', '—')}/{max_possible} | "
                f"Financial health: {piotroski.get('strength') or piotroski.get('interpretation', '—')}"
            )
            signals = piotroski.get("signals") or piotroski.get("components") or {}
            for name, value in list(signals.items())[:12]:
                verdict = "pass" if value in {1, True, "pass", "PASS"} else "fail" if value in {0, False, "fail", "FAIL"} else value
                lines.append(f"    - {name}: {verdict}")

            lines.append("\n▶ Altman Z'-score")
            lines.append(
                f"  Score: {altman.get('score', '—')} | "
                f"Zone: {altman.get('zone') or altman.get('interpretation', '—')}"
            )
            components = altman.get("components") or {}
            for name, value in list(components.items())[:8]:
                lines.append(f"    - {name}: {value}")

            if forensic.get("summary"):
                lines.append("\n▶ SUMMARY")
                for line in str(forensic["summary"]).splitlines():
                    lines.append(f"  {line}")

        # ── TECHNICAL SETUP (for /analyze 360°) ─────────────────────────────
        if tech and isinstance(tech, dict) and not tech.get("error"):
            lines.append("\n━━━ TECHNICAL SETUP ━━━")
            if tech.get("technical_score") is not None:
                lines.append(
                    f"  Derived score: {tech.get('technical_score')} "
                    f"({tech.get('score_method', 'derived')})"
                )
            lines.append(f"  RSI:        {tech.get('rsi', '—')}")
            lines.append(f"  ADX:        {tech.get('adx', '—')}  (>25 = trending)")
            lines.append(f"  MACD:       {tech.get('macd', '—')}")
            lines.append(f"  Supertrend: {tech.get('supertrend', '—')}")
            ma_flags = []
            if tech.get("above_sma20"):
                ma_flags.append("▲ SMA20")
            if tech.get("above_sma50"):
                ma_flags.append("▲ SMA50")
            if tech.get("above_sma200"):
                ma_flags.append("▲ SMA200")
            lines.append(f"  MAs:        {' | '.join(ma_flags) or '— below key MAs'}")
            h52, l52, pct = tech.get("52w_high"), tech.get("52w_low"), tech.get("pct_from_52h")
            if h52 and l52:
                pct_txt = f"  ({pct:+.1f}% from high)" if isinstance(pct, (int, float)) else ""
                lines.append(f"  52W Range:  ₹{l52:,.0f} – ₹{h52:,.0f}{pct_txt}")
            vr = tech.get("vol_ratio")
            if isinstance(vr, (int, float)):
                lines.append(f"  Volume:     {vr:.1f}x avg")
            if tech.get("stage"):
                lines.append(f"  Stage:      {tech.get('stage')}")
            if tech.get("trend_signal"):
                lines.append(f"  Trend:      {tech.get('trend_signal')}")

        # ── SECTOR CONTEXT (for /analyze 360°) ──────────────────────────────
        if sec and isinstance(sec, dict) and not sec.get("error"):
            lines.append("\n━━━ SECTOR CONTEXT ━━━")
            lines.append(f"  Sector:         {sec.get('sector', '—')}")
            lines.append(f"  Stocks in DB:   {sec.get('total_stocks', '—')}")
            lines.append(f"  Stage 2 count:  {sec.get('stage2_count', '—')}")
            lines.append(f"  Buy signals:    {sec.get('buy_signals', '—')}")
            avg_rs = sec.get("avg_rs_pct")
            if isinstance(avg_rs, (int, float)):
                lines.append(f"  Avg RS:         {avg_rs:+.1f}%")
            avg_1m = sec.get("avg_1m_pct")
            if isinstance(avg_1m, (int, float)):
                lines.append(f"  Avg 1M chg:     {avg_1m:+.2f}%")
            top5 = sec.get("top5_by_score") or []
            if top5:
                lines.append(
                    "  Top peers:      "
                    + ", ".join(str(s.get("symbol", "?")) for s in top5[:5])
                )

        # ── LATEST CATALYSTS (for /analyze 360°) ────────────────────────────
        if cat and isinstance(cat, dict) and (cat.get("results") or []):
            lines.append("\n━━━ LATEST CATALYSTS ━━━")
            for r in (cat.get("results") or [])[:5]:
                if not isinstance(r, dict):
                    continue
                title = str(r.get("title") or "")[:100]
                url = str(r.get("url") or "")
                snippet = str(r.get("snippet") or "")[:140]
                lines.append(f"  • {title}")
                if url:
                    lines.append(f"    {url}")
                if snippet:
                    lines.append(f"    {snippet}")
            sentiment = cat.get("sentiment") or cat.get("overall_sentiment")
            if sentiment:
                lines.append(f"  Sentiment: {sentiment}")

        # ── INSTITUTIONAL & INSIDER (screener shareholding + deep_search) ───
        section_lines: list[str] = []
        shp_src = (scr_fund or {}).get("shareholding") if isinstance(scr_fund, dict) else None
        if isinstance(shp_src, dict) and shp_src:
            for label, keys in (
                ("Promoters", ("Promoters", "Promoter")),
                ("FII",       ("FIIs", "FII")),
                ("DII",       ("DIIs", "DII")),
                ("Government",("Government",)),
                ("Public",    ("Public",)),
            ):
                v = None
                for k in keys:
                    if shp_src.get(k) not in (None, ""):
                        v = shp_src.get(k); break
                if v is not None:
                    trend = shp_src.get(f"{keys[0]}_trend") or shp_src.get(f"{label}_trend")
                    extra = ""
                    if isinstance(trend, list) and len(trend) >= 2:
                        extra = f"  (trend: {' → '.join(str(t) for t in trend[-4:])})"
                    section_lines.append(f"  {label:<11} {v}{extra}")
            quarters = shp_src.get("_quarters")
            if isinstance(quarters, list) and quarters:
                section_lines.append(f"  Quarters covered: {quarters[0]} → {quarters[-1]}")
        if deep and isinstance(deep, dict) and not deep.get("error"):
            verticals = deep.get("verticals") or deep.get("data") or {}
            if isinstance(verticals, dict):
                insider = verticals.get("insider_trades") or verticals.get("insiders") or []
                if isinstance(insider, list) and insider:
                    section_lines.append("  Recent insider activity:")
                    for entry in insider[:3]:
                        if isinstance(entry, dict):
                            txt = entry.get("summary") or entry.get("description") or str(entry)
                            section_lines.append(f"    • {str(txt)[:140]}")
                targets = verticals.get("analyst_targets") or verticals.get("targets") or []
                if isinstance(targets, list) and targets:
                    section_lines.append("  Analyst targets:")
                    for entry in targets[:3]:
                        if isinstance(entry, dict):
                            txt = entry.get("summary") or entry.get("target") or str(entry)
                            section_lines.append(f"    • {str(txt)[:140]}")
            if section_lines:
                lines.append("\n━━━ INSTITUTIONAL & INSIDER ACTIVITY ━━━")
                lines.extend(section_lines)

        # ── FUNDAMENTAL ANALYSIS (for /analyze 360°) ────────────────────────
        # /analyze runs comprehensive_stock_research which carries screener.in
        # fundamentals under result["screener"] (already backfilled into
        # scr_fund above). Surface ratios, P&L trend, pros/cons here so the
        # user sees fundamentals alongside the forensic block.
        if scr_fund and isinstance(scr_fund, dict) and not scr_fund.get("error"):
            ratios_f = scr_fund.get("ratios") or {}
            q_f = scr_fund.get("quarterly") or {}
            annual_f = scr_fund.get("annual_pl") or {}
            pros_f = scr_fund.get("pros") or []
            cons_f = scr_fund.get("cons") or []

            fund_lines: list[str] = []

            if isinstance(ratios_f, dict) and ratios_f:
                def _norm_key(k: str) -> str:
                    return str(k).strip().rstrip("+").strip().lower()
                key_ratios = [
                    ("Market Cap", ("Market Cap",)),
                    ("Current Price", ("Current Price",)),
                    ("Stock P/E", ("Stock P/E", "P/E")),
                    ("Industry P/E", ("Industry PE", "Industry P/E")),
                    ("Book Value", ("Book Value",)),
                    ("Price to Book", ("Price to book value", "P/B")),
                    ("Dividend Yield", ("Dividend Yield",)),
                    ("ROCE", ("ROCE", "Return on capital employed")),
                    ("ROE", ("ROE", "Return on equity")),
                    ("Debt to Equity", ("Debt to equity",)),
                    ("Sales Growth 3Y", ("Sales growth 3Years", "Compounded Sales Growth 3Years")),
                    ("Profit Growth 3Y", ("Profit growth 3Years", "Compounded Profit Growth 3Years")),
                    ("Promoter Holding", ("Promoter holding",)),
                    ("FII Holding", ("FII holding",)),
                ]
                rendered_ratio_rows: list[tuple[str, str]] = []
                norm_ratios = {_norm_key(k): v for k, v in ratios_f.items()}
                for label, keys in key_ratios:
                    val = None
                    for k in keys:
                        v = norm_ratios.get(_norm_key(k))
                        if v not in (None, "", "—"):
                            val = v
                            break
                    if val not in (None, "", "—"):
                        rendered_ratio_rows.append((label, str(val)))
                if rendered_ratio_rows:
                    fund_lines.append("\n▶ KEY RATIOS")
                    for label, val in rendered_ratio_rows:
                        fund_lines.append(f"  - {label}: {val}")

            q_headers_f = q_f.get("_headers") if isinstance(q_f, dict) else []
            if q_headers_f:
                qmetrics = []
                for labels in (
                    ("Sales", "Revenue", "Operating Revenue"),
                    ("Operating Profit",),
                    ("OPM %",),
                    ("Net Profit", "Profit after tax", "PAT"),
                    ("EPS in Rs", "EPS"),
                ):
                    wanted = {l.strip().lower() for l in labels}
                    for key, values in q_f.items():
                        if str(key).startswith("_"):
                            continue
                        norm_k = str(key).strip().rstrip("+").strip().lower()
                        if norm_k in wanted and isinstance(values, list):
                            if any(str(v).strip() for v in values):
                                qmetrics.append((str(key).rstrip("+").strip(), values))
                                break
                if qmetrics:
                    fund_lines.append("\n▶ QUARTERLY P&L (₹ Cr — last 6 quarters)")
                    hdrs = [str(h) for h in q_headers_f[-6:]]
                    fund_lines.append("  | Metric              | " + " | ".join(f"{h:>10}" for h in hdrs) + " |")
                    fund_lines.append("  |---------------------|" + ("------------|" * len(hdrs)))
                    for label, values in qmetrics:
                        vals = list(values)
                        if vals and isinstance(vals[0], str) and vals[0].strip().rstrip("+").strip().lower() == label.strip().lower():
                            vals = vals[1:]
                        tail = vals[-len(hdrs):] if len(vals) >= len(hdrs) else vals
                        padded = [""] * (len(hdrs) - len(tail)) + list(tail)
                        cells = " | ".join(f"{str(v or '—'):>10}" for v in padded)
                        fund_lines.append(f"  | {str(label)[:19]:<19} | {cells} |")

            annual_headers_f = annual_f.get("_headers") if isinstance(annual_f, dict) else []
            if annual_headers_f:
                ametrics = []
                for labels in (
                    ("Sales", "Revenue"),
                    ("Net Profit", "Profit after tax", "PAT"),
                    ("EPS in Rs", "EPS"),
                ):
                    wanted = {l.strip().lower() for l in labels}
                    for key, values in annual_f.items():
                        if str(key).startswith("_"):
                            continue
                        norm_k = str(key).strip().rstrip("+").strip().lower()
                        if norm_k in wanted and isinstance(values, list):
                            if any(str(v).strip() for v in values):
                                ametrics.append((str(key).rstrip("+").strip(), values))
                                break
                if ametrics:
                    fund_lines.append("\n▶ ANNUAL P&L (₹ Cr — last 5 years)")
                    hdrs = [str(h) for h in annual_headers_f[-5:]]
                    fund_lines.append("  | Metric              | " + " | ".join(f"{h:>10}" for h in hdrs) + " |")
                    fund_lines.append("  |---------------------|" + ("------------|" * len(hdrs)))
                    for label, values in ametrics:
                        vals = list(values)
                        if vals and isinstance(vals[0], str) and vals[0].strip().rstrip("+").strip().lower() == label.strip().lower():
                            vals = vals[1:]
                        tail = vals[-len(hdrs):] if len(vals) >= len(hdrs) else vals
                        padded = [""] * (len(hdrs) - len(tail)) + list(tail)
                        cells = " | ".join(f"{str(v or '—'):>10}" for v in padded)
                        fund_lines.append(f"  | {str(label)[:19]:<19} | {cells} |")

            if pros_f or cons_f:
                fund_lines.append("\n▶ SCREENER ANALYSIS")
                if pros_f:
                    fund_lines.append("  Pros:")
                    for p in pros_f[:5]:
                        fund_lines.append(f"    • {p}")
                if cons_f:
                    fund_lines.append("  Cons:")
                    for c in cons_f[:5]:
                        fund_lines.append(f"    • {c}")

            if fund_lines:
                lines.append("\n━━━ FUNDAMENTAL ANALYSIS ━━━")
                lines.extend(fund_lines)
                if scr_fund.get("source_url"):
                    lines.append(f"\nSource: {scr_fund.get('source_url')}")

        lines.append("\n▶ SOURCE TRAIL")
        for tr in tool_results:
            result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
            status = f"ERROR: {result.get('error')}" if result.get("error") else "ok"
            lines.append(f"  {tr['tool']}: {status}")
        lines.append("\n━━━ Not investment advice. For research and learning only. ━━━")
        return "\n".join(l for l in lines if str(l).strip() != "")

    if sym:
        lines.append(f"━━━ {cname} ({sym}) — Market Brief ━━━")
        snap_date = (snap or {}).get("snapshot_date", "N/A")
        lines.append(f"Data: EOD snapshot {snap_date}\n")

    if market_recap and not market_recap.get("error"):
        minutes = market_recap.get("minutes", 15)
        lines.append(f"━━━ Last {minutes} Minutes — Market Recap ━━━")
        lines.append(f"  {market_recap.get('narrative', 'Live market recap unavailable.')}")
        rows = market_recap.get("rows") or []
        if rows:
            lines.append("\n▶ INDEX TAPE")
            for row in rows:
                current = row.get("current")
                day_pct = row.get("current_pct_change")
                interval_pct = row.get("interval_pct_change")
                points = row.get("point_change")
                if current is None:
                    continue
                interval_text = (
                    f" | {points:+.2f} pts ({interval_pct:+.2f}%) vs stored {minutes}m tape"
                    if isinstance(points, (int, float)) and isinstance(interval_pct, (int, float))
                    else " | no earlier stored tape"
                )
                day_text = f" ({day_pct:+.2f}% day)" if isinstance(day_pct, (int, float)) else ""
                lines.append(f"  {row.get('symbol')}: {float(current):,.2f}{day_text}{interval_text}")
        adv_dec = market_recap.get("adv_dec") or {}
        if adv_dec:
            lines.append(
                f"\n▶ LIVE BREADTH\n  {adv_dec.get('advances', '—')} advances / "
                f"{adv_dec.get('declines', '—')} declines"
            )
        lines.append(f"\nSource: {market_recap.get('source', 'NSE live API')} | As of: {market_recap.get('as_of', '—')}")

    if strength and not strength.get("error"):
        lines.append("━━━ Validated Multi-Factor Strength ━━━")
        lines.append(f"Data: EOD snapshot {strength.get('snapshot_date') or 'N/A'}")
        lines.append(strength.get("validation_rule", "Missing evidence is not inferred."))
        for row in strength.get("results", [])[:10]:
            score = row.get("strength_score")
            score_txt = f"{score:.1f}" if isinstance(score, (int, float)) else "N/A"
            piot = row.get("piotroski_score")
            piot_txt = f"{piot}/{row.get('piotroski_max')}" if piot is not None else "N/A"
            missing = row.get("missing_evidence") or []
            lines.append(
                f"- {row.get('symbol')}: score {score_txt}; "
                f"CANSLIM {row.get('can_slim_score') or 'N/A'}; "
                f"RS {row.get('rs_pct') if row.get('rs_pct') is not None else 'N/A'}; "
                f"Fund {row.get('enhanced_fund_score') or 'N/A'}; "
                f"Piotroski {piot_txt}; "
                f"Risk {row.get('overall_forensic_risk') or 'unknown'}; "
                f"{row.get('verdict')}"
            )
            if missing:
                lines.append(f"  Missing evidence: {', '.join(missing)}")
        lines.append("\n━━━ Not investment advice. For research and learning only. ━━━")
        return "\n".join([ln for ln in lines if ln is not None])

    if comparison and not comparison.get("error"):
        lines.append("▶ STOCK COMPARISON")
        lines.append(f"  Symbols: {', '.join(comparison.get('symbols') or [])}")
        lines.append(f"  Aspects: {', '.join(comparison.get('aspects') or [])}")
        for row in (comparison.get("stock_details") or [])[:6]:
            bits = [
                str(row.get("symbol", "—")),
                f"stage {row.get('stage', '—')}",
                f"tech {row.get('technical_score', '—')}",
                f"RS {row.get('rs_pct', '—')}",
                f"signal {row.get('trading_signal', '—')}",
                f"sector {row.get('sector', '—')}",
            ]
            if row.get("pe") is not None:
                bits.append(f"P/E {row.get('pe')}")
            if row.get("roe") is not None:
                bits.append(f"ROE {row.get('roe')}")
            lines.append("  - " + " | ".join(bits))

    if portfolio_narratives and not portfolio_narratives.get("error"):
        lines.append("▶ PORTFOLIO REVIEW")
        for row in (portfolio_narratives.get("narratives") or [])[:10]:
            if row.get("error"):
                lines.append(f"  - {row.get('symbol')}: ERROR {row.get('error')}")
                continue
            lines.append(
                f"  - {row.get('symbol')}: stage {row.get('stage', '—')} | "
                f"RSI {row.get('rsi', '—')} | action {row.get('action_hint', '—')}"
            )
            if row.get("thesis"):
                lines.append(f"    thesis: {row.get('thesis')}")
            if row.get("bear_case"):
                lines.append(f"    risk: {row.get('bear_case')}")

    if event_calendar and not event_calendar.get("error"):
        lines.append("▶ EVENT CALENDAR")
        lines.append(
            f"  Index: {event_calendar.get('index', '—')} | "
            f"Window: {event_calendar.get('days_ahead', '—')} days | "
            f"Total events: {event_calendar.get('total_events', '—')}"
        )
        counts = event_calendar.get("event_counts") or {}
        if counts:
            lines.append("  Event mix: " + " | ".join(f"{k}: {v}" for k, v in counts.items()))
        events = event_calendar.get("events") or []
        if events:
            lines.append("  Upcoming:")
            for ev in events[:10]:
                lines.append(
                    f"    - {ev.get('symbol', '—')} | {ev.get('type', '—')} | "
                    f"{ev.get('ex_date', '—')} | {ev.get('detail', '—')}"
                )

    if knowledge:
        answer = knowledge.get("answer_markdown")
        if answer:
            return str(answer)
        if knowledge.get("error"):
            return f"No reliable Investopedia or Wikipedia source was found: {knowledge['error']}"

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
        if snap.get("missing_evidence"):
            lines.append(f"  Missing evidence: {', '.join(snap.get('missing_evidence') or [])}")

    # 2. Technical Setup
    if tech and not tech.get("error"):
        lines.append("\n▶ TECHNICAL SETUP")
        if tech.get("technical_score") is not None:
            lines.append(f"  Derived score: {tech.get('technical_score')} ({tech.get('score_method', 'derived')})")
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

    # 3b. Screener.in Fundamentals — ratios, quarterly P&L, annual P&L, peers,
    # latest BSE filings. Activated when scrape_screener_in / search_nse_announcements
    # were run (results/financials/quarterly queries).
    if scr_fund and not scr_fund.get("error"):
        ratios = scr_fund.get("ratios") or {}
        if ratios:
            lines.append("\n▶ FUNDAMENTAL RATIOS (screener.in)")
            key_order = [
                "Market Cap", "Current Price", "High / Low", "Stock P/E",
                "Book Value", "Dividend Yield", "ROCE", "ROE",
                "Face Value", "Industry PE", "Debt to equity",
                "PEG Ratio", "EPS", "Promoter holding",
            ]
            shown = 0
            for k in key_order:
                v = ratios.get(k)
                if v:
                    lines.append(f"  {k:<18} {v}")
                    shown += 1
            # Include any remaining ratios not in our preferred order
            for k, v in ratios.items():
                if k in key_order or not v:
                    continue
                lines.append(f"  {k:<18} {v}")
                shown += 1
                if shown >= 18:
                    break

        quarterly = scr_fund.get("quarterly") or {}
        q_headers = quarterly.get("_headers") if isinstance(quarterly, dict) else None
        q_rows = {k: v for k, v in (quarterly or {}).items() if k != "_headers"} if isinstance(quarterly, dict) else {}
        if q_headers and q_rows:
            lines.append("\n▶ QUARTERLY RESULTS (₹ Cr — last 6 quarters)")
            lines.append("  | Metric              | " + " | ".join(f"{h:>10}" for h in q_headers) + " |")
            lines.append("  |" + "-" * 22 + "|" + ("-" * 12 + "|") * len(q_headers))
            priority = ("Sales", "Sales+", "Revenue", "Expenses", "Expenses+",
                        "Operating Profit", "OPM %", "Net Profit", "Net Profit+", "EPS in Rs")
            ordered = [k for k in priority if k in q_rows] + [k for k in q_rows if k not in priority]
            for metric in ordered[:10]:
                vals = q_rows.get(metric) or []
                cells = " | ".join(f"{(v or '—'):>10}" for v in (vals[:len(q_headers)] + [""] * (len(q_headers) - len(vals))))
                lines.append(f"  | {metric[:18]:<18} | {cells} |")

        annual = scr_fund.get("annual_pl") or {}
        a_headers = annual.get("_headers") if isinstance(annual, dict) else None
        a_rows = {k: v for k, v in (annual or {}).items() if k != "_headers"} if isinstance(annual, dict) else {}
        if a_headers and a_rows:
            lines.append("\n▶ ANNUAL P&L (₹ Cr — last 5 years)")
            lines.append("  | Metric              | " + " | ".join(f"{h:>10}" for h in a_headers) + " |")
            lines.append("  |" + "-" * 22 + "|" + ("-" * 12 + "|") * len(a_headers))
            priority = ("Sales", "Sales+", "Revenue", "Expenses", "Expenses+",
                        "Operating Profit", "OPM %", "Net Profit", "Net Profit+", "EPS in Rs", "Dividend Payout %")
            ordered = [k for k in priority if k in a_rows] + [k for k in a_rows if k not in priority]
            for metric in ordered[:10]:
                vals = a_rows.get(metric) or []
                cells = " | ".join(f"{(v or '—'):>10}" for v in (vals[:len(a_headers)] + [""] * (len(a_headers) - len(vals))))
                lines.append(f"  | {metric[:18]:<18} | {cells} |")

        pros = scr_fund.get("pros") or []
        cons = scr_fund.get("cons") or []
        if pros or cons:
            lines.append("\n▶ SCREENER ANALYSIS")
            if pros:
                lines.append("  Pros:")
                for p in pros[:4]:
                    lines.append(f"    • {p}")
            if cons:
                lines.append("  Cons:")
                for c in cons[:4]:
                    lines.append(f"    • {c}")

        peers = scr_fund.get("peers") or []
        if peers:
            lines.append("\n▶ PEER COMPARISON")
            for p in peers[:5]:
                name = p.get("Name") or p.get("S.No.") or "—"
                pe   = p.get("P/E") or p.get("PE") or "—"
                mcap = p.get("Mar Cap Rs.Cr.") or p.get("Mar Cap") or "—"
                roe  = p.get("ROCE %") or p.get("ROE") or "—"
                lines.append(f"  - {str(name)[:24]:<24} | P/E {pe:>8} | M-Cap {mcap:>10} | ROCE {roe:>6}")

        shp = scr_fund.get("shareholding") or {}
        if shp:
            promo = shp.get("Promoters") or shp.get("Promoter")
            fii   = shp.get("FIIs") or shp.get("FII")
            dii   = shp.get("DIIs") or shp.get("DII")
            if any([promo, fii, dii]):
                lines.append("\n▶ SHAREHOLDING (latest)")
                if promo: lines.append(f"  Promoters: {promo}")
                if fii:   lines.append(f"  FII:       {fii}")
                if dii:   lines.append(f"  DII:       {dii}")

        announcements = scr_fund.get("announcements") or []
        if announcements:
            lines.append("\n▶ RECENT FILINGS (BSE)")
            for a in announcements[:5]:
                title = (a.get("title") or "")[:80]
                url = a.get("url") or ""
                lines.append(f"  • {title}")
                if url:
                    lines.append(f"    {url}")

        src = scr_fund.get("source_url")
        if src:
            lines.append(f"\n  Source: {src}")

    # 3c. Latest NSE / BSE corporate announcements (when search_nse_announcements ran)
    if nse_ann and not nse_ann.get("error"):
        items = nse_ann.get("announcements") or nse_ann.get("results") or []
        if items:
            lines.append("\n▶ NSE/BSE ANNOUNCEMENTS")
            for a in items[:5]:
                title = (a.get("subject") or a.get("title") or "")[:90]
                date  = a.get("date") or a.get("dt") or ""
                url   = a.get("url") or a.get("link") or a.get("pdf") or ""
                lines.append(f"  • [{date}] {title}")
                if url:
                    lines.append(f"    {url}")

    # 4. Live market overview / Index / breadth
    if live and not live.get("error"):
        lines.append("\n▶ LIVE MARKET")
        indices = live.get("indices") or {}
        for index_name in ("NIFTY 50", "NIFTY BANK", "NIFTY MIDCAP SELECT", "NIFTY MIDCAP 50", "NIFTY MIDCAP 100"):
            row = indices.get(index_name)
            if not row:
                continue
            last = row.get("last", row.get("close"))
            pct = row.get("pct_change", row.get("chg_pct"))
            if isinstance(last, (int, float)):
                pct_txt = f"  ({pct:+.2f}%)" if isinstance(pct, (int, float)) else ""
                lines.append(f"  {index_name}: {last:,.2f}{pct_txt}")
        adv_dec = live.get("adv_dec") or {}
        if adv_dec:
            lines.append(
                f"  Live breadth: {adv_dec.get('advances', '—')} advances / "
                f"{adv_dec.get('declines', '—')} declines"
            )
        if live.get("as_of") or live.get("source"):
            lines.append(f"  Source: {live.get('source', 'NSE live API')} | As of: {live.get('as_of', '—')}")

        top_sectors = live.get("top_sectors") or []
        bottom_sectors = live.get("bottom_sectors") or []
        if (top_sectors or bottom_sectors) and intent in {"market_overview", "market_situation_assessment"}:
            lines.append("\n▶ SECTOR STRENGTH")
            if top_sectors:
                lines.append("  Leading sectors: " + " | ".join(
                    f"{row.get('name', '—')} {float(row.get('pct_change') or 0):+.2f}%"
                    for row in top_sectors[:5]
                ))
            if bottom_sectors:
                lines.append("  Weak sectors: " + " | ".join(
                    f"{row.get('name', '—')} {float(row.get('pct_change') or 0):+.2f}%"
                    for row in bottom_sectors[:5]
                ))

        index_rows = []
        for name, row in indices.items():
            pct = row.get("pct_change", row.get("chg_pct"))
            last = row.get("last", row.get("close"))
            if isinstance(pct, (int, float)):
                index_rows.append((name, pct, last))
        if index_rows and intent in {"market_overview", "market_situation_assessment"}:
            leaders = sorted(index_rows, key=lambda x: x[1], reverse=True)[:5]
            laggards = sorted(index_rows, key=lambda x: x[1])[:5]
            lines.append("\n▶ INDEX MOVERS")
            lines.append("  Top indices: " + " | ".join(
                f"{name} {pct:+.2f}%" for name, pct, _ in leaders
            ))
            lines.append("  Weak indices: " + " | ".join(
                f"{name} {pct:+.2f}%" for name, pct, _ in laggards
            ))

    if idx and not idx.get("error"):
        lines.append("\n▶ INDEX")
        lines.append(f"  {idx.get('index')}: {idx.get('close'):,.2f}  ({idx.get('chg_pct'):+.2f}%)")
        t = idx.get("trend_10d", {})
        lines.append(f"  10d trend: {t.get('chg_pct',0):+.2f}%  ({t.get('up_days',0)}/{len(t.get('closes',[]))-1} up-days)")

    if brd and not brd.get("error"):
        if live and not live.get("error"):
            lines.append("\n▶ DB UNIVERSE CONTEXT")
        else:
            lines.append("\n▶ MARKET BREADTH")
        lines.append(f"  Advances: {brd.get('advances')}  Declines: {brd.get('declines')}  "
                     f"A/D ratio: {brd.get('ad_ratio')}")
        lines.append(f"  Universe avg RS: {brd.get('avg_rs_pct',0):+.1f}%")
        sd = brd.get("stage_distribution", {})
        if sd:
            stage_parts = [
                ("Stage 1", sd.get("STAGE_1", sd.get("stage_1", 0))),
                ("Stage 2", sd.get("STAGE_2", sd.get("stage_2", 0))),
                ("Stage 3", sd.get("STAGE_3", sd.get("stage_3", 0))),
                ("Stage 4", sd.get("STAGE_4", sd.get("stage_4", 0))),
            ]
            unknown = sd.get("UNKNOWN", sd.get("unknown"))
            if unknown:
                stage_parts.append(("Unknown", unknown))
            lines.append("  Stage dist: " + " | ".join(f"{label}: {int(value or 0)}" for label, value in stage_parts))

    if movers and not movers.get("error"):
        lines.append("\n▶ TOP STOCK MOVERS")
        gainers = movers.get("gainers") or []
        losers = movers.get("losers") or []
        if gainers:
            lines.append("  Top gainers: " + " | ".join(
                f"{row.get('symbol', '—')} {row.get('pct_change', 0):+.2f}%"
                if isinstance(row.get("pct_change"), (int, float)) else f"{row.get('symbol', '—')} n/a"
                for row in gainers[:5]
            ))
        if losers:
            lines.append("  Top losers: " + " | ".join(
                f"{row.get('symbol', '—')} {row.get('pct_change', 0):+.2f}%"
                if isinstance(row.get("pct_change"), (int, float)) else f"{row.get('symbol', '—')} n/a"
                for row in losers[:5]
            ))

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

    # 5b. PostgreSQL intraday setup and screeners
    if intra_setup and not intra_setup.get("error"):
        _sym = intra_setup.get("symbol", "—")
        _tf = intra_setup.get("timeframe", "—")
        _label = intra_setup.get("setup_label", "—")
        _score = intra_setup.get("score", "—")
        _price = intra_setup.get("latest_close")
        _ts = intra_setup.get("latest_timestamp", "—")
        _ind = intra_setup.get("indicators") or {}
        _levels = intra_setup.get("levels") or {}
        _pivots = _levels.get("pivot_levels") or {}
        _ema_lvl = _levels.get("ema_levels") or {}
        _sups = _levels.get("supports") or []
        _ress = _levels.get("resistances") or []
        _inv = intra_setup.get("invalidation_level")
        _targets = intra_setup.get("technical_target_zones") or []
        _signals = intra_setup.get("signals") or []
        _tp = intra_setup.get("trade_plan") or {}
        _ps = intra_setup.get("position_sizing") or {}
        _rr = intra_setup.get("risk_reward_frame") or {}

        def _pct_from(ref, val):
            if isinstance(ref, (int, float)) and isinstance(val, (int, float)) and ref > 0:
                return f"({(val - ref) / ref * 100:+.2f}%)"
            return ""

        # -- Header
        lines.append("\n▶ INTRADAY SETUP")
        price_str = f"₹{_price:,.2f}" if isinstance(_price, (int, float)) else "—"
        lines.append(f"  Symbol:    {_sym}  |  Timeframe: {_tf}")
        lines.append(f"  Setup:     {_label}  |  Score: {_score}")
        lines.append(f"  Price:     {price_str}  |  As of: {_ts}")

        # -- Key Levels
        lines.append("  ── Key Levels ──")
        if _pivots.get("PP") is not None:
            lines.append(f"  Pivot (PP): ₹{_pivots['PP']:,.2f}")
        for lvl in ["R1", "R2", "R3"]:
            v = _pivots.get(lvl)
            if v is not None:
                lines.append(f"  {lvl}:        ₹{v:,.2f}  {_pct_from(_price, v)}")
        for lvl in ["S1", "S2", "S3"]:
            v = _pivots.get(lvl)
            if v is not None:
                lines.append(f"  {lvl}:        ₹{v:,.2f}  {_pct_from(_price, v)}")
        if _sups:
            lines.append("  Supports:   " + " | ".join(f"₹{s:,.2f}" if isinstance(s, (int, float)) else str(s) for s in _sups[:4]))
        if _ress:
            lines.append("  Resistances:" + " | ".join(f"₹{r:,.2f}" if isinstance(r, (int, float)) else str(r) for r in _ress[:4]))
        ema_parts = []
        for ek in ["ema9", "ema21", "ema50", "ema200"]:
            ev = _ema_lvl.get(ek) or _ind.get(ek)
            if isinstance(ev, (int, float)):
                ema_parts.append(f"{ek.upper()}: ₹{ev:,.2f}")
        if ema_parts:
            lines.append("  EMAs:       " + " | ".join(ema_parts))

        # -- Targets & Invalidation
        lines.append("  ── Targets & Invalidation ──")
        if len(_targets) > 0 and isinstance(_targets[0], (int, float)):
            lines.append(f"  T1:         ₹{_targets[0]:,.2f}  {_pct_from(_price, _targets[0])}")
        else:
            lines.append("  T1:         —")
        if len(_targets) > 1 and isinstance(_targets[1], (int, float)):
            lines.append(f"  T2:         ₹{_targets[1]:,.2f}  {_pct_from(_price, _targets[1])}")
        if isinstance(_inv, (int, float)):
            lines.append(f"  Invalidation (SL): ₹{_inv:,.2f}  {_pct_from(_price, _inv)}")
        else:
            lines.append("  Invalidation (SL): —")

        # -- Indicators Snapshot
        lines.append("  ── Indicators ──")
        rsi_str = f"{_ind['rsi']:.1f}" if isinstance(_ind.get("rsi"), (int, float)) else "—"
        macd_str = f"{_ind['macd_hist']:.4f}" if isinstance(_ind.get("macd_hist"), (int, float)) else "—"
        st_map = {1: "Bullish", -1: "Bearish"}
        st_str = st_map.get(_ind.get("supertrend_dir"), "—")
        lines.append(f"  RSI: {rsi_str} | MACD hist: {macd_str} | Supertrend: {st_str}")
        ind_extra = []
        if isinstance(_ind.get("volume_ratio"), (int, float)):
            ind_extra.append(f"Vol ratio: {_ind['volume_ratio']:.1f}x")
        if isinstance(_ind.get("atr"), (int, float)):
            ind_extra.append(f"ATR: ₹{_ind['atr']:,.2f}")
        if isinstance(_ind.get("bb_pct"), (int, float)):
            ind_extra.append(f"BB%: {_ind['bb_pct']:.0f}%")
        if ind_extra:
            lines.append("  " + " | ".join(ind_extra))

        # -- Strategy Signals
        active_sigs = [s for s in _signals if s.get("entry") is not None]
        if active_sigs:
            lines.append("  ── Strategy Signals ──")
            for sig in active_sigs[:5]:
                s_name = sig.get("strategy", "—")
                s_dir = sig.get("setup_label", sig.get("direction", "—"))
                s_entry = sig.get("entry")
                s_tgt = sig.get("target")
                s_sl = sig.get("stoploss")
                s_rr = sig.get("rr")
                s_str = sig.get("strength", "")
                parts = [f"{s_name} ({s_dir}):"]
                if isinstance(s_entry, (int, float)):
                    parts.append(f"entry ₹{s_entry:,.2f}")
                if isinstance(s_tgt, (int, float)):
                    parts.append(f"target ₹{s_tgt:,.2f}")
                if isinstance(s_sl, (int, float)):
                    parts.append(f"SL ₹{s_sl:,.2f}")
                if isinstance(s_rr, (int, float)):
                    parts.append(f"R:R {s_rr:.1f}")
                if s_str:
                    parts.append(f"[{s_str}]")
                lines.append("  " + " | ".join(parts))
                note = sig.get("note")
                if note:
                    lines.append(f"    {note}")

        # -- Trade Plan (only for LONG/SHORT)
        if _tp and _tp.get("direction"):
            lines.append(f"  ── Trade Plan (Educational) — {_tp['direction']} ──")
            lines.append("  Entry confirmations:")
            for c in _tp.get("entry_confirmations", []):
                lines.append(f"    • {c}")
            so = _tp.get("scale_out", [])
            if so:
                lines.append("  Scale-out plan:")
                for s in so:
                    lines.append(f"    • {s}")
            inv_act = _tp.get("invalidation_action")
            if inv_act:
                lines.append(f"  Invalidation: {inv_act}")

        # -- Position Sizing
        if _ps and not _ps.get("error"):
            budget = _ps.get("risk_per_trade", 5000)
            lines.append(f"  ── Position Sizing (Educational, ₹{budget:,.0f} risk budget) ──")
            lines.append(f"  Risk/share:  ₹{_ps.get('risk_per_share', 0):,.2f}")
            cash = _ps.get("cash") or {}
            if cash.get("shares"):
                lines.append(
                    f"  Cash/Equity: {cash['shares']:,} shares "
                    f"(capital ~₹{cash.get('capital_required', 0):,.0f})"
                )
            fut = _ps.get("futures")
            if fut:
                lines.append(
                    f"  Futures:     {fut['lots']} lot(s) x {fut['lot_size']} = "
                    f"{fut['units']} units "
                    f"(risk ₹{fut['risk_per_lot']:,.0f}/lot, "
                    f"margin ~₹{fut['approx_margin_per_lot']:,.0f}/lot)"
                )
            opt_note = _ps.get("options_note")
            if opt_note:
                lines.append(f"  Options:     {opt_note}")

        # -- Risk-Reward Frame
        if _rr and _rr.get("risk_per_share"):
            lines.append("  ── Risk-Reward Frame ──")
            lines.append(f"  Risk/share:  ₹{_rr['risk_per_share']:,.2f}")
            if _rr.get("t1_rr") is not None:
                lines.append(
                    f"  T1 R:R       1:{_rr['t1_rr']:.1f}  "
                    f"(₹{_rr.get('rupee_risk', 0):,.0f} risk → "
                    f"₹{_rr.get('t1_rupee_reward', 0):,.0f} reward)"
                )
            if _rr.get("t2_rr") is not None:
                lines.append(
                    f"  T2 R:R       1:{_rr['t2_rr']:.1f}  "
                    f"(₹{_rr.get('rupee_risk', 0):,.0f} risk → "
                    f"₹{_rr.get('t2_rupee_reward', 0):,.0f} reward)"
                )

        lines.append("  ━━━ Research setup only; not a buy/sell recommendation. Not SEBI registered. ━━━")

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

    if nse_intraday and not nse_intraday.get("error"):
        lines.append("\n▶ NSE LIVE SNAPSHOT")
        lines.append(f"  Symbol:      {nse_intraday.get('symbol', '—')}")
        lines.append(f"  Source:      {nse_intraday.get('source', 'NSE website')}")
        lines.append(f"  As of:       {nse_intraday.get('as_of', '—')}")
        lines.append(f"  Last price:  ₹{nse_intraday.get('last_price', '—')}")
        if nse_intraday.get("pct_change") is not None:
            lines.append(f"  Change:      {nse_intraday.get('pct_change')}%")
        lines.append(f"  Day range:   {nse_intraday.get('day_low', '—')} – {nse_intraday.get('day_high', '—')}")
        if nse_intraday.get("vwap") is not None:
            lines.append(f"  VWAP:        ₹{nse_intraday.get('vwap')}")
        lines.append("  Framing:     NSE website live snapshot; not a full intraday candle series.")

    if (
        intra_legacy
        and not intra_legacy.get("error")
        and (
            (intra_setup and intra_setup.get("error"))
            or (intra_levels and intra_levels.get("error"))
            or not (intra_setup or intra_levels or intra_ind)
        )
    ):
        bars_error = (
            (intra_setup or {}).get("error")
            or (intra_levels or {}).get("error")
            or "PostgreSQL intraday bars unavailable"
        )
        lines.append("\n▶ INTRADAY FALLBACK ANALYSIS")
        lines.append(f"  PostgreSQL intraday bars unavailable: {bars_error}")
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

    if intra_index_scan and not intra_index_scan.get("error"):
        buy = intra_index_scan.get("top_buy") or intra_index_scan.get("buy_signals") or []
        sell = intra_index_scan.get("top_sell") or intra_index_scan.get("sell_signals") or []
        lines.append("\n▶ INTRADAY INDEX SCAN")
        lines.append(f"  Index:       {intra_index_scan.get('index', '—')}")
        lines.append(f"  Timeframe:   {intra_index_scan.get('interval') or intra_index_scan.get('timeframe') or '—'}")
        if intra_index_scan.get("data_source"):
            lines.append(f"  Source:      {intra_index_scan.get('data_source')}")
        lines.append(f"  Signals:     {len(buy)} long research setups | {len(sell)} short research setups")
        for label, rows in (("Long", buy), ("Short", sell)):
            if not rows:
                continue
            lines.append(f"  {label} setups:")
            for sig in rows[:10]:
                bits = [str(sig.get("symbol", "—"))]
                if sig.get("strategy"):
                    bits.append(str(sig.get("strategy")))
                if sig.get("entry") is not None:
                    bits.append(f"entry {sig.get('entry')}")
                if sig.get("target") is not None:
                    bits.append(f"target {sig.get('target')}")
                invalidation = sig.get("stoploss", sig.get("invalidation_level"))
                if invalidation is not None:
                    bits.append(f"invalidation {invalidation}")
                if sig.get("rr") is not None:
                    bits.append(f"R:R {sig.get('rr')}")
                lines.append("    - " + " | ".join(bits))

    if intra_symbol_scan and not intra_symbol_scan.get("error"):
        buy = intra_symbol_scan.get("top_buy") or intra_symbol_scan.get("buy_signals") or []
        sell = intra_symbol_scan.get("top_sell") or intra_symbol_scan.get("sell_signals") or []
        symbols_scanned = intra_symbol_scan.get("symbols_scanned") or []
        lines.append("\n▶ INTRADAY SYMBOL SCAN")
        lines.append(f"  Symbols:     {', '.join(symbols_scanned[:20]) if symbols_scanned else '—'}")
        lines.append(f"  Timeframe:   {intra_symbol_scan.get('interval') or intra_symbol_scan.get('timeframe') or '—'}")
        if intra_symbol_scan.get("data_source"):
            lines.append(f"  Source:      {intra_symbol_scan.get('data_source')}")
        lines.append(f"  Signals:     {len(buy)} long research setups | {len(sell)} short research setups")
        for label, rows in (("Long", buy), ("Short", sell)):
            if not rows:
                continue
            lines.append(f"  {label} setups:")
            for sig in rows[:10]:
                bits = [str(sig.get("symbol", "—"))]
                if sig.get("strategy"):
                    bits.append(str(sig.get("strategy")))
                if sig.get("entry") is not None:
                    bits.append(f"entry {sig.get('entry')}")
                if sig.get("target") is not None:
                    bits.append(f"target {sig.get('target')}")
                invalidation = sig.get("stoploss", sig.get("invalidation_level"))
                if invalidation is not None:
                    bits.append(f"invalidation {invalidation}")
                if sig.get("rr") is not None:
                    bits.append(f"R:R {sig.get('rr')}")
                lines.append("    - " + " | ".join(bits))
        lines.append("  Framing: Research-only intraday scan; not buy/sell recommendations.")

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
    if tech and not tech.get("error"):
        if tech.get("rsi", 50) > 75:  risks.append("RSI overbought (>75)")
        if not tech.get("above_sma50"): risks.append("Price below SMA50")
        if tech.get("adx", 0) < 20:  risks.append("ADX < 20 — weak trend")
    if snap and not snap.get("error"):
        if snap.get("stage") not in ("STAGE_2", None) and snap.get("stage"):
            risks.append(f"Not in Stage 2 ({snap.get('stage')})")
    if risks:
        lines.append("\n▶ RISKS / WATCH")
        for r in risks:
            lines.append(f"  ⚠ {r}")

    missing_tools = [
        tr["tool"]
        for tr in tool_results
        if isinstance(tr.get("result"), dict) and tr["result"].get("error")
    ]
    if missing_tools:
        lines.append("\n▶ MISSING EVIDENCE")
        lines.append("  Missing evidence: " + ", ".join(dict.fromkeys(missing_tools)))
        lines.append("  No unsupported technical, fundamental, catalyst, or sector conclusion was inferred from missing data.")

    # Intraday / data health
    intra_health = _get("get_intraday_source_health")
    data_health = _get("get_data_health")
    if intent in ("intraday_health", "data_health"):
        src = intra_health or data_health or {}
        if src and not src.get("error"):
            lines.append(f"## Intraday Data Health  —  {src.get('source', 'PostgreSQL')}")
            lines.append(f"Overall status: **{src.get('overall_status', '—')}**")
            lines.append(f"Database: `{src.get('db_path', '—')}`")
            tables = src.get("tables") or {}
            if tables:
                lines.append("\n| Table | Status | Rows | Latest | Age (min) |")
                lines.append("|-------|--------|------|--------|-----------|")
                for tname, tinfo in tables.items():
                    if isinstance(tinfo, dict):
                        lines.append(
                            f"| {tname} | {tinfo.get('status', '—')} "
                            f"| {tinfo.get('rows', '—'):,} "
                            f"| {tinfo.get('latest_timestamp', '—')} "
                            f"| {tinfo.get('age_minutes', '—')} |"
                        )
        elif src:
            lines.append(f"## Data Health\n- Error: {src.get('error', 'unknown')}")

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


class Agent:
    """Agent Adda NLP Query Agent."""

    # Approx token budget for rolling history (chars ÷ 4 ≈ tokens).
    # At ~4 chars/token, 40_000 chars ≈ 10k tokens — safe headroom for most models.
    _HISTORY_CHAR_BUDGET = 40_000
    # Hard cap: never keep more than 20 turns (40 messages) regardless of size
    _HISTORY_MAX_TURNS   = 20
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
    ) -> None:
        """Persist compact chat state plus the latest resolved symbols."""
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

        self._history.append({"role": "user", "content": user_input})
        self._history.append({"role": "assistant", "content": answer})

    def _conversation_fallback_context(self, *, mode: str, source_label: str) -> TurnContext | None:
        """Build minimal context from rolling history when structured context is absent."""
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

    def query(self, user_input: str, show_trace: bool = False) -> dict:
        """Process a user query. Returns {"answer": str, "trace": list, "backend": str}.

        Compound query support: if the user packs multiple distinct questions
        into one prompt (separated by ". ", " and also ", " ; ", "?" boundaries,
        etc.), split them and run each through `_query_single`, then merge the
        answers. Single-question queries are dispatched unchanged.
        """
        parts = _split_compound_query(user_input)
        if len(parts) <= 1:
            return self._query_single(user_input, show_trace=show_trace)

        # Multi-part compound query: dispatch each part sequentially.
        merged_answers: list[str] = []
        merged_trace: list[dict] = []
        last_backend = self.backend_name
        for idx, part in enumerate(parts, start=1):
            res = self._query_single(part, show_trace=show_trace)
            merged_answers.append(
                f"━━━ Part {idx} of {len(parts)}: {part} ━━━\n\n"
                + (res.get("answer") or "")
            )
            merged_trace.append({"step": f"compound_part_{idx}", "query": part,
                                 "intent": res.get("intent"),
                                 "trace": res.get("trace", [])})
            last_backend = res.get("backend") or last_backend
        return {
            "answer": "\n\n".join(merged_answers),
            "trace": merged_trace,
            "backend": last_backend,
            "intent": "compound",
        }

    def _query_single(self, user_input: str, show_trace: bool = False) -> dict:
        """Process a single user query. Returns {"answer": str, "trace": list, "backend": str}.

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
            if _is_global_query(user_input.lower()):
                mode = "global"
            elif _looks_like_intraday_query(user_input):
                mode = "intraday"

        clean_input = self._contextualize_pronouns(clean_input)
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

        def _with_readiness_metadata(answer: str) -> str:
            if mode != "historical":
                return answer
            try:
                return append_readiness_metadata(
                    answer,
                    project_root=Path(__file__).resolve().parent.parent,
                )
            except Exception:
                return answer

        trace: list[dict] = []
        entity_assessment = assess_entity_topic_request(clean_input)
        if entity_assessment.applies and entity_assessment.decision == "route_with_entity_topic":
            trace.append({"step": "entity_topic_assessment", "result": entity_assessment.__dict__})
            entity_plan = _entity_topic_execution_plan(entity_assessment)
            if entity_plan:
                tool_results = _execute_plan(entity_plan)
                trace.extend(tool_results)
                answer_body = _synthesize_no_llm(
                    "entity_topic_command",
                    tool_results,
                )
                answer_body = _apply_response_guardrails(clean_input, "entity_topic_command", tool_results, answer_body)
                answer = answer_body + mode_suffix
                answer = _with_readiness_metadata(answer)
                turn_context = build_turn_context(
                    user_input=clean_input,
                    intent="entity_topic_command",
                    mode=mode,
                    source_label=source_label,
                    tool_results=tool_results,
                    answer=answer,
                )
                self._remember_interaction(clean_input, answer, tool_results, turn_context=turn_context)
                return {
                    "answer": answer,
                    "trace": trace,
                    "backend": self.backend_name,
                    "intent": "entity_topic_command",
                }

        if needs_situation_assessment(clean_input):
            previous_context = self._last_turn_context or self._conversation_fallback_context(
                mode=mode,
                source_label=source_label,
            )
            assessment = assess_followup(clean_input, previous_context)
            trace.append({"step": "situation_assessment", "result": assessment.__dict__})

            if assessment.applies and assessment.decision in {"answer_from_context", "ask_clarification"}:
                previous_context = previous_context or TurnContext(
                    user_input="",
                    intent="unknown",
                    mode=mode,
                    tools=[],
                    source_label=source_label,
                )
                answer = render_context_answer(clean_input, assessment, previous_context)
                self._remember_interaction(clean_input, answer, [])
                return {
                    "answer": answer,
                    "trace": trace,
                    "backend": self.backend_name,
                    "intent": "situation_assessment",
                }

            if assessment.applies and assessment.decision == "run_tool_plan":
                tool_results = _execute_plan(assessment.tool_plan)
                trace.extend(tool_results)
                synthesis_intent = (
                    "report_lookup"
                    if any(name in {"open_report", "read_report", "summarize_report", "get_last_report", "list_generated_reports"} for name, _ in assessment.tool_plan)
                    else "intraday_symbol_scan"
                )
                answer_body = (
                    render_assessment_block(assessment)
                    + "\n\n"
                    + _synthesize_no_llm(synthesis_intent, tool_results)
                )
                answer_body = _apply_response_guardrails(clean_input, synthesis_intent, tool_results, answer_body)
                answer = answer_body + mode_suffix
                turn_context = build_turn_context(
                    user_input=clean_input,
                    intent="contextual_tool_plan",
                    mode=mode,
                    source_label=source_label,
                    tool_results=tool_results,
                    answer=answer,
                )
                self._remember_interaction(clean_input, answer, tool_results, turn_context=turn_context)
                return {
                    "answer": answer,
                    "trace": trace,
                    "backend": self.backend_name,
                    "intent": "contextual_tool_plan",
                }

        intent_plan = _keyword_intent(clean_input, data_mode=mode)
        if intent_plan.get("intent") == "market_overview":
            source_label = "NSE live API + DB breadth"
            mode_suffix = (
                f"\n\n_Mode: {mode.title()} | Sources: NSE live API + DB breadth | "
                f"Market: {market_status.compact_label} | "
                f"Clock: {market_status.clock_label}_"
            )
        if intent_plan.get("intent") == "market_situation_assessment":
            source_label = "situation planner + NSE live API + DB breadth"
            mode_suffix = (
                f"\n\n_Mode: {mode.title()} | Sources: situation planner + NSE live API + DB breadth | "
                f"Market: {market_status.compact_label} | "
                f"Clock: {market_status.clock_label}_"
            )
        if intent_plan.get("intent") == "market_dashboard":
            source_label = "dashboard planner + NSE live API + DB breadth + FII/DII + global context"
            mode_suffix = (
                f"\n\n_Mode: Intraday | Sources: dashboard planner + NSE live API + DB breadth + FII/DII + global context | "
                f"Market: {market_status.compact_label} | "
                f"Clock: {market_status.clock_label}_"
            )
        if intent_plan.get("intent") == "intraday_market_recap":
            # PG-source-label: be explicit that the recap reads from PG
            # intraday.quote_snapshots, not SQLite — these snapshots are
            # captured every 60 s by terminal/intraday_capture.py.
            source_label = "NSE live API + PG intraday.quote_snapshots + DB breadth"
            mode_suffix = (
                f"\n\n_Mode: Intraday | Sources: NSE live API + PG intraday.quote_snapshots + DB breadth | "
                f"Market: {market_status.compact_label} | "
                f"Clock: {market_status.clock_label}_"
            )
        if intent_plan.get("intent") == "fno_overview":
            source_label = "NSE options/futures API + F&O EOD fallback"
            mode_suffix = (
                f"\n\n_Mode: Intraday | Sources: NSE options/futures API + F&O EOD fallback | "
                f"Market: {market_status.compact_label} | "
                f"Clock: {market_status.clock_label}_"
            )
        if intent_plan.get("intent") in {
            "youtube_video_analysis", "youtube_channel_latest",
            "youtube_video_transcription", "youtube_channel_transcription",
            "youtube_channels",
        }:
            source_label = "YouTube watch metadata + available captions + preset channel registry"
            if intent_plan.get("intent") in {"youtube_video_transcription", "youtube_channel_transcription"}:
                source_label += " + explicit audio speech-to-text when captions are unavailable"
            mode_suffix = (
                f"\n\n_Mode: Research | Sources: {source_label} | "
                f"Market: {market_status.compact_label} | "
                f"Clock: {market_status.clock_label}_"
            )
        if intent_plan.get("intent") in {
            "greeting", "startup_morning_briefing", "global_market_assessment",
            "market_situation_assessment", "placeholder_symbol_request",
            "document_link_help",
            "strength_validation", "market_knowledge", "entity_topic_command", "stock_brief",
            "stock_results",
            "results_feed", "forthcoming_results",
            "stock_comparison", "portfolio_review",
            "event_calendar",
            "fno_overview", "market_dashboard", "screener",
            "market_overview", "intraday_index_scan", "intraday_screener",
            "intraday_market_recap", "intraday_setup", "intraday_levels",
            "data_health", "intraday_health",
            "youtube_video_analysis", "youtube_channel_latest",
            "youtube_video_transcription", "youtube_channel_transcription",
            "youtube_channels",
        }:
            trace.append({"step": "intent", "result": intent_plan})
            tool_results = _execute_plan(intent_plan["plan"])
            trace.extend(tool_results)
            if mode == "intraday":
                source_label = _intraday_source_label(
                    intent_plan["intent"],
                    tool_results,
                    mode_sources["intraday"],
                )
                mode_suffix = (
                    f"\n\n_Mode: Intraday | Sources: {source_label} | "
                    f"Market: {market_status.compact_label} | "
                    f"Clock: {market_status.clock_label}_"
                )
            answer_body = _synthesize_no_llm(
                intent_plan["intent"],
                tool_results,
                intent_plan.get("assessment_plan"),
            )
            answer_body = _apply_response_guardrails(
                clean_input,
                intent_plan["intent"],
                tool_results,
                answer_body,
            )
            answer = answer_body + mode_suffix
            answer = _with_readiness_metadata(answer)
            turn_context = build_turn_context(
                user_input=clean_input,
                intent=intent_plan["intent"],
                mode=mode,
                source_label=source_label,
                tool_results=tool_results,
                answer=answer,
            )
            self._remember_interaction(clean_input, answer, tool_results, turn_context=turn_context)
            return {"answer": answer, "trace": trace, "backend": self.backend_name,
                    "intent": intent_plan["intent"]}

        # ── LLM path ──────────────────────────────────────────────────────────
        if self.backend is not None:
            result = self._llm_query(clean_input, show_trace, mode_context)
            # Only append mode suffix if the LLM didn't include a Source Trail
            if "Mode:" not in result.get("answer", "")[-600:]:
                result["answer"] = result.get("answer", "") + mode_suffix
            result["answer"] = _with_readiness_metadata(result.get("answer", ""))
            return result

        # ── Keyword fallback path ──────────────────────────────────────────────
        trace.append({"step": "intent", "result": intent_plan})

        tool_results = _execute_plan(intent_plan["plan"])
        trace.extend(tool_results)
        if mode == "intraday":
            source_label = _intraday_source_label(
                intent_plan["intent"],
                tool_results,
                mode_sources["intraday"],
            )
            mode_suffix = (
                f"\n\n_Mode: Intraday | Sources: {source_label} | "
                f"Market: {market_status.compact_label} | "
                f"Clock: {market_status.clock_label}_"
            )

        answer_body = _synthesize_no_llm(
            intent_plan["intent"],
            tool_results,
            intent_plan.get("assessment_plan"),
        )
        answer_body = _apply_response_guardrails(
            clean_input,
            intent_plan["intent"],
            tool_results,
            answer_body,
        )
        answer = answer_body + mode_suffix
        # PG-self-check: same degraded-response guard for keyword fallback.
        answer = self._quality_check(
            user_input, intent_plan["intent"], tool_results, answer, mode_suffix,
        )
        answer = _with_readiness_metadata(answer)
        turn_context = build_turn_context(
            user_input=clean_input,
            intent=intent_plan["intent"],
            mode=mode,
            source_label=source_label,
            tool_results=tool_results,
            answer=answer,
        )
        self._remember_interaction(clean_input, answer, tool_results, turn_context=turn_context)
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
            resp = self.backend.chat(messages, tools=self._tool_schemas_for_query(self._tool_selection_text(user_input)))

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
                answer = _apply_response_guardrails(user_input, "llm_driven", tool_results, answer)

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
        answer = _apply_response_guardrails(user_input, "llm_driven_fallback", tool_results, answer)
        # Still save the turn so context is preserved
        self._remember_interaction(user_input, answer, tool_results)
        return {"answer": answer, "trace": tool_results, "backend": self.backend_name,
                "intent": "llm_driven_fallback", "turn": self.turn_count}
