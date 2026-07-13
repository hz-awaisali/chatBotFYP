FROM python:3.12-slim-bookworm

# faiss-cpu wheels often link against OpenMP
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 user

USER user
ENV HOME=/home/user \
    PYTHONUNBUFFERED=1

WORKDIR $HOME/app

# Venv avoids PEP 668 "externally managed" errors when installing as non-root
RUN python -m venv .venv
ENV PATH=/home/user/app/.venv/bin:$PATH

COPY --chown=user requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt \
    && python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY --chown=user app ./app
COPY --chown=user templates ./templates
COPY --chown=user data ./data

EXPOSE 7860

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
