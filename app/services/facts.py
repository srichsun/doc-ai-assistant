"""Atomic facts pulled from each exchange — the semantic-memory raw material.

One journaling turn often mixes several topics. Instead of storing the whole
turn as one vector (which blurs the topics together), we ask a small model to
break it into 5-10 single-topic facts, each filed under one fixed `category`.
Each fact is then embedded on its own, so recall over "health" matches only the
health fact, not a whole turn where health was one thread among many.

One of the categories is `wins` — the concrete things the person actually did
that count. That's the same material the old tag extraction produced, now folded
into this single call so there's no second model round-trip: the wins review
screen and the strengths passage both read wins straight back out of here.
"""
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core import db
from app.models import Fact
from app.services import chat_model, recall

# The eight "who this person is" categories, plus `wins` (what they did that
# counts). Fixed on purpose: a bounded set keeps recall filters and the coach's
# category choices predictable. Order is the order the model sees them.
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
    "- wins: what they did today that counts, one concrete thing each. Plain "
    "and factual ('cold shower', 'two hours on the project while exhausted'). "
    "Small counts — holding momentum on a hard day is a win. No coach voice, "
    "no adjectives, no explaining why it mattered. Skip only what carried no "
    "intent (ate lunch, commuted).\n"
    "Keep each fact to one topic — never fold work and health into one line. "
    "Only state what's actually here; invent nothing. Return an empty list if "
    "there is genuinely nothing.\n\n"
    "Person: {transcript}\nCoach: {reply}"
)


def extract_and_save(
    entry_id: int, transcript: str, reply: str, user_id: str
) -> list[int]:
    """Pull atomic facts from one exchange, store them, and index each.

    Returns the new fact row ids. One model call does all the categorising,
    including wins, so the store stays a single source for both semantic recall
    and the wins list.
    """
    result = _extractor.invoke(
        _EXTRACT_PROMPT.format(transcript=transcript, reply=reply)
    )
    fact_ids: list[int] = []
    with db.get_session() as s:
        rows = [
            Fact(
                user_id=user_id,
                entry_id=entry_id,
                category=f.category,
                text=f.text,
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


def recent_wins(user_id: str, limit: int = 20) -> list[Fact]:
    """One person's most recent win facts, newest first.

    The raw material for the wins review screen and the strengths passage.
    """
    with db.get_session() as s:
        stmt = (
            select(Fact)
            .where(Fact.user_id == user_id, Fact.category == "wins")
            .order_by(Fact.created_at.desc(), Fact.id.desc())
            .limit(limit)
        )
        return list(s.scalars(stmt))


def existing_fact_entry_ids(user_id: str) -> set[int]:
    """The entry ids that already have facts — so a backfill can skip them."""
    with db.get_session() as s:
        stmt = select(Fact.entry_id).where(Fact.user_id == user_id).distinct()
        return set(s.scalars(stmt))
