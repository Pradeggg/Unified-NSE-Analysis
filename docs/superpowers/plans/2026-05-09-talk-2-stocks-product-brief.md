# Talk 2 Stocks Product Brief Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a comprehensive Talk 2 Stocks product brief with terminal screenshots of `nse_agent.py`, product/report screenshots, DOCX/PDF exports, and a LinkedIn-ready post.

**Architecture:** Use the existing spec as source requirements, generate screenshots from local HTML/report surfaces plus terminal-styled captures of real `nse_agent.py` command output, then assemble a canonical Markdown brief. Export Markdown to DOCX with Pandoc and to PDF through browser/Pandoc fallback.

**Tech Stack:** Python 3, Playwright via `npx`, Pandoc, local HTML reports, Markdown, DOCX/PDF.

---

### Task 1: Prepare Output Structure

**Files:**
- Create: `reports/talk_2_stocks/`
- Create: `reports/talk_2_stocks/assets/`
- Create: `reports/talk_2_stocks/terminal_captures/`

- [ ] **Step 1: Create directories**

Run:

```bash
mkdir -p reports/talk_2_stocks/assets reports/talk_2_stocks/terminal_captures
```

Expected: directories exist.

### Task 2: Capture Terminal Evidence

**Files:**
- Read: `nse_agent.py`
- Create: `reports/talk_2_stocks/terminal_captures/*.txt`
- Create: `reports/talk_2_stocks/assets/nse_agent_*.png`

- [ ] **Step 1: Capture real command output**

Run selected non-interactive commands such as:

```bash
python3 nse_agent.py --help
python3 nse_agent.py -q "/help"
python3 nse_agent.py -q "Explain what Agent Adda can do for market research"
```

Expected: terminal text captures show banner/help/query surfaces without requiring interactive input.

- [ ] **Step 2: Render terminal screenshots**

Render the text captures into terminal-styled HTML and capture screenshots with Playwright.

Expected: at least two PNG screenshots showing `nse_agent.py` in a terminal-like surface.

### Task 3: Capture Product Screenshots

**Files:**
- Read: `reports/latest/sector_rotation.html`
- Read: `reports/sector_rotation/stage2_tracker_2026-05-07.html`
- Read: `reports/latest/us_market_report.html`
- Read: `reports/qa/talk_2_stocks_pov_companion.html`
- Create: `reports/talk_2_stocks/assets/*.png`

- [ ] **Step 1: Capture local HTML surfaces**

Use Playwright to capture full-page screenshots from local HTML files.

Expected: at least four total screenshots are available for the brief.

### Task 4: Write Brief and LinkedIn Post

**Files:**
- Create: `reports/talk_2_stocks/talk_2_stocks_product_brief.md`
- Create: `reports/talk_2_stocks/linkedin_post.md`

- [ ] **Step 1: Build Markdown brief**

Use the approved spec sections: why built, what it is, features, capabilities, architecture, RIC, curated prompts, screenshots, time saved, and disclaimer.

Expected: Markdown includes screenshot references and captions.

- [ ] **Step 2: Build LinkedIn post**

Extract a concise post with hook, product idea, concrete capabilities, builder insight, and research-only disclaimer.

Expected: separate LinkedIn-ready Markdown file exists.

### Task 5: Export and Verify

**Files:**
- Create: `reports/talk_2_stocks/talk_2_stocks_product_brief.docx`
- Create: `reports/talk_2_stocks/talk_2_stocks_product_brief.pdf`

- [ ] **Step 1: Export DOCX**

Run:

```bash
pandoc reports/talk_2_stocks/talk_2_stocks_product_brief.md -o reports/talk_2_stocks/talk_2_stocks_product_brief.docx
```

Expected: DOCX exists and is non-empty.

- [ ] **Step 2: Export PDF**

Use Pandoc or browser print-to-PDF fallback.

Expected: PDF exists and is non-empty.

- [ ] **Step 3: Verify artifacts**

Run:

```bash
ls -lh reports/talk_2_stocks
find reports/talk_2_stocks/assets -type f
```

Expected: Markdown, LinkedIn post, DOCX, PDF, and at least four PNG assets exist.

## Self-Review

- Spec coverage: plan covers the document, screenshots, LinkedIn post, Word export, and PDF export.
- Placeholder scan: no TODO/TBD placeholders remain.
- Scope check: this is a document-generation task; no product feature work is included.
