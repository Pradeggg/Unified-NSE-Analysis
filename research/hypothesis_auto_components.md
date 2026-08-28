# Hypothesis Memo: Auto Components (India)

**Date:** 2026-03-08  
**Status:** In progress

---

## 1. Research question (one sentence)

We are studying NSE-listed auto component suppliers (parts/systems to vehicle OEMs) to identify quality names with positive relative strength in a large, under-researched industry; success is a shortlist backed by a cited sector definition, validated market size, and an optional backtest.

---

## 2. Definition

- **Industry term:** “Auto Components” = parts and systems supplied to vehicle manufacturers (OEMs). Excludes OEMs (passenger vehicles, 2W, CVs). Aligned with ACMA (Automotive Component Manufacturers Association of India).
- **Universe rule:** NSE-listed; **exclude OEMs** (MARUTI, TATAMOTORS, M&M, BAJAJ-AUTO, HEROMOTOCO, EICHERMOT, ASHOKLEY, TVSMOTOR); **include ancillaries** (tyres, batteries, forgings, electrical, engine/transmission parts — e.g. BHARATFORG, MOTHERSON, BOSCHLTD, APOLLOTYRE, MRF, EXIDEIND, UNOMINDA, TIINDIA, SONACOMS, TMPV).
- **Source:** ACMA definition and industry reports (see literature_notes_auto_components.md).
- **Sub-segments:** Tyres (APOLLOTYRE, MRF), Batteries (EXIDEIND), Forgings (BHARATFORG), Electrical/Electronics (BOSCHLTD, UNOMINDA, MOTHERSON, TIINDIA, SONACOMS, TMPV), Other.

---

## 3. Hypotheses

### H1 (Sector)

- **H1:** The auto components segment (listed ancillaries, ex-OEM) has delivered comparable or better capital efficiency than the broad market, as evidenced by median ROCE and revenue growth vs Nifty 50 over the last 5 years.
- **How we test it:** Compare sector median ROCE and 3Y revenue growth (from our data) with Nifty 50; optionally cite ACMA growth figures (e.g. 14% CAGR).

### H2 (Stock selection)

- **H2:** Listed auto component suppliers with ROCE > 15% and relative strength vs Nifty 500 > 0 (over 6M) have outperformed Nifty 500 over rolling 3Y windows (before transaction costs).
- **How we test it:** Backtest: each month (or quarter), apply screen; compute forward 1Y/3Y return of equal-weight portfolio of passing stocks vs Nifty 500; report hit rate, average excess return, max drawdown.

---

## 4. Scope and limits

- **In scope:** NSE-listed auto component companies (ancillaries only), using NSE price data, Screener fundamentals, and Nifty Auto / Nifty 500 for relative strength.
- **Out of scope:** Unlisted companies; BSE-only names; global comparables; OEMs.
- **Known limits:** Listed only (survivorship bias); single fundamental source (Screener); point-in-time; backtest period limited by data availability.

---

## 5. Screen criteria (operational)

- **Quality:** ROCE > 15%; fundamental score (earnings + sales + financial + institutional) > 70.
- **Momentum / RS:** Relative strength vs Nifty 500 (or Nifty Auto) > 0 over 6M.
- **Composite (optional):** 0.4 × fundamental score + 0.4 × technical score + 0.2 × RS percentile rank (0–100).
- **Shortlist:** Top 15 by composite, subject to minimum liquidity (e.g. in NSE universe with sufficient history).

---

## 6. Revision log

| Date       | Change                                      |
|------------|---------------------------------------------|
| 2026-03-08 | Initial draft; definition aligned with ACMA |
