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

# PG 2026-05-27: pluggable embedding backend.
#   KB_EMBED_BACKEND = "openai" (default) | "sentence-transformers" | "auto"
#   - "openai":  hosted, 1536-d, requires US-geography key.
#   - "sentence-transformers": local CPU, 384-d (all-MiniLM-L6-v2 default).
#   - "auto": try openai first, fall back to ST on failure.
# Collections are namespaced by backend so the two embedding spaces never mix
# (Chroma would reject dim-mismatched inserts otherwise).
EMBED_BACKEND = os.environ.get("KB_EMBED_BACKEND", "openai").lower().strip()
EMBED_MODEL   = os.environ.get("KB_EMBED_MODEL", "text-embedding-3-small")
ST_MODEL      = os.environ.get("KB_ST_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
# PG 2026-08-25: Ollama local embedding backend
OLLAMA_MODEL  = os.environ.get("KB_OLLAMA_MODEL", "nomic-embed-text")
OLLAMA_BASE   = os.environ.get("KB_OLLAMA_BASE", "http://localhost:11434").rstrip("/")
EMBED_BATCH   = 64

_COLLECTION_SUFFIX = {
    "openai": "",                      # legacy / existing data stays in kb_chunks / kb_qa
    "sentence-transformers": "_st",    # PG: separate space for 384-d vectors
    "ollama": "_ol",                   # PG 2026-08-25: Ollama local embeddings
}


class KBVectorStore:
    """Thin façade over chromadb persistent client."""

    def __init__(self) -> None:
        import chromadb  # noqa: WPS433
        self._client = chromadb.PersistentClient(path=str(CHROMA_DIR))

        # PG 2026-05-27: resolve backend; "auto" probes OpenAI first.
        self._backend = self._resolve_backend(EMBED_BACKEND)
        suffix = _COLLECTION_SUFFIX.get(self._backend, "")

        self._chunks = self._client.get_or_create_collection(
            name=f"kb_chunks{suffix}", metadata={"hnsw:space": "cosine"}
        )
        self._qa = self._client.get_or_create_collection(
            name=f"kb_qa{suffix}", metadata={"hnsw:space": "cosine"}
        )

        self._openai = self._make_openai() if self._backend == "openai" else None
        self._st_model = self._make_st() if self._backend == "sentence-transformers" else None

    # ─── backend resolution ────────────────────────────────────────────
    def _resolve_backend(self, requested: str) -> str:
        if requested == "sentence-transformers":
            return "sentence-transformers"
        if requested == "ollama":
            return "ollama"
        if requested == "auto":
            # PG: cheap probe — if no OPENAI_API_KEY, try Ollama, then ST.
            if not os.environ.get("OPENAI_API_KEY"):
                if self._probe_ollama():
                    return "ollama"
                return "sentence-transformers"
            return "openai"
        return "openai"

    @staticmethod
    def _probe_ollama() -> bool:
        """Check if Ollama server is reachable."""
        try:
            import urllib.request  # noqa: WPS433
            urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=2)
            return True
        except Exception:
            return False

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

    def _make_st(self):
        # PG 2026-05-27: lazy-load to avoid 2 GB torch import on OpenAI users.
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as exc:  # pragma: no cover - import error path
            raise RuntimeError(
                "sentence-transformers not installed; "
                "run: pip install sentence-transformers"
            ) from exc
        return SentenceTransformer(ST_MODEL)

    def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        if not self._openai:
            raise RuntimeError("OPENAI_API_KEY not set; cannot embed via openai.")
        out: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH):
            batch = texts[i : i + EMBED_BATCH]
            resp = self._openai.embeddings.create(model=EMBED_MODEL, input=batch)
            out.extend(d.embedding for d in resp.data)
        return out

    def _embed_st(self, texts: list[str]) -> list[list[float]]:
        if self._st_model is None:
            self._st_model = self._make_st()
        # PG: SentenceTransformer returns numpy arrays; convert to plain lists
        # so Chroma's JSON serializer accepts them.
        vecs = self._st_model.encode(
            texts, batch_size=32, show_progress_bar=False, normalize_embeddings=True
        )
        return [list(map(float, v)) for v in vecs]

    # PG 2026-08-25: Ollama local embedding backend
    def _embed_ollama(self, texts: list[str]) -> list[list[float]]:
        """Embed via local Ollama server (e.g. nomic-embed-text, mxbai-embed-large)."""
        import json as _json
        import urllib.request as _req  # noqa: WPS433

        out: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH):
            batch = texts[i : i + EMBED_BATCH]
            payload = _json.dumps({"model": OLLAMA_MODEL, "input": batch}).encode()
            req = _req.Request(
                f"{OLLAMA_BASE}/api/embed",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with _req.urlopen(req, timeout=60) as resp:
                body = _json.loads(resp.read())
            out.extend(body["embeddings"])
        return out

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if self._backend == "sentence-transformers":
            return self._embed_st(texts)
        if self._backend == "ollama":
            return self._embed_ollama(texts)
        return self._embed_openai(texts)

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
