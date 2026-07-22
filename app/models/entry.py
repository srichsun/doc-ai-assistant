"""One journal entry — one person's writing for one day.

A day is the unit of this product: exactly one entry per person per calendar
day (Taiwan time, see app.core.clock), enforced by a unique index rather than
by a check in the service layer. Writing a second entry for a day isn't
disallowed, it's impossible.

Only today can be written to. Past days are read-only — there is no code path
that opens one for editing, so "the past is the past" is a property of the
schema, not a rule someone has to remember.
"""
from datetime import date, datetime

from sqlalchemy import DateTime, Date, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, now


class Entry(Base):
    __tablename__ = "entries"
    __table_args__ = (
        UniqueConstraint("user_id", "entry_date", name="uq_entries_user_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Firebase uid of the person this entry belongs to. Required: an entry with
    # no owner could never be read back, since every query scopes by uid.
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    # The journal day this entry is for, in Taiwan time — not the UTC date of
    # created_at, which would roll over at 8am local and split a night in two.
    entry_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    content: Mapped[str] = mapped_column(Text)  # what they wrote
    # Self-rated energy, 1-10, filled in after writing. Nullable because an
    # entry can be saved before the person has rated the day.
    energy: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # How many times the day has been analysed (see
    # app.services.entries.ANALYSIS_LIMIT). Writing is free and unmetered — a
    # day gets added to all day long. Analysis is the part that costs a model
    # call, and the part that should settle rather than be reworked forever.
    analysis_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # When the facts for this day were last extracted; None means never.
    analyzed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now
    )
