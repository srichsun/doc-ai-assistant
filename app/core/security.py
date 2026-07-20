"""Authentication via Firebase (Google sign-in).

The browser signs the person in with Google and gets a Firebase ID token; it
sends that token as `Authorization: Bearer <token>` on every request. Here we
verify it with the Firebase Admin SDK and hand back the user's uid, which is
what we scope journal entries and profiles by.

We never touch passwords or the login flow ourselves — Firebase owns all of
that. The Admin SDK is initialized lazily from the service-account file so
tests (which pass a uid directly) don't need it.
"""
from functools import lru_cache

import firebase_admin
from fastapi import Header, HTTPException
from firebase_admin import auth as fb_auth
from firebase_admin import credentials

from app.core import config

@lru_cache(maxsize=1)
def _app() -> firebase_admin.App:
    """Initialize the Firebase Admin app once, from the service-account file."""
    cred = credentials.Certificate(config.FIREBASE_CREDENTIALS)
    return firebase_admin.initialize_app(cred)


def verify_token(id_token: str) -> str:
    """Verify a Firebase ID token and return the user's uid (raises on bad token)."""
    decoded = fb_auth.verify_id_token(id_token, app=_app())
    return decoded["uid"]


def current_user(authorization: str | None = Header(None)) -> str:
    """FastAPI dependency: require a valid Bearer token, return the uid."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        uid = verify_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return uid
