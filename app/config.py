from __future__ import annotations

import os
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    base = os.getenv("VERCEL", "")
    if base:
        return Path("/tmp") / "kb"
    return Path(__file__).resolve().parent.parent / "data" / "kb"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default_factory=_default_data_dir)
    faiss_index_name: str = "index.faiss"
    metadata_name: str = "metadata.json"

    openrouter_api_key: str | None = None
    openrouter_base: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-oss-120b:free"
    openrouter_referer: str | None = "https://github.com/vercel/vercel"
    openrouter_title: str | None = "University RAG Chatbot"

    groq_api_key: str | None = None
    groq_base: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"
    llm_provider: str = "openrouter"

    @property
    def is_llm_configured(self) -> bool:
        provider = self.llm_provider.lower().strip()
        if provider == "openrouter" and not self.openrouter_api_key and self.groq_api_key:
            provider = "groq"
        if provider == "groq":
            return bool(self.groq_api_key and self.groq_api_key.strip())
        return bool(self.openrouter_api_key and self.openrouter_api_key.strip())

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    top_k: int = 5
    chunk_size: int = 500
    chunk_overlap: int = 80
    request_timeout: float = 90.0

    admin_token: str | None = None
    max_upload_bytes: int = 20 * 1024 * 1024  # 20 MB

    # Comma-separated origins, e.g. "https://a.com,https://b.com" or * for all
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> List[str]:
        raw = self.cors_origins.strip()
        if not raw or raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    @field_validator("data_dir", mode="before")
    @classmethod
    def _coerce_data_dir(cls, v) -> Path:
        return Path(v) if not isinstance(v, Path) else v
