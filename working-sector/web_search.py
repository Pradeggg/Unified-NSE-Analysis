#!/usr/bin/env python3
"""
Web search script: multiple search engines and iterative search for sector research.

Engines: duckduckgo (default, no API key), google (optional, googlesearch-python),
bing (optional, requires BING_SEARCH_KEY env). Iterative search runs initial query,
then optionally uses Ollama to suggest follow-up queries from snippets and runs
another round; results are deduplicated by URL.

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
from pathlib import Path

WORKING_SECTOR = Path(__file__).resolve().parent
if str(WORKING_SECTOR) not in sys.path:
    sys.path.insert(0, str(WORKING_SECTOR))

# Result shape: list of {"title", "url", "snippet"}
ResultItem = dict


def search_duckduckgo(query: str, max_results: int = 10, region: str = "in-en") -> list[ResultItem]:
    """Search DuckDuckGo. No API key. Region in-en for India."""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return [{"title": "Error", "url": "", "snippet": "Install: pip install duckduckgo-search"}]
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


ENGINES = {
    "duckduckgo": search_duckduckgo,
    "google": search_googlesearch,
    "bing": search_bing,
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
        engine: One of duckduckgo, google, bing.
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


def suggest_follow_up_queries(
    topic: str,
    snippets: list[str],
    num_queries: int = 2,
    model: str = "granite4:latest",
) -> list[str]:
    """Use Ollama to suggest 1–2 follow-up search queries from topic and initial snippets."""
    try:
        from ollama import chat
    except ImportError:
        return []
    text = "\n\n".join((s[:500] for s in snippets[:5] if s))
    prompt = (
        f"Topic: {topic}\n\nFirst search result snippets (excerpts):\n{text}\n\n"
        "Suggest exactly 1 or 2 short, specific web search queries to find more detail "
        "(e.g. market size, recent news, reports). Reply with only the queries, one per line, no numbering or extra text."
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


def search_iterative(
    topic: str,
    rounds: int = 2,
    engine: str = "duckduckgo",
    max_results_per_query: int = 8,
    use_ollama: bool = True,
    region: str = "in-en",
) -> list[ResultItem]:
    """
    Iterative search: round 1 = search topic; round 2+ = optional follow-up queries via Ollama.

    Args:
        topic: Main search topic (first query).
        rounds: Number of search rounds (1 = single query).
        engine: Search engine to use.
        max_results_per_query: Max results per query.
        use_ollama: If True and rounds > 1, use Ollama to suggest follow-up queries from round 1 snippets.
        region: DuckDuckGo region.

    Returns:
        Deduplicated list of results (title, url, snippet).
    """
    all_results: list[ResultItem] = []
    queries_done: list[str] = []

    # Round 1
    first = search(topic, engine=engine, max_results=max_results_per_query, region=region)
    first = [r for r in first if r.get("snippet") or r.get("url")]
    all_results.extend(first)
    queries_done.append(topic)

    for _ in range(rounds - 1):
        if use_ollama and all_results:
            snippets = [r.get("snippet", "") for r in all_results[:10] if r.get("snippet")]
            follow_ups = suggest_follow_up_queries(topic, snippets, num_queries=2)
            for q in follow_ups:
                if q and q not in queries_done:
                    queries_done.append(q)
                    more = search(q, engine=engine, max_results=max_results_per_query, region=region)
                    more = [r for r in more if r.get("snippet") or r.get("url")]
                    all_results.extend(more)
        else:
            break

    return dedupe_by_url(all_results)


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
