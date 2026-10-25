"""
Turn the agent's cards (which only name a problem, an answer or a lesson) into plain JSON the React page can draw:
Gantt segments and tables with every number computed by the OS Engine here, on the server.
"""
from __future__ import annotations

import math

from engine import bankers, deadlock, question_bank, scheduling, semaphore
from engine.advanced import performance
from engine.generator import problem_from_dict
from engine.scheduling import ALGORITHMS, IDLE
from tutor.chat_agent import LESSON

STATUS_ICON = {"correct": "✅", "consistent": "↪️", "wrong": "❌", "missing": "—"}


def _num(v):
    if isinstance(v, float):
        if math.isnan(v):
            return None
        return int(v) if v.is_integer() else round(v, 2)
    return v


def table(columns: list[str], rows: list[list]) -> dict:
    return {"columns": columns, "rows": [[_num(x) for x in r] for r in rows]}


def gantt(segments, order: list[str] | None = None, highlight: int | None = None, title: str | None = None) -> dict:
    segs = [[s.pid, _num(s.start), _num(s.end)] if hasattr(s, "pid") else [s[0], _num(s[1]), _num(s[2])] for s in segments]
    if order is None:
        order = []
        for pid, _, _ in segs:
            if pid != IDLE and pid not in order:
                order.append(pid)
    return {"segments": segs, "order": order, "highlight": highlight, "title": title}


def _pids(problem) -> list[str]:
    return [j.pid for j in problem.jobs] if problem.kind == "advanced" else [p.pid for p in problem.processes]


def _sched_results(res) -> dict:
    return table(["Process", "AT", "BT", "CT", "TAT", "WT", "RT"],
                 [[r.pid, r.arrival, r.burst, r.completion, r.turnaround, r.waiting, r.response] for r in res.results.values()])


def _decisions(res) -> dict:
    return table(["t", "Ready (remaining)", "Chosen", "Why"],
                 [[d.time, ", ".join(f"{r['pid']} ({r['remaining']})" for r in d.ready) or "—", d.chosen, d.reason]
                  for d in res.decisions])


def _matrix(m, resources, first=0) -> dict:
    return table(["", *resources], [[f"P{i + first}", *row] for i, row in enumerate(m)])


def _sem_steps(eng) -> dict:
    return table(["Step", "Process", "Operation", "Before", "After", "What happens"],
                 [[s["step"], s["pid"], f"{s['op']}({s['sem']})", s["value_before"], s["value_after"], s["effect"]]
                  for s in eng["steps"]])


# ============================================================================ card types
def problem_card(card: dict) -> dict:
    problem = problem_from_dict(card["problem"])
    item = card.get("bank_item")
    out = {"type": "problem", "kind": problem.kind, "bank": None, "tables": []}
    if item:
        out["bank"] = {"source": item.get("paper", item.get("source", "")), "question": item.get("question", ""),
                       "marks": item.get("marks"), "text": item.get("text", "")}
    if problem.kind == "scheduling":
        pri = problem.algorithm in scheduling.USES_PRIORITY
        out["title"] = ALGORITHMS[problem.algorithm] + (f", q = {problem.quantum}" if problem.algorithm == "RR" else "")
        out["tables"].append(table(["Process", "Arrival (AT)", "Burst (BT)"] + (["Priority"] if pri else []),
                                   [[p.pid, p.arrival, p.burst] + ([p.priority] if pri else []) for p in problem.processes]))
        conv = "Ties go to the earlier arrival."
        if pri:
            conv += " Lower number = higher priority."
        if problem.algorithm in ("SRTF", "PRIORITY_P"):
            conv += " Preempt only if strictly better."
        if problem.algorithm == "RR":
            conv += " A process arriving when a slice ends joins the queue before the preempted one."
        out["caption"] = conv
    elif problem.kind == "advanced":
        out["title"] = problem.label
        out["statement"] = None if item else problem.statement()
        out["tables"].append(table(["Process", "AT", "Priority", "Bursts"],
                                   [[j.pid, j.arrival, j.priority, " → ".join(f"{k} {v:g}" for k, v in j.bursts)]
                                    for j in problem.jobs]))
    elif problem.kind == "bankers":
        out["title"] = "Banker's algorithm"
        out["tables"] = [{"label": "Allocation", **_matrix(problem.allocation, problem.resources)},
                         {"label": "Max", **_matrix(problem.maximum, problem.resources)},
                         {"label": "Available", **table(problem.resources, [problem.available])}]
        out["caption"] = "Is the system in a safe state? If it is, give a safe sequence."
    else:
        out["title"] = "Semaphores"
        out["statement"] = problem.statement()
    return out


def solution_card(card: dict) -> dict:
    problem = problem_from_dict(card["problem"])
    out = {"type": "solution", "kind": problem.kind, "tables": []}
    if problem.kind == "scheduling":
        res = problem.solve()
        pf = performance(res.gantt, len(problem.processes))
        out["gantt"] = gantt(res.gantt, _pids(problem))
        out["tables"].append(_sched_results(res))
        out["stats"] = [["Average TAT", f"{res.avg_tat:.2f}"], ["Average WT", f"{res.avg_wt:.2f}"],
                        ["Average RT", f"{res.avg_rt:.2f}"], ["CPU utilisation", f"{pf['cpu_utilization']:g}%"],
                        ["Context switches", str(pf["context_switches"])]]
        out["details"] = {"label": "Every decision, step by step", **_decisions(res)}
    elif problem.kind == "advanced":
        res = problem.solve()
        out["gantt"] = gantt(res.gantt, _pids(problem))
        out["tables"].append(table(["Process", "AT", "CPU", "I/O", "CT", "TAT", "WT", "WT (I/O as waiting)", "RT"],
                                   [[r.pid, r.arrival, r.cpu, r.io, r.completion, r.turnaround, r.waiting, r.waiting_incl_io,
                                     r.response] for r in res.results.values()]))
        out["stats"] = [["Average TAT", f"{res.avg('turnaround'):.2f}"], ["Average WT", f"{res.avg('waiting'):.2f}"]]
        if problem.has_io():
            out["caption"] = (f"Counting I/O as waiting, as the Module 3 notes do, the average WT is "
                              f"{res.avg('waiting_incl_io'):.2f}.")
    elif problem.kind == "bankers":
        eng = problem.solve()
        out["tables"].append({"label": "Need = Max − Allocation", **_matrix(eng["need"], problem.resources)})
        out["verdict"] = ("✅ **Safe**: sequence " + " → ".join(eng["sequence"])) if eng["safe"] else \
            f"⛔ **Unsafe**: {', '.join(eng['stuck'])} can never finish"
        if eng["steps"]:
            out["details"] = {"label": "Every step of the safety algorithm",
                              **table(["Step", "Process", "Need", "Work before", "+ Allocation", "Work after"],
                                      [[s["step"], s["process"], _fmt(s["need"]), _fmt(s["work_before"]),
                                        _fmt(s["allocation_released"]), _fmt(s["work_after"])] for s in eng["steps"]])}
    else:
        eng = problem.solve()
        busy = {k: max(0, v) for k, v in eng["final_values"].items()}
        out["tables"].append(_sem_steps(eng))
        vals = ", ".join(f"{k} = {v}" for k, v in eng["final_values"].items())
        out["caption"] = (f"Final values: {vals} (blocking definition)."
                          + (" With the busy-waiting P/V from the Module 4 notes: "
                             + ", ".join(f"{k} = {v}" for k, v in busy.items()) + "." if busy != eng["final_values"] else "")
                          + f" Blocked at the end: {', '.join(eng['blocked']) or 'none'}.")
    item = card.get("bank_item")
    if item:
        chk = question_bank.check(item)
        off = item.get("official", {})
        out["key"] = {"items": [[k.replace("_", " "), str(v)] for k, v in off.items()],
                      "match": chk["match"], "notes": item.get("notes")}
    return out


def detection_card(card: dict) -> dict:
    """A pasted deadlock-detection question, solved; drawn by the page like any other solution card."""
    first = card.get("first_pid", 0)
    names = [f"P{first + k}" for k in range(len(card["allocation"]))]
    det = deadlock.detect(card["available"], card["allocation"], card["request"], names=names)
    res = list("ABCDE")[:len(card["available"])]
    out = {"type": "solution", "kind": "detection",
           "tables": [{"label": "Allocation", **table(["", *res], [[p, *r] for p, r in zip(names, card["allocation"])])},
                      {"label": "Request", **table(["", *res], [[p, *r] for p, r in zip(names, card["request"])])},
                      {"label": "Available", **table(res, [card["available"]])}],
           "verdict": (f"⛔ **Deadlock**: {', '.join(det['deadlocked'])} can never finish" if det["deadlock"] else
                       "✅ **No deadlock**: every process can finish, e.g. " + " → ".join(det["sequence"])),
           "caption": "Detection algorithm: Work = Available; a process with Request ≤ Work finishes and releases its "
                      "allocation; a process holding nothing starts as finished. Try it in Labs → Deadlocks."}
    if det["steps"]:
        out["details"] = {"label": "Every step of the detection algorithm",
                          **table(["Step", "Process", "Request", "Work before", "+ Allocation", "Work after"],
                                  [[s["step"], s["process"], _fmt(s["request"]), _fmt(s["work_before"]),
                                    _fmt(s["allocation_released"]), _fmt(s["work_after"])] for s in det["steps"]])}
    return out


def _fmt(v):
    if isinstance(v, (list, tuple)):
        return " ".join(str(x) for x in v)
    if isinstance(v, bool):
        return "yes" if v else "no"
    return v


def marked_card(card: dict) -> dict:
    problem = problem_from_dict(card["problem"])
    a = card["analysis"]
    ans = card.get("answer") or {}
    root = a.get("root_cause")
    out = {"type": "marked", "kind": problem.kind, "correct": bool(a.get("correct")),
           "headline": "Verified by the OS Engine" if a.get("correct") else
           (f"First thing to fix: {root['label']}" if root else "Your answer isn't complete yet"),
           "tables": [], "said": None}
    if problem.kind in ("scheduling", "advanced"):
        if problem.kind == "scheduling" and a.get("student_gantt"):
            hl = a["divergence"]["time"] if a.get("divergence") and not a.get("gantt_correct") else None
            out["gantt"] = gantt(a["student_gantt"], _pids(problem), hl, "Your Gantt chart")
        if a.get("cells") and (a.get("metrics_given") or problem.kind == "advanced"):
            metrics = ans.get("metrics") or {}
            rows = []
            for pid in _pids(problem):
                m = metrics.get(pid, {})
                row = [pid]
                for k in ("CT", "TAT", "WT"):
                    v = m.get(k)
                    stt = (a["cells"].get(pid) or {}).get(k, "missing")
                    row.append(f"{STATUS_ICON[stt]} {'' if v is None else _num(v)}".strip())
                rows.append(row)
            out["tables"].append(table(["Process", "CT", "TAT", "WT"], rows))
            out["legend"] = ["✅ right", "❌ wrong", "↪️ follows from an earlier value (your formula is fine)", "— missing"]
    elif problem.kind == "bankers":
        if ans.get("safe") is not None:
            out["said"] = f"You said {'safe' if ans['safe'] else 'unsafe'}" + \
                (f", sequence {' → '.join(ans['sequence'])}" if ans.get("sequence") else "")
        sc = a.get("sequence_check")
        if sc:
            out["legend"] = [("✅ " if sc["valid"] else "❌ ") + sc["message"]]
    elif problem.kind == "semaphore":
        out["said"] = "You said " + ", ".join(f"{k} = {v}" for k, v in (ans.get("final") or {}).items()) + \
            f"; blocked: {', '.join(ans.get('blocked') or []) or 'none'}"
    others = [e for e in a.get("errors", []) if e.get("type") != "missing_value"
              and not (root and e.get("label") == root.get("label"))]          # the headline already names it
    if others and not a.get("correct"):
        out["mistakes"] = [e["label"] + (f" ×{e['count']}" if (e.get("count") or 1) > 1 else "") for e in others]
    if card.get("changes"):
        out["mastery"] = [{"skill": k, "before": round(v[0], 3), "after": round(v[1], 3)} for k, v in card["changes"].items()]
    return out


def example_card(card: dict) -> dict:
    lesson = LESSON[card["lesson"]]
    w = lesson["watch"]
    out = {"type": "example", "intro": card.get("intro", ""), "tables": []}
    if w["kind"] == "scheduling":
        res = scheduling.run(w["algorithm"], w["processes"], w.get("quantum"))
        out["title"] = ALGORITHMS[w["algorithm"]] + (f", q = {w['quantum']}" if w.get("quantum") else "")
        out["gantt"] = gantt(res.gantt, [p.pid for p in w["processes"]])
        out["tables"].append(_sched_results(res))
        out["stats"] = [["Average TAT", f"{res.avg_tat:.2f}"], ["Average WT", f"{res.avg_wt:.2f}"]]
    elif w["kind"] == "bankers":
        eng = bankers.safety(w["available"], w["maximum"], w["allocation"])
        out["title"] = "Banker's algorithm"
        out["tables"] = [{"label": "Allocation", **_matrix(w["allocation"], w["resources"])},
                         {"label": "Max", **_matrix(w["maximum"], w["resources"])},
                         {"label": "Need", **_matrix(eng["need"], w["resources"])}]
        out["caption"] = f"Available: {' '.join(map(str, w['available']))}. " + \
            ("Safe sequence: " + " → ".join(eng["sequence"]) + "." if eng["safe"] else "The state is unsafe.")
    elif w["kind"] == "semaphore":
        eng = semaphore.trace(w["initial"], w["ops"])
        out["title"] = "Semaphore trace"
        out["tables"].append(_sem_steps(eng))
    return out


def hydrate(card: dict, active: bool = False) -> dict | None:
    t = card.get("type")
    try:
        if t == "problem":
            return problem_card(card)
        if t == "solution":
            return solution_card(card)
        if t == "marked":
            return marked_card(card)
        if t == "example":
            return example_card(card)
        if t == "detection":
            return detection_card(card)
        if t == "video":
            from tutor import videos
            clips = videos.clips_for(card["lesson"])
            return {"type": "video", "clips": clips} if clips else None
        if t == "progress":
            return {"type": "progress", "skills": card["skills"]}
        if t == "sources":
            return {"type": "sources", "title": card.get("title", "Sources"), "items": card["items"]}
        if t == "quiz":
            out = {"type": "quiz", "number": card["number"], "options": card["options"], "key": card["key"],
                   "active": active}
            out.update({k: card[k] for k in ("q", "of", "title", "picked", "answer", "grade") if k in card})
            return out
    except Exception as e:  # a card should never break the whole conversation
        return {"type": "error", "text": f"Could not draw this card ({type(e).__name__})."}
    return None


def form_spec(state: dict) -> dict | None:
    """The answer form for the open problem (None when there is nothing to answer)."""
    ps = state.get("problem")
    if not ps or ps.get("solved") or ps.get("revealed") or state.get("quiz") or state.get("teachback"):
        return None
    problem = problem_from_dict(ps["problem"])
    prev = ps.get("answer") or {}
    if problem.kind == "scheduling":
        return {"kind": "scheduling", "pids": _pids(problem), "rows": len(problem.processes) +
                (2 if problem.algorithm in scheduling.PREEMPTIVE else 0), "prev": prev, "key": ps["pid"]}
    if problem.kind == "advanced":
        return {"kind": "advanced", "pids": _pids(problem), "prev": prev, "key": ps["pid"]}
    if problem.kind == "bankers":
        return {"kind": "bankers", "pids": [f"P{i}" for i in range(len(problem.allocation))], "prev": prev, "key": ps["pid"]}
    return {"kind": "semaphore", "sems": list(problem.initial), "procs": sorted({o["pid"] for o in problem.ops}),
            "prev": prev, "key": ps["pid"]}
