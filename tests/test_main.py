"""App-level route tests."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app import entries
from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_entries_endpoint_returns_todays_entries(sqlite_db):
    entries.save_entry("felt good today", "love that", mood="happy")
    today = datetime.now(timezone.utc).date().isoformat()

    resp = client.get(f"/entries?day={today}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["day"] == today
    assert len(body["entries"]) == 1
    assert body["entries"][0]["mood"] == "happy"


def test_wins_endpoint_lists_only_wins(sqlite_db):
    entries.save_entry("just a normal day", "ok", wins=None)
    entries.save_entry("shipped the feature", "huge!", wins="shipped feature")

    resp = client.get("/wins")
    assert resp.status_code == 200
    wins = resp.json()["wins"]
    assert len(wins) == 1
    assert wins[0]["wins"] == "shipped feature"
