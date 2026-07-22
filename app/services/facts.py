"""Atomic facts pulled from each journal entry — the semantic-memory raw material.

A day's writing mixes several topics. Instead of storing the whole entry as one
vector (which blurs the topics together), we ask a small model to break it into
5-10 single-topic facts, each filed under one fixed `category`. Each fact is
then embedded on its own, so recall over "health" matches only the health fact,
not a whole day where health was one thread among many.

Extraction runs only when the person presses Analyse. Nothing else in the app
writes facts, so the memory grows from what they chose to write down.
"""
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core import db
from app.models import Category, Fact
from app.services import chat_model, recall


class _Fact(BaseModel):
    """One single-topic statement about the person, filed under one category."""

    category: Category = Field(
        description="which category this fact belongs to"
    )
    text: str = Field(description="the single-topic statement, in plain words")


class _FactList(BaseModel):
    """The facts pulled from one exchange."""

    facts: list[_Fact] = Field(default_factory=list)


# A small model call that only returns the structured facts above — same shape
# as the profile condenser and the old tag extractor.
_extractor = chat_model.build_chat_model().with_structured_output(_FactList)

_EXTRACT_PROMPT = (
    "Break this day's journal entry into atomic facts about the person — 5 to "
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
    "- gratitude: something they were glad of that day — a person, a moment, "
    "something that went right. State it plainly, as they'd say it.\n"
    "Keep each fact to one topic — never fold work and health into one line.\n"
    "Write each fact TO the person, in the second person: \"went for a run "
    "while exhausted\", \"your sister is the one you call first\". Never write "
    "about them in the third person and never use they/their — there is only "
    "one person here, and these lines get read back to them.\n"
    "Never use a relative date — no \"yesterday\", \"last week\", \"this "
    "morning\". Each fact is read months later with no idea when it was "
    "written, so a relative date points at nothing. Say what happened, not "
    "when, unless the entry gives an actual date.\n"
    "Only state what's actually here; invent nothing. Return an empty list if "
    "there is genuinely nothing.\n\n"
    "Journal entry:\n{content}"
)


def extract_and_save(
    entry_id: int,
    content: str,
    user_id: str,
    created_at: datetime | None = None,
) -> list[int]:
    """Pull atomic facts from one day's journal entry, store them, index each.

    Returns the new fact row ids.

    created_at defaults to now, which is right for a day being analysed as it
    happens. Backfilling old entries must pass the entry's own timestamp.
    """
    result = _extractor.invoke(_EXTRACT_PROMPT.format(content=content))
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


def replace_for_entry(entry_id: int, content: str, user_id: str) -> list[int]:
    """Re-extract one day's facts, discarding whatever was there before.

    Analysing the same day twice must not leave both readings in memory: the
    old facts are deleted from SQL and from the vector store first, so what the
    coach knows about that day is always the latest reading of it.
    """
    forget_entry(entry_id, user_id)
    return extract_and_save(entry_id, content, user_id)


def forget_entry(entry_id: int, user_id: str) -> None:
    """Delete one day's facts from both stores."""
    with db.get_session() as s:
        stmt = select(Fact).where(Fact.user_id == user_id, Fact.entry_id == entry_id)
        rows = list(s.scalars(stmt))
        if not rows:
            return
        ids = [r.id for r in rows]
        for row in rows:
            s.delete(row)
        s.commit()
    try:
        recall.forget_facts(ids)
    except Exception:
        # The SQL rows are gone either way; a stale vector is recoverable by
        # re-indexing, but losing the delete of the rows would not be.
        pass


def for_entries(
    entry_ids: list[int], user_id: str, categories: tuple[str, ...] | None = None
) -> dict[int, list[Fact]]:
    """The stored facts for these days, grouped by entry id.

    The record screen reads wins and gratitude back this way — plain SQL by id,
    no embeddings involved. Semantic search is for "find me something like
    this"; showing a day's own facts is just a lookup.
    """
    if not entry_ids:
        return {}
    with db.get_session() as s:
        stmt = select(Fact).where(
            Fact.user_id == user_id, Fact.entry_id.in_(entry_ids)
        )
        if categories:
            stmt = stmt.where(Fact.category.in_(categories))
        grouped: dict[int, list[Fact]] = {}
        for row in s.scalars(stmt.order_by(Fact.id)):
            grouped.setdefault(row.entry_id, []).append(row)
        return grouped


def existing_fact_entry_ids(user_id: str) -> set[int]:
    """The entry ids that already have facts — so a backfill can skip them."""
    with db.get_session() as s:
        stmt = select(Fact.entry_id).where(Fact.user_id == user_id).distinct()
        return set(s.scalars(stmt))
