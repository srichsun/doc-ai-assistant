"""FastAPI entrypoint for the life-coach journaling app."""
from datetime import date, datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import agent, entries

app = FastAPI(title="Daily Coach")

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
    tools_used: list[str]
    sources: list[str] = []
    session_id: str | None = None


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
def agent_endpoint(req: TalkRequest):
    """Talk to the coach. The exchange is saved as a journal entry.

    Pass a session_id to keep memory across follow-ups.
    """
    return agent.chat_and_log(req.question, session_id=req.session_id)


@app.get("/entries")
def entries_on_day(day: str | None = None):
    """Recall one day's entries. `day` is YYYY-MM-DD; defaults to today (UTC)."""
    d = date.fromisoformat(day) if day else datetime.now(timezone.utc).date()
    rows = entries.entries_on(d)
    return {"day": d.isoformat(), "entries": [_entry_dict(r) for r in rows]}


@app.get("/wins")
def wins():
    """List the most recent entries where the coach recorded a win."""
    return {"wins": [_entry_dict(r) for r in entries.recent_wins()]}
