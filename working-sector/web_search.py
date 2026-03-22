#!/usr/bin/env python3
"""
Web search script: multiple search engines and iterative search for sector research.

Engines (all optional except duckduckgo):
- duckduckgo (default): no API key.
- google: googlesearch-python, no key, rate-limited.
- bing: BING_SEARCH_KEY (Azure; free tier ~1k/mo).
- yahoo: SERPAPI_API_KEY (SerpAPI).
- brave: BRAVE_API_KEY — free tier 500 queries/month, no credit card.
- searxng: SEARXNG_BASE_URL — use a SearXNG instance (self-hosted or public); no API key.

Iterative search runs initial query, then optionally uses Ollama to suggest follow-up
queries from snippets; results are deduplicated by URL.

Usage:
  python web_search.py "Auto components India market size 2025"
  python web_search.py "Nifty Auto sector outlook" --engine duckduckgo --max-results 15
  python web_search.py "ACMA auto components" --iterative --rounds 2 --save
  python web_search.py "pharma sector India" --engine google --save --output-dir output/auto_components
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

WORKING_SECTOR = Path(__file__).resolve().parent
if str(WORKING_SECTOR) not in sys.path:
    sys.path.insert(0, str(WORKING_SECTOR))
# Load .env from project root so SERPAPI_API_KEY, BRAVE_API_KEY, etc. are set
try:
    from dotenv import load_dotenv
    load_dotenv(WORKING_SECTOR.parent / ".env")
except ImportError:
    pass

# Result shape: list of {"title", "url", "snippet", "retrieved_date?", "source_site"?}
ResultItem = dict

# Indian stock market, research and government sites for targeted sector research (site: operator)
# Format: (display_name, domain for site: query)
RESEARCH_SITES_INDIA: list[tuple[str, str]] = [
    # Stock / markets
    ("Moneycontrol", "moneycontrol.com"),
    ("Economic Times Markets", "economictimes.indiatimes.com"),
    ("Business Standard", "business-standard.com"),
    ("Livemint", "livemint.com"),
    ("Financial Express", "financialexpress.com"),
    ("NSE India", "nseindia.com"),
    ("BSE India", "bseindia.com"),
    ("Investing.com India", "in.investing.com"),
    # Research / ratings / industry
    ("CRISIL", "crisil.com"),
    ("ICRA", "icra.in"),
    ("Care Ratings", "careratings.com"),
    ("India Ratings", "indiaratings.co.in"),
    ("IBEF", "ibef.org"),
    ("Invest India", "investindia.gov.in"),
    # Government / policy
    ("Ministry of Commerce", "commerce.gov.in"),
    ("DPIIT", "dpiit.gov.in"),
    ("RBI", "rbi.org.in"),
    ("SEBI", "sebi.gov.in"),
    ("PIB", "pib.gov.in"),
]


def search_duckduckgo(query: str, max_results: int = 10, region: str = "in-en") -> list[ResultItem]:
    """Search DuckDuckGo. No API key. Region in-en for India. Uses ddgs package (pip install ddgs)."""
    import warnings
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*renamed to.*ddgs.*", category=RuntimeWarning)
        try:
            from ddgs import DDGS
        except ImportError:
            try:
                from duckduckgo_search import DDGS
            except ImportError:
                return [{"title": "Error", "url": "", "snippet": "Install: pip install ddgs"}]
    out = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results, region=region):
                out.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", r.get("url", "")),
                    "snippet": r.get("body", r.get("snippet", "")),
                })
    except Exception as e:
        out.append({"title": "DuckDuckGo error", "url": "", "snippet": str(e)})
    return out


def search_googlesearch(query: str, max_results: int = 10) -> list[ResultItem]:
    """Search via googlesearch-python (no API key). May be rate-limited. Returns URLs; title/snippet often empty."""
    try:
        from googlesearch import search as gsearch
    except ImportError:
        return [{"title": "Error", "url": "", "snippet": "Install: pip install googlesearch-python"}]
    out = []
    try:
        # Newer API may support advanced=True with title/description
        for item in gsearch(query, num_results=max_results, advanced=True):
            if hasattr(item, "url"):
                out.append({
                    "title": getattr(item, "title", "") or "",
                    "url": getattr(item, "url", "") or str(item),
                    "snippet": getattr(item, "description", "") or "",
                })
            else:
                out.append({"title": "", "url": str(item), "snippet": ""})
    except TypeError:
        try:
            from googlesearch import search as gsearch
            for url in gsearch(query, num_results=max_results):
                out.append({"title": "", "url": str(url), "snippet": ""})
        except Exception as e2:
            out.append({"title": "Google search error", "url": "", "snippet": str(e2)})
    except Exception as e:
        out.append({"title": "Google search error", "url": "", "snippet": str(e)})
    return out


def search_bing(query: str, max_results: int = 10) -> list[ResultItem]:
    """Search Bing Web Search API. Requires BING_SEARCH_KEY (or BING_SUBSCRIPTION_KEY) env."""
    key = os.environ.get("BING_SEARCH_KEY") or os.environ.get("BING_SUBSCRIPTION_KEY")
    if not key:
        return [{"title": "Bing", "url": "", "snippet": "Set BING_SEARCH_KEY (or BING_SUBSCRIPTION_KEY) for Bing search."}]
    try:
        import requests
        url = "https://api.bing.microsoft.com/v7.0/search"
        r = requests.get(
            url,
            headers={"Ocp-Apim-Subscription-Key": key},
            params={"q": query, "count": min(max_results, 50), "textDecorations": False},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        out = []
        for item in data.get("webPages", {}).get("value", [])[:max_results]:
            out.append({
                "title": item.get("name", ""),
                "url": item.get("url", ""),
                "snippet": item.get("snippet", ""),
            })
        return out
    except Exception as e:
        return [{"title": "Bing error", "url": "", "snippet": str(e)}]


def search_yahoo(query: str, max_results: int = 10) -> list[ResultItem]:
    """Search Yahoo via SerpAPI. Requires SERPAPI_API_KEY env. See https://serpapi.com/yahoo-search-api"""
    key = os.environ.get("SERPAPI_API_KEY")
    if not key:
        return [{"title": "Yahoo", "url": "", "snippet": "Set SERPAPI_API_KEY for Yahoo search (optional)."}]
    try:
        import requests
        url = "https://serpapi.com/search"
        r = requests.get(
            url,
            params={
                "engine": "yahoo",
                "p": query,
                "api_key": key,
                "num": min(max_results, 40),
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        out = []
        for item in data.get("organic_results", [])[:max_results]:
            out.append({
                "title": item.get("title", ""),
                "url": item.get("link", item.get("url", "")),
                "snippet": item.get("snippet", item.get("description", "")),
            })
        return out
    except Exception as e:
        return [{"title": "Yahoo error", "url": "", "snippet": str(e)}]


def search_brave(query: str, max_results: int = 10) -> list[ResultItem]:
    """Search Brave. Free tier: 500 queries/month. Requires BRAVE_API_KEY (or BRAVE_SUBSCRIPTION_TOKEN)."""
    key = os.environ.get("BRAVE_API_KEY") or os.environ.get("BRAVE_SUBSCRIPTION_TOKEN")
    if not key:
        return [{"title": "Brave", "url": "", "snippet": "Set BRAVE_API_KEY for Brave search (free tier: 500/mo)."}]
    try:
        import requests
        url = "https://api.search.brave.com/res/v1/web/search"
        r = requests.get(
            url,
            headers={"X-Subscription-Token": key, "Accept": "application/json"},
            params={"q": query, "count": min(max_results, 20)},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        out = []
        for item in data.get("web", {}).get("results", [])[:max_results]:
            out.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
            })
        return out
    except Exception as e:
        return [{"title": "Brave error", "url": "", "snippet": str(e)}]


def search_searxng(query: str, max_results: int = 10) -> list[ResultItem]:
    """Search via SearXNG instance (self-hosted or public). Set SEARXNG_BASE_URL (e.g. https://search.example.org). No API key."""
    base = (os.environ.get("SEARXNG_BASE_URL") or "").rstrip("/")
    if not base:
        return [{"title": "SearXNG", "url": "", "snippet": "Set SEARXNG_BASE_URL to a SearXNG instance (e.g. https://search.example.org)."}]
    try:
        import requests
        url = f"{base}/search"
        r = requests.get(
            url,
            params={"q": query, "format": "json", "categories": "general"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        out = []
        for item in data.get("results", [])[:max_results]:
            out.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", item.get("snippet", "")),
            })
        return out
    except Exception as e:
        return [{"title": "SearXNG error", "url": "", "snippet": str(e)}]


ENGINES = {
    "duckduckgo": search_duckduckgo,
    "google": search_googlesearch,
    "bing": search_bing,
    "yahoo": search_yahoo,
    "brave": search_brave,
    "searxng": search_searxng,
}


def search(
    query: str,
    engine: str = "duckduckgo",
    max_results: int = 10,
    region: str = "in-en",
) -> list[ResultItem]:
    """
    Run a single search with the chosen engine.

    Args:
        query: Search query string.
        engine: One of duckduckgo, google, bing, yahoo, brave, searxng.
        max_results: Max number of results to return.
        region: For DuckDuckGo only (e.g. in-en for India).

    Returns:
        List of dicts with title, url, snippet.
    """
    engine = (engine or "duckduckgo").strip().lower()
    fn = ENGINES.get(engine, search_duckduckgo)
    if engine == "duckduckgo":
        return search_duckduckgo(query, max_results=max_results, region=region)
    return fn(query, max_results=max_results)


def search_multi_engine(
    query: str,
    engines: list[str],
    max_results_per_engine: int = 6,
    region: str = "in-en",
) -> list[ResultItem]:
    """
    Run the same query on multiple engines, merge and dedupe by URL.
    Each result gets source_engine set (e.g. 'duckduckgo', 'google', 'yahoo').
    Engines that fail or return no real results are skipped.
    """
    all_results: list[ResultItem] = []
    for eng in engines:
        eng = (eng or "").strip().lower()
        if eng not in ENGINES:
            continue
        try:
            if eng == "duckduckgo":
                res = search_duckduckgo(query, max_results=max_results_per_engine, region=region)
            else:
                res = ENGINES[eng](query, max_results=max_results_per_engine)
            res = [r for r in res if (r.get("url") or "").strip() and not (r.get("snippet") or "").strip().startswith("Set ")]
            for r in res:
                r["source_engine"] = eng
            all_results.extend(res)
        except Exception:
            continue
    return dedupe_by_url(all_results)


def suggest_follow_up_queries(
    topic: str,
    snippets: list[str],
    num_queries: int = 2,
    model: str = "granite4:latest",
    emphasize_latest: bool = True,
) -> list[str]:
    """Use Ollama to suggest 1–2 follow-up search queries; emphasize latest data and dated sources."""
    try:
        from ollama import chat
    except ImportError:
        return []
    text = "\n\n".join((s[:500] for s in snippets[:5] if s))
    latest_instruction = (
        " Prioritise finding the LATEST data: add terms like 'latest', '2025', '2026', 'current', 'recent', "
        "or 'outlook' so users can see when the information is from. Prefer queries that surface dated reports or news."
    ) if emphasize_latest else ""
    prompt = (
        f"Topic: {topic}\n\nFirst search result snippets (excerpts):\n{text}\n\n"
        "Suggest exactly 1 or 2 short, specific web search queries to find more detail "
        "(e.g. market size, recent news, industry reports)."
        f"{latest_instruction}\n\n"
        "Reply with only the queries, one per line, no numbering or extra text."
    )
    try:
        r = chat(model=model, messages=[{"role": "user", "content": prompt}], options={"temperature": 0.3})
        content = (r.message.content or "").strip()
        queries = [q.strip() for q in content.splitlines() if q.strip()][:num_queries]
        return [q.lstrip("0123456789.-) ") for q in queries]
    except Exception:
        return []


def dedupe_by_url(results: list[ResultItem]) -> list[ResultItem]:
    """Deduplicate by url, keeping first occurrence."""
    seen = set()
    out = []
    for r in results:
        u = (r.get("url") or "").strip()
        if u and u not in seen:
            seen.add(u)
            out.append(r)
    return out


def search_research_sites(
    topic: str,
    sites: list[tuple[str, str]] | None = None,
    engine: str = "duckduckgo",
    engines: list[str] | None = None,
    max_per_site: int = 5,
    region: str = "in-en",
) -> tuple[list[ResultItem], list[str]]:
    """
    Run site-restricted searches on Indian stock market, research and government websites.
    For each (label, domain) runs: topic + " site:domain". If engines is set, runs each
    site query on all engines and merges. Returns (results, list of site labels that were queried).
    """
    sites = sites or RESEARCH_SITES_INDIA
    all_results: list[ResultItem] = []
    today = date.today().isoformat()
    use_multi = engines and len(engines) >= 1
    effective_engines = [e.strip().lower() for e in engines if (e or "").strip()] if use_multi else [engine]

    for label, domain in sites:
        query = f"{topic} site:{domain}"
        try:
            if use_multi and len(effective_engines) > 1:
                res = search_multi_engine(query, effective_engines, max_results_per_engine=max_per_site, region=region)
            else:
                res = search(query, engine=effective_engines[0], max_results=max_per_site, region=region)
            res = [r for r in res if r.get("url") or r.get("snippet")]
            for r in res:
                r["retrieved_date"] = today
                r["source_site"] = label
            all_results.extend(res)
        except Exception:
            continue
    out = dedupe_by_url(all_results)
    queried = [label for label, _ in sites]
    return out, queried


def search_iterative(
    topic: str,
    rounds: int = 2,
    engine: str = "duckduckgo",
    engines: list[str] | None = None,
    max_results_per_query: int = 8,
    use_ollama: bool = True,
    region: str = "in-en",
) -> list[ResultItem]:
    """
    Iterative search: round 1 = search topic; round 2+ = optional follow-up queries via Ollama.
    If engines is a list (e.g. ["duckduckgo", "google", "yahoo"]), each query is run on all engines and results merged.

    Args:
        topic: Main search topic (first query).
        rounds: Number of search rounds (1 = single query).
        engine: Search engine when engines is None.
        engines: If set, run each query on these engines and merge (e.g. ["duckduckgo", "google", "yahoo"]).
        max_results_per_query: Max results per query (or per engine when using multi-engine).
        use_ollama: If True and rounds > 1, use Ollama to suggest follow-up queries from round 1 snippets.
        region: DuckDuckGo region.

    Returns:
        Deduplicated list of results (title, url, snippet).
    """
    all_results: list[ResultItem] = []
    queries_done: list[str] = []
    use_multi = engines and len(engines) >= 1
    effective_engines = [e.strip().lower() for e in engines if (e or "").strip()] if use_multi else [engine]

    def run_query(q: str) -> list[ResultItem]:
        if use_multi and len(effective_engines) > 1:
            return search_multi_engine(q, effective_engines, max_results_per_engine=max_results_per_query, region=region)
        return search(q, engine=effective_engines[0], max_results=max_results_per_query, region=region)

    # Round 1
    first = run_query(topic)
    first = [r for r in first if r.get("snippet") or r.get("url")]
    all_results.extend(first)
    queries_done.append(topic)

    for _ in range(rounds - 1):
        if use_ollama and all_results:
            snippets = [r.get("snippet", "") for r in all_results[:10] if r.get("snippet")]
            follow_ups = suggest_follow_up_queries(topic, snippets, num_queries=2, emphasize_latest=True)
            for q in follow_ups:
                if q and q not in queries_done:
                    queries_done.append(q)
                    more = run_query(q)
                    more = [r for r in more if r.get("snippet") or r.get("url")]
                    all_results.extend(more)
        else:
            break

    results_out = dedupe_by_url(all_results)
    today = date.today().isoformat()
    for r in results_out:
        r["retrieved_date"] = today
    return results_out


def results_to_markdown(results: list[ResultItem], title: str = "Web search results") -> str:
    """Format results as Markdown."""
    lines = [f"# {title}", ""]
    for i, r in enumerate(results, 1):
        t, u, s = r.get("title", ""), r.get("url", ""), r.get("snippet", "")
        lines.append(f"## {i}. {t or '(no title)'}")
        if u:
            lines.append(f"**URL:** {u}")
        lines.append("")
        if s:
            lines.append(s[:800] + ("..." if len(s) > 800 else ""))
        lines.append("")
    return "\n".join(lines)


def save_results(
    results: list[ResultItem],
    output_dir: Path,
    base_name: str = "web_search",
) -> tuple[Path, Path]:
    """Write results to JSON and Markdown in output_dir. Returns (json_path, md_path)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{base_name}.json"
    md_path = output_dir / f"{base_name}.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    md_path.write_text(results_to_markdown(results, title=base_name.replace("_", " ").title()), encoding="utf-8")
    return json_path, md_path


def _add_retrieved_date(results: list[ResultItem], when: str | None = None) -> None:
    """Add retrieved_date to each result (for source attribution in reports)."""
    d = (when or date.today().isoformat())
    for r in results:
        r["retrieved_date"] = d


def synthesize_research_with_sources(
    sector_display_name: str,
    results: list[ResultItem],
    model: str = "granite4:latest",
) -> str:
    """
    Use LLM to synthesize web search results into a short research summary that explicitly
    cites sources and dates. Instructs the model to list sources (URL, retrieved date) and
    to mark any LLM-added knowledge as undated.
    """
    try:
        from ollama import chat
    except ImportError:
        return "(Ollama not available; install ollama and run synthesis separately.)"
    if not results:
        return "(No web results to synthesize.)"
    retrieved = results[0].get("retrieved_date", date.today().isoformat())
    # Build context: numbered list of title, URL, snippet, retrieved_date
    lines = []
    for i, r in enumerate(results[:12], 1):
        t, u, s = r.get("title", ""), r.get("url", ""), r.get("snippet", "")
        rd = r.get("retrieved_date", retrieved)
        lines.append(f"{i}. Title: {t}\n   URL: {u}\n   Retrieved: {rd}\n   Excerpt: {s[:400]}...")
    context = "\n\n".join(lines)
    prompt = (
        f"You are writing a research summary for the sector: {sector_display_name} (India).\n\n"
        "Use ONLY the following web search results. Each was retrieved on the date shown (retrieved_date).\n\n"
        "Instructions:\n"
        "1. Write a short paragraph (3–5 sentences) summarising the LATEST data and outlook from these sources. "
        "Mention specific numbers (e.g. market size, growth) and any dates cited in the excerpts.\n"
        "2. Then under 'Sources (retrieved [date]):', list each source as: Title – URL. "
        "So the user knows exactly where the information came from and when it was retrieved.\n"
        "3. If you add any fact from your own training (not from the excerpts), put it in a separate sentence and "
        "end it with: '(LLM general knowledge; not dated—verify for current use.)'\n\n"
        f"Web search results (retrieved on {retrieved}):\n\n{context}"
    )
    try:
        r = chat(model=model, messages=[{"role": "user", "content": prompt}], options={"temperature": 0.3})
        return (r.message.content or "").strip()
    except Exception as e:
        return f"(Synthesis failed: {e})"


# Default engines for sector research. Free/no-key: duckduckgo, google (rate-limited). Optional keys: yahoo (SERPAPI_API_KEY), brave (BRAVE_API_KEY, 500/mo free), searxng (SEARXNG_BASE_URL).
DEFAULT_RESEARCH_ENGINES = ["duckduckgo", "google", "yahoo", "brave"]


def research_with_synthesis(
    sector_display_name: str,
    topic_query: str | None = None,
    rounds: int = 3,
    engine: str = "duckduckgo",
    engines: list[str] | None = None,
    max_results_per_query: int = 8,
    region: str = "in-en",
    model: str = "granite4:latest",
    research_sites: list[tuple[str, str]] | None = None,
    max_per_site: int = 5,
) -> tuple[list[ResultItem], str, list[str]]:
    """
    Multi-step research: build a 'latest data' query, run iterative search (optionally on multiple
    engines: DuckDuckGo, Google, Yahoo), then run site-restricted searches. Merges and dedupes,
    then LLM synthesis. Returns (results, synthesis_text, list of site labels queried).
    """
    current_year = str(date.today().year)
    next_year = str(date.today().year + 1)
    if topic_query:
        base = topic_query.strip()
        if not any(w in base.lower() for w in ("latest", "current", "recent", "2025", "2026", current_year, next_year)):
            topic = f"{base} latest {current_year} {next_year} outlook market size"
        else:
            topic = base
    else:
        topic = f"{sector_display_name} India latest {current_year} {next_year} market size outlook"
    effective_engines = engines if engines is not None else DEFAULT_RESEARCH_ENGINES
    results = search_iterative(
        topic=topic,
        rounds=rounds,
        engine=engine,
        engines=effective_engines,
        max_results_per_query=max_results_per_query,
        use_ollama=True,
        region=region,
    )
    _add_retrieved_date(results)
    site_results, sites_queried = search_research_sites(
        topic=topic,
        sites=research_sites,
        engine=engine,
        engines=effective_engines,
        max_per_site=max_per_site,
        region=region,
    )
    # Prefer iterative results for duplicates; then add site-only results
    seen_urls = {r.get("url", "").strip() for r in results if r.get("url")}
    for r in site_results:
        u = (r.get("url") or "").strip()
        if u and u not in seen_urls:
            seen_urls.add(u)
            results.append(r)
    synthesis = synthesize_research_with_sources(sector_display_name, results, model=model)
    return results, synthesis, sites_queried


def write_research_sources_md(
    output_dir: Path,
    sector_display_name: str,
    synthesis: str,
    results: list[ResultItem],
    pipeline_data_as_of: str | None = None,
    research_sites_used: list[str] | None = None,
) -> Path:
    """
    Write research_sources.md so the report and user can see data and research source and dates.
    If research_sites_used is provided, documents the Indian stock market, research and government sites that were queried.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    lines = [
        "# Data and research sources",
        "",
        "This section documents where the data and research in this report come from and when they were obtained, so users can assess recency and verify sources.",
        "",
        "---",
        "",
        "## Report and retrieval dates",
        "",
        f"- **Report generated:** {today}",
        f"- **Pipeline data (prices, fundamentals) as of:** {pipeline_data_as_of or 'See sector note.'}",
        "",
        "---",
        "",
        "## Web search and LLM synthesis",
        "",
        f"- **Web search conducted on:** {today}",
        "- Search was run with emphasis on **latest data** (current year, recent outlook). Multi-step iterative search was used; follow-up queries aimed at dated reports and recent news.",
        "- **Search engines used:** DuckDuckGo, Google, Yahoo, Brave (and optionally SearXNG). Yahoo needs SERPAPI_API_KEY; Brave needs BRAVE_API_KEY (500 free queries/mo); SearXNG needs SEARXNG_BASE_URL. Results from all configured engines are merged and deduplicated.",
        "- Additional **targeted searches** were run on a list of Indian stock market, research and government websites (site-restricted queries) to improve coverage of authoritative sources.",
        "- The summary below was produced by an LLM using the retrieved snippets. Any sentence marked '(LLM general knowledge; not dated)' was not taken from the search results and should be verified for current use.",
        "",
    ]
    if research_sites_used:
        lines += [
            "### Targeted research sites (India)",
            "",
            "Searches were run on the following sites (site: operator):",
            "",
        ]
        for name in research_sites_used:
            lines.append(f"- {name}")
        lines += ["", ""]
    lines += [
        "### Research summary (sources and dates)",
        "",
        synthesis,
        "",
        "---",
        "",
        "## Source list (web search results)",
        "",
    ]
    has_source_site = any(r.get("source_site") for r in results[:35])
    has_source_engine = any(r.get("source_engine") for r in results[:35])
    if has_source_site and has_source_engine:
        lines.append("| # | Title | URL | Source site | Source engine | Retrieved date |")
        lines.append("|---|-------|-----|-------------|---------------|----------------|")
    elif has_source_site:
        lines.append("| # | Title | URL | Source site | Retrieved date |")
        lines.append("|---|-------|-----|-------------|----------------|")
    elif has_source_engine:
        lines.append("| # | Title | URL | Source engine | Retrieved date |")
        lines.append("|---|-------|-----|---------------|----------------|")
    else:
        lines.append("| # | Title | URL | Retrieved date |")
        lines.append("|---|-------|-----|----------------|")
    for i, r in enumerate(results[:35], 1):
        title = (r.get("title") or "").replace("|", "\\|").strip()[:80]
        url = (r.get("url") or "").strip()
        rd = r.get("retrieved_date", today)
        site = (r.get("source_site") or "").strip()
        eng = (r.get("source_engine") or "").strip()
        if has_source_site and has_source_engine:
            lines.append(f"| {i} | {title} | {url} | {site} | {eng} | {rd} |")
        elif has_source_site:
            lines.append(f"| {i} | {title} | {url} | {site} | {rd} |")
        elif has_source_engine:
            lines.append(f"| {i} | {title} | {url} | {eng} | {rd} |")
        else:
            lines.append(f"| {i} | {title} | {url} | {rd} |")
    lines += [
        "",
        "---",
        "",
        "**Disclaimer:** Data and web results are as of the dates above. Users should verify sources and dates for their own use.",
        "",
    ]
    path = output_dir / "research_sources.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _research_context_for_llm(results: list[ResultItem], synthesis: str, max_sources: int = 12) -> str:
    """Build a single context block from synthesis + numbered sources for LLM prompts."""
    lines = [f"Research summary (from web search + LLM synthesis):\n{synthesis}\n"]
    for i, r in enumerate(results[:max_sources], 1):
        t, u, s = r.get("title", ""), r.get("url", ""), r.get("snippet", "")
        rd = r.get("retrieved_date", date.today().isoformat())
        lines.append(f"Source {i}: {t}\n  URL: {u}\n  Retrieved: {rd}\n  Excerpt: {s[:350]}...")
    return "\n\n".join(lines)


def generate_sector_narrative(
    sector_display_name: str,
    synthesis: str,
    results: list[ResultItem],
    model: str = "granite4:latest",
) -> str:
    """
    Use LLM to generate sector narrative (definition, market size, outlook) from research + LLM knowledge.
    Output is markdown suitable for sector_narrative_<sector>.md.
    """
    try:
        from ollama import chat
    except ImportError:
        return f"# Sector Narrative: {sector_display_name} (India)\n\n*(Ollama not available; install and run to generate from research.)*"
    context = _research_context_for_llm(results, synthesis)
    prompt = (
        f"You are writing the **Sector Narrative** for {sector_display_name} (India) for a financial research report.\n\n"
        "Use the research summary and sources below. Add your own knowledge where helpful, but for any fact not from the sources, add: (LLM general knowledge; verify for current use).\n\n"
        "Write markdown with these sections (use ## for headings):\n"
        "1. **Definition and market size** – How the sector is defined, key associations, market size in ₹/USD, growth, number of players. Cite sources where possible.\n"
        "2. **Strategic outlook** – Recent performance, policy, key drivers (e.g. PLI, exports, raw materials), and near-term outlook. Include dates/years when available.\n"
        "3. **Why this sector for research** – One short paragraph on why this sector is relevant for equity research (size, under-researched, thematic alignment, etc.).\n\n"
        "Keep it concise (about 1–2 pages). Cite URLs or source numbers where you use them.\n\n"
        f"Research context:\n\n{context}"
    )
    try:
        r = chat(model=model, messages=[{"role": "user", "content": prompt}], options={"temperature": 0.3})
        body = (r.message.content or "").strip()
        if not body.startswith("#"):
            body = f"# Sector Narrative: {sector_display_name} (India)\n\n**Sources:** Web search and industry reports (see research_sources.md).\n\n---\n\n{body}"
        return body
    except Exception as e:
        return f"# Sector Narrative: {sector_display_name} (India)\n\n*(Generation failed: {e})*"


def generate_hypothesis_memo(
    sector_display_name: str,
    synthesis: str,
    results: list[ResultItem],
    model: str = "granite4:latest",
) -> str:
    """
    Use LLM to generate hypothesis memo (research question, definition, H1/H2, scope, screen criteria) from research.
    Output is markdown for hypothesis_<sector>.md.
    """
    try:
        from ollama import chat
    except ImportError:
        return f"# Hypothesis Memo: {sector_display_name}\n\n*(Ollama not available.)*"
    context = _research_context_for_llm(results, synthesis)
    prompt = (
        f"You are writing the **Hypothesis Memo** for {sector_display_name} (India) for equity research.\n\n"
        "Use the research summary and sources below. Add (LLM general knowledge; verify for current use) for any fact not from the sources.\n\n"
        "Write markdown with these sections (use ## for headings):\n"
        "## 1. Research question (one sentence)\n"
        "What we are studying, why it matters, and what success looks like (e.g. shortlist + backtest).\n\n"
        "## 2. Definition\n"
        "Industry term, universe rule (e.g. NSE-listed, exclude OEMs or similar), source (e.g. aligned with industry body), optional sub-segments.\n\n"
        "## 3. Hypotheses\n"
        "### H1 (Sector)\n"
        "One sentence: sector has [characteristic] as evidenced by [metric] over [horizon]. How we test it.\n\n"
        "### H2 (Stock selection)\n"
        "Stocks that satisfy [screen criteria] have [outcome] vs benchmark over [horizon]. How we test (e.g. backtest).\n\n"
        "## 4. Scope and limits\n"
        "In scope, out of scope, known limits (e.g. listed only, point-in-time).\n\n"
        "## 5. Screen criteria (operational)\n"
        "Quality (e.g. fundamental score > 70), momentum/RS (e.g. RS vs Nifty 500 > 0 over 6M), composite weights, shortlist size (e.g. top 15).\n\n"
        "Keep each section concise. Use bullet points where appropriate.\n\n"
        f"Research context:\n\n{context}"
    )
    try:
        r = chat(model=model, messages=[{"role": "user", "content": prompt}], options={"temperature": 0.3})
        body = (r.message.content or "").strip()
        if not body.startswith("#"):
            body = f"# Hypothesis Memo: {sector_display_name}\n\n**Date:** {date.today().isoformat()}\n\n---\n\n{body}"
        return body
    except Exception as e:
        return f"# Hypothesis Memo: {sector_display_name}\n\n*(Generation failed: {e})*"


def generate_literature_notes(
    sector_display_name: str,
    synthesis: str,
    results: list[ResultItem],
    model: str = "granite4:latest",
) -> str:
    """
    Use LLM to generate literature notes (source table, cross-check, summary) from research.
    Output is markdown for literature_notes_<sector>.md.
    """
    try:
        from ollama import chat
    except ImportError:
        return f"# Literature Notes: {sector_display_name}\n\n*(Ollama not available.)*"
    # Build a clear source list for the model
    source_lines = []
    for i, r in enumerate(results[:15], 1):
        t, u, s = r.get("title", ""), r.get("url", ""), r.get("snippet", "")
        rd = r.get("retrieved_date", date.today().isoformat())
        source_lines.append(f"{i}. Title: {t}\n   URL: {u}\n   Retrieved: {rd}\n   Excerpt: {s[:300]}...")
    sources_text = "\n\n".join(source_lines)
    context = f"Research summary:\n{synthesis}\n\nNumbered sources:\n{sources_text}"
    prompt = (
        f"You are writing **Literature Notes** for {sector_display_name} (India) for a financial research report.\n\n"
        "Use the research summary and numbered sources below. For any fact not from these sources, add: (LLM general knowledge; verify for current use).\n\n"
        "Write markdown with:\n\n"
        "## Source-by-source (or grouped)\n"
        "For each source (or group): Title/Report name, Publisher/Author, Date/URL, Definition of sector, Market size (₹/USD, year), Key segments, Key drivers (3–5 bullets), How our universe aligns or deviates.\n\n"
        "## Cross-check: Our numbers vs sources\n"
        "A short table or bullets: metric (e.g. market size, no. of companies), source value, our assumption for the report.\n\n"
        "## One-paragraph summary for sector note\n"
        "One paragraph for the final report 'Definition and market size' section, with citation to these sources.\n\n"
        "Keep it concise. Cite source numbers or URLs.\n\n"
        f"Research context:\n\n{context}"
    )
    try:
        r = chat(model=model, messages=[{"role": "user", "content": prompt}], options={"temperature": 0.3})
        body = (r.message.content or "").strip()
        if not body.startswith("#"):
            body = f"# Literature Notes: {sector_display_name}\n\n**Purpose:** Industry/sector report findings for definition, market size, and narrative. Cite in the final sector note.\n\n---\n\n{body}"
        return body
    except Exception as e:
        return f"# Literature Notes: {sector_display_name}\n\n*(Generation failed: {e})*"


def write_sector_docs_from_research(
    working_sector_dir: Path,
    sector_key: str,
    sector_display_name: str,
    synthesis: str,
    results: list[ResultItem],
    model: str = "granite4:latest",
) -> dict[str, Path]:
    """
    Generate sector narrative, hypothesis memo, and literature notes from research + LLM, and write them
    to working_sector_dir. Files: sector_narrative_<sector>.md, hypothesis_<sector>.md,
    literature_notes_<sector>.md. Returns dict of doc_name -> path.
    """
    working_sector_dir = Path(working_sector_dir)
    written = {}
    narrative = generate_sector_narrative(sector_display_name, synthesis, results, model=model)
    path_narr = working_sector_dir / f"sector_narrative_{sector_key}.md"
    path_narr.write_text(narrative, encoding="utf-8")
    written["sector_narrative"] = path_narr
    hypothesis = generate_hypothesis_memo(sector_display_name, synthesis, results, model=model)
    path_hyp = working_sector_dir / f"hypothesis_{sector_key}.md"
    path_hyp.write_text(hypothesis, encoding="utf-8")
    written["hypothesis"] = path_hyp
    literature = generate_literature_notes(sector_display_name, synthesis, results, model=model)
    path_lit = working_sector_dir / f"literature_notes_{sector_key}.md"
    path_lit.write_text(literature, encoding="utf-8")
    written["literature_notes"] = path_lit
    return written


def run_search(
    query: str,
    engine: str = "duckduckgo",
    max_results: int = 10,
    iterative: bool = False,
    rounds: int = 2,
    use_ollama: bool = True,
    save: bool = False,
    output_dir: Path | None = None,
    region: str = "in-en",
) -> tuple[list[ResultItem], str]:
    """
    Run search (single or iterative) and optionally save. Returns (results, summary_string).
    """
    if iterative and rounds >= 2:
        results = search_iterative(
            topic=query,
            rounds=rounds,
            engine=engine,
            max_results_per_query=max_results,
            use_ollama=use_ollama,
            region=region,
        )
    else:
        results = search(query, engine=engine, max_results=max_results, region=region)
        results = [r for r in results if r.get("snippet") or r.get("url")]
        _add_retrieved_date(results)

    summary = f"Found {len(results)} results (engine={engine}" + (f", iterative rounds={rounds}" if iterative and rounds >= 2 else "") + ")."
    if save and results and output_dir:
        jp, mp = save_results(results, output_dir, base_name="web_search_results")
        summary += f" Saved to {jp.name} and {mp.name} in {output_dir}."

    return results, summary


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Web search for sector research (multiple engines, iterative).")
    parser.add_argument("query", nargs="+", help="Search query (words joined).")
    parser.add_argument("--engine", default="duckduckgo", choices=list(ENGINES.keys()), help="Search engine.")
    parser.add_argument("--max-results", type=int, default=10, help="Max results per query.")
    parser.add_argument("--iterative", action="store_true", help="Run iterative search (rounds with optional Ollama follow-ups).")
    parser.add_argument("--rounds", type=int, default=2, help="Iterative search rounds (default 2).")
    parser.add_argument("--no-ollama", action="store_true", help="Disable Ollama for follow-up suggestions in iterative mode.")
    parser.add_argument("--save", action="store_true", help="Save results to JSON and Markdown.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directory for saved files (default: working-sector/output/<sector> or output/).")
    parser.add_argument("--region", default="in-en", help="DuckDuckGo region (e.g. in-en for India).")
    args = parser.parse_args()
    query = " ".join(args.query)
    output_dir = args.output_dir
    if output_dir is None:
        try:
            from config import OUTPUT_DIR
            output_dir = OUTPUT_DIR
        except Exception:
            output_dir = WORKING_SECTOR / "output"
    results, summary = run_search(
        query=query,
        engine=args.engine,
        max_results=args.max_results,
        iterative=args.iterative,
        rounds=args.rounds,
        use_ollama=not args.no_ollama,
        save=args.save,
        output_dir=output_dir,
        region=args.region,
    )
    print(summary)
    if results and not args.save:
        print()
        print(results_to_markdown(results, title=f"Search: {query}")[:4000] + ("..." if len(results_to_markdown(results)) > 4000 else ""))


if __name__ == "__main__":
    main()
