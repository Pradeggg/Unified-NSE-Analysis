"""Multi-turn grounded chat about a single symbol.

PG 2026-05-27: Loads KB passages + DB snapshot ONCE per session, then keeps a
rolling chat history. Each turn:
    [system: snapshot + passages] + [running history] + [new user question]
goes to gpt-4o-mini. Cheap and fast — ~$0.001 per turn at typical context size.

Usage from Python:
    sess = SymbolChatSession("TATASTEEL")
    print(sess.ask("Is the broker target realistic vs our momentum?"))
    print(sess.ask("What would invalidate the bull case?"))

Used by nse_agent.py via the `/chat-symbol` slash command.
"""
from __future__ import annotations

import json
import os
from typing import Any

from ._common import load_dotenv
from .critique import fetch_db_snapshot
from .vector_store import KBVectorStore

load_dotenv()

CHAT_MODEL = os.environ.get("KB_CHAT_MODEL", "gpt-4o-mini")
DEFAULT_TOP_K = 8

# PG: cap the static context so multi-turn history has room to grow.
MAX_SNAPSHOT_CHARS = 5000
MAX_PASSAGE_CHARS  = 1500
MAX_PASSAGES_BLOCK = 8000


def _trim(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n] + " …"


class SymbolChatSession:
    """Stateful, KB+DB-grounded chat session for one symbol."""

    def __init__(
        self,
        symbol: str,
        *,
        top_k: int = DEFAULT_TOP_K,
        model: str | None = None,
        brand: str | None = None,
    ) -> None:
        self.symbol = symbol.upper().strip()
        self.top_k = top_k
        self.model = model or CHAT_MODEL
        self.brand = brand
        self.history: list[dict[str, str]] = []  # {role, content}
        self.snapshot: dict[str, Any] = {}
        self.passages: list[dict[str, Any]] = []
        self._client = self._make_openai()
        self._load_context()

    # ─── setup ─────────────────────────────────────────────────────────
    def _make_openai(self):
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return None
        try:
            from openai import OpenAI  # type: ignore
            return OpenAI(api_key=api_key)
        except Exception:
            return None

    def _load_context(self) -> None:
        # PG: pull both DB and KB up front so each turn is purely incremental
        self.snapshot = fetch_db_snapshot(self.symbol)
        try:
            store = KBVectorStore()
            query = f"{self.brand} {self.symbol}" if self.brand else self.symbol
            query += " outlook target rating recommendation thesis risks"
            self.passages = store.query(query, k=self.top_k, collection="chunks")
        except Exception:
            self.passages = []

    # ─── prompt assembly ──────────────────────────────────────────────
    def _system_prompt(self) -> str:
        snap_str = _trim(json.dumps(self.snapshot, indent=2, default=str), MAX_SNAPSHOT_CHARS)

        excerpts: list[str] = []
        budget = MAX_PASSAGES_BLOCK
        for i, p in enumerate(self.passages, start=1):
            txt = _trim((p.get("text") or "").strip(), MAX_PASSAGE_CHARS)
            meta = p.get("metadata") or {}
            tag = meta.get("source_name") or meta.get("path") or "?"
            page = ""
            if meta.get("page_start"):
                page = f" p{meta['page_start']}"
                if meta.get("page_end") and meta["page_end"] != meta["page_start"]:
                    page += f"-{meta['page_end']}"
            block = f"[p{i} | {tag}{page}]\n{txt}\n"
            if len(block) > budget:
                break
            excerpts.append(block)
            budget -= len(block)

        passages_str = "\n".join(excerpts) if excerpts else "[no KB passages]"

        return (
            f"You are a senior equity analyst helping the user understand "
            f"{self.symbol}. Ground every answer in the DB SNAPSHOT (our "
            "internal facts) and BROKER PASSAGES (external research) below. "
            "If a question requires data not present here, say so explicitly "
            "instead of guessing. Quote concrete numbers. Be concise (≤180 words "
            "unless the user asks for depth).\n\n"
            f"==== DB SNAPSHOT for {self.symbol} ====\n"
            f"{snap_str}\n\n"
            f"==== BROKER PASSAGES ====\n"
            f"{passages_str}\n"
        )

    # ─── turn ──────────────────────────────────────────────────────────
    def ask(self, question: str) -> str:
        if not self._client:
            return "[error] OPENAI_API_KEY not set; chat unavailable."

        messages = [{"role": "system", "content": self._system_prompt()}]
        messages.extend(self.history)
        messages.append({"role": "user", "content": question})

        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                max_tokens=700,
            )
            answer = (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            return f"[error] LLM call failed: {exc}"

        self.history.append({"role": "user", "content": question})
        self.history.append({"role": "assistant", "content": answer})
        # PG: trim history to last 12 turns (~6 exchanges) to control cost
        if len(self.history) > 24:
            self.history = self.history[-24:]
        return answer

    # ─── introspection ─────────────────────────────────────────────────
    def context_summary(self) -> dict[str, Any]:
        snap_top = (self.snapshot.get("stage_snapshot") or {})
        rets = self.snapshot.get("returns") or {}
        return {
            "symbol": self.symbol,
            "model": self.model,
            "kb_passages": len(self.passages),
            "kb_top_sources": list({
                (p.get("metadata") or {}).get("source_name") or "?"
                for p in self.passages
            }),
            "cmp": rets.get("cmp"),
            "as_of": rets.get("as_of"),
            "stage": snap_top.get("stage"),
            "stance": snap_top.get("stance"),
            "history_turns": len(self.history) // 2,
        }


__all__ = ["SymbolChatSession"]
