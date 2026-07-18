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
from langchain_core.messages import AIMessageChunk
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field

from app import auth, chat_model, entries, profile, recall

SYSTEM_PROMPT = """You are this person's personal coach and thinking partner — someone who has known them a long time and genuinely cares how their life is going.

Write like a wise, warm friend who has been paying close attention. Talk TO them, not about them. If you know their name, use it naturally.

Ground everything in who they actually are. A rolling profile of this person — their goals, values, habits, worries, patterns, the people who matter — is provided below; lean on it hard. Make specific, personal callbacks: connect what they say today to their history, their recurring struggles, the story they've been telling themselves. When it helps, use the search_past_entries tool to recall a specific past moment. The magic is in the specific, not the general — "for years your Friday nights meant loneliness; tonight was different" lands; "you're growing" does not.

Reflect their own words back to them — quoting a line they actually said is powerful.

Notice patterns and shifts they might not see themselves, and name the emotional undercurrent honestly. Point out progress, but only what's real — don't flatter, don't hand out empty encouragement, and gently push back when they're avoiding something or fooling themselves.

Write in natural, flowing prose — like a thoughtful letter, not a report. Let it breathe with short paragraphs. Do NOT format it as a structured document: no bullet checklists, no ✅, no bold section headers, no rigid step-by-step template. An occasional short list is fine only when it genuinely helps; prose is the default.

Match the length to what they gave you — a full, rich day deserves a rich reflection; a passing line deserves a short, warm reply. Never pad.

Close with a single grounded thought they can carry into their day — not a slogan, something true.

Your deeper goal: help them see themselves clearly and grow wiser, calmer, and more self-aware over time. They should leave feeling genuinely understood, not just cheered up."""


def _default_model():
    """The real chat model used in production — ChatGPT or Claude per config."""
    return chat_model.build_chat_model()


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


def _thread_id(session_id: str | None) -> str:
    """Conversation-memory key: user id + session id.

    Scoping by user matters — the session id lives in browser localStorage, so
    two Google accounts on the same machine would otherwise share one memory.
    No session id means a one-off turn (throwaway id, nothing bleeds).
    """
    if not session_id:
        return f"anon-{uuid.uuid4()}"
    return f"{auth.current_uid.get() or 'anon'}:{session_id}"


def run(message: str, session_id: str | None = None) -> dict:
    """Send one message to the coach and get its reply.

    Pass the same session_id across turns to keep the conversation's memory.

    Returns {"answer", "session_id"}.
    """
    cfg = {"configurable": {"thread_id": _thread_id(session_id)}}
    result = _agent.invoke(
        {"messages": [{"role": "user", "content": message}]}, cfg
    )
    reply = result["messages"][-1].content  # the coach's latest reply text
    return {"answer": reply, "session_id": session_id}


class EntryTags(BaseModel):
    """The few things we pull out of an exchange to store alongside the text,
    so later we can list wins or chart mood without re-reading everything."""

    mood: str | None = Field(
        None, description="one word for the person's mood, e.g. anxious, proud, calm"
    )
    wins: str | None = Field(
        None,
        description=(
            "The 3-5 most MEANINGFUL wins of the day — not a chore log. For each, "
            "give two parts: a short wise insight naming the MEANING (coach voice, "
            "like a headline: 'You stopped preparing and started participating'), "
            "then the concrete detail behind it. Draw the insight from the wisest "
            "observations in the coach's reply; skip routine facts with no "
            "significance. Format each as '**[insight]**' then the detail on the next "
            "line. Null only if there is genuinely nothing meaningful."
        ),
    )
    themes: str | None = Field(
        None, description="comma-separated topics, e.g. work, health, family"
    )


# A small model call that only returns the structured tags above.
_extractor = _default_model().with_structured_output(EntryTags)


def extract_tags(transcript: str, reply: str) -> EntryTags:
    """Pull mood / wins / themes out of one exchange."""
    prompt = (
        "From this journaling exchange, extract:\n"
        "- mood: one word.\n"
        "- wins: the 3-5 most MEANINGFUL wins of the day (not a chore log). For each, "
        "a short wise insight naming the meaning (coach voice, like a headline), then "
        "the concrete detail. Draw the insight from the wisest lines in the coach's "
        "reply; skip routine facts. Format each as '**[insight]**' then the detail.\n"
        "- themes: comma-separated topics.\n"
        "Use null only when something genuinely isn't there.\n"
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
    _log_exchange(message, result["answer"], user_id, session_id)
    return result


def _log_exchange(
    message: str, reply: str, user_id: str | None, session_id: str | None
) -> None:
    """Save one exchange as a journal entry, then embed it and (occasionally)
    refresh the profile. Failures in the extras never lose the saved entry."""
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
    try:
        recall.index_entry(entry_id, message, user_id=user_id)
    except Exception:
        pass
    try:
        profile.maybe_refresh(user_id)
    except Exception:
        pass


def stream_and_log(
    message: str, user_id: str | None = None, session_id: str | None = None
):
    """Stream the coach's reply token by token (for a typewriter effect), then
    save the exchange once it's complete. Yields plain text chunks."""
    auth.current_uid.set(user_id)
    cfg = {"configurable": {"thread_id": _thread_id(session_id)}}
    parts = []
    for chunk, _meta in _agent.stream(
        {"messages": [{"role": "user", "content": message}]},
        cfg,
        stream_mode="messages",
    ):
        # Only the coach's own text tokens (not tool-call plumbing).
        if isinstance(chunk, AIMessageChunk) and isinstance(chunk.content, str):
            if chunk.content:
                parts.append(chunk.content)
                yield chunk.content
    _log_exchange(message, "".join(parts), user_id, session_id)
