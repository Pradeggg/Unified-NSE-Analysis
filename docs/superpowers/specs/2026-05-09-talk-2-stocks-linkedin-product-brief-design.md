# Talk 2 Stocks LinkedIn Product Brief Design

Date: 2026-05-09
Owner: Agent Adda / Codex
Audience: AI and product builders
Primary output: LinkedIn article plus product brief

## Goal

Create a polished point-of-view document for LinkedIn titled:

**Talk 2 Stocks: Your Personal AI Assistant for Market Intelligence**

The document should explain Agent Adda as a working example of applied AI agents for market intelligence. It should be practical and credible for AI/product builders: less of a marketing brochure, more of a product-builder narrative showing why the system exists, what it can do, how it is architected, and how it saves research time.

The final deliverables are:

- A Microsoft Word document.
- A PDF version of the same brief.
- A screenshot asset folder with captured examples from the product.
- A LinkedIn-ready short-form post extracted from the longer brief.

## Positioning

Agent Adda should be positioned as a personal AI market intelligence assistant, not as a trading recommendation engine.

Core message:

> Market research is not a single question-answering problem. It is a repeated workflow of situation assessment, data retrieval, rule-based screening, technical context, global context, evidence gathering, and synthesis. Agent Adda turns that workflow into a conversational and command-driven assistant.

The narrative must clearly state:

- This is a learning and research system.
- It is not investment advice.
- It does not replace judgement, risk management, or regulatory obligations.
- The value is disciplined synthesis and time saved, not prediction.

## Document Shape

Target length: 5 to 8 pages.

Tone:

- Builder-oriented.
- Clear, confident, and specific.
- Avoid hype and generic "AI will transform everything" language.
- Use concrete examples from the repo and current product surfaces.

Recommended sections:

1. **Why We Built It**
   - Market intelligence is scattered across indices, stocks, screeners, filings, sector reports, global markets, and intraday signals.
   - Manual workflows are slow and inconsistent.
   - AI alone is not enough; the system needs tools, rules, data freshness, and repeatable workflows.

2. **What Agent Adda Is**
   - A terminal-first personal AI assistant for market intelligence.
   - Combines natural language, slash commands, curated prompts, RIC workflows, screeners, reports, and data tools.
   - Supports NSE-first workflows with emerging US/global market intelligence.

3. **Core Features**
   - Natural language market research.
   - `/live`, `/eod`, and `/auto` data modes.
   - `/scan` intraday screeners.
   - `/monitor` background alert monitors.
   - `/prompts` curated prompt library.
   - `/ric` recursive investigative conversations.
   - Sector rotation reports.
   - Stage 2 tracker.
   - US/global market report and India read-through.
   - Financial filing intelligence for PDFs/XBRL/iXBRL.

4. **Capabilities**
   - Situation assessment and intent detection.
   - Symbol and index resolution.
   - Tool routing.
   - EOD and intraday analysis.
   - Technical indicators: RSI, MACD, SMA, VWAP proxy, Supertrend, VCP, support/resistance, relative strength.
   - Rules-based screeners.
   - LLM-based synthesis and narrative generation.
   - HTML/PDF report generation.
   - Session-oriented research flow.

5. **Why RIC Matters**
   - RIC stands for Recursive Investigative Conversations.
   - RICs turn vague market questions into repeatable multi-step research recipes.
   - Examples: Sherlock stock deep dive, Sector X-Ray, Breakout Hunter, Earnings Playbook, Index Pulse, Peer Battle, Risk Radar, Morning Intel.
   - RICs are useful because market research often requires sequence, not one-shot prompting.

6. **Why Curated Prompts Matter**
   - Prompt libraries reduce friction for recurring workflows.
   - They encode common analyst questions.
   - They make the assistant usable by people who know what they want to investigate but do not want to remember exact commands.

7. **Solution Architecture**
   - Input layer: natural language, slash commands, prompt library, RIC recipes.
   - Orchestration layer: mode selection, intent detection, context/session state, tool routing.
   - Data layer: historical CSV/SQLite, intraday SQLite, NSE/yfinance fallbacks, report artifacts, filing documents.
   - Analysis layer: technical indicators, rules-based screeners, global context, corporate events, filing extraction, LLM synthesis.
   - Output layer: terminal response, HTML reports, PDF reports, Word/PDF product brief exports.

8. **Screenshots and Examples**
   - Bloomberg-style terminal overview.
   - Sector rotation report.
   - Stage 2 tracker.
   - US/global market report.
   - RIC library or terminal help view.
   - Prompt library.
   - Financial filing intelligence design/report example.

9. **How It Saves Time**
   - Replaces repeated navigation across multiple tools and files.
   - Turns recurring analysis patterns into commands and recipes.
   - Generates structured summaries instead of raw tables only.
   - Creates reusable reports with charts, narratives, and disclaimers.
   - Helps users move from question to evidence-backed view faster.

10. **LinkedIn Closing POV**
    - A concise reflection on applied AI agents: the durable value is not a chat box, but a tool-using, evidence-aware workflow assistant.

## Screenshot Plan

Screenshots should be captured with Playwright where possible, from local HTML files or locally rendered pages.

Preferred assets:

- `reports/latest/sector_rotation.html`
- `reports/sector_rotation/stage2_tracker_2026-05-07.html`
- `reports/latest/us_market_report.html`
- `reports/global/us_market_report_20260508.html`
- `reports/qa/talk_2_stocks_pov_companion.html`

Terminal screenshots can be handled in one of two ways:

- Preferred: generate a static HTML mock of the terminal surface based on current command/help output, then capture it with Playwright.
- Fallback: include existing user-provided terminal screenshots only if they are available as local files.

Screenshot output directory:

- `reports/talk_2_stocks/assets/`

Screenshots should be descriptive and captioned in the document. The brief should not rely on screenshots alone; each screenshot needs a short explanation of what capability it demonstrates.

## Document Generation Approach

Use a generated Markdown source as the canonical content, then export to Word and PDF.

Planned files:

- `reports/talk_2_stocks/talk_2_stocks_product_brief.md`
- `reports/talk_2_stocks/talk_2_stocks_product_brief.docx`
- `reports/talk_2_stocks/talk_2_stocks_product_brief.pdf`
- `reports/talk_2_stocks/linkedin_post.md`
- `reports/talk_2_stocks/assets/*.png`

Recommended conversion path:

1. Capture screenshots with Playwright.
2. Build the Markdown brief with image references and captions.
3. Convert Markdown to DOCX with Pandoc.
4. Convert DOCX or Markdown to PDF using the best available local tool.
5. If PDF conversion is unavailable, produce HTML and use browser print/PDF export as fallback.

## LinkedIn Post Extraction

The short LinkedIn post should be a separate artifact, not just the first page of the brief.

It should contain:

- A strong opening hook.
- Why the project exists.
- The product idea: "Talk 2 Stocks."
- 5 to 7 concrete capabilities.
- A builder insight about AI agents and workflows.
- A clear research-only disclaimer.

The LinkedIn post should avoid:

- Stock recommendations.
- Claims of predictive accuracy.
- Regulatory ambiguity.
- Overpromising automation or trading outcomes.

## Acceptance Criteria

The implementation is complete when:

- The Word document exists and opens locally.
- The PDF exists and opens locally.
- The Markdown source exists.
- The LinkedIn post exists as a separate Markdown file.
- At least four screenshots are included in the brief.
- The document includes:
  - Why we built it.
  - Features.
  - Capabilities.
  - Solution architecture.
  - Why RIC matters.
  - Why curated prompts matter.
  - How it saves time.
  - Research-only / not-investment-advice disclaimer.
- Screenshot captions explain the capability being shown.
- Playwright-based capture is used for local HTML/report screenshots.
- Generated artifacts are placed under `reports/talk_2_stocks/`.

## Out of Scope

- Publishing directly to LinkedIn.
- Creating a public marketing website.
- Building new Agent Adda product features.
- Making claims about financial performance or trade recommendations.
- Using live brokerage integrations.

## Risks and Mitigations

- **Risk: screenshots are visually stale or too dense.**
  - Mitigation: use report screenshots plus a purpose-built terminal/product overview mock if needed.

- **Risk: PDF conversion fails on local dependencies.**
  - Mitigation: keep Markdown and DOCX as canonical outputs and add HTML/PDF fallback generation.

- **Risk: article reads like an investment product.**
  - Mitigation: include explicit research-only framing and avoid trading recommendation language.

- **Risk: document becomes too long for LinkedIn.**
  - Mitigation: produce both the product brief and a separate LinkedIn post.

## Spec Self-Review

- No placeholders remain.
- Scope is limited to content, screenshots, and document generation.
- The audience is explicit: AI/product builders.
- The selected format is explicit: LinkedIn article plus product brief.
- The document is positioned as research and learning only, not investment advice.
