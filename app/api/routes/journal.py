"""The journal — writing today, analysing it, and reading days back.

Only today can be written to. There is no endpoint that takes a date to write
to, so backfilling a day you missed isn't refused, it's unreachable.
"""
from datetime import timedelta

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUid
from app.core import clock
from app.models import Entry
from app.schemas.journal import EntryWrite
from app.services import entries, facts

router = APIRouter(tags=["journal"])

# The two categories the record screen shows back day by day.
SHOWN = ("wins", "gratitude")


def _entry_dict(e: Entry, shown: list | None = None) -> dict:
    """Turn a stored Entry into plain JSON for the review screens."""
    shown = shown or []
    return {
        "id": e.id,
        "date": e.entry_date.isoformat(),
        "content": e.content,
        "energy": e.energy,
        "analyses_left": max(0, entries.ANALYSIS_LIMIT - e.analysis_count),
        "analyzed": e.analyzed_at is not None,
        "wins": [f.text for f in shown if f.category == "wins"],
        "gratitude": [f.text for f in shown if f.category == "gratitude"],
    }


@router.get("/entries")
def entries_in_range(uid: CurrentUid, days: int = 7):
    """The last `days` journal days, oldest first.

    Days with no entry are absent rather than blank — the energy chart draws a
    gap for them, which is the honest picture of a day nobody wrote.
    """
    end = clock.today()
    start = end - timedelta(days=days - 1)
    rows = entries.entries_between(start, end, user_id=uid)
    shown = facts.for_entries([r.id for r in rows], user_id=uid, categories=SHOWN)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "entries": [_entry_dict(r, shown.get(r.id)) for r in rows],
    }


@router.post("/entries")
def write_today(req: EntryWrite, uid: CurrentUid):
    """Write or rewrite today's entry. Unmetered — a day is often written in
    passes, and charging for that would punish keeping up with it."""
    row = entries.save_today(req.content, user_id=uid, energy=req.energy)
    return _entry_dict(row)


@router.post("/entries/{entry_id}/analyze")
def analyze(entry_id: int, uid: CurrentUid):
    """Pull this day's facts out of what was written.

    This is the only thing in the app that grows the memory, and it only runs
    when the person asks for it. Re-analysing replaces the day's facts rather
    than adding a second reading, and spends one of the day's analyses.
    """
    row = entries.entry_on_id(entry_id, user_id=uid)
    if row is None:
        raise HTTPException(status_code=404, detail="no such entry")
    try:
        entries.spend_analysis(row.id)
    except entries.AnalysisLimitReached:
        raise HTTPException(status_code=409, detail="no analyses left today")

    facts.replace_for_entry(row.id, row.content, user_id=uid)
    entries.mark_analyzed(row.id)

    fresh = entries.entry_on(row.entry_date, user_id=uid)
    shown = facts.for_entries([row.id], user_id=uid, categories=SHOWN)
    return _entry_dict(fresh, shown.get(row.id))
