# Web search (multiple engines + iterative search)

Script and agent tools for web search during sector research: market size, outlook, industry reports, news.

## Engines

| Engine        | Requirement | Notes |
|---------------|-------------|--------|
| **duckduckgo** | None (default) | No API key; region e.g. `in-en` for India. **Free.** |
| **google**     | `pip install googlesearch-python` | No key; rate-limited. **Free.** |
| **bing**       | `BING_SEARCH_KEY` or `BING_SUBSCRIPTION_KEY` | Azure; free tier ~1k queries/mo. |
| **yahoo**      | `SERPAPI_API_KEY` | Via SerpAPI (paid). |
| **brave**      | `BRAVE_API_KEY` or `BRAVE_SUBSCRIPTION_TOKEN` | **Free tier: 500 queries/month**, no credit card. [Get key](https://api-dashboard.search.brave.com/) |
| **searxng**     | `SEARXNG_BASE_URL` (e.g. `https://search.example.org`) | Use any SearXNG instance; **no API key**. Self-host or use a public instance that allows JSON. |

## Standalone script

From project root or `working-sector`:

```bash
# Single search (DuckDuckGo, India region)
python3 working-sector/web_search.py "Auto components India market size 2025"

# More results, different engine
python3 working-sector/web_search.py "Nifty Auto sector outlook" --engine duckduckgo --max-results 15

# Iterative search: round 1 = topic, round 2 = Ollama-suggested follow-up queries from snippets
python3 working-sector/web_search.py "ACMA auto components India" --iterative --rounds 2

# Save results to sector output dir (JSON + Markdown)
python3 working-sector/web_search.py "pharma sector India outlook" --iterative --rounds 2 --save
```

**Options**

- `--engine` — `duckduckgo` (default), `google`, `bing`, `yahoo`, `brave`, `searxng`
- `--max-results` — Max results per query (default 10)
- `--iterative` — Enable multi-round search
- `--rounds` — Number of rounds (default 2); round 2+ use Ollama to suggest follow-up queries
- `--no-ollama` — In iterative mode, do not use Ollama for follow-ups (only round 1 runs)
- `--save` — Write `web_search_results.json` and `web_search_results.md` to output dir
- `--output-dir` — Override output directory (default: sector output from config)
- `--region` — DuckDuckGo region (default `in-en` for India)

## Agent tools

The agent can call:

- **web_search(query, engine, max_results)** — Single search. Use for one-off lookups.
- **web_search_iterative(topic, rounds, engine, max_results_per_query)** — Multi-round search with optional Ollama follow-up queries; results deduplicated by URL. Use for deeper research.

Example prompts: “Search the web for auto components India market size”, “Do an iterative web search on pharma sector outlook India”.

## Iterative search flow

1. **Round 1:** Search the given topic; collect title, URL, snippet for each result.
2. **Round 2+ (if rounds > 1 and Ollama available):** Send topic + first round snippets to Ollama; get 1–2 suggested follow-up queries **emphasising latest data** (e.g. "latest", "2025", "recent", "outlook"); run those searches; append results.
3. Deduplicate by URL; tag every result with **retrieved_date** (today) so reports can cite when data was obtained.
4. **run_sector_research (agent tool):** Runs multi-step search + LLM synthesis that cites sources and dates; writes **research_sources.md** so the sector note and user can see data/research source and when it is from. The sector note (Phase 5) includes a "Data and research sources" section and references research_sources.md when present.

## Dependencies

- **ddgs** (or duckduckgo-search) — required for default engine
- **ollama** — for iterative follow-up suggestions (optional; use `--no-ollama` to skip)
- **googlesearch-python** — optional, for `--engine google`
- **requests** — used by Bing, Yahoo, Brave, SearXNG
- **Bing** — set `BING_SEARCH_KEY` for Azure
- **Yahoo** — set `SERPAPI_API_KEY` for SerpAPI
- **Brave** — set `BRAVE_API_KEY` for Brave Search (500 free queries/month)
- **SearXNG** — set `SEARXNG_BASE_URL` to a SearXNG instance URL (no key)
