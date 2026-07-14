from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

from fastapi import (
    Body,
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import ingestion
from app.config import Settings
from app.schemas import AddDocumentsResponse, ChatResponse, FileIngestError, HealthResponse
from app.services.embeddings import EmbeddingService
from app.services.llm import OpenRouterClient
from app.services.rag import RAGService
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def _get_settings(request: Request) -> Settings:
    return request.app.state.settings


def _get_rag(request: Request) -> RAGService:
    r = request.app.state.rag
    if r is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG service is not available",
        )
    return r


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_level = logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    s = Settings()
    app.state.settings = s
    app.state.rag = None
    s.data_dir.mkdir(parents=True, exist_ok=True)

    emb = EmbeddingService(s)
    try:
        emb.load()
    except Exception as e:
        logger.exception("Failed to load embedding model: %s", e)
        app.state.rag = None
        app.state.store = None
        app.state.embeddings = None
        app.state.llm = None
        yield
        return

    app.state.embeddings = emb
    try:
        store = VectorStore.try_load(s, emb.dimension) or VectorStore.create_new(
            s, emb.dimension
        )
    except ValueError as e:
        logger.error("%s", e)
        app.state.rag = None
        app.state.store = None
        yield
        return

    app.state.store = store
    app.state.llm = OpenRouterClient(s)
    app.state.rag = RAGService(s, emb, store, app.state.llm)
    logger.info("RAG service ready, index has %s vectors", store.ntotal)
    yield


app = FastAPI(
    title="University RAG Chatbot",
    description="RAG backend with FAISS + Sentence-Transformers + OpenRouter",
    version="1.0.0",
    lifespan=lifespan,
)

_cors = Settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors.cors_origin_list,
    # Do not set allow_credentials with wildcard origins (browser CORS spec)
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _check_admin(request: Request, s: Settings) -> None:
    t = s.admin_token
    if not t or not t.strip():
        return
    header = request.headers.get("X-Admin-Token") or request.headers.get(
        "Authorization", ""
    )
    if header.startswith("Bearer "):
        header = header[7:].strip()
    if header != t.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing admin token"
        )


@app.get("/health", response_model=HealthResponse)
def health_check(request: Request) -> HealthResponse:
    s: Settings = request.app.state.settings
    emb: EmbeddingService | None = getattr(request.app.state, "embeddings", None)
    st: VectorStore | None = getattr(request.app.state, "store", None)
    
    provider = s.llm_provider.lower().strip()
    if provider == "openrouter" and not s.openrouter_api_key and s.groq_api_key:
        provider = "groq"
        
    return HealthResponse(
        status="ok",
        embedding_ready=bool(emb and emb.is_ready()),
        openrouter_configured=bool(s.openrouter_api_key and s.openrouter_api_key.strip()),
        groq_configured=bool(s.groq_api_key and s.groq_api_key.strip()),
        llm_provider=provider,
        index_vectors=int(st.ntotal) if st else 0,
        embedding_model=s.embedding_model,
        data_dir=str(s.data_dir),
    )


def _parse_chat_request(body: dict) -> tuple[str, bool]:
    m = (body or {}).get("message")
    if m is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="message is required"
        )
    if not isinstance(m, str) or not m.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="message must not be empty or whitespace only",
        )
    inc = bool((body or {}).get("include_sources", False))
    return m.strip(), inc


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: Request,
    body: dict = Body(...),
) -> ChatResponse:
    s: Settings = _get_settings(request)
    msg, include_sources = _parse_chat_request(body)
    if not s.is_llm_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat is unavailable: LLM is not configured (set OPENROUTER_API_KEY or GROQ_API_KEY)",
        )
    rag = _get_rag(request)
    if getattr(request.app.state, "store", None) and request.app.state.store.ntotal == 0:
        logger.info("RAG: empty index, answering with empty KB hint")
    try:
        text, src = await rag.answer(msg, include_sources=include_sources)
    except RuntimeError as e:
        msg_err = str(e) or "RAG / LLM error"
        if "key" in msg_err.lower() and "config" in msg_err.lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=msg_err
            ) from e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=msg_err
        ) from e
    return ChatResponse(reply=text, sources=src if include_sources else None)


@app.post("/add-documents", response_model=AddDocumentsResponse)
async def add_documents(
    request: Request,
    files: List[UploadFile] = File(),
) -> AddDocumentsResponse:
    s: Settings = _get_settings(request)
    _check_admin(request, s)
    emb: EmbeddingService | None = request.app.state.embeddings
    st: VectorStore | None = request.app.state.store
    if not emb or not emb.is_ready() or st is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding or vector store is not ready",
        )
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file is required",
        )

    all_chunks: list[dict] = []
    fe: list[FileIngestError] = []
    allowed = (".txt", ".pdf")
    n_files = 0
    pre_skip = 0
    for uf in files:
        name = (uf.filename or "unnamed") or "unnamed"
        lower = name.lower()
        if not any(lower.endswith(ext) for ext in allowed):
            fe.append(
                FileIngestError(
                    filename=name,
                    error="Only .txt and .pdf are allowed",
                )
            )
            continue
        data = await uf.read()
        if s.max_upload_bytes and len(data) > s.max_upload_bytes:
            fe.append(
                FileIngestError(
                    filename=name,
                    error=f"File too large (max {s.max_upload_bytes} bytes)",
                )
            )
            continue
        n_files += 1
        try:
            if lower.endswith(".txt"):
                raw_t = ingestion.read_txt_bytes(data)
            else:
                raw_t = ingestion.read_pdf_bytes(data)
        except Exception as e:
            fe.append(
                FileIngestError(
                    filename=name, error=f"Read failed: {e}"[:200]
                )
            )
            continue
        for chunk, src in ingestion.split_chunks(
            raw_t, source=name, settings=s
        ):
            if st.is_duplicate(chunk):
                pre_skip += 1
            else:
                all_chunks.append({"text": chunk, "source": src})
    if not all_chunks:
        return AddDocumentsResponse(
            files_processed=n_files,
            chunks_added=0,
            chunks_skipped_duplicates=pre_skip,
            file_errors=fe,
        )

    texts = [c["text"] for c in all_chunks]
    vecs = emb.encode(texts)
    if vecs.size == 0:
        return AddDocumentsResponse(
            files_processed=n_files,
            chunks_added=0,
            chunks_skipped_duplicates=pre_skip,
            file_errors=fe,
        )
    added, batch_skip = st.add_texts(all_chunks, vecs)
    try:
        st.save()
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to save index: {e!s}"[:200]
        ) from e
    return AddDocumentsResponse(
        files_processed=n_files,
        chunks_added=added,
        chunks_skipped_duplicates=pre_skip + batch_skip,
        file_errors=fe,
    )


@app.get("/", response_class=HTMLResponse)
async def chat_page(request: Request) -> HTMLResponse:
    # Starlette: TemplateResponse(request, name, context) — not (name, context).
    debug = request.query_params.get("debug", "").lower() in (
        "1",
        "true",
        "yes",
    )
    return templates.TemplateResponse(
        request,
        "chat.html",
        {
            "include_sources_default": debug,
        },
    )


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin.html",
        {"title": "Upload documents"},
    )
