# Multi-stage image for Cloud Run: build the React frontend, then serve it and
# the FastAPI backend from one container (one URL for the whole app).

# --- Stage 1: build the frontend (uses frontend/.env.production) ---
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build   # -> /web/dist

# --- Stage 2: the Python app, serving the built frontend too ---
FROM python:3.12-slim

# uv for fast, locked dependency installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Install deps first (cached unless the lockfile changes).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Application code + the built frontend.
COPY app ./app
COPY scripts ./scripts
COPY --from=web /web/dist ./frontend/dist

# Run uvicorn straight from the venv (no `uv run` re-sync) for fast cold
# starts. Cloud Run sends requests to $PORT (default 8080); shell form expands it.
ENV PORT=8080
CMD .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
