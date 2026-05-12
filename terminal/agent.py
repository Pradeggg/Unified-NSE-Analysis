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
from .market_calendar import market_context_for_agent, market_session_status

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
• If SQLite/live intraday data is unavailable, say so clearly and avoid directional claims from missing data.
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

[Intraday screener tools — quote/index recap tape lives in PostgreSQL intraday.quote_snapshots (refreshed every 60s by the background capture daemon); SQLite intraday_ohlcv supplies bar/candle history; legacy yfinance tools remain available]
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
• get_nse_intraday_snapshot(symbol)   → NSE website live quote/index snapshot. Always use this
                                        before yfinance fallback when SQLite intraday bars are absent.
• get_intraday_analysis(symbol,       → Legacy yfinance candle analysis of one stock only after
    interval, strategies)               SQLite and NSE website snapshot have been attempted; keep output research-only.
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
• For any stock-specific query, Always resolve the entity first with resolve_symbol.
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
• "intraday setup / technical target zones / invalidation / trading setup" → call explain_intraday_setup(symbol); if SQLite tables are missing/stale or symbol bars are absent, call get_nse_intraday_snapshot(symbol) first, then get_intraday_analysis(symbol) only for candle history, and clearly label it as Yahoo Finance/EOD fallback context
• "intraday levels / support resistance / pivots / VWAP levels" → call get_intraday_levels(symbol); if SQLite levels are unavailable, call get_nse_intraday_snapshot(symbol) first, then get_intraday_analysis(symbol) only for candle history, and clearly label fallback levels
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
        self.client = OpenAI(api_key=key)
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
    if "nifty bank" in q or "bank nifty" in q:
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


def _primary_symbol_query(candidates: list[str], symbol_candidates: list[str]) -> str:
    """Choose the most explicit stock entity from a routed user query.

    Uppercase NSE-like ticker tokens are stronger evidence than prose labels
    such as "Earnings", "Teach", or "End-to-end". This keeps deterministic
    routes from handing common task words to resolve_symbol().
    """
    if symbol_candidates:
        return symbol_candidates[0]
    return candidates[0] if candidates else ""


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


def _keyword_intent(query: str, data_mode: str = "historical") -> dict:
    """Detect intent and build a tool plan from keywords alone."""
    routing_text = _routing_query_text(query)
    q = routing_text.lower()

    if _is_greeting_query(q):
        return {"intent": "greeting", "plan": []}

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
                ("search_latest_catalysts", {"symbol": "NIFTY India market global cues GIFT Nifty crude USDINR"}),
            ],
        }

    if data_mode == "intraday" and "intraday" in q and re.search(r"\bnifty\s*50\b|\bnifty50\b|\bnifty\b", q):
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

    assessment_plan = _build_market_situation_assessment_plan(query, data_mode=data_mode)
    if assessment_plan:
        return {
            "intent": "market_situation_assessment",
            "plan": _planner_execution_plan(assessment_plan["tasks"]),
            "assessment_plan": assessment_plan,
        }

    fno_terms = (
        "f&o", "fno", "option chain", "options chain", "option data", "options data",
        "pcr", "put call", "put-call", "max pain", "open interest", " oi ",
        "top oi", "futures basis", "cost of carry", "rollover", "futures premium",
        "futures discount",
    )
    if any(term in f" {q} " for term in fno_terms):
        symbol = _extract_fno_symbol(routing_text)
        plan = [
            ("get_options_chain", {"symbol": symbol, "expiry_index": 0}),
            ("get_futures_analysis", {"symbol": symbol}),
        ]
        if any(term in q for term in ("strategy", "recommend", "best options", "options play")):
            plan.append(("get_strategy_recommendations", {"symbol": symbol}))
        return {"intent": "fno_overview", "plan": plan}

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
    if any(w in q for w in breadth_words) or q.strip() in {"overview", "market"}:
        plan = [
            ("get_live_market_overview", {}),
            ("get_market_breadth", {}),
        ]
        if any(w in q for w in mover_words):
            plan.append(("get_top_gainers_losers", {"index": "NIFTY 500", "top_n": 5, "direction": "both"}))
        return {"intent": "market_overview", "plan": plan}

    words = re.findall(r"[A-Za-z][A-Za-z0-9\-&\.]+", routing_text)
    skip  = {"show","me","the","latest","on","for","what","is","how","tell",
              "about","give","setup","stock","stocks","sector","nse","india","market","today","brief","full",
              "overview","intraday","levels","level","support","resistance","screener","scan",
              "deep","dive","analysis","technical","trade","trading","of",
              "answer","analyze","analyse","this","spoken","question","your","read","view",
              "after","before","results","result","concise","evidence","aware","risk","first",
              "research","only","include","context","watch","next","hello","hi","hey",
              "happened","changed","change","last","minute","minutes","min","few",
              "compare","vs","versus","from","perspective","into","including","combine",
              "fundamental","fundamentals","forensic","red","flags","flag",
              "own","portfolio","holding","holdings","monitor","should"}
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
    if (
        not is_single_stock_technical_setup
        and any(term in q for term in ("compare", " vs ", " versus "))
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

    strength_terms = ("canslim", "can slim", "rs", "relative strength", "fundamental", "piotroski", "petroski")
    if sum(1 for term in strength_terms if term in q) >= 2 and any(w in q for w in ("strength", "strong", "which", "rank", "out of")):
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

    # Intraday routing: SQLite first, NSE website live snapshot second,
    # yfinance candle analysis only as fallback for OHLCV history.
    if data_mode == "intraday":
        if "scan" in q and (
            "nifty" in q
            or "bank nifty" in q
            or "midcap" in q
            or "smallcap" in q
        ):
            return {"intent": "intraday_index_scan", "plan": [("scan_intraday_market", {
                "index": _extract_intraday_scan_index(q),
                "interval": _extract_intraday_timeframe(q),
                "strategies": _extract_intraday_scan_strategies(q),
                "direction_filter": "buy" if any(w in q for w in (" buy", " long", " bullish")) else (
                    "sell" if any(w in q for w in (" sell", " short", " bearish")) else "all"
                ),
                "min_rr": 1.3,
                "top_n": 10,
            })]}
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
            sym_q = _primary_symbol_query(candidates, symbol_candidates)
            return {"intent": "intraday_levels", "plan": [
                ("resolve_symbol", {"query": sym_q}),
                ("get_intraday_levels", {"symbol": sym_q}),
                ("get_nse_intraday_snapshot", {"symbol": sym_q}),
                ("get_intraday_analysis", {"symbol": sym_q}),
            ]}
        if candidates:
            sym_q = _primary_symbol_query(candidates, symbol_candidates)
            return {"intent": "intraday_setup", "plan": [
                ("resolve_symbol", {"query": sym_q}),
                ("explain_intraday_setup", {"symbol": sym_q}),
                ("get_nse_intraday_snapshot", {"symbol": sym_q}),
                ("get_intraday_analysis", {"symbol": sym_q}),
            ]}

    technical_stock_terms = (
        "technical setup", "indicators", "rsi", "adx", "macd", "supertrend",
        "moving average", "sma", "weinstein stage", "rs rank", "relative strength"
    )
    if candidates and any(term in q for term in technical_stock_terms) and (" for " in f" {q} " or "setup" in q):
        sym_q = _primary_symbol_query(candidates, symbol_candidates)
        return {"intent": "stock_brief", "plan": [
            ("resolve_symbol",       {"query": sym_q}),
            ("get_symbol_snapshot",  {"symbol": sym_q.upper()}),
            ("get_technical_setup",  {"symbol": sym_q.upper()}),
            ("get_sector_context",   {"sector_or_symbol": sym_q.upper()}),
        ]}

    # Index query
    index_words = ["nifty", "sensex", "bank nifty", "nifty it", "nifty 50"]
    if any(w in q for w in index_words):
        idx = "NIFTY BANK" if "bank" in q else ("NIFTY IT" if " it" in q else "NIFTY 50")
        return {"intent": "index_status", "plan": [("get_index_snapshot", {"index_name": idx})]}

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

    if any(
        phrase in q
        for phrase in [
            "upcoming events", "event calendar", "events this week", "corporate action",
            "corporate actions", "upcoming results", "results this week", "board meeting",
            "dividend", "agm", "ex-date", "ex date",
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
        sym_q = _primary_symbol_query(candidates, symbol_candidates)
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
        sym_q = _primary_symbol_query(candidates, symbol_candidates)
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
    intra_setup = _get("explain_intraday_setup")
    intra_screen = _get("run_intraday_screener")
    intra_index_scan = _get("scan_intraday_market")
    intra_levels = _get("get_intraday_levels")
    intra_ind = _get("compute_intraday_indicators")
    nse_intraday = _get("get_nse_intraday_snapshot")
    intra_legacy = _get("get_intraday_analysis")

    sym = (snap or {}).get("symbol") or (tech or {}).get("symbol") or ""
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

    if intent == "greeting":
        lines.append("Hello — Agent Adda is ready.")
        lines.append("Try `/live` for current market status, `/global` for global cues, `/heat` for breadth/sector heat, or ask about a specific NSE symbol.")
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
        self.backend_name = _backend_name(self.backend)
        # Rolling conversation history: list of {"role": ..., "content": ...}
        # Only user + assistant turns (no system, no tool messages).
        self._history: list[dict] = []
        self._last_symbols: list[str] = []

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
        if clean_provider in {"gpt-4o", "gpt4o", "got-40", "got-4o", "openai"}:
            clean_model = model or ("gpt-4o" if clean_provider != "openai" else None)
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
                "error": "Usage: /model status | /model gpt-4o | /model ollama [model-name] | /model keyword",
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

    def _remember_interaction(self, user_input: str, answer: str, tool_results: list[dict]) -> None:
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

        self._history.append({"role": "user", "content": user_input})
        self._history.append({"role": "assistant", "content": answer})

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
               "Use get_intraday_source_health first for calculations, then SQLite-backed "
               "get_intraday_bars, compute_intraday_indicators, get_intraday_levels, "
               "explain_intraday_setup, and run_intraday_screener. If SQLite intraday "
               "tables are missing or stale for a single-stock/index deep dive, call "
               "get_nse_intraday_snapshot first from the NSE website, then call "
               "get_intraday_analysis only when OHLCV candle history is required. Label "
               "yfinance/EOD fallback clearly, and do not present fallback levels as "
               "SQLite/NSE live-table data."
                    if mode == "intraday"
                    else "Use EOD CSV and DB snapshot tools for historical/technical analysis."
                )
            )
            + f"\n\n{market_context}"
        )
        mode_sources = {
            "global": "cached global indices + correlations",
            # PG-source-label: intraday quote tape now lives in PostgreSQL
            # (intraday.quote_snapshots, populated by the always-on capture
            # daemon). SQLite intraday_ohlcv is still the bar/candle source.
            "intraday": "PG intraday.quote_snapshots + SQLite intraday OHLCV",
            "historical": "EOD CSV + DB snapshot",
        }
        market_status = market_session_status()
        mode_suffix = (
            f"\n\n_Mode: {mode.title()} | Sources: "
            f"{mode_sources.get(mode, 'EOD CSV + DB snapshot')} | "
            f"Market: {market_status.compact_label} | "
            f"Clock: {market_status.clock_label}_"
        )

        trace: list[dict] = []
        intent_plan = _keyword_intent(clean_input, data_mode=mode)
        if intent_plan.get("intent") == "market_overview":
            mode_suffix = (
                f"\n\n_Mode: {mode.title()} | Sources: NSE live API + DB breadth | "
                f"Market: {market_status.compact_label} | "
                f"Clock: {market_status.clock_label}_"
            )
        if intent_plan.get("intent") == "market_situation_assessment":
            mode_suffix = (
                f"\n\n_Mode: {mode.title()} | Sources: situation planner + NSE live API + DB breadth | "
                f"Market: {market_status.compact_label} | "
                f"Clock: {market_status.clock_label}_"
            )
        if intent_plan.get("intent") == "market_dashboard":
            mode_suffix = (
                f"\n\n_Mode: Intraday | Sources: dashboard planner + NSE live API + DB breadth + FII/DII + global context | "
                f"Market: {market_status.compact_label} | "
                f"Clock: {market_status.clock_label}_"
            )
        if intent_plan.get("intent") == "intraday_market_recap":
            # PG-source-label: be explicit that the recap reads from PG
            # intraday.quote_snapshots, not SQLite — these snapshots are
            # captured every 60 s by terminal/intraday_capture.py.
            mode_suffix = (
                f"\n\n_Mode: Intraday | Sources: NSE live API + PG intraday.quote_snapshots + DB breadth | "
                f"Market: {market_status.compact_label} | "
                f"Clock: {market_status.clock_label}_"
            )
        if intent_plan.get("intent") == "fno_overview":
            mode_suffix = (
                f"\n\n_Mode: Intraday | Sources: NSE options/futures API + F&O EOD fallback | "
                f"Market: {market_status.compact_label} | "
                f"Clock: {market_status.clock_label}_"
            )
        if intent_plan.get("intent") in {
            "greeting", "startup_morning_briefing", "global_market_assessment",
            "market_situation_assessment",
            "strength_validation", "market_knowledge", "stock_brief",
            "stock_comparison", "portfolio_review",
            "event_calendar",
            "fno_overview", "market_dashboard",
            "market_overview", "intraday_index_scan", "intraday_screener",
            "intraday_market_recap",
        }:
            trace.append({"step": "intent", "result": intent_plan})
            tool_results = _execute_plan(intent_plan["plan"])
            trace.extend(tool_results)
            answer = _synthesize_no_llm(
                intent_plan["intent"],
                tool_results,
                intent_plan.get("assessment_plan"),
            ) + mode_suffix
            self._remember_interaction(clean_input, answer, tool_results)
            return {"answer": answer, "trace": trace, "backend": self.backend_name,
                    "intent": intent_plan["intent"]}

        # ── LLM path ──────────────────────────────────────────────────────────
        if self.backend is not None:
            result = self._llm_query(clean_input, show_trace, mode_context)
            # Only append mode suffix if the LLM didn't include a Source Trail
            if "Mode:" not in result.get("answer", "")[-600:]:
                result["answer"] = result.get("answer", "") + mode_suffix
            return result

        # ── Keyword fallback path ──────────────────────────────────────────────
        trace.append({"step": "intent", "result": intent_plan})

        tool_results = _execute_plan(intent_plan["plan"])
        trace.extend(tool_results)

        answer = _synthesize_no_llm(
            intent_plan["intent"],
            tool_results,
            intent_plan.get("assessment_plan"),
        ) + mode_suffix
        # PG-self-check: same degraded-response guard for keyword fallback.
        answer = self._quality_check(
            user_input, intent_plan["intent"], tool_results, answer, mode_suffix,
        )
        self._remember_interaction(clean_input, answer, tool_results)
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
        # Still save the turn so context is preserved
        self._remember_interaction(user_input, answer, tool_results)
        return {"answer": answer, "trace": tool_results, "backend": self.backend_name,
                "intent": "llm_driven_fallback", "turn": self.turn_count}
