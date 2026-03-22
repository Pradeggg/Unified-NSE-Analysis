#!/usr/bin/env python3
"""
Market sentiment: comprehensive sector-level and stock-level research (news, broker reports).

Uses iterative search with both DDGS (DuckDuckGo) and SERP (Google; optional SerpAPI).
Outputs: market-level + per-sector + per-stock sentiment with cited sources and dates.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

PORTFOLIO_ANALYZER = Path(__file__).resolve().parent
PROJECT_ROOT = PORTFOLIO_ANALYZER.parent
WORKING_SECTOR = PROJECT_ROOT / "working-sector"
if str(WORKING_SECTOR) not in sys.path:
    sys.path.insert(0, str(WORKING_SECTOR))

try:
    from config import OUTPUT_DIR, MARKET_SENTIMENT_MD, MARKET_SENTIMENT_SOURCES_JSON
except ImportError:
    OUTPUT_DIR = PORTFOLIO_ANALYZER / "output"
    MARKET_SENTIMENT_MD = OUTPUT_DIR / "market_sentiment.md"
    MARKET_SENTIMENT_SOURCES_JSON = OUTPUT_DIR / "market_sentiment_sources.json"

# Iterative search: use both DDGS (DuckDuckGo) and SERP. Google = googlesearch-python; for SerpAPI set SERPAPI_API_KEY and add "yahoo" for extra coverage.
SENTIMENT_ENGINES = ["duckduckgo", "google"]
if os.environ.get("SERPAPI_API_KEY"):
    SENTIMENT_ENGINES = ["duckduckgo", "google", "yahoo"]  # yahoo uses SerpAPI


def _search_iterative(topic: str, rounds: int = 3, max_results: int = 10) -> list:
    """Iterative search using both DDGS and SERP (engines list). Merge and dedupe."""
    try:
        import web_search as ws
        return ws.search_iterative(
            topic=topic,
            rounds=rounds,
            engines=SENTIMENT_ENGINES,
            max_results_per_query=max_results,
            use_ollama=False,
            region="in-en",
        )
    except Exception:
        return []


def _synthesize(text_context: str, instruction: str, model: str = "granite4:latest") -> str:
    """LLM synthesis with strict cite-sources instruction."""
    try:
        from ollama import chat
    except ImportError:
        return "(Ollama not available. Install ollama and run: ollama pull granite4.)"
    prompt = (
        f"{instruction}\n\n"
        "Use ONLY the following search results. Add 'Sources (retrieved [date]):' and list each as: Title – URL. "
        "If you add any fact not from the excerpts, mark: '(LLM general knowledge; verify for current use.)'\n\n"
        f"Search results:\n\n{text_context}"
    )
    try:
        r = chat(model=model, messages=[{"role": "user", "content": prompt}], options={"temperature": 0.3})
        return (r.message.content or "").strip()
    except Exception as e:
        return f"(Synthesis failed: {e})"


def _results_to_context(results: list, max_items: int = 15) -> str:
    retrieved = results[0].get("retrieved_date", date.today().isoformat()) if results else date.today().isoformat()
    return "\n\n".join(
        f"{i}. Title: {r.get('title', '')}\n   URL: {r.get('url', '')}\n   Retrieved: {r.get('retrieved_date', retrieved)}\n   Excerpt: {(r.get('snippet') or '')[:400]}"
        for i, r in enumerate(results[:max_items], 1)
    )


def run_market_sentiment(
    topic_query: str | None = None,
    portfolio_context: str | None = None,
    rounds: int = 3,
    max_results: int = 10,
    model: str = "granite4:latest",
) -> tuple[str, list]:
    """
    Run iterative web search (DDGS + SERP) for market-level sentiment, then LLM synthesis.
    Writes market_sentiment.md and market_sentiment_sources.json.
    """
    current_year = str(date.today().year)
    topic = (topic_query or "").strip() or f"India equity market Nifty 50 outlook sentiment {current_year} latest news broker report"
    results = _search_iterative(topic, rounds=rounds, max_results=max_results)
    for r in results:
        r.setdefault("retrieved_date", date.today().isoformat())
    context = _results_to_context(results)
    instruction = (
        "You are writing a short MARKET SENTIMENT note for an Indian equity portfolio holder. "
        "Summarise in 3–5 sentences: current India equity outlook (bullish/bearish/neutral), key themes (rates, earnings, global), and major risks. "
        "Use numbers and dates from the excerpts. If portfolio context is provided, add 1–2 sentences on how this relates to the portfolio (sector tilt, beta, concentration)."
    )
    synthesis = _synthesize(context, instruction, model=model)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MARKET_SENTIMENT_MD.write_text(synthesis, encoding="utf-8")
    with open(MARKET_SENTIMENT_SOURCES_JSON, "w", encoding="utf-8") as f:
        json.dump([{"title": r.get("title"), "url": r.get("url"), "retrieved_date": r.get("retrieved_date")} for r in results], f, indent=2)
    return synthesis, results


def run_sector_sentiment(sector_name: str, rounds: int = 2, max_results: int = 8, model: str = "granite4:latest") -> tuple[str, list]:
    """Sector-level sentiment: iterative search (DDGS + SERP) for sector outlook, broker reports, then LLM synthesis."""
    topic = f"{sector_name} sector India outlook 2026 broker report CRISIL news"
    results = _search_iterative(topic, rounds=rounds, max_results=max_results)
    for r in results:
        r.setdefault("retrieved_date", date.today().isoformat())
    context = _results_to_context(results, max_items=12)
    instruction = f"Summarise in 2–4 sentences the current sentiment and outlook for the {sector_name} sector in India. Use broker reports, news and research excerpts. Cite key numbers and dates."
    return _synthesize(context, instruction, model=model), results


def run_stock_sentiment(symbol: str, company_name: str | None = None, rounds: int = 2, max_results: int = 8, model: str = "granite4:latest") -> tuple[str, list]:
    """Stock-level sentiment: news and broker research for one stock. company_name optional for better query."""
    name = company_name or symbol
    topic = f"{name} {symbol} stock news analyst report earnings India"
    results = _search_iterative(topic, rounds=rounds, max_results=max_results)
    for r in results:
        r.setdefault("retrieved_date", date.today().isoformat())
    context = _results_to_context(results, max_items=12)
    instruction = f"Summarise in 2–3 sentences the latest news and analyst view for {name} ({symbol}). Use excerpts only; cite sources and dates."
    return _synthesize(context, instruction, model=model), results


def run_comprehensive_sentiment(
    sector_names: list[str] | None = None,
    stock_symbols: list[str] | None = None,
    portfolio_context: str | None = None,
    rounds: int = 2,
    max_results: int = 8,
    model: str = "granite4:latest",
) -> tuple[str, list]:
    """
    Comprehensive sentiment: market-level + sector-level (for each sector) + stock-level (for each symbol).
    Uses iterative search with DDGS + SERP throughout. Writes market_sentiment.md with sections and combined sources.
    """
    all_sources = []
    sections = []
    current_year = str(date.today().year)

    # Market-level (same logic as run_market_sentiment but no write)
    topic_market = f"India equity market Nifty 50 outlook sentiment {current_year} latest news broker report"
    res_market = _search_iterative(topic_market, rounds=rounds, max_results=max_results)
    for r in res_market:
        r.setdefault("retrieved_date", date.today().isoformat())
    ctx_market = _results_to_context(res_market)
    inst_market = (
        "Summarise in 3–5 sentences the current India equity market sentiment: outlook, key themes, risks. "
        "If portfolio context is provided below, add 1–2 sentences on how it relates to the portfolio. Cite sources and dates.\n\n"
        f"Portfolio context: {portfolio_context or 'Not provided.'}"
    )
    syn_market = _synthesize(ctx_market, inst_market, model=model)
    sections.append(("Market (India equity, Nifty)", syn_market))
    all_sources.extend([{"scope": "market", "title": r.get("title"), "url": r.get("url"), "retrieved_date": r.get("retrieved_date")} for r in res_market])

    # Sector-level
    for sector in sector_names or []:
        syn, res = run_sector_sentiment(sector, rounds=rounds, max_results=max_results, model=model)
        sections.append((f"Sector: {sector}", syn))
        all_sources.extend([{"scope": f"sector_{sector}", **{k: r.get(k) for k in ("title", "url", "retrieved_date")}} for r in res])

    # Stock-level
    for sym in stock_symbols or []:
        syn, res = run_stock_sentiment(sym, rounds=rounds, max_results=max_results, model=model)
        sections.append((f"Stock: {sym}", syn))
        all_sources.extend([{"scope": f"stock_{sym}", **{k: r.get(k) for k in ("title", "url", "retrieved_date")}} for r in res])

    # Single MD: Market + Sector + Stock
    lines = ["# Market sentiment and research (comprehensive)", "", "Sources: iterative search (DDGS + SERP). All sections cite retrieval dates.", ""]
    for title, body in sections:
        lines.append(f"## {title}")
        lines.append("")
        lines.append(body)
        lines.append("")
    full_text = "\n".join(lines)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MARKET_SENTIMENT_MD.write_text(full_text, encoding="utf-8")
    with open(MARKET_SENTIMENT_SOURCES_JSON, "w", encoding="utf-8") as f:
        json.dump(all_sources, f, indent=2)
    return full_text, all_sources


def get_portfolio_context_for_sentiment() -> str:
    """Build portfolio context from Phase 0/7 outputs."""
    try:
        from config import PORTFOLIO_SUMMARY_JSON, RISK_METRICS_JSON
    except ImportError:
        PORTFOLIO_SUMMARY_JSON = OUTPUT_DIR / "portfolio_summary.json"
        RISK_METRICS_JSON = OUTPUT_DIR / "risk_metrics.json"
    ctx = []
    if PORTFOLIO_SUMMARY_JSON.exists():
        d = json.loads(PORTFOLIO_SUMMARY_JSON.read_text(encoding="utf-8"))
        ctx.append(f"Holdings: {d.get('holdings_count', 0)}; closed trades: {d.get('closed_trades_count', 0)}; realized PnL: Rs {d.get('total_realized_pnl')}")
    if RISK_METRICS_JSON.exists():
        d = json.loads(RISK_METRICS_JSON.read_text(encoding="utf-8"))
        ctx.append(f"Beta (Nifty): {d.get('beta_nifty')}; volatility (ann. %): {d.get('portfolio_volatility_annual_pct')}; Sharpe: {d.get('sharpe_ratio')}")
    return " ".join(ctx) if ctx else ""


def get_sectors_and_symbols_from_holdings() -> tuple[list[str], list[str]]:
    """Return (sector_names, stock_symbols) from holdings or closed_pnl for comprehensive sentiment."""
    sectors = []
    symbols = []
    try:
        from config import HOLDINGS_CSV_OUT, CLOSED_PNL_CSV
    except ImportError:
        HOLDINGS_CSV_OUT = OUTPUT_DIR / "holdings.csv"
        CLOSED_PNL_CSV = OUTPUT_DIR / "closed_pnl.csv"
    if HOLDINGS_CSV_OUT.exists():
        import pandas as pd
        df = pd.read_csv(HOLDINGS_CSV_OUT)
        if "symbol" in df.columns:
            symbols = df["symbol"].dropna().astype(str).str.strip().str.upper().unique().tolist()
        if "sector" in df.columns:
            sectors = df["sector"].dropna().astype(str).str.strip().unique().tolist()
    if not symbols and CLOSED_PNL_CSV.exists():
        import pandas as pd
        df = pd.read_csv(CLOSED_PNL_CSV)
        if "symbol" in df.columns:
            symbols = df["symbol"].dropna().astype(str).str.strip().str.upper().unique().tolist()[:20]
    return sectors, symbols


if __name__ == "__main__":
    context = get_portfolio_context_for_sentiment()
    sectors, symbols = get_sectors_and_symbols_from_holdings()
    if sectors or symbols:
        syn, sources = run_comprehensive_sentiment(sector_names=sectors, stock_symbols=symbols[:15], portfolio_context=context)
        print("Comprehensive sentiment done (market + sector + stock).")
    else:
        syn, sources = run_market_sentiment(portfolio_context=context)
        print("Market sentiment done.")
    print(f"  Output: {MARKET_SENTIMENT_MD}")
    print(f"  Sources: {len(sources)} -> {MARKET_SENTIMENT_SOURCES_JSON}")
