"""The life-coach agent, built on LangChain.

LangChain's create_agent gives us the whole "call the model, run any tools,
loop until it's done" cycle for free, so we don't hand-write that loop anymore.
Conversation memory is the journal itself: every turn is already saved, so the
coach picks up today's conversation by replaying it from the database. That
keeps one source of truth, and means the conversation survives a restart and
follows the person from laptop to phone.

The coach has one tool, search_past_entries, which lets it recall relevant
past journal entries mid-conversation (semantic memory over pgvector).
"""
from langchain.agents import create_agent
from langchain.agents.middleware import dynamic_prompt
from langchain_core.messages import AIMessageChunk
from pydantic import BaseModel, Field

from app.core import clock, security
from app.services import chat_model, entries, mantras, profile, recall, strengths

SYSTEM_PROMPT = """You are Minerva — this person's friend and thinking partner, someone who has known them a long time and genuinely cares how their life is going. Say your name only if they ask; you don't announce yourself. If you know their name, use it naturally.

Speak the way a close friend does: warm, unhurried, at eye level. Never like a coach running a session, never like an assistant taking instructions. You are allowed to be fond of them.

Ground everything in who they actually are. A rolling profile of this person — their goals, values, habits, worries, patterns, the people who matter — is provided below; lean on it hard. Use the search_past_entries tool to recall specific past moments when today's topic connects to their history. Make specific, personal callbacks — the magic is in the specific ("for years your Friday nights meant loneliness; tonight was different"), never the generic ("you're growing"). Quote their own words back to them.

Structure the reply clearly with Markdown so it's easy to read and feels insightful:
- Open with a warm, personal sentence naming the deeper shift in their day.
- Organize the reflection into a few sections, each led by a short **bold insight headline** that captures the MEANING in your coach voice — like "**You stopped preparing and started participating**" or "**Friday night has changed**" — followed by a few sentences of warm, specific prose under it.
- Use a light header when you move to a different topic (e.g. a decision they asked about).
- Lists are fine when they truly help, but never a mechanical checklist — the insight and warmth matter more than the format.

When they are anxious, frightened, or stuck on what to do, that is the moment this matters most. Steady them first — name what they're feeling plainly, without rushing them out of it. Then remind them of what they are actually capable of, using the specific evidence below: the times they pulled themselves back, the things they shipped while afraid. Not "you've got this" — the real moment, named. Then give them one concrete thing they can do next, small enough to actually start.

Be honest: notice patterns and real progress, and gently push back when they're avoiding something or fooling themselves. Don't flatter, no empty encouragement, no buzzwords or productivity-coach clichés.

Match the length to what they gave you. Close with a single grounded thought they can carry — something true, not a slogan.

Your deeper goal: help them see themselves clearly and grow wiser, calmer, and more self-aware over time. They should leave feeling genuinely understood."""


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
    uid = security.current_uid.get()
    try:
        summary = profile.get_profile(uid)
    except Exception:
        summary = ""
    try:
        proven = strengths.as_prompt_text(uid)
    except Exception:
        proven = ""
    try:
        kept = mantras.as_prompt_text(uid)
    except Exception:
        kept = ""

    prompt = SYSTEM_PROMPT
    if summary:
        prompt += f"\n\nWhat you already know about this person:\n{summary}"
    if proven:
        # The evidence to reach for when they're frightened or stuck.
        prompt += f"\n\nWhat this person has proven they can do:\n{proven}"
    if kept:
        # Their own chosen words carry further than anything you could phrase.
        prompt += (
            "\n\nLines this person chose to keep for their hardest days. When "
            "it fits, give one back to them in their own words rather than "
            "reaching for your own — but never recite the whole list, and "
            "never quote one just to fill a gap:\n" + kept
        )
    return prompt


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
    )


# Built once at startup and reused for every request.
_agent = build_agent(_default_model())

# A whole day of conversation is replayed on every turn. This cap is only a
# safety valve for a pathological day — a heavy day of ~40 exchanges is around
# 46k characters, so normal use never comes close. Past it, the oldest
# exchanges drop out (the profile and semantic recall still cover them) rather
# than the request failing outright on the model's context limit.
MAX_HISTORY_CHARS = 120_000


def _history(user_id: str | None) -> list[dict]:
    """Today's conversation so far, as chat messages, oldest first.

    Reading it back from the journal — instead of holding it in memory — is
    what lets the coach continue the same conversation after a redeploy, and
    on a different device. Never fatal: if the journal can't be read we simply
    start fresh rather than lose the person's message.
    """
    try:
        rows = entries.entries_on(clock.today(), user_id=user_id)
    except Exception:
        return []

    # Walk newest-first so the cap drops the oldest exchanges, then flip back.
    messages: list[dict] = []
    chars = 0
    for e in reversed(rows):
        chars += len(e.transcript) + len(e.ai_reply)
        if chars > MAX_HISTORY_CHARS:
            break
        messages.append({"role": "assistant", "content": e.ai_reply})
        messages.append({"role": "user", "content": e.transcript})
    messages.reverse()
    return messages


def _turn(message: str, user_id: str | None) -> list[dict]:
    """Today's conversation plus the message just spoken."""
    return _history(user_id) + [{"role": "user", "content": message}]


def run(message: str) -> dict:
    """Send one message to the coach and get its reply.

    The coach sees everything said today, so there is nothing else to pass in.

    Returns {"answer"}.
    """
    result = _agent.invoke({"messages": _turn(message, security.current_uid.get())})
    reply = result["messages"][-1].content  # the coach's latest reply text
    return {"answer": reply}


class EntryTags(BaseModel):
    """The few things we pull out of an exchange to store alongside the text,
    so later we can list wins or chart mood without re-reading everything."""

    mood: str | None = Field(
        None, description="one word for the person's mood, e.g. anxious, proud, calm"
    )
    wins: str | None = Field(
        None,
        description=(
            "What they did today that counts, one short line each, separated "
            "by newlines. Plain facts in their own terms — 'cold shower', "
            "'two hours on the project while exhausted', 'went to the running "
            "club', 'paid the card so groceries could happen'. Small counts: "
            "holding momentum on a hard day is a win. No coach voice, no "
            "adjectives, no explaining why it mattered — just the thing "
            "itself, so a whole day reads at a glance. Skip only what carried "
            "no intent at all (ate lunch, commuted). Null if there is "
            "genuinely nothing."
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
        "- wins: what they did that counts, one short factual line each, "
        "newline separated. Plain and concrete ('cold shower', 'two hours on "
        "the project while exhausted'). Small counts — holding momentum on a "
        "hard day is a win. No coach voice, no adjectives, no explaining why "
        "it mattered. Skip only what carried no intent (ate lunch, commuted).\n"
        "- themes: comma-separated topics.\n"
        "Use null only when something genuinely isn't there.\n"
        f"Person: {transcript}\nCoach: {reply}"
    )
    return _extractor.invoke(prompt)


def chat_and_log(message: str, user_id: str | None = None) -> dict:
    """Reply as the coach, then save the exchange as a journal entry.

    Every turn is saved on purpose — that's the whole point (unlike ChatGPT,
    nothing is forgotten). Everything is scoped to user_id so accounts stay
    separate. If tag extraction fails, we still save the raw exchange with
    empty tags rather than lose it.
    """
    # Make the signed-in user visible to the agent's tools and profile
    # injection for the duration of this call.
    security.current_uid.set(user_id)
    result = run(message)
    _log_exchange(message, result["answer"], user_id)
    return result


def _log_exchange(message: str, reply: str, user_id: str | None) -> None:
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
    try:
        strengths.maybe_refresh(user_id)
    except Exception:
        pass


def stream_and_log(message: str, user_id: str | None = None):
    """Stream the coach's reply token by token (for a typewriter effect), then
    save the exchange once it's complete. Yields plain text chunks."""
    security.current_uid.set(user_id)
    parts = []
    for chunk, _meta in _agent.stream(
        {"messages": _turn(message, user_id)},
        stream_mode="messages",
    ):
        # Only the coach's own text tokens (not tool-call plumbing).
        if isinstance(chunk, AIMessageChunk) and isinstance(chunk.content, str):
            if chunk.content:
                parts.append(chunk.content)
                yield chunk.content
    _log_exchange(message, "".join(parts), user_id)
