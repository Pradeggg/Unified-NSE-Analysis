"""
Pipeline tools for the NSE sector research agent.
Each function is designed to be used as an Ollama tool: it returns a string summary
suitable for the model to reason over. Run from project root with working-sector on path.
"""
from __future__ import annotations

import sys
from pathlib import Path

WORKING_SECTOR = Path(__file__).resolve().parent
if str(WORKING_SECTOR) not in sys.path:
    sys.path.insert(0, str(WORKING_SECTOR))

# Lazy imports inside each tool to avoid loading heavy deps until needed


def _output_dir():
    """Output dir for current sector (from config)."""
    from config import OUTPUT_DIR
    return OUTPUT_DIR


def run_phase2() -> str:
    """
    Run Phase 2: load universe, NSE stock and index data, compute returns and relative strength,
    merge fundamentals. Produces universe metrics (one row per stock).
    Call this before Phase 3 if you need fresh data. Output: phase2_universe_metrics.csv.

    Returns:
        A short summary of what was done and how many rows were written.
    """
    try:
        from phase2_data import run_phase2 as _run
        df = _run()
        n = len(df)
        return f"Phase 2 completed successfully. Universe metrics: {n} stocks. Output: phase2_universe_metrics.csv"
    except Exception as e:
        return f"Phase 2 failed: {e!s}"


def run_phase3() -> str:
    """
    Run Phase 3: build composite score (fundamental + technical + RS rank), apply screens
    (FUND_SCORE >= 70, RS_6M > 0), produce shortlist (top 15 by composite).
    Requires Phase 2 output (phase2_universe_metrics.csv). Outputs: phase3_shortlist.csv,
    phase3_full_with_composite.csv.

    Returns:
        A short summary of shortlist size and files written.
    """
    try:
        from phase3_screens import run_phase3 as _run
        full_table, shortlist = _run()
        n_short = len(shortlist)
        n_full = len(full_table)
        return (
            f"Phase 3 completed successfully. Shortlist: {n_short} stocks (top by composite). "
            f"Full table with composite: {n_full} rows. Outputs: phase3_shortlist.csv, phase3_full_with_composite.csv"
        )
    except Exception as e:
        return f"Phase 3 failed: {e!s}"


def run_phase4() -> str:
    """
    Run Phase 4: backtest. At each monthly rebalance, apply momentum screen (RS_6M > 0),
    equal-weight portfolio, forward 1Y return vs Nifty 500. Uses only price-based criteria.
    Output: phase4_backtest_results.csv.

    Returns:
        A short summary of backtest results (e.g. mean excess return, hit rate).
    """
    try:
        from phase4_backtest import run_phase4 as _run
        df = _run()
        n = len(df)
        if df.empty:
            return "Phase 4 completed. No backtest rows (check data range). Output: phase4_backtest_results.csv"
        mean_excess = df["EXCESS_RET"].mean() * 100 if "EXCESS_RET" in df.columns and df["EXCESS_RET"].notna().any() else None
        hit = (df["EXCESS_RET"] > 0).sum() / max(1, df["EXCESS_RET"].notna().sum()) * 100 if "EXCESS_RET" in df.columns else None
        parts = [f"Phase 4 completed. Backtest: {n} rebalance dates. Output: phase4_backtest_results.csv"]
        if mean_excess is not None:
            parts.append(f"Mean excess return (1Y): {mean_excess:.2f}%")
        if hit is not None:
            parts.append(f"Hit rate (excess > 0): {hit:.0f}%")
        return ". ".join(parts)
    except Exception as e:
        return f"Phase 4 failed: {e!s}"


def run_phase5() -> str:
    """
    Run Phase 5: generate sector note (Markdown) and HTML dashboard from Phase 2–4 outputs.
    Produces sector_note.md and dashboard.html for the current sector.
    Requires Phase 2, 3, and 4 outputs to exist.

    Returns:
        A short summary of generated files.
    """
    try:
        from phase5_report import run_phase5 as _run
        _run()
        return (
            "Phase 5 completed successfully. Generated: sector_note.md, "
            "dashboard.html in output/."
        )
    except Exception as e:
        return f"Phase 5 failed: {e!s}"


def run_full_pipeline() -> str:
    """
    Run the full research pipeline: Phase 2 (data) -> Phase 3 (screens & shortlist) ->
    Phase 4 (backtest) -> Phase 5 (report & dashboard). Use this when the user wants
    to run everything in one go. Outputs go to working-sector/output/.

    Returns:
        A combined summary of all phases and output files.
    """
    try:
        from phase2_data import run_phase2
        from phase3_screens import run_phase3
        from phase4_backtest import run_phase4
        from phase5_report import run_phase5

        phase2_table = run_phase2()
        full_table, shortlist = run_phase3(phase2_table=phase2_table)
        backtest_df = run_phase4()
        run_phase5(phase2_table=phase2_table, shortlist=shortlist, backtest_df=backtest_df)

        return (
            f"Full pipeline completed. Phase 2: {len(phase2_table)} universe metrics. "
            f"Phase 3: shortlist {len(shortlist)} stocks. Phase 4: {len(backtest_df)} backtest dates. "
            "Phase 5: sector note and dashboard generated. Outputs in working-sector/output/<sector>/."
        )
    except Exception as e:
        return f"Full pipeline failed: {e!s}"


def list_outputs() -> str:
    """
    List the current pipeline output files for this sector (working-sector/output/<sector>/) with
    their sizes or row counts. Use this to show the user what outputs exist before or after running phases.

    Returns:
        A summary of existing output files (name, size or brief description).
    """
    output_dir = _output_dir()
    if not output_dir.exists():
        return "Output directory does not exist yet. Run Phase 2 or the full pipeline first."
    lines = [f"Pipeline outputs in {output_dir}:"]
    for f in sorted(output_dir.iterdir()):
        if f.is_file():
            size = f.stat().st_size
            if f.suffix.lower() == ".csv":
                try:
                    import pandas as pd
                    df = pd.read_csv(f, nrows=0)
                    # count lines for rough row count
                    with open(f, "rb") as fp:
                        n = sum(1 for _ in fp) - 1  # subtract header
                    lines.append(f"  {f.name}: {n} rows, {size:,} bytes")
                except Exception:
                    lines.append(f"  {f.name}: {size:,} bytes")
            else:
                lines.append(f"  {f.name}: {size:,} bytes")
    return "\n".join(lines)


def run_fetch_fundamental_scores() -> str:
    """
    Fetch EARNINGS_QUALITY, SALES_GROWTH, FINANCIAL_STRENGTH, INSTITUTIONAL_BACKING from Screener
    for any current-sector universe symbols missing from fundamental_scores_database.csv, and merge
    them in. Run before the pipeline so Phase 2 and narratives get the four sub-scores (like Auto
    Components). Requires R and core/screenerdata.R. If skipped or failed, pipeline continues;
    report will show fundamental strength only where the database already has the symbol.
    """
    try:
        import os
        import subprocess
        from config import UNIVERSE_CSV, OUTPUT_DIR, FUNDAMENTAL_CSV, WORKING_SECTOR, PROJECT_ROOT
        if not UNIVERSE_CSV.exists():
            return "No universe CSV; skip fundamental scores fetch."
        import pandas as pd
        universe_df = pd.read_csv(UNIVERSE_CSV)
        universe = universe_df["SYMBOL"].astype(str).str.strip().str.upper().tolist()
        existing = set()
        if FUNDAMENTAL_CSV.exists():
            fund_df = pd.read_csv(FUNDAMENTAL_CSV)
            if "symbol" in fund_df.columns:
                existing = set(fund_df["symbol"].astype(str).str.strip().str.upper())
        missing = [s for s in universe if s not in existing]
        if not missing:
            return f"All {len(universe)} universe symbols already in fundamental_scores_database. No fetch needed."
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        symbols_file = OUTPUT_DIR / "symbols_to_fetch.txt"
        symbols_file.write_text("\n".join(missing) + "\n", encoding="utf-8")
        r_script = WORKING_SECTOR / "fetch_screener_fundamentals.R"
        if not r_script.exists():
            return f"R script not found: {r_script}. Run pipeline anyway; report may miss fundamental strength for some symbols."
        result = subprocess.run(
            ["Rscript", str(r_script), str(symbols_file), str(FUNDAMENTAL_CSV)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=3600,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "")[:400]
            return f"Fundamental scores fetch failed: {err}. Run pipeline anyway; report may miss sub-scores for {len(missing)} symbols."
        return f"Fetched fundamental scores (earnings quality, sales growth, financial strength, institutional backing) for {len(missing)} symbols and merged into fundamental_scores_database. Run full pipeline next."
    except subprocess.TimeoutExpired:
        return "Fundamental scores fetch timed out. Run pipeline anyway; report may miss sub-scores."
    except FileNotFoundError:
        return "R not found (Rscript). Run pipeline anyway; report may miss fundamental strength table for symbols not already in database."
    except Exception as e:
        return f"Fundamental scores fetch failed: {e!s}. Run pipeline anyway."


def run_fetch_fundamental_details() -> str:
    """
    Fetch P&L, quarterly, balance sheet, and ratios from Screener.in for the current sector universe.
    Runs the R script fetch_screener_fundamental_details.R; writes fundamental_details.csv in the
    sector output dir. Run before run_narratives so the comprehensive report shows fundamental
    strength and financial ratios in each stock card. Requires R and core/screenerdata.R.

    Returns:
        Summary: path written and row count, or a message if R/script failed (pipeline continues).
    """
    try:
        import os
        import subprocess
        from config import OUTPUT_DIR, WORKING_SECTOR, SECTOR, PROJECT_ROOT
        out_csv = OUTPUT_DIR / "fundamental_details.csv"
        env = dict(os.environ)
        env["NSE_SECTOR"] = SECTOR
        r_script = WORKING_SECTOR / "fetch_screener_fundamental_details.R"
        if not r_script.exists():
            return f"R script not found: {r_script}. Fundamental details will be missing in narratives."
        result = subprocess.run(
            ["Rscript", str(r_script)],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "")[:500]
            return f"Fetch fundamental details (R script) failed: {err}. Narratives will run without P&L/ratios."
        if out_csv.exists():
            n = len(out_csv.read_text(encoding="utf-8").splitlines()) - 1
            return f"Fetched fundamental details for {n} symbols. Wrote {out_csv.name} in {OUTPUT_DIR}. Run run_narratives next."
        return "Fundamental details script ran; check output dir for fundamental_details.csv."
    except subprocess.TimeoutExpired:
        return "Fetch fundamental details timed out (10 min). Narratives will run without P&L/ratios."
    except FileNotFoundError:
        return "R not found (Rscript). Install R or skip; narratives will run without P&L/ratios in report."
    except Exception as e:
        return f"Fetch fundamental details failed: {e!s}. Narratives will run without P&L/ratios."


def run_narratives() -> str:
    """
    Generate stock narratives (Ollama Granite 4) for each stock in the Phase 3 shortlist/full table.
    Reads phase3_full_with_composite.csv and fundamental details (fundamental_details.csv); writes
    stock_narratives.md and stock_narratives.json. Run after Phase 3 (or full pipeline). For
    fundamental strength and ratios in the report, run run_fetch_fundamental_details first.
    Requires Ollama running.

    Returns:
        A short summary of how many narratives were written and output paths.
    """
    try:
        # Import and run main() from generate_stock_narratives
        import generate_stock_narratives as gen
        gen.main()
        out_dir = _output_dir()
        md_path = out_dir / "stock_narratives.md"
        json_path = out_dir / "stock_narratives.json"
        if md_path.exists():
            n_lines = len(md_path.read_text(encoding="utf-8").splitlines())
            return f"Narratives generated. Outputs: stock_narratives.md ({n_lines} lines), stock_narratives.json in {out_dir}."
        return "Narratives run completed. Check output directory for stock_narratives.md and .json."
    except Exception as e:
        return f"Narratives failed: {e!s}"


def run_comprehensive_report() -> str:
    """
    Build the comprehensive sector report (MD, HTML, XLSX) from pipeline outputs and stock narratives.
    Use after Phase 5 and run_narratives. Reads from current sector output dir; writes comprehensive_report.md,
    comprehensive_report.html, comprehensive_report.xlsx there.
    """
    try:
        import build_comprehensive_report as bcr
        bcr.main()
        out_dir = _output_dir()
        return (
            f"Comprehensive report built. Outputs in {out_dir}: "
            "comprehensive_report.md, comprehensive_report.html, comprehensive_report.xlsx"
        )
    except Exception as e:
        return f"Comprehensive report failed: {e!s}"


def download_nse_sector_universe(sector_key: str | None = None, use_nse_api: bool = True) -> str:
    """
    Download Plastics and Packaging (or current sector) stocks from NSE and save as <sector>_universe.csv.
    Uses NSE session + equity-stockIndices API when use_nse_api=True; otherwise uses curated list.
    Run this before the pipeline to refresh the universe for plastics_and_packaging (or set NSE_SECTOR).

    Args:
        sector_key: Sector key (e.g. plastics_and_packaging). If None, uses config.SECTOR.
        use_nse_api: If True, try NSE API first; if False or API fails, use curated list.

    Returns:
        Summary: path written and number of symbols.
    """
    try:
        from config import SECTOR, WORKING_SECTOR
        import nse_fetch_sector_universe as nse_fetch
        key = (sector_key or SECTOR).strip().lower().replace(" ", "_")
        path = nse_fetch.fetch_and_save(sector_key=key, output_path=WORKING_SECTOR / f"{key}_universe.csv", use_nse_api=use_nse_api)
        n_lines = len(path.read_text(encoding="utf-8").splitlines()) - 1  # exclude header
        return f"Downloaded {n_lines} symbols to {path.name}. Set NSE_SECTOR={key!r} and run the pipeline."
    except Exception as e:
        return f"Download NSE sector universe failed: {e!s}"


def web_search(
    query: str,
    engine: str = "duckduckgo",
    max_results: int = 10,
) -> str:
    """
    Run a single web search for sector research. Use for one-off lookups (market size, news, reports).
    Engines: duckduckgo (default, no key), google (optional), bing (needs BING_SEARCH_KEY).

    Args:
        query: Search query string.
        engine: duckduckgo, google, or bing.
        max_results: Max results to return (e.g. 10).

    Returns:
        Summary and top results (title, URL, snippet) as text.
    """
    try:
        import web_search as ws
        results = ws.search(query, engine=engine, max_results=max_results)
        results = [r for r in results if r.get("url") or r.get("snippet")]
        if not results:
            return f"Web search ('{query}'): no results (engine={engine})."
        summary = f"Web search: '{query}' — {len(results)} results (engine={engine}). Top 5:\n\n"
        for i, r in enumerate(results[:5], 1):
            summary += f"{i}. {r.get('title', '')}\n   {r.get('url', '')}\n   {r.get('snippet', '')[:300]}...\n\n"
        return summary.strip()
    except Exception as e:
        return f"Web search failed: {e!s}"


def web_search_iterative(
    topic: str,
    rounds: int = 2,
    engine: str = "duckduckgo",
    max_results_per_query: int = 8,
) -> str:
    """
    Run iterative web search: first round searches the topic; second round uses Ollama to suggest
    follow-up queries (emphasising latest data). Results are deduplicated and tagged with retrieved_date.
    Use for deeper research (e.g. sector outlook, market size, industry reports).

    Args:
        topic: Main search topic (e.g. "Auto components India market size 2025").
        rounds: Number of search rounds (2 = topic + follow-ups).
        engine: duckduckgo (default), google, or bing.
        max_results_per_query: Max results per query per round.

    Returns:
        Summary and aggregated results as text.
    """
    try:
        import web_search as ws
        results = ws.search_iterative(
            topic=topic,
            rounds=rounds,
            engine=engine,
            max_results_per_query=max_results_per_query,
            use_ollama=True,
        )
        if not results:
            return f"Iterative web search ('{topic}'): no results after {rounds} round(s)."
        summary = f"Iterative search: '{topic}' — {len(results)} unique results ({rounds} round(s), engine={engine}). Top 8:\n\n"
        for i, r in enumerate(results[:8], 1):
            rd = r.get("retrieved_date", "")
            summary += f"{i}. {r.get('title', '')}\n   {r.get('url', '')}\n   Retrieved: {rd}\n   {r.get('snippet', '')[:350]}...\n\n"
        return summary.strip()
    except Exception as e:
        return f"Iterative web search failed: {e!s}"


def run_sector_research(
    topic_query: str | None = None,
    rounds: int = 3,
    engine: str = "duckduckgo",
    engines: list[str] | None = None,
) -> str:
    """
    Run multi-step sector research: web search focused on LATEST data (current year, recent outlook),
    then LLM synthesis that cites sources and dates. Writes research_sources.md so the report and user
    can see data/research source and when it was retrieved. Use before or with the full pipeline so
    the sector note can reference research_sources.md.

    Args:
        topic_query: Optional search topic; if omitted, uses sector name + "India latest [year] market size outlook".
        rounds: Number of iterative search rounds (default 3 for broader coverage).
        engine: duckduckgo (default), google, or bing (used when engines is None).
        engines: If set, use only these engines (e.g. ["duckduckgo", "yahoo"] for DDGS + SerpAPI).

    Returns:
        Summary including: search date, number of sources, path to research_sources.md, and reminder that sources/dates are in the report.
    """
    try:
        from config import SECTOR_DISPLAY_NAME, OUTPUT_DIR, PHASE2_TABLE_CSV, SECTOR, WORKING_SECTOR
        import web_search as ws
        results, synthesis, research_sites_queried = ws.research_with_synthesis(
            sector_display_name=SECTOR_DISPLAY_NAME,
            topic_query=topic_query,
            rounds=rounds,
            engine=engine,
            engines=engines,
            max_results_per_query=8,
        )
        pipeline_as_of = None
        if PHASE2_TABLE_CSV.exists():
            try:
                import pandas as pd
                df = pd.read_csv(PHASE2_TABLE_CSV, nrows=1)
                if "AS_OF_DATE" in df.columns:
                    pipeline_as_of = str(df["AS_OF_DATE"].iloc[0])
            except Exception:
                pass
        path = ws.write_research_sources_md(
            output_dir=OUTPUT_DIR,
            sector_display_name=SECTOR_DISPLAY_NAME,
            synthesis=synthesis,
            results=results,
            pipeline_data_as_of=pipeline_as_of,
            research_sites_used=research_sites_queried,
        )
        # Generate sector narrative, hypothesis memo, and literature notes from research + LLM
        doc_paths = ws.write_sector_docs_from_research(
            working_sector_dir=WORKING_SECTOR,
            sector_key=SECTOR,
            sector_display_name=SECTOR_DISPLAY_NAME,
            synthesis=synthesis,
            results=results,
        )
        doc_list = ", ".join(p.name for p in doc_paths.values())
        return (
            f"Sector research completed. Multi-step search (rounds={rounds}) emphasised latest data; "
            f"additional targeted searches ran on {len(research_sites_queried)} Indian stock market, research and government sites. "
            f"Found {len(results)} sources; LLM synthesis cites each source and retrieval date. "
            f"Wrote {path.name} in {OUTPUT_DIR}. "
            f"Generated sector docs from research + LLM: {doc_list}. "
            "The sector note (Phase 5) and comprehensive report use these; research_sources.md lists all data and research sources with dates."
        )
    except Exception as e:
        return f"Sector research failed: {e!s}"


def get_phase_help() -> str:
    """
    Return a brief description of each pipeline phase (2–5), full pipeline, narratives, and web search.
    Use this when the user asks what the pipeline does or what each phase is for.
    """
    return """Pipeline phases (NSE sector research):
- Phase 2 (Data): Load universe, NSE stock/index data; compute returns (1M/3M/6M), relative strength vs Nifty 500, RSI, technical score; merge fundamentals. Output: phase2_universe_metrics.csv.
- Phase 3 (Screens): Composite score (0.4*fund + 0.4*tech + 0.2*RS rank); screen FUND_SCORE >= 70, RS_6M > 0; top 15 shortlist. Outputs: phase3_shortlist.csv, phase3_full_with_composite.csv.
- Phase 4 (Backtest): Monthly rebalance, momentum screen (RS_6M > 0), equal-weight portfolio, forward 1Y return vs Nifty 500. Output: phase4_backtest_results.csv.
- Phase 5 (Report): Sector note (Markdown) and HTML dashboard. Outputs: sector_note.md, dashboard.html.
- run_full_pipeline: Run Phase 2 -> 3 -> 4 -> 5 in sequence.
- run_narratives: Generate per-stock narratives (Ollama) after Phase 3; writes stock_narratives.md and .json.
- run_comprehensive_report: Build comprehensive report (MD, HTML, XLSX) from pipeline + narratives; use after Phase 5 and narratives.
- run_fetch_fundamental_scores: Fetch EARNINGS_QUALITY, SALES_GROWTH, FINANCIAL_STRENGTH, INSTITUTIONAL_BACKING from Screener for universe symbols missing from fundamental_scores_database; merge into DB. Run before run_full_pipeline so Phase 2 and narratives get the four sub-scores (like Auto Components report).
- run_fetch_fundamental_details: Fetch P&L, quarterly, balance sheet, ratios from Screener (R script); writes fundamental_details.csv in sector output. Run before run_narratives so the report shows fundamental strength and financial ratios per stock.
- download_nse_sector_universe: Download Plastics and Packaging (or current sector) stocks from NSE; writes <sector>_universe.csv. Use before pipeline for plastics_and_packaging.
- web_search: Single web search (duckduckgo/google/bing) for market size, news, reports.
- web_search_iterative: Multi-round search with emphasis on latest data; follow-ups suggest dated reports.
- run_sector_research: Multi-step research (latest-data search + LLM synthesis); writes research_sources.md with sources and dates so the report and user can verify data and research provenance."""


# Registry for the agent: name -> callable (for executing tool calls)
TOOL_FUNCTIONS = [
    run_phase2,
    run_phase3,
    run_phase4,
    run_phase5,
    run_full_pipeline,
    run_fetch_fundamental_scores,
    run_fetch_fundamental_details,
    run_narratives,
    run_comprehensive_report,
    download_nse_sector_universe,
    run_sector_research,
    web_search,
    web_search_iterative,
    list_outputs,
    get_phase_help,
]

def get_tool_by_name(name: str):
    """Return the function for a tool name, or None."""
    for f in TOOL_FUNCTIONS:
        if f.__name__ == name:
            return f
    return None
