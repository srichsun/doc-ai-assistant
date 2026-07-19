"""Reading back the journal — one day's entries, and the strengths review."""
from datetime import date

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core import clock
from app.models import Entry
from app.services import entries, strengths

router = APIRouter(tags=["journal"])


def _entry_dict(e: Entry) -> dict:
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


@router.get("/entries")
def entries_on_day(uid: CurrentUser, day: str | None = None):
    """Recall one day's entries. `day` is YYYY-MM-DD; defaults to today."""
    d = date.fromisoformat(day) if day else clock.today()
    rows = entries.entries_on(d, user_id=uid)
    return {"day": d.isoformat(), "entries": [_entry_dict(r) for r in rows]}


@router.get("/strengths")
def get_strengths(uid: CurrentUser):
    """What this person has proven they can do — the review screen.

    Deliberately not a list of every win ever recorded: a few durable
    capabilities, each carrying the moments that earned it.
    """
    return {"strengths": strengths.get_strengths(uid)}


@router.post("/strengths/refresh")
def refresh_strengths(uid: CurrentUser):
    """Re-fold the journal's wins into strengths now (normally this happens on
    its own every few entries)."""
    return {"strengths": strengths.refresh_strengths(uid)}
