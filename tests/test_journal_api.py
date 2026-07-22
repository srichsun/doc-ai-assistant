"""Journal route tests — writing today, analysing it, reading days back.

Fact extraction is an LLM call, so it's faked; what's checked here is the glue
and the boundaries: that only today is writable, that the allowance runs out,
and that analysing twice leaves one reading of the day rather than two.
"""
import pytest
from fastapi.testclient import TestClient

from app.core import clock
from app.core import security as auth
from app.main import app
from app.services import entries, facts

client = TestClient(app)

UID = "u-journal"


@pytest.fixture(autouse=True)
def signed_in_as_journal_user():
    """Sign every request in this module in as UID, and hand the override back
    afterwards. Set per test rather than at import: the overrides live on the
    one shared app, so a module-level assignment would depend on import order
    and quietly run these tests as another module's user."""
    previous = app.dependency_overrides.get(auth.current_user_uid)
    app.dependency_overrides[auth.current_user_uid] = lambda: UID
    yield
    if previous is None:
        app.dependency_overrides.pop(auth.current_user_uid, None)
    else:
        app.dependency_overrides[auth.current_user_uid] = previous


def _fake_extraction(monkeypatch, *pairs):
    """Make analysis return these (category, text) facts without a model call."""
    from app.services import facts as facts_mod

    result = facts_mod._FactList(
        facts=[facts_mod._Fact(category=c, text=t) for c, t in pairs]
    )
    monkeypatch.setattr(facts_mod, "_extractor", type("F", (), {
        "invoke": lambda self, prompt: result
    })())
    monkeypatch.setattr(facts_mod.recall, "index_fact", lambda *a, **k: None)
    monkeypatch.setattr(facts_mod.recall, "forget_facts", lambda *a, **k: None)


def test_writing_today(sqlite_db):
    resp = client.post("/entries", json={"content": "long day", "energy": 6})

    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == "long day"
    assert body["energy"] == 6
    assert body["date"] == clock.today().isoformat()
    assert body["edits_left"] == entries.EDIT_LIMIT
    assert body["analyzed"] is False


def test_a_blank_day_is_rejected(sqlite_db):
    """An empty entry would spend an edit and give the analysis nothing."""
    for blank in ("", "   ", "\n\t"):
        assert client.post("/entries", json={"content": blank}).status_code == 422
    assert entries.today_entry(UID) is None


def test_energy_outside_one_to_ten_is_rejected(sqlite_db):
    assert client.post("/entries", json={"content": "x", "energy": 0}).status_code == 422
    assert client.post("/entries", json={"content": "x", "energy": 11}).status_code == 422


def test_the_allowance_runs_out(sqlite_db):
    client.post("/entries", json={"content": "first"})
    for i in range(entries.EDIT_LIMIT):
        resp = client.post("/entries", json={"content": f"rewrite {i}"})
        assert resp.status_code == 200
        assert resp.json()["edits_left"] == entries.EDIT_LIMIT - (i + 1)

    spent = client.post("/entries", json={"content": "one more"})
    assert spent.status_code == 409


def test_analysis_extracts_the_days_facts(sqlite_db, monkeypatch):
    _fake_extraction(
        monkeypatch,
        ("wins", "went for a run while exhausted"),
        ("gratitude", "a friend read my CV"),
        ("patterns", "keeps going when tired"),
    )
    entry_id = client.post("/entries", json={"content": "tired but ran"}).json()["id"]

    body = client.post(f"/entries/{entry_id}/analyze").json()

    assert body["analyzed"] is True
    assert body["wins"] == ["went for a run while exhausted"]
    assert body["gratitude"] == ["a friend read my CV"]
    # Analysing costs the same as an edit.
    assert body["edits_left"] == entries.EDIT_LIMIT - 1


def test_re_analysing_replaces_rather_than_doubles(sqlite_db, monkeypatch):
    _fake_extraction(monkeypatch, ("wins", "first reading"))
    entry_id = client.post("/entries", json={"content": "a day"}).json()["id"]
    client.post(f"/entries/{entry_id}/analyze")

    _fake_extraction(monkeypatch, ("wins", "second reading"))
    body = client.post(f"/entries/{entry_id}/analyze").json()

    assert body["wins"] == ["second reading"]
    stored = facts.for_entries([entry_id], user_id=UID)[entry_id]
    assert [f.text for f in stored] == ["second reading"]


def test_analysing_someone_elses_day_is_a_404(sqlite_db):
    other = entries.save_today("their day", "someone-else")

    assert client.post(f"/entries/{other.id}/analyze").status_code == 404


def test_the_record_range_carries_each_days_wins(sqlite_db, monkeypatch):
    _fake_extraction(monkeypatch, ("wins", "shipped it"), ("about me", "lives in Taipei"))
    entry_id = client.post("/entries", json={"content": "a day", "energy": 9}).json()["id"]
    client.post(f"/entries/{entry_id}/analyze")

    body = client.get("/entries?days=7").json()

    assert len(body["entries"]) == 1
    day = body["entries"][0]
    assert day["energy"] == 9
    assert day["wins"] == ["shipped it"]
    # Only the two shown categories come back — the rest are memory, not screen.
    assert day["gratitude"] == []
