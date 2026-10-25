"""The progress dashboard: empty for a new student, then filled by real attempts made through the chat API."""
import json

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from engine.generator import problem_from_dict  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import tutor.chat_store as store
    monkeypatch.setattr(store, "CHAT_DIR", tmp_path / "chats")
    from server import api
    monkeypatch.setattr(api, "students", api.StudentModel(tmp_path / "t.db"))
    monkeypatch.setattr(api, "chat_models", lambda: [])
    return TestClient(api.app)


def _send(c, cid, text, structured=None):
    r = c.post("/api/message", json={"sid": "dee", "id": cid, "text": text, "structured": structured, "model": None})
    return [json.loads(line) for line in r.text.splitlines() if line.strip()][-1]


def test_new_student_has_an_empty_dashboard(client):
    d = client.get("/api/progress", params={"sid": "new"}).json()
    assert d["summary"]["problems"] == 0 and d["summary"]["first_try"] is None
    assert d["recent"] == [] and d["mistakes"] == []
    assert d["next"]["request"].startswith("Give me an easy")
    assert all(k["tried"] == 0 for g in d["groups"] for k in g["skills"])


def test_attempts_fill_the_dashboard(client):
    from tutor.chat_store import load_chat
    for wrong in (True, True, False):
        cid = client.post("/api/chat/new", json={"sid": "dee"}).json()["id"]
        _send(client, cid, "Give me an easy SJF problem")
        res = problem_from_dict(load_chat("dee", cid)["problem"]["problem"]).solve()
        m = {r.pid: {"CT": r.completion, "TAT": r.turnaround, "WT": r.turnaround if wrong else r.waiting}
             for r in res.results.values()}
        _send(client, cid, "My answer", {"gantt": [[s.pid, s.start, s.end] for s in res.gantt if s.pid != "IDLE"],
                                         "metrics": m})
    d = client.get("/api/progress", params={"sid": "dee"}).json()
    assert d["summary"]["problems"] == 3 and d["summary"]["solved"] == 1
    assert d["recent"][0]["correct"] and not d["recent"][-1]["correct"]          # newest first
    top = d["mistakes"][0]
    assert top["type"] == "wt_equals_tat" or "WT" in top["label"]
    assert top["count"] == 2 and top["recurring"]
    sjf = next(k for g in d["groups"] for k in g["skills"] if k["id"] == "SJF")
    assert sjf["tried"] == 3
    assert "Recurring error" in d["next"]["reason"]
