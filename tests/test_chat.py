"""Route tests. The Anthropic call is mocked so no API key is needed."""
from fastapi.testclient import TestClient

from app import llm, rag
from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_chat_returns_answer_with_sources(monkeypatch):
    # Stub retrieval and the LLM call so the route runs without Chroma or an API key.
    monkeypatch.setattr(
        rag,
        "retrieve",
        lambda q: [
            {"source": "doc.md", "page": 1, "text": "ctx"},
            {"source": "doc.md", "page": 1, "text": "more"},  # duplicate source
        ],
    )
    monkeypatch.setattr(llm, "generate", lambda prompt, system=None: "stub answer")

    resp = client.post("/chat", json={"question": "hello?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "stub answer"
    # duplicate (doc.md, page 1) collapses to a single source
    assert body["sources"] == [{"source": "doc.md", "page": 1}]


def test_chat_without_matches_skips_llm(monkeypatch):
    monkeypatch.setattr(rag, "retrieve", lambda q: [])

    def _fail(*a, **k):
        raise AssertionError("LLM should not be called when nothing is retrieved")

    monkeypatch.setattr(llm, "generate", _fail)

    resp = client.post("/chat", json={"question": "hello?"})
    assert resp.status_code == 200
    assert resp.json()["sources"] == []
