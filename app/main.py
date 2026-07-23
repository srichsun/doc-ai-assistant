"""FastAPI entrypoint — assembly only.

This file wires the app together and nothing else: middleware, the API routes
(see app/api/), and the built frontend. All the actual work lives in
app/services/; the endpoints themselves live in app/api/routes/.
"""
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core import config, db

log = logging.getLogger(__name__)

app = FastAPI(title="Dear Myself")


@app.on_event("startup")
def _check_settings() -> None:
    """Refuse to boot on a misconfigured deploy, rather than serving a 500 to
    the first person who talks to the coach.

    Cloud Run's health check fails, the release is rolled back automatically,
    and the reason is the first line in the logs. Checked here rather than at
    import time so tests can import the modules without any real keys.
    """
    missing = config.missing_required_settings()
    if missing:
        raise RuntimeError("Cannot start — bad configuration: " + "; ".join(missing))


@app.on_event("startup")
def _ensure_tables() -> None:
    """Run any pending migrations on boot, so a fresh deploy (e.g. Cloud Run
    pointed at an empty Cloud SQL) works with no manual step.

    Best-effort on purpose: a transient DB hiccup shouldn't stop the app from
    serving /health, which is what you need to diagnose it. The failure is
    logged rather than swallowed — a schema left behind is worth knowing about.
    (pgvector's own tables are created by LangChain on first use.)
    """
    try:
        db.run_migrations()
    except Exception:
        log.exception("Database migration failed — schema may be out of date")


# Allow the local React dev server (Vite) to call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# Serve the built React frontend (if present) so the whole app lives at one URL.
# Mounted last, at "/", so the API routes above always take precedence; only
# unmatched paths (the SPA and its assets) fall through to the static files.
# Absent in local dev, where the frontend runs on its own Vite server.
if os.path.isdir("frontend/dist"):
    app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="web")
