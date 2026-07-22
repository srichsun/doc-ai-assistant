"""App-level route tests.

Every data route now requires a signed-in user. We override the auth
dependency with a fixed test uid instead of verifying a real Firebase token,
and scope the entries we create to that same uid.
"""
from fastapi.testclient import TestClient

from app.core import clock
from app.core import security as auth
from app.services import agent, entries, questions, voice
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
        assert client.post("/agent/stream", json={"question": "hi"}).status_code == 401
        # /speak costs money per character — it must be locked down too.
        assert client.post("/speak", json={"text": "hi"}).status_code == 401
    finally:
        app.dependency_overrides[auth.current_user_uid] = lambda: TEST_UID


def test_a_blank_turn_is_rejected_before_it_costs_anything(sqlite_db):
    """A silent recording or a stray Enter must not reach the model, and must
    not leave an empty journal entry that no recall could ever use."""
    for blank in ("", "   ", "\n\t"):
        resp = client.post("/agent/stream", json={"question": blank})
        assert resp.status_code == 422, blank

    # Nothing was written.
    assert questions.questions_on(clock.today(), user_id=TEST_UID) == []


def test_surrounding_whitespace_is_stripped_from_what_is_stored(sqlite_db, monkeypatch):
    """What gets recorded is what was asked, not the padding around it."""
    asked = {}
    monkeypatch.setattr(
        agent,
        "stream_and_save",
        lambda message, user_id: iter([asked.setdefault("m", message) and ""]),
    )

    resp = client.post("/agent/stream", json={"question": "  I ran 5k today  "})

    assert resp.status_code == 200
    assert asked["m"] == "I ran 5k today"


def test_entries_endpoint_returns_the_recent_days(sqlite_db):
    entries.save_today("felt good today", TEST_UID, energy=8)

    resp = client.get("/entries?days=7")
    assert resp.status_code == 200
    body = resp.json()
    assert body["end"] == clock.today().isoformat()
    assert len(body["entries"]) == 1
    assert body["entries"][0]["content"] == "felt good today"
    assert body["entries"][0]["energy"] == 8
    assert body["entries"][0]["analyses_left"] == entries.ANALYSIS_LIMIT


def test_entries_are_scoped_to_the_signed_in_user(sqlite_db):
    # Someone else's entry must not show up for TEST_UID.
    entries.save_today("their private day", "someone-else")

    assert client.get("/entries?days=7").json()["entries"] == []


def test_a_day_nobody_wrote_is_a_404(sqlite_db):
    """Absent, not blank — the record screen draws a gap rather than a hole."""
    assert client.get("/entries/2020-01-01").status_code == 404


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
