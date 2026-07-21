"""Tests for the life-coach agent and the tool helpers.

The coach is driven by a fake, offline chat model, so these tests spend no
tokens and need no API key.
"""
from langchain_core.language_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.core import clock
from app.services import agent, entries


def _coach_with(replies):
    """Build a coach backed by a fake model that returns the given replies.

    tools=[] because the fake model can't bind tools (the real coach has the
    recall tool); these tests only exercise plain replies and memory.
    """
    fake = GenericFakeChatModel(messages=iter([AIMessage(r) for r in replies]))
    return agent._build_agent(fake, tools=[], middleware=[])


# --- coach agent ---

def test_coach_replies(monkeypatch):
    monkeypatch.setattr(agent, "_agent", _coach_with(["you've got this"]))
    assert agent._reply_to("I feel down today", "u1") == "you've got this"


def test_coach_replays_todays_conversation(sqlite_db, monkeypatch):
    """Memory comes from the journal, not from anything the caller passes in —
    which is what lets a conversation continue on another device or after a
    restart."""
    entries.save_entry("I was nervous", "tell me more", user_id="u1")
    seen = {}
    monkeypatch.setattr(
        agent,
        "_agent",
        type(
            "Spy",
            (),
            {"invoke": lambda self, state, **kw: seen.update(state) or {
                "messages": [AIMessage("ok")]
            }},
        )(),
    )
    agent._reply_to("and then?", user_id="u1")

    assert seen["messages"] == [
        {"role": "user", "content": "I was nervous"},
        {"role": "assistant", "content": "tell me more"},
        {"role": "user", "content": "and then?"},
    ]


def test_history_drops_oldest_when_a_day_runs_long(sqlite_db, monkeypatch):
    """The safety valve trims the oldest exchanges rather than letting the
    request blow past the model's context limit."""
    monkeypatch.setattr(agent, "MAX_HISTORY_CHARS", 100)
    entries.save_entry("x" * 80, "y" * 80, user_id="u1")  # oldest, too big
    entries.save_entry("recent", "reply", user_id="u1")

    history = agent._todays_conversation("u1")

    assert history == [
        {"role": "user", "content": "recent"},
        {"role": "assistant", "content": "reply"},
    ]


def test_history_is_empty_when_the_journal_cannot_be_read(monkeypatch):
    """A database hiccup must never swallow the person's message."""
    monkeypatch.setattr(
        agent.entries, "entries_on", lambda *a, **k: (_ for _ in ()).throw(OSError())
    )
    assert agent._todays_conversation("u1") == []


def test_reply_and_save_saves_a_journal_entry(sqlite_db, monkeypatch):
    monkeypatch.setattr(agent, "_agent", _coach_with(["proud of you"]))
    # Skip the real fact-extraction LLM + vector store; just record the call.
    extracted = []
    monkeypatch.setattr(
        agent.facts,
        "extract_and_save",
        lambda eid, transcript, reply, user_id=None: extracted.append(
            (eid, transcript, reply, user_id)
        )
        or [],
    )

    result = agent.reply_and_save("I ran 5k today", user_id="u1")
    assert result["answer"] == "proud of you"

    # The exchange should now be in the database, owned by u1.
    saved = entries.entries_on(clock.today(), user_id="u1")
    assert len(saved) == 1
    assert saved[0].transcript == "I ran 5k today"

    # ...and handed to fact extraction, keyed by the saved row id and user.
    assert extracted == [(saved[0].id, "I ran 5k today", "proud of you", "u1")]
