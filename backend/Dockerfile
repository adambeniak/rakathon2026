# Štafeta backend image. Build context: backend/. Dependencies come from uv.lock (frozen).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    FASTEMBED_CACHE_PATH=/opt/fastembed \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /srv/backend
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

# Local embedding model (~220 MB) baked in at build time: no download on the first question, no network at runtime.
ARG EMBEDDING_MODEL_NAME=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
RUN python -c "import sys; from fastembed import TextEmbedding; TextEmbedding(sys.argv[1], cache_dir='/opt/fastembed')" \
        "$EMBEDDING_MODEL_NAME" \
    && chmod -R a+rX /opt/fastembed
ENV HF_HUB_OFFLINE=1

COPY app ./app
# Recorded LLM responses (fictitious demo data) for STAFETA_LLM_CACHE=1; read-only for the runtime user.
COPY tests/fixtures/llm_cache /srv/llm_cache
ENV LLM_CACHE_DIR=/srv/llm_cache
RUN useradd --system --uid 10001 --no-create-home stafeta
USER stafeta

EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
