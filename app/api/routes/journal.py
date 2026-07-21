"""Reading back the journal — one day's entries, and the strengths review."""
from datetime import date

from fastapi import APIRouter

from app.api.deps import CurrentUid
from app.core import clock
from app.models import Entry
from app.services import entries, facts, strengths

router = APIRouter(tags=["journal"])

# How many days of wins the review screen loads at once.
WINS_LIMIT = 200


def _entry_dict(e: Entry) -> dict:
    """Turn a stored Entry into plain JSON for the review screens."""
    return {
        "id": e.id,
        "created_at": e.created_at.isoformat(),
        "transcript": e.transcript,
        "ai_reply": e.ai_reply,
    }


@router.get("/entries")
def entries_on_day(uid: CurrentUid, day: str | None = None):
    """Recall one day's entries. `day` is YYYY-MM-DD; defaults to today."""
    d = date.fromisoformat(day) if day else clock.today()
    rows = entries.entries_on(d, user_id=uid)
    return {"day": d.isoformat(), "entries": [_entry_dict(r) for r in rows]}


@router.get("/wins")
def wins(uid: CurrentUid):
    """Every win, newest first — the day-by-day review screen.

    Each win is one atomic fact now (category "wins"), but the shape the screen
    consumes is unchanged: an item with `created_at` (to group by day) and
    `wins` (the line to show)."""
    rows = facts.recent_wins(user_id=uid, limit=WINS_LIMIT)
    return {
        "wins": [
            {
                "id": f.id,
                "created_at": f.created_at.isoformat(),
                "wins": f.text,
            }
            for f in rows
        ]
    }


@router.get("/strengths")
def get_strengths(uid: CurrentUid):
    """The passage about who this person is, written from their own record."""
    return {"strengths": strengths.get_strengths(uid)}


@router.post("/strengths/refresh")
def refresh_strengths(uid: CurrentUid):
    """Re-fold the journal's wins into strengths now (normally this happens on
    its own every few entries)."""
    return {"strengths": strengths.refresh_strengths(uid)}
