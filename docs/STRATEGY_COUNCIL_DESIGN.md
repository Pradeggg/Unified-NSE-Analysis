# Strategy Council — Design Document

> Location: `backtesting/strategy_council/`
> Status: implemented (deterministic + optional LLM agents)
> Scope: end-of-day (EOD) strategy research for NSE symbols
> Stance: **research-only output. Not investment advice.**
> Related: [`STRATEGY_COUNCIL_ENHANCEMENTS.md`](./STRATEGY_COUNCIL_ENHANCEMENTS.md) — proposed enrichment, advanced critics, rule composition, dashboards (design-only).

---

## 1. Purpose

The Strategy Council simulates a small panel of specialised "agents" (a Strategist and one or more Critics) that iteratively propose, backtest, and critique candidate EOD trading strategies for a single NSE symbol. After a fixed number of refinement rounds it locks one candidate, runs a single out-of-sample test, and emits a recommendation (`TRADE_RESEARCH`, `WAIT`, or `NO_TRADE`) together with a full audit trail.

Goals:

1. Produce **reproducible, auditable** strategy research artifacts for any NSE symbol.
2. Prevent **data leakage** by construction — the test split is hidden until the final lock.
3. Keep the LLM in a **bounded role** — it can only return JSON that compiles into a constrained `StrategySpec`; it cannot execute code or pick the strategy whitelist.
4. Provide a **deterministic fallback** so the council remains fully testable in CI without any API key.
5. Persist every run to PostgreSQL for later review and comparison.

Non-goals:

- Live order execution.
- Intraday or tick-level strategies.
- Free-form code generation by the LLM.

---

## 2. High-level Architecture

```
                       ┌──────────────────────────────┐
                       │      run_strategy_council    │   (council.py)
                       └──────────────┬───────────────┘
                                      │
       ┌──────────────────────────────┼─────────────────────────────────┐
       ▼                              ▼                                 ▼
┌──────────────┐             ┌──────────────────┐               ┌───────────────┐
│ EvidencePack │             │ build_time_splits│               │   Agents      │
│ (evidence.py)│             │   (splits.py)    │               │   (llm.py)    │
└──────┬───────┘             └────────┬─────────┘               └──────┬────────┘
       │                              │                                │
       │                              ▼                                ▼
       │                ┌───────────────────────────┐    ┌────────────────────────┐
       │                │ train / validation / test │    │ Strategist proposes    │
       │                │     pandas DataFrames     │    │ StrategySpecs          │
       │                └────────────┬──────────────┘    │ Critics emit Critiques │
       │                             │                   └─────────────┬──────────┘
       │                             ▼                                 │
       │                ┌────────────────────────────┐                 │
       │                │ run_strategy_spec_on_split │ ◄───────────────┘
       │                │       (runner.py)          │
       │                └────────────┬───────────────┘
       │                             ▼
       │                ┌────────────────────────────┐
       └───────────────►│  CouncilIteration history  │
                        └────────────┬───────────────┘
                                     ▼
                        ┌────────────────────────────┐
                        │   Lock + one-shot test     │
                        │ → Recommendation + report  │
                        └────────────┬───────────────┘
                                     ▼
                        ┌────────────────────────────┐
                        │  Markdown report (report.py)│
                        │  Postgres persistence       │
                        │  (postgres_storage.py)      │
                        └────────────────────────────┘
```

---

## 3. Module Map

| File | Responsibility |
|---|---|
| `types.py` | Frozen dataclasses for config, evidence, specs, results, critiques, iterations, final result. |
| `evidence.py` | Loads point-in-time EOD history (Postgres-first, CSV fallback) into an `EvidencePack`. |
| `splits.py` | Builds time-ordered train/validation/test split DataFrames. |
| `dsl.py` | Compiles LLM JSON proposals into safe, whitelisted `StrategySpec` objects. |
| `llm.py` | `Strategist` / `Critic` protocols, rule-based fallbacks, JSON-LLM adapters, OpenAI wiring. |
| `runner.py` | Executes a `StrategySpec` on a split via `backtesting.engine.run_backtest`. |
| `council.py` | Orchestrates the iterative propose → backtest → critique loop, then locks and one-shot-tests. |
| `report.py` | Renders the Markdown report (`render_council_markdown`, `write_council_report`). |
| `postgres_storage.py` | Defines `strategy_council` schema and persists `CouncilResult` with full audit trail. |

---

## 4. Data Contracts

All contracts live in `types.py`. They are intentionally `@dataclass(frozen=True)` so iteration history is immutable.

### 4.1 `CouncilConfig`

Run-level inputs.

| Field | Type | Default | Notes |
|---|---|---|---|
| `symbol` | `str` | — | NSE symbol (uppercased). |
| `horizons` | `tuple[int, ...]` | `(5, 10, 20)` | Allowed holding horizons in trading days. |
| `iterations` | `int` | `3` | Number of refinement rounds. |
| `max_candidates` | `int` | `5` | Cap on proposals per iteration. |
| `initial_capital` | `float` | `100_000.0` | Forwarded to the backtester. |
| `from_date` / `validation_from` / `test_from` | `str \| None` | `None` | Optional explicit split cuts (ISO date). |
| `allowed_strategies` | `tuple[str, ...]` | `("stage2", "supertrend_continuation", "rsi_pullback_stage2", "52w_high", "vcp")` | Whitelist enforced both at proposal compile time and at runner time. |
| `recommendation_threshold` | `str` | `"validation_then_test"` | Reserved for future policies. |

### 4.2 `EvidencePack`

Point-in-time facts surfaced to the Strategist. Mutable on purpose (`@dataclass`) so the builder can incrementally fill it in.

Key fields: `symbol`, `as_of`, `technical`, `fundamental`, `market`, `news`, `freshness`, `missing`, `source_trail`.

`missing` always lists the slots the council could not populate so critics and reports can react explicitly.

### 4.3 `StrategySpec`

The only object that drives a backtest. Holds `strategy_id`, `horizon_days`, `entry_rules`, `exit_rules`, `risk_rules`, `thesis`, `params`, `status`, `origin`. Compiled by `dsl.compile_strategy_proposal` for LLM proposals; built directly by the deterministic strategist.

### 4.4 `BacktestSliceResult`

Per-split outcome of running a spec: `split` (`"train"|"validation"|"test"`), `strategy_id`, `horizon_days`, `metrics` dict, `trade_count`.

### 4.5 `Critique`

Critic verdict: `critic`, `verdict` (`"accept"|"revise"|"reject"`), `issues`, `required_changes`, `confidence_delta`.

### 4.6 `CouncilIteration` and `CouncilResult`

Iteration captures candidates, train/validation results, critiques, and the strategist's revision note. `CouncilResult` is the final immutable record: config, evidence, iterations, locked strategy, test results, recommendation, rationale, optional report path.

---

## 5. Evidence Pack Construction (`evidence.py`)

`build_evidence_pack(symbol)` is the entry point.

1. Project root resolution (defaults to `Path.cwd()`).
2. Load EOD history via `load_symbol_eod_history`:
   - **Primary**: PostgreSQL `market.equity_eod` using DSN `AGENT_ADDA_PG_DSN` (default: `dbname=nse_market user=nse_admin host=/tmp`).
   - **Fallback**: A list of CSV paths under `data/` (see `STOCK_HISTORY_FALLBACK_CSVS`).
   - In both paths, `_normalize_eod` lowercases columns, renames `timestamp→date` and `tottrdqty→volume`, coerces numeric types, and drops malformed rows.
3. Optional `from_date` filter.
4. Latest row populates `technical` (`open`, `high`, `low`, `close`, `volume`, `bars`); `freshness["eod"] = "available"`.
5. Slots known to be unavailable today (`fundamentals`, `market_breadth`, `news`, `sentiment`, `latest_results`) are appended to `missing` so critics and reports can flag them explicitly.
6. Every load attempt — success or failure — is appended to `source_trail`, giving a verifiable provenance chain.

---

## 6. Time-based Splits (`splits.py`)

`build_time_splits(df, validation_from=None, test_from=None)`:

1. Renames `timestamp→date` if needed, coerces to datetime, drops NaT rows, sorts ascending.
2. If `validation_from` / `test_from` are supplied, uses them as hard cuts.
3. Otherwise defaults to a 60% / 20% / 20% time-ordered split.
4. Returns `{"train": df, "validation": df, "test": df}` — purely time-ordered to avoid lookahead.

This is the only place where split logic lives; both runner calls and critics rely on these labels.

---

## 7. LLM Safety Compiler (`dsl.py`)

`compile_strategy_proposal(proposal, allowed_strategies, allowed_horizons)` is the choke point between LLM output and the rest of the system.

Validations:

- `strategy_id` (lowercased, `-` → `_`) must be in the whitelist.
- `horizon_days` must be in the allowed horizons.
- `thesis` must be a non-empty string.
- `entry_rules`, `exit_rules`, `risk_rules` must be non-empty lists of non-empty strings.
- Combined rule text must not contain any forbidden token from:
  `("eval", "exec", "__", "import", "open(", "subprocess", "os.", "sys.")`.

Any violation raises `ValueError`, which the LLM strategist treats as "drop this candidate". The compiler is the reason a misbehaving LLM cannot inject executable code, exfiltrate via `open(`, or escape the strategy whitelist.

---

## 8. Agents (`llm.py`)

### 8.1 Protocols

```python
class Strategist(Protocol):
    def propose(self, *, evidence, config, prior_feedback) -> tuple[StrategySpec, ...]: ...

class Critic(Protocol):
    def critique(self, *, candidates, train_results, validation_results) -> Critique: ...
```

Anything matching these protocols can be plugged into `run_strategy_council`.

### 8.2 Deterministic Strategist (`RuleBasedStrategist`)

Generates the Cartesian product of `allowed_strategies × horizons`, truncated to `max_candidates`. Appends prior critic issues to the thesis text so revisions are visible in reports even without an LLM.

### 8.3 Deterministic Critics

- **`RuleBasedDataLeakageCritic`** — flags missing candidates and any appearance of `split == "test"` in train/validation results. Required change: *"hide test metrics until final lock"*.
- **`RuleBasedRiskCritic`** — flags zero-trade fleets and uniformly negative validation returns. Required change: *"tighten filters or return NO_TRADE"*.

### 8.4 LLM Adapters

- **`JSONLLMStrategist(llm_call)`** — formats a structured JSON prompt (symbol, horizons, allowed strategies, evidence summary, prior feedback, response schema) with a strict system message: *"Return JSON only. Propose bounded EOD research strategies; do not write Python code."* Each returned strategy passes through `compile_strategy_proposal`; invalid items are silently skipped. If all proposals fail validation, falls back to the deterministic strategist.
- **`JSONLLMCritic(critic_name, llm_call)`** — same pattern; coerces returned `verdict` into `{accept, revise, reject}` and `confidence_delta` into a float.

### 8.5 Factory

`build_default_agents(use_llm=True)`:

- If `OPENAI_API_KEY` is set and `use_llm` is True, builds `_openai_json_call(model)` using `AGENT_ADDA_STRATEGY_COUNCIL_MODEL` (default `gpt-4o`) and returns `(JSONLLMStrategist, (JSONLLMCritic("data_leakage"), JSONLLMCritic("market_risk")))`.
- Otherwise returns the rule-based trio.

OpenAI calls are configured with `response_format={"type": "json_object"}` and `temperature=0.2` for stability.

---

## 9. Candidate Execution (`runner.py`)

`run_strategy_spec_on_split(df, spec, split_name, initial_capital)`:

- If `spec.strategy_id != "stage2"`, returns a zero-trade `BacktestSliceResult` whose metrics include `"unsupported_strategy": <id>`. This is by design — the council may **propose** any whitelisted strategy, but only strategies actually wired into `backtesting.engine.run_backtest` execute. Unsupported proposals are visible in the report but never inflate metrics.
- Otherwise delegates to `run_backtest(df, BacktestConfig(strategy_id=spec.strategy_id, initial_capital=initial_capital))` and wraps the metrics into a `BacktestSliceResult`.

This separation lets the strategist freely explore the design space while keeping risk of half-implemented strategies generating false signals at zero.

---

## 10. Orchestration (`council.py::run_strategy_council`)

Signature:

```python
def run_strategy_council(
    eod_data: pd.DataFrame,
    *,
    evidence: EvidencePack,
    config: CouncilConfig,
    strategist=None,
    critics=None,
) -> CouncilResult
```

Steps:

1. **Feature enrichment.** `compute_stage2_features(eod_data)` is best-effort (wrapped in `try/except`); the council never fails because of feature computation.
2. **Splits.** `build_time_splits` produces train/validation/test.
3. **Iteration loop** for `idx in 1..config.iterations`:
   1. `strategist.propose(evidence, config, prior_feedback)` → up to `max_candidates` specs.
   2. For each candidate, run on **train** then **validation** (test is never touched here).
   3. Each critic produces a `Critique`. `required_changes` are concatenated into a `strategist_revision` string that feeds the next iteration's prompt.
   4. A `CouncilIteration` snapshot is appended to history.
4. **Selection.** `_select_best(last_candidates, last_validation_results)`:
   - Scores each result by `total_return_pct − 10·(trade_count == 0)` (no-trade penalty).
   - Picks the candidate whose `(strategy_id, horizon_days)` matches the best validation score.
5. **One-shot test.** The locked spec runs exactly once on the test split.
6. **Recommendation.** `_recommend(test_results)`:
   - No results / non-numeric return / zero trades → `NO_TRADE`.
   - `total_return_pct > 2` → `TRADE_RESEARCH`.
   - Otherwise → `WAIT`.
7. Returns a `CouncilResult` with full history, locked spec, test results, recommendation, and rationale text emphasising research-only intent.

**Leakage guarantee.** The test split is referenced exactly once, after the loop, and only on the single locked spec. The `RuleBasedDataLeakageCritic` additionally flags any accidental leakage of `split == "test"` into iteration results.

---

## 11. Reporting (`report.py`)

`render_council_markdown(result)` produces a single self-contained Markdown report covering:

- Header with symbol, generation time, evidence `as_of`, recommendation (bolded).
- Evidence Pack snapshot (`technical`, `freshness`).
- Missing data list.
- Source trail (every load attempt).
- Optional Intraday Evidence section (live snapshot, intraday setup, fallback analysis) when those keys are present in evidence.
- Iterations: per-iteration candidate count, strategist revision, metrics table over train + validation, and one line per critique with verdict and issues.
- Locked Strategy: id, origin, horizon, thesis.
- Final One-Shot Test metrics table.
- Rationale paragraph.
- Disclaimer footer.

`write_council_report(result, output_dir=None)` writes the file to `reports/strategy_council/strategy_council_<SYMBOL>_<YYYYMMDD_HHMMSS>.md` by default and returns the `Path`.

---

## 12. Persistence (`postgres_storage.py`)

`persist_council_result(result, conn=None, dsn=None)` writes a full audit trail. DSN resolution order: explicit `dsn` argument → `AGENT_ADDA_PG_DSN` → `PG_DSN` → default local socket DSN.

### 12.1 Schema (auto-created via `ensure_strategy_council_schema`)

- **`strategy_council.runs`** — one row per `CouncilResult`. Holds `run_id` (UUID), symbol, evidence as-of, recommendation, rationale, report path, locked strategy id/horizon, plus full `config`, `evidence`, and `locked_strategy` as JSONB.
- **`strategy_council.iterations`** — one row per iteration; stores counts and the full iteration as JSONB for replay.
- **`strategy_council.candidates`** — one row per proposed `StrategySpec` per iteration; full spec as JSONB plus normalised columns for fast filtering.
- **`strategy_council.critiques`** — one row per `Critique` per iteration, with issues/required_changes as text arrays.
- **`strategy_council.split_results`** — one row per `BacktestSliceResult`. `phase` is `"iteration"` (train/validation) or `"final_test"`, with `iteration_index` set for the former and `NULL` for the latter.

Helpful indexes: `(symbol, created_at DESC)` on runs; `(strategy_id, horizon_days)` on candidates; `(run_id, phase, split)` on split results.

### 12.2 Encoding

`_jsonable` recursively converts dataclasses → dicts, datetimes/dates → ISO strings, Decimals → floats, ensuring all JSONB columns are stable across runs.

### 12.3 Transaction model

The function opens its own connection if none is supplied, ensures the schema, inserts the run row, then `execute_values`-batches iterations, candidates, critiques, and split results. Caller-supplied connections are not committed automatically; owned connections commit and close at the end of the function.

---

## 13. Failure Modes and Defensive Behaviour

| Scenario | Behaviour |
|---|---|
| `compute_stage2_features` raises | Caught; raw EOD is used. The run continues. |
| Postgres unavailable for evidence load | CSV fallback paths are tried in order; failures recorded in `source_trail`. |
| LLM returns malformed JSON | Each proposal is wrapped in `try/except`; invalid items are dropped. If none survive, deterministic strategist takes over. |
| LLM verdict outside `{accept, revise, reject}` | Coerced to `"revise"`. |
| LLM tries to inject code (e.g. `import os`) | Rejected by `_FORBIDDEN_TOKENS` check in `dsl.py`. |
| Strategy not implemented in engine | Runner returns zero-trade slice with `"unsupported_strategy"` flag. |
| No trades anywhere | Risk critic flags it; selector applies `-10` no-trade penalty; recommender returns `NO_TRADE`. |
| Empty input frame | Splits return three empty DataFrames; iterations still execute but produce empty results; recommendation is `NO_TRADE`. |

---

## 14. Environment Variables

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | Enables LLM agents in `build_default_agents`. |
| `AGENT_ADDA_STRATEGY_COUNCIL_MODEL` | Overrides default `gpt-4o`. |
| `AGENT_ADDA_PG_DSN` | Postgres DSN for evidence loads and persistence. |
| `PG_DSN` | Fallback DSN for persistence. |

---

## 15. Testing Surface

Tests under `tests/`:

- `test_strategy_council_types.py` — dataclass contracts.
- `test_strategy_council_runner.py` — runner behaviour for supported vs. unsupported strategies.
- `test_strategy_council_loop.py` — iteration ordering, prior-feedback propagation, lock + one-shot test invariant.
- `test_strategy_council_evidence.py` — Postgres-first / CSV-fallback loader.
- `test_strategy_council_report.py` — Markdown structure and required sections.
- `test_strategy_council_postgres_storage.py` — schema creation and persistence round-trip.
- `test_nse_agent_strategy_council.py` — agent integration.

The deterministic agents make every test fully reproducible without network or API access.

---

## 16. Design Principles (Why It Looks This Way)

1. **Leakage-by-construction.** Test split is referenced exactly once, on the locked spec only, and a critic actively checks for accidental contamination.
2. **Bounded LLM surface.** The LLM only returns JSON; the JSON only compiles into a tightly constrained `StrategySpec`; forbidden tokens are rejected before execution.
3. **Deterministic baseline.** Every protocol has a rule-based implementation so the system runs end-to-end with no external dependencies. The LLM is an optional accelerator, not a load-bearing piece.
4. **Auditability over cleverness.** Every iteration, every critic verdict, every split result lands in Postgres and the Markdown report. Nothing important is summarised away.
5. **Failure-tolerant evidence.** Missing data is explicit (`missing`, `source_trail`, `freshness`) so downstream critics and readers can reason about it instead of assuming silence means "fine".
6. **Research-only stance.** The rationale text and report disclaimer make the non-investment-advice posture impossible to miss.

---

## 17. Extension Points

- **New strategies.** Add an id to `CouncilConfig.allowed_strategies` *and* wire it into `backtesting.engine.run_backtest`. Without the engine wiring, the runner will continue to return `unsupported_strategy` slices.
- **New critics.** Implement the `Critic` protocol and pass it in via the `critics` argument to `run_strategy_council`, or extend `build_default_agents`.
- **Alternative LLM backends.** Provide a `Callable[[str, str], dict[str, Any]]` to `JSONLLMStrategist` / `JSONLLMCritic` — no other code changes are required.
- **Custom split policies.** Pass `validation_from` and `test_from` on `CouncilConfig` to override the default 60/20/20 cuts.
- **Alternative storage.** `persist_council_result` accepts a `conn`, so the same `CouncilResult` can be persisted to any psycopg2-compatible connection (e.g. a per-test temporary database).

---

## 18. Glossary

- **EOD** — End of Day. Council operates on daily bars.
- **Split** — Time-ordered partition of EOD history into `train`, `validation`, `test`.
- **Spec** — A `StrategySpec`: the only thing the runner executes.
- **Iteration** — One propose → backtest → critique cycle.
- **Lock** — The act of selecting the best validation candidate before touching the test split.
- **One-shot test** — Single execution of the locked spec on the test split.
- **Recommendation** — `TRADE_RESEARCH`, `WAIT`, or `NO_TRADE`. Research output, never an order.
