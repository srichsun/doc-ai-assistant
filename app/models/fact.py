"""One atomic fact pulled from a journal exchange.

A single thing the person said gets broken into several single-topic facts, so
each can be embedded and searched on its own — searching "health" then matches
only the health fact, not a whole three-minute turn where health was one thread
among work and relationships. Every fact carries a `category` (one of the fixed
set in app.services.facts.CATEGORIES) so recall can pull back just the relevant
kinds, and the coach can say which kinds it wants.

`entry_id` and `created_at` are kept so a later pass can merge a day's facts or
count how often a pattern recurs; today nothing reads them beyond scoping.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, now


class Fact(Base):
    __tablename__ = "facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Firebase uid of the person this fact is about; every query scopes by it.
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    # The journal entry this fact was pulled from — several facts share one.
    entry_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    # One of the fixed categories (see app.services.facts.CATEGORIES).
    category: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    text: Mapped[str] = mapped_column(Text)  # the single-topic statement itself
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, index=True
    )
