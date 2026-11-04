# Single image serving both the API and the built single-page application, and
# also used for the worker with a different command.
#
# This is what keeps the deployment at the three containers the approved Phase 3
# design specifies: web/API, worker, PostgreSQL. A separate nginx container for
# the frontend would make four and would be a deviation from that design, so the
# SPA is built here and served by FastAPI as static files instead.

# ---- Stage 1: build the SPA -------------------------------------------------
FROM node:20-alpine AS frontend_build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: application ---------------------------------------------------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libpq is needed by psycopg. No compiler is installed, because the binary
# wheel is pinned in requirements.txt.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first, so a code change does not invalidate the install layer.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install -r backend/requirements.txt

# The ML dependency set is deliberately NOT installed here. It is over 2 GB and
# is only needed once the improved models exist (Milestone 6). To enable it,
# uncomment the two lines below and rebuild.
# COPY backend/requirements-ml.txt ./backend/requirements-ml.txt
# RUN pip install -r backend/requirements-ml.txt

COPY backend/ ./backend/
COPY analysis/ ./analysis/
COPY acquisition/ ./acquisition/
COPY ml/ ./ml/

# Built SPA. FastAPI serves it; see backend/app/main.py.
COPY --from=frontend_build /build/dist ./static

ENV PYTHONPATH=/app:/app/backend \
    STATIC_DIR=/app/static

RUN useradd --create-home --shell /usr/sbin/nologin auditor \
    && mkdir -p /app/data/policies/raw /app/ml/checkpoints \
    && chown -R auditor:auditor /app
USER auditor

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
