"""The FastAPI server: chats are created, messages stream back, cards come with engine numbers."""
import json

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import tutor.chat_store as store
    monkeypatch.setattr(store, "CHAT_DIR", tmp_path / "chats")
    from server import api
    monkeypatch.setattr(api, "students", api.StudentModel(tmp_path / "t.db"))
    monkeypatch.setattr(api, "chat_models", lambda: [])          # behave as if Ollama were offline
    return TestClient(api.app)


def send(c, sid, chat_id, text, structured=None):
    r = c.post("/api/message", json={"sid": sid, "id": chat_id, "text": text, "structured": structured, "model": None})
    assert r.status_code == 200
    events = [json.loads(line) for line in r.text.splitlines() if line.strip()]
    assert events[0]["type"] == "start" and events[-1]["type"] == "done", events[-1]
    return events


def test_status_and_new_chat(client):
    s = client.get("/api/status").json()
    assert s["online"] is False and s["notes"]["chunks"] > 0
    chat = client.post("/api/chat/new", json={"sid": "ana"}).json()
    assert chat["messages"][0]["role"] == "assistant" and chat["messages"][0]["suggestions"]


def test_practice_answer_and_history(client):
    chat = client.post("/api/chat/new", json={"sid": "ana"}).json()
    cid = chat["id"]
    ev = send(client, "ana", cid, "give me an easy FCFS problem")
    done = ev[-1]
    card = done["message"]["cards"][0]
    assert card["type"] == "problem" and card["tables"][0]["columns"][0] == "Process"
    assert done["form"]["kind"] == "scheduling"
    # answer through the form: the server checks it with the engine
    from engine.generator import problem_from_dict
    from tutor.chat_store import load_chat
    st = load_chat("ana", cid)
    res = problem_from_dict(st["problem"]["problem"]).solve()
    structured = {"gantt": [[s.pid, s.start, s.end] for s in res.gantt if s.pid != "IDLE"],
                  "metrics": {r.pid: {"CT": r.completion, "TAT": r.turnaround, "WT": r.waiting} for r in res.results.values()}}
    done = send(client, "ana", cid, "My answer", structured)[-1]
    marked = done["message"]["cards"][0]
    assert marked["type"] == "marked" and marked["correct"] and done["form"] is None
    chats = client.get("/api/chats", params={"sid": "ana"}).json()
    assert chats[0]["id"] == cid and chats[0]["title"].startswith("give me")
    again = client.get("/api/chat", params={"sid": "ana", "id": cid}).json()
    assert len(again["messages"]) == 5


def test_solution_quiz_and_explain_cards(client):
    cid = client.post("/api/chat/new", json={"sid": "ben"}).json()["id"]
    done = send(client, "ben", cid, "Solve using SRTF: P1 AT=0 BT=8, P2 AT=1 BT=4, P3 AT=2 BT=9")[-1]
    sol = done["message"]["cards"][0]
    assert sol["type"] == "solution" and sol["gantt"]["segments"][0][0] == "P1" and sol["details"]["rows"]
    done = send(client, "ben", cid, "quiz me on deadlocks")[-1]
    assert done["message"]["cards"][0]["type"] == "quiz" and done["message"]["cards"][0]["active"]
    done = send(client, "ben", cid, "explain round robin")[-1]
    assert any(c["type"] == "example" and c.get("gantt") for c in done["message"]["cards"])
    deltas = [e for e in send(client, "ben", cid, "how am i doing?") if e["type"] == "delta"]
    assert deltas


def test_delete_chat(client):
    cid = client.post("/api/chat/new", json={"sid": "cy"}).json()["id"]
    send(client, "cy", cid, "hi")
    assert client.get("/api/chats", params={"sid": "cy"}).json()
    client.delete("/api/chat", params={"sid": "cy", "id": cid})
    assert client.get("/api/chats", params={"sid": "cy"}).json() == []
