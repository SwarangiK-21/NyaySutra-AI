# NyaySutra AI — container image (runs on any Docker host: a VM, Oracle/AWS/DigitalOcean, Google Cloud Run…).
# Build on the machine that has the law library (data/library, incl. the India Code acts imported at run time):
#     docker build -t nyaysutra .
# Secrets are NOT in the image: pass them at run time (docker compose env_file: .env, or the host's secret settings).
# See docs/DEPLOYMENT.md.
# Pinned by digest (python:3.14-slim as of 2026-11-05) so every build uses the scanned base; refresh it monthly.
FROM python:3.14-slim@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    NYAYA_HOME=/var/lib/nyaysutra \
    MODEL_CACHE=/opt/nyaysutra/models \
    HF_HUB_DISABLE_PROGRESS_BARS=1

# libgomp1: OpenMP runtime used by ONNX Runtime (embeddings, re-ranker, OCR). fonts-noto-core: Latin + Devanagari
# for PDF export (Hindi/Marathi drafts). No curl: the health check uses Python.
# `upgrade` applies Debian security fixes released after the pinned base (e.g. zlib, November 2026).
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends libgomp1 fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/nyaysutra/app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY nyaya ./nyaya
COPY web ./web
COPY data/library ./data/library
COPY data/awareness ./data/awareness
COPY data/drafting ./data/drafting
COPY supabase ./supabase
COPY scripts ./scripts
COPY run.py .

# Download the search models once, at build time, so a new container starts without fetching ~190 MB.
RUN python -c "from nyaya import embeddings; embeddings.warm_up()"

RUN useradd --system --create-home --home-dir /var/lib/nyaysutra nyaya \
    && mkdir -p /var/lib/nyaysutra /opt/nyaysutra/app/data/uploads \
    && chown -R nyaya /var/lib/nyaysutra /opt/nyaysutra/app/data /opt/nyaysutra/models
USER nyaya

EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=10s --start-period=180s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=8)"]
CMD ["python", "run.py", "--no-browser"]
