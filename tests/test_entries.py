"""Journal entry storage tests, run against an in-memory SQLite database
so they need no Postgres server and spend no time on I/O.

The sqlite_db fixture lives in conftest.py."""
from datetime import timedelta

import pytest

from app.core import clock
from app.services import entries

UID = "u1"


def test_save_and_read_back(sqlite_db):
    entries.save_today("I ran 5k today", UID, energy=8)

    today = entries.today_entry(UID)
    assert today.content == "I ran 5k today"
    assert today.energy == 8
    assert today.entry_date == clock.today()


def test_a_second_save_rewrites_the_same_day(sqlite_db):
    first = entries.save_today("draft", UID)
    second = entries.save_today("what I actually meant", UID)

    assert second.id == first.id
    assert entries.count_entries(UID) == 1
    assert entries.today_entry(UID).content == "what I actually meant"


def test_writing_as_many_times_as_the_day_needs(sqlite_db):
    """A day gets written in passes. Charging for that would punish keeping up
    with it, and storing text costs nothing."""
    for i in range(entries.ANALYSIS_LIMIT + 5):
        entries.save_today(f"pass {i}", UID)

    assert entries.today_entry(UID).content == f"pass {entries.ANALYSIS_LIMIT + 4}"
    assert entries.today_entry(UID).analysis_count == 0


def test_running_out_of_analyses(sqlite_db):
    entry = entries.save_today("today", UID)
    for _ in range(entries.ANALYSIS_LIMIT):
        entries.spend_analysis(entry.id)

    with pytest.raises(entries.AnalysisLimitReached):
        entries.spend_analysis(entry.id)


def test_writing_again_after_the_analyses_are_gone(sqlite_db):
    """Out of analyses is not out of journal — the day can still be added to."""
    entry = entries.save_today("today", UID)
    for _ in range(entries.ANALYSIS_LIMIT):
        entries.spend_analysis(entry.id)

    entries.save_today("one more thought", UID)
    assert entries.today_entry(UID).content == "one more thought"


def test_energy_survives_an_edit_that_does_not_set_it(sqlite_db):
    entries.save_today("draft", UID, energy=7)
    entries.save_today("rewritten", UID)

    assert entries.today_entry(UID).energy == 7


def test_entries_are_scoped_to_one_person(sqlite_db):
    entries.save_today("mine", UID)
    entries.save_today("theirs", "u2")

    assert entries.today_entry(UID).content == "mine"
    assert entries.today_entry("u2").content == "theirs"


def test_a_range_leaves_out_days_nobody_wrote(sqlite_db):
    entries.save_today("only today", UID)
    today = clock.today()

    rows = entries.entries_between(today - timedelta(days=6), today, UID)
    assert [r.entry_date for r in rows] == [today]


def test_marking_a_day_analysed(sqlite_db):
    entry = entries.save_today("today", UID)
    assert entries.today_entry(UID).analyzed_at is None

    entries.mark_analyzed(entry.id)
    assert entries.today_entry(UID).analyzed_at is not None
