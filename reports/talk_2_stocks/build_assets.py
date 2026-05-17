#!/usr/bin/env python3
"""Build Talk 2 Stocks document sources and terminal HTML assets."""

from __future__ import annotations

import html
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "talk_2_stocks"
ASSETS = OUT / "assets"
CAPTURES = OUT / "terminal_captures"


def _clean_terminal(text: str, max_lines: int | None = None) -> str:
    text = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)
    text = text.replace("\r", "\n")
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned: list[str] = []
    last = ""
    spinner_seen = 0
    for line in lines:
        if "Agent Adda is thinking" in line:
            spinner_seen += 1
            if spinner_seen > 2:
                continue
        if line == "" and last == "":
            continue
        cleaned.append(line)
        last = line
    if max_lines:
        cleaned = cleaned[:max_lines]
    return "\n".join(cleaned).strip() + "\n"


def _terminal_html(title: str, subtitle: str, body: str) -> str:
    safe = html.escape(body)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #071018;
      --chrome: #111d2a;
      --line: #26384a;
      --ink: #d6e6f2;
      --muted: #8ea4b8;
      --green: #55d88a;
      --yellow: #ffd166;
      --blue: #79b8ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      background: #071018;
      color: var(--ink);
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      padding: 32px;
    }}
    .terminal {{
      width: min(1320px, calc(100vw - 64px));
      min-height: calc(100vh - 64px);
      margin: 0 auto;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #08131d;
      box-shadow: 0 24px 80px rgba(0, 0, 0, .45);
      overflow: hidden;
    }}
    .bar {{
      height: 42px;
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 0 16px;
      background: var(--chrome);
      border-bottom: 1px solid var(--line);
      color: var(--muted);
      font-size: 13px;
    }}
    .dot {{ width: 11px; height: 11px; border-radius: 999px; display: inline-block; }}
    .red {{ background: #ff5f57; }}
    .amber {{ background: #febc2e; }}
    .green {{ background: #28c840; }}
    .title {{ margin-left: 12px; color: var(--ink); font-weight: 700; }}
    .subtitle {{ margin-left: auto; color: var(--muted); }}
    pre {{
      margin: 0;
      padding: 24px 28px 30px;
      white-space: pre-wrap;
      font-size: 14px;
      line-height: 1.48;
    }}
    .prompt {{ color: var(--green); }}
  </style>
</head>
<body>
  <section class="terminal">
    <div class="bar">
      <span class="dot red"></span><span class="dot amber"></span><span class="dot green"></span>
      <span class="title">{html.escape(title)}</span>
      <span class="subtitle">{html.escape(subtitle)}</span>
    </div>
    <pre>{safe}</pre>
  </section>
</body>
</html>
"""


def write_terminal_html() -> None:
    help_text = _clean_terminal((CAPTURES / "nse_agent_help.txt").read_text(), 36)
    query_text = _clean_terminal((CAPTURES / "nse_agent_query_help.txt").read_text(), 92)
    (OUT / "terminal_nse_agent_cli_help.html").write_text(
        _terminal_html(
            "nse_agent.py --help",
            "CLI options and modes",
            "$ ./.venv/bin/python nse_agent.py --help\n\n" + help_text,
        )
    )
    (OUT / "terminal_nse_agent_research_help.html").write_text(
        _terminal_html(
            "nse_agent.py -q /help",
            "Agent Adda research terminal",
            "$ ./.venv/bin/python nse_agent.py -q \"/help\"\n\n" + query_text,
        )
    )


def write_documents() -> None:
    brief = """# Talk 2 Stocks: Your Personal AI Assistant for Market Intelligence

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
"""

    linkedin = """# LinkedIn Post

Most market AI demos start with: "Ask any question about a stock."

But real market research rarely works that way.

It is a workflow:
scan the market, check breadth, compare sectors, inspect setups, review filings, bring in global context, then synthesize a view without pretending it is a prediction.

That is the idea behind **Talk 2 Stocks**, built on Agent Adda.

It is a personal AI assistant for market intelligence, surfaced through a terminal-first product called `nse_agent.py`.

What it can do:

- answer natural-language market research questions
- switch between live, EOD, and auto data modes
- run screeners for momentum, Stage 2, breakouts, VCP, Supertrend, and relative strength
- use curated prompt libraries for repeatable analyst workflows
- guide deeper research through Recursive Investigative Conversations
- generate reusable sector, stage-tracking, and global market reports
- support filing-oriented research across PDFs/XBRL-style documents

The lesson for AI builders: the durable product value is not "chat with data."

It is a tool-using workflow assistant that helps users move from question to evidence-backed view faster and more consistently.

Research and learning only. Not investment advice, not a trading recommendation engine, and not a replacement for independent judgement or risk management.
"""

    (OUT / "talk_2_stocks_product_brief.md").write_text(brief)
    (OUT / "linkedin_post.md").write_text(linkedin)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    CAPTURES.mkdir(parents=True, exist_ok=True)
    write_terminal_html()
    write_documents()


if __name__ == "__main__":
    main()
