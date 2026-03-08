# NSE Sector Research Agent (Ollama Granite4 + Tool Calling)

An AI agent that takes user inputs and runs the pipeline phases (2–5) and **narratives** via **tool calling** using **Ollama** and the **Granite4** model. Use the **CLI** to specify a sector and run full research (all phases + narratives) or start the interactive agent.

## CLI (recommended)

From the **project root**:

```bash
# Run full pipeline + narratives for a sector, then exit
python working-sector/agent_cli.py --sector "Auto Components" --run-all

# Start interactive agent for a sector (chat, run phases/narratives via tools)
python working-sector/agent_cli.py --sector auto_components --interactive

# Run full pipeline + narratives, then start the agent
python working-sector/agent_cli.py --sector "Auto Components" --run-all --interactive
```

**Sector:** Use a key (`auto_components`, `pharma`) or display name (`"Auto Components"`). The sector must have a universe file: `working-sector/<sector>_universe.csv` (e.g. `auto_components_universe.csv`). Outputs go to `working-sector/output/<sector>/` (or legacy `working-sector/output/` for existing auto_components data).

## Step-by-step setup

### 1. Install Ollama

- **macOS / Linux:** [ollama.com](https://ollama.com) → download and install.
- Start the server (often automatic): `ollama serve`

### 2. Pull the Granite4 model

```bash
ollama pull granite4
```

Use `granite4:latest` or a specific tag (e.g. `granite4:3b`).

### 3. Python dependencies

From the **project root**:

```bash
pip install ollama pandas numpy
```

Or ensure `ollama` is in your environment (the rest are already required by the pipeline).

### 4. Run the agent

**Via CLI (set sector first):**

```bash
python working-sector/agent_cli.py --sector "Auto Components" --interactive
```

**Or run the agent script directly** (uses `NSE_SECTOR` env or default `auto_components`):

```bash
export NSE_SECTOR=auto_components   # optional
python working-sector/agent.py
```

## How it works

1. **Agent loop:** The script reads your message (e.g. “Run the full pipeline”) and sends it to Ollama with a list of **tools** (pipeline phases and helpers).
2. **Tool calling:** If the model decides to call a tool (e.g. `run_full_pipeline`), the agent runs the corresponding Python function and appends the **text result** back into the conversation.
3. **Multi-turn tools:** The model can call several tools in sequence (e.g. Phase 2, then Phase 3) until it has enough information, then it replies in natural language.
4. **Output:** All phase outputs (CSVs, sector note, dashboard) are written to `working-sector/output/` as in the normal pipeline.

## Available tools (exposed to the model)

| Tool | Description |
|------|-------------|
| `run_phase2` | Load universe and NSE data; compute returns, RS, RSI, technical score; merge fundamentals. Writes `phase2_universe_metrics.csv`. |
| `run_phase3` | Build composite score, apply screens (FUND≥70, RS_6M>0), shortlist top 15. Writes `phase3_shortlist.csv`, `phase3_full_with_composite.csv`. |
| `run_phase4` | Backtest: monthly rebalance, momentum screen, forward 1Y vs Nifty 500. Writes `phase4_backtest_results.csv`. |
| `run_phase5` | Generate sector note (Markdown) and HTML dashboard. Writes `sector_note.md`, `dashboard.html`. |
| `run_full_pipeline` | Run Phase 2 → 3 → 4 → 5 in order (recommended for “run everything”). |
| `run_narratives` | Generate per-stock narratives (Ollama) from Phase 3 table; writes `stock_narratives.md` and `.json`. |
| `web_search` | Single web search (duckduckgo/google/bing) for market size, news, reports. |
| `web_search_iterative` | Multi-round search with Ollama-suggested follow-up queries; use for deeper sector research. |
| `list_outputs` | List current sector output files with sizes/row counts. |
| `get_phase_help` | Return a short description of each phase, full pipeline, narratives, and web search. |

## Example prompts

- “Run the full pipeline.”
- “Run only Phase 2 and Phase 3.”
- “What does each phase do?” (uses `get_phase_help`)
- “What output files do I have?” (uses `list_outputs`)
- “Run Phase 2, then list the outputs.”

## Configuration

- **Model:** Default is `granite4:latest`. Override with:
  ```bash
  export OLLAMA_MODEL=granite4:3b
  python working-sector/agent.py
  ```
- **Pipeline config:** Same as the rest of the project: edit `working-sector/config.py` for universe, paths, screen thresholds, backtest params, etc.

## Files

| File | Purpose |
|------|---------|
| `agent_cli.py` | **CLI:** `--sector`, `--run-all`, `--interactive`; runs pipeline + narratives and/or starts the agent. |
| `agent.py` | Main agent loop: user input → Ollama chat with tools → execute tool calls → print reply. |
| `pipeline_tools.py` | Defines the tools (phases, pipeline, narratives, web_search, web_search_iterative, list_outputs, get_phase_help). |
| `web_search.py` | Standalone script: multiple engines (DuckDuckGo, Google, Bing) and iterative search. See **WEB_SEARCH_README.md**. |
| `config.py` | Sector from `NSE_SECTOR`; paths (universe, output dir) are sector-aware. |
| `AGENT_README.md` | This file. |

## Requirements

- **Ollama** running (e.g. `ollama serve`).
- **Granite4** (or another tool-calling model) pulled: `ollama pull granite4`.
- **Python:** `ollama`, `pandas`, `numpy`. Pipeline inputs (universe CSV, NSE data, fundamentals) must be present as for the normal pipeline (see `PIPELINE_README.md`).

## Troubleshooting

- **“Connection refused” to Ollama:** Start the server: `ollama serve`.
- **“Model not found”:** Run `ollama pull granite4`.
- **Tool not executed / model doesn’t call tools:** Try a model that supports tool calling (e.g. Granite4, Qwen3, Llama 3.1). You can set `OLLAMA_MODEL` to another model name.
- **Phase fails (e.g. missing CSV):** Ensure NSE data and universe are set up as in `PIPELINE_README.md`; run the pipeline once without the agent to confirm.
