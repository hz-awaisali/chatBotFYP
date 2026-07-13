from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, List, Optional, Set, Tuple

import faiss
import numpy as np

from app.config import Settings

logger = logging.getLogger(__name__)


def _chunk_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class VectorStore:
    """FAISS IndexFlatIP with normalized vectors; metadata aligned by row id; dedupe by content hash."""

    def __init__(self, settings: Settings, dimension: int) -> None:
        self._settings = settings
        self._dimension = dimension
        self._lock = threading.Lock()
        self._index = faiss.IndexFlatIP(dimension)
        self._metadata: List[dict[str, Any]] = []
        self._hashes: Set[str] = set()
        self._data_dir = settings.data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def ntotal(self) -> int:
        return int(self._index.ntotal)

    @property
    def path_index(self) -> Path:
        return self._data_dir / self._settings.faiss_index_name

    @property
    def path_metadata(self) -> Path:
        return self._data_dir / self._settings.metadata_name

    @classmethod
    def _from_loaded(
        cls,
        settings: Settings,
        index: Any,
        meta: List[dict],
        expected_dim: int,
    ) -> "VectorStore":
        for row in meta:
            t = row.get("text", "")
            if "hash" not in row and t:
                row["hash"] = _chunk_hash(t)
        hashes: Set[str] = {h for m in meta if (h := m.get("hash"))}
        vs = object.__new__(cls)
        vs._settings = settings
        vs._lock = threading.Lock()
        vs._index = index
        vs._metadata = meta
        vs._hashes = hashes
        vs._data_dir = settings.data_dir
        vs._dimension = expected_dim
        return vs

    @classmethod
    def try_load(
        cls, settings: Settings, expected_dim: int
    ) -> Optional["VectorStore"]:
        data_dir = settings.data_dir
        p_idx = data_dir / settings.faiss_index_name
        p_meta = data_dir / settings.metadata_name
        if not p_idx.is_file() or not p_meta.is_file():
            return None
        try:
            index = faiss.read_index(str(p_idx))
        except Exception as e:
            logger.error("FAISS read failed: %s", e)
            raise
        if int(index.d) != expected_dim:
            raise ValueError(
                f"FAISS index dimension {index.d} does not match model dimension {expected_dim}. "
                "Re-index with the current embedding model or delete the index files in DATA_DIR."
            )
        with open(p_meta, encoding="utf-8") as f:
            raw = json.load(f)
        meta: List[dict] = raw.get("rows", raw) if isinstance(raw, dict) else raw
        if not isinstance(meta, list):
            raise ValueError("metadata.json has invalid format")
        if len(meta) != int(index.ntotal):
            raise ValueError(
                f"metadata rows ({len(meta)}) and FAISS ntotal ({index.ntotal}) mismatch"
            )
        return cls._from_loaded(settings, index, meta, expected_dim)

    @classmethod
    def create_new(cls, settings: Settings, dimension: int) -> "VectorStore":
        return cls(settings, dimension)

    def search(
        self, query_vector: np.ndarray, top_k: int
    ) -> List[Tuple[float, dict[str, Any]]]:
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)
        with self._lock:
            n = int(self._index.ntotal)
            if n == 0:
                return []
            k = min(top_k, n)
            scores, indices = self._index.search(
                query_vector.astype(np.float32, copy=False), k
            )
        out: List[Tuple[float, dict[str, Any]]] = []
        for s, i in zip(scores[0], indices[0]):
            if int(i) < 0 or int(i) >= len(self._metadata):
                continue
            out.append((float(s), self._metadata[int(i)]))
        return out

    def is_duplicate(self, text: str) -> bool:
        h = _chunk_hash(text)
        with self._lock:
            return h in self._hashes

    def add_texts(
        self, items: List[dict[str, str]], embeddings: np.ndarray
    ) -> Tuple[int, int]:
        """items: {text, source} each; returns (added, skipped)"""
        if not items:
            return 0, 0
        if len(items) != embeddings.shape[0]:
            raise ValueError("items and embeddings count mismatch")
        if embeddings.shape[1] != self._dimension:
            raise ValueError("embedding dimension mismatch for vector store")
        added = 0
        skipped = 0
        to_stack: List[np.ndarray] = []
        with self._lock:
            for item, vec in zip(items, embeddings):
                text = item.get("text") or ""
                if not text.strip():
                    continue
                h = _chunk_hash(text)
                if h in self._hashes:
                    skipped += 1
                    continue
                self._hashes.add(h)
                self._metadata.append(
                    {
                        "text": text,
                        "source": item.get("source", "unknown"),
                        "hash": h,
                    }
                )
                to_stack.append(vec.astype(np.float32, copy=True))
                added += 1
            if to_stack:
                m = np.vstack(to_stack)
                self._index.add(m)
        return added, skipped

    def save(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            faiss.write_index(self._index, str(self.path_index))
            payload = {"version": 1, "rows": self._metadata}
            with open(self.path_metadata, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=0)
