"""One journal entry — a single conversation turn.

What the user said, what the coach replied, plus a few things the coach pulled
out (mood, wins, themes) so we can later list "this month's wins" or chart mood
without re-reading every entry.
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
    # Firebase uid of the person this entry belongs to. Nullable so pre-auth
    # rows still load; new rows always carry it.
    user_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    transcript: Mapped[str] = mapped_column(Text)  # what the user said
    ai_reply: Mapped[str] = mapped_column(Text)  # what the coach replied
    # The coach fills these in; all optional. wins/themes are kept as plain
    # text (comma-separated) to stay simple and DB-portable.
    mood: Mapped[str | None] = mapped_column(String(32), nullable=True)
    wins: Mapped[str | None] = mapped_column(Text, nullable=True)
    themes: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
