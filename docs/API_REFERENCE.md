# University RAG Chatbot — HTTP API reference

This document describes the REST API exposed by the **University RAG Chatbot** backend (FastAPI). It is intended for **Flutter** (mobile/web) and other HTTP clients.

For interactive exploration, the running server also serves:

- **Swagger UI:** `GET /docs`
- **OpenAPI JSON:** `GET /openapi.json`

Replace `{BASE_URL}` below with your deployment root (no trailing slash), for example:

- Local: `http://127.0.0.1:5001`
- Hugging Face Space: use the **Space URL** shown on the Space page (typically `https://<space-subdomain>.hf.space`)

All JSON APIs use **UTF-8**. Timestamps and IDs are not versioned in responses beyond what is documented here.

---

## Conventions

### Authentication

| Endpoint | Auth |
| -------- | ---- |
| `GET /health` | None |
| `POST /chat` | None (backend must have LLM API key configured server-side) |
| `POST /add-documents` | Optional **admin token** (see below) |

There is **no end-user JWT or API key** for `/chat`. The OpenRouter key lives on the server only.

### Admin token (`POST /add-documents`)

If the server sets `ADMIN_TOKEN` in its environment:

- Send **`X-Admin-Token: <token>`**, **or**
- Send **`Authorization: Bearer <token>`**

If `ADMIN_TOKEN` is **not** set on the server, uploads are **not** protected by this check (still only use in trusted environments).

### Error responses

FastAPI returns JSON shaped like:

```json
{ "detail": "Human-readable message" }
```

or, for some validation errors, `detail` may be a **list** of objects. Clients should treat non-2xx responses as errors and read `detail` when present.

### CORS

- **Flutter mobile (iOS/Android):** CORS does not apply to the Dart `HttpClient` / typical plugin traffic.
- **Flutter web:** The browser enforces CORS. Production servers should set `CORS_ORIGINS` to your web app origin(s), or `*` for development (already common default).

---

## Endpoints overview

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/health` | Liveness / configuration snapshot |
| `POST` | `/chat` | Send a user message; get RAG reply (JSON) |
| `POST` | `/add-documents` | Upload `.txt` / `.pdf` files to grow the knowledge base |
| `GET` | `/` | Browser chat UI (HTML) |
| `GET` | `/admin` | Browser upload UI (HTML) |
| `GET` | `/docs` | OpenAPI Swagger UI (HTML) |
| `GET` | `/openapi.json` | OpenAPI schema (JSON) |

Flutter apps normally call **`/health`**, **`/chat`**, and optionally **`/add-documents`** only.

---

## `GET /health`

Lightweight status check for dashboards and startup probes.

### Request

- **Headers:** none required.
- **Body:** none.

### Response `200 OK`

JSON object:

| Field | Type | Description |
| ----- | ---- | ----------- |
| `status` | `string` | Always `"ok"` when the handler runs. |
| `embedding_ready` | `bool` | `true` if the embedding model loaded successfully. |
| `openrouter_configured` | `bool` | `true` if `OPENROUTER_API_KEY` is set on the server (required for chat). |
| `index_vectors` | `int` | Number of vectors in the FAISS index (chunks stored). |
| `embedding_model` | `string` | Hugging Face id of the embedding model (server config). |
| `data_dir` | `string` | Filesystem path used for index/metadata (informational). |

### Example

```http
GET {BASE_URL}/health HTTP/1.1
```

```json
{
  "status": "ok",
  "embedding_ready": true,
  "openrouter_configured": true,
  "index_vectors": 42,
  "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
  "data_dir": "/home/user/app/data/kb"
}
```

---

## `POST /chat`

Runs retrieval over the knowledge base and generates an answer via the configured LLM (OpenRouter).

### Request

- **Headers:** `Content-Type: application/json`
- **Body (JSON object):**

| Field | Type | Required | Description |
| ----- | ---- | -------- | ----------- |
| `message` | `string` | **Yes** | User question; must be non-empty after trimming whitespace. |
| `include_sources` | `bool` | No | Default `false`. If `true`, response includes retrieved chunks and scores. |

Extra JSON keys are ignored.

### Response `200 OK`

| Field | Type | Description |
| ----- | ---- | ----------- |
| `reply` | `string` | Assistant answer text. The model is instructed to use **Markdown** (headings, lists, emphasis); Flutter/web clients should render it with a Markdown widget/package for structured display. |
| `sources` | `array \| null` | Present only when `include_sources` is `true`. Each item is a **source chunk** (see below). If `include_sources` is `false`, this field is **`null`** (not an empty array). |

**Source chunk** object (when `sources` is non-null):

| Field | Type | Description |
| ----- | ---- | ----------- |
| `text` | `string` | Retrieved chunk text (may be truncated server-side, up to ~2000 chars per chunk). |
| `source` | `string` | Label / filename associated with the chunk. |
| `score` | `number` | Similarity-related score from vector search (float). |

### Status codes

| Code | When |
| ---- | ---- |
| `200` | Success. |
| `400` | Missing `message`, or empty / whitespace-only message. |
| `503` | RAG not available (e.g. embeddings failed), LLM not configured (`OPENROUTER_API_KEY` missing), or some LLM configuration errors. |
| `500` | Unexpected server/LLM failure (`detail` explains). |

### Example (minimal)

```http
POST {BASE_URL}/chat HTTP/1.1
Content-Type: application/json

{"message": "What is the academic honesty policy?"}
```

```json
{
  "reply": "According to the knowledge base …",
  "sources": null
}
```

### Example (with sources)

```json
{
  "message": "How do I register for courses?",
  "include_sources": true
}
```

```json
{
  "reply": "…",
  "sources": [
    {
      "text": "… chunk text …",
      "source": "registration.txt",
      "score": 0.812
    }
  ]
}
```

### Behaviour notes

- If the index is **empty**, the model still responds; the server injects context explaining there are no documents yet (operators should ingest via `/add-documents` or seed data).
- Long-running LLM calls may take tens of seconds; use a **client timeout** of at least **90 seconds** unless your deployment tightens `REQUEST_TIMEOUT` server-side.

---

## `POST /add-documents`

Multipart upload of knowledge-base files. Server extracts text, chunks it, embeds new chunks, updates FAISS, and persists index/metadata under the server `DATA_DIR`.

### Request

- **Content-Type:** `multipart/form-data`
- **Parts:** one or more file parts named **`files`** (same field name repeated per file — this matches HTML form conventions and OpenAPI).

Supported extensions **only**:

- `.txt` — plain text (encoding as interpreted by server)
- `.pdf` — PDF text extraction via `pypdf`

Other extensions are **skipped** and reported in `file_errors` (upload may still succeed partially).

- **Max size per file:** **20 MiB** by default (`20971520` bytes), unless the server overrides `MAX_UPLOAD_BYTES`.

### Headers (when admin token is enabled)

Either:

- `X-Admin-Token: <your-admin-token>`

or:

- `Authorization: Bearer <your-admin-token>`

### Response `200 OK`

| Field | Type | Description |
| ----- | ---- | ----------- |
| `files_processed` | `int` | Count of uploaded parts that were eligible (correct extension, within size, attempted read). |
| `chunks_added` | `int` | New chunks written to the index in this request. |
| `chunks_skipped_duplicates` | `int` | Chunks skipped because they duplicate existing content (hash-based). |
| `file_errors` | `array` | Per-file problems; may be empty. |

**File error** object:

| Field | Type | Description |
| ----- | ---- | ----------- |
| `filename` | `string` | Original filename or `unnamed`. |
| `error` | `string` | Reason (wrong type, too large, read failure, etc.). |

### Status codes

| Code | When |
| ---- | ---- |
| `200` | Request handled (check `file_errors` and counts for partial failures). |
| `400` | No files provided. |
| `401` | Admin token required but missing or wrong. |
| `503` | Embeddings or vector store not ready. |
| `500` | Failed to persist index (`detail` explains). |

### Example (curl)

```bash
curl -X POST "{BASE_URL}/add-documents" \
  -H "X-Admin-Token: YOUR_TOKEN" \
  -F "files=@./doc1.txt" \
  -F "files=@./handbook.pdf"
```

---

## HTML routes (optional for Flutter)

These return **HTML**, not JSON. Flutter apps typically **do not** call them unless you embed a WebView.

| Route | Query | Purpose |
| ----- | ----- | ------- |
| `GET /` | `debug=1` (optional) | Chat UI; `debug` pre-enables “show sources” style behaviour in the web UI only. |
| `GET /admin` | — | Simple upload form hitting `/add-documents`. |

---

## Server-side environment (operator reference)

Flutter developers **do not** send these as client headers; they configure the **deployment**. Listed for completeness when debugging `503` from `/health` or `/chat`.

| Variable | Role |
| -------- | ---- |
| `OPENROUTER_API_KEY` | Required for `/chat`. |
| `OPENROUTER_BASE` | Default `https://openrouter.ai/api/v1`. |
| `OPENROUTER_MODEL` | Default `openai/gpt-4o-mini`. |
| `EMBEDDING_MODEL` | Default `sentence-transformers/all-MiniLM-L6-v2`. |
| `DATA_DIR` | Directory for `index.faiss` + `metadata.json`. |
| `ADMIN_TOKEN` | Enables admin auth for `/add-documents`. |
| `MAX_UPLOAD_BYTES` | Per-file upload cap (default 20 MiB). |
| `CORS_ORIGINS` | Comma-separated origins or `*`. |
| `TOP_K` | Chunks retrieved per query (default `5`). |

---

## Flutter implementation hints

### Dependencies

Common packages: [`http`](https://pub.dev/packages/http), [`dio`](https://pub.dev/packages/dio), or [`chopper`](https://pub.dev/packages/chopper). Below uses conceptual steps; adapt to your stack.

### Base URL configuration

Store `{BASE_URL}` per flavor (dev/staging/prod), for example via `--dart-define` or `flutter_dotenv`.

### `POST /chat` (JSON)

- Set header `Content-Type: application/json`.
- Encode body: `{"message": question, "include_sources": showSources}`.
- Parse JSON; read `reply` and optional `sources`.
- Use a **timeout** ≥ 90s for slow LLM responses unless you know your server is faster.

### `POST /add-documents` (multipart)

- Field name must be **`files`** for each part.
- Many Dart helpers use `MultipartFile` / `MultipartRequest`; repeat the same field name for multiple files (aligned with `curl -F "files=@a" -F "files=@b"`).
- Add `X-Admin-Token` if your backend uses `ADMIN_TOKEN`.

### Parsing errors

Read `response.body` as UTF-8 JSON and inspect `detail` on failures. Display a generic message to users; log `detail` for developers.

### OpenAPI → Dart models

You can generate models from `GET {BASE_URL}/openapi.json` using tools such as [openapi_generator](https://pub.dev/packages/openapi_generator) or quicktype; verify generated names against this document.

---

## Quick reference card

```
GET  {BASE_URL}/health          → JSON status
POST {BASE_URL}/chat            → JSON { message, include_sources? }
POST {BASE_URL}/add-documents   → multipart/form-data, field "files" (+ admin headers if configured)
GET  {BASE_URL}/docs            → Swagger UI
GET  {BASE_URL}/openapi.json    → OpenAPI spec
```

---

## Changelog / versioning

The API version field in OpenAPI is **`1.0.0`** (see `/openapi.json`). Breaking changes should bump version and be communicated to mobile teams.
