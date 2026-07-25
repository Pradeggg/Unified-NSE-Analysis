# Agent Adda Decision Engine POV Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Revise the EOD signal-effectiveness research paper so it leads with the Agent Adda product POV: from scanner to conditional decision engine.

**Architecture:** This is a documentation/report rewrite. The Markdown paper is the source of truth, and the HTML file is regenerated from Markdown with `pandoc`. No research numbers, backtest logic, or scanner code changes are in scope.

**Tech Stack:** Markdown, Pandoc, local Agent Adda report artifacts under `reports/signal_effectiveness/`.

---

### Task 1: Rewrite The Report POV

**Files:**
- Modify: `reports/latest/agent_adda_eod_signal_effectiveness_research_paper_20260622.md`

- [ ] **Step 1: Open the current paper and source spec**

Run:

```bash
sed -n '1,460p' reports/latest/agent_adda_eod_signal_effectiveness_research_paper_20260622.md
sed -n '1,220p' docs/superpowers/specs/2026-06-22-agent-adda-decision-engine-pov-design.md
```

Expected: the current paper includes the existing "The Conditional Edge Engine" title and the spec includes the approved "From Scanner To Decision Engine" POV.

- [ ] **Step 2: Replace the title and opening block**

Update the top of `reports/latest/agent_adda_eod_signal_effectiveness_research_paper_20260622.md` so it begins with:

```markdown
# From Scanner To Decision Engine

What 53,246 EOD Signals Taught Agent Adda About Conditional Edge
Agent Adda Research Paper - EOD Equity Setup Effectiveness
Generated: 2026-06-22
Primary study run: `reports/signal_effectiveness/signal_effectiveness_20260621_220118.md`
Latest EOD data date in study: 2026-06-19
```

Keep the research-only disclaimer immediately below the metadata block.

- [ ] **Step 3: Insert the product POV section after the disclaimer**

Add this section before `## Abstract`:

```markdown
## Point Of View

Agent Adda should not be another scanner.

A scanner asks whether a pattern appeared. A decision engine asks whether that pattern deserves action after regime, breadth, liquidity, cost, F&O context, and execution quality are considered.

That distinction is the product insight from this research. The study did not prove that every breakout or pullback should be traded. It proved the opposite: raw setup detection is not enough. Most familiar EOD setups showed small gross edges that were erased once realistic cost and slippage were applied.

The opportunity for Agent Adda is therefore not to generate more signals. The opportunity is to convert signals into decisions:

`Pattern -> Regime -> Breadth -> Liquidity -> Cost -> F&O -> Execution -> Action`

The output should not be a binary buy/sell label. It should be an action gate:

- `Block`
- `Watch`
- `Wait Retest`
- `Half Size`
- `Trade Candidate`
```

- [ ] **Step 4: Replace the abstract with product-led wording**

Replace the existing `## Abstract` section text with:

```markdown
## Abstract

This study tested whether common end-of-day equity setups in the Indian market have a durable forward edge when evaluated across a broad NIFTY 500 universe. The research used 53,246 labelled setup events across 496 symbols, covering the period from 2023-06-19 to 2026-06-05, with EOD data available through 2026-06-19. Each setup was evaluated over a 10-session forward horizon using a 2R target, stop, or timeout exit.

The uncomfortable finding is that many familiar setups show mildly positive gross expectancy, but most fail after realistic cost, liquidity, and slippage adjustments. That is not a dead end. It is the reason Agent Adda needs to be a decision engine rather than a scanner.

The edge is conditional. It appears only when the setup is filtered by market regime, breadth, liquidity, controlled volume confirmation, F&O context, and execution discipline. The research therefore shifts the product question from "which pattern triggered?" to "which triggered pattern should be promoted, downgraded, blocked, or carried forward as a retest watch?"
```

- [ ] **Step 5: Add a decision-stack architecture section before Live Gate Recommendations**

Insert this section immediately before `## Live Gate Recommendations`:

```markdown
## The Decision Stack

The report converts historical setup research into a live decision stack.

| Layer | Question | Example Output |
|---|---|---|
| Pattern | Did a known setup trigger? | `ema20_pullback_reclaim`, `relative_strength_breakout` |
| Regime | Has this setup worked in the current market regime? | favorable, mixed, unfavorable |
| Breadth | Is participation broad enough to support follow-through? | broad-positive, mixed, weak |
| Liquidity | Can the trade be executed without excessive impact? | liquid, mid, illiquid-spike |
| Cost | Does net expectancy survive estimated cost? | positive, marginal, negative |
| F&O | Does derivatives context support or crowd the move? | supportive, sideways, conflicting |
| Execution | Is the entry clean now or should it wait? | close, next-day confirmation, retest-hold |
| Action | What should the system publish? | block, watch, wait retest, half size, trade candidate |

This stack is where Agent Adda becomes a product rather than a table of signals. A candidate can trigger a pattern and still be blocked. Another can have weak aggregate performance but become relevant in the right breadth or VIX regime. The decision engine keeps both ideas true at the same time.
```

- [ ] **Step 6: Strengthen the Agent Adda Thesis section**

Find the `## The Agent Adda Thesis` section and replace the first half of the section through the bullet list with:

```markdown
## The Agent Adda Thesis

The research supports a thesis called the Conditional Edge Engine, but the more practical product framing is:

> Agent Adda is moving from scanner to decision engine.

Traditional scanners ask:

> Which stocks triggered a pattern today?

Agent Adda should ask:

> Which patterns have historically worked, in this regime, after cost, with this liquidity profile, and with this execution rule?

That shift changes the product:

- A breakout is evidence, not an instruction.
- A volume spike is context, not automatic confirmation.
- F&O alignment is an overlay, not a substitute for expectancy.
- Cost is part of the strategy, not an afterthought.
- Regime can upgrade, downgrade, or block a setup.
- The final output is an action gate, not a raw signal.
```

Keep the rest of the section if it does not duplicate the new bullets.

- [ ] **Step 7: Replace the LinkedIn takeaway**

Replace `## LinkedIn-Ready Takeaway` with:

```markdown
## LinkedIn-Ready Takeaway

We tested 53,246 EOD setup events across 496 NIFTY 500 stocks over nearly three years.

The uncomfortable result: most familiar breakout and pullback setups looked better before costs than after costs.

The product insight: Agent Adda should not be a scanner that simply says "pattern triggered."

It should be a decision engine that asks:

- Did the setup historically work?
- Did it work after costs?
- Did it work in this regime?
- Is breadth supportive?
- Is liquidity good enough?
- Is F&O confirming or crowding the move?
- Should the action be block, watch, wait retest, half size, or trade candidate?

The future is not more signals.

It is better decisions.
```

- [ ] **Step 8: Save and inspect the rewritten Markdown**

Run:

```bash
rg -n "From Scanner To Decision Engine|Point Of View|The Decision Stack|The Agent Adda Thesis|LinkedIn-Ready Takeaway|Source Trail" reports/latest/agent_adda_eod_signal_effectiveness_research_paper_20260622.md
sed -n '1,140p' reports/latest/agent_adda_eod_signal_effectiveness_research_paper_20260622.md
```

Expected: all listed sections are present, and the opening clearly frames the report as a scanner-to-decision-engine POV.

---

### Task 2: Regenerate HTML

**Files:**
- Modify: `reports/latest/agent_adda_eod_signal_effectiveness_research_paper_20260622.html`

- [ ] **Step 1: Regenerate the HTML from Markdown**

Run:

```bash
pandoc reports/latest/agent_adda_eod_signal_effectiveness_research_paper_20260622.md \
  -s \
  -o reports/latest/agent_adda_eod_signal_effectiveness_research_paper_20260622.html \
  --metadata title='From Scanner To Decision Engine - Agent Adda EOD Signal Effectiveness Research'
```

Expected: command exits with status 0 and rewrites the HTML file.

- [ ] **Step 2: Verify the generated files**

Run:

```bash
ls -lh reports/latest/agent_adda_eod_signal_effectiveness_research_paper_20260622.md \
       reports/latest/agent_adda_eod_signal_effectiveness_research_paper_20260622.html
rg -n "From Scanner To Decision Engine|Point Of View|The Decision Stack|The future is not more signals" \
  reports/latest/agent_adda_eod_signal_effectiveness_research_paper_20260622.md \
  reports/latest/agent_adda_eod_signal_effectiveness_research_paper_20260622.html
```

Expected: both files exist, and the POV phrases appear in both Markdown and HTML.

---

### Task 3: Final Review

**Files:**
- Review: `reports/latest/agent_adda_eod_signal_effectiveness_research_paper_20260622.md`
- Review: `reports/latest/agent_adda_eod_signal_effectiveness_research_paper_20260622.html`

- [ ] **Step 1: Confirm research numbers were not changed incorrectly**

Run:

```bash
rg -n "53,246|496|2023-06-19|2026-06-05|2026-06-19|0.121|-0.010|-0.337" \
  reports/latest/agent_adda_eod_signal_effectiveness_research_paper_20260622.md
```

Expected: all source study numbers remain present in the report.

- [ ] **Step 2: Check the diff**

Run:

```bash
git diff -- reports/latest/agent_adda_eod_signal_effectiveness_research_paper_20260622.md \
           reports/latest/agent_adda_eod_signal_effectiveness_research_paper_20260622.html
```

Expected: diff shows POV rewrite and regenerated HTML only. No code files are changed by this task.

- [ ] **Step 3: Report outcome**

Final response should state:

- Markdown path.
- HTML path.
- The POV now leads with "From Scanner To Decision Engine".
- Verification commands run and whether they passed.
