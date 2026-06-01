"""Knowledge Base pipeline for Agent Adda — financial sources → vector DB.

Pipeline stages:
    fetch    → download PDFs/HTML from data/financial_sources_registry.json
    chunk    → split documents into logical, semantic chunks with provenance
    qa       → generate Q&A pairs for each chunk (LLM gpt-4o-mini)
    index    → embed and store in ChromaDB
    query    → semantic search the knowledge base

Layout on disk:
    data/knowledge_base/
        raw/<source_id>/<YYYY-MM-DD>/<filename>     # downloaded artefacts
        manifest.jsonl                              # one row per fetch attempt
        chunks.jsonl                                # one row per chunk + metadata
        qa.jsonl                                    # generated Q&A pairs
        chroma/                                     # persistent ChromaDB store

PG-kb: kept self-contained so it can be invoked from nse_agent.py via /kb command.
"""
from __future__ import annotations

# Submodules re-exported for convenience.
from .registry import load_registry, iter_sources        # noqa: F401
from .fetcher import fetch_source, fetch_all             # noqa: F401
from .chunker import chunk_document                      # noqa: F401
from .qa_generator import generate_qa_for_chunk          # noqa: F401
from .vector_store import KBVectorStore                  # noqa: F401
from .pipeline import run_pipeline, query_kb             # noqa: F401
# PG 2026-05-27: ad-hoc single-document ingest (broker reports, etc.)
from .ingest import ingest_pdf_url, ingest_local_pdf, ingest_any  # noqa: F401
# PG 2026-05-27: broker-vs-DB critique with LLM verdict
from .critique import critique_report, fetch_db_snapshot  # noqa: F401
# PG 2026-05-27: multi-turn grounded chat about a symbol
from .chat import SymbolChatSession  # noqa: F401
# PG 2026-05-27: DuckDuckGo discovery + auto-ingest of broker PDFs
from .research import research_symbol, search_research_reports  # noqa: F401

__all__ = [
    "load_registry", "iter_sources",
    "fetch_source", "fetch_all",
    "chunk_document",
    "generate_qa_for_chunk",
    "KBVectorStore",
    "run_pipeline", "query_kb",
    "ingest_pdf_url", "ingest_local_pdf", "ingest_any",
    "critique_report", "fetch_db_snapshot",
    "SymbolChatSession",
    "research_symbol", "search_research_reports",
]
