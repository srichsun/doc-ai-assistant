"""Atomic facts pulled from each exchange — the semantic-memory raw material.

One journaling turn often mixes several topics. Instead of storing the whole
turn as one vector (which blurs the topics together), we ask a small model to
break it into 5-10 single-topic facts, each filed under one fixed `category`.
Each fact is then embedded on its own, so recall over "health" matches only the
health fact, not a whole turn where health was one thread among many.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core import db
from app.models import Fact
from app.services import chat_model, recall

# The eight "who this person is" categories, plus `wins` — what they actually
# did that counts. Wins earn their own category because "remind me what I've
# done" is a different question from "what am I like", and she needs to be able
# to search for it directly on the days someone has forgotten. Fixed on purpose:
# a bounded set keeps recall filters and the coach's category choices
# predictable. Order is the order the model sees them.
CATEGORIES = (
    "about me",
    "preferences",
    "people",
    "work & career",
    "goals & aspirations",
    "health & habits",
    "beliefs",
    "patterns",
    "wins",
)


class _Fact(BaseModel):
    """One single-topic statement about the person, filed under one category."""

    category: Literal[
        "about me",
        "preferences",
        "people",
        "work & career",
        "goals & aspirations",
        "health & habits",
        "beliefs",
        "patterns",
        "wins",
    ] = Field(description="which category this fact belongs to")
    text: str = Field(description="the single-topic statement, in plain words")


class _FactList(BaseModel):
    """The facts pulled from one exchange."""

    facts: list[_Fact] = Field(default_factory=list)


# A small model call that only returns the structured facts above — same shape
# as the profile condenser and the old tag extractor.
_extractor = chat_model.build_chat_model().with_structured_output(_FactList)

_EXTRACT_PROMPT = (
    "Break this journaling exchange into atomic facts about the person — 5 to "
    "10 short, single-topic statements. Each fact must sit under exactly one "
    "category:\n"
    "- about me: lasting facts about who they are (age, job, where they live, "
    "situation).\n"
    "- preferences: how they like things — to be talked to, to work, to live.\n"
    "- people: the people who matter and their relationships to them.\n"
    "- work & career: their work, projects, ambitions, and struggles there.\n"
    "- goals & aspirations: what they're reaching for.\n"
    "- health & habits: body, sleep, exercise, routines, coping.\n"
    "- beliefs: values and convictions they hold.\n"
    "- patterns: recurring behaviour, especially how they act under stress.\n"
    "- wins: something they actually did that counts, stated plainly ('cold "
    "shower', 'two hours on the project while exhausted', 'made a call they "
    "were afraid of'). Small counts — holding momentum on a hard day is a win. "
    "No praise, no adjectives, no explaining why it mattered.\n"
    "Keep each fact to one topic — never fold work and health into one line. "
    "Only state what's actually here; invent nothing. Return an empty list if "
    "there is genuinely nothing.\n\n"
    "Person: {transcript}\nCoach: {reply}"
)


def extract_and_save(
    entry_id: int,
    transcript: str,
    reply: str,
    user_id: str,
    created_at: datetime | None = None,
) -> list[int]:
    """Pull atomic facts from one exchange, store them, and index each.

    Returns the new fact row ids.

    created_at defaults to now, which is right for a live exchange. Backfilling
    old entries must pass the entry's own timestamp instead.
    """
    result = _extractor.invoke(
        _EXTRACT_PROMPT.format(transcript=transcript, reply=reply)
    )
    fact_ids: list[int] = []
    # A fact happened when its exchange did, not when we got round to reading
    # it, so a backfill of months of journal must not stamp everything today.
    stamp = {"created_at": created_at} if created_at is not None else {}
    with db.get_session() as s:
        rows = [
            Fact(
                user_id=user_id,
                entry_id=entry_id,
                category=f.category,
                text=f.text,
                **stamp,
            )
            for f in result.facts
            if f.text and f.text.strip()
        ]
        s.add_all(rows)
        s.commit()
        for row in rows:
            fact_ids.append(row.id)
            recall.index_fact(
                row.id, row.text, user_id=user_id, category=row.category
            )
    return fact_ids


def existing_fact_entry_ids(user_id: str) -> set[int]:
    """The entry ids that already have facts — so a backfill can skip them."""
    with db.get_session() as s:
        stmt = select(Fact.entry_id).where(Fact.user_id == user_id).distinct()
        return set(s.scalars(stmt))
