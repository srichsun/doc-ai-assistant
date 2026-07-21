"""Who this person is, written from their own record.

The wins list answers "what did I do" — day by day, concrete, small. This
answers a harder question: "what does all of that say about me?"

An LLM reads the whole journal of wins and writes back a short passage in
plain prose. Not a list of capabilities (too clinical, too easy to skim past)
— a few paragraphs that sound like someone who knows you, reminding you what
you're actually like when things are hard. It's meant to be read on the days
you've forgotten.

Stored alongside the profile (same table, a suffixed key) because it is the
same idea: a bounded, LLM-condensed view of a person, rewritten as the
journal grows.
"""
from app.core import db
from app.models import Profile
from app.services import chat_model, entries, facts

# Rewrite once this many new entries have piled up. Slower than the profile's
# cadence — who you are does not change week to week, and re-reading the whole
# journal is a bigger call.
REFRESH_EVERY = 10

# How many entries' wins to draw on. The whole journal at this scale; the cap
# keeps one call bounded as the history grows.
SOURCE_LIMIT = 200


def _key(user_id: str) -> str:
    """Where this person's passage lives in the profiles table."""
    return f"{user_id}:strengths"


_CONDENSE_PROMPT = (
    "Below is everything this person has done, gathered from their journal.\n\n"
    "Write them a short passage — 130 to 190 words — about who they are, "
    "drawn only from what is actually here. Flowing prose, second person, "
    "warm and plain. Not a list, no headers, no bullet points.\n\n"
    "This gets read on the days they are frightened and have forgotten "
    "themselves. So name the pattern their own record proves: how they behave "
    "when it's hard, what they keep doing anyway, what they have already come "
    "through. Reach for their real specifics — the small ones especially, "
    "because those are the ones that convince.\n\n"
    "Never flatter and never generalise into 'you're amazing'. The evidence "
    "is what makes it land; without it this is worthless to them. Do not "
    "invent anything that isn't below.\n\n"
    "End on something steadying they can hold onto — true, not a slogan.\n\n"
    "What they've done:\n{wins}"
)


def get_strengths(user_id: str) -> str:
    """This person's passage, or "" if one hasn't been written yet."""
    if not user_id:
        return ""
    with db.get_session() as s:
        row = s.get(Profile, _key(user_id))
        if not row or not row.content:
            return ""
        content = row.content
    # An earlier version stored a JSON list here; treat it as not-yet-written
    # so the next refresh replaces it rather than showing raw JSON.
    return "" if content.lstrip().startswith("[") else content


def as_prompt_text(user_id: str) -> str:
    """The passage, for injecting into her prompt when they're struggling."""
    return get_strengths(user_id)


def refresh_strengths(user_id: str) -> str:
    """Rewrite this person's passage from their journal and save it."""
    if not user_id:
        return ""
    rows = facts.recent_wins(user_id=user_id, limit=SOURCE_LIMIT)
    wins_text = "\n".join(r.text for r in rows if r.text)
    if not wins_text:
        return ""

    passage = (
        chat_model.build_chat_model()
        .invoke(_CONDENSE_PROMPT.format(wins=wins_text))
        .content.strip()
    )

    with db.get_session() as s:
        row = s.get(Profile, _key(user_id))
        if row is None:
            row = Profile(key=_key(user_id))
            s.add(row)
        row.content = passage
        row.entry_count = entries.count_entries(user_id)
        s.commit()
    return passage


def maybe_refresh(user_id: str) -> None:
    """Rewrite only once enough new entries have accumulated."""
    if not user_id:
        return
    with db.get_session() as s:
        row = s.get(Profile, _key(user_id))
        last_count = row.entry_count if row else 0
    if entries.count_entries(user_id) - last_count >= REFRESH_EVERY:
        refresh_strengths(user_id)
