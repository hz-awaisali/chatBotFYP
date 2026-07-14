from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from app.config import Settings
from app.schemas import SourceChunk
from app.services.embeddings import EmbeddingService
from app.services.llm import OpenRouterClient
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)

SYSTEM_MESSAGE = (
    "You are a helpful, friendly assistant for a university.\n\n"
    "Tone and answers:\n"
    "- Greetings and light pleasantries (hello, hi, good morning, thanks): reply briefly and warmly, "
    "like a front-desk helper; do not dump policy content unless they asked something concrete.\n"
    "- For real questions, ground what you say in the supplied context when it applies. "
    "If something is unknown or not covered, say so simply (you are not sure, or they should confirm with "
    "the relevant office or official university channels). Never expose internals: do not mention a "
    "\"knowledge base\", \"retrieved context\", \"provided documents\", filenames, or phrases like "
    "\"according to the … document\" or \"from the admission regulations file\". State facts naturally, "
    "as if speaking directly to the student.\n\n"
    "Structure:\n"
    "- Do not use filler headings such as \"Answer\", \"Response\", \"Summary\", or \"Conclusion\" as section titles. "
    "Start with useful content. Use ## headings only when they name real topics (e.g. ## Application deadlines), "
    "not wrappers around the whole reply.\n"
    "- Use Markdown for readability when it helps: ## for real sections, bullet or numbered lists for steps, "
    "**bold** for key terms. Use fenced code blocks only for short verbatim quotes or technical snippets.\n"
    "- For mathematics, use LaTeX inside `$$ ... $$` for display (block) formulas and `$ ... $` for short inline math. "
    "Do not wrap formulas in bare square brackets like `[ \\frac{a}{b} ]`.\n"
    "- Be clear and concise."
)


class RAGService:
    def __init__(
        self,
        settings: Settings,
        embeddings: EmbeddingService,
        store: VectorStore,
        llm: OpenRouterClient,
    ) -> None:
        self._s = settings
        self._emb = embeddings
        self._store = store
        self._llm = llm

    def _context_block(
        self, pairs: List[Tuple[float, dict]]
    ) -> str:
        lines: List[str] = []
        for j, (score, meta) in enumerate(pairs, 1):
            t = (meta or {}).get("text", "")
            src = (meta or {}).get("source", "unknown")
            lines.append(
                f"[{j}] (source: {src}, relevance: {score:.3f})\n{t}"
            )
        return "\n\n---\n\n".join(lines)

    async def answer(
        self, user_message: str, include_sources: bool
    ) -> Tuple[str, Optional[List[SourceChunk]]]:
        if not self._s.is_llm_configured:
            raise RuntimeError("LLM is not configured (set OPENROUTER_API_KEY or GROQ_API_KEY)")

        qv = self._emb.encode_query(user_message)
        hits = self._store.search(qv, self._s.top_k)

        if not hits:
            ctx = "No document chunks in the index yet, or the index is empty. Advise the user to upload materials via add-documents."
        else:
            ctx = self._context_block(hits)
        user_prompt = f"Context from the knowledge base:\n\n{ctx}\n\nUser question: {user_message}"
        messages = [
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": user_prompt},
        ]
        text, _request_id = await self._llm.chat(messages)
        src_models: Optional[List[SourceChunk]] = None
        if include_sources:
            src_models = [
                SourceChunk(
                    text=(m or {}).get("text", "")[:2000],
                    source=str((m or {}).get("source", "")),
                    score=float(s),
                )
                for s, m in hits
            ]
        return text, src_models
