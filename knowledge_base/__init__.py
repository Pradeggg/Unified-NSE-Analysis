"""Knowledge Base for Agent Adda.

Two complementary layers
─────────────────────────
Layer 1 — Tools/Skills/Commands (BM25, always fast, zero LLM)
    Query via:  python -m knowledge_base query "..."
    API:        from knowledge_base import query_tools, get_context
    Covers:     138 launcher entries, 5 skill YAMLs, 9 project skills,
                9 MCP tools, 13 curated workflow definitions.

Layer 2 — Financial Documents (ChromaDB, requires embeddings)
    Query via:  python -m knowledge_base ask "..."
    API:        from knowledge_base import query_kb, KBVectorStore
    Covers:     SEBI / RBI / CRISIL / broker research PDFs
    Backends:   KB_EMBED_BACKEND = openai | sentence-transformers | ollama | auto

Layer 3 — Live Web Search (DuckDuckGo, on-demand)
    Query via:  python -m knowledge_base query "..." --web
    API:        from knowledge_base import web_search, format_web_block
    Returns:    [{title, url, snippet, domain, score}] — finance domains boosted
    Use when:   you need the latest real-world data alongside the command to run

Token usage analytics
──────────────────────
    python -m knowledge_base tokens          # 7-day summary
    python -m knowledge_base tokens --days 30
    API: from knowledge_base import get_tracker; get_tracker().stats()

Financial document pipeline stages:
    fetch → chunk → qa → index → query
    Layout: data/knowledge_base/  (raw/, chunks.jsonl, qa.jsonl, chroma/)
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
# PG 2026-08-25: Tools/skills/commands BM25 index + token tracking
from .skills_registry import SkillsRegistry, get_registry       # noqa: F401
from .token_tracker import TokenTracker, get_tracker, count_tokens  # noqa: F401
from .kb_tools_query import query_tools, get_context, get_json   # noqa: F401
# PG 2026-08-25: Layer 3 — live web search augmentation (DuckDuckGo)
from .web_search import web_search, format_web_block             # noqa: F401

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
    # tools/skills layer
    "SkillsRegistry", "get_registry",
    "TokenTracker", "get_tracker", "count_tokens",
    "query_tools", "get_context", "get_json",
]
