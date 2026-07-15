"""The life-coach agent, built on LangChain.

LangChain's create_agent gives us the whole "call the model, run any tools,
loop until it's done" cycle for free, so we don't hand-write that loop anymore.
Conversation memory is handled by a checkpointer keyed on the session id:
same id -> same remembered conversation.

Right now the coach has no tools (it just talks). Later phases add tools like
log_entry (save a journal entry) and search_past_entries (recall the past).
"""
import uuid

from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field

from app import config, entries

SYSTEM_PROMPT = (
    "You are a warm, encouraging personal life coach and journaling companion. "
    "The person talks to you about their day, their feelings, and their goals. "
    "Listen first, reflect back what you hear, and validate how they feel. "
    "Gently help them notice their small wins and the patterns in how they live. "
    "Ask one thoughtful question when it genuinely helps — don't interrogate. "
    "Keep replies short, kind, and human. Never sound clinical or preachy."
)


def _default_model() -> ChatAnthropic:
    """The real Claude model used in production (needs an API key)."""
    return ChatAnthropic(
        model_name=config.CHAT_MODEL,
        api_key=config.ANTHROPIC_API_KEY,
        max_tokens=config.MAX_TOKENS,
        timeout=30.0,  # fail fast instead of hanging the worker
    )


def build_agent(model):
    """Wrap a chat model into a coach agent with memory.

    Split out so tests can pass a fake, offline model instead of real Claude.
    """
    return create_agent(
        model,
        tools=[],  # no tools yet — added in later phases
        system_prompt=SYSTEM_PROMPT,
        checkpointer=InMemorySaver(),
    )


# Built once at startup and reused for every request.
_agent = build_agent(_default_model())


def run(message: str, session_id: str | None = None) -> dict:
    """Send one message to the coach and get its reply.

    Pass the same session_id across turns to keep the conversation's memory.
    With no session_id, the turn is one-off (a throwaway id, so anonymous
    turns never bleed into each other).

    Returns {"answer", "tools_used", "sources", "session_id"}.
    """
    thread_id = session_id or f"anon-{uuid.uuid4()}"
    cfg = {"configurable": {"thread_id": thread_id}}
    result = _agent.invoke(
        {"messages": [{"role": "user", "content": message}]}, cfg
    )
    reply = result["messages"][-1].content  # the coach's latest reply text
    return {
        "answer": reply,
        "tools_used": [],
        "sources": [],
        "session_id": session_id,
    }


class EntryTags(BaseModel):
    """The few things we pull out of an exchange to store alongside the text,
    so later we can list wins or chart mood without re-reading everything."""

    mood: str | None = Field(
        None, description="one word for the person's mood, e.g. anxious, proud, calm"
    )
    wins: str | None = Field(
        None, description="a short win the person mentioned, else null"
    )
    themes: str | None = Field(
        None, description="comma-separated topics, e.g. work, health, family"
    )


# A small model call that only returns the structured tags above.
_extractor = _default_model().with_structured_output(EntryTags)


def extract_tags(transcript: str, reply: str) -> EntryTags:
    """Pull mood / wins / themes out of one exchange."""
    prompt = (
        "From this journaling exchange, extract the person's mood, any win they "
        "mentioned, and the main themes. Use null when something isn't there.\n"
        f"Person: {transcript}\nCoach: {reply}"
    )
    return _extractor.invoke(prompt)


def chat_and_log(message: str, session_id: str | None = None) -> dict:
    """Reply as the coach, then save the exchange as a journal entry.

    Every turn is saved on purpose — that's the whole point (unlike ChatGPT,
    nothing is forgotten). If tag extraction fails, we still save the raw
    exchange with empty tags rather than lose it.
    """
    result = run(message, session_id)
    reply = result["answer"]
    try:
        tags = extract_tags(message, reply)
    except Exception:
        tags = EntryTags()
    entries.save_entry(
        transcript=message,
        ai_reply=reply,
        session_id=session_id,
        mood=tags.mood,
        wins=tags.wins,
        themes=tags.themes,
    )
    return result
