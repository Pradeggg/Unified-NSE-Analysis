# Agent Adda Model Benchmark Report

Generated: `2026-05-12T02:48:04`

## Scope

This benchmark compares the main Agent Adda chat backend between OpenAI `gpt-4o` and Ollama `granite4:latest`. Voice STT/TTS models are excluded.

## Backend Status

| Backend | Status | Model | Switch Result |
|---|---|---|---|
| openai | OpenAI (gpt-4o) | gpt-4o | ok |
| ollama | Ollama (granite4:latest) | granite4:latest | ok |

## Heuristic Metrics

| Backend | OK Cases | Error Cases | Avg Time | Avg Tool Calls | Avg Words | Source Trail Cases | Missing Data Flags |
|---|---:|---:|---:|---:|---:|---:|---:|
| openai | 9 | 0 | 2.46s | 2.67 | 212.8 | 7 | 5 |
| ollama | 9 | 0 | 4.88s | 2.22 | 186.6 | 5 | 5 |

## Case Results

| Case | Category | OpenAI Status / Tools / Time | Ollama Status / Tools / Time |
|---|---|---|---|
| `market_overview` | market_overview | ok / 2 / 0.432s | ok / 2 / 0.152s |
| `stock_technical_dmart` | stock_technical | ok / 4 / 0.085s | ok / 4 / 0.059s |
| `education_roce_roe` | market_education | ok / 1 / 1.259s | ok / 1 / 0.773s |
| `compare_stocks` | comparative_research | ok / 4 / 0.083s | ok / 4 / 0.068s |
| `strength_validation` | validated_strength | ok / 1 / 0.342s | ok / 1 / 0.336s |
| `intraday_nifty` | intraday_situation | ok / 1 / 7.67s | ok / 0 / 10.509s |
| `tool_heavy_research` | tool_calls | ok / 4 / 0.09s | ok / 4 / 0.057s |
| `multi_turn_1` | multi_turn_context | ok / 4 / 0.044s | ok / 4 / 0.044s |
| `multi_turn_2` | multi_turn_context | ok / 3 / 12.132s | ok / 0 / 31.923s |

## Report Generation

- Stage 2 Markdown report generated in `0.023s` at `/Users/pgorai/Documents/Projects/Unified-NSE-Analysis/reports/generated/NSE_stage2_20260512_024911.md` with `20131` characters.

## GPT-5.5 Evaluation

- Evaluator model: `gpt-5.5`
- Overall winner: `OpenAI gpt-4o`

### Executive Summary

OpenAI gpt-4o wins on application behavior because it followed tool discipline better in the live intraday NIFTY case and produced more usable, source-labeled output under LLM-driven routing. However, both backends show serious application-level failures: the compare_stocks case returned TALBROAUTO instead of DMART/TRENT/VBL, market_overview omitted FII/DII flow without flagging it, and several stock reports used generic single-stock templates despite broader requests. Ollama granite4:latest matched OpenAI on template-driven tool-routed cases but failed badly on LLM-driven intraday and multi-turn cases, including zero tool calls, blank/near-blank intraday output, and fabricated claims about NAVABUPA/NAVA proprietary analytics. Neither backend is acceptable as an unconstrained autonomous market-research backend without stricter routing, symbol resolution validation, source trails, and missing-evidence gating.

### Strengths

```json
{
  "openai": [
    {
      "score": 4,
      "finding": "Strong tool discipline in most tool-routed cases, with correct calls for market overview, stock brief, strength validation, and intraday NIFTY."
    },
    {
      "score": 4,
      "finding": "Generally good source transparency in templated market and stock outputs, including mode, clock, source labels, and explicit tool trails."
    },
    {
      "score": 4,
      "finding": "Better output usability than Ollama on LLM-driven intraday analysis because it produced actionable levels and freshness labels from a real tool result."
    },
    {
      "score": 3,
      "finding": "Reasonable risk handling in stock briefs by flagging overbought RSI, non-Stage-2 conditions, and missing evidence where template fields support it."
    }
  ],
  "ollama": [
    {
      "score": 4,
      "finding": "Performed similarly to OpenAI on deterministic, template-driven tool routes such as market overview, DMART technicals, strength validation, and WELCORP brief."
    },
    {
      "score": 4,
      "finding": "Fast and stable on simple routed cases, with no reported tool errors in the successful template paths."
    },
    {
      "score": 3,
      "finding": "Preserved disclaimer, mode, clock, and source formatting when the application path generated a standard report template."
    }
  ]
}
```

### Weaknesses

```json
{
  "openai": [
    {
      "score": 2,
      "finding": "Failed comparative stock routing in the DMART/TRENT/VBL case by returning TALBROAUTO, making the answer irrelevant."
    },
    {
      "score": 2,
      "finding": "Poor multi-turn context management in the final turn: it did not resolve 'it' to WELCORP and instead compared NIFTY 50 with NIVABUPA."
    },
    {
      "score": 3,
      "finding": "Sometimes omitted requested dimensions such as FII/DII flow, latest catalysts, forensic red flags, support/resistance, examples, and traps."
    },
    {
      "score": 3,
      "finding": "Evidence transparency is good when a template supplies it, but missing requested data is not always explicitly marked as unavailable."
    }
  ],
  "ollama": [
    {
      "score": 1,
      "finding": "Failed LLM-driven intraday tool discipline: zero tool calls and a near-empty answer despite explicit instruction to use NSE snapshot first."
    },
    {
      "score": 1,
      "finding": "Severe hallucination in multi-turn comparison, including unsupported claims about NAVABUPA/NAVA proprietary analytics, peer-reviewed models, GitHub repositories, and validation studies."
    },
    {
      "score": 1,
      "finding": "Poor context management: did not anchor 'it' to the previous WELCORP analysis and did not validate NAVABUPA/NIVABUPA through tools."
    },
    {
      "score": 2,
      "finding": "Same symbol/routing failure as OpenAI in compare_stocks, returning TALBROAUTO instead of the requested DMART/TRENT/VBL comparison."
    }
  ]
}
```

### Tool Call Findings

```json
{
  "openai_score": 3,
  "ollama_score": 2,
  "findings": [
    "OpenAI made 24 tool calls across the evaluated cases and usually selected relevant tools for routed tasks.",
    "OpenAI correctly used get_nse_intraday_snapshot for the intraday NIFTY instruction, satisfying the NSE-first requirement.",
    "OpenAI still had tool/routing failures: compare_stocks resolved or processed the wrong symbol, and multi_turn_2 mixed resolve_symbol, get_nse_intraday_snapshot, and compare_stocks into an incorrect NIFTY-vs-NIVABUPA comparison.",
    "Ollama matched tool calls in standard intent-routed templates but made zero tool calls in two critical LLM-driven cases: intraday_nifty and multi_turn_2.",
    "Ollama's zero-tool multi_turn_2 response fabricated evidence instead of retrieving or validating it.",
    "Both backends need hard validation that requested tickers match resolved tickers before generating reports."
  ]
}
```

### Context Findings

```json
{
  "openai_score": 2,
  "ollama_score": 1,
  "findings": [
    "OpenAI handled single-turn context adequately but failed the key pronoun-resolution test. It did not treat 'it' as a ticker, but it also did not map 'it' to WELCORP; it substituted NIFTY 50 from a prior intraday case.",
    "Ollama failed the same pronoun-resolution task more severely, producing a generic fabricated evidence-quality essay without grounding either instrument in the prior WELCORP context.",
    "Both systems need conversation-state constraints that bind referents to the immediately preceding stock entity and disallow unrelated symbols unless explicitly requested.",
    "The test specifically asked not to treat common words as symbols. Neither output showed an 'IT' ticker mistake, but both still failed context grounding."
  ]
}
```

### Report Generation Findings

```json
{
  "openai_score": 4,
  "ollama_score": 4,
  "findings": [
    "The stage2 report generation succeeded, produced a Markdown report of 20131 characters, and was generated directly from the DB snapshot with no LLM required.",
    "Because report generation bypassed the model backend, the result does not distinguish OpenAI from Ollama.",
    "The no-LLM report path is a strength for reliability and reproducibility: it avoids hallucinated market data and ensures a deterministic DB-backed artifact.",
    "Recommended improvement: include a machine-readable source manifest, snapshot timestamp, row counts, missing-field counts, and validation checks in the report metadata."
  ]
}
```

### Recommended Backend Policy

```json
{
  "primary_backend": "OpenAI gpt-4o",
  "fallback_backend": "Ollama granite4:latest only for deterministic template-routed tasks after tool outputs are already validated",
  "policy_score": 4,
  "rules": [
    "Use OpenAI gpt-4o for LLM-driven market reasoning, intraday interpretation, and user-facing synthesis.",
    "Use Ollama granite4:latest only where the application controls the data path and the model is not responsible for deciding whether tools are needed.",
    "Do not allow either backend to generate comparative research unless all requested symbols are resolved and echoed back before analysis.",
    "Block final answers when requested fields such as FII/DII flow, catalysts, forensic red flags, RS rank, valuation, or fundamentals are unavailable unless the response explicitly marks them missing.",
    "Require source trails for every market-data answer, including tool names, timestamps, source type, and freshness state.",
    "For multi-turn sessions, maintain an explicit entity memory object and force pronoun resolution against that object before any tool call or narrative answer.",
    "Reject or retry outputs that introduce symbols not requested or not resolved from the user's query."
  ]
}
```

### Remediation Backlog

- `{"priority": 1, "score": 5, "item": "Add a symbol-resolution guardrail that compares requested symbols with resolved symbols and blocks outputs when they mismatch, especially for multi-symbol comparisons."}`
- `{"priority": 2, "score": 5, "item": "Implement mandatory missing-evidence reporting for every requested dimension, including FII/DII flow, support/resistance, RS rank, valuation, catalysts, and forensic red flags."}`
- `{"priority": 3, "score": 5, "item": "Add a multi-turn entity memory layer that records the active company/ticker and resolves pronouns like 'it' before routing or answering."}`
- `{"priority": 4, "score": 5, "item": "Disallow zero-tool answers for live, intraday, latest, current, comparison, or evidence-quality queries unless a cached validated data object is already attached."}`
- `{"priority": 5, "score": 4, "item": "Introduce a hallucination gate that rejects unsupported claims about proprietary analytics, peer review, GitHub repositories, backtests, and methodologies unless backed by retrieved sources."}`
- `{"priority": 6, "score": 4, "item": "Create a dedicated comparative-research workflow that loops over each requested symbol, collects the same evidence fields, and produces a table with missing values explicitly preserved."}`
- `{"priority": 7, "score": 4, "item": "Improve intraday freshness labeling by clearly distinguishing live market data, market-closed snapshots, previous-session close data, and stale fallback data."}`
- `{"priority": 8, "score": 3, "item": "Enhance education answers to satisfy instructional details such as simple examples, common traps, Indian investor context, and source list."}`
- `{"priority": 9, "score": 3, "item": "Standardize source trails across all answer types, including validation outputs and education outputs."}`
- `{"priority": 10, "score": 3, "item": "Add report-generation metadata with DB snapshot timestamp, universe size, filters used, missing-field counts, and validation status."}`

### Case Scores

```json
{
  "market_overview": {
    "openai_score": 3,
    "ollama_score": 3,
    "winner": "tie",
    "notes": "Both called the right market overview and breadth tools, labeled freshness, clock, sources, and market state. Both omitted the requested FII/DII flow and did not explicitly mark it missing, so evidence completeness is only moderate."
  },
  "stock_technical_dmart": {
    "openai_score": 4,
    "ollama_score": 4,
    "winner": "tie",
    "notes": "Both used the expected symbol, snapshot, technical, and sector tools and exposed a source trail. Missing RS was flagged. However, requested support/resistance was not directly provided beyond 52-week range, and the narrative had internal inconsistency between snapshot RSI and technical RSI."
  },
  "education_roce_roe": {
    "openai_score": 3,
    "ollama_score": 3,
    "winner": "tie",
    "notes": "Both used a knowledge search and cited accessible sources while disclosing the Investopedia extraction failure. The answer was source-backed but did not fully satisfy the request for a simple example and common traps in the excerpted output."
  },
  "compare_stocks": {
    "openai_score": 1,
    "ollama_score": 1,
    "winner": "tie",
    "notes": "Severe failure for both. The query asked to compare DMART, TRENT, and VBL, but the response was a single-stock TALBROAUTO brief. This indicates symbol extraction or routing failure and makes the output unusable for the requested comparative research."
  },
  "strength_validation": {
    "openai_score": 4,
    "ollama_score": 4,
    "winner": "tie",
    "notes": "Both used the dedicated validation tool, did not infer missing RS/fundamental/forensic evidence, and flagged missing fields. Source trail was absent, and no clear ranked conclusion was given beyond the raw validation rows."
  },
  "intraday_nifty": {
    "openai_score": 4,
    "ollama_score": 1,
    "winner": "OpenAI gpt-4o",
    "notes": "OpenAI called the NSE intraday snapshot tool, used NSE first as requested, labeled data freshness, and gave usable support/resistance from the snapshot. It could better label the market-closed/stale nature of the snapshot. Ollama made zero tool calls and returned almost no analysis, failing the main instruction."
  },
  "tool_heavy_research": {
    "openai_score": 3,
    "ollama_score": 3,
    "winner": "tie",
    "notes": "Both showed tools used and provided technical and sector context for WELCORP. However, neither retrieved or reported latest catalysts or forensic red flags; missing catalyst/forensic evidence was not explicitly handled."
  },
  "multi_turn_1": {
    "openai_score": 3,
    "ollama_score": 3,
    "winner": "tie",
    "notes": "Both provided a WELCORP stock brief with tool trail and missing RS evidence. The company-analysis component was shallow, and fresh-evidence needs were not comprehensively separated from known DB facts."
  },
  "multi_turn_2": {
    "openai_score": 1,
    "ollama_score": 1,
    "winner": "OpenAI gpt-4o",
    "notes": "Both failed the multi-turn evidence-quality comparison. OpenAI at least used tools, but it lost the antecedent of 'it' and compared NIFTY 50 with NIVABUPA instead of WELCORP with NAVABUPA/NIVABUPA. Ollama made no tool calls, lost context, and fabricated unsupported claims about proprietary NAVA analytics, peer review, GitHub repositories, and econometric methods."
  }
}
```

## Raw Output Location

- JSON: `/Users/pgorai/Documents/Projects/Unified-NSE-Analysis/reports/model_benchmarks/agent_model_benchmark_20260512_025101.json`
