"""Load and summarise the latest parsed filing for a symbol.

The downloader writes filings to ``data/filings/<SYMBOL>/LATEST/`` with a
``manifest.json`` and a ``parsed/filing_parse.json`` produced by
``terminal/document_parsers.py``. This module gives the Strategy Council a
compact, evidence-pack-friendly view of that data so critics and strategists
no longer treat fundamentals as "missing" when a filing is on disk.

The summary is intentionally lossy: only metadata, the first few page texts
(capped), and tables whose row labels mention key P&L / balance-sheet
keywords are surfaced. Downstream consumers (LLM strategist, /analyze) can
treat it as a structured pointer into the parsed JSON without loading the
whole document.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


FILING_KEYWORDS = (
    "revenue",
    "income",
    "ebitda",
    "pat",
    "net profit",
    "net loss",
    "profit after tax",
    "eps",
    "earnings per share",
    "net debt",
    "gross debt",
    "borrowings",
    "cash flow",
    "operating activities",
    "total assets",
    "equity",
    "margin",
)

NUMBER_PATTERN = re.compile(
    r"(?P<num>\(?-?\d{1,3}(?:[,\d]{0,12})(?:\.\d+)?\)?)"
)


def _filing_root(symbol: str, project_root: Path | None = None) -> Path:
    root = Path(project_root) if project_root is not None else Path.cwd()
    symbol_dir = root / "data" / "filings" / symbol.strip().upper()
    latest = symbol_dir / "LATEST"
    if (latest / "parsed" / "filing_parse.json").is_file():
        return latest
    if symbol_dir.is_dir():
        candidates = [
            p for p in symbol_dir.iterdir()
            if p.is_dir() and (p / "parsed" / "filing_parse.json").is_file()
        ]
        if candidates:
            return max(candidates, key=lambda p: p.stat().st_mtime)
    return latest


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _row_label(row: list[Any]) -> str:
    if not row:
        return ""
    return " ".join(str(cell or "").strip() for cell in row if str(cell or "").strip()).lower()


def _row_matches_keyword(row: list[Any]) -> bool:
    label = _row_label(row)
    return any(kw in label for kw in FILING_KEYWORDS)


def _flatten_row(row: list[Any]) -> str:
    return " | ".join(str(cell or "").strip() for cell in row)


def _extract_headline_numbers(tables: list[dict[str, Any]]) -> dict[str, str]:
    """Return a coarse map of {metric: first matched row text}.

    Heuristic only: scans table rows for keyword anchors and stores the first
    one seen. The raw text is preserved so the LLM can disambiguate units
    (Cr / M / %) itself instead of us mis-parsing.
    """
    wanted = {
        "revenue": ("revenue", "income"),
        "ebitda": ("ebitda",),
        "pat": ("net profit", "profit after tax", "pat"),
        "eps": ("eps", "earnings per share"),
        "net_debt": ("net debt",),
        "operating_cash_flow": ("operating activities", "cash flow"),
    }
    found: dict[str, str] = {}
    for table in tables:
        for row in table.get("rows") or []:
            label = _row_label(row)
            if not label:
                continue
            flat = _flatten_row(row)
            for key, needles in wanted.items():
                if key in found:
                    continue
                if any(needle in label for needle in needles):
                    found[key] = flat[:400]
    return found


def summarise_filing(
    symbol: str,
    *,
    project_root: Path | None = None,
    max_page_chars: int = 4000,
    max_pages: int = 5,
    max_tables: int = 6,
) -> dict[str, Any] | None:
    """Return a compact summary of the latest parsed filing for ``symbol``.

    Returns ``None`` when no filing or no parsed JSON is available so the
    caller can mark this evidence axis as missing without raising.
    """
    sym = symbol.strip().upper()
    base = _filing_root(sym, project_root)
    manifest = _load_json(base / "manifest.json") or {}
    parsed = _load_json(base / "parsed" / "filing_parse.json")
    if not parsed:
        return None

    pages = parsed.get("pages") or []
    tables = parsed.get("tables") or []

    page_excerpts: list[dict[str, Any]] = []
    char_budget = max_page_chars
    for page in pages[:max_pages]:
        if not isinstance(page, dict):
            continue
        text = (page.get("text") or "").strip()
        if not text:
            continue
        snippet = text[: max(0, char_budget)]
        if not snippet:
            break
        char_budget -= len(snippet)
        page_excerpts.append(
            {
                "page": page.get("page_number"),
                "char_count": page.get("char_count"),
                "text": snippet,
            }
        )

    keyword_tables: list[dict[str, Any]] = []
    for table in tables:
        rows = table.get("rows") or []
        relevant = [row for row in rows if _row_matches_keyword(row)]
        if not relevant:
            continue
        keyword_tables.append(
            {
                "page": table.get("page_number"),
                "table_index": table.get("table_index"),
                "rows": [_flatten_row(row) for row in rows[: 20]],
                "matched_rows": [_flatten_row(row) for row in relevant[: 20]],
            }
        )
        if len(keyword_tables) >= max_tables:
            break

    summary: dict[str, Any] = {
        "symbol": sym,
        "available": True,
        "source_url": manifest.get("source_url"),
        "local_path": manifest.get("local_path"),
        "document_type": parsed.get("document_type") or manifest.get("document_type"),
        "period": parsed.get("period") or manifest.get("period"),
        "fetched_at": manifest.get("fetched_at"),
        "parsed_at": parsed.get("parsed_at"),
        "page_count": parsed.get("page_count"),
        "scanned_page_count": parsed.get("scanned_page_count"),
        "table_count": len(tables),
        "page_excerpts": page_excerpts,
        "key_tables": keyword_tables,
        "headline_numbers": _extract_headline_numbers(tables),
        "warnings": parsed.get("warnings") or [],
    }
    return summary


__all__ = ["summarise_filing", "FILING_KEYWORDS"]
