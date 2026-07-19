"""Durable strengths — what the journal says this person is capable of.

The wins recorded on each entry are observations about *a day*: "you adjusted
instead of forcing performance". Useful in the moment, but after a few weeks
there are hundreds of them, all the same size, mostly restating each other —
and someone in the middle of an anxiety spiral cannot read a hundred lines.

This layer answers a different question: not "what did you do on Tuesday" but
"what are you reliably capable of". An LLM folds the scattered wins into a
handful of durable strengths, each carrying the concrete moments that prove
it. That is the thing worth reading when you are frightened.

Stored alongside the profile (same table, a suffixed key) because it is the
same idea: a bounded, LLM-condensed view of a person that gets rewritten as
the journal grows.
"""
import json

from pydantic import BaseModel, Field

from app.core import db
from app.models import Profile
from app.services import chat_model, entries

# Re-condense once this many new entries have piled up. Higher than the
# profile's cadence — strengths are meant to be stable, and re-reading the
# whole journal costs a bigger LLM call.
REFRESH_EVERY = 10

# How many entries' wins to fold in. The whole journal at this scale; the cap
# keeps one condense call bounded as the history grows.
SOURCE_LIMIT = 200


def _key(user_id: str) -> str:
    """Where this person's strengths live in the profiles table."""
    return f"{user_id}:strengths"


class Strength(BaseModel):
    """One lasting capability, plus the moments that earned it."""

    title: str = Field(
        description=(
            "The capability itself, in second person, as something that is "
            "lastingly true about them — 'You pull yourself back from a low' "
            "— never a single day's event. Short, plain, and quietly confident."
        )
    )
    evidence: list[str] = Field(
        description=(
            "The concrete moments proving it, drawn from their journal. Each "
            "one specific and factual ('stayed with the two-hour Python "
            "session while exhausted'), never a restatement of the title."
        )
    )


class StrengthList(BaseModel):
    strengths: list[Strength]


_CONDENSE_PROMPT = (
    "Below are the wins recorded across this person's journal. Many of them "
    "describe the same underlying capability in different words, on different "
    "days.\n\n"
    "Find the 5-8 capabilities that are genuinely, lastingly true about this "
    "person, and gather the evidence for each.\n\n"
    "Rules:\n"
    "- Merge restatements. If 'chose structure over avoidance', 'turned a "
    "spiral into a reset', and 'adjusted instead of forcing' are the same "
    "capability, they are ONE strength with three pieces of evidence.\n"
    "- A strength is who they are, not what happened on a Tuesday. Write it "
    "so it would still be true next month.\n"
    "- Ground every strength in real evidence from the entries. Never invent "
    "or flatter — an unearned strength is worse than a missing one.\n"
    "- Order them by how much evidence supports them, strongest first.\n"
    "- Keep each piece of evidence to one concrete sentence.\n\n"
    "This is read by someone who is anxious and needs to remember what they "
    "are capable of. Make it true, specific, and steadying.\n\n"
    "Their recorded wins:\n{wins}"
)


def _condense_model():
    """The model that does the folding, forced to return the structure above."""
    return chat_model.build_chat_model().with_structured_output(StrengthList)


def get_strengths(user_id: str | None) -> list[dict]:
    """This person's current strengths, or [] if none have formed yet."""
    if not user_id:
        return []
    with db.get_session() as s:
        row = s.get(Profile, _key(user_id))
        if not row or not row.content:
            return []
    try:
        return json.loads(row.content)
    except ValueError:
        return []  # a half-written or legacy value shouldn't break the screen


def as_prompt_text(user_id: str | None) -> str:
    """The strengths as plain lines, for injecting into the coach's prompt."""
    items = get_strengths(user_id)
    if not items:
        return ""
    return "\n".join(
        "- {title} (e.g. {first})".format(
            title=s["title"], first=(s.get("evidence") or ["—"])[0]
        )
        for s in items
    )


def refresh_strengths(user_id: str | None) -> list[dict]:
    """Re-fold this person's wins into strengths and save them."""
    if not user_id:
        return []
    rows = entries.recent_wins(user_id=user_id, limit=SOURCE_LIMIT)
    wins_text = "\n\n".join(r.wins for r in rows if r.wins)
    if not wins_text:
        return []

    result = _condense_model().invoke(_CONDENSE_PROMPT.format(wins=wins_text))
    items = [s.model_dump() for s in result.strengths]

    with db.get_session() as s:
        row = s.get(Profile, _key(user_id))
        if row is None:
            row = Profile(key=_key(user_id))
            s.add(row)
        row.content = json.dumps(items, ensure_ascii=False)
        row.entry_count = entries.count_entries(user_id)
        s.commit()
    return items


def maybe_refresh(user_id: str | None) -> None:
    """Re-fold only once enough new entries have accumulated."""
    if not user_id:
        return
    with db.get_session() as s:
        row = s.get(Profile, _key(user_id))
        last_count = row.entry_count if row else 0
    if entries.count_entries(user_id) - last_count >= REFRESH_EVERY:
        refresh_strengths(user_id)
