# Agent Adda Strategy Council — A Point of View

## 1. The Big Idea

Every retail trader and most institutional analysts make the same trade-off
every day: **speed of conviction vs. depth of evidence**. You can either
decide fast on a thin chart pattern, or you can spend a week pulling EOD
data, parsing a filing, eyeballing breadth, reading three brokerage notes,
backtesting one idea — and by then the setup has changed.

Agent Adda's **Strategy Council** collapses that trade-off into a single
CLI command. It is not "one model giving an opinion." It is a
**deliberative simulation of an investment committee** — strategist,
critics, deterministic backtester, factor exposure model, and a
verifiable audit trail — running on your own data, in under a minute,
for any of 2,000+ NSE names.

The Council does not tell you to buy. It tells you: *here is the strategy
that survived three rounds of structured criticism on this specific
symbol, under this specific market regime, using this specific evidence —
and here is everything we could not find, so you know the shape of the
unknown.*

---

## 2. What Makes It Unique

Most "AI for stocks" products fall into one of three buckets:

| Category | What it does | What it misses |
|---|---|---|
| **Robo-advisors** | Allocate to ETFs by risk profile | Zero stock-specific reasoning |
| **AI chat over filings** | Summarise an annual report | No backtest, no regime fit, no critic |
| **Screener + signal apps** | Rank by static factors | One-shot opinions, no deliberation, no provenance |

Agent Adda's Council is structurally different on **five axes**:

1. **Adversarial by construction.** Strategist proposes; critics veto.
   Three iterations. The output is whatever survives — not whatever
   sounds best in one prompt.
2. **Deterministic backtest in the loop.** Every candidate is actually
   run on train + validation splits across multiple horizons in pure
   pandas. No LLM hallucination of returns — the numbers are
   reproducible.
3. **Full provenance.** Every report carries a `source_trail` block:
   which Postgres table, which filing PDF (page count, table count,
   period), which screener facts, which Nifty 50 series — line by line.
   If a fetcher fails, it says so. No silent gaps.
4. **Tool-calling LLM, not blob-stuffed prompts.** With
   `AGENT_ADDA_STRATEGY_COUNCIL_TOOL_CALLS=1`, the strategist *asks for*
   the snapshot / filing extract / sector breadth / index history on
   demand from a 9-tool router — same way a human analyst opens a new
   Bloomberg tab. Up to 6 tool turns per role per iteration.
5. **Honest about missing data.** Readiness score (0–100) and a
   `missing` list ship in every report. GESHIP went from "data leakage
   everywhere" to "100/ready" not by faking data — by wiring the right
   fetchers and naming the gaps when they remain (e.g., DMART: "filing
   absent, council ran on 90/ready, here is why").

This is **research infrastructure with epistemic humility**, not a
confidence engine.

---

## 3. Benefits — Concretely

**For an individual investor / power retail:**
- Run `/strategy-council RELIANCE --horizons 5,10,20` and get a 120-line
  markdown + HTML dashboard in ~60s.
- See *why* a candidate was rejected (critic concerns are quoted
  verbatim).
- Get a `WAIT` recommendation in a bear regime instead of being talked
  into trades — the system has structural reasons to abstain.
- Reuse the same evidence pack across `/analyze`, `/sector-rotation`,
  `/forensics` — no re-pulling.

**For a small fund / family office / RIA:**
- Run the council nightly across a 50-symbol watchlist; persist to
  Postgres (`--persist`).
- Diff today's recommendation vs. yesterday's per symbol — that is your
  alert feed.
- Reports are markdown — they paste into IC notes, compliance logs,
  client letters.
- Every claim is cited; every gap is named. Compliance can actually
  audit the reasoning chain.

**For the analyst:**
- Stops being a data janitor. Spends time on the 5% of cases where the
  council says `TRADE_RESEARCH` and the critics flagged something
  interesting — not on pulling balance sheets.

---

## 4. How It Changes the Way We Look at Stocks & Markets

Three shifts:

**Shift 1: From point-in-time opinions to deliberated stances.**
Old workflow: "What do you think of HDFCBANK?" → 30 minutes of
subjective chart-reading + recency bias → "I like it." New workflow:
60 seconds → "stage2 candidate, validation P&L -10.5%, critic veto on
regime mismatch, recommendation WAIT." The unit of analysis is no
longer the analyst's mood — it is the **deliberation transcript**.

**Shift 2: From hidden assumptions to explicit data readiness.**
Most research notes do not tell you *what was not looked at*. The
Council's `missing` list and `source_trail` make the un-known part of
the output. You stop overweighting confident-sounding notes that were
quietly working off two data points.

**Shift 3: From "model says buy" to "strategy survived three critics."**
The Council never asserts a thesis. It surfaces strategies that
backtested well *and* withstood adversarial review *and* are compatible
with the current regime. That is a categorically different epistemic
claim — and it generalises across market conditions (bull/bear/range)
because the regime detector and critics adapt.

---

## 5. The Manual Equivalent — What This Would Cost Without Agent Adda

Below is what a **single Council run for a single stock** decomposes
into if a human team had to do it cold (no cached infra), benchmarked
against industry analyst workflows.

| Council step | Manual equivalent | Skill required | Time (per stock) |
|---|---|---|---|
| EOD pull + 1239-bar prep | Download from NSE bhavcopies, clean, normalise corporate actions | Data engineer | 30–45 min |
| Snapshot (stage, RSI, RS, signals) | Run TA library, compute stage classification, RS vs index | Quant analyst | 20 min |
| Market breadth | Pull A/D, build stage distribution from full universe | Quant analyst | 30 min |
| News / catalysts | Search 4–5 sources, dedupe, rank | Research associate | 30 min |
| Latest results reconciliation | BSE filings + NSE announcements + screener.in, reconcile facts | Equity analyst | 60–90 min |
| Filing parse (revenue / EBITDA / PAT / net debt) | Download PDF, OCR tables, normalise periods | Equity analyst | 45–60 min |
| Regime detection + factor β | Compute bull/bear/range bias, 90-day β vs Nifty 50 | Quant | 30 min |
| Strategy generation (5+ candidates) | Read research, draft strategy rules, parameters | Senior strategist | 60 min |
| Backtest train + validation × N horizons | Build harness, run, validate no look-ahead | Quant developer | 2–4 hrs |
| Critic review (regime / leakage / drawdown / β / correlation) | Senior analyst challenge session | Senior analyst | 60 min |
| 3 iterations of refinement | Repeat strategist + critic loop | Strategist + analyst | 3 hrs |
| Final one-shot held-out test | Build, run, document | Quant | 45 min |
| Report write-up + dashboard | Prepare IC-grade note | Analyst + designer | 90 min |

**Per-stock total: ~14–18 hours of expert time, across 4 distinct
roles.**

### FTE math at portfolio scale

Assume a 50-symbol watchlist refreshed **weekly** (modest by buy-side
standards):

- 50 stocks × 16 hrs avg = **800 person-hours / week**
- At 40 productive hrs/week = **20 FTE-weeks of work**
- Compressed into 5 working days = **20 FTEs**

That team typically looks like:

- 1 Head of Research (strategy oversight)
- 4 Senior Equity Analysts (sector-aligned)
- 4 Junior Analysts (data pulls, model maintenance)
- 3 Quant Developers (backtest harness, factor models)
- 2 Data Engineers (ingestion, cleaning)
- 2 Quant Analysts (regime, microstructure)
- 1 Compliance / Documentation
- 3 Buffer (vacations, write-ups, IC prep)

**Loaded cost in India: ₹4–6 crore/year** (mid-tier salary mix, no
software).
**Loaded cost in NYC/London**: USD 4–6M/year.

And critically: **most of this work is never reproducible.** Analysts
rotate, spreadsheets break, conventions drift. The Council's evidence
pack is a versioned artifact — same inputs, same output, forever.

### With Agent Adda

- **People required:** 1 power user (analyst or PM) operating the CLI.
- **Time per stock:** ~60 seconds for the council run; ~5 min to read
  the report and decide.
- **Time for the 50-symbol watchlist:** ~1 hour of compute + ~4 hours
  of human review = **half a working day**.
- **Marginal cost per run:** local compute + (optionally) ~$0.05–0.20
  of OpenAI tokens if tool-calling is on.
- **Reproducibility:** every report is a markdown file; every input is
  in Postgres or `data/filings/`.

**Compression factor: ~20 FTEs → 1 analyst. ~800 hrs/week → 4 hrs/week.**
Two orders of magnitude.

---

## 6. What's *Not* Automated (Honest Caveats)

This is research infrastructure, not investment advice. The Council:

- Will not capture **qualitative judgement on management** (only what
  filings/news say literally).
- Cannot **read your fund mandate or risk limits** — those gates sit
  outside.
- Is only as good as **its data**: DMART today shows the seam — no
  parsed PDF, so the filing slot is honestly missing, and the LLM is
  told.
- Recommendations are tagged `TRADE_RESEARCH` / `WAIT` / `NO_TRADE` —
  these are research stances, not orders. Position sizing and execution
  remain human decisions.

The disclaimer is in every report for a reason.

---

## 7. The Agent Adda Thesis

Indian markets have 5,000+ listed names, fragmented data, weak research
coverage below the top 200, and an exploding retail base. The
bottleneck is **not data availability** — it is **the cost of
synthesising data into a defensible stance, at scale, with provenance.**

Agent Adda's Strategy Council is the first piece of infrastructure that
makes that synthesis **deterministic, auditable, deliberated, and
cheap.** The strategist proposes, the critics push back, the
backtester adjudicates, the evidence pack carries the receipts. What
used to require a 20-person research desk now runs on a laptop with a
terminal and a Postgres database.

That is not "AI replacing analysts." That is **analysts getting the
leverage of a 20-person desk** — and spending their time on the 10
decisions per week that actually need a human.

---

*Research-only. Not investment advice. Every Council report carries its
own disclaimer and full source trail.*
