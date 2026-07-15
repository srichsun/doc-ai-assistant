"""The life-coach agent, built on LangChain.

LangChain's create_agent gives us the whole "call the model, run any tools,
loop until it's done" cycle for free, so we don't hand-write that loop anymore.
Conversation memory is handled by a checkpointer keyed on the session id:
same id -> same remembered conversation.

The coach has one tool, search_past_entries, which lets it recall relevant
past journal entries mid-conversation (semantic memory over pgvector).
"""
import uuid

from langchain.agents import create_agent
from langchain.agents.middleware import dynamic_prompt
from langchain_anthropic import ChatAnthropic
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field

from app import auth, config, entries, profile, recall

SYSTEM_PROMPT = (
    "You are a warm, encouraging personal life coach and journaling companion. "
    "The person talks to you about their day, their feelings, and their goals. "
    "Listen first, reflect back what you hear, and validate how they feel. "
    "Gently help them notice their small wins and the patterns in how they live. "
    "Ask one thoughtful question when it genuinely helps — don't interrogate. "
    "Keep replies short, kind, and human. Never sound clinical or preachy. "
    "When it would help to remember what they've shared before — a recurring "
    "worry, an earlier win, a similar day — use the search_past_entries tool "
    "to recall it, then weave it in naturally."
)


def _default_model() -> ChatAnthropic:
    """The real Claude model used in production (needs an API key)."""
    return ChatAnthropic(
        model_name=config.CHAT_MODEL,
        api_key=config.ANTHROPIC_API_KEY,
        max_tokens=config.MAX_TOKENS,
        timeout=30.0,  # fail fast instead of hanging the worker
    )


@dynamic_prompt
def _with_profile(request) -> str:
    """Prepend the person's long-term profile to the system prompt each turn,
    so the coach always talks with the freshest sense of who they are.

    Runs at model-call time; if the profile can't be read we just fall back to
    the base prompt rather than break the conversation.
    """
    try:
        summary = profile.get_profile(auth.current_uid.get())
    except Exception:
        summary = ""
    if not summary:
        return SYSTEM_PROMPT
    return f"{SYSTEM_PROMPT}\n\nWhat you already know about this person:\n{summary}"


def build_agent(model, tools=None, middleware=None):
    """Wrap a chat model into a coach agent with memory.

    Split out so tests can pass a fake, offline model instead of real Claude.
    Tests pass tools=[] (the fake model can't bind tools) and middleware=[]
    (so no profile lookup hits the database); the real coach defaults to the
    recall tool and the profile-injecting middleware.
    """
    if tools is None:
        tools = [recall.search_past_entries]
    if middleware is None:
        middleware = [_with_profile]
    return create_agent(
        model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=middleware,
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


def chat_and_log(
    message: str, user_id: str | None = None, session_id: str | None = None
) -> dict:
    """Reply as the coach, then save the exchange as a journal entry.

    Every turn is saved on purpose — that's the whole point (unlike ChatGPT,
    nothing is forgotten). Everything is scoped to user_id so accounts stay
    separate. If tag extraction fails, we still save the raw exchange with
    empty tags rather than lose it.
    """
    # Make the signed-in user visible to the agent's tools and profile
    # injection for the duration of this call.
    auth.current_uid.set(user_id)
    result = run(message, session_id)
    reply = result["answer"]
    try:
        tags = extract_tags(message, reply)
    except Exception:
        tags = EntryTags()
    entry_id = entries.save_entry(
        transcript=message,
        ai_reply=reply,
        user_id=user_id,
        session_id=session_id,
        mood=tags.mood,
        wins=tags.wins,
        themes=tags.themes,
    )
    # Embed the entry so future conversations can recall it. A failure here
    # (no key, vector store down) must not lose the entry we just saved.
    try:
        recall.index_entry(entry_id, message, user_id=user_id)
    except Exception:
        pass
    # Periodically re-condense the long-term profile from recent entries.
    try:
        profile.maybe_refresh(user_id)
    except Exception:
        pass
    return result
