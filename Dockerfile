# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_DEFAULT_TIMEOUT=180 PIP_RETRIES=10 PIP_CACHE_DIR=/root/.cache/pip

COPY requirements.txt .
# cache mount: if a slow download fails, the next build reuses what was already fetched
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt

# run as an unprivileged user, never as root
RUN useradd --create-home --uid 10001 neurosre && mkdir -p /app/data && chown -R neurosre:neurosre /app
COPY --chown=neurosre:neurosre . .
USER neurosre
ENV HOME=/home/neurosre

# Build the vector index and download the embedding model at image build time.
# Fail the build if semantic search is not available, instead of silently falling back to keywords.
RUN python -c "from neurosre.knowledge.store import KnowledgeBase; kb = KnowledgeBase(); print(kb.backend, len(kb.chunks)); assert kb.backend == 'chromadb', 'ChromaDB unavailable'"

EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/faults')"
CMD ["uvicorn", "neurosre.api:app", "--host", "0.0.0.0", "--port", "8000"]
