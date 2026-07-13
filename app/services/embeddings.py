from __future__ import annotations

import logging
from typing import List

import numpy as np

from app.config import Settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Loads Sentence-Transformers once; encodes with L2-normalized vectors for cosine via IP."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = None
        self._dim: int | None = None

    def load(self) -> None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model: %s", self._settings.embedding_model)
        self._model = SentenceTransformer(self._settings.embedding_model)
        # Infer dimension from a tiny encode
        v = self._model.encode(
            "dimension probe",
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        self._dim = int(np.array(v).shape[-1])
        logger.info("Embedding dimension: %s", self._dim)

    @property
    def dimension(self) -> int:
        if self._dim is None:
            raise RuntimeError("Embedding model not loaded")
        return self._dim

    def is_ready(self) -> bool:
        return self._model is not None and self._dim is not None

    def encode(self, texts: List[str]) -> np.ndarray:
        if not self._model:
            raise RuntimeError("Embedding model not loaded")
        if not texts:
            return np.zeros((0, self._dim or 0), dtype=np.float32)
        return np.array(
            self._model.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=False,
            ),
            dtype=np.float32,
        )

    def encode_query(self, text: str) -> np.ndarray:
        return self.encode([text])
