from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    message: str
    include_sources: bool = False

    @field_validator("message")
    @classmethod
    def not_empty_message(cls, v: str) -> str:
        if not (v and v.strip()):
            raise ValueError("message must not be empty or whitespace only")
        return v.strip()


class SourceChunk(BaseModel):
    text: str
    source: str
    score: float


class ChatResponse(BaseModel):
    reply: str
    sources: Optional[List[SourceChunk]] = None


class FileIngestError(BaseModel):
    filename: str
    error: str


class AddDocumentsResponse(BaseModel):
    files_processed: int
    chunks_added: int
    chunks_skipped_duplicates: int
    file_errors: List[FileIngestError] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    embedding_ready: bool
    openrouter_configured: bool
    groq_configured: bool = False
    llm_provider: str = "openrouter"
    index_vectors: int
    embedding_model: str
    data_dir: str
