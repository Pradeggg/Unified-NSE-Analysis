from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass
from typing import Any, Callable, Protocol


DEFAULT_SENTENCE_TRANSFORMER_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_DIMENSION = 384


class EmbeddingProvider(Protocol):
    def embed_texts(self, texts: list[str], model: str | None = None) -> "EmbeddingResult":
        ...


@dataclass(frozen=True)
class EmbeddingResult:
    model: str
    dimension: int
    vectors: list[list[float]]


class FakeEmbeddingProvider:
    model = "fake-sentence-transformer"

    def embed_texts(self, texts: list[str], model: str | None = None) -> EmbeddingResult:
        vectors = [_fake_vector(text, DEFAULT_EMBEDDING_DIMENSION) for text in texts]
        return EmbeddingResult(
            model=model or self.model,
            dimension=DEFAULT_EMBEDDING_DIMENSION,
            vectors=vectors,
        )


class SentenceTransformerEmbeddingProvider:
    def __init__(self, model_name: str | None = None, model_loader: Callable[[str], Any] | None = None):
        self.model_name = model_name or os.environ.get("SKILL_STORE_ST_MODEL") or DEFAULT_SENTENCE_TRANSFORMER_MODEL
        self._model_loader = model_loader
        self._model: Any | None = None

    def embed_texts(self, texts: list[str], model: str | None = None) -> EmbeddingResult:
        model_name = model or self.model_name
        loaded = self._load_model(model_name)
        encoded = loaded.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        vectors = [_coerce_vector(row) for row in encoded]
        _validate_vectors(vectors)
        return EmbeddingResult(model=model_name, dimension=DEFAULT_EMBEDDING_DIMENSION, vectors=vectors)

    def _load_model(self, model_name: str) -> Any:
        if self._model is not None and model_name == self.model_name:
            return self._model
        loader = self._model_loader or _sentence_transformer_loader
        model = loader(model_name)
        if model_name == self.model_name:
            self._model = model
        return model


def get_embedding_provider(name: str | None = None) -> EmbeddingProvider:
    provider_name = (name or "sentence-transformer").strip().lower().replace("_", "-")
    if provider_name in {"sentence-transformer", "sentence-transformers", "local", "bge"}:
        return SentenceTransformerEmbeddingProvider()
    if provider_name in {"fake", "test"}:
        return FakeEmbeddingProvider()
    raise ValueError(f"unsupported embedding provider: {name}")


def _sentence_transformer_loader(model_name: str) -> Any:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is not installed. Install requirements.txt or choose the fake provider for tests."
        ) from exc
    return SentenceTransformer(model_name)


def _coerce_vector(vector: Any) -> list[float]:
    if hasattr(vector, "tolist"):
        vector = vector.tolist()
    return [float(item) for item in vector]


def _validate_vectors(vectors: list[list[float]]) -> None:
    for vector in vectors:
        if len(vector) != DEFAULT_EMBEDDING_DIMENSION:
            raise ValueError(f"embedding dimension must be {DEFAULT_EMBEDDING_DIMENSION}")


def _fake_vector(text: str, dimension: int) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = []
    for index in range(dimension):
        byte = digest[index % len(digest)]
        values.append((byte / 127.5) - 1.0)
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [round(value / norm, 12) for value in values]
