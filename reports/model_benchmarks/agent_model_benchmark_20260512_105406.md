# Agent Adda Model Benchmark Report

Generated: `2026-05-12T10:54:06`

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
| openai | 52 | 0 | 1.093s | 1.62 | 153.9 | 23 | 11 | 49 | 3 |
| ollama | 50 | 2 | 3.234s | 1.6 | 163.7 | 20 | 11 | 46 | 4 |

## Case Results

| Case | Category | OpenAI Status / Tools / Factual / Time | Ollama Status / Tools / Factual / Time |
|---|---|---|---|
| `market_overview` | market_overview | ok / 3 / pass / 1.505s | ok / 3 / pass / 0.097s |
| `stock_technical_dmart` | stock_technical | ok / 4 / pass / 0.415s | ok / 4 / pass / 0.047s |
| `education_roce_roe` | market_education | ok / 1 / pass / 0.756s | ok / 1 / pass / 0.741s |
| `compare_stocks` | comparative_research | ok / 1 / pass / 0.442s | ok / 1 / pass / 0.502s |
| `strength_validation` | validated_strength | ok / 1 / pass / 0.357s | ok / 1 / pass / 0.445s |
| `intraday_nifty` | intraday_situation | ok / 2 / fail / 0.069s | ok / 2 / fail / 0.075s |
| `tool_heavy_research` | tool_calls | ok / 4 / pass / 0.047s | ok / 4 / pass / 0.047s |
| `prompt_market` | prompt_library | ok / 3 / pass / 0.088s | ok / 3 / pass / 0.102s |
| `prompt_intraday` | prompt_library | ok / 3 / pass / 20.76s | ok / 1 / fail / 31.333s |
| `prompt_technical` | prompt_library | ok / 4 / pass / 0.05s | ok / 4 / pass / 0.113s |
| `prompt_sector` | prompt_library | ok / 2 / fail / 0.067s | ok / 2 / fail / 0.075s |
| `prompt_screener` | prompt_library | ok / 1 / pass / 7.6s | error / 0 / fail / 60.006s |
| `prompt_fundamentals` | prompt_library | ok / 4 / pass / 0.057s | ok / 4 / pass / 0.066s |
| `prompt_stock` | prompt_library | ok / 5 / pass / 3.377s | ok / 5 / pass / 2.956s |
| `prompt_news` | prompt_library | ok / 1 / pass / 7.962s | error / 0 / fail / 60.006s |
| `prompt_portfolio` | prompt_library | ok / 1 / pass / 0.519s | ok / 1 / pass / 0.638s |
| `prompt_global` | prompt_library | ok / 1 / pass / 0.006s | ok / 1 / pass / 0.017s |
| `scan_default` | slash_scan | ok / 1 / pass / 0.309s | ok / 1 / pass / 0.708s |
| `scan_nifty_bank` | slash_scan | ok / 1 / pass / 0.213s | ok / 1 / pass / 0.717s |
| `scan_nifty_midcap` | slash_scan | ok / 1 / pass / 0.178s | ok / 1 / pass / 0.341s |
| `scan_orb` | slash_scan | ok / 1 / pass / 0.131s | ok / 1 / pass / 0.515s |
| `scan_gap` | slash_scan | ok / 1 / pass / 0.136s | ok / 1 / pass / 0.518s |
| `scan_macd` | slash_scan | ok / 1 / pass / 0.145s | ok / 1 / pass / 0.162s |
| `scan_rsi` | slash_scan | ok / 1 / pass / 0.125s | ok / 1 / pass / 0.135s |
| `scan_bb` | slash_scan | ok / 1 / pass / 0.125s | ok / 1 / pass / 0.13s |
| `scan_vwap` | slash_scan | ok / 1 / pass / 0.127s | ok / 1 / pass / 0.126s |
| `scan_vcp` | slash_scan | ok / 1 / pass / 0.135s | ok / 1 / pass / 0.154s |
| `scan_momentum` | slash_scan | ok / 1 / pass / 0.143s | ok / 1 / pass / 0.13s |
| `screen_stage2` | slash_screen | ok / 1 / pass / 0.006s | ok / 1 / pass / 0.005s |
| `screen_momentum` | slash_screen | ok / 1 / pass / 0.005s | ok / 1 / pass / 0.005s |
| `screen_highrs` | slash_screen | ok / 1 / pass / 0.005s | ok / 1 / pass / 0.006s |
| `screen_turnaround` | slash_screen | ok / 1 / pass / 0.005s | ok / 1 / pass / 0.005s |
| `screen_base` | slash_screen | ok / 1 / pass / 0.006s | ok / 1 / pass / 0.005s |
| `screen_tight` | slash_screen | ok / 1 / pass / 0.005s | ok / 1 / pass / 0.004s |
| `screen_dip` | slash_screen | ok / 1 / pass / 0.005s | ok / 1 / pass / 0.004s |
| `cmd_model_status` | slash_command | ok / 0 / pass / 0.0s | ok / 0 / pass / 0.0s |
| `cmd_prompts_catalog` | slash_command | ok / 0 / pass / 0.0s | ok / 0 / pass / 0.0s |
| `cmd_backtest_list` | slash_command | ok / 0 / pass / 0.024s | ok / 0 / pass / 0.0s |
| `cmd_backtest_validate` | slash_command | ok / 0 / pass / 0.007s | ok / 0 / pass / 0.007s |
| `cmd_strength` | slash_command | ok / 0 / pass / 0.37s | ok / 0 / pass / 0.373s |
| `cmd_report_stage2_md` | slash_command | ok / 0 / pass / 0.013s | ok / 0 / pass / 0.011s |
| `cmd_report_sector_rotation_md` | slash_command | ok / 0 / pass / 0.005s | ok / 0 / pass / 0.005s |
| `learn_pe_ratio` | market_education | ok / 1 / pass / 1.271s | ok / 1 / pass / 1.419s |
| `learn_minervini` | market_education | ok / 1 / pass / 1.515s | ok / 1 / pass / 1.8s |
| `stock_brief_welcorp` | stock_brief | ok / 4 / pass / 0.063s | ok / 4 / pass / 0.047s |
| `stock_brief_navabupa` | stock_brief | ok / 4 / fail / 3.934s | ok / 4 / fail / 1.709s |
| `stock_brief_ushamart` | stock_brief | ok / 4 / pass / 0.049s | ok / 4 / pass / 0.048s |
| `market_clock` | market_clock | ok / 2 / pass / 0.06s | ok / 2 / pass / 0.375s |
| `fno_options` | fno | ok / 2 / pass / 2.192s | ok / 2 / pass / 0.309s |
| `global_readthrough` | global | ok / 2 / pass / 0.073s | ok / 2 / pass / 0.06s |
| `multi_turn_1` | multi_turn_context | ok / 4 / pass / 0.046s | ok / 4 / pass / 0.047s |
| `multi_turn_2` | multi_turn_context | ok / 1 / pass / 1.309s | ok / 1 / pass / 1.011s |

## Factual Check Failures

### openai

- `intraday_nifty`: `{"missing_symbols": [], "missing_required_tools": ["get_nse_intraday_snapshot"], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `prompt_sector`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["sector"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `stock_brief_navabupa`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["missing"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`

### ollama

- `intraday_nifty`: `{"missing_symbols": [], "missing_required_tools": ["get_nse_intraday_snapshot"], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `prompt_intraday`: `{"missing_symbols": ["RELIANCE"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `prompt_sector`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["sector"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`
- `prompt_screener`: `{"missing_symbols": [], "missing_required_tools": ["run_screener_query"], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": false, "error": "ReadTimeout: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=60)"}`
- `prompt_news`: `{"missing_symbols": ["INFY"], "missing_required_tools": [], "missing_required_terms": [], "forbidden_term_hits": [], "data_freshness_issue": true, "error": "ReadTimeout: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=60)"}`
- `stock_brief_navabupa`: `{"missing_symbols": [], "missing_required_tools": [], "missing_required_terms": ["missing"], "forbidden_term_hits": [], "data_freshness_issue": false, "error": null}`

## Report Generation

- Stage 2 Markdown report generated in `0.012s` at `/Users/pgorai/Documents/Projects/Unified-NSE-Analysis/reports/generated/NSE_stage2_20260512_105751.md` with `20131` characters.

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
  "summary": "OpenAI gpt-4o is the stronger backend for this benchmark. Much of the application output is deterministic/template-driven, so both backends perform similarly on simple market overview, stock brief, comparison, screener, slash-command, and report-generation routes. The separation appears in LLM-driven tasks: OpenAI generally selected the right intraday tools and produced usable trade-context output, while Ollama granite4 timed out on several research prompts and produced a materially wrong RELIANCE intraday response using option-chain data, missing the requested symbol and fabricating/deriving unusable stock details. Both backends still show application-level weaknesses: missing required NSE intraday snapshot in one NIFTY intraday case, weak sector-specific routing, weak global-cue routing in one global query, poor handling of unavailable NAVABUPA data, index scan commands defaulting to RELIANCE, and duplicated WELCORP in multi-turn comparison."
}
```

### Strengths

```json
{
  "openai": [
    "Best overall LLM-driven tool choice, especially in RELIANCE intraday where it used source health, NSE snapshot, and intraday analysis.",
    "Consistently includes source trails, freshness labels, market clock, missing-evidence flags, and investment-advice disclaimers in template-backed responses.",
    "Handles knowledge responses conservatively by refusing to infer when reliable sources are unavailable.",
    "Successfully completed screener and catalyst prompts that caused Ollama timeouts.",
    "Good command/report compatibility with deterministic slash-command routes."
  ],
  "ollama": [
    "Matches OpenAI on many deterministic application routes, including market overview, stock brief, comparison, slash screen, report, and backtest commands.",
    "Very fast on many template-backed tool routes when not timing out.",
    "Often preserves source trails, freshness labels, missing-evidence flags, and disclaimers when the application route controls output.",
    "Correctly refuses unsupported market-education inference in the Minervini/VCP case.",
    "Structured JSON command outputs are generally parseable and usable."
  ]
}
```

### Weaknesses

```json
{
  "openai": [
    "Missed required get_nse_intraday_snapshot in the NIFTY50 intraday case.",
    "Weak sector-routing: IT sector prompt returned broad market overview rather than sector breadth/leaders/laggards.",
    "Weak global-routing in one global_readthrough case: returned local market overview instead of global cues.",
    "NAVABUPA unavailable-data case still generated technical risk warnings without data support.",
    "Multi-turn comparison duplicated WELCORP and did not explicitly answer evidence-quality ranking.",
    "Index scan commands defaulted to RELIANCE, indicating command-argument handling failure outside the model."
  ],
  "ollama": [
    "Severe LLM-driven failure on RELIANCE intraday: wrong tool, wrong data class, missing symbol, and unusable/fabricated price context.",
    "Timed out on prompt_screener and prompt_news, reducing reliability for research/report-assimilation workloads.",
    "Same sector, global, NAVABUPA, multi-turn duplication, and scan-command coverage issues as OpenAI.",
    "Less reliable tool discipline under ambiguous LLM-driven prompts.",
    "Weaker output usability on long-form reasoning tasks because failures are either timeouts or irrelevant option-chain summaries."
  ]
}
```

### Tool Call Findings

```json
{
  "score_openai": 4,
  "score_ollama": 3,
  "findings": [
    "Both backends used the correct tools for core deterministic routes: get_live_market_overview, get_market_breadth, get_fii_dii_activity, compare_stocks, validate_strength_watchlist, run_screener_query, get_options_chain, and get_futures_analysis.",
    "OpenAI made the correct intraday RELIANCE calls: get_intraday_source_health, get_nse_intraday_snapshot, and get_intraday_analysis.",
    "Ollama used get_options_chain for RELIANCE intraday, which is the wrong tool family for stock intraday target/stop analysis.",
    "Both missed get_nse_intraday_snapshot for the NIFTY50 intraday query.",
    "Both failed to call catalyst/forensic tools in the WELCORP heavy-research query despite asking for latest catalysts and forensic red flags.",
    "Ollama had two 60-second read timeouts, including missing run_screener_query for a screener prompt."
  ]
}
```

### Context Findings

```json
{
  "score_openai": 3,
  "score_ollama": 3,
  "findings": [
    "Both backends correctly avoided treating the word 'it' as a ticker in the multi-turn case.",
    "Both used prior context to infer WELCORP, but the comparison output included WELCORP twice: WELCORP, NAVABUPA, WELCORP.",
    "Neither backend produced a clear evidence-quality conclusion in the multi-turn answer; WELCORP should have been explicitly identified as higher evidence quality because NAVABUPA had unresolved symbol and missing DB/history data.",
    "Context management appears application-assisted and mostly stable, but de-duplication and follow-up answer synthesis need remediation."
  ]
}
```

### Report Generation Findings

```json
{
  "score_openai": 5,
  "score_ollama": 5,
  "findings": [
    "Report generation succeeded independently of LLM behavior: stage2 markdown report was generated directly from DB snapshot.",
    "Both /report stage2 md and /report sector-rotation md returned success paths, titles, formats, report types, and no-LLM-required notes.",
    "The standalone report_generation object shows a successful markdown report with 20131 content characters.",
    "Because reports are deterministic DB-backed outputs, backend choice has little impact on this route."
  ]
}
```

### Factual Accuracy Findings

```json
{
  "score_openai": 4,
  "score_ollama": 3,
  "findings": [
    "OpenAI had fewer severe factual failures; most factual-check failures were missing tools or weak routing rather than invented data.",
    "Ollama produced the most serious factual issue in RELIANCE intraday by presenting option-chain-derived context as stock information, including 'Current Price: ₹10' and 'symbol not explicitly mentioned'.",
    "Both backends failed the NAVABUPA unavailable-data standard by adding unsupported technical risk warnings despite no snapshot or price history.",
    "Both sometimes used stale/fallback data but generally labeled freshness in F&O and market contexts.",
    "Both returned high-RS and momentum screens where relative_strength was null, exposing a data-definition/reporting mismatch that should be flagged more clearly."
  ]
}
```

### Command Coverage Findings

```json
{
  "score_openai": 3,
  "score_ollama": 3,
  "findings": [
    "Basic slash commands were well covered: /model, /prompts, /backtest list, /strategy-lab validate, /strength, /report, and /screen variants.",
    "Slash scan coverage is weak: /scan NIFTY BANK and /scan NIFTY MIDCAP 100 scanned only RELIANCE rather than the requested index universe.",
    "Scan strategy aliases such as orb, gap, macd, rsi, bb, vwap, vcp, and momentum mapped to strategy sets, but symbol/universe handling was unreliable.",
    "OpenAI and Ollama both depend on deterministic command handlers here; defects are likely in command parsing/default-universe logic rather than pure model reasoning."
  ]
}
```

### Recommended Backend Policy

```json
{
  "primary_backend": "OpenAI gpt-4o",
  "secondary_backend": "Ollama granite4:latest",
  "policy": [
    "Use OpenAI gpt-4o as the default for LLM-driven research, intraday analysis, catalyst synthesis, multi-tool orchestration, and any task requiring source assimilation.",
    "Allow Ollama granite4:latest for deterministic, DB-backed, low-risk routes such as /model, /prompts, /backtest list, /strategy-lab validate, /screen, /strength, and /report where the application controls tool execution and output structure.",
    "Do not use Ollama as primary for intraday trade setup, news/catalyst research, or long-form synthesis until timeout and wrong-tool failures are remediated.",
    "Require tool-gating for all market-data answers: if a query asks for intraday NSE snapshot, sector analysis, global cues, or catalysts, enforce the required tool set before any natural-language answer is generated.",
    "Require unavailable-data hard stop: if symbol resolution and price history fail, output only missing fields and source errors; suppress derived risk, trend, SMA, ADX, target, and stop statements.",
    "Implement automatic fallback from Ollama to OpenAI after timeout, wrong required tool, missing symbol, or failed factual check."
  ]
}
```

### Remediation Backlog

- `{"priority": "P0", "item": "Add required-tool enforcement for intraday queries.", "details": "For NSE intraday requests, require get_nse_intraday_snapshot first and label yfinance/intraday_analysis as fallback. Block answers if required tools are absent."}`
- `{"priority": "P0", "item": "Fix Ollama wrong-tool routing for stock intraday prompts.", "details": "Prevent get_options_chain from satisfying equity intraday setup prompts unless the user explicitly asks for options."}`
- `{"priority": "P0", "item": "Harden unavailable-symbol behavior.", "details": "For NAVABUPA-like failures, suppress generic technical risks and state exact missing evidence: symbol resolution, DB snapshot, price history, technical setup, sector context."}`
- `{"priority": "P1", "item": "Fix sector-analysis routing.", "details": "IT sector prompts should call sector-specific breadth/leaders/laggards/rotation tools or clearly state that such data is unavailable, not return broad market overview only."}`
- `{"priority": "P1", "item": "Fix global-readthrough routing.", "details": "Queries asking for US, Asia, crude, USD/INR, or global cues should use get_global_market_assessment rather than local market overview."}`
- `{"priority": "P1", "item": "Repair slash scan universe parsing.", "details": "/scan NIFTY BANK and /scan NIFTY MIDCAP 100 must scan the requested universe, not default to RELIANCE. If universe expansion fails, return an explicit error."}`
- `{"priority": "P1", "item": "Add multi-turn de-duplication and answer synthesis.", "details": "When resolving pronouns, avoid duplicate symbols and explicitly answer comparative questions such as evidence-quality ranking."}`
- `{"priority": "P1", "item": "Add timeout fallback policy for Ollama.", "details": "If Ollama exceeds a lower threshold or fails factual checks, automatically retry with OpenAI or a deterministic tool route."}`
- `{"priority": "P2", "item": "Improve fundamental-review routing.", "details": "TCS fundamental queries should retrieve ROE, ROCE, debt, valuation, growth, and missing fields rather than returning mostly technical stock briefs."}`
- `{"priority": "P2", "item": "Clarify screener evidence gaps.", "details": "If a screener description claims RS thresholds but relative_strength is null, flag this as missing evidence or adjust description to match available fields."}`
- `{"priority": "P2", "item": "Expand heavy-research tool coverage.", "details": "Queries asking for catalysts and forensic red flags should call catalyst/news and forensic/risk tools, and separate fresh evidence from stale or unavailable evidence."}`

### Case Scores

```json
{
  "market_overview": {
    "openai": 5,
    "ollama": 5,
    "finding": "Both used live market overview, breadth, and FII/DII tools with freshness and source trail."
  },
  "stock_technical_dmart": {
    "openai": 4,
    "ollama": 4,
    "finding": "Both provided stage, RSI, ADX, MACD, supertrend, moving averages, missing RS evidence, and source trail; support/resistance detail was limited."
  },
  "education_roce_roe": {
    "openai": 4,
    "ollama": 4,
    "finding": "Both stayed source-backed and avoided inferring blocked Investopedia content."
  },
  "compare_stocks": {
    "openai": 4,
    "ollama": 4,
    "finding": "Both used compare_stocks and avoided filling RS; risk/fundamental depth was thin."
  },
  "strength_validation": {
    "openai": 4,
    "ollama": 4,
    "finding": "Both correctly flagged missing RS and financial-strength evidence."
  },
  "intraday_nifty": {
    "openai": 3,
    "ollama": 3,
    "finding": "Both missed the required get_nse_intraday_snapshot tool despite the instruction to use NSE snapshot first."
  },
  "tool_heavy_research_welcorp": {
    "openai": 3,
    "ollama": 3,
    "finding": "Both showed tools used and core technical context, but did not actually fetch latest catalysts or forensic red-flag tools."
  },
  "prompt_intraday_reliance": {
    "openai": 4,
    "ollama": 1,
    "finding": "OpenAI used source health, NSE intraday snapshot, and intraday analysis. Ollama used get_options_chain, omitted RELIANCE as a resolved symbol, and produced unusable/fabricated stock context."
  },
  "prompt_sector_it": {
    "openai": 2,
    "ollama": 2,
    "finding": "Both returned broad market context rather than IT sector breadth, leaders, laggards, rotation, and risks."
  },
  "prompt_screener_stage2": {
    "openai": 4,
    "ollama": 1,
    "finding": "OpenAI ran the screener and explained candidates. Ollama timed out and missed run_screener_query."
  },
  "prompt_news_infy": {
    "openai": 4,
    "ollama": 1,
    "finding": "OpenAI returned catalyst items with URLs and freshness comments. Ollama timed out and failed the freshness/symbol checks."
  },
  "prompt_fundamentals_tcs": {
    "openai": 3,
    "ollama": 3,
    "finding": "Both answered with a generic stock technical brief rather than a true fundamental-quality review covering ROCE, debt, valuation, growth, and missing fields."
  },
  "prompt_stock_hdfcbank": {
    "openai": 4,
    "ollama": 4,
    "finding": "Both used technical, sector, and catalyst tools; output was usable but fundamentals and risk synthesis remained shallow."
  },
  "prompt_portfolio": {
    "openai": 3,
    "ollama": 3,
    "finding": "Both compared evidence fields but gave limited portfolio-risk synthesis."
  },
  "prompt_global": {
    "openai": 5,
    "ollama": 5,
    "finding": "Both used the global market assessment tool and gave sector read-through with data freshness."
  },
  "slash_scan": {
    "openai": 2,
    "ollama": 2,
    "finding": "Both executed scan tools, but index scans such as NIFTY BANK and NIFTY MIDCAP 100 incorrectly scanned only RELIANCE. Ollama generated live buy signals in some scans, but the command coverage defect remained."
  },
  "slash_screen": {
    "openai": 4,
    "ollama": 4,
    "finding": "Both returned structured screener JSON quickly using run_screener_query, though descriptions referenced RS thresholds while relative_strength fields were null."
  },
  "slash_commands": {
    "openai": 5,
    "ollama": 5,
    "finding": "Model, prompts, backtest, strength, and report commands worked; most were deterministic and no LLM was required."
  },
  "stock_brief_navabupa": {
    "openai": 2,
    "ollama": 2,
    "finding": "Both exposed source errors but still emitted generic risk warnings such as price below SMA50 and ADX < 20 despite no usable price history."
  },
  "market_clock": {
    "openai": 3,
    "ollama": 3,
    "finding": "Both showed live market data and market clock, but answered via market overview rather than a concise market-status/fallback classification."
  },
  "fno_options": {
    "openai": 4,
    "ollama": 4,
    "finding": "Both used option-chain and futures tools and labeled stale EOD/fallback sources; interpretation of options-buying attractiveness was limited in excerpt."
  },
  "global_readthrough": {
    "openai": 2,
    "ollama": 2,
    "finding": "Both routed to market overview/breadth instead of global market assessment despite the explicit global-cues request."
  },
  "multi_turn_context": {
    "openai": 3,
    "ollama": 3,
    "finding": "Both resolved 'it' to WELCORP rather than treating it as a ticker, but duplicated WELCORP in the comparison and did not clearly rank evidence quality."
  }
}
```

## Raw Output Location

- JSON: `/Users/pgorai/Documents/Projects/Unified-NSE-Analysis/reports/model_benchmarks/agent_model_benchmark_20260512_105406.json`
