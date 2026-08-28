# AgentAdda.in Product Cost Sheet Assessment

Date: 2026-08-23  
Prepared for: Agent Adda / Talk 2 Stocks product review  
Purpose: subscription pricing, cost-to-serve, breakeven, and 20% operating-profit assessment  
Status: working model for team review; not a vendor quote

## Executive Summary

AgentAdda.in can support a paid subscription model for 100 users if the product is operated as a tool-first research platform and the LLM layer is routed by task.

The core conclusion:

- Do not run routine user traffic on legacy `GPT-4`, `GPT-4 Turbo`, or default `GPT-4o`.
- Use `GPT-5 nano` or `GPT-4o mini` for routing, JSON extraction, alert parsing, and low-risk summaries.
- Use `GPT-4o mini` as the low-cost default answer model if the priority is subscription margin.
- Use `GPT-5.6 Luna` for better synthesis and deep research only where the product tier justifies it.
- Use `GPT-5.6 Terra` only for premium deep-research workflows, not everyday chat.
- Keep DeepSeek V4 Flash as an optional batch/offline report fallback.
- Keep Sarvam for Indic language, speech, and India-local UX, not as the default core reasoning engine.

For a 100-user paid beta, the safer price ladder is:

| Plan | Suggested price / month | Primary audience | Commercial logic |
|---|---:|---|---|
| Free Trial | ₹0 | acquisition | strict cap; no deep reports |
| Starter | ₹149 | light retail research | viable after fixed-cost allocation |
| Plus | ₹299 | active market users | recommended default plan |
| Pro | ₹799 | power users / portfolio users | supports deep research and alerts |
| Power | ₹1,499 | heavy users / advisors / teams | requires fair-use controls |

The earlier ₹99 Starter plan is technically possible if we look only at LLM token cost. It becomes weak once we include even modest fixed platform cost, support, observability, email, and payment overhead.

## Product Scope Covered

This assessment treats AgentAdda.in as the full product surface, not only Talk 2 Stocks chat.

Covered feature groups:

1. Web app and subscription access
2. Talk 2 Stocks natural-language assistant
3. Stock deep dive
4. Technical analysis and stage detection
5. Fundamental analysis and company research
6. Peer comparison
7. Sector rotation and index intelligence
8. Daily EOD and weekend market reports
9. Watchlists
10. Alerts and intraday monitoring
11. Portfolio assessment
12. Report export and sharing
13. Email delivery
14. Voice briefing and voice Q&A
15. Evidence trail, source validation, and report QA
16. Admin, logging, observability, and cost controls

## Key Assumptions

### Usage Assumption

Standard Talk 2 Stocks query:

- 10,000 input tokens
- 1,200 output tokens
- local tools retrieve market data before the LLM answer
- excludes web-search tool charges, market-data vendor charges, email, voice, and hosting

Trading month:

- 22 active market days

FX:

- ₹95.66 / USD

### Current API Pricing Snapshot

Pricing researched from official provider pricing pages on 2026-08-23.

| Model | Input / 1M tokens | Output / 1M tokens | Notes |
|---|---:|---:|---|
| OpenAI `gpt-5-nano` | $0.05 | $0.40 | lowest-cost OpenAI model for routing/classification |
| OpenAI `gpt-4o-mini` | $0.15 | $0.60 | strong low-cost default for focused tasks |
| OpenAI `gpt-5.6-luna` | $0.20 | $1.20 | better synthesis; still low cost |
| OpenAI `gpt-5.6-terra` | $2.00 | $12.00 | premium research only |
| OpenAI `gpt-4o` | $2.50 | $10.00 | expensive for routine traffic |
| OpenAI `gpt-4` | $30.00 | $60.00 | not viable for normal subscriptions |
| DeepSeek V4 Flash off-peak | $0.22 | $0.66 | attractive for batch/offline tasks |
| Sarvam 105B | ₹29.28 | ₹73.20 | useful for Indic-language layer |
| xAI Grok 4.6 | $2.00 | $6.00 | optional social/news experiments |

## Feature-Level Cost Classification

| Feature group | User value | Main cost drivers | Recommended model route | Cost risk |
|---|---|---|---|---|
| Landing + onboarding | conversion | hosting, auth, analytics | no LLM | Low |
| Talk 2 Stocks chat | core product | LLM tokens, DB reads | `gpt-4o-mini` default; `gpt-5-nano` for routing | Medium |
| Intent routing | invisible core UX | small JSON calls | `gpt-5-nano` | Low |
| Stock deep dive | high perceived value | LLM synthesis + data queries | `gpt-4o-mini`; Luna for Plus/Pro | Medium |
| Fundamental analysis | high value | filings, summaries, evidence context | Luna; Terra only for premium | Medium/High |
| Technical/stage analysis | high value | compute + chart rendering | deterministic first | Low |
| Peer comparison | high value | larger evidence pack | `gpt-4o-mini` or Luna | Medium |
| Sector/index intelligence | frequent usage | data refresh + synthesis | deterministic + `gpt-4o-mini` | Low/Medium |
| EOD/weekend reports | retention | batch generation + email | DeepSeek Flash or Luna batch | Medium |
| Watchlists | retention | DB, scheduled jobs | no LLM except summaries | Low |
| Alerts/intraday monitor | engagement | polling, email/SMS/push | LLM only for setup text | Medium |
| Portfolio assessment | monetizable | CSV import, analytics, report synthesis | Luna for Pro | Medium |
| Report export/share | team value | HTML generation, storage, email | deterministic + optional LLM cover note | Low/Medium |
| Email delivery | distribution | SMTP/API volume, bounce handling | no LLM required | Low |
| Voice briefing | premium UX | STT/TTS minutes/chars | Sarvam/OpenAI speech | Medium/High |
| Evidence trail/QA | trust | source storage, validation jobs | mostly deterministic | Low |
| Admin/cost dashboard | operating control | logs, DB, analytics | no LLM | Low |

## LLM Cost Per User

Pure LLM cost per user/month at 22 trading days:

| Model | 5 queries/day | 10 queries/day | 20 queries/day | 50 queries/day |
|---|---:|---:|---:|---:|
| `gpt-5-nano` | ₹10 | ₹21 | ₹41 | ₹103 |
| `gpt-4o-mini` | ₹23 | ₹47 | ₹93 | ₹234 |
| `gpt-5.6-luna` | ₹36 | ₹72 | ₹145 | ₹362 |
| `gpt-4o` | ₹389 | ₹779 | ₹1,557 | ₹3,893 |
| `gpt-4` | ₹4,092 | ₹8,184 | ₹16,368 | ₹40,920 |

Implication:

- `gpt-4o-mini` can be used for low-cost everyday answers.
- `gpt-5-nano` is cheaper than `gpt-4o-mini`, but should be used where quality risk is acceptable.
- `gpt-4o` destroys entry-tier economics.
- `gpt-4` is not a subscription model option for routine use.

## Proposed Subscription Tiers

| Plan | Price / month | Included usage | Feature access | Model policy | Estimated variable COGS/user |
|---|---:|---|---|---|---:|
| Free Trial | ₹0 | 3 queries/day, 1 watchlist, delayed reports | basic chat, limited sector view | mostly `gpt-5-nano` | ₹6 |
| Starter | ₹149 | 10 queries/day, 2 watchlists, basic alerts | stock Q&A, sector/index summary, limited reports | 80% nano / 20% `gpt-4o-mini` | ₹30 |
| Plus | ₹299 | 20 queries/day, 5 watchlists, 5 deep dives/month | compare, portfolio-lite, EOD/weekend reports | nano + `gpt-4o-mini` + limited Luna | ₹90 |
| Pro | ₹799 | 50 queries/day, 15 watchlists, 25 deep dives/month | portfolio assessment, alerts, report export, email | `gpt-4o-mini` + Luna; premium gated | ₹280 |
| Power | ₹1,499 | fair-use high quota, team/report workflows | bulk reports, advanced alerts, priority jobs | Luna + limited Terra | ₹650 |

Variable COGS includes estimated LLM, email/report storage allowance, and modest per-user infra overhead. It excludes licensed market data and human research/support.

## 100-User Base Case

Recommended early paid mix:

| Plan | Users | Price | Revenue | Variable COGS/user | Total variable COGS | Contribution |
|---|---:|---:|---:|---:|---:|---:|
| Starter | 50 | ₹149 | ₹7,450 | ₹30 | ₹1,500 | ₹5,950 |
| Plus | 35 | ₹299 | ₹10,465 | ₹90 | ₹3,150 | ₹7,315 |
| Pro | 12 | ₹799 | ₹9,588 | ₹280 | ₹3,360 | ₹6,228 |
| Power | 3 | ₹1,499 | ₹4,497 | ₹650 | ₹1,950 | ₹2,547 |
| Total | 100 |  | ₹32,000 |  | ₹9,960 | ₹22,040 |

### Fixed Monthly Cost Assumption

Lean paid beta fixed platform cost:

| Cost bucket | Monthly estimate | Notes |
|---|---:|---|
| Hosting / app runtime / CDN | ₹2,000 | Cloudflare/Vercel-style lean deployment |
| PostgreSQL / storage / backups | ₹3,000 | small production DB + backups |
| Monitoring / logs / analytics | ₹1,500 | lightweight observability |
| Email infrastructure | ₹1,000 | SMTP/API, bounce handling, domain hygiene |
| Domain / security / misc | ₹500 | amortized |
| Support / content ops reserve | ₹7,000 | lean founder-led support |
| Total fixed cost | ₹15,000 | excludes market-data vendor license |

### Current Deployment Architecture Cost Mapping

The current AgentAdda deployment is a split architecture, not a single monolith.

| Layer | Current evidence in repo | Current role | Cost treatment in original model |
|---|---|---|---|
| Public website / reports frontend | `agentadda-www/wrangler.jsonc`, `agentadda-www/package.json` | Next.js static/export-style site deployed through Cloudflare Worker assets | Included only as generic Hosting/CDN |
| Static report hosting | `agentadda-www/public/reports/` | HTML reports copied into public site and served as static assets | Included only as generic hosting/storage |
| FastAPI backend | `agent_adda/web_api/main.py` | Local API on `127.0.0.1:8765` for Talk 2 Stocks, charting, RIC, F&O, backtest routes | Not explicitly included as production service |
| PostgreSQL | `postgres/`, `postgres/start_pg.sh`, `installer/*postgres*` | Local NSE market database and analytics store | Included only as generic PostgreSQL/storage |
| Daily refresh jobs | `installer/systemd/agentadda-daily-refresh.service/timer` | Weekday EOD refresh at 16:15 IST | Included only as generic app/ops cost |
| Intraday capture | `installer/systemd/agentadda-intraday-capture.service` | Always-on quote tape capture | Included only generically; real cost depends on data source/license |
| Email/report delivery | `terminal/email_dispatcher.py`, `/email` commands | Report delivery and alert distribution | Included only as generic email infrastructure |

Conclusion: the first version included hosting, database, email, and monitoring costs as broad buckets, but it did not make the Cloudflare + FastAPI + Postgres + worker architecture visible enough for team review. The workbook now includes a dedicated `Deployment Costs` tab.

### Architecture-Level Cost View

Recommended paid-beta deployment budget:

| Component | Current / target architecture | Lean beta estimate | Production estimate | Notes |
|---|---|---:|---:|---|
| Cloudflare Worker/static frontend | Current `agentadda-www` deployment | ₹500 | ₹2,500 | Cloudflare Workers paid plan starts at $5/month; low traffic can stay near base |
| Static report/object storage | Public HTML reports; optional R2 later | ₹0 | ₹500 | R2 has a free monthly allowance; reports are small initially |
| FastAPI backend | Needs production service for interactive Talk 2 Stocks | ₹700 | ₹3,000 | Current FastAPI is local-only; deploy via Render/Fly/Railway/VPS/container |
| Managed PostgreSQL | Production replacement for local PG | ₹1,500 | ₹5,000 | Size depends on historical bars, intraday capture, backups |
| Background workers / schedulers | Daily refresh, intraday capture, alerts | ₹1,500 | ₹6,000 | Can share backend initially; separate worker when alerts scale |
| Monitoring/logging | App logs, errors, uptime, cost ledger | ₹500 | ₹2,000 | Required before subscriptions |
| Email infrastructure | SMTP/API provider, deliverability | ₹500 | ₹2,000 | Depends on alert/report volume |
| Backup/storage reserve | DB snapshots, report artifacts | ₹500 | ₹1,500 | Needed for portfolio/history features |
| Support/content ops reserve | Manual QA and support | ₹5,000 | ₹10,000 | Still the largest lean-beta fixed cost |
| Market data licensing | Vendor/exchange-compliant public market data | excluded | vendor quote | This can dominate infra cost if real-time public features are sold |

For a 100-user paid beta, keep the fixed-cost planning number at ₹15,000/month. For a production-realistic public deployment with public FastAPI + managed Postgres + alert workers, use ₹25,000-₹40,000/month before market-data licensing.

### Base-Case P&L

| Metric | Amount |
|---|---:|
| Revenue | ₹32,000 |
| Variable COGS | ₹9,960 |
| Contribution after variable cost | ₹22,040 |
| Fixed cost | ₹15,000 |
| Operating profit before tax | ₹7,040 |
| Operating margin | 22.0% |

This clears a 20% operating-profit target under the assumed 100-user mix. The margin disappears if users are underpriced, if usage is uncapped, or if licensed real-time data is added without raising subscription price.

## Subscriber Growth, Breakeven, and Profitability

The base-case plan mix produces:

| Metric | Value |
|---|---:|
| Blended ARPU | ₹320/user/month |
| Blended variable COGS | ₹99.60/user/month |
| Blended contribution | ₹220.40/user/month |
| Contribution margin before fixed cost | 68.9% |

Subscriber thresholds:

| Fixed-cost case | Monthly fixed cost | Breakeven subscribers | Subscribers for 20% operating margin | Readout |
|---|---:|---:|---:|---|
| Lean beta | ₹15,000 | 69 | 96 | 100 users clears the 20% margin target |
| Production low | ₹25,000 | 114 | 160 | 100 users is loss-making; need ~160 users |
| Production high | ₹40,000 | 182 | 256 | need ~256 users before market-data licensing |

Growth curve under current price/mix:

| Subscribers | Lean beta profit / margin | Production low profit / margin | Production high profit / margin |
|---:|---:|---:|---:|
| 50 | -₹3,980 / -24.9% | -₹13,980 / -87.4% | -₹28,980 / -181.1% |
| 75 | ₹1,530 / 6.4% | -₹8,470 / -35.3% | -₹23,470 / -97.8% |
| 100 | ₹7,040 / 22.0% | -₹2,960 / -9.2% | -₹17,960 / -56.1% |
| 150 | ₹18,060 / 37.6% | ₹8,060 / 16.8% | -₹6,940 / -14.5% |
| 200 | ₹29,080 / 45.4% | ₹19,080 / 29.8% | ₹4,080 / 6.4% |
| 300 | ₹51,120 / 53.2% | ₹41,120 / 42.8% | ₹26,120 / 27.2% |
| 500 | ₹95,200 / 59.5% | ₹85,200 / 53.2% | ₹70,200 / 43.9% |

Commercial interpretation:

- At 100 users, the current plan mix is acceptable only as a lean beta.
- Once FastAPI, managed Postgres, workers, monitoring, and production ops are fully deployed, 100 users is not enough unless pricing or mix improves.
- The product becomes structurally healthy at ~200 users in a low-production-infra case.
- In a higher production-infra case, aim for at least 300 users or a higher ARPU before expanding expensive real-time features.
- The quickest profitability lever is not cutting LLM cost further; it is moving more users from Starter to Plus/Pro and keeping deep research/intraday alerts quota-based.

## Breakeven and 20% Profit Logic

Formula:

```text
Breakeven revenue = fixed cost + variable cost
20% operating-profit revenue = (fixed cost + variable cost) / 0.80
```

For the 100-user base mix:

```text
Variable cost = ₹9,960
Fixed cost = ₹15,000
Total cost = ₹24,960
20% margin revenue target = ₹31,200
Base-case revenue = ₹32,000
Headroom vs 20% margin target = ₹800
```

This is tight but acceptable for a paid beta. A safer production plan should target at least 30% gross headroom before adding licensed data, marketing, and support.

## Sensitivity View

### If all users are Starter at ₹149

| Metric | Amount |
|---|---:|
| Users | 100 |
| Revenue | ₹14,900 |
| Variable COGS | ~₹3,000 |
| Fixed cost | ₹15,000 |
| Profit / loss | -₹3,100 |

Conclusion: all-Starter composition does not cover a 100-user product unless fixed costs are much lower or support is unpaid.

### If all users are Plus at ₹299

| Metric | Amount |
|---|---:|
| Users | 100 |
| Revenue | ₹29,900 |
| Variable COGS | ~₹9,000 |
| Fixed cost | ₹15,000 |
| Profit / loss | ₹5,900 |
| Margin | 19.7% |

Conclusion: Plus-only is almost at the 20% target. Price at ₹349 or reduce fixed cost to clear the target more comfortably.

### If all users are Pro at ₹799

| Metric | Amount |
|---|---:|
| Users | 100 |
| Revenue | ₹79,900 |
| Variable COGS | ~₹28,000 |
| Fixed cost | ₹15,000 |
| Profit / loss | ₹36,900 |
| Margin | 46.2% |

Conclusion: Pro is commercially attractive, but only if deep research and alerts remain capped.

## Market Data and Compliance Caveat

The biggest unknown is not LLM cost. It is production-grade market data licensing and regulatory/compliance posture.

Operating modes:

| Mode | Data approach | Incremental monthly cost | Suitability |
|---|---|---:|---|
| Internal / research beta | existing local/public/derived data pipelines | ₹0-₹10k | internal testing and private beta |
| Community education product | delayed data, EOD reports, public filings | ₹10k-₹50k | likely initial public launch |
| Production real-time product | licensed feed/API, SLAs, vendor contract | vendor quote required; can be ₹50k+ to several lakh/month | requires repricing and legal review |

If the product offers real-time actionable alerts, the team should validate exchange/vendor data-license terms before scaling public subscriptions.

## Cost Controls Required Before Launch

Required controls:

1. Per-user monthly token ledger.
2. Per-plan hard usage quotas.
3. Model route logged on every answer.
4. Feature-level cost tags: chat, report, alert, portfolio, voice, email.
5. Deep-research quota separate from normal chat quota.
6. Evidence-pack size limits before LLM calls.
7. Cached standard system prompts.
8. Batch mode for nightly/weekend narratives.
9. Circuit breaker when monthly LLM spend crosses 70%, 90%, and 100% of budget.
10. Admin dashboard for user-level cost outliers.

## Recommended Launch Packaging

### MVP Paid Beta

Launch with:

- Free Trial
- Starter ₹149
- Plus ₹299
- Pro ₹799

Hold Power ₹1,499 until:

- cost logging is live
- model routing is proven
- deep-research usage distribution is known
- support burden is measured

## Paid Feature and Report Packaging

The product should avoid charging only for "chat." Chat is the entry point, but the monetizable value is saved work: reports, alerts, portfolio reviews, watchlists, exports, evidence trails, and recurring research workflows.

Recommended monetization principle:

```text
Free users get discovery.
Starter users get daily utility.
Plus users get repeatable research.
Pro users get portfolio and alert workflows.
Power users get bulk, export, and team-grade workflows.
```

### Paid Feature Candidates

| Feature | Free | Starter | Plus | Pro | Power | Monetization rationale |
|---|---|---|---|---|---|
| Basic Talk 2 Stocks chat | capped | yes | yes | yes | yes | acquisition and daily engagement |
| Higher daily chat quota | no | 10/day | 20/day | 50/day | fair-use | direct usage-based cost control |
| Follow-up context memory | no | short | medium | long | long + saved sessions | increases retention |
| Watchlists | 1 | 2 | 5 | 15 | custom | high-retention feature with low COGS |
| Stage 2 tracker access | limited preview | yes | yes | yes | yes | differentiated Agent Adda signal surface |
| Advanced screeners | no | limited | yes | yes | yes | strong paid conversion feature |
| Peer comparison | no | 2 stocks | 5 stocks | 10 stocks | baskets | clear tier boundary |
| Portfolio upload | no | no | lite | full | full + history | strong Pro upsell |
| Portfolio sell/add/trim review | no | no | monthly | weekly | on demand | high willingness-to-pay |
| Alert subscriptions | no | EOD alerts | EOD + limited intraday | intraday + email | advanced multi-channel | recurring utility |
| Email report delivery | no | no | yes | yes | yes | convenience feature |
| Export/share reports | no | limited | yes | yes | branded/custom | team-sharing value |
| Voice briefing | no | no | limited | yes | yes | premium UX and higher variable cost |
| Evidence trail | basic | yes | full | full | full | trust feature; useful for paid research |
| Source freshness validation | no | limited | yes | yes | yes | credibility and QA moat |
| Broker/news research overlay | no | limited | yes | yes | yes | paid insight layer |
| API / CSV export | no | no | limited | yes | bulk | power-user monetization |
| Custom report packs | no | no | no | limited | yes | high-value workflow automation |

### Paid Report Candidates

| Report / artifact | Suggested access | Frequency | Why users pay | Cost risk |
|---|---|---|---|---|
| Daily EOD Market Report | Plus+ | daily | saves daily market review time | Medium |
| Weekend Market Report | Plus+ | weekly | high-value planning artifact | Medium |
| Sector Rotation Report | Starter preview, Plus full | daily/EOD | identifies leadership and risk areas | Low/Medium |
| Stage 2 Tracker | Starter+ | daily/EOD | direct idea-discovery workflow | Low |
| Top Picks / Buy Candidates | Plus+ | daily/weekly | actionable research shortlist; must stay research-only | Medium |
| Must-Sell / Risk Review | Pro+ | weekly/on demand | portfolio risk control | Medium |
| Portfolio Assessment Report | Pro+ | weekly/on demand | personalized value; strong upsell | Medium |
| Individual Stock Deep Dive | Plus limited, Pro full | on demand | core research artifact | Medium/High |
| Fundamental Deep Research Report | Pro+ | on demand quota | higher LLM/document cost; high willingness-to-pay | High |
| Peer Battle Report | Plus+ | on demand | useful for allocation decisions | Medium |
| Results / Earnings Review | Plus+ | event-driven | timely post-result interpretation | Medium |
| Concall Summary + Key Questions | Pro+ | event-driven | document-grounded research | Medium/High |
| Broker/Analyst Consensus Overlay | Plus/Pro | event-driven | market narrative and target changes | Medium |
| FII/DII + Flow Dashboard | Starter+ | daily | macro/market context | Low |
| Intraday Options / F&O Alerts | Pro+ | intraday | high engagement; requires strict risk disclaimers | High |
| Watchlist Change Report | Plus+ | daily/weekly | tells users what changed in names they track | Low/Medium |
| Small/Mid Cap Fund Review | Pro/Power | weekly | premium curation workflow | Medium |
| Evidence QA Report | Power | on demand | trust/compliance for shared artifacts | Low/Medium |
| Branded Shareable HTML Report | Pro/Power | on demand | shareability and professional polish | Medium |

### Report Packaging Recommendation

| Bundle | Included reports | Tier |
|---|---|---|
| Market Pulse Pack | Daily EOD, weekend report, sector rotation, FII/DII flow | Plus |
| Idea Discovery Pack | Stage 2 tracker, top picks, peer battle, watchlist change report | Plus |
| Portfolio Risk Pack | Portfolio assessment, must-sell review, add/trim review, concentration risk | Pro |
| Earnings Pack | Results review, concall summary, broker overlay, open questions | Pro |
| Trader Alert Pack | Intraday alerts, F&O/option watch, VWAP/ORB alerts, breakout monitor | Pro/Power |
| Research Desk Pack | Deep stock research, custom HTML exports, evidence QA, bulk reports | Power |

### Add-On Monetization

| Add-on | Suggested price | Included usage |
|---|---:|---|
| Extra deep research pack | ₹199 | 10 additional deep reports |
| Portfolio history pack | ₹199/month | historical portfolio snapshots and change tracking |
| Intraday alert pack | ₹299/month | higher-frequency alerts and email delivery |
| Voice briefing pack | ₹149/month | daily audio briefings |
| Team share/export pack | ₹499/month | branded exports and shared report links |
| Custom research pack | ₹999+ | bespoke watchlists/report packs |

### Paid Feature Gating Rules

1. Deep research must be quota-based.
2. Intraday alerts must be quota- and frequency-based.
3. Voice must have minutes/characters caps.
4. Portfolio reports should be Pro+ because they are personalized and support-heavy.
5. Shareable branded reports should be Pro/Power because they create external product visibility.
6. Free should show enough value to convert, but not enough to replace a paid plan.
7. Every paid report should show data freshness, evidence sources, and research-only disclaimer.

### Feature Gating

| Feature | Free | Starter | Plus | Pro | Power |
|---|---|---|---|---|---|
| Basic chat | limited | yes | yes | yes | yes |
| Stock deep dive | limited | basic | full | full | full |
| Peer compare | no | 2 stocks | 5 stocks | 10 stocks | baskets |
| Sector/index reports | limited | yes | yes | yes | yes |
| Watchlists | 1 | 2 | 5 | 15 | custom |
| Alerts | no | basic EOD | EOD + limited intraday | intraday + email | advanced |
| Portfolio upload | no | no | lite | full | full + history |
| Deep research reports | no | 1/month | 5/month | 25/month | fair-use |
| Email report delivery | no | no | yes | yes | yes |
| Voice briefing | no | no | limited | yes | yes |
| API/export | no | no | limited | yes | team/export |

## Implementation Recommendations

### Environment Defaults

```text
LLM_ROUTER_PROVIDER=openai
LLM_ROUTER_MODEL=gpt-5-nano

LLM_DEFAULT_PROVIDER=openai
LLM_DEFAULT_MODEL=gpt-4o-mini

LLM_RESEARCH_PROVIDER=openai
LLM_RESEARCH_MODEL=gpt-5.6-luna

LLM_PREMIUM_PROVIDER=openai
LLM_PREMIUM_MODEL=gpt-5.6-terra

LLM_BATCH_PROVIDER=deepseek
LLM_BATCH_MODEL=deepseek-v4-flash

LLM_INDIC_PROVIDER=sarvam
LLM_INDIC_MODEL=sarvam-105b
```

### Product Decision

For the first 100 paid users, use:

- `gpt-5-nano` for routing, extraction, alert parsing
- `gpt-4o-mini` as the default answer model
- `gpt-5.6-luna` for Plus/Pro deep research
- no routine `gpt-4o`
- no routine `gpt-4`

This gives the team a credible path to 20%+ operating margin while keeping answer quality adequate for a research-first product.

## Source Notes

Pricing and external assumptions:

- OpenAI model and pricing pages: https://developers.openai.com/api/docs/models
- OpenAI `gpt-4o-mini`: https://developers.openai.com/api/docs/models/gpt-4o-mini
- OpenAI `gpt-4o`: https://developers.openai.com/api/docs/models/gpt-4o
- OpenAI `gpt-4`: https://developers.openai.com/api/docs/models/gpt-4
- OpenAI deprecations: https://developers.openai.com/api/docs/deprecations
- DeepSeek pricing: https://api-docs.deepseek.com/quick_start/pricing/
- Sarvam pricing: https://docs.sarvam.ai/api/getting-started/pricing
- xAI pricing: https://docs.x.ai/developers/pricing
- USD/INR reference: https://wise.com/us/currency-converter/usd-to-inr-rate/history

Internal scope references:

- Talk 2 Stocks product design: `docs/superpowers/specs/2026-08-23-talk-2-stocks-comprehensive-product-design.md`
- Agent Adda terminal feature registry: `nse_agent.py`
