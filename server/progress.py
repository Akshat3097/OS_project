"""
The progress dashboard as JSON: headline numbers, mastery per skill (Bayesian Knowledge Tracing), recent attempts,
the most common mistakes, lessons and teach-backs, and what to practise next (StudentModel.recommend_next).
"""
from __future__ import annotations

import json
from collections import Counter

from tutor import lessons as L
from tutor.error_analysis import ERROR_CATALOG
from tutor.student_model import SKILLS, TOPIC_NAMES, StudentModel

GROUPS = [("CPU scheduling", ["FCFS", "SJF", "SRTF", "RR", "PRIORITY_NP", "PRIORITY_P"]),
          ("Formulas", ["CT_READING", "TAT_FORMULA", "WT_FORMULA"]),
          ("Synchronization and deadlocks", ["SEMAPHORE", "BANKERS_NEED", "BANKERS_SAFETY"])]
DIFFICULTY = {1: "easy", 2: "medium", 3: "hard"}
PRACTICE_WORDS = {"FCFS": "FCFS", "SJF": "SJF", "SRTF": "SRTF", "RR": "Round Robin", "PRIORITY_NP": "priority scheduling",
                  "PRIORITY_P": "preemptive priority", "SEMAPHORE": "semaphore", "BANKERS": "Banker's algorithm"}


def _level(p: float) -> str:
    return "not yet" if p < 0.4 else "getting there" if p < 0.75 else "mastered"


def dashboard(students: StudentModel, sid: str) -> dict:
    m = students.mastery(sid)
    with students._conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT problem_id, ts, topic, difficulty, attempt_no, correct, hints_used, revealed, error_types, root_cause "
            "FROM attempts WHERE student_id=? ORDER BY id", (sid,))]
    firsts = [r for r in rows if r["attempt_no"] == 1]
    solved = {r["problem_id"] for r in rows if r["correct"]}
    errors = Counter(e for r in rows for e in json.loads(r["error_types"] or "[]") if e != "missing_value")
    recurring = {r["type"] for r in students.recurring_errors(sid)}
    lessons = students.lesson_progress(sid)
    tbs = students.teachbacks(sid, limit=200)
    rec = students.recommend_next(sid)

    groups = []
    for name, skills in GROUPS:
        groups.append({"name": name, "skills": [
            {"id": s, "name": SKILLS[s], "p": round(m[s]["p_known"], 3), "tried": m[s]["n_obs"],
             "right": m[s]["n_correct"], "level": _level(m[s]["p_known"])} for s in skills]})

    recent = []
    for r in reversed(rows[-12:]):
        root = ERROR_CATALOG.get(r["root_cause"] or "", {}).get("label") if r["root_cause"] else None
        recent.append({"ts": r["ts"], "topic": TOPIC_NAMES.get(r["topic"], r["topic"]),
                       "difficulty": DIFFICULTY.get(r["difficulty"], ""), "attempt": r["attempt_no"],
                       "correct": bool(r["correct"]), "hints": r["hints_used"] or 0, "revealed": bool(r["revealed"]),
                       "mistake": root})

    best_tb = {}
    for t in tbs:                                   # newest first, so the first one per lesson is the latest
        best_tb.setdefault(t["lesson_id"], t)
    lesson_rows = []
    for l in L.LESSONS:
        p = lessons.get(l["id"], {})
        tb = best_tb.get(l["id"])
        lesson_rows.append({"id": l["id"], "title": l["title"], "completed": bool(p.get("completed")),
                            "started": bool(p), "explained": round(tb["score"], 2) if tb and tb["score"] is not None else None})

    return {
        "summary": {"problems": len({r["problem_id"] for r in rows}), "solved": len(solved),
                    "first_try": round(sum(bool(r["correct"]) and not r["hints_used"] for r in firsts) / len(firsts), 3)
                    if firsts else None,
                    "lessons_done": sum(1 for x in lesson_rows if x["completed"]), "lessons_total": len(lesson_rows),
                    "teachbacks": len(tbs), "hints": sum(r["hints_used"] or 0 for r in rows)},
        "groups": groups,
        "recent": recent,
        "mistakes": [{"type": e, "label": ERROR_CATALOG.get(e, {}).get("label", e), "count": n,
                      "why": ERROR_CATALOG.get(e, {}).get("misconception"), "recurring": e in recurring}
                     for e, n in errors.most_common(6)],
        "lessons": lesson_rows,
        "next": {"topic": rec["topic"], "name": TOPIC_NAMES.get(rec["topic"], rec["topic"]),
                 "difficulty": DIFFICULTY.get(rec["difficulty"], ""), "reason": rec["reason"],
                 "request": f"Give me {'an' if rec['difficulty'] == 1 else 'a'} {DIFFICULTY.get(rec['difficulty'], 'medium')} "
                            f"{PRACTICE_WORDS.get(rec['topic'], rec['topic'])} problem"},
    }
