# Agent Adda finance tools

Use the `agent-adda` MCP server for fundamental-report rendering and Skill Store discovery or execution.

- Call `render_fundamental_analysis_report` only with sourced data following `.agents/skills/fundamental-analyze/references/input-schema.md`.
- Gather filings, Screener history, and prices with the repository helpers in `.agents/skills/fundamental-analyze/references/tool-integrations.md` before rendering.
- Call `find_agent_adda_skills` before `execute_agent_adda_skill` when the appropriate runtime skill is not already explicit.
- Execute only validated or production cards. Preserve evidence-validation errors and stale-data warnings.
- Do not describe Stage 2 momentum candidates as 52-week highs unless separate 52-week-high evidence exists.
- Treat outputs as research, not personalized investment advice.
