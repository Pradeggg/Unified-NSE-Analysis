"""Compose context from an email + linked filings and call the LLM."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from .classifier import Classification
from .config import AppConfig
from .content_fetcher import FetchedContent, fetch_url
from .email_client import EmailMessage
from .llm_client import LLMClient, LLMError

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an experienced Indian equities analyst. You receive corporate-action "
    "and earnings emails (NSE/BSE filings, broker notes, IR mailers). Produce concise, "
    "decision-useful output. Be precise with numbers, mention units, and clearly separate "
    "FACTS (from the source) from OPINION (your view). Never fabricate figures. If a number "
    "isn't in the source, say 'not disclosed'. Output Markdown."
)

ANALYSIS_TEMPLATE = """Analyse the following stock-related email and any attached filing text.

## Email
- Subject: {subject}
- From: {sender}
- Date: {date}
- Detected categories: {categories}
- Detected tickers: {tickers}

### Email body (truncated)
{body}

## Linked documents
{docs_section}

---

Produce the following sections in Markdown:
1. **TL;DR** — 2-3 bullets
2. **Key facts** — table/bullets of headline numbers (revenue, PAT, EPS, YoY/QoQ, dividend amount, record date, ratio, etc.) with units
3. **What changed vs. expectations / prior period** (only if inferable)
4. **Why it matters** — sector / macro context
5. **Opinion** — your independent view (bull/bear points, key risks). Mark clearly as OPINION.
6. **Suggested follow-ups** — what the user should check next
"""

MAX_BODY_CHARS = 8000
MAX_DOC_CHARS = 12000


@dataclass
class AnalysisResult:
    email: EmailMessage
    classification: Classification
    docs: List[FetchedContent] = field(default_factory=list)
    summary_markdown: str = ""
    error: Optional[str] = None


def _truncate(text: str, limit: int) -> str:
    if not text:
        return "(empty)"
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n…[truncated {len(text) - limit} chars]"


def _build_docs_section(docs: List[FetchedContent]) -> str:
    if not docs:
        return "(no linked documents fetched)"
    sections = []
    per_doc = max(2000, MAX_DOC_CHARS // max(1, len(docs)))
    for i, doc in enumerate(docs, 1):
        sections.append(
            f"### Document {i}: {doc.url}\nContent-Type: {doc.content_type}\n\n"
            + _truncate(doc.text, per_doc)
        )
    return "\n\n".join(sections)


def analyze_email(
    msg: EmailMessage,
    classification: Classification,
    cfg: AppConfig,
    llm: LLMClient,
    fetch_links: bool = True,
    max_links: int = 3,
) -> AnalysisResult:
    docs: List[FetchedContent] = []
    if fetch_links and classification.is_critical and msg.links:
        for url in msg.links[:max_links]:
            doc = fetch_url(url, cfg.cache_dir, cfg.max_link_bytes, cfg.request_timeout)
            if doc and doc.text:
                docs.append(doc)

    prompt = ANALYSIS_TEMPLATE.format(
        subject=msg.subject or "(no subject)",
        sender=msg.sender or "(unknown)",
        date=msg.short_date,
        categories=", ".join(classification.categories) or "(none)",
        tickers=", ".join(classification.tickers) or "(none)",
        body=_truncate(msg.body_text, MAX_BODY_CHARS),
        docs_section=_build_docs_section(docs),
    )

    try:
        summary = llm.complete(SYSTEM_PROMPT, prompt)
    except LLMError as exc:
        return AnalysisResult(email=msg, classification=classification, docs=docs, error=str(exc))

    return AnalysisResult(
        email=msg,
        classification=classification,
        docs=docs,
        summary_markdown=summary,
    )


def chat_followup(
    base: AnalysisResult,
    user_message: str,
    history: List[dict],
    llm: LLMClient,
) -> str:
    """Follow-up Q&A about an analysed email. Maintains conversation history."""
    context = (
        f"You previously produced this analysis for the email '{base.email.subject}':\n\n"
        f"{base.summary_markdown}\n\n"
        "Answer the user's follow-up question grounded in this context plus the original "
        "email and documents. If the user asks for something not in scope, say so."
    )
    try:
        return llm.complete(SYSTEM_PROMPT + "\n\n" + context, user_message, history=history)
    except LLMError as exc:
        return f"[LLM error: {exc}]"
