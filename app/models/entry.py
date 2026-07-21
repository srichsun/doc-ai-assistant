"""One journal entry — a single conversation turn.

What the user said and what the coach replied. The things once pulled out onto
this row (mood, wins, themes) now live as atomic facts (see app.models.fact and
app.services.facts); those columns were retired from the model, though the
physical DB columns stay until an Alembic migration drops them.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, now


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, index=True
    )
    # Firebase uid of the person this entry belongs to. Required: an entry with
    # no owner could never be read back, since every query scopes by uid.
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    transcript: Mapped[str] = mapped_column(Text)  # what the user said
    ai_reply: Mapped[str] = mapped_column(Text)  # what the coach replied
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
