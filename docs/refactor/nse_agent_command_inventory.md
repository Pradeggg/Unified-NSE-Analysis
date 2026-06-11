# `nse_agent.py` Refactor Command Inventory

Date: 2026-06-10

Scope: AA-AR-13 safety harness for incremental `nse_agent.py` refactoring.

The current `nse_agent.py` file is both a terminal app and a command/workflow host. This inventory freezes the command surface before extraction so later refactors can prove they preserved behavior.

## Shared Registry Commands

These handlers are registered by `nse_agent._build_command_registry()` and are available in both interactive and `--query` single-query mode unless noted.

| Handler | Modes | Description |
|---|---|---|
| `help` | interactive, single_query | Slash-command help |
| `commands` | interactive, single_query | Search or list available commands |
| `scan` | interactive, single_query | Intraday screener |
| `strategy-council` | interactive, single_query | Multi-agent strategy council deliberation |
| `council` | interactive, single_query | Research Council orchestration |
| `backtest` | interactive, single_query | Backtest or strategy-lab run |
| `data-coverage` | interactive, single_query | Data coverage report |
| `open-last-report` | interactive, single_query | Open the most-recently generated report |
| `visual-scan` | interactive, single_query | Grounded EOD chart-pattern visual scan |
| `doctor` | interactive, single_query | PostgreSQL connectivity and readiness check |
| `mtf` | interactive, single_query | Multi-timeframe analysis |
| `strength` | interactive, single_query | Relative-strength watchlist validator |
| `diagnose` | interactive, single_query | Financial metric driver diagnosis |
| `skills` | interactive, single_query | Inspect Skill Store cards, status counts, and recent activity |
| `report-diagnosis` | interactive, single_query | Fundamental driver diagnosis report |
| `email` | interactive, single_query | First-class report mailer |
| `swing-playbook` | interactive, single_query | Swing trading playbook report |
| `interaction` | interactive, single_query | `/style`, `/verbosity`, `/steps` interaction profile |
| `copilot-workflows` | interactive, single_query | `/brainstorm`, `/plan`, `/debug`, `/review`, `/verify` copilot workflows |
| `quality-breakouts` | interactive, single_query | Composite breakout screener with fundamental quality overlay |
| `my-portfolio` | interactive, single_query | Live intraday P&L and portfolio signals |

Regression anchor: `tests/test_command_registry_inventory.py`.

## Interactive-Only Branches Still In `nse_agent.py`

These commands are still handled directly inside or around `_chat_loop()` and should be migrated only after registry coverage and smoke tests exist.

| Family | Command prefixes | Current responsibility | Suggested target |
|---|---|---|---|
| Model/session | `/model`, `/new`, `/clear` | Backend selection and session reset | `terminal/commands/session.py` |
| Help/catalog | `/help`, `/commands`, `/prompts` | Help output and prompt library | `terminal/commands/help.py` |
| Monitor/alerts | `/monitor-report`, `/monitor`, `/alert` | Monitor lifecycle, event render, auto-display | `terminal/commands/monitor.py` |
| RIC workflows | `/ric` | Recipe listing and multi-step recipe execution | `terminal/workflows/ric.py` |
| Data refresh/status | `/refresh`, `/data-status`, `/refresh-data` | Data refresh orchestration and readiness | `terminal/commands/data.py` |
| Report/export | `/export`, `/report`, `/reports`, `/open`, `/critique-report` | Report generation, registry, open/export, critique | `terminal/commands/reports.py` |
| Global/market views | `/global`, `/heat`, `/cycle`, dashboard helpers | Market/global dashboards and heat/cycle views | `terminal/dashboard/` |
| Screeners/charts | `/scan`, `/screen`, `/chart`, `/visual-scan` | Screener parsing, chart/report rendering | `terminal/commands/screeners.py` |
| Company research | `/company-index`, `/company-xray`, `/search`, `/analyze`, `/canslim`, `/forensic`, `/concall`, `/kb` | Company research workflows and KB access | `terminal/commands/research.py` |
| Voice | `/voice-mode`, `/voice-live`, `/voice`, `/ask-voice` | Voice state, STT/TTS, voice briefing | `terminal/commands/voice.py` |
| Events/F&O | `/events`, `/options`, `/chain`, `/oi`, `/fno` | Corporate event and derivatives views | `terminal/commands/derivatives.py` |
| Portfolio/strategy | `/strategy`, `/recap`, `/pnl`, `/my-portfolio` | Portfolio/paper-trading/strategy views | `terminal/commands/portfolio.py` |
| UI preferences | `/theme`, `/scale`, `/style`, `/verbosity`, `/steps` | Terminal appearance and interaction profile | `terminal/ui/preferences.py` |

## Extraction Order

1. Add tests and inventory first.
2. Extract pure UI rendering helpers with compatibility wrappers.
3. Extract prompt session, completer, toolbar, and preferences.
4. Convert remaining slash commands to registry-backed dispatch.
5. Move command families one at a time.
6. Move dashboard runtime into `terminal/dashboard/`.
7. Thin `nse_agent.py` to an entrypoint shim.
8. Split `terminal/agent.py` pipeline internals after the CLI shell is stable.

## Regression Smoke Matrix

Run the narrow smoke set after each extraction slice:

```bash
.venv/bin/python -m pytest tests/test_command_registry_inventory.py tests/test_nse_agent_interaction_commands.py tests/test_nse_agent_monitor_scan.py -q
.venv/bin/python nse_agent.py --no-briefing --skip-readiness -q "/help"
.venv/bin/python nse_agent.py --no-briefing --skip-readiness -q "how does NIFTY500 look like"
```

Before thinning `nse_agent.py`, also run the broader agent/rendering set:

```bash
.venv/bin/python -m pytest tests/test_terminal_agent_market_prompt.py tests/test_renderers.py tests/test_on_demand_stock_data.py tests/test_semantic_intent.py -q
```

