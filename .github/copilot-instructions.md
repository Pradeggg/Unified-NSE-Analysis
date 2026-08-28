# Agent Adda finance tools

Use the `agent-adda` MCP server for fundamental-report rendering and Skill Store discovery or execution.

- Call `render_fundamental_analysis_report` only with sourced data following `.agents/skills/fundamental-analyze/references/input-schema.md`.
- Gather filings, Screener history, and prices with the repository helpers in `.agents/skills/fundamental-analyze/references/tool-integrations.md` before rendering.
- Call `find_agent_adda_skills` before `execute_agent_adda_skill` when the appropriate runtime skill is not already explicit.
- Execute only validated or production cards. Preserve evidence-validation errors and stale-data warnings.
- Do not describe Stage 2 momentum candidates as 52-week highs unless separate 52-week-high evidence exists.
- Treat outputs as research, not personalized investment advice.
- For publishing/posting Agent Adda reports to `agentadda.in` and notifying recipients, follow `.github/instructions/agent-adda-publish-intelligence-report.instructions.md` and `.agents/skills/agent-adda-publish-intelligence-report/SKILL.md`.

## Command Centre — discovering capabilities

Three surfaces index all 52 Agent Adda commands (skills, screeners, reports, pipeline, admin):

| Surface | How to open | Best for |
|---------|-------------|----------|
| Browser palette | `open reports/latest/launcher.html` | ⌘K fuzzy search, copy CLI |
| Terminal TUI | `python tools/command_center.py` | Arrow-key nav, run in subshell |
| REPL completion | `python nse_agent.py` then `/` Tab | Inline while chatting |

Every chart HTML (`reports/latest/charts/*.html`) also has ⌘K built in.

Rebuild catalogue after adding new skills: `python scripts/build_launcher.py`

### Key command-centre files

- `scripts/build_launcher.py` — catalogue generator
- `reports/latest/launcher.html` — browser palette
- `tools/command_center.py` — Rich TUI (`--list` dumps JSON, `--run <id>` runs directly)
- `nse_agent.py` `_AgentCompleter` — REPL tab completion (prompt_toolkit)

### Routing shortcuts

- "show me all tools" → `python tools/command_center.py`
- "open command palette" → `open reports/latest/launcher.html`
- "rebuild skill index" → `python scripts/build_launcher.py`
- "run a specific skill" → `python tools/command_center.py --run <skill_id> [SYMBOL]`
