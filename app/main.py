"""FastAPI entrypoint for the life-coach journaling app."""
import os
from datetime import date, datetime, timezone

from fastapi import Depends, FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import agent, auth, db, entries, profile, voice

app = FastAPI(title="Performance Coach")


@app.on_event("startup")
def _ensure_tables() -> None:
    """Create the journal tables on boot so a fresh deploy (e.g. Cloud Run
    pointed at an empty Cloud SQL) works with no manual migration step.
    Best-effort: a transient DB hiccup shouldn't stop the app from serving
    /health. (pgvector's own tables + extension are created lazily on first use.)
    """
    try:
        db.init_db()
    except Exception:
        pass

# Allow the local React dev server (Vite) to call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class TalkRequest(BaseModel):
    question: str
    session_id: str | None = None  # pass the same id to continue a conversation


class TalkResponse(BaseModel):
    answer: str
    session_id: str | None = None


class SpeakRequest(BaseModel):
    text: str


def _entry_dict(e) -> dict:
    """Turn a stored Entry into plain JSON for the review screens."""
    return {
        "id": e.id,
        "created_at": e.created_at.isoformat(),
        "mood": e.mood,
        "wins": e.wins,
        "themes": e.themes,
        "transcript": e.transcript,
        "ai_reply": e.ai_reply,
    }


@app.get("/health")
def health():
    """Liveness check — no dependencies, no API key needed."""
    return {"status": "ok"}


@app.post("/agent", response_model=TalkResponse)
def agent_endpoint(req: TalkRequest, uid: str = Depends(auth.current_user)):
    """Talk to the coach. The exchange is saved as a journal entry.

    Requires sign-in; pass a session_id to keep memory across follow-ups.
    """
    return agent.chat_and_log(req.question, user_id=uid, session_id=req.session_id)


@app.post("/agent/stream")
def agent_stream(req: TalkRequest, uid: str = Depends(auth.current_user)):
    """Same as /agent, but streams the reply token by token (typewriter effect).
    The exchange is saved once streaming completes."""
    return StreamingResponse(
        agent.stream_and_log(req.question, user_id=uid, session_id=req.session_id),
        media_type="text/plain",
    )


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...), uid: str = Depends(auth.current_user)):
    """Turn recorded audio into text (Whisper only). The browser then streams
    the reply via /agent/stream, so voice replies type out live like typed ones."""
    data = await audio.read()
    return {"text": voice.transcribe(data, audio.filename or "audio.webm")}


@app.post("/speak")
def speak(req: SpeakRequest, uid: str = Depends(auth.current_user)):
    """Turn text into spoken audio (mp3) so the browser can play it.

    Requires sign-in — TTS costs real money per character, so this must not be
    open to the world. If the TTS provider fails (e.g. an out-of-quota plan),
    return 503 with a short reason instead of a raw 500 — the UI skips playback.
    """
    try:
        audio = voice.speak(req.text)
    except Exception as e:
        return Response(content=str(e)[:200], media_type="text/plain", status_code=503)
    return Response(content=audio, media_type="audio/mpeg")


@app.get("/entries")
def entries_on_day(day: str | None = None, uid: str = Depends(auth.current_user)):
    """Recall one day's entries. `day` is YYYY-MM-DD; defaults to today (UTC)."""
    d = date.fromisoformat(day) if day else datetime.now(timezone.utc).date()
    rows = entries.entries_on(d, user_id=uid)
    return {"day": d.isoformat(), "entries": [_entry_dict(r) for r in rows]}


@app.get("/wins")
def wins(uid: str = Depends(auth.current_user)):
    """List the entries where the coach recorded wins, newest first (for the
    review screen)."""
    rows = entries.recent_wins(user_id=uid, limit=200)
    return {"wins": [_entry_dict(r) for r in rows]}


@app.get("/profile")
def get_profile(uid: str = Depends(auth.current_user)):
    """The long-term profile the coach has built up about the person."""
    return {"profile": profile.get_profile(uid)}


@app.post("/profile/refresh")
def refresh_profile(uid: str = Depends(auth.current_user)):
    """Force a re-condense of the profile from recent entries (normally this
    happens on its own every few entries)."""
    return {"profile": profile.refresh_profile(uid)}


# Serve the built React frontend (if present) so the whole app lives at one URL.
# Mounted last, at "/", so the API routes above always take precedence; only
# unmatched paths (the SPA and its assets) fall through to the static files.
# Absent in local dev, where the frontend runs on its own Vite server.
if os.path.isdir("frontend/dist"):
    app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="web")
