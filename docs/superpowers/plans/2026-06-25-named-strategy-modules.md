# Named Strategy Modules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-class named Agent Adda strategy modules, backtest summaries, current candidate tables, and comprehensive Markdown/HTML reports on top of the existing EOD signal-effectiveness research pipeline.
**Architecture:** Keep strategy definitions in a testable registry module, reuse `scripts/research_signal_effectiveness.py` for data loading/event labelling/backtest metrics, and add module-level CSV plus report rendering outputs without changing the existing report contract.
**Tech Stack:** Python 3, pandas, pytest, existing PostgreSQL-backed Agent Adda EOD research pipeline, existing Markdown-to-HTML renderer.

---

## Context

The approved design is in `docs/superpowers/specs/2026-06-25-named-strategy-modules-design.md`.

Existing pipeline entry point:

- `scripts/research_signal_effectiveness.py`

Existing relevant tests:

- `tests/test_signal_effectiveness_regime.py`
- `tests/test_backtesting_strategy_registry.py`

New files to create:

- `terminal/strategy_modules.py`
- `tests/test_strategy_modules.py`
- `tests/test_named_strategy_modules_report.py`

Existing file to modify:

- `scripts/research_signal_effectiveness.py`

New generated output paths:

- `reports/strategy_modules/named_strategy_modules_<stamp>.md`
- `reports/strategy_modules/named_strategy_modules_<stamp>.html`
- `reports/strategy_modules/module_summary_<stamp>.csv`
- `reports/strategy_modules/module_candidates_<stamp>.csv`
- `reports/latest/named_strategy_modules.md`
- `reports/latest/named_strategy_modules.html`
- `reports/latest/named_strategy_module_summary.csv`
- `reports/latest/named_strategy_module_candidates.csv`

## Task 1: Add Registry Tests First

- [ ] Create `tests/test_strategy_modules.py`.
- [ ] Add `test_strategy_module_registry_has_unique_complete_modules`.
  - Import `STRATEGY_MODULES` and `validate_strategy_modules` from `terminal.strategy_modules`.
  - Assert module IDs are unique.
  - Assert every module has `module_id`, `name`, `inspiration`, `purpose`, `mapped_setups`, `entry_rules`, `no_trade_rules`, and `failure_modes`.
  - Assert the registry includes these IDs:
    - `oneil_canslim_growth_breakout`
    - `weinstein_stage2_leader`
    - `minervini_sepa_vcp`
    - `darvas_box_breakout`
    - `graham_quality_value_confirmation`
    - `fisher_quality_growth`
    - `wyckoff_accumulation_breakout_proxy`
    - `agent_adda_composite_edge`
- [ ] Add `test_setup_family_maps_to_expected_named_modules`.
  - Assert `darvas_box_breakout` maps to `darvas_box_breakout`.
  - Assert `vcp_breakout_proxy` maps to `minervini_sepa_vcp` and `wyckoff_accumulation_breakout_proxy`.
  - Assert `combo_rs_volume_sector` maps to `oneil_canslim_growth_breakout`, `weinstein_stage2_leader`, `fisher_quality_growth`, and `agent_adda_composite_edge`.
  - Assert `combo_momentum_quality` maps to `oneil_canslim_growth_breakout`, `minervini_sepa_vcp`, `graham_quality_value_confirmation`, `fisher_quality_growth`, and `agent_adda_composite_edge`.
  - Assert `unknown_setup` returns an empty list.
- [ ] Add `test_module_summary_aggregates_setup_metrics`.
  - Build a synthetic `setup_summary` DataFrame with `setup`, `trades`, `win_rate_pct`, `expectancy_r`, `net_expectancy_r`, `net_profit_factor`, `avg_cost_r`, and `sample_quality`.
  - Call `aggregate_module_summary`.
  - Assert every mapped module gets a row.
  - Assert weighted metrics use `trades` as weight.
  - Assert `source_setups` records contributing setup names.
- [ ] Add `test_module_gate_classification_is_deterministic`.
  - Use synthetic rows and assert:
    - `net_expectancy_r > 0`, `net_profit_factor > 1`, and `sample_quality` in `{"higher", "medium"}` returns `TRADE_CANDIDATE`.
    - `-0.05 <= net_expectancy_r <= 0` with enough sample quality returns `HALF_SIZE_CANDIDATE`.
    - Breakout-sensitive setup with better retest evidence returns `WAIT_RETEST`.
    - `net_expectancy_r < -0.05` returns `BLOCK`.
    - Low trade count or low sample quality returns `WATCH`.
- [ ] Run the expected failing tests:
  - Command: `.venv/bin/python -m pytest tests/test_strategy_modules.py -q`
  - Expected result before implementation: import failure for `terminal.strategy_modules`.

## Task 2: Implement `terminal/strategy_modules.py`

- [ ] Create `terminal/strategy_modules.py`.
- [ ] Add frozen dataclass `StrategyModule` with fields:
  - `module_id: str`
  - `name: str`
  - `inspiration: str`
  - `purpose: str`
  - `mapped_setups: tuple[str, ...]`
  - `entry_rules: tuple[str, ...]`
  - `no_trade_rules: tuple[str, ...]`
  - `failure_modes: tuple[str, ...]`
  - `gate_notes: tuple[str, ...]`
- [ ] Define `STRATEGY_MODULES` using the eight approved module IDs and setup mappings from the design spec.
- [ ] Implement `validate_strategy_modules() -> None`.
  - Raise `ValueError` for duplicate IDs.
  - Raise `ValueError` for empty required fields.
  - Raise `ValueError` for modules without mapped setups.
- [ ] Implement `setup_to_modules(setup: str) -> list[StrategyModule]`.
  - Normalize setup names with `str(setup).strip()`.
  - Return all modules whose `mapped_setups` contains the setup.
  - Return `[]` for unknown or empty setup names.
- [ ] Implement `module_ids_for_setup(setup: str) -> list[str]`.
- [ ] Implement `attach_modules_to_events(events: pd.DataFrame) -> pd.DataFrame`.
  - Preserve empty inputs.
  - Add `module_ids` as a comma-separated string.
  - Add `module_count`.
- [ ] Implement `aggregate_module_summary(setup_summary: pd.DataFrame) -> pd.DataFrame`.
  - For each setup row, map it to all matching modules.
  - Aggregate weighted metrics by `trades`.
  - Output at least:
    - `module_id`
    - `module_name`
    - `source_setups`
    - `mapped_setup_count`
    - `trades`
    - `win_rate_pct`
    - `expectancy_r`
    - `net_expectancy_r`
    - `net_profit_factor`
    - `avg_cost_r`
    - `sample_quality`
    - `module_gate`
    - `gate_reason`
  - Sort by `module_gate` priority, `net_expectancy_r`, `win_rate_pct`, and `trades`.
- [ ] Implement `classify_module_gate(row: Mapping[str, Any]) -> tuple[str, str]`.
  - Return gate and human-readable reason.
  - Use thresholds from the design:
    - positive net expectancy: `net_expectancy_r > 0`
    - marginal net expectancy: `-0.05 <= net_expectancy_r <= 0`
    - weak net expectancy: `net_expectancy_r < -0.05`
    - positive net profit factor: `net_profit_factor > 1.0`
    - acceptable sample quality: `sample_quality in {"higher", "medium"}`
- [ ] Implement `build_module_candidates(current_decision_queue: pd.DataFrame, setup_summary: pd.DataFrame) -> pd.DataFrame`.
  - Map current decision queue rows through setup families.
  - Join setup-level metrics from `setup_summary`.
  - Add module metadata and module gate.
  - Preserve empty current queues by returning an empty DataFrame with stable columns.
- [ ] Run:
  - `.venv/bin/python -m pytest tests/test_strategy_modules.py -q`
  - Expected result after implementation: all tests pass.

## Task 3: Add Standalone Report Rendering Tests

- [ ] Create `tests/test_named_strategy_modules_report.py`.
- [ ] Import `build_named_strategy_modules_markdown` and `markdown_to_html` from `scripts.research_signal_effectiveness`.
- [ ] Add `test_named_strategy_modules_markdown_contains_all_modules_and_candidates`.
  - Build synthetic `module_summary` and `module_candidates` DataFrames.
  - Assert the Markdown includes:
    - `# Agent Adda Named Strategy Modules`
    - all eight module display names
    - `Current Module Candidates`
    - `Research only. Not investment advice.`
    - source trail lines for module summary and candidate CSV paths.
- [ ] Add `test_named_strategy_modules_html_renders_tables`.
  - Convert the Markdown with existing `markdown_to_html`.
  - Assert HTML includes `<table>`, module names, and no raw Markdown table separators.
- [ ] Run expected failing tests:
  - `.venv/bin/python -m pytest tests/test_named_strategy_modules_report.py -q`
  - Expected result before report implementation: import failure for `build_named_strategy_modules_markdown`.

## Task 4: Integrate Modules Into Signal Effectiveness Pipeline

- [ ] Modify imports in `scripts/research_signal_effectiveness.py`.
  - Add:
    - `aggregate_module_summary`
    - `attach_modules_to_events`
    - `build_module_candidates`
    - `STRATEGY_MODULES`
- [ ] Add constant:
  - `MODULE_REPORT_DIR = ROOT / "reports" / "strategy_modules"`
- [ ] In `write_outputs(...)`, before writing the event CSV:
  - Call `attach_modules_to_events(events)`.
  - Use the enriched event DataFrame for event CSV output.
- [ ] In `write_outputs(...)`, after `cost_maps` and `regime_maps` are built:
  - Compute `module_summary = aggregate_module_summary(setup_summary)`.
  - Compute `module_candidates = build_module_candidates(current_decision_queue, setup_summary)`.
- [ ] Extend `paths` with:
  - `module_summary`
  - `module_candidates`
  - `named_modules_md`
  - `named_modules_html`
- [ ] Write:
  - `module_summary.to_csv(paths["module_summary"], index=False)`
  - `module_candidates.to_csv(paths["module_candidates"], index=False)`
- [ ] Copy latest CSVs:
  - `reports/latest/named_strategy_module_summary.csv`
  - `reports/latest/named_strategy_module_candidates.csv`
- [ ] Implement `build_named_strategy_modules_markdown(...)` in `scripts/research_signal_effectiveness.py`.
  - Inputs:
    - `module_summary`
    - `module_candidates`
    - `latest_trade_date`
    - `selected_symbols`
    - `args`
    - `paths`
  - Sections:
    - title and metadata
    - module research thesis
    - module leaderboard
    - one section per module with rules, no-trade filters, failure modes, and metrics
    - current module candidates
    - diagnostics for empty candidates or unmapped setups
    - source trail
    - research-only disclaimer
- [ ] Generate and write:
  - `reports/strategy_modules/named_strategy_modules_<stamp>.md`
  - `reports/strategy_modules/named_strategy_modules_<stamp>.html`
  - latest Markdown/HTML copies under `reports/latest`.
- [ ] Add a short section to the existing signal-effectiveness Markdown from `build_markdown(...)`.
  - Section title: `## Named Strategy Modules`
  - Include top module summary table and link/path references to standalone module report and CSVs.
- [ ] Preserve existing printed CLI lines and add:
  - `Named modules: {paths['named_modules_html']}`
- [ ] Run:
  - `.venv/bin/python -m pytest tests/test_strategy_modules.py tests/test_named_strategy_modules_report.py tests/test_signal_effectiveness_regime.py -q`
  - Expected result: all selected tests pass.

## Task 5: Generate Backtest Reports

- [ ] Run a fast smoke report over a smaller liquid universe:
  - Command: `.venv/bin/python scripts/research_signal_effectiveness.py --top-n 50 --start 2026-01-01 --lookback 2025-10-01 --min-trades 1 --min-regime-trades 5`
  - Expected output includes:
    - `Signal effectiveness research complete`
    - `Markdown:`
    - `HTML:`
    - `Named modules:`
- [ ] Verify latest outputs exist:
  - `test -s reports/latest/named_strategy_modules.md`
  - `test -s reports/latest/named_strategy_modules.html`
  - `test -s reports/latest/named_strategy_module_summary.csv`
  - `test -s reports/latest/named_strategy_module_candidates.csv`
- [ ] If the fast smoke succeeds, run the full EOD research universe:
  - Command: `.venv/bin/python scripts/research_signal_effectiveness.py --top-n 500 --start 2023-06-19 --lookback 2023-01-01 --min-trades 3 --min-regime-trades 50`
  - Expected output includes:
    - labelled events count above zero
    - latest signal-effectiveness report paths
    - named module report paths
- [ ] Inspect module report for basic report quality:
  - Command: `sed -n '1,220p' reports/latest/named_strategy_modules.md`
  - Confirm it contains:
    - all eight module sections
    - module leaderboard
    - current module candidates
    - source trail
    - disclaimer

## Task 6: Final Verification

- [ ] Run targeted tests:
  - `.venv/bin/python -m pytest tests/test_strategy_modules.py tests/test_named_strategy_modules_report.py tests/test_signal_effectiveness_regime.py -q`
- [ ] Run import smoke:
  - `.venv/bin/python - <<'PY'
from terminal.strategy_modules import STRATEGY_MODULES, validate_strategy_modules
validate_strategy_modules()
print(len(STRATEGY_MODULES))
PY`
  - Expected output: `8`
- [ ] Check generated files:
  - `ls -lh reports/latest/named_strategy_modules.html reports/latest/named_strategy_module_summary.csv reports/latest/named_strategy_module_candidates.csv`
- [ ] Review `git diff -- terminal/strategy_modules.py scripts/research_signal_effectiveness.py tests/test_strategy_modules.py tests/test_named_strategy_modules_report.py docs/superpowers/plans/2026-06-25-named-strategy-modules.md`.
- [ ] Do not modify or revert unrelated dirty worktree files.

## Completion Criteria

- [ ] Tests for registry, setup mapping, aggregation, gate classification, and report rendering pass.
- [ ] The signal-effectiveness pipeline emits named strategy module Markdown, HTML, summary CSV, and candidate CSV.
- [ ] `reports/latest/named_strategy_modules.html` opens as the current comprehensive module report.
- [ ] Existing signal-effectiveness report output still works.
- [ ] The implementation makes no unsupported investment claims and keeps research-only disclaimers visible.
