"""Backend runner for the /company-index command."""

from __future__ import annotations

import argparse
import shlex
import sqlite3
from pathlib import Path
from typing import Any

from .company_intelligence_db import init_company_intelligence_db, upsert_company
from .company_website_adapters import get_company_site_adapter
from .company_website_indexer import crawl_company_website, download_company_document, fetch_url


DEFAULT_DB_PATH = Path("data/company_intelligence/company_intelligence.db")
DEFAULT_DOCUMENT_ROOT = Path("data/company_intelligence/documents")
DEFAULT_WEBSITES = {
    "DMART": "https://www.dmartindia.com/investor-relationship",
}


def parse_company_index_args(command_args: str | list[str]) -> argparse.Namespace:
    tokens = shlex.split(command_args) if isinstance(command_args, str) else list(command_args)
    parser = argparse.ArgumentParser(prog="/company-index", add_help=False)
    parser.add_argument("symbol", nargs="?")
    parser.add_argument("--website", default="")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--max-pages", type=int, default=25)
    parser.add_argument("--include-documents", action="store_true")
    parser.add_argument("--seed-sitemap", action="store_true")
    parser.add_argument("--respect-robots", action="store_true")
    parser.add_argument("--no-respect-robots", dest="respect_robots", action="store_false")
    parser.add_argument("--adapter", choices=["auto", "none", "dmart"], default="auto")
    parser.add_argument("--document-limit", type=int, default=25)
    parser.add_argument("--stale-only", action="store_true")
    parser.set_defaults(respect_robots=True)
    args = parser.parse_args(tokens)
    if args.symbol:
        args.symbol = args.symbol.strip().upper()
    return args


def run_company_index(
    symbol: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    website: str = "",
    refresh: bool = False,
    max_pages: int = 25,
    include_documents: bool = False,
    respect_robots: bool = True,
    seed_sitemap: bool = False,
    adapter: str = "auto",
    document_limit: int = 25,
    document_root: str | Path = DEFAULT_DOCUMENT_ROOT,
    fetcher=fetch_url,
) -> dict[str, Any]:
    clean_symbol = symbol.strip().upper()
    if not clean_symbol:
        raise ValueError("symbol is required")
    base_url = website or DEFAULT_WEBSITES.get(clean_symbol, "")
    if not base_url:
        raise ValueError(f"website is required for {clean_symbol}")

    path = init_company_intelligence_db(db_path)
    with sqlite3.connect(path) as conn:
        upsert_company(conn, clean_symbol, website=base_url)
        crawl_result = crawl_company_website(
            conn,
            clean_symbol,
            base_url,
            fetcher=fetcher,
            max_pages=max_pages,
            max_depth=1,
            include_documents=include_documents,
            respect_robots=respect_robots,
            seed_sitemap=seed_sitemap,
            document_root=document_root if include_documents else None,
        )

        selected_adapter = _select_adapter(adapter, clean_symbol, base_url)
        adapter_docs: list[dict[str, Any]] = []
        download_results: list[dict[str, Any]] = []
        if selected_adapter is not None:
            adapter_docs = selected_adapter.discover_documents(fetcher=fetcher, limit=document_limit)
            if include_documents:
                for doc in adapter_docs:
                    download_results.append(
                        download_company_document(
                            conn,
                            clean_symbol,
                            doc["url"],
                            doc["document_type"],
                            fetcher=fetcher,
                            root_dir=document_root,
                        )
                    )

    return {
        "symbol": clean_symbol,
        "db_path": str(path),
        "website": base_url,
        "refresh": bool(refresh),
        "crawl": crawl_result,
        "adapter": getattr(selected_adapter, "name", ""),
        "adapter_documents_found": len(adapter_docs),
        "documents_downloaded": sum(1 for item in download_results if item.get("status") == "downloaded"),
        "documents_cached": sum(1 for item in download_results if item.get("status") == "cached"),
        "document_errors": [item for item in download_results if item.get("status") == "error"],
    }


def run_company_index_from_args(
    command_args: str | list[str],
    db_path: str | Path = DEFAULT_DB_PATH,
    document_root: str | Path = DEFAULT_DOCUMENT_ROOT,
    fetcher=fetch_url,
) -> dict[str, Any]:
    args = parse_company_index_args(command_args)
    if args.stale_only:
        raise NotImplementedError("--stale-only is reserved for the scheduled index job")
    return run_company_index(
        args.symbol or "",
        db_path=db_path,
        website=args.website,
        refresh=args.refresh,
        max_pages=args.max_pages,
        include_documents=args.include_documents,
        respect_robots=args.respect_robots,
        seed_sitemap=args.seed_sitemap,
        adapter=args.adapter,
        document_limit=args.document_limit,
        document_root=document_root,
        fetcher=fetcher,
    )


def _select_adapter(adapter: str, symbol: str, base_url: str):
    selected = (adapter or "auto").lower()
    if selected == "none":
        return None
    if selected == "dmart":
        from company_website_adapters import DmartInvestorAdapter

        return DmartInvestorAdapter()
    return get_company_site_adapter(symbol, base_url)
