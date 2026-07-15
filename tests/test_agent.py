"""Tests for the life-coach agent and the tool helpers.

The coach is driven by a fake, offline chat model, so these tests spend no
tokens and need no API key.
"""
from datetime import datetime, timezone

from langchain_core.language_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app import agent, entries, rag, tools


def _coach_with(replies):
    """Build a coach backed by a fake model that returns the given replies."""
    fake = GenericFakeChatModel(messages=iter([AIMessage(r) for r in replies]))
    return agent.build_agent(fake)


# --- coach agent ---

def test_coach_replies(monkeypatch):
    monkeypatch.setattr(agent, "_agent", _coach_with(["you've got this"]))
    result = agent.run("I feel down today")
    assert result == {
        "answer": "you've got this",
        "tools_used": [],
        "sources": [],
        "session_id": None,
    }


def test_coach_remembers_within_a_session(monkeypatch):
    monkeypatch.setattr(agent, "_agent", _coach_with(["hi there", "second reply"]))
    agent.run("first message", session_id="s-1")
    result = agent.run("second message", session_id="s-1")
    # Same session id -> the same agent handled both turns, in order.
    assert result["answer"] == "second reply"
    assert result["session_id"] == "s-1"


def test_chat_and_log_saves_a_journal_entry(sqlite_db, monkeypatch):
    monkeypatch.setattr(agent, "_agent", _coach_with(["proud of you"]))
    # Skip the real extraction LLM call; return fixed tags.
    monkeypatch.setattr(
        agent,
        "extract_tags",
        lambda t, r: agent.EntryTags(mood="proud", wins="ran 5k", themes="health"),
    )

    result = agent.chat_and_log("I ran 5k today", session_id="s-log")
    assert result["answer"] == "proud of you"

    # The exchange should now be in the database.
    saved = entries.entries_on(datetime.now(timezone.utc).date())
    assert len(saved) == 1
    assert saved[0].transcript == "I ran 5k today"
    assert saved[0].mood == "proud"
    assert saved[0].wins == "ran 5k"


# --- tool helpers (from the original engine, reused by later phases) ---

def test_dispatch_lookup_order():
    assert "iPhone" in tools.dispatch("lookup_order", {"order_id": "1001"})
    assert "No order" in tools.dispatch("lookup_order", {"order_id": "9999"})


def test_dispatch_unknown_tool():
    assert tools.dispatch("nope", {}) == "Unknown tool: nope"


def test_search_documents_uses_retrieval(monkeypatch):
    monkeypatch.setattr(rag, "retrieve", lambda q: [{"source": "d.md", "text": "hi"}])
    assert tools.search_documents("q") == "[d.md] hi"
