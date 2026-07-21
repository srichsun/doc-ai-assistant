"""Semantic-recall tests.

PGVector needs a real Postgres with the vector extension, which we can't run
here, so we mock the store. These tests check the glue: that we call the store
the way we mean to, and format its results for the coach.
"""
from app.services import recall


class _Runtime:
    """Stands in for the ToolRuntime LangChain injects when the agent calls a
    tool; only the context — the caller's uid — is ever read."""

    def __init__(self, user_id):
        self.context = user_id


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


def test_index_fact_adds_text_keyed_by_row_id(monkeypatch):
    store = _FakeStore()
    monkeypatch.setattr(recall, "_facts_store", lambda: store)

    recall.index_fact(
        42, "still went for a run while exhausted", user_id="u9",
        category="wins",
    )

    assert store.added == [
        (
            ["still went for a run while exhausted"],
            [{"fact_id": 42, "user_id": "u9", "category": "wins"}],
            ["42"],
        )
    ]


def test_recall_filters_by_user(monkeypatch):
    store = _FakeStore(docs=[_Doc("first"), _Doc("second")])
    monkeypatch.setattr(recall, "_facts_store", lambda: store)

    hits = recall.recall("interview nerves", user_id="u9", k=2)

    assert hits == ["first", "second"]
    # With no categories, the query is scoped to the user only.
    assert store.last == ("interview nerves", 2, {"user_id": "u9"})


def test_recall_narrows_to_categories(monkeypatch):
    store = _FakeStore(docs=[_Doc("ran anyway")])
    monkeypatch.setattr(recall, "_facts_store", lambda: store)

    hits = recall.recall(
        "how do I cope", user_id="u9",
        categories=["health & habits", "patterns"], k=5,
    )

    assert hits == ["ran anyway"]
    # Category filter rides alongside the user filter (implicit AND).
    assert store.last == (
        "how do I cope",
        5,
        {"user_id": "u9", "category": {"$in": ["health & habits", "patterns"]}},
    )


def test_search_past_entries_tool_uses_the_runs_context(monkeypatch):
    """The tool scopes to whoever LangChain says is running, never a global."""
    seen = {}
    monkeypatch.setattr(
        recall,
        "recall",
        lambda q, user_id=None, categories=None, k=recall.TOP_K: seen.update(
            uid=user_id, categories=categories
        )
        or ["a win", "a worry"],
    )
    out = recall.search_past_entries.func("how am I doing", _Runtime("u-caller"))

    assert out == ["a win", "a worry"]
    assert seen["uid"] == "u-caller"


def test_search_past_entries_passes_categories_through(monkeypatch):
    """The model can narrow the search; the tool forwards its choice."""
    seen = {}
    monkeypatch.setattr(
        recall,
        "recall",
        lambda q, user_id=None, categories=None, k=recall.TOP_K: seen.update(
            categories=categories
        )
        or ["x"],
    )
    recall.search_past_entries.func(
        "coping", _Runtime("u-caller"), categories=["patterns"]
    )

    assert seen["categories"] == ["patterns"]


def test_the_model_sees_query_and_categories_but_not_runtime():
    """`runtime` is injected by LangChain, so it must stay out of the schema the
    model is shown; query and categories are the model's to fill."""
    assert list(recall.search_past_entries.args) == ["query", "categories"]


def test_search_past_entries_tool_handles_no_history(monkeypatch):
    monkeypatch.setattr(
        recall,
        "recall",
        lambda q, user_id=None, categories=None, k=recall.TOP_K: [],
    )

    out = recall.search_past_entries.func("anything", _Runtime("u-caller"))

    assert out == "No related past facts found."
