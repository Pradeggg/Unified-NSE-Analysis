# Agent Adda Model Benchmark Report

Generated: `2026-05-12T10:24:08`

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
| openai | 30 | 0 | 11.92s | 2.6 | 287.9 | 23 | 12 | 16 | 14 |
| ollama | 24 | 6 | 22.481s | 2.29 | 203.9 | 16 | 11 | 5 | 19 |

## Case Results

| Case | Category | OpenAI Status / Tools / Factual / Time | Ollama Status / Tools / Factual / Time |
|---|---|---|---|
| `complex_stock_sherlock_reliance` | complex_ric_stock | ok / 6 / pass / 18.259s | error / 0 / fail / 60.008s |
| `complex_peer_battle_retail` | complex_peer_battle | ok / 5 / fail / 6.139s | ok / 5 / fail / 3.804s |
| `complex_breakout_hunter` | complex_screener_to_scan | ok / 1 / fail / 153.071s | ok / 1 / fail / 113.139s |
| `complex_sector_xray_it` | complex_sector | ok / 2 / pass / 0.079s | ok / 2 / fail / 0.064s |
| `complex_index_pulse_banknifty` | complex_index | ok / 4 / fail / 0.119s | ok / 4 / fail / 0.105s |
| `complex_earnings_playbook_tcs` | complex_earnings | ok / 4 / fail / 0.072s | ok / 4 / fail / 0.066s |
| `complex_risk_radar` | complex_macro_risk | ok / 3 / fail / 0.087s | ok / 3 / fail / 0.084s |
| `complex_morning_intel` | complex_morning | ok / 3 / pass / 0.091s | ok / 3 / pass / 0.097s |
| `complex_company_xray_dmart` | complex_company_xray | ok / 3 / pass / 14.485s | error / 0 / fail / 60.009s |
| `complex_kb_policy_impact_banks` | complex_kb_policy | ok / 2 / fail / 0.489s | ok / 2 / fail / 0.094s |
| `complex_concall_management_infy` | complex_concall | ok / 4 / fail / 1.025s | ok / 4 / fail / 0.077s |
| `complex_deep_search_welcorp` | complex_deep_search | ok / 5 / fail / 3.171s | ok / 5 / fail / 1.735s |
| `complex_forensic_strength_pack` | complex_forensic | ok / 1 / pass / 0.475s | ok / 1 / pass / 0.584s |
| `complex_intraday_supertrend_midcap` | complex_intraday_scan | ok / 1 / pass / 21.622s | ok / 1 / pass / 21.411s |
| `complex_options_strategy_nifty` | complex_options | ok / 3 / pass / 10.914s | ok / 1 / fail / 25.115s |
| `complex_backtest_strategy_design` | complex_backtest_design | ok / 4 / fail / 0.075s | ok / 4 / fail / 0.067s |
| `complex_report_generation_request` | complex_report_generation | ok / 0 / pass / 4.918s | error / 0 / fail / 60.006s |
| `complex_code_assimilation_reports_py` | complex_code_assimilation | ok / 0 / pass / 7.681s | error / 0 / fail / 60.011s |
| `complex_code_assimilation_enhanced_report` | complex_code_assimilation | ok / 0 / pass / 8.883s | error / 0 / fail / 60.012s |
| `complex_market_education_to_stock` | complex_education_application | ok / 4 / fail / 7.609s | ok / 4 / fail / 1.959s |
| `complex_portfolio_risk_assessment` | complex_portfolio | ok / 1 / pass / 16.347s | ok / 1 / fail / 17.04s |
| `complex_global_to_sector_rotation` | complex_global_sector | ok / 1 / fail / 0.009s | ok / 1 / fail / 0.009s |
| `complex_navabupa_symbol_guardrail` | complex_symbol_guardrail | ok / 1 / fail / 7.421s | ok / 0 / fail / 19.608s |
| `complex_multiturn_setup_1` | complex_multi_turn | ok / 3 / pass / 10.336s | ok / 0 / fail / 8.802s |
| `complex_multiturn_followup_2` | complex_multi_turn | ok / 1 / pass / 15.084s | ok / 0 / fail / 11.754s |
| `complex_multi_tool_failure_handling` | complex_failure_handling | ok / 6 / pass / 16.317s | ok / 0 / pass / 55.779s |
| `complex_screen_to_report` | complex_screen_to_report | ok / 1 / fail / 17.584s | error / 0 / fail / 60.011s |
| `complex_scan_to_watchlist` | complex_scan_to_watchlist | ok / 1 / pass / 11.946s | ok / 1 / fail / 30.832s |
| `complex_agent_quality_audit` | complex_meta_audit | ok / 4 / pass / 0.297s | ok / 4 / pass / 0.074s |
| `complex_end_to_end_trade_research` | complex_end_to_end | ok / 4 / fail / 2.983s | ok / 4 / fail / 2.076s |

## Factual Check Failures

### openai

- `complex_peer_battle_retail`: `{"missing_symbols": ["DMART", "TRENT", "VBL"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_breakout_hunter`: `{"missing_symbols": [], "missing_required_tools": ["run_screener_query"], "missing_required_terms": ["Stage", "missing"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_index_pulse_banknifty`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["freshness"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_earnings_playbook_tcs`: `{"missing_symbols": ["TCS"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_risk_radar`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["risk"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_kb_policy_impact_banks`: `{"missing_symbols": ["HDFCBANK", "SBIN"], "missing_required_tools": [], "missing_required_terms": ["RBI", "Budget"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_concall_management_infy`: `{"missing_symbols": ["INFY"], "missing_required_tools": [], "missing_required_terms": ["concall"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_deep_search_welcorp`: `{"missing_symbols": ["WELCORP"], "missing_required_tools": [], "missing_required_terms": ["WELCORP"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_backtest_strategy_design`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["backtest", "PostgreSQL"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_market_education_to_stock`: `{"missing_symbols": ["TCS", "INFY"], "missing_required_tools": [], "missing_required_terms": ["ROCE", "missing"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_global_to_sector_rotation`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["confidence"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_navabupa_symbol_guardrail`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": ["NIVABUPA"], "data_freshness_issue": false, "error": null}`
- `complex_screen_to_report`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["Markdown"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_end_to_end_trade_research`: `{"missing_symbols": ["THERMAX"], "missing_required_tools": [], "missing_required_terms": ["THERMAX"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`

### ollama

- `complex_stock_sherlock_reliance`: `{"missing_symbols": ["RELIANCE"], "missing_required_tools": ["resolve_symbol", "get_technical_setup", "get_sector_context"], "missing_required_terms": ["RELIANCE", "evidence"], "forbidden_term_hits": [], "data_freshness_issue": true, "error": "ReadTimeout: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=60)"}`
- `complex_peer_battle_retail`: `{"missing_symbols": ["DMART", "TRENT", "VBL"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_breakout_hunter`: `{"missing_symbols": [], "missing_required_tools": ["run_screener_query"], "missing_required_terms": ["Stage", "missing"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_sector_xray_it`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["sector"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_index_pulse_banknifty`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["freshness"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_earnings_playbook_tcs`: `{"missing_symbols": ["TCS"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_risk_radar`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["risk"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_company_xray_dmart`: `{"missing_symbols": ["DMART"], "missing_required_tools": [], "missing_required_terms": ["business model", "evidence"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": "ReadTimeout: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=60)"}`
- `complex_kb_policy_impact_banks`: `{"missing_symbols": ["HDFCBANK", "SBIN"], "missing_required_tools": [], "missing_required_terms": ["RBI", "Budget"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_concall_management_infy`: `{"missing_symbols": ["INFY"], "missing_required_tools": [], "missing_required_terms": ["concall"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_deep_search_welcorp`: `{"missing_symbols": ["WELCORP"], "missing_required_tools": [], "missing_required_terms": ["WELCORP"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_options_strategy_nifty`: `{"missing_symbols": ["NIFTY"], "missing_required_tools": [], "missing_required_terms": ["PCR", "max pain"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_backtest_strategy_design`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["backtest", "PostgreSQL"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_report_generation_request`: `{"missing_symbols": ["HDFCBANK"], "missing_required_tools": [], "missing_required_terms": ["report", "source"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": "ReadTimeout: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=60)"}`
- `complex_code_assimilation_reports_py`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["reports.py", "test"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": "ReadTimeout: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=60)"}`
- `complex_code_assimilation_enhanced_report`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["DB", "report"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": "ReadTimeout: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=60)"}`
- `complex_market_education_to_stock`: `{"missing_symbols": ["TCS", "INFY"], "missing_required_tools": [], "missing_required_terms": ["ROCE", "missing"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_portfolio_risk_assessment`: `{"missing_symbols": ["RELIANCE", "TCS", "HDFCBANK", "DMART", "WELCORP"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_global_to_sector_rotation`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["confidence"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_navabupa_symbol_guardrail`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": ["NIVABUPA"], "data_freshness_issue": false, "error": null}`
- `complex_multiturn_setup_1`: `{"missing_symbols": ["WELCORP"], "missing_required_tools": [], "missing_required_terms": ["WELCORP"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_multiturn_followup_2`: `{"missing_symbols": ["WELCORP"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_screen_to_report`: `{"missing_symbols": [], "missing_required_tools": ["run_screener_query"], "missing_required_terms": ["Markdown", "risk"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": "ReadTimeout: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=60)"}`
- `complex_scan_to_watchlist`: `{"missing_symbols": ["RELIANCE", "TCS", "INFY", "HDFCBANK", "SBIN"], "missing_required_tools": [], "missing_required_terms": ["invalidation"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `complex_end_to_end_trade_research`: `{"missing_symbols": ["THERMAX"], "missing_required_tools": [], "missing_required_terms": ["THERMAX"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`

## Report Generation

- Stage 2 Markdown report generated in `0.012s` at `/Users/pgorai/Documents/Projects/Unified-NSE-Analysis/reports/generated/NSE_stage2_20260512_104121.md` with `20131` characters.

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
  "openai_score": 3,
  "ollama_score": 2,
  "summary": "OpenAI gpt-4o is the stronger backend for Agent Adda because it completes more complex workflows, uses required tools more consistently, preserves multi-turn context better, and produces more usable research/report-style outputs. However, OpenAI still has major routing and symbol-resolution failures: it often treats common words such as Peer, Teach, End-to-end, or IT as symbols, substitutes wrong securities for TCS, INFY, and WELCORP in several stock-brief paths, and sometimes provides thin generic market summaries where the user asked for specific sector, risk, or policy reasoning. Ollama granite4:latest is materially less reliable: it times out on multiple complex/report/code tasks, emits raw or pseudo tool-call JSON, uses wrong tools, misses required symbols, loses context, and in one APOLLOPIPE case appears to fabricate broker/concall/NSE details without source-backed tool traces. The direct DB report generation path succeeded independently of either LLM and should be preferred for deterministic report outputs."
}
```

### Strengths

```json
{
  "openai": [
    "Completes most long-form and multi-tool LLM-driven workflows without timeout.",
    "Uses relevant tools on strong cases, for example RELIANCE, NIFTY options, APOLLOPIPE multi-source workflow, WELCORP multi-turn setup, and intraday scans.",
    "Generally includes disclaimers, mode labels, market clock, and source-trail sections when templated tools are used.",
    "Better at synthesizing tool results into readable research, portfolio risk, options, and report-plan narratives.",
    "Maintains multi-turn context better, especially WELCORP to JINDALSAW comparison."
  ],
  "ollama": [
    "Can execute simple routed tool templates quickly when intent classification is deterministic, such as market overview, breadth, FII/DII, forensic watchlist, and intraday index scan.",
    "Produces standard disclaimer/clock wrappers in many successful templated paths.",
    "Matches OpenAI on several failures caused by shared upstream routing logic, indicating some issues are not model-only.",
    "Occasionally refuses substitution in spirit, as in NAVABUPA, though it still referenced forbidden alternatives."
  ]
}
```

### Weaknesses

```json
{
  "openai": [
    "Severe symbol-resolution and routing errors remain: Peer to PEER, Teach to TEACH, End-to-end to END-TO-END, TCS to VERANDA, INFY to JBFIND, WELCORP to DEEPINDS in deep-search.",
    "Often relies on generic market overview tooling for sector, policy, risk, or morning-intel queries instead of satisfying all requested subparts.",
    "Evidence gaps are inconsistently indexed; some LLM-driven outputs mention conclusions without a full source trail.",
    "Report and code-assimilation answers are plausible but conceptual, not grounded in actual file inspection unless the code is provided or a tool is used.",
    "NAVABUPA guardrail response still included the forbidden NIVABUPA token and suggested exploratory NIFTY follow-up, weakening strict symbol discipline."
  ],
  "ollama": [
    "Frequent 60-second timeouts on complex research, report generation, and code-assimilation cases.",
    "Weak tool discipline: uses no tools where tools are required, uses wrong tools such as options-chain for stock watchlists, and sometimes emits raw tool JSON instead of final analysis.",
    "High factual-risk behavior, including apparent fabricated APOLLOPIPE broker target/concall/NSE details without supporting tool traces.",
    "Very poor context retention: lost WELCORP and invented TREKKING in the multi-turn follow-up.",
    "Misses requested symbols and required terms more often than OpenAI, especially in portfolio, options, report, and long research cases."
  ]
}
```

### Tool Call Findings

```json
{
  "openai": {
    "score": 3,
    "finding": "Tool use is materially better than Ollama but inconsistent. Strong cases call the intended tools, including resolve_symbol, quote, technical, sector, catalyst, forensic, option-chain/FNO, compare_stocks, and scan tools. Weak cases show bad intent routing and token extraction, causing irrelevant stock_brief workflows on non-symbol words and missed required screeners."
  },
  "ollama": {
    "score": 2,
    "finding": "Tool use is unreliable. Several tasks time out before tool execution. Some successful paths are just shared deterministic templates. Wrong-tool selection appears in options and intraday watchlist cases, and the portfolio case returned a raw get_portfolio_pnl JSON block rather than assimilating results."
  },
  "shared_system_issue": "Many identical wrong-symbol outputs across both backends suggest an upstream intent/entity extraction bug, not only model behavior. The backend should not pass the first capitalized/common word as a ticker without explicit validation against user-requested symbols."
}
```

### Context Findings

```json
{
  "openai": {
    "score": 4,
    "finding": "OpenAI retained prior WELCORP context in the follow-up and used it as the base against JINDALSAW. Context management is still vulnerable when the initial routing extracts the wrong entity."
  },
  "ollama": {
    "score": 1,
    "finding": "Ollama failed the multi-turn chain: the WELCORP setup produced almost no content, and the follow-up claimed the prior company was TREKKING. This is a critical context integrity failure."
  }
}
```

### Report Generation Findings

```json
{
  "openai": {
    "score": 4,
    "finding": "OpenAI produced usable report plans and conceptual Markdown/HTML/PDF workflow descriptions. It did not always use tools, but for planning tasks this was acceptable. Source trails are sometimes described rather than actually backed by tool calls."
  },
  "ollama": {
    "score": 1,
    "finding": "Ollama timed out on the HDFCBANK report-generation request and both code-assimilation/report-generation conceptual tasks. It is not suitable for report planning or code/report assimilation under the observed timeout budget."
  },
  "direct_report_generation": {
    "score": 5,
    "finding": "The separate DB-backed report_generation path succeeded in 0.012 seconds, generated a 20,131-character Markdown Stage 2 report, and explicitly required no LLM. This should be the preferred mechanism for deterministic reports."
  }
}
```

### Factual Accuracy Findings

```json
{
  "openai": {
    "score": 2,
    "finding": "OpenAI is less likely than Ollama to fabricate unsupported details, but it still produces serious factual failures through wrong-symbol substitution and incomplete checks. Cases involving TCS, INFY, WELCORP deep search, PEER, TEACH, and END-TO-END are not usable without validation."
  },
  "ollama": {
    "score": 1,
    "finding": "Ollama combines wrong-symbol failures with timeouts, raw tool artifacts, and apparent hallucinated claims. The APOLLOPIPE answer cites broker targets, BSE filings, and concall details without recorded tool calls, making it high risk."
  },
  "critical_penalties": [
    "Wrong symbols or substitutions for requested equities.",
    "Treating common words as ticker symbols.",
    "Missing source URLs or source trails for news/concall/broker claims.",
    "Missing required freshness labels or evidence-gap matrices.",
    "Unsupported financial facts, broker targets, or transcript details."
  ]
}
```

### Command Coverage Findings

```json
{
  "openai": {
    "score": 3,
    "covered_well": [
      "RELIANCE Stock Sherlock",
      "DMART company X-ray",
      "NIFTY options strategy",
      "forensic strength validation",
      "intraday index scan",
      "portfolio risk assessment",
      "multi-turn WELCORP follow-up",
      "code/report conceptual tasks"
    ],
    "missed_or_partial": [
      "Peer battle DMART/TRENT/VBL",
      "TCS earnings playbook",
      "INFY concall evidence",
      "WELCORP deep search",
      "Stage 2 breakout workflow requiring run_screener_query",
      "policy reasoning for HDFCBANK/SBIN",
      "education application to TCS/INFY",
      "THERMAX end-to-end research"
    ]
  },
  "ollama": {
    "score": 2,
    "covered_well": [
      "simple market overview templates",
      "forensic strength validation",
      "intraday NIFTY MIDCAP 100 scan",
      "global market assessment template"
    ],
    "missed_or_partial": [
      "RELIANCE Stock Sherlock due timeout",
      "DMART company X-ray due timeout",
      "HDFCBANK report plan due timeout",
      "code/report assimilation due timeout",
      "portfolio risk assessment",
      "multi-turn context",
      "options strategy completeness",
      "screen-to-report due timeout",
      "stock-specific TCS/INFY/WELCORP/THERMAX tasks"
    ]
  }
}
```

### Recommended Backend Policy

```json
{
  "default_backend": "OpenAI gpt-4o",
  "policy": [
    "Use OpenAI gpt-4o for complex market research, multi-tool workflows, report planning, code/report assimilation, portfolio risk, options strategy, and multi-turn analysis.",
    "Use deterministic DB/report-generation code paths whenever available; do not involve an LLM for standard Stage 2 or snapshot-based report generation.",
    "Restrict Ollama granite4:latest to simple, single-intent, low-latency templated commands only after adding timeout safeguards and hallucination checks.",
    "Do not allow either backend to answer stock-specific queries unless all requested symbols are explicitly resolved and echoed before downstream tools run.",
    "Require source-trail and missing-evidence sections for all broker, concall, news, forensic, and catalyst claims.",
    "Block final answers when the resolved symbol differs from the requested symbol unless the user explicitly approves the substitution."
  ]
}
```

### Remediation Backlog

- `{"priority": 1, "score": 5, "item": "Fix entity extraction so common words and task labels such as Peer, Teach, End-to-end, IT, and Start are never treated as tickers when explicit requested symbols exist."}`
- `{"priority": 2, "score": 5, "item": "Add a symbol-guardrail validator: compare requested_symbols versus resolved_symbols before every stock tool chain; abort with a clear missing-evidence response on mismatch."}`
- `{"priority": 3, "score": 5, "item": "Enforce no-substitution policy for exact-symbol requests, including NAVABUPA-style cases; avoid even suggesting forbidden substitutes unless quoting the user's prohibition is necessary."}`
- `{"priority": 4, "score": 4, "item": "Add required-tool plans per intent, for example Stage 2 workflows must call run_screener_query before intraday scan; options strategies must call option chain plus PCR/max-pain/IV analytics."}`
- `{"priority": 5, "score": 4, "item": "Implement source-backed claim gating for broker targets, concalls, announcements, and catalysts: every claim must carry a URL/tool result or be marked unavailable."}`
- `{"priority": 6, "score": 4, "item": "Improve missing-evidence matrices with rows for requested data, attempted tool, status, source URL, timestamp, and safe inference boundary."}`
- `{"priority": 7, "score": 4, "item": "Add model timeout policy for Ollama: shorter prompts, staged tool-first execution, streaming heartbeat, and fallback to OpenAI or deterministic reports after timeout."}`
- `{"priority": 8, "score": 3, "item": "Strengthen multi-turn memory by persisting resolved base symbol, company name, evidence gaps, and prior tool outputs; reject follow-up comparisons if base symbol is missing."}`
- `{"priority": 9, "score": 3, "item": "Separate data from inference in macro/risk/sector outputs and require requested terms such as risk, confidence, freshness, RBI, Budget, and Markdown when specified."}`
- `{"priority": 10, "score": 3, "item": "Route report-generation commands to deterministic DB-backed report builders first, with LLM only for optional narrative polishing constrained to supplied data."}`

### Case Scores

```json
{
  "scale": "1=poor, 2=weak, 3=mixed/usable with supervision, 4=good, 5=excellent",
  "openai": {
    "overall": 3,
    "tool_discipline": 3,
    "evidence_transparency": 3,
    "instruction_following": 3,
    "market_reasoning": 3,
    "risk_handling": 3,
    "context_management": 4,
    "factual_data_checks": 2,
    "report_generation": 4,
    "output_usability": 3
  },
  "ollama": {
    "overall": 2,
    "tool_discipline": 2,
    "evidence_transparency": 2,
    "instruction_following": 2,
    "market_reasoning": 2,
    "risk_handling": 2,
    "context_management": 1,
    "factual_data_checks": 1,
    "report_generation": 1,
    "output_usability": 2
  },
  "representative_case_results": {
    "complex_stock_sherlock_reliance": {
      "openai": 4,
      "ollama": 1,
      "finding": "OpenAI completed the full quote/technical/sector/catalyst/forensic workflow; Ollama timed out."
    },
    "complex_peer_battle_retail": {
      "openai": 1,
      "ollama": 1,
      "finding": "Both misrouted the word Peer as symbol PEER and omitted DMART, TRENT, and VBL."
    },
    "complex_earnings_playbook_tcs": {
      "openai": 1,
      "ollama": 1,
      "finding": "Both returned VERANDA instead of TCS, a severe symbol substitution failure."
    },
    "complex_company_xray_dmart": {
      "openai": 4,
      "ollama": 1,
      "finding": "OpenAI produced a usable business/sector X-ray; Ollama timed out."
    },
    "complex_options_strategy_nifty": {
      "openai": 4,
      "ollama": 1,
      "finding": "OpenAI used option-chain, FNO analytics, and strategy tools; Ollama used only an options-chain-like tool and produced incomplete/wrong strike reasoning."
    },
    "complex_portfolio_risk_assessment": {
      "openai": 4,
      "ollama": 1,
      "finding": "OpenAI produced a portfolio risk assessment using compare_stocks; Ollama returned a raw get_portfolio_pnl JSON stub and omitted all requested symbols."
    },
    "complex_multiturn_followup_2": {
      "openai": 4,
      "ollama": 1,
      "finding": "OpenAI retained WELCORP and compared it with JINDALSAW; Ollama lost prior context and invented TREKKING."
    },
    "complex_multi_tool_failure_handling": {
      "openai": 4,
      "ollama": 1,
      "finding": "OpenAI called multiple relevant tools and exposed an intraday-table failure; Ollama produced unsupported APOLLOPIPE claims without trace evidence."
    },
    "complex_code_assimilation_reports_py": {
      "openai": 4,
      "ollama": 1,
      "finding": "OpenAI generated a conceptual workflow and testing plan; Ollama timed out."
    },
    "complex_end_to_end_trade_research": {
      "openai": 1,
      "ollama": 1,
      "finding": "Both treated End-to-end as a symbol and missed THERMAX."
    }
  }
}
```

## Raw Output Location

- JSON: `/Users/pgorai/Documents/Projects/Unified-NSE-Analysis/reports/model_benchmarks/agent_model_benchmark_20260512_102408.json`
