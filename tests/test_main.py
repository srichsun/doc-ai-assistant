"""App-level route tests.

Every data route now requires a signed-in user. We override the auth
dependency with a fixed test uid instead of verifying a real Firebase token,
and scope the entries we create to that same uid.
"""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core import security as auth
from app.services import entries, strengths, voice
from app.main import app

client = TestClient(app)

TEST_UID = "u-test"
# Pretend the request is signed in as TEST_UID for all tests by default.
app.dependency_overrides[auth.current_user] = lambda: TEST_UID


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_protected_routes_require_auth():
    # Drop the override so the real gate runs; no token -> 401.
    app.dependency_overrides.pop(auth.current_user, None)
    try:
        assert client.post("/agent", json={"question": "hi"}).status_code == 401
        # /speak costs money per character — it must be locked down too.
        assert client.post("/speak", json={"text": "hi"}).status_code == 401
    finally:
        app.dependency_overrides[auth.current_user] = lambda: TEST_UID


def test_entries_endpoint_returns_todays_entries(sqlite_db):
    entries.save_entry("felt good today", "love that", user_id=TEST_UID, mood="happy")
    today = datetime.now(timezone.utc).date().isoformat()

    resp = client.get(f"/entries?day={today}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["day"] == today
    assert len(body["entries"]) == 1
    assert body["entries"][0]["mood"] == "happy"


def test_entries_are_scoped_to_the_signed_in_user(sqlite_db):
    # Someone else's entry must not show up for TEST_UID.
    entries.save_entry("their private day", "ok", user_id="someone-else", mood="sad")
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


def test_strengths_endpoint_returns_the_saved_strengths(sqlite_db, monkeypatch):
    monkeypatch.setattr(
        strengths,
        "get_strengths",
        lambda uid: [{"title": "You keep going", "evidence": ["shipped it tired"]}],
    )

    resp = client.get("/strengths")
    assert resp.status_code == 200
    assert resp.json()["strengths"] == [
        {"title": "You keep going", "evidence": ["shipped it tired"]}
    ]


def test_strengths_endpoint_is_empty_before_any_have_formed(sqlite_db):
    entries.save_entry("a normal day", "ok", user_id=TEST_UID, wins=None)

    resp = client.get("/strengths")
    assert resp.status_code == 200
    assert resp.json()["strengths"] == []
