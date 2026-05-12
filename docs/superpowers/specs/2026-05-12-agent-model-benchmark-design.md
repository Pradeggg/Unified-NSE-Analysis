# Agent Adda Model Benchmark Design

## Objective

Compare the main Agent Adda chat backend across OpenAI `gpt-4o` and Ollama
`granite4:latest`, then use GPT-5.5 as an external evaluator when the API is
available. The benchmark focuses on application behavior, not only prose quality:
tool use, evidence handling, report generation, multi-turn context, market-clock
awareness, factual validation, command coverage, and failure transparency.

## Scope

The benchmark covers the main `nse_agent.py` / `terminal.agent.Agent` reasoning
backend only. It does not compare voice transcription, GPT TTS, macOS audio
playback, or the `/voice-*` commands. The full suite must contain at least 40
scenarios; the current suite contains 52.

## Test Categories

1. **Backend availability**: verify OpenAI and Ollama can be initialized.
2. **Model switching**: validate `/model` status and backend switching behavior.
3. **Market overview**: broad market query with live/tool routing.
4. **Stock technical brief**: symbol resolution, snapshot, technicals, and source trail.
5. **Education / market knowledge**: concept explanation with source-backed behavior.
6. **Comparative research**: multi-stock comparison requiring tool selection.
7. **Strength validation**: CANSLIM / RS / fundamentals / Piotroski no-assumption flow.
8. **Intraday situation assessment**: market-clock-aware intraday answer.
9. **Multi-turn context**: first query establishes a company, second query relies on context.
10. **Prompt library coverage**: run representative prompts across every prompt category.
11. **Slash command coverage**: run `/model`, `/prompts`, `/scan`, `/screen`, `/strength`, `/backtest`, `/strategy-lab`, and `/report`.
12. **Factual checks**: validate requested symbols, required tools, required terms, forbidden hallucination terms, and freshness labels.
13. **Report generation**: direct preset report generation to validate application output.

## Evaluation Rubric

Each model is scored from 1 to 5 on:

- **Instruction following**: answers the requested task without drifting.
- **Tool discipline**: calls relevant tools and does not invent unavailable data.
- **Evidence transparency**: shows source trail, data freshness, and gaps.
- **Market reasoning**: connects technical, fundamental, and market context coherently.
- **Risk handling**: avoids buy/sell advice and flags stale or missing data.
- **Context management**: uses previous turns correctly without treating filler words as symbols.
- **Output usability**: structured enough for a trader/researcher to act on as research.

The GPT-5.5 evaluator emits case-level scores plus an overall comparison. If
GPT-5.5 is unavailable, the benchmark still produces raw outputs and heuristic
metrics so the run is auditable.

## Artifacts

- Raw benchmark JSON: `reports/model_benchmarks/agent_model_benchmark_<timestamp>.json`
- Markdown report: `reports/model_benchmarks/agent_model_benchmark_<timestamp>.md`

## Guardrails

- Do not log API keys.
- Mark deterministic/no-LLM cases explicitly.
- Record errors as benchmark findings instead of hiding them.
- Treat live market/API failures as infrastructure observations, not model quality.
- Keep all generated report artifacts outside source code paths.
