# Agent Adda Model Benchmark Report

Generated: `2026-05-12T11:16:25`

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
| openai | 52 | 0 | 1.433s | 1.62 | 164.8 | 23 | 12 | 51 | 1 |
| ollama | 51 | 1 | 3.467s | 1.55 | 173.0 | 19 | 13 | 48 | 3 |

## Case Results

| Case | Category | OpenAI Status / Tools / Factual / Time | Ollama Status / Tools / Factual / Time |
|---|---|---|---|
| `market_overview` | market_overview | ok / 3 / pass / 0.423s | ok / 3 / pass / 0.162s |
| `stock_technical_dmart` | stock_technical | ok / 4 / pass / 0.058s | ok / 4 / pass / 0.057s |
| `education_roce_roe` | market_education | ok / 1 / pass / 1.49s | ok / 1 / pass / 0.758s |
| `compare_stocks` | comparative_research | ok / 1 / pass / 0.477s | ok / 1 / pass / 0.484s |
| `strength_validation` | validated_strength | ok / 1 / pass / 0.385s | ok / 1 / pass / 0.412s |
| `intraday_nifty` | intraday_situation | ok / 2 / pass / 13.701s | ok / 1 / fail / 27.76s |
| `tool_heavy_research` | tool_calls | ok / 4 / pass / 0.062s | ok / 4 / pass / 0.073s |
| `prompt_market` | prompt_library | ok / 3 / pass / 0.133s | ok / 3 / pass / 0.142s |
| `prompt_intraday` | prompt_library | ok / 2 / pass / 11.589s | ok / 1 / fail / 21.724s |
| `prompt_technical` | prompt_library | ok / 4 / pass / 0.052s | ok / 4 / pass / 0.062s |
| `prompt_sector` | prompt_library | ok / 2 / fail / 0.09s | ok / 2 / fail / 0.102s |
| `prompt_screener` | prompt_library | ok / 1 / pass / 14.479s | error / 0 / fail / 60.006s |
| `prompt_fundamentals` | prompt_library | ok / 4 / pass / 0.063s | ok / 4 / pass / 0.065s |
| `prompt_stock` | prompt_library | ok / 5 / pass / 3.27s | ok / 5 / pass / 3.175s |
| `prompt_news` | prompt_library | ok / 2 / pass / 14.731s | ok / 0 / pass / 53.884s |
| `prompt_portfolio` | prompt_library | ok / 1 / pass / 0.522s | ok / 1 / pass / 0.501s |
| `prompt_global` | prompt_library | ok / 1 / pass / 0.006s | ok / 1 / pass / 0.015s |
| `scan_default` | slash_scan | ok / 1 / pass / 0.862s | ok / 1 / pass / 0.618s |
| `scan_nifty_bank` | slash_scan | ok / 1 / pass / 0.206s | ok / 1 / pass / 0.645s |
| `scan_nifty_midcap` | slash_scan | ok / 1 / pass / 0.138s | ok / 1 / pass / 0.209s |
| `scan_orb` | slash_scan | ok / 1 / pass / 0.126s | ok / 1 / pass / 0.765s |
| `scan_gap` | slash_scan | ok / 1 / pass / 0.313s | ok / 1 / pass / 0.539s |
| `scan_macd` | slash_scan | ok / 1 / pass / 0.134s | ok / 1 / pass / 0.184s |
| `scan_rsi` | slash_scan | ok / 1 / pass / 0.131s | ok / 1 / pass / 0.127s |
| `scan_bb` | slash_scan | ok / 1 / pass / 0.158s | ok / 1 / pass / 0.175s |
| `scan_vwap` | slash_scan | ok / 1 / pass / 0.138s | ok / 1 / pass / 0.118s |
| `scan_vcp` | slash_scan | ok / 1 / pass / 0.144s | ok / 1 / pass / 0.13s |
| `scan_momentum` | slash_scan | ok / 1 / pass / 0.421s | ok / 1 / pass / 0.208s |
| `screen_stage2` | slash_screen | ok / 1 / pass / 0.009s | ok / 1 / pass / 0.007s |
| `screen_momentum` | slash_screen | ok / 1 / pass / 0.007s | ok / 1 / pass / 0.005s |
| `screen_highrs` | slash_screen | ok / 1 / pass / 0.006s | ok / 1 / pass / 0.005s |
| `screen_turnaround` | slash_screen | ok / 1 / pass / 0.005s | ok / 1 / pass / 0.005s |
| `screen_base` | slash_screen | ok / 1 / pass / 0.005s | ok / 1 / pass / 0.005s |
| `screen_tight` | slash_screen | ok / 1 / pass / 0.005s | ok / 1 / pass / 0.004s |
| `screen_dip` | slash_screen | ok / 1 / pass / 0.005s | ok / 1 / pass / 0.004s |
| `cmd_model_status` | slash_command | ok / 0 / pass / 0.0s | ok / 0 / pass / 0.0s |
| `cmd_prompts_catalog` | slash_command | ok / 0 / pass / 0.0s | ok / 0 / pass / 0.0s |
| `cmd_backtest_list` | slash_command | ok / 0 / pass / 0.007s | ok / 0 / pass / 0.0s |
| `cmd_backtest_validate` | slash_command | ok / 0 / pass / 0.005s | ok / 0 / pass / 0.005s |
| `cmd_strength` | slash_command | ok / 0 / pass / 0.391s | ok / 0 / pass / 0.398s |
| `cmd_report_stage2_md` | slash_command | ok / 0 / pass / 0.012s | ok / 0 / pass / 0.011s |
| `cmd_report_sector_rotation_md` | slash_command | ok / 0 / pass / 0.005s | ok / 0 / pass / 0.005s |
| `learn_pe_ratio` | market_education | ok / 1 / pass / 1.282s | ok / 1 / pass / 1.654s |
| `learn_minervini` | market_education | ok / 1 / pass / 1.562s | ok / 1 / pass / 1.71s |
| `stock_brief_welcorp` | stock_brief | ok / 4 / pass / 0.063s | ok / 4 / pass / 0.06s |
| `stock_brief_navabupa` | stock_brief | ok / 4 / pass / 3.859s | ok / 4 / pass / 1.441s |
| `stock_brief_ushamart` | stock_brief | ok / 4 / pass / 0.049s | ok / 4 / pass / 0.048s |
| `market_clock` | market_clock | ok / 2 / pass / 0.084s | ok / 2 / pass / 0.373s |
| `fno_options` | fno | ok / 2 / pass / 1.568s | ok / 2 / pass / 0.255s |
| `global_readthrough` | global | ok / 2 / pass / 0.089s | ok / 2 / pass / 0.074s |
| `multi_turn_1` | multi_turn_context | ok / 4 / pass / 0.048s | ok / 4 / pass / 0.048s |
| `multi_turn_2` | multi_turn_context | ok / 1 / pass / 1.162s | ok / 1 / pass / 1.071s |

## Factual Check Failures

### openai

- `prompt_sector`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["sector"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`

### ollama

- `intraday_nifty`: `{"missing_symbols": [], "missing_required_tools": ["get_nse_intraday_snapshot"], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `prompt_intraday`: `{"missing_symbols": ["RELIANCE"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `prompt_sector`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["sector"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `prompt_screener`: `{"missing_symbols": [], "missing_required_tools": ["run_screener_query"], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": "ReadTimeout: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=60)"}`

## Report Generation

- Stage 2 Markdown report generated in `0.018s` at `/Users/pgorai/Documents/Projects/Unified-NSE-Analysis/reports/generated/NSE_stage2_20260512_112041.md` with `20131` characters.

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
  "openai_score": 4,
  "ollama_score": 3,
  "summary": "OpenAI gpt-4o is the safer default backend for Agent Adda market workflows. Both backends perform well on deterministic routed commands, stock briefs, screeners, slash commands, report generation, and database-backed market summaries. The decisive gap appears in LLM-driven workflows: OpenAI generally selected the right market tools and preserved data freshness, while Ollama granite4:latest made wrong tool calls, timed out, omitted source trails, and fabricated unsupported news/catalyst details. Both backends share some application-level issues such as generic sector handling, wrong /scan symbol coverage, duplicate WELCORP in multi-turn comparison, and weak assimilation of fundamentals/news into full research briefs."
}
```

### Strengths

```json
{
  "openai": [
    "Strong tool discipline on most market, stock, F&O, comparison, education, and report-generation cases.",
    "Generally transparent source trails with market clock and data freshness labels.",
    "Good missing-evidence handling for unavailable symbols and null fields.",
    "Better LLM-driven fallback behavior than Ollama for intraday and news workflows.",
    "Produced usable narrative explanations for screeners and catalysts when tools were available."
  ],
  "ollama": [
    "Performs well on deterministic routed workflows where the application selects the tool path.",
    "Fast and accurate for many stock briefs, slash screeners, slash commands, market overview, and report commands.",
    "Correctly flags missing evidence in database-backed stock and strength-validation outputs.",
    "Matches OpenAI output quality on many templated DB-backed responses."
  ]
}
```

### Weaknesses

```json
{
  "openai": [
    "Some queries were misrouted to generic market overview instead of sector/global-specific analysis.",
    "Tool-heavy WELCORP research omitted requested catalysts and forensic red flags despite claiming a full brief.",
    "Intraday RELIANCE response had weak risk framing, used lower circuit as invalidation, and had one failed intraday OHLCV tool.",
    "Slash scan commands incorrectly scanned RELIANCE for NIFTY BANK and NIFTY MIDCAP 100.",
    "Multi-turn comparison duplicated WELCORP and did not fully answer which stock had better evidence quality."
  ],
  "ollama": [
    "Severe LLM-driven tool discipline failures: wrong tools for intraday, missing required NSE snapshot, and no tools for INFY news.",
    "Fabricated unsupported INFY catalyst data and stale/future-inconsistent facts without source trail.",
    "Timed out on prompt_screener and failed to call the required screener tool.",
    "Produced code/debugging advice instead of RELIANCE intraday market analysis after a tool error.",
    "Shares application-level symbol/universe bugs in slash scan and multi-turn duplicate comparison."
  ]
}
```

### Tool Call Findings

```json
{
  "openai": {
    "score": 4,
    "findings": [
      "Tool calls were mostly appropriate and complete across market overview, stock briefs, comparisons, education, F&O, and screeners.",
      "OpenAI used get_intraday_source_health and get_nse_intraday_snapshot for NIFTY, respecting the NSE-first instruction.",
      "One intraday RELIANCE tool failed because intraday_ohlcv table was missing, but OpenAI still used get_nse_intraday_snapshot.",
      "Some tool omissions remain: WELCORP catalyst/forensic requests did not trigger catalyst or forensic tools; global_readthrough was routed to domestic market tools."
    ]
  },
  "ollama": {
    "score": 2,
    "findings": [
      "Tool use was reliable only when deterministic application routing dominated.",
      "NIFTY intraday called analyze_document and hit HTTP 404 instead of get_nse_intraday_snapshot.",
      "RELIANCE intraday called get_watchlist_alerts incorrectly and then answered with function-debugging advice.",
      "INFY catalysts used zero tools and generated unsupported content.",
      "Stage 2 screener explanation timed out and missed run_screener_query."
    ]
  }
}
```

### Context Findings

```json
{
  "openai": {
    "score": 3,
    "findings": [
      "Resolved the pronoun 'it' to WELCORP instead of treating it as a ticker.",
      "However, the comparison included WELCORP twice and did not clearly synthesize the evidence-quality conclusion versus NAVABUPA.",
      "Mode/source label switched to intraday for the comparison, which may confuse evidence provenance."
    ]
  },
  "ollama": {
    "score": 3,
    "findings": [
      "Matched OpenAI in resolving 'it' to WELCORP.",
      "Repeated the same duplicate WELCORP comparison issue.",
      "No additional context-management advantage was visible over OpenAI."
    ]
  }
}
```

### Report Generation Findings

```json
{
  "openai": {
    "score": 5,
    "findings": [
      "Report commands returned successful Markdown report metadata with path, title, type, symbol, and DB-backed note.",
      "Standalone report_generation result produced a 20131-character Stage 2 Markdown report directly from DB snapshot.",
      "No LLM hallucination risk was observed in report generation."
    ]
  },
  "ollama": {
    "score": 5,
    "findings": [
      "Report commands succeeded with the same DB-backed deterministic behavior.",
      "Because reports are generated outside the LLM, Ollama performed equivalently for this path."
    ]
  }
}
```

### Factual Accuracy Findings

```json
{
  "openai": {
    "score": 4,
    "findings": [
      "Most factual checks passed, with explicit freshness and missing-evidence labels.",
      "NAVABUPA was handled safely without hallucinated data.",
      "Some outputs under-covered requested facts: IT sector analysis lacked sector-specific structure; full fundamentals did not provide ROE/ROCE/debt/growth depth; WELCORP catalyst/forensic evidence was missing.",
      "Slash scan wrong-universe behavior is a factual usability issue even though benchmark factual checks passed."
    ]
  },
  "ollama": {
    "score": 2,
    "findings": [
      "Database-backed factual outputs were usually accurate because they reused deterministic tool results.",
      "LLM-generated INFY news/catalysts were fabricated or unsupported, with no tool calls and stale/inconsistent date framing.",
      "Intraday outputs failed required data-source checks and omitted the requested symbol in RELIANCE intraday.",
      "The timeout on prompt_screener caused a missing factual check and missing required tool."
    ]
  }
}
```

### Command Coverage Findings

```json
{
  "openai": {
    "score": 4,
    "findings": [
      "Covered most slash commands, screeners, strength, reports, model status, prompt catalog, backtest, stock brief, market, F&O, and education paths.",
      "Command coverage is weakened by /scan index queries scanning RELIANCE instead of the requested index/universe.",
      "Sector and global natural-language prompt coverage needs better intent routing."
    ]
  },
  "ollama": {
    "score": 3,
    "findings": [
      "Covered deterministic slash commands well.",
      "Failed or timed out on multiple natural-language LLM-driven workflows.",
      "Shares the same /scan index universe bug as OpenAI."
    ]
  }
}
```

### Recommended Backend Policy

```json
{
  "default_backend": "OpenAI gpt-4o",
  "policy": [
    "Use OpenAI gpt-4o as the default backend for user-facing natural-language market research, intraday analysis, news/catalysts, and multi-tool synthesis.",
    "Allow Ollama granite4:latest only for deterministic DB-backed commands, cached slash commands, report metadata, and low-risk local/offline workflows.",
    "Require tool-backed evidence for all live market, intraday, news, F&O, fundamentals, and catalyst claims regardless of backend.",
    "Block or downgrade any response that contains market facts without a source trail, freshness label, and tool trace.",
    "Prefer deterministic command handlers over LLM generation for /scan, /screen, /report, /strength, /model, /prompts, and strategy-lab commands."
  ]
}
```

### Remediation Backlog

- `{"priority": "P0", "item": "Enforce tool contract for intraday queries", "details": "NSE intraday prompts must call get_intraday_source_health and get_nse_intraday_snapshot first; fallback tools must be explicitly labeled. Reject analyze_document or watchlist tools for this intent unless explicitly requested."}`
- `{"priority": "P0", "item": "Prevent unsupported news/catalyst generation", "details": "Require search_latest_catalysts or approved news tools for catalyst answers. If no tool result exists, return 'no fresh evidence found' rather than generating narrative."}`
- `{"priority": "P0", "item": "Fix /scan symbol and universe parsing", "details": "/scan NIFTY BANK and /scan NIFTY MIDCAP 100 should scan the requested index/universe, not default to RELIANCE. Do not treat common strategy words or index phrases as equity symbols."}`
- `{"priority": "P1", "item": "Improve sector intent routing", "details": "Sector analysis for IT should call sector-specific breadth/leader/laggard tools or filter DB universe by sector, not return generic market overview."}`
- `{"priority": "P1", "item": "Improve global read-through routing", "details": "Queries asking for US, Asia, crude, USD/INR, and sector implications should call get_global_market_assessment rather than domestic breadth-only tools."}`
- `{"priority": "P1", "item": "Add forensic and catalyst tools to stock deep-dive planner", "details": "When the query requests catalysts, news, forensic red flags, Beneish, Piotroski, or governance risk, the planner should call the appropriate evidence tools and flag unavailable fields."}`
- `{"priority": "P1", "item": "Strengthen fundamentals brief coverage", "details": "Fundamental quality prompts requesting ROE, ROCE, debt, valuation, and growth should use fundamental-specific data tools, not only stock snapshot and technical setup."}`
- `{"priority": "P2", "item": "Deduplicate symbols in multi-turn comparison", "details": "When resolving pronouns, merge context-derived symbols with explicit symbols and remove duplicates before calling compare_stocks."}`
- `{"priority": "P2", "item": "Add explicit evidence-quality summaries", "details": "Comparisons involving missing data should include a direct conclusion such as 'WELCORP has better evidence quality because NAVABUPA lacks symbol resolution, snapshot, technical, and sector data.'"}`
- `{"priority": "P2", "item": "Improve stale/fresh consistency checks", "details": "Flag contradictions such as current benchmark clock in 2026 versus generated news dated 2025, and require source timestamps for all catalyst claims."}`

### Case Scores

```json
{
  "market_overview": {
    "openai": 5,
    "ollama": 5,
    "winner": "tie",
    "notes": "Both used get_live_market_overview, get_market_breadth, and get_fii_dii_activity with freshness labels, breadth, risks, market clock, and source trail."
  },
  "stock_technical_briefs": {
    "openai": 4,
    "ollama": 4,
    "winner": "tie",
    "notes": "Both resolved symbols and used snapshot, technical setup, and sector context. Missing RS/fundamental evidence was flagged. Some inconsistencies remain between snapshot RSI/commentary and derived technical setup."
  },
  "market_education": {
    "openai": 4,
    "ollama": 4,
    "winner": "tie",
    "notes": "Both used source-backed education and refused to infer Minervini/VCP when reliable sources were unavailable. Source trails were sometimes implicit rather than formal."
  },
  "comparative_research": {
    "openai": 4,
    "ollama": 4,
    "winner": "tie",
    "notes": "Both used compare_stocks and avoided filling RS when null. Outputs were concise but did not deeply discuss risks or evidence quality."
  },
  "validated_strength": {
    "openai": 4,
    "ollama": 4,
    "winner": "tie",
    "notes": "Both used validate_strength_watchlist and clearly flagged missing RS, enhanced fundamental, and financial strength fields."
  },
  "intraday_analysis": {
    "openai": 4,
    "ollama": 1,
    "winner": "OpenAI gpt-4o",
    "notes": "OpenAI used NSE intraday snapshot and source health for NIFTY and used NSE quote for RELIANCE despite one intraday OHLCV tool error. Ollama used wrong tools, hit HTTP 404 or argument errors, missed RELIANCE, and produced troubleshooting text instead of market analysis."
  },
  "tool_heavy_research": {
    "openai": 3,
    "ollama": 3,
    "winner": "tie",
    "notes": "Both used core stock tools but did not actually fetch catalysts or forensic red flags for WELCORP despite the query requesting them."
  },
  "sector_analysis": {
    "openai": 2,
    "ollama": 2,
    "winner": "tie",
    "notes": "Both returned broad market overview rather than a focused IT sector analysis with leaders, laggards, rotation, and sector-specific risks."
  },
  "screener_explanation": {
    "openai": 4,
    "ollama": 1,
    "winner": "OpenAI gpt-4o",
    "notes": "OpenAI ran run_screener_query and explained top Stage 2 candidates while flagging missing evidence. Ollama timed out and missed the required screener tool."
  },
  "news_and_catalysts": {
    "openai": 4,
    "ollama": 1,
    "winner": "OpenAI gpt-4o",
    "notes": "OpenAI used search_latest_catalysts and Yahoo search with URLs and freshness framing. Ollama made no tool calls and fabricated unsupported INFY catalyst data with stale/inconsistent dates."
  },
  "global_market_reasoning": {
    "openai": 3,
    "ollama": 3,
    "winner": "tie",
    "notes": "Prompt-library global read-through used the correct global assessment tool for both. The separate global_readthrough case was misrouted by both to domestic market overview instead of global cues."
  },
  "slash_scan_commands": {
    "openai": 2,
    "ollama": 2,
    "winner": "tie",
    "notes": "Commands executed and returned JSON, but /scan NIFTY BANK and /scan NIFTY MIDCAP 100 still scanned RELIANCE, indicating wrong symbol/universe handling."
  },
  "slash_screen_commands": {
    "openai": 4,
    "ollama": 4,
    "winner": "tie",
    "notes": "Both returned structured JSON from run_screener_query for stage2, momentum, highrs, turnaround, base, tight, and dip screens. Missing RS values remained visible as null."
  },
  "slash_admin_and_strategy_commands": {
    "openai": 5,
    "ollama": 5,
    "winner": "tie",
    "notes": "Model status, prompt catalog, backtest list, strategy validation, strength command, and report commands were handled reliably."
  },
  "missing_symbol_handling": {
    "openai": 5,
    "ollama": 5,
    "winner": "tie",
    "notes": "NAVABUPA was not hallucinated; both listed exact missing evidence and tool errors."
  },
  "fno_options": {
    "openai": 4,
    "ollama": 4,
    "winner": "tie",
    "notes": "Both used options chain and futures tools, labeled stale EOD/fallback data, and provided PCR/max pain. Options-buying attractiveness was not deeply reasoned."
  },
  "multi_turn_context": {
    "openai": 3,
    "ollama": 3,
    "winner": "tie",
    "notes": "Both resolved 'it' to WELCORP rather than treating it as a ticker, but duplicated WELCORP in the comparison and did not clearly conclude evidence quality."
  },
  "report_generation": {
    "openai": 5,
    "ollama": 5,
    "winner": "tie",
    "notes": "Report generation was deterministic and DB-backed with successful Markdown outputs; no LLM dependency was required."
  }
}
```

## Raw Output Location

- JSON: `/Users/pgorai/Documents/Projects/Unified-NSE-Analysis/reports/model_benchmarks/agent_model_benchmark_20260512_111625.json`
