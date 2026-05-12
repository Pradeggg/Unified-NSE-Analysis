# Agent Adda Model Benchmark Report

Generated: `2026-05-12T10:58:54`

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
| openai | 30 | 0 | 9.94s | 2.27 | 276.0 | 23 | 11 | 19 | 11 |
| ollama | 27 | 3 | 17.645s | 1.93 | 205.0 | 19 | 9 | 10 | 17 |

## Case Results

| Case | Category | OpenAI Status / Tools / Factual / Time | Ollama Status / Tools / Factual / Time |
|---|---|---|---|
| `complex_stock_sherlock_reliance` | complex_ric_stock | ok / 6 / pass / 22.739s | ok / 0 / fail / 9.18s |
| `complex_peer_battle_retail` | complex_peer_battle | ok / 1 / pass / 0.438s | ok / 1 / pass / 0.591s |
| `complex_breakout_hunter` | complex_screener_to_scan | ok / 1 / fail / 102.151s | ok / 1 / fail / 104.94s |
| `complex_sector_xray_it` | complex_sector | ok / 2 / fail / 0.075s | ok / 2 / fail / 0.127s |
| `complex_index_pulse_banknifty` | complex_index | ok / 4 / fail / 0.116s | ok / 4 / fail / 0.165s |
| `complex_earnings_playbook_tcs` | complex_earnings | ok / 4 / pass / 0.057s | ok / 4 / pass / 0.069s |
| `complex_risk_radar` | complex_macro_risk | ok / 3 / fail / 0.097s | ok / 3 / fail / 0.092s |
| `complex_morning_intel` | complex_morning | ok / 3 / pass / 0.096s | ok / 3 / pass / 0.085s |
| `complex_company_xray_dmart` | complex_company_xray | ok / 0 / pass / 5.862s | error / 0 / fail / 60.01s |
| `complex_kb_policy_impact_banks` | complex_kb_policy | ok / 2 / fail / 0.076s | ok / 2 / fail / 0.092s |
| `complex_concall_management_infy` | complex_concall | ok / 4 / fail / 0.047s | ok / 4 / fail / 0.053s |
| `complex_deep_search_welcorp` | complex_deep_search | ok / 5 / pass / 6.315s | ok / 5 / pass / 2.261s |
| `complex_forensic_strength_pack` | complex_forensic | ok / 1 / pass / 0.481s | ok / 1 / pass / 0.548s |
| `complex_intraday_supertrend_midcap` | complex_intraday_scan | ok / 1 / pass / 21.03s | ok / 1 / pass / 22.929s |
| `complex_options_strategy_nifty` | complex_options | ok / 3 / pass / 1.668s | ok / 3 / pass / 0.361s |
| `complex_backtest_strategy_design` | complex_backtest_design | ok / 4 / fail / 3.243s | ok / 4 / fail / 1.387s |
| `complex_report_generation_request` | complex_report_generation | ok / 0 / pass / 12.056s | ok / 0 / fail / 50.024s |
| `complex_code_assimilation_reports_py` | complex_code_assimilation | ok / 0 / pass / 10.31s | error / 0 / fail / 60.016s |
| `complex_code_assimilation_enhanced_report` | complex_code_assimilation | ok / 0 / pass / 13.953s | error / 0 / fail / 60.014s |
| `complex_market_education_to_stock` | complex_education_application | ok / 1 / fail / 0.716s | ok / 1 / fail / 0.683s |
| `complex_portfolio_risk_assessment` | complex_portfolio | ok / 1 / pass / 3.554s | ok / 1 / pass / 0.91s |
| `complex_global_to_sector_rotation` | complex_global_sector | ok / 1 / fail / 0.013s | ok / 1 / fail / 0.007s |
| `complex_navabupa_symbol_guardrail` | complex_symbol_guardrail | ok / 1 / pass / 9.603s | ok / 0 / pass / 34.795s |
| `complex_multiturn_setup_1` | complex_multi_turn | ok / 4 / pass / 39.016s | ok / 1 / fail / 21.994s |
| `complex_multiturn_followup_2` | complex_multi_turn | ok / 1 / pass / 0.031s | ok / 1 / fail / 1.525s |
| `complex_multi_tool_failure_handling` | complex_failure_handling | ok / 5 / pass / 16.965s | ok / 0 / fail / 8.994s |
| `complex_screen_to_report` | complex_screen_to_report | ok / 1 / pass / 12.419s | ok / 1 / fail / 47.934s |
| `complex_scan_to_watchlist` | complex_scan_to_watchlist | ok / 1 / pass / 12.804s | ok / 0 / pass / 37.753s |
| `complex_agent_quality_audit` | complex_meta_audit | ok / 4 / fail / 2.224s | ok / 4 / fail / 1.755s |
| `complex_end_to_end_trade_research` | complex_end_to_end | ok / 4 / fail / 0.052s | ok / 4 / fail / 0.049s |

## Factual Check Failures

### openai

- `complex_breakout_hunter`: `{"missing_symbols": [], "missing_required_tools": ["run_screener_query"], "missing_required_terms": ["Stage", "missing"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_sector_xray_it`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["sector"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_index_pulse_banknifty`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["freshness"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_risk_radar`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["risk"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_kb_policy_impact_banks`: `{"missing_symbols": ["HDFCBANK", "SBIN"], "missing_required_tools": [], "missing_required_terms": ["RBI", "Budget"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_concall_management_infy`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["concall"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_backtest_strategy_design`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["backtest", "PostgreSQL"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_market_education_to_stock`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["missing"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_global_to_sector_rotation`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["confidence"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_agent_quality_audit`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["missing"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_end_to_end_trade_research`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["risk"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`

### ollama

- `complex_stock_sherlock_reliance`: `{"missing_symbols": [], "missing_required_tools": ["resolve_symbol", "get_technical_setup", "get_sector_context"], "missing_required_terms": ["evidence"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_breakout_hunter`: `{"missing_symbols": [], "missing_required_tools": ["run_screener_query"], "missing_required_terms": ["Stage", "missing"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_sector_xray_it`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["sector"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_index_pulse_banknifty`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["freshness"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_risk_radar`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["risk"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_company_xray_dmart`: `{"missing_symbols": ["DMART"], "missing_required_tools": [], "missing_required_terms": ["business model", "evidence"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": "ReadTimeout: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=60)"}`
- `complex_kb_policy_impact_banks`: `{"missing_symbols": ["HDFCBANK", "SBIN"], "missing_required_tools": [], "missing_required_terms": ["RBI", "Budget"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_concall_management_infy`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["concall"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_backtest_strategy_design`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["backtest", "PostgreSQL"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_report_generation_request`: `{"missing_symbols": ["HDFCBANK"], "missing_required_tools": [], "missing_required_terms": ["report"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_code_assimilation_reports_py`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["reports.py", "test"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": "ReadTimeout: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=60)"}`
- `complex_code_assimilation_enhanced_report`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["DB", "report"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": "ReadTimeout: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=60)"}`
- `complex_market_education_to_stock`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["missing"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_global_to_sector_rotation`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["confidence"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_multiturn_setup_1`: `{"missing_symbols": ["WELCORP"], "missing_required_tools": [], "missing_required_terms": ["WELCORP"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_multiturn_followup_2`: `{"missing_symbols": ["WELCORP"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_multi_tool_failure_handling`: `{"missing_symbols": ["APOLLOPIPE"], "missing_required_tools": [], "missing_required_terms": ["missing", "evidence"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_screen_to_report`: `{"missing_symbols": [], "missing_required_tools": ["run_screener_query"], "missing_required_terms": ["Markdown"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_agent_quality_audit`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["missing"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_end_to_end_trade_research`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["risk"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`

## Report Generation

- Stage 2 Markdown report generated in `0.009s` at `/Users/pgorai/Documents/Projects/Unified-NSE-Analysis/reports/generated/NSE_stage2_20260512_111242.md` with `20131` characters.

## Code Assimilation Checks

| File | Exists | Chars | Functions | Classes | Mentions Report | Mentions OpenAI |
|---|---:|---:|---:|---:|---:|---:|
| `/Users/pgorai/Documents/Projects/Unified-NSE-Analysis/terminal/reports.py` | True | 105612 | 20 | 0 | True | False |
| `/Users/pgorai/Documents/Projects/Unified-NSE-Analysis/reports/enhanced_comprehensive_analysis.py` | True | 28433 | 10 | 0 | True | False |
| `/Users/pgorai/Documents/Projects/Unified-NSE-Analysis/company_intelligence_search.py` | True | 5338 | 4 | 0 | True | False |

## GPT-5.5 Evaluation

- Evaluator model: `gpt-5.5`
- Overall winner: `OpenAI gpt-4o`

### Executive Summary

```json
{
  "winner_rationale": "OpenAI gpt-4o is the stronger backend for Agent Adda market-research workflows. It used the intended tool stack more often, preserved multi-turn context better, produced fuller research/report-style outputs, and handled symbol guardrails and missing evidence more reliably. It still has serious routing and factual-discipline issues, especially when generic words are misread as symbols and when deep report/code prompts are answered generically.",
  "ollama_summary": "Ollama granite4:latest performed acceptably only when the application router forced a deterministic tool/template path. On LLM-driven cases it often failed to call tools, timed out, emitted raw JSON-like tool-call text instead of executing tools, fabricated or estimated market setups, lost context, selected wrong tools, and sometimes returned only boilerplate disclaimers.",
  "high_level_result": "Use OpenAI as the default backend for complex market research and report planning. Restrict Ollama to simple, already-routed, low-latency template cases unless additional guardrails, function-calling enforcement, timeout handling, and factual validation are added.",
  "shared_system_issue": "Several failures appear caused by upstream intent routing rather than only model quality: examples include treating 'EOD', 'Audit', 'PE', 'ROE', and 'ROCE' as stock symbols, and generic market overview templates being used for sector, policy, and risk questions."
}
```

### Strengths

```json
{
  "openai_gpt_4o": [
    "Best overall tool orchestration in complex LLM-driven stock research, especially RELIANCE Stock Sherlock and WELCORP multi-step setup.",
    "Generally better symbol guardrails; NAVABUPA was not substituted after failed resolution.",
    "Better preservation of multi-turn context; retained WELCORP for the JINDALSAW follow-up.",
    "More complete report-generation and code-assimilation prose than Ollama, even when generic.",
    "Usually includes disclaimer, mode, market clock, and often a source trail.",
    "More consistent missing-evidence disclosure in stock briefs, portfolio review, forensic validation, and failure cases."
  ],
  "ollama_granite4_latest": [
    "Performs adequately when the application intent router bypasses free-form reasoning and invokes deterministic tools/templates, such as compare_stocks, options overview, portfolio review, and some stock briefs.",
    "Can preserve requested symbols in simple, routed comparison cases.",
    "Fast in some purely routed market overview and options cases.",
    "Sometimes uses safe no-investment-advice boilerplate and market clock metadata consistently via application wrapper."
  ]
}
```

### Weaknesses

```json
{
  "openai_gpt_4o": [
    "Still misrouted several non-symbol concepts as tickers, including EOD, Audit, PE, ROE, and ROCE.",
    "Several complex prompts were answered through generic market overview templates rather than the requested sector, policy, risk, or educational reasoning.",
    "Deep-search and failure-handling outputs lacked sufficiently auditable source trails and may contain weak or mismatched URL claims.",
    "Report/code-assimilation answers were plausible but not clearly grounded in actual repository code; they made assumptions about libraries and workflow internals.",
    "Some required terms and user constraints were missed, such as explicit freshness labels, risk separation, missing-data handling, and Stage 2 screen usage.",
    "Some answers were too thin for the requested scope, especially earnings, concall, end-to-end trade research, and breakout-hunter workflows."
  ],
  "ollama_granite4_latest": [
    "Frequent tool-discipline failures on LLM-driven cases: no tools called, raw JSON tool-call text emitted, irrelevant tools selected, or required tools omitted.",
    "Multiple timeouts on company X-ray and code/report assimilation cases.",
    "Severe context loss in multi-turn workflow; WELCORP was lost and replaced with PE.",
    "Fabricated or unsupported market estimates in intraday watchlist and scenario/report cases.",
    "Returned empty or near-empty boilerplate for report-generation and APOLLOPIPE failure-handling cases.",
    "Poor evidence transparency in free-form outputs; often no source trail despite claiming tool-derived facts.",
    "Wrong tool choice in screen-to-report case, using scenario analysis instead of Stage 2 screener.",
    "Weak instruction following for missing-evidence matrices, URL-backed research, policy reasoning, and report planning."
  ]
}
```

### Tool Call Findings

```json
{
  "openai_gpt_4o": {
    "score": 3,
    "findings": [
      "Strongest example: RELIANCE Stock Sherlock used resolve_symbol, get_live_quote, get_technical_setup, get_sector_context, search_latest_catalysts, and run_forensic_analysis.",
      "Good multi-tool failure attempt for APOLLOPIPE: broker research, concall transcripts, NSE announcements, intraday setup, and forensic analysis were invoked, with intraday table error captured.",
      "Good routed cases: compare_stocks, validate_strength_watchlist, scan_intraday_market, options-chain tools, portfolio narratives, and screener query generally executed.",
      "Major failures: backtest design and self-audit were routed as stock briefs for EOD/AUDIT; education prompt treated PE/ROE/ROCE as symbols; several sector/policy cases used only generic market overview tools.",
      "Some LLM-driven report and company X-ray cases used no tools where live/DB evidence would have improved grounding."
    ]
  },
  "ollama_granite4_latest": {
    "score": 2,
    "findings": [
      "Works when the application router already selected a deterministic tool path; outputs often mirror OpenAI on those cases.",
      "Failed RELIANCE Stock Sherlock by outputting a JSON get_live_quote call as text with zero recorded tool calls.",
      "Failed multi-turn WELCORP setup by calling irrelevant get_watchlist_alerts, producing a missing-argument error, and not recovering.",
      "Failed screen-to-report by selecting run_scenario_analysis instead of run_screener_query.",
      "Several free-form cases had zero tools despite requiring current market data or source checks.",
      "Timeouts caused no tool trace for multiple report/code assimilation tasks."
    ]
  }
}
```

### Context Findings

```json
{
  "openai_gpt_4o": {
    "score": 4,
    "findings": [
      "Retained WELCORP from the setup turn into the comparison follow-up.",
      "Maintained symbol guardrails in NAVABUPA and did not substitute prohibited names.",
      "Generally preserved requested symbol lists in portfolio and peer comparison cases.",
      "Context quality degraded when generic concepts were routed as symbols, indicating a classifier/semantic parsing gap rather than only memory failure."
    ]
  },
  "ollama_granite4_latest": {
    "score": 1,
    "findings": [
      "Lost prior-company context in the multi-turn follow-up and compared PE with JINDALSAW instead of WELCORP.",
      "Did not recover from tool error in the initial WELCORP setup.",
      "Misinterpreted educational terms as securities in the same way as OpenAI, but with weaker recovery.",
      "Claimed tool-like symbol-resolution results in NAVABUPA despite no recorded tool call, weakening context and evidence integrity."
    ]
  }
}
```

### Report Generation Findings

```json
{
  "openai_gpt_4o": {
    "score": 4,
    "findings": [
      "Produced a usable HDFCBANK research-report plan with sections, sources, formats, and source-trail intent.",
      "Produced plausible conceptual guidance for Markdown/HTML/PDF reporting and DB-backed comprehensive analysis.",
      "Screen-to-report generated a structured Stage 2 Markdown-style report after using run_screener_query.",
      "Weakness: code-assimilation answers were not proven to inspect actual terminal/reports.py or enhanced module implementation and lacked source trail in some code/report cases."
    ]
  },
  "ollama_granite4_latest": {
    "score": 1,
    "findings": [
      "HDFCBANK report-generation case returned only boilerplate/disclaimer and failed factual checks.",
      "Both code-assimilation cases timed out.",
      "Screen-to-report used the wrong tool and produced irrelevant/nonsensical scenario analysis instead of a Stage 2 report outline.",
      "Report outputs lacked reliable source trails and were often unusable."
    ]
  },
  "non_llm_report_generation": {
    "score": 5,
    "findings": [
      "The separate report_generation result succeeded directly from DB snapshot with no LLM required.",
      "Generated Markdown report path: /Users/pgorai/Documents/Projects/Unified-NSE-Analysis/reports/generated/NSE_stage2_20260512_111242.md.",
      "This deterministic path should be preferred for production Stage 2 reports because it avoids LLM hallucination and provides DB-backed reproducibility."
    ]
  }
}
```

### Factual Accuracy Findings

```json
{
  "openai_gpt_4o": {
    "score": 3,
    "findings": [
      "Factual checks passed on many symbol-specific and routed tool cases, including RELIANCE, TCS brief, WELCORP deep-search, forensic pack, options, portfolio, NAVABUPA, and multi-turn WELCORP.",
      "Failed factual checks on breakout hunter, sector IT, Bank Nifty freshness labeling, risk radar, policy-impact banks, concall INFY, backtest design, education-to-stock, global sector confidence, self-audit, and THERMAX end-to-end.",
      "Wrong-symbol behavior was a major issue in EOD/AUDIT/PE/ROE/ROCE cases.",
      "Potential unsupported URL/source claims remain a concern in APOLLOPIPE and deep-search style outputs unless source payloads are explicitly cited."
    ]
  },
  "ollama_granite4_latest": {
    "score": 2,
    "findings": [
      "Factual checks passed mostly on deterministic routed cases, not free-form model reasoning.",
      "Failed factual checks on RELIANCE Stock Sherlock, company X-ray timeout, policy banks, report generation, code assimilation timeouts, multi-turn WELCORP, APOLLOPIPE, screen-to-report, and several market reasoning cases.",
      "Fabricated estimated setups and broad target ranges in intraday watchlist without recorded tool evidence.",
      "Claimed unavailable-symbol resolution in NAVABUPA without recorded resolve_symbol call."
    ]
  }
}
```

### Command Coverage Findings

```json
{
  "openai_gpt_4o": {
    "score": 3,
    "findings": [
      "Covered most requested commands in RELIANCE, portfolio risk, multi-turn WELCORP, intraday symbol scan, options strategy, and report plan.",
      "Partial command coverage in earnings, concall, sector X-ray, risk radar, global sector rotation, and end-to-end THERMAX; tool data was present but requested analysis dimensions were incomplete.",
      "Failed command coverage in backtest design, education application, self-audit, and some policy reasoning due to intent misclassification.",
      "Missing explicit source trails in several LLM-driven cases reduced command completeness."
    ]
  },
  "ollama_granite4_latest": {
    "score": 2,
    "findings": [
      "Good coverage only in simple routed templates such as peer comparison, options overview, portfolio review, and forensic validation.",
      "Poor coverage in LLM-driven commands requiring orchestration, report writing, missing-evidence matrices, or context carryover.",
      "Timeouts and boilerplate-only responses caused total command failure in several report/code/company cases.",
      "Wrong-symbol and wrong-tool behavior caused severe misses in multi-turn, screen-to-report, and education cases."
    ]
  }
}
```

### Recommended Backend Policy

```json
{
  "default_backend": "OpenAI gpt-4o",
  "policy": [
    {
      "use_case": "Complex stock research, multi-tool workflows, symbol guardrails, missing-evidence analysis, multi-turn investigations, report planning, and code/report explanation",
      "backend": "OpenAI gpt-4o",
      "condition": "Use with mandatory tool-plan validation and post-answer factual checks."
    },
    {
      "use_case": "Simple deterministic routed commands with fixed tools, such as compare_stocks, options overview, portfolio review, and prebuilt market templates",
      "backend": "Either backend, OpenAI preferred for reliability",
      "condition": "Ollama may be allowed only if the router has already selected the exact tool and response template."
    },
    {
      "use_case": "Production Stage 2 reports and other reproducible DB-backed reports",
      "backend": "No LLM / deterministic report generator",
      "condition": "Use direct DB snapshot report_generation path whenever possible."
    },
    {
      "use_case": "Deep search, broker/concall/NSE announcement synthesis, source URL claims",
      "backend": "OpenAI gpt-4o only",
      "condition": "Require source payload IDs/URLs from tools; block unsupported URL generation."
    },
    {
      "use_case": "LLM-driven report/code assimilation or long free-form reasoning",
      "backend": "Do not use Ollama granite4:latest in current form",
      "condition": "Observed timeouts and incomplete outputs make it unsuitable without remediation."
    }
  ],
  "fallback_rules": [
    "If OpenAI produces wrong-symbol routing or missing required tools, retry with an explicit non-symbol intent and required tool list.",
    "If Ollama emits raw JSON-like tool calls, intercept and execute only if schema-valid; otherwise fail safely.",
    "If any backend lacks source trail for market data, mark the answer incomplete rather than presenting conclusions.",
    "For unavailable symbols, allow only resolve_symbol output and a no-substitution explanation."
  ]
}
```

### Remediation Backlog

- `{"priority": "P0", "item": "Fix intent classification to distinguish educational terms, workflow nouns, and code/report concepts from ticker symbols.", "evidence": "EOD, Audit, PE, ROE, and ROCE were treated as symbols."}`
- `{"priority": "P0", "item": "Add required-tool validation before answer generation.", "evidence": "Breakout hunter missed run_screener_query; screen-to-report in Ollama used run_scenario_analysis; RELIANCE Ollama made no recorded tool calls."}`
- `{"priority": "P0", "item": "Enforce structured function calling for Ollama or disable LLM-driven tool orchestration on Ollama.", "evidence": "Ollama emitted raw JSON tool-call text and frequently made zero calls on tool-required tasks."}`
- `{"priority": "P0", "item": "Implement post-answer factual check gating and automatic retry when required symbols, terms, tools, or freshness labels are missing.", "evidence": "Multiple failed checks for HDFCBANK/SBIN, freshness, risk, confidence, backtest, PostgreSQL, and missing-data handling."}`
- `{"priority": "P1", "item": "Require source-trail objects in all LLM-driven outputs, not only routed templates.", "evidence": "OpenAI and Ollama both lacked source trails in several LLM-driven cases despite market claims."}`
- `{"priority": "P1", "item": "Add no-fabricated-URL guardrails for broker, concall, announcement, and news workflows.", "evidence": "APOLLOPIPE and deep-search style outputs need auditable source payloads and URL provenance."}`
- `{"priority": "P1", "item": "Improve sector and macro-policy routing.", "evidence": "IT sector X-ray and RBI/Budget impact on HDFCBANK/SBIN fell back to generic market overview."}`
- `{"priority": "P1", "item": "Add explicit freshness-label templates for live, intraday, EOD, stale, and fallback data.", "evidence": "Bank Nifty and options-style prompts required freshness labels; some outputs had market clock but missed explicit freshness semantics."}`
- `{"priority": "P1", "item": "Strengthen missing-evidence matrices.", "evidence": "Breakout hunter, APOLLOPIPE Ollama, and education cases failed to enumerate unavailable data cleanly."}`
- `{"priority": "P2", "item": "Add multi-turn memory assertions for base company, symbol list, and forbidden substitutions.", "evidence": "Ollama lost WELCORP and substituted PE in the follow-up."}`
- `{"priority": "P2", "item": "Create report/code assimilation fixtures with actual repository snippets or schemas.", "evidence": "OpenAI gave generic terminal/reports.py assumptions; Ollama timed out."}`
- `{"priority": "P2", "item": "Route deterministic DB-backed report generation outside LLM path by default.", "evidence": "Standalone report_generation succeeded instantly and reproducibly without LLM."}`
- `{"priority": "P2", "item": "Add timeout fallback for Ollama with concise safe-fail response and retry to OpenAI.", "evidence": "Ollama timed out on DMART X-ray and both code/report assimilation cases."}`

### Case Scores

```json
{
  "openai_gpt_4o": {
    "tool_discipline": 3,
    "evidence_transparency": 4,
    "instruction_following": 3,
    "market_reasoning": 3,
    "risk_handling": 4,
    "context_management": 4,
    "factual_data_checks": 3,
    "report_generation": 4,
    "output_usability": 4,
    "overall": 4
  },
  "ollama_granite4_latest": {
    "tool_discipline": 2,
    "evidence_transparency": 2,
    "instruction_following": 2,
    "market_reasoning": 2,
    "risk_handling": 2,
    "context_management": 1,
    "factual_data_checks": 2,
    "report_generation": 1,
    "output_usability": 2,
    "overall": 2
  },
  "notable_case_results": [
    {
      "case_id": "complex_stock_sherlock_reliance",
      "winner": "OpenAI gpt-4o",
      "openai_score": 5,
      "ollama_score": 1,
      "reason": "OpenAI called six relevant tools and produced a structured thesis. Ollama emitted a raw get_live_quote JSON block, made no recorded tool call, and missed required identity, technical, sector, forensic, and evidence-gap coverage."
    },
    {
      "case_id": "complex_peer_battle_retail",
      "winner": "Tie",
      "openai_score": 4,
      "ollama_score": 4,
      "reason": "Both used compare_stocks and preserved the requested symbols, but output was thin on business quality, catalysts, and missing evidence."
    },
    {
      "case_id": "complex_breakout_hunter",
      "winner": "Tie - weak",
      "openai_score": 2,
      "ollama_score": 2,
      "reason": "Both used only intraday screener, missed the Stage 2 screener requirement, and returned no shortlist or missing-data discussion."
    },
    {
      "case_id": "complex_sector_xray_it",
      "winner": "Tie - weak",
      "openai_score": 2,
      "ollama_score": 2,
      "reason": "Both fell back to generic market overview/breadth instead of a true IT sector X-ray with leaders, laggards, RS vs Nifty, and rotation conclusion."
    },
    {
      "case_id": "complex_index_pulse_banknifty",
      "winner": "Tie",
      "openai_score": 3,
      "ollama_score": 3,
      "reason": "Both used several relevant market tools but missed explicit freshness labeling and detailed Bank Nifty technical/intraday levels."
    },
    {
      "case_id": "complex_earnings_playbook_tcs",
      "winner": "Tie - moderate",
      "openai_score": 3,
      "ollama_score": 3,
      "reason": "Both produced a stock brief with technical and sector evidence, but latest results, peer comparison, and management commentary were under-covered."
    },
    {
      "case_id": "complex_company_xray_dmart",
      "winner": "OpenAI gpt-4o",
      "openai_score": 3,
      "ollama_score": 1,
      "reason": "OpenAI produced a useful but largely generic no-tool company analysis. Ollama timed out."
    },
    {
      "case_id": "complex_kb_policy_impact_banks",
      "winner": "Tie - poor",
      "openai_score": 1,
      "ollama_score": 1,
      "reason": "Both ignored HDFCBANK/SBIN-specific policy reasoning and returned generic market overview data."
    },
    {
      "case_id": "complex_deep_search_welcorp",
      "winner": "Tie - moderate",
      "openai_score": 3,
      "ollama_score": 3,
      "reason": "Both used stock and catalyst tools and included missing evidence, but the answer remained a market brief rather than a deep URL-backed search across all requested source categories."
    },
    {
      "case_id": "complex_backtest_strategy_design",
      "winner": "Tie - failed",
      "openai_score": 1,
      "ollama_score": 1,
      "reason": "Both treated EOD as a symbol, called stock-brief tools, and failed to design the backtest or PostgreSQL persistence plan."
    },
    {
      "case_id": "complex_report_generation_request",
      "winner": "OpenAI gpt-4o",
      "openai_score": 4,
      "ollama_score": 1,
      "reason": "OpenAI generated a usable HDFCBANK report plan. Ollama returned only boilerplate/disclaimer and missed the symbol and report requirements."
    },
    {
      "case_id": "complex_code_assimilation_reports_py",
      "winner": "OpenAI gpt-4o",
      "openai_score": 3,
      "ollama_score": 1,
      "reason": "OpenAI gave a plausible conceptual workflow but likely generic code assumptions. Ollama timed out."
    },
    {
      "case_id": "complex_code_assimilation_enhanced_report",
      "winner": "OpenAI gpt-4o",
      "openai_score": 3,
      "ollama_score": 1,
      "reason": "OpenAI produced a generic but usable DB-backed report assimilation outline. Ollama timed out."
    },
    {
      "case_id": "complex_market_education_to_stock",
      "winner": "Tie - failed routing",
      "openai_score": 1,
      "ollama_score": 1,
      "reason": "Both treated PE, ROE, and ROCE as symbols and failed the educational explanation plus missing-data handling requirement."
    },
    {
      "case_id": "complex_navabupa_symbol_guardrail",
      "winner": "OpenAI gpt-4o",
      "openai_score": 4,
      "ollama_score": 3,
      "reason": "OpenAI actually called resolve_symbol and did not substitute. Ollama also avoided substitution but claimed a tool result despite zero recorded tool calls."
    },
    {
      "case_id": "complex_multiturn_setup_1",
      "winner": "OpenAI gpt-4o",
      "openai_score": 4,
      "ollama_score": 1,
      "reason": "OpenAI established WELCORP identity, technical state, sector context, and gaps. Ollama called an irrelevant watchlist-alert tool, hit an error, and did not answer."
    },
    {
      "case_id": "complex_multiturn_followup_2",
      "winner": "OpenAI gpt-4o",
      "openai_score": 4,
      "ollama_score": 1,
      "reason": "OpenAI retained WELCORP and compared it with JINDALSAW. Ollama lost context and compared PE with JINDALSAW."
    },
    {
      "case_id": "complex_multi_tool_failure_handling",
      "winner": "OpenAI gpt-4o",
      "openai_score": 3,
      "ollama_score": 1,
      "reason": "OpenAI called the requested broker, concall, NSE announcement, intraday, and forensic tools and exposed at least one tool error, though source-trail and URL fidelity remain questionable. Ollama returned only boilerplate."
    },
    {
      "case_id": "complex_screen_to_report",
      "winner": "OpenAI gpt-4o",
      "openai_score": 4,
      "ollama_score": 1,
      "reason": "OpenAI used run_screener_query and produced a Stage 2 Markdown-style report. Ollama used the wrong scenario-analysis tool and produced nonsensical scenario math."
    },
    {
      "case_id": "complex_scan_to_watchlist",
      "winner": "OpenAI gpt-4o",
      "openai_score": 4,
      "ollama_score": 1,
      "reason": "OpenAI used scan_symbols_intraday and produced concrete entries, targets, and invalidations. Ollama fabricated broad estimates without recorded tools."
    }
  ]
}
```

## Raw Output Location

- JSON: `/Users/pgorai/Documents/Projects/Unified-NSE-Analysis/reports/model_benchmarks/agent_model_benchmark_20260512_105854.json`
