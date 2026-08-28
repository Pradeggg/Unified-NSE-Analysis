# Agent Adda — Agentic Loop Architecture

> **Status:** Verified against source code 2026-08-25. ~95% of structural claims confirmed.
> Unverified: learning-cycle end-to-end wiring, live PG memory (PG was down at verification time).

---

## Table of Contents

1. [The Core Mental Model](#1-the-core-mental-model)
2. [The Two-Loop Structure](#2-the-two-loop-structure)
3. [Knowledge Base — Three Search Layers](#3-knowledge-base--three-search-layers)
4. [KB Episodes and Session Logging](#4-kb-episodes-and-session-logging)
5. [Inner Loop — 9-Stage Pipeline](#5-inner-loop--9-stage-pipeline)
6. [UnifiedRouter — 8 Providers](#6-unifiedrouter--8-providers)
7. [RouteDecision Schema](#7-routedecision-schema)
8. [PostgreSQL Memory Schemas](#8-postgresql-memory-schemas)
9. [Skill Store Pipeline](#9-skill-store-pipeline)
10. [Learning Cycle — Interaction to Promotion](#10-learning-cycle--interaction-to-promotion)
11. [MCP Server — 10 Exposed Tools](#11-mcp-server--10-exposed-tools)
12. [Grounding Verification](#12-grounding-verification)

---

## 1. The Core Mental Model

Two agentic loops share one knowledge layer:

```
Claude Code (OUTER LOOP — coding assistant / orchestrator)
│
│   Task arrives → query KB first → get exact CLI + ordering rules
│   → execute or edit code → verify output → next task
│
│   Path A (MCP):   query_kb_tools(query)  via stdio MCP → nse_market
│   Path B (shell): python -m knowledge_base query "…"  → same BM25 index
│   Path A+:        get_stock_profile() / get_market_overview()  → PostgreSQL
│
└──────────────────────── KNOWLEDGE BASE (shared bridge) ──────────────────────
          BM25 Layer 1  ·  ChromaDB Layer 2  ·  Web Layer 3
          173 entries   ·  PDFs / Q&A pairs  ·  DuckDuckGo / WebSearch
──────────────────────────────────────────────────────────────────────────────
│
AgentAdda (INNER LOOP — nse_agent.py + terminal/agent.py)
│
│   REPL receives input → 9-stage pipeline → UnifiedRouter (8 providers)
│   → tool execution → PostgreSQL memory write → next turn
│
└── State persisted to PG: agent_memory.turn_events, agent_context.*
```

**Why two loops share the KB:**
- The outer loop (Claude Code / Codex) needs to know *what command to run* without reading source code. BM25 gives it the exact CLI, argument ordering, and critical ordering constraints (like `VCP-PICKS-ORDER`) in < 10 ms.
- The inner loop (AgentAdda REPL) uses the KB for skill retrieval — when a user asks something open-ended, `_stage_skill_store` retrieves the best matching skill card and executes its `tool_plan_template`.
- Both write to the same token-savings log (`data/knowledge_base/query_log.db`), making cross-loop analytics possible via the episodes subsystem.

---

## 2. The Two-Loop Structure

### Outer Loop — Claude Code / Codex

**Entry:** Task or question from developer
**Stateless:** No persistent memory between sessions (relies on KB + git)

**Step sequence:**
```
1. Receive task
2. query_kb_tools("relevant keywords")          ← always first
3. Interpret context_block (CLI + rules)
4. Execute CLI via shell tool, or edit source files
5. Verify output (run tests, check HTML, check DB)
6. Report outcome
```

**Connection points to inner loop:**

| Path | Mechanism | Use case |
|------|-----------|----------|
| `query_kb_tools(query)` | stdio MCP → `kb_tools_query.query_tools()` | Get CLI + ordering rules |
| `python -m knowledge_base query "…"` | Shell subprocess | Same BM25, no MCP needed |
| `get_stock_profile(symbol)` | MCP → PostgreSQL | Live stock data |
| `get_market_overview()` | MCP → PostgreSQL | Breadth, FII/DII, indices |
| `python scripts/generate_research_report.py SYMBOL` | Shell subprocess | Run inner-loop tool directly |

### Inner Loop — AgentAdda REPL

**Entry:** `python nse_agent.py` → prompt_toolkit interactive REPL
**Stateful:** Full PostgreSQL memory, 5-turn context window fed to router each turn

**Step sequence:**
```
1. User types input
2. /slash commands → dedicated handler (bypasses pipeline)
3. Natural language → Agent._query(user_input)
4. _build_pipeline_ctx() → constructs _PipelineCtx with ContextPack from PG
5. _query_single() runs 9-stage short-circuit pipeline
6. Winner stage executes tool_plan
7. Response synthesised and rendered via Rich Markdown
8. Turn written to agent_memory.turn_events (PG)
9. Context pack updated for next turn
```

---

## 3. Knowledge Base — Three Search Layers

### Layer 1 — BM25 Skills Index (always on, < 10 ms)

**File:** `knowledge_base/skills_registry.py`

Indexes 5 source types into a single ranked list:

| Source | Count | File |
|--------|-------|------|
| `reports/latest/launcher_data.json` | ~138 commands | Launcher catalogue |
| `skill_store/stored/*.yml` | 6 YAMLs | Production skill cards |
| `.claude/skills/*/SKILL.md` | 9 project skills | Claude Code skills |
| `knowledge_base/entries/workflows.yaml` | 16 workflows | Curated workflow entries |
| `mcp_server.py` tool docstrings | 9–10 MCP tools | MCP tool surface |

**Total at last index:** 173 entries

Each entry carries `source_file_tokens` — an estimate of how many tokens a caller would consume reading source files instead of the KB. The `token_tracker.py` logs actual savings per query to SQLite.

**Rebuild after adding skill cards:**
```bash
python -m knowledge_base index-skills
```

**Query formats:**
```bash
python -m knowledge_base query "daily pipeline" --format context       # markdown block
python -m knowledge_base query "stage 2 screener" --format json        # machine-readable
python -m knowledge_base query "chart RELIANCE" --format context-compact  # one-liner
```

### Layer 2 — ChromaDB Vector Store (hybrid mode, ~200 ms)

**File:** `knowledge_base/vector_store.py`

Two ChromaDB collections:
- `kb_chunks` — raw PDF text chunks
- `kb_qa` — LLM-generated Q&A pairs (preferred; higher precision)

Three embedding backends via `KB_EMBED_BACKEND` env var:

| Backend | Value | Notes |
|---------|-------|-------|
| OpenAI | `openai` (default) | `text-embedding-3-small`, 1536-dim |
| Ollama | `ollama` | `nomic-embed-text`; `ollama pull nomic-embed-text` |
| Sentence Transformers | `sentence-transformers` | `all-MiniLM-L6-v2`, 384-dim, local CPU |
| Auto | `auto` | Probes OpenAI → Ollama → ST in order |

Collections are namespaced by backend suffix (`_st`, `_ol`) to prevent dimension mixing on backend switch.

**Merge formula when hybrid=True:**
```
final_score = BM25_normalised × 0.6 + vector_score × 0.4
```

**Feed pipeline:**
```bash
python -m knowledge_base build          # fetch PDFs → chunk → QA → embed → upsert
python -m knowledge_base ingest <url>   # ad-hoc single PDF
```

Source registry: `data/financial_sources_registry.json` (SEBI, RBI, CRISIL, broker research).

### Layer 3 — Live Web Augmentation (real-time, ~1–3 s)

**File:** `knowledge_base/web_search.py`

- **DuckDuckGo HTML scraper** — activated with `--web` flag or `web=True` parameter
- **Claude WebSearch injection** — pre-fetched results passed as `web_results=[…]` to `query_tools()`, bypasses DuckDuckGo entirely

**Preferred pattern for company research:**
```python
# Step 1: Run WebSearch natively in Claude Code for 5 web dimensions
# Step 2: Inject into generate():
from scripts.generate_research_report import generate
generate("LTFOODS", injected_web={
    "analyst_view":  [{"title": "…", "url": "…", "snippet": "…"}],
    "order_book":    […],
    "credit_rating": […],
    "exports":       […],
    "latest_news":   […],
}, open_browser=True)
```

### Unified query gateway

**File:** `knowledge_base/kb_tools_query.py` — `query_tools()`

```python
result = query_tools(
    query="how to run daily pipeline",
    k=5,
    fmt="context",        # context | context-compact | json | text
    hybrid=False,         # True = add Layer 2
    web=False,            # True = add Layer 3
    web_results=None,     # inject pre-fetched WebSearch hits
    max_tokens=2000,
    caller="claude_code", # logged to query_log.db
    session_id="…",
)
# Returns: context_block, hits, token_savings, tokens_in, tokens_out,
#          latency_ms, search_method, log_id, web_hits
```

---

## 4. KB Episodes and Session Logging

Four kinds of session/episode tracking coexist:

### 4.1 Derived Episodes (passive analytics)

**File:** `knowledge_base/episodes.py`

Groups past KB `query_log` rows into session-like episodes by `(caller, session_id)` with configurable gap-splitting. No extra writes — pure analytics over the existing query log.

```bash
python -m knowledge_base episodes            # list recent episodes
python -m knowledge_base episodes --hours 168   # last 7 days
```

### 4.2 Real Episodes (instrumented execution)

**File:** `knowledge_base/episode_store.py`
**Storage:** `data/knowledge_base/episodes/events.jsonl` (append-only)

Instruments actual command executions when called explicitly (JSONL, safe-by-default):
```python
from knowledge_base.episode_store import EpisodeStore
store = EpisodeStore()
ep = store.start_episode(goal="validate midday report", caller="report_validation", tags=["report_validation","midday_market"])
store.log_step(ep, step="execute", tool_name="subprocess.run", tool_args={"cli": "python report_validation.py --checkpoint midday_market"})
store.log_validator(ep, name="report_validation:midday_market", ok=True, details={"high": 0})
store.log_artifact(ep, artifact_type="report_artifact", locator="reports/latest/midday_market.html")
store.end_episode(ep, status="SUCCESS", summary="checkpoint=midday_market findings=0 high=0")
```

Set `AGENT_ADDA_EPISODE_ID` env var to tag multiple executions into one episode.

```bash
python -m knowledge_base episodes-real
```

**Propagation:** `tools/command_center.py` exports `AGENT_ADDA_EPISODE_ID` into subprocesses so child scripts
can attach validator/artifact logs into the same episode.

### 4.3 Imported Episodes (cross-tool metadata)

**File:** `knowledge_base/episode_import.py`
**Storage:** `data/knowledge_base/imported_episodes_*.jsonl`

Reads metadata (no message text) from:
- `~/.claude/history.jsonl` — Claude Code session history
- Cursor's `conversation-search.db` SQLite — Cursor conversation metadata

```bash
python -m knowledge_base import-episodes
python -m knowledge_base episodes-imported
```

**Current data:** 11 Claude Code sessions + 29 Cursor sessions imported.

### 4.4 Turn Events (full REPL memory, PostgreSQL)

**File:** `terminal/conversation_memory.py`
**Schema:** `agent_memory.turn_events` (see §8)

Every AgentAdda REPL turn is written to PostgreSQL. The next turn's `build_context_pack(depth=5)` reads back the 5 most recent turns to construct the `ContextPack` that feeds the UnifiedRouter — this is what makes "what about the earlier stock?" context-awareness work.

---

## 5. Inner Loop — 9-Stage Pipeline

**File:** `terminal/agent.py` — `Agent._query_single()`

The pipeline is a short-circuit chain — each stage returns `dict | None`. First non-None result wins; remaining stages are skipped.

```python
# Actual call chain (lines 6830–6838):
return (
    self._stage_clarification_binding(ctx)
    or self._stage_compressed_context_synthesis(ctx)
    or self._stage_agentic_bound_action(ctx)
    or self._stage_unified_router(ctx)
    or self._stage_entity_topic(ctx, entity_assessment)
    or self._stage_situation_assessment(ctx)
    or self._stage_skill_store(ctx)
    or self._stage_semantic_intent(ctx)
    or self._stage_keyword_and_llm(ctx)
)
```

> **Note:** The docstring inside `_query_single` lists 7 stages — it is stale. The code has 9.

### Stage Details

| # | Stage | Type | Description |
|---|-------|------|-------------|
| 1 | `_stage_clarification_binding` | Context | Matches structured "yes/no/A/B" replies to pending clarification questions |
| 2 | `_stage_compressed_context_synthesis` | Context | Synthesises over compressed prior context when conversation exceeds depth threshold; prevents context drift in long sessions |
| 3 | `_stage_agentic_bound_action` | Context | Executes a previously confirmed tool plan. Single-letter/digit label "A" → runs `bound_action` JSONB from `agent_context.pending_options` at score 1.0 |
| 4 | `_stage_unified_router` | **Router** | Primary router. Runs all 8 DEFAULT_PROVIDERS, sorts by score DESC, projects winner, runs `enforce_validation()` (AA-UR-5). Returns typed `RouteDecision`. |
| 5 | `_stage_entity_topic` | Fallback | Legacy: `EntityTopicProvider` + `DirectIntentProvider` (not in DEFAULT_PROVIDERS). Deterministic entity + intent resolution. |
| 6 | `_stage_situation_assessment` | Context | Contextual follow-up + full entity orchestration. Binds to `active_workflow` if open. |
| 7 | `_stage_skill_store` | **Skill** | Retrieves skill candidates via BM25+vector (`retrieve_skill_candidates()`), selects best match, runs `execute_skill_plan()` against the skill's `tool_plan_template`. |
| 8 | `_stage_semantic_intent` | LLM | LLM intent classification (gpt-4o → Ollama Granite4 cascade). Fires only when keyword rules in stage 9 would miss. |
| 9 | `_stage_keyword_and_llm` | Fallback | Keyword dispatch for 20+ intents (`stock_brief`, `screener_inquiry`, `intraday_scan`, …). Falls through to full LLM response if no rule fires. Terminal fallback — always returns a non-None dict. |

### Context Pack

Before each `_query_single()` call, `_build_pipeline_ctx()` calls `conversation_memory.build_context_pack(depth=5)` which reads PostgreSQL and constructs:

```python
@dataclass
class ContextPack:
    recent_turns: tuple[RecentTurn, ...]       # last 5 turns
    active_symbols: frozenset[str]             # symbols in flight
    active_indices: frozenset[str]
    active_sectors: frozenset[str]
    active_reports: tuple[ActiveReport, ...]   # generated report paths on disk
    active_workflow: ActiveWorkflow | None     # open Sherlock workflow
    pending_options: tuple[PendingOption, ...] # NEXT OPTIONS awaiting reply
    source_trails: tuple[SourceTrail, ...]     # provenance ledger entries
    freshness: FreshnessInfo
```

---

## 6. UnifiedRouter — 8 Providers

**File:** `terminal/router/providers.py`
**Instantiated by:** `terminal/router/router.py` — `UnifiedRouter`

```python
DEFAULT_PROVIDERS: tuple[type, ...] = (
    PendingOptionProvider,
    CouncilCommandProvider,
    ContextualFollowupProvider,
    _CompoundStockProvider,
    ReportProvider,
    VisualScanProvider,
    TopMoversProvider,
    MarketSituationProvider,
)
```

### Provider Reference

| Provider | Score | Route Type | Trigger |
|----------|-------|------------|---------|
| `PendingOptionProvider` | 1.00 / 0.95 | `direct_tool_plan` | Single-letter/digit reply matching a live entry in `agent_context.pending_options` |
| `CouncilCommandProvider` | 0.99 | `direct_tool_plan` | Input starts with `/council` |
| `ContextualFollowupProvider` | 0.92 (workflow) / 0.90 | `contextual_answer` | Follow-up phrases ("based on the above"); binds to full active workflow if open |
| `_CompoundStockProvider` | 0.95 | `compound_plan` | ≥2 facets from {live_quote, F&O, intraday} in one prompt. Emits 5-tool dependency graph via `task_graph.add_blocks()`. |
| `ReportProvider` | 0.80 | `contextual_answer` | "the report", "open the report" — requires matching entry in `active_reports` |
| `VisualScanProvider` | 0.70 | `direct_tool_plan` | "chart", "candlestick", "visual scan" |
| `TopMoversProvider` | 0.85 | `direct_tool_plan` | "top gainers/losers/movers" → `get_top_gainers_losers` (intraday) or `get_eod_top_movers` |
| `MarketSituationProvider` | 0.65–0.88 | `direct_tool_plan` | Market/sector phrases, FII/DII, screener words. Quality-breakout detection scores 0.88. |

**Not in DEFAULT_PROVIDERS** (used directly by `_stage_entity_topic`):
- `EntityTopicProvider` — resolves company/index entity + intent type
- `DirectIntentProvider` — direct keyword → tool mapping

### Router execution logic (`router.py`):
```
1. Run all registered providers → list[RouteCandidate]
2. Sort by (score DESC, registration_index ASC)
3. Project winner via to_decision()
4. Build ContextBinding from pack + winner's tool_plan symbols
5. Run enforce_validation() (AA-UR-5):
   - Strip broken NEXT OPTIONS
   - Check: unknown tools, missing required args, empty symbol binding
   - Rewrite invalid direct/compound plans to blocked_ungrounded
6. Return RouteDecision
```

Provider exceptions are caught, logged as zero-score rejected candidates — never crash the router.

### Out-of-domain filter

`is_out_of_domain(text)` in `providers.py` — two-step:
1. Match OOD regex (weather, sports, food, medical)
2. Override if any financial term is also present
Returns a polite redirect or `None`.

---

## 7. RouteDecision Schema

**File:** `terminal/router/schema.py`

```python
@dataclass(frozen=True)
class RouteDecision:
    decision_id: str
    intent: str
    route_type: RouteType          # direct_tool_plan | contextual_answer |
                                   # clarification | compound_plan |
                                   # fallback_llm | blocked_ungrounded
    confidence: float
    user_is_asking: str            # plain-English paraphrase of intent
    context_binding: ContextBinding
    evidence_requirements: tuple[EvidenceRequirement, ...]
    tool_plan: tuple[ToolCallSpec, ...]
    next_options: tuple[NextOption, ...]   # NEXT OPTIONS rendered to user
    reasoning_summary: str
    validation: ValidationResult
```

**`ToolCallSpec`** — one tool call with optional dependency tracking:
```python
@dataclass(frozen=True)
class ToolCallSpec:
    tool: str
    args: dict[str, Any]
    task_id: str | None = None
    blocked_by: frozenset[str] = field(default_factory=frozenset)
```

**`NextOption`** — a menu item presented to the user:
```python
@dataclass(frozen=True)
class NextOption:
    label: str        # "A", "B", "1", "2"
    text: str         # human-readable option text
    bound_action: BoundAction   # serialised tool_plan stored to PG
```

**Dependency graph** (`terminal/router/task_graph.py`):
```python
add_blocks(specs, blocker_id, *blocked_ids)   # set blocked_by on specs
dependency_layers(specs)                       # topological sort → parallel layers
validate(specs)                                # DFS cycle detection
```

---

## 8. PostgreSQL Memory Schemas

PostgreSQL cluster: Unix socket `/tmp`, user `nse_admin`, database `nse_market`.

```bash
./postgres/start_pg.sh start    # required before any REPL session
./postgres/start_pg.sh status
```

### Schema `agent_memory` (`postgres/migrations/20260520_agent_memory.sql`)

**`agent_memory.turn_events`**

| Column | Type | Description |
|--------|------|-------------|
| `session_id` | text | REPL session identifier |
| `turn_index` | int | Sequential turn counter within session |
| `user_input` | text | Raw user message |
| `answer` | text | Agent response |
| `intent` | text | Resolved intent label |
| `mode` | text | `/live`, `/eod`, or `/auto` |
| `symbols` | text[] | Symbols referenced in this turn |
| `tool_names` | text[] | Tools executed |
| `tool_results` | jsonb | Full tool outputs |
| `turn_context` | jsonb | Snapshot of ContextPack at turn time |

**`agent_memory.session_snapshots`**

Rolling serialised `ConversationMemory` per session (latest state only; replaced on each turn).

### Schema `agent_context` (`postgres/migrations/20260525_agent_context.sql`)

**`agent_context.active_workflows`**

Sherlock-style multi-step investigation workflows. Each row:

| Column | Type | Description |
|--------|------|-------------|
| `workflow_id` | uuid | Primary key |
| `session_id` | text | Owning session |
| `status` | text | `open` / `closed` / `abandoned` |
| `steps` | jsonb[] | Array of `WorkflowStep` — each carries structured evidence (fact / value / symbol / source_label / freshness / tools), **never free prose** |

**`agent_context.active_reports`**

Generated report registry. Enables `"open the report"` routing through `ReportProvider`.

| Column | Description |
|--------|-------------|
| `session_id + path` | composite primary key |
| `type` | report type (fundamental, stage2, swing, …) |
| `symbol` | ticker |
| `generated_at` | timestamp |

**`agent_context.pending_options`**

NEXT OPTIONS waiting for label reply. Drives `PendingOptionProvider` at score 1.0.

| Column | Description |
|--------|-------------|
| `option_label` | "A", "B", "1", "2" |
| `text` | human-readable option description |
| `bound_action` | jsonb — serialised `ToolCallSpec[]` to execute on reply |
| `expires_at` | nullable — auto-expire stale options |

**`agent_context.source_trails`**

Append-only provenance ledger. Every data access writes `(source_label, freshness)`.

---

## 9. Skill Store Pipeline

**Directory:** `terminal/skills/`

### Retrieval

**`retriever.py`** — `retrieve_skill_candidates(query, top_n, repo, embedding_provider)`:

```
1. Vector path:  embed query → search_vector_candidates() in DB
2. Tag path:     list_runtime_eligible() → BM25 tag + input_pattern match
3. Merge:        combined_score = vector×0.7 + tag×0.3 + status_boost(0.05 if production)
4. Log retrieval event to skill_store.retrieval_log
```

### Execution

**`executor.py`** — `execute_skill_plan(execution_plan, …) → SkillExecutionResult`:

Step types:
- `tool_call` — calls a registered tool function
- `sql_template` — safe parameterised SQL via `sql_runner.py` / `sql_safety.py`
- `report_lookup` — resolves report path from `active_reports`

Validates evidence against `output_contract` after execution. Logs to `skill_store.execution_log`.

### Skill card locations

| Location | Count | Status |
|----------|-------|--------|
| `skill_store/stored/*.yml` | 6 | Production |
| `terminal/skills/seed_cards/*.yml` | 3 | Seed / bootstrapping |

**Production skills:**
- `company_story_v1.yml` — 15-dimension deep research + template fill
- `comprehensive_stock_research_v1.yml`
- `equity_chart_v1.yml`
- `intraday_fno_alert_scan_v1.yml`
- `publish_intelligence_report_v1.yml`
- `swing_playbook_report_v1.yml`

### Additional `terminal/skills/` modules

Beyond the core pipeline, the directory contains:

| File | Role |
|------|------|
| `commands.py` / `commands_store.py` | Skill command registry + store |
| `fundamental_driver.py` | Drives fundamental analysis skill execution |
| `release_gate.py` | Gates skill promotion to production status |
| `reviewer.py` | Reviews generated skill cards before promotion |
| `scenario_validation.py` | Validates skill scenarios before execution |
| `tool_surface.py` | Maps skills to available tool surface |
| `reranker.py` | Reranks retrieved skill candidates |
| `runtime_assessment.py` | Assesses if a skill can be executed given current evidence |

---

## 10. Learning Cycle — Interaction to Promotion

**Directory:** `terminal/learning/`

Closed feedback loop from REPL usage to new skill cards in the BM25 index:

```
Turn execution
    ↓
interaction_log.py → InteractionEvent (intent, route_type, tools, artifacts, errors)
    ↓
repository.py → LearningRepository (SQLite persistence)
    ↓
pattern_miner.py → frequent tool sequences + intent patterns
    ↓
workflow_chains.py → multi-step chain detection
    ↓
proposal_generator.py → draft skill YAML cards (LLM-assisted)
    ↓
proposal_validator.py → checks output contract, evidence requirements
    ↓
promotion.py / terminal/skills/promote.py → write to skill_store/stored/*.yml
    ↓
python -m knowledge_base index-skills → BM25 picks up new skill
    ↓ (loop)
future queries surface the new skill at stage 7 (_stage_skill_store)
```

Supporting modules:
- `audit.py` — audits skill usage and effectiveness
- `daily_summary.py` — daily roll-up of learning activity

### Synthetic Router Eval Loop

**Files:** `knowledge_base/synth_router.py` + `knowledge_base/evals/router_eval.py`

Generates evaluation data from real KB query patterns and measures BM25 recall:

```bash
# Generate synthetic training set
python -m knowledge_base synth-router --mode both --days 60 --max 300

# Evaluate BM25 top-K recall
python -m knowledge_base eval-router data/knowledge_base/router_synth_both_d60_n300_s42.jsonl
```

**Training row shape:**
```json
{
  "query": "search knowledge base",
  "expected_id": "workflow_kb_financial_docs",
  "expected_cli": "python -m knowledge_base query …",
  "expected_category": "workflow",
  "expected_tags": ["kb", "search", "bm25"],
  "label_source": "input_pattern",
  "candidates": […]
}
```

Two label sources:
- **Gold labels** — from curated `input_patterns` in `workflows.yaml`
- **Weak labels** — recent KB queries + BM25 top-1 hit

Hard negatives (BM25 near-misses) and parameterised variants (symbol/date substitution) added automatically.

**Current data:** 500 rows on disk (200 + 300 across two runs).

---

## 13. Agent Adda Intelligence Loop (outer execution runner)

**File:** `terminal/agent_adda_intelligence_loop.py`

This is a lightweight “agentic loop” entrypoint for operational work:
- pulls KB context (`knowledge_base query`)
- pulls similar real episodes (`episodes-real`)
- proposes the next command via BM25 router
- optionally executes it (behind `--execute`)
- logs all steps into a real episode (`EpisodeStore`)

CLI:
```bash
python -m terminal.agent_adda_intelligence_loop "validate midday market report"
python -m terminal.agent_adda_intelligence_loop "validate midday market report" --execute
```

Recall gaps identified by `router_eval.py` drive updates to `knowledge_base/entries/workflows.yaml`.

---

## 11. MCP Server — 10 Exposed Tools

**File:** `mcp_server.py` (stdio MCP protocol)

Registered in Claude Code `settings.json`:
```json
{
  "mcpServers": {
    "nse": {
      "command": "/path/to/.venv/bin/python",
      "args": ["/path/to/mcp_server.py"]
    }
  }
}
```

| Tool | Description |
|------|-------------|
| `query_kb_tools(query, top_k, fmt, web, hybrid, max_tokens)` | **Primary bridge.** Calls `kb_tools_query.query_tools()` with `caller="mcp"`. Returns context_block + token accounting. Always call this first. |
| `get_market_overview()` | Breadth, index closes, global indices, FII/DII from `breadth.market_daily`, `market.index_eod`, `signals.fii_dii_flows` |
| `get_stage2_picks(index, sector, min_rs, limit)` | Stocks in Weinstein Stage 2 from `scores.stage_snapshots` + `ref.index_compositions` |
| `get_stock_profile(symbol)` | Stage history (30d), fundamentals, quarterly results, latest EOD from `scores.*` + `market.equity_eod` |
| `get_swing_candidates(limit)` | High-turnover Stage 2 stocks: RSI 40–70, RS ≥ 55 |
| `get_sector_rotation()` | Stage distribution + avg RS per sector across NIFTY 500 |
| `get_strategy_lab(strategy_id)` | Backtest leaderboard + trade log from `portfolio/data/nse_pg_strategy_lab/` JSON |
| `get_fno_signals(symbol, limit)` | PCR, OI buildup, max pain from `derivatives.fno_signals` |
| `get_bulk_block_deals(symbol, limit)` | Institutional bulk/block deals from `signals.bulk_block_deals` |
| `get_corporate_events(symbol, days_ahead)` | Dividends, splits, AGMs from `signals.corporate_events` |

All tools connect to PostgreSQL via `psycopg2` using `AGENT_ADDA_PG_DSN` or `PG_DSN` env vars. PostgreSQL must be running (`./postgres/start_pg.sh start`) before the MCP server is useful.

---

## 12. Grounding Verification

Verified 2026-08-25 against actual source files.

### ✅ Confirmed accurate

| Claim | Evidence |
|-------|----------|
| 9 pipeline stages, exact order | `grep "def _stage_" terminal/agent.py` + lines 6830–6838 |
| DEFAULT_PROVIDERS has 8 providers | `sed -n '1129,1145p' terminal/router/providers.py` |
| All KB modules exist | `ls knowledge_base/*.py` — all 23 files present |
| `terminal/learning/` has all 10 files | `ls terminal/learning/*.py` confirmed |
| All 8 router files present | `ls terminal/router/*.py` confirmed |
| PostgreSQL migrations exist | `ls postgres/migrations/` — 9 migration files |
| Synth router data on disk | 500 rows across 2 JSONL files |
| `evals/router_eval.py` exists and is wired | `ls knowledge_base/evals/` confirmed |
| Episode data populated | `events.jsonl` = 7.2 KB; 40 imported sessions |
| KB query log active | 29 queries, 1 session in `query_log.db` |

### ⚠️ Slight inaccuracies corrected here

| Original claim | Correction |
|----------------|------------|
| `terminal/skills/` — ~15 files listed | Actual: 27 files; additional modules include `commands.py`, `fundamental_driver.py`, `release_gate.py`, `reviewer.py`, `scenario_validation.py`, `tool_surface.py`, `promote.py` |
| `CompoundStockProvider` | Actual name in DEFAULT_PROVIDERS is `_CompoundStockProvider` (private alias) |
| Docstring says 7 stages | Code executes 9; docstring is stale |
| `terminal/skills/seed_cards/` contents | 3 files: `market_3m_rotation_swing_v1.yml`, `portfolio_incremental_add_trim_v1.yml`, `vcp_breakouts_with_fundamentals_v1.yml` |

### 🔶 Unverified (PG down at check time)

- **`agent_memory.turn_events` live data** — migrations confirm schema; actual row count unknown
- **`agent_context.*` live data** — same
- **Learning cycle end-to-end** — all files exist; whether `interaction_log → pattern_miner → proposal_generator → promote` runs automatically (scheduled) or only on manual invocation is unconfirmed
- **`LearningRepository` SQLite path** — the class exists but no corresponding `.db` file was found; may write on first REPL run with PG up

---

*Agent Adda · Architecture reference · 2026-08-25 · Educational, not investment advice*
