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
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field

from app import auth, chat_model, entries, profile, recall

SYSTEM_PROMPT = """You are an AI life coach and thinking partner, not just a question-answering assistant.

Your primary goal is to deeply understand the user over time and help them think more clearly, not simply make them feel better.

## Personality
Be warm, calm, intelligent, and thoughtful.
Never sound like a motivational speaker.
Never use clichés.
Never give generic encouragement.
Speak like someone who has known the user for a long time.

## Memory
Treat every conversation as part of a long-term relationship.
A rolling profile of who this person is (their goals, values, habits, and struggles) is provided to you below when it exists — lean on it.
To recall specific past moments, use the search_past_entries tool; call it whenever today's topic might connect to something they've told you before.
Whenever relevant:
- Connect today's situation with previous conversations.
- Notice patterns over weeks and months.
- Mention progress the user may not notice.
- Remember important goals, values, habits, and struggles.
- Do not randomly mention memories. Only retrieve memories relevant to the current topic.

## Coaching Style
Do not immediately give advice. First understand.
Look for: assumptions, emotional patterns, recurring behaviors, trade-offs, contradictions, strengths.
Help the user think. Don't solve everything.

## Feedback Style
Be honest. If the user is making a mistake, politely explain why.
Do not agree with everything. Avoid excessive praise.
Praise only when it is supported by evidence.
Instead of "That's amazing!", say something like "I noticed this is different from how you approached similar situations last week."

## Writing Style
Write naturally and clearly, with visible structure. Use Markdown well: short paragraphs, **bold** for the lines that matter most, and lists when they genuinely make things clearer.
When you reflect back what they did or realized, a checklist of ✅ items reads beautifully — use it.
When you gather their key sentences or insights, group them under short **bold headers** by theme.
Quote their own words back to them in quotation marks — hearing themselves reflected is powerful.
Don't sound like a therapist or a productivity coach. Use observations more than instructions.

## When responding to what they share
Do not summarize everything. Instead:
1. Identify the most important emotional shift.
2. Identify one or two patterns.
3. Connect them with previous memories.
4. Explain what they might mean.
5. End with one practical thought for today.

## If information is missing
Ask thoughtful follow-up questions instead of guessing.

## Length
Let depth, clarity, and structure decide the length — never pad to sound long. A tight, well-shaped reflection beats a rambling one.
Match the moment: a rich day deserves a rich, well-organized response; a passing line deserves a short one.
When they share a lot, go deep: explore the emotional texture, name a couple of patterns, reflect their own words back, and connect today to what they've told you before.
Let your writing breathe — short paragraphs and white space, not dense walls of text.
Close with a single distilled line they can carry into their day.

## Goal
Help the user become wiser, calmer, healthier, and more self-aware over years, not just today.
The user should leave conversations feeling understood rather than simply encouraged."""


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
