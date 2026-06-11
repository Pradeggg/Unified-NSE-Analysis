from __future__ import annotations

import builtins

import pytest


def test_fake_embedding_provider_is_deterministic_and_384_dimensional():
    from terminal.skills.embedding_provider import DEFAULT_EMBEDDING_DIMENSION, FakeEmbeddingProvider

    provider = FakeEmbeddingProvider()

    first = provider.embed_texts(["stage 2 stocks", "stage 2 stocks"])
    second = provider.embed_texts(["stage 2 stocks"])

    assert first.model == "fake-sentence-transformer"
    assert first.dimension == DEFAULT_EMBEDDING_DIMENSION == 384
    assert len(first.vectors) == 2
    assert len(first.vectors[0]) == 384
    assert first.vectors[0] == first.vectors[1] == second.vectors[0]


def test_sentence_transformer_provider_uses_configured_model_without_real_download():
    from terminal.skills.embedding_provider import DEFAULT_SENTENCE_TRANSFORMER_MODEL, SentenceTransformerEmbeddingProvider

    class StubModel:
        def __init__(self, model_name: str):
            self.model_name = model_name

        def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
            assert texts == ["quality breakouts"]
            assert normalize_embeddings is True
            assert show_progress_bar is False
            return [[0.25] * 384]

    provider = SentenceTransformerEmbeddingProvider(model_loader=StubModel)

    result = provider.embed_texts(["quality breakouts"])

    assert result.model == DEFAULT_SENTENCE_TRANSFORMER_MODEL
    assert result.dimension == 384
    assert result.vectors == [[0.25] * 384]


def test_sentence_transformer_provider_supports_env_model_override(monkeypatch):
    from terminal.skills.embedding_provider import SentenceTransformerEmbeddingProvider

    class StubModel:
        def __init__(self, model_name: str):
            self.model_name = model_name

        def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
            return [[0.25] * 384]

    monkeypatch.setenv("SKILL_STORE_ST_MODEL", "local/all-MiniLM-L6-v2")

    result = SentenceTransformerEmbeddingProvider(model_loader=StubModel).embed_texts(["quality breakouts"])

    assert result.model == "local/all-MiniLM-L6-v2"


def test_sentence_transformer_provider_fails_gracefully_when_dependency_missing(monkeypatch):
    from terminal.skills.embedding_provider import SentenceTransformerEmbeddingProvider

    real_import = builtins.__import__

    def missing_sentence_transformers(name, *args, **kwargs):
        if name == "sentence_transformers":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_sentence_transformers)

    with pytest.raises(RuntimeError, match="sentence-transformers is not installed"):
        SentenceTransformerEmbeddingProvider().embed_texts(["market breadth"])


def test_embedding_provider_rejects_dimension_mismatch():
    from terminal.skills.embedding_provider import SentenceTransformerEmbeddingProvider

    class BadModel:
        def __init__(self, model_name: str):
            pass

        def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
            return [[0.1, 0.2, 0.3]]

    provider = SentenceTransformerEmbeddingProvider(model_loader=BadModel)

    with pytest.raises(ValueError, match="embedding dimension must be 384"):
        provider.embed_texts(["bad dimension"])


def test_get_embedding_provider_supports_fake_and_sentence_transformer():
    from terminal.skills.embedding_provider import FakeEmbeddingProvider, SentenceTransformerEmbeddingProvider, get_embedding_provider

    assert isinstance(get_embedding_provider("fake"), FakeEmbeddingProvider)
    assert isinstance(get_embedding_provider("sentence-transformer"), SentenceTransformerEmbeddingProvider)
    with pytest.raises(ValueError, match="unsupported embedding provider"):
        get_embedding_provider("openai")
