"""Journal entry storage tests, run against an in-memory SQLite database
so they need no Postgres server and spend no time on I/O.

The sqlite_db fixture lives in conftest.py."""
from datetime import datetime, timezone

from app import entries


def test_save_and_read_back(sqlite_db):
    new_id = entries.save_entry(
        "I ran 5k today", "That's a real win!", mood="proud", wins="ran 5k"
    )
    assert isinstance(new_id, int)

    todays = entries.entries_on(datetime.now(timezone.utc).date())
    assert len(todays) == 1
    assert todays[0].transcript == "I ran 5k today"
    assert todays[0].mood == "proud"


def test_recent_wins_only_returns_entries_with_wins(sqlite_db):
    entries.save_entry("nothing much happened", "that's okay", wins=None)
    entries.save_entry("finished the report", "great job", wins="finished report")

    wins = entries.recent_wins()
    assert len(wins) == 1
    assert wins[0].wins == "finished report"
