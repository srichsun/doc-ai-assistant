"""Journal entry storage tests, run against an in-memory SQLite database
so they need no Postgres server and spend no time on I/O.

The sqlite_db fixture lives in conftest.py."""
from datetime import datetime, timezone

from app.services import entries

UID = "u1"


def test_save_and_read_back(sqlite_db):
    new_id = entries.save_entry("I ran 5k today", "That's a real win!", UID)
    assert isinstance(new_id, int)

    todays = entries.entries_on(datetime.now(timezone.utc).date(), UID)
    assert len(todays) == 1
    assert todays[0].transcript == "I ran 5k today"
    assert todays[0].ai_reply == "That's a real win!"


def test_entries_are_scoped_to_one_person(sqlite_db):
    entries.save_entry("mine", "reply", UID)
    entries.save_entry("theirs", "reply", "u2")

    assert [e.transcript for e in entries.entries_on(
        datetime.now(timezone.utc).date(), UID
    )] == ["mine"]
    assert [e.transcript for e in entries.entries_on(
        datetime.now(timezone.utc).date(), "u2"
    )] == ["theirs"]
