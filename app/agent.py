"""Agentic loop: Claude decides which tools to call, and how many times.

This is the Agent version of the RAG pipeline. Instead of a fixed
"retrieve then answer" flow, the model chooses when to search documents,
when to look up an order, and when it has enough to answer.
"""
from app import config, llm, rag, sessions, tools

SYSTEM_PROMPT = (
    "You are a customer-support agent. Use the search_documents tool for "
    "questions about plans, pricing, returns, or warranty, and the "
    "lookup_order tool for order status. Answer using only what the tools "
    "return; if you cannot find the answer, say you don't know. Be concise."
)

MAX_STEPS = 6  # safety cap so a misbehaving loop can't run forever


def run(question: str, session_id: str | None = None) -> dict:
    """Answer a question, letting Claude call tools as needed.

    If session_id is given, prior turns are loaded and this exchange is saved,
    so follow-up questions ("when does it arrive?") keep their context.

    Returns {"answer", "tools_used", "sources", "session_id"}.
    """
    # Start from any saved history for this session.
    messages = list(sessions.get(session_id)) if session_id else []
    messages.append({"role": "user", "content": question})
    tools_used: list[str] = []
    sources: list[str] = []  # document filenames the agent searched, deduped

    for _ in range(MAX_STEPS):
        response = llm.client.messages.create(
            model=config.CHAT_MODEL,
            max_tokens=config.MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=tools.TOOLS,
            messages=messages,
        )
        # Record the assistant turn either way, so history stays complete.
        messages.append({"role": "assistant", "content": response.content})

        # Claude didn't ask for a tool, so it has enough to answer now — done.
        if response.stop_reason != "tool_use":
            answer = "".join(b.text for b in response.content if b.type == "text")
            if session_id:
                sessions.save(session_id, messages)
            return {
                "answer": answer,
                "tools_used": tools_used,
                "sources": sources,
                "session_id": session_id,
            }

        # Claude asked for one or more tools: run them, feed results back.
        results = []
        for block in response.content:
            if block.type == "tool_use":
                tools_used.append(block.name)
                # Track which documents a search touched, for the UI.
                if block.name == "search_documents":
                    for hit in rag.retrieve(block.input.get("query", "")):
                        if hit["source"] not in sources:
                            sources.append(hit["source"])
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tools.dispatch(block.name, block.input),
                    }
                )
        messages.append({"role": "user", "content": results})

    return {
        "answer": "Stopped after too many steps.",
        "tools_used": tools_used,
        "sources": sources,
        "session_id": session_id,
    }
