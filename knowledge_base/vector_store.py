"""ChromaDB wrapper — persistent local vector store with OpenAI embeddings.

Two collections:
    - "chunks" : full text chunks (large, used for context window)
    - "qa"     : LLM-generated Q&A pairs (small, used for fast lookup)
"""
from __future__ import annotations

import os
from typing import Iterable

from ._common import CHROMA_DIR, load_dotenv

load_dotenv()

EMBED_MODEL = os.environ.get("KB_EMBED_MODEL", "text-embedding-3-small")
EMBED_BATCH = 64


class KBVectorStore:
    """Thin façade over chromadb persistent client."""

    def __init__(self) -> None:
        import chromadb  # noqa: WPS433
        self._client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self._chunks = self._client.get_or_create_collection(
            name="kb_chunks", metadata={"hnsw:space": "cosine"}
        )
        self._qa = self._client.get_or_create_collection(
            name="kb_qa", metadata={"hnsw:space": "cosine"}
        )
        self._openai = self._make_openai()

    # ─── embedding ─────────────────────────────────────────────────────
    def _make_openai(self):
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return None
        try:
            from openai import OpenAI  # type: ignore
            return OpenAI(api_key=api_key)
        except Exception:
            return None

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not self._openai:
            raise RuntimeError("OPENAI_API_KEY not set; cannot embed.")
        out: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH):
            batch = texts[i : i + EMBED_BATCH]
            resp = self._openai.embeddings.create(model=EMBED_MODEL, input=batch)
            out.extend(d.embedding for d in resp.data)
        return out

    # ─── upsert ────────────────────────────────────────────────────────
    @staticmethod
    def _clean_meta(d: dict) -> dict:
        # Chroma rejects None values in metadata; coerce to "" or 0.
        clean = {}
        for k, v in d.items():
            if v is None:
                clean[k] = ""
            elif isinstance(v, (str, int, float, bool)):
                clean[k] = v
            else:
                clean[k] = str(v)
        return clean

    def upsert_chunks(self, chunks: Iterable[dict]) -> int:
        chunks = list(chunks)
        if not chunks:
            return 0
        ids   = [c["chunk_id"] for c in chunks]
        docs  = [c["text"] for c in chunks]
        metas = [self._clean_meta({k: v for k, v in c.items() if k != "text"}) for c in chunks]
        embs  = self._embed(docs)
        self._chunks.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=embs)
        return len(chunks)

    def upsert_qa(self, pairs: Iterable[dict]) -> int:
        pairs = list(pairs)
        if not pairs:
            return 0
        ids = [p["qa_id"] for p in pairs]
        # Embed the Q+A text together — both phrasings retrievable.
        docs  = [f"Q: {p['q']}\nA: {p['a']}" for p in pairs]
        metas = [self._clean_meta(p) for p in pairs]
        embs  = self._embed(docs)
        self._qa.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=embs)
        return len(pairs)

    # ─── query ─────────────────────────────────────────────────────────
    def query(self, text: str, *, k: int = 6, collection: str = "qa") -> list[dict]:
        """Semantic search. `collection` is 'qa' or 'chunks'."""
        if not text.strip():
            return []
        col = self._qa if collection == "qa" else self._chunks
        emb = self._embed([text])[0]
        res = col.query(query_embeddings=[emb], n_results=k,
                        include=["documents", "metadatas", "distances"])
        out: list[dict] = []
        for doc, meta, dist in zip(
            res.get("documents", [[]])[0],
            res.get("metadatas", [[]])[0],
            res.get("distances", [[]])[0],
        ):
            out.append({"text": doc, "metadata": meta, "score": 1.0 - float(dist)})
        return out

    def stats(self) -> dict:
        return {"chunks": self._chunks.count(), "qa": self._qa.count()}
