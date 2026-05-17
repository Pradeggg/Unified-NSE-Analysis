# Agent Adda Model Benchmark Report

Generated: `2026-05-12T03:18:30`

## Scope

This benchmark compares the main Agent Adda chat backend between OpenAI `gpt-4o` and Ollama `granite4:latest`. Voice STT/TTS models are excluded.

## Backend Status

| Backend | Status | Model | Switch Result |
|---|---|---|---|
| openai | OpenAI (gpt-4o) | gpt-4o | ok |
| ollama | Ollama (granite4:latest) | granite4:latest | ok |

## Heuristic Metrics

| Backend | OK Cases | Error Cases | Avg Time | Avg Tool Calls | Avg Words | Source Trail Cases | Missing Data Flags | Factual Pass | Factual Fail |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| openai | 52 | 0 | 1.682s | 1.73 | 181.6 | 17 | 15 | 46 | 6 |
| ollama | 50 | 2 | 6.133s | 1.56 | 185.7 | 15 | 13 | 40 | 10 |

## Case Results

| Case | Category | OpenAI Status / Tools / Factual / Time | Ollama Status / Tools / Factual / Time |
|---|---|---|---|
| `market_overview` | market_overview | ok / 2 / pass / 0.423s | ok / 2 / pass / 0.075s |
| `stock_technical_dmart` | stock_technical | ok / 4 / pass / 0.065s | ok / 4 / pass / 0.053s |
| `education_roce_roe` | market_education | ok / 1 / pass / 0.746s | ok / 1 / pass / 0.783s |
| `compare_stocks` | comparative_research | ok / 4 / fail / 0.072s | ok / 4 / fail / 0.077s |
| `strength_validation` | validated_strength | ok / 1 / pass / 0.361s | ok / 1 / pass / 0.359s |
| `intraday_nifty` | intraday_situation | ok / 2 / pass / 6.398s | ok / 1 / fail / 23.721s |
| `tool_heavy_research` | tool_calls | ok / 4 / pass / 0.042s | ok / 4 / pass / 0.067s |
| `prompt_market` | prompt_library | ok / 2 / pass / 0.06s | ok / 2 / pass / 0.061s |
| `prompt_intraday` | prompt_library | ok / 3 / pass / 7.427s | ok / 1 / fail / 21.245s |
| `prompt_technical` | prompt_library | ok / 4 / pass / 0.063s | ok / 4 / pass / 0.066s |
| `prompt_sector` | prompt_library | ok / 2 / fail / 0.064s | ok / 2 / fail / 0.059s |
| `prompt_screener` | prompt_library | ok / 1 / pass / 10.527s | ok / 0 / fail / 8.27s |
| `prompt_fundamentals` | prompt_library | ok / 4 / fail / 0.064s | ok / 4 / fail / 0.131s |
| `prompt_stock` | prompt_library | ok / 5 / pass / 2.95s | ok / 5 / pass / 3.429s |
| `prompt_news` | prompt_library | ok / 2 / pass / 13.474s | ok / 0 / pass / 57.361s |
| `prompt_portfolio` | prompt_library | ok / 4 / fail / 0.084s | ok / 4 / fail / 0.084s |
| `prompt_global` | prompt_library | ok / 1 / pass / 9.4s | error / 0 / fail / 60.007s |
| `scan_default` | slash_scan | ok / 1 / pass / 1.01s | ok / 1 / pass / 0.256s |
| `scan_nifty_bank` | slash_scan | ok / 1 / pass / 0.232s | ok / 1 / pass / 0.202s |
| `scan_nifty_midcap` | slash_scan | ok / 1 / pass / 0.157s | ok / 1 / pass / 0.213s |
| `scan_orb` | slash_scan | ok / 1 / pass / 0.196s | ok / 1 / pass / 0.138s |
| `scan_gap` | slash_scan | ok / 1 / pass / 0.143s | ok / 1 / pass / 0.141s |
| `scan_macd` | slash_scan | ok / 1 / pass / 0.191s | ok / 1 / pass / 0.197s |
| `scan_rsi` | slash_scan | ok / 1 / pass / 0.173s | ok / 1 / pass / 0.14s |
| `scan_bb` | slash_scan | ok / 1 / pass / 0.15s | ok / 1 / pass / 0.147s |
| `scan_vwap` | slash_scan | ok / 1 / pass / 0.16s | ok / 1 / pass / 0.14s |
| `scan_vcp` | slash_scan | ok / 1 / pass / 0.159s | ok / 1 / pass / 0.132s |
| `scan_momentum` | slash_scan | ok / 1 / pass / 0.157s | ok / 1 / pass / 0.156s |
| `screen_stage2` | slash_screen | ok / 1 / pass / 0.006s | ok / 1 / pass / 0.006s |
| `screen_momentum` | slash_screen | ok / 1 / pass / 0.005s | ok / 1 / pass / 0.005s |
| `screen_highrs` | slash_screen | ok / 1 / pass / 0.005s | ok / 1 / pass / 0.006s |
| `screen_turnaround` | slash_screen | ok / 1 / pass / 0.005s | ok / 1 / pass / 0.005s |
| `screen_base` | slash_screen | ok / 1 / pass / 0.011s | ok / 1 / pass / 0.005s |
| `screen_tight` | slash_screen | ok / 1 / pass / 0.005s | ok / 1 / pass / 0.005s |
| `screen_dip` | slash_screen | ok / 1 / pass / 0.005s | ok / 1 / pass / 0.004s |
| `cmd_model_status` | slash_command | ok / 0 / pass / 0.0s | ok / 0 / pass / 0.0s |
| `cmd_prompts_catalog` | slash_command | ok / 0 / pass / 0.0s | ok / 0 / pass / 0.0s |
| `cmd_backtest_list` | slash_command | ok / 0 / pass / 0.014s | ok / 0 / pass / 0.0s |
| `cmd_backtest_validate` | slash_command | ok / 0 / pass / 0.005s | ok / 0 / pass / 0.009s |
| `cmd_strength` | slash_command | ok / 0 / pass / 0.394s | ok / 0 / pass / 0.448s |
| `cmd_report_stage2_md` | slash_command | ok / 0 / pass / 0.011s | ok / 0 / pass / 0.01s |
| `cmd_report_sector_rotation_md` | slash_command | ok / 0 / pass / 0.004s | ok / 0 / pass / 0.004s |
| `learn_pe_ratio` | market_education | ok / 1 / pass / 1.183s | ok / 1 / pass / 1.241s |
| `learn_minervini` | market_education | ok / 1 / pass / 1.477s | ok / 1 / pass / 1.528s |
| `stock_brief_welcorp` | stock_brief | ok / 4 / pass / 0.063s | ok / 4 / pass / 0.063s |
| `stock_brief_navabupa` | stock_brief | ok / 4 / fail / 0.059s | ok / 4 / fail / 0.057s |
| `stock_brief_ushamart` | stock_brief | ok / 4 / pass / 0.043s | ok / 4 / pass / 0.043s |
| `market_clock` | market_clock | ok / 2 / pass / 0.066s | ok / 2 / pass / 0.365s |
| `fno_options` | fno | ok / 1 / pass / 6.988s | ok / 1 / fail / 22.983s |
| `global_readthrough` | global | ok / 1 / pass / 12.563s | error / 0 / fail / 60.007s |
| `multi_turn_1` | multi_turn_context | ok / 4 / pass / 0.066s | ok / 4 / pass / 0.058s |
| `multi_turn_2` | multi_turn_context | ok / 4 / fail / 9.535s | ok / 0 / fail / 54.331s |

## Factual Check Failures

### openai

- `compare_stocks`: `{"missing_symbols": ["DMART", "TRENT", "VBL"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": ["TALBROAUTO"], "data_freshness_issue": false, "error": null}`
- `prompt_sector`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["sector"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `prompt_fundamentals`: `{"missing_symbols": ["TCS"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `prompt_portfolio`: `{"missing_symbols": ["RELIANCE", "TCS", "HDFCBANK"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `stock_brief_navabupa`: `{"missing_symbols": ["NAVABUPA"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `multi_turn_2`: `{"missing_symbols": ["WELCORP"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`

### ollama

- `compare_stocks`: `{"missing_symbols": ["DMART", "TRENT", "VBL"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": ["TALBROAUTO"], "data_freshness_issue": false, "error": null}`
- `intraday_nifty`: `{"missing_symbols": [], "missing_required_tools": ["get_nse_intraday_snapshot"], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `prompt_intraday`: `{"missing_symbols": ["RELIANCE"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `prompt_sector`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["sector"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `prompt_screener`: `{"missing_symbols": [], "missing_required_tools": ["run_screener_query"], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `prompt_fundamentals`: `{"missing_symbols": ["TCS"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `prompt_portfolio`: `{"missing_symbols": ["RELIANCE", "TCS", "HDFCBANK"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `prompt_global`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["global"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": "ReadTimeout: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=60)"}`
- `stock_brief_navabupa`: `{"missing_symbols": ["NAVABUPA"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `fno_options`: `{"missing_symbols": ["NIFTY"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `global_readthrough`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["global", "India"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": "ReadTimeout: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=60)"}`
- `multi_turn_2`: `{"missing_symbols": ["WELCORP"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": ["proprietary"], "data_freshness_issue": false, "error": null}`

## Report Generation

- Stage 2 Markdown report generated in `0.025s` at `/Users/pgorai/Documents/Projects/Unified-NSE-Analysis/reports/generated/NSE_stage2_20260512_032518.md` with `20131` characters.

## GPT-5.5 Evaluation

- Evaluator model: `gpt-5.5`
- Overall winner: `OpenAI gpt-4o`

### Executive Summary

```json
{
  "score": 4,
  "finding": "OpenAI gpt-4o is the safer default backend for Agent Adda. Both backends perform well on deterministic slash commands, market overview, stock brief templates, strength validation, education with guarded sources, and DB-generated reports. However, OpenAI is materially more reliable on LLM-driven intraday, options, global, and news-style tasks. Ollama granite4:latest shows severe tool-discipline failures, timeouts, fabricated catalysts, wrong instrument context, and missing required tools in several non-template cases. OpenAI still has serious application-level failures: multi-symbol comparisons often collapse to a single unrelated symbol, TCS resolves to QGOLDHALF, portfolio comparison resolves to TALBROAUTO, sector analysis returns generic market overview, NAVABUPA/NIVABUPA spelling is mishandled, and multi-turn WELCORP context is lost. These appear partly caused by orchestration/symbol-resolution/routing logic, but backend choice affects how badly LLM-driven paths degrade."
}
```

### Strengths

```json
{
  "openai": [
    {
      "score": 4,
      "finding": "Good tool use on most template-driven cases: market overview, single-stock technical setup, strength validation, news/catalyst search, intraday snapshot, option chain, global assessment, and screeners."
    },
    {
      "score": 4,
      "finding": "Generally strong evidence transparency: frequent source trail, data date, market clock, missing evidence, and not-investment-advice language."
    },
    {
      "score": 4,
      "finding": "Better resilience on LLM-driven paths than Ollama. It handled NIFTY intraday, RELIANCE intraday after an intraday_ohlcv table error, global read-through, options context, and catalyst search."
    },
    {
      "score": 5,
      "finding": "Deterministic report commands and DB-generated outputs were clean, fast, and usable."
    }
  ],
  "ollama": [
    {
      "score": 4,
      "finding": "Matched OpenAI on deterministic or heavily orchestrated flows such as market overview, single-symbol stock briefs, education search, slash screeners, strength command, model status, prompt catalog, and report commands."
    },
    {
      "score": 4,
      "finding": "Very fast where no generative reasoning was required or where app templates dominated output."
    },
    {
      "score": 3,
      "finding": "Some source-backed educational answers were appropriately conservative and refused unsupported inference."
    }
  ]
}
```

### Weaknesses

```json
{
  "openai": [
    {
      "score": 1,
      "finding": "Severe multi-symbol failures: DMART/TRENT/VBL and RELIANCE/TCS/HDFCBANK comparisons returned TALBROAUTO instead of requested symbols."
    },
    {
      "score": 1,
      "finding": "Symbol-resolution failure for TCS fundamental review returned QGOLDHALF, a wrong instrument."
    },
    {
      "score": 2,
      "finding": "Multi-turn context failure: follow-up referring to WELCORP as 'it' became TALBROAUTO vs NIVABUPA, despite explicit instruction not to treat 'it' as a ticker."
    },
    {
      "score": 2,
      "finding": "Sector analysis prompt for IT returned generic market overview and did not cover sector breadth, leaders, laggards, rotation, or sector-specific risks."
    },
    {
      "score": 3,
      "finding": "Some outputs did not include explicit source trail even when tools were used, especially global, news, option-chain, and screener explanation cases."
    }
  ],
  "ollama": [
    {
      "score": 1,
      "finding": "Major tool-discipline failures in LLM-driven cases: used get_options_chain for NIFTY intraday and RELIANCE intraday instead of required intraday tools."
    },
    {
      "score": 1,
      "finding": "Fabricated or unsupported news/catalyst content for INFY with no tool calls, including implausible events and stale/fake freshness claims."
    },
    {
      "score": 1,
      "finding": "Timeouts on global market prompts at 60 seconds, making the backend unreliable for broader reasoning tasks."
    },
    {
      "score": 1,
      "finding": "FNO option-chain answer failed NIFTY context and discussed a generic stock ID/EOD data with stale 2023 date."
    },
    {
      "score": 1,
      "finding": "Multi-turn context failed catastrophically: NAVABUPA was treated as a pharmaceutical company and compared with Gilead/Merck-style entities, omitting WELCORP."
    },
    {
      "score": 2,
      "finding": "Output usability degrades on LLM-driven tasks due to irrelevant calculations, raw pseudo-tool-call text, fabricated tables, and long unsupported answers."
    }
  ]
}
```

### Tool Call Findings

```json
{
  "score": 3,
  "openai": "Mostly disciplined. It used required tools in most cases: get_live_market_overview, get_market_breadth, resolve_symbol, get_symbol_snapshot, get_technical_setup, get_sector_context, validate_strength_watchlist, get_nse_intraday_snapshot, run_screener_query, search_latest_catalysts, get_global_market_assessment, and get_option_chain. Weaknesses include one intraday tool error, incomplete tool coverage for WELCORP catalysts/forensics, and failures where multi-symbol requests were routed through a single stock brief.",
  "ollama": "Acceptable on deterministic/template routes, but poor on open-ended LLM routes. It called get_options_chain for intraday technical analysis, skipped run_screener_query in the Stage 2 prompt-library screener case, returned raw tool-call-like text, skipped tools for INFY catalysts, and timed out on global tools. This indicates weak tool planning and poor adherence to required tool constraints.",
  "notable_failures": [
    "Ollama intraday_nifty missing get_nse_intraday_snapshot and answered with options OI ratio.",
    "Ollama prompt_intraday for RELIANCE missed the symbol and answered generic options chain data.",
    "Ollama prompt_screener had zero real tool calls and emitted a run_scenario_analysis pseudo-call for RELIANCE.",
    "OpenAI compare_stocks and prompt_portfolio used stock-brief tools but returned unrelated TALBROAUTO instead of requested multi-symbol comparisons."
  ]
}
```

### Context Findings

```json
{
  "score": 1,
  "openai": "Failed the key multi-turn follow-up. It should have carried WELCORP from the previous turn and compared WELCORP with NAVABUPA/NIVABUPA, but returned TALBROAUTO vs NIVABUPA. It did not treat 'it' as a ticker, but still lost the referent.",
  "ollama": "Failed worse. It did not use tools, did not retain WELCORP, and fabricated a pharmaceutical-company comparison involving unrelated global pharma entities. This is unsafe for finance use.",
  "shared_issue": "The benchmark reveals insufficient conversation-state binding between resolved symbols and pronoun references. A context memory layer should store last_resolved_symbols and enforce follow-up resolution before tool execution or answer generation."
}
```

### Report Generation Findings

```json
{
  "score": 5,
  "finding": "Report generation is strong and backend-independent. /report stage2 md and /report sector-rotation md succeeded for both, returning paths, format, title, report_type, symbol, success=true, and a note that the report was generated directly from DB snapshot with no LLM required. The standalone report_generation result also succeeded with 20,131 content characters.",
  "risk": "Because report generation bypasses LLMs, it should remain deterministic. The main risk is not the model but whether reports include enough source/freshness metadata and missing-field disclosures inside the generated file."
}
```

### Factual Accuracy Findings

```json
{
  "score": 2,
  "openai": "Moderate. Many single-symbol and market cases passed factual checks, but high-severity failures include wrong symbols TALBROAUTO and QGOLDHALF, missing requested symbols in multi-stock comparisons, NAVABUPA spelling mismatch, sector prompt omission, and context loss. Some news/global/options content needs stronger source trails.",
  "ollama": "Weak. It inherits the same deterministic symbol/routing failures and adds backend-specific hallucinations: fabricated INFY catalysts, irrelevant options-chain answers, generic EOD stock-ID option data for NIFTY, wrong NAVABUPA identity, and global timeouts.",
  "penalties_applied": [
    "Wrong symbols and missing requested symbols.",
    "Treating multi-symbol comparative tasks as single-symbol stock briefs.",
    "Fabricated data and unsupported news/catalysts.",
    "Missing required factual checks/tool calls.",
    "Incorrect or stale instrument context in options/intraday answers."
  ]
}
```

### Command Coverage Findings

```json
{
  "score": 4,
  "finding": "Slash command coverage is broad and mostly reliable for /model, /prompts, /backtest list, /strategy-lab validate, /strength, /report, /screen variants, and /scan variants. The main weakness is semantic coverage: /scan NIFTY BANK and /scan NIFTY MIDCAP 100 still scanned only RELIANCE, suggesting index/universe arguments are not honored. Prompt-library natural-language equivalents are less reliable than slash commands, especially sector, screener explanation, portfolio comparison, and fundamentals.",
  "openai": "Better for natural-language prompt-library cases, but still fails several important routes.",
  "ollama": "Good when commands bypass the LLM; poor when natural-language prompts require tool selection or reasoning."
}
```

### Recommended Backend Policy

```json
{
  "score": 4,
  "default_backend": "OpenAI gpt-4o",
  "policy": [
    "Use OpenAI gpt-4o as the default backend for natural-language research, intraday analysis, options, global macro, news/catalysts, and any task requiring multi-step tool planning.",
    "Allow Ollama granite4:latest only for deterministic, template-dominated, or offline-safe commands such as /model, /prompts, /screen, /scan, /strength, /report, and /strategy-lab validate, where application code controls tool execution and output.",
    "Disable Ollama for LLM-driven intraday, news, options, global, and multi-turn contexts until tool discipline, timeout behavior, and hallucination controls are remediated.",
    "Route multi-symbol comparisons through a deterministic multi-symbol workflow regardless of backend; do not allow generic stock_brief fallback.",
    "Require post-generation factual validation before returning any answer with ticker symbols, option chain data, catalysts, global macro data, or claimed freshness."
  ],
  "fallback_policy": "If OpenAI tool calls fail, return a missing-evidence answer rather than falling back to Ollama for generative completion. Ollama fallback should be limited to deterministic command outputs."
}
```

### Remediation Backlog

- `{"priority": "P0", "score": 1, "item": "Fix multi-symbol routing so comparative queries resolve and fetch every requested symbol, not a single default or unrelated symbol."}`
- `{"priority": "P0", "score": 1, "item": "Harden symbol resolver with exact-match validation and reject wrong outputs such as TCS -> QGOLDHALF, portfolio -> TALBROAUTO, and NAVABUPA/NIVABUPA ambiguity unless explicitly explained."}`
- `{"priority": "P0", "score": 1, "item": "Add a final answer validator that checks all requested symbols appear and no forbidden/unrequested symbols appear unless clearly identified as peers."}`
- `{"priority": "P0", "score": 1, "item": "Disable or gate Ollama granite4:latest for LLM-driven tool selection until it stops using options-chain tools for intraday prompts and stops emitting pseudo-tool calls."}`
- `{"priority": "P0", "score": 1, "item": "Implement source-grounding enforcement for news/catalyst answers: no tool call or no URL/date means no catalyst claim."}`
- `{"priority": "P1", "score": 2, "item": "Persist conversation context with last_resolved_symbols and require explicit pronoun resolution before follow-up answers."}`
- `{"priority": "P1", "score": 2, "item": "Create dedicated sector-analysis tools/routes so IT sector prompts return sector breadth, leaders, laggards, rotation, and risks instead of generic market overview."}`
- `{"priority": "P1", "score": 2, "item": "Require freshness labels on every live/intraday/options/global answer: source, timestamp, market open/closed state, and whether data is live, cached, EOD, or fallback."}`
- `{"priority": "P1", "score": 2, "item": "Fix scan universe parsing so /scan NIFTY BANK and /scan NIFTY MIDCAP 100 scan the intended index constituents rather than default RELIANCE."}`
- `{"priority": "P1", "score": 3, "item": "Improve missing-evidence reporting in screener explanations; when relative_strength is null, do not describe RS-qualified screens as if RS evidence exists."}`
- `{"priority": "P2", "score": 3, "item": "Standardize source trails across all generated answers, including education, global, options, news, and screener explanation cases."}`
- `{"priority": "P2", "score": 3, "item": "Add latency/timeouts policy for local backends: early abort, structured timeout response, and fallback only to deterministic data summaries."}`

### Case Scores

```json
{
  "openai": {
    "overall": 3,
    "tool_discipline": 4,
    "evidence_transparency": 4,
    "instruction_following": 3,
    "market_reasoning": 3,
    "risk_handling": 4,
    "context_management": 2,
    "factual_data_checks": 3,
    "report_generation": 5,
    "output_usability": 4
  },
  "ollama": {
    "overall": 2,
    "tool_discipline": 2,
    "evidence_transparency": 3,
    "instruction_following": 2,
    "market_reasoning": 2,
    "risk_handling": 3,
    "context_management": 1,
    "factual_data_checks": 2,
    "report_generation": 5,
    "output_usability": 2
  },
  "category_scores": {
    "market_overview": {
      "openai": 4,
      "ollama": 4,
      "notes": "Both used get_live_market_overview and get_market_breadth, disclosed NSE closed clock and source freshness. FII/DII flow was requested but not visibly satisfied, so not a perfect score."
    },
    "stock_technical_single_symbol": {
      "openai": 4,
      "ollama": 4,
      "notes": "Both handled DMART, RELIANCE, WELCORP, USHAMART via resolve_symbol, snapshot, technical setup, and sector context. Missing evidence was usually flagged."
    },
    "multi_symbol_comparative_research": {
      "openai": 1,
      "ollama": 1,
      "notes": "Both failed DMART/TRENT/VBL and RELIANCE/TCS/HDFCBANK comparisons by returning TALBROAUTO. This is a major factual and routing failure."
    },
    "intraday_analysis": {
      "openai": 4,
      "ollama": 1,
      "notes": "OpenAI used NSE intraday snapshot first for NIFTY and handled RELIANCE despite one table error. Ollama used options-chain data instead of required NSE intraday snapshot and produced irrelevant option OI text."
    },
    "screeners_and_slash_commands": {
      "openai": 4,
      "ollama": 4,
      "notes": "Slash screen, scan, strength, model, prompts, and strategy-lab commands are mostly deterministic and worked similarly. Some scan index inputs still scanned only RELIANCE, indicating command coverage/routing limitations."
    },
    "education": {
      "openai": 4,
      "ollama": 4,
      "notes": "Both used source-backed education and refused to infer Minervini/VCP when reliable sources were unavailable. Source trail could be clearer."
    },
    "news_and_catalysts": {
      "openai": 3,
      "ollama": 1,
      "notes": "OpenAI used catalyst/search tools and gave URLs, though source trail/freshness granularity was limited. Ollama produced long, likely fabricated INFY catalysts without tool calls."
    },
    "global_macro": {
      "openai": 4,
      "ollama": 1,
      "notes": "OpenAI completed global assessment using the global market tool. Ollama timed out on global read-through cases."
    },
    "fno_options": {
      "openai": 4,
      "ollama": 1,
      "notes": "OpenAI returned NIFTY option chain context with PCR/max pain. Ollama used wrong/ambiguous EOD stock-ID option data and failed NIFTY context."
    },
    "multi_turn_context": {
      "openai": 1,
      "ollama": 1,
      "notes": "OpenAI failed to carry WELCORP into the follow-up and compared TALBROAUTO vs NIVABUPA. Ollama failed worse, fabricated a pharmaceutical comparison and omitted WELCORP."
    },
    "report_generation": {
      "openai": 5,
      "ollama": 5,
      "notes": "Reports were generated directly from DB snapshots with no LLM dependency. Both succeeded for stage2 and sector-rotation report commands."
    }
  }
}
```

## Raw Output Location

- JSON: `/Users/pgorai/Documents/Projects/Unified-NSE-Analysis/reports/model_benchmarks/agent_model_benchmark_20260512_032630.json`
