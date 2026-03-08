# Working Sector: Research and Analysis

This folder holds the **enhanced research approach**, sector-specific plans, and reusable templates for hypothesis-driven sector deep-dives (starting with Auto Components).

---

## Contents

| File | Purpose |
|------|--------|
| **ENHANCED_RESEARCH_APPROACH.md** | Master workflow: Phase 0 (hypothesis) → Phase 1 (definition + literature) → Phase 2 (data) → Phase 3 (screens) → Phase 4 (validation) → Phase 5 (output). Use this for every sector. |
| **CRITICAL_REVIEW_AND_VALIDATION.md** | Critical review of the original Auto Components plan: hypothesis gap, “Auto Components” vs “Nifty Auto,” need for industry reports and backtest. |
| **auto_components_deep_analysis_plan.md** | Implementation plan (data, technicals, fundamentals, merge, dashboard). **Run only after Phase 0 and Phase 1 of the enhanced approach.** |
| **hypothesis_template.md** | Template for research question, definition, H1/H2, scope, and screen criteria. Copy and fill per sector. |
| **literature_notes_template.md** | Template for industry/sector report notes: source, definition, market size, drivers, alignment with our universe. |
| **screen_spec_template.md** | Template for screen logic: quality, momentum/RS, composite, exclusions, output. |
| **unsexy_industries_india.csv** | Extracted table: Auto Components and other “unsexy” industries (market size, no. of enterprises). |
| **unsexy_industries_india.md** | Same table in Markdown with short summary. |
| **sector_view_auto_components.md** | Combined sector view: [Sharescart](https://www.sharescart.com/industry/auto-ancillary/) listed universe (113 companies, ₹7.53 L Cr mcap) + strategic outlook from **auto-components.md**. |
| **auto-components.md** | Strategic outlook 2025–2026: FY25/26 numbers, Budget 2026, PLI, EV, ADAS, clusters, challenges (with source links). |
| **PIPELINE_README.md** | How to run the Python pipeline (Phases 2–5) step-by-step. |
| **AGENT_README.md** | AI agent (Ollama Granite4 + tool calling): run phases via natural language. |
| **config.py**, **phase2_data.py** … **phase5_report.py**, **run_pipeline.py** | Python pipeline; outputs in **output/** (CSVs, sector note, dashboard HTML). |
| **web_search.py**, **WEB_SEARCH_README.md** | Web search: multiple engines (DuckDuckGo, Google, Bing) and iterative search for sector research. |
| **agent.py**, **pipeline_tools.py** | Agent loop and pipeline tools for Ollama (phases, narratives, web search). |

---

## Recommended order (Auto Components)

1. Read **ENHANCED_RESEARCH_APPROACH.md** (full workflow).
2. Copy **hypothesis_template.md** → e.g. `hypothesis_auto_components.md`; fill Phase 0 (question, definition, H1, H2, scope).
3. Copy **literature_notes_template.md** → e.g. `literature_notes_auto_components.md`; search ACMA/CRISIL/ICRA (or similar); fill Phase 1 and validate market size.
4. Build universe: `auto_components_universe.csv` (aligned with definition); fix index mapping if needed.
5. **Run the Python pipeline (Phases 2–5):** `python3 run_pipeline.py` (see **PIPELINE_README.md**). Outputs go to `output/`.
6. Backtest and robustness (Phase 4) are included in the pipeline; sector note and dashboard (Phase 5) are generated automatically.
7. Use **screen_spec_template.md** (or copy to `screen_spec_auto_components.md`) to document final screen logic.

---

## Reuse for other sectors

For Textiles, Chemicals, Packaging, etc.:

- New hypothesis memo + literature notes + universe CSV.
- Same workflow (ENHANCED_RESEARCH_APPROACH Phase 0–5).
- Sector-specific plan and screen spec derived from the templates.

---

## Multi-step agentic workflow (run_research_workflow.sh)

The script **run_research_workflow.sh** runs the local steps in order:

1. **Phase 0–1 (pre-done):** Hypothesis memo and literature notes (filled manually / from web search).
2. **Ollama narrative:** Calls Ollama (default `granite4:latest`) with `prompt_for_narrative.txt` and overwrites `sector_narrative_auto_components.md`.
3. **Universe check:** Confirms `auto_components_universe.csv` exists.
4. **Next steps:** Prints reminder to run R pipeline (data, RS, technicals, fundamentals, merge, backtest, report).

**Run:** From repo root or `working-sector`: `./working-sector/run_research_workflow.sh`. Requires `ollama` running and `python3`. Set `OLLAMA_MODEL` to use another model (e.g. `granite3.2:latest`).

## Python pipeline (Phases 2–5)

- **Run:** `python3 run_pipeline.py` (from project root or `working-sector`). See **PIPELINE_README.md** for step-by-step description.
- **Outputs:** `output/phase2_universe_metrics.csv`, `phase3_shortlist.csv`, `phase4_backtest_results.csv`, `auto_components_sector_note.md`, `auto_components_dashboard.html`.

## AI agent and CLI (Ollama Granite4 + tool calling)

An agent that takes user input and runs pipeline phases via **tool calling** (e.g. “Run the full pipeline”, “Run Phase 2 and 3”, “What outputs do I have?”). Requires Ollama running and `ollama pull granite4`. See **AGENT_README.md** for setup and usage. Use CLI: `python working-sector/agent_cli.py --sector "Auto Components" --run-all` or `--interactive`. See AGENT_README.md.

## Comprehensive sector report (.md, .html, .xlsx)

**build_comprehensive_report.py** combines all pipeline outputs (sector narrative, hypothesis, literature, universe metrics, shortlist, backtest, stock narratives) into one report in three formats:

- **Markdown:** `output/auto_components_comprehensive_report.md` — full narrative, tables, and per-stock narratives with fundamental details.
- **Interactive HTML:** `output/auto_components_comprehensive_report.html` — tabbed view (Overview, Universe, Shortlist, Backtest, Stock narratives) with sortable tables.
- **Excel:** `output/auto_components_comprehensive_report.xlsx` — multi-sheet workbook (Summary, Sector_narrative, Hypothesis, Literature, Universe_metrics, Shortlist, Backtest, Stock_narratives). Requires `openpyxl` (e.g. `pip install openpyxl` or use project `.venv`).

**Run:** From project root: `python3 working-sector/build_comprehensive_report.py`. For .xlsx, use a environment where openpyxl is installed (e.g. `.venv/bin/python working-sector/build_comprehensive_report.py`).

## Data and report outputs

- **Universe:** `auto_components_universe.csv` (or `<sector>_universe.csv`).
- **Reports:** Sector note (Markdown), dashboard (HTML), comprehensive report (MD + HTML + XLSX), CSVs in `working-sector/output/`.
- **Cache:** Optional `screener_cache/` or similar for fundamental data.
