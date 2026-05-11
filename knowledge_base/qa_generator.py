"""LLM-driven Q&A generation per chunk.

For each chunk, produce 3-5 Q&A pairs grounded ONLY in the chunk text.
Each pair is stored as a separate vector entry so semantic search can
match either the question phrasing or the answer content.
"""
from __future__ import annotations

import json
import os

from ._common import load_dotenv

load_dotenv()

QA_MODEL = os.environ.get("KB_QA_MODEL", "gpt-4o-mini")
N_QA_PER_CHUNK = int(os.environ.get("KB_QA_PER_CHUNK", "4"))

_SYSTEM_PROMPT = (
    "You are a financial-research analyst building a grounded knowledge base. "
    "Read the provided source excerpt and produce concise, faithful Q&A pairs. "
    "Rules: (1) every answer MUST be supported by the excerpt — do not add outside knowledge; "
    "(2) keep each answer under 80 words; (3) make questions self-contained (include the company, "
    "regulator, or topic name); (4) prefer factual numbers, dates, ratings, policy decisions; "
    "(5) skip boilerplate, footers, navigation. "
    "Return ONLY valid JSON: a list of {\"q\": string, \"a\": string} objects. No prose."
)


def _trim(text: str, max_chars: int = 8000) -> str:
    if len(text) <= max_chars:
        return text
    head = text[: max_chars * 2 // 3]
    tail = text[-max_chars // 3 :]
    return head + "\n[...truncated...]\n" + tail


def generate_qa_for_chunk(chunk: dict, *, n: int = N_QA_PER_CHUNK) -> list[dict]:
    """Return list of {q, a, chunk_id, source_id, ...} entries for one chunk."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return []
    try:
        from openai import OpenAI  # type: ignore
        client = OpenAI(api_key=api_key)
    except Exception:
        return []

    excerpt = _trim(chunk.get("text", ""))
    if len(excerpt) < 200:
        return []

    user = (
        f"SOURCE: {chunk.get('source_name')} ({chunk.get('source_id')})\n"
        f"CATEGORY: {chunk.get('category')}\n"
        f"URL: {chunk.get('source_url')}\n"
        f"FETCHED: {chunk.get('fetched_date')}\n"
        f"GENERATE: {n} grounded Q&A pairs from the excerpt below.\n\n"
        f"EXCERPT:\n{excerpt}"
    )

    try:
        resp = client.chat.completions.create(
            model=QA_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user + "\n\nReturn JSON of shape: {\"qa\":[{\"q\":\"...\",\"a\":\"...\"}]}"},
            ],
            temperature=0.2,
            max_tokens=900,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        items = data.get("qa") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []
    except Exception:
        return []

    out: list[dict] = []
    for i, qa in enumerate(items):
        q = (qa.get("q") or "").strip()
        a = (qa.get("a") or "").strip()
        if not q or not a:
            continue
        out.append({
            "qa_id":        f"{chunk['chunk_id']}::qa{i}",
            "chunk_id":     chunk["chunk_id"],
            "source_id":    chunk.get("source_id"),
            "source_name":  chunk.get("source_name"),
            "category":     chunk.get("category"),
            "tier":         chunk.get("tier"),
            "source_url":   chunk.get("source_url"),
            "fetched_date": chunk.get("fetched_date"),
            "page_start":   chunk.get("page_start"),
            "page_end":     chunk.get("page_end"),
            "q":            q,
            "a":            a,
        })
    return out
