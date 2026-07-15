"""Long-term profile tests.

The LLM condense step is mocked, so these run offline and check the wiring:
that we gather recent entries, save the condensed text, count what's folded in,
and only re-condense once enough new entries have accumulated.
"""
from app import entries, profile


def test_get_profile_empty_when_none(sqlite_db):
    assert profile.get_profile() == ""


def test_refresh_condenses_and_saves(sqlite_db, monkeypatch):
    entries.save_entry("I started running again", "great start")
    entries.save_entry("Nervous about the interview", "you'll do well")
    seen = {}
    monkeypatch.setattr(
        profile,
        "condense",
        lambda existing, recent: seen.update(existing=existing, recent=recent)
        or "- runs regularly\n- job hunting",
    )

    text = profile.refresh_profile()

    assert text == "- runs regularly\n- job hunting"
    assert profile.get_profile() == "- runs regularly\n- job hunting"
    # Both entries were handed to the condenser as raw material.
    assert "running" in seen["recent"] and "interview" in seen["recent"]
    assert seen["existing"] == ""


def test_refresh_carries_forward_existing_profile(sqlite_db, monkeypatch):
    entries.save_entry("first", "ok")
    monkeypatch.setattr(profile, "condense", lambda e, r: "v1")
    profile.refresh_profile()

    captured = {}
    monkeypatch.setattr(
        profile, "condense", lambda e, r: captured.update(existing=e) or "v2"
    )
    profile.refresh_profile()
    # The second condense sees the first profile as its starting point.
    assert captured["existing"] == "v1"


def test_maybe_refresh_waits_for_enough_entries(sqlite_db, monkeypatch):
    calls = []
    monkeypatch.setattr(profile, "refresh_profile", lambda key=profile.DEFAULT_KEY: calls.append(1))

    # Below the threshold: no refresh.
    for _ in range(profile.REFRESH_EVERY - 1):
        entries.save_entry("x", "y")
    profile.maybe_refresh()
    assert calls == []

    # One more crosses the threshold: refresh fires.
    entries.save_entry("x", "y")
    profile.maybe_refresh()
    assert calls == [1]
