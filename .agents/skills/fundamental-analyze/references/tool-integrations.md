# Tool integrations

Gather facts with repository Python helpers from the project root, then render with the bounded MCP tool. Do not treat Screener or the snapshot as a substitute for the primary filing.

## Fact gathering (local Python, not MCP)

Run from the repository root with `.venv/bin/python`. These functions are the source of prices, filings links, and Screener history; copy only figures you can reconcile to a filing.

```python
from terminal.tools import resolve_symbol, get_symbol_snapshot
from terminal.search_engine import search_nse_announcements
from terminal.web_research import scrape_screener_in

resolve_symbol("Elgi Equipments")           # name → NSE symbol
get_symbol_snapshot("ELGIEQUIP")            # as-of EOD price, sector, snapshot date
search_nse_announcements("ELGIEQUIP")       # result/presentation/annual-report URLs
scrape_screener_in("ELGIEQUIP")              # ratios, annuals, quarters, shareholding, peers
```

Optional cross-check files (never newer than the filing):

- `data/fundamental_scores_database.csv`
- `core/fundamental_scores_database.csv`

Open each filing URL from `search_nse_announcements` (or the company IR page) and transcribe numbers into the input JSON. Use Screener to fill history and to flag mismatches; if Screener and the filing disagree, keep the filing and record the conflict.

## Report rendering (MCP or CLI)

The repository exposes four bounded tools through Agent Adda and the shared stdio MCP server:

- `render_fundamental_analysis_report`: validate and render a sourced dataset.
- `list_agent_adda_skills`: inspect runtime cards and static contracts.
- `find_agent_adda_skills`: retrieve runtime cards and log retrieval telemetry.
- `execute_agent_adda_skill`: execute a validated/production card, validate its evidence, and log execution telemetry.

Cursor reads `.cursor/mcp.json`, Claude Code reads `.mcp.json`, and VS Code/GitHub Copilot reads `.vscode/mcp.json`. Each launches `integrations/agent_adda_mcp/server.py` with the project virtual environment. Keep the MCP allowlist bounded; do not expose the complete financial tool registry without a separate security review.
