"""App-level route tests.

Every data route now requires a signed-in user. We override the auth
dependency with a fixed test uid instead of verifying a real Firebase token,
and scope the entries we create to that same uid.
"""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core import db
from app.core import security as auth
from app.models import Fact
from app.services import entries, strengths, voice
from app.main import app

client = TestClient(app)

TEST_UID = "u-test"
# Pretend the request is signed in as TEST_UID for all tests by default.
app.dependency_overrides[auth.current_user_uid] = lambda: TEST_UID


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_protected_routes_require_auth():
    # Drop the override so the real gate runs; no token -> 401.
    app.dependency_overrides.pop(auth.current_user_uid, None)
    try:
        assert client.post("/agent", json={"question": "hi"}).status_code == 401
        # /speak costs money per character — it must be locked down too.
        assert client.post("/speak", json={"text": "hi"}).status_code == 401
    finally:
        app.dependency_overrides[auth.current_user_uid] = lambda: TEST_UID


def test_entries_endpoint_returns_todays_entries(sqlite_db):
    entries.save_entry("felt good today", "love that", user_id=TEST_UID)
    today = datetime.now(timezone.utc).date().isoformat()

    resp = client.get(f"/entries?day={today}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["day"] == today
    assert len(body["entries"]) == 1
    assert body["entries"][0]["transcript"] == "felt good today"


def test_entries_are_scoped_to_the_signed_in_user(sqlite_db):
    # Someone else's entry must not show up for TEST_UID.
    entries.save_entry("their private day", "ok", user_id="someone-else")
    today = datetime.now(timezone.utc).date().isoformat()

    resp = client.get(f"/entries?day={today}")
    assert resp.json()["entries"] == []


def test_transcribe_returns_whisper_text(monkeypatch):
    # No real OpenAI call: fake the transcription.
    monkeypatch.setattr(voice, "transcribe", lambda data, name: "I feel tired")
    resp = client.post(
        "/transcribe",
        files={"audio": ("clip.webm", b"fake-audio-bytes", "audio/webm")},
    )
    assert resp.status_code == 200
    assert resp.json() == {"text": "I feel tired"}


def test_speak_returns_audio(monkeypatch):
    monkeypatch.setattr(voice, "speak", lambda text, voice=None: b"fake-mp3")
    resp = client.post("/speak", json={"text": "you did great"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
    assert resp.content == b"fake-mp3"


def _add_win_fact(user_id, text):
    with db.get_session() as s:
        s.add(Fact(user_id=user_id, entry_id=1, category="wins", text=text))
        s.commit()


def test_wins_endpoint_lists_win_facts(sqlite_db):
    _add_win_fact(TEST_UID, "cold shower")
    _add_win_fact("someone-else", "not mine")  # another user's win is hidden

    resp = client.get("/wins")
    assert resp.status_code == 200
    wins = resp.json()["wins"]
    assert len(wins) == 1
    assert wins[0]["wins"] == "cold shower"
    assert "created_at" in wins[0]


def test_strengths_endpoint_returns_the_passage(sqlite_db, monkeypatch):
    monkeypatch.setattr(strengths, "get_strengths", lambda uid: "You keep going.")

    resp = client.get("/strengths")
    assert resp.status_code == 200
    assert resp.json()["strengths"] == "You keep going."


def test_strengths_endpoint_is_empty_before_one_is_written(sqlite_db):
    entries.save_entry("a normal day", "ok", user_id=TEST_UID)

    resp = client.get("/strengths")
    assert resp.status_code == 200
    assert resp.json()["strengths"] == ""
