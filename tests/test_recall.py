"""Semantic-recall tests.

PGVector needs a real Postgres with the vector extension, which we can't run
here, so we mock the store. These tests check the glue: that we call the store
the way we mean to, and format its results for the coach.
"""
from app import recall


class _FakeStore:
    """Stands in for the PGVector store, recording calls and returning canned
    documents from similarity_search."""

    def __init__(self, docs=None):
        self.added = []
        self._docs = docs or []

    def add_texts(self, texts, metadatas=None, ids=None):
        self.added.append((texts, metadatas, ids))

    def similarity_search(self, query, k, filter=None):
        self.last = (query, k, filter)
        return self._docs[:k]


class _Doc:
    def __init__(self, content):
        self.page_content = content


def test_index_entry_adds_text_keyed_by_row_id(monkeypatch):
    store = _FakeStore()
    monkeypatch.setattr(recall, "_store", lambda: store)

    recall.index_entry(42, "I felt anxious before the interview", user_id="u9")

    assert store.added == [
        (
            ["I felt anxious before the interview"],
            [{"entry_id": 42, "user_id": "u9"}],
            ["42"],
        )
    ]


def test_recall_filters_by_user(monkeypatch):
    store = _FakeStore(docs=[_Doc("first"), _Doc("second")])
    monkeypatch.setattr(recall, "_store", lambda: store)

    hits = recall.recall("interview nerves", user_id="u9", k=2)

    assert hits == ["first", "second"]
    # The query is scoped to the user via a metadata filter.
    assert store.last == ("interview nerves", 2, {"user_id": "u9"})


def test_search_past_entries_tool_uses_current_user(monkeypatch):
    from app import auth

    seen = {}
    monkeypatch.setattr(
        recall,
        "recall",
        lambda q, user_id=None, k=recall.TOP_K: seen.update(uid=user_id)
        or ["a win", "a worry"],
    )
    token = auth.current_uid.set("u-caller")
    try:
        out = recall.search_past_entries.invoke({"query": "how am I doing"})
    finally:
        auth.current_uid.reset(token)

    assert out == "- a win\n\n- a worry"
    assert seen["uid"] == "u-caller"


def test_search_past_entries_tool_handles_no_history(monkeypatch):
    monkeypatch.setattr(
        recall, "recall", lambda q, user_id=None, k=recall.TOP_K: []
    )

    out = recall.search_past_entries.invoke({"query": "anything"})

    assert out == "No related past entries found."
