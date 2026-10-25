"""
A demo student with about two weeks of history and roughly 80 % of the course done, for showing the Home and
Progress pages with real-looking data. Everything goes through the app's own code, so the numbers are consistent:
practice problems are generated and marked by the OS Engine and the error analysis (with a few typical mistakes and
retries), mastery comes from Bayesian knowledge tracing, Explain-it-back is scored by the keyword rubric, and the
chats are answered by the chat agent (language model off). Activity is dated over the last 14 days.

    python -m eval.demo_profile                    → the student "Akshat" in data/
    python -m eval.demo_profile --name Akshat --reset     (remove that student's data first)
    python -m eval.demo_profile --remove           → remove the student again
"""
from __future__ import annotations

import argparse
import random
import shutil
import sys
import time
import uuid

import config
from engine import bankers, scheduling, semaphore
from engine.generator import generate_bankers, generate_scheduling, generate_semaphore
from tutor import lessons as L
from tutor import note_store
from tutor import teachback as TB
from tutor.chat_store import _dir as chat_dir
from tutor.error_analysis import analyse_bankers, analyse_scheduling, analyse_semaphore
from tutor.student_model import StudentModel

DAY = 86400
_clock = [time.time()]
_real_time = time.time


def at(days_ago: float, hour: float) -> None:
    """Set the simulated clock: `days_ago` days back, at `hour` o'clock (local time)."""
    t = time.localtime(_real_time() - days_ago * DAY)
    _clock[0] = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, int(hour), int(hour % 1 * 60), 0, 0, 0, -1))


def tick(minutes: float) -> None:
    _clock[0] += minutes * 60


# ---------------------------------------------------------------------------- answers, right and wrong
def _chart(res) -> list:
    return [(s.pid, s.start, s.end) for s in res.gantt if s.pid != "IDLE"]


def _metrics(res, wt_is_tat: bool = False, tat_is_ct: bool = False) -> dict:
    out = {}
    for pid, r in res.results.items():
        tat = r.completion if tat_is_ct else r.turnaround
        out[pid] = {"CT": r.completion, "TAT": tat, "WT": tat if wt_is_tat else tat - r.burst}
    return out


WRONG_SCHEDULE = {"SJF": lambda p: scheduling.fcfs(p.processes), "SRTF": lambda p: scheduling.sjf(p.processes),
                  "RR": lambda p: scheduling.round_robin(p.processes, p.quantum, new_arrivals_first=False),
                  "PRIORITY_P": lambda p: scheduling.priority_np(p.processes),
                  "PRIORITY_NP": lambda p: scheduling.fcfs(p.processes)}


def scheduling_answer(problem, mistake: str | None) -> dict:
    """mistake: None, "formula" (WT = TAT), "arrival" (TAT = CT) or "order" (the typical wrong schedule)."""
    res = problem.solve()
    if mistake == "order" and problem.algorithm in WRONG_SCHEDULE:
        wrong = WRONG_SCHEDULE[problem.algorithm](problem)
        return {"gantt": _chart(wrong), "metrics": _metrics(wrong)}
    return {"gantt": _chart(res), "metrics": _metrics(res, wt_is_tat=mistake == "formula", tat_is_ct=mistake == "arrival")}


def mark(kind: str, problem, mistake: str | None) -> dict:
    if kind == "scheduling":
        a = scheduling_answer(problem, mistake)
        return analyse_scheduling(problem, a["gantt"], a["metrics"])
    if kind == "bankers":
        s = bankers.safety(problem.available, problem.maximum, problem.allocation)
        seq = list(s["sequence"])
        if mistake and len(seq) > 1:
            seq = seq[::-1]                         # the order of the table instead of what fits in Work
        return analyse_bankers(problem, s["need"], s["safe"], seq if s["safe"] else None)
    t = semaphore.trace(problem.initial, problem.ops)
    final = dict(t["final_values"])
    if mistake:
        k = next(iter(final))
        final[k] += 1                               # forgot that a blocking wait still decrements the value
    return analyse_semaphore(problem, final, [] if mistake else t["blocked"])


def make_problem(topic: str, difficulty: int, rng: random.Random, mistake: str | None):
    """A generated problem on which the planned mistake really is wrong (and the right answer really is right)."""
    for _ in range(60):
        seed = rng.randrange(10 ** 6)
        if topic == "BANKERS":
            p, kind = generate_bankers(difficulty, seed), "bankers"
        elif topic == "SEMAPHORE":
            p, kind = generate_semaphore(difficulty, seed), "semaphore"
        else:
            p, kind = generate_scheduling(topic, difficulty, seed), "scheduling"
        if mark(kind, p, None)["correct"] and (mistake is None or not mark(kind, p, mistake)["correct"]):
            return p, kind
    raise RuntimeError(f"no {topic} problem where '{mistake}' is wrong")


def practise(students, sid, rng, topic, difficulty, tries, hints=0):
    """tries: the mistake made on each submission; None means solved (a list without None was left unsolved).
    hints: asked before the first submission."""
    problem, kind = make_problem(topic, difficulty, rng, next((m for m in tries if m), None))
    pid = f"practice:{uuid.uuid4().hex[:10]}"
    for n, mistake in enumerate(tries, 1):
        tick(rng.uniform(2.5, 7))
        analysis = mark(kind, problem, mistake)
        students.record_attempt(sid, problem.to_dict(), pid, analysis, n, hints if n == 1 else hints + n - 1, False,
                                rng.uniform(90, 420))


# ---------------------------------------------------------------------------- the two weeks
# (days ago, hour, lessons finished that day, practice: (topic, difficulty, submissions, hints))
PLAN = [
    (14, 18.5, ["basics"], [("FCFS", 1, ["formula", None], 0), ("FCFS", 1, [None], 0)]),
    (13, 19.0, ["fcfs"], [("FCFS", 2, [None], 0), ("FCFS", 2, [None], 0)]),
    (12, 17.5, ["sjf"], [("SJF", 1, ["order", None], 1), ("SJF", 2, [None], 0), ("SJF", 2, [None], 0)]),
    (11, 20.0, ["srtf"], [("SRTF", 1, ["order", None], 0), ("SRTF", 2, [None], 0), ("SRTF", 2, [None], 0)]),
    (10, 18.0, [], [("SRTF", 2, [None], 0), ("FCFS", 3, [None], 0)]),
    (9, 19.5, ["rr"], [("RR", 1, ["order", None], 1), ("RR", 2, [None], 0), ("RR", 2, ["formula", None], 0)]),
    (8, 18.0, [], [("RR", 2, ["order", None], 0), ("RR", 3, ["order", "order"], 1)]),     # a hard one left unsolved
    (7, 17.0, ["priority"], [("PRIORITY_NP", 1, [None], 0), ("PRIORITY_P", 2, ["order", None], 1),
                             ("PRIORITY_P", 2, [None], 0)]),
    (6, 19.0, ["critical_section"], []),
    (5, 18.5, ["semaphores"], [("SEMAPHORE", 1, [None], 0), ("SEMAPHORE", 2, ["wrong", None], 0)]),
    (4, 20.0, ["bounded_buffer"], [("SEMAPHORE", 2, [None], 0), ("RR", 2, [None], 0), ("PRIORITY_P", 2, [None], 0)]),
    (3, 17.5, [], [("BANKERS", 1, ["wrong", None], 0), ("SRTF", 3, ["order", None], 0)]),
    (2, 18.0, ["readers_writers"], [("PRIORITY_P", 3, ["order", None], 0), ("SJF", 3, ["arrival", None], 0)]),
    (1, 19.0, [], [("SEMAPHORE", 3, [None], 0), ("BANKERS", 2, [None], 0)]),
]
IN_PROGRESS = ("dining", 2, 1)                     # (lesson, stage reached, days ago)
SKIP_IDEA = {"rr": "q_size", "srtf": -1, "bounded_buffer": -1}   # an idea left out when explaining (-1: the last one)
EXPLAINED = ["basics", "fcfs", "sjf", "srtf", "rr", "priority", "semaphores", "bounded_buffer", "readers_writers"]
QUIZ_SCORE = {"basics": 1.0, "fcfs": 1.0, "sjf": 0.67, "srtf": 1.0, "rr": 0.67, "priority": 1.0,
              "critical_section": 0.67, "semaphores": 1.0, "bounded_buffer": 0.67, "readers_writers": 1.0}

NOTES = [
    {"title": "Formulas", "color": "butter", "pinned": True,
     "text": "- CT = when it finishes\n- TAT = CT − AT\n- WT = TAT − BT\n- RT = first run − AT"},
    {"title": "Round Robin queue rule", "color": "sky", "source": "Saved from the chat",
     "text": "If a slice ends at the same moment a process arrives, the **new arrival joins the queue first**, then "
             "the preempted process."},
    {"title": "SRTF tie", "color": "peach",
     "text": "Preempt only when the newcomer is **strictly** shorter. On a tie the running process carries on."},
    {"title": "Semaphore vs mutex", "color": "lilac", "source": "Saved from the chat",
     "text": "A mutex is a lock with an owner (0 or 1). A counting semaphore counts free resources, and any process "
             "may signal it."},
    {"title": "Producer–consumer order", "color": "mint",
     "text": "`wait(empty)` before `wait(mutex)`. The other way round deadlocks when the buffer is full."},
]
CHATS = [
    (11, 21.0, ["Solve using SRTF: P1 arrives at 0 with burst 7, P2 at 2 with burst 4, P3 at 4 with burst 1, "
                "P4 at 5 with burst 4", "What is the convoy effect?"]),
    (5, 20.0, ["What is the difference between a semaphore and a mutex?", "Quiz me on semaphores", "a", "b", "c"]),
]


def explanation(lesson: dict, skip: str | int | None) -> str:
    if skip == -1:
        skip = lesson["ideas"][-1]["id"]
    said = [i["statement"] for i in lesson["ideas"] if i["id"] != skip]
    return "So, " + lesson["title"] + ". " + " ".join(said) + " That is the main idea, I think."


def remove(students: StudentModel, sid: str) -> None:
    students.reset(sid)
    shutil.rmtree(chat_dir(sid), ignore_errors=True)
    nf = note_store._file(sid)
    if nf.exists():
        nf.unlink()


def build(sid: str, seed: int = 7) -> StudentModel:
    time.time = lambda: _clock[0]                   # every record is stamped with the simulated date
    try:
        rng = random.Random(seed)
        students = StudentModel()
        from rag.store import KnowledgeBase
        from tutor.chat_agent import ChatAgent
        from tutor.chat_store import new_chat, save_chat
        kb = KnowledgeBase()
        kb.load_or_build()
        for days, hour, done, practice in PLAN:
            at(days, hour)
            for lid in done:
                lesson = L.LESSON_BY_ID[lid]
                students.update_lesson(sid, lid, stage=1)
                tick(rng.uniform(8, 14))
                if lid in EXPLAINED:
                    a = TB.assess(lesson, explanation(lesson, SKIP_IDEA.get(lid)), None)
                    students.record_teachback(sid, lid, explanation(lesson, SKIP_IDEA.get(lid)), a)
                    tick(4)
                students.update_lesson(sid, lid, stage=4, completed=1, check_score=QUIZ_SCORE.get(lid))   # at Pointers
            for topic, difficulty, tries, hints in practice:
                practise(students, sid, rng, topic, difficulty, tries, hints)
            for d, h, msgs in CHATS:
                if d == days:
                    at(d, h)
                    state = new_chat(sid)
                    agent = ChatAgent(students, kb, None, use_llm=False)
                    state["messages"].append(agent.welcome(state))
                    for m in msgs:
                        tick(1.5)
                        reply = agent.respond(state, m)
                        agent.commit(state, reply)
                    save_chat(state)
        lid, stage, days = IN_PROGRESS
        at(days, 20.5)
        students.update_lesson(sid, lid, stage=stage)
        for k, n in enumerate(NOTES):
            at(12 - 2 * k, 21.5)
            made = note_store.add_note(sid, n["text"], n["title"], n["color"], n.get("source", ""))
            if n.get("pinned"):
                note_store.update_note(sid, made["id"], pinned=True)
        return students
    finally:
        time.time = _real_time


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default="Akshat", help="the student's name, exactly as typed in the sidebar")
    ap.add_argument("--reset", action="store_true", help="remove this student's existing data first")
    ap.add_argument("--remove", action="store_true", help="only remove this student's data")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    students = StudentModel()
    if a.remove:
        remove(students, a.name)
        print(f"Removed {a.name}.")
        return
    if students.history(a.name, 1) or students.lesson_progress(a.name):
        if not a.reset:
            raise SystemExit(f"{a.name} already has data. Use --reset to replace it, or another --name.")
        remove(students, a.name)
    students = build(a.name)
    from server import progress
    d = progress.dashboard(students, a.name)
    s = d["summary"]
    tried = [k for g in d["groups"] for k in g["skills"] if k["tried"]]
    avg = sum(k["p"] for k in tried) / len(tried)
    print(f"{a.name}: {s['lessons_done']}/{s['lessons_total']} lessons, mastery {avg:.0%} over {len(tried)} skills, "
          f"{s['solved']} of {s['problems']} problems solved, first try {s['first_try']:.0%}, "
          f"{s['teachbacks']} explained back, {len(note_store.list_notes(a.name))} notes")
    for g in d["groups"]:
        print("  " + g["name"] + ": " + ", ".join(f"{k['name']} {k['p']:.2f}" for k in g["skills"]))
    print("  next:", d["next"]["reason"])
    print(f"Data in {config.DB_PATH}, {chat_dir(a.name)} and {note_store._file(a.name)}")


if __name__ == "__main__":
    main()
