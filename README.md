---
title: University RAG Chatbot
emoji: 🎓
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 7860
---

# University RAG Chatbot (FastAPI)

Backend for an AI university assistant using **RAG** (FAISS + [Sentence-Transformers](https://www.sbert.net) + [OpenRouter](https://openrouter.ai/)). It exposes JSON APIs (e.g. for a Flutter app) and a small **Jinja2 + Tailwind** chat and admin UI for testing.

The YAML block above is for [Hugging Face Spaces](https://huggingface.co/docs/hub/spaces-sdks-docker) (Docker SDK). On GitHub it may appear as a short preamble at the top of this file.

## Stack

- FastAPI, Jinja2, FAISS (`faiss-cpu`), `sentence-transformers`, `pypdf` for PDFs, `httpx` for the LLM

## Local setup

Requires **Python 3.10+**.

```bash
cd fastapi
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
# or: pip install .
```

### Environment

Create a `.env` in the project root (optional if you set variables in the shell):

| Variable | Description |
| -------- | ----------- |
| `OPENROUTER_API_KEY` | **Required** for `POST /chat` — [OpenRouter](https://openrouter.ai/) API key |
| `OPENROUTER_BASE` | Default: `https://openrouter.ai/api/v1` |
| `OPENROUTER_MODEL` | Default: `openai/gpt-4o-mini` (change in dashboard to any OpenRouter model id) |
| `EMBEDDING_MODEL` | Default: `sentence-transformers/all-MiniLM-L6-v2` (384-dim) |
| `DATA_DIR` | Default: `data/kb` (local) or on Vercel, `/tmp/kb` when `VERCEL` is set) |
| `TOP_K` | RAG top-k (default: 5) |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | Chunking for new documents (defaults: 500 / 80) |
| `ADMIN_TOKEN` | If set, `POST /add-documents` requires header `X-Admin-Token: <value>` (or `Authorization: Bearer …`) |
| `CORS_ORIGINS` | Comma-separated list, or `*` for all origins (default: `*`) |
| `MAX_UPLOAD_BYTES` | Per-file cap for uploads (default: 20 MB) |

**First run** will download the embedding model from Hugging Face (can take a while).

## Run the server

```bash
python main.py
# or
uvicorn main:app --host 0.0.0.0 --port 5001 --reload
```

Open: `http://127.0.0.1:5001/` (chat), `http://127.0.0.1:5001/admin` (uploads), `http://127.0.0.1:5001/docs` (OpenAPI).

## Ingest sample data (curl)

With the server running, index the bundled sample texts (paths are relative to your CWD; use full paths on Windows as needed):

```bash
curl -X POST "http://127.0.0.1:5001/add-documents" ^
  -F "files=@data/sample/academic_honesty.txt" ^
  -F "files=@data/sample/registration.txt"
```

If you set `ADMIN_TOKEN`, add `-H "X-Admin-Token: YOUR_TOKEN"`.

Then ask a question in the browser UI or:

```bash
curl -X POST "http://127.0.0.1:5001/chat" ^
  -H "Content-Type: application/json" ^
  -d "{\"message\": \"What is the academic honesty policy?\"}"
```

Response JSON: `{ "reply": "…", "sources": null }`. Add `include_sources: true` in the body to return retrieved chunks in `sources` (or open `/` with `?debug=1` and enable “Show source chunks” in the UI).

## API

| Method | Path | Description |
| ------ | ---- | ----------- |
| `GET` | `/` | Chat UI (Jinja2) |
| `GET` | `/admin` | Optional upload form → `POST /add-documents` |
| `POST` | `/chat` | JSON `{ "message", "include_sources"?: bool }` |
| `POST` | `/add-documents` | Multipart, field name `files` (repeat for multiple) — `.txt`, `.pdf` only; incrementally updates FAISS; duplicate chunks (same hash) skipped |
| `GET` | `/health` | Status, `embedding_ready`, `index_vectors`, paths |

`GET /` includes `?debug=1` to pre-enable source blocks in the UI (same as `include_sources: true` on each message).

## Deploying on Hugging Face Spaces

- Create a **Docker** Space and push this repo (or connect GitHub). The image is built from the root [`Dockerfile`](Dockerfile); the Space listens on **7860** (`app_port` in the README frontmatter matches `EXPOSE` / `uvicorn`).
- In the Space **Settings → Variables and secrets**, add at least **`OPENROUTER_API_KEY`** (and optionally `ADMIN_TOKEN`, `EMBEDDING_MODEL`, `CORS_ORIGINS`, etc.). Same names as in the table above.
- **Hardware**: the default embedding stack (`sentence-transformers` + PyTorch + FAISS) needs enough RAM; start with **CPU Upgrade** if the Space OOMs during model load or encoding.
- **Persistence**: disk on a Space is ephemeral unless you attach [Storage](https://huggingface.co/docs/hub/storage-buckets) or sync elsewhere. The FAISS index under `DATA_DIR` is lost on restart unless you point `DATA_DIR` at mounted storage (e.g. `/data/kb` when a bucket is attached) or re-ingest after restarts.
- **Permissions**: the Dockerfile follows HF’s **UID 1000** non-root user and copies app files with `--chown=user`.

## Deploying on Vercel

- Set **environment variables** in the Vercel project, especially `OPENROUTER_API_KEY` and, if you use it, `ADMIN_TOKEN`.
- [vercel.json](vercel.json) sets `maxDuration` and `memory` for the Python function (adjust to your plan).
- `sentence-transformers` and PyTorch are **large**; cold starts are slow, and the serverless **filesystem is not durable** across all scenarios. The app writes the FAISS index under `DATA_DIR` (e.g. `/tmp/kb` on Vercel) — for production, prefer a long-running host with a **persistent volume**, or add **object storage** (S3 / Vercel Blob) sync for `index.faiss` and `metadata.json` (not implemented in this template).
- CORS: set `CORS_ORIGINS` to your Flutter or web app origin in production.
- Vercel’s [Python function limits](https://vercel.com/docs/functions/runtimes/python) and bundle size still apply; using a **small** embedding model (the default) helps.

## License

As your project requires.
