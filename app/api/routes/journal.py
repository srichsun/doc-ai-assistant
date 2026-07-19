"""Reading back the journal — one day's entries, and the wins review."""
from datetime import date

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core import clock
from app.models import Entry
from app.services import entries

router = APIRouter(tags=["journal"])

# How many win entries the review screen loads at once.
WINS_LIMIT = 200


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


@router.get("/wins")
def wins(uid: CurrentUser):
    """List the entries where the coach recorded wins, newest first (for the
    review screen)."""
    rows = entries.recent_wins(user_id=uid, limit=WINS_LIMIT)
    return {"wins": [_entry_dict(r) for r in rows]}
