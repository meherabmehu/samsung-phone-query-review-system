"""Embedding providers for the RAG retrieval layer.

Two implementations are provided:

- ``SentenceTransformerEmbedder`` — real semantic embeddings via
  sentence-transformers (default, uses a small open-source model).
- ``HashEmbedder`` — a dependency-free hashing fallback (bag-of-words over a
  fixed-size hash space) so retrieval still works even if torch /
  sentence-transformers are not installed.

:func:`get_embedder` picks the best available provider and caches it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from app.config import settings
from app.logging_setup import get_logger

logger = get_logger(__name__)


class BaseEmbedder(ABC):
    """Interface every embedder implements."""

    @abstractmethod
    def encode(self, texts: list[str]) -> np.ndarray:
        """Return an (n, dim) matrix of unit-normalized embeddings."""


class SentenceTransformerEmbedder(BaseEmbedder):
    """Semantic embeddings using a sentence-transformers model."""

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.embedding_model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model %s", self.model_name)
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim))
        model = self._load()
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vectors, dtype=np.float32)

    @property
    def dim(self) -> int:
        return int(self._load().get_sentence_embedding_dimension())


class HashEmbedder(BaseEmbedder):
    """Lightweight, dependency-free bag-of-words fallback (l2-normalized)."""

    DIM = 2048

    def __init__(self) -> None:
        from sklearn.feature_extraction.text import HashingVectorizer

        self._vectorizer = HashingVectorizer(
            n_features=self.DIM, norm="l2", alternate_sign=False, lowercase=True
        )

    @property
    def dim(self) -> int:
        return self.DIM

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.DIM), dtype=np.float32)
        return self._vectorizer.transform(texts).toarray().astype(np.float32)


_embedder: BaseEmbedder | None = None


def get_embedder() -> BaseEmbedder:
    """Return a cached embedder, preferring sentence-transformers."""
    global _embedder
    if _embedder is not None:
        return _embedder
    try:
        embedder = SentenceTransformerEmbedder()
        embedder._load()  # fail fast if the model can't be loaded
        _embedder = embedder
    except Exception as exc:  # noqa: BLE001 - any load failure -> fallback
        logger.warning("SentenceTransformer unavailable (%s); using hash fallback", exc)
        _embedder = HashEmbedder()
    return _embedder
