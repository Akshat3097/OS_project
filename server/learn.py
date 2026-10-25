"""
Learn mode for the web page: the lessons of tutor/lessons.py turned into plain JSON.

Every step of a worked example (the Gantt chart so far, the ready queue, the reason for each choice) and every
"Try it" problem is computed here by the OS Engine, so the page only reveals data, it never calculates.
The teach-back state (what the student explained, the questions asked) lives on the server in TeachbackSessions.
"""
from __future__ import annotations

import random
import threading

from engine import bankers, generator, scheduling
from engine.generator import SchedulingProblem
from engine.scheduling import ALGORITHMS
from server.cards import gantt, table
from tutor import lessons as L
from tutor import teachback as TB

SHORT = {"basics": "Scheduling basics", "fcfs": "FCFS", "sjf": "SJF", "srtf": "SRTF", "rr": "Round Robin",
         "priority": "Priority", "critical_section": "Critical section", "semaphores": "Semaphores",
         "bounded_buffer": "Producer–consumer", "readers_writers": "Readers–writers", "dining": "Dining philosophers",
         "deadlock": "Deadlocks", "bankers": "Banker's algorithm"}
TOPIC_TO_LESSON = {"FCFS": "fcfs", "SJF": "sjf", "SRTF": "srtf", "RR": "rr", "PRIORITY_NP": "priority",
                   "PRIORITY_P": "priority", "SEMAPHORE": "semaphores", "BANKERS": "bankers",
                   "CT_READING": "basics", "TAT_FORMULA": "basics", "WT_FORMULA": "basics",
                   "BANKERS_NEED": "bankers", "BANKERS_SAFETY": "bankers"}
PROMPTS = ["What is this topic about, in one sentence?", "What exactly is the rule? How does it decide?",
           "Give an example, from real life or a small problem.", "What is a common mistake or trap?"]


# ============================================================================ the lesson list
def recommended(progress: dict, recurring: list[dict]) -> str:
    for r in recurring:
        lid = TOPIC_TO_LESSON.get(r.get("skill") or "") or TOPIC_TO_LESSON.get(r.get("topic") or "")
        if lid:
            return lid
    return next((lid for lid in L.ORDER if not progress.get(lid, {}).get("completed")), L.ORDER[0])


def lesson_list(progress: dict, recurring: list[dict]) -> dict:
    rec = recommended(progress, recurring)
    items = []
    for l in L.LESSONS:
        p = progress.get(l["id"], {})
        items.append({"id": l["id"], "group": l["group"], "title": l["title"], "short": SHORT.get(l["id"], l["title"]),
                      "minutes": l["minutes"], "goal": l["goal"], "completed": bool(p.get("completed")),
                      "started": bool(p), "stage": int(p.get("stage") or 0)})
    return {"lessons": items, "recommended": rec, "stages": L.STAGES}


# ============================================================================ helpers
def _process_table(problem) -> dict:
    pri = problem.algorithm in scheduling.USES_PRIORITY
    return table(["Process", "Arrival (AT)", "Burst (BT)"] + (["Priority"] if pri else []),
                 [[p.pid, p.arrival, p.burst] + ([p.priority] if pri else []) for p in problem.processes])


def _ready_table(ready: list[dict], algorithm: str) -> dict:
    pre, pri = algorithm in scheduling.PREEMPTIVE, algorithm in scheduling.USES_PRIORITY
    rows = []
    for r in sorted(ready, key=lambda r: (len(r["pid"]), r["pid"])):   # fixed order, so the table never hints the answer
        rows.append([r["pid"], r["arrival"], r["burst"]] + ([r["remaining"]] if pre else []) + ([r["priority"]] if pri else []))
    return table(["Process", "Arrived", "Burst"] + (["Remaining"] if pre else []) + (["Priority"] if pri else []), rows)


def _title(problem) -> str:
    return ALGORITHMS[problem.algorithm] + (f", q = {problem.quantum}" if problem.quantum else "")


def _breakdown(res) -> list[str]:
    return L.results_breakdown(res)


def _vec(v) -> str:
    return " ".join(map(str, v))


def _scheduling_walk(problem, only_choices: bool = False) -> dict:
    """The schedule one decision at a time: the chart so far, who is ready, who gets the CPU and why."""
    res = problem.solve()
    order = [p.pid for p in problem.processes]
    steps = []
    for s in L.scheduling_steps(res):
        if only_choices and len(s["options"]) < 2:
            continue
        steps.append({"time": s["time"], "event": s["event"], "question": s["question"], "options": s["options"],
                      "answer": s["answer"], "reason": s["reason"], "queue": s["queue"],
                      "ready": _ready_table(s["ready"], problem.algorithm),
                      "gantt": gantt(L.gantt_until(res.gantt, s["time"]), order)})
    return {"title": _title(problem), "processes": _process_table(problem), "span": res.makespan,
            "order": order, "steps": steps, "final": gantt(res.gantt, order), "breakdown": _breakdown(res),
            "stats": [["Average TAT", f"{res.avg_tat:.2f}"], ["Average WT", f"{res.avg_wt:.2f}"]]}


def named_effect(effect: str, sem: str) -> str:
    """The engine's messages say "S"; name the semaphore this step used."""
    return (effect.replace("(S<0)", f"({sem} < 0)").replace("while (S <= 0); S stays 0", f"while ({sem} <= 0); {sem} stays 0")
            .replace("(S back to 0)", f"({sem} back to 0)"))


def semaphore_walk(initial: dict, ops: list[dict], notes: list[str] | None = None) -> dict:
    steps = L.semaphore_steps(initial, ops)
    notes = notes or []
    return {"initial": [[k, v] for k, v in initial.items()],
            "steps": [{"pid": s["pid"], "op": s["op"], "sem": s["sem"], "before": s["before"], "after": s["after"],
                       "effect": named_effect(s["effect"], s["sem"]), "queue": s["queue"], "value_options": s["value_options"],
                       "outcome": s["outcome"], "outcomes": s["outcomes"], "note": notes[k] if k < len(notes) else None}
                      for k, s in enumerate(steps)]}


def bankers_walk(available, maximum, allocation, resources) -> dict:
    out = bankers.safety(available, maximum, allocation)
    need = out["need"]
    procs = [f"P{k}" for k in range(len(maximum))]
    steps, finished, work = [], [], list(available)
    for s in out["steps"]:
        checks = [{"pid": p, "need": _vec(need[int(p[1:])]),
                   "ok": all(a <= b for a, b in zip(need[int(p[1:])], work))} for p in procs if p not in finished]
        steps.append({"work": _vec(work), "finished": list(finished), "checks": checks, "chosen": s["process"],
                      "released": _vec(s["allocation_released"]), "work_after": _vec(s["work_after"])})
        finished.append(s["process"])
        work = s["work_after"]
    return {"resources": resources, "available": _vec(available),
            "tables": [{"label": "Allocation", **table(["", *resources], [[p, *r] for p, r in zip(procs, allocation)])},
                       {"label": "Max", **table(["", *resources], [[p, *r] for p, r in zip(procs, maximum)])},
                       {"label": "Need = Max − Allocation", **table(["", *resources], [[p, *r] for p, r in zip(procs, need)])}],
            "steps": steps, "safe": out["safe"], "sequence": out["sequence"], "stuck": out["stuck"],
            "final_work": _vec(work)}


# ============================================================================ one lesson
def watch_view(lesson: dict) -> dict:
    w = lesson["watch"]
    base = {"kind": w["kind"], "intro": w.get("intro", "")}
    if w["kind"] == "scheduling":
        return {**base, **_scheduling_walk(SchedulingProblem(w["algorithm"], 1, w["processes"], w.get("quantum")))}
    if w["kind"] == "semaphore":
        return {**base, **semaphore_walk(w["initial"], w["ops"], w.get("notes"))}
    if w["kind"] == "bankers":
        return {**base, **bankers_walk(w["available"], w["maximum"], w["allocation"], w["resources"])}
    return {**base, "slides": [{"title": t, "body": b} for t, b in w["slides"]]}


def lesson_view(lesson: dict, progress: dict | None = None) -> dict:
    p = progress or {}
    return {"id": lesson["id"], "title": lesson["title"], "group": lesson["group"], "goal": lesson["goal"],
            "minutes": lesson["minutes"], "analogy": lesson["analogy"], "real_life": lesson.get("real_life", []),
            "concept": lesson["concept"].strip(), "summary": lesson["summary"], "stages": L.STAGES,
            "watch": watch_view(lesson),
            "mcq": [{"q": q["q"], "options": [{"text": t, "ok": ok, "why": why} for t, ok, why in q["options"]]}
                    for q in lesson["mcq"][:3]],
            "has_try": bool(lesson.get("try")), "try_intro": (lesson.get("try") or {}).get("intro"),
            "practice_topic": lesson.get("practice_topic"), "prompts": PROMPTS,
            "next": _next_id(lesson["id"]), "stage": int(p.get("stage") or 0), "completed": bool(p.get("completed")),
            "number": L.ORDER.index(lesson["id"]) + 1, "of": len(L.ORDER)}


def _next_id(lid: str) -> str | None:
    i = L.ORDER.index(lid) + 1
    return L.ORDER[i] if i < len(L.ORDER) else None


# ============================================================================ "Try it": guided practice
def try_view(lesson: dict, seed: int | None = None) -> dict | None:
    t = lesson.get("try")
    if not t:
        return None
    seed = seed if seed is not None else random.randrange(10**9)
    if t["kind"] == "predict":
        prob = generator.generate_scheduling(t["algorithm"], t["difficulty"], seed)
        return {"kind": "predict", "intro": t["intro"], **_scheduling_walk(prob, only_choices=True)}
    if t["kind"] == "metrics":
        prob = SchedulingProblem(t["algorithm"], 1, t["processes"])
        walk = _scheduling_walk(prob)
        return {"kind": "metrics", "intro": t["intro"], "title": walk["title"], "processes": walk["processes"],
                "final": walk["final"], "pids": walk["order"], "problem": prob.to_dict()}
    if t["kind"] == "semaphore":
        prob = generator.generate_semaphore(t["difficulty"], seed)
        return {"kind": "semaphore", "intro": t["intro"], **semaphore_walk(prob.initial, prob.ops)}
    prob = generator.generate_bankers(t["difficulty"], seed)
    need = bankers.compute_need(prob.maximum, prob.allocation)
    procs = [f"P{k}" for k in range(len(prob.maximum))]
    return {"kind": "bankers", "intro": t.get("intro", "Build a safe sequence one process at a time."),
            "resources": prob.resources, "procs": procs, "available": prob.available,
            "allocation": prob.allocation, "need": need,
            "tables": [{"label": "Allocation", **table(["", *prob.resources], [[p, *r] for p, r in zip(procs, prob.allocation)])},
                       {"label": "Need", **table(["", *prob.resources], [[p, *r] for p, r in zip(procs, need)])}]}


def check_metrics(problem_dict: dict, metrics: dict) -> dict:
    """The 'basics' Try it: the student fills CT, TAT and WT for a finished chart; the error analysis marks each cell."""
    from tutor.error_analysis import analyse_scheduling
    prob = generator.problem_from_dict(problem_dict)
    res = prob.solve()
    a = analyse_scheduling(prob, [(s.pid, s.start, s.end) for s in res.gantt], metrics)
    errors = []
    for e in a["errors"]:
        if e["type"] == "missing_value":
            errors.append("Some cells are empty.")
            continue
        pids = ", ".join(sorted({d.get("pid") for d in e["details"] if d.get("pid")}))
        errors.append(f"**{e['label']}** ({pids}). {e.get('misconception') or ''}".strip())
    return {"correct": bool(a["correct"]), "cells": a["cells"], "errors": errors,
            "breakdown": _breakdown(res) if a["correct"] else None}


# ============================================================================ explain it back → question → pointers
def question_view(q: dict) -> dict:
    """A teach-back question as the page shows it, without the answer."""
    if q["kind"] == "mcq":
        return {"kind": "mcq", "prompt": q["q"], "options": [o[0] for o in q["options"]]}
    prob = generator.problem_from_dict(q["problem"])
    if q["kind"] in ("decision", "metric"):
        res = prob.solve()
        order = [p.pid for p in prob.processes]
        base = {"title": _title(prob), "processes": _process_table(prob), "span": res.makespan, "order": order}
        if q["kind"] == "decision":
            s = L.scheduling_steps(res)[q["step"]]
            return {"kind": "decision", **base, "gantt": gantt(L.gantt_until(res.gantt, s["time"]), order),
                    "prompt": f"{s['event']} {s['question']}", "ready": _ready_table(s["ready"], prob.algorithm),
                    "options": s["options"]}
        return {"kind": "metric", **base, "gantt": gantt(res.gantt, order),
                "prompt": f"What is the {q['field']} of {q['pid']}?"}
    if q["kind"] == "semaphore":
        steps = L.semaphore_steps(prob.initial, prob.ops)
        k = q["step"]
        s = steps[k]
        return {"kind": "semaphore", "initial": [[a, b] for a, b in prob.initial.items()],
                "done": [{"pid": x["pid"], "op": x["op"], "sem": x["sem"], "after": x["after"],
                          "queue": x["queue"]} for x in steps[:k]],
                "prompt": f"Step {k + 1}: {s['pid']} calls {s['op']}({s['sem']}). What is the new value, and what happens?",
                "value_options": s["value_options"], "outcomes": s["outcomes"]}
    procs = [f"P{i}" for i in range(len(prob.maximum))]
    return {"kind": "bankers", "available": _vec(prob.available), "resources": prob.resources,
            "tables": [{"label": "Allocation", **table(["", *prob.resources], [[p, *r] for p, r in zip(procs, prob.allocation)])},
                       {"label": "Max", **table(["", *prob.resources], [[p, *r] for p, r in zip(procs, prob.maximum)])}],
            "prompt": "Which process can finish FIRST in a safe sequence? Work out Need yourself.", "options": procs}


def assessment_view(lesson: dict, a: dict) -> dict:
    by_id = {i["id"]: i for i in lesson["ideas"]}
    mis = [m["text"] for m in lesson["misconceptions"] if m["id"] in a.get("misconceptions", [])]
    quotes = a.get("evidence") or {}
    return {"ideas": [{"id": k, "statement": by_id[k]["statement"], "rating": v,
                       "evidence": quotes.get(k) if v != "missing" else None} for k, v in a["ideas"].items()],
            "clear": sum(v == "clear" for v in a["ideas"].values()), "total": len(a["ideas"]),
            "did_well": a.get("did_well") or "", "gap": a.get("gap") or "", "misconceptions": mis,
            "source": a.get("source", ""), "words": a.get("words", 0), "score": a.get("score", 0)}


class TeachbackSessions:
    """What each student explained per lesson and the questions asked since (kept in memory; a restart starts over)."""

    MAX_QUESTIONS = 3

    def __init__(self):
        self._data: dict[tuple[str, str], dict] = {}
        self._lock = threading.Lock()

    def get(self, sid: str, lid: str) -> dict | None:
        with self._lock:
            return self._data.get((sid, lid))

    def start(self, sid: str, lid: str, transcript: str, assessment: dict, row: int | None) -> dict:
        tb = {"transcript": transcript, "assessment": assessment, "row": row, "questions": [], "current": None}
        with self._lock:
            self._data[(sid, lid)] = tb
        return tb

    def skip(self, sid: str, lesson: dict) -> dict:
        a = {"ideas": {i["id"]: "missing" for i in lesson["ideas"]}, "misconceptions": [], "source": "skipped",
             "words": 0, "score": 0.0}
        return self.start(sid, lesson["id"], "", a, None)

    def next_question(self, sid: str, lesson: dict) -> dict:
        tb = self.get(sid, lesson["id"]) or self.skip(sid, lesson)
        cur = tb["current"]
        if cur is not None and cur.get("result") is None:
            return self._question_out(lesson, tb, cur)            # same question again (page reloaded)
        if cur is not None:
            tb["questions"].append(cur)
        asked = [q["q"]["idea"] for q in tb["questions"]]
        idea, why = TB.target_idea(lesson, tb["assessment"], asked)
        tb["current"] = {"q": TB.make_question(lesson, idea), "why": why, "result": None}
        return self._question_out(lesson, tb, tb["current"])

    def _question_out(self, lesson: dict, tb: dict, cur: dict) -> dict:
        idea = next(i for i in lesson["ideas"] if i["id"] == cur["q"]["idea"])
        return {"question": question_view(cur["q"]), "why": cur["why"],
                "rating": tb["assessment"]["ideas"][idea["id"]], "number": len(tb["questions"]) + 1,
                "explained": tb["assessment"].get("source") != "skipped"}

    def answer(self, sid: str, lesson: dict, answer) -> dict:
        tb = self.get(sid, lesson["id"])
        if not tb or not tb.get("current"):
            raise LookupError("no open question")
        cur = tb["current"]
        if cur["result"] is None:
            view = question_view(cur["q"])
            if "options" in view and answer not in view["options"]:
                raise ValueError("that is not one of the options")
            if view["kind"] == "semaphore" and not (isinstance(answer, list) and len(answer) == 2
                                                    and answer[0] in view["value_options"] and answer[1] in view["outcomes"]):
                raise ValueError("choose a value and what happens")
            if view["kind"] == "metric" and (isinstance(answer, bool) or not isinstance(answer, (int, float))):
                raise ValueError("type a number")
            try:
                cur["result"] = TB.check_answer(cur["q"], answer)
            except (StopIteration, ValueError, TypeError, IndexError):
                raise ValueError("that is not one of the options") from None
            cur["answer"] = answer
        idea = next(i for i in lesson["ideas"] if i["id"] == cur["q"]["idea"])
        return {**cur["result"], "idea": idea["statement"],
                "more": len(tb["questions"]) + 1 < self.MAX_QUESTIONS}

    def results(self, tb: dict) -> list[dict]:
        out = []
        for q in tb["questions"] + ([tb["current"]] if tb.get("current") and tb["current"].get("result") else []):
            out.append({"idea": q["q"]["idea"], "ok": q["result"]["ok"], "explanation": q["result"]["explanation"],
                        "correct": q["result"]["correct"]})
        return out


def pointers_view(lesson: dict, tb: dict, results: list[dict]) -> dict:
    p = TB.pointers(lesson, tb["assessment"], results)
    return {"verdict": p["verdict"], "next": p["next"], "clear": p["clear"], "add": p["partial"] + p["missing"],
            "misconceptions": p["misconceptions"], "questions": [{"ok": r["ok"], "text": r["explanation"]} for r in results],
            "summary": lesson["summary"], "practice_topic": lesson.get("practice_topic"),
            "explained": tb["assessment"].get("source") != "skipped"}


def notes_view(notes: list[dict]) -> list[dict]:
    out = []
    for n in notes:
        body = n["text"].split(": ", 1)[1] if ": " in n["text"] else n["text"]
        out.append({"section": n["meta"].get("section", ""), "source": n["meta"].get("source", ""),
                    "text": body[:1200] + ("…" if len(body) > 1200 else "")})
    return out
