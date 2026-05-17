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
- Overall winner: `n/a`

### Executive Summary

n/a

### Strengths

n/a

### Weaknesses

n/a

### Tool Call Findings

n/a

### Context Findings

n/a

### Report Generation Findings

n/a

### Factual Accuracy Findings

n/a

### Command Coverage Findings

n/a

### Recommended Backend Policy

n/a

### Remediation Backlog

n/a

### Case Scores

```json
{}
```

## Raw Output Location

- JSON: `/Users/pgorai/Documents/Projects/Unified-NSE-Analysis/reports/model_benchmarks/agent_model_benchmark_20260512_031830.json`
