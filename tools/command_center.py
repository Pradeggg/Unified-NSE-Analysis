#!/usr/bin/env python3
"""
tools/command_center.py — Agent Adda Command Centre (TUI)

A Rich-powered interactive command browser with live search.
Run it as a companion to the REPL or standalone to discover and
launch any skill, screener, or pipeline command.

Usage
─────
  python tools/command_center.py          # interactive TUI
  python tools/command_center.py --list   # dump all commands as JSON
  python tools/command_center.py --run equity_chart_v1 RELIANCE

Features
────────
  • Searchable catalogue — all skills, screeners, REPL commands, pipeline steps
  • Category tabs: All | Skills | Screeners | Reports | Pipeline | Admin
  • Arrow-key navigation + Enter to run / copy command
  • Live status bar: market hours, last daily-refresh timestamp
  • Cmd shortcut panel (F1=help, F5=refresh, q=quit, Enter=run)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# ─── self-bootstrap into project venv ────────────────────────────────────────
_project_root = Path(__file__).resolve().parent.parent
_venv_py = _project_root / ".venv" / "bin" / "python"
if _venv_py.exists() and Path(sys.executable).resolve() != _venv_py.resolve():
    os.execv(str(_venv_py), [str(_venv_py), str(Path(__file__).resolve()), *sys.argv[1:]])

try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.prompt import Prompt
    from rich.columns import Columns
    from rich.rule import Rule
    from rich.style import Style
    from rich import box
except ImportError:
    sys.exit("❌  rich not installed — run: pip install rich")

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

console = Console(highlight=False)

# ─── episode logging (real runs) ──────────────────────────────────────────────
try:
    from knowledge_base.episode_store import EpisodeStore  # type: ignore
    _EPISODES = EpisodeStore()
except Exception:
    _EPISODES = None

# ─── Catalogue ────────────────────────────────────────────────────────────────

CATEGORIES = ["All", "Skills", "Screeners", "Reports", "Pipeline", "Admin"]

# ── REPL slash-commands ───────────────────────────────────────────────────────
# Excludes pure aliases (/dash=/dashboard, /company-xray=/xray, /council=/strategy_council)
_REPL_COMMANDS: list[dict[str, Any]] = [
    # ── Market overview ─────────────────────────────────────────────────────────
    {"id": "/dashboard",          "cat": "Reports",  "desc": "Full market dashboard — breadth, sector rotation, regime",             "tags": ["market", "overview"],              "cli": "python nse_agent.py → /dashboard"},
    {"id": "/heat",               "cat": "Reports",  "desc": "Sector heat map — colour-coded stage/momentum grid",                   "tags": ["sector", "heat", "overview"],      "cli": "python nse_agent.py → /heat"},
    {"id": "/global",             "cat": "Reports",  "desc": "Overnight US / Asian / SGX global cues and readthrough",               "tags": ["global", "macro"],                 "cli": "python nse_agent.py → /global"},
    {"id": "/us",                 "cat": "Reports",  "desc": "US market readthrough — how US close maps to Indian open",             "tags": ["global", "us"],                    "cli": "python nse_agent.py → /us"},
    {"id": "/cycle",              "cat": "Reports",  "desc": "Market cycle position — phase, duration, historical analogues",        "tags": ["cycle", "macro"],                  "cli": "python nse_agent.py → /cycle"},
    {"id": "/data-status",        "cat": "Admin",    "desc": "Data freshness check — last update time for each source",              "tags": ["admin", "health", "data"],         "cli": "python nse_agent.py → /data-status"},
    {"id": "/status",             "cat": "Admin",    "desc": "System status — PG, LLM, yfinance, Screener.in connectivity",         "tags": ["admin", "health"],                 "cli": "python nse_agent.py → /status"},
    {"id": "/commands",           "cat": "Admin",    "desc": "List all REPL commands with descriptions",                            "tags": ["admin", "help"],                   "cli": "python nse_agent.py → /commands"},
    # ── Scans & screeners ───────────────────────────────────────────────────────
    {"id": "/scan",               "cat": "Screeners","desc": "Live intraday scan across the F&O universe",                          "tags": ["intraday", "scan"],                "cli": "python nse_agent.py → /scan"},
    {"id": "/screen",             "cat": "Screeners","desc": "Run any of the 40 screeners (stage2, momentum, highrs, vcp…)",        "tags": ["screener"],                        "cli": "python nse_agent.py → /screen"},
    {"id": "/visual-scan",        "cat": "Screeners","desc": "Grounded EOD chart-pattern visual scan across universe",              "tags": ["screener", "technical", "eod"],    "cli": "python nse_agent.py → /visual-scan"},
    {"id": "/intraday-alerts",    "cat": "Screeners","desc": "View latest intraday alert cycle results from the tracker",           "tags": ["intraday", "alerts"],              "cli": "python nse_agent.py → /intraday-alerts"},
    {"id": "/monitor",            "cat": "Screeners","desc": "Start live monitoring loop — continuous alert tracking",              "tags": ["intraday", "monitor"],             "cli": "python nse_agent.py → /monitor"},
    {"id": "/search",             "cat": "Skills",   "desc": "Symbol / concept search — find stocks matching a description",       "tags": ["search", "symbol"],                "cli": "python nse_agent.py → /search QUERY"},
    # ── Single-stock skills ──────────────────────────────────────────────────────
    {"id": "/chart",              "cat": "Skills",   "desc": "Comprehensive HTML chart — SMA, Supertrend, RS, S/R, MACD, BB, VWAP","tags": ["chart", "technical"],              "cli": "python -m terminal.chart_engine SYMBOL"},
    {"id": "/xray",               "cat": "Skills",   "desc": "Company X-Ray — fundamentals, insider, events, Weinstein stage",     "tags": ["fundamental", "research"],         "cli": "python nse_agent.py → /xray SYMBOL"},
    {"id": "/mtf",                "cat": "Skills",   "desc": "Multi-time-frame level analysis — PWk/P3D/PD/SOD/L30",              "tags": ["mtf", "levels"],                   "cli": "python nse_agent.py → /mtf SYMBOL"},
    {"id": "/options",            "cat": "Skills",   "desc": "Options chain, PCR, OI heatmap, bias and trade verdict",             "tags": ["options", "derivatives"],          "cli": "python nse_agent.py → /options SYMBOL"},
    {"id": "/fno",                "cat": "Skills",   "desc": "F&O summary — OI, PCR, basis, max pain, CE/PE walls",               "tags": ["fno", "derivatives"],              "cli": "python nse_agent.py → /fno SYMBOL"},
    {"id": "/oi",                 "cat": "Skills",   "desc": "Open interest analysis — OI change, long/short build-up",           "tags": ["oi", "fno"],                       "cli": "python nse_agent.py → /oi SYMBOL"},
    {"id": "/pcr",                "cat": "Skills",   "desc": "Put/Call Ratio trend and interpretation",                            "tags": ["pcr", "options"],                  "cli": "python nse_agent.py → /pcr SYMBOL"},
    {"id": "/scenario",           "cat": "Skills",   "desc": "Options scenario P&L run — payoff across price range",              "tags": ["options", "scenario"],             "cli": "python nse_agent.py → /scenario SYMBOL"},
    {"id": "/backtest",           "cat": "Skills",   "desc": "Historical backtest for a symbol — signals vs EOD returns",         "tags": ["backtest", "historical"],          "cli": "python nse_agent.py → /backtest SYMBOL"},
    {"id": "/research",           "cat": "Skills",   "desc": "Full research pipeline — technicals + fundamentals + F&O + news",   "tags": ["research", "fundamental"],         "cli": "python nse_agent.py → /research SYMBOL"},
    {"id": "/deep-research",      "cat": "Skills",   "desc": "Deep research pipeline — multi-source AI-synthesised report",       "tags": ["research", "llm", "deep"],         "cli": "python nse_agent.py → /deep-research SYMBOL"},
    {"id": "/ric",                "cat": "Skills",   "desc": "Research Intelligence Council — AI ensemble deep-dive",             "tags": ["ric", "llm"],                      "cli": "python nse_agent.py → /ric SYMBOL"},
    {"id": "/strategy_council",   "cat": "Skills",   "desc": "Multi-agent strategy council for a symbol",                        "tags": ["strategy", "llm"],                 "cli": "python nse_agent.py → /strategy_council SYMBOL"},
    {"id": "/plan",               "cat": "Skills",   "desc": "Trade plan — entry trigger, stop, target, R:R for a symbol",       "tags": ["trade", "plan"],                   "cli": "python nse_agent.py → /plan SYMBOL"},
    {"id": "/strength",           "cat": "Skills",   "desc": "Relative strength vs Nifty 50 and sector index",                   "tags": ["rs", "relative-strength"],         "cli": "python nse_agent.py → /strength SYMBOL"},
    {"id": "/canslim",            "cat": "Skills",   "desc": "CANSLIM analysis — O'Neil criteria scored for a symbol",           "tags": ["canslim", "fundamental"],          "cli": "python nse_agent.py → /canslim SYMBOL"},
    {"id": "/valuation-check",    "cat": "Skills",   "desc": "Valuation scenario — DCF, P/E, EV/EBITDA bands",                  "tags": ["valuation", "fundamental"],        "cli": "python nse_agent.py → /valuation-check SYMBOL"},
    {"id": "/forensic",           "cat": "Skills",   "desc": "Forensic accounting check — red flags, cash flow vs profit",       "tags": ["forensic", "fundamental"],         "cli": "python nse_agent.py → /forensic SYMBOL"},
    {"id": "/diagnose",           "cat": "Skills",   "desc": "Fundamental driver diagnosis — what's driving earnings",           "tags": ["fundamental", "diagnosis"],        "cli": "python nse_agent.py → /diagnose SYMBOL"},
    {"id": "/investment-checklist","cat": "Skills",  "desc": "Investment checklist — quality, growth, momentum, valuation score","tags": ["checklist", "fundamental"],        "cli": "python nse_agent.py → /investment-checklist SYMBOL"},
    {"id": "/concall",            "cat": "Skills",   "desc": "Concall transcript summary — management commentary from Screener.in","tags": ["concall", "fundamental"],        "cli": "python nse_agent.py → /concall SYMBOL"},
    {"id": "/results",            "cat": "Skills",   "desc": "Latest quarterly results — revenue, PAT, margins, YoY/QoQ",       "tags": ["results", "fundamental"],          "cli": "python nse_agent.py → /results SYMBOL"},
    {"id": "/events",             "cat": "Skills",   "desc": "Corporate events — dividends, buybacks, board meetings, splits",   "tags": ["events", "corporate"],             "cli": "python nse_agent.py → /events SYMBOL"},
    {"id": "/broker-research",    "cat": "Skills",   "desc": "Broker research fetch — target prices and ratings",               "tags": ["broker", "research"],              "cli": "python nse_agent.py → /broker-research SYMBOL"},
    {"id": "/sector",             "cat": "Skills",   "desc": "Sector deep-dive — stage distribution, leaders, catalysts",       "tags": ["sector", "research"],              "cli": "python nse_agent.py → /sector NAME"},
    # ── Portfolio ────────────────────────────────────────────────────────────────
    {"id": "/pnl",                "cat": "Reports",  "desc": "Portfolio P&L snapshot — holdings, cost basis, unrealised",        "tags": ["portfolio", "pnl"],                "cli": "python nse_agent.py → /pnl"},
    {"id": "/my-portfolio",       "cat": "Reports",  "desc": "Portfolio analysis — add/trim/hold ranking with stage + fundamentals","tags": ["portfolio", "analysis"],        "cli": "python nse_agent.py → /my-portfolio"},
    {"id": "/swing-playbook",     "cat": "Reports",  "desc": "Swing trade playbook — ranked setups with entry/stop/target",     "tags": ["swing", "trade", "report"],        "cli": "python nse_agent.py → /swing-playbook"},
    {"id": "/strategy-lab",       "cat": "Reports",  "desc": "Portfolio strategy lab HTML — best-strategy replay + VCP tabs",   "tags": ["strategy", "portfolio"],           "cli": "python nse_agent.py → /strategy-lab run"},
    # ── Reports & content ────────────────────────────────────────────────────────
    {"id": "/report",             "cat": "Reports",  "desc": "Top picks HTML report from today's screener results",             "tags": ["report", "picks"],                 "cli": "python nse_agent.py → /report"},
    {"id": "/results-feed",       "cat": "Reports",  "desc": "Recent filings feed — symbols with latest quarterly results",     "tags": ["results", "feed"],                 "cli": "python nse_agent.py → /results-feed"},
    {"id": "/voice",              "cat": "Reports",  "desc": "Generate voice briefing script (no TTS)",                         "tags": ["voice", "report"],                 "cli": "python generate_voice_briefing.py --no-tts"},
    {"id": "/voice-mode",         "cat": "Reports",  "desc": "Toggle real-time voice mode — speak queries, hear answers",       "tags": ["voice", "tts"],                    "cli": "python nse_agent.py → /voice-mode"},
    {"id": "/email",              "cat": "Reports",  "desc": "Draft and send daily top-picks email to distribution list",       "tags": ["email", "report"],                 "cli": "python nse_agent.py → /email"},
    {"id": "/youtube",            "cat": "Skills",   "desc": "YouTube research search — find analyst videos for a query",       "tags": ["youtube", "research"],             "cli": "python nse_agent.py → /youtube QUERY"},
    {"id": "/export",             "cat": "Admin",    "desc": "Export REPL session data — signals, scores, watchlist",           "tags": ["export", "data"],                  "cli": "python nse_agent.py → /export"},
    {"id": "/screenshot",         "cat": "Admin",    "desc": "Capture terminal output as HTML and attach to email",             "tags": ["screenshot", "export"],            "cli": "python nse_agent.py → /screenshot"},
    # ── Skill store ─────────────────────────────────────────────────────────────
    {"id": "/skills",             "cat": "Skills",   "desc": "List and execute skill-store cards from the REPL",                "tags": ["skills", "store"],                 "cli": "python nse_agent.py → /skills"},
    {"id": "/prompts",            "cat": "Skills",   "desc": "Browse the 60+ prompt library with fuzzy search",                 "tags": ["prompts"],                         "cli": "python nse_agent.py → /prompts"},
    # ── Admin ────────────────────────────────────────────────────────────────────
    {"id": "/doctor",             "cat": "Admin",    "desc": "Health check — data freshness, DB status, API keys",              "tags": ["admin", "health"],                 "cli": "agent-adda doctor"},
    {"id": "/refresh",            "cat": "Admin",    "desc": "Run full daily pipeline (all 7 phases)",                          "tags": ["pipeline", "admin"],               "cli": "python daily_refresh.py"},
]

# ── Screeners, standalone tools, direct-run scripts ──────────────────────────
_SCREENERS: list[dict[str, Any]] = [
    # Charts
    {"id": "equity_chart",           "cat": "Skills",   "desc": "Comprehensive chart — BB, MACD, VWAP, RS, S/R, Supertrend (chart_engine)", "tags": ["chart", "technical"],         "cli": "python -m terminal.chart_engine SYMBOL"},
    # Screeners
    {"id": "stage2_vcp",             "cat": "Screeners","desc": "Stage 2 VCP breakout candidates",                                           "tags": ["stage2", "vcp", "breakout"],  "cli": "python nse_agent.py → /screen stage2_vcp"},
    {"id": "intraday_alerts",        "cat": "Screeners","desc": "Live F&O intraday alert scan — trigger, R:R, options verdict",             "tags": ["intraday", "fno", "alerts"],  "cli": "python -m terminal.live_intraday_alerts --cycles 1"},
    {"id": "pullback_recovery",      "cat": "Screeners","desc": "Apex pullback-recovery screener — Midcap/Nifty500 resilience candidates",   "tags": ["screener", "pullback"],       "cli": "python pullback_recovery_screener.py"},
    {"id": "screeners_stage",        "cat": "Screeners","desc": "William O'Neil Stage Analysis screener — full universe stage scan",         "tags": ["stage", "oneil"],             "cli": "python screeners.py"},
    # Reports
    {"id": "sector_rotation",        "cat": "Reports",  "desc": "Sector rotation report — stage distribution, leaders / laggards",          "tags": ["sector", "rotation"],         "cli": "python sector_rotation_report.py"},
    {"id": "fund_dashboard",         "cat": "Reports",  "desc": "Mutual fund holdings & sector allocation dashboard",                        "tags": ["fund", "portfolio"],          "cli": "python tools/fund_refresh.py"},
    {"id": "live_prices",            "cat": "Reports",  "desc": "Live prices dashboard for watchlist",                                       "tags": ["live", "prices"],             "cli": "python tools/live_prices.py"},
    {"id": "market_breadth",         "cat": "Reports",  "desc": "Market breadth — A/D, McClellan, TRIN",                                    "tags": ["breadth", "market"],          "cli": "python market_breadth.py"},
    {"id": "rrg_report",             "cat": "Reports",  "desc": "Relative Rotation Graph (RRG) — sector momentum quadrant chart → rrg.html", "tags": ["rrg", "sector", "rs"],        "cli": "python rrg_report.py"},
    {"id": "seasonal_heat_calendar", "cat": "Reports",  "desc": "Sectoral heat calendar — seasonal return patterns by month",               "tags": ["seasonal", "sector"],         "cli": "python seasonal_heat_calendar.py"},
    {"id": "global_correlation",     "cat": "Reports",  "desc": "Global correlation monitor — NSE vs US/EM/commodities",                    "tags": ["global", "correlation"],      "cli": "python global_correlation.py"},
    {"id": "knowledge_graph",        "cat": "Reports",  "desc": "NSE knowledge graph with shock propagation paths",                         "tags": ["knowledge", "graph"],         "cli": "python knowledge_graph.py"},
    {"id": "apex_resilience",        "cat": "Reports",  "desc": "Apex resilience full report — drawdown recovery scoring",                  "tags": ["resilience", "screener"],     "cli": "python apex_resilience_full_report.py"},
    {"id": "top_picks",              "cat": "Reports",  "desc": "Top picks report from today's screener results",                            "tags": ["picks", "report"],            "cli": "python scripts/top_picks_report.py"},
    {"id": "swing_playbook_html",    "cat": "Reports",  "desc": "Swing playbook HTML — ranked candidates with entry/stop/target",           "tags": ["swing", "report"],            "cli": "python nse_agent.py → /swing-playbook"},
    {"id": "strategy_lab",          "cat": "Reports",  "desc": "Portfolio strategy lab HTML — replay + VCP tabs",                          "tags": ["strategy", "portfolio"],      "cli": "python nse_agent.py → /strategy-lab run"},
    # Morning / EOD / weekend reports
    {"id": "morning_market_report",  "cat": "Reports",  "desc": "Morning market report — pre-open global cues, sector outlook, watchlist",  "tags": ["morning", "report"],          "cli": "python scripts/build_morning_market_report.py"},
    {"id": "midday_market_report",   "cat": "Reports",  "desc": "Midday market report — second-half breadth, sector leaders, risk control", "tags": ["midday", "report"],           "cli": "python scripts/build_morning_market_report.py --variant midday"},
    {"id": "eod_market_report",      "cat": "Reports",  "desc": "EOD market report — day's movers, breadth, F&O snapshot",                 "tags": ["eod", "report"],              "cli": "python scripts/build_eod_market_report.py"},
    {"id": "weekend_review",         "cat": "Reports",  "desc": "Weekend market review — weekly summary, leaders, setups to watch",        "tags": ["weekend", "report"],          "cli": "python scripts/run_weekend_market_review.py"},
    {"id": "morning_publish",        "cat": "Reports",  "desc": "Morning market report + auto-publish (email + HTML)",                      "tags": ["morning", "publish"],         "cli": "python scripts/run_morning_market_publish.py"},
    {"id": "broader_market",         "cat": "Reports",  "desc": "Broader market analysis — Midcap / Smallcap / Microcap breakdown",        "tags": ["midcap", "smallcap", "market"],"cli": "python scripts/build_broader_market_analysis.py"},
    {"id": "smallcap_super_report",  "cat": "Reports",  "desc": "Smallcap super report — quality filter + momentum screen",                "tags": ["smallcap", "report"],         "cli": "python scripts/build_smallcap_super_report.py"},
    {"id": "intraday_fno_report",    "cat": "Reports",  "desc": "Intraday F&O editorial report — evidence-bound narrative",               "tags": ["intraday", "fno", "report"],  "cli": "python scripts/build_agent_adda_intraday_fno_report.py"},
    {"id": "email_daily_reports",    "cat": "Reports",  "desc": "Email daily NSE reports to distribution list (PG-backed)",               "tags": ["email", "daily"],             "cli": "python email_daily_reports.py"},
    # Scoring / signals
    {"id": "universe_scoring",       "cat": "Pipeline", "desc": "Full NSE universe scoring → scores.daily_scores in PostgreSQL",           "tags": ["scoring", "universe"],        "cli": "python fixed_nse_universe_analysis.py"},
    {"id": "regime_detector",        "cat": "Skills",   "desc": "HMM regime detection — BULL / ROTATION / CHOP / BEAR",                   "tags": ["regime", "hmm"],              "cli": "python regime_detector.py"},
    {"id": "global_market_intel",    "cat": "Reports",  "desc": "Global market intelligence — overnight US/Asia/macro digest",            "tags": ["global", "macro"],            "cli": "python global_market_intelligence.py"},
    {"id": "index_intelligence",     "cat": "Reports",  "desc": "Index intelligence — composition, momentum, sector allocation shifts",    "tags": ["index", "intelligence"],      "cli": "python index_intelligence.py"},
    # Tools dir
    {"id": "portfolio_signals",      "cat": "Reports",  "desc": "Daily portfolio signal digest — add/trim/watch signals for holdings",    "tags": ["portfolio", "signals"],       "cli": "python tools/portfolio_signals.py"},
    {"id": "portfolio_assessment",   "cat": "Skills",   "desc": "Portfolio add/trim/hold assessment from ICICI Direct CSV",               "tags": ["portfolio", "assessment"],    "cli": "python tools/build_equity_portfolio_assessment.py --portfolio FILE.csv"},
    {"id": "fund_daily",             "cat": "Reports",  "desc": "Fund daily dashboard — intraday NAV and holding movements",              "tags": ["fund", "daily"],              "cli": "python tools/fund_daily.py"},
    {"id": "fund_rebalance",         "cat": "Reports",  "desc": "Monthly fund rebalance engine — drift check and rebalance orders",       "tags": ["fund", "rebalance"],          "cli": "python tools/fund_rebalance.py"},
    {"id": "backtest_fund",          "cat": "Skills",   "desc": "Fund strategy backtest — historical replay of allocation strategies",    "tags": ["fund", "backtest"],           "cli": "python tools/backtest_fund_strategies.py"},
    {"id": "midcap_monitor",         "cat": "Screeners","desc": "Midcap daily monitor — top movers, stage changes, watchlist alerts",     "tags": ["midcap", "monitor"],          "cli": "python tools/midcap_daily_monitor.py"},
    {"id": "smallcap_monitor",       "cat": "Screeners","desc": "Smallcap daily monitor — top movers, stage changes, breakouts",         "tags": ["smallcap", "monitor"],        "cli": "python tools/smallcap_daily_monitor.py"},
    {"id": "n500_fund_refresh",      "cat": "Pipeline", "desc": "NIFTY 500 fund dashboard refresh — full holding re-pull",               "tags": ["fund", "nifty500"],           "cli": "python tools/n500_fund_refresh.py"},
    {"id": "deep_research_report",   "cat": "Skills",   "desc": "Deep research report — tail-first narrative with sourced evidence",      "tags": ["research", "deep"],           "cli": "python tools/build_tail_first_deep_research_report.py"},
    {"id": "export_fundamentals",    "cat": "Admin",    "desc": "Export fundamentals from DB to CSV / JSON",                             "tags": ["export", "fundamentals"],     "cli": "python tools/export_fundamentals.py"},
    # Terminal modules
    {"id": "intraday_editorial",     "cat": "Reports",  "desc": "Evidence-bound F&O editorial report (terminal module)",                 "tags": ["intraday", "editorial"],      "cli": "python -m terminal.intraday_editorial_report"},
    {"id": "scope_report",           "cat": "Reports",  "desc": "Sector/index grounded report (terminal module)",                        "tags": ["sector", "report"],           "cli": "python -m terminal.scope_report"},
    # Admin / backfill
    {"id": "materialize_vcp",        "cat": "Pipeline", "desc": "Materialise Stage 2 VCP picks into portfolio.stage2_vcp_picks",         "tags": ["vcp", "portfolio"],           "cli": "python scripts/materialize_stage2_vcp_picks.py"},
    {"id": "backfill_fund",          "cat": "Admin",    "desc": "Screener.in fundamentals backfill (NIFTY 500, run weekly)",             "tags": ["fundamentals", "backfill"],   "cli": "python scripts/backfill_screener_fundamentals.py"},
    {"id": "backfill_eod",           "cat": "Admin",    "desc": "Extend equity price history >200 days via yfinance",                   "tags": ["price", "history"],           "cli": "python scripts/backfill_equity_eod_yfinance.py"},
    {"id": "backfill_stage_history", "cat": "Admin",    "desc": "Backfill historical stage snapshots — extend stage history in DB",      "tags": ["stage", "history"],           "cli": "python scripts/backfill_historical_stage_snapshots.py"},
    {"id": "refresh_results_feed",   "cat": "Admin",    "desc": "Refresh Screener.in results feed for symbols with recent filings",      "tags": ["results", "feed"],            "cli": "python scripts/refresh_results_feed.py"},
    {"id": "sync_signal_log",        "cat": "Admin",    "desc": "Sync signal_log.csv → PostgreSQL signals table",                       "tags": ["signals", "sync"],            "cli": "python scripts/sync_signal_log_to_pg.py"},
    {"id": "pg_loader",              "cat": "Pipeline", "desc": "Load all data into PostgreSQL (equity + F&O + fundamentals)",           "tags": ["postgres", "admin"],          "cli": "python postgres/loader.py"},
    {"id": "pg_loader_eod",          "cat": "Pipeline", "desc": "Load equity EOD only into PostgreSQL",                                 "tags": ["postgres", "eod"],            "cli": "python postgres/loader.py --eod-only"},
    {"id": "pg_loader_fno",          "cat": "Pipeline", "desc": "Load F&O EOD into PostgreSQL",                                        "tags": ["postgres", "fno"],            "cli": "python postgres/loader.py --fno-only"},
    {"id": "mcp_server",             "cat": "Admin",    "desc": "Start MCP server — exposes tool catalogue to Copilot / Claude",        "tags": ["mcp", "server"],              "cli": "python mcp_server.py"},
    # Data fetchers
    {"id": "fetch_corporate_events", "cat": "Admin",    "desc": "Fetch upcoming corporate events from NSE API",                         "tags": ["corporate", "events"],        "cli": "python fetch_corporate_events.py"},
    {"id": "fetch_insider_alerts",   "cat": "Admin",    "desc": "Fetch insider trade alerts from NSE API",                              "tags": ["insider", "alerts"],          "cli": "python fetch_insider_alerts.py"},
    {"id": "fetch_fii_dii",          "cat": "Admin",    "desc": "Fetch FII / DII flow data for the day",                               "tags": ["fii", "dii", "flow"],         "cli": "python fetch_fii_dii_flows.py"},
    {"id": "fetch_macro_proxies",     "cat": "Admin",    "desc": "Fetch macro-economic proxy signals (FRED etc.)",                      "tags": ["macro", "fred"],              "cli": "python fetch_macro_proxies.py"},
    {"id": "intraday_ohlcv_capture", "cat": "Admin",    "desc": "Intraday OHLCV capture — scheduled bar data collection (launchd)",    "tags": ["intraday", "ohlcv"],          "cli": "python scripts/run_intraday_ohlcv_capture.py"},
    {"id": "intraday_pattern_monitor","cat":"Screeners","desc": "Intraday pattern monitor — live pattern detection across universe",     "tags": ["intraday", "pattern"],        "cli": "python scripts/run_intraday_pattern_monitor.py"},
    # Analysis scripts
    {"id": "portfolio_construction", "cat": "Skills",   "desc": "Portfolio construction from signals — build target portfolio",         "tags": ["portfolio", "signals"],       "cli": "python scripts/portfolio_construction.py"},
    {"id": "analyze_daily_results",  "cat": "Reports",  "desc": "Analyze daily results — batch parse quarterly filings",               "tags": ["results", "analysis"],        "cli": "python scripts/analyze_daily_results.py"},
    {"id": "deep_analyze_batch",     "cat": "Skills",   "desc": "Batch deep analysis — run deep research on a symbol list",            "tags": ["research", "batch"],          "cli": "python scripts/deep_analyze_batch.py"},
    {"id": "full_analysis_pipeline", "cat": "Pipeline", "desc": "End-to-end analysis pipeline — all stages in one run",               "tags": ["pipeline", "analysis"],       "cli": "python run_complete_analysis_pipeline.py"},
    {"id": "report_validation",      "cat": "Admin",    "desc": "Report validation — check HTML reports for broken links and stale data","tags": ["validation", "report"],     "cli": "python report_validation.py"},
]

_PIPELINE: list[dict[str, Any]] = [
    {"id": "daily_refresh",          "cat": "Pipeline", "desc": "Full 7-phase daily pipeline (~25–35 min, run after NSE close 16:00 IST)",  "tags": ["pipeline", "daily"],    "cli": "python daily_refresh.py"},
    {"id": "daily_refresh_dry",      "cat": "Pipeline", "desc": "Daily pipeline dry-run — preview plan without executing",                   "tags": ["pipeline", "dry-run"],  "cli": "python daily_refresh.py --dry-run"},
    {"id": "daily_refresh_live",     "cat": "Pipeline", "desc": "Fast live-price update only (~1 min)",                                      "tags": ["pipeline", "live"],     "cli": "python daily_refresh.py --live-only"},
    {"id": "stage_snapshot",         "cat": "Pipeline", "desc": "Stage tracker snapshot → scores.stage_snapshots",                          "tags": ["stage", "tracker"],     "cli": "python sector_rotation_tracker.py --snapshot"},
    {"id": "pg_start",               "cat": "Admin",    "desc": "Start local PostgreSQL cluster",                                            "tags": ["postgres", "admin"],    "cli": "./postgres/start_pg.sh start"},
    {"id": "pg_stop",                "cat": "Admin",    "desc": "Stop local PostgreSQL cluster",                                             "tags": ["postgres", "admin"],    "cli": "./postgres/start_pg.sh stop"},
    {"id": "pg_status",              "cat": "Admin",    "desc": "Check PostgreSQL cluster status",                                           "tags": ["postgres", "admin"],    "cli": "./postgres/start_pg.sh status"},
    {"id": "ollama_pull",            "cat": "Admin",    "desc": "Pull Granite4 local LLM model via Ollama",                                  "tags": ["llm", "local"],         "cli": "ollama pull granite4"},
    {"id": "bhavcopy_loader",        "cat": "Pipeline", "desc": "Load daily bhavcopy CSV into PostgreSQL via R",                             "tags": ["bhavcopy", "eod"],      "cli": "Rscript load_latest_nse_data_comprehensive.R"},
    {"id": "sector_analysis_r",      "cat": "Pipeline", "desc": "Run R sector analysis (analyze_all_sectors.R)",                             "tags": ["r", "sector"],          "cli": "Rscript analyze_all_sectors.R"},
    {"id": "data_bootstrap",         "cat": "Admin",    "desc": "Seed SQLite from bundled CSV history (first-time setup)",                   "tags": ["setup", "admin"],       "cli": "agent-adda data bootstrap --historical --source data"},
    {"id": "agent_adda_intelligence_loop", "cat": "Admin", "desc": "Agent Adda Intelligence Loop — KB + episodes + propose/execute",       "tags": ["agent", "loop", "kb"],  "cli": "python -m terminal.agent_adda_intelligence_loop"},
]


def _load_skill_cards() -> list[dict[str, Any]]:
    """Load skill YAML cards from skill_store/stored/ and skill_store/generated/."""
    if not _HAS_YAML:
        return []
    cards: list[dict[str, Any]] = []
    dirs = [
        _project_root / "terminal" / "skills" / "seed_cards",
        _project_root / "skill_store" / "stored",
        _project_root / "skill_store" / "generated",
    ]
    for d in dirs:
        if not d.exists():
            continue
        for f in sorted(d.glob("*.yml")):
            try:
                with open(f) as fh:
                    data = yaml.safe_load(fh)
                if not isinstance(data, dict):
                    continue
                status = data.get("status", "")
                if status in ("test_failed", "deprecated"):
                    continue
                sid = data.get("id", f.stem)
                desc = data.get("description", "")
                if isinstance(desc, str):
                    desc = desc.strip().replace("\n", " ")
                metadata = data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {}
                tags = metadata.get("tags") or data.get("tags") or []
                cli = metadata.get("cli", "")
                patterns = data.get("input_patterns") or []
                if not cli and patterns:
                    cli = f'AGENT_ADDA_SKILL_STORE=1 .venv/bin/python3 nse_agent.py --query "{patterns[0]}"'
                if not cli:
                    cli = f'AGENT_ADDA_SKILL_STORE=1 .venv/bin/python3 nse_agent.py --query "{sid}"'
                cards.append({
                    "id": sid,
                    "cat": "Skills",
                    "desc": desc[:120],
                    "tags": tags,
                    "cli": cli,
                    "_source": "skill_card",
                    "_status": status,
                })
            except Exception:
                pass
    return cards


def build_catalogue() -> list[dict[str, Any]]:
    """Merge all sources; deduplicate by id."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in _REPL_COMMANDS + _SCREENERS + _PIPELINE + _load_skill_cards():
        if item["id"] not in seen:
            seen.add(item["id"])
            out.append(item)
    return out


# ─── Fuzzy search ─────────────────────────────────────────────────────────────

def _fuzzy_score(item: dict, query: str) -> int:
    if not query:
        return 1
    haystack = " ".join([
        item.get("id", ""),
        item.get("desc", ""),
        " ".join(item.get("tags", [])),
    ]).lower()
    terms = query.lower().split()
    score = 0
    for t in terms:
        if t not in haystack:
            return 0
        score += 3 if item.get("id", "").lower().startswith(t) else 1
    return score


def filter_catalogue(
    catalogue: list[dict],
    query: str = "",
    category: str = "All",
) -> list[dict]:
    filtered = [
        c for c in catalogue
        if (category == "All" or c.get("cat") == category)
    ]
    if query:
        scored = [(c, _fuzzy_score(c, query)) for c in filtered]
        scored = [(c, s) for c, s in scored if s > 0]
        scored.sort(key=lambda x: -x[1])
        return [c for c, _ in scored]
    return filtered


# ─── Status helpers ──────────────────────────────────────────────────────────

def _market_status() -> str:
    now = datetime.now()
    # IST offset +5:30 from UTC; crude local check
    h, m = now.hour, now.minute
    # Assume server is IST or adjust as needed
    total = h * 60 + m
    if 555 <= total <= 930:   # 09:15 – 15:30
        return "[bold green]OPEN[/bold green]"
    return "[dim]CLOSED[/dim]"


def _last_refresh() -> str:
    log_dir = _project_root / "logs"
    pattern = "daily_refresh_*.log"
    logs = sorted(log_dir.glob(pattern)) if log_dir.exists() else []
    if not logs:
        return "never"
    mtime = datetime.fromtimestamp(logs[-1].stat().st_mtime)
    return mtime.strftime("%Y-%m-%d %H:%M")


# ─── Tag colours ─────────────────────────────────────────────────────────────

_TAG_COLORS = {
    "chart": "blue", "technical": "blue",
    "screener": "green", "stage2": "green", "vcp": "green",
    "admin": "yellow", "pipeline": "yellow",
    "fno": "magenta", "options": "magenta", "derivatives": "magenta",
    "intraday": "cyan", "live": "cyan",
    "sector": "bright_yellow", "rotation": "bright_yellow",
    "llm": "red", "ric": "red", "strategy": "red",
    "portfolio": "bright_green",
    "report": "bright_blue",
}

def _tag_text(tag: str) -> Text:
    color = _TAG_COLORS.get(tag, "bright_black")
    t = Text()
    t.append(f" {tag} ", style=f"bold {color} on grey11")
    return t


# ─── Rendering ────────────────────────────────────────────────────────────────

def render_table(items: list[dict], selected: int, max_rows: int = 30) -> Table:
    tbl = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold bright_white",
        expand=True,
        show_footer=False,
        padding=(0, 1),
    )
    tbl.add_column("#",    style="dim",          width=4,  no_wrap=True)
    tbl.add_column("ID",   style="bold cyan",    width=28, no_wrap=True)
    tbl.add_column("Category", style="dim",      width=10, no_wrap=True)
    tbl.add_column("Description",                ratio=1)
    tbl.add_column("Tags",                       width=24, no_wrap=True)

    visible = items[:max_rows]
    for i, item in enumerate(visible):
        is_sel = (i == selected)
        row_style = Style(bgcolor="grey19") if is_sel else Style()
        num = Text(f"{'▶ ' if is_sel else '  '}{i+1}", style="bold yellow" if is_sel else "dim")
        id_text = Text(item["id"], style="bold bright_cyan" if is_sel else "cyan")
        cat_text = Text(item.get("cat", ""), style="dim")
        desc = item.get("desc", "")
        desc_text = Text(desc[:90], style="bright_white" if is_sel else "white")
        tags_text = Text()
        for t in item.get("tags", [])[:3]:
            color = _TAG_COLORS.get(t, "bright_black")
            tags_text.append(f"[{t}] ", style=color)
        tbl.add_row(num, id_text, cat_text, desc_text, tags_text, style=row_style)

    if len(items) > max_rows:
        tbl.add_row("", Text(f"… {len(items)-max_rows} more (refine search)", style="dim"), "", "", "")
    return tbl


def render_detail(item: dict | None) -> Panel:
    if item is None:
        return Panel(Text("No command selected", style="dim"), title="Detail", border_style="grey30")

    lines = Text()
    lines.append(item["id"] + "\n", style="bold bright_cyan")
    lines.append(item.get("desc", "") + "\n\n", style="bright_white")
    lines.append("Category:  ", style="dim")
    lines.append(item.get("cat", "") + "\n", style="yellow")
    lines.append("Tags:      ", style="dim")
    for t in item.get("tags", []):
        color = _TAG_COLORS.get(t, "bright_black")
        lines.append(f"[{t}] ", style=color)
    lines.append("\n\n")
    lines.append("CLI Command:\n", style="dim")
    lines.append("  " + item.get("cli", "") + "\n", style="bold green")
    return Panel(lines, title="[bold]Detail[/bold]", border_style="bright_blue", padding=(1, 2))


def render_status(catalogue: list, filtered: list, query: str, category: str) -> Text:
    t = Text()
    t.append("Agent Adda", style="bold bright_cyan")
    t.append(" · Command Centre  ", style="dim")
    t.append("Market: ", style="dim")
    t.append(_market_status() + "  ", style="")
    t.append("Last refresh: ", style="dim")
    t.append(_last_refresh() + "  ", style="bright_yellow")
    t.append(f"{len(filtered)}/{len(catalogue)} commands", style="dim")
    if query:
        t.append(f"  [search: {query}]", style="italic cyan")
    t.append(f"  [tab: {category}]", style="dim")
    return t


def render_help() -> Text:
    keys = [
        ("↑↓", "Navigate"),
        ("Enter", "Copy CLI & run"),
        ("Tab", "Next category"),
        ("Esc", "Clear search"),
        ("/", "Start search"),
        ("q", "Quit"),
        ("F5", "Refresh catalogue"),
    ]
    t = Text()
    for key, desc in keys:
        t.append(f" {key} ", style="bold yellow on grey11")
        t.append(f" {desc}   ", style="dim")
    return t


# ─── Interactive TUI ─────────────────────────────────────────────────────────

def run_tui() -> None:
    try:
        import tty
        import termios
        import select as _select
        _HAS_TTY = True
    except ImportError:
        _HAS_TTY = False

    if not _HAS_TTY or not sys.stdin.isatty():
        # Fallback: simple non-interactive listing
        catalogue = build_catalogue()
        console.print(f"[bold cyan]Agent Adda Command Centre[/bold cyan] — {len(catalogue)} commands\n")
        for item in catalogue:
            console.print(f"  [cyan]{item['id']:<30}[/cyan] [dim]{item['cat']:<12}[/dim] {item['desc'][:70]}")
        return

    catalogue = build_catalogue()
    query = ""
    cat_idx = 0
    sel_idx = 0
    search_mode = False

    def current_filtered():
        return filter_catalogue(catalogue, query, CATEGORIES[cat_idx])

    def make_layout(filtered: list) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=1),
            Layout(name="body"),
            Layout(name="detail", size=10),
            Layout(name="footer", size=1),
        )
        layout["body"].update(
            Panel(
                render_table(filtered, sel_idx),
                title=f"[bold] Commands [/bold]  [dim]{' · '.join(CATEGORIES)}[/dim]",
                border_style="bright_blue",
                padding=(0, 0),
            )
        )
        sel = filtered[sel_idx] if filtered and sel_idx < len(filtered) else None
        layout["detail"].update(render_detail(sel))
        layout["header"].update(render_status(catalogue, filtered, query, CATEGORIES[cat_idx]))
        layout["footer"].update(render_help())
        return layout

    def read_key(fd: int) -> str:
        ch = os.read(fd, 1).decode("utf-8", errors="replace")
        if ch == "\x1b":
            try:
                ch2 = os.read(fd, 1).decode("utf-8", errors="replace")
                ch3 = os.read(fd, 1).decode("utf-8", errors="replace")
                return ch + ch2 + ch3
            except Exception:
                return ch
        return ch

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        tty.setraw(fd)
        with Live(make_layout(current_filtered()), refresh_per_second=10, screen=True) as live:
            while True:
                filtered = current_filtered()
                sel_idx = max(0, min(sel_idx, len(filtered) - 1))
                live.update(make_layout(filtered))

                # Wait for a keypress with timeout for live refresh
                r, _, _ = _select.select([sys.stdin], [], [], 0.15)
                if not r:
                    continue

                key = read_key(fd)

                # Arrow keys (ANSI: ESC [ A/B)
                if key == "\x1b[A":       # up
                    sel_idx = max(0, sel_idx - 1)
                elif key == "\x1b[B":     # down
                    sel_idx = min(len(filtered) - 1, sel_idx + 1)
                elif key == "\t":         # Tab — next category
                    cat_idx = (cat_idx + 1) % len(CATEGORIES)
                    sel_idx = 0
                elif key == "\r":         # Enter — copy CLI
                    if filtered and sel_idx < len(filtered):
                        item = filtered[sel_idx]
                        cli = item.get("cli", "")
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                        live.stop()
                        console.print(f"\n[bold bright_cyan]Selected:[/bold bright_cyan] {item['id']}")
                        console.print(f"[bold green]CLI:[/bold green] {cli}")
                        console.print("\n[dim]Press Enter to run in a subshell, or Ctrl+C to cancel…[/dim]")
                        try:
                            inp = input()
                            if inp.strip().lower() not in ("n", "no", "cancel"):
                                # Expand SYMBOL placeholder
                                run_cli = cli
                                if "SYMBOL" in run_cli:
                                    sym = input("  Symbol (e.g. RELIANCE): ").strip().upper() or "RELIANCE"
                                    run_cli = run_cli.replace("SYMBOL", sym)
                                # If it contains '→' (REPL shortcut), just print it
                                if "→" in run_cli:
                                    console.print(f"\n[dim]In the REPL, type:[/dim] [bold]{run_cli.split('→')[1].strip()}[/bold]")
                                else:
                                    console.print(f"\n[dim]Running:[/dim] [green]{run_cli}[/green]")
                                    handle = None
                                    if _EPISODES:
                                        handle = _EPISODES.start_episode(
                                            goal=f"command_center tui {item.get('id')}",
                                            caller="command_center",
                                            tags=["command_center", "tui", str(item.get("cat") or "").lower()],
                                            metadata={"id": item.get("id"), "cli": run_cli},
                                        )
                                        _EPISODES.log_step(
                                            handle,
                                            step="execute",
                                            tool_name="subprocess.run",
                                            tool_args={"cli": run_cli, "cwd": str(_project_root)},
                                        )
                                    env = os.environ.copy()
                                    if handle:
                                        env["AGENT_ADDA_EPISODE_ID"] = handle.episode_id
                                    res = subprocess.run(run_cli, shell=True, cwd=str(_project_root), env=env)
                                    if _EPISODES and handle:
                                        _EPISODES.log_step(
                                            handle,
                                            step="completed",
                                            tool_name="subprocess.run",
                                            status="ok" if res.returncode == 0 else "error",
                                            result={"returncode": res.returncode},
                                        )
                                        _EPISODES.end_episode(
                                            handle,
                                            status="SUCCESS" if res.returncode == 0 else "FAILED",
                                            summary=f"{item.get('id')} returncode={res.returncode}",
                                            metadata={"returncode": res.returncode},
                                        )
                        except KeyboardInterrupt:
                            pass
                        return

                elif key == "\x1b":       # Escape
                    if search_mode:
                        query = ""
                        search_mode = False
                        sel_idx = 0
                    else:
                        break

                elif key == "q" and not search_mode:
                    break

                elif key == "/":
                    search_mode = True
                    # Switch to simple input for search
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    live.stop()
                    q = input("  Search: ").strip()
                    tty.setraw(fd)
                    query = q
                    sel_idx = 0
                    live.start()

                elif key == "\x7f" and search_mode:  # Backspace
                    query = query[:-1]
                    sel_idx = 0

                elif key.isprintable() and len(key) == 1 and search_mode:
                    query += key
                    sel_idx = 0

                # F5 (refresh catalogue)
                elif key == "\x1b[15~":
                    catalogue = build_catalogue()
                    sel_idx = 0

    except KeyboardInterrupt:
        pass
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            pass

    console.print("\n[dim]Agent Adda Command Centre — bye![/dim]")


# ─── CLI modes ────────────────────────────────────────────────────────────────

def cmd_list() -> None:
    catalogue = build_catalogue()
    print(json.dumps(catalogue, indent=2))


def cmd_run(skill_id: str, extra_args: list[str]) -> None:
    catalogue = build_catalogue()
    item = next((c for c in catalogue if c["id"] == skill_id), None)
    if not item:
        console.print(f"[red]Unknown command:[/red] {skill_id}")
        console.print(f"[dim]Available: {', '.join(c['id'] for c in catalogue[:20])}…[/dim]")
        sys.exit(1)
    cli = item["cli"]
    if "SYMBOL" in cli and extra_args:
        cli = cli.replace("SYMBOL", extra_args[0])
    if "→" in cli:
        console.print(f"[yellow]REPL shortcut:[/yellow] {cli.split('→')[1].strip()}")
        console.print("[dim]Start nse_agent.py and type the command above.[/dim]")
    else:
        console.print(f"[dim]Running:[/dim] [green]{cli}[/green]")
        handle = None
        if _EPISODES:
            handle = _EPISODES.start_episode(
                goal=f"command_center run {skill_id}",
                caller="command_center",
                tags=["command_center", "run", str(item.get("cat") or "").lower()],
                metadata={"id": skill_id, "cli": cli, "extra_args": extra_args},
            )
            _EPISODES.log_step(handle, step="execute", tool_name="subprocess.run", tool_args={"cli": cli, "cwd": str(_project_root)})
        env = os.environ.copy()
        if handle:
            env["AGENT_ADDA_EPISODE_ID"] = handle.episode_id
        result = subprocess.run(cli, shell=True, cwd=str(_project_root), env=env)
        if _EPISODES and handle:
            _EPISODES.log_step(handle, step="completed", tool_name="subprocess.run", status="ok" if result.returncode == 0 else "error",
                               result={"returncode": result.returncode})
            _EPISODES.end_episode(handle, status="SUCCESS" if result.returncode == 0 else "FAILED",
                                  summary=f"{skill_id} returncode={result.returncode}",
                                  metadata={"returncode": result.returncode})
        sys.exit(result.returncode)


def main() -> None:
    ap = argparse.ArgumentParser(description="Agent Adda Command Centre")
    ap.add_argument("--list", action="store_true", help="Dump full catalogue as JSON and exit")
    ap.add_argument("--run", metavar="SKILL_ID", help="Run a command by its ID")
    ap.add_argument("args", nargs="*", help="Extra args passed to the skill (e.g. SYMBOL)")
    opts = ap.parse_args()

    if opts.list:
        cmd_list()
    elif opts.run:
        cmd_run(opts.run, opts.args)
    else:
        run_tui()


if __name__ == "__main__":
    main()
