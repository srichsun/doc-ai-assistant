"""Tests for atomic-fact extraction and the wins helper.

The extraction is an LLM call, so it's faked here — these check the glue: that
each fact is written to the facts table, each is handed to the vector index, and
the wins helper reads back only wins.
"""
from app.services import facts


class _FakeExtractor:
    """Stands in for the structured-output model, returning canned facts."""

    def __init__(self, result):
        self._result = result
        self.prompt = None

    def invoke(self, prompt):
        self.prompt = prompt
        return self._result


def _result(*pairs):
    """Build a _FactList from (category, text) pairs."""
    return facts._FactList(
        facts=[facts._Fact(category=c, text=t) for c, t in pairs]
    )


def test_extract_and_save_writes_every_fact_and_indexes_it(sqlite_db, monkeypatch):
    monkeypatch.setattr(
        facts,
        "_extractor",
        _FakeExtractor(
            _result(
                ("health & habits", "went for a run while exhausted"),
                ("work & career", "the project stalled"),
                ("wins", "ran even though tired"),
            )
        ),
    )
    indexed = []
    monkeypatch.setattr(
        facts.recall,
        "index_fact",
        lambda fid, text, user_id=None, category=None: indexed.append(
            (fid, text, user_id, category)
        ),
    )

    ids = facts.extract_and_save(7, "tired but ran", "proud of you", user_id="u1")

    assert len(ids) == 3
    # Every fact landed in the table, keyed to the entry and owner.
    rows = facts.existing_fact_entry_ids("u1")
    assert rows == {7}
    # Every fact was handed to the vector index with its category.
    assert [(t, u, c) for (_id, t, u, c) in indexed] == [
        ("went for a run while exhausted", "u1", "health & habits"),
        ("the project stalled", "u1", "work & career"),
        ("ran even though tired", "u1", "wins"),
    ]
    assert [fid for (fid, *_rest) in indexed] == ids


def test_extract_and_save_skips_blank_facts(sqlite_db, monkeypatch):
    monkeypatch.setattr(
        facts, "_extractor", _FakeExtractor(_result(("wins", "  "), ("wins", "x")))
    )
    monkeypatch.setattr(
        facts.recall, "index_fact", lambda *a, **k: None
    )

    ids = facts.extract_and_save(1, "t", "r", user_id="u1")

    assert len(ids) == 1


def test_recent_wins_returns_only_wins_newest_first(sqlite_db, monkeypatch):
    monkeypatch.setattr(facts.recall, "index_fact", lambda *a, **k: None)
    monkeypatch.setattr(
        facts,
        "_extractor",
        _FakeExtractor(
            _result(
                ("work & career", "shipped the feature"),
                ("wins", "cold shower"),
                ("wins", "finished the report"),
            )
        ),
    )

    facts.extract_and_save(3, "busy day", "nice", user_id="u1")

    wins = facts.recent_wins("u1")
    texts = [w.text for w in wins]
    # Only the wins come back, and never the work fact.
    assert set(texts) == {"cold shower", "finished the report"}
    assert "shipped the feature" not in texts


def test_recent_wins_is_scoped_to_one_person(sqlite_db, monkeypatch):
    monkeypatch.setattr(facts.recall, "index_fact", lambda *a, **k: None)
    monkeypatch.setattr(
        facts, "_extractor", _FakeExtractor(_result(("wins", "mine")))
    )
    facts.extract_and_save(1, "a", "b", user_id="u1")
    monkeypatch.setattr(
        facts, "_extractor", _FakeExtractor(_result(("wins", "theirs")))
    )
    facts.extract_and_save(2, "a", "b", user_id="u2")

    assert [w.text for w in facts.recent_wins("u1")] == ["mine"]
    assert [w.text for w in facts.recent_wins("u2")] == ["theirs"]
