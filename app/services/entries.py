"""Save and read journal entries — the plain-SQL heart of the app.

Every query is scoped to one person (their Firebase uid), so accounts never
see each other's journal. Recalling a day is just a filtered query by date; no
AI needed. (Atomic facts and the wins list live in facts.py; semantic "find
similar past moments" lives in recall.py with pgvector.)
"""
from datetime import date

from sqlalchemy import func, select

from app.core import clock, db
from app.models import Entry


def save_entry(
    transcript: str,
    ai_reply: str,
    user_id: str,
    note: str | None = None,
) -> int:
    """Store one conversation turn as a journal entry; return its new id.

    The things pulled out of an exchange (wins and the like) are no longer
    stored on the entry — they live as atomic facts (see app.services.facts).
    """
    with db.get_session() as s:
        entry = Entry(
            transcript=transcript,
            ai_reply=ai_reply,
            user_id=user_id,
            note=note,
        )
        s.add(entry)
        s.commit()
        return entry.id


def entries_on(day: date, user_id: str) -> list[Entry]:
    """One person's entries from a given journal day, oldest first."""
    start, end = clock.day_bounds(day)
    with db.get_session() as s:
        stmt = (
            select(Entry)
            .where(
                Entry.user_id == user_id,
                Entry.created_at >= start,
                Entry.created_at <= end,
            )
            .order_by(Entry.created_at)
        )
        return list(s.scalars(stmt))


def recent_entries(user_id: str, limit: int = 30) -> list[Entry]:
    """One person's most recent entries, newest first — raw material for the profile."""
    with db.get_session() as s:
        stmt = (
            select(Entry)
            .where(Entry.user_id == user_id)
            .order_by(Entry.created_at.desc())
            .limit(limit)
        )
        return list(s.scalars(stmt))


def count_entries(user_id: str) -> int:
    """How many entries one person has."""
    with db.get_session() as s:
        stmt = select(func.count()).select_from(Entry).where(Entry.user_id == user_id)
        return s.scalar(stmt) or 0
