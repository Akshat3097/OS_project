"""
Labs: the OS Engine to play with directly. Every number is computed here; the page only draws it.

  scheduler   one set of processes through all six algorithms, with the averages compared
  bankers     the safety algorithm step by step, and the resource-request algorithm
  semaphores  a sequence of wait/signal operations as a timeline, in both conventions (blocking and busy-waiting)
  deadlocks   a resource-allocation graph: its cycles, the wait-for graph and the detection algorithm
"""
from __future__ import annotations

import random

from engine import bankers, deadlock, generator, scheduling, semaphore
from engine.advanced import performance
from engine.scheduling import ALGORITHMS, Process
from server.cards import gantt, table
from server.learn import bankers_walk, named_effect
from tutor.chat_parse import parse_bankers_problem, parse_scheduling_problem

SHORT_NAMES = {"FCFS": "FCFS", "SJF": "SJF", "SRTF": "SRTF", "RR": "Round Robin", "PRIORITY_NP": "Priority (NP)",
               "PRIORITY_P": "Priority (P)"}

PRESETS = {
    "scheduler": [
        {"name": "Textbook (Silberschatz)", "quantum": 4,
         "processes": [["P1", 0, 8, 3], ["P2", 1, 4, 1], ["P3", 2, 9, 4], ["P4", 3, 5, 2]]},
        {"name": "Convoy effect", "quantum": 2,
         "processes": [["P1", 0, 12, 3], ["P2", 1, 2, 1], ["P3", 2, 1, 2], ["P4", 3, 2, 4]]},
        {"name": "Idle gap", "quantum": 3,
         "processes": [["P1", 0, 3, 2], ["P2", 6, 4, 1], ["P3", 7, 2, 3]]},
    ],
    "bankers": [
        {"name": "Textbook (safe)", "resources": ["A", "B", "C"], "available": [3, 3, 2],
         "allocation": [[0, 1, 0], [2, 0, 0], [3, 0, 2], [2, 1, 1], [0, 0, 2]],
         "maximum": [[7, 5, 3], [3, 2, 2], [9, 0, 2], [2, 2, 2], [4, 3, 3]]},
        {"name": "Unsafe state", "resources": ["A", "B", "C"], "available": [2, 1, 0],    # P1, P3 finish, then stuck
         "allocation": [[0, 1, 0], [2, 0, 0], [3, 0, 2], [2, 1, 1], [0, 0, 2]],
         "maximum": [[7, 5, 3], [3, 1, 0], [9, 0, 4], [4, 1, 1], [4, 3, 3]]},
    ],
    "semaphores": [
        {"name": "Mutex, three processes", "initial": {"mutex": 1},
         "ops": [["P1", "wait", "mutex"], ["P2", "wait", "mutex"], ["P3", "wait", "mutex"],
                 ["P1", "signal", "mutex"], ["P2", "signal", "mutex"], ["P3", "signal", "mutex"]]},
        {"name": "Counting semaphore (2 printers)", "initial": {"S": 2},
         "ops": [["P1", "wait", "S"], ["P2", "wait", "S"], ["P3", "wait", "S"], ["P4", "wait", "S"],
                 ["P1", "signal", "S"], ["P2", "signal", "S"]]},
        {"name": "Producer–consumer (buffer of 2)", "initial": {"mutex": 1, "empty": 2, "full": 0},
         "ops": [["C", "wait", "full"],                                            # buffer empty: consumer blocks
                 ["P", "wait", "empty"], ["P", "wait", "mutex"], ["P", "signal", "mutex"], ["P", "signal", "full"],
                 ["C", "wait", "mutex"], ["C", "signal", "mutex"], ["C", "signal", "empty"],
                 ["P", "wait", "empty"], ["P", "signal", "full"], ["P", "wait", "empty"], ["P", "signal", "full"],
                 ["P", "wait", "empty"]]},                                         # buffer full: producer blocks
    ],
    "deadlocks": [
        {"name": "Two processes, one instance each (deadlock)", "processes": ["P1", "P2"],
         "resources": [["R1", 1], ["R2", 1]],
         "edges": [["P1", "holds", "R1", 1], ["P2", "holds", "R2", 1], ["P1", "wants", "R2", 1], ["P2", "wants", "R1", 1]]},
        {"name": "Cycle, but no deadlock", "processes": ["P1", "P2", "P3", "P4"],      # Silberschatz Fig. 7.3
         "resources": [["R1", 2], ["R2", 2]],
         "edges": [["P1", "holds", "R2", 1], ["P1", "wants", "R1", 1], ["P2", "holds", "R1", 1],
                   ["P3", "holds", "R1", 1], ["P3", "wants", "R2", 1], ["P4", "holds", "R2", 1]]},
        {"name": "Theory folder deadlock problem", "processes": ["P0", "P1", "P2", "P3"],
         "resources": [["R1", 2], ["R2", 3], ["R3", 3], ["R4", 2]],
         "edges": [["P0", "holds", "R1", 1], ["P1", "holds", "R1", 1], ["P1", "holds", "R2", 1], ["P2", "holds", "R2", 1],
                   ["P3", "holds", "R2", 1], ["P0", "holds", "R3", 2], ["P3", "holds", "R4", 1], ["P2", "holds", "R4", 1],
                   ["P1", "wants", "R1", 1], ["P0", "wants", "R2", 1], ["P3", "wants", "R1", 1], ["P3", "wants", "R2", 2],
                   ["P0", "wants", "R3", 1], ["P2", "wants", "R3", 1]]},
    ],
}


class LabError(ValueError):
    """Bad input, explained in words the student can act on."""


# ============================================================================ scheduler lab
def _processes(rows: list) -> list[Process]:
    procs = []
    for k, r in enumerate(rows, start=1):
        try:
            pid = str(r[0]).strip().upper() or f"P{k}"
            procs.append(Process(pid, int(r[1]), int(r[2]), int(r[3]) if len(r) > 3 and r[3] not in ("", None) else 0))
        except (TypeError, ValueError, IndexError):
            raise LabError(f"Row {k}: arrival, burst and priority must be whole numbers.") from None
    if len(procs) > 10:
        raise LabError("Use at most 10 processes.")
    try:
        scheduling._validate(procs)
    except ValueError as e:
        raise LabError(str(e)) from None
    if sum(p.burst for p in procs) + max(p.arrival for p in procs) > 200:
        raise LabError("Keep the total time under 200 units so the charts stay readable.")
    return procs


def scheduler(rows: list, quantum: int | None, lower_is_higher: bool = True) -> dict:
    procs = _processes(rows)
    q = int(quantum or 2)
    if q < 1:
        raise LabError("The time quantum must be at least 1.")
    runs = []
    for algo in ALGORITHMS:
        res = scheduling.run(algo, procs, q if algo == "RR" else None, lower_is_higher=lower_is_higher)
        pf = performance(res.gantt, len(procs))
        runs.append({
            "algorithm": algo, "name": ALGORITHMS[algo] + (f", q = {q}" if algo == "RR" else ""),
            "short": SHORT_NAMES[algo], "gantt": gantt(res.gantt, [p.pid for p in procs]),
            "results": table(["Process", "AT", "BT", "CT", "TAT", "WT", "RT"],
                             [[r.pid, r.arrival, r.burst, r.completion, r.turnaround, r.waiting, r.response]
                              for r in res.results.values()]),
            "decisions": table(["t", "Ready (remaining)", "Chosen", "Why"],
                               [[d.time, ", ".join(f"{x['pid']} ({x['remaining']})" for x in d.ready) or "—", d.chosen,
                                 d.reason] for d in res.decisions]),
            "avg_wt": round(res.avg_wt, 2), "avg_tat": round(res.avg_tat, 2), "avg_rt": round(res.avg_rt, 2),
            "switches": pf["context_switches"], "utilisation": pf["cpu_utilization"], "makespan": res.makespan})
    best = min(r["avg_wt"] for r in runs)
    return {"processes": [[p.pid, p.arrival, p.burst, p.priority] for p in procs], "quantum": q,
            "span": max(r["makespan"] for r in runs), "order": [p.pid for p in procs], "runs": runs,
            "best": [r["algorithm"] for r in runs if r["avg_wt"] == best],
            "note": ("Ties go to the earlier arrival. SRTF and preemptive priority preempt only when strictly better. "
                     f"Priority: {'lower' if lower_is_higher else 'higher'} number = higher priority. Round Robin: "
                     "a process arriving when a slice ends joins the queue before the preempted one.")}


def random_scheduler(seed: int | None = None) -> dict:
    rng = random.Random(seed)
    prob = generator.generate_scheduling("PRIORITY_P", rng.choice([2, 3]), rng.randrange(10**9))
    return {"processes": [[p.pid, p.arrival, p.burst, p.priority] for p in prob.processes], "quantum": rng.choice([2, 3, 4])}


# ============================================================================ Banker's lab
def _matrix(m, name: str) -> list[list[int]]:
    try:
        return [[int(x) for x in row] for row in m]
    except (TypeError, ValueError):
        raise LabError(f"{name}: every value must be a whole number.") from None


def bankers_lab(available: list, maximum: list, allocation: list, resources: list[str] | None = None,
                req: dict | None = None) -> dict:
    av, mx, al = _matrix([available], "Available")[0], _matrix(maximum, "Max"), _matrix(allocation, "Allocation")
    if not 2 <= len(mx) <= 8 or not 1 <= len(av) <= 5:
        raise LabError("Use 2 to 8 processes and 1 to 5 resource types.")
    resources = list(resources or [])[:len(av)]
    resources += [chr(65 + k) for k in range(len(resources), len(av))]
    try:
        bankers.validate(av, mx, al)
    except ValueError as e:
        raise LabError(str(e)) from None
    out = {"walk": bankers_walk(av, mx, al, resources), "request": None}
    if req:
        pid = int(req.get("pid", 0))
        vec = _matrix([req.get("vector") or []], "Request")[0]
        if not 0 <= pid < len(mx) or len(vec) != len(av):
            raise LabError(f"The request needs a process P0–P{len(mx) - 1} and {len(av)} values.")
        r = bankers.request(av, mx, al, pid, vec)
        out["request"] = {"granted": r["granted"], "reason": r["reason"], "message": r["message"],
                          "pid": f"P{pid}", "vector": " ".join(map(str, vec))}
        if r.get("new_available") is not None:
            out["request"]["walk"] = bankers_walk(r["new_available"], mx, r["new_allocation"], resources)
    return out


def random_bankers(seed: int | None = None) -> dict:
    rng = random.Random(seed)
    b = generator.generate_bankers(rng.choice([2, 3]), rng.randrange(10**9))
    return {"resources": b.resources, "available": b.available, "maximum": b.maximum, "allocation": b.allocation}


# ============================================================================ semaphore lab
def semaphores_lab(initial: dict, ops: list) -> dict:
    try:
        init = {str(k).strip(): int(v) for k, v in initial.items() if str(k).strip()}
    except (TypeError, ValueError):
        raise LabError("Initial values must be whole numbers.") from None
    if not init:
        raise LabError("Add at least one semaphore.")
    if len(ops) > 30:
        raise LabError("Use at most 30 operations.")
    clean = [{"pid": str(o[0]).strip().upper() or "P1", "op": str(o[1]).strip().lower(), "sem": str(o[2]).strip()}
             for o in ops]
    try:
        styles = {s: semaphore.trace(init, clean, s) for s in ("blocking", "busy_wait")}
    except ValueError as e:
        raise LabError(str(e)) from None
    pids = sorted({o["pid"] for o in clean}, key=lambda p: (len(p), p))
    out = {"sems": list(init), "pids": pids}
    for style, tr in styles.items():
        lanes = {p: [] for p in pids}            # per step, what each process is doing
        blocked: set[str] = set()
        for s in tr["steps"]:
            if "blocks" in s["effect"] or "spins" in s["effect"]:
                blocked.add(s["pid"])
            if s["woken"]:
                blocked.discard(s["woken"])
            for p in pids:
                lanes[p].append("acts" if p == s["pid"] and "invalid" not in s["effect"] else
                                "invalid" if p == s["pid"] else
                                ("blocked" if style == "blocking" else "spinning") if p in blocked else "")
        out[style] = {
            "steps": [{"n": s["step"], "pid": s["pid"], "op": s["op"], "sem": s["sem"], "before": s["value_before"],
                       "after": s["value_after"], "effect": named_effect(s["effect"], s["sem"]),
                       "queue": s["queues"].get(s["sem"], []) if style == "blocking" else []} for s in tr["steps"]],
            "lanes": lanes, "final": tr["final_values"], "blocked": tr["blocked"]}
    return out


def random_semaphores(seed: int | None = None) -> dict:
    rng = random.Random(seed)
    s = generator.generate_semaphore(rng.choice([2, 3]), rng.randrange(10**9))
    return {"initial": s.initial, "ops": [[o["pid"], o["op"], o["sem"]] for o in s.ops]}


# ============================================================================ deadlock lab
def deadlocks_lab(processes: list, resources: list, edges: list) -> dict:
    procs = [str(p).strip().upper() for p in processes if str(p).strip()]
    try:
        res = {str(r[0]).strip().upper(): int(r[1]) for r in resources if str(r[0]).strip()}
        clean = [(str(e[0]).strip().upper(), str(e[1]).strip().lower(), str(e[2]).strip().upper(), int(e[3])) for e in edges]
    except (TypeError, ValueError, IndexError):
        raise LabError("Every count must be a whole number.") from None
    if not 1 <= len(procs) <= 8 or not 1 <= len(res) <= 6 or len(set(procs)) != len(procs):
        raise LabError("Use 1 to 8 processes and 1 to 6 resources, each with a different name.")
    if any(n < 1 for n in res.values()):
        raise LabError("Every resource needs at least one instance.")
    try:
        g = deadlock.analyse_graph(procs, res, [(p, r, c) for p, kind, r, c in clean if kind == "holds"],
                                   [(p, r, c) for p, kind, r, c in clean if kind != "holds"])
    except ValueError as e:
        raise LabError(str(e)) from None
    det = g["detection"]
    cyc_edges = {(c[k], c[(k + 1) % len(c)]) for c in g["cycles"] for k in range(len(c))}
    return {"processes": procs, "resources": [[r, n] for r, n in res.items()],
            "edges": [{"from": r if kind == "holds" else p, "to": p if kind == "holds" else r, "kind": kind, "count": c,
                       "in_cycle": ((r, p) if kind == "holds" else (p, r)) in cyc_edges} for p, kind, r, c in clean],
            "cycles": g["cycles"], "wait_for": [list(e) for e in g["wait_for"]], "wait_for_cycles": g["wait_for_cycles"],
            "single_instance": g["single_instance"], "deadlock": g["deadlock"], "why": g["why"],
            "tables": [{"label": "Allocation (held)", **table(["", *g["resources"]], [[p, *r] for p, r in zip(procs, g["allocation"])])},
                       {"label": "Request (waiting for)", **table(["", *g["resources"]], [[p, *r] for p, r in zip(procs, g["request"])])},
                       {"label": "Available", **table(g["resources"], [g["available"]])}],
            "steps": table(["Step", "Process", "Request", "Work before", "+ Allocation", "Work after"],
                           [[s["step"], s["process"], " ".join(map(str, s["request"])), " ".join(map(str, s["work_before"])),
                             " ".join(map(str, s["allocation_released"])), " ".join(map(str, s["work_after"]))] for s in det["steps"]]),
            "sequence": det["sequence"], "deadlocked": det["deadlocked"], "skipped": det["skipped"]}


# ============================================================================ reading a pasted question
def parse(text: str) -> dict:
    sched = parse_scheduling_problem(text)
    if sched:
        return {"kind": "scheduler", "processes": [[p.pid, p.arrival, p.burst, p.priority] for p in sched["processes"]],
                "quantum": sched.get("quantum")}
    bk = parse_bankers_problem(text)
    if bk:
        return {"kind": "bankers", **{k: bk[k] for k in ("available", "maximum", "allocation") if k in bk},
                "resources": bk.get("resources")}
    raise LabError("I couldn't read a scheduling or Banker's problem from that text. Try a table with Process, "
                   "Arrival and Burst columns, or P1(0,5) P2(1,3).")

