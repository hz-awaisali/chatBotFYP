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


class OpenRouterClient:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    async def chat(
        self,
        messages: List[dict[str, str]],
    ) -> tuple[str, Optional[str]]:
        key = self._s.openrouter_api_key
        if not key or not key.strip():
            raise RuntimeError("OpenRouter API key is not configured")
        url = f"{self._s.openrouter_base.rstrip('/')}/chat/completions"
        body: dict[str, Any] = {
            "model": self._s.openrouter_model,
            "messages": messages,
        }
        try:
            async with httpx.AsyncClient(timeout=self._s.request_timeout) as client:
                r = await client.post(
                    url,
                    headers=_build_headers(self._s),
                    json=body,
                )
        except httpx.RequestError as e:
            logger.exception("OpenRouter request failed: %s", e)
            raise RuntimeError("Could not reach OpenRouter") from e
        if r.status_code >= 400:
            err_text = r.text[:2000] if r.text else ""
            req_id = r.headers.get("x-request-id", "")
            logger.error(
                "OpenRouter %s: %s request_id=%s", r.status_code, err_text, req_id
            )
            safe = f"Model error (HTTP {r.status_code})"
            if "error" in err_text and len(err_text) < 500:
                # surface short JSON error messages only
                safe = err_text[:500]
            raise RuntimeError(safe) from None
        data = r.json()
        choice = (data.get("choices") or [{}])[0] or {}
        message = (choice.get("message") or {}).get("content")
        if not message or not str(message).strip():
            raise RuntimeError("OpenRouter returned an empty reply")
        return str(message).strip(), r.headers.get("x-request-id")
