"""Rolling user profile — the long-term memory layer ("gets to know you").

The other two memory layers look backward at individual moments: structured SQL
(entries) answers "what happened when", semantic recall (pgvector) finds "a
similar past moment". The profile is different — a short, always-current summary
of who this person *is*: their goals, habits, recurring worries, what triggers
them, what helps. An LLM condenses it from the journal and it's injected into
every conversation, so the coach steadily understands them better without ever
re-reading the whole history.

Fixed size on purpose: injected every turn, so it must not grow without bound.
"""
from langchain_anthropic import ChatAnthropic

from app import config, db, entries
from app.models import Profile

# Re-condense the profile once this many new entries have accumulated. Cheap,
# deterministic, and good enough — we don't need a real-time rewrite every turn.
REFRESH_EVERY = 5

_CONDENSE_PROMPT = (
    "You maintain a concise, evolving profile of a person, built from their "
    "journal. Update the profile below with anything new and lasting from the "
    "recent entries: their goals, habits, recurring worries, what triggers "
    "them, what helps, and the people who matter. Keep what is still true, drop "
    "one-off trivia, and write it as short bullet points under 150 words.\n\n"
    "Current profile:\n{existing}\n\n"
    "Recent journal entries (newest first):\n{recent}\n\n"
    "Updated profile:"
)


def _condense_model() -> ChatAnthropic:
    """The model that rewrites the profile (real Claude; needs a key)."""
    return ChatAnthropic(
        model_name=config.CHAT_MODEL,
        api_key=config.ANTHROPIC_API_KEY,
        max_tokens=config.MAX_TOKENS,
        timeout=30.0,
    )


def get_profile(user_id: str | None) -> str:
    """One person's current profile text, or "" if none has formed yet.

    The profile row is keyed by the person's Firebase uid.
    """
    with db.get_session() as s:
        row = s.get(Profile, user_id)
        return row.content if row else ""


def condense(existing: str, recent_text: str) -> str:
    """Fold recent entries into the existing profile and return the new text."""
    prompt = _CONDENSE_PROMPT.format(
        existing=existing or "(empty)", recent=recent_text or "(none)"
    )
    return _condense_model().invoke(prompt).content.strip()


def refresh_profile(user_id: str | None) -> str:
    """Re-condense one person's profile from their latest entries and save it.

    Returns the updated profile text.
    """
    rows = entries.recent_entries(user_id)
    recent_text = "\n".join(f"- {e.transcript}" for e in rows)
    existing = get_profile(user_id)
    updated = condense(existing, recent_text)
    with db.get_session() as s:
        row = s.get(Profile, user_id)
        if row is None:
            row = Profile(key=user_id)
            s.add(row)
        row.content = updated
        row.entry_count = entries.count_entries(user_id)
        s.commit()
    return updated


def maybe_refresh(user_id: str | None) -> None:
    """Refresh one person's profile only when enough new entries have piled up.

    Called after saving each entry. Cheap no-op most turns; runs the condense
    LLM call about once every REFRESH_EVERY entries.
    """
    with db.get_session() as s:
        row = s.get(Profile, user_id)
        last_count = row.entry_count if row else 0
    if entries.count_entries(user_id) - last_count >= REFRESH_EVERY:
        refresh_profile(user_id)
