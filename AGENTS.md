# Agent Adda — Codex Instructions

**Project:** Agent Adda NSE Analysis Platform (`Unified-NSE-Analysis/`)  
**Working directory for all commands:** `/Users/pradeepgorai/Documents/Projects/finance/Unified-NSE-Analysis`  
**Python:** `.venv/bin/python` (always use the venv)

---

## ⚡ Query the Knowledge Base FIRST

Before reading any source file or searching code, run a KB query to get the
exact command, ordering rules, and guidance in < 100 ms:

```bash
# BM25 search — 169 entries, zero LLM, zero network
python -m knowledge_base query "<your question here>" --format context

# Examples:
python -m knowledge_base query "how to run daily pipeline"
python -m knowledge_base query "chart RELIANCE"
python -m knowledge_base query "stage 2 screener"
python -m knowledge_base query "fundamental analysis HDFC"
python -m knowledge_base query "ollama local setup"
```

The output is a markdown context block with the exact CLI, trigger phrases,
ordering rules, and source file pointers. Use it to answer the user directly
without reading source code.

For JSON output (easier to parse):
```bash
python -m knowledge_base query "<question>" --format json --top 8
```

---

## Environment

```bash
source .venv/bin/activate
# Or prefix every python command with:
.venv/bin/python ...
```

Required env vars (in `/Users/pradeepgorai/Documents/Projects/finance/.env`):
- `OPENAI_API_KEY` — for LLM + TTS + embeddings
- `ANTHROPIC_API_KEY` — for sector rotation narrative

PostgreSQL must be running for most analysis commands:
```bash
./postgres/start_pg.sh start
./postgres/start_pg.sh status
```

---

## Key commands (quick reference — query KB for details)

```bash
# Interactive REPL
python nse_agent.py

# Daily pipeline (after NSE close ~16:00 IST)
python daily_refresh.py
python daily_refresh.py --dry-run      # preview only
python daily_refresh.py --live-only    # fast price update

# Chart
python -m terminal.chart_engine SYMBOL --months 6 --intra-days 5 --open

# Live prices
python tools/live_prices.py

# Fund dashboard
python tools/fund_refresh.py --no-open

# Sector rotation
python sector_rotation_report.py

# Company Story — 15-dimension deep research (business, financials, concall,
# analyst view, order book, credit rating, exports, technical, management)
python scripts/company_story.py SYMBOL --open      # all dims + auto-open
python scripts/company_story.py SYMBOL --no-web    # DB + Screener only, offline

# Token usage of KB queries
python -m knowledge_base tokens

# Layer 3 web search (DuckDuckGo fallback)
python -m knowledge_base query "RELIANCE results" --web
```

---

## Coding rules

- All writes are idempotent upserts on natural composite keys `(date, symbol[, …])`.
- Never bypass the `--fundamentals-only` step before `--snapshot` (PG-FUND-ORDER).
- VCP materialiser must run before `top_picks_report.py` (VCP-PICKS-ORDER).
- Treat all outputs as research — never investment advice.
- Tests: `pytest -m "not llm"` (offline-safe); LLM tests need `RESEARCH_COUNCIL_RUN_LLM_TESTS=1`.

---

## MCP tools available (via Cursor / Claude Code)

Call `query_kb_tools(query="...")` first on any Agent Adda task — it returns
the exact CLI and context before you search code.

Other tools: `find_agent_adda_skills`, `execute_agent_adda_skill`,
`render_fundamental_analysis_report`, `get_market_overview`,
`get_stage2_picks`, `get_stock_profile`, `get_sector_rotation`, etc.
