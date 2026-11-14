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
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libpq5 is the runtime library psycopg needs; its binary wheel is pinned, so
# no libpq-dev and no compiler are needed for that.
#
# build-essential IS needed, at build time, and the comment here used to say
# the opposite. spaCy is pinned at 3.8.3, which publishes no Linux wheel for
# aarch64 - only macOS wheels, x86_64 manylinux wheels and the sdist - so on
# an arm64 host pip builds it from source and compiles
# `spacy.matcher.levenshtein`. Without a compiler the build fails at the pip
# layer below with "Failed building wheel for spacy". The old reasoning was
# true of psycopg and not of spaCy (C-95).
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first, so a code change does not invalidate the install layer.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install -r backend/requirements.txt

# F-09 needs this model and pip does not install it: requirements.txt says so
# in a comment, and the image never ran it, so segmentation raised
# SegmenterUnavailableError on every audit. It is ~12 MB, not part of the
# multi-gigabyte set below. The model is pinned in analysis/text/segmenter.py
# because a different one places sentence boundaries differently, which would
# move every evidence offset.
RUN python -m spacy download en_core_web_sm

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
