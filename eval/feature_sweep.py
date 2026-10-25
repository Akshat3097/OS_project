"""
Every feature through the server's API, quickly and without the language model: all 13 lessons (lesson page, stages,
notes, guided practice, explain-it-back, questions, pointers, clips), every lab preset plus random labs, mock exams
(a perfect script must score 30/30, an empty one 0), the chat's actions, and the progress page.

    python -m eval.feature_sweep             (about a minute; uses a temporary database)

Prints one line per area and exits non-zero if anything failed.
"""
from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path

from fastapi.testclient import TestClient

from server import api, exam
from tests.test_exam import perfect
from tutor import lessons as L
from tutor import videos
from tutor.student_model import StudentModel

SID = "Sweep"
results: list[tuple[str, bool, str]] = []


def area(name: str):
    def wrap(fn):
        try:
            note = fn() or ""
            results.append((name, True, note))
        except Exception as e:  # keep going
            results.append((name, False, f"{type(e).__name__}: {e}"))
            traceback.print_exc()
        return fn
    return wrap


def ok(r, what: str):
    assert r.status_code == 200, f"{what}: HTTP {r.status_code} {r.text[:200]}"
    return r.json()


def ndjson(r) -> list[dict]:
    assert r.status_code == 200, r.text[:200]
    return [json.loads(line) for line in r.text.splitlines() if line.strip()]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    tmp = Path(tempfile.mkdtemp(prefix="sweep_"))
    api.students = StudentModel(tmp / "sweep.db")
    api.exams = exam.Exams()
    import tutor.chat_store as store
    store.CHAT_DIR = tmp / "chats"
    c = TestClient(api.app)

    @area("Status and lesson list")
    def _():
        s = ok(c.get("/api/status"), "status")
        lessons = ok(c.get(f"/api/learn/lessons?sid={SID}"), "lessons")
        n = sum(len(g["lessons"]) for g in lessons["groups"]) if "groups" in lessons else len(lessons.get("lessons", []))
        return f"{len(s.get('models', []))} models, {n} lessons listed"

    @area("All 13 lessons: page, stages, notes, practice, explain-back, questions, pointers")
    def _():
        notes = []
        for lesson in L.LESSONS:
            lid = lesson["id"]
            ok(c.get(f"/api/learn/lesson?sid={SID}&id={lid}"), f"{lid} page")
            for stage in range(len(L.STAGES)):
                ok(c.post("/api/learn/stage", json={"sid": SID, "lesson": lid, "stage": stage}), f"{lid} stage {stage}")
            ok(c.get(f"/api/learn/notes?id={lid}"), f"{lid} notes")
            tr = c.get(f"/api/learn/try?id={lid}&seed=7")
            if tr.status_code == 200 and tr.json()["kind"] == "metrics":
                t = tr.json()
                from engine import generator
                res = generator.problem_from_dict(t["problem"]).solve()
                right = {p: {"CT": r.completion, "TAT": r.turnaround, "WT": r.waiting} for p, r in res.results.items()}
                chk = ok(c.post("/api/learn/try/check", json={"problem": t["problem"], "metrics": right}), f"{lid} check")
                assert chk["correct"], f"{lid}: the correct table was marked wrong"
            text = " ".join(i["statement"] for i in lesson["ideas"]) + " That is how I would explain it to a friend."
            a = ok(c.post("/api/learn/teachback", json={"sid": SID, "lesson": lid, "text": text, "use_llm": False}),
                   f"{lid} teachback")
            assert a["clear"] >= 1, f"{lid}: reading out the key ideas scored {a['clear']}/{a['total']}"
            asked = 0
            for _ in range(4):
                q = c.post("/api/learn/question", json={"sid": SID, "lesson": lid})
                if q.status_code != 200 or not q.json().get("question"):
                    break
                qv = q.json()["question"]
                ans = (qv["options"][0] if qv.get("options") else
                       [qv["value_options"][0], qv["outcomes"][0]] if qv["kind"] == "semaphore" else 3)
                r = ok(c.post("/api/learn/answer", json={"sid": SID, "lesson": lid, "answer": ans}), f"{lid} answer")
                asked += 1
                if not r.get("more"):
                    break
            p = ok(c.post("/api/learn/pointers", json={"sid": SID, "lesson": lid}), f"{lid} pointers")
            notes.append(f"{lid}:{a['clear']}/{a['total']}+{asked}q")
        return "explain-back key ideas found: " + ", ".join(notes)

    @area("Lecture clips")
    def _():
        missing = [l["id"] for l in L.LESSONS if not videos.clips_for(l["id"])]
        assert not missing, f"lessons without a clip: {missing}"
        n = len({c_["video"] for c_ in videos.load()})
        return f"every lesson has a clip; {n} videos"

    @area("Labs: every preset")
    def _():
        out = []
        for p in api.labs.PRESETS["scheduler"]:
            r = ok(c.post("/api/labs/scheduler", json={"processes": p["processes"], "quantum": p["quantum"]}), p["name"])
        out.append(f"{len(api.labs.PRESETS['scheduler'])} scheduler")
        for p in api.labs.PRESETS["bankers"]:
            ok(c.post("/api/labs/bankers", json={k: p[k] for k in ("available", "maximum", "allocation", "resources")}),
               p["name"])
        out.append(f"{len(api.labs.PRESETS['bankers'])} Banker's")
        for p in api.labs.PRESETS["semaphores"]:
            ok(c.post("/api/labs/semaphores", json={"initial": p["initial"], "ops": p["ops"]}), p["name"])
        out.append(f"{len(api.labs.PRESETS['semaphores'])} semaphore")
        for p in api.labs.PRESETS["deadlocks"]:
            ok(c.post("/api/labs/deadlocks", json={k: p[k] for k in ("processes", "resources", "edges")}), p["name"])
        out.append(f"{len(api.labs.PRESETS['deadlocks'])} deadlock")
        ok(c.post("/api/labs/parse", json={"text": "Round robin q=2: P1(0,5), P2(1,3), P3(2,1)"}), "parse")
        return ", ".join(out) + " presets, and a pasted question"

    @area("Labs: 60 random problems")
    def _():
        for _ in range(20):
            s = ok(c.get("/api/labs/random?kind=scheduler"), "random scheduler")
            ok(c.post("/api/labs/scheduler", json=s), "scheduler")
            b = ok(c.get("/api/labs/random?kind=bankers"), "random bankers")
            ok(c.post("/api/labs/bankers", json=b), "bankers")
            m = ok(c.get("/api/labs/random?kind=semaphores"), "random semaphores")
            ok(c.post("/api/labs/semaphores", json=m), "semaphores")
        return "20 each of scheduler, Banker's and semaphore, all solved"

    @area("Mock exam: 15 papers")
    def _():
        for _ in range(15):
            v = ok(c.post("/api/exam/start", json={"sid": SID}), "start")
            full = ok(c.post("/api/exam/submit", json={"id": v["id"], "answers": perfect(api.exams.get(v["id"])["paper"])}),
                      "perfect")
            assert full["total"] == 30, f"a perfect script scored {full['total']}/30"
            v2 = ok(c.post("/api/exam/start", json={"sid": SID}), "start")
            empty = ok(c.post("/api/exam/submit", json={"id": v2["id"], "answers": {}}), "empty")
            assert empty["total"] == 0, f"an empty script scored {empty['total']}"
        return "perfect scripts 30/30, empty scripts 0/30"

    @area("Chat actions (language model off)")
    def _():
        chat = ok(c.post("/api/chat/new", json={"sid": SID}), "new chat")
        msgs = ["explain round robin", "give me an example",
                "Solve using SRTF: P1 arrives at 0 with burst 8, P2 at 1 with burst 4, P3 at 2 with burst 9",
                "why is the waiting time of P3 that much?",
                "P1 arrives at 0 with burst 4, P2 at 1 with burst 3, P3 at 2 with burst 1. Use FCFS. "
                "My answer: waiting times P1 = 0, P2 = 3, P3 = 5",
                "Allocation: P0 0 1 0, P1 2 0 0, P2 3 0 2, P3 2 1 1, P4 0 0 2. Max: P0 7 5 3, P1 3 2 2, P2 9 0 2, "
                "P3 2 2 2, P4 4 3 3. Available 3 3 2. Is it safe?", "show me the full solution",
                "what if P1 requests 1 0 2?", "quiz me on deadlocks", "a", "stop", "is an unsafe state a deadlock?",
                "what does fork return?", "give me a hard round robin problem", "how am I doing?",
                "let me explain semaphores", "a semaphore is an integer changed only by atomic wait and signal; "
                "wait decrements it and blocks the process when it goes negative, signal increments it and wakes one",
                "what can you teach me?", "dinning philosphers problem?", "write a python program for bubble sort"]
        actions = []
        for m in msgs:
            ev = ndjson(c.post("/api/message", json={"sid": SID, "id": chat["id"], "text": m, "use_llm": False}))
            errs = [e for e in ev if e["type"] == "error"]
            assert not errs, f"{m!r}: {errs[0]['text']}"
            done = next(e for e in ev if e["type"] == "done")
            text = done["message"]["content"]
            assert text.strip(), f"{m!r}: empty reply"
            assert not text.startswith("Sorry, something went wrong"), f"{m!r}: {text[:80]}"
            actions.append(done["message"]["meta"].get("action", "?"))
        return f"{len(msgs)} messages, no errors: " + " ".join(actions)

    @area("Progress page")
    def _():
        p = ok(c.get(f"/api/progress?sid={SID}"), "progress")
        return f"{len(json.dumps(p))} bytes of dashboard data"

    width = max(len(n) for n, _, _ in results)
    for name, passed, note in results:
        print(f"  {'✓' if passed else '✗'} {name:<{width}}  {note}")
    bad = [n for n, p, _ in results if not p]
    print(f"\n{'All areas passed.' if not bad else 'FAILED: ' + ', '.join(bad)}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
