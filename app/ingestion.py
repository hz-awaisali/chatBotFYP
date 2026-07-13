from __future__ import annotations

import io
import logging
from typing import List, Tuple

from pypdf import PdfReader

from app.config import Settings

logger = logging.getLogger(__name__)


def read_pdf_bytes(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    parts: List[str] = []
    for i, page in enumerate(reader.pages):
        try:
            t = page.extract_text() or ""
        except Exception as e:
            logger.warning("pdf page %s: %s", i, e)
            t = ""
        parts.append(t)
    return "\n".join(parts).strip()


def read_txt_bytes(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").strip()


def split_chunks(text: str, source: str, settings: Settings) -> List[Tuple[str, str]]:
    """Yields (chunk_text, source) with overlap by character count."""
    text = (text or "").strip()
    if not text:
        return []
    size = max(1, settings.chunk_size)
    overlap = max(0, min(settings.chunk_overlap, size - 1))
    step = size - overlap
    if step <= 0:
        step = 1
    out: List[Tuple[str, str]] = []
    n = len(text)
    i = 0
    while i < n:
        end = min(i + size, n)
        chunk = text[i:end]
        c = chunk.strip()
        if c:
            out.append((c, source))
        if end >= n:
            break
        i += step
    return out
