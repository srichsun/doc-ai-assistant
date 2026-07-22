"""Save and read journal entries — the plain-SQL heart of the app.

One entry per person per day. Every query is scoped to one person (their
Firebase uid), so accounts never see each other's journal. (Atomic facts pulled
from an entry live in facts.py; semantic "find similar past moments" lives in
recall.py with pgvector.)

Only today is writable. There is no function here that takes a day to write to
— the past simply has no entry point, rather than a guard that says no.
"""
from datetime import date

from sqlalchemy import func, select

from app.core import clock, db
from app.models import Entry

# How many times a day may be reworked after it was first written. Editing the
# text and re-running the analysis draw on the same allowance: the point is that
# a day settles, not that one kind of change is cheaper than the other.
EDIT_LIMIT = 3


class EditLimitReached(Exception):
    """Raised when today's allowance of edits and re-analyses is used up."""


def today_entry(user_id: str) -> Entry | None:
    """This person's entry for today, if they've started one."""
    return entry_on(clock.today(), user_id)


def entry_on(day: date, user_id: str) -> Entry | None:
    """This person's entry for one journal day, or None."""
    with db.get_session() as s:
        stmt = select(Entry).where(Entry.user_id == user_id, Entry.entry_date == day)
        return s.scalars(stmt).first()


def entry_on_id(entry_id: int, user_id: str) -> Entry | None:
    """One entry by id, but only if it belongs to this person.

    Scoping the lookup by uid rather than checking ownership afterwards means a
    guessed id reads as "no such entry" — there is no branch where someone
    else's day is loaded and then rejected.
    """
    with db.get_session() as s:
        stmt = select(Entry).where(Entry.id == entry_id, Entry.user_id == user_id)
        return s.scalars(stmt).first()


def save_today(content: str, user_id: str, energy: int | None = None) -> Entry:
    """Write or rewrite today's entry; return it.

    The first write of the day is free. Every rewrite after that spends one of
    EDIT_LIMIT, and raises EditLimitReached once they're gone.
    """
    day = clock.today()
    with db.get_session() as s:
        stmt = select(Entry).where(Entry.user_id == user_id, Entry.entry_date == day)
        entry = s.scalars(stmt).first()
        if entry is None:
            entry = Entry(user_id=user_id, entry_date=day, content=content, energy=energy)
            s.add(entry)
        else:
            if entry.edit_count >= EDIT_LIMIT:
                raise EditLimitReached
            entry.edit_count += 1
            entry.content = content
            if energy is not None:
                entry.energy = energy
        s.commit()
        return entry


def spend_edit(entry_id: int) -> Entry:
    """Charge one of the day's allowance without changing the text.

    Re-running the analysis costs the same as an edit — see EDIT_LIMIT.
    """
    with db.get_session() as s:
        entry = s.get(Entry, entry_id)
        if entry is None:
            raise LookupError(f"no entry {entry_id}")
        if entry.edit_count >= EDIT_LIMIT:
            raise EditLimitReached
        entry.edit_count += 1
        s.commit()
        return entry


def mark_analyzed(entry_id: int) -> None:
    """Record that this day's facts have just been extracted."""
    from app.models.base import now

    with db.get_session() as s:
        entry = s.get(Entry, entry_id)
        if entry is not None:
            entry.analyzed_at = now()
            s.commit()


def entries_between(start: date, end: date, user_id: str) -> list[Entry]:
    """One person's entries across a date range, oldest first.

    Days with no entry simply aren't there — the energy chart shows a gap
    rather than inventing a value for a day nobody wrote.
    """
    with db.get_session() as s:
        stmt = (
            select(Entry)
            .where(
                Entry.user_id == user_id,
                Entry.entry_date >= start,
                Entry.entry_date <= end,
            )
            .order_by(Entry.entry_date)
        )
        return list(s.scalars(stmt))


def recent_entries(user_id: str, limit: int = 30) -> list[Entry]:
    """One person's most recent entries, newest first — raw material for the profile."""
    with db.get_session() as s:
        stmt = (
            select(Entry)
            .where(Entry.user_id == user_id)
            .order_by(Entry.entry_date.desc())
            .limit(limit)
        )
        return list(s.scalars(stmt))


def count_entries(user_id: str) -> int:
    """How many entries one person has."""
    with db.get_session() as s:
        stmt = select(func.count()).select_from(Entry).where(Entry.user_id == user_id)
        return s.scalar(stmt) or 0
