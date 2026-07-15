"""Database models for the journal.

One row per conversation turn: what the user said, what the coach replied,
plus a few things the coach pulled out (mood, wins, themes) so we can later
list "this month's wins" or chart mood without re-reading every entry.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transcript: Mapped[str] = mapped_column(Text)  # what the user said
    ai_reply: Mapped[str] = mapped_column(Text)  # what the coach replied
    # The coach fills these in; all optional. wins/themes are kept as plain
    # text (comma-separated) to stay simple and DB-portable.
    mood: Mapped[str | None] = mapped_column(String(32), nullable=True)
    wins: Mapped[str | None] = mapped_column(Text, nullable=True)
    themes: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class Profile(Base):
    """The long-term, always-current summary of a person, condensed by an LLM
    from their journal and injected into every conversation. Kept to a fixed
    size on purpose — it's sent every turn, so it must not grow without bound.

    Keyed by a string so Phase 6 (auth) can switch "default" to a real user id
    without a schema change.
    """

    __tablename__ = "profiles"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[str] = mapped_column(Text, default="")
    # How many journal entries have been folded in, so we can refresh every N.
    entry_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
