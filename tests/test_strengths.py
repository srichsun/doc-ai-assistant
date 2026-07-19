"""Tests for the strengths layer.

The condense step is an LLM call, so it's faked here — these check the glue:
that we feed it the journal's wins, store what comes back, and degrade quietly
when there's nothing (or something broken) to show.
"""
import json

from app.core import db
from app.models import Profile
from app.services import entries, strengths


class _FakeCondenser:
    """Stands in for the structured-output model, recording its prompt."""

    def __init__(self, result):
        self._result = result
        self.prompt = None

    def invoke(self, prompt):
        self.prompt = prompt
        return self._result


def _result(*pairs):
    return strengths.StrengthList(
        strengths=[
            strengths.Strength(title=t, evidence=list(e)) for t, e in pairs
        ]
    )


def test_refresh_folds_wins_into_strengths(sqlite_db, monkeypatch):
    entries.save_entry("a", "b", user_id="u1", wins="**Reset the day**\nCold shower")
    entries.save_entry("c", "d", user_id="u1", wins="**Kept going**\nTwo hours tired")
    fake = _FakeCondenser(
        _result(("You pull yourself back", ("Cold shower", "Two hours tired")))
    )
    monkeypatch.setattr(strengths, "_condense_model", lambda: fake)

    items = strengths.refresh_strengths("u1")

    assert items == [
        {
            "title": "You pull yourself back",
            "evidence": ["Cold shower", "Two hours tired"],
        }
    ]
    # Both entries' wins were handed to the model to merge.
    assert "Cold shower" in fake.prompt and "Two hours tired" in fake.prompt
    # ...and the result is readable back.
    assert strengths.get_strengths("u1") == items


def test_refresh_is_a_noop_without_any_wins(sqlite_db, monkeypatch):
    """No journal yet means nothing to fold — and no wasted LLM call."""
    called = []
    monkeypatch.setattr(
        strengths, "_condense_model", lambda: called.append(1) or _FakeCondenser(None)
    )

    assert strengths.refresh_strengths("u1") == []
    assert called == []


def test_get_strengths_is_empty_for_a_new_person(sqlite_db):
    assert strengths.get_strengths("nobody") == []


def test_get_strengths_survives_a_corrupt_row(sqlite_db):
    """A half-written value must not take down the review screen."""
    with db.get_session() as s:
        s.add(Profile(key=strengths._key("u1"), content="{not json"))
        s.commit()

    assert strengths.get_strengths("u1") == []


def test_prompt_text_lists_each_strength_with_one_example(sqlite_db, monkeypatch):
    """What gets injected into the coach's prompt when someone is anxious."""
    with db.get_session() as s:
        s.add(
            Profile(
                key=strengths._key("u1"),
                content=json.dumps(
                    [{"title": "You keep going", "evidence": ["shipped it tired"]}]
                ),
            )
        )
        s.commit()

    assert (
        strengths.as_prompt_text("u1") == "- You keep going (e.g. shipped it tired)"
    )


def test_maybe_refresh_waits_for_enough_new_entries(sqlite_db, monkeypatch):
    refreshed = []
    monkeypatch.setattr(
        strengths, "refresh_strengths", lambda uid: refreshed.append(uid)
    )

    entries.save_entry("a", "b", user_id="u1", wins="one")
    strengths.maybe_refresh("u1")
    assert refreshed == []  # one entry is nowhere near the threshold

    for _ in range(strengths.REFRESH_EVERY):
        entries.save_entry("a", "b", user_id="u1", wins="more")
    strengths.maybe_refresh("u1")
    assert refreshed == ["u1"]
