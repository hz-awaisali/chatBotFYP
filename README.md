---
title: University RAG Chatbot
emoji: 🎓
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 7860
---

# University RAG Chatbot (FastAPI)

Backend for an AI university assistant using **RAG** (FAISS + [Sentence-Transformers](https://www.sbert.net) + [OpenRouter](https://openrouter.ai/) / [Groq API](https://groq.com/)). It exposes JSON APIs (e.g. for a Flutter app) and provides a sleek **Jinja2 + Tailwind** chat and document management interface.

---

## Features

*   **Dual LLM Provider Support**: Dynamically switch between **OpenRouter** and **Groq** APIs depending on your API keys and provider preference.
*   **Knowledge Base Document Manager**: Upload, view, and delete `.txt` or `.pdf` documents directly from the admin panel.
*   **Auto-rebuild Vector Search**: Deleting outdated documents unlinks them from storage and automatically rebuilds the FAISS vector index using the remaining documents, preventing hallucinated and outdated answers.
*   **Docker Container Optimization**: Optimized Docker builds pre-install CPU-only PyTorch and pre-cache embedding models, speeding up VPS deployment builds and enabling instant container boot times.
*   **Persistent Storage**: Mounts a Docker volume to persist all source files and the vectorized FAISS database permanently.

---

## Stack

*   **Backend**: FastAPI, Jinja2, Uvicorn, HTTPX
*   **Vector DB & Ingestion**: FAISS (`faiss-cpu`), `sentence-transformers` (`all-MiniLM-L6-v2`), `pypdf`, `numpy`
*   **LLMs**: OpenRouter & Groq API

---

## Local Setup

Requires **Python 3.10+**.

1.  **Clone and Navigate**:
    ```bash
    git clone <your-repo-url>
    cd chatBotFYP
    ```

2.  **Create and Activate Virtual Environment**:
    ```bash
    python -m venv .venv
    # Windows:
    .venv\Scripts\activate
    # macOS/Linux:
    source .venv/bin/activate
    ```

3.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

---

## Environment Variables

Create a `.env` in the project root:

| Variable | Description | Default |
| -------- | ----------- | ------- |
| `LLM_PROVIDER` | Active LLM client. Options: `openrouter`, `groq` | `openrouter` (auto-detects `groq` if OpenRouter key is missing and Groq key is present) |
| `OPENROUTER_API_KEY` | OpenRouter API Key | `None` |
| `OPENROUTER_MODEL` | OpenRouter chat model | `openai/gpt-oss-120b:free` |
| `GROQ_API_KEY` | Groq API Key | `None` |
| `GROQ_MODEL` | Groq chat model | `llama-3.3-70b-versatile` |
| `EMBEDDING_MODEL` | Embedding model for text chunks | `sentence-transformers/all-MiniLM-L6-v2` |
| `ADMIN_TOKEN` | Required in headers (`X-Admin-Token`) for upload/delete endpoints if set | `None` |
| `CORS_ORIGINS` | Comma-separated CORS origins or `*` | `*` |
| `TOP_K` | Number of RAG chunks to retrieve | `5` |
| `CHUNK_SIZE` | Chunk size (by char count) for splitting texts | `500` |
| `CHUNK_OVERLAP` | Overlap size between adjacent chunks | `80` |
| `MAX_UPLOAD_BYTES` | Maximum file size for uploads | `20971520` (20 MB) |

---

## Run the Server

```bash
python main.py
# or
uvicorn main:app --host 0.0.0.0 --port 5001 --reload
```

Open your browser to:
*   **Chat Interface**: `http://127.0.0.1:5001/`
*   **Knowledge Base Manager**: `http://127.0.0.1:5001/admin`
*   **OpenAPI Documentation**: `http://127.0.0.1:5001/docs`
*   **Health Status**: `http://127.0.0.1:5001/health`

---

## API Documentation

| Method | Path | Auth Header (Optional) | Description |
| ------ | ---- | ---------------------- | ----------- |
| `GET` | `/` | None | Chat UI (Jinja2 Template) |
| `GET` | `/admin` | None | Document Uploader and File Manager UI |
| `POST` | `/chat` | None | Send user query. JSON body: `{"message": "...", "include_sources"?: bool}` |
| `POST` | `/add-documents` | `X-Admin-Token` | Upload and index `.txt` or `.pdf` files. Saves files to disk and adds chunks to FAISS index. |
| `GET` | `/admin/files` | `X-Admin-Token` | List all active source files in the knowledge base. |
| `DELETE` | `/admin/files/{filename}` | `X-Admin-Token` | Delete a file from disk and automatically rebuild the FAISS search index. |
| `GET` | `/health` | None | Status endpoint returning system checks and LLM configuration info. |

---

## Deployment Guides

### 1. VPS Deployment using Coolify (Docker Compose)

Coolify makes deploying to a Contabo VPS simple. We provide a `docker-compose.yaml` in the repository that builds the Dockerfile, exposes the app, mounts persistent volumes, and handles health checks.

#### Steps:
1.  **Repository Setup**: Connect your GitHub/GitLab account to your Coolify dashboard.
2.  **Create Service**: Go to **Resources** -> **New Resource** -> **Service** (or **Docker Compose**) and select your repository and branch.
3.  **Deploy Configuration**: Coolify automatically reads the root `docker-compose.yaml`.
4.  **Configure Environment**: Add the following keys in Coolify's Environment tab:
    *   `GROQ_API_KEY`: Your Groq API key (to use Groq's fast tier).
    *   `LLM_PROVIDER`: `groq` (or `openrouter`).
    *   `ADMIN_TOKEN`: A secure token to protect upload and delete APIs.
5.  **Data Persistence**: Coolify will automatically provision a Docker named volume `chatbot_data` and mount it to `/home/user/app/data`. This keeps your uploaded source documents and the FAISS vector index safe during container updates.
6.  **Set Domain**: In the settings, configure your subdomain (e.g., `https://chatbot.yourdomain.com`). Coolify will handle Let's Encrypt SSL and proxy requests to internal port `7860`.
7.  **Deploy**: Click **Deploy**.

---

### 2. Deploying on Hugging Face Spaces

*   Create a **Docker** Space on Hugging Face.
*   Connect your repository. Hugging Face reads the root `Dockerfile` and listens on port `7860`.
*   Go to **Settings** -> **Variables and secrets** and add `OPENROUTER_API_KEY` (or `GROQ_API_KEY`), `ADMIN_TOKEN`, etc.
*   *Note*: Ephemeral disk space on Hugging Face spaces resets on container sleep/restart unless you attach persistent storage.

---

### 3. Deploying on Vercel

*   Set your environment variables in Vercel.
*   Configure the Python serverless function parameters in `vercel.json`.
*   *Note*: Due to large dependencies (PyTorch, sentence-transformers), serverless functions can face cold-start lag. We recommend VPS/Docker hosting for best RAG performance.

---

## License

This project is licensed under the MIT License.
