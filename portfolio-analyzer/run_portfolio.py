#!/usr/bin/env python3
"""
Run the portfolio analyzer for a named portfolio with custom input/output paths.

Examples:
  python3 portfolio-analyzer/run_portfolio.py \
    --name friend_amit \
    --pnl ~/Downloads/friend_EQProfitLossDetails.csv \
    --cas ~/Downloads/friend_CAS.pdf

  python3 portfolio-analyzer/run_portfolio.py \
    --name friend_amit \
    --pnl ~/Downloads/friend_EQProfitLossDetails.csv \
    --holdings ~/Downloads/friend_holdings.csv \
    --no-sentiment
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from types import ModuleType


PORTFOLIO_ANALYZER = Path(__file__).resolve().parent
PROJECT_ROOT = PORTFOLIO_ANALYZER.parent
if str(PORTFOLIO_ANALYZER) not in sys.path:
    sys.path.insert(0, str(PORTFOLIO_ANALYZER))


OUTPUT_FILES = {
    "HOLDINGS_CSV_OUT": "holdings.csv",
    "CLOSED_PNL_CSV": "closed_pnl.csv",
    "PORTFOLIO_SUMMARY_JSON": "portfolio_summary.json",
    "PNL_SUMMARY_MD": "pnl_summary.md",
    "PNL_AGGREGATES_CSV": "pnl_aggregates.csv",
    "SECTOR_ASSESSMENT_MD": "sector_assessment.md",
    "TECHNICAL_BY_STOCK_CSV": "technical_by_stock.csv",
    "TECHNICAL_SUMMARY_MD": "technical_summary.md",
    "FUNDAMENTAL_BY_STOCK_CSV": "fundamental_by_stock.csv",
    "FUNDAMENTAL_DETAILS_CSV": "fundamental_details.csv",
    "CALL_TRANSCRIPTS_SUMMARY_CSV": "call_transcripts_summary.csv",
    "CREDIT_RATINGS_CSV": "credit_ratings.csv",
    "STOCK_NARRATIVES_JSON": "stock_narratives.json",
    "STOCK_NARRATIVES_MD": "stock_narratives.md",
    "LLM_STOCK_VIEWS_JSON": "llm_stock_views.json",
    "REPORT_MD": "portfolio_comprehensive_report.md",
    "REPORT_HTML": "portfolio_comprehensive_report.html",
    "REPORT_XLSX": "portfolio_comprehensive_report.xlsx",
    "RISK_METRICS_CSV": "risk_metrics.csv",
    "RISK_METRICS_JSON": "risk_metrics.json",
    "SCENARIO_PROJECTIONS_CSV": "scenario_projections.csv",
    "SCENARIO_NARRATIVE_MD": "scenario_narrative.md",
    "MARKET_SENTIMENT_MD": "market_sentiment.md",
    "MARKET_SENTIMENT_SOURCES_JSON": "market_sentiment_sources.json",
}


def slugify_name(name: str) -> str:
    """Convert a friendly portfolio name into a stable folder slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "portfolio"


def default_output_dir(name: str) -> Path:
    """Default per-portfolio output directory."""
    return PORTFOLIO_ANALYZER / "runs" / slugify_name(name)


def apply_runtime_config(
    config_module: ModuleType,
    *,
    pnl_csv: Path | None,
    output_dir: Path,
    cas_pdf: Path | None = None,
    holdings_csv: Path | None = None,
) -> None:
    """Patch config.py constants for this process before the pipeline imports phase modules."""
    config_module.PNL_CSV = Path(pnl_csv).expanduser() if pnl_csv is not None else None
    if cas_pdf is not None:
        config_module.CAS_PDF = Path(cas_pdf).expanduser()
    if holdings_csv is not None:
        config_module.HOLDINGS_CSV = Path(holdings_csv).expanduser()

    config_module.OUTPUT_DIR = Path(output_dir).expanduser()
    config_module.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for attr, filename in OUTPUT_FILES.items():
        setattr(config_module, attr, config_module.OUTPUT_DIR / filename)


def validate_inputs(args: argparse.Namespace) -> None:
    """Fail early with actionable path errors."""
    if args.pnl is None and args.cas is None and args.holdings is None:
        raise FileNotFoundError("provide at least one of --pnl, --cas, or --holdings")
    required = []
    if args.pnl is not None:
        required.append(("PnL CSV", args.pnl))
    optional = [("CAS PDF", args.cas), ("holdings CSV", args.holdings)]
    for label, path in required:
        if not path.expanduser().exists():
            raise FileNotFoundError(f"{label} not found: {path}")
    for label, path in optional:
        if path is not None and not path.expanduser().exists():
            raise FileNotFoundError(f"{label} not found: {path}")


def run_configured_pipeline(
    skip_sentiment: bool,
    comprehensive_sentiment: bool,
    require_pnl: bool,
    use_llm_mapping: bool,
    llm_mapping_model: str,
    use_llm_stock_views: bool = False,
    stock_view_model: str = "gpt-4o",
) -> str:
    """Run pipeline phases after runtime config has been applied."""
    import pipeline_tools

    if not skip_sentiment and require_pnl:
        return pipeline_tools.run_full_pipeline(comprehensive_sentiment=comprehensive_sentiment)

    results = [
        pipeline_tools.run_phase0(
            require_pnl=require_pnl,
            use_llm_mapping=use_llm_mapping,
            llm_mapping_model=llm_mapping_model,
        ),
        pipeline_tools.run_phase1(),
        pipeline_tools.run_phase2(),
        pipeline_tools.run_phase3(),
        pipeline_tools.run_phase4(),
        pipeline_tools.run_phase7_risk(),
        (
            "Market sentiment skipped by --no-sentiment."
            if skip_sentiment
            else pipeline_tools.run_market_sentiment(comprehensive=comprehensive_sentiment)
        ),
        pipeline_tools.run_phase5(),
    ]
    if use_llm_stock_views:
        import config
        import llm_stock_views

        llm_result = llm_stock_views.run_llm_stock_views(
            narratives_json=config.STOCK_NARRATIVES_JSON,
            output_json=config.LLM_STOCK_VIEWS_JSON,
            model=stock_view_model,
        )
        results.append(
            f"LLM stock views: {llm_result.get('n_views', 0)} views. "
            f"{llm_result.get('note', '')}".strip()
        )
    results.append(pipeline_tools.run_phase6())
    return "Full pipeline without sentiment done.\n" + "\n".join(results)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_portfolio.py",
        description="Run portfolio analysis for another portfolio without editing config.py.",
    )
    parser.add_argument("--name", help="Portfolio label used for the default output folder.")
    parser.add_argument("--pnl", type=Path, help="Broker equity PnL CSV.")
    parser.add_argument("--cas", type=Path, help="NSDL/CDSL CAS PDF for current holdings.")
    parser.add_argument("--holdings", type=Path, help="Manual holdings CSV, used before CAS PDF.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output directory. Defaults to portfolio-analyzer/runs/<name>.",
    )
    parser.add_argument(
        "--cas-password",
        help="CAS PDF password. Sets CAS_PDF_PASSWORD for this run only.",
    )
    parser.add_argument(
        "--no-sentiment",
        action="store_true",
        help="Skip web/LLM sentiment for a faster local-only report.",
    )
    parser.add_argument(
        "--simple-sentiment",
        action="store_true",
        help="Run market-level sentiment only instead of market + sector + stock sentiment.",
    )
    parser.add_argument(
        "--llm-mapping",
        action="store_true",
        help="Use GPT-4o to adjudicate unresolved/ambiguous broker symbol mappings.",
    )
    parser.add_argument(
        "--mapping-model",
        default="gpt-4o",
        help="OpenAI model for --llm-mapping. Defaults to gpt-4o.",
    )
    parser.add_argument(
        "--llm-stock-views",
        action="store_true",
        help="Use GPT-4o to add short-term/long-term MUST BUY/HOLD/MUST SELL views.",
    )
    parser.add_argument(
        "--stock-view-model",
        default="gpt-4o",
        help="OpenAI model for --llm-stock-views. Defaults to gpt-4o.",
    )
    args = parser.parse_args(argv)
    if not args.name:
        source = args.pnl or args.holdings or args.cas
        args.name = source.expanduser().stem if source is not None else "portfolio"
    if args.output is None:
        args.output = default_output_dir(args.name)
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        validate_inputs(args)
    except FileNotFoundError as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2

    if args.cas_password:
        os.environ["CAS_PDF_PASSWORD"] = args.cas_password
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
    except Exception:
        pass

    import config

    apply_runtime_config(
        config,
        pnl_csv=args.pnl,
        cas_pdf=args.cas,
        holdings_csv=args.holdings,
        output_dir=args.output,
    )

    result = run_configured_pipeline(
        skip_sentiment=args.no_sentiment,
        comprehensive_sentiment=not args.simple_sentiment,
        require_pnl=args.pnl is not None,
        use_llm_mapping=args.llm_mapping,
        llm_mapping_model=args.mapping_model,
        use_llm_stock_views=args.llm_stock_views,
        stock_view_model=args.stock_view_model,
    )
    print(result)
    print(f"\nOutput directory: {config.OUTPUT_DIR}")
    print(f"HTML report: {config.REPORT_HTML}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
