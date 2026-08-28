# Agent Adda Skill Catalog

This is the single inventory for the Agent Adda skill surface in this repo.

It groups three different things that have been built:

- file-backed skills for Claude, Cursor, and Agents
- runtime skill definitions in `terminal/skills/registry.py`
- seed cards and generated skill-store corpora

## 1. File-Backed Skills

These are the concrete `SKILL.md` packages checked into the repo.

| Skill | Purpose | Locations |
|---|---|---|
| `fundamental-analyze` | Deep company research using filings, Screener, and market data | `.agents/skills/fundamental-analyze`, `.cursor/skills/fundamental-analyze`, `.claude/skills/fundamental-analyze` |
| `tradingview-chart` | TradingView-style charts plus Cursor Canvas charts | `.agents/skills/tradingview-chart`, `.cursor/skills/tradingview-chart`, `.claude/skills/tradingview-chart` |
| `agent-adda-publish-intelligence-report` | Validate, publish, verify, and notify recipients for Agent Adda Market Intelligence reports | `.agents/skills/agent-adda-publish-intelligence-report`, `.cursor/skills/agent-adda-publish-intelligence-report`, `.claude/skills/agent-adda-publish-intelligence-report`, `.github/instructions/agent-adda-publish-intelligence-report.instructions.md`, `~/.codex/skills/agent-adda-publish-intelligence-report` |
| `live-prices` | Live NSE price dashboard via yfinance | `.claude/skills/live-prices` |
| `daily-pipeline` | Full daily EOD refresh pipeline, report generation, and email dispatch | `.claude/skills/daily-pipeline` |
| `refresh-fund-dashboard` | Refresh the fund holdings dashboard with live prices and DB context | `.claude/skills/refresh-fund-dashboard` |

## 2. Runtime Skill Registry

These are the built-in deterministic skill definitions in `terminal/skills/registry.py`.

| Skill ID | Purpose |
|---|---|
| `market_readiness` | Check market state, freshness, and data readiness |
| `entity_resolution` | Resolve company, symbol, index, and sector names |
| `evidence_grounding` | Force source-backed answers or an explicit gap |
| `fundamental_driver_diagnosis` | Explain EPS, ROCE, margin, debt, or cash-flow changes |
| `financial_statement_analysis` | Analyze P&L, balance sheet, and cash flow across periods |
| `valuation_analysis` | Build valuation ranges and scenario-based fair values |
| `forensic_accounting` | Surface accounting and earnings-quality red flags |
| `capital_allocation` | Assess capex, buybacks, dividends, and acquisitions |
| `corporate_event_analysis` | Interpret results, mergers, pledges, orders, and events |
| `portfolio_risk_review` | Review holdings, concentration, trims, and exits |
| `swing_trade_playbook` | Rank swing candidates with entry, stop, and target plans |
| `report_qa` | Validate report freshness, links, and required sections |
| `systematic_debugging` | Diagnose broken commands, pipelines, and reports |
| `trading_discipline` | Enforce timeframe, risk, and invalidation rules |

## 3. Seed Cards

These are the approved seed strategy cards under `terminal/skills/seed_cards`.

| Card | Domain | Use Case |
|---|---|---|
| `portfolio_incremental_add_trim_v1` | portfolio_review | Incrementally add, trim, or hold existing positions |
| `vcp_breakouts_with_fundamentals_v1` | screening | Stage 2 VCP breakouts with fundamental quality filters |
| `market_3m_rotation_swing_v1` | market_analysis | Three-month rotation and swing-candidate analysis |
| `publish_intelligence_report_v1` | report_distribution | Publish validated HTML report artifacts to agentadda.in and prepare/send approved recipient notifications |

## 4. Skill-Store Corpus

The repository also contains the larger skill-store corpus used for retrieval, validation, and promotion.

- `skill_store/stored/`
- `skill_store/generated_*`
- `skill_store/generated_1000_gpt4o_reaudited/`
- `skill_store/generated_2000_gpt4o_schema_fixed_part*/`

Those folders contain many generated cards, including report QA, quarterly-results, market-rotation, portfolio, and company-research variants. They are not all runtime-eligible; use the skill-store operator guide before promoting anything.

## 5. Supporting Docs

- `docs/codex_skill_index.md`
- `docs/AGENT_ADDA_CAPABILITIES.md`
- `docs/agent_adda_skill_store.md`
- `docs/refactor/nse_agent_command_inventory.md`
- `docs/superpowers/specs/2026-06-06-agent-adda-skill-store-design.md`

## 6. Practical Reading Order

If you are trying to understand the reusable skill surface, read in this order:

1. This catalog
2. `docs/AGENT_ADDA_CAPABILITIES.md`
3. `terminal/skills/registry.py`
4. The relevant `SKILL.md` package
5. The relevant seed card or skill-store card
