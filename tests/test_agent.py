"""Agent-loop tests with a fake Anthropic client (no API key, no tokens spent)."""
from types import SimpleNamespace

from app import agent, llm, rag, tools


def _text(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use(id, name, input):
    return SimpleNamespace(type="tool_use", id=id, name=name, input=input)


def _reply(content, stop_reason):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


def test_dispatch_lookup_order():
    assert "iPhone" in tools.dispatch("lookup_order", {"order_id": "1001"})
    assert "No order" in tools.dispatch("lookup_order", {"order_id": "9999"})


def test_dispatch_unknown_tool():
    assert tools.dispatch("nope", {}) == "Unknown tool: nope"


def test_search_documents_uses_retrieval(monkeypatch):
    monkeypatch.setattr(rag, "retrieve", lambda q: [{"source": "d.md", "text": "hi"}])
    assert tools.search_documents("q") == "[d.md] hi"


def test_agent_answers_without_tools(monkeypatch):
    # Model replies directly, no tool call.
    monkeypatch.setattr(
        llm.client.messages,
        "create",
        lambda **kw: _reply([_text("direct answer")], "end_turn"),
    )
    result = agent.run("hi")
    assert result == {"answer": "direct answer", "tools_used": [], "session_id": None}


def test_agent_remembers_history_across_turns(monkeypatch):
    seen_messages = []

    def fake_create(**kw):
        seen_messages.append(kw["messages"])
        return _reply([_text("ok")], "end_turn")

    monkeypatch.setattr(llm.client.messages, "create", fake_create)

    agent.run("first question", session_id="s-mem")
    agent.run("second question", session_id="s-mem")

    # The second turn's request must include the first question in its history.
    second_turn = seen_messages[-1]
    texts = [m["content"] for m in second_turn if isinstance(m["content"], str)]
    assert "first question" in texts
    assert "second question" in texts


def test_agent_calls_a_tool_then_answers(monkeypatch):
    # First call asks for a tool; second call returns the final answer.
    replies = iter(
        [
            _reply([_tool_use("t1", "lookup_order", {"order_id": "1001"})], "tool_use"),
            _reply([_text("your order shipped")], "end_turn"),
        ]
    )
    monkeypatch.setattr(llm.client.messages, "create", lambda **kw: next(replies))

    result = agent.run("where is order 1001?")
    assert result["answer"] == "your order shipped"
    assert result["tools_used"] == ["lookup_order"]
