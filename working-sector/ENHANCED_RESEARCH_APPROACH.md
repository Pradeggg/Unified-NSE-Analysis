# Enhanced Research Approach: Sector Deep-Dive (Auto Components & Reusable Framework)

**Purpose:** A hypothesis-driven, definition-clear, literature-backed research workflow that produces defensible sector analysis and stock screens. Designed for Auto Components first; reusable for other “unsexy” or target sectors.

---

## 1. Research Workflow Overview

```
Phase 0: Scope & hypothesis
    ↓
Phase 1: Definition & literature (industry reports, validation)
    ↓
Phase 2: Universe & data (NSE, indices, fundamentals, technicals)
    ↓
Phase 3: Screens & composite score (aligned to hypothesis)
    ↓
Phase 4: Validation (backtest, robustness, regime check)
    ↓
Phase 5: Output (sector note, dashboard, cited sources)
```

**Rule:** Do not skip Phase 0 or Phase 1. Building screens before defining the hypothesis and validating the sector definition leads to uninterpretable or wrong conclusions.

---

## 2. Phase 0: Scope and Hypothesis

### 2.1 Clarify the research question

Answer in one sentence:

- **What** are we studying? (e.g. “Auto component suppliers listed on NSE.”)
- **Why** does it matter? (e.g. “Unsexy industry with large market size; want to find quality names.”)
- **What** would “success” look like? (e.g. “A shortlist of stocks that meet quality and momentum criteria, with sector context.”)

### 2.2 State testable hypotheses

Write 1–2 hypotheses in this form:

- **H1 (sector):**  
  *“[Sector/segment] in India has [characteristic], as evidenced by [observable metric] over [time horizon].”*  
  Example: “Auto components (suppliers, ex-OEM) as a segment has delivered higher median ROCE than Nifty 50 over the last 5 years.”

- **H2 (stock selection):**  
  *“Stocks in [universe] that satisfy [screen criteria] have [outcome] relative to [benchmark] over [time horizon].”*  
  Example: “Listed auto component suppliers with ROCE > 18% and relative strength vs Nifty 500 > 0 have outperformed Nifty 500 over rolling 3Y windows (after transaction costs).”

### 2.3 Document scope and limits

- **In scope:** e.g. NSE-listed auto component suppliers (or Nifty Auto if you choose the broader definition).
- **Out of scope:** e.g. unlisted companies, BSE-only names (until BSE data is added), global comparables.
- **Limits:** e.g. “Analysis is point-in-time; screens are not backtested until Phase 4.”

**Deliverable:** A short **hypothesis memo** (see `working-sector/hypothesis_template.md`) with research question, H1/H2, and scope. Update it when you change definition or scope.

---

## 3. Phase 1: Definition and Literature

### 3.1 Define the sector precisely

- **Industry term:** e.g. “Auto Components” (ACMA-style: parts/suppliers to OEMs) vs “Auto” (OEM + ancillaries, e.g. Nifty Auto).
- **Universe rule:**  
  - **Option A — Component-only:** Exclude OEMs (no Maruti, Tata Motors, M&M, Bajaj Auto, Hero, Eicher, Ashok Leyland, TVS Motor). Include ancillaries (tyres, batteries, forgings, electrical, etc.).  
  - **Option B — Nifty Auto:** Use index as-is (OEM + ancillaries). Then **rename** the study to “Auto (OEM + Ancillaries)” and do not claim “830+ component companies.”
- **Sub-segments (optional):** Tyres, Batteries, Forgings, Electrical/Electronics, Engine/Transmission, etc., for later breakdown.

**Deliverable:** A **definition paragraph** in the hypothesis memo and in the final report: “In this note, we define [sector] as [rule]. Our universe is [list/source]. This aligns with [cited source].”

### 3.2 Industry and sector report search

**Objectives:**

1. Validate market size and player count (e.g. ₹6.2L Cr, 830+).
2. Confirm OEM vs component split and key players.
3. Get narrative and drivers (EV, PLI, exports, input costs).
4. Obtain a **citable source** for the final report.

**Suggested sources:**

| Type | Examples |
|------|----------|
| Industry bodies | ACMA, SIAM |
| Rating / research | CRISIL, ICRA, CARE (sector reports) |
| Government / promo | Invest India, PLI scheme docs, DPIIT |
| Equity research | Broker reports: “India Auto Components”, “Auto Ancillaries” |

**Search checklist:**

- [ ] At least one report that defines “Auto Components” and gives market size (₹) and number of players.
- [ ] Note: report name, date, URL or file, and exact definition used.
- [ ] Extract: market size, growth rate, key segments, 3–5 key drivers, and whether OEMs are included or excluded.

**Deliverable:** A **literature note** (e.g. `working-sector/literature_notes_auto_components.md`) with: source, definition, numbers, drivers, and how our universe aligns or deviates.

### 3.3 Align universe with definition

- Build or update the universe list (e.g. `auto_components_universe.csv`) so that:
  - Every symbol fits the chosen definition (component-only or Nifty Auto).
  - Each row has: SYMBOL, NAME (if available), SOURCE (Nifty Auto / sector list / manual), SUBSECTOR (OEM / Tyre / Battery / Forgings / Electrical / Other).
- Resolve index mapping issues (e.g. “NIFTY AUTO” vs “Nifty Auto”) and dedupe.

**Deliverable:** `working-sector/auto_components_universe.csv` (or equivalent) and one sentence in the report: “Universe built from [sources]; definition aligned with [cited report].”

---

## 4. Phase 2: Universe and Data

### 4.1 Price and index data

- **Stocks:** NSE OHLCV for universe only; same date range as index.
- **Index:** Nifty Auto (and optionally Nifty 50, Nifty 500) for benchmark and relative strength.
- **Checks:** No NA in CLOSE for index on used dates; constituent list matches NSE if possible.

### 4.2 Fundamental data

- **Primary:** Screener (existing R pipeline) — P&L, balance sheet, cash flow, ratios, quarterly results, shareholding.
- **Cache:** Store by symbol and as-of date; document “fundamental data as of [date].”
- **Optional backup:** One other source (e.g. key ratios from annual report or another provider) for a subset, to spot-check.

### 4.3 Technical and relative strength

- **Technicals:** DMA, RSI, Bollinger, trend, signal (existing pipeline) on universe.
- **Relative strength:** Stock vs **Nifty Auto** (and vs Nifty 50 or Nifty 500 if needed for H2). Same formula as existing RS; ensure index and stock dates align.

### 4.4 Regime context

- **Simple regime check:** Nifty Auto (and Nifty 50) returns: 1M, 3M, 6M, 1Y. Note whether sector is in uptrend or correction.
- **Optional:** One sentence from latest industry report (e.g. “ACMA expects FY25 growth at X%”) and add to “Sector context” in the report.

**Deliverable:** Clean tables: stock-level prices, fundamentals, technicals, RS vs chosen benchmark(s). One small “regime” summary (index returns + optional narrative).

---

## 5. Phase 3: Screens and Composite Score

### 5.1 Design screens to match hypotheses

- **H1 (sector):** Use sector aggregates (median/mean ROCE, revenue growth, PE, etc.) and compare to Nifty 50 or report figures. No “screen” needed; just summary stats.
- **H2 (stock selection):** Define screens that operationalize “quality” and “momentum” in a testable way, e.g.:
  - **Quality:** ROCE > 15%, or composite fundamental score > 70.
  - **Momentum / RS:** RS vs Nifty Auto (or Nifty 500) > 0 over 3M or 6M.
  - **Optional:** Technical score > 70, or trend = BULLISH.

### 5.2 Composite score (optional)

- **TechnoFunda or custom:** Combine fundamental score + technical score + RS (e.g. equal weight or 40% funda, 40% technical, 20% RS). Document formula.
- **Ranking:** Sort universe by composite (or by individual screens); produce a shortlist (e.g. top 10–15).

### 5.3 Document screen logic

- **Deliverable:** A short **screen specification** (in code comments or `working-sector/screen_spec_auto_components.md`):  
  “We define ‘quality’ as …; ‘momentum’ as …; composite = …; shortlist = top N by composite subject to ….”

---

## 6. Phase 4: Validation

### 6.1 Backtest (recommended for H2)

- **Question:** Would the screen (or composite) have added value historically?
- **Method:** For each historical date (e.g. monthly), apply the screen; compute forward return (e.g. 1Y) for passing stocks vs benchmark (e.g. Nifty 500 or Nifty Auto). Report hit rate, average excess return, max drawdown.
- **Caveat:** Survivorship bias if only current constituents are used; document the assumption.

**Deliverable:** Backtest results (table or one-page summary); one sentence in report: “Historical backtest over [period] shows [summary].”

### 6.2 Robustness

- **Sensitivity:** Vary thresholds (e.g. ROCE 12% vs 18%); check if shortlist and conclusions are stable.
- **Sub-periods:** If data allows, run backtest over two sub-periods (e.g. pre-/post-COVID) to check regime dependence.

### 6.3 Limits and caveats

- **Document:** Survivorship bias, single fundamental source (Screener), point-in-time nature, and that past backtest does not guarantee future results.

**Deliverable:** “Validation” subsection in the final report (backtest summary, robustness note, caveats).

---

## 7. Phase 5: Output and Citation

### 7.1 Sector note (narrative)

- **Definition:** One paragraph (from Phase 1); cite industry report.
- **Market size:** Number and source (e.g. “ACMA estimates FY24 at ₹X Lakh Cr”).
- **Regime:** Index returns + optional one-line narrative from report.
- **Universe:** How built; count of names; OEM vs component if relevant.
- **Sector stats:** Median/mean PE, ROE, ROCE, revenue growth (from our data).
- **Screens and shortlist:** How we selected names; table of shortlist with key metrics.
- **Validation:** Backtest summary and caveats.
- **Sources:** “Industry data from [Report, Year, URL/file]. Price and fundamental data from NSE and Screener as of [date].”

### 7.2 Dashboard and exports

- **Dashboard:** Table of universe (or shortlist) with fundamentals, technicals, RS vs Nifty Auto; charts (index vs Nifty 50, RS distribution, optional score distribution).
- **Export:** CSV of full universe with all metrics; CSV of shortlist; optional Excel.

### 7.3 Versioning and reproducibility

- **As-of dates:** Price data as of [date]; fundamental data as of [date]; report as of [date].
- **Code:** Scripts that run Phase 2–5 from universe + config; document in README or in `working-sector/README.md`.

**Deliverable:** Final sector note (Markdown or PDF), dashboard (HTML), CSVs, and a “Sources and data” section that cites industry report(s) and data sources.

---

## 8. Auto Components: Concrete Checklist

Use this as the runbook for the current project.

### Phase 0
- [ ] Write hypothesis memo: research question, H1 (sector), H2 (stock selection), scope.
- [ ] Decide definition: **component-only** (exclude OEMs) vs **Nifty Auto** (OEM + ancillaries); document.

### Phase 1
- [ ] Search for ≥1 industry report (ACMA / CRISIL / ICRA / broker); fill literature note.
- [ ] Validate/correct ₹6.2L Cr and 830+; cite source.
- [ ] Build `auto_components_universe.csv` with SOURCE and SUBSECTOR; fix index mapping.

### Phase 2
- [ ] Load NSE + Nifty Auto; filter to universe; add RS vs Nifty Auto (and Nifty 50/500 if needed).
- [ ] Run Screener batch; cache; build fundamental summary table.
- [ ] Run technical pipeline on universe; attach RS.
- [ ] Write regime summary (index returns + optional narrative).

### Phase 3
- [ ] Define screens (quality, momentum/RS) and composite; document in screen spec.
- [ ] Produce ranked shortlist.

### Phase 4
- [ ] Backtest screen or composite; document results and caveats.
- [ ] Optional: sensitivity and sub-period checks.

### Phase 5
- [ ] Write sector note with definition, size, regime, universe, stats, shortlist, validation, sources.
- [ ] Generate dashboard and CSVs; document as-of dates.

---

## 9. Reuse for Other Sectors

For another sector (e.g. Textiles, Chemicals, Packaging):

1. **Phase 0:** New hypothesis memo (research question, H1, H2, scope).
2. **Phase 1:** New definition; search sector-specific reports (e.g. TEXPROCIL, chemical industry body); new literature note; new universe CSV.
3. **Phase 2–5:** Same workflow; swap universe and benchmark index (e.g. Nifty Pharma, custom list, or Nifty 500).

Keep the same file structure: `working-sector/<sector>/` or `working-sector/<sector>_universe.csv`, `literature_notes_<sector>.md`, `screen_spec_<sector>.md`.

---

## 10. Summary

| Phase | Goal | Key deliverable |
|-------|------|------------------|
| 0 | Scope and hypothesis | Hypothesis memo (question, H1, H2, scope) |
| 1 | Definition and validation | Definition + literature note + cited market size + universe CSV |
| 2 | Data | Clean price, fundamental, technical, RS; regime summary |
| 3 | Screens | Screen spec; composite score; shortlist |
| 4 | Validation | Backtest + robustness + caveats |
| 5 | Output | Sector note (with sources), dashboard, CSVs |

**Enhancement over the original plan:** Explicit hypotheses, definition vs Nifty Auto, mandatory literature phase with citation, backtest and robustness, and a clear, auditable trail from “unsexy industry” claim to numbers and sources.
