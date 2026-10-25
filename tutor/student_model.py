"""
Student model: the learner's profile, stored in SQLite.

* Every submission is logged (topic, difficulty, correctness, attempt number, hints,
  time taken, error types), matching the "student interaction dataset" in the proposal.
* Mastery of each skill is estimated with Bayesian Knowledge Tracing (BKT), the
  classic intelligent-tutoring-system model. Following the Cognitive Tutor
  convention, only the FIRST submission for a problem updates mastery, and asking
  for a hint before that submission counts as not-yet-mastered for the main skill.
* Recurring errors = the same error type appearing repeatedly in recent submissions.
* recommend_next() decides what to practise next and at what difficulty, and says why.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import config
from tutor.error_analysis import ERROR_CATALOG

SKILLS: dict[str, str] = {
    "FCFS": "FCFS scheduling",
    "SJF": "SJF (non-preemptive)",
    "SRTF": "SRTF (preemptive SJF)",
    "RR": "Round Robin",
    "PRIORITY_NP": "Priority (non-preemptive)",
    "PRIORITY_P": "Priority (preemptive)",
    "CT_READING": "Reading completion time",
    "TAT_FORMULA": "Turnaround time formula",
    "WT_FORMULA": "Waiting time formula",
    "BANKERS_NEED": "Banker's: Need matrix",
    "BANKERS_SAFETY": "Banker's: safety algorithm",
    "SEMAPHORE": "Semaphore tracing",
}
TOPICS = ["FCFS", "SJF", "SRTF", "RR", "PRIORITY_NP", "PRIORITY_P", "BANKERS", "SEMAPHORE"]
TOPIC_NAMES = {**{k: SKILLS[k] for k in TOPICS if k in SKILLS},
               "BANKERS": "Banker's algorithm", "SEMAPHORE": "Semaphores", "ADVANCED": "Past paper (exam-style)"}
TOPIC_SKILLS = {t: [t] for t in TOPICS[:6]}
TOPIC_SKILLS["BANKERS"] = ["BANKERS_NEED", "BANKERS_SAFETY"]
TOPIC_SKILLS["SEMAPHORE"] = ["SEMAPHORE"]
FORMULA_SKILLS = {"CT_READING", "TAT_FORMULA", "WT_FORMULA"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT NOT NULL,
    ts REAL NOT NULL,
    problem_id TEXT,
    topic TEXT,
    difficulty INTEGER,
    attempt_no INTEGER,
    correct INTEGER,
    hints_used INTEGER,
    revealed INTEGER,
    time_taken REAL,
    error_types TEXT,
    root_cause TEXT,
    problem TEXT,
    analysis TEXT
);
CREATE TABLE IF NOT EXISTS lessons (
    student_id TEXT NOT NULL,
    lesson_id TEXT NOT NULL,
    stage INTEGER NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0,
    try_score REAL,
    check_score REAL,
    updated REAL,
    PRIMARY KEY (student_id, lesson_id)
);
CREATE TABLE IF NOT EXISTS teachbacks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT NOT NULL,
    lesson_id TEXT NOT NULL,
    ts REAL NOT NULL,
    transcript TEXT,
    words INTEGER,
    score REAL,
    ratings TEXT,
    misconceptions TEXT,
    judge TEXT,
    questions TEXT
);
CREATE TABLE IF NOT EXISTS skills (
    student_id TEXT NOT NULL,
    skill TEXT NOT NULL,
    p_known REAL NOT NULL,
    n_obs INTEGER NOT NULL DEFAULT 0,
    n_correct INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (student_id, skill)
);
"""


def bkt_update(p: float, correct: bool, prm: dict | None = None) -> float:
    prm = prm or config.BKT
    s, g, t = prm["p_slip"], prm["p_guess"], prm["p_learn"]
    if correct:
        post = p * (1 - s) / (p * (1 - s) + (1 - p) * g)
    else:
        post = p * s / (p * s + (1 - p) * (1 - g))
    return post + (1 - post) * t


class StudentModel:
    def __init__(self, db_path: Path | str = config.DB_PATH):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(db_path)
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------ writes
    def record_attempt(self, student_id: str, problem: dict, problem_id: str, analysis: dict,
                       attempt_no: int, hints_used: int, revealed: bool, time_taken: float) -> dict:
        """Log the submission and (on first submission only) update BKT mastery.
        Returns {skill: (before, after)} for skills that changed."""
        topic = problem.get("algorithm") if problem.get("kind") == "scheduling" else problem.get("kind", "").upper()
        root = analysis.get("root_cause")
        with self._conn() as c:
            c.execute(
                "INSERT INTO attempts (student_id, ts, problem_id, topic, difficulty, attempt_no, correct, hints_used,"
                " revealed, time_taken, error_types, root_cause, problem, analysis) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (student_id, time.time(), problem_id, topic, problem.get("difficulty"), attempt_no,
                 int(bool(analysis.get("correct"))), hints_used, int(revealed), time_taken,
                 json.dumps(analysis.get("error_types", [])), root["type"] if root else None,
                 json.dumps(problem), json.dumps(_slim(analysis))))
        changes: dict[str, tuple[float, float]] = {}
        if attempt_no != 1:
            return changes
        main_skills = set(TOPIC_SKILLS.get(topic, []))
        for skill, ok in analysis.get("observations", {}).items():
            if skill in main_skills and (hints_used > 0 or revealed):
                ok = False
            before = self._get_skill(student_id, skill)["p_known"]
            after = bkt_update(before, ok)
            self._set_skill(student_id, skill, after, ok)
            changes[skill] = (before, after)
        return changes

    def _get_skill(self, sid: str, skill: str) -> dict:
        with self._conn() as c:
            row = c.execute("SELECT * FROM skills WHERE student_id=? AND skill=?", (sid, skill)).fetchone()
        if row:
            return dict(row)
        return {"student_id": sid, "skill": skill, "p_known": config.BKT["p_init"], "n_obs": 0, "n_correct": 0}

    def _set_skill(self, sid: str, skill: str, p: float, ok: bool) -> None:
        cur = self._get_skill(sid, skill)
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO skills VALUES (?,?,?,?,?)",
                      (sid, skill, p, cur["n_obs"] + 1, cur["n_correct"] + int(ok)))

    def reset(self, student_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM attempts WHERE student_id=?", (student_id,))
            c.execute("DELETE FROM skills WHERE student_id=?", (student_id,))
            c.execute("DELETE FROM lessons WHERE student_id=?", (student_id,))
            c.execute("DELETE FROM teachbacks WHERE student_id=?", (student_id,))

    # ------------------------------------------------------------------ teach-back (Explain it back)
    def record_teachback(self, student_id: str, lesson_id: str, transcript: str, assessment: dict) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO teachbacks (student_id, lesson_id, ts, transcript, words, score, ratings, misconceptions,"
                " judge, questions) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (student_id, lesson_id, time.time(), transcript, assessment.get("words"), assessment.get("score"),
                 json.dumps(assessment.get("ideas")), json.dumps(assessment.get("misconceptions")),
                 assessment.get("source"), "[]"))
            return cur.lastrowid

    def update_teachback_questions(self, row_id: int, questions: list[dict]) -> None:
        with self._conn() as c:
            c.execute("UPDATE teachbacks SET questions=? WHERE id=?", (json.dumps(questions), row_id))

    def teachbacks(self, student_id: str, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM teachbacks WHERE student_id=? ORDER BY id DESC LIMIT ?",
                             (student_id, limit)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ lessons (Learn mode)
    def lesson_progress(self, student_id: str) -> dict[str, dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM lessons WHERE student_id=?", (student_id,)).fetchall()
        return {r["lesson_id"]: dict(r) for r in rows}

    def update_lesson(self, student_id: str, lesson_id: str, **fields) -> None:
        cur = self.lesson_progress(student_id).get(lesson_id, {"stage": 0, "completed": 0, "try_score": None,
                                                                "check_score": None})
        furthest = int(cur.get("stage") or 0)
        cur.update({k: v for k, v in fields.items() if v is not None})
        if fields.get("stage") is not None:
            cur["stage"] = max(furthest, int(fields["stage"]))   # remember the furthest stage reached
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO lessons VALUES (?,?,?,?,?,?,?)",
                      (student_id, lesson_id, cur["stage"], int(bool(cur["completed"])), cur["try_score"],
                       cur["check_score"], time.time()))

    # ------------------------------------------------------------------ reads
    def mastery(self, student_id: str) -> dict[str, dict]:
        out = {k: {"skill": k, "name": v, "p_known": config.BKT["p_init"], "n_obs": 0, "n_correct": 0}
               for k, v in SKILLS.items()}
        with self._conn() as c:
            for r in c.execute("SELECT * FROM skills WHERE student_id=?", (student_id,)):
                out[r["skill"]].update({"p_known": r["p_known"], "n_obs": r["n_obs"], "n_correct": r["n_correct"]})
        return out

    def topic_mastery(self, student_id: str, topic: str) -> float:
        m = self.mastery(student_id)
        return min(m[s]["p_known"] for s in TOPIC_SKILLS[topic])

    def history(self, student_id: str, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT id, ts, topic, difficulty, attempt_no, correct, hints_used, revealed, "
                             "time_taken, error_types, root_cause FROM attempts WHERE student_id=? "
                             "ORDER BY id DESC LIMIT ?", (student_id, limit)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["error_types"] = json.loads(d["error_types"] or "[]")
            out.append(d)
        return out

    def recurring_errors(self, student_id: str) -> list[dict]:
        """Error types seen in several DIFFERENT recent problems (retries of one problem don't count twice)."""
        with self._conn() as c:
            rows = c.execute("SELECT problem_id, topic, error_types FROM attempts WHERE student_id=? "
                             "ORDER BY id DESC LIMIT ?", (student_id, config.RECURRING_WINDOW * 3)).fetchall()
        problems_seen: list[str] = []
        per_type: dict[str, set] = {}
        topic_of: dict[str, str] = {}
        for r in rows:
            if r["problem_id"] not in problems_seen:
                if len(problems_seen) >= config.RECURRING_WINDOW:
                    break
                problems_seen.append(r["problem_id"])
            for e in json.loads(r["error_types"] or "[]"):
                per_type.setdefault(e, set()).add(r["problem_id"])
                topic_of.setdefault(e, r["topic"])
        out = []
        for e, pids in sorted(per_type.items(), key=lambda kv: -len(kv[1])):
            if len(pids) >= config.RECURRING_MIN:
                info = ERROR_CATALOG.get(e, {})
                skill = info.get("skill")
                if skill == "ALGO":
                    skill = topic_of[e]
                out.append({"type": e, "count": len(pids), "label": info.get("label", e), "skill": skill,
                            "topic": topic_of[e], "misconception": info.get("misconception")})
        return out

    def first_attempt_results(self, student_id: str, topic: str, n: int = 2) -> list[bool]:
        with self._conn() as c:
            rows = c.execute("SELECT correct, hints_used FROM attempts WHERE student_id=? AND topic=? AND attempt_no=1 "
                             "ORDER BY id DESC LIMIT ?", (student_id, topic, n)).fetchall()
        return [bool(r["correct"]) and r["hints_used"] == 0 for r in rows]

    def level(self, student_id: str, topic: str) -> str:
        p = self.topic_mastery(student_id, topic) if topic in TOPIC_SKILLS else config.BKT["p_init"]
        if p < 0.4:
            return "beginner"
        if p < 0.75:
            return "intermediate"
        return "advanced"

    def overall_level(self, student_id: str) -> str:
        seen = [v["p_known"] for v in self.mastery(student_id).values() if v["n_obs"] > 0]
        if not seen:
            return "beginner"
        p = sum(seen) / len(seen)
        return "beginner" if p < 0.4 else "intermediate" if p < 0.75 else "advanced"

    # ------------------------------------------------------------------ adaptivity
    def difficulty_for(self, student_id: str, topic: str) -> tuple[int, str]:
        p = self.topic_mastery(student_id, topic)
        lo, hi = config.MASTERY_THRESHOLDS
        d = 1 if p < lo else 2 if p < hi else 3
        why = f"mastery {p:.2f} → {['', 'easy', 'medium', 'hard'][d]}"
        recent = self.first_attempt_results(student_id, topic, 2)
        if len(recent) == 2 and all(recent) and d < 3:
            d += 1
            why += "; last two solved first time without hints → one level up"
        elif len(recent) == 2 and not any(recent) and d > 1:
            d -= 1
            why += "; last two first attempts wrong → one level down"
        return d, why

    def recommend_next(self, student_id: str, topics: list[str] | None = None) -> dict:
        topics = topics or TOPICS
        recurring = self.recurring_errors(student_id)
        for r in recurring:
            skill = r["skill"]
            if skill in FORMULA_SKILLS:
                # isolate the formula in the simplest context: easy FCFS (no scheduling decisions to get wrong)
                topic = "FCFS" if "FCFS" in topics else topics[0]
                return {"topic": topic, "difficulty": 1, "focus_error": r["type"],
                        "reason": f"Recurring error: “{r['label']}” (in {r['count']} recent problems). An easy FCFS problem "
                                  f"isolates the formula from scheduling decisions."}
            for t in topics:
                if skill in TOPIC_SKILLS.get(t, []):
                    d, why = self.difficulty_for(student_id, t)
                    return {"topic": t, "difficulty": max(1, d - 1), "focus_error": r["type"],
                            "reason": f"Recurring error: “{r['label']}” (in {r['count']} recent problems) in "
                                      f"{TOPIC_NAMES[t]}; practising it again one level easier ({why})."}
        m = self.mastery(student_id)

        def score(t):
            ps = [m[s]["p_known"] for s in TOPIC_SKILLS[t]]
            obs = sum(m[s]["n_obs"] for s in TOPIC_SKILLS[t])
            return (min(ps), obs, topics.index(t))
        target = min(topics, key=score)
        d, why = self.difficulty_for(student_id, target)
        seen = sum(m[s]["n_obs"] for s in TOPIC_SKILLS[target])
        lead = "Not practised yet" if seen == 0 else "Lowest mastery"
        return {"topic": target, "difficulty": d, "focus_error": None,
                "reason": f"{lead}: {TOPIC_NAMES[target]} ({why})."}


def _slim(analysis: dict) -> dict:
    keep = ("kind", "correct", "gantt_correct", "metrics_correct", "cells", "error_types", "observations",
            "divergence", "student_gantt")
    out = {k: analysis.get(k) for k in keep if k in analysis}
    out["errors"] = [{k: e[k] for k in ("type", "category", "skill", "count")} for e in analysis.get("errors", [])]
    return out
