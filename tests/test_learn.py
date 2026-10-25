"""Learn mode in the web app: every lesson loads, its worked example matches the engine, and the
teach-back → question → pointers loop works through the API."""
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from engine.generator import SchedulingProblem  # noqa: E402
from tutor import lessons as L  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from server import api, learn
    monkeypatch.setattr(api, "students", api.StudentModel(tmp_path / "t.db"))
    monkeypatch.setattr(api, "teachbacks", learn.TeachbackSessions())
    monkeypatch.setattr(api, "chat_models", lambda: [])
    return TestClient(api.app)


def test_every_lesson_loads(client):
    data = client.get("/api/learn/lessons", params={"sid": "a"}).json()
    assert len(data["lessons"]) == len(L.LESSONS) and data["recommended"] == "basics"
    for item in data["lessons"]:
        v = client.get("/api/learn/lesson", params={"sid": "a", "id": item["id"]}).json()
        w = v["watch"]
        assert v["concept"] and v["mcq"] and len(v["stages"]) == 5
        assert w.get("steps") or w.get("slides")
        r = client.get("/api/learn/try", params={"id": item["id"]})
        assert r.status_code == (200 if v["has_try"] else 404)


def test_watch_steps_match_the_engine(client):
    v = client.get("/api/learn/lesson", params={"sid": "a", "id": "srtf"}).json()["watch"]
    w = L.LESSON_BY_ID["srtf"]["watch"]
    res = SchedulingProblem("SRTF", 1, w["processes"]).solve()
    assert v["final"]["segments"] == [[s.pid, s.start, s.end] for s in res.gantt]
    assert v["stats"][1] == ["Average WT", "6.50"]                       # the textbook answer
    times = [s["time"] for s in v["steps"]]
    assert times == sorted(times)
    for s in v["steps"]:                                                 # the chart so far never passes the decision time
        assert all(seg[2] <= s["time"] for seg in s["gantt"]["segments"])


def test_teachback_question_pointers(client):
    ref = {"sid": "b", "lesson": "srtf"}
    assert client.post("/api/learn/teachback", json={**ref, "text": "too short"}).status_code == 400
    a = client.post("/api/learn/teachback", json={**ref, "text": (
        "SRTF always runs the process with the shortest remaining time. When a new process arrives we compare it "
        "with the remaining time of the running one and preempt only if it is strictly shorter.")}).json()
    assert a["total"] == 4 and a["source"] == "keyword rubric"
    q = client.post("/api/learn/question", json=ref).json()
    again = client.post("/api/learn/question", json=ref).json()
    assert again["question"] == q["question"]                            # unanswered: same question after a reload
    assert client.post("/api/learn/answer", json={**ref, "answer": "not an option"}).status_code == 400
    opts = q["question"].get("options")
    ans = opts[0] if opts else ([q["question"]["value_options"][0], q["question"]["outcomes"][0]]
                                if q["question"]["kind"] == "semaphore" else 0)
    r = client.post("/api/learn/answer", json={**ref, "answer": ans}).json()
    assert set(r) >= {"ok", "explanation", "correct", "idea", "more"}
    p = client.post("/api/learn/pointers", json=ref).json()
    assert p["verdict"] and p["explained"] and len(p["questions"]) == 1
    done = {l["id"]: l for l in client.get("/api/learn/lessons", params={"sid": "b"}).json()["lessons"]}
    assert done["srtf"]["completed"]


def test_skipping_the_explanation_still_gives_a_question(client):
    q = client.post("/api/learn/question", json={"sid": "c", "lesson": "bankers"}).json()
    assert q["explained"] is False and q["question"]["kind"]


def test_metrics_try_marks_cells(client):
    t = client.get("/api/learn/try", params={"id": "basics"}).json()
    from engine.generator import problem_from_dict
    res = problem_from_dict(t["problem"]).solve()
    right = {r.pid: {"CT": r.completion, "TAT": r.turnaround, "WT": r.waiting} for r in res.results.values()}
    assert client.post("/api/learn/try/check", json={"problem": t["problem"], "metrics": right}).json()["correct"]
    wrong = {pid: {**m, "TAT": m["CT"]} for pid, m in right.items()}
    out = client.post("/api/learn/try/check", json={"problem": t["problem"], "metrics": wrong}).json()
    assert not out["correct"] and out["errors"]
