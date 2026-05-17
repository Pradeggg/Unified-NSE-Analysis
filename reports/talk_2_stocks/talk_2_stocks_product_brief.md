# Talk 2 Stocks: Your Personal AI Assistant for Market Intelligence

**Product brief for AI and product builders**  
**Date:** 2026-05-09  
**System:** Agent Adda / `nse_agent.py`  
**Positioning:** Research and learning assistant, not a trading recommendation engine.

## Executive Summary

Most market AI demos start with a simple promise: ask any question about a stock. Real research rarely works that way.

Market intelligence is a repeated workflow. A user has to understand the market state, pick the right data mode, retrieve evidence, inspect technical context, compare sectors, check global cues, review filings or events, and then synthesize a view with appropriate risk framing. Agent Adda, surfaced through `nse_agent.py`, turns that workflow into a terminal-first personal AI assistant.

The goal is not prediction. The value is disciplined synthesis, repeatable investigation, faster navigation across scattered artifacts, and a clearer path from question to evidence-backed view.

## Why We Built It

Market research is fragmented. Indices live in one place, stock-level data in another, sector rotation in another, corporate events in another, and global context somewhere else. Even when the data exists locally, the workflow is repetitive: open reports, scan screeners, compare symbols, inspect indicators, write notes, and remember what to check next.

Large language models help with synthesis, but a chat box alone is not enough. Market intelligence needs tools, rules, data freshness, context routing, and reusable research recipes. Agent Adda exists to combine these pieces into one working assistant.

## What Agent Adda Is

Agent Adda is a terminal-first AI market intelligence assistant for NSE-first workflows, with expanding support for US and global market context. It combines natural language questions, slash commands, curated prompts, Recursive Investigative Conversations (RICs), technical screeners, HTML reports, and local data tools.

At the center is `nse_agent.py`, the interactive research terminal. The terminal exposes chat, command shortcuts, data-mode controls, prompt libraries, scan workflows, monitor hooks, and report generation surfaces.

![Agent Adda terminal startup and help](assets/nse_agent_research_help.png)

*The `nse_agent.py` terminal shows the product surface: natural language entry, slash commands, market research prompts, help output, and the research-only disclaimer.*

## Core Product Capabilities

- **Natural language research:** Ask about stocks, indices, sectors, screeners, or market conditions without remembering exact function names.
- **Mode-aware analysis:** Use `/live`, `/eod`, and `/auto` to control whether the assistant prioritizes intraday/live context, historical snapshots, or automatic routing.
- **Screeners and scans:** Run rule-based research screens for Stage 2 setups, breakouts, momentum, Supertrend, VCP, relative strength, and market breadth.
- **Prompt library:** Use curated prompts for recurring analyst workflows such as market pulse, sector health, technical setup, stock deep dive, and portfolio review.
- **RIC workflows:** Turn vague research goals into multi-step investigations such as Sherlock stock deep dive, Sector X-Ray, Breakout Hunter, Earnings Playbook, Index Pulse, Peer Battle, Risk Radar, and Morning Intel.
- **Report generation:** Produce HTML/PDF-style research artifacts for sector rotation, stage tracking, global market context, and product QA views.
- **Filing intelligence:** Support research around PDFs, XBRL/iXBRL, and evidence-backed summaries for financial documents.

![Agent Adda command-line modes](assets/nse_agent_cli_help.png)

*The CLI help view documents non-interactive query mode, trace mode, data-mode selection, briefing controls, themes, and layout scale.*

## Solution Architecture

Agent Adda is easiest to understand as a workflow assistant with five layers.

1. **Input layer:** natural language, slash commands, prompt-library entries, and RIC recipes.
2. **Orchestration layer:** intent detection, mode selection, context/session state, tool routing, and follow-up handling.
3. **Data layer:** historical CSV/SQLite, intraday SQLite, NSE/yfinance fallbacks, report artifacts, and filing documents.
4. **Analysis layer:** technical indicators, screeners, global context, corporate-event checks, filing extraction, and LLM synthesis.
5. **Output layer:** terminal answers, Markdown-style narratives, HTML reports, PDF reports, and exportable product briefs.

This architecture is deliberately practical. The assistant does not try to replace every market tool. It coordinates the repeated steps that usually sit between raw data and a usable research view.

## Evidence Surfaces and Reports

Agent Adda produces visual artifacts that make research easier to revisit and share. The screenshots below show local report surfaces used as evidence and product examples.

![Sector rotation report](assets/sector_rotation_report.png)

*The sector rotation report turns market breadth, rotation, and technical context into a reusable research artifact.*

![Stage 2 tracker](assets/stage2_tracker.png)

*The Stage 2 tracker focuses the workflow on leadership, trend quality, relative strength, and setup readiness.*

![US and global market report](assets/us_market_report.png)

*The US/global report adds overnight context, risk regime, and India read-through to an NSE-first workflow.*

![Product POV companion](assets/talk_2_stocks_pov_companion.png)

*The POV companion summarizes the article structure, architecture story, and screenshot plan for the LinkedIn/product narrative.*

## Why RIC Matters

RIC stands for Recursive Investigative Conversations. The point is simple: market research often requires sequence.

A one-shot prompt can answer a narrow question, but it does not reliably guide a user through the whole investigation. A RIC can start with a broad question, break it into sub-questions, retrieve evidence, compare alternatives, refine the hypothesis, and produce a final view with caveats.

Examples include:

- **Sherlock stock deep dive:** inspect company, technicals, events, filings, peers, and risk.
- **Sector X-Ray:** compare sector breadth, leaders, laggards, rotation, and catalysts.
- **Breakout Hunter:** identify technical breakouts with confirmation and invalidation levels.
- **Earnings Playbook:** organize pre- and post-result research checks.
- **Index Pulse:** summarize index trend, breadth, support/resistance, and sector leadership.
- **Peer Battle:** compare several stocks across fundamentals, technicals, and relative strength.
- **Risk Radar:** inspect downside triggers, concentration, event risk, and weak evidence.
- **Morning Intel:** produce a structured market-prep workflow.

## Why Curated Prompts Matter

Prompt libraries reduce friction. Many users know what they want to investigate but do not want to remember the exact syntax, data mode, screener name, or tool chain.

Curated prompts encode recurring analyst questions. They also make the system more teachable: users can browse common workflows, run one, then adapt it to their own research style. This makes the assistant feel less like an empty chat box and more like an operating surface for market intelligence.

## How It Saves Time

Agent Adda saves time by reducing repeated navigation and synthesis work.

- It brings commands, reports, scans, prompts, and research flows into one terminal surface.
- It turns recurring analyst patterns into repeatable recipes.
- It generates structured summaries instead of leaving the user with raw tables only.
- It preserves report outputs that can be reviewed later.
- It supports a faster move from question to evidence-backed view.

The time saving is not just speed. It is consistency. A repeatable workflow is easier to audit, improve, and teach than an improvised series of browser tabs and ad hoc notes.

## Builder Takeaway

The durable value in applied AI agents is not the chat box. It is the tool-using, evidence-aware workflow around the chat box.

For market intelligence, that means an assistant that can route intent, choose data modes, run screeners, read reports, produce artifacts, and keep the user inside a disciplined research loop. Agent Adda is a working example of that product pattern.

## Research-Only Disclaimer

Agent Adda and Talk 2 Stocks are for research, education, and workflow exploration only. They are not investment advice, trading recommendations, financial planning, or a substitute for independent judgement, risk management, or regulatory obligations. Market data can be delayed, incomplete, stale, or incorrect. Users should verify evidence independently before making financial decisions.
