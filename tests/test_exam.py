"""Exam mode: the paper hides its answers, a perfect script scores 30/30 and updates mastery, mistakes are marked
fairly (method marks for follow-on errors), and submitting twice gives the same result."""
import json

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from engine import bankers, deadlock, generator, semaphore  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from server import api, exam
    monkeypatch.setattr(api, "students", api.StudentModel(tmp_path / "t.db"))
    monkeypatch.setattr(api, "exams", exam.Exams())
    return TestClient(api.app), api


def perfect(paper: dict) -> dict:
    s = generator.problem_from_dict(paper["scheduling"]).solve()
    b = generator.problem_from_dict(paper["bankers"])
    sb = bankers.safety(b.available, b.maximum, b.allocation)
    m = generator.problem_from_dict(paper["semaphore"])
    tm = semaphore.trace(m.initial, m.ops)
    d = paper["detection"]
    det = deadlock.detect(d["available"], d["allocation"], d["request"])
    return {"q1": {"gantt": ", ".join(f"{g.pid} {g.start}-{g.end}" for g in s.gantt if g.pid != "IDLE"),
                   "metrics": {r.pid: {"CT": r.completion, "TAT": r.turnaround, "WT": r.waiting} for r in s.results.values()},
                   "avg_wt": round(s.avg_wt, 2)},
            "q2": {"need": sb["need"], "safe": sb["safe"], "sequence": ", ".join(sb["sequence"])},
            "q3": {"final": tm["final_values"], "blocked": tm["blocked"]},
            "q4": {"deadlock": det["deadlock"], "deadlocked": det["deadlocked"]},
            "q5": [next(o["text"] for o in q["options"] if o["ok"]) for q in paper["mcq"]]}


def test_paper_hides_answers_and_perfect_scores_full(client):
    c, api = client
    v = c.post("/api/exam/start", json={"sid": "e"}).json()
    assert [q["kind"] for q in v["questions"]] == ["scheduling", "bankers", "semaphore", "detection", "mcq"]
    def keys(x):                                                  # every key anywhere in the paper
        return set(x) | set().union(*map(keys, x.values())) if isinstance(x, dict) else \
            set().union(*map(keys, x)) if isinstance(x, list) else set()
    assert not keys(v) & {"ok", "why", "need", "sequence", "safe", "final", "blocked", "deadlocked", "results", "answer"}
    assert all(isinstance(o, str) for item in v["questions"][4]["items"] for o in item["options"])
    assert "result" not in json.dumps(v)
    r = c.post("/api/exam/submit", json={"id": v["id"], "answers": perfect(api.exams.get(v["id"])["paper"])}).json()
    assert r["total"] == 30 and all(q["marks"] == sum(p[2] for p in q["parts"]) for q in r["questions"])
    assert r["mastery"] and all(m["after"] > m["before"] for m in r["mastery"])
    again = c.post("/api/exam/submit", json={"id": v["id"], "answers": {}}).json()
    assert again["total"] == 30                                      # a second submission does not re-mark
    assert c.get("/api/progress", params={"sid": "e"}).json()["summary"]["problems"] == 3


def test_empty_script_scores_zero_and_follow_on_errors_get_method_marks(client):
    c, api = client
    v = c.post("/api/exam/start", json={"sid": "f"}).json()
    assert c.post("/api/exam/submit", json={"id": v["id"], "answers": {}}).json()["total"] == 0
    v2 = c.post("/api/exam/start", json={"sid": "f"}).json()
    ans = perfect(api.exams.get(v2["id"])["paper"])
    ans["q1"]["metrics"] = {k: {**m, "WT": m["TAT"]} for k, m in ans["q1"]["metrics"].items()}     # WT = TAT slip
    q1 = c.post("/api/exam/submit", json={"id": v2["id"], "answers": ans}).json()["questions"][0]
    assert q1["parts"][0][1] == 3 and 0 < q1["parts"][1][1] < 6
    assert any("WT = TAT" in m for m in q1["mistakes"])


def test_unknown_paper(client):
    c, _ = client
    assert c.get("/api/exam", params={"id": "nope"}).status_code == 404
    assert c.post("/api/exam/submit", json={"id": "nope", "answers": {}}).status_code == 404
