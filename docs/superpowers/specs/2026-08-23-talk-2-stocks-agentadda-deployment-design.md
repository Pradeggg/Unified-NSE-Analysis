# Talk 2 Stocks AgentAdda Deployment Design

Date: 2026-08-23
Owner: Agent Adda / Codex
Status: MVP deployment design
Scope: 10-user closed beta under Agent Adda

## Decision

Talk 2 Stocks ships as an Agent Adda-branded surface, not a standalone product.

The MVP deployment should use a split architecture:

1. AgentAdda.in serves the public/static product shell.
2. `Unified-NSE-Analysis` runs the FastAPI research API.
3. Existing Agent Adda data refresh jobs keep market evidence current.
4. Access is restricted to 10 approved beta users.

This matches the repo's current shape: `agentadda/www` already hosts static pages and reports, while `agent_adda/web_api` exposes the local research API.

## MVP URLs

Recommended beta URLs:

```text
https://agentadda.in/talk-2-stocks
https://api.agentadda.in/api/talk/chat
https://api.agentadda.in/api/talk/compare
https://api.agentadda.in/api/talk/defaults
https://api.agentadda.in/api/health
```

Local development URLs:

```text
http://127.0.0.1:8765/talk-2-stocks
http://127.0.0.1:8765/api/talk/chat
```

## Deployment Phases

### Phase 0: Local MVP

Purpose:

- prove the chat loop end to end
- keep all data local
- avoid auth, billing, and public API exposure while the workflow stabilizes

Runtime:

```text
python -m agent_adda.web_api.main
```

Local app:

```text
agent_adda/web_api/static/talk_2_stocks.html
```

Required endpoints:

- `GET /talk-2-stocks`
- `POST /api/talk/chat`
- `POST /api/talk/compare`
- `GET /api/talk/defaults`
- `GET /api/health`

Acceptance:

- chat answers stock questions with evidence and gaps
- compare handles 2-3 symbols
- watchlist is stored in browser local storage
- missing evidence is visible
- no brokerage or trade execution features exist

### Phase 1: Private AgentAdda Beta

Purpose:

- expose the MVP to 10 users without making the API generally public
- preserve local Agent Adda data and scheduled refresh jobs

Recommended topology:

```text
agentadda.in/talk-2-stocks
  -> static shell in agentadda/www

api.agentadda.in
  -> HTTPS reverse proxy or tunnel
  -> FastAPI app on 127.0.0.1:8765
  -> local/Postgres Agent Adda evidence store
```

Access control:

- invite-only allowlist of 10 users
- require email-based access gate before loading the app
- keep API behind the same gate
- add per-user daily query limits

Recommended beta guardrails:

- `LLM_ROUTER_MODEL=gpt-5-nano`
- `LLM_DEFAULT_MODEL=gpt-4o-mini`
- permissive evidence mode by default
- max 20 chat calls per user per day until cost logs are proven
- no paid public subscriptions until cost telemetry is verified

### Phase 2: Production AgentAdda Surface

Purpose:

- move from founder-operated beta to a durable product surface

Target topology:

```text
Cloud/CDN static frontend
  -> AgentAdda.in shell, reports, docs, onboarding

API runtime
  -> FastAPI container or service
  -> /api/talk/*
  -> /api/chart/*
  -> /api/ric/*

Data runtime
  -> managed PostgreSQL or hardened self-hosted PostgreSQL
  -> daily market refresh worker
  -> intraday capture worker
  -> report generation worker

Ops runtime
  -> request logs
  -> token/cost ledger
  -> error monitoring
  -> backup jobs
```

## Frontend Deployment

There are two acceptable frontend paths.

### MVP Path: Static HTML Shell

Use the committed local HTML shell:

```text
agent_adda/web_api/static/talk_2_stocks.html
```

For AgentAdda.in beta, copy or port this shell into `agentadda/www` as:

```text
app/talk-2-stocks/page.tsx
```

or serve it as a static page if the current website build supports static assets.

The shell should call:

```text
NEXT_PUBLIC_AGENTADDA_API_BASE=https://api.agentadda.in
```

### Later Path: React/Vite or Next.js Surface

Once the chat loop is proven, replace the static HTML shell with a first-class AgentAdda.in page that keeps the same API contract.

Do not move market logic into the frontend. The frontend remains a client.

## Backend Deployment

The FastAPI app is the product API:

```text
agent_adda/web_api/main.py
```

Minimum service command:

```text
uvicorn agent_adda.web_api.main:app --host 127.0.0.1 --port 8765
```

Public traffic should terminate at HTTPS, then proxy to local Uvicorn.

Recommended service environment:

```text
AGENT_ADDA_WEB_PORT=8765
AGENT_ADDA_SKIP_VENV_CHECK=1
PG_DSN=...
OPENAI_API_KEY=...
LLM_ROUTER_PROVIDER=openai
LLM_ROUTER_MODEL=gpt-5-nano
LLM_DEFAULT_PROVIDER=openai
LLM_DEFAULT_MODEL=gpt-4o-mini
TALK2STOCKS_BETA_MODE=1
TALK2STOCKS_DAILY_QUERY_LIMIT=20
TALK2STOCKS_ALLOWED_USERS=user1@example.com,user2@example.com
```

The API process loads `Unified-NSE-Analysis/.env` first and the parent finance workspace `.env` second, using only missing values. For local MVP, this allows `OPENAI_API_KEY` to live in the shared workspace `.env` while repo-specific mail, database, or deployment values stay in the repo `.env`.

### MVP Engine Runtime Contract

The deployed API should run Talk 2 Stocks as a bounded Agent Adda engine, not as an unconstrained LLM chat endpoint.

Current local route:

```text
POST /api/talk/chat
 -> resolve symbols
 -> infer lightweight intent
 -> gather fixed evidence
 -> build deterministic fallback
 -> synthesize with gpt-4o-mini when OPENAI_API_KEY is configured
 -> return structured response
```

Target closed-beta route:

```text
TalkTurnState
 -> gpt-5-nano JSON router
 -> validated intent
 -> fixed tool plan
 -> Agent Adda tool execution
 -> gpt-4o-mini synthesis
 -> evidence/gap/cost response
 -> persisted audit trail
```

Runtime requirements:

- keep `LLM_ROUTER_MODEL` and `LLM_DEFAULT_MODEL` environment-configurable
- use LLM synthesis as the preferred MVP answer path
- validate router JSON before tool execution
- execute only fixed server-side tool plans
- preserve deterministic fallback answers when LLM synthesis fails
- return explicit evidence gaps in every answer
- persist turn state before the external 10-user beta
- log user/session, model route, token counts, cost, intent, symbols, gaps, and errors

Initial allowed MVP intents:

```text
stock_deep_dive
compare
market_context
watchlist
financials_review
evidence_review
advice_boundary
clarification
general_research
```

Initial web tool surface:

```text
resolve_symbol
get_symbol_snapshot
get_technical_setup
get_cached_financials
data/sector_breadth.csv
```

Next tool additions should be gated behind fixed plans:

```text
compare_stocks
get_market_breadth
get_index_snapshot
get_live_market_overview
get_sector_context
get_cached_financials
get_latest_results
search_nse_announcements
search_bse_filings
run_screener_query
```

## Data Deployment

MVP reads existing Agent Adda evidence:

- PostgreSQL stage snapshots
- EOD price history
- technical setup calculations
- `data/sector_breadth.csv`
- local report artifacts

The API must surface gaps rather than failing the full answer when optional evidence is unavailable.

Current T2S read path:

```text
/api/talk/chat
 -> load session context when session_id exists
 -> bind pronouns such as "it" to prior symbols
 -> terminal.tools.get_symbol_snapshot
    -> PostgreSQL scores.stage_snapshots
    -> optional technical-only on-demand backfill
 -> terminal.tools.get_technical_setup
    -> PostgreSQL market.equity_eod
    -> PostgreSQL on_demand.eod_price_history
    -> CSV/yfinance fallback when needed
 -> terminal.tools.get_cached_financials for financial follow-ups
    -> PostgreSQL financial statement cache
 -> data/sector_breadth.csv for current web sector context
```

The API service should not duplicate SQL logic in the route layer. Routes should call bounded Agent Adda tools, normalize their output into evidence/gaps, and persist the Talk 2 Stocks turn audit separately.

Recommended production-beta persistence:

```text
talk.sessions
talk.turns
talk.tool_runs
talk.evidence_items
talk.cost_ledger
```

These tables are for chat/session observability, quota, follow-up context, and cost control. They do not replace `scores.stage_snapshots`, `market.equity_eod`, `on_demand.eod_price_history`, or existing Agent Adda evidence stores.

Scheduled jobs stay separate from the API:

- daily EOD refresh
- sector breadth refresh
- intraday capture
- report generation

For public production, all scheduled jobs need health checks and last-success timestamps visible in an admin view.

## Auth and Beta Access

MVP options, in order:

1. Cloud/email access gate in front of `agentadda.in/talk-2-stocks` and `api.agentadda.in`.
2. Simple server-side shared beta token for the first internal test.
3. Full Agent Adda account login later.

Do not ship a public unauthenticated API for the MVP.

The API should eventually receive:

```text
X-AgentAdda-User: beta-user-id
X-AgentAdda-Session: browser-session-id
```

The first version may use anonymous browser sessions locally, but production beta should identify users for quota and cost logs.

## Cost Controls

Required before 10-user external beta:

- log model route per request
- log prompt and completion token counts
- estimate cost per request
- daily per-user query limit
- monthly product spend cap
- fallback to deterministic answer if LLM call fails

Current MVP route already returns:

- `model_route`
- `input_tokens`
- `output_tokens`
- `cost_usd`
- `gaps`
- `evidence`

These should be persisted before paid beta.

## CI and Release Flow

API release:

1. run Python tests
2. run API smoke checks
3. deploy FastAPI service
4. verify `/api/health`
5. verify `/api/talk/chat`

Frontend release:

1. build AgentAdda.in page
2. point API base to beta API
3. deploy `agentadda/www`
4. verify `/talk-2-stocks`

Reports remain on the existing path:

```text
scripts/push_to_www.py
```

That script publishes static reports. It is not enough to deploy the interactive Talk 2 Stocks API.

## Rollback

Frontend rollback:

- hide `/talk-2-stocks` from navigation
- keep static reports live

API rollback:

- stop public proxy to FastAPI
- keep local API available for internal testing
- disable LLM calls by unsetting `OPENAI_API_KEY`

Data rollback:

- keep scheduled refresh jobs independent of Talk 2 Stocks
- do not let a Talk 2 Stocks deploy block EOD report generation

## MVP Exit Criteria

The deployment is beta-ready when:

- 10 named users can access the AgentAdda-branded page
- unauthenticated users cannot call the API
- chat, compare, and watchlist workflows work from the hosted page
- evidence gaps are visible in every answer
- token/cost logging is captured for each LLM request
- the API can fall back to deterministic answers when the LLM is unavailable
- daily refresh jobs have a visible freshness timestamp
- research-only disclaimer is present in the UI
