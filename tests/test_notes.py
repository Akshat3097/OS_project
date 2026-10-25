"""The student's own notes: add, list (pinned first), edit, pin, delete, per student."""
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import config
    from server import api
    monkeypatch.setattr(config, "NOTES_DIR", tmp_path / "notes")
    return TestClient(api.app)


def test_notes_round_trip(client):
    a = client.post("/api/notes", json={"sid": "Asha", "text": "RR: new arrival joins the queue first", "title": "RR rule",
                                        "source": "From chat: Round Robin"}).json()
    b = client.post("/api/notes", json={"sid": "Asha", "text": "WT = TAT - BT", "color": "mint"}).json()
    assert a["color"] in ("butter", "peach", "lilac", "sky", "mint") and b["color"] == "mint"
    notes = client.get("/api/notes?sid=Asha").json()["notes"]
    assert [n["id"] for n in notes] == [b["id"], a["id"]]                 # newest first
    client.put(f"/api/notes/{a['id']}", json={"sid": "Asha", "pinned": True, "text": "RR: arrival before the preempted one"})
    notes = client.get("/api/notes?sid=Asha").json()["notes"]
    assert notes[0]["id"] == a["id"] and notes[0]["pinned"] and notes[0]["text"].startswith("RR: arrival")
    assert client.get("/api/notes?sid=Ravi").json()["notes"] == []          # another student sees nothing
    assert client.delete(f"/api/notes/{b['id']}?sid=Asha").json() == {"ok": True}
    assert [n["id"] for n in client.get("/api/notes?sid=Asha").json()["notes"]] == [a["id"]]


def test_notes_reject_empty_and_unknown(client):
    assert client.post("/api/notes", json={"sid": "Asha", "text": "   "}).status_code == 400
    assert client.put("/api/notes/nope", json={"sid": "Asha", "text": "x"}).status_code == 404
    assert client.delete("/api/notes/nope?sid=Asha").status_code == 404
