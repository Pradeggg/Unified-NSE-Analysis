---
name: command-centre
description: >-
  Agent Adda Command Centre — discover, search, and launch any skill, screener,
  or pipeline command. Use when the user asks to find a tool, browse skills,
  open the command palette, or launch any Agent Adda capability by name.
---

# Agent Adda Command Centre

Three surfaces for discovering and launching every Agent Adda capability:

| Surface | Where | How to open |
|---------|-------|-------------|
| Browser Command Palette | `reports/latest/launcher.html` | `open reports/latest/launcher.html` |
| Terminal TUI | `tools/command_center.py` | `python tools/command_center.py` |
| REPL Tab Completion | Built into `nse_agent.py` | Start REPL, type `/` then Tab |

All commands are indexed across three sources: skill YAMLs in `skill_store/stored/`, REPL slash-commands, and pipeline scripts.

---

## Browser Command Palette (`launcher.html`)

```bash
# Open the hub
open reports/latest/launcher.html

# Rebuild after adding new skills
python scripts/build_launcher.py
```

**Usage:**
- ⌘K / Ctrl+K — focus search from anywhere
- Type to fuzzy-search across id, description, tags, input patterns
- Click 📋 next to any CLI command to copy it
- ↑↓ keys + Enter to copy the highlighted command
- Esc — clear search
- Category tabs: All | Skills | Screeners | Reports | Admin | REPL

**Every HTML chart** also has ⌘K built in — opens the same palette inline.

---

## Terminal TUI (`tools/command_center.py`)

```bash
# Interactive TUI — arrow keys + search
python tools/command_center.py

# Dump full catalogue as JSON (52 commands)
python tools/command_center.py --list

# Run a specific skill directly
python tools/command_center.py --run equity_chart_v1 RELIANCE
python tools/command_center.py --run intraday_alerts
python tools/command_center.py --run /dashboard
```

**TUI keyboard shortcuts:**
- ↑↓ — navigate command list
- Tab — cycle category (All → Skills → Screeners → Reports → Pipeline → Admin)
- `/` — enter search mode
- Enter — copy CLI, prompt for SYMBOL if needed, run in subshell
- Esc — clear search
- q — quit

The TUI reads `skill_store/stored/*.yml` live on each run, so newly-added skills appear immediately without rebuilding.

---

## REPL Tab Completion (prompt_toolkit `_AgentCompleter`)

Already active when you run `python nse_agent.py`. No setup needed.

| What you type | What completes |
|--------------|----------------|
| `/` + Tab | All slash-commands with descriptions |
| `/chart` + Space + Tab | NSE symbols, indices |
| `/screen` + Space + Tab | stage2, momentum, highrs, vcp, base, tight, dip… |
| `/scan` + Space + Tab | orb, gap, macd, rsi, bb, vwap, vcp, momentum |
| `/email` + Space + Tab | Targets + flags (--to, --bcc, --send, --dry-run…) |
| `p` + Tab | All 60+ prompt-library entries |
| `p42` + Tab | Jump directly to prompt #42 |
| Free text + Tab | NSE symbols, starter phrases |
| ↑ / ↓ history | AutoSuggest from session history (grey ghost) |

---

## Catalogue size

52 commands across:
- **16 Skills** — `/chart`, `/xray`, `/options`, `/mtf`, `/ric`, `/strategy_council`, screeners, regime, RS…
- **11 Pipeline** — daily_refresh phases, bhavcopy loader, PG loader, VCP materialiser, R scripts
- **11 Reports** — dashboard, voice, email, sector rotation, fund dashboard, top picks, strategy lab…
- **10 Admin** — pg start/stop/status, doctor, backfills, MCP server, ollama pull
- **4 Screeners** — stage2_vcp, intraday_alerts, universe_scoring, market_breadth

---

## Rebuild catalogue

```bash
# Re-index after adding new skill cards, screeners, or pipeline steps
python scripts/build_launcher.py
# → reports/latest/launcher.html  (browser palette)
# → reports/latest/launcher_data.json  (shared JSON catalogue)
```

---

## Key files

| File | Role |
|------|------|
| `scripts/build_launcher.py` | Catalogue generator — scrapes YAMLs + hardcoded lists |
| `reports/latest/launcher.html` | Self-contained browser command palette (20 KB) |
| `reports/latest/launcher_data.json` | Shared JSON catalogue |
| `tools/command_center.py` | Rich TUI command browser |
| `terminal/chart_engine.py` | Every chart HTML carries ⌘K palette inline |
| `nse_agent.py` | REPL with `_AgentCompleter` (prompt_toolkit) |

---

## Guardrail

All outputs are for research purposes only — not investment advice.
