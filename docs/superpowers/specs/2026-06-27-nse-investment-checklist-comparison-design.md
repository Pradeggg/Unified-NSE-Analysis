# NSE Investment Checklist Comparison Design

**Date:** 2026-06-27  
**Project:** Agent Adda / Unified NSE Analysis  
**Status:** Approved for implementation planning  

## Purpose

Add a native Agent Adda capability for NSE-specific multi-stock value research comparison. The first version focuses on a repeatable checklist report for 2-10 NSE stocks, inspired by the decision discipline and financial rigor patterns from `ai-berkshire`, but implemented against Agent Adda's existing evidence stack instead of vendoring that repository.

The goal is to make prompts such as `/investment-checklist TCS INFY HDFCBANK` produce a ranked, evidence-gated comparison report with explicit verdicts, missing evidence, and research-only framing.

## Goals

- Compare multiple NSE stocks through a deterministic value-investing checklist.
- Produce explicit verdicts: `PASS`, `CONDITIONAL`, `WATCH`, `AVOID`, or `INSUFFICIENT_EVIDENCE`.
- Reuse Agent Adda's existing data and evidence tools: fundamentals, latest results, sector context, price history, Stage 2/relative strength, forensic/governance flags, insider/promoter data where available, report validation, and source trails.
- Keep scoring and verdict classification reproducible and testable.
- Use LLM prose only after evidence is collected and rules have generated the score/verdict.
- Render Markdown and HTML reports, with latest copies under `reports/latest/`.

## Non-Goals

- Do not vendor or fork `xbtlin/ai-berkshire` inside this repo.
- Do not build a generic US/HK/India investment framework in V1.
- Do not add broker integration, order placement, or portfolio execution.
- Do not claim investment-adviser status or produce financial advice.
- Do not build a full intrinsic valuation engine in V1.
- Do not require web-only research when Agent Adda already has local evidence.

## User Experience

Primary command:

```text
/investment-checklist TCS INFY HDFCBANK
```

Expected output:

- Ranked comparison table across all resolved symbols.
- One per-stock checklist section.
- Verdict, score, evidence quality, top strengths, top risks, and missing evidence.
- A short "why this ranked higher/lower" comparison narrative.
- Mirror-test thesis with five concise evidence-backed claims, or a failed mirror-test marker when evidence is insufficient.
- Source trail and data freshness block.
- Research-only disclaimer.

V1 should support 2-10 symbols. A single symbol can be accepted, but the workflow is optimized for comparison. Inputs above 10 symbols should ask the user to narrow the list or route to an existing screener workflow first.

## Checklist Dimensions

The workflow uses a 100-point score.

| Dimension | Weight | Intent |
| --- | ---: | --- |
| Understandable business | 10 | Sector, revenue model, cyclicality, dependency risks |
| Business quality | 20 | ROE/ROCE, margins, cash conversion, debt, consistency |
| Moat / competitive position | 15 | Sector leadership, pricing power proxy, relative strength, market position where available |
| Management / governance | 15 | Promoter pledge, insider events, forensic flags, capital allocation evidence |
| Valuation / safety margin | 15 | PE, PB, EV/EBITDA where available, earnings yield, peer and history context where available |
| Technical confirmation | 15 | Stage, relative strength, trend, volume, support/risk context |
| Decision discipline | 10 | Mirror-test quality, invalidation triggers, no-trade flags |

## Verdict Rules

Base verdict from score:

| Verdict | Rule |
| --- | --- |
| `PASS` | Score >= 78, no major red flags, evidence quality at least medium |
| `CONDITIONAL` | Score 65-77, or one important unresolved concern |
| `WATCH` | Score 50-64, mixed evidence, or stretched valuation |
| `AVOID` | Score < 50, or hard red flag |
| `INSUFFICIENT_EVIDENCE` | Required core evidence is missing |

Hard caps:

- Missing fundamentals -> `INSUFFICIENT_EVIDENCE`.
- Severe governance or promoter pledge red flag -> max `WATCH` or `AVOID`, depending severity.
- Negative or weak cash conversion -> max `CONDITIONAL`.
- Stage 4 or severe technical breakdown -> max `WATCH`.
- Excessive valuation without quality/growth support -> max `WATCH`.
- Stale or low-confidence evidence across multiple core dimensions -> max `WATCH`.

Ranking order:

1. Verdict priority.
2. Total score.
3. Evidence quality.
4. Governance safety.
5. Valuation reasonableness.
6. Technical confirmation.

## Architecture

Add a native value-checklist layer rather than copying `ai-berkshire` prompts.

### Core Module

Create `terminal/value_checklist.py`.

Responsibilities:

- Define checklist data classes.
- Normalize per-symbol evidence into a stable internal model.
- Score each dimension.
- Apply hard caps and verdict rules.
- Rank symbols.
- Build Markdown-ready report sections.
- Preserve missing evidence and source trails as first-class fields.

### Command and Tool Routing

Wire `/investment-checklist` through the existing terminal command path. The command should:

1. Parse requested symbols.
2. Resolve NSE symbols using existing symbol resolution.
3. Collect evidence per symbol.
4. Run checklist scoring.
5. Render a deterministic report.
6. Save timestamped and latest Markdown/HTML outputs.

V1 should keep the workflow behind the terminal command and internal Python functions. A public router or Research Council tool can be added in Phase 2.

### Research Council Compatibility

Research Council integration is Phase 2. The V1 implementation should keep its scoring/reporting module shaped so a later `investment_checklist` or `value_checklist` mode profile can call it without rewriting the scoring logic.

### Evidence Inputs

Reuse existing providers where available:

- Screener/fundamental cache and fundamental score derivation.
- Latest results and earnings data.
- Sector context and sector rotation evidence.
- Price history, Stage 2 state, relative strength, VCP/breakout context.
- Forensic and governance evidence.
- Insider/promoter/pledge data where available.
- Report validation and source trail utilities.

Evidence collection must fail open per symbol: if one stock has missing data, the report should still compare the others and mark the incomplete stock explicitly.

## Data Model

Suggested structures in `terminal/value_checklist.py`:

```python
@dataclass(frozen=True)
class ValueChecklistEvidence:
    symbol: str
    company_name: str
    sector: str
    fundamentals: Mapping[str, Any]
    valuation: Mapping[str, Any]
    governance: Mapping[str, Any]
    technical: Mapping[str, Any]
    latest_results: Mapping[str, Any]
    source_trail: tuple[Mapping[str, Any], ...]
    missing_evidence: tuple[str, ...]
    freshness: Mapping[str, str]

@dataclass(frozen=True)
class ChecklistDimensionScore:
    name: str
    weight: float
    raw_score: float
    weighted_score: float
    reasons: tuple[str, ...]
    missing_evidence: tuple[str, ...]

@dataclass(frozen=True)
class ValueChecklistResult:
    symbol: str
    company_name: str
    verdict: str
    total_score: float
    evidence_quality: str
    dimension_scores: tuple[ChecklistDimensionScore, ...]
    hard_caps: tuple[str, ...]
    top_strengths: tuple[str, ...]
    top_risks: tuple[str, ...]
    mirror_test: tuple[str, ...]
    mirror_test_passed: bool
    source_trail: tuple[Mapping[str, Any], ...]
    missing_evidence: tuple[str, ...]
```

The exact field names can be adjusted during implementation to match local conventions, but the report contract should preserve these concepts.

## Report Output

Timestamped outputs:

- `reports/value_checklists/investment_checklist_<stamp>.md`
- `reports/value_checklists/investment_checklist_<stamp>.html`
- `reports/value_checklists/investment_checklist_summary_<stamp>.csv`

Latest outputs:

- `reports/latest/investment_checklist.md`
- `reports/latest/investment_checklist.html`
- `reports/latest/investment_checklist_summary.csv`.

Report sections:

1. Title and metadata.
2. Ranked comparison table.
3. Verdict distribution.
4. Why the top-ranked stock ranks highest.
5. Per-stock checklist sections.
6. Mirror-test section per stock.
7. Missing evidence and limitations.
8. Source trail.
9. Research-only disclaimer.

## Error Handling

- Unknown symbol -> list unresolved token, continue with resolved symbols if at least one valid symbol exists.
- Fewer than two valid symbols -> allow single-stock mode but state that comparison context is limited.
- No fundamentals for a symbol -> `INSUFFICIENT_EVIDENCE`.
- Tool or database failure -> mark affected evidence category missing and continue.
- HTML rendering failure -> keep Markdown output and report the HTML failure.
- LLM synthesis failure -> keep deterministic scoring report.

## Testing Strategy

Add focused tests before implementation:

- `tests/test_value_checklist.py`
  - scoring weights sum to 100.
  - missing fundamentals returns `INSUFFICIENT_EVIDENCE`.
  - governance red flag caps verdict.
  - Stage 4 caps verdict at `WATCH`.
  - strong quality plus reasonable valuation outranks weak expensive names.
  - mirror-test fails when required claims cannot be supported.

- `tests/test_terminal_investment_checklist.py`
  - `/investment-checklist TCS INFY` routes to the new workflow.
  - unresolved symbols are reported without breaking valid symbols.
  - output contains comparison table, per-stock sections, source trail, missing evidence, and disclaimer.

- `tests/test_value_checklist_report.py`
  - Markdown converts to HTML without raw Markdown table separators.

## Rollout Plan

Phase 1:

- Deterministic scoring module.
- Terminal command.
- Markdown/HTML report.
- Latest output copies.
- Unit and command tests.

Phase 2:

- Research Council mode profile.
- LLM prose synthesis using deterministic scores as the source of truth.
- Report audit sampling for financial data points.

Phase 3:

- Deep single-stock value research mode.
- Earnings-review mode.
- Portfolio-thesis mode.

## Acceptance Criteria

- `/investment-checklist TCS INFY HDFCBANK` produces a ranked report without relying on hidden or uncited claims.
- Each stock receives a score, verdict, strengths, risks, missing evidence, and mirror-test result.
- Missing required evidence blocks unsupported conclusions.
- Hard caps are applied deterministically.
- Report outputs are saved under timestamped and latest paths.
- Tests cover scoring, caps, missing evidence, routing, and report shape.
- The report clearly states: research only, not investment advice.
