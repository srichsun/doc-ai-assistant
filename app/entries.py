"""Save and read journal entries — the plain-SQL heart of the app.

Recalling a day or listing this month's wins is just a database query by
date/column; no AI needed. (Semantic "find similar past moments" comes later
with pgvector.)
"""
from datetime import date, datetime, time, timezone

from sqlalchemy import func, select

from app import db
from app.models import Entry


def save_entry(
    transcript: str,
    ai_reply: str,
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
            session_id=session_id,
            mood=mood,
            wins=wins,
            themes=themes,
            note=note,
        )
        s.add(entry)
        s.commit()
        return entry.id


def entries_on(day: date) -> list[Entry]:
    """All entries created on a given calendar day (UTC), oldest first."""
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(day, time.max, tzinfo=timezone.utc)
    with db.get_session() as s:
        stmt = (
            select(Entry)
            .where(Entry.created_at >= start, Entry.created_at <= end)
            .order_by(Entry.created_at)
        )
        return list(s.scalars(stmt))


def recent_entries(limit: int = 30) -> list[Entry]:
    """The most recent entries, newest first — raw material for the profile."""
    with db.get_session() as s:
        stmt = select(Entry).order_by(Entry.created_at.desc()).limit(limit)
        return list(s.scalars(stmt))


def count_entries() -> int:
    """Total number of journal entries."""
    with db.get_session() as s:
        return s.scalar(select(func.count()).select_from(Entry)) or 0


def recent_wins(limit: int = 20) -> list[Entry]:
    """The most recent entries that recorded a win, newest first."""
    with db.get_session() as s:
        stmt = (
            select(Entry)
            .where(Entry.wins.is_not(None), Entry.wins != "")
            .order_by(Entry.created_at.desc())
            .limit(limit)
        )
        return list(s.scalars(stmt))
