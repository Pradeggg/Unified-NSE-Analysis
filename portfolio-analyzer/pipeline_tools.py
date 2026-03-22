"""
Pipeline tools for the portfolio analyzer agent.

Tools: run_phase0–6, run_phase7_risk, run_market_sentiment, web_search, web_search_iterative,
list_outputs, run_full_pipeline. Agent uses these via tool calling (Ollama/OpenAI).
"""
from __future__ import annotations

import sys
from pathlib import Path

PORTFOLIO_ANALYZER = Path(__file__).resolve().parent
if str(PORTFOLIO_ANALYZER) not in sys.path:
    sys.path.insert(0, str(PORTFOLIO_ANALYZER))


def _output_dir() -> Path:
    from config import OUTPUT_DIR
    return OUTPUT_DIR


def run_phase0() -> str:
    """Run Phase 0: Ingest PnL CSV (and optional holdings) → holdings.csv, closed_pnl.csv, portfolio_summary.json."""
    try:
        from phase0_ingest import run_phase0 as _run
        closed, holdings, summary = _run()
        return f"Phase 0 done. Closed PnL: {len(closed)} rows. Holdings: {len(holdings) if holdings is not None else 0}. Total realized PnL: Rs {summary.get('total_realized_pnl')}. Outputs: holdings.csv, closed_pnl.csv, portfolio_summary.json"
    except Exception as e:
        return f"Phase 0 failed: {e!s}"


def run_phase1() -> str:
    """Run Phase 1: PnL aggregation and summary → pnl_summary.md, pnl_aggregates.csv."""
    try:
        from config import PNL_SUMMARY_MD, PNL_AGGREGATES_CSV, CLOSED_PNL_CSV
        import pandas as pd
        if not CLOSED_PNL_CSV.exists():
            return "Phase 1 skipped: run Phase 0 first (no closed_pnl.csv)."
        df = pd.read_csv(CLOSED_PNL_CSV)
        agg = df.groupby(["symbol", "tenure_bucket"]).agg({"pnl": "sum", "qty": "sum"}).reset_index()
        agg.to_csv(PNL_AGGREGATES_CSV, index=False)
        total = df["pnl"].sum()
        lines = [f"# PnL summary\n", f"Total realized PnL: Rs {total:.2f}\n", f"Trades: {len(df)}\n", "See pnl_aggregates.csv for per-symbol, per-tenure.\n"]
        PNL_SUMMARY_MD.write_text("".join(lines), encoding="utf-8")
        return f"Phase 1 done. Total PnL: Rs {total:.2f}. Outputs: pnl_summary.md, pnl_aggregates.csv"
    except Exception as e:
        return f"Phase 1 failed: {e!s}"


def run_phase2() -> str:
    """Run Phase 2: Sectoral assessment → sector_assessment.md."""
    try:
        from phase2_sectoral import run_phase2 as _run
        summary = _run()
        return f"Phase 2 done. Stocks: {summary.get('n_stocks', 0)}; sectors: {summary.get('n_sectors', 0)}. Outputs: sector_assessment.md"
    except Exception as e:
        return f"Phase 2 failed: {e!s}"


def run_phase3() -> str:
    """Run Phase 3: Technical analysis per holding → technical_by_stock.csv, technical_summary.md."""
    try:
        from phase3_technical import run_phase3 as _run
        summary = _run()
        return f"Phase 3 done. Stocks: {summary.get('n_stocks', 0)}. Outputs: technical_by_stock.csv, technical_summary.md"
    except Exception as e:
        return f"Phase 3 failed: {e!s}"


def run_phase4() -> str:
    """Run Phase 4: Fundamental analysis (scores, P&L/BS/ratios; optional call transcripts and credit ratings from NSE/Screener). Outputs: fundamental_by_stock.csv, fundamental_details.csv."""
    try:
        from phase4_fundamental import run_phase4 as _run
        summary = _run()
        return f"Phase 4 done. Stocks: {summary.get('n_stocks', 0)}; with fundamentals: {summary.get('n_with_fundamentals', 0)}. Outputs: fundamental_by_stock.csv. {summary.get('note', '')}"
    except Exception as e:
        return f"Phase 4 failed: {e!s}"


def run_phase5() -> str:
    """Run Phase 5: Stock narratives → stock_narratives.json, stock_narratives.md."""
    try:
        from phase5_narratives import run_phase5 as _run
        summary = _run()
        return f"Phase 5 done. Stocks: {summary.get('n_stocks', 0)}. Outputs: stock_narratives.json, stock_narratives.md"
    except Exception as e:
        return f"Phase 5 failed: {e!s}"


def run_phase6() -> str:
    """Run Phase 6: Comprehensive report → portfolio_comprehensive_report.md, .html."""
    try:
        from phase6_report import run_phase6 as _run
        summary = _run()
        return f"Phase 6 done. Outputs: {summary.get('report_md', '')}, {summary.get('report_html', '')}"
    except Exception as e:
        return f"Phase 6 failed: {e!s}"


def run_phase7_risk() -> str:
    """Run Phase 7: Risk metrics (VaR, Sharpe, beta, drawdown, concentration) + scenario projections. Writes risk_metrics.csv, risk_metrics.json, scenario_projections.csv, scenario_narrative.md."""
    try:
        from phase7_risk import run_phase7
        summary = run_phase7()
        return (
            f"Phase 7 done. Volatility (ann. %): {summary.get('portfolio_volatility_annual_pct')}; "
            f"VaR 95% 1d: {summary.get('var_95_1d_pct')}%; Sharpe: {summary.get('sharpe_ratio')}; "
            f"Beta: {summary.get('beta_nifty')}; Max DD: {summary.get('max_drawdown_pct')}%. "
            "Outputs: risk_metrics.csv, risk_metrics.json, scenario_projections.csv, scenario_narrative.md"
        )
    except Exception as e:
        return f"Phase 7 failed: {e!s}"


def run_market_sentiment(topic_query: str | None = None, comprehensive: bool = False) -> str:
    """Run market sentiment: iterative search (DDGS + SERP). If comprehensive=True, runs sector-level and stock-level sentiment too. Writes market_sentiment.md, market_sentiment_sources.json."""
    try:
        from market_sentiment import (
            run_market_sentiment as _run_simple,
            run_comprehensive_sentiment,
            get_portfolio_context_for_sentiment,
            get_sectors_and_symbols_from_holdings,
        )
        context = get_portfolio_context_for_sentiment()
        if comprehensive:
            sectors, symbols = get_sectors_and_symbols_from_holdings()
            syn, sources = run_comprehensive_sentiment(sector_names=sectors, stock_symbols=symbols[:15], portfolio_context=context)
            return f"Comprehensive sentiment done (market + sector + stock). Sections: {len(sectors) + len(symbols) + 1}. Sources: {len(sources)}. Outputs: market_sentiment.md, market_sentiment_sources.json"
        syn, res = _run_simple(portfolio_context=context, topic_query=topic_query or None)
        return f"Market sentiment done. Synthesis: {len(syn)} chars. Sources: {len(res)}. Outputs: market_sentiment.md, market_sentiment_sources.json"
    except Exception as e:
        return f"Market sentiment failed: {e!s}"


def web_search(query: str, engine: str = "duckduckgo", max_results: int = 10) -> str:
    """Single web search (India markets, Nifty, sectors). Use for quick lookups or to build context for sentiment."""
    try:
        sys.path.insert(0, str(PORTFOLIO_ANALYZER.parent / "working-sector"))
        import web_search as ws
        results = ws.search(query, engine=engine, max_results=max_results, region="in-en")
        results = [r for r in results if r.get("url") or r.get("snippet")]
        from datetime import date
        for r in results:
            r["retrieved_date"] = date.today().isoformat()
        summary = "\n".join([f"- {r.get('title', '')} | {r.get('url', '')}" for r in results[:15]])
        return f"Search: '{query}'\n\nResults ({len(results)}):\n{summary}"
    except Exception as e:
        return f"Web search failed: {e!s}"


def web_search_iterative(topic: str, rounds: int = 3, max_results: int = 10) -> str:
    """Iterative multi-round web search using both DDGS (DuckDuckGo) and SERP (Google; optional Yahoo/SerpAPI). For deeper market/sector/stock research."""
    try:
        sys.path.insert(0, str(PORTFOLIO_ANALYZER.parent / "working-sector"))
        import web_search as ws
        engines = ["duckduckgo", "google"]
        if __import__("os").environ.get("SERPAPI_API_KEY"):
            engines.append("yahoo")
        results = ws.search_iterative(topic=topic, rounds=rounds, engines=engines, max_results_per_query=max_results, use_ollama=False, region="in-en")
        results = [r for r in results if r.get("url") or r.get("snippet")]
        summary = "\n".join([f"- {r.get('title', '')} | {r.get('url', '')}" for r in results[:20]])
        return f"Iterative search (DDGS + SERP): '{topic}' ({len(results)} results):\n{summary}"
    except Exception as e:
        return f"Web search iterative failed: {e!s}"


def list_outputs() -> str:
    """List portfolio-analyzer output files and sizes."""
    out = _output_dir()
    if not out.exists():
        return "Output dir does not exist. Run Phase 0 first."
    lines = []
    for f in sorted(out.iterdir()):
        if f.is_file():
            lines.append(f"{f.name}: {f.stat().st_size} bytes")
    return "Output files:\n" + "\n".join(lines) if lines else "No files in output yet."


def run_full_pipeline(comprehensive_sentiment: bool = True) -> str:
    """Run full pipeline: Phase 0 → 1 → 2 → 3 → 4 → 7 → market sentiment → 5 → 6 (comprehensive report)."""
    try:
        r0 = run_phase0()
        r1 = run_phase1()
        r2 = run_phase2()
        r3 = run_phase3()
        r4 = run_phase4()
        r7 = run_phase7_risk()
        r_sent = run_market_sentiment(comprehensive=comprehensive_sentiment)
        r5 = run_phase5()
        r6 = run_phase6()
        return (
            f"Full pipeline (0→1→2→3→4→7→sentiment→5→6) done. Comprehensive report generated.\n"
            f"{r0}\n{r1}\n{r2}\n{r3}\n{r4}\n{r7}\n{r_sent}\n{r5}\n{r6}"
        )
    except Exception as e:
        return f"Full pipeline failed: {e!s}"


# Tool list for Ollama/OpenAI: name -> callable
TOOL_FUNCTIONS = {
    "run_phase0": run_phase0,
    "run_phase1": run_phase1,
    "run_phase2": run_phase2,
    "run_phase3": run_phase3,
    "run_phase4": run_phase4,
    "run_phase5": run_phase5,
    "run_phase6": run_phase6,
    "run_phase7_risk": run_phase7_risk,
    "run_market_sentiment": run_market_sentiment,
    "web_search": web_search,
    "web_search_iterative": web_search_iterative,
    "list_outputs": list_outputs,
    "run_full_pipeline": run_full_pipeline,
}


def get_tool_by_name(name: str):
    return TOOL_FUNCTIONS.get(name)
