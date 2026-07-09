"""Route tests. The Anthropic call is mocked so no API key is needed."""
from fastapi.testclient import TestClient

from app import llm
from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_chat_returns_answer(monkeypatch):
    # Replace the real LLM call with a stub.
    monkeypatch.setattr(llm, "generate", lambda prompt, system=None: "stub answer")

    resp = client.post("/chat", json={"question": "hello?"})
    assert resp.status_code == 200
    assert resp.json() == {"answer": "stub answer"}
