# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_DEFAULT_TIMEOUT=180 PIP_RETRIES=10 HOME=/home/neurosre

COPY requirements.txt .
# cache mount: if a slow download fails, the next build reuses what was already fetched
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt

# run as an unprivileged user, never as root
RUN useradd --create-home --uid 10001 neurosre && mkdir -p /app/data && chown -R neurosre:neurosre /app
COPY --chown=neurosre:neurosre . .
USER neurosre

# Build the vector index (and download the embedding model) at image build time
RUN python -c "from neurosre.knowledge.store import KnowledgeBase; kb = KnowledgeBase(); print(kb.backend, len(kb.chunks))"

EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
