from __future__ import annotations

import logging
from typing import Any, List, Optional

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


def _build_headers(settings: Settings) -> dict[str, str]:
    h: dict[str, str] = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.openrouter_api_key or ''}",
    }
    if settings.openrouter_referer:
        h["HTTP-Referer"] = settings.openrouter_referer
    if settings.openrouter_title:
        h["X-Title"] = settings.openrouter_title
    return h


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    async def chat(
        self,
        messages: List[dict[str, str]],
    ) -> tuple[str, Optional[str]]:
        provider = self._s.llm_provider.lower().strip()
        
        # Auto-detect fallback: if provider is openrouter but openrouter key is not set,
        # and groq key is set, automatically use groq.
        if provider == "openrouter" and not self._s.openrouter_api_key and self._s.groq_api_key:
            provider = "groq"

        if provider == "groq":
            key = self._s.groq_api_key
            if not key or not key.strip():
                raise RuntimeError("Groq API key is not configured (set GROQ_API_KEY)")
            url = f"{self._s.groq_base.rstrip('/')}/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            }
            model = self._s.groq_model
        else:
            key = self._s.openrouter_api_key
            if not key or not key.strip():
                raise RuntimeError("OpenRouter API key is not configured (set OPENROUTER_API_KEY)")
            url = f"{self._s.openrouter_base.rstrip('/')}/chat/completions"
            headers = _build_headers(self._s)
            model = self._s.openrouter_model

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }

        try:
            async with httpx.AsyncClient(timeout=self._s.request_timeout) as client:
                r = await client.post(
                    url,
                    headers=headers,
                    json=body,
                )
        except httpx.RequestError as e:
            logger.exception("%s request failed: %s", provider.capitalize(), e)
            raise RuntimeError(f"Could not reach {provider.capitalize()}") from e

        if r.status_code >= 400:
            err_text = r.text[:2000] if r.text else ""
            req_id = r.headers.get("x-request-id", "")
            logger.error(
                "%s %s: %s request_id=%s", provider.capitalize(), r.status_code, err_text, req_id
            )
            safe = f"Model error (HTTP {r.status_code})"
            if "error" in err_text and len(err_text) < 500:
                safe = err_text[:500]
            raise RuntimeError(safe) from None

        data = r.json()
        choice = (data.get("choices") or [{}])[0] or {}
        message = (choice.get("message") or {}).get("content")
        if not message or not str(message).strip():
            raise RuntimeError(f"{provider.capitalize()} returned an empty reply")
        return str(message).strip(), r.headers.get("x-request-id")


OpenRouterClient = LLMClient




