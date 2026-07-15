"""Save and read journal entries — the plain-SQL heart of the app.

Every query is scoped to one person (their Firebase uid), so accounts never
see each other's journal. Recalling a day or listing this month's wins is just
a filtered query by date/column; no AI needed. (Semantic "find similar past
moments" lives in recall.py with pgvector.)
"""
from datetime import date, datetime, time, timezone

from sqlalchemy import func, select

from app import db
from app.models import Entry


def save_entry(
    transcript: str,
    ai_reply: str,
    user_id: str | None = None,
    session_id: str | None = None,
    mood: str | None = None,
    wins: str | None = None,
    themes: str | None = None,
    note: str | None = None,
) -> int:
    """Store one conversation turn as a journal entry; return its new id."""
    with db.get_session() as s:
        entry = Entry(
            transcript=transcript,
            ai_reply=ai_reply,
            user_id=user_id,
            session_id=session_id,
            mood=mood,
            wins=wins,
            themes=themes,
            note=note,
        )
        s.add(entry)
        s.commit()
        return entry.id


def entries_on(day: date, user_id: str | None = None) -> list[Entry]:
    """One person's entries created on a given calendar day (UTC), oldest first."""
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(day, time.max, tzinfo=timezone.utc)
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


def recent_entries(user_id: str | None = None, limit: int = 30) -> list[Entry]:
    """One person's most recent entries, newest first — raw material for the profile."""
    with db.get_session() as s:
        stmt = (
            select(Entry)
            .where(Entry.user_id == user_id)
            .order_by(Entry.created_at.desc())
            .limit(limit)
        )
        return list(s.scalars(stmt))


def count_entries(user_id: str | None = None) -> int:
    """How many entries one person has."""
    with db.get_session() as s:
        stmt = select(func.count()).select_from(Entry).where(Entry.user_id == user_id)
        return s.scalar(stmt) or 0


def recent_wins(user_id: str | None = None, limit: int = 20) -> list[Entry]:
    """One person's most recent entries that recorded a win, newest first."""
    with db.get_session() as s:
        stmt = (
            select(Entry)
            .where(
                Entry.user_id == user_id,
                Entry.wins.is_not(None),
                Entry.wins != "",
            )
            .order_by(Entry.created_at.desc())
            .limit(limit)
        )
        return list(s.scalars(stmt))
